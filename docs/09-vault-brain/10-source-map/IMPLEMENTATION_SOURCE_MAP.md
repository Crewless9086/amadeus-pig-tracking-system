# Implementation Source Map

## Rootline owner daily brief

- Doctrine: `docs/09-vault-brain/02-agents/farm/ROOTLINE.md`
- Control architecture:
  `docs/09-vault-brain/04-workflows/ROOTLINE_CONTROL_ARCHITECTURE.md`
- Composer: `modules/telemetry/rootline_daily_brief.py`
- Owner-only route: `GET /api/telemetry/rootline/daily-brief`
- Existing owner dashboard surfaces: `templates/dashboard.html`,
  `static/js/dashboard.js`
- Focused safety/behavior tests: `tests/test_rootline_daily_brief.py`
- Underlying truth remains in the existing weather, forecast, power,
  irrigation, and daily-rollup readers. Rootline adds no write or hardware
  control authority.
- Delivery evidence: built, merged, and deployed through PR #464 at merge
  `187e07fb9f531549d35b04824ec9149875fabb85`; the owner-only route returned
  structured HTTP 200 evidence in one controlled read. This proves the Level 1
  Daily Brief route, not complete telemetry, hardware control, IFTTT
  authorization, or autonomous irrigation.

Status: active machine-aligned map, maintained with `modules/charlie/source_map.py`.

Purpose: tell CHARLIE CORE where real implementation truth lives before it advises or builds. Vault Brain carries doctrine and strategy; this map links doctrine to code, routes, tests, migrations, and legacy sources.

## Rule

For income, SAM, Beacon, order, WhatsApp, Chatwoot, n8n, or live-sales missions, CHARLIE CORE must inspect the relevant implementation source-map section before planning or building.

## Current Sections

### CHARLIE CORE Adaptive Mission Orchestration

Current implementation and review surface:

- operating contract:
  `docs/00-start-here/CHARLIE_CORE_AGENT_RUNNER_V2.md`;
- scoring and packet construction:
  `modules/charlie/adaptive_orchestration.py`,
  `modules/charlie/core_workflow.py`;
- durable execution, historical compatibility and evidence-driven expansion:
  `modules/charlie/execution_bridge.py`,
  `modules/charlie/mission_store.py`;
- owner-only throughput surface:
  `GET /api/charlie/build-relay/missions/summary`;
- tests:
  `tests/test_charlie_adaptive_orchestration.py`,
  `tests/test_charlie_core_workflow.py`,
  `tests/test_charlie_execution_bridge.py`,
  `tests/test_charlie_mission_store.py`,
  `tests/test_charlie_mission_pickup.py`,
  `tests/test_charlie_runner_control.py`,
  `tests/test_charlie_runner_supervisor.py`,
  `tests/test_charlie_runner_watchdog.py`;
- persistence: existing `charlie_missions.metadata_json`, agent artifacts and
  execution evidence; no second mission ledger or schema migration;
- rule: missions about workflow selection, mission scoring, execution tiers,
  agent budgets, dynamic expansion, historical workflow compatibility or
  orchestration throughput must inspect this section. Protected triggers and
  owner gates outrank aggregate scores. Existing persisted workflows remain
  frozen.

### CHARLIE CORE Process Ownership Bootstrap

Current implementation and verification surface:

- ownership identity, canonical tree normalization, signing, redaction, and
  live validation: `modules/charlie/process_ownership.py`;
- governed start/stop, stop-marker enforcement, acknowledgement waiting, and
  containment: `modules/charlie/runner_control.py`;
- supervisor-side handshake and runner-spawn gate:
  `scripts/charlie_runner_supervisor.py`;
- pickup/recovery acknowledgement gate:
  `scripts/charlie_mission_pickup.py`;
- focused tests:
  `tests/test_charlie_process_ownership.py`,
  `tests/test_charlie_runner_control.py`,
  `tests/test_charlie_runner_supervisor.py`,
  `tests/test_charlie_mission_pickup.py`;
- rule: startup or stop work must validate the complete externally observed
  launcher/interpreter topology, generation, revision, startup nonce,
  executable/command roles, parentage, PIDs, and live creation identity.
  Missing or stale identity fails closed. The canonical stop marker is not an
  implicit startup toggle, and watchdog enablement remains a separate governed
  action.
- delivery state: PR #517 code is merged and Render-deployed at
  `0c4eb404fce6df8dfc2e8aab100690697d6e7cb9`; local governed promotion,
  startup, watchdog activation, mission pickup, and natural proof have not
  been authorized.

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

### Agent Authority Matrix And Claude Review

Current active governance surface:

- routes: `/charlie`, `/api/charlie/build-relay/missions/<mission_id>/review`, `/api/charlie/build-relay/missions/<mission_id>/decision`, `/api/charlie/build-relay/source-map`;
- Vault doctrine: `docs/09-vault-brain/07-standards/AGENT_AUTHORITY_MATRIX.md`, `docs/09-vault-brain/02-agents/AGENT_REGISTRY.md`, `docs/09-vault-brain/01-identity/CHARLIE_CORE.md`, `docs/09-vault-brain/00-governance/SOURCE_OF_TRUTH_RULES.md`, `docs/09-vault-brain/00-governance/UPDATE_RULES.md`, `docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md`, `docs/09-vault-brain/07-standards/TESTING_STANDARD.md`, `docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md`;
- code: `modules/charlie/source_map.py`, `modules/charlie/execution_bridge.py`, `modules/charlie/core_workflow.py`, `modules/charlie/mission_store.py`, `modules/oom_sakkie/agent_runtime.py`, `modules/oom_sakkie/routes.py`, `modules/beacon/media_library.py`, `modules/sales/beacon_campaign.py`, `modules/sales/sam_sales_router.py`, `modules/sales/sam_live_stock_runtime.py`, `modules/sales/sam_meat_runtime.py`, `modules/sales/meat_ops.py`, `modules/sales/meat_fulfillment.py`, `modules/pig_weights/pig_weights_service.py`, `modules/orders/order_intake_service.py`, `modules/sales/sales_transaction_read.py`, `modules/sales/sales_transaction_create.py`;
- tests: `tests/test_charlie_source_map.py`, `tests/test_charlie_execution_bridge.py`, `tests/test_charlie_core_workflow.py`, `tests/test_oom_sakkie_routes.py`, `tests/test_beacon_campaign.py`, `tests/test_sam_sales_router.py`, `tests/test_sam_live_stock_runtime.py`, `tests/test_sam_meat_runtime.py`, `tests/test_meat_ops.py`, `tests/test_pig_allocation_readiness_service.py`, `tests/test_sales_transaction_read.py`;
- legacy references: `docs/01-architecture/OOM_SAKKIE_AGENT_ROSTER.md`, `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md`;
- rule: authority, Claude review, public/customer automation, payment, meat, slaughter, butcher, stock reservation, farm lifecycle, specialist dispatch, runtime authority, or agent registration missions must inspect this section. The matrix documents current authority only; it does not grant new live authority.

### SAM General Conversation

Current governance and implementation-ownership surface:

- routes: `/api/sales/channels/chatwoot/sam-meat/inbound`,
  `/api/sales/channels/chatwoot/sam-live-stock/inbound`;
- Vault doctrine:
  `docs/09-vault-brain/04-workflows/SAM_GENERAL_CONVERSATION.md`,
  `docs/09-vault-brain/02-agents/sales/SAM.md`,
  `docs/09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md`,
  `docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md`,
  `docs/09-vault-brain/00-governance/BRAIN_GUARD.md`,
  `docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md`;
- router and context:
  `modules/sales/sam_sales_router.py`,
  `modules/sales/sam_shared_context.py`;
- LLM/review and inbound surfaces:
  `modules/sales/sam_meat_runtime.py`,
  `modules/sales/sam_live_stock_runtime.py`,
  `modules/sales/sales_transaction_routes.py`;
- journey tests:
  `tests/test_sam_sales_router.py`,
  `tests/test_sam_v3_shared_context.py`,
  `tests/test_sam_v3_replay_stress.py`,
  `tests/test_sam_meat_runtime.py`,
  `tests/test_sam_live_stock_runtime.py`,
  `tests/test_sam_live_stock_replay.py`;
- migrations: none;
- legacy reference only:
  `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md`;
- rule: missions affecting ordinary SAM dialogue, unknown/general intent,
  ownership transitions, progressive lane discovery, topic changes, or
  specialist-tool timing must inspect this domain first and prove the complete
  customer journey. This map records ownership; it does not claim the doctrine
  is implemented, deployed, configured, or operational.

### Shared Outbound Delivery Truth

Current cross-system governance surface:

- Vault doctrine:
  `docs/09-vault-brain/07-standards/OUTBOUND_DELIVERY_TRUTH_STANDARD.md`,
  `docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md`,
  `docs/09-vault-brain/00-governance/BRAIN_GUARD.md`;
- SAM journeys:
  `docs/09-vault-brain/04-workflows/SAM_GENERAL_CONVERSATION.md`,
  `docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md`,
  `docs/09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md`;
- quote/invoice/attachment doctrine:
  `docs/02-backend/QUOTE_INVOICE_DESIGN.md`,
  `docs/04-n8n/workflows/1.5 - outbound-document-delivery/README.md`;
- implementation surfaces to inspect, not authority granted:
  `modules/sales/sales_transaction_routes.py`,
  `modules/sales/sam_live_stock_runtime.py`,
  `modules/sales/sam_meat_runtime.py`,
  `modules/documents/document_service.py`;
- tests to inspect:
  `tests/test_sales_transaction_routes.py`,
  `tests/test_sam_live_stock_runtime.py`,
  `tests/test_sam_meat_runtime.py`,
  `tests/test_document_service_send.py`;
- rule: every customer-message, quote, invoice, or attachment delivery mission
  must distinguish prepared, claimed, Chatwoot-accepted, provider-delivered,
  provider-read, failed, and ambiguous states. HTTP/mock success is not
  delivery proof; provider identity and application idempotency remain
  separate; accepted/ambiguous outcomes are not automatically retried.

### SAM Meat Sales And Production

Current built pilot surface:

- routes: `/sales/meat-leads`, `/sales/meat-driver`, `/sales/meat-production`, `/meat-planning`, `/api/sales/meat-leads`, `/api/sales/meat-production/batches`, `/api/sales/meat-pilot-readiness`, `/api/sales/meat-pricing`, `/api/sales/channels/chatwoot/sam-meat/inbound`;
- Vault doctrine: `docs/09-vault-brain/02-agents/sales/SAM.md`, `docs/09-vault-brain/02-agents/sales/BUTCHER.md`, `docs/09-vault-brain/02-agents/sales/MEAT_SALES_AGENT.md`, `docs/09-vault-brain/02-agents/sales/SAM_MEAT_PERSONALITY.md`, `docs/09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md`, `docs/09-vault-brain/05-playbooks/SAM_MEAT_HUMAN_SALES_PLAYBOOK.md`, `docs/09-vault-brain/08-business-rules/MEAT_SALES_RULES.md`, `docs/09-vault-brain/08-business-rules/MEAT_PRODUCTION_RULES.md`, `docs/09-vault-brain/09-examples/SAM_MEAT_GOLD_STANDARD_REPLIES.md`;
- code: `modules/sales/sam_meat_runtime.py`, `modules/sales/meat_pilot_readiness.py`, `modules/sales/meat_production.py`, `modules/sales/meat_documents.py`, `modules/sales/meat_match_engine.py`, `modules/sales/meat_ops.py`, `modules/sales/meat_fulfillment.py`, `modules/sales/meat_reconciliation.py`, `modules/oom_sakkie/sales_campaign_store.py`;
- UI: `templates/meat-sales-leads.html`, `templates/meat-production.html`, `static/js/meatSalesLeads.js`, `static/js/meatProduction.js`, `static/css/meatSalesLeads.css`, `static/css/meatProduction.css`;
- tests: `tests/test_sam_meat_runtime.py`, `tests/test_meat_launch_readiness.py`, `tests/test_meat_production.py`, `tests/test_meat_ops.py`, `tests/test_meat_fulfillment.py`, `tests/test_meat_reconciliation.py`, `tests/sam_meat_command_room_playwright.spec.js`;
- migrations: `supabase/migrations/202606140002_create_oom_sakkie_sales_leads.sql`, `202606160005_create_meat_price_book.sql`, `202606160006_create_meat_ops_rails.sql`, `202606170001_create_meat_reservation_events.sql`, `202606180001_create_meat_sales_conversation_learning_events.sql`, `202607130001_create_meat_processing_batches.sql`;
- legacy references: `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md`, `MEAT_INTAKE_HANDOFF_PLAN.md`.

### Beacon Marketing

Current built gated surface:

- routes: `/sales/beacon-media`, `/api/beacon/media-assets`, `/api/beacon/creative-studio/providers`, `/api/beacon/creative-studio/jobs`, `/api/beacon/creative-studio/jobs/<job_id>/reviews`, `/api/beacon/campaign-draft-selection`, `/api/beacon/campaign-publish-packet`, `/api/beacon/facebook-image-launch-packet`, `/api/beacon/manual-post-evidence`, `/api/beacon/campaign-performance`;
- queued owner workflow: `docs/09-vault-brain/04-workflows/BEACON_MEDIA_INTAKE_WORKFLOW.md`; OOM SAKKIE is the preferred owner-only Telegram intake gateway, while BEACON owns private storage, cataloguing, understanding, visual review, approval state, and usage history. This direction is documented but not implemented or activated;
- code: `modules/beacon/media_library.py`, `modules/beacon/creative_providers.py`, `modules/beacon/creative_studio.py`, `modules/beacon/organic_media_intelligence.py`, `modules/beacon/organic_publication_binding.py`, `modules/beacon/organic_publication_authorization.py`, `modules/beacon/weekly_owner_review.py`, `modules/beacon/weekly_owner_review_decisions.py`, `modules/sales/beacon_campaign.py`, `modules/sales/sales_transaction_routes.py`;
- UI: `templates/beacon-media.html`, `static/js/beaconMedia.js`, `static/css/beaconMedia.css`;
- tests: `tests/test_beacon_media_library.py`, `tests/test_beacon_creative_studio.py`, `tests/test_beacon_creative_studio_migration.py`, `tests/test_beacon_campaign.py`, `tests/test_beacon_organic_media_intelligence.py`, `tests/test_beacon_organic_media_intelligence_postgres.py`, `tests/test_beacon_weekly_owner_review.py`, `tests/test_beacon_weekly_owner_review_decisions.py`;
- migrations: `supabase/migrations/202606180002_create_beacon_media_library.sql`, `202606180003_create_beacon_manual_post_events.sql`, `202606180004_create_beacon_campaign_performance_events.sql`, `202606180005_create_beacon_facebook_post_execution_events.sql`, `202606180006_extend_beacon_facebook_post_execution_statuses.sql`, `202607130002_create_beacon_creative_studio.sql`, `202607130003_enable_beacon_creative_studio_rls.sql`, `202607250001_create_beacon_weekly_review_decisions.sql`, `202607260003_create_beacon_publication_bindings.sql`, `202607260005_create_beacon_publication_authorizations.sql`, `202607260008_create_beacon_organic_media_learning.sql`;
- legacy references: `docs/05-ai/agents/beacon/BEACON_SCOPE.md`, `docs/05-ai/agents/beacon/MEDIA_STORAGE_DECISION.md`.
- rule: media-intake missions must inspect the BEACON media-intake workflow plus current OOM SAKKIE Telegram and BEACON storage contracts. Intake, library acceptance, public-use approval, and publication authorization remain separate. Historical OneDrive/folder import is a separate phase.

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
