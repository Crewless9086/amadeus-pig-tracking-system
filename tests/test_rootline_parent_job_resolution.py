from datetime import datetime, timedelta, timezone
import pytest

from modules.telemetry.rootline_irrigation_job_contract import (
    build_irrigation_job, project_next_segment,
)
from modules.telemetry.rootline_parent_job_resolution import (
    build_contained_parent_cancellation, record_contained_parent_cancellation,
    resolve_current_contained_b_parent,
)

NOW=datetime(2026,8,16,11,0,tzinfo=timezone.utc)


def subject():
    job=build_irrigation_job(zone_id="B12345",operating_date="2026-08-16",
        requested_total_seconds=7200,maximum_segment_seconds=3599,
        plan_identity="PLAN-CURRENT",requested_total_minutes=120,
        expected_segment_count=2)
    first=project_next_segment(job,[],rearm_readback_off=True)
    parent={"job":job,"projection":{"status":"segment_contained","current_segment":2,
        "cumulative_verified_runtime_seconds":3599},"remaining_seconds":3599}
    controller={"online":True,"retrieved_at":NOW.isoformat(),"response_digest":"OFF-READBACK",
        "channels":[{"channel":n,"output_state":"OFF"} for n in range(1,5)]}
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
    assert calls[0][0]=="record_job_resolution"
    assert calls[0][1]["owner_principal"]=="charl"


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
            store=lambda *_:pytest.fail("must not write"),now=NOW)
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
