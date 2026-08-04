"""Typed, command-inert dispatch for authenticated operational owner messages."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
import os
from typing import Any, Callable, Mapping

from modules.oom_sakkie.gateway_authority import (
    ROOTLINE_READ_ONLY_TOOL,
    bind_gateway_owner_authority,
    validates_rootline_gateway_authority,
    issue_rootline_observation_write_authority,
)
from modules.oom_sakkie.rootline_commissioning_adapter import accept_supervised_commissioning_presence
from modules.oom_sakkie.rootline_operational_adapter import dispatch_rootline_operation, persist_rootline_observations

CONTRACT_VERSION = "oom_sakkie_operational_specialist_intake_v1"
ROOTLINE_PRESENCE_MAX_AGE_SECONDS = 300
_ROOTLINE_PRESENCE = re.compile(
    r"\bB and C valve area\b.*\bobserve both camps\b.*\bintervene immediately\b.*\bsupervised commissioning\b",
    re.I,
)
_ROOTLINE_OPERATIONAL = re.compile(
    r"\b(reservoir|storage tanks?|water level|[BC]\s*camps?|irrigat(?:e|ion)|needs?\s+(?:water|irrigation))\b",
    re.I,
)
_FRACTION = re.compile(r"\b(reservoir|storage tanks?)\s+(?:is|are)?\s*(\d+)\s*/\s*(\d+)\b", re.I)
_C_NEED = re.compile(r"\bC\s*camps?\b.{0,40}\bneed(?:s|ed)?\s+(?:irrigation|water)\b", re.I)
_C_NO_NEED = re.compile(r"\bC\s*camps?\b.{0,40}\b(?:do(?:es)?\s+not|doesn't|don't|no longer)\s+need", re.I)
ZERO_AUTHORITY = {"writes_farm_data": False, "hardware_commands": 0,
                  "protected_actions_performed": False, "sends_telegram": False}


def handle_operational_specialist_message(
    parsed: Mapping[str, Any], gateway_authority: Any, *, now: datetime | None = None,
    rootline_dispatcher: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = accept_supervised_commissioning_presence,
    rootline_operations_dispatcher: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = dispatch_rootline_operation,
    rootline_observation_writer: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    operation_store=None,
) -> tuple[dict[str, Any], int]:
    text = str((parsed or {}).get("text") or "").strip()
    semantic = parsed.get("semantic") if isinstance(parsed.get("semantic"), Mapping) else {}
    semantic_present = bool(semantic)
    semantic_rootline_observation = (semantic.get("domain") == "rootline"
        and semantic.get("message_kind") in {"observation", "correction"}
        and not semantic.get("needs_clarification"))
    legacy_rootline_observation = not semantic_present and _ROOTLINE_OPERATIONAL.search(text)
    if (semantic_rootline_observation or legacy_rootline_observation) and not _ROOTLINE_PRESENCE.search(text):
        return _handle_rootline_operation(parsed, gateway_authority, rootline_operations_dispatcher,
                                          rootline_observation_writer or persist_rootline_observations, now,
                                          operation_store or _operation_event_store)
    if not _ROOTLINE_PRESENCE.search(text):
        return {"handled": False, "status": "operational_specialist_intake_not_applicable"}, 200
    provider_id = str(parsed.get("provider_message_id") or "").strip()
    provider_at = _time(parsed.get("provider_timestamp"))
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    bound = bind_gateway_owner_authority(gateway_authority, ROOTLINE_READ_ONLY_TOOL)
    if (not provider_id or provider_at is None or not validates_rootline_gateway_authority(bound)
            or bound.owner_user_id != str(parsed.get("telegram_user_id") or "")
            or bound.private_chat_id != str(parsed.get("telegram_chat_id") or "")):
        return _contained(parsed, "operational_specialist_auth_or_chronology_invalid", now), 409
    age = (now - provider_at).total_seconds()
    if age < 0 or age > ROOTLINE_PRESENCE_MAX_AGE_SECONDS:
        result = _contained(parsed, "rootline_physical_presence_stale", now)
        result["answer"] = ("⚠️ <b>ROOTLINE PRESENCE EXPIRED</b>\n\n"
            "I retained your earlier B/C valve-area message, but physical presence is valid for only five minutes. "
            "No hardware action was taken. I will ask again only when ROOTLINE is immediately ready to commission.")
        result["dispatch_state"] = "contained"
        return result, 200
    if rootline_dispatcher is None:
        result = _contained(parsed, "rootline_deployed_adapter_unavailable", now)
        result["answer"] = ("⚠️ <b>ROOTLINE CONTINUATION UNAVAILABLE</b>\n\n"
            "I received and retained your current presence confirmation, but the deployed ROOTLINE adapter did not accept it. "
            "No hardware action was taken; one technical exception is being tracked.")
        return result, 503
    try:
        evidence = dict(rootline_dispatcher({"owner_user_id": str(parsed.get("telegram_user_id") or ""),
            "chat_id": str(parsed.get("telegram_chat_id") or "")}) or {})
    except Exception:
        evidence = {}
    authority = evidence.get("authority") if isinstance(evidence.get("authority"), Mapping) else {}
    if (not evidence or evidence.get("success") is not True
            or str(evidence.get("contract_version") or "") != "rootline_commissioning_continuation_adapter_v1"
            or evidence.get("writes_performed") is not False
            or authority != {"hardware_control": False, "configuration_write": False, "telegram_send": False}
            or type(evidence.get("hardware_commands")) is not int
            or evidence.get("hardware_commands") != 0
            or evidence.get("authorization_current") is not True
            or evidence.get("specialist_acceptance") is not True):
        result = _contained(parsed, "rootline_deployed_adapter_result_invalid", now)
        result["answer"] = ("⚠️ <b>ROOTLINE CONTINUATION CONTAINED</b>\n\n"
            "Your presence confirmation is retained, but safe ROOTLINE acceptance was not proven. No hardware action was taken.")
        return result, 503
    digest = _digest(evidence)
    mission = _mission(parsed)
    return ({"handled": True, "success": True, "status": "working",
        "dispatch_state": "specialist_accepted", "specialist_identity": "ROOTLINE",
        "mission_id": mission, "card_mission_id": mission,
        "provider_message_id": provider_id, "provider_timestamp": provider_at.isoformat(),
        "evidence_generation": str(evidence.get("evidence_cutoff") or evidence.get("observed_at") or ""),
        "adapter_version": CONTRACT_VERSION, "result_digest": digest,
        "answer": ("✅ <b>ROOTLINE PRESENCE RECEIVED</b>\n\n"
            "I retained your current B/C valve-area confirmation and ROOTLINE accepted the read-only continuation. "
            "No hardware command has been issued. ROOTLINE must still preserve every governed safety boundary during the supervised continuation."),
        **ZERO_AUTHORITY}, 200)


def _handle_rootline_operation(parsed, gateway_authority, dispatcher, observation_writer, now, store):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    provider_id = str(parsed.get("provider_message_id") or "").strip()
    provider_at = _time(parsed.get("provider_timestamp"))
    bound = bind_gateway_owner_authority(gateway_authority, ROOTLINE_READ_ONLY_TOOL)
    if (not provider_id or provider_at is None or not validates_rootline_gateway_authority(bound)
            or bound.owner_user_id != str(parsed.get("telegram_user_id") or "")
            or bound.private_chat_id != str(parsed.get("telegram_chat_id") or "")):
        return _contained(parsed, "operational_specialist_auth_or_chronology_invalid", now), 409
    observations = []
    for label, numerator, denominator in _FRACTION.findall(str(parsed.get("text") or "")):
        denominator = int(denominator)
        numerator = int(numerator)
        if denominator < 1 or numerator < 0 or numerator > denominator:
            return _contained(parsed, "rootline_water_observation_invalid", now), 409
        observations.append({
            "kind": "reservoir_level" if label.lower().startswith("reservoir") else "storage_level",
            "value": f"{numerator}/{denominator}", "numerator": numerator, "denominator": denominator,
            "provider_message_id": provider_id, "observed_at": provider_at.isoformat(),
        })
    raw_text = str(parsed.get("text") or "")
    semantic = parsed.get("semantic") if isinstance(parsed.get("semantic"), Mapping) else {}
    visible_need = "C12345" if _C_NEED.search(raw_text) and not _C_NO_NEED.search(raw_text) else None
    semantic_observation = str(semantic.get("observation") or "").strip()
    if not observations and not visible_need and not semantic_observation:
        return {"handled": False, "status": "operational_specialist_intake_not_applicable"}, 200
    mission = _mission(parsed)
    context = {
        "contract_version": "oom_rootline_operational_dispatch_v1",
        "mission_id": mission, "owner_user_id": str(parsed.get("telegram_user_id") or ""),
        "chat_id": str(parsed.get("telegram_chat_id") or ""), "provider_message_id": provider_id,
        "provider_timestamp": provider_at.isoformat(), "observations": observations,
        "visible_irrigation_need_zone": visible_need,
        "semantic_observation": semantic_observation,
        "semantic_intent": str(semantic.get("intent") or "")[:100],
        "content_sha256": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        "authority": {"farm_observation_write": False, "hardware_control": False,
                      "telegram_send": False, "automatic_on_retry": False},
    }
    write_bound=issue_rootline_observation_write_authority(gateway_authority,
        mission_id=mission,provider_message_id=provider_id,provider_timestamp=provider_at.isoformat(),
        content_sha256=context["content_sha256"])
    try:
        prior = list(store("load", mission, None) or [])
    except Exception:
        result = _contained(parsed, "rootline_operational_persistence_unavailable", now)
        result["answer"] = "<b>IRRIGATION FOLLOW-UP CONTAINED</b>\n\nDurable intake storage is unavailable. No ROOTLINE dispatch or irrigation command was attempted."
        return result, 503
    completed = next((row for row in reversed(prior) if row.get("state") == "completed"), None)
    if completed and isinstance(completed.get("outcome"), Mapping):
        if completed.get("context") != context:
            result = _contained(parsed, "rootline_operational_replay_binding_conflict", now)
            result["answer"] = "<b>IRRIGATION FOLLOW-UP CONTAINED</b>\n\nThe provider identity conflicts with the preserved evidence. Nothing was dispatched or changed."
            return result, 409
        return {**dict(completed["outcome"]), "status": "operational_replay_suppressed",
                "replay_suppressed": True, "hardware_commands": 0}, 200
    claimed_prior = next((row for row in reversed(prior) if row.get("state") == "claimed"), None)
    if claimed_prior:
        if claimed_prior.get("context") != context:
            result = _contained(parsed, "rootline_operational_replay_binding_conflict", now)
            result["answer"] = "<b>IRRIGATION FOLLOW-UP CONTAINED</b>\n\nThe provider identity conflicts with the in-progress evidence. Nothing was dispatched or changed."
            return result, 409
        result = _contained(parsed, "rootline_operational_dispatch_in_progress", now)
        result["answer"] = "<b>IRRIGATION FOLLOW-UP IN PROGRESS</b>\n\nThis exact handover is already being processed. No duplicate dispatch or irrigation command was created."
        return result, 202
    claim_id = mission + "-DISPATCH"
    try:
        claimed = store("record", claim_id, {"event_id": claim_id, "mission_id": mission,
            "state": "claimed", "context": context})
    except Exception:
        return _persistence_failed(parsed, now)
    if claimed.get("created") is False or claimed.get("success") is not True:
        result = _contained(parsed, "rootline_operational_dispatch_claim_conflict", now)
        result["answer"] = "<b>IRRIGATION FOLLOW-UP CONTAINED</b>\n\nThe current handover is already being processed. No irrigation command was sent."
        return result, 202
    try:
        observation_result = dict(observation_writer(context, write_bound) or {}) if observation_writer else {}
    except Exception:
        observation_result = {}
    write_truth = _canonical_write_truth(observation_result)
    if (observation_result.get("success") is not True
            or observation_result.get("contract_version") != "rootline_owner_observation_bridge_v1"
            or write_truth is None):
        result = _contained(parsed, "rootline_canonical_observation_bridge_failed", now)
        _apply_write_truth(result, observation_result, write_truth)
        result["answer"] = "<b>ROOTLINE OBSERVATION CONTAINED</b>\n\nThe owner evidence could not be proven in canonical readback. No irrigation command was sent."
        if _record_terminal(store, mission, context, result).get("success") is not True:
            failed, failed_status = _persistence_failed(parsed, now)
            _apply_write_truth(failed, observation_result, write_truth)
            return failed, failed_status
        return result, 503
    if dispatcher is None:
        result = _contained(parsed, "rootline_operational_adapter_unavailable", now)
        result.update({"observations": observations, "visible_irrigation_need_zone": visible_need,
            "answer": ("<b>IRRIGATION FOLLOW-UP CONTAINED</b>\n\n"
                       "I retained the current water and irrigation observation, but ROOTLINE did not accept "
                       "the operational handover. No irrigation command was sent.")})
        _apply_write_truth(result, observation_result, write_truth)
        if _record_terminal(store, mission, context, result).get("success") is not True:
            failed, failed_status = _persistence_failed(parsed, now)
            _apply_write_truth(failed, observation_result, write_truth)
            return failed, failed_status
        return result, 503
    try:
        evidence = dict(dispatcher(context) or {})
    except Exception:
        evidence = {}
    authority = evidence.get("authority") if isinstance(evidence.get("authority"), Mapping) else {}
    expected_authority = {"telegram_send": False, "hardware_control": False,
                          "farm_observation_write": False, "automatic_on_retry": False}
    if (evidence.get("success") is not True
            or evidence.get("contract_version") != "rootline_operational_dispatch_result_v1"
            or evidence.get("specialist_acceptance") is not True
            or authority != expected_authority
            or type(evidence.get("hardware_commands")) is not int
            or evidence.get("hardware_commands") != 0):
        result = _contained(parsed, "rootline_operational_adapter_result_invalid", now)
        result.update({"observations": observations, "visible_irrigation_need_zone": visible_need,
                       "answer": "<b>IRRIGATION DECISION CONTAINED</b>\n\nROOTLINE could not safely validate the current decision. No irrigation command was sent."})
        _apply_write_truth(result, observation_result, write_truth)
        if _record_terminal(store, mission, context, result).get("success") is not True:
            failed, failed_status = _persistence_failed(parsed, now)
            _apply_write_truth(failed, observation_result, write_truth)
            return failed, failed_status
        return result, 503
    digest = _digest({"context": context, "result": evidence})
    recommendation = str(evidence.get("recommendation") or "Needs Data")
    answer = str(evidence.get("owner_answer") or "").strip() or (
        f"<b>ROOTLINE UPDATE</b>\n\nI received the current water observations. "
        f"ROOTLINE's current decision is <b>{recommendation}</b>. No command was sent by this intake step."
    )
    outcome = {"handled": True, "success": True, "status": "specialist_accepted",
        "dispatch_state": "specialist_accepted", "specialist_identity": "ROOTLINE",
        "mission_id": mission, "card_mission_id": mission, "provider_message_id": provider_id,
        "provider_timestamp": provider_at.isoformat(), "observations": observations,
        "visible_irrigation_need_zone": visible_need, "specialist_result": evidence,
        "canonical_observation": observation_result,
        "evidence_generation": str(evidence.get("evidence_generation") or ""),
        "adapter_version": CONTRACT_VERSION, "result_digest": digest, "answer": answer,
        **ZERO_AUTHORITY}
    _apply_write_truth(outcome, observation_result, write_truth)
    complete_id = mission + "-COMPLETED"
    try:
        recorded = store("record", complete_id, {"event_id": complete_id, "mission_id": mission,
            "state": "completed", "context": context, "outcome": outcome})
    except Exception:
        failed, failed_status = _persistence_failed(parsed, now)
        _apply_write_truth(failed, observation_result, write_truth)
        return failed, failed_status
    if recorded.get("success") is not True:
        result = _contained(parsed, "rootline_operational_result_persistence_failed", now)
        result["answer"] = "<b>IRRIGATION FOLLOW-UP CONTAINED</b>\n\nROOTLINE assessed the evidence, but durable completion was not proven. No irrigation command was sent. A separately authorized recovery identity is required."
        _apply_write_truth(result, observation_result, write_truth)
        return result, 503
    return outcome, 200


def _canonical_write_truth(observation_result):
    count = observation_result.get("canonical_writes")
    if type(count) is not int or count not in (0, 1):
        return None
    if count == 1 and not str(observation_result.get("observation_id") or "").strip():
        return None
    return count == 1


def _apply_write_truth(result, observation_result, write_truth):
    result["writes_farm_data"] = write_truth
    result["writes_farm_data_unknown"] = write_truth is None
    result["canonical_observation_id"] = observation_result.get("observation_id")
    result["canonical_observation"] = observation_result


def _operation_event_store(action, identity, payload):
    if not str(os.environ.get("DATABASE_URL") or "").strip():
        raise RuntimeError("durable_rootline_operational_store_required")
    import psycopg
    event_source = "oom_sakkie_rootline_operational_intake"
    if action == "load":
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
            connection.read_only = True
            with connection.cursor() as cursor:
                cursor.execute("""select review_json->'rootline_operational_intake'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s and review_json->'rootline_operational_intake'->>'mission_id'=%s
                    order by created_at,review_event_id""", (event_source, identity))
                return [row[0] for row in cursor.fetchall()]
    from modules.sales.sam_live_stock_launch_control import build_sam_live_stock_review_event, record_sam_live_stock_review_event
    event = build_sam_live_stock_review_event({"conversation_id": payload["mission_id"]}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "rootline_operational_intake"},
        event_source=event_source)
    event["review_event_id"] = identity
    event["chatwoot_conversation_id"] = payload["mission_id"]
    event["review_json"] = {"rootline_operational_intake": dict(payload)}
    event["decision_json"] = {}; event["facts_json"] = {}
    event["customer_message_excerpt"] = ""; event["sam_reply_excerpt"] = ""
    result, status = record_sam_live_stock_review_event(event)
    return {**result, "success": status < 400 and result.get("success") is True,
            "created": result.get("created", result.get("success") is True)}


def _record_terminal(store, mission, context, outcome):
    identity = mission + "-COMPLETED"
    try:
        return store("record", identity, {"event_id": identity, "mission_id": mission,
            "state": "completed", "context": context, "outcome": outcome})
    except Exception:
        return {"success": False, "created": False}


def _persistence_failed(parsed, now):
    result = _contained(parsed, "rootline_operational_result_persistence_failed", now)
    result["answer"] = "<b>IRRIGATION FOLLOW-UP CONTAINED</b>\n\nDurable lifecycle completion was not proven. No irrigation command was sent. A separately authorized recovery identity is required."
    return result, 503


def _contained(parsed, reason, now):
    mission = _mission(parsed)
    return {"handled": True, "success": False, "status": "contained",
        "systemic_exception": reason, "dispatch_state": "contained",
        "specialist_identity": "ROOTLINE", "mission_id": mission, "card_mission_id": mission,
        "provider_message_id": str(parsed.get("provider_message_id") or ""),
        "provider_timestamp": str(parsed.get("provider_timestamp") or ""),
        "adapter_version": CONTRACT_VERSION, "result_digest": _digest({"reason": reason, "mission": mission}),
        "evidence_generation": now.isoformat(), "answer": "", **ZERO_AUTHORITY}


def _mission(parsed):
    return "OOM-ROOTLINE-" + _digest({"owner": str(parsed.get("telegram_user_id") or ""),
        "chat": str(parsed.get("telegram_chat_id") or ""),
        "message": str(parsed.get("provider_message_id") or "")})[:24].upper()


def _time(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return result.astimezone(timezone.utc) if result.tzinfo else None


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
