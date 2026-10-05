"""Real isolated PostgreSQL + authenticated Telegram adapters; only provider I/O is fake."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import re
import pytest
from modules.oom_sakkie import herdmaster_purpose_telegram as runtime
from modules.oom_sakkie import protected_action_claims as claims
from modules.oom_sakkie import protected_delivery_lifecycle as delivery
from modules.oom_sakkie import family_message_lifecycle as family
from modules.oom_sakkie import bounded_postgres_read as bounded
from modules.oom_sakkie import manager_case_sources as sources
from modules.oom_sakkie.general_manager_worker import PostgresManagerCaseStore, normalize_candidate
from modules.pig_weights import purpose_correction_batch_service as batches
from modules.pig_weights.herdmaster_purpose_work import load_purpose_work_snapshot
from tests.test_herdmaster_purpose_weighing_postgres import purpose_store
from tests.test_herdmaster_weighing_reconciliation_postgres import weighing_store
from tests.test_oom_sakkie_retained_report_recovery_postgres import store, URL

pytestmark=pytest.mark.skipif(not URL,reason='explicit isolated PostgreSQL URL required')
MIGRATION='20261004232451_allow_herdmaster_purpose_protected_claims.sql'
OWNER='42'; TOKEN='synthetic-gateway-secret-32-characters'; SECRET='synthetic-direct-secret-32-characters'


def environment():
    return {'OOM_SAKKIE_TELEGRAM_OWNER_USER_ID':OWNER,'OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS':OWNER,
        'OOM_SAKKIE_TELEGRAM_OWNER_LANGUAGE':'en','OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED':'1',
        'OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED':'1','OOM_SAKKIE_TELEGRAM_BOT_TOKEN':'123456789:'+'x'*40,
        'OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET':SECRET,'OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED':'1',
        'OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN':TOKEN}


@pytest.fixture
def database(purpose_store,monkeypatch):
    connect=purpose_store;folder=Path(__file__).parents[1]/'supabase/migrations'
    with connect() as db,db.cursor() as cur:
        schema=db.schema
        # This inherited fixture starts at the original two-kind migration.
        # Install the exact tracked predecessor expression before qualifying the
        # actual additive migration, with only its namespace relocated.
        previous=(folder/'202609110001_allow_herdmaster_weaning_protected_claims.sql').read_text(encoding='utf-8')
        kinds=re.search(r'target_action_kinds constant text\[\] := array\[(.*?)\]::text\[\]',previous,re.S)[1]
        cur.execute('alter table app_private.oom_protected_action_claims drop constraint oom_protected_action_claims_action_kind_check')
        cur.execute('alter table app_private.oom_protected_action_claims add constraint oom_protected_action_claims_action_kind_check check(action_kind in ('+kinds+'))')
        ddl=(folder/MIGRATION).read_text(encoding='utf-8').replace("n.nspname = 'app_private'", "n.nspname = '"+schema+"'")
        cur.execute(ddl);cur.execute(ddl)
        cur.execute((folder/'202607220001_create_pig_purpose_correction_batches.sql').read_text(encoding='utf-8'))
        cur.execute("update public.pigs set pig_id='PIG-'||pig_id")
        cur.execute("update public.pig_weight_events set pig_id='PIG-'||pig_id")
        cur.execute("update public.litters set sow_tag_number='Synthetic Waki'")
        for pig in ('PIG-PURPOSE-A','PIG-PURPOSE-B'):
            cur.execute("insert into public.pig_weight_events(weight_event_id,pig_id,weight_date,weight_kg) values(%s,%s,current_date,14)",('FRESH-'+pig,pig))
    monkeypatch.setenv('OWNER_SESSION_SECRET','synthetic-purpose-telegram-owner-secret')
    monkeypatch.setattr(runtime,'_connect',connect);monkeypatch.setattr(claims,'_connect',connect)
    monkeypatch.setattr(delivery,'_connect',connect)
    monkeypatch.setattr(bounded,'connect_bounded_rootline_postgres',lambda **kw:connect())
    monkeypatch.setattr(batches,'_connect',lambda cf=None:cf('') if cf else connect())
    # The owning journal API insists on explicit DB configuration even when a
    # connection factory is supplied. Keep ambient DATABASE_URL blank and bind
    # its existing explicit argument to this same guarded local fixture only.
    from modules.sales import sam_live_stock_launch_control as journal
    record = journal.record_sam_live_stock_review_event
    monkeypatch.setattr(journal,'record_sam_live_stock_review_event',
        lambda event,**kw:record(event,database_url=URL,**kw))

    now=datetime.now(timezone.utc)
    snapshot=load_purpose_work_snapshot(analysis_date=now.astimezone(runtime.FARM_ZONE).date(),database_url=URL,connect=lambda *a,**kw:connect())
    snapshot['snapshot_observed_at']=now.isoformat()
    raw=sources._purpose_review_candidates(snapshot,now=now,today=now.astimezone(runtime.FARM_ZONE).date(),observed_at=now)
    assert len(raw)==1 and raw[0]['_purpose_membership']['member_count']==2
    manager=PostgresManagerCaseStore(connect_factory=connect)
    with connect() as db,db.cursor() as cur:manager._reconcile(cur,normalize_candidate(raw[0],now=now),now)
    return connect


@pytest.fixture
def transport(database,monkeypatch):
    from modules.sales import sam_live_stock_launch_control as telegram
    from modules.oom_sakkie import telegram_gateway as gateway
    from modules.oom_sakkie import telegram_direct as direct
    from modules.oom_sakkie import semantic_front_door
    effects=[];current_card=[699]
    def send(chat,text,**kwargs):
        effects.append(('send',chat,text,kwargs.get('reply_markup')));current_card[0]+=1
        return {'success':True,'telegram_message_id':str(current_card[0]),'provider_timestamp':datetime.now(timezone.utc).isoformat()}
    def edit(chat,message,text,**kwargs):
        effects.append(('edit',chat,text,kwargs.get('reply_markup')))
        return {'success':True,'telegram_message_id':message}
    def api(token,method,payload):
        assert method=='answerCallbackQuery';effects.append(('ack',payload['callback_query_id']));return {'ok':True}
    monkeypatch.setattr(family,'_send_telegram',send);monkeypatch.setattr(family,'_edit_telegram',edit)
    monkeypatch.setattr(telegram,'_telegram_api',api)
    monkeypatch.setattr(gateway,'interpret_owner_message',lambda *a,**kw:pytest.fail('purpose navigation must not call model'))
    monkeypatch.setattr(semantic_front_door,'budgeted_urlopen',lambda *a,**kw:pytest.fail('no model'))
    count=[0]
    def invoke(channel,text=None,data=None,callback_id=None,card_id=None):
        count[0]+=1;now=int(datetime.now(timezone.utc).timestamp())
        if data:
            payload={'update_id':1000+count[0],'callback_query':{'id':callback_id or 'CB-'+str(count[0]),'data':data,
                'from':{'id':42},'message':{'message_id':card_id or current_card[0],'date':now,'chat':{'id':42,'type':'private'}}}}
        else:payload={'update_id':1000+count[0],'message':{'message_id':1000+count[0],'date':now,'text':text,
            'from':{'id':42},'chat':{'id':42,'type':'private'}}}
        if channel=='direct':return direct.handle_telegram_direct_webhook(payload,headers={'X-Telegram-Bot-Api-Secret-Token':SECRET},environ=environment())
        return gateway.handle_telegram_gateway_message(payload,headers={'Authorization':'Bearer '+TOKEN},environ=environment())
    return invoke,effects


def button(body,action):
    result=body['message']
    return next(b['callback_data'] for row in result['reply_markup']['inline_keyboard'] for b in row if b['callback_data'].endswith(':'+action))


def counts(connect):
    with connect() as db,db.cursor() as cur:
        cur.execute("select pig_id,purpose from public.pigs order by pig_id");pigs=cur.fetchall()
        cur.execute("select count(*) from public.operational_events where event_type='pig.purpose_corrected'");events=cur.fetchone()[0]
        cur.execute("select count(*) from public.pig_purpose_correction_batches where status='executed'");executed=cur.fetchone()[0]
    return pigs,events,executed


@pytest.mark.parametrize('channel',['direct','gateway'])
def test_real_authenticated_journey_edits_one_card_and_records_once(database,transport,channel):
    invoke,effects=transport;before=counts(database)
    overview,code=invoke(channel,text='Review the purpose decisions in Telegram');assert code==200,json.dumps(overview,default=str)
    assert overview['delivery']['protected_preview_card_bound'] is True
    group,code=invoke(channel,data=button(overview,'group0'));assert code==200,json.dumps(group,default=str)
    assert 'Synthetic Waki' in group['answer'] and 'LITTER-' not in group['answer']
    selection,code=invoke(channel,data=button(group,'change'));assert code==200,json.dumps(selection,default=str)
    selected,code=invoke(channel,data=button(selection,'pick0'));assert code==200,json.dumps(selected,default=str)
    preview,code=invoke(channel,data=button(selected,'set3'));assert code==200,json.dumps(preview,default=str)
    assert counts(database)==before
    assert [e[0] for e in effects].count('send')==1 and [e[0] for e in effects].count('edit')==4
    assert all(e[3] and e[3]['inline_keyboard'] for e in effects if e[0] in {'send','edit'})
    confirm=button(preview,'confirm')
    saved,code=invoke(channel,data=confirm,callback_id='EXACT-CONFIRM');assert code==200,json.dumps(saved,default=str)
    pigs,events,executed=counts(database);assert events==1 and executed==1
    assert dict(pigs)=={'PIG-PURPOSE-A':'Unknown','PIG-PURPOSE-B':'Sale'}
    assert saved['message']['status']=='purpose_recorded_verified'
    replay,code=invoke(channel,data=confirm,callback_id='EXACT-CONFIRM');assert code==200,json.dumps(replay,default=str)
    assert counts(database)==(pigs,events,executed)
    with database() as db,db.cursor() as cur:
        cur.execute("select count(*) from public.sam_live_stock_conversation_review_events where event_source=%s",(family.EVENT_SOURCE,))
        assert cur.fetchone()[0]>=12


def test_migration_exact_additive_replay_privileges_and_foreign_kind_rejection(database):
    with database() as db,db.cursor() as cur:
        cur.execute("select pg_get_constraintdef(oid) from pg_constraint where conrelid=%s::regclass and conname='oom_protected_action_claims_action_kind_check'",(db.schema+'.oom_protected_action_claims',))
        kinds=set(re.findall("'([a-z_]+)'",cur.fetchone()[0]));assert len(kinds)==19 and {runtime.REVIEW,runtime.CORRECTION}<=kinds
        cur.execute("select has_table_privilege('anon',%s,'INSERT'),has_table_privilege('authenticated',%s,'UPDATE')",(db.schema+'.oom_protected_action_claims',)*2)
        assert cur.fetchone()==(False,False)
    with pytest.raises(Exception):
        claims.create_claim(action_kind='unapproved_purpose',owner_user_id='42',private_chat_id='42',mission_id='BAD',provider_message_id='BAD',evidence_generation='1',preview_payload={},connect_factory=database)


def test_real_loader_and_membership_use_current_snapshot_without_writes(database):
    before=counts(database);ctx=runtime.load_context(now=datetime.now(timezone.utc),connect=database)
    assert len(ctx['cases'])==1 and ctx['cases'][0]['available'],ctx['cases']
    assert ctx['cases'][0]['membership']['member_ids']==['PIG-PURPOSE-A','PIG-PURPOSE-B']
    assert ctx['snapshot']['snapshot_observed_at'] and counts(database)==before


def test_real_writer_optional_guard_rolls_back_and_default_remains_compatible(database):
    decisions=[dict(pig_id='PIG-PURPOSE-A',purpose='Sale',reason='Synthetic owner',note='')]
    kw={'actor_id':'42','connect_factory':lambda url:database()}
    preview,code=batches.preview_correction_batch(decisions,**kw);assert code==200
    created,code=batches.create_correction_batch(decisions,idempotency_key='guard-test',confirmation_binding=preview['confirmation_binding'],**kw);assert code==201
    assert batches.approve_correction_batch(created['batch_id'],**kw)[1]==200
    before=counts(database)
    def reject(connection,envelope):
        connection.cursor().execute("update public.pigs set purpose='Meat' where pig_id='PIG-PURPOSE-B'")
        raise ValueError('synthetic_guard_refusal')
    result,code=batches.execute_correction_batch(created['batch_id'],validate_current=reject,**kw)
    assert code==409 and counts(database)==before
    result,code=batches.execute_correction_batch(created['batch_id'],**kw)
    assert code==200 and result['rows_updated']==1


def test_completed_claim_requires_same_provider_for_delivery_recovery(database):
    p={'contract':runtime.CONTRACT,'mode':'overview','cases':[],'mission_id':'RECOVERY','language':'en'}
    c=claims.create_claim(action_kind=runtime.REVIEW,owner_user_id='42',private_chat_id='42',mission_id='RECOVERY',provider_message_id='first',evidence_generation='1',preview_payload=p,connect_factory=database)
    claims.bind_claim_card(c['callback_token'],'700',connect_factory=database)
    args=dict(owner_user_id='42',private_chat_id='42',source_card_message_id='700',provider_timestamp=datetime.now(timezone.utc).isoformat(),connect_factory=database,purpose_callback=True)
    command='oompa:'+c['callback_token']+':confirm'
    claimed,code=claims.claim_callback(command,provider_message_id='CONFIRM',**args);assert code==200
    claims.complete_claim(c['callback_token'],{'success':True,'status':'purpose_review_date_recorded'},connect_factory=database)
    assert claims.claim_callback(command,provider_message_id='CONFIRM',**args)[0]['status']=='purpose_completed_delivery_recovery'
    assert claims.claim_callback(command,provider_message_id='DIFFERENT',**args)[0]['status']=='protected_callback_replayed_noop'
    args['source_card_message_id']='foreign';assert claims.claim_callback(command,provider_message_id='CONFIRM',**args)[1]==409


def prepared_preview(invoke, channel='direct'):
    overview,code=invoke(channel,text='Review the purpose decisions in Telegram');assert code==200,json.dumps(overview,default=str)
    group,code=invoke(channel,data=button(overview,'group0'));assert code==200,json.dumps(group,default=str)
    selection,code=invoke(channel,data=button(group,'change'));assert code==200
    preview,code=invoke(channel,data=button(selection,'set3'));assert code==200,json.dumps(preview,default=str)
    return preview


def test_domain_commit_then_claim_completion_loss_recovers_existing_batch(database,transport,monkeypatch):
    invoke,effects=transport;preview=prepared_preview(invoke);confirm=button(preview,'confirm')
    real=claims.complete_claim
    def lost(*a,**kw):raise RuntimeError('synthetic acknowledgement failure after domain commit')
    monkeypatch.setattr(claims,'complete_claim',lost)
    result,code=invoke('direct',data=confirm,callback_id='COMMIT-LOSS')
    assert code==503 and result['message']['writes_farm_data'] is None and 'may have completed' in result['answer']
    saved=counts(database);assert saved[1:]==(2,1)
    monkeypatch.setattr(claims,'complete_claim',real)
    replay,code=invoke('direct',data=confirm,callback_id='COMMIT-LOSS',card_id=700)
    assert code==200,json.dumps(replay,default=str)
    assert replay['message']['status']=='purpose_recorded_verified' and counts(database)==saved


def test_completed_claim_lost_provider_reply_recovers_without_second_writer(database,transport,monkeypatch):
    invoke,effects=transport;preview=prepared_preview(invoke);confirm=button(preview,'confirm')
    real_edit=family._edit_telegram
    monkeypatch.setattr(family,'_edit_telegram',lambda *a,**kw:{'success':False,'delivery_definitely_not_sent':True})
    result,code=invoke('direct',data=confirm,callback_id='REPLY-LOSS');assert code>=400
    saved=counts(database);assert saved[1:]==(2,1)
    monkeypatch.setattr(family,'_edit_telegram',real_edit)
    monkeypatch.setattr(batches,'execute_correction_batch',lambda *a,**kw:pytest.fail('completed claim must not execute again'))
    replay,code=invoke('direct',data=confirm,callback_id='REPLY-LOSS')
    assert code==200,json.dumps(replay,default=str)
    assert replay['message']['delivery_recovery_required'] and counts(database)==saved


def test_real_explicit_review_date_preserves_farm_and_case_material_once(database,transport):
    invoke,effects=transport;before=counts(database)
    overview,code=invoke('gateway',text='Show me purpose decisions');assert code==200
    group,code=invoke('gateway',data=button(overview,'group0'));assert code==200
    dates,code=invoke('gateway',data=button(group,'later'));assert code==200
    choice=next(b['callback_data'] for row in dates['message']['reply_markup']['inline_keyboard'] for b in row if ':date' in b['callback_data'])
    preview,code=invoke('gateway',data=choice);assert code==200
    with database() as db,db.cursor() as cur:
        cur.execute('select case_id,generation,evidence_digest,last_delivery_digest from app_private.oom_manager_cases');old=cur.fetchone()
    confirm=button(preview,'confirm');saved,code=invoke('gateway',data=confirm,callback_id='DEFER-EXACT')
    assert code==200,json.dumps(saved,default=str)
    assert counts(database)==before
    with database() as db,db.cursor() as cur:
        cur.execute('select case_id,generation,evidence_digest,last_delivery_digest from app_private.oom_manager_cases');assert cur.fetchone()==old
        cur.execute("select event_payload->'purpose_review_deferred' from app_private.oom_manager_case_events where event_payload ? 'purpose_review_deferred'")
        rows=cur.fetchall();assert len(rows)==1
        event=rows[0][0];assert event['owner_user_id']=='42' and event['review_at'].endswith('06:00:00+00:00')
    replay,code=invoke('gateway',data=confirm,callback_id='DEFER-EXACT');assert code==200 and counts(database)==before


def test_fresh_hold_after_preview_prevents_real_writer(database,transport):
    invoke,effects=transport;preview=prepared_preview(invoke);before=counts(database)
    with database() as db,db.cursor() as cur:
        cur.execute("insert into public.pig_active_outlets(pig_id,active,outlet_assignment_id,outlet_type,source_record_id) values('PIG-PURPOSE-A',true,'HOLD','reservation','HOLD')")
    result,code=invoke('direct',data=button(preview,'confirm'),callback_id='HELD')
    assert code>=400 and counts(database)==before


def test_generic_callback_namespace_cannot_consume_purpose_claim(database,transport):
    invoke,effects=transport;preview=prepared_preview(invoke)
    token=preview['message']['callback_token']
    result,code=claims.claim_callback('oompa:'+token+':confirm',owner_user_id='42',private_chat_id='42',
        provider_message_id='FORGED-NAMESPACE',provider_timestamp=datetime.now(timezone.utc).isoformat(),source_card_message_id='700',connect_factory=database)
    assert code==409 and result['status']=='purpose_typed_callback_required'
    with database() as db,db.cursor() as cur:
        cur.execute('select status from app_private.oom_protected_action_claims where callback_token=%s',(token,));assert cur.fetchone()[0]=='active'


def test_tampered_callback_and_expired_card_no_domain_effect(database,transport):
    invoke,effects=transport;preview=prepared_preview(invoke);token=preview['message']['callback_token'];before=counts(database)
    with database() as db,db.cursor() as cur:
        cur.execute("update app_private.oom_protected_action_claims set expires_at=now()-interval '1 second' where callback_token=%s",(token,))
    result,code=invoke('direct',data=button(preview,'confirm'),callback_id='EXPIRED')
    assert code==409 and result['message']['reason']=='protected_callback_expired' and counts(database)==before


def test_typed_semantic_synonym_opens_real_review_without_recording(database,transport,monkeypatch):
    from modules.oom_sakkie import telegram_gateway as gateway
    from modules.oom_sakkie.semantic_front_door import SemanticInterpretation
    invoke,effects=transport;before=counts(database);seen=[]
    def interpretation(parsed,**kwargs):
        seen.append(parsed['text'])
        return SemanticInterpretation(domain='herd_management',intent='purpose_review_telegram',
            message_kind='question',requested_action='open_current_purpose_review',
            recording_prohibited=True,language='en')
    monkeypatch.setattr(gateway,'interpret_owner_message',interpretation)
    # Earlier inbox context also executes its real bounded SQL on this schema.
    # The fixture captured the fenced raw connection before this routing seam.
    import psycopg
    monkeypatch.setenv('DATABASE_URL',URL)
    def connect_current_fixture(conninfo='',**kwargs):
        assert conninfo==URL
        return database()
    monkeypatch.setattr(psycopg,'connect',connect_current_fixture)
    result,code=invoke('gateway',text="What should we do with Synthetic Waki's piglets?")
    assert code==200,json.dumps(result,default=str)
    assert len(seen)==1 and result['message']['status']=='purpose_telegram_overview'
    assert result['delivery']['protected_preview_card_bound'] is True
    assert counts(database)==before and [e[0] for e in effects].count('send')==1
    assert any(':group0' in b['callback_data'] for row in result['message']['reply_markup']['inline_keyboard'] for b in row)


def test_late_navigation_cannot_retire_newly_bound_successor(database,transport):
    from copy import deepcopy
    invoke,effects=transport
    overview,code=invoke('direct',text='Review purpose decisions');assert code==200
    token=overview['message']['callback_token']
    delayed,code=claims.claim_callback('oompa:'+token+':details',owner_user_id='42',private_chat_id='42',
        provider_message_id='LATE',provider_timestamp=datetime.now(timezone.utc).isoformat(),
        source_card_message_id='700',connect_factory=database,purpose_callback=True)
    assert code==200 and delayed['status']=='protected_preview_details'
    newer,code=invoke('direct',data=button(overview,'group0'));assert code==200
    newer_token=newer['message']['callback_token']
    payload=deepcopy(delayed['preview_payload']);payload['interaction']='LATE'
    payload['parent_transition']={'callback_token':token,'preview_digest':delayed['preview_digest'],
        'source_card_message_id':'700','provider_message_id':'LATE'}
    with pytest.raises(ValueError,match='purpose_parent_transition_not_current'):
        runtime._issue(payload,{'telegram_user_id':'42','telegram_chat_id':'42','provider_message_id':'LATE'},connect=database)
    with database() as db,db.cursor() as cur:
        cur.execute("select callback_token,preview_card_message_id from app_private.oom_protected_action_claims where status='active'")
        assert cur.fetchall()==[(newer_token,'700')]
    why,code=invoke('direct',data=button(newer,'why'));assert code==200


def test_verified_completion_opens_other_group_in_telegram_once(database,transport):
    # A second actual canonical cohort; not a mocked recommendation or manager case.
    with database() as db,db.cursor() as cur:
        cur.execute("""insert into public.litters select (jsonb_populate_record(null::public.litters,
            to_jsonb(l)||'{"litter_id":"COHORT-B","sow_tag_number":"Synthetic Sophie","weaned_count":1}'::jsonb)).*
            from public.litters l where litter_id='COHORT-A'""")
        cur.execute("""insert into public.pigs select (jsonb_populate_record(null::public.pigs,
            to_jsonb(p)||'{"pig_id":"PIG-PURPOSE-C","tag_number":"503","pig_name":"Synthetic 503","litter_id":"COHORT-B"}'::jsonb)).*
            from public.pigs p where pig_id='PIG-PURPOSE-A'""")
        cur.execute("insert into public.pig_weight_events(weight_event_id,pig_id,weight_date,weight_kg) values('C-FRESH','PIG-PURPOSE-C',current_date,14)")
    now=datetime.now(timezone.utc)
    snapshot=load_purpose_work_snapshot(analysis_date=now.astimezone(runtime.FARM_ZONE).date(),database_url=URL,connect=lambda *a,**kw:database())
    snapshot['snapshot_observed_at']=now.isoformat()
    raw=sources._purpose_review_candidates(snapshot,now=now,today=now.astimezone(runtime.FARM_ZONE).date(),observed_at=now)
    manager=PostgresManagerCaseStore(connect_factory=database)
    with database() as db,db.cursor() as cur:
        for candidate in raw:manager._reconcile(cur,normalize_candidate(candidate,now=now),now)
    invoke,effects=transport;preview=prepared_preview(invoke)
    saved,code=invoke('direct',data=button(preview,'confirm'),callback_id='FIRST-GROUP');assert code==200
    before=counts(database);assert before[1]>0
    continue_data=button(saved,'remaining')
    overview,code=invoke('direct',data=continue_data,callback_id='REMAINING',card_id=700)
    assert code==200,json.dumps(overview,default=str)
    assert overview['message']['status']=='purpose_telegram_overview' and counts(database)==before
    assert overview['message']['mission_id']!=saved['message']['mission_id']
    sends=[e[0] for e in effects].count('send');assert sends==2
    replay,code=invoke('direct',data=continue_data,callback_id='REMAINING',card_id=700)
    assert code==200 and [e[0] for e in effects].count('send')==sends and counts(database)==before
    group_buttons=[b for row in overview['message']['reply_markup']['inline_keyboard'] for b in row if ':group' in b['callback_data']]
    assert group_buttons
    group,code=invoke('direct',data=group_buttons[0]['callback_data']);assert code==200
    assert counts(database)==before


@pytest.mark.parametrize('wrong',['same_count_wrong_kind','weakened_same_kinds'])
def test_migration_refuses_wrong_predecessor_without_constraint_or_privilege_change(database,wrong):
    folder=Path(__file__).parents[1]/'supabase/migrations'
    previous=(folder/'202609110001_allow_herdmaster_weaning_protected_claims.sql').read_text(encoding='utf-8')
    kinds=re.search(r'target_action_kinds constant text\[\] := array\[(.*?)\]::text\[\]',previous,re.S)[1]
    if wrong=='same_count_wrong_kind':kinds=kinds.replace("'mortality'","'unauthorized_kind'")
    expression='action_kind in ('+kinds+')'
    if wrong=='weakened_same_kinds':expression+=' or length(action_kind)>0'
    with database() as db,db.cursor() as cur:
        schema=db.schema
        cur.execute('alter table app_private.oom_protected_action_claims drop constraint oom_protected_action_claims_action_kind_check')
        cur.execute('alter table app_private.oom_protected_action_claims add constraint oom_protected_action_claims_action_kind_check check('+expression+')')
        cur.execute("select oid,pg_get_constraintdef(oid) from pg_constraint where conrelid=%s::regclass and conname='oom_protected_action_claims_action_kind_check'",(schema+'.oom_protected_action_claims',));before=cur.fetchone()
        cur.execute("select has_table_privilege('anon',%s,'INSERT'),has_table_privilege('authenticated',%s,'UPDATE')",(schema+'.oom_protected_action_claims',)*2);privileges=cur.fetchone()
    ddl=(folder/MIGRATION).read_text(encoding='utf-8').replace("n.nspname = 'app_private'", "n.nspname = '"+schema+"'")
    with pytest.raises(Exception,match='constraint (structure )?mismatch'):
        with database() as db,db.cursor() as cur:cur.execute(ddl)
    with database() as db,db.cursor() as cur:
        cur.execute("select oid,pg_get_constraintdef(oid) from pg_constraint where conrelid=%s::regclass and conname='oom_protected_action_claims_action_kind_check'",(schema+'.oom_protected_action_claims',));assert cur.fetchone()==before
        cur.execute("select has_table_privilege('anon',%s,'INSERT'),has_table_privilege('authenticated',%s,'UPDATE')",(schema+'.oom_protected_action_claims',)*2);assert cur.fetchone()==privileges
