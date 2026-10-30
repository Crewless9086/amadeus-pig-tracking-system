"""Disposable PostgreSQL proof of coherent weather and independent output claims."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import os
from concurrent.futures import ThreadPoolExecutor
import uuid
from pathlib import Path

import pytest
from tests.test_rootline_managed_startup_handover_postgres import db, seed, dispatch, store
from modules.telemetry import weather_service as weather

pytestmark=pytest.mark.skipif(not os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL"),reason="disposable PostgreSQL required")
NOW=datetime(2026,10,30,0,20,tzinfo=timezone.utc)


@pytest.fixture
def weather_db(db,monkeypatch):
    import psycopg
    source="timing-"+uuid.uuid4().hex
    monkeypatch.setattr(weather,"DEFAULT_WEATHER_SOURCE_ID",source)
    with psycopg.connect(db) as c:
        migrations=Path(__file__).resolve().parents[1]/"supabase/migrations"
        for name in ("202605210005_create_telemetry_power_tables.sql","202605220001_create_telemetry_weather_tables.sql"):
            c.execute((migrations/name).read_text(encoding="utf-8"))
        c.execute("insert into public.telemetry_sources (source_id,source_type,display_name,provider,stale_after_minutes) values (%s,'weather','synthetic station','synthetic',30)",(source,))
        c.execute("insert into public.weather_latest_state (source_id,reading_at,flags,summary_status,summary_headline,summary_notes) values (%s,%s,'{}','ok','dry','[]')",(source,NOW-timedelta(minutes=1)))
        for minutes in (35,20,1):
            c.execute("insert into public.weather_readings (reading_id,source_id,reading_at,rain_rate_mm_h,rain_today_mm) values (%s,%s,%s,0,0)",(uuid.uuid4().hex,source,NOW-timedelta(minutes=minutes)))
    return db,source


def test_weather_current_and_dry_history_survive_backdated_concurrent_ingestion(weather_db,monkeypatch):
    import psycopg
    from modules.oom_sakkie import bounded_postgres_read
    db,source=weather_db;real=bounded_postgres_read.connect_bounded_read;queries=[]
    class Cursor:
        def __init__(self,inner):self.inner=inner
        def execute(self,sql,params):
            queries.append(sql);self.inner.execute(sql,params)
            # A new reading at/before the fixed cutoff arrives after SELECT's
            # snapshot. Two independently-latest queries would disagree here.
            with psycopg.connect(db) as c:
                c.execute("insert into public.weather_readings (reading_id,source_id,reading_at,rain_rate_mm_h,rain_today_mm) values (%s,%s,%s,1,1)",(uuid.uuid4().hex,source,NOW))
                c.execute("update public.weather_latest_state set reading_at=%s where source_id=%s",(NOW,source))
        def fetchone(self):return self.inner.fetchone()
        def __enter__(self):self.inner.__enter__();return self
        def __exit__(self,*args):return self.inner.__exit__(*args)
    class Connection:
        def __init__(self,inner):self.inner=inner
        def cursor(self):return Cursor(self.inner.cursor())
    @contextmanager
    def captured(**kwargs):
        with real(**kwargs) as c:yield Connection(c)
    with monkeypatch.context() as patch:
        patch.setattr(bounded_postgres_read,"connect_bounded_read",captured)
        snapshot,status=weather.get_weather_control_snapshot(db,now=NOW)
    assert status==200 and len(queries)==1
    end=snapshot["rain_release"]["interval_end_at"]
    assert end==snapshot["weather_current"]["source"]["last_reading_at"]
    assert datetime.fromisoformat(end)==NOW-timedelta(minutes=1)
    assert snapshot["rain_release"]["continuous_zero_rain_confirmed"] is True
    changed,_=weather.get_weather_control_snapshot(db,now=NOW)
    assert changed["weather_current"]["current"]["rain_rate_mm_h"]==1
    assert changed["rain_release"]["continuous_zero_rain_confirmed"] is False


@pytest.mark.parametrize("gate",["stale","unhealthy","rain"])
def test_weather_snapshot_preserves_live_safety_holds(weather_db,gate):
    import psycopg
    db,source=weather_db;at=NOW
    with psycopg.connect(db) as c:
        if gate=="unhealthy":c.execute("update public.weather_latest_state set flags='{\"source_unhealthy\":true}' where source_id=%s",(source,))
        if gate=="rain":c.execute("update public.weather_readings set rain_rate_mm_h=0.5 where source_id=%s and reading_at=%s",(source,NOW-timedelta(minutes=1)))
        if gate=="stale":at=NOW+timedelta(minutes=31)
    snapshot,status=weather.get_weather_control_snapshot(db,now=at)
    assert status==200 and snapshot["rain_release"]["continuous_zero_rain_confirmed"] is False


def test_distinct_auxiliaries_claim_together_but_same_device_replay_is_rejected(db):
    at=datetime.now(timezone.utc)
    parent={"execution_id":"PARENT-"+uuid.uuid4().hex,"job_id":"ROOTLINE-IRRIGATION-JOB-"+"A"*24,
        "job_sha256":"a"*64,"segment_identity":"ROOTLINE-JOB-SEGMENT-"+"B"*24,
        "zone_id":"B12345","device_id":"100204e9bc","channel":1,"state":"Active",
        "primary_stop_deadline":(at+timedelta(minutes=30)).isoformat()}
    seed(db,"claim_before_on",parent);seed(db,"mark_active",parent)
    common={"claimed_at":at.isoformat(),"primary_stop_deadline":(at+timedelta(seconds=120)).isoformat(),
        "maximum_duration_seconds":120,"device_id":"100204d497","state":"claimed","on_attempts":0,"off_attempts":0}
    mixer={**common,"execution_id":"MIX-"+uuid.uuid4().hex,"consumption_key":uuid.uuid4().hex,
        "auxiliary_device_id":"FERTILIZER-MIXER-CH2","device_type":"fertilizer_mixer","channel":2}
    injector={**common,"execution_id":"INJECT-"+uuid.uuid4().hex,"consumption_key":uuid.uuid4().hex,
        "auxiliary_device_id":"FERTILIZER-INJECTION-CH1","device_type":"fertilizer_injection_valve","channel":1,
        "zone_execution_id":parent["execution_id"],"pulse_number":1,
        **{key:parent[key] for key in ("job_id","job_sha256","segment_identity","zone_id")}}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda body:store.rootline_irrigation_execution_store("claim_auxiliary_before_on",body),(mixer,injector)))
    assert all(result["created"] for result in results)
    all_active=store.rootline_irrigation_execution_store("load_active_auxiliaries",None)
    assert {row["execution_id"] for row in all_active}=={mixer["execution_id"],injector["execution_id"]}
    for body in (mixer,injector):
        selected=store.rootline_irrigation_execution_store("load_active_auxiliary",body["auxiliary_device_id"])
        assert selected["execution_id"]==body["execution_id"]
        duplicate={**body,"execution_id":uuid.uuid4().hex,"consumption_key":uuid.uuid4().hex}
        assert store.rootline_irrigation_execution_store("claim_auxiliary_before_on",duplicate)["created"] is False
    with pytest.raises(store.RootlineExecutionStoreUnavailable):
        store.rootline_irrigation_execution_store("load_active_auxiliary",None)
