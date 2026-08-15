"""Deterministic, evidence-aware pre-send usefulness contract for SAM."""

from __future__ import annotations

import hashlib
import re
from typing import Mapping


CONTRACT_VERSION = "sam_response_usefulness_v1"
GUIDANCE_POLICY_ID = "sam_live_stock_customer_guidance_v1"
CANONICAL_OFFER_VERSION = "sam_livestock_evidence_offer_v1"
CANONICAL_OBLIGATION_VERSION = "sam_conversation_obligation_v1"
GUIDANCE_POLICY_DIGEST = hashlib.sha256(
    (
        "small:2-6kg|weaned:7-19kg|growing:20-49kg|larger:50-79kg|"
        "slaughter:80kg+|location:Riversdale,Western Cape|"
        "collection:arranged"
    ).encode()
).hexdigest()


def evaluate_response_usefulness(*, lane, inbound, decision, evidence=None):
    inbound = dict(inbound or {})
    decision = dict(decision or {})
    evidence = dict(evidence or {})
    content = _text(inbound.get("content"), 1800)
    reply = _text(
        decision.get("suggested_reply_text") or decision.get("reply_text"),
        1800,
    )
    canonical = _canonical_usefulness_boundary(
        lane=lane, inbound=inbound, decision=decision, evidence=evidence, reply=reply
    )
    if canonical is not None:
        return canonical
    raw_missing = decision.get("missing_fields") or []
    missing_fields_valid = bool(
        isinstance(raw_missing, (list, tuple, set))
        and all(isinstance(value, str) for value in raw_missing)
    )
    missing = {
        _field_name(value)
        for value in raw_missing
        if missing_fields_valid and _field_name(value)
    }
    intents = _intents(content)
    required_guidance = _required_guidance(lane, intents, content, missing)
    availability = (
        evidence.get("availability")
        if isinstance(evidence.get("availability"), Mapping)
        else {}
    )
    coverage = {
        "location": _covers_location(reply),
        "size": _covers_size_guidance(reply, minimum_bands=1),
        "size_choices": _covers_size_guidance(reply, minimum_bands=2),
        "price": _covers_or_qualifies(reply, "price"),
        "availability": _covers_or_qualifies(
            reply,
            "availability",
            availability_current=(
                availability.get("evidence_complete") is True
                and str(availability.get("freshness") or "").lower()
                == "current"
            ),
        ),
        "collection": _covers_collection(reply),
        "sex": _covers_sex(reply),
        "purpose": _covers_purpose(reply),
    }
    unanswered = sorted(
        intent for intent in intents
        if intent in coverage and not coverage[intent]
    )
    guidance_missing = sorted(
        guidance for guidance in required_guidance
        if guidance == "customer_friendly_size_choices"
        and not coverage["size_choices"]
        or guidance == "location_or_collection_guidance"
        and not (coverage["location"] or coverage["collection"])
    )
    asked_missing = _asked_missing_facts(reply, missing)
    asks_useful = bool(asked_missing)
    has_useful_question = asks_useful or _has_useful_question(reply)
    qualification_required = bool(
        missing & {"quantity", "sex", "size", "weight_range", "location", "timing"}
    )
    unresolved_commercial = bool(
        ("price" in intents and not _has_supported_price_answer(reply))
        or (
            "availability" in intents
            and not (
                availability.get("evidence_complete") is True
                and str(availability.get("freshness") or "").lower() == "current"
                and _has_affirmative_availability_answer(reply)
            )
        )
    )
    pure_deferral = bool(
        unresolved_commercial
        and not (
            coverage["size"]
            or coverage["location"]
            or coverage["collection"]
            or has_useful_question
        )
    )
    checks = {
        "missing_fields_valid": missing_fields_valid,
        "material_intents_covered": not unanswered,
        "required_guidance_included": not guidance_missing,
        "qualification_advanced": (
            not qualification_required
            or asks_useful
        ),
        "not_pure_deferral": not pure_deferral,
        "customer_language_used": not _unexplained_internal_taxonomy(reply),
        "concise": 0 < len(reply) <= 1800,
        "provenance_present": bool(
            inbound.get("message_id")
            and inbound.get("conversation_id")
            and evidence.get("supporting_evidence_valid") is True
        ),
        # Static customer guidance is accepted only when it matches this
        # compiled, versioned policy. Callers cannot mint authority booleans at
        # the send boundary.
        "claim_specific_provenance_valid": bool(
            not (coverage["size"] or coverage["location"] or coverage["collection"])
            or lane == "live_stock"
        ),
    }
    passed = all(checks.values())
    return {
        "version": CONTRACT_VERSION,
        "passed": passed,
        "checks": checks,
        "blockers": [name for name, value in checks.items() if not value],
        "intents": sorted(intents),
        "unanswered_intents": unanswered,
        "missing_facts": sorted(missing),
        "required_guidance": sorted(required_guidance),
        "guidance_missing": guidance_missing,
        "prohibited_claims": list(evidence.get("prohibited_claims") or []),
        "evidence_provenance": {
            "conversation_id_hash": _hash(inbound.get("conversation_id")),
            "inbound_message_id_hash": _hash(inbound.get("message_id")),
            "supporting_evidence_valid": (
                evidence.get("supporting_evidence_valid") is True
            ),
            "availability_freshness": str(
                availability.get("freshness") or "unavailable"
            ).lower(),
            "guidance_policy_id": GUIDANCE_POLICY_ID,
            "guidance_policy_digest": GUIDANCE_POLICY_DIGEST,
        },
        "contains_customer_content": False,
        "sends_customer_message": False,
        "mutates_business_state": False,
    }


def customer_advancement_outcome(*, provider_state, usefulness_passed,
                                 qualification_advanced):
    delivered = provider_state in {"provider_delivered", "provider_read"}
    return {
        "provider_transport_confirmed": delivered,
        "customer_advancement_confirmed": bool(
            delivered and usefulness_passed and qualification_advanced
        ),
        "ambiguous_quarantine": provider_state in {
            "chatwoot_accepted_unverified", "provider_outcome_ambiguous"
        },
        "intake_write_alone_is_advancement": False,
    }


def _canonical_usefulness_boundary(*, lane, inbound, decision, evidence, reply):
    """Make the final canonical obligation authoritative over legacy hints."""
    offer = decision.get("canonical_evidence_offer")
    if not isinstance(offer, Mapping):
        return None
    obligations = offer.get("conversation_obligations")
    authority = offer.get("authority")
    offer_identity = offer.get("identity")
    obligation_identity = (
        obligations.get("identity") if isinstance(obligations, Mapping) else None
    )
    expected = {
        "account_id": str(inbound.get("account_id") or ""),
        "inbox_id": str(inbound.get("inbox_id") or ""),
        "contact_id": str(inbound.get("contact_id") or ""),
        "conversation_id": str(inbound.get("conversation_id") or ""),
        "latest_inbound_message_id": str(
            inbound.get("message_id") or inbound.get("inbound_message_id") or ""
        ),
    }
    identity_bound = bool(
        all(expected.values())
        and isinstance(offer_identity, Mapping)
        and isinstance(obligation_identity, Mapping)
        and all(
            str(offer_identity.get(key) or "") == value
            for key, value in expected.items()
        )
        and all(
            str(obligation_identity.get(key) or "") == value
            for key, value in expected.items()
        )
    )
    chronology = (
        obligations.get("public_chronology")
        if isinstance(obligations, Mapping)
        else None
    )
    latest_content_hash = hashlib.sha256(
        " ".join(str(inbound.get("content") or "").split()).encode("utf-8")
    ).hexdigest()
    chronology_tail = (
        chronology[-1]
        if isinstance(chronology, list)
        and chronology
        and isinstance(chronology[-1], Mapping)
        else {}
    )
    chronology_bound = bool(
        isinstance(chronology, list)
        and chronology
        and isinstance(chronology[-1], Mapping)
        and str(chronology_tail.get("message_id") or chronology_tail.get("id") or "")
        == expected["latest_inbound_message_id"]
        and chronology_tail.get("message_type") in (0, "incoming", "customer")
        and str(chronology_tail.get("content_sha256") or "") == latest_content_hash
    )
    response_bound = bool(
        reply
        and reply == _text(offer.get("customer_reply"), 1800)
        and decision.get("canonical_composition_authorized") is True
        and offer.get("should_reply") is True
    )
    authority_valid = bool(
        isinstance(authority, Mapping)
        and authority.get("allowed") is True
        and not authority.get("blockers")
        and not offer.get("evidence_errors")
    )
    raw_supported = obligations.get("supported_answer_facts") \
        if isinstance(obligations, Mapping) else None
    supported_rows_valid = bool(
        isinstance(raw_supported, list)
        and all(isinstance(fact, Mapping) for fact in raw_supported)
    )
    supported_rows = list(raw_supported) if supported_rows_valid else []
    supported = {str(fact.get("kind") or "") for fact in supported_rows}
    supported_provenance_valid = bool(
        supported_rows_valid
        and all(_canonical_supported_fact_valid(fact, offer) for fact in supported_rows)
    )
    supported_reply_coverage_valid = bool(
        supported_rows_valid
        and all(_canonical_supported_fact_covered(fact, reply) for fact in supported_rows)
    )
    raw_direct = obligations.get("explicit_direct_questions") \
        if isinstance(obligations, Mapping) else None
    direct_valid = bool(
        isinstance(raw_direct, list)
        and all(isinstance(question, str) and question for question in raw_direct)
    )
    direct = set(raw_direct) if direct_valid else set()
    support_by_question = {
        "price": {"price", "price_dependency"},
        "location": {"handover_location"},
        "availability": {"availability_boundary", "availability"},
        "product_guidance": {"piglet_size_guidance"},
    }
    delivery_answered = bool(
        "delivery" in direct
        and isinstance(offer.get("owner_exception"), Mapping)
        and offer["owner_exception"].get("type") == "livestock_delivery_decision"
        and re.search(r"\bdelivery\b.{0,80}\b(?:confirm|needs)\b", reply, re.I)
    )
    unanswered = sorted(
        question
        for question in direct
        if not (
            supported & support_by_question.get(question, set())
            or (question == "delivery" and delivery_answered)
        )
    )
    next_value = obligations.get("single_next_useful_question") \
        if isinstance(obligations, Mapping) else ""
    next_question = next_value if isinstance(next_value, str) else ""
    raw_dependencies = obligations.get("qualification_dependencies") \
        if isinstance(obligations, Mapping) else None
    dependencies_valid = bool(
        isinstance(raw_dependencies, list)
        and all(
            isinstance(value, str)
            and value in {"category", "quantity", "sex", "timing", "location"}
            for value in raw_dependencies
        )
    )
    raw_asked = authority.get("asked_fields") if isinstance(authority, Mapping) else None
    asked_valid = bool(
        isinstance(raw_asked, list)
        and all(isinstance(value, str) and value for value in raw_asked)
    )
    asked = set(raw_asked) if asked_valid else set()
    normalized_next = (
        "category" if next_question in {"size", "weight_range"} else next_question
    )
    next_question_valid = bool(
        not normalized_next
        or (
            normalized_next in {"category", "quantity", "sex", "timing", "location"}
            and dependencies_valid
            and raw_dependencies
            and raw_dependencies[0] == normalized_next
            and normalized_next in asked
        )
    )
    qualification_advanced = bool(normalized_next and next_question_valid)
    protected_safe = not bool(re.search(
        r"\b(?:reserve(?:d|ation)?|allocate(?:d|ion)?|order confirmed|"
        r"payment received|delivery (?:is|has been) confirmed|"
        r"collect(?:ion)? (?:at|from) (?:the )?farm)\b",
        reply, re.I,
    ))
    evidence_offer_progress = _canonical_offer_progress_valid(offer, reply)
    useful_progress = bool(
        (supported and supported_reply_coverage_valid)
        or qualification_advanced
        or delivery_answered
        or evidence_offer_progress
    )
    checks = {
        "canonical_packet_present": isinstance(obligations, Mapping),
        "canonical_contracts_versioned": bool(
            offer.get("contract_version") == CANONICAL_OFFER_VERSION
            and isinstance(obligations, Mapping)
            and obligations.get("contract_version") == CANONICAL_OBLIGATION_VERSION
        ),
        "canonical_obligation_schema_valid": bool(
            supported_rows_valid and direct_valid and asked_valid
            and dependencies_valid and next_question_valid
        ),
        "canonical_identity_bound": identity_bound,
        "canonical_chronology_bound": chronology_bound,
        "canonical_response_bound": response_bound,
        "canonical_authority_valid": authority_valid,
        "material_intents_covered": not unanswered,
        "supported_fact_provenance_valid": supported_provenance_valid,
        "supported_fact_reply_coverage_valid": supported_reply_coverage_valid,
        "qualification_advanced": not normalized_next or qualification_advanced,
        "not_pure_deferral": useful_progress,
        "customer_language_used": not _unexplained_internal_taxonomy(reply),
        "protected_commitments_absent": protected_safe,
        "supporting_evidence_valid": evidence.get("supporting_evidence_valid") is True,
        "claim_specific_provenance_valid": bool(
            lane == "live_stock" and supported_provenance_valid
        ),
        "concise": 0 < len(reply) <= 1800,
    }
    return {
        "version": CONTRACT_VERSION,
        "authority_source": "canonical_conversation_obligation_packet",
        "passed": all(checks.values()),
        "checks": checks,
        "blockers": [name for name, value in checks.items() if not value],
        "intents": sorted(direct),
        "unanswered_intents": unanswered,
        "missing_facts": list(obligations.get("qualification_dependencies") or [])
        if isinstance(obligations, Mapping) else [],
        "required_guidance": sorted(supported),
        "guidance_missing": [],
        "prohibited_claims": list(evidence.get("prohibited_claims") or []),
        "evidence_provenance": {
            "conversation_id_hash": _hash(inbound.get("conversation_id")),
            "inbound_message_id_hash": _hash(expected["latest_inbound_message_id"]),
            "supporting_evidence_valid": (
                evidence.get("supporting_evidence_valid") is True
            ),
            "canonical_offer_contract_version": str(offer.get("contract_version") or ""),
            "canonical_obligation_contract_version": str(
                obligations.get("contract_version") or ""
            ) if isinstance(obligations, Mapping) else "",
        },
        "legacy_diagnostics": {
            "intents": sorted(_intents(_text(inbound.get("content"), 1800))),
            "missing_fields": list(decision.get("missing_fields") or [])
            if isinstance(
                decision.get("missing_fields") or [], (list, tuple, set)
            ) else [],
            "authoritative": False,
        },
        "contains_customer_content": False,
        "sends_customer_message": False,
        "mutates_business_state": False,
    }


def _intents(content):
    intents = set()
    if re.search(
        r"(?:^\s*(?:where|location)\s*\??\s*$|"
        r"\bwhere\b.{0,30}\b(?:you|farm|located|based)\b|"
        r"\b(?:your|farm)\s+location\b|\bwhere\s+are\s+you\b)",
        content,
        re.I,
    ):
        intents.add("location")
    if re.search(r"\b(?:collect|collection|handover|pick\s*up)\b", content, re.I):
        intents.add("collection")
    if re.search(r"\b(?:price|cost|how much)\b", content, re.I):
        intents.add("price")
    if re.search(r"\b(?:available|availability|in stock|have any)\b", content, re.I):
        intents.add("availability")
    explicit_size_unknown = bool(re.search(
        r"\b(?:what|which)\s+(?:size|weight|kind|type)|"
        r"\b(?:do not|don't|dont)\s+know\b.{0,30}\b(?:size|weight|kind|type)\b",
        content,
        re.I,
    ))
    generic_pig = bool(
        re.search(r"\b(?:piglets?|pigs?)\b", content, re.I)
        and not re.search(
            r"\b(?:weaned\s+piglets?|weaners?|growing\s+pigs?|growers?|"
            r"larger\s+pigs?|finishers?|slaughter(?:-size)?|"
            r"\d+\s*(?:kg|kilograms?))\b",
            content,
            re.I,
        )
    )
    direct_size_question = bool(re.search(
        r"\b(?:what|which)\s+(?:is\s+an?\s+)?"
        r"(?:weaner|grower|finisher|slaughter-size|size|weight|kind|type)\b",
        content,
        re.I,
    ))
    if explicit_size_unknown or generic_pig or direct_size_question:
        intents.add("size")
    if re.search(
        r"(?:\b(?:male|female)\s+or\s+(?:male|female)\b|"
        r"\bwhat\s+sex\b|\bwhich\s+sex\b|\bsex\s+(?:do|are|is)\b)",
        content,
        re.I,
    ):
        intents.add("sex")
    if re.search(
        r"\b(?:breeding|breed(?:er|ing)?|raise\s+for\s+meat|"
        r"slaughter|intended\s+use|what\s+(?:type|kind)\s+of\s+pig)\b",
        content,
        re.I,
    ):
        intents.add("purpose")
    return intents


def _canonical_supported_fact_valid(fact, offer):
    kind = str(fact.get("kind") or "")
    provenance = fact.get("provenance")
    if not kind or provenance in (None, "", {}, []):
        return False
    if kind == "handover_location":
        return (
            fact.get("value") == "Riversdale or Albertinia"
            and provenance == "canonical_handover_policy"
        )
    if kind == "price":
        price = offer.get("price_evidence")
        pricing = price.get("pricing") if isinstance(price, Mapping) else None
        return bool(
            fact.get("value") not in (None, "")
            and isinstance(provenance, Mapping)
            and isinstance(pricing, Mapping)
            and provenance == pricing
            and provenance.get("pricing_id")
            and provenance.get("source") == "supabase"
            and str(fact.get("value")) == str(price.get("unit_price"))
        )
    if kind == "price_dependency":
        return (
            fact.get("value") == "size_or_weight_category_required"
            and provenance == "canonical_category_pricing_contract"
        )
    if kind == "availability_boundary":
        return (
            fact.get("value") == "current availability requires confirmation"
            and provenance == "canonical_inventory_freshness_contract"
        )
    if kind == "availability":
        availability = offer.get("availability_evidence")
        return bool(
            isinstance(provenance, Mapping)
            and isinstance(availability, Mapping)
            and provenance == availability
            and availability.get("evidence_complete") is True
            and str(availability.get("freshness") or "").lower() == "current"
            and (
                availability.get("observation_id")
                or availability.get("projection_id")
                or availability.get("observation_timestamp")
            )
            and fact.get("value") not in (None, "")
        )
    if kind == "piglet_size_guidance":
        return (
            fact.get("value") == {
                "small": "small piglets (about 2-6 kg)",
                "weaned": "weaned piglets (about 7-19 kg)",
            }
            and provenance == "canonical_livestock_categories"
        )
    return False


def _canonical_supported_fact_covered(fact, reply):
    kind = str(fact.get("kind") or "")
    if kind == "handover_location":
        return bool(re.search(r"\bRiversdale\b.*\bAlbertinia\b", reply, re.I))
    if kind == "price":
        return _reply_contains_money(reply, fact.get("value"))
    if kind == "price_dependency":
        return bool(re.search(r"\bprice\b.{0,50}\b(?:size|weight)\b.{0,30}\bcategory\b", reply, re.I))
    if kind == "availability_boundary":
        return bool(re.search(
            r"\b(?:availability|stock)\b.{0,60}\b(?:confirm|check|uncertain)",
            reply,
            re.I,
        ))
    if kind == "availability":
        return _has_affirmative_availability_answer(reply)
    if kind == "piglet_size_guidance":
        return bool(
            re.search(r"\b2\s*(?:-|to)\s*6\s*kg\b", reply, re.I)
            and re.search(r"\b7\s*(?:-|to)\s*19\s*kg\b", reply, re.I)
        )
    return False


def _reply_contains_money(reply, value):
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return False
    variants = {
        f"R{amount:,.2f}",
        f"R{amount:,.0f}",
        f"R {amount:,.2f}",
        f"R {amount:,.0f}",
    }
    return any(variant in reply for variant in variants)


def _canonical_offer_progress_valid(offer, reply):
    kind = str(offer.get("response_kind") or "")
    match = offer.get("match_evidence")
    availability = offer.get("availability_evidence")
    price = offer.get("price_evidence")
    if kind == "exact_supported_offer":
        return bool(
            isinstance(match, Mapping)
            and match.get("complete_fulfillment") is True
            and isinstance(availability, Mapping)
            and availability.get("evidence_complete") is True
            and str(availability.get("freshness") or "").lower() == "current"
            and isinstance(price, Mapping)
            and isinstance(price.get("pricing"), Mapping)
            and price["pricing"].get("pricing_id")
            and price["pricing"].get("source") == "supabase"
            and _reply_contains_money(reply, price.get("unit_price"))
            and _reply_contains_money(reply, price.get("estimated_total"))
            and "current sale-eligible list" in reply.lower()
        )
    if kind == "closest_supported_alternatives":
        selected = offer.get("selected_alternative_evidence")
        return bool(
            isinstance(selected, list)
            and selected
            and all(
                isinstance(row, Mapping)
                and row.get("pig_id")
                and row.get("pricing_id")
                and row.get("price_source") == "supabase"
                and row.get("unit_price") not in (None, "")
                for row in selected
            )
            and "closest supported option" in reply.lower()
            and all(_reply_contains_money(reply, row.get("unit_price")) for row in selected)
        )
    if kind == "weekly_weight_reassessment":
        return bool(
            isinstance(match, Mapping)
            and offer.get("retained_facts")
            and re.search(r"\breassess\b.{0,80}\bweights\b|\bweights\b.{0,80}\breassess\b", reply, re.I)
        )
    return False


def _required_guidance(lane, intents, content, missing):
    required = set()
    generic_unknown = bool(
        re.search(r"\b(?:piglets?|pigs?)\b", content, re.I)
        and not re.search(
            r"\b(?:weaned\s+piglets?|weaners?|growing\s+pigs?|growers?|"
            r"larger\s+pigs?|finishers?|slaughter(?:-size)?|"
            r"\d+\s*(?:kg|kilograms?))\b",
            content,
            re.I,
        )
    )
    if lane == "live_stock" and "size" in intents and (
        "size" in missing or "weight_range" in missing or generic_unknown
    ):
        required.add("customer_friendly_size_choices")
    if "location" in intents or "collection" in intents:
        required.add("location_or_collection_guidance")
    return required


def _covers_size_guidance(reply, *, minimum_bands):
    bands = re.findall(
        r"\b(?:2\s*(?:to|-|–)\s*6|7\s*(?:to|-|–)\s*19|"
        r"20\s*(?:to|-|–)\s*49|50\s*(?:to|-|–)\s*79|80)\s*kg\b",
        reply,
        re.I,
    )
    return len(bands) >= minimum_bands


def _covers_location(reply):
    declarative = re.sub(r"[^.!?]*\?", " ", reply)
    if re.search(
        r"\b(?:not|isn't|aren't|never)\b.{0,30}"
        r"\b(?:based|located|riversdale|albertinia|western cape)\b",
        declarative,
        re.I,
    ):
        return False
    return bool(re.search(
        r"\b(?:we|our\s+farm)\s+(?:are|are\s+based|is|is\s+based|"
        r"are\s+located|is\s+located)\s+(?:near|in|outside)\s+"
        r"(?:riversdale|albertinia|the\s+western\s+cape)\b|"
        r"\bbased\s+near\s+riversdale\b",
        declarative,
        re.I,
    ))


def _covers_collection(reply):
    declarative = re.sub(r"[^.!?]*\?", " ", reply)
    if re.search(
        r"\b(?:free|nationwide|guaranteed|included)\b.{0,40}"
        r"\b(?:collection|pick\s*up|handover)\b|"
        r"\b(?:collection|pick\s*up|handover)\b.{0,40}"
        r"\b(?:free|nationwide|guaranteed|included)\b",
        declarative,
        re.I,
    ):
        return False
    return bool(re.search(
        r"\bcollection\s+is\s+arranged(?:\s+(?:in|near)\s+"
        r"(?:riversdale|albertinia))?(?=[.!?]|$)|"
        r"\b(?:pick\s*up|handover)\s+is\s+arranged(?=[.!?]|$)",
        declarative,
        re.I,
    ))


def _covers_sex(reply):
    return bool(re.search(
        r"\b(?:male|female|either|mixture|mix|sex preference)\b",
        reply,
        re.I,
    ))


def _covers_purpose(reply):
    return bool(re.search(
        r"\b(?:breeding|breed|raise\s+for\s+meat|meat|slaughter|"
        r"intended\s+use|purpose)\b",
        reply,
        re.I,
    ))


def _covers_or_qualifies(reply, intent, *, availability_current=False):
    if intent == "price":
        return bool(re.search(
            r"(?:\bR\s?\d|\b\d[\d ,.]*\s*(?:rand|zar)\b|"
            r"\bprice\b.{0,50}\b(?:confirm|check|current)|"
            r"\bconfirm\b.{0,50}\bprice\b)",
            reply,
            re.I,
        ))
    qualified = bool(re.search(
        r"\b(?:available|availability|in stock)\b.{0,60}\b(?:confirm(?:ing)?|check(?:ing)?|current)|"
        r"\b(?:confirm(?:ing)?|check(?:ing)?)\b.{0,60}\b(?:available|availability|stock)\b",
        reply,
        re.I,
    ))
    affirmative = bool(re.search(
        r"\b(?:we|i)\s+(?:currently\s+)?have\b.{0,60}\bavailable\b|"
        r"\b(?:is|are)\s+(?:currently\s+)?available\b|"
        r"\b(?:we\s+have|there\s+(?:is|are))\b.{0,60}\bin stock\b",
        reply,
        re.I,
    ))
    return qualified or (availability_current and affirmative)


def _has_supported_price_answer(reply):
    return bool(re.search(
        r"(?:\bR\s?\d|\b\d[\d ,.]*\s*(?:rand|zar)\b)",
        reply,
        re.I,
    ))


def _has_affirmative_availability_answer(reply):
    return bool(re.search(
        r"\b(?:we|i)\s+(?:currently\s+)?have\b.{0,60}\bavailable\b|"
        r"\b(?:is|are)\s+(?:currently\s+)?available\b|"
        r"\b(?:we\s+have|there\s+(?:is|are))\b.{0,60}\bin stock\b",
        reply,
        re.I,
    ))


def _asked_missing_facts(reply, missing):
    questions = " ".join(re.findall(r"[^?]*\?", reply))
    patterns = {
        "quantity": r"\b(?:how many|quantity)\b",
        "sex": r"\b(?:male|female|either|mixture|mix)\b",
        "size": r"\b(?:size|weight|kg|piglet|weaned|growing|larger|slaughter)\b",
        "weight_range": r"\b(?:size|weight|kg|piglet|weaned|growing|larger|slaughter)\b",
        "location": r"\b(?:where|location|area|collect|delivery)\b",
        "timing": r"\b(?:when|date|week|month|timing)\b",
    }
    return {
        field for field, pattern in patterns.items()
        if field in missing and re.search(pattern, questions, re.I)
    }


def _has_useful_question(reply):
    questions = " ".join(re.findall(r"[^?]*\?", reply))
    return bool(re.search(
        r"\b(?:size|weight|kg|how many|quantity|male|female|either|mixture|"
        r"where|location|area|collect|delivery|when|date|week|month)\b",
        questions,
        re.I,
    ))
def _unexplained_internal_taxonomy(reply):
    return bool(
        re.search(
            r"\b(?:young\s+piglets?|weaner\s+piglets?|grower\s+pigs?|"
            r"finisher\s+pigs?)\b",
            reply,
            re.I,
        )
        and not re.search(r"\b(?:kg|small|weaned|growing|larger|slaughter-size)\b", reply, re.I)
    )


def _field_name(value):
    field = str(value or "").split(".")[-1].strip().lower()
    if field == "category":
        return "size"
    if field == "collection_location":
        return "location"
    return field


def _text(value, limit):
    return str(value or "").strip()[:limit]


def _hash(value):
    return hashlib.sha256(str(value or "").encode()).hexdigest()[:16]
