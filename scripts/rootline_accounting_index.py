"""Closed reviewed concurrent-index contracts shared by both migration runners."""
from psycopg.pq import TransactionStatus

MIGRATION_ID = "20261116211107_rootline_accounting_nonzero_window_index"
INDEX_NAME = "idx_sam_review_budget_nonzero_window"
TABLE_NAME = "public.sam_live_stock_conversation_review_events"
DESCRIPTION = "Add exact nonzero request-accounting window index; preserve canonical ledger and charging semantics."
EXPECTED_DEFINITION = ("CREATE INDEX " + INDEX_NAME + " ON " + TABLE_NAME
    + " USING btree (chatwoot_conversation_id, event_source, created_at) WHERE "
    + "(((review_json #>> '{ewelink_request_budget,attempt_units}'::text[]) COLLATE \"C\") IS DISTINCT FROM '0'::text)")
CREATE_SQL = ("CREATE INDEX CONCURRENTLY " + INDEX_NAME + " ON " + TABLE_NAME
    + " (chatwoot_conversation_id, event_source, created_at) WHERE "
    + "(review_json #>> '{ewelink_request_budget,attempt_units}') COLLATE \"C\" IS DISTINCT FROM '0'")

RESTORATION_MIGRATION_ID = '20261120182628_rootline_ewelink_restoration_scope_index'
RESTORATION_INDEX_NAME = 'idx_rootline_ewelink_restoration_scope_created'
RESTORATION_DESCRIPTION = 'Add exact provider-failure and restoration scope indexes; preserve outage identity and canonical receipt semantics.'
RESTORATION_EXPECTED_DEFINITION = "CREATE INDEX idx_rootline_ewelink_restoration_scope_created ON public.sam_live_stock_conversation_review_events USING btree (chatwoot_conversation_id, ((((review_json -> 'ewelink_request_budget'::text) -> 'detail'::text) ->> 'scope'::text)), created_at DESC, review_event_id DESC) WHERE ((event_source = 'rootline_provider_availability'::text) AND (((review_json -> 'ewelink_request_budget'::text) ->> 'action'::text) = 'complete_snapshot_restored_availability'::text))"
RESTORATION_CREATE_SQL = "CREATE INDEX CONCURRENTLY idx_rootline_ewelink_restoration_scope_created\nON public.sam_live_stock_conversation_review_events\n    (chatwoot_conversation_id,\n     ((review_json->'ewelink_request_budget'->'detail'->>'scope')),\n     created_at DESC, review_event_id DESC)\nWHERE event_source = 'rootline_provider_availability'\n  AND review_json->'ewelink_request_budget'->>'action' =\n      'complete_snapshot_restored_availability'"
FAILURE_INDEX_NAME = 'idx_rootline_ewelink_failure_scope_created'
FAILURE_EXPECTED_DEFINITION = "CREATE INDEX idx_rootline_ewelink_failure_scope_created ON public.sam_live_stock_conversation_review_events USING btree (chatwoot_conversation_id, ((((review_json -> 'ewelink_request_budget'::text) -> 'detail'::text) ->> 'scope'::text)), created_at, review_event_id) WHERE ((event_source = 'rootline_provider_availability'::text) AND (((review_json -> 'ewelink_request_budget'::text) ->> 'action'::text) = ANY (ARRAY['request_completed'::text, 'snapshot_validation_failed'::text])) AND ((((((review_json -> 'ewelink_request_budget'::text) -> 'state'::text) -> 'scopes'::text) -> (((review_json -> 'ewelink_request_budget'::text) -> 'detail'::text) ->> 'scope'::text)) ->> 'category'::text) IS NOT NULL))"
FAILURE_CREATE_SQL = "CREATE INDEX CONCURRENTLY idx_rootline_ewelink_failure_scope_created\nON public.sam_live_stock_conversation_review_events\n    (chatwoot_conversation_id,\n     ((review_json->'ewelink_request_budget'->'detail'->>'scope')),\n     created_at, review_event_id)\nWHERE event_source = 'rootline_provider_availability'\n  AND review_json->'ewelink_request_budget'->>'action' IN\n      ('request_completed','snapshot_validation_failed')\n  AND review_json->'ewelink_request_budget'->'state'->'scopes'\n      ->(review_json->'ewelink_request_budget'->'detail'->>'scope')->>'category' IS NOT NULL"
CAMP_MIGRATION_ID = '20261127181319_rootline_camp_inventory_index'
CAMP_DESCRIPTION = 'Add exact camp inventory partial index; retain malformed envelopes, full history and outstanding shutdown ownership.'
CAMP_INDEX_NAME = 'idx_rootline_camp_inventory_created'
CAMP_EXPECTED_DEFINITION = "CREATE INDEX idx_rootline_camp_inventory_created ON public.sam_live_stock_conversation_review_events USING btree (created_at DESC, review_event_id DESC) WHERE ((event_source = 'rootline_irrigation_execution'::text) AND ((jsonb_typeof((review_json -> 'rootline_execution'::text)) IS DISTINCT FROM 'object'::text) OR (jsonb_typeof(((review_json -> 'rootline_execution'::text) -> 'action'::text)) IS DISTINCT FROM 'string'::text) OR (((review_json -> 'rootline_execution'::text) ->> 'action'::text) = ANY (ARRAY['claim_before_on'::text, 'contain_zone'::text, 'mark_active'::text, 'mark_stopping'::text, 'record_ambiguous_shutdown'::text, 'record_auxiliary_on_outcome'::text, 'record_claim_recovery'::text, 'record_completed'::text, 'record_execution_not_dispatched'::text, 'record_on_outcome'::text]))))"
CAMP_CREATE_SQL = "CREATE INDEX CONCURRENTLY idx_rootline_camp_inventory_created on public.sam_live_stock_conversation_review_events (created_at desc,review_event_id desc) where event_source='rootline_irrigation_execution' and (jsonb_typeof(review_json->'rootline_execution') is distinct from 'object' or jsonb_typeof(review_json->'rootline_execution'->'action') is distinct from 'string' or review_json->'rootline_execution'->>'action'=any(ARRAY['claim_before_on','contain_zone','mark_active','mark_stopping','record_ambiguous_shutdown','record_auxiliary_on_outcome','record_claim_recovery','record_completed','record_execution_not_dispatched','record_on_outcome']::text[]))"
MIGRATION_IDS = frozenset((MIGRATION_ID, RESTORATION_MIGRATION_ID, CAMP_MIGRATION_ID))


def _contracts(migration_id):
    if migration_id == MIGRATION_ID:
        return ((INDEX_NAME, EXPECTED_DEFINITION, CREATE_SQL, "rootline_accounting_index"),)
    if migration_id == RESTORATION_MIGRATION_ID:
        return ((RESTORATION_INDEX_NAME, RESTORATION_EXPECTED_DEFINITION,
                 RESTORATION_CREATE_SQL, "rootline_restoration_index"),
                (FAILURE_INDEX_NAME, FAILURE_EXPECTED_DEFINITION,
                 FAILURE_CREATE_SQL, "rootline_failure_index"))
    if migration_id == CAMP_MIGRATION_ID:
        return ((CAMP_INDEX_NAME, CAMP_EXPECTED_DEFINITION, CAMP_CREATE_SQL, "rootline_camp_inventory_index"),)
    raise ValueError("unregistered_concurrent_index_migration")


def _verify_contract(connection, contract, *, required=True):
    index_name, definition, _create, error = contract
    row = connection.execute("""select c.relkind, pg_catalog.pg_get_indexdef(i.indexrelid),
             i.indisvalid, i.indisready, i.indislive
        from pg_catalog.pg_class c
        join pg_catalog.pg_namespace n on n.oid=c.relnamespace
        left join pg_catalog.pg_index i on i.indexrelid=c.oid
       where n.nspname='public' and c.relname=%s""", (index_name,)).fetchone()
    if row is None:
        if required:
            raise RuntimeError(error + "_missing")
        return False
    if tuple(row) != ('i', definition, True, True, True):
        raise RuntimeError(error + "_definition_or_state_mismatch")
    return True


def verify_index(connection, *, required=True, migration_id=MIGRATION_ID):
    # Do not short-circuit: a missing first index must not hide a wrong sibling.
    present = [_verify_contract(connection, contract, required=required)
               for contract in _contracts(migration_id)]
    return all(present)


def prepare_index(connection, migration_id):
    """Never commit a caller transaction or repair/drop a mismatched object."""
    if migration_id not in MIGRATION_IDS:
        return None
    contracts = _contracts(migration_id)
    error = contracts[0][3]
    if not connection.autocommit or connection.info.transaction_status != TransactionStatus.IDLE:
        raise RuntimeError(error + "_requires_idle_autocommit")
    # Verify every existing member before any DDL, including a partial prior build.
    present = [_verify_contract(connection, contract, required=False) for contract in contracts]
    if all(present):
        return "existing_exact_valid"
    # Concurrent failures may leave an invalid index. Preserve it and stop;
    # cleanup is a separate reviewed operation, never an automatic retry/drop.
    settings = dict(connection.execute("select name, setting::integer from pg_catalog.pg_settings where name in ('statement_timeout','lock_timeout')").fetchall())
    limits = {"statement_timeout": 180000, "lock_timeout": 30000}
    bounded = {name: min(settings[name], maximum) if settings[name] else maximum
               for name, maximum in limits.items()}
    try:
        for name, milliseconds in bounded.items():
            connection.execute("select pg_catalog.set_config(%s,%s,false)", (name, str(milliseconds)))
        acknowledged = dict(connection.execute("select name, setting::integer from pg_catalog.pg_settings where name in ('statement_timeout','lock_timeout')").fetchall())
        if acknowledged != bounded:
            raise RuntimeError(error + "_timeout_not_acknowledged")
        for contract, exists in zip(contracts, present):
            if not exists:
                connection.execute(contract[2])
                _verify_contract(connection, contract)
        verify_index(connection, migration_id=migration_id)
    finally:
        # Autocommit statement failures leave the session usable. A disconnected
        # session is already contained; restoration failure remains an error.
        for name, milliseconds in settings.items():
            connection.execute("select pg_catalog.set_config(%s,%s,false)", (name, str(milliseconds)))
        restored = dict(connection.execute("select name, setting::integer from pg_catalog.pg_settings where name in ('statement_timeout','lock_timeout')").fetchall())
        if restored != settings:
            raise RuntimeError(error + "_timeout_restore_failed")
    return "created_exact_valid"
