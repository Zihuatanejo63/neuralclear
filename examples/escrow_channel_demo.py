"""Run both escrow branches with fake Stripe HTTP; no keys or network required.

python examples/escrow_channel_demo.py --output /tmp/neuralclear-evidence
python -m neuralclear.verify /tmp/neuralclear-evidence/normal.receipt.json \
    /tmp/neuralclear-evidence/normal.chain.json --algorithm Ed25519 \
    --key-id clearing --key-file /tmp/neuralclear-evidence/public.key
"""

from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from io import BytesIO
import json
from urllib.parse import parse_qs

from neuralclear.clearing import ClearingLedger
from neuralclear.ed25519 import public_key
from neuralclear.mandates import issue_mandate
from neuralclear.sdk import NeuralClearSDK
from neuralclear.stripe_channel import Funding, StripeChannel, StripeHTTP
from neuralclear.verify import verify
from neuralclear.wire import PROFILE

SEED = bytes(range(32))  # Public test seed, never a deployment key.
PUBLIC = public_key(SEED)
OWNER_KEYS = {"owner": ("buyer", "Ed25519", PUBLIC)}


class FakeStripeHTTP:
    """urllib opener stub: deterministic successful payment and bank payout."""

    def __init__(self, payout_status="paid"):
        self.objects, self.requests, self.idempotency = {}, [], {}
        self.payout_status = payout_status

    def __call__(self, request, timeout):
        self.requests.append(request)
        path = request.full_url.split("/v1/")[1]
        if request.method == "GET":
            response = self.objects[path.split("/")[1]]
        else:
            identity = (path, request.get_header("Idempotency-key"))
            if identity in self.idempotency:
                return BytesIO(json.dumps(self.idempotency[identity]).encode())
            fields = {k: v[0] for k, v in parse_qs(request.data.decode()).items()}
            prefix = {"payment_intents": "pi", "transfers": "tr", "payouts": "po"}[path]
            response = {
                "id": prefix + "_" + str(len(self.objects) + 1),
                "amount": int(fields["amount"]),
                "currency": fields["currency"],
                "metadata": {k[9:-1]: v for k, v in fields.items() if k.startswith("metadata[")},
                "status": "succeeded" if path == "payment_intents" else "paid",
            }
            if path == "payment_intents":
                response["amount_received"] = response["amount"]
            if path == "transfers":
                response["destination"] = fields["destination"]
            if path == "payouts":
                response["status"] = self.payout_status
            self.objects[response["id"]] = response
            self.idempotency[identity] = response
        return BytesIO(json.dumps(response).encode())


def run_branch(dispute=False, *, journal_path=None, checkpoint=None, payout_status="paid"):
    ledger = ClearingLedger(
        provider_accounts={"provider": "acct_provider"},
        mandate_keys=OWNER_KEYS,
        clock=lambda: 100,
        journal_path=journal_path,
        checkpoint=checkpoint,
    )
    ledger.open_account("buyer")
    ledger.open_account("provider")
    workflow = NeuralClearSDK(None, ledger, profile=PROFILE).escrow()
    mandate = issue_mandate(
        dict(
            mandate_id="mandate",
            owner="buyer",
            agent="research",
            currency="usd",
            allowed_capabilities=["summarize"],
            max_per_task=100,
            max_daily=100,
            max_total=100,
            valid_until=2000000000,
            requires_human_approval_above=100,
        ),
        SEED,
        "owner",
        "Ed25519",
    )
    tx = "disputed" if dispute else "normal"
    workflow.prepare(
        dict(transaction_id=tx, buyer="buyer", provider="provider", amount=50, fee=5),
        mandate,
        "research",
        "summarize",
    )
    fake = FakeStripeHTTP(payout_status)
    channel = StripeChannel(ledger, StripeHTTP("sk_test_fake", opener=fake))
    funding = Funding("buyer", tx, 55, "usd")
    intent = channel.create_deposit(funding, idempotency_key="deposit")
    channel.confirm_deposit(intent["id"], funding, idempotency_key="deposit")
    channel.confirm_deposit(intent["id"], funding, idempotency_key="deposit")
    funded = ledger.snapshot()
    result = workflow.execute(
        tx,
        {"summary": "Metered service result"},
        50,
        provider_key=SEED,
        provider_key_id="provider",
        provider_keys={"provider": ("Ed25519", PUBLIC)},
        dispute=dispute,
        award=20 if dispute else 50,
        fee=2 if dispute else 5,
    )
    settled = ledger.snapshot()
    payout = channel.payout(tx, idempotency_key="payout")
    receipt = ledger.receipt(tx, key=SEED, key_id="clearing", algorithm="Ed25519")
    chain = ledger.chain(tx)
    verify(receipt, chain, {"clearing": ("Ed25519", PUBLIC)})
    return dict(
        ledger=ledger,
        channel=channel,
        fake=fake,
        funded=funded,
        settled=settled,
        payout=payout,
        receipt=receipt,
        chain=chain,
        result=result,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    for disputed in (False, True):
        result = run_branch(disputed)
        name = "disputed" if disputed else "normal"
        if args.output:
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / (name + ".receipt.json")).write_text(
                json.dumps(result["receipt"], indent=2)
            )
            (args.output / (name + ".chain.json")).write_text(json.dumps(result["chain"], indent=2))
            (args.output / "public.key").write_bytes(PUBLIC)
        print(
            json.dumps(
                {
                    "branch": name,
                    "verified": True,
                    "amount": result["receipt"]["amount"],
                    "refund": result["receipt"]["refund"],
                    "payout": result["payout"]["status"],
                    "snapshot": result["ledger"].snapshot(),
                }
            )
        )
        result["ledger"].close()


if __name__ == "__main__":
    main()
