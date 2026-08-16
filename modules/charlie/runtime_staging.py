"""Fail-closed, staging-only promotion boundary for the local CORE runtime."""

from __future__ import annotations

import base64
import hashlib
import hmac
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
    expected_task_sha256=None, git_safety_checker=None,
):
    source_ref = str(source_ref or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", source_ref):
        raise RuntimeStagingError("immutable_source_ref_required")
    runtime_root, execution_root, state_root = map(
        lambda value: Path(value).resolve(), (runtime_root, execution_root, state_root)
    )
    _validate_target_roots(runtime_root, execution_root, state_root)
    git_safety = {
        "runtime": (git_safety_checker or inspect_git_checkout_safety)(runtime_root, runner),
        "execution": (git_safety_checker or inspect_git_checkout_safety)(execution_root, runner),
    }
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
    if str(Path(str(manifest.get("runtime_root") or "")).resolve()).casefold() != str(runtime_root).casefold():
        raise RuntimeStagingError("manifest_runtime_root_mismatch")
    if not stop_path.is_file():
        raise RuntimeStagingError("governed_stop_marker_required")
    receipt_path = Path(receipt_path).resolve()
    receipt_digest = _sha256(receipt_path)
    if not re.fullmatch(r"[0-9a-f]{64}", str(receipt_sha256 or "").lower()):
        raise RuntimeStagingError("sealed_receipt_digest_required")
    if receipt_digest != str(receipt_sha256).lower():
        raise RuntimeStagingError("sealed_receipt_digest_mismatch")
    receipt = _read_json(receipt_path, "isolated_validation_receipt_invalid")
    receipt_key_path = state_root / "validation-receipt.key"
    _validate_receipt(receipt, source_ref, _read_receipt_key(receipt_key_path))
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
    task_sha256 = _payload_sha256(task)
    if not re.fullmatch(r"[0-9a-f]{64}", str(expected_task_sha256 or "").lower()):
        raise RuntimeStagingError("exact_scheduled_task_digest_required")
    if task_sha256 != str(expected_task_sha256).lower():
        raise RuntimeStagingError("scheduled_task_digest_mismatch")
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
        "task_ownership_sha256": task_sha256,
        "git_checkout_safety_sha256": _payload_sha256(git_safety),
        "receipt_key_sha256": _sha256(receipt_key_path),
    }
    if not all((runtime.get("head"), execution.get("head"), manifest.get("promoted_commit"))):
        raise RuntimeStagingError("rollback_identity_incomplete")
    plan = {
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
    plan["plan_sha256"] = _payload_sha256(plan)
    return plan


def stage_runtime(plan, *, task_reader=None, runner=subprocess.run, git_safety_checker=None):
    if not isinstance(plan, dict) or plan.get("status") != "runtime_staging_plan_ready":
        raise RuntimeStagingError("validated_staging_plan_required")
    supplied_digest = plan.get("plan_sha256")
    unsigned = {key: value for key, value in plan.items() if key != "plan_sha256"}
    if supplied_digest != _payload_sha256(unsigned):
        raise RuntimeStagingError("staging_plan_digest_mismatch")
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
    recovery_error = None
    try:
        if _sha256(plan["receipt_path"]) != plan["receipt_sha256"]:
            raise RuntimeStagingError("sealed_receipt_changed")
        receipt_key_path = state_root / "validation-receipt.key"
        if _sha256(receipt_key_path) != plan["rollback"]["receipt_key_sha256"]:
            raise RuntimeStagingError("validation_receipt_authority_changed")
        _validate_receipt(
            _read_json(plan["receipt_path"], "isolated_validation_receipt_invalid"),
            source_ref, _read_receipt_key(receipt_key_path),
        )
        task = (task_reader or read_watchdog_task)()
        _validate_task(task, runtime_root)
        if _payload_sha256(task) != plan["rollback"]["task_ownership_sha256"]:
            raise RuntimeStagingError("scheduled_task_ownership_changed")
        git_safety = {
            "runtime": (git_safety_checker or inspect_git_checkout_safety)(runtime_root, runner),
            "execution": (git_safety_checker or inspect_git_checkout_safety)(execution_root, runner),
        }
        if _payload_sha256(git_safety) != plan["rollback"]["git_checkout_safety_sha256"]:
            raise RuntimeStagingError("git_checkout_safety_changed")
        runtime_now = _worktree_identity(runtime_root, runner)
        execution_now = _worktree_identity(execution_root, runner)
        if runtime_now != plan["rollback"]["runtime"] or execution_now != plan["rollback"]["execution"]:
            raise RuntimeStagingError("worktree_identity_changed_before_staging")
        if _sha256(state_root / "runtime-manifest.json") != plan["rollback"]["manifest_sha256"]:
            raise RuntimeStagingError("runtime_manifest_changed_before_staging")
        _atomic_json(rollback_path, {
            **plan["rollback"], "lane_id": lane_id, "source_ref": source_ref,
            "recorded_at": _now(), "status": "rollback_tuple_recorded",
        })
        if _sha256(state_root / "supervisor.stop") != plan["rollback"]["stop_marker_sha256"]:
            raise RuntimeStagingError("governed_stop_marker_changed")
        _validate_governed_state_unchanged(state_root, plan["rollback"])
        mutated = True
        _git_mutate(runtime_root, ["switch", "--detach", source_ref], runner)
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
        if _sha256(state_root / "runtime-manifest.json") != plan["rollback"]["manifest_sha256"]:
            raise RuntimeStagingError("runtime_manifest_changed_during_staging")
        if _sha256(state_root / "supervisor.stop") != plan["rollback"]["stop_marker_sha256"]:
            raise RuntimeStagingError("governed_stop_marker_changed")
        _validate_governed_state_unchanged(state_root, plan["rollback"])
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
            "observed_manifest_sha256": _optional_sha256(state_root / "runtime-manifest.json"),
            "rollback_sha256": _optional_sha256(rollback_path),
        }
        _atomic_json(result_path, failure)
        raise
    finally:
        if not mutated or recovery_error is None:
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


def read_staging_state(state_root):
    state_root = Path(state_root).resolve()
    lane_path = state_root / "release-staging.lock"
    if not lane_path.is_file():
        return {"success": True, "status": "no_active_release_lane", "zero_effect": True}
    lane = _read_json(lane_path, "release_lane_invalid")
    lane_id = str(lane.get("lane_id") or "")
    if not re.fullmatch(r"[0-9a-f]{32}", lane_id):
        raise RuntimeStagingError("release_lane_invalid")
    rollback_path = state_root / "promotion-ledger" / f"{lane_id}-rollback.json"
    result_path = state_root / "promotion-ledger" / f"{lane_id}-result.json"
    return {
        "success": True,
        "status": "release_lane_recovery_required",
        "zero_effect": True,
        "lane": lane,
        "lane_sha256": _sha256(lane_path),
        "rollback_path": str(rollback_path),
        "rollback_sha256": _sha256(rollback_path),
        "failure_result_path": str(result_path) if result_path.is_file() else None,
        "failure_result_sha256": _sha256(result_path) if result_path.is_file() else None,
    }


def recover_runtime_staging(
    *, state_root, lane_id, rollback_sha256, failure_result_sha256=None, task_reader=None,
    runner=subprocess.run, git_safety_checker=None,
):
    state_root = Path(state_root).resolve()
    evidence = read_staging_state(state_root)
    lane = evidence.get("lane") or {}
    if lane.get("lane_id") != lane_id:
        raise RuntimeStagingError("release_lane_identity_mismatch")
    if evidence.get("rollback_sha256") != str(rollback_sha256 or "").lower():
        raise RuntimeStagingError("rollback_digest_mismatch")
    rollback = _read_json(evidence["rollback_path"], "rollback_tuple_invalid")
    if rollback.get("lane_id") != lane_id or rollback.get("source_ref") != lane.get("source_ref"):
        raise RuntimeStagingError("rollback_lane_binding_mismatch")
    runtime_root = Path(rollback.get("runtime", {}).get("root", "")).resolve()
    execution_root = Path(rollback.get("execution", {}).get("root", "")).resolve()
    _validate_target_roots(runtime_root, execution_root, state_root)
    task = (task_reader or read_watchdog_task)()
    _validate_task(task, runtime_root)
    if _payload_sha256(task) != rollback.get("task_ownership_sha256"):
        raise RuntimeStagingError("scheduled_task_ownership_changed")
    current_identities = {}
    for name, root in (("runtime", runtime_root), ("execution", execution_root)):
        (git_safety_checker or inspect_git_checkout_safety)(root, runner)
        current = _worktree_identity(root, runner)
        allowed = (
            rollback[name],
            {"root": str(root), "head": lane["source_ref"], "branch": ""},
        )
        if current not in allowed:
            raise RuntimeStagingError("worktree_state_not_authorized_for_recovery", worktree=name)
        current_identities[name] = current
    if _sha256(state_root / "supervisor.stop") != rollback.get("stop_marker_sha256"):
        raise RuntimeStagingError("governed_stop_marker_changed")
    _validate_governed_state_unchanged(state_root, rollback)
    current_manifest_sha256 = _sha256(state_root / "runtime-manifest.json")
    allowed_manifest_digests = {rollback.get("manifest_sha256")}
    failure_path = state_root / "promotion-ledger" / f"{lane_id}-result.json"
    if failure_path.is_file():
        actual_failure_digest = _sha256(failure_path)
        if actual_failure_digest != str(failure_result_sha256 or "").lower():
            raise RuntimeStagingError("failure_result_digest_mismatch")
        failure = _read_json(failure_path, "staging_failure_evidence_invalid")
        if (
            failure.get("lane_id") != lane_id or failure.get("source_ref") != lane.get("source_ref")
            or failure.get("success") is not False
            or str(Path(str(failure.get("rollback_path") or "")).resolve()) != str(Path(evidence["rollback_path"]).resolve())
            or failure.get("rollback_sha256") != evidence["rollback_sha256"]
        ):
            raise RuntimeStagingError("staging_failure_evidence_invalid")
        allowed_manifest_digests.add(failure.get("observed_manifest_sha256"))
    if current_manifest_sha256 not in allowed_manifest_digests:
        raise RuntimeStagingError("manifest_state_not_authorized_for_recovery")
    recovery_plan = {
        "runtime_root": str(runtime_root), "execution_root": str(execution_root),
        "state_root": str(state_root), "rollback": rollback,
    }
    _restore_rollback(recovery_plan, runner)
    if _worktree_identity(runtime_root, runner) != rollback["runtime"]:
        raise RuntimeStagingError("runtime_recovery_readback_mismatch")
    if _worktree_identity(execution_root, runner) != rollback["execution"]:
        raise RuntimeStagingError("execution_recovery_readback_mismatch")
    result = {
        "version": STAGING_VERSION, "success": True,
        "status": "runtime_staging_recovered", "lane_id": lane_id,
        "runtime_head": rollback["runtime"]["head"],
        "execution_head": rollback["execution"]["head"],
        "manifest_sha256": rollback["manifest_sha256"],
        "watchdog_action": "none", "core_started": False, "recovered_at": _now(),
    }
    ledger = state_root / "promotion-ledger"
    _atomic_json(ledger / f"{lane_id}-recovery.json", result)
    (state_root / "release-staging.lock").replace(ledger / f"{lane_id}-lane-recovered.json")
    return result


def _validate_receipt(receipt, source_ref, receipt_key):
    isolation = receipt.get("isolation") if isinstance(receipt.get("isolation"), dict) else {}
    signature = str(receipt.get("signature_hmac_sha256") or "").lower()
    unsigned = {key: value for key, value in receipt.items() if key != "signature_hmac_sha256"}
    expected_signature = hmac.new(
        receipt_key,
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if (
        receipt.get("version") != RECEIPT_VERSION
        or receipt.get("issuer") != "control_tower_isolated_validator_v1"
        or not hmac.compare_digest(signature, expected_signature)
        or receipt.get("source_commit") != source_ref
        or receipt.get("status") != "passed"
        or isolation.get("boundary") != "disposable_process_boundary"
        or isolation.get("host_processes_visible") is not False
        or int(isolation.get("outside_boundary_targets") or 0) != 0
        or int(receipt.get("focused_passed") or 0) <= 0
        or int(receipt.get("full_suite_passed") or 0) <= 0
    ):
        raise RuntimeStagingError("isolated_validation_receipt_not_authorized")


def _read_receipt_key(path):
    try:
        key = Path(path).read_bytes()
    except OSError as exc:
        raise RuntimeStagingError("validation_receipt_authority_unavailable") from exc
    if len(key) < 32:
        raise RuntimeStagingError("validation_receipt_authority_invalid")
    return key


def _validate_task(rows, runtime_root):
    if not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeStagingError("scheduled_task_ownership_ambiguous")
    row = rows[0] if isinstance(rows[0], dict) else {}
    canonical_root = runtime_root.parent.parent
    expected_execute = canonical_root / "venv" / "Scripts" / "pythonw.exe"
    expected_watchdog = runtime_root / "scripts" / "charlie_runner_watchdog.py"
    expected_env = canonical_root / ".env"
    expected_arguments = (
        '-c "from dotenv import load_dotenv; load_dotenv(r\'{0}\', override=True); '
        "import runpy,sys; sys.argv=[r'{1}','--json']; "
        "runpy.run_path(r'{1}', run_name='__main__')\""
    ).format(expected_env, expected_watchdog)
    execute = str(Path(str(row.get("execute") or "")).resolve()).casefold()
    working = str(Path(str(row.get("working_directory") or "")).resolve()).casefold()
    arguments = str(row.get("arguments") or "").casefold()
    if (
        row.get("task_name") != TASK_NAME or int(row.get("action_count") or 0) != 1
        or execute != str(expected_execute.resolve()).casefold()
        or working != str(runtime_root).casefold()
        or str(row.get("state") or "").casefold() not in {"ready", "disabled"}
        or arguments != expected_arguments.casefold()
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
    errors = []
    for name in ("runtime", "execution"):
        identity = rollback[name]
        try:
            root = Path(identity["root"])
            branch = identity.get("branch")
            if branch:
                if _git(root, ["rev-parse", f"refs/heads/{branch}"], runner) != identity["head"]:
                    raise RuntimeStagingError("rollback_branch_moved", worktree=name)
                _git_mutate(root, ["switch", branch], runner)
            else:
                _git_mutate(root, ["switch", "--detach", identity["head"]], runner)
            if _git(root, ["rev-parse", "HEAD"], runner) != identity["head"]:
                raise RuntimeStagingError("rollback_head_readback_mismatch", worktree=name)
        except Exception as exc:
            errors.append({"component": name, "status": getattr(exc, "status", exc.__class__.__name__)})
    try:
        _atomic_bytes(
            Path(plan["state_root"]) / "runtime-manifest.json",
            base64.b64decode(rollback["manifest_bytes_b64"], validate=True),
        )
        if _sha256(Path(plan["state_root"]) / "runtime-manifest.json") != rollback["manifest_sha256"]:
            raise RuntimeStagingError("rollback_manifest_readback_mismatch")
    except Exception as exc:
        errors.append({"component": "manifest", "status": getattr(exc, "status", exc.__class__.__name__)})
    if errors:
        raise RuntimeStagingError("rollback_recovery_incomplete", errors=errors)


def _validate_target_roots(runtime_root, execution_root, state_root):
    if runtime_root == execution_root or runtime_root in execution_root.parents or execution_root in runtime_root.parents:
        raise RuntimeStagingError("runtime_execution_roots_overlap")
    if runtime_root != state_root / "core-runtime-current" or execution_root != state_root / "core-execution-current":
        raise RuntimeStagingError("non_authoritative_staging_roots")


def inspect_git_checkout_safety(root, runner=subprocess.run):
    completed = runner(
        ["git", "config", "--show-origin", "--get-regexp",
         r"^(core\.hooksPath|core\.fsmonitor|filter\..*\.(process|smudge))$"],
        cwd=str(root), capture_output=True, text=True, timeout=30, check=False,
    )
    if completed.returncode not in (0, 1):
        raise RuntimeStagingError("git_checkout_extensions_unreadable", root=str(root))
    if completed.returncode == 0 and str(completed.stdout or "").strip():
        raise RuntimeStagingError("git_executable_checkout_extension_present", root=str(root))
    hook = _git(root, ["rev-parse", "--git-path", "hooks/post-checkout"], runner)
    hook_path = Path(hook)
    if not hook_path.is_absolute():
        hook_path = root / hook_path
    if hook_path.is_file():
        raise RuntimeStagingError("git_post_checkout_hook_present", root=str(root))
    return {"extensions": "none", "post_checkout_hook": "absent"}


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
    command = ["git", *args]
    if args and args[0] == "switch":
        command = ["git", "-c", "core.hooksPath=NUL", "-c", "core.fsmonitor=false", *args]
    completed = runner(command, cwd=str(root), capture_output=True, text=True, timeout=60, check=False)
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


def _optional_sha256(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


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
        stream.flush()
        os.fsync(stream.fileno())
    return descriptor


def _atomic_json(path, payload):
    _atomic_bytes(path, json.dumps(payload, indent=2).encode("utf-8"))


def _atomic_bytes(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def _now():
    return datetime.now(timezone.utc).isoformat()
