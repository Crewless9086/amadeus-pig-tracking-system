"""Owner-safe Telegram mission control for Supabase-backed CHARLIE CORE."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable, Mapping


CALLBACK_PREFIX = "cm:"
ACTIONABLE_STATUSES = ("in_progress", "release_in_progress", "pr_ready", "blocked", "release_approved", "approved", "new", "paused")


@dataclass(frozen=True)
class MissionControlResult:
    ok: bool
    action: str
    reason: str = ""
    mission_id: str = ""


def mission_token(mission_id: str) -> str:
    return hashlib.sha256(mission_id.encode("utf-8")).hexdigest()[:14]


def mission_callback(mission_id: str, action: str = "open", argument: str = "") -> str:
    parts = [CALLBACK_PREFIX.rstrip(":"), action, mission_token(mission_id)]
    if argument:
        parts.append(argument)
    return ":".join(parts)


def _metadata(mission: Mapping[str, Any]) -> dict[str, Any]:
    return dict(mission.get("metadata") or {})


def _review_packet(mission: Mapping[str, Any]) -> dict[str, Any]:
    packet = _metadata(mission).get("review_packet")
    return dict(packet) if isinstance(packet, dict) else {}


def _workflow_progress(mission: Mapping[str, Any]) -> tuple[int, str]:
    workflow = mission.get("agent_workflow") or _metadata(mission).get("agent_workflow") or []
    if not isinstance(workflow, list) or not workflow:
        return 0, "not started"
    completed = 0
    current = "pending"
    for row in workflow:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").lower()
        if status in {"complete", "completed", "passed", "done"}:
            completed += 1
        if status in {"active", "in_progress", "blocked"}:
            current = str(row.get("agent") or row.get("name") or current)
    return round((completed / max(1, len(workflow))) * 100), current


def mission_card_text(mission: Mapping[str, Any], runner: Mapping[str, Any] | None = None) -> str:
    mission_id = str(mission.get("mission_id") or "")
    status = str(mission.get("status") or "unknown")
    packet = _review_packet(mission)
    progress, current = _workflow_progress(mission)
    blocked_reason = str(packet.get("blocked_reason") or packet.get("reason") or "").strip()
    next_action = str(packet.get("recommended_next_action") or packet.get("next_action") or "").strip()
    runner = dict(runner or {})
    runner_line = str(runner.get("status") or "runner visibility unavailable")
    title = str(mission.get("title") or mission.get("raw_text") or mission_id or "Untitled mission").strip()
    lines = [
        "CHARLIE MISSION",
        title[:180],
        f"ID: {mission_id}",
        f"Status: {status}",
        f"Progress: {progress}%",
        f"Current stage: {current}",
        f"Runner: {runner_line}",
    ]
    if blocked_reason:
        lines.append(f"Blocked reason: {blocked_reason[:500]}")
    if next_action:
        lines.append(f"Next action: {next_action[:300]}")
    if status == "in_progress":
        lines.append("Observe only while the runner owns this mission.")
    return "\n".join(lines)


def mission_keyboard(mission: Mapping[str, Any]) -> dict[str, Any]:
    mission_id = str(mission.get("mission_id") or "")
    status = str(mission.get("status") or "").lower()
    actions: list[tuple[str, str, str]] = []
    if status == "new":
        actions = [("Approve", "approve", ""), ("Pause", "pause", ""), ("Reject", "reject", "")]
    elif status in {"approved", "in_progress", "release_in_progress", "release_approved"}:
        actions = [("Refresh", "open", "")]
    elif status == "blocked":
        actions = [("Send Back", "sendback", "builder"), ("Pause", "pause", ""), ("Reject", "reject", "")]
    elif status == "pr_ready":
        actions = [("Approve Final", "approvefinal", ""), ("Send Back", "sendback", "builder"), ("Pause", "pause", "")]
    elif status == "paused":
        actions = [("Approve / Resume", "resume", ""), ("Reject", "reject", "")]
    rows = [[{"text": label, "callback_data": mission_callback(mission_id, action, arg)}] for label, action, arg in actions]
    return {"inline_keyboard": rows}


def _load_candidates(list_loader: Callable[..., tuple[dict[str, Any], int]]) -> list[dict[str, Any]]:
    payload, status_code = list_loader(status="owner_queue", limit=100, compact=False)
    if status_code >= 400:
        return []
    return [dict(row) for row in (payload.get("missions") or []) if isinstance(row, Mapping)]


def resolve_mission(token: str, list_loader: Callable[..., tuple[dict[str, Any], int]]) -> dict[str, Any] | None:
    matches = [mission for mission in _load_candidates(list_loader) if mission_token(str(mission.get("mission_id") or "")) == token]
    return matches[0] if len(matches) == 1 else None


def handle_callback(
    data: str,
    *,
    list_loader: Callable[..., tuple[dict[str, Any], int]],
    get_loader: Callable[..., tuple[dict[str, Any], int]],
    status_updater: Callable[..., tuple[dict[str, Any], int]],
    review_updater: Callable[..., tuple[dict[str, Any], int]],
) -> tuple[MissionControlResult, dict[str, Any] | None]:
    parts = data.split(":")
    if len(parts) < 3 or parts[0] != CALLBACK_PREFIX.rstrip(":"):
        return MissionControlResult(False, "invalid_callback", "invalid_callback"), None
    action, token = parts[1], parts[2]
    candidate = resolve_mission(token, list_loader)
    if not candidate:
        return MissionControlResult(False, action, "mission_not_found_or_ambiguous"), None
    mission_id = str(candidate.get("mission_id") or "")
    loaded, load_code = get_loader(mission_id)
    if load_code >= 400:
        return MissionControlResult(False, action, str(loaded.get("status") or "mission_load_failed"), mission_id), None
    mission = dict(loaded.get("mission") or {})
    status = str(mission.get("status") or "").lower()

    if action == "open":
        return MissionControlResult(True, "mission_opened", mission_id=mission_id), mission

    status_actions = {
        "approve": ("new", "approved", "owner_approved"),
        "resume": ("paused", "approved", "owner_resumed"),
        "pause": (status, "paused", "owner_paused"),
        "reject": (status, "rejected", "owner_rejected"),
    }
    if action in status_actions:
        expected, target, decision = status_actions[action]
        if action in {"pause", "reject"} and status not in {"new", "blocked", "pr_ready", "paused"}:
            return MissionControlResult(False, action, f"action_not_allowed_from_{status}", mission_id), mission
        payload, code = status_updater(
            mission_id,
            target,
            owner_decision=decision,
            event_type="approval_decision",
            notes=f"Telegram owner action: {action}.",
            expected_status=expected,
            metadata={"source": "charlie_telegram_mission_control"},
        )
    elif action == "sendback":
        if status not in {"blocked", "pr_ready"}:
            return MissionControlResult(False, action, f"action_not_allowed_from_{status}", mission_id), mission
        stage = parts[3] if len(parts) > 3 else "builder"
        payload, code = review_updater(mission_id, "send_back", comments="Returned from Telegram owner review.", target_stage=stage)
    elif action == "approvefinal":
        if status != "pr_ready":
            return MissionControlResult(False, action, f"action_not_allowed_from_{status}", mission_id), mission
        payload, code = review_updater(mission_id, "approve_final_release", comments="Approved from Telegram owner review.")
    else:
        return MissionControlResult(False, action, "unknown_action", mission_id), mission

    if code >= 400:
        return MissionControlResult(False, action, str(payload.get("status") or "mission_update_failed"), mission_id), mission
    refreshed, refresh_code = get_loader(mission_id)
    refreshed_mission = dict(refreshed.get("mission") or {}) if refresh_code < 400 else mission
    return MissionControlResult(True, action, mission_id=mission_id), refreshed_mission
