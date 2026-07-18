"""Typed, policy-bounded tools exposed to the private CHARLIE runtime."""

from __future__ import annotations

import os
import re

from modules.charlie.block_adjudication import adjudicate_block
from modules.charlie.executive_store import executive_scorecard
from modules.charlie.executive_store import list_capability_trust
from modules.charlie.improvement_analyst import analyst_scorecard
from modules.charlie.mission_store import (
    get_mission, list_missions, mission_status_summary, record_mission,
    transition_mission_review_state, update_mission_status,
)
from modules.charlie.owner_approval_inbox import list_owner_approval_inbox
from modules.charlie.runner_control import runner_status
from modules.beacon.workforce import beacon_workforce_scorecard
from modules.orders.order_read import get_order_detail, get_order_operator_summary, list_orders
from modules.sales.sam_live_stock_sales_pack import prepare_live_stock_sales_pack
from modules.sales.sam_conversation_state import plan_live_stock_next_action
from modules.orders.order_intake_service import get_intake_context
from modules.sales.sam_live_stock_runtime import load_chatwoot_conversation_history
from modules.beacon.post_composer import build_beacon_caption_suggestions
from modules.pig_weights.pig_weights_service import get_pig_detail, get_sales_availability
from modules.sales.conversation_learning import live_stock_learning_scorecard


TOOL_FOR_INTENT = {
    "executive_brief": "executive_brief", "read_core_status": "core_status", "read_queue": "queue",
    "read_blocked": "blocked", "read_mission": "mission", "read_workforce": "workforce",
    "read_analyst": "analyst", "read_decisions": "decisions", "create_mission": "create_mission",
    "approve_mission": "approve_mission", "pause_mission": "pause_mission", "reject_mission": "reject_mission",
    "send_back_mission": "send_back_mission",
    "read_business_status": "business_status", "read_sam_status": "sam_status",
    "read_beacon_status": "beacon_status", "read_orders_status": "orders_status",
    "read_farm_status": "farm_status",
    "read_pig": "pig",
    "read_order": "order", "prepare_order_pack": "order_pack",
    "prepare_beacon_draft": "beacon_draft", "read_trust": "trust",
    "read_sam_conversation": "sam_conversation",
}


def execute_private_tool(intent_type, args):
    tool = TOOL_FOR_INTENT.get(intent_type)
    if not tool:
        return {"success": False, "status": "tool_not_available", "summary": "That action is not available through CHARLIE yet."}, 400
    return globals()[f"_{tool}"](args or {})


def _core_status(_args):
    summary, ss = mission_status_summary()
    active_result, active_status = list_missions(status="in_progress", limit=5, compact=False)
    local = runner_status(include_git=False, include_ledger=False)
    counts = summary.get("counts") or {}
    cloud_cannot_see_local = bool(os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID"))
    runner_label = ("local heartbeat not visible from Render" if cloud_cannot_see_local else
                    "healthy" if local.get("process_alive") and local.get("heartbeat_fresh") else local.get("status", "unknown"))
    text = f"CORE: {counts.get('in_progress',0)} active, {counts.get('approved',0)} approved, {counts.get('pr_ready',0)} ready for review, {counts.get('blocked',0)} blocked. Runner: {runner_label}."
    active = active_result.get("missions") or []
    if active:
        lines = []
        for mission in active:
            metadata = mission.get("metadata") or {}
            packet = metadata.get("review_packet") or {}
            progress = metadata.get("progress_pct") or packet.get("progress_pct") or mission.get("progress_pct")
            stage = metadata.get("current_agent") or packet.get("current_agent") or packet.get("responsible_stage") or local.get("current_agent")
            detail = f"{mission.get('title') or mission.get('mission_id')} [{mission.get('mission_id')}]"
            if stage:
                detail += f", stage {stage}"
            if progress is not None:
                detail += f", {progress}% progress"
            lines.append(detail)
        text += " Active now: " + "; ".join(lines) + "."
    elif not cloud_cannot_see_local and local.get("process_alive") and local.get("last_mission_id"):
        text += f" The local runner last reported mission {local['last_mission_id']}, but Supabase currently has no mission marked in_progress."
    else:
        text += " No mission is currently marked in_progress."
    ok = ss < 400 and active_status < 400
    return {"success": ok, "status": "core_status_ready", "summary": text, "counts": counts, "active_missions": active, "runner": local}, 200 if ok else max(ss, active_status)


def _queue(_args):
    result, status = list_missions(status="owner_queue", limit=20, compact=True)
    missions = result.get("missions") or []
    lines = [f"{m.get('status')}: {m.get('title') or m.get('mission_id')} [{m.get('mission_id')}]" for m in missions[:10]]
    return {"success": status < 400, "status": "queue_ready", "summary": "Owner queue:\n" + ("\n".join(lines) or "No owner-work missions are waiting."), "missions": missions}, status


def _blocked(_args):
    result, status = list_missions(status="blocked", limit=20, compact=False)
    missions = result.get("missions") or []
    rows = []
    for mission in missions:
        packet = ((mission.get("metadata") or {}).get("review_packet") or {})
        decision = adjudicate_block(mission)
        rows.append({
            "mission_id": mission.get("mission_id"), "title": mission.get("title"),
            "reason": decision.get("reason") or packet.get("blocked_reason"),
            "owner_required": decision.get("owner_required") is True,
            "responsible_stage": decision.get("target_stage") or packet.get("return_to_stage"),
            "charlie_action": decision.get("action"),
        })
    lines = [f"- {row['title']} [{row['mission_id']}]: {row['reason'] or 'reason unavailable'}; next: {'Charl decision' if row['owner_required'] else row['responsible_stage'] or 'CHARLIE recovery'}" for row in rows]
    return {"success": status < 400, "status": "blocked_ready", "summary": "Blocked missions:\n" + ("\n".join(lines) or "No blocked missions."), "missions": rows}, status


def _mission(args):
    mission_id = str(args.get("mission_id") or "").strip()
    if not mission_id:
        return {"success": False, "status": "mission_id_required", "summary": "Send me the CORE mission ID you want inspected."}, 400
    result, status = get_mission(mission_id)
    mission = result.get("mission") or {}
    if status >= 400 or not mission:
        return {"success": False, "status": "mission_not_found", "summary": f"I could not find CORE mission {mission_id}."}, 404 if status < 500 else status
    packet = ((mission.get("metadata") or {}).get("review_packet") or {})
    metadata = mission.get("metadata") or {}
    progress = metadata.get("progress_pct") or packet.get("progress_pct") or mission.get("progress_pct")
    stage = metadata.get("current_agent") or packet.get("current_agent") or packet.get("responsible_stage") or packet.get("return_to_stage")
    text = f"{mission.get('title') or mission.get('mission_id')} [{mission.get('mission_id')}] is {mission.get('status')}."
    if stage:
        text += f" Current stage: {stage}."
    if progress is not None:
        text += f" Progress: {progress}%."
    if packet.get("blocked_reason"):
        text += f" Blocked because: {packet['blocked_reason']}."
    if packet.get("recommended_next_action"):
        text += f" Recommended next action: {packet['recommended_next_action']}"
    attempts = metadata.get("attempt_count") or packet.get("attempt_count")
    if attempts:
        text += f" Attempts recorded: {attempts}."
    return {"success": status < 400, "status": "mission_ready", "summary": text, "mission": mission}, status


def _workforce(_args):
    summary, ss = mission_status_summary()
    local = runner_status(include_git=False, include_ledger=False)
    runner_label = "healthy" if local.get("process_alive") and local.get("heartbeat_fresh") else local.get("status")
    return {"success": ss < 400, "status": "workforce_ready", "summary": f"Workforce: CORE runner {runner_label}; active missions {(summary.get('counts') or {}).get('in_progress',0)}. Detailed agent training remains on /charlie-agents.", "link": "/charlie-agents"}, 200


def _analyst(_args):
    result, status = analyst_scorecard(limit=50)
    card = result.get("scorecard") or {}
    effectiveness = float(card.get("validated_effectiveness_rate") or 0)
    return {"success": status < 400, "status": "analyst_ready", "summary": f"ANALYST: {card.get('observations',0)} observations, {card.get('pending_proposals',0)} pending proposals, {effectiveness:.0%} validated effectiveness.", "scorecard": card}, status


def _decisions(_args):
    result, status = list_owner_approval_inbox(limit_per_status=10)
    items = result.get("items") or []
    pending = [item for item in items if item.get("status") in {"pending", "send_back"}]
    lines = [f"- {item.get('title')} ({item.get('source_agent')}): {item.get('action_label')}" for item in pending[:8]]
    return {"success": status < 400, "status": "decisions_ready", "summary": f"{len(pending)} decision(s) need review.\n" + "\n".join(lines), "items": pending}, status


def _executive_brief(_args):
    core, _ = _core_status({})
    blocked, _ = _blocked({})
    analyst, _ = _analyst({})
    executive, _ = executive_scorecard()
    summary = f"Executive brief\n{core['summary']}\n{blocked['summary']}\n{analyst['summary']}\nExecutive recoveries open: {executive.get('open_recoveries',0)}; notification failures: {executive.get('notification_failures',0)}."
    return {"success": True, "status": "executive_brief_ready", "summary": summary, "sections": {"core": core, "blocked": blocked, "analyst": analyst, "executive": executive}}, 200


def _sam_status(_args):
    result, status = live_stock_learning_scorecard(limit=500)
    card = result.get("scorecard") or {}
    total = int(card.get("total_events") or card.get("events") or 0)
    edits = int(card.get("owner_edit_events") or card.get("edited_replies") or 0)
    summary = f"SAM livestock learning: {total} captured event(s), {edits} owner edit(s). Owner approval remains active."
    return {"success": status < 400, "status": "sam_status_ready", "summary": summary, "scorecard": card}, status


def _sam_conversation(args):
    conversation_id = str(args.get("conversation_id") or "").strip()
    if not conversation_id:
        return {"success": False, "status": "conversation_id_required", "summary": "Tell me the Chatwoot conversation ID."}, 400
    try:
        intake = get_intake_context(conversation_id)
        history = load_chatwoot_conversation_history(conversation_id, limit=12)
        plan = plan_live_stock_next_action(intake, {})
    except Exception as exc:
        return {"success": False, "status": "sam_conversation_read_failed", "summary": f"I could not verify conversation {conversation_id}: {exc.__class__.__name__}."}, 503
    messages = history.get("messages") if isinstance(history, dict) else history if isinstance(history, list) else []
    goal = plan.get("goal") or "not established"
    summary = f"SAM conversation {conversation_id}: goal {goal}; stage {plan.get('stage')}; next action {plan.get('next_action')}; {len(messages or [])} recent message(s) inspected."
    if plan.get("missing_fields"):
        summary += " Missing: " + ", ".join(plan["missing_fields"]) + "."
    return {"success": True, "status": "sam_conversation_ready", "summary": summary, "conversation_id": conversation_id, "intake": intake, "conversation_plan": plan, "recent_messages": messages}, 200


def _beacon_status(_args):
    result = beacon_workforce_scorecard(limit=500)
    card = result.get("scorecard") or {}
    summary = (f"Beacon: {card.get('progress_percent', 0)}% readiness, {card.get('approved_assets', 0)} approved asset(s), "
               f"{card.get('production_posts_sent', 0)} published post(s), {card.get('media_review_backlog', 0)} awaiting media review.")
    return {"success": bool(result.get("success")), "status": "beacon_status_ready", "summary": summary, "scorecard": card}, 200 if result.get("success") else 503


def _orders_status(_args):
    try:
        orders = list_orders()
    except Exception as exc:
        return {"success": False, "status": "orders_status_failed", "summary": f"Orders could not be read: {exc.__class__.__name__}."}, 503
    active = [row for row in orders if str(row.get("order_status") or "").lower() not in {"completed", "cancelled", "rejected"}]
    ready = [row for row in orders if str(row.get("approval_status") or "").lower() in {"approved", "quote_ready"}]
    return {"success": True, "status": "orders_status_ready", "summary": f"Orders: {len(orders)} total, {len(active)} active, {len(ready)} approved or quote-ready.", "counts": {"total": len(orders), "active": len(active), "ready": len(ready)}, "orders": orders[:10]}, 200


def _order(args):
    order_id = str(args.get("order_id") or "").strip().upper()
    if not order_id:
        return {"success": False, "status": "order_id_required", "summary": "Tell me which order you want inspected."}, 400
    try:
        detail = get_order_detail(order_id)
        operator = get_order_operator_summary(order_id) or {}
    except Exception as exc:
        return {"success": False, "status": "order_read_failed", "summary": f"I could not verify order {order_id}: {exc.__class__.__name__}."}, 503
    if not detail:
        return {"success": False, "status": "order_not_found", "summary": f"I could not find order {order_id}."}, 404
    order = detail.get("order") if isinstance(detail, dict) and isinstance(detail.get("order"), dict) else detail
    lines = detail.get("lines") if isinstance(detail, dict) else []
    status = order.get("Order_Status") or order.get("order_status") or order.get("status") or "unknown"
    approval = order.get("Approval_Status") or order.get("approval_status") or "not set"
    summary = f"Order {order_id} is {status}; approval {approval}; {len(lines or [])} line(s)."
    actions = operator.get("outstanding_actions") if isinstance(operator, dict) else []
    if actions:
        labels = [str(item.get("label") or item.get("code") or "") if isinstance(item, dict) else str(item) for item in actions[:4]]
        summary += " Next: " + "; ".join(item for item in labels if item) + "."
    return {"success": True, "status": "order_ready", "summary": summary, "order_id": order_id, "detail": detail, "operator_summary": operator}, 200


def _order_pack(args):
    order_id = str(args.get("order_id") or "").strip().upper()
    if not order_id:
        return {"success": False, "status": "order_id_required", "summary": "Tell me which order needs the document pack."}, 400
    try:
        result = prepare_live_stock_sales_pack(order_id, {"created_by": "CHARLIE private executive"})
    except (ValueError, RuntimeError) as exc:
        return {"success": False, "status": "order_pack_preparation_failed", "summary": str(exc)}, 409
    success = result.get("success") is True
    summary = f"Prepared and verified the livestock sales pack for {order_id}. Nothing was sent or reserved." if success else f"The sales pack for {order_id} still needs input: {', '.join(result.get('missing_fields') or [row.get('reason','') for row in result.get('errors') or []])}."
    return {**result, "success": success, "summary": summary, "prepared_only": True}, 200 if success else 409


def _beacon_draft(args):
    result, status = build_beacon_caption_suggestions({"brief": args.get("brief"), "campaign_lane": args.get("campaign_lane")})
    suggestions = result.get("suggestions") or []
    summary = "Beacon prepared three owner-review caption options. Nothing was posted.\n" + "\n\n".join(f"Option {index + 1}: {value}" for index, value in enumerate(suggestions)) if status < 400 else "Beacon could not prepare a safe draft: " + str(result.get("status") or "unknown reason")
    return {**result, "summary": summary, "prepared_only": True, "posts_publicly": False}, status


def _trust(_args):
    result, status = list_capability_trust(limit=50)
    rows = result.get("capabilities") or []
    delegated = [row for row in rows if row.get("tier") in {"delegated", "auto"}]
    summary = f"CHARLIE capability trust: {len(rows)} measured capabilities; {len(delegated)} delegated or auto. Trust is capability-specific and never overrides red-zone approval."
    return {"success": status < 400, "status": "trust_ready", "summary": summary, "capabilities": rows}, status


def _farm_status(_args):
    orders, status = _orders_status({})
    if status >= 400:
        return {"success": False, "status": "farm_status_degraded", "summary": "Farm status is partially unavailable. " + orders["summary"]}, status
    try:
        availability = get_sales_availability()
        rows = availability.get("rows") if isinstance(availability, dict) else availability if isinstance(availability, list) else []
        stock_note = f" Livestock availability has {len(rows or [])} candidate record(s)."
    except Exception:
        rows, stock_note = [], " Livestock availability could not be verified."
    return {"success": True, "status": "farm_status_ready", "summary": "Farm operational read access is active. " + orders["summary"] + stock_note, "orders": orders.get("counts"), "availability_count": len(rows or [])}, 200


def _pig(args):
    pig_id = str(args.get("pig_id") or "").strip().upper()
    if not pig_id:
        return {"success": False, "status": "pig_id_required", "summary": "Tell me the pig ID or tag number you want inspected."}, 400
    try:
        detail = get_pig_detail(pig_id)
    except Exception as exc:
        return {"success": False, "status": "pig_read_failed", "summary": f"I could not verify pig {pig_id}: {exc.__class__.__name__}."}, 503
    if not detail:
        return {"success": False, "status": "pig_not_found", "summary": f"I could not find pig {pig_id} in the authoritative herd records."}, 404
    pig = detail.get("pig") if isinstance(detail, dict) and isinstance(detail.get("pig"), dict) else detail
    tag = pig.get("Tag_Number") or pig.get("tag_number") or pig_id
    sex = pig.get("Sex") or pig.get("sex") or "unknown sex"
    pen = pig.get("Current_Pen_ID") or pig.get("current_pen_id") or pig.get("Pen_ID") or "no current pen"
    weight = pig.get("Latest_Weight_KG") or pig.get("latest_weight_kg") or pig.get("Weight_KG")
    summary = f"Pig {tag} ({pig_id}) is {sex} and is in {pen}."
    if weight not in (None, ""):
        summary += f" Latest recorded weight: {weight} kg."
    return {"success": True, "status": "pig_ready", "summary": summary, "pig_id": pig_id, "detail": detail}, 200


def _business_status(_args):
    sections = {}
    for name, reader in (("core", _core_status), ("sam", _sam_status), ("beacon", _beacon_status), ("orders", _orders_status), ("farm", _farm_status)):
        sections[name], _ = reader({})
    summary = "Business status\n" + "\n".join(f"{name.upper()}: {value.get('summary')}" for name, value in sections.items())
    return {"success": all(value.get("success") for value in sections.values()), "status": "business_status_ready", "summary": summary, "sections": sections}, 200


def _create_mission(args):
    title = str(args.get("title") or args.get("raw_text") or "").strip()
    if not title:
        return {"success": False, "status": "mission_text_required", "summary": "Tell me what outcome the mission must deliver."}, 400
    existing, existing_status = list_missions(limit=100, compact=True)
    if existing_status < 400:
        fingerprint = _mission_fingerprint(title)
        duplicate = next((row for row in existing.get("missions") or [] if row.get("status") not in {"done", "merged", "deployed", "rejected"} and _mission_fingerprint(row.get("title")) == fingerprint), None)
        if duplicate:
            mission_id = duplicate.get("mission_id")
            return {"success": True, "status": "existing_mission_reused", "summary": f"CORE already has this active outcome [{mission_id}]. I reused it instead of creating a duplicate.", "mission_id": mission_id, "verified": True, "duplicate_prevented": True}, 200
    result, status = record_mission({"title": title[:180], "raw_text": str(args.get("raw_text") or title)[:6000], "urgency": str(args.get("urgency") or "P2"), "mission_type": str(args.get("mission_type") or "feature build"), "approval_level": "LEVEL 3", "metadata": {"created_from": "charlie_private_executive", "owner_work": True, "executive_outcome": title[:500]}}, source_context={"source": "charlie_private_executive"})
    mission_id = result.get("mission_id")
    verified = False
    if status < 400 and mission_id:
        loaded, loaded_status = get_mission(mission_id)
        verified = loaded_status < 400 and (loaded.get("mission") or {}).get("mission_id") == mission_id
    code = status if status >= 400 else (200 if verified else 503)
    return {"success": verified, "status": "mission_created_verified" if verified else result.get("status") or "mission_create_unverified", "summary": f"Mission created and verified in CORE: {title} [{mission_id}]. It is waiting in New for approval." if verified else "CORE did not provide enough evidence to verify the mission creation.", "mission_id": mission_id, "verified": verified}, code


def _mission_fingerprint(value):
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def _mission_transition(args, target):
    mission_id = args.get("mission_id")
    loaded, status = get_mission(mission_id)
    if status >= 400:
        return {"success": False, "status": "mission_not_found", "summary": "I could not find that mission."}, status
    current = (loaded.get("mission") or {}).get("status")
    allowed = {"approved": {"new", "blocked"}, "paused": {"new", "approved", "blocked"}, "rejected": {"new", "blocked"}}
    if current not in allowed[target]:
        return {"success": False, "status": "transition_not_allowed", "summary": f"I did not change it because {current} cannot safely move to {target}."}, 409
    result, code = update_mission_status(mission_id, target, owner_decision=f"Explicit private CHARLIE owner instruction: {target}", expected_status=current)
    verified = False
    if code < 400:
        reloaded, reload_status = get_mission(mission_id)
        verified = reload_status < 400 and (reloaded.get("mission") or {}).get("status") == target
    final_code = code if code >= 400 else (200 if verified else 503)
    return {"success": verified, "status": f"mission_{target}_verified" if verified else result.get("status") or "mission_transition_unverified", "summary": f"Mission {mission_id} moved from {current} to {target}, and I verified the new state." if verified else "The mission action could not be verified against current Supabase state.", "mission_id": mission_id, "verified": verified}, final_code


def _approve_mission(args): return _mission_transition(args, "approved")
def _pause_mission(args): return _mission_transition(args, "paused")
def _reject_mission(args): return _mission_transition(args, "rejected")


def _send_back_mission(args):
    mission_id = args.get("mission_id")
    loaded, status = get_mission(mission_id)
    if status >= 400:
        return {"success": False, "status": "mission_not_found", "summary": "I could not find that mission."}, status
    mission = loaded.get("mission") or {}
    current = mission.get("status")
    if current not in {"blocked", "pr_ready"}:
        return {"success": False, "status": "transition_not_allowed", "summary": f"I did not change it because {current} is not awaiting review."}, 409
    packet = dict(((mission.get("metadata") or {}).get("review_packet") or {}))
    stage = str(args.get("target_stage") or packet.get("responsible_stage") or packet.get("return_to_stage") or packet.get("blocked_agent") or "builder")
    packet.update({
        "review_status": "send_back",
        "return_to_stage": stage,
        "responsible_stage": stage,
        "owner_decision": "send_back",
        "owner_comments": str(args.get("comments") or "Returned by Charl through private CHARLIE.")[:1000],
    })
    result, code = transition_mission_review_state(
        mission_id, "blocked", packet, expected_status=current,
        owner_decision="Explicit private CHARLIE owner instruction: send back",
        notes=f"Owner returned mission to {stage} through private CHARLIE.",
    )
    verified = False
    if code < 400:
        reloaded, reload_status = get_mission(mission_id)
        updated = reloaded.get("mission") or {}
        updated_packet = ((updated.get("metadata") or {}).get("review_packet") or {})
        verified = reload_status < 400 and updated.get("status") == "blocked" and updated_packet.get("return_to_stage") == stage
    final_code = code if code >= 400 else (200 if verified else 503)
    return {
        "success": verified,
        "status": "mission_send_back_verified" if verified else result.get("status") or "mission_send_back_unverified",
        "summary": f"Mission {mission_id} was returned to {stage}, and I verified the recovery state." if verified else "The send-back could not be verified against current Supabase state.",
        "mission_id": mission_id,
        "target_stage": stage,
        "verified": verified,
    }, final_code
