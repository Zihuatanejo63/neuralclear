"""Tests: signed result proofs + the clearing gateway over real HTTP."""

from __future__ import annotations

import json
import unittest
import urllib.request

from neuralclear.clearing import ClearingService, EscrowLedger, FeePolicy, FeeSchedule
from neuralclear.core import SettlementCredit
from neuralclear.gateway import ClearingGateway
from neuralclear.httpwire import ProviderHTTPServer
from neuralclear.proofs import ProofKeyring, SignedResultProof
from neuralclear.provider import ProviderAgent


def http_json(method: str, url: str, body: dict | None = None, api_key: str | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-NeuralClear-Api-Key"] = api_key
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return {"_status": exc.code, **json.loads(exc.read().decode())}


class SignedProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.keys = ProofKeyring()
        self.keys.register("agent.w", "provider_secret")

    def test_sign_verify_and_output_binding(self) -> None:
        proof = SignedResultProof.sign(
            self.keys.signer_for("agent.w"), "agent.w", "cap.x", {"answer": 42}
        )
        self.assertTrue(proof.verify_with(self.keys.verifier_for("agent.w")))
        self.assertTrue(proof.matches_output({"answer": 42}))
        self.assertFalse(proof.matches_output({"answer": 43}))

    def test_wrong_key_and_tampered_fields_fail(self) -> None:
        self.keys.register("agent.evil", "other_secret")
        proof = SignedResultProof.sign(
            self.keys.signer_for("agent.w"), "agent.w", "cap.x", {"answer": 42}
        )
        self.assertFalse(proof.verify_with(self.keys.verifier_for("agent.evil")))
        proof.capability = "cap.y"  # tamper
        self.assertFalse(proof.verify_with(self.keys.verifier_for("agent.w")))

    def test_unbound_proof_never_settles(self) -> None:
        proof = SignedResultProof.sign(
            self.keys.signer_for("agent.w"), "agent.w", "cap.x", {}
        )
        self.assertFalse(proof.verify())  # no verifier bound -> refuse
        proof.bind_verifier(self.keys.verifier_for("agent.w"))
        self.assertTrue(proof.verify())


class GatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        provider = ProviderAgent("agent.echo")

        @provider.capability("echo.text", price=10, resource_estimate=1, resource_unit="calls")
        def echo(payload: object) -> object:
            return {"echo": payload}

        cls.provider_server = ProviderHTTPServer(provider).start()

        ledger = EscrowLedger()
        clearing = ClearingService(ledger=ledger, fees=FeeSchedule(FeePolicy(minimum=1)))
        cls.gateway = ClearingGateway(clearing=clearing, api_key="k_test").start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.gateway.stop()
        cls.provider_server.stop()

    def test_01_account_and_full_clear_over_http(self) -> None:
        base = self.gateway.url
        http_json("POST", f"{base}/v1/accounts", {"account": "owner.acme", "deposit": 200}, "k_test")
        http_json("POST", f"{base}/v1/accounts", {"account": "agent.echo", "deposit": 0}, "k_test")
        receipt = http_json(
            "POST",
            f"{base}/v1/clear",
            {
                "buyer_owner": "owner.acme",
                "provider_url": self.provider_server.url,
                "capability": "echo.text",
                "payload": {"msg": "hi"},
            },
            "k_test",
        )
        self.assertEqual(receipt["amount"], 10)
        self.assertEqual(receipt["fee"], 1)
        ledger = http_json("GET", f"{base}/v1/ledger")
        self.assertEqual(ledger["balances"]["agent.echo"], 10)
        self.assertEqual(ledger["balances"]["owner.acme"], 189)
        fetched = http_json("GET", f"{base}/v1/receipts/{receipt['receipt_id']}")
        self.assertEqual(fetched["receipt_id"], receipt["receipt_id"])

    def test_02_netting_channel_over_http(self) -> None:
        base = self.gateway.url
        channel = http_json(
            "POST", f"{base}/v1/channels",
            {"buyer": "owner.acme", "provider": "agent.echo", "deposit": 31},
            "k_test",
        )
        for index in range(20):
            record = http_json(
                "POST",
                f"{base}/v1/channels/{channel['channel_id']}/meter",
                {"capability": "echo.text", "amount": 1, "payload_hash": f"sha256:{index}"},
                "k_test",
            )
            self.assertEqual(record["sequence"], index)
        receipt = http_json(
            "POST", f"{base}/v1/channels/{channel['channel_id']}/settle", {}, "k_test"
        )
        self.assertEqual(receipt["tasks_metered"], 20)
        self.assertEqual(receipt["net_to_provider"], 20)

    def test_03_api_key_required_for_writes(self) -> None:
        response = http_json(
            "POST", f"{self.gateway.url}/v1/accounts", {"account": "x", "deposit": 1}
        )
        self.assertEqual(response.get("_status"), 401)

    def test_04_unknown_endpoint_is_protocol_error(self) -> None:
        response = http_json("POST", f"{self.gateway.url}/v1/nope", {}, "k_test")
        self.assertEqual(response.get("_status"), 400)


if __name__ == "__main__":
    unittest.main()
