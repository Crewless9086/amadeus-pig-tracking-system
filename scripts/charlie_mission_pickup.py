import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.mission_store import list_missions, update_mission_status
from scripts.charlie_notify import _format_message, main as notify_main


CODEX_CHAT_PATH = REPO_ROOT / "planning" / "CODEX_CHAT.md"


def main():
    load_dotenv(REPO_ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description="Pick up the next approved CHARLIE mission for Codex.")
    parser.add_argument("--status", default="approved", help="Mission status to pick up. Default: approved.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--notify", action="store_true", help="Send owner Telegram notification after pickup.")
    parser.add_argument("--watch", action="store_true", help="Poll for approved missions until one is picked up or Ctrl+C stops the runner.")
    parser.add_argument("--interval-seconds", type=int, default=60)
    args = parser.parse_args()

    if args.watch:
        result, status_code = watch_for_mission(
            status=args.status,
            limit=args.limit,
            dry_run=args.dry_run,
            notify=args.notify,
            interval_seconds=args.interval_seconds,
        )
    else:
        result, status_code = pick_up_next_mission(
            status=args.status,
            limit=args.limit,
            dry_run=args.dry_run,
            notify=args.notify,
        )
    print(result)
    return 0 if status_code < 400 else 1


def watch_for_mission(status="approved", limit=10, dry_run=False, notify=False, interval_seconds=60, max_checks=None):
    interval_seconds = max(5, int(interval_seconds or 60))
    checks = 0
    while True:
        checks += 1
        result, status_code = pick_up_next_mission(
            status=status,
            limit=limit,
            dry_run=dry_run,
            notify=notify,
        )
        result["checks"] = checks
        if result.get("status") != "no_mission_available" or status_code >= 400:
            return result, status_code
        if max_checks is not None and checks >= max_checks:
            return {
                "success": True,
                "status": "watch_timeout_no_mission_available",
                "checks": checks,
            }, 200
        time.sleep(interval_seconds)


def pick_up_next_mission(status="approved", limit=10, dry_run=False, notify=False):
    loaded, status_code = list_missions(status=status, limit=limit)
    if status_code >= 400:
        return {
            "success": False,
            "status": loaded.get("status", "mission_queue_unavailable"),
            "mission_count": 0,
        }, status_code

    missions = loaded.get("missions") or []
    if not missions:
        return {
            "success": True,
            "status": "no_mission_available",
            "mission_count": 0,
        }, 200

    mission = missions[0]
    mission_id = mission.get("mission_id", "")
    codex_chat_preview = _codex_chat_content(mission)
    if dry_run:
        return {
            "success": True,
            "status": "dry_run",
            "mission_id": mission_id,
            "title": mission.get("title"),
            "approval_level": mission.get("approval_level"),
            "runner_mode": _runner_mode(mission.get("approval_level")),
            "would_write": "planning/CODEX_CHAT.md",
            "would_mark_status": "in_progress",
        }, 200

    _write_codex_chat(codex_chat_preview)
    updated, update_status = update_mission_status(
        mission_id,
        "in_progress",
        owner_decision="Codex picked up this approved CHARLIE mission for execution under CODEX_CHAT rules.",
        event_type="status_changed",
        notes="Codex mission pickup wrote planning/CODEX_CHAT.md and marked the mission in progress.",
        metadata={"script": "scripts/charlie_mission_pickup.py"},
    )
    if update_status >= 400:
        return {
            "success": False,
            "status": updated.get("status", "mission_status_update_failed"),
            "mission_id": mission_id,
            "codex_chat_written": True,
        }, update_status

    if notify:
        _send_pickup_notification(mission)

    return {
        "success": True,
        "status": "mission_picked_up",
        "mission_id": mission_id,
        "title": mission.get("title"),
        "approval_level": mission.get("approval_level"),
        "runner_mode": _runner_mode(mission.get("approval_level")),
        "codex_chat_written": True,
        "mission_status": "in_progress",
    }, 200


def _codex_chat_content(mission):
    title = str(mission.get("title") or "").strip()
    raw_text = str(mission.get("raw_text") or title).strip()
    urgency = str(mission.get("urgency") or "P2").strip()
    mission_type = str(mission.get("mission_type") or "feature build").strip()
    approval_level = str(mission.get("approval_level") or "LEVEL 3").strip()
    mission_id = str(mission.get("mission_id") or "").strip()
    runner_mode = _runner_mode(approval_level)
    level_guidance = _approval_level_guidance(approval_level)
    return f"""# CODEX CHAT - ACTIVE MISSION TEMPLATE

This mission was picked up from the CHARLIE Supabase mission queue.

Codex must follow:

- `docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md`
- `docs/00-start-here/CURRENT_STATE.md`
- `docs/00-start-here/NEXT_STEPS.md`
- `docs/00-start-here/WORKFLOW.md`
- `docs/00-start-here/DEPLOYMENT_SOP.md`

---

## OWNER QUICK INPUT

### Concept / Problem / Idea

```text
{raw_text}
```

### Desired Outcome

```text
Codex scopes this CHARLIE mission, updates active docs, builds only within the approved level and hard stops, tests thoroughly, and reports a debrief.
```

### Urgency

```text
{urgency}
```

### Mission Type

```text
{mission_type}
```

### Approval Level

```text
{approval_level}
```

---

## CHARLIE MISSION RECORD

```text
Mission ID: {mission_id}
Mission title: {title}
Mission status at pickup: in_progress
Runner mode: {runner_mode}
```

---

## APPROVAL LEVEL HANDOFF

```text
{level_guidance}
```

---

## REQUIRED CODEX STARTUP

1. Read `docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md`.
2. Read `CURRENT_STATE.md`, `NEXT_STEPS.md`, `WORKFLOW.md`, and `DEPLOYMENT_SOP.md`.
3. Classify scope, hard stops, confidence, and tests.
4. Proceed only within the approved mission level.
5. Update docs and debrief when done.
"""


def _runner_mode(approval_level):
    level = str(approval_level or "").strip().upper().replace("LEVEL", "").strip()
    return {
        "0": "report_only",
        "1": "read_only_scope",
        "2": "docs_planning",
        "3": "code_test_pr",
        "4": "merge_after_verification",
        "5": "red_zone_requires_explicit_confirmation",
    }.get(level, "unknown_requires_review")


def _approval_level_guidance(approval_level):
    mode = _runner_mode(approval_level)
    guidance = {
        "report_only": "LEVEL 0: inspect and report only. Do not edit files, commit, push, merge, deploy, migrate, or write production data.",
        "read_only_scope": "LEVEL 1: read-only investigation and planning. Do not edit files beyond explicit owner-approved scratch/report notes.",
        "docs_planning": "LEVEL 2: docs/planning edits may be made. Do not edit app code, tests, migrations, templates, static assets, or production data.",
        "code_test_pr": "LEVEL 3: code and tests may be changed within the mission scope. Create a branch, run tests, commit, push, and open a PR. Do not merge.",
        "merge_after_verification": "LEVEL 4: release/merge authority after diff and tests are verified. Still do not apply migrations, deploy manually, or perform production writes unless separately approved.",
        "red_zone_requires_explicit_confirmation": "LEVEL 5: red-zone work still requires exact owner confirmation for destructive actions, migrations, production data writes, secrets, sends, payments, reservations, public posts, and lifecycle writes.",
    }
    return guidance.get(mode, "Approval level is unclear. Stop and ask owner before editing or running build actions.")


def _write_codex_chat(content):
    CODEX_CHAT_PATH.write_text(content, encoding="utf-8")


def _send_pickup_notification(mission):
    original_argv = list(sys.argv)
    try:
        sys.argv = [
            "charlie_notify.py",
            "--level",
            "info",
            "--title",
            "Mission picked up",
            "--message",
            f"Codex picked up: {mission.get('title')} ({mission.get('mission_id')}).",
        ]
        return notify_main()
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
