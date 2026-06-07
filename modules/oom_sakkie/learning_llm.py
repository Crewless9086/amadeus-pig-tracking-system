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


ENABLED_ENV = "OOM_SAKKIE_LLM_LEARNING_ENABLED"
ALLOWED_KINDS = {
    "routing_review",
    "data_freshness_review",
    "answer_style_review",
    "tool_gap_review",
    "briefing_structure_review",
    "test_gap_review",
    "tool_pattern_review",
}
ALLOWED_PRIORITIES = {"high", "medium", "normal", "low"}


def llm_learning_enabled():
    return os.getenv(ENABLED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def llm_learning_configured():
    return bool(os.getenv(MODEL_ENV, "").strip() and os.getenv(API_KEY_ENV, "").strip())


def llm_learning_policy():
    return {
        "enabled": llm_learning_enabled(),
        "configured": llm_learning_configured(),
        "provider": "openai_compatible_chat_completions",
        "outbound_endpoint_when_enabled": os.getenv(API_URL_ENV, DEFAULT_API_URL).strip() or DEFAULT_API_URL,
        "sends_trace_text_when_enabled": True,
        "writes_code": False,
        "writes_feedback": False,
        "can_apply_changes": False,
        "requires_human_approval": True,
        "model_env": MODEL_ENV,
        "api_key_env": API_KEY_ENV,
    }


def analyze_learning_with_llm(*, summary, issue_traces, deterministic_proposals):
    if not llm_learning_enabled():
        return {"ran": False, "status": "disabled", "proposals": []}
    if not llm_learning_configured():
        return {"ran": False, "status": "not_configured", "proposals": []}

    payload = _build_payload(
        summary=summary,
        issue_traces=issue_traces,
        deterministic_proposals=deterministic_proposals,
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
        return {"ran": False, "status": "network_failed", "proposals": []}

    parsed = parse_learning_response(body)
    if not parsed["proposals"]:
        parsed["status"] = "empty_or_invalid"
    return parsed


def parse_learning_response(body):
    try:
        data = json.loads(body or "{}")
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(_strip_code_fence(str(content or "")))
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return {"ran": True, "status": "parse_failed", "proposals": []}

    proposals = []
    for item in parsed.get("proposals") or []:
        proposal = _clean_proposal(item)
        if proposal:
            proposals.append(proposal)
    return {
        "ran": True,
        "status": "ok" if proposals else "empty_or_invalid",
        "proposals": proposals[:5],
    }


def _build_payload(*, summary, issue_traces, deterministic_proposals):
    system = (
        "You are Oom Sakkie's Learning Analyst. "
        "Your job is to inspect reviewed kiosk traces and propose narrow, human-approved improvements. "
        "You cannot edit code, change prompts, write feedback, send messages, or alter farm data. "
        "Use only the trace evidence provided. Do not invent missing systems or claim you applied a fix. "
        "Prefer small improvements: routing alias, answer wording rule, stale-data handling, test gap, or read-only tool gap. "
        "Every proposal must require human approval. "
        "Return compact JSON only: {\"proposals\":[{\"kind\":\"...\",\"priority\":\"high|medium|normal|low\",\"title\":\"...\",\"evidence\":\"...\",\"recommended_action\":\"...\",\"approval_required\":true}]}."
    )
    user = {
        "review_summary": summary or {},
        "issue_traces": _trace_excerpt(issue_traces),
        "deterministic_proposals": deterministic_proposals or [],
        "allowed_kinds": sorted(ALLOWED_KINDS),
    }
    return {
        "model": os.getenv(MODEL_ENV, "").strip(),
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, default=str, separators=(",", ":"))[:6000]},
        ],
        "response_format": {"type": "json_object"},
    }


def _trace_excerpt(issue_traces):
    traces = []
    for row in (issue_traces or [])[:12]:
        feedback = row.get("latest_feedback") or {}
        traces.append({
            "trace_id": str(row.get("trace_id") or "")[:96],
            "tool_name": str(row.get("tool_name") or "")[:80],
            "feedback_type": str(feedback.get("feedback_type") or "")[:64],
            "user_text": str(row.get("user_text") or "")[:500],
            "answer": str(row.get("answer") or "")[:700],
            "stale_warnings": [str(item)[:200] for item in (row.get("stale_warnings") or [])[:3]],
            "safety_notes": [str(item)[:200] for item in (row.get("safety_notes") or [])[:3]],
        })
    return traces


def _clean_proposal(item):
    if not isinstance(item, dict):
        return None
    kind = str(item.get("kind") or "").strip()
    if kind not in ALLOWED_KINDS:
        return None
    priority = str(item.get("priority") or "normal").strip().lower()
    if priority not in ALLOWED_PRIORITIES:
        priority = "normal"
    title = str(item.get("title") or "").strip()[:120]
    evidence = str(item.get("evidence") or "").strip()[:360]
    action = str(item.get("recommended_action") or "").strip()[:360]
    if not title or not evidence or not action:
        return None
    return {
        "kind": kind,
        "priority": priority,
        "title": title,
        "evidence": evidence,
        "recommended_action": action,
        "approval_required": True,
        "source": "llm_learning_analyst",
    }


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
