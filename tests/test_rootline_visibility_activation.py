"""Default-off staged visibility: no new readers or sends, existing safety intact."""
from datetime import datetime, timezone
import pytest
from modules.telemetry import rootline_input_health as health
from modules.telemetry import rootline_provider_availability as provider
from modules.oom_sakkie import rootline_transition_notifications as notices

NOW=datetime(2026,11,20,17,tzinfo=timezone.utc)
ENABLED={health.OWNERSHIP_FLAG:"true"}
PROVIDER_ID="ROOTLINE-PROVIDER-"+"A"*32+":unavailable"
INPUT_ID="ROOTLINE-INPUT-"+"A"*32+":unavailable:"+"b"*32

def forbidden(*a,**kw): raise AssertionError("disabled_visibility_effect")


@pytest.mark.parametrize("value",[None,"false","","0","1",False])
def test_disabled_public_readers_and_receipts_never_connect(value,monkeypatch):
    monkeypatch.delenv(health.OWNERSHIP_FLAG,raising=False)
    if value is not None: monkeypatch.setenv(health.OWNERSHIP_FLAG,str(value))
    p=provider.read_provider_availability(connect=forbidden,now="invalid")
    i=health.read_input_health(connect=forbidden,now="invalid")
    assert p=={"contract":provider.CONTRACT,"status":"unknown","reason":"not_enabled","scopes":[]}
    assert i=={"contract":health.CONTRACT,"status":"unknown","reason":"not_enabled","inputs":{}}
    assert provider.read_notification_receipt(PROVIDER_ID,connect=forbidden)=={}
    assert health.read_input_notification_receipt(INPUT_ID,connect=forbidden)=={}
    state=health.read_input_notice_state("power",connect=forbidden)
    assert state["status"]==state["input"]["state"]=="unknown"
    assert state["reason"]=="not_enabled" and state["episode"] is None
    assert state["input"]["notify"] is False
    assert health.reconcile_input_health(connect=forbidden)["status"]=="disabled"


def test_explicit_disabled_environment_overrides_ambient_enabled(monkeypatch):
    monkeypatch.setenv(health.OWNERSHIP_FLAG,"true")
    assert provider.read_provider_availability(connect=forbidden,environ={})["reason"]=="not_enabled"
    assert health.read_input_health(connect=forbidden,environ={})["reason"]=="not_enabled"
    assert provider.read_notification_receipt(PROVIDER_ID,connect=forbidden,environ={})=={}
    assert health.read_input_notification_receipt(INPUT_ID,connect=forbidden,environ={})=={}
    assert health.read_input_notice_state("weather",connect=forbidden,environ={})["episode"] is None


@pytest.mark.parametrize("environment",[{}, {health.OWNERSHIP_FLAG:"false"}])
def test_disabled_recovery_never_calls_any_injected_dependency(environment):
    p=notices.recover_provider_notifications(notify=forbidden,store=forbidden,loader=forbidden,
        receipt_loader=forbidden,clock=forbidden,environ=environment)
    i=notices.recover_input_notifications(notify=forbidden,recipient=None,store=forbidden,
        reconcile=forbidden,state_loader=forbidden,receipt_loader=forbidden,clock=forbidden,environ=environment)
    for result in (p,i):
        assert result["status"].endswith("disabled") and result["success"] is True
        assert result["telegram_sends"]==result["notification_count"]==result["hardware_commands"]==0


@pytest.mark.parametrize("entry",["provider","input","provider_receipt","input_receipt","notice_state","reconcile"])
def test_explicit_enablement_reaches_the_existing_connection_boundary(entry,monkeypatch):
    monkeypatch.delenv(health.OWNERSHIP_FLAG,raising=False)
    class Reached(Exception): pass
    def connect(**kw): raise Reached()
    calls={"provider":lambda:provider.read_provider_availability(connect=connect,now=NOW,environ=ENABLED),
        "input":lambda:health.read_input_health(connect=connect,now=NOW,environ=ENABLED),
        "provider_receipt":lambda:provider.read_notification_receipt(PROVIDER_ID,connect=connect,environ=ENABLED),
        "input_receipt":lambda:health.read_input_notification_receipt(INPUT_ID,connect=connect,environ=ENABLED),
        "notice_state":lambda:health.read_input_notice_state("power",connect=connect,now=NOW,environ=ENABLED),
        "reconcile":lambda:health.reconcile_input_health(connect=connect,environ=ENABLED)}
    with pytest.raises(Reached): calls[entry]()


def test_enabled_recovery_propagates_explicit_environment_to_default_readers(monkeypatch):
    monkeypatch.delenv(health.OWNERSHIP_FLAG,raising=False)
    seen=[]
    def available(**kw):
        seen.append(kw)
        assert kw["environ"]==ENABLED
        return {"contract":provider.CONTRACT,"status":"unobserved","scopes":[]}
    monkeypatch.setattr(provider,"read_provider_availability",available)
    result=notices.recover_provider_notifications(notify=forbidden,store=forbidden,environ=ENABLED,clock=lambda:NOW)
    assert result["status"]=="rootline_provider_notifications_observed" and len(seen)==1


@pytest.mark.parametrize("report_due",[False,True])
def test_disabled_gateway_keeps_existing_safety_and_equipment_reports(report_due,monkeypatch):
    from modules.oom_sakkie import automatic_reassessment_scheduler as scheduler
    from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
    from modules.telemetry import rootline_water_energy_plan as planning
    monkeypatch.setenv(health.OWNERSHIP_FLAG,"true") # Explicit source must win.
    monkeypatch.setattr(scheduler,"run_due_reassessment",lambda **kw:(kw["invoke"] if report_due else kw["invoke_not_due"])())
    monkeypatch.setattr(planning,"ensure_due_daily_program",lambda **kw:({"success":True},200))
    calls=[]
    def safety(**kw):
        calls.append("safety")
        return {"success":True,"status":"no_active_irrigation","hardware_commands":0,"telegram_sends":0}
    def equipment(**kw):
        calls.append("equipment")
        return {"success":True,"status":"existing_equipment_report","telegram_sends":0}
    def plan(): calls.append("plan"); raise RuntimeError("existing plan unavailable")
    def new_visibility(**kw):
        calls.append("new_visibility_forbidden")
        return forbidden()
    env={"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED":"true","OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"x"*40,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"42"}
    payload={"scheduler_identity":scheduler.SCHEDULER_IDENTITY,"specialist":"ROOTLINE","owner_user_id":"42","chat_id":"42",
        "due_at":NOW.isoformat(),"evidence_cutoff":NOW.isoformat(),"trigger_id":"MINUTE-OFF","trigger":"declared_time","trigger_timestamp":NOW.isoformat()}
    result,status=handle_rootline_reassessment_trigger(payload,{"X-Oom-Sakkie-Telegram-Token":"x"*40},env,
        schedule_store=lambda *a:{},state_store=lambda *a:{},scheduler_now=NOW,specialist_loader=plan,
        active_supervision_cycle=safety,managed_device_cycle=safety,equipment_notification_cycle=equipment,
        provider_notification_cycle=new_visibility,input_notification_cycle=new_visibility,family_delivery=forbidden)
    assert calls[:2]==["safety","safety"] and result["telegram_sends"]==0
    assert "new_visibility_forbidden" not in calls
    if report_due: assert "plan" in calls
    else: assert "equipment" in calls and "plan" not in calls


def test_disabled_legacy_health_delivery_remains_owned_by_existing_paths(monkeypatch):
    monkeypatch.delenv(health.OWNERSHIP_FLAG,raising=False)
    for kind,typ in health.LEGACY_TYPES.items():
        value={"sendable_alerts":[{"alert_type":typ},{"alert_type":"UNRELATED"}],"suppressed_alerts":[]}
        assert health.apply_legacy_ownership(value,kind) is value
