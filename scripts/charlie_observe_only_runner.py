"""Minimal governed CORE child for ownership observation without mission access."""

import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.process_ownership import (
    process_tree_identity_digest,
    validate_bootstrap_tree,
    validate_live_bootstrap_tree,
    verify_controller_acknowledgement,
)
from modules.charlie.runner_control import (
    EXECUTION_MODE_OBSERVE_ONLY,
    SUPERVISOR_PATH,
    SUPERVISOR_STOP_PATH,
    _read_json,
    validate_supervisor_packet,
    write_runner_heartbeat,
)
from modules.charlie.control_tower_feedback import (
    FEEDBACK_EVENT,
    process_pending_control_tower_feedback,
)


def _identity():
    return {
        "generation": str(os.getenv("CHARLIE_SUPERVISOR_GENERATION") or ""),
        "supervisor_nonce": str(os.getenv("CHARLIE_STARTUP_NONCE") or ""),
        "runner_nonce": str(os.getenv("CHARLIE_RUNNER_STARTUP_NONCE") or ""),
        "runtime_revision": str(os.getenv("CHARLIE_INTENDED_RUNTIME_REVISION") or ""),
        "execution_revision": str(os.getenv("CHARLIE_INTENDED_EXECUTION_REVISION") or ""),
        "public_key": str(os.getenv("CHARLIE_CONTROLLER_PUBLIC_KEY") or ""),
        "activation_id": str(os.getenv("CHARLIE_ACTIVATION_ID") or ""),
    }


def _validate_runner_start(sleep_fn=time.sleep, timeout_seconds=60):
    identity = _identity()
    if SUPERVISOR_STOP_PATH.exists():
        return {"success": False, "reason": "governed_stop_active"}
    if str(os.getenv("CHARLIE_CORE_EXECUTION_MODE") or "") != EXECUTION_MODE_OBSERVE_ONLY:
        return {"success": False, "reason": "observe_only_mode_missing"}
    if not all(identity.values()):
        return {"success": False, "reason": "observe_only_identity_incomplete"}
    deadline = time.monotonic() + max(0, float(timeout_seconds))
    packet = _read_json(SUPERVISOR_PATH)
    while (
        str(packet.get("runner_state") or "") == "not_spawned"
        and time.monotonic() <= deadline
    ):
        sleep_fn(0.05)
        packet = _read_json(SUPERVISOR_PATH)
    valid, reason = validate_supervisor_packet(
        packet,
        identity["generation"],
        identity["runtime_revision"],
        identity["execution_revision"],
        runner_states={"runner_starting"},
        startup_nonce=identity["supervisor_nonce"],
        statuses={"runner_starting"},
        execution_mode=EXECUTION_MODE_OBSERVE_ONLY,
    )
    if not valid:
        return {"success": False, "reason": reason}
    runner = validate_bootstrap_tree(
        packet.get("process_tree_identity"),
        generation=identity["generation"],
        revision=identity["execution_revision"],
        startup_nonce=identity["runner_nonce"],
        require_interpreter=True,
    )
    if not runner["authorized"] or os.getpid() not in set(runner.get("member_pids") or []):
        return {
            "success": False,
            "reason": runner.get("reason") or "runner_identity_pid_not_acknowledged",
        }
    acknowledgement = packet.get("runner_controller_acknowledgement")
    for field, expected in {
        "generation": identity["generation"],
        "startup_nonce": identity["runner_nonce"],
        "revision": identity["execution_revision"],
        "execution_mode": EXECUTION_MODE_OBSERVE_ONLY,
    }.items():
        if not isinstance(acknowledgement, dict) or str(
            acknowledgement.get(field) or ""
        ) != expected:
            return {
                "success": False,
                "reason": f"runner_controller_acknowledgement_{field}_mismatch",
            }
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    actual_revision = str(completed.stdout or "").strip()
    if completed.returncode or actual_revision != identity["execution_revision"]:
        return {"success": False, "reason": "execution_revision_mismatch"}
    return {"success": True, **identity}


def _validate_final(packet):
    identity = _identity()
    acknowledgement = packet.get("controller_final_acknowledgement")
    if not isinstance(acknowledgement, dict):
        return {"success": False, "reason": "controller_final_acknowledgement_missing"}
    expected = {
        "generation": identity["generation"],
        "supervisor_startup_nonce": identity["supervisor_nonce"],
        "runner_startup_nonce": identity["runner_nonce"],
        "revision": identity["execution_revision"],
        "runner_pid": str(os.getpid()),
        "execution_mode": EXECUTION_MODE_OBSERVE_ONLY,
    }
    if identity.get("activation_id"):
        expected["activation_id"] = identity["activation_id"]
    mismatch = next(
        (
            field
            for field, value in expected.items()
            if str(acknowledgement.get(field) or "") != str(value)
        ),
        "",
    )
    unsigned = {key: value for key, value in acknowledgement.items() if key != "signature"}
    if mismatch:
        return {"success": False, "reason": f"controller_final_{mismatch}_mismatch"}
    if (
        str(packet.get("controller_public_key") or "") != identity["public_key"]
        or not verify_controller_acknowledgement(
            unsigned, acknowledgement.get("signature"), identity["public_key"]
        )
    ):
        return {"success": False, "reason": "controller_final_signature_invalid"}
    supervisor = validate_live_bootstrap_tree(
        packet.get("supervisor_tree_identity"),
        generation=identity["generation"],
        revision=identity["execution_revision"],
        startup_nonce=identity["supervisor_nonce"],
        allowed_descendant_tree=packet.get("process_tree_identity"),
    )
    runner = validate_live_bootstrap_tree(
        packet.get("process_tree_identity"),
        generation=identity["generation"],
        revision=identity["execution_revision"],
        startup_nonce=identity["runner_nonce"],
    )
    if not supervisor["authorized"]:
        return {"success": False, "reason": supervisor["reason"]}
    if not runner["authorized"]:
        return {"success": False, "reason": runner["reason"]}
    for field, expected_members in {
        "supervisor_member_pids": supervisor["member_pids"],
        "runner_member_pids": runner["member_pids"],
    }.items():
        if sorted(acknowledgement.get(field) or []) != sorted(expected_members):
            return {"success": False, "reason": f"controller_final_{field}_mismatch"}
    for field, tree in {
        "supervisor_tree_digest": packet.get("supervisor_tree_identity"),
        "runner_tree_digest": packet.get("process_tree_identity"),
    }.items():
        if str(acknowledgement.get(field) or "") != process_tree_identity_digest(tree):
            return {"success": False, "reason": f"controller_final_{field}_mismatch"}
    return {"success": True}


def main(sleep_fn=time.sleep, timeout_seconds=30):
    startup = _validate_runner_start(sleep_fn=sleep_fn)
    if not startup["success"]:
        write_runner_heartbeat({"status": "observe_only_startup_refused", **startup})
        return 1
    write_runner_heartbeat({"status": "ownership_ready", "execution_mode": EXECUTION_MODE_OBSERVE_ONLY})
    deadline = time.monotonic() + max(0, float(timeout_seconds))
    while time.monotonic() <= deadline:
        if SUPERVISOR_STOP_PATH.exists():
            return 0
        packet = _read_json(SUPERVISOR_PATH)
        if (
            str(packet.get("status") or "") == "operational_authorized"
            and str(packet.get("runner_state") or "") == "operational_authorized"
        ):
            final = _validate_final(packet)
            if not final["success"]:
                write_runner_heartbeat({"status": "observe_only_authorization_refused", **final})
                return 1
            break
        sleep_fn(0.05)
    else:
        write_runner_heartbeat({"status": "observe_only_authorization_timeout"})
        return 1
    checks = 0
    interval_seconds = max(5, int(os.getenv("CHARLIE_SHADOW_POLL_SECONDS") or "30"))
    while not SUPERVISOR_STOP_PATH.exists():
        checks += 1
        try:
            shadow = process_pending_control_tower_feedback()
        except Exception:
            shadow = {
                "success": False,
                "status": "control_tower_feedback_cycle_failed",
                "processed_count": 0,
                "next_eligible_event": FEEDBACK_EVENT,
                "dispatches": 0,
                "provider_actions": 0,
                "farm_writes": 0,
                "release_actions": 0,
            }
        write_runner_heartbeat(
            {
                "status": "shadow_observation_cycle",
                "active_status": "observe_only",
                "current_action": "control_tower_feedback_observation",
                "execution_mode": EXECUTION_MODE_OBSERVE_ONLY,
                "checks": checks,
                "shadow": shadow,
                "next_eligible_event": shadow.get("next_eligible_event") or FEEDBACK_EVENT,
                "mission_pickup_attempted": False,
                "release_attempted": False,
            }
        )
        sleep_fn(interval_seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
