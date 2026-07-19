"""Fail-closed acceptance matrix for Agentic Business OS roadmap phases 2-7."""

from __future__ import annotations


PHASE_GATES = {
    2: (
        "concurrent_edits_detected", "owner_main_execution_forbidden", "feature_worktree_enforced",
        "mission_file_leases_enforced", "single_release_coordinator", "revision_truth_complete",
    ),
    3: (
        "typed_event_contract", "deterministic_replay", "duplicate_events_safe", "late_events_safe",
        "partial_events_safe", "authority_audit_mandatory", "provenance_privacy_mandatory",
        "existing_sources_reconciled", "additive_migration_only",
    ),
    4: (
        "sam_observer", "ledger_observer", "herdmaster_observer", "beacon_observer",
        "schedule_trigger", "event_trigger", "failure_telemetry", "recommendation_evidence",
        "false_positive_measurement", "no_unauthorized_execution",
    ),
    5: (
        "daily_executive_cycle", "evidence_linked_priorities", "bounded_runway", "owner_decision_inbox",
        "stale_plan_recovery", "no_invented_business_truth", "software_routes_to_core",
        "operations_route_to_domain_owner",
    ),
    6: (
        "per_capability_trust", "minimum_sample_sizes", "reversibility", "value_risk_limits",
        "kill_switches", "automatic_regression", "zero_blanket_authority", "red_zone_owner_visibility",
    ),
    7: (
        "authoritative_dashboard", "daily_brief", "source_freshness_visible", "decision_action_outcome_trace",
        "responsive_failure_states", "revision_truth_visible", "live_owner_canary",
    ),
}


def evaluate_phase(phase, evidence):
    phase = int(phase)
    gates = PHASE_GATES.get(phase)
    if not gates:
        return {"complete": False, "status": "phase_unknown", "phase": phase}
    evidence = evidence if isinstance(evidence, dict) else {}
    results = {gate: evidence.get(gate) is True for gate in gates}
    missing = [gate for gate, passed in results.items() if not passed]
    return {
        "phase": phase,
        "complete": not missing,
        "status": "phase_acceptance_passed" if not missing else "phase_acceptance_incomplete",
        "passed_count": len(gates) - len(missing),
        "required_count": len(gates),
        "missing_gates": missing,
        "gates": results,
    }


def evaluate_program(evidence_by_phase):
    evidence_by_phase = evidence_by_phase if isinstance(evidence_by_phase, dict) else {}
    phases = {
        phase: evaluate_phase(phase, evidence_by_phase.get(phase) or evidence_by_phase.get(str(phase)) or {})
        for phase in PHASE_GATES
    }
    incomplete = [phase for phase, result in phases.items() if not result["complete"]]
    return {
        "version": "agentic_business_os_acceptance_v1",
        "complete": not incomplete,
        "status": "program_acceptance_passed" if not incomplete else "program_acceptance_incomplete",
        "incomplete_phases": incomplete,
        "phases": phases,
    }
