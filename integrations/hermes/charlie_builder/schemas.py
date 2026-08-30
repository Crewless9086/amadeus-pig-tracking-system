"""Strict structured contracts for the no-tool Hermes native builder."""

from __future__ import annotations


NATIVE_PATCH_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "state": {"type": "string", "enum": ["NEEDS_CONTEXT", "PATCH_READY", "BLOCKED"]},
        "context_paths": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 240},
            "maxItems": 20,
        },
        "unified_diff": {"type": "string", "maxLength": 200000},
        "test_proposal": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 240},
            "maxItems": 20,
        },
        "reason": {"type": "string", "maxLength": 500},
    },
    "required": ["state", "context_paths", "unified_diff", "test_proposal", "reason"],
}


class NativeSchemaError(ValueError):
    """The model response does not match the bounded protocol."""


def validate_native_response(value):
    """Validate without trusting optional provider-side schema enforcement."""
    if not isinstance(value, dict) or set(value) != {
        "state", "context_paths", "unified_diff", "test_proposal", "reason"
    }:
        raise NativeSchemaError("native_response_schema_invalid")
    state = value.get("state")
    if state not in {"NEEDS_CONTEXT", "PATCH_READY", "BLOCKED"}:
        raise NativeSchemaError("native_response_state_invalid")
    paths = value.get("context_paths")
    tests = value.get("test_proposal")
    if not isinstance(paths, list) or len(paths) > 20 or not all(
        isinstance(item, str) and 0 < len(item) <= 240 for item in paths
    ):
        raise NativeSchemaError("native_context_request_invalid")
    if not isinstance(tests, list) or len(tests) > 20 or not all(
        isinstance(item, str) and 0 < len(item) <= 240 for item in tests
    ):
        raise NativeSchemaError("native_test_proposal_invalid")
    diff = value.get("unified_diff")
    reason = value.get("reason")
    if not isinstance(diff, str) or len(diff.encode("utf-8")) > 200000:
        raise NativeSchemaError("native_patch_size_invalid")
    if not isinstance(reason, str) or len(reason) > 500:
        raise NativeSchemaError("native_reason_invalid")
    if state == "NEEDS_CONTEXT" and (not paths or diff):
        raise NativeSchemaError("native_context_state_invalid")
    if state == "PATCH_READY" and (paths or not diff):
        raise NativeSchemaError("native_patch_state_invalid")
    if state == "BLOCKED" and (paths or diff or not reason.strip()):
        raise NativeSchemaError("native_blocked_state_invalid")
    return {
        "state": state,
        "context_paths": list(paths),
        "unified_diff": diff,
        "test_proposal": list(tests),
        "reason": reason.strip(),
    }
