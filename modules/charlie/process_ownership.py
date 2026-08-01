"""Fail-closed process ownership records and termination authorization."""

import base64
import hashlib
import json
import os
import re
import secrets
import shlex
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


REQUIRED_IDENTITY_FIELDS = (
    "pid", "creation_time", "executable_path", "command_fingerprint",
    "parent_pid", "runner_generation", "mission_id", "execution_id", "ownership_type",
    "revision", "startup_nonce",
)

TERMINATION_ENABLE_ENV = "CHARLIE_PROCESS_TERMINATION_ENABLED"
TERMINATION_ENABLE_VALUE = "I_UNDERSTAND_THIS_CAN_TERMINATE_PROCESSES"
TEST_ISOLATION_ENV = "CHARLIE_TEST_ISOLATION"
_SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")
_WINDOWS_CONSOLE_HOST = "conhost.exe"
_WINDOWS_CONSOLE_HOST_COMMAND = re.compile(
    r'^(?:\\\\\?\\|\\\?\?\\)?(?:"?[^"]*\\)?conhost\.exe"?(?:\s+(?:0x[0-9a-f]+|'
    r'0xffffffff|-forcev1|--headless|[0-9]+))*\s*$',
    re.IGNORECASE,
)


def process_termination_enabled(environ=None):
    """Require an explicit capability grant in addition to ownership proof."""
    values = os.environ if environ is None else environ
    if str(values.get(TEST_ISOLATION_ENV) or "") == "1":
        return False
    return str(values.get(TERMINATION_ENABLE_ENV) or "") == TERMINATION_ENABLE_VALUE


def normalize_command_fingerprint(command):
    normalized = " ".join(str(command or "").split()).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def generate_controller_signing_key(bits=2048):
    """Generate an ephemeral RSA key; only the public half enters child envs."""
    e = 65537
    while True:
        p = _probable_prime(bits // 2)
        q = _probable_prime(bits // 2)
        if p == q:
            continue
        phi = (p - 1) * (q - 1)
        if phi % e:
            n = p * q
            return {"n": n, "d": pow(e, -1, phi)}, f"{n:x}:{e:x}"


def sign_controller_acknowledgement(payload, private_key):
    n = int(private_key["n"])
    d = int(private_key["d"])
    encoded = _signature_encoding(payload, (n.bit_length() + 7) // 8)
    return pow(int.from_bytes(encoded, "big"), d, n).to_bytes(
        (n.bit_length() + 7) // 8, "big"
    ).hex()


def verify_controller_acknowledgement(payload, signature, public_key):
    try:
        n_hex, e_hex = str(public_key or "").split(":", 1)
        n, e = int(n_hex, 16), int(e_hex, 16)
        size = (n.bit_length() + 7) // 8
        actual = pow(int(str(signature or ""), 16), e, n).to_bytes(size, "big")
        return secrets.compare_digest(actual, _signature_encoding(payload, size))
    except (TypeError, ValueError, OverflowError):
        return False


def _signature_encoding(payload, size):
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest_info = _SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(canonical).digest()
    padding = b"\xff" * (size - len(digest_info) - 3)
    if len(padding) < 8:
        raise ValueError("controller_signing_key_too_small")
    return b"\x00\x01" + padding + b"\x00" + digest_info


def _probable_prime(bits):
    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if _is_probable_prime(candidate):
            return candidate


def _is_probable_prime(value, rounds=32):
    small = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    if value in small:
        return True
    if any(value % prime == 0 for prime in small):
        return False
    exponent, shifts = value - 1, 0
    while exponent % 2 == 0:
        shifts += 1
        exponent //= 2
    for _ in range(rounds):
        base = secrets.randbelow(value - 3) + 2
        witness = pow(base, exponent, value)
        if witness in (1, value - 1):
            continue
        for _step in range(shifts - 1):
            witness = pow(witness, 2, value)
            if witness == value - 1:
                break
        else:
            return False
    return True


def make_ownership_record(
    process,
    runner_generation,
    mission_id,
    execution_id,
    ownership_type,
    revision=None,
    startup_nonce=None,
    process_role=None,
):
    if not isinstance(process, dict):
        return {}
    command = process.get("command_line") or process.get("command")
    return {
        "pid": process.get("pid"),
        "creation_time": str(process.get("creation_time") or ""),
        "executable_path": _normalize_path(process.get("executable_path")),
        "command_fingerprint": normalize_command_fingerprint(command),
        "parent_pid": process.get("parent_pid"),
        "runner_generation": str(runner_generation or ""),
        "mission_id": str(mission_id or ""),
        "execution_id": str(execution_id or ""),
        "ownership_type": str(ownership_type or ""),
        "revision": str(revision or runner_generation or ""),
        "startup_nonce": str(startup_nonce or runner_generation or ""),
        "process_role": str(process_role or ownership_type or ""),
    }


def make_process_tree_record(root_record, member_records, runner_generation):
    """Persist one logical launcher/interpreter tree without raw commands."""
    root = dict(root_record) if isinstance(root_record, dict) else {}
    members = [
        dict(item) for item in (member_records or [])
        if isinstance(item, dict) and item.get("pid")
    ]
    if root and not any(item.get("pid") == root.get("pid") for item in members):
        members.insert(0, root)
    return {
        "version": "charlie_process_tree_v1",
        "runner_generation": str(runner_generation or ""),
        "root_pid": root.get("pid"),
        "root": root,
        "members": members,
    }


def process_tree_identity_digest(tree):
    """Hash the stable, security-relevant identity of an observed tree."""
    tree = tree if isinstance(tree, dict) else {}
    stable_fields = (
        "pid", "parent_pid", "creation_time", "executable_path",
        "command_fingerprint", "runner_generation", "mission_id",
        "execution_id", "ownership_type", "revision", "startup_nonce",
        "process_role",
    )
    members = [
        {field: item.get(field) for field in stable_fields}
        for item in (tree.get("members") or [])
        if isinstance(item, dict)
    ]
    members.sort(key=lambda item: int(item.get("pid") or 0))
    payload = {
        "version": str(tree.get("version") or ""),
        "runner_generation": str(tree.get("runner_generation") or ""),
        "root_pid": int(tree.get("root_pid") or 0),
        "root": {
            field: (tree.get("root") or {}).get(field)
            for field in stable_fields
        },
        "members": members,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def validate_process_tree(
    tree,
    expected,
    inspect_process,
    current_pid=None,
    require_descendant=False,
    allow_current_descendant=False,
):
    """Validate every identity and bind every interpreter to the launcher."""
    if not isinstance(tree, dict) or tree.get("version") != "charlie_process_tree_v1":
        return _deny("process_tree_metadata_missing")
    root = tree.get("root") if isinstance(tree.get("root"), dict) else {}
    members = tree.get("members") if isinstance(tree.get("members"), list) else []
    if not root or not members:
        return _deny("process_tree_metadata_incomplete")
    root_decision = validate_termination(
        root,
        expected,
        inspect_process,
        current_pid=current_pid,
        allow_current_descendant=allow_current_descendant,
    )
    if not root_decision["authorized"]:
        return _deny(f"root_{root_decision['reason']}")
    root_pid = int(root["pid"])
    validated = []
    for member in members:
        decision = validate_termination(
            member,
            expected,
            inspect_process,
            current_pid=current_pid,
            allow_current_descendant=allow_current_descendant,
            allow_console_host_tree_member=(
                str(member.get("process_role") or "").endswith(
                    "_console_host"
                )
            ),
        )
        if not decision["authorized"]:
            return _deny(f"member_{member.get('pid')}_{decision['reason']}")
        current = inspect_process(int(member["pid"]))
        if int(member["pid"]) != root_pid:
            ancestry = current.get("ancestry") if isinstance(current, dict) else []
            ancestor_pids = {
                int(item.get("pid") or -1)
                for item in ancestry or []
                if isinstance(item, dict)
            }
            if root_pid not in ancestor_pids:
                return _deny(f"member_{member.get('pid')}_not_descendant_of_root")
        validated.append(int(member["pid"]))
    if require_descendant and len(set(validated)) < 2:
        return _deny("interpreter_descendant_missing")
    return {
        "authorized": True,
        "reason": "logical_process_tree_identity_match",
        "pid": root_pid,
        "member_pids": sorted(set(validated)),
    }


def validate_bootstrap_tree(
    tree,
    *,
    generation,
    revision,
    startup_nonce,
    expected_root_parent_pid=None,
    require_interpreter=True,
):
    """Validate a controller-observed startup tree without trusting its child."""
    if not isinstance(tree, dict) or tree.get("version") != "charlie_process_tree_v1":
        return _deny("ownership_identity_incomplete:process_tree")
    root = tree.get("root") if isinstance(tree.get("root"), dict) else {}
    members = tree.get("members") if isinstance(tree.get("members"), list) else []
    if not root:
        return _deny("ownership_identity_incomplete:root")
    if not members:
        return _deny("ownership_identity_incomplete:members")
    for label, record in [("root", root), *[(f"member_{index}", item) for index, item in enumerate(members)]]:
        if not isinstance(record, dict):
            return _deny(f"ownership_identity_incomplete:{label}")
        for field in REQUIRED_IDENTITY_FIELDS:
            if record.get(field) in (None, ""):
                return _deny(f"ownership_identity_incomplete:{label}.{field}")
        if not str(record.get("process_role") or ""):
            return _deny(f"ownership_identity_incomplete:{label}.process_role")
        if str(record.get("runner_generation") or "") != str(generation or ""):
            return _deny(f"stale_generation:{label}")
        if str(record.get("revision") or "") != str(revision or ""):
            return _deny(f"revision_mismatch:{label}")
        if str(record.get("startup_nonce") or "") != str(startup_nonce or ""):
            return _deny(f"startup_nonce_mismatch:{label}")
    try:
        root_pid = int(root["pid"])
        root_parent_pid = int(root["parent_pid"])
    except (TypeError, ValueError):
        return _deny("ownership_identity_incomplete:root.pid")
    if expected_root_parent_pid is not None and root_parent_pid != int(expected_root_parent_pid):
        return _deny("root_parent_pid_mismatch")
    member_pids = {int(item["pid"]) for item in members}
    if len(member_pids) != len(members):
        return _deny("ownership_identity_incomplete:duplicate_pid")
    if root_pid not in member_pids:
        return _deny("ownership_identity_incomplete:root_member")
    canonical_root = next(
        (item for item in members if int(item.get("pid") or -1) == root_pid),
        {},
    )
    root_fields = set(REQUIRED_IDENTITY_FIELDS) | {"process_role"}
    if any(root.get(field) != canonical_root.get(field) for field in root_fields):
        return _deny("root_member_identity_mismatch")
    descendants = [item for item in members if int(item["pid"]) != root_pid]
    if (
        require_interpreter
        and not descendants
        and not str(root.get("process_role") or "").endswith("_interpreter")
    ):
        return _deny("ownership_identity_incomplete:interpreter")
    known_pids = set(member_pids)
    for member in descendants:
        if int(member["parent_pid"]) not in known_pids:
            return _deny(f"parentage_mismatch:member_{member['pid']}")
    return {
        "authorized": True,
        "reason": "ownership_bootstrap_identity_complete",
        "pid": root_pid,
        "member_pids": sorted(member_pids),
        "generation": str(generation),
        "revision": str(revision),
        "startup_nonce": str(startup_nonce),
    }


def validate_live_bootstrap_tree(
    tree,
    *,
    generation,
    revision,
    startup_nonce,
    allowed_descendant_tree=None,
):
    """Revalidate a persisted bootstrap tree against current OS identities."""
    structural = validate_bootstrap_tree(
        tree,
        generation=generation,
        revision=revision,
        startup_nonce=startup_nonce,
        require_interpreter=True,
    )
    if not structural["authorized"]:
        return structural
    members = tree.get("members") or []
    root_pid = int((tree.get("root") or {}).get("pid") or -1)
    live_processes, windows_snapshot = inspect_processes_with_snapshot(
        [record.get("pid") for record in members if isinstance(record, dict)]
    )
    for index, record in enumerate(members):
        current = live_processes.get(int(record.get("pid") or 0))
        label = f"member_{index}"
        if not isinstance(current, dict) or current.get("inspection_complete") is False:
            detail = str((current or {}).get("inspection_reason") or "incomplete")
            return _deny(f"live_identity_inspection_{detail}:{label}")
        checks = {
            "pid": int(current.get("pid") or -1) == int(record.get("pid") or -2),
            "creation_time": str(current.get("creation_time") or "") == str(record.get("creation_time") or ""),
            "executable_path": _normalize_path(current.get("executable_path")) == _normalize_path(record.get("executable_path")),
            "command_fingerprint": normalize_command_fingerprint(
                current.get("command_line") or current.get("command")
            ) == str(record.get("command_fingerprint") or ""),
            "parent_pid": int(current.get("parent_pid") or -1) == int(record.get("parent_pid") or -2),
        }
        mismatch = next((field for field, matches in checks.items() if not matches), "")
        if mismatch:
            return _deny(f"live_identity_{mismatch}_mismatch:{label}")
        if int(record.get("pid") or -1) != root_pid:
            ancestry = current.get("ancestry")
            if not isinstance(ancestry, list) or root_pid not in {
                int(item.get("pid") or -1)
                for item in ancestry
                if isinstance(item, dict)
            }:
                return _deny(f"live_identity_parentage_mismatch:{label}")
    live_rows = (
        _process_tree_rows_from_snapshot(root_pid, windows_snapshot)
        if windows_snapshot is not None
        else _inspect_process_descendants(root_pid)
    )
    live_identities = {
        (int(row.get("pid") or -1), str(row.get("creation_time") or ""))
        for row in live_rows
        if isinstance(row, dict)
    }
    recorded_identities = {
        (int(record.get("pid") or -1), str(record.get("creation_time") or ""))
        for record in members
        if isinstance(record, dict)
    }
    allowed_identities = {
        (int(record.get("pid") or -1), str(record.get("creation_time") or ""))
        for record in (
            (allowed_descendant_tree or {}).get("members") or []
        )
        if isinstance(record, dict)
    }
    if allowed_identities:
        live_identities -= allowed_identities
    if live_identities != recorded_identities:
        return _deny("live_identity_descendant_set_mismatch")
    chronology = _validate_process_creation_chronology(live_rows, root_pid)
    if chronology:
        return _deny(chronology)
    return {
        **structural,
        "reason": "live_ownership_bootstrap_identity_match",
    }


def observe_process_tree(
    root_pid,
    *,
    generation,
    revision,
    startup_nonce,
    expected_script="",
    expected_root_executable="",
    expected_interpreter_executable="",
    expected_root_parent_pid=None,
    process_role_prefix="process",
    timeout_seconds=10,
    poll_seconds=0.1,
    sleep_fn=time.sleep,
):
    """Observe a launcher/interpreter tree externally from its controller."""
    deadline = time.monotonic() + max(0, float(timeout_seconds))
    last_reason = "ownership_identity_incomplete:root"
    previous_candidate_digest = ""
    while time.monotonic() <= deadline:
        rows = _inspect_process_descendants(root_pid)
        records = [
            make_ownership_record(
                row,
                generation,
                "charlie-control",
                generation,
                "charlie_runner",
                revision=revision,
                startup_nonce=startup_nonce,
                process_role=_observed_process_role(
                    row,
                    root_pid=root_pid,
                    expected_script=expected_script,
                    expected_interpreter_executable=expected_interpreter_executable,
                    process_role_prefix=process_role_prefix,
                ),
            )
            for row in rows
            if isinstance(row, dict)
        ]
        root = next((item for item in records if int(item.get("pid") or -1) == int(root_pid)), {})
        tree = make_process_tree_record(root, records, generation)
        decision = validate_bootstrap_tree(
            tree,
            generation=generation,
            revision=revision,
            startup_nonce=startup_nonce,
            expected_root_parent_pid=(
                os.getpid()
                if expected_root_parent_pid is None
                else expected_root_parent_pid
            ),
            require_interpreter=True,
        )
        if decision["authorized"]:
            chronology = _validate_process_creation_chronology(rows, root_pid)
            if chronology:
                last_reason = chronology
                sleep_fn(poll_seconds)
                continue
            if str(root.get("process_role") or "") not in {
                f"{process_role_prefix}_launcher",
                f"{process_role_prefix}_interpreter",
            }:
                last_reason = "root_process_role_mismatch"
                sleep_fn(poll_seconds)
                continue
            row_by_pid = {
                int(row.get("pid") or -1): row
                for row in rows
                if isinstance(row, dict)
            }
            descendants = [
                item for item in records
                if int(item.get("pid") or -1) != int(root_pid)
            ]
            interpreters = [
                item for item in records
                if str(item.get("process_role") or "")
                == f"{process_role_prefix}_interpreter"
            ]
            wrappers = [
                item for item in descendants
                if str(item.get("process_role") or "")
                == f"{process_role_prefix}_console_host"
            ]
            unexpected = next(
                (
                    item for item in descendants
                    if item not in interpreters and item not in wrappers
                ),
                None,
            )
            if unexpected is not None:
                last_reason = (
                    f"command_role_identity_mismatch:{unexpected.get('pid')}"
                )
                sleep_fn(poll_seconds)
                continue
            if expected_script and len(interpreters) != 1:
                last_reason = "interpreter_process_role_ambiguous"
                sleep_fn(poll_seconds)
                continue
            invalid_interpreter = next(
                (
                    item for item in interpreters
                    if expected_script
                    and not _valid_interpreter_command_role(
                        row_by_pid.get(int(item.get("pid") or -1), {}),
                        expected_script=expected_script,
                        expected_interpreter_executable=(
                            expected_interpreter_executable
                        ),
                    )
                ),
                None,
            )
            if invalid_interpreter is not None:
                last_reason = (
                    f"interpreter_identity_mismatch:"
                    f"{invalid_interpreter.get('pid')}"
                )
                sleep_fn(poll_seconds)
                continue
            wrapper_parent_pids = {
                int(root_pid),
                *[int(item.get("pid") or -1) for item in interpreters],
            }
            wrapper_parent_counts = {}
            for item in wrappers:
                row = row_by_pid.get(int(item.get("pid") or -1), {})
                parent_pid = int(row.get("parent_pid") or -1)
                wrapper_parent_counts[parent_pid] = (
                    wrapper_parent_counts.get(parent_pid, 0) + 1
                )
            invalid_wrapper = next(
                (
                    item for item in wrappers
                    if not _valid_windows_console_host_wrapper(
                        row_by_pid.get(int(item.get("pid") or -1), {}),
                        allowed_parent_pids=wrapper_parent_pids,
                        expected_script=expected_script,
                    )
                    or wrapper_parent_counts.get(
                        int(
                            row_by_pid.get(
                                int(item.get("pid") or -1), {}
                            ).get("parent_pid")
                            or -1
                        ),
                        0,
                    )
                    != 1
                ),
                None,
            )
            if invalid_wrapper is not None:
                last_reason = (
                    f"console_host_identity_mismatch:{invalid_wrapper.get('pid')}"
                )
                sleep_fn(poll_seconds)
                continue
            root_row = next(
                (row for row in rows if int(row.get("pid") or -1) == int(root_pid)),
                {},
            )
            if expected_root_executable and _normalize_path(
                root_row.get("executable_path")
            ) != _normalize_path(expected_root_executable):
                last_reason = "root_executable_identity_mismatch"
                sleep_fn(poll_seconds)
                continue
            if expected_script:
                command_role_rows = [
                    root_row,
                    *[
                        row_by_pid.get(int(item.get("pid") or -1), {})
                        for item in interpreters
                    ],
                ]
                missing_role = next(
                    (
                        row for row in command_role_rows
                        if not _command_has_exact_script(
                            row.get("command_line"),
                            expected_script,
                        )
                    ),
                    None,
                )
                if missing_role is not None:
                    last_reason = f"command_role_identity_mismatch:{missing_role.get('pid')}"
                else:
                    candidate_digest = process_tree_identity_digest(tree)
                    if candidate_digest == previous_candidate_digest:
                        return {
                            "success": True,
                            "tree": tree,
                            "validation": decision,
                        }
                    previous_candidate_digest = candidate_digest
                    last_reason = "process_tree_identity_not_stable"
            else:
                candidate_digest = process_tree_identity_digest(tree)
                if candidate_digest == previous_candidate_digest:
                    return {
                        "success": True,
                        "tree": tree,
                        "validation": decision,
                    }
                previous_candidate_digest = candidate_digest
                last_reason = "process_tree_identity_not_stable"
        else:
            last_reason = decision["reason"]
        sleep_fn(poll_seconds)
    return {"success": False, "reason": last_reason, "tree": tree if "tree" in locals() else {}}


def _observed_process_role(
    row,
    *,
    root_pid,
    expected_script,
    expected_interpreter_executable,
    process_role_prefix,
):
    """Classify one observed member without conflating wrappers and interpreters."""
    if int(row.get("pid") or -1) == int(root_pid):
        if expected_script and _valid_interpreter_command_role(
            row,
            expected_script=expected_script,
            expected_interpreter_executable=expected_interpreter_executable,
        ):
            return f"{process_role_prefix}_interpreter"
        return f"{process_role_prefix}_launcher"
    if _looks_like_windows_console_host(row):
        return f"{process_role_prefix}_console_host"
    if not expected_script or _valid_interpreter_command_role(
        row,
        expected_script=expected_script,
        expected_interpreter_executable=expected_interpreter_executable,
    ):
        return f"{process_role_prefix}_interpreter"
    return f"{process_role_prefix}_unexpected"


def _looks_like_windows_console_host(row):
    executable = str(row.get("executable_path") or "").replace("/", "\\")
    name = str(row.get("name") or executable.rsplit("\\", 1)[-1]).casefold()
    system_root = str(
        os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows"
    ).replace("/", "\\").rstrip("\\")
    expected = f"{system_root}\\System32\\{_WINDOWS_CONSOLE_HOST}"
    return (
        name == _WINDOWS_CONSOLE_HOST
        and _canonical_windows_path(executable)
        == _canonical_windows_path(expected)
    )


def _valid_windows_console_host_wrapper(
    row,
    *,
    allowed_parent_pids,
    expected_script,
):
    """Accept only the bounded Windows console host attached to this launcher."""
    if not _looks_like_windows_console_host(row):
        return False
    if int(row.get("parent_pid") or -1) not in {
        int(pid) for pid in allowed_parent_pids
    }:
        return False
    command = " ".join(str(row.get("command_line") or "").split())
    if not command or not _WINDOWS_CONSOLE_HOST_COMMAND.fullmatch(command):
        return False
    executable = str(row.get("executable_path") or "").replace("/", "\\")
    command_end = command.casefold().find(_WINDOWS_CONSOLE_HOST)
    if command_end < 0:
        return False
    command_executable = command[:command_end + len(_WINDOWS_CONSOLE_HOST)]
    command_executable = command_executable.strip('"')
    for prefix in ("\\\\?\\", "\\??\\"):
        if command_executable.startswith(prefix):
            command_executable = command_executable[len(prefix):]
            break
    if command_executable.casefold() != executable.casefold():
        return False
    if expected_script and str(expected_script).casefold() in command.casefold():
        return False
    return True


def _valid_interpreter_command_role(
    row,
    *,
    expected_script,
    expected_interpreter_executable,
):
    executable = _canonical_windows_path(row.get("executable_path"))
    expected_executable = _canonical_windows_path(
        expected_interpreter_executable
    )
    if expected_executable and executable != expected_executable:
        return False
    name = executable.rsplit("\\", 1)[-1]
    if name not in {"python.exe", "pythonw.exe"}:
        return False
    return _command_has_exact_script(row.get("command_line"), expected_script)


def _command_has_exact_script(command, expected_script):
    tokens = _windows_command_tokens(command)
    if len(tokens) < 2:
        return False
    return (
        _canonical_windows_path(tokens[1])
        == _canonical_windows_path(expected_script)
    )


def _windows_command_tokens(command):
    try:
        return [
            str(token).strip('"')
            for token in shlex.split(str(command or ""), posix=False)
        ]
    except ValueError:
        return []


def _canonical_windows_path(value):
    path = str(value or "").strip().strip('"').replace("/", "\\")
    for prefix in ("\\\\?\\", "\\??\\"):
        if path.startswith(prefix):
            path = path[len(prefix):]
            break
    return os.path.normpath(path).casefold() if path else ""


def _validate_process_creation_chronology(rows, root_pid):
    rows = [row for row in (rows or []) if isinstance(row, dict)]
    by_pid = {int(row.get("pid") or -1): row for row in rows}
    if int(root_pid) not in by_pid:
        return "ownership_identity_incomplete:root"
    for row in rows:
        pid = int(row.get("pid") or -1)
        if pid == int(root_pid):
            continue
        parent = by_pid.get(int(row.get("parent_pid") or -1))
        if not parent:
            return f"parentage_mismatch:member_{pid}"
        child_created = _parse_creation_identity(row.get("creation_time"))
        parent_created = _parse_creation_identity(parent.get("creation_time"))
        if child_created is None or parent_created is None:
            return f"creation_identity_invalid:member_{pid}"
        if child_created[0] != parent_created[0]:
            return f"creation_identity_domain_mismatch:member_{pid}"
        if child_created[1] < parent_created[1]:
            return f"creation_identity_precedes_parent:member_{pid}"
    return ""


def _parse_creation_identity(value):
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return ("process_start_ticks", int(text))
    dmtf = re.fullmatch(
        r"(\d{14})\.(\d{6})([+-])(\d{3})",
        text,
    )
    if dmtf:
        try:
            local = datetime.strptime(
                f"{dmtf.group(1)}.{dmtf.group(2)}",
                "%Y%m%d%H%M%S.%f",
            )
            minutes = int(dmtf.group(4))
            if dmtf.group(3) == "-":
                minutes = -minutes
            parsed = local.replace(
                tzinfo=timezone(timedelta(minutes=minutes))
            ).astimezone(timezone.utc)
            return ("wall_clock", parsed.timestamp())
        except (ValueError, OverflowError):
            return None
    for parser in (
        lambda item: datetime.fromisoformat(item.replace("Z", "+00:00")),
        lambda item: datetime.strptime(item, "%m/%d/%Y %H:%M:%S").replace(
            tzinfo=timezone.utc
        ),
        lambda item: datetime.strptime(item, "%Y%m%d%H%M%S.%f%z"),
    ):
        try:
            parsed = parser(text)
            parsed = (
                parsed.replace(tzinfo=timezone.utc)
                if parsed.tzinfo is None
                else parsed.astimezone(timezone.utc)
            )
            return ("wall_clock", parsed.timestamp())
        except ValueError:
            continue
    return None


def _inspect_process_descendants(root_pid):
    if os.name != "nt":
        root = inspect_process(root_pid)
        if not isinstance(root, dict):
            return []
        rows = [root]
        for proc_dir in Path("/proc").iterdir():
            if not proc_dir.name.isdigit() or int(proc_dir.name) == int(root_pid):
                continue
            try:
                row = inspect_process(int(proc_dir.name))
            except (OSError, ValueError, TypeError):
                continue
            ancestry = row.get("ancestry") if isinstance(row, dict) else []
            if any(int(item.get("pid") or -1) == int(root_pid) for item in ancestry if isinstance(item, dict)):
                rows.append(row)
        return rows
    return _process_tree_rows_from_snapshot(
        root_pid,
        _windows_process_snapshot(),
    )


def _process_tree_rows_from_snapshot(root_pid, all_rows):
    """Return one process tree from an already-consistent OS snapshot."""
    ids = {int(root_pid)}
    changed = True
    while changed:
        changed = False
        for row in all_rows:
            if (
                int(row.get("parent_pid") or -1) in ids
                and int(row.get("pid") or -1) not in ids
            ):
                ids.add(int(row["pid"]))
                changed = True
    return [row for row in all_rows if int(row.get("pid") or -1) in ids]


def validate_termination(
    record,
    expected,
    inspect_process,
    current_pid=None,
    allow_current_descendant=False,
    allow_console_host_tree_member=False,
):
    """Authorize only a complete, exact, non-interactive disposable identity."""
    if not isinstance(record, dict):
        return _deny("corrupt_metadata")
    if any(field not in record or record.get(field) in (None, "") for field in REQUIRED_IDENTITY_FIELDS):
        return _deny("missing_identity_metadata")
    try:
        pid = int(record["pid"])
        parent_pid = int(record["parent_pid"])
    except (TypeError, ValueError):
        return _deny("corrupt_metadata")
    if pid <= 0 or parent_pid < 0:
        return _deny("corrupt_metadata")
    expected = expected if isinstance(expected, dict) else {}
    for field in ("runner_generation", "mission_id", "execution_id", "ownership_type"):
        if not expected.get(field) or record.get(field) != expected.get(field):
            return _deny(f"{field}_mismatch")
    try:
        current = inspect_process(pid)
    except Exception:
        return _deny("process_inspection_failed")
    if not isinstance(current, dict):
        return _deny("pid_not_found")
    if current.get("inspection_complete") is False:
        return _deny("process_inspection_failed")
    if int(current.get("pid") or -1) != pid:
        return _deny("pid_reused")
    if str(current.get("creation_time") or "") != str(record["creation_time"]):
        return _deny("creation_time_mismatch")
    if _normalize_path(current.get("executable_path")) != _normalize_path(record["executable_path"]):
        return _deny("executable_mismatch")
    if normalize_command_fingerprint(current.get("command_line") or current.get("command")) != record["command_fingerprint"]:
        return _deny("command_fingerprint_mismatch")
    if int(current.get("parent_pid") or -1) != parent_pid:
        return _deny("parent_pid_mismatch")
    ancestry = current.get("ancestry")
    if not isinstance(ancestry, list):
        return _deny("process_inspection_failed")
    if _protected(current):
        console_host_member = bool(
            allow_console_host_tree_member
            and str(record.get("process_role") or "").endswith(
                "_console_host"
            )
            and _valid_windows_console_host_wrapper(
                current,
                allowed_parent_pids={parent_pid},
                expected_script="",
            )
        )
        if not console_host_member:
            return _deny("protected_process_boundary")
    protected_pids = {int(current_pid or os.getpid())}
    for item in current.get("current_process_ancestry", []):
        if isinstance(item, dict) and str(item.get("pid") or "").isdigit():
            protected_pids.add(int(item["pid"]))
    ancestry_pids = {
        int(item.get("pid") or -1)
        for item in ancestry
        if isinstance(item, dict)
    }
    if allow_current_descendant:
        starter_pid = int(current_pid or os.getpid())
        ancestry_before_starter = []
        for item in ancestry:
            if not isinstance(item, dict):
                continue
            if int(item.get("pid") or -1) == starter_pid:
                break
            ancestry_before_starter.append(item)
        if any(_protected(item) for item in ancestry_before_starter):
            return _deny("protected_process_boundary")
    elif any(_protected(item) for item in ancestry if isinstance(item, dict)):
        return _deny("protected_process_boundary")
    if pid in protected_pids:
        return _deny("current_process_ancestry")
    intersects_current = bool(ancestry_pids & protected_pids)
    if intersects_current and not allow_current_descendant:
        return _deny("current_process_ancestry")
    if allow_current_descendant and int(current_pid or os.getpid()) not in ancestry_pids:
        return _deny("not_current_process_descendant")
    if record["ownership_type"] not in {"charlie_runner", "charlie_worker", "charlie_agent"}:
        return _deny("ownership_ambiguous")
    return {"authorized": True, "reason": "identity_match", "pid": pid}


def inspect_process(pid):
    """Inspect a process and its ancestry. Any partial result is unusable."""
    if os.name != "nt":
        try:
            return _inspect_proc(pid)
        except OSError:
            # A process can exit between the caller's liveness check and the
            # first /proc read. Treat the now-absent identity as not live;
            # partial identities remain unusable inside _inspect_proc.
            return None
    try:
        rows = _windows_process_snapshot()
        return _inspect_windows_process_from_snapshot(pid, rows)
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, json.JSONDecodeError):
        # Process inspection is a safety aid, never a reason to terminate the
        # supervisor.  Returning no identity keeps termination fail-closed:
        # make_ownership_record produces an unusable record and every later
        # kill authorization is refused until a complete inspection succeeds.
        return None


def inspect_processes(pids):
    """Inspect a bounded PID set from one consistent OS snapshot.

    Windows CIM startup is comparatively expensive and can time out when a
    live-tree validation launches one query per member.  One snapshot both
    avoids that startup failure and prevents identities from being compared
    across different observation instants.
    """
    inspected, _snapshot = inspect_processes_with_snapshot(pids)
    return inspected


def inspect_processes_with_snapshot(pids):
    """Return bounded inspections and the Windows snapshot they came from."""
    normalized = sorted({int(pid or 0) for pid in (pids or []) if int(pid or 0) > 0})
    if os.name != "nt":
        return ({pid: inspect_process(pid) for pid in normalized}, None)
    try:
        rows = _windows_process_snapshot()
        if not rows:
            return ({
                pid: {"inspection_complete": False, "inspection_reason": "snapshot_empty"}
                for pid in normalized
            }, rows)
        return ({
            pid: (
                _inspect_windows_process_from_snapshot(pid, rows)
                or {"inspection_complete": False, "inspection_reason": "target_missing"}
            )
            for pid in normalized
        }, rows)
    except subprocess.TimeoutExpired:
        reason = "snapshot_timeout"
    except json.JSONDecodeError:
        reason = "snapshot_json_invalid"
    except OSError as exc:
        reason = f"snapshot_os_error_{int(getattr(exc, 'winerror', 0) or 0)}"
    except (subprocess.SubprocessError, ValueError, TypeError):
        reason = "snapshot_failed"
    return ({
        pid: {"inspection_complete": False, "inspection_reason": reason}
        for pid in normalized
    }, [])


def _inspect_windows_process_from_snapshot(pid, rows):
    by_pid = {
        int(row["pid"]): row
        for row in (rows or [])
        if isinstance(row, dict) and row.get("pid")
    }
    target = dict(by_pid.get(int(pid)) or {})
    if not target:
        return None
    target["ancestry"] = _snapshot_ancestry(by_pid, target.get("parent_pid"))
    target["current_process_ancestry"] = _snapshot_ancestry(
        by_pid, os.getpid(), include_start=True
    )
    if not target["current_process_ancestry"]:
        return None
    target["inspection_complete"] = True
    return target


def inspect_descendant_processes(root_pid):
    """Return a bounded live descendant snapshot for one exact parent PID."""
    root_pid = int(root_pid or 0)
    if root_pid <= 0:
        return []
    try:
        if os.name == "nt":
            rows = _windows_process_snapshot()
        else:
            rows = []
            for entry in Path("/proc").iterdir():
                if not entry.name.isdigit():
                    continue
                try:
                    rows.append(_proc_row(int(entry.name)))
                except OSError:
                    continue
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    by_parent = {}
    for row in rows:
        if isinstance(row, dict):
            by_parent.setdefault(int(row.get("parent_pid") or 0), []).append(row)
    descendants, pending, seen = [], [root_pid], set()
    while pending:
        parent = pending.pop(0)
        for row in by_parent.get(parent, []):
            pid = int(row.get("pid") or 0)
            if pid <= 0 or pid in seen:
                continue
            seen.add(pid)
            descendants.append(dict(row))
            pending.append(pid)
    return descendants


def _windows_process_snapshot():
    script = (
        "$ErrorActionPreference='Stop';"
        "$selfPid=$PID;"
        "$json=Get-CimInstance Win32_Process|"
        "Where-Object{$_.ProcessId -ne $selfPid -and $_.ParentProcessId -ne $selfPid}|"
        "ForEach-Object{"
        "[pscustomobject]@{pid=[int]$_.ProcessId;parent_pid=[int]$_.ParentProcessId;"
        "creation_time=[string]$_.CreationDate;executable_path=[string]$_.ExecutablePath;"
        "command_line=[string]$_.CommandLine;name=[string]$_.Name}}|"
        "ConvertTo-Json -Compress;"
        "[Console]::Out.Write([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json)))"
    )
    result = None
    for attempt in range(2):
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=8, check=False,
            )
            break
        except subprocess.TimeoutExpired:
            if attempt:
                raise
            # Controller and supervisor can request their startup snapshots in
            # the same second.  Give the already-running CIM query one bounded
            # opportunity to clear; a second timeout remains fail-closed.
            time.sleep(0.1)
    if result is None:
        return []
    raw = str(result.stdout or "").strip()
    if result.returncode or not raw:
        return []
    rows = json.loads(base64.b64decode(raw, validate=True).decode("utf-8"))
    rows = [rows] if isinstance(rows, dict) else rows
    return rows if isinstance(rows, list) else []


def _snapshot_ancestry(by_pid, start_pid, include_start=False):
    result = []
    current = int(start_pid or 0)
    seen = set()
    first = True
    while current > 0 and current not in seen:
        seen.add(current)
        row = by_pid.get(current)
        if not isinstance(row, dict):
            break
        if include_start or not first:
            result.append(dict(row))
        elif not include_start:
            result.append(dict(row))
        current = int(row.get("parent_pid") or 0)
        first = False
    return result


def _inspect_proc(pid):
    target = _proc_row(pid)
    ancestry, ancestry_complete = _proc_ancestry(target["parent_pid"])
    current_ancestry, current_complete = _proc_ancestry(os.getpid(), include_start=True)
    target["ancestry"] = ancestry
    target["current_process_ancestry"] = current_ancestry
    target["inspection_complete"] = bool(
        target.pop("row_complete", True) and ancestry_complete and current_complete
    )
    return target


def _current_ancestry_windows():
    rows = _windows_process_snapshot()
    by_pid = {int(row["pid"]): row for row in rows if row.get("pid")}
    ancestry = _snapshot_ancestry(by_pid, os.getpid(), include_start=True)
    if not ancestry:
        raise OSError("current process ancestry inspection failed")
    return ancestry


def _proc_row(pid):
    pid = int(pid)
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
    row_complete = True
    try:
        command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode().strip()
    except OSError:
        command = ""
        row_complete = False
    try:
        executable_path = str(Path(f"/proc/{pid}/exe").resolve(strict=True))
    except OSError:
        executable_path = ""
        row_complete = False
    try:
        name = Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
    except OSError:
        name = ""
        row_complete = False
    return {"pid": pid, "parent_pid": int(stat[3]), "creation_time": stat[21],
            "executable_path": executable_path, "command_line": command,
            "name": name, "row_complete": row_complete}


def _proc_ancestry(pid, include_start=False):
    rows, seen, complete = [], set(), True
    current = int(pid)
    while current > 0 and current not in seen:
        seen.add(current)
        try:
            row = _proc_row(current)
        except OSError:
            complete = False
            break
        if not row.pop("row_complete", True):
            complete = False
        if include_start or current != int(pid):
            rows.append(row)
        elif not include_start:
            rows.append(row)
        current = int(row.get("parent_pid") or 0)
    return rows, complete


def _protected(process):
    name = Path(str(process.get("name") or process.get("executable_path") or "")).name.casefold()
    command = str(process.get("command_line") or process.get("command") or "").casefold()
    if name == "cursor.exe" or "cursor" in command:
        return True
    if name in {"conhost.exe", "windowsterminal.exe"}:
        return True
    if name in {"powershell.exe", "pwsh.exe", "cmd.exe"}:
        return not any(flag in command for flag in ("-noninteractive", "-file"))
    if name in {"codex.exe", "codex.cmd"}:
        return "exec" not in command or "--json" not in command
    return False


def _normalize_path(value):
    return os.path.normcase(os.path.normpath(str(value or "").strip())) if value else ""


def _deny(reason):
    return {"authorized": False, "reason": reason}
