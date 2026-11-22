"""Exact bounded SQL anchor against the authorized synthetic database only."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import uuid
import pytest
from tests.test_rootline_command_mode_postgres import URL, connect, schema
from modules.telemetry import weather_service as weather
pytestmark=pytest.mark.skipif(not URL,reason="explicit command-mode synthetic database required")
NOW=datetime(2026,11,22,2,12,27,tzinfo=timezone.utc)

@pytest.fixture
def weather_db(monkeypatch):
    source="anchor-"+uuid.uuid4().hex
    monkeypatch.setattr(weather,"DEFAULT_WEATHER_SOURCE_ID",source)
    with connect() as c:
        root=Path(__file__).resolve().parents[1]/"supabase/migrations"
        c.execute((root/"202605220001_create_telemetry_weather_tables.sql").read_text())
        c.execute("insert into public.telemetry_sources(source_id,source_type,display_name,provider,stale_after_minutes) values(%s,'weather','synthetic','synthetic',30)",(source,))
        c.execute("insert into public.weather_latest_state(source_id,reading_at,flags,summary_status,summary_headline,summary_notes) values(%s,%s,'{}','ok','dry','[]')",(source,NOW))
    return source

def insert(source,rows):
    with connect() as c:
        for at,rate in rows:
            c.execute("insert into public.weather_readings(reading_id,source_id,reading_at,rain_rate_mm_h,rain_today_mm) values(%s,%s,%s,%s,0)",(uuid.uuid4().hex,source,at,rate))

@pytest.mark.parametrize("minutes",[30,60])
def test_sql_nearest_anchor_ignores_older_wet_row_and_future_reading(weather_db,minutes):
    source=weather_db;end=NOW-timedelta(seconds=128)
    # Real observed 30-minute jitter: span35m12, formerly truncated to29m36.
    offsets=[2112,1776,1500,1200,900,600,300,0] if minutes==30 else list(range(3900,-1,-300))
    rows=[(end-timedelta(seconds=s),0) for s in offsets]
    insert(source,[(rows[0][0]-timedelta(minutes=4),1),*rows,(NOW+timedelta(seconds=1),1)])
    snapshot,status=weather.get_weather_control_snapshot(URL,now=NOW,dry_interval_minutes=minutes)
    release=snapshot["rain_release"]
    assert status==200 and release["continuous_zero_rain_confirmed"] is True,snapshot
    expected=max(at for at,rate in rows if at<=end-timedelta(minutes=minutes))
    assert datetime.fromisoformat(release["interval_start_at"])==expected
    assert datetime.fromisoformat(release["interval_end_at"])==end
    if minutes==30:
        direct,_=weather.get_weather_dry_release_evidence(URL,now=NOW)
        assert direct==release

@pytest.mark.parametrize("minutes",[30,60])
def test_sql_does_not_search_past_bounded_anchor(weather_db,minutes):
    end=NOW-timedelta(minutes=1)
    rows=[(end-timedelta(minutes=m),0) for m in range(minutes-5,-1,-5)]
    insert(weather_db,[(end-timedelta(minutes=minutes+10,seconds=1),0),*rows])
    packet,_=weather.get_weather_control_snapshot(URL,now=NOW,dry_interval_minutes=minutes)
    assert packet["rain_release"]["continuous_zero_rain_confirmed"] is False
