"""Read-only, source-backed contextual livestock sales recommendations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Callable, Mapping

from modules.sales.sam_pricing import list_live_stock_price_entries


CONTRACT_VERSION = "sam_live_stock_contextual_sales_v1"
MAX_HISTORY_MESSAGES = 20
MAX_EVIDENCE_AGE = timedelta(hours=24)

CATEGORY_LABELS = {
    "Young Piglets": "Young piglets",
    "Weaner Piglets": "Weaners",
    "Grower Pigs": "Growers",
    "Finisher Pigs": "Finishers",
    "Ready for Slaughter": "Ready-for-slaughter live pigs",
}
CATEGORY_ORDER = tuple(CATEGORY_LABELS)

COMMERCIAL_PATTERNS = (
    r"\bdo you sell\b",
    r"\b(?:can|could|would)\s+you\s+sell\s+(?:me|us)\b",
    r"\bdo you have\b",
    r"\bany\b.*\bleft\b",
    r"\b(?:want|wants|wanted|need|needs|looking)\s+to\s+buy\b",
    r"\b(?:want|need|looking for|buy|koop|soek)\b",
    r"\bavailable\b",
    r"\bavailability\b",
    r"\bprice\b",
    r"\bpric+e\b",
    r"\bprise\b",
    r"\bprys\b",
    r"\bhow much\b",
    r"\bquote\b",
    r"\bfor sale\b",
)

AUTHORITY_FLAGS = {
    "customer_send_allowed": False,
    "sends_customer_message": False,
    "creates_quote": False,
    "creates_order": False,
    "reserves_stock": False,
    "allocates_stock": False,
    "changes_stock": False,
    "writes_farm_data": False,
    "mutates_business_state": False,
}


def build_contextual_sales_recommendation(
    inbound: Mapping[str, Any],
    facts: Mapping[str, Any],
    history_messages: list[Mapping[str, Any]],
    availability: Mapping[str, Any],
    *,
    price_loader: Callable[..., tuple[dict[str, Any], int]] | None = None,
    database_url: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Interpret bounded chronology and prepare one no-send commercial draft."""
    now = _aware(now or datetime.now(timezone.utc))
    interpretation = interpret_contextual_livestock_request(
        inbound, facts, history_messages
    )
    if interpretation["intent"] == "sell_livestock_to_farm":
        return {
            "version": CONTRACT_VERSION,
            "applicable": True,
            "status": "seller_enquiry_owner_handoff",
            "interpretation": interpretation,
            "general_information_fallback_blocked": True,
            "recommendation": (
                "Thanks for the offer. I'll pass the livestock details to the "
                "owner for review; no purchase is confirmed."
            ),
            "next_action": "owner_review_seller_enquiry",
            "owner_review_required": True,
            **AUTHORITY_FLAGS,
        }
    if interpretation["commercial_intent"] is not True:
        return {
            "version": CONTRACT_VERSION,
            "applicable": False,
            "status": "not_commercial_livestock",
            "interpretation": interpretation,
            "general_information_fallback_blocked": False,
            "recommendation": "",
            **AUTHORITY_FLAGS,
        }
    if any(
        facts.get(key)
        for key in (
            "order_commitment",
            "reservation_requested",
            "payment_requested",
        )
    ):
        return {
            "version": CONTRACT_VERSION,
            "applicable": False,
            "status": "protected_commercial_action_owner_gate",
            "interpretation": interpretation,
            # Protected-action composition remains on its existing governed
            # owner-review rail and cannot enter the general-information LLM.
            "general_information_fallback_blocked": True,
            "recommendation": "",
            "owner_review_required": True,
            **AUTHORITY_FLAGS,
        }

    aggregate = build_customer_livestock_aggregate(
        availability,
        interpretation,
        price_loader=price_loader,
        database_url=database_url,
        now=now,
    )
    if aggregate["evidence_complete"] is not True:
        return {
            "version": CONTRACT_VERSION,
            "applicable": True,
            "status": "commercial_evidence_unavailable",
            "interpretation": interpretation,
            "herdmaster_aggregate": aggregate,
            "general_information_fallback_blocked": True,
            "recommendation": (
                "I'm checking the current livestock availability and pricing "
                "before giving you an answer."
            ),
            "next_action": "verify_current_stock_and_pricing",
            "owner_review_required": True,
            **AUTHORITY_FLAGS,
        }

    recommendation = _recommendation(interpretation, aggregate)
    return {
        "version": CONTRACT_VERSION,
        "applicable": True,
        "status": "commercial_recommendation_ready",
        "interpretation": interpretation,
        "herdmaster_aggregate": aggregate,
        "general_information_fallback_blocked": True,
        "recommendation": recommendation,
        "next_action": interpretation["next_action"],
        "owner_review_required": True,
        **AUTHORITY_FLAGS,
    }


def interpret_contextual_livestock_request(
    inbound: Mapping[str, Any],
    facts: Mapping[str, Any],
    history_messages: list[Mapping[str, Any]],
) -> dict[str, Any]:
    inbound = dict(inbound or {})
    facts = dict(facts or {})
    history = [
        dict(row)
        for row in (history_messages or [])[-MAX_HISTORY_MESSAGES:]
        if isinstance(row, Mapping)
    ]
    latest = normalize_livestock_language(
        inbound.get("content") or facts.get("latest_customer_message")
    )
    customer_history = [
        normalize_livestock_language(row.get("content"))
        for row in history
        if str(row.get("speaker") or "").lower() == "customer"
    ]
    context = " ".join([*customer_history, latest]).strip()
    seller_intent = bool(
        re.search(
            r"\b(?:i|we|ek|ons)\s+(?:want|would like|need)\s+to\s+sell\b|"
            r"\b(?:i|we|ek|ons)\s+sell\b|"
            r"\b(?:can|could)\s+(?:i|we|ek|ons)\s+sell\b|"
            r"\b(?:i|we|ek|ons)\s+(?:have|het)\b.*\bfor sale\b|"
            r"\b(?:selling|sell my|sell our)\b|"
            r"\b(?:do|would)\s+you\s+buy\b|"
            r"\bcan\s+you\s+buy\s+(?:my|our)\b",
            latest,
        )
        and _livestock_signal(context)
    )
    current_product = _product(latest)
    product = current_product or _product(context)
    quantity = _quantity(latest)
    sex = _sex(latest)
    timing = _timing(latest)
    location = _location(latest)
    transport = _transport(latest)
    selected_category = _selected_category(latest)
    current_commercial = _commercial_intent(latest)
    prior_commercial = any(
        _commercial_intent(message) and _livestock_signal(message)
        for message in customer_history
    )
    prior_livestock = any(_livestock_signal(message) for message in customer_history)
    continuation_facts = bool(
        current_product
        or quantity not in ("", None)
        or sex
        or timing
        or location
        or transport
        or selected_category
    )
    contextual_anaphora = bool(
        prior_livestock
        and re.search(r"\b(?:it|they|them|these|those)\b", latest)
    )
    subjectless_commercial_followup = bool(
        prior_commercial
        and re.fullmatch(
            r"(?:(?:what(?:'s| is) the )?(?:price|prices|availability)|"
            r"how much|(?:is it |are they )?available)\s*[?.!]?",
            latest,
        )
    )
    commercial = bool(
        current_commercial
        and (
            _livestock_signal(latest)
            or contextual_anaphora
            or subjectless_commercial_followup
        )
        or (prior_commercial and continuation_facts)
    )

    # Prior chronology may establish product/lane, but never silently chooses
    # a sale category, quantity, sex, timing, or transport for a newer request.
    if not product and _livestock_signal(context):
        product = "live_pigs"
    if facts.get("quantity") not in ("", None) and quantity in ("", None):
        quantity = facts.get("quantity")
    if facts.get("sex") and not sex:
        sex = _normal_sex(facts.get("sex"))
    if facts.get("timing") and not timing:
        timing = str(facts.get("timing"))
    if facts.get("location") and not location:
        location = str(facts.get("location"))
    if facts.get("transport_expectation") and not transport:
        transport = str(facts.get("transport_expectation"))

    if re.search(r"\bbig\s+(?:one|ones|pig|pigs)\b", latest):
        category_options = ["Grower Pigs", "Finisher Pigs"]
    elif product == "piglets" and not selected_category:
        category_options = ["Young Piglets", "Weaner Piglets"]
    elif selected_category:
        category_options = [selected_category]
    else:
        category_options = list(CATEGORY_ORDER)

    missing = []
    if quantity in ("", None):
        missing.append("quantity")
    if not sex:
        missing.append("sex")
    if not selected_category:
        missing.append("category")
    if product == "piglets":
        next_action = "present_piglet_options_then_ask_quantity_and_sex"
    elif quantity and sex and not selected_category:
        next_action = "present_matching_category_counts_and_prices_then_offer_quote"
    else:
        next_action = "present_current_options_then_ask_missing_quote_facts"
    return {
        "intent": (
            "sell_livestock_to_farm"
            if seller_intent
            else "buy_live_pigs"
            if commercial
            else "not_proven"
        ),
        "commercial_intent": bool(commercial and _livestock_signal(context)),
        "message_type": (
            "availability_enquiry"
            if re.search(r"\b(?:sell|available|availability)\b", latest)
            else "price_enquiry"
            if re.search(r"\b(?:price|how much|quote)\b", latest)
            else "purchase_enquiry"
        ),
        "product": product,
        "customer_name": str(inbound.get("customer_name") or "").strip(),
        "quantity": quantity,
        "sex": sex,
        "category": selected_category,
        "category_options": category_options,
        "timing": timing,
        "location": location,
        "transport": transport,
        "missing_quote_facts": missing,
        "next_action": next_action,
        "history_messages_considered": len(history),
        "contains_customer_content": False,
    }


def build_customer_livestock_aggregate(
    availability: Mapping[str, Any],
    interpretation: Mapping[str, Any],
    *,
    price_loader: Callable[..., tuple[dict[str, Any], int]] | None = None,
    database_url: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = _aware(now or datetime.now(timezone.utc))
    availability = dict(availability or {})
    interpretation = dict(interpretation or {})
    observed_at = _parse_timestamp(availability.get("observation_timestamp"))
    availability_fresh = bool(
        availability.get("success") is True
        and observed_at
        and timedelta(0) <= now - observed_at <= MAX_EVIDENCE_AGE
    )
    categories = interpretation.get("category_options") or list(CATEGORY_ORDER)
    sex = _normal_sex(interpretation.get("sex"))
    category_evidence = availability.get("customer_category_counts")
    count_evidence_complete = bool(
        isinstance(category_evidence, Mapping)
        and availability.get("customer_category_counts_complete", True) is True
    )
    counts = {}
    exclusions = {}
    for category in categories:
        category_counts = (
            category_evidence.get(category)
            if isinstance(category_evidence, Mapping)
            else None
        )
        if not isinstance(category_counts, Mapping):
            count_evidence_complete = False
            counts[category] = 0
            exclusions[category] = 0
            continue
        all_count = _nonnegative_int(category_counts.get("all"))
        if sex == "mixture":
            female_count = _nonnegative_int(category_counts.get("female"))
            male_count = _nonnegative_int(category_counts.get("male"))
            selected_count = (
                female_count + male_count
                if female_count is not None and male_count is not None
                else None
            )
        else:
            selected_count = (
                _nonnegative_int(category_counts.get(sex)) if sex else all_count
            )
        if all_count is None or selected_count is None or selected_count > all_count:
            count_evidence_complete = False
            counts[category] = 0
            exclusions[category] = 0
            continue
        counts[category] = selected_count
        exclusions[category] = all_count - selected_count

    loader = price_loader or list_live_stock_price_entries
    listed, price_status = loader(limit=500, database_url=database_url)
    entries = (
        listed.get("price_entries")
        if price_status == 200 and isinstance(listed, Mapping)
        else []
    )
    pricing_authoritative = bool(
        price_status == 200
        and listed.get("configured") is True
        and listed.get("source") == "supabase"
    )
    ranges = {}
    latest_price_evidence = None
    for category in categories:
        effective_by_dimension = {}
        for row in entries or []:
            if not isinstance(row, Mapping):
                continue
            if row.get("active") is not True or str(row.get("sale_category")) != category:
                continue
            start = _parse_timestamp(row.get("effective_from"))
            end = _parse_timestamp(row.get("effective_to"), allow_blank=True)
            if not start or start > now or (end and end <= now):
                continue
            entry_sex = _normal_sex(row.get("sex"))
            if sex in ("female", "male") and entry_sex not in ("", sex):
                continue
            try:
                price = float(row.get("unit_price"))
            except (TypeError, ValueError):
                continue
            dimension = str(row.get("weight_band") or "").strip()
            key = (dimension, entry_sex)
            current = effective_by_dimension.get(key)
            if current is None or start > current["effective_from"]:
                effective_by_dimension[key] = {
                    "unit_price": price,
                    "effective_from": start,
                    "sex": entry_sex,
                }
        selected = []
        dimensions = {key[0] for key in effective_by_dimension}
        for dimension in dimensions:
            exact = (
                effective_by_dimension.get((dimension, sex))
                if sex in ("female", "male")
                else None
            )
            unscoped = effective_by_dimension.get((dimension, ""))
            chosen = exact or unscoped
            if sex in ("", "mixture"):
                if unscoped:
                    selected.append(unscoped)
                    continue
                for candidate_sex in ("female", "male"):
                    candidate = effective_by_dimension.get(
                        (dimension, candidate_sex)
                    )
                    if candidate:
                        selected.append(candidate)
                continue
            if chosen is not None:
                selected.append(chosen)
        active = [item["unit_price"] for item in selected]
        for item in selected:
            latest_price_evidence = max(
                latest_price_evidence or item["effective_from"],
                item["effective_from"],
            )
        if active:
            ranges[category] = {
                "minimum": min(active),
                "maximum": max(active),
                "currency": "ZAR",
                "active_entry_count": len(active),
            }
    required_categories = [
        category for category in categories if counts.get(category, 0) > 0
    ]
    pricing_fresh = bool(
        pricing_authoritative
        and (
            not required_categories
            or latest_price_evidence is not None
            and latest_price_evidence <= now
        )
        and all(category in ranges for category in required_categories)
    )
    options = [
        {
            "category": category,
            "label": CATEGORY_LABELS[category],
            "eligible_count": counts.get(category, 0),
            "price_range": ranges.get(category),
            "excluded_count": exclusions.get(category, 0),
        }
        for category in categories
        if counts.get(category, 0) > 0 and ranges.get(category)
    ]
    blockers = []
    if not availability_fresh:
        blockers.append("herdmaster_availability_stale_or_unavailable")
    if not count_evidence_complete:
        blockers.append("herdmaster_complete_category_counts_unavailable")
    if not pricing_fresh:
        blockers.append("active_pricing_stale_or_unavailable")
    return {
        "contract_version": "herdmaster_customer_category_aggregate_v1",
        "evidence_complete": not blockers,
        "availability_observed_at_utc": (
            observed_at.isoformat() if observed_at else None
        ),
        "availability_fresh": availability_fresh,
        "pricing_fresh": pricing_fresh,
        "options": options,
        "blockers": blockers,
        "private_animal_ids_exposed": False,
        "read_only": True,
        **AUTHORITY_FLAGS,
    }


def normalize_livestock_language(value: Any) -> str:
    text = " ".join(str(value or "").casefold().split())
    replacements = (
        (r"\bsoggies\b", "female pigs"),
        (r"\bsogies\b", "female pigs"),
        (r"\bsowgies\b", "female pigs"),
        (r"\bto bay\b", "to buy"),
        (r"\bte koop\b", "for sale"),
        (r"\bvarkies\b", "piglets"),
        (r"\bvarkie\b", "piglet"),
        (r"\bspeenvarkies\b", "weaner piglets"),
        (r"\bwyfies\b", "females"),
        (r"\bmannetjies\b", "males"),
        (r"\bpric+e\b", "price"),
        (r"\bprise\b", "price"),
        (r"\bprys\b", "price"),
        (r"\bbeskikbaar\b", "available"),
        (r"\bkoop\b", "buy"),
        (r"\bsoek\b", "looking for"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return text


def _recommendation(interpretation: Mapping[str, Any], aggregate: Mapping[str, Any]) -> str:
    name = str(interpretation.get("customer_name") or "").strip()
    product = interpretation.get("product")
    quantity = interpretation.get("quantity")
    sex = interpretation.get("sex")
    if product == "piglets":
        opening = "Yes, we do sell piglets."
        missing = set(interpretation.get("missing_quote_facts") or [])
        if {"quantity", "sex"}.issubset(missing):
            ask = (
                "How many are you looking for, and would you prefer males, "
                "females, or a mixture? I can then confirm current availability "
                "and prepare a quote for you."
            )
        elif "quantity" in missing:
            ask = (
                "How many are you looking for? I can then confirm current "
                "availability and prepare a quote for you."
            )
        elif "sex" in missing:
            ask = (
                "Would you prefer males, females, or a mixture? I can then "
                "confirm current availability and prepare a quote for you."
            )
        elif "category" in missing:
            ask = (
                "Would you prefer Young Piglets or Weaners for the quote?"
            )
        else:
            ask = "Would you like me to prepare the quote for these piglets?"
    else:
        descriptor = "female " if sex == "female" else "male " if sex == "male" else ""
        amount = f"{quantity} " if quantity else ""
        opening = f"I understand you're looking to buy {amount}{descriptor}live pigs.".replace("  ", " ")
        ask = (
            f"Would you like me to prepare a quote for {quantity} from one of "
            "these categories?" if quantity else
            "Which category, quantity and sex would you prefer for a quote?"
        )
    lines = []
    for option in aggregate.get("options") or []:
        price = option["price_range"]
        price_label = _money(price["minimum"])
        if price["maximum"] != price["minimum"]:
            price_label = f"{price_label} to {_money(price['maximum'])}"
        lines.append(
            f"- {option['label']}: {option['eligible_count']} currently "
            f"eligible; {price_label} each"
        )
    greeting = f"Hi {name}," if name else "Hi,"
    if not aggregate.get("options"):
        return (
            f"{greeting} I don't currently have an eligible option in the "
            "relevant livestock categories to offer. I can check again when "
            "new stock becomes eligible."
        )
    options = aggregate.get("options") or []
    if (
        isinstance(quantity, int)
        and quantity > 0
        and max(option["eligible_count"] for option in options) < quantity
    ):
        sex_label = (
            "female pigs" if sex == "female"
            else "male pigs" if sex == "male"
            else "pigs"
        )
        clauses = []
        for option in options:
            count = option["eligible_count"]
            category = option["category"]
            label = category
            if count == 1:
                label = {
                    "Young Piglets": "Young Piglet",
                    "Weaner Piglets": "Weaner Piglet",
                    "Grower Pigs": "Grower Pig",
                    "Finisher Pigs": "Finisher Pig",
                    "Ready for Slaughter": "ready-for-slaughter live pig",
                }.get(category, category.rstrip("s"))
            price = option["price_range"]
            price_label = _money(price["minimum"])
            if price["maximum"] != price["minimum"]:
                price_label = f"{price_label} to {_money(price['maximum'])}"
            clauses.append(f"{count} {label} at {price_label} each")
        available = _join_commercial_clauses(clauses)
        requested_category = interpretation.get("category")
        total_available = sum(option["eligible_count"] for option in options)
        if requested_category:
            shortage = (
                f"the requested {requested_category} category does not "
                f"currently have all {quantity}"
            )
            choice = (
                "Please let me know whether you would like the available "
                "quantity from this category or want to consider other "
                "supported categories."
            )
        elif total_available >= quantity:
            shortage = f"no single category currently has all {quantity}"
            choice = (
                "Please let me know whether you prefer one of these available "
                "category quantities or would like us to consider a "
                "split across categories."
            )
        else:
            shortage = f"no single category currently has all {quantity}"
            choice = (
                "Please let me know whether you prefer one of these available "
                "category quantities or would like us to check again when "
                "more eligible animals become available."
            )
        return (
            f"{greeting} yes, we currently have {sex_label} available, but "
            f"{shortage}. We have {available}. {choice} "
            "Choosing an option does not reserve the animals; "
            "availability would still need to be confirmed when we prepare "
            "the quote."
        )
    return "\n".join([
        f"{greeting} {opening}",
        "",
        "Our current categories are:",
        "",
        *lines,
        "",
        ask,
    ])


def _join_commercial_clauses(clauses: list[str]) -> str:
    if len(clauses) == 1:
        return clauses[0]
    if len(clauses) == 2:
        return f"{clauses[0]} and {clauses[1]}"
    return f"{', '.join(clauses[:-1])}, and {clauses[-1]}"


def _commercial_intent(text: str) -> bool:
    return any(re.search(pattern, text) for pattern in COMMERCIAL_PATTERNS)


def _livestock_signal(text: str) -> bool:
    return bool(re.search(
        r"\b(?:pig|pigs|piglet|piglets|weaner|weaners|grower|growers|"
        r"finisher|finishers|gilt|gilts|sow|sows|boar|boars|female|females|"
        r"male|males|female pigs|big one|big ones)\b",
        text,
    ))


def _product(text: str) -> str:
    if re.search(r"\b(?:piglet|piglets|weaner|weaners|weaner piglets)\b", text):
        return "piglets"
    if _livestock_signal(text) or re.search(r"\bbig(?:ger)? ones?\b", text):
        return "live_pigs"
    return ""


def _selected_category(text: str) -> str:
    for pattern, category in (
        (r"\byoung piglets?\b", "Young Piglets"),
        (r"\bweaners?\b|\bweaner piglets?\b", "Weaner Piglets"),
        (r"\bgrowers?\b", "Grower Pigs"),
        (r"\bfinishers?\b", "Finisher Pigs"),
        (r"\bready(?: |-)?for(?: |-)?slaughter\b|\bslaughter pigs?\b", "Ready for Slaughter"),
    ):
        if re.search(pattern, text):
            return category
    return ""


def _quantity(text: str) -> int | str:
    patterns = (
        r"\b(?:buy|purchase|need|want|looking for)\s+(\d{1,3})"
        r"(?!\s*(?:kg|kgs|kilograms?)\b)\b",
        r"\bsell\s+(?:me|us)\s+(\d{1,3})"
        r"(?!\s*(?:kg|kgs|kilograms?)\b)\b",
        r"\b(\d{1,3})\s+(?:x\s+)?(?:live\s+)?"
        r"(?:pig|pigs|piglet|piglets|weaner|weaners|grower|growers|"
        r"finisher|finishers|female|females|male|males|gilt|gilts|"
        r"sow|sows|boar|boars)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return ""


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _sex(text: str) -> str:
    female = bool(re.search(r"\b(?:female|females|female pigs|gilts?|sows?)\b", text))
    male = bool(re.search(r"\b(?:male|males|boars?)\b", text))
    if female and male:
        return "mixture"
    return "female" if female else "male" if male else ""


def _normal_sex(value: Any) -> str:
    text = normalize_livestock_language(value)
    if text in {"mixture", "mixed", "split"}:
        return "mixture"
    return _sex(text)


def _timing(text: str) -> str:
    match = re.search(
        r"\b(?:today|tomorrow|next week|this week|in \d+ (?:days?|weeks?)|"
        r"over \d+ (?:dae|weke))\b",
        text,
    )
    return match.group(0) if match else ""


def _location(text: str) -> str:
    for place in (
        "riversdale", "albertinia", "stilbaai", "still bay", "george",
        "mossel bay", "cape town",
    ):
        if place in text:
            return place.title()
    return ""


def _transport(text: str) -> str:
    if re.search(r"\b(?:deliver|delivery|aflewer)\b", text):
        return "delivery_requested"
    if re.search(r"\b(?:collect|collection|pickup|pick up|afhaal)\b", text):
        return "collection_requested"
    return ""


def _sale_category(row: Mapping[str, Any]) -> str:
    text = " ".join(str(row.get(key) or "") for key in (
        "sale_category", "suggested_price_category", "weight_band",
    )).casefold()
    if "young" in text or ("piglet" in text and "weaner" not in text):
        return "Young Piglets"
    if "weaner" in text:
        return "Weaner Piglets"
    if "grower" in text:
        return "Grower Pigs"
    if "finisher" in text:
        return "Finisher Pigs"
    if "slaughter" in text:
        return "Ready for Slaughter"
    return ""


def _eligible_public_row(row: Mapping[str, Any]) -> bool:
    return bool(
        row.get("live_stock_sale_eligible") is True
        and row.get("evidence_complete") is True
        and str(row.get("purpose") or "").casefold() == "sale"
        and str(row.get("allocation_query_status") or "").casefold()
        in {"known", "success"}
        and str(row.get("allocation_evidence_state") or "").replace("_", " ").casefold()
        == "known unallocated"
        and str(row.get("medical_status") or "").casefold() == "clear"
        and str(row.get("reserved_status") or "").replace("_", " ").casefold()
        == "not reserved"
    )


def _parse_timestamp(value: Any, *, allow_blank: bool = False) -> datetime | None:
    if value in ("", None) and allow_blank:
        return None
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
    return parsed.astimezone(timezone.utc)


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("timezone_aware_now_required")
    return value.astimezone(timezone.utc)


def _money(value: float) -> str:
    return f"R{float(value):,.0f}"
