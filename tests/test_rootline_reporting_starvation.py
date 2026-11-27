"""No-effect admission skips only redundant middle supervision, never final safety."""
from copy import deepcopy
from datetime import timedelta
import pytest
from tests.test_rootline_bc_starvation import ComposedPath, NOW
from tests.test_rootline_active_supervision import reports


def inert(**changes):
    return {"success": True, "status": "planner_hold_or_no_dispatchable_zone",
        "hardware_commands": 0, "writes_farm_data": False, **changes}


@pytest.mark.parametrize("changed,expected", [({}, 2), ({"hardware_commands": 1}, 3),
    ({"hardware_commands": False}, 3), ({"hardware_commands": "0"}, 3),
    ({"hardware_commands": None}, 3), ({"writes_farm_data": None}, 3),
    ({"writes_farm_data": True}, 3), ({"effects_unknown": True}, 3),
    ({"success": False}, 3), ({"status": "unknown"}, 3),
    ({"status": "execution_store_degraded_hold"}, 3), ({"status": None}, 3)])
def test_composed_gateway_skips_only_proven_no_effect_admission(monkeypatch, changed, expected):
    path = ComposedPath(monkeypatch, optional_seconds=1)
    path.cycle = lambda **_: inert(**changed)
    result, _ = path.gateway()
    assert path.fault_checks == expected
    assert sum(name == "managed inventory" for name, _ in path.clock.events) == expected
    assert path.transport.calls == []


@pytest.mark.parametrize("missing", ["hardware_commands", "writes_farm_data", "success"])
def test_missing_admission_proof_keeps_middle_pass(monkeypatch, missing):
    path = ComposedPath(monkeypatch, optional_seconds=1)
    value = inert(); value.pop(missing)
    path.cycle = lambda **_: value
    path.gateway()
    assert path.fault_checks == 3


@pytest.mark.parametrize("result", [None, {}, {"success": True}])
def test_missing_or_unproven_callback_keeps_middle_pass(monkeypatch, result):
    path = ComposedPath(monkeypatch, optional_seconds=1)
    path.cycle = lambda **_: result
    path.gateway()
    assert path.fault_checks == 3


def test_slow_inert_callback_crossing_owned_deadline_still_stops(monkeypatch):
    path = ComposedPath(monkeypatch, optional_seconds=1)
    path.borehole['primary_stop_deadline'] = (NOW+timedelta(seconds=30)).isoformat()
    def callback(**_):
        path.clock.spend('slow inert admission', 40)
        return inert()
    path.cycle = callback
    path.gateway()
    assert path.borehole is None
    assert [row['state'] for row in path.transport.calls] == ['OFF']
    names = [name for name, _ in path.clock.events]
    assert names.index('slow inert admission') < names.index('provider OFF') < names.index('optional managed evidence')


@pytest.mark.parametrize('change', ['fault', 'canonical', 'new_owner', 'factory_exception'])
def test_no_effect_callback_retains_final_safety_after_planning(monkeypatch, change):
    path = ComposedPath(monkeypatch, optional_seconds=1)
    path.cycle = lambda **_: inert()
    def altered():
        if change in {'fault', 'factory_exception'}:
            path.fault = lambda: False
        elif change == 'canonical':
            path.borehole['state'] = 'Stopping'
        else:
            path.borehole['execution_id'] = 'NEW-OWNER'
            path.borehole['primary_stop_deadline'] = (NOW-timedelta(seconds=1)).isoformat()
        if change == 'factory_exception': raise RuntimeError('synthetic failed planning')
    path.optional_hook = altered
    path.gateway()
    assert path.borehole is None
    assert [row['state'] for row in path.transport.calls] == ['OFF']
    names = [name for name, _ in path.clock.events]
    assert names.index('optional managed evidence') < names.index('provider OFF')


@pytest.mark.parametrize('unknown', ['auxiliary', 'borehole'])
def test_false_callback_cannot_skip_incomplete_inventory(monkeypatch, unknown):
    from modules.telemetry import rootline_managed_devices_runtime as managed
    calls = []
    def store(action, payload):
        if action == "load_owner_control_stop": return None  # No saved owner stop in this baseline fixture.
        calls.append(action)
        if action == 'load_active_auxiliaries':
            return None if unknown == 'auxiliary' else []
        if action == 'load_active_borehole':
            if unknown == 'borehole': raise RuntimeError('unknown inventory')
            return None
        pytest.fail(action)
    managed.run_rootline_managed_device_cycle(evidence={}, transport=object(), store=store,
        environ={}, allow_new_starts=False, after_safety=lambda _: False, clock=lambda: NOW)
    assert calls.count('load_active_auxiliaries') == 2


@pytest.mark.parametrize('force_old', [False, True])
def test_reporting_reserve_after_inert_admission_with_real_gateway(monkeypatch, reports, force_old):
    from tests.test_rootline_active_supervision import gateway, payload, ENV, current
    path = ComposedPath(monkeypatch, optional_seconds=20)
    if force_old:
        # Preserve the historical comparison: the old three-pass coordinator
        # also lost its observation marker on a successful skipped read.
        from modules.telemetry import rootline_managed_devices_runtime as managed_runtime
        original_pass = managed_runtime._supervise_owned_devices_unbounded
        def old_bookmark(**kwargs):
            result = original_pass(**kwargs)
            if not result["outcomes"]:
                result["observed_borehole"] = None
            return result
        monkeypatch.setattr(managed_runtime, "_supervise_owned_devices_unbounded", old_bookmark)

    observed = []
    def callback(**_):
        path.clock.spend('inert eligibility read', 48)
        return inert()
    path.cycle = callback
    managed = path.managed
    def compose(**kwargs):
        if force_old:
            original = kwargs['after_safety']
            def discard_result(result): original(result)
            kwargs['after_safety'] = discard_result
        return managed(**kwargs)
    def report():
        observed.append(path.clock.elapsed)
        return {**current(), 'operating_date': NOW.date().isoformat(),
            'evidence_cutoff': (NOW-timedelta(seconds=2)).isoformat()}
    result, _, _, _ = gateway(path.backing, path.transport,
        schedules=path.schedules, scheduler_now=NOW,
        request_payload=payload(due_at=NOW.isoformat(), trigger_timestamp=NOW.isoformat(),
            evidence_cutoff=(NOW-timedelta(seconds=1)).isoformat()),
        source_env={**ENV,'ROOTLINE_BOREHOLE_ENABLED':'true',
            'ROOTLINE_FERTILIZER_MIXING_ENABLED':'true','ROOTLINE_FERTILIZER_INJECTION_ENABLED':'true'},
        active_supervision_cycle=path.supervisor, execution_cycle=callback,
        managed_device_cycle=compose, specialist_loader=report)
    assert path.transport.calls == []
    if force_old:
        assert result['status'] == 'scheduled_rootline_reporting_deadline_deferred', (path.clock.elapsed, observed, path.clock.events)
        assert not observed
    else:
        assert result['status'] != 'scheduled_rootline_reporting_deadline_deferred'
        assert observed and observed[0] <= 115
        assert result['plan_delivery_status'] == 'delivered_current_irrigation_plan'


@pytest.mark.parametrize('callback_value,expected', [(None,2),(0,2),({},2),(True,2),(False,1)])
def test_callback_opt_out_requires_exact_false(monkeypatch, callback_value, expected):
    from modules.telemetry import rootline_managed_devices_runtime as managed
    calls=[]
    def store(action,payload):
        if action == "load_owner_control_stop": return None  # No saved owner stop in this baseline fixture.
        calls.append(action)
        if action=='load_active_auxiliaries': return []
        if action=='load_active_borehole': return None
        pytest.fail(action)
    managed.run_rootline_managed_device_cycle(evidence={},transport=object(),store=store,
        environ={},allow_new_starts=False,after_safety=lambda _:callback_value,clock=lambda:NOW)
    assert calls.count('load_active_auxiliaries')==expected


@pytest.mark.parametrize('uncertain', [
    {'success':False}, {'success':True,'effects_unknown':True}, {'success':False,'effects_unknown':True}])
def test_initial_safety_uncertainty_keeps_refresh_with_complete_inventory(monkeypatch, uncertain):
    from modules.telemetry import rootline_managed_devices_runtime as managed
    calls=[]; passes=[]
    owned={'execution_id':'KNOWN-BOREHOLE','device_id':'1002851416','channel':1,
        'state':'Active','primary_stop_deadline':(NOW+timedelta(hours=1)).isoformat()}
    def store(action,payload):
        if action == "load_owner_control_stop": return None  # No saved owner stop in this baseline fixture.
        calls.append(action)
        if action=='load_active_auxiliaries': return []
        if action=='load_active_borehole': return deepcopy(owned)
        pytest.fail(action)
    def supervise(**kwargs):
        passes.append('supervise')
        return {'status':'borehole_supervision_unproven','hardware_commands':0,**uncertain}
    monkeypatch.setattr(managed,'advance_borehole_execution',supervise)
    managed.run_rootline_managed_device_cycle(evidence={},transport=object(),store=store,
        environ={},allow_new_starts=False,after_safety=lambda _:False,clock=lambda:NOW,
        borehole_safety_reader=lambda:True,
        evidence_factory=lambda **_:pytest.fail('no optional planning required'))
    assert calls.count('load_active_auxiliaries')==2
    assert calls.count('load_active_borehole')==2
    assert passes==['supervise','supervise']
