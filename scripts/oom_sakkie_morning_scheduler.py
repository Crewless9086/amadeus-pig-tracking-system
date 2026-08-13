"""Render cron client for the authenticated deployed morning entry point."""
import json
import os
import urllib.request

url = os.environ["OOM_SAKKIE_MORNING_SCHEDULER_URL"].rstrip("/")
token = os.environ["OOM_SAKKIE_MORNING_SCHEDULER_TOKEN"]
synthetic = str(os.environ.get("OOM_SAKKIE_SYNTHETIC_ACCEPTANCE_IDENTITY") or "").strip()
payload = {"synthetic_acceptance_identity": synthetic} if synthetic else {}
request = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
    headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
with urllib.request.urlopen(request, timeout=120) as response:
    result = json.load(response)
if not result.get("success") and result.get("status") not in {
        "daily_manager_unchanged_silent", "daily_manager_replay_suppressed",
        "morning_runtime_failure_replay_suppressed", "synthetic_acceptance_replay_suppressed"}:
    raise SystemExit(1)
print(json.dumps({"success": True, "status": result.get("status"),
                  "telegram_sends": result.get("telegram_sends", 0),
                  "telegram_edits": result.get("telegram_edits", 0)}))
