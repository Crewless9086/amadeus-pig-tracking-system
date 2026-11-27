"""Real SQL OFF ownership for parent deadline rechecks; dedicated local test DB."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
from functools import partial
import psycopg
from psycopg.types.json import Jsonb
import pytest
from modules.telemetry import rootline_command_acceptance as ca
from modules.telemetry import rootline_irrigation_execution_store as storemod
from modules.telemetry.rootline_execution_runtime import supervise_rootline_active_execution
from modules.telemetry.rootline_timed_control import timed_control_scope
from tests.test_rootline_owner_controls_postgres import database_url, sql
from tests.test_rootline_command_mode import start,receipt,route,ENV as COMMAND_ENV
from modules.telemetry.rootline_ifttt_transport import output_evidence_from_snapshot
from tests.test_rootline_active_supervision import reports,gateway,Transport,ScheduleStore,payload,ENV
from tests.test_rootline_active_weather_stop import dry_weather_reader

@pytest.fixture
def parent_sql(sql):
    with psycopg.connect(sql) as c:
        for name in ("202605210005_create_telemetry_power_tables.sql","202605230001_create_irrigation_tables.sql",
                "202608050001_harden_irrigation_events_history.sql","20261101150806_extend_rootline_a_irrigation_history.sql",
                "20261115090517_extend_rootline_e_irrigation_history.sql","202608150009_create_rootline_water_credit_lifecycle.sql"):
            c.execute((Path("supabase/migrations")/name).read_text("utf-8"))
        for zone in ("A12345","B12345","C12345","E12345"):
            c.execute("insert into public.irrigation_zones(zone_id,zone_name) values(%s,%s) on conflict do nothing",(zone,zone))
        c.execute("truncate public.irrigation_events")
    at=datetime.now(timezone.utc)-timedelta(hours=3)
    _,_,memory,_,clock=start(at=at)
    active=deepcopy(memory.active)
    with psycopg.connect(sql) as c,c.cursor() as cur:
        for row in memory.rows:
            storemod._insert_managed_event(cur,row["action"],{k:v for k,v in row.items() if k!="action"})
            c.commit()  # Production transitions commit separately; transaction-now ties reorder hashes.
    loaded=storemod.rootline_irrigation_execution_store("load_active",None)
    assert loaded["state"]=="Active" and loaded["execution_id"]==active["execution_id"]
    return sql,active

@pytest.mark.parametrize("mode",["normal","concurrent","failed"])
def test_real_gateway_parent_off_once_and_next_tick_recovery(parent_sql,reports,mode):
    url,active=parent_sql
    deadline=ca.command_stop_deadline(active);wall=[deadline-timedelta(seconds=15)];sent=[];trace=[]
    db=storemod.rootline_irrigation_execution_store
    class OffTransport:
        def set_state(self,**kwargs):
            assert kwargs["state"]=="OFF"
            sent.append(kwargs)
            attempt=int(kwargs["idempotency_key"].rsplit(":",1)[1])
            if mode=="failed" and len(sent)<=3:
                raise RuntimeError("synthetic transport interrupted after OFF attempt")
            return receipt(active,"OFF",at=wall[0],attempt=attempt)
        def read_output_state(self,**kwargs):
            # Routine command-route observation is allowed; it is not physical feedback.
            assert kwargs == {"device_id":active["device_id"],"channel":active["channel"]}
            return output_evidence_from_snapshot(route(active["device_id"],now=wall[0]),
                device_id=active["device_id"],channel=active["channel"])
    supervisor=partial(supervise_rootline_active_execution,store=db,transport=OffTransport(),
        token_store=object(),clock=lambda:wall[0],active_weather_reader=dry_weather_reader)
    def wait(seconds):
        trace.append({"wait":seconds})
        wall[0]+=timedelta(seconds=seconds)
        if mode=="concurrent":
            concurrent=supervisor(notify=lambda *a:{"success":True,"provider_delivery_confirmed":True,"provider_message_id":"synthetic"},
                environ=COMMAND_ENV,now=wall[0],owner_user_id="42",chat_id="42")
            trace.append({"concurrent_result":concurrent})
    def invoke():
        return gateway(None,Transport(),schedules=ScheduleStore(),
            active_supervision_cycle=supervisor,supervision_clock=lambda:wall[0],
            parent_deadline_store=db,parent_deadline_wait=wait,
            source_env={**ENV,**COMMAND_ENV},scheduler_now=wall[0],
            request_payload=payload(due_at=wall[0].isoformat(),trigger_timestamp=wall[0].isoformat(),
                evidence_cutoff=wall[0].isoformat()),
            managed_device_cycle=lambda **kw:{"success":True,"status":"no_eligible_managed_device_task","hardware_commands":0})
    first=invoke()[0]
    expected_attempts=3 if mode=="failed" else 1
    assert len(sent)==expected_attempts, {"result":first,"trace":trace,"wall":str(wall[0]),"deadline":str(deadline)}
    assert first["hardware_commands"]==(0 if mode=="concurrent" else expected_attempts)
    assert all(row["state"]=="OFF" for row in sent)
    assert wall[0]>=deadline and trace[0]["wait"]==15.0
    if mode=="failed":
        assert db("load_active",None) is not None
        wall[0]+=timedelta(minutes=1)
        second=invoke()[0]
        assert len(sent)==3 and second["hardware_commands"]==0
        assert db("load_active",None) is not None
        # Re-seed the disposable fixture with the same complete audit rows at
        # an older creation clock, as a later worker would read them. The real
        # append-only trigger stays enabled; no UPDATE/DELETE bypass is used.
        with psycopg.connect(url) as connection:
            rows=connection.execute("""select to_jsonb(e) from
                public.sam_live_stock_conversation_review_events e
                order by created_at,review_event_id""").fetchall()
            connection.execute("truncate public.sam_live_stock_conversation_review_events")
            for (row,) in rows:
                row["created_at"]=(datetime.fromisoformat(row["created_at"])-timedelta(seconds=301)).isoformat()
                connection.execute("""insert into public.sam_live_stock_conversation_review_events
                    select * from jsonb_populate_record(
                        null::public.sam_live_stock_conversation_review_events,%s::jsonb)""",(Jsonb(row),))
        wall[0]+=timedelta(minutes=5)
        third=invoke()[0]
        assert len(sent)==4 and third["hardware_commands"]==1
        assert [row["idempotency_key"].rsplit(":",1)[1] for row in sent]==["1","2","3","4"]
    assert db("load_active",None) is None
    with timed_control_scope(COMMAND_ENV):
        replay=supervisor(notify=lambda *a:pytest.fail("terminal replay notification"),environ=COMMAND_ENV,
            now=wall[0],owner_user_id="42",chat_id="42")
    assert replay["hardware_commands"]==0 and len(sent)==(4 if mode=="failed" else 1)
