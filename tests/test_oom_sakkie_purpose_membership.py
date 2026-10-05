"""Full membership is durable evidence, not a second task or write authority."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest

from modules.oom_sakkie import herdmaster_purpose_membership as membership
from modules.oom_sakkie import general_manager_worker as worker
from modules.oom_sakkie import herdmaster_purpose_completion as completion
from modules.oom_sakkie import manager_case_sources as sources
from modules.pig_weights.herdmaster_purpose_work import build_purpose_work
from tests.test_herdmaster_purpose_work import inputs, DAY, NOW
from tests.test_oom_sakkie_purpose_completion import (
    purpose_db, execute_real_correction, proof_fixture, pg)


def packet(count=2, *, now=NOW, removed=(), extra=0):
    allocation, checks, _ = inputs(count=count+extra, weight_day=DAY-timedelta(days=1))
    for i in removed:
        allocation['pigs'][i]['purpose'] = 'Sale'
        checks['rows'][i]['canonical']['purpose'] = 'Sale'
    work = build_purpose_work(allocation, checks, analysis_date=DAY)
    snapshot = {'purpose_work': work, 'snapshot_observed_at': now}
    raw = sources._purpose_review_candidates(snapshot, now=now, today=DAY, observed_at=now)[0]
    case = {**worker.normalize_candidate(raw, now=now), 'generation': 1,
        'status': 'waiting_reassessment', 'generation_started_at': now,
        'assigned_worker_id': None, 'lease_until': None}
    return raw, case, snapshot


def event(case, record, *, kind='created'):
    return {'case_id': case['case_id'], 'generation': record['generation'], 'event_type': kind,
        'occurred_at': record['recorded_at'], 'event_payload': {'case_id': case['case_id'],
        'generation': record['generation'], 'purpose_membership': record}}


def verified(case, snapshot, record, *, now=NOW):
    return membership.verify_current_membership(case, snapshot,
        membership_events=[event(case, record)], now=now,
        expected_generation=case['generation'], expected_evidence_digest=case['evidence_digest'])


@pytest.mark.parametrize('count', [1, 2, 11, 12, 13, 50, 5000])
def test_exact_full_membership_beyond_reference_cap(count):
    raw, case, snapshot = packet(count)
    record = membership.build_record(case, generation=1, now=NOW)
    result = verified(case, snapshot, record)
    assert result['member_count'] == count
    assert len(result['member_ids']) == count == len(result['completion_member_ids'])
    assert len([r for r in case['evidence_refs'] if r.startswith('pig:')]) == min(count, 12)
    assert result['member_ids'] == sorted(result['member_ids'])
    bare = deepcopy(raw); bare.pop('_purpose_membership')
    assert worker.normalize_candidate(bare, now=NOW)['evidence_digest'] == case['evidence_digest']


@pytest.mark.parametrize('change', ['duplicate_id', 'duplicate_tag', 'missing_tag', 'foreign_id',
    'missing_id', 'count', 'members_digest', 'material', 'source_digest', 'stale_generation',
    'stale_digest', 'future', 'naive', 'old', 'missing_event', 'duplicate_event',
    'foreign_event', 'leased', 'delegated', 'held', 'missing_source'])
def test_preview_fails_closed_for_incomplete_stale_or_foreign_binding(change):
    raw, case, snapshot = packet()
    record = membership.build_record(case, generation=1, now=NOW)
    events = [event(case, record)]
    if change in {'duplicate_id', 'duplicate_tag', 'missing_tag', 'foreign_id', 'missing_id'}:
        cohort = snapshot['purpose_work']['cohorts'][0]
        if change == 'duplicate_id': cohort['members'][1]['pig_id'] = cohort['members'][0]['pig_id']
        elif change == 'duplicate_tag': cohort['members'][1]['tag'] = cohort['members'][0]['tag']
        elif change == 'missing_tag': cohort['members'][0]['tag'] = ''
        elif change == 'foreign_id': cohort['members'][0]['pig_id'] = 'PIG-FOREIGN'
        else: cohort['member_ids'].pop()
    elif change == 'count': record['member_count'] = 1
    elif change == 'members_digest': record['membership_digest'] = 'f'*64
    elif change == 'material': case['evidence_refs'] = [r.replace(record['material_digest'], 'F'*64) for r in case['evidence_refs']]
    elif change == 'source_digest': snapshot['purpose_work']['cohorts'][0]['material_digest'] = 'F'*64
    elif change == 'stale_generation': case['generation'] += 1
    elif change == 'stale_digest': case['evidence_digest'] = 'f'*64
    elif change == 'future': snapshot['snapshot_observed_at'] = NOW+timedelta(seconds=1)
    elif change == 'naive': snapshot['snapshot_observed_at'] = NOW.replace(tzinfo=None)
    elif change == 'old': snapshot['snapshot_observed_at'] = NOW-timedelta(seconds=121)
    elif change == 'missing_event': events = []
    elif change == 'duplicate_event': events *= 2
    elif change == 'foreign_event': events[0]['case_id'] = 'OTHER'
    elif change == 'leased': case['lease_until'] = NOW+timedelta(seconds=1)
    elif change == 'delegated': case['status'] = 'delegated'
    elif change == 'held': snapshot['purpose_work']['cohorts'][0]['phase'] = 'held'
    elif change == 'missing_source': snapshot['purpose_work']['cohorts'] = []
    with pytest.raises(membership.PurposeMembershipError):
        membership.verify_current_membership(case, snapshot, membership_events=events, now=NOW)


def test_partial_and_added_member_lineage_preserves_original_epochs():
    _, original, _ = packet()
    first = membership.build_record(original, generation=1, now=NOW)
    later = NOW+timedelta(minutes=1)
    _, remaining, snapshot = packet(now=later, removed=(0,), extra=1)
    remaining['generation'] = 2
    second = membership.build_record(remaining, generation=2, now=later, previous=first)
    result = verified(remaining, snapshot, second, now=later)
    assert second['origin'] == first['origin']
    assert len(result['member_ids']) == 2 and len(result['completion_member_ids']) == 3
    epochs = {v['pig_id']: v['required_since'] for v in second['obligations']}
    assert epochs['PIG-SYNTHETIC-0000'] == epochs['PIG-SYNTHETIC-0001'] == NOW.isoformat()
    assert epochs['PIG-SYNTHETIC-0002'] == later.isoformat()
    with pytest.raises(membership.PurposeMembershipError):
        membership.verify_current_membership(remaining, snapshot, membership_events=[event(remaining, second)],
            now=later, expected_generation=1, expected_evidence_digest=original['evidence_digest'])


def test_partial_successor_completion_requires_previously_removed_member_proof():
    case, pigs, history = proof_fixture()
    _, original, _ = packet()
    first = membership.build_record(original, generation=1, now=NOW)
    later = NOW+timedelta(seconds=4)
    _, remaining, _ = packet(now=later, removed=(0,))
    remaining.update(generation=2, generation_started_at=later)
    remaining['purpose_membership'] = membership.build_record(remaining, generation=2, now=later, previous=first)
    # Both approved events precede the narrowed generation, but follow their
    # original membership epoch. Losing one cannot be concealed by the subset.
    result = completion.completion_candidate(remaining, pigs, history, now=NOW+timedelta(minutes=1))
    assert result is not None
    assert completion.completion_candidate(remaining, pigs, history[1:], now=NOW+timedelta(minutes=1)) is None
    pigs[0]['purpose'] = 'Unknown'
    assert completion.completion_candidate(remaining, pigs, history, now=NOW+timedelta(minutes=1)) is None


@pytest.mark.parametrize('bad', ['', 'S0001'])
def test_held_missing_or_duplicate_tag_does_not_erase_eligible_sibling(bad):
    allocation, checks, _ = inputs(count=3, weight_day=DAY-timedelta(days=1))
    for rows in (allocation['pigs'],):
        rows[2]['litter_id'] = 'COHORT-B'
        rows[0]['tag_number'] = bad
    checks['rows'][0]['canonical']['tag_number'] = bad
    work = build_purpose_work(allocation, checks, analysis_date=DAY)
    rows = sources._purpose_review_candidates({'purpose_work': work}, now=NOW, today=DAY, observed_at=NOW)
    assert len(rows) == 2
    held = next(r for r in rows if r['dedupe_key'].endswith('COHORT-A'))
    sibling = next(r for r in rows if r['dedupe_key'].endswith('COHORT-B'))
    assert '_purpose_membership' not in held
    assert sibling['_purpose_membership']['member_count'] == 1


def test_member_bound_refuses_oversized_metadata():
    _, case, _ = packet()
    value = case['_purpose_membership']
    value['members'] = value['members'] * 2501
    with pytest.raises(membership.PurposeMembershipError, match='bound'):
        membership.validate_candidate_membership(case, value)


def seed_legacy(pg, raw):
    from unittest.mock import patch
    original = pg.store._event
    def legacy_event(cur, case, event_type, now, **payload):
        payload.pop('purpose_membership_unavailable', None)
        return original(cur, case, event_type, now, **payload)
    with patch.object(pg.store, '_event', side_effect=legacy_event):
        pg.seed([raw])


def test_postgres_same_generation_legacy_adoption_is_once_metadata_only(purpose_db):
    pg, connect = purpose_db
    raw, _, _ = packet(now=pg.now)
    legacy = deepcopy(raw); legacy.pop('_purpose_membership')
    seed_legacy(pg, legacy)
    with connect() as db:
        db.execute("update app_private.oom_manager_cases set status='waiting_reassessment',last_delivery_digest=evidence_digest,last_delivery_at=%s", (pg.now,))
        before = db.execute('select generation,evidence_digest,last_delivery_digest,last_delivery_at,next_reassessment_at from app_private.oom_manager_cases').fetchone()
        with db.cursor() as cur:
            assert pg.store._reconcile(cur, worker.normalize_candidate(raw, now=pg.now), pg.now) == 'replayed'
            assert pg.store._reconcile(cur, worker.normalize_candidate(raw, now=pg.now), pg.now) == 'replayed'
        assert db.execute('select generation,evidence_digest,last_delivery_digest,last_delivery_at,next_reassessment_at from app_private.oom_manager_cases').fetchone() == before
        events = db.execute("select event_type,event_payload from app_private.oom_manager_case_events order by occurred_at,event_id").fetchall()
        adopted = [v for kind,v in events if kind=='reassessment_scheduled']
        assert len(adopted)==1 and adopted[0]['metadata_only'] is True
        assert adopted[0]['schedule_changed'] is False and adopted[0]['delivery_changed'] is False
        assert not any(kind in {'delivery_confirmed','evidence_changed'} for kind,_ in events)


def test_postgres_legacy_after_partial_correction_cannot_invent_original_membership(purpose_db, monkeypatch):
    pg, connect = purpose_db
    raw, _, _ = packet(now=pg.now)
    legacy = deepcopy(raw); legacy.pop('_purpose_membership'); seed_legacy(pg, legacy)
    execute_real_correction(connect, monkeypatch, ['PIG-SYNTHETIC-0000'])
    pg.now=datetime.now(timezone.utc)+timedelta(seconds=1)
    remaining, _, _ = packet(now=pg.now, removed=(0,))
    with connect() as db, db.cursor() as cur:
        assert pg.store._reconcile(cur, worker.normalize_candidate(remaining, now=pg.now), pg.now) == 'changed'
        assert pg.store._reconcile(cur, worker.normalize_candidate(remaining, now=pg.now), pg.now) == 'replayed'
        assert db.execute("select count(*) from app_private.oom_manager_case_events where event_payload ? 'purpose_membership'").fetchone()[0] == 0
        assert db.execute("select count(*) from app_private.oom_manager_case_events where event_payload ? 'purpose_membership_unavailable'").fetchone()[0] == 1


def test_postgres_partial_new_lineage_completion_preserves_original_members(purpose_db, monkeypatch):
    pg, connect = purpose_db
    raw, _, _ = packet(now=pg.now); pg.seed([raw])
    execute_real_correction(connect, monkeypatch, ['PIG-SYNTHETIC-0000'])
    pg.now=datetime.now(timezone.utc)+timedelta(seconds=1)
    remaining, _, _ = packet(now=pg.now, removed=(0,))
    pg.seed([remaining])
    with connect() as db:
        records = db.execute("select event_payload->'purpose_membership' from app_private.oom_manager_case_events where event_payload ? 'purpose_membership' order by generation").fetchall()
        assert len(records)==2
        assert records[1][0]['origin'] == records[0][0]['origin']
        assert len(records[1][0]['member_ids'])==1 and len(records[1][0]['obligations'])==2
    assert completion.collect_purpose_completions(pg.now, connect=connect) == []
    execute_real_correction(connect, monkeypatch, ['PIG-SYNTHETIC-0001'])
    pg.now=datetime.now(timezone.utc)+timedelta(seconds=1)
    done=completion.collect_purpose_completions(pg.now, connect=connect)
    assert len(done)==1
    result=pg.cycle(done, deliver=lambda *_a,**_k: pytest.fail('completion cannot send'))
    assert result['success']
    with connect() as db:
        assert db.execute('select status,generation from app_private.oom_manager_cases').fetchone()==('completed',3)
        assert db.execute("select count(*) from app_private.oom_manager_case_events where event_type='completed'").fetchone()[0]==1


def test_postgres_uncapped_adoption_ignores_unrelated_correction_without_historical_claim(purpose_db, monkeypatch):
    pg, connect = purpose_db
    raw, _, _ = packet(now=pg.now)
    legacy=deepcopy(raw);legacy.pop('_purpose_membership');seed_legacy(pg,legacy)
    with connect() as db:
        db.execute("insert into public.pigs values('PIG-OTHER','OTHER','OTHER','Unknown','Active',true,now())")
        db.execute("insert into public.pig_weight_events values('W-OTHER','PIG-OTHER',current_date,12,now())")
    execute_real_correction(connect,monkeypatch,['PIG-OTHER'])
    pg.now=datetime.now(timezone.utc)+timedelta(seconds=1)
    with connect() as db, db.cursor() as cur:
        pg.store._reconcile(cur,worker.normalize_candidate(raw,now=pg.now),pg.now)
        record=db.execute("select event_payload->'purpose_membership' from app_private.oom_manager_case_events where event_payload ? 'purpose_membership'").fetchone()[0]
        assert record['origin']['scope']=='legacy_current_generation'
        assert record['origin']['proof_epoch']==record['obligations'][0]['required_since']


@pytest.mark.parametrize('count',[12,13])
def test_postgres_capped_legacy_does_not_adopt_unknown_membership(purpose_db,count):
    pg,connect=purpose_db
    raw,_,_=packet(count,now=pg.now)
    legacy=deepcopy(raw);legacy.pop('_purpose_membership');seed_legacy(pg,legacy)
    with connect() as db,db.cursor() as cur:
        assert pg.store._reconcile(cur,worker.normalize_candidate(raw,now=pg.now),pg.now)=='replayed'
        assert db.execute("select count(*) from app_private.oom_manager_case_events where event_payload ? 'purpose_membership'").fetchone()[0]==0


@pytest.mark.parametrize('state,offset',[('delegated',60),('delegated',-60),('open',60)])
def test_postgres_legacy_adoption_never_mutates_leased_or_delegated_case(purpose_db,state,offset):
    pg,connect=purpose_db
    raw,_,_=packet(now=pg.now);legacy=deepcopy(raw);legacy.pop('_purpose_membership');seed_legacy(pg,legacy)
    with connect() as db,db.cursor() as cur:
        db.execute("update app_private.oom_manager_cases set status=%s,assigned_worker_id='OTHER',lease_until=%s",(state,pg.now+timedelta(seconds=offset)))
        pg.store._reconcile(cur,worker.normalize_candidate(raw,now=pg.now),pg.now)
        assert db.execute("select count(*) from app_private.oom_manager_case_events where event_payload ? 'purpose_membership'").fetchone()[0]==0


def test_postgres_thirteen_members_actual_corrections_close_exactly_once(purpose_db,monkeypatch):
    pg,connect=purpose_db
    raw,_,_=packet(13,now=pg.now);pg.seed([raw])
    with connect() as db:
        for i in range(2,13):
            identity=f'PIG-SYNTHETIC-{i:04d}'
            db.execute("insert into public.pigs values(%s,%s,'COHORT-A','Unknown','Active',true,now())",(identity,f'S{i:04d}'))
            db.execute("insert into public.pig_weight_events values(%s,%s,current_date,12,now())",('W-'+identity,identity))
    execute_real_correction(connect,monkeypatch,[f'PIG-SYNTHETIC-{i:04d}' for i in range(13)])
    pg.now=datetime.now(timezone.utc)+timedelta(seconds=1)
    candidates=completion.collect_purpose_completions(pg.now,connect=connect)
    assert len(candidates)==1
    assert pg.cycle(candidates,deliver=lambda *_a,**_k:pytest.fail('no completion message'))['success']
    assert pg.cycle(candidates,deliver=lambda *_a,**_k:pytest.fail('no replay message'))['success']
    with connect() as db:
        assert db.execute("select count(*) from app_private.oom_manager_case_events where event_type='completed'").fetchone()[0]==1
        assert db.execute('select count(*) from public.operational_events').fetchone()[0]==13


def test_postgres_missing_new_generation_metadata_never_falls_back_to_short_refs(purpose_db,monkeypatch):
    pg,connect=purpose_db
    raw,_,_=packet(now=pg.now);raw.pop('_purpose_membership');pg.seed([raw])
    execute_real_correction(connect,monkeypatch,[f'PIG-SYNTHETIC-{i:04d}' for i in range(2)])
    pg.now=datetime.now(timezone.utc)+timedelta(seconds=1)
    assert completion.collect_purpose_completions(pg.now,connect=connect)==[]


@pytest.mark.parametrize('field,value',[('obligations',[None]),('members',[None]),
    ('origin',None),('member_count',True)])
def test_malformed_record_refuses_with_typed_error(field,value):
    _,case,_=packet()
    record=membership.build_record(case,generation=1,now=NOW)
    record[field]=value
    record['snapshot_digest']=membership._digest({k:v for k,v in record.items() if k!='snapshot_digest'})
    with pytest.raises(membership.PurposeMembershipError):
        membership.validate_record(record)


def test_expired_inherited_budget_cannot_open_connection():
    with pytest.raises(TimeoutError,match='purpose_membership_read_deadline'):
        membership.list_current_review_cases({},now=NOW,deadline_monotonic=0,
            connect=lambda:pytest.fail('must not connect after deadline'))


def test_postgres_membership_read_uses_borrowed_transaction_and_exact_lease_policy(purpose_db):
    from contextlib import nullcontext
    pg,connect=purpose_db
    raw,case,snapshot=packet(now=pg.now);pg.seed([raw])
    with connect() as db:
        db.execute('select 1')
        result=membership.load_current_membership(case['case_id'],snapshot,now=pg.now,
            connect=lambda:nullcontext(db),transaction_managed=True,lock_case=True,
            expected_generation=1,expected_evidence_digest=case['evidence_digest'])
        assert result['member_count']==2
        db.execute("update app_private.oom_manager_cases set status='delegated',assigned_worker_id='CYCLE-A',lease_until=%s",(pg.now+timedelta(minutes=1),))
        with pytest.raises(membership.PurposeMembershipError,match='leased'):
            membership.load_current_membership(case['case_id'],snapshot,now=pg.now,
                connect=lambda:nullcontext(db),transaction_managed=True)
        rows=membership.list_current_review_cases(snapshot,now=pg.now,connect=lambda:nullcontext(db),
            transaction_managed=True,owning_cycle_id='CYCLE-A')
        assert rows['unavailable_count']==0 and rows['cases'][0]['membership']['read_only_cycle_membership'] is True
        other=membership.list_current_review_cases(snapshot,now=pg.now,connect=lambda:nullcontext(db),
            transaction_managed=True,owning_cycle_id='CYCLE-B')
        assert other['unavailable_count']==1 and other['cases'][0]['available'] is False
        assert db.execute('select count(*) from app_private.oom_manager_case_events').fetchone()[0]==1


# The real family lifecycle creates these synthetic receipts; only the provider
# transport and protected-card fixture are local doubles. The overview suite
# separately covers the actual default worker + PostgreSQL lifecycle path.
from tests.test_oom_sakkie_purpose_overview import harness as overview_harness


def test_postgres_overview_coverage_is_append_only_exact_and_replay_quiet(pg, overview_harness):
    run, memory, raw, _, now = overview_harness
    pg.now=now; pg.seed(raw)
    outcome=run(); assert outcome['success'],outcome
    with pg.db() as db:
        before=db.execute('select case_id,generation,evidence_digest,last_delivery_digest,last_delivery_at from app_private.oom_manager_cases order by case_id').fetchall()
    covered=pg.store._record_purpose_overview_coverage(outcome,cycle_id='CYCLE-A',now=now)
    assert covered=={v['case_id'] for v in outcome['manifest']} and len(covered)==7
    assert pg.store._record_purpose_overview_coverage(outcome,cycle_id='CYCLE-A',now=now)==covered
    with pg.db() as db:
        assert db.execute('select case_id,generation,evidence_digest,last_delivery_digest,last_delivery_at from app_private.oom_manager_cases order by case_id').fetchall()==before
        events=db.execute("select event_payload from app_private.oom_manager_case_events where event_type='delivery_suppressed'").fetchall()
        assert len(events)==7 and all(v[0]['delivery_confirmed'] is False for v in events)
        assert db.execute("select count(*) from app_private.oom_manager_case_events where event_type='delivery_confirmed'").fetchone()[0]==0
    assert len(memory.sent)==1


@pytest.mark.parametrize('change',['generation','material','membership','foreign_lease','completed'])
def test_postgres_overview_coverage_refuses_changed_case_without_lending_receipt(pg,overview_harness,change):
    run,_,raw,_,now=overview_harness
    pg.now=now;pg.seed(raw)
    outcome=run();assert outcome['success'],outcome
    identity=outcome['manifest'][0]['case_id']
    with pg.db() as db:
        if change=='generation':db.execute('update app_private.oom_manager_cases set generation=generation+1 where case_id=%s',(identity,))
        elif change=='material':db.execute('update app_private.oom_manager_cases set evidence_digest=%s where case_id=%s',('a'*64,identity))
        elif change=='membership':
            with db.cursor() as cur:
                pg.store._event(cur,{'case_id':identity,'generation':1},'reassessment_scheduled',
                    now+timedelta(microseconds=1),purpose_membership={'membership_digest':'b'*64})
        elif change=='foreign_lease':db.execute("update app_private.oom_manager_cases set status='delegated',assigned_worker_id='OTHER',lease_until=%s where case_id=%s",(now+timedelta(minutes=1),identity))
        else:db.execute("update app_private.oom_manager_cases set status='completed' where case_id=%s",(identity,))
    covered=pg.store._record_purpose_overview_coverage(outcome,cycle_id='CYCLE-A',now=now)
    assert len(covered)==6 and identity not in covered
    with pg.db() as db:
        assert db.execute("select count(*) from app_private.oom_manager_case_events where case_id=%s and event_type='delivery_suppressed'",(identity,)).fetchone()[0]==0


def test_overview_forged_receipt_or_expired_parent_budget_cannot_open_connection(overview_harness):
    run,_,_,_,now=overview_harness
    outcome=run();assert outcome['success'],outcome
    store=worker.PostgresManagerCaseStore(connect_factory=lambda:pytest.fail('no DB admission'))
    forged=deepcopy(outcome);forged['receipt_events']=[]
    with pytest.raises(worker.ManagerCaseError,match='receipt_unproven'):
        store._record_purpose_overview_coverage(forged,cycle_id='CYCLE-A',now=now)
    with pytest.raises(TimeoutError,match='coverage_deadline'):
        store._record_purpose_overview_coverage(outcome,cycle_id='CYCLE-A',now=now,deadline_monotonic=0)


@pytest.mark.parametrize('old_delivery',[False,True])
def test_postgres_overview_unavailable_never_falls_back_to_individual_purpose_send(pg,old_delivery):
    raw,_,_=packet(now=pg.now);pg.seed([raw])
    if old_delivery:
        with pg.db() as db:
            db.execute('update app_private.oom_manager_cases set last_delivery_digest=evidence_digest,last_delivery_at=%s',(pg.now,))
    before=pg.now
    result=pg.cycle([raw],deliver=lambda *_a,**_k:pytest.fail('no per-case fallback'),
        purpose_overview=lambda *_a,**_k:{'success':False,'coverage':[], 'status':'quiet-or-unavailable','telegram_sends':0})
    assert result['success'] and result['deliveries_confirmed']==0
    assert result['exceptions']==(0 if old_delivery else 1)
    with pg.db() as db:
        row=db.execute('select last_delivery_digest,evidence_digest,last_delivery_at from app_private.oom_manager_cases').fetchone()
        assert row[0]==(row[1] if old_delivery else None)
        assert row[2]==(before if old_delivery else None)


def test_postgres_already_admitted_coverage_remains_quiet_when_later_summary_is_subset(pg,overview_harness):
    run,_,raw,_,now=overview_harness
    pg.now=now;pg.seed(raw)
    outcome=run();assert outcome['success'],outcome
    pg.store._record_purpose_overview_coverage(outcome,cycle_id='CYCLE-A',now=now)
    urgent=pg.value('protected',dedupe_key='herdmaster:retained-mortality:urgent',urgency='urgent',
        message_family='retained_protected_recovery',evidence_refs=['event:protected'],next_reassessment_at=now)
    dispatched=[]
    def deliver(case,**kwargs):
        assert case['dedupe_key']==urgent['dedupe_key']
        dispatched.append(case['case_id'])
        return {'success':True,'delivery_confirmed':False,'telegram_sends':0,'status':'urgent-checked'}
    result=pg.cycle([*raw,urgent],deliver=deliver,refresh=lambda case:urgent,
        purpose_overview=lambda *_a,**_k:{'success':True,'coverage':[], 'status':'no-new-groups','telegram_sends':0})
    assert result['success'] and result['exceptions']==0
    assert result['deliveries_confirmed']==0 and result['deliveries_suppressed']==5
    assert result['case_results'][0]['case_id']==dispatched[0] and len(dispatched)==1
    assert all(v['outcome_status']=='purpose_review_overview_covered' for v in result['case_results'][1:])
    with pg.db() as db:
        assert db.execute("select count(*) from app_private.oom_manager_cases where last_delivery_digest is not null").fetchone()[0]==0
        assert db.execute("select count(*) from app_private.oom_manager_case_events where event_payload ? 'purpose_overview_coverage'").fetchone()[0]==7


def test_postgres_urgent_provider_turn_precedes_real_family_overview(pg,overview_harness):
    run,memory,raw,_,now=overview_harness
    pg.now=now;order=[]
    real_send=memory.send
    def send(*args,**kwargs):
        order.append('overview-provider')
        return real_send(*args,**kwargs)
    memory.send=send
    urgent=pg.value('protected',dedupe_key='herdmaster:retained-mortality:urgent',urgency='urgent',
        message_family='retained_protected_recovery',evidence_refs=['event:protected'],next_reassessment_at=now)
    def urgent_provider(case,**kwargs):
        assert case['dedupe_key']==urgent['dedupe_key']
        order.append('urgent-provider')
        return {'success':True,'delivery_confirmed':False,'telegram_sends':0}
    result=pg.cycle([*raw,urgent],deliver=urgent_provider,refresh=lambda case:urgent,
        purpose_overview=lambda *_a,**_k:run())
    assert result['success'] and result['exceptions']==0,result
    assert order==['urgent-provider','overview-provider']
    assert result['purpose_overview']['covered_cases']==7
    assert result['purpose_overview']['telegram_sends']==1
    assert result['deliveries_confirmed']==0


def test_postgres_overview_own_lease_expiring_during_queries_cannot_admit_coverage(pg,overview_harness,monkeypatch):
    run,_,raw,_,now=overview_harness
    pg.now=now;pg.seed(raw)
    outcome=run();assert outcome['success'],outcome
    identity=outcome['manifest'][0]['case_id']
    with pg.db() as db:
        db.execute("update app_private.oom_manager_cases set status='delegated',assigned_worker_id='CYCLE-A',lease_until=%s where case_id=%s",(now+timedelta(seconds=2),identity))
    clock=[now]
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return clock[0]
    original=worker.ReadBudgetCursor
    class DelayedCursor(original):
        def execute(self,statement,params=None):
            result=super().execute(statement,params)
            if "select case_id,event_payload->'purpose_overview_coverage'" in statement:
                clock[0]=now+timedelta(seconds=3)
            return result
    monkeypatch.setattr(worker,'datetime',Clock)
    monkeypatch.setattr(worker,'ReadBudgetCursor',DelayedCursor)
    covered=pg.store._record_purpose_overview_coverage(outcome,cycle_id='CYCLE-A',now=now)
    assert len(covered)==6 and identity not in covered
    with pg.db() as db:
        assert db.execute("select count(*) from app_private.oom_manager_case_events where case_id=%s and event_payload ? 'purpose_overview_coverage'",(identity,)).fetchone()[0]==0
