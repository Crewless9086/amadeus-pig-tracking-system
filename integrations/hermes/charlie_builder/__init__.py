"""Native Hermes registration for the bounded CHARLIE supervisor tools."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.hermes_supervisor import build_plugin_from_environment


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
    tools = build_plugin_from_environment()
    text = {"type": "string"}
    schemas = {
        "charlie_reconcile_mission": _schema(
            "charlie_reconcile_mission", "Reconcile one authenticated Slack owner instruction into canonical CHARLIE truth.",
            {"instruction": text, "event_id": text, "owner_user_id": text,
             "channel_id": text, "thread_ts": text},
            ["instruction", "event_id", "owner_user_id", "channel_id", "thread_ts"]),
        "charlie_dispatch_cursor": _schema(
            "charlie_dispatch_cursor", "Dispatch Cursor only from the mission's current canonical admission.",
            {"mission_id": text}, ["mission_id"]),
        "charlie_get_mission_status": _schema(
            "charlie_get_mission_status", "Read one canonical mission.", {"mission_id": text}, ["mission_id"]),
        "charlie_get_cursor_status": _schema(
            "charlie_get_cursor_status", "Poll the canonically linked Cursor Agent, PR, checks, and review.",
            {"mission_id": text}, ["mission_id"]),
        "charlie_supervise_once": _schema(
            "charlie_supervise_once", "Run one deterministic supervision poll and route SEND_BACK to the same Agent.",
            {"mission_id": text}, ["mission_id"]),
        "charlie_continue_cursor": _schema(
            "charlie_continue_cursor", "Continue the same idle Cursor Agent after an independent SEND_BACK.",
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
