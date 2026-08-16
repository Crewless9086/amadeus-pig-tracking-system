"""Fail-closed, staging-only promotion boundary for the local CORE runtime."""

from __future__ import annotations

import hashlib
import base64
import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path


RECEIPT_VERSION = "charlie_isolated_validation_receipt_v1"
STAGING_VERSION = "charlie_core_staging_v1"
TASK_NAME = "CHARLIE CORE Runner Watchdog"


class RuntimeStagingError(RuntimeError):
    def __init__(self, status, **evidence):
        super().__init__(status)
        self.status = status
        self.evidence = evidence


def plan_runtime_staging(
    *, source_ref, runtime_root, execution_root, state_root, receipt_path,
    receipt_sha256, expected_runtime_head, expected_execution_head,
    expected_manifest_commit, task_reader=None, runner=subprocess.run,
):
    source_ref = str(source_ref or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", source_ref):
        raise RuntimeStagingError("immutable_source_ref_required")
    runtime_root, execution_root, state_root = map(
        lambda value: Path(value).resolve(), (runtime_root, execution_root, state_root)
    )
    resolved = _git(runtime_root, ["rev-parse", "--verify", f"{source_ref}^{{commit}}"], runner)
    if resolved != source_ref:
        raise RuntimeStagingError("source_ref_resolution_mismatch", resolved=resolved)
    execution_resolved = _git(
        execution_root, ["rev-parse", "--verify", f"{source_ref}^{{commit}}"], runner
    )
    if execution_resolved != source_ref:
        raise RuntimeStagingError(
            "source_ref_resolution_mismatch", root=str(execution_root), resolved=execution_resolved
        )
    runtime = _worktree_identity(runtime_root, runner)
    execution = _worktree_identity(execution_root, runner)
    manifest_path = state_root / "runtime-manifest.json"
    stop_path = state_root / "supervisor.stop"
    supervisor_path = state_root / "supervisor.json"
    watchdog_path = state_root / "watchdog.json"
    manifest = _read_json(manifest_path, "runtime_manifest_missing_or_invalid")
    if not stop_path.is_file():
        raise RuntimeStagingError("governed_stop_marker_required")
    receipt_path = Path(receipt_path).resolve()
    receipt_digest = _sha256(receipt_path)
    if not re.fullmatch(r"[0-9a-f]{64}", str(receipt_sha256 or "").lower()):
        raise RuntimeStagingError("sealed_receipt_digest_required")
    if receipt_digest != str(receipt_sha256).lower():
        raise RuntimeStagingError("sealed_receipt_digest_mismatch")
    receipt = _read_json(receipt_path, "isolated_validation_receipt_invalid")
    _validate_receipt(receipt, source_ref)
    _validate_expected_rollback(
        runtime, execution, manifest, expected_runtime_head,
        expected_execution_head, expected_manifest_commit,
    )
    supervisor = _read_json(supervisor_path, "supervisor_state_missing_or_invalid")
    watchdog = _read_json(watchdog_path, "watchdog_state_missing_or_invalid")
    if supervisor.get("status") != "supervisor_stopped":
        raise RuntimeStagingError("supervisor_not_governed_stopped")
    if watchdog.get("status") != "governed_stop_active":
        raise RuntimeStagingError("watchdog_governed_stop_not_active")
    task = (task_reader or read_watchdog_task)()
    _validate_task(task, runtime_root)
    rollback = {
        "version": STAGING_VERSION,
        "runtime": runtime,
        "execution": execution,
        "manifest": manifest,
        "manifest_bytes_b64": base64.b64encode(manifest_path.read_bytes()).decode("ascii"),
        "manifest_sha256": _sha256(manifest_path),
        "stop_marker_sha256": _sha256(stop_path),
        "supervisor_state_sha256": _sha256(supervisor_path),
        "watchdog_state_sha256": _sha256(watchdog_path),
        "task_ownership": task,
        "task_ownership_sha256": _payload_sha256(task),
    }
    if not all((runtime.get("head"), execution.get("head"), manifest.get("promoted_commit"))):
        raise RuntimeStagingError("rollback_identity_incomplete")
    return {
        "success": True,
        "status": "runtime_staging_plan_ready",
        "source_ref": source_ref,
        "runtime_root": str(runtime_root),
        "execution_root": str(execution_root),
        "state_root": str(state_root),
        "receipt_sha256": receipt_digest,
        "receipt_path": str(receipt_path),
        "rollback": rollback,
        "zero_effect": True,
        "watchdog_action": "none",
    }


def stage_runtime(plan, *, task_reader=None, runner=subprocess.run):
    if not isinstance(plan, dict) or plan.get("status") != "runtime_staging_plan_ready":
        raise RuntimeStagingError("validated_staging_plan_required")
    state_root = Path(plan["state_root"])
    runtime_root = Path(plan["runtime_root"])
    execution_root = Path(plan["execution_root"])
    source_ref = plan["source_ref"]
    lane_id = uuid.uuid4().hex
    lane_path = state_root / "release-staging.lock"
    ledger_dir = state_root / "promotion-ledger"
    lane = {
        "version": STAGING_VERSION,
        "lane_id": lane_id,
        "source_ref": source_ref,
        "mission_id": "CMQ-20260813-05",
        "acquired_at": _now(),
        "status": "staging_acquired",
    }
    descriptor = _exclusive_json(lane_path, lane)
    os.close(descriptor)
    rollback_path = ledger_dir / f"{lane_id}-rollback.json"
    result_path = ledger_dir / f"{lane_id}-result.json"
    mutated = False
    try:
        if _sha256(plan["receipt_path"]) != plan["receipt_sha256"]:
            raise RuntimeStagingError("sealed_receipt_changed")
        _validate_receipt(
            _read_json(plan["receipt_path"], "isolated_validation_receipt_invalid"),
            source_ref,
        )
        task = (task_reader or read_watchdog_task)()
        _validate_task(task, runtime_root)
        if _payload_sha256(task) != plan["rollback"]["task_ownership_sha256"]:
            raise RuntimeStagingError("scheduled_task_ownership_changed")
        runtime_now = _worktree_identity(runtime_root, runner)
        execution_now = _worktree_identity(execution_root, runner)
        if runtime_now != plan["rollback"]["runtime"] or execution_now != plan["rollback"]["execution"]:
            raise RuntimeStagingError("worktree_identity_changed_before_staging")
        _atomic_json(rollback_path, {
            **plan["rollback"], "lane_id": lane_id, "source_ref": source_ref,
            "recorded_at": _now(), "status": "rollback_tuple_recorded",
        })
        if _sha256(state_root / "supervisor.stop") != plan["rollback"]["stop_marker_sha256"]:
            raise RuntimeStagingError("governed_stop_marker_changed")
        _validate_governed_state_unchanged(state_root, plan["rollback"])
        _git_mutate(runtime_root, ["switch", "--detach", source_ref], runner)
        mutated = True
        _git_mutate(execution_root, ["switch", "--detach", source_ref], runner)
        if _git(runtime_root, ["rev-parse", "HEAD"], runner) != source_ref:
            raise RuntimeStagingError("runtime_revision_readback_mismatch")
        if _git(execution_root, ["rev-parse", "HEAD"], runner) != source_ref:
            raise RuntimeStagingError("execution_revision_readback_mismatch")
        if _sha256(state_root / "supervisor.stop") != plan["rollback"]["stop_marker_sha256"]:
            raise RuntimeStagingError("governed_stop_marker_changed")
        _validate_governed_state_unchanged(state_root, plan["rollback"])
        task_after = (task_reader or read_watchdog_task)()
        if _payload_sha256(task_after) != plan["rollback"]["task_ownership_sha256"]:
            raise RuntimeStagingError("scheduled_task_ownership_changed")
        manifest = {
            "version": "charlie_core_runtime_v1",
            "promoted_commit": source_ref,
            "promoted_branch": "(detached)",
            "runtime_root": str(runtime_root),
            "execution_root": str(execution_root),
            "promoted_at": _now(),
            "source": "isolated_receipt_staging",
            "validation_receipt_sha256": plan["receipt_sha256"],
            "release_lane_id": lane_id,
            "governed_stop_preserved": True,
        }
        _atomic_json(state_root / "runtime-manifest.json", manifest)
        result = {
            "version": STAGING_VERSION, "success": True,
            "status": "runtime_staged_governed_stop_preserved",
            "lane_id": lane_id, "source_ref": source_ref,
            "runtime_head": source_ref, "execution_head": source_ref,
            "manifest": manifest, "rollback_path": str(rollback_path),
            "watchdog_action": "none", "core_started": False,
            "completed_at": _now(),
        }
        _atomic_json(result_path, result)
        return result
    except Exception as exc:
        recovery_error = None
        if mutated:
            try:
                _restore_rollback(plan, runner)
            except Exception as recovery_exc:
                recovery_error = {
                    "status": getattr(recovery_exc, "status", "rollback_recovery_failed"),
                    "error_type": recovery_exc.__class__.__name__,
                }
        failure = {
            "version": STAGING_VERSION, "success": False,
            "status": getattr(exc, "status", "runtime_staging_failed"),
            "lane_id": lane_id, "source_ref": source_ref,
            "error_type": exc.__class__.__name__, "failed_at": _now(),
            "rollback_path": str(rollback_path), "watchdog_action": "none",
            "rollback_recovery": recovery_error or {"status": "not_required_or_completed"},
        }
        _atomic_json(result_path, failure)
        raise
    finally:
        try:
            lane_path.replace(ledger_dir / f"{lane_id}-lane.json")
        except OSError:
            pass


def read_watchdog_task(runner=subprocess.run):
    script = (
        "$ErrorActionPreference='Stop';$t=@(Get-ScheduledTask -TaskName 'CHARLIE CORE Runner Watchdog');"
        "$rows=@($t|ForEach-Object{$a=@($_.Actions);[pscustomobject]@{task_name=$_.TaskName;"
        "state=[string]$_.State;action_count=$a.Count;execute=[string]$a[0].Execute;"
        "arguments=[string]$a[0].Arguments;working_directory=[string]$a[0].WorkingDirectory}});"
        "$rows|ConvertTo-Json -Compress"
    )
    completed = runner(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=15, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeStagingError("scheduled_task_ownership_unreadable")
    try:
        rows = json.loads(completed.stdout or "[]")
    except ValueError as exc:
        raise RuntimeStagingError("scheduled_task_ownership_invalid") from exc
    return rows if isinstance(rows, list) else [rows]


def _validate_receipt(receipt, source_ref):
    isolation = receipt.get("isolation") if isinstance(receipt.get("isolation"), dict) else {}
    if (
        receipt.get("version") != RECEIPT_VERSION
        or receipt.get("source_commit") != source_ref
        or receipt.get("status") != "passed"
        or isolation.get("boundary") != "disposable_process_boundary"
        or isolation.get("host_processes_visible") is not False
        or int(isolation.get("outside_boundary_targets") or 0) != 0
        or int(receipt.get("focused_passed") or 0) <= 0
        or int(receipt.get("full_suite_passed") or 0) <= 0
    ):
        raise RuntimeStagingError("isolated_validation_receipt_not_authorized")


def _validate_task(rows, runtime_root):
    if not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeStagingError("scheduled_task_ownership_ambiguous")
    row = rows[0] if isinstance(rows[0], dict) else {}
    execute = Path(str(row.get("execute") or "")).name.casefold()
    working = str(Path(str(row.get("working_directory") or "")).resolve()).casefold()
    arguments = str(row.get("arguments") or "").casefold()
    if (
        row.get("task_name") != TASK_NAME or int(row.get("action_count") or 0) != 1
        or execute != "pythonw.exe" or working != str(runtime_root).casefold()
        or str(row.get("state") or "").casefold() == "running"
        or "charlie_runner_watchdog.py" not in arguments
        or str(runtime_root).casefold() not in arguments
    ):
        raise RuntimeStagingError("scheduled_task_ownership_ambiguous")


def _validate_expected_rollback(runtime, execution, manifest, expected_runtime,
                                expected_execution, expected_manifest):
    expected = (expected_runtime, expected_execution, expected_manifest)
    if not all(re.fullmatch(r"[0-9a-f]{40}", str(item or "").lower()) for item in expected):
        raise RuntimeStagingError("exact_expected_rollback_tuple_required")
    actual = (runtime.get("head"), execution.get("head"), manifest.get("promoted_commit"))
    if tuple(str(item).lower() for item in actual) != tuple(str(item).lower() for item in expected):
        raise RuntimeStagingError("current_state_contradicts_expected_rollback", actual=actual)


def _validate_governed_state_unchanged(state_root, rollback):
    if _sha256(state_root / "supervisor.json") != rollback["supervisor_state_sha256"]:
        raise RuntimeStagingError("supervisor_state_changed")
    if _sha256(state_root / "watchdog.json") != rollback["watchdog_state_sha256"]:
        raise RuntimeStagingError("watchdog_state_changed")


def _restore_rollback(plan, runner):
    rollback = plan["rollback"]
    _git_mutate(Path(plan["runtime_root"]), ["switch", "--detach", rollback["runtime"]["head"]], runner)
    _git_mutate(Path(plan["execution_root"]), ["switch", "--detach", rollback["execution"]["head"]], runner)
    _atomic_bytes(
        Path(plan["state_root"]) / "runtime-manifest.json",
        base64.b64decode(rollback["manifest_bytes_b64"], validate=True),
    )


def _worktree_identity(root, runner):
    if _git(root, ["status", "--porcelain"], runner):
        raise RuntimeStagingError("runtime_worktree_dirty", root=str(root))
    return {
        "root": str(root), "head": _git(root, ["rev-parse", "HEAD"], runner),
        "branch": _git(root, ["branch", "--show-current"], runner),
    }


def _git(root, args, runner):
    completed = runner(["git", *args], cwd=str(root), capture_output=True, text=True, timeout=30, check=False)
    if completed.returncode != 0:
        raise RuntimeStagingError("git_read_failed", command=args)
    return str(completed.stdout or "").strip()


def _git_mutate(root, args, runner):
    completed = runner(["git", *args], cwd=str(root), capture_output=True, text=True, timeout=60, check=False)
    if completed.returncode != 0:
        raise RuntimeStagingError("git_staging_failed", command=args)


def _read_json(path, status):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeStagingError(status) from exc
    if not isinstance(value, dict):
        raise RuntimeStagingError(status)
    return value


def _sha256(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError as exc:
        raise RuntimeStagingError("required_evidence_unreadable", path=str(path)) from exc


def _payload_sha256(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _exclusive_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeStagingError("release_lane_already_owned") from exc
    with os.fdopen(os.dup(descriptor), "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)
    return descriptor


def _atomic_json(path, payload):
    _atomic_bytes(path, json.dumps(payload, indent=2).encode("utf-8"))


def _atomic_bytes(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _now():
    return datetime.now(timezone.utc).isoformat()
