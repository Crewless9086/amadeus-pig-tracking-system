from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
import pytest
import psycopg
from modules.telemetry import weather_service as subject
from modules.telemetry.rootline_daily_brief import build_rootline_daily_brief

URL=os.getenv("FORECAST_CONSUMER_POSTGRES_URL", "")
H=Path(os.getenv("FORECAST_CONSUMER_SOURCE_ROOT", str(Path(__file__).resolve().parents[1])))
F=Path(__file__).parents[1]

@pytest.fixture(scope="module")
def database():
    if not URL:
        pytest.skip("Explicit isolated forecast PostgreSQL URL required")
    info=psycopg.conninfo.conninfo_to_dict(URL)
    assert info.get("host") in {"127.0.0.1", "localhost"}
    assert info.get("dbname", "").startswith("forecast_consumer_")
    admin={**info,"dbname":"postgres"}
    with psycopg.connect(**admin,autocommit=True) as c:
        assert c.info.host in {"127.0.0.1", "localhost"}
        clients=c.execute("select datname,application_name,state from pg_stat_activity where backend_type='client backend' and pid<>pg_backend_pid()").fetchall()
        assert not clients, clients
        exists=c.execute("select 1 from pg_database where datname=%s",(info["dbname"],)).fetchone()
        if not exists: c.execute(psycopg.sql.SQL("create database {}").format(psycopg.sql.Identifier(info["dbname"])))
    with psycopg.connect(URL) as c:
        assert c.execute("select current_database()").fetchone()[0]==info["dbname"]
        for filename, table in (("202605210005_create_telemetry_power_tables.sql","telemetry_sources"),("202605220001_create_telemetry_weather_tables.sql","weather_forecast_snapshots")):
            source=(H/"supabase/migrations"/filename).read_text()
            start=source.index("create table if not exists public."+table+" (")
            end=source.index("\n);",start)+3
            c.execute(source[start:end])
    yield URL

@pytest.fixture
def clean_database(database):
    with psycopg.connect(database) as c:
        assert c.info.dbname.startswith("forecast_consumer_")
        c.execute("delete from public.weather_forecast_snapshots")
        c.execute("delete from public.telemetry_sources")
        for source_id,provider in subject.FORECAST_PROVIDERS.items():
            c.execute("insert into public.telemetry_sources(source_id,source_type,provider,display_name,stale_after_minutes) values(%s,'forecast',%s,%s,360)",(source_id,provider,provider))
    return database


def payload(provider="visual_crossing",age=5, count=3):
    run=datetime.now(timezone.utc)-timedelta(minutes=age)
    source_id=next(key for key,value in subject.FORECAST_PROVIDERS.items() if value==provider)
    today=datetime.now(subject.ZA_TZ).date()
    provenance={"provider":provider,"source_id":source_id,"forecast_run_at":run.isoformat(),"fetched_at":run.isoformat(),"freshness_basis":"retrieved","provider_model_updated_at":None,"local_observation_credit":False}
    return {"source_id":source_id,"provider":provider,"provenance":provenance,"forecast_run_at":run.isoformat(),"timezone":"Africa/Johannesburg","days":[{"forecast_date":(today+timedelta(days=i)).isoformat(),"offset_days":i,"rain_sum_mm":2,"rain_probability_max_pct":30,"wind_max_kmh":10,"gust_max_kmh":15,"temp_max_c":25,"temp_min_c":10,"provenance":provenance,"provider_daily_chance_of_rain_pct":10,"provider_source":"comb" if i==0 else "fcst","provider_hour_sources":["obs","fcst"] if i==0 else ["fcst"]} for i in range(count)]}


def seed(database, packet):
    with psycopg.connect(database) as c:
        for row in subject._normalize_forecast_payload(packet):
            c.execute("""insert into public.weather_forecast_snapshots(forecast_snapshot_id,source_id,forecast_run_at,timezone,forecast_date,offset_days,temp_max_c,temp_min_c,rain_sum_mm,rain_probability_max_pct,wind_max_kmh,gust_max_kmh,flags,raw_payload)
              values(%(forecast_snapshot_id)s,%(source_id)s,%(forecast_run_at)s,%(timezone)s,%(forecast_date)s,%(offset_days)s,%(temp_max_c)s,%(temp_min_c)s,%(rain_sum_mm)s,%(rain_probability_max_pct)s,%(wind_max_kmh)s,%(gust_max_kmh)s,%(flags)s::jsonb,%(raw_payload)s::jsonb)""",row)


def read(database):
    result,status=subject.get_weather_forecast(days=3,database_url=database)
    assert status==200,result
    return result


def test_real_postgres_backup_and_primary_return_never_mix_runs(clean_database):
    db=clean_database
    seed(db,payload(age=60))
    backup=payload("weatherapi",age=10);backup["days"][0]["rain_sum_mm"]=9
    seed(db,backup)
    actual=read(db)
    assert actual["source"]["provider"]=="weatherapi"
    assert actual["days"][0]["rain_sum_mm"]==9
    primary=payload(age=1,count=1);primary["days"][0]["rain_sum_mm"]=1
    seed(db,primary)
    actual=read(db)
    assert actual["source"]["provider"]=="visual_crossing"
    assert len(actual["days"])==1 and actual["days"][0]["rain_sum_mm"]==1
    assert actual["window"]["complete_requested_horizon"] is False


def test_real_postgres_rejects_future_invalid_inactive_and_expired_runs(clean_database):
    db=clean_database
    seed(db,payload("weatherapi",age=50))
    seed(db,payload(age=1))
    with psycopg.connect(db) as c:
        c.execute("update public.weather_forecast_snapshots set forecast_run_at=now()+interval '1 hour' where source_id='visual-crossing-forecast-main'")
    assert read(db)["source"]["provider"]=="weatherapi"
    with psycopg.connect(db) as c:
        c.execute("update public.weather_forecast_snapshots set forecast_run_at=now()-interval '1 minute',rain_sum_mm='NaN' where source_id='visual-crossing-forecast-main'")
    assert read(db)["source"]["provider"]=="weatherapi"
    with psycopg.connect(db) as c:
        c.execute("update public.weather_forecast_snapshots set rain_sum_mm=0 where source_id='visual-crossing-forecast-main'")
        c.execute("update public.telemetry_sources set active=false where source_id='visual-crossing-forecast-main'")
    assert read(db)["source"]["provider"]=="weatherapi"
    with psycopg.connect(db) as c:
        c.execute("update public.weather_forecast_snapshots set forecast_date=forecast_date-10 where source_id='weatherapi-forecast-main'")
    assert read(db)["success"] is False


def test_real_postgres_unknown_fields_and_provider_daily_chance_stay_distinct(clean_database):
    packet=payload("weatherapi",count=1)
    packet["days"][0].update(rain_sum_mm=None,wind_max_kmh=None,gust_max_kmh=None)
    seed(clean_database,packet)
    actual=read(clean_database)
    day=actual["days"][0]
    assert day["rain_sum_mm"] is None and day["availability"]["rain_amount"] is False
    assert day["rain_probability_max_pct"]==30 and day["provider_daily_chance_of_rain_pct"]==10
    assert actual["summary"]["status"]=="caution"
    assert any("unavailable" in note for note in actual["summary"]["operator_notes"])
    assert actual["source"]["provider_model_updated_at"] is None
    assert actual["source"]["attribution"]["name"]=="WeatherAPI.com"
    assert day["local_observation_credit"] is False


def test_real_postgres_stale_run_keeps_true_age_and_current_local_day(clean_database):
    packet=payload(age=400)
    seed(clean_database,packet)
    actual=read(clean_database)
    assert actual["source"]["is_stale"] is True
    assert actual["window"]["covers_today"] is True
    assert datetime.fromisoformat(actual["source"]["last_forecast_run_at"])==datetime.fromisoformat(packet["forecast_run_at"])


def test_real_postgres_same_run_date_window_does_not_relable_yesterday(clean_database):
    packet=payload(count=3)
    for day in packet["days"]:
        day["forecast_date"]=(datetime.fromisoformat(day["forecast_date"])-timedelta(days=1)).date().isoformat()
    seed(clean_database,packet)
    actual=read(clean_database)
    assert actual["days"][0]["forecast_date"]==datetime.now(subject.ZA_TZ).date().isoformat()
    assert actual["window"]["returned_days"]==2


@pytest.mark.parametrize("bad", [float('nan'),float('inf'),-1,True,"not-number"])
def test_ingest_invalid_rain_is_rejected(bad):
    packet=payload();packet["days"][0]["rain_sum_mm"]=bad
    with pytest.raises(ValueError): subject._normalize_forecast_payload(packet)


@pytest.mark.parametrize("mutation", ["future","naive","source","provider","timezone","duplicate","provenance"])
def test_ingest_rejects_untrustworthy_identity_time_and_dates(mutation):
    packet=payload()
    if mutation=="future":packet["forecast_run_at"]=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
    if mutation=="naive":packet["forecast_run_at"]="2026-11-19T10:00:00"
    if mutation=="source":packet["source_id"]="invented-provider"
    if mutation=="provider":packet["provider"]="weatherapi"
    if mutation=="timezone":packet["timezone"]="UTC"
    if mutation=="duplicate":packet["days"][1]["forecast_date"]=packet["days"][0]["forecast_date"]
    if mutation=="provenance":packet["days"][0]["provenance"]["source_id"]="weatherapi-forecast-main"
    with pytest.raises(ValueError):subject._normalize_forecast_payload(packet)


def test_legacy_partial_payload_remains_accepted_and_null_is_not_zero():
    packet=payload(count=1)
    packet.pop("provider")
    packet.pop("provenance")
    packet["days"][0].pop("provenance")
    packet["days"][0]["rain_sum_mm"]=None
    rows=subject._normalize_forecast_payload(packet)
    assert len(rows)==1 and rows[0]["rain_sum_mm"] is None


def test_alert_identity_uses_backup_provider_and_forecast_area():
    run=datetime.now(timezone.utc)-timedelta(minutes=1)
    day=datetime.now(subject.ZA_TZ).date()
    row=(run,day,0,25,10,11,80,10,15,"weatherapi-forecast-main","WeatherAPI.com",360,{"provenance":{"provider":"weatherapi"}})
    alerts=subject._forecast_alert_candidates([row])
    assert alerts and all(a["source_id"]=="weatherapi-forecast-main" and a["area"]=="forecast" for a in alerts)
    assert all(a["details"]["provider"]=="weatherapi" for a in alerts)
    assert all("Forecast by WeatherAPI.com" in a["message"] for a in alerts)


def test_daily_brief_preserves_attribution_and_no_local_observation_credit():
    source={"provider":"visual_crossing","source_id":"visual-crossing-forecast-main","attribution":subject.forecast_attribution("visual_crossing"),"freshness_basis":"retrieved","provider_model_updated_at":None}
    packet={"success":True,"source":source,"window":{"returned_days":3}}
    result=build_rootline_daily_brief({"forecast":packet},datetime.now(subject.ZA_TZ).date().isoformat())
    assert result["forecast"]["attribution"]==source["attribution"]
    assert result["forecast"]["local_observation_credit"] is False


def test_attribution_unknown_is_empty_and_returned_dict_is_not_shared():
    assert subject.forecast_attribution("unknown")=={}
    actual=subject.forecast_attribution("visual_crossing");actual["url"]="wrong"
    assert subject.forecast_attribution("visual_crossing")["url"].startswith("https://www.visualcrossing.com/")


def test_real_ingest_rejects_expired_claim_atomically_then_commits_current_claim(clean_database, monkeypatch):
    from modules.telemetry import forecast_provider_health as health
    from uuid import uuid4
    db=clean_database
    packet=payload()
    claim={"provider":"visual_crossing","attempt_id":str(uuid4()),"generation":1}
    packet["provider_health_claim"]=claim
    monkeypatch.setenv("TELEMETRY_INGEST_API_KEY","synthetic-test-ingest-key")
    with psycopg.connect(db) as c:
        now=c.execute("select clock_timestamp()").fetchone()[0].astimezone(timezone.utc)
        state,_,_,_=health.transition({}, {"action":"claim","provider":"visual_crossing","attempt_id":claim["attempt_id"]},now-timedelta(minutes=16))
        cycle={'attempt_id':str(uuid4()),'cycle_date':now.date().isoformat(),
            'operating_date':(now.date()+timedelta(days=1)).isoformat()}
        state['nightly_cycle']=cycle
        owner={**cycle,'status':'pending','claimed_at':(now-timedelta(minutes=20)).isoformat(),
            'attempts':[{'provider':'visual_crossing','attempt_id':state['attempt_id'],
                'generation':state['generation'],'status':'pending'}]}
        packet['provenance']['nightly_cycle']=cycle
        c.execute("update public.telemetry_sources set metadata=%s::jsonb where source_id=%s",(json.dumps({
            "preserve":"unrelated","forecast_provider_health":state,'forecast_nightly_cycle':owner}),packet["source_id"]))
    result,code=subject.ingest_weather_forecast(packet,provided_api_key="synthetic-test-ingest-key",database_url=db)
    assert code==400 and result["success"] is False
    with psycopg.connect(db) as c:
        assert c.execute("select count(*) from public.weather_forecast_snapshots").fetchone()[0]==0
        now=c.execute("select clock_timestamp()").fetchone()[0].astimezone(timezone.utc)
        new_attempt=str(uuid4())
        state,_,_,_=health.transition(state,{"action":"claim","provider":"visual_crossing","attempt_id":new_attempt},now)
        cycle={'attempt_id':str(uuid4()),'cycle_date':now.date().isoformat(),
            'operating_date':(now.date()+timedelta(days=1)).isoformat()}
        state['nightly_cycle']=cycle
        owner={**cycle,'status':'pending','claimed_at':(now-timedelta(minutes=20)).isoformat(),
            'attempts':[{'provider':'visual_crossing','attempt_id':state['attempt_id'],
                'generation':state['generation'],'status':'pending'}]}
        packet['provenance']['nightly_cycle']=cycle
        c.execute("update public.telemetry_sources set metadata=%s::jsonb where source_id=%s",(json.dumps({
            "preserve":"unrelated","forecast_provider_health":state,'forecast_nightly_cycle':owner}),packet["source_id"]))
    # Old generation is blocked even after a replacement claim exists.
    result,code=subject.ingest_weather_forecast(packet,provided_api_key="synthetic-test-ingest-key",database_url=db)
    assert code==400
    packet["provider_health_claim"]={"provider":"visual_crossing","attempt_id":new_attempt,"generation":2}
    result,code=subject.ingest_weather_forecast(packet,provided_api_key="synthetic-test-ingest-key",database_url=db)
    assert code==201 and result["success"] is True, result
    with psycopg.connect(db) as c:
        assert c.execute("select count(*) from public.weather_forecast_snapshots").fetchone()[0]==3
        assert c.execute("select metadata->>'preserve' from public.telemetry_sources where source_id=%s",(packet["source_id"],)).fetchone()[0]=="unrelated"


def test_real_ingest_requires_claim_for_new_provider(clean_database,monkeypatch):
    monkeypatch.setenv("TELEMETRY_INGEST_API_KEY","synthetic-test-ingest-key")
    result,code=subject.ingest_weather_forecast(payload(),provided_api_key="synthetic-test-ingest-key",database_url=clean_database)
    assert code==400 and result["success"] is False
    with psycopg.connect(clean_database) as c:
        assert c.execute("select count(*) from public.weather_forecast_snapshots").fetchone()[0]==0



def test_reader_provider_switch_committed_before_fetch_keeps_one_statement_snapshot(clean_database, monkeypatch):
    from modules.oom_sakkie import bounded_postgres_read
    db=clean_database
    seed(db,payload("weatherapi",age=10))
    later=payload("visual_crossing",age=1)
    fired=[]
    statements=[]
    class SwitchCursor(psycopg.Cursor):
        def execute(self, query, params=None, **kwargs):
            result=super().execute(query, params, **kwargs)
            if isinstance(query,str) and "selected_forecast_run" in query:
                statements.append(query)
                if not fired:
                    fired.append(True)
                    # A second connection commits a different provider after the
                    # statement selected its snapshot, before the reader fetches.
                    seed(db,later)
            return result
    with psycopg.connect(db) as c:
        assert c.execute("show transaction_isolation").fetchone()[0]=="read committed"
    monkeypatch.setattr(bounded_postgres_read,"connect_bounded_read",lambda **kwargs:
        psycopg.connect(db,cursor_factory=SwitchCursor,options="-c default_transaction_read_only=on"))
    first=read(db)
    assert first["success"] is True and first["source"]["provider"]=="weatherapi", first
    assert len(statements)==1
    assert all(day["provenance"]["provider"]=="weatherapi" for day in first["days"])
    second=read(db)
    assert len(statements)==2
    assert second["success"] is True and second["source"]["provider"]=="visual_crossing"
    assert all(day["provenance"]["provider"]=="visual_crossing" for day in second["days"])


@pytest.mark.parametrize('mutation',[
    {'start_at':'2026-11-22T08:00:00+02:00'}, {'start_at':'2026-11-21T08:00:00'},
    {'source':'obs'}, {'local_observation_credit':True}, {'rain_sum_mm':-1},
    {'rain_probability_pct':101}, {'wind_max_kmh':float('nan')}])
def test_hourly_planning_rejects_invalid_estimates(mutation):
    from datetime import date
    hour={'start_at':'2026-11-21T08:00:00+02:00','source':'fcst',
        'local_observation_credit':False,'rain_sum_mm':0,'rain_probability_pct':20,'wind_max_kmh':3}
    with pytest.raises(ValueError):
        subject._validated_planning_hours({'planning_hours':[{**hour,**mutation}]},date(2026,11,21))


def test_nightly_dated_reader_target_boundary_and_true_stale_age(monkeypatch):
    from datetime import date
    from modules.oom_sakkie import bounded_postgres_read
    calls=[]
    run=datetime.fromisoformat('2026-11-20T23:30:00+02:00')
    target=date(2026,11,21)
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def cursor(self):return self
        def execute(self,query,params):calls.append((query,params))
        def fetchall(self):return [('visual-crossing-forecast-main','Forecast','visual_crossing',360,
            run,'Africa/Johannesburg',target,1,25,10,0,20,3,5,{},
            {'planning_hours':[{'start_at':'2026-11-21T08:00:00+02:00','source':'fcst',
                'local_observation_credit':False,'rain_sum_mm':0,'rain_probability_pct':20,'wind_max_kmh':3}]} )]
    monkeypatch.setattr(bounded_postgres_read,'connect_bounded_read',lambda **_:Connection())
    early,status=subject.get_weather_forecast(1,'offline',operating_date=target.isoformat(),
        as_of=run-timedelta(minutes=1),nightly=True)
    assert early['success'] is False and calls==[]
    initial,status=subject.get_weather_forecast(1,'offline',operating_date=target.isoformat(),as_of=run,nightly=True)
    assert status==200 and initial['days'][0]['forecast_date']==target.isoformat()
    query,params=calls[-1]
    assert params[0]==target and params[3]==run
    assert "forecast_nightly_cycle" in query and "completed_at" in query
    assert "f.ingested_at <= (select at from reporting_epoch)" in query
    assert "f.forecast_date >= (select day from requested_forecast)" in query
    midday,status=subject.get_weather_forecast(1,'offline',operating_date=target.isoformat(),
        as_of=run+timedelta(hours=12,minutes=30),nightly=True)
    assert midday['source']['is_stale'] is True and midday['source']['data_age_minutes']==750
    assert midday['source']['snapshot_role']=='pinned_nightly_programme'
    assert midday['days'][0]['planning_hours'][0]['local_observation_credit'] is False


def test_real_postgres_nightly_target_pin_midday_and_completed_cutoff(clean_database):
    db=clean_database
    packet=payload(age=1)
    seed(db,packet)
    today=datetime.now(subject.ZA_TZ).date()
    target=today+timedelta(days=1)
    at=datetime.combine(today,datetime.min.time(),tzinfo=subject.ZA_TZ)+timedelta(hours=23,minutes=30)
    cycle={'status':'ingested','operating_date':target.isoformat(),
        'completed_at':(at-timedelta(seconds=1)).isoformat(),
        'result':{'source_id':packet['source_id'],'forecast_run_at':packet['forecast_run_at']}}
    with psycopg.connect(db) as c:
        c.execute("update public.telemetry_sources set metadata=jsonb_set(metadata,'{forecast_nightly_cycle}',%s::jsonb,true) where source_id=%s",
            (json.dumps(cycle),'visual-crossing-forecast-main'))
    actual,status=subject.get_weather_forecast(1,db,operating_date=target.isoformat(),as_of=at,nightly=True)
    assert status==200 and actual['success'] is True,actual
    assert len(actual['days'])==1 and actual['days'][0]['forecast_date']==target.isoformat()
    assert actual['source']['last_forecast_run_at']==datetime.fromisoformat(packet['forecast_run_at']).isoformat()
    midday=at+timedelta(hours=12,minutes=30)
    later,status=subject.get_weather_forecast(1,db,operating_date=target.isoformat(),as_of=midday,nightly=True)
    assert later['success'] is True and later['source']['is_stale'] is True,later
    assert later['source']['snapshot_role']=='pinned_nightly_programme'
    with psycopg.connect(db) as c:
        cycle['completed_at']=(at+timedelta(seconds=1)).isoformat()
        c.execute("update public.telemetry_sources set metadata=jsonb_set(metadata,'{forecast_nightly_cycle}',%s::jsonb,true) where source_id=%s",
            (json.dumps(cycle),'visual-crossing-forecast-main'))
    future,status=subject.get_weather_forecast(1,db,operating_date=target.isoformat(),as_of=at,nightly=True)
    assert future['success'] is False


def test_consumer_fixture_exposes_ingest_provenance_before_database_setup():
    packet=payload()
    cycle={'attempt_id':'offline-cycle','cycle_date':'2026-11-20','operating_date':'2026-11-21'}
    packet['provenance']['nightly_cycle']=cycle
    assert packet['provenance']['provider']==packet['provider']
    assert packet['provenance']['source_id']==packet['source_id']
    assert packet['provenance']['forecast_run_at']==packet['forecast_run_at']
    assert all(day['provenance']['nightly_cycle']==cycle for day in packet['days'])
    # The production normalizer still validates every period; this fixture
    # correction does not bypass the separate persisted claim/receipt gate.
    normalized=subject._normalize_forecast_payload(packet)
    assert len(normalized)==3
    assert all(json.loads(row['raw_payload'])['provenance']['nightly_cycle']==cycle for row in normalized)
