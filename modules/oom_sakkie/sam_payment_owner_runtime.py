"""Provider-bound Telegram preview for the canonical sale-payment action."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from typing import Mapping

from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.protected_action_claims import (
    CALLBACK_PREFIX, bind_claim_card, canonical_preview_digest, contain_unbound_preview_claim,
    create_claim,
)
from modules.sales.sales_payment_receipt import preview_sale_payment_state, record_sale_payment_state
from modules.sales.sales_transaction_read import get_sales_transaction

ACTION_KIND = "sam_sale_payment"
MISSION_ID = "SMQ-20260813-05"
OWNER_ENV = "OOM_SAKKIE_DAILY_MANAGER_OWNER_USER_ID"


def present_sale_payment_preview(payload=None, *, environ=None, connect_factory=None,
                                 previewer=preview_sale_payment_state,
                                 transaction_reader=get_sales_transaction,
                                 deliverer=deliver_family_result):
    source = environ if environ is not None else os.environ
    requested = dict(payload or {})
    owner = str(source.get(OWNER_ENV) or "").strip()
    sale_id = str(requested.get("sale_id") or "").strip()
    payment_date = str(requested.get("payment_date") or "").strip()
    if not owner or not sale_id or not payment_date:
        return _safe("sale_payment_preview_binding_required"), 400
    transaction_result, transaction_status = transaction_reader(sale_id)
    transaction = transaction_result.get("sales_transaction") if isinstance(
        transaction_result.get("sales_transaction"), Mapping) else {}
    expected_invoice = str(requested.get("invoice_reference") or "").strip()
    expected_counterparty = str(requested.get("counterparty") or "").strip()
    if not expected_invoice or not expected_counterparty:
        return _safe("sale_payment_transaction_identity_required"), 400
    counterparty = str(transaction.get("buyer_name") or transaction.get("destination") or "").strip()
    if (transaction_status != 200 or transaction.get("external_reference") != expected_invoice
            or counterparty != expected_counterparty):
        return _safe("sale_payment_transaction_identity_mismatch"), 409
    actor_id = "telegram-owner:" + sha256(owner.encode()).hexdigest()
    proposed = {"payment_status": "Paid", "received_amount": requested.get("received_amount"),
        "payment_method": "EFT", "payment_date": payment_date}
    preview_result, status = previewer(sale_id, proposed, actor_id=actor_id)
    preview = preview_result.get("preview") if isinstance(preview_result.get("preview"), Mapping) else {}
    if status != 200 or preview_result.get("status") != "payment_state_preview_ready":
        return {**_safe(str(preview_result.get("status") or "sale_payment_preview_failed")),
            "canonical": preview_result}, status
    if (preview.get("transaction_label") != "Livestock — Auction"
            or str(preview.get("received_amount")) != str(preview.get("amount_due"))
            or preview.get("payment_method") != "EFT"
            or preview.get("payment_date") != payment_date):
        return _safe("sale_payment_preview_canonical_mismatch"), 409
    payment_digest = str(preview_result.get("preview_digest") or "")
    bound = {"contract_version": "sam_sale_payment_telegram_preview_v1",
        "mission_id": MISSION_ID, "sale_id": sale_id,
        "payment_status": "Paid", "received_amount": str(preview["received_amount"]),
        "amount_due": str(preview["amount_due"]), "payment_method": "EFT",
        "payment_date": payment_date, "sale_status": str(preview.get("sale_status") or ""),
        "sale_channel": str(preview.get("sale_channel") or ""),
        "transaction_label": str(preview.get("transaction_label") or ""),
        "counterparty": counterparty, "invoice_reference": expected_invoice,
        "payment_preview_digest": payment_digest, "actor_id": actor_id}
    evidence_generation = sha256(json.dumps(bound, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    fact_identity = "owner-retained-payment-fact:" + evidence_generation
    claim = create_claim(action_kind=ACTION_KIND, owner_user_id=owner,
        private_chat_id=owner, mission_id=MISSION_ID, provider_message_id=fact_identity,
        evidence_generation=evidence_generation, preview_payload=bound,
        ttl_minutes=30, connect_factory=connect_factory, supersede_active=False)
    token = str(claim["callback_token"])
    answer = ("<b>SAM — PROTECTED SETTLEMENT PREVIEW</b>\n\n"
        "<b>Livestock — Auction</b>\n"
        f"• {counterparty}\n• Invoice {expected_invoice}\n• Sale {sale_id}\n"
        f"• Receipt R{bound['received_amount']}\n"
        f"• Cumulative receipt R{bound['received_amount']} of R{bound['amount_due']}\n"
        f"• EFT\n• Bank receipt date {payment_date}\n\n"
        "Auction completed. Settlement is not recorded yet. Confirm records this exact preview once; Cancel records nothing.")
    result = {"handled": True, "success": True, "status": "sale_payment_preview_ready",
        "answer": answer, "mission_id": MISSION_ID,
        "card_mission_id": MISSION_ID + ":PAYMENT:" + payment_digest[:24].upper(),
        "callback_token": token, "preview_digest": str(claim["preview_digest"]),
        "action_kind": str(claim.get("action_kind") or ACTION_KIND),
        "reply_markup": _payment_buttons(token), "requires_visible_notification": True,
        "writes_farm_data": False, "writes_to_supabase": False}
    existing_card_id = str(claim.get("preview_card_message_id") or "")
    if existing_card_id:
        return {**result, "answer": "", "provider_message_id": existing_card_id,
            "provider_delivery_confirmed": True,
            "delivery": {"success": True, "status": "family_message_replayed_noop",
                "telegram_message_id": existing_card_id,
                "telegram_sends": 0, "telegram_edits": 0}}, 200
    parsed = {"telegram_user_id": owner, "telegram_chat_id": owner,
        "telegram_chat_type": "private", "provider_message_id": fact_identity,
        "provider_timestamp": payment_date + "T12:00:00+02:00", "text": "retained owner payment fact"}
    delivery = deliverer(parsed, result, specialist="SAM", mission_id=MISSION_ID,
        card_mission_id=result["card_mission_id"])
    message_id = str(delivery.get("telegram_message_id") or "")
    if not delivery.get("success") or not message_id or not bind_claim_card(
            token, message_id, connect_factory=connect_factory):
        contain_unbound_preview_claim(token, {"status": "sale_payment_preview_delivery_contained"},
            connect_factory=connect_factory)
        return {**_safe("sale_payment_preview_delivery_contained"), "delivery": delivery}, 503
    return {**result, "answer": "", "delivery": delivery,
        "provider_message_id": message_id, "provider_delivery_confirmed": True}, 200


def execute_claimed_sale_payment(claim, *, connect_factory=None,
                                 previewer=preview_sale_payment_state,
                                 recorder=record_sale_payment_state,
                                 transaction_reader=get_sales_transaction):
    bound = claim.get("preview_payload") if isinstance(claim.get("preview_payload"), Mapping) else {}
    if (bound.get("contract_version") != "sam_sale_payment_telegram_preview_v1"
            or canonical_preview_digest(ACTION_KIND, bound) != claim.get("preview_digest")):
        return _safe("sale_payment_claim_binding_mismatch"), 409
    proposed = {key: bound.get(key) for key in
        ("payment_status", "received_amount", "payment_method", "payment_date")}
    identity_result, identity_status = transaction_reader(str(bound.get("sale_id") or ""))
    transaction = identity_result.get("sales_transaction") if isinstance(
        identity_result.get("sales_transaction"), Mapping) else {}
    counterparty = str(transaction.get("buyer_name") or transaction.get("destination") or "").strip()
    if (identity_status != 200 or counterparty != bound.get("counterparty")
            or transaction.get("external_reference") != bound.get("invoice_reference")
            or transaction.get("sale_channel") != bound.get("sale_channel")
            or transaction.get("sale_status") != bound.get("sale_status")):
        return _safe("sale_payment_transaction_identity_changed"), 409
    current, status = previewer(str(bound.get("sale_id") or ""), proposed,
        actor_id=str(bound.get("actor_id") or ""))
    current_status = current.get("status")
    if (status != 200 or current_status not in {
            "payment_state_preview_ready", "payment_state_already_recorded"}):
        return _safe("sale_payment_repreview_required"), 409
    if (current_status == "payment_state_preview_ready"
            and current.get("preview_digest") != bound.get("payment_preview_digest")):
        return _safe("sale_payment_repreview_required"), 409
    confirmed = {**proposed, "confirmed_preview_digest": bound["payment_preview_digest"]}
    confirmed.update({"expected_counterparty": bound["counterparty"],
        "expected_invoice_reference": bound["invoice_reference"]})
    result, status = recorder(str(bound["sale_id"]), confirmed,
        actor_id=str(bound["actor_id"]))
    if status != 200 or result.get("success") is not True:
        return {**_safe(str(result.get("status") or "sale_payment_record_failed")),
            "canonical": result}, status
    return {**result, "answer": (
        f"Auction completed. Settlement received: R{result['received_amount']} by "
        f"{result['payment_method']} on {result['payment_date']}. Fully reconciled."),
        "specialist": "SAM", "mission_id": MISSION_ID,
        "card_mission_id": MISSION_ID + ":PAYMENT:" + bound["payment_preview_digest"][:24].upper(),
        "reply_markup": {"inline_keyboard": []},
        "owner_visible_completion_policy": "verified_edit_or_new_message"}, status


def _safe(status):
    return {"handled": True, "success": False, "status": status,
        "writes_farm_data": False, "writes_to_supabase": False,
        "telegram_sends": 0, "telegram_edits": 0}


def _payment_buttons(token):
    return {"inline_keyboard": [[
        {"text": "Confirm", "callback_data": f"{CALLBACK_PREFIX}{token}:confirm"},
        {"text": "Cancel", "callback_data": f"{CALLBACK_PREFIX}{token}:cancel"},
    ]]}
