"""Backend-owned Render cron client for recurring ROOTLINE reassessment.

The deployed application remains the sole planner/action spine.  This process
only supplies a signed, date-stable 15-minute trigger to its authenticated
endpoint; Supabase schedule claims provide exactly-once ownership.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import urllib.request

# Render and other schedulers execute this file directly, which otherwise puts
# only ``scripts/`` on sys.path instead of the repository root.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from modules.oom_sakkie.automatic_reassessment_scheduler import (
    CADENCE_MINUTES, SCHEDULER_IDENTITY,
)


def build_payload(now: datetime, owner_id: str) -> dict:
    current = now.astimezone(timezone.utc).replace(second=0, microsecond=0)
    minute = current.minute - current.minute % CADENCE_MINUTES
    due = current.replace(minute=minute)
    identity = due.strftime("%Y%m%dT%H%M%SZ")
    return {
        "scheduler_identity": SCHEDULER_IDENTITY,
        "specialist": "ROOTLINE",
        "due_at": due.isoformat(),
        "evidence_cutoff": current.isoformat(),
        "owner_user_id": owner_id,
        "chat_id": owner_id,
        "trigger": "durable_backend_schedule",
        "trigger_id": f"ROOTLINE-AUTO-{identity}",
        "trigger_timestamp": current.isoformat(),
        "language": "en",
    }


def run(*, environ=None, now=None, opener=None) -> dict:
    source = environ if environ is not None else os.environ
    url = str(source.get("ROOTLINE_REASSESSMENT_SCHEDULER_URL") or "").strip()
    token = str(source.get("OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN") or "").strip()
    owners = [part.strip() for part in str(
        source.get("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS") or "").split(",") if part.strip()]
    owner = str(source.get("ROOTLINE_REASSESSMENT_OWNER_USER_ID") or "").strip()
    if (not url.startswith("https://") or len(token) < 32 or not owner
            or owner not in owners):
        return {"success": False, "status": "rootline_scheduler_configuration_invalid",
                "hardware_commands": 0, "telegram_sends": 0}
    payload = build_payload(now or datetime.now(timezone.utc), owner)
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        response = (opener or urllib.request.urlopen)(request, timeout=115)
        with response:
            result = json.load(response)
    except Exception:
        return {"success": False, "status": "rootline_scheduler_endpoint_unavailable",
                "hardware_commands": 0, "telegram_sends": 0}
    return {"success": result.get("success") is True,
            "status": str(result.get("status") or "rootline_scheduler_response_invalid"),
            "scheduled_underlying_status": str(result.get("scheduled_underlying_status") or ""),
            "schedule_identity": str(result.get("schedule_identity") or ""),
            "next_due_at": str(result.get("next_due_at") or ""),
            "hardware_commands": int(result.get("hardware_commands") or 0),
            "telegram_sends": int(result.get("telegram_sends") or 0)}


if __name__ == "__main__":
    outcome = run()
    print(json.dumps(outcome, sort_keys=True))
    sys.exit(0 if outcome.get("success") else 1)
