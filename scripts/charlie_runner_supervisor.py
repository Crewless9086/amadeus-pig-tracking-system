import json
import csv
import os
import signal
import subprocess
import sys
import time
import uuid
import ctypes
import hashlib
from urllib.parse import urlsplit, urlunsplit
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from modules.charlie.process_policy import background_process_kwargs, background_run_kwargs
from modules.charlie.environment import env_value
from modules.charlie.repository_guard import RepositoryOperationLock, repository_lock_path
from modules.charlie.runner_control import (
    _contain_spawned_process,
    RUNNER_DIR,
    SUPERVISOR_PACKET_VERSION,
    _contain_observed_tree,
    atomic_write_json,
    validate_supervisor_packet,
)
from modules.charlie.runner_control import emergency_process_cleanup_disabled, record_emergency_cleanup_refusal
from modules.charlie.process_ownership import (
    inspect_process,
    generate_controller_signing_key,
    make_ownership_record,
    make_process_tree_record,
    observe_process_tree,
    process_termination_enabled,
    process_tree_identity_digest,
    sign_controller_acknowledgement,
    validate_bootstrap_tree,
    validate_live_bootstrap_tree,
    validate_termination,
    verify_controller_acknowledgement,
)
from modules.charlie.secret_redaction import redact_payload, redact_tree_in_place
EXECUTION_ROOT = Path(env_value("CORE_EXECUTION_ROOT") or (RUNNER_DIR / "core-execution-current")).resolve()
SUPERVISOR_PATH = RUNNER_DIR / "supervisor.json"
STOP_PATH = RUNNER_DIR / "supervisor.stop"
LOCK_PATH = RUNNER_DIR / "supervisor.lock"
RUNNER_HEARTBEAT_PATH = RUNNER_DIR / "runner.json"
INFRASTRUCTURE_FAILURE_LIMIT = 3
EXECUTION_BASE_BRANCH = "charlie-core-execution-base"
NON_RETRYABLE_RUNNER_STATUSES = {
    "base_branch_checkout_failed",
    "base_branch_current_failed",
    "base_branch_switch_failed",
    "base_branch_verify_failed",
    "git_operation_in_progress",
    "git_operation_marker_check_failed",
    "git_operation_marker_permission_denied",
    "git_operation_marker_remove_failed",
    "repository_operation_locked",
    "runner_preflight_failed",
}
_TEST_CONTROLLER_SIGNING_KEY = None
GENERATED_EXECUTION_PATHS = {"planning/CODEX_CHAT.md"}


class SupervisorInstanceLock:
    """Atomic, process-owned guard against duplicate local supervisors."""

    def __init__(self, path=LOCK_PATH):
        self.path = Path(path)
        self.owned = False
        self.mutex_handle = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            acquired, handle = _acquire_windows_supervisor_mutex(self.path)
            if not acquired:
                return False, 0
            self.mutex_handle = handle
        for _attempt in range(2):
            try:
                descriptor = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                owner_pid = _lock_owner_pid(self.path)
                if owner_pid and _pid_alive(owner_pid):
                    self._release_mutex()
                    return False, owner_pid
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    self._release_mutex()
                    return False, owner_pid
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump({"pid": os.getpid(), "created_at": datetime.now(timezone.utc).isoformat()}, stream)
            self.owned = True
            return True, os.getpid()
        self._release_mutex()
        return False, _lock_owner_pid(self.path)

    def release(self):
        if not self.owned:
            return
        try:
            if _lock_owner_pid(self.path) == os.getpid():
                self.path.unlink()
        except FileNotFoundError:
            pass
        finally:
            self.owned = False
            self._release_mutex()

    def _release_mutex(self):
        if self.mutex_handle and os.name == "nt":
            ctypes.windll.kernel32.CloseHandle(self.mutex_handle)
        self.mutex_handle = None


def _acquire_windows_supervisor_mutex(path, kernel32=None):
    kernel32 = kernel32 or ctypes.windll.kernel32
    digest = hashlib.sha256(str(Path(path).resolve()).lower().encode("utf-8")).hexdigest()[:24]
    handle = kernel32.CreateMutexW(None, False, f"Local\\CHARLIE_CORE_SUPERVISOR_{digest}")
    if not handle:
        return False, None
    if kernel32.GetLastError() == 183:
        kernel32.CloseHandle(handle)
        return False, None
    return True, handle


def _windowless_process_kwargs(platform_name=None):
    return background_process_kwargs(platform_name)


def _lock_owner_pid(path=LOCK_PATH):
    try:
        return int(json.loads(Path(path).read_text(encoding="utf-8")).get("pid") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return 0


def _transaction_pool_url(value):
    """Use Supabase's transaction pool for long-lived local runner processes."""
    raw = str(value or "").strip()
    if not raw:
        return raw
    try:
        parsed = urlsplit(raw)
        if not parsed.hostname or not parsed.hostname.endswith(".pooler.supabase.com") or parsed.port != 5432:
            return raw
        if not parsed.netloc.endswith(":5432"):
            return raw
        netloc = f"{parsed.netloc[:-5]}:6543"
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    except (ValueError, TypeError):
        return raw


def _python_executable(repo_root=REPO_ROOT):
    candidates = [
        Path(repo_root) / "venv" / "Scripts" / "python.exe",
        Path(repo_root).parents[1] / "venv" / "Scripts" / "python.exe",
    ]
    return str(next((path for path in candidates if path.exists()), Path(sys.executable)))


RUNNER_COMMAND = [
    _python_executable(),
    str(EXECUTION_ROOT / "scripts" / "charlie_mission_pickup.py"),
    "--watch", "--continuous", "--notify", "--execute-codex", "--watch-release",
    "--auto-merge-pr", "--release-verify-url",
    "https://amadeus-pig-tracking-system.onrender.com/charlie", "--interval-seconds", "30",
]


def supervise_runner(
    popen_factory=subprocess.Popen,
    sleep_fn=time.sleep,
    max_cycles=None,
    notifier=None,
    prepare_fn=None,
    generation=None,
    acknowledgement_fn=None,
    recovery_fn=None,
):
    RUNNER_DIR.mkdir(parents=True, exist_ok=True)
    if STOP_PATH.exists():
        return {"status": "governed_stop_active", "runner_state": "not_spawned"}
    generation = str(generation or os.getenv("CHARLIE_SUPERVISOR_GENERATION") or uuid.uuid4().hex)
    startup_nonce = str(os.getenv("CHARLIE_STARTUP_NONCE") or uuid.uuid4().hex)
    execution_mode = str(os.getenv("CHARLIE_CORE_EXECUTION_MODE") or "ordinary").strip().lower()
    if execution_mode not in {"ordinary", "observe_only"}:
        return {"status": "infrastructure_hold", "failure_status": "execution_mode_invalid"}
    test_mode = popen_factory is not subprocess.Popen
    controller_public_key = str(os.getenv("CHARLIE_CONTROLLER_PUBLIC_KEY") or "")
    test_controller_private_key = None
    if test_mode and not controller_public_key:
        global _TEST_CONTROLLER_SIGNING_KEY
        if _TEST_CONTROLLER_SIGNING_KEY is None:
            _TEST_CONTROLLER_SIGNING_KEY = generate_controller_signing_key()
        test_controller_private_key, controller_public_key = _TEST_CONTROLLER_SIGNING_KEY
    actual_runtime_revision = _git_revision(REPO_ROOT)
    actual_execution_revision = _git_revision(EXECUTION_ROOT)
    runtime_revision = str(os.getenv("CHARLIE_INTENDED_RUNTIME_REVISION") or actual_runtime_revision)
    execution_revision = str(os.getenv("CHARLIE_INTENDED_EXECUTION_REVISION") or actual_execution_revision)
    if test_mode:
        runtime_revision = runtime_revision or "test-revision"
        execution_revision = execution_revision or "test-revision"
    if test_mode and not _read_status():
        _write_test_controller_packet(
            generation,
            startup_nonce,
            runtime_revision,
            execution_revision,
            controller_public_key,
            test_controller_private_key,
            execution_mode,
        )
    controller = _wait_for_controller_ack(
        generation,
        startup_nonce,
        runtime_revision,
        execution_revision,
        controller_public_key=controller_public_key,
        execution_mode=execution_mode,
        live_validate=not test_mode,
        sleep_fn=sleep_fn,
    )
    if not controller.get("success"):
        _write_status(
            "infrastructure_hold",
            generation=generation,
            startup_nonce=startup_nonce,
            intended_runtime_revision=runtime_revision,
            intended_execution_revision=execution_revision,
            runner_state="not_spawned",
            execution_mode=execution_mode,
            failure_status=controller.get("reason") or "ownership_identity_incomplete",
            failure_detail=controller,
        )
        return {
            "status": "infrastructure_hold",
            "failure_status": controller.get("reason") or "ownership_identity_incomplete",
        }
    if not test_mode and (
        actual_runtime_revision != runtime_revision
        or actual_execution_revision != execution_revision
    ):
        _write_status(
            "infrastructure_hold",
            generation=generation,
            startup_nonce=startup_nonce,
            intended_runtime_revision=runtime_revision,
            intended_execution_revision=execution_revision,
            runner_state="not_spawned",
            failure_status="startup_revision_mismatch",
            failure_detail={
                "actual_runtime_revision": actual_runtime_revision,
                "actual_execution_revision": actual_execution_revision,
            },
        )
        return {"status": "infrastructure_hold", "failure_status": "startup_revision_mismatch"}
    restart_count = 0
    cycles = 0
    repeated_failure = ""
    repeated_failure_count = 0
    while not STOP_PATH.exists():
        cycles += 1
        bootstrap = (prepare_fn or _prepare_execution_root)()
        if not bootstrap.get("success"):
            payload = _write_status(
                "infrastructure_hold",
                child_pid=0,
                restart_count=restart_count,
                failure_status=bootstrap.get("status", "execution_bootstrap_failed"),
                failure_detail=bootstrap,
                identical_failure_count=1,
                generation=generation,
                recommended_action=bootstrap.get("recommended_action") or "Repair the dedicated execution checkout, then explicitly restart CORE.",
            )
            if notifier:
                notifier(payload)
            return {
                "status": "infrastructure_hold",
                "restart_count": restart_count,
                "cycles": cycles,
                "failure_status": bootstrap.get("status", "execution_bootstrap_failed"),
                "bootstrap": bootstrap,
            }
        scrub_results = [
            redact_tree_in_place(RUNNER_HEARTBEAT_PATH),
            redact_tree_in_place(RUNNER_DIR / "runner.log"),
            redact_tree_in_place(EXECUTION_ROOT / ".charlie_runner" / "executions"),
        ]
        scrub_errors = [error for result in scrub_results for error in result.get("errors", [])]
        if scrub_errors:
            payload = _write_status(
                "infrastructure_hold",
                child_pid=0,
                restart_count=restart_count,
                failure_status="secret_scrub_failed",
                failure_detail={"errors": scrub_errors},
                identical_failure_count=1,
                generation=generation,
                recommended_action="Repair runtime evidence permissions and rerun secret scrubbing before CORE starts.",
            )
            if notifier:
                notifier(payload)
            return {"status": "infrastructure_hold", "failure_status": "secret_scrub_failed", "scrub_results": scrub_results}
        if execution_mode == "observe_only":
            child_env = {
                key: os.environ[key]
                for key in (
                    "PATH",
                    "PATHEXT",
                    "SYSTEMROOT",
                    "WINDIR",
                    "COMSPEC",
                    "TEMP",
                    "TMP",
                    "GIT_CONFIG_GLOBAL",
                )
                if os.environ.get(key)
            }
        else:
            child_env = dict(os.environ)
            child_env["DATABASE_URL"] = _transaction_pool_url(
                child_env.get("DATABASE_URL")
            )
        child_env.update({
            "CHARLIE_SUPERVISOR_GENERATION": generation,
            "CHARLIE_STARTUP_NONCE": startup_nonce,
            "CHARLIE_CORE_EXECUTION_MODE": execution_mode,
            "GIT_CONFIG_GLOBAL": os.environ.get("GIT_CONFIG_GLOBAL", ""),
        })
        # The legacy alias can still be present in the scheduled-task
        # environment.  Child configuration is a single supervisor-owned
        # value, so keep both names identical instead of triggering the
        # fail-closed alias conflict before mission pickup.
        child_env["CORE_EXECUTION_BASE_BRANCH"] = EXECUTION_BASE_BRANCH
        child_env["CHARLIE_RUNNER_BASE_BRANCH"] = EXECUTION_BASE_BRANCH
        if STOP_PATH.exists():
            _write_status(
                "supervisor_stopped", generation=generation,
                intended_runtime_revision=runtime_revision,
                intended_execution_revision=execution_revision,
                runner_state="not_spawned", child_pid=0,
            )
            break
        runner_nonce = uuid.uuid4().hex
        child_env["CHARLIE_RUNNER_STARTUP_NONCE"] = runner_nonce
        runner_command = (
            [RUNNER_COMMAND[0], str(REPO_ROOT / "scripts" / "charlie_observe_only_runner.py")]
            if execution_mode == "observe_only"
            else list(RUNNER_COMMAND)
        )
        child = popen_factory(runner_command, cwd=str(EXECUTION_ROOT), env=child_env, **_windowless_process_kwargs())
        if test_mode:
            runner_observation = _test_runner_observation(
                child.pid, generation, execution_revision, runner_nonce
            )
        else:
            runner_observation = observe_process_tree(
                child.pid,
                generation=generation,
                revision=execution_revision,
                startup_nonce=runner_nonce,
                expected_script=Path(runner_command[1]).name,
                expected_root_executable=RUNNER_COMMAND[0],
                process_role_prefix="runner",
            )
        if not runner_observation.get("success"):
            STOP_PATH.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
            containment = _contain_spawned_process(
                child, runner_observation.get("tree") or {}
            )
            _write_status(
                "infrastructure_hold",
                generation=generation,
                startup_nonce=startup_nonce,
                intended_runtime_revision=runtime_revision,
                intended_execution_revision=execution_revision,
                runner_state="containment_required",
                failure_status=runner_observation.get("reason") or "ownership_identity_incomplete",
                failure_detail={**runner_observation, "containment": containment},
            )
            return {
                "status": "infrastructure_hold",
                "failure_status": runner_observation.get("reason") or "ownership_identity_incomplete",
            }
        runner_tree = runner_observation["tree"]
        child_identity = runner_tree["root"]
        _write_status(
            "runner_starting", child_pid=child.pid, child_identity=child_identity,
            process_tree_identity=runner_tree,
            restart_count=restart_count, generation=generation,
            intended_runtime_revision=runtime_revision,
            intended_execution_revision=execution_revision,
            runner_state="runner_starting",
            execution_mode=execution_mode,
            runner_startup_nonce=runner_nonce,
            runner_controller_acknowledgement={
                "status": "runner_identity_acknowledged",
                "generation": generation,
                "startup_nonce": runner_nonce,
                "revision": execution_revision,
                "execution_mode": execution_mode,
                "member_pids": runner_observation["validation"]["member_pids"],
                "runner_tree_digest": process_tree_identity_digest(runner_tree),
                "acknowledged_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        waiter = acknowledgement_fn
        if waiter is None:
            waiter = _wait_for_runner_ack if popen_factory is subprocess.Popen else _test_acknowledgement
        acknowledgement = waiter(
            child,
            generation,
            runtime_revision,
            execution_revision,
            runner_nonce=runner_nonce,
            sleep_fn=sleep_fn,
        )
        if not acknowledgement.get("success"):
            STOP_PATH.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
            containment = _contain_spawned_process(child, runner_tree)
            _write_status(
                "infrastructure_hold",
                child_pid=child.pid,
                child_identity=child_identity,
                restart_count=restart_count,
                generation=generation,
                intended_runtime_revision=runtime_revision,
                intended_execution_revision=execution_revision,
                runner_state="containment_required",
                failure_status="runner_acknowledgement_failed",
                failure_detail={
                    "acknowledgement": acknowledgement,
                    "containment": containment,
                },
            )
            return {
                "status": "infrastructure_hold",
                "failure_status": "runner_acknowledgement_failed",
                "acknowledgement": acknowledgement,
                "containment": containment,
            }
        _write_status(
            "running",
            child_pid=child.pid,
            child_identity=child_identity,
            process_tree_identity=acknowledgement.get("process_tree_identity"),
            restart_count=restart_count,
            generation=generation,
            intended_runtime_revision=runtime_revision,
            intended_execution_revision=execution_revision,
            runner_state="running",
            runner_acknowledgement=acknowledgement,
        )
        if test_mode:
            _write_test_final_authorization(
                generation,
                startup_nonce,
                runner_nonce,
                execution_revision,
                child.pid,
                controller_public_key,
                test_controller_private_key,
            )
        final_authorization = _wait_for_controller_final_authorization(
            child,
            generation,
            startup_nonce,
            runner_nonce,
            execution_revision,
            controller_public_key=controller_public_key,
            live_validate=not test_mode,
            sleep_fn=sleep_fn,
        )
        if not final_authorization.get("success") or STOP_PATH.exists():
            STOP_PATH.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
            containment = _contain_spawned_process(child, runner_tree)
            _write_status(
                "infrastructure_hold",
                generation=generation,
                runner_state="containment_required",
                failure_status=final_authorization.get("reason") or "governed_stop_active",
                failure_detail={"containment": containment},
            )
            return {
                "status": "infrastructure_hold",
                "failure_status": final_authorization.get("reason") or "governed_stop_active",
                "containment": containment,
            }
        try:
            if execution_mode == "observe_only":
                recovery, recovery_status = ({"status": "observe_only_recovery_unreachable"}, 200)
            elif recovery_fn is not None:
                recovery, recovery_status = recovery_fn()
            elif test_mode:
                recovery, recovery_status = ({"status": "test_recovery_skipped"}, 200)
            else:
                from modules.charlie.execution_bridge import recover_pending_final_agent_artifact
                recovery, recovery_status = recover_pending_final_agent_artifact()
        except Exception as exc:
            recovery = {
                "status": "final_artifact_recovery_failed",
                "error_type": exc.__class__.__name__,
            }
            recovery_status = 503
        if recovery_status >= 400 or STOP_PATH.exists():
            STOP_PATH.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
            containment = _contain_spawned_process(child, runner_tree)
            _write_status(
                "final_artifact_recovery_blocked",
                generation=generation,
                runner_state="containment_required",
                recovery=recovery,
                failure_detail={"containment": containment},
            )
            return {
                "status": "final_artifact_recovery_blocked",
                "recovery": recovery,
                "containment": containment,
            }
        _write_status(
            "operational_authorized",
            generation=generation,
            runner_state="operational_authorized",
            execution_mode=execution_mode,
            recovery=recovery,
        )
        return_code = child.wait()
        if STOP_PATH.exists():
            _write_status("supervisor_stopped", child_pid=child.pid, restart_count=restart_count, return_code=return_code, generation=generation)
            break
        restart_count += 1
        failure_packet = _runner_failure_packet(return_code=return_code)
        failure = failure_packet.get("signature", "")
        repair = {}
        if failure_packet.get("status") in {"git_operation_marker_permission_denied", "git_operation_marker_remove_failed"}:
            repair = _recreate_damaged_runner_worktree(failure_packet)
            if repair.get("success"):
                repair["analyst_validation"] = _run_analyst_repair_validation()
                repeated_failure = ""
                repeated_failure_count = 0
        if failure and failure == repeated_failure:
            repeated_failure_count += 1
        elif failure:
            repeated_failure = failure
            repeated_failure_count = 1
        else:
            repeated_failure = ""
            repeated_failure_count = 0
        if failure and repeated_failure_count >= INFRASTRUCTURE_FAILURE_LIMIT:
            payload = _write_status(
                "infrastructure_hold",
                child_pid=child.pid,
                restart_count=restart_count,
                return_code=return_code,
                failure_status=failure,
                failure_detail=failure_packet,
                identical_failure_count=repeated_failure_count,
                generation=generation,
                recommended_action=failure_packet.get("recommended_action") or "Resolve the recorded infrastructure failure, then explicitly restart CORE.",
            )
            if notifier:
                notifier(payload)
            return {"status": "infrastructure_hold", "restart_count": restart_count, "cycles": cycles, "failure_status": failure, "repair": repair}
        delay = min(5 * (2 ** min(restart_count - 1, 4)), 60)
        _write_status(
            "runner_exited_restart_pending", child_pid=child.pid, restart_count=restart_count,
            return_code=return_code, restart_delay_seconds=delay, generation=generation,
            latest_failure=failure_packet, identical_failure_count=repeated_failure_count,
            automatic_repair=repair,
        )
        if max_cycles is not None and cycles >= max_cycles:
            break
        sleep_fn(delay)
    return {"status": "supervisor_stopped", "restart_count": restart_count, "cycles": cycles}


def _test_acknowledgement(
    child, generation, runtime_revision, execution_revision,
    runner_nonce=None, sleep_fn=None,
):
    return {
        "success": True,
        "status": "test_acknowledged",
        "generation": generation,
        "runtime_revision": runtime_revision,
        "execution_revision": execution_revision,
        "startup_nonce": runner_nonce,
        "process_tree_identity": {},
    }


def _wait_for_controller_ack(
    generation,
    startup_nonce,
    runtime_revision,
    execution_revision,
    controller_public_key="",
    execution_mode="ordinary",
    live_validate=True,
    sleep_fn=time.sleep,
    timeout_seconds=15,
):
    deadline = time.monotonic() + max(0, float(timeout_seconds))
    last_reason = "controller_ownership_packet_missing"
    while time.monotonic() <= deadline:
        packet = _read_status()
        if packet and str(packet.get("generation") or "") == generation:
            valid, reason = validate_supervisor_packet(
                packet,
                generation,
                runtime_revision,
                execution_revision,
                runner_states={"not_spawned"},
                startup_nonce=startup_nonce,
                statuses={"supervisor_ready"},
                execution_mode=execution_mode,
            )
            if not valid:
                return {"success": False, "reason": reason, "packet": packet}
            acknowledgement = packet.get("controller_acknowledgement")
            if not isinstance(acknowledgement, dict):
                return {
                    "success": False,
                    "reason": "ownership_identity_incomplete:controller_acknowledgement",
                }
            checks = {
                "generation": generation,
                "startup_nonce": startup_nonce,
                "revision": runtime_revision,
            }
            if execution_mode == "observe_only" or acknowledgement.get("execution_mode"):
                checks["execution_mode"] = execution_mode
            for field, expected in checks.items():
                if str(acknowledgement.get(field) or "") != expected:
                    return {
                        "success": False,
                        "reason": f"controller_acknowledgement_{field}_mismatch",
                    }
            signature = acknowledgement.get("signature")
            unsigned = {
                key: value for key, value in acknowledgement.items()
                if key != "signature"
            }
            if (
                not controller_public_key
                or str(packet.get("controller_public_key") or "") != controller_public_key
                or not verify_controller_acknowledgement(
                    unsigned, signature, controller_public_key
                )
            ):
                return {
                    "success": False,
                    "reason": "controller_acknowledgement_signature_invalid",
                }
            member_pids = sorted(
                int(value) for value in acknowledgement.get("member_pids") or []
            )
            tree_member_pids = sorted(
                int(item.get("pid"))
                for item in (packet.get("supervisor_tree_identity") or {}).get("members", [])
                if item.get("pid")
            )
            if member_pids != tree_member_pids:
                return {
                    "success": False,
                    "reason": "controller_acknowledgement_member_pids_mismatch",
                }
            if str(acknowledgement.get("supervisor_tree_digest") or "") != (
                process_tree_identity_digest(packet.get("supervisor_tree_identity"))
            ):
                return {
                    "success": False,
                    "reason": "controller_acknowledgement_tree_digest_mismatch",
                }
            if live_validate:
                live = validate_live_bootstrap_tree(
                    packet.get("supervisor_tree_identity"),
                    generation=generation,
                    revision=runtime_revision,
                    startup_nonce=startup_nonce,
                )
                if not live["authorized"]:
                    return {"success": False, "reason": live["reason"]}
            return {
                "success": True,
                "status": "controller_identity_acknowledged",
                "packet": packet,
            }
        if STOP_PATH.exists():
            return {"success": False, "reason": "governed_stop_during_supervisor_start"}
        sleep_fn(0.05)
    return {"success": False, "reason": last_reason}


def _write_test_controller_packet(
    generation,
    startup_nonce,
    runtime_revision,
    execution_revision,
    controller_public_key,
    controller_private_key,
    execution_mode="ordinary",
):
    root = {
        "pid": 100,
        "creation_time": "test-launcher",
        "executable_path": str(sys.executable),
        "command_fingerprint": "test-launcher-command",
        "parent_pid": 1,
        "runner_generation": generation,
        "mission_id": "charlie-control",
        "execution_id": generation,
        "ownership_type": "charlie_runner",
        "revision": runtime_revision,
        "execution_mode": execution_mode,
        "startup_nonce": startup_nonce,
        "process_role": "supervisor_launcher",
    }
    interpreter = {
        **root,
        "pid": os.getpid(),
        "parent_pid": 100,
        "creation_time": "test-interpreter",
        "command_fingerprint": "test-interpreter-command",
        "process_role": "supervisor_interpreter",
    }
    supervisor_tree = make_process_tree_record(
        root, [root, interpreter], generation
    )
    acknowledgement = {
        "status": "supervisor_identity_acknowledged",
        "generation": generation,
        "startup_nonce": startup_nonce,
        "revision": runtime_revision,
        "execution_mode": execution_mode,
        "member_pids": [100, os.getpid()],
        "supervisor_tree_digest": process_tree_identity_digest(supervisor_tree),
    }
    acknowledgement["signature"] = sign_controller_acknowledgement(
        acknowledgement, controller_private_key
    )
    packet = {
        "version": SUPERVISOR_PACKET_VERSION,
        "pid": interpreter["pid"],
        "status": "supervisor_ready",
        "runner_state": "not_spawned",
        "generation": generation,
        "startup_nonce": startup_nonce,
        "process_role": "runner_launcher",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "intended_runtime_revision": runtime_revision,
        "intended_execution_revision": execution_revision,
        "controller_public_key": controller_public_key,
        "execution_mode": execution_mode,
        "supervisor_tree_identity": supervisor_tree,
        "controller_acknowledgement": acknowledgement,
    }
    atomic_write_json(SUPERVISOR_PATH, packet)
    return packet


def _test_runner_observation(pid, generation, revision, startup_nonce):
    root = {
        "pid": pid,
        "creation_time": "test-runner-launcher",
        "executable_path": str(sys.executable),
        "command_fingerprint": "test-runner-launcher-command",
        "parent_pid": os.getpid(),
        "runner_generation": generation,
        "mission_id": "charlie-control",
        "execution_id": generation,
        "ownership_type": "charlie_runner",
        "revision": revision,
        "startup_nonce": startup_nonce,
    }
    interpreter = {
        **root,
        "pid": int(pid) + 1,
        "parent_pid": pid,
        "creation_time": "test-runner-interpreter",
        "command_fingerprint": "test-runner-interpreter-command",
        "process_role": "runner_interpreter",
    }
    tree = make_process_tree_record(root, [root, interpreter], generation)
    return {
        "success": True,
        "tree": tree,
        "validation": {
            "authorized": True,
            "member_pids": [pid, int(pid) + 1],
        },
    }


def _wait_for_runner_ack(
    child,
    generation,
    runtime_revision,
    execution_revision,
    runner_nonce=None,
    sleep_fn=time.sleep,
    timeout_seconds=30,
):
    deadline = time.monotonic() + max(0, float(timeout_seconds))
    reason = "runner_heartbeat_acknowledgement_missing"
    while time.monotonic() <= deadline:
        heartbeat = _read_json(RUNNER_HEARTBEAT_PATH)
        if (
            str(heartbeat.get("status") or "") == "ownership_ready"
            and
            str(heartbeat.get("supervisor_generation") or "") == generation
            and str(heartbeat.get("runner_source_commit") or "") == execution_revision
            and str(heartbeat.get("startup_nonce") or "") == str(runner_nonce or "")
            and isinstance(heartbeat.get("process_identity"), dict)
        ):
            interpreter = heartbeat["process_identity"]
            tree = _read_status().get("process_tree_identity")
            decision = validate_bootstrap_tree(
                tree,
                generation=generation,
                revision=execution_revision,
                startup_nonce=runner_nonce,
                require_interpreter=True,
            )
            if (
                decision["authorized"]
                and int(interpreter.get("pid") or -1) in set(decision.get("member_pids") or [])
            ):
                return {
                    "success": True,
                    "status": "runner_acknowledged",
                    "generation": generation,
                    "runtime_revision": runtime_revision,
                    "execution_revision": execution_revision,
                    "runner_pid": heartbeat.get("pid"),
                    "process_tree_identity": tree,
                }
            reason = decision.get("reason") or "runner_process_tree_acknowledgement_invalid"
        if child.poll() is not None:
            return {"success": False, "reason": "runner_exited_before_acknowledgement"}
        if STOP_PATH.exists():
            return {"success": False, "reason": "governed_stop_during_runner_start"}
        sleep_fn(0.1)
    return {"success": False, "reason": reason}


def _wait_for_controller_final_authorization(
    child,
    generation,
    supervisor_nonce,
    runner_nonce,
    revision,
    *,
    controller_public_key="",
    live_validate=True,
    sleep_fn=time.sleep,
    timeout_seconds=30,
):
    execution_mode = str(os.getenv("CHARLIE_CORE_EXECUTION_MODE") or "ordinary")
    deadline = time.monotonic() + max(0, float(timeout_seconds))
    reason = "controller_final_acknowledgement_missing"
    while time.monotonic() <= deadline:
        if STOP_PATH.exists():
            return {"success": False, "reason": "governed_stop_during_final_authorization"}
        packet = _read_status()
        acknowledgement = packet.get("controller_final_acknowledgement")
        if (
            str(packet.get("status") or "") == "running_authorized"
            and str(packet.get("runner_state") or "") == "running_authorized"
            and isinstance(acknowledgement, dict)
        ):
            supervisor_root_pid = int(
                ((packet.get("supervisor_tree_identity") or {}).get("root") or {}).get("pid")
                or -1
            )
            expected = {
                "generation": generation,
                "supervisor_startup_nonce": supervisor_nonce,
                "runner_startup_nonce": runner_nonce,
                "revision": revision,
                "supervisor_pid": str(supervisor_root_pid),
                "runner_pid": str(child.pid),
                "supervisor_tree_digest": process_tree_identity_digest(
                    packet.get("supervisor_tree_identity")
                ),
                "runner_tree_digest": process_tree_identity_digest(
                    packet.get("process_tree_identity")
                ),
            }
            if execution_mode == "observe_only" or acknowledgement.get("execution_mode"):
                expected["execution_mode"] = execution_mode
            mismatch = next(
                (
                    field for field, value in expected.items()
                    if str(acknowledgement.get(field) or "") != str(value or "")
                ),
                "",
            )
            if mismatch:
                return {
                    "success": False,
                    "reason": f"controller_final_acknowledgement_{mismatch}_mismatch",
                }
            signature = acknowledgement.get("signature")
            unsigned = {
                key: value for key, value in acknowledgement.items()
                if key != "signature"
            }
            if (
                not controller_public_key
                or str(packet.get("controller_public_key") or "") != controller_public_key
                or not verify_controller_acknowledgement(
                    unsigned, signature, controller_public_key
                )
            ):
                return {
                    "success": False,
                    "reason": "controller_final_acknowledgement_signature_invalid",
                }
            if live_validate:
                supervisor_live = validate_live_bootstrap_tree(
                    packet.get("supervisor_tree_identity"),
                    generation=generation,
                    revision=revision,
                    startup_nonce=supervisor_nonce,
                )
                runner_live = validate_live_bootstrap_tree(
                    packet.get("process_tree_identity"),
                    generation=generation,
                    revision=revision,
                    startup_nonce=runner_nonce,
                )
                if not supervisor_live["authorized"]:
                    return {"success": False, "reason": supervisor_live["reason"]}
                if not runner_live["authorized"]:
                    return {"success": False, "reason": runner_live["reason"]}
                for field, expected_members in {
                    "supervisor_member_pids": supervisor_live["member_pids"],
                    "runner_member_pids": runner_live["member_pids"],
                }.items():
                    if sorted(acknowledgement.get(field) or []) != sorted(expected_members):
                        return {
                            "success": False,
                            "reason": f"controller_final_{field}_mismatch",
                        }
            return {"success": True, "status": "controller_final_authorized"}
        if child.poll() is not None:
            return {"success": False, "reason": "runner_exited_before_final_authorization"}
        sleep_fn(0.05)
    return {"success": False, "reason": reason}


def _write_test_final_authorization(
    generation,
    supervisor_nonce,
    runner_nonce,
    revision,
    runner_pid,
    controller_public_key,
    controller_private_key,
):
    execution_mode = str(os.getenv("CHARLIE_CORE_EXECUTION_MODE") or "ordinary")
    packet = _read_status()
    supervisor_members = (
        (packet.get("supervisor_tree_identity") or {}).get("members") or []
    )
    supervisor_root_pid = (
        ((packet.get("supervisor_tree_identity") or {}).get("root") or {}).get("pid")
    )
    runner_members = (packet.get("process_tree_identity") or {}).get("members") or []
    acknowledgement = {
        "status": "current_process_tree_acknowledged",
        "generation": generation,
        "supervisor_startup_nonce": supervisor_nonce,
        "runner_startup_nonce": runner_nonce,
        "revision": revision,
        "supervisor_pid": str(supervisor_root_pid or ""),
        "runner_pid": str(runner_pid),
        "supervisor_member_pids": [item.get("pid") for item in supervisor_members],
        "runner_member_pids": [item.get("pid") for item in runner_members],
        "supervisor_tree_digest": process_tree_identity_digest(
            packet.get("supervisor_tree_identity")
        ),
        "runner_tree_digest": process_tree_identity_digest(
            packet.get("process_tree_identity")
        ),
        "execution_mode": execution_mode,
    }
    acknowledgement["signature"] = sign_controller_acknowledgement(
        acknowledgement, controller_private_key
    )
    packet.update({
        "status": "running_authorized",
        "runner_state": "running_authorized",
        "controller_public_key": controller_public_key,
        "execution_mode": execution_mode,
        "controller_final_acknowledgement": acknowledgement,
    })
    atomic_write_json(SUPERVISOR_PATH, packet)
    return packet


def _prepare_execution_root(run_factory=subprocess.run):
    """Boot every worker from the promoted control revision, never a stale mission checkout."""
    if not EXECUTION_ROOT.exists():
        return {
            "success": False,
            "status": "execution_root_missing",
            "recommended_action": "Recreate the dedicated CORE execution worktree from the promoted runtime.",
        }
    base_branch = EXECUTION_BASE_BRANCH

    def git(args, cwd):
        return run_factory(["git", *args], cwd=cwd, text=True, capture_output=True, timeout=120)

    revision = git(["rev-parse", "HEAD"], REPO_ROOT)
    promoted_revision = str(revision.stdout or "").strip() if revision.returncode == 0 else ""
    if not promoted_revision:
        return {
            "success": False,
            "status": "promoted_runtime_revision_unavailable",
            "stderr": str(revision.stderr or "")[-500:],
            "recommended_action": "Verify the promoted CORE runtime checkout before restarting the supervisor.",
        }

    status = git(["status", "--porcelain"], EXECUTION_ROOT)
    if status.returncode != 0:
        return {
            "success": False,
            "status": "execution_status_failed",
            "stderr": str(status.stderr or "")[-500:],
            "recommended_action": "Repair the dedicated CORE execution checkout before restarting.",
        }
    dirty_paths = []
    for line in str(status.stdout or "").splitlines():
        path = line[3:].strip().replace("\\", "/") if len(line) > 3 else ""
        if path and path not in GENERATED_EXECUTION_PATHS:
            dirty_paths.append(path)
    if dirty_paths:
        return {
            "success": False,
            "status": "execution_root_has_unpreserved_changes",
            "dirty_paths": dirty_paths,
            "recommended_action": "Preserve or package the listed execution changes; CORE refused to overwrite them.",
        }
    if str(status.stdout or "").strip():
        restored = git(["restore", "--staged", "--worktree", "--", *sorted(GENERATED_EXECUTION_PATHS)], EXECUTION_ROOT)
        if restored.returncode != 0:
            return {
                "success": False,
                "status": "generated_execution_state_restore_failed",
                "stderr": str(restored.stderr or "")[-500:],
                "recommended_action": "Preserve and restore the generated execution state before restarting CORE.",
            }
    detached = git(["switch", "--detach"], EXECUTION_ROOT)
    if detached.returncode != 0:
        return {
            "success": False,
            "status": "execution_detach_failed",
            "stderr": str(detached.stderr or "")[-500:],
            "recommended_action": "Detach the dedicated execution checkout before promoting its base branch.",
        }
    update_base = git(["branch", "--force", base_branch, promoted_revision], EXECUTION_ROOT)
    if update_base.returncode != 0:
        return {
            "success": False,
            "status": "execution_base_promotion_failed",
            "stderr": str(update_base.stderr or "")[-500:],
            "recommended_action": "Repair the dedicated execution base branch before restarting CORE.",
        }
    switched = git(["switch", base_branch], EXECUTION_ROOT)
    if switched.returncode != 0:
        return {
            "success": False,
            "status": "execution_base_switch_failed",
            "stderr": str(switched.stderr or "")[-500:],
            "recommended_action": "Restore the dedicated execution checkout to its promoted base branch.",
        }
    current = git(["rev-parse", "HEAD"], EXECUTION_ROOT)
    current_revision = str(current.stdout or "").strip() if current.returncode == 0 else ""
    if current_revision != promoted_revision:
        return {
            "success": False,
            "status": "execution_bootstrap_revision_mismatch",
            "promoted_revision": promoted_revision,
            "execution_revision": current_revision,
            "recommended_action": "Do not start CORE until control and execution bootstrap revisions match.",
        }
    return {
        "success": True,
        "status": "execution_bootstrap_ready",
        "base_branch": base_branch,
        "promoted_revision": promoted_revision,
        "execution_revision": current_revision,
    }


def _runner_failure_signature(path=None):
    return _runner_failure_packet(path=path).get("signature", "")


def _runner_failure_packet(path=None, return_code=None):
    path = RUNNER_HEARTBEAT_PATH if path is None else path
    try:
        heartbeat = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, AttributeError):
        heartbeat = {}
    status = str(heartbeat.get("last_result_status") or "").strip()
    failure_detail = heartbeat.get("last_failure") if isinstance(heartbeat.get("last_failure"), dict) else {}
    error_type = str(failure_detail.get("error_type") or heartbeat.get("error_type") or "").strip()
    marker = str(failure_detail.get("marker_path") or heartbeat.get("marker_path") or "").strip()
    if status in NON_RETRYABLE_RUNNER_STATUSES:
        signature = ":".join(item for item in (status, error_type, marker) if item)
    else:
        signature = f"child_exit:{int(return_code)}:{status or 'no_durable_status'}"
    return {
        "signature": signature,
        "status": status or "child_process_exited",
        "return_code": return_code,
        "error_type": error_type,
        "marker_path": marker,
        "mission_id": str(heartbeat.get("last_mission_id") or ""),
        "recommended_action": str(
            failure_detail.get("recommended_action")
            or heartbeat.get("recommended_action")
            or "Inspect the recorded runner failure and repair the dedicated worktree before restarting CORE."
        ),
    }


def _notify_infrastructure_hold(payload):
    failure = str((payload or {}).get("failure_status") or "unknown_infrastructure_failure")
    detail = (payload or {}).get("failure_detail") if isinstance((payload or {}).get("failure_detail"), dict) else {}
    action = str((payload or {}).get("recommended_action") or detail.get("recommended_action") or "Repair the runner and restart CORE.")
    location = str(detail.get("marker_path") or "")
    message = (
        f"CORE stopped after {INFRASTRUCTURE_FAILURE_LIMIT} identical child crashes. "
        f"Failure: {failure}." + (f" Path: {location}." if location else "") + f" Required recovery: {action}"
    )
    try:
        completed = subprocess.run(
            [
                _python_executable(),
                str(REPO_ROOT / "scripts" / "charlie_notify.py"),
                "--level", "blocked",
                "--title", "CORE infrastructure hold",
                "--message", message,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            **background_run_kwargs(),
        )
    except Exception as exc:
        return {"success": False, "status": "notification_failed", "error_type": exc.__class__.__name__}
    return {"success": completed.returncode == 0, "status": "sent" if completed.returncode == 0 else "notification_failed"}


def _recreate_damaged_runner_worktree(failure, run_factory=subprocess.run):
    """Recreate only the dedicated runner worktree after a typed marker-access failure."""
    if REPO_ROOT.parent.name != ".charlie_runner":
        return {"success": False, "status": "automatic_repair_refused_non_runner_worktree"}
    canonical = REPO_ROOT.parents[1]
    base_branch = str(env_value("CORE_EXECUTION_BASE_BRANCH", "charlie-core-execution-base") or "charlie-core-execution-base").strip()
    lock = RepositoryOperationLock(repository_lock_path(REPO_ROOT))
    acquired, owner = lock.acquire()
    if not acquired:
        return {"success": False, "status": "automatic_repair_repository_locked", "lock_owner": owner}
    original_cwd = Path.cwd()
    try:
        os.chdir(canonical)
        commands = [["git", "worktree", "remove", "--force", str(REPO_ROOT)]]
        results = []
        for command in commands:
            completed = run_factory(command, cwd=canonical, text=True, capture_output=True, timeout=120)
            results.append({"command": command[1:3], "returncode": completed.returncode, "stderr": str(completed.stderr or "")[-500:]})
        quarantine_path = ""
        if results[0]["returncode"] != 0 and REPO_ROOT.exists():
            quarantine = REPO_ROOT.with_name(f"{REPO_ROOT.name}.quarantine-{int(time.time())}")
            REPO_ROOT.rename(quarantine)
            quarantine_path = str(quarantine)
        for command in (["git", "worktree", "prune"], ["git", "worktree", "add", "--force", str(REPO_ROOT), base_branch]):
            completed = run_factory(command, cwd=canonical, text=True, capture_output=True, timeout=120)
            results.append({"command": command[1:3], "returncode": completed.returncode, "stderr": str(completed.stderr or "")[-500:]})
            if command[2] == "add" and completed.returncode != 0:
                return {"success": False, "status": "automatic_worktree_recreate_failed", "results": results, "failure": failure, "quarantine_path": quarantine_path}
        return {"success": True, "status": "damaged_runner_worktree_recreated", "base_branch": base_branch, "results": results, "quarantine_path": quarantine_path}
    except Exception as exc:
        return {"success": False, "status": "automatic_worktree_recreate_failed", "error_type": exc.__class__.__name__, "failure": failure}
    finally:
        try:
            os.chdir(canonical if not original_cwd.exists() else original_cwd)
        except OSError:
            os.chdir(canonical)
        lock.release()


def _run_analyst_repair_validation():
    """Refresh proposal outcomes immediately after a conveyor repair completes."""
    try:
        from modules.charlie.improvement_analyst import run_operational_analyst
        result, status_code = run_operational_analyst(trigger="conveyor_repair_completed", limit=50)
    except Exception as exc:
        return {"success": False, "status": "analyst_repair_validation_failed", "error_type": exc.__class__.__name__}
    return {
        "success": status_code < 400 and bool(result.get("success")),
        "status": result.get("status", "analyst_repair_validation_failed"),
        "status_code": status_code,
        "lifecycle": result.get("lifecycle", {}),
    }


def _recover_stale_owned_child():
    if emergency_process_cleanup_disabled():
        record_emergency_cleanup_refusal("supervisor_recover_stale_owned_child", "recorded-child")
        return False
    if not process_termination_enabled():
        return False
    try:
        state = json.loads(SUPERVISOR_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    supervisor_pid = state.get("pid")
    child_pid = state.get("child_pid")
    if not child_pid or _pid_alive(supervisor_pid) or not _pid_alive(child_pid):
        return False
    recorded_identity = state.get("child_identity")
    expected = {
        "runner_generation": recorded_identity.get("runner_generation") if isinstance(recorded_identity, dict) else "",
        "mission_id": "charlie-control",
        "execution_id": recorded_identity.get("execution_id") if isinstance(recorded_identity, dict) else "",
        "ownership_type": "charlie_runner",
    }
    decision = validate_termination(recorded_identity, expected, inspect_process)
    if not decision["authorized"]:
        return False
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(child_pid), "/T", "/F"], capture_output=True, check=False, timeout=15)
    else:
        os.kill(int(child_pid), signal.SIGTERM)
    return True


def _same_process_identity(recorded, current):
    required = ("created", "executable", "command")
    if not isinstance(recorded, dict) or not isinstance(current, dict):
        return False
    return all(recorded.get(key) and recorded.get(key) == current.get(key) for key in required)


def _process_identity(pid):
    """Return non-reusable process evidence, or None when ownership cannot be proven."""
    try:
        pid = int(pid)
        if os.name == "nt":
            return _windows_process_identity(pid)
        stat_parts = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
        executable = str(Path(f"/proc/{pid}/exe").resolve())
        command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8").strip()
        return {"created": stat_parts[21], "executable": executable, "command": command}
    except (OSError, ValueError, IndexError, UnicodeError, subprocess.SubprocessError):
        return None


def _windows_process_identity(pid):
    process_query_limited_information = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return None
    try:
        creation = ctypes.c_ulonglong()
        exit_time = ctypes.c_ulonglong()
        kernel = ctypes.c_ulonglong()
        user = ctypes.c_ulonglong()
        if not ctypes.windll.kernel32.GetProcessTimes(
            handle, ctypes.byref(creation), ctypes.byref(exit_time),
            ctypes.byref(kernel), ctypes.byref(user),
        ):
            return None
        size = ctypes.c_ulong(32768)
        image = ctypes.create_unicode_buffer(size.value)
        if not ctypes.windll.kernel32.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
            return None
        command = _windows_process_command(pid)
        if not command:
            return None
        return {"created": str(creation.value), "executable": image.value, "command": command}
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _windows_process_command(pid):
    script = (
        "$p=Get-CimInstance Win32_Process -Filter \"ProcessId = " + str(pid) + "\"; "
        "if($p){[Console]::Out.Write($p.CommandLine)}"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, check=False, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
    except subprocess.SubprocessError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _pid_alive(pid, runner=subprocess.run):
    try:
        pid = int(pid)
        if pid <= 0:
            return False
        if os.name == "nt":
            completed = runner(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if completed.returncode != 0:
                return False
            rows = list(csv.reader(str(completed.stdout or "").splitlines()))
            return any(len(row) > 1 and row[1].strip() == str(pid) for row in rows)
        os.kill(pid, 0)
        return True
    except (TypeError, ValueError, OSError, SystemError, subprocess.SubprocessError):
        return False


def _write_status(status, **extra):
    previous = _read_status()
    payload = {
        "version": SUPERVISOR_PACKET_VERSION,
        "pid": os.getpid(),
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    generation = str(payload.get("generation") or "").strip()
    previous_generation = str(previous.get("generation") or "").strip()
    history = previous.get("ownership_history") if isinstance(previous.get("ownership_history"), list) else []
    if previous and previous_generation != generation:
        history = [
            *history,
            {
                key: previous.get(key)
                for key in (
                    "version", "generation", "created_at", "updated_at", "status",
                    "startup_nonce", "runner_state", "supervisor_tree_identity",
                    "process_tree_identity", "stop_evidence",
                )
                if key in previous
            },
        ][-10:]
    if history:
        payload["ownership_history"] = history
    if previous_generation == generation:
        for key in (
            "created_at",
            "startup_nonce",
            "controller_acknowledgement",
            "child_identity",
            "process_tree_identity",
            "stop_evidence",
            "supervisor_tree_identity",
            "runner_acknowledgement",
            "runner_startup_nonce",
            "runner_controller_acknowledgement",
            "controller_final_acknowledgement",
            "execution_mode",
        ):
            if key not in payload and key in previous:
                payload[key] = previous[key]
    payload = redact_payload(payload)
    atomic_write_json(SUPERVISOR_PATH, payload)
    return payload


def _read_status():
    return _read_json(SUPERVISOR_PATH)


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def _git_revision(path):
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            **background_run_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return str(completed.stdout or "").strip() if completed.returncode == 0 else ""


def main():
    for path in (REPO_ROOT / ".env", REPO_ROOT.parents[1] / ".env"):
        if path.exists():
            load_dotenv(path, override=False)
            break
    instance_lock = SupervisorInstanceLock()
    acquired, owner_pid = instance_lock.acquire()
    if not acquired:
        return {"status": "duplicate_supervisor_refused", "existing_supervisor_pid": owner_pid}
    try:
        if STOP_PATH.exists():
            return {"status": "governed_stop_active", "runner_state": "not_spawned"}
        generation = str(os.getenv("CHARLIE_SUPERVISOR_GENERATION") or uuid.uuid4().hex)
        return supervise_runner(
            notifier=_notify_infrastructure_hold,
            generation=generation,
        )
    finally:
        instance_lock.release()


if __name__ == "__main__":
    result = main()
    raise SystemExit(0 if result.get("status") in {"supervisor_stopped", "duplicate_supervisor_refused"} else 1)
