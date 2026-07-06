# Implementation Source Map

Status: active machine-aligned map, maintained with `modules/charlie/source_map.py`.

Purpose: tell CHARLIE CORE where real implementation truth lives before it advises or builds. Vault Brain carries doctrine and strategy; this map links doctrine to code, routes, tests, migrations, and legacy sources.

## Rule

For income, SAM, Beacon, order, WhatsApp, Chatwoot, n8n, or live-sales missions, CHARLIE CORE must inspect the relevant implementation source-map section before planning or building.

## Current Sections

### CHARLIE CORE Dashboard

Current built active workflow surface:

- routes: `/charlie`, `/api/charlie/build-relay/missions`, `/api/charlie/build-relay/runner/status`, `/api/charlie/build-relay/command-center`, `/api/charlie/build-relay/missions/<mission_id>/review`, `/api/charlie/build-relay/missions/<mission_id>/decision`;
- Vault doctrine: `docs/09-vault-brain/01-identity/CHARLIE_CORE.md`, `docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md`, `docs/09-vault-brain/07-standards/CHARLIE_CORE_UI_MISSION_STANDARD.md`, `docs/09-vault-brain/07-standards/UI_DASHBOARD_STANDARD.md`, `docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md`;
- code: `app.py`, `modules/charlie/routes.py`, `modules/charlie/mission_store.py`, `modules/charlie/runner_control.py`, `modules/charlie/execution_bridge.py`, `modules/charlie/core_workflow.py`, `modules/charlie/source_map.py`;
- UI: `templates/charlie.html`, `static/js/charlieMissionControl.js`, `static/css/main.css`;
- tests: `tests/test_charlie_build_relay.py`, `tests/test_charlie_execution_bridge.py`, `tests/test_charlie_mission_store.py`, `tests/test_charlie_core_workflow.py`, `tests/test_charlie_source_map.py`, `tests/test_frontend_route_contracts.py`;
- migrations: `supabase/migrations/202606300001_create_charlie_mission_queue.sql`, `202606300002_create_charlie_vault_v1_tables.sql`, `202607010002_create_charlie_core_v3_tables.sql`;
- legacy references: none;
- rule: when a mission is explicitly about the CHARLIE CORE dashboard, command center, mission queue, runner status, owner review, or workflow UI, CHARLIE CORE must select this section first. Negated mentions such as holding SAM/Beacon work out of scope must not pull in sales source-map sections.

### CHARLIE CORE Memory And Mission Recall

Current built active workflow surface:

- routes: `/api/charlie/build-relay/missions/<mission_id>/review`, `/api/charlie/build-relay/missions/<mission_id>/decision`, `/api/charlie/build-relay/missions/<mission_id>/replay`, `/api/charlie/build-relay/missions/<mission_id>/replay/stress`;
- Vault doctrine: `docs/09-vault-brain/01-identity/CHARLIE_CORE.md`, `docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md`, `docs/09-vault-brain/06-data/BRAIN_AND_MEMORY_V2.md`, `docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md`, `docs/09-vault-brain/07-standards/TESTING_STANDARD.md`, `docs/09-vault-brain/09-examples/GOLD_STANDARD_RECOVERY_PACKET.md`;
- code: `modules/charlie/mission_memory.py`, `modules/charlie/execution_bridge.py`, `modules/charlie/core_workflow.py`, `modules/charlie/routes.py`, `modules/charlie/mission_store.py`, `modules/charlie/replay_stress.py`, `modules/charlie/improvement_analyst.py`, `scripts/charlie_mission_pickup.py`, `scripts/charlie_codex_execution_bridge.py`;
- tests: `tests/test_charlie_mission_memory.py`, `tests/test_charlie_execution_bridge.py`, `tests/test_charlie_core_workflow.py`, `tests/test_charlie_replay_stress.py`, `tests/test_charlie_improvement_analyst.py`, `tests/test_charlie_build_relay.py`, `tests/test_charlie_source_map.py`;
- migrations: `supabase/migrations/202606300001_create_charlie_mission_queue.sql`, `202606300002_create_charlie_vault_v1_tables.sql`;
- legacy references: none;
- rule: when a mission is explicitly about CHARLIE CORE memory runtime, mission working memory, mission recall, recovery packets, blocked states, send-backs, resumed missions, handoffs, or agent ledgers, CHARLIE CORE must select this section before advising or building. Mission working memory remains mission-scoped evidence and does not outrank owner instructions, runtime records, or owner-reviewed Vault doctrine.

### SAM Meat Sales

Current built pilot surface:

- routes: `/sales/meat-leads`, `/sales/meat-driver`, `/meat-planning`, `/api/sales/meat-leads`, `/api/sales/meat-pilot-readiness`, `/api/sales/meat-pricing`, `/api/sales/channels/chatwoot/sam-meat/inbound`;
- Vault doctrine: `docs/09-vault-brain/02-agents/sales/SAM.md`, `docs/09-vault-brain/02-agents/sales/MEAT_SALES_AGENT.md`, `docs/09-vault-brain/02-agents/sales/SAM_MEAT_PERSONALITY.md`, `docs/09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md`, `docs/09-vault-brain/05-playbooks/SAM_MEAT_HUMAN_SALES_PLAYBOOK.md`, `docs/09-vault-brain/08-business-rules/MEAT_SALES_RULES.md`, `docs/09-vault-brain/09-examples/SAM_MEAT_GOLD_STANDARD_REPLIES.md`;
- code: `modules/sales/sam_meat_runtime.py`, `modules/sales/meat_pilot_readiness.py`, `modules/sales/meat_documents.py`, `modules/sales/meat_match_engine.py`, `modules/sales/meat_ops.py`, `modules/sales/meat_fulfillment.py`, `modules/sales/meat_reconciliation.py`, `modules/oom_sakkie/sales_campaign_store.py`;
- UI: `templates/meat-sales-leads.html`, `static/js/meatSalesLeads.js`, `static/css/meatSalesLeads.css`;
- tests: `tests/test_sam_meat_runtime.py`, `tests/test_meat_launch_readiness.py`, `tests/test_meat_ops.py`, `tests/test_meat_fulfillment.py`, `tests/test_meat_reconciliation.py`, `tests/sam_meat_command_room_playwright.spec.js`;
- migrations: `supabase/migrations/202606140002_create_oom_sakkie_sales_leads.sql`, `202606160005_create_meat_price_book.sql`, `202606160006_create_meat_ops_rails.sql`, `202606170001_create_meat_reservation_events.sql`, `202606180001_create_meat_sales_conversation_learning_events.sql`;
- legacy references: `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md`, `MEAT_INTAKE_HANDOFF_PLAN.md`.

### Beacon Marketing

Current built gated surface:

- routes: `/sales/beacon-media`, `/api/beacon/media-assets`, `/api/beacon/campaign-draft-selection`, `/api/beacon/campaign-publish-packet`, `/api/beacon/facebook-image-launch-packet`, `/api/beacon/manual-post-evidence`, `/api/beacon/campaign-performance`;
- code: `modules/beacon/media_library.py`, `modules/sales/beacon_campaign.py`, `modules/sales/sales_transaction_routes.py`;
- UI: `templates/beacon-media.html`, `static/js/beaconMedia.js`, `static/css/beaconMedia.css`;
- tests: `tests/test_beacon_media_library.py`, `tests/test_beacon_campaign.py`;
- migrations: `supabase/migrations/202606180002_create_beacon_media_library.sql`, `202606180003_create_beacon_manual_post_events.sql`, `202606180004_create_beacon_campaign_performance_events.sql`, `202606180005_create_beacon_facebook_post_execution_events.sql`;
- legacy references: `docs/05-ai/agents/beacon/BEACON_SCOPE.md`, `docs/05-ai/agents/beacon/MEDIA_STORAGE_DECISION.md`.

### Orders And Sales Transactions

Current built Supabase-backed surface:

- routes: `/orders`, `/orders/new`, `/sales-dashboard`, `/sales-availability`, `/api/orders`, `/api/sales-transactions`, `/api/pig-weights/sales-dashboard`;
- code: `modules/orders/*`, `modules/sales/sales_transaction_*`, `modules/pig_weights/pig_weights_service.py`;
- UI: `templates/orders.html`, `templates/order-detail.html`, `templates/add-order.html`, `templates/sales-dashboard.html`, `templates/sales-availability.html`;
- tests: `tests/test_order_routes.py`, `tests/test_order_service_*.py`, `tests/test_sales_transaction_*.py`;
- migrations: `supabase/migrations/202605210002_create_order_sales_tables.sql`, `202605210003_create_sales_transaction_tables.sql`, `202605210004_add_sales_transaction_payment_date.sql`;
- legacy references: `docs/03-google-sheets/sheets/SALES_STOCK_TOTALS.md`, `docs/04-n8n/workflows/ORDER_STEWARD_HANDOFF_CONTRACTS.md`.

### Pig Allocation And Herdmaster Purpose Intelligence

Current built read-only readiness surface to expand:

- routes: `/pig-allocation`, `/api/pig-weights/pig-allocation-readiness`, `/api/pig-weights/purpose-review`, `/api/pig-weights/purpose-review/apply`, `/api/pig-weights/purpose-review/recheck`;
- Vault doctrine: `docs/09-vault-brain/02-agents/farm/HERDMASTER.md`, `docs/09-vault-brain/04-workflows/HERDMASTER_PURPOSE_REVIEW_WORKFLOW.md`, `docs/09-vault-brain/06-data/FARM_DATA_MODEL.md`, `docs/09-vault-brain/08-business-rules/PIG_PURPOSE_RULES.md`, `docs/09-vault-brain/08-business-rules/HERDMASTER_PIG_ALLOCATION_ALERT_RULES.md`, `docs/09-vault-brain/00-governance/SOURCE_OF_TRUTH_RULES.md`;
- code: `modules/pig_weights/pig_weights_service.py`;
- UI: `templates/pig-allocation.html`, `static/js/pigAllocation.js`;
- tests: `tests/test_pig_allocation_readiness_service.py`;
- migrations: none for the first read-only alert build;
- legacy references: `docs/03-google-sheets/sheets/PIG_MASTER.md`, `docs/03-google-sheets/sheets/PIG_OVERVIEW.md`, `docs/03-google-sheets/sheets/WEIGHT_LOG.md`;
- rule: Herdmaster Pig Allocation alert missions must inspect this section and the alert rules doc before advising or building. Alerts are advisory until owner-approved backend rails create any write, lifecycle, purpose, sales, slaughter, reservation, or customer-facing action.

### Live Pig Sales Legacy

Current status: live pig sales behavior is not yet a clean backend-native agent lane. It must be rebuilt against Supabase/app truth after Meat Sales pilot readiness is confirmed.

- current app surfaces: `/sales-dashboard`, `/sales-availability`, `/orders`, `/api/sales-transactions`, `/api/pig-weights/sales-dashboard`;
- legacy references: `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md`, `docs/03-google-sheets/sheets/SALES_STOCK_TOTALS.md`, `docs/99-archive/legacy/planning_CHAT_2026-04_n8n_sales_agent_rewire.md`;
- rule: preserve old n8n behavior lessons, but do not treat old Google Sheets/n8n as current source of truth without app/Supabase verification.

### SAM Live Stock Sales

Current Stage 4 surface:

- routes to inspect later: `/sales-dashboard`, `/sales-availability`, `/orders`, `/api/order-intake/context`, `/api/order-intake/update`, `/api/orders/active-customer-context`, `/api/orders/available-pigs`, `/api/master/orders`, `/api/master/order-lines`, `/api/pig-weights/sales-dashboard`, `/api/pig-weights/pig-allocation-readiness`;
- Vault doctrine: `docs/09-vault-brain/02-agents/sales/SAM.md`, `docs/09-vault-brain/02-agents/sales/LIVE_PIG_SALES_AGENT.md`, `docs/09-vault-brain/03-business/LIVE_PIG_SALES.md`, `docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md`, `docs/09-vault-brain/04-workflows/BEACON_LIVE_STOCK_AWARENESS_WORKFLOW.md`, `docs/09-vault-brain/05-playbooks/SAM_LIVE_STOCK_HUMAN_SALES_PLAYBOOK.md`, `docs/09-vault-brain/08-business-rules/LIVE_STOCK_SALES_RULES.md`, `docs/09-vault-brain/09-examples/SAM_LIVE_STOCK_GOLD_STANDARD_REPLIES.md`;
- code: `modules/sales/sam_sales_router.py`, `modules/sales/sam_live_stock_runtime.py`, `modules/pig_weights/pig_weights_service.py`, `modules/orders/order_intake_service.py`, `modules/orders/order_service.py`, `modules/orders/order_write.py`, `modules/orders/order_routes.py`, `modules/sales/sales_transaction_read.py`, `modules/sales/sales_transaction_create.py`;
- tests: `tests/test_sam_sales_router.py`, `tests/test_sam_live_stock_runtime.py`, `tests/test_order_intake_service.py`, `tests/test_order_routes.py`, `tests/test_order_service_reservation.py`, `tests/test_sales_transaction_read.py`, `tests/test_pig_allocation_readiness_service.py`;
- legacy references to mine only: `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md`, `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/workflow.json`, `docs/03-google-sheets/sheets/SALES_PRICING.md`, `docs/03-google-sheets/sheets/SALES_AVAILABILITY.md`, `docs/03-google-sheets/sheets/SALES_STOCK_TOTALS.md`;
- rule: Stage 4 permits env-gated writes only to the existing order-intake service after validation. Customer sends, order creation, stock reservation, quotes, and sales transactions remain blocked until later owner-approved stages.
