import hashlib
import re
from datetime import datetime, timezone

from modules.charlie.block_recovery import normalize_findings


GOVERNANCE_VERSION = "charlie_mission_governance_v1"
DEFAULT_TOTAL_BACKFLOW_LIMIT = 4
DEFAULT_FAMILY_BACKFLOW_LIMIT = 2
OVERSIZED_SCOPE_DOMAIN_LIMIT = 4
RED_ZONE_TERMS = (
    "auth bypass",
    "authorization bypass",
    "secret exposed",
    "production data deletion",
    "destructive migration",
    "customer send without owner",
    "payment without owner",
    "reservation without owner",
    "lifecycle write without owner",
    "public post without owner",
)
FAMILY_RULES = (
    ("baseline_regression", ("pre-existing", "preexisting", "reproduces on main", "merge base", "not introduced by")),
    ("environment_timeout", ("timeout", "timed out", "tool unavailable", "permission denied", "environment")),
    ("revision_evidence", ("wrong revision", "wrong commit", "tested revision", "pr head", "branch", "worktree")),
    ("visual_evidence", ("screenshot", "viewport", "visual evidence", "preview url", "browser evidence")),
    ("input_validation", ("malformed", "invalid", "null", "structured", "uninterpretable", "threshold", "unknown quantity")),
    ("supply_compatibility", ("category", "weight", "sex", "compatible supply", "demand cap", "capacity")),
    ("access_authority", ("owner guard", "access gate", "permission", "authority", "authentication", "authorization")),
    ("test_evidence", ("test_status", "tests failed", "test failed", "missing test", "evidence missing")),
)


def ensure_acceptance_matrix(mission, planner_artifact=None):
    mission = mission if isinstance(mission, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    existing = metadata.get("mission_governance") if isinstance(metadata.get("mission_governance"), dict) else {}
    matrix = existing.get("acceptance_matrix") if isinstance(existing.get("acceptance_matrix"), list) else []
    planner_criteria = _clean_list((planner_artifact or {}).get("acceptance_criteria")) if isinstance(planner_artifact, dict) else []
    if matrix and not (planner_criteria and existing.get("matrix_source") == "mission_fallback"):
        return _governance_packet(existing, matrix)

    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    planner_artifact = planner_artifact if isinstance(planner_artifact, dict) else {}
    vault_criteria = _clean_list(vault.get("acceptance_criteria"))
    criteria = planner_criteria or vault_criteria
    tests = _clean_list(planner_artifact.get("test_plan") or vault.get("test_plan"))
    if not criteria:
        outcome = str(vault.get("desired_outcome") or mission.get("raw_text") or mission.get("title") or "Approved mission outcome").strip()
        criteria = [outcome[:500]]

    rows = []
    for index, requirement in enumerate(criteria, 1):
        rows.append({
            "id": _stable_id("acceptance", requirement),
            "sequence": index,
            "requirement": requirement,
            "evidence_required": tests[min(index - 1, len(tests) - 1)] if tests else "Focused deterministic verification",
            "test_scope": tests[min(index - 1, len(tests) - 1)] if tests else "mission-owned focused tests",
            "verification_stage": "tester",
            "status": "pending",
            "evidence": [],
        })
    rows.append({
        "id": "authority-boundary",
        "sequence": len(rows) + 1,
        "requirement": "No authority, safety, or owner-approval boundary is weakened.",
        "evidence_required": "QA authority and red-zone invariant review",
        "test_scope": "mission authority invariants",
        "verification_stage": "qa_red_team",
        "status": "pending",
        "evidence": [],
    })
    source = "planner" if planner_criteria else ("mission_vault" if vault_criteria else "mission_fallback")
    return _governance_packet(existing, rows, frozen=True, source=source)


def update_acceptance_matrix(governance, agent, artifact, passed):
    governance = governance if isinstance(governance, dict) else {}
    artifact = artifact if isinstance(artifact, dict) else {}
    rows = [dict(row) for row in governance.get("acceptance_matrix", []) if isinstance(row, dict)]
    explicit = artifact.get("acceptance_results") if isinstance(artifact.get("acceptance_results"), list) else []
    explicit_by_id = {str(item.get("id") or ""): item for item in explicit if isinstance(item, dict)}
    evidence = _clean_list(artifact.get("tests_run") or artifact.get("test_evidence") or artifact.get("qa_findings"))[:8]
    for row in rows:
        result = explicit_by_id.get(str(row.get("id") or ""))
        if result:
            row["status"] = _matrix_status(result.get("status"))
            row["evidence"] = _clean_list(result.get("evidence")) or evidence
            row["verified_by"] = agent
            continue
        if passed and row.get("verification_stage") == agent:
            row["status"] = "passed"
            row["evidence"] = evidence
            row["verified_by"] = agent
    return _governance_packet(governance, rows)


def validate_acceptance_scope(rows, allowed_files=None):
    """Prove that a bounded child's path-bearing criteria fit its allowed scope."""
    rows = [dict(row) for row in (rows or []) if isinstance(row, dict)]
    allowed = [str(item or "").replace("\\", "/").strip() for item in (allowed_files or []) if str(item or "").strip()]
    violations = []
    if allowed:
        for row in rows:
            text = " ".join(str(row.get(key) or "") for key in ("requirement", "test_scope", "evidence_required"))
            referenced = re.findall(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+", text.replace("\\", "/"))
            outside = [path for path in referenced if not any(path == root or path.startswith(root.rstrip("/") + "/") for root in allowed)]
            if outside:
                violations.append({"acceptance_id": row.get("id", ""), "outside_paths": outside})
    return {
        "satisfiable": not violations,
        "checked_rows": len(rows),
        "allowed_files": allowed,
        "violations": violations,
        "status": "acceptance_scope_satisfiable" if not violations else "acceptance_scope_unsatisfiable",
    }


def evaluate_quality_failure(mission, agent, artifact, quality):
    mission = mission if isinstance(mission, dict) else {}
    artifact = artifact if isinstance(artifact, dict) else {}
    quality = quality if isinstance(quality, dict) else {}
    findings = classify_artifact_findings(agent, artifact, quality)
    blocking = [item for item in findings if item["disposition"] == "matrix_violation"]
    red_zone = [item for item in findings if item["disposition"] == "red_zone"]
    followups = [item for item in findings if item["disposition"] in {"followup", "baseline_advisory"}]
    budget = backflow_budget(mission, blocking)
    failed_acceptance_ids = _failed_acceptance_ids(artifact)

    if red_zone:
        route = "owner_block"
        reason = "Red-zone finding requires owner review."
    elif failed_acceptance_ids and budget["exhausted"]:
        route = "owner_block"
        reason = "Frozen acceptance criteria remain failed after the bounded correction budget was exhausted."
    elif not blocking:
        route = "continue_with_followups"
        reason = "Only advisory, baseline, or adjacent findings remain."
    elif budget["exhausted"]:
        followups.extend(blocking)
        blocking = []
        route = "continue_with_followups"
        reason = "Acceptance expansion budget exhausted; new findings were converted to linked follow-up missions."
    else:
        route = "backflow"
        reason = quality.get("reason") or "Acceptance matrix violation requires correction."
    return {
        "version": GOVERNANCE_VERSION,
        "route": route,
        "reason": reason,
        "findings": findings,
        "blocking_findings": blocking,
        "followup_findings": _dedupe_findings(followups),
        "red_zone_findings": red_zone,
        "failed_acceptance_ids": failed_acceptance_ids,
        "budget": budget,
    }


def classify_artifact_findings(agent, artifact, quality=None):
    artifact = artifact if isinstance(artifact, dict) else {}
    quality = quality if isinstance(quality, dict) else {}
    values = []
    for key in ("bugs", "errors", "qa_findings", "unresolved_blockers"):
        value = artifact.get(key)
        values.extend(value if isinstance(value, list) else ([value] if value else []))
    if not values and quality.get("reason"):
        values.append(quality["reason"])
    normalized = normalize_findings(values, agent=agent, artifact=artifact)
    result = []
    for original, item in zip(values, normalized):
        text = _finding_text(original)
        lowered = text.lower()
        family = semantic_finding_family(text)
        explicit_scope = item.get("scope_relation")
        if _contains_any(lowered, RED_ZONE_TERMS):
            disposition = "red_zone"
        elif family == "baseline_regression" or explicit_scope in {"pre_existing", "unrelated"}:
            disposition = "baseline_advisory"
        elif family == "environment_timeout" or explicit_scope == "advisory":
            disposition = "followup"
        elif item.get("blocking", True):
            disposition = "matrix_violation"
        else:
            disposition = "followup"
        result.append({
            **item,
            "summary": text,
            "family": family,
            "disposition": disposition,
            "source_agent": agent,
            "affected_paths": _affected_paths(original, text),
        })
    return result


def backflow_budget(mission, findings=None):
    metadata = mission.get("metadata") if isinstance(mission, dict) and isinstance(mission.get("metadata"), dict) else {}
    governance = metadata.get("mission_governance") if isinstance(metadata.get("mission_governance"), dict) else {}
    limits = governance.get("backflow_limits") if isinstance(governance.get("backflow_limits"), dict) else {}
    total_limit = _positive_int(limits.get("mission_total"), DEFAULT_TOTAL_BACKFLOW_LIMIT)
    family_limit = _positive_int(limits.get("per_family"), DEFAULT_FAMILY_BACKFLOW_LIMIT)
    memory = metadata.get("mission_memory") if isinstance(metadata.get("mission_memory"), dict) else {}
    all_events = [event for event in memory.get("events", []) if isinstance(event, dict) and event.get("type") == "agent_backflow"]
    revision_scope = _active_builder_revision(memory)
    events = all_events
    if revision_scope:
        events = [
            event
            for event in all_events
            if str((event.get("metadata") or {}).get("revision_sha") or "").strip() == revision_scope
        ]
    family_counts = {}
    for event in events:
        event_metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        family = str(event_metadata.get("finding_family") or semantic_finding_family(event.get("summary"))).strip()
        family_counts[family] = family_counts.get(family, 0) + 1
    requested_families = sorted({item.get("family") for item in (findings or []) if isinstance(item, dict) and item.get("family")})
    exhausted_families = [family for family in requested_families if family_counts.get(family, 0) >= family_limit]
    return {
        "mission_total": len(events),
        "historical_mission_total": len(all_events),
        "mission_limit": total_limit,
        "per_family_limit": family_limit,
        "family_counts": family_counts,
        "requested_families": requested_families,
        "exhausted_families": exhausted_families,
        "exhausted": len(events) >= total_limit or bool(exhausted_families),
        "revision_scope": revision_scope,
    }


def _active_builder_revision(memory):
    latest = memory.get("latest_by_agent") if isinstance(memory.get("latest_by_agent"), dict) else {}
    builder = latest.get("builder") if isinstance(latest.get("builder"), dict) else {}
    return str(builder.get("commit_sha") or "").strip()


def build_followup_missions(parent, findings):
    parent = parent if isinstance(parent, dict) else {}
    metadata = parent.get("metadata") if isinstance(parent.get("metadata"), dict) else {}
    family = metadata.get("mission_family") if isinstance(metadata.get("mission_family"), dict) else {}
    parent_id = str(parent.get("mission_id") or "").strip()
    root_id = str(family.get("root_mission_id") or parent_id).strip()
    by_family = {}
    for finding in _dedupe_findings(findings):
        by_family.setdefault(finding.get("family") or "implementation_defect", []).append(finding)
    missions = []
    for sequence, (finding_family, items) in enumerate(sorted(by_family.items()), 1):
        key = f"{root_id}|{finding_family}|{'|'.join(sorted(path for item in items for path in item.get('affected_paths', [])))}"
        child_id = f"CHARLIE-FOLLOWUP-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:16].upper()}"
        evidence = [item.get("summary", "") for item in items if item.get("summary")]
        missions.append({
            "mission_id": child_id,
            "status": "new",
            "title": f"Follow-up: {finding_family.replace('_', ' ').title()}",
            "raw_text": f"Resolve the {finding_family.replace('_', ' ')} findings discovered by {parent_id}. " + " ".join(evidence[:4]),
            "urgency": "P1" if any(item.get("severity") in {"high", "critical"} for item in items) else "P2",
            "mission_type": parent.get("mission_type") or "system improvement",
            "approval_level": parent.get("approval_level") or "LEVEL 3",
            "acceptance_criteria": [f"Resolve and regression-test the discovered {finding_family.replace('_', ' ')} finding."],
            "test_plan": ["Run focused tests for the affected paths and compare unrelated failures with main."],
            "metadata": {
                "mission_family": {
                    "parent_mission_id": parent_id,
                    "root_mission_id": root_id,
                    "sequence": int(family.get("next_child_sequence") or 0) + sequence,
                    "discovery_source": "charlie_agent_review",
                    "finding_family": finding_family,
                    "dependency": parent_id,
                    "recommended_priority": "P1" if any(item.get("severity") in {"high", "critical"} for item in items) else "P2",
                    "created_at": _utc_now(),
                },
                "discovery_evidence": items,
                "queue": {"priority": _positive_int((metadata.get("queue") or {}).get("priority"), 100) + sequence},
            },
        })
    return missions


def analyze_pre_builder_scope(mission):
    """Freeze architecture questions and proposed child work before Builder starts."""
    mission = mission if isinstance(mission, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    frozen_child = metadata.get("pre_builder_scope") if isinstance(metadata.get("pre_builder_scope"), dict) else {}
    child_scope = str(frozen_child.get("scope") or "").strip()
    if child_scope:
        return {
            "version": "charlie_pre_builder_scope_v1",
            "domains": [child_scope],
            "planning_gates": [],
            "split_required": False,
            "child_scopes": [],
            "builder_allowed": True,
            "scope": child_scope,
            "parent_analysis": frozen_child.get("parent_analysis", {}),
        }
    text = " ".join(str(mission.get(key) or "") for key in ("title", "raw_text", "mission_type")).lower()
    domains = {
        "data_model": ("schema", "table", "migration", "canonical", "supabase"),
        "lifecycle": ("lifecycle", "status transition", "cancel", "complete", "negative path"),
        "frontend": ("ui", "dashboard", "page", "frontend", "browser"),
        "agent_runtime": ("sam", "agent", "prompt", "conversation", "telegram"),
        "commercial": ("sale", "order", "quote", "price", "payment", "reservation"),
        "release": ("deploy", "render", "github", "pr", "release"),
    }
    matched = [name for name, needles in domains.items() if any(needle in text for needle in needles)]
    gates = []
    if "data_model" in matched and "commercial" in matched:
        gates.extend(["canonical_record_discriminator", "ownership_and_source_of_truth"])
    if "lifecycle" in matched:
        gates.append("positive_and_negative_lifecycle_paths")
    if "data_model" in matched:
        gates.append("migration_and_rollback_authority")
    split_required = len(matched) >= OVERSIZED_SCOPE_DOMAIN_LIMIT
    return {
        "version": "charlie_pre_builder_scope_v1",
        "domains": matched,
        "planning_gates": list(dict.fromkeys(gates)),
        "split_required": split_required,
        "child_scopes": [
            {"sequence": index, "scope": domain, "depends_on": matched[index - 2] if index > 1 else ""}
            for index, domain in enumerate(matched, 1)
        ] if split_required else [],
        "builder_allowed": not gates or bool(((mission.get("metadata") or {}).get("pre_builder_plan") or {}).get("approved")),
    }


def build_scope_child_missions(parent, scope_analysis=None):
    parent = parent if isinstance(parent, dict) else {}
    analysis = scope_analysis if isinstance(scope_analysis, dict) else analyze_pre_builder_scope(parent)
    if not analysis.get("split_required"):
        return []
    parent_id = str(parent.get("mission_id") or "").strip()
    metadata = parent.get("metadata") if isinstance(parent.get("metadata"), dict) else {}
    family = metadata.get("mission_family") if isinstance(metadata.get("mission_family"), dict) else {}
    root_id = str(family.get("root_mission_id") or parent_id).strip()
    children = []
    previous_id = ""
    for item in analysis.get("child_scopes", []):
        scope = str(item.get("scope") or "").strip()
        if not scope:
            continue
        child_id = f"CHARLIE-SCOPE-{hashlib.sha256(f'{root_id}|{scope}'.encode('utf-8')).hexdigest()[:16].upper()}"
        child_metadata = {
            "mission_family": {
                "parent_mission_id": parent_id,
                "root_mission_id": root_id,
                "sequence": item.get("sequence"),
                "discovery_source": "pre_builder_scope_split",
                "finding_family": scope,
                "dependency": previous_id,
            },
            "depends_on_mission_ids": [previous_id] if previous_id else [],
            "pre_builder_scope": {"parent_analysis": analysis, "scope": scope},
        }
        children.append({
            "mission_id": child_id,
            "status": "new",
            "title": f"{parent.get('title') or parent_id}: {scope.replace('_', ' ').title()}",
            "raw_text": f"Deliver the {scope.replace('_', ' ')} slice of parent mission {parent_id}. Keep adjacent domains out of scope and record them as follow-ups.",
            "urgency": parent.get("urgency") or "P1",
            "mission_type": parent.get("mission_type") or "system improvement",
            "approval_level": parent.get("approval_level") or "LEVEL 3",
            "acceptance_criteria": [f"Complete and regression-test only the {scope.replace('_', ' ')} slice."],
            "test_plan": [f"Run focused verification for the {scope.replace('_', ' ')} affected paths."],
            "metadata": child_metadata,
        })
        previous_id = child_id
    return children


def mission_governance_summary(mission):
    mission = mission if isinstance(mission, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    governance = ensure_acceptance_matrix(mission)
    matrix = governance.get("acceptance_matrix", [])
    counts = {"passed": 0, "failed": 0, "pending": 0}
    for row in matrix:
        status = _matrix_status(row.get("status"))
        counts[status] = counts.get(status, 0) + 1
    memory = metadata.get("mission_memory") if isinstance(metadata.get("mission_memory"), dict) else {}
    events = memory.get("events") if isinstance(memory.get("events"), list) else []
    backflows = [event for event in events if isinstance(event, dict) and event.get("type") == "agent_backflow"]
    discoveries = [event for event in events if isinstance(event, dict) and event.get("type") == "followup_discovered"]
    family = metadata.get("mission_family") if isinstance(metadata.get("mission_family"), dict) else {}
    total = len(matrix)
    return {
        "version": GOVERNANCE_VERSION,
        "acceptance_matrix": matrix,
        "acceptance_counts": counts,
        "acceptance_percent": round((counts["passed"] / total) * 100) if total else 0,
        "review_runs": sum(1 for event in events if isinstance(event, dict) and event.get("agent") in {"tester", "qa_red_team"}),
        "backflow_count": len(backflows),
        "fix_count": sum(1 for event in events if isinstance(event, dict) and event.get("agent") == "builder" and event.get("type") == "agent_complete"),
        "followup_count": len(discoveries),
        "cycling": len(backflows) >= DEFAULT_TOTAL_BACKFLOW_LIMIT,
        "family": family,
        "budget": backflow_budget(mission),
    }


def semantic_finding_family(value):
    text = str(value or "").lower()
    for family, needles in FAMILY_RULES:
        if _contains_any(text, needles):
            return family
    return "implementation_defect"


def _governance_packet(existing, matrix, frozen=False, source=""):
    packet = dict(existing if isinstance(existing, dict) else {})
    packet.update({
        "version": GOVERNANCE_VERSION,
        "acceptance_matrix": matrix,
        "matrix_frozen": bool(packet.get("matrix_frozen") or frozen),
        "backflow_limits": packet.get("backflow_limits") or {
            "mission_total": DEFAULT_TOTAL_BACKFLOW_LIMIT,
            "per_family": DEFAULT_FAMILY_BACKFLOW_LIMIT,
        },
        "updated_at": _utc_now(),
    })
    if source:
        packet["matrix_source"] = source
    if frozen and not packet.get("frozen_at"):
        packet["frozen_at"] = _utc_now()
    return packet


def _matrix_status(value):
    value = str(value or "pending").strip().lower()
    if value in {"pass", "passed", "complete", "completed"}:
        return "passed"
    if value in {"fail", "failed", "blocked"}:
        return "failed"
    return "pending"


def _failed_acceptance_ids(artifact):
    results = artifact.get("acceptance_results") if isinstance(artifact, dict) else None
    if not isinstance(results, list):
        return []
    return [
        str(item.get("id") or "").strip()
        for item in results
        if isinstance(item, dict)
        and str(item.get("id") or "").strip()
        and _matrix_status(item.get("status")) == "failed"
    ]


def _affected_paths(original, text):
    paths = []
    if isinstance(original, dict):
        for key in ("file", "source", "path"):
            if original.get(key):
                paths.append(str(original[key]).split(":", 1)[0])
    paths.extend(re.findall(r"(?:modules|tests|static|templates|scripts)/[A-Za-z0-9_./-]+", text.replace("\\", "/")))
    return list(dict.fromkeys(path for path in paths if path))[:8]


def _finding_text(value):
    if isinstance(value, dict):
        return str(value.get("finding") or value.get("summary") or value.get("reason") or value).strip()
    return str(value or "").strip()


def _dedupe_findings(findings):
    seen = set()
    result = []
    for finding in findings or []:
        if not isinstance(finding, dict):
            continue
        key = (finding.get("family"), " ".join(str(finding.get("summary") or "").lower().split())[:400])
        if key in seen:
            continue
        seen.add(key)
        result.append(finding)
    return result


def _clean_list(value):
    values = value if isinstance(value, list) else ([value] if value else [])
    return [str(item).strip()[:600] for item in values if str(item or "").strip()]


def _positive_int(value, default):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _stable_id(prefix, value):
    return f"{prefix}-{hashlib.sha256(str(value).encode('utf-8')).hexdigest()[:10]}"


def _contains_any(text, needles):
    return any(needle in text for needle in needles)


def _utc_now():
    return datetime.now(timezone.utc).isoformat()
