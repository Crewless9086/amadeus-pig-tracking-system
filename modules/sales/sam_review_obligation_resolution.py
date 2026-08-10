"""Append-only identity and customer-obligation resolution for SAM reviews."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Mapping


CONTRACT_VERSION = "sam_review_obligation_resolution_v1"
TABLE = "sam_review_obligation_resolution_events"
REPRESENTED_STATUSES = {"current", "superseded", "conflicting", "unknown"}
DELIVERY_STATUSES = {
    "not_attempted", "attempt_claimed", "chatwoot_accepted_unverified",
    "provider_delivered", "provider_read", "provider_failed",
    "provider_outcome_ambiguous", "unknown",
}
OBLIGATION_STATUSES = {
    "active_replan_required",
    "delivered_attempt_requires_content_resolution",
    "completed_by_attributable_supported_reply",
    "corrective_replan_required_after_reply",
    "superseded_by_later_inbound",
    "quarantined_no_retry",
    "closed_window_reengagement_required",
    "protected_owner_action_required",
    "unknown_fail_closed",
}
RESOLUTION_ACTIONS = {
    "active", "completed", "quarantined", "protected",
    "corrective_replanning", "indeterminate", "historical",
}
TERMINAL_DELIVERY = {"provider_delivered", "provider_read"}
AMBIGUOUS_DELIVERY = {
    "chatwoot_accepted_unverified", "provider_outcome_ambiguous",
}


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def decision_payload_sha256(value: Any) -> str:
    """Hash the immutable JSON semantic value without rewriting its source row."""
    return canonical_sha256(value if isinstance(value, Mapping) else {})


def resolution_identity(packet: Mapping[str, Any]) -> str:
    return "SAM-REVIEW-RESOLUTION-" + resolution_payload_sha256(packet)[:24].upper()


def resolution_payload_sha256(packet: Mapping[str, Any]) -> str:
    material = resolution_material(packet)
    return hashlib.sha256(
        json.dumps(material, ensure_ascii=False, separators=(", ", ": "), default=str).encode()
    ).hexdigest()


def resolution_material(packet: Mapping[str, Any]) -> list:
    packet = dict(packet or {})
    return [
        packet.get(key)
        for key in (
            "contract_version", "review_event_id", "account_id", "inbox_id",
            "contact_id", "conversation_id", "inbound_message_id",
            "review_decision_sha256", "represented_pig_id",
            "governed_disposition_operation_id", "represented_identity_status",
            "same_animal_mapping_prohibited",
            "canonical_same_animal_pig_id", "alias_evidence_id",
            "outgoing_message_id", "bound_reply_to_inbound_id",
            "outgoing_content_sha256", "response_class_evidence_id",
            "communication_delivery_status", "delivery_evidence_id",
            "delivery_evidence_sha256", "customer_obligation_status",
            "delivery_conversation_id", "delivery_inbound_message_id",
            "delivery_outgoing_message_id",
            "obligation_evidence_id", "obligation_evidence_sha256",
            "quarantine_evidence_id", "quarantine_evidence_sha256",
            "protected_decision_evidence_id", "protected_decision_evidence_sha256",
            "whatsapp_window_evidence_id", "whatsapp_window_evidence_sha256",
            "resolution_action", "chronology_cutoff_at", "chronology_sha256",
            "successor_work_item_id", "successor_contact_id",
            "successor_conversation_id", "successor_inbound_message_id",
            "successor_evidence_id", "successor_evidence_sha256",
            "content_relied_on_superseded_identity",
            "source_generation", "service_authority", "resolution_errors",
        )
    ]


def resolve_review_obligation(*, review, evidence, represented_identity) -> dict:
    """Resolve one exact review from canonical evidence; uncertainty stays visible."""
    review = dict(review or {})
    evidence = dict(evidence or {})
    represented_identity = dict(represented_identity or {})
    identity = dict(evidence.get("identity") or {})
    chronology = list(evidence.get("public_chronology") or [])
    delivery = dict(evidence.get("delivery") or {})
    content = dict(evidence.get("content_obligation") or {})
    protected = dict(evidence.get("protected_decision") or {})
    quarantine = dict(evidence.get("quarantine") or {})
    window = dict(evidence.get("whatsapp_window") or {})
    errors = []

    exact = {
        "review_event_id": str(review.get("review_event_id") or ""),
        "conversation_id": str(review.get("chatwoot_conversation_id") or ""),
        "inbound_message_id": str(review.get("chatwoot_message_id") or ""),
    }
    for field in ("account_id", "inbox_id", "contact_id"):
        if not str(identity.get(field) or ""):
            errors.append(f"{field}_missing")
    for field, value in exact.items():
        evidence_key = "bound_inbound_message_id" if field == "inbound_message_id" else field
        if not value or str(identity.get(evidence_key) or "") != value:
            errors.append(f"exact_{field}_mismatch")
    if not chronology or not all(isinstance(row, Mapping) for row in chronology):
        errors.append("canonical_public_chronology_missing")
    chronology_order = []
    for row in chronology:
        if not isinstance(row, Mapping):
            continue
        observed = str(row.get("provider_observed_at") or "")
        message_id = str(row.get("message_id") or "")
        try:
            observed_dt = datetime.fromisoformat(observed.replace("Z", "+00:00"))
            if observed_dt.tzinfo is None:
                raise ValueError
            chronology_order.append((observed_dt.astimezone(timezone.utc), message_id))
        except ValueError:
            errors.append("chronology_provider_timestamp_invalid")
    if chronology_order and chronology_order != sorted(chronology_order):
        errors.append("canonical_public_chronology_order_invalid")
    chronology_ids = {str(row.get("message_id") or "") for row in chronology if isinstance(row, Mapping)}
    if exact["inbound_message_id"] not in chronology_ids:
        errors.append("review_inbound_absent_from_chronology")
    chronology_sha = str(evidence.get("chronology_sha256") or "")
    if len(chronology_sha) != 64:
        errors.append("chronology_sha256_invalid")
    elif chronology_sha != canonical_sha256(chronology):
        errors.append("canonical_public_chronology_digest_mismatch")
    cutoff = str(evidence.get("chronology_cutoff_at") or "")
    if not cutoff:
        errors.append("chronology_cutoff_missing")
    elif chronology_order:
        try:
            cutoff_dt = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
            if cutoff_dt.tzinfo is None or cutoff_dt.astimezone(timezone.utc) != chronology_order[-1][0]:
                errors.append("chronology_cutoff_tail_mismatch")
        except ValueError:
            errors.append("chronology_cutoff_invalid")
    decision_sha = str(review.get("decision_json_sha256") or "")
    decision_text = review.get("decision_json_text")
    if decision_sha and isinstance(decision_text, str):
        try:
            if json.loads(decision_text) != review.get("decision_json"):
                errors.append("review_decision_text_semantic_mismatch")
        except (TypeError, ValueError):
            errors.append("review_decision_text_invalid")
        if hashlib.sha256(decision_text.encode()).hexdigest() != decision_sha:
            errors.append("review_decision_sha256_mismatch")
    elif decision_sha:
        errors.append("review_decision_text_required_for_supplied_digest")
    else:
        decision_sha = decision_payload_sha256(review.get("decision_json"))
    represented_pig_id = str(represented_identity.get("represented_pig_id") or "")
    if not represented_pig_id:
        errors.append("represented_pig_identity_mismatch")
    represented_status = str(represented_identity.get("status") or "unknown")
    if represented_status not in REPRESENTED_STATUSES:
        errors.append("represented_identity_status_invalid")
    elif represented_status in {"conflicting", "unknown"}:
        errors.append("represented_identity_not_authoritative")
    same_animal = represented_identity.get("canonical_same_animal_pig_id")
    alias_evidence = represented_identity.get("alias_evidence_id")
    if same_animal and not alias_evidence:
        errors.append("same_animal_alias_evidence_required")
    same_animal_mapping_prohibited = represented_identity.get(
        "same_animal_mapping_prohibited") is True
    if same_animal_mapping_prohibited and same_animal:
        errors.append("cohort_child_same_animal_mapping_prohibited")

    delivery_status = str(delivery.get("status") or "unknown")
    if delivery_status not in DELIVERY_STATUSES:
        errors.append("delivery_status_invalid")
    later_inbound = str(evidence.get("later_inbound_message_id") or "")
    outgoing = dict(evidence.get("later_public_outgoing") or {})
    outgoing_id = str(outgoing.get("message_id") or "")
    outgoing_bound = str(outgoing.get("bound_reply_to_inbound_id") or "")
    delivery_conversation = str(delivery.get("conversation_id") or "")
    delivery_inbound = str(delivery.get("inbound_message_id") or "")
    delivery_outgoing = str(delivery.get("outgoing_message_id") or "")
    if delivery_status not in {"not_attempted", "unknown"}:
        if delivery_conversation != exact["conversation_id"]:
            errors.append("delivery_conversation_identity_mismatch")
        if delivery_inbound != exact["inbound_message_id"]:
            errors.append("delivery_inbound_identity_mismatch")
    if delivery_status in TERMINAL_DELIVERY and not delivery_outgoing:
        errors.append("terminal_delivery_outgoing_identity_mismatch")
    elif outgoing_id and delivery_outgoing and delivery_outgoing != outgoing_id:
        errors.append("terminal_delivery_outgoing_identity_mismatch")
    content_answered = content.get("supported_obligation_answered") is True
    content_attributable = bool(
        outgoing_id
        and outgoing_id in chronology_ids
        and outgoing_bound == exact["inbound_message_id"]
        and len(str(outgoing.get("content_sha256") or "")) == 64
        and str(outgoing.get("response_class_evidence_id") or "")
    )
    relied_on_superseded = content.get("relied_on_superseded_identity") is True
    successor_evidence = dict(evidence.get("successor_work_item") or {})
    successor = str(successor_evidence.get("work_item_id") or "")
    if later_inbound and later_inbound not in chronology_ids:
        errors.append("later_inbound_absent_from_chronology")

    def evidence_binding(source, kind):
        evidence_id = str(source.get("evidence_id") or f"{kind.upper()}-EVIDENCE-UNAVAILABLE")
        digest = str(source.get("evidence_sha256") or "")
        payload = source.get("evidence_payload")
        if not isinstance(payload, Mapping):
            errors.append(f"{kind}_evidence_payload_missing")
            payload = {"kind": kind, "status": "unavailable"}
        computed = canonical_sha256(payload)
        semantic_projection = {
            key: value for key, value in source.items()
            if key not in {"evidence_id", "evidence_sha256", "evidence_payload"}
        }
        if semantic_projection != dict(payload):
            errors.append(f"{kind}_evidence_payload_semantic_mismatch")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            errors.append(f"{kind}_evidence_sha256_invalid")
            digest = computed
        elif digest != computed:
            errors.append(f"{kind}_evidence_sha256_mismatch")
        return evidence_id, digest

    delivery_evidence_id, delivery_evidence_sha = evidence_binding(delivery, "delivery")
    obligation_evidence_id, obligation_evidence_sha = evidence_binding(content, "obligation")
    quarantine_evidence_id, quarantine_evidence_sha = evidence_binding(quarantine, "quarantine")
    protected_evidence_id, protected_evidence_sha = evidence_binding(protected, "protected_decision")
    window_evidence_id, window_evidence_sha = evidence_binding(window, "whatsapp_window")
    successor_evidence_id = None
    successor_evidence_sha = None
    if later_inbound:
        successor_evidence_id, successor_evidence_sha = evidence_binding(
            successor_evidence, "successor_work_item"
        )
        if not successor:
            errors.append("later_inbound_successor_binding_missing")
        if str(successor_evidence.get("contact_id") or "") != str(identity.get("contact_id") or ""):
            errors.append("successor_contact_identity_mismatch")
        if str(successor_evidence.get("conversation_id") or "") != exact["conversation_id"]:
            errors.append("successor_conversation_identity_mismatch")
        if str(successor_evidence.get("inbound_message_id") or "") != later_inbound:
            errors.append("successor_inbound_identity_mismatch")
        if successor_evidence.get("current_actionable") is not True:
            errors.append("successor_current_actionable_evidence_required")
        if str(successor_evidence.get("chronology_sha256") or "") != chronology_sha:
            errors.append("successor_chronology_binding_mismatch")
    if str(window.get("state") or "unknown") not in {"open", "closed", "unknown"}:
        errors.append("whatsapp_window_state_invalid")
    elif str(window.get("state") or "unknown") == "unknown":
        errors.append("whatsapp_window_state_unknown")

    if errors:
        obligation, action = "unknown_fail_closed", "indeterminate"
    elif protected.get("active") is True:
        obligation, action = "protected_owner_action_required", "protected"
    elif quarantine.get("active") is True or delivery_status in AMBIGUOUS_DELIVERY:
        obligation, action = "quarantined_no_retry", "quarantined"
    elif later_inbound:
        obligation, action = "superseded_by_later_inbound", "historical"
    elif window.get("state") == "closed" and not content_attributable:
        obligation, action = "closed_window_reengagement_required", "active"
    elif delivery_status in TERMINAL_DELIVERY:
        if content_attributable and content_answered and not relied_on_superseded:
            obligation, action = "completed_by_attributable_supported_reply", "completed"
        elif relied_on_superseded or content_attributable:
            obligation, action = "corrective_replan_required_after_reply", "corrective_replanning"
        else:
            obligation, action = "delivered_attempt_requires_content_resolution", "indeterminate"
    elif content_attributable:
        obligation, action = "unknown_fail_closed", "indeterminate"
        errors.append("substantive_reply_without_terminal_delivery")
    elif identity.get("latest_public_message_type") == "incoming":
        obligation, action = "active_replan_required", "active"
    else:
        obligation, action = "unknown_fail_closed", "indeterminate"

    packet = {
        "contract_version": CONTRACT_VERSION,
        "review_event_id": exact["review_event_id"],
        "account_id": str(identity.get("account_id") or ""),
        "inbox_id": str(identity.get("inbox_id") or ""),
        "contact_id": str(identity.get("contact_id") or ""),
        "conversation_id": exact["conversation_id"],
        "inbound_message_id": exact["inbound_message_id"],
        "review_decision_sha256": decision_sha,
        "represented_pig_id": represented_pig_id,
        "governed_disposition_operation_id": str(represented_identity.get(
            "governed_disposition_operation_id") or "GOVERNED-DISPOSITION-UNKNOWN"),
        "represented_identity_status": represented_status,
        "same_animal_mapping_prohibited": same_animal_mapping_prohibited,
        "canonical_same_animal_pig_id": same_animal or None,
        "alias_evidence_id": alias_evidence or None,
        "outgoing_message_id": outgoing_id or None,
        "bound_reply_to_inbound_id": outgoing_bound or None,
        "outgoing_content_sha256": outgoing.get("content_sha256") or None,
        "response_class_evidence_id": outgoing.get("response_class_evidence_id") or None,
        "communication_delivery_status": delivery_status,
        "delivery_evidence_id": delivery_evidence_id,
        "delivery_evidence_sha256": delivery_evidence_sha,
        "delivery_conversation_id": delivery_conversation or None,
        "delivery_inbound_message_id": delivery_inbound or None,
        "delivery_outgoing_message_id": delivery_outgoing or None,
        "customer_obligation_status": obligation,
        "obligation_evidence_id": obligation_evidence_id,
        "obligation_evidence_sha256": obligation_evidence_sha,
        "quarantine_evidence_id": quarantine_evidence_id,
        "quarantine_evidence_sha256": quarantine_evidence_sha,
        "protected_decision_evidence_id": protected_evidence_id,
        "protected_decision_evidence_sha256": protected_evidence_sha,
        "whatsapp_window_evidence_id": window_evidence_id,
        "whatsapp_window_evidence_sha256": window_evidence_sha,
        "resolution_action": action,
        "chronology_cutoff_at": cutoff,
        "chronology_sha256": chronology_sha,
        "successor_work_item_id": successor or None,
        "successor_contact_id": successor_evidence.get("contact_id") or None,
        "successor_conversation_id": successor_evidence.get("conversation_id") or None,
        "successor_inbound_message_id": successor_evidence.get("inbound_message_id") or None,
        "successor_evidence_id": successor_evidence_id,
        "successor_evidence_sha256": successor_evidence_sha,
        "content_relied_on_superseded_identity": relied_on_superseded,
        "source_generation": str(evidence.get("source_generation") or "unavailable"),
        "service_authority": "sam_review_obligation_resolver",
        "resolution_errors": sorted(set(errors)),
    }
    packet["event_payload_sha256"] = resolution_payload_sha256(packet)
    packet["resolution_event_id"] = resolution_identity(packet)
    return packet


def build_resolution_manifest(*, reviews, evidence_by_review, represented_identity) -> dict:
    rows = []
    seen = set()
    for review in sorted(reviews or [], key=lambda row: str(row.get("review_event_id") or "")):
        review_id = str(review.get("review_event_id") or "")
        if not review_id or review_id in seen:
            raise ValueError("unique_review_identity_required")
        seen.add(review_id)
        rows.append(resolve_review_obligation(
            review=review,
            evidence=(evidence_by_review or {}).get(review_id) or {},
            represented_identity=represented_identity,
        ))
    manifest = {
        "contract_version": CONTRACT_VERSION,
        "represented_pig_id": str((represented_identity or {}).get("represented_pig_id") or ""),
        "row_count": len(rows),
        "resolution_event_ids": [row["resolution_event_id"] for row in rows],
        "rows": rows,
        "disposition_counts": {
            action: sum(row["resolution_action"] == action for row in rows)
            for action in sorted(RESOLUTION_ACTIONS)
        },
        "obligation_counts": {
            status: sum(row["customer_obligation_status"] == status for row in rows)
            for status in sorted(OBLIGATION_STATUSES)
        },
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return manifest


def record_resolution_event(packet, *, database_url=None) -> tuple[dict, int]:
    packet = dict(packet or {})
    expected_id = resolution_identity(packet)
    if packet.get("resolution_event_id") != expected_id:
        return _result("resolution_identity_mismatch"), 400
    url = str(database_url or os.getenv("DATABASE_URL") or "").strip()
    if not url:
        return _result("resolution_database_unavailable"), 503
    try:
        import psycopg
        with psycopg.connect(url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select public.record_sam_review_obligation_resolution(%s::jsonb)", (json.dumps(packet),))
                created = bool((cursor.fetchone() or [False])[0])
        return _result(
            "resolution_event_recorded" if created else "resolution_event_replay_withheld",
            resolution_event_id=expected_id,
            created=created,
        ), 201 if created else 200
    except Exception as exc:
        return _result("resolution_event_failed", error_type=exc.__class__.__name__), 503


def _result(status, **values):
    return {
        "success": status in {"resolution_event_recorded", "resolution_event_replay_withheld"},
        "status": status,
        **values,
        "sends_customer_message": False,
        "mutates_chatwoot": False,
        "mutates_review_history": False,
        "mutates_farm_state": False,
    }
