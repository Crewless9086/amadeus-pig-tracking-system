"""Authenticated entrypoint for one consolidated Oom Sakkie manager round."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
import os
from typing import Any, Callable
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import wait
import html

from modules.oom_sakkie.farm_manager_loop import (
    Authority, Provenance, SpecialistAvailability, SpecialistResult,
    SpecialistWorkItem, WorkState, build_family_brief,
)
from modules.oom_sakkie.gateway_authority import bind_gateway_owner_authority
from modules.oom_sakkie.herdmaster_management_runtime import consume_current_herdmaster_management
from modules.telemetry.rootline_specialist_result import build_current_rootline_specialist_result

CONTRACT_VERSION = "oom_sakkie_farm_manager_round_v1"
EVENT_SOURCE = "oom_sakkie_farm_manager_round"
SPECIALIST_BUDGET_SECONDS = 12.0
_SPECIALIST_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="oom-manager")
_MANAGER_PHRASES = (
    "what needs our attention", "what needs attention", "farm status",
    "farm priorities", "morning brief", "management plan", "today's work",
    "todays work", "farm-management brief", "farm management brief",
)
_DOMAINS = {
    "herd": ("pig", "herd", "welfare", "breed", "mating", "weigh"),
    "rootline": ("irrigation", "water", "energy", "power", "solar"),
    "sales": ("sale", "sales", "customer", "enquir"),
    "marketing": ("marketing", "facebook", "media", "post"),
}
ZERO_AUTHORITY = {
    "writes_farm_data": False, "writes_weights": False, "writes_mating": False,
    "sends_customers": False, "publishes": False, "hardware_commands": False,
    "protected_actions_performed": False,
}


def is_farm_manager_round(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    if any(phrase in normalized for phrase in _MANAGER_PHRASES):
        return True
    mentioned = sum(any(term in normalized for term in terms) for terms in _DOMAINS.values())
    return mentioned >= 2


def handle_farm_manager_round(parsed: dict[str, Any], authority: Any, *, now=None,
                              loaders: dict[str, Callable] | None = None,
                              event_store=None, weighing_loader=None,
                              specialist_budget_seconds=SPECIALIST_BUDGET_SECONDS):
    if not is_farm_manager_round(parsed.get("text", "")):
        return {"handled": False}, 200
    # The durable manager lifecycle is provider-bound. Legacy/local callers
    # without Telegram chronology continue through the existing read-only tool.
    if not parsed.get("provider_message_id") or not parsed.get("provider_timestamp"):
        return {"handled": False}, 200
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    owner = str(parsed.get("telegram_user_id") or "")
    chat = str(parsed.get("telegram_chat_id") or "")
    bound = bind_gateway_owner_authority(authority, "farm_manager_round")
    if not bound or bound.owner_user_id != owner or bound.private_chat_id != chat:
        return {"handled": False}, 200
    binding = {
        "owner": owner, "chat": chat,
        "provider_message_id": str(parsed.get("provider_message_id") or ""),
        "provider_timestamp": str(parsed.get("provider_timestamp") or ""),
        "content_digest": _digest(str(parsed.get("text") or "")),
        "contract_version": CONTRACT_VERSION,
    }
    mission_id = "OOM-FARM-ROUND-" + _digest({"owner": owner, "chat": chat,
        "provider_message_id": binding["provider_message_id"]}).upper()[:24]
    store = event_store or _event_store
    try:
        prior = store("load", mission_id, None)
    except Exception:
        return {"handled": True, "success": False,
            "status": "farm_manager_round_persistence_unavailable",
            "mission_id": mission_id, **ZERO_AUTHORITY}, 503
    if prior:
        prior_binding = prior.get("binding") or {}
        if prior_binding != binding:
            return {"handled": True, "success": False,
                "status": "farm_manager_provider_binding_conflict",
                "mission_id": mission_id, **ZERO_AUTHORITY}, 409
        preserved = prior.get("result") or {}
        return {**preserved, "status": "farm_manager_round_replay_suppressed"}, 200
    providers = loaders or {
        "herdmaster": lambda: _load_herdmaster(authority, owner, now),
        "rootline": lambda: _load_rootline(now),
        "sam": lambda: _missing("sam", now),
        "beacon": lambda: _missing("beacon", now),
    }
    results = []
    exceptions = {}
    specialists = ("herdmaster", "rootline", "sam", "beacon")
    # Independent specialist evidence loads run concurrently so one slow source
    # cannot consume the synchronous Telegram delivery budget. HERDMASTER may
    # append only its existing idempotent internal consumption audit trace.
    futures = {specialist: _SPECIALIST_EXECUTOR.submit(providers[specialist]) for specialist in specialists}
    done, pending = wait(tuple(futures.values()), timeout=max(0.01, float(specialist_budget_seconds)))
    try:
        for specialist in specialists:
            future = futures[specialist]
            try:
                if future not in done:
                    raise TimeoutError("specialist_delivery_budget_exceeded")
                result = future.result()
                if not isinstance(result, SpecialistResult):
                    raise ValueError("malformed specialist result")
            except Exception:
                result = _missing(specialist, now, SpecialistAvailability.CONTAINED)
                exceptions[specialist] = "specialist_result_unavailable"
            results.append(result)
    finally:
        for future in pending:
            future.cancel()
    try:
        weighing_worklist = tuple((weighing_loader or _load_weighing_worklist)())
        results[0] = _consolidate_herdmaster(results[0], weighing_worklist, weighing_available=True)
    except Exception:
        weighing_worklist = ()
        exceptions["herdmaster_weighing"] = "current_active_on_farm_worklist_unavailable"
        results.append(_missing("herdmaster_weighing", now, SpecialistAvailability.CONTAINED))
        results[0] = _consolidate_herdmaster(results[0], weighing_worklist, weighing_available=False)
    brief = build_family_brief(results, now=now)
    try:
        answer = _render(brief)
    except ValueError:
        return {"handled": True, "success": False,
            "status": "farm_manager_round_render_contained",
            "mission_id": mission_id, **ZERO_AUTHORITY}, 503
    result_digest = _digest({
        "binding": binding, "answer": answer,
        "specialists": [(r.specialist, r.result_id, r.observed_at.isoformat(), r.availability.value) for r in results],
    })
    output = {
        "handled": True, "success": True, "status": "farm_manager_round_ready",
        "specialist_identity": "OOM_SAKKIE", "mission_id": mission_id,
        "card_mission_id": mission_id, "answer": answer, "binding": binding,
        "result_digest": result_digest, "specialist_exceptions": exceptions,
        "specialist_gaps": dict(brief.specialist_gaps),
        "action_count": min(3, len(brief.queue)),
        "question_count": sum(len(values) for values in brief.questions.values()),
        "reassessment_triggers": [f.follow_up_id for f in brief.follow_ups],
        "weighing_worklist": weighing_worklist,
        **ZERO_AUTHORITY,
    }
    recorded = store("record", mission_id, {"binding": binding, "result": output})
    if not isinstance(recorded, dict) or recorded.get("success") is not True:
        return {"handled": True, "success": False,
            "status": "farm_manager_round_persistence_unproven",
            "mission_id": mission_id, **ZERO_AUTHORITY}, 503
    if recorded.get("created") is False:
        winner = store("load", mission_id, None) or {}
        if (winner.get("binding") or {}) != binding:
            return {"handled": True, "success": False,
                "status": "farm_manager_provider_binding_conflict",
                "mission_id": mission_id, **ZERO_AUTHORITY}, 409
        return {**(winner.get("result") or {}),
                "status": "farm_manager_round_replay_suppressed"}, 200
    return output, 200


def _load_herdmaster(authority, owner, now):
    consumed = consume_current_herdmaster_management(
        authority=authority, owner_user_id=owner, now=now,
        retain_replay_result=True)
    result = consumed.get("specialist_result")
    return result if isinstance(result, SpecialistResult) else _missing("herdmaster", now,
        SpecialistAvailability.CONTAINED)


def _load_weighing_worklist():
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("""select pig_id,tag_number from public.current_canonical_pig_state
                where lower(status)='active' and on_farm is true
                order by nullif(regexp_replace(coalesce(tag_number,''),'[^0-9]','','g'),'')::int nulls last,
                         tag_number,pig_id""")
            rows = cursor.fetchall()
    return tuple({"pig_id": str(pig_id), "tag_number": str(tag)} for pig_id, tag in rows)


def _consolidate_herdmaster(result, worklist, *, weighing_available):
    if result.availability is not SpecialistAvailability.AVAILABLE:
        return result
    source_items = tuple(item for item in result.work_items
                         if item.state not in {WorkState.COMPLETED, WorkState.HANDLED})
    provenance = (source_items[0].provenance if source_items else
        Provenance("herdmaster", result.result_id, ("canonical_herdmaster_result",), result.observed_at, 1.0))
    if not weighing_available and not source_items:
        return replace(result, work_items=())
    weighing = (f"Weigh all {len(worklist)} current active/on-farm pigs; capture each tag and kg through the "
        "existing governed bulk-weight flow, then review the exact tag/Pig ID/weight preview and confirm before any write."
        if worklist else ("No current active/on-farm pigs are in today's canonical weighing worklist."
            if weighing_available else "The current active/on-farm weighing list is waiting for canonical evidence."))
    herd_actions = "; ".join(item.next_action for item in source_items)
    item = SpecialistWorkItem(
        item_id=result.result_id + ":daily-herd-round", dedupe_key="herdmaster:daily-herd-round",
        domain="herd", title=(f"Today's weighing, breeding and welfare round ({len(worklist)} pigs to weigh)"
            if weighing_available else "Today's breeding and welfare round; weighing evidence unavailable"),
        why="Fresh weights improve welfare, breeding and supported sales decisions. " +
            "; ".join(item.title + ": " + item.why for item in source_items),
        next_action=weighing + (" Breeding/welfare: " + herd_actions if herd_actions else ""),
        assignee="charl", state=(WorkState.WAITING_EVIDENCE
            if any(item.genuine_question for item in source_items) else WorkState.DUE_TODAY),
        authority=Authority.ADVISORY,
        provenance=provenance, business_value=100,
        genuine_question=next((item.genuine_question for item in source_items if item.genuine_question), ""),
        question_for="charl" if any(item.genuine_question for item in source_items) else "")
    return replace(result, work_items=(item,))


def _load_rootline(now):
    raw = build_current_rootline_specialist_result(operating_date=now.date().isoformat())
    observed = _time(((raw.get("evidence") or {}).get("generated_at") or raw.get("generated_at")), now)
    result_id = str(raw.get("result_id") or raw.get("plan_id") or "rootline-current")
    provenance = Provenance("rootline", result_id, ("canonical_rootline_specialist_result",), observed, 1.0)
    recommendation = str((raw.get("owner_brief") or {}).get("recommend_now") or raw.get("overall_status") or "Needs Data")
    state = WorkState.WAITING_EVIDENCE if "needs data" in recommendation.lower() else WorkState.PLANNED
    item = SpecialistWorkItem(
        item_id=result_id + "-plan", dedupe_key="rootline:daily-plan", domain="water_energy",
        title=f"ROOTLINE: {recommendation}", why="Current power, weather, water and irrigation evidence determine today's safe plan.",
        next_action=str((raw.get("owner_brief") or {}).get("reassess") or "Reassess when canonical evidence changes."),
        assignee="charl", state=state, authority=Authority.ADVISORY, provenance=provenance,
        business_value=80, genuine_question=str((raw.get("owner_brief") or {}).get("family_fact_needed") or ""),
        question_for="charl" if (raw.get("owner_brief") or {}).get("family_fact_needed") else "",
    )
    return SpecialistResult("rootline", result_id, observed,
        SpecialistAvailability.AVAILABLE if raw.get("success") else SpecialistAvailability.CONTAINED,
        work_items=(item,))


def _missing(name, now, availability=SpecialistAvailability.MISSING):
    return SpecialistResult(name, f"{name}-unavailable", now, availability)


def _render(brief):
    labels = {
        WorkState.URGENT: "DO NOW", WorkState.DUE_TODAY: "DO TODAY",
        WorkState.PLANNED: "PLANNED / RECOMMENDED",
        WorkState.WAITING_EVIDENCE: "WAITING FOR EVIDENCE",
        WorkState.PROTECTED_OWNER_DECISION: "PROTECTED DECISION",
    }
    lines = ["<b>OOM SAKKIE — TODAY'S FARM BRIEF</b>"]
    for item in brief.queue[:3]:
        lines += ["", f"<b>{labels[item.state]}</b> — {_clip(item.title, 120)}",
                  _clip(item.why, 300), f"Next: {_clip(item.next_action, 450)}",
                  f"Owner: {_clip(item.assignee.title(), 30)} · Specialist: {_clip(item.provenance.specialist.upper(), 40)}"]
    if brief.specialist_gaps:
        gap_text = ", ".join(f"{k.upper()} ({v})" for k, v in brief.specialist_gaps.items())
        lines += ["", "<b>BOUNDED WAITING</b>", "Unavailable or stale specialist evidence limits only its own conclusion: " + _clip(gap_text, 350) + "."]
    questions = [question for values in brief.questions.values() for question in values]
    if questions:
        lines += ["", "<b>ONE QUESTION</b>", _clip(questions[0], 300)]
    lines += ["", "No weight, mating, farm, customer, publication or hardware action was performed. Weights require an exact tag/Pig ID/weight preview and confirmation; mating and irrigation execution remain separately governed."]
    rendered = "\n".join(lines)
    if len(rendered) > 3900:
        raise ValueError("farm_manager_render_budget_exceeded")
    return rendered


def _clip(value, limit):
    text = " ".join(str(value or "").split())
    escaped = []
    used = 0
    for character in text:
        entity = html.escape(character, quote=False)
        if used + len(entity) > limit:
            return "".join(escaped).rstrip() + "…"
        escaped.append(entity)
        used += len(entity)
    return "".join(escaped)


def _digest(value):
    payload = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _time(value, fallback):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return fallback


def _event_store(action, identity, payload):
    from modules.sales.sam_live_stock_launch_control import (
        build_sam_live_stock_review_event, record_sam_live_stock_review_event,
    )
    if action == "load":
        import psycopg
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
            connection.read_only = True
            with connection.cursor() as cursor:
                cursor.execute("""select review_json->'farm_manager_round'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s and review_event_id=%s limit 1""",
                    (EVENT_SOURCE, identity))
                row = cursor.fetchone()
        return row[0] if row and isinstance(row[0], dict) else None
    event = build_sam_live_stock_review_event({"conversation_id": identity}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "internal_farm_manager_round"},
        event_source=EVENT_SOURCE)
    event.update({"review_event_id": identity, "chatwoot_conversation_id": identity,
        "review_json": {"farm_manager_round": payload}, "decision_json": {}, "facts_json": {},
        "customer_message_excerpt": "", "sam_reply_excerpt": ""})
    saved, status = record_sam_live_stock_review_event(event)
    return {"success": status < 400 and saved.get("success") is True,
            "created": saved.get("created")}
