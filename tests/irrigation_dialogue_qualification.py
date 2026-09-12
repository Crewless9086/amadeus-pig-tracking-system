"""Disposable PostgreSQL and local browser qualification for irrigation dialogue."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests import plan_dialogue_qualification as base

DATABASE_NAME = 'irrigation_dialogue_test'
base.DATABASE_NAME = DATABASE_NAME
MODULES = ['tests/test_oom_sakkie_irrigation_dialogue_postgres.py', *base.MODULES]
UNIT_MODULES = list(dict.fromkeys([*base.UNIT_MODULES,
    'tests/test_oom_sakkie_irrigation_dialogue.py',
    'tests/test_oom_sakkie_owner_operational_continuation.py',
    'tests/test_oom_sakkie_operational_specialist_intake.py',
    'tests/test_rootline_irrigation_lifecycle.py',
    'tests/test_rootline_owner_status.py',
    'tests/test_oom_sakkie_rootline_operational_adapter.py']))


def isolate():
    os.environ['PLAN_DIALOGUE_POSTGRES_URL'] = os.environ.get('IRRIGATION_DIALOGUE_POSTGRES_URL', '')
    return base.isolate()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['bootstrap', 'unit', 'postgres', 'serve'])
    mode = parser.parse_args().mode
    dsn = isolate()
    if mode == 'bootstrap':
        base.bootstrap(dsn)
        import psycopg
        for name in ('202607280001_create_rootline_water_energy_plans.sql',
                     '202608030001_extend_rootline_fraction_observations.sql'):
            path = ROOT / 'supabase/migrations' / name
            with psycopg.connect(dsn) as db:
                if db.execute('select 1 from app_private.migration_log where migration_id=%s', (path.stem,)).fetchone():
                    continue
                db.execute(path.read_text(encoding='utf-8'))
            print(json.dumps({'classification':'synthetic_disposable_schema_only',
                'source': str(path.relative_to(ROOT)), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}), flush=True)
    elif mode == 'postgres':
        os.environ['OOM_PROTECTED_ACTION_POSTGRES_URL'] = dsn
        import pytest
        raise SystemExit(pytest.main(['-p','no:cacheprovider','-q',*MODULES],
            plugins=[base.RequireExecution(MODULES)]))
    elif mode == 'unit':
        for key in ('DATABASE_URL','CHARLIE_DISPOSABLE_POSTGRES_URL'):
            os.environ.pop(key,None)
        import pytest
        raise SystemExit(pytest.main(['-p','no:cacheprovider','-q',*UNIT_MODULES],
            plugins=[base.RequireExecution(UNIT_MODULES)]))
    else:
        runpy.run_module('tests.irrigation_dialogue_qualification_server', run_name='__main__')


if __name__ == '__main__':
    main()
