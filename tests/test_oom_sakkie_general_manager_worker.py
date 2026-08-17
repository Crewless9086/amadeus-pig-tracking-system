from datetime import datetime, timedelta, timezone

import pytest

from modules.oom_sakkie.general_manager_worker import (
    ManagerCaseError, PostgresManagerCaseStore, normalize_candidate)


NOW = datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)


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
