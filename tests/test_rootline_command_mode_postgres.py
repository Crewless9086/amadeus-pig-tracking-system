"""Real canonical SQL against one explicitly selected synthetic loopback database."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import os
from pathlib import Path
from urllib.parse import urlparse
import uuid

import pytest
import psycopg

from tests.test_rootline_command_mode import start, receipt, route, ENV
from modules.telemetry import rootline_command_acceptance as ca
from modules.telemetry.rootline_timed_control import timed_control_scope

NOW=datetime.now(timezone.utc)-timedelta(hours=3)
store_module=importlib.import_module("modules.telemetry.rootline_irrigation_execution_store")
URL=os.getenv("ROOTLINE_HA_COMMAND_TEST_URL","")
pytestmark=pytest.mark.skipif(not URL,reason="explicit command-mode synthetic database required")


def connect():
    parsed=urlparse(URL)
    assert parsed.hostname=="127.0.0.1" and parsed.port==55485 and parsed.path=="/rootline_ha_command_mode_test"
    assert parsed.username=="postgres"
    return psycopg.connect(URL,connect_timeout=5)


@pytest.fixture(scope="module",autouse=True)
def schema():
    if not URL:
        yield;return
    root=Path(__file__).resolve().parents[1]/"supabase/migrations"
    with connect() as c:
        c.execute("create schema if not exists app_private")
        c.execute("create table if not exists app_private.migration_log(migration_id text primary key, description text not null)")
        for name in ("202607070001_create_sam_live_stock_conversation_review_events.sql",
                     "202605210005_create_telemetry_power_tables.sql","202605230001_create_irrigation_tables.sql",
                     "202608050001_harden_irrigation_events_history.sql",
                     "20261101150806_extend_rootline_a_irrigation_history.sql",
                     "20261115090517_extend_rootline_e_irrigation_history.sql",
                     "202608150009_create_rootline_water_credit_lifecycle.sql"):
            c.execute((root/name).read_text(encoding="utf-8"))
        for zone in ("A12345","B12345","C12345","E12345"):
            c.execute("insert into public.irrigation_zones(zone_id,zone_name) values(%s,%s) on conflict do nothing",(zone,zone))
    yield


@pytest.fixture
def db(monkeypatch):
    with connect() as c:
        c.execute("truncate public.sam_live_stock_conversation_review_events, public.irrigation_events")
    monkeypatch.setenv("DATABASE_URL",URL)
    return store_module.rootline_irrigation_execution_store


def seed(rows):
    with connect() as c, c.cursor() as cursor:
        for row in rows:
            store_module._insert_managed_event(cursor,row["action"],{k:v for k,v in row.items() if k!="action"})


def test_real_terminal_and_typed_history_keep_command_and_water_separate(db):
    _,artifact,memory,transport,clock=start(at=NOW)
    original=deepcopy(memory.active)
    seed(memory.rows)
    assert db("load_active",None)["execution_id"]==original["execution_id"]
    off=receipt(original,"OFF",at=NOW+timedelta(seconds=7200))
    assert db("mark_stopping",{**original,"state":"stopping","reason":"primary_deadline_reached"})["success"]
    assert db("claim_off_attempt",{"execution_id":original["execution_id"],"attempt":1})["created"]
    assert db("record_off_outcome",{"execution_id":original["execution_id"],"attempt":1,"outcome":off})["success"]
    terminal=ca.terminal(original,off,now=NOW+timedelta(seconds=7200),reason="primary_deadline_reached")
    terminal.update(command_program_completed=True,command_job_completed=True,job_completed=False)
    result=db("record_completed",terminal)
    assert result["success"] and result["history_event_created"],result
    assert db("load_active",None) is None
    assert db("record_completed",terminal)["created"] is False
    from modules.telemetry.rootline_irrigation_history import read_canonical_irrigation_history
    history=read_canonical_irrigation_history(connect=connect,now=datetime.now(timezone.utc))
    assert history["status"]=="Available",history
    events=history["zones"]["B12345"]["events"]
    completed=[row for row in events if row["command_job_completed"]]
    assert len(completed)==1,events
    assert completed[0]["qualifies_as_completed_watering"] is False
    assert history["zones"]["B12345"]["verified_completed_days"]==[]
    assert not history["zones"]["B12345"].get("incomplete_parent_job")
    assert completed[0]["operating_date"]==original["operating_date"]


def test_terminal_rejects_missing_or_other_claim_receipt(db):
    _,_,memory,_,_=start(at=NOW);original=memory.active;seed(memory.rows)
    off=receipt(original,"OFF",at=NOW+timedelta(seconds=7200))
    terminal=ca.terminal(original,off,now=NOW+timedelta(seconds=7200))
    with pytest.raises(ValueError,match="command_terminal_receipt_unproven"):
        db("record_completed",terminal)
    assert db("load_active",None) is not None


def test_auxiliary_accepted_off_releases_existing_sql_latch(db):
    original={"execution_id":"HA-MIX-"+uuid.uuid4().hex,"acceptance_mode":ca.MODE,
        "device_id":"100204d497","channel":2,"auxiliary_device_id":"FERTILIZER-MIXER-CH2",
        "device_type":"fertilizer_mixer","claimed_at":NOW.isoformat(),
        "primary_stop_deadline":(NOW+timedelta(seconds=600)).isoformat(),
        "maximum_duration_seconds":600,"state":"claimed","on_attempts":0,"off_attempts":0}
    on=receipt(original,"ON",at=NOW)
    active={**original,"state":"Active","on_attempts":1,"command_on_receipt":on}
    seed([{**original,"action":"claim_auxiliary_before_on"},
        {**original,"action":"dispatch_auxiliary_on_edge"},
        {**original,"action":"record_auxiliary_on_outcome","on_outcome":on},
        {**active,"action":"mark_auxiliary_active"}])
    off=receipt(active,"OFF",at=NOW+timedelta(seconds=600))
    outcome=db("dispatch_auxiliary_off_edge",{"execution_id":active["execution_id"],"attempt":1,"dispatch":lambda:off})
    assert outcome["accepted_unambiguous"],outcome
    terminal=ca.terminal(active,off,now=NOW+timedelta(seconds=600),reason="primary_deadline_reached")
    terminal.update(command_program_completed=True,command_accounted_mixing_seconds=600)
    result=db("record_auxiliary_completed",terminal)
    assert result["success"],result
    assert db("load_active_auxiliary","FERTILIZER-MIXER-CH2") is None
    replay=db("dispatch_auxiliary_off_edge",{"execution_id":active["execution_id"],"attempt":2,"dispatch":lambda:pytest.fail("retired sender")})
    assert replay["provider_command_attempted"] is False


def test_adopted_borehole_restart_off_uses_no_invented_on_credit(db):
    from modules.telemetry.rootline_ifttt_transport import output_evidence_from_snapshot
    from modules.telemetry.rootline_borehole_commissioning import advance_borehole_execution
    adopted={"execution_id":"HA-ADOPT-"+uuid.uuid4().hex,"acceptance_mode":ca.MODE,
        "contract_version":"rootline_borehole_runtime_eligibility.v5","stop_mode":"conditions",
        "device_id":"1002851416","channel":1,"device_key":"ewelink:ewelink_owner_account:1002851416:1",
        "auxiliary_device_id":"BOREHOLE-1-MINI-R4-CH1","state":"Active","on_attempts":0,
        "claimed_at":NOW.isoformat(),"original_start_at":None,"provider_start_evidence":None,
        "execution_origin":"ha_reported_external_on","requested_seconds":None,"native_fail_stop_seconds":0,
        "command_adoption_evidence":output_evidence_from_snapshot(route("1002851416",now=NOW,reported="ON"),device_id="1002851416",channel=1)}
    assert ca.active_command(adopted,now=NOW+timedelta(hours=2))
    seed([{**adopted,"action":"mark_borehole_active"}])
    calls=[]
    class Transport:
        def set_state(self,**kwargs):
            calls.append(kwargs)
            assert kwargs["state"]=="OFF"
            return receipt(adopted,"OFF",at=datetime.now(timezone.utc),attempt=int(kwargs["idempotency_key"].rsplit(":",1)[1]))
        def read_output_state(self,**kwargs): pytest.fail("independent feedback is not required")
    active=advance_borehole_execution(eligibility=None,store=db,transport=Transport(),now=datetime.now(timezone.utc))
    assert active["status"]=="borehole_command_duty_active",active
    assert calls==[]
    done=advance_borehole_execution(eligibility=None,store=db,transport=Transport(),now=datetime.now(timezone.utc),stop_for_energy=True)
    assert done["status"]=="borehole_off_command_accepted",done
    assert len(calls)==1 and done["execution"]["commanded_runtime_seconds"]==0
    assert done["execution"].get("command_on_receipt") is None
    assert db("load_active_borehole",None) is None
    replay=db("dispatch_borehole_off_edge",{"execution_id":adopted["execution_id"],"attempt":2,"dispatch":lambda:pytest.fail("retired borehole sender")})
    assert replay["provider_command_attempted"] is False


def test_real_fresh_claim_and_duplicate_dispatch_are_consumed_once(db,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    for key,value in ENV.items():monkeypatch.setenv(key,value)
    result,artifact,memory,_,_=start(at=datetime.now(timezone.utc))
    claim=next(row for row in memory.rows if row["action"]=="claim_before_on")
    claim={k:v for k,v in claim.items() if k!="action"}
    assert db("record_eligibility",artifact)["success"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims=list(pool.map(lambda _:db("claim_before_on",claim),range(2)))
    assert sum(row.get("created") is True for row in claims)==1,claims
    sends=[]
    def dispatch():
        sends.append("ON")
        return receipt(claim,"ON",at=datetime.now(timezone.utc))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:db("dispatch_irrigation_on_edge",{**claim,"dispatch":dispatch}),range(2)))
    assert sends==["ON"],results
    assert sum(row.get("accepted_unambiguous") is True for row in results)==1,results
    assert db("dispatch_irrigation_on_edge",{**claim,"dispatch":lambda:pytest.fail("replayed ON")})["accepted_unambiguous"] is False


def test_real_stopping_barrier_prevents_stale_irrigation_sender(db,monkeypatch):
    for key,value in ENV.items():monkeypatch.setenv(key,value)
    _,artifact,memory,_,_=start(at=datetime.now(timezone.utc))
    claim={k:v for k,v in next(row for row in memory.rows if row["action"]=="claim_before_on").items() if k!="action"}
    assert db("record_eligibility",artifact)["success"]
    assert db("claim_before_on",claim)["created"]
    assert db("mark_stopping",{**claim,"state":"stopping","reason":"owner_stop"})["success"]
    result=db("dispatch_irrigation_on_edge",{**claim,"dispatch":lambda:pytest.fail("stale ON after stop")})
    assert result["accepted_unambiguous"] is False,result


def test_real_locked_ha_transport_sends_exact_entity_once(db,monkeypatch):
    from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
    from modules.telemetry.rootline_ewelink_request_budget import execution_duty
    from modules.telemetry.rootline_device_registry import get_device_contract
    from modules.telemetry import rootline_home_assistant as ha
    from tests.test_rootline_home_assistant import debug_fixture
    source={**ENV,"DATABASE_URL":URL,"ROOTLINE_HOME_ASSISTANT_URL":"https://offline.example.test",
        "ROOTLINE_HOME_ASSISTANT_TOKEN":"offline-placeholder",get_device_contract("B12345")["authority_flag"]:"true"}
    for key,value in source.items():monkeypatch.setenv(key,value)
    _,artifact,memory,_,_=start(at=datetime.now(timezone.utc))
    claim={k:v for k,v in next(row for row in memory.rows if row["action"]=="claim_before_on").items() if k!="action"}
    transport=RootlineIFTTTTransport(token_store=None,environ=source)
    claim["provider_capacity_permit"]=transport.prepare_execution_capacity(claim)
    assert db("record_eligibility",artifact)["success"]
    assert db("claim_before_on",claim)["created"]
    calls=[];devices,entities,states,debug=debug_fixture()
    class Client:
        def __init__(self,_):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def request(self,kind,**fields):
            if kind=="config/device_registry/list":return devices
            if kind=="config/entity_registry/list":return entities
            if kind=="mqtt/device/debug_info":return debug
            assert kind=="call_service"
            calls.append(fields);return {}
    original=ha.send_state
    monkeypatch.setattr(ha,"send_state",lambda **kwargs:original(**kwargs,client_factory=Client))
    def dispatch():
        with execution_duty(claim):
            return transport.set_state(device_id=claim["device_id"],channel=claim["channel"],state="ON",idempotency_key=claim["execution_id"]+":ON")
    # An in-memory duty cannot authorize a provider send outside the locked edge.
    assert dispatch()["provider_command_attempted"] is False
    assert calls==[]
    result=db("dispatch_irrigation_on_edge",{**claim,"dispatch":dispatch})
    assert ca.accepted(result,claim,"ON"),result
    assert calls==[{"domain":"switch","service":"turn_on","target":{"entity_id":"switch.renamed_1"}}]
    assert db("dispatch_irrigation_on_edge",{**claim,"dispatch":dispatch})["accepted_unambiguous"] is False
    assert len(calls)==1
