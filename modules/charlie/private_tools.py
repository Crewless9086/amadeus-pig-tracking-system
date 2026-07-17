"""Typed, policy-bounded tools exposed to the private CHARLIE runtime."""

from __future__ import annotations

from modules.charlie.executive_store import executive_scorecard
from modules.charlie.improvement_analyst import analyst_scorecard
from modules.charlie.mission_store import (
    get_mission, list_missions, mission_status_summary, record_mission,
    transition_mission_review_state, update_mission_status,
)
from modules.charlie.owner_approval_inbox import list_owner_approval_inbox
from modules.charlie.runner_control import runner_status
from modules.beacon.workforce import beacon_workforce_scorecard
from modules.orders.order_read import list_orders
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
}


def execute_private_tool(intent_type, args):
    tool = TOOL_FOR_INTENT.get(intent_type)
    if not tool:
        return {"success": False, "status": "tool_not_available", "summary": "That action is not available through CHARLIE yet."}, 400
    return globals()[f"_{tool}"](args or {})


def _core_status(_args):
    summary, ss = mission_status_summary()
    local = runner_status(include_git=False, include_ledger=False)
    counts = summary.get("counts") or {}
    runner_label = "healthy" if local.get("process_alive") and local.get("heartbeat_fresh") else local.get("status", "unknown")
    text = f"CORE: {counts.get('in_progress',0)} active, {counts.get('approved',0)} approved, {counts.get('pr_ready',0)} ready for review, {counts.get('blocked',0)} blocked. Runner: {runner_label}."
    return {"success": ss < 400, "status": "core_status_ready", "summary": text, "counts": counts, "runner": local}, 200 if ss < 400 else ss


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
        disposition = packet.get("block_disposition") or {}
        rows.append({"mission_id": mission.get("mission_id"), "title": mission.get("title"), "reason": disposition.get("reason") or packet.get("blocked_reason"), "owner_required": disposition.get("owner_required") is True, "responsible_stage": disposition.get("responsible_stage") or packet.get("return_to_stage")})
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
    text = f"{mission.get('title') or mission.get('mission_id')} is {mission.get('status')}."
    if packet.get("blocked_reason"):
        text += f" Blocked because: {packet['blocked_reason']}."
    if packet.get("recommended_next_action"):
        text += f" Recommended next action: {packet['recommended_next_action']}"
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


def _farm_status(_args):
    orders, status = _orders_status({})
    if status >= 400:
        return {"success": False, "status": "farm_status_degraded", "summary": "Farm status is partially unavailable. " + orders["summary"]}, status
    return {"success": True, "status": "farm_status_ready", "summary": "Farm operational read access is active. " + orders["summary"], "orders": orders.get("counts")}, 200


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
    result, status = record_mission({"title": title[:180], "raw_text": str(args.get("raw_text") or title)[:6000], "urgency": str(args.get("urgency") or "P2"), "mission_type": str(args.get("mission_type") or "feature build"), "approval_level": "LEVEL 3", "metadata": {"created_from": "charlie_private_executive", "owner_work": True}}, source_context={"source": "charlie_private_executive"})
    mission_id = result.get("mission_id")
    return {"success": status < 400, "status": "mission_created" if status < 400 else result.get("status"), "summary": f"Mission created in CORE: {title} [{mission_id}]. It is waiting in New for approval.", "mission_id": mission_id}, status


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
    return {"success": code < 400, "status": result.get("status"), "summary": f"Mission {mission_id} moved from {current} to {target}." if code < 400 else "The mission changed before execution, so I made no stale update.", "mission_id": mission_id}, code


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
    return {
        "success": code < 400,
        "status": result.get("status"),
        "summary": f"Mission {mission_id} was returned to {stage}." if code < 400 else "The mission changed before execution, so I made no stale update.",
        "mission_id": mission_id,
        "target_stage": stage,
    }, code
