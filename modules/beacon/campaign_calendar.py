"""Deterministic, prepare-only BEACON campaign calendar contracts.

This module deliberately has no database, timer, queue, HTTP, Meta, Chatwoot, or
campaign-execution dependency.  Its outputs are immutable evidence packets for
owner review, never runnable jobs.
"""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PREPARE_ONLY_AUTHORITY = {
    "prepare_only": True,
    "dispatch_enabled": False,
    "posts_publicly": False,
    "sends_customer_message": False,
    "spends_money": False,
    "calls_meta": False,
    "calls_chatwoot": False,
    "calls_n8n": False,
    "creates_order": False,
    "creates_reservation": False,
    "changes_stock": False,
    "writes_farm_data": False,
}

ACTIVE_APPROVAL_STATUS = "approved"
INACTIVE_APPROVAL_STATUSES = {"proposed", "revoked", "expired", "superseded"}
PAUSE_SCOPES = {"global", "rule", "channel", "campaign", "asset", "fulfilment"}


def propose_rule_version(payload, previous_version=None, now=None):
    """Create a content-addressed proposed rule version; never mutate its parent."""
    payload = payload if isinstance(payload, dict) else {}
    previous_version = previous_version if isinstance(previous_version, dict) else {}
    now = _utc(now)
    version = int(previous_version.get("version") or 0) + 1
    rule = {
        "rule_id": _text(payload.get("rule_id") or previous_version.get("rule_id")),
        "version": version,
        "status": "proposed",
        "campaign_lane": _text(payload.get("campaign_lane")),
        "allowed_channels": sorted({_text(v) for v in payload.get("allowed_channels", []) if _text(v)}),
        "timezone": _text(payload.get("timezone")),
        "window_start": _text(payload.get("window_start")),
        "window_end": _text(payload.get("window_end")),
        "demand_unit": _text(payload.get("demand_unit")),
        "expires_at": _text(payload.get("expires_at")),
        "created_at": now.isoformat(),
        "supersedes_version": previous_version.get("version"),
    }
    errors = _rule_definition_errors(rule)
    rule["rule_hash"] = _digest(_rule_content(rule))
    return _result(not errors, "rule_version_proposed" if not errors else "rule_version_invalid", errors, rule=rule)


def approve_rule_version(rule, owner_id, approved_at=None):
    """Return approval evidence only; it cannot create calendar entries."""
    rule = deepcopy(rule) if isinstance(rule, dict) else {}
    errors = _rule_definition_errors(rule)
    if rule.get("status") != "proposed":
        errors.append("rule_status_must_be_proposed")
    if not _text(owner_id):
        errors.append("owner_identity_required")
    if rule.get("rule_hash") != _digest(_rule_content(rule)):
        errors.append("rule_content_hash_mismatch")
    approved_at = _utc(approved_at)
    approved = deepcopy(rule)
    approved.update({
        "status": ACTIVE_APPROVAL_STATUS,
        "approved_by": _text(owner_id),
        "approved_at": approved_at.isoformat(),
        "approval_id": "BEACON-RULE-APPROVAL-" + _digest({
            "rule_hash": rule.get("rule_hash"), "owner": _text(owner_id), "at": approved_at.isoformat()
        })[:20].upper(),
    })
    return _result(not errors, "rule_version_approved" if not errors else "rule_approval_rejected", errors,
                   rule=approved if not errors else rule, calendar_entries=[])


def prepare_calendar_entry(payload, now=None):
    """Validate evidence and return a frozen review entry or fail closed."""
    payload = payload if isinstance(payload, dict) else {}
    now = _utc(now)
    rule = deepcopy(payload.get("rule") or {})
    asset = deepcopy(payload.get("asset") or {})
    demand = deepcopy(payload.get("demand_evidence") or {})
    pauses = deepcopy(payload.get("pauses") or [])
    channel = _text(payload.get("channel"))
    exact_copy = payload.get("exact_copy") if isinstance(payload.get("exact_copy"), str) else ""
    errors = []

    errors.extend(_active_rule_errors(rule, now))
    errors.extend(_asset_errors(asset, rule))
    if not exact_copy or _digest(exact_copy) != _text(payload.get("copy_sha256")):
        errors.append("exact_copy_source_hash_mismatch")
    if channel not in rule.get("allowed_channels", []):
        errors.append("channel_not_allowed")
    window_error = _window_error(rule, now)
    if window_error:
        errors.append(window_error)
    cap, demand_errors = _demand_cap(demand, rule, now)
    errors.extend(demand_errors)
    pause_reasons = _pause_reasons(pauses, rule, asset, channel)
    errors.extend(pause_reasons)
    errors = sorted(set(errors))
    if errors:
        return _result(False, "calendar_entry_preparation_blocked", errors,
                       pause_reasons=pause_reasons, calculated_cap=cap, calendar_entry=None)

    requested = _number(payload.get("requested_target"))
    calculated_cap = min(requested, cap) if requested is not None and requested >= 0 else cap
    snapshot = {
        "rule": rule,
        "approval": {k: rule.get(k) for k in ("approval_id", "approved_by", "approved_at")},
        "asset": asset,
        "copy": {"exact": exact_copy, "sha256": _text(payload.get("copy_sha256")),
                 "source_id": _text(payload.get("copy_source_id"))},
        "channel": channel,
        "timezone": rule.get("timezone"),
        "window_start": rule.get("window_start"),
        "window_end": rule.get("window_end"),
        "demand_evidence": demand,
        "calculated_cap": calculated_cap,
        "pause_result": {"active": False, "reasons": []},
        "prepared_at": now.isoformat(),
    }
    entry_id = "BEACON-CALENDAR-" + _digest(snapshot)[:20].upper()
    entry = {"entry_id": entry_id, "status": "prepared_owner_review", **snapshot,
             "snapshot_sha256": _digest(snapshot), "authority": deepcopy(PREPARE_ONLY_AUTHORITY)}
    return _result(True, "calendar_entry_prepared", [], calendar_entry=entry,
                   calculated_cap=calculated_cap, pause_reasons=[])


def evaluate_prepared_entry(entry, rule_status=None, pauses=None):
    """Re-evaluate revocation/pause state without rewriting historical evidence."""
    entry = deepcopy(entry) if isinstance(entry, dict) else {}
    reasons = []
    if rule_status and rule_status != ACTIVE_APPROVAL_STATUS:
        reasons.append("rule_" + _text(rule_status))
    reasons.extend(_pause_reasons(pauses or [], entry.get("rule", {}), entry.get("asset", {}), entry.get("channel", "")))
    return {"entry": entry, "currently_blocked": bool(reasons), "reasons": sorted(set(reasons)),
            "authority": deepcopy(PREPARE_ONLY_AUTHORITY)}


def _active_rule_errors(rule, now):
    errors = _rule_definition_errors(rule)
    status = rule.get("status")
    if status != ACTIVE_APPROVAL_STATUS:
        errors.append("rule_not_approved" if status not in INACTIVE_APPROVAL_STATUSES else "rule_" + status)
    if not rule.get("approved_by") or not rule.get("approved_at") or not rule.get("approval_id"):
        errors.append("owner_approval_evidence_required")
    if rule.get("rule_hash") != _digest(_rule_content(rule)):
        errors.append("rule_content_hash_mismatch")
    expires = _parse_datetime(rule.get("expires_at"))
    if rule.get("expires_at") and (not expires or expires <= now):
        errors.append("rule_expired")
    return errors


def _rule_definition_errors(rule):
    errors = []
    for key in ("rule_id", "campaign_lane", "timezone", "window_start", "window_end", "demand_unit"):
        if not _text(rule.get(key)):
            errors.append(key + "_required")
    if not rule.get("allowed_channels"):
        errors.append("allowed_channels_required")
    try:
        ZoneInfo(_text(rule.get("timezone")))
    except (ZoneInfoNotFoundError, ValueError):
        errors.append("invalid_iana_timezone")
    return errors


def _asset_errors(asset, rule):
    errors = []
    if asset.get("effective_approval_status") != "approved": errors.append("asset_not_effectively_approved")
    if asset.get("effective_public_use_approved") is not True: errors.append("asset_public_use_not_approved")
    if asset.get("archived") or asset.get("latest_event", {}).get("event_type") == "archived": errors.append("asset_archived")
    if _text(asset.get("privacy_risk")) in {"blocked", "high"}: errors.append("asset_privacy_blocked")
    expected = _text(asset.get("content_sha256"))
    if len(expected) != 64 or expected != _text(asset.get("verified_content_sha256")): errors.append("asset_integrity_unverified")
    lanes = asset.get("sale_stream_relevance") or asset.get("campaign_lanes") or []
    if rule.get("campaign_lane") not in lanes: errors.append("asset_campaign_lane_incompatible")
    return errors


def _window_error(rule, now):
    start, end = _parse_datetime(rule.get("window_start")), _parse_datetime(rule.get("window_end"))
    if not start or not end or start >= end: return "invalid_campaign_window"
    zone_name = _text(rule.get("timezone"))
    try: zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError): return "invalid_iana_timezone"
    if start.utcoffset() is None or end.utcoffset() is None: return "window_offset_required"
    for boundary in (start, end):
        local = boundary.astimezone(zone)
        supplied_wall = boundary.replace(tzinfo=None)
        if local.replace(tzinfo=None) != supplied_wall or local.utcoffset() != boundary.utcoffset():
            return "window_timezone_offset_invalid"
        fold_zero = supplied_wall.replace(tzinfo=zone, fold=0).utcoffset()
        fold_one = supplied_wall.replace(tzinfo=zone, fold=1).utcoffset()
        if fold_zero != fold_one:
            return "window_dst_ambiguous"
    if not (start.astimezone(timezone.utc) <= now < end.astimezone(timezone.utc)): return "outside_campaign_window"
    return ""


def _demand_cap(demand, rule, now):
    errors = []
    if demand.get("unit") != rule.get("demand_unit"): errors.append("demand_unit_mismatch")
    recorded = _parse_datetime(demand.get("recorded_at"))
    max_age = _number(demand.get("max_age_seconds"))
    if not recorded or max_age is None or max_age < 0 or (now - recorded).total_seconds() > max_age: errors.append("demand_evidence_stale")
    if not demand.get("source") or not demand.get("source_record_ids"): errors.append("demand_provenance_required")
    values = [_number(demand.get(k)) for k in ("verified_availability", "commitments", "operational_reserve", "safety_buffer")]
    if any(v is None or v < 0 for v in values): errors.append("demand_values_invalid"); return 0, errors
    cap = max(0, values[0] - values[1] - values[2] - values[3])
    if cap <= 0: errors.append("demand_capacity_zero")
    return cap, errors


def _pause_reasons(pauses, rule, asset, channel):
    reasons = []
    targets = {"global": "*", "rule": rule.get("rule_id"), "channel": channel,
               "campaign": rule.get("campaign_lane"), "asset": asset.get("asset_id"), "fulfilment": rule.get("demand_unit")}
    for pause in pauses if isinstance(pauses, list) else []:
        scope = _text(pause.get("scope"))
        if pause.get("active") is True and scope in PAUSE_SCOPES and _text(pause.get("target")) in {"*", _text(targets[scope])}:
            reasons.append("pause_" + scope + "_" + (_text(pause.get("reason_code")) or "active"))
    return sorted(set(reasons))


def _rule_content(rule):
    return {k: rule.get(k) for k in ("rule_id", "version", "campaign_lane", "allowed_channels", "timezone",
                                      "window_start", "window_end", "demand_unit", "expires_at", "supersedes_version")}


def _result(success, status, errors, **extra):
    return {"success": success, "status": status, "errors": sorted(set(errors)),
            "authority": deepcopy(PREPARE_ONLY_AUTHORITY), **extra}


def _digest(value):
    raw = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _text(value): return str(value or "").strip()
def _number(value):
    try: return float(value)
    except (TypeError, ValueError): return None
def _parse_datetime(value):
    try:
        parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else None
    except ValueError: return None
def _utc(value):
    if isinstance(value, datetime):
        if value.tzinfo is None: raise ValueError("datetime must be timezone-aware")
        return value.astimezone(timezone.utc)
    parsed = _parse_datetime(value)
    return parsed.astimezone(timezone.utc) if parsed else datetime.now(timezone.utc)
