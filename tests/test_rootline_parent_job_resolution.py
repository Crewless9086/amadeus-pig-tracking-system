from datetime import datetime, timedelta, timezone
import pytest

from modules.telemetry.rootline_irrigation_job_contract import (
    build_irrigation_job, project_next_segment,
)
from modules.telemetry.rootline_parent_job_resolution import (
    build_contained_parent_cancellation, record_contained_parent_cancellation,
    resolve_current_contained_b_parent, resolve_current_contained_parent,
)

NOW=datetime(2026,8,16,11,0,tzinfo=timezone.utc)


def subject(zone="B12345"):
    job=build_irrigation_job(zone_id=zone,operating_date="2026-08-16",
        requested_total_seconds=7200,maximum_segment_seconds=3599,
        plan_identity="PLAN-CURRENT",requested_total_minutes=120,
        expected_segment_count=2)
    first=project_next_segment(job,[],rearm_readback_off=True)
    parent={"job":job,"projection":{"status":"segment_contained","current_segment":2,
        "cumulative_verified_runtime_seconds":3599},"remaining_seconds":3599}
    from modules.telemetry.rootline_ewelink_oauth import normalize_device_readback
    controller=normalize_device_readback(device={"deviceid":"100204e9bc","online":True},
        status={"params":{"switches":[{"outlet":n,"switch":"off"} for n in range(4)]}},
        retrieved_at=NOW)
    controller["response_digest"]="OFF-READBACK"
    auth={"mission_id":"RMQ-20260813-04","decision":"cancel_unverified_remainder",
        "job_id":job["job_id"],"job_sha256":job["job_sha256"],
        "owner_principal":"charl"}
    completed={"action":"record_completed","job_id":job["job_id"],"segment_number":1,
        "segment_identity":first["segment_identity"],"execution_id":"EXEC-OLD",
        "state":"Completed","verified_runtime_seconds":3599,"shutdown_verified":True}
    return job,parent,controller,auth,completed


def test_terminal_cancellation_is_digest_stable_zero_effect_and_retires_remainder():
    job,parent,controller,auth,completed=subject()
    one=build_contained_parent_cancellation(parent=parent,controller=controller,
        authorization=auth,now=NOW)
    two=build_contained_parent_cancellation(parent=parent,controller=controller,
        authorization=auth,now=NOW+timedelta(seconds=1))
    assert one==two and one["hardware_commands"]==one["provider_control_calls"]==0
    assert one["fabricated_runtime_seconds"]==0 and one["water_credit_created"] is False
    projected=project_next_segment(job,[completed,{**one,"action":"record_job_resolution"}],
        rearm_readback_off=True)
    assert projected["status"]=="job_cancelled" and projected["remaining_seconds"]==0
    assert projected["cumulative_verified_runtime_seconds"]==3599
    with pytest.raises(ValueError):
        project_next_segment(job,[completed,{**one,"action":"record_job_resolution",
            "cumulative_verified_runtime_seconds":0}],rearm_readback_off=True)


def test_cancellation_requires_exact_job_authority_and_fresh_all_off_readback():
    _,parent,controller,auth,_=subject()
    for bad_auth,bad_controller in (
        ({**auth,"job_id":"OTHER"},controller),
        (auth,{**controller,"channels":[{"channel":1,"output_state":"ON"}]}),
        (auth,{**controller,"retrieved_at":(NOW-timedelta(minutes=6)).isoformat()})):
        with pytest.raises(ValueError):
            build_contained_parent_cancellation(parent=parent,controller=bad_controller,
                authorization=bad_auth,now=NOW)


def test_record_replay_is_append_idempotent_and_never_creates_credit_or_control():
    _,parent,controller,auth,_=subject(); seen={}
    def store(action,payload):
        if action=="record_job_resolution":
            created=payload["execution_id"] not in seen
            seen.setdefault(payload["execution_id"],{**payload,"action":action})
            return {"success":True,"created":created}
        assert action=="load_job_events"
        return list(seen.values())
    first=record_contained_parent_cancellation(parent=parent,controller=controller,
        authorization=auth,store=store,now=NOW)
    replay=record_contained_parent_cancellation(parent=parent,controller=controller,
        authorization=auth,store=store,now=NOW)
    assert first["created"] is True and replay["created"] is False and len(seen)==1
    assert replay["hardware_commands"]==replay["provider_control_calls"]==0
    assert replay["water_credit_created"] is False


def test_runtime_resolution_reloads_exact_parent_and_current_off_before_append():
    job,parent,controller,_,_=subject(); calls=[]
    request={"contract_version":"rootline_parent_job_terminal_resolution_request.v1",
        "mission_id":"RMQ-20260813-04","decision":"cancel_unverified_remainder",
        "zone_id":"B12345","job_id":job["job_id"],"job_sha256":job["job_sha256"]}
    result,status=resolve_current_contained_b_parent(request,"charl",
        history_loader=lambda:{"status":"Available","zones":{"B12345":{
            "contained_parent_jobs":[parent]}}},readback_loader=lambda:controller,
        store=_recording_store(calls),now=NOW)
    assert status==201 and result["status"]=="contained_parent_cancelled"
    assert result["hardware_commands"]==result["provider_control_calls"]==0
    assert calls[0][0]=="load_job_events"
    writes=[payload for action,payload in calls if action=="record_job_resolution"]
    assert len(writes)==1 and writes[0]["owner_principal"]=="charl"


def test_runtime_resolution_fails_closed_on_stale_binding_or_on_readback():
    job,parent,controller,_,_=subject()
    request={"contract_version":"rootline_parent_job_terminal_resolution_request.v1",
        "mission_id":"RMQ-20260813-04","decision":"cancel_unverified_remainder",
        "zone_id":"B12345","job_id":job["job_id"],"job_sha256":job["job_sha256"]}
    cases=[({"status":"Available","zones":{"B12345":{
        "contained_parent_jobs":[]}}},controller),
        ({"status":"Available","zones":{"B12345":{
            "contained_parent_jobs":[parent]}}},
         {**controller,"channels":[{"channel":1,"output_state":"ON"}]})]
    for history,readback in cases:
        result,status=resolve_current_contained_b_parent(request,"charl",
            history_loader=lambda history=history:history,
            readback_loader=lambda readback=readback:readback,
            store=lambda action,payload:[] if action=="load_job_events" else pytest.fail("must not write"),now=NOW)
        assert status==409
        assert result["hardware_commands"]==result["provider_control_calls"]==0


def _recording_store(calls):
    stored=[]
    def store(action,payload):
        calls.append((action,payload))
        if action=="record_job_resolution":
            stored.append({**payload,"action":action})
            return {"success":True,"created":True}
        return list(stored)
    return store


def test_different_fresh_off_receipts_converge_on_one_job_scoped_cancellation():
    _,parent,controller,auth,_=subject(); stored={}
    def store(action,payload):
        if action=="record_job_resolution":
            created=payload["execution_id"] not in stored
            stored.setdefault(payload["execution_id"],{**payload,"action":action})
            return {"success":True,"created":created}
        return list(stored.values())
    first=record_contained_parent_cancellation(parent=parent,controller=controller,
        authorization=auth,store=store,now=NOW)
    second_controller={**controller,"retrieved_at":(NOW+timedelta(seconds=1)).isoformat(),
        "response_digest":"NEW-OFF-READBACK"}
    second=record_contained_parent_cancellation(parent=parent,controller=second_controller,
        authorization=auth,store=store,now=NOW+timedelta(seconds=1))
    assert first["created"] is True and second["created"] is False
    assert first["resolution"]==second["resolution"] and len(stored)==1


@pytest.mark.parametrize("zone",["B12345","C12345"])
def test_generic_resolution_for_both_camps_and_replay_after_parent_disappears(zone):
    job,parent,controller,_,_=subject(zone); calls=[]
    request={"contract_version":"rootline_parent_job_terminal_resolution_request.v1",
        "mission_id":"RMQ-20260813-04","decision":"cancel_unverified_remainder",
        "zone_id":zone,"job_id":job["job_id"],"job_sha256":job["job_sha256"]}
    store=_recording_store(calls)
    first,status=resolve_current_contained_parent(request,"charl",
        history_loader=lambda:{"status":"Available","zones":{zone:{"contained_parent_jobs":[parent]}}},
        readback_loader=lambda:controller,store=store,now=NOW)
    assert status==201 and first["resolution"]["zone_id"]==zone
    assert first["resolution"]["cumulative_verified_runtime_seconds"]==3599
    before=len(calls)
    replay,status=resolve_current_contained_parent(request,"charl",
        history_loader=lambda:pytest.fail("replay must not need a current parent"),
        readback_loader=lambda:pytest.fail("replay must not make a provider call"),
        store=store,now=NOW+timedelta(days=2))
    assert status==200 and replay["created"] is False
    assert replay["resolution"]==first["resolution"]
    assert [action for action,_ in calls[before:]]==["load_job_events"]


@pytest.mark.parametrize("zone",["B12345","C12345"])
@pytest.mark.parametrize("observed_offset",[-360,120])
def test_real_provider_normalization_rejects_stale_or_future_device_evidence(zone,observed_offset):
    from modules.telemetry.rootline_ewelink_oauth import normalize_device_readback
    _,parent,_,auth,_=subject(zone)
    controller=normalize_device_readback(device={"deviceid":"100204e9bc","online":True},
        status={"updatedAt":(NOW+timedelta(seconds=observed_offset)).isoformat(),
            "params":{"switches":[{"outlet":n,"switch":"off"} for n in range(4)]}},retrieved_at=NOW)
    controller["response_digest"]="AUTHENTICATED-GET"
    assert controller["observation_fresh"] is False
    with pytest.raises(ValueError,match="current_provider_off_evidence_invalid"):
        build_contained_parent_cancellation(parent=parent,controller=controller,authorization=auth,now=NOW)


def test_provider_observation_must_still_be_fresh_after_lock_wait():
    from modules.telemetry.rootline_ewelink_oauth import normalize_device_readback
    _,parent,_,auth,_=subject()
    controller=normalize_device_readback(device={"deviceid":"100204e9bc","online":True},
        status={"updatedAt":(NOW-timedelta(minutes=4)).isoformat(),
            "params":{"switches":[{"outlet":n,"switch":"off"} for n in range(4)]}},retrieved_at=NOW)
    controller["response_digest"]="AUTHENTICATED-GET"
    assert controller["observation_fresh"] is True
    with pytest.raises(ValueError,match="current_provider_off_evidence_invalid"):
        build_contained_parent_cancellation(parent=parent,controller=controller,
            authorization=auth,now=NOW+timedelta(minutes=2))


@pytest.mark.parametrize("change",[
    {"device_id":"wrong-controller"},{"online":False},{"observation_fresh":False},
    {"current_outputs_authoritative":False},{"response_digest":""},
    {"channels":[{"channel":n,"output_state":"OFF"} for n in (1,1,3,4)]},
    {"channels":[{"channel":n,"output_state":"OFF"} for n in (True,2,3,4)]},
    {"retrieved_at":(NOW+timedelta(seconds=1)).isoformat()},
])
def test_invalid_off_evidence_cannot_retire_a_parent(change):
    _,parent,controller,auth,_=subject("C12345")
    with pytest.raises(ValueError,match="current_provider_off_evidence_invalid"):
        build_contained_parent_cancellation(parent=parent,controller={**controller,**change},
            authorization=auth,now=NOW)


@pytest.mark.parametrize("field,value",[
    ("remaining_seconds",None),("remaining_seconds",0),("remaining_seconds",True),
    ("remaining_seconds",3598),("cumulative_verified_runtime_seconds",None),
    ("cumulative_verified_runtime_seconds",False),("current_segment",3),
])
def test_unknown_or_inconsistent_accounting_cannot_be_converted_into_zero(field,value):
    _,parent,controller,auth,_=subject()
    if field=="remaining_seconds": parent[field]=value
    else: parent["projection"][field]=value
    with pytest.raises(ValueError,match="contained_parent_accounting_unproven"):
        build_contained_parent_cancellation(parent=parent,controller=controller,authorization=auth,now=NOW)


@pytest.mark.parametrize("field,value",[("owner_principal","other"),("zone_id","C12345"),
    ("job_sha256","wrong"),("job_id","wrong"),("resolution_sha256","wrong")])
def test_saved_decision_conflicts_are_not_successful_replays(field,value):
    job,parent,controller,auth,_=subject()
    saved={**build_contained_parent_cancellation(parent=parent,controller=controller,
        authorization=auth,now=NOW),"action":"record_job_resolution"}
    saved[field]=value
    request={"contract_version":"rootline_parent_job_terminal_resolution_request.v1",
        "zone_id":"B12345",**auth}
    result,status=resolve_current_contained_parent(request,"charl",
        store=lambda action,payload:[saved],
        history_loader=lambda:pytest.fail("conflicting saved record must fail closed"),now=NOW)
    assert status==409 and result["success"] is False


def test_legacy_b_entry_point_never_silently_expands_to_c():
    result,status=resolve_current_contained_b_parent({"zone_id":"C12345"},"charl",
        store=lambda *_:pytest.fail("compatibility boundary must reject before I/O"))
    assert status==400 and result["success"] is False


@pytest.mark.parametrize("payload",[None,[],[1],"invalid",17])
def test_malformed_request_is_a_controlled_client_error(payload):
    result,status=resolve_current_contained_parent(payload,"charl",
        store=lambda *_:pytest.fail("invalid input must not access persistence"))
    assert status==400 and result["success"] is False


def test_existing_route_keeps_owner_admin_session_and_server_principal(monkeypatch):
    from flask import Flask,session
    from modules.auth.owner_access import set_owner_session
    from modules.telemetry import telemetry_routes as routes
    for key,value in {"OWNER_ACCESS_ENABLED":"true","OWNER_ACCESS_ALLOW_LOCAL_DEV":"false",
            "OWNER_SESSION_SECRET":"s"*40,"OWNER_ADMIN_TOKEN":"a"*40,
            "OWNER_READ_TOKEN":"r"*40}.items(): monkeypatch.setenv(key,value)
    app=Flask(__name__); app.secret_key="test-secret"; app.config["TESTING"]=True
    app.register_blueprint(routes.telemetry_bp,url_prefix="/api")
    calls=[]
    def resolve(payload,principal):
        calls.append((payload,principal)); return {"success":True},201
    monkeypatch.setattr(routes,"resolve_current_contained_parent",resolve)
    endpoint="/api/telemetry/rootline/contained-parent-resolution"
    client=app.test_client()
    assert client.post(endpoint,json={"zone_id":"C12345"}).status_code==403
    for role in ("read","admin"):
        with app.test_request_context():
            set_owner_session(role); saved=dict(session)
        with client.session_transaction() as target: target.update(saved)
        result=client.post(endpoint,json={"zone_id":"C12345","owner_principal":"forged"})
        assert result.status_code==(201 if role=="admin" else 403)
    assert len(calls)==1 and calls[0][1].startswith("owner-admin:")
    assert calls[0][1]!="forged"
