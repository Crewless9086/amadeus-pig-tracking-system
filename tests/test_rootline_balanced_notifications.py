"""Approved owner notification policy through typed records and real delivery rails."""
from copy import deepcopy
from datetime import timedelta
import pytest
from modules.oom_sakkie.rootline_activity_presentation import activity_notice
from modules.oom_sakkie import rootline_transition_notifications as notices
from modules.telemetry import rootline_command_acceptance as ca
from tests.test_rootline_command_notice_routing import duty, receipt, NOW
from tests.test_rootline_input_health_visibility import Memory, episode, ENABLED, RECIPIENT

@pytest.mark.parametrize("language", ["en", "af"])
def test_early_mixer_stop_is_unfinished_not_completed(language):
    row = duty("FERTILIZER-MIXER-CH2")
    stop = ca.moment(row["command_on_receipt"]["accepted_at"])+timedelta(seconds=82)
    row = ca.terminal(row, receipt(row,"OFF",at=stop), now=stop, reason="energy_stop")
    text = activity_notice("Completed", row, language=language)
    assert ("Programme unfinished" if language=="en" else "Program onvoltooid") in text
    assert "✅" not in text and "⏸️" in text
    assert "physical" not in text and "water delivery" not in text
    assert "82" not in text  # seconds are presented as minutes, not an invented full programme
    assert "/ 10 min" in text

@pytest.mark.parametrize("state", ["Started", "Completed"])
def test_missing_command_receipt_does_not_claim_success(state):
    row=duty(); row["command_on_receipt"]=None
    text=activity_notice(state,row)
    assert "Outcome unconfirmed" in text and "✅" not in text
    assert "command accepted" not in text

@pytest.mark.parametrize("pending,active,expected", [(False,False,0),(True,False,1),(False,True,1)])
def test_short_gap_only_quiet_when_no_active_or_pending_work(pending,active,expected):
    item=episode("power");item["outage_started_at"]=(NOW-timedelta(seconds=60)).isoformat()
    memory=Memory(item)
    def store(action,payload):
        if action=="load_active": return {"execution_id":"active"} if active else None
        if action=="load_active_borehole": return None
        if action=="load_active_auxiliaries": return []
        return memory.store(action,payload)
    result=notices.recover_input_notifications(notify=memory.notify,recipient=RECIPIENT,
        now=NOW,environ=ENABLED,clock=lambda:NOW,store=store,
        reconcile=lambda **_: {"contract":item["contract"],"status":"observed","episodes":[item]},
        state_loader=memory.state,receipt_loader=memory.receipt,pending_work_loader=lambda **_:pending)
    assert result["telegram_sends"]==expected
    assert len(memory.calls)==expected


def test_unreported_brief_gap_has_no_recovery_message():
    memory=Memory(episode("power",restored=True))
    assert memory.run()["telegram_sends"]==0 and memory.calls==[]


def test_high_battery_is_quiet_but_low_battery_and_grid_alerts_remain(monkeypatch):
    from modules.telemetry.rootline_input_health import apply_legacy_ownership
    monkeypatch.setenv("ROOTLINE_INPUT_HEALTH_ENABLED","true")
    rows=[{"alert_type":kind} for kind in ("POWER_BATTERY_HIGH","POWER_BATTERY_LOW","POWER_GRID_ACTIVE")]
    result=apply_legacy_ownership({"sendable_alerts":rows,"suppressed_alerts":[]},"power")
    assert result["sendable_alerts"]==rows[1:]
    assert result["suppressed_alerts"][0]["alert_type"]=="POWER_BATTERY_HIGH"


def test_gap_heading_names_power_and_recovery_is_not_equipment_start():
    text=notices.compose_input_notice("InputUnavailable",episode("power"))
    assert "Power readings delayed" in text and "INPUTS UNAVAILABLE" not in text
    text=notices.compose_input_notice("InputRestored",episode("power",restored=True))
    assert "Power readings restored" in text and "running" not in text

@pytest.mark.parametrize("state", ["Started","Completed","Stopped","Adopted"])
def test_single_emoji_and_actual_afrikaans_family_localization(state):
    from modules.oom_sakkie.family_message_lifecycle import localize_recipient_result
    from modules.oom_sakkie.family_presentation import envelope
    text=activity_notice(state,duty("BOREHOLE-1-MINI-R4-CH1"),language="af")
    result=localize_recipient_result({"output_language":"af"},{"status":state.lower(),"answer":text,
        "recipient_render_contract":"specialist_structured_recipient_v1","recipient_language":"af"},"ROOTLINE")
    assert result["answer"]==text and not result.get("recipient_language_render_unrecognized")
    assert envelope(text)==text


def test_actual_gateway_preserves_auxiliary_intervention_and_no_hardware():
    from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    from tests.test_rootline_visible_operation import Events, current, plan_store, schedule_store, scheduled_payload, ENV, HEADERS, NOW as gateway_now
    events=Events([]); sent=[]
    def sender(chat,text,**kwargs):
        sent.append(text)
        return {"success":True,"telegram_message_id":str(len(sent))}
    def deliver(parsed,result,**kwargs):
        return deliver_family_result(parsed,result,event_store=events.delivery,sender=sender,**kwargs)
    def equipment(**kwargs):
        proof=kwargs["notify"]("Intervention",duty("FERTILIZER-MIXER-CH2"))
        return {"success":True,"status":"observed","telegram_sends":proof["telegram_sends"],"hardware_commands":0}
    result,_=handle_rootline_reassessment_trigger({**scheduled_payload(due_at=gateway_now.isoformat()),
        "owner_user_id":"42","chat_id":"42","trigger":"declared_time","trigger_id":gateway_now.isoformat(),
        "trigger_timestamp":gateway_now.isoformat()},HEADERS,ENV,scheduler_now=gateway_now,
        specialist_loader=current,state_store=plan_store()[1],schedule_store=schedule_store()[1],
        family_delivery=deliver,equipment_notification_cycle=equipment,
        active_supervision_cycle=lambda **_: {"success":True,"status":"no_active_irrigation",
            "active_execution_found":False,"hardware_commands":0,"writes_farm_data":False})
    assert any("INTERVENTION" in text for text in sent), str((sent,result))
    alert=next(text for text in sent if "INTERVENTION" in text)
    assert "Mixer shutdown is uncertain" in alert and "owner attention is required" in alert
    assert "automatic reuse is contained" in alert.lower()
    assert result["hardware_commands"]==0


@pytest.mark.parametrize("damage,expected", [(None,False),("pending",True),("missing",True),("empty",True),("malformed",True)])
def test_production_plan_inventory_required_before_quiet_gap(monkeypatch,damage,expected):
    from modules.telemetry import rootline_water_energy_plan as planning
    from modules.telemetry.rootline_device_registry import IRRIGATION_ZONE_IDS
    plan={"success":True,"candidate_tasks":[{"task_id":"irrigation_"+zone,"zone_decision":"Do Not Run"}
        for zone in IRRIGATION_ZONE_IDS],"irrigation_auxiliary_tasks":[]}
    if damage=="pending":plan["candidate_tasks"][0]["zone_decision"]="Recommend"
    if damage=="missing":plan.pop("candidate_tasks")
    if damage=="empty":plan["candidate_tasks"]=[]
    if damage=="malformed":plan["candidate_tasks"]=[None]
    monkeypatch.setattr(planning,"get_current_water_energy_plan",lambda *a,**k:(plan,200))
    assert notices._input_gap_has_pending_work(now=NOW,environ={}) is expected


def test_partial_start_times_do_not_claim_complete_camp_order():
    from modules.oom_sakkie.rootline_daily_presentation import compose_daily_rootline_plan
    value={"recommendations":[{"subject":"A12345","planned_duration_minutes":30,"planned_start_at":NOW.isoformat()},
        {"subject":"B12345","planned_duration_minutes":30}]}
    assert "Order:" not in compose_daily_rootline_plan(value)


def test_unverified_equipment_check_does_not_reassure_no_action_needed():
    from modules.oom_sakkie.rootline_daily_presentation import compose_daily_rootline_plan
    text=compose_daily_rootline_plan({"control_observation":"unverified"})
    assert "No action needed" not in text and "equipment check is unconfirmed" in text
