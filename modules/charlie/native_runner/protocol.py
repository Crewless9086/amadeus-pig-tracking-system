"""Pure wire-protocol identities used by the isolated Hermes plugin."""

from __future__ import annotations

import hashlib
import json


class ProtocolError(ValueError):
    """Stable failure for malformed plugin protocol input."""


def _path(value):
    text = str(value or "").strip().replace("\\", "/")
    if (not text or text.startswith("/") or text.startswith("../")
            or "/../" in text or text == ".."):
        raise ProtocolError("candidate_paths_invalid")
    return text


def canonical_candidate_diff(changed_files, patch_bytes):
    """Return the backend-compatible identity for one complete candidate diff."""
    if not isinstance(changed_files, (list, tuple, set)) or not changed_files:
        raise ProtocolError("candidate_paths_invalid")
    paths = sorted({_path(value) for value in changed_files})
    if len(paths) != len(changed_files):
        raise ProtocolError("candidate_paths_invalid")
    patch = patch_bytes if isinstance(patch_bytes, bytes) else str(patch_bytes).encode("utf-8")
    payload = json.dumps({
        "changed_files": paths,
        "patch_sha256": hashlib.sha256(patch).hexdigest(),
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
