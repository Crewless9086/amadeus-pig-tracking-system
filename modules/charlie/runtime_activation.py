"""Serialized, provider-origin-only observe-only CORE activation."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import shlex
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from modules.charlie.runtime_staging import read_watchdog_task
from modules.charlie.process_ownership import (
    normalize_command_fingerprint,
    process_tree_identity_digest,
    validate_bootstrap_tree,
    verify_controller_acknowledgement,
)


AUTHORITY_VERSION = "charlie_provider_activation_authority_v1"
ACTIVATION_VERSION = "charlie_provider_activation_v1"
TASK_NAME = "CHARLIE CORE Runner Watchdog"
MODE = "observe_only"
PROTECTED_ANCESTRY = {
    "codex.exe", "codex.cmd", "powershell.exe", "pwsh.exe", "cmd.exe",
    "windowsterminal.exe", "conhost.exe",
}
PROVIDER_PARENTS = {"svchost.exe", "taskeng.exe", "taskhostw.exe"}


class ActivationError(RuntimeError):
    def __init__(self, status, **evidence):
        super().__init__(status)
        self.status = status
        self.evidence = evidence


def plan_activation(*, authority_path, authority_sha256, state_root,
                    runtime_root, execution_root, task_reader=read_watchdog_task,
                    git_runner=subprocess.run, now=None):
    state_root = Path(state_root).resolve()
    runtime_root = Path(runtime_root).resolve()
    execution_root = Path(execution_root).resolve()
    _validate_roots(state_root, runtime_root, execution_root)
    if (state_root / "activation.lock").exists():
        raise ActivationError("activation_lane_already_owned")
    if (state_root / "release-staging.lock").exists():
        raise ActivationError("release_lane_active")
    authority_path = Path(authority_path).resolve()
    if _sha256(authority_path) != str(authority_sha256 or "").lower():
        raise ActivationError("activation_authority_digest_mismatch")
    authority = _read_json(authority_path, "activation_authority_invalid")
    key_path = state_root / "activation-authority.key"
    key = _read_key(key_path)
    _validate_authority(authority, key, now=now)
    runtime = _worktree(runtime_root, git_runner)
    execution = _worktree(execution_root, git_runner)
    manifest_path = state_root / "runtime-manifest.json"
    receipt_path = Path(str(authority.get("receipt_path") or "")).resolve()
    stop_path = state_root / "supervisor.stop"
    manifest_sha = _sha256(manifest_path)
    stop_sha = _sha256(stop_path)
    receipt_sha = _sha256(receipt_path)
    task = task_reader()
    task_sha = _task_action_sha256(task)
    expected = {
        "runtime_revision": runtime["head"],
        "execution_revision": execution["head"],
        "manifest_sha256": manifest_sha,
        "receipt_sha256": receipt_sha,
        "stop_marker_sha256": stop_sha,
        "task_action_sha256": task_sha,
        "execution_mode": MODE,
    }
    mismatch = next((name for name, value in expected.items()
                     if str(authority.get(name) or "") != str(value)), "")
    if mismatch:
        raise ActivationError(f"activation_{mismatch}_mismatch")
    manifest = _read_json(manifest_path, "runtime_manifest_invalid")
    revision = authority["runtime_revision"]
    if manifest.get("promoted_commit") != revision:
        raise ActivationError("activation_manifest_revision_mismatch")
    if manifest.get("validation_receipt_sha256") != receipt_sha:
        raise ActivationError("activation_manifest_receipt_mismatch")
    _validate_exact_task(task, runtime_root)
    if runtime["head"] != execution["head"]:
        raise ActivationError("activation_staged_revisions_disagree")
    plan = {
        "version": ACTIVATION_VERSION,
        "status": "activation_plan_ready",
        "activation_id": authority["activation_id"],
        "authority_path": str(authority_path),
        "authority_sha256": authority_sha256,
        "authority": authority,
        "state_root": str(state_root),
        "runtime_root": str(runtime_root),
        "execution_root": str(execution_root),
        "key_sha256": _sha256(key_path),
        "runtime": runtime,
        "execution": execution,
        "task_ownership": task,
        "manifest_bytes_b64": base64.b64encode(manifest_path.read_bytes()).decode("ascii"),
        **expected,
        "zero_effect": True,
    }
    plan["plan_sha256"] = _payload_sha256(plan)
    return plan


def prepare_activation(plan, *, task_controller, task_reader=read_watchdog_task,
                       git_runner=subprocess.run, now=None):
    _validate_plan(plan, now=now)
    if (Path(plan["state_root"]) / "activation.lock").exists():
        raise ActivationError("activation_lane_already_owned")
    _validate_pre_mutation(plan, task_reader=task_reader, git_runner=git_runner)
    state_root = Path(plan["state_root"])
    lane_path = state_root / "activation.lock"
    lane = {
        "version": ACTIVATION_VERSION, "activation_id": plan["activation_id"],
        "status": "activation_lane_acquired", "acquired_at": _now(now),
    }
    descriptor = _exclusive_json(lane_path, lane)
    os.close(descriptor)
    ledger = state_root / "activation-ledger"
    activation_id = plan["activation_id"]
    rollback_path = ledger / f"{activation_id}-rollback.json"
    packet_path = state_root / "activation-packet.json"
    stop_path = state_root / "supervisor.stop"
    archive_path = state_root / f"supervisor.stop.activation-{activation_id}"
    for historical in (rollback_path, packet_path, archive_path,
                       state_root / f"activation-consumed-{activation_id}.json"):
        if historical.exists():
            lane_path.replace(ledger / f"{activation_id}-replay-refused-lane.json")
            raise ActivationError("activation_identity_already_used", path=str(historical))
    rollback = {
        "version": ACTIVATION_VERSION, "activation_id": activation_id,
        "status": "activation_rollback_recorded", "recorded_at": _now(now),
        "stop_marker_bytes_b64": base64.b64encode(stop_path.read_bytes()).decode("ascii"),
        "stop_marker_sha256": plan["stop_marker_sha256"],
        "task_action_sha256": plan["task_action_sha256"],
        "task_prior_state": "Disabled", "authority_sha256": plan["authority_sha256"],
    }
    rollback["rollback_hmac_sha256"] = _sign_record(rollback, _read_key(state_root / "activation-authority.key"), "rollback_hmac_sha256")
    packet = {
        "version": ACTIVATION_VERSION, "status": "provider_pending",
        "activation_id": activation_id, "authority": plan["authority"],
        "authority_path": plan["authority_path"],
        "authority_sha256": plan["authority_sha256"], "prepared_at": _now(now),
        "runtime_root": plan["runtime_root"], "execution_root": plan["execution_root"],
        "task_ownership": plan["task_ownership"],
    }
    packet["packet_hmac_sha256"] = _sign_packet(packet, _read_key(state_root / "activation-authority.key"))
    try:
        if (state_root / "release-staging.lock").exists():
            raise ActivationError("release_lane_active")
        _atomic_json(rollback_path, rollback)
        _atomic_json(packet_path, packet)
        if _sha256(stop_path) != plan["stop_marker_sha256"]:
            raise ActivationError("governed_stop_changed_before_archive")
        stop_path.replace(archive_path)
        if hasattr(task_controller, "bind_exact"):
            task_controller.bind_exact(plan["task_ownership"])
        task_controller.enable_and_trigger_exact(plan["task_action_sha256"])
    except Exception:
        if rollback_path.exists():
            _recover_prepare_failure(state_root, plan, task_controller, archive_path, stop_path)
        elif lane_path.exists():
            lane_path.replace(ledger / f"{activation_id}-prepare-write-failed-lane.json")
        raise
    return {
        "success": True, "status": "provider_activation_requested",
        "activation_id": activation_id, "lane_path": str(lane_path),
        "rollback_path": str(rollback_path), "packet_path": str(packet_path),
        "terminal_spawned_core": False,
    }


def consume_provider_activation(*, state_root, starter, task_reader=read_watchdog_task,
                                provider_inspector=None, git_runner=subprocess.run,
                                task_controller=None, now=None):
    state_root = Path(state_root).resolve()
    packet_path = state_root / "activation-packet.json"
    packet = _read_json(packet_path, "activation_packet_invalid")
    _validate_packet(packet, state_root, task_reader, git_runner=git_runner, now=now)
    provider = verify_provider_origin(
        provider_inspector or inspect_current_provider_chain,
        expected_task=packet["task_ownership"],
    )
    if not provider.get("authorized"):
        raise ActivationError(provider.get("reason") or "provider_origin_invalid")
    consumed_path = state_root / f"activation-consumed-{packet['activation_id']}.json"
    descriptor = _exclusive_json(consumed_path, {
        "version": ACTIVATION_VERSION, "activation_id": packet["activation_id"],
        "provider_pid": provider["pid"], "provider_parent_pid": provider["parent_pid"],
        "consumed_at": _now(now),
    })
    os.close(descriptor)
    previous = os.environ.get("CHARLIE_ACTIVATION_ID")
    os.environ["CHARLIE_ACTIVATION_ID"] = packet["activation_id"]
    try:
        result, status_code = starter(execution_mode=MODE)
    except Exception as exc:
        if task_controller is not None:
            recover_activation(state_root=state_root, task_controller=task_controller,
                               activation_id=packet["activation_id"])
        raise ActivationError("provider_start_failed", error_type=exc.__class__.__name__) from exc
    finally:
        if previous is None:
            os.environ.pop("CHARLIE_ACTIVATION_ID", None)
        else:
            os.environ["CHARLIE_ACTIVATION_ID"] = previous
    status = "provider_started_observe_only" if status_code < 300 else "provider_start_failed"
    updated = {**packet, "status": status, "provider": provider,
               "start_result": result, "provider_started_at": _now(now)}
    updated["packet_hmac_sha256"] = _sign_packet(updated, _read_key(state_root / "activation-authority.key"))
    _atomic_json(packet_path, updated)
    if status_code >= 300:
        if task_controller is not None:
            recover_activation(state_root=state_root, task_controller=task_controller,
                               activation_id=packet["activation_id"])
        raise ActivationError("provider_start_failed", start_result=result)
    return {"success": True, "status": status, "activation_id": packet["activation_id"],
            "terminal_spawned_core": False, "provider": provider, "start_result": result}


def verify_or_recover_activation(*, state_root, verification_reader, task_controller,
                                 task_reader=read_watchdog_task,
                                 git_runner=subprocess.run, now=None):
    state_root = Path(state_root).resolve()
    packet = _read_json(state_root / "activation-packet.json", "activation_packet_invalid")
    try:
        _validate_packet(packet, state_root, task_reader, git_runner=git_runner,
                         now=now, allow_consumed=True, allow_expired=True)
        if _parse_time(packet["authority"].get("expires_at")) <= (now or datetime.now(timezone.utc)):
            raise ActivationError("activation_authority_expired")
        evidence = verification_reader(packet)
    except Exception as exc:
        recover_activation(state_root=state_root, task_controller=task_controller,
                           activation_id=str(packet.get("activation_id") or ""))
        raise ActivationError("activation_verification_failed",
                              evidence_status=getattr(exc, "status", exc.__class__.__name__)) from exc
    required = (
        "loaded_revision_exact", "execution_mode_observe_only",
        "signed_supervisor_tree", "signed_runner_tree", "heartbeat_fresh",
        "activation_id_exact", "unrelated_processes_absent",
    )
    if all(evidence.get(item) is True for item in required):
        lane = state_root / "activation.lock"
        archive = state_root / "activation-ledger" / f"{packet['activation_id']}-lane.json"
        lane.replace(archive)
        _atomic_json(state_root / "activation-ledger" / f"{packet['activation_id']}-verified.json", evidence)
        _archive_activation_artifacts(state_root, packet["activation_id"], "verified")
        return {"success": True, "status": "activation_verified", "evidence": evidence}
    recover_activation(state_root=state_root, task_controller=task_controller,
                       activation_id=packet["activation_id"])
    raise ActivationError("activation_verification_failed", evidence=evidence)


def read_activation_runtime_evidence(packet, *, state_root, now=None,
                                     live_validator=None):
    """Validate exact signed runtime evidence; never infer ownership by name."""
    state_root = Path(state_root)
    supervisor = _read_json(state_root / "supervisor.json", "supervisor_state_invalid")
    heartbeat = _read_json(state_root / "runner.json", "runner_heartbeat_invalid")
    authority = packet["authority"]
    activation_id = packet["activation_id"]
    final = supervisor.get("controller_final_acknowledgement")
    public_key = str(supervisor.get("controller_public_key") or "")
    unsigned = ({k: v for k, v in final.items() if k != "signature"}
                if isinstance(final, dict) else {})
    revision_exact = all(str(value or "") == authority["runtime_revision"] for value in (
        supervisor.get("intended_runtime_revision"),
        supervisor.get("intended_execution_revision"),
        (final or {}).get("revision") if isinstance(final, dict) else "",
        heartbeat.get("runner_source_commit"),
    ))
    activation_exact = all(str(value or "") == activation_id for value in (
        supervisor.get("activation_id"),
        (final or {}).get("activation_id") if isinstance(final, dict) else "",
        heartbeat.get("activation_id"),
    ))
    signature_valid = bool(
        unsigned and public_key
        and verify_controller_acknowledgement(unsigned, final.get("signature"), public_key)
    )
    supervisor_tree = supervisor.get("supervisor_tree_identity")
    runner_tree = supervisor.get("process_tree_identity")
    live_validator = live_validator or _bounded_validate_live_tree
    supervisor_live = live_validator(
        supervisor_tree,
        generation=str(supervisor.get("generation") or ""),
        revision=authority["runtime_revision"],
        startup_nonce=str(supervisor.get("startup_nonce") or ""),
        allowed_descendant_tree=runner_tree,
    )
    runner_live = live_validator(
        runner_tree,
        generation=str(supervisor.get("generation") or ""),
        revision=authority["execution_revision"],
        startup_nonce=str(supervisor.get("runner_startup_nonce") or ""),
    )
    tree_digests_exact = isinstance(final, dict) and all((
        str(final.get("supervisor_tree_digest") or "") == process_tree_identity_digest(supervisor_tree),
        str(final.get("runner_tree_digest") or "") == process_tree_identity_digest(runner_tree),
    ))
    try:
        heartbeat_at = _parse_time(heartbeat.get("last_seen"))
        heartbeat_fresh = 0 <= ((now or datetime.now(timezone.utc)) - heartbeat_at).total_seconds() <= 120
    except ActivationError:
        heartbeat_fresh = False
    unrelated_absent = bool(
        supervisor_live.get("authorized") and runner_live.get("authorized")
        and not any(
            Path(str(item.get("executable_path") or "")).name.casefold() in PROTECTED_ANCESTRY
            for item in [*(supervisor_tree or {}).get("members", []), *(runner_tree or {}).get("members", [])]
            if isinstance(item, dict)
        )
    )
    return {
        "loaded_revision_exact": revision_exact,
        "execution_mode_observe_only": all(str(value or "") == MODE for value in (
            supervisor.get("execution_mode"), (final or {}).get("execution_mode") if isinstance(final, dict) else "",
            heartbeat.get("execution_mode"),
        )),
        "signed_supervisor_tree": bool(signature_valid and tree_digests_exact and supervisor_live.get("authorized")),
        "signed_runner_tree": bool(signature_valid and tree_digests_exact and runner_live.get("authorized")),
        "heartbeat_fresh": heartbeat_fresh,
        "activation_id_exact": activation_exact,
        "unrelated_processes_absent": unrelated_absent,
        "supervisor_member_pids": supervisor_live.get("member_pids") or [],
        "runner_member_pids": runner_live.get("member_pids") or [],
    }


def _bounded_validate_live_tree(tree, *, generation, revision, startup_nonce,
                                allowed_descendant_tree=None,
                                inspector=None):
    static = validate_bootstrap_tree(
        tree, generation=generation, revision=revision,
        startup_nonce=startup_nonce, require_interpreter=True,
    )
    if not static.get("authorized"):
        return static
    inspector = inspector or _inspect_exact_process
    members = tree.get("members") if isinstance(tree, dict) else []
    for record in members:
        current = inspector(int(record.get("pid") or -1))
        if not isinstance(current, dict) or not current.get("inspection_complete"):
            return {"authorized": False, "reason": "owned_pid_inspection_failed"}
        checks = (
            int(current.get("pid") or -1) == int(record.get("pid") or -2),
            int(current.get("parent_pid") or -1) == int(record.get("parent_pid") or -2),
            str(current.get("creation_time") or "") == str(record.get("creation_time") or ""),
            str(Path(str(current.get("executable_path") or "")).resolve()).casefold()
            == str(Path(str(record.get("executable_path") or "")).resolve()).casefold(),
            normalize_command_fingerprint(current.get("command_line"))
            == str(record.get("command_fingerprint") or ""),
        )
        if not all(checks):
            return {"authorized": False, "reason": "owned_pid_identity_changed"}
    return {"authorized": True, "reason": "exact_owned_members_live",
            "member_pids": sorted(int(item["pid"]) for item in members)}


def _inspect_exact_process(pid, runner=subprocess.run):
    script = (
        "$ErrorActionPreference='Stop';"
        f"$p=Get-CimInstance Win32_Process -Filter \"ProcessId={int(pid)}\";"
        "if($null-eq$p){exit 4};"
        "$p|Select-Object ProcessId,ParentProcessId,ExecutablePath,CreationDate,CommandLine|ConvertTo-Json -Compress"
    )
    completed = runner(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if completed.returncode:
        return {"inspection_complete": False}
    try:
        row = json.loads(completed.stdout)
        return {
            "inspection_complete": True, "pid": int(row["ProcessId"]),
            "parent_pid": int(row["ParentProcessId"]),
            "executable_path": str(row.get("ExecutablePath") or ""),
            "creation_time": str(row.get("CreationDate") or ""),
            "command_line": str(row.get("CommandLine") or ""),
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {"inspection_complete": False}


def recover_activation(*, state_root, task_controller, activation_id):
    state_root = Path(state_root).resolve()
    lane = _read_json(state_root / "activation.lock", "activation_lane_missing")
    if lane.get("activation_id") != activation_id:
        raise ActivationError("activation_lane_identity_mismatch")
    rollback = _read_json(
        state_root / "activation-ledger" / f"{activation_id}-rollback.json",
        "activation_rollback_missing",
    )
    packet = _read_json(state_root / "activation-packet.json", "activation_packet_invalid")
    key = _read_key(state_root / "activation-authority.key")
    if not hmac.compare_digest(
        str(rollback.get("rollback_hmac_sha256") or ""),
        _sign_record(rollback, key, "rollback_hmac_sha256"),
    ):
        raise ActivationError("activation_rollback_signature_invalid")
    authority = packet.get("authority") if isinstance(packet.get("authority"), dict) else {}
    if any((
        rollback.get("version") != ACTIVATION_VERSION,
        rollback.get("activation_id") != activation_id,
        rollback.get("authority_sha256") != packet.get("authority_sha256"),
        rollback.get("stop_marker_sha256") != authority.get("stop_marker_sha256"),
        rollback.get("task_action_sha256") != authority.get("task_action_sha256"),
    )):
        raise ActivationError("activation_rollback_binding_invalid")
    if hasattr(task_controller, "bind_exact"):
        task_controller.bind_exact(packet.get("task_ownership"))
    errors = []
    try:
        task_controller.disable_exact(rollback["task_action_sha256"])
    except Exception as exc:
        errors.append({"component": "scheduled_task", "status": getattr(exc, "status", exc.__class__.__name__)})
    stop_path = state_root / "supervisor.stop"
    archive = state_root / f"supervisor.stop.activation-{activation_id}"
    try:
        if stop_path.exists() and _sha256(stop_path) != rollback["stop_marker_sha256"]:
            raise ActivationError("governed_stop_conflict_during_recovery")
        if not stop_path.exists():
            expected = base64.b64decode(rollback["stop_marker_bytes_b64"], validate=True)
            if archive.exists() and hashlib.sha256(archive.read_bytes()).hexdigest() != rollback["stop_marker_sha256"]:
                raise ActivationError("archived_stop_identity_mismatch")
            _atomic_bytes(stop_path, expected)
        if _sha256(stop_path) != rollback["stop_marker_sha256"]:
            raise ActivationError("governed_stop_restore_failed")
    except Exception as exc:
        errors.append({"component": "governed_stop", "status": getattr(exc, "status", exc.__class__.__name__)})
    if errors:
        raise ActivationError("activation_recovery_incomplete", errors=errors)
    lane_path = state_root / "activation.lock"
    lane_path.replace(state_root / "activation-ledger" / f"{activation_id}-lane-recovered.json")
    _archive_activation_artifacts(state_root, activation_id, "recovered")
    return {"success": True, "status": "activation_recovered", "activation_id": activation_id}


def verify_provider_origin(inspector, *, expected_task):
    current = inspector(os.getpid())
    if not isinstance(current, dict) or not current.get("inspection_complete"):
        return {"authorized": False, "reason": "provider_identity_incomplete"}
    ancestry = current.get("ancestry")
    if not isinstance(ancestry, list) or not ancestry:
        return {"authorized": False, "reason": "provider_ancestry_incomplete"}
    names = [Path(str(item.get("executable_path") or "")).name.casefold() for item in ancestry]
    if any(name in PROTECTED_ANCESTRY for name in names):
        return {"authorized": False, "reason": "terminal_ancestry_rejected"}
    parent = ancestry[0]
    parent_name = Path(str(parent.get("executable_path") or "")).name.casefold()
    current_name = Path(str(current.get("executable_path") or "")).name.casefold()
    if current_name != "pythonw.exe" or parent_name not in PROVIDER_PARENTS:
        return {"authorized": False, "reason": "scheduled_provider_origin_required"}
    row = expected_task[0] if isinstance(expected_task, list) and len(expected_task) == 1 else {}
    current_executable = str(Path(str(current.get("executable_path") or "")).resolve()).casefold()
    expected_executable = str(Path(str(row.get("execute") or "")).resolve()).casefold()
    current_tokens = _command_tokens(current.get("command_line"))
    expected_tokens = _command_tokens(str(row.get("arguments") or ""))
    if (current_executable != expected_executable or not current_tokens
            or str(Path(current_tokens[0]).resolve()).casefold() != expected_executable
            or current_tokens[1:] != expected_tokens):
        return {"authorized": False, "reason": "provider_task_action_mismatch"}
    return {"authorized": True, "reason": "scheduled_provider_origin_verified",
            "pid": int(current["pid"]), "parent_pid": int(current["parent_pid"]),
            "parent_executable": parent_name}


def inspect_current_provider_chain(pid=None, runner=subprocess.run):
    """Inspect only this process and its exact parent chain, never a host snapshot."""
    current_pid = int(pid or os.getpid())
    chain = []
    current = {}
    for index in range(12):
        script = (
            "$ErrorActionPreference='Stop';"
            f"$p=Get-CimInstance Win32_Process -Filter \"ProcessId={current_pid}\";"
            "if($null-eq$p){exit 4};"
            "$p|Select-Object ProcessId,ParentProcessId,ExecutablePath,CreationDate,CommandLine|ConvertTo-Json -Compress"
        )
        completed = runner(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if completed.returncode:
            return {"inspection_complete": False, "reason": "provider_identity_unreadable"}
        try:
            row = json.loads(completed.stdout)
            item = {
                "pid": int(row["ProcessId"]),
                "parent_pid": int(row["ParentProcessId"]),
                "executable_path": str(row.get("ExecutablePath") or ""),
                "creation_time": str(row.get("CreationDate") or ""),
                "command_line": str(row.get("CommandLine") or ""),
            }
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return {"inspection_complete": False, "reason": "provider_identity_invalid"}
        if index == 0:
            current = item
        else:
            chain.append(item)
        current_pid = item["parent_pid"]
        if current_pid <= 0:
            break
    return {**current, "inspection_complete": bool(chain), "ancestry": chain}


class WindowsExactTaskController:
    def __init__(self, task_reader=read_watchdog_task, runner=subprocess.run):
        self.task_reader, self.runner = task_reader, runner
        self.expected_task = None

    def bind_exact(self, rows):
        if not isinstance(rows, list) or len(rows) != 1:
            raise ActivationError("scheduled_task_ownership_ambiguous")
        self.expected_task = rows

    def enable_and_trigger_exact(self, digest):
        self._mutate(digest, "Enable-ScheduledTask -InputObject $t|Out-Null")
        if _task_action_sha256(self.task_reader()) != digest:
            self._mutate(digest, "Disable-ScheduledTask -InputObject $t|Out-Null")
            raise ActivationError("scheduled_task_identity_changed_after_enable")
        self._mutate(digest, "Start-ScheduledTask -InputObject $t")

    def disable_exact(self, digest):
        self._mutate(digest, "Disable-ScheduledTask -InputObject $t|Out-Null")

    def _mutate(self, digest, action):
        if _task_action_sha256(self.task_reader()) != digest:
            raise ActivationError("scheduled_task_identity_changed")
        if not self.expected_task:
            raise ActivationError("scheduled_task_binding_missing")
        encoded = base64.b64encode(_canonical(self.expected_task[0])).decode("ascii")
        script = (
            "$ErrorActionPreference='Stop';"
            f"$e=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}'))|ConvertFrom-Json;"
            "$ts=@(Get-ScheduledTask -TaskName $e.task_name -TaskPath $e.task_path);"
            "if($ts.Count-ne 1){throw 'task identity ambiguous'};$t=$ts[0];$a=@($t.Actions);"
            "if($a.Count-ne 1-or[string]$a[0].Execute-ne[string]$e.execute-or"
            "[string]$a[0].Arguments-ne[string]$e.arguments-or"
            "[string]$a[0].WorkingDirectory-ne[string]$e.working_directory){throw 'task action changed'};"
            + action
        )
        completed = self.runner(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                capture_output=True, text=True, timeout=30, check=False)
        if completed.returncode != 0:
            raise ActivationError("scheduled_task_provider_mutation_failed")


def _validate_authority(authority, key, now=None, allow_expired=False):
    signature = str(authority.get("signature_hmac_sha256") or "")
    unsigned = {k: v for k, v in authority.items() if k != "signature_hmac_sha256"}
    expected = hmac.new(key, _canonical(unsigned), hashlib.sha256).hexdigest()
    expiry = _parse_time(authority.get("expires_at"))
    current = now or datetime.now(timezone.utc)
    if (authority.get("version") != AUTHORITY_VERSION
            or authority.get("issuer") != "control_tower_activation_authority_v1"
            or not re.fullmatch(r"[0-9a-f]{32}", str(authority.get("activation_id") or ""))
            or not hmac.compare_digest(signature, expected)
            or (not allow_expired and expiry <= current.astimezone(timezone.utc))
            or authority.get("execution_mode") != MODE):
        raise ActivationError("activation_authority_not_valid")


def _validate_plan(plan, now=None):
    if not isinstance(plan, dict) or plan.get("status") != "activation_plan_ready":
        raise ActivationError("activation_plan_required")
    unsigned = {k: v for k, v in plan.items() if k != "plan_sha256"}
    if plan.get("plan_sha256") != _payload_sha256(unsigned):
        raise ActivationError("activation_plan_digest_mismatch")
    _validate_authority(plan["authority"], _read_key(Path(plan["state_root"]) / "activation-authority.key"), now=now)


def _validate_pre_mutation(plan, *, task_reader, git_runner):
    state_root = Path(plan["state_root"])
    if _sha256(state_root / "activation-authority.key") != plan["key_sha256"]:
        raise ActivationError("activation_authority_key_changed")
    for path, expected, status in (
        (state_root / "runtime-manifest.json", plan["manifest_sha256"], "activation_manifest_changed"),
        (plan["authority"]["receipt_path"], plan["receipt_sha256"], "activation_receipt_changed"),
        (state_root / "supervisor.stop", plan["stop_marker_sha256"], "governed_stop_changed"),
    ):
        if _sha256(path) != expected:
            raise ActivationError(status)
    if _task_action_sha256(task_reader()) != plan["task_action_sha256"]:
        raise ActivationError("scheduled_task_identity_changed")
    runtime = _worktree(Path(plan["runtime_root"]), git_runner)
    execution = _worktree(Path(plan["execution_root"]), git_runner)
    if runtime != plan["runtime"] or execution != plan["execution"]:
        raise ActivationError("activation_worktree_identity_changed")


def _validate_packet(packet, state_root, task_reader, git_runner=subprocess.run,
                     now=None, allow_consumed=False, allow_expired=False):
    key = _read_key(state_root / "activation-authority.key")
    signature = packet.get("packet_hmac_sha256")
    if not hmac.compare_digest(str(signature or ""), _sign_packet(packet, key)):
        raise ActivationError("activation_packet_signature_invalid")
    authority = packet.get("authority") if isinstance(packet.get("authority"), dict) else {}
    if (packet.get("version") != ACTIVATION_VERSION
            or packet.get("activation_id") != authority.get("activation_id")):
        raise ActivationError("activation_packet_binding_invalid")
    if packet.get("status") not in ({"provider_pending", "provider_started_observe_only"} if allow_consumed else {"provider_pending"}):
        raise ActivationError("activation_packet_replayed")
    _validate_authority(authority, key, now=now, allow_expired=allow_expired)
    if (_sha256(packet.get("authority_path")) != packet.get("authority_sha256")
            or Path(packet.get("runtime_root", "")).resolve() != state_root / "core-runtime-current"
            or Path(packet.get("execution_root", "")).resolve() != state_root / "core-execution-current"):
        raise ActivationError("activation_packet_authority_or_roots_invalid")
    lane = _read_json(state_root / "activation.lock", "activation_lane_missing")
    rollback = _read_json(
        state_root / "activation-ledger" / f"{packet['activation_id']}-rollback.json",
        "activation_rollback_missing",
    )
    if lane.get("activation_id") != packet["activation_id"]:
        raise ActivationError("activation_lane_identity_mismatch")
    if (not hmac.compare_digest(
            str(rollback.get("rollback_hmac_sha256") or ""),
            _sign_record(rollback, key, "rollback_hmac_sha256"))
            or rollback.get("activation_id") != packet["activation_id"]
            or rollback.get("authority_sha256") != packet.get("authority_sha256")
            or rollback.get("stop_marker_sha256") != authority.get("stop_marker_sha256")
            or rollback.get("task_action_sha256") != authority.get("task_action_sha256")):
        raise ActivationError("activation_rollback_binding_invalid")
    manifest_path = state_root / "runtime-manifest.json"
    if _sha256(manifest_path) != authority["manifest_sha256"]:
        raise ActivationError("activation_manifest_sha256_mismatch")
    if _sha256(authority["receipt_path"]) != authority["receipt_sha256"]:
        raise ActivationError("activation_receipt_sha256_mismatch")
    if _task_action_sha256(task_reader()) != authority["task_action_sha256"]:
        raise ActivationError("activation_task_action_sha256_mismatch")
    if _sha256(state_root / f"supervisor.stop.activation-{packet['activation_id']}") != authority["stop_marker_sha256"]:
        raise ActivationError("activation_archived_stop_sha256_mismatch")
    runtime = _worktree(Path(packet["runtime_root"]), git_runner)
    execution = _worktree(Path(packet["execution_root"]), git_runner)
    if runtime["head"] != authority["runtime_revision"] or execution["head"] != authority["execution_revision"]:
        raise ActivationError("activation_worktree_revision_mismatch")


def _validate_exact_task(rows, runtime_root):
    if (not isinstance(rows, list) or len(rows) != 1
            or rows[0].get("task_name") != TASK_NAME
            or str(rows[0].get("task_path") or "") != "\\"):
        raise ActivationError("scheduled_task_ownership_ambiguous")
    if int(rows[0].get("action_count") or 0) != 1 or str(rows[0].get("state")) != "Disabled":
        raise ActivationError("scheduled_task_not_exact_disabled")
    expected = runtime_root.parent.parent / "venv" / "Scripts" / "pythonw.exe"
    if str(Path(str(rows[0].get("execute") or "")).resolve()).casefold() != str(expected.resolve()).casefold():
        raise ActivationError("scheduled_task_executable_mismatch")
    if str(Path(str(rows[0].get("working_directory") or "")).resolve()).casefold() != str(runtime_root).casefold():
        raise ActivationError("scheduled_task_working_directory_mismatch")
    canonical_root = runtime_root.parent.parent
    expected_watchdog = runtime_root / "scripts" / "charlie_runner_watchdog.py"
    expected_arguments = (
        '-c "from dotenv import load_dotenv; load_dotenv(r\'{0}\', override=True); '
        "import runpy,sys; sys.argv=[r'{1}','--json']; "
        "runpy.run_path(r'{1}', run_name='__main__')\""
    ).format(canonical_root / ".env", expected_watchdog)
    if str(rows[0].get("arguments") or "").casefold() != expected_arguments.casefold():
        raise ActivationError("scheduled_task_arguments_mismatch")


def _recover_prepare_failure(state_root, plan, controller, archive, stop):
    try:
        controller.disable_exact(plan["task_action_sha256"])
    finally:
        if archive.exists() and not stop.exists():
            archive.replace(stop)


def _validate_roots(state, runtime, execution):
    if runtime != state / "core-runtime-current" or execution != state / "core-execution-current" or runtime == execution:
        raise ActivationError("activation_roots_invalid")


def _worktree(root, runner):
    if _git(root, ["status", "--porcelain"], runner):
        raise ActivationError("activation_worktree_dirty", root=str(root))
    return {"root": str(root), "head": _git(root, ["rev-parse", "HEAD"], runner),
            "branch": _git(root, ["branch", "--show-current"], runner)}


def _git(root, args, runner):
    result = runner(["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=NUL", *args], cwd=str(root), capture_output=True, text=True, timeout=30, check=False)
    if result.returncode:
        raise ActivationError("activation_git_read_failed")
    return str(result.stdout or "").strip()


def _sign_packet(packet, key):
    unsigned = {k: v for k, v in packet.items() if k != "packet_hmac_sha256"}
    return hmac.new(key, _canonical(unsigned), hashlib.sha256).hexdigest()


def _read_key(path):
    try:
        value = Path(path).read_bytes()
    except OSError as exc:
        raise ActivationError("activation_authority_key_unavailable") from exc
    if len(value) < 32:
        raise ActivationError("activation_authority_key_invalid")
    return value


def _read_json(path, status):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise ActivationError(status) from exc
    if not isinstance(value, dict):
        raise ActivationError(status)
    return value


def _sha256(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError as exc:
        raise ActivationError("activation_evidence_unreadable", path=str(path)) from exc


def _payload_sha256(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _task_action_sha256(rows):
    normalized = []
    for row in rows if isinstance(rows, list) else []:
        item = dict(row) if isinstance(row, dict) else {}
        item["state"] = "Disabled"
        normalized.append(item)
    return _payload_sha256(normalized)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _command_tokens(value):
    try:
        return [token.strip('"') for token in shlex.split(str(value or ""), posix=False)]
    except ValueError:
        return []


def _sign_record(record, key, signature_field):
    unsigned = {k: v for k, v in record.items() if k != signature_field}
    return hmac.new(key, _canonical(unsigned), hashlib.sha256).hexdigest()


def _archive_activation_artifacts(state_root, activation_id, suffix):
    ledger = Path(state_root) / "activation-ledger"
    ledger.mkdir(parents=True, exist_ok=True)
    for path in (
        Path(state_root) / "activation-packet.json",
        Path(state_root) / f"activation-consumed-{activation_id}.json",
        Path(state_root) / f"supervisor.stop.activation-{activation_id}",
    ):
        if path.exists():
            path.replace(ledger / f"{activation_id}-{suffix}-{path.name}")


def _parse_time(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        raise ActivationError("activation_expiry_invalid") from exc


def _exclusive_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ActivationError("activation_lane_already_owned") from exc
    with os.fdopen(os.dup(descriptor), "wb") as stream:
        stream.write(json.dumps(value, indent=2).encode())
        stream.flush(); os.fsync(stream.fileno())
    return descriptor


def _atomic_json(path, value):
    _atomic_bytes(path, json.dumps(value, indent=2).encode())


def _atomic_bytes(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("wb") as stream:
        stream.write(value); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


def _now(value=None):
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
