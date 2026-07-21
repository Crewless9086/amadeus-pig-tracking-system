import hmac
import json
import os
import re
import time
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from modules.charlie.mission_store import (
    get_mission,
    list_owner_work_missions,
    list_missions,
    mission_status_summary,
    normalize_approval_level,
    record_mission,
    update_mission_status,
    update_mission_workflow_step,
)
from modules.charlie.runner_control import runner_status as local_runner_status
from modules.charlie.environment import alias_environment


TRUTHY = {"1", "true", "yes", "on"}
ENABLED_ENV = "CORE_RELAY_ENABLED"
BOT_TOKEN_ENV = "CORE_RELAY_BOT_TOKEN"
WEBHOOK_SECRET_ENV = "CORE_RELAY_WEBHOOK_SECRET"
ALLOWED_USER_IDS_ENV = "CORE_RELAY_ALLOWED_USER_IDS"
CODEX_CHAT_WRITE_ENABLED_ENV = "CORE_RELAY_CODEX_CHAT_WRITE_ENABLED"
MISSION_STORE_ENABLED_ENV = "CORE_RELAY_MISSION_STORE_ENABLED"
REPO_ROOT_ENV = "CORE_RELAY_REPO_ROOT"
MIN_SECRET_CHARS = 32
MAX_TELEGRAM_TEXT_CHARS = 3000
MAX_REPLY_CHARS = 3900
AUTH_FAILURE_LIMIT = 8
AUTH_FAILURE_WINDOW_SECONDS = 60
AUTH_LOCKOUT_SECONDS = 300
_AUTH_FAILURE_TIMES = []
_AUTH_LOCKED_UNTIL = 0.0


def build_relay_policy(environ=None):
    source = alias_environment(environ if environ is not None else os.environ)
    explicitly_enabled = _truthy(source.get(ENABLED_ENV))
    bot_token = str(source.get(BOT_TOKEN_ENV, "") or "").strip()
    webhook_secret = str(source.get(WEBHOOK_SECRET_ENV, "") or "").strip()
    allowed_ids = _allowed_user_ids(source)
    auth_locked = _auth_locked()
    repo_write_enabled = _truthy(source.get(CODEX_CHAT_WRITE_ENABLED_ENV))
    mission_store_enabled = _truthy(source.get(MISSION_STORE_ENABLED_ENV, "1"))
    ready = (
        explicitly_enabled
        and bool(bot_token)
        and len(webhook_secret) >= MIN_SECRET_CHARS
        and bool(allowed_ids)
        and not auth_locked
    )
    return {
        "enabled": ready,
        "explicitly_enabled": explicitly_enabled,
        "configured": bool(bot_token),
        "webhook_secret_configured": bool(webhook_secret),
        "webhook_secret_meets_minimum_entropy": len(webhook_secret) >= MIN_SECRET_CHARS,
        "minimum_secret_chars": MIN_SECRET_CHARS,
        "mode": "owner_only_charlie_build_relay",
        "route": "POST /api/charlie/build-relay/telegram/webhook",
        "auth": "x_telegram_bot_api_secret_token",
        "allowed_user_ids_required": True,
        "allowed_user_ids_configured": bool(allowed_ids),
        "allowed_user_ids_count": len(allowed_ids),
        "repo_file_write_enabled": repo_write_enabled,
        "repo_file_write_scope": ["planning/CODEX_CHAT.md"] if repo_write_enabled else [],
        "mission_store_enabled": mission_store_enabled,
        "auth_rate_limit": {
            "enabled": True,
            "failure_limit": AUTH_FAILURE_LIMIT,
            "window_seconds": AUTH_FAILURE_WINDOW_SECONDS,
            "lockout_seconds": AUTH_LOCKOUT_SECONDS,
            "locked": auth_locked,
        },
        "sends_telegram": ready,
        "can_trigger_codex_runtime": False,
        "can_commit": False,
        "can_merge": False,
        "can_deploy": False,
        "can_run_shell": False,
        "can_write_production_data": False,
        "customer_public_output_enabled": False,
        "payments_enabled": False,
        "reservations_enabled": False,
        "lifecycle_writes_enabled": False,
    }


def handle_charlie_telegram_webhook(payload, headers=None, environ=None):
    source = alias_environment(environ if environ is not None else os.environ)
    policy = build_relay_policy(environ=source)
    if not policy["explicitly_enabled"]:
        return _result(False, "charlie_build_relay_disabled", policy, 503)
    if not policy["configured"]:
        return _result(False, "charlie_build_relay_bot_token_not_configured", policy, 503)
    if not policy["webhook_secret_configured"]:
        return _result(False, "charlie_build_relay_webhook_secret_not_configured", policy, 503)
    if not policy["webhook_secret_meets_minimum_entropy"]:
        return _result(False, "charlie_build_relay_webhook_secret_too_short", policy, 503)
    if not policy["allowed_user_ids_configured"]:
        return _result(False, "charlie_build_relay_allowed_user_ids_required", policy, 503)
    if policy["auth_rate_limit"]["locked"]:
        return _result(False, "charlie_build_relay_auth_rate_limited", policy, 429)
    if not _secret_matches(headers or {}, source):
        _record_auth_failure()
        return _result(False, "charlie_build_relay_auth_denied", policy, 403)

    parsed = parse_telegram_payload(payload)
    callback_data = str(((payload or {}).get("callback_query") or {}).get("data") or "")
    if callback_data.startswith("cm:"):
        return handle_mission_control_callback_webhook(payload, policy=policy, environ=source)
    if not parsed["text"]:
        return _result(False, "charlie_build_relay_text_required", policy, 400)
    if parsed["telegram_user_id"] not in _allowed_user_ids(source):
        body, status_code = _result(False, "charlie_build_relay_user_not_allowed", policy, 403)
        body["telegram_user_id"] = parsed["telegram_user_id"]
        return body, status_code

    action_source = dict(source)
    action_source["_charlie_telegram_user_id"] = parsed["telegram_user_id"]
    action_source["_charlie_telegram_chat_id"] = parsed["telegram_chat_id"]
    action = build_relay_action(parsed["text"], environ=action_source)
    send_result, send_status = send_charlie_telegram_message(
        chat_id=parsed["telegram_chat_id"],
        text=action["telegram_text"],
        reply_markup=action.get("reply_markup"),
        environ=source,
    )
    body, _ = _result(send_result.get("success") is True, send_result.get("status", "telegram_send_failed"), policy, send_status)
    body.update({
        "telegram_user_id": parsed["telegram_user_id"],
        "telegram_chat_id": parsed["telegram_chat_id"],
        "command": action["command"],
        "action": action,
        "telegram_send": send_result,
    })
    return body, send_status


def handle_mission_control_callback_webhook(payload, *, policy=None, environ=None, callback_handler=None, update_claimer=None, update_completer=None):
    """Run an authenticated ``cm:`` callback once and retain its terminal outcome.

    The caller has already checked the webhook secret.  Claiming happens before
    owner validation so authenticated refused callbacks are auditable, while an
    unauthenticated request never reaches this function or creates durable data.
    """
    source = alias_environment(environ if environ is not None else os.environ)
    policy = policy or build_relay_policy(environ=source)
    parsed = parse_telegram_payload(payload)
    callback = (payload or {}).get("callback_query") or {}
    update_id = str((payload or {}).get("update_id") or "")
    callback_id = str(callback.get("id") or "")
    if not update_id:
        return _result(False, "charlie_mission_callback_update_id_required", policy, 400)

    if update_claimer is None or update_completer is None:
        from modules.charlie.private_store import claim_update, complete_update
        update_claimer = update_claimer or claim_update
        update_completer = update_completer or complete_update
    claim, claim_status = update_claimer(update_id, callback_id)
    if claim_status >= 400:
        return _result(False, "charlie_mission_callback_claim_failed", policy, claim_status)
    if not claim.get("created"):
        body, _ = _result(True, "charlie_mission_callback_duplicate_ignored", policy, 200)
        body["update_key"] = claim.get("update_key", "")
        return body, 200

    update_key = claim["update_key"]

    def complete_terminal_outcome(status, outcome):
        """Complete an already-claimed update exactly once.

        The mission action can have committed before its audit completion is
        attempted.  A completion failure must therefore be surfaced as a
        recoverable delivery failure, never retried from an exception handler
        (which used to mask the original failure and escape the webhook).
        """
        try:
            completion, completion_status = update_completer(update_key, status=status, result=outcome)
            if not isinstance(completion, dict):
                raise TypeError("update_completer_result_invalid")
            if completion_status >= 400 or not completion.get("success"):
                return False, {
                    "status": str(completion.get("status") or "update_complete_failed")[:80],
                    "error_type": str(completion.get("error_type") or "")[:80],
                }
        except Exception as exc:
            return False, {"status": "update_complete_failed", "error_type": exc.__class__.__name__}
        return True, {}

    def completion_failure_body(outcome, completion_failure):
        body, _ = _result(False, "charlie_mission_callback_completion_failed", policy, 503)
        body["callback"] = outcome
        body["completion"] = completion_failure
        body["update_key"] = update_key
        return body, 503

    if parsed["telegram_user_id"] not in _allowed_user_ids(source):
        outcome = {"status": "unauthorized_user"}
        completed, completion_failure = complete_terminal_outcome("ignored", outcome)
        if not completed:
            return completion_failure_body(outcome, completion_failure)
        body, _ = _result(False, "charlie_build_relay_user_not_allowed", policy, 403)
        body["telegram_user_id"] = parsed["telegram_user_id"]
        return body, 403

    try:
        if callback_handler is None:
            from scripts.build_relay_telegram_buttons import handle_update
            callback_handler = handle_update
        result = callback_handler(payload, environ=source)
        outcome = {
            "status": str(getattr(result, "action", "mission_callback_handled")),
            "reason": str(getattr(result, "reason", ""))[:240],
            "mission_id": str(getattr(result, "selected_title", ""))[:90],
        }
        terminal_status = "processed" if bool(getattr(result, "ok", False)) else "refused"
        completed, completion_failure = complete_terminal_outcome(terminal_status, outcome)
        if not completed:
            return completion_failure_body(outcome, completion_failure)
        body, _ = _result(bool(getattr(result, "ok", False)), "charlie_mission_callback_handled", policy, 200)
        body["callback"] = outcome
        return body, 200
    except Exception as exc:
        outcome = {"status": "mission_callback_failed", "error_type": exc.__class__.__name__}
        completed, completion_failure = complete_terminal_outcome("failed", outcome)
        if not completed:
            return completion_failure_body(outcome, completion_failure)
        body, _ = _result(False, "charlie_mission_callback_failed", policy, 503)
        body["callback"] = outcome
        return body, 503


def build_relay_action(text, environ=None):
    source = alias_environment(environ if environ is not None else os.environ)
    cleaned = str(text or "").strip()[:MAX_TELEGRAM_TEXT_CHARS]
    lower = cleaned.lower()
    repo_root = _repo_root(source)
    if lower in {"/start", "start", "/help", "help", "charlie", "/charlie"}:
        return _help_action()
    if lower.startswith("/status "):
        return _mission_status_action(cleaned[len("/status"):].strip())
    if lower.startswith("status:"):
        return _mission_status_action(cleaned.split(":", 1)[1].strip())
    if lower in {"/status", "status", "what is happening", "where are we"}:
        return _status_action(repo_root)
    if lower in {"/next", "next", "what next", "what is next", "next steps"}:
        return _next_action(repo_root)
    if lower in {"/missions", "missions", "mission queue"}:
        return _missions_action(source)
    if lower in {"/review", "review", "ready for review"}:
        return _review_action()
    if lower.startswith("/done"):
        return _mission_decision_action(cleaned[len("/done"):].strip(), "done", "done")
    if lower.startswith("done:"):
        return _mission_decision_action(cleaned.split(":", 1)[1].strip(), "done", "done")
    if lower.startswith("/workflow"):
        return _workflow_action(cleaned[len("/workflow"):].strip())
    if lower.startswith("/approve"):
        return _mission_decision_action(cleaned[len("/approve"):].strip(), "approved", "approve")
    if lower.startswith("approve:"):
        return _mission_decision_action(cleaned.split(":", 1)[1].strip(), "approved", "approve")
    if lower.startswith("/pause"):
        return _mission_decision_action(cleaned[len("/pause"):].strip(), "paused", "pause")
    if lower.startswith("pause:"):
        return _mission_decision_action(cleaned.split(":", 1)[1].strip(), "paused", "pause")
    if lower.startswith("/reject"):
        return _mission_decision_action(cleaned[len("/reject"):].strip(), "rejected", "reject")
    if lower.startswith("reject:"):
        return _mission_decision_action(cleaned.split(":", 1)[1].strip(), "rejected", "reject")
    if lower.startswith("/debrief"):
        return _mission_detail_action(cleaned[len("/debrief"):].strip(), command="debrief")
    if lower.startswith("/mission"):
        mission_text = cleaned[len("/mission"):].strip()
        if _looks_like_mission_id(mission_text):
            return _mission_detail_action(mission_text, command="mission_detail")
        return _mission_action(mission_text, source, repo_root, "mission", {})
    if lower.startswith("mission:"):
        return _mission_action(cleaned.split(":", 1)[1].strip(), source, repo_root, "mission", {})
    if lower.startswith("/select"):
        return _select_next_action(cleaned[len("/select"):].strip(), source, repo_root)
    if lower.startswith("select:"):
        return _select_next_action(cleaned.split(":", 1)[1].strip(), source, repo_root)
    return _mission_action(cleaned, source, repo_root, "free_text_mission", {})


def parse_telegram_payload(payload):
    payload = payload or {}
    message = payload.get("message") or payload.get("edited_message") or {}
    callback = payload.get("callback_query") or {}
    callback_message = callback.get("message") or {}
    from_user = callback.get("from") or message.get("from") or payload.get("from") or {}
    chat = message.get("chat") or callback_message.get("chat") or payload.get("chat") or {}
    text = callback.get("data") or payload.get("text") or message.get("text") or message.get("caption") or ""
    return {
        "text": str(text or "").strip()[:MAX_TELEGRAM_TEXT_CHARS],
        "telegram_user_id": str(payload.get("telegram_user_id") or payload.get("from_user_id") or from_user.get("id") or "").strip()[:80],
        "telegram_chat_id": str(payload.get("telegram_chat_id") or payload.get("chat_id") or chat.get("id") or "").strip()[:80],
    }


def send_charlie_telegram_message(chat_id, text, reply_markup=None, environ=None):
    source = alias_environment(environ if environ is not None else os.environ)
    policy = build_relay_policy(environ=source)
    if not policy["enabled"]:
        return _send_result(False, "charlie_build_relay_not_ready", policy), 503
    chat_id = str(chat_id or "").strip()
    text = str(text or "").strip()[:MAX_REPLY_CHARS]
    if not chat_id:
        return _send_result(False, "telegram_chat_id_required", policy), 400
    if not text:
        return _send_result(False, "telegram_reply_text_required", policy), 400

    body = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        body["reply_markup"] = reply_markup
    request = urllib_request.Request(
        f"https://api.telegram.org/bot{str(source.get(BOT_TOKEN_ENV, '') or '').strip()}/sendMessage",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=15) as response:
            response_body = json.loads(response.read().decode("utf-8") or "{}")
            status_code = response.status
    except urllib_error.HTTPError as error:
        try:
            response_body = json.loads(error.read().decode("utf-8") or "{}")
        except ValueError:
            response_body = {}
        result = _send_result(False, "telegram_api_rejected", policy)
        result["telegram_status_code"] = error.code
        result["telegram_ok"] = response_body.get("ok") is True
        result["telegram_error_code"] = response_body.get("error_code")
        result["telegram_description"] = str(response_body.get("description") or "")[:300]
        return result, 502
    except OSError:
        return _send_result(False, "telegram_api_unreachable", policy), 502

    result = _send_result(status_code == 200 and response_body.get("ok") is True, "telegram_sent", policy)
    result["telegram_status_code"] = status_code
    result["telegram_ok"] = response_body.get("ok") is True
    result["telegram_message_id"] = ((response_body.get("result") or {}).get("message_id"))
    return result, 200 if result["success"] else 502


def _help_action():
    return {
        "command": "help",
        "telegram_text": (
            "CHARLIE Build Relay is online as an owner-only command layer.\n\n"
            "Commands:\n"
            "/status - quick CHARLIE Mission Control overview\n"
            "/status <id> - quick live status for one mission\n"
            "/next - current CHARLIE handoff plus missions waiting approval\n"
            "/missions - recent durable mission queue records\n"
            "/mission <id> - show one mission record\n"
            "/mission <idea> - prepare a mission intake\n"
            "/select 1 - turn a listed NEXT_STEPS option into a mission intake\n\n"
            "/review - missions ready for owner review\n"
            "/workflow <id> tester complete - update planner/architect/builder/tester/reviewer handoff\n"
            "/approve <id> level3 - approve build/test/PR handoff\n"
            "/approve <id> level4 - approve merge/release handoff after PR verification\n"
            "/done <id>, /pause <id>, /reject <id> - record owner decision only\n\n"
            "Safety: this relay cannot run shell commands, commit, merge, deploy, send customers, post publicly, take payments, reserve stock, or write production data."
        ),
        "reply_markup": _main_keyboard(),
        "writes_repo_file": False,
    }


def _status_action(repo_root):
    runner = local_runner_status()
    summary, _ = mission_status_summary()
    active = _first_available_mission(("in_progress", "release_in_progress"))
    review_ready = _first_available_mission(("pr_ready", "blocked"))
    approved = _first_available_mission(("approved",))
    release_approved = _first_available_mission(("release_approved",))
    new_missions = _mission_list_for_status("new", limit=3, owner_work_only=True)
    keyboard = []
    lines = [
        "CHARLIE Mission Control",
        "",
        f"Local runner: {_runner_label(runner)}",
    ]
    if runner.get("last_seen"):
        lines.append(f"Runner last seen: {runner.get('last_seen')}")
    if summary.get("success"):
        counts = summary.get("counts") or {}
        lines.append(f"Queue: {_status_counts_line(counts)}")
    else:
        lines.append(f"Queue: {summary.get('status', 'unavailable')}")

    if active:
        mission = active["mission"]
        lines.extend(["", f"Active: {_mission_title_line(mission)}", f"Status: {mission.get('status')}"])
        keyboard.append([{"text": "Active Status", "callback_data": f"status:{mission.get('mission_id')}"}])
    if review_ready:
        mission = review_ready["mission"]
        lines.extend(["", f"Owner review: {_mission_title_line(mission)}", f"Status: {mission.get('status')}"])
        keyboard.append([{"text": "Review Status", "callback_data": f"status:{mission.get('mission_id')}"}])
    if approved:
        mission = approved["mission"]
        lines.extend(["", f"Waiting pickup: {_mission_title_line(mission)}", f"Approval: {mission.get('approval_level') or 'not set'}"])
        keyboard.append([{"text": "Pickup Status", "callback_data": f"status:{mission.get('mission_id')}"}])
    if release_approved:
        mission = release_approved["mission"]
        lines.extend(["", f"Release approved: {_mission_title_line(mission)}", "Next: local release bridge verifies and closes it."])
        keyboard.append([{"text": "Release Status", "callback_data": f"status:{mission.get('mission_id')}"}])
    if new_missions:
        lines.extend(["", f"Needs approval: {len(new_missions)} recent new mission(s)."])
        for mission in new_missions[:2]:
            keyboard.append([
                {"text": f"Status {str(mission.get('mission_id') or '')[-4:]}", "callback_data": f"status:{mission.get('mission_id')}"},
                {"text": "Approve L3", "callback_data": f"approve:{mission.get('mission_id')} level3"},
            ])
    if not any([active, review_ready, approved, release_approved, new_missions]):
        lines.extend(["", "No active, review-ready, approved, release-approved, or new missions are visible right now."])
    lines.extend(["", "Telegram records decisions only. Builds still run through the local Codex/Cursor runner boundary."])
    return {
        "command": "status",
        "telegram_text": "\n".join(lines)[:MAX_REPLY_CHARS],
        "reply_markup": {"inline_keyboard": keyboard[:6]} if keyboard else _main_keyboard(),
        "local_runner": runner,
        "mission_store": {"summary_status": summary.get("status")},
        "writes_repo_file": False,
    }


def _mission_status_action(mission_id):
    mission_id = _clean_source_value(mission_id)
    if not mission_id:
        return {
            "command": "mission_status",
            "telegram_text": "Send /status <mission id> or tap a mission Status button.",
            "reply_markup": _main_keyboard(),
            "writes_repo_file": False,
        }
    result, _ = get_mission(mission_id)
    if not result.get("success"):
        return {
            "command": "mission_status",
            "telegram_text": f"Mission status lookup failed: {result.get('status', 'unavailable')}.",
            "mission_store": result,
            "reply_markup": _main_keyboard(),
            "writes_repo_file": False,
        }
    mission = result.get("mission") or {}
    return {
        "command": "mission_status",
        "telegram_text": _mission_status_text(mission),
        "mission": mission,
        "mission_store": result,
        "reply_markup": _mission_decision_keyboard(mission.get("mission_id", "")),
        "writes_repo_file": False,
    }


def _next_action(repo_root):
    queue_action = _mission_queue_next_action()
    if queue_action:
        return queue_action

    items = _next_step_options(repo_root)
    lines = ["Next mission options:"]
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item}")
    lines.append("\nReply /select 1, /select 2, or send /mission <your idea>.")
    return {
        "command": "next",
        "telegram_text": "\n".join(lines)[:MAX_REPLY_CHARS],
        "reply_markup": {
            "inline_keyboard": [[
                {"text": f"Select {idx + 1}", "callback_data": f"select:{idx + 1}"}
                for idx in range(min(len(items), 3))
            ]]
        } if items else _main_keyboard(),
        "options": items,
        "writes_repo_file": False,
    }


def _mission_queue_next_action():
    active = _first_available_mission(("in_progress", "release_in_progress"))
    review_ready = _first_available_mission(("pr_ready", "blocked"))
    approved = _first_available_mission(("approved",))
    release_approved = _first_available_mission(("release_approved",))
    new_missions = _mission_list_for_status("new", limit=3, owner_work_only=True)

    if not active and not review_ready and not approved and not release_approved and new_missions is None:
        return None
    if not active and not review_ready and not approved and not release_approved and not new_missions:
        return None

    lines = ["CHARLIE next"]
    keyboard = []
    if active:
        mission = active["mission"]
        status = str(mission.get("status") or "").strip()
        label = "PR ready for owner review" if status == "pr_ready" else "Release in progress" if status == "release_in_progress" else "In progress"
        lines.extend([
            "",
            f"{label}: {_mission_title_line(mission)}",
            f"Status: {status}",
            f"Approval: {mission.get('approval_level') or 'not set'}",
            _active_next_instruction(status),
        ])
        keyboard.append([
            {"text": "Mission Status", "callback_data": f"status:{mission.get('mission_id')}"},
            {"text": "View", "callback_data": f"/mission {mission.get('mission_id')}"},
        ])

    if review_ready:
        mission = review_ready["mission"]
        lines.extend([
            "",
            f"Waiting owner review: {_mission_title_line(mission)}",
            f"Status: {mission.get('status')}",
            "This review backlog does not block the local runner from picking the next approved mission.",
        ])
        keyboard.append([
            {"text": "Mission Status", "callback_data": f"status:{mission.get('mission_id')}"},
            {"text": "View", "callback_data": f"/mission {mission.get('mission_id')}"},
        ])

    if approved:
        mission = approved["mission"]
        lines.extend([
            "",
            f"Approved waiting for Codex runner: {_mission_title_line(mission)}",
            f"Approval: {mission.get('approval_level') or 'not set'}",
            "If the local runner is active, it will pick this up when no mission is in progress or release-in-progress.",
        ])
        keyboard.append([
            {"text": "Mission Status", "callback_data": f"status:{mission.get('mission_id')}"},
            {"text": "View", "callback_data": f"/mission {mission.get('mission_id')}"},
        ])

    if release_approved:
        mission = release_approved["mission"]
        lines.extend([
            "",
            f"Final release approved: {_mission_title_line(mission)}",
            f"Approval: {mission.get('approval_level') or 'LEVEL 4'}",
            "Next: local Codex release bridge must verify, merge/deploy if applicable, and mark done.",
        ])
        keyboard.append([
            {"text": "Mission Status", "callback_data": f"status:{mission.get('mission_id')}"},
            {"text": "View", "callback_data": f"/mission {mission.get('mission_id')}"},
        ])

    if new_missions:
        lines.append("")
        lines.append("Missions waiting for approval:")
        for index, mission in enumerate(new_missions, start=1):
            lines.append(f"{index}. {_mission_title_line(mission)}")
            if index <= 2:
                keyboard.append([
                    {"text": f"Status {index}", "callback_data": f"status:{mission.get('mission_id')}"},
                    {"text": f"Approve L3 {index}", "callback_data": f"approve:{mission.get('mission_id')} level3"},
                ])
        lines.append("Use /approve <id> level1, level3, or level4 to approve a mission.")

    lines.extend([
        "",
        "Telegram records owner decisions only. Build execution still happens through the local Codex/Cursor runner boundary.",
    ])
    return {
        "command": "next",
        "telegram_text": "\n".join(lines)[:MAX_REPLY_CHARS],
        "reply_markup": {"inline_keyboard": keyboard[:6]} if keyboard else _main_keyboard(),
        "mission_queue": {
            "active_status": active.get("status") if active else "",
            "approved_status": approved.get("status") if approved else "",
            "new_count": len(new_missions or []),
        },
        "writes_repo_file": False,
    }


def _first_available_mission(statuses):
    for status in statuses:
        missions = _mission_list_for_status(status, limit=1, owner_work_only=True)
        if missions is None:
            return None
        if missions:
            return {"status": status, "mission": missions[0]}
    return None


def _mission_list_for_status(status, limit=3, owner_work_only=False):
    if owner_work_only:
        result, status_code = list_owner_work_missions(status, limit=limit)
    else:
        result, status_code = list_missions(status=status, limit=limit)
    if status_code >= 400:
        return None
    return (result.get("missions") or [])[:limit]


def _mission_title_line(mission):
    mission_id = str(mission.get("mission_id") or "")
    short_id = mission_id[-8:] if mission_id else "no-id"
    title = mission.get("title") or mission.get("raw_text") or "Untitled mission"
    urgency = mission.get("urgency") or "P2"
    return f"{short_id} | {urgency} | {title}"


def _runner_label(runner):
    if runner.get("active"):
        return f"active ({runner.get('status') or 'runner_active'})"
    return runner.get("status") or "not active"


def _status_counts_line(counts):
    priority = ("in_progress", "pr_ready", "blocked", "approved", "release_approved", "new")
    parts = [f"{key}={counts.get(key, 0)}" for key in priority if counts.get(key)]
    return ", ".join(parts) if parts else "no active queue counts"


def _active_next_instruction(status):
    if status == "pr_ready":
        return "Next: owner review in CHARLIE dashboard. Final approval records release_approved for the local release watcher."
    if status == "release_in_progress":
        return "Next: local Codex release bridge must finish release verification and mark done."
    return "Next: let Codex finish and debrief this mission before picking up another one."


def _select_next_action(choice, source, repo_root):
    items = _next_step_options(repo_root)
    try:
        index = int(str(choice or "").strip()) - 1
    except ValueError:
        index = -1
    if index < 0 or index >= len(items):
        return {
            "command": "select",
            "telegram_text": "I could not match that option. Use /next, then /select 1, /select 2, or /select 3.",
            "reply_markup": _main_keyboard(),
            "writes_repo_file": False,
        }
    return _mission_action(items[index], source, repo_root, "select_next", {"selected_next_step": items[index]})


def _missions_action(source):
    summary, _ = mission_status_summary()
    loaded, _ = list_missions(limit=20)
    lines = ["CHARLIE mission queue"]
    if summary.get("success"):
        counts = summary.get("counts") or {}
        lines.append("Counts: " + (", ".join(f"{key}={value}" for key, value in counts.items()) or "none"))
    else:
        lines.append(f"Queue status: {summary.get('status', 'unavailable')}")
    missions = [
        mission
        for mission in (loaded.get("missions") or [])
        if mission.get("queue_class", "owner_work") == "owner_work"
    ][:5]
    for index, mission in enumerate(missions, start=1):
        mission_id = str(mission.get("mission_id") or "")
        short_id = mission_id[-8:] if mission_id else "no-id"
        lines.append(f"{index}. {short_id} | {mission.get('status')} | {mission.get('urgency')} | {mission.get('title')}")
    if not missions:
        lines.append("No stored missions returned.")
    return {
        "command": "missions",
        "telegram_text": "\n".join(lines)[:MAX_REPLY_CHARS],
        "reply_markup": _main_keyboard(),
        "mission_store": {
            "summary_status": summary.get("status"),
            "list_status": loaded.get("status"),
            "configured": summary.get("configured") or loaded.get("configured"),
        },
        "writes_repo_file": False,
    }


def _review_action():
    ready = []
    for status in ("pr_ready", "blocked"):
        missions = _mission_list_for_status(status, limit=5, owner_work_only=True)
        if missions is not None:
            ready.extend(missions)
    lines = ["CHARLIE review queue"]
    keyboard = []
    if not ready:
        lines.append("No PR-ready or blocked missions are waiting for owner review.")
    for index, mission in enumerate(ready[:6], start=1):
        lines.append(f"{index}. {_mission_title_line(mission)} | {mission.get('status')}")
        keyboard.append([
            {"text": f"Status {index}", "callback_data": f"status:{mission.get('mission_id')}"},
            {"text": f"View {index}", "callback_data": f"/mission {mission.get('mission_id')}"},
        ])
    lines.append("\nUse /mission <id> for detail or /approve <id> level4 after PR verification.")
    return {
        "command": "review",
        "telegram_text": "\n".join(lines)[:MAX_REPLY_CHARS],
        "reply_markup": {"inline_keyboard": keyboard[:6]} if keyboard else _main_keyboard(),
        "writes_repo_file": False,
    }


def _mission_detail_action(mission_id, command="mission_detail"):
    mission_id = _clean_source_value(mission_id)
    if not mission_id:
        return {
            "command": command,
            "telegram_text": "Send /mission <mission id> or /debrief <mission id>.",
            "reply_markup": _main_keyboard(),
            "writes_repo_file": False,
        }
    result, _ = get_mission(mission_id)
    if not result.get("success"):
        return {
            "command": command,
            "telegram_text": f"Mission lookup failed: {result.get('status', 'unavailable')}.",
            "mission_store": result,
            "reply_markup": _main_keyboard(),
            "writes_repo_file": False,
        }
    mission = result.get("mission") or {}
    return {
        "command": command,
        "telegram_text": _mission_detail_text(mission),
        "mission": mission,
        "mission_store": result,
        "reply_markup": _mission_decision_keyboard(mission.get("mission_id", "")),
        "writes_repo_file": False,
    }


def _workflow_action(raw_input):
    mission_id, agent, step_status = _parse_workflow_input(raw_input)
    if not mission_id or not agent:
        return {
            "command": "workflow",
            "telegram_text": "Send /workflow <mission id> planner complete. Agents: planner, architect, builder, tester, reviewer.",
            "reply_markup": _main_keyboard(),
            "writes_repo_file": False,
        }
    result, _ = update_mission_workflow_step(
        mission_id,
        agent=agent,
        step_status=step_status or "complete",
        findings=f"Telegram marked {agent} {step_status or 'complete'}.",
    )
    if not result.get("success"):
        return {
            "command": "workflow",
            "telegram_text": f"Workflow update failed: {result.get('status', 'unavailable')}.",
            "mission_store": result,
            "reply_markup": _main_keyboard(),
            "writes_repo_file": False,
        }
    return {
        "command": "workflow",
        "telegram_text": (
            f"Workflow updated.\n\nMission: {mission_id}\nAgent: {agent}\nStatus: {step_status or 'complete'}\n"
            "The Mission Vault now carries this handoff for the next Codex/Cursor pickup."
        )[:MAX_REPLY_CHARS],
        "mission_store": result,
        "reply_markup": _main_keyboard(),
        "writes_repo_file": False,
    }


def _mission_decision_action(raw_mission_id, status, command):
    mission_id, approval_level = _parse_mission_decision_input(raw_mission_id)
    if not mission_id:
        return {
            "command": command,
            "telegram_text": f"Send /{command} <mission id> or /{command} <mission id> level3.",
            "reply_markup": _main_keyboard(),
            "writes_repo_file": False,
        }
    if approval_level and approval_level not in {"LEVEL 0", "LEVEL 1", "LEVEL 2", "LEVEL 3", "LEVEL 4", "LEVEL 5"}:
        return {
            "command": command,
            "telegram_text": "Approval level was not recognized. Use level1, level2, level3, level4, or level5.",
            "reply_markup": _main_keyboard(),
            "writes_repo_file": False,
        }
    decision_text = {
        "approved": f"Owner approved mission according to {approval_level or 'the recorded approval level'}.",
        "done": "Owner marked this mission done.",
        "paused": "Owner paused this mission.",
        "rejected": "Owner rejected this mission.",
    }.get(status, f"Owner set mission status to {status}.")
    result, _ = update_mission_status(
        mission_id,
        status,
        owner_decision=decision_text,
        approval_level=approval_level,
        event_type="approval_decision",
        notes=decision_text,
        metadata={"telegram_command": command, "approval_level": approval_level},
    )
    if not result.get("success"):
        return {
            "command": command,
            "telegram_text": f"Mission decision was not recorded: {result.get('status', 'unavailable')}.",
            "mission_store": result,
            "reply_markup": _main_keyboard(),
            "writes_repo_file": False,
        }
    return {
        "command": command,
        "telegram_text": (
            f"Mission {status}.\n\n"
            f"Mission: {mission_id}\n"
            f"Approval: {approval_level or 'unchanged'}\n"
            f"Local runner: {'active' if local_runner_status().get('active') else 'not active'}\n\n"
            "This records your decision for the Codex runner handoff and does not execute build actions. If the local runner is not active, start it with scripts/charlie_runner_control.py start. Telegram still cannot run shell commands directly, apply migrations, send customers, post publicly, take payments, reserve stock, or change farm lifecycle records."
        )[:MAX_REPLY_CHARS],
        "mission_store": result,
        "reply_markup": _main_keyboard(),
        "writes_repo_file": False,
    }


def _mission_action(mission_text, source, repo_root, command, extra):
    mission_text = str(mission_text or "").strip()
    if not mission_text:
        return {
            "command": command,
            "telegram_text": "Send /mission followed by the idea or problem you want Codex to scope.",
            "reply_markup": _main_keyboard(),
            "writes_repo_file": False,
        }
    if _placeholder_mission_text(mission_text):
        return {
            "command": command,
            "telegram_text": (
                "Mission intake was not stored because it is too vague.\n\n"
                "Send /mission with a specific problem, target screen/workflow, and expected outcome."
            ),
            "reply_markup": _main_keyboard(),
            "mission_store": {
                "stored": False,
                "status": "mission_intake_too_vague",
                "reason": "placeholder_charlie_relay_title_without_specific_goal",
            },
            "writes_repo_file": False,
        }
    mission = _mission_summary(mission_text)
    write_result = {"performed": False, "status": "repo_file_write_disabled"}
    if _truthy(source.get(CODEX_CHAT_WRITE_ENABLED_ENV)):
        write_result = _write_mission_to_codex_chat(repo_root, mission_text)
    mission["selected_next_step"] = extra.get("selected_next_step", "") if isinstance(extra, dict) else ""
    mission["codex_chat_write_status"] = write_result["status"]
    store_result = {"stored": False, "status": "mission_store_disabled"}
    if _truthy(source.get(MISSION_STORE_ENABLED_ENV, "1")):
        store_result, _ = record_mission(mission, source_context={
            "source": "telegram",
            "telegram_user_id": _clean_source_value(source.get("_charlie_telegram_user_id", "")),
            "telegram_chat_id": _clean_source_value(source.get("_charlie_telegram_chat_id", "")),
        })
    return {
        "command": command,
        "telegram_text": (
            "Mission intake prepared for CODEX_CHAT.\n\n"
            f"Mission: {mission['title']}\n"
            f"Urgency: {mission['urgency']}\n"
            f"Type: {mission['mission_type']}\n"
            f"Approval level: {mission['approval_level']}\n"
            f"Mission store: {store_result['status']}\n"
            f"Write status: {write_result['status']}\n\n"
            "Codex must still read CODEX_CHAT, CURRENT_STATE, and NEXT_STEPS before building. Hard stops remain active."
        )[:MAX_REPLY_CHARS],
        "reply_markup": _main_keyboard(),
        "mission": mission,
        "codex_chat_write": write_result,
        "mission_store": store_result,
        "writes_repo_file": write_result["performed"],
    }


def _mission_summary(text):
    lower = text.lower()
    urgency = "P2"
    if any(word in lower for word in ["data loss", "down", "broken", "security", "p0", "urgent", "live failed"]):
        urgency = "P0"
    elif any(word in lower for word in ["sales", "money", "customer", "sam", "lead"]):
        urgency = "P1"
    elif any(word in lower for word in ["future", "later", "idea", "backlog"]):
        urgency = "P4"
    mission_type = "feature build"
    if any(word in lower for word in ["plan", "feasibility", "scope", "design"]):
        mission_type = "planning/docs"
    elif any(word in lower for word in ["bug", "fix", "error", "failed"]):
        mission_type = "bugfix"
    elif any(word in lower for word in ["verify", "live test", "test"]):
        mission_type = "live verification"
    approval_level = "LEVEL 2" if mission_type == "planning/docs" else "LEVEL 3"
    return {
        "title": _compact_title(text),
        "raw_text": text,
        "urgency": urgency,
        "mission_type": mission_type,
        "approval_level": approval_level,
        "build_confidence": "requires Codex inspection before build",
    }


def _write_mission_to_codex_chat(repo_root, mission_text):
    path = repo_root / "planning" / "CODEX_CHAT.md"
    try:
        original = path.read_text(encoding="utf-8")
        updated = _replace_code_block_after_heading(original, "### Concept / Problem / Idea", mission_text)
        updated = _replace_code_block_after_heading(
            updated,
            "### Desired Outcome",
            "Codex scopes this Telegram mission, updates the active docs, and proceeds only within the approved safety level.",
        )
        path.write_text(updated, encoding="utf-8")
        return {"performed": True, "status": "codex_chat_updated", "path": "planning/CODEX_CHAT.md"}
    except OSError:
        return {"performed": False, "status": "codex_chat_update_failed"}


def _replace_code_block_after_heading(content, heading, replacement):
    pattern = rf"({re.escape(heading)}\s*\n\s*)```text\n.*?\n```"
    block = f"{heading}\n\n```text\n{replacement.strip()}\n```"
    updated, count = re.subn(pattern, block, content, count=1, flags=re.DOTALL)
    return updated if count else content


def _next_step_options(repo_root):
    text = _read_text(repo_root / "docs" / "00-start-here" / "NEXT_STEPS.md")
    options = []
    current_heading = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            current_heading = line.lstrip("# ").strip()
            continue
        if not line.startswith("- "):
            continue
        item = line[2:].strip()
        if not item or item.lower().startswith("do not "):
            continue
        if current_heading.startswith(("P0", "P1", "P2")):
            options.append(item)
        if len(options) >= 5:
            break
    return options[:5]


def _first_lines_after(text, heading, max_items=5):
    lines = []
    in_section = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == heading:
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section and line.startswith("- "):
            lines.append(line)
        if len(lines) >= max_items:
            break
    return lines


def _compact_title(text):
    title = " ".join(str(text or "").split())
    return title[:90] + ("..." if len(title) > 90 else "")


def _placeholder_mission_text(text):
    normalized = " ".join(str(text or "").strip().lower().split())
    return normalized in {"build charlie relay", "charlie relay", "<idea>"}


def _mission_detail_text(mission):
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    workflow = mission.get("agent_workflow") if isinstance(mission.get("agent_workflow"), list) else []
    context_pack = mission.get("mission_context_pack") if isinstance(mission.get("mission_context_pack"), dict) else {}
    workflow_line = ", ".join(
        f"{item.get('agent')}:{item.get('status', 'pending')}"
        for item in workflow[:5]
        if isinstance(item, dict)
    )
    docs = context_pack.get("active_truth_docs") if isinstance(context_pack.get("active_truth_docs"), list) else []
    return (
        "CHARLIE mission\n\n"
        f"ID: {mission.get('mission_id')}\n"
        f"Status: {mission.get('status')}\n"
        f"Urgency: {mission.get('urgency')}\n"
        f"Type: {mission.get('mission_type')}\n"
        f"Approval: {mission.get('approval_level')}\n"
        f"Vault stage: {vault.get('mission_stage', 'intake')}\n"
        f"Title: {mission.get('title')}\n\n"
        f"Problem: {vault.get('problem_statement') or mission.get('raw_text') or 'not captured'}\n\n"
        f"Agent workflow: {workflow_line or 'planner, architect, builder, tester, reviewer pending'}\n\n"
        f"Context pack: {context_pack.get('version', 'charlie_context_pack_v1')}\n"
        f"Active docs: {', '.join(docs[:4]) or 'start-here docs'}\n\n"
        f"Owner decision: {mission.get('owner_decision') or 'none recorded'}\n\n"
        "Commands: /approve <id> level3, /approve <id> level4, /workflow <id> tester complete, /done <id>, /pause <id>, /reject <id>. These record decisions for the Codex runner handoff; Telegram does not execute shell commands directly."
    )[:MAX_REPLY_CHARS]


def _mission_status_text(mission):
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    workflow = mission.get("agent_workflow") if isinstance(mission.get("agent_workflow"), list) else []
    runner = local_runner_status()
    current_agent, agent_status = _current_agent_status(workflow)
    status = str(mission.get("status") or "unknown").strip()
    return (
        "Mission status\n\n"
        f"ID: {mission.get('mission_id')}\n"
        f"Title: {mission.get('title') or 'Untitled mission'}\n"
        f"Mission status: {status}\n"
        f"Approval: {mission.get('approval_level') or 'not set'}\n"
        f"Vault stage: {vault.get('mission_stage', 'intake')}\n"
        f"Current agent: {current_agent} ({agent_status})\n"
        f"Local runner: {_runner_label(runner)}\n"
        f"Next: {_mission_status_next_action(status, current_agent)}\n\n"
        "This is a quick live position update only. Findings, review packet detail, media, and diffs stay out of Telegram status."
    )[:MAX_REPLY_CHARS]


def _current_agent_status(workflow):
    if not isinstance(workflow, list) or not workflow:
        return "planner", "pending"
    active_states = {"in_progress", "running", "started", "blocked"}
    for item in workflow:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "pending").strip().lower()
        if status in active_states:
            return str(item.get("agent") or "agent").strip(), status
    for item in workflow:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "pending").strip().lower()
        if status in {"pending", "queued", "not_started"}:
            return str(item.get("agent") or "agent").strip(), status
    last = next((item for item in reversed(workflow) if isinstance(item, dict)), {})
    return str(last.get("agent") or "reviewer").strip(), str(last.get("status") or "complete").strip()


def _mission_status_next_action(status, current_agent):
    if status == "new":
        return "owner approval is needed before local pickup."
    if status == "approved":
        return "waiting for the local runner to pick it up."
    if status == "in_progress":
        return f"{current_agent} stage is moving through Agent Runner v2."
    if status == "blocked":
        return "owner or builder attention is needed before it can advance."
    if status == "pr_ready":
        return "owner review is waiting in the CHARLIE dashboard."
    if status == "release_approved":
        return "local release bridge must verify and close the release."
    if status in {"merged", "deployed", "done"}:
        return "mission is past build execution; closeout/release evidence should be checked."
    if status == "paused":
        return "mission is paused until the owner resumes it."
    if status == "rejected":
        return "mission is rejected and should not be picked up."
    return "check the CHARLIE dashboard for the next queue action."


def _mission_decision_keyboard(mission_id):
    mission_id = _clean_source_value(mission_id)
    if not mission_id:
        return _main_keyboard()
    return {
        "inline_keyboard": [[
            {"text": "Status", "callback_data": f"status:{mission_id}"},
        ], [
            {"text": "Approve L3", "callback_data": f"approve:{mission_id} level3"},
            {"text": "Approve L4", "callback_data": f"approve:{mission_id} level4"},
        ], [
            {"text": "Pause", "callback_data": f"pause:{mission_id}"},
            {"text": "Reject", "callback_data": f"reject:{mission_id}"},
        ]]
    }


def _parse_mission_decision_input(value):
    parts = str(value or "").strip().split()
    if not parts:
        return "", ""
    mission_id = _clean_source_value(parts[0])
    approval_level = ""
    for part in parts[1:]:
        normalized = normalize_approval_level(part)
        if normalized:
            approval_level = normalized
            break
    return mission_id, approval_level


def _parse_workflow_input(value):
    parts = str(value or "").strip().split()
    if len(parts) < 2:
        return "", "", ""
    mission_id = _clean_source_value(parts[0])
    agent = parts[1].lower()
    step_status = parts[2].lower() if len(parts) >= 3 else "complete"
    return mission_id, agent, step_status


def _looks_like_mission_id(value):
    value = str(value or "").strip().upper()
    return value.startswith("CHARLIE-MISSION-") or value.startswith("MISSION-")


def _clean_source_value(value):
    return str(value or "").strip()[:120]


def _main_keyboard():
    return {"inline_keyboard": [[{"text": "Status", "callback_data": "/status"}, {"text": "Next", "callback_data": "/next"}]]}


def _read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _repo_root(source):
    configured = str(source.get(REPO_ROOT_ENV, "") or "").strip()
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[2]


def _result(success, status, policy, status_code):
    return {
        "success": success,
        "status": status,
        "mode": "owner_only_charlie_build_relay",
        "charlie_build_relay": dict(policy),
        "sends_telegram": success and policy["enabled"],
        "writes_repo_file": False,
        "can_trigger_codex_runtime": False,
        "can_commit": False,
        "can_merge": False,
        "can_deploy": False,
        "can_write_production_data": False,
        "customer_public_output_enabled": False,
    }, status_code


def _send_result(success, status, policy):
    return {
        "success": success,
        "status": status,
        "mode": "owner_only_charlie_build_relay_send",
        "sends_telegram": success,
        "charlie_build_relay": dict(policy),
        "writes_repo_file": False,
        "can_trigger_codex_runtime": False,
        "can_commit": False,
        "can_merge": False,
        "can_deploy": False,
        "can_write_production_data": False,
        "customer_public_output_enabled": False,
    }


def _secret_matches(headers, source):
    expected = str(source.get(WEBHOOK_SECRET_ENV, "") or "").strip()
    provided = str(_header_value(headers, "X-Telegram-Bot-Api-Secret-Token") or "").strip()
    return bool(expected) and hmac.compare_digest(provided, expected)


def _header_value(headers, name):
    if hasattr(headers, "get"):
        return headers.get(name) or headers.get(name.lower()) or headers.get(name.upper())
    return ""


def _allowed_user_ids(source):
    raw = str(source.get(ALLOWED_USER_IDS_ENV, "") or "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _truthy(value):
    return str(value or "").strip().lower() in TRUTHY


def _auth_locked(now=None):
    now = time.monotonic() if now is None else now
    return now < _AUTH_LOCKED_UNTIL


def _record_auth_failure(now=None):
    global _AUTH_LOCKED_UNTIL
    now = time.monotonic() if now is None else now
    cutoff = now - AUTH_FAILURE_WINDOW_SECONDS
    kept = [stamp for stamp in _AUTH_FAILURE_TIMES if stamp >= cutoff]
    kept.append(now)
    _AUTH_FAILURE_TIMES[:] = kept
    if len(_AUTH_FAILURE_TIMES) >= AUTH_FAILURE_LIMIT:
        _AUTH_LOCKED_UNTIL = now + AUTH_LOCKOUT_SECONDS


def _reset_auth_rate_limit_for_tests():
    global _AUTH_LOCKED_UNTIL
    _AUTH_FAILURE_TIMES[:] = []
    _AUTH_LOCKED_UNTIL = 0.0
