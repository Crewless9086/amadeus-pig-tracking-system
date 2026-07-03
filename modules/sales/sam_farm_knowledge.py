import json
import os
from pathlib import Path


KNOWLEDGE_PATH_ENV = "SAM_FARM_KNOWLEDGE_PATH"
DEFAULT_KNOWLEDGE_PATH = Path(__file__).resolve().parents[2] / "config" / "sam_farm_knowledge.json"

DEFAULT_KNOWLEDGE = {
    "version": "fallback",
    "status": "fallback_default",
    "public_profile": {
        "farm_name": "Amadeus Farm",
        "agent_name": "Sam",
        "short_intro": "Hi, I am Sam from Amadeus Farm.",
        "one_line_story": "We help customers with planned farm pork preorders and related farm sales questions.",
        "location_summary": "Riversdale area, with delivery planned per farm run.",
        "google_maps_url": "",
        "service_areas": ["Riversdale"],
    },
    "voice": {
        "style": "warm, practical, human, calm, and concise",
        "frustration_acknowledgement": "I hear you. I will keep this practical.",
    },
    "product_menu": [
        {"key": "meat_sales", "label": "Pork meat sales", "summary": "Half carcass, full carcass, and cut-set preorder options."},
        {"key": "live_sales", "label": "Live pig sales", "summary": "Live pig interest can be captured."},
        {"key": "farm_info", "label": "Farm information", "summary": "Farm story, location, and general questions."},
    ],
    "meat_sales": {
        "positioning": "Pre-booked Amadeus Farm pork for freezer buyers.",
        "core_options": ["half carcass", "full carcass", "custom cuts", "assisted slaughter"],
        "payment_rule": "For meat sales we use EFT only for now so the reference and payment trail stay clean.",
        "pilot_payment_rule": "For meat sales we use EFT only for now so the reference and payment trail stay clean.",
        "deposit_explanation": "The deposit holds the customer's place in the preorder run and helps the farm plan properly.",
        "pop_explanation": "Proof of payment is useful evidence, but the booking only moves forward once the money reflects in the farm account.",
    },
    "cut_sets": {},
    "faq": {},
    "blocked_claims": [],
}


def load_sam_farm_knowledge(environ=None):
    source = environ if environ is not None else os.environ
    path = Path(str(source.get(KNOWLEDGE_PATH_ENV) or DEFAULT_KNOWLEDGE_PATH)).expanduser()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _result("fallback_default_file_missing", path, DEFAULT_KNOWLEDGE, configured=False)
    except json.JSONDecodeError as exc:
        return {
            **_result("fallback_default_invalid_json", path, DEFAULT_KNOWLEDGE, configured=False),
            "error": str(exc)[:240],
        }
    except OSError as exc:
        return {
            **_result("fallback_default_read_failed", path, DEFAULT_KNOWLEDGE, configured=False),
            "error": str(exc)[:240],
        }
    knowledge = _deep_merge(DEFAULT_KNOWLEDGE, loaded if isinstance(loaded, dict) else {})
    return _result("ok", path, _sanitize_knowledge(knowledge), configured=True)


def public_profile(knowledge):
    return (knowledge if isinstance(knowledge, dict) else {}).get("public_profile") or DEFAULT_KNOWLEDGE["public_profile"]


def meat_sales_knowledge(knowledge):
    return (knowledge if isinstance(knowledge, dict) else {}).get("meat_sales") or DEFAULT_KNOWLEDGE["meat_sales"]


def product_menu_text(knowledge):
    items = (knowledge if isinstance(knowledge, dict) else {}).get("product_menu")
    if not isinstance(items, list):
        items = DEFAULT_KNOWLEDGE["product_menu"]
    labels = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = _clean(item.get("label"), 80)
        summary = _clean(item.get("summary"), 180)
        if label and summary:
            labels.append(f"{label}: {summary}")
        elif label:
            labels.append(label)
    return "; ".join(labels[:5])


def _result(status, path, knowledge, configured):
    return {
        "success": True,
        "status": status,
        "configured": configured,
        "path": str(path),
        "knowledge": _sanitize_knowledge(knowledge),
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "creates_order": False,
        "changes_stock": False,
    }


def _deep_merge(base, override):
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _sanitize_knowledge(value):
    if isinstance(value, dict):
        return {str(key)[:80]: _sanitize_knowledge(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_knowledge(item) for item in value[:50]]
    return _clean(value, 1200)


def _clean(value, limit=200):
    return " ".join(str(value or "").split())[:limit]
