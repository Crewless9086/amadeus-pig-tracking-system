"""Real gateway/managed orchestration omits only an inert admission callback."""
from datetime import timedelta
import pytest
from tests.test_rootline_bc_starvation import ComposedPath, NOW


def active_path(monkeypatch):
    path=ComposedPath(monkeypatch, optional_seconds=1)
    path.gateway()
    assert path.backing.active["state"]=="Active"
    path.clock.elapsed=180
    path.fault_checks=0
    path.transport.calls.clear()
    path.clock.events.clear()
    return path


@pytest.mark.parametrize("planning,expected", [(False,1),(True,2)])
def test_owned_active_omits_only_inert_callback_pass(monkeypatch, planning, expected):
    path=active_path(monkeypatch)
    flags={} if planning else {"ROOTLINE_FERTILIZER_MIXING_ENABLED":"false",
        "ROOTLINE_FERTILIZER_INJECTION_ENABLED":"false"}
    result,_=path.gateway(tick=NOW+timedelta(minutes=3),environ=flags)
    assert result["active_supervision_status"]=="active_segment_owned"
    assert path.fault_checks==expected
    assert sum(name=="managed inventory" for name,_ in path.clock.events)==expected
    assert path.transport.calls==[]
    assert len(path.controls)==1


@pytest.mark.parametrize("failure", [False,True])
def test_active_planning_change_and_exception_still_get_fresh_safety(monkeypatch,failure):
    path=active_path(monkeypatch)
    def change():
        path.fault=lambda:False
        if failure:raise RuntimeError("optional planning failed after manual stop")
    path.optional_hook=change
    result,_=path.gateway(tick=NOW+timedelta(minutes=3))
    assert path.fault_checks==2
    assert [(row["device_id"],row["state"]) for row in path.transport.calls]==[("1002851416","OFF")]
    assert path.borehole is None
    assert any(action=="record_borehole_completed" for action,_ in path.backing.rows)


@pytest.mark.parametrize("failure", [False,True])
def test_real_admission_callback_change_and_exception_still_refresh(monkeypatch,failure):
    path=ComposedPath(monkeypatch,optional_seconds=1)
    original=path.cycle
    def callback(**kwargs):
        result=original(**kwargs)
        path.fault=lambda:False
        if failure:raise RuntimeError("admission result failed after manual stop")
        return result
    path.cycle=callback
    result,_=path.gateway()
    assert path.fault_checks>=2
    assert [(row["device_id"],row["state"]) for row in path.transport.calls]==[
        ("100204e9bc","ON"),("1002851416","OFF")]
    names=[name for name,_ in path.clock.events]
    assert names.index("provider ON")<names.index("provider OFF")
    assert path.borehole is None


def test_active_irrigation_keeps_unsent_proof_optional_when_budget_expired(monkeypatch):
    from tests.test_rootline_no_send_scheduling import Scenario
    from tests.test_rootline_active_supervision import gateway, ExecutionStore, Transport, ScheduleStore, NOW as GATEWAY_NOW, ENV
    from modules.telemetry import rootline_managed_devices_runtime as managed
    scenario=Scenario(monkeypatch)
    def exhausted():raise managed.RootlineCycleDeadlineExceeded("expired optional window")
    monkeypatch.setattr(managed,"remaining_seconds",exhausted)
    def managed_cycle(**kwargs):
        return managed.run_rootline_managed_device_cycle(evidence={},transport=object(),
            store=scenario.store,clock=lambda:scenario.now,**kwargs)
    schedules=ScheduleStore()
    schedules.rows["prior:outcome"]={"specialist":"ROOTLINE","status":"completed",
        "next_due_at":(GATEWAY_NOW+timedelta(minutes=30)).isoformat()}
    result,_,_,_=gateway(ExecutionStore(),Transport(),schedules=schedules,
        source_env={**ENV,"ROOTLINE_BOREHOLE_ENABLED":"true"},
        active_supervision_cycle=lambda **_: {"success":True,"status":"active_segment_owned",
            "active_execution_found":True,"hardware_commands":0},
        managed_device_cycle=managed_cycle,
        execution_cycle=lambda **_:pytest.fail("active irrigation cannot admit a second run"))
    assert scenario.events.count("OFF:UNSENT")==1
    assert "PROOF:UNSENT" not in scenario.events
    assert result["hardware_commands"]==1


def test_declared_inert_callback_exception_still_refreshes(monkeypatch):
    from tests.test_rootline_no_send_scheduling import Scenario
    from modules.telemetry import rootline_managed_devices_runtime as managed
    scenario=Scenario(monkeypatch)
    scenario.callback_failure=True
    with pytest.raises(RuntimeError,match="callback failure"):
        managed.run_rootline_managed_device_cycle(evidence={},transport=object(),
            store=scenario.store,environ={},clock=lambda:scenario.now,
            after_safety=scenario.admission,refresh_after_safety=False)
    assert "AUX_OFF:NEW-DUE" in scenario.events
    assert "PROOF:UNSENT" not in scenario.events



@pytest.mark.parametrize("kind", ["auxiliary", "borehole", "unknown_auxiliary"])
def test_initial_safety_time_cannot_hide_owned_deadline_without_optional_work(monkeypatch,kind):
    from modules.telemetry import rootline_managed_devices_runtime as managed
    current=[NOW]; events=[]
    auxiliary={"execution_id":"AUX","auxiliary_device_id":"FERTILIZER-MIXER-CH2",
        "device_type":"fertilizer_mixer","state":"Active",
        "primary_stop_deadline": (NOW+timedelta(seconds=1)).isoformat()}
    borehole={"execution_id":"BH","state":"Active",
        "primary_stop_deadline": (NOW+timedelta(seconds=1 if kind=="borehole" else 3600)).isoformat()}
    if kind=="unknown_auxiliary":auxiliary["primary_stop_deadline"]="unknown"
    if kind=="borehole":auxiliary=None
    def store(action,item):
        if action == "load_owner_control_stop": return None  # No saved owner stop in this baseline fixture.
        if action=="load_active_auxiliaries":
            events.append("inventory")
            return [dict(auxiliary)] if auxiliary else []
        if action=="load_active_borehole":return dict(borehole) if borehole else None
        pytest.fail(action)
    def advance_aux(**kwargs):
        nonlocal auxiliary
        if kind=="unknown_auxiliary" or current[0]>=datetime_from(auxiliary["primary_stop_deadline"]):
            events.append("AUX_OFF");auxiliary=None
        return {"success":True,"status":"auxiliary_active","hardware_commands":0}
    def advance_borehole(**kwargs):
        nonlocal borehole
        if current[0]>=datetime_from(borehole["primary_stop_deadline"]):
            events.append("BH_OFF");borehole=None
            return {"success":True,"status":"borehole_completed","hardware_commands":1}
        return {"success":True,"status":"borehole_active","hardware_commands":0}
    def safety():
        # Slow borehole work occurs after auxiliary supervision in this pass.
        current[0]+=timedelta(seconds=2)
        return True
    from datetime import datetime
    datetime_from=datetime.fromisoformat
    monkeypatch.setattr(managed,"advance_auxiliary_execution",advance_aux)
    monkeypatch.setattr(managed,"advance_borehole_execution",advance_borehole)
    managed.run_rootline_managed_device_cycle(evidence={},transport=object(),store=store,
        environ={},clock=lambda:current[0],allow_new_starts=False,
        borehole_safety_reader=safety,after_safety=lambda _:events.append("NOOP"),
        refresh_after_safety=False,
        evidence_factory=lambda **_:pytest.fail("no optional planning is needed"))
    assert events.count("inventory")==2
    assert ("BH_OFF" if kind=="borehole" else "AUX_OFF") in events
    if kind=="auxiliary":assert events.index("NOOP")<events.index("AUX_OFF")
