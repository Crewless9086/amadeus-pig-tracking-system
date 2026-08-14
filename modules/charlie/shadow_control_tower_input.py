"""Authenticated observation-only input for the Phase A Shadow Control Tower."""
from __future__ import annotations

import hmac
import os
from typing import Mapping

from modules.charlie.environment import alias_environment
from modules.charlie.mission_store import get_mission, mission_runtime_eligible
from modules.charlie.private_policy import is_authenticated_private_action_context
from modules.charlie.shadow_control_tower import (
    ENABLE_ENV,
    compare_human_decision,
    propose_shadow_decision,
    record_shadow_proposal,
    shadow_enabled,
)

VERSION = "shadow_control_tower_private_input_v1"
ACTION = "observe_shadow_control_tower"


def shadow_input_runtime_state(*, environ=None):
    """Return non-secret kill-switch and authority state."""
    return {
        "success": True,
        "status": "shadow_control_tower_input_state",
        "schema_version": VERSION,
        "kill_switch": ENABLE_ENV,
        "enabled": shadow_enabled(environ),
        "human_control_tower_is_sole_dispatcher": True,
        **_zero_effects(),
    }


def handle_shadow_control_tower_input(
    payload,
    *,
    runtime_context=None,
    environ=None,
    database_url=None,
    connect_factory=None,
    mission_reader=None,
):
    """Accept one authenticated private CORE observation action.

    Authentication is supplied by the existing private CORE boundary. This
    function never accepts a credential value inside the action payload.
    """
    state = shadow_input_runtime_state(environ=environ)
    if not state["enabled"]:
        return {**state, "success": False, "status": "shadow_control_tower_disabled"}, 403
    context = runtime_context
    if not _authenticated(context, environ):
        return _failure("shadow_control_tower_private_authentication_required", 403)
    action = payload if isinstance(payload, Mapping) else {}
    if action.get("action") != ACTION:
        return _failure("shadow_control_tower_action_invalid", 400)
    record_type = str(action.get("record_type") or "").strip()
    transaction = action.get("transaction") if isinstance(action.get("transaction"), Mapping) else {}
    mission_id = str(transaction.get("existing_mission_id") or "").strip()
    bound_mission = str(context.existing_mission_id or "").strip()
    if not mission_id or not bound_mission or not hmac.compare_digest(mission_id, bound_mission):
        return _failure("shadow_control_tower_cross_mission_record_denied", 409)
    reader = mission_reader or get_mission
    loaded, loaded_status = reader(mission_id)
    mission = (loaded.get("mission") or {}) if isinstance(loaded, Mapping) else {}
    exact = mission.get("mission_id")
    if loaded_status >= 400 or not hmac.compare_digest(str(exact or ""), mission_id):
        return _failure("shadow_control_tower_existing_mission_not_found", 404)
    if not mission_runtime_eligible(mission):
        return _failure("shadow_control_tower_mission_not_runnable", 409)
    if record_type == "proposal":
        prepared = propose_shadow_decision(transaction, environ=environ)
        if not prepared.get("success"):
            return {**prepared, "input_schema_version": VERSION, **_zero_effects()}, 400
        result, status = record_shadow_proposal(
            transaction, environ=environ, database_url=database_url,
            connect_factory=connect_factory,
        )
        result = {**result, "proposal": prepared["proposal"]}
    elif record_type == "human_decision":
        proposal = action.get("proposal") if isinstance(action.get("proposal"), Mapping) else {}
        if (not hmac.compare_digest(str(proposal.get("existing_mission_id") or ""), mission_id)
                or not hmac.compare_digest(
                    str(proposal.get("feedback_transaction_id") or ""),
                    str(transaction.get("feedback_transaction_id") or ""))):
            return _failure("shadow_control_tower_cross_mission_record_denied", 409)
        decision = action.get("human_decision") if isinstance(action.get("human_decision"), Mapping) else {}
        result, status = compare_human_decision(
            proposal, decision, environ=environ, database_url=database_url,
            connect_factory=connect_factory,
        )
    else:
        return _failure("shadow_control_tower_record_type_invalid", 400)
    return {**result, "input_schema_version": VERSION, **_zero_effects()}, status


def _authenticated(context, environ):
    env = alias_environment(environ if isinstance(environ, Mapping) else os.environ)
    expected = str(env.get("CHARLIE_TELEGRAM_OWNER_USER_ID") or "").split(",")[0].strip()
    if not is_authenticated_private_action_context(context):
        return False
    principal = str(context.authenticated_principal_id or "").strip()
    return (
        str(context.authentication_scope or "") == "core_private_owner"
        and bool(expected)
        and hmac.compare_digest(principal, expected)
    )


def _failure(status, code):
    return {"success": False, "status": status, **_zero_effects()}, code


def _zero_effects():
    return {
        "dispatches": 0,
        "prompts_sent": 0,
        "terminals_started": 0,
        "processes_spawned": 0,
        "missions_created": 0,
        "merges": 0,
        "deployments": 0,
        "provider_messages": 0,
        "farm_writes": 0,
        "release_authority_granted": False,
    }
