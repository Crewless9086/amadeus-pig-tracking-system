"""Secret-safe evidence launcher for the scheduled CORE watchdog."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import re
import runpy
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = REPO_ROOT.parent.parent / ".charlie_runner"
EVIDENCE_ROOT = STATE_ROOT / "activation-ledger" / "startup-evidence"
KEY_PATH = STATE_ROOT / "activation-authority.key"
PACKET_PATH = STATE_ROOT / "activation-packet.json"
WATCHDOG_PATH = REPO_ROOT / "scripts" / "charlie_runner_watchdog.py"
VERSION = "charlie_core_startup_evidence_v1"
ACTIVATION_VERSION = "charlie_provider_activation_v2"
AUTHORITY_VERSION = "charlie_provider_activation_authority_v1"
MAX_STDERR_CHARS = 4000
MAX_RECORD_BYTES = 8192
_SECRET_NAME = re.compile(r"(?i)(secret|token|password|credential|api[_-]?key|database_url)")
_URL_CREDENTIAL = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/@\s:]+:[^/@\s]+@")
_BEARER = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")


class _BoundedStderr(io.TextIOBase):
    def __init__(self, prior=None, limit=MAX_STDERR_CHARS):
        self.prior, self.limit, self.tail = prior, int(limit), ""

    def write(self, value):
        text = str(value or "")
        self.tail = (self.tail + text)[-self.limit:]
        # Never forward untrusted exception text to Task Scheduler/process
        # stderr. Redaction cannot be stream-safe when a secret spans writes;
        # only the bounded, sanitized evidence record is published.
        return len(text)

    def flush(self):
        return None


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sanitize_text(value):
    text = _URL_CREDENTIAL.sub(r"\1[REDACTED]@", str(value or ""))
    text = _BEARER.sub("Bearer [REDACTED]", text)
    for name, secret in os.environ.items():
        if _SECRET_NAME.search(name) and secret and len(secret) >= 4:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(
        r"(?i)\b(secret|token|password|credential|api[_-]?key)\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]", text,
    )
    return text[-MAX_STDERR_CHARS:]


def _activation_binding():
    try:
        packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
        key = KEY_PATH.read_bytes()
        value = str(packet.get("activation_id") or "")
        authority = packet.get("authority") if isinstance(packet.get("authority"), dict) else {}
        signature = str(packet.get("packet_hmac_sha256") or "")
        unsigned = {key: item for key, item in packet.items() if key != "packet_hmac_sha256"}
        expected = hmac.new(key, _canonical(unsigned), hashlib.sha256).hexdigest()
        authority_signature = str(authority.get("signature_hmac_sha256") or "")
        unsigned_authority = {
            key: item for key, item in authority.items() if key != "signature_hmac_sha256"
        }
        expected_authority = hmac.new(
            key, _canonical(unsigned_authority), hashlib.sha256
        ).hexdigest()
        expires_at = datetime.fromisoformat(
            str(authority.get("expires_at") or "").replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        ledger = STATE_ROOT / "activation-ledger"
        sealed = any((ledger / name).exists() for name in (
            f"{value}-failure.json", f"{value}-recovery-completed.json",
            f"{value}-reconciled.json", f"{value}-verified.json",
        ))
        if (len(key) >= 32 and packet.get("version") == ACTIVATION_VERSION
                and packet.get("status") == "provider_pending"
                and re.fullmatch(r"[0-9a-f]{32}", value)
                and authority.get("activation_id") == value
                and authority.get("version") == AUTHORITY_VERSION
                and authority.get("execution_mode") == "observe_only"
                and expires_at > datetime.now(timezone.utc)
                and not sealed
                and hmac.compare_digest(signature, expected)):
            if not hmac.compare_digest(authority_signature, expected_authority):
                return "Unknown", ""
            return value, signature
        return "Unknown", ""
    except (OSError, ValueError, TypeError, OverflowError):
        return "Unknown", ""


def _activation_id():
    return _activation_binding()[0]


def _activation_packet_hmac(activation_id):
    if activation_id == "Unknown":
        return ""
    try:
        packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
        key = KEY_PATH.read_bytes()
        signature = str(packet.get("packet_hmac_sha256") or "")
        unsigned = {key: item for key, item in packet.items() if key != "packet_hmac_sha256"}
        expected = hmac.new(key, _canonical(unsigned), hashlib.sha256).hexdigest()
        if (packet.get("activation_id") == activation_id
                and hmac.compare_digest(signature, expected)):
            return signature
    except (OSError, ValueError, TypeError):
        pass
    return ""


def _append_phase(phase, *, activation_id="Unknown", exit_code=None,
                  error_type="", stderr_tail="", activation_packet_hmac_sha256=""):
    record = {
        "version": VERSION,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "activation_id": activation_id,
        "phase": str(phase),
        "pid": os.getpid(),
        "launcher_path": str(Path(__file__).resolve()),
        "launcher_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python_executable": str(Path(sys.executable).resolve()),
        "working_directory": str(Path.cwd().resolve()),
        "action_arguments_sha256": hashlib.sha256(
            "\0".join(sys.argv).encode("utf-8")
        ).hexdigest(),
    }
    if activation_packet_hmac_sha256:
        record["activation_packet_hmac_sha256"] = activation_packet_hmac_sha256
    if exit_code is not None:
        record["exit_code"] = int(exit_code)
    if error_type:
        record["error_type"] = str(error_type)[:160]
    if stderr_tail:
        record["stderr_tail"] = _sanitize_text(stderr_tail)
    try:
        key = KEY_PATH.read_bytes()
        if len(key) < 32:
            return False
        record["record_hmac_sha256"] = hmac.new(
            key, _canonical(record), hashlib.sha256
        ).hexdigest()
        encoded = _canonical(record) + b"\n"
        if len(encoded) > MAX_RECORD_BYTES:
            record.pop("record_hmac_sha256", None)
            record["stderr_tail"] = str(record.get("stderr_tail") or "")[-1000:]
            record["record_hmac_sha256"] = hmac.new(
                key, _canonical(record), hashlib.sha256
            ).hexdigest()
            encoded = _canonical(record) + b"\n"
        if len(encoded) > MAX_RECORD_BYTES:
            return False
        epoch = activation_id if re.fullmatch(r"[0-9a-f]{32}", activation_id) else "unbound"
        evidence_dir = EVIDENCE_ROOT / epoch
        evidence_dir.mkdir(parents=True, exist_ok=True)
        name = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}-{os.getpid()}-{uuid.uuid4().hex}.json"
        path = evidence_dir / name
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb", buffering=0) as stream:
            stream.write(encoded)
        return True
    except (OSError, ValueError, TypeError):
        return False


def main():
    stderr = _BoundedStderr(sys.stderr)
    sys.stderr = stderr
    activation_id, packet_hmac = _activation_binding()
    evidence_binding = {
        "activation_id": activation_id,
        "activation_packet_hmac_sha256": packet_hmac,
    }
    _append_phase("launcher_entered", **evidence_binding)
    try:
        _append_phase(
            "activation_packet_authenticated" if activation_id != "Unknown"
            else "activation_packet_unavailable_or_invalid",
            **evidence_binding,
        )
        if activation_id == "Unknown" or not packet_hmac:
            return 1
        from dotenv import load_dotenv
        load_dotenv(REPO_ROOT.parent.parent / ".env", override=True)
        _append_phase("environment_loaded", **evidence_binding)
        _append_phase("watchdog_entry_started", **evidence_binding)
        sys.argv = [str(WATCHDOG_PATH), "--json"]
        runpy.run_path(str(WATCHDOG_PATH), run_name="__main__")
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        _append_phase("watchdog_entry_exited", **evidence_binding,
                      exit_code=code, stderr_tail=stderr.tail)
        return code
    except BaseException as exc:
        _append_phase("launcher_failed", **evidence_binding, exit_code=1,
                      error_type=exc.__class__.__name__, stderr_tail=stderr.tail)
        return 1
    _append_phase("watchdog_entry_exited", **evidence_binding,
                  exit_code=0, stderr_tail=stderr.tail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
