import json
import os
from urllib import error as urllib_error
from urllib import request as urllib_request

from modules.oom_sakkie.llm_router import (
    API_KEY_ENV,
    API_URL_ENV,
    DEFAULT_API_URL,
    DEFAULT_TIMEOUT_SECONDS,
    MODEL_ENV,
    TIMEOUT_ENV,
)


ANSWER_ENABLED_ENV = "OOM_SAKKIE_LLM_ANSWER_ENABLED"


def llm_answer_enabled():
    return os.getenv(ANSWER_ENABLED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def llm_answer_configured():
    return bool(os.getenv(MODEL_ENV, "").strip() and os.getenv(API_KEY_ENV, "").strip())


def llm_answer_policy():
    return {
        "enabled": llm_answer_enabled(),
        "configured": llm_answer_configured(),
        "provider": "openai_compatible_chat_completions",
        "outbound_endpoint_when_enabled": os.getenv(API_URL_ENV, DEFAULT_API_URL).strip() or DEFAULT_API_URL,
        "sends_user_text_when_enabled": True,
        "sends_tool_summary_when_enabled": True,
        "model_env": MODEL_ENV,
        "api_key_env": API_KEY_ENV,
        "can_write": False,
    }


def compose_answer_with_llm(*, user_text, tool_name, deterministic_answer, stale_warnings, safety_notes):
    if not llm_answer_enabled():
        return None
    if not llm_answer_configured():
        return None

    payload = _build_payload(
        user_text=user_text,
        tool_name=tool_name,
        deterministic_answer=deterministic_answer,
        stale_warnings=stale_warnings,
        safety_notes=safety_notes,
    )
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

    return parse_llm_answer_response(body)


def parse_llm_answer_response(body):
    try:
        data = json.loads(body or "{}")
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(_strip_code_fence(str(content or "")))
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return None

    answer = str(parsed.get("answer") or "").strip()
    if not answer:
        return None
    if _looks_unsafe(answer):
        return None
    return answer[:900]


def _build_payload(*, user_text, tool_name, deterministic_answer, stale_warnings, safety_notes):
    system = (
        "You are Oom Sakkie's read-only answer composer. "
        "Rewrite the provided backend answer into a short, natural farm-operator reply. "
        "Use only the facts in backend_answer, stale_warnings, and safety_notes. "
        "Do not invent numbers, dates, statuses, causes, recommendations, or actions. "
        "Never claim that anything was saved, sent, switched, started, stopped, posted, or changed. "
        "If a safety note or stale warning exists, preserve it plainly. "
        "Keep the answer to one or two sentences unless the backend answer already needs a list. "
        "Return only compact JSON: {\"answer\":\"...\"}."
    )
    user = {
        "user_text": str(user_text or "")[:2000],
        "tool_name": str(tool_name or "")[:80],
        "backend_answer": str(deterministic_answer or "")[:1200],
        "stale_warnings": [str(item)[:240] for item in (stale_warnings or [])[:3]],
        "safety_notes": [str(item)[:240] for item in (safety_notes or [])[:3]],
    }
    return {
        "model": os.getenv(MODEL_ENV, "").strip(),
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, separators=(",", ":"))},
        ],
        "response_format": {"type": "json_object"},
    }


def _looks_unsafe(answer):
    return bool(
        __import__("re").search(
            r"\b(saved|sent|switched|started|stopped|posted|published|changed|updated|deleted|created)\b",
            answer or "",
            __import__("re").I,
        )
    )


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
    return text.strip("`").strip()
