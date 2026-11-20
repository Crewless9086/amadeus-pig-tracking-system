"""Offline existing-rail tests; no provider, database or equipment access."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from threading import Lock,Barrier
from concurrent.futures import ThreadPoolExecutor
import time
import pytest
from modules.telemetry import rootline_managed_devices_runtime as managed
from modules.telemetry import rootline_irrigation_coordinator as coordinator
from modules.telemetry.rootline_cycle_budget import cycle_budget

BASE=datetime(2026,11,20,tzinfo=timezone.utc)
IDENTITY='FERTILIZER-INJECTION-CH1'

class Rig:
    def __init__(self, *, phase=0, read_seconds=2, command_seconds=0):
        self.now=BASE+timedelta(seconds=60)
        self.claimed=BASE+timedelta(seconds=phase)
        self.deadline=self.claimed+timedelta(seconds=120)
        self.active=dict(execution_id='INJECTOR',auxiliary_device_id=IDENTITY,
            device_id='100204d497',channel=1,device_type='fertilizer_injection_valve',
            stop_mode='scheduled',state='Active',on_attempts=1,
            maximum_duration_seconds=120,claimed_at=self.claimed.isoformat(),
            primary_stop_deadline=self.deadline.isoformat(),
            start_evidence=self.proof('ON',self.claimed+timedelta(seconds=2)))
        self.original=deepcopy(self.active)
        self.borehole=None
        self.other=[];self.records=[];self.attempts=set();self.commands=[]
        self.lock=Lock();self.lock_held=False;self.waits=[];self.parent_reads=0
        self.read_count=0
        self.read_seconds=read_seconds;self.command_seconds=command_seconds
        self.parent=dict(execution_id='PARENT',primary_stop_deadline=(BASE+timedelta(hours=2)).isoformat())
    def proof(self,state,at):
        return dict(authoritative=True,state=state,device_id='100204d497',channel=1,retrieved_at=at.isoformat())
    def clock(self):return self.now
    def advance(self,seconds):self.now+=timedelta(seconds=seconds)
    def wait(self,seconds):
        assert not self.lock_held
        self.waits.append(seconds);self.advance(seconds)
    def store(self,action,payload):
        with self.lock:
            self.lock_held=True
            try:
                if action=='load_active_auxiliary':return deepcopy(self.active)
                if action=='load_active_auxiliaries':return deepcopy(([self.active] if self.active else [])+self.other)
                if action=='load_active':return deepcopy(self.parent)
                if action=='load_active_borehole':return deepcopy(self.borehole)
                if action=='load_auxiliary_physical_outcome':return None
                if action=='load_auxiliary_off_attempts':return [{'attempt':p['attempt']} for a,p in self.records if a=='record_auxiliary_off_outcome']
                if action=='dispatch_auxiliary_off_edge':
                    if payload['attempt'] in self.attempts:
                        return {'accepted_unambiguous':False,'provider_command_attempted':False}
                    self.attempts.add(payload['attempt'])
                    outcome=payload['dispatch']()
                    slot={key:payload[key] for key in ('execution_id','attempt')}
                    self.records.append(('record_auxiliary_off_outcome',{**slot,'outcome':outcome}))
                    return {**outcome,'provider_command_attempted':True}
                if action=='claim_auxiliary_off_attempt':
                    created=payload['attempt'] not in self.attempts
                    self.attempts.add(payload['attempt']);return {'success':True,'created':created}
                self.records.append((action,deepcopy(payload)))
                if action in ('record_auxiliary_completed','record_auxiliary_control_pulse_stopped') or (action=='contain_auxiliary_device' and payload.get('shutdown_verified') is True):
                    self.active=None
                return {'success':True,'created':True}
            finally:self.lock_held=False
    def set_state(self,**kwargs):
        assert kwargs['state']=='OFF' and kwargs['channel']==1
        self.commands.append((self.now,kwargs));self.advance(self.command_seconds)
        return {'accepted_unambiguous':True}
    def read_output_state(self,**kwargs):
        self.read_count+=1
        self.advance(self.read_seconds);return self.proof('OFF',self.now)
    def finish(self,**kwargs):
        return managed._finish_injector_deadline(store=self.store,transport=self,
            clock=self.clock,wait=self.wait,horizon_seconds=120,**kwargs)
    def terminal(self):
        return next(p for a,p in self.records if a in ('record_auxiliary_completed','record_auxiliary_control_pulse_stopped'))

@pytest.mark.parametrize('phase',range(60))
@pytest.mark.parametrize('parent_cost',[0,1,2,5,15])
def test_all_minute_phases_stop_without_incidental_reads(monkeypatch,phase,parent_cost):
    rig=Rig(phase=phase)
    def parent(*args,**kwargs):rig.parent_reads+=1;rig.advance(parent_cost);return True
    monkeypatch.setattr(coordinator,'_injection_parent_still_on',parent)
    result=rig.finish(verify_parent=True)
    assert result['status']=='auxiliary_injection_control_completed'
    assert rig.commands[0][0]==rig.deadline
    assert rig.terminal()['observed_control_seconds']==120
    assert rig.terminal()['primary_stop_deadline']==rig.original['primary_stop_deadline']
    assert rig.parent_reads==1 and len(rig.waits)==1

@pytest.mark.parametrize('command_delay,proof_delay',[(0,3),(15,2),(30,30)])
def test_delayed_off_or_proof_never_gets_full_pulse_credit(command_delay,proof_delay):
    rig=Rig(read_seconds=proof_delay,command_seconds=command_delay)
    result=rig.finish()
    assert result['status']=='auxiliary_control_pulse_off_verified'
    row=rig.terminal()
    assert row['control_completed'] is False and row['fertilizer_debt'] is True
    assert row['control_stop_reason']=='injection_duration_exceeded'
    assert not any(a=='record_auxiliary_completed' for a,p in rig.records)

def test_expired_worker_budget_stops_early_without_wait_or_parent_probe(monkeypatch):
    rig=Rig()
    monkeypatch.setattr(coordinator,'_injection_parent_still_on',lambda *a,**kw:pytest.fail('unnecessary probe'))
    with cycle_budget(time.monotonic()-1):result=rig.finish(verify_parent=True)
    assert not rig.waits and rig.commands[0][0]<rig.deadline
    assert result['status']=='auxiliary_control_pulse_off_verified'
    assert rig.terminal()['control_stop_reason']=='injector_early_stop_worker_budget'
    assert rig.terminal()['control_completed'] is False

def test_another_owned_deadline_is_not_delayed_by_wait():
    rig=Rig()
    rig.other=[dict(execution_id='MIXER',primary_stop_deadline=(rig.now+timedelta(seconds=5)).isoformat())]
    rig.finish()
    assert not rig.waits and rig.commands[0][0]<rig.deadline
    assert rig.terminal()['control_stop_reason']=='injector_early_stop_other_owned_deadline'

@pytest.mark.parametrize('kind',['identity','deadline','terminal'])
def test_reload_after_wait_does_not_operate_replaced_execution(kind):
    rig=Rig()
    def wait(seconds):
        rig.advance(seconds)
        if kind=='identity':rig.active['execution_id']='REPLACEMENT'
        elif kind=='deadline':rig.active['primary_stop_deadline']=(rig.deadline+timedelta(minutes=1)).isoformat()
        else:rig.active=None
    rig.wait=wait
    result=rig.finish()
    assert not rig.commands
    assert result['status'] in ('auxiliary_recovery_identity_changed','auxiliary_recovery_already_terminal')

def test_restart_after_deadline_is_immediate_and_honestly_late():
    rig=Rig();rig.now=rig.deadline+timedelta(seconds=49)
    result=rig.finish()
    assert not rig.waits and result['status']=='auxiliary_control_pulse_off_verified'
    assert rig.terminal()['stop_deadline_lateness_seconds']==49

def test_clock_reversal_never_rewaits_or_claims_complete():
    rig=Rig()
    def wait(seconds):rig.waits.append(seconds);rig.now-=timedelta(seconds=1)
    rig.wait=wait;result=rig.finish()
    assert len(rig.waits)==1 and len(rig.commands)==1
    assert result['status']=='auxiliary_control_pulse_off_verified'
    assert rig.terminal()['control_stop_reason']=='injector_deadline_clock_unproven'

def test_slow_broader_supervisor_cannot_delay_existing_injector(monkeypatch):
    rig=Rig()
    rig.borehole=dict(execution_id='BOREHOLE',primary_stop_deadline=(BASE+timedelta(hours=4)).isoformat())
    monkeypatch.setattr(coordinator,'_injection_parent_still_on',lambda *a,**kw:True)
    def slow_energy():
        assert rig.active is None and rig.commands[0][0]==rig.deadline
        rig.advance(130)
        return {'fresh':True,'borehole_eligible':True}
    monkeypatch.setattr(managed,'advance_borehole_execution',lambda **kw:{'success':True,'status':'borehole_active'})
    managed.run_rootline_managed_device_cycle(evidence={},transport=rig,store=rig.store,
        clock=rig.clock,deadline_wait=rig.wait,environ={'ROOTLINE_TIMED_CONTROL_ENABLED':'true'},
        energy_reader=slow_energy,allow_new_starts=False,allow_borehole_starts=False)
    assert rig.terminal()['observed_control_seconds']==120


def test_duplicate_waiters_use_existing_bounded_off_attempt_keys():
    rig=Rig();barrier=Barrier(2)
    def wait(seconds):
        assert not rig.lock_held
        barrier.wait(timeout=3)
        rig.now=rig.deadline
    rig.wait=wait
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:rig.finish(),range(2)))
    keys=[kw['idempotency_key'] for _,kw in rig.commands]
    assert len(keys)==len(set(keys)) and 1<=len(keys)<=3
    assert all(kw['state']=='OFF' for _,kw in rig.commands)
    assert all(row['primary_stop_deadline']==rig.original['primary_stop_deadline']
        for action,row in rig.records if action.startswith('record_auxiliary_') and 'primary_stop_deadline' in row)

def test_missing_off_proof_keeps_containment(monkeypatch):
    rig=Rig();monkeypatch.setattr(rig,'read_output_state',lambda **kw:{'authoritative':False,'state':'Unknown'})
    result=rig.finish()
    assert result['status']=='auxiliary_shutdown_intervention_required'
    assert any(a=='contain_auxiliary_device' for a,p in rig.records)
    assert not any(a=='record_auxiliary_completed' for a,p in rig.records)

def test_expired_budget_is_preserved_inside_mandatory_inventory(monkeypatch):
    rig=Rig()
    monkeypatch.setattr(coordinator,'_injection_parent_still_on',lambda *a,**kw:pytest.fail('unnecessary probe'))
    with cycle_budget(time.monotonic()-1):
        managed.run_rootline_managed_device_cycle(evidence={},transport=rig,store=rig.store,
            clock=rig.clock,deadline_wait=rig.wait,environ={'ROOTLINE_TIMED_CONTROL_ENABLED':'true'},
            allow_new_starts=False,allow_borehole_starts=False)
    assert not rig.waits and rig.terminal()['control_stop_reason']=='injector_early_stop_worker_budget'

def test_parent_dependency_loss_stops_without_wait(monkeypatch):
    rig=Rig()
    monkeypatch.setattr(coordinator,'_injection_parent_still_on',lambda *a,**kw:False)
    result=rig.finish(verify_parent=True)
    assert not rig.waits and result['status']=='auxiliary_emergency_off_verified'
    assert not any(a=='record_auxiliary_completed' for a,p in rig.records)

def test_slow_parent_proof_crossing_deadline_is_not_full_credit(monkeypatch):
    rig=Rig()
    def parent(*args,**kwargs):rig.advance(70);return True
    monkeypatch.setattr(coordinator,'_injection_parent_still_on',parent)
    result=rig.finish(verify_parent=True)
    assert not rig.waits and result['status']=='auxiliary_control_pulse_off_verified'
    assert rig.terminal()['observed_control_seconds']>120

def test_earlier_mixer_deadline_avoids_unnecessary_parent_read(monkeypatch):
    rig=Rig();rig.other=[dict(execution_id='MIXER',primary_stop_deadline=(rig.now+timedelta(seconds=1)).isoformat())]
    monkeypatch.setattr(coordinator,'_injection_parent_still_on',lambda *a,**kw:pytest.fail('must stop first'))
    rig.finish(verify_parent=True)
    assert not rig.waits and rig.terminal()['control_stop_reason']=='injector_early_stop_other_owned_deadline'

def test_missing_start_evidence_cannot_get_pulse_credit():
    rig=Rig();rig.active['start_evidence']['authoritative']=False
    result=rig.finish()
    assert result['status']=='auxiliary_control_pulse_off_verified'
    assert rig.terminal()['observed_control_seconds'] is None


def test_malformed_deadline_keeps_existing_safety_off_recovery():
    rig=Rig();rig.active['primary_stop_deadline']='invalid'
    managed.run_rootline_managed_device_cycle(evidence={},transport=rig,store=rig.store,
        clock=rig.clock,deadline_wait=rig.wait,environ={'ROOTLINE_TIMED_CONTROL_ENABLED':'true'},
        allow_new_starts=False,allow_borehole_starts=False)
    assert not rig.waits and len(rig.commands)==1
    assert any(a=='contain_auxiliary_device' and p['reason']=='restart_or_deadline_ambiguous' for a,p in rig.records)


def test_unproven_off_not_repeated_in_same_supervisor_pass(monkeypatch):
    rig=Rig();rig.now=rig.deadline
    def unknown(**kwargs):
        rig.read_count+=1
        return {'authoritative':False,'state':'Unknown'}
    monkeypatch.setattr(rig,'read_output_state',unknown)
    managed.run_rootline_managed_device_cycle(evidence={},transport=rig,store=rig.store,
        clock=rig.clock,deadline_wait=rig.wait,environ={'ROOTLINE_TIMED_CONTROL_ENABLED':'true'},
        allow_new_starts=False,allow_borehole_starts=False,after_safety=lambda _:None)
    assert len(rig.commands)==1 and rig.read_count==1
    assert rig.active is not None


@pytest.mark.parametrize("remaining", [61, 90, 111, 119, 120])
def test_new_injector_owns_full_remaining_window_in_starting_worker(monkeypatch, remaining):
    rig = Rig()
    rig.now = rig.deadline-timedelta(seconds=remaining)
    monkeypatch.setattr(managed, "_run_rootline_managed_device_cycle",
        lambda **_: {"status": "auxiliary_started", "success": True,
            "execution": deepcopy(rig.active), "hardware_commands": 1})
    result = managed.run_rootline_managed_device_cycle(evidence={}, transport=rig,
        store=rig.store, clock=rig.clock, deadline_wait=rig.wait)
    assert rig.commands[0][0] == rig.deadline
    assert rig.active is None and len(rig.waits) == 1
    assert rig.terminal()["control_completed"] is True
    assert rig.terminal()["observed_control_seconds"] == 120
    assert result["hardware_commands"] == 2


@pytest.mark.parametrize("budget_left", [1, 50, 111])
def test_new_injector_without_full_wait_budget_stops_partial_now(monkeypatch, budget_left):
    rig = Rig(); rig.now = rig.claimed+timedelta(seconds=9)
    monkeypatch.setattr(managed, "_run_rootline_managed_device_cycle",
        lambda **_: {"status": "auxiliary_started", "success": True,
            "execution": deepcopy(rig.active), "hardware_commands": 1})
    with cycle_budget(time.monotonic()+budget_left):
        managed.run_rootline_managed_device_cycle(evidence={}, transport=rig,
            store=rig.store, clock=rig.clock, deadline_wait=rig.wait)
    assert not rig.waits and rig.commands[0][0] < rig.deadline
    assert rig.active is None
    assert rig.terminal()["control_stop_reason"] == "injector_early_stop_worker_budget"
    assert rig.terminal()["control_completed"] is False
    assert rig.terminal()["fertilizer_debt"] is True


def test_clock_reversal_before_new_injector_epilogue_cannot_escape_stop(monkeypatch):
    rig = Rig(); rig.now = rig.claimed-timedelta(seconds=1)
    monkeypatch.setattr(managed, "_run_rootline_managed_device_cycle",
        lambda **_: {"status": "auxiliary_started", "success": True,
            "execution": deepcopy(rig.active), "hardware_commands": 1})
    managed.run_rootline_managed_device_cycle(evidence={}, transport=rig,
        store=rig.store, clock=rig.clock, deadline_wait=rig.wait)
    assert not rig.waits and len(rig.commands) == 1
    assert rig.terminal()["control_stop_reason"] == "injector_deadline_clock_unproven"
    assert rig.terminal()["control_completed"] is False


def test_new_injector_reaches_off_before_any_later_optional_start(monkeypatch):
    from tests.test_rootline_managed_devices_runtime import canonical
    rig = Rig(); new = deepcopy(rig.active); rig.active = None
    rig.now = rig.claimed+timedelta(seconds=9)
    original = managed.advance_auxiliary_execution
    def advance(**kwargs):
        if not kwargs["eligibility"]:
            return original(**kwargs)
        assert kwargs["auxiliary_device_id"] == IDENTITY, "optional work ran after injector ON"
        rig.active = deepcopy(new)
        return {"status": "auxiliary_started", "success": True,
            "execution": deepcopy(new), "hardware_commands": 1}
    monkeypatch.setattr(managed, "advance_auxiliary_execution", advance)
    monkeypatch.setattr(managed, "advance_borehole_execution",
        lambda **_: pytest.fail("optional borehole start after injector ON"))
    monkeypatch.setattr(managed, "canonical_timed_authority", lambda *a, **kw: True)
    monkeypatch.setattr(managed, "build_auxiliary_eligibility", lambda **kw:
        {"eligible": True, "stop_mode": "scheduled", "maximum_duration_seconds": 120})
    tasks = [{"auxiliary_device_id": identity, "device_type": kind, "decision": "Run now"}
        for identity, kind in [(IDENTITY, "fertilizer_injection_valve"),
            ("FERTILIZER-MIXER-CH2", "fertilizer_mixer")]]
    result = managed.run_rootline_managed_device_cycle(evidence={
        "irrigation_auxiliary_tasks": tasks, "borehole_execution": {"eligible": True}},
        transport=rig, store=rig.store, clock=rig.clock, deadline_wait=rig.wait,
        canonical_loader=canonical, connect_factory=lambda: object(),
        environ={"ROOTLINE_TIMED_CONTROL_ENABLED": "true",
            "ROOTLINE_FERTILIZER_INJECTION_ENABLED": "true",
            "ROOTLINE_FERTILIZER_MIXING_ENABLED": "true", "ROOTLINE_BOREHOLE_ENABLED": "true"})
    assert rig.active is None and rig.commands[0][0] == rig.deadline
    assert rig.terminal()["control_completed"] is True
    assert result["hardware_commands"] == 2


@pytest.mark.parametrize("start_elapsed,complete", [(0, True), (10, True),
    (20, False), (35, False), (125, False)])
def test_new_injector_respects_original_140_second_cycle(monkeypatch, start_elapsed, complete):
    from types import SimpleNamespace
    from modules.telemetry import rootline_cycle_budget as cycle
    rig = Rig(); rig.now = BASE
    monotonic_clock = lambda: (rig.now-BASE).total_seconds()
    monkeypatch.setattr(cycle, "time", SimpleNamespace(monotonic=monotonic_clock))
    monkeypatch.setattr(managed, "monotonic", monotonic_clock)
    def newly_started(**kwargs):
        rig.advance(start_elapsed)
        rig.claimed = rig.now; rig.deadline = rig.claimed+timedelta(seconds=120)
        rig.active.update(claimed_at=rig.claimed.isoformat(),
            primary_stop_deadline=rig.deadline.isoformat(),
            start_evidence=rig.proof("ON", rig.claimed+timedelta(seconds=2)))
        # Admission, ON, readback and persistence have used nine seconds.
        rig.advance(9)
        return {"status": "auxiliary_started", "success": True,
            "execution": deepcopy(rig.active), "hardware_commands": 1}
    monkeypatch.setattr(managed, "_run_rootline_managed_device_cycle", newly_started)
    with cycle.cycle_budget() as bound:
        assert bound == 140
        managed.run_rootline_managed_device_cycle(evidence={}, transport=rig,
            store=rig.store, clock=rig.clock, deadline_wait=rig.wait)
        assert cycle.on_deadline() == 140  # No deadline extension during wait/OFF.
    row = rig.terminal()
    assert row["control_completed"] is complete and rig.active is None
    assert monotonic_clock() <= 140
    if complete:
        assert rig.waits == [111] and rig.commands[0][0] == rig.deadline
        assert row["observed_control_seconds"] == 120
    else:
        assert not rig.waits and rig.commands[0][0] < rig.deadline
        assert row["control_stop_reason"] == "injector_early_stop_worker_budget"
        assert row["fertilizer_debt"] is True
