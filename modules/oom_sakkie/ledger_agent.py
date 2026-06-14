import json
import os
import re
from urllib import error as urllib_error
from urllib import request as urllib_request

LEDGER_AGENT_ENABLED_ENV = "OOM_SAKKIE_LEDGER_AGENT_ENABLED"
MODEL_ENV = "OOM_SAKKIE_LLM_ROUTER_MODEL"
API_KEY_ENV = "OPENAI_API_KEY"
API_URL_ENV = "OOM_SAKKIE_LLM_ROUTER_URL"
TIMEOUT_ENV = "OOM_SAKKIE_LLM_ROUTER_TIMEOUT_SECONDS"
DEFAULT_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_TIMEOUT_SECONDS = 8
MAX_STRATEGY_CHARS = 900
MAX_DRAFT_CHARS = 900
MAX_LIST_ITEMS = 5
FORBIDDEN_RESPONSE_KEYS = {
    "send",
    "sent",
    "quote",
    "order",
    "reservation",
    "stock_update",
    "sql",
    "tool_call",
    "webhook",
    "chatwoot",
    "whatsapp",
}
UNSAFE_CLAIM_RE = re.compile(
    r"\b(sent|posted|published|created\s+(?:a\s+)?quote|created\s+(?:an?\s+)?order|"
    r"reserved|booked|changed\s+stock|updated\s+stock|contacted\s+customers)\b",
    re.I,
)
NEGATED_SAFETY_RE = re.compile(r"\b(no|not|never|nothing|did not|didn't|was not|wasn't|without)\b", re.I)


def ledger_agent_enabled(environ=None):
    source = environ if environ is not None else os.environ
    return str(source.get(LEDGER_AGENT_ENABLED_ENV, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def ledger_agent_configured(environ=None):
    source = environ if environ is not None else os.environ
    return bool(str(source.get(MODEL_ENV, "") or "").strip() and str(source.get(API_KEY_ENV, "") or "").strip())


def ledger_agent_policy(environ=None):
    source = environ if environ is not None else os.environ
    enabled = ledger_agent_enabled(source)
    configured = ledger_agent_configured(source)
    return {
        "enabled": enabled and configured,
        "explicitly_enabled": enabled,
        "configured": configured,
        "mode": "owner_only_ledger_sales_advisor",
        "provider": "openai_compatible_chat_completions",
        "outbound_endpoint_when_enabled": str(source.get(API_URL_ENV, DEFAULT_API_URL) or DEFAULT_API_URL).strip() or DEFAULT_API_URL,
        "sends_owner_sales_context_when_enabled": True,
        "model_env": MODEL_ENV,
        "api_key_env": API_KEY_ENV,
        "enable_env": LEDGER_AGENT_ENABLED_ENV,
        "output_mode": "owner_review_strategy_and_copy_only",
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_n8n": False,
        "creates_quote": False,
        "creates_order": False,
        "changes_stock": False,
        "writes": False,
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
    }


def run_ledger_sales_agent(*, user_text, offer_context, draft_context, environ=None):
    source = environ if environ is not None else os.environ
    policy = ledger_agent_policy(source)
    if not policy["explicitly_enabled"]:
        return _fallback("ledger_agent_disabled", policy, "Ledger's LLM advisor is disabled. Use /offer and /draft for deterministic owner-review material.")
    if not policy["configured"]:
        return _fallback("ledger_agent_not_configured", policy, "Ledger's LLM advisor is enabled but missing model or API key configuration.")

    payload = _build_payload(user_text=user_text, offer_context=offer_context, draft_context=draft_context, source=source)
    request = urllib_request.Request(
        policy["outbound_endpoint_when_enabled"],
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {str(source.get(API_KEY_ENV, '') or '').strip()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=_timeout_seconds(source)) as response:
            body = response.read().decode("utf-8")
    except (urllib_error.HTTPError, urllib_error.URLError, TimeoutError, OSError):
        return _fallback("ledger_agent_unavailable", policy, "Ledger's LLM advisor could not be reached. No customer action was taken.")

    parsed = parse_ledger_agent_response(body)
    if not parsed:
        return _fallback("ledger_agent_rejected_response", policy, "Ledger's LLM advisor returned an unsafe or unusable draft. No customer action was taken.")

    parsed.update({
        "success": True,
        "status": "ledger_agent_advice_ready",
        "policy": policy,
        "llm_called": True,
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_n8n": False,
        "creates_quote": False,
        "creates_order": False,
        "changes_stock": False,
        "writes": False,
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
    })
    return parsed


def parse_ledger_agent_response(body):
    try:
        data = json.loads(body or "{}")
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(_strip_code_fence(str(content or "")))
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if _has_forbidden_key(parsed):
        return None
    strategy = _clean_text(parsed.get("strategy"), MAX_STRATEGY_CHARS)
    customer_draft = _clean_text(parsed.get("customer_draft"), MAX_DRAFT_CHARS)
    next_action = _clean_text(parsed.get("next_action"), 300)
    if not strategy or not customer_draft or not next_action:
        return None
    combined = " ".join([strategy, customer_draft, next_action])
    if _looks_unsafe(combined):
        return None
    return {
        "strategy": strategy,
        "customer_draft": customer_draft,
        "owner_questions": _clean_list(parsed.get("owner_questions"), 180),
        "risks": _clean_list(parsed.get("risks"), 180),
        "next_action": next_action,
    }


def _build_payload(*, user_text, offer_context, draft_context, source):
    system = (
        "You are Ledger, the farm owner's sales advisor inside Oom Sakkie. "
        "Use only the provided backend sales and meat context. "
        "Your job is to help the owner decide how to sell ready meat stock and improve owner-review buyer copy. "
        "Do not claim that you sent, posted, quoted, booked, reserved, changed stock, contacted a customer, or created an order. "
        "Do not invent prices, exact availability dates, delivery terms, buyer names, or health status. "
        "Treat all output as owner-review draft material only. "
        "Return compact JSON with exactly these useful keys: strategy, customer_draft, owner_questions, risks, next_action."
    )
    user = {
        "owner_request": str(user_text or "")[:1200],
        "offer_context": _safe_json_excerpt(offer_context),
        "draft_context": _safe_json_excerpt(draft_context),
        "hard_limits": {
            "customer_send_allowed": False,
            "chatwoot_allowed": False,
            "whatsapp_allowed": False,
            "quote_or_order_allowed": False,
            "stock_change_allowed": False,
            "prices_must_be_owner_confirmed": True,
        },
    }
    return {
        "model": str(source.get(MODEL_ENV, "") or "").strip(),
        "temperature": 0.35,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, separators=(",", ":"))},
        ],
        "response_format": {"type": "json_object"},
    }


def _fallback(status, policy, summary):
    return {
        "success": False,
        "status": status,
        "strategy": summary,
        "customer_draft": "",
        "owner_questions": ["Enable Ledger's LLM advisor only when you want owner-only sales strategy help."],
        "risks": ["No LLM advice was produced and no customer action was taken."],
        "next_action": "Use /offer or /draft, or enable Ledger's LLM advisor after setting the required env.",
        "policy": policy,
        "llm_called": False,
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_n8n": False,
        "creates_quote": False,
        "creates_order": False,
        "changes_stock": False,
        "writes": False,
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
    }


def _has_forbidden_key(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            clean = str(key or "").strip().lower()
            if any(token in clean for token in FORBIDDEN_RESPONSE_KEYS):
                return True
            if _has_forbidden_key(nested):
                return True
    if isinstance(value, list):
        return any(_has_forbidden_key(item) for item in value)
    return False


def _looks_unsafe(text):
    for match in UNSAFE_CLAIM_RE.finditer(text or ""):
        prefix = text[max(0, match.start() - 45):match.start()]
        if NEGATED_SAFETY_RE.search(prefix):
            continue
        return True
    return False


def _clean_text(value, limit):
    text = " ".join(str(value or "").split())
    return text[:limit]


def _clean_list(value, limit):
    if not isinstance(value, list):
        return []
    return [_clean_text(item, limit) for item in value[:MAX_LIST_ITEMS] if _clean_text(item, limit)]


def _timeout_seconds(source):
    try:
        return max(1, min(30, int(source.get(TIMEOUT_ENV, DEFAULT_TIMEOUT_SECONDS))))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS


def _safe_json_excerpt(value):
    try:
        text = json.dumps(value or {}, default=str, ensure_ascii=True, sort_keys=True)
    except (TypeError, ValueError):
        text = json.dumps({"unavailable": True}, separators=(",", ":"))
    return text[:4000]


def _strip_code_fence(value):
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text.strip("`").strip()
