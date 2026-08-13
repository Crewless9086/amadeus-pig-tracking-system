"""One provider-scheduled Oom Sakkie morning lifecycle invocation.

Render invokes this process once at 04:45 UTC (06:45 SAST). The process owns
the bounded retry window; Supabase's date-stable delivery claim remains the
singular effect authority across retries, restarts, or duplicate workers.
"""
from __future__ import annotations

from datetime import datetime, time, timezone
import json
import sys
import time as clock

from modules.oom_sakkie.morning_runtime import SAST, run_morning_cycle


WINDOW_END = time(7, 0)
RETRY_SECONDS = 60


def run_job(*, cycle=run_morning_cycle, now_fn=None, sleep_fn=None) -> tuple[dict, int]:
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    sleep_fn = sleep_fn or clock.sleep
    while True:
        now = now_fn()
        result = cycle(now=now)
        status = str(result.get("status") or "")
        if status not in {"morning_runtime_recovery_pending", "daily_manager_claim_unproven"}:
            return result, _exit_code(result)
        local = now.astimezone(SAST)
        remaining = (local.replace(hour=7, minute=0, second=0, microsecond=0)
                     - local).total_seconds()
        if remaining <= 0:
            return result, 1
        sleep_fn(min(RETRY_SECONDS, remaining))


def _exit_code(result: dict) -> int:
    status = str(result.get("status") or "")
    safe = (int(result.get("hardware_commands") or 0) == 0
            and result.get("writes_farm_data") is not True
            and result.get("protected_actions_performed") is not True)
    if not safe:
        return 1
    if status == "daily_manager_presented":
        return 0 if (int(result.get("telegram_sends") or 0) == 1
                     and bool(str(result.get("telegram_message_id") or ""))) else 1
    if status in {
        "daily_manager_replay_suppressed",
        "daily_manager_unchanged_silent",
        "morning_runtime_failure_replay_suppressed",
    }:
        return 0 if int(result.get("telegram_sends") or 0) == 0 else 1
    if status == "morning_runtime_failure_escalated":
        return 0 if result.get("provider_delivery_confirmed") is True else 1
    return 1


def _safe_summary(result: dict, exit_code: int) -> dict:
    return {
        "status": str(result.get("status") or ""),
        "success": result.get("success") is True,
        "provider_delivery_confirmed": result.get("provider_delivery_confirmed") is True
            or (str(result.get("telegram_message_id") or "") != ""
                and int(result.get("telegram_sends") or 0) == 1),
        "telegram_sends": int(result.get("telegram_sends") or 0),
        "hardware_commands": int(result.get("hardware_commands") or 0),
        "writes_farm_data": result.get("writes_farm_data") is True,
        "exit_code": exit_code,
    }


if __name__ == "__main__":
    outcome, code = run_job()
    print(json.dumps(_safe_summary(outcome, code), sort_keys=True))
    sys.exit(code)
