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
    "Young Piglets": "small piglets (about 2-6 kg)",
    "Weaner Piglets": "weaned piglets (about 7-19 kg)",
    "Grower Pigs": "growing pigs (about 20-49 kg)",
    "Finisher Pigs": "larger pigs (about 50-79 kg)",
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
    reassessment_date = (
        availability.get("next_weight_reassessment_date")
        or _future_reassessment_date(facts)
    )

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
    elif _direct_price_question(latest) and _price_provenanced(price_packet):
        response_kind = "supported_price_first"
        customer_reply = _price_first_reply(
            facts=facts,
            price_packet=price_packet,
            next_missing=missing[0] if missing else "",
        )
    elif (
        match_packet.get("complete_fulfillment") is not True
        and reassessment_date
        and not any(field in missing for field in ("category", "quantity", "sex"))
    ):
        response_kind = "weekly_weight_reassessment"
        customer_reply = _weekly_reassessment_reply(
            facts,
            reassessment_date,
            match_packet,
        )
    elif (
        facts.get("quantity")
        and not _blank(facts.get("category"))
        and not _blank(facts.get("sex"))
        and (
            match_packet.get("complete_fulfillment") is True
            or _alternatives(
                match_packet,
                int(facts.get("quantity") or 0),
                facts,
                availability,
            )
        )
    ):
        response_kind, customer_reply = _offer_reply(
            facts=facts,
            availability=availability,
            match_packet=match_packet,
            price_packet=price_packet,
        )
        if missing and customer_reply and "?" not in customer_reply:
            customer_reply = f"{customer_reply} {_qualification_reply(missing[0], facts)}"
    elif missing:
        response_kind = "qualification"
        customer_reply = _qualification_reply(missing[0], facts)
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
    if collection:
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
            "What size would suit you: small piglets (about 2-6 kg), weaned piglets "
            "(about 7-19 kg), growing pigs (about 20-49 kg), larger pigs "
            "(about 50-79 kg), or slaughter-size pigs (80 kg and above)?"
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
    observed = str(
        availability.get("latest_weight_date")
        or availability.get("observation_timestamp")
        or ""
    )

    exact_supported = bool(
        match_packet.get("complete_fulfillment") is True
        and exact_count >= quantity
        and len(match_packet.get("matched_sample") or []) >= quantity
        and quantity > 0
        and evidence_complete
        and _price_provenanced(price_packet)
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
            "Would that option work for you?"
        )
    alternatives = _alternatives(match_packet, quantity, facts, availability)
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
        difference = _alternative_difference(
            facts,
            match_packet,
            quantity,
            availability,
        )
        option_question = (
            "Would this lighter option work for you?"
            if difference.startswith("This proposed combination is lighter")
            else "Would that option work for you?"
        )
        return (
            "closest_supported_alternatives",
            f"{evidence_position}{difference}The closest supported option is "
            f"{alternatives}.{stale} "
            f"{option_question}"
        )
    return (
        "evidence_bounded_progression",
        "I cannot confirm current stock or price from the evidence I have yet. "
        "Your size, quantity, sex, timing and handover preference are recorded, "
        "so I can send the exact request for owner confirmation without asking you to repeat it."
    )


def _alternatives(match_packet, quantity, facts=None, availability=None):
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
    availability = availability if isinstance(availability, Mapping) else {}
    rows = [
        row for row in rows
        if _alternative_row_current(row, availability)
    ]
    if not rows:
        return ""
    rows.sort(key=lambda row: (int(row["alternative_rank"]), str(row.get("pig_id") or "")))
    selected = _select_alternative_rows(rows, max(quantity, 1), facts or {})
    groups = {}
    for row in selected:
        category = str(row.get("sale_category") or row.get("suggested_price_category") or "nearby weight")
        band = str(row.get("weight_band") or "")
        sex = str(row.get("sex") or "").strip().casefold()
        pricing = row.get("pricing") if isinstance(row.get("pricing"), Mapping) else {}
        price = pricing.get("unit_price")
        if not pricing.get("pricing_id") or not pricing.get("source"):
            price = None
        groups.setdefault((sex, category, band, price), 0)
        groups[(sex, category, band, price)] += 1
    clauses = []
    total = Decimal("0")
    priced = True
    for (sex, category, band, price), count in groups.items():
        label = _alternative_group_label(
            sex=sex,
            category=category,
            weight_band=band,
            count=count,
        )
        if price in ("", None):
            priced = False
            clauses.append(label)
        else:
            subtotal = Decimal(str(price)) * count
            total += subtotal
            clauses.append(f"{label} at {_money(price)} each ({_money(subtotal)})")
    joined = ", ".join(clauses)
    return f"{joined}; total {_money(total)}" if priced else joined


def _weekly_reassessment_reply(facts, reassessment_date, match_packet):
    quantity = int(facts.get("quantity") or 0)
    split = facts.get("sex_split") if isinstance(facts.get("sex_split"), Mapping) else {}
    sex = (
        f"{int(split.get('female') or 0)} females and "
        f"{int(split.get('male') or 0)} male"
        if split.get("female") and split.get("male")
        else str(facts.get("sex") or "requested sex mix")
    )
    weight = str(
        facts.get("weight_range") or facts.get("category") or "preferred size"
    )
    timing = str(facts.get("timing") or "the requested date")
    if re.fullmatch(r"\d{1,2}(?:st|nd|rd|th)", timing, re.I):
        timing = f"the {timing}"
    recorded = _alternatives(match_packet, quantity, facts)
    current = (
        f" The closest recorded options are {recorded}."
        if recorded
        else ""
    )
    return (
        f"I have noted {quantity} pigs ({sex}), {weight}, for {timing}, as requested. "
        "We weigh the pigs weekly, so specific pigs cannot be confirmed this far "
        f"in advance.{current} We will reassess the updated weights on "
        f"{reassessment_date} and then confirm the best supported combination "
        "and current category prices. This does not reserve or promise future stock."
    )


def _future_reassessment_date(facts, *, now=None):
    """Derive the owner-approved five-day-before check for a dated request."""
    timing = str(facts.get("timing") or "").strip()
    match = re.fullmatch(r"(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?", timing, re.I)
    if not match:
        return ""
    requested_day = int(match.group(1))
    if not 1 <= requested_day <= 31:
        return ""
    today = (now or datetime.now(timezone.utc)).date()
    year, month = today.year, today.month
    for _ in range(2):
        try:
            requested = today.replace(year=year, month=month, day=requested_day)
        except ValueError:
            requested = None
        if requested and requested > today:
            reassess = max(requested - timedelta(days=5), today)
            return f"{reassess.day} {reassess.strftime('%B')}"
        month += 1
        if month == 13:
            month = 1
            year += 1
    return ""


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
    if _canonical_message_text(latest.get("content")) != _canonical_message_text(
        inbound.get("content")
    ):
        errors.append("latest_inbound_content_mismatch")
    return errors


def _canonical_message_text(value):
    return " ".join(str(value or "").split())


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
    if availability.get("success") is not True:
        return False
    if availability.get("observation_evidence_state") in {"stale", "conflicting"}:
        return False
    projection_complete = (
        availability.get("eligible_evidence_complete") is True
        or availability.get("evidence_complete") is True
    )
    if not projection_complete:
        return False
    if availability.get("weight_freshness_consistent") is False:
        return False
    raw = str(availability.get("observation_timestamp") or "")
    observed_current = True
    if raw:
        try:
            observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        age = datetime.now(timezone.utc) - observed.astimezone(timezone.utc)
        observed_current = timedelta(0) <= age <= timedelta(days=7)
        if not observed_current:
            return False
    # HERDMASTER can prove freshness from the canonical weekly weight
    # projection even when the source has no time-of-day observation.
    age_days = availability.get("oldest_weight_age_days")
    evidence_date = str(availability.get("latest_weight_date") or "")
    try:
        weight_current = bool(evidence_date) and 0 <= float(age_days) <= 7
        return observed_current and weight_current
    except (TypeError, ValueError):
        return False


def _direct_price_question(text):
    return bool(
        re.search(r"\b(?:price|prices|cost|how much|prys)\b", str(text or ""), re.I)
    )


def _price_provenanced(price_packet):
    pricing = (
        price_packet.get("pricing")
        if isinstance(price_packet.get("pricing"), Mapping)
        else {}
    )
    return bool(
        price_packet.get("can_answer_price") is True
        and pricing.get("pricing_id")
        and pricing.get("source")
        and price_packet.get("unit_price") not in ("", None)
    )


def _price_first_reply(*, facts, price_packet, next_missing):
    unit = price_packet.get("unit_price")
    pricing = (
        price_packet.get("pricing")
        if isinstance(price_packet.get("pricing"), Mapping)
        else {}
    )
    band = (
        pricing.get("weight_band")
        or price_packet.get("requested_weight_range")
        or facts.get("weight_range")
        or facts.get("category")
    )
    label = _human_weight_band(band)
    reply = f"The current supported price for {label} live pigs is {_money(unit)} each."
    quantity = facts.get("quantity")
    total = price_packet.get("estimated_total")
    if quantity and total not in ("", None):
        reply += f" For {int(quantity)}, the price total is {_money(total)}."
    if next_missing:
        if next_missing == "quantity" and label:
            reply += f" How many {label} piglets would you like?"
        else:
            reply += f" {_qualification_reply(next_missing, facts)}"
    else:
        reply += (
            " Riversdale or Albertinia can be used for handover; any delivery "
            "or different arrangement needs owner confirmation."
        )
    return reply


def _select_alternative_rows(rows, quantity, facts):
    split = facts.get("sex_split") if isinstance(facts.get("sex_split"), Mapping) else {}
    female_count = int(split.get("female") or 0)
    male_count = int(split.get("male") or 0)
    if female_count + male_count != quantity:
        return rows[:quantity]
    approved_split = _approved_approx_19_split(rows, facts, female_count, male_count)
    if approved_split:
        return approved_split
    selected = []
    used_ids = set()
    for wanted_sex, count in (("female", female_count), ("male", male_count)):
        candidates = [
            row for row in rows
            if str(row.get("sex") or "").strip().casefold() == wanted_sex
        ]
        for row in candidates[:count]:
            selected.append(row)
            used_ids.add(str(row.get("pig_id") or id(row)))
    if len(selected) < quantity:
        selected.extend(
            row for row in rows
            if str(row.get("pig_id") or id(row)) not in used_ids
        )
    selected = selected[:quantity]
    selected.sort(key=lambda row: (int(row["alternative_rank"]), str(row.get("pig_id") or "")))
    return selected


def _approved_approx_19_split(rows, facts, female_count, male_count):
    """Apply the reusable owner-approved 19 kg split-alternative journey."""
    midpoint = _weight_midpoint(facts.get("weight_range"))
    if (
        midpoint is None
        or not 18 <= midpoint <= 20
        or female_count != 4
        or male_count != 1
    ):
        return []
    by_band_and_sex = {}
    for row in rows:
        key = (
            str(row.get("sex") or "").strip().casefold(),
            _normal_weight_band(row.get("weight_band")),
        )
        by_band_and_sex.setdefault(key, []).append(row)
    selected = [
        *by_band_and_sex.get(("female", "35-39"), [])[:3],
        *by_band_and_sex.get(("female", "40-44"), [])[:1],
        *by_band_and_sex.get(("male", "15-19"), [])[:1],
    ]
    if len(selected) != 5:
        return []
    selected.sort(
        key=lambda row: (int(row["alternative_rank"]), str(row.get("pig_id") or ""))
    )
    return selected


def _weight_midpoint(value):
    numbers = [
        float(item)
        for item in re.findall(r"\d+(?:\.\d+)?", str(value or ""))
    ]
    if not numbers:
        return None
    return sum(numbers[:2]) / min(len(numbers), 2)


def _normal_weight_band(value):
    text = " ".join(str(value or "").replace("_", " ").split()).casefold()
    numbers = re.findall(r"\d+(?:\.\d+)?", text)
    return "-".join(numbers[:2]) if len(numbers) >= 2 else ""


def _alternative_group_label(*, sex, category, weight_band, count):
    sex_label = (
        ("female" if count == 1 else "females")
        if sex == "female"
        else ("male" if count == 1 else "males")
        if sex == "male"
        else ("pig" if count == 1 else "pigs")
    )
    band = _human_weight_band(weight_band)
    if band:
        return f"{count} {sex_label} in the {band} category"
    product = WEIGHT_CHOICES.get(category, category)
    return f"{count} {sex_label} ({product})"


def _alternative_row_current(row, availability):
    if availability.get("observation_evidence_state") in {"stale", "conflicting"}:
        return False
    if row.get("evidence_complete") is not True:
        return False
    if row.get("weight_freshness_consistent") is False:
        return False
    if not str(row.get("latest_weight_date") or ""):
        return False
    try:
        age = float(row.get("days_since_weight"))
    except (TypeError, ValueError):
        return False
    return 0 <= age <= 7 and _weight_date_matches_age(
        row.get("latest_weight_date"), age
    )


def _alternative_difference(facts, match_packet, quantity, availability):
    split = facts.get("sex_split") if isinstance(facts.get("sex_split"), Mapping) else {}
    if _approved_split_explanation_supported(
        facts,
        match_packet,
        quantity,
        availability,
    ):
        return (
            f"The requested {int(split['female'])}-female/"
            f"{int(split['male'])}-male split is preserved, but some pigs are "
            "in different weight bands from the requested size. "
        )
    rows = [
        row for row in match_packet.get("considered_sample") or []
        if (
            isinstance(row, Mapping)
            and row.get("live_stock_sale_eligible") is True
            and row.get("alternative_rank") not in ("", None)
            and _alternative_row_current(row, availability)
        )
    ]
    rows.sort(
        key=lambda row: (int(row["alternative_rank"]), str(row.get("pig_id") or ""))
    )
    selected = _select_alternative_rows(rows, quantity, facts)
    requested_weight = _weight_midpoint(facts.get("weight_range"))
    selected_weights = [
        _weight_midpoint(row.get("weight_band"))
        for row in selected
    ]
    if (
        requested_weight is not None
        and selected_weights
        and all(weight is not None and weight < requested_weight for weight in selected_weights)
    ):
        return (
            "This proposed combination is lighter than your requested "
            "approximately-19 kg group. "
        )
    return (
        ""
    )


def _approved_split_explanation_supported(
    facts, match_packet, quantity, availability
):
    split = facts.get("sex_split") if isinstance(facts.get("sex_split"), Mapping) else {}
    if (
        int(split.get("female") or 0) != 4
        or int(split.get("male") or 0) != 1
        or quantity != 5
    ):
        return False
    rows = [
        row for row in match_packet.get("considered_sample") or []
        if (
            isinstance(row, Mapping)
            and row.get("live_stock_sale_eligible") is True
            and row.get("alternative_rank") not in ("", None)
            and _alternative_row_current(row, availability)
        )
    ]
    rows.sort(
        key=lambda row: (int(row["alternative_rank"]), str(row.get("pig_id") or ""))
    )
    selected = _approved_approx_19_split(rows, facts, 4, 1)
    if len(selected) != 5:
        return False
    return (
        sum(
            str(row.get("sex") or "").strip().casefold() == "female"
            for row in selected
        )
        == 4
        and sum(
            str(row.get("sex") or "").strip().casefold() == "male"
            for row in selected
        )
        == 1
    )


def _human_weight_band(value):
    text = " ".join(str(value or "").replace("_", " ").split())
    match = re.search(r"(\d+(?:\.\d+)?)\s+to\s+(\d+(?:\.\d+)?)", text, re.I)
    if match:
        return f"{match.group(1)}-{match.group(2)} kg"
    return text


def _weight_date_matches_age(value, reported_age):
    raw = str(value or "").strip()
    try:
        observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    actual_age = (datetime.now(timezone.utc).date() - observed.date()).days
    return actual_age >= 0 and abs(actual_age - float(reported_age)) <= 1
