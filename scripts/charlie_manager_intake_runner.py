"""Provider/controller-owned deterministic intake; no ordinary runner entry."""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie import INTAKE_EXECUTION_MODE
from modules.charlie.runner_control import RUNNER_DIR, SUPERVISOR_PATH, SUPERVISOR_STOP_PATH, _read_json, write_runner_heartbeat
from modules.charlie.runtime_activation import (read_intake_activation, load_intake_environment,
    intake_database_connection, INTAKE_ENV_KEYS, ActivationError)
from scripts.charlie_observe_only_runner import _validate_runner_start, _validate_final


def run_intake_cycle():
    """Recheck signed identity/config before exposing only the exact receipt service."""
    from modules.charlie.executive_runtime import run_manager_dependency_intake_cycle
    if SUPERVISOR_STOP_PATH.exists():
        raise ActivationError("governed_stop_active")
    packet = _read_json(SUPERVISOR_PATH)
    if packet.get("status") != "operational_authorized" or packet.get("runner_state") != "operational_authorized":
        raise ActivationError("intake_controller_not_operational")
    final = _validate_final(packet, execution_mode=INTAKE_EXECUTION_MODE)
    if not final.get("success"):
        raise ActivationError("intake_controller_identity_changed")
    authority = read_intake_activation(RUNNER_DIR, os.getenv("CHARLIE_ACTIVATION_ID"))
    # Leave room for the existing bounded policy read and intake transaction.
    expires = datetime.fromisoformat(authority["expires_at"].replace("Z", "+00:00"))
    if (expires - datetime.now(timezone.utc)).total_seconds() <= 20:
        raise ActivationError("intake_activation_window_ending")
    values = load_intake_environment(authority)
    scope = authority["manager_dependency_intake"]
    previous = {k: os.environ.get(k) for k in INTAKE_ENV_KEYS}
    try:
        for key in INTAKE_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ.update(values)
        def connect(target):
            read_intake_activation(RUNNER_DIR, os.getenv("CHARLIE_ACTIVATION_ID"))
            return intake_database_connection(authority, target)
        result, status = run_manager_dependency_intake_cycle(policy_id=scope["policy_id"],
            scope_sha256=scope["scope_sha256"], database_url=values["DATABASE_URL"], connect_factory=connect)
        return result, status
    finally:
        for key, value in previous.items():
            if value is None: os.environ.pop(key, None)
            else: os.environ[key] = value


def main(*, sleep_fn=time.sleep, timeout_seconds=30, max_cycles=None):
    startup = _validate_runner_start(sleep_fn=sleep_fn, execution_mode=INTAKE_EXECUTION_MODE)
    if not startup.get("success"):
        write_runner_heartbeat({"status": "intake_startup_refused", "execution_mode": INTAKE_EXECUTION_MODE})
        return 1
    write_runner_heartbeat({"status": "ownership_ready", "execution_mode": INTAKE_EXECUTION_MODE})
    deadline = time.monotonic() + max(0, float(timeout_seconds))
    while time.monotonic() <= deadline:
        if SUPERVISOR_STOP_PATH.exists(): return 0
        packet = _read_json(SUPERVISOR_PATH)
        if packet.get("status") == "operational_authorized" and packet.get("runner_state") == "operational_authorized":
            break
        sleep_fn(0.05)
    else:
        write_runner_heartbeat({"status": "intake_authorization_timeout", "execution_mode": INTAKE_EXECUTION_MODE})
        return 1
    checks = 0
    while not SUPERVISOR_STOP_PATH.exists():
        try:
            result, status = run_intake_cycle()
        except Exception as exc:
            result, status = {"status": "intake_cycle_contained", "error_type": type(exc).__name__}, 503
        checks += 1
        write_runner_heartbeat({"status": "intake_receipt_cycle" if status < 400 else "intake_cycle_contained",
            "execution_mode": INTAKE_EXECUTION_MODE, "checks": checks, "intake": result,
            "mission_pickup_attempted": False, "release_attempted": False})
        if status >= 400: return 1
        if max_cycles is not None and checks >= max_cycles: return 0
        sleep_fn(30)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
