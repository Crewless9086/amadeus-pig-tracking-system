from datetime import datetime, timedelta, timezone
import os
import uuid

import pytest

from modules.telemetry.rootline_water_balance import (
    RULE_VERSION, append_zone_water_balance, build_learning_proposal,
    build_zone_water_balance, notification_projection,
)

NOW=datetime(2026,8,9,10,0,tzinfo=timezone.utc)
ACTIVATION=datetime(2026,8,9,9,0,tzinfo=timezone.utc)


def rain(mm,**changes):
    value={"station_id":"farm-weather-station","observed_at":NOW.isoformat(),
        "rain_mm":mm,"coverage":"B/C nearby station","fresh":True}
    value.update(changes);return value


def balance(zone="B12345",mm=0,**kwargs):
    observed=kwargs.pop("observed_rain",rain(mm))
    return build_zone_water_balance(zone,activation_at=ACTIVATION,
        complete_through=NOW,observed_rain=observed,now=NOW,**kwargs)


def test_no_rain_and_forecast_only_create_zero_delivered_credit():
    value=balance(mm=0,forecast={"status":"fresh","rain_mm":40,
        "observed_at":NOW.isoformat()})
    assert value["obligation_effect"]=="no credit"
    assert value["forecast"]["delivered_water_credit_mm"]==0
    assert value["forecast_water_credit_mm"]==0
    assert value["schedule_debt_rewritten"] is False


def test_trace_rain_holds_without_discharge():
    value=balance(mm=1.9)
    assert value["obligation_effect"]=="Hold with no credit"
    assert value["effective_rainfall_mm"]==0
    assert value["partial_obligation_credit"]==0


def test_soaking_rain_credits_b_and_c_differently_and_caps_need():
    b=balance("B12345",25);c=balance("C12345",25)
    assert b["effective_rainfall_mm"]==14
    assert b["obligation_effect"]=="satisfied"
    assert c["effective_rainfall_mm"]==11.25
    assert c["obligation_effect"]=="partial credit"
    assert b["credited_supply_mm"]<=14 and c["credited_supply_mm"]<=14


def test_verified_irrigation_plus_rain_caps_without_double_counting():
    outcomes=[{"execution_id":"EXEC-1","zone_id":"B12345",
        "completed_at":NOW.isoformat(),"shutdown_verified":True,
        "verified_runtime_minutes":60}]
    value=balance(mm=20,irrigation_outcomes=outcomes)
    assert value["verified_irrigation"]["credited_mm"]==7
    assert value["effective_rainfall_mm"]==12
    assert value["credited_supply_mm"]==14
    assert value["remaining_water_need_mm"]==0
    assert value["verified_irrigation"]["outcomes"][0]["method"]==(
        "layout_derived_runtime_estimate")


def test_on_receipt_or_wrong_zone_never_earns_irrigation_credit():
    rows=[{"execution_id":"ON-ONLY","zone_id":"B12345","completed_at":NOW.isoformat(),
        "shutdown_verified":False,"verified_runtime_minutes":60},
        {"execution_id":"C-EXEC","zone_id":"C12345","completed_at":NOW.isoformat(),
         "shutdown_verified":True,"verified_runtime_minutes":60}]
    value=balance(mm=0,irrigation_outcomes=rows)
    assert value["verified_irrigation"]["credited_mm"]==0
    assert value["on_receipts_counted"]==0


def test_activation_boundary_prevents_manufactured_historical_credit():
    old=rain(30,observed_at=(ACTIVATION-timedelta(seconds=1)).isoformat())
    value=build_zone_water_balance("B12345",activation_at=ACTIVATION,
        complete_through=NOW,observed_rain=old,now=NOW)
    assert value["observed_rain"]["status"]=="outside_activation_boundary"
    assert value["effective_rainfall_mm"]==0
    crossing=balance(observed_rain=rain(30,coverage_start=(
        ACTIVATION-timedelta(seconds=1)).isoformat()))
    assert crossing["observed_rain"]["status"]=="coverage_crosses_activation_boundary"
    assert crossing["effective_rainfall_mm"]==0


def test_stale_and_conflicting_evidence_fail_only_rain_credit():
    stale=balance(observed_rain=rain(10,fresh=False))
    conflict=balance(observed_rain=rain(10,conflicting=True))
    assert stale["obligation_effect"]==conflict["obligation_effect"]=="Needs Data"
    assert stale["schedule_debt_rewritten"] is False
    duplicate={"execution_id":"DUP","zone_id":"B12345","completed_at":NOW.isoformat(),
        "shutdown_verified":True,"verified_runtime_minutes":60}
    changed=dict(duplicate,verified_runtime_minutes=30)
    conflict_irrigation=balance(irrigation_outcomes=[duplicate,changed])
    assert conflict_irrigation["obligation_effect"]=="Needs Data"


def test_replay_identity_and_notification_are_deterministic():
    first=balance(mm=10);replay=balance(mm=10)
    assert first["water_balance_event_id"]==replay["water_balance_event_id"]
    assert notification_projection(first,first["evidence_digest"])["unchanged_silent"]
    assert notification_projection(first,None)["emit"] is True


def test_learning_is_versioned_review_only_and_cannot_silently_apply():
    value=build_learning_proposal(current_rule_version=RULE_VERSION,
        proposed_changes={"B12345":{"coefficient":0.58}},evidence_ids=["OBS-1"],
        rationale="owner soil-depth correction",now=NOW)
    assert value["status"]=="review_required"
    assert value["auto_apply"] is False and value["production_policy_changed"] is False


class FakeDatabase:
    def __enter__(self):return self
    def __exit__(self,*_args):return False
    def cursor(self):return self
    def execute(self,_sql,params):self.params=params
    def fetchone(self):return [False]


def test_exact_replay_store_returns_zero_new_rows(monkeypatch):
    import sys,types
    fake=types.SimpleNamespace(connect=lambda *_args,**_kwargs:FakeDatabase())
    monkeypatch.setitem(sys.modules,"psycopg",fake)
    result=append_zone_water_balance(balance(mm=10),"postgres://disposable")
    assert result["status"]=="exact_replay" and result["created"] is False


@pytest.mark.skipif(not os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL"),
    reason="disposable ROOTLINE PostgreSQL URL is required")
def test_disposable_postgres_append_only_replay_and_schedule_separation():
    import psycopg
    url=os.environ["ROOTLINE_DISPOSABLE_POSTGRES_URL"]
    now=datetime.now(timezone.utc);activation=now-timedelta(minutes=1)
    value=build_zone_water_balance("B12345",activation_at=activation,
        complete_through=now,observed_rain={"station_id":"test-station-"+uuid.uuid4().hex,
            "observed_at":now.isoformat(),"coverage_start":activation.isoformat(),
            "rain_mm":10,"coverage":"B/C","fresh":True},now=now)
    with psycopg.connect(url,connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select count(*) from public.irrigation_events")
            before=cursor.fetchone()[0]
    first=append_zone_water_balance(value,url);replay=append_zone_water_balance(value,url)
    assert first["created"] is True and replay["created"] is False
    with psycopg.connect(url,connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select count(*) from public.irrigation_events")
            assert cursor.fetchone()[0]==before
