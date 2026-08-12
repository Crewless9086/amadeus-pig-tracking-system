from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from pathlib import Path
import uuid
import json

import pytest

from modules.telemetry.rootline_irrigation_execution_store import (
    _claim_single_auxiliary, _claim_single_controller, _daily_dispatch_blocker,
    _event_id, _stored_event_body,
    _is_active_candidate,
)


def test_on_claim_identity_is_atomic_and_stable_across_replay():
    first = _event_id("claim_before_on", {"execution_id": "EXEC-1", "zone_id": "B12345"})
    replay = _event_id("claim_before_on", {"execution_id": "EXEC-1", "zone_id": "B12345",
                                            "untrusted_extra": "ignored"})
    other = _event_id("claim_before_on", {"execution_id": "EXEC-2", "zone_id": "B12345"})
    assert first == replay and first != other


def test_off_attempt_claims_are_unique_per_execution_and_attempt():
    identities = {_event_id("claim_off_attempt", {"execution_id": "EXEC-1", "attempt": n})
                  for n in (1, 2, 3)}
    assert len(identities) == 3
    assert _event_id("claim_off_attempt", {"execution_id": "EXEC-1", "attempt": 1}) in identities


def test_store_action_cannot_be_shadowed_by_loaded_active_payload():
    value=_stored_event_body("record_completed",{
        "execution_id":"EXEC-1","action":"mark_active","state":"Completed"},"EVENT-1")
    assert value["action"]=="record_completed"
    assert value["event_id"]=="EVENT-1"


def test_completed_shaped_mark_active_is_not_an_active_candidate():
    assert not _is_active_candidate(
        {"action":"mark_active","state":"Completed"},"mark_active","claim_before_on")
    assert _is_active_candidate(
        {"action":"mark_active","state":"Active"},"mark_active","claim_before_on")
    assert _is_active_candidate(
        {"action":"claim_before_on","state":"claimed"},"mark_active","claim_before_on")


def test_typed_history_append_call_casts_numeric_runtime_arguments():
    source=Path("modules/telemetry/rootline_irrigation_execution_store.py").read_text(encoding="utf-8")
    assert "%s::numeric,%s::numeric,%s::jsonb" in source


class DailyCursor:
    def __init__(self, answers, rows=()): self.answers=iter(answers); self.rows=rows; self.sql=[]
    def execute(self, statement, params=None): self.sql.append((statement,params))
    def fetchone(self): return next(self.answers)
    def fetchall(self): return self.rows


def test_daily_guard_requires_persisted_exact_eligibility_before_completion_checks():
    cursor=DailyCursor([None])
    status=_daily_dispatch_blocker(cursor,execution_id="EXEC-1",eligibility_id="ELIG-1",
        eligibility_sha256="a"*64,zone_id="B12345",operating_date="2026-08-12")
    assert status=="canonical_eligibility_unproven" and len(cursor.sql)==1


def test_daily_guard_rejects_existing_verified_completion_before_provider_on(monkeypatch):
    monkeypatch.setattr("modules.telemetry.rootline_irrigation_history.project_canonical_irrigation_history",
        lambda rows,snapshot_cutoff:{"zones":{"B12345":{"verified_completed_days":["2026-08-12"]}}})
    cursor=DailyCursor([(1,),(datetime(2026,8,12,tzinfo=timezone.utc),)])
    status=_daily_dispatch_blocker(cursor,execution_id="EXEC-2",eligibility_id="ELIG-2",
        eligibility_sha256="b"*64,zone_id="B12345",operating_date="2026-08-12")
    assert status=="zone_daily_completion_already_credited" and len(cursor.sql)==3


def test_daily_guard_rejects_prior_accepted_on_during_delayed_completion_window(monkeypatch):
    monkeypatch.setattr("modules.telemetry.rootline_irrigation_history.project_canonical_irrigation_history",
        lambda rows,snapshot_cutoff:{"zones":{"B12345":{"verified_completed_days":[]}}})
    cursor=DailyCursor([(1,),(datetime(2026,8,12,tzinfo=timezone.utc),),(1,)])
    status=_daily_dispatch_blocker(cursor,execution_id="EXEC-2",eligibility_id="ELIG-2",
        eligibility_sha256="b"*64,zone_id="B12345",operating_date="2026-08-12")
    assert status=="zone_daily_on_already_accepted" and len(cursor.sql)==4


def test_daily_guard_allows_other_zone_or_day_when_all_atomic_checks_are_clear(monkeypatch):
    monkeypatch.setattr("modules.telemetry.rootline_irrigation_history.project_canonical_irrigation_history",
        lambda rows,snapshot_cutoff:{"zones":{"C12345":{"verified_completed_days":[]}}})
    cursor=DailyCursor([(1,),(datetime(2026,8,12,tzinfo=timezone.utc),),None])
    assert _daily_dispatch_blocker(cursor,execution_id="EXEC-C",eligibility_id="ELIG-C",
        eligibility_sha256="c"*64,zone_id="C12345",operating_date="2026-08-13") is None


def test_auxiliary_claim_and_off_identities_are_stable_and_separate():
    claim=_event_id("claim_auxiliary_before_on",{"execution_id":"AUX-1"})
    assert claim==_event_id("claim_auxiliary_before_on",{
        "execution_id":"AUX-1","untrusted_extra":"ignored"})
    assert _event_id("claim_auxiliary_off_attempt",{
        "execution_id":"AUX-1","attempt":1})!=_event_id(
            "claim_auxiliary_off_attempt",{"execution_id":"AUX-1","attempt":2})


@pytest.mark.skipif(not os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL"),
                    reason="disposable ROOTLINE PostgreSQL URL is required")
def test_auxiliary_consumption_is_atomic_without_blocking_bc_claim(monkeypatch):
    import psycopg
    url=os.environ["ROOTLINE_DISPOSABLE_POSTGRES_URL"];monkeypatch.setenv("DATABASE_URL",url)
    migration=Path("supabase/migrations/202607070001_create_sam_live_stock_conversation_review_events.sql")
    with psycopg.connect(url) as connection:connection.execute(migration.read_text(encoding="utf-8"))
    suffix=uuid.uuid4().hex;key=f"ROOTLINE-AUX-CONSUME-{suffix}"
    def claim(index):
        return _claim_single_auxiliary({"execution_id":f"ROOTLINE-AUX-{suffix}-{index}",
            "consumption_key":key,"auxiliary_device_id":"FERTILIZER-INJECTION-CH1"})
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(claim,(1,2)))
    assert sum(item.get("created") is True for item in results)==1
    assert sorted(item.get("status") for item in results)==[
        "claimed","eligibility_already_consumed"]


@pytest.mark.skipif(not os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL"),
                    reason="disposable ROOTLINE PostgreSQL URL is required")
def test_consumption_key_is_atomically_single_use_across_regenerated_executions(monkeypatch):
    import psycopg
    url=os.environ["ROOTLINE_DISPOSABLE_POSTGRES_URL"]
    monkeypatch.setenv("DATABASE_URL",url)
    migration=Path("supabase/migrations/202607070001_create_sam_live_stock_conversation_review_events.sql")
    with psycopg.connect(url) as connection:
        connection.execute(Path("supabase/migrations/202605230001_create_irrigation_tables.sql").read_text(encoding="utf-8"))
        connection.execute(migration.read_text(encoding="utf-8"))
    suffix=uuid.uuid4().hex
    key=f"ROOTLINE-BC-CONSUMPTION-{suffix}"
    def claim(index):
        execution=f"ROOTLINE-EXEC-{suffix}-{index}"
        eligibility=f"ROOTLINE-ELIG-{suffix}-{index}"
        digest=(str(index)*64)[:64]
        with psycopg.connect(url) as connection:
            connection.execute("""insert into public.sam_live_stock_conversation_review_events
                (review_event_id,chatwoot_conversation_id,event_source,recommended_action,review_json)
                values (%s,%s,'rootline_irrigation_execution','record_eligibility',%s::jsonb)""",
                (f"ROOTLINE-TEST-ELIG-{suffix}-{index}",execution,json.dumps({
                    "rootline_execution":{"action":"record_eligibility","execution_id":execution,
                    "eligibility_id":eligibility,"eligibility_sha256":digest,
                    "operating_date":"2026-08-12","zone_id":"B12345"}})))
        return _claim_single_controller({"execution_id":execution,
            "eligibility_id":eligibility,"eligibility_sha256":digest,
            "consumption_key":key,"zone_id":"B12345","operating_date":"2026-08-12"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(claim,(1,2)))
    assert sum(item.get("created") is True for item in results)==1
    assert sorted(item.get("status") for item in results)==[
        "claimed","eligibility_already_consumed"]
    winner=1 if results[0].get("created") else 2
    execution=f"ROOTLINE-EXEC-{suffix}-{winner}"
    with psycopg.connect(url) as connection:
        connection.execute("""insert into public.sam_live_stock_conversation_review_events
            (review_event_id,chatwoot_conversation_id,event_source,recommended_action,review_json)
            values (%s,%s,'rootline_irrigation_execution','record_completed',%s::jsonb)""",
            (f"ROOTLINE-TEST-TERMINAL-{suffix}",execution,
             json.dumps({"rootline_execution":{"action":"record_completed",
                 "execution_id":execution,"shutdown_verified":True}})))
