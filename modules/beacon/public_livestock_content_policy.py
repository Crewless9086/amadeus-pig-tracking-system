"""Fail-closed public-content policy for live-animal media and copy."""

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timezone


POLICY_VERSION = "beacon_public_livestock_awareness_only_v2"
ENQUIRY_POLICY_VERSION = POLICY_VERSION
POLICY_ID = "beacon_public_livestock_awareness_only"
EXTERNAL_POLICY_AUTHORITY = {
    "record_version": "meta_public_livestock_surface_authority_2026-08-22_v1",
    "reviewed_on": "2026-08-22",
    "valid_through": "2026-09-21",
    "surface": "facebook_organic_page_post",
    "jurisdiction": "ZA",
    "entity_id": "AMADEUS-FARM-ZA",
    "entity_eligibility": "awareness_only_no_commerce_exception_relied_upon",
    "decision": "amadeus_stricter_awareness_only_fail_closed",
    "sources": [
        {"source_id": "meta-marketplace-animals", "version": "reviewed-2026-08-22",
         "url": "https://www.facebook.com/help/130910837313345",
         "content_sha256": "68ab8be8f56ce970413074124094b6b5947bc3abf7e8aaffc865e79cb70d36d2"},
        {"source_id": "meta-terms", "version": "effective-2025-01-01-reviewed-2026-08-22",
         "url": "https://www.facebook.com/terms",
         "content_sha256": "ec6e6d4ba5328769d88702dfca4581e0cb568146d2fbb913253aee8e003cbd86"},
        {"source_id": "oversight-board-bun-63gbjx9k", "version": "decision-reviewed-2026-08-22",
         "url": "https://www.oversightboard.com/decision/bun-63gbjx9k/",
         "content_sha256": "38f23817e9cbd564bbc71f57d18c7d0ccf128e025610260295ec0f04c4fe86e4"},
    ],
}
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
    "live_stock_enquiry_capture",
}
LIVESTOCK_SIGNALS = (
    "animal", "animals", "livestock", "live stock", "pig", "pigs", "piglet",
    "piglets", "weaner", "weaners", "sow", "sows", "boar", "boars", "litter",
    "litters", "vark", "varke", "varkie", "varkies", "speenvark", "speenvarke",
    "zeug", "zeugen", "beer", "bere",
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
    r"\b(?:looking|searching)\s+for\s+(?:live\s+)?(?:livestock|pigs?|piglets?|weaners?)\b",
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


def assess_public_livestock_enquiry_capture(text, *, campaign_lane="", media=None):
    """Compatibility entry point; it may add restrictions but never bypass common policy."""
    result = assess_public_livestock_content(
        text, objective="qualified_livestock_enquiries",
        campaign_lane=campaign_lane or "live_stock_enquiry_capture", media=media)
    result["reasons"] = sorted(set(result["reasons"] + [
        "public_livestock_enquiry_capture_exception_retired"]))
    result.update({"allowed": False, "withhold_draft": True, "status": RISK_STATUS})
    return result


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
        "policy_id": POLICY_ID,
        "policy_authority": policy_authority_binding(),
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
    result = {
        "allowed": bool(allowed),
        "status": "public_livestock_awareness_policy_passed"
        if allowed else RISK_STATUS,
        "withhold_draft": not allowed,
        "livestock_context": bool(livestock_context),
        "objective": objective,
        "reasons": sorted(set(reasons)),
        "policy_version": POLICY_VERSION,
        "policy_id": POLICY_ID,
        "performance_optimization_for_commerce_allowed": False,
        "private_sam_livestock_sales_unchanged": True,
    }
    result["policy_authority"] = policy_authority_binding()
    result["evaluation_digest"] = _digest({
        "allowed": result["allowed"], "reasons": result["reasons"],
        "livestock_context": result["livestock_context"],
        "objective": result["objective"], "policy_version": POLICY_VERSION,
        "policy_authority": result["policy_authority"],
    })
    return result


def policy_authority_binding(*, target_page_id="", now=None):
    authority = dict(EXTERNAL_POLICY_AUTHORITY)
    authority["sources"] = [dict(item) for item in EXTERNAL_POLICY_AUTHORITY["sources"]]
    authority["target_page_id"] = str(target_page_id or "").strip()
    authority["source_digest"] = _digest(EXTERNAL_POLICY_AUTHORITY)
    return authority


def public_livestock_policy_binding(assessment, *, target_page_id="", now=None):
    authority = policy_authority_binding(target_page_id=target_page_id, now=now)
    return {"policy_id": assessment.get("policy_id"),
        "policy_version": assessment.get("policy_version"),
        "evaluation_digest": assessment.get("evaluation_digest"),
        "policy_authority": authority}


def public_livestock_policy_binding_matches(bound, assessment, *, target_page_id="", now=None):
    if not isinstance(bound, dict) or not str(target_page_id or "").strip():
        return False
    when = now or datetime.now(timezone.utc)
    today = when.date() if isinstance(when, datetime) else when
    if not isinstance(today, date) or today > date.fromisoformat(
            EXTERNAL_POLICY_AUTHORITY["valid_through"]):
        return False
    return bound == public_livestock_policy_binding(assessment,
        target_page_id=target_page_id, now=when)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


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
