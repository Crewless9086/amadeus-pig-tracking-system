"""Observation-only takeover on the actual append-only store; no provider I/O."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from copy import deepcopy
import importlib
import json
import os
from pathlib import Path
import uuid
import pytest
import psycopg
from psycopg.types.json import Jsonb
from modules.telemetry import rootline_borehole_commissioning as borehole
store = importlib.import_module("modules.telemetry.rootline_irrigation_execution_store")
from tests.test_rootline_borehole_commissioning import BoreholeTransport
from tests.test_rootline_continuous_borehole import snapshot

MIGRATION_PATH = Path(__file__).resolve().parents[1] / "supabase/migrations/202607070001_create_sam_live_stock_conversation_review_events.sql"
URL = os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="explicit disposable ROOTLINE database required")


def now(): return datetime.now(timezone.utc)


def proof(state="ON", stamp=None):
    return {"authoritative": True, "state": state, "device_id": "1002851416", "channel": 1,
        "evidence_id": "a"*64, "retrieved_at": (stamp or now()).isoformat(),
        "borehole_configuration": {"online": True, "native_auto_off_enabled": False}}


def baseline():
    return {"current": True, "stop_mode": "conditions", "registry_generation": 3,
        "baseline_sha256": "b"*64, "maximum_routine_runtime_seconds": 0, "native_fail_stop_seconds": 0}


class Transport(BoreholeTransport):
    def __init__(self): super().__init__(); self.state = "ON"
    def read_output_state(self, **kwargs): return proof(self.state)
    def prepare_execution_capacity(self, _): pytest.fail("adoption must reserve no ON capacity")
    def set_state(self, **kwargs):
        assert kwargs["state"] == "OFF", "adoption must never send ON"
        return super().set_state(**kwargs)


def record_interlocks(**facts):
    evidence = "SYNTHETIC-INTERLOCK-" + uuid.uuid4().hex
    body = {"state": "completed", "outcome": {"borehole_interlocks": {
        **facts, "observed_at": now().isoformat(), "evidence_id": evidence}}}
    with psycopg.connect(URL) as db:
        db.execute("insert into public.sam_live_stock_conversation_review_events(review_event_id,event_source,review_json) values(%s,'oom_sakkie_rootline_operational_intake',%s)",
            (evidence, Jsonb({"rootline_operational_intake": body})))


@pytest.fixture
def database(monkeypatch):
    from psycopg.conninfo import conninfo_to_dict
    target = conninfo_to_dict(URL)
    assert target.get("host") == "127.0.0.1" and target.get("dbname") in {
        "rootline_managed", "rootline_manual_on_adoption_test_20261117_01"}
    with psycopg.connect(URL) as connection:
        connection.execute(MIGRATION_PATH.read_text())
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setattr(store, "EVENT_SOURCE", "SYNTHETIC-ADOPTION-" + uuid.uuid4().hex)
    record_interlocks(manual_off_active=False, manual_isolation_active=False,
        dry_run_safe=True, low_water_clear=True, supply_pressure_safe=True, full_tank_cutoff_fault=False)
    try:
        yield URL
    finally:
        # Keep append-only evidence; avoid leaking a synthetic hold to other tests.
        record_interlocks(manual_off_active=False, manual_isolation_active=False,
            dry_run_safe=True, low_water_clear=True, supply_pressure_safe=True, full_tank_cutoff_fault=False)


def artifact(*, forecast=False, rain=False, energy=None, interlocks=None, authority=True, output=None):
    stamp = now()
    conditions = store.rootline_irrigation_execution_store("assess_borehole_conditions", {
        "weather_snapshot": snapshot(now=stamp, rate=.1 if rain else 0),
        "forecast": {"observed_at": stamp.isoformat(), "days": [{"rain_sum_mm": 20}]} if forecast else None,
        "protection_safe": True, "protection_evidence": {"safe": True}})
    result = borehole.build_borehole_runtime_eligibility(need={"eligible": True}, baseline=baseline(),
        authority={"inside_standing_authority": authority}, provider=output or proof(stamp=stamp),
        interlocks=interlocks or {}, energy=energy or {"eligible": True, "fresh": True},
        requested_seconds=None, now=now(), conditions=conditions)
    if result["eligible"]:
        assert store.rootline_irrigation_execution_store("record_borehole_eligibility", result)["success"]
    return result


def advance(value, transport):
    return borehole.advance_borehole_execution(eligibility=value,
        store=store.rootline_irrigation_execution_store, transport=transport, now=now(), clock=now)


def rows(value):
    with psycopg.connect(URL) as db:
        with db.cursor() as cursor: return store._managed_edge_rows(cursor, value["execution_id"])


def test_forecast_deferral_takeover_preserves_zero_on_and_original_start_unknown(database):
    art = artifact(forecast=True)
    assert not art["start_gates"]["weather"] and art["eligible"]
    assert store._valid_borehole_eligibility(art)
    transport = Transport(); result = advance(art, transport)
    assert result["status"] == "borehole_observed_on_adopted"
    active = store.rootline_irrigation_execution_store("load_active_borehole", None)
    assert active["original_start_at"] is None and active["on_attempts"] == 0
    assert active["primary_stop_deadline"] is None and active["native_fail_stop_deadline"] is None
    assert active["provider_start_evidence"]["state"] == "ON" and transport.commands == []
    assert [row["action"] for row in rows(art)] == ["record_borehole_eligibility", "mark_borehole_active"]
    denied = store.rootline_irrigation_execution_store("dispatch_borehole_on_edge", {
        **active, "dispatch": lambda: pytest.fail("adoption cannot dispatch ON")})
    assert denied["accepted_unambiguous"] is False


def test_actual_concurrent_adoption_creates_one_owner_and_duplicate_never_starts(database, monkeypatch):
    from threading import Barrier
    barrier = Barrier(2)
    actual = store._claim_borehole_material_load
    def contend(body, *, adopt=False):
        barrier.wait(timeout=5)
        return actual(body, adopt=adopt)
    monkeypatch.setattr(store, "_claim_borehole_material_load", contend)
    art = artifact(); transport = Transport()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: advance(art, transport), range(2)))
    assert sum(r["status"] == "borehole_observed_on_adopted" for r in results) == 1
    assert sum(row["action"] == "mark_borehole_active" for row in rows(art)) == 1
    assert transport.commands == []
    assert advance(art, transport)["status"] == "borehole_active"


def test_restart_unknown_observation_preserves_same_owner_then_observed_off_completes(database):
    art = artifact(); first = Transport(); advance(art, first)
    transport = Transport(); transport.state = "Unknown"
    result = advance({}, transport)
    assert result["status"] == "borehole_active" and result["supervision_evidence_pending"]
    assert result["execution"]["execution_id"] == art["execution_id"] and transport.commands == []
    transport.state = "OFF"
    result = advance({}, transport)
    assert result["status"] == "borehole_completed" and transport.commands == []
    assert result["execution"]["original_start_at"] is None
    assert "verified_runtime_seconds" not in result["execution"]


@pytest.mark.parametrize("trigger", ["rain", "energy", "manual_off", "isolation", "dry_run"])
def test_current_adverse_evidence_is_owned_and_stopped_without_an_on_edge(database, trigger):
    art = artifact(rain=trigger == "rain", energy={"eligible": False, "fresh": True, "reason": "battery_floor"}
        if trigger == "energy" else None)
    if trigger in {"manual_off", "isolation", "dry_run"}:
        record_interlocks(**{"manual_off_active" if trigger == "manual_off" else
            "manual_isolation_active" if trigger == "isolation" else "dry_run_safe": trigger != "dry_run"})
    transport = Transport(); result = advance(art, transport)
    assert result["status"] == "borehole_completed" and result["adopted_observed_on"]
    assert [x["state"] for x in transport.commands] == ["OFF"]
    evidence = rows(art)
    active = next(row for row in evidence if row["action"] == "mark_borehole_active")
    off = next(row for row in evidence if row["action"] == "claim_borehole_off_attempt")
    assert active["stop_requested"] is True and active["stop_trigger"] == off["stop_trigger"]
    assert not any(row["action"] in {"claim_borehole_before_on", "dispatch_borehole_on_edge"} for row in evidence)
    assert store.rootline_irrigation_execution_store("load_active_borehole", None) is None


@pytest.mark.parametrize("state", ["OFF", "Unknown"])
def test_final_changed_or_unknown_output_is_not_adopted_or_commanded(database, state):
    art = artifact(); transport = Transport(); transport.state = state
    result = advance(art, transport)
    assert result["hardware_commands"] == 0 and transport.commands == []
    assert store.rootline_irrigation_execution_store("load_active_borehole", None) is None
    assert [row["action"] for row in rows(art)] == ["record_borehole_eligibility"]


def test_authority_and_exact_identity_are_not_inferred_from_on(database):
    assert not artifact(authority=False)["eligible"]
    invalid = proof(); invalid["channel"] = 2
    assert not artifact(output=invalid)["eligible"]
    stale = proof(stamp=now()-timedelta(seconds=31))
    assert not artifact(output=stale)["eligible"]


def test_competing_existing_owner_is_preserved(database):
    first = artifact(); transport = Transport(); advance(first, transport)
    other = artifact()
    result = advance(other, transport)
    assert result["execution"]["execution_id"] == first["execution_id"]
    assert transport.commands == []
    assert not any(row["action"] == "mark_borehole_active" for row in rows(other))


def test_stop_survives_crash_after_durable_adoption_before_off(database):
    art = artifact(rain=True); transport = Transport()
    def crashed(action, body):
        value = store.rootline_irrigation_execution_store(action, body)
        if action == "adopt_borehole_observed_on" and value.get("created"):
            raise RuntimeError("synthetic crash after committed adoption")
        return value
    with pytest.raises(RuntimeError, match="synthetic crash"):
        borehole.advance_borehole_execution(eligibility=art, store=crashed, transport=transport, now=now(), clock=now)
    assert transport.commands == []
    result = advance({}, transport)
    assert result["status"] == "borehole_completed"
    assert [x["state"] for x in transport.commands] == ["OFF"]



def test_actual_scheduler_composition_adopts_on_while_new_start_plan_waits(database, monkeypatch):
    from modules.telemetry import rootline_execution_runtime as runtime
    from modules.telemetry.rootline_water_energy_plan import ZA_TZ
    monkeypatch.setattr(borehole, "load_registered_borehole_baseline", lambda **kwargs: baseline())
    monkeypatch.setattr(runtime, "build_water_energy_plan", lambda *args, **kwargs: {
        "candidate_tasks": [{"task_id": "borehole", "recommendation": "Wait", "reason": "forecast_start_deferred"}]})
    monkeypatch.setattr("modules.telemetry.weather_service.get_weather_control_snapshot",
        lambda *args, **kwargs: (snapshot(now=now()), 200))
    def evidence_loader(**kwargs):
        stamp = now()
        return ({"power": {"observed_at": stamp.isoformat(), "solar_power_w": 2000},
            "forecast": {"observed_at": stamp.isoformat(), "days": [{"rain_sum_mm": 20}]}},
            stamp.astimezone(ZA_TZ).date().isoformat(), stamp)
    transport = Transport()
    result = runtime.run_rootline_managed_device_reassessment(environ={"ROOTLINE_BOREHOLE_ENABLED": "true"},
        database_url=URL, store=store.rootline_irrigation_execution_store, transport=transport,
        evidence_loader=evidence_loader, now=now(), clock=now)
    active = store.rootline_irrigation_execution_store("load_active_borehole", None)
    assert active is not None, result
    assert active["operation"] == "adopt_observed_on" and active["on_attempts"] == 0
    assert active["condition_evidence"]["reason"] == "forecast_start_deferred"
    assert active["start_gates"]["canonical_need"] is False
    assert transport.commands == []


def test_observed_unsafe_interlock_is_not_erased_by_older_clearance(database):
    art = artifact(interlocks={"dry_run_safe": False})
    assert art["start_gates"]["dry_run"] is False
    transport = Transport(); result = advance(art, transport)
    assert result["status"] == "borehole_completed"
    assert [x["state"] for x in transport.commands] == ["OFF"]
    assert result["execution"]["stop_trigger"]["adoption_interlocks"]["dry_run_safe"] is False


def test_off_committed_while_adoption_waits_on_same_lock_is_not_missed(database):
    from threading import Event
    art = artifact(); read = Event()
    class Observed(Transport):
        def read_output_state(self, **kwargs):
            result = super().read_output_state(**kwargs); read.set(); return result
    transport = Observed()
    with psycopg.connect(URL, autocommit=True) as holder, ThreadPoolExecutor(max_workers=1) as pool:
        with holder.transaction():
            holder.execute("select pg_advisory_xact_lock(%s)", (1874320911,))
            future = pool.submit(advance, art, transport)
            assert read.wait(timeout=3)
            identity = "SYNTHETIC-RACING-OFF-" + uuid.uuid4().hex
            body = {"rootline_operational_intake": {"state": "completed", "outcome": {
                "borehole_interlocks": {"manual_off_active": True,
                    "observed_at": now().isoformat(), "evidence_id": identity}}}}
            holder.execute("insert into public.sam_live_stock_conversation_review_events(review_event_id,event_source,review_json) values(%s,'oom_sakkie_rootline_operational_intake',%s)",
                (identity, Jsonb(body)))
        result = future.result(timeout=5)
    assert result["status"] == "borehole_completed"
    assert [x["state"] for x in transport.commands] == ["OFF"]


def test_new_manual_off_after_takeover_uses_normal_supervisor(database):
    from modules.telemetry.rootline_managed_devices_runtime import run_rootline_managed_device_cycle
    from modules.telemetry.rootline_water_energy_plan import read_current_borehole_faults
    art = artifact(); transport = Transport(); advance(art, transport)
    record_interlocks(manual_off_active=True)
    run_rootline_managed_device_cycle(evidence={}, transport=transport,
        store=store.rootline_irrigation_execution_store, environ={}, allow_new_starts=False,
        now=now(), clock=now, borehole_safety_reader=lambda: read_current_borehole_faults(URL,now=now()),
        borehole_conditions_reader=lambda: {"success": True, "stop_required": False, "reason": "conditions_allow_start"})
    assert [x["state"] for x in transport.commands] == ["OFF"]
    assert store.rootline_irrigation_execution_store("load_active_borehole", None) is None


def test_unavailable_energy_does_not_become_a_stop_or_a_start_permission(database):
    art = artifact(energy={"eligible": False, "fresh": False, "reason": "power_unavailable"})
    assert art["start_gates"]["energy"] is False
    transport = Transport(); result = advance(art, transport)
    assert result["status"] == "borehole_observed_on_adopted" and transport.commands == []
    assert not result["execution"].get("stop_requested")


def test_superseded_condition_snapshot_cannot_take_ownership(database):
    art = artifact()
    store.rootline_irrigation_execution_store("assess_borehole_conditions", {
        "weather_snapshot": snapshot(now=now(), rate=.1), "protection_safe": True})
    transport = Transport(); result = advance(art, transport)
    assert result["status"] == "borehole_observed_on_adoption_unproven"
    assert transport.commands == []
    assert store.rootline_irrigation_execution_store("load_active_borehole", None) is None


@pytest.mark.parametrize("change", [{"device_id": "other-device"}, {"retrieved_at": "2020-01-01T00:00:00+00:00"}])
def test_final_on_must_still_be_fresh_and_exact_identity(database, change):
    art = artifact()
    class InvalidFinal(Transport):
        def read_output_state(self, **kwargs): return {**proof(), **change}
    transport = InvalidFinal(); result = advance(art, transport)
    assert result["status"] == "borehole_current_on_unproven" and transport.commands == []
    assert store.rootline_irrigation_execution_store("load_active_borehole", None) is None
