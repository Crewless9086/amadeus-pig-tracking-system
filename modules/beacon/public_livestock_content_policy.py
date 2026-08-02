"""Fail-closed public-content policy for live-animal media and copy."""

import re
import unicodedata


POLICY_VERSION = "beacon_public_livestock_awareness_only_v1"
RISK_STATUS = "owner_review_required_meta_livestock_commerce_risk"
SAFE_OBJECTIVES = (
    "farm_awareness",
    "education",
    "welfare",
    "husbandry",
    "responsible_farming",
    "community_engagement",
    "farm_story",
)
PUBLIC_LIVESTOCK_LANES = {
    "live_stock",
    "livestock",
    "live_stock_awareness",
    "live_stock_sales",
    "live_pig_sales",
}
LIVESTOCK_SIGNALS = (
    "animal", "livestock", "live stock", "pig", "piglet", "weaner", "sow",
    "boar", "litter", "vark", "varkie", "speenvark", "zeug", "beer",
)
SAFE_EDUCATION_SIGNALS = (
    "follow the farm journey",
    "follow along",
    "ask an educational question",
    "questions about animal care",
    "responsible animal care",
    "behind the scenes",
    "farm journey",
    "learn about",
    "animal welfare",
    "husbandry",
    "volg die plaas",
    "vrae oor diereversorging",
    "verantwoordelike diereversorging",
    "agter die skerms",
)
DIRECT_COMMERCE_PATTERNS = (
    r"\b(?:for sale|sell(?:ing)?|sale|buy|purchase|purchasing)\b",
    r"\b(?:order|book(?:ing)?|reservation|reserve|collection|collect)\b",
    r"\b(?:price|quote|(?<!live )stock|availability|available)\b",
    r"\b(?:te koop|verkoop|koop|aankoop)\b",
    r"\b(?:bestel|bespreek|bespreking|reserveer|afhaal)\b",
    r"\b(?:prys|kwotasie|voorraad|beskikbaar(?:heid)?)\b",
)
IMPLIED_COMMERCE_PATTERNS = (
    r"\bplanning\s+(?:livestock|pigs?|piglets?|your herd)\b",
    r"\b(?:looking|searching)\s+for\s+(?:livestock|pigs?|piglets?)\b",
    r"\bready\s+for\s+(?:a\s+)?new\s+home\b",
    r"\b(?:secure|choose|claim)\s+(?:one|yours|your animals?)\b",
    r"\b(?:make|take)\s+(?:one|them|this one)\s+(?:yours|home)\b",
    r"\b(?:join|contact us about)\s+(?:the\s+)?(?:waiting|interest)\s+list\b",
    r"\b(?:enquire|inquire)\s+(?:now|for details|about)\b",
    r"\b(?:we|the farm)\s+can\s+(?:help|match|supply|provide)\b",
    r"\bbeplan\s+(?:vee|lewende hawe|varke?|varkies?)\b",
    r"\bop\s+soek\s+na\s+(?:vee|lewende hawe|varke?|varkies?)\b",
    r"\breg\s+vir\s+(?:'n\s+)?nuwe\s+huis\b",
    r"\bmaak\s+(?:een|hierdie een)\s+joune\b",
    r"\bsluit\s+aan\s+by\s+(?:die\s+)?(?:wag|belangstelling)\s*lys\b",
)
ACQUISITION_DETAIL_PATTERN = re.compile(
    r"\b(?:type|kind|quantity|number|how many|sex|male|female|age|weight|"
    r"required timing|when (?:you )?need|soort|tipe|hoeveel(?:heid)?|aantal|"
    r"geslag|mannetjie|wyfie|ouderdom|gewig|wanneer)\b",
    re.I,
)
SOLICITATION_PATTERN = re.compile(
    r"\b(?:message|dm|inbox|contact|tell us|let us know|send us|reply|"
    r"stuur|kontak|laat weet|antwoord)\b",
    re.I,
)


def assess_public_livestock_content(
    text,
    *,
    objective="",
    campaign_lane="",
    media=None,
):
    """Classify combined copy/objective/media meaning; uncertainty withholds."""
    normalized = _normalize(text)
    objective_text = _normalize(objective).replace(" ", "_")
    lane = _normalize(campaign_lane).replace(" ", "_")
    media_text = _media_text(media)
    implied_commerce = any(
        re.search(pattern, normalized, re.I)
        for pattern in IMPLIED_COMMERCE_PATTERNS
    )
    livestock_context = (
        lane in PUBLIC_LIVESTOCK_LANES
        or _contains_any(normalized, LIVESTOCK_SIGNALS)
        or _contains_any(media_text, LIVESTOCK_SIGNALS)
        or implied_commerce
    )
    if not livestock_context:
        return _result(True, [], False, objective_text)

    reasons = []
    if lane in {"live_stock_sales", "live_pig_sales"}:
        reasons.append("public_live_stock_sales_lane_prohibited")
    if objective_text and objective_text not in SAFE_OBJECTIVES:
        reasons.append("public_livestock_objective_not_allowlisted")
    for pattern in DIRECT_COMMERCE_PATTERNS:
        if re.search(pattern, normalized, re.I):
            reasons.append("direct_livestock_commerce_meaning")
            break
    if implied_commerce:
        reasons.append("implied_livestock_acquisition_meaning")
    if ACQUISITION_DETAIL_PATTERN.search(normalized):
        reasons.append("livestock_acquisition_detail_solicitation")

    safe_education_context = _contains_any(
        normalized, SAFE_EDUCATION_SIGNALS
    )
    if SOLICITATION_PATTERN.search(normalized) and not safe_education_context:
        reasons.append("ambiguous_or_commercial_livestock_contact_cta")

    media_commerce = any(
        re.search(pattern, media_text, re.I)
        for pattern in (*DIRECT_COMMERCE_PATTERNS, *IMPLIED_COMMERCE_PATTERNS)
    )
    if media_commerce:
        reasons.append("combined_media_copy_commercial_meaning")

    if not normalized:
        reasons.append("public_livestock_copy_missing")
    allowed = not reasons
    return _result(allowed, reasons, True, objective_text)


def enforce_public_livestock_drafts(
    drafts,
    *,
    objective="",
    campaign_lane="live_stock_awareness",
    media=None,
):
    accepted, blocked = [], []
    for draft in drafts or []:
        item = dict(draft) if isinstance(draft, dict) else {"text": str(draft)}
        text = item.get("draft_copy") or item.get("text") or ""
        assessment = assess_public_livestock_content(
            text,
            objective=objective,
            campaign_lane=campaign_lane,
            media=media,
        )
        item["public_livestock_policy"] = assessment
        if assessment["allowed"]:
            accepted.append(item)
        else:
            blocked.append(item)
    return accepted, blocked


def public_livestock_policy_contract():
    return {
        "policy_version": POLICY_VERSION,
        "rule": (
            "Public live-animal content is awareness, education, husbandry, "
            "welfare, responsible-farming, community, or farm-story content "
            "only; it never solicits or implies a livestock transaction."
        ),
        "safe_objectives": list(SAFE_OBJECTIVES),
        "risk_status": RISK_STATUS,
        "private_sam_livestock_sales_unchanged": True,
        "performance_may_report_not_reward_commerce": True,
    }


def _result(allowed, reasons, livestock_context, objective):
    return {
        "allowed": bool(allowed),
        "status": "public_livestock_awareness_policy_passed"
        if allowed else RISK_STATUS,
        "withhold_draft": not allowed,
        "livestock_context": bool(livestock_context),
        "objective": objective,
        "reasons": sorted(set(reasons)),
        "policy_version": POLICY_VERSION,
        "performance_optimization_for_commerce_allowed": False,
        "private_sam_livestock_sales_unchanged": True,
    }


def _media_text(media):
    items = media if isinstance(media, list) else [media] if media else []
    values = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in (
            "title", "description", "original_filename", "campaign_lane",
        ):
            values.append(str(item.get(key) or ""))
        for key in ("subject_tags", "sale_stream_relevance", "campaign_lanes"):
            value = item.get(key)
            values.extend(value if isinstance(value, list) else [str(value or "")])
    return _normalize(" ".join(values).replace("_", " "))


def _contains_any(text, signals):
    return any(re.search(rf"(?<!\w){re.escape(signal)}(?!\w)", text, re.I)
               for signal in signals)


def _normalize(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(
        "".join(char for char in text if not unicodedata.combining(char))
        .replace("\x00", " ")
        .lower()
        .split()
    )
