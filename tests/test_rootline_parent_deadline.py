"""Existing gateway budgets and OFF coordinators respect an owned parent deadline."""
from copy import deepcopy
from datetime import timedelta
from functools import partial
import pytest
from tests.test_rootline_active_supervision import reports, gateway, ExecutionStore, Transport, ScheduleStore, active, NOW
from modules.telemetry import rootline_cycle_budget as budget
from modules.telemetry import rootline_owned_deadlines as owned

def clocks(monkeypatch):
    wall=[NOW];mono=[1000.0]
    monkeypatch.setattr(budget.time,"monotonic",lambda:mono[0])
    monkeypatch.setattr(owned,"monotonic",lambda:mono[0])
    def advance(seconds):
        wall[0]+=timedelta(seconds=seconds);mono[0]+=seconds
    return wall,mono,advance

@pytest.mark.parametrize("stage",["managed","report","uncooperative","none"])
def test_gateway_deadline_caps_optional_work_and_rechecks(monkeypatch,reports,stage):
    wall,mono,advance=clocks(monkeypatch);deadline=NOW+timedelta(seconds=15);checks=[]
    execution={**active(due=False),"primary_stop_deadline":deadline.isoformat()}
    def supervisor(**kwargs):
        checks.append(wall[0])
        due=wall[0]>=deadline
        return {"success":True,"status":"segment_completed" if due else "active_segment_owned",
            "active_execution_found":True,"execution":execution,"hardware_commands":int(due),
            "telegram_sends":0,"writes_farm_data":due}
    def spend():
        advance(112 if stage=="uncooperative" else budget.remaining_seconds(maximum=112))
        budget.remaining_seconds()
    def managed(**kwargs):
        if stage in {"managed","uncooperative"}:spend()
        return {"success":True,"status":"no_eligible_managed_device_task","hardware_commands":0}
    from tests.test_rootline_active_supervision import current
    def loader():
        if stage=="report":spend()
        return current()
    # Unproven inventory must not sleep: the optional-budget path handles the deadline.
    def unknown(*args):raise ValueError("unknown inventory")
    value,code,starts,messages=gateway(ExecutionStore(None),Transport(),
        active_supervision_cycle=supervisor,managed_device_cycle=managed,specialist_loader=loader,
        supervision_clock=lambda:wall[0],parent_deadline_store=unknown,
        parent_deadline_wait=lambda _:pytest.fail("unknown inventory cannot wait"))
    assert not starts and len(checks)==(1 if stage=="none" else 2)
    assert checks[-1]==NOW+timedelta(seconds=0 if stage=="none" else 112 if stage=="uncooperative" else 15)
    assert value["hardware_commands"]==int(stage!="none")
    assert value["active_supervision_status"]==("active_segment_owned" if stage=="none" else "segment_completed")

@pytest.mark.parametrize("case",["clear","earlier_injector","earlier_borehole","unknown","reversed","expired","changed"])
def test_parent_wait_requires_inventory_and_original_bound(monkeypatch,case):
    wall,mono,advance=clocks(monkeypatch)
    parent={"execution_id":"parent","primary_stop_deadline":(NOW+timedelta(seconds=15)).isoformat()}
    other={"execution_id":"other","primary_stop_deadline":(NOW+timedelta(seconds=5)).isoformat()}
    waited=[]
    def store(action,payload):
        if case=="unknown":return None if action=="load_active_auxiliaries" else parent
        if action=="load_active_auxiliaries":return [other] if case=="earlier_injector" else []
        if action=="load_active_borehole":return other if case=="earlier_borehole" else None
        if case=="reversed":wall[0]-=timedelta(seconds=1)
        return {**parent,"execution_id":"changed"} if case=="changed" else parent
    def wait(seconds):waited.append(seconds);advance(seconds)
    with budget.cycle_budget(1140),budget.mandatory_safety():
        result=owned.wait_for_parent_deadline(parent,store=store,clock=lambda:wall[0],wait=wait,
            original_bound=1001 if case=="expired" else 1140)
    assert bool(waited)==(case=="clear")
    if case=="clear":assert result=="parent_due" and waited==[15]
    else:assert wall[0] < NOW+timedelta(seconds=15)

def test_real_active_only_coordinator_stops_after_bounded_wait(monkeypatch,reports):
    from modules.telemetry.rootline_execution_runtime import supervise_rootline_active_execution
    from tests.test_rootline_active_weather_stop import dry_weather_reader
    wall,mono,advance=clocks(monkeypatch)
    row=active(due=False);row["primary_stop_deadline"]=(NOW+timedelta(seconds=15)).isoformat()
    row["native_fail_stop_deadline"]=row["primary_stop_deadline"]
    row["claimed_at"]=(NOW-timedelta(seconds=3584)).isoformat()
    row["start_evidence"]["retrieved_at"]=(NOW-timedelta(seconds=3583)).isoformat()
    store=ExecutionStore(row);transport=Transport();schedules=ScheduleStore()
    original_read=transport.read_output_state
    monkeypatch.setattr(transport,"read_output_state",lambda **kw:{**original_read(**kw),"retrieved_at":wall[0].isoformat()})
    supervisor=partial(supervise_rootline_active_execution,store=store,transport=transport,
        token_store=object(),clock=lambda:wall[0],active_weather_reader=dry_weather_reader)
    value,code,starts,messages=gateway(store,transport,schedules=schedules,
        active_supervision_cycle=supervisor,supervision_clock=lambda:wall[0],
        parent_deadline_store=store,parent_deadline_wait=advance,
        managed_device_cycle=lambda **kwargs:{"success":True,"status":"no_eligible_managed_device_task","hardware_commands":0})
    assert wall[0]==NOW+timedelta(seconds=15)
    assert not starts and value["hardware_commands"]==1
    assert value["active_supervision_status"]=="segment_completed"
    assert store.active is None


def test_mandatory_inventory_crossing_checks_parent_before_next_read(monkeypatch):
    from modules.telemetry.rootline_managed_devices_runtime import _supervise_owned_devices
    wall,mono,advance=clocks(monkeypatch);events=[]
    def store(action,payload):
        events.append(action)
        if action=="load_active_auxiliaries":
            advance(16);return []
        assert action=="load_active_borehole"
        return None
    def checkpoint(**kwargs):
        if wall[0]>=NOW+timedelta(seconds=15):events.append("due_parent_check")
    with owned.owned_deadline_checkpoint(checkpoint):
        result=_supervise_owned_devices(store=store,transport=Transport(),
            energy_reader=None,borehole_safety_reader=None,clock=lambda:wall[0])
    assert result["auxiliary_inventory_proven"] and result["borehole_inventory_proven"]
    assert events.index("due_parent_check")<events.index("load_active_borehole")


def test_actual_managed_safety_stage_waits_before_optional_planner(monkeypatch,reports):
    from modules.telemetry import rootline_managed_devices_runtime as managed
    from modules.telemetry.rootline_execution_runtime import supervise_rootline_active_execution
    from tests.test_rootline_active_weather_stop import dry_weather_reader
    wall,mono,advance=clocks(monkeypatch)
    row=active(due=False);row["claimed_at"]=(NOW-timedelta(seconds=3584)).isoformat()
    row["primary_stop_deadline"]=(NOW+timedelta(seconds=15)).isoformat()
    row["native_fail_stop_deadline"]=row["primary_stop_deadline"]
    row["start_evidence"]["retrieved_at"]=(NOW-timedelta(seconds=3583)).isoformat()
    store=ExecutionStore(row);transport=Transport()
    original=transport.read_output_state
    monkeypatch.setattr(transport,"read_output_state",lambda **kw:{**original(**kw),"retrieved_at":wall[0].isoformat()})
    supervisor=partial(supervise_rootline_active_execution,store=store,transport=transport,
        token_store=object(),clock=lambda:wall[0],active_weather_reader=dry_weather_reader)
    plans=[]
    def cycle(**kwargs):
        return managed.run_rootline_managed_device_cycle(evidence={},store=store,transport=transport,
            environ=kwargs["environ"],clock=lambda:wall[0],now=wall[0],
            after_safety=kwargs.get("after_safety"),evidence_factory=lambda **kw:plans.append(kw) or {},
            allow_new_starts=True,connect_factory=lambda:pytest.fail("no new authority"))
    value,code,starts,messages=gateway(store,transport,active_supervision_cycle=supervisor,
        managed_device_cycle=cycle,supervision_clock=lambda:wall[0],parent_deadline_store=store,
        parent_deadline_wait=advance)
    assert wall[0]==NOW+timedelta(seconds=15) and not plans and not starts
    assert value["hardware_commands"]==1 and value["active_supervision_status"]=="segment_completed"


@pytest.mark.parametrize("failed", [False, True])
@pytest.mark.parametrize("kind", ["borehole","mixer"])
def test_earlier_timed_borehole_uses_existing_off_before_parent_wait(monkeypatch, failed, kind):
    from modules.telemetry import rootline_managed_devices_runtime as managed
    from tests.test_rootline_managed_devices_runtime import Store, Transport as BoreholeTransport
    wall, mono, advance = clocks(monkeypatch)
    parent = {"execution_id":"parent", "primary_stop_deadline":(NOW+timedelta(seconds=15)).isoformat()}
    base = Store()
    base.active_borehole = {"execution_id":"borehole", "state":"Active",
        "primary_stop_deadline":(NOW+timedelta(seconds=5)).isoformat(),
        "provider_start_evidence":{"authoritative":True,"state":"ON","retrieved_at":(NOW-timedelta(hours=1)).isoformat()}}
    if kind == "mixer":
        base.active_aux={"execution_id":"mixer","auxiliary_device_id":"FERTILIZER-MIXER-CH2",
            "device_type":"fertilizer_mixer","device_id":"100204d497","channel":2,
            "state":"Active","claimed_at":(NOW-timedelta(seconds=295)).isoformat(),
            "primary_stop_deadline":(NOW+timedelta(seconds=5)).isoformat(),
            "maximum_duration_seconds":300,"on_attempts":1,
            "start_evidence":{"authoritative":True,"state":"ON","retrieved_at":(NOW-timedelta(seconds=294)).isoformat()}}
        base.active_borehole=None
    def store(action, payload):
        if action == "load_active": return parent
        if action == "load_owner_control_stop": return None
        return base(action, payload)
    transport = BoreholeTransport()
    original_read = transport.read_output_state
    monkeypatch.setattr(transport,"read_output_state",lambda **kw:{**original_read(**kw),"retrieved_at":wall[0].isoformat()})
    attempts=[]
    original_send=transport.set_state
    def send(**kwargs):
        attempts.append(wall[0])
        if failed: raise RuntimeError("interrupted OFF")
        return original_send(**kwargs)
    monkeypatch.setattr(transport,"set_state",send)
    waits=[]; parent_checks=[]
    def wait(seconds): waits.append(seconds); advance(seconds)
    def checkpoint(safety_complete=False):
        if safety_complete:
            result=owned.wait_for_parent_deadline(parent,store=store,clock=lambda:wall[0],wait=wait,original_bound=1140)
            if result=="parent_due": parent_checks.append(wall[0]); return None
        return {"execution":parent,"original_bound":1140}
    with budget.cycle_budget(1140), owned.owned_deadline_checkpoint(checkpoint):
        result=managed._supervise_owned_devices(store=store,transport=transport,
            energy_reader=None,borehole_safety_reader=None,clock=lambda:wall[0],deadline_wait=wait)
        # The same canonical failed duty cannot cause another wrapper wait.
        if failed:
            assert owned.wait_for_earlier_owned_deadline(parent,store=store,clock=lambda:wall[0],wait=wait,original_bound=1140) is None
    assert attempts==[NOW+timedelta(seconds=5)], str(result["outcomes"])
    assert waits==([5] if failed else [5,10])
    assert parent_checks==([] if failed else [NOW+timedelta(seconds=15)])
    assert ((base.active_borehole if kind=="borehole" else base.active_aux) is not None)==failed
    assert sum(row.get("hardware_commands",0) for row in result["outcomes"])==1


def test_unresolved_supervision_does_not_admit_wait(monkeypatch):
    from modules.telemetry import rootline_managed_devices_runtime as managed
    observed=[]
    monkeypatch.setattr(managed,"_supervise_owned_devices_unbounded",lambda **kw:{
        "auxiliary_inventory_proven":True,"borehole_inventory_proven":True,
        "outcomes":[{"success":True,"supervision_evidence_pending":True}]})
    with owned.owned_deadline_checkpoint(lambda **kw:observed.append(kw)):
        managed._supervise_owned_devices(store=None,transport=None,energy_reader=None,
            borehole_safety_reader=None,clock=lambda:NOW)
    assert observed[-1]=={"safety_complete":False}


@pytest.mark.parametrize("tied",[False,True])
def test_two_earlier_owned_deadlines_are_selected_once_in_order(monkeypatch,tied):
    wall,mono,advance=clocks(monkeypatch)
    parent={"execution_id":"parent","primary_stop_deadline":(NOW+timedelta(seconds=15)).isoformat()}
    mixer={"execution_id":"mixer","state":"Active","primary_stop_deadline":(NOW+timedelta(seconds=5)).isoformat()}
    borehole={"execution_id":"borehole","state":"Active","primary_stop_deadline":(NOW+timedelta(seconds=5 if tied else 10)).isoformat()}
    active_rows=[mixer,borehole]; waits=[]
    def store(action,payload):
        if action=="load_active":return parent
        if action=="load_active_auxiliaries":return [mixer] if mixer in active_rows else []
        if action=="load_active_borehole":return borehole if borehole in active_rows else None
    def wait(seconds):waits.append(seconds);advance(seconds)
    with budget.cycle_budget(1140),owned.owned_deadline_checkpoint(lambda **kw:None):
        for expected in ([borehole,mixer] if tied else [mixer,borehole]):
            duty=owned.wait_for_earlier_owned_deadline(parent,store=store,clock=lambda:wall[0],wait=wait,original_bound=1140)
            assert duty==expected
            # Until canonical completion, a second wait may not pass this obligation.
            assert owned.wait_for_earlier_owned_deadline(parent,store=store,clock=lambda:wall[0],wait=wait,original_bound=1140) is None
            active_rows.remove(expected)
        assert owned.wait_for_parent_deadline(parent,store=store,clock=lambda:wall[0],wait=wait,original_bound=1140)=="parent_due"
    assert waits==([5,10] if tied else [5,5,5])


def test_actual_family_reserve_uses_parent_notification_deadline(monkeypatch,reports):
    from modules.oom_sakkie import family_message_lifecycle as family
    from tests.test_rootline_notice47_delivery import Rail
    wall,mono,advance=clocks(monkeypatch); rail=Rail(mono); deadlines=[]; notices=[]
    execution={**active(due=False),"primary_stop_deadline":(NOW+timedelta(seconds=35)).isoformat()}
    def supervisor(**kwargs):
        return {"success":True,"status":"active_segment_owned","execution":execution,"hardware_commands":0}
    def delivery(*args,**kwargs):
        deadlines.append(kwargs["deadline_monotonic"])
        return family.deliver_family_result(*args,**kwargs,event_store=rail.store,
            sender=lambda *a,**kw:pytest.fail("35 seconds cannot admit existing 40-second family reserve"))
    def equipment(**kwargs):
        notices.append(kwargs["notify"]("Started",execution))
        return {"success":True,"status":"checked","telegram_sends":0}
    def unknown(*args): raise ValueError("inventory unavailable")
    gateway(ExecutionStore(None),Transport(),active_supervision_cycle=supervisor,
        supervision_clock=lambda:wall[0],parent_deadline_store=unknown,
        parent_deadline_wait=lambda _:pytest.fail("unknown inventory cannot wait"),
        managed_device_cycle=lambda **kw:{"success":True,"status":"no_eligible_managed_device_task","hardware_commands":0},
        equipment_notification_cycle=equipment,family_delivery=delivery)
    assert notices and all(value==1035 for value in deadlines)
    assert notices[0]["status"]=="family_message_cycle_deadline_deferred"
    assert not rail.rows and wall[0]==NOW
