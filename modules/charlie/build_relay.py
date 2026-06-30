import hmac
import json
import os
import re
import time
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request


TRUTHY = {"1", "true", "yes", "on"}
ENABLED_ENV = "CHARLIE_BUILD_RELAY_ENABLED"
BOT_TOKEN_ENV = "CHARLIE_BUILD_RELAY_BOT_TOKEN"
WEBHOOK_SECRET_ENV = "CHARLIE_BUILD_RELAY_WEBHOOK_SECRET"
ALLOWED_USER_IDS_ENV = "CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS"
CODEX_CHAT_WRITE_ENABLED_ENV = "CHARLIE_BUILD_RELAY_CODEX_CHAT_WRITE_ENABLED"
REPO_ROOT_ENV = "CHARLIE_BUILD_RELAY_REPO_ROOT"
MIN_SECRET_CHARS = 32
MAX_TELEGRAM_TEXT_CHARS = 3000
MAX_REPLY_CHARS = 3900
AUTH_FAILURE_LIMIT = 8
AUTH_FAILURE_WINDOW_SECONDS = 60
AUTH_LOCKOUT_SECONDS = 300
_AUTH_FAILURE_TIMES = []
_AUTH_LOCKED_UNTIL = 0.0


def build_relay_policy(environ=None):
    source = environ if environ is not None else os.environ
    explicitly_enabled = _truthy(source.get(ENABLED_ENV))
    bot_token = str(source.get(BOT_TOKEN_ENV, "") or "").strip()
    webhook_secret = str(source.get(WEBHOOK_SECRET_ENV, "") or "").strip()
    allowed_ids = _allowed_user_ids(source)
    auth_locked = _auth_locked()
    repo_write_enabled = _truthy(source.get(CODEX_CHAT_WRITE_ENABLED_ENV))
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
    source = environ if environ is not None else os.environ
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
    if not parsed["text"]:
        return _result(False, "charlie_build_relay_text_required", policy, 400)
    if parsed["telegram_user_id"] not in _allowed_user_ids(source):
        body, status_code = _result(False, "charlie_build_relay_user_not_allowed", policy, 403)
        body["telegram_user_id"] = parsed["telegram_user_id"]
        return body, status_code

    action = build_relay_action(parsed["text"], environ=source)
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


def build_relay_action(text, environ=None):
    source = environ if environ is not None else os.environ
    cleaned = str(text or "").strip()[:MAX_TELEGRAM_TEXT_CHARS]
    lower = cleaned.lower()
    repo_root = _repo_root(source)
    if lower in {"/help", "help", "charlie", "/charlie"}:
        return _help_action()
    if lower in {"/status", "status", "what is happening", "where are we"}:
        return _status_action(repo_root)
    if lower in {"/next", "next", "what next", "what is next", "next steps"}:
        return _next_action(repo_root)
    if lower.startswith("/mission"):
        return _mission_action(cleaned[len("/mission"):].strip(), source, repo_root, "mission")
    if lower.startswith("mission:"):
        return _mission_action(cleaned.split(":", 1)[1].strip(), source, repo_root, "mission")
    if lower.startswith("/select"):
        return _select_next_action(cleaned[len("/select"):].strip(), source, repo_root)
    if lower.startswith("select:"):
        return _select_next_action(cleaned.split(":", 1)[1].strip(), source, repo_root)
    return _mission_action(cleaned, source, repo_root, "free_text_mission")


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
    source = environ if environ is not None else os.environ
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
            "/status - current repo state summary\n"
            "/next - next mission options from NEXT_STEPS\n"
            "/mission <idea> - prepare a mission intake\n"
            "/select 1 - turn a listed NEXT_STEPS option into a mission intake\n\n"
            "Safety: this relay cannot run shell commands, commit, merge, deploy, send customers, post publicly, take payments, reserve stock, or write production data."
        ),
        "reply_markup": _main_keyboard(),
        "writes_repo_file": False,
    }


def _status_action(repo_root):
    current = _read_text(repo_root / "docs" / "00-start-here" / "CURRENT_STATE.md")
    summary = _first_lines_after(current, "## Active Branches / PRs", max_items=6)
    if not summary:
        summary = _first_lines_after(current, "## Production State", max_items=5)
    return {
        "command": "status",
        "telegram_text": ("CHARLIE status\n\n" + ("\n".join(summary) if summary else "CURRENT_STATE.md could not be summarized."))[:MAX_REPLY_CHARS],
        "reply_markup": _main_keyboard(),
        "writes_repo_file": False,
    }


def _next_action(repo_root):
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
    return _mission_action(items[index], source, repo_root, "select_next")


def _mission_action(mission_text, source, repo_root, command):
    mission_text = str(mission_text or "").strip()
    if not mission_text:
        return {
            "command": command,
            "telegram_text": "Send /mission followed by the idea or problem you want Codex to scope.",
            "reply_markup": _main_keyboard(),
            "writes_repo_file": False,
        }
    mission = _mission_summary(mission_text)
    write_result = {"performed": False, "status": "repo_file_write_disabled"}
    if _truthy(source.get(CODEX_CHAT_WRITE_ENABLED_ENV)):
        write_result = _write_mission_to_codex_chat(repo_root, mission_text)
    return {
        "command": command,
        "telegram_text": (
            "Mission intake prepared for CODEX_CHAT.\n\n"
            f"Mission: {mission['title']}\n"
            f"Urgency: {mission['urgency']}\n"
            f"Type: {mission['mission_type']}\n"
            f"Approval level: {mission['approval_level']}\n"
            f"Write status: {write_result['status']}\n\n"
            "Codex must still read CODEX_CHAT, CURRENT_STATE, and NEXT_STEPS before building. Hard stops remain active."
        )[:MAX_REPLY_CHARS],
        "reply_markup": _main_keyboard(),
        "mission": mission,
        "codex_chat_write": write_result,
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
