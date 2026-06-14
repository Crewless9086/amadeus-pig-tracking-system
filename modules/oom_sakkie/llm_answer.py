import json
import os
import re
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
UNSAFE_ACTION_RE = re.compile(
    r"\b(saved|sent|switched|started|stopped|posted|published|changed|updated|deleted|created)\b",
    re.I,
)
NEGATED_SAFETY_RE = re.compile(r"\b(no|not|never|nothing|did not|didn't|was not|wasn't|is not|isn't)\b", re.I)


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
        "sends_capped_tool_context_when_enabled": True,
        "model_env": MODEL_ENV,
        "api_key_env": API_KEY_ENV,
        "can_write": False,
    }


def compose_answer_with_llm(*, user_text, tool_name, deterministic_answer, stale_warnings, safety_notes, raw_context=None):
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
        raw_context=raw_context,
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

    answer = parse_llm_answer_response(body)
    if _looks_off_topic(answer, tool_name):
        return None
    return answer


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


def _build_payload(*, user_text, tool_name, deterministic_answer, stale_warnings, safety_notes, raw_context=None):
    system = (
        "You are Oom Sakkie, the farm operating co-pilot. "
        "You are not a generic assistant and you do not read tables back like a clerk. "
        "Rewrite the provided backend answer into a useful spoken briefing for the farm owner. "
        "Use only the facts in backend_answer, backend_context, stale_warnings, and safety_notes. "
        "Do not invent numbers, dates, statuses, causes, recommendations, or actions. "
        "Never claim that anything was saved, sent, switched, started, stopped, posted, or changed. "
        "If a safety note or stale warning exists, preserve it plainly. "
        "Lead with the operational meaning, then the key facts. "
        "If backend_context includes multiple items, prioritize what the owner should look at first and why. "
        "Do not recite every ID unless the ID is useful for inspection. "
        "For jarvis_daily_command_brief, give one owner-ready command brief across farm, business, and command-center sections; "
        "lead with the highest priority and end with the next owner decision if one is present. "
        "For jarvis_owner_review_packet, state whether the review packet is ready, name the Claude handoff file, and clearly say no authority is approved by the packet. "
        "For farm_operating_brief, mention all required sections: attention or priority, power, weather, and irrigation. "
        "For business_growth_brief, sound like a business advisor: lead with the commercial move, name the stock or ready pigs that justify it, "
        "if backend_context.offer_brief_outline exists, summarize it as an internal offer brief outline only, not customer-facing copy, "
        "then ask exactly one approval-style follow-up question from backend_context.owner_question if present. "
        "For sales_offer_brief, summarize the owner-review draft only; explicitly avoid customer-facing copy and never imply a message, quote, sale, reservation, or stock change happened. "
        "For system_work_status, state the next owner action first, then mention build/patch/deploy/dispatch-design counts only if useful. "
        "For every other tool, stay in that tool's lane. Do not mention unrelated systems that were not checked. "
        "Never say things like 'power is not part of this' or 'weather was not evaluated' unless a safety note explicitly says it. "
        "If there are no stale warnings or safety notes, do not say 'no stale warning' or 'no safety note'. "
        "For operating briefs, use at most three short sentences: first priority, system status, and any safety/stale note. "
        "Sound calm, direct, and present: 'I'd look at the litter queue first; power is fine for now.' "
        "Avoid assistant openers like 'Based on the data', 'Here is', 'I can help', and 'Certainly'. "
        "Keep the answer to one to three short spoken sentences unless the backend answer already needs a list. "
        "Return only compact JSON: {\"answer\":\"...\"}."
    )
    user = {
        "user_text": str(user_text or "")[:2000],
        "tool_name": str(tool_name or "")[:80],
        "backend_answer": str(deterministic_answer or "")[:1200],
        "backend_context": _safe_json_excerpt(raw_context),
        "stale_warnings": [str(item)[:240] for item in (stale_warnings or [])[:3]],
        "safety_notes": [str(item)[:240] for item in (safety_notes or [])[:3]],
    }
    return {
        "model": os.getenv(MODEL_ENV, "").strip(),
        "temperature": 0.55,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, separators=(",", ":"))},
        ],
        "response_format": {"type": "json_object"},
    }


def _looks_unsafe(answer):
    text = answer or ""
    for match in UNSAFE_ACTION_RE.finditer(text):
        prefix = text[max(0, match.start() - 40):match.start()]
        if NEGATED_SAFETY_RE.search(prefix):
            continue
        return True
    return False


def _looks_off_topic(answer, tool_name):
    if not answer:
        return False
    if str(tool_name or "") in {"farm_operating_brief", "jarvis_daily_command_brief", "jarvis_owner_review_packet"}:
        return False
    text = answer.lower().replace("’", "'").replace("‘", "'")
    blocked_fragments = (
        "not part of this",
        "not evaluated",
        "weren't evaluated",
        "wasn't evaluated",
        "aren't evaluated",
        "isn't evaluated",
        "not provided here",
        "not reported here",
        "not checked here",
        "no stale warning",
        "no safety note",
    )
    return any(fragment in text for fragment in blocked_fragments)


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


def _safe_json_excerpt(value):
    try:
        text = json.dumps(value or {}, default=str, ensure_ascii=True, sort_keys=True)
    except (TypeError, ValueError):
        text = json.dumps({"unavailable": True}, separators=(",", ":"))
    return text[:3000]
