"""Restoration index: closed preparation, immutable prefix, and receipt custody."""
import hashlib
import re
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from psycopg.pq import TransactionStatus
from scripts import rootline_accounting_index as index
from scripts import run_render_production_migrations as rail
from scripts import apply_supabase_migration as single
from tests import test_rootline_accounting_index_migration as accounting
from tests.test_rootline_accounting_index_migration import ready as accounting_ready
from tests.test_render_rootline_a_migration_rail import predecessor, purpose_predecessor
from tests import test_render_production_migration_rail as legacy

ITEM = next(item for item in rail.ALLOWLIST if item.migration_id == index.RESTORATION_MIGRATION_ID)
PREFIX = rail.ALLOWLIST[:rail.ALLOWLIST.index(ITEM)]

@pytest.fixture(autouse=True)
def restoration_prefix_only():
    # Preserve this historical ceremony when a later reviewed index is appended.
    with patch.object(rail, "ALLOWLIST", PREFIX + (ITEM,)):
        yield



def test_exact_append_only_registration_and_clean_ci_order():
    assert len(PREFIX) == 11 and PREFIX[-1].migration_id == index.MIGRATION_ID
    assert ITEM.migration_id not in rail.BASELINE_ELIGIBLE_IDS
    assert ITEM.migration_id not in rail.LEGACY_ADOPTION_RECEIPT_IDS
    sql = rail._load_sql(ITEM)
    assert hashlib.sha256(sql.encode()).hexdigest() == ITEM.sha256
    assert index.RESTORATION_EXPECTED_DEFINITION.replace("'", "''") in sql
    assert index.FAILURE_EXPECTED_DEFINITION.replace("'", "''") in sql
    assert index.RESTORATION_DESCRIPTION in sql
    statements = re.sub(r"'(?:''|[^'])*'", "''", sql)
    assert 'CREATE INDEX' not in statements and 'DROP ' not in statements
    assert 'indisvalid' in sql and 'indisready' in sql and 'indislive' in sql
    workflow = (rail.REPO_ROOT / '.github/workflows/oom-sakkie-audit-rails.yml').read_text()
    before = 'python scripts/apply_supabase_migration.py supabase/migrations/' + PREFIX[-1].filename
    after = 'python scripts/apply_supabase_migration.py supabase/migrations/' + ITEM.filename
    assert workflow.index(before) < workflow.index(after)
    assert 'tests/test_rootline_restoration_index_migration.py' in workflow
    assert single.prepare_index is index.prepare_index


class Result:
    def __init__(self, rows): self.rows = rows
    def fetchone(self): return self.rows[0] if self.rows else None
    def fetchall(self): return self.rows


class IndexConnection:
    def __init__(self, migration_id, *, existing=False):
        self.contracts = index._contracts(migration_id)
        self.name, self.definition, self.create, self.error = self.contracts[0]
        self.rows = {name: ('i', definition, True, True, True) if existing else None
                     for name, definition, _create, _error in self.contracts}
        self.autocommit = True
        self.info = SimpleNamespace(transaction_status=TransactionStatus.IDLE)
        self.settings = {'statement_timeout': 300000, 'lock_timeout': 60000}
        self.calls = []
        self.fail_build = False
        self.fail_name = None
    @property
    def row(self): return self.rows[self.name]
    @row.setter
    def row(self, value): self.rows[self.name] = value
    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if 'from pg_catalog.pg_class c' in sql:
            row = self.rows[params[0]]
            return Result([] if row is None else [row])
        if 'from pg_catalog.pg_settings' in sql:
            return Result(list(self.settings.items()))
        if 'pg_catalog.set_config' in sql:
            self.settings[params[0]] = int(params[1])
            return Result([(params[1],)])
        for name, definition, create, _error in self.contracts:
            if sql == create:
                assert self.settings == {'statement_timeout': 180000, 'lock_timeout': 30000}
                if self.fail_build or self.fail_name == name:
                    raise RuntimeError('synthetic_build_failure')
                self.rows[name] = ('i', definition, True, True, True)
                return Result([])
        raise AssertionError(sql)


@pytest.mark.parametrize('migration_id', [index.MIGRATION_ID, index.RESTORATION_MIGRATION_ID])
def test_shared_helper_prepares_once_with_bounded_restored_timeouts(migration_id):
    db = IndexConnection(migration_id)
    assert index.prepare_index(db, migration_id) == 'created_exact_valid'
    assert db.settings == {'statement_timeout': 300000, 'lock_timeout': 60000}
    assert index.prepare_index(db, migration_id) == 'existing_exact_valid'
    assert all(sum(sql == contract[2] for sql, _ in db.calls) == 1 for contract in db.contracts)
    assert db.create.startswith('CREATE INDEX CONCURRENTLY ')
    assert not any('DROP ' in sql for sql, _ in db.calls)


@pytest.mark.parametrize('position,value', [(0, 'r'), (1, 'wrong definition'), (2, False), (3, False), (4, False)])
def test_wrong_or_invalid_restoration_index_is_preserved_and_rejected(position, value):
    db = IndexConnection(index.RESTORATION_MIGRATION_ID, existing=True)
    row = list(db.row); row[position] = value; db.row = tuple(row)
    with pytest.raises(RuntimeError, match='definition_or_state_mismatch'):
        index.prepare_index(db, index.RESTORATION_MIGRATION_ID)
    assert not any(sql == db.create or 'DROP ' in sql for sql, _ in db.calls)


@pytest.mark.parametrize('autocommit,status', [(False, TransactionStatus.IDLE), (True, TransactionStatus.INTRANS)])
def test_restoration_preparation_never_commits_caller_transaction(autocommit, status):
    db = IndexConnection(index.RESTORATION_MIGRATION_ID)
    db.autocommit = autocommit; db.info.transaction_status = status
    with pytest.raises(RuntimeError, match='requires_idle_autocommit'):
        index.prepare_index(db, index.RESTORATION_MIGRATION_ID)
    assert not db.calls


def test_restoration_build_failure_restores_limits_and_never_drops():
    db = IndexConnection(index.RESTORATION_MIGRATION_ID); db.fail_build = True
    with pytest.raises(RuntimeError, match='synthetic_build_failure'):
        index.prepare_index(db, index.RESTORATION_MIGRATION_ID)
    assert db.settings == {'statement_timeout': 300000, 'lock_timeout': 60000}
    assert not any('DROP ' in sql for sql, _ in db.calls)


def index_row():
    return ['public', 'sam_live_stock_conversation_review_events', index.RESTORATION_INDEX_NAME,
            False, False, True, True, index.RESTORATION_EXPECTED_DEFINITION]


def test_prior_checkpoint_comparison_removes_only_exact_prepared_addition():
    db = IndexConnection(index.RESTORATION_MIGRATION_ID, existing=True)
    other = ['public', 'sam_live_stock_conversation_review_events', 'existing_index', False, False, True, True, 'old']
    manifest = {'scope': {'relations': [index.TABLE_NAME]}, 'indexes': [other, index_row()], 'columns': ['unchanged']}
    before = deepcopy(manifest)
    result = rail._prior_catalog_without_prepared_restoration(db, manifest)
    assert result == {**before, 'indexes': [other]}
    assert manifest == before
    assert result['columns'] == ['unchanged']


@pytest.mark.parametrize('mutate', ['definition', 'duplicate', 'invalid', 'unique'])
def test_prepared_index_catalog_mismatch_cannot_be_subtracted(mutate):
    db = IndexConnection(index.RESTORATION_MIGRATION_ID, existing=True)
    rows = [index_row()]
    if mutate == 'definition': rows[0][-1] = 'wrong'
    if mutate == 'duplicate': rows.append(index_row())
    if mutate == 'invalid': rows[0][5] = False
    if mutate == 'unique': rows[0][3] = True
    with pytest.raises(RuntimeError, match='catalog_mismatch'):
        rail._prior_catalog_without_prepared_restoration(db, {'indexes': rows})
    assert not db.calls


@pytest.fixture
def ready_restoration(accounting_ready):
    # Existing accounting fixture installs prefix10 and the canonical review rail.
    with patch.object(rail, 'ALLOWLIST', PREFIX):
        rail.run(legacy.DATABASE_URL, legacy.ENV)
    return True


def test_real_restoration_concurrent_build_receipt_replay_and_history_preserved(ready_restoration):
    with accounting.connect() as db:
        before = accounting.state(db)
    first = rail.run(legacy.DATABASE_URL, legacy.ENV)
    assert first['restoration_index_preparation'] == 'created_exact_valid'
    with accounting.connect() as db:
        assert index.verify_index(db, migration_id=ITEM.migration_id)
        after = accounting.state(db)
        assert before[3] == after[3]
        assert rail._verify_migration_log(db, ITEM.migration_id, required=True) == index.RESTORATION_DESCRIPTION
    second = rail.run(legacy.DATABASE_URL, legacy.ENV)
    assert second['restoration_index_preparation'] == 'existing_exact_valid'
    assert second['migrations'][-1]['receipt_id'] == first['migrations'][-1]['receipt_id']
    with accounting.connect() as db: assert accounting.state(db) == after


def test_real_prepared_index_survives_rollback_then_same_prefix_retries(ready_restoration):
    with accounting.connect() as db: before = accounting.state(db)
    original = rail._verify_migration_readback
    def fail(db, item):
        result = original(db, item)
        if item == ITEM: raise RuntimeError('synthetic_restoration_postcondition_failure')
        return result
    with patch.object(rail, '_verify_migration_readback', side_effect=fail):
        with pytest.raises(RuntimeError, match='restoration_index_may_persist'):
            rail.run(legacy.DATABASE_URL, legacy.ENV)
    with accounting.connect() as db:
        assert accounting.state(db) == before
        assert index.verify_index(db, migration_id=ITEM.migration_id)
    assert rail.run(legacy.DATABASE_URL, legacy.ENV)['migrations'][-1]['outcome'] == 'applied'


def test_real_unrelated_catalog_drift_stops_before_restoration_build(ready_restoration):
    with accounting.connect() as db:
        db.execute('alter table public.sam_live_stock_conversation_review_events add column synthetic_drift text')
        before = accounting.state(db)
    with pytest.raises(RuntimeError, match='catalog_drift'):
        rail.run(legacy.DATABASE_URL, legacy.ENV)
    with accounting.connect() as db:
        assert accounting.state(db) == before
        assert not index.verify_index(db, migration_id=ITEM.migration_id, required=False)


def test_real_wrong_restoration_index_is_not_repaired(ready_restoration):
    with accounting.connect() as db:
        db.execute('create index idx_rootline_ewelink_restoration_scope_created on public.sam_live_stock_conversation_review_events(created_at)')
        before = accounting.state(db)
    with pytest.raises(RuntimeError): rail.run(legacy.DATABASE_URL, legacy.ENV)
    with accounting.connect() as db:
        assert accounting.state(db) == before
        with pytest.raises(RuntimeError, match='definition_or_state_mismatch'):
            index.verify_index(db, migration_id=ITEM.migration_id)


def test_real_single_runner_uses_same_preparation_and_log(ready_restoration, monkeypatch):
    monkeypatch.setenv(single.DATABASE_URL_ENV, legacy.DATABASE_URL)
    monkeypatch.setattr(single, 'load_dotenv', lambda *args: None)
    monkeypatch.setattr('sys.argv', ['apply_supabase_migration.py', 'supabase/migrations/' + ITEM.filename])
    assert single.main() == 0 and single.main() == 0
    with accounting.connect() as db:
        assert index.verify_index(db, migration_id=ITEM.migration_id)
        assert rail._verify_migration_log(db, ITEM.migration_id, required=True) == index.RESTORATION_DESCRIPTION


def test_wrong_failure_sibling_rejected_before_restoration_creation():
    db = IndexConnection(index.RESTORATION_MIGRATION_ID)
    db.rows[index.FAILURE_INDEX_NAME] = ('i', 'wrong definition', True, True, True)
    with pytest.raises(RuntimeError, match='rootline_failure_index_definition_or_state_mismatch'):
        index.prepare_index(db, index.RESTORATION_MIGRATION_ID)
    assert not any(sql.startswith('CREATE ') for sql, _ in db.calls)


def test_partial_two_index_build_preserved_then_missing_member_only_is_created():
    db = IndexConnection(index.RESTORATION_MIGRATION_ID)
    db.fail_name = index.FAILURE_INDEX_NAME
    with pytest.raises(RuntimeError, match='synthetic_build_failure'):
        index.prepare_index(db, index.RESTORATION_MIGRATION_ID)
    assert db.rows[index.RESTORATION_INDEX_NAME] is not None
    assert db.rows[index.FAILURE_INDEX_NAME] is None
    db.fail_name = None; db.calls.clear()
    assert index.prepare_index(db, index.RESTORATION_MIGRATION_ID) == 'created_exact_valid'
    assert [sql for sql, _ in db.calls if sql.startswith('CREATE ')] == [index.FAILURE_CREATE_SQL]


def test_prior_checkpoint_removes_both_exact_additions_without_hiding_other_drift():
    db = IndexConnection(index.RESTORATION_MIGRATION_ID, existing=True)
    failure = ['public', 'sam_live_stock_conversation_review_events', index.FAILURE_INDEX_NAME,
               False, False, True, True, index.FAILURE_EXPECTED_DEFINITION]
    manifest = {'indexes': [index_row(), failure], 'columns': ['unrelated drift retained']}
    assert rail._prior_catalog_without_prepared_restoration(db, manifest) == {
        'indexes': [], 'columns': ['unrelated drift retained']}


def test_real_missing_accounting_predecessor_blocks_both_outage_indexes(accounting_ready):
    with pytest.raises(RuntimeError, match='predecessor_not_applied'):
        rail.run(legacy.DATABASE_URL, legacy.ENV)
    with accounting.connect() as db:
        assert not index.verify_index(db, migration_id=ITEM.migration_id, required=False)
        assert db.execute('select count(*) from app_private.migration_log where migration_id=%s',
                          (ITEM.migration_id,)).fetchone()[0] == 0


def test_real_second_build_failure_retains_first_index_and_retries(ready_restoration):
    import psycopg
    original = psycopg.Connection.execute
    def fail(db, sql, *args, **kwargs):
        if sql == index.FAILURE_CREATE_SQL: raise RuntimeError('synthetic_second_build_failure')
        return original(db, sql, *args, **kwargs)
    with patch.object(psycopg.Connection, 'execute', fail):
        with pytest.raises(RuntimeError, match='synthetic_second_build_failure'):
            rail.run(legacy.DATABASE_URL, legacy.ENV)
    with accounting.connect() as db:
        assert index._verify_contract(db, index._contracts(ITEM.migration_id)[0])
        assert not index._verify_contract(db, index._contracts(ITEM.migration_id)[1], required=False)
        assert db.execute('select count(*) from app_private.migration_log where migration_id=%s',
                          (ITEM.migration_id,)).fetchone()[0] == 0
    assert rail.run(legacy.DATABASE_URL, legacy.ENV)['migrations'][-1]['outcome'] == 'applied'


def test_real_two_outage_migration_runners_serialize(ready_restoration):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: rail.run(legacy.DATABASE_URL, legacy.ENV), range(2)))
    assert sorted(r['migrations'][-1]['outcome'] for r in results) == ['already_applied', 'applied']
    assert len({r['migrations'][-1]['receipt_id'] for r in results}) == 1


def test_real_failure_predicate_equivalence_including_malformed_json():
    from psycopg.types.json import Jsonb
    from modules.telemetry import rootline_provider_availability as provider
    from tests.test_rootline_provider_outage_visibility import QueueConnection, event, NOW, SCOPE
    latest = event('LATEST')
    capture = QueueConnection([[latest], [], []])
    with pytest.raises(ValueError, match='incident_unproven'):
        provider.read_provider_availability(now=NOW, connect=lambda **kwargs: capture, environ={"ROOTLINE_INPUT_HEALTH_ENABLED": "true"})
    current_sql, current_params = capture.queries[2]
    key = "->(review_json->'ewelink_request_budget'->'detail'->>'scope')"
    assert current_sql.count(key) == 1
    old_sql = current_sql.replace(key, '->%s')
    old_params = (*current_params, SCOPE)
    base = event('ROW')[2]
    cases = []
    for action in ('request_completed', 'snapshot_validation_failed'):
        value = deepcopy(base); value['action'] = action; cases.append((action, value))
    for label, category in [('success', None), ('empty_category', ''), ('object_category', {'bad': True})]:
        value = deepcopy(base); value['state']['scopes'][SCOPE]['category'] = category
        cases.append((label, value))
    for label, detail in [('missing_scope', {}), ('null_scope', {'scope': None}),
                          ('other_scope', {'scope': 'b'*64}), ('scalar_detail', 'malformed')]:
        value = deepcopy(base); value['detail'] = detail; cases.append((label, value))
    for label, scopes in [('missing_category', {SCOPE: {}}), ('missing_scope_state', {}),
                          ('null_scopes', None), ('scalar_scopes', 'malformed')]:
        value = deepcopy(base); value['state']['scopes'] = scopes; cases.append((label, value))
    malformed = deepcopy(base); malformed['detail'] = {'scope': SCOPE}
    cases.append(('malformed_failure_detail', malformed))
    cte = """with candidate_events(review_event_id,created_at,event_source,chatwoot_conversation_id,review_json)
        as (values (%s::text,%s::timestamptz,%s::text,%s::text,%s::jsonb)) """
    with accounting.connect() as db:
        for label, body in cases:
            prefix = ('A-ROW', NOW, provider.EVENT_SOURCE, provider.LEDGER_ID,
                      Jsonb({'ewelink_request_budget': body}))
            old = db.execute(cte + old_sql.replace(provider.TABLE, 'candidate_events'),
                             (*prefix, *old_params)).fetchall()
            current = db.execute(cte + current_sql.replace(provider.TABLE, 'candidate_events'),
                                 (*prefix, *current_params)).fetchall()
            assert current == old, label
            if label == 'malformed_failure_detail':
                assert current
                with pytest.raises(ValueError, match='failure_invalid'):
                    provider.project_scope(SCOPE, latest, current[0], None, now=NOW)
