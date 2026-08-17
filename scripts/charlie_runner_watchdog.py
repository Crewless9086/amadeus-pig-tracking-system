"""Idempotent outer watchdog for the local CHARLIE runner supervisor."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("GIT_CONFIG_COUNT", "1")
os.environ.setdefault("GIT_CONFIG_KEY_0", "safe.directory")
os.environ.setdefault("GIT_CONFIG_VALUE_0", str(REPO_ROOT))

from modules.charlie.runner_control import (
    RUNNER_DIR,
    SUPERVISOR_STOP_PATH,
    _pid_alive,
    runner_status,
    start_runner,
)
from modules.charlie.process_ownership import (
    process_tree_identity_digest,
    verify_controller_acknowledgement,
)
from modules.charlie.runtime_integrity import cold_start_readiness
from modules.charlie.runtime_activation import (
    WindowsExactTaskController,
    consume_provider_activation,
    recover_activation,
    reconcile_recovered_activation_stop,
)


STATE_PATH = RUNNER_DIR / "watchdog.json"
GIT_CONFIG_PATH = RUNNER_DIR / "task-gitconfig"
SUPERVISOR_LOCK_PATH = RUNNER_DIR / "supervisor.lock"
SUPERVISOR_STATE_PATH = RUNNER_DIR / "supervisor.json"
DEFAULT_RUNNER_BASE_BRANCH = "charlie-core-runtime-base"


def _live_supervisor_lock(path=SUPERVISOR_LOCK_PATH):
    try:
        owner_pid = int(json.loads(Path(path).read_text(encoding="utf-8")).get("pid") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return 0
    return owner_pid if _pid_alive(owner_pid) else 0


def _configure_git_safe_directory(config_path=GIT_CONFIG_PATH):
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    safe_paths = (
        REPO_ROOT,
        config_path.parent / "core-execution-current",
    )
    entries = "".join(
        f'\tdirectory = "{str(path).replace(chr(92), "/")}"\n'
        for path in safe_paths
    )
    config_path.write_text(f"[safe]\n{entries}", encoding="utf-8")
    os.environ["GIT_CONFIG_GLOBAL"] = str(config_path)
    return config_path


def _fast_runner_status():
    return runner_status(include_orphans=False, include_git=False, include_ledger=False)


def _infrastructure_hold(path=SUPERVISOR_STATE_PATH):
    try:
        state = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return state if state.get("status") == "infrastructure_hold" else {}


def _supervisor_state(path=SUPERVISOR_STATE_PATH):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _cold_start_readiness():
    return cold_start_readiness(REPO_ROOT, runtime_dir=RUNNER_DIR)


def watchdog_tick(status_reader=_fast_runner_status, starter=start_runner, state_path=STATE_PATH, supervisor_lock_reader=_live_supervisor_lock, hold_reader=None, supervisor_state_reader=None, readiness_reader=_cold_start_readiness, stop_path=None, activation_consumer=consume_provider_activation, provider_inspector=None, activation_controller_factory=WindowsExactTaskController, activation_recoverer=recover_activation, activation_reconciler=reconcile_recovered_activation_stop):
    state_path = Path(state_path)
    stop_path = Path(stop_path) if stop_path is not None else (
        state_path.with_name("supervisor.stop")
        if state_path != STATE_PATH
        else SUPERVISOR_STOP_PATH
    )
    _configure_git_safe_directory(state_path.with_name("task-gitconfig"))
    if stop_path.exists():
        pending_path = state_path.with_name("activation-reconciliation-pending.json")
        if pending_path.exists():
            pending = json.loads(pending_path.read_text(encoding="utf-8"))
            previous = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
            if state_path.with_name("activation.lock").exists():
                activation_recoverer(
                    state_root=state_path.parent,
                    task_controller=activation_controller_factory(),
                    activation_id=str(pending.get("activation_id") or ""),
                    failure_evidence=previous,
                )
            return activation_reconciler(
                state_root=state_path.parent,
                activation_id=str(pending.get("activation_id") or ""),
                failure_evidence=previous,
            )
        if state_path.exists():
            previous = json.loads(state_path.read_text(encoding="utf-8"))
            if (previous.get("version") == "charlie_activation_recovery_projection_v1"
                    and previous.get("status") == "governed_stop_active"):
                return activation_reconciler(
                    state_root=state_path.parent,
                    activation_id=str(previous.get("recovered_activation_id") or ""),
                    failure_evidence=previous,
                )
        result = {
            "status": "governed_stop_active",
            "started": False,
            "stop_marker": str(stop_path),
        }
        payload = {
            **result,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "runner_status_before": "not_read_while_stopped",
        }
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload
    activation_packet = state_path.with_name("activation-packet.json")
    if activation_packet.exists():
        controller = activation_controller_factory()
        try:
            result = activation_consumer(
                state_root=state_path.parent,
                starter=starter,
                provider_inspector=provider_inspector,
                task_controller=controller,
            )
        except Exception as exc:
            recovery = None
            try:
                packet = json.loads(activation_packet.read_text(encoding="utf-8"))
                activation_id = str(packet.get("activation_id") or "")
                if activation_id and (state_path.parent / "activation.lock").exists():
                    recovery = activation_recoverer(
                        state_root=state_path.parent,
                        task_controller=controller,
                        activation_id=activation_id,
                        failure_evidence={
                            "status": getattr(exc, "status", "provider_activation_failed"),
                            "started": False,
                        },
                    )
            except Exception as recovery_exc:
                recovery = {"success": False, "status": getattr(recovery_exc, "status", "activation_recovery_failed")}
            result = {
                "success": False,
                "status": getattr(exc, "status", "provider_activation_failed"),
                "started": False,
                "recovery": recovery,
            }
            pending_path = state_path.with_name("activation-reconciliation-pending.json")
            if pending_path.exists() and (recovery is None or recovery.get("success")):
                pending = json.loads(pending_path.read_text(encoding="utf-8"))
                result = activation_reconciler(
                    state_root=state_path.parent,
                    activation_id=str(pending.get("activation_id") or ""),
                    failure_evidence=result,
                )
                return result
        payload = {
            **result,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "runner_status_before": "not_read_during_provider_activation",
        }
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload
    supervisor_state_path = state_path.with_name("supervisor.json")
    supervisor_state = (
        supervisor_state_reader()
        if supervisor_state_reader
        else _supervisor_state(supervisor_state_path)
    )
    if (
        supervisor_state_reader is None
        and supervisor_state_path.exists()
        and not supervisor_state
    ):
        payload = {
            "status": "supervisor_state_unreadable",
            "started": False,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "runner_status_before": "not_read_with_unreadable_supervisor_state",
        }
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload
    persisted_mode = str(supervisor_state.get("execution_mode") or "")
    final_ack = supervisor_state.get("controller_final_acknowledgement")
    signed_mode = str(
        (final_ack if isinstance(final_ack, dict) else {}).get("execution_mode")
        or ""
    )
    if not persisted_mode and signed_mode == "observe_only":
        persisted_mode = "observe_only"
    elif not persisted_mode:
        persisted_mode = "ordinary"
    if supervisor_state and persisted_mode not in {"ordinary", "observe_only"}:
        payload = {
            "status": "execution_mode_evidence_invalid",
            "started": False,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "runner_status_before": "not_read_with_invalid_mode_evidence",
        }
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload
    if persisted_mode == "observe_only":
        public_key = str(supervisor_state.get("controller_public_key") or "")
        if isinstance(final_ack, dict):
            unsigned = {
                key: value for key, value in final_ack.items()
                if key != "signature"
            }
            signature_valid = (
                str(final_ack.get("execution_mode") or "") == "observe_only"
                and str(final_ack.get("generation") or "")
                == str(supervisor_state.get("generation") or "")
                and str(final_ack.get("revision") or "")
                == str(supervisor_state.get("intended_execution_revision") or "")
                and str(final_ack.get("supervisor_startup_nonce") or "")
                == str(supervisor_state.get("startup_nonce") or "")
                and str(final_ack.get("supervisor_tree_digest") or "")
                == process_tree_identity_digest(
                    supervisor_state.get("supervisor_tree_identity")
                )
                and str(final_ack.get("runner_tree_digest") or "")
                == process_tree_identity_digest(
                    supervisor_state.get("process_tree_identity")
                )
                and bool(public_key)
                and verify_controller_acknowledgement(
                    unsigned, final_ack.get("signature"), public_key
                )
            )
            if not signature_valid:
                payload = {
                    "status": "observe_only_authorization_invalid",
                    "started": False,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "runner_status_before": "not_read_with_invalid_authorization",
                }
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                return payload
        payload = {
            "status": "observe_only_watchdog_recovery_disabled",
            "started": False,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "runner_status_before": "not_read_in_observe_only",
        }
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload
    status = status_reader()
    supervisor_pid = supervisor_lock_reader()
    hold = hold_reader() if hold_reader else _infrastructure_hold(state_path.with_name("supervisor.json"))
    if hold:
        result = {
            "status": "infrastructure_hold",
            "started": False,
            "failure_status": hold.get("failure_status", ""),
            "identical_failure_count": hold.get("identical_failure_count", 0),
        }
    elif status.get("active"):
        queue_health = status.get("queue_health") if isinstance(status.get("queue_health"), dict) else {}
        if queue_health.get("deadlocked"):
            result = {
                "status": "runner_queue_deadlocked", "started": False,
                "approved_count": int(queue_health.get("approved_count") or 0),
                "runnable_count": int(queue_health.get("runnable_count") or 0),
                "dependency_blocked_ids": queue_health.get("dependency_blocked_ids") or [],
                "recommended_action": "CHARLIE must adjudicate the dependency deadlock or select independent safe work.",
            }
        else:
            result = {"status": "runner_healthy", "started": False}
    elif supervisor_pid:
        supervisor_status = str(supervisor_state.get("status") or "")
        if supervisor_status == "runner_exited_restart_pending":
            result = {
                "status": "supervisor_child_crash_restarting", "started": False,
                "supervisor_pid": supervisor_pid,
                "restart_count": int(supervisor_state.get("restart_count") or 0),
                "identical_failure_count": int(supervisor_state.get("identical_failure_count") or 0),
                "latest_failure": supervisor_state.get("latest_failure") or {},
            }
        else:
            result = {"status": "supervisor_healthy_runner_starting", "started": False, "supervisor_pid": supervisor_pid, "restart_count": int(supervisor_state.get("restart_count") or 0)}
    elif status.get("orphan_processes"):
        result = {"status": "orphan_requires_cleanup", "started": False}
    else:
        readiness = readiness_reader()
        if not readiness.get("ready"):
            result = {
                "status": "cold_start_preflight_blocked", "started": False,
                "blockers": readiness.get("blockers") or [], "readiness": readiness,
            }
        else:
            if stop_path.exists():
                result = {
                    "status": "governed_stop_active",
                    "started": False,
                    "stop_marker": str(stop_path),
                }
            else:
                started, status_code = (
                    starter(status_override=status, respect_stop_marker=True)
                    if starter is start_runner
                    else starter()
                )
                result = {
                    "status": str(started.get("status") or "runner_start_failed"),
                    "started": status_code < 300 and started.get("status") == "runner_started",
                    "status_code": status_code,
                }
    payload = {
        **result,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "runner_status_before": str(status.get("status") or "unknown"),
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser(description="Check and recover the local CHARLIE runner.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = watchdog_tick()
    print(json.dumps(result) if args.json else f"CHARLIE watchdog: {result['status']}")
    return 0 if result["status"] not in {"runner_start_failed", "orphan_requires_cleanup", "cold_start_preflight_blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
