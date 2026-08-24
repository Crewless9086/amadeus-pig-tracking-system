"""Owner-first projection and append-only event contract for CORE missions."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone


CONTRACT_VERSION = "core_mission_control_event.v1"
EVENT_TYPES = {"finding_recorded", "owner_correction_recorded", "acceptance_recorded"}
REAL_LIFE_STATES = {"prepared", "integrated", "operational", "business_complete", "closed", "contained", "unknown"}
MAX_TEXT = 2000


def validate_mission_control_event(value):
    row = dict(value or {})
    event_type = _text(row.get("event_type"), 50)
    if row.get("contract_version") != CONTRACT_VERSION or event_type not in EVENT_TYPES:
        return False, "invalid_event_contract"
    if not _text(row.get("mission_id"), 90) or not _text(row.get("summary"), MAX_TEXT):
        return False, "mission_id_and_summary_required"
    if event_type == "acceptance_recorded":
        state = _text(row.get("real_life_state"), 40)
        if state not in REAL_LIFE_STATES:
            return False, "invalid_real_life_state"
        if row.get("accepted") not in {True, False}:
            return False, "accepted_boolean_required"
    if event_type == "owner_correction_recorded" and not _text(row.get("corrects_event_id"), 120):
        return False, "corrects_event_id_required"
    return True, "ok"


def build_mission_control_event(mission_id, payload, *, recorded_by, now=None):
    payload = dict(payload or {})
    timestamp = (now or datetime.now(timezone.utc)).isoformat()
    row = {
        "contract_version": CONTRACT_VERSION,
        "mission_id": _text(mission_id, 90),
        "event_type": _text(payload.get("event_type"), 50),
        "summary": _text(payload.get("summary"), MAX_TEXT),
        "recorded_by": _text(recorded_by, 180),
        "recorded_at": timestamp,
        "outcome": _text(payload.get("outcome"), MAX_TEXT),
        "real_life_state": _text(payload.get("real_life_state"), 40),
        "first_missing_acceptance_gate": _text(payload.get("first_missing_acceptance_gate"), MAX_TEXT),
        "current_worker": _text(payload.get("current_worker"), 240),
        "next_automatic_step": _text(payload.get("next_automatic_step"), MAX_TEXT),
        "owner_action": _text(payload.get("owner_action"), MAX_TEXT),
        "corrects_event_id": _text(payload.get("corrects_event_id"), 120),
        "accepted": payload.get("accepted"),
        "evidence_refs": [_text(item, 500) for item in payload.get("evidence_refs", []) if _text(item, 500)][:20],
    }
    valid, reason = validate_mission_control_event(row)
    if not valid:
        raise ValueError(reason)
    supplied = _text(payload.get("idempotency_key"), 200)
    identity = supplied or hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    row["event_id"] = "CORE-MISSION-CONTROL-" + hashlib.sha256(
        f"{row['mission_id']}|{row['event_type']}|{identity}".encode()).hexdigest()[:24].upper()
    return row


def owner_projection(mission, events=()):
    mission = dict(mission or {})
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    cached = metadata.get("mission_control_projection") if isinstance(metadata.get("mission_control_projection"), dict) else {}
    projection = {
        "outcome": _text(cached.get("outcome") or (mission.get("vault") or {}).get("desired_outcome") or mission.get("raw_text"), MAX_TEXT),
        "real_life_state": _text(cached.get("real_life_state"), 40) or _state_from_status(mission.get("status")),
        "first_missing_acceptance_gate": _text(cached.get("first_missing_acceptance_gate"), MAX_TEXT),
        "current_worker": _text(cached.get("current_worker") or (mission.get("vault") or {}).get("current_agent"), 240),
        "latest_finding": _text(cached.get("latest_finding"), MAX_TEXT),
        "next_automatic_step": _text(cached.get("next_automatic_step") or mission.get("selected_next_step"), MAX_TEXT),
        "owner_action": _text(cached.get("owner_action"), MAX_TEXT) or "NONE",
        "latest_event_id": _text(cached.get("latest_event_id"), 120),
    }
    for event in events or ():
        _apply(projection, event)
    return projection


def apply_event_to_projection(mission, event):
    projection = owner_projection(mission)
    _apply(projection, event)
    return projection


def _apply(projection, event):
    row = dict(event or {})
    event_type = row.get("event_type")
    if event_type in EVENT_TYPES:
        projection["latest_event_id"] = _text(row.get("event_id"), 120)
        projection["latest_finding"] = _text(row.get("summary"), MAX_TEXT)
    for key in ("outcome", "real_life_state", "first_missing_acceptance_gate", "current_worker", "next_automatic_step", "owner_action"):
        value = _text(row.get(key), MAX_TEXT)
        if value:
            projection[key] = value


def _state_from_status(status):
    value = _text(status, 40).lower()
    if value in {"merged", "deployed"}: return "integrated"
    if value == "done": return "closed"
    if value in {"blocked", "paused", "rejected"}: return "contained"
    return "prepared" if value else "unknown"


def _text(value, limit):
    return str(value or "").strip()[:limit]
