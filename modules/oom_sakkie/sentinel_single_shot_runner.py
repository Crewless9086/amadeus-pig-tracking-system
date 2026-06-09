import json
import os
from urllib import error as urllib_error
from urllib import request as urllib_request

from modules.oom_sakkie.agent_dry_run_result_store import record_sentinel_single_shot_result
from modules.oom_sakkie.dispatch_decision_store import get_dispatch_request
from modules.oom_sakkie.dispatch_execution_approval_store import (
    dispatch_execution_approval_consumed,
    get_dispatch_execution_approval,
    record_dispatch_execution_approval_event,
)
from modules.oom_sakkie.llm_answer import _looks_unsafe
from modules.oom_sakkie.llm_router import (
    API_KEY_ENV,
    API_URL_ENV,
    DEFAULT_API_URL,
    DEFAULT_TIMEOUT_SECONDS,
    MODEL_ENV,
    TIMEOUT_ENV,
)


SPECIALIST_DRY_RUN_ENABLED_ENV = "OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED"


def specialist_dry_run_enabled():
    return os.getenv(SPECIALIST_DRY_RUN_ENABLED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def specialist_dry_run_configured():
    return bool(os.getenv(MODEL_ENV, "").strip() and os.getenv(API_KEY_ENV, "").strip())


def specialist_dry_run_policy():
    return {
        "enabled": specialist_dry_run_enabled(),
        "configured": specialist_dry_run_configured(),
        "provider": "openai_compatible_chat_completions",
        "outbound_endpoint_when_enabled": os.getenv(API_URL_ENV, DEFAULT_API_URL).strip() or DEFAULT_API_URL,
        "sends_capped_read_only_context_when_enabled": True,
        "specialist_slug": "sentinel",
        "mode": "single_shot_advisory_only",
        "requires_dispatch_execution_approval": True,
        "runs_specialist_tools": False,
        "writes": False,
        "dispatches_further": False,
        "model_env": MODEL_ENV,
        "api_key_env": API_KEY_ENV,
        "enabled_env": SPECIALIST_DRY_RUN_ENABLED_ENV,
        "can_write": False,
    }


def run_sentinel_single_shot_dry_run(approval_id, database_url=None):
    approval_id = str(approval_id or "").strip()[:100]
    if not approval_id:
        return {"success": False, "status": "approval_id_required"}, 400
    if not specialist_dry_run_enabled():
        return {
            "success": False,
            "status": "specialist_dry_run_disabled",
            "enabled_env": SPECIALIST_DRY_RUN_ENABLED_ENV,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
        }, 403
    if not specialist_dry_run_configured():
        return {
            "success": False,
            "status": "specialist_dry_run_not_configured",
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
        }, 503

    loaded, loaded_status = get_dispatch_execution_approval(approval_id, database_url=database_url)
    if loaded_status != 200:
        return loaded, loaded_status
    approval = loaded.get("execution_approval", {})
    validation, validation_status = _validate_approval_for_execution(approval, database_url=database_url)
    if validation_status != 200:
        return validation, validation_status
    dry_run_request_id = validation["dry_run_request_id"]
    dispatch_request = validation["dispatch_request"]

    consumed, consumed_status = dispatch_execution_approval_consumed(approval_id, database_url=database_url)
    if consumed_status != 200:
        return consumed, consumed_status
    if consumed.get("consumed"):
        return {
            "success": False,
            "status": "dispatch_execution_approval_already_consumed",
            "approval_id": approval_id,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
        }, 409

    consume_event, consume_status = record_dispatch_execution_approval_event(
        approval_id,
        {
            "event_type": "consumed_by_single_dry_run_result",
            "notes": "Single-shot Sentinel advisory dry-run attempt started. This approval cannot be replayed.",
            "recorded_by": "sentinel_single_shot_runner",
        },
        database_url=database_url,
        allow_consumed=True,
    )
    if consume_status != 201:
        return consume_event, consume_status

    llm_result = _call_sentinel_llm(
        approval=approval,
        dispatch_request=dispatch_request,
        dry_run_request_id=dry_run_request_id,
    )
    if not llm_result:
        return {
            "success": False,
            "status": "sentinel_single_shot_llm_failed",
            "approval_id": approval_id,
            "consumed": True,
            "runs_specialist_llm": True,
            "runs_specialist_tools": False,
            "writes": False,
            "note": "The one-shot approval was consumed before the outbound call to prevent replay.",
        }, 502

    stored, stored_status = record_sentinel_single_shot_result(
        dry_run_request_id,
        {
            "approval_id": approval_id,
            "result_text": llm_result["result_text"],
            "findings": llm_result["findings"],
            "recommended_next_gate": "owner_review_before_learning_or_runtime_change",
            "recorded_by": "sentinel_single_shot_runner",
        },
        database_url=database_url,
    )
    if stored_status != 201:
        return stored, stored_status

    return {
        "success": True,
        "status": "ok",
        "mode": "single_shot_sentinel_advisory_result",
        "approval_id": approval_id,
        "dispatch_request_id": approval.get("dispatch_request_id", ""),
        "dry_run_request_id": dry_run_request_id,
        "dry_run_result_id": stored.get("dry_run_result_id", ""),
        "result_text": llm_result["result_text"],
        "findings": llm_result["findings"],
        "consumed_event": consume_event,
        "runs_specialist_llm": True,
        "runs_specialist_tools": False,
        "writes": False,
        "applies_runtime_change": False,
        "dispatches_further": False,
        "next_gate": "owner_review_before_learning_or_runtime_change",
        "safety_notes": [
            "Sentinel single-shot dry-run is advisory only. No specialist tools ran, no farm data was written, and no public/customer output was created."
        ],
    }, 201


def parse_sentinel_single_shot_response(body):
    try:
        data = json.loads(body or "{}")
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(_strip_code_fence(str(content or "")))
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return None

    result_text = str(parsed.get("result_text") or parsed.get("answer") or "").strip()
    findings = parsed.get("findings") or []
    findings = [str(item).strip()[:500] for item in list(findings)[:12] if str(item).strip()]
    if not result_text:
        return None
    if _looks_unsafe(result_text) or any(_looks_unsafe(item) for item in findings):
        return None
    return {
        "result_text": result_text[:6000],
        "findings": findings,
    }


def _validate_approval_for_execution(approval, database_url=None):
    if approval.get("approval_type") != "approved_for_single_dry_run_execution":
        return {
            "success": False,
            "status": "approval_not_for_single_dry_run_execution",
            "approval_type": approval.get("approval_type", ""),
        }, 409
    if approval.get("specialist_slug") != "sentinel":
        return {
            "success": False,
            "status": "single_shot_execution_is_sentinel_only",
            "specialist_slug": approval.get("specialist_slug", ""),
        }, 400

    dispatch_request_id = str(approval.get("dispatch_request_id") or "").strip()
    request_result, request_status = get_dispatch_request(dispatch_request_id, database_url=database_url)
    if request_status != 200:
        return request_result, request_status
    dispatch_request = request_result.get("dispatch_request", {})
    latest_decision = dispatch_request.get("latest_decision") or {}
    if dispatch_request.get("specialist_slug") != "sentinel":
        return {"success": False, "status": "dispatch_request_is_not_sentinel"}, 400
    if latest_decision.get("decision_type") != "approved_for_design_review":
        return {
            "success": False,
            "status": "dispatch_design_not_approved",
            "required_decision": "approved_for_design_review",
            "latest_decision": latest_decision,
        }, 409

    scope = approval.get("one_shot_scope") if isinstance(approval.get("one_shot_scope"), dict) else {}
    dry_run_request_id = str(scope.get("dry_run_request_id") or "").strip()[:100]
    if not dry_run_request_id:
        return {
            "success": False,
            "status": "dry_run_request_id_required_in_one_shot_scope",
            "required_scope_key": "dry_run_request_id",
        }, 409
    return {
        "success": True,
        "status": "ok",
        "dry_run_request_id": dry_run_request_id,
        "dispatch_request": dispatch_request,
    }, 200


def _call_sentinel_llm(*, approval, dispatch_request, dry_run_request_id):
    payload = _build_payload(approval=approval, dispatch_request=dispatch_request, dry_run_request_id=dry_run_request_id)
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
    return parse_sentinel_single_shot_response(body)


def _build_payload(*, approval, dispatch_request, dry_run_request_id):
    system = (
        "You are Sentinel, Oom Sakkie's safety reviewer. "
        "Perform one advisory review of the provided read-only context. "
        "Do not call tools, do not ask to dispatch another agent, do not write farm data, and do not claim any action was taken. "
        "Focus on guardrails, no-execution flags, owner approval boundaries, stale/evidence gaps, and whether the next gate is safe. "
        "Return only compact JSON: {\"result_text\":\"...\",\"findings\":[\"...\"]}."
    )
    user = {
        "approval": _safe_json_excerpt(approval, 1600),
        "dispatch_request": _safe_json_excerpt(dispatch_request, 2200),
        "dry_run_request_id": dry_run_request_id,
        "allowed_output": "advisory text only; append-only result record; no external transmission",
        "forbidden": [
            "tool calls",
            "farm-data writes",
            "public/customer output",
            "Telegram",
            "physical controls",
            "deploys",
            "further dispatch",
        ],
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


def _safe_json_excerpt(value, max_chars):
    try:
        return json.dumps(value or {}, default=str, ensure_ascii=True, sort_keys=True)[:max_chars]
    except (TypeError, ValueError):
        return json.dumps({"unavailable": True}, separators=(",", ":"))
