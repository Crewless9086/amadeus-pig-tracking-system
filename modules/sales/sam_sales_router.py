import re


LANE_MEAT = "meat_sales"
LANE_LIVE_STOCK = "live_stock_sales"
LANE_SLAUGHTER = "slaughter_abattoir_sales"
LANE_FARM_GENERAL = "farm_general_question"
LANE_OWNER_HANDOFF = "owner_handoff"
LANE_UNCLEAR = "unclear"


def classify_sam_sales_lane(message, prior_context=None):
    """Classify SAM customer intent without writing data or sending replies."""
    text = _normalise(message)
    prior_context = prior_context if isinstance(prior_context, dict) else {}
    context_lane = str(prior_context.get("lane") or prior_context.get("sales_lane") or "").strip()

    if not text:
        return _result(LANE_UNCLEAR, 0.0, ["empty_message"], "Ask what the customer needs.")

    handoff_hits = _hits(text, OWNER_HANDOFF_TERMS)
    if handoff_hits:
        return _result(
            LANE_OWNER_HANDOFF,
            0.96,
            [f"owner_handoff:{hit}" for hit in handoff_hits],
            "Escalate to owner/SAM supervisor before sales handling.",
        )

    scores = {
        LANE_MEAT: _score_terms(text, MEAT_TERMS, MEAT_NEGATION_TERMS),
        LANE_LIVE_STOCK: _score_terms(text, LIVE_STOCK_TERMS, LIVE_STOCK_NEGATION_TERMS),
        LANE_SLAUGHTER: _score_terms(text, SLAUGHTER_TERMS, SLAUGHTER_NEGATION_TERMS),
        LANE_FARM_GENERAL: _score_terms(text, FARM_GENERAL_TERMS, ()),
    }

    reasons = []
    for lane, packet in scores.items():
        reasons.extend(f"{lane}:{term}" for term in packet["hits"])
        reasons.extend(f"negated_{lane}:{term}" for term in packet["negated"])

    positive = {lane: packet["score"] for lane, packet in scores.items() if packet["score"] > 0}

    if not positive and context_lane in VALID_LANES and not _context_reset_requested(text):
        return _result(
            context_lane,
            0.74,
            ["prior_context_lane"],
            "Use prior lane cautiously and ask one confirming question.",
        )

    if not positive:
        return _result(
            LANE_UNCLEAR,
            0.35,
            reasons or ["no_sales_lane_signal"],
            "Clarify whether this is meat, live pigs, slaughter/abattoir, or a general farm question.",
        )

    if _mixed_sales_intent(scores):
        return _result(
            LANE_UNCLEAR,
            0.62,
            reasons + ["mixed_sales_intent"],
            "Clarify the intended lane before continuing.",
        )

    lane = max(positive, key=lambda item: (positive[item], _lane_priority(item)))
    confidence = _confidence(lane, scores, context_lane)
    next_action = _next_action(lane, confidence)
    return _result(lane, confidence, reasons, next_action)


def _normalise(value):
    text = str(value or "").lower()
    text = text.replace("livestock", "live stock")
    text = text.replace("live-stock", "live stock")
    text = text.replace("livepig", "live pig")
    text = text.replace("whatsapp", "whatsapp")
    text = re.sub(r"[^a-z0-9/%+.,;\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _result(lane, confidence, reasons, next_action):
    return {
        "lane": lane,
        "confidence": round(float(confidence), 2),
        "reasons": _unique(reasons),
        "next_action": next_action,
        "writes_allowed": False,
        "customer_send_allowed": False,
        "owner_gate_required": lane in {LANE_OWNER_HANDOFF, LANE_UNCLEAR, LANE_SLAUGHTER},
    }


def _score_terms(text, terms, negation_terms):
    hits = []
    negated = []
    for term in terms:
        if _contains_term(text, term):
            if _is_negated(text, term, negation_terms):
                negated.append(term)
            else:
                hits.append(term)
    score = sum(3 if " " in term else 2 for term in hits)
    return {"score": score, "hits": hits, "negated": negated}


def _hits(text, terms):
    return [term for term in terms if _contains_term(text, term) and not _is_negated(text, term, ())]


def _contains_term(text, term):
    term = str(term or "").lower().strip()
    if not term:
        return False
    if re.search(r"[a-z0-9]", term):
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None
    return term in text


def _is_negated(text, term, extra_negation_terms):
    for match in re.finditer(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text):
        clause_start = max(text.rfind(marker, 0, match.start()) for marker in (".", ",", ";", "\n"))
        before = text[max(clause_start + 1, match.start() - 45):match.start()]
        after = text[match.end():match.end() + 45]
        negators = ("not ", "no ", "dont ", "don't ", "do not ", "without ", "not looking for ", "not asking for ")
        if any(negator in before for negator in negators):
            return True
        if any(extra and extra in before for extra in extra_negation_terms):
            return True
        if any(marker in after for marker in (" not needed", " not now", " no thanks")):
            return True
    return False


def _mixed_sales_intent(scores):
    meat = scores[LANE_MEAT]["score"] > 0
    live = scores[LANE_LIVE_STOCK]["score"] > 0
    slaughter = scores[LANE_SLAUGHTER]["score"] > 0
    if meat and live:
        return True
    if meat and slaughter:
        return True
    return live and slaughter and scores[LANE_SLAUGHTER]["score"] == scores[LANE_LIVE_STOCK]["score"]


def _confidence(lane, scores, context_lane):
    score = scores[lane]["score"]
    other_scores = [value["score"] for key, value in scores.items() if key != lane]
    gap = score - max(other_scores or [0])
    base = 0.78 + min(score, 8) * 0.05 + min(max(gap, 0), 6) * 0.03
    if context_lane == lane:
        base += 0.04
    if lane == LANE_FARM_GENERAL:
        base = min(base, 0.82)
    return min(base, 0.98)


def _next_action(lane, confidence):
    if lane == LANE_MEAT:
        return "Route to SAM Meat Sales; do not enter live-stock rails."
    if lane == LANE_LIVE_STOCK:
        if confidence >= 0.96:
            return "Route to SAM Live Stock planning/runtime; collect missing live-stock facts."
        return "Confirm live-stock intent and collect one missing fact."
    if lane == LANE_SLAUGHTER:
        return "Route to slaughter/abattoir lane or owner review before customer promises."
    if lane == LANE_FARM_GENERAL:
        return "Answer generally or ask whether the customer wants meat, live pigs, or slaughter help."
    return "Clarify sales lane before continuing."


def _lane_priority(lane):
    return {
        LANE_OWNER_HANDOFF: 5,
        LANE_SLAUGHTER: 4,
        LANE_LIVE_STOCK: 3,
        LANE_MEAT: 2,
        LANE_FARM_GENERAL: 1,
        LANE_UNCLEAR: 0,
    }.get(lane, 0)


def _context_reset_requested(text):
    return any(phrase in text for phrase in ("new question", "different thing", "not that", "instead", "change topic"))


def _unique(items):
    result = []
    seen = set()
    for item in items:
        item = str(item or "").strip()
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result


MEAT_TERMS = (
    "pork",
    "meat",
    "half carcass",
    "full carcass",
    "carcass",
    "set a",
    "set b",
    "set c",
    "set d",
    "cut set",
    "cuts",
    "chops",
    "roasts",
    "belly",
    "ribs",
    "mince",
    "stew meat",
    "freezer",
    "freezer pack",
    "packed kg",
    "vleis",
    "pork vleis",
    "vrieskas",
    "vrieskas pak",
)

LIVE_STOCK_TERMS = (
    "live pig",
    "live pigs",
    "live stock",
    "livestock",
    "piglet",
    "piglets",
    "weaner",
    "weaners",
    "grower",
    "growers",
    "finisher",
    "finishers",
    "gilt",
    "gilts",
    "boar",
    "boars",
    "sow",
    "sows",
    "breeding pig",
    "breeding pigs",
    "pigs to raise",
    "buy pigs",
    "buy a pig",
    "buy live",
    "pigs for sale",
    "pig for sale",
    "pigs available",
    "raise pigs",
    "raise a pig",
    "male pig",
    "female pig",
    "price",
    "how much",
    "cost",
    "prys",
    "hoeveel",
    "kos",
    "transport",
    "deliver",
    "delivery",
    "aflewer",
    "vervoer",
    "vark",
    "varke",
    "varkie",
    "varkies",
    "big",
    "biggies",
    "sog",
    "soggie",
    "sow",
    "sows",
    "beer",
    "beertjie",
    "klein varkies",
    "speenvark",
    "speenvarke",
)

SLAUGHTER_TERMS = (
    "abattoir",
    "slaughter",
    "slaughter pig",
    "ready for slaughter",
    "kill",
    "butcher for me",
    "assisted slaughter",
)

FARM_GENERAL_TERMS = (
    "tell me more",
    "tell me more about",
    "tell me more about your ad",
    "about your ad",
    "your ad",
    "your advert",
    "your business",
    "learn more",
    "learn more about",
    "what do you do",
    "what are you selling",
    "what do you sell",
    "where are you",
    "where are u",
    "where u",
    "where you",
    "where are you guys",
    "where are u guys",
    "where are you located",
    "where are u located",
    "where are you based",
    "where are u based",
    "waar is julle",
    "waar is jy",
    "waar is u",
    "waar",
    "location",
    "located",
    "based",
    "ligging",
    "adres",
    "province",
    "provinsie",
    "farm",
    "plaas",
    "amadeus",
    "visiting",
    "open",
    "hours",
    "directions",
    "aanwysings",
    "send pictures",
    "send pics",
    "pictures",
    "photos",
    "pics",
    "foto",
    "fotos",
    "prentjie",
    "prentjies",
)

OWNER_HANDOFF_TERMS = (
    "speak to charl",
    "owner",
    "complaint",
    "refund",
    "discount",
    "special price",
    "credit",
    "proof of payment",
    "pop",
    "paid",
)

MEAT_NEGATION_TERMS = ("not meat", "not pork")
LIVE_STOCK_NEGATION_TERMS = ("not live", "not livestock", "not live stock")
SLAUGHTER_NEGATION_TERMS = ("not slaughter",)

VALID_LANES = {
    LANE_MEAT,
    LANE_LIVE_STOCK,
    LANE_SLAUGHTER,
    LANE_FARM_GENERAL,
    LANE_OWNER_HANDOFF,
    LANE_UNCLEAR,
}
