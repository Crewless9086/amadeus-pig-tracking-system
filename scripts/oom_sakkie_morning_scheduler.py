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

MORNING_OK = {"daily_manager_presented", "daily_manager_replay_suppressed",
              "daily_manager_unchanged_silent", "morning_runtime_recipients_projected"}

def run_scheduler(*, now=None, post_fn=post):
    recovery_url = url.rsplit("/morning-schedule", 1)[0] + "/protected-payment-recovery"
    green_recovery_url = url.rsplit("/morning-schedule", 1)[0] + "/green-print-recovery"
    manager_url = url.rsplit("/morning-schedule", 1)[0] + "/general-manager-cycle"
    beacon_url = url.rsplit("/morning-schedule", 1)[0] + "/beacon-publication-cycle"
    recovery = post_fn(recovery_url, {})
    green_recovery = post_fn(green_recovery_url, {})
    manager = post_fn(manager_url, {})
    beacon = post_fn(beacon_url, {})
    now = now or datetime.now(timezone.utc)
    morning = None
    if synthetic or (now.hour > 4 or (now.hour == 4 and now.minute >= 45)):
        morning = post_fn(url, {"synthetic_acceptance_identity": synthetic} if synthetic else {})
    safe = (recovery.get("status") in {"payment_recovery_idle", "payment_recovery_completed"}
        and green_recovery.get("status") in {"documents_green_recovery_idle", "documents_green_recovery_authorized"}
        and manager.get("status") == "general_manager_cycle_completed"
        and beacon.get("success") is True
        and (morning is None or (morning.get("success") is True
                                 and morning.get("status") in MORNING_OK)))
    result = {"success": safe, "status": recovery.get("status"),
    "worker_id": recovery.get("worker_id"), "cycle_id": recovery.get("cycle_id"),
    "heartbeat_at": recovery.get("heartbeat_at"), "next_cycle_at": recovery.get("next_cycle_at"),
    "telegram_sends": recovery.get("telegram_sends", 0),
    "telegram_edits": recovery.get("telegram_edits", 0),
    "green_print_recovery_status": green_recovery.get("status"),
    "green_print_job_id": green_recovery.get("job_id"),
    "manager_status": manager.get("status"),
    "manager_worker_id": manager.get("worker_id"),
    "manager_cycle_id": manager.get("cycle_id"),
    "manager_heartbeat_at": manager.get("heartbeat_at"),
    "manager_next_cycle_at": manager.get("next_cycle_at"),
    "manager_cases_claimed": manager.get("cases_claimed", 0),
    "manager_deliveries_confirmed": manager.get("deliveries_confirmed", 0),
    "beacon_publication_status": beacon.get("status"),
    "beacon_publication_consumer_status": beacon.get("consumer_status"),
    "morning_status": (morning or {}).get("status")}
    return result, 0 if safe else 1

if __name__ == "__main__":
    result, code = run_scheduler()
    print(json.dumps(result))
    raise SystemExit(code)
