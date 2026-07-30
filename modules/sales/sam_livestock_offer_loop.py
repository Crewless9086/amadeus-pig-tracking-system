"""Canonical evidence-to-offer composition for customer-facing Livestock replies."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re
from typing import Any, Mapping


CONTRACT_VERSION = "sam_livestock_evidence_offer_v1"
HANDOVER_POINTS = ("Riversdale", "Albertinia")
QUALIFICATION_ORDER = ("category", "quantity", "sex", "timing", "location")
WEIGHT_CHOICES = {
    "Young Piglets": "small piglets (about 2–6 kg)",
    "Weaner Piglets": "weaned piglets (about 7–19 kg)",
    "Grower Pigs": "growing pigs (about 20–49 kg)",
    "Finisher Pigs": "larger pigs (about 50–79 kg)",
    "Ready for Slaughter": "slaughter-size pigs (80 kg and above)",
}
CATEGORY_ALIASES = {
    "piglet": "Young Piglets",
    "piglets": "Young Piglets",
    "young piglets": "Young Piglets",
    "weaner": "Weaner Piglets",
    "weaners": "Weaner Piglets",
    "weaner piglets": "Weaner Piglets",
    "grower": "Grower Pigs",
    "growers": "Grower Pigs",
    "grower pigs": "Grower Pigs",
    "finisher": "Finisher Pigs",
    "finishers": "Finisher Pigs",
    "finisher pigs": "Finisher Pigs",
    "ready for slaughter": "Ready for Slaughter",
}

_COLLECTION_OR_PICKUP = re.compile(r"\b(?:collect(?:ion)?|pick\s*up|pickup|afhaal)\b", re.I)
_GENERIC_DETAIL = re.compile(
    r"\bwhat\s+(?:detail|details|information)\s+should\s+i\s+(?:note|record)\b",
    re.I,
)
_DELIVERY_PROMISE = re.compile(
    r"\b(?:we|i)\s+(?:can|will)\s+deliver\b|\bdelivery\s+(?:is|will be)\s+(?:available|confirmed)\b",
    re.I,
)


def build_canonical_livestock_offer(
    *,
    inbound: Mapping[str, Any],
    facts: Mapping[str, Any],
    chronology: list[Mapping[str, Any]],
    availability: Mapping[str, Any],
    match_packet: Mapping[str, Any],
    price_packet: Mapping[str, Any],
    protected_decisions: list[Mapping[str, Any]] | None = None,
    proposed_reply: str = "",
    proposed_source: str = "",
    evidence_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind all evidence once and compose the only Livestock customer draft."""
    facts = dict(facts or {})
    chronology = [dict(row) for row in chronology or [] if isinstance(row, Mapping)]
    evidence_errors = _evidence_errors(inbound, chronology)
    missing = [
        field
        for field in QUALIFICATION_ORDER
        if _qualification_blank(field, facts.get(field))
    ]
    protected = [dict(row) for row in protected_decisions or [] if isinstance(row, Mapping)]
    evidence_context = dict(evidence_context or {})
    latest = str(inbound.get("content") or "").strip()
    customer_reply = ""
    response_kind = "no_reply"
    owner_exception = None

    proposed_authority = validate_customer_livestock_reply(
        proposed_reply,
        facts=facts,
        response_kind="candidate",
        availability=availability,
        price_packet=price_packet,
    )
    if evidence_errors:
        response_kind = "identity_or_chronology_blocked"
    elif _acknowledgement_only(latest):
        response_kind = "natural_close"
    elif facts.get("reservation_requested"):
        response_kind = "protected_reservation_request"
        customer_reply = (
            "I have noted that you are interested, but I cannot say the pigs "
            "are held until the owner confirms a reservation."
        )
        owner_exception = {
            "type": "livestock_reservation_decision",
            "decision_required": "Confirm whether the requested animals may be reserved.",
        }
    elif facts.get("payment_requested") or facts.get("payment_proof_received"):
        response_kind = "protected_payment_request"
        customer_reply = (
            "Thank you. Proof of payment helps with the record, but payment "
            "can only be confirmed after the money reflects in the farm account."
        )
        owner_exception = {
            "type": "livestock_payment_decision",
            "decision_required": "Verify reflected payment before confirming it.",
        }
    elif _delivery_request(latest):
        response_kind = "protected_delivery_request"
        customer_reply = (
            "Live-pig handover is normally arranged in Riversdale or Albertinia. "
            "A delivery or different arrangement needs the owner to confirm it first."
        )
        if _blank(facts.get("location")):
            customer_reply += " Which town or area would the delivery need to be to?"
        owner_exception = {
            "type": "livestock_delivery_decision",
            "decision_required": "Confirm whether delivery or another handover arrangement can be offered, including terms.",
        }
    elif (
        _small_talk(latest)
        and not _livestock_signal(latest)
        and facts.get("front_door_context_transfer") is not True
    ):
        response_kind = "warm_discovery"
        customer_reply = "Good day! How can I help with your live-pig enquiry?"
    elif missing:
        response_kind = "qualification"
        customer_reply = _qualification_reply(missing[0], facts)
    elif protected:
        response_kind = "protected_owner_decision"
        owner_exception = {
            "type": "livestock_protected_decision",
            "decision_required": (
                "Review the exact protected quote, order, delivery, ambiguity, "
                "or commercial decision before any customer commitment."
            ),
            "packets": protected,
        }
    elif (
        match_packet.get("complete_fulfillment") is not True
        and availability.get("next_weight_reassessment_date")
    ):
        response_kind = "weekly_weight_reassessment"
        customer_reply = _weekly_reassessment_reply(
            facts,
            availability.get("next_weight_reassessment_date"),
            match_packet,
        )
    else:
        response_kind, customer_reply = _offer_reply(
            facts=facts,
            availability=availability,
            match_packet=match_packet,
            price_packet=price_packet,
        )
    if (
        not customer_reply
        and proposed_reply
        and proposed_authority["allowed"] is True
        and not protected
        and not evidence_errors
        and response_kind not in {"natural_close", "identity_or_chronology_blocked"}
    ):
        response_kind = "canonical_validated_candidate"
        customer_reply = proposed_reply

    authority_price_packet = dict(price_packet or {})
    if response_kind in {"closest_supported_alternatives", "weekly_weight_reassessment"}:
        authority_price_packet["can_answer_price"] = True
    authority = validate_customer_livestock_reply(
        customer_reply,
        facts=facts,
        response_kind=response_kind,
        availability=availability,
        price_packet=authority_price_packet,
    )
    if customer_reply and authority["allowed"] is not True:
        customer_reply = ""
        response_kind = "composition_authority_blocked"
        evidence_errors.extend(authority["blockers"])

    return {
        "contract_version": CONTRACT_VERSION,
        "identity": {
            "account_id": str(inbound.get("account_id") or ""),
            "inbox_id": str(inbound.get("inbox_id") or ""),
            "contact_id": str(inbound.get("contact_id") or ""),
            "conversation_id": str(inbound.get("conversation_id") or ""),
            "latest_inbound_message_id": str(inbound.get("message_id") or ""),
        },
        "chronology_message_count": len(chronology),
        "retained_facts": facts,
        "availability_evidence": dict(availability or {}),
        "match_evidence": dict(match_packet or {}),
        "price_evidence": dict(price_packet or {}),
        "protected_decisions": protected,
        "returning_customer_context": dict(
            evidence_context.get("returning_customer_context") or {}
        ),
        "campaign_or_post_context": dict(
            evidence_context.get("campaign_or_post_context") or {}
        ),
        "farm_knowledge": dict(evidence_context.get("farm_knowledge") or {}),
        "delivery_claims": list(evidence_context.get("delivery_claims") or []),
        "delivery_outcomes": list(evidence_context.get("delivery_outcomes") or []),
        "quarantines": list(evidence_context.get("quarantines") or []),
        "missing_fields": missing,
        "response_kind": response_kind,
        "customer_reply": customer_reply,
        "should_reply": bool(customer_reply),
        "owner_exception": owner_exception,
        "authority": authority,
        "proposed_candidate": {
            "source": proposed_source,
            "accepted": bool(proposed_reply and proposed_authority["allowed"] is True),
            "authority": proposed_authority,
        },
        "evidence_errors": evidence_errors,
        "handover_policy": {
            "normal_points": list(HANDOVER_POINTS),
            "farm_collection_customer_claim_allowed": False,
            "delivery_requires_owner_decision": True,
        },
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def validate_customer_livestock_reply(
    reply: Any,
    *,
    facts: Mapping[str, Any] | None = None,
    response_kind: str = "",
    availability: Mapping[str, Any] | None = None,
    price_packet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    text = str(reply or "").strip()
    blockers = []
    collection = _COLLECTION_OR_PICKUP.search(text)
    authorized_handover = bool(
        re.search(r"\bhandover\b", text, re.I)
        and re.search(r"\bRiversdale\b", text, re.I)
        and re.search(r"\bAlbertinia\b", text, re.I)
    )
    if collection and not authorized_handover:
        blockers.append("collection_or_pickup_claim_prohibited")
    if _GENERIC_DETAIL.search(text):
        blockers.append("context_blind_generic_question_prohibited")
    if _DELIVERY_PROMISE.search(text):
        blockers.append("delivery_commitment_prohibited")
    if re.search(r"\b(?:definitely|currently)\s+available\b", text, re.I):
        blockers.append("unsupported_availability_claim_prohibited")
    if re.search(r"\b(?:R|ZAR)\s?\d|R\d", text, re.I):
        if not price_packet or price_packet.get("can_answer_price") is not True:
            blockers.append("price_claim_without_active_price_evidence")
    if re.search(r"\b(?:available|eligible|in stock|current sale-eligible)\b", text, re.I):
        if not _availability_current(availability or {}):
            blockers.append("availability_claim_without_current_complete_evidence")
    if re.fullmatch(
        r".*(?:check|confirm|review|get back to you|needs confirmation)[.!]?",
        text,
        re.I,
    ) and "?" not in text:
        blockers.append("safe_but_useless_deferral")
    facts = facts or {}
    asked = _asked_fields(text)
    repeated = sorted(field for field in asked if not _blank(facts.get(field)))
    if repeated and response_kind in {"qualification", "candidate"}:
        blockers.extend(f"repeats_known_{field}" for field in repeated)
    if response_kind == "qualification" and len(asked) != 1:
        blockers.append("qualification_must_ask_one_smallest_question")
    return {"allowed": not blockers, "blockers": blockers, "asked_fields": sorted(asked)}


def _qualification_reply(field: str, facts: Mapping[str, Any]) -> str:
    if field == "category":
        return (
            "What size would suit you: small piglets (about 2–6 kg), weaned piglets "
            "(about 7–19 kg), growing pigs (about 20–49 kg), larger pigs "
            "(about 50–79 kg), or slaughter-size pigs (80 kg and above)?"
        )
    if field == "quantity":
        descriptor = _plain_product(facts)
        return f"How many {descriptor} would you like?"
    if field == "sex":
        return "Would you prefer males, females, or a mixture?"
    if field == "timing":
        return "When would you ideally need them?"
    return "Would Riversdale or Albertinia suit you for handover?"


def _offer_reply(*, facts, availability, match_packet, price_packet):
    quantity = int(facts.get("quantity") or 0)
    category = _normal_category(facts.get("category"))
    label = WEIGHT_CHOICES.get(category, _plain_product(facts))
    exact_count = int(match_packet.get("exact_match_count") or 0)
    unit = price_packet.get("unit_price")
    total = price_packet.get("estimated_total")
    evidence_complete = _availability_current(availability)
    observed = str(availability.get("observation_timestamp") or "")

    exact_supported = bool(
        match_packet.get("complete_fulfillment") is True
        and exact_count >= quantity
        and len(match_packet.get("matched_sample") or []) >= quantity
        and quantity > 0
        and evidence_complete
        and price_packet.get("can_answer_price") is True
        and unit not in ("", None)
        and total not in ("", None)
        and Decimal(str(total)) == Decimal(str(unit)) * quantity
    )
    if exact_supported:
        return (
            "exact_supported_offer",
            f"The current sale-eligible list has {quantity} {label} matching your request "
            f"at {_money(unit)} each, giving a subtotal of {_money(total)}. "
            "This is a supported price summary, not a reservation or final commitment. "
            "Would you like me to prepare it for owner review?"
        )
    alternatives = _alternatives(match_packet, quantity)
    if alternatives:
        evidence_position = (
            "The exact group is not fully matched on the current sale-eligible list. "
            if evidence_complete
            else "The last recorded list did not fully match the exact group. "
        )
        stale = (
            f" The latest weight evidence is dated {observed}, so current weights must be confirmed."
            if observed and not evidence_complete
            else ""
        )
        return (
            "closest_supported_alternatives",
            f"{evidence_position}The closest supported option is {alternatives}.{stale} "
            "Would that option suit you for owner review?"
        )
    return (
        "evidence_bounded_progression",
        "I cannot confirm current stock or price from the available evidence yet. "
        "Your size, quantity, sex, timing and handover preference are recorded, "
        "so I can send the exact request for owner confirmation without asking you to repeat it."
    )


def _alternatives(match_packet, quantity):
    rows = [
        row for row in match_packet.get("considered_sample") or []
        if (
            isinstance(row, Mapping)
            and row.get("live_stock_sale_eligible") is True
            and row.get("alternative_rank") not in ("", None)
        )
    ]
    if not rows:
        return ""
    rows.sort(key=lambda row: (int(row["alternative_rank"]), str(row.get("pig_id") or "")))
    selected = rows[: max(quantity, 1)]
    groups = {}
    for row in selected:
        category = str(row.get("sale_category") or row.get("suggested_price_category") or "nearby weight")
        pricing = row.get("pricing") if isinstance(row.get("pricing"), Mapping) else {}
        price = pricing.get("unit_price")
        if not pricing.get("pricing_id") or not pricing.get("source"):
            price = None
        groups.setdefault((category, price), 0)
        groups[(category, price)] += 1
    clauses = []
    total = Decimal("0")
    priced = True
    for (category, price), count in groups.items():
        label = WEIGHT_CHOICES.get(category, category)
        if price in ("", None):
            priced = False
            clauses.append(f"{count} {label}")
        else:
            subtotal = Decimal(str(price)) * count
            total += subtotal
            clauses.append(f"{count} {label} at {_money(price)} each ({_money(subtotal)})")
    joined = ", ".join(clauses)
    return f"{joined}; total {_money(total)}" if priced else joined


def _weekly_reassessment_reply(facts, reassessment_date, match_packet):
    quantity = int(facts.get("quantity") or 0)
    sex = str(facts.get("sex") or "requested sex mix")
    weight = str(facts.get("weight_range") or facts.get("category") or "preferred size")
    timing = str(facts.get("timing") or "the requested date")
    recorded = _alternatives(match_packet, quantity)
    current = (
        f" The closest recorded options are {recorded}."
        if recorded
        else ""
    )
    return (
        f"I have noted {quantity} pigs ({sex}), around {weight}, for {timing}. "
        "We weigh the pigs weekly, so specific pigs cannot be confirmed this far "
        f"in advance.{current} We will reassess the updated weights on "
        f"{reassessment_date} and then confirm the best supported combination "
        "and current category prices. This does not reserve or promise future stock."
    )


def _evidence_errors(inbound, chronology):
    errors = []
    identity = {
        key: str(inbound.get(key) or "")
        for key in ("account_id", "inbox_id", "contact_id", "conversation_id")
    }
    if not all(identity.values()) or not str(inbound.get("message_id") or ""):
        errors.append("exact_identity_incomplete")
    if not chronology:
        errors.append("complete_public_chronology_missing")
        return errors
    timestamps = []
    for row in chronology:
        latest_scope = {
            key: str(row.get(key) or row.get("identity", {}).get(key) or "")
            for key in ("account_id", "inbox_id", "contact_id", "conversation_id")
        }
        if any(latest_scope[key] and latest_scope[key] != identity[key] for key in identity):
            errors.append("chronology_scope_identity_mismatch")
            break
        timestamps.append(str(row.get("created_at") or ""))
    if any(timestamps) and timestamps != sorted(timestamps):
        errors.append("chronology_order_invalid")
    latest = chronology[-1]
    latest_id = str(latest.get("id") or latest.get("message_id") or "")
    if latest_id != str(inbound.get("message_id") or ""):
        errors.append("latest_inbound_not_bound_to_packet")
    if latest.get("message_type") not in (0, "incoming", "customer"):
        errors.append("chronology_tail_not_customer_inbound")
    if str(latest.get("content") or "") != str(inbound.get("content") or ""):
        errors.append("latest_inbound_content_mismatch")
    return errors


def _asked_fields(text):
    fields = set()
    patterns = {
        "category": r"\bwhat size|which size|what type|which type\b",
        "quantity": r"\bhow many\b",
        "sex": r"\b(?:males?|females?|sex preference|mixture)\b.*\?",
        "timing": r"\bwhen\b.*\?",
        "location": r"\b(?:where|riversdale or albertinia)\b.*\?",
    }
    for field, pattern in patterns.items():
        if re.search(pattern, text, re.I):
            fields.add(field)
    return fields


def _plain_product(facts):
    category = _normal_category(facts.get("category"))
    return WEIGHT_CHOICES.get(category, "live pigs")


def _delivery_request(text):
    return bool(re.search(r"\b(?:deliver|delivery|transport|drop[- ]?off)\b", text, re.I))


def _acknowledgement_only(text):
    return bool(re.fullmatch(r"\s*(?:thanks?|thank you|okay|ok|great|👍|🙏)[\s.!🙏👍]*", text, re.I))


def _small_talk(text):
    return bool(re.search(r"\b(?:hi|hello|good (?:day|morning|afternoon)|how are you)\b", text, re.I))


def _livestock_signal(text):
    return bool(re.search(r"\b(?:pig|piglet|weaner|grower|finisher|sow|boar|gilt)\w*\b", text, re.I))


def _money(value):
    amount = Decimal(str(value))
    return f"R{amount:,.2f}"


def _blank(value):
    return value is None or value is False or not str(value).strip() or str(value).strip().lower() == "unknown"


def _qualification_blank(field, value):
    if _blank(value):
        return True
    return field != "sex" and str(value).strip().casefold() in {"any", "either"}


def _normal_category(value):
    text = " ".join(str(value or "").replace("_", " ").split()).casefold()
    return CATEGORY_ALIASES.get(text, str(value or ""))


def _availability_current(availability):
    if availability.get("success") is not True or availability.get("evidence_complete") is not True:
        return False
    raw = str(availability.get("observation_timestamp") or "")
    if not raw:
        return False
    try:
        observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    age = datetime.now(timezone.utc) - observed.astimezone(timezone.utc)
    return timedelta(0) <= age <= timedelta(days=7)
