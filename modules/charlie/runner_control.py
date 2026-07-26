import json
import os
import csv
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from modules.charlie import (
    TEST_CONTROL_ROOT_ENV,
    TEST_ISOLATION_ENV,
    shared_repository_root,
    test_isolation_enabled,
    validated_test_control_root,
)
from modules.charlie.process_policy import background_process_kwargs, background_run_kwargs
from modules.charlie.process_ownership import (
    inspect_process,
    generate_controller_signing_key,
    make_ownership_record,
    make_process_tree_record,
    observe_process_tree,
    process_termination_enabled,
    sign_controller_acknowledgement,
    validate_bootstrap_tree,
    validate_live_bootstrap_tree,
    validate_process_tree,
    validate_termination,
)
from modules.charlie.secret_redaction import redact_payload


REPO_ROOT = Path(__file__).resolve().parents[2]


def _shared_repository_root(repo_root=REPO_ROOT):
    return shared_repository_root(repo_root)


def _control_root(repo_root=REPO_ROOT, environ=None):
    if test_isolation_enabled(environ):
        return validated_test_control_root(repo_root, environ)
    return _shared_repository_root(repo_root)


CONTROL_ROOT = _control_root()
RUNNER_DIR = CONTROL_ROOT / ".charlie_runner"
HEARTBEAT_PATH = RUNNER_DIR / "runner.json"
LOG_PATH = RUNNER_DIR / "runner.log"
SUPERVISOR_PATH = RUNNER_DIR / "supervisor.json"
START_CONTAINMENT_PATH = RUNNER_DIR / "startup-containment.json"
SUPERVISOR_STOP_PATH = RUNNER_DIR / "supervisor.stop"
EMERGENCY_CLEANUP_DISABLED_PATH = RUNNER_DIR / "EMERGENCY_PROCESS_CLEANUP_DISABLED"
EMERGENCY_CLEANUP_REFUSAL_LOG = RUNNER_DIR / "emergency-process-cleanup-refusals.jsonl"
STALE_SECONDS = 120
START_ACK_TIMEOUT_SECONDS = 30
SUPERVISOR_PACKET_VERSION = "charlie_supervisor_ownership_v3"


def _python_executable(repo_root=REPO_ROOT):
    candidates = [
        Path(repo_root) / "venv" / "Scripts" / "python.exe",
        Path(repo_root).parents[1] / "venv" / "Scripts" / "python.exe",
    ]
    return str(next((path for path in candidates if path.exists()), Path(sys.executable)))


RUNNER_COMMAND = [
    _python_executable(),
    str(REPO_ROOT / "scripts" / "charlie_mission_pickup.py"),
    "--watch",
    "--continuous",
    "--notify",
    "--execute-codex",
    "--watch-release",
    "--auto-merge-pr",
    "--release-verify-url",
    "https://amadeus-pig-tracking-system.onrender.com/charlie",
    "--interval-seconds",
    "30",
]
SUPERVISOR_COMMAND = [
    _python_executable(),
    str(REPO_ROOT / "scripts" / "charlie_runner_supervisor.py"),
]


def runner_status(heartbeat_path=None, now=None, include_orphans=None, include_git=True, include_ledger=True):
    heartbeat_path = Path(heartbeat_path or HEARTBEAT_PATH)
    if include_orphans is None:
        include_orphans = heartbeat_path == HEARTBEAT_PATH
    payload = _read_json(heartbeat_path)
    now = now or datetime.now(timezone.utc)
    last_seen = _parse_iso(payload.get("last_seen"))
    age_seconds = int((now - last_seen).total_seconds()) if last_seen else None
    process_alive = _pid_alive(payload.get("pid"))
    heartbeat_fresh = age_seconds is not None and age_seconds <= STALE_SECONDS
    runner_source_commit = str(payload.get("runner_source_commit") or "").strip()
    current_source_commit = _current_git_commit() if include_git else ""
    code_stale = bool(runner_source_commit and current_source_commit and runner_source_commit != current_source_commit)
    active = process_alive and heartbeat_fresh and not code_stale
    final_artifact_present = bool(payload.get("final_artifact_present"))
    if not final_artifact_present and _execution_artifact_exists(payload.get("execution_artifact", "")):
        final_artifact_present = True
        if payload.get("last_result_status") == "codex_running":
            payload["last_result_status"] = "codex_final_artifact_seen"
    orphan_processes = [] if payload or not include_orphans else _find_runner_processes()
    supervisor = _read_json(SUPERVISOR_PATH) if heartbeat_path == HEARTBEAT_PATH else {}
    supervisor_alive = _pid_alive(supervisor.get("pid"))
    supervisor_child_alive = _pid_alive(supervisor.get("child_pid"))
    generation_owned = bool(
        str(supervisor.get("generation") or "")
        and str(supervisor.get("generation") or "") == str(payload.get("supervisor_generation") or "")
    )
    supervisor_owns_runner = bool(
        supervisor_alive
        and supervisor_child_alive
        and process_alive
        and generation_owned
        and (
            int(supervisor.get("child_pid") or 0) == int(payload.get("pid") or -1)
            or _pid_descends_from(payload.get("pid"), supervisor.get("child_pid"))
            # The generation is an unguessable token injected only into this
            # child tree. It is the reliable fallback when a Windows process
            # ancestry probe transiently fails.
            or generation_owned
        )
    )
    if heartbeat_path == HEARTBEAT_PATH:
        active = active and supervisor_owns_runner
    ledger_summary = _read_agent_ledger_summary(payload.get("agent_ledger_path", "")) if include_ledger else {}
    operating_state = _runner_operating_state(payload, ledger_summary, active)
    if code_stale and process_alive and heartbeat_fresh:
        status = "runner_code_stale"
        next_action = "Restart the local CHARLIE runner because main changed after this runner process started."
    elif active:
        status = "runner_active"
        next_action = {
            "running_agent": "CORE is actively executing the displayed agent stage.",
            "between_stages": "CORE is healthy and transitioning between agent stages.",
            "waiting_for_queue": "CORE is healthy and waiting for an approved mission.",
            "queue_deadlocked": "CORE is alive but cannot run approved work; CHARLIE must repair the dependency deadlock.",
        }.get(operating_state, "CORE is healthy and processing the mission queue.")
    elif orphan_processes:
        status = "runner_orphaned"
        next_action = "Stop the orphaned local CHARLIE runner, then start it again so runner control owns the heartbeat."
    elif heartbeat_path == HEARTBEAT_PATH and supervisor_alive:
        status = "runner_starting"
        next_action = "CORE supervisor owns a current startup generation and is waiting for runner acknowledgement."
    elif payload:
        status = "runner_stale_or_stopped"
        next_action = "Start the local CHARLIE runner before expecting approved missions to auto-pick up."
    else:
        status = "runner_not_started"
        next_action = "Start the local CHARLIE runner before expecting approved missions to auto-pick up."
    return redact_payload({
        "success": True,
        "status": status,
        "active": active,
        "operating_state": operating_state,
        "pid": payload.get("pid"),
        "process_alive": process_alive,
        "heartbeat_fresh": heartbeat_fresh,
        "last_seen": payload.get("last_seen", ""),
        "age_seconds": age_seconds,
        "last_result_status": payload.get("last_result_status", ""),
        "last_mission_id": payload.get("last_mission_id", ""),
        "elapsed_seconds": payload.get("elapsed_seconds"),
        "changed_files_count": payload.get("changed_files_count"),
        "final_artifact_present": final_artifact_present,
        "execution_artifact": payload.get("execution_artifact", ""),
        "agent_runner_version": payload.get("agent_runner_version", ""),
        "runner_source_commit": runner_source_commit,
        "current_source_commit": current_source_commit,
        "runner_code_stale": code_stale,
        "current_agent": payload.get("current_agent", ""),
        "current_action": payload.get("current_action", ""),
        "agent_ledger_path": payload.get("agent_ledger_path", ""),
        "stdout_tail": payload.get("stdout_tail", ""),
        "stderr_tail": payload.get("stderr_tail", ""),
        "notify_failing": bool(payload.get("notify_failing")),
        "notification_level": payload.get("notification_level", ""),
        "notification_title": payload.get("notification_title", ""),
        "queue_health": payload.get("queue_health") if isinstance(payload.get("queue_health"), dict) else {},
        "last_progress_at": payload.get("last_progress_at", ""),
        "agent_ledger": ledger_summary,
        "orphan_processes": orphan_processes,
        "supervisor_active": supervisor_alive,
        "supervisor_owns_runner": supervisor_owns_runner,
        "supervisor_status": supervisor.get("status", ""),
        "supervisor_pid": supervisor.get("pid"),
        "supervisor_child_pid": supervisor.get("child_pid"),
        "supervisor_generation": supervisor.get("generation", ""),
        "owner_process_pid": supervisor.get("pid") if supervisor_owns_runner else None,
        "supervisor_restart_count": int(supervisor.get("restart_count") or 0),
        "supervisor_identical_failure_count": int(supervisor.get("identical_failure_count") or 0),
        "supervisor_latest_failure": supervisor.get("latest_failure") or supervisor.get("failure_detail") or {},
        "supervisor_recommended_action": supervisor.get("recommended_action", ""),
        "log_path": str(LOG_PATH),
        "heartbeat_path": str(heartbeat_path),
        "command": _display_command(),
        "next_action": next_action,
        "can_start_from_web": False,
        "can_stop_from_web": False,
    })


def _runner_operating_state(payload, ledger, active):
    if not active:
        return "stale_or_stopped"
    latest = ledger.get("latest_stage") if isinstance(ledger, dict) and isinstance(ledger.get("latest_stage"), dict) else {}
    current_agent = str(payload.get("current_agent") or latest.get("agent") or "").strip()
    stage_status = str(latest.get("status") or "").strip().lower()
    if current_agent and stage_status in {"running", "in_progress", "active"}:
        return "running_agent"
    if payload.get("last_mission_id") and (current_agent or stage_status in {"complete", "completed", "passed"}):
        return "between_stages"
    queue_health = payload.get("queue_health") if isinstance(payload.get("queue_health"), dict) else {}
    return "queue_deadlocked" if queue_health.get("deadlocked") else "waiting_for_queue"


def write_runner_heartbeat(result=None, heartbeat_path=None):
    heartbeat_path = Path(heartbeat_path or HEARTBEAT_PATH)
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    result = redact_payload(result if isinstance(result, dict) else {})
    previous = _read_json(heartbeat_path)
    payload = {
        "pid": os.getpid(),
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "last_result_status": str(result.get("status") or ""),
        "last_mission_id": str(result.get("mission_id") or ""),
        "active_status": str(result.get("active_status") or ""),
        "runner_source_commit": _current_git_commit(),
        "runner_source_branch": _current_git_branch(),
        "supervisor_generation": str(os.getenv("CHARLIE_SUPERVISOR_GENERATION") or ""),
        "startup_nonce": str(os.getenv("CHARLIE_RUNNER_STARTUP_NONCE") or ""),
    }
    for key in (
        "elapsed_seconds",
        "changed_files_count",
        "final_artifact_present",
        "execution_artifact",
        "agent_runner_version",
        "current_agent",
        "current_action",
        "agent_ledger_path",
        "stdout_tail",
        "stderr_tail",
        "notify_failing",
        "notification_level",
        "notification_title",
        "last_failure",
        "failure_class",
        "error_type",
        "marker_path",
        "recommended_action",
        "queue_health",
        "executive",
        "last_progress_at",
    ):
        if key in result:
            payload[key] = result.get(key)
        elif key in {"queue_health", "executive", "last_progress_at"} and key in previous:
            payload[key] = previous.get(key)
    payload = redact_payload(payload)
    generation = str(payload.get("supervisor_generation") or "")
    if generation:
        identity = {}
        startup_nonce = str(payload.get("startup_nonce") or "")
        if startup_nonce:
            supervisor = _read_json(SUPERVISOR_PATH)
            tree = supervisor.get("process_tree_identity")
            decision = validate_bootstrap_tree(
                tree,
                generation=generation,
                revision=str(payload.get("runner_source_commit") or ""),
                startup_nonce=startup_nonce,
                require_interpreter=True,
            )
            if decision["authorized"]:
                identity = next(
                    (
                        item for item in tree.get("members", [])
                        if int(item.get("pid") or -1) == os.getpid()
                    ),
                    {},
                )
        else:
            identity = make_ownership_record(
                inspect_process(os.getpid()),
                generation,
                "charlie-control",
                generation,
                "charlie_runner",
            )
        if identity:
            payload["process_identity"] = identity
    atomic_write_json(heartbeat_path, payload)
    return payload


def emergency_process_cleanup_disabled(marker_path=None):
    return Path(marker_path or EMERGENCY_CLEANUP_DISABLED_PATH).exists()


def record_emergency_cleanup_refusal(operation, requested_pid, log_path=None):
    path = Path(log_path or EMERGENCY_CLEANUP_REFUSAL_LOG)
    packet = {
        "status": "emergency_process_cleanup_disabled",
        "operation": str(operation or ""),
        "requested_pid": str(requested_pid if requested_pid is not None else ""),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(packet, sort_keys=True) + "\n")
    except OSError:
        packet["refusal_log_status"] = "write_failed"
    return packet


def start_runner(status_override=None, respect_stop_marker=True):
    # Starting and clearing containment are deliberately separate governed
    # actions.  No startup caller is allowed to consume or remove this marker.
    if SUPERVISOR_STOP_PATH.exists():
        return {
            "success": False,
            "status": "governed_stop_active",
            "stop_marker": str(SUPERVISOR_STOP_PATH),
        }, 423
    supervisor = _read_json(SUPERVISOR_PATH)
    if _pid_alive(supervisor.get("pid")):
        return {
            "success": True,
            "status": "runner_already_active",
            "runner": status_override if isinstance(status_override, dict) else runner_status(),
            "supervisor_pid": supervisor.get("pid"),
            "supervisor_generation": supervisor.get("generation", ""),
        }, 200
    status = status_override if isinstance(status_override, dict) else runner_status()
    if status["active"]:
        return {"success": True, "status": "runner_already_active", "runner": status}, 200
    if status.get("orphan_processes"):
        return {"success": False, "status": "runner_orphaned_existing_process", "runner": status}, 409
    if not process_termination_enabled():
        return {
            "success": False,
            "status": "start_containment_capability_not_enabled",
        }, 423
    RUNNER_DIR.mkdir(parents=True, exist_ok=True)
    if SUPERVISOR_STOP_PATH.exists():
        return {
            "success": False,
            "status": "governed_stop_active",
            "stop_marker": str(SUPERVISOR_STOP_PATH),
        }, 423
    python_path = SUPERVISOR_COMMAND[0]
    if not Path(python_path).exists():
        python_path = sys.executable
    command = [python_path, *SUPERVISOR_COMMAND[1:]]
    generation = uuid.uuid4().hex
    startup_nonce = uuid.uuid4().hex
    controller_private_key, controller_public_key = generate_controller_signing_key()
    intended_revision = _current_git_commit()
    child_env = {
        **os.environ,
        "CHARLIE_SUPERVISOR_GENERATION": generation,
        "CHARLIE_STARTUP_NONCE": startup_nonce,
        "CHARLIE_INTENDED_RUNTIME_REVISION": intended_revision,
        "CHARLIE_INTENDED_EXECUTION_REVISION": intended_revision,
        "CHARLIE_CONTROLLER_PUBLIC_KEY": controller_public_key,
    }
    # The final check is deliberately adjacent to process creation.  A marker
    # arriving after this point is still authoritative: both the child entry
    # point and the acknowledgement loop refuse it and contain the new tree.
    if SUPERVISOR_STOP_PATH.exists():
        return {
            "success": False,
            "status": "governed_stop_active",
            "stop_marker": str(SUPERVISOR_STOP_PATH),
        }, 423
    with LOG_PATH.open("ab") as log:
        process = subprocess.Popen(
            command,
            cwd=str(REPO_ROOT),
            env=child_env,
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            **background_process_kwargs(),
        )
    observation = observe_process_tree(
        process.pid,
        generation=generation,
        revision=intended_revision,
        startup_nonce=startup_nonce,
        expected_script=Path(command[-1]).name,
        expected_root_executable=python_path,
        process_role_prefix="supervisor",
    )
    if not observation.get("success"):
        SUPERVISOR_STOP_PATH.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        evidence = _write_startup_failure(
            generation,
            startup_nonce,
            intended_revision,
            observation.get("reason") or "ownership_identity_incomplete",
            observation.get("tree") or {},
        )
        containment = _contain_spawned_process(
            process, observation.get("tree") or {}
        )
        return {
            "success": False,
            "status": "ownership_identity_incomplete",
            "reason": evidence["reason"],
            "generation": generation,
            "startup_nonce": startup_nonce,
            "containment": containment,
        }, 503
    supervisor_tree = observation["tree"]
    members = supervisor_tree.get("members") or []
    interpreter = next(
        (item for item in members if int(item.get("pid") or -1) != int(process.pid)),
        supervisor_tree.get("root") or {},
    )
    previous = _read_json(SUPERVISOR_PATH)
    history = previous.get("ownership_history") if isinstance(previous.get("ownership_history"), list) else []
    if previous:
        history = [*history, _historical_ownership_packet(previous)][-10:]
    controller_acknowledgement = {
        "status": "supervisor_identity_acknowledged",
        "generation": generation,
        "startup_nonce": startup_nonce,
        "revision": intended_revision,
        "member_pids": observation["validation"]["member_pids"],
        "acknowledged_at": datetime.now(timezone.utc).isoformat(),
    }
    controller_acknowledgement["signature"] = sign_controller_acknowledgement(
        controller_acknowledgement, controller_private_key
    )
    controller_packet = {
        "version": SUPERVISOR_PACKET_VERSION,
        "pid": interpreter.get("pid"),
        "status": "supervisor_ready",
        "runner_state": "not_spawned",
        "generation": generation,
        "startup_nonce": startup_nonce,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "intended_runtime_revision": intended_revision,
        "intended_execution_revision": intended_revision,
        "controller_public_key": controller_public_key,
        "supervisor_tree_identity": supervisor_tree,
        "controller_acknowledgement": controller_acknowledgement,
        "ownership_history": history,
    }
    atomic_write_json(SUPERVISOR_PATH, controller_packet)
    reread = _read_json(SUPERVISOR_PATH)
    valid, reason = validate_supervisor_packet(
        reread,
        generation,
        intended_revision,
        intended_revision,
        runner_states={"not_spawned"},
        startup_nonce=startup_nonce,
        statuses={"supervisor_ready"},
    )
    if not valid or reread != controller_packet:
        SUPERVISOR_STOP_PATH.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        _write_startup_failure(
            generation, startup_nonce, intended_revision,
            reason if not valid else "controller_packet_reread_mismatch",
            supervisor_tree,
        )
        containment = _contain_spawned_process(process, supervisor_tree)
        return {
            "success": False,
            "status": "ownership_identity_incomplete",
            "reason": reason,
            "containment": containment,
        }, 503
    acknowledgement = _wait_for_supervisor_ack(
        generation,
        intended_revision,
        supervisor_pid=process.pid,
        startup_nonce=startup_nonce,
        controller_private_key=controller_private_key,
        controller_public_key=controller_public_key,
    )
    if not acknowledgement.get("success"):
        SUPERVISOR_STOP_PATH.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        contained, contain_status = stop_runner()
        supervisor_containment = _contain_spawned_process(process, supervisor_tree)
        return {
            "success": False,
            "status": "runner_start_acknowledgement_failed",
            "reason": acknowledgement.get("reason"),
            "generation": generation,
            "supervisor_pid": process.pid,
            "containment": contained,
            "supervisor_containment": supervisor_containment,
        }, max(503, contain_status if supervisor_containment.get("success") else 503)
    return {
        "success": True,
        "status": "runner_started",
        "pid": process.pid,
        "generation": generation,
        "acknowledgement": acknowledgement,
        "command": _display_command(command),
        "log_path": str(LOG_PATH),
    }, 200


def _wait_for_supervisor_ack(
    generation,
    intended_revision,
    supervisor_pid,
    startup_nonce=None,
    controller_private_key=None,
    controller_public_key="",
    timeout_seconds=START_ACK_TIMEOUT_SECONDS,
    poll_seconds=0.1,
    sleep_fn=time.sleep,
):
    deadline = time.monotonic() + max(0, float(timeout_seconds))
    last_reason = "current_generation_packet_not_published"
    while time.monotonic() <= deadline:
        if SUPERVISOR_STOP_PATH.exists():
            return {
                "success": False,
                "reason": "governed_stop_during_start_acknowledgement",
            }
        packet = _read_json(SUPERVISOR_PATH)
        valid, reason = validate_supervisor_packet(
            packet,
            generation=generation,
            runtime_revision=intended_revision,
            execution_revision=intended_revision,
            runner_states={"running"},
            startup_nonce=startup_nonce or generation,
            statuses={"running"},
        )
        if valid:
            heartbeat = _read_json(HEARTBEAT_PATH)
            supervisor_tree = packet.get("supervisor_tree_identity")
            runner_tree = packet.get("process_tree_identity")
            runner_nonce = str(packet.get("runner_startup_nonce") or "")
            runner_ack = packet.get("runner_controller_acknowledgement")
            process_identity = heartbeat.get("process_identity")
            runner_pid = int(heartbeat.get("pid") or -1)
            supervisor_live = validate_live_bootstrap_tree(
                supervisor_tree,
                generation=generation,
                revision=intended_revision,
                startup_nonce=startup_nonce or generation,
            )
            runner_live = validate_live_bootstrap_tree(
                runner_tree,
                generation=generation,
                revision=intended_revision,
                startup_nonce=runner_nonce,
            )
            expected_runner_record = next(
                (
                    item for item in (runner_tree.get("members") or [])
                    if int(item.get("pid") or -2) == runner_pid
                ),
                {},
            ) if isinstance(runner_tree, dict) else {}
            if str(heartbeat.get("status") or "") != "ownership_ready":
                last_reason = "runner_ownership_ready_acknowledgement_missing"
            elif str(heartbeat.get("supervisor_generation") or "") != generation:
                last_reason = "runner_heartbeat_generation_mismatch"
            elif str(heartbeat.get("runner_source_commit") or "") != intended_revision:
                last_reason = "runner_heartbeat_revision_mismatch"
            elif str(heartbeat.get("startup_nonce") or "") != runner_nonce:
                last_reason = "runner_heartbeat_startup_nonce_mismatch"
            elif not isinstance(runner_ack, dict):
                last_reason = "runner_controller_acknowledgement_missing"
            elif any(
                str(runner_ack.get(field) or "") != str(expected)
                for field, expected in {
                    "generation": generation,
                    "startup_nonce": runner_nonce,
                    "revision": intended_revision,
                }.items()
            ):
                last_reason = "runner_controller_acknowledgement_mismatch"
            elif not supervisor_live["authorized"]:
                last_reason = supervisor_live["reason"]
            elif not runner_live["authorized"]:
                last_reason = runner_live["reason"]
            elif int(supervisor_pid) not in set(supervisor_live.get("member_pids") or []):
                last_reason = "supervisor_launcher_pid_not_live"
            elif not expected_runner_record or process_identity != expected_runner_record:
                last_reason = "runner_heartbeat_process_identity_mismatch"
            else:
                if not controller_private_key or not controller_public_key:
                    return {
                        "success": False,
                        "reason": "controller_signing_identity_missing",
                    }
                final_acknowledgement = {
                    "status": "current_process_tree_acknowledged",
                    "generation": generation,
                    "supervisor_startup_nonce": str(startup_nonce or generation),
                    "runner_startup_nonce": runner_nonce,
                    "revision": intended_revision,
                    "supervisor_pid": str(supervisor_pid),
                    "runner_pid": str(runner_pid),
                    "supervisor_member_pids": supervisor_live["member_pids"],
                    "runner_member_pids": runner_live["member_pids"],
                    "acknowledged_at": datetime.now(timezone.utc).isoformat(),
                }
                final_acknowledgement["signature"] = sign_controller_acknowledgement(
                    final_acknowledgement, controller_private_key
                )
                final_packet = {
                    **packet,
                    "status": "running_authorized",
                    "runner_state": "running_authorized",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "controller_public_key": controller_public_key,
                    "controller_final_acknowledgement": final_acknowledgement,
                }
                atomic_write_json(SUPERVISOR_PATH, redact_payload(final_packet))
                if _read_json(SUPERVISOR_PATH) != redact_payload(final_packet):
                    return {"success": False, "reason": "final_acknowledgement_reread_mismatch"}
                return {
                    "success": True,
                    "status": "current_generation_acknowledged",
                    "generation": generation,
                    "supervisor_pid": supervisor_pid,
                    "runner_pid": runner_pid,
                }
        else:
            last_reason = reason
        if not _pid_alive(supervisor_pid):
            return {"success": False, "reason": "supervisor_exited_before_acknowledgement"}
        sleep_fn(poll_seconds)
    return {"success": False, "reason": last_reason}


def _contain_started_supervisor(supervisor_pid, generation, inspector=inspect_process):
    # A current PID inspection cannot establish that the inspected process is
    # the one originally spawned.  Callers must retain the Popen handle and
    # controller-observed tree; this legacy helper is now denial-only.
    record = {}
    decision = {
        "authorized": False,
        "reason": "controller_observed_supervisor_identity_required",
    }
    evidence = {
        "version": "charlie_start_containment_evidence_v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "generation": str(generation or ""),
        "supervisor_identity": record,
        "success": bool(decision.get("terminated")),
        "reason": decision.get("reason") or (
            "exact_supervisor_tree_terminated" if decision.get("terminated") else "termination_not_confirmed"
        ),
        "termination": decision,
        "stop_marker_present": SUPERVISOR_STOP_PATH.exists(),
    }
    atomic_write_json(START_CONTAINMENT_PATH, evidence)
    return evidence


def stop_runner():
    if emergency_process_cleanup_disabled():
        refusal = record_emergency_cleanup_refusal("stop_runner", "all")
        return {"success": False, **refusal}, 423
    if not process_termination_enabled():
        return {"success": False, "status": "process_termination_not_enabled"}, 423
    status = runner_status()
    RUNNER_DIR.mkdir(parents=True, exist_ok=True)
    SUPERVISOR_STOP_PATH.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    supervisor = _read_json(SUPERVISOR_PATH)
    root = supervisor.get("child_identity")
    heartbeat = _read_json(HEARTBEAT_PATH)
    interpreter = heartbeat.get("process_identity")
    if (not isinstance(root, dict) or not root.get("pid")) and isinstance(interpreter, dict):
        current = inspect_process(interpreter.get("pid"))
        ancestry = current.get("ancestry") if isinstance(current, dict) else []
        launcher_pid = int(supervisor.get("child_pid") or 0)
        launcher = next(
            (
                item for item in ancestry
                if isinstance(item, dict)
                and int(item.get("pid") or -1) == launcher_pid
            ),
            None,
        )
        if launcher:
            root = make_ownership_record(
                launcher,
                interpreter.get("runner_generation"),
                interpreter.get("mission_id"),
                interpreter.get("execution_id"),
                interpreter.get("ownership_type"),
            )
    members = [
        item for item in (root, interpreter)
        if isinstance(item, dict) and item.get("pid")
    ]
    tree = (
        make_process_tree_record(root, members, supervisor.get("generation"))
        if isinstance(root, dict) else {}
    )
    target_kind = "runner"
    if not tree:
        supervisor_tree = supervisor.get("supervisor_tree_identity")
        if isinstance(supervisor_tree, dict) and supervisor_tree.get("root"):
            tree = supervisor_tree
            root = supervisor_tree.get("root")
            target_kind = "supervisor"
    if not tree:
        if status.get("orphan_processes"):
            result = {
                "success": False,
                "status": "runner_process_ownership_not_proven",
                "reason": "process_tree_metadata_missing",
                "pids": [],
            }
            _write_stop_evidence(supervisor, tree, result)
            return result, 409
        prior = supervisor.get("stop_evidence") if isinstance(supervisor.get("stop_evidence"), dict) else {}
        if prior.get("status") in {"runner_stop_requested", "runner_already_stopped"}:
            return {"success": True, "status": "runner_already_stopped", "stop_evidence": prior}, 200
        return {"success": True, "status": "runner_not_started", "runner": status}, 200
    expected = {
        field: root.get(field)
        for field in ("runner_generation", "mission_id", "execution_id", "ownership_type")
    }
    decision = validate_process_tree(
        tree,
        expected,
        inspect_process,
        require_descendant=os.name == "nt",
        allow_current_descendant=target_kind == "supervisor",
    )
    if not decision["authorized"]:
        result = {
            "success": False,
            "status": "runner_process_ownership_not_proven",
            "reason": decision["reason"],
            "pids": [],
        }
        _write_stop_evidence(supervisor, tree, result)
        return result, 409
    stopped = []
    termination = {}
    try:
        termination = _stop_process_tree(
            root,
            expected,
            allow_current_descendant=target_kind == "supervisor",
        )
        if termination.get("terminated"):
            stopped.append(int(root["pid"]))
    except OSError:
        if not stopped:
            return {"success": True, "status": "runner_already_stopped", "runner": status}, 200
    if not stopped:
        result = {
            "success": False,
            "status": "runner_process_ownership_not_proven",
            "reason": termination.get("reason", "termination_not_confirmed"),
            "pids": [],
        }
        _write_stop_evidence(supervisor, tree, result)
        return result, 409
    result = {
        "success": True,
        "status": "runner_stop_requested",
        "pids": stopped,
        "target_kind": target_kind,
        "logical_process_tree": decision,
    }
    _write_stop_evidence(supervisor, tree, result)
    return result, 200


def _write_stop_evidence(supervisor, tree, result):
    payload = dict(supervisor) if isinstance(supervisor, dict) else {}
    payload["process_tree_identity"] = tree
    payload["stop_evidence"] = {
        "version": "charlie_governed_stop_evidence_v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "stop_marker_present": SUPERVISOR_STOP_PATH.exists(),
        "status": result.get("status"),
        "success": bool(result.get("success")),
        "reason": result.get("reason") or (
            (result.get("logical_process_tree") or {}).get("reason")
        ),
        "target_pids": result.get("pids") or [],
        "process_tree_identity": tree,
    }
    atomic_write_json(SUPERVISOR_PATH, payload)
    return payload["stop_evidence"]


def _stop_process_tree(
    ownership_record,
    expected_ownership=None,
    inspector=inspect_process,
    allow_current_descendant=False,
):
    if emergency_process_cleanup_disabled():
        requested_pid = ownership_record.get("pid") if isinstance(ownership_record, dict) else ownership_record
        return record_emergency_cleanup_refusal("_stop_process_tree", requested_pid)
    if not process_termination_enabled():
        return {"authorized": False, "reason": "process_termination_not_enabled"}
    decision = validate_termination(
        ownership_record,
        expected_ownership,
        inspector,
        allow_current_descendant=allow_current_descendant,
    )
    if not decision["authorized"]:
        return decision
    pid = decision["pid"]
    if os.name == "nt":
        completed = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
            **background_run_kwargs(),
        )
        if completed.returncode not in (0, 128):
            return {
                "authorized": True,
                "terminated": False,
                "pid": pid,
                "reason": "process_tree_termination_failed",
            }
    else:
        os.kill(pid, signal.SIGTERM)
    for _attempt in range(50):
        try:
            current = inspector(pid)
        except Exception:
            current = None
        if not isinstance(current, dict) or int(current.get("pid") or -1) != pid:
            return {"authorized": True, "terminated": True, "pid": pid}
        time.sleep(0.1)
    return {
        "authorized": True,
        "terminated": False,
        "pid": pid,
        "reason": "process_tree_termination_not_verified",
    }


def cleanup_runner_environment(stop_stale=True, prune_worktrees=True):
    if emergency_process_cleanup_disabled():
        refusal = record_emergency_cleanup_refusal("cleanup_runner_environment", "all")
        return {"success": False, **refusal, "actions": []}, 423
    status = runner_status()
    actions = []
    stop_result = {}
    should_stop = (
        bool(stop_stale)
        and status.get("status") in {"runner_orphaned", "runner_code_stale", "runner_stale_or_stopped"}
        and (status.get("process_alive") or status.get("orphan_processes"))
    )
    if status.get("active"):
        actions.append({"action": "stop_runner", "status": "skipped_active_runner"})
    elif should_stop:
        stop_result, stop_status = stop_runner()
        actions.append({"action": "stop_runner", "status_code": stop_status, "result": stop_result})
    else:
        actions.append({"action": "stop_runner", "status": "not_required"})

    prune_result = {"status": "skipped"}
    if prune_worktrees:
        prune_result = _git_worktree_prune()
        actions.append({"action": "git_worktree_prune", "result": prune_result})

    prune_ok = prune_result.get("status") == "ok"
    return {
        "success": not any(
            int(action.get("status_code") or 200) >= 400
            for action in actions
            if isinstance(action, dict)
        ) and prune_ok,
        "status": "cleanup_complete" if prune_ok else "cleanup_partial_failure",
        "runner_before": status,
        "actions": actions,
        "execution_boundary": "Cleanup only stops stale/orphaned/code-stale runner processes and prunes git worktree metadata; it does not delete repo work or active review media.",
    }, 200 if prune_ok else 500


def _display_command(command=None):
    command = command or RUNNER_COMMAND
    return " ".join(command).replace(str(REPO_ROOT) + "\\", "")


def _current_git_commit():
    # The deployed branch is authoritative. A dirty or intentionally divergent
    # primary checkout must not make a healthy dedicated runner look stale.
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "refs/remotes/origin/main"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(CONTROL_ROOT),
            timeout=10,
            check=False,
            **background_run_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if completed.returncode == 0:
        return completed.stdout.strip()
    try:
        fallback = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(REPO_ROOT),
            timeout=10,
            check=False,
            **background_run_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return fallback.stdout.strip() if fallback.returncode == 0 else ""


def _current_git_branch():
    try:
        completed = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(REPO_ROOT),
            timeout=10,
            check=False,
            **background_run_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _git_worktree_prune():
    try:
        completed = subprocess.run(
            ["git", "worktree", "prune"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(REPO_ROOT),
            timeout=30,
            check=False,
            **background_run_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "failed", "error_type": exc.__class__.__name__, "error": str(exc)[:500]}
    stderr = completed.stderr or ""
    partial_failure = "permission denied" in stderr.lower() or "failed to delete" in stderr.lower()
    return {
        "status": "partial_failure" if completed.returncode == 0 and partial_failure else "ok" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "stdout_tail": (completed.stdout or "")[-1000:],
        "stderr_tail": stderr[-1000:],
    }


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def atomic_write_json(path, payload, replace_fn=os.replace):
    """Replace one durable JSON packet without exposing a partial document."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        replace_fn(str(temporary), str(path))
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return payload


def validate_supervisor_packet(
    packet,
    generation,
    runtime_revision,
    execution_revision,
    runner_states=None,
    startup_nonce=None,
    statuses=None,
):
    if not isinstance(packet, dict) or not packet:
        return False, "supervisor_packet_missing"
    checks = (
        ("version", SUPERVISOR_PACKET_VERSION),
        ("generation", str(generation or "")),
        ("intended_runtime_revision", str(runtime_revision or "")),
        ("intended_execution_revision", str(execution_revision or "")),
        ("startup_nonce", str(startup_nonce or generation or "")),
    )
    for field, expected in checks:
        if not expected or str(packet.get(field) or "") != expected:
            return False, f"supervisor_packet_{field}_mismatch"
    if not str(packet.get("created_at") or ""):
        return False, "supervisor_packet_creation_timestamp_missing"
    tree = packet.get("supervisor_tree_identity")
    tree_decision = validate_bootstrap_tree(
        tree,
        generation=generation,
        revision=runtime_revision,
        startup_nonce=startup_nonce or generation,
        require_interpreter=True,
    )
    if not tree_decision["authorized"]:
        return False, tree_decision["reason"]
    if runner_states is not None and str(packet.get("runner_state") or "") not in set(runner_states):
        return False, "supervisor_packet_runner_state_invalid"
    if statuses is not None and str(packet.get("status") or "") not in set(statuses):
        return False, "supervisor_packet_status_invalid"
    return True, "supervisor_packet_valid"


def _historical_ownership_packet(packet):
    return redact_payload({
        key: packet.get(key)
        for key in (
            "version", "generation", "startup_nonce", "created_at", "updated_at",
            "status", "runner_state", "supervisor_tree_identity",
            "process_tree_identity", "stop_evidence",
        )
        if key in packet
    })


def _write_startup_failure(generation, startup_nonce, revision, reason, tree):
    evidence = {
        "version": "charlie_start_containment_evidence_v2",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "generation": str(generation or ""),
        "startup_nonce": str(startup_nonce or ""),
        "revision": str(revision or ""),
        "status": "ownership_identity_incomplete",
        "reason": str(reason or "ownership_identity_incomplete"),
        "process_tree_identity": tree if isinstance(tree, dict) else {},
        "stop_marker_present": SUPERVISOR_STOP_PATH.exists(),
    }
    evidence = redact_payload(evidence)
    atomic_write_json(START_CONTAINMENT_PATH, evidence)
    return evidence


def _contain_observed_tree(tree):
    root = tree.get("root") if isinstance(tree, dict) else {}
    if not isinstance(root, dict) or not root.get("pid"):
        return {"success": False, "reason": "ownership_identity_incomplete:root.pid"}
    members = tree.get("members") if isinstance(tree.get("members"), list) else []
    decisions = []
    terminated_pids = []
    for record in [root, *[
        item for item in members
        if isinstance(item, dict) and item.get("pid") != root.get("pid")
    ]]:
        expected = {
            field: record.get(field)
            for field in ("runner_generation", "mission_id", "execution_id", "ownership_type")
        }
        decision = _stop_process_tree(
            record,
            expected,
            allow_current_descendant=record is root,
        )
        decisions.append(decision)
        if decision.get("terminated"):
            terminated_pids.append(int(record["pid"]))
    survivors = []
    for record in members:
        current = inspect_process(record.get("pid"))
        if (
            isinstance(current, dict)
            and str(current.get("creation_time") or "")
            == str(record.get("creation_time") or "")
        ):
            survivors.append(int(record["pid"]))
    if not survivors and (terminated_pids or decisions):
        return {
            "success": True,
            "reason": "observed_process_tree_termination_verified",
            "terminated_pids": sorted(set(terminated_pids)),
            "termination": decisions[-1] if decisions else {},
            "attempts": decisions,
        }
    return {
        "success": False,
        "reason": (
            f"observed_process_tree_survivors:{','.join(map(str, survivors))}"
            if survivors
            else decisions[-1].get("reason") if decisions else "termination_not_confirmed"
        ),
        "termination": decisions[-1] if decisions else {},
        "attempts": decisions,
    }


def _contain_spawned_process(process, observed_tree):
    """Contain a freshly returned Popen handle even when inspection was partial."""
    observed = _contain_observed_tree(observed_tree)
    if observed.get("success"):
        return observed
    pid = int(getattr(process, "pid", 0) or 0)
    if pid <= 0:
        return {
            "success": False,
            "reason": "spawned_process_handle_incomplete",
            "observed_containment": observed,
        }
    try:
        if getattr(process, "poll", lambda: None)() is not None:
            return {
                "success": False,
                "reason": "spawned_process_exited_before_containment",
                "pid": pid,
                "observed_containment": observed,
            }
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
                **background_run_kwargs(),
            )
        else:
            process.terminate()
        process.wait(timeout=15)
    except (OSError, subprocess.SubprocessError, TimeoutError):
        try:
            process.kill()
            process.wait(timeout=10)
        except (OSError, subprocess.SubprocessError, TimeoutError):
            return {
                "success": False,
                "reason": "spawned_process_termination_not_verified",
                "pid": pid,
                "observed_containment": observed,
            }
    if getattr(process, "poll", lambda: None)() is None:
        return {
            "success": False,
            "reason": "spawned_process_termination_not_verified",
            "pid": pid,
            "observed_containment": observed,
        }
    return {
        "success": True,
        "reason": "fresh_spawn_handle_tree_termination_verified",
        "pid": pid,
        "observed_containment": observed,
    }


def _execution_artifact_exists(path):
    raw_path = str(path or "").strip()
    if not raw_path:
        return False
    artifact_path = Path(raw_path)
    if not artifact_path.is_absolute():
        artifact_path = REPO_ROOT / artifact_path
    try:
        return artifact_path.exists() and artifact_path.stat().st_size > 0
    except OSError:
        return False


def _read_agent_ledger_summary(path):
    raw_path = str(path or "").strip()
    if not raw_path:
        return {}
    try:
        ledger_path = Path(raw_path).resolve()
        root = REPO_ROOT.resolve()
        execution_root = (RUNNER_DIR / "core-execution-current").resolve()
        allowed_roots = (root, execution_root)
        if not any(candidate == ledger_path or candidate in ledger_path.parents for candidate in allowed_roots):
            return {"status": "ledger_path_outside_repo"}
        ledger = _read_json(ledger_path)
    except (OSError, ValueError):
        return {"status": "ledger_unavailable"}
    stages = ledger.get("stages") if isinstance(ledger.get("stages"), list) else []
    latest = stages[-1] if stages else {}
    return {
        "version": ledger.get("version", ""),
        "execution_id": ledger.get("execution_id", ""),
        "status": ledger.get("status", ""),
        "last_progress_at": ledger.get("last_progress_at", ""),
        "blocked_agent": ledger.get("blocked_agent", ""),
        "blocked_reason": ledger.get("blocked_reason", ""),
        "backflow_events": ledger.get("backflow_events", [])[-5:] if isinstance(ledger.get("backflow_events"), list) else [],
        "latest_stage": {
            "agent": latest.get("agent", ""),
            "status": latest.get("status", ""),
            "attempt": latest.get("attempt", 1),
            "current_action": latest.get("current_action", ""),
            "commands_run": latest.get("commands_run", [])[-5:] if isinstance(latest.get("commands_run"), list) else [],
            "files_inspected": latest.get("files_inspected", [])[-8:] if isinstance(latest.get("files_inspected"), list) else [],
            "changed_files": latest.get("changed_files", [])[-8:] if isinstance(latest.get("changed_files"), list) else [],
            "stdout_tail": str(latest.get("stdout_tail", ""))[-800:],
            "stderr_tail": str(latest.get("stderr_tail", ""))[-800:],
            "quality_gate": latest.get("quality_gate", {}) if isinstance(latest.get("quality_gate"), dict) else {},
        },
    }


def _parse_iso(value):
    try:
        return datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None


def _pid_alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        return _pid_alive_windows(pid)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _pid_alive_windows(pid):
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return False

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    SYNCHRONIZE = 0x00100000
    WAIT_TIMEOUT = 0x00000102
    STILL_ACTIVE = 259

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
    if not handle:
        # Scheduled tasks can run under a different Windows token. OpenProcess
        # may be denied even though the exact PID is alive, so use tasklist as
        # a read-only existence fallback before declaring the runner dead.
        return _pid_exists_windows_tasklist(pid)
    try:
        wait_result = kernel32.WaitForSingleObject(handle, 0)
        if wait_result == WAIT_TIMEOUT:
            return True
        exit_code = wintypes.DWORD()
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return exit_code.value == STILL_ACTIVE
        return False
    finally:
        kernel32.CloseHandle(handle)


def _pid_exists_windows_tasklist(pid, runner=subprocess.run):
    try:
        completed = runner(
            ["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if completed.returncode != 0:
            return False
        rows = list(csv.reader(str(completed.stdout or "").splitlines()))
        return any(len(row) > 1 and row[1].strip() == str(int(pid)) for row in rows)
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def _pid_descends_from(pid, ancestor_pid):
    try:
        pid = int(pid)
        ancestor_pid = int(ancestor_pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0 or ancestor_pid <= 0 or pid == ancestor_pid:
        return pid == ancestor_pid and pid > 0
    if os.name == "nt":
        script = (
            f"$current={pid}; $ancestor={ancestor_pid}; $seen=@{{}}; "
            "$rows=Get-CimInstance Win32_Process -ErrorAction SilentlyContinue; $parents=@{}; "
            "foreach($item in $rows){ $parents[[int]$item.ProcessId]=[int]$item.ParentProcessId }; "
            "for($i=0; $i -lt 12; $i++){ "
            "if($seen.ContainsKey($current)){ break }; $seen[$current]=$true; "
            "if(-not $parents.ContainsKey($current)){ break }; $parent=[int]$parents[$current]; "
            "if($parent -eq $ancestor){ Write-Output 'true'; exit 0 }; "
            "if($parent -le 0){ break }; $current=$parent }; Write-Output 'false'"
        )
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return completed.returncode == 0 and completed.stdout.strip().lower().endswith("true")
    current = pid
    for _ in range(12):
        try:
            fields = Path(f"/proc/{current}/stat").read_text(encoding="utf-8").split()
            parent = int(fields[3])
        except (OSError, ValueError, IndexError):
            return False
        if parent == ancestor_pid:
            return True
        if parent <= 1 or parent == current:
            return False
        current = parent
    return False


def _find_runner_processes():
    if os.name == "nt":
        return _find_runner_processes_windows()
    return _find_runner_processes_posix()


def _find_runner_processes_windows():
    script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -like 'python*' -and "
        "$_.CommandLine -like '*charlie_mission_pickup.py*' -and "
        "$_.CommandLine -like '*--watch*' -and "
        "$_.CommandLine -like '*--continuous*' } | "
        "Select-Object ProcessId,ParentProcessId,CommandLine | "
        "ConvertTo-Json -Depth 4"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    try:
        loaded = json.loads(completed.stdout)
    except ValueError:
        return []
    rows = loaded if isinstance(loaded, list) else [loaded]
    return [
        {
            "pid": row.get("ProcessId"),
            "parent_pid": row.get("ParentProcessId"),
            "command": row.get("CommandLine", ""),
        }
        for row in rows
        if isinstance(row, dict) and row.get("ProcessId") != os.getpid()
    ]


def _find_runner_processes_posix():
    try:
        completed = subprocess.run(
            ["ps", "-eo", "pid=,ppid=,command="],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    processes = []
    for line in completed.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        pid, parent_pid, command = parts
        if (
            pid.isdigit()
            and int(pid) != os.getpid()
            and "charlie_mission_pickup.py" in command
            and "--watch" in command
            and "--continuous" in command
        ):
            processes.append({"pid": int(pid), "parent_pid": int(parent_pid), "command": command})
    return processes
