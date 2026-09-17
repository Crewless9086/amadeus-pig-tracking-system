"""Authenticated, append-only attachment of retained ROOTLINE physical facts."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os

CONTRACT_VERSION = "rootline_physical_acceptance.v1"
EVENT_SOURCE = "rootline_physical_acceptance"
MISSION_ID = "RMQ-20260813-04"
EXPECTED_EXECUTIONS = {
    "ROOTLINE-EXECUTION-79A473B14C98D5E58B9DD2D5": "C12345",
    "ROOTLINE-EXECUTION-8CF9AD2989F15CC5BDC696AE": "B12345",
}


def attach_physical_acceptance(payload, *, owner_principal, execution_loader=None,
                               event_store=None, sender=None, now=None,
                               allowed_owner_ids=None):
    now = _aware(now or datetime.now(timezone.utc))
    packet = _canonical_packet(payload, owner_principal, now, allowed_owner_ids)
    if not packet:
        return _safe("physical_acceptance_binding_invalid"), 400
    execution_loader = execution_loader or _load_completed_execution
    for observation in packet["observations"]:
        execution = execution_loader(observation["execution_id"])
        if not _completed_execution_matches(execution, observation):
            return _safe("physical_acceptance_execution_unproven"), 409
        observation.update({
            "verified_runtime_seconds": 3599,
            "provider_start_state": "ON",
            "provider_shutdown_state": "OFF",
            "shutdown_verified": True,
        })
    packet["acceptance_sha256"] = _digest(packet)
    scope_id = "ROOTLINE-PHYSICAL-" + _digest({
        "mission_id": packet["mission_id"],
        "owner_user_id": packet["owner_user_id"],
        "execution_ids": sorted(row["execution_id"] for row in packet["observations"]),
    })[:24].upper()
    packet["acceptance_id"] = scope_id
    event_store = event_store or _event_store
    prior = event_store("load", scope_id, None)
    if prior:
        if prior.get("acceptance_sha256") != packet["acceptance_sha256"]:
            return _safe("physical_acceptance_conflict"), 409
        return _delivery_result(prior, event_store, sender, replay=True)
    recorded = event_store("record_acceptance", scope_id, packet)
    if not recorded.get("success"):
        return _safe("physical_acceptance_persistence_unproven"), 503
    stored = event_store("load", scope_id, None)
    if not stored or stored.get("acceptance_sha256") != packet["acceptance_sha256"]:
        return _safe("physical_acceptance_persistence_unproven"), 503
    return _delivery_result(stored, event_store, sender, replay=False)


def _delivery_result(packet, event_store, sender, *, replay):
    acceptance_id = packet["acceptance_id"]
    delivered = event_store("load_delivery", acceptance_id, None)
    if delivered and delivered.get("delivery_state") == "confirmed":
        return _result(packet, "physical_acceptance_replayed", replay=True,
                       telegram_sends=0, provider_message_id=delivered.get("provider_message_id")), 200
    claim = event_store("claim_delivery", acceptance_id, {
        "acceptance_id": acceptance_id,
        "acceptance_sha256": packet["acceptance_sha256"],
        "delivery_state": "claimed",
    })
    if claim.get("created") is not True:
        return _safe("physical_acceptance_delivery_unresolved"), 409
    sender = sender or _send_owner_closure
    delivery = sender(packet["private_chat_id"], _closure_text(packet))
    message_id = str((delivery or {}).get("telegram_message_id") or "")
    if (delivery or {}).get("success") is not True or not message_id:
        event_store("record_delivery_ambiguous", acceptance_id, {
            "acceptance_id": acceptance_id, "acceptance_sha256": packet["acceptance_sha256"],
            "delivery_state": "ambiguous",
        })
        return _safe("physical_acceptance_delivery_ambiguous"), 502
    confirmed_result = event_store("record_delivery_confirmed", acceptance_id, {
        "acceptance_id": acceptance_id, "acceptance_sha256": packet["acceptance_sha256"],
        "delivery_state": "confirmed", "provider_message_id": message_id,
    })
    confirmed = event_store("load_delivery", acceptance_id, None)
    if (not confirmed_result.get("success") or not confirmed
            or confirmed.get("delivery_state") != "confirmed"
            or confirmed.get("acceptance_sha256") != packet["acceptance_sha256"]
            or str(confirmed.get("provider_message_id") or "") != message_id):
        return {**_safe("physical_acceptance_delivery_confirmation_persistence_unproven"),
                "provider_delivery_confirmed": True, "provider_message_id": message_id,
                "telegram_sends": 1, "acceptance_persisted": True}, 503
    return _result(packet, "physical_acceptance_recorded_and_delivered", replay=replay,
                   telegram_sends=1, provider_message_id=message_id), 201


def _canonical_packet(payload, principal, now, allowed_owner_ids):
    payload = payload if isinstance(payload, dict) else {}
    owner = str(payload.get("owner_user_id") or "").strip()
    chat = str(payload.get("private_chat_id") or "").strip()
    allowed = set(str(item) for item in (allowed_owner_ids if allowed_owner_ids is not None
                  else _allowed_owner_ids()))
    observed_at = _timestamp(payload.get("observed_at"))
    rows = payload.get("observations")
    if (payload.get("contract_version") != CONTRACT_VERSION
            or payload.get("mission_id") != MISSION_ID or not principal
            or not owner or owner != chat or owner not in allowed
            or payload.get("source") != "control_tower_authenticated_owner_statement"
            or observed_at is None or observed_at > now
            or not isinstance(rows, list) or len(rows) != 2):
        return None
    observations = []
    for row in rows:
        if (not isinstance(row, dict) or not str(row.get("execution_id") or "").strip()
                or str(row.get("zone_id") or "") not in {"B12345", "C12345"}
                or row.get("water_flow") != "normal"
                or row.get("stopped_flow") != "normal"
                or row.get("physically_off_now") is not True):
            return None
        observations.append({key: row[key] for key in (
            "execution_id", "zone_id", "water_flow", "stopped_flow", "physically_off_now")})
    if ({row["zone_id"] for row in observations} != {"B12345", "C12345"}
            or len({row["execution_id"] for row in observations}) != 2
            or {row["execution_id"]: row["zone_id"] for row in observations}
               != EXPECTED_EXECUTIONS):
        return None
    return {"contract_version": CONTRACT_VERSION, "mission_id": MISSION_ID,
            "owner_principal": str(principal), "owner_user_id": owner,
            "private_chat_id": chat, "observed_at": observed_at.isoformat(),
            "source": payload["source"],
            "observations": sorted(observations, key=lambda row: row["zone_id"])}


def _completed_execution_matches(execution, observation):
    return (isinstance(execution, dict)
            and execution.get("execution_id") == observation["execution_id"]
            and execution.get("zone_id") == observation["zone_id"]
            and execution.get("action") == "record_completed"
            and execution.get("state") == "Completed"
            and int(execution.get("verified_runtime_seconds") or 0) == 3599
            and execution.get("shutdown_verified") is True
            and (execution.get("start_evidence") or {}).get("state") == "ON"
            and (execution.get("shutdown_evidence") or {}).get("state") == "OFF")


def _load_completed_execution(execution_id):
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL")) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""select review_json->'rootline_execution'
              from public.sam_live_stock_conversation_review_events
             where event_source='rootline_irrigation_execution'
               and review_json->'rootline_execution'->>'execution_id'=%s
               and review_json->'rootline_execution'->>'action'='record_completed'
             order by created_at desc limit 1""", (execution_id,))
            row = cursor.fetchone()
    return row[0] if row else None


def _event_store(action, identity, payload):
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    from modules.sales.sam_live_stock_launch_control import (
        build_sam_live_stock_review_event, record_sam_live_stock_review_event,
    )
    if action in {"load", "load_delivery"}:
        with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL")) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select review_json->'rootline_physical_acceptance'
                  from public.sam_live_stock_conversation_review_events
                 where event_source=%s and chatwoot_conversation_id=%s
                 order by created_at desc""", (EVENT_SOURCE, identity))
                rows = [row[0] for row in cursor.fetchall()]
        if action == "load":
            return next((row for row in reversed(rows) if row.get("action") == "record_acceptance"), None)
        return next((row for row in rows if row.get("action") in {
            "record_delivery_confirmed", "record_delivery_ambiguous"}), None)
    event_id = identity + ":" + action.upper()
    body = {**dict(payload or {}), "action": action, "event_id": event_id}
    event = build_sam_live_stock_review_event(
        {"conversation_id": identity}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": action},
        event_source=EVENT_SOURCE)
    event.update({"review_event_id": event_id, "chatwoot_conversation_id": identity,
        "review_json": {"rootline_physical_acceptance": body}, "decision_json": {},
        "facts_json": {}, "customer_message_excerpt": "", "sam_reply_excerpt": ""})
    result, status = record_sam_live_stock_review_event(event,
        connect_factory=lambda: connect_bounded_rootline_postgres(
            database_url=os.environ.get("DATABASE_URL"), read_only=False))
    return {**result, "success": status < 400 and result.get("success") is True}


def _send_owner_closure(chat_id, text):
    from modules.oom_sakkie.telegram_direct import send_owner_telegram_reply
    result, _status = send_owner_telegram_reply(chat_id, text)
    return result


def _closure_text(_packet):
    return ("ROOTLINE acceptance complete: C Camp and B Camp irrigated with normal water "
            "flow and both stopped normally. Provider evidence confirmed each shutdown OFF; "
            "Charl confirms both camps are physically OFF now. "
            "Each bounded segment ran exactly once for 3,599 seconds. RMQ-20260813-04 is complete.")


def _allowed_owner_ids():
    raw = str(os.environ.get("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS") or "")
    return {item.strip() for item in raw.replace(";", ",").split(",") if item.strip()}


def _result(packet, status, *, replay, telegram_sends, provider_message_id):
    return {"success": True, "status": status, "acceptance_id": packet["acceptance_id"],
            "acceptance_sha256": packet["acceptance_sha256"], "replay": replay,
            "provider_message_id": provider_message_id, "telegram_sends": telegram_sends,
            "provider_control_calls": 0, "hardware_commands": 0,
            "writes_farm_data": True, "n8n_authority": False,
            "google_sheets_authority": False}


def _safe(status):
    return {"success": False, "status": status, "telegram_sends": 0,
            "provider_control_calls": 0, "hardware_commands": 0,
            "writes_farm_data": False, "n8n_authority": False,
            "google_sheets_authority": False}


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        default=str).encode()).hexdigest()


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return _aware(parsed)
    except (TypeError, ValueError):
        return None


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
