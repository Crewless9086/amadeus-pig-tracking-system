"""Real owner formatting and delivery gate, isolated canonical/provider boundaries."""
from copy import deepcopy
from datetime import datetime
import pytest
from modules.oom_sakkie.rootline_daily_presentation import compose_daily_rootline_plan, SAST
from modules.oom_sakkie.rootline_material import rootline_material_digest
from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
from tests.test_oom_sakkie_rootline_reassessment_delivery import memory_store, ENV, HEADERS, payload


def plan():
    return {"success":True,"operating_date":"2026-11-26","result_id":"NOTICE46",
        "generated_at":"2026-11-26T00:00:00+02:00", "evidence_cutoff":"2026-11-26T06:29:00+02:00",
        "recommendations":[{"subject":zone+"12345","status":"Hold","planned_duration_minutes":60,
            "planned_start_at":f"2026-11-26T{hour:02}:00:00+02:00",
            "planned_end_at":f"2026-11-26T{hour+1:02}:00:00+02:00",
            "preferred_window":"stale advisory window"} for zone,hour in [("B",11),("C",12),("A",10),("E",13)]]}


@pytest.mark.parametrize("language",["en","af"])
def test_bullets_follow_canonical_times_with_both_local_endpoints(language):
    value=plan();value['recommendations'] += [{"subject":"fertilizer_mixing","status":"Needs Data"},
        {"subject":"fertilizer_injection","status":"Recommend"}]
    text=compose_daily_rootline_plan(value,language=language)
    label="Camp" if language=='en' else "Kamp"
    assert [text.index(f"<b>{zone} {label}:") for zone in 'ABCE']==sorted(text.index(f"<b>{zone} {label}:") for zone in 'ABCE')
    assert '10h00–11h00 SAST' in text and '13h00–14h00 SAST' in text
    assert text.count('2026-11-26')==1
    assert 'stale advisory window' not in text and 'Needs Data' not in text
    assert 'Recommendation - irrigate' not in text and 'Not running' not in text
    assert 'FERTILIZER' not in text


@pytest.mark.parametrize("damage",['missing_end','naive','reversed'])
def test_unknown_window_is_not_invented(damage):
    value=plan();row=value['recommendations'][2]
    if damage=='missing_end':row.pop('planned_end_at')
    elif damage=='naive':row['planned_end_at']='2026-11-26T11:00:00'
    else:row['planned_end_at']='2026-11-26T09:00:00+02:00'
    text=compose_daily_rootline_plan(value)
    assert '10h00–11h00' not in text and 'stale advisory window' not in text


def test_window_only_edit_changes_shared_material_identity():
    value=plan();changed=deepcopy(value);changed['recommendations'][0]['planned_end_at']='2026-11-26T12:30:00+02:00'
    assert rootline_material_digest(value)!=rootline_material_digest(changed)


def call(value,store,calls,clock,**kwargs):
    def deliver(*args,**kw):
        calls.append(args);return {"success":True,"telegram_message_id":str(8000+len(calls)),"telegram_sends":1}
    return handle_rootline_reassessment_trigger(payload(),HEADERS,ENV,specialist_loader=lambda:value,
        state_store=store,family_delivery=deliver,scheduler_now=datetime.fromisoformat(clock),**kwargs)


def test_routine_gate_0629_0630_then_unchanged_and_material_edit():
    rows,store=memory_store();calls=[];value=plan()
    for clock in ['00:00:00','06:29:59']:
        result,status=call(value,store,calls,'2026-11-26T'+clock+'+02:00',routine_plan=True)
        assert status==200 and result['status']=='rootline_reassessment_not_due'
        assert result['next_due_at']=='2026-11-26T06:30:00+02:00'
        assert not calls and all(r['delivery_state']=='observation_only' for r in rows.values())
    first,status=call(value,store,calls,'2026-11-26T06:30:00+02:00',routine_plan=True)
    assert status==200 and first['telegram_sends']==1
    replay,_=call(value,store,calls,'2026-11-26T06:31:00+02:00',routine_plan=True)
    assert replay['notify_owner'] is False and len(calls)==1
    value=deepcopy(value);value['recommendations'][0]['planned_end_at']='2026-11-26T12:30:00+02:00'
    changed,_=call(value,store,calls,'2026-11-26T06:32:00+02:00',routine_plan=True)
    assert changed['notify_owner'] is True and len(calls)==2


def test_explicit_on_demand_plan_remains_available_before_morning():
    _,store=memory_store();calls=[]
    value,status=call(plan(),store,calls,'2026-11-26T01:00:00+02:00')
    assert status==200 and value['telegram_sends']==1 and len(calls)==1


def test_typed_urgent_shutdown_exception_bypasses_morning_gate():
    from tests.test_rootline_shutdown_preservation import owner_result
    _,store=memory_store();calls=[]
    value,status=call(owner_result(),store,calls,'2026-11-26T01:00:00+02:00',routine_plan=True)
    assert status==200 and value['telegram_sends']==1 and len(calls)==1


def test_activity_uses_local_h_clock_and_preserves_unfinished_status():
    from modules.oom_sakkie.rootline_activity_presentation import activity_notice
    from tests.test_rootline_command_notice_routing import duty
    row=duty();row['command_on_receipt']['accepted_at']='2026-11-26T08:05:00Z';row['notification_observed_at']='2026-11-27T10:00:00Z'
    text=activity_notice('Started',row)
    assert '26 Nov 2026</b>' in text and '10h05 SAST' in text
    assert '27 Nov' not in text and '26 Nov' in text.splitlines()[0]
    assert '• ' in text


def test_daily_presentation_uses_same_exact_0630_boundary():
    from modules.oom_sakkie.rootline_daily_presentation import present_daily_rootline_plan
    from tests.test_oom_sakkie_rootline_daily_presentation import store, delivery
    rows,state=store();calls=[];value=plan()
    args=dict(owner_user_id="42",chat_id="42",specialist_loader=lambda:value,state_store=state,deliver=delivery(calls))
    early=present_daily_rootline_plan(**args,now=datetime.fromisoformat('2026-11-26T06:29:59+02:00'))
    assert early['status']=='rootline_daily_not_due' and not rows and not calls
    assert early['next_due_at']=='2026-11-26T06:30:00+02:00'
    due=present_daily_rootline_plan(**args,now=datetime.fromisoformat('2026-11-26T06:30:00+02:00'))
    assert due['status']=='rootline_daily_delivered' and len(calls)==1

@pytest.mark.parametrize("clock,expected_sends", [("06:29:59", 0), ("06:30:00", 1)])
def test_actual_scheduled_gateway_applies_morning_gate(clock, expected_sends):
    from tests.test_rootline_visible_operation import plan_store, schedule_store, scheduled_payload, ENV as scheduled_env, HEADERS as scheduled_headers
    now = datetime.fromisoformat('2026-11-26T' + clock + '+02:00')
    value = plan()
    value['evidence_cutoff'] = now.isoformat()
    value['generated_at'] = now.isoformat()
    sent = []
    def deliver(*args, **kwargs):
        sent.append(args)
        return {'success': True, 'telegram_sends': 1, 'telegram_message_id': str(9000 + len(sent))}
    result, status = handle_rootline_reassessment_trigger(
        {**scheduled_payload(due_at=now.isoformat()), 'owner_user_id': '42', 'chat_id': '42',
         'trigger': 'declared_time', 'trigger_id': now.isoformat(), 'trigger_timestamp': now.isoformat(),
         'evidence_cutoff': now.isoformat()},
        scheduled_headers, scheduled_env, scheduler_now=now,
        specialist_loader=lambda: value, state_store=plan_store()[1], schedule_store=schedule_store()[1],
        family_delivery=deliver,
        active_supervision_cycle=lambda **_: {'success': True, 'status': 'no_active_irrigation',
            'active_execution_found': False, 'hardware_commands': 0, 'writes_farm_data': False})
    assert result['hardware_commands'] == 0
    assert len(sent) == expected_sends, (status, result)
    assert result['plan_delivery_status'] == ('delivered_current_irrigation_plan' if expected_sends
        else 'current_irrigation_plan_waiting_for_morning')


def test_new_day_same_plan_waits_until_morning_then_sends_once():
    _, store = memory_store(); calls = []; first = plan()
    result, status = call(first, store, calls, '2026-11-26T06:30:00+02:00', routine_plan=True)
    assert status == 200 and result['telegram_sends'] == 1
    next_day = deepcopy(first)
    next_day['operating_date'] = '2026-11-27'
    next_day['evidence_cutoff'] = '2026-11-27T06:29:00+02:00'
    for row in next_day['recommendations']:
        for key in ('planned_start_at', 'planned_end_at'):
            row[key] = row[key].replace('2026-11-26', '2026-11-27')
    early, _ = call(next_day, store, calls, '2026-11-27T06:29:59+02:00', routine_plan=True)
    assert early['status'] == 'rootline_reassessment_not_due' and len(calls) == 1
    due, _ = call(next_day, store, calls, '2026-11-27T06:30:00+02:00', routine_plan=True)
    assert due['telegram_sends'] == 1 and len(calls) == 2
    replay, _ = call(next_day, store, calls, '2026-11-27T06:31:00+02:00', routine_plan=True)
    assert replay['notify_owner'] is False and len(calls) == 2


@pytest.mark.parametrize('existing_state', ['pending', 'ambiguous'])
def test_early_gate_preserves_existing_delivery_packet(existing_state):
    rows, store = memory_store(); calls = []
    rows['existing-packet'] = {'delivery_state': existing_state, 'identity': 'existing-packet',
        'owner_user_id': '42', 'chat_id': '42', 'provider_message_id': ''}
    before = deepcopy(rows['existing-packet'])
    result, status = call(plan(), store, calls, '2026-11-26T06:29:59+02:00', routine_plan=True)
    assert status == 200 and result['status'] == 'rootline_reassessment_not_due'
    assert not calls and rows['existing-packet'] == before
    assert all(row['delivery_state'] == 'observation_only' for key, row in rows.items() if key != 'existing-packet')
