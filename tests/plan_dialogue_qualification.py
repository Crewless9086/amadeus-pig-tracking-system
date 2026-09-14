"""Isolated synthetic plan-dialogue qualification; never a production entrypoint."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import runpy
import socket
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATABASE_NAME = 'plan_dialogue_test'
MODULES = [
    'tests/test_oom_sakkie_plan_dialogue_postgres.py',
    'tests/test_herdmaster_health_loss_recording_postgres.py',
    'tests/test_oom_sakkie_protected_delivery_postgres.py',
    'tests/test_oom_sakkie_protected_breeding_claim_postgres.py',
]
UNIT_MODULES = [
    'tests/test_oom_sakkie_plan_dialogue.py',
    'tests/test_oom_sakkie_typed_welfare_dialogue.py',
    'tests/test_oom_sakkie_manager_question_runtime.py',
    'tests/test_oom_sakkie_daily_farm_manager.py',
    'tests/test_oom_sakkie_herdmaster_health_loss_runtime.py',
    'tests/test_oom_sakkie_semantic_front_door.py',
    'tests/test_oom_sakkie_herdmaster_health_loss_preview.py',
    'tests/test_herdmaster_natural_health_loss_intake.py',
    'tests/test_herdmaster_health_loss_recording.py',
    'tests/test_oom_sakkie_protected_action_runtime.py',
    'tests/test_oom_sakkie_family_message_lifecycle.py',
    'tests/test_oom_sakkie_owner_task_gateway.py',
    'tests/test_oom_sakkie_family_rootline_callback.py',
    'tests/test_oom_sakkie_family_runtime.py',
]


def isolate():
    """Require an explicit disposable database and strip all inherited secrets."""
    dsn = os.environ.get('PLAN_DIALOGUE_POSTGRES_URL', '')
    parsed = urlparse(dsn)
    if (parsed.scheme not in {'postgres', 'postgresql'}
            or parsed.hostname not in {'127.0.0.1', 'localhost'}
            or parsed.path != '/' + DATABASE_NAME or parsed.query or parsed.fragment):
        raise RuntimeError('Explicit loopback herd qualification database required')
    kept = {key: value for key, value in os.environ.items() if key.upper() in {
        'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT', 'SYSTEMDRIVE',
        'PROCESSOR_ARCHITECTURE', 'NUMBER_OF_PROCESSORS', 'LOCALAPPDATA', 'APPDATA',
        'LANG', 'LC_ALL', 'TMP', 'TEMP', 'TMPDIR',
    }}
    os.environ.clear()
    os.environ.update(kept)
    os.environ.update({
        'DATABASE_URL': dsn, 'CHARLIE_DISPOSABLE_POSTGRES_URL': dsn,
        'ALLOW_SUPABASE_WRITES_IN_TESTS': '1',
        'PIG_WELFARE_CASE_RUNTIME_ENABLED': 'true',
        'PYTHON_DOTENV_DISABLED': '1', 'PYTHONDONTWRITEBYTECODE': '1',
        'PYTHONUNBUFFERED': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
        'OWNER_ACCESS_ENABLED': 'true', 'OWNER_ACCESS_ALLOW_LOCAL_DEV': 'false',
        'OWNER_SESSION_SECRET': 'synthetic-session-only-' + 's' * 40,
        'OWNER_READ_TOKEN': 'synthetic-read-only-' + 'r' * 40,
        'OWNER_ADMIN_TOKEN': 'synthetic-admin-only-' + 'a' * 40,
    })
    sys.dont_write_bytecode = True
    os.chdir(ROOT)
    import dotenv
    dotenv.load_dotenv = lambda *args, **kwargs: False

    def check_address(address):
        if not isinstance(address, tuple):
            raise RuntimeError('Non-loopback connection blocked by herd qualification')
        host = str(address[0])
        if host == 'localhost':
            return
        try:
            if ipaddress.ip_address(host).is_loopback:
                return
        except ValueError:
            pass
        raise RuntimeError('External connection blocked by herd qualification')

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def local_connect(sock, address):
        check_address(address)
        return original_connect(sock, address)

    def local_connect_ex(sock, address):
        check_address(address)
        return original_connect_ex(sock, address)

    socket.socket.connect = local_connect
    socket.socket.connect_ex = local_connect_ex

    # libpq uses native sockets, so fence its connection parameters separately.
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    original_pg_connect = psycopg.connect

    def local_pg_connect(conninfo='', *args, **kwargs):
        info = conninfo_to_dict(conninfo, **{key: value for key, value in kwargs.items()
            if key in {'host', 'hostaddr', 'port', 'dbname'}})
        hosts = [info[key] for key in ('host', 'hostaddr') if info.get(key)]
        if (not hosts or any(host not in {'127.0.0.1', 'localhost', '::1'} for host in hosts)
                or info.get('dbname') != DATABASE_NAME):
            raise RuntimeError('External or non-fixture libpq connection blocked')
        return original_pg_connect(conninfo, *args, **kwargs)

    psycopg.connect = local_pg_connect
    return dsn


def bootstrap(dsn):
    """Apply existing SQL only to a fresh isolated test database."""
    import psycopg
    with psycopg.connect(dsn) as db:
        assert not db.execute("select 1 from pg_tables where schemaname not in ('pg_catalog','information_schema') limit 1").fetchone(), 'Fresh empty fixture database required'
        db.execute('''
            do $$ begin create role anon nologin; exception when duplicate_object then null; end $$;
            do $$ begin create role authenticated nologin; exception when duplicate_object then null; end $$;
            do $$ begin create role service_role nologin bypassrls; exception when duplicate_object then null; end $$;
            alter default privileges in schema public grant all privileges on tables to service_role;
        ''')
    workflow = (ROOT / '.github/workflows/oom-sakkie-audit-rails.yml').read_text(encoding='utf-8')
    audit = re.findall(r'python scripts/apply_supabase_migration.py (supabase/migrations/\S+\.sql)', workflow)
    assert audit, 'Existing audit schema preparation must be present'
    prefix = [
        '202605210001_foundation_migration_log.sql',
        '202605210002_create_order_sales_tables.sql',
        '202605210003_create_sales_transaction_tables.sql',
        '202605210004_add_sales_transaction_payment_date.sql',
        '202606140001_create_oom_sakkie_sales_campaigns.sql',
        '202606280001_create_bulk_weight_batch_tables.sql',
        '202606290001_create_farm_canonical_tables.sql',
        '202606290002_add_pig_exit_fields.sql',
        '202606290003_add_litter_lifecycle_fields.sql',
        '202607130001_create_meat_processing_batches.sql',
    ]
    extra = [
        '202607200001_create_pig_observation_events.sql',
        '202608160004_add_protected_delivery_lifecycle.sql',
        '202607070001_create_sam_live_stock_conversation_review_events.sql',
        '202607300001_create_litter_supersession_rail.sql',
        '202608080001_add_governed_livestock_auction_sales.sql',
    ]
    sequence = list(dict.fromkeys([*(f'supabase/migrations/{name}' for name in prefix),
        *audit, *(f'supabase/migrations/{name}' for name in extra)]))
    for relative in sequence:
        source = ROOT / relative
        with psycopg.connect(dsn) as db:
            db.execute(source.read_text(encoding='utf-8'))
        print(json.dumps({'classification': 'synthetic_disposable_schema_only',
            'source': relative, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}), flush=True)
    print(f'Disposable herd schema ready: {len(sequence)} existing SQL files', flush=True)


class RequireExecution:
    """A green required check must collect every named module and skip nothing."""
    def __init__(self, modules):
        self.modules = modules

    def pytest_collection_finish(self, session):
        import pytest
        collected = {item.nodeid.split('::', 1)[0] for item in session.items}
        missing = set(self.modules) - collected
        if missing:
            pytest.exit('Required herd modules collected no tests: ' + ', '.join(sorted(missing)), returncode=1)

    def pytest_sessionfinish(self, session, exitstatus):
        reporter = session.config.pluginmanager.getplugin('terminalreporter')
        allowed = ('tests/test_oom_sakkie_manager_question_runtime.py::'
            'test_existing_earlier_process_alarm_is_not_suppressed_and_late_connection_closes')
        skipped = reporter.stats.get('skipped', []) if reporter else []
        unexpected = [row for row in skipped if not (sys.platform == 'win32' and row.nodeid == allowed)]
        if session.testscollected == 0 or unexpected:
            session.exitstatus = 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['bootstrap', 'postgres', 'unit', 'serve'])
    mode = parser.parse_args().mode
    dsn = isolate()
    if mode == 'bootstrap':
        bootstrap(dsn)
    elif mode == 'postgres':
        os.environ['OOM_PROTECTED_ACTION_POSTGRES_URL'] = dsn
        import psycopg
        with psycopg.connect(dsn) as db:
            assert db.execute('SELECT count(*) FROM public.pigs').fetchone()[0] == 0, 'Fresh empty herd fixture required before the complete suite'
            assert db.execute('SELECT count(*) FROM public.litters').fetchone()[0] == 0, 'Fresh empty litter fixture required before the complete suite'
            assert db.execute('SELECT count(*) FROM public.pig_welfare_cases').fetchone()[0] == 0, 'Fresh empty welfare fixture required before the complete suite'
            assert db.execute('SELECT count(*) FROM app_private.oom_protected_action_claims').fetchone()[0] == 0, 'Fresh empty recovery fixture required before the complete suite'
        import pytest
        raise SystemExit(pytest.main(['-p', 'no:cacheprovider', '-q', *MODULES], plugins=[RequireExecution(MODULES)]))
    elif mode == 'unit':
        for key in ('DATABASE_URL', 'CHARLIE_DISPOSABLE_POSTGRES_URL'):
            os.environ.pop(key, None)
        import pytest
        raise SystemExit(pytest.main(['-p', 'no:cacheprovider', '-q', *UNIT_MODULES], plugins=[RequireExecution(UNIT_MODULES)]))
    else:
        runpy.run_module('tests.plan_dialogue_qualification_server', run_name='__main__')


if __name__ == '__main__':
    main()
