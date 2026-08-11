"""Provider-bound read-only HERDMASTER request lifecycle."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import json
from typing import Any, Callable, Mapping

from modules.oom_sakkie.gateway_authority import bind_gateway_owner_authority
from modules.pig_weights.mating_routes import load_current_breeding_operating_loop

CONTRACT_VERSION = "oom_sakkie_herdmaster_request_v1"
EVENT_SOURCE = "oom_sakkie_herdmaster_request"
BREEDING_PLAN_INTENTS = frozenset({"breeding_plan", "current_breeding_plan"})
ZERO = {"writes_farm_data": False, "writes_mating": False, "writes_weights": False,
        "hardware_commands": False, "customer_sends": False,
        "protected_actions_performed": False}


def handle_herdmaster_request(parsed: Mapping[str, Any], authority: Any, *,
        canonical_loader: Callable = load_current_breeding_operating_loop,
        event_store=None, now=None):
    semantic = parsed.get("semantic") if isinstance(parsed.get("semantic"), Mapping) else {}
    if (semantic.get("domain") != "herd_management"
            or str(semantic.get("intent") or "").strip().casefold() not in BREEDING_PLAN_INTENTS
            or semantic.get("needs_clarification") is True):
        return {"handled": False}, 200
    provider_id = str(parsed.get("provider_message_id") or "")
    provider_time = str(parsed.get("provider_timestamp") or "")
    owner = str(parsed.get("telegram_user_id") or "")
    chat = str(parsed.get("telegram_chat_id") or "")
    if not provider_id or not provider_time:
        return {"handled": False}, 200
    bound = bind_gateway_owner_authority(authority, "farm_manager_round")
    if not bound or bound.owner_user_id != owner or bound.private_chat_id != chat:
        return {"handled": False}, 200
    binding = {"owner": owner, "chat": chat, "provider_message_id": provider_id,
        "provider_timestamp": provider_time, "content_digest": _digest(parsed.get("text") or ""),
        "semantic_domain": "herd_management", "semantic_intent": str(semantic.get("intent") or ""),
        "requested_action": str(semantic.get("requested_action") or ""),
        "contract_version": CONTRACT_VERSION}
    mission_id = "OOM-HERDMASTER-REQUEST-" + _digest(
        {"owner": owner, "chat": chat, "provider_message_id": provider_id})[:24].upper()
    store = event_store or _event_store
    try:
        prior = store("load", mission_id, None)
    except Exception:
        return {"handled": True, "success": False,
            "status": "herdmaster_request_persistence_unavailable",
            "mission_id": mission_id, **ZERO}, 503
    if prior:
        if prior.get("binding") != binding:
            return {"handled": True, "success": False,
                "status": "herdmaster_request_provider_binding_conflict",
                "mission_id": mission_id, **ZERO}, 409
        return {**(prior.get("result") or {}), "status": "herdmaster_request_replay_recovered"}, 200
    try:
        packet = canonical_loader()
        if not isinstance(packet, Mapping) or packet.get("success") is not True:
            raise ValueError("canonical_herdmaster_packet_unavailable")
        answer, selected = render_breeding_plan(packet,
            language=str(semantic.get("language") or "en"))
    except Exception:
        return {"handled": True, "success": False,
            "status": "herdmaster_request_evidence_unavailable",
            "mission_id": mission_id, **ZERO}, 503
    output = {"handled": True, "success": True, "status": "herdmaster_request_ready",
        "specialist_identity": "HERDMASTER", "mission_id": mission_id,
        "card_mission_id": mission_id, "answer": answer, "binding": binding,
        "canonical_worklist_id": str(packet.get("worklist_id") or ""),
        "canonical_generated_at": str(packet.get("generated_at") or ""),
        "selected_task_ids": [str(row.get("task_id") or "") for row in selected],
        "result_digest": _digest({"binding": binding, "worklist": packet.get("worklist_id"),
                                  "answer": answer}), **ZERO}
    recorded = store("record", mission_id, {"binding": binding, "result": output})
    if not isinstance(recorded, Mapping) or recorded.get("success") is not True:
        return {"handled": True, "success": False,
            "status": "herdmaster_request_persistence_unproven",
            "mission_id": mission_id, **ZERO}, 503
    if recorded.get("created") is False:
        winner = store("load", mission_id, None) or {}
        if winner.get("binding") != binding:
            return {"handled": True, "success": False,
                "status": "herdmaster_request_provider_binding_conflict",
                "mission_id": mission_id, **ZERO}, 409
        return {**(winner.get("result") or {}), "status": "herdmaster_request_replay_recovered"}, 200
    return output, 200


def render_breeding_plan(packet: Mapping[str, Any], *, language="en"):
    tasks = [dict(row) for row in packet.get("tasks") or ()
             if isinstance(row, Mapping) and not row.get("completed")]
    tasks.sort(key=lambda row: (0 if row.get("days_since_weaning") == 0 else 1,
        int(row.get("placement_cohort_number") or 99),
        str(row.get("proposed_placement_date") or "9999-12-31"),
        -int(row.get("priority") or 0), str(row.get("tag_number") or "")))
    groups = []
    for row in tasks:
        male = ((row.get("male_recommendation") or {}).get("recommended") or {})
        key = (str(row.get("proposed_placement_date") or "Needs Data"),
               str(male.get("tag_number") or "Needs Data"),
               str(row.get("placement_cohort") or "review"))
        existing = next((group for group in groups if group[0] == key), None)
        if existing is None:
            existing = [key, []]; groups.append(existing)
        existing[1].append(row)
    af = str(language).casefold().startswith("af")
    lines = ["<b>HERDMASTER — OPGEDATEERDE TEELPLAN</b>" if af
             else "<b>HERDMASTER — UPDATED BREEDING PLAN</b>", ""]
    selected=[]
    for index, (key, rows) in enumerate(groups[:3], 1):
        date, male, _cohort = key
        names = ", ".join(html.escape(str(row.get("tag_number") or "Unnamed")) for row in rows)
        selected.extend(rows)
        if af:
            lines.append(f"• <b>{index}. {names}</b> — beplande plasing {html.escape(date)}; "
                         f"huidige bewys-gesteunde beer: {html.escape(male)}.")
        else:
            lines.append(f"• <b>{index}. {names}</b> — planned placement {html.escape(date)}; "
                         f"current evidence-supported boar: {html.escape(male)}.")
    if not selected:
        lines.append("• Geen huidige teeltaak is uit die kanonieke kuddebewyse verskuldig nie." if af
                     else "• No current breeding task is due from the canonical herd evidence.")
    today_names = [html.escape(str(row.get("tag_number") or "Unnamed")) for row in tasks
                   if row.get("days_since_weaning") == 0]
    if today_names:
        lines += ["", "<b>VANDAG SE SPEENWERK</b>" if af else "<b>TODAY'S WEANINGS</b>",
                  ("Ingesluit: " if af else "Included: ") + ", ".join(today_names) + "."]
    lines += ["", "Geen paring is uitgevoer nie; finale plasing bly beskerm." if af
              else "No mating was performed; final placement remains protected.",
              "HERDMASTER herbeoordeel wanneer kuddebewyse verander." if af
              else "HERDMASTER will reassess when herd evidence changes."]
    answer="\n".join(lines)
    if len(answer) > 3900:
        raise ValueError("herdmaster_request_render_budget_exceeded")
    return answer, selected


def delivery_retry_authority_for(result: Mapping[str, Any]):
    """Authorize retry two only after durable proof that attempt one sent nothing."""
    from modules.oom_sakkie.delivery_retry_authority import issue_delivery_retry_authority
    from modules.oom_sakkie.family_message_lifecycle import load_family_lifecycle
    mission_id=str(result.get("mission_id") or "")
    card_id=str(result.get("card_mission_id") or mission_id)
    answer=str(result.get("answer") or "")
    if not mission_id or not card_id or not answer:
        return None
    try:
        events=list(load_family_lifecycle(card_id) or ())
    except Exception:
        return None
    if any(row.get("state") in {"delivered","updated"} for row in events):
        return None
    definite=[row for row in events if row.get("state")=="contained"
              and row.get("reason")=="telegram_delivery_definitely_not_sent"]
    attempts=[row for row in events if row.get("state")=="delivery_attempted"]
    if len(definite)!=1 or len(attempts)!=1:
        return None
    return issue_delivery_retry_authority(mission_id=mission_id,card_mission_id=card_id,
        text=answer,proof_identity=str(definite[0].get("event_id") or ""))


def _event_store(action, identity, payload):
    from modules.sales.sam_live_stock_launch_control import (
        build_sam_live_stock_review_event, record_sam_live_stock_review_event)
    if action == "load":
        import os, psycopg
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
            connection.read_only = True
            with connection.cursor() as cursor:
                cursor.execute("""select review_json->'herdmaster_request'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s and review_event_id=%s limit 1""",
                    (EVENT_SOURCE, identity))
                row=cursor.fetchone(); return row[0] if row else None
    event=build_sam_live_stock_review_event({"conversation_id":identity},{},{},
        {"score":0,"safe_to_send":False,"recommended_action":"herdmaster_request"},
        event_source=EVENT_SOURCE)
    event.update({"review_event_id":identity,"chatwoot_conversation_id":identity,
        "review_json":{"herdmaster_request":payload},"decision_json":{},"facts_json":{},
        "customer_message_excerpt":"","sam_reply_excerpt":""})
    result,status=record_sam_live_stock_review_event(event)
    return {**result,"success":status < 400 and result.get("success") is True,
            "created":result.get("created",status < 300)}


def _digest(value):
    raw=value if isinstance(value,str) else json.dumps(value,sort_keys=True,separators=(",",":"),default=str)
    return hashlib.sha256(raw.encode()).hexdigest()
