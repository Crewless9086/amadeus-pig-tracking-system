"""Deterministic blocker classification for the CHARLIE conveyor."""

from datetime import datetime, timezone


OWNER_DECISION_REQUIRED = "owner_decision_required"
RED_ZONE_OWNER_APPROVAL_REQUIRED = "red_zone_owner_approval_required"
INTERNAL_BLOCK_CLASSES = {
    "system_repair_required",
    "environment_retry_required",
    "branch_repair_required",
    "implementation_fix_required",
    "evidence_repair_required",
    "stale_state_reconciliation_required",
}


def classify_block(agent="", reason="", artifact=None):
    artifact = artifact if isinstance(artifact, dict) else {}
    text = _block_text(reason, artifact)
    scope = _scope_relation(text, artifact)
    introduced = _introduced_by_current_diff(text, artifact, scope)

    if _contains(text, (
        "destructive migration", "production data deletion", "delete production",
        "customer send", "send to customer", "payment", "deposit", "reserve stock",
        "reservation", "lifecycle write", "public post",
    )) and _contains(text, ("owner approval", "requires owner", "owner decision", "not approved", "red zone")):
        block_class = RED_ZONE_OWNER_APPROVAL_REQUIRED
        route = "owner"
    elif _contains(text, (
        "repeated same blocker loop", "durable loop cap", "contract retry exhausted",
        "recovery attempts exhausted",
    )):
        block_class = OWNER_DECISION_REQUIRED
        route = "owner"
    elif _contains(text, (
        "owner must decide", "owner decision required", "needs owner decision",
        "missing owner decision", "business choice", "ambiguous owner intent",
    )):
        block_class = OWNER_DECISION_REQUIRED
        route = "owner"
    elif _contains(text, (
        "merge conflict", "has conflicts", "conflicting", "branch mismatch", "wrong branch",
        "head branch", "not pushed", "behind main", "stale branch",
    )):
        block_class = "branch_repair_required"
        route = "publisher" if agent in {"publisher", "reviewer", "evidence_reviewer"} else "builder"
    elif _contains(text, (
        "browser unavailable", "browser runtime", "browser list", "could not capture screenshot",
        "no real screenshots", "screenshot permission", "preview server", "preview url",
        "timed out", "timeout", "permissionerror", "temporary directory", "tool unavailable",
    )):
        block_class = "environment_retry_required"
        route = "visual_qa_reviewer" if _contains(text, ("browser", "screenshot", "preview", "visual")) else (agent or "tester")
    elif _contains(text, (
        "stale review", "stale_review", "wrong commit", "wrong revision", "tested sha",
        "head sha", "base commit", "not the pr", "review packet persistence",
    )):
        block_class = "stale_state_reconciliation_required"
        route = "evidence_reviewer"
    elif scope in {"unrelated", "pre_existing"}:
        block_class = "system_repair_required"
        route = "evidence_reviewer"
    elif _contains(text, (
        "source-map", "source map", "vault brain", "did not cite", "missing required agent",
        "missing doctrine", "missing evidence", "artifact missing", "contract retry",
        "review media", "files_inspected", "commands_run evidence",
    )):
        block_class = "evidence_repair_required"
        route = _evidence_route(agent, text)
    elif introduced or artifact.get("bugs") or _contains(text, ("test_status=fail", "reported errors or bugs", "regression", "test failed", "tests failed")):
        block_class = "implementation_fix_required"
        route = "builder"
    else:
        block_class = "system_repair_required"
        route = agent or "planner"

    owner_required = block_class in {OWNER_DECISION_REQUIRED, RED_ZONE_OWNER_APPROVAL_REQUIRED}
    return {
        "version": "charlie_block_disposition_v1",
        "block_class": block_class,
        "owner_required": owner_required,
        "recoverable": not owner_required,
        "responsible_stage": route,
        "scope_relation": scope,
        "introduced_by_current_diff": introduced,
        "blocking": True,
        "severity": _severity(block_class, artifact),
        "reason": str(reason or artifact.get("summary") or "").strip(),
        "evidence": _evidence(artifact),
        "classified_at": datetime.now(timezone.utc).isoformat(),
    }


def normalize_findings(values, *, agent="", artifact=None):
    result = []
    for value in values or []:
        text = _finding_text(value)
        if not text:
            continue
        local_artifact = dict(artifact or {})
        if isinstance(value, dict):
            local_artifact.update(value)
        disposition = classify_block(agent, text, local_artifact)
        result.append({
            "summary": text,
            "scope_relation": disposition["scope_relation"],
            "introduced_by_current_diff": disposition["introduced_by_current_diff"],
            "blocking": disposition["scope_relation"] not in {"unrelated", "pre_existing", "advisory"},
            "severity": disposition["severity"],
            "evidence": disposition["evidence"],
            "responsible_stage": disposition["responsible_stage"],
        })
    return result


def _block_text(reason, artifact):
    values = [reason, artifact.get("summary"), artifact.get("stdout_tail"), artifact.get("stderr_tail")]
    for key in ("errors", "bugs", "qa_findings", "test_evidence"):
        value = artifact.get(key)
        values.extend(value if isinstance(value, list) else [value])
    return "\n".join(_finding_text(value) for value in values if _finding_text(value)).lower()


def _scope_relation(text, artifact):
    explicit = str(artifact.get("scope_relation") or "").strip().lower()
    if explicit in {"current_diff", "unrelated", "pre_existing", "advisory", "unknown"}:
        return explicit
    if _contains(text, ("outside changed surface", "outside the changed surface", "unrelated existing", "unrelated to this", "not introduced by", "pre-existing", "preexisting")):
        return "pre_existing" if "pre" in text else "unrelated"
    if _contains(text, ("advisory only", "non-blocking advisory", "informational only")):
        return "advisory"
    if _contains(text, ("current diff", "introduced by this", "changed code", "regression in")):
        return "current_diff"
    return "unknown"


def _introduced_by_current_diff(text, artifact, scope):
    explicit = artifact.get("introduced_by_current_diff")
    if isinstance(explicit, bool):
        return explicit
    if scope in {"unrelated", "pre_existing", "advisory"}:
        return False
    return scope == "current_diff" or _contains(text, ("introduced by this", "caused by this diff", "regression in the changed"))


def _evidence_route(agent, text):
    if "visual" in text or "screenshot" in text or "review media" in text:
        return "visual_qa_reviewer"
    if "source" in text or "vault" in text or "doctrine" in text:
        return "source_mapper"
    return agent or "evidence_reviewer"


def _severity(block_class, artifact):
    explicit = str(artifact.get("severity") or artifact.get("risk_rating") or "").strip().lower()
    if explicit in {"low", "medium", "high", "critical"}:
        return explicit
    if block_class == RED_ZONE_OWNER_APPROVAL_REQUIRED:
        return "critical"
    if block_class in {OWNER_DECISION_REQUIRED, "implementation_fix_required", "branch_repair_required"}:
        return "high"
    return "medium"


def _evidence(artifact):
    values = []
    for key in ("commands_run", "tests_run", "test_evidence", "files_inspected", "changed_files"):
        value = artifact.get(key)
        values.extend(value if isinstance(value, list) else ([value] if value else []))
    return [_finding_text(value) for value in values if _finding_text(value)][:12]


def _finding_text(value):
    if isinstance(value, dict):
        return str(value.get("summary") or value.get("finding") or value.get("reason") or value.get("message") or value).strip()
    return str(value or "").strip()


def _contains(text, needles):
    return any(needle in text for needle in needles)
