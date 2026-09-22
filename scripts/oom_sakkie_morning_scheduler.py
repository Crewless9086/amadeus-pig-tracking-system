"""Render cron client for the authenticated deployed morning entry point."""
import json
import os
import re
from http.client import HTTPException
from urllib.error import HTTPError
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

url = os.environ["OOM_SAKKIE_MORNING_SCHEDULER_URL"].rstrip("/")
token = os.environ["OOM_SAKKIE_MORNING_SCHEDULER_TOKEN"]
synthetic = str(os.environ.get("OOM_SAKKIE_SYNTHETIC_ACCEPTANCE_IDENTITY") or "").strip()
MANAGER_TIMEOUT_SECONDS = 90
SAST = ZoneInfo("Africa/Johannesburg")
def post(target, payload, *, timeout=120):
    request = urllib.request.Request(target, data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)

MORNING_OK = {"daily_manager_presented", "daily_manager_replay_suppressed",
              "daily_manager_unchanged_silent", "morning_runtime_recipients_projected",
              "morning_runtime_not_due", "daily_manager_not_due",
              "daily_manager_internal_work_silent"}


def _recipient_failures(body):
    """Keep bounded status diagnostics, never recipient identities or prose."""
    rows = body.get("recipient_results") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        return []
    failures = []
    for index, row in enumerate(rows[:8], 1):
        if not isinstance(row, dict) or row.get("success") is not False:
            continue
        failure = {"recipient_index": index, "success": False}
        for field, pattern in (
                ("status", r"[a-z][a-z0-9_]{0,119}"),
                ("delivery_failure_reason", r"[a-z][a-z0-9_]{0,119}"),
                ("failure_kind", r"[A-Za-z][A-Za-z0-9_]{0,63}"),
                ("failure_class", r"[A-Za-z][A-Za-z0-9_]{0,63}")):
            value = row.get(field)
            if isinstance(value, str) and re.fullmatch(pattern, value):
                failure[field] = value
        failures.append(failure)
    return failures

def run_scheduler(*, now=None, post_fn=post):
    request_failures = []

    def invoke(target, payload, *, timeout=120):
        stage = target.rsplit("/", 1)[-1].replace("-", "_")
        try:
            response = (post_fn(target, payload, timeout=timeout)
                        if post_fn is post else post_fn(target, payload))
            if not isinstance(response, dict):
                raise ValueError("scheduler_response_not_object")
            if stage == "morning_schedule":
                response = {**response, "recipient_failures": _recipient_failures(response)}
            return response
        except (OSError, HTTPException, ValueError) as exc:
            # Requests may already have produced effects. Never retry here or
            # let one independent lane prevent the manager's bounded cycle.
            failure = {"stage": stage, "failure_kind": type(exc).__name__,
                       "provider_effects_unknown": True}
            if isinstance(exc, HTTPError):
                failure["http_status"] = exc.code
                try:
                    body = json.loads(exc.read(4096))
                    status = body.get("status") if isinstance(body, dict) else None
                    if isinstance(status, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,119}", status):
                        failure["response_status"] = status
                    if stage == "morning_schedule":
                        recipients = _recipient_failures(body)
                        if recipients:
                            failure["recipient_failures"] = recipients
                except (OSError, HTTPException, ValueError):
                    pass
                finally:
                    exc.close()
            request_failures.append(failure)
            return {"success": False, "status": stage + "_request_contained", **failure}

    recovery_url = url.rsplit("/morning-schedule", 1)[0] + "/protected-payment-recovery"
    green_recovery_url = url.rsplit("/morning-schedule", 1)[0] + "/green-print-recovery"
    manager_url = url.rsplit("/morning-schedule", 1)[0] + "/general-manager-cycle"
    beacon_url = url.rsplit("/morning-schedule", 1)[0] + "/beacon-publication-cycle"
    recovery = invoke(recovery_url, {})
    green_recovery = invoke(green_recovery_url, {})
    beacon = invoke(beacon_url, {})
    now = now or datetime.now(timezone.utc)
    morning = None
    local = now.astimezone(SAST)
    if synthetic or (local.hour, local.minute) >= (6, 45):
        morning = invoke(
            url,
            {"synthetic_acceptance_identity": synthetic} if synthetic else {},
        )
    manager = invoke(manager_url, {}, timeout=MANAGER_TIMEOUT_SECONDS)
    safe = (recovery.get("status") in {"payment_recovery_idle", "payment_recovery_completed"}
        and green_recovery.get("status") in {"documents_green_recovery_idle", "documents_green_recovery_authorized"}
        and manager.get("status") == "general_manager_cycle_completed"
        and beacon.get("success") is True
        and (morning is None or (morning.get("success") is True
                                 and morning.get("status") in MORNING_OK
                                 and not morning.get("recipient_failures"))))
    result = {"success": safe, "status": recovery.get("status"),
    "worker_id": recovery.get("worker_id"), "cycle_id": recovery.get("cycle_id"),
    "heartbeat_at": recovery.get("heartbeat_at"), "next_cycle_at": recovery.get("next_cycle_at"),
    "telegram_sends": recovery.get("telegram_sends", 0),
    "telegram_edits": recovery.get("telegram_edits", 0),
    "green_print_recovery_status": green_recovery.get("status"),
    "green_print_job_id": green_recovery.get("job_id"),
    "manager_status": manager.get("status"),
    "manager_failure_kind": manager.get("failure_kind"),
    "manager_worker_id": manager.get("worker_id"),
    "manager_cycle_id": manager.get("cycle_id"),
    "manager_heartbeat_at": manager.get("heartbeat_at"),
    "manager_next_cycle_at": manager.get("next_cycle_at"),
    "manager_cases_claimed": manager.get("cases_claimed", 0),
    "manager_deliveries_confirmed": manager.get("deliveries_confirmed", 0),
    "beacon_publication_status": beacon.get("status"),
    "beacon_publication_consumer_status": beacon.get("consumer_status"),
    "morning_status": (morning or {}).get("status"),
    "morning_failure_kind": (morning or {}).get("failure_kind"),
    "morning_recipient_failures": (morning or {}).get("recipient_failures", []),
    "request_failures": request_failures}
    return result, 0 if safe else 1

if __name__ == "__main__":
    result, code = run_scheduler()
    print(json.dumps(result))
    raise SystemExit(code)
