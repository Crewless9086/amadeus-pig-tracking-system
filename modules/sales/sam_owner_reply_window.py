"""Authoritative, no-send WhatsApp reply-window evaluation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo


WINDOW_HOURS = 24
DEFAULT_WARNING_HOURS = 6
DEFAULT_URGENT_HOURS = 2
WARNING_ENV = "SAM_OWNER_INBOX_WINDOW_WARNING_HOURS"
URGENT_ENV = "SAM_OWNER_INBOX_WINDOW_URGENT_HOURS"
CONTRACT_VERSION = "sam_owner_reply_window_v1"
JOHANNESBURG = ZoneInfo("Africa/Johannesburg")
WINDOW_STATES = {
    "open", "approaching_expiry", "expired", "unavailable", "not_applicable",
}
AUTHORITY_FLAGS = {
    "sends_customer_message": False,
    "changes_conversation_ownership": False,
    "calls_telegram": False,
    "uses_template": False,
    "mutates_business_state": False,
}


class ReplyWindowEvidenceError(ValueError):
    pass


def evaluate_reply_window(
    messages: Iterable[Mapping[str, Any]],
    *,
    conversation_identity: Mapping[str, Any],
    provider_evidence: Mapping[str, Any] | None = None,
    suspicious_link_evidence: bool | None = None,
    now: datetime | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Evaluate window truth without inspecting customer content."""
    now = _aware(now or datetime.now(timezone.utc))
    source = environ if environ is not None else os.environ
    warning_hours, urgent_hours = thresholds(source)
    identity = _identity(conversation_identity)
    provider = _provider_classification(conversation_identity, provider_evidence or {})
    rows = [_message_metadata(row) for row in list(messages or [])]
    public = sorted(
        [row for row in rows if row is not None and row["public"]],
        key=lambda row: (row["created_at_utc"], _numeric(row["message_id"])),
    )
    inbound = [row for row in public if row["direction"] == "incoming"]
    outgoing = [row for row in public if row["direction"] == "outgoing"]
    latest_inbound = inbound[-1] if inbound else None
    latest_outgoing = outgoing[-1] if outgoing else None

    if not public or not latest_inbound:
        return _result(
            identity, "not_applicable", "not_applicable",
            reason="no_public_inbound", warning_hours=warning_hours,
            urgent_hours=urgent_hours, now=now,
        )
    if latest_outgoing and latest_outgoing["created_at_utc"] > latest_inbound["created_at_utc"]:
        return _result(
            identity, "not_applicable", "not_applicable",
            reason="authoritative_later_owner_reply", warning_hours=warning_hours,
            urgent_hours=urgent_hours, now=now,
            latest_inbound=latest_inbound,
        )
    if provider not in {"genuine_whatsapp", "genuine_webwidget"}:
        return _result(
            identity, "unavailable", "unavailable",
            reason="whatsapp_provider_identity_unavailable",
            warning_hours=warning_hours, urgent_hours=urgent_hours, now=now,
            latest_inbound=latest_inbound, provider_identity=provider,
        )
    conflict = _provider_conflict(provider_evidence or {}, latest_inbound)
    if conflict:
        return _result(
            identity, "unavailable", "unavailable", reason=conflict,
            warning_hours=warning_hours, urgent_hours=urgent_hours, now=now,
            latest_inbound=latest_inbound, provider_identity=provider,
        )

    if provider == "genuine_webwidget":
        result = _result(
            identity, "not_applicable", "ordinary_reply_allowed",
            reason="webwidget_reply_channel_open",
            warning_hours=warning_hours, urgent_hours=urgent_hours, now=now,
            latest_inbound=latest_inbound, provider_identity=provider,
        )
        result["ordinary_reply_allowed"] = True
        result["send_reply_action_visible"] = True
        return result

    expiry = latest_inbound["created_at_utc"] + timedelta(hours=WINDOW_HOURS)
    remaining_seconds = max(0, int((expiry - now).total_seconds()))
    raw_remaining_seconds = int((expiry - now).total_seconds())
    suspicious = suspicious_link_evidence is True
    attachment_present = bool(latest_inbound["attachment_present"])
    if suspicious:
        state = "open" if raw_remaining_seconds > 0 else "expired"
        reply_state = "customer_reply_prohibited"
        reason = "suspected_malicious_link"
        alert_band = "withheld"
    elif raw_remaining_seconds <= 0:
        state = "expired"
        reply_state = "template_required"
        reason = "provider_reply_window_expired"
        alert_band = "missed_window"
    elif raw_remaining_seconds <= urgent_hours * 3600:
        state = "approaching_expiry"
        reply_state = "ordinary_reply_allowed"
        reason = "urgent_reply_window"
        alert_band = "urgent"
    elif raw_remaining_seconds <= warning_hours * 3600:
        state = "approaching_expiry"
        reply_state = "ordinary_reply_allowed"
        reason = "reply_window_warning"
        alert_band = "warning"
    else:
        state = "open"
        reply_state = "ordinary_reply_allowed"
        reason = "reply_window_open"
        alert_band = "none"
    if attachment_present and reply_state == "ordinary_reply_allowed":
        reply_state = "customer_reply_prohibited"
        reason = "unreviewed_attachment"
        alert_band = "withheld"

    result = _result(
        identity, state, reply_state, reason=reason,
        warning_hours=warning_hours, urgent_hours=urgent_hours, now=now,
        latest_inbound=latest_inbound, provider_identity=provider,
        expiry=expiry, remaining_seconds=remaining_seconds,
        alert_band=alert_band,
    )
    result["ordinary_reply_allowed"] = reply_state == "ordinary_reply_allowed"
    result["send_reply_action_visible"] = reply_state == "ordinary_reply_allowed"
    result["template_required"] = reply_state == "template_required"
    result["suspicious_link_withheld"] = suspicious
    result["attachment_withheld"] = attachment_present
    return result


def prepare_window_alert(
    work_item_id: str,
    observation_hash: str,
    evaluation: Mapping[str, Any],
    *,
    prepared_at: datetime | None = None,
) -> dict[str, Any] | None:
    """Prepare one sanitized, stable alert. This function never delivers it."""
    evaluation = dict(evaluation or {})
    band = str(evaluation.get("alert_band") or "none")
    if band not in {"warning", "urgent", "missed_window", "withheld"}:
        return None
    work_item_id = _clean(work_item_id)
    observation_hash = _clean(observation_hash)
    if not work_item_id or not observation_hash:
        raise ReplyWindowEvidenceError("alert_identity_incomplete")
    canonical = {
        "work_item_id": work_item_id,
        "observation_hash": observation_hash,
        "window_contract_version": CONTRACT_VERSION,
        "window_state": evaluation.get("window_state"),
        "reply_authority_state": evaluation.get("reply_authority_state"),
        "alert_band": band,
        "expires_at_utc": evaluation.get("expires_at_utc"),
        "reason": evaluation.get("reason"),
    }
    alert_hash = _digest(canonical)
    return {
        "alert_event_id": f"SAM-OWNER-WINDOW-ALERT-{alert_hash[:24]}",
        "alert_deduplication_hash": alert_hash,
        **canonical,
        "conversation_id": evaluation.get("conversation_id"),
        "contact_id": evaluation.get("contact_id"),
        "inbox_id": evaluation.get("inbox_id"),
        "prepared_at": _aware(prepared_at or datetime.now(timezone.utc)).isoformat(),
        "delivery_enabled": False,
        "delivered": False,
        "contains_customer_content": False,
        **AUTHORITY_FLAGS,
    }


def thresholds(environ: Mapping[str, str]) -> tuple[int, int]:
    warning = _bounded_hours(environ.get(WARNING_ENV), DEFAULT_WARNING_HOURS)
    urgent = _bounded_hours(environ.get(URGENT_ENV), DEFAULT_URGENT_HOURS)
    if urgent >= warning:
        raise ReplyWindowEvidenceError("reply_window_threshold_order_invalid")
    return warning, urgent


def _result(
    identity: Mapping[str, str],
    window_state: str,
    reply_state: str,
    *,
    reason: str,
    warning_hours: int,
    urgent_hours: int,
    now: datetime,
    latest_inbound: Mapping[str, Any] | None = None,
    provider_identity: str = "unavailable",
    expiry: datetime | None = None,
    remaining_seconds: int | None = None,
    alert_band: str = "none",
) -> dict[str, Any]:
    if window_state not in WINDOW_STATES:
        raise ReplyWindowEvidenceError("reply_window_state_invalid")
    latest_inbound = dict(latest_inbound or {})
    evidence = {
        "window_contract_version": CONTRACT_VERSION,
        **identity,
        "window_state": window_state,
        "reply_authority_state": reply_state,
        "reason": reason,
        "provider_identity_class": provider_identity,
        "latest_inbound_message_id": latest_inbound.get("message_id", ""),
        "latest_inbound_at_utc": _iso(latest_inbound.get("created_at_utc")),
        "evaluated_at_utc": now.isoformat(),
        "expires_at_utc": _iso(expiry),
        "expires_at_johannesburg": _iso(expiry.astimezone(JOHANNESBURG)) if expiry else None,
        "remaining_seconds": remaining_seconds,
        "remaining_minutes": (
            max(0, remaining_seconds // 60) if isinstance(remaining_seconds, int) else None
        ),
        "warning_threshold_hours": warning_hours,
        "urgent_threshold_hours": urgent_hours,
        "alert_band": alert_band,
        "ordinary_reply_allowed": False,
        "send_reply_action_visible": False,
        "template_required": reply_state == "template_required",
        "suspicious_link_withheld": False,
        "attachment_withheld": False,
        "contains_customer_content": False,
        **AUTHORITY_FLAGS,
    }
    evidence["window_evidence_hash"] = _digest({
        key: evidence.get(key) for key in (
            "window_contract_version", "account_id", "conversation_id",
            "contact_id", "inbox_id", "window_state", "reply_authority_state",
            "reason", "provider_identity_class", "latest_inbound_message_id",
            "latest_inbound_at_utc", "expires_at_utc",
            "warning_threshold_hours", "urgent_threshold_hours",
        )
    })
    return evidence


def _identity(value: Mapping[str, Any]) -> dict[str, str]:
    value = dict(value or {})
    identity = {
        key: _clean(value.get(key))
        for key in ("account_id", "conversation_id", "contact_id", "inbox_id")
    }
    if any(not item for item in identity.values()):
        raise ReplyWindowEvidenceError("reply_window_identity_incomplete")
    return identity


def _provider_classification(
    conversation: Mapping[str, Any], evidence: Mapping[str, Any]
) -> str:
    inbox = conversation.get("inbox") if isinstance(conversation.get("inbox"), Mapping) else {}
    evidence_class = _provider_class(evidence.get("provider_identity_class"))
    conversation_classes = {
        value
        for raw in (
            conversation.get("channel"),
            conversation.get("channel_type"),
            inbox.get("channel_type"),
        )
        if (value := _provider_class(raw)) not in {"", "transport_only"}
    }
    if evidence_class == "conflicting" or len(conversation_classes) > 1:
        return "conflicting"
    if evidence_class and evidence_class != "transport_only":
        if conversation_classes and evidence_class not in conversation_classes:
            return "conflicting"
        return evidence_class
    if not conversation_classes:
        return "unavailable"
    return next(iter(conversation_classes))


def _provider_class(value: Any) -> str:
    value = _clean(value).lower()
    if not value:
        return ""
    if value in {
        "channel::whatsapp", "chatwoot_whatsapp", "genuine_whatsapp", "whatsapp",
    }:
        return "genuine_whatsapp"
    if value in {
        "channel::webwidget", "chatwoot_webwidget", "genuine_webwidget",
        "webwidget", "website",
    }:
        return "genuine_webwidget"
    if value in {"chatwoot", "api", "webhook"}:
        return "transport_only"
    if value in {
        "channel::facebookpage", "chatwoot_facebook", "facebook", "messenger",
        "channel::instagram", "chatwoot_instagram", "instagram",
        "channel::email", "chatwoot_email", "email",
    }:
        return "non_whatsapp"
    return "conflicting"


def _provider_conflict(
    evidence: Mapping[str, Any], latest_inbound: Mapping[str, Any]
) -> str:
    bound = evidence.get("identity_binding")
    bound = bound if isinstance(bound, Mapping) else evidence
    expected = evidence.get("expected_identity")
    expected = expected if isinstance(expected, Mapping) else {}
    for key in ("account_id", "conversation_id", "contact_id", "inbox_id"):
        actual_value = _clean(bound.get(key))
        expected_value = _clean(expected.get(key))
        if actual_value and expected_value and actual_value != expected_value:
            return f"provider_{key}_conflict"
        if expected_value and not actual_value:
            return f"provider_{key}_unbound"
    message_id = _clean(evidence.get("latest_inbound_message_id"))
    timestamp = evidence.get("latest_inbound_at_utc")
    if message_id and message_id != latest_inbound["message_id"]:
        return "provider_latest_inbound_identity_conflict"
    if timestamp:
        try:
            canonical = _timestamp(timestamp)
        except ReplyWindowEvidenceError:
            return "provider_latest_inbound_timestamp_invalid"
        # Chatwoot's conversation/message API exposes epoch-second precision,
        # while its webhook can carry fractional seconds for the same exact
        # message. The message ID remains the primary identity; accept only a
        # sub-second representation difference for that already-bound event.
        if abs((canonical - latest_inbound["created_at_utc"]).total_seconds()) >= 1:
            return "provider_latest_inbound_timestamp_conflict"
    return ""


def _message_metadata(row: Any) -> dict[str, Any] | None:
    if not isinstance(row, Mapping):
        raise ReplyWindowEvidenceError("reply_window_message_shape_invalid")
    message_type = str(row.get("message_type") if row.get("message_type") is not None else "")
    if message_type in {"2", "activity"}:
        return None
    direction = _clean(row.get("direction")).lower()
    if not direction:
        direction = {"0": "incoming", "1": "outgoing"}.get(message_type, "")
    if direction not in {"incoming", "outgoing"}:
        raise ReplyWindowEvidenceError("reply_window_message_direction_invalid")
    message_id = _clean(row.get("id") or row.get("message_id"))
    if not message_id:
        raise ReplyWindowEvidenceError("reply_window_message_identity_missing")
    attachments = row.get("attachments")
    if attachments is not None and not isinstance(attachments, list):
        raise ReplyWindowEvidenceError("reply_window_attachment_shape_invalid")
    return {
        "message_id": message_id,
        "direction": direction,
        "created_at_utc": _timestamp(row.get("created_at")),
        "public": row.get("private") is not True,
        "attachment_present": bool(attachments),
    }


def _timestamp(value: Any) -> datetime:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return _aware(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
        except ValueError as exc:
            raise ReplyWindowEvidenceError("reply_window_timestamp_invalid") from exc
    if isinstance(value, datetime):
        return _aware(value)
    raise ReplyWindowEvidenceError("reply_window_timestamp_missing")


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ReplyWindowEvidenceError("reply_window_timestamp_timezone_missing")
    return value.astimezone(timezone.utc)


def _bounded_hours(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(str(value))
    except ValueError as exc:
        raise ReplyWindowEvidenceError("reply_window_threshold_invalid") from exc
    if not 1 <= parsed <= 23:
        raise ReplyWindowEvidenceError("reply_window_threshold_out_of_range")
    return parsed


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _clean(value: Any, limit: int = 200) -> str:
    return str(value if value is not None else "").strip()[:limit]


def _numeric(value: str) -> tuple[int, str]:
    return (int(value), value) if str(value).isdigit() else (0, str(value))


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest().upper()
