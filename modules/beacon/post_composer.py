import json
import os
import re
from urllib import request as urllib_request


LLM_ENABLED_ENV = "BEACON_BACKEND_LLM_ENABLED"
LLM_MODEL_ENV = "BEACON_BACKEND_LLM_MODEL"
LLM_URL_ENV = "BEACON_BACKEND_LLM_URL"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
DEFAULT_LLM_URL = "https://api.openai.com/v1/chat/completions"

DIRECT_SALES_TERMS = (
    "buy", "sale", "available", "stock", "price", "cost", "discount", "special",
    "order", "book", "reserve", "dm to buy", "message to buy",
)


def build_beacon_caption_suggestions(payload=None, historical_events=None, environ=None, requester=None):
    payload = payload if isinstance(payload, dict) else {}
    source = environ if environ is not None else os.environ
    brief = _clean(payload.get("brief"), 1200)
    lane = _clean(payload.get("campaign_lane") or "live_stock_awareness", 80)
    history = _historical_captions(historical_events or [])
    if len(brief) < 8:
        return _result(False, "post_brief_required", [], history, "none"), 400
    if lane not in {"live_stock_awareness", "meat_launch"}:
        return _result(False, "unsupported_campaign_lane", [], history, "none"), 400

    suggestions = []
    source_name = "evidence_guided_fallback"
    llm_enabled = _truthy(source.get(LLM_ENABLED_ENV) or source.get("SAM_LIVE_STOCK_BACKEND_LLM_ENABLED"))
    if llm_enabled and _model(source) and source.get(OPENAI_API_KEY_ENV):
        suggestions = _llm_suggestions(brief, lane, history, source, requester=requester)
        source_name = "beacon_llm_with_historical_examples" if suggestions else source_name
    if not suggestions:
        suggestions = _fallback_suggestions(brief, lane, history)

    safe = []
    blocked = []
    for suggestion in suggestions:
        text = _clean_caption(suggestion, 2200)
        reasons = caption_safety_issues(text, lane)
        if reasons:
            blocked.append({"text": text, "reasons": reasons})
        elif text and text not in safe:
            safe.append(text)
    if not safe:
        return {
            **_result(False, "all_caption_suggestions_blocked", [], history, source_name),
            "blocked_suggestions": blocked,
        }, 409
    return {
        **_result(True, "caption_suggestions_ready", safe[:3], history, source_name),
        "blocked_suggestions": blocked,
        "style_profile": _style_profile(history),
    }, 200


def caption_safety_issues(text, lane="live_stock_awareness"):
    lowered = _clean(text, 3000).lower()
    issues = []
    if not lowered:
        issues.append("caption_required")
    if lane == "live_stock_awareness":
        issues.extend(f"direct_sales_wording:{term}" for term in DIRECT_SALES_TERMS if _contains_term(lowered, term))
        if re.search(r"(?:^|\s)r\s?\d|\br\d", lowered):
            issues.append("livestock_price_wording_blocked")
    return sorted(set(issues))


def _historical_captions(events):
    captions = []
    for event in events:
        notes = str((event or {}).get("evidence_notes") or "")
        match = re.search(r"(?:Exact text|Text):\s*(.+?)(?:\s+Media reference:|$)", notes, re.I | re.S)
        text = _clean_caption(match.group(1) if match else "", 2200)
        if text and text != "[no message]" and text not in captions:
            captions.append(text)
    return captions[:8]


def _contains_term(text, term):
    return bool(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.I))


def _style_profile(history):
    if not history:
        return {"example_count": 0, "average_length": 0, "uses_emoji": False, "voice": "warm farm storytelling"}
    return {
        "example_count": len(history),
        "average_length": round(sum(len(item) for item in history) / len(history)),
        "uses_emoji": any(any(ord(char) > 10000 for char in item) for item in history),
        "voice": "warm, specific farm storytelling",
    }


def _llm_suggestions(brief, lane, history, source, requester=None):
    examples = "\n\n".join(f"PAST POST {index + 1}:\n{text}" for index, text in enumerate(history[:5]))
    boundary = (
        "This is livestock awareness only. Never mention sales, price, availability, stock, ordering, booking, reserving, or buying."
        if lane == "live_stock_awareness" else
        "This is a meat launch draft. Do not invent prices, availability, quantities, delivery, or guarantees."
    )
    body = {
        "model": _model(source),
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": (
                "You are Beacon, Amadeus Farm's marketing lead. Produce three distinct, polished Facebook captions. "
                "Sound human, warm and confident. Use concrete details from the owner brief, natural paragraphs, and tasteful emojis. "
                "Learn phrasing and rhythm from past posts without copying them. Return JSON only: {\"suggestions\":[\"...\"]}. " + boundary
            )},
            {"role": "user", "content": f"OWNER BRIEF:\n{brief}\n\nPAST APPROVED POSTS:\n{examples or '[none yet]'}"},
        ],
    }
    try:
        if requester:
            response = requester(body)
        else:
            req = urllib_request.Request(
                source.get(LLM_URL_ENV) or DEFAULT_LLM_URL,
                data=json.dumps(body).encode("utf-8"),
                headers={"Authorization": f"Bearer {source[OPENAI_API_KEY_ENV]}", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib_request.urlopen(req, timeout=30) as raw:
                response = json.loads(raw.read().decode("utf-8"))
        if isinstance(response, dict) and isinstance(response.get("suggestions"), list):
            return response["suggestions"]
        content = (((response.get("choices") or [{}])[0].get("message") or {}).get("content") or "{}")
        decoded = json.loads(content) if isinstance(content, str) else content
        return decoded.get("suggestions", []) if isinstance(decoded, dict) else []
    except (OSError, TimeoutError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return []


def _fallback_suggestions(brief, lane, history):
    base = brief.rstrip(" .")
    if lane == "live_stock_awareness":
        return [
            f"🐷🌿 A little farm update from Amadeus Farm.\n\n{base}.\n\nThese are the moments we love sharing: healthy animals, steady progress and plenty of personality along the way. We’ll keep sharing their journey as it unfolds. 💛",
            f"There is always something worth noticing on the farm. 🐖\n\n{base}.\n\nIt is rewarding to watch the small daily changes add up, and we are looking forward to sharing more of the journey with you. 🌱",
            f"🐷 Farm life, one good moment at a time.\n\n{base}.\n\nStrong, curious and growing well - exactly what we love to see. Follow along for more from Amadeus Farm. 💛🌿",
        ]
    return [
        f"A new chapter is taking shape at Amadeus Farm.\n\n{base}.\n\nWe are preparing carefully and will share the confirmed details as the journey develops.",
        f"Behind the scenes at Amadeus Farm: {base}.\n\nThoughtful preparation comes first. More confirmed details will follow soon.",
        f"Something new is coming from Amadeus Farm.\n\n{base}.\n\nWe are taking it step by step and look forward to sharing more.",
    ]


def _model(source):
    return _clean(source.get(LLM_MODEL_ENV) or source.get("SAM_LIVE_STOCK_BACKEND_LLM_MODEL"), 120)


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _clean(value, limit):
    return " ".join(str(value or "").replace("\x00", " ").split())[:limit]


def _clean_caption(value, limit):
    lines = [" ".join(line.split()) for line in str(value or "").replace("\x00", " ").splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()[:limit]


def _result(success, status, suggestions, history, source):
    return {
        "success": success,
        "status": status,
        "suggestions": suggestions,
        "suggestion_source": source,
        "historical_example_count": len(history),
        "calls_meta": False,
        "posts_publicly": False,
        "spends_money": False,
        "sends_customer_message": False,
        "changes_stock": False,
    }
