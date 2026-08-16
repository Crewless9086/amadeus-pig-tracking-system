from datetime import datetime, timedelta, timezone
import pytest

from modules.telemetry.rootline_irrigation_job_contract import (
    build_irrigation_job, project_next_segment,
)
from modules.telemetry.rootline_parent_job_resolution import (
    build_contained_parent_cancellation, record_contained_parent_cancellation,
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
        "job_id":job["job_id"],"job_sha256":job["job_sha256"]}
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
        assert action=="record_job_resolution"
        created=payload["execution_id"] not in seen
        seen[payload["execution_id"]]=payload
        return {"success":True,"created":created}
    first=record_contained_parent_cancellation(parent=parent,controller=controller,
        authorization=auth,store=store,now=NOW)
    replay=record_contained_parent_cancellation(parent=parent,controller=controller,
        authorization=auth,store=store,now=NOW)
    assert first["created"] is True and replay["created"] is False and len(seen)==1
    assert replay["hardware_commands"]==replay["provider_control_calls"]==0
    assert replay["water_credit_created"] is False
