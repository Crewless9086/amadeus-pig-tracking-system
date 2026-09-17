"""Real scoped privilege/visibility transactions; synthetic local principals only."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import pytest
from tests.test_charlie_native_image_roles import role_plane, grant_for, M, REV, disposable_role_dsn

APP = 'charlie_mission_application'
WRITER = 'charlie_owner_execution_hold_writer'
MIGRATION = '20260908141447_qualify_charlie_mission_database_privileges.sql'
ROOT = Path(__file__).resolve().parents[1]


def initialize_privilege_database(admin_dsn):
    """Reset only a specifically named disposable database using real migrations."""
    assert os.environ.get('CHARLIE_TEST_POSTGRES_DISPOSABLE') == '1'
    assert admin_dsn.startswith('host=127.0.0.1 ') and 'user=qualification_admin ' in admin_dsn
    assert any('dbname='+name+' ' in admin_dsn for name in ('charlie_runtime_test','charlie_roles_test'))
    import psycopg
    with psycopg.connect(admin_dsn) as c:
        c.execute('drop schema if exists public cascade; create schema public; grant usage on schema public to public')
        c.execute('create schema if not exists app_private; create table if not exists app_private.migration_log(migration_id text primary key,description text)')
        for name in ('202606300001_create_charlie_mission_queue.sql','202606300002_create_charlie_vault_v1_tables.sql',
                     '202607010002_create_charlie_core_v3_tables.sql',
                     '202607170001_create_charlie_executive_control_plane.sql',
                     '202607170002_create_charlie_private_executive_interface.sql',
                     '202607190002_create_domain_observer_runs.sql','202607190001_create_operational_event_fabric.sql',
                     '202607270003_create_charlie_owner_execution_holds.sql',MIGRATION):
            c.execute((ROOT/'supabase/migrations'/name).read_text())
    return disposable_role_dsn(admin_dsn,APP)


def held(p):
    result, code = p['store'].create_owner_execution_hold(M, 'g1', 'synthetic privilege hold', owner_principal='synthetic-owner')
    assert code == 201, result
    return result['hold']


def guard(p, role=APP, purpose='application'):
    return p['sql']('select * from app_private.assert_charlie_mission_connection(%s)', (purpose,), role=role)


@pytest.mark.parametrize('role,purpose', [(APP, 'application'), (WRITER, 'hold_writer'), (APP, 'hold_read'), (WRITER, 'hold_read')])
def test_exact_authenticated_connection_contract(role_plane, role, purpose):
    p=role_plane
    assert p['sql']('select session_user,current_user', role=role) == [(role, role)]
    assert guard(p, role, purpose) == [('charlie_mission_connection_v1', role, purpose, True)]


@pytest.mark.parametrize('credential_role,target_role',[(APP,WRITER),(WRITER,APP),(APP,'qualification_admin')])
def test_credentials_cannot_authenticate_as_other_role(role_plane,credential_role,target_role):
    import psycopg
    dsn=role_plane['dsn'](credential_role).replace('user='+credential_role+' ','user='+target_role+' ')
    with pytest.raises(psycopg.OperationalError,match='password authentication failed'):
        psycopg.connect(dsn)


@pytest.mark.parametrize('role,purpose', [(APP, 'hold_writer'), (WRITER, 'application'), ('service_role', 'application'), ('qualification_admin', 'application')])
def test_wrong_or_privileged_principal_rejected(role_plane, role, purpose):
    import psycopg
    with pytest.raises(psycopg.Error):guard(role_plane, role, purpose)


@pytest.mark.parametrize('statement', [
    'insert into charlie_owner_execution_hold_events(event_id) values(\'forbidden\')',
    'update charlie_owner_execution_hold_events set reason=\'forbidden\'',
    'delete from charlie_owner_execution_hold_events',
    'truncate charlie_owner_execution_hold_events',
    'set role charlie_owner_execution_hold_writer',
    'set role service_role',
    'alter table charlie_owner_execution_hold_events disable row level security',
    "select public.append_charlie_owner_execution_hold('e','h','m','g','r',repeat('a',64),'{}')",
    "select public.append_charlie_owner_execution_hold_release('e','h','m','g','r',repeat('a',64),'c','{}')",
])
def test_application_cannot_assume_writer_or_modify_holds(role_plane, statement):
    import psycopg
    p=role_plane;held(p)
    before=p['sql']('select to_jsonb(h) from charlie_owner_execution_hold_events h')
    with pytest.raises(psycopg.Error):p['sql'](statement, role=APP)
    assert p['sql']('select to_jsonb(h) from charlie_owner_execution_hold_events h') == before


@pytest.mark.parametrize('statement', [
    "insert into charlie_owner_execution_hold_events(event_id) values('forbidden')",
    "update charlie_owner_execution_hold_events set reason='forbidden'",
    'delete from charlie_owner_execution_hold_events',
    'truncate charlie_owner_execution_hold_events',
    "update charlie_missions set title='forbidden'",
    'set role charlie_mission_application',
])
def test_writer_has_only_function_write_path(role_plane, statement):
    import psycopg
    p=role_plane;held(p)
    with pytest.raises(psycopg.Error):p['sql'](statement, role=WRITER)
    assert len(p['sql']('select event_id from charlie_owner_execution_hold_events')) == 1


def test_writer_generation_owner_identity_and_exact_replays(role_plane):
    p=role_plane;s=p['store']
    assert s.create_owner_execution_hold(M,'g1','r',owner_principal='')[1] == 400
    assert s.create_owner_execution_hold(M,'stale','r',owner_principal='synthetic-owner')[1] == 409
    h=held(p)
    assert s.create_owner_execution_hold(M,'g1','synthetic privilege hold',owner_principal='synthetic-owner')[1] == 200
    assert s.create_owner_execution_hold(M,'g1','synthetic privilege hold',owner_principal='different-owner')[1] == 409
    assert s.release_owner_execution_hold(M,'stale',h['hold_id'],'release',owner_principal='synthetic-owner')[1] == 409
    assert s.release_owner_execution_hold(M,'g1','wrong-hold','release',owner_principal='synthetic-owner')[1] == 404
    assert s.release_owner_execution_hold(M,'g1',h['hold_id'],'release',owner_principal='')[1] == 400
    assert len(p['sql']('select event_id from charlie_owner_execution_hold_events')) == 1
    result,code=s.release_owner_execution_hold(M,'g1',h['hold_id'],'release',owner_principal='synthetic-owner')
    assert code == 201, result
    assert s.release_owner_execution_hold(M,'g1',h['hold_id'],'release',owner_principal='synthetic-owner')[1] == 200
    assert s.release_owner_execution_hold(M,'g1',h['hold_id'],'different',owner_principal='synthetic-owner')[1] == 409
    assert len(p['sql']('select event_id from charlie_owner_execution_hold_events')) == 2
    assert s.owner_execution_hold_status(M)[0]['active'] is False


@pytest.mark.parametrize('change', [
    'drop policy charlie_mission_application_hold_read on charlie_owner_execution_hold_events',
    'alter policy charlie_mission_application_hold_read on charlie_owner_execution_hold_events using (false)',
    'create policy invisible on charlie_owner_execution_hold_events as restrictive for select to public using (false)',
    'revoke select on charlie_owner_execution_hold_events from charlie_mission_application',
])
def test_invisible_or_missing_hold_access_fails_closed(role_plane, change):
    p=role_plane;held(p);p['sql'](change)
    state,code=p['store'].owner_execution_hold_status(M)
    assert code==503 and state['success'] is False and 'active' not in state
    result,code=p['store'].native_runner_recovery(M,'issue',grant_for(p),authenticated_principal='owner-admin:synthetic-signed',runtime={'worker_revision':REV,'web_revision':REV})
    assert code==503 and result['success'] is False
    assert p['sql']('select count(*) from charlie_mission_events') == [(0,)]


@pytest.mark.parametrize('relation',['charlie_missions','charlie_mission_events','operational_events','operational_projection_checkpoints'])
def test_rls_hidden_canonical_writers_and_receipts_fail_closed(role_plane,relation):
    p=role_plane
    p['sql']('alter table '+relation+' enable row level security')
    p['sql']('create policy hidden_receipt on '+relation+' as restrictive for select to charlie_mission_application using (false)')
    result,code=p['store'].native_runner_recovery(M,'read',{},authenticated_principal='hermes:builder',runtime={'worker_revision':REV,'web_revision':REV})
    assert code==503 and result['success'] is False
    result,code=p['store'].list_resumable_hermes_native_executions(authenticated_principal='hermes:charlie-builder')
    assert code==503 and result['success'] is False


def test_role_membership_even_noinherit_is_not_separation(role_plane):
    import psycopg
    p=role_plane;p['sql']('grant charlie_owner_execution_hold_writer to charlie_mission_application')
    try:
        with pytest.raises(psycopg.Error, match='principal_unsafe'):guard(p)
    finally:p['sql']('revoke charlie_owner_execution_hold_writer from charlie_mission_application')


def test_privileged_session_set_role_does_not_qualify(role_plane):
    import psycopg
    p=role_plane
    with psycopg.connect(p['dsn']('qualification_admin')) as c:
        c.execute('set role charlie_mission_application')
        with pytest.raises(psycopg.Error, match='principal_unsafe'):
            c.execute("select * from app_private.assert_charlie_mission_connection('application')")


def test_caller_supplied_cursor_cannot_bypass_guard(role_plane):
    import psycopg
    p=role_plane;held(p)
    with psycopg.connect(p['dsn']('qualification_admin')) as c:
        result,code=p['store'].owner_execution_hold_status(M,cursor=c.cursor())
        assert code==503 and result['success'] is False


def test_autocommit_factory_and_supplied_cursor_cannot_certify_absence(role_plane):
    import psycopg
    p=role_plane;held(p)
    with psycopg.connect(p['dsn'](APP),autocommit=True) as c:
        result,code=p['store'].owner_execution_hold_status(M,cursor=c.cursor())
        assert code==503 and result['error_type']=='RuntimeError'
        p['sql']('alter policy charlie_mission_application_hold_read on charlie_owner_execution_hold_events using (false)')
        assert c.execute('select count(*) from charlie_owner_execution_hold_events').fetchone()==(0,)
    result,code=p['store'].owner_execution_hold_status(M,database_url=p['dsn'](APP),
        connect_factory=lambda dsn:psycopg.connect(dsn,autocommit=True))
    assert code==503 and result['success'] is False and 'active' not in result
    assert p['sql']('select count(*) from charlie_mission_events')==[(0,)]


@pytest.mark.parametrize('grant',[
    'grant update on charlie_missions to charlie_owner_execution_hold_writer',
    'grant update(title) on charlie_missions to charlie_owner_execution_hold_writer',
    'grant insert on charlie_mission_events to charlie_owner_execution_hold_writer',
])
def test_writer_direct_privilege_drift_prevents_function_path(role_plane,grant):
    import psycopg
    p=role_plane;p['sql'](grant)
    with pytest.raises(psycopg.Error,match='direct_write_unsafe'):guard(p,WRITER,'hold_writer')
    result,code=p['store'].create_owner_execution_hold(M,'g1','r',owner_principal='synthetic-owner')
    assert code==503 and result['success'] is False
    assert p['sql']('select count(*) from charlie_owner_execution_hold_events')==[(0,)]


def test_policy_ddl_serializes_with_visibility_proof(role_plane):
    import psycopg
    p=role_plane;held(p)
    with p['store']._connect(p['dsn'](APP)) as connection:
        # A genuinely independent transaction attempts to invalidate the proof.
        with psycopg.connect(p['dsn']('qualification_admin')) as ddl:
            ddl.execute("set local lock_timeout='250ms'")
            with pytest.raises(psycopg.errors.LockNotAvailable):
                ddl.execute('alter policy charlie_mission_application_hold_read on charlie_owner_execution_hold_events using (false)')
        state,code=p['store'].owner_execution_hold_status(M,cursor=connection.cursor())
        assert code==200 and state['active'] is True
    p['sql']('alter policy charlie_mission_application_hold_read on charlie_owner_execution_hold_events using (false)')
    assert p['store'].owner_execution_hold_status(M)[1] == 503


def test_migration_replay_preserves_hold_and_unrelated_grants(role_plane):
    p=role_plane;held(p)
    before=p['sql']('select to_jsonb(h) from charlie_owner_execution_hold_events h')
    unrelated=p['sql']("select rolname,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb from pg_roles where rolname in ('service_role','qualification_admin')")
    applied=ROOT/'supabase/migrations/202607270003_create_charlie_owner_execution_holds.sql'
    digest=hashlib.sha256(applied.read_bytes()).hexdigest()
    p['sql']((ROOT/'supabase/migrations'/MIGRATION).read_text())
    assert p['sql']('select to_jsonb(h) from charlie_owner_execution_hold_events h')==before
    assert p['sql']("select rolname,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb from pg_roles where rolname in ('service_role','qualification_admin')")==unrelated
    assert hashlib.sha256(applied.read_bytes()).hexdigest()==digest
    assert p['store'].owner_execution_hold_status(M)[0]['active'] is True


def test_missing_and_swapped_configuration_never_falls_back(role_plane, monkeypatch):
    p=role_plane;s=p['store']
    monkeypatch.delenv('CHARLIE_MISSION_DATABASE_URL')
    assert os.environ['DATABASE_URL']
    assert s.owner_execution_hold_status(M)[1]==503
    monkeypatch.setenv('CHARLIE_MISSION_DATABASE_URL',p['dsn'](WRITER))
    assert s.owner_execution_hold_status(M)[1]==503
    monkeypatch.setenv('CHARLIE_OWNER_EXECUTION_HOLD_DATABASE_URL',p['dsn'](APP))
    assert s.create_owner_execution_hold(M,'g1','r',owner_principal='synthetic-owner')[1]==503
    monkeypatch.delenv('CHARLIE_OWNER_EXECUTION_HOLD_DATABASE_URL')
    assert s.create_owner_execution_hold(M,'g1','r',owner_principal='synthetic-owner')[1]==503
    assert p['sql']('select count(*) from charlie_owner_execution_hold_events')==[(0,)]


def test_delegated_vault_writes_use_restricted_application_connection(role_plane):
    p=role_plane
    payload={'mission_vault':{'project_truth':{'project_key':'synthetic-project','purpose':'disposable'},
                             'handoff_reports':[{'mission_id':M,'agent':'builder','stage':'build','status':'held','summary':'synthetic'}]},
             'agent_execution':{'execution_id':'synthetic-execution','stages':[{'agent':'builder','status':'held'}]},
             'review_packet':{'agent_artifacts':{'builder':{'artifact_type':'synthetic','title':'synthetic','value':'test'}},
                              'quality_gates':[{'gate_name':'synthetic','passed':False}]},
             'intelligence_loop':{'lesson_records':[{'mission_id':M,'failure':'synthetic','improvement':'test'}]},
             'income_stream_readiness':{'ready':False}}
    rows=p['store']._write_normalized_vault_records(M,payload,database_url=p['dsn'](APP))
    assert rows and all(row['success'] for row in rows),rows
    assert p['sql']('select count(*) from charlie_vault_artifacts')==[(1,)]


def test_existing_private_executive_and_observer_callers_keep_finite_access(role_plane):
    import psycopg
    from modules.charlie import private_store,executive_store,domain_observer_store,private_briefing
    p=role_plane
    result,code=private_store.bind_owner('synthetic-user','synthetic-chat')
    assert code==200,result
    thread=result['thread_id']
    assert private_store.record_message(thread,'owner','synthetic local context')[1]==201
    assert private_store.recent_context(thread)[1]==200
    assert private_store.private_owner_snapshot()[1]==200
    result,code=executive_store.upsert_executive_goal({'goal_id':'synthetic-goal','title':'Synthetic','objective':'offline qualification',
        'business_area':'system','success_metrics':['disposable rows only']})
    assert code==200,result
    assert executive_store.load_executive_context()[1]==200
    assert executive_store.executive_scorecard()[1]==200
    # Only disposable canonical intent is written. No notifier/runtime is run.
    assert private_briefing.queue_due_private_followups()[1]==200
    run={'run_id':'synthetic-observer','observer_key':'qualification','domain':'missions','trigger':'manual','status':'observed',
         'ran_at':datetime.now(timezone.utc).isoformat(),'authority_tier':'observe','writes_authorized':False,'sends_authorized':False}
    assert domain_observer_store.record_observer_run(run)[1]==201
    assert domain_observer_store.record_observer_run(run)[1]==200
    assert domain_observer_store.observer_last_runs()[1]==200
    assert domain_observer_store.record_observer_feedback('synthetic-observer','synthetic-recommendation',useful=True)[1]==200
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        p['sql']('update charlie_delegation_policies set enabled=true',role=APP)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        p['sql']('delete from charlie_owner_bindings',role=APP)


@pytest.mark.parametrize('row',[(),('partial',),('e','h','wrong','g','r','a'*64,'b'*64,datetime.now(timezone.utc)),
                              ('e','h',M,'g','r','a'*64,'b'*64,None)])
def test_malformed_hold_result_is_unavailable_not_absent(row):
    from modules.charlie import mission_store as store
    from types import SimpleNamespace
    class Cursor:
        connection=SimpleNamespace(autocommit=False)
        def execute(self,sql,params):self.guard='assert_charlie_mission_connection' in sql
        def fetchone(self):return ('charlie_mission_connection_v1',APP,'hold_read',True) if self.guard else row
    result,code=store.owner_execution_hold_status(M,cursor=Cursor())
    assert code==503 and result['success'] is False and 'active' not in result
