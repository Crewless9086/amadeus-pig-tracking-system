from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest

from modules.charlie.mission_outcome_gate import (
    CONTRACT_VERSION, EVIDENCE_ROWS, evaluate_outcome_handover, mission_lifecycle_projection,
)
from modules.charlie.mission_store import record_mission_outcome_handover


MISSION = "CORE-MOG-20260820"


def valid_handover():
    observed = "2026-08-20T12:00:00+00:00"
    evidence = {row: {"evidence_id": f"ev-{row}", "observed_at": observed} for row in EVIDENCE_ROWS}
    evidence.update({
        "operational_actor": {**evidence["operational_actor"], "runtime_identity": "core-worker-7", "is_terminal": False, "correlation_id": "cycle-1"},
        "genuine_trigger": {**evidence["genuine_trigger"], "provider_identity": "durable-queue", "created_by_terminal": False, "correlation_id": "cycle-1"},
        "loaded_revision": {**evidence["loaded_revision"], "sha": "a" * 40, "exact_match": True, "correlation_id": "cycle-1"},
        "primary_correlation_id": "cycle-1",
        "canonical_readback": {**evidence["canonical_readback"], "receipt_id": "receipt-7", "readback_id": "readback-7", "readback_matches": True, "correlation_id": "cycle-1"},
        "provider_result": {**evidence["provider_result"], "provider_identity": "provider-7", "provider_result_id": "result-7", "correlation_id": "cycle-1"},
        "physical_or_customer_result": {**evidence["physical_or_customer_result"], "result_identity": "physical-7", "correlation_id": "cycle-1", "verified": True},
        "later_independent_cycle": {**evidence["later_independent_cycle"], "correlation_id": "cycle-later-2", "terminal_independent": True},
        "safe_final_state": {**evidence["safe_final_state"], "state": "safe", "verified": True, "correlation_id": "cycle-1"},
        "replay_and_concurrency_containment": {**evidence["replay_and_concurrency_containment"], "replay_contained": True, "concurrency_contained": True, "control_identity": "claim-7", "correlation_id": "cycle-1"},
        "automatic_follow_up_or_unresolved_work_ownership": {**evidence["automatic_follow_up_or_unresolved_work_ownership"], "automatic": True, "next_trigger": "queue subscription", "correlation_id": "cycle-1"},
        "owner_work_removal": {**evidence["owner_work_removal"], "measurement_id": "measure-7", "before_manual_steps": 3, "after_manual_steps": 0, "correlation_id": "cycle-1"},
    })
    return {"contract_version": CONTRACT_VERSION, "handover_id": "handover-1", "mission_id": MISSION,
            "reporting_actor_type": "external_verifier", "terminal_disposition": "release_stage_passed",
            "requested_lifecycle": "BUSINESS_COMPLETE", "technical_milestones": ["merged", "deployed"],
            "applicability": {row: "required" for row in EVIDENCE_ROWS}, "evidence": evidence}


def test_recent_short_summary_shape_is_invalid_and_open():
    result = evaluate_outcome_handover("Done. Full template exists at the same path.", mission_id=MISSION)
    assert result["handover_status"] == "INVALID_HANDOVER"
    assert result["lifecycle_state"] == "WORKING"


def test_technical_stage_only_success_stays_open_and_bare_done_is_rejected():
    item = valid_handover(); item.update(requested_lifecycle="WORKING", reporting_actor_type="terminal", terminal_disposition="tests_stage_passed")
    result = evaluate_outcome_handover(item, mission_id=MISSION)
    assert result["handover_status"] == "VALID_HANDOVER" and not result["business_complete"]
    item["terminal_disposition"] = "done"
    assert "terminal_disposition_stage_qualifier" in evaluate_outcome_handover(item, mission_id=MISSION)["errors"]


def test_terminal_cannot_close_its_own_mission():
    item = valid_handover(); item["reporting_actor_type"] = "terminal"
    result = evaluate_outcome_handover(item, mission_id=MISSION)
    assert result["handover_status"] == "INVALID_HANDOVER"
    assert "terminal_cannot_set_business_complete" in result["errors"]


def test_missing_genuine_trigger_and_terminal_created_trigger_fail():
    for mutation in (None, True):
        item = valid_handover()
        if mutation is None: item["evidence"].pop("genuine_trigger")
        else: item["evidence"]["genuine_trigger"]["created_by_terminal"] = True
        assert evaluate_outcome_handover(item, mission_id=MISSION)["handover_status"] == "INVALID_HANDOVER"


def test_deployment_only_missing_later_cycle_and_owner_delta_fail():
    item = valid_handover()
    for row in ("operational_actor", "genuine_trigger", "canonical_readback", "provider_result", "physical_or_customer_result", "later_independent_cycle", "owner_work_removal"):
        item["evidence"].pop(row)
    result = evaluate_outcome_handover(item, mission_id=MISSION)
    assert not result["business_complete"] and "later_independent_cycle" in result["remaining_acceptance_rows"]
    for row in ("later_independent_cycle", "owner_work_removal"):
        broken = valid_handover(); broken["evidence"].pop(row)
        assert f"missing:{row}" in evaluate_outcome_handover(broken, mission_id=MISSION)["errors"]


def test_conditional_provider_and_physical_require_bounded_auditable_na():
    item = valid_handover()
    for row in ("provider_result", "physical_or_customer_result"):
        item["evidence"].pop(row)
        item["applicability"][row] = {"state": "not_applicable", "reason_code": "NO_PROVIDER_OR_PHYSICAL_EFFECT",
            "reason": "Software-only observation mission.", "authority": "mission_acceptance_scope", "audit_ref": "scope-row-4"}
    assert evaluate_outcome_handover(item, mission_id=MISSION)["business_complete"] is True
    item["applicability"]["provider_result"].pop("audit_ref")
    assert evaluate_outcome_handover(item, mission_id=MISSION)["handover_status"] == "INVALID_HANDOVER"


def test_canonical_and_safety_rows_cannot_be_waived():
    for row in ("canonical_readback", "safe_final_state", "replay_and_concurrency_containment",
                "automatic_follow_up_or_unresolved_work_ownership"):
        item = valid_handover()
        item["evidence"].pop(row)
        item["applicability"][row] = {"state": "not_applicable", "reason_code": "NO_EFFECT",
            "reason": "claimed optional", "authority": "test", "audit_ref": "audit-1"}
        result = evaluate_outcome_handover(item, mission_id=MISSION)
        assert result["handover_status"] == "INVALID_HANDOVER"
        assert f"invalid_not_applicable:{row}" in result["errors"]


def test_provider_and_physical_labels_without_bound_results_fail():
    item = valid_handover()
    item["evidence"]["provider_result"].pop("provider_result_id")
    item["evidence"]["physical_or_customer_result"]["verified"] = False
    result = evaluate_outcome_handover(item, mission_id=MISSION)
    assert "provider_result_not_bound" in result["errors"]
    assert "physical_or_customer_result_not_bound" in result["errors"]


def test_cross_evidence_correlations_and_same_later_cycle_fail():
    item = valid_handover()
    item["evidence"]["provider_result"]["correlation_id"] = "different-cycle"
    item["evidence"]["later_independent_cycle"]["correlation_id"] = "cycle-1"
    result = evaluate_outcome_handover(item, mission_id=MISSION)
    assert "provider_result_not_bound" in result["errors"]
    assert "later_independent_cycle_not_proven" in result["errors"]


def test_store_path_requires_canonical_event_binding_for_every_required_row():
    item = valid_handover()
    result = evaluate_outcome_handover(item, mission_id=MISSION, canonical_evidence={})
    assert result["handover_status"] == "INVALID_HANDOVER"
    assert "canonical_evidence_unverified:canonical_readback" in result["errors"]


def test_invalid_attempt_preserves_prior_complete_projection():
    prior = {"lifecycle_state": "BUSINESS_COMPLETE", "business_complete": True,
             "follow_up_proven": True, "hold": {}}
    item = valid_handover(); item["handover_id"] = ""
    result = evaluate_outcome_handover(item, mission_id=MISSION, prior=prior)
    assert result["handover_status"] == "INVALID_HANDOVER"
    assert result["lifecycle_state"] == "BUSINESS_COMPLETE"


def test_follow_up_requires_automatic_trigger_or_exact_unresolved_owner():
    item = valid_handover()
    item["evidence"]["automatic_follow_up_or_unresolved_work_ownership"].update(automatic=False, next_trigger="")
    result = evaluate_outcome_handover(item, mission_id=MISSION)
    assert "follow_up_or_unresolved_work_ownership_not_proven" in result["errors"]
    assert result["follow_up_proven"] is False
    item["evidence"]["automatic_follow_up_or_unresolved_work_ownership"].update(
        unresolved_work_owner="CORE", exact_blocker="provider unavailable", wake_condition="provider recovers")
    assert evaluate_outcome_handover(item, mission_id=MISSION)["business_complete"] is True


def test_empty_and_cross_mission_handover_identity_rejected_before_database():
    item = valid_handover(); item["handover_id"] = ""
    result, status = record_mission_outcome_handover(MISSION, item, connect_factory=lambda _: None)
    assert status == 400 and result["status"] == "handover_id_required"
    item = valid_handover(); item["mission_id"] = "OTHER-MISSION"
    result, status = record_mission_outcome_handover(MISSION, item, connect_factory=lambda _: None)
    assert status == 409 and result["status"] == "handover_mission_identity_mismatch"


def test_history_storage_is_bounded_before_append():
    source = Path("modules/charlie/mission_store.py").read_text(encoding="utf-8")
    assert "MISSION_LIFECYCLE_HISTORY_LIMIT = 100" in source
    assert "mission_lifecycle_history_archive_digest" in source
    history = [{"handover_id": f"old-{index}", "handover_digest": f"digest-{index}"} for index in range(100)]

    class Cursor:
        def __init__(self): self.executed = []
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def execute(self, sql, params=None): self.executed.append((sql, params))
        def fetchall(self):
            sql = self.executed[-1][0]
            if "select status" in sql:
                return [("in_progress", {"mission_lifecycle_history": history})]
            if "event_type='outcome_handover_recorded'" in sql:
                return []
            if "from public.charlie_mission_events" in sql:
                rows = []
                for row, value in valid_handover()["evidence"].items():
                    if isinstance(value, dict) and value.get("evidence_id"):
                        digest = __import__("hashlib").sha256(__import__("json").dumps(
                            value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
                        rows.append((value["evidence_id"], "outcome_evidence_recorded",
                                     {"outcome_evidence_row": row, "evidence_payload_digest": digest,
                                      "producer_identity": "core-worker-7",
                                      "producer_actor_type": "deployed_agent"}, None))
                return rows
            return []

    class Connection:
        def __init__(self): self.db_cursor = Cursor()
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def cursor(self): return self.db_cursor

    connection = Connection()
    item = valid_handover(); item["reporting_actor_type"] = "control_tower"
    result, status = record_mission_outcome_handover(
        MISSION, item, authenticated_principal="owner-admin:test",
        database_url="postgres://unit-test", connect_factory=lambda _: connection)
    assert status == 200 and result["status"] == "VALID_HANDOVER"
    update = next(params for sql, params in connection.db_cursor.executed if "update public.charlie_missions" in sql)
    metadata = __import__("json").loads(update["metadata"])
    assert len(metadata["mission_lifecycle_history"]) == 100
    assert metadata["mission_lifecycle_history_archived_count"] == 1
    assert metadata["mission_lifecycle_history_archive_digest"]


def test_valid_external_hold_and_protected_boundary_preserve_automatic_continuation():
    for lifecycle in ("EXTERNAL_HOLD", "PROTECTED_BOUNDARY"):
        item = valid_handover(); item.update(requested_lifecycle=lifecycle, reporting_actor_type="terminal",
            hold={"type": lifecycle, "owner": "release-coordinator", "reason": "authority boundary",
                  "wake_condition": "approved revision reaches main", "automatic_continuation_trigger": "merge event"})
        result = evaluate_outcome_handover(item, mission_id=MISSION)
        assert result["lifecycle_state"] == lifecycle
        assert result["next_safe_stage"] == "automatic_continuation_on_hold_wake"


def test_fully_valid_business_complete_fixture_and_projection_separate_status():
    result = evaluate_outcome_handover(valid_handover(), mission_id=MISSION)
    assert result["handover_status"] == "VALID_HANDOVER" and result["business_complete"] is True
    projection = mission_lifecycle_projection({"status": "done", "metadata": {}})
    assert projection["technical_stage"] == "done" and projection["lifecycle_state"] == "WORKING"


def test_digest_is_idempotent_and_changed_contract_conflicts_by_identity():
    first = evaluate_outcome_handover(valid_handover(), mission_id=MISSION)
    replay = evaluate_outcome_handover(valid_handover(), mission_id=MISSION)
    changed = deepcopy(valid_handover()); changed["evidence"]["owner_work_removal"]["after_manual_steps"] = 1
    assert first["handover_digest"] == replay["handover_digest"]
    assert first["handover_digest"] != evaluate_outcome_handover(changed, mission_id=MISSION)["handover_digest"]


def test_concurrent_replay_is_deterministic_and_store_serializes_row():
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: evaluate_outcome_handover(valid_handover(), mission_id=MISSION), range(32)))
    assert len({result["handover_digest"] for result in results}) == 1
    source = Path("modules/charlie/mission_store.py").read_text(encoding="utf-8")
    assert "where mission_id=%(mission_id)s for update" in source
    assert "handover_replay_conflict" in source


def load_tests(_loader, _tests, _pattern):
    """Keep this fixture family visible to CORE's per-module unittest CI rail."""
    names = sorted(name for name, value in globals().items()
                   if name.startswith("test_") and callable(value))
    return unittest.TestSuite(unittest.FunctionTestCase(globals()[name]) for name in names)
