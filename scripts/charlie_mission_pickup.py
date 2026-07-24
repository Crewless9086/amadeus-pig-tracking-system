import argparse
import os
import re
import socket
import subprocess
import sys
import threading
from types import SimpleNamespace
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.core_workflow import build_core_plan
from modules.charlie.environment import env_value
from modules.charlie.mission_store import AGENT_DEFINITIONS, consume_final_agent_artifact, get_mission, list_missions, list_owner_work_missions, transition_mission_review_state, update_mission_status, update_mission_vault
from modules.charlie.review_readiness import cleared_review_packet, mission_dependency_ids, mission_execution_dependency_ids
from modules.charlie.repository_guard import RepositoryOperationLock, inspect_git_operation_markers, repository_lock_path
from modules.charlie.runner_control import STALE_SECONDS, _pid_alive, runner_status, write_runner_heartbeat
from modules.charlie.runner_preflight import runner_environment_preflight
from modules.charlie.process_policy import background_run_kwargs
from modules.charlie.pr_reconciliation import mission_pr_reference, query_pr_state, reconciliation_decision
from modules.charlie.improvement_analyst import run_operational_analyst
from modules.charlie.executive_runtime import executive_mode, run_executive_cycle
from modules.charlie.private_briefing import queue_due_private_briefs, queue_due_private_followups
from modules.charlie.private_policy import private_policy
from modules.charlie.private_runtime import send_private_telegram_message
from modules.charlie.executive_control import portfolio_priority
from modules.charlie.executive_store import claim_pending_outbox, complete_outbox, record_capability_outcome
from modules.charlie.domain_observers import run_observer_cycle
from modules.charlie.domain_observer_readers import observer_readers
from modules.charlie.domain_observer_store import observer_last_runs, record_observer_run
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
from scripts.charlie_mission_telegram import mission_callback, review_candidate_token


CODEX_CHAT_PATH = REPO_ROOT / "planning" / "CODEX_CHAT.md"
ANALYST_THREAD = None
ANALYST_THREAD_LOCK = threading.Lock()
RECOVERED_STALE_MISSIONS = set()
NOTIFICATION_FINGERPRINTS = {}
BASE_BRANCH_ENV = "CORE_EXECUTION_BASE_BRANCH"
LEASE_TTL_SECONDS = int(env_value("CORE_RUNNER_LEASE_TTL_SECONDS", "900") or "900")


def _load_runner_dotenv():
    candidates = [REPO_ROOT / ".env"]
    if REPO_ROOT.parent.name == ".worktrees":
        candidates.append(REPO_ROOT.parent.parent / ".env")
    if REPO_ROOT.parent.name == ".charlie_runner":
        candidates.append(REPO_ROOT.parents[1] / ".env")
    for path in candidates:
        if path.exists():
            load_dotenv(path, override=False)
            return str(path)
    return ""


def main():
    _load_runner_dotenv()
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
            if checks == 1 or checks % 5 == 0:
                executive, _executive_status = run_executive_cycle(runner={"active_mission_id": (_active_mission() or {}).get("mission_id", "")})
                if executive.get("status") not in {"executive_disabled", "executive_cycle_complete"} or executive.get("results"):
                    executive["checks"] = checks
                    cycle = executive.get("cycle") if isinstance(executive.get("cycle"), dict) else {}
                    write_runner_heartbeat({
                        "status": "executive_cycle_observed", "executive": executive, "checks": checks,
                        "queue_health": cycle.get("queue_health") if isinstance(cycle.get("queue_health"), dict) else {},
                    })
                observers = _run_domain_observers()
                if observers.get("status") not in {"domain_observers_disabled", "observer_cycle_not_due"}:
                    write_runner_heartbeat({"status": "domain_observer_cycle", "observers": observers, "checks": checks})
                if notify:
                    _deliver_executive_outbox()
                reconciliation = reconcile_blocked_pr_missions(notify=notify)
                if reconciliation.get("changed_count"):
                    reconciliation["checks"] = checks
                    write_runner_heartbeat(reconciliation)
            # Review-media cleanup is maintenance, not a mission-pickup gate.
            # Running it every cycle delayed an otherwise ready queue by nearly
            # a minute on the owner workstation.
            if checks % 10 == 0:
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


def reconcile_blocked_pr_missions(notify=False, run_subprocess=None):
    missions, status_code = _owner_queue_missions(statuses=("blocked",), limit=50)
    if status_code >= 400:
        return {"success": False, "status": "blocked_pr_reconciliation_unavailable", "changed_count": 0}
    changed = []
    skipped = []
    for mission in missions:
        mission_id = str(mission.get("mission_id") or "").strip()
        reference = mission_pr_reference(mission)
        if not mission_id or not reference:
            skipped.append({"mission_id": mission_id, "reason": "pr_reference_missing"})
            continue
        pr_state = query_pr_state(reference, run_subprocess=run_subprocess)
        dependency_states = {}
        for dependency_id in mission_dependency_ids(mission):
            dependency_result, dependency_code = get_mission(dependency_id)
            if dependency_code < 400:
                dependency_states[dependency_id] = (dependency_result.get("mission") or {}).get("status", "")
        decision = reconciliation_decision(mission, pr_state, dependency_states)
        if decision.get("action") == "none":
            skipped.append({"mission_id": mission_id, "reason": decision.get("reason")})
            continue
        metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
        review_packet = dict(metadata.get("review_packet") or {})
        review_packet["github_reconciliation"] = {
            "reason": decision.get("reason"),
            "head_sha": decision.get("head_sha", ""),
            "pr_reference": reference,
            "action": decision.get("action"),
        }
        if decision.get("action") == "mark_pr_ready":
            review_packet.update({
                "review_status": "ready_for_owner_review",
                "blocked_agent": "",
                "blocked_reason": "",
                "unresolved_blockers": [],
                "tested_revision": decision.get("head_sha", ""),
                "recommended_next_action": "Owner can review the green, mergeable PR and its evidence.",
            })
        elif decision.get("action") in {"queue_recovery", "wait_dependencies"}:
            disposition = decision.get("disposition") or {}
            review_packet = cleared_review_packet(
                review_packet,
                reason=decision.get("reason", "internal recovery required"),
                return_to_stage=disposition.get("responsible_stage", "planner"),
            )
            review_packet.update({
                "block_disposition": disposition,
                "github_reconciliation": review_packet.get("github_reconciliation", {}),
            })
        updated, updated_code = transition_mission_review_state(
            mission_id,
            decision.get("target_status"),
            review_packet,
            owner_decision="" if decision.get("target_status") == "approved" else str(mission.get("owner_decision") or ""),
            notes=f"GitHub reconciliation: {decision.get('reason')}.",
            expected_status=str(mission.get("status") or "blocked"),
        )
        if updated_code >= 400:
            skipped.append({"mission_id": mission_id, "reason": updated.get("status", "status_update_failed")})
            continue
        changed.append({"mission_id": mission_id, **decision})
        if notify and decision.get("target_status") == "pr_ready":
            _send_notification(
                "pr_ready",
                "CHARLIE mission reconciled as review ready",
                f"Mission {mission_id} has green checks on the exact PR head and is ready for owner review.",
                mission_id=mission_id,
            )
    return {
        "success": True,
        "status": "blocked_pr_reconciliation_complete",
        "changed_count": len(changed),
        "changed": changed,
        "skipped": skipped,
    }


def _active_mission():
    missions, status_code = _execution_state_missions(
        statuses=("in_progress", "release_in_progress"),
        limit=1,
    )
    if status_code < 400 and missions:
        return missions[0]
    return None


def recover_stranded_missions(notify=False):
    missions, status_code = _execution_state_missions(statuses=("in_progress",), limit=100)
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
        metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
        previous_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
        recovery_history = list(previous_packet.get("runner_recovery_history") or [])
        recovery_event = {
            "status": "lease_expired_runner_dead",
            "reason": decision["reason"],
            "runner_status": local_status.get("status"),
            "heartbeat_age_seconds": local_status.get("age_seconds"),
            "process_alive": local_status.get("process_alive"),
            "last_runner_mission_id": local_status.get("last_mission_id", ""),
            "recovered_at": datetime.now(timezone.utc).isoformat(),
        }
        recovery_history.append(recovery_event)
        review_packet = {
            **previous_packet,
            "review_status": "internal_recovery_queued",
            "blocked_agent": blocked_agent,
            "return_to_stage": blocked_agent,
            "blocked_reason": decision["reason"],
            "summary": "CHARLIE runner recovered a stranded in-progress mission instead of freezing the queue.",
            "recommended_next_action": f"CORE will resume automatically from {blocked_agent} after runner recovery.",
            "runner_recovery": recovery_event,
            "runner_recovery_history": recovery_history[-20:],
        }
        status_result, block_status = update_mission_status(
            mission_id,
            "approved",
            owner_decision="CHARLIE runner recovered a dead execution and queued an internal stage resume.",
            event_type="status_changed",
            notes=f"Runner recovery returned dead execution to its responsible stage: {decision['reason']}",
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
                "mission_vault": {"mission_stage": f"recovery_queued_at_{blocked_agent}" if blocked_agent else "recovery_queued"},
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
    lease = ((mission.get("metadata") or {}).get("execution_lease") or {}) if isinstance(mission, dict) else {}
    lease_expired = _execution_lease_expired(lease)
    lease_pid = _execution_lease_pid(lease)
    missing_lease = not isinstance(lease, dict) or not lease.get("lease_id")
    observer_only = (
        str(local_status.get("last_mission_id") or "").strip() == mission_id
        and str(local_status.get("last_result_status") or "").strip() == "active_mission_in_progress"
        and not str(local_status.get("current_agent") or "").strip()
        and not str(local_status.get("execution_artifact") or "").strip()
    )
    mission_stale = _mission_update_age_seconds(mission) >= max(STALE_SECONDS * 2, 240)
    if missing_lease and observer_only and mission_stale:
        return {"recover": True, "reason": "in_progress_missing_execution_lease_and_no_active_stage"}
    if lease_pid and not _pid_alive(lease_pid) and lease_expired:
        return {"recover": True, "reason": "execution_lease_owner_dead_and_expired"}
    if process_dead and heartbeat_stale and lease_expired:
        return {"recover": True, "reason": "runner_process_dead_and_heartbeat_stale"}
    if runner_not_active and heartbeat_stale and lease_expired:
        return {"recover": True, "reason": "runner_inactive_and_heartbeat_stale"}
    return {"recover": False, "reason": "execution_alive_or_lease_not_expired"}


def _mission_update_age_seconds(mission, now=None):
    now = now or datetime.now(timezone.utc)
    updated_at = str((mission or {}).get("updated_at") or "").strip()
    if not updated_at:
        return 0
    try:
        updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        return max(int((now - updated).total_seconds()), 0)
    except (TypeError, ValueError):
        return 0


def _execution_lease_pid(lease):
    if not isinstance(lease, dict):
        return 0
    try:
        process_id = int(lease.get("process_id") or 0)
    except (TypeError, ValueError):
        process_id = 0
    if process_id > 0:
        return process_id
    match = re.search(r":(\d+)$", str(lease.get("holder") or ""))
    return int(match.group(1)) if match else 0


def _execution_lease_expired(lease, now=None):
    if not isinstance(lease, dict) or not lease.get("lease_id"):
        return False
    now = now or datetime.now(timezone.utc)
    expires_at = str(lease.get("expires_at") or "").strip()
    try:
        if expires_at:
            return datetime.fromisoformat(expires_at.replace("Z", "+00:00")) <= now
        heartbeat = datetime.fromisoformat(str(lease.get("heartbeat_at") or lease.get("acquired_at") or "").replace("Z", "+00:00"))
        return heartbeat + timedelta(seconds=int(lease.get("ttl_seconds") or LEASE_TTL_SECONDS)) <= now
    except (TypeError, ValueError):
        return False


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
    dependency_status_cache = {}
    for status in statuses:
        clean_status = str(status or "").strip()
        if not clean_status or clean_status not in wanted:
            continue
        # Approved rows must be dependency-filtered before applying the caller's
        # limit. Otherwise one blocked family child can hide runnable work later
        # in the queue and make a healthy runner wait forever.
        query_limit = max(parsed_limit * 10, 100) if clean_status == "approved" else parsed_limit
        loaded, status_code = list_owner_work_missions(clean_status, limit=query_limit)
        if status_code >= 400:
            return [], status_code
        candidates = loaded.get("missions") or []
        if clean_status == "approved":
            candidates = [
                mission for mission in candidates
                if _mission_dependencies_ready(mission, status_cache=dependency_status_cache)
            ]
        missions.extend(candidates)
        if len(missions) >= parsed_limit:
            break
    return missions[:parsed_limit], status_code


def _execution_state_missions(statuses, limit=100):
    """Read every active execution row, including legacy/system queue classes.

    Pickup remains owner-work only. Liveness and stranded recovery cannot use that
    filter because an invisible active row still owns the global execution slot.
    """
    parsed_limit = max(int(limit or 1), 1)
    missions = []
    status_code = 200
    for status in statuses:
        clean_status = str(status or "").strip()
        if not clean_status:
            continue
        loaded, status_code = list_missions(status=clean_status, limit=parsed_limit, compact=False)
        if status_code >= 400:
            return [], status_code
        missions.extend(loaded.get("missions") or [])
        if len(missions) >= parsed_limit:
            break
    return missions[:parsed_limit], status_code


def _mission_dependencies_ready(mission, status_cache=None):
    status_cache = status_cache if isinstance(status_cache, dict) else {}
    dependency_ids = mission_execution_dependency_ids(mission)
    if not dependency_ids:
        return True
    for dependency_id in dependency_ids:
        if dependency_id not in status_cache:
            loaded, status_code = get_mission(dependency_id)
            dependency = loaded.get("mission") if status_code < 400 and isinstance(loaded, dict) else {}
            status_cache[dependency_id] = str((dependency or {}).get("status") or "").lower()
        if status_cache[dependency_id] not in {"done", "merged", "deployed"}:
            return False
    return True


def _queue_health_snapshot():
    loaded, status_code = list_owner_work_missions("approved", limit=100)
    if status_code >= 400:
        return {"available": False, "status": loaded.get("status", "mission_queue_unavailable")}
    approved = loaded.get("missions") or []
    cache = {}
    runnable = [mission for mission in approved if _mission_dependencies_ready(mission, status_cache=cache)]
    return {
        "available": True,
        "approved_count": len(approved),
        "runnable_count": len(runnable),
        "dependency_blocked_count": len(approved) - len(runnable),
        "dependency_blocked_ids": [mission.get("mission_id") for mission in approved if mission not in runnable],
        "deadlocked": bool(approved and not runnable),
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


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
        artifact_consumer=consume_final_agent_artifact,
    )
    capability_key = f"core.mission.{str(mission.get('mission_type') or 'unknown').strip().lower().replace(' ', '_')}"
    result["capability_trust"] = record_capability_outcome(
        capability_key,
        clean_pass=result.get("mission_status") == "pr_ready" and not result.get("backflow_events"),
        recovered=result.get("status") == "agent_stage_recovery_queued" or bool(result.get("backflow_events")),
        evidence_version=str(result.get("agent_runner_version") or ""),
    )[0]
    if result.get("mission_status") in {"pr_ready", "blocked", "rejected"}:
        result["analyst"] = _queue_analyst_cycle(mission_id, "mission_execution_terminal", notify=notify)
    elif result.get("status") == "agent_stage_recovery_queued":
        result["analyst"] = _queue_analyst_cycle(mission_id, "mission_recovery_queued", notify=notify)
    if notify:
        if status_code < 400 and result.get("mission_status") == "pr_ready":
            _send_review_ready_notification(result)
        elif status_code < 400 and result.get("status") in {"codex_execution_completed", "agent_execution_completed"}:
            _send_review_ready_notification(result)
        elif status_code < 400 and result.get("status") == "agent_stage_recovery_queued":
            _send_notification(
                "info",
                "CHARLIE internal recovery queued",
                (
                    f"Mission {mission_id} hit {result.get('block_disposition', {}).get('block_class', 'a recoverable failure')}. "
                    f"CORE queued recovery from {result.get('block_disposition', {}).get('responsible_stage', result.get('agent', 'the responsible stage'))}; no owner action is required."
                ),
                mission_id=mission_id,
            )
        else:
            _send_blocked_notification(
                "CHARLIE agent execution blocked",
                f"Mission {mission_id} did not complete Agent Runner v2 execution. Status: {result.get('status')}.",
                mission_id=mission_id,
            )
    return result, status_code


def _mission_requires_browser_preflight(mission):
    if str(env_value("CORE_REQUIRE_BROWSER_PREFLIGHT") or "").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    mission = mission if isinstance(mission, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    core = metadata.get("charlie_core") if isinstance(metadata.get("charlie_core"), dict) else {}
    truth = core.get("project_truth") if isinstance(core.get("project_truth"), dict) else {}
    return str(truth.get("workflow_template") or "").strip() == "ui_product_build"


def process_release_approved_mission(mission_id, notify=False, auto_close_no_release=False, auto_merge_pr=False, release_verify_url=""):
    if auto_close_no_release:
        result, status_code = complete_no_release_mission(mission_id=mission_id)
    elif auto_merge_pr:
        result, status_code = run_release_execution(mission_id=mission_id, merge_pr=True, verify_url=release_verify_url)
    else:
        result, status_code = prepare_release_execution(mission_id=mission_id)
        result["status"] = "release_waiting_for_explicit_mode"
        result["next_action"] = "Restart runner with --auto-close-no-release or --auto-merge-pr for automatic release handling."
    if result.get("mission_status") in {"done", "merged", "deployed", "blocked"}:
        result["analyst"] = _queue_analyst_cycle(mission_id, "release_terminal", notify=notify)
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


def _queue_analyst_cycle(mission_id, trigger, notify=False):
    global ANALYST_THREAD
    with ANALYST_THREAD_LOCK:
        if ANALYST_THREAD is not None and ANALYST_THREAD.is_alive():
            return {"success": True, "status": "analyst_cycle_already_running", "mission_id": mission_id}
        ANALYST_THREAD = threading.Thread(
            target=_run_analyst_cycle,
            args=(mission_id, trigger, notify),
            name="charlie-improvement-analyst",
            daemon=True,
        )
        ANALYST_THREAD.start()
    return {"success": True, "status": "analyst_cycle_queued", "mission_id": mission_id, "trigger": trigger}


def _run_analyst_cycle(mission_id, trigger, notify=False):
    try:
        result, status_code = run_operational_analyst(mission_id=mission_id, trigger=trigger, limit=50)
    except Exception as exc:
        return {"success": False, "status": "analyst_cycle_failed", "error_type": exc.__class__.__name__}
    if notify and status_code < 400 and result.get("new_proposals"):
        strongest = sorted(result["new_proposals"], key=lambda item: int(item.get("weakness_score") or 0), reverse=True)[0]
        _send_notification(
            "needs_owner_approval",
            "ANALYST found a CORE improvement",
            (
                f"{strongest.get('problem_detected', 'A recurring CORE weakness was detected')} "
                f"Score: {strongest.get('weakness_score', 0)}. Review it in CORE or Workforce; nothing is applied automatically."
            ),
            mission_id=mission_id,
        )
    return {**result, "status_code": status_code}


def pick_up_next_mission(status="approved", limit=10, dry_run=False, notify=False):
    checkout = _ensure_base_branch()
    if not checkout["success"]:
        failure_status = str(checkout.get("status") or "base_branch_checkout_failed")
        return {
            **checkout,
            "status": failure_status,
            "last_failure": checkout,
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

    if clean_status == "approved" and executive_mode() == "active":
        missions = sorted(missions, key=lambda item: (-portfolio_priority(item), str(item.get("created_at") or ""), str(item.get("mission_id") or "")))
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

    branch_restore = _restore_mission_branch_for_resume(mission)
    if not branch_restore.get("success"):
        return {
            **branch_restore,
            "status": "mission_branch_restore_failed",
            "mission_id": mission_id,
            "codex_chat_written": False,
            "next_action": "Restore the packaged mission branch before resuming review stages.",
        }, 409

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
        "branch_restore": branch_restore,
    }, 200


def _restore_mission_branch_for_resume(mission, run_subprocess=None):
    mission = mission if isinstance(mission, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    artifacts = review_packet.get("agent_artifacts") if isinstance(review_packet.get("agent_artifacts"), dict) else {}
    builder = artifacts.get("builder") if isinstance(artifacts.get("builder"), dict) else {}
    packaging = builder.get("git_packaging") if isinstance(builder.get("git_packaging"), dict) else {}
    branch_name = str(builder.get("branch_name") or packaging.get("branch_name") or "").strip()
    recovery_stash = str(packaging.get("recovery_stash") or "").strip()
    run = run_subprocess or _run_git_command
    explicit_no_change = "changed_files" in builder and not [value for value in (builder.get("changed_files") or []) if str(value).strip()]
    packaged_revision = str(packaging.get("candidate_revision") or packaging.get("source_commit") or "").strip()
    builder_pr = str(builder.get("pr_number") or review_packet.get("pr_number") or "").strip()
    if explicit_no_change and not builder_pr and not recovery_stash and not packaged_revision:
        return {
            "success": True,
            "status": "mission_branch_not_required_no_change",
            "branch_name": branch_name,
            "revision_source": "clean_promoted_base",
        }
    if not branch_name:
        pr_number = builder_pr
        if not pr_number and isinstance(builder.get("links"), dict):
            match = re.search(r"/pull/(\d+)(?:$|[/?#])", str(builder["links"].get("pr") or builder.get("pr_url") or ""))
            pr_number = match.group(1) if match else ""
        if not pr_number:
            return {"success": True, "status": "mission_branch_not_required", "branch_name": ""}
        if not pr_number.isdigit():
            return {"success": False, "status": "invalid_mission_pr_number", "pr_number": pr_number[:40]}
        resolved = run(["gh", "pr", "view", pr_number, "--json", "headRefName", "--jq", ".headRefName"])
        if resolved.returncode != 0:
            return {"success": False, "status": "mission_pr_branch_resolution_failed", "pr_number": pr_number, "stderr": (resolved.stderr or "")[-500:]}
        branch_name = str(resolved.stdout or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._/-]{1,180}", branch_name) or branch_name.startswith(("-", "/")) or ".." in branch_name:
        return {"success": False, "status": "invalid_mission_branch_name", "branch_name": branch_name[:180]}
    fetched = run(["git", "fetch", "origin", branch_name])
    if fetched.returncode != 0:
        return {"success": False, "status": "mission_branch_fetch_failed", "branch_name": branch_name, "stderr": (fetched.stderr or "")[-500:]}
    # The preceding fetch makes FETCH_HEAD the authoritative packaged revision.
    # Detached checkout avoids collisions with a same-named local branch owned by
    # another worktree and prevents a stale local branch from changing evidence.
    switched = run(["git", "switch", "--detach", "FETCH_HEAD"])
    if switched.returncode != 0:
        return {"success": False, "status": "mission_branch_switch_failed", "branch_name": branch_name, "stderr": (switched.stderr or "")[-500:]}
    if recovery_stash:
        applied = run(["git", "stash", "apply", recovery_stash])
        if applied.returncode != 0:
            return {
                "success": False,
                "status": "mission_recovery_stash_apply_failed",
                "branch_name": branch_name,
                "recovery_stash": recovery_stash,
                "stderr": (applied.stderr or "")[-500:],
            }
    return {
        "success": True,
        "status": "mission_branch_restored",
        "branch_name": branch_name,
        "recovery_stash": recovery_stash,
        "recovery_stash_applied": bool(recovery_stash),
        "revision_source": "FETCH_HEAD",
    }


def _run_git_command(command):
    try:
        return subprocess.run(
            command, cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False, timeout=60,
            **background_run_kwargs(),
        )
    except subprocess.TimeoutExpired:
        return SimpleNamespace(returncode=124, stdout="", stderr=f"Command timed out after 60 seconds: {' '.join(command)}")


def _refresh_core_plan_for_pickup(mission):
    mission = mission if isinstance(mission, dict) else {}
    mission_id = str(mission.get("mission_id") or "").strip()
    if not mission_id:
        return {"refreshed": False, "reason": "mission_id_missing"}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    resume_stage = str(review_packet.get("return_to_stage") or review_packet.get("blocked_agent") or "").strip().lower()
    targeted = metadata.get("targeted_invalidation") if isinstance(metadata.get("targeted_invalidation"), dict) else {}
    current_workflow = mission.get("agent_workflow") if isinstance(mission.get("agent_workflow"), list) else []
    if _explicit_targeted_workflow_ready(current_workflow, targeted, resume_stage):
        return {
            "refreshed": False,
            "reason": "explicit_targeted_workflow_preserved",
            "resume_stage": resume_stage,
            "agent_count": len(current_workflow),
        }
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
    if resume_stage in AGENT_DEFINITIONS and resume_stage not in planned_agents:
        definition = AGENT_DEFINITIONS[resume_stage]
        inserted = {
            "agent": resume_stage,
            "status": "pending",
            "purpose": definition.get("purpose", "Complete the owner-requested recovery stage."),
            "findings": "",
            "handoff_to": "",
            "required_output": definition.get("required_output", "charlie_handoff_v1"),
            "instruction_pack": definition.get("instruction_pack", {}),
        }
        review_agents = {"tester", "qa_red_team", "visual_qa_reviewer", "product_reviewer", "business_reviewer", "security_reviewer", "evidence_reviewer", "reviewer", "publisher"}
        insert_at = next((index for index, item in enumerate(plan.get("agent_workflow") or []) if str(item.get("agent") or "").strip() in review_agents), len(plan.get("agent_workflow") or []))
        plan["agent_workflow"] = [*(plan.get("agent_workflow") or [])[:insert_at], inserted, *(plan.get("agent_workflow") or [])[insert_at:]]
        planned_agents.insert(insert_at, resume_stage)
    if (
        current_agents == planned_agents
        and current_truth.get("pipeline_profile") == planned_truth.get("pipeline_profile")
        and current_truth.get("workflow_right_sized") == planned_truth.get("workflow_right_sized")
    ):
        return {"refreshed": False, "reason": "workflow_already_current", "pipeline_profile": planned_truth.get("pipeline_profile", "")}
    refreshed_workflow = _merge_resumable_workflow(
        mission.get("agent_workflow"),
        plan.get("agent_workflow"),
        resume_stage=resume_stage,
    )
    payload = {
        "agent_workflow": refreshed_workflow,
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
        "resume_stage": resume_stage,
    }


def _explicit_targeted_workflow_ready(workflow, targeted, resume_stage=""):
    """Keep an explicit repair workflow from being replaced by a template.

    Control-plane repairs may add missing implementation stages to a malformed
    mission.  Once every declared upstream stage is durably complete and the
    exact target is the sole active stage, pickup must execute that workflow,
    not regenerate the original defective template.
    """
    if not isinstance(targeted, dict) or targeted.get("version") != "charlie_targeted_invalidation_v1":
        return False
    target = str(targeted.get("target_agent") or "").strip().lower()
    if not target or target != str(resume_stage or "").strip().lower():
        return False
    items = {
        str(item.get("agent") or "").strip().lower(): item
        for item in (workflow or [])
        if isinstance(item, dict) and str(item.get("agent") or "").strip()
    }
    target_item = items.get(target) or {}
    if str(target_item.get("status") or "").strip().lower() != "active":
        return False
    active = [agent for agent, item in items.items() if str(item.get("status") or "").strip().lower() == "active"]
    if active != [target]:
        return False
    preserved = [str(agent or "").strip().lower() for agent in (targeted.get("preserved_agents") or []) if str(agent or "").strip()]
    if not preserved:
        if targeted.get("coordinator_reconciliation") is not True:
            return False
        if set(items) != {"evidence_reviewer", "reviewer", "publisher"}:
            return False
        return all(
            str((items.get(agent) or {}).get("status") or "").strip().lower() == "pending"
            and not (items.get(agent) or {}).get("completed_at")
            for agent in ("reviewer", "publisher")
        )
    return all(
        str((items.get(agent) or {}).get("status") or "").strip().lower() == "complete"
        and bool((items.get(agent) or {}).get("completed_at"))
        for agent in preserved
    )


def _merge_resumable_workflow(current_workflow, planned_workflow, resume_stage=""):
    current = {
        str(item.get("agent") or "").strip().lower(): item
        for item in (current_workflow if isinstance(current_workflow, list) else [])
        if isinstance(item, dict) and str(item.get("agent") or "").strip()
    }
    planned = [dict(item) for item in (planned_workflow if isinstance(planned_workflow, list) else []) if isinstance(item, dict)]
    if not planned:
        return []
    sequence = [str(item.get("agent") or "").strip().lower() for item in planned]
    target = resume_stage if resume_stage in sequence else ""
    target_index = sequence.index(target) if target else None
    if target_index is not None:
        earliest_missing = next(
            (
                index
                for index in range(target_index)
                if str(current.get(sequence[index], {}).get("status") or "").strip().lower() != "complete"
            ),
            None,
        )
        if earliest_missing is not None:
            target_index = earliest_missing
            target = sequence[target_index]
    merged = []
    for index, item in enumerate(planned):
        agent = sequence[index]
        previous = current.get(agent, {})
        previous_status = str(previous.get("status") or "").strip().lower()
        if target_index is not None:
            status = "complete" if index < target_index and previous_status == "complete" else ("active" if index == target_index else "pending")
        else:
            status = previous_status if previous_status in {"complete", "active", "pending"} else str(item.get("status") or "pending")
        merged_item = {**item, "status": status}
        if previous_status == "complete":
            for key in ("findings", "handoff_to"):
                if previous.get(key):
                    merged_item[key] = previous[key]
        if status == "complete" and previous_status == "complete" and previous.get("completed_at"):
            merged_item["completed_at"] = previous["completed_at"]
        elif status in {"active", "pending"}:
            merged_item["completed_at"] = None
        merged.append(merged_item)
    active_indexes = [index for index, item in enumerate(merged) if item.get("status") == "active"]
    if len(active_indexes) > 1:
        for index in active_indexes[1:]:
            merged[index]["status"] = "pending"
    if target_index is None and not any(item.get("status") == "active" for item in merged):
        first_pending = next((item for item in merged if item.get("status") == "pending"), None)
        if first_pending:
            first_pending["status"] = "active"
    return merged


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
    now_value = datetime.now(timezone.utc)
    now = now_value.isoformat()
    return {
        "lease_id": f"charlie-lease-{uuid.uuid4().hex[:16]}",
        "mission_id": str(mission_id or "").strip(),
        "holder": f"{socket.gethostname()}:{os.getpid()}",
        "acquired_at": now,
        "heartbeat_at": now,
        "expires_at": (now_value + timedelta(seconds=LEASE_TTL_SECONDS)).isoformat(),
        "ttl_seconds": LEASE_TTL_SECONDS,
        "source": "scripts/charlie_mission_pickup.py",
    }


def _ensure_base_branch():
    configured_base = str(env_value(BASE_BRANCH_ENV) or "").strip()
    # The promoted runtime owns this branch exclusively.  Mission revisions are
    # inspected detached and the next cycle returns here; sharing the legacy
    # runner branch with another worktree recreates the collision this guard is
    # intended to prevent.
    default_base = "charlie-core-runtime-base" if ".charlie_runner" in REPO_ROOT.parts else ""
    base_branch = configured_base or default_base

    repository_lock = RepositoryOperationLock(repository_lock_path(REPO_ROOT))
    acquired, owner = repository_lock.acquire()
    if not acquired:
        return {
            "success": False,
            "status": "repository_operation_locked",
            "failure_class": "repository_infrastructure",
            "lock_owner": owner,
            "recommended_action": "Wait for the active repository operation or recover its stale lock.",
        }
    try:
        return _ensure_base_branch_locked(base_branch)
    finally:
        repository_lock.release()


def _ensure_base_branch_locked(base_branch):
    marker_recovery = _recover_empty_git_operation_markers()
    if not marker_recovery["success"]:
        return marker_recovery

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
    if not base_branch:
        return {
            "success": True,
            "status": "base_branch_not_required_outside_runner_worktree",
            "current_branch": current_branch,
        }
    if current_branch == base_branch:
        codex_chat_recovery = _preserve_generated_codex_chat_before_switch()
        if not codex_chat_recovery["success"]:
            return codex_chat_recovery
        return {
            "success": True,
            "status": "base_branch_already_active",
            "base_branch": base_branch,
            "current_branch": current_branch,
            "codex_chat_recovery": codex_chat_recovery,
        }
    codex_chat_recovery = _preserve_generated_codex_chat_before_switch()
    if not codex_chat_recovery["success"]:
        return codex_chat_recovery
    switched = run(["git", "switch", base_branch])
    if switched["returncode"] != 0:
        return {
            "success": False,
            "status": "base_branch_switch_failed",
            "base_branch": base_branch,
            "current_branch": current_branch,
            "stderr": switched["stderr"],
            "recommended_action": (
                f"Stop the runner and restore the runner worktree to {base_branch}. "
                "CHARLIE will not pick another mission from a mission branch."
            ),
        }
    verified = run(["git", "branch", "--show-current"])
    if verified["returncode"] != 0 or verified["stdout"] != base_branch:
        return {
            "success": False,
            "status": "base_branch_verify_failed",
            "base_branch": base_branch,
            "previous_branch": current_branch,
            "current_branch": verified["stdout"],
            "stderr": verified["stderr"],
            "recommended_action": "Runner branch verification failed after checkout; do not pick a mission.",
        }
    return {
        "success": True,
        "status": "base_branch_restored",
        "base_branch": base_branch,
        "previous_branch": current_branch,
        "codex_chat_recovery": codex_chat_recovery,
    }


def _recover_empty_git_operation_markers(repo_root=REPO_ROOT):
    """Remove only empty stale Git-operation markers left by an interrupted process."""
    return inspect_git_operation_markers(repo_root, run_factory=subprocess.run)


def _preserve_generated_codex_chat_before_switch(repo_root=REPO_ROOT, codex_chat_path=None, run_factory=None):
    codex_chat_path = Path(codex_chat_path or CODEX_CHAT_PATH)
    run_factory = subprocess.run if run_factory is None else run_factory
    relative_path = Path("planning") / "CODEX_CHAT.md"
    try:
        dirty = run_factory(
            ["git", "status", "--porcelain", "--", str(relative_path).replace("\\", "/")],
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=10,
        )
    except Exception as exc:
        return {"success": False, "status": "codex_chat_preservation_check_failed", "error_type": exc.__class__.__name__}
    if dirty.returncode != 0:
        return {"success": False, "status": "codex_chat_preservation_check_failed", "stderr": (dirty.stderr or "").strip()}
    if not (dirty.stdout or "").strip():
        return {"success": True, "status": "codex_chat_clean", "backup_path": ""}
    recovery_dir = Path(repo_root) / ".charlie_runner" / "recovery"
    recovery_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = recovery_dir / f"CODEX_CHAT-{stamp}.md"
    try:
        backup_path.write_text(codex_chat_path.read_text(encoding="utf-8"), encoding="utf-8")
        restored = run_factory(
            ["git", "restore", "--worktree", "--", str(relative_path).replace("\\", "/")],
            cwd=repo_root,
            text=True,
            capture_output=True,
            timeout=10,
        )
    except Exception as exc:
        return {"success": False, "status": "codex_chat_preservation_failed", "error_type": exc.__class__.__name__, "backup_path": str(backup_path)}
    if restored.returncode != 0:
        return {"success": False, "status": "codex_chat_restore_failed", "stderr": (restored.stderr or "").strip(), "backup_path": str(backup_path)}
    return {"success": True, "status": "codex_chat_preserved", "backup_path": str(backup_path)}


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
    if not str(env_value("CORE_RELAY_ALLOWED_USER_IDS") or "").strip():
        missing.append("CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS")
    if not str(env_value("CORE_RELAY_BOT_TOKEN") or "").strip():
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
    notification_mode = str(env_value("CORE_NOTIFICATION_MODE", "all") or "all").strip().lower()
    normalized_level = str(level or "").strip().lower()
    if notification_mode == "executive_only" and normalized_level not in {"needs_owner_approval", "hard_stop"}:
        return 0
    fingerprint = (normalized_level, str(mission_id or ""), str(title or ""), str(message or ""))
    now = time.time()
    ttl = 1800 if normalized_level == "hard_stop" else 21600
    if now - float(NOTIFICATION_FINGERPRINTS.get(fingerprint) or 0) < ttl:
        return 0
    NOTIFICATION_FINGERPRINTS[fingerprint] = now
    notification_level = {
        "running": "info",
        "pr_ready": "success",
        "needs_owner_approval": "warning",
        "hard_stop": "blocked",
    }.get(str(level or "").strip().lower(), level)
    original_argv = list(sys.argv)
    try:
        sys.argv = [
            "charlie_notify.py",
            "--level",
            notification_level,
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
                "notification_level": notification_level,
                "notification_title": title,
            })
        return exit_code
    finally:
        sys.argv = original_argv


def _deliver_executive_outbox():
    policy = private_policy()
    if policy.get("enabled"):
        queue_due_private_briefs()
        queue_due_private_followups()
    claimed, status_code = claim_pending_outbox(limit=10)
    if status_code >= 400:
        return claimed
    delivered = []
    for item in claimed.get("items", []):
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        private_text = payload.get("private_text")
        reply_markup = None
        if not private_text and item.get("event_type") != "private_executive_brief":
            mission_id = str(payload.get("mission_id") or "")
            loaded, loaded_status = get_mission(mission_id) if mission_id else ({}, 404)
            mission = loaded.get("mission") if loaded_status < 400 and isinstance(loaded.get("mission"), dict) else {}
            private_text = _executive_owner_decision_text(payload, mission)
            reply_markup = _executive_owner_decision_keyboard(payload, mission)
        if policy.get("enabled") and private_text:
            _send_result, send_status = send_private_telegram_message(
                policy.get("owner_chat_id"), private_text, reply_markup=reply_markup,
            )
            exit_code = 0 if send_status < 400 else 1
        else:
            exit_code = _send_notification(
                "needs_owner_approval",
                "CHARLIE needs an owner decision",
                str(payload.get("reason") or payload.get("block_class") or "A genuine owner decision is required."),
                mission_id=payload.get("mission_id", ""),
            )
        complete_outbox(item.get("outbox_id"), sent=exit_code == 0, error="" if exit_code == 0 else f"notify_exit_{exit_code}")
        delivered.append({"outbox_id": item.get("outbox_id"), "sent": exit_code == 0})
    return {"success": True, "status": "outbox_delivery_complete", "delivered": delivered}


def _executive_owner_decision_text(payload, mission=None):
    payload = payload if isinstance(payload, dict) else {}
    mission = mission if isinstance(mission, dict) else {}
    mission_id = str(payload.get("mission_id") or mission.get("mission_id") or "")
    title = str(payload.get("title") or mission.get("title") or mission_id or "Protected mission")
    if str(payload.get("action") or "").startswith("operational_outcome_"):
        pending = payload.get("pending_gate_keys") if isinstance(payload.get("pending_gate_keys"), list) else []
        follow_up = str(payload.get("follow_up_mission_id") or "")
        owner_line = (
            "Your decision is required before the protected operation can happen."
            if payload.get("action") == "operational_outcome_owner_required"
            else "No protected action has been taken; CHARLIE prepared the next bounded mission."
        )
        return "\n".join([
            "CHARLIE: delivery is not the finished business outcome",
            title,
            f"Delivered mission: {mission_id}",
            "",
            f"What is complete: code delivery reached {payload.get('mission_status') or 'a terminal delivery state'}.",
            f"What is NOT complete: {payload.get('business_impact') or 'The capability is not verified as operational.'}",
            f"Still pending: {', '.join(pending) or 'operational verification'}.",
            f"Next mission {'prepared' if payload.get('follow_up_prepared', True) else 'identified'}: {follow_up or 'preparation pending'}.",
            owner_line,
            "",
            f"My recommendation: {payload.get('recommended_action') or 'Review the prepared follow-up.'}",
        ]).strip()
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    pr_url = str(packet.get("pr_url") or metadata.get("pr_url") or "").strip()
    risks = payload.get("risk_flags") if isinstance(payload.get("risk_flags"), list) else []
    protected = []
    if any("customer send" in str(value).lower() for value in risks):
        protected.append("customer-message sending")
    if any("payment" in str(value).lower() for value in risks):
        protected.append("payment handling")
    protected_text = " and ".join(protected) or "a protected operational surface"
    evidence = packet.get("test_evidence") if isinstance(packet.get("test_evidence"), list) else []
    evidence_line = f"Evidence: {len(evidence)} recorded test/check item(s) passed." if evidence else "Evidence: release gates will be rechecked when you press Approve Release."
    lines = [
        "CHARLIE needs one release decision",
        title,
        f"Mission: {mission_id}",
        "",
        f"What changed: This tested code touches {protected_text} paths, so I am not allowed to approve it silently.",
        "What Approve Release means: CORE may merge and deploy this tested code after the final release checks pass.",
        "What it does NOT mean: it does not send a customer message, take or confirm payment, reserve stock, or bypass any separate customer/payment approval.",
        evidence_line,
    ]
    if pr_url:
        lines.append(f"PR: {pr_url}")
    lines.extend([
        "",
        "My recommendation: Approve Release if you accept this protected code-path change. Otherwise press Send Back to Tester.",
        "Use one of the buttons below; you do not need to type the mission ID.",
    ])
    return "\n".join(lines).strip()


def _executive_owner_decision_keyboard(payload, mission=None):
    payload = payload if isinstance(payload, dict) else {}
    mission = mission if isinstance(mission, dict) else {}
    mission_id = str(payload.get("mission_id") or mission.get("mission_id") or "")
    if not mission_id:
        return None
    status = str(mission.get("status") or payload.get("mission_status") or "").lower()
    rows = []
    follow_up_id = str(payload.get("follow_up_mission_id") or "")
    if str(payload.get("action") or "").startswith("operational_outcome_") and follow_up_id:
        rows.append([{"text": "Review Follow-up", "callback_data": mission_callback(follow_up_id, "open")}])
    if status == "pr_ready":
        packet = ((mission.get("metadata") or {}).get("review_packet") or {}) if isinstance(mission.get("metadata"), dict) else {}
        if packet.get("review_generation") and packet.get("tested_revision"):
            rows.append([{"text": "Approve Release", "callback_data": mission_callback(mission_id, "approvefinal", review_candidate_token(mission))}])
        rows.append([{"text": "Send Back to Tester", "callback_data": mission_callback(mission_id, "sendback", "tester")}])
    rows.append([{"text": "Refresh Mission", "callback_data": mission_callback(mission_id, "open")}])
    return {"inline_keyboard": rows}


def _run_domain_observers(environ=None):
    values = os.environ if environ is None else environ
    if str(values.get("CHARLIE_DOMAIN_OBSERVERS_ENABLED") or "").strip() != "1":
        return {"success": True, "status": "domain_observers_disabled", "runs": []}
    loaded, loaded_status = observer_last_runs()
    if loaded_status >= 400:
        return {**loaded, "success": False}

    def recorder(run):
        result, status = record_observer_run(run)
        return {**result, "status_code": status}

    return run_observer_cycle(
        observer_readers(),
        last_runs=loaded.get("last_runs") or {},
        recorder=recorder,
    )


if __name__ == "__main__":
    raise SystemExit(main())
