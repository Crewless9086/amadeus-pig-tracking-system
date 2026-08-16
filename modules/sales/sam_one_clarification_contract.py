"""Dormant, fail-closed contract for the owner-promotable clarification class.

This module prepares and validates authority-bound proposals.  It never calls a
provider and does not grant dispatch authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

from modules.sales.sam_live_stock_evaluation import EVALUATOR_VERSION
from modules.sales.sam_response_class_authority import (
    ONE_CLARIFICATION_CLASS,
    ONE_CLARIFICATION_ENVELOPE_VERSION,
)


TERMINAL_DELIVERY_STATES = {"provider_delivered", "provider_read"}
QUARANTINE_DELIVERY_STATES = {
    "provider_rejected", "provider_failed", "provider_outcome_ambiguous",
    "delivery_transition_missing",
}


def prepare_one_clarification(context: Mapping[str, Any], *, now=None) -> dict[str, Any]:
    """Validate one exact inbound and return a digest-bound no-send proposal."""
    context = dict(context or {})
    observed = _aware(now or datetime.now(timezone.utc))
    blockers = []
    required_identity = (
        "account_id", "inbox_id", "conversation_id", "inbound_message_id",
        "contact_id", "chronology_hash", "missing_fact_key", "authority_event_id",
    )
    for key in required_identity:
        if not _clean(context.get(key)):
            blockers.append(f"{key}_missing")
    if context.get("response_class") != ONE_CLARIFICATION_CLASS:
        blockers.append("response_class_mismatch")
    if context.get("policy_version") != EVALUATOR_VERSION:
        blockers.append("policy_version_mismatch")
    if context.get("envelope_version") != ONE_CLARIFICATION_ENVELOPE_VERSION:
        blockers.append("envelope_version_mismatch")
    if _clean(context.get("lane")).lower() != "livestock":
        blockers.append("typed_livestock_lane_required")
    if context.get("genuine_chatwoot_inbound") is not True:
        blockers.append("genuine_chatwoot_inbound_required")
    inbound_at = _time(context.get("inbound_at"))
    activated_at = _time(context.get("activated_at"))
    if inbound_at is None or activated_at is None or inbound_at < activated_at:
        blockers.append("post_activation_inbound_required")
    if context.get("exact_latest_inbound") is not True:
        blockers.append("exact_latest_inbound_required")
    if context.get("identity_certain") is not True:
        blockers.append("identity_uncertain")
    if context.get("reply_window_healthy") is not True:
        blockers.append("provider_reply_window_unhealthy")
    if context.get("missing_fact_unanswered") is not True:
        blockers.append("missing_fact_already_answered_or_unproven")
    if not _clean(context.get("customer_language")):
        blockers.append("retained_customer_language_missing")
    if context.get("closing_or_thanks") is True:
        blockers.append("closing_or_thanks_excluded")
    if any(context.get(key) is True for key in (
        "customer_opt_out", "complaint_or_dispute", "sensitive_or_welfare",
        "protected_action", "commercially_binding_instruction", "historical_backlog",
    )):
        blockers.append("excluded_inbound")
    evidence = context.get("evidence_health")
    if not isinstance(evidence, Mapping) or any(
        evidence.get(key) is not True for key in (
            "canonical_context", "stock", "pricing", "eligibility",
            "identity_chronology", "provider",
        )
    ):
        blockers.append("internal_evidence_unhealthy_quarantine")
    acknowledgement = _clean(context.get("neutral_acknowledgement"))
    question = _clean(context.get("question"))
    if not acknowledgement or not question or context.get("question_count") != 1:
        blockers.append("one_natural_question_required")
    if context.get("question_missing_fact_key") != context.get("missing_fact_key"):
        blockers.append("question_missing_fact_binding_mismatch")
    if context.get("contains_commercial_statement") is not False:
        blockers.append("commercial_statement_prohibited")

    binding = {key: _clean(context.get(key)) for key in required_identity}
    binding.update({
        "response_class": ONE_CLARIFICATION_CLASS,
        "policy_version": EVALUATOR_VERSION,
        "envelope_version": ONE_CLARIFICATION_ENVELOPE_VERSION,
        "inbound_at": inbound_at.isoformat() if inbound_at else "",
        "customer_language": _clean(context.get("customer_language")),
        "evidence_identities": _json_safe(context.get("evidence_identities") or {}),
    })
    response_text = f"{acknowledgement} {question}".strip()
    binding["content_digest"] = _digest({"language": binding["customer_language"], "text": response_text})
    proposal_digest = _digest(binding)
    return {
        "success": not blockers,
        "status": "one_clarification_prepared" if not blockers else "one_clarification_withheld",
        "allowed": not blockers,
        "blockers": sorted(set(blockers)),
        "binding": binding,
        "proposal_digest": proposal_digest,
        "claim_key": _digest({"kind": "one_clarification_claim", **binding}),
        "response_text": response_text if not blockers else "",
        "maximum_provider_attempts": 1,
        "automatic_retry": False,
        "proactive_follow_up": False,
        "retained_state": "awaiting_customer" if not blockers else "quarantined",
        "evaluated_at": observed.isoformat(),
        "provider_calls": 0,
    }


def delivery_disposition(state: str) -> dict[str, Any]:
    state = _clean(state).lower()
    return {
        "state": state,
        "complete": state in TERMINAL_DELIVERY_STATES,
        "retry_allowed": False,
        "quarantined": state in QUARANTINE_DELIVERY_STATES,
    }


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(_json_safe(value), sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _json_safe(value):
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _clean(value):
    return str(value or "").strip()


def _time(value):
    try:
        return _aware(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return None


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
