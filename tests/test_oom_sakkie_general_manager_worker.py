from datetime import datetime, timedelta, timezone

import pytest

from modules.oom_sakkie.general_manager_worker import (
    ManagerCaseError, PostgresManagerCaseStore, build_scheduled_brain_guard_audit,
    normalize_candidate, run_general_manager_cycle)


NOW = datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)


def test_scheduled_brain_guard_audit_is_revision_bound_and_time_stable():
    result = {"version": "alignment.v1", "passed": True, "findings": [],
              "checked_files": ["b.md", "a.md"]}
    first = build_scheduled_brain_guard_audit(
        source_revision="abc123", now=NOW, alignment_result=result)
    later = build_scheduled_brain_guard_audit(
        source_revision="abc123", now=NOW + timedelta(minutes=5), alignment_result=result)
    assert first["passed"] is True
    assert first["status"] == "brain_guard_alignment_passed"
    assert first["checked_files"] == ["a.md", "b.md"]
    assert first["checked_count"] == 2
    assert first["evidence_digest"] == later["evidence_digest"]
    assert first["observed_at"] != later["observed_at"]
    changed = build_scheduled_brain_guard_audit(
        source_revision="def456", now=NOW, alignment_result=result)
    assert changed["evidence_digest"] != first["evidence_digest"]


def test_scheduled_brain_guard_audit_preserves_failure_findings():
    audit = build_scheduled_brain_guard_audit(
        source_revision="abc123", now=NOW,
        alignment_result={"version": "alignment.v1", "passed": False,
                          "findings": ["missing authority"], "checked_files": []})
    assert audit["passed"] is False
    assert audit["status"] == "brain_guard_alignment_failed"
    assert audit["findings"] == ["missing authority"]


def test_current_beacon_generation_retires_every_older_unconsumed_card():
    commands = []

    class Cursor:
        def execute(self, sql, params):
            commands.append((sql, params))
        def fetchone(self):
            return ("OOM-CASE-BEACON", 26)

    PostgresManagerCaseStore._retire_stale_beacon_claims(
        Cursor(), "general-manager:beacon", NOW)
    update, params = commands[-1]
    assert "c.status in ('active','executing','completed')" in update
    assert "beacon_protected_publication_consumers" in update
    assert "coalesce(result_payload,'{}'::jsonb)" in update
    assert params[2] == "scheduled:OOM-CASE-BEACON:G%"
    assert params[3] == "scheduled:OOM-CASE-BEACON:G26"
    assert "c.provider_message_id like %s" in update
    assert "superseded_by_current_manager_generation" in params[0]


def test_beacon_reconciliation_checks_claimed_publication_point_of_no_return():
    commands = []

    class Cursor:
        responses = [("old", 26, "waiting_reassessment", None, None, []), (1,)]
        def execute(self, sql, params):
            commands.append((sql, params))
        def fetchone(self):
            return self.responses.pop(0)

    candidate = {"case_id": "CASE-A", "dedupe_key": "beacon:a",
        "specialist": "BEACON", "urgency": "planned", "evidence_digest": "new",
        "evidence_refs": [], "unknowns": [], "summary": "summary",
        "next_action": "next", "next_reassessment_at": NOW.isoformat()}
    result = PostgresManagerCaseStore(connect_factory=lambda: None)._reconcile(
        Cursor(), candidate, NOW)
    assert result == "deferred"
    assert "beacon_protected_publication_consumers" in commands[-1][0]
    assert commands[-1][1] == ("scheduled:CASE-A:G26",)


def test_terminal_completed_candidate_closes_existing_case_without_delivery():
    commands = []
    class Cursor:
        responses = [("old", 2, "waiting_reassessment", None, None,
                      ["pig:PIG-A", "observation:OLD"])]
        def execute(self, sql, params): commands.append((sql, params))
        def fetchone(self): return self.responses.pop(0)
    candidate = normalize_candidate(_candidate(dedupe_key="herdmaster:bulk-condition:PIG-A",
        evidence_refs=["pig:PIG-A", "observation:NEW"], terminal_state="completed"), now=NOW)
    result = PostgresManagerCaseStore(connect_factory=lambda: None)._reconcile(Cursor(), candidate, NOW)
    assert result == "changed"
    assert any("status='completed'" in sql for sql, _ in commands)
    assert any("oom_manager_case_events" in sql and params[3] == "completed"
               for sql, params in commands)


def test_cycle_wrapper_supplies_current_brain_guard_audit_to_store():
    class Store:
        def run_cycle(self, candidates, **kwargs):
            return {"candidates": list(candidates), **kwargs}

    result = run_general_manager_cycle(
        candidates=[], now=NOW, source_revision="abc123", store=Store())
    audit = result["brain_guard_audit"]
    assert audit["source_revision"] == "abc123"
    assert audit["passed"] is True
    assert audit["checked_count"] > 0


def test_failed_brain_guard_is_persisted_and_blocks_case_delivery():
    commands = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, params): commands.append((sql, params))

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
        def close(self): pass

    delivered = []
    audit = build_scheduled_brain_guard_audit(
        source_revision="abc123", now=NOW,
        alignment_result={"version": "alignment.v1", "passed": False,
                          "findings": ["conflicting doctrine"], "checked_files": ["bad.md"]})
    result = PostgresManagerCaseStore(connect_factory=Connection).run_cycle(
        [_candidate()], now=NOW, source_revision="abc123",
        deliver=lambda case: delivered.append(case), brain_guard_audit=audit)
    assert result["success"] is False
    assert result["brain_guard"]["status"] == "brain_guard_alignment_failed"
    assert delivered == []
    assert not any("from app_private.oom_manager_cases" in sql for sql, _ in commands)
    failure_writes = [(sql, params) for sql, params in commands
                      if "status,case_counts,completed_at" in sql]
    assert len(failure_writes) == 1
    assert "brain_guard_alignment_failed" in failure_writes[0][1][-2]
    assert '"kind": "ManagerCaseError"' in failure_writes[0][1][-2]
    assert '"code": "scheduled_brain_guard_alignment_failed"' in failure_writes[0][1][-2]


def test_audit_commit_uses_separate_connection_from_manager_work():
    connections = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, _sql, _params): pass
        def fetchall(self): return []

    class Connection:
        def __init__(self):
            self.closed = False
            connections.append(self)
        def __enter__(self):
            if self.closed:
                raise RuntimeError("closed connection reused")
            return self
        def __exit__(self, *_args):
            self.closed = True
            return False
        def cursor(self): return Cursor()
        def close(self): self.closed = True

    audit = build_scheduled_brain_guard_audit(
        source_revision="abc123", now=NOW,
        alignment_result={"version": "alignment.v1", "passed": True,
                          "findings": [], "checked_files": ["one.md"]})
    result = PostgresManagerCaseStore(connect_factory=Connection).run_cycle(
        [], now=NOW, source_revision="abc123", brain_guard_audit=audit)
    assert result["success"] is True
    assert len(connections) == 3
    assert len({id(connection) for connection in connections}) == 3


def test_audit_checkpoint_uses_existing_started_status_vocabulary():
    commands = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, params): commands.append((sql, params))
        def fetchall(self): return []

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
        def close(self): pass

    audit = build_scheduled_brain_guard_audit(
        source_revision="abc123", now=NOW,
        alignment_result={"version": "alignment.v1", "passed": True,
                          "findings": [], "checked_files": ["one.md"]})
    result = PostgresManagerCaseStore(connect_factory=Connection).run_cycle(
        [], now=NOW, source_revision="abc123", brain_guard_audit=audit)
    assert result["success"] is True
    checkpoint = next(params for sql, params in commands
                      if "next_cycle_at,status,case_counts" in sql)
    assert checkpoint[-2] == "started"
    assert "brain_guard_alignment_passed" in checkpoint[-1]


def _candidate(**changes):
    value = {
        "dedupe_key": "rootline:current-plan",
        "specialist": "ROOTLINE",
        "urgency": "urgent",
        "evidence_refs": ["event:one"],
        "unknowns": ["delivered_current_irrigation_plan"],
        "summary": "Current plan remains contained.",
        "next_action": "Delegate to ROOTLINE and retain ownership.",
        "next_reassessment_at": (NOW + timedelta(minutes=15)).isoformat(),
    }
    value.update(changes)
    return value


def test_candidate_identity_is_stable_when_only_reassessment_time_moves():
    first = normalize_candidate(_candidate(), now=NOW)
    later = normalize_candidate(_candidate(
        next_reassessment_at=(NOW + timedelta(minutes=30)).isoformat()), now=NOW)
    assert first["case_id"] == later["case_id"]
    assert first["evidence_digest"] == later["evidence_digest"]


def test_evidence_change_changes_generation_digest():
    first = normalize_candidate(_candidate(), now=NOW)
    changed = normalize_candidate(_candidate(evidence_refs=["event:two"]), now=NOW)
    assert first["evidence_digest"] != changed["evidence_digest"]


def test_observation_epoch_does_not_create_a_new_material_digest():
    first = normalize_candidate(_candidate(
        evidence_refs=["event:one", "observed:2026-08-17T10:00:00+00:00"]), now=NOW)
    later = normalize_candidate(_candidate(
        evidence_refs=["event:one", "observed:2026-08-17T10:05:00+00:00"]), now=NOW)
    assert first["evidence_digest"] == later["evidence_digest"]


@pytest.mark.parametrize(("lease_until", "expected"), [
    (NOW + timedelta(minutes=2), "deferred"),
    (NOW - timedelta(minutes=2), "replayed")])
def test_changed_evidence_cannot_replace_a_delegated_generation(lease_until, expected):
    class Cursor:
        def __init__(self): self.commands=[]
        def execute(self, sql, params): self.commands.append((sql, params))
        def fetchone(self):
            return ("a"*64, 1, "delegated", "oom-sakkie-general-manager-v1",
                    lease_until, ["observed:2026-08-17T10:00:00+00:00"])
    cursor=Cursor()
    candidate=normalize_candidate(_candidate(evidence_refs=["event:new"]), now=NOW)
    result=PostgresManagerCaseStore(connect_factory=lambda: None)._reconcile(cursor,candidate,NOW)
    assert result == expected
    assert len(cursor.commands) == 1


def test_failed_reclaimed_worker_cannot_downgrade_confirmed_generation():
    class Cursor:
        def __init__(self): self.commands=[]
        def __enter__(self): return self
        def __exit__(self,*_args): return False
        def execute(self,sql,params): self.commands.append((sql,params))
        def fetchone(self):
            return (1,"d"*64,"d"*64,"waiting_reassessment","cycle-two",
                    NOW + timedelta(minutes=2))
    class Connection:
        def __init__(self,cursor): self.value=cursor
        def __enter__(self): return self
        def __exit__(self,*_args): return False
        def cursor(self): return self.value
    cursor=Cursor()
    store=PostgresManagerCaseStore(connect_factory=lambda: Connection(cursor))
    case={"case_id":"OOM-CASE-ONE","generation":1,"evidence_digest":"d"*64,
          "next_reassessment_at":NOW.isoformat()}
    store._finish_claim(case,{"success":False,"status":"ambiguous"},NOW,"cycle-two")
    assert len(cursor.commands) == 1


def test_confirmed_duplicate_releases_claim_and_reschedules_without_delivery():
    class Cursor:
        def __init__(self): self.commands=[]
        def __enter__(self): return self
        def __exit__(self,*_args): return False
        def execute(self,sql,params): self.commands.append((sql,params))
        def fetchone(self):
            return (1,"d"*64,"d"*64,"delegated","cycle-two",
                    NOW + timedelta(minutes=2))
    class Connection:
        def __init__(self,cursor): self.value=cursor
        def __enter__(self): return self
        def __exit__(self,*_args): return False
        def cursor(self): return self.value
    cursor=Cursor(); store=PostgresManagerCaseStore(connect_factory=lambda: Connection(cursor))
    case={"case_id":"OOM-CASE-ONE","generation":1,"evidence_digest":"d"*64,
          "next_reassessment_at":NOW.isoformat()}
    store._finish_claim(case,{"success":True,"status":"manager_delivery_duplicate_suppressed",
        "next_reassessment_at":(NOW+timedelta(minutes=5)).isoformat()},NOW,"cycle-two")
    assert any("update app_private.oom_manager_cases set status" in sql for sql,_ in cursor.commands)


@pytest.mark.parametrize("field,value", [
    ("specialist", "UNKNOWN"), ("urgency", "panic"),
    ("evidence_refs", []), ("dedupe_key", "bad key"),
])
def test_candidate_contract_fails_closed(field, value):
    with pytest.raises(ManagerCaseError):
        normalize_candidate(_candidate(**{field: value}), now=NOW)
