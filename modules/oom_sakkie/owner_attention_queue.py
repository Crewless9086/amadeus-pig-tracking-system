"""I/O-free contracts for Oom Sakkie's consolidated owner attention queue.

The kernel returns instructions only. Existing authenticated adapters must atomically
consume owner decisions, persist their receipt, and edit the existing Telegram card.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


SUMMARY_STATES = frozenset({"new_enquiry", "automatically_answered", "qualification_progress", "awaiting_customer", "owner_decision"})
PROTECTED_AUTHORITIES = frozenset({"special_price", "delivery_commitment", "reservation", "allocation", "binding_quote", "order", "payment", "farm_collection_exception"})
SYSTEM_STATES = frozenset({"healthy", "disabled", "systemically_contained", "chronology_unavailable"})
BINDING_KEYS = ("account_id", "inbox_id", "contact_id", "conversation_id", "latest_inbound_id", "evidence_packet_hash", "requested_authority")
_OPAQUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")
_CHOICE = re.compile(r"^[a-z][a-z0-9_]{0,23}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_WORK_LABELS = {
    "current_livestock_inbox": "current livestock inbox",
    "current_eligible_enquiries": "current eligible enquiries",
    "authoritative_chronology": "authoritative conversation chronology",
}
_COVER_LABELS = {
    "sam_disabled": "SAM is disabled; the named work needs owner-assigned manual coverage",
    "systemic_containment": "SAM is contained; the named work needs owner-assigned manual coverage",
    "chronology_unavailable": "authoritative chronology is unavailable; do not answer until restored",
    "no_manual_cover_safe": "no manual customer action is safe or required while the system recovers",
}


def build_owner_attention_queue(observations: Iterable[Mapping[str, Any]], *, period_start: str, period_end: str,
                                sam_state: Mapping[str, Any] | None = None, existing_summary: Mapping[str, Any] | None = None,
                                existing_decision_ids: Iterable[str] = (), existing_alert_ids: Iterable[str] = (),
                                now: str | datetime | None = None) -> dict[str, Any]:
    """Select each conversation's latest proven state and prepare bounded intents."""
    generated = _time(now)
    start, end = _time(period_start), _time(period_end)
    if end <= start or generated < end:
        raise ValueError("period must be complete at generation time")

    latest: dict[tuple[str, ...], dict[str, Any]] = {}
    for raw in observations:
        item = _observation(raw, start, end, generated)
        key = tuple(item[k] for k in ("account_id", "inbox_id", "contact_id", "conversation_id"))
        prior = latest.get(key)
        if prior is None:
            latest[key] = item
        else:
            prior_sequence, item_sequence = prior["chronology_sequence"], item["chronology_sequence"]
            if prior_sequence == item_sequence:
                if _digest(item) != _digest(prior):
                    raise ValueError("conflicting observations at the same chronology position")
                continue
            older, newer = (prior, item) if prior_sequence < item_sequence else (item, prior)
            if _time(newer["observed_at"]) < _time(older["observed_at"]) or _time(newer["latest_inbound_at"]) < _time(older["latest_inbound_at"]):
                raise ValueError("conversation chronology rollback")
            if item_sequence > prior_sequence:
                latest[key] = item

    counts = {state: 0 for state in SUMMARY_STATES}
    cards: list[dict[str, Any]] = []
    known = {_safe_id(v, "existing decision id") for v in existing_decision_ids}
    for item in sorted(latest.values(), key=lambda value: tuple(value[k] for k in ("account_id", "inbox_id", "contact_id", "conversation_id"))):
        counts[item["status"]] += 1
        if item["status"] == "owner_decision":
            card = _decision_card(item, generated)
            if card["decision_id"] not in known:
                cards.append(card)
                known.add(card["decision_id"])

    system = sam_state or {"state": "healthy"}
    system_status = str(system.get("state") or "healthy").strip()
    if system_status not in SYSTEM_STATES:
        raise ValueError("unsupported SAM system state")
    summary_id = _digest({"kind": "sam_sales_status", "period_start": start.isoformat(), "period_end": end.isoformat()})
    existing_id = str((existing_summary or {}).get("summary_id") or "")
    existing_message = _optional_id((existing_summary or {}).get("telegram_message_id"), "summary message id") if existing_id == summary_id else ""
    summary = {
        "summary_id": summary_id, "period_start": start.isoformat(), "period_end": end.isoformat(),
        "counts": {"new_enquiries": counts["new_enquiry"], "automatically_answered_customers": counts["automatically_answered"],
                   "qualification_progress": counts["qualification_progress"], "awaiting_customers": counts["awaiting_customer"],
                   "genuine_owner_decisions": counts["owner_decision"], "systemic_failures": int(system_status != "healthy")},
        "telegram_intent": "edit_existing_summary" if existing_message else "create_period_summary",
        "telegram_message_id": existing_message, "buttons": [],
    }
    return {"version": "oom_sakkie_owner_attention_queue_v2", "generated_at": generated.isoformat(), "summary": summary,
            "decision_cards": cards, "system_alerts": _system_alerts(system, set(existing_alert_ids)),
            "ordinary_individual_notifications": [], "authority": _zero_authority()}


def reassess_decision_card(card: Mapping[str, Any], current_binding: Mapping[str, Any], *, expected_card_digest: str,
                           now: str | datetime | None = None) -> dict[str, Any]:
    """Prepare removal of buttons if trusted card, evidence, chronology, or time changed."""
    valid = _validated_card(card, expected_card_digest)
    current = _binding(current_binding)
    expired = _time(now) >= _time(valid["expires_at"])
    changed = not hmac.compare_digest(_digest(valid["binding"]), _digest(current))
    if not expired and not changed:
        return {"status": "decision_current", "edit_intent": None, "authority": _zero_authority()}
    return {"status": "decision_expired", "edit_intent": {"intent": "edit_existing_decision_card",
            "telegram_message_id": valid["telegram_message_id"], "decision_id": valid["decision_id"], "state": "expired",
            "reason_code": "expired" if expired else "chronology_or_evidence_changed", "buttons": [],
            "next_follow_up_owner": "SAM Livestock", "next_follow_up_trigger": "reassess_current_chronology_and_evidence"},
            "authority": _zero_authority()}


def consume_decision_card(card: Mapping[str, Any], *, choice: str, actor_identity_hash: str,
                          expected_owner_identity_hash: str, expected_card_digest: str,
                          current_binding: Mapping[str, Any], existing_consumption_receipt: Mapping[str, Any] | None = None,
                          now: str | datetime | None = None) -> dict[str, Any]:
    """Prepare (never execute) an adapter-side atomic compare-and-consume operation."""
    actor = _hash(actor_identity_hash, "actor identity hash")
    owner = _hash(expected_owner_identity_hash, "expected owner identity hash")
    if not hmac.compare_digest(actor, owner):
        raise ValueError("authenticated actor is not the bound owner")
    valid = _validated_card(card, expected_card_digest)
    choice_id = _choice_id(choice)
    choices = {item["id"]: item for item in valid["choices"]}
    if choice_id not in choices:
        raise ValueError("choice is not actionable for this decision")
    replay_key = _digest({"card_digest": valid["card_digest"], "choice": choice_id, "actor_identity_hash": actor})
    if existing_consumption_receipt is not None:
        receipt = _receipt(existing_consumption_receipt)
        if any((receipt["replay_key"] != replay_key, receipt["decision_id"] != valid["decision_id"],
                receipt["card_digest"] != valid["card_digest"], receipt["choice_id"] != choice_id,
                receipt["actor_identity_hash"] != actor)):
            raise ValueError("consumption receipt does not match this decision")
        return {"status": "decision_replay_noop", "receipt_id": receipt["receipt_id"], "writes_performed": 0,
                "telegram_calls_performed": 0, "authority": _zero_authority()}
    freshness = reassess_decision_card(card, current_binding, expected_card_digest=expected_card_digest, now=now)
    if freshness["status"] != "decision_current":
        return {**freshness, "writes_performed": 0, "telegram_calls_performed": 0}
    return {"status": "decision_consumption_intent_prepared", "atomic_consumption_intent": {
                "operation": "existing_owner_decision_compare_and_consume", "decision_id": valid["decision_id"],
                "card_digest": valid["card_digest"], "choice_id": choice_id, "actor_identity_hash": actor,
                "binding_digest": _digest(_binding(current_binding)), "replay_key": replay_key,
                "consumed_at": _time(now).isoformat(), "requires_atomic_unique_receipt": True},
            "post_receipt_edit": {"operation": "build_resolved_card_edit", "telegram_message_id": valid["telegram_message_id"]},
            "writes_performed": 0, "telegram_calls_performed": 0, "authority": _zero_authority()}


def build_resolved_card_edit(card: Mapping[str, Any], receipt: Mapping[str, Any], *, expected_card_digest: str,
                             expected_owner_identity_hash: str, expected_replay_key: str) -> dict[str, Any]:
    """Prepare the in-place, buttonless edit only after an authoritative receipt."""
    valid, proven = _validated_card(card, expected_card_digest), _receipt(receipt)
    owner = _hash(expected_owner_identity_hash, "expected owner identity hash")
    replay_key = _hash(expected_replay_key, "expected replay key")
    if any((proven["card_digest"] != valid["card_digest"], proven["decision_id"] != valid["decision_id"],
            proven["actor_identity_hash"] != owner, proven["replay_key"] != replay_key)):
        raise ValueError("receipt is not bound to this card")
    choice = next((item for item in valid["choices"] if item["id"] == proven["choice_id"]), None)
    if choice is None:
        raise ValueError("receipt choice is not valid for this card")
    return {"status": "resolved_card_edit_intent_prepared", "edit_intent": {"intent": "edit_existing_decision_card",
            "telegram_message_id": valid["telegram_message_id"], "decision_id": valid["decision_id"], "state": "resolved",
            "outcome_code": choice["outcome_code"], "buttons": [], "next_follow_up_owner": "SAM Livestock",
            "next_follow_up_trigger": choice["follow_up_trigger_code"]}, "telegram_calls_performed": 0,
            "writes_performed": 0, "authority": _zero_authority()}


def _observation(raw: Mapping[str, Any], start: datetime, end: datetime, generated: datetime) -> dict[str, Any]:
    status = str(raw.get("status") or "").strip()
    if status not in SUMMARY_STATES:
        raise ValueError("unsupported sales attention status")
    item = {key: _safe_id(raw.get(key), key) for key in ("account_id", "inbox_id", "contact_id", "conversation_id", "latest_inbound_id")}
    item["status"] = status
    item["observed_at"] = _time(raw.get("observed_at")).isoformat()
    item["latest_inbound_at"] = _time(raw.get("latest_inbound_at")).isoformat()
    item["chronology_sequence"] = _nonnegative_int(raw.get("chronology_sequence"), "chronology sequence")
    observed, inbound = _time(item["observed_at"]), _time(item["latest_inbound_at"])
    if not start <= observed < end or inbound > observed or observed > generated:
        raise ValueError("observation chronology is outside the proven period")
    if status == "owner_decision":
        item.update({key: raw.get(key) for key in ("evidence_packet_hash", "requested_authority", "expires_at", "choices", "telegram_message_id")})
    return item


def _chronology(item: Mapping[str, Any]) -> tuple[datetime, int, datetime, str]:
    return (_time(item["observed_at"]), int(item["chronology_sequence"]), _time(item["latest_inbound_at"]), item["latest_inbound_id"])


def _decision_card(item: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    authority = str(item.get("requested_authority") or "").strip()
    if authority not in PROTECTED_AUTHORITIES:
        raise ValueError("owner decision must request a protected authority")
    binding = _binding(item)
    expires = _time(item.get("expires_at"))
    if expires <= now:
        raise ValueError("owner decision is already expired")
    choices = _choices(item.get("choices"), require_actionable=True)
    core = {"binding": binding, "requested_authority": authority, "expires_at": expires.isoformat(), "choices": choices}
    card_digest = _digest(core)
    decision_id = "oaq_" + card_digest[:32]
    buttons = []
    for choice in choices:
        callback = f"sam_owner:{decision_id}:{choice['id']}"
        if len(callback.encode("utf-8")) > 64:
            raise ValueError("Telegram callback exceeds 64 bytes")
        buttons.append({"text_code": choice["label_code"], "callback_data": callback})
    return {**core, "decision_id": decision_id, "card_digest": card_digest, "state": "actionable", "choices": choices,
            "buttons": buttons, "telegram_intent": "create_decision_card",
            "telegram_message_id": _optional_id(item.get("telegram_message_id"), "Telegram message id")}


def _validated_card(card: Mapping[str, Any], expected_digest: str) -> dict[str, Any]:
    trusted = _hash(expected_digest, "expected card digest")
    binding, authority = _binding(card.get("binding") if isinstance(card.get("binding"), Mapping) else {}), str(card.get("requested_authority") or "")
    if authority not in PROTECTED_AUTHORITIES or binding["requested_authority"] != authority:
        raise ValueError("card authority is invalid")
    core = {"binding": binding, "requested_authority": authority, "expires_at": _time(card.get("expires_at")).isoformat(), "choices": _choices(card.get("choices"), require_actionable=False)}
    digest = _digest(core)
    if not hmac.compare_digest(digest, trusted) or str(card.get("card_digest") or "") != digest or str(card.get("decision_id") or "") != "oaq_" + digest[:32]:
        raise ValueError("card digest or identity is invalid")
    return {**core, "card_digest": digest, "decision_id": "oaq_" + digest[:32], "telegram_message_id": _optional_id(card.get("telegram_message_id"), "Telegram message id")}


def _binding(value: Mapping[str, Any]) -> dict[str, str]:
    result = {key: _safe_id(value.get(key), key) for key in BINDING_KEYS if key != "evidence_packet_hash"}
    result["evidence_packet_hash"] = _hash(value.get("evidence_packet_hash"), "evidence packet hash")
    return {key: result[key] for key in BINDING_KEYS}


def _choices(raw: Any, *, require_actionable: bool) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        raise ValueError("owner decision has no actionable choices")
    result, seen = [], set()
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        if require_actionable and item.get("actionable") is not True:
            continue
        if not require_actionable and not all(key in item for key in ("id", "label_code", "outcome_code", "follow_up_trigger_code")):
            continue
        choice = _choice_id(item.get("id"))
        if choice in seen:
            raise ValueError("duplicate decision choice")
        seen.add(choice)
        result.append({"id": choice, "label_code": _choice_id(item.get("label_code")),
                       "outcome_code": _choice_id(item.get("outcome_code")),
                       "follow_up_trigger_code": _choice_id(item.get("follow_up_trigger_code"))})
    if not result or len(result) > 4:
        raise ValueError("owner decision must have one to four actionable choices")
    return sorted(result, key=lambda item: item["id"])


def _system_alerts(state: Mapping[str, Any], existing: set[str]) -> list[dict[str, Any]]:
    status = str(state.get("state") or "healthy").strip()
    if status not in SYSTEM_STATES:
        raise ValueError("unsupported SAM system state")
    if status == "healthy":
        return []
    codes = sorted({_safe_id(value, "affected work code") for value in state.get("affected_work_codes", [])})
    if not codes or any(code not in _WORK_LABELS for code in codes):
        raise ValueError("system alert requires supported affected work codes")
    required = state.get("manual_coverage_required")
    if not isinstance(required, bool):
        raise ValueError("manual coverage required must be a boolean")
    reason = _safe_id(state.get("manual_coverage_reason_code"), "manual coverage reason code")
    if reason not in _COVER_LABELS or (required and reason == "no_manual_cover_safe") or (not required and reason != "no_manual_cover_safe"):
        raise ValueError("manual coverage requirement and reason are inconsistent")
    incident_id = _digest({"state": status, "affected_work_codes": codes, "manual_coverage_required": required, "reason_code": reason})
    known = {_hash(value, "existing alert id") for value in existing}
    if incident_id in known:
        return []
    return [{"alert_id": incident_id, "state": status, "affected_work": [_WORK_LABELS[code] for code in codes],
             "manual_coverage_required": required, "manual_coverage_guidance": _COVER_LABELS[reason],
             "telegram_intent": "create_system_alert", "buttons": [], "customer_decision": False}]


def _receipt(value: Mapping[str, Any]) -> dict[str, str]:
    if value.get("status") != "consumed":
        raise ValueError("decision receipt is not authoritative")
    return {"receipt_id": _safe_id(value.get("receipt_id"), "receipt id"), "decision_id": _safe_id(value.get("decision_id"), "decision id"),
            "card_digest": _hash(value.get("card_digest"), "receipt card digest"), "choice_id": _choice_id(value.get("choice_id")),
            "actor_identity_hash": _hash(value.get("actor_identity_hash"), "receipt actor identity hash"),
            "replay_key": _hash(value.get("replay_key"), "receipt replay key")}


def _safe_id(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not _OPAQUE.fullmatch(text):
        raise ValueError(f"{field} must be a privacy-safe opaque identifier")
    return text


def _optional_id(value: Any, field: str) -> str:
    text = str(value or "").strip()
    return _safe_id(text, field) if text else ""


def _choice_id(value: Any) -> str:
    text = str(value or "").strip()
    if not _CHOICE.fullmatch(text):
        raise ValueError("choice fields must be bounded callback-safe codes")
    return text


def _hash(value: Any, field: str) -> str:
    text = str(value or "").strip().lower()
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{field} must be a SHA-256 hex digest")
    return text


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _time(value: str | datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _zero_authority() -> dict[str, bool]:
    return {"sends_telegram": False, "sends_customer_message": False, "writes_customer_state": False,
            "writes_farm_state": False, "consumes_owner_decision": False}
