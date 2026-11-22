"""Exact loopback synthetic database: real activation, OFF races and restart."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
import time
import uuid
import pytest
from modules.telemetry import rootline_command_acceptance as ca
from modules.telemetry import rootline_irrigation_execution_store as store
from tests.test_rootline_command_mode import start, receipt
from tests.test_rootline_command_mode_postgres import schema, connect, URL

pytestmark=pytest.mark.skipif(not URL,reason="explicit dedicated synthetic database required")


@pytest.fixture
def packet(monkeypatch):
    with connect() as connection:
        assert connection.execute("select host(inet_server_addr()),inet_server_port(),current_database()").fetchone()==(
            "127.0.0.1",55485,"rootline_ha_command_mode_test")
        connection.execute("truncate public.sam_live_stock_conversation_review_events,public.irrigation_events")
    monkeypatch.setenv("DATABASE_URL",URL)
    now=datetime.now(timezone.utc)
    _,_,memory,_,_=start(at=now-timedelta(seconds=600))
    parent=memory.active
    claim={"execution_id":"OFFLINE-TARGET-"+uuid.uuid4().hex,
        "auxiliary_device_id":"FERTILIZER-INJECTION-CH1","device_type":"fertilizer_injection_valve",
        "device_id":"100204d497","channel":1,"acceptance_mode":ca.MODE,"stop_mode":"scheduled",
        "state":"claimed","on_attempts":0,"off_attempts":0,"maximum_duration_seconds":120,
        "claimed_at":(now-timedelta(seconds=10)).isoformat(),
        "primary_stop_deadline":(now+timedelta(seconds=110)).isoformat(),
        "injector_timing_contract":ca.INJECTOR_TARGET_V1,"consumption_key":"OFFLINE-CONSUME-"+uuid.uuid4().hex,
        "zone_execution_id":parent["execution_id"],
        **{k:parent[k] for k in ("zone_id","job_id","job_sha256","segment_identity")}}
    on=receipt(claim,"ON",at=now-timedelta(seconds=5))
    on["accepted_at"]=(now-timedelta(seconds=2)).isoformat()
    on["receipt_sha256"]=ca.digest({k:v for k,v in on.items() if k!="receipt_sha256"})
    rows=memory.rows+[{**claim,"action":"claim_auxiliary_before_on"},
        {**claim,"action":"claim_auxiliary_dispatch"},
        {**claim,"action":"record_auxiliary_on_outcome","on_outcome":on}]
    for row in rows:
        with connect() as connection,connection.cursor() as cursor:
            store._insert_managed_event(cursor,row["action"],{k:v for k,v in row.items() if k!="action"})
    return {**claim,"state":"Active","on_attempts":1,"command_on_receipt":on},parent


def activate(body): return store._guarded_managed_transition("mark_auxiliary_active",body)


def rows(identity):
    with connect() as connection,connection.cursor() as cursor:
        return store._managed_edge_rows(cursor,identity)


def test_sql_activation_restart_terminal_and_no_second_off(packet):
    body,parent=packet
    result=activate(body); assert result["success"],result
    active=result["execution"]
    assert ca.injector_target_matches_rows(active,rows(body["execution_id"]))
    loaded=store._load("load_active_auxiliary","FERTILIZER-INJECTION-CH1")
    assert loaded["injector_target"]==active["injector_target"]
    replay=activate(body)
    assert replay["success"] and not replay["created"] and replay["execution"]==active
    off=receipt(active,"OFF",at=datetime.now(timezone.utc))
    outcome=store.rootline_irrigation_execution_store("dispatch_auxiliary_off_edge",{
        "execution_id":active["execution_id"],"attempt":1,"dispatch":lambda:off})
    assert outcome["accepted_unambiguous"]
    terminal=ca.terminal(active,off,reason="offline_early_stop")
    terminal["command_program_completed"]=False
    saved=store.rootline_irrigation_execution_store("record_auxiliary_completed",terminal)
    assert saved["success"],saved
    assert store._load("load_active_auxiliary","FERTILIZER-INJECTION-CH1") is None
    again=store.rootline_irrigation_execution_store("dispatch_auxiliary_off_edge",{
        "execution_id":active["execution_id"],"attempt":2,"dispatch":lambda:pytest.fail("no resend")})
    assert again["provider_command_attempted"] is False


@pytest.mark.parametrize("winner",["off","parent_stop","activation"])
def test_waiting_activation_sees_winner_after_existing_locks(packet,winner):
    body,parent=packet
    locker=connect()
    try:
        locker.execute("select pg_advisory_xact_lock(1874320911)")
        locker.execute("select pg_advisory_xact_lock(1874320912)")
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(activate,deepcopy(body))
            until=time.monotonic()+3
            waiting=False
            while time.monotonic()<until:
                with connect() as observer:
                    waiting=bool(observer.execute("select exists(select 1 from pg_stat_activity where datname=current_database() and wait_event='advisory')").fetchone()[0])
                if waiting: break
                time.sleep(.01)
            assert waiting,"contender did not reach advisory lock"
            with locker.cursor() as cursor:
                if winner=="off":
                    store._insert_managed_event(cursor,"claim_auxiliary_off_attempt",{"execution_id":body["execution_id"],"attempt":1})
                elif winner=="parent_stop":
                    store._insert_managed_event(cursor,"mark_stopping",{**parent,"state":"stopping"})
                else:
                    canonical=ca.build_injector_target_active(body,body["command_on_receipt"],parent,now=datetime.now(timezone.utc))
                    store._insert_managed_event(cursor,"mark_auxiliary_active",canonical)
            locker.commit()
            result=pending.result(timeout=5)
            if winner=="activation":
                assert result["success"] and not result["created"],result
                assert result["execution"]["injector_target"]==canonical["injector_target"]
            else:
                assert result["success"] is False,result
        activations=[r for r in rows(body["execution_id"]) if r["action"]=="mark_auxiliary_active"]
        assert len(activations)==int(winner=="activation")
    finally:
        locker.rollback();locker.close()


def test_sql_concurrent_activations_derive_one_binding(packet):
    body,parent=packet
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(activate,[deepcopy(body),deepcopy(body)]))
    assert all(r["success"] for r in results),results
    assert sum(r["created"] for r in results)==1
    assert results[0]["execution"]["injector_target"]==results[1]["execution"]["injector_target"]


def test_sql_partial_terminal_cannot_strip_target_contract(packet):
    body,parent=packet;active=activate(body)["execution"]
    off=receipt(active,"OFF",at=datetime.now(timezone.utc))
    store.rootline_irrigation_execution_store("dispatch_auxiliary_off_edge",{
        "execution_id":active["execution_id"],"attempt":1,"dispatch":lambda:off})
    terminal=ca.terminal(active,off,reason="primary_deadline_reached")
    terminal.pop("injector_target");terminal.pop("injector_timing_contract")
    terminal["command_program_completed"]=True
    result=store.rootline_irrigation_execution_store("record_auxiliary_completed",terminal)
    assert result["success"] is False,result
