"""Real PostgreSQL producer/store proof; no provider or hardware is invoked."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from modules.oom_sakkie import general_manager_worker as worker
from modules.oom_sakkie import manager_case_sources as sources
from tests.test_oom_sakkie_purpose_decision import pg
from tests.test_oom_sakkie_rootline_notification_followthrough import evidence


@pytest.fixture
def rootline_db(pg,monkeypatch):
    import psycopg
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID','42')
    monkeypatch.setenv('ROOTLINE_REASSESSMENT_OWNER_USER_ID','42')
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS','42')
    from tests.test_oom_sakkie_general_manager_postgres import _IsolatedConnection,_IsolatedCursor,URL
    class Cursor(_IsolatedCursor):
        def execute(self,sql,params=None):
            return super().execute(sql.replace('public.',self.owner.schema+'.'),params)
    class Connection(_IsolatedConnection):
        def cursor(self): return Cursor(self.connection.cursor(),self.owner)
    def connect(): return Connection(psycopg.connect(URL,options='-c statement_timeout=10000'),pg)
    with connect() as db:
        db.execute((Path(__file__).parents[1]/'supabase/migrations/202607070001_create_sam_live_stock_conversation_review_events.sql').read_text())
    monkeypatch.setattr(sources,'connect_bounded_read',connect)
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None): return pg.now.astimezone(tz) if tz else pg.now.replace(tzinfo=None)
    monkeypatch.setattr(worker,'datetime',Clock)
    monkeypatch.setattr(worker,'build_scheduled_brain_guard_audit',lambda **kwargs:{'passed':True})
    return pg,connect


def append(db_factory,row):
    with db_factory() as db:
        db.execute('''insert into public.sam_live_stock_conversation_review_events
            (review_event_id,chatwoot_conversation_id,event_source,review_json,created_at)
            values(%s,%s,'oom_sakkie_rootline_reassessment',%s::jsonb,%s)''',
            (row[0],row[2]['identity'],json.dumps({'rootline_reassessment':row[2]}),row[1]))


def seed(rootline_db):
    pg,connect=rootline_db; observation,delivery=evidence(pg.now)
    append(connect,observation)
    raw=sources._rootline(pg.now)[0]
    pg.seed([raw])
    return observation,delivery,raw


def run(pg,collector=None,deliver=None):
    return worker.run_general_manager_cycle(now=pg.now,source_revision='synthetic-rootline-followthrough',
        store=pg.store,collectors=(collector or sources._rootline,),
        deliver=deliver or (lambda *args,**kwargs:pytest.fail('notification completion must not send')))


def case(pg):
    with pg.db() as db:
        return db.execute('''select case_id,generation,status,evidence_digest,last_delivery_digest,last_delivery_at,
            assigned_worker_id,lease_until from app_private.oom_manager_cases where dedupe_key='rootline:current-plan' ''').fetchone()


def completions(pg):
    with pg.db() as db:
        return db.execute("select event_payload from app_private.oom_manager_case_events where event_type='completed' order by occurred_at").fetchall()


def test_three_post_completion_default_reads_are_one_transition_and_six_siblings_unchanged(rootline_db):
    pg,connect=rootline_db; observation,delivery,raw=seed(rootline_db)
    siblings=[pg.value('purpose-'+str(i),dedupe_key='herdmaster:purpose-review:SYNTHETIC-'+str(i),
        message_family='purpose_review',next_reassessment_at=(pg.now+timedelta(days=1)).isoformat()) for i in range(6)]
    pg.seed(siblings)
    with pg.db() as db:
        db.execute('''update app_private.oom_manager_cases set last_delivery_digest=evidence_digest,
            last_delivery_at=%s,status='waiting_reassessment' ''',(pg.now-timedelta(minutes=1),))
        before_siblings=db.execute("select row_to_json(m) from app_private.oom_manager_cases m where specialist='HERDMASTER' order by case_id").fetchall()
    original=case(pg)
    append(connect,delivery)
    outcomes=[run(pg)]
    first=case(pg); first_events=completions(pg)
    for index in (1,2):
        pg.now+=timedelta(minutes=5)
        if index==2:
            fresh=deepcopy(observation[2]);fresh.update(identity='OOM-ROOTLINE-OBS-FRESH',
                event_id='OOM-ROOTLINE-OBS-FRESH-RECORD_OBSERVATION',result_id='RESULT-FRESH',evidence_generation='GEN-FRESH')
            append(connect,(fresh['event_id'],pg.now-timedelta(seconds=1),fresh))
        outcomes.append(run(pg))
    assert first[0]==original[0] and first[1]==original[1]+1 and first[2]=='completed'
    assert first[4:6]==original[4:6] and first[6:]==(None,None)
    assert case(pg)==first and completions(pg)==first_events and len(first_events)==1
    proof=first_events[0][0]
    assert proof['prior_generation']==original[1] and proof['prior_evidence_digest']==original[3]
    assert proof['rootline_delivery_proof']['delivery']['event_id']==delivery[0]
    assert proof['rootline_delivery_proof']['delivery']['provider_message_id']=='12345'
    assert proof['rootline_delivery_proof']['observation']['event_id']==observation[0]
    assert proof['rootline_delivery_proof']['retained']['evidence_refs']==worker.normalize_candidate(raw,now=pg.now)['evidence_refs']
    assert all(v['exceptions']==0 and v['deliveries_confirmed']==0 for v in outcomes)
    with pg.db() as db:
        assert db.execute("select row_to_json(m) from app_private.oom_manager_cases m where specialist='HERDMASTER' order by case_id").fetchall()==before_siblings


def test_fresher_observation_same_material_existing_receipt_completes_original_case(rootline_db):
    pg,connect=rootline_db; observation,delivery,_=seed(rootline_db);append(connect,delivery)
    pg.now+=timedelta(minutes=5)
    fresh=deepcopy(observation[2]);fresh.update(identity='OOM-ROOTLINE-OBS-NEW',
        event_id='OOM-ROOTLINE-OBS-NEW-RECORD_OBSERVATION',result_id='NEW-RESULT',evidence_generation='NEW-GENERATION')
    append(connect,(fresh['event_id'],pg.now-timedelta(seconds=1),fresh))
    assert run(pg)['exceptions']==0
    assert case(pg)[2]=='completed'
    proof=completions(pg)[0][0]['rootline_delivery_proof']
    assert proof['delivery']['result_id']!=proof['observation']['result_id']
    assert proof['delivery']['material_digest']==proof['observation']['material_digest']


@pytest.mark.parametrize('change',['material','owner','chat','date','provider','ambiguous','future'])
def test_real_read_does_not_complete_conflicting_or_missing_receipt(rootline_db,change):
    pg,connect=rootline_db; _,delivery,_=seed(rootline_db); delivery=list(delivery)
    if change=='material': delivery[2]['material_digest']='b'*64
    elif change=='owner': delivery[2]['owner_user_id']='43'
    elif change=='chat': delivery[2]['chat_id']='43'
    elif change=='date': delivery[2]['operating_date']='2026-01-01'
    elif change=='provider': delivery[2]['provider_message_id']=''
    elif change=='ambiguous': delivery[2]['delivery_state']='ambiguous'
    elif change=='future': delivery[1]=pg.now+timedelta(hours=1)
    append(connect,delivery)
    run(pg)
    assert case(pg)[2]!='completed' and completions(pg)==[]


def test_latest_ambiguous_state_does_not_borrow_older_confirmed_receipt(rootline_db):
    pg,connect=rootline_db; _,delivery,_=seed(rootline_db);append(connect,delivery)
    ambiguous=deepcopy(delivery[2]);ambiguous.update(event_id='SYNTHETIC-AMBIGUOUS',delivery_state='ambiguous')
    append(connect,(ambiguous['event_id'],pg.now,ambiguous))
    run(pg)
    assert case(pg)[2]!='completed' and completions(pg)==[]


@pytest.mark.parametrize('change',['generation','digest','refs'])
def test_case_changed_after_source_snapshot_cannot_close(rootline_db,change):
    pg,connect=rootline_db;_,delivery,_=seed(rootline_db);append(connect,delivery)
    terminal=sources._rootline(pg.now)[0]
    with pg.db() as db:
        if change=='generation': db.execute("update app_private.oom_manager_cases set generation=generation+1")
        elif change=='digest': db.execute("update app_private.oom_manager_cases set evidence_digest=%s",('b'*64,))
        else: db.execute("update app_private.oom_manager_cases set evidence_refs=evidence_refs||'[\"newer:fact\"]'::jsonb")
    result=pg.cycle([terminal])
    assert result['candidates_changed']==0
    assert case(pg)[2]!='completed' and completions(pg)==[]


def test_foreign_active_lease_blocks_terminal_then_expired_delegation_recovers_safely(rootline_db):
    pg,connect=rootline_db;_,delivery,_=seed(rootline_db);append(connect,delivery)
    with pg.db() as db:
        db.execute('''update app_private.oom_manager_cases set status='delegated',assigned_worker_id='foreign',
            lease_until=%s,next_reassessment_at=%s''',(pg.now+timedelta(minutes=1),pg.now))
    assert run(pg)['cases_claimed']==0
    assert case(pg)[2]=='delegated' and completions(pg)==[]
    pg.now+=timedelta(minutes=2)
    deferred=run(pg)
    assert deferred['case_results'][0]['outcome_status']=='manager_delivery_refreshed_generation_deferred'
    assert case(pg)[2]=='waiting_reassessment' and completions(pg)==[]
    pg.now+=timedelta(minutes=5)
    assert run(pg)['exceptions']==0
    assert case(pg)[2]=='completed' and len(completions(pg))==1


def test_receipt_arriving_between_collection_and_refresh_completes_owned_claim(rootline_db):
    pg,connect=rootline_db;_,delivery,_=seed(rootline_db)
    pg.now+=timedelta(minutes=5);calls=[]
    def _rootline(now):
        rows=sources._rootline(now);calls.append(1)
        if len(calls)==1:append(connect,delivery)
        return rows
    outcome=run(pg,collector=_rootline)
    assert len(calls)==2 and outcome['cases_claimed']==1
    assert outcome['case_results'][0]['outcome_status']=='manager_case_completed_from_current_evidence'
    assert outcome['exceptions']==0 and case(pg)[2]=='completed' and len(completions(pg))==1


def test_real_read_failure_keeps_case_and_counts_sanitized_failure(rootline_db,monkeypatch):
    pg,_=rootline_db;seed(rootline_db);pg.now+=timedelta(minutes=5)
    def failed():raise TimeoutError('synthetic private connection detail')
    monkeypatch.setattr(sources,'connect_bounded_read',failed)
    result=run(pg)
    assert result['exceptions']==1 and case(pg)[2]=='waiting_reassessment' and completions(pg)==[]
    with pg.db() as db:
        event=db.execute("select event_payload from app_private.oom_manager_case_events where event_type='exception'").fetchone()[0]
    assert event['outcome_status']=='manager_specialist_processing_exception_contained'
    assert event['failure_kind']=='collector:rootline:TimeoutError'
    assert 'private connection' not in json.dumps(event)


def test_material_change_after_completion_reopens_once_without_erasing_receipt(rootline_db):
    pg,connect=rootline_db;observation,delivery,_=seed(rootline_db);append(connect,delivery);run(pg)
    closed=case(pg);old_events=completions(pg)
    pg.now+=timedelta(minutes=5)
    changed=deepcopy(observation[2]);changed.update(identity='OOM-ROOTLINE-OBS-CHANGED',
        event_id='OOM-ROOTLINE-OBS-CHANGED-RECORD_OBSERVATION',material_digest='b'*64,
        result_id='CHANGED-RESULT',evidence_generation='CHANGED-GENERATION')
    append(connect,(changed['event_id'],pg.now-timedelta(seconds=1),changed))
    run(pg);opened=case(pg)
    assert opened[0]==closed[0] and opened[1]==closed[1]+1 and opened[2]=='open'
    assert completions(pg)==old_events
    pg.now+=timedelta(minutes=5)
    result=run(pg,deliver=lambda *args,**kwargs:{'success':True,'status':'synthetic_no_send','delivery_confirmed':False})
    assert case(pg)[1]==opened[1] and result['candidate_replays']==1 and completions(pg)==old_events


def test_foreign_owner_pair_cannot_close_legacy_case_or_replace_current_observation(rootline_db):
    pg,connect=rootline_db;_,delivery,_=seed(rootline_db)
    with pg.db() as db:
        db.execute("update app_private.oom_manager_cases set evidence_refs='[\"event:legacy-no-recipient\"]'::jsonb")
    original=case(pg)
    observation,_=evidence(pg.now)
    for row in (observation,delivery):row[2].update(owner_user_id='43',chat_id='43')
    foreign=deepcopy(observation[2]);foreign.update(identity='FOREIGN-OBS',event_id='FOREIGN-OBS-RECORD_OBSERVATION')
    append(connect,(foreign['event_id'],pg.now,foreign));append(connect,delivery)
    run(pg)
    assert case(pg)[2]!='completed' and completions(pg)==[]
    with pg.db() as db:
        refs=db.execute("select evidence_refs from app_private.oom_manager_cases where case_id=%s",(original[0],)).fetchone()[0]
    assert 'owner:42' in refs and 'owner:43' not in refs


def test_recipient_changed_after_normalization_refuses_locked_completion(rootline_db,monkeypatch):
    pg,connect=rootline_db;_,delivery,_=seed(rootline_db);append(connect,delivery)
    terminal=worker.normalize_candidate(sources._rootline(pg.now)[0],now=pg.now)
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID','43')
    monkeypatch.setenv('ROOTLINE_REASSESSMENT_OWNER_USER_ID','43')
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS','42,43')
    with pg.db() as db,db.cursor() as cur:
        assert pg.store._reconcile(cur,terminal,pg.now)=='stale'
    assert case(pg)[2]!='completed' and completions(pg)==[]


def test_successive_fresh_pending_observations_keep_due_and_generation_then_claim_normally(rootline_db):
    pg,connect=rootline_db;observation,_,_=seed(rootline_db)
    with pg.db() as db:
        original=db.execute('select generation,evidence_digest,next_reassessment_at from app_private.oom_manager_cases').fetchone()
    for index in (1,2):
        pg.now+=timedelta(minutes=5)
        fresh=deepcopy(observation[2]);fresh.update(identity='FRESH-'+str(index),
            event_id='FRESH-'+str(index)+'-RECORD_OBSERVATION',result_id='RESULT-'+str(index),
            evidence_generation='GEN-'+str(index),evidence_cutoff=pg.now.isoformat())
        append(connect,(fresh['event_id'],pg.now-timedelta(seconds=1),fresh))
        candidate=worker.normalize_candidate(sources._rootline(pg.now)[0],now=pg.now)
        with pg.db() as db,db.cursor() as cur:
            before=db.execute('select next_reassessment_at from app_private.oom_manager_cases').fetchone()[0]
            assert pg.store._reconcile(cur,candidate,pg.now)=='replayed'
            actual=db.execute('select generation,evidence_digest,next_reassessment_at,evidence_refs from app_private.oom_manager_cases').fetchone()
        assert actual[:2]==original[:2] and actual[2]==before and actual[2]<=pg.now
        assert 'event:'+fresh['event_id'] in actual[3]
        result=run(pg,deliver=lambda *args,**kwargs:{'success':True,'status':'synthetic_no_send','delivery_confirmed':False})
        assert result['cases_claimed']==1 and result['candidate_replays']==1 and result['exceptions']==0
        assert case(pg)[1]==original[0]


def test_no_retained_advisory_is_not_created_from_a_delivery_receipt(rootline_db):
    pg,connect=rootline_db;observation,delivery=evidence(pg.now)
    append(connect,observation);append(connect,delivery)
    outcome=run(pg)
    assert outcome['cases_claimed']==0 and outcome['candidates_created']==0 and completions(pg)==[]
    with pg.db() as db:assert db.execute('select count(*) from app_private.oom_manager_cases').fetchone()==(0,)


def test_concurrent_exact_terminal_snapshots_append_one_completion(rootline_db):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    pg,connect=rootline_db;_,delivery,_=seed(rootline_db);append(connect,delivery)
    terminal=worker.normalize_candidate(sources._rootline(pg.now)[0],now=pg.now)
    barrier=Barrier(2)
    def apply():
        with pg.db() as db,db.cursor() as cur:
            barrier.wait(timeout=5)
            return pg.store._reconcile(cur,terminal,pg.now)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:apply(),range(2)))
    assert sorted(results)==['changed','replayed']
    assert case(pg)[2]=='completed' and len(completions(pg))==1


def test_actual_paired_unknown_material_cannot_complete(rootline_db):
    pg,connect=rootline_db;observation,delivery=evidence(pg.now)
    observation[2]['material_digest']=delivery[2]['material_digest']='unknown'
    append(connect,observation)
    pg.seed(sources._rootline(pg.now));append(connect,delivery)
    result=run(pg)
    assert result['exceptions']==0 and case(pg)[2]!='completed' and completions(pg)==[]
