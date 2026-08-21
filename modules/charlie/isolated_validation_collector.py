"""Collect CORE validation evidence from a constrained Docker provider boundary."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from modules.charlie.validation_receipt import VALIDATION_COMMANDS, ValidationReceiptError


_IMAGE = re.compile(r"sha256:([0-9a-f]{64})$")
_CONTAINER = re.compile(r"[0-9a-f]{64}")
_RAN = re.compile(r"Ran (\d+) tests?")
_SKIPPED = re.compile(r"skipped=(\d+)")


def collect_docker_validation_evidence(source_root, source_commit, image, *, runner=None):
    """Run the fixed suites in Docker and attest the inspected provider controls."""
    source_root = Path(source_root).resolve()
    if not source_root.is_dir() or not re.fullmatch(r"[0-9a-f]{40}", source_commit or ""):
        raise ValidationReceiptError("validation_collector_source_invalid")
    run = runner or _run
    requested = re.fullmatch(r".+@sha256:([0-9a-f]{64})", str(image or ""))
    if requested is None:
        raise ValidationReceiptError("validation_provider_digest_reference_required")
    image_row = _json(run(["docker", "image", "inspect", image]))
    if not isinstance(image_row, list) or len(image_row) != 1:
        raise ValidationReceiptError("validation_provider_image_invalid")
    match = _IMAGE.fullmatch(str(image_row[0].get("Id") or ""))
    if not match:
        raise ValidationReceiptError("validation_provider_image_invalid")
    image_sha256 = match.group(1)
    if image not in (image_row[0].get("RepoDigests") or []):
        raise ValidationReceiptError("validation_provider_image_mismatch")
    rows, container_ids = [], []
    for name in ("focused", "proportional"):
        command = VALIDATION_COMMANDS[name]
        provider_command = (
            f'test "$(git rev-parse HEAD)" = "{source_commit}" && '
            'test -z "$(git status --porcelain)" && exec ' + command
        )
        create = [
            "docker", "create", "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", "65532:65532",
            "--pids-limit", "256", "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--mount", f"type=bind,src={source_root},dst=/source,readonly",
            "--workdir", "/source", image, "sh", "-lc", provider_command,
        ]
        container_id = str(run(create)).strip().lower()
        if not _CONTAINER.fullmatch(container_id):
            raise ValidationReceiptError("validation_provider_execution_invalid")
        container_ids.append(container_id)
        try:
            inspected = _json(run(["docker", "inspect", container_id]))
            _verify_container(inspected, source_root, image_sha256, provider_command)
            completed = run(["docker", "start", "--attach", container_id], allow_failure=True)
            rows.append(_suite_row(name, command, completed))
        finally:
            run(["docker", "rm", "--force", container_id], allow_failure=True)
    provider_config = {
        "provider": "docker_engine", "network": "none", "rootfs_read_only": True,
        "source_read_only": True, "cap_drop": ["ALL"], "no_new_privileges": True,
        "user": "65532:65532", "pid_mode": "private", "pids_limit": 256,
    }
    return {
        "source_commit": source_commit,
        "suites": rows,
        "isolation": {
            "boundary": "disposable_process_boundary", "host_processes_visible": False,
            "outside_boundary_targets": 0, "network_enabled": False,
            "source_read_only": True, "capabilities_dropped": True,
            "unprivileged": True, "image_sha256": image_sha256,
            "provider": "docker_engine",
            "provider_actor": "control_tower_isolated_validator_v2",
            "provider_execution_id": _digest(container_ids),
            "provider_execution_ids": container_ids,
            "provider_config_sha256": _digest(provider_config),
        },
    }


def _verify_container(value, source_root, image_sha256, command):
    if not isinstance(value, list) or len(value) != 1:
        raise ValidationReceiptError("validation_provider_attestation_invalid")
    row = value[0]
    host, config = row.get("HostConfig") or {}, row.get("Config") or {}
    mounts = row.get("Mounts") or []
    source_mount = [item for item in mounts if item.get("Destination") == "/source"]
    security = [str(item).lower() for item in host.get("SecurityOpt") or []]
    expected = (
        str(row.get("Image") or "").lower() == f"sha256:{image_sha256}"
        and host.get("NetworkMode") == "none" and host.get("ReadonlyRootfs") is True
        and [str(x).upper() for x in host.get("CapDrop") or []] == ["ALL"]
        and any("no-new-privileges" in item for item in security)
        and not host.get("PidMode") and host.get("PidsLimit") == 256
        and config.get("User") == "65532:65532" and config.get("WorkingDir") == "/source"
        and config.get("Entrypoint") in (None, [])
        and config.get("Cmd") == ["sh", "-lc", command]
        and len(source_mount) == 1 and source_mount[0].get("RW") is False
        and Path(source_mount[0].get("Source") or "").resolve() == source_root
    )
    if not expected:
        raise ValidationReceiptError("validation_provider_attestation_invalid")


def _suite_row(name, command, completed):
    output, returncode = completed if isinstance(completed, tuple) else (str(completed), 0)
    ran = _RAN.search(output)
    if ran is None:
        raise ValidationReceiptError("validation_provider_result_invalid")
    total = int(ran.group(1))
    skipped_match = _SKIPPED.search(output)
    skipped = int(skipped_match.group(1)) if skipped_match else 0
    failure_counts = [int(value) for value in re.findall(r"(?:failures|errors)=(\d+)", output)]
    failed = 0 if returncode == 0 else max(1, sum(failure_counts))
    return {"name": name, "command_sha256": hashlib.sha256(command.encode()).hexdigest(),
            "passed": max(0, total - skipped - failed),
            "failed": failed, "skipped": skipped}


def _json(value):
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValidationReceiptError("validation_provider_attestation_invalid") from exc


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _run(command, allow_failure=False):
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode and not allow_failure:
        raise ValidationReceiptError("validation_provider_command_failed")
    return (output, completed.returncode) if allow_failure else output
