"""Shared deterministic authority boundary for SAM Sales Autonomy Level 1."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Mapping

from modules.sales.sam_owner_reply_window import (
    ReplyWindowEvidenceError,
    evaluate_reply_window,
)


LEVEL_ENV = "SAM_SALES_AUTONOMY_LEVEL"
COHORT_ENABLED_ENV = "SAM_SALES_LEVEL1_COHORT_ENABLED"
COHORT_BINDINGS_ENV = "SAM_SALES_LEVEL1_COHORT_BINDINGS"
BROAD_DISPATCH_ENV = "SAM_SALES_LEVEL1_BROAD_DISPATCH_ENABLED"
COHORT_STOPPED_ENV = "SAM_SALES_LEVEL1_COHORT_STOPPED"
MEAT_ENABLED_ENV = "SAM_SALES_LEVEL1_MEAT_ENABLED"
LIVE_STOCK_ENABLED_ENV = "SAM_SALES_LEVEL1_LIVE_STOCK_ENABLED"
CONTRACT_VERSION = "sam_sales_autonomy_level_1_v1"

TIER1_ACTIONS = {
    "answer_general_info", "answer_location", "answer_price",
    "ask_one_missing_detail", "answer_delivery_policy", "confirm_collection",
    "explain_product", "explain_process", "qualify_lead", "no_reply_needed",
    "soft_qualify_interest", "request_missing_fact", "answer_farm_info",
    "explain_product_options", "no_reply",
}
PROTECTED_FLAGS = {
    "creates_quote", "creates_order", "confirms_payment", "issues_refund",
    "reserves_stock", "allocates_stock", "changes_stock", "assigns_animal",
    "books_slaughter", "commits_carcass", "writes_farm_data",
    "promises_delivery", "applies_discount", "negotiates_price",
}
PROTECTED_TEXT = re.compile(
    r"\b(?:reserved for you|(?:i(?:'ve| have)|we(?:'ve| have)) reserved "
    r"(?:them|these|it|\d+[^.!?]*)|reservation confirmed|"
    r"(?:your )?order (?:is )?confirmed|payment (?:is )?(?:confirmed|received)|"
    r"deposit (?:is )?(?:confirmed|received)|(?:we can|we will|we'll) deliver "
    r"(?:today|tomorrow|on|by)|delivery (?:is|will be) (?:on|by)|"
    r"(?:we can|we will|we'll) allocate \d+|slaughter (?:booking )?(?:is )?"
    r"(?:confirmed|booked)|discount(?:ed)? to|final binding quote)\b",
    re.I,
)
OWNER_EXCEPTION_TEXT = re.compile(
    r"\b(?:complaint|refund|discount|negotiate|special price|promise|guarantee|"
    r"reserve|reservation|book slaughter|payment dispute|welfare|injured|sick)\b",
    re.I,
)


def sales_autonomy_level1_policy(environ: Mapping | None = None) -> dict:
    """Expose sanitized configuration state; configured identity is never evidence."""
    source = dict(environ or {})
    bindings, valid = _cohort_bindings(source.get(COHORT_BINDINGS_ENV))
    selected = _text(source.get(LEVEL_ENV), 20) == "1"
    stopped = _truthy(source.get(COHORT_STOPPED_ENV))
    cohort = _truthy(source.get(COHORT_ENABLED_ENV))
    broad = _truthy(source.get(BROAD_DISPATCH_ENV))
    cohort_safe = valid and 0 < len(bindings) <= 5
    return {
        "version": CONTRACT_VERSION,
        "selected": selected,
        "meat_enabled": _truthy(source.get(MEAT_ENABLED_ENV)),
        "live_stock_enabled": _truthy(source.get(LIVE_STOCK_ENABLED_ENV)),
        "cohort_enabled": cohort,
        "cohort_configured_count": len(bindings),
        "cohort_configuration_safe": cohort_safe,
        "broad_dispatch_enabled": broad,
        "stopped": stopped,
        "dispatch_gate_configured": selected and not stopped and (broad or (cohort and cohort_safe)),
        "contains_identity_values": False,
        "protected_actions_authorized": False,
        "automatic_retry_authorized": False,
    }

def evaluate_level1_authority(
    *,
    lane: str,
    inbound: Mapping | None,
    decision: Mapping | None,
    review: Mapping | None,
    evidence: Mapping | None = None,
    environ: Mapping | None = None,
) -> dict:
    """Return a fail-closed Tier 1 decision without performing any action."""
    inbound = dict(inbound or {})
    decision = dict(decision or {})
    review = dict(review or {})
    evidence = dict(evidence or {})
    source = dict(environ or {})
    reply = _text(decision.get("suggested_reply_text") or decision.get("reply_text"), 1800)
    identity = {
        key: _text(inbound.get(key), 120)
        for key in ("account_id", "conversation_id", "contact_id", "inbox_id")
    }
    inbound_id = _text(
        inbound.get("message_id") or inbound.get("inbound_message_id"), 120
    )
    next_action = _text(decision.get("next_action"), 100) or _infer_tier1_action(decision)
    protected = sorted(key for key in PROTECTED_FLAGS if decision.get(key) is True)
    protected_text = bool(PROTECTED_TEXT.search(reply))
    owner_exception_text = bool(OWNER_EXCEPTION_TEXT.search(
        str(inbound.get("content") or "")
    ))
    availability = evidence.get("availability")
    availability_current = (
        isinstance(availability, Mapping)
        and availability.get("evidence_complete") is True
        and str(availability.get("freshness") or "").lower() == "current"
    )
    unsupported_count = bool(
        not availability_current
        and re.search(r"\b\d+\s+(?:available|in stock|pigs?|carcasses?)\b", reply, re.I)
    )
    unsupported_availability = bool(
        not availability_current and _affirmative_availability_claim(reply)
    )
    availability_required = _availability_question(inbound.get("content"))
    supported_partial = bool(
        not availability_current
        and _availability_uncertainty(reply)
        and _useful_qualification_question(reply)
    )
    cohort_bindings, cohort_bindings_valid = _cohort_bindings(
        source.get(COHORT_BINDINGS_ENV)
    )
    conversation_id = identity["conversation_id"]
    checks = {
        "level_1_enabled": _text(source.get(LEVEL_ENV), 20) == "1",
        "lane_enabled": _truthy(source.get(
            MEAT_ENABLED_ENV if lane == "meat" else LIVE_STOCK_ENABLED_ENV
        )),
        "cohort_not_stopped": not _truthy(source.get(COHORT_STOPPED_ENV)),
        "identity_complete": bool(inbound_id and all(identity.values())),
        "chronology_current": (
            inbound.get("processable") is True
            and inbound.get("message_type") in {None, "", "incoming"}
            and inbound.get("chronology_current") is True
            and _canonical_instant(inbound.get("latest_observed_at")) is not None
        ),
        "channel_authorized": (
            inbound.get("whatsapp_window_state") == "open"
            and inbound.get("whatsapp_window_evidence_authoritative") is True
        ),
        "specialist_lane": lane in {"meat", "live_stock"},
        "reply_recommended": decision.get("should_reply") is True and bool(reply),
        "review_safe": (
            review.get("safe_to_send") is True
            and review.get("escalation_required") is not True
            and review.get("owner_authority_required") is not True
        ),
        "tier_1_action": next_action in TIER1_ACTIONS,
        "protected_flags_absent": not protected,
        "protected_text_absent": not protected_text,
        "owner_exception_text_absent": not owner_exception_text,
        "unsupported_availability_count_absent": not unsupported_count,
        "unsupported_availability_claim_absent": not unsupported_availability,
        "availability_pending_answer_useful": (
            not availability_required or availability_current or supported_partial
        ),
        "supporting_evidence_valid": evidence.get("supporting_evidence_valid") is True,
        "durable_delivery_rail_available": evidence.get("delivery_rail_available") is True,
        "automatic_retry_disabled": evidence.get("automatic_retry") is not True,
    }
    eligible = all(checks.values())
    cohort_enabled = _truthy(source.get(COHORT_ENABLED_ENV))
    broad_enabled = _truthy(source.get(BROAD_DISPATCH_ENV))
    cohort_config_safe = cohort_bindings_valid and 0 < len(cohort_bindings) <= 5
    cohort_member = (conversation_id, inbound_id) in cohort_bindings
    dispatch_authorized = bool(
        eligible
        and (
            broad_enabled
            or (cohort_enabled and cohort_config_safe and cohort_member)
        )
    )
    classification = _classification(decision, review, checks)
    return {
        "version": CONTRACT_VERSION,
        "lane": lane,
        "classification": classification,
        "tier_1_action": next_action,
        "tier_1_eligible": eligible,
        "dispatch_authorized": dispatch_authorized,
        "checks": checks,
        "blockers": [key for key, passed in checks.items() if not passed],
        "cohort": {
            "enabled": cohort_enabled,
            "configured_count": len(cohort_bindings),
            "configuration_safe": cohort_config_safe,
            "conversation_member": cohort_member,
            "inbound_event_member": cohort_member,
            "broad_dispatch_enabled": broad_enabled,
            "stopped": _truthy(source.get(COHORT_STOPPED_ENV)),
            "maximum_first_cohort": 5,
            "contains_identity_values": False,
        },
        "owner_decision": _owner_decision_card(decision, classification, protected),
        "authority_id": _identity(lane, conversation_id, inbound_id, reply),
        "reply_hash": hashlib.sha256(reply.encode("utf-8")).hexdigest() if reply else "",
        "contains_customer_values": False,
        "writes_performed": False,
        "automatic_retry_authorized": False,
        "protected_actions_authorized": False,
    }


def bind_authoritative_conversation_evidence(
    inbound: Mapping | None,
    messages,
    *,
    provider_evidence: Mapping | None = None,
    now=None,
) -> dict:
    """Bind current public chronology and provider-window evidence fail closed."""
    row = dict(inbound or {})
    try:
        window = evaluate_reply_window(
            messages or [],
            conversation_identity={
                key: row.get(key)
                for key in ("account_id", "conversation_id", "contact_id", "inbox_id")
            } | {"channel": row.get("channel")},
            provider_evidence=provider_evidence or {
                "provider_identity_class": row.get("channel"),
            },
            now=now,
        )
    except (ReplyWindowEvidenceError, TypeError, ValueError):
        return {
            **row,
            "chronology_current": False,
            "whatsapp_window_state": "unavailable",
            "whatsapp_window_evidence_authoritative": False,
            "latest_observed_at": "",
            "level1_evidence_status": "authoritative_chronology_unavailable",
        }
    expected_inbound = _text(
        row.get("message_id") or row.get("inbound_message_id"), 120
    )
    current = bool(
        expected_inbound
        and window.get("latest_inbound_message_id") == expected_inbound
        and window.get("reply_authority_state") == "ordinary_reply_allowed"
    )
    return {
        **row,
        "chronology_current": current,
        "whatsapp_window_state": window.get("window_state", "unavailable"),
        "whatsapp_window_evidence_authoritative": True,
        "latest_observed_at": window.get("evaluated_at_utc") or "",
        "reply_window_evidence": window,
        "level1_evidence_status": (
            "current_authoritative_evidence"
            if current
            else "latest_inbound_or_reply_authority_changed"
        ),
    }


def supporting_claims_are_evidence_backed(
    lane: str,
    decision: Mapping | None,
    *,
    review_evidence_ready: bool,
) -> bool:
    """Verify price and availability claims without authorizing a mutation."""
    row = dict(decision or {})
    reply = _text(row.get("suggested_reply_text") or row.get("reply_text"), 1800)
    if not review_evidence_ready or list(row.get("blockers") or []):
        return False
    price_claim = bool(re.search(r"(?:R\s?\d|\d[\d ,.]*\s*(?:rand|zar))", reply, re.I))
    count_claim = bool(re.search(
        r"\b\d+\s+(?:female|male|available|in stock|pigs?|piglets?|weaners?|"
        r"growers?|finishers?|carcasses?)\b",
        reply,
        re.I,
    ))
    if lane == "meat":
        truth = row.get("commercial_truth") if isinstance(row.get("commercial_truth"), Mapping) else {}
        if price_claim and not (
            truth.get("price_evidence_complete") is True
            or row.get("price_evidence_complete") is True
            or row.get("reply_source") in {"product_knowledge_tool", "hard_price_gate"}
        ):
            return False
        return not count_claim or row.get("availability_evidence_complete") is True
    pricing = row.get("price_answer_packet") if isinstance(row.get("price_answer_packet"), Mapping) else {}
    contextual = row.get("contextual_sales") if isinstance(row.get("contextual_sales"), Mapping) else {}
    availability = row.get("availability") if isinstance(row.get("availability"), Mapping) else {}
    if price_claim and not (
        pricing.get("can_answer_price") is True
        or contextual.get("source_evidence_complete") is True
    ):
        return False
    if count_claim and not (
        availability.get("evidence_complete") is True
        or contextual.get("source_evidence_complete") is True
    ):
        return False
    return True


def _infer_tier1_action(decision):
    """Map a reviewed legacy decision into the bounded Level 1 vocabulary."""
    missing = decision.get("missing_fields") or decision.get("missing_facts") or []
    if missing:
        return "request_missing_fact"
    if decision.get("should_reply") is True:
        return "answer_general_info"
    return ""

def _classification(decision, review, checks):
    if decision.get("not_interested") is True or decision.get("next_action") == "no_reply_needed":
        return "not_interested"
    if review.get("owner_authority_required") is True or any(
        decision.get(key) is True for key in PROTECTED_FLAGS
    ) or not checks.get("owner_exception_text_absent", True):
        return "owner_exception"
    if not checks["supporting_evidence_valid"] or not checks["review_safe"]:
        return "evidence_specific_pending"
    if decision.get("next_action") in {"prepare_quote", "quote_needed"}:
        return "quote_needed"
    return "qualified" if checks["reply_recommended"] else "handled_non_sales"


def _owner_decision_card(decision, classification, protected):
    if classification != "owner_exception":
        return {}
    return {
        "status": "prepared_owner_decision",
        "recommended_decision": _text(decision.get("recommended_owner_decision"), 240)
        or "Review the protected commercial exception.",
        "commercial_consequence": _text(decision.get("commercial_consequence"), 300)
        or "No protected commitment is made until the owner decides.",
        "next_executable_action": _text(decision.get("next_executable_action"), 240)
        or "Approve, edit, reject, or send back through the owner decision rail.",
        "protected_reasons": protected,
        "customer_send_performed": False,
    }


def _cohort_bindings(value):
    raw_rows = [item.strip() for item in str(value or "").split(",") if item.strip()]
    pairs = []
    for item in raw_rows:
        parts = item.split(":", 1)
        if len(parts) != 2 or not all(_text(part, 120) for part in parts):
            return set(), False
        pairs.append((_text(parts[0], 120), _text(parts[1], 120)))
    return set(pairs), len(pairs) == len(set(pairs))


def _affirmative_availability_claim(reply):
    text = _text(reply, 1800).lower()
    return bool(re.search(
        r"\b(?:available|in stock|we have|can fulfil|can fulfill|enough (?:pigs?|"
        r"piglets?|stock)|shortage|only \d+)\b",
        text,
    ))


def _availability_uncertainty(reply):
    text = _text(reply, 1800).lower()
    return any(phrase in text for phrase in (
        "confirming availability",
        "confirm availability",
        "checking availability",
        "check availability",
        "availability still needs to be confirmed",
    ))


def _availability_question(content):
    return bool(re.search(
        r"\b(?:available|availability|in stock|have any|have \d+|can you supply|"
        r"can you fulfil|can you fulfill)\b",
        _text(content, 1800),
        re.I,
    ))


def _useful_qualification_question(reply):
    questions = re.findall(r"[^?]*\?", _text(reply, 1800), re.I)
    return any(re.search(
        r"\b(?:how many|quantity|male|female|mixture|mix|category|piglet|weaner|"
        r"grower|finisher|collection|collect|delivery|area|location|where|when|"
        r"timing|date|week|month|weight|age|cut|half|both halves)\b",
        question,
        re.I,
    ) for question in questions)


def _identity(lane, conversation_id, inbound_id, reply):
    seed = "\x1f".join((CONTRACT_VERSION, lane, conversation_id, inbound_id,
                       hashlib.sha256(reply.encode("utf-8")).hexdigest()))
    return "SAM-SALES-L1-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:28].upper()


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _text(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _canonical_instant(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
