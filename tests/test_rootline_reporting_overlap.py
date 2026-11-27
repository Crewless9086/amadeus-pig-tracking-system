"""Reporting decorations share the canonical bounded reader group, never authority."""
from copy import deepcopy
from datetime import timedelta
import threading
import time
import pytest
from modules.telemetry import rootline_specialist_result as specialist
from modules.telemetry import rootline_water_energy_plan as plan
from modules.telemetry import rootline_bounded_read_group as groups
from modules.telemetry import rootline_provider_availability as provider
from modules.telemetry import rootline_input_health as inputs
from tests.test_rootline_reporting_read_efficiency import NOW, wire_other_readers

@pytest.fixture
def wired(monkeypatch):
    wire_other_readers(monkeypatch)
    monkeypatch.setattr(plan,"_read_recent_irrigation_history",lambda *a,**kw:{"zones":{},"snapshot_cutoff":NOW.isoformat()})
    monkeypatch.setattr(plan,"_read_managed_device_evidence",lambda *a,**kw:{})
    monkeypatch.setattr(plan,"get_current_water_energy_plan",lambda *a,**kw:({},404))
    calls=[]
    def read(name,**kw):
        assert kw["now"]==NOW
        calls.append(name)
        return {"contract":name,"observed_at":(NOW+timedelta(seconds=1)).isoformat()}
    monkeypatch.setattr(provider,"read_provider_availability",lambda **kw:read("provider",**kw))
    monkeypatch.setattr(inputs,"read_input_health",lambda **kw:read("inputs",**kw))
    return calls

def load(sink=None,readers=None):
    kw={} if sink is None else {"_reporting_readers":readers or specialist._presentation_readers(now=NOW),"_reporting_results":sink}
    return plan.read_current_water_energy_evidence(now=NOW,evidence_cutoff=NOW,forecast_mode="live_only",**kw)[0]

def test_real_loader_same_group_max_four_and_no_canonical_pollution(wired,monkeypatch):
    baseline=load(); actual=groups.run_bounded_read_group
    active=0;peak=0;lock=threading.Lock();groups_seen=[]
    def bounded(readers,**kw):
        nonlocal active,peak
        groups_seen.append((set(readers),kw["max_workers"]))
        def wrap(fn):
            def run():
                nonlocal active,peak
                with lock: active+=1;peak=max(peak,active)
                try:time.sleep(.02);return fn()
                finally:
                    with lock:active-=1
            return run
        return actual({name:wrap(fn) for name,fn in readers.items()},**kw)
    monkeypatch.setattr(groups,"run_bounded_read_group",bounded)
    sink={};result=load(sink)
    assert result==baseline and peak==4 and active==0
    assert len(groups_seen)==1 and groups_seen[0][1]==4
    assert set(sink)=={"presentation_provider_availability","presentation_input_health"}
    assert wired==["provider","inputs"] or wired==["inputs","provider"]
    assert specialist._reporting_evidence_error(result,NOW,NOW) is None
    assert "presentation" not in repr(result)
    decorated=specialist._with_provider_availability({"success":True},now=NOW,_read_results=sink)
    assert decorated["input_health"]["observed_at"]==(NOW+timedelta(seconds=1)).isoformat()
    assert len(wired)==2

@pytest.mark.parametrize("failed",["provider","inputs"])
def test_independent_unknown_fallback_without_aborting_evidence(wired,monkeypatch,failed):
    def fail(**kw):raise RuntimeError("synthetic read unavailable")
    monkeypatch.setattr(provider if failed=="provider" else inputs,
        "read_provider_availability" if failed=="provider" else "read_input_health",fail)
    sink={};load(sink)
    value=sink["presentation_provider_availability" if failed=="provider" else "presentation_input_health"]
    assert value==({"contract":provider.CONTRACT,"status":"unknown","scopes":[]} if failed=="provider" else
        {"contract":inputs.CONTRACT,"status":"unknown","inputs":{}})
    assert sink["presentation_input_health" if failed=="provider" else "presentation_provider_availability"]["contract"] in {"provider","inputs"}

def test_deadline_no_sink_completion_or_later_reuse(wired,monkeypatch):
    from modules.telemetry.rootline_cycle_budget import cycle_budget
    event=threading.Event();actual=specialist._presentation_readers(now=NOW)
    def blocked():event.wait(.2);return {"status":"late"}
    actual["presentation_input_health"]=blocked;sink={}
    try:
        with cycle_budget(time.monotonic()+.03),pytest.raises((groups.RootlineReadGroupDeadlineExceeded,TimeoutError)):
            load(sink,actual)
    finally:event.set()
    time.sleep(.03)
    assert sink=={}
    next_sink={};load(next_sink)
    assert next_sink["presentation_input_health"]["contract"]=="inputs"

def test_default_reader_and_direct_enrichment_stay_fresh(wired):
    load();assert wired==[]
    specialist._with_provider_availability({},now=NOW)
    specialist._with_provider_availability({},now=NOW)
    assert wired==["provider","inputs","provider","inputs"]

def test_refresh_keeps_later_fresh_programme_and_sidecar_outside_revision(wired,monkeypatch):
    events=[]
    def ensure(*a,**kw):
        assert len(wired)==2
        events.append("fresh programme")
        return {"success":True,"generation":8,"daily_program":{"creation_cutoff":NOW.isoformat()}},200
    def revise(saved,evidence,**kw):
        assert saved["generation"]==8 and "presentation" not in repr(evidence)
        events.append("revision")
        return saved,200
    monkeypatch.setattr(plan,"ensure_saved_daily_program",ensure)
    monkeypatch.setattr(plan,"revise_program_remainder",revise)
    monkeypatch.setattr(specialist,"project_water_energy_plan",lambda packet,**kw:{"success":True,"generation":packet["generation"]})
    result=specialist.refresh_current_rootline_specialist_result(now=NOW,evidence_cutoff=NOW)
    assert events==["fresh programme","revision"] and len(wired)==2
    assert result["generation"]==8 and result["provider_availability"]["contract"]=="provider"

@pytest.mark.parametrize("override",[{"purpose":"managed"},{"evidence_cutoff":None},{"forecast_mode":"current"}])
def test_private_sidecar_refuses_nonreporting_scope(wired,override):
    kw=dict(now=NOW,evidence_cutoff=NOW,forecast_mode="live_only",_reporting_results={},
        _reporting_readers=specialist._presentation_readers(now=NOW));kw.update(override)
    with pytest.raises(ValueError,match="reporting_presentation_scope_invalid"):
        plan.read_current_water_energy_evidence(**kw)
    assert wired==[]


def test_actual_group_overlaps_both_presentations_with_canonical_reader(wired,monkeypatch,record_property):
    saved_started=threading.Event();provider_started=threading.Event();input_started=threading.Event()
    finished=[];lock=threading.Lock()
    def finished_reader(name):
        with lock:finished.append(name)
    def saved(*a,**kw):
        saved_started.set()
        assert provider_started.wait(3), "provider must start before canonical reader completes"
        assert input_started.wait(3), "input must start before canonical reader completes"
        finished_reader("canonical")
        return {},404
    def provider_read(**kw):
        provider_started.set()
        assert saved_started.wait(3)
        assert input_started.wait(3), "both decorations must overlap in the existing group"
        finished_reader("provider")
        return {"status":"observed"}
    def input_read(**kw):
        input_started.set()
        assert saved_started.wait(3)
        assert provider_started.wait(3)
        finished_reader("inputs")
        return {"status":"observed"}
    monkeypatch.setattr(plan,"get_current_water_energy_plan",saved)
    monkeypatch.setattr(provider,"read_provider_availability",provider_read)
    monkeypatch.setattr(inputs,"read_input_health",input_read)
    sink={};load(sink)
    assert sorted(finished)==["canonical","inputs","provider"]
    assert sink["presentation_provider_availability"]["status"]=="observed"
    assert sink["presentation_input_health"]["status"]=="observed"
    # Preserve measured local acquisition/query inputs as information only;
    # thread scheduling and Render latency cannot be qualified by a sleep delta.
    record_property("local_provider_acquisition_and_queries_seconds",1.860+.219+.235+.219)
    record_property("local_input_acquisition_and_queries_seconds",1.547+.375+.203)
