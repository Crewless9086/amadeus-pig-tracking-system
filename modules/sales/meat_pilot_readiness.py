from modules.oom_sakkie.sales_campaign_store import list_sales_leads, get_sales_lead_preorder_contract
from modules.sales.meat_documents import build_meat_estimated_quote_packet
from modules.sales.meat_ops import get_meat_ops_status
from modules.sales.meat_template_pack import meat_whatsapp_template_pack


def get_meat_pilot_readiness(limit=12, status_filter="launch_test"):
    leads_result, leads_status = list_sales_leads(limit=limit, status_filter=status_filter)
    if leads_status >= 400:
        return leads_result, leads_status

    leads = leads_result.get("sales_leads") if isinstance(leads_result.get("sales_leads"), list) else []
    lead_rows = []
    degraded_sources = []
    for item in leads[:_safe_limit(limit)]:
        row = _lead_readiness_row(item)
        lead_rows.append(row)
        degraded_sources.extend(row.get("degraded_sources", []))

    templates = _safe_template_pack()
    if templates.get("source_degraded"):
        degraded_sources.append(_degraded_source("template_pack", "pilot_readiness", templates.get("degraded_reason") or "template_pack_unavailable"))

    summary = _summary(lead_rows, templates)
    status = "degraded" if degraded_sources else "ok"
    return {
        "success": True,
        "status": status,
        "mode": "meat_sales_pilot_readiness_dashboard",
        "pilot_percent": summary["pilot_percent"],
        "summary": summary,
        "lead_stages": lead_rows,
        "template_pack": {
            "configured_count": templates.get("configured_count", 0),
            "required_count": templates.get("required_count", 0),
            "all_configured": templates.get("all_configured", False),
            "missing_envs": templates.get("missing_envs", []),
        },
        "checklist": _checklist(summary, lead_rows, templates),
        "next_gate": summary["next_gate"],
        "degraded_sources": degraded_sources,
        "source_degraded": bool(degraded_sources),
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_meta": False,
        "creates_quote": False,
        "creates_invoice": False,
        "creates_order": False,
        "changes_stock": False,
        "customer_public_output_enabled": False,
    }, 200


def _lead_readiness_row(lead):
    lead = lead if isinstance(lead, dict) else {}
    lead_id = str(lead.get("lead_id") or "").strip()
    degraded_sources = []

    contract, contract_status, degraded = _safe_source_read(
        "contract",
        lead_id,
        lambda: get_sales_lead_preorder_contract(lead_id),
        default_body={},
    ) if lead_id else ({}, 400, _degraded_source("lead", "", "missing_lead_id"))
    if degraded:
        degraded_sources.append(degraded)

    quote, quote_status, degraded = _safe_source_read(
        "quote",
        lead_id,
        lambda: build_meat_estimated_quote_packet(lead_id),
        default_body={},
    ) if lead_id else ({}, 400, None)
    if degraded:
        degraded_sources.append(degraded)

    ops, ops_status, degraded = _safe_source_read(
        "ops",
        lead_id,
        lambda: get_meat_ops_status(lead_id),
        default_body={},
    ) if lead_id else ({}, 400, None)
    if degraded:
        degraded_sources.append(degraded)

    contract_body = contract.get("contract") if isinstance(contract.get("contract"), dict) else {}
    assembly = ops.get("assembly") if isinstance(ops.get("assembly"), dict) else {}
    payment_gate = ops.get("payment_gate") if isinstance(ops.get("payment_gate"), dict) else {}
    latest_event = lead.get("latest_event") if isinstance(lead.get("latest_event"), dict) else {}
    stage = _stage(lead, contract_body, quote, assembly, payment_gate, latest_event)
    return {
        "lead_id": lead_id,
        "lead_label": lead.get("lead_label") or "Buyer lead",
        "status": lead.get("status") or "",
        "chatwoot_conversation_id": lead.get("chatwoot_conversation_id") or "",
        "whatsapp_window_state": lead.get("whatsapp_window_state") or "",
        "interest": lead.get("interest") if isinstance(lead.get("interest"), dict) else {},
        "stage": stage,
        "stage_label": _stage_label(stage),
        "stage_percent": _stage_percent(stage),
        "contract_status": contract_body.get("contract_status", ""),
        "quote_safe": bool(quote.get("quote_safe")) if quote_status == 200 else False,
        "quote_status": quote.get("status", "") if isinstance(quote, dict) else "",
        "payment_state": payment_gate.get("state", "unknown"),
        "payment_gate": payment_gate,
        "assembly_status": assembly.get("status", ""),
        "full_carcass_committed": bool(assembly.get("full_carcass_committed")),
        "ready_for_slaughter_booking": bool(assembly.get("ready_for_slaughter_booking")),
        "latest_event_type": latest_event.get("event_type", ""),
        "blockers": _blockers(contract_status, contract_body, quote_status, quote, ops_status, assembly, payment_gate),
        "next_action": _next_action(stage, quote, payment_gate, assembly),
        "degraded_sources": degraded_sources,
        "source_degraded": bool(degraded_sources),
    }


def _safe_template_pack():
    try:
        templates = meat_whatsapp_template_pack()
    except Exception as exc:
        return {
            "configured_count": 0,
            "required_count": 0,
            "all_configured": False,
            "missing_envs": ["template_pack_unavailable"],
            "source_degraded": True,
            "degraded_reason": exc.__class__.__name__,
        }
    if not isinstance(templates, dict):
        return {
            "configured_count": 0,
            "required_count": 0,
            "all_configured": False,
            "missing_envs": ["template_pack_unavailable"],
            "source_degraded": True,
            "degraded_reason": "invalid_source_payload",
        }
    return templates

def _safe_source_read(source, lead_id, reader, default_body=None):
    try:
        result, status_code = reader()
    except Exception as exc:
        return default_body or {}, 503, _degraded_source(source, lead_id, exc.__class__.__name__)
    if not isinstance(result, dict):
        return default_body or {}, 503, _degraded_source(source, lead_id, "invalid_source_payload")
    return result, status_code, None


def _degraded_source(source, lead_id, reason):
    return {
        "source": source,
        "lead_id": lead_id,
        "status": "degraded",
        "reason": reason,
    }


def _stage(lead, contract, quote, assembly, payment_gate, latest_event):
    if latest_event.get("event_type") == "closed" or lead.get("status") in {"closed", "not_interested"}:
        return "closed"
    if assembly.get("ready_for_slaughter_booking"):
        return "slaughter_ready"
    if payment_gate.get("state") == "deposit_confirmed_in_bank":
        return "deposit_confirmed"
    if payment_gate.get("state") == "pop_received_unverified":
        return "pop_review"
    if any((event.get("event_type") or "").startswith("estimated_quote_delivery") for event in lead.get("events", []) if isinstance(event, dict)):
        return "quote_delivered"
    if quote.get("quote_safe"):
        return "quote_ready"
    if contract.get("contract_status") == "owner_money_path_ready":
        return "document_gate"
    return "intake"


def _stage_label(stage):
    return {
        "intake": "Intake",
        "document_gate": "Document gate",
        "quote_ready": "Quote ready",
        "quote_delivered": "Quote delivered",
        "pop_review": "POP review",
        "deposit_confirmed": "Deposit confirmed",
        "slaughter_ready": "Slaughter ready",
        "closed": "Closed",
    }.get(stage, "Review")


def _stage_percent(stage):
    return {
        "intake": 20,
        "document_gate": 35,
        "quote_ready": 50,
        "quote_delivered": 60,
        "pop_review": 68,
        "deposit_confirmed": 78,
        "slaughter_ready": 88,
        "closed": 100,
    }.get(stage, 10)


def _blockers(contract_status, contract, quote_status, quote, ops_status, assembly, payment_gate):
    blockers = []
    if contract_status != 200:
        blockers.append("contract_read_failed")
    for item in contract.get("missing_fields") or contract.get("missing_before_money_path") or []:
        blockers.append(str(item))
    if quote_status >= 400:
        blockers.extend(str(item) for item in quote.get("blockers", []))
        if not quote.get("blockers"):
            blockers.append("quote_read_failed")
    if payment_gate.get("state") == "pop_received_unverified":
        blockers.append("bank_confirmation_required")
    elif payment_gate.get("state") in {"deposit_not_received", "unknown", ""}:
        blockers.append("deposit_not_bank_confirmed")
    if not assembly.get("full_carcass_committed"):
        blockers.append("full_carcass_not_assembled")
    if ops_status >= 400:
        blockers.append("ops_status_unavailable")
    return list(dict.fromkeys(item for item in blockers if item))


def _next_action(stage, quote, payment_gate, assembly):
    if stage == "intake":
        return "Let Sam collect missing product, delivery, timing, or EFT details."
    if stage in {"document_gate", "quote_ready"}:
        return "Send or resend the estimated quote, then wait for customer confirmation."
    if stage == "quote_delivered":
        return "Wait for customer confirmation or deposit/POP."
    if stage == "pop_review":
        return payment_gate.get("customer_wording", "Check bank before moving the booking forward.")
    if stage == "deposit_confirmed":
        return "Assemble the full carcass and prepare abattoir/butcher instruction drafts."
    if stage == "slaughter_ready":
        return "Confirm Dad/abattoir/butcher timing and draft customer journey update."
    return quote.get("next_gate") or assembly.get("next_gate") or "Review lead."


def _summary(rows, templates):
    active = [row for row in rows if row["stage"] != "closed"]
    highest = max([row["stage_percent"] for row in active] or [0])
    template_bonus = 8 if templates.get("all_configured") else 0
    pilot_percent = min(90, max(70 if active else 60, highest + template_bonus))
    next_gate = "run_small_live_client_test" if pilot_percent >= 85 else "finish_template_and_payment_gates_before_public_boost"
    return {
        "lead_count": len(rows),
        "active_lead_count": len(active),
        "quote_ready_count": len([row for row in active if row["stage"] in {"quote_ready", "quote_delivered", "pop_review", "deposit_confirmed", "slaughter_ready"}]),
        "pop_review_count": len([row for row in active if row["stage"] == "pop_review"]),
        "deposit_confirmed_count": len([row for row in active if row["stage"] in {"deposit_confirmed", "slaughter_ready"}]),
        "slaughter_ready_count": len([row for row in active if row["stage"] == "slaughter_ready"]),
        "template_pack_configured": bool(templates.get("all_configured")),
        "pilot_percent": pilot_percent,
        "next_gate": next_gate,
    }


def _checklist(summary, rows, templates):
    return [
        _item("whatsapp_templates", "WhatsApp template pack created and env names configured", bool(templates.get("all_configured")), templates.get("missing_envs", [])),
        _item("quote_docs", "At least one lead can generate and send an estimated quote", summary["quote_ready_count"] > 0, []),
        _item("payment_gate", "Payment gate separates POP received from money confirmed", True, []),
        _item("deposit_confirmed", "At least one pilot lead has bank-confirmed deposit before slaughter", summary["deposit_confirmed_count"] > 0, ["deposit_confirmed_in_bank"]),
        _item("fulfillment_ready", "Full carcass assembly and slaughter gate are ready", summary["slaughter_ready_count"] > 0, ["full_carcass_committed", "deposit_confirmed_in_bank"]),
        _item("beacon_media", "Beacon has owner-approved image media for the launch post", False, ["approved_beacon_image_selected"]),
    ]


def _item(key, label, complete, blockers):
    return {
        "key": key,
        "label": label,
        "complete": bool(complete),
        "blockers": blockers,
    }


def _safe_limit(value):
    try:
        return max(1, min(int(value), 50))
    except (TypeError, ValueError):
        return 12
