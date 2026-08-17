"""Render cron client for the authenticated deployed morning entry point."""
import json
import os
import urllib.request
from datetime import datetime, timezone

url = os.environ["OOM_SAKKIE_MORNING_SCHEDULER_URL"].rstrip("/")
token = os.environ["OOM_SAKKIE_MORNING_SCHEDULER_TOKEN"]
synthetic = str(os.environ.get("OOM_SAKKIE_SYNTHETIC_ACCEPTANCE_IDENTITY") or "").strip()
def post(target, payload):
    request = urllib.request.Request(target, data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)

recovery_url = url.rsplit("/morning-schedule", 1)[0] + "/protected-payment-recovery"
manager_url = url.rsplit("/morning-schedule", 1)[0] + "/general-manager-cycle"
recovery = post(recovery_url, {})
manager = post(manager_url, {})
now = datetime.now(timezone.utc)
morning = None
if synthetic or (now.hour == 4 and 45 <= now.minute < 50):
    morning = post(url, {"synthetic_acceptance_identity": synthetic} if synthetic else {})
safe_recovery = recovery.get("status") in {"payment_recovery_idle", "payment_recovery_completed"}
safe_manager = manager.get("status") == "general_manager_cycle_completed"
if not safe_recovery or not safe_manager:
    raise SystemExit(1)
print(json.dumps({"success": True, "status": recovery.get("status"),
    "worker_id": recovery.get("worker_id"), "cycle_id": recovery.get("cycle_id"),
    "heartbeat_at": recovery.get("heartbeat_at"), "next_cycle_at": recovery.get("next_cycle_at"),
    "telegram_sends": recovery.get("telegram_sends", 0),
    "telegram_edits": recovery.get("telegram_edits", 0),
    "manager_status": manager.get("status"),
    "manager_worker_id": manager.get("worker_id"),
    "manager_cycle_id": manager.get("cycle_id"),
    "manager_heartbeat_at": manager.get("heartbeat_at"),
    "manager_next_cycle_at": manager.get("next_cycle_at"),
    "manager_cases_claimed": manager.get("cases_claimed", 0),
    "manager_deliveries_confirmed": manager.get("deliveries_confirmed", 0),
    "morning_status": (morning or {}).get("status")}))
