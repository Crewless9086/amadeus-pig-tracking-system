"""Regression for the retained 14 September 06:45/06:50/06:55 plans."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import pytest

from modules.oom_sakkie.daily_farm_manager import build_daily_management_packet, run_daily_farm_manager
from modules.oom_sakkie.farm_manager_loop import (
    Authority, Provenance, SpecialistAvailability, SpecialistResult, SpecialistWorkItem, WorkState,
)

NOW = datetime(2026, 9, 14, 4, 45, tzinfo=timezone.utc)


def task(key, state=WorkState.URGENT, value=100):
    return SpecialistWorkItem(item_id='source:' + key, dedupe_key=key, domain='herd',
        title=key, why='An attributable farm fact needs review.',
        next_action='HERDMASTER will check the related records.', assignee='charl',
        state=state, authority=Authority.ADVISORY,
        provenance=Provenance('herdmaster', 'source', ('canonical',), NOW, 1),
        business_value=value)


def result(items):
    return SpecialistResult('herdmaster', 'source', NOW, SpecialistAvailability.AVAILABLE,
        work_items=tuple(items))


@pytest.mark.parametrize('language', ['en', 'af'])
def test_retained_mortality_weaning_order_swap_is_not_new_material(language):
    # These task identities and the same-priority swap come from the retained
    # morning receipts; every task's substantive fields were unchanged.
    mortality = task('herdmaster:mortality-cluster:f3f387c0cda08c0007dc', value=1000)
    weaning = replace(task('weaning:LIT-2026-5C36', value=130),
        authority=Authority.OWNER_DECISION, title='Weaning overdue — Molly',
        due_at=NOW - timedelta(days=3))
    farrowing = task('herdmaster:farrowing-preparation', WorkState.DUE_TODAY)
    irrigation = task('rootline:daily-plan', WorkState.PLANNED)
    weighing = task('herdmaster:weekly-weight-evidence', WorkState.WAITING_EVIDENCE)
    items = [mortality, weaning, farrowing, irrigation, weighing]
    packets = [build_daily_management_packet([result(items)], now=NOW, language=language,
        semantic_prioritizer=lambda _rows, order=order, **_kw: [row.item_id for row in order])
        for order in (items, [weaning, mortality, farrowing, irrigation, weighing], items)]
    assert len({packet['material_digest'] for packet in packets}) == 1


def test_equal_material_reordering_cannot_change_visibility_at_three_or_six():
    items = [task(str(index)) for index in range(7)]
    orders = [items, list(reversed(items)), items[2:] + items[:2]]
    packets = [build_daily_management_packet([result(order)], now=NOW,
        semantic_prioritizer=lambda _rows, order=order, **_kw: [row.item_id for row in order])
        for order in orders]
    assert len({packet['material_digest'] for packet in packets}) == 1
    assert all({row.dedupe_key for row in packet['priorities']} == {'0', '1', '2'} for packet in packets)


@pytest.mark.parametrize('change', ['priority', 'state', 'reason', 'action', 'due', 'physical_work'])
def test_genuine_changes_still_replace_material(change):
    item = replace(task('weaning'), authority=Authority.OWNER_DECISION, due_at=NOW)
    changes = {'priority': {'business_value': 150}, 'state': {'state': WorkState.DUE_TODAY},
        'reason': {'why': 'The current litter count changed.'},
        'action': {'next_action': 'Review the corrected piglet count.'},
        'due': {'due_at': NOW + timedelta(days=1)},
        'physical_work': {'authority': Authority.ADVISORY, 'metadata': {'physical_work_ready': True}}}
    first = build_daily_management_packet([result([item])], now=NOW)
    changed = build_daily_management_packet([result([replace(item, **changes[change])])], now=NOW)
    assert changed['material_digest'] != first['material_digest']


def test_source_generation_is_not_business_priority():
    items = [task('a'), task('b'), task('c'), task('d')]
    first = build_daily_management_packet([result(items)], now=NOW)
    refreshed = [replace(row, item_id='new:' + str(10-index)) for index, row in enumerate(items)]
    second = build_daily_management_packet([result(refreshed)], now=NOW)
    assert first['material_digest'] == second['material_digest']


def test_no_question_has_no_invented_question_binding():
    packet = build_daily_management_packet([result([task('a')])], now=NOW)
    assert packet['question'] == '' and packet['question_binding'] == {}


def test_identical_question_wording_on_a_different_hidden_task_is_new_material():
    visible = [task(str(index), value=100) for index in range(6)]
    question = replace(task('sow-a', value=10), genuine_question='Has she farrowed?', question_for='charl')
    first = build_daily_management_packet([result(visible + [question])], now=NOW)
    second = build_daily_management_packet([result(visible + [replace(question, dedupe_key='sow-b', item_id='sow-b')])], now=NOW)
    assert first['question'] == second['question']
    assert first['material_digest'] != second['material_digest']


def test_order_only_scheduled_followup_has_no_provider_or_replacement_effect():
    items = [task('a'), task('b')]
    events, sends, replacements = {}, [], []
    def store(action, identity, payload):
        if action == 'load_daily':
            return next((value for value in reversed(list(events.values()))
                if value.get('status') == 'presented'), None)
        if action == 'load_answered_questions':
            return ()
        created = identity not in events
        if created:
            events[identity] = dict(payload)
        return {'success': True, 'created': created}
    def deliver(*args, **kwargs):
        sends.append(args)
        return {'success': True, 'telegram_message_id': 'local-initial', 'telegram_sends': 1}
    for order in (items, items[::-1], items):
        outcome = run_daily_farm_manager(owner_user_id='local-owner', chat_id='local-owner',
            specialist_results=[result(items)], litter_rows=[], now=NOW, store=store,
            deliver=deliver, replace_brief=lambda *a, **k: replacements.append(a),
            semantic_prioritizer=lambda _rows, order=order, **kw: [row.item_id for row in order])
    assert outcome['status'] == 'daily_manager_unchanged_silent'
    assert len(sends) == 1 and replacements == []
