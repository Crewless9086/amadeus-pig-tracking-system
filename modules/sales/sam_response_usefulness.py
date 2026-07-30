"""Deterministic, evidence-aware pre-send usefulness contract for SAM."""

from __future__ import annotations

import hashlib
import re
from typing import Mapping


CONTRACT_VERSION = "sam_response_usefulness_v1"
GUIDANCE_POLICY_ID = "sam_live_stock_customer_guidance_v1"
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
