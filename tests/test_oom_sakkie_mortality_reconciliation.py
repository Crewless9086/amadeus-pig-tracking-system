"""Exact legacy mortality dependency; no farm completion or provider authority."""
from datetime import datetime, timedelta, timezone
from copy import deepcopy
import pytest
from modules.oom_sakkie import herdmaster_case_disposition as disposition
from modules.oom_sakkie import manager_case_sources as sources
from modules.oom_sakkie import general_manager_worker as worker

NOW = datetime(2026, 10, 6, 1, tzinfo=timezone.utc)


def legacy(now=NOW, *, cluster=False):
    digest = "A" * 64
    return {"dedupe_key": "herdmaster:herdmaster:" + ("mortality-cluster:" if cluster else "mortality:") + "a" * 20,
        "specialist": "HERDMASTER", "urgency": "urgent", "unknowns": [],
        "evidence_refs": [digest, "attention:welfare_priority", "herdmaster.daily_manager_evidence.v1",
            "observed:" + (now-timedelta(days=20)).isoformat(),
            "result:HERD-NEXT-" + "B"*24 + ":HERD-DAILY-EVIDENCE-" + digest[:24]],
        "summary": "Historical mortality review remains retained.",
        "next_action": "Review the original mortality evidence.",
        "next_reassessment_at": (now-timedelta(minutes=1)).isoformat()}


def test_exact_legacy_family_requires_complete_original_projection():
    assert disposition.is_legacy_mortality_case(legacy())
    assert disposition.is_legacy_mortality_case(legacy(cluster=True))
    value = legacy(); value["evidence_refs"] = value["evidence_refs"][:-1]
    assert not disposition.is_legacy_mortality_case(value)


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_OWNER_USER_ID", "42")
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "42")
    monkeypatch.delenv("OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON", raising=False)


@pytest.mark.parametrize("change", ["specialist", "family", "key", "key_suffix", "digest", "result", "observed", "naive", "duplicate", "extra", "unknowns"])
def test_incomplete_or_foreign_projection_is_not_pending(change):
    value = legacy()
    if change == "specialist": value["specialist"] = "ROOTLINE"
    elif change == "family": value["message_family"] = "purpose_review"
    elif change == "key": value["dedupe_key"] = "herdmaster:retained-mortality:" + "a"*20
    elif change == "key_suffix": value["dedupe_key"] += "x"
    elif change == "digest": value["evidence_refs"][0] = "unknown"
    elif change == "result": value["evidence_refs"][-1] = value["evidence_refs"][-1][:-1] + "C"
    elif change == "observed": value["evidence_refs"][3] = "observed:unknown"
    elif change == "naive": value["evidence_refs"][3] = "observed:2026-10-05T00:00:00"
    elif change == "duplicate": value["evidence_refs"].append(value["evidence_refs"][0])
    elif change == "extra": value["evidence_refs"].append("protected:report")
    else: value["unknowns"] = ["owner_decision"]
    assert not disposition.is_legacy_mortality_case(value)


def receipt_row():
    claim = worker.normalize_candidate(legacy(), now=NOW)
    claim.update(generation=7, last_delivery_digest="b"*64)
    row = {**claim, "status": "delegated", "assigned_worker_id": "cycle-one",
        "lease_until": (NOW+timedelta(minutes=4)).isoformat(), "last_delivery_at": NOW.isoformat()}
    return claim, row


def receipt(row):
    return disposition.MortalityReconciliationPending(disposition._projection_json(row),
        disposition._mortality_owner_binding(), NOW)


def test_dependency_identity_ignores_only_scheduling_lease_and_read_clock(owner):
    claim, row = receipt_row(); one = receipt(row)
    assert disposition.mortality_pending_matches(one, row, claim, now=NOW, cycle_id="cycle-one")
    changed = {**row, "lease_until": (NOW+timedelta(minutes=8)).isoformat(), "assigned_worker_id": "cycle-two"}
    two = receipt(changed)
    assert one.metadata() == two.metadata()
    assert one.metadata()["completion_proven"] is False and one.metadata()["core_acknowledged"] is False
    changed["generation"] += 1
    assert receipt(changed).metadata()["dependency_id"] != one.metadata()["dependency_id"]


@pytest.mark.parametrize("field,value", [("generation", 8), ("evidence_digest", "c"*64),
    ("evidence_refs", ["unproven"]), ("summary", "new facts"), ("next_action", "current welfare work"),
    ("last_delivery_digest", "d"*64), ("last_delivery_at", None), ("status", "completed"),
    ("assigned_worker_id", "foreign"), ("lease_until", "2026-10-05T00:00:00+00:00"),
    ("next_reassessment_at", "2026-10-07T00:00:00+00:00")])
def test_any_changed_durable_projection_refuses_receipt(owner, field, value):
    claim, row = receipt_row(); proof = receipt(row)
    row[field] = value
    assert not disposition.mortality_pending_matches(proof, row, claim, now=NOW, cycle_id="cycle-one")


@pytest.mark.parametrize("seconds", [-1, 31, 241])
def test_future_stale_or_expired_receipt_refused(owner, seconds):
    claim, row = receipt_row(); proof = receipt(row)
    assert not disposition.mortality_pending_matches(proof, row, claim,
        now=NOW+timedelta(seconds=seconds), cycle_id="cycle-one")


@pytest.mark.parametrize("owner_id,allowed", [("", ""), ("43", "42"), ("42", "43,42"), ("", "42,43")])
def test_current_recipient_ambiguity_refuses(owner, monkeypatch, owner_id, allowed):
    claim, row = receipt_row(); proof = receipt(row)
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_OWNER_USER_ID", owner_id)
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", allowed)
    assert not disposition.mortality_pending_matches(proof, row, claim, now=NOW, cycle_id="cycle-one")


class ReadConnection:
    def __init__(self, rows): self.rows = rows; self.statements = []
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def cursor(self): return self
    def execute(self, sql, params=None): self.statements.append((sql, params)); return self
    def fetchall(self): return [(v,) for v in self.rows]


@pytest.mark.parametrize("returned", ["missing", "duplicate", "foreign", "overflow"])
def test_read_requires_exact_bounded_set(owner, returned):
    claim, row = receipt_row()
    rows = [] if returned == "missing" else [row, row] if returned == "duplicate" else (
        [{**row, "case_id": "FOREIGN"}] if returned == "foreign" else [row]*65)
    db = ReadConnection(rows)
    with pytest.raises(ValueError, match="rows_unproven"):
        disposition.collect_mortality_reconciliation(NOW, claimed_cases=[claim], connect=lambda: db)
    assert sum("from app_private" in sql for sql, _ in db.statements) == 1
    assert db.statements[0][0] == "set transaction isolation level repeatable read read only"


def test_shared_deadline_is_not_extended(owner):
    import time
    claim, _ = receipt_row(); db = ReadConnection([])
    with pytest.raises(TimeoutError):
        disposition.collect_mortality_reconciliation(NOW, claimed_cases=[claim], connect=lambda: db,
            deadline_monotonic=time.monotonic()-1)
    assert not any("from app_private" in sql for sql, _ in db.statements)


def test_explicit_collector_failure_never_becomes_absence_pending(owner, monkeypatch):
    claim, _ = receipt_row()
    error = {"dedupe_key": "runtime:collector:herdmaster", "specialist": "RUNTIME",
        "evidence_refs": ["collector:herdmaster:TimeoutError"]}
    monkeypatch.setattr(disposition, "collect_mortality_reconciliation", lambda *a, **k: pytest.fail("failed collector is not absence"))
    result = sources.collect_manager_refresh_snapshot(now=NOW, cases=[claim], initial_candidates=[error])
    assert isinstance(result[(claim["dedupe_key"], "HERDMASTER")], sources.ManagerCollectorRefreshError)


def test_current_candidate_receives_fresh_normal_owning_refresh(owner, monkeypatch):
    claim, _ = receipt_row(); current = legacy(); current["summary"] = "Current canonical mortality work"
    def _herdmaster(now): return [current]
    monkeypatch.setattr(disposition, "collect_mortality_reconciliation", lambda *a, **k: pytest.fail("current work wins"))
    result = sources.collect_manager_refresh_snapshot(now=NOW, cases=[claim], collectors=(_herdmaster,),
        initial_candidates=[current])
    assert result[(claim["dedupe_key"], "HERDMASTER")]["summary"] == current["summary"]
