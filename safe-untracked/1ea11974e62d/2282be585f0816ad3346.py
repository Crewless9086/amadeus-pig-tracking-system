"""Existing migration/role contracts against an explicitly disposable PostgreSQL."""
from datetime import datetime, timedelta, timezone
import json
import hashlib
import os
import re
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
M = 'CHARLIE-MISSION-IMAGE-ROLE-TEST'
REV = 'a' * 40


def disposable_role_dsn(dsn, role):
    """Distinct synthetic credentials for each explicitly disposable LOGIN."""
    assert dsn.startswith('host=127.0.0.1 ') and 'password=synthetic-' in dsn
    assert role in {'qualification_admin','native_recovery_test','service_role','image_app_nonbypass',
                    'image_denied','charlie_mission_application','charlie_owner_execution_hold_writer'}
    password='synthetic-qualification-20260909-'+hashlib.sha256(role.encode()).hexdigest()[:16]
    return re.sub(r'password=\S+', 'password='+password, re.sub(r'user=\S+', 'user='+role, dsn))


@pytest.fixture
def role_plane(monkeypatch, tmp_path):
    if os.environ.get('CHARLIE_TEST_IMAGE_ROLES') != '1':
        pytest.skip('requires owned disposable image-role database; no configured database fallback')
    import psycopg
    from modules.charlie import mission_store as store
    admin = os.environ['CHARLIE_TEST_POSTGRES_ADMIN_DSN']
    assert admin.startswith('host=127.0.0.1 ') and 'user=qualification_admin ' in admin
    assert 'dbname=charlie_roles_test ' in admin
    def dsn(role):
        return disposable_role_dsn(admin,role)
    def sql(command, params=(), role='qualification_admin'):
        with psycopg.connect(dsn(role)) as connection:
            with connection.cursor() as cursor:
                cursor.execute(command, params if params else None)
                return cursor.fetchall() if cursor.description else None
    sql('drop schema if exists public cascade; create schema public; grant usage on schema public to public')
    sql('create schema if not exists app_private; create table if not exists app_private.migration_log(migration_id text primary key,description text)')
    for filename in ('202606300001_create_charlie_mission_queue.sql', '202606300002_create_charlie_vault_v1_tables.sql',
                     '202607010002_create_charlie_core_v3_tables.sql',
                     '202607170001_create_charlie_executive_control_plane.sql',
                     '202607170002_create_charlie_private_executive_interface.sql',
                     '202607190002_create_domain_observer_runs.sql',
                     '202607190001_create_operational_event_fabric.sql', '202607270003_create_charlie_owner_execution_holds.sql',
                     '20260908141447_qualify_charlie_mission_database_privileges.sql'):
        sql((ROOT / 'supabase/migrations' / filename).read_text())
    sql('grant select,insert,update,delete on charlie_missions,charlie_mission_events,operational_events,operational_projection_checkpoints to service_role')
    sql('grant select,insert,update,delete on charlie_missions,charlie_mission_events to image_app_nonbypass')
    sql('grant select on charlie_owner_execution_hold_events to image_app_nonbypass')
    metadata = {'orchestration': {'generation_identity': 'g1'},
                'native_runner_blocker': {'blocker_fingerprint': 'f' * 64, 'runner_revision': REV, 'generation': 'g1'},
                'dispatch_authorization': {'generation': 'g1', 'base_sha': REV, 'owner_instruction_digest': 'b' * 64,
                                           'allowed_files': ['demo.py'], 'allowed_effects': ['edit_allowed_files']},
                'mission_vault': {'test_plan': ['synthetic-contract'], 'acceptance_criteria': ['synthetic outcome']}}
    sql('insert into charlie_missions(mission_id,status,raw_text,title,urgency,mission_type,approval_level,metadata_json) values(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)',
        (M, 'approved', 'Synthetic role test', 'Synthetic role test', 'normal', 'software', 'owner', json.dumps(metadata)))
    monkeypatch.setenv('DATABASE_URL', dsn('service_role'))
    monkeypatch.setenv('CHARLIE_MISSION_DATABASE_URL', dsn('charlie_mission_application'))
    monkeypatch.setenv('CHARLIE_OWNER_EXECUTION_HOLD_DATABASE_URL', dsn('charlie_owner_execution_hold_writer'))
    rows = sql('select rolname,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb from pg_roles where rolname in (%s,%s,%s,%s)',
               ('service_role', 'image_app_nonbypass', 'charlie_owner_execution_hold_writer', 'image_denied'))
    assert all(not row[1] for row in rows)
    assert next(row for row in rows if row[0] == 'service_role')[2] is True
    facts = {'roles': rows, 'table_owners': sql("select tablename,tableowner,rowsecurity from pg_tables where schemaname='public'"),
             'policies': sql("select tablename,policyname,roles::text,cmd,qual from pg_policies where schemaname='public'"),
             'functions': sql("select p.proname,p.prosecdef,r.rolname from pg_proc p join pg_namespace n on n.oid=p.pronamespace join pg_roles r on r.oid=p.proowner where n.nspname='public'"),
             'runtime_identity': sql('select session_user,current_user', role='charlie_mission_application'),
             'applied_actual_migrations': sql('select migration_id from app_private.migration_log order by migration_id')}
    (tmp_path / 'database-role-facts.json').write_text(json.dumps(facts, indent=2))
    return {'sql': sql, 'dsn': dsn, 'store': store, 'metadata': metadata}


def grant_for(plane):
    from modules.charlie.native_runner.recovery import scope_for
    return {'request_id': 'SYNTHETIC-IMAGE-OWNER-1',
            'scope': scope_for(M, plane['metadata'], {'worker_revision': REV, 'web_revision': REV}),
            'expires_at': (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            'limits': {'requests': 2, 'spend_microusd': 20, 'per_request_microusd': 10},
            'verification': [{'name': 'synthetic-contract', 'argv': ['python', '-m', 'unittest', 'tests.test_synthetic']} ]}


def test_nonowner_runtime_can_atomically_issue_consume_and_replay(role_plane):
    p = role_plane
    args = dict(authenticated_principal='owner-admin:synthetic-signed', runtime={'worker_revision': REV, 'web_revision': REV})
    request = grant_for(p)
    issued, code = p['store'].native_runner_recovery(M, 'issue', request, **args)
    assert code == 201, issued
    assert p['store'].native_runner_recovery(M, 'issue', request, **args)[1] == 200
    # Reuse exact bytes for replay, including the original expiry.
    grant = issued['receipt']['grant']
    consume = {'grant_id': grant['grant_id'], 'request_id': 'synthetic-consume', 'incarnation': 'synthetic-image-boot'}
    args['authenticated_principal'] = 'hermes:builder'
    receipt, code = p['store'].native_runner_recovery(M, 'consume', consume, **args)
    assert code == 201, receipt
    replay, code = p['store'].native_runner_recovery(M, 'consume', consume, **args)
    assert code == 200 and replay['receipt']['lease'] == receipt['receipt']['lease']
    assert p['sql']('select count(*) from charlie_mission_events')[0][0] == 2


def test_dedicated_hold_writer_and_runtime_visibility_veto(role_plane):
    p = role_plane
    hold, code = p['store'].create_owner_execution_hold(M, 'g1', 'synthetic role hold', owner_principal='synthetic-owner')
    assert code in {200, 201}, hold
    state, code = p['store'].owner_execution_hold_status(M)
    assert code == 200 and state['active'] is True
    result, code = p['store'].native_runner_recovery(M, 'issue', grant_for(p), authenticated_principal='owner-admin:synthetic-signed', runtime={'worker_revision': REV, 'web_revision': REV})
    assert code >= 400, result
    assert p['sql']('select metadata_json ? %s from charlie_missions where mission_id=%s', ('native_recovery', M))[0][0] is False
    assert p['sql']('select count(*) from charlie_mission_events')[0][0] == 0
    import psycopg
    with pytest.raises(psycopg.Error, match='owner_execution_hold_active'):
        p['sql']('update charlie_missions set title=%s where mission_id=%s', ('unauthorised synthetic change', M), role='charlie_mission_application')
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        p['sql']('select append_charlie_owner_execution_hold(%s,%s,%s,%s,%s,%s,%s::jsonb)', ('fake', 'fake', M, 'g1', 'no authority', 'a' * 64, '{}'), role='charlie_mission_application')


def test_nonbypass_visibility_is_not_misrepresented_as_deployed_role_proof(role_plane, tmp_path):
    p = role_plane
    hold, code = p['store'].create_owner_execution_hold(M, 'g1', 'synthetic hidden hold', owner_principal='synthetic-owner')
    assert code in {200, 201}, hold
    # This is an explicit incompatible-role probe, not a policy added to pass.
    hidden, code = p['store'].owner_execution_hold_status(M, database_url=p['dsn']('image_app_nonbypass'))
    assert code == 503 and hidden['success'] is False and 'active' not in hidden
    result, code = p['store'].native_runner_recovery(M, 'issue', grant_for(p), authenticated_principal='owner-admin:synthetic-signed',
                                                  runtime={'worker_revision': REV, 'web_revision': REV}, database_url=p['dsn']('image_app_nonbypass'))
    assert code >= 400, result
    assert p['sql']('select metadata_json ? %s from charlie_missions where mission_id=%s', ('native_recovery', M))[0][0] is False
    assert p['sql']('select count(*) from charlie_mission_events')[0][0] == 0
    (tmp_path / 'nonbypass-visibility-limit.json').write_text(json.dumps({'incompatible_role_readback': hidden, 'grant_result': result,
        'grant_http_status': code, 'actual_trigger_prevents_mutation': True,
        'release_gate': 'The incompatible role now fails closed. Deployed authenticated mission identity and policy contract remain unverified.'}, indent=2))


def test_missing_privilege_fails_without_authority_or_events(role_plane):
    p = role_plane
    result, code = p['store'].native_runner_recovery(M, 'read', {}, authenticated_principal='hermes:builder',
                                                  runtime={'worker_revision': REV, 'web_revision': REV}, database_url=p['dsn']('image_denied'))
    assert code >= 400 and result['success'] is False
    assert p['sql']('select count(*) from charlie_mission_events')[0][0] == 0


def test_full_application_positive_role_and_negative_http_contracts(role_plane, monkeypatch):
    p = role_plane
    import sys
    assert sys.prefix == '/usr/local', 'Actual application role qualification must use application Python'
    for key, value in {'OWNER_ACCESS_ENABLED': '1', 'OWNER_ACCESS_ALLOW_LOCAL_DEV': '0',
                       'OWNER_ADMIN_TOKEN': 'synthetic-owner-admin-' + 'a' * 40,
                       'OWNER_SESSION_SECRET': 'synthetic-owner-session-' + 'b' * 40,
                       'CHARLIE_HERMES_GATEWAY_TOKEN': 'synthetic-worker-' + 'c' * 40,
                       'RENDER_GIT_COMMIT': REV}.items():
        monkeypatch.setenv(key, value)
    import threading
    from unittest.mock import patch
    def denied_start(*args, **kwargs):
        raise RuntimeError('Unexpected application background startup')
    with patch.object(threading.Thread, 'start', denied_start):
        import app
    assert 'charlie' in app.app.blueprints
    from modules.auth import owner_access
    client = app.app.test_client()
    path = '/api/charlie/hermes/native-executions/resumable'
    assert client.get(path).status_code == 403
    bearer = {'Authorization': 'Bearer ' + os.environ['CHARLIE_HERMES_GATEWAY_TOKEN']}
    response = client.get(path, headers=bearer)
    assert response.status_code == 200, response.get_json()
    owner_path = '/api/charlie/build-relay/missions/' + M + '/native-runner/resume'
    assert client.post(owner_path, json=grant_for(p), headers=bearer).status_code == 403
    with client.session_transaction() as session:
        session['owner_access'] = {'role': 'admin', 'principal_id': owner_access._stable_owner_principal('admin')}
    response = client.post(owner_path, json=grant_for(p), headers={'X-CHARLIE-Owner-Action': 'native_runner_resume'})
    assert response.status_code == 201, response.get_json()
    assert p['sql']('select count(*) from charlie_mission_events')[0][0] == 1
    from services.database_service import check_database_health
    assert check_database_health()[1] == 200
    # Independent selectors: a missing shared DB remains unhealthy, while the
    # configured mission connection continues to provide canonical reads.
    shared_url = os.environ['DATABASE_URL']
    monkeypatch.delenv('DATABASE_URL')
    assert check_database_health()[1] == 503
    assert client.get(path, headers=bearer).status_code == 200
    monkeypatch.setenv('DATABASE_URL',shared_url)
    monkeypatch.delenv('CHARLIE_MISSION_DATABASE_URL')
    assert client.get(path, headers=bearer).status_code == 503
    assert check_database_health()[1] == 200
