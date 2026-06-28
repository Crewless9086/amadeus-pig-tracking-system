from datetime import datetime, timezone

from modules.oom_sakkie.sales_campaign_store import (
    get_sales_lead_preorder_contract,
    get_sales_lead_pricing_estimate,
)
from modules.sales.meat_fulfillment import get_meat_fulfillment_timeline
from modules.sales.meat_match_engine import get_sales_lead_meat_match
from modules.sales.meat_ops import get_meat_ops_status
from modules.sales.meat_reconciliation import get_meat_reconciliation_status


REQUIRED_FACTS = ("product_type", "cut_set", "location", "timing", "delivery_or_collection")

FORBIDDEN_ACTIONS = [
    "send_customer_message",
    "create_whatsapp_send",
    "create_public_post",
    "record_deposit",
    "confirm_bank_payment",
    "reserve_carcass",
    "create_order",
    "promise_price",
    "promise_stock",
    "promise_slaughter",
    "promise_delivery",
    "approve_anything",
    "mutate_supabase_state",
]

ACTIVE_RESERVATION_STATUSES = {
    "half_reserved_pending_pair",
    "full_carcass_committed",
    "deposit_pending",
    "ready_for_slaughter_booking",
}


def get_sam_command_state(lead_id, database_url=None, beacon_provider=None):
    lead_id = _clean(lead_id, 100)
    if not lead_id:
        return {"ok": False, "success": False, "status": "lead_id_required"}, 400

    contract_result, contract_status = get_sales_lead_preorder_contract(lead_id, database_url=database_url)
    if contract_status == 404:
        return {
            "ok": False,
            "success": False,
            "status": "sales_lead_not_found",
            "lead_id": lead_id,
        }, 404
    if contract_status != 200:
        return {
            "ok": False,
            "success": False,
            "status": contract_result.get("status") or "command_state_primary_source_unavailable",
            "lead_id": lead_id,
            "source_refs": [_source_ref("contract", contract_status, contract_result)],
        }, contract_status

    sources = {"contract": contract_result}
    source_refs = [_source_ref("contract", contract_status, contract_result)]
    degraded_sources = []

    for key, reader in (
        ("pricing_estimate", lambda: get_sales_lead_pricing_estimate(lead_id, {}, database_url=database_url)),
        ("meat_match", lambda: get_sales_lead_meat_match(lead_id, {}, database_url=database_url)),
        ("meat_ops", lambda: get_meat_ops_status(lead_id, database_url=database_url)),
        ("fulfillment", lambda: get_meat_fulfillment_timeline(lead_id, database_url=database_url)),
        ("reconciliation", lambda: get_meat_reconciliation_status(lead_id, database_url=database_url)),
    ):
        result, status_code = _read_source(reader)
        sources[key] = result
        source_refs.append(_source_ref(key, status_code, result))
        if status_code >= 400:
            degraded_sources.append(_degraded_source(key, status_code, result))

    beacon_gate = _beacon_gate(beacon_provider)
    if beacon_gate.get("status") == "degraded":
        degraded_sources.append({"source": "beacon", "status_code": 503, "status": "beacon_unavailable"})
    source_refs.append({"source": "beacon", "status": beacon_gate.get("status", "not_needed")})

    lead = _lead_summary(contract_result)
    missing_facts = _missing_facts(contract_result)
    events = _events(contract_result)
    ops = sources.get("meat_ops") if isinstance(sources.get("meat_ops"), dict) else {}
    fulfillment_source = sources.get("fulfillment") if isinstance(sources.get("fulfillment"), dict) else {}
    reconciliation_source = sources.get("reconciliation") if isinstance(sources.get("reconciliation"), dict) else {}

    money_gate = _money_gate(contract_result, sources.get("pricing_estimate"), ops)
    butcher_gate = _butcher_gate(sources.get("meat_match"), ops)
    draft_reply = _draft_reply(events, lead)
    fulfillment = _fulfillment_gate(fulfillment_source)
    reconciliation = _reconciliation_gate(reconciliation_source)
    history = _history(events)
    next_action = _next_action(
        contract_result=contract_result,
        missing_facts=missing_facts,
        events=events,
        lead=lead,
        money_gate=money_gate,
        butcher_gate=butcher_gate,
        draft_reply=draft_reply,
        ops=ops,
        fulfillment=fulfillment,
        reconciliation=reconciliation,
    )
    gatekeeper = _gatekeeper(next_action)

    response = {
        "ok": True,
        "success": True,
        "status": "ok",
        "mode": "sam_command_state_read_only",
        "lead_id": lead_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_refs": source_refs,
        "lead": lead,
        "next_action": next_action,
        "missing_facts": missing_facts,
        "money_gate": money_gate,
        "butcher_gate": butcher_gate,
        "beacon_gate": beacon_gate,
        "gatekeeper": gatekeeper,
        "draft_reply": draft_reply,
        "ops_gate": _ops_gate(ops),
        "fulfillment": fulfillment,
        "reconciliation": reconciliation,
        "history": history,
        "degraded_sources": degraded_sources,
        "safe_actions": _safe_actions(next_action),
        "forbidden_actions": FORBIDDEN_ACTIONS,
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "creates_quote": False,
        "creates_order": False,
        "changes_stock": False,
        "reserves_stock": False,
        "posts_publicly": False,
        "writes_to_supabase": False,
    }
    return response, 200


def _read_source(reader):
    try:
        result, status_code = reader()
    except Exception as exc:
        return {"success": False, "status": "read_failed", "error_type": exc.__class__.__name__}, 503
    return result if isinstance(result, dict) else {}, int(status_code or 500)


def _lead_summary(contract_result):
    lead = contract_result.get("lead") if isinstance(contract_result.get("lead"), dict) else {}
    contract = contract_result.get("contract") if isinstance(contract_result.get("contract"), dict) else {}
    interest = lead.get("interest") if isinstance(lead.get("interest"), dict) else {}
    summary = contract.get("lead_summary") if isinstance(contract.get("lead_summary"), dict) else {}
    latest_event = lead.get("latest_event") if isinstance(lead.get("latest_event"), dict) else {}
    return {
        "contact_label": _first(lead.get("contact_label"), lead.get("lead_label"), summary.get("contact_label")),
        "status": _clean(lead.get("status"), 100),
        "stage": _first(latest_event.get("event_type"), contract.get("contract_status"), lead.get("status")),
        "interest": interest,
        "whatsapp_window_state": _window_state(lead.get("whatsapp_window_state")),
    }


def _missing_facts(contract_result):
    lead = contract_result.get("lead") if isinstance(contract_result.get("lead"), dict) else {}
    contract = contract_result.get("contract") if isinstance(contract_result.get("contract"), dict) else {}
    interest = lead.get("interest") if isinstance(lead.get("interest"), dict) else {}
    summary = contract.get("lead_summary") if isinstance(contract.get("lead_summary"), dict) else {}
    available = []
    missing = list(contract.get("missing_fields") or contract.get("missing_core_context") or [])
    if not missing:
        for field in REQUIRED_FACTS:
            value = _first(
                interest.get(field),
                summary.get(field),
                summary.get("product") if field == "product_type" else "",
            )
            if value:
                available.append(field)
            else:
                missing.append(field)
    else:
        available = [field for field in REQUIRED_FACTS if field not in set(missing)]
    return {
        "required": list(REQUIRED_FACTS),
        "available": available,
        "missing": _unique(missing),
    }


def _money_gate(contract_result, pricing, ops):
    contract = contract_result.get("contract") if isinstance(contract_result.get("contract"), dict) else {}
    pricing = pricing if isinstance(pricing, dict) else {}
    ops = ops if isinstance(ops, dict) else {}
    payment = ops.get("payment_gate") if isinstance(ops.get("payment_gate"), dict) else {}
    blocked = []
    if pricing.get("success") is False:
        return {
            "status": "degraded",
            "summary": "Pricing estimate is unavailable; owner money review cannot be trusted yet.",
            "blocked_reasons": [pricing.get("status") or "pricing_estimate_unavailable"],
        }
    if payment.get("pop_received_unverified") and not payment.get("deposit_confirmed_in_bank"):
        return {
            "status": "blocked",
            "summary": "POP is present but money is not confirmed in the bank.",
            "blocked_reasons": ["pop_received_unverified", "bank_confirmation_required"],
        }
    if payment.get("deposit_confirmed_in_bank"):
        return {"status": "ready", "summary": "Deposit is confirmed in bank.", "blocked_reasons": []}
    if contract.get("contract_status") == "owner_money_path_ready":
        return {"status": "ready", "summary": "Owner money path has been reviewed.", "blocked_reasons": []}
    blocked.extend(contract.get("missing_fields") or [])
    return {
        "status": "needs_owner",
        "summary": "Owner price/deposit review is still required.",
        "blocked_reasons": blocked,
    }


def _butcher_gate(match, ops):
    match = match if isinstance(match, dict) else {}
    ops = ops if isinstance(ops, dict) else {}
    if match.get("success") is False:
        return {
            "status": "degraded",
            "summary": "Butcher match is unavailable; no reservation can be recommended.",
            "blocked_reasons": [match.get("status") or "meat_match_unavailable"],
        }
    reservations = ops.get("reservations") if isinstance(ops.get("reservations"), list) else []
    if _active_reservation(reservations):
        return {"status": "ready", "summary": "An active carcass reservation exists.", "blocked_reasons": []}
    meat_match = match.get("meat_match") if isinstance(match.get("meat_match"), dict) else {}
    if meat_match.get("recommendation"):
        return {"status": "needs_owner", "summary": "Butcher match recommendation is ready for owner review.", "blocked_reasons": []}
    return {
        "status": "blocked",
        "summary": "No active reservation or safe Butcher match exists yet.",
        "blocked_reasons": ["no_active_reservation"],
    }


def _beacon_gate(provider=None):
    if provider is None:
        return {"status": "not_needed", "summary": "Beacon is optional for this command-state response."}
    try:
        result = provider()
    except Exception:
        return {"status": "degraded", "summary": "Beacon source is unavailable and non-blocking."}
    if isinstance(result, dict) and result.get("success") is False:
        return {"status": "degraded", "summary": "Beacon source is unavailable and non-blocking."}
    return {"status": "draft_only", "summary": "Beacon material is review-only and not posted."}


def _draft_reply(events, lead):
    if _has_event(events, "customer_followup_sent"):
        return {
            "status": "sent",
            "summary": "Customer follow-up was already sent.",
            "can_send": False,
            "send_blocked_reasons": ["already_sent"],
        }
    if _has_event(events, "owner_customer_followup_send_approved"):
        reasons = []
        if lead.get("whatsapp_window_state") != "open":
            reasons.append("whatsapp_window_not_open")
        return {
            "status": "approved",
            "summary": "Exact reply approval exists, but command-state remains read-only.",
            "can_send": False,
            "send_blocked_reasons": reasons or ["send_not_executed_by_command_state"],
        }
    return {
        "status": "not_generated",
        "summary": "Draft reply is generated on demand and is not persisted by command-state.",
        "can_send": False,
        "send_blocked_reasons": ["draft_not_generated"],
    }


def _ops_gate(ops):
    ops = ops if isinstance(ops, dict) else {}
    payment = ops.get("payment_gate") if isinstance(ops.get("payment_gate"), dict) else {}
    assembly = ops.get("assembly") if isinstance(ops.get("assembly"), dict) else {}
    drafts = ops.get("instruction_drafts") if isinstance(ops.get("instruction_drafts"), list) else []
    return {
        "reservation_status": assembly.get("status") or "none",
        "instruction_status": "drafted" if drafts else "not_started",
        "payment_status": payment.get("state") or "unknown",
    }


def _fulfillment_gate(source):
    source = source if isinstance(source, dict) else {}
    if source.get("success") is False:
        return {"status": "degraded", "summary": "Fulfillment timeline is unavailable."}
    fulfillment = source.get("fulfillment") if isinstance(source.get("fulfillment"), dict) else {}
    next_gate = fulfillment.get("next_gate", "")
    if not fulfillment:
        return {"status": "not_started", "summary": "Fulfillment has not started."}
    if next_gate in {"complete", "delivered"} or fulfillment.get("delivered"):
        return {"status": "complete", "summary": "Fulfillment appears complete."}
    if fulfillment.get("exception_open"):
        return {"status": "blocked", "summary": "Fulfillment has an open exception."}
    return {"status": "in_progress", "summary": next_gate or fulfillment.get("status") or "Fulfillment is in progress."}


def _reconciliation_gate(source):
    source = source if isinstance(source, dict) else {}
    if source.get("success") is False:
        return {"status": "degraded", "summary": "Reconciliation is unavailable."}
    reconciliation = source.get("reconciliation") if isinstance(source.get("reconciliation"), dict) else {}
    if not reconciliation:
        return {"status": "not_ready", "summary": "Reconciliation has not started."}
    if reconciliation.get("balance_confirmed") or reconciliation.get("next_gate") == "delivery_release_allowed":
        return {"status": "complete", "summary": "Final balance gate is clear."}
    if reconciliation.get("next_gate") == "confirm_final_balance_in_bank":
        return {"status": "ready", "summary": "Final balance confirmation is required."}
    return {"status": "not_ready", "summary": reconciliation.get("next_gate") or "Reconciliation is not ready."}


def _history(events):
    latest = events[0] if events else {}
    return {
        "latest_event": latest,
        "event_count": len(events),
        "summary": f"{len(events)} lead event(s) available." if events else "No lead events available.",
    }


def _next_action(contract_result, missing_facts, events, lead, money_gate, butcher_gate, draft_reply, ops, fulfillment, reconciliation):
    if missing_facts.get("missing"):
        return _action("missing_facts", "Capture Missing Facts", "Required customer/order facts are missing.", "draft_only", True, "open_missing_facts", missing_facts.get("missing"))
    contract = contract_result.get("contract") if isinstance(contract_result.get("contract"), dict) else {}
    money_approved = contract.get("contract_status") == "owner_money_path_ready" or _has_event(events, "owner_money_path_approved")
    if not money_approved:
        return _action("owner_price_deposit_review", "Owner Price/Deposit Review", "Facts are complete, but owner money-path review is not approved.", "owner_review", True, "open_money_review", money_gate.get("blocked_reasons", []))
    sent = _has_event(events, "customer_followup_sent")
    send_approved = _has_event(events, "owner_customer_followup_send_approved")
    if not send_approved and not sent:
        return _action("build_draft_reply", "Build Draft Reply", "Owner money path is ready; draft reply can be prepared for review.", "draft_only", True, "open_draft_reply", [])
    if send_approved and not sent:
        blocked = list(draft_reply.get("send_blocked_reasons") or [])
        if lead.get("whatsapp_window_state") != "open":
            blocked = _unique(blocked + ["whatsapp_window_not_open"])
        return _action("ready_for_owner_send_review", "Owner Send Review", "Exact reply approval exists, but sending remains gated outside command-state.", "owner_review", True, "open_send_review", blocked)
    if not _has_event(events, "customer_booking_confirmed"):
        return _action("wait_for_customer_yes", "Wait For Customer Yes", "Customer follow-up is sent; wait for a clear booking confirmation.", "wait", False, "show_customer_status", [])

    payment = ops.get("payment_gate") if isinstance(ops.get("payment_gate"), dict) else {}
    reservations = ops.get("reservations") if isinstance(ops.get("reservations"), list) else []
    active_reservation = _active_reservation(reservations)
    if payment.get("pop_received_unverified") and not payment.get("deposit_confirmed_in_bank"):
        return _action("confirm_money_in_bank", "Confirm Money In Bank", "POP alone does not unlock slaughter or delivery.", "owner_review", True, "open_money_gate", ["bank_confirmation_required"])
    if not active_reservation:
        return _action("reserve_or_pair_carcass", "Review Carcass Pairing", "Customer has confirmed; Butcher match or reservation needs owner review.", "owner_review", True, "open_butcher_gate", butcher_gate.get("blocked_reasons", []))
    if not payment.get("deposit_confirmed_in_bank"):
        return _action("record_pop_evidence", "Record POP Evidence", "Reservation exists but bank-confirmed money is still missing.", "owner_review", True, "open_money_gate", ["deposit_not_confirmed_in_bank"])
    drafts = ops.get("instruction_drafts") if isinstance(ops.get("instruction_drafts"), list) else []
    if not drafts:
        return _action("create_instruction_drafts", "Create Instruction Drafts", "Money and reservation gates are ready; instruction drafts are still missing.", "draft_only", True, "open_instruction_drafts", [])
    if not _has_approved_instruction(drafts):
        return _action("approve_external_instruction", "Approve External Instruction", "Instruction drafts exist and need explicit owner approval.", "owner_review", True, "open_instruction_approval", [])
    if fulfillment.get("status") in {"not_started", "in_progress", "blocked", "degraded"}:
        return _action("record_fulfillment", "Record Fulfillment", "Operational fulfillment still needs tracking.", "owner_review", True, "open_fulfillment", [] if fulfillment.get("status") != "degraded" else ["fulfillment_degraded"])
    if reconciliation.get("status") in {"not_ready", "ready", "blocked", "degraded"}:
        return _action("reconcile_final_invoice", "Reconcile Final Invoice", "Final invoice and balance release are not complete.", "owner_review", True, "open_reconciliation", [] if reconciliation.get("status") != "degraded" else ["reconciliation_degraded"])
    return _action("close_or_follow_up", "Close Or Follow Up", "All visible command-state gates are complete or waiting for owner follow-up.", "owner_review", True, "open_close_review", [])


def _action(key, label, why, risk_level, owner_action_required, allowed_ui_action, blocked_reasons):
    return {
        "key": key,
        "label": label,
        "why": why,
        "risk_level": risk_level,
        "owner_action_required": bool(owner_action_required),
        "allowed_ui_action": allowed_ui_action,
        "blocked_reasons": list(blocked_reasons or []),
    }


def _gatekeeper(next_action):
    blocked = list(next_action.get("blocked_reasons") or [])
    approval_required = bool(next_action.get("owner_action_required"))
    if blocked:
        status = "blocked"
    elif approval_required:
        status = "approval_required"
    else:
        status = "clear"
    return {
        "status": status,
        "risk_level": next_action.get("risk_level", "owner_review"),
        "approval_required": approval_required,
        "blocked_reasons": blocked,
    }


def _safe_actions(next_action):
    action = next_action.get("allowed_ui_action")
    return [action] if action else []


def _events(contract_result):
    lead = contract_result.get("lead") if isinstance(contract_result.get("lead"), dict) else {}
    events = lead.get("events") if isinstance(lead.get("events"), list) else []
    return [event for event in events if isinstance(event, dict)]


def _has_event(events, event_type):
    return any(event.get("event_type") == event_type for event in events)


def _active_reservation(reservations):
    for item in reservations:
        if isinstance(item, dict) and item.get("status") in ACTIVE_RESERVATION_STATUSES:
            return item
    return {}


def _has_approved_instruction(drafts):
    for item in drafts:
        if isinstance(item, dict) and item.get("approval_status") in {"approved", "owner_approved"}:
            return True
    return False


def _source_ref(source, status_code, result):
    result = result if isinstance(result, dict) else {}
    return {
        "source": source,
        "status_code": status_code,
        "status": result.get("status") or ("ok" if status_code < 400 else "unavailable"),
        "success": bool(result.get("success", status_code < 400)),
    }


def _degraded_source(source, status_code, result):
    result = result if isinstance(result, dict) else {}
    return {
        "source": source,
        "status_code": status_code,
        "status": result.get("status") or "unavailable",
    }


def _window_state(value):
    text = _clean(value, 40).lower()
    return text if text in {"open", "closed", "unknown"} else "unknown"


def _first(*values):
    for value in values:
        text = _clean(value, 500)
        if text:
            return text
    return ""


def _clean(value, limit):
    return str(value or "").strip()[:limit]


def _unique(values):
    seen = set()
    result = []
    for value in values or []:
        text = _clean(value, 100)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
