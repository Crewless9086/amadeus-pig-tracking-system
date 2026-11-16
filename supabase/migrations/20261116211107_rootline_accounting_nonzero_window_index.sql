-- The shared runner helper prepares this one index concurrently before this
-- transaction. This migration only verifies it and records the canonical log.
DO $verify$
DECLARE definition text; valid boolean; ready boolean; live boolean;
BEGIN
    SELECT pg_catalog.pg_get_indexdef(i.indexrelid), i.indisvalid, i.indisready, i.indislive
      INTO definition, valid, ready, live
      FROM pg_catalog.pg_index i
     WHERE i.indexrelid=pg_catalog.to_regclass('public.idx_sam_review_budget_nonzero_window');
    IF definition IS DISTINCT FROM 'CREATE INDEX idx_sam_review_budget_nonzero_window ON public.sam_live_stock_conversation_review_events USING btree (chatwoot_conversation_id, event_source, created_at) WHERE (((review_json #>> ''{ewelink_request_budget,attempt_units}''::text[]) COLLATE "C") IS DISTINCT FROM ''0''::text)'
       OR valid IS DISTINCT FROM true OR ready IS DISTINCT FROM true
       OR live IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'rootline_accounting_index_definition_or_state_mismatch';
    END IF;
    IF EXISTS (SELECT 1 FROM app_private.migration_log
                WHERE migration_id='20261116211107_rootline_accounting_nonzero_window_index'
                  AND description IS DISTINCT FROM 'Add exact nonzero request-accounting window index; preserve canonical ledger and charging semantics.') THEN
        RAISE EXCEPTION 'rootline_accounting_index_migration_log_mismatch';
    END IF;
END
$verify$;
INSERT INTO app_private.migration_log(migration_id,description)
VALUES ('20261116211107_rootline_accounting_nonzero_window_index', 'Add exact nonzero request-accounting window index; preserve canonical ledger and charging semantics.')
ON CONFLICT (migration_id) DO NOTHING;
