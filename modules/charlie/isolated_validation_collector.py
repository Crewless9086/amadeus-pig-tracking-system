"""Collect CORE validation evidence from a constrained Docker provider boundary."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from modules.charlie.validation_receipt import (
    VALIDATION_COMMANDS, ValidationReceiptError, git_validation_environment,
)


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
    binding = _source_binding(source_root, source_commit, run)
    image_row = _json(run(["docker", "image", "inspect", image]))
    if not isinstance(image_row, list) or len(image_row) != 1:
        raise ValidationReceiptError("validation_provider_image_invalid")
    match = _IMAGE.fullmatch(str(image_row[0].get("Id") or ""))
    if not match:
        raise ValidationReceiptError("validation_provider_image_invalid")
    image_manifest_sha256 = requested.group(1)
    image_config_sha256 = match.group(1)
    if image not in (image_row[0].get("RepoDigests") or []):
        raise ValidationReceiptError("validation_provider_image_mismatch")
    image_environment = _environment((image_row[0].get("Config") or {}).get("Env") or [])
    if any(key.startswith("GIT_") for key in image_environment):
        raise ValidationReceiptError("validation_provider_image_environment_invalid")
    environment = {**image_environment, **binding["environment"]}
    git_binding = {"version": "charlie_linked_git_binding_v1", "mounts": binding["mounts"],
        "environment": environment, "git_file_sha256": binding["git_file_sha256"]}
    rows, container_ids = [], []
    for name in ("focused", "proportional"):
        command = VALIDATION_COMMANDS[name]
        provider_command = (
            f'source_head=$(git rev-parse HEAD) && test "$source_head" = "{source_commit}" && '
            'source_status=$(git status --porcelain --untracked-files=all) && '
            'test -z "$source_status" && exec ' + command
        )
        create = [
            "docker", "create", "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", "65532:65532",
            "--pids-limit", "256", "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        ]
        for mount in binding["mounts"]:
            create += ["--mount", f'type=bind,src={mount["source"]},dst={mount["destination"]},readonly']
        for key, value in binding["environment"].items():
            create += ["--env", key + "=" + value]
        create += ["--workdir", "/source", image, "sh", "-lc", provider_command]
        container_id = str(run(create)).strip().lower()
        if not _CONTAINER.fullmatch(container_id):
            raise ValidationReceiptError("validation_provider_execution_invalid")
        container_ids.append(container_id)
        try:
            inspected = _json(run(["docker", "inspect", container_id]))
            _verify_container(inspected, binding, image_config_sha256, provider_command, environment)
            completed = run(["docker", "start", "--attach", container_id], allow_failure=True)
            rows.append(_suite_row(name, command, completed))
        finally:
            run(["docker", "rm", "--force", container_id], allow_failure=True)
    provider_config = {
        "provider": "docker_engine", "network": "none", "rootfs_read_only": True,
        "source_read_only": True, "cap_drop": ["ALL"], "no_new_privileges": True,
        "user": "65532:65532", "pid_mode": "private", "pids_limit": 256,
        "image_manifest_sha256": image_manifest_sha256,
        "image_config_sha256": image_config_sha256,
        "git_binding": git_binding,
    }
    return {
        "source_commit": source_commit,
        "suites": rows,
        "isolation": {
            "boundary": "disposable_process_boundary", "host_processes_visible": False,
            "outside_boundary_targets": 0, "network_enabled": False,
            "source_read_only": True, "capabilities_dropped": True,
            "unprivileged": True,
            "image_manifest_sha256": image_manifest_sha256,
            "image_config_sha256": image_config_sha256,
            "provider": "docker_engine",
            "provider_actor": "control_tower_isolated_validator_v2",
            "provider_execution_id": _digest(container_ids),
            "provider_execution_ids": container_ids,
            "provider_config_sha256": _digest(provider_config),
            "git_binding": git_binding,
        },
    }


def _source_binding(source_root, source_commit, run):
    # Linked-only: embedding .git would expose host config through /source.
    marker = source_root / ".git"
    if not marker.is_file() or marker.is_symlink():
        raise ValidationReceiptError("validation_collector_linked_checkout_required")
    # Resolve the selected checkout, never the coordinator's current branch.
    git = ["git", "-c", "safe.directory=" + str(source_root), "-c", "core.fsmonitor=false",
           "-C", str(source_root)]
    paths = str(run(git + ["rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir"])).splitlines()
    if len(paths) != 2 or any(not Path(value).is_absolute() for value in paths):
        raise ValidationReceiptError("validation_collector_git_identity_invalid")
    private, common = (Path(value).resolve() for value in paths)
    if (not private.is_dir() or not common.is_dir()
            or private == common or private.parent != common / "worktrees"
            or common == source_root or source_root in common.parents
            or str(run(git + ["rev-parse", "HEAD"])).strip() != source_commit
            or str(run(git + ["status", "--porcelain", "--untracked-files=all"])).strip()):
        raise ValidationReceiptError("validation_collector_source_not_exact_clean")
    # The files ref backend reads commondir itself, independently of GIT_COMMON_DIR.
    # Preserve the existing relative layout; never synthesize or rewrite Git metadata.
    common_marker = private / "commondir"
    if (not common_marker.is_file() or common_marker.is_symlink()
            or common_marker.read_bytes() not in (b"../..", b"../..\n", b"../..\r\n")):
        raise ValidationReceiptError("validation_collector_git_commondir_invalid")
    # Do not expose host Git configuration, hooks, logs, sibling worktree state,
    # credentials, or external object stores. Git gets an explicit native view.
    if any(path.exists() for path in (common / "objects/info/alternates",
            common / "info/grafts", common / "reftable")):
        raise ValidationReceiptError("validation_collector_git_layout_unsupported")
    if any(ch in str(source_root) for ch in (",", "\n", "\r")):
        raise ValidationReceiptError("validation_collector_git_path_invalid")
    mounts = [{"source": str(source_root), "destination": "/source", "read_only": True}]
    files = {}
    def mount(path, destination, *, directory=False):
        if (path.is_symlink() or path.resolve() != path
                or not (path.is_dir() if directory else path.is_file())
                or any(ch in str(path) for ch in (",", "\n", "\r"))):
            raise ValidationReceiptError("validation_collector_git_path_invalid")
        mounts.append({"source": str(path), "destination": destination, "read_only": True})
        if not directory:
            files[destination] = hashlib.sha256(path.read_bytes()).hexdigest()
    mount(common / "objects", "/git-common/objects", directory=True)
    mount(common / "refs", "/git-common/refs", directory=True)
    mount(private / "HEAD", "/git-common/worktrees/selected/HEAD")
    mount(private / "index", "/git-common/worktrees/selected/index")
    mount(common_marker, "/git-common/worktrees/selected/commondir")
    for name in ("packed-refs", "shallow"):
        if (common / name).exists():
            mount(common / name, "/git-common/" + name)
    for path in sorted(private.glob("sharedindex.*")):
        if not re.fullmatch(r"sharedindex\.[0-9a-f]{40}", path.name):
            raise ValidationReceiptError("validation_collector_git_layout_unsupported")
        mount(path, "/git-common/worktrees/selected/" + path.name)
    settings = {}
    for name, default, choices in (("core.autocrlf", "false", {"true", "false", "input"}),
                                   ("core.filemode", "true", {"true", "false"})):
        output, code = run(git + ["config", "--get", name], allow_failure=True)
        value = str(output).strip().lower() if code == 0 else default
        if code not in (0, 1) or value not in choices:
            raise ValidationReceiptError("validation_collector_git_setting_invalid")
        settings[name] = value
    environment = git_validation_environment(settings["core.autocrlf"], settings["core.filemode"])
    return {"mounts": mounts, "environment": environment, "git_file_sha256": files}


def _environment(values):
    result = {}
    for value in values:
        if not isinstance(value, str) or "=" not in value:
            raise ValidationReceiptError("validation_provider_environment_invalid")
        key, value = value.split("=", 1)
        if not key or key in result:
            raise ValidationReceiptError("validation_provider_environment_invalid")
        result[key] = value
    return result


def _mount_source_identity(value):
    # Docker Desktop may report the Linux bridge path for an exact Windows bind.
    text = str(value).replace("\\", "/")
    if any(part in (".", "..") for part in text.split("/")):
        return None
    mapped = re.fullmatch(r"/(?:run/desktop/mnt/host|host_mnt)/([A-Za-z])/(.+)", text)
    if mapped:
        text = mapped.group(1) + ":/" + mapped.group(2)
    if re.match(r"^[A-Za-z]:/", text):
        return ("windows", text.rstrip("/").casefold())
    if text.startswith("/"):
        return ("posix", text.rstrip("/"))
    return None


def _verify_container(value, binding, image_sha256, command, environment):
    if not isinstance(value, list) or len(value) != 1:
        raise ValidationReceiptError("validation_provider_attestation_invalid")
    row = value[0]
    host, config = row.get("HostConfig") or {}, row.get("Config") or {}
    mounts = row.get("Mounts") or []
    expected_mounts = {m["destination"]: _mount_source_identity(m["source"]) for m in binding["mounts"]}
    actual = {}
    for item in mounts:
        destination = item.get("Destination")
        if destination in actual:
            raise ValidationReceiptError("validation_provider_attestation_invalid")
        if destination == "/tmp" and item.get("Type") == "tmpfs" and item.get("RW") is True:
            actual[destination] = "tmpfs"
        elif item.get("Type") == "bind" and item.get("RW") is False:
            actual[destination] = _mount_source_identity(item.get("Source"))
        else:
            raise ValidationReceiptError("validation_provider_attestation_invalid")
    if "/tmp" in actual:
        actual.pop("/tmp")
    security = [str(item).lower() for item in host.get("SecurityOpt") or []]
    expected = (
        str(row.get("Image") or "").lower() == f"sha256:{image_sha256}"
        and host.get("NetworkMode") == "none" and host.get("ReadonlyRootfs") is True
        and [str(x).upper() for x in host.get("CapDrop") or []] == ["ALL"]
        and not host.get("CapAdd") and host.get("Privileged") is not True
        and security == ["no-new-privileges"]
        and not host.get("PidMode") and host.get("PidsLimit") == 256
        and host.get("Tmpfs") == {"/tmp": "rw,noexec,nosuid,size=64m"}
        and config.get("User") == "65532:65532" and config.get("WorkingDir") == "/source"
        and config.get("Entrypoint") in (None, [])
        and config.get("Cmd") == ["sh", "-lc", command]
        and _environment(config.get("Env") or []) == environment
        and actual == expected_mounts
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
    environment = None
    if command[0] == "git":
        environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
        environment.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1")
    completed = subprocess.run(command, text=True, capture_output=True, check=False, env=environment)
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode and not allow_failure:
        raise ValidationReceiptError("validation_provider_command_failed")
    return (output, completed.returncode) if allow_failure else output
