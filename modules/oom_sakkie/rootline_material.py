"""Stable owner-visible ROOTLINE decision material shared by daily/change rails."""
import hashlib
import json
from typing import Any, Mapping


def rootline_material_digest(result: Mapping[str, Any]) -> str:
    recommendations = [{key: _normal(row.get(key)) for key in
            ("subject", "status", "recommendation", "reason", "preferred_window")}
                            for row in result.get("recommendations") or () if isinstance(row, Mapping)]
    recommendations.sort(key=lambda row: (str(row.get("subject") or ""),
                                           str(row.get("status") or row.get("recommendation") or "")))
    selected = {"overall_status": _normal(result.get("overall_status")),
        "recommendations": recommendations,
        "next_reassessment": stable_reassessment(result.get("next_reassessment")),
        "owner_question": _normal((result.get("owner_brief") or {}).get("family_fact_needed"))}
    return hashlib.sha256(json.dumps(selected, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def stable_reassessment(value):
    if not isinstance(value, Mapping):
        return value
    trigger = str(value.get("trigger") or "")
    stable = {key: _normal(value.get(key)) for key in (
        "trigger", "reason", "also_on", "recovery_if_window_is_missed", "automatic_command"
    ) if key in value}
    if trigger not in {"new_canonical_evidence", "new_canonical_evidence_or_next_read"} and "at" in value:
        stable["at"] = value.get("at")
    return stable


def _normal(value):
    return " ".join(value.split()) if isinstance(value, str) else value
