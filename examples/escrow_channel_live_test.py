"""Real Stripe TEST API only. No fake fallback and no live credentials accepted.

Start with --preflight. A run directory is create-once: do not rerun a payment
after an uncertain outcome; reconcile its saved Stripe IDs and journal instead.
Secrets/signing seeds stay in a private directory outside the repository.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

import argparse
from datetime import datetime, timezone
import json
import os
import re
import secrets
import shlex
import ssl
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPSHandler, HTTPRedirectHandler
from uuid import uuid4

from neuralclear.clearing import ClearingLedger
from neuralclear.core import ProtocolError
from neuralclear.ed25519 import public_key
from neuralclear.journal import FileCheckpoint
from neuralclear.mandates import issue_mandate
from neuralclear.sdk import NeuralClearSDK
from neuralclear.stripe_channel import Funding, NetSettlement, StripeChannel, StripeHTTP
from neuralclear.wire import PROFILE


def read_test_key(path):
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            parts = shlex.split(line, comments=True)
        except ValueError:
            raise ProtocolError("invalid credential file syntax") from None
        if parts and parts[0] == "export":
            parts = parts[1:]
        name, separator, value = " ".join(parts).partition("=")
        if separator:
            values[name.strip()] = value.strip()
    key = values.get("STRIPE_SECRET_KEY", "")
    if not re.fullmatch(r"sk_test_[A-Za-z0-9]+", key):
        raise ProtocolError("a test-mode secret key is required")
    return key


def redact(value, secret):
    text = str(value).replace(secret, "[REDACTED]")
    text = re.sub(r"\b(?:sk|rk|pk)_(?:test|live)_[^\s\"'<>]+", "[REDACTED]", text)
    return re.sub(r"\bpi_[A-Za-z0-9]+_secret_[A-Za-z0-9]+", "[REDACTED]", text)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProtocolError("Stripe redirects are not allowed")


class ObservedStripeHTTP(StripeHTTP):
    """Real urllib transport; records only allowlisted non-secret evidence."""

    def __init__(self, secret, evidence):
        if not re.fullmatch(r"sk_test_[A-Za-z0-9]+", secret):
            raise ProtocolError("test credential required")
        context = ssl.create_default_context(
            cafile="/etc/ssl/cert.pem" if Path("/etc/ssl/cert.pem").exists() else None
        )
        self.transport = build_opener(HTTPSHandler(context=context), NoRedirect())
        self.evidence = evidence
        super().__init__(secret, opener=self._open, timeout=30)

    def _open(self, request, timeout):
        try:
            return self.transport.open(request, timeout=timeout)
        except HTTPError as exc:
            try:
                body = json.loads(exc.read())
                error = body.get("error", {})
                detail = {
                    name: redact(error[name], self.secret_key)
                    for name in ("type", "code", "param", "message")
                    if name in error
                }
            except (ValueError, TypeError):
                detail = {"message": "non-JSON error body omitted"}
            self.evidence["requests"].append(
                {
                    "method": request.method,
                    "path": request.full_url.split("/v1/", 1)[1],
                    "http_status": exc.code,
                    "error": detail,
                    "request_id": exc.headers.get("Request-Id"),
                }
            )
            raise

    def request(self, method, path, *, data=None, key=None, account=None):
        if not re.fullmatch(r"[A-Za-z0-9_/?=&.-]+", path) or ".." in path:
            raise ProtocolError("invalid Stripe path")
        result = super().request(method, path, data=data, key=key, account=account)
        if result.get("livemode") is True:
            raise ProtocolError("live-mode object rejected")
        if path.split("/", 1)[0] in {"payment_intents", "transfers", "payouts"}:
            if result.get("livemode") is not False:
                raise ProtocolError("test-mode object marker missing")
        safe = {
            name: result[name]
            for name in (
                "id",
                "object",
                "status",
                "livemode",
                "amount",
                "amount_received",
                "currency",
                "latest_charge",
                "charges_enabled",
                "payouts_enabled",
            )
            if name in result
        }
        self.evidence["requests"].append(
            dict(method=method, path=path, account=account, result=safe)
        )
        return result


def preflight(http, evidence):
    account = http.request("GET", "account")
    evidence["platform_account"] = account["id"]
    balance = http.request("GET", "balance")
    if balance.get("livemode") is not False:
        raise ProtocolError("test balance required")
    evidence["balance_before"] = {
        name: [{"amount": v["amount"], "currency": v["currency"]} for v in balance.get(name, [])]
        for name in ("available", "pending")
    }
    try:
        accounts = http.request("GET", "accounts?limit=100")
        evidence["connected_accounts"] = [
            {
                "id": a["id"],
                "charges_enabled": a.get("charges_enabled"),
                "payouts_enabled": a.get("payouts_enabled"),
            }
            for a in accounts.get("data", [])
        ]
        evidence["accounts_has_more"] = accounts.get("has_more", False)
    except ProtocolError:
        evidence["connected_accounts"] = []
        evidence["connect_preflight"] = "blocked; see sanitized Stripe error"


def private_write(path, content):
    with open(path, "xb") as stream:
        os.chmod(path, 0o600)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def run(http, evidence, directory, connected_account=None):
    directory = Path(directory).resolve()
    if directory == ROOT or ROOT in directory.parents:
        raise ProtocolError("private run directory must be outside repository")
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    ledger = None
    tx = "nc_stripe_test_" + uuid4().hex
    evidence.update(
        transaction_id=tx,
        currency="usd",
        deposit_amount=50,
        service_amount=50,
        fee=0,
        run_directory=str(directory),
        steps=[],
    )

    def step(name, **details):
        evidence["steps"].append(dict(step=name, **details))
        (directory / "evidence.json").write_text(json.dumps(evidence, indent=2))

    try:
        preflight(http, evidence)
        destination = None
        if connected_account:
            if not re.fullmatch(r"acct_[A-Za-z0-9]+", connected_account):
                raise ProtocolError("invalid connected account id")
            known = {a["id"] for a in evidence["connected_accounts"]}
            if connected_account not in known or connected_account == evidence["platform_account"]:
                raise ProtocolError("destination is not an authorized listed connected account")
            destination = connected_account
        step("preflight", status="ok", connected_account=destination)
        owner, provider, clearing = (secrets.token_bytes(32) for _ in range(3))
        for name, seed in (("owner", owner), ("provider", provider), ("clearing", clearing)):
            private_write(directory / (name + ".seed"), seed)
        private_write(directory / "public.key", public_key(clearing))
        checkpoint = FileCheckpoint(directory / "checkpoint.json", initialize=True)
        ledger = ClearingLedger(
            provider_accounts={"provider": destination} if destination else {},
            mandate_keys={"owner": ("buyer", "Ed25519", public_key(owner))},
            journal_path=directory / "ledger.jsonl",
            checkpoint=checkpoint,
        )
        ledger.open_account("buyer")
        ledger.open_account("provider")
        workflow = NeuralClearSDK(None, ledger, profile=PROFILE).escrow()
        mandate = issue_mandate(
            dict(
                mandate_id=tx + "_mandate",
                owner="buyer",
                agent="research",
                currency="usd",
                allowed_capabilities=["summarize"],
                max_per_task=50,
                max_daily=50,
                max_total=50,
                valid_until=int(time.time()) + 3600,
                requires_human_approval_above=50,
            ),
            owner,
            "owner",
            "Ed25519",
        )
        workflow.prepare(
            dict(transaction_id=tx, buyer="buyer", provider="provider", amount=50, fee=0),
            mandate,
            "research",
            "summarize",
        )
        step("mandate", status="validated", budget=50)
        channel = StripeChannel(ledger, http)
        funding = Funding("buyer", tx, 50, "usd")
        intent = channel.create_deposit(funding, idempotency_key=tx + "_deposit")
        pi = intent["id"]
        step("create_payment_intent", status=intent["status"], object_id=pi)
        confirmation = http.request(
            "POST",
            "payment_intents/" + pi + "/confirm",
            data={"payment_method": "pm_card_visa", "return_url": "https://neuralclear.org/"},
            key=tx + "_confirm",
        )
        step("confirm_payment_intent", status=confirmation["status"], object_id=pi)
        channel.confirm_deposit(pi, funding, idempotency_key=tx + "_deposit")
        channel.confirm_deposit(pi, funding, idempotency_key=tx + "_deposit")
        step("escrow", status="funded", snapshot=ledger.snapshot())
        outcome = workflow.execute(
            tx,
            {"summary": "NeuralClear real Stripe test-mode service."},
            50,
            provider_key=provider,
            provider_key_id="provider",
            provider_keys={"provider": ("Ed25519", public_key(provider))},
            fee=0,
        )
        step(
            "meter_and_net_settlement",
            status=outcome["transaction"]["state"],
            snapshot=ledger.snapshot(),
        )
        if destination:
            try:
                payout = channel.payout(tx, idempotency_key=tx + "_payout")
                step("payout", status=payout["status"], object_id=payout["id"])
                row = ledger.payout_record(tx)
                latest = channel.reconcile_payout(
                    NetSettlement(**row["net"]), row["transfer"], payout["id"]
                )
                step("payout_retrieved", status=latest["status"], object_id=latest["id"])
            except ProtocolError as exc:
                step("payout", status="blocked", reason=redact(exc, http.secret_key))
        else:
            step(
                "payout",
                status="not_attempted",
                reason="No explicitly selected authorized Connect destination; no transfer or payout created.",
            )
        receipt = ledger.receipt(tx, key=clearing, key_id="clearing", algorithm="Ed25519")
        for name, body in (
            ("receipt", receipt),
            ("chain", ledger.chain(tx)),
            ("signed_result", outcome),
        ):
            private_write(directory / (name + ".json"), json.dumps(body, indent=2).encode())
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "neuralclear.verify",
                str(directory / "receipt.json"),
                str(directory / "chain.json"),
                "--algorithm",
                "Ed25519",
                "--key-id",
                "clearing",
                "--key-file",
                str(directory / "public.key"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        step(
            "independent_verification",
            status="VALID" if process.returncode == 0 else "INVALID",
            exit_code=process.returncode,
        )
        evidence["final_snapshot"] = ledger.snapshot()
    except (ProtocolError, OSError, ValueError) as exc:
        step("run_blocked", status="blocked", reason=redact(exc, http.secret_key))
    finally:
        if ledger is not None:
            ledger.close()
        verified = any(
            s["step"] == "independent_verification" and s["status"] == "VALID"
            for s in evidence["steps"]
        )
        paid = any(
            s["step"] in {"payout", "payout_retrieved"} and s["status"] == "paid"
            for s in evidence["steps"]
        )
        evidence["outcome"] = (
            "complete" if verified and paid else "partial" if verified else "blocked"
        )
        (directory / "evidence.json").write_text(json.dumps(evidence, indent=2))
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path.home() / ".config/neuralclear/stripe.env"
    )
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--connected-account")
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    evidence = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "mode": "real Stripe test API",
        "requests": [],
    }
    try:
        secret = read_test_key(args.config)
        http = ObservedStripeHTTP(secret, evidence)
        if args.preflight:
            preflight(http, evidence)
        else:
            if args.run_dir is None:
                raise ProtocolError("explicit --run-dir required")
            run(http, evidence, args.run_dir, args.connected_account)
    except (ProtocolError, OSError, ValueError):
        # Never print arbitrary exceptions from credential loading or transport.
        evidence["blocked"] = (
            "Preflight/configuration failed; see sanitized request evidence. No automatic retry."
        )
    print(json.dumps(evidence, indent=2))
    if evidence.get("blocked"):
        return 1
    return 0 if args.preflight or evidence.get("outcome") == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
