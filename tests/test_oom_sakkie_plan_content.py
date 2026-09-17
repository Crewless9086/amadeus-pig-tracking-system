"""Current farm actions must use the application's canonical timing and facts."""
from copy import deepcopy
from datetime import datetime, timezone
from modules.oom_sakkie.farm_manager_runtime import _whole_herd_specialist_result
from tests.test_oom_sakkie_herd_morning_language import snapshot


def test_current_sows_with_different_matings_keep_their_own_farrowing_windows():
    value = deepcopy(snapshot())
    now = datetime(2026, 8, 15, tzinfo=timezone.utc)
    value['canonical']['generated_at'] = now.isoformat()
    value['canonical']['tasks'][1]['known_evidence']['current_mating_date'] = '2026-05-09'
    value['observations'][1]['mating_date'] = '2026-05-09'
    result = _whole_herd_specialist_result(value['canonical'], value['observations'], [], now)
    rows = {row.title: row for row in result.work_items}
    assert set(rows) == {'Prepare Mysikind', 'Prepare Mona'}
    assert '2026-08-22 to 2026-08-26' in rows['Prepare Mysikind'].why
    assert '2026-08-29 to 2026-09-02' in rows['Prepare Mona'].why


def test_later_canonical_litter_retires_the_old_pregnancy_watch():
    value = deepcopy(snapshot())
    for task in value['canonical']['tasks']:
        task['known_evidence']['latest_litter_date'] = '2026-08-23'
    result = _whole_herd_specialist_result(value['canonical'], value['observations'], [],
        datetime(2026, 9, 14, tzinfo=timezone.utc))
    assert not result.work_items


def test_old_litter_does_not_suppress_unresolved_current_mating():
    value = deepcopy(snapshot())
    for task in value['canonical']['tasks']:
        task['known_evidence']['latest_litter_date'] = '2026-03-29'
    result = _whole_herd_specialist_result(value['canonical'], value['observations'], [],
        datetime(2026, 9, 14, tzinfo=timezone.utc))
    row, = result.work_items
    assert row.title == 'Current farrowing status — Mysikind and Mona'
    assert '2026-08-22 to 2026-08-26 has passed' in row.why
    assert 'already farrowed' in row.genuine_question
