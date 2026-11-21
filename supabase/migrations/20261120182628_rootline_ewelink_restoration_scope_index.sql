-- Additive migration: the existing shared runner prepares both exact indexes
-- CONCURRENTLY before this transaction. This file only verifies and records them.
-- Release this migration before the outage reader; retain both indexes on rollback.
DO $verify$
DECLARE definition text; valid boolean; ready boolean; live boolean;
BEGIN
    SELECT pg_catalog.pg_get_indexdef(i.indexrelid), i.indisvalid, i.indisready, i.indislive
      INTO definition, valid, ready, live
      FROM pg_catalog.pg_index i
     WHERE i.indexrelid=pg_catalog.to_regclass('public.idx_rootline_ewelink_restoration_scope_created');
    IF definition IS DISTINCT FROM 'CREATE INDEX idx_rootline_ewelink_restoration_scope_created ON public.sam_live_stock_conversation_review_events USING btree (chatwoot_conversation_id, ((((review_json -> ''ewelink_request_budget''::text) -> ''detail''::text) ->> ''scope''::text)), created_at DESC, review_event_id DESC) WHERE ((event_source = ''rootline_provider_availability''::text) AND (((review_json -> ''ewelink_request_budget''::text) ->> ''action''::text) = ''complete_snapshot_restored_availability''::text))'
       OR valid IS DISTINCT FROM true OR ready IS DISTINCT FROM true
       OR live IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'rootline_restoration_index_definition_or_state_mismatch';
    END IF;
    SELECT pg_catalog.pg_get_indexdef(i.indexrelid), i.indisvalid, i.indisready, i.indislive
      INTO definition, valid, ready, live
      FROM pg_catalog.pg_index i
     WHERE i.indexrelid=pg_catalog.to_regclass('public.idx_rootline_ewelink_failure_scope_created');
    IF definition IS DISTINCT FROM 'CREATE INDEX idx_rootline_ewelink_failure_scope_created ON public.sam_live_stock_conversation_review_events USING btree (chatwoot_conversation_id, ((((review_json -> ''ewelink_request_budget''::text) -> ''detail''::text) ->> ''scope''::text)), created_at, review_event_id) WHERE ((event_source = ''rootline_provider_availability''::text) AND (((review_json -> ''ewelink_request_budget''::text) ->> ''action''::text) = ANY (ARRAY[''request_completed''::text, ''snapshot_validation_failed''::text])) AND ((((((review_json -> ''ewelink_request_budget''::text) -> ''state''::text) -> ''scopes''::text) -> (((review_json -> ''ewelink_request_budget''::text) -> ''detail''::text) ->> ''scope''::text)) ->> ''category''::text) IS NOT NULL))'
       OR valid IS DISTINCT FROM true OR ready IS DISTINCT FROM true
       OR live IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'rootline_failure_index_definition_or_state_mismatch';
    END IF;
    IF EXISTS (SELECT 1 FROM app_private.migration_log
                WHERE migration_id='20261120182628_rootline_ewelink_restoration_scope_index'
                  AND description IS DISTINCT FROM 'Add exact provider-failure and restoration scope indexes; preserve outage identity and canonical receipt semantics.') THEN
        RAISE EXCEPTION 'rootline_restoration_index_migration_log_mismatch';
    END IF;
END
$verify$;
INSERT INTO app_private.migration_log(migration_id,description)
VALUES ('20261120182628_rootline_ewelink_restoration_scope_index', 'Add exact provider-failure and restoration scope indexes; preserve outage identity and canonical receipt semantics.')
ON CONFLICT (migration_id) DO NOTHING;
