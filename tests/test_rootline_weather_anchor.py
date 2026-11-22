"""Shared dry-window continuity and boundary behaviour."""
from datetime import datetime, timedelta, timezone
import pytest
from modules.telemetry.weather_service import build_weather_dry_release_evidence as build
NOW=datetime(2026,11,22,2,12,27,tzinfo=timezone.utc)

@pytest.mark.parametrize("minutes",[30,60])
@pytest.mark.parametrize("change",["valid","rain","stale","unhealthy","future","short","gap","duplicate","nan","negative","bool","missing"])
def test_dry_interval_requires_continuous_fresh_healthy_zero_rain(minutes,change):
    end=NOW-timedelta(minutes=2)
    rows=[(end-timedelta(minutes=m),0) for m in range(minutes,-1,-5)]
    at=NOW;healthy=True
    if change=="rain":rows[2]=(rows[2][0],0.01)
    elif change=="stale":at=end+timedelta(minutes=30,seconds=1)
    elif change=="unhealthy":healthy=False
    elif change=="future":at=end-timedelta(seconds=1)
    elif change=="short":rows[0]=(rows[0][0]+timedelta(microseconds=1),0)
    elif change=="gap":rows=rows[:1]+rows[3:]
    elif change=="duplicate":rows.insert(1,rows[0])
    elif change in {"nan","negative","bool","missing"}:rows[2]=(rows[2][0],{"nan":float("nan"),"negative":-1,"bool":False,"missing":None}[change])
    result=build(rows,evaluated_at=at,stale_after_minutes=30,provider_healthy=healthy,dry_interval_minutes=minutes)
    assert result["continuous_zero_rain_confirmed"] is (change=="valid")

@pytest.mark.parametrize("extra,valid",[(0,True),(0.000001,False)])
def test_existing_ten_minute_gap_boundary(extra,valid):
    rows=[(NOW-timedelta(seconds=s),0) for s in (1800,1200,600-extra,0)]
    assert build(rows,evaluated_at=NOW,stale_after_minutes=30)["continuous_zero_rain_confirmed"] is valid
