"""Deterministic owner-readiness gates for CHARLIE missions."""

from __future__ import annotations

from typing import Any, Mapping


READY = "ready_to_approve"
OWNER_ACTION = "owner_action_required"
VERIFY = "verification_required"


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _truth(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "pass", "passed", "complete", "completed", "applied", "verified"}


def _evidence_flag(packet: Mapping[str, Any], metadata: Mapping[str, Any], *keys: str) -> bool:
    release = _dict(packet.get("release_readiness"))
    deployment = _dict(packet.get("deployment_watch"))
    evidence = _dict(packet.get("operational_evidence"))
    for key in keys:
        for source in (packet, release, deployment, evidence, metadata):
            if key in source and _truth(source.get(key)):
                return True
    return False


def _gate(key: str, label: str, required: bool, passed: bool, action: str = "") -> dict[str, Any]:
    status = "not_required" if not required else ("passed" if passed else "pending")
    return {"key": key, "label": label, "required": required, "passed": bool(passed or not required), "status": status, "action": action}


def evaluate_final_readiness(mission: Mapping[str, Any]) -> dict[str, Any]:
    """Return the single owner-facing release/final readiness verdict.

    Explicit packet evidence wins. Changed files determine which operational gates
    are mandatory, so an agent cannot call a migration or UI mission ready merely
    by setting ``review_status``.
    """
    mission = _dict(mission)
    metadata = _dict(mission.get("metadata"))
    packet = _dict(metadata.get("review_packet"))
    changed = [str(item).replace("\\", "/").lower() for item in _list(packet.get("changed_files")) if str(item).strip()]
    status = str(mission.get("status") or "").strip().lower()

    migration_required = any(path.startswith("supabase/migrations/") or "/migrations/" in path for path in changed)
    ui_required = any(path.startswith(("templates/", "static/js/", "static/css/")) for path in changed)
    production_required = any(path.startswith(("modules/", "templates/", "static/")) or path in {"app.py", "requirements.txt"} for path in changed)

    implementation_complete = status in {"pr_ready", "release_approved", "merged", "deployed", "done"} or str(packet.get("review_status") or "") in {
        "ready_for_owner_review", "final_approved", "deployed", "done"
    }
    tests_passed = bool(_list(packet.get("test_evidence"))) or _evidence_flag(packet, metadata, "tests_passed", "verify_passed")
    migration_approved = _evidence_flag(packet, metadata, "migration_owner_approved", "migration_approved")
    migration_applied = _evidence_flag(packet, metadata, "migration_applied", "migrations_applied")
    visual_verified = _evidence_flag(packet, metadata, "visual_verified", "browser_smoke_passed", "ui_smoke_passed")
    visual_review = _dict(packet.get("visual_review"))
    visual_verified = visual_verified or str(visual_review.get("status") or "").lower() in {"captured", "pass", "passed", "approved", "verified"}
    deployed = status in {"deployed", "done"} or _evidence_flag(packet, metadata, "deployment_verified", "deployed")
    live_smoke = _evidence_flag(packet, metadata, "live_smoke_passed", "production_smoke_passed")

    release_gates = [
        _gate("implementation", "Implementation complete", True, implementation_complete, "Return to the build workflow."),
        _gate("tests", "Focused tests passed", True, tests_passed, "Run and persist focused verification evidence."),
        _gate("migration_approval", "Migration owner approval", migration_required, migration_approved or migration_applied, "Review and explicitly approve the additive migration."),
        _gate("migration_applied", "Migration applied", migration_required, migration_applied, "Apply the approved migration and record verification."),
        _gate("visual_review", "Browser/UI evidence", ui_required, visual_verified, "Capture and review browser evidence."),
    ]
    operational_gates = [
        _gate("deployment", "Production deployment verified", production_required, deployed, "Deploy the merged change and record deployment evidence."),
        _gate("live_smoke", "Live smoke test passed", production_required, live_smoke, "Run and record the live production smoke test."),
    ]

    release_pending = [gate for gate in release_gates if gate["required"] and not gate["passed"]]
    operational_pending = [gate for gate in operational_gates if gate["required"] and not gate["passed"]]
    if release_pending:
        verdict = OWNER_ACTION if release_pending[0]["key"] == "migration_approval" else VERIFY
        next_action = release_pending[0]["action"]
    elif operational_pending:
        # Release can be authorized only when the remaining work is performed by
        # the release bridge. Already-merged work must finish those gates first.
        already_released = status in {"merged", "deployed", "done"} or bool(packet.get("merge_commit"))
        verdict = VERIFY if already_released else READY
        next_action = operational_pending[0]["action"] if already_released else "Approve release; CORE must then deploy and verify the remaining operational gates."
    else:
        verdict = READY
        next_action = "Approve the completed mission."

    can_authorize_release = verdict == READY and status == "pr_ready"
    final_operational_ready = not release_pending and not operational_pending
    review_phase = (
        "operational_complete" if final_operational_ready
        else "release_authorization_ready" if can_authorize_release
        else "needs_owner_action" if verdict == OWNER_ACTION
        else "verification_required"
    )
    return {
        "version": "charlie-final-readiness-v1",
        "verdict": verdict,
        "review_phase": review_phase,
        "headline": {READY: "READY TO APPROVE", OWNER_ACTION: "OWNER ACTION REQUIRED", VERIFY: "DO NOT APPROVE YET"}[verdict],
        "next_action": next_action,
        "can_authorize_release": can_authorize_release,
        "final_operational_ready": final_operational_ready,
        "requirements": {
            "migration": migration_required,
            "ui": ui_required,
            "production": production_required,
        },
        "gates": release_gates + operational_gates,
        "pending_gate_keys": [gate["key"] for gate in release_pending + operational_pending],
    }
