"""F2 discovery/containment only: actual local handlers; no execution grant."""
import copy
import json
from unittest.mock import patch
from types import SimpleNamespace

import pytest

from tests.test_charlie_native_runner_contracts import (
    Plane, MISSION, NATIVE, claim_payload, client_response, service_at)
from modules.charlie.native_runner.execution import NativeExecutionError


def retire_in_memory(plane):
    evidence = {"generation": "g1", "cursor_agent_id": "bc-test", "cursor_run_id": "run-test",
        "execution_attempt": 5, "provider_agent_state": "ARCHIVED", "provider_run_state": "FINISHED",
        "branch": "cursor/test", "repository_mutation": False, "remote_branch_created": False,
        "pr_number": 0, "head_sha": "", "exact_candidate": "absent"}
    plane.metadata = {"external_supervisor_state": {**evidence, "agent_state": "ARCHIVED", "run_state": "FINISHED",
        "slack_channel_id": "C-TEST", "slack_thread_ts": "1.1"},
        "dispatch_authorization": {"generation": "g1", "status": "valid"}}
    plane.api.retire_cursor(MISSION, evidence)


def test_F2_actual_retirement_before_HNX_must_remain_visible():
    plane = Plane(); retire_in_memory(plane)
    assert len(plane.writes) == 1 and "hermes_native_execution" not in plane.metadata
    rows = plane.api.resumable()
    assert len(rows) == 1 and rows[0]["mission_id"] == MISSION
    assert rows[0]["resume_kind"] == "native_reconciliation_required"
    assert rows[0]["recovery_obligations"] == ["retirement_to_native_reconciliation"]
    assert len(plane.writes) == 1 and plane.provider_reads == []


@pytest.mark.parametrize("stage", ["OWNER_DECISION_REQUIRED", "BLOCKED"])
def test_F2_unfinished_claim_obligation_must_remain_visible(stage):
    plane = Plane()
    plane.native.update(execution_status=stage, worker_claim_id="HNC-EXISTING",
                        claim_expires_at=claim_payload()["claim_expires_at"], head_sha="b" * 40)
    rows = plane.api.resumable()
    assert len(rows) == 1 and rows[0]["mission_id"] == MISSION
    assert rows[0]["resume_kind"] == "native_reconciliation_required"
    assert "terminal_claim_reconciliation" in rows[0]["recovery_obligations"]
    assert plane.writes == []


@pytest.mark.parametrize("kind", ["retired", "owner_notice", "blocked_claim"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_F2_reconciliation_only_rows_hold_before_every_execution_boundary(tmp_path, kind, dry_run):
    plane = Plane()
    if kind == "retired": retire_in_memory(plane)
    elif kind == "owner_notice": plane.native.update(execution_status="OWNER_DECISION_REQUIRED", head_sha="b" * 40)
    else: plane.native.update(execution_status="BLOCKED", worker_claim_id="HNC-EXISTING")
    prior = copy.deepcopy(plane.metadata); writes = len(plane.writes)
    service = service_at(tmp_path, plane.api)
    with patch.object(service, "_process", side_effect=AssertionError("execution after reconciliation")) as execute:
        state = service.once(dry_run=dry_run)
    assert state["state"] == "BLOCKED_HOLD" and state["reason"] == "native_canonical_reconciliation_required"
    assert state["mission_id"] == MISSION and state["recovery_obligations"]
    assert not execute.called and plane.metadata == prior and len(plane.writes) == writes
    assert plane.provider_reads == []
    assert not any(req[0] != "GET" for req in plane.requests[-1:])
    # Local lock/status only: no repository or native execution worktree.
    assert not service.repository_root.exists()
    assert not (service.worktree_root / MISSION).exists()
    restarted = service_at(tmp_path, plane.api)
    with pytest.raises(NativeExecutionError, match="native_execution_held"):
        restarted.once()
    assert restarted._read_status()["recovery_obligations"] == state["recovery_obligations"]


def reconciliation_row():
    return {"mission_id": MISSION, "native_execution_id": NATIVE, "generation": "g1",
            "slack_channel_id": "C-TEST", "slack_thread_ts": "1.1",
            "resume_kind": "native_reconciliation_required",
            "recovery_obligations": ["terminal_claim_reconciliation"]}


@pytest.mark.parametrize("mutation", [
    {"mission_id": ""}, {"mission_id": 1}, {"resume_kind": []},
    {"resume_kind": "unknown"}, {"recovery_obligations": None}, {"recovery_obligations": []},
    {"recovery_obligations": "terminal_claim_reconciliation"}, {"recovery_obligations": [None]},
    {"recovery_obligations": [{}]}, {"recovery_obligations": ["resume_now"]},
    {"resume_kind": "hermes_native_execution"},
])
def test_F2_eleven_malformed_rows_have_zero_execution(tmp_path, mutation):
    row = {**reconciliation_row(), **mutation}
    api = client_response({"success": True, "status": "native_recovery_ready", "executions": [row]})
    service = service_at(tmp_path, api)
    with patch.object(service, "_process", side_effect=AssertionError("execution after malformed row")) as execute:
        with pytest.raises(NativeExecutionError): service.once()
    assert not execute.called
    assert service._read_status()["state"] == "BLOCKED"
    assert not service.repository_root.exists() and not (service.worktree_root / MISSION).exists()


def test_F2_completed_notification_and_released_claim_do_not_create_new_obligation():
    plane = Plane()
    plane.native.update(execution_status="OWNER_DECISION_REQUIRED", head_sha="b" * 40,
                        owner_notification_head="b" * 40, worker_claim_id="")
    assert plane.api.resumable() == [] and plane.writes == []


def test_F2_existing_native_discovery_contract_preserved():
    plane = Plane()
    assert plane.api.resumable() == [{"mission_id": MISSION, "native_execution_id": NATIVE,
        "slack_channel_id": None, "slack_thread_ts": None, "resume_kind": "hermes_native_execution"}]
    assert plane.writes == []


def test_F2_existing_cursor_retirement_pending_contract_preserved():
    plane = Plane()
    plane.metadata = {"external_supervisor_state": {"execution_attempt": 5,
        "cursor_agent_id": "bc-test", "cursor_run_id": "run-test", "branch": "cursor/test",
        "slack_channel_id": "C-TEST", "slack_thread_ts": "1.1", "repository_mutation": False},
        "dispatch_authorization": {"status": "valid"}}
    assert plane.api.resumable() == [{"mission_id": MISSION, "native_execution_id": "",
        "slack_channel_id": "C-TEST", "slack_thread_ts": "1.1", "resume_kind": "cursor_retirement_pending"}]
    assert plane.writes == []


def test_F2_discovery_authentication_is_still_required():
    plane = Plane()
    response = plane.http.get('/api/charlie/hermes/native-executions/resumable')
    assert response.status_code == 403 and plane.writes == []


def test_F2_existing_hold_receipts_survive_reconciliation_status_update(tmp_path):
    service = service_at(tmp_path)
    original = service._status(state="BLOCKED_HOLD", mission_id=MISSION, reason="funding_hold",
        blocker_fingerprint="f" * 64, reporting_completed={"thread": True}, reporting_attempts={"thread": 1})
    service._status(state="BLOCKED_HOLD", reason="native_canonical_reconciliation_required",
                    recovery_obligations=["terminal_claim_reconciliation"])
    service._status(state="STOPPED")
    restarted = service_at(tmp_path)
    state = restarted._read_status()
    for key in ("state", "mission_id", "reason", "blocker_fingerprint", "reporting_completed", "reporting_attempts"):
        assert state[key] == original[key]


@pytest.mark.parametrize("kind", ["retired", "owner_notice", "blocked_claim"])
def test_F2_review_R1_watch_and_restart_have_no_reconciliation_effects(tmp_path, kind):
    from modules.charlie.native_runner.service import ProcessLock
    plane = Plane()
    if kind == "retired": retire_in_memory(plane)
    elif kind == "owner_notice": plane.native.update(execution_status="OWNER_DECISION_REQUIRED", head_sha="b" * 40)
    else: plane.native.update(execution_status="BLOCKED", worker_claim_id="HNC-EXISTING")
    prior = copy.deepcopy(plane.metadata); writes = len(plane.writes)
    effects = []
    plane.api.blocker = lambda *a, **k: effects.append("canonical_blocker") or {"success": True}
    service = service_at(tmp_path, plane.api)
    service.notifier = SimpleNamespace(post=lambda *a, **k: effects.append("notification"))

    class Stop:
        polls = 0
        def is_set(self): return self.polls >= 3
        def wait(self, _):
            with pytest.raises(NativeExecutionError):
                with ProcessLock(service.worktree_root / ".charlie-native-runner.lock"):
                    raise AssertionError("second writer entered")
            self.polls += 1
            return self.is_set()

    with patch.object(service, "_process", side_effect=AssertionError("reconciliation execution")) as execute:
        assert service.watch(stop_event=Stop()) == 0
    assert not execute.called and effects == []
    assert plane.metadata == prior and len(plane.writes) == writes
    assert len(plane.requests) == (2 if kind == "retired" else 1)
    saved = service._read_status()
    assert saved["state"] == "BLOCKED_HOLD" and saved["process_state"] == "STOPPED"
    assert not saved.get("reporting_completed") and not saved.get("reporting_attempts")
    # A fresh watch process must not consult an unavailable API or report this hold.
    service = service_at(tmp_path, client_response({"success": False}, 503))
    service.notifier = SimpleNamespace(post=lambda *a, **k: effects.append("notification"))
    with patch.object(service.canonical.client, "request", side_effect=AssertionError("API after held restart")) as request:
        with patch.object(service, "_process", side_effect=AssertionError("restart execution")) as execute:
            assert service.watch(stop_event=Stop()) == 0
    assert not request.called and not execute.called and effects == []
    assert all(service._read_status()[key] == saved[key] for key in
               ("state", "mission_id", "reason", "generation", "native_execution_id", "recovery_obligations"))
    assert not service.repository_root.exists() and not (service.worktree_root / MISSION).exists()


@pytest.mark.parametrize("row", [
    {"mission_id": MISSION, "resume_kind": "hermes_native_execution"},
    {"mission_id": MISSION, "resume_kind": "hermes_native_execution", "native_execution_id": []},
    {"mission_id": MISSION, "resume_kind": "hermes_native_execution", "native_execution_id": ""},
    {"mission_id": MISSION, "resume_kind": "cursor_retirement_pending", "native_execution_id": NATIVE},
    {"mission_id": MISSION, "resume_kind": "cursor_retirement_pending", "native_execution_id": None},
    {**reconciliation_row(), "native_execution_id": []},
    {**reconciliation_row(), "generation": []},
])
def test_F2_review_R2_malformed_kind_identity_never_enters_execution(tmp_path, row):
    service = service_at(tmp_path, client_response({"success": True, "status": "native_recovery_ready", "executions": [row]}))
    service._status(state="IDLE")
    with patch.object(service, "_process", side_effect=AssertionError("malformed identity executed")) as execute:
        with pytest.raises(NativeExecutionError, match="native_discovery_response_invalid"):
            service.once()
    assert not execute.called and service._read_status()["state"] == "BLOCKED"
    assert not service.repository_root.exists() and not (service.worktree_root / MISSION).exists()


@pytest.mark.parametrize("status", [[], {}, None, True, 200])
def test_F2_review_R3_malformed_operation_cannot_leave_healthy_idle(tmp_path, status):
    service = service_at(tmp_path, client_response({"success": True, "status": status, "executions": []}))
    service._status(state="IDLE")
    with patch.object(service, "_process", side_effect=AssertionError("malformed operation executed")) as execute:
        with pytest.raises(NativeExecutionError, match="native_canonical_response_invalid"):
            service.once()
    assert not execute.called and service._read_status()["state"] == "BLOCKED"
    assert not service.repository_root.exists()
