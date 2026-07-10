import argparse
import os
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.core_workflow import build_core_plan
from modules.charlie.mission_store import get_mission, list_missions, list_owner_work_missions, update_mission_status, update_mission_vault
from modules.charlie.runner_control import STALE_SECONDS, runner_status, write_runner_heartbeat
from modules.charlie.runner_preflight import runner_environment_preflight
from modules.charlie.execution_bridge import (
    DEFAULT_TIMEOUT_SECONDS,
    complete_no_release_mission,
    prepare_release_execution,
    process_visual_review_cleanup_queue,
    run_agent_execution_bridge_v2,
    run_codex_execution_bridge,
    run_release_execution,
)
from modules.charlie.build_relay import build_relay_policy
from scripts.charlie_notify import _format_message, main as notify_main


CODEX_CHAT_PATH = REPO_ROOT / "planning" / "CODEX_CHAT.md"
RECOVERED_STALE_MISSIONS = set()
BASE_BRANCH_ENV = "CHARLIE_RUNNER_BASE_BRANCH"
LEASE_TTL_SECONDS = int(os.getenv("CHARLIE_RUNNER_LEASE_TTL_SECONDS", "900") or "900")


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
            checkout = _ensure_base_branch()
            result["post_execution_checkout"] = checkout
            if not checkout["success"]:
                status_code = max(int(status_code or 0), 409)
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
    if notify:
        preflight = _notification_preflight()
        if not preflight["success"]:
            write_runner_heartbeat(preflight)
            return preflight, 503
    if execute_codex:
        preflight = runner_environment_preflight()
        if not preflight["success"]:
            write_runner_heartbeat(preflight)
            return preflight, 503
    checks = 0
    write_runner_heartbeat({"status": "watch_started"})
    while True:
        checks += 1
        if continuous:
            recovery = recover_stranded_missions(notify=notify)
            if recovery.get("recovered_count"):
                recovery["checks"] = checks
                write_runner_heartbeat(recovery)
            cleanup_result = process_visual_review_cleanup_queue()
            if cleanup_result.get("processed_count"):
                cleanup_result["checks"] = checks
                write_runner_heartbeat(cleanup_result)
            active = _active_mission()
            if active:
                result = {
                    "success": True,
                    "status": "active_mission_in_progress",
                    "mission_id": active.get("mission_id"),
                    "title": active.get("title"),
                    "active_status": active.get("status"),
                    "checks": checks,
                    "next_action": "Existing in-progress missions are observed only; CHARLIE will not blindly re-run the pipeline without a lease/recovery decision.",
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
                checkout = _ensure_base_branch()
                result["post_execution_checkout"] = checkout
                if not checkout["success"]:
                    status_code = max(int(status_code or 0), 409)
                result["checks"] = checks
                write_runner_heartbeat(result)
                if not checkout["success"]:
                    return result, status_code
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
    missions, status_code = _owner_queue_missions(
        statuses=("in_progress", "release_in_progress"),
        limit=1,
    )
    if status_code < 400 and missions:
        return missions[0]
    return None


def recover_stranded_missions(notify=False):
    missions, status_code = _owner_queue_missions(statuses=("in_progress",), limit=5)
    if status_code >= 400:
        return {"success": False, "status": "stranded_recovery_queue_unavailable", "recovered_count": 0, "status_code": status_code}
    local_status = runner_status(include_orphans=False, include_git=False, include_ledger=True)
    recovered = []
    skipped = []
    for mission in missions:
        mission_id = str(mission.get("mission_id") or "").strip()
        if not mission_id:
            continue
        decision = _stranded_recovery_decision(mission, local_status)
        if not decision["recover"]:
            skipped.append({"mission_id": mission_id, "reason": decision["reason"]})
            continue
        if mission_id in RECOVERED_STALE_MISSIONS:
            skipped.append({"mission_id": mission_id, "reason": "already_recovered_this_runner"})
            continue
        blocked_agent = _recovery_blocked_agent(mission, local_status)
        review_packet = {
            "review_status": "blocked",
            "blocked_agent": blocked_agent,
            "return_to_stage": blocked_agent,
            "blocked_reason": decision["reason"],
            "summary": "CHARLIE runner recovered a stranded in-progress mission instead of freezing the queue.",
            "recommended_next_action": "Review the recovery packet, then send back or approve rerun from the blocked stage.",
            "runner_recovery": {
                "status": "lease_expired_runner_dead",
                "runner_status": local_status.get("status"),
                "heartbeat_age_seconds": local_status.get("age_seconds"),
                "process_alive": local_status.get("process_alive"),
                "last_runner_mission_id": local_status.get("last_mission_id", ""),
            },
        }
        status_result, block_status = update_mission_status(
            mission_id,
            "blocked",
            owner_decision="CHARLIE runner watchdog recovered a stranded in-progress mission.",
            event_type="status_changed",
            notes=f"Runner watchdog moved stale in-progress mission to blocked: {decision['reason']}",
            metadata={"watchdog": "charlie_mission_pickup", "blocked_agent": blocked_agent},
            expected_status="in_progress",
        )
        if block_status >= 400:
            skipped.append({"mission_id": mission_id, "reason": status_result.get("status", "blocked_status_update_failed")})
            continue
        vault_result, vault_status = update_mission_vault(
            mission_id,
            {
                "review_packet": review_packet,
                "mission_vault": {"mission_stage": f"blocked_at_{blocked_agent}" if blocked_agent else "blocked"},
            },
            notes="Runner watchdog wrote stranded-mission recovery packet.",
        )
        RECOVERED_STALE_MISSIONS.add(mission_id)
        recovered.append({
            "mission_id": mission_id,
            "blocked_agent": blocked_agent,
            "status_update": status_result.get("status"),
            "vault_status": vault_result.get("status"),
            "vault_status_code": vault_status,
        })
        if notify:
            _send_blocked_notification(
                "CHARLIE mission recovered as blocked",
                f"Mission {mission_id} was stranded in_progress and has been moved to blocked. Reason: {decision['reason']}.",
                mission_id=mission_id,
            )
    return {
        "success": True,
        "status": "stranded_recovery_checked",
        "recovered_count": len(recovered),
        "recovered": recovered,
        "skipped": skipped,
        "runner_status": local_status.get("status"),
    }


def _stranded_recovery_decision(mission, local_status):
    mission_id = str(mission.get("mission_id") or "").strip()
    last_mission_id = str(local_status.get("last_mission_id") or "").strip()
    age = local_status.get("age_seconds")
    heartbeat_stale = age is not None and int(age) > max(STALE_SECONDS * 2, 240)
    process_dead = local_status.get("process_alive") is False
    runner_not_active = local_status.get("active") is False and local_status.get("status") in {"runner_stale_or_stopped", "runner_not_started", "runner_code_stale"}
    if last_mission_id and last_mission_id != mission_id and local_status.get("active"):
        return {"recover": True, "reason": "in_progress_not_owned_by_active_runner"}
    if process_dead and heartbeat_stale:
        return {"recover": True, "reason": "runner_process_dead_and_heartbeat_stale"}
    if runner_not_active and heartbeat_stale:
        return {"recover": True, "reason": "runner_inactive_and_heartbeat_stale"}
    return {"recover": False, "reason": "runner_heartbeat_still_active_or_uncertain"}


def _recovery_blocked_agent(mission, local_status):
    ledger = local_status.get("agent_ledger") if isinstance(local_status.get("agent_ledger"), dict) else {}
    latest = ledger.get("latest_stage") if isinstance(ledger.get("latest_stage"), dict) else {}
    agent = str(latest.get("agent") or ledger.get("blocked_agent") or "").strip().lower()
    if agent:
        return agent
    workflow = mission.get("agent_workflow") if isinstance(mission.get("agent_workflow"), list) else []
    for item in workflow:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").strip().lower() in {"active", "blocked"}:
            return str(item.get("agent") or "").strip().lower()
    return "builder"


def _release_approved_mission():
    missions, status_code = _owner_queue_missions(statuses=("release_approved",), limit=1)
    if status_code < 400 and missions:
        return missions[0]
    return None


def _owner_queue_missions(statuses, limit=10):
    wanted = {str(status or "").strip() for status in statuses if str(status or "").strip()}
    parsed_limit = max(int(limit or 1), 1)
    if not wanted:
        return [], 200
    missions = []
    for status in statuses:
        clean_status = str(status or "").strip()
        if not clean_status or clean_status not in wanted:
            continue
        loaded, status_code = list_owner_work_missions(clean_status, limit=parsed_limit)
        if status_code >= 400:
            return [], status_code
        missions.extend(loaded.get("missions") or [])
        if len(missions) >= parsed_limit:
            break
    return missions[:parsed_limit], status_code


def _retryable_queue_error(result, status_code):
    status = str((result or {}).get("status") or "")
    return int(status_code or 0) >= 500 or status in {
        "mission_queue_unavailable",
        "mission_read_failed",
        "not_configured",
    }


def execute_codex_for_mission(mission_id, notify=False, timeout_seconds=DEFAULT_TIMEOUT_SECONDS):
    loaded, _load_status = get_mission(mission_id) if mission_id else ({}, 400)
    mission = loaded.get("mission") if isinstance(loaded, dict) and isinstance(loaded.get("mission"), dict) else {}
    preflight = runner_environment_preflight(require_browser=_mission_requires_browser_preflight(mission))
    if not preflight["success"]:
        preflight["mission_id"] = mission_id
        write_runner_heartbeat(preflight)
        if notify:
            _send_blocked_notification(
                "CHARLIE runner preflight failed",
                f"Mission {mission_id} was not executed because the local runner environment is not ready. {preflight.get('recommended_action')}",
                mission_id=mission_id,
            )
        return preflight, 503
    result, status_code = run_agent_execution_bridge_v2(
        mission_id=mission_id,
        execute_codex=True,
        timeout_seconds=timeout_seconds,
    )
    if notify:
        if status_code < 400 and result.get("mission_status") == "pr_ready":
            _send_review_ready_notification(result)
        elif status_code < 400 and result.get("status") in {"codex_execution_completed", "agent_execution_completed"}:
            _send_review_ready_notification(result)
        else:
            _send_blocked_notification(
                "CHARLIE agent execution blocked",
                f"Mission {mission_id} did not complete Agent Runner v2 execution. Status: {result.get('status')}.",
                mission_id=mission_id,
            )
    return result, status_code


def _mission_requires_browser_preflight(mission):
    mission = mission if isinstance(mission, dict) else {}
    haystack = " ".join([
        str(mission.get("title") or ""),
        str(mission.get("mission_type") or ""),
        str(mission.get("raw_text") or ""),
    ]).lower()
    return any(term in haystack for term in ("ui", "frontend", "dashboard", "visual", "browser", "screenshot", "family tree"))


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
                mission_id=mission_id,
            )
    return result, status_code


def pick_up_next_mission(status="approved", limit=10, dry_run=False, notify=False):
    checkout = _ensure_base_branch()
    if not checkout["success"]:
        return {
            **checkout,
            "status": "base_branch_checkout_failed",
            "mission_count": 0,
            "next_action": "Resolve the git checkout problem before CHARLIE picks up another mission.",
        }, 409
    clean_status = str(status or "approved").strip()
    if clean_status == "approved":
        missions, status_code = _owner_queue_missions(statuses=("approved",), limit=limit)
        loaded = {
            "success": status_code < 400,
            "status": "ok" if status_code < 400 else "mission_queue_unavailable",
            "missions": missions,
        }
    else:
        loaded, status_code = list_missions(status=clean_status, limit=limit)
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

    refresh = _refresh_core_plan_for_pickup(mission)
    if refresh.get("refreshed"):
        refreshed, refreshed_status = get_mission(mission_id)
        if refreshed_status < 400 and refreshed.get("mission"):
            mission = refreshed["mission"]
            codex_chat_preview = _codex_chat_content(mission)

    updated, update_status = update_mission_status(
        mission_id,
        "in_progress",
        owner_decision="Codex picked up this approved CHARLIE mission for execution under CODEX_CHAT rules.",
        event_type="status_changed",
        notes="Codex mission pickup wrote planning/CODEX_CHAT.md and marked the mission in progress.",
        metadata={"script": "scripts/charlie_mission_pickup.py"},
        expected_status=clean_status,
    )
    if update_status >= 400:
        return {
            "success": False,
            "status": "claim_lost" if updated.get("status") == "status_claim_lost" else updated.get("status", "mission_status_update_failed"),
            "mission_id": mission_id,
            "codex_chat_written": False,
            "expected_status": clean_status,
        }, update_status

    lease = _write_execution_lease(mission_id)
    _write_codex_chat(codex_chat_preview)
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
        "execution_lease": lease,
        "workflow_refresh": refresh,
    }, 200


def _refresh_core_plan_for_pickup(mission):
    mission = mission if isinstance(mission, dict) else {}
    mission_id = str(mission.get("mission_id") or "").strip()
    if not mission_id:
        return {"refreshed": False, "reason": "mission_id_missing"}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    if review_packet.get("return_to_stage") or review_packet.get("blocked_agent"):
        return {"refreshed": False, "reason": "resume_marker_present"}
    current_core = metadata.get("charlie_core") if isinstance(metadata.get("charlie_core"), dict) else {}
    current_truth = current_core.get("project_truth") if isinstance(current_core.get("project_truth"), dict) else {}
    plan = build_core_plan(mission)
    planned_truth = plan.get("project_truth") if isinstance(plan.get("project_truth"), dict) else {}
    current_agents = [
        str(item.get("agent") or "").strip()
        for item in (mission.get("agent_workflow") if isinstance(mission.get("agent_workflow"), list) else [])
        if isinstance(item, dict) and str(item.get("agent") or "").strip()
    ]
    planned_agents = [
        str(item.get("agent") or "").strip()
        for item in (plan.get("agent_workflow") if isinstance(plan.get("agent_workflow"), list) else [])
        if isinstance(item, dict) and str(item.get("agent") or "").strip()
    ]
    if (
        current_agents == planned_agents
        and current_truth.get("pipeline_profile") == planned_truth.get("pipeline_profile")
        and current_truth.get("workflow_right_sized") == planned_truth.get("workflow_right_sized")
    ):
        return {"refreshed": False, "reason": "workflow_already_current", "pipeline_profile": planned_truth.get("pipeline_profile", "")}
    payload = {
        "agent_workflow": plan.get("agent_workflow", []),
        "mission_context_pack": {
            "version": plan.get("version", ""),
            "agent_order": planned_agents,
            "workflow_template": planned_truth.get("workflow_template", ""),
            "pipeline_profile": planned_truth.get("pipeline_profile", ""),
            "workflow_right_sized": planned_truth.get("workflow_right_sized", False),
        },
        "charlie_core": plan,
    }
    result, status_code = update_mission_vault(
        mission_id,
        payload,
        notes="CHARLIE runner refreshed approved mission workflow before pickup.",
    )
    return {
        "refreshed": int(status_code or 0) < 400 and result.get("success") is True,
        "reason": result.get("status", "workflow_refresh_attempted"),
        "status_code": status_code,
        "pipeline_profile": planned_truth.get("pipeline_profile", ""),
        "workflow_right_sized": planned_truth.get("workflow_right_sized", False),
        "agent_count": len(planned_agents),
    }


def _write_execution_lease(mission_id):
    lease = _execution_lease_packet(mission_id)
    result, status_code = update_mission_vault(
        mission_id,
        {"execution_lease": lease},
        notes="CHARLIE runner claimed execution lease for local mission run.",
    )
    return {
        **lease,
        "write_status": result.get("status") if isinstance(result, dict) else "unknown",
        "write_status_code": status_code,
        "persisted": int(status_code or 0) < 400,
    }


def _execution_lease_packet(mission_id):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "lease_id": f"charlie-lease-{uuid.uuid4().hex[:16]}",
        "mission_id": str(mission_id or "").strip(),
        "holder": f"{socket.gethostname()}:{os.getpid()}",
        "acquired_at": now,
        "heartbeat_at": now,
        "ttl_seconds": LEASE_TTL_SECONDS,
        "source": "scripts/charlie_mission_pickup.py",
    }


def _ensure_base_branch():
    base_branch = str(os.getenv(BASE_BRANCH_ENV) or "main").strip() or "main"
    upstream_ref = f"origin/{base_branch}" if "/" not in base_branch else base_branch

    def run(command):
        try:
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                timeout=30,
            )
        except Exception as exc:  # pragma: no cover - defensive process boundary
            return {
                "returncode": 1,
                "stdout": "",
                "stderr": f"{exc.__class__.__name__}: {exc}",
            }
        return {
            "returncode": completed.returncode,
            "stdout": (completed.stdout or "").strip(),
            "stderr": (completed.stderr or "").strip(),
        }

    current = run(["git", "branch", "--show-current"])
    if current["returncode"] != 0:
        return {
            "success": False,
            "status": "base_branch_current_failed",
            "base_branch": base_branch,
            "stderr": current["stderr"],
        }
    current_branch = current["stdout"]
    if current_branch == base_branch:
        return {
            "success": True,
            "status": "base_branch_already_active",
            "base_branch": base_branch,
            "current_branch": current_branch,
        }
    upstream = run(["git", "rev-parse", "--verify", upstream_ref])
    if upstream["returncode"] == 0:
        contains_upstream = run(["git", "merge-base", "--is-ancestor", upstream_ref, "HEAD"])
        if contains_upstream["returncode"] == 0:
            return {
                "success": True,
                "status": "base_branch_upstream_contained_by_current_branch",
                "base_branch": base_branch,
                "upstream_ref": upstream_ref,
                "current_branch": current_branch,
            }
    switched = run(["git", "switch", base_branch])
    if switched["returncode"] != 0:
        if upstream["returncode"] == 0:
            contains_upstream = run(["git", "merge-base", "--is-ancestor", upstream_ref, "HEAD"])
            if contains_upstream["returncode"] == 0:
                return {
                    "success": True,
                    "status": "base_branch_switch_skipped_upstream_contained",
                    "base_branch": base_branch,
                    "upstream_ref": upstream_ref,
                    "current_branch": current_branch,
                    "switch_stderr": switched["stderr"],
                }
        return {
            "success": False,
            "status": "base_branch_switch_failed",
            "base_branch": base_branch,
            "current_branch": current_branch,
            "stderr": switched["stderr"],
        }
    return {
        "success": True,
        "status": "base_branch_restored",
        "base_branch": base_branch,
        "previous_branch": current_branch,
    }


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


def _notification_preflight():
    missing = []
    if not str(os.getenv("CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS") or "").strip():
        missing.append("CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS")
    if not str(os.getenv("CHARLIE_BUILD_RELAY_BOT_TOKEN") or "").strip():
        missing.append("CHARLIE_BUILD_RELAY_BOT_TOKEN")
    policy = build_relay_policy()
    if not policy.get("webhook_secret_configured"):
        missing.append("CHARLIE_BUILD_RELAY_WEBHOOK_SECRET")
    if not policy.get("explicitly_enabled"):
        missing.append("CHARLIE_BUILD_RELAY_ENABLED")
    if missing or not policy.get("enabled"):
        return {
            "success": False,
            "status": "notification_preflight_failed",
            "missing_env": sorted(set(missing)),
            "relay_policy_status": {
                "enabled": policy.get("enabled"),
                "explicitly_enabled": policy.get("explicitly_enabled"),
                "configured": policy.get("configured"),
                "allowed_user_ids_configured": policy.get("allowed_user_ids_configured"),
                "webhook_secret_configured": policy.get("webhook_secret_configured"),
            },
            "next_action": "Fix Telegram notification env before starting an unattended CHARLIE runner with --notify.",
        }
    return {"success": True, "status": "notification_preflight_ok"}


def _send_pickup_notification(mission):
    return _send_notification(
        "info",
        "Mission picked up",
        f"Codex picked up: {mission.get('title')} ({mission.get('mission_id')}).",
        mission_id=mission.get("mission_id"),
    )


def _send_review_ready_notification(result):
    return _send_notification(
        "success",
        "Mission ready for review",
        (
            f"Mission {result.get('mission_id')} is at owner review. "
            "Open the CHARLIE dashboard Review section and inspect the packet before final approval."
        ),
        mission_id=result.get("mission_id"),
    )


def _send_release_ready_notification(result):
    return _send_notification(
        "warning",
        "Release approval waiting",
        (
            f"Mission {result.get('mission_id')} has final approval, but release mode is not automatic yet. "
            f"Status: {result.get('status')}."
        ),
        mission_id=result.get("mission_id"),
    )


def _send_done_notification(result):
    return _send_notification(
        "done",
        "Mission completed",
        f"Mission {result.get('mission_id')} reached {result.get('mission_status') or result.get('status')}.",
        mission_id=result.get("mission_id"),
    )


def _send_blocked_notification(title, message, mission_id=""):
    return _send_notification("blocked", title, message, mission_id=mission_id)


def _send_notification(level, title, message, mission_id=""):
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
        if mission_id:
            sys.argv.extend(["--mission-id", str(mission_id)])
        exit_code = notify_main()
        if exit_code != 0:
            write_runner_heartbeat({
                "status": "notification_failed",
                "mission_id": mission_id,
                "notify_failing": True,
                "notification_level": level,
                "notification_title": title,
            })
        return exit_code
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
