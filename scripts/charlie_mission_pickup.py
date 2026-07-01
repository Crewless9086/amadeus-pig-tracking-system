import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.mission_store import list_missions, update_mission_status
from modules.charlie.runner_control import write_runner_heartbeat
from modules.charlie.execution_bridge import (
    DEFAULT_TIMEOUT_SECONDS,
    complete_no_release_mission,
    prepare_release_execution,
    run_agent_execution_bridge_v2,
    run_codex_execution_bridge,
    run_release_execution,
)
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
    parser.add_argument("--continuous", action="store_true", help="Keep polling after pickup and wait while another mission is active.")
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--execute-codex", action="store_true", help="After pickup, run the local Codex execution bridge and stop at owner review.")
    parser.add_argument("--codex-timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--watch-release", action="store_true", help="Also watch release_approved missions and run the local release bridge.")
    parser.add_argument("--auto-close-no-release", action="store_true", help="For release_approved missions with no release needed, mark done automatically.")
    parser.add_argument("--auto-merge-pr", action="store_true", help="For release_approved missions with a PR link, merge the PR locally with gh.")
    parser.add_argument("--release-verify-url", default="", help="Live URL to verify before marking a merged release deployed.")
    args = parser.parse_args()

    if args.watch:
        result, status_code = watch_for_mission(
            status=args.status,
            limit=args.limit,
            dry_run=args.dry_run,
            notify=args.notify,
            interval_seconds=args.interval_seconds,
            continuous=args.continuous,
            execute_codex=args.execute_codex,
            codex_timeout_seconds=args.codex_timeout_seconds,
            watch_release=args.watch_release,
            auto_close_no_release=args.auto_close_no_release,
            auto_merge_pr=args.auto_merge_pr,
            release_verify_url=args.release_verify_url,
        )
    else:
        result, status_code = pick_up_next_mission(
            status=args.status,
            limit=args.limit,
            dry_run=args.dry_run,
            notify=args.notify,
        )
        if (
            args.execute_codex
            and result.get("status") == "mission_picked_up"
            and not args.dry_run
            and status_code < 400
        ):
            result, status_code = execute_codex_for_mission(
                result.get("mission_id", ""),
                notify=args.notify,
                timeout_seconds=args.codex_timeout_seconds,
            )
    print(result)
    return 0 if status_code < 400 else 1


def watch_for_mission(
    status="approved",
    limit=10,
    dry_run=False,
    notify=False,
    interval_seconds=60,
    max_checks=None,
    continuous=False,
    execute_codex=False,
    codex_timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
    watch_release=False,
    auto_close_no_release=False,
    auto_merge_pr=False,
    release_verify_url="",
):
    interval_seconds = max(5, int(interval_seconds or 60))
    checks = 0
    write_runner_heartbeat({"status": "watch_started"})
    while True:
        checks += 1
        if continuous:
            active = _active_mission()
            if active:
                if execute_codex and active.get("status") == "in_progress" and not dry_run:
                    result, status_code = execute_codex_for_mission(
                        active.get("mission_id", ""),
                        notify=notify,
                        timeout_seconds=codex_timeout_seconds,
                    )
                    result["checks"] = checks
                    write_runner_heartbeat(result)
                    if max_checks is not None and checks >= max_checks:
                        return result, status_code
                    time.sleep(interval_seconds)
                    continue
                result = {
                    "success": True,
                    "status": "active_mission_in_progress",
                    "mission_id": active.get("mission_id"),
                    "title": active.get("title"),
                    "active_status": active.get("status"),
                    "checks": checks,
                }
                write_runner_heartbeat(result)
                if max_checks is not None and checks >= max_checks:
                    return result, 200
                time.sleep(interval_seconds)
                continue
            if watch_release:
                release_mission = _release_approved_mission()
                if release_mission:
                    result, status_code = process_release_approved_mission(
                        release_mission.get("mission_id", ""),
                        notify=notify,
                        auto_close_no_release=auto_close_no_release,
                        auto_merge_pr=auto_merge_pr,
                        release_verify_url=release_verify_url,
                    )
                    result["checks"] = checks
                    write_runner_heartbeat(result)
                    if max_checks is not None and checks >= max_checks:
                        return result, status_code
                    time.sleep(interval_seconds)
                    continue
        result, status_code = pick_up_next_mission(
            status=status,
            limit=limit,
            dry_run=dry_run,
            notify=notify,
        )
        result["checks"] = checks
        write_runner_heartbeat(result)
        if continuous and _retryable_queue_error(result, status_code):
            if max_checks is not None and checks >= max_checks:
                return result, status_code
            time.sleep(interval_seconds)
            continue
        if result.get("status") == "mission_picked_up" and continuous and status_code < 400:
            if execute_codex and not dry_run:
                result, status_code = execute_codex_for_mission(
                    result.get("mission_id", ""),
                    notify=notify,
                    timeout_seconds=codex_timeout_seconds,
                )
                result["checks"] = checks
                write_runner_heartbeat(result)
            if max_checks is not None and checks >= max_checks:
                return result, status_code
            time.sleep(interval_seconds)
            continue
        if result.get("status") != "no_mission_available" or status_code >= 400:
            return result, status_code
        if max_checks is not None and checks >= max_checks:
            return {
                "success": True,
                "status": "watch_timeout_no_mission_available",
                "checks": checks,
            }, 200
        time.sleep(interval_seconds)


def _active_mission():
    for status in ("in_progress", "release_in_progress"):
        loaded, status_code = list_missions(status=status, limit=1)
        if status_code < 400 and loaded.get("missions"):
            return loaded["missions"][0]
    return None


def _release_approved_mission():
    loaded, status_code = list_missions(status="release_approved", limit=1)
    if status_code < 400 and loaded.get("missions"):
        return loaded["missions"][0]
    return None


def _retryable_queue_error(result, status_code):
    status = str((result or {}).get("status") or "")
    return int(status_code or 0) >= 500 or status in {
        "mission_queue_unavailable",
        "mission_read_failed",
        "not_configured",
    }


def execute_codex_for_mission(mission_id, notify=False, timeout_seconds=DEFAULT_TIMEOUT_SECONDS):
    result, status_code = run_agent_execution_bridge_v2(
        mission_id=mission_id,
        execute_codex=True,
        timeout_seconds=timeout_seconds,
    )
    if notify:
        if status_code < 400 and result.get("status") in {"codex_execution_completed", "agent_execution_completed"}:
            _send_review_ready_notification(result)
        else:
            _send_blocked_notification(
                "CHARLIE agent execution blocked",
                f"Mission {mission_id} did not complete Agent Runner v2 execution. Status: {result.get('status')}.",
            )
    return result, status_code


def process_release_approved_mission(mission_id, notify=False, auto_close_no_release=False, auto_merge_pr=False, release_verify_url=""):
    if auto_close_no_release:
        result, status_code = complete_no_release_mission(mission_id=mission_id)
    elif auto_merge_pr:
        result, status_code = run_release_execution(mission_id=mission_id, merge_pr=True, verify_url=release_verify_url)
    else:
        result, status_code = prepare_release_execution(mission_id=mission_id)
        result["status"] = "release_waiting_for_explicit_mode"
        result["next_action"] = "Restart runner with --auto-close-no-release or --auto-merge-pr for automatic release handling."
    if notify:
        if status_code < 400 and result.get("mission_status") in {"done", "merged", "deployed"}:
            _send_done_notification(result)
        elif status_code < 400:
            _send_release_ready_notification(result)
        else:
            _send_blocked_notification(
                "Release bridge blocked",
                f"Mission {mission_id} release bridge stopped. Status: {result.get('status')}.",
            )
    return result, status_code


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
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    workflow = mission.get("agent_workflow") if isinstance(mission.get("agent_workflow"), list) else []
    media_references = mission.get("media_references") if isinstance(mission.get("media_references"), list) else []
    context_pack = mission.get("mission_context_pack") if isinstance(mission.get("mission_context_pack"), dict) else {}
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
Vault stage: {vault.get("mission_stage", "intake")}
```

---

## MISSION VAULT

### Problem Statement

```text
{vault.get("problem_statement") or raw_text}
```

### Desired Outcome

```text
{vault.get("desired_outcome") or "Codex scopes this CHARLIE mission, updates active docs, builds only within the approved level and hard stops, tests thoroughly, and reports a debrief."}
```

### Acceptance Criteria

```text
{_format_list(vault.get("acceptance_criteria"))}
```

### Test Plan

```text
{_format_list(vault.get("test_plan"))}
```

### Forbidden Actions

```text
{_format_list(vault.get("forbidden_actions"))}
```

### Media / References

```text
{_format_media(media_references)}
```

### Agent Workflow

```text
{_format_agent_workflow(workflow)}
```

### Shared Mission Context Pack

```text
Version: {context_pack.get("version", "charlie_context_pack_v1")}

Active truth docs:
{_format_list(context_pack.get("active_truth_docs"))}

Shared data rules:
{_format_list(context_pack.get("shared_data_rules"))}

Approval rules:
{_format_list(context_pack.get("approval_rules"))}

Parallel work:
{context_pack.get("parallel_work", "disabled_until_phase_6_parallel_controls")}
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


def _format_list(items):
    if not isinstance(items, list) or not items:
        return "- Not captured yet; Codex must scope this before build."
    return "\n".join(f"- {str(item).strip()}" for item in items if str(item).strip()) or "- Not captured yet."


def _format_media(items):
    if not isinstance(items, list) or not items:
        return "- No media references captured."
    lines = []
    for item in items:
        if isinstance(item, dict):
            label = str(item.get("label") or "Reference").strip()
            reference = str(item.get("reference") or "").strip()
            if reference:
                lines.append(f"- {label}: {reference}")
        elif str(item).strip():
            lines.append(f"- {str(item).strip()}")
    return "\n".join(lines) or "- No media references captured."


def _format_agent_workflow(items):
    if not isinstance(items, list) or not items:
        return "- planner: pending\n- architect: pending\n- builder: pending\n- tester: pending\n- reviewer: pending"
    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        agent = str(item.get("agent") or "agent").strip()
        status = str(item.get("status") or "pending").strip()
        purpose = str(item.get("purpose") or "").strip()
        lines.append(f"- {agent}: {status}" + (f" - {purpose}" if purpose else ""))
    return "\n".join(lines) or "- planner: pending\n- architect: pending\n- builder: pending\n- tester: pending\n- reviewer: pending"


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
    return _send_notification(
        "info",
        "Mission picked up",
        f"Codex picked up: {mission.get('title')} ({mission.get('mission_id')}).",
    )


def _send_review_ready_notification(result):
    return _send_notification(
        "success",
        "Mission ready for review",
        (
            f"Mission {result.get('mission_id')} is at owner review. "
            "Open the CHARLIE dashboard Review section and inspect the packet before final approval."
        ),
    )


def _send_release_ready_notification(result):
    return _send_notification(
        "warning",
        "Release approval waiting",
        (
            f"Mission {result.get('mission_id')} has final approval, but release mode is not automatic yet. "
            f"Status: {result.get('status')}."
        ),
    )


def _send_done_notification(result):
    return _send_notification(
        "done",
        "Mission completed",
        f"Mission {result.get('mission_id')} reached {result.get('mission_status') or result.get('status')}.",
    )


def _send_blocked_notification(title, message):
    return _send_notification("blocked", title, message)


def _send_notification(level, title, message):
    original_argv = list(sys.argv)
    try:
        sys.argv = [
            "charlie_notify.py",
            "--level",
            level,
            "--title",
            title,
            "--message",
            message,
        ]
        return notify_main()
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
