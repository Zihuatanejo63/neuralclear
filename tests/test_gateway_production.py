"""HTTP acceptance tests for tenant auth, isolation, health, and production startup."""

from __future__ import annotations

import io
import json
import logging
import os
import sqlite3
import tempfile
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from neuralclear.accesslog import JsonFormatter
from neuralclear.core import ProtocolError
from neuralclear.gateway import ClearingGateway, assemble_gateway, main
from neuralclear.httpwire import ProviderHTTPServer
from neuralclear.provider import ProviderAgent
from neuralclear.runtime_config import DEV_RECEIPT_SECRET, GatewayStartupError, load_settings
from neuralclear.tenancy import TenantHub

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_SECRET = "unit-test-receipt-secret-value-32"


def http_json(
    method: str,
    url: str,
    body: dict | None = None,
    api_key: str | None = None,
) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if api_key is not None:
        headers["X-NeuralClear-Api-Key"] = api_key
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode() or "{}")
            payload["_status"] = response.status
            return payload
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode() or "{}"
        payload = json.loads(raw)
        payload["_status"] = exc.code
        return payload


def http_text(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


class TenantIsolationHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "gateway.db")
        self.hub = TenantHub(store_path=self.db, receipt_secret=RECEIPT_SECRET)
        self.alice = self.hub.create_tenant("Alice")
        self.bolt = self.hub.create_tenant("Bolt")
        self.gw = ClearingGateway(hub=self.hub, host="127.0.0.1", port=0).start()
        self.addCleanup(self.gw.stop)
        self.base = self.gw.url

    def test_missing_and_wrong_key_are_401_on_reads_and_writes(self) -> None:
        missing_read = http_json("GET", f"{self.base}/v1/ledger")
        wrong_read = http_json("GET", f"{self.base}/v1/ledger", api_key="nck_wrong_key_value")
        missing_receipt = http_json("GET", f"{self.base}/v1/receipts/rcpt_missing")
        missing_write = http_json(
            "POST", f"{self.base}/v1/accounts", {"account": "owner.x", "deposit": 1}
        )
        wrong_write = http_json(
            "POST",
            f"{self.base}/v1/accounts",
            {"account": "owner.x", "deposit": 1},
            api_key="nck_wrong_key_value",
        )
        for response in (missing_read, wrong_read, missing_receipt, missing_write, wrong_write):
            self.assertEqual(response.get("_status"), 401)
            self.assertEqual(response.get("error"), "invalid api key")
            self.assertNotIn("balances", response)

    def test_tenants_cannot_read_or_mutate_each_other(self) -> None:
        created = http_json(
            "POST",
            f"{self.base}/v1/accounts",
            {"account": "owner.a", "deposit": 50},
            self.alice.api_key,
        )
        self.assertEqual(created.get("_status"), 200)
        http_json(
            "POST",
            f"{self.base}/v1/accounts",
            {"account": "agent.a", "deposit": 0},
            self.alice.api_key,
        )
        http_json(
            "POST",
            f"{self.base}/v1/accounts",
            {"account": "owner.b", "deposit": 7},
            self.bolt.api_key,
        )

        alice_ledger = http_json("GET", f"{self.base}/v1/ledger", api_key=self.alice.api_key)
        bolt_ledger = http_json("GET", f"{self.base}/v1/ledger", api_key=self.bolt.api_key)
        self.assertEqual(alice_ledger["balances"].get("owner.a"), 50)
        self.assertNotIn("owner.b", alice_ledger["balances"])
        self.assertEqual(bolt_ledger["balances"].get("owner.b"), 7)
        self.assertNotIn("owner.a", bolt_ledger["balances"])

        http_json(
            "POST",
            f"{self.base}/v1/accounts",
            {"account": "owner.a", "deposit": 10},
            self.bolt.api_key,
        )
        alice_again = http_json("GET", f"{self.base}/v1/ledger", api_key=self.alice.api_key)
        self.assertEqual(alice_again["balances"].get("owner.a"), 50)
        bolt_again = http_json("GET", f"{self.base}/v1/ledger", api_key=self.bolt.api_key)
        self.assertEqual(bolt_again["balances"].get("owner.a"), 10)
        self.assertEqual(bolt_again["balances"].get("owner.b"), 7)

        channel = http_json(
            "POST",
            f"{self.base}/v1/channels",
            {"buyer": "owner.a", "provider": "agent.a", "deposit": 20},
            self.alice.api_key,
        )
        self.assertEqual(channel.get("_status"), 200)
        denied = http_json(
            "POST",
            f"{self.base}/v1/channels/{channel['channel_id']}/meter",
            {"capability": "echo", "amount": 1, "payload_hash": "sha256:nope"},
            self.bolt.api_key,
        )
        self.assertEqual(denied.get("_status"), 400)
        self.assertIn("unknown channel", str(denied.get("error")))

        metered = http_json(
            "POST",
            f"{self.base}/v1/channels/{channel['channel_id']}/meter",
            {"capability": "echo", "amount": 1, "payload_hash": "sha256:ok"},
            self.alice.api_key,
        )
        self.assertEqual(metered.get("_status"), 200)
        self.assertEqual(metered.get("sequence"), 0)
        receipt = http_json(
            "POST",
            f"{self.base}/v1/channels/{channel['channel_id']}/settle",
            {},
            self.alice.api_key,
        )
        self.assertEqual(receipt.get("_status"), 200)
        fetched = http_json(
            "GET",
            f"{self.base}/v1/receipts/{receipt['receipt_id']}",
            api_key=self.alice.api_key,
        )
        self.assertEqual(fetched.get("_status"), 200)
        self.assertEqual(fetched.get("receipt_id"), receipt["receipt_id"])
        hidden = http_json(
            "GET",
            f"{self.base}/v1/receipts/{receipt['receipt_id']}",
            api_key=self.bolt.api_key,
        )
        self.assertEqual(hidden.get("_status"), 404)
        self.assertNotEqual(hidden.get("receipt_id"), receipt["receipt_id"])

    def test_key_rotation_rejects_the_old_key(self) -> None:
        http_json(
            "POST",
            f"{self.base}/v1/accounts",
            {"account": "owner.a", "deposit": 40},
            self.alice.api_key,
        )
        old = self.alice.api_key
        new = self.hub.rotate_key(self.alice.tenant_id)
        rejected = http_json("GET", f"{self.base}/v1/ledger", api_key=old)
        self.assertEqual(rejected.get("_status"), 401)
        accepted = http_json("GET", f"{self.base}/v1/ledger", api_key=new)
        self.assertEqual(accepted.get("_status"), 200)
        self.assertEqual(accepted["balances"].get("owner.a"), 40)

    def test_rotation_in_another_process_invalidates_the_old_key(self) -> None:
        http_json(
            "POST",
            f"{self.base}/v1/accounts",
            {"account": "owner.a", "deposit": 15},
            self.alice.api_key,
        )
        old = self.alice.api_key
        other = TenantHub(store_path=self.db, receipt_secret=RECEIPT_SECRET)
        new = other.rotate_key(self.alice.tenant_id)
        rejected = http_json("GET", f"{self.base}/v1/ledger", api_key=old)
        self.assertEqual(rejected.get("_status"), 401)
        accepted = http_json("GET", f"{self.base}/v1/ledger", api_key=new)
        self.assertEqual(accepted["balances"].get("owner.a"), 15)
        with self.assertRaises(ProtocolError):
            self.hub.by_key(old)

    def test_restart_keeps_tenant_state_and_not_the_raw_key(self) -> None:
        http_json(
            "POST",
            f"{self.base}/v1/accounts",
            {"account": "owner.a", "deposit": 80},
            self.alice.api_key,
        )
        http_json(
            "POST",
            f"{self.base}/v1/accounts",
            {"account": "agent.a", "deposit": 0},
            self.alice.api_key,
        )
        channel = http_json(
            "POST",
            f"{self.base}/v1/channels",
            {"buyer": "owner.a", "provider": "agent.a", "deposit": 30},
            self.alice.api_key,
        )
        first = http_json(
            "POST",
            f"{self.base}/v1/channels/{channel['channel_id']}/meter",
            {"capability": "echo", "amount": 1, "payload_hash": "sha256:1"},
            self.alice.api_key,
        )
        self.assertEqual(first.get("sequence"), 0)
        key = self.alice.api_key
        self.gw.stop()

        for suffix in ("", "-wal", "-shm"):
            path = self.db + suffix
            if os.path.exists(path):
                self.assertNotIn(key.encode(), Path(path).read_bytes())
        with sqlite3.connect(self.db) as conn:
            stored = " ".join(row[0] for row in conn.execute("SELECT key_hash FROM tenants"))
        self.assertNotIn(key, stored)

        restored = TenantHub(store_path=self.db, receipt_secret=RECEIPT_SECRET)
        self.assertEqual(restored.by_key(key).clearing.ledger.balance_of("owner.a"), 50)
        gw2 = ClearingGateway(hub=restored, host="127.0.0.1", port=0).start()
        self.addCleanup(gw2.stop)
        second = http_json(
            "POST",
            f"{gw2.url}/v1/channels/{channel['channel_id']}/meter",
            {"capability": "echo", "amount": 1, "payload_hash": "sha256:2"},
            key,
        )
        self.assertEqual(second.get("sequence"), 1)
        receipt = http_json(
            "POST",
            f"{gw2.url}/v1/channels/{channel['channel_id']}/settle",
            {},
            key,
        )
        self.assertEqual(receipt.get("tasks_metered"), 2)
        receipt.pop("_status", None)
        self.assertTrue(restored.by_key(key).clearing.signer.verify(receipt))

    def test_health_and_metrics(self) -> None:
        live = http_json("GET", f"{self.base}/health/live")
        ready = http_json("GET", f"{self.base}/health/ready")
        health = http_json("GET", f"{self.base}/health")
        self.assertEqual(live.get("_status"), 200)
        self.assertEqual(live.get("status"), "ok")
        self.assertEqual(ready.get("_status"), 200)
        self.assertEqual(ready.get("storage"), "ok")
        self.assertEqual(ready.get("fiat_settlement"), "not_live")
        self.assertEqual(health.get("_status"), 200)
        self.assertEqual(health.get("fiat_settlement"), "not_live")

        leaked = "nck_this_value_must_not_appear_in_metrics"
        http_json("GET", f"{self.base}/v1/ledger", api_key=leaked)
        status, body = http_text(f"{self.base}/metrics")
        self.assertEqual(status, 200)
        self.assertIn("neuralclear_http_requests_total", body)
        self.assertIn("neuralclear_auth_failures_total", body)
        self.assertIn("neuralclear_http_request_duration_seconds", body)
        self.assertIn('fiat_settlement="not_live"', body)
        self.assertIn('reason="invalid"', body)
        self.assertNotIn(leaked, body)
        self.assertNotIn(self.alice.api_key, body)
        self.assertNotIn(self.bolt.api_key, body)

    def test_ready_fails_when_storage_is_closed(self) -> None:
        self.assertEqual(http_json("GET", f"{self.base}/health/ready").get("_status"), 200)
        assert self.hub.store is not None
        self.hub.store.close()
        ready = http_json("GET", f"{self.base}/health/ready")
        live = http_json("GET", f"{self.base}/health/live")
        self.assertEqual(ready.get("_status"), 503)
        self.assertEqual(ready.get("storage"), "error")
        self.assertEqual(live.get("_status"), 200)
        status, metrics = http_text(f"{self.base}/metrics")
        self.assertEqual(status, 200)
        self.assertIn("neuralclear_gateway_ready 0", metrics)


class ProductionStartupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_env = os.environ.copy()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self._restore_env)
        self.db = os.path.join(self.tmp.name, "gateway.db")

    def _restore_env(self) -> None:
        os.environ.clear()
        os.environ.update(self._saved_env)
        from neuralclear.kms import set_process_kms

        set_process_kms(None)

    def _production(self, **extra: str) -> dict[str, str]:
        env = {
            "NEURALCLEAR_ENV": "production",
            "NEURALCLEAR_MODE": "production",
            "NEURALCLEAR_DB": self.db,
            "NEURALCLEAR_KMS_PATH": os.path.join(self.tmp.name, "kms.db"),
            "NEURALCLEAR_KMS_ENV": "test",
            "NEURALCLEAR_REPLAY_STORE": os.path.join(self.tmp.name, "replay.db"),
            "NEURALCLEAR_SIGNING_KEY_ID": "gateway-receipt",
            "NEURALCLEAR_TLS_MODE": "terminator",
            "NEURALCLEAR_GATEWAY_HOST": "127.0.0.1",
            "NEURALCLEAR_GATEWAY_PORT": "0",
        }
        env.update(extra)
        return env

    def test_production_refuses_missing_placeholder_and_sandbox_secrets(self) -> None:
        with self.assertRaises(GatewayStartupError):
            load_settings({"NEURALCLEAR_ENV": "production", "NEURALCLEAR_DB": self.db}, command="serve")
        with self.assertRaises(GatewayStartupError):
            load_settings(self._production(NEURALCLEAR_KMS_ENV="live"), command="serve")
        with self.assertRaises(GatewayStartupError):
            load_settings(self._production(NEURALCLEAR_REPLAY_STORE=""), command="serve")
        with self.assertRaises(GatewayStartupError):
            load_settings(
                self._production(NEURALCLEAR_RECEIPT_SECRET=DEV_RECEIPT_SECRET),
                command="serve",
            )
        with self.assertRaises(GatewayStartupError):
            load_settings(
                self._production(NEURALCLEAR_SIGNING_SECRET="sandbox-hmac-secret-value"),
                command="serve",
            )
        with self.assertRaises(GatewayStartupError):
            load_settings(
                self._production(NEURALCLEAR_BOOTSTRAP_API_KEY="nck_replace_me_not_a_real_key"),
                command="serve",
            )
        with self.assertRaises(GatewayStartupError):
            load_settings(self._production(NEURALCLEAR_API_KEY="dev_neuralclear_key"), command="serve")
        with self.assertRaises(GatewayStartupError):
            load_settings(self._production(NEURALCLEAR_TLS_MODE="direct"), command="serve")

        key_file = os.path.join(self.tmp.name, "bootstrap")
        Path(key_file).write_text("nck_" + ("ab" * 16) + "\n", encoding="utf-8")
        both = self._production(
            NEURALCLEAR_RECEIPT_SECRET_FILE=os.path.join(self.tmp.name, "receipt"),
            NEURALCLEAR_BOOTSTRAP_API_KEY_FILE=key_file,
        )
        with self.assertRaises(GatewayStartupError):
            load_settings(both, command="serve")
        del both["NEURALCLEAR_RECEIPT_SECRET_FILE"]
        settings = load_settings(both, command="serve")
        self.assertIsNone(settings.receipt_secret)
        self.assertEqual(settings.kms_env, "test")
        self.assertEqual(settings.bootstrap_api_key, "nck_" + ("ab" * 16))

    def test_production_refuses_to_serve_without_a_tenant(self) -> None:
        env = self._production()
        self.assertEqual(main(["kms-init"], env), 0)
        settings = load_settings(env, command="serve")
        with self.assertRaises(GatewayStartupError) as caught:
            assemble_gateway(settings)
        self.assertIn("tenant", str(caught.exception).lower())

    def test_production_serves_when_secrets_and_a_tenant_exist(self) -> None:
        bootstrap = "nck_" + ("cd" * 16)
        env = self._production(
            NEURALCLEAR_BOOTSTRAP_API_KEY=bootstrap,
            NEURALCLEAR_BOOTSTRAP_TENANT_NAME="primary",
        )
        self.assertEqual(main(["kms-init"], env), 0)
        settings = load_settings(env, command="serve")
        gateway = assemble_gateway(settings).start()
        self.addCleanup(gateway.stop)
        self.assertTrue(settings.production)
        self.assertIsNone(settings.receipt_secret)
        ready = http_json("GET", f"{gateway.url}/health/ready")
        self.assertEqual(ready.get("_status"), 200)
        self.assertEqual(ready.get("fiat_settlement"), "not_live")
        ledger = http_json("GET", f"{gateway.url}/v1/ledger", api_key=bootstrap)
        self.assertEqual(ledger.get("_status"), 200)
        missing = http_json("GET", f"{gateway.url}/v1/ledger")
        self.assertEqual(missing.get("_status"), 401)
        status, metrics = http_text(f"{gateway.url}/metrics")
        self.assertEqual(status, 200)
        self.assertIn('signing="persistent-kms"', metrics)
        self.assertNotIn(bootstrap, metrics)
        blob = Path(self.db).read_bytes()
        self.assertNotIn(bootstrap.encode(), blob)

    def test_cli_issues_a_key_once_and_rotation_rejects_it(self) -> None:
        env = {
            "NEURALCLEAR_ENV": "development",
            "NEURALCLEAR_DB": self.db,
            "NEURALCLEAR_TLS_MODE": "terminator",
        }
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["tenant-create", "--name", "Acme"], env)
        self.assertEqual(code, 0)
        issued = dict(
            line.split("=", 1) for line in out.getvalue().splitlines() if "=" in line
        )
        self.assertTrue(issued["tenant_id"].startswith("ten_"))
        self.assertTrue(issued["api_key"].startswith("nck_"))
        self.assertNotIn(issued["api_key"], err.getvalue())

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["tenant-rotate", "--tenant-id", issued["tenant_id"]], env)
        self.assertEqual(code, 0)
        rotated = dict(
            line.split("=", 1) for line in out.getvalue().splitlines() if "=" in line
        )
        self.assertNotEqual(rotated["api_key"], issued["api_key"])
        self.assertNotIn(rotated["api_key"], err.getvalue())
        hub = TenantHub(store_path=self.db, receipt_secret=DEV_RECEIPT_SECRET)
        self.assertIsNotNone(hub.by_key(rotated["api_key"]))
        with self.assertRaises(ProtocolError):
            hub.by_key(issued["api_key"])

    def test_main_serve_fails_closed_without_printing_a_secret(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            code = main(
                ["serve"],
                self._production(NEURALCLEAR_RECEIPT_SECRET="replace-me-not-a-signing-secret"),
            )
        self.assertEqual(code, 1)
        self.assertNotIn("replace-me-not-a-signing-secret", err.getvalue())
        self.assertIn("authenticator", err.getvalue())


class LegacyGatewayTests(unittest.TestCase):
    def test_single_key_still_allows_unauthenticated_reads(self) -> None:
        gateway = ClearingGateway(api_key="k_test", host="127.0.0.1", port=0).start()
        self.addCleanup(gateway.stop)
        ledger = http_json("GET", f"{gateway.url}/v1/ledger")
        self.assertEqual(ledger.get("_status"), 200)
        denied = http_json("POST", f"{gateway.url}/v1/accounts", {"account": "x", "deposit": 1})
        self.assertEqual(denied.get("_status"), 401)
        live = http_json("GET", f"{gateway.url}/health/live")
        ready = http_json("GET", f"{gateway.url}/health/ready")
        self.assertEqual(live.get("fiat_settlement"), "not_live")
        self.assertEqual(ready.get("_status"), 200)
        self.assertEqual(ready.get("storage"), "unconfigured")
        self.assertEqual(ready.get("fiat_settlement"), "not_live")


class LogScrubTests(unittest.TestCase):
    def test_access_formatter_drops_raw_keys(self) -> None:
        record = logging.makeLogRecord(
            {
                "msg": "request nck_in_the_message",
                "levelno": logging.INFO,
                "levelname": "INFO",
                "name": "neuralclear.gateway",
            }
        )
        record.fields = {"path": "/v1/ledger", "api_key": "nck_supersecret", "note": "nck_other"}
        text = JsonFormatter().format(record)
        self.assertNotIn("nck_in_the_message", text)
        self.assertNotIn("nck_supersecret", text)
        self.assertNotIn("nck_other", text)
        self.assertNotIn("api_key", text)
        self.assertIn("[redacted]", text)


class ProductionArtifactTests(unittest.TestCase):
    def test_compose_and_image_do_not_bake_secrets(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        compose = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
        caddy = (ROOT / "deploy" / "Caddyfile").read_text(encoding="utf-8")
        alerts = (ROOT / "deploy" / "prometheus" / "alerts.yml").read_text(encoding="utf-8")
        self.assertNotIn("NEURALCLEAR_API_KEY", dockerfile)
        self.assertNotIn("dev_neuralclear_key", compose)
        self.assertNotIn("server.app", compose)
        self.assertNotIn("8080:8080", compose)
        self.assertNotIn("BEGIN CERTIFICATE", compose)
        self.assertNotIn("sk_live", compose)
        self.assertIn("neuralclear.gateway", compose)
        self.assertIn("caddy:2.11-alpine", compose)
        self.assertIn("NEURALCLEAR_MODE: production", compose)
        self.assertIn("NEURALCLEAR_KMS_ENV: test", compose)
        self.assertNotIn("NEURALCLEAR_KMS_ENV: live", compose)
        self.assertIn("NEURALCLEAR_REPLAY_STORE", compose)
        self.assertIn("127.0.0.1:9090:9090", compose)
        self.assertIn("reverse_proxy gateway:8080", caddy)
        self.assertIn("admin off", caddy)
        self.assertIn("X-NeuralClear-Api-Key delete", caddy)
        for name in (
            "NeuralclearGatewayDown",
            "NeuralclearHigh5xx",
            "NeuralclearAuthFailureSpike",
            "NeuralclearTlsCertExpiring",
            "NeuralclearTlsProbeFailing",
        ):
            self.assertIn(name, alerts)
        gateway_source = (ROOT / "neuralclear" / "gateway.py").read_text(encoding="utf-8")
        self.assertIn("cannot attach the fiat", gateway_source)
        self.assertNotIn("sk_live", gateway_source)
        self.assertNotIn("stripe.api", gateway_source.lower())
        self.assertIn("compare_digest", gateway_source)


class ProductionSignerPathTests(ProductionStartupTests):
    def _started(self) -> tuple[ClearingGateway, str]:
        bootstrap = "nck_" + ("ef" * 16)
        env = self._production(
            NEURALCLEAR_BOOTSTRAP_API_KEY=bootstrap,
            NEURALCLEAR_BOOTSTRAP_TENANT_NAME="primary",
        )
        self.assertEqual(main(["kms-init"], env), 0)
        gateway = assemble_gateway(load_settings(env, command="serve")).start()
        self.addCleanup(gateway.stop)
        return gateway, bootstrap

    def test_mockproof_is_refused_and_credits_are_refunded(self) -> None:
        provider = ProviderAgent("agent.echo")

        @provider.capability("echo.text", price=10, resource_estimate=1, resource_unit="calls")
        def echo(payload: object) -> object:
            return {"echo": payload}

        server = ProviderHTTPServer(provider).start()
        self.addCleanup(server.stop)
        gateway, key = self._started()
        opened = http_json(
            "POST",
            f"{gateway.url}/v1/accounts",
            {"account": "owner.a", "deposit": 200},
            key,
        )
        self.assertEqual(opened.get("_status"), 200)
        http_json(
            "POST",
            f"{gateway.url}/v1/accounts",
            {"account": "agent.echo", "deposit": 0},
            key,
        )
        refused = http_json(
            "POST",
            f"{gateway.url}/v1/clear",
            {
                "buyer_owner": "owner.a",
                "provider_url": server.url,
                "capability": "echo.text",
                "payload": {"msg": "hi"},
            },
            key,
        )
        self.assertEqual(refused.get("_status"), 400)
        self.assertIn("MockProof is not allowed in production", str(refused.get("error")))
        ledger = http_json("GET", f"{gateway.url}/v1/ledger", api_key=key)
        self.assertEqual(ledger["balances"].get("owner.a"), 200)
        self.assertEqual(ledger.get("escrow_total", 0), 0)

    def test_receipt_replay_and_kid_revocation(self) -> None:
        gateway, key = self._started()
        http_json(
            "POST",
            f"{gateway.url}/v1/accounts",
            {"account": "owner.a", "deposit": 100},
            key,
        )
        http_json(
            "POST",
            f"{gateway.url}/v1/accounts",
            {"account": "agent.a", "deposit": 0},
            key,
        )
        channel = http_json(
            "POST",
            f"{gateway.url}/v1/channels",
            {"buyer": "owner.a", "provider": "agent.a", "deposit": 20},
            key,
        )
        http_json(
            "POST",
            f"{gateway.url}/v1/channels/{channel['channel_id']}/meter",
            {"capability": "echo", "amount": 1, "payload_hash": "sha256:1"},
            key,
        )
        receipt = http_json(
            "POST",
            f"{gateway.url}/v1/channels/{channel['channel_id']}/settle",
            {},
            key,
        )
        self.assertEqual(receipt.get("_status"), 200)
        self.assertTrue(str(receipt.get("signature", "")).startswith("ed25519:"))
        self.assertEqual(receipt.get("key_id"), "gateway-receipt")
        receipt.pop("_status", None)
        signer = gateway.hub._signer  # type: ignore[union-attr]
        self.assertTrue(signer.verify(dict(receipt)))
        with self.assertRaisesRegex(ProtocolError, "replayed nonce"):
            signer.verify(dict(receipt))

        channel_b = http_json(
            "POST",
            f"{gateway.url}/v1/channels",
            {"buyer": "owner.a", "provider": "agent.a", "deposit": 10},
            key,
        )
        later = http_json(
            "POST",
            f"{gateway.url}/v1/channels/{channel_b['channel_id']}/settle",
            {},
            key,
        )
        later.pop("_status", None)
        signer.kms.revoke("gateway-receipt")
        with self.assertRaisesRegex(ProtocolError, "revoked key"):
            signer.verify(dict(later))

    def test_hmac_hub_is_not_a_production_gateway(self) -> None:
        hub = TenantHub(store_path=self.db, receipt_secret="unit-test-receipt-secret-value-32")
        hub.create_tenant("Acme")
        with self.assertRaises(GatewayStartupError):
            ClearingGateway(hub=hub, production=True)


if __name__ == "__main__":
    unittest.main()
