"""One reviewed concurrent index preparation, shared by both migration runners."""
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


def verify_index(connection, *, required=True):
    row = connection.execute("""select c.relkind, pg_catalog.pg_get_indexdef(i.indexrelid),
             i.indisvalid, i.indisready, i.indislive
        from pg_catalog.pg_class c
        join pg_catalog.pg_namespace n on n.oid=c.relnamespace
        left join pg_catalog.pg_index i on i.indexrelid=c.oid
       where n.nspname='public' and c.relname=%s""", (INDEX_NAME,)).fetchone()
    if row is None:
        if required:
            raise RuntimeError("rootline_accounting_index_missing")
        return False
    if tuple(row) != ('i', EXPECTED_DEFINITION, True, True, True):
        raise RuntimeError("rootline_accounting_index_definition_or_state_mismatch")
    return True


def prepare_index(connection, migration_id):
    """Never commit a caller transaction or repair/drop a mismatched object."""
    if migration_id != MIGRATION_ID:
        return None
    if not connection.autocommit or connection.info.transaction_status != TransactionStatus.IDLE:
        raise RuntimeError("rootline_accounting_index_requires_idle_autocommit")
    if verify_index(connection, required=False):
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
            raise RuntimeError("rootline_accounting_index_timeout_not_acknowledged")
        connection.execute(CREATE_SQL)
        verify_index(connection)
    finally:
        # Autocommit statement failures leave the session usable. A disconnected
        # session is already contained; restoration failure remains an error.
        for name, milliseconds in settings.items():
            connection.execute("select pg_catalog.set_config(%s,%s,false)", (name, str(milliseconds)))
        restored = dict(connection.execute("select name, setting::integer from pg_catalog.pg_settings where name in ('statement_timeout','lock_timeout')").fetchall())
        if restored != settings:
            raise RuntimeError("rootline_accounting_index_timeout_restore_failed")
    return "created_exact_valid"
