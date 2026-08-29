#!/usr/bin/env python3
"""Shared fail-closed Mission Admission Guard for Cursor hooks and CI."""

from __future__ import annotations

import argparse
import base64
import contextlib
import getpass
import hashlib
import json
import http.client
import os
import socket
import stat
import shlex
import subprocess
import sys
import tempfile
import time
from urllib import request as url_request
from urllib import error as url_error
from urllib import parse as url_parse
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.mission_admission import (  # noqa: E402
    MissionAdmissionError,
    canonical_candidate_diff,
    collision_snapshot_digest,
    sign_mission_admission_receipt,
    validate_mission_admission_receipt,
)
from modules.charlie.mission_admission import (  # noqa: E402
    RECEIPT_CLOCK_SKEW_SECONDS,
    _TOP_LEVEL_FIELDS,
    _parse_timestamp,
    _validate_body,
    _validate_lifetime,
)
from modules.charlie.validation_receipt import canonical_json  # noqa: E402
from modules.charlie.mission_store import (  # noqa: E402
    append_mission_admission_event,
    get_mission,
    list_missions,
    read_current_mission_admission_authority,
)


READ_ONLY_TOOLS = {
    "read",
    "readfile",
    "grep",
    "rg",
    "glob",
    "search",
    "websearch",
    "webfetch",
    "todos",
    "todowrite",
}
MUTATING_TOOL_EFFECTS = {
    "write": "repository_file_write",
    "delete": "repository_file_delete",
    "applypatch": "repository_file_write",
    "editnotebook": "repository_file_write",
}
READ_ONLY_COMMANDS = {
    "pwd",
    "ls",
    "rg",
    "wc",
    "sha256sum",
    "stat",
    "file",
    "which",
    "type",
}
READ_ONLY_GIT_SUBCOMMANDS = {
    "status",
    "diff",
    "show",
    "log",
    "rev-parse",
    "merge-base",
    "name-rev",
    "branch",
    "ls-files",
    "hash-object",
    "cat-file",
    "remote",
    "config",
}
DELEGATING_TOOLS = {"task", "subagent", "agent", "runagent"}
WINDOWS_INTERPRETERS = {
    "cmd", "powershell", "pwsh", "wscript", "cscript", "mshta",
}
INTERPRETERS = {
    "python", "python3", "py", "node", "ruby", "perl", "php",
    "bash", "sh", "zsh", "fish",
} | WINDOWS_INTERPRETERS
CURSOR_HOOK_AUDIENCE = "urn:amadeus:charlie:cursor-hook:v1"
CURSOR_HOOK_ENDPOINT = "https://amadeus-pig-tracking-system.onrender.com/api/charlie/cursor/hooks/authorize"
CURSOR_HOOK_OPERATION_SECONDS = 8.0
CURSOR_OIDC_CACHE_SCHEMA = "charlie_cursor_oidc_cache_v1"
PROTECTED_ADMISSION_ROUTE_PREFIX = "/api/charlie/hermes/missions/"
_CURSOR_OIDC_CACHE = {"token": "", "expires_at": 0, "audience": "", "socket_identity": ""}

EXTERNAL_ADMISSION_PUBLIC_KEY_B64 = "ZAY5VaAnbWY2hrgxXivez5eLaNX4RjiRxjqYmPkoG9o="
EXTERNAL_CANONICAL_BINDING_ENV = "CHARLIE_ADMISSION_CANONICAL_BINDING_B64"
ADMISSION_READ_DATABASE_ENV = "CHARLIE_ADMISSION_READ_DATABASE_URL"
EXTERNAL_COLLISION_MAX_AGE_SECONDS = 900

BOOTSTRAP_BASE_SHA = "087f315b15acd1e683eb4f9b3d0f7c57ceb5e65f"
BOOTSTRAP_MISSION_ID = "CMQ-20260813-05"
BOOTSTRAP_ROOT_MISSION_ID = "CMQ-20260813-05"
BOOTSTRAP_GENERATION = "mission-admission-guard-bootstrap-20260826"
BOOTSTRAP_OWNER_INSTRUCTION_SHA256 = "b9d959ee6f8ef1ff6f20e5d7aca6344b17106e9cb6e0723f95096590063a5ef5"
BOOTSTRAP_PACKET_SHA256 = "e1af16aca874ac24af53371a7bf7384c850d788c986f9c6bcbca45800cc21014"
BOOTSTRAP_ALLOWED_FILES = frozenset({
    ".cursor/hooks.json",
    ".github/workflows/charlie-core-tests.yml",
    "docs/09-vault-brain/00-governance/BRAIN_GUARD.md",
    "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md",
    "docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md",
    "docs/09-vault-brain/CHANGELOG.md",
    "modules/charlie/mission_admission.py",
    "modules/charlie/mission_store.py",
    "scripts/charlie_mission_admission_guard.py",
    "tests/fixtures/mission_admission/pr1306_scope_drift.json",
    "tests/test_charlie_mission_admission.py",
})
BOOTSTRAP_FORBIDDEN_EFFECTS = frozenset({
    "branch_protection_change",
    "customer_send",
    "deployment",
    "farm_write",
    "hardware_action",
    "merge",
    "payment",
    "production_mutation",
    "public_send",
    "secret_write",
})
BOOTSTRAP_REQUIRED_TESTS = frozenset({
    "python -m unittest tests.test_charlie_mission_admission -q",
    "python -m unittest tests.test_charlie_mission_store tests.test_charlie_validation_receipt tests.test_charlie_vault_retrieval tests.test_vault_alignment -q",
    "python -m unittest tests.test_charlie_mission_admission.MissionAdmissionPostgresTests -q",
    "python modules/charlie/vault_alignment.py",
    "git diff --check",
})
STAGE2_BASE_SHA = "7c603cfff58c984409e6b40100009166cc9c8062"
STAGE2_MISSION_ID = "CMQ-20260813-05-STAGE2-ADMISSION"
STAGE2_ROOT_MISSION_ID = "CMQ-20260813-05"
STAGE2_GENERATION = "7379c0b621b7e53aa03aa03e"
STAGE2_OWNER_INSTRUCTION_SHA256 = "4c8824fc68ed15522c6ca85b6bd4b8d85e8f31a76e1fe7f52d1f68d7042014e0"
STAGE2_PACKET_SHA256 = "7a5ae24b827e83d633317fa48bb1fd97b0e56b71910e27b68732f2a681c0d1c8"
STAGE2_ALLOWED_FILES = frozenset({
    ".github/workflows/charlie-core-tests.yml",
    "docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md",
    "docs/09-vault-brain/CHANGELOG.md",
    "modules/charlie/execution_bridge.py",
    "modules/charlie/mission_admission_delivery.py",
    "scripts/charlie_mission_admission_guard.py",
    "scripts/charlie_codex_execution_bridge.py",
    "scripts/charlie_mission_pickup.py",
    "tests/test_charlie_mission_admission_delivery.py",
    "tests/test_charlie_mission_admission.py",
})
STAGE2_REQUIRED_TESTS = frozenset({
    "python -m unittest tests.test_charlie_mission_admission_delivery -q",
    "python -m unittest tests.test_charlie_mission_admission -q",
    "python -m unittest tests.test_charlie_execution_bridge -q",
    "python -m modules.charlie.vault_alignment",
    "git diff --check",
})
BOOTSTRAP_GOVERNANCE_PATHS = tuple(sorted({
    "docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md",
    "docs/06-operations/CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md",
    "docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md",
    "docs/09-vault-brain/00-governance/BRAIN_GUARD.md",
    "docs/09-vault-brain/00-governance/CONTROL_TOWER_ASSESSMENT_AND_DISPATCH_PROTOCOL.md",
    "docs/09-vault-brain/00-governance/DOCUMENT_LIFECYCLE_AND_LEGACY_RETIREMENT_STANDARD.md",
    "docs/09-vault-brain/00-governance/SOURCE_OF_TRUTH_RULES.md",
    "docs/09-vault-brain/01-identity/CHARLIE_CORE.md",
    "docs/09-vault-brain/02-agents/AGENT_REGISTRY.md",
    "docs/09-vault-brain/02-agents/owner-command/CHARLIE.md",
    "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md",
    "docs/09-vault-brain/07-standards/DEPLOYMENT_STANDARD.md",
    "docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md",
    "docs/09-vault-brain/07-standards/TESTING_STANDARD.md",
    "docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md",
    "docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md",
}))


def main(argv=None):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)
    hook_parser = subparsers.add_parser("hook")
    hook_parser.add_argument("--audit", action="store_true")
    ci_parser = subparsers.add_parser("ci")
    ci_parser.add_argument("--base", required=True)
    ci_parser.add_argument("--head", required=True)
    external_parser = subparsers.add_parser("ci-external")
    external_parser.add_argument("--base", required=True)
    external_parser.add_argument("--head", required=True)
    external_parser.add_argument("--receipt", required=True)
    trusted_parser = subparsers.add_parser("trusted-check")
    trusted_parser.add_argument("--event", required=True)
    issuer_parser = subparsers.add_parser("issue-pr")
    issuer_parser.add_argument("--pull-request-number", required=True, type=int)
    issuer_parser.add_argument("--expected-head-sha", required=True)
    issuer_parser.add_argument("--event-output")
    issue_parser = subparsers.add_parser("issue-bootstrap")
    issue_parser.add_argument("--base", required=True)
    issue_parser.add_argument("--head", required=True)
    stage2_parser = subparsers.add_parser("issue-stage2")
    stage2_parser.add_argument("--base", required=True)
    stage2_parser.add_argument("--head", required=True)
    args = parser.parse_args(argv)
    if args.mode == "hook":
        return hook_main(audit=args.audit)
    if args.mode in {"issue-bootstrap", "issue-stage2"}:
        return issue_bootstrap_main(args)
    if args.mode == "ci-external":
        return ci_external_main(args)
    if args.mode == "trusted-check":
        return trusted_check_main(args)
    if args.mode == "issue-pr":
        return issue_pr_main(args)
    return ci_main(args)


def hook_main(
    *,
    audit=False,
    stdin=None,
    environ=None,
    authority_reader=None,
    repo_root=REPO_ROOT,
    os_name=None,
):
    environ = os.environ if environ is None else environ
    try:
        packet = json.load(stdin or sys.stdin)
        if not isinstance(packet, dict):
            raise MissionAdmissionError("hook_input_invalid")
        cloud_hook = _cursor_cloud_socket(environ)
        if environ.get("CHARLIE_MISSION_ADMISSION_GUARD_URL") and not cloud_hook:
            _emit(_remote_authorization(packet, environ))
            return 0
        event = str(packet.get("hook_event_name") or "")
        if cloud_hook and (audit or event == "afterFileEdit"):
            path = _tool_target_path(packet)
            if not path:
                raise MissionAdmissionError("after_file_edit_path_missing")
            _emit(_cursor_cloud_authorization({"action": "after_file_edit", "target_path": path}, environ))
            return 0
        if audit or event == "afterFileEdit":
            _audit_after_file_edit(
                packet,
                environ=environ,
                authority_reader=authority_reader,
                repo_root=repo_root,
                os_name=os_name,
            )
            _emit({})
            return 0
        if event == "beforeShellExecution":
            command = str(packet.get("command") or "")
            if _references_trusted_authority(command, environ):
                raise MissionAdmissionError("trusted_admission_read_denied")
            if _is_read_only_shell(command, os_name=os_name):
                if cloud_hook and not _cloud_read_only_shell_safe(command, os_name=os_name):
                    raise MissionAdmissionError("cloud_read_scope_denied")
                return _allow("read_only_shell")
            if cloud_hook:
                _emit(_cursor_cloud_authorization({"action": "shell_verify", "command": command}, environ))
                return 0
            raise MissionAdmissionError("stage1_shell_mutation_denied")
        if event == "preToolUse":
            tool_name = str(packet.get("tool_name") or "").strip()
            normalized = tool_name.lower()
            if normalized in READ_ONLY_TOOLS:
                if _references_trusted_authority(packet, environ):
                    raise MissionAdmissionError("trusted_admission_read_denied")
                if cloud_hook and normalized in {"read", "readfile"}:
                    if not _cloud_repository_read_path_safe(_tool_target_path(packet), repo_root):
                        raise MissionAdmissionError("cloud_read_scope_denied")
                elif cloud_hook and normalized in {"grep", "rg", "glob", "search"}:
                    raise MissionAdmissionError("cloud_read_scope_denied")
                return _allow("read_only_tool")
            if normalized == "shell":
                command = str((packet.get("tool_input") or {}).get("command") or "")
                if _references_trusted_authority(command, environ):
                    raise MissionAdmissionError("trusted_admission_read_denied")
                if cloud_hook:
                    return _allow("deferred_to_fail_closed_before_shell_execution")
                if _is_read_only_shell(command, os_name=os_name):
                    return _allow("read_only_shell")
                raise MissionAdmissionError("stage1_shell_mutation_denied")
            if normalized in DELEGATING_TOOLS:
                raise MissionAdmissionError("stage1_delegation_denied")
            if normalized.startswith("mcp:"):
                raise MissionAdmissionError("stage1_mcp_execution_denied")
            effect = MUTATING_TOOL_EFFECTS.get(normalized)
            if effect:
                if cloud_hook:
                    target = _tool_target_path(packet)
                    if not target:
                        raise MissionAdmissionError("mutation_target_path_required")
                    _emit(_cursor_cloud_authorization({"action": effect, "target_path": target}, environ))
                    return 0
                _require_admission(
                    packet,
                    effect,
                    environ=environ,
                    authority_reader=authority_reader,
                    repo_root=repo_root,
                    os_name=os_name,
                )
                return _allow("mission_admission_verified")
            raise MissionAdmissionError("unknown_tool_denied")
        raise MissionAdmissionError("unsupported_hook_event_denied")
    except (OSError, ValueError, json.JSONDecodeError, MissionAdmissionError) as exc:
        return _deny(_reason(exc))


def _cursor_cloud_socket(environ):
    if os.name == "nt":
        return ""
    configured = str(environ.get("CURSOR_AGENT_SOCKET") or "").strip()
    if configured:
        # Cursor documents this variable as the managed-VM socket contract.  Do
        # not silently fall back to the local MAR path merely because the socket
        # is momentarily absent while the VM finishes starting; the OIDC mint
        # will then fail closed with its specific bounded reason instead.
        return configured
    default = "/run/cursor/api.sock"
    return default if Path(default).exists() else ""


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path, timeout=3):
        super().__init__("cursor-agent", timeout=timeout)
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


def _cursor_cache_identity(environ):
    socket_path = os.path.normcase(os.path.abspath(_cursor_cloud_socket(environ)))
    if not socket_path:
        raise MissionAdmissionError("cursor_oidc_cache_unavailable")
    user = str(os.geteuid()) if hasattr(os, "geteuid") else getpass.getuser()
    digest = hashlib.sha256(
        f"{user}\0{socket_path}\0{CURSOR_HOOK_AUDIENCE}".encode("utf-8")
    ).hexdigest()
    return user, socket_path, digest


def _cursor_cache_paths(environ):
    user, socket_path, digest = _cursor_cache_identity(environ)
    runtime = str(environ.get("XDG_RUNTIME_DIR") or "").strip()
    if runtime and not Path(runtime).is_absolute():
        raise MissionAdmissionError("cursor_oidc_cache_unavailable")
    root = (Path(runtime) / "charlie-cursor-hook" if runtime
            else Path(tempfile.gettempdir()) / f"charlie-cursor-hook-{user}")
    root = root.resolve(strict=False)
    try:
        if root == REPO_ROOT.resolve() or root.is_relative_to(REPO_ROOT.resolve()):
            raise MissionAdmissionError("cursor_oidc_cache_unavailable")
    except AttributeError:  # pragma: no cover - Python < 3.9 compatibility
        if str(root).startswith(str(REPO_ROOT.resolve()) + os.sep):
            raise MissionAdmissionError("cursor_oidc_cache_unavailable")
    if root.exists() and root.is_symlink():
        raise MissionAdmissionError("cursor_oidc_cache_unavailable")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(root, 0o700)
        stat_result = root.stat()
        if stat_result.st_uid != os.geteuid() or stat_result.st_mode & 0o077:
            raise MissionAdmissionError("cursor_oidc_cache_unavailable")
    return root / f"token-{digest}.json", root / f"token-{digest}.lock", socket_path


def _safe_cache_read(path, socket_identity, *, observed):
    try:
        if path.is_symlink():
            raise MissionAdmissionError("cursor_oidc_cache_unavailable")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise MissionAdmissionError("cursor_oidc_cache_unavailable") from exc
    try:
        stat_result = os.fstat(descriptor)
        if not stat.S_ISREG(stat_result.st_mode):
            raise MissionAdmissionError("cursor_oidc_cache_unavailable")
        if os.name != "nt" and (stat_result.st_uid != os.geteuid() or stat_result.st_mode & 0o077):
            raise MissionAdmissionError("cursor_oidc_cache_unavailable")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=False) as handle:
            packet = json.loads(handle.read(32768))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    finally:
        os.close(descriptor)
    expected = {"schema", "token", "expires_at", "audience", "socket_identity"}
    if (not isinstance(packet, dict) or set(packet) != expected
            or packet.get("schema") != CURSOR_OIDC_CACHE_SCHEMA
            or packet.get("audience") != CURSOR_HOOK_AUDIENCE
            or packet.get("socket_identity") != socket_identity
            or not str(packet.get("token") or "")):
        return None
    try:
        expires_at = int(packet.get("expires_at") or 0)
    except (TypeError, ValueError):
        return None
    return packet if expires_at > observed + 30 else None


def _safe_cache_write(path, socket_identity, token, expires_at):
    if path.exists() and path.is_symlink():
        raise MissionAdmissionError("cursor_oidc_cache_unavailable")
    packet = {"schema": CURSOR_OIDC_CACHE_SCHEMA, "token": token,
              "expires_at": int(expires_at), "audience": CURSOR_HOOK_AUDIENCE,
              "socket_identity": socket_identity}
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as handle:
            json.dump(packet, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
    except Exception as exc:
        raise MissionAdmissionError("cursor_oidc_cache_unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


@contextlib.contextmanager
def _cursor_cache_lock(path, *, deadline, monotonic=time.monotonic, sleep=time.sleep):
    if path.exists() and path.is_symlink():
        raise MissionAdmissionError("cursor_oidc_cache_unavailable")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise MissionAdmissionError("cursor_oidc_cache_unavailable") from exc
    locked = False
    try:
        if os.name != "nt":
            os.fchmod(descriptor, 0o600)
            lock_stat = os.fstat(descriptor)
            if not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_uid != os.geteuid():
                raise MissionAdmissionError("cursor_oidc_cache_unavailable")
        if os.name == "nt":
            import msvcrt
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
            while monotonic() < deadline:
                try:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                    locked = True
                    break
                except OSError:
                    sleep(min(0.05, max(0.0, deadline - monotonic())))
        else:
            import fcntl
            while monotonic() < deadline:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                    break
                except BlockingIOError:
                    sleep(min(0.05, max(0.0, deadline - monotonic())))
        if not locked:
            raise MissionAdmissionError("cursor_oidc_cache_lock_timeout")
        yield
    finally:
        if locked:
            if os.name == "nt":
                import msvcrt
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _retry_after_seconds(response, remaining):
    try:
        value = float(str(response.getheader("Retry-After") or "0").strip())
    except (TypeError, ValueError):
        value = 0.0
    return min(max(0.0, value), max(0.0, remaining))


def _mint_cursor_oidc(environ, *, now=None, deadline=None, monotonic=time.monotonic,
                      sleep=time.sleep, connection_factory=None):
    observed = int(time.time() if now is None else now)
    deadline = float(deadline if deadline is not None else monotonic() + 4.0)
    connection_factory = connection_factory or _UnixHTTPConnection
    cache_path, lock_path, socket_identity = _cursor_cache_paths(environ)
    if (_CURSOR_OIDC_CACHE["token"]
            and _CURSOR_OIDC_CACHE.get("audience") == CURSOR_HOOK_AUDIENCE
            and _CURSOR_OIDC_CACHE.get("socket_identity") == socket_identity
            and observed < int(_CURSOR_OIDC_CACHE["expires_at"] or 0) - 30):
        return _CURSOR_OIDC_CACHE["token"]
    cached = _safe_cache_read(cache_path, socket_identity, observed=observed)
    if cached:
        _CURSOR_OIDC_CACHE.update({"token": cached["token"], "expires_at": cached["expires_at"],
                                   "audience": CURSOR_HOOK_AUDIENCE, "socket_identity": socket_identity})
        return cached["token"]
    body = json.dumps({"aud": CURSOR_HOOK_AUDIENCE}, separators=(",", ":")).encode()
    retryable_errors = (FileNotFoundError, ConnectionRefusedError, ConnectionResetError,
                        BrokenPipeError, TimeoutError, socket.timeout)
    with _cursor_cache_lock(lock_path, deadline=deadline, monotonic=monotonic, sleep=sleep):
        cached = _safe_cache_read(cache_path, socket_identity, observed=observed)
        if cached:
            _CURSOR_OIDC_CACHE.update({"token": cached["token"], "expires_at": cached["expires_at"],
                                       "audience": CURSOR_HOOK_AUDIENCE, "socket_identity": socket_identity})
            return cached["token"]
        attempt = 0
        while monotonic() < deadline and attempt < 4:
            attempt += 1
            remaining = max(0.0, deadline - monotonic())
            connection = connection_factory(socket_identity, timeout=max(0.1, min(1.0, remaining)))
            response = None
            try:
                connection.request("POST", "/v1/tokens/oidc", body=body,
                                   headers={"Content-Type": "application/json", "Content-Length": str(len(body))})
                response = connection.getresponse()
                status = int(response.status)
                raw = response.read(16384)
            except retryable_errors:
                status, raw = 0, b""
            except Exception as exc:
                raise MissionAdmissionError("cursor_oidc_unavailable") from exc
            finally:
                connection.close()
            if status == 200:
                try:
                    result = json.loads(raw)
                    token = str(result.get("token") or "")
                    expires_at = int(result.get("expires_at") or 0)
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise MissionAdmissionError("cursor_oidc_response_invalid") from exc
                if not token or expires_at <= observed + 30:
                    raise MissionAdmissionError("cursor_oidc_response_invalid")
                _safe_cache_write(cache_path, socket_identity, token, expires_at)
                _CURSOR_OIDC_CACHE.update({"token": token, "expires_at": expires_at,
                                           "audience": CURSOR_HOOK_AUDIENCE,
                                           "socket_identity": socket_identity})
                return token
            if status in {400, 403, 404, 405, 413, 415}:
                raise MissionAdmissionError("cursor_oidc_request_rejected")
            if status not in {0, 429, 500, 502, 503, 504}:
                raise MissionAdmissionError("cursor_oidc_unavailable")
            remaining = max(0.0, deadline - monotonic())
            delay = (_retry_after_seconds(response, remaining)
                     if response is not None and status in {429, 503}
                     else min(0.1 * attempt, remaining))
            if delay > 0:
                sleep(delay)
        raise MissionAdmissionError("cursor_oidc_unavailable")


def _cursor_cloud_authorization(payload, environ, *, opener=url_request.urlopen):
    deadline = time.monotonic() + CURSOR_HOOK_OPERATION_SECONDS
    payload = dict(payload or {})
    if payload.get("action") in {"repository_file_write", "repository_file_delete", "after_file_edit"}:
        payload["changed_files"] = _worktree_changed_files("HEAD")
    request = url_request.Request(
        CURSOR_HOOK_ENDPOINT, data=json.dumps(payload, separators=(",", ":")).encode(),
        headers={"Authorization": "Bearer " + _mint_cursor_oidc(environ, deadline=deadline),
                 "Content-Type": "application/json", "Accept": "application/json"}, method="POST")
    try:
        with opener(request, timeout=max(0.1, min(3.0, deadline - time.monotonic()))) as response:
            result = json.loads(response.read(32768))
    except url_error.HTTPError as exc:
        try:
            result = json.loads(exc.read(32768))
        except Exception:
            result = {"permission": "deny", "status": "cursor_hook_authorization_denied"}
    except Exception as exc:
        raise MissionAdmissionError("cursor_hook_authorization_unavailable") from exc
    if not isinstance(result, dict) or result.get("permission") not in {"allow", "deny"}:
        raise MissionAdmissionError("cursor_hook_authorization_invalid")
    return result


def ci_main(
    args,
    *,
    environ=None,
    authority_reader=None,
    repo_root=REPO_ROOT,
    os_name=None,
):
    try:
        base = _commit(args.base)
        head = _commit(args.head)
        changed_files = _changed_files(base, head)
        patch = _git_bytes(
            "diff", "--no-ext-diff", "--no-textconv", "--binary",
            "--full-index", base, head, "--",
        )
        diff_sha256 = canonical_candidate_diff(changed_files, patch)
        receipt, identity, _authority = _validated_trusted_identity(
            authority_reader=authority_reader,
            repo_root=repo_root,
            os_name=os_name,
            expected_base_sha=base,
            expected_head_sha=head,
            expected_changed_files=changed_files,
        )
        _verify_governance_reads(receipt, head)
        if receipt["candidate"]["diff_sha256"] != diff_sha256:
            raise MissionAdmissionError("admission_candidate_changed")
        if identity["generation"] == BOOTSTRAP_GENERATION:
            contract_base = BOOTSTRAP_BASE_SHA
            contract_files = BOOTSTRAP_ALLOWED_FILES
            contract_tests = BOOTSTRAP_REQUIRED_TESTS
        elif identity["generation"] == STAGE2_GENERATION:
            contract_base = STAGE2_BASE_SHA
            contract_files = STAGE2_ALLOWED_FILES
            contract_tests = STAGE2_REQUIRED_TESTS
        else:
            raise MissionAdmissionError("candidate_admission_contract_unknown")
        if (
            base != contract_base
            or set(changed_files) != contract_files
            or set(identity["allowed_files"]) != contract_files
            or not BOOTSTRAP_FORBIDDEN_EFFECTS.issubset(
                set(identity["forbidden_effects"])
            )
            or not contract_tests.issubset(
                set(receipt["required_tests"])
            )
        ):
            raise MissionAdmissionError("bootstrap_exact_contract_changed")
        _validate_paths_and_effects(
            changed_files,
            identity["allowed_files"],
            identity["forbidden_files"],
            "repository_candidate_validation",
            identity["allowed_effects"],
            identity["forbidden_effects"],
        )
        result = {
            "success": True,
            "status": "mission_admission_verified",
            "receipt_id": identity["receipt_id"],
            "generation": identity["generation"],
            "base_sha": base,
            "head_sha": head,
            "changed_files": changed_files,
            "diff_sha256": diff_sha256,
        }
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, MissionAdmissionError, subprocess.SubprocessError) as exc:
        print(json.dumps({
            "success": False,
            "status": "READMISSION_REQUIRED",
            "reason_code": _reason(exc),
        }, sort_keys=True))
        return 2


def ci_external_main(args, *, repo_root=REPO_ROOT, os_name=None):
    """Verify an externally issued exact-candidate receipt without DB access."""
    try:
        base = _commit(args.base)
        head = _commit(args.head)
        changed_files = _changed_files(base, head)
        patch = _git_bytes("diff", "--binary", "--full-index", base, head, "--")
        diff_sha256 = canonical_candidate_diff(changed_files, patch)

        receipt_path = Path(args.receipt)
        if receipt_path.is_symlink() or not receipt_path.is_file():
            raise MissionAdmissionError("external_admission_receipt_unavailable")
        envelope = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt, identity = _validate_external_receipt_envelope(
            envelope,
            expected_repository=_repository_identity(),
            expected_base_sha=base,
            expected_head_sha=head,
            expected_changed_files=changed_files,
        )
        _verify_governance_reads(receipt, head)
        if receipt["candidate"]["diff_sha256"] != diff_sha256:
            raise MissionAdmissionError("admission_candidate_changed")
        if receipt["repository"]["base_sha"] != receipt["candidate"]["base_sha"]:
            raise MissionAdmissionError("admission_base_changed")
        if not receipt.get("required_tests"):
            raise MissionAdmissionError("admission_required_tests_invalid")
        if receipt.get("operational_acceptance", {}).get("business_outcome_authorized") is not False:
            raise MissionAdmissionError("admission_business_outcome_authority_invalid")
        _validate_paths_and_effects(
            changed_files,
            identity["allowed_files"],
            identity["forbidden_files"],
            "repository_candidate_validation",
            identity["allowed_effects"],
            identity["forbidden_effects"],
        )
        print(json.dumps({
            "success": True,
            "status": "mission_admission_verified",
            "receipt_id": identity["receipt_id"],
            "generation": identity["generation"],
            "base_sha": base,
            "head_sha": head,
            "changed_files": changed_files,
            "diff_sha256": diff_sha256,
        }, sort_keys=True))
        return 0
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        MissionAdmissionError,
        subprocess.SubprocessError,
    ) as exc:
        print(json.dumps({
            "success": False,
            "status": "READMISSION_REQUIRED",
            "reason_code": _reason(exc),
        }, sort_keys=True))
        return 2


def _validate_external_receipt_envelope(
    envelope,
    *,
    expected_repository,
    expected_base_sha,
    expected_head_sha,
    expected_changed_files,
    expected_canonical_binding=None,
    now=None,
):
    if not isinstance(envelope, dict) or set(envelope) != {
        "version", "receipt", "signature_ed25519"
    } or envelope.get("version") != "mission_admission_ci_envelope_v1":
        raise MissionAdmissionError("external_admission_envelope_invalid")
    receipt = envelope.get("receipt")
    try:
        signature = base64.b64decode(envelope["signature_ed25519"], validate=True)
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(EXTERNAL_ADMISSION_PUBLIC_KEY_B64, validate=True)
        )
        public_key.verify(signature, canonical_json(receipt))
    except (KeyError, TypeError, ValueError, InvalidSignature) as exc:
        raise MissionAdmissionError("external_admission_signature_invalid") from exc
    if not isinstance(receipt, dict) or set(receipt) != _TOP_LEVEL_FIELDS:
        raise MissionAdmissionError("admission_receipt_schema_invalid")
    body = {
        key: value for key, value in receipt.items()
        if key not in {"receipt_id", "content_sha256", "signature_hmac_sha256"}
    }
    _validate_body(body)
    content_sha256 = hashlib.sha256(canonical_json(body)).hexdigest()
    if (
        receipt.get("content_sha256") != content_sha256
        or receipt.get("receipt_id") != f"MAR-{content_sha256.upper()}"
        or not __import__("re").fullmatch(
            r"[0-9a-f]{64}", str(receipt.get("signature_hmac_sha256") or "")
        )
    ):
        raise MissionAdmissionError("admission_content_digest_invalid")
    issued = _parse_timestamp(receipt["issued_at"])
    expiry = _parse_timestamp(receipt["expires_at"])
    _validate_lifetime(issued, expiry)
    clock = _parse_timestamp(now) if now else __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    )
    if issued > clock + __import__("datetime").timedelta(
        seconds=RECEIPT_CLOCK_SKEW_SECONDS
    ):
        raise MissionAdmissionError("admission_not_yet_valid")
    if clock >= expiry:
        raise MissionAdmissionError("admission_expired")
    mission = receipt["mission"]
    repository = receipt["repository"]
    candidate = receipt["candidate"]
    changed_files = sorted(expected_changed_files)
    if expected_canonical_binding is not None:
        expected = {
            "mission_id": mission["mission_id"],
            "root_mission_id": mission["root_mission_id"],
            "generation": mission["generation"],
            "authority_key_sha256": receipt["authority_key_sha256"],
            "latest_correction_digest": receipt["owner_instruction_chain"][
                "latest_correction_digest"
            ],
            "collision_snapshot_sha256": receipt["collision_snapshot"][
                "snapshot_sha256"
            ],
        }
        observed_at = expected_canonical_binding.get("canonical_observed_at")
        if {
            key: value for key, value in expected_canonical_binding.items()
            if key != "canonical_observed_at"
        } != expected:
            raise MissionAdmissionError("canonical_admission_authority_changed")
        observed = _parse_timestamp(observed_at)
        if observed > issued + __import__("datetime").timedelta(
            seconds=RECEIPT_CLOCK_SKEW_SECONDS
        ) or issued - observed > __import__("datetime").timedelta(
            seconds=EXTERNAL_COLLISION_MAX_AGE_SECONDS
        ):
            raise MissionAdmissionError("canonical_admission_observation_stale")
    if repository["repository"] != expected_repository:
        raise MissionAdmissionError("admission_repository_changed")
    if repository["base_sha"] != expected_base_sha:
        raise MissionAdmissionError("admission_base_changed")
    if candidate["head_sha"] != expected_head_sha:
        raise MissionAdmissionError("admission_candidate_changed")
    if candidate["changed_files"] != changed_files:
        raise MissionAdmissionError("admission_candidate_changed")
    return receipt, {
        "receipt_id": receipt["receipt_id"],
        "content_sha256": content_sha256,
        "mission_id": mission["mission_id"],
        "root_mission_id": mission["root_mission_id"],
        "generation": mission["generation"],
        "base_sha": repository["base_sha"],
        "head_sha": candidate["head_sha"],
        "allowed_files": list(receipt["scope"]["allowed_files"]),
        "forbidden_files": list(receipt["scope"]["forbidden_files"]),
        "allowed_effects": list(receipt["scope"]["allowed_effects"]),
        "forbidden_effects": list(receipt["scope"]["forbidden_effects"]),
        "changed_files": list(candidate["changed_files"]),
    }


def _protected_database_url(environ):
    database_url = str(environ.get(ADMISSION_READ_DATABASE_ENV) or "").strip()
    if not database_url or "sslmode=require" not in database_url.lower():
        raise MissionAdmissionError("CANONICAL_AUTHORITY_UNAVAILABLE")
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set transaction read only")
                cursor.execute("set local statement_timeout='10000ms'")
                cursor.execute("set local lock_timeout='3000ms'")
                cursor.execute("set local idle_in_transaction_session_timeout='10000ms'")
                cursor.execute("show transaction_read_only")
                if str(cursor.fetchone()[0]).lower() != "on":
                    raise MissionAdmissionError("canonical_database_not_read_only")
                for setting, allowed in (
                    ("statement_timeout", {"10s", "10000ms"}),
                    ("lock_timeout", {"3s", "3000ms"}),
                    ("idle_in_transaction_session_timeout", {"10s", "10000ms"}),
                ):
                    cursor.execute(f"show {setting}")
                    if str(cursor.fetchone()[0]).lower() not in allowed:
                        raise MissionAdmissionError("canonical_database_timeout_invalid")
                cursor.execute("select rolsuper,rolcreaterole,rolcreatedb,rolreplication,rolbypassrls from pg_roles where rolname=current_user")
                role = cursor.fetchone()
                if not role or any(role):
                    raise MissionAdmissionError("canonical_database_privilege_invalid")
                cursor.execute("select has_database_privilege(current_user,current_database(),'CREATE'),has_schema_privilege(current_user,'public','CREATE')")
                if any(cursor.fetchone()):
                    raise MissionAdmissionError("canonical_database_privilege_invalid")
                for table in ("charlie_missions", "charlie_mission_events", "operational_events"):
                    cursor.execute(
                        "select has_table_privilege(current_user,%s,'SELECT'),has_table_privilege(current_user,%s,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')",
                        (f"public.{table}", f"public.{table}"),
                    )
                    can_read, can_write = cursor.fetchone()
                    if not can_read or can_write:
                        raise MissionAdmissionError("canonical_database_privilege_invalid")
    except MissionAdmissionError:
        raise
    except Exception as exc:
        raise MissionAdmissionError("CANONICAL_AUTHORITY_UNAVAILABLE") from exc
    return database_url


def _canonical_contract_for_pull(number, base, head, branch, diff_sha256, changed_files, database_url):
    result, status = list_missions(limit=100, database_url=database_url)
    if status >= 400 or not result.get("success"):
        raise MissionAdmissionError("CANONICAL_AUTHORITY_UNAVAILABLE")
    matches = []
    for mission in result.get("missions") or []:
        metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
        packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
        if (
            packet.get("pr_number") == number
            and packet.get("candidate_revision") == head
            and packet.get("branch_name") == branch
            and packet.get("candidate_diff_sha256") == diff_sha256
        ):
            matches.append((mission, metadata))
    if len(matches) != 1:
        dispatch_matches = []
        for mission in result.get("missions") or []:
            metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
            authorization = metadata.get("dispatch_authorization") \
                if isinstance(metadata.get("dispatch_authorization"), dict) else {}
            if (authorization.get("status") == "valid"
                    and authorization.get("base_sha") == base
                    and authorization.get("branch") == branch
                    and sorted(authorization.get("allowed_files") or []) == sorted(changed_files)):
                contract = {"generation": authorization.get("generation"), "branch": branch,
                    "base_sha": base, "allowed_files": sorted(changed_files), "forbidden_files": ["*"],
                    "allowed_effects": sorted(authorization.get("allowed_effects") or []),
                    "forbidden_effects": sorted(authorization.get("forbidden_effects") or []),
                    "required_tests": ["mission-admission", "charlie-core",
                        "Unit tests with disposable Postgres audit rails",
                        "Closed Render migration rail with disposable Postgres",
                        "Playwright real-browser behavior gate"],
                    "operational_acceptance": ["Independent review completed; stop before merge or deployment"]}
                family = dict(metadata.get("mission_family") or {})
                family["root_mission_id"] = family.get("root_mission_id") or mission.get("mission_id")
                family["generation"] = authorization.get("generation")
                dispatch_matches.append((mission, metadata, contract, family))
        if len(dispatch_matches) != 1:
            raise MissionAdmissionError("canonical_candidate_linkage_unavailable")
        return dispatch_matches[0]
    mission, metadata = matches[0]
    contract = metadata.get("mission_admission_contract")
    family = metadata.get("mission_family")
    if not isinstance(contract, dict) or not isinstance(family, dict):
        raise MissionAdmissionError("canonical_admission_contract_invalid")
    return mission, metadata, contract, family


def _require_canonical_review_linkage(metadata, number, head, branch, diff_sha256, changed_files):
    packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    if (
        packet.get("pr_number") != number
        or packet.get("candidate_revision") != head
        or packet.get("branch_name") != branch
        or packet.get("candidate_diff_sha256") != diff_sha256
        or sorted(packet.get("changed_files") or []) != sorted(changed_files)
    ):
        raise MissionAdmissionError("canonical_candidate_linkage_changed")


def _replace_receipt_marker(body, marker):
    pattern = r"(?m)^Mission-Admission-Receipt-B64: .*(?:\r?\n|$)"
    if len(__import__("re").findall(pattern, body)) > 1:
        raise MissionAdmissionError("duplicate_external_admission_receipts")
    preserved = __import__("re").sub(pattern, "", body).rstrip()
    return (preserved + "\n\n" if preserved else "") + f"Mission-Admission-Receipt-B64: {marker}\n"


def _compare_current_authority(receipt, authority, contract):
    admission = authority.get("admission") if isinstance(authority.get("admission"), dict) else {}
    mission = receipt["mission"]
    if authority.get("mission_id") != mission["mission_id"] or authority.get("root_mission_id") != mission["root_mission_id"]:
        raise MissionAdmissionError("mission_generation_changed")
    if mission["generation"] != str(contract.get("generation") or mission["generation"]):
        raise MissionAdmissionError("mission_generation_changed")
    if admission.get("status") in {"revoked", "consumed"}:
        raise MissionAdmissionError(f"admission_{admission['status']}")
    if admission.get("status") != "valid":
        raise MissionAdmissionError("projection_identity_mismatch")
    if receipt["owner_instruction_chain"]["latest_correction_digest"] != authority.get("latest_correction_digest"):
        raise MissionAdmissionError("owner_correction_changed")
    if receipt["collision_snapshot"]["snapshot_sha256"] != authority.get("collision_snapshot_sha256"):
        raise MissionAdmissionError("collision_snapshot_changed")
    expected_projection = {
        "mission_id": mission["mission_id"],
        "root_mission_id": mission["root_mission_id"],
        "generation": mission["generation"],
        "base_sha": receipt["repository"]["base_sha"],
        "head_sha": receipt["candidate"]["head_sha"],
        "authority_key_sha256": receipt["authority_key_sha256"],
        "latest_correction_digest": authority.get("latest_correction_digest"),
        "collision_snapshot_sha256": authority.get("collision_snapshot_sha256"),
    }
    if any(admission.get(key) != value for key, value in expected_projection.items()):
        raise MissionAdmissionError("projection_identity_mismatch")
    if (
        admission.get("receipt_id") != receipt.get("receipt_id")
        or admission.get("content_sha256") != receipt.get("content_sha256")
    ):
        raise MissionAdmissionError("receipt_content_mismatch")
    comparisons = {
        "allowed_files": receipt["scope"]["allowed_files"],
        "forbidden_files": receipt["scope"]["forbidden_files"],
        "allowed_effects": receipt["scope"]["allowed_effects"],
        "forbidden_effects": receipt["scope"]["forbidden_effects"],
        "required_tests": receipt["required_tests"],
    }
    for key, value in comparisons.items():
        if sorted(value) != sorted(contract.get(key) or []):
            raise MissionAdmissionError(
                "required_test_mismatch" if key == "required_tests" else "scope_mismatch"
            )
    acceptance = receipt["operational_acceptance"]
    if acceptance.get("business_outcome_authorized") is not False or sorted(acceptance.get("requirements") or []) != sorted(contract.get("operational_acceptance") or []):
        raise MissionAdmissionError("operational_acceptance_mismatch")
    if receipt["owner_instruction_chain"]["admission_packet_sha256"] != _canonical_packet_digest(authority, contract):
        raise MissionAdmissionError("admission_packet_mismatch")


def _canonical_packet_digest(authority, contract):
    admission = authority.get("admission") if isinstance(authority.get("admission"), dict) else {}
    binding = {
        "admission": {
            key: admission.get(key)
            for key in (
                "mission_id", "root_mission_id",
                "generation", "base_sha", "head_sha", "authority_key_sha256",
                "latest_correction_digest", "collision_snapshot_sha256", "status",
            )
        },
        "contract": contract,
        "latest_correction_digest": authority.get("latest_correction_digest"),
        "collision_snapshot_sha256": authority.get("collision_snapshot_sha256"),
    }
    return hashlib.sha256(canonical_json(binding)).hexdigest()


def _require_exact_admission_projection(authority, mission, family, base, head, authority_key_sha256):
    admission = authority.get("admission") if isinstance(authority.get("admission"), dict) else {}
    expected = {
        "status": "valid",
        "mission_id": mission["mission_id"],
        "root_mission_id": authority.get("root_mission_id"),
        "generation": family.get("generation"),
        "base_sha": base,
        "head_sha": head,
        "authority_key_sha256": authority_key_sha256,
        "latest_correction_digest": authority.get("latest_correction_digest"),
        "collision_snapshot_sha256": authority.get("collision_snapshot_sha256"),
    }
    mismatches = [key for key, value in expected.items() if admission.get(key) != value]
    if mismatches:
        status = admission.get("status")
        if status in {"revoked", "consumed"}:
            raise MissionAdmissionError(f"admission_{status}")
        raise MissionAdmissionError("projection_identity_mismatch_" + mismatches[0])


def _build_exact_candidate_payload(*, mission, family, authority, contract, base,
                                   head, branch, diff_sha256, changed_files,
                                   governance_reads, repository):
    """Build the one canonical payload used by recording and protected issuance."""
    return {
        "mission": {"mission_id": mission["mission_id"], "root_mission_id": authority["root_mission_id"], "generation": str(family.get("generation") or "")},
        "owner_instruction_chain": {"instruction_digests": [hashlib.sha256(str(mission.get("raw_text") or "").encode()).hexdigest(), authority["latest_correction_digest"]], "latest_correction_digest": authority["latest_correction_digest"], "admission_packet_sha256": _canonical_packet_digest(authority, contract)},
        "repository": {"repository": repository, "base_ref": "main", "base_sha": base},
        "governance_reads": governance_reads,
        "existing_system_trace": {"smallest_genuine_gap": "Protected main lacked a dynamic canonical receipt issuer.", "reused_components": ["charlie_missions", "charlie_mission_events", "operational_events", "mission_admission_receipt_v1", "CHARLIE Admission Guard"], "implementation_sources": sorted(["modules/charlie/mission_admission.py", "modules/charlie/mission_store.py", "scripts/charlie_mission_admission_guard.py"])},
        "scope": {key: sorted(contract.get(key) or []) for key in ("allowed_files", "forbidden_files", "allowed_effects", "forbidden_effects")},
        "collision_snapshot": {"captured_at": authority["collision_observed_at"], "active_claims": list(authority["active_claims"]), "snapshot_sha256": authority["collision_snapshot_sha256"]},
        "required_tests": sorted(contract.get("required_tests") or []),
        "operational_acceptance": {"requirements": sorted(contract.get("operational_acceptance") or []), "business_outcome_authorized": False},
        "candidate": {"candidate_id": f"{mission['mission_id']}:{family.get('generation')}:{head}", "branch": branch, "base_sha": base, "head_sha": head, "diff_sha256": diff_sha256, "changed_files": changed_files},
    }


def _github_pull_request(number, token, *, body=None):
    url = f"https://api.github.com/repos/Crewless9086/amadeus-pig-tracking-system/pulls/{number}"
    payload = None if body is None else json.dumps({"body": body}, separators=(",", ":")).encode()
    req = url_request.Request(url, data=payload, method="GET" if body is None else "PATCH", headers={
        "Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
        "Content-Type": "application/json", "User-Agent": "CHARLIE-Admission-Issuer",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with url_request.urlopen(req, timeout=15) as response:
        return json.loads(response.read(1048576))


def issue_pr_main(args, *, environ=None):
    """Issue one exact signed receipt from protected canonical authority."""
    environ = os.environ if environ is None else environ
    try:
        if args.pull_request_number <= 0 or not __import__("re").fullmatch(r"[0-9a-f]{40}", args.expected_head_sha):
            raise MissionAdmissionError("issuer_input_invalid")
        token = str(environ.get("GITHUB_TOKEN") or "")
        if not token:
            raise MissionAdmissionError("issuer_runtime_unavailable")
        database_url = _protected_database_url(environ)
        pull = _github_pull_request(args.pull_request_number, token)
        if pull.get("state") != "open" or pull.get("merged_at") is not None:
            raise MissionAdmissionError("issuer_target_not_open")
        head = str((pull.get("head") or {}).get("sha") or "")
        base = str((pull.get("base") or {}).get("sha") or "")
        branch = str((pull.get("head") or {}).get("ref") or "")
        if head != args.expected_head_sha or (pull.get("base") or {}).get("ref") != "main":
            raise MissionAdmissionError("admission_candidate_changed")
        subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "protocol.file.allow=never", "fetch", "--no-tags", "--no-recurse-submodules", "origin", head], cwd=REPO_ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        base, head = _commit(base), _commit(head)
        changed_files = _changed_files(base, head)
        patch = _git_bytes("diff", "--no-ext-diff", "--no-textconv", "--binary", "--full-index", base, head, "--")
        diff_sha256 = canonical_candidate_diff(changed_files, patch)
        mission, metadata, contract, family = _canonical_contract_for_pull(
            args.pull_request_number, base, head, branch, diff_sha256, changed_files, database_url)
        if sorted(changed_files) != sorted(contract.get("allowed_files") or []) or base != contract.get("base_sha") or branch != contract.get("branch"):
            raise MissionAdmissionError("canonical_candidate_linkage_changed")
        if not str(family.get("generation") or ""):
            raise MissionAdmissionError("mission_generation_changed")
        authority, status = read_current_mission_admission_authority(mission["mission_id"], database_url=database_url)
        if status >= 400 or not authority.get("success"):
            raise MissionAdmissionError("CANONICAL_AUTHORITY_UNAVAILABLE")
        collision_time, active_claims = authority["collision_observed_at"], list(authority["active_claims"])
        if collision_snapshot_digest(collision_time, active_claims) != authority.get("collision_snapshot_sha256"):
            raise MissionAdmissionError("canonical_collision_snapshot_invalid")
        payload = _build_exact_candidate_payload(
            mission=mission, family=family, authority=authority, contract=contract,
            base=base, head=head, branch=branch, diff_sha256=diff_sha256,
            changed_files=changed_files,
            governance_reads=_governance_read_identities(base),
            repository=_repository_identity(),
        )
        try:
            hmac_key = base64.b64decode(str(environ.get("CHARLIE_VALIDATION_RECEIPT_KEY_B64") or ""), validate=True)
            signing_seed = base64.b64decode(str(environ.get("CHARLIE_ADMISSION_RECEIPT_SIGNING_KEY_B64") or ""), validate=True)
            if len(signing_seed) != 32:
                raise ValueError
        except Exception as exc:
            raise MissionAdmissionError("issuer_signing_authority_unavailable") from exc
        if not hmac_key:
            raise MissionAdmissionError("issuer_signing_authority_unavailable")
        authority_key_sha256 = hashlib.sha256(hmac_key).hexdigest()
        protected_receipt, protected_marker = None, ""
        try:
            _require_exact_admission_projection(
                authority, mission, family, base, head, authority_key_sha256)
        except MissionAdmissionError as exc:
            if not str(exc).startswith("projection_identity_mismatch_"):
                raise
            projected = dict(authority)
            projected["admission"] = {"status": "valid", "mission_id": mission["mission_id"],
                "root_mission_id": authority["root_mission_id"], "generation": family["generation"],
                "base_sha": base, "head_sha": head, "authority_key_sha256": authority_key_sha256,
                "latest_correction_digest": authority["latest_correction_digest"],
                "collision_snapshot_sha256": authority["collision_snapshot_sha256"]}
            payload = _build_exact_candidate_payload(
                mission=mission, family=family, authority=projected, contract=contract,
                base=base, head=head, branch=branch, diff_sha256=diff_sha256,
                changed_files=changed_files, governance_reads=_governance_read_identities(base),
                repository=_repository_identity())
            protected_receipt = sign_mission_admission_receipt(payload, hmac_key)
            envelope = {"version": "mission_admission_ci_envelope_v1", "receipt": protected_receipt,
                "signature_ed25519": base64.b64encode(Ed25519PrivateKey.from_private_bytes(
                    signing_seed).sign(canonical_json(protected_receipt))).decode()}
            callback_base = str(environ.get("CHARLIE_CANONICAL_API_URL") or "").rstrip("/")
            if not callback_base.startswith("https://"):
                raise MissionAdmissionError("canonical_admission_callback_unavailable")
            callback = url_request.Request(callback_base + PROTECTED_ADMISSION_ROUTE_PREFIX +
                url_parse.quote(mission["mission_id"], safe="") + "/protected-admission",
                data=canonical_json({"envelope": envelope, "pr_number": args.pull_request_number}), method="POST",
                headers={"Content-Type": "application/json", "User-Agent": "CHARLIE-Admission-Issuer"})
            try:
                with url_request.urlopen(callback, timeout=15) as response:
                    if response.status not in {200, 201}:
                        raise OSError("unexpected_status")
            except (url_error.URLError, OSError) as callback_error:
                raise MissionAdmissionError("canonical_admission_callback_unavailable") from callback_error
            authority, status = read_current_mission_admission_authority(
                mission["mission_id"], database_url=database_url)
            if status >= 400 or not authority.get("success"):
                raise MissionAdmissionError("CANONICAL_AUTHORITY_UNAVAILABLE")
            _require_exact_admission_projection(
                authority, mission, family, base, head, authority_key_sha256)
            protected_marker = base64.b64encode(canonical_json(envelope)).decode()
        body = str(pull.get("body") or "")
        pattern = r"(?m)^Mission-Admission-Receipt-B64: .*(?:\r?\n|$)"
        existing = __import__("re").findall(pattern, body)
        if len(existing) > 1:
            raise MissionAdmissionError("duplicate_external_admission_receipts")
        receipt = protected_receipt
        marker = protected_marker
        encoded_existing = __import__("re").findall(
            r"(?m)^Mission-Admission-Receipt-B64: ([A-Za-z0-9+/]+={0,2})\r?$",
            body,
        )
        if len(encoded_existing) == 1:
            try:
                existing_envelope = json.loads(base64.b64decode(
                    encoded_existing[0], validate=True
                ))
                existing_receipt, _identity = _validate_external_receipt_envelope(
                    existing_envelope,
                    expected_repository=_repository_identity(),
                    expected_base_sha=base,
                    expected_head_sha=head,
                    expected_changed_files=changed_files,
                )
                if existing_receipt["candidate"]["diff_sha256"] != diff_sha256:
                    raise MissionAdmissionError("admission_candidate_changed")
                _compare_current_authority(existing_receipt, authority, contract)
                receipt = existing_receipt
                marker = encoded_existing[0]
            except Exception:
                receipt = None
        if receipt is None:
            receipt = admission_receipt = authority.get("admission", {}).get("signed_receipt")
            if not isinstance(admission_receipt, dict):
                raise MissionAdmissionError("receipt_content_mismatch")
            validate_mission_admission_receipt(
                admission_receipt, hmac_key,
                expected_repository=_repository_identity(),
                expected_base_sha=base, expected_head_sha=head,
                expected_generation=str(family.get("generation") or ""),
                expected_mission_id=mission["mission_id"],
                expected_root_mission_id=authority["root_mission_id"],
                expected_changed_files=changed_files,
            )
            if {
                key: admission_receipt.get(key)
                for key in payload
            } != payload:
                raise MissionAdmissionError("receipt_content_mismatch")
            _compare_current_authority(admission_receipt, authority, contract)
            envelope = {"version": "mission_admission_ci_envelope_v1", "receipt": receipt, "signature_ed25519": base64.b64encode(Ed25519PrivateKey.from_private_bytes(signing_seed).sign(canonical_json(receipt))).decode()}
            marker = base64.b64encode(canonical_json(envelope)).decode()
        updated = _replace_receipt_marker(body, marker)
        if updated != body:
            _github_pull_request(args.pull_request_number, token, body=updated)
        if args.event_output:
            event_path = Path(args.event_output)
            if event_path.is_symlink() or not event_path.parent.is_dir():
                raise MissionAdmissionError("issuer_event_output_invalid")
            event_path.write_text(json.dumps({
                "number": args.pull_request_number,
                "repository": {"full_name": _repository_identity()},
                "pull_request": {
                    "body": updated,
                    "base": {"ref": "main", "sha": base},
                    "head": {"ref": branch, "sha": head},
                },
            }, sort_keys=True), encoding="utf-8")
        print(json.dumps({"success": True, "pr_number": args.pull_request_number, "head_sha": head, "receipt_id": receipt["receipt_id"], "expires_at": receipt["expires_at"]}, sort_keys=True))
        hmac_key, signing_seed = b"", b""
        return 0
    except Exception as exc:
        print(json.dumps({"success": False, "status": "READMISSION_REQUIRED", "reason_code": _reason(exc)}, sort_keys=True))
        return 2


def trusted_check_main(args, *, environ=None):
    """Publish the exact check using only protected-base code and an App token."""
    environ = os.environ if environ is None else environ
    check_id = None
    head = ""
    token = str(environ.get("CHARLIE_ADMISSION_APP_TOKEN") or "")
    try:
        event_path = Path(args.event)
        if event_path.is_symlink() or not event_path.is_file() or not token:
            raise MissionAdmissionError("trusted_check_runtime_unavailable")
        event = json.loads(event_path.read_text(encoding="utf-8"))
        database_url = _protected_database_url(environ)
        pull = event.get("pull_request") if isinstance(event, dict) else {}
        repository = event.get("repository") if isinstance(event, dict) else {}
        base_row = pull.get("base") if isinstance(pull, dict) else {}
        head_row = pull.get("head") if isinstance(pull, dict) else {}
        number = event.get("number")
        base = str((base_row or {}).get("sha") or "")
        head = str((head_row or {}).get("sha") or "")
        if (
            repository.get("full_name") != "Crewless9086/amadeus-pig-tracking-system"
            or (base_row or {}).get("ref") != "main"
            or not isinstance(number, int)
            or number <= 0
            or not __import__("re").fullmatch(r"[0-9a-f]{40}", base)
            or not __import__("re").fullmatch(r"[0-9a-f]{40}", head)
        ):
            raise MissionAdmissionError("trusted_check_event_invalid")
        pending = _app_check_request(
            "POST", token, {
                "name": "mission-admission",
                "head_sha": head,
                "status": "in_progress",
                "output": {
                    "title": "Mission Admission verification running",
                    "summary": f"Verifying exact candidate {head}.",
                },
            },
        )
        check_id = pending.get("id")
        if not isinstance(check_id, int):
            raise MissionAdmissionError("trusted_check_publish_failed")
        subprocess.run(
            [
                "git", "-c", "core.hooksPath=/dev/null",
                "-c", "protocol.file.allow=never", "fetch", "--no-tags",
                "--no-recurse-submodules", "origin", head,
            ],
            cwd=REPO_ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        base = _commit(base)
        head = _commit(head)
        changed_files = _changed_files(base, head)
        patch = _git_bytes(
            "diff", "--no-ext-diff", "--no-textconv", "--binary",
            "--full-index", base, head, "--",
        )
        diff_sha256 = canonical_candidate_diff(changed_files, patch)
        matches = __import__("re").findall(
            r"(?m)^Mission-Admission-Receipt-B64: ([A-Za-z0-9+/]+={0,2})\r?$",
            str(pull.get("body") or ""),
        )
        if len(matches) != 1:
            raise MissionAdmissionError("exactly_one_external_admission_receipt_required")
        try:
            envelope = json.loads(base64.b64decode(matches[0], validate=True))
        except Exception as exc:
            raise MissionAdmissionError("external_admission_receipt_invalid") from exc
        receipt, identity = _validate_external_receipt_envelope(
            envelope,
            expected_repository=repository["full_name"],
            expected_base_sha=base,
            expected_head_sha=head,
            expected_changed_files=changed_files,
        )
        mission_result, mission_status = get_mission(
            receipt["mission"]["mission_id"], database_url=database_url
        )
        authority, authority_status = read_current_mission_admission_authority(
            receipt["mission"]["mission_id"], database_url=database_url
        )
        if (
            mission_status >= 400 or not mission_result.get("success")
            or authority_status >= 400 or not authority.get("success")
        ):
            raise MissionAdmissionError("CANONICAL_AUTHORITY_UNAVAILABLE")
        metadata = mission_result["mission"].get("metadata") or {}
        contract = metadata.get("mission_admission_contract") or {}
        family = metadata.get("mission_family") or {}
        if receipt["mission"]["generation"] != family.get("generation"):
            raise MissionAdmissionError("mission_generation_changed")
        _require_canonical_review_linkage(
            metadata,
            number,
            head,
            str((head_row or {}).get("ref") or ""),
            diff_sha256,
            changed_files,
        )
        _compare_current_authority(receipt, authority, contract)
        _verify_governance_reads(receipt, head)
        if receipt["candidate"]["diff_sha256"] != diff_sha256:
            raise MissionAdmissionError("admission_candidate_changed")
        _validate_paths_and_effects(
            changed_files,
            identity["allowed_files"],
            identity["forbidden_files"],
            "repository_candidate_validation",
            identity["allowed_effects"],
            identity["forbidden_effects"],
        )
        _app_check_request("PATCH", token, {
            "status": "completed",
            "conclusion": "success",
            "output": {
                "title": "Mission Admission verified",
                "summary": (
                    f"Receipt {identity['receipt_id']} verified for exact head {head}."
                ),
            },
        }, check_id=check_id)
        print(json.dumps({
            "success": True, "receipt_id": identity["receipt_id"], "head_sha": head
        }, sort_keys=True))
        return 0
    except Exception as exc:
        reason = _reason(exc)
        if check_id is not None:
            try:
                _app_check_request("PATCH", token, {
                    "status": "completed",
                    "conclusion": "failure",
                    "output": {
                        "title": "Mission Admission rejected",
                        "summary": f"Exact head {head}: {reason}",
                    },
                }, check_id=check_id)
            except Exception:
                pass
        print(json.dumps({
            "success": False, "status": "READMISSION_REQUIRED", "reason_code": reason
        }, sort_keys=True))
        return 2


def _app_check_request(method, token, payload, *, check_id=None):
    suffix = f"/{check_id}" if check_id is not None else ""
    request = url_request.Request(
        "https://api.github.com/repos/Crewless9086/amadeus-pig-tracking-system/check-runs" + suffix,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "CHARLIE-Admission-Guard",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method=method,
    )
    with url_request.urlopen(request, timeout=15) as response:
        return json.loads(response.read(131072))


def issue_bootstrap_main(
    args,
    *,
    environ=None,
    authority_reader=None,
    admission_writer=None,
    repo_root=REPO_ROOT,
    os_name=None,
):
    """Trusted CI issuer for the one immutable bootstrap candidate."""
    environ = os.environ if environ is None else environ
    try:
        stage2 = getattr(args, "mode", "") == "issue-stage2"
        contract = {
            "base_sha": STAGE2_BASE_SHA if stage2 else BOOTSTRAP_BASE_SHA,
            "mission_id": STAGE2_MISSION_ID if stage2 else BOOTSTRAP_MISSION_ID,
            "root_mission_id": STAGE2_ROOT_MISSION_ID if stage2 else BOOTSTRAP_ROOT_MISSION_ID,
            "generation": STAGE2_GENERATION if stage2 else BOOTSTRAP_GENERATION,
            "owner_instruction_sha256": STAGE2_OWNER_INSTRUCTION_SHA256 if stage2 else BOOTSTRAP_OWNER_INSTRUCTION_SHA256,
            "packet_sha256": STAGE2_PACKET_SHA256 if stage2 else BOOTSTRAP_PACKET_SHA256,
            "allowed_files": STAGE2_ALLOWED_FILES if stage2 else BOOTSTRAP_ALLOWED_FILES,
            "required_tests": STAGE2_REQUIRED_TESTS if stage2 else BOOTSTRAP_REQUIRED_TESTS,
            "branch": "cursor/mission-admission-stage2-20260827" if stage2 else "cursor/mission-admission-guard-80dd",
        }
        if str(environ.get("CI") or "").lower() != "true":
            raise MissionAdmissionError("bootstrap_issuer_ci_only")
        base = _commit(args.base)
        head = _commit(args.head)
        if stage2 and str(environ.get("CHARLIE_STAGE2_ADMITTED_HEAD") or "") != head:
            raise MissionAdmissionError("stage2_external_head_admission_required")
        changed_files = _changed_files(base, head)
        if (
            base != contract["base_sha"]
            or set(changed_files) != contract["allowed_files"]
        ):
            raise MissionAdmissionError("bootstrap_exact_contract_changed")
        authority_reader = (
            authority_reader or read_current_mission_admission_authority
        )
        authority, status = authority_reader(contract["mission_id"])
        if status >= 400 or not authority.get("success"):
            raise MissionAdmissionError("canonical_admission_authority_unavailable")
        if (
            authority.get("mission_id") != contract["mission_id"]
            or authority.get("root_mission_id") != contract["root_mission_id"]
            or not __import__("re").fullmatch(
                r"[0-9a-f]{64}",
                str(authority.get("latest_correction_digest") or ""),
            )
        ):
            raise MissionAdmissionError("canonical_owner_correction_unavailable")
        state_root = _trusted_state_root(repo_root, os_name=os_name)
        key_path = state_root / "validation-receipt.key"
        if key_path.is_symlink():
            raise MissionAdmissionError("validation_authority_symlink_denied")
        key = key_path.read_bytes()
        if (os_name or os.name) != "nt" and key_path.stat().st_mode & 0o077:
            raise MissionAdmissionError("validation_authority_permissions_invalid")
        patch = _git_bytes(
            "diff", "--binary", "--full-index", base, head, "--"
        )
        diff_sha256 = canonical_candidate_diff(changed_files, patch)
        governance_reads = _governance_read_identities(head)
        collision_time = str(authority.get("collision_observed_at") or "")
        active_claims = list(authority.get("active_claims") or [])
        if (
            collision_snapshot_digest(collision_time, active_claims)
            != authority.get("collision_snapshot_sha256")
        ):
            raise MissionAdmissionError("canonical_collision_snapshot_invalid")
        payload = {
            "mission": {
                "mission_id": contract["mission_id"],
                "root_mission_id": contract["root_mission_id"],
                "generation": contract["generation"],
            },
            "owner_instruction_chain": {
                "instruction_digests": [
                    contract["owner_instruction_sha256"],
                    authority["latest_correction_digest"],
                ],
                "latest_correction_digest": authority[
                    "latest_correction_digest"
                ],
                "admission_packet_sha256": contract["packet_sha256"],
            },
            "repository": {
                "repository": _repository_identity(),
                "base_ref": "main",
                "base_sha": base,
            },
            "governance_reads": governance_reads,
            "existing_system_trace": {
                "smallest_genuine_gap": (
                    "Cursor mutation lacked a trusted, mission-bound, "
                    "content-addressed admission decision."
                ),
                "reused_components": [
                    "charlie_missions",
                    "charlie_mission_events",
                    "operational_events",
                    "validation_receipt authority",
                    "Vault retrieval and alignment",
                ],
                "implementation_sources": sorted([
                    "modules/charlie/mission_store.py",
                    "modules/charlie/runtime_staging.py",
                    "modules/charlie/validation_receipt.py",
                ]),
            },
            "scope": {
                "allowed_files": sorted(contract["allowed_files"]),
                "forbidden_files": sorted({
                    ".cursor/environment.json",
                    "AGENTS.md",
                    "docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md",
                    "docs/09-vault-brain/00-governance/CONTROL_TOWER_ASSESSMENT_AND_DISPATCH_PROTOCOL.md",
                    "modules/charlie/runner_control.py",
                    "package-lock.json",
                    "tests/test_charlie_runner_control.py",
                }),
                "allowed_effects": [
                    "repository_candidate_validation",
                    "repository_file_delete",
                    "repository_file_write",
                ],
                "forbidden_effects": sorted(BOOTSTRAP_FORBIDDEN_EFFECTS),
            },
            "collision_snapshot": {
                "captured_at": collision_time,
                "active_claims": active_claims,
                "snapshot_sha256": authority[
                    "collision_snapshot_sha256"
                ],
            },
            "required_tests": sorted(contract["required_tests"]),
            "operational_acceptance": {
                "requirements": [
                    "Hosted exact-head admission and CHARLIE checks pass.",
                    "A fresh independent reviewer accepts the corrected source.",
                    "Stage 2 separately integrates a deployed receipt supplier.",
                ],
                "business_outcome_authorized": False,
            },
            "candidate": {
                "candidate_id": (
                    f"{contract['mission_id']}:{contract['generation']}:{head}"
                ),
                "branch": contract["branch"],
                "base_sha": base,
                "head_sha": head,
                "diff_sha256": diff_sha256,
                "changed_files": changed_files,
            },
        }
        receipt = sign_mission_admission_receipt(payload, key)
        receipt_dir = state_root / "mission-admission-receipts"
        receipt_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = receipt_dir / f"{receipt['receipt_id']}.json"
        encoded = json.dumps(
            receipt, sort_keys=True, separators=(",", ":")
        ).encode("utf-8") + b"\n"
        if receipt_path.exists():
            if receipt_path.read_bytes() != encoded:
                raise MissionAdmissionError("bootstrap_receipt_replay_conflict")
        else:
            descriptor = os.open(
                receipt_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        admission = {
            "receipt_id": receipt["receipt_id"],
            "content_sha256": receipt["content_sha256"],
            "mission_id": contract["mission_id"],
            "root_mission_id": contract["root_mission_id"],
            "generation": contract["generation"],
            "base_sha": base,
            "head_sha": head,
            "authority_key_sha256": receipt["authority_key_sha256"],
            "latest_correction_digest": authority[
                "latest_correction_digest"
            ],
            "collision_snapshot_sha256": authority[
                "collision_snapshot_sha256"
            ],
            "signed_receipt": receipt,
        }
        writer = admission_writer or append_mission_admission_event
        written, write_status = writer(
            contract["mission_id"],
            admission,
            authenticated_principal="control_tower_isolated_validator_v2",
        )
        if write_status >= 400 or not written.get("success"):
            raise MissionAdmissionError(
                written.get("status") or "bootstrap_admission_write_failed"
            )
        print(json.dumps({
            "success": True,
            "status": "bootstrap_admission_issued",
            "receipt_id": receipt["receipt_id"],
            "head_sha": head,
            "diff_sha256": diff_sha256,
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, MissionAdmissionError, subprocess.SubprocessError) as exc:
        print(json.dumps({
            "success": False,
            "status": "READMISSION_REQUIRED",
            "reason_code": _reason(exc),
        }, sort_keys=True))
        return 2


def _require_admission(
    packet,
    effect,
    *,
    environ=None,
    authority_reader=None,
    repo_root=REPO_ROOT,
    os_name=None,
):
    receipt, identity, _authority = _validated_trusted_identity(
        authority_reader=authority_reader,
        repo_root=repo_root,
        os_name=os_name,
        environ=environ,
    )
    _verify_governance_reads(receipt, identity["head_sha"])
    current_head = _commit("HEAD")
    if current_head not in {identity["base_sha"], identity["head_sha"]}:
        raise MissionAdmissionError("admission_candidate_changed")
    current_paths = _worktree_changed_files(identity["base_sha"])
    target_path = _tool_target_path(packet)
    if not target_path:
        raise MissionAdmissionError("mutation_target_path_required")
    current_paths = sorted(set(current_paths + [target_path]))
    _validate_paths_and_effects(
        current_paths,
        identity["allowed_files"],
        identity["forbidden_files"],
        effect,
        identity["allowed_effects"],
        identity["forbidden_effects"],
    )
    return identity


def _validated_trusted_identity(
    *,
    authority_reader=None,
    repo_root=REPO_ROOT,
    os_name=None,
    expected_base_sha="",
    expected_head_sha="",
    expected_changed_files=None,
    environ=None,
):
    environ = os.environ if environ is None else environ
    delivered_root = str(environ.get("CHARLIE_MISSION_ADMISSION_STATE_ROOT") or "").strip()
    delivered_mission = str(environ.get("CHARLIE_MISSION_ADMISSION_MISSION_ID") or "").strip()
    if bool(delivered_root) != bool(delivered_mission):
        raise MissionAdmissionError("trusted_admission_delivery_incomplete")
    mission_id = delivered_mission or BOOTSTRAP_MISSION_ID
    authority_reader = authority_reader or read_current_mission_admission_authority
    authority_result, authority_status = authority_reader(mission_id)
    if authority_status >= 400 or not authority_result.get("success"):
        raise MissionAdmissionError("canonical_admission_authority_unavailable")
    authority = authority_result
    current = (
        authority.get("admission")
        if isinstance(authority.get("admission"), dict)
        else {}
    )
    if current.get("status") != "valid":
        raise MissionAdmissionError("canonical_admission_not_active")
    receipt, key, key_sha256 = _trusted_receipt(
        current,
        repo_root=repo_root,
        os_name=os_name,
        environ=environ,
    )
    identity = validate_mission_admission_receipt(
        receipt,
        key,
        expected_repository=_repository_identity(),
        expected_base_sha=expected_base_sha,
        expected_head_sha=expected_head_sha,
        expected_generation=str(current.get("generation") or ""),
        expected_mission_id=mission_id,
        expected_root_mission_id=str(authority.get("root_mission_id") or ""),
        expected_authority_key_sha256=key_sha256,
        expected_changed_files=expected_changed_files,
    )
    if (
        authority.get("mission_id") != mission_id
        or identity["root_mission_id"] != authority.get("root_mission_id")
        or identity["receipt_id"] != current.get("receipt_id")
        or identity["content_sha256"] != current.get("content_sha256")
        or receipt["owner_instruction_chain"]["latest_correction_digest"]
        != authority.get("latest_correction_digest")
        or receipt["collision_snapshot"]["snapshot_sha256"]
        != authority.get("collision_snapshot_sha256")
    ):
        raise MissionAdmissionError("canonical_admission_authority_changed")
    return receipt, identity, authority


def _trusted_receipt(current, *, repo_root=REPO_ROOT, os_name=None, environ=None):
    state_root = _trusted_state_root(repo_root, os_name=os_name, environ=environ)
    receipt_id = str(current.get("receipt_id") or "")
    if not __import__("re").fullmatch(r"MAR-[0-9A-F]{64}", receipt_id):
        raise MissionAdmissionError("canonical_admission_identity_invalid")
    receipt_file = state_root / "mission-admission-receipts" / f"{receipt_id}.json"
    key_file = state_root / "validation-receipt.key"
    if receipt_file.is_symlink() or key_file.is_symlink():
        raise MissionAdmissionError("validation_authority_symlink_denied")
    try:
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
        key = key_file.read_bytes()
    except (OSError, json.JSONDecodeError) as exc:
        raise MissionAdmissionError("trusted_validation_authority_unavailable") from exc
    key_sha256 = hashlib.sha256(key).hexdigest()
    if (
        current.get("authority_key_sha256") != key_sha256
        or receipt.get("receipt_id") != receipt_id
    ):
        raise MissionAdmissionError("validation_authority_identity_changed")
    if (os_name or os.name) != "nt" and key_file.stat().st_mode & 0o077:
        raise MissionAdmissionError("validation_authority_permissions_invalid")
    return receipt, key, key_sha256


def _trusted_state_root(repo_root=REPO_ROOT, *, os_name=None, environ=None):
    environ = os.environ if environ is None else environ
    delivered = str(environ.get("CHARLIE_MISSION_ADMISSION_STATE_ROOT") or "").strip()
    if delivered:
        candidate = Path(delivered)
        if not candidate.is_absolute() or candidate.is_symlink():
            raise MissionAdmissionError("trusted_state_root_invalid")
        return candidate.resolve()
    root = Path(repo_root).resolve()
    if root.parent.name == ".charlie_runner":
        return root.parent
    return root / ".charlie_runner"


def _references_trusted_authority(value, environ=None):
    """Deny model-visible reads of the externally staged signing authority."""

    environ = os.environ if environ is None else environ
    serialized = json.dumps(value, default=str).replace("\\", "/").lower()
    protected = {
        "/.aws/",
        "/.config/gh/",
        "/.ssh/",
        "/.charlie_runner/",
        "/.env",
        "/.git/config",
        "/.git/credentials",
        "/.netrc",
        "/.npmrc",
        "/.pypirc",
        ".aws/",
        ".config/gh/",
        ".docker/config.json",
        ".ssh/",
        ".charlie_runner/",
        ".env",
        ".git/config",
        ".git/credentials",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "validation-receipt.key",
        "mission-admission-receipts",
    }
    delivered = str(environ.get("CHARLIE_MISSION_ADMISSION_STATE_ROOT") or "").strip()
    if delivered:
        protected.add(str(Path(delivered).resolve()).replace("\\", "/").lower())
    return any(item and item in serialized for item in protected)


def _cloud_repository_read_path_safe(path, repo_root=REPO_ROOT):
    """Allow Cloud file reads only for tracked, non-secret repository files."""
    raw = str(path or "").strip().replace("\\", "/")
    if not raw or _references_trusted_authority(raw):
        return False
    root = Path(repo_root).resolve()
    candidate = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
    try:
        relative = candidate.relative_to(root).as_posix()
    except ValueError:
        return False
    if not relative or candidate.is_symlink():
        return False
    completed = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "ls-files", "--error-unmatch", "--", relative],
        cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=3, check=False,
    )
    return completed.returncode == 0


def _cloud_read_only_shell_safe(command, *, os_name=None):
    """Narrow managed-VM discovery to Git operations scoped by repository objects."""
    if not _is_read_only_shell(command, os_name=os_name) or _references_trusted_authority(command):
        return False
    try:
        words = [word.strip("\"'") for word in shlex.split(
            str(command), posix=(os_name or os.name) != "nt")]
    except ValueError:
        return False
    executable = _executable_name(words[0])
    normalized = tuple(word.lower() for word in words)
    if normalized == ("pwd",):
        return True
    return normalized in {
        ("git", "status"),
        ("git", "status", "--short"),
        ("git", "status", "--porcelain"),
        ("git", "diff"),
        ("git", "diff", "--check"),
        ("git", "diff", "--stat"),
        ("git", "diff", "--name-only"),
        ("git", "diff", "--cached"),
        ("git", "diff", "--staged"),
        ("git", "rev-parse", "head"),
        ("git", "rev-parse", "--show-toplevel"),
        ("git", "ls-files"),
    }


def _remote_authorization(packet, environ):
    endpoint = str(environ.get("CHARLIE_MISSION_ADMISSION_GUARD_URL") or "").strip()
    capability = str(environ.get("CHARLIE_MISSION_ADMISSION_CAPABILITY") or "").strip()
    if not endpoint.startswith("http://127.0.0.1:") or not capability:
        raise MissionAdmissionError("trusted_guard_endpoint_invalid")
    request = url_request.Request(
        endpoint,
        data=json.dumps(packet).encode("utf-8"),
        headers={
            "Authorization": f"Charlie {capability}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with url_request.urlopen(request, timeout=5) as response:
            result = json.loads(response.read(131072))
    except Exception as exc:
        raise MissionAdmissionError("trusted_guard_unavailable") from exc
    if not isinstance(result, dict) or result.get("permission") not in {"allow", "deny"}:
        raise MissionAdmissionError("trusted_guard_response_invalid")
    return result


def _verify_governance_reads(receipt, candidate_head):
    for expected in receipt["governance_reads"]:
        path = expected["path"]
        try:
            blob = _git_text("rev-parse", f"{candidate_head}:{path}")
            content = _git_bytes("show", f"{candidate_head}:{path}")
        except subprocess.SubprocessError as exc:
            raise MissionAdmissionError("admission_governance_changed") from exc
        actual = {
            "git_blob": blob,
            "filesystem_sha256": __import__("hashlib").sha256(content).hexdigest(),
            "byte_count": len(content),
            "physical_line_count": content.count(b"\n"),
        }
        if any(expected.get(key) != value for key, value in actual.items()):
            raise MissionAdmissionError("admission_governance_changed")


def _governance_read_identities(candidate_head):
    rows = []
    for path in BOOTSTRAP_GOVERNANCE_PATHS:
        content = _git_bytes("show", f"{candidate_head}:{path}")
        rows.append({
            "path": path,
            "git_blob": _git_text("rev-parse", f"{candidate_head}:{path}"),
            "filesystem_sha256": hashlib.sha256(content).hexdigest(),
            "byte_count": len(content),
            "physical_line_count": content.count(b"\n"),
            "complete_byte_read": True,
        })
    return rows


def _repository_identity():
    remote = _git_text("config", "--get", "remote.origin.url")
    remote = remote.removesuffix(".git").replace("\\", "/")
    if "github.com/" in remote:
        return remote.split("github.com/", 1)[1]
    if remote.startswith("git@github.com:"):
        return remote.split(":", 1)[1]
    raise MissionAdmissionError("admission_repository_identity_unavailable")


def _validate_paths_and_effects(
    paths, allowed_files, forbidden_files, effect, allowed_effects, forbidden_effects
):
    normalized = {_relative_path(path) for path in paths}
    if "" in normalized:
        raise MissionAdmissionError("admission_path_invalid")
    if not normalized.issubset(set(allowed_files)):
        raise MissionAdmissionError("admission_scope_drift")
    if normalized.intersection(forbidden_files):
        raise MissionAdmissionError("admission_forbidden_path")
    if effect in set(forbidden_effects):
        raise MissionAdmissionError("admission_forbidden_effect")
    if effect not in set(allowed_effects):
        raise MissionAdmissionError("admission_effect_not_allowed")


def _is_read_only_shell(command, *, os_name=None):
    command = str(command or "").strip()
    if not command or any(
        token in command
        for token in (
            "\n", "\r", ">", "<", "|", ";", "&&", "||", "`", "$(",
            "2>", "&>", "\x00",
        )
    ):
        return False
    try:
        words = shlex.split(command, posix=(os_name or os.name) != "nt")
    except ValueError:
        return False
    if not words:
        return False
    words = [word.strip("\"'") for word in words]
    if "=" in words[0] and not words[0].startswith(("./", "/", "\\")):
        return False
    executable = _executable_name(words[0])
    if executable in INTERPRETERS:
        return False
    if executable in READ_ONLY_COMMANDS:
        if executable == "rg" and any(
            item == "--pre" or item.startswith("--pre=")
            or item == "--pre-glob" or item.startswith("--pre-glob=")
            for item in words[1:]
        ):
            return False
        return True
    if executable == "git" and len(words) >= 2:
        subcommand = words[1].lower()
        args = words[2:]
        if subcommand not in READ_ONLY_GIT_SUBCOMMANDS:
            return False
        if any(
            item == "--output" or item.startswith("--output=")
            or item in {"--ext-diff", "--textconv", "--exec"}
            for item in args
        ):
            return False
        if subcommand == "branch":
            mutation_flags = {
                "-d", "-D", "-m", "-M", "-c", "-C", "--delete", "--move",
                "--copy", "--edit-description", "--set-upstream-to",
                "--unset-upstream",
            }
            if any(item in mutation_flags for item in args):
                return False
            return not any(
                not item.startswith("-")
                for item in args
            )
        if subcommand == "remote":
            return not args or args[0] in {"-v", "--verbose", "show", "get-url"}
        if subcommand == "hash-object":
            return "-w" not in args and "--write" not in args
        if subcommand == "config":
            return bool(args) and args[0] in {
                "--get", "--get-all", "--get-regexp", "--list",
                "--show-origin", "--show-scope",
            }
        if subcommand == "cat-file" and any(
            item == "--filters" or item.startswith("--filters=")
            for item in args
        ):
            return False
        return True
    return False


def _executable_name(value):
    name = str(value or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _tool_target_path(packet):
    event = str(packet.get("hook_event_name") or "")
    if event == "afterFileEdit":
        return _relative_path(packet.get("file_path"))
    tool_input = packet.get("tool_input") if isinstance(packet.get("tool_input"), dict) else {}
    for key in ("path", "file_path", "target_file", "target_notebook"):
        if tool_input.get(key):
            return _relative_path(tool_input[key])
    if str(packet.get("tool_name") or "").strip().lower() == "applypatch":
        patch = next(
            (
                value
                for key, value in tool_input.items()
                if key in {"patch", "input", "content"}
                and isinstance(value, str)
            ),
            "",
        )
        targets = __import__("re").findall(
            r"^\*\*\* (?:Add|Update) File: (.+)$",
            patch,
            flags=__import__("re").MULTILINE,
        )
        normalized = sorted({_relative_path(path) for path in targets})
        if len(normalized) == 1 and normalized[0]:
            return normalized[0]
    return ""


def _audit_after_file_edit(
    packet,
    *,
    environ=None,
    authority_reader=None,
    repo_root=REPO_ROOT,
    os_name=None,
):
    path = _tool_target_path(packet)
    if not path:
        raise MissionAdmissionError("after_file_edit_path_missing")
    _require_admission(
        {
            "hook_event_name": "preToolUse",
            "tool_name": "Write",
            "tool_input": {"path": path},
        },
        "repository_file_write",
        environ=environ,
        authority_reader=authority_reader,
        repo_root=repo_root,
        os_name=os_name,
    )


def _changed_files(base, head):
    output = _git_text(
        "diff", "--no-ext-diff", "--no-textconv", "--name-only",
        "--diff-filter=ACMRDTUXB", base, head, "--",
    )
    return sorted({line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()})


def _worktree_changed_files(base):
    tracked = {
        line.strip().replace("\\", "/")
        for line in _git_text("diff", "--name-only", base, "--").splitlines()
        if line.strip()
    }
    status = _git_bytes(
        "status", "--porcelain=v1", "--untracked-files=all"
    ).decode("utf-8", errors="strict")
    for line in status.splitlines():
        candidate = line[3:] if len(line) > 3 else ""
        if " -> " in candidate:
            candidate = candidate.split(" -> ", 1)[1]
        candidate = candidate.strip().strip('"').replace("\\", "/")
        if candidate:
            tracked.add(candidate)
    return sorted(tracked)


def _commit(value):
    commit = _git_text("rev-parse", f"{value}^{{commit}}")
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise MissionAdmissionError("admission_commit_identity_invalid")
    return commit


def _relative_path(value):
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    path = Path(text)
    if path.is_absolute():
        try:
            text = str(path.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
        except ValueError:
            return ""
    if text.startswith("../") or "/../" in text or text == "..":
        return ""
    return text


def _git_text(*args):
    return _git_bytes(*args).decode("utf-8", errors="strict").strip()


def _git_bytes(*args):
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def _allow(reason):
    _emit({"permission": "allow", "agent_message": reason})
    return 0


def _deny(reason):
    _emit({
        "permission": "deny",
        "user_message": "READMISSION_REQUIRED",
        "agent_message": f"READMISSION_REQUIRED: {reason}",
    })
    return 0


def _emit(value):
    print(json.dumps(value, sort_keys=True))


def _reason(exc):
    text = str(exc).strip()
    return text or exc.__class__.__name__


if __name__ == "__main__":
    raise SystemExit(main())
