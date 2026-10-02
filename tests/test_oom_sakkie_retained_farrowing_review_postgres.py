"""Exact retained farrowing handoff: real isolated PostgreSQL, no provider calls."""
import json
import time
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from unittest.mock import Mock

import pytest
from psycopg.types.json import Jsonb

from tests.test_oom_sakkie_retained_report_recovery_postgres import (
    store, retain, collect, set_current_recipient_policy, URL)
from modules.oom_sakkie import manager_case_sources as sources
from modules.oom_sakkie import herdmaster_retained_recovery_runtime as recovery
from modules.oom_sakkie import general_manager_worker as worker
from modules.oom_sakkie import family_message_lifecycle as family
from modules.oom_sakkie import bounded_postgres_read as bounded
from modules.oom_sakkie.protected_action_claims import canonical_preview_digest

pytestmark = pytest.mark.skipif(not URL, reason='explicit disposable PostgreSQL URL required')
NOW = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
OLD = NOW-timedelta(days=30)
MISSION = 'OOM-HERD-LITTER-SYNTHETIC'
KEY = recovery.FARROWING_KEY+MISSION
KIND = recovery.FARROWING_KIND


@pytest.fixture
def journey(store, monkeypatch):
    set_current_recipient_policy(monkeypatch, 'manager')
    monkeypatch.setenv('DATABASE_URL', URL)
    monkeypatch.setattr(sources, 'connect_bounded_read', lambda:store(True))
    monkeypatch.setattr(bounded, 'connect_bounded_rootline_postgres', lambda **kw:store(kw.get('read_only',True)))
    preview = {'sow_pig_id':'SOW-A', 'sow_display_name':'Synthetic sow',
        'farrowing_date':'2026-09-01', 'principal_id':'42','provider_message_id':'101',
        'counts':{'total_born':12,'born_alive':11,'stillborn':1,'mummified':0,'died_after_live_birth':0}}
    digest = canonical_preview_digest(KIND,preview)
    with store() as db, db.cursor() as cur:
        # The fixture owns only these test action kinds; production schema is unchanged.
        cur.execute('alter table app_private.oom_protected_action_claims drop constraint oom_protected_action_claims_action_kind_check')
        cur.execute("alter table app_private.oom_protected_action_claims add constraint oom_protected_action_claims_action_kind_check check (action_kind in ('mortality','grouped_weights','herdmaster_record_farrowing_litter'))")
        for token, mission, card, state in [('original',MISSION,'100','delivery_confirmed'),
                ('recovery',MISSION+'-RECOVERY-ABC',None,'claim_created')]:
            cur.execute("""insert into app_private.oom_protected_action_claims
                (callback_token,action_kind,owner_user_id,private_chat_id,mission_id,provider_message_id,
                 preview_card_message_id,preview_digest,evidence_generation,preview_payload,status,expires_at,
                 created_at,delivery_state,provider_accepted_at,delivery_confirmed_at)
                values(%s,%s,'42','42',%s,'101',%s,%s,'OLD',%s,'active',%s,%s,%s,%s,%s)""",
                (token,KIND,mission,card,digest,Jsonb(preview),OLD+timedelta(minutes=15),
                 OLD if card else OLD+timedelta(minutes=1),state,OLD if card else None,OLD if card else None))
    selected=retain(store,KEY,[f'mission:{MISSION}','provider_message:101','sow:SOW-A','canonical_effect:none'])
    return {'store':store,'selected':selected,'preview':preview,'monkeypatch':monkeypatch}


def snapshot(store):
    with store(True) as db, db.cursor() as cur:
        cur.execute('select to_jsonb(c) from app_private.oom_protected_action_claims c order by callback_token')
        claims=cur.fetchall()
        cur.execute('select to_jsonb(p) from public.pigs p order by pig_id')
        pigs=cur.fetchall()
        cur.execute('select to_jsonb(l) from public.litters l order by litter_id')
        return claims,pigs,cur.fetchall()


def ready(j):
    rows=collect(j['store'],NOW,claimed_cases=[j['selected']])
    assert len(rows)==1
    normalized=worker.normalize_candidate(rows[0],now=NOW)
    manager=worker.PostgresManagerCaseStore(connect_factory=j['store'])
    with j['store']() as db, db.cursor() as cur:
        manager._reconcile(cur,normalized,NOW)
        cur.execute('select generation from app_private.oom_manager_cases where case_id=%s',(j['selected']['case_id'],))
        generation=cur.fetchone()[0]
    return {**normalized,'case_id':j['selected']['case_id'],'generation':generation}


def test_exact_refresh_routes_without_wide_herd_and_keeps_report_attribution(journey,monkeypatch):
    monkeypatch.setattr(sources,'_herdmaster',lambda *_:pytest.fail('wide herd refresh'))
    selected={**journey['selected'],'evidence_refs':['provider_message:WRONG'],
              'message_family':'forged','status':'completed'}
    before=snapshot(journey['store'])
    rows=sources.collect_manager_refresh_snapshot(now=NOW,cases=[selected])
    value=rows[(KEY,'HERDMASTER')]
    assert value['message_family']==recovery.FARROWING_REVIEW_FAMILY
    assert 'Historical UNCONFIRMED' in value['summary']
    for text in ['total born 12','born alive 11','stillborn 1','mummified 0','died after live birth 0']:
        assert text in value['summary']
    assert 'older report from the farm reporter' in value['summary']
    assert 'verified sow, date and birth counts' in value['next_action']
    assert 'terminal_state' not in value
    assert snapshot(journey['store'])==before


@pytest.mark.parametrize('change',[{'case_id':'wrong'}, {'dedupe_key':KEY+'X'}, {'specialist':'ROOTLINE'}])
def test_exact_selector_cannot_cross_case_key_or_specialist(journey,change):
    selector={**journey['selected'],**change}
    if change.get('specialist'):
        with pytest.raises(ValueError): collect(journey['store'],NOW,claimed_cases=[selector])
    else:
        assert collect(journey['store'],NOW,claimed_cases=[selector])==[]


@pytest.mark.parametrize('ref',['mission:OTHER','provider_message:999','sow:OTHER'])
def test_durable_original_refs_must_bind_exactly(journey,ref):
    prefix=ref.split(':')[0]+':'
    with journey['store']() as db,db.cursor() as cur:
        cur.execute('select evidence_refs from app_private.oom_manager_cases where case_id=%s',(journey['selected']['case_id'],))
        refs=[r for r in cur.fetchone()[0] if not r.startswith(prefix)]+[ref]
        cur.execute('update app_private.oom_manager_cases set evidence_refs=%s where case_id=%s',
                    (Jsonb(refs),journey['selected']['case_id']))
    assert collect(journey['store'],NOW,claimed_cases=[journey['selected']])==[]


@pytest.mark.parametrize('assignment',[
    "status='cancelled'", "status='completed'", "status='changed'", "status='executing'",
    "private_chat_id='999'", "owner_user_id='999'", "provider_message_id='999'",
    "preview_digest=repeat('f',64)", "result_payload='{}'::jsonb",
    "confirmation_provider_message_id='200'", "delivery_state='claim_created'",
    "provider_accepted_at=null", "delivery_ambiguous_at=now()",
])
def test_changed_original_cannot_be_presented(journey,assignment):
    case=ready(journey)
    with journey['store']() as db,db.cursor() as cur:
        cur.execute('update app_private.oom_protected_action_claims set '+assignment+" where callback_token='original'")
    assert recovery.build_retained_farrowing_owner_review(case,now=NOW)['success'] is False


@pytest.mark.parametrize('assignment',[
    "status='cancelled'", "status='completed'", "owner_user_id='999'", "private_chat_id='999'",
    "mission_id='UNRELATED'", "preview_card_message_id='201'", "delivery_attempt_id='attempt'",
    "delivery_result='{}'::jsonb", "expires_at='2027-01-01'::timestamptz",
])
def test_later_or_foreign_claim_is_contained_without_overriding_it(journey,assignment):
    with journey['store']() as db,db.cursor() as cur:
        cur.execute('update app_private.oom_protected_action_claims set '+assignment+" where callback_token='recovery'")
    before=snapshot(journey['store'])
    rows=collect(journey['store'],NOW,claimed_cases=[journey['selected']])
    assert not rows or all(r['message_family']=='herdmaster_disposition' and not r.get('terminal_state') for r in rows)
    assert snapshot(journey['store'])==before


@pytest.mark.parametrize('mutation',['litter','off_farm','conversation','new_owner_question','multiple_recovery'])
def test_new_canonical_or_source_authority_prevents_handoff(journey,mutation):
    with journey['store']() as db,db.cursor() as cur:
        if mutation=='litter':
            cur.execute("insert into public.litters values('NEW','SOW-A','2026-09-01','Active')")
        elif mutation=='off_farm':
            cur.execute("update public.pigs set on_farm=false where pig_id='SOW-A'")
        elif mutation in {'conversation','new_owner_question'}:
            cur.execute("""insert into public.sam_live_stock_conversation_review_events
                (review_event_id,event_source,review_json) values('NEW','oom_sakkie_farrowing_litter',%s)""",
                (Jsonb({'farrowing_litter':({'provider_message_id':'101','context_id':MISSION}
                    if mutation=='conversation' else {'provider_message_id':'9001','context_id':'NEW',
                        'owner_user_id':'900','private_chat_id':'900','sow_refs':['SOW-A'], 'facts':{'farrowing_date':'2026-09-01'}})}),))
        else:
            cur.execute("""insert into app_private.oom_protected_action_claims
                (callback_token,action_kind,owner_user_id,private_chat_id,mission_id,provider_message_id,
                 preview_digest,evidence_generation,preview_payload,status,expires_at)
                select 'third',action_kind,owner_user_id,private_chat_id,mission_id||'-THIRD',provider_message_id,
                 preview_digest,evidence_generation,preview_payload,status,expires_at
                from app_private.oom_protected_action_claims where callback_token='recovery'""")
    rows=collect(journey['store'],NOW,claimed_cases=[journey['selected']])
    assert not rows or all(r['message_family']=='herdmaster_disposition' and not r.get('terminal_state') for r in rows)


def test_real_family_delivery_owner_only_replay_no_claim_or_farm_changes(journey,monkeypatch):
    case=ready(journey); before=snapshot(journey['store']); sends=[]
    def send(chat,text,**kwargs):
        sends.append((chat,text,kwargs))
        assert chat=='900' and not kwargs.get('reply_markup')
        return {'success':True,'telegram_message_id':'700','provider_timestamp':NOW.isoformat()}
    monkeypatch.setattr(family,'_send_telegram',send)
    monkeypatch.setattr(family,'_edit_telegram',lambda *_a,**_k:pytest.fail('duplicate edit'))
    first=worker.deliver_farm_manager_case(case,now=NOW)
    replay=worker.deliver_farm_manager_case(case,now=NOW)
    assert first['success'] is True and first['delivery_confirmed'] is True, first
    assert replay['success'] is True and replay['delivery_confirmed'] is False
    assert len(sends)==1 and 'Onbevestig — nog nie aangeteken nie.' in sends[0][1]
    assert 'nog nie aangeteken nie' in sends[0][1].casefold()
    assert snapshot(journey['store'])==before
    with journey['store'](True) as db,db.cursor() as cur:
        cur.execute("select review_json->'family_message_lifecycle' from public.sam_live_stock_conversation_review_events where event_source='oom_sakkie_family_message_lifecycle'")
        rows=[r[0] for r in cur.fetchall()]
    assert rows and {r['owner_user_id'] for r in rows}=={'900'}
    assert {r['card_mission_id'] for r in rows}=={case['case_id']}
    assert all(not r.get('callback_token') for r in rows)


@pytest.mark.parametrize('drift',['owner','source','generation','lease'])
def test_provider_boundary_revalidates_owner_and_source_after_family_reads(journey,monkeypatch,drift):
    case=ready(journey); original=family._event_store; changed=[]
    def store_events(action,identity,payload):
        value=original(action,identity,payload)
        if action=='load' and not changed:
            changed.append(True)
            if drift=='owner': monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID','42')
            else:
                with journey['store']() as db,db.cursor() as cur:
                    if drift=='lease':
                        cur.execute("update app_private.oom_manager_cases set status='delegated',assigned_worker_id='another-cycle',lease_until=%s where case_id=%s",(NOW+timedelta(minutes=5),case['case_id']))
                    elif drift=='generation':
                        cur.execute('update app_private.oom_manager_cases set generation=generation+1 where case_id=%s',(case['case_id'],))
                    else:
                        cur.execute("update app_private.oom_protected_action_claims set status='cancelled' where callback_token='original'")
        return value
    monkeypatch.setattr(family,'_event_store',store_events)
    monkeypatch.setattr(family,'_send_telegram',lambda *_a,**_k:pytest.fail('stale send'))
    value=worker.deliver_farm_manager_case(case,now=NOW)
    assert value['success'] is False and value['delivery_confirmed'] is False


def test_deadline_and_database_timeout_never_send(journey,monkeypatch):
    case=ready(journey)
    monkeypatch.setattr(family,'_send_telegram',lambda *_a,**_k:pytest.fail('timed out send'))
    value=worker.deliver_farm_manager_case(case,now=NOW,deadline_monotonic=time.monotonic()+0.01)
    assert value['success'] is False and value['status']=='manager_cycle_deadline_deferred'
    def fail(): raise TimeoutError('private diagnostic')
    monkeypatch.setattr(sources,'connect_bounded_read',fail)
    value=worker.deliver_farm_manager_case(case,now=NOW)
    assert value['success'] is False and 'private diagnostic' not in str(value)


def test_full_worker_two_natural_shape_cycles_wait_for_owner_without_exceptions(journey,monkeypatch):
    case=ready(journey); before=snapshot(journey['store']); sends=[]
    monkeypatch.setattr(family,'_send_telegram',lambda chat,text,**kw:
        sends.append(chat) or {'success':True,'telegram_message_id':'701','provider_timestamp':NOW.isoformat()})
    monkeypatch.setattr(worker,'build_scheduled_brain_guard_audit',lambda **kw:{'passed':True})
    manager=worker.PostgresManagerCaseStore(connect_factory=journey['store'])
    for name in ('_herdmaster_advisories','_rootline','_herdmaster','_sam','_beacon','_delivery_gaps','_runtime'):
        monkeypatch.setattr(sources,name,lambda *_:[])
    monkeypatch.setattr('modules.telemetry.rootline_mixer_readiness_observer.collect_mixer_readiness',lambda **kw:[])
    class Clock(datetime):
        current=NOW
        @classmethod
        def now(cls,tz=None): return cls.current
    monkeypatch.setattr(worker,'datetime',Clock)
    monkeypatch.setattr(recovery,'datetime',Clock)
    for offset in [31,62]:
        now=Clock.current=NOW+timedelta(minutes=offset)
        outcome=worker.run_general_manager_cycle(now=now,store=manager,source_revision='synthetic',
            deliver=worker.deliver_farm_manager_case)
        assert outcome['success'] is True
    assert sends==['900'], json.dumps(outcome,default=str)
    with journey['store'](True) as db,db.cursor() as cur:
        cur.execute('select status,generation,last_delivery_digest,evidence_digest from app_private.oom_manager_cases where case_id=%s',(case['case_id'],))
        status,generation,delivered,digest=cur.fetchone()
        assert status=='waiting_reassessment' and generation==case['generation'] and delivered==digest
        cur.execute("select count(*) from app_private.oom_manager_case_events where case_id=%s and event_type='exception'",(case['case_id'],))
        assert cur.fetchone()[0]==0
    assert snapshot(journey['store'])==before


@pytest.mark.parametrize('new_evidence',['owner_report','canonical_litter'])
def test_following_owner_journey_parks_same_case_over_two_cycles(journey,monkeypatch,new_evidence):
    case=ready(journey)
    monkeypatch.setattr(family,'_send_telegram',lambda *_a,**_k:
        {'success':True,'telegram_message_id':'702','provider_timestamp':NOW.isoformat()})
    assert worker.deliver_farm_manager_case(case,now=NOW)['delivery_confirmed'] is True
    with journey['store']() as db,db.cursor() as cur:
        if new_evidence=='canonical_litter':
            cur.execute("insert into public.litters values('NEW-BIRTH','SOW-A','2026-09-01','Active')")
        else:
            cur.execute("""insert into public.sam_live_stock_conversation_review_events
                (review_event_id,event_source,review_json) values('OWNER-NEW','oom_sakkie_farrowing_litter',%s)""",
                (Jsonb({'farrowing_litter':{'context_id':'NEW-CONTEXT','provider_message_id':'9001',
                    'owner_user_id':'900','private_chat_id':'900','sow_refs':['SOW-A'],
                    'facts':{'farrowing_date':'2026-09-01'},'question':'Current owner detail'}}),))
    before=snapshot(journey['store'])
    watch=collect(journey['store'],NOW,claimed_cases=[journey['selected']])
    assert len(watch)==1 and watch[0]['message_family']=='herdmaster_disposition'
    assert 'terminal_state' not in watch[0]
    assert any(r.startswith('retained_farrowing_source:') for r in watch[0]['evidence_refs'])
    monkeypatch.setattr(family,'_send_telegram',lambda *_a,**_k:pytest.fail('second card'))
    monkeypatch.setattr(family,'_edit_telegram',lambda *_a,**_k:pytest.fail('unneeded edit'))
    monkeypatch.setattr(worker,'build_scheduled_brain_guard_audit',lambda **kw:{'passed':True})
    for name in ('_herdmaster_advisories','_rootline','_herdmaster','_sam','_beacon','_delivery_gaps','_runtime'):
        monkeypatch.setattr(sources,name,lambda *_:[])
    monkeypatch.setattr('modules.telemetry.rootline_mixer_readiness_observer.collect_mixer_readiness',lambda **kw:[])
    class Clock(datetime):
        current=NOW
        @classmethod
        def now(cls,tz=None): return cls.current
    monkeypatch.setattr(worker,'datetime',Clock)
    monkeypatch.setattr(recovery,'datetime',Clock)
    manager=worker.PostgresManagerCaseStore(connect_factory=journey['store'])
    for offset in [31,62,93]:
        now=Clock.current=NOW+timedelta(minutes=offset)
        outcome=worker.run_general_manager_cycle(now=now,store=manager,source_revision='synthetic',
            deliver=worker.deliver_farm_manager_case)
        assert outcome['success'] is True and outcome['exceptions']==0, outcome
    with journey['store'](True) as db,db.cursor() as cur:
        cur.execute('select status,generation,evidence_refs from app_private.oom_manager_cases where case_id=%s',(case['case_id'],))
        status,generation,refs=cur.fetchone()
        assert status=='waiting_reassessment' and generation==case['generation']+1
        assert 'manager_message_family:herdmaster_disposition' in refs
        cur.execute("select count(*) from app_private.oom_manager_case_events where case_id=%s and event_type in ('completed','exception')",(case['case_id'],))
        assert cur.fetchone()[0]==0
    assert snapshot(journey['store'])==before


def test_real_postgres_lock_timeout_is_contained_before_delivery(journey,monkeypatch):
    case=ready(journey)
    monkeypatch.setattr(sources,'RETAINED_REPORT_READ_SECONDS',0.15)
    monkeypatch.setattr(family,'_send_telegram',lambda *_a,**_k:pytest.fail('blocked read send'))
    with journey['store']() as blocked,blocked.cursor() as cur:
        cur.execute('lock table app_private.oom_protected_action_claims in access exclusive mode')
        started=time.monotonic()
        result=worker.deliver_farm_manager_case(case,now=NOW)
        elapsed=time.monotonic()-started
    assert result['success'] is False and result['delivery_confirmed'] is False
    assert result['status']=='retained_farrowing_owner_review_unavailable' and elapsed<2


def test_legacy_preview_missing_identity_display_fields_uses_stored_claim_and_canonical_sow(journey):
    preview=deepcopy(journey['preview'])
    for key in ('principal_id','provider_message_id','sow_display_name'): preview.pop(key)
    with journey['store']() as db,db.cursor() as cur:
        cur.execute('update app_private.oom_protected_action_claims set preview_payload=%s,preview_digest=%s',
                    (Jsonb(preview),canonical_preview_digest(KIND,preview)))
    row=collect(journey['store'],NOW,claimed_cases=[journey['selected']])[0]
    assert 'for Linda on 2026-09-01' in row['summary']
    assert row['message_family']==recovery.FARROWING_REVIEW_FAMILY


def test_concurrent_default_worker_cycles_deliver_one_owner_card(journey,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    case=ready(journey); before=snapshot(journey['store']); sends=[]
    monkeypatch.setattr(family,'_send_telegram',lambda chat,text,**kw:
        sends.append(chat) or {'success':True,'telegram_message_id':'703','provider_timestamp':NOW.isoformat()})
    monkeypatch.setattr(worker,'build_scheduled_brain_guard_audit',lambda **kw:{'passed':True})
    for name in ('_herdmaster_advisories','_rootline','_herdmaster','_sam','_beacon','_delivery_gaps','_runtime'):
        monkeypatch.setattr(sources,name,lambda *_:[])
    monkeypatch.setattr('modules.telemetry.rootline_mixer_readiness_observer.collect_mixer_readiness',lambda **kw:[])
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None): return NOW+timedelta(minutes=31)
    monkeypatch.setattr(worker,'datetime',Clock)
    monkeypatch.setattr(recovery,'datetime',Clock)
    barrier=Barrier(2)
    def run():
        barrier.wait(timeout=5)
        return worker.run_general_manager_cycle(now=Clock.now(),source_revision='synthetic',
            store=worker.PostgresManagerCaseStore(connect_factory=journey['store']),
            deliver=worker.deliver_farm_manager_case)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=[future.result(timeout=20) for future in [pool.submit(run),pool.submit(run)]]
    assert all(r['success'] is True and r['exceptions']==0 for r in results), results
    assert sends==['900'] and sum(r['deliveries_confirmed'] for r in results)==1
    assert snapshot(journey['store'])==before
