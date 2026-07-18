"""Evidence-grounded multi-tool executive loop for private CHARLIE."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import urllib.request

from modules.charlie.private_policy import authority_for_intent
from modules.charlie.private_policy import private_policy
from modules.charlie.private_capabilities import capability_metadata, follow_up_capabilities, select_capabilities
from modules.charlie.private_tools import TOOL_FOR_INTENT, execute_private_tool

MAX_TOOLS_PER_TURN = 8
MAX_INITIAL_TOOLS = 5

READ_PLANS = {
    "read_core_status": ("read_core_status", "read_blocked"),
    "executive_brief": ("read_core_status", "read_blocked", "read_decisions", "read_analyst"),
    "read_business_status": ("read_business_status",),
    "read_queue": ("read_queue",),
    "read_blocked": ("read_blocked",),
    "read_mission": ("read_mission",),
    "read_workforce": ("read_workforce",),
    "read_analyst": ("read_analyst",),
    "read_decisions": ("read_decisions",),
    "read_sam_status": ("read_sam_status",),
    "read_beacon_status": ("read_beacon_status",),
    "read_orders_status": ("read_orders_status",),
    "read_farm_status": ("read_farm_status",),
    "read_order": ("read_order",),
    "prepare_order_pack": ("prepare_order_pack",),
    "prepare_beacon_draft": ("prepare_beacon_draft",),
    "read_trust": ("read_trust",),
    "read_sam_conversation": ("read_sam_conversation",),
}


def build_executive_plan(owner_text, intent, context=None):
    context = context if isinstance(context, dict) else {}
    intent_type = str(intent.get("type") or "clarify")
    tools = select_capabilities(owner_text, intent_type, intent.get("args") or {}, limit=MAX_INITIAL_TOOLS)
    if not tools and intent_type != "investigate":
        tools = list(READ_PLANS.get(intent_type) or (intent_type,))[:MAX_INITIAL_TOOLS]
    subject = _subject(intent_type, intent.get("args") or {}, context)
    goal = _goal(owner_text, intent_type, subject)
    return {
        "version": "charlie_private_executive_plan_v3",
        "goal": goal,
        "subject": subject,
        "intent_type": intent_type,
        "tools": [{"intent_type": item, "args": _tool_args(item, intent.get("args") or {}, subject)} for item in tools],
        "completion_condition": "Return a direct answer supported by authoritative evidence, identify unresolved gaps, and recommend or delegate the next bounded action.",
        "risk_flags": list(intent.get("risk_flags") or []),
        "existing_commitments": list(((context.get("open_context") or {}).get("commitments") or []))[-20:],
        "owner_preferences": dict(context.get("preferences") or {}),
        "recent_conversation": [{"role": row.get("role"), "content": str(row.get("content") or "")[:700]} for row in (context.get("messages") or [])[-6:]],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def run_executive_plan(plan, intent_id, *, recorder=None, event_sink=None):
    evidence = _run_steps((plan.get("tools") or [])[:MAX_INITIAL_TOOLS], plan, intent_id, recorder, event_sink=event_sink, start_index=1)
    selected = [item.get("intent_type") for item in evidence]
    follow_ups = follow_up_capabilities(evidence, selected, limit=MAX_TOOLS_PER_TURN - len(evidence))
    if follow_ups:
        steps = [{"intent_type": name, "args": {}} for name in follow_ups]
        evidence.extend(_run_steps(steps, plan, intent_id, recorder, event_sink=event_sink, start_index=len(evidence) + 1))
    return sorted(evidence, key=lambda item: item.get("step") or 0)


def _run_steps(steps, plan, intent_id, recorder, *, event_sink=None, start_index):
    authorized = []
    evidence = []
    for index, step in enumerate(steps, start=start_index):
        intent_type = step.get("intent_type")
        authority = authority_for_intent(intent_type, plan.get("risk_flags"), explicit_owner_command=False)
        if not authority["allowed"]:
            evidence.append({"step": index, "intent_type": intent_type, "success": False, "status": "authority_denied", "authority": authority})
            break
        if event_sink:
            event_sink("capability_started", {"capability": intent_type, "domain": capability_metadata(intent_type).get("domain")})
        authorized.append((index, step, authority))
    with ThreadPoolExecutor(max_workers=max(1, len(authorized))) as pool:
        futures = [(index, step, authority, pool.submit(
            _execute_step, step, plan, intent_id, recorder, event_sink,
        )) for index, step, authority in authorized]
        completed = [(index, step, authority, future.result()) for index, step, authority, future in futures]
    for index, step, authority, (result, status) in completed:
        intent_type = step.get("intent_type")
        succeeded = status < 400 and result.get("success") is not False
        metadata = capability_metadata(intent_type)
        item = {"step": index, "intent_type": intent_type, "tool": TOOL_FOR_INTENT.get(intent_type, intent_type), "success": succeeded, "status": status, "result": result,
                "domain": metadata.get("domain"), "source_of_truth": metadata.get("source_of_truth"), "freshness_seconds": metadata.get("freshness_seconds"),
                "observed_at": datetime.now(timezone.utc).isoformat()}
        evidence.append(item)
        if event_sink:
            event_sink("evidence_received", {"capability": intent_type, "domain": item.get("domain"), "success": succeeded, "status": status, "summary": str(result.get("summary") or "")[:240]})
        if recorder:
            recorder(intent_id, item["tool"], authority["tier"], step.get("args") or {}, result, status="succeeded" if succeeded else "failed")
    return evidence


def _execute_step(step, plan, intent_id, recorder, event_sink):
    intent_type = step.get("intent_type")
    args = step.get("args") or {}
    if intent_type in {"read_farm_status", "read_pig"}:
        return execute_private_tool(intent_type, args, {
            "intent_id": intent_id, "recorder": recorder, "event_sink": event_sink,
            "owner_question": plan.get("goal"), "subject": plan.get("subject") or {},
        })
    return execute_private_tool(intent_type, args)


def compose_executive_reply(plan, evidence, *, environ=None, http_open=None):
    successful = [item for item in evidence if item.get("success")]
    if not successful:
        if plan.get("intent_type") == "investigate" and not evidence:
            return "I understand the question, but I do not yet have an authoritative capability for that domain. I can log a bounded CORE mission to add it rather than guess."
        first = evidence[0] if evidence else {}
        result = first.get("result") if isinstance(first.get("result"), dict) else {}
        return result.get("summary") or "I could not verify that from the authoritative system, so I will not guess."
    primary = successful[0].get("result") or {}
    intent_type = plan.get("intent_type")
    if intent_type not in {"read_core_status", "executive_brief"}:
        lines = [str(primary.get("summary") or "I verified the requested information.")]
        supporting = [str((item.get("result") or {}).get("summary") or "") for item in successful[1:]]
        lines.extend(value for value in supporting if value and value not in lines)
        failed = [item for item in evidence if not item.get("success")]
        if failed:
            lines.append("Evidence gap: " + ", ".join(str(item.get("tool") or item.get("intent_type")) for item in failed) + " could not be verified.")
        deterministic = "\n".join(lines)
        return _grounded_synthesis(plan, evidence, deterministic, environ=environ, http_open=http_open)
    lines = [str(primary.get("summary") or "CORE status verified.")]
    by_intent = {item.get("intent_type"): item.get("result") or {} for item in successful[1:]}
    blocked = by_intent.get("read_blocked") or {}
    blocked_rows = blocked.get("missions") or []
    genuine = [row for row in blocked_rows if row.get("owner_required")]
    recoverable = [row for row in blocked_rows if not row.get("owner_required")]
    if blocked_rows:
        recoverable_verb = "is" if len(recoverable) == 1 else "are"
        genuine_verb = "genuinely needs" if len(genuine) == 1 else "genuinely need"
        lines.append(f"Of the blocked missions, {len(recoverable)} {recoverable_verb} CORE-recoverable and {len(genuine)} {genuine_verb} your decision.")
        for row in genuine[:3]:
            reason = str(row.get('reason') or 'reason unavailable').rstrip('. ')
            lines.append(f"Your decision: {row.get('title') or row.get('mission_id')} - {reason}."
            )
    decisions = by_intent.get("read_decisions") or {}
    pending = decisions.get("items") or []
    if pending:
        lines.append(f"There are {len(pending)} verified owner decision item(s) waiting.")
    analyst = by_intent.get("read_analyst") or {}
    if analyst.get("summary"):
        lines.append(str(analyst["summary"]))
    deterministic = "\n".join(lines)
    return _grounded_synthesis(plan, evidence, deterministic, environ=environ, http_open=http_open)


def _grounded_synthesis(plan, evidence, fallback, *, environ=None, http_open=None):
    policy = private_policy(environ)
    if not policy.get("llm_enabled"):
        return fallback
    safe_evidence = []
    for item in evidence:
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        safe_evidence.append({
              "capability": item.get("intent_type"),
              "success": item.get("success"),
              "status": item.get("status"),
              "summary": str(result.get("summary") or "")[:2000],
              "structured_result": _bounded_agent_result(result),
          })
    payload = {
        "model": policy["llm_model"],
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": "You are CHARLIE, Charl's private digital executive. Think across the supplied agent evidence, do not copy tool text. Answer the question directly in the first sentence, then add only useful context, anomalies, business impact, and a practical recommendation. Sound like a calm, capable human executive speaking to Charl. Use plain language and natural paragraphs, not labels such as Verified facts or Inference unless uncertainty truly matters. Distinguish verified facts from inference without exposing JSON, agent internals, capability names, or code. Never invent facts or actions, never request approval for reads, and never claim an action occurred unless evidence proves it."},
            {"role": "user", "content": json.dumps({"goal": plan.get("goal"), "subject": plan.get("subject"), "owner_preferences": plan.get("owner_preferences") or {}, "recent_conversation": plan.get("recent_conversation") or [], "agent_evidence": safe_evidence, "deterministic_fallback": fallback})},
        ],
    }
    source = environ if environ is not None else __import__("os").environ
    request = urllib.request.Request(
        policy["llm_url"], data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {source.get('OPENAI_API_KEY', '')}", "Content-Type": "application/json"}, method="POST",
    )
    try:
        opener = http_open or urllib.request.urlopen
        with opener(request, timeout=30) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        text = str(parsed["choices"][0]["message"]["content"] or "").strip()
        return text[:3900] if text else fallback
    except Exception:
        return fallback


def _bounded_agent_result(result):
    if not isinstance(result, dict):
        return {}
    allowed = ("direct_answer", "facts", "metrics", "breakdown", "anomalies", "inferences", "recommendations", "unresolved_questions", "sources", "freshness", "confidence", "agent")
    packet = {key: result.get(key) for key in allowed if result.get(key) not in (None, "", [], {})}
    encoded = json.dumps(packet, default=str)
    if len(encoded) <= 12000:
        return packet
    return {key: packet.get(key) for key in ("direct_answer", "facts", "metrics", "anomalies", "recommendations", "freshness", "confidence", "agent") if key in packet}


def context_after_plan(plan, evidence):
    successful = [item for item in evidence if item.get("success")]
    subject = dict(plan.get("subject") or {})
    primary = (successful[0].get("result") or {}) if successful else {}
    active = primary.get("active_missions") or []
    if active:
        subject = {"type": "mission", "mission_id": active[0].get("mission_id"), "title": active[0].get("title")}
    mission = primary.get("mission") if isinstance(primary.get("mission"), dict) else {}
    if mission:
        subject = {"type": "mission", "mission_id": mission.get("mission_id"), "title": mission.get("title")}
    elif primary.get("mission_id"):
        subject = {"type": "mission", "mission_id": primary.get("mission_id")}
    failed = [item for item in evidence if not item.get("success")]
    commitments = [dict(item) for item in (plan.get("existing_commitments") or []) if isinstance(item, dict)]
    for item in successful:
        result = item.get("result") or {}
        if result.get("mission_id"):
            _upsert_commitment(commitments, {
                "type": "core_mission",
                "mission_id": result.get("mission_id"),
                "goal": plan.get("goal"),
                "status": "monitoring",
                "acceptance": plan.get("completion_condition"),
                "next_check": "Read current Supabase mission state before reporting completion.",
            })
        elif result.get("prepared_only"):
            _upsert_commitment(commitments, {
                "type": "prepared_domain_work",
                "goal": plan.get("goal"),
                "status": "awaiting_owner_review",
                "next_check": "Verify the prepared artifact and current source state before execution.",
            })
        mission = result.get("mission") if isinstance(result.get("mission"), dict) else {}
        if mission.get("mission_id") and mission.get("status") in {"done", "merged", "deployed", "rejected"}:
            _upsert_commitment(commitments, {"type": "core_mission", "mission_id": mission.get("mission_id"), "goal": plan.get("goal"), "status": "completed", "completed_state": mission.get("status")})
    return {
        "version": "charlie_private_context_v2",
        "goal": plan.get("goal"),
        "stage": "verified" if successful and not failed else "needs_follow_up",
        "active_subject": subject,
        "last_intent": plan.get("intent_type"),
        "last_plan": {"tools": [step.get("intent_type") for step in plan.get("tools") or []], "completion_condition": plan.get("completion_condition")},
        "last_evidence": [{"tool": item.get("tool"), "success": item.get("success"), "status": item.get("status"), "source_of_truth": item.get("source_of_truth"), "observed_at": item.get("observed_at")} for item in evidence],
        "pending_follow_ups": ([{"reason": "authoritative_tool_failed", "tools": [item.get("tool") for item in failed]}] if failed else []),
        "commitments": commitments[-20:],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _subject(intent_type, args, context):
    mission_id = str(args.get("mission_id") or "").strip()
    if mission_id:
        return {"type": "mission", "mission_id": mission_id}
    if args.get("order_id"):
        return {"type": "order", "order_id": args.get("order_id")}
    existing = context.get("open_context") if isinstance(context.get("open_context"), dict) else {}
    active = existing.get("active_subject") if isinstance(existing.get("active_subject"), dict) else {}
    if intent_type == "read_mission" and active.get("mission_id"):
        return active
    return {"type": "core" if intent_type in {"read_core_status", "read_queue", "read_blocked", "executive_brief"} else intent_type.removeprefix("read_")}


def _tool_args(intent_type, args, subject):
    if intent_type == "read_mission":
        return {"mission_id": args.get("mission_id") or subject.get("mission_id")}
    return dict(args)


def _goal(owner_text, intent_type, subject):
    if intent_type in {"read_core_status", "executive_brief"}:
        return "Give Charl a verified operational picture of CORE and identify only decisions that genuinely need him."
    if intent_type == "read_mission":
        return f"Explain the current state and next action for mission {subject.get('mission_id') or ''}.".strip()
    return str(owner_text or f"Complete {intent_type}")[:1000]


def _upsert_commitment(commitments, new_item):
    key = (new_item.get("type"), new_item.get("mission_id") or new_item.get("goal"))
    for index, item in enumerate(commitments):
        if (item.get("type"), item.get("mission_id") or item.get("goal")) == key:
            commitments[index] = {**item, **new_item}
            return
    commitments.append(new_item)
