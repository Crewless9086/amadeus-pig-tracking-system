"""Fail-closed secret handling for CHARLIE agent processes and telemetry."""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from pathlib import Path


_SENSITIVE_NAME = re.compile(
    r"(?:^DATABASE_URL$|PASSWORD|SECRET|TOKEN|API[_-]?KEY|PRIVATE[_-]?KEY|CONNECTION[_-]?STRING|^SUPABASE_)",
    re.IGNORECASE,
)
_ASSIGNMENT = re.compile(
    r"\b(?:database_url|password|passwd|secret|token|api[_-]?key|private[_-]?key)\s*[:=]\s*[^\s,;]+",
    re.IGNORECASE,
)
_CREDENTIAL_URL = re.compile(r"\b([a-z][a-z0-9+.-]*://)[^\s/@:]+:[^\s/@]+@", re.IGNORECASE)


def sensitive_environment_name(name: object) -> bool:
    return bool(_SENSITIVE_NAME.search(str(name or "")))


def restricted_agent_environment(environ=None) -> dict[str, str]:
    """Remove credentials from the untrusted model/tool child environment."""

    source = os.environ if environ is None else environ
    return {str(key): str(value) for key, value in source.items() if not sensitive_environment_name(key)}


def redact_secrets(value: object, environ=None) -> str:
    text = str(value or "")
    source = os.environ if environ is None else environ
    secrets = {
        str(secret)
        for key, secret in source.items()
        if sensitive_environment_name(key) and len(str(secret or "")) >= 6
    }
    for secret in sorted(secrets, key=len, reverse=True):
        variants = {secret, urllib.parse.quote(secret, safe=""), urllib.parse.quote_plus(secret)}
        for variant in sorted(variants, key=len, reverse=True):
            if variant:
                text = text.replace(variant, "[REDACTED]")
    text = _CREDENTIAL_URL.sub(r"\1[REDACTED]@", text)
    return _ASSIGNMENT.sub("[REDACTED]", text)


def redact_payload(value, environ=None):
    if isinstance(value, dict):
        return {str(key): redact_payload(item, environ) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_payload(item, environ) for item in value]
    return redact_secrets(value, environ) if isinstance(value, str) else value


def redact_file_in_place(path, environ=None) -> bool:
    target = Path(path)
    if not target.exists() or not target.is_file():
        return False
    original = target.read_text(encoding="utf-8", errors="replace")
    redacted = redact_secrets(original, environ)
    if redacted == original:
        return False
    target.write_text(redacted, encoding="utf-8")
    return True


def assert_serialized_payload_safe(payload, environ=None) -> bool:
    serialized = json.dumps(payload, default=str)
    source = os.environ if environ is None else environ
    return not any(
        str(secret) in serialized
        for key, secret in source.items()
        if sensitive_environment_name(key) and len(str(secret or "")) >= 6
    )
