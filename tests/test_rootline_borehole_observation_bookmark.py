"""Actual three-pass coordinator retains observation only after fresh guards."""
from copy import deepcopy
from datetime import timedelta
import pytest
from modules.telemetry import rootline_managed_devices_runtime as managed
from modules.telemetry.rootline_stage_timings import StageTimings
from tests.test_rootline_borehole_external_off import Store as CommandStore, Transport, active, reported
from tests.test_rootline_command_mode import NOW, receipt

class Store(CommandStore):
    def __init__(self):
        super().__init__();self.owner_stop=None;self.inventory_reads=0;self.owner_reads=0;self.fail_owner_at=set();self.owner_failure_hook=None
    def __call__(self,action,body):
        if action=="load_active_auxiliaries":self.inventory_reads+=1;return []
        if action=="load_owner_control_stop":
            self.owner_reads+=1
            if self.owner_reads in self.fail_owner_at:
                if self.owner_failure_hook:self.owner_failure_hook()
                raise managed.RootlineExecutionStoreUnavailable("owner read unavailable")
            return self.owner_stop
        return super().__call__(action,body)

class ObservedTransport(Transport):
    def __init__(self,store):super().__init__(store,reported(state="ON"));self.reads=0
    def read_output_state(self,**kw):self.reads+=1;return super().read_output_state(**kw)

class Case:
    def __init__(self):
        self.store=Store();self.transport=ObservedTransport(self.store);self.timings=StageTimings()
        self.energy_reads=0;self.protection_reads=0;self.condition_reads=0
        self.now=NOW;self.energy_pending=False;self.condition_pending=False;self.protection_pending=False
    def run(self,mutation=None):
        def energy():
            self.energy_reads+=1
            return {"continuous_borehole_fresh":not self.energy_pending,"continuous_borehole_eligible":True,"borehole_fresh":not self.energy_pending,"borehole_eligible":True}
        def protection():
            self.protection_reads+=1
            return {"safe":None if self.protection_pending else True}
        def conditions(**kw):
            self.condition_reads+=1
            return {"success":not self.condition_pending,"stop_required":False}
        def evidence(**kw):
            if mutation:mutation()
            return {"irrigation_auxiliary_tasks":[]}
        return managed.run_rootline_managed_device_cycle(evidence={},store=self.store,transport=self.transport,
            environ={"ROOTLINE_FERTILIZER_MIXING_ENABLED":"true"},canonical_loader=lambda key:None,
            now=self.now,clock=lambda:self.now,energy_reader=energy,borehole_safety_reader=protection,
            borehole_conditions_reader=conditions,after_safety=lambda result:None,
            evidence_factory=evidence,allow_borehole_starts=False,stage_timings=self.timings)

def test_three_passes_one_observation_but_all_checks_fresh_and_next_tick_fresh():
    c=Case();result=c.run()
    assert c.transport.reads==1 and c.transport.commands==[]
    assert c.store.inventory_reads==c.store.owner_reads==c.energy_reads==c.protection_reads==c.condition_reads==3
    rows=c.timings.snapshot()["stages"]
    assert rows["managed_borehole_advance"]["calls"]==1
    assert rows["managed_borehole_observation"]["calls"]==1
    assert rows["managed_owned_inventory"]["calls"]==6
    for name in ("energy","protection","owner_stop","conditions"):
        assert rows["managed_borehole_"+name]["calls"]==3
    c.run();assert c.transport.reads==2
    assert result["hardware_commands"]==0

@pytest.mark.parametrize("change",["owner_stop","execution","deadline","conditions","energy","protection"])
def test_third_pass_does_not_reuse_after_new_stop_change_or_uncertainty(change):
    c=Case()
    def mutate():
        if change=="owner_stop":
            c.store.owner_stop={"request_id":"owner-stop","change":{"kind":"stop","changes":{"execution_id":c.store.active["execution_id"]}}}
        elif change=="execution":
            c.store.active["execution_id"]="ROOTLINE-BOREHOLE-REPLACEMENT"
            c.store.active["command_on_receipt"]=receipt(c.store.active,"ON",at=NOW-timedelta(hours=10))
        elif change=="deadline":
            c.store.active.update(stop_mode="timed",primary_stop_deadline=(NOW-timedelta(seconds=1)).isoformat())
        elif change=="conditions":c.condition_pending=True
        elif change=="energy":c.energy_pending=True
        else:c.protection_pending=True
    result=c.run(mutate)
    assert c.timings.snapshot()["stages"]["managed_borehole_advance"]["calls"]==2
    if change in {"owner_stop","deadline"}:
        assert [row["state"] for row in c.transport.commands]==["OFF"]
    else:
        assert c.transport.reads==2 and c.transport.commands==[]
    assert all(row["state"]!="ON" for row in c.transport.commands)
    assert c.store.owner_reads==3

def test_failed_inventory_keeps_its_error_and_timing(monkeypatch):
    c=Case();original=c.store
    def broken(action,payload):
        if action=="load_active_borehole":raise managed.RootlineExecutionStoreUnavailable("synthetic unavailable")
        return original(action,payload)
    result=managed.run_rootline_managed_device_cycle(evidence={},store=broken,transport=c.transport,
        now=NOW,clock=lambda:NOW,allow_new_starts=False,allow_borehole_starts=False,
        stage_timings=c.timings)
    assert c.timings.snapshot()["stages"]["managed_owned_inventory"]["calls"]==2
    assert result["status"]=="borehole_inventory_unproven" and result["success"] is False
    assert c.transport.commands==[]


@pytest.mark.parametrize("failed_pass",[1,2,3])
def test_owner_lookup_failure_never_qualifies_bookmark_and_next_tick_recovers(failed_pass):
    c=Case();c.store.fail_owner_at={failed_pass}
    result=c.run()
    assert c.store.owner_reads==3  # exactly one lookup per pass, even on error
    assert c.transport.reads==(2 if failed_pass in {1,3} else 3)
    outcomes=result.get("outcomes",[result])
    assert any(row.get("supervision_evidence_pending") is True for row in outcomes)
    assert c.transport.commands==[]
    old=c.transport.reads;c.run()
    assert c.transport.reads==old+1 and c.store.owner_reads==6


def test_owner_failure_crossing_deadline_still_performs_owned_off():
    c=Case()
    c.store.active.update(stop_mode="timed",primary_stop_deadline=(NOW+timedelta(seconds=5)).isoformat())
    c.store.fail_owner_at={2}
    c.store.owner_failure_hook=lambda:setattr(c,"now",NOW+timedelta(seconds=6))
    c.run()
    assert [row["state"] for row in c.transport.commands]==["OFF"]
    assert c.store.active is None
