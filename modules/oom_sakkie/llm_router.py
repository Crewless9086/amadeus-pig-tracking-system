import json
import os
from dataclasses import dataclass
from urllib import error as urllib_error
from urllib import request as urllib_request

from modules.oom_sakkie.tools import RiskLevel, TOOL_REGISTRY


ENABLED_ENV = "OOM_SAKKIE_LLM_ROUTER_ENABLED"
MODEL_ENV = "OOM_SAKKIE_LLM_ROUTER_MODEL"
API_KEY_ENV = "OPENAI_API_KEY"
API_URL_ENV = "OOM_SAKKIE_LLM_ROUTER_URL"
TIMEOUT_ENV = "OOM_SAKKIE_LLM_ROUTER_TIMEOUT_SECONDS"
DEFAULT_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_TIMEOUT_SECONDS = 8


@dataclass(frozen=True)
class LlmRouteResult:
    intent: str
    tool_name: str
    confidence: float
    reason: str
    needs_clarification: bool = False
    clarification_question: str = ""


def llm_router_enabled():
    return os.getenv(ENABLED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def llm_router_configured():
    return bool(os.getenv(MODEL_ENV, "").strip() and os.getenv(API_KEY_ENV, "").strip())


def llm_router_policy():
    return {
        "enabled": llm_router_enabled(),
        "configured": llm_router_configured(),
        "provider": "openai_compatible_chat_completions",
        "outbound_endpoint_when_enabled": os.getenv(API_URL_ENV, DEFAULT_API_URL).strip() or DEFAULT_API_URL,
        "sends_user_text_when_enabled": True,
        "model_env": MODEL_ENV,
        "api_key_env": API_KEY_ENV,
        "allowed_tools": sorted(_allowed_tool_names()),
        "max_risk_level": int(RiskLevel.READ_ONLY),
        "can_write": False,
    }


def route_with_llm(text):
    if not llm_router_enabled():
        return None
    if not llm_router_configured():
        return None

    payload = _build_payload(text)
    req = urllib_request.Request(
        os.getenv(API_URL_ENV, DEFAULT_API_URL).strip() or DEFAULT_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {os.getenv(API_KEY_ENV, '').strip()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=_timeout_seconds()) as response:
            body = response.read().decode("utf-8")
    except (urllib_error.HTTPError, urllib_error.URLError, TimeoutError, OSError):
        return None

    return parse_llm_route_response(body)


def parse_llm_route_response(body):
    try:
        data = json.loads(body or "{}")
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(_strip_code_fence(str(content or "")))
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return None

    tool_name = str(parsed.get("tool_name") or "").strip()
    needs_clarification = bool(parsed.get("needs_clarification"))
    confidence = _bounded_confidence(parsed.get("confidence"))
    if needs_clarification or tool_name == "clarification":
        return LlmRouteResult(
            intent="llm_clarification",
            tool_name="",
            confidence=confidence,
            reason=_clean_reason(parsed.get("reason") or "llm:clarification"),
            needs_clarification=True,
            clarification_question=_clean_question(parsed.get("clarification_question")),
        )

    if tool_name not in _allowed_tool_names():
        return None
    return LlmRouteResult(
        intent=str(parsed.get("intent") or tool_name).strip()[:80],
        tool_name=tool_name,
        confidence=confidence,
        reason=_clean_reason(parsed.get("reason") or "llm:tool_selection"),
    )


def _build_payload(text):
    allowed = [
        {
            "name": tool.name,
            "description": tool.description,
        }
        for tool in TOOL_REGISTRY.values()
        if tool.risk_level == RiskLevel.READ_ONLY and not tool.requires_confirmation
    ]
    system = (
        "You are the Oom Sakkie read-only tool router. "
        "Choose exactly one approved read-only tool for the user's farm question, or ask for clarification. "
        "Prefer the best safe read-only tool when a broad operational question reasonably maps to one: "
        "inspection, priority, worry, or what-to-check-first questions usually map to farm_attention_summary; "
        "outside conditions usually map to weather_today unless the user asks for future conditions; "
        "energy, inverter, solar, battery, or grid questions map to power_current. "
        "Never invent tools. Never choose writes, messages, public posting, hardware control, or customer actions. "
        "Return only compact JSON with keys: intent, tool_name, confidence, reason, needs_clarification, clarification_question. "
        "Use tool_name='clarification' and needs_clarification=true only when no approved read-only tool is a reasonable fit."
    )
    # The tool list sent to the LLM is guidance only; parse-time allowlist
    # validation against _allowed_tool_names() is the real safety gate.
    user = {
        "user_text": str(text or "")[:2000],
        "allowed_tools": allowed,
    }
    return {
        "model": os.getenv(MODEL_ENV, "").strip(),
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, separators=(",", ":"))},
        ],
        "response_format": {"type": "json_object"},
    }


def _allowed_tool_names():
    return {
        tool.name
        for tool in TOOL_REGISTRY.values()
        if tool.risk_level == RiskLevel.READ_ONLY and not tool.requires_confirmation
    }


def _bounded_confidence(value):
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


def _timeout_seconds():
    try:
        return max(1, min(30, int(os.getenv(TIMEOUT_ENV, DEFAULT_TIMEOUT_SECONDS))))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS


def _strip_code_fence(value):
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def _clean_reason(value):
    return str(value or "")[:160]


def _clean_question(value):
    question = str(value or "").strip()
    return question[:240] or "Which farm system should I check?"
