"""Real disposable PostgreSQL proof for the existing transition and family rails."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import importlib, os, uuid
import pytest

store = importlib.import_module('modules.telemetry.rootline_irrigation_execution_store')
from modules.oom_sakkie.rootline_transition_notifications import recover_transition_notifications
from modules.oom_sakkie.family_message_lifecycle import deliver_family_result

pytestmark = pytest.mark.skipif(not os.getenv('ROOTLINE_DISPOSABLE_POSTGRES_URL'),reason='isolated PostgreSQL required')

@pytest.fixture
def db(monkeypatch):
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    url=os.environ['ROOTLINE_DISPOSABLE_POSTGRES_URL'];target=conninfo_to_dict(url)
    assert target.get('host')=='127.0.0.1' and target.get('dbname')=='rootline_visibility_20261116'
    source=Path(os.getenv('ROOTLINE_SOURCE_CHECKOUT') or Path(__file__).resolve().parents[1])
    with psycopg.connect(url) as connection:
        connection.execute((source/'supabase/migrations/202607070001_create_sam_live_stock_conversation_review_events.sql').read_text())
    monkeypatch.setenv('DATABASE_URL',url)
    monkeypatch.setattr(store,'EVENT_SOURCE','visibility-test-'+uuid.uuid4().hex)
    monkeypatch.setattr(store,'_NOTIFICATION_EPOCH_ID','TEST-EPOCH-'+uuid.uuid4().hex)
    return url


def seed(db, action, row, *, created_at=None):
    import psycopg
    from psycopg.types.json import Jsonb
    body={**row,'action':action,'event_id':uuid.uuid4().hex}
    with psycopg.connect(db) as connection:
        connection.execute('''insert into public.sam_live_stock_conversation_review_events
            (review_event_id,event_source,review_json,created_at) values(%s,%s,%s,%s)''',
            (body['event_id'],store.EVENT_SOURCE,Jsonb({'rootline_execution':body}),created_at or datetime.now(timezone.utc)))
    return body


def edge(*, valid=True):
    now=datetime.now(timezone.utc)
    return {'execution_id':'TEST-'+uuid.uuid4().hex,'device_id':'1002851416','channel':1,
        'state':'Active','provider_start_evidence':{'authoritative':valid,'state':'ON',
        'device_id':'1002851416','channel':1,'retrieved_at':now.isoformat()}}


def notifier(sent):
    def notify(state,row,**kwargs):
        identity=row['notification_identity']+':'+state.upper()
        def sender(chat,text,**kwargs):
            sent.append(identity);return {'success':True,'telegram_message_id':uuid.uuid4().hex}
        delivered=deliver_family_result({'telegram_user_id':'42','telegram_chat_id':'42',
            'provider_message_id':identity,'provider_timestamp':row['notification_observed_at']},
            {'success':True,'status':state.lower(),'answer':'Verified switch transition.'},
            specialist='ROOTLINE',mission_id=identity,card_mission_id=identity,sender=sender)
        return {**delivered,'provider_message_id':delivered.get('telegram_message_id'),
            'provider_delivery_confirmed':bool(delivered.get('telegram_message_id')) and
                (delivered.get('success') is True or delivered.get('provider_delivery_confirmed') is True)}
    return notify


def test_epoch_is_atomic_server_dated_and_ignores_supplied_cutoff(db):
    def claim(_):return store.rootline_irrigation_execution_store('claim_notification_recovery_epoch',
        {'since':'1900-01-01T00:00:00Z','execution_id':'caller-selected'})
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(claim,range(4)))
    assert all(row['success'] for row in results)
    assert sum(row.get('created') is True for row in results)==1
    epochs=[row['epoch'] for row in results]
    assert all(row==epochs[0] for row in epochs)
    from zoneinfo import ZoneInfo
    cutoff=datetime.fromisoformat(epochs[0]['since']).astimezone(ZoneInfo('Africa/Johannesburg'))
    assert cutoff.hour==cutoff.minute==cutoff.second==0
    assert cutoff.date()==datetime.now(ZoneInfo('Africa/Johannesburg')).date()
    assert epochs[0]['historical_before_cutoff']=='preserved_not_claimed_delivered'


def test_persisted_epoch_survives_midnight_and_restart_without_historical_backfill(db):
    # A canonical epoch from the prior deployed day; caller clock does not reset it.
    initial=store.rootline_irrigation_execution_store('claim_notification_recovery_epoch',{})['epoch']
    cutoff=datetime.fromisoformat(initial['since']);sent=[]
    old=seed(db,'mark_borehole_active',edge(),created_at=cutoff-timedelta(seconds=1))
    active=seed(db,'mark_borehole_active',edge(),created_at=cutoff+timedelta(seconds=1))
    future_clock=datetime.now(timezone.utc)+timedelta(days=1)
    first=recover_transition_notifications(notify=notifier(sent),now=future_clock)
    again=recover_transition_notifications(notify=notifier(sent),now=future_clock+timedelta(minutes=1))
    loaded=store.rootline_irrigation_execution_store('load_notification_transitions',{})
    assert loaded['epoch']==initial and sent==[active['execution_id']+':Started:STARTED']
    assert first['notification_count']==1 and again['notification_count']==0
    import psycopg
    with psycopg.connect(db) as connection:
        assert connection.execute('select 1 from public.sam_live_stock_conversation_review_events where review_event_id=%s',
            (old['event_id'],)).fetchone()==(1,)


def test_invalid_and_already_delivered_backlog_does_not_starve_later_valid_edges(db):
    store.rootline_irrigation_execution_store('claim_notification_recovery_epoch',{})
    invalid=[seed(db,'mark_borehole_active',edge(valid=False)) for _ in range(8)]
    valid=[seed(db,'mark_borehole_active',edge()) for _ in range(9)];sent=[]
    result1=recover_transition_notifications(notify=notifier(sent))
    assert result1['status']=='rootline_transition_evidence_unproven' and sent==[]
    result2=recover_transition_notifications(notify=notifier(sent))
    result3=recover_transition_notifications(notify=notifier(sent))
    result4=recover_transition_notifications(notify=notifier(sent))
    assert result2['notification_count']==8 and result3['notification_count']==1 and result4['notification_count']==0
    assert len(sent)==len(set(sent))==9
    import psycopg
    with psycopg.connect(db) as connection:
        rows=connection.execute('''select review_json->'rootline_execution' from public.sam_live_stock_conversation_review_events
            where event_source=%s and review_json->'rootline_execution'->>'notification_projection_rejected'='true' ''',
            (store.EVENT_SOURCE,)).fetchall()
    assert len(rows)==8 and all(row[0]['delivery_confirmed'] is False for row in rows)
    assert all(row[0]['next_action_owner']=='ROOTLINE' and row[0]['delivery_state']=='verification_required' for row in rows)


def test_concurrent_recovery_uses_real_family_atomic_claim_and_restart_proof(db):
    store.rootline_irrigation_execution_store('claim_notification_recovery_epoch',{})
    seed(db,'mark_borehole_active',edge());sent=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(lambda _:recover_transition_notifications(notify=notifier(sent)),range(2)))
    recover_transition_notifications(notify=notifier(sent))
    assert len(sent)==1


def test_malformed_ids_do_not_starve_valid_edges(db):
    import psycopg
    from psycopg.types.json import Jsonb
    store.rootline_irrigation_execution_store('claim_notification_recovery_epoch',{})
    for index in range(8):
        body={**edge(),'action':'mark_borehole_active'}
        if index % 2:body['event_id']='mismatched-payload-id'
        else:body.pop('execution_id')
        with psycopg.connect(db) as connection:
            connection.execute("insert into public.sam_live_stock_conversation_review_events (review_event_id,event_source,review_json) values(%s,%s,%s)",
                (uuid.uuid4().hex,store.EVENT_SOURCE,Jsonb({'rootline_execution':body})))
    for _ in range(9):seed(db,'mark_borehole_active',edge())
    sent=[]
    first=recover_transition_notifications(notify=notifier(sent))
    assert first['status']=='rootline_transition_evidence_unproven' and not sent
    assert recover_transition_notifications(notify=notifier(sent))['notification_count']==8
    assert recover_transition_notifications(notify=notifier(sent))['notification_count']==1
    assert recover_transition_notifications(notify=notifier(sent))['notification_count']==0
    assert len(sent)==len(set(sent))==9


def test_confirmed_receipt_dominates_later_uncertain_records(db):
    import psycopg
    store.rootline_irrigation_execution_store('claim_notification_recovery_epoch',{})
    event=seed(db,'mark_borehole_active',edge())
    shared={'execution_id':event['execution_id'],'transition_event_id':event['event_id']}
    confirmed=seed(db,'record_notification_delivery',{**shared,'delivery_confirmed':True,
        'provider_message_id':'synthetic-confirmed-receipt'})
    ambiguous=seed(db,'record_notification_delivery',{**shared,'delivery_confirmed':False,
        'delivery_ambiguous':True})
    assert store.rootline_irrigation_execution_store('load_notification_transitions',{})['transitions']==[]
    # A later stale zero-send observation must not erase the same confirmation either.
    unsent=seed(db,'record_notification_delivery',{**shared,'delivery_confirmed':False,
        'delivery_definitely_not_sent':True})
    assert store.rootline_irrigation_execution_store('load_notification_transitions',{})['transitions']==[]
    recover_transition_notifications(notify=lambda *a,**k:pytest.fail('confirmed edge retried'))
    with psycopg.connect(db) as connection:
        preserved=connection.execute('select count(*) from public.sam_live_stock_conversation_review_events where review_event_id=any(%s)',
            ([row['event_id'] for row in (confirmed,ambiguous,unsent)],)).fetchone()[0]
    assert preserved==3
