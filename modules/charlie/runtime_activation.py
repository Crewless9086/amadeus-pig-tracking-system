"""Serialized, provider-origin-only observe-only CORE activation."""

from __future__ import annotations

import base64
import csv
import ctypes
import hashlib
import hmac
import json
import os
import re
import shlex
import subprocess
import sys
import time
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
ACTIVATION_VERSION = "charlie_provider_activation_v2"
RECOVERY_PROJECTION_VERSION = "charlie_activation_recovery_projection_v1"
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
    if (state_root / "activation-reconciliation.lock").exists():
        raise ActivationError("activation_reconciliation_lane_active")
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
    if (Path(plan["state_root"]) / "activation-reconciliation.lock").exists():
        raise ActivationError("activation_reconciliation_lane_active")
    if (Path(plan["state_root"]) / "activation-verification.lock").exists():
        raise ActivationError("activation_verification_lane_active")
    _validate_pre_mutation(plan, task_reader=task_reader, git_runner=git_runner)
    state_root = Path(plan["state_root"])
    if not hasattr(task_controller, "read_audit_channel_state"):
        raise ActivationError("task_scheduler_audit_controller_required")
    audit_prior = task_controller.read_audit_channel_state()
    if (not isinstance(audit_prior, dict)
            or audit_prior.get("log_name") != TASK_SCHEDULER_OPERATIONAL_LOG
            or not isinstance(audit_prior.get("enabled"), bool)):
        raise ActivationError("task_scheduler_audit_state_invalid")
    if not hasattr(task_controller, "read_audit_event_record_id"):
        raise ActivationError("task_scheduler_audit_controller_required")
    if not hasattr(task_controller, "assert_no_running_instances"):
        raise ActivationError("task_scheduler_instance_controller_required")
    task_controller.assert_no_running_instances()
    event_record_id_lower_bound = task_controller.read_audit_event_record_id()
    if not isinstance(event_record_id_lower_bound, int) or event_record_id_lower_bound < 0:
        raise ActivationError("task_scheduler_audit_record_id_invalid")
    lane_path = state_root / "activation.lock"
    ledger = state_root / "activation-ledger"
    activation_id = plan["activation_id"]
    rollback_path = ledger / f"{activation_id}-rollback.json"
    packet_path = state_root / "activation-packet.json"
    stop_path = state_root / "supervisor.stop"
    archive_path = state_root / f"supervisor.stop.activation-{activation_id}"
    audit_intent_path = state_root / f"activation-audit-intent-{activation_id}.json"
    audit_receipt_path = state_root / f"activation-audit-receipt-{activation_id}.json"
    historical_candidates = [
        rollback_path, packet_path, archive_path,
        state_root / f"activation-consumed-{activation_id}.json",
        audit_intent_path, audit_receipt_path,
        *ledger.glob(f"{activation_id}-*"),
    ]
    for historical in historical_candidates:
        if historical.exists():
            raise ActivationError("activation_identity_already_used", path=str(historical))
    rollback = {
        "version": ACTIVATION_VERSION, "activation_id": activation_id,
        "status": "activation_rollback_recorded", "recorded_at": _now(now),
        "stop_marker_bytes_b64": base64.b64encode(stop_path.read_bytes()).decode("ascii"),
        "stop_marker_sha256": plan["stop_marker_sha256"],
        "task_action_sha256": plan["task_action_sha256"],
        "task_ownership": plan["task_ownership"],
        "task_prior_state": "Disabled", "authority_sha256": plan["authority_sha256"],
        "task_scheduler_audit_prior": audit_prior,
        "task_scheduler_event_record_id_lower_bound": event_record_id_lower_bound,
        "task_scheduler_audit_mutation_required": not audit_prior["enabled"],
        "task_scheduler_audit_rollback_command": (
            f"wevtutil sl {TASK_SCHEDULER_OPERATIONAL_LOG} "
            f"/e:{str(audit_prior['enabled']).lower()}"
        ),
    }
    rollback["rollback_hmac_sha256"] = _sign_record(rollback, _read_key(state_root / "activation-authority.key"), "rollback_hmac_sha256")
    packet = {
        "version": ACTIVATION_VERSION, "status": "provider_pending",
        "activation_id": activation_id, "authority": plan["authority"],
        "authority_path": plan["authority_path"],
        "authority_sha256": plan["authority_sha256"], "prepared_at": _now(now),
        "runtime_root": plan["runtime_root"], "execution_root": plan["execution_root"],
        "task_ownership": plan["task_ownership"],
        "task_scheduler_event_record_id_lower_bound": event_record_id_lower_bound,
    }
    packet["packet_hmac_sha256"] = _sign_packet(packet, _read_key(state_root / "activation-authority.key"))
    lane = {
        "version": ACTIVATION_VERSION, "activation_id": activation_id,
        "status": "activation_lane_acquired", "acquired_at": _now(now),
        "rollback": rollback, "packet": packet,
    }
    lane["lane_hmac_sha256"] = _sign_record(
        lane, _read_key(state_root / "activation-authority.key"), "lane_hmac_sha256"
    )
    _exclusive_json(lane_path, lane)
    try:
        if (state_root / "activation-reconciliation.lock").exists():
            raise ActivationError("activation_reconciliation_lane_active")
        if (state_root / "release-staging.lock").exists():
            raise ActivationError("release_lane_active")
        _atomic_json(rollback_path, rollback)
        _atomic_json(packet_path, packet)
        if _sha256(stop_path) != plan["stop_marker_sha256"]:
            raise ActivationError("governed_stop_changed_before_archive")
        _durable_replace(stop_path, archive_path)
        if hasattr(task_controller, "bind_exact"):
            task_controller.bind_exact(plan["task_ownership"])
        task_controller.bind_audit_channel_state(audit_prior)
        audit_intent = {
            "version": ACTIVATION_VERSION,
            "activation_id": activation_id,
            "status": "task_scheduler_audit_enable_intended",
            "log_name": TASK_SCHEDULER_OPERATIONAL_LOG,
            "prior_enabled": audit_prior["enabled"],
            "intended_enabled": True,
            "recorded_at": _now(now),
        }
        audit_intent["audit_intent_hmac_sha256"] = _sign_record(
            audit_intent, _read_key(state_root / "activation-authority.key"),
            "audit_intent_hmac_sha256",
        )
        _exclusive_json(audit_intent_path, audit_intent)
        audit_changed = task_controller.ensure_audit_channel_enabled()
        if audit_changed is not (not audit_prior["enabled"]):
            raise ActivationError("task_scheduler_audit_mutation_result_invalid")
        audit_receipt = {
            "version": ACTIVATION_VERSION,
            "activation_id": activation_id,
            "status": "task_scheduler_audit_enable_readback_complete",
            "log_name": TASK_SCHEDULER_OPERATIONAL_LOG,
            "prior_enabled": audit_prior["enabled"],
            "current_enabled": True,
            "changed": audit_changed,
            "event_record_id_lower_bound": event_record_id_lower_bound,
            "recorded_at": _now(now),
        }
        audit_receipt["audit_receipt_hmac_sha256"] = _sign_record(
            audit_receipt, _read_key(state_root / "activation-authority.key"),
            "audit_receipt_hmac_sha256",
        )
        _exclusive_json(audit_receipt_path, audit_receipt)
        expected_instance_guid = task_controller.enable_and_trigger_exact(
            plan["task_action_sha256"]
        )
        if not str(expected_instance_guid or "").strip("{}"):
            raise ActivationError("task_scheduler_instance_guid_missing")
        packet["expected_instance_guid"] = str(expected_instance_guid)
        packet["packet_hmac_sha256"] = _sign_packet(
            packet, _read_key(state_root / "activation-authority.key")
        )
        _atomic_json(packet_path, packet)
    except Exception:
        if lane_path.exists() and not rollback_path.exists():
            try:
                _atomic_json(rollback_path, rollback)
            except Exception:
                pass
        if rollback_path.exists():
            _close_prepare_failure(
                state_root, plan, task_controller, archive_path, stop_path,
                lane_path, rollback_path, packet_path,
            )
        raise
    return {
        "success": True, "status": "provider_activation_requested",
        "activation_id": activation_id, "lane_path": str(lane_path),
        "rollback_path": str(rollback_path), "packet_path": str(packet_path),
        "terminal_spawned_core": False,
    }


def consume_provider_activation(*, state_root, starter, task_controller,
                                task_reader=read_watchdog_task,
                                provider_inspector=None, git_runner=subprocess.run,
                                now=None):
    state_root = Path(state_root).resolve()
    packet_path = state_root / "activation-packet.json"
    deadline = time.monotonic() + 35
    while True:
        packet = _read_json(packet_path, "activation_packet_invalid")
        if str(packet.get("expected_instance_guid") or "").strip("{}"):
            break
        if time.monotonic() >= deadline:
            raise ActivationError("task_scheduler_instance_guid_timeout")
        time.sleep(0.05)
    _validate_packet(packet, state_root, task_reader, git_runner=git_runner, now=now)
    inspector = provider_inspector or (lambda pid: inspect_current_provider_chain(
        pid, activation_id=packet["activation_id"],
        activation_prepared_at=packet["prepared_at"],
        activation_event_record_id_lower_bound=packet["task_scheduler_event_record_id_lower_bound"],
    ))
    provider = verify_provider_origin(
        inspector,
        expected_task=packet["task_ownership"],
    )
    if not provider.get("authorized"):
        raise ActivationError(provider.get("reason") or "provider_origin_invalid")
    if (str(provider.get("provider_instance_guid") or "").strip("{}").casefold()
            != str(packet["expected_instance_guid"]).strip("{}").casefold()):
        raise ActivationError("task_scheduler_instance_guid_mismatch")
    consumed_path = state_root / f"activation-consumed-{packet['activation_id']}.json"
    consumed = {
        "version": ACTIVATION_VERSION, "activation_id": packet["activation_id"],
        "provider_pid": provider["pid"], "provider_parent_pid": provider["parent_pid"],
        "provider_instance_guid": provider["provider_instance_guid"],
        "expected_instance_guid": packet["expected_instance_guid"],
        "packet_hmac_sha256": packet["packet_hmac_sha256"],
        "consumed_at": _now(now),
    }
    consumed["consumed_hmac_sha256"] = _sign_record(
        consumed, _read_key(state_root / "activation-authority.key"),
        "consumed_hmac_sha256",
    )
    _exclusive_json(consumed_path, consumed)
    previous = os.environ.get("CHARLIE_ACTIVATION_ID")
    os.environ["CHARLIE_ACTIVATION_ID"] = packet["activation_id"]
    try:
        result, status_code = starter(execution_mode=MODE)
    except Exception as exc:
        recover_activation(state_root=state_root, task_controller=task_controller,
                           activation_id=packet["activation_id"], failure_evidence={
                               "status": "provider_start_failed",
                               "error_type": exc.__class__.__name__,
                           })
        raise ActivationError("provider_start_failed", error_type=exc.__class__.__name__) from exc
    finally:
        if previous is None:
            os.environ.pop("CHARLIE_ACTIVATION_ID", None)
        else:
            os.environ["CHARLIE_ACTIVATION_ID"] = previous
    status = "provider_started_observe_only" if status_code < 300 else "provider_start_failed"
    updated = {**packet, "status": status, "provider": provider,
               "start_result": result, "provider_started_at": _now(now),
               "consumed_packet_hmac_sha256": packet["packet_hmac_sha256"]}
    updated["packet_hmac_sha256"] = _sign_packet(updated, _read_key(state_root / "activation-authority.key"))
    _atomic_json(packet_path, updated)
    if status_code >= 300:
        recover_activation(state_root=state_root, task_controller=task_controller,
                           activation_id=packet["activation_id"], failure_evidence={
                               "status": "provider_start_failed", "start_result": result,
                           })
        raise ActivationError("provider_start_failed", start_result=result)
    return {"success": True, "status": status, "activation_id": packet["activation_id"],
            "terminal_spawned_core": False, "provider": provider, "start_result": result}


def verify_or_recover_activation(*, state_root, verification_reader, task_controller,
                                 task_reader=read_watchdog_task,
                                 git_runner=subprocess.run, now=None,
                                 activation_id=None):
    state_root = Path(state_root).resolve()
    live_packet = state_root / "activation-packet.json"
    if live_packet.exists():
        packet_path = live_packet
    elif (state_root / "activation-verification.lock").exists():
        marker = _read_json(state_root / "activation-verification.lock",
                            "activation_verification_marker_missing")
        marker_key = _read_key(state_root / "activation-authority.key")
        if (marker.get("version") != ACTIVATION_VERSION
                or marker.get("status") != "activation_verification_archival_pending"
                or not hmac.compare_digest(
                    str(marker.get("marker_hmac_sha256") or ""),
                    _sign_record(marker, marker_key, "marker_hmac_sha256"))):
            raise ActivationError("activation_verification_marker_invalid")
        packet_path = (state_root / "activation-ledger"
                       / f"{marker.get('activation_id')}-verified-activation-packet.json")
    else:
        if (state_root / "activation.lock").exists():
            raise ActivationError("activation_packet_missing_for_active_lane")
        completion = _read_json(
            state_root / "activation-verification-complete.json",
            "activation_verification_marker_missing",
        )
        completion_key = _read_key(state_root / "activation-authority.key")
        if (completion.get("version") != ACTIVATION_VERSION
                or completion.get("status") != "activation_verified"
                or not hmac.compare_digest(
                    str(completion.get("completion_hmac_sha256") or ""),
                    _sign_record(completion, completion_key,
                                 "completion_hmac_sha256"))):
            raise ActivationError("activation_verification_completion_invalid")
        if not activation_id or completion.get("activation_id") != activation_id:
            raise ActivationError("activation_verification_completion_identity_required")
        archive_hashes = completion.get("archive_hashes")
        if not isinstance(archive_hashes, dict) or not archive_hashes:
            raise ActivationError("activation_verification_completion_archives_invalid")
        ledger = state_root / "activation-ledger"
        for name, expected_hash in archive_hashes.items():
            if (Path(name).name != name
                    or not re.fullmatch(r"[0-9a-f]{64}", str(expected_hash or ""))
                    or _sha256(ledger / name) != expected_hash):
                raise ActivationError("activation_verification_completion_archives_invalid")
        return {"success": True, "status": "activation_verified",
                "evidence": completion.get("evidence", {})}
    deadline = time.monotonic() + 5
    while True:
        packet = _read_json(packet_path, "activation_packet_invalid")
        if str(packet.get("expected_instance_guid") or "").strip("{}"):
            break
        if time.monotonic() >= deadline:
            raise ActivationError("task_scheduler_instance_guid_timeout")
        time.sleep(0.05)
    marker_path = state_root / "activation-verification.lock"
    if marker_path.exists():
        current_marker = _read_json(marker_path, "activation_verification_marker_invalid")
        if current_marker.get("activation_id") != packet.get("activation_id"):
            raise ActivationError("activation_verification_marker_identity_mismatch")
    try:
        _validate_packet(packet, state_root, task_reader, git_runner=git_runner,
                         now=now, allow_consumed=True, allow_expired=True)
        if _parse_time(packet["authority"].get("expires_at")) <= (now or datetime.now(timezone.utc)):
            raise ActivationError("activation_authority_expired")
        evidence = verification_reader(packet)
    except Exception as exc:
        recover_activation(state_root=state_root, task_controller=task_controller,
                           activation_id=str(packet.get("activation_id") or ""),
                           failure_evidence={
                               "status": "activation_verification_failed",
                               "evidence_status": getattr(exc, "status", exc.__class__.__name__),
                           })
        raise ActivationError("activation_verification_failed",
                              evidence_status=getattr(exc, "status", exc.__class__.__name__)) from exc
    required = (
        "loaded_revision_exact", "execution_mode_observe_only",
        "signed_supervisor_tree", "signed_runner_tree", "heartbeat_fresh",
        "activation_id_exact", "unrelated_processes_absent",
    )
    if all(evidence.get(item) is True for item in required):
        marker_path = state_root / "activation-verification.lock"
        if not marker_path.exists():
            marker = {
                "version": ACTIVATION_VERSION,
                "activation_id": packet["activation_id"],
                "status": "activation_verification_archival_pending",
                "recorded_at": _now(now),
            }
            marker["marker_hmac_sha256"] = _sign_record(
                marker, _read_key(state_root / "activation-authority.key"),
                "marker_hmac_sha256",
            )
            _exclusive_json(marker_path, marker)
        lane = state_root / "activation.lock"
        archive = state_root / "activation-ledger" / f"{packet['activation_id']}-lane.json"
        if lane.exists():
            _durable_replace(lane, archive)
        elif not archive.exists():
            raise ActivationError("activation_lane_missing")
        _atomic_json(state_root / "activation-ledger" / f"{packet['activation_id']}-verified.json", evidence)
        _archive_activation_artifacts(state_root, packet["activation_id"], "verified")
        ledger = state_root / "activation-ledger"
        required_archives = [
            f"{packet['activation_id']}-lane.json",
            f"{packet['activation_id']}-verified.json",
            f"{packet['activation_id']}-verified-activation-packet.json",
            f"{packet['activation_id']}-verified-activation-audit-intent-{packet['activation_id']}.json",
            f"{packet['activation_id']}-verified-activation-audit-receipt-{packet['activation_id']}.json",
            f"{packet['activation_id']}-verified-activation-consumed-{packet['activation_id']}.json",
            f"{packet['activation_id']}-verified-supervisor.stop.activation-{packet['activation_id']}",
        ]
        archive_hashes = {name: _sha256(ledger / name) for name in required_archives}
        completion = {
            "version": ACTIVATION_VERSION,
            "activation_id": packet["activation_id"],
            "status": "activation_verified",
            "completed_at": _now(now),
            "evidence": evidence,
            "archive_hashes": archive_hashes,
        }
        completion["completion_hmac_sha256"] = _sign_record(
            completion, _read_key(state_root / "activation-authority.key"),
            "completion_hmac_sha256",
        )
        _atomic_json(state_root / "activation-verification-complete.json", completion)
        marker_path = state_root / "activation-verification.lock"
        if marker_path.exists():
            _durable_replace(
                marker_path,
                state_root / "activation-ledger"
                / f"{packet['activation_id']}-verified-activation-verification.lock",
            )
        return {"success": True, "status": "activation_verified", "evidence": evidence}
    recover_activation(state_root=state_root, task_controller=task_controller,
                       activation_id=packet["activation_id"], failure_evidence={
                           "status": "activation_verification_failed", "evidence": evidence,
                       })
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
                                inspector=None, child_inspector=None):
    static = validate_bootstrap_tree(
        tree, generation=generation, revision=revision,
        startup_nonce=startup_nonce, require_interpreter=True,
    )
    if not static.get("authorized"):
        return static
    inspector = inspector or _inspect_exact_process
    child_inspector = child_inspector or _inspect_exact_children
    members = tree.get("members") if isinstance(tree, dict) else []
    signed_pids = {int(item.get("pid") or -1) for item in members}
    allowed_members = (
        allowed_descendant_tree.get("members", [])
        if isinstance(allowed_descendant_tree, dict) else []
    )
    allowed_pids = {int(item.get("pid") or -1) for item in allowed_members}
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
        children = child_inspector(int(record.get("pid") or -1))
        if not isinstance(children, list):
            return {"authorized": False, "reason": "owned_descendant_inspection_failed"}
        if any(int(child.get("pid") or -1) not in signed_pids | allowed_pids for child in children):
            return {"authorized": False, "reason": "unsigned_live_descendant"}
    if allowed_pids:
        allowed_roots = [
            item for item in allowed_members
            if int(item.get("parent_pid") or -1) not in allowed_pids
        ]
        if len(allowed_roots) != 1 or int(allowed_roots[0].get("parent_pid") or -1) not in signed_pids:
            return {"authorized": False, "reason": "descendant_tree_parentage_mismatch"}
    return {"authorized": True, "reason": "exact_owned_members_live",
            "member_pids": sorted(signed_pids), "complete_descendants": True}


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


def _inspect_exact_children(parent_pid, runner=subprocess.run):
    script = (
        "$ErrorActionPreference='Stop';"
        f"$p=@(Get-CimInstance Win32_Process -Filter \"ParentProcessId={int(parent_pid)}\");"
        "$p|Select-Object ProcessId,ParentProcessId,ExecutablePath,CreationDate,CommandLine|ConvertTo-Json -Compress"
    )
    completed = runner(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if completed.returncode:
        return None
    try:
        rows = json.loads(completed.stdout or "[]")
        rows = rows if isinstance(rows, list) else [rows]
        return [{
            "pid": int(row["ProcessId"]), "parent_pid": int(row["ParentProcessId"]),
            "executable_path": str(row.get("ExecutablePath") or ""),
            "creation_time": str(row.get("CreationDate") or ""),
            "command_line": str(row.get("CommandLine") or ""),
        } for row in rows]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def recover_activation(*, state_root, task_controller, activation_id,
                       failure_evidence=None, now=None):
    state_root = Path(state_root).resolve()
    ledger = state_root / "activation-ledger"
    lane_path = state_root / "activation.lock"
    lane_archives = [
        ledger / f"{activation_id}-lane-recovered.json",
        ledger / f"{activation_id}-lane.json",
    ]
    lane_candidates = [path for path in [lane_path, *lane_archives] if path.exists()]
    if len(lane_candidates) != 1:
        raise ActivationError("activation_lane_missing" if not lane_candidates
                              else "activation_lane_ambiguous")
    lane = _read_json(lane_candidates[0], "activation_lane_missing")
    lane_source = lane_candidates[0]
    lane_archive = lane_archives[0]
    if lane.get("activation_id") != activation_id:
        raise ActivationError("activation_lane_identity_mismatch")
    key = _read_key(state_root / "activation-authority.key")
    if (lane.get("version") == ACTIVATION_VERSION and not hmac.compare_digest(
            str(lane.get("lane_hmac_sha256") or ""),
            _sign_record(lane, key, "lane_hmac_sha256"))):
        raise ActivationError("activation_lane_signature_invalid")
    rollback_path = ledger / f"{activation_id}-rollback.json"
    if rollback_path.exists():
        rollback = _read_json(rollback_path, "activation_rollback_missing")
    else:
        rollback = lane.get("rollback") if isinstance(lane.get("rollback"), dict) else {}
        if not rollback:
            raise ActivationError("activation_rollback_missing")
        _atomic_json(rollback_path, rollback)
    packet_path = state_root / "activation-packet.json"
    packet_archive = ledger / f"{activation_id}-recovered-activation-packet.json"
    packet_provenance_error = None
    if not packet_path.exists() and not packet_archive.exists():
        embedded_packet = (lane.get("packet")
                           if isinstance(lane.get("packet"), dict) else {})
        if not embedded_packet:
            raise ActivationError("activation_packet_invalid")
        consumed_candidates = [path for path in (
            state_root / f"activation-consumed-{activation_id}.json",
            ledger / f"{activation_id}-recovered-activation-consumed-{activation_id}.json",
            ledger / f"{activation_id}-verified-activation-consumed-{activation_id}.json",
        ) if path.exists()]
        if len(consumed_candidates) > 1:
            packet_provenance_error = "activation_consumed_identity_ambiguous"
        elif consumed_candidates:
            consumed = _read_json(
                consumed_candidates[0], "activation_consumed_identity_invalid"
            )
            reconstructed = dict(embedded_packet)
            reconstructed["expected_instance_guid"] = consumed.get(
                "expected_instance_guid"
            )
            reconstructed["packet_hmac_sha256"] = _sign_packet(reconstructed, key)
            try:
                _validate_consumed_identity(
                    reconstructed, consumed, key,
                    require_packet_hmac=True,
                )
            except ActivationError as exc:
                packet_provenance_error = exc.status
            else:
                _atomic_json(packet_path, reconstructed)
        else:
            receipt_candidates = [path for path in (
                state_root / f"activation-audit-receipt-{activation_id}.json",
                ledger / f"{activation_id}-recovered-activation-audit-receipt-{activation_id}.json",
                ledger / f"{activation_id}-verified-activation-audit-receipt-{activation_id}.json",
            ) if path.exists()]
            if receipt_candidates:
                # Once the post-readback receipt exists, RunEx may have returned
                # an instance identity.  The pre-RunEx lane seed can no longer
                # prove the strongest packet state and must never replace it.
                packet_provenance_error = "activation_provider_identity_provenance_missing"
            else:
                # The receipt is written before RunEx.  With neither receipt nor
                # consumed identity, the signed lane packet is provably only the
                # pre-provider seed and is safe to retain for containment.
                _atomic_json(packet_path, embedded_packet)
    packet_source = packet_path if packet_path.exists() else packet_archive
    packet_missing = not packet_source.exists()
    packet = {} if packet_missing else _read_json(packet_source, "activation_packet_invalid")
    if not hmac.compare_digest(
        str(rollback.get("rollback_hmac_sha256") or ""),
        _sign_record(rollback, key, "rollback_hmac_sha256"),
    ):
        raise ActivationError("activation_rollback_signature_invalid")
    errors = []
    packet_valid = (not packet_missing and hmac.compare_digest(
        str(packet.get("packet_hmac_sha256") or ""), _sign_packet(packet, key)
    ))
    rollback_version = rollback.get("version")
    if rollback_version not in {"charlie_provider_activation_v1", ACTIVATION_VERSION}:
        raise ActivationError("activation_rollback_version_unsupported")
    authority = packet.get("authority") if isinstance(packet.get("authority"), dict) else {}
    if rollback.get("activation_id") != activation_id:
        raise ActivationError("activation_rollback_binding_invalid")
    rollback_task = (rollback.get("task_ownership") if rollback_version == ACTIVATION_VERSION
                     else packet.get("task_ownership"))
    if (not packet_valid and rollback_version != ACTIVATION_VERSION):
        raise ActivationError("legacy_activation_packet_signature_invalid")
    if _payload_sha256(rollback_task) != rollback.get("task_action_sha256"):
        raise ActivationError("activation_rollback_task_binding_invalid")
    if hasattr(task_controller, "bind_exact"):
        task_controller.bind_exact(rollback_task)
    audit_prior = rollback.get("task_scheduler_audit_prior") if rollback_version == ACTIVATION_VERSION else {
        "log_name": TASK_SCHEDULER_OPERATIONAL_LOG, "enabled": True,
    }
    if (rollback_version == ACTIVATION_VERSION and (not isinstance(audit_prior, dict)
            or audit_prior.get("log_name") != TASK_SCHEDULER_OPERATIONAL_LOG
            or not isinstance(audit_prior.get("enabled"), bool)
            or rollback.get("task_scheduler_audit_rollback_command") != (
                f"wevtutil sl {TASK_SCHEDULER_OPERATIONAL_LOG} "
                f"/e:{str(audit_prior.get('enabled')).lower()}"))):
        raise ActivationError("activation_audit_rollback_binding_invalid")
    if not hasattr(task_controller, "bind_audit_channel_state"):
        raise ActivationError("task_scheduler_audit_controller_required")
    task_controller.bind_audit_channel_state(audit_prior)
    audit_mutation_required = (rollback.get("task_scheduler_audit_mutation_required")
                               if rollback_version == ACTIVATION_VERSION else False)
    if (rollback_version == ACTIVATION_VERSION
            and audit_mutation_required is not (not audit_prior["enabled"])):
        raise ActivationError("activation_audit_rollback_binding_invalid")
    try:
        task_controller.disable_exact(rollback["task_action_sha256"])
    except Exception as exc:
        errors.append({"component": "scheduled_task", "status": getattr(exc, "status", exc.__class__.__name__)})
    audit_intent_valid = rollback_version != ACTIVATION_VERSION
    audit_receipt_valid = rollback_version != ACTIVATION_VERSION
    try:
        if rollback_version != ACTIVATION_VERSION:
            raise StopIteration
        intent_live = state_root / f"activation-audit-intent-{activation_id}.json"
        intent_archive = ledger / f"{activation_id}-recovered-activation-audit-intent-{activation_id}.json"
        intent_path = intent_live if intent_live.exists() else intent_archive
        if not intent_path.exists():
            audit_intent_valid = False
            raise FileNotFoundError("activation_audit_intent_missing")
        audit_intent = _read_json(intent_path, "activation_audit_intent_invalid")
        audit_intent_valid = bool(
            hmac.compare_digest(
                str(audit_intent.get("audit_intent_hmac_sha256") or ""),
                _sign_record(audit_intent, key, "audit_intent_hmac_sha256"))
            and audit_intent.get("activation_id") == activation_id
            and audit_intent.get("status") == "task_scheduler_audit_enable_intended"
            and audit_intent.get("log_name") == TASK_SCHEDULER_OPERATIONAL_LOG
            and audit_intent.get("prior_enabled") is audit_prior["enabled"]
            and audit_intent.get("intended_enabled") is True
        )
        if not audit_intent_valid:
            raise ActivationError("activation_audit_intent_invalid")
    except StopIteration:
        pass
    except FileNotFoundError:
        # The intent is written before any channel mutation. Its absence is a
        # recoverable pre-mutation crash state; task and stop containment are
        # still completed from the authenticated rollback record.
        pass
    except Exception as exc:
        errors.append({"component": "task_scheduler_audit_intent",
                       "status": getattr(exc, "status", exc.__class__.__name__)})
    try:
        if rollback_version != ACTIVATION_VERSION:
            raise StopIteration
        receipt_live = state_root / f"activation-audit-receipt-{activation_id}.json"
        receipt_archive = ledger / f"{activation_id}-recovered-activation-audit-receipt-{activation_id}.json"
        receipt_path = receipt_live if receipt_live.exists() else receipt_archive
        if not receipt_path.exists():
            audit_receipt_valid = False
            raise FileNotFoundError("activation_audit_receipt_missing")
        audit_receipt = _read_json(receipt_path, "activation_audit_receipt_invalid")
        audit_receipt_valid = bool(
            hmac.compare_digest(
                str(audit_receipt.get("audit_receipt_hmac_sha256") or ""),
                _sign_record(audit_receipt, key, "audit_receipt_hmac_sha256"))
            and audit_receipt.get("activation_id") == activation_id
            and audit_receipt.get("status") == "task_scheduler_audit_enable_readback_complete"
            and audit_receipt.get("log_name") == TASK_SCHEDULER_OPERATIONAL_LOG
            and audit_receipt.get("prior_enabled") is audit_prior["enabled"]
            and audit_receipt.get("current_enabled") is True
            and audit_receipt.get("changed") is audit_mutation_required
            and audit_receipt.get("event_record_id_lower_bound")
            == rollback.get("task_scheduler_event_record_id_lower_bound")
        )
        if not audit_receipt_valid:
            raise ActivationError("activation_audit_receipt_invalid")
    except StopIteration:
        pass
    except FileNotFoundError:
        # A missing post-readback receipt is an ordinary interruption window.
        # Enabled is additive and never rolled back automatically, so exact
        # task/stop containment can safely retire this activation lane.
        pass
    except Exception as exc:
        errors.append({"component": "task_scheduler_audit_receipt",
                       "status": getattr(exc, "status", exc.__class__.__name__)})
    # Enabled is the fail-safe audit posture. A Boolean channel state has no
    # writer generation, so automatic disable could overwrite a later
    # independent enablement. Keep the authenticated prior state and rollback
    # command as evidence, but never auto-disable the channel.
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
    if (not packet_missing and (not packet_valid
            or rollback.get("authority_sha256") != packet.get("authority_sha256")
            or rollback.get("stop_marker_sha256") != authority.get("stop_marker_sha256")
            or rollback.get("task_action_sha256") != authority.get("task_action_sha256")
            or rollback_task != packet.get("task_ownership"))):
        errors.append({"component": "activation_packet",
                       "status": "activation_packet_or_binding_invalid"})
    if packet_provenance_error:
        errors.append({"component": "activation_packet",
                       "status": packet_provenance_error})
    if errors:
        raise ActivationError("activation_recovery_incomplete", errors=errors)
    failure_path = ledger / f"{activation_id}-failure.json"
    if not failure_path.exists():
        failure = dict(failure_evidence) if isinstance(failure_evidence, dict) else {}
        if not failure.get("status") or failure.get("status") == "governed_stop_active":
            raise ActivationError("activation_failure_evidence_required")
        failure_record = {
            "version": RECOVERY_PROJECTION_VERSION,
            "activation_id": activation_id,
            "status": "activation_failure_preserved",
            "recorded_at": _now(now),
            "failure_bytes_b64": base64.b64encode(_canonical(failure)).decode("ascii"),
            "failure_sha256": hashlib.sha256(_canonical(failure)).hexdigest(),
        }
        failure_record["failure_hmac_sha256"] = _sign_record(
            failure_record, key, "failure_hmac_sha256"
        )
        _exclusive_json(failure_path, failure_record)
    pending = {
        "version": RECOVERY_PROJECTION_VERSION,
        "activation_id": activation_id,
        "status": "governed_stop_reconciliation_pending",
        "rollback_sha256": _sha256(state_root / "activation-ledger" / f"{activation_id}-rollback.json"),
        "stop_marker_sha256": rollback["stop_marker_sha256"],
        "task_action_sha256": rollback["task_action_sha256"],
        "historical_failure_sha256": _sha256(failure_path),
        "lane_sha256": _payload_sha256(lane),
    }
    pending["recovery_hmac_sha256"] = _sign_record(
        pending, key, "recovery_hmac_sha256"
    )
    _atomic_json(state_root / "activation-reconciliation-pending.json", pending)
    _archive_activation_artifacts(state_root, activation_id, "recovered")
    if lane_source != lane_archive and lane_source.exists():
        _durable_replace(lane_source, lane_archive)
    completion = {
        "version": RECOVERY_PROJECTION_VERSION,
        "activation_id": activation_id,
        "status": "activation_recovery_completed",
        "completed_at": _now(now),
        "historical_failure_sha256": _sha256(failure_path),
        "recovered_packet_sha256": _sha256(packet_archive),
        "rollback_sha256": _sha256(ledger / f"{activation_id}-rollback.json"),
        "lane_sha256": _sha256(lane_archive),
        "stop_marker_sha256": rollback["stop_marker_sha256"],
        "task_action_sha256": rollback["task_action_sha256"],
    }
    completion["completion_hmac_sha256"] = _sign_record(
        completion, key, "completion_hmac_sha256"
    )
    completion_path = ledger / f"{activation_id}-recovery-completed.json"
    if completion_path.exists():
        existing_completion = _read_json(completion_path, "activation_recovery_completion_invalid")
        if (existing_completion.get("activation_id") != activation_id
                or existing_completion.get("status") != "activation_recovery_completed"
                or not hmac.compare_digest(
                    str(existing_completion.get("completion_hmac_sha256") or ""),
                    _sign_record(existing_completion, key, "completion_hmac_sha256"))):
            raise ActivationError("activation_recovery_completion_conflict")
    else:
        _exclusive_json(completion_path, completion)
    return {"success": True, "status": "activation_recovered", "activation_id": activation_id}


def reconcile_recovered_activation_stop(*, state_root, activation_id,
                                        failure_evidence, task_reader=read_watchdog_task,
                                        process_presence_reader=None, now=None):
    """Project an authenticated completed rollback as current stopped authority.

    The transient activation failure remains an immutable signed ledger record.
    This transition is deliberately unavailable until every stopped-state
    invariant and every archived activation binding has been re-read exactly.
    """
    state_root = Path(state_root).resolve()
    ledger = state_root / "activation-ledger"
    key = _read_key(state_root / "activation-authority.key")
    pending_path = state_root / "activation-reconciliation-pending.json"
    reconciled_path = ledger / f"{activation_id}-reconciled.json"
    replay = reconciled_path.exists() and not pending_path.exists()
    reconciliation_lock = state_root / "activation-reconciliation.lock"
    if replay:
        existing_projection = None
        try:
            existing_projection = _read_json(
                state_root / "watchdog.json", "watchdog_state_invalid"
            )
        except ActivationError:
            pass
        projection_valid = bool(
            existing_projection
            and existing_projection.get("version") == RECOVERY_PROJECTION_VERSION
            and existing_projection.get("status") == "governed_stop_active"
            and existing_projection.get("recovered_activation_id") == activation_id
            and existing_projection.get("reconciled_sha256") == _sha256(reconciled_path)
            and hmac.compare_digest(
                str(existing_projection.get("projection_hmac_sha256") or ""),
                _sign_record(existing_projection, key, "projection_hmac_sha256"))
        )
        if projection_valid:
            if reconciliation_lock.exists():
                owner = _read_json(
                    reconciliation_lock, "activation_reconciliation_lane_invalid"
                )
                if owner.get("activation_id") != activation_id:
                    raise ActivationError("activation_reconciliation_lane_active")
                _durable_replace(
                    reconciliation_lock,
                    ledger / f"{activation_id}-reconciliation-lane.json",
                )
            return existing_projection
        if not reconciliation_lock.exists():
            raise ActivationError("activation_reconciliation_replay_conflict")
        owner = _read_json(
            reconciliation_lock, "activation_reconciliation_lane_invalid"
        )
        if owner.get("activation_id") != activation_id:
            raise ActivationError("activation_reconciliation_lane_active")
    resumed_historical_recovery = not pending_path.exists() and not replay
    if resumed_historical_recovery:
        rollback_path = ledger / f"{activation_id}-rollback.json"
        rollback_seed = _read_json(rollback_path, "activation_rollback_missing")
        pending = {
            "version": RECOVERY_PROJECTION_VERSION,
            "activation_id": activation_id,
            "status": "governed_stop_reconciliation_pending",
            "rollback_sha256": _sha256(rollback_path),
            "stop_marker_sha256": rollback_seed.get("stop_marker_sha256"),
            "task_action_sha256": rollback_seed.get("task_action_sha256"),
        }
        pending["recovery_hmac_sha256"] = _sign_record(
            pending, key, "recovery_hmac_sha256"
        )
    else:
        pending = _read_json(
            reconciled_path if replay else pending_path,
            "activation_reconciliation_not_pending",
        )
    if (pending.get("version") != RECOVERY_PROJECTION_VERSION
            or pending.get("activation_id") != activation_id
            or pending.get("status") != "governed_stop_reconciliation_pending"
            or not hmac.compare_digest(
                str(pending.get("recovery_hmac_sha256") or ""),
                _sign_record(pending, key, "recovery_hmac_sha256"))):
        raise ActivationError("activation_reconciliation_binding_invalid")
    if any((
        (state_root / "activation.lock").exists(),
        (state_root / "release-staging.lock").exists(),
        (state_root / "supervisor.lock").exists(),
    )):
        raise ActivationError("activation_reconciliation_lane_active")
    if reconciliation_lock.exists():
        if not replay:
            owner = _read_json(
                reconciliation_lock, "activation_reconciliation_lane_invalid"
            )
            presence = (process_presence_reader or _process_presence)(
                owner.get("owner_pid")
            )
            if owner.get("activation_id") != activation_id or presence != "absent":
                status = ("activation_reconciliation_process_proof_unavailable"
                          if presence == "unknown"
                          else "activation_reconciliation_lane_active")
                raise ActivationError(status)
    else:
        _exclusive_json(reconciliation_lock, {
            "version": RECOVERY_PROJECTION_VERSION,
            "activation_id": activation_id,
            "status": "activation_reconciliation_owned",
            "owner_pid": os.getpid(),
        })
    if any((
        (state_root / "activation.lock").exists(),
        (state_root / "release-staging.lock").exists(),
        (state_root / "supervisor.lock").exists(),
    )):
        raise ActivationError("activation_reconciliation_lane_active")
    rollback_path = ledger / f"{activation_id}-rollback.json"
    rollback = _read_json(rollback_path, "activation_rollback_missing")
    if (not hmac.compare_digest(
            str(rollback.get("rollback_hmac_sha256") or ""),
            _sign_record(rollback, key, "rollback_hmac_sha256"))
            or rollback.get("activation_id") != activation_id
            or _sha256(rollback_path) != pending.get("rollback_sha256")):
        raise ActivationError("activation_rollback_binding_invalid")
    lane_archive = ledger / f"{activation_id}-lane-recovered.json"
    packet_archive = ledger / f"{activation_id}-recovered-activation-packet.json"
    if not lane_archive.is_file() or not packet_archive.is_file():
        raise ActivationError("activation_recovery_archive_incomplete")
    recovered_lane = _read_json(lane_archive, "activation_recovered_lane_invalid")
    if resumed_historical_recovery:
        pending["lane_sha256"] = _payload_sha256(recovered_lane)
        pending["recovery_hmac_sha256"] = _sign_record(
            pending, key, "recovery_hmac_sha256"
        )
    if (recovered_lane.get("activation_id") != activation_id
            or _payload_sha256(recovered_lane) != pending.get("lane_sha256")):
        raise ActivationError("activation_recovered_lane_binding_invalid")
    packet = _read_json(packet_archive, "activation_recovered_packet_invalid")
    if (packet.get("activation_id") != activation_id
            or not hmac.compare_digest(
                str(packet.get("packet_hmac_sha256") or ""), _sign_packet(packet, key))):
        raise ActivationError("activation_recovered_packet_binding_invalid")
    authority = packet.get("authority") if isinstance(packet.get("authority"), dict) else {}
    if any((
        rollback.get("authority_sha256") != packet.get("authority_sha256"),
        rollback.get("stop_marker_sha256") != authority.get("stop_marker_sha256"),
        rollback.get("task_action_sha256") != authority.get("task_action_sha256"),
        pending.get("stop_marker_sha256") != rollback.get("stop_marker_sha256"),
        pending.get("task_action_sha256") != rollback.get("task_action_sha256"),
    )):
        raise ActivationError("activation_reconciliation_authority_mismatch")
    stop_path = state_root / "supervisor.stop"
    if not stop_path.is_file() or _sha256(stop_path) != rollback["stop_marker_sha256"]:
        raise ActivationError("activation_reconciliation_stop_mismatch")
    supervisor = _read_json(state_root / "supervisor.json", "supervisor_state_invalid")
    if supervisor.get("status") != "supervisor_stopped":
        raise ActivationError("activation_reconciliation_supervisor_not_stopped")
    process_pids = {supervisor.get("pid"), supervisor.get("child_pid")}
    for tree_name in ("supervisor_tree_identity", "process_tree_identity"):
        tree = supervisor.get(tree_name)
        root = tree.get("root") if isinstance(tree, dict) else None
        if isinstance(root, dict):
            process_pids.add(root.get("pid"))
        members = tree.get("members") if isinstance(tree, dict) else []
        process_pids.update(
            member.get("pid") for member in members if isinstance(member, dict)
        )
    process_pids.discard(None)
    process_pids.discard("")
    if not process_pids:
        raise ActivationError("activation_reconciliation_process_identity_missing")
    for pid in process_pids:
        presence = (process_presence_reader or _process_presence)(pid)
        if presence == "live":
            raise ActivationError("activation_reconciliation_process_still_live")
        if presence != "absent":
            raise ActivationError("activation_reconciliation_process_proof_unavailable")
    task = task_reader()
    _validate_exact_task(task, Path(str(packet.get("runtime_root") or "")))
    if _task_action_sha256(task) != rollback["task_action_sha256"]:
        raise ActivationError("activation_reconciliation_task_mismatch")
    failure_path = ledger / f"{activation_id}-failure.json"
    if failure_path.exists():
        existing = _read_json(failure_path, "activation_failure_record_invalid")
        if (existing.get("version") != RECOVERY_PROJECTION_VERSION
                or existing.get("activation_id") != activation_id
                or existing.get("status") != "activation_failure_preserved"
                or not hmac.compare_digest(
                str(existing.get("failure_hmac_sha256") or ""),
                _sign_record(existing, key, "failure_hmac_sha256"))):
            raise ActivationError("activation_failure_record_conflict")
    else:
        failure = dict(failure_evidence) if isinstance(failure_evidence, dict) else {}
        if not failure.get("status") or failure.get("status") == "governed_stop_active":
            raise ActivationError("activation_failure_evidence_required")
        failure_record = {
            "version": RECOVERY_PROJECTION_VERSION,
            "activation_id": activation_id,
            "status": "activation_failure_preserved",
            "recorded_at": _now(now),
            "failure_bytes_b64": base64.b64encode(_canonical(failure)).decode("ascii"),
            "failure_sha256": hashlib.sha256(_canonical(failure)).hexdigest(),
        }
        failure_record["failure_hmac_sha256"] = _sign_record(
            failure_record, key, "failure_hmac_sha256"
        )
        _exclusive_json(failure_path, failure_record)
    if pending.get("historical_failure_sha256") and pending.get("historical_failure_sha256") != _sha256(failure_path):
        raise ActivationError("activation_failure_record_binding_invalid")
    completion_path = ledger / f"{activation_id}-recovery-completed.json"
    if completion_path.exists():
        completion = _read_json(completion_path, "activation_recovery_completion_invalid")
    else:
        completion = {
            "version": RECOVERY_PROJECTION_VERSION,
            "activation_id": activation_id,
            "status": "activation_recovery_completed",
            "completed_at": _now(now),
            "historical_failure_sha256": _sha256(failure_path),
            "recovered_packet_sha256": _sha256(packet_archive),
            "rollback_sha256": _sha256(rollback_path),
            "lane_sha256": _sha256(lane_archive),
            "stop_marker_sha256": rollback["stop_marker_sha256"],
            "task_action_sha256": rollback["task_action_sha256"],
        }
        completion["completion_hmac_sha256"] = _sign_record(
            completion, key, "completion_hmac_sha256"
        )
        _exclusive_json(completion_path, completion)
    if (completion.get("version") != RECOVERY_PROJECTION_VERSION
            or completion.get("activation_id") != activation_id
            or completion.get("status") != "activation_recovery_completed"
            or not hmac.compare_digest(
                str(completion.get("completion_hmac_sha256") or ""),
                _sign_record(completion, key, "completion_hmac_sha256"))
            or any(completion.get(name) != expected for name, expected in (
                ("historical_failure_sha256", _sha256(failure_path)),
                ("recovered_packet_sha256", _sha256(packet_archive)),
                ("rollback_sha256", _sha256(rollback_path)),
                ("lane_sha256", _sha256(lane_archive)),
            ))):
        raise ActivationError("activation_recovery_completion_binding_invalid")
    if resumed_historical_recovery:
        pending["historical_failure_sha256"] = _sha256(failure_path)
        pending["lane_sha256"] = _payload_sha256(recovered_lane)
        pending["recovery_hmac_sha256"] = _sign_record(pending, key, "recovery_hmac_sha256")
        _atomic_json(pending_path, pending)
    projection = {
        "version": RECOVERY_PROJECTION_VERSION,
        "status": "governed_stop_active",
        "started": False,
        "checked_at": _now(now),
        "stop_marker": str(stop_path),
        "stop_marker_sha256": rollback["stop_marker_sha256"],
        "scheduled_task_state": "Disabled",
        "task_action_sha256": rollback["task_action_sha256"],
        "supervisor_status": "supervisor_stopped",
        "recovered_activation_id": activation_id,
        "historical_failure_path": str(failure_path),
        "historical_failure_sha256": _sha256(failure_path),
        "recovered_packet_path": str(packet_archive),
        "recovered_packet_sha256": _sha256(packet_archive),
        "recovered_lane_path": str(lane_archive),
        "recovered_lane_sha256": _sha256(lane_archive),
        "rollback_path": str(rollback_path),
        "rollback_sha256": _sha256(rollback_path),
        "recovery_completion_path": str(completion_path),
        "recovery_completion_sha256": _sha256(completion_path),
        "reconciled_path": str(reconciled_path),
        "reconciled_sha256": "pending",
        "runner_status_before": "not_read_after_authenticated_activation_recovery",
    }
    projection["projection_hmac_sha256"] = _sign_record(
        projection, key, "projection_hmac_sha256"
    )
    if not replay:
        _durable_replace(pending_path, reconciled_path)
    projection["reconciled_sha256"] = _sha256(reconciled_path)
    projection["projection_hmac_sha256"] = _sign_record(
        projection, key, "projection_hmac_sha256"
    )
    _atomic_json(state_root / "watchdog.json", projection)
    _durable_replace(reconciliation_lock,
                     ledger / f"{activation_id}-reconciliation-lane.json")
    return projection


def _process_presence(pid, runner=subprocess.run):
    """Return live/absent/unknown; an inspection failure is never absence."""
    try:
        pid = int(pid)
        if pid <= 0:
            return "unknown"
        if os.name == "nt":
            completed = runner(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode != 0:
                return "unknown"
            rows = list(csv.reader(str(completed.stdout or "").splitlines()))
            return "live" if any(
                len(row) > 1 and row[1].strip() == str(pid) for row in rows
            ) else "absent"
        os.kill(pid, 0)
        return "live"
    except ProcessLookupError:
        return "absent"
    except (PermissionError, TypeError, ValueError, OSError, subprocess.SubprocessError):
        return "unknown"


def verify_provider_origin(inspector, *, expected_task):
    current = inspector(os.getpid())
    if not isinstance(current, dict) or not current.get("inspection_complete"):
        reason = (str(current.get("reason") or "provider_identity_incomplete")
                  if isinstance(current, dict) else "provider_identity_incomplete")
        return {"authorized": False, "reason": reason}
    ancestry = current.get("ancestry")
    if not isinstance(ancestry, list) or not ancestry:
        return {"authorized": False, "reason": "provider_ancestry_incomplete"}
    names = [Path(str(item.get("executable_path") or "")).name.casefold() for item in ancestry]
    if any(name in PROTECTED_ANCESTRY for name in names):
        return {"authorized": False, "reason": "terminal_ancestry_rejected"}
    parent = ancestry[0]
    parent_name = Path(str(parent.get("executable_path") or "")).name.casefold()
    current_name = Path(str(current.get("executable_path") or "")).name.casefold()
    if (current_name != "pythonw.exe" or parent_name not in PROVIDER_PARENTS
            or not parent.get("provider_identity_verified")):
        return {"authorized": False, "reason": "scheduled_provider_origin_required"}
    row = expected_task[0] if isinstance(expected_task, list) and len(expected_task) == 1 else {}
    provider_action = {
        "execute": str(parent.get("action_execute") or ""),
        "arguments": str(parent.get("action_arguments") or ""),
        "working_directory": str(parent.get("action_working_directory") or ""),
    }
    expected_action = {
        "execute": str(row.get("execute") or ""),
        "arguments": str(row.get("arguments") or ""),
        "working_directory": str(row.get("working_directory") or ""),
    }
    if any(
            str(Path(provider_action[field]).resolve()).casefold()
            != str(Path(expected_action[field]).resolve()).casefold()
            if field != "arguments" else provider_action[field] != expected_action[field]
            for field in expected_action):
        return {"authorized": False, "reason": "provider_task_action_mismatch"}
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
            "parent_executable": parent_name,
            "provider_instance_guid": str(parent.get("instance_guid") or "")}


def inspect_current_provider_chain(pid=None, runner=subprocess.run, current_identity=None,
                                   provider_identity=None, activation_id=None,
                                   activation_prepared_at=None,
                                   activation_event_record_id_lower_bound=None):
    """Inspect this process locally and only its exact parent PIDs through CIM."""
    requested_pid = int(pid or os.getpid())
    if current_identity is not None:
        current = current_identity()
    elif requested_pid == os.getpid():
        current = _local_current_process_identity()
    else:
        current = _inspect_exact_process(requested_pid, runner=runner)
    required = ("pid", "parent_pid", "executable_path", "creation_time", "command_line")
    if (not isinstance(current, dict) or not current.get("inspection_complete")
            or int(current.get("pid") or -1) != requested_pid
            or any(not str(current.get(field) or "") for field in required[2:])):
        return {"inspection_complete": False, "reason": "provider_identity_unreadable"}

    provider_reader = provider_identity or (
        (lambda: _inspect_windows_task_scheduler_provider(
            requested_pid, runner=runner, activation_id=activation_id,
            activation_prepared_at=activation_prepared_at,
            event_record_id_lower_bound=activation_event_record_id_lower_bound))
        if os.name == "nt" else lambda: {"inspection_complete": False}
    )
    provider = provider_reader()
    if (not _valid_task_scheduler_provider(provider)
            or int(provider.get("engine_pid") or -1) != requested_pid):
        reason = (str(provider.get("reason") or "provider_identity_unreadable")
                  if isinstance(provider, dict) else "provider_identity_unreadable")
        return {"inspection_complete": False, "reason": reason}

    chain = []
    next_pid = int(current.get("parent_pid") or 0)
    seen = {requested_pid}
    terminated = False
    for _index in range(12):
        if next_pid <= 0:
            terminated = True
            break
        if next_pid in seen:
            return {"inspection_complete": False, "reason": "provider_ancestry_cycle"}
        if next_pid == int(provider["pid"]):
            provider_again = provider_reader()
            stable_provider_fields = (
                "pid", "creation_time", "service_name", "service_state",
                "start_name", "executable_path", "service_binary_path", "service_dll",
                "system_root",
                "engine_pid", "instance_guid", "task_path", "current_action",
                "action_execute", "action_arguments", "action_working_directory",
                "evidence_source", "event_record_id", "event_time",
                "event_activity_id", "activation_id",
            )
            if (not _valid_task_scheduler_provider(provider_again) or any(
                    str(provider_again.get(field) or "").casefold()
                    != str(provider.get(field) or "").casefold()
                    for field in stable_provider_fields)):
                return {"inspection_complete": False, "reason": "provider_ancestry_changed"}
            chain.append({key: value for key, value in provider.items()
                          if key != "inspection_complete"})
            terminated = True
            break
        item = _inspect_exact_process(next_pid, runner=runner)
        if (not item.get("inspection_complete") or int(item.get("pid") or -1) != next_pid
                or not str(item.get("executable_path") or "")
                or not str(item.get("creation_time") or "")):
            return {"inspection_complete": False, "reason": "provider_ancestry_unreadable"}
        chain.append({key: value for key, value in item.items() if key != "inspection_complete"})
        seen.add(next_pid)
        next_pid = int(item.get("parent_pid") or 0)
    else:
        return {"inspection_complete": False, "reason": "provider_ancestry_depth_exceeded"}
    if not terminated or not chain:
        return {"inspection_complete": False, "reason": "provider_ancestry_incomplete"}

    # A second exact read binds the immediate provider identity across the
    # inspection window and fails closed if a PID was reused or reparented.
    if not chain[0].get("provider_identity_verified"):
        parent_again = _inspect_exact_process(int(current["parent_pid"]), runner=runner)
        stable_fields = ("pid", "parent_pid", "executable_path", "creation_time")
        if (not parent_again.get("inspection_complete") or any(
                str(parent_again.get(field) or "").casefold()
                != str(chain[0].get(field) or "").casefold()
                for field in stable_fields)):
            return {"inspection_complete": False, "reason": "provider_ancestry_changed"}
    if current_identity is not None:
        current_again = current_identity()
    elif requested_pid == os.getpid():
        current_again = _local_current_process_identity()
    else:
        current_again = _inspect_exact_process(requested_pid, runner=runner)
    stable_current_fields = (
        "pid", "parent_pid", "executable_path", "creation_time", "command_line",
    )
    if (not isinstance(current_again, dict) or not current_again.get("inspection_complete")
            or any(
                str(current_again.get(field) or "").casefold()
                != str(current.get(field) or "").casefold()
                for field in stable_current_fields)):
        return {"inspection_complete": False, "reason": "provider_child_identity_changed"}
    return {**current, "inspection_complete": True, "ancestry": chain}


def _inspect_windows_task_scheduler_provider(engine_pid, runner=subprocess.run,
                                             process_creation_time=None,
                                             activation_id=None,
                                             activation_prepared_at=None,
                                             event_record_id_lower_bound=None):
    """Bind this PID to one Task Scheduler instance and its exact service.

    Task Scheduler can start the action before its COM running-instance view
    exposes that action. Retry only the exact EnginePID miss for a short,
    bounded window; every successful read still has to prove the complete
    service, task-instance, action, and provider-process identity.
    """
    script = (
        "$ErrorActionPreference='Stop';"
        "$q=(& sc.exe queryex Schedule 2>&1|Out-String);"
        "$c=(& sc.exe qc Schedule 2>&1|Out-String);"
        "if($LASTEXITCODE-ne 0){exit 4};"
        "$providerPid=[int]([regex]::Match($q,'(?m)^\\s*PID\\s*:\\s*(\\d+)\\s*$').Groups[1].Value);"
        "$state=[regex]::Match($q,'(?m)^\\s*STATE\\s*:\\s*\\d+\\s+(\\S+)').Groups[1].Value;"
        "$binary=[regex]::Match($c,'(?m)^\\s*BINARY_PATH_NAME\\s*:\\s*(.+?)\\s*$').Groups[1].Value;"
        "$start=[regex]::Match($c,'(?m)^\\s*SERVICE_START_NAME\\s*:\\s*(.+?)\\s*$').Groups[1].Value;"
        "if($providerPid-le 0-or-not$binary){exit 5};"
        "$ts=New-Object -ComObject 'Schedule.Service';$ts.Connect();"
        "$task=$ts.GetFolder('\\').GetTask('" + TASK_NAME.replace("'", "''") + "');"
        "$deadline=[DateTime]::UtcNow.AddSeconds(5);"
        "do{$instances=@($task.GetInstances(0)|Where-Object {[int]$_.EnginePID-eq" + str(int(engine_pid)) + "});"
        "if($instances.Count-eq 0-and[DateTime]::UtcNow-lt$deadline){Start-Sleep -Milliseconds 100}}"
        "while($instances.Count-eq 0-and[DateTime]::UtcNow-lt$deadline);"
        "$instance=$null;$evidenceSource='running_instance';$eventRecordId=0;$eventTime='';$eventActivity='';$engineCreated='';"
        "if($instances.Count-ne 0){if($instances.Count-ne 1){exit 8};$instance=$instances[0];$instance.Refresh()}"
        "else{"
        "$engineProcess=Get-CimInstance Win32_Process -Filter 'ProcessId=" + str(int(engine_pid)) + "';"
        "if($null-eq$engineProcess-or[int]$engineProcess.ProcessId-ne" + str(int(engine_pid)) + "){exit 12};"
        "$engineCreated=if($engineProcess.CreationDate-is[DateTime]){$engineProcess.CreationDate.ToUniversalTime()}else{[Management.ManagementDateTimeConverter]::ToDateTime([string]$engineProcess.CreationDate).ToUniversalTime()};"
        "$log=Get-WinEvent -ListLog 'Microsoft-Windows-TaskScheduler/Operational' -ErrorAction Stop;"
        "if(-not$log.IsEnabled){exit 9};"
        "$prepared=[DateTime]::Parse('" + str(activation_prepared_at or "").replace("'", "''") + "').ToUniversalTime();"
        "$now=[DateTime]::UtcNow;"
        "$matches=@(Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-TaskScheduler/Operational';Id=200;StartTime=$prepared.AddSeconds(-2)} -ErrorAction Stop|Where-Object {"
        "$xml=[xml]$_.ToXml();$d=@{};foreach($x in $xml.Event.EventData.Data){$d[[string]$x.Name]=[string]$x.'#text'};"
        "([string]$d.TaskName).Equals('\\" + TASK_NAME.replace("'", "''") + "',[StringComparison]::OrdinalIgnoreCase)-and"
        "([int]$d.EnginePID-eq" + str(int(engine_pid)) + ")-and[long]$_.RecordId-gt" + str(int(event_record_id_lower_bound or 0)) + "-and$_.TimeCreated.ToUniversalTime()-ge$prepared-and$_.TimeCreated.ToUniversalTime()-ge$engineCreated-and$_.TimeCreated.ToUniversalTime()-le$engineCreated.AddSeconds(10)-and$_.TimeCreated.ToUniversalTime()-le$now.AddSeconds(2)"
        "});if($matches.Count-eq 0){exit 6};if($matches.Count-ne 1){exit 10};"
        "$m=$matches[0];$mx=[xml]$m.ToXml();$md=@{};foreach($x in $mx.Event.EventData.Data){$md[[string]$x.Name]=[string]$x.'#text'};"
        "$eventInstance=if($md.TaskInstanceId){$md.TaskInstanceId}else{$md.InstanceId};"
        "$instance=[pscustomobject]@{EnginePID=[int]$md.EnginePID;InstanceGuid=[string]$eventInstance;Path=[string]$md.TaskName;CurrentAction=[string]$md.ActionName};"
        "$evidenceSource='operational_event';$eventRecordId=[long]$m.RecordId;$eventTime=$m.TimeCreated.ToUniversalTime().ToString('o');$eventActivity=[string]$mx.Event.System.Correlation.ActivityID}"
        "$actions=@($task.Definition.Actions);if($actions.Count-ne 1-or[int]$actions[0].Type-ne 0){exit 7};"
        "$action=$actions[0];"
        "if($evidenceSource-eq'operational_event'-and-not([string]$instance.CurrentAction).Equals([string]$action.Path,[StringComparison]::OrdinalIgnoreCase)){exit 11};"
        "$dll=(Get-ItemProperty -LiteralPath "
        "'Registry::HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Services\\Schedule\\Parameters' "
        "-Name ServiceDll).ServiceDll;"
        "$root=(Get-ItemProperty -LiteralPath "
        "'Registry::HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion' "
        "-Name SystemRoot).SystemRoot;"
        "[pscustomobject]@{ProcessId=$providerPid;"
        "Name='Schedule';State=$state;StartName=$start;PathName=$binary;"
        "EnginePID=[int]$instance.EnginePID;InstanceGuid=[string]$instance.InstanceGuid;"
        "TaskPath=[string]$instance.Path;CurrentAction=[string]$instance.CurrentAction;"
        "ActionExecute=[string]$action.Path;ActionArguments=[string]$action.Arguments;"
        "ActionWorkingDirectory=[string]$action.WorkingDirectory;"
        "ServiceDll=[Environment]::ExpandEnvironmentVariables($dll);SystemRoot=$root;"
        "EvidenceSource=$evidenceSource;EventRecordId=$eventRecordId;EventTime=$eventTime;EventActivityId=$eventActivity;"
        "EngineCreationTime=$(if($engineCreated){$engineCreated.ToString('o')}else{''});"
        "EventRecordIdLowerBound=" + str(int(event_record_id_lower_bound or 0)) + ";"
        "ActivationId='" + str(activation_id or "").replace("'", "''") + "'}"
        "|ConvertTo-Json -Compress"
    )
    try:
        completed = runner(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except subprocess.TimeoutExpired:
        return {"inspection_complete": False, "reason": "provider_inspection_deadline_exceeded"}
    except (OSError, subprocess.SubprocessError):
        return {"inspection_complete": False, "reason": "provider_inspector_unavailable"}
    if completed.returncode:
        reasons = {
            4: "task_scheduler_service_query_failed",
            5: "task_scheduler_service_identity_missing",
            6: "task_instance_visibility_timeout",
            7: "task_action_identity_invalid",
            8: "task_instance_identity_ambiguous",
            9: "task_scheduler_operational_log_disabled",
            10: "task_event_identity_ambiguous",
            11: "task_event_action_mismatch",
            12: "task_engine_process_identity_missing",
        }
        return {"inspection_complete": False,
                "reason": reasons.get(completed.returncode, "provider_identity_unreadable")}
    try:
        row = json.loads(completed.stdout)
        creation_time = (process_creation_time or _windows_process_creation_time)(
            int(row["ProcessId"])
        )
        if not creation_time:
            return {"inspection_complete": False}
        binary_tokens = _command_tokens(row.get("PathName"))
        return {
            "inspection_complete": True,
            "pid": int(row["ProcessId"]),
            "creation_time": str(creation_time),
            "service_name": str(row.get("Name") or ""),
            "service_state": str(row.get("State") or ""),
            "start_name": str(row.get("StartName") or ""),
            "executable_path": binary_tokens[0] if binary_tokens else "",
            "service_binary_path": str(row.get("PathName") or ""),
            "service_dll": str(row.get("ServiceDll") or ""),
            "system_root": str(row.get("SystemRoot") or ""),
            "engine_pid": int(row.get("EnginePID") or 0),
            "instance_guid": str(row.get("InstanceGuid") or ""),
            "task_path": str(row.get("TaskPath") or ""),
            "current_action": str(row.get("CurrentAction") or ""),
            "action_execute": str(row.get("ActionExecute") or ""),
            "action_arguments": str(row.get("ActionArguments") or ""),
            "action_working_directory": str(row.get("ActionWorkingDirectory") or ""),
            "provider_identity_verified": True,
            "evidence_source": str(row.get("EvidenceSource") or ""),
            "event_record_id": int(row.get("EventRecordId") or 0),
            "event_time": str(row.get("EventTime") or ""),
            "event_activity_id": str(row.get("EventActivityId") or ""),
            "engine_creation_time": str(row.get("EngineCreationTime") or ""),
            "event_record_id_lower_bound": int(row.get("EventRecordIdLowerBound") or 0),
            "activation_id": str(row.get("ActivationId") or ""),
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {"inspection_complete": False}


def _valid_task_scheduler_provider(value):
    if not isinstance(value, dict) or not value.get("inspection_complete"):
        return False
    required = ("pid", "creation_time", "service_name", "service_state",
                "start_name", "executable_path", "service_binary_path", "service_dll",
                "system_root", "engine_pid", "instance_guid", "task_path",
                "current_action", "action_execute", "action_working_directory")
    if int(value.get("pid") or 0) <= 0 or any(
            not str(value.get(field) or "") for field in required[1:]):
        return False
    binary_tokens = _command_tokens(value.get("service_binary_path"))
    expected_executable = Path(str(value["system_root"])) / "System32" / "svchost.exe"
    expected_dll = Path(str(value["system_root"])) / "System32" / "schedsvc.dll"
    evidence_source = str(value.get("evidence_source") or "running_instance")
    event_identity_valid = evidence_source == "running_instance" or bool(
        evidence_source == "operational_event"
        and int(value.get("event_record_id") or 0) > 0
        and str(value.get("event_time") or "")
        and str(value.get("engine_creation_time") or "")
        and int(value.get("event_record_id") or 0)
        > int(value.get("event_record_id_lower_bound") or -1)
        and str(value.get("event_activity_id") or "").strip("{}").casefold()
        == str(value.get("instance_guid") or "").strip("{}").casefold()
    )
    return bool(
        value.get("provider_identity_verified")
        and event_identity_valid
        and str(value["service_name"]).casefold() == "schedule"
        and str(value["service_state"]).casefold() == "running"
        and str(value["start_name"]).casefold() in {"localsystem", "local system"}
        and len(binary_tokens) >= 4
        and str(Path(binary_tokens[0])).casefold()
        == str(Path(str(value["executable_path"]))).casefold()
        and str(Path(binary_tokens[0])).casefold() == str(expected_executable).casefold()
        and binary_tokens[1:] == ["-k", "netsvcs", "-p"]
        and str(Path(str(value["service_dll"]))).casefold() == str(expected_dll).casefold()
        and int(value["engine_pid"]) > 0
        and re.fullmatch(r"\{?[0-9a-fA-F-]{36}\}?", str(value["instance_guid"]))
        and str(value["task_path"]).casefold() == ("\\" + TASK_NAME).casefold()
    )


def _windows_process_creation_time(pid):
    """Read one exact Windows PID's kernel creation timestamp without enumeration."""
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return ""
        try:
            created = wintypes.FILETIME()
            exited = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                    handle, ctypes.byref(created), ctypes.byref(exited),
                    ctypes.byref(kernel), ctypes.byref(user)):
                return ""
            return str((int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime))
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError, TypeError, ValueError):
        return ""


def _local_current_process_identity():
    """Read self identity without requiring WMI access to the scheduled child."""
    command_line = subprocess.list2cmdline([sys.executable, *sys.argv])
    creation_time = "local-current-process"
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetCommandLineW.restype = wintypes.LPWSTR
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            kernel32.GetProcessTimes.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
            ]
            kernel32.GetProcessTimes.restype = wintypes.BOOL
            command_line = str(kernel32.GetCommandLineW() or "")
            created = wintypes.FILETIME()
            exited = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                    kernel32.GetCurrentProcess(), ctypes.byref(created), ctypes.byref(exited),
                    ctypes.byref(kernel), ctypes.byref(user)):
                return {"inspection_complete": False}
            creation_time = str((int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime))
        except (AttributeError, OSError, ValueError):
            return {"inspection_complete": False}
    return {
        "inspection_complete": True,
        "pid": os.getpid(),
        "parent_pid": os.getppid(),
        "executable_path": sys.executable,
        "creation_time": creation_time,
        "command_line": command_line,
    }


TASK_SCHEDULER_OPERATIONAL_LOG = "Microsoft-Windows-TaskScheduler/Operational"


class WindowsExactTaskController:
    def __init__(self, task_reader=read_watchdog_task, runner=subprocess.run):
        self.task_reader, self.runner = task_reader, runner
        self.expected_task = None
        self.audit_prior = None
        self.audit_changed = False
        self.audit_mutation_attempted = False

    def bind_exact(self, rows):
        if not isinstance(rows, list) or len(rows) != 1:
            raise ActivationError("scheduled_task_ownership_ambiguous")
        self.expected_task = rows

    def read_audit_channel_state(self):
        script = (
            "$ErrorActionPreference='Stop';"
            f"$l=Get-WinEvent -ListLog '{TASK_SCHEDULER_OPERATIONAL_LOG}';"
            f"[pscustomobject]@{{log_name='{TASK_SCHEDULER_OPERATIONAL_LOG}';"
            "enabled=[bool]$l.IsEnabled}|ConvertTo-Json -Compress"
        )
        try:
            completed = self.runner(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=30, check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ActivationError("task_scheduler_audit_provider_error") from exc
        if completed.returncode:
            raise ActivationError("task_scheduler_audit_state_unreadable")
        try:
            value = json.loads(completed.stdout)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ActivationError("task_scheduler_audit_state_unreadable") from exc
        if (not isinstance(value, dict)
                or value.get("log_name") != TASK_SCHEDULER_OPERATIONAL_LOG
                or not isinstance(value.get("enabled"), bool)):
            raise ActivationError("task_scheduler_audit_state_invalid")
        return value

    def bind_audit_channel_state(self, value):
        if (not isinstance(value, dict)
                or value.get("log_name") != TASK_SCHEDULER_OPERATIONAL_LOG
                or not isinstance(value.get("enabled"), bool)):
            raise ActivationError("task_scheduler_audit_state_invalid")
        self.audit_prior = dict(value)

    def read_audit_event_record_id(self):
        script = (
            "$ErrorActionPreference='Stop';"
            f"$e=Get-WinEvent -FilterHashtable @{{LogName='{TASK_SCHEDULER_OPERATIONAL_LOG}'}} "
            "-MaxEvents 1 -ErrorAction SilentlyContinue;"
            "if($null-eq$e){'0'}else{[string][long]$e.RecordId}"
        )
        completed = self.runner(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=30, check=False,
        )
        try:
            value = int(str(completed.stdout or "0").strip())
        except ValueError as exc:
            raise ActivationError("task_scheduler_audit_record_id_unreadable") from exc
        if completed.returncode or value < 0:
            raise ActivationError("task_scheduler_audit_record_id_unreadable")
        return value

    def assert_no_running_instances(self):
        script = (
            "$ErrorActionPreference='Stop';"
            "$s=New-Object -ComObject 'Schedule.Service';$s.Connect();"
            f"$t=$s.GetFolder('\\').GetTask('{TASK_NAME}');"
            "[string]@($t.GetInstances(0)).Count"
        )
        completed = self.runner(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=30, check=False,
        )
        try:
            count = int(str(completed.stdout or "").strip())
        except ValueError as exc:
            raise ActivationError("task_scheduler_instance_state_unreadable") from exc
        if completed.returncode or count != 0:
            raise ActivationError("task_scheduler_instance_already_running")

    def ensure_audit_channel_enabled(self):
        if self.audit_prior is None:
            raise ActivationError("task_scheduler_audit_binding_missing")
        changed = self._set_audit_channel(
            True, expected_enabled=self.audit_prior["enabled"],
        )
        self.audit_changed = changed
        return changed

    def restore_audit_channel_state(self):
        if self.audit_prior is None:
            raise ActivationError("task_scheduler_audit_binding_missing")
        return self._set_audit_channel(
            self.audit_prior["enabled"], expected_enabled=True,
        )

    def reconcile_audit_channel_state(self):
        if self.audit_prior is None:
            raise ActivationError("task_scheduler_audit_binding_missing")
        current = self.read_audit_channel_state()
        if current["log_name"] != self.audit_prior["log_name"]:
            raise ActivationError("task_scheduler_audit_identity_changed")
        if current["enabled"] is self.audit_prior["enabled"]:
            return False
        if current["enabled"] is not True:
            raise ActivationError("task_scheduler_audit_state_ambiguous")
        return self._set_audit_channel(
            self.audit_prior["enabled"], expected_enabled=True,
        )

    def _set_audit_channel(self, enabled, *, expected_enabled):
        expected_before = self.read_audit_channel_state()
        if (self.audit_prior is None
                or expected_before["log_name"] != self.audit_prior["log_name"]
                or expected_before["enabled"] is not bool(expected_enabled)):
            raise ActivationError("task_scheduler_audit_identity_changed")
        if expected_before["enabled"] is bool(enabled):
            return False
        state = str(bool(enabled)).lower()
        self.audit_mutation_attempted = True
        try:
            completed = self.runner(
                # Once this command is issued, immediate cleanup may reconcile the
                # exact channel even if post-mutation readback fails.
                ["wevtutil", "sl", TASK_SCHEDULER_OPERATIONAL_LOG, f"/e:{state}"],
                capture_output=True, text=True, timeout=30, check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            if getattr(exc, "winerror", None) == 5:
                raise ActivationError("task_scheduler_audit_access_denied") from exc
            raise ActivationError("task_scheduler_audit_provider_error") from exc
        if completed.returncode:
            # Native Windows ERROR_ACCESS_DENIED is stable and does not depend on
            # the localized wevtutil message.  Keep privilege/configuration
            # failures distinct from provider/tool failures so recovery never
            # retries a mutation that the controller cannot authorize.
            native_code = int(completed.returncode) & 0xffffffff
            if native_code in {5, 0x80070005}:
                raise ActivationError("task_scheduler_audit_access_denied")
            raise ActivationError("task_scheduler_audit_provider_error")
        after = self.read_audit_channel_state()
        if after.get("enabled") is not bool(enabled):
            raise ActivationError("task_scheduler_audit_readback_mismatch")
        return True

    def enable_and_trigger_exact(self, digest):
        self._mutate(digest, "Enable-ScheduledTask -InputObject $t|Out-Null", {"Disabled"})
        if _task_action_sha256(self.task_reader()) != digest:
            self._mutate(digest, "Disable-ScheduledTask -InputObject $t|Out-Null", {"Ready", "Running", "Disabled"})
            raise ActivationError("scheduled_task_identity_changed_after_enable")
        return self._mutate(
            digest,
            "$s=New-Object -ComObject 'Schedule.Service';$s.Connect();"
            "$rt=$s.GetFolder($e.task_path).GetTask($e.task_name).RunEx($null,0,0,$null);"
            "$rt.Refresh();[string]$rt.InstanceGuid",
            {"Ready"},
        ).strip()

    def disable_exact(self, digest):
        self._mutate(digest, "Disable-ScheduledTask -InputObject $t|Out-Null", {"Ready", "Running", "Disabled"})

    def _mutate(self, digest, action, allowed_states):
        if _task_action_sha256(self.task_reader()) != digest:
            raise ActivationError("scheduled_task_identity_changed")
        if not self.expected_task:
            raise ActivationError("scheduled_task_binding_missing")
        encoded = base64.b64encode(_canonical(self.expected_task[0])).decode("ascii")
        states = ",".join(f"'{value}'" for value in sorted(allowed_states))
        script = (
            "$ErrorActionPreference='Stop';"
            f"$e=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{encoded}'))|ConvertFrom-Json;"
            "$ts=@(Get-ScheduledTask -TaskName $e.task_name -TaskPath $e.task_path);"
            "if($ts.Count-ne 1){throw 'task identity ambiguous'};$t=$ts[0];$a=@($t.Actions);"
            f"if(@({states})-notcontains[string]$t.State){{throw 'task state changed'}};"
            "if($a.Count-ne 1-or[string]$a[0].Execute-ne[string]$e.execute-or"
            "[string]$a[0].Arguments-ne[string]$e.arguments-or"
            "[string]$a[0].WorkingDirectory-ne[string]$e.working_directory){throw 'task action changed'};"
            + action
        )
        completed = self.runner(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                capture_output=True, text=True, timeout=30, check=False)
        if completed.returncode != 0:
            raise ActivationError("scheduled_task_provider_mutation_failed")
        return str(completed.stdout or "")


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
    task = task_reader()
    _validate_exact_task(task, Path(plan["runtime_root"]))
    if _task_action_sha256(task) != plan["task_action_sha256"]:
        raise ActivationError("scheduled_task_identity_changed")
    runtime = _worktree(Path(plan["runtime_root"]), git_runner)
    execution = _worktree(Path(plan["execution_root"]), git_runner)
    if runtime != plan["runtime"] or execution != plan["execution"]:
        raise ActivationError("activation_worktree_identity_changed")


def _validate_consumed_identity(packet, consumed, key, *, require_packet_hmac):
    expected = str(packet.get("expected_instance_guid") or "").strip("{}").casefold()
    consumed_expected = str(consumed.get("expected_instance_guid") or "").strip("{}").casefold()
    provider_instance = str(consumed.get("provider_instance_guid") or "").strip("{}").casefold()
    packet_hmac = (packet.get("packet_hmac_sha256") if require_packet_hmac
                   else packet.get("consumed_packet_hmac_sha256"))
    if (not hmac.compare_digest(
            str(consumed.get("consumed_hmac_sha256") or ""),
            _sign_record(consumed, key, "consumed_hmac_sha256"))
            or consumed.get("activation_id") != packet.get("activation_id")
            or not expected
            or consumed_expected != expected
            or provider_instance != expected
            or consumed.get("packet_hmac_sha256") != packet_hmac):
        raise ActivationError("activation_consumed_identity_invalid")


def _validate_packet(packet, state_root, task_reader, git_runner=subprocess.run,
                     now=None, allow_consumed=False, allow_expired=False):
    key = _read_key(state_root / "activation-authority.key")
    signature = packet.get("packet_hmac_sha256")
    if not hmac.compare_digest(str(signature or ""), _sign_packet(packet, key)):
        raise ActivationError("activation_packet_signature_invalid")
    authority = packet.get("authority") if isinstance(packet.get("authority"), dict) else {}
    if (packet.get("version") != ACTIVATION_VERSION
            or packet.get("activation_id") != authority.get("activation_id")
            or not str(packet.get("expected_instance_guid") or "").strip("{}")):
        raise ActivationError("activation_packet_binding_invalid")
    if packet.get("status") not in ({"provider_pending", "provider_started_observe_only"} if allow_consumed else {"provider_pending"}):
        raise ActivationError("activation_packet_replayed")
    consumed_name = f"activation-consumed-{packet['activation_id']}.json"
    consumed_live = state_root / consumed_name
    consumed_verified = (state_root / "activation-ledger"
                         / f"{packet['activation_id']}-verified-{consumed_name}")
    consumed_path = consumed_live if consumed_live.exists() else consumed_verified
    if packet.get("status") == "provider_pending" and consumed_path.exists() and not allow_consumed:
        raise ActivationError("activation_consumed_pending_recovery_required")
    if packet.get("status") == "provider_started_observe_only" or consumed_path.exists():
        consumed = _read_json(consumed_path, "activation_consumed_identity_missing")
        _validate_consumed_identity(
            packet, consumed, key,
            require_packet_hmac=packet.get("status") == "provider_pending",
        )
    _validate_authority(authority, key, now=now, allow_expired=allow_expired)
    if (_sha256(packet.get("authority_path")) != packet.get("authority_sha256")
            or Path(packet.get("runtime_root", "")).resolve() != state_root / "core-runtime-current"
            or Path(packet.get("execution_root", "")).resolve() != state_root / "core-execution-current"):
        raise ActivationError("activation_packet_authority_or_roots_invalid")
    if _read_json(packet.get("authority_path"), "activation_authority_invalid") != authority:
        raise ActivationError("activation_authority_content_mismatch")
    lane_path = state_root / "activation.lock"
    verified_lane = (state_root / "activation-ledger"
                     / f"{packet['activation_id']}-lane.json")
    lane_candidates = [path for path in (lane_path, verified_lane) if path.exists()]
    if len(lane_candidates) != 1:
        raise ActivationError("activation_lane_missing" if not lane_candidates
                              else "activation_lane_ambiguous")
    lane = _read_json(lane_candidates[0], "activation_lane_missing")
    if not hmac.compare_digest(
            str(lane.get("lane_hmac_sha256") or ""),
            _sign_record(lane, key, "lane_hmac_sha256")):
        raise ActivationError("activation_lane_signature_invalid")
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
            or rollback.get("task_action_sha256") != authority.get("task_action_sha256")
            or rollback.get("task_scheduler_event_record_id_lower_bound")
            != packet.get("task_scheduler_event_record_id_lower_bound")):
        raise ActivationError("activation_rollback_binding_invalid")
    activation_id = packet["activation_id"]
    intent_name = f"activation-audit-intent-{activation_id}.json"
    receipt_name = f"activation-audit-receipt-{activation_id}.json"
    intent_live = state_root / intent_name
    receipt_live = state_root / receipt_name
    intent_verified = (state_root / "activation-ledger"
                       / f"{activation_id}-verified-{intent_name}")
    receipt_verified = (state_root / "activation-ledger"
                        / f"{activation_id}-verified-{receipt_name}")
    intent = _read_json(intent_live if intent_live.exists() else intent_verified,
                        "activation_audit_intent_missing")
    receipt = _read_json(receipt_live if receipt_live.exists() else receipt_verified,
                         "activation_audit_receipt_missing")
    prior = rollback.get("task_scheduler_audit_prior") or {}
    if (not hmac.compare_digest(
            str(intent.get("audit_intent_hmac_sha256") or ""),
            _sign_record(intent, key, "audit_intent_hmac_sha256"))
            or not hmac.compare_digest(
                str(receipt.get("audit_receipt_hmac_sha256") or ""),
                _sign_record(receipt, key, "audit_receipt_hmac_sha256"))
            or intent.get("activation_id") != activation_id
            or receipt.get("activation_id") != activation_id
            or intent.get("prior_enabled") is not prior.get("enabled")
            or receipt.get("current_enabled") is not True
            or receipt.get("event_record_id_lower_bound")
            != packet.get("task_scheduler_event_record_id_lower_bound")):
        raise ActivationError("activation_audit_transaction_invalid")
    manifest_path = state_root / "runtime-manifest.json"
    if _sha256(manifest_path) != authority["manifest_sha256"]:
        raise ActivationError("activation_manifest_sha256_mismatch")
    if _sha256(authority["receipt_path"]) != authority["receipt_sha256"]:
        raise ActivationError("activation_receipt_sha256_mismatch")
    if _task_action_sha256(task_reader()) != authority["task_action_sha256"]:
        raise ActivationError("activation_task_action_sha256_mismatch")
    live_stop_archive = state_root / f"supervisor.stop.activation-{packet['activation_id']}"
    verified_stop_archive = (state_root / "activation-ledger"
                             / f"{packet['activation_id']}-verified-{live_stop_archive.name}")
    if _sha256(live_stop_archive if live_stop_archive.exists() else verified_stop_archive) != authority["stop_marker_sha256"]:
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


def _close_prepare_failure(state_root, plan, controller, archive, stop,
                           lane_path, rollback_path, packet_path):
    errors = []
    if archive.exists():
        try:
            if hasattr(controller, "bind_exact"):
                controller.bind_exact(plan["task_ownership"])
            controller.disable_exact(plan["task_action_sha256"])
        except Exception as exc:
            errors.append({"component": "scheduled_task", "status": getattr(exc, "status", exc.__class__.__name__)})
    _read_json(rollback_path, "activation_rollback_missing")
    try:
        if stop.exists() and _sha256(stop) != plan["stop_marker_sha256"]:
            raise ActivationError("governed_stop_conflict_during_prepare_recovery")
        if not stop.exists():
            rollback = _read_json(rollback_path, "activation_rollback_missing")
            expected = base64.b64decode(rollback["stop_marker_bytes_b64"], validate=True)
            if hashlib.sha256(expected).hexdigest() != plan["stop_marker_sha256"]:
                raise ActivationError("governed_stop_rollback_identity_invalid")
            _atomic_bytes(stop, expected)
        if _sha256(stop) != plan["stop_marker_sha256"]:
            raise ActivationError("governed_stop_restore_failed")
    except Exception as exc:
        errors.append({"component": "governed_stop", "status": getattr(exc, "status", exc.__class__.__name__)})
    if errors:
        raise ActivationError("activation_prepare_recovery_incomplete", errors=errors)
    ledger = Path(state_root) / "activation-ledger"
    activation_id = plan["activation_id"]
    if packet_path.exists():
        _durable_replace(packet_path, ledger / f"{activation_id}-prepare-failed-packet.json")
    if rollback_path.exists():
        _durable_replace(rollback_path, ledger / f"{activation_id}-prepare-failed-rollback.json")
    if lane_path.exists():
        _durable_replace(lane_path, ledger / f"{activation_id}-prepare-failed-lane.json")


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
        Path(state_root) / f"activation-audit-intent-{activation_id}.json",
        Path(state_root) / f"activation-audit-receipt-{activation_id}.json",
        Path(state_root) / f"supervisor.stop.activation-{activation_id}",
    ):
        if path.exists():
            _durable_replace(path, ledger / f"{activation_id}-{suffix}-{path.name}")


def _parse_time(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        raise ActivationError("activation_expiry_invalid") from exc


def _exclusive_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(json.dumps(value, indent=2).encode())
            stream.flush()
            os.fsync(stream.fileno())
        try:
            if os.name == "nt":
                _windows_move_write_through(temporary, path, replace_existing=False)
            else:
                os.link(temporary, path)
                _fsync_directory(path.parent)
        except FileExistsError as exc:
            raise ActivationError("activation_lane_already_owned") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _atomic_json(path, value):
    _atomic_bytes(path, json.dumps(value, indent=2).encode())


def _atomic_bytes(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("wb") as stream:
        stream.write(value); stream.flush(); os.fsync(stream.fileno())
    _durable_replace(temporary, path, replace_existing=True)


def _windows_move_write_through(source, target, *, replace_existing):
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.MoveFileExW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    kernel32.MoveFileExW.restype = ctypes.c_int
    flags = 0x8 | (0x1 if replace_existing else 0)
    if not kernel32.MoveFileExW(str(source), str(target), flags):
        error = ctypes.get_last_error()
        if not replace_existing and error in {80, 183}:
            raise FileExistsError(str(target))
        raise OSError(error, "MoveFileExW failed", str(source), str(target))


def _fsync_directory(path):
    if os.name == "nt":
        return
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _durable_replace(source, target, *, replace_existing=False):
    source, target = Path(source), Path(target)
    source_parent = source.parent
    target.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        _windows_move_write_through(source, target,
                                    replace_existing=replace_existing)
    else:
        if replace_existing:
            os.replace(source, target)
        else:
            libc = ctypes.CDLL(None, use_errno=True)
            renameat2 = getattr(libc, "renameat2", None)
            if renameat2 is None:
                raise OSError("atomic no-replace rename unavailable")
            renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p,
                                  ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            renameat2.restype = ctypes.c_int
            if renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1) != 0:
                error = ctypes.get_errno()
                if error == 17:
                    raise FileExistsError(str(target))
                raise OSError(error, "renameat2 failed", str(source), str(target))
        _fsync_directory(target.parent)
        if source_parent.resolve() != target.parent.resolve():
            _fsync_directory(source_parent)


def _now(value=None):
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
