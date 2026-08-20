from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import unittest

from modules.charlie.mission_outcome_gate import (
    CONTRACT_VERSION, EVIDENCE_ROWS, evaluate_outcome_handover, mission_lifecycle_projection,
)


MISSION = "CORE-MOG-20260820"


def valid_handover():
    observed = "2026-08-20T12:00:00+00:00"
    evidence = {row: {"evidence_id": f"ev-{row}", "observed_at": observed} for row in EVIDENCE_ROWS}
    evidence.update({
        "operational_actor": {**evidence["operational_actor"], "runtime_identity": "core-worker-7", "is_terminal": False},
        "genuine_trigger": {**evidence["genuine_trigger"], "provider_identity": "durable-queue", "created_by_terminal": False},
        "loaded_revision": {**evidence["loaded_revision"], "sha": "a" * 40, "exact_match": True},
        "later_independent_cycle": {**evidence["later_independent_cycle"], "correlation_id": "cycle-later-2", "terminal_independent": True},
        "owner_work_removal": {**evidence["owner_work_removal"], "measurement_id": "measure-7", "before_manual_steps": 3, "after_manual_steps": 0},
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
