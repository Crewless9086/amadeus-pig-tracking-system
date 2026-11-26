"""Prospective owner injector policy on the existing command and supervision rails."""
from copy import deepcopy
from datetime import timedelta
import pytest
from modules.telemetry import rootline_owner_auxiliary_policy as policy
from modules.telemetry import rootline_auxiliary_management as auxiliary
from modules.telemetry import rootline_command_acceptance as ca
from modules.telemetry import rootline_managed_devices_runtime as managed
from modules.telemetry.rootline_owner_controls import _owner_auxiliary_gate
from tests.test_rootline_injector_target import Database, fixture
from tests.test_rootline_command_mode import receipt, ENV
from modules.telemetry.rootline_timed_control import timed_control_scope


def controls(**changes):
    return {"devices": {"injection": {"fields": {
        "pulse_minutes": 10, "pulses_per_60_minutes": 2,
        **{"inject_camp_"+c: True for c in ("a", "b", "c", "e")}, **changes}}}}


def versioned_database(monkeypatch, minutes=10):
    d = Database(monkeypatch)
    now = ca.moment(d.body["claimed_at"])
    config = policy.owner_injection_policy(controls(pulse_minutes=minutes), now=now)
    claim = {**d.rows[0], "injection_policy": config, "injector_timing_contract": ca.INJECTOR_TARGET_V2,
        "pulse_number": 1, "phase_number": 1, "maximum_duration_seconds": minutes*60,
        "primary_stop_deadline": (now+timedelta(minutes=minutes)).isoformat()}
    claim.pop("action")
    on = receipt(claim, "ON", at=now+timedelta(seconds=4))
    on["accepted_at"] = (now+timedelta(seconds=9)).isoformat()
    on["receipt_sha256"] = ca.digest({k:v for k,v in on.items() if k != "receipt_sha256"})
    d.body = {**claim, "state": "Active", "on_attempts": 1, "command_on_receipt": on}
    d.rows = [{**claim,"action":"claim_auxiliary_before_on"},
        {**claim,"action":"claim_auxiliary_dispatch"},
        {**claim,"action":"record_auxiliary_on_outcome","on_outcome":on}]
    return d


@pytest.mark.parametrize("minutes", [1, 2, 10])
def test_locked_new_target_replay_and_pinned_original_duration(monkeypatch, minutes):
    d = versioned_database(monkeypatch, minutes)
    result = d.activate()
    assert result["success"] and result["created"]
    active = result["execution"]
    assert ca.injector_target_matches_rows(active, d.rows)
    assert ca.injector_target_timing(active)["target_seconds"] == minutes*60
    assert ca.command_stop_deadline(active) == ca.moment(active["command_on_receipt"]["accepted_at"])+timedelta(minutes=minutes)
    before = deepcopy(active)
    d.now += timedelta(seconds=20)
    replay = d.activate()
    assert replay["success"] and not replay["created"] and replay["execution"] == before
    assert len([r for r in d.rows if r["action"] == "mark_auxiliary_active"]) == 1
    assert not _owner_auxiliary_gate(None, "injection", active, d.now, controls(pulse_minutes=3))
    assert ca.injector_target_binding(active) and active == before


def test_legacy_claim_digest_and_target_never_change():
    now, body, rows, parents = fixture()
    original = ca.injector_claim_digest(body)
    assert original == ca.digest({k:body.get(k) for k in ca._INJECTOR_CLAIM_FIELDS})
    active = ca.build_injector_target_active(body, body["command_on_receipt"], parents[-1], now=now+timedelta(seconds=10))
    assert active["injector_target"]["target_seconds"] == 120
    malformed = {**body, "maximum_duration_seconds": 600}
    assert not ca.injector_target_claim(malformed)
    assert ca.injector_claim_digest(body) == original


@pytest.mark.parametrize("field,value", [
    ("pulse_minutes",0),("pulse_minutes",11),("pulse_minutes",True),
    ("pulses_per_60_minutes",3),("pulses_per_60_minutes",1.5),("inject_camp_a",1)])
def test_configuration_rejects_invalid_fields(field,value):
    with pytest.raises(ValueError):
        policy.validate_auxiliary_control_fields("injection",{field:value})


@pytest.mark.parametrize("case", ["missing", "expired", "future", "native"])
def test_current_overlay_discards_stale_policy(case):
    now = fixture()[0]
    selected = controls()
    context = {"stop_mode":"scheduled","acceptance_mode":ca.MODE,"injection_policy":{"stale":True}}
    if case=="missing": selected={}
    elif case=="expired": selected["devices"]["injection"]["expires_at"]=(now-timedelta(seconds=1)).isoformat()
    elif case=="future": selected["devices"]["injection"]["effective_at"]=(now+timedelta(seconds=1)).isoformat()
    else: context["stop_mode"]="native"
    assert "injection_policy" not in policy.injection_policy_context(context, selected, now=now)


def test_explicit_new_save_replaces_legacy_cap_but_absent_save_preserves_it():
    now = fixture()[0]
    old={"devices":{"injection":{"fields":{"max_pulses_per_run":1}}}}
    assert policy.owner_injection_policy(old,now=now) is None
    assert policy.owner_injection_pulse_limit(old,now=now)==1
    ctx=policy.injection_policy_context({"stop_mode":"scheduled","acceptance_mode":ca.MODE,"planned_runtime_seconds":7200},
        controls(max_pulses_per_run=1),now=now)
    assert auxiliary._pulse_limit(ctx)==4
    assert ctx["injection_policy"]["pulse_seconds"]==600


def test_long_pulse_handoff_does_not_wait_or_stop_and_keeps_exact_target(monkeypatch):
    d=versioned_database(monkeypatch)
    active=d.activate()["execution"]
    before=deepcopy(active)
    def forbidden(*args,**kwargs): pytest.fail("long pulse must hand back without waiting or device calls")
    assert managed._finish_injector_deadline(store=forbidden,transport=object(),clock=lambda:d.now,
        wait=forbidden,horizon_seconds=120,require_stop=False,active=active) is None
    assert active==before


@pytest.mark.parametrize("count,expected", [(1,[1,2]),(2,[1,2,3,4])])
def test_hour_slots_and_counts_are_deterministic(count,expected):
    now=fixture()[0]
    ctx=policy.injection_policy_context({"stop_mode":"scheduled","acceptance_mode":ca.MODE,
        "planned_runtime_seconds":7200,"zone_start_evidence":{"observed_at":now.isoformat()}},
        controls(pulses_per_60_minutes=count),now=now)
    seen=[]
    for hour in (0,1):
        at=now+timedelta(hours=hour,minutes=10)
        for _ in range(count):
            index=auxiliary._next_pulse_index(ctx,at)
            seen.append(index+1)
            ctx["completed_pulse_numbers"]=list(seen)
    assert seen==expected and auxiliary._pulse_limit(ctx)==len(expected)


@pytest.mark.parametrize("field,value", [("zone_id","UNKNOWN"),("maximum_duration_seconds",601),
    ("phase_number",2),("pulse_number",True)])
def test_new_claim_rejects_identity_or_duration_drift(monkeypatch,field,value):
    d=versioned_database(monkeypatch)
    claim=deepcopy(d.rows[0]);claim[field]=value
    assert not ca.injector_target_claim(claim)


def admission(zone="B12345", *, minutes=10, count=2):
    from tests.test_rootline_command_mode import start
    from modules.telemetry.rootline_water_energy_plan import _active_irrigation_context
    _, _, store, transport, clock = start(zone)
    clock[0] += timedelta(seconds=600)
    context = _active_irrigation_context(store.active, [], True, "TEST-BATCH", now=clock[0])
    context.update(premix_command_accepted=True, fertilizer_history_complete_through=clock[0].isoformat())
    context["zone_output_evidence"]=transport.read_output_state(device_id=store.active["device_id"],channel=store.active["channel"])
    context=policy.injection_policy_context(context,controls(pulse_minutes=minutes,pulses_per_60_minutes=count),now=clock[0])
    safety=transport.read_safety_configuration(device_id="100204d497",channel=1)
    artifact=auxiliary.build_auxiliary_eligibility(task={"auxiliary_device_id":"FERTILIZER-INJECTION-CH1"},
        context=context,safety=safety,flags={"ROOTLINE_FERTILIZER_INJECTION_ENABLED":True},now=clock[0])
    return store,transport,clock,context,safety,artifact


@pytest.mark.parametrize("zone", ["A12345","B12345","C12345","E12345"])
def test_all_commissioned_camps_real_coordinator_claim_and_duplicate(zone):
    from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution
    from modules.telemetry.rootline_irrigation_execution_store import _scheduled_auxiliary_claim_valid
    with timed_control_scope(ENV):
        store,transport,clock,context,safety,artifact=admission(zone)
        assert artifact["eligible"] and artifact["maximum_duration_seconds"]==600,artifact
        result=advance_auxiliary_execution(eligibility=artifact,revalidate=lambda _:context,
            store=store,transport=transport,now=clock[0],clock=lambda:clock[0],auxiliary_device_id="FERTILIZER-INJECTION-CH1")
        assert result["status"]=="auxiliary_on_command_accepted",result
        active=store.auxiliary["FERTILIZER-INJECTION-CH1"]
        assert active["injector_target"]["target_seconds"]==600
        assert _scheduled_auxiliary_claim_valid(active,artifact,clock[0])
        altered={**active,"injection_policy":policy.owner_injection_policy(controls(pulse_minutes=3),now=clock[0])}
        assert not _scheduled_auxiliary_claim_valid(altered,artifact,clock[0])
        before=len(transport.calls)
        again=advance_auxiliary_execution(eligibility=artifact,revalidate=lambda _:context,
            store=store,transport=transport,now=clock[0],clock=lambda:clock[0],auxiliary_device_id="FERTILIZER-INJECTION-CH1")
        assert again["status"]=="auxiliary_command_duty_active"
        assert len(transport.calls)==before
        original=deepcopy(active)
        clock[0]+=timedelta(seconds=180)
        ongoing=advance_auxiliary_execution(eligibility={},store=store,transport=transport,
            now=clock[0],clock=lambda:clock[0],auxiliary_device_id="FERTILIZER-INJECTION-CH1")
        assert ongoing["status"]=="auxiliary_command_duty_active"
        assert store.auxiliary["FERTILIZER-INJECTION-CH1"]==original


@pytest.mark.parametrize("case", ["preflow","flush","camp_disabled","policy_drift"])
def test_new_policy_timing_and_fresh_edge_fail_closed(case):
    with timed_control_scope(ENV):
        store,transport,clock,context,safety,artifact=admission()
        assert artifact["eligible"]
        if case=="preflow":
            context["zone_start_evidence"]["observed_at"]=(clock[0]-timedelta(seconds=599)).isoformat()
        elif case=="flush":
            context["irrigation_stop_deadline"]=(clock[0]+timedelta(seconds=2399)).isoformat()
        elif case=="camp_disabled":
            context=policy.injection_policy_context(context,controls(inject_camp_b=False),now=clock[0])
        else:
            context=policy.injection_policy_context(context,controls(pulse_minutes=9),now=clock[0])
        assert not auxiliary.revalidate_auxiliary_execution_edge(artifact,current_context=context,current_safety=safety,now=clock[0])


@pytest.mark.parametrize("case", ["parent_loss","deadline","late_activation"])
def test_long_pulse_restart_shutdown_and_late_activation(monkeypatch,case):
    from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution
    with timed_control_scope(ENV):
        store,transport,clock,context,safety,artifact=admission()
        started=advance_auxiliary_execution(eligibility=artifact,revalidate=lambda _:context,
            store=store,transport=transport,now=clock[0],clock=lambda:clock[0],auxiliary_device_id="FERTILIZER-INJECTION-CH1")
        active=deepcopy(store.auxiliary["FERTILIZER-INJECTION-CH1"])
        deadline=ca.command_stop_deadline(active)
        if case=="late_activation":
            with pytest.raises(ValueError):
                ca.build_injector_target_active(active,active["command_on_receipt"],store.active,now=deadline+timedelta(seconds=1))
            return
        if case=="parent_loss":
            clock[0]+=timedelta(seconds=180)
            store.active=None
        else:
            clock[0]=deadline
        result=advance_auxiliary_execution(eligibility={},store=store,transport=transport,
            now=clock[0],clock=lambda:clock[0],auxiliary_device_id="FERTILIZER-INJECTION-CH1")
        assert result["status"]=="auxiliary_off_command_accepted",result
        terminal=next(r for r in reversed(store.rows) if r["action"]=="record_auxiliary_completed")
        assert terminal["primary_stop_deadline"]==active["primary_stop_deadline"]
        assert ca.program_completed(terminal)==(case=="deadline")
        assert len([c for c in transport.calls if c[0]=="100204d497" and c[2]=="ON"])==1
        assert len([c for c in transport.calls if c[0]=="100204d497" and c[2]=="OFF"])==1

def test_full_settings_snapshot_matches_actual_editable_schema_and_legacy_shape():
    from modules.telemetry.rootline_owner_controls import _validate_owner_fields, owner_device_settings
    now=fixture()[0]
    state=controls()
    state["devices"]["injection"].update(mode="automatic")
    schema=owner_device_settings("injection",state,{},now)
    editable={field["key"]:field["value"] for field in schema["fields"] if field["editable"]}
    assert set(editable)==set(policy.INJECTION_POLICY_FIELDS)
    assert _validate_owner_fields("injection",editable,require_full=True)==editable
    assert _validate_owner_fields("injection",{"max_pulses_per_run":1},require_full=True)=={"max_pulses_per_run":1}
    for bad in ({**editable,"max_pulses_per_run":1},{k:v for k,v in editable.items() if k!="inject_camp_e"},{**editable,"unknown":True}):
        with pytest.raises(ValueError):
            _validate_owner_fields("injection",bad,require_full=True)


@pytest.mark.parametrize("canonical_readback", [True, False])
def test_managed_wrapper_handoff_requires_canonical_readback(monkeypatch, canonical_readback):
    from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution
    with timed_control_scope(ENV):
        store,transport,clock,context,safety,artifact=admission()
        started=advance_auxiliary_execution(eligibility=artifact,revalidate=lambda _:context,
            store=store,transport=transport,now=clock[0],clock=lambda:clock[0],auxiliary_device_id="FERTILIZER-INJECTION-CH1")
        active=deepcopy(store.auxiliary["FERTILIZER-INJECTION-CH1"])
        monkeypatch.setattr(managed,"_run_rootline_managed_device_cycle",lambda **kwargs:started)
        first=[True]
        def readback(action,body):
            if action=="load_active_auxiliary" and first[0]:
                first[0]=False
                if not canonical_readback: raise RuntimeError("unconfirmed persistence")
            return store(action,body)
        def forbidden_wait(seconds): pytest.fail("no600second scheduler wait")
        result=managed.run_rootline_managed_device_cycle(store=readback,transport=transport,
            clock=lambda:clock[0],deadline_wait=forbidden_wait)
        if canonical_readback:
            assert result["short_auxiliary_duty_owned"] is True
            assert ca.moment(result["short_auxiliary_stop_deadline"])==ca.command_stop_deadline(active)
            assert not any(c[0]=="100204d497" and c[2]=="OFF" for c in transport.calls)
        else:
            assert not result.get("short_auxiliary_duty_owned")
            assert any(c[0]=="100204d497" and c[2]=="OFF" for c in transport.calls)


@pytest.mark.parametrize("zone", ["A12345","E12345"])
def test_default_policy_does_not_enable_new_camps(zone):
    with timed_control_scope(ENV):
        store,transport,clock,context,safety,artifact=admission(zone)
        context=policy.injection_policy_context(context,{},now=clock[0])
        assert auxiliary._injection_gate(context,clock[0])=="exactly_one_bc_zone_required"


def test_two_ten_minute_pulses_spacing_and_hour_boundary():
    from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution
    from modules.telemetry.rootline_water_energy_plan import _active_irrigation_context
    with timed_control_scope(ENV):
        store,transport,clock,context,safety,artifact=admission()
        initial=clock[0]-timedelta(minutes=10)
        for index in (1,2):
            if index==2:
                context=_active_irrigation_context(store.active,store.rows,True,"TEST-BATCH",now=clock[0])
                context.update(premix_command_accepted=True,fertilizer_history_complete_through=clock[0].isoformat())
                context["zone_output_evidence"]=transport.read_output_state(device_id=store.active["device_id"],channel=store.active["channel"])
                context=policy.injection_policy_context(context,controls(),now=clock[0])
                assert auxiliary._injection_gate(context,clock[0])=="pulse_spacing_incomplete"
                clock[0]+=timedelta(minutes=10)
                context["fertilizer_history_complete_through"]=clock[0].isoformat()
                context["zone_output_evidence"]=transport.read_output_state(device_id=store.active["device_id"],channel=store.active["channel"])
                safety=transport.read_safety_configuration(device_id="100204d497",channel=1)
                artifact=auxiliary.build_auxiliary_eligibility(task={"auxiliary_device_id":"FERTILIZER-INJECTION-CH1"},
                    context=context,safety=safety,flags={"ROOTLINE_FERTILIZER_INJECTION_ENABLED":True},now=clock[0])
            assert artifact["eligible"] and artifact["pulse_number"]==index,artifact
            result=advance_auxiliary_execution(eligibility=artifact,revalidate=lambda _:context,
                store=store,transport=transport,now=clock[0],clock=lambda:clock[0],auxiliary_device_id="FERTILIZER-INJECTION-CH1")
            assert result["status"]=="auxiliary_on_command_accepted",result
            clock[0]+=timedelta(minutes=10)
            result=advance_auxiliary_execution(eligibility={},store=store,transport=transport,
                now=clock[0],clock=lambda:clock[0],auxiliary_device_id="FERTILIZER-INJECTION-CH1")
            assert result["status"]=="auxiliary_off_command_accepted"
        assert clock[0]==initial+timedelta(minutes=40)
        onrows=[r for r in store.rows if r["action"]=="record_auxiliary_on_outcome"]
        assert len(onrows)==2
        assert [ca.moment(r["on_outcome"]["accepted_at"]) for r in onrows]==[initial+timedelta(minutes=10),initial+timedelta(minutes=30)]
        terminals=[r for r in store.rows if r["action"]=="record_auxiliary_completed"]
        assert all(ca.program_completed(r) and ca.injector_target_timing(r)["target_seconds"]==600 for r in terminals)

from tests.test_rootline_owner_controls import memory_api


def test_actual_preview_apply_and_replay_with_checkbox_fields(memory_api):
    from modules.telemetry import rootline_owner_controls as api
    from tests.test_rootline_owner_controls import NOW, ACTOR
    state=api.project_owner_controls(memory_api,now=NOW)
    fields=controls()["devices"]["injection"]["fields"]
    body={"kind":"settings","device_id":"injection","reason":"Owner selected injection programme",
        "expected_revision":state["devices"]["injection"]["revision"],"idempotency_key":"injector-preview-001",
        "changes":{"mode":"automatic","scope":"ongoing","fields":fields}}
    preview,status=api.preview_owner_control(body,ACTOR,now=NOW)
    assert status==200,preview
    changes=preview["preview"]["changes"]
    assert {"label":"Inject in Camp A","before":"Disabled","after":"Enabled"} in changes
    assert {"label":"Injection duration (minutes)","before":2,"after":10} in changes
    request={"preview_id":preview["preview"]["id"],"preview_digest":preview["preview"]["digest"],
        "idempotency_key":"injector-apply-001"}
    saved,status=api.apply_owner_control(request,ACTOR,now=NOW)
    assert status==200 and saved["readback_bound"],saved
    replay,status=api.apply_owner_control(request,ACTOR,now=NOW+timedelta(days=1))
    assert status==200 and replay==saved
    projected=api.project_owner_controls(memory_api,now=NOW)
    assert projected["devices"]["injection"]["fields"]==fields
    assert policy.owner_injection_policy(projected,now=NOW)["zone_ids"]==["A12345","B12345","C12345","E12345"]
    assert len([row for row in memory_api if row["state"]=="confirmed"])==1

@pytest.mark.parametrize("old_count,new_count", [(1,2),(2,1)])
def test_count_change_never_reinterprets_existing_parent_pulse_ordinals(old_count,new_count):
    with timed_control_scope(ENV):
        store,transport,clock,context,safety,artifact=admission(count=new_count)
        context["prior_pulse_shutdown_evidence"]={"command_execution":{
            "injection_policy":policy.owner_injection_policy(controls(pulses_per_60_minutes=old_count),now=clock[0])}}
        assert auxiliary._injection_gate(context,clock[0])=="injection_count_changed_during_parent"
        assert not auxiliary.fertilizer_control_progress(context,now=clock[0])["completed"]
        del context["prior_pulse_shutdown_evidence"]
        assert auxiliary._injection_gate(context,clock[0]) is None


def test_changed_count_has_specific_nonblocking_task_reason():
    with timed_control_scope(ENV):
        store,transport,clock,context,safety,artifact=admission(count=1)
        context["prior_pulse_shutdown_evidence"]={"command_execution":{
            "injection_policy":policy.owner_injection_policy(controls(pulses_per_60_minutes=2),now=clock[0])}}
        result=auxiliary.build_auxiliary_tasks(batch={},active_irrigation_context=context,
            owner_controls=controls(pulses_per_60_minutes=1),now=clock[0])
        task=next(t for t in result["irrigation_auxiliary_tasks"] if t["device_type"]=="fertilizer_injection_valve")
        assert task["reason"]=="Injection count changes take effect on the next camp run"
        assert task["does_not_block_bc_irrigation"] is True


@pytest.mark.parametrize("policy_value", [{}, {"pulses_per_60_minutes":0}, "invalid"])
def test_malformed_context_policy_fails_without_attempting_commands(policy_value):
    with timed_control_scope(ENV):
        store,transport,clock,context,safety,artifact=admission()
        context["injection_policy"]=policy_value
        assert auxiliary._injection_gate(context,clock[0])=="injection_policy_invalid"


def test_selected_camp_projection_and_legacy_limit_are_truthful():
    from modules.telemetry.rootline_owner_controls import owner_device_settings, project_owner_controls
    from modules.telemetry.rootline_owner_control_projection import project_next_action
    now=fixture()[0]
    assert project_next_action("injection","FERTILIZER-INJECTION-CH1",controls(),{},now)=="Wait for an eligible A/B/C/E run"
    assert project_next_action("injection","FERTILIZER-INJECTION-CH1",{}, {},now)=="Wait for an eligible B/C run"
    state=project_owner_controls([],now=now)
    state["devices"]["injection"]["fields"]={"max_pulses_per_run":1}
    schema=owner_device_settings("injection",state,{},now)
    cap=next(field for field in schema["fields"] if field["key"]=="legacy_pulse_cap")
    assert cap["value"]==1 and cap["editable"] is False and "replaces" in cap["reason"]
