from unittest.mock import patch

from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
from modules.oom_sakkie.sam_payment_owner_runtime import (
    ACTION_KIND, MISSION_ID, execute_claimed_sale_payment, present_sale_payment_preview,
)


PREVIEW = {"version": "sale_payment_preview_v1", "sale_id": "SALE-AUCT",
    "transaction_label": "Livestock — Auction", "sale_channel": "Auction",
    "sale_status": "Completed", "received_amount": "4470.51",
    "amount_due": "4470.51", "payment_method": "EFT",
    "payment_date": "2026-08-11"}

IDENTITY = lambda sale_id: ({"sales_transaction": {"destination": "BKB",
    "external_reference": "S-EE02-2710", "sale_channel": "Auction",
    "sale_status": "Completed"}}, 200)


def test_deployed_runtime_delivers_one_provider_bound_preview_and_replay_sends_zero():
    deliveries = []
    def previewer(sale_id, payload, **kwargs):
        return {"success": True, "status": "payment_state_preview_ready",
            "preview": PREVIEW, "preview_digest": "a" * 64,
            "writes_to_supabase": False}, 200
    def deliverer(parsed, result, **kwargs):
        deliveries.append((parsed, result, kwargs))
        return {"success": True, "status": "family_message_delivered",
            "telegram_message_id": "9001", "telegram_sends": 1,
            "provider_delivery_confirmed": True}
    claim = {"callback_token": "opaque", "preview_digest": "b" * 64}
    with patch("modules.oom_sakkie.sam_payment_owner_runtime.create_claim", return_value=claim), patch(
            "modules.oom_sakkie.sam_payment_owner_runtime.bind_claim_card", return_value=True):
        result, status = present_sale_payment_preview({"sale_id": "SALE-AUCT",
            "counterparty": "BKB", "invoice_reference": "S-EE02-2710",
            "received_amount": "4470.51", "payment_date": "2026-08-11"},
            environ={"OOM_SAKKIE_DAILY_MANAGER_OWNER_USER_ID": "77"},
            previewer=previewer,
            transaction_reader=IDENTITY,
            deliverer=deliverer)
    assert status == 200 and result["provider_delivery_confirmed"] is True
    assert result["provider_message_id"] == "9001"
    assert len(deliveries) == 1
    buttons = deliveries[0][1]["reply_markup"]["inline_keyboard"][0]
    assert [button["text"] for button in buttons] == ["Confirm", "Cancel"]


def test_existing_bound_claim_returns_provider_card_without_delivery():
    claim = {"callback_token": "opaque", "preview_digest": "b" * 64,
        "preview_card_message_id": "9001"}
    with patch("modules.oom_sakkie.sam_payment_owner_runtime.create_claim", return_value=claim):
        result, status = present_sale_payment_preview({"sale_id": "SALE-AUCT",
            "counterparty": "BKB", "invoice_reference": "S-EE02-2710",
            "received_amount": "4470.51", "payment_date": "2026-08-11"},
            environ={"OOM_SAKKIE_DAILY_MANAGER_OWNER_USER_ID": "77"},
            previewer=lambda *a, **k: ({"success": True,
                "status": "payment_state_preview_ready", "preview": PREVIEW,
                "preview_digest": "a" * 64, "writes_to_supabase": False}, 200),
            transaction_reader=IDENTITY,
            deliverer=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not send")))
    assert status == 200 and result["provider_message_id"] == "9001"
    assert result["delivery"]["telegram_sends"] == 0


def test_preview_requires_nonempty_canonical_transaction_identity():
    result, status = present_sale_payment_preview({"sale_id": "SALE-AUCT",
        "received_amount": "4470.51", "payment_date": "2026-08-11"},
        environ={"OOM_SAKKIE_DAILY_MANAGER_OWNER_USER_ID": "77"},
        transaction_reader=lambda sale_id: ({"sales_transaction": {}}, 200),
        deliverer=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not send")))
    assert status == 400 and result["status"] == "sale_payment_transaction_identity_required"


def test_claim_execution_rechecks_exact_preview_and_uses_only_canonical_writer():
    bound = {"contract_version": "sam_sale_payment_telegram_preview_v1",
        "mission_id": MISSION_ID, "sale_id": "SALE-AUCT", "payment_status": "Paid",
        "received_amount": "4470.51", "amount_due": "4470.51",
        "payment_method": "EFT", "payment_date": "2026-08-11",
        "sale_status": "Completed", "sale_channel": "Auction",
        "transaction_label": "Livestock — Auction", "payment_preview_digest": "a" * 64,
        "counterparty": "BKB", "invoice_reference": "S-EE02-2710",
        "actor_id": "telegram-owner:opaque"}
    claim = {"preview_payload": bound,
        "preview_digest": canonical_preview_digest(ACTION_KIND, bound)}
    writes = []
    def previewer(*args, **kwargs):
        return {"success": True, "status": "payment_state_preview_ready",
            "preview_digest": "a" * 64}, 200
    def recorder(sale_id, payload, **kwargs):
        writes.append((sale_id, payload, kwargs))
        return {"success": True, "status": "payment_state_recorded",
            "received_amount": "4470.51", "payment_method": "EFT",
            "payment_date": "2026-08-11", "auction_completed": True,
            "settlement_received": True, "fully_reconciled": True}, 200
    result, status = execute_claimed_sale_payment(claim, previewer=previewer,
        recorder=recorder, transaction_reader=IDENTITY)
    assert status == 200 and len(writes) == 1
    assert writes[0][1]["confirmed_preview_digest"] == "a" * 64
    assert result["answer"] == (
        "Auction completed. Settlement received: R4470.51 by EFT on 2026-08-11. Fully reconciled.")


def test_changed_canonical_state_requires_repreview_and_writes_zero():
    bound = {"contract_version": "sam_sale_payment_telegram_preview_v1",
        "sale_id": "SALE-AUCT", "payment_status": "Paid", "received_amount": "4470.51",
        "payment_method": "EFT", "payment_date": "2026-08-11",
        "payment_preview_digest": "a" * 64, "actor_id": "telegram-owner:opaque",
        "counterparty": "BKB", "invoice_reference": "S-EE02-2710",
        "sale_channel": "Auction", "sale_status": "Completed"}
    claim = {"preview_payload": bound,
        "preview_digest": canonical_preview_digest(ACTION_KIND, bound)}
    result, status = execute_claimed_sale_payment(claim,
        previewer=lambda *a, **k: ({"success": True, "status": "payment_state_preview_ready",
            "preview_digest": "c" * 64}, 200),
        recorder=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not write")),
        transaction_reader=IDENTITY)
    assert status == 409 and result["status"] == "sale_payment_repreview_required"


def test_matching_recorded_state_uses_writer_replay_check_without_second_write():
    bound = {"contract_version": "sam_sale_payment_telegram_preview_v1",
        "sale_id": "SALE-AUCT", "payment_status": "Paid", "received_amount": "4470.51",
        "payment_method": "EFT", "payment_date": "2026-08-11",
        "payment_preview_digest": "a" * 64, "actor_id": "telegram-owner:opaque",
        "counterparty": "BKB", "invoice_reference": "S-EE02-2710",
        "sale_channel": "Auction", "sale_status": "Completed"}
    claim = {"preview_payload": bound,
        "preview_digest": canonical_preview_digest(ACTION_KIND, bound)}
    calls = []
    def recorder(*args, **kwargs):
        calls.append((args, kwargs))
        return {"success": True, "status": "payment_state_replay_noop",
            "received_amount": "4470.51", "payment_method": "EFT",
            "payment_date": "2026-08-11"}, 200
    result, status = execute_claimed_sale_payment(claim,
        previewer=lambda *a, **k: ({"success": True,
            "status": "payment_state_already_recorded", "preview_digest": "a" * 64}, 200),
        recorder=recorder, transaction_reader=IDENTITY)
    assert status == 200 and result["status"] == "payment_state_replay_noop"
    assert len(calls) == 1
