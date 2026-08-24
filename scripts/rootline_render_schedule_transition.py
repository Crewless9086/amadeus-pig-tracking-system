"""Compare-and-swap the existing ROOTLINE Render cron to one-minute control.

This changes no hardware or farm state. It is intentionally unusable until the
exact application and cron revisions are live, then updates one named Render
cron and verifies the provider readback. Any unexpected readback is restored
to the observed prior schedule.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request

CRON_ID = "crn-d9vvpi9t0dsc738hjc70"
CRON_NAME = "rootline-autonomous-reassessment"
WEB_REVISION_URL = "https://amadeus-pig-tracking-system.onrender.com/health/revision"
RENDER_BASE = "https://api.render.com/v1"
EXPECTED_PRIOR_SCHEDULE = "*/15 * * * *"
TARGET_SCHEDULE = "*/1 * * * *"


def transition(*, expected_source_commit: str, request_json) -> dict:
    if len(expected_source_commit) != 40 or any(c not in "0123456789abcdef" for c in expected_source_commit):
        return _result(False, "expected_source_commit_invalid")
    service = _service(request_json("GET", f"{RENDER_BASE}/services/{CRON_ID}", None))
    if (service.get("id") != CRON_ID or service.get("name") != CRON_NAME
            or service.get("type") != "cron_job"
            or service.get("suspended") != "not_suspended"):
        return _result(False, "render_cron_identity_mismatch")
    prior = str((service.get("serviceDetails") or {}).get("schedule") or "")
    if prior == TARGET_SCHEDULE:
        return _result(True, "render_cron_schedule_already_current", schedule=prior)
    if prior != EXPECTED_PRIOR_SCHEDULE:
        return _result(False, "render_cron_prior_schedule_mismatch", schedule=prior)
    deploys = request_json("GET", f"{RENDER_BASE}/services/{CRON_ID}/deploys?limit=5", None)
    live_commits = {_deploy(row).get("commit", {}).get("id") for row in deploys
                    if _deploy(row).get("status") == "live"}
    if expected_source_commit not in live_commits:
        return _result(False, "render_cron_exact_revision_not_live", schedule=prior)
    health = request_json("GET", WEB_REVISION_URL, None)
    if (health.get("status") != "ok" or health.get("identity_complete") is not True
            or health.get("revision") != expected_source_commit):
        return _result(False, "render_web_exact_revision_not_live", schedule=prior)
    request_json("PATCH", f"{RENDER_BASE}/services/{CRON_ID}",
                 {"serviceDetails": {"schedule": TARGET_SCHEDULE}})
    after = _service(request_json("GET", f"{RENDER_BASE}/services/{CRON_ID}", None))
    observed = str((after.get("serviceDetails") or {}).get("schedule") or "")
    if observed != TARGET_SCHEDULE:
        request_json("PATCH", f"{RENDER_BASE}/services/{CRON_ID}",
                     {"serviceDetails": {"schedule": prior}})
        restored = _service(request_json("GET", f"{RENDER_BASE}/services/{CRON_ID}", None))
        restored_schedule = str((restored.get("serviceDetails") or {}).get("schedule") or "")
        return _result(False, "render_cron_schedule_readback_mismatch",
                       schedule=observed, rollback_schedule=restored_schedule)
    return _result(True, "render_cron_schedule_transition_verified",
                   schedule=observed, prior_schedule=prior)


def _request_json(method, url, payload):
    token = str(os.environ.get("RENDER_API_KEY") or "").strip()
    if not token:
        raise RuntimeError("render_api_key_unavailable")
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _service(value):
    return value.get("service", value) if isinstance(value, dict) else {}


def _deploy(value):
    return value.get("deploy", value) if isinstance(value, dict) else {}


def _result(success, status, **extra):
    return {"success": success, "status": status, "service_id": CRON_ID,
            "hardware_commands": 0, "farm_writes": 0, **extra}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-source-commit", required=True)
    args = parser.parse_args()
    if not args.apply:
        print(json.dumps(_result(False, "explicit_apply_required"), sort_keys=True))
        raise SystemExit(2)
    result = transition(expected_source_commit=args.expected_source_commit,
                        request_json=_request_json)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
