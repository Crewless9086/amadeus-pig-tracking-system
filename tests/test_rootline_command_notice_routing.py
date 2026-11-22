"""Provider-specific reporting on existing delivery rails; no external I/O."""
from copy import deepcopy
from datetime import timedelta
import pytest
from modules.oom_sakkie.rootline_transition_notifications import (
    recover_provider_notifications, compose_provider_notice, provider_availability_text)
from modules.telemetry.rootline_command_acceptance import MODE
from modules.telemetry.rootline_device_registry import get_device_contract
from tests.test_rootline_command_mode import receipt, route
from tests.test_rootline_provider_outage_visibility import (
    Memory, FamilyRail, NOW, snapshot, event, QueueConnection, read_notification_receipt, CONTRACT,
    enable_reviewed_visibility_paths)

ENV={"ROOTLINE_INPUT_HEALTH_ENABLED":"true","ROOTLINE_SONOFF_TRANSPORT":"home_assistant",
    "ROOTLINE_HOME_ASSISTANT_ACCEPTANCE_MODE":MODE}


def duty(identity="E12345", *, adopted=False):
    c=get_device_contract(identity);at=NOW-timedelta(minutes=10)
    row={"execution_id":"DUTY-"+identity,"event_id":"EVENT-"+identity,"device_id":c["device_id"],
        "channel":c["channel"],"acceptance_mode":MODE,"state":"Active","on_attempts":1,
        "claimed_at":at.isoformat(),"primary_stop_deadline":(NOW+timedelta(hours=1)).isoformat(),
        "stop_mode":"scheduled","action":"mark_active","zone_id":identity}
    if identity.startswith("FERTILIZER"):
        row.pop("zone_id");row.update(auxiliary_device_id=identity,action="mark_auxiliary_active",
            device_type="fertilizer_mixer" if "MIXER" in identity else "fertilizer_injection_valve",
            maximum_duration_seconds=600)
    elif identity.startswith("BOREHOLE"):
        row.pop("zone_id");row.update(action="mark_borehole_active",stop_mode="conditions",
            primary_stop_deadline=None,device_type="borehole_pump")
    row["command_on_receipt"]=receipt(row,"ON",at=at)
    if adopted:
        row.update(execution_origin="ha_reported_external_on",on_attempts=0,command_on_receipt=None,
            original_start_at=None,provider_start_evidence=None,
            command_adoption_evidence=route("1002851416",now=at,reported="ON"))
    return row


class CommandMemory(Memory):
    def __init__(self,rows=()):
        super().__init__();self.rows=list(rows);self.off={}
    def store(self,action,payload):
        if action=="load_active":return next((deepcopy(x) for x in self.rows if x.get("zone_id")),None)
        if action=="load_active_borehole":return next((deepcopy(x) for x in self.rows if x["device_id"]=="1002851416"),None)
        if action=="load_active_auxiliaries":return [deepcopy(x) for x in self.rows if x.get("auxiliary_device_id")]
        if action in {"load_off_attempts","load_auxiliary_off_attempts","load_borehole_off_attempts"}:
            return deepcopy(self.off.get(payload,[]))
        return super().store(action,payload)
    def run(self,current=None,*,now=NOW,notify=None,loader=None):
        return recover_provider_notifications(notify=notify or self.notify,now=now,environ=ENV,
            store=self.store,receipt_loader=self.receipt,loader=loader or (lambda **_:deepcopy(current or snapshot())),clock=lambda:now)


@pytest.mark.parametrize("identity",["A12345","B12345","C12345","E12345","FERTILIZER-MIXER-CH2","FERTILIZER-INJECTION-CH1","BOREHOLE-1-MINI-R4-CH1"])
def test_healthy_command_duties_do_not_inherit_ewelink_outage(identity):
    memory=CommandMemory([duty(identity)]);before=deepcopy(memory.rows)
    assert memory.run()["notification_count"]==1
    assert [x[0] for x in memory.calls]==["ProviderUnavailable"]
    text=compose_provider_notice(*memory.calls[0][:2])
    assert "separate switch readback is not required" in text and "Check the local situation" not in text
    assert memory.run()["telegram_sends"]==0 and memory.rows==before


def test_owner_started_borehole_adoption_is_silent_and_legacy_duty_still_alerts():
    legacy={"execution_id":"LEGACY","zone_id":"B12345","state":"Active"}
    memory=CommandMemory([duty("BOREHOLE-1-MINI-R4-CH1",adopted=True),legacy])
    memory.run()
    safety=[p for state,p,_ in memory.calls if state=="ProviderSafety"]
    assert len(safety)==1 and safety[0]["duty_id"]=="LEGACY"
    assert "Check the local situation" in compose_provider_notice("ProviderSafety",safety[0])


@pytest.mark.parametrize("identity",["FERTILIZER-MIXER-CH2","FERTILIZER-INJECTION-CH1","BOREHOLE-1-MINI-R4-CH1"])
@pytest.mark.parametrize("legacy_status",["unavailable","restored","unobserved"])
def test_actual_failed_off_is_reported_once_independent_of_legacy_outage(identity,legacy_status):
    row=duty(identity);memory=CommandMemory([row])
    memory.off[row["execution_id"]]=[{"execution_id":row["execution_id"],"event_id":"FAILED-OFF",
        "outcome":{"accepted_unambiguous":False,"provider_command_attempted":True}}]
    current=snapshot() if legacy_status=="unavailable" else {"contract":CONTRACT,"status":legacy_status,"scopes":[]}
    memory.run(current)
    safety=[p for state,p,_ in memory.calls if state=="ProviderSafety"]
    assert len(safety)==1 and safety[0]["provider"]=="home_assistant"
    assert safety[0]["severity"]=="off_command_unaccepted"
    assert safety[0]["incident_id"]!=snapshot()["scopes"][0]["incident_id"]
    text=compose_provider_notice("ProviderSafety",safety[0]);assert "OFF-command duty remains open" in text
    assert "Check the local situation" not in text and "valid readback" not in text
    assert memory.run(current)["telegram_sends"]==0
    connection=QueueConnection([[]])
    assert read_notification_receipt(safety[0]["notification_identity"],connect=lambda **_:connection,environ=ENV)=={}


def test_command_failure_survives_legacy_ledger_read_failure():
    row=duty("FERTILIZER-MIXER-CH2");row["primary_stop_deadline"]=(NOW-timedelta(seconds=1)).isoformat();memory=CommandMemory([row])
    def offline(**kwargs):raise RuntimeError("legacy ledger unavailable")
    result=memory.run(loader=offline)
    assert result["success"] is False and len(memory.calls)==1
    assert memory.calls[0][1]["provider"]=="home_assistant"


def test_accepted_off_waiting_for_terminal_write_never_raises_physical_feedback_alarm():
    row=duty("FERTILIZER-MIXER-CH2");row["primary_stop_deadline"]=(NOW-timedelta(seconds=1)).isoformat()
    memory=CommandMemory([row]);memory.off[row["execution_id"]]=[{"execution_id":row["execution_id"],
        "outcome":receipt(row,"OFF",at=NOW-timedelta(seconds=1))}]
    memory.run();assert [x[0] for x in memory.calls]==["ProviderUnavailable"]
    assert row.get("shutdown_verified") is not True


def test_pending_on_uncertainty_and_later_off_deadline_escalate_once():
    row=duty("FERTILIZER-MIXER-CH2");row.update(state="claimed_recovery_required",command_on_receipt=None,on_attempts=0)
    memory=CommandMemory([row]);memory.run()
    assert memory.calls[-1][1]["severity"]=="command_outcome_unconfirmed"
    assert memory.run()["telegram_sends"]==0
    memory.rows[0]["primary_stop_deadline"]=(NOW-timedelta(seconds=1)).isoformat()
    assert memory.run()["notification_count"]==1
    assert memory.calls[-1][1]["severity"]=="off_command_unaccepted"


def test_command_attention_rechecks_actual_duty_before_sending():
    row=duty("FERTILIZER-MIXER-CH2");row["primary_stop_deadline"]=(NOW-timedelta(seconds=1)).isoformat()
    memory=CommandMemory([row]);original=memory.store;reads=[]
    def store(action,payload):
        if action=="load_auxiliary_off_attempts":
            reads.append(action)
            if len(reads)==2:return [{"execution_id":row["execution_id"],"outcome":receipt(row,"OFF",at=NOW)}]
        return original(action,payload)
    memory.store=store
    result=memory.run({"contract":CONTRACT,"status":"unobserved","scopes":[]})
    assert not memory.calls and result["status"]=="rootline_provider_notice_superseded"


def test_command_alert_reuses_family_delivery_retry_and_ambiguity_fences():
    row=duty("FERTILIZER-MIXER-CH2");row["stop_requested"]=True;memory=CommandMemory([row]);family=FamilyRail()
    current={"contract":CONTRACT,"status":"unobserved","scopes":[]}
    family.fail=True;assert memory.run(current,notify=family.notify)["success"] is False
    family.fail=False;assert memory.run(current,notify=family.notify)["notification_count"]==1
    assert family.sent[0]==family.sent[1] and memory.run(current,notify=family.notify)["telegram_sends"]==0
    memory=CommandMemory([row])
    memory.run(current,notify=lambda *a,**kw:{"telegram_sends":0,"status":"ambiguous"})
    assert memory.run(current)["status"]=="rootline_provider_delivery_ambiguous" and not memory.calls


def test_confirmed_false_legacy_safety_notice_is_not_replayed_or_escalated():
    legacy=Memory();legacy.duties=[{"execution_id":"DUTY-E12345","zone_id":"E12345","state":"Active"}]
    legacy.run(snapshot())
    memory=CommandMemory([duty()]);memory.receipts=deepcopy(legacy.receipts)
    assert memory.run()["telegram_sends"]==0 and not memory.calls


@pytest.mark.parametrize("language",["en","af"])
def test_command_mode_owner_text_is_informational_and_legacy_wording_retained(language):
    text=provider_availability_text(snapshot(),language=language,command_mode=True)
    assert "Home Assistant" in text and "eWeLink" in text
    legacy=provider_availability_text(snapshot(),language=language,command_mode=False)
    assert ("valid readback" if language=="en" else "geldige lesing") in legacy
    memory=CommandMemory([duty("BOREHOLE-1-MINI-R4-CH1")]);memory.rows[0]["stop_requested"]=True
    memory.run();payload=memory.calls[-1][1];text=compose_provider_notice("ProviderSafety",payload,language=language)
    assert ("Physical state remains unverified" if language=="en" else "Fisiese toestand bly onbevestig") in text


@pytest.mark.parametrize("identity",["FERTILIZER-MIXER-CH2","FERTILIZER-INJECTION-CH1","BOREHOLE-1-MINI-R4-CH1"])
def test_actual_managed_off_failure_remains_visible_without_ewelink_incident(identity):
    from modules.telemetry.rootline_irrigation_coordinator import _finish_command_auxiliary
    from modules.telemetry.rootline_borehole_commissioning import _finish_command_borehole
    row=duty(identity);memory=CommandMemory([row]);original=memory.store;sent=[];contained=[]
    def store(action,payload):
        if action in {"dispatch_auxiliary_off_edge","dispatch_borehole_off_edge"}:
            outcome=payload["dispatch"]()
            memory.off.setdefault(payload["execution_id"],[]).append({"execution_id":payload["execution_id"],
                "attempt":payload["attempt"],"outcome":outcome})
            return outcome
        if action in {"contain_auxiliary_device","contain_borehole"}:
            contained.append(payload);return {"success":True}
        return original(action,payload)
    class Rejected:
        def set_state(self,**kwargs):
            sent.append(kwargs);return {"accepted_unambiguous":False,"provider_command_attempted":True}
    memory.store=store
    if identity.startswith("BOREHOLE"):
        result=_finish_command_borehole(row,store,Rejected(),now=NOW)
    else:
        result=_finish_command_auxiliary(row,store,Rejected(),now=NOW,reason="energy_stop")
    assert result["effects_unknown"] is True and len(sent)==3 and len(contained)==1
    deadline=row["primary_stop_deadline"]
    current={"contract":CONTRACT,"status":"unobserved","scopes":[]}
    assert memory.run(current)["notification_count"]==1
    assert memory.calls[0][1]["severity"]=="off_command_unaccepted"
    assert memory.run(current)["telegram_sends"]==0
    assert len(sent)==3 and row["primary_stop_deadline"]==deadline


def test_legacy_recheck_failure_does_not_skip_command_alert():
    row=duty("FERTILIZER-MIXER-CH2");row["stop_requested"]=True;memory=CommandMemory([row]);reads=[]
    def loader(**kwargs):
        reads.append(True)
        if len(reads)>1:raise RuntimeError("legacy ledger unavailable")
        return snapshot()
    result=memory.run(loader=loader)
    assert result["success"] is False
    assert len(memory.calls)==1 and memory.calls[0][1]["provider"]=="home_assistant"


def test_direct_plan_uses_mode_aware_provider_explanation(monkeypatch):
    from modules.oom_sakkie.rootline_daily_presentation import compose_daily_rootline_plan
    for key,value in ENV.items():monkeypatch.setenv(key,value)
    text=compose_daily_rootline_plan({"success":True,"provider_availability":snapshot(),"recommendations":[]})
    assert "separate switch readback is not required" in text
    assert "Check the local situation" not in text


def test_irrigation_failed_off_keeps_existing_intervention_without_duplicate_provider_alarm():
    from tests.test_rootline_command_mode import start
    from modules.telemetry.rootline_irrigation_coordinator import advance_irrigation_execution
    _,_,store,transport,clock=start(at=NOW);transport.reject_off=True
    clock[0]+=timedelta(seconds=7201);notices=[]
    def notify(state,payload):
        notices.append((state,payload))
        return {"success":True,"provider_delivery_confirmed":True,"provider_message_id":"INTERVENTION"}
    claimed={row["notification_identity"] for row in store.rows if row.get("action")=="claim_notification"}
    def runtime_store(action,payload):
        if action=="claim_notification":
            identity=payload["notification_identity"];created=identity not in claimed;claimed.add(identity)
            return {"success":True,"created":created}
        return store(action,payload)
    result=advance_irrigation_execution(decision_id="",commissioning_id="",decision_reader=lambda _:None,
        commissioning_reader=lambda _:None,store=runtime_store,transport=transport,notify=notify,
        now=clock[0],clock=lambda:clock[0],active_only=True)
    assert result["status"]=="irrigation_off_command_unknown"
    assert [state for state,_ in notices]==["Intervention"]
    memory=CommandMemory([{**store.active,"event_id":"STOPPING-EVENT"}])
    memory.off[store.active["execution_id"]]=[row for row in store.rows if row.get("action")=="record_off_outcome"]
    assert memory.run(now=clock[0])["notification_count"]==1
    assert [state for state,_,_ in memory.calls]==["ProviderUnavailable"]
    assert len(transport.calls)==4
