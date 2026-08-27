"""Trusted runtime delivery for an already-issued Mission Admission Receipt."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path

from modules.charlie.mission_admission import (
    MissionAdmissionError,
    validate_mission_admission_receipt,
)
from modules.charlie.mission_store import read_current_mission_admission_authority


RUNTIME_STATE_ENV = "CHARLIE_MISSION_ADMISSION_STATE_ROOT"
RUNTIME_MISSION_ENV = "CHARLIE_MISSION_ADMISSION_MISSION_ID"
RUNTIME_GUARD_URL_ENV = "CHARLIE_MISSION_ADMISSION_GUARD_URL"
RUNTIME_CAPABILITY_ENV = "CHARLIE_MISSION_ADMISSION_CAPABILITY"


def provision_mission_admission_runtime(
    mission_id,
    receipt,
    signing_key,
    state_root,
    *,
    database_url=None,
    connect_factory=None,
):
    """Validate canonical authority, then atomically stage key and receipt.

    The returned launch contract contains identities and a path only. Secret
    bytes never enter the agent prompt, command line, environment, or ledger.
    """

    mission_id = str(mission_id or "").strip()
    if not mission_id or not isinstance(receipt, dict):
        raise MissionAdmissionError("admission_delivery_invalid")
    key = bytes(signing_key or b"")
    if len(key) < 32:
        raise MissionAdmissionError("admission_validation_authority_invalid")
    authority, status = read_current_mission_admission_authority(
        mission_id,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status >= 400 or not authority.get("success"):
        raise MissionAdmissionError("canonical_admission_authority_unavailable")
    current = authority.get("admission") if isinstance(authority.get("admission"), dict) else {}
    if current.get("status") != "valid":
        raise MissionAdmissionError("canonical_admission_not_active")
    key_sha256 = hashlib.sha256(key).hexdigest()
    identity = validate_mission_admission_receipt(
        receipt,
        key,
        expected_mission_id=mission_id,
        expected_root_mission_id=str(authority.get("root_mission_id") or ""),
        expected_generation=str(current.get("generation") or ""),
        expected_authority_key_sha256=key_sha256,
    )
    if (
        current.get("receipt_id") != identity.get("receipt_id")
        or current.get("content_sha256") != identity.get("content_sha256")
        or current.get("authority_key_sha256") != key_sha256
        or authority.get("latest_correction_digest")
        != receipt.get("owner_instruction_chain", {}).get("latest_correction_digest")
        or authority.get("collision_snapshot_sha256")
        != receipt.get("collision_snapshot", {}).get("snapshot_sha256")
    ):
        raise MissionAdmissionError("canonical_admission_authority_changed")

    root = _safe_state_root(state_root)
    receipt_bytes = json.dumps(
        receipt, sort_keys=True, separators=(",", ":")
    ).encode("utf-8") + b"\n"
    _stage_directory_atomically(root, identity["receipt_id"], key, receipt_bytes)
    receipt_dir = root / "mission-admission-receipts"
    key_path = root / "validation-receipt.key"
    receipt_path = receipt_dir / f"{identity['receipt_id']}.json"
    if os.name != "nt":
        root.chmod(0o700)
        receipt_dir.chmod(0o700)
        key_path.chmod(0o600)
        receipt_path.chmod(0o600)
    return {
        "validated": True,
        "state_root": str(root),
        "mission_id": mission_id,
        "root_mission_id": identity["root_mission_id"],
        "generation": identity["generation"],
        "receipt_id": identity["receipt_id"],
        "content_sha256": identity["content_sha256"],
        "authority_key_sha256": key_sha256,
    }


def provision_from_canonical_runner_state(
    mission_id,
    source_state_root,
    target_parent,
    *,
    database_url=None,
    connect_factory=None,
):
    """Production supplier: load the canonical receipt identity, then stage it."""

    authority, status = read_current_mission_admission_authority(
        mission_id,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    current = authority.get("admission") if isinstance(authority.get("admission"), dict) else {}
    if status >= 400 or current.get("status") != "valid":
        raise MissionAdmissionError("canonical_admission_not_active")
    source = _safe_state_root(source_state_root)
    receipt_id = str(current.get("receipt_id") or "")
    try:
        key = (source / "validation-receipt.key").read_bytes()
        receipt = json.loads(
            (source / "mission-admission-receipts" / f"{receipt_id}.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError) as exc:
        raise MissionAdmissionError("trusted_validation_authority_unavailable") from exc
    return provision_mission_admission_runtime(
        mission_id,
        receipt,
        key,
        Path(target_parent).absolute() / receipt_id,
        database_url=database_url,
        connect_factory=connect_factory,
    )


def admitted_agent_environment(runtime, environ=None):
    """Return the secret-stripped child environment with one staged-root hint."""

    from modules.charlie.secret_redaction import restricted_agent_environment

    runtime = runtime if isinstance(runtime, dict) else {}
    if (
        runtime.get("validated") is not True
        or not runtime.get("state_root")
        or not runtime.get("mission_id")
    ):
        raise MissionAdmissionError("admission_delivery_not_validated")
    environment = restricted_agent_environment(environ)
    environment[RUNTIME_STATE_ENV] = str(Path(runtime["state_root"]).resolve())
    environment[RUNTIME_MISSION_ENV] = str(runtime.get("mission_id") or "")
    if runtime.get("guard_url") and runtime.get("capability"):
        environment[RUNTIME_GUARD_URL_ENV] = str(runtime["guard_url"])
        environment[RUNTIME_CAPABILITY_ENV] = str(runtime["capability"])
    return environment


def start_admission_guard_server(runtime, *, repo_root, database_url=None, connect_factory=None):
    """Start a loopback-only validator that retains canonical DB authority."""

    runtime = runtime if isinstance(runtime, dict) else {}
    capability = secrets.token_urlsafe(32)
    server_environ = {
        RUNTIME_STATE_ENV: str(runtime.get("state_root") or ""),
        RUNTIME_MISSION_ENV: str(runtime.get("mission_id") or ""),
    }
    from modules.charlie.mission_store import read_current_mission_admission_authority
    from scripts.charlie_mission_admission_guard import hook_main

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.headers.get("Authorization") != f"Charlie {capability}":
                self.send_error(403)
                return
            try:
                length = min(int(self.headers.get("Content-Length") or 0), 131072)
                packet = json.loads(self.rfile.read(length))
                output = StringIO()
                with redirect_stdout(output):
                    hook_main(
                        stdin=StringIO(json.dumps(packet)),
                        environ=server_environ,
                        authority_reader=lambda mission_id: read_current_mission_admission_authority(
                            mission_id,
                            database_url=database_url,
                            connect_factory=connect_factory,
                        ),
                        repo_root=repo_root,
                    )
                body = output.getvalue().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                self.send_error(503)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    launch = dict(runtime)
    launch.update({
        "guard_url": f"http://127.0.0.1:{server.server_port}/authorize",
        "capability": capability,
    })
    return server, thread, launch


def stop_admission_guard_server(server, thread):
    if server is not None:
        server.shutdown()
        server.server_close()
    if thread is not None:
        thread.join(timeout=5)


def _write_once(path, content):
    path = Path(path)
    if path.is_symlink():
        raise MissionAdmissionError("admission_delivery_symlink_denied")
    if path.exists():
        if path.read_bytes() != content:
            raise MissionAdmissionError("admission_delivery_replay_conflict")
        return
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _safe_state_root(value):
    raw = Path(value).expanduser().absolute()
    for candidate in (raw, *raw.parents):
        if candidate.exists() and candidate.is_symlink():
            raise MissionAdmissionError("admission_delivery_symlink_denied")
    return raw


def _stage_directory_atomically(root, receipt_id, key, receipt_bytes):
    if root.exists():
        key_path = root / "validation-receipt.key"
        receipt_path = root / "mission-admission-receipts" / f"{receipt_id}.json"
        if key_path.is_file() and receipt_path.is_file():
            if key_path.read_bytes() == key and receipt_path.read_bytes() == receipt_bytes:
                return
        raise MissionAdmissionError("admission_delivery_replay_conflict")
    parent = root.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = parent / f".{root.name}.stage-{secrets.token_hex(12)}"
    try:
        (temporary / "mission-admission-receipts").mkdir(parents=True)
        _write_once(temporary / "validation-receipt.key", key)
        _write_once(
            temporary / "mission-admission-receipts" / f"{receipt_id}.json",
            receipt_bytes,
        )
        os.replace(temporary, root)
    except Exception:
        if temporary.exists():
            import shutil
            shutil.rmtree(temporary, ignore_errors=True)
        raise
