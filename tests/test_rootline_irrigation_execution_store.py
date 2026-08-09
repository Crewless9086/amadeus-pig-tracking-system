from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import uuid
import json

import pytest

from modules.telemetry.rootline_irrigation_execution_store import (
    _claim_single_auxiliary, _claim_single_controller, _event_id,
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
        connection.execute(migration.read_text(encoding="utf-8"))
    suffix=uuid.uuid4().hex
    key=f"ROOTLINE-BC-CONSUMPTION-{suffix}"
    def claim(index):
        return _claim_single_controller({"execution_id":f"ROOTLINE-EXEC-{suffix}-{index}",
            "consumption_key":key,"zone_id":"B12345"})
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
