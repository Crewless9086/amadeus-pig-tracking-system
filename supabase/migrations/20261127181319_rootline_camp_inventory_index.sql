-- Additive: existing shared runner prepares the exact index CONCURRENTLY.
-- This transaction only verifies and records it. Retain index on source rollback.
DO $verify$
DECLARE definition text; valid boolean; ready boolean; live boolean;
BEGIN
    SELECT pg_catalog.pg_get_indexdef(i.indexrelid), i.indisvalid, i.indisready, i.indislive
      INTO definition, valid, ready, live
      FROM pg_catalog.pg_index i
     WHERE i.indexrelid=pg_catalog.to_regclass('public.idx_rootline_camp_inventory_created');
    IF definition IS DISTINCT FROM 'CREATE INDEX idx_rootline_camp_inventory_created ON public.sam_live_stock_conversation_review_events USING btree (created_at DESC, review_event_id DESC) WHERE ((event_source = ''rootline_irrigation_execution''::text) AND ((jsonb_typeof((review_json -> ''rootline_execution''::text)) IS DISTINCT FROM ''object''::text) OR (jsonb_typeof(((review_json -> ''rootline_execution''::text) -> ''action''::text)) IS DISTINCT FROM ''string''::text) OR (((review_json -> ''rootline_execution''::text) ->> ''action''::text) = ANY (ARRAY[''claim_before_on''::text, ''contain_zone''::text, ''mark_active''::text, ''mark_stopping''::text, ''record_ambiguous_shutdown''::text, ''record_auxiliary_on_outcome''::text, ''record_claim_recovery''::text, ''record_completed''::text, ''record_execution_not_dispatched''::text, ''record_on_outcome''::text]))))'
       OR valid IS DISTINCT FROM true OR ready IS DISTINCT FROM true
       OR live IS DISTINCT FROM true THEN
        RAISE EXCEPTION 'rootline_camp_inventory_index_definition_or_state_mismatch';
    END IF;
    IF EXISTS (SELECT 1 FROM app_private.migration_log
                WHERE migration_id='20261127181319_rootline_camp_inventory_index'
                  AND description IS DISTINCT FROM 'Add exact camp inventory partial index; retain malformed envelopes, full history and outstanding shutdown ownership.') THEN
        RAISE EXCEPTION 'rootline_camp_inventory_index_migration_log_mismatch';
    END IF;
END
$verify$;
INSERT INTO app_private.migration_log(migration_id,description)
VALUES ('20261127181319_rootline_camp_inventory_index', 'Add exact camp inventory partial index; retain malformed envelopes, full history and outstanding shutdown ownership.')
ON CONFLICT (migration_id) DO NOTHING;
