"""Native Hermes registration for the bounded CHARLIE supervisor tools."""

from __future__ import annotations

import json
import atexit
import threading
from concurrent.futures import ThreadPoolExecutor
from .supervisor import build_plugin_from_environment


_BOUNDED_TOOLS = frozenset({
    "charlie_reconcile_mission", "charlie_dispatch_cursor",
    "charlie_get_mission_status", "charlie_get_cursor_status",
    "charlie_issue_admission", "charlie_supervise_once",
    "charlie_continue_cursor", "charlie_prepare_owner_decision",
})


def _source_value(source, name, default=""):
    return str(getattr(source, name, default) or default).strip()


def _is_slack(value):
    platform = getattr(value, "value", value)
    return str(platform or "").lower().split(".")[-1] == "slack"


def _bounded_reason(exc):
    reason = str(exc or "routing_unavailable").strip().lower()
    return reason if reason.replace("_", "").isalnum() else "routing_unavailable"


def _schema(name, description, properties, required):
    return {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": required,
        "additionalProperties": False,
    }}


def _json_handler(handler, adapt=lambda value: value):
    def invoke(params, **kwargs):
        del kwargs
        try:
            result = handler(adapt(dict(params or {})))
            return json.dumps(result, sort_keys=True, default=str)
        except Exception as exc:
            return json.dumps({"success": False, "status": str(exc)[:160]})
    return invoke


def register(ctx):
    # Registration establishes the bounded tool and hook safety surface.  Live
    # dependencies are checked by the individual operations that use them; a
    # transient provider outage must never remove the fail-closed Slack hooks.
    tools = build_plugin_from_environment(validate_live=False)
    supervisor = getattr(tools, "supervisor", None)
    if supervisor is not None:
        supervisor.native_llm = getattr(ctx, "llm", None)
    native_jobs = ThreadPoolExecutor(max_workers=1, thread_name_prefix="charlie-native")
    text = {"type": "string"}
    schemas = {
        "charlie_reconcile_mission": _schema(
            "charlie_reconcile_mission", "Reconcile one authenticated Slack owner instruction into canonical CHARLIE truth.",
            {"instruction": text, "event_id": text, "owner_user_id": text,
             "channel_id": text, "thread_ts": text},
            ["instruction", "event_id", "owner_user_id", "channel_id", "thread_ts"]),
        "charlie_dispatch_cursor": _schema(
            "charlie_dispatch_cursor", "Dispatch the one canonically selected bounded builder provider.",
            {"mission_id": text}, ["mission_id"]),
        "charlie_get_mission_status": _schema(
            "charlie_get_mission_status", "Read one canonical mission.", {"mission_id": text}, ["mission_id"]),
        "charlie_get_cursor_status": _schema(
            "charlie_get_cursor_status", "Poll the canonical execution, PR, checks, and independent review.",
            {"mission_id": text}, ["mission_id"]),
        "charlie_supervise_once": _schema(
            "charlie_supervise_once", "Run one deterministic supervision poll and route SEND_BACK to the same Agent.",
            {"mission_id": text}, ["mission_id"]),
        "charlie_continue_cursor": _schema(
            "charlie_continue_cursor", "Continue the same canonical execution workspace after SEND_BACK.",
            {"mission_id": text, "correction": text}, ["mission_id", "correction"]),
        "charlie_issue_admission": _schema(
            "charlie_issue_admission", "Request the protected issuer for the canonically bound exact PR head.",
            {"mission_id": text, "expected_head_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"}},
            ["mission_id", "expected_head_sha"]),
        "charlie_prepare_owner_decision": _schema(
            "charlie_prepare_owner_decision", "Prepare a notification only for a green independently approved exact head.",
            {"mission_id": text}, ["mission_id"]),
    }

    def event(value):
        return {"text": value["instruction"], "event_id": value["event_id"],
                "user": value["owner_user_id"], "channel": value["channel_id"],
                "thread_ts": value["thread_ts"]}

    canonical = tools["charlie_get_mission_status"]

    def mission(value):
        loaded = canonical({"mission_id": value["mission_id"]})
        row = dict(loaded.get("mission") or {})
        state = dict((row.get("metadata") or {}).get("external_supervisor_state") or {})
        return {**row, "dispatch": state}

    adapters = {
        "charlie_reconcile_mission": event,
        "charlie_dispatch_cursor": lambda value: {"mission_id": value["mission_id"]},
        "charlie_get_mission_status": lambda value: value,
        "charlie_get_cursor_status": mission,
        "charlie_supervise_once": mission,
        "charlie_continue_cursor": lambda value: {"mission": mission(value), "correction": value["correction"]},
        "charlie_issue_admission": lambda value: value,
        "charlie_prepare_owner_decision": mission,
    }
    for name, schema in schemas.items():
        ctx.register_tool(name=name, toolset="charlie_builder", schema=schema,
                          handler=_json_handler(tools[name], adapters[name]))

    slack_sessions = set()
    active_native = set()
    active_native_lock = threading.Lock()

    def run_native(mission_id, channel, thread_id):
        with active_native_lock:
            if mission_id in active_native:
                return
            active_native.add(mission_id)
        try:
            dispatch = getattr(supervisor, "dispatch_builder", supervisor.dispatch_cursor)
            result = dispatch({"mission_id": mission_id})
            if str((result or {}).get("status") or "") == "PACKAGER_CREDENTIAL_REQUIRED":
                raise RuntimeError("github_packager_token_required")
            for _ in range(2160):
                observed = supervisor.supervise_once({"mission_id": mission_id})
                status = str((observed or {}).get("execution_status") or (observed or {}).get("status") or "")
                if status in {"OWNER_DECISION_REQUIRED", "BLOCKED"}:
                    break
                threading.Event().wait(10)
        except Exception as exc:
            try:
                if supervisor and supervisor.slack_bot:
                    supervisor.slack_bot.post(
                        channel,
                        f"BLOCKED: CHARLIE native execution unavailable ({_bounded_reason(exc)}).",
                        thread_ts=thread_id,
                    )
            except Exception:
                pass
        finally:
            with active_native_lock:
                active_native.discard(mission_id)

    def recover_native(mission_id, channel, thread_id):
        # A replacement gateway may observe the dead process's still-valid
        # canonical lease. Retry from canonical truth until that bounded lease
        # expires; do not create a second execution or worktree.
        for _ in range(50):
            run_native(mission_id, channel, thread_id)
            try:
                remaining = {str(item.get("mission_id") or "")
                             for item in supervisor.canonical.resumable_native_executions()}
            except Exception:
                remaining = {mission_id}
            if mission_id not in remaining:
                return
            threading.Event().wait(15)

    def pre_gateway_dispatch(event, **kwargs):
        del kwargs
        source = getattr(event, "source", None)
        if not source or not _is_slack(getattr(source, "platform", "")):
            return {"action": "allow"}
        if getattr(event, "internal", False):
            return {"action": "skip", "reason": "internal_slack_event"}
        channel = _source_value(source, "chat_id")
        owner = _source_value(source, "user_id")
        message_id = str(getattr(event, "message_id", "") or "").strip()
        thread_id = _source_value(source, "thread_id") or message_id
        instruction = str(getattr(event, "text", "") or "").strip()
        if (supervisor is None or owner != supervisor.owner_slack_user_id
                or channel != supervisor.slack_command_channel_id):
            return {"action": "skip", "reason": "slack_ingress_not_authorized"}
        try:
            try:
                from gateway.session import build_session_key
                slack_sessions.add(str(build_session_key(source)))
            except Exception:
                pass
            reconciled = supervisor.reconcile_slack_event({
                "text": instruction, "event_id": message_id, "user": owner,
                "channel": channel, "thread_ts": thread_id,
            })
            mission_id = str(reconciled.get("mission_id") or "").strip()
            if not mission_id:
                raise RuntimeError("canonical_mission_unverified")
            supervisor.canonical.prepare_dispatch_authorization(mission_id)
            native_jobs.submit(run_native, mission_id, channel, thread_id)
        except Exception as exc:
            reason = _bounded_reason(exc)
            try:
                if supervisor and supervisor.slack_bot and channel and thread_id:
                    supervisor.slack_bot.post(
                        channel, f"BLOCKED: CHARLIE routing unavailable ({reason}).",
                        thread_ts=thread_id)
            except Exception:
                pass
            return {"action": "skip", "reason": reason}
        return {"action": "skip", "reason": "charlie_builder_dispatched"}

    def pre_tool_call(tool_name="", task_id="", **kwargs):
        session_id = str(kwargs.get("session_id") or "")
        task_id = str(task_id or "")
        slack_scoped = (session_id in slack_sessions or ":slack:" in session_id.lower()
                        or ":slack:" in task_id.lower())
        if slack_scoped and str(tool_name or "") not in _BOUNDED_TOOLS:
            return {"action": "block", "message": "Slack CHARLIE-BUILDER exposes only bounded supervisor tools."}
        return None

    ctx.register_hook("pre_gateway_dispatch", pre_gateway_dispatch)
    ctx.register_hook("pre_tool_call", pre_tool_call)
    # Canonical mission truth, not Slack replay, restarts unfinished work after
    # a gateway process replacement.
    try:
        for execution in supervisor.canonical.resumable_native_executions():
            mission_id = str(execution.get("mission_id") or "").strip()
            if mission_id:
                native_jobs.submit(
                    recover_native, mission_id,
                    str(execution.get("slack_channel_id") or ""),
                    str(execution.get("slack_thread_ts") or ""),
                )
    except Exception:
        pass
    atexit.register(native_jobs.shutdown, wait=False, cancel_futures=True)
