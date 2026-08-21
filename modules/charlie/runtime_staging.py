"""Fail-closed, staging-only promotion boundary for the local CORE runtime."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from modules.charlie.validation_receipt import (
    RECEIPT_VERSION,
    ValidationReceiptError,
    validate_validation_receipt,
)


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
    if (state_root / "activation.lock").exists():
        raise RuntimeStagingError("activation_lane_active")
    if (state_root / "activation-reconciliation.lock").exists():
        raise RuntimeStagingError("activation_reconciliation_lane_active")
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
    receipt_identity = _validate_receipt(receipt, source_ref, _read_receipt_key(receipt_key_path))
    _validate_receipt_history(state_root, receipt_path, receipt_identity, receipt_digest)
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
    if watchdog.get("version") == "charlie_activation_recovery_projection_v1":
        _validate_recovery_projection(watchdog, state_root)
    task = (task_reader or read_watchdog_task)()
    task_mode = _validate_task(task, runtime_root, allow_historical=True)
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
        "task_action_mode": task_mode,
        "task_launcher_ownership": (
            _launcher_task(task, runtime_root) if task_mode == "historical_inline_disabled" else task
        ),
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


def _validate_recovery_projection(projection, state_root):
    activation_id = str(projection.get("recovered_activation_id") or "")
    if not re.fullmatch(r"[0-9a-f]{32}", activation_id):
        raise RuntimeStagingError("watchdog_recovery_projection_identity_invalid")
    try:
        key = (state_root / "activation-authority.key").read_bytes()
    except OSError as exc:
        raise RuntimeStagingError("watchdog_recovery_projection_key_unavailable") from exc
    if len(key) < 32 or not hmac.compare_digest(
            str(projection.get("projection_hmac_sha256") or ""),
            _record_hmac(projection, key, "projection_hmac_sha256")):
        raise RuntimeStagingError("watchdog_recovery_projection_signature_invalid")
    ledger = state_root / "activation-ledger"
    expected = {
        "historical_failure": ledger / f"{activation_id}-failure.json",
        "recovered_packet": ledger / f"{activation_id}-recovered-activation-packet.json",
        "recovered_lane": ledger / f"{activation_id}-lane-recovered.json",
        "rollback": ledger / f"{activation_id}-rollback.json",
        "recovery_completion": ledger / f"{activation_id}-recovery-completed.json",
        "reconciled": ledger / f"{activation_id}-reconciled.json",
    }
    for field, path in expected.items():
        path_field = f"{field}_path"
        digest_field = f"{field}_sha256"
        if (str(Path(str(projection.get(path_field) or "")).resolve()).casefold()
                != str(path.resolve()).casefold()
                or not path.is_file()
                or _sha256(path) != projection.get(digest_field)):
            raise RuntimeStagingError("watchdog_recovery_projection_archive_mismatch", field=field)
    failure = _read_json(expected["historical_failure"], "activation_failure_record_invalid")
    completion = _read_json(expected["recovery_completion"], "activation_recovery_completion_invalid")
    reconciled = _read_json(expected["reconciled"], "activation_reconciliation_record_invalid")
    for record, signature_field, status in (
        (failure, "failure_hmac_sha256", "activation_failure_preserved"),
        (completion, "completion_hmac_sha256", "activation_recovery_completed"),
        (reconciled, "recovery_hmac_sha256", "governed_stop_reconciliation_pending"),
    ):
        if (record.get("activation_id") != activation_id or record.get("status") != status
                or not hmac.compare_digest(
                    str(record.get(signature_field) or ""),
                    _record_hmac(record, key, signature_field))):
            raise RuntimeStagingError("watchdog_recovery_projection_record_invalid")
    if (any(completion.get(name) != projection.get(name) for name in (
            "historical_failure_sha256", "recovered_packet_sha256", "rollback_sha256"
            ))
            or completion.get("lane_sha256") != projection.get("recovered_lane_sha256")):
        raise RuntimeStagingError("watchdog_recovery_projection_completion_mismatch")


def _record_hmac(record, key, signature_field):
    unsigned = {k: v for k, v in record.items() if k != signature_field}
    return hmac.new(key, json.dumps(
        unsigned, sort_keys=True, separators=(",", ":")
    ).encode("utf-8"), hashlib.sha256).hexdigest()


def stage_runtime(plan, *, task_reader=None, task_writer=None, runner=subprocess.run,
                  git_safety_checker=None):
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
        if ((state_root / "activation.lock").exists()
                or (state_root / "activation-reconciliation.lock").exists()):
            raise RuntimeStagingError("activation_lane_active")
        if _sha256(plan["receipt_path"]) != plan["receipt_sha256"]:
            raise RuntimeStagingError("sealed_receipt_changed")
        receipt_key_path = state_root / "validation-receipt.key"
        if _sha256(receipt_key_path) != plan["rollback"]["receipt_key_sha256"]:
            raise RuntimeStagingError("validation_receipt_authority_changed")
        receipt_identity = _validate_receipt(
            _read_json(plan["receipt_path"], "isolated_validation_receipt_invalid"),
            source_ref, _read_receipt_key(receipt_key_path),
        )
        _validate_receipt_history(
            state_root, Path(plan["receipt_path"]), receipt_identity, plan["receipt_sha256"]
        )
        task = (task_reader or read_watchdog_task)()
        task_mode = _validate_task(task, runtime_root, allow_historical=True)
        if _payload_sha256(task) != plan["rollback"]["task_ownership_sha256"]:
            raise RuntimeStagingError("scheduled_task_ownership_changed")
        if task_mode != plan["rollback"]["task_action_mode"]:
            raise RuntimeStagingError("scheduled_task_action_mode_changed")
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
        consumption_path = (
            state_root / "validation-consumptions" / f"{receipt_identity['validation_id']}.json"
        )
        consumption_descriptor = _exclusive_json(consumption_path, {
            "version": RECEIPT_VERSION, "validation_id": receipt_identity["validation_id"],
            "receipt_sha256": plan["receipt_sha256"], "source_commit": source_ref,
            "lane_id": lane_id, "status": "consumed_for_staging", "consumed_at": _now(),
        })
        os.close(consumption_descriptor)
        _atomic_json(rollback_path, {
            **plan["rollback"], "lane_id": lane_id, "source_ref": source_ref,
            "recorded_at": _now(), "status": "rollback_tuple_recorded",
        })
        if _sha256(state_root / "supervisor.stop") != plan["rollback"]["stop_marker_sha256"]:
            raise RuntimeStagingError("governed_stop_marker_changed")
        _validate_governed_state_unchanged(state_root, plan["rollback"])
        mutated = True
        if task_mode == "historical_inline_disabled":
            (task_writer or write_watchdog_task_action)(
                plan["rollback"]["task_launcher_ownership"], runner=runner
            )
            task = (task_reader or read_watchdog_task)()
            _validate_task(task, runtime_root)
            if _payload_sha256(task) != _payload_sha256(
                    plan["rollback"]["task_launcher_ownership"]):
                raise RuntimeStagingError("scheduled_task_launcher_readback_mismatch")
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
        expected_task = plan["rollback"]["task_launcher_ownership"]
        _validate_task(task_after, runtime_root)
        if _payload_sha256(task_after) != _payload_sha256(expected_task):
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
            "validation_receipt_sha256": plan["receipt_sha256"],
            "validation_consumption_path": str(consumption_path),
            "watchdog_action": (
                "migrated_disabled_launcher"
                if task_mode == "historical_inline_disabled" else "none"
            ),
            "scheduled_task_sha256": _payload_sha256(task_after),
            "scheduled_task_state": task_after[0]["state"],
            "core_started": False,
            "completed_at": _now(),
        }
        _atomic_json(result_path, result)
        return result
    except Exception as exc:
        if mutated:
            try:
                _restore_rollback(plan, runner, task_reader=task_reader, task_writer=task_writer)
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
        "task_path=[string]$_.TaskPath;state=[string]$_.State;action_count=$a.Count;execute=[string]$a[0].Execute;"
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


def write_watchdog_task_action(rows, *, runner=subprocess.run):
    """Replace only the watchdog action and force the task to remain disabled."""
    if not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeStagingError("scheduled_task_restore_tuple_invalid")
    row = rows[0]
    encoded = base64.b64encode(json.dumps(row).encode("utf-8")).decode("ascii")
    script = (
        "$ErrorActionPreference='Stop';"
        f"$r=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}'))|ConvertFrom-Json;"
        "$a=New-ScheduledTaskAction -Execute $r.execute -Argument $r.arguments "
        "-WorkingDirectory $r.working_directory;"
        "Set-ScheduledTask -TaskName $r.task_name -TaskPath $r.task_path -Action $a|Out-Null;"
        "Disable-ScheduledTask -TaskName $r.task_name -TaskPath $r.task_path|Out-Null"
    )
    completed = runner(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       capture_output=True, text=True, timeout=30, check=False)
    if completed.returncode != 0:
        raise RuntimeStagingError("scheduled_task_action_write_failed")


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
    task_writer=None, runner=subprocess.run, git_safety_checker=None,
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
    _validate_task(task, runtime_root, allow_historical=True)
    allowed_task_digests = {
        rollback.get("task_ownership_sha256"),
        _payload_sha256(rollback.get("task_launcher_ownership")),
    }
    if _payload_sha256(task) not in allowed_task_digests:
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
    _restore_rollback(recovery_plan, runner, task_reader=task_reader, task_writer=task_writer)
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
    try:
        return validate_validation_receipt(receipt, source_ref, receipt_key)
    except ValidationReceiptError as exc:
        raise RuntimeStagingError(str(exc)) from exc


def _validate_receipt_history(state_root, receipt_path, identity, receipt_sha256):
    validation_id = identity["validation_id"]
    canonical_receipt = state_root / "validation-identities" / f"{validation_id}.json"
    if receipt_path.resolve() != canonical_receipt.resolve():
        raise RuntimeStagingError("validation_receipt_path_not_canonical")
    if _sha256(canonical_receipt) != receipt_sha256:
        raise RuntimeStagingError("validation_identity_record_invalid")
    if (state_root / "validation-consumptions" / f"{validation_id}.json").exists():
        raise RuntimeStagingError("validation_receipt_replay_rejected")
    ledger = state_root / "promotion-ledger"
    if ledger.is_dir():
        for path in ledger.glob("*-result.json"):
            record = _read_json(path, "promotion_result_invalid")
            if record.get("success") is True and record.get("validation_receipt_sha256") == receipt_sha256:
                raise RuntimeStagingError("validation_receipt_replay_rejected")


def _read_receipt_key(path):
    try:
        key = Path(path).read_bytes()
    except OSError as exc:
        raise RuntimeStagingError("validation_receipt_authority_unavailable") from exc
    if len(key) < 32:
        raise RuntimeStagingError("validation_receipt_authority_invalid")
    return key


def _validate_task(rows, runtime_root, allow_historical=False):
    if not isinstance(rows, list) or len(rows) != 1:
        raise RuntimeStagingError("scheduled_task_ownership_ambiguous")
    row = rows[0] if isinstance(rows[0], dict) else {}
    canonical_root = runtime_root.parent.parent
    expected_execute = canonical_root / "venv" / "Scripts" / "pythonw.exe"
    expected_launcher = runtime_root / "scripts" / "charlie_runner_task_launcher.py"
    expected_arguments = f'"{expected_launcher}"'
    execute = str(Path(str(row.get("execute") or "")).resolve()).casefold()
    working = str(Path(str(row.get("working_directory") or "")).resolve()).casefold()
    arguments = str(row.get("arguments") or "").casefold()
    common_valid = (
        row.get("task_name") != TASK_NAME or int(row.get("action_count") or 0) != 1
        or execute != str(expected_execute.resolve()).casefold()
        or working != str(runtime_root).casefold()
        or str(row.get("state") or "").casefold() not in {"ready", "disabled"}
    )
    if common_valid:
        raise RuntimeStagingError("scheduled_task_ownership_ambiguous")
    if arguments == expected_arguments.casefold():
        return "launcher"
    watchdog = str((runtime_root / "scripts" / "charlie_runner_watchdog.py").resolve()).casefold()
    env_file = str((canonical_root / ".env").resolve()).casefold()
    if (allow_historical and str(row.get("state") or "").casefold() == "disabled"
            and arguments.lstrip().startswith("-c ")
            and watchdog in arguments and env_file in arguments):
        return "historical_inline_disabled"
    raise RuntimeStagingError("scheduled_task_ownership_ambiguous")


def _launcher_task(rows, runtime_root):
    row = dict(rows[0])
    row["state"] = "Disabled"
    row["arguments"] = f'"{runtime_root / "scripts" / "charlie_runner_task_launcher.py"}"'
    return [row]


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


def _restore_rollback(plan, runner, *, task_reader=None, task_writer=None):
    rollback = plan["rollback"]
    errors = []
    try:
        current = (task_reader or read_watchdog_task)()
        original = rollback["task_ownership"]
        if _payload_sha256(current) != rollback["task_ownership_sha256"]:
            (task_writer or write_watchdog_task_action)(original, runner=runner)
        restored = (task_reader or read_watchdog_task)()
        _validate_task(restored, Path(plan["runtime_root"]), allow_historical=True)
        if _payload_sha256(restored) != rollback["task_ownership_sha256"]:
            raise RuntimeStagingError("scheduled_task_rollback_readback_mismatch")
    except Exception as exc:
        errors.append({"component": "scheduled_task", "status": getattr(exc, "status", exc.__class__.__name__)})
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


_GOVERNED_LFS_CONFIG = {
    "filter.lfs.clean": "git-lfs clean -- %f",
    "filter.lfs.smudge": "git-lfs smudge -- %f",
    "filter.lfs.process": "git-lfs filter-process",
    "filter.lfs.required": "true",
}
_GOVERNED_LFS_SCOPES = frozenset({"system", "global"})
_TRUSTED_GIT_EXECUTABLE_DIRS = (
    (Path("C:/Program Files/Git/cmd"), Path("C:/Program Files (x86)/Git/cmd"))
    if os.name == "nt"
    else (Path("/usr/bin"), Path("/usr/local/bin"), Path("/opt/homebrew/bin"))
)


def _resolved_sibling_executables(left, right):
    left_path = shutil.which(left)
    right_path = shutil.which(right)
    if not left_path or not right_path:
        return False
    try:
        left_path = Path(left_path).resolve(strict=True)
        right_path = Path(right_path).resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    trusted_directories = set()
    for candidate in _TRUSTED_GIT_EXECUTABLE_DIRS:
        try:
            trusted_directories.add(candidate.resolve(strict=True))
        except (OSError, RuntimeError):
            continue
    if not trusted_directories:
        return None
    return (
        left_path
        if (
        left_path.is_file()
        and right_path.is_file()
        and left_path.parent == right_path.parent
        and left_path.parent in trusted_directories
        and left_path.name.lower() in {"git", "git.exe"}
        and right_path.name.lower() in {"git-lfs", "git-lfs.exe"}
        )
        else None
    )


def inspect_git_checkout_safety(root, runner=subprocess.run):
    git_executable = _resolved_sibling_executables("git", "git-lfs")
    if not git_executable:
        raise RuntimeStagingError("git_executable_checkout_extension_present", root=str(root))
    completed = runner(
        [str(git_executable), "config", "-z", "--show-scope", "--show-origin", "--list"],
        cwd=str(root), capture_output=True, text=True, timeout=30, check=False,
    )
    if completed.returncode not in (0, 1):
        raise RuntimeStagingError("git_checkout_extensions_unreadable", root=str(root))
    governed_lfs = set()
    fields = str(completed.stdout or "").split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    if len(fields) % 3:
        raise RuntimeStagingError("git_checkout_extensions_unreadable", root=str(root))
    for offset in range(0, len(fields), 3):
        scope, _origin, setting = fields[offset:offset + 3]
        if "\n" not in setting:
            raise RuntimeStagingError("git_checkout_extensions_unreadable", root=str(root))
        key, value = setting.split("\n", 1)
        key = key.lower()
        if not (
            key.startswith("filter.")
            or key in {"core.hookspath", "core.fsmonitor"}
            or key.startswith("include.")
            or key.startswith("includeif.")
        ):
            continue
        if (
            scope not in _GOVERNED_LFS_SCOPES
            or key not in _GOVERNED_LFS_CONFIG
            or value != _GOVERNED_LFS_CONFIG[key]
        ):
            raise RuntimeStagingError("git_executable_checkout_extension_present", root=str(root))
        governed_lfs.add(key)
    if governed_lfs:
        if governed_lfs != set(_GOVERNED_LFS_CONFIG):
            raise RuntimeStagingError("git_executable_checkout_extension_present", root=str(root))
    completed = runner(
        [str(git_executable), "rev-parse", "--git-path", "hooks/post-checkout"],
        cwd=str(root), capture_output=True, text=True, timeout=30, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeStagingError("git_read_failed", command=["rev-parse", "--git-path", "hooks/post-checkout"])
    hook = str(completed.stdout or "").strip()
    hook_path = Path(hook)
    if not hook_path.is_absolute():
        hook_path = root / hook_path
    if hook_path.is_file():
        raise RuntimeStagingError("git_post_checkout_hook_present", root=str(root))
    return {
        "extensions": "governed_git_lfs" if governed_lfs else "none",
        "post_checkout_hook": "absent",
    }


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
