from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_MAP_VERSION = "charlie_implementation_source_map_v1"


IMPLEMENTATION_SOURCE_MAP = {
    "charlie_core_dashboard": {
        "label": "CHARLIE CORE Dashboard",
        "status": "built_active_workflow",
        "summary": "CHARLIE mission control dashboard, mission queue, runner status, owner review, source-map, Vault readiness, and agent workflow UI.",
        "keywords": ["charlie core", "/charlie", "charlie dashboard", "mission control", "command center", "dashboard ui", "owner review", "runner status"],
        "vault_docs": [
            "docs/09-vault-brain/01-identity/CHARLIE_CORE.md",
            "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md",
            "docs/09-vault-brain/07-standards/CHARLIE_CORE_UI_MISSION_STANDARD.md",
            "docs/09-vault-brain/07-standards/UI_DASHBOARD_STANDARD.md",
            "docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md",
        ],
        "app_routes": [
            "/charlie",
            "/api/charlie/build-relay/missions",
            "/api/charlie/build-relay/runner/status",
            "/api/charlie/build-relay/command-center",
            "/api/charlie/build-relay/missions/<mission_id>/review",
            "/api/charlie/build-relay/missions/<mission_id>/decision",
        ],
        "code_paths": [
            "app.py",
            "templates/charlie.html",
            "static/js/charlieMissionControl.js",
            "static/css/main.css",
            "modules/charlie/routes.py",
            "modules/charlie/mission_store.py",
            "modules/charlie/runner_control.py",
            "modules/charlie/execution_bridge.py",
            "modules/charlie/core_workflow.py",
            "modules/charlie/source_map.py",
        ],
        "tests": [
            "tests/test_charlie_build_relay.py",
            "tests/test_charlie_execution_bridge.py",
            "tests/test_charlie_mission_store.py",
            "tests/test_charlie_core_workflow.py",
            "tests/test_charlie_source_map.py",
            "tests/test_frontend_route_contracts.py",
        ],
        "migrations": [
            "supabase/migrations/202606300001_create_charlie_mission_queue.sql",
            "supabase/migrations/202606300002_create_charlie_vault_v1_tables.sql",
            "supabase/migrations/202607010002_create_charlie_core_v3_tables.sql",
        ],
        "legacy_sources": [],
        "must_inspect_before_advice": True,
    },
    "charlie_core_memory_recall": {
        "label": "CHARLIE CORE Memory And Mission Recall",
        "status": "built_active_workflow",
        "summary": "Mission working memory, handoff recall, recovery packets, blocked-stage replay, send-back preservation, and prompt recall context for CHARLIE CORE Agent Runner v2.",
        "keywords": [
            "charlie core memory",
            "memory runtime",
            "working memory",
            "mission recall",
            "mission memory",
            "brain & memory",
            "recovery packet",
            "recovery recall",
            "blocked states",
            "send-backs",
            "send back",
            "resumed missions",
            "handoff",
            "agent ledger",
        ],
        "vault_docs": [
            "docs/09-vault-brain/01-identity/CHARLIE_CORE.md",
            "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md",
            "docs/09-vault-brain/06-data/BRAIN_AND_MEMORY_V2.md",
            "docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md",
            "docs/09-vault-brain/07-standards/TESTING_STANDARD.md",
            "docs/09-vault-brain/09-examples/GOLD_STANDARD_RECOVERY_PACKET.md",
        ],
        "app_routes": [
            "/api/charlie/build-relay/missions/<mission_id>/review",
            "/api/charlie/build-relay/missions/<mission_id>/decision",
            "/api/charlie/build-relay/missions/<mission_id>/replay",
            "/api/charlie/build-relay/missions/<mission_id>/replay/stress",
        ],
        "code_paths": [
            "modules/charlie/mission_memory.py",
            "modules/charlie/execution_bridge.py",
            "modules/charlie/core_workflow.py",
            "modules/charlie/routes.py",
            "modules/charlie/mission_store.py",
            "modules/charlie/replay_stress.py",
            "modules/charlie/improvement_analyst.py",
            "scripts/charlie_mission_pickup.py",
            "scripts/charlie_codex_execution_bridge.py",
        ],
        "tests": [
            "tests/test_charlie_mission_memory.py",
            "tests/test_charlie_execution_bridge.py",
            "tests/test_charlie_core_workflow.py",
            "tests/test_charlie_replay_stress.py",
            "tests/test_charlie_improvement_analyst.py",
            "tests/test_charlie_build_relay.py",
            "tests/test_charlie_source_map.py",
        ],
        "migrations": [
            "supabase/migrations/202606300001_create_charlie_mission_queue.sql",
            "supabase/migrations/202606300002_create_charlie_vault_v1_tables.sql",
        ],
        "legacy_sources": [],
        "must_inspect_before_advice": True,
    },
    "agent_authority_matrix": {
        "label": "Agent Authority Matrix And Claude Review",
        "status": "active_governance_standard",
        "summary": "Cross-agent authority boundaries, owner gates, source routing, required tests, and Claude review triggers for CHARLIE CORE, Beacon, SAM, Butcher, Herdmaster, Oom Sakkie, Gatekeeper, Ledger, Atlas, Sentinel, and Forge.",
        "keywords": [
            "agent authority matrix",
            "authority matrix",
            "claude review",
            "claude-review",
            "authority increase",
            "runtime authority",
            "specialist dispatch",
            "agent registration",
            "public automation",
            "customer automation",
            "payment",
            "meat",
            "slaughter",
            "butcher",
            "stock reservation",
            "farm lifecycle",
        ],
        "vault_docs": [
            "docs/09-vault-brain/07-standards/AGENT_AUTHORITY_MATRIX.md",
            "docs/09-vault-brain/02-agents/AGENT_REGISTRY.md",
            "docs/09-vault-brain/01-identity/CHARLIE_CORE.md",
            "docs/09-vault-brain/00-governance/SOURCE_OF_TRUTH_RULES.md",
            "docs/09-vault-brain/00-governance/UPDATE_RULES.md",
            "docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md",
            "docs/09-vault-brain/07-standards/TESTING_STANDARD.md",
            "docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md",
        ],
        "app_routes": [
            "/charlie",
            "/api/charlie/build-relay/missions/<mission_id>/review",
            "/api/charlie/build-relay/missions/<mission_id>/decision",
            "/api/charlie/build-relay/source-map",
        ],
        "code_paths": [
            "modules/charlie/source_map.py",
            "modules/charlie/execution_bridge.py",
            "modules/charlie/core_workflow.py",
            "modules/charlie/mission_store.py",
            "modules/oom_sakkie/agent_runtime.py",
            "modules/oom_sakkie/routes.py",
            "modules/beacon/media_library.py",
            "modules/sales/beacon_campaign.py",
            "modules/sales/sam_sales_router.py",
            "modules/sales/sam_live_stock_runtime.py",
            "modules/sales/sam_meat_runtime.py",
            "modules/sales/meat_ops.py",
            "modules/sales/meat_fulfillment.py",
            "modules/pig_weights/pig_weights_service.py",
            "modules/orders/order_intake_service.py",
            "modules/sales/sales_transaction_read.py",
            "modules/sales/sales_transaction_create.py",
        ],
        "tests": [
            "tests/test_charlie_source_map.py",
            "tests/test_charlie_execution_bridge.py",
            "tests/test_charlie_core_workflow.py",
            "tests/test_oom_sakkie_routes.py",
            "tests/test_beacon_campaign.py",
            "tests/test_sam_sales_router.py",
            "tests/test_sam_live_stock_runtime.py",
            "tests/test_sam_meat_runtime.py",
            "tests/test_meat_ops.py",
            "tests/test_pig_allocation_readiness_service.py",
            "tests/test_sales_transaction_read.py",
        ],
        "migrations": [],
        "legacy_sources": [
            "docs/01-architecture/OOM_SAKKIE_AGENT_ROSTER.md",
            "docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md",
        ],
        "must_inspect_before_advice": True,
    },
    "sam_meat_sales": {
        "label": "SAM Meat Sales",
        "status": "built_active_pilot",
        "summary": "Backend-native SAM meat sales intake, command room, quote, payment, reservation, fulfilment, reconciliation, and learning rails.",
        "keywords": ["sam", "meat", "meat sales", "meat production", "meat batch", "butcher", "cuts", "yield", "half carcass", "set a", "chatwoot", "whatsapp", "preorder", "quote", "deposit"],
        "vault_docs": [
            "docs/09-vault-brain/03-business/MEAT_SALES.md",
            "docs/09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md",
            "docs/09-vault-brain/08-business-rules/MEAT_SALES_RULES.md",
            "docs/09-vault-brain/08-business-rules/MEAT_PRODUCTION_RULES.md",
            "docs/08-business-modules/MEAT_PRODUCTION_BATCH_WORKFLOW.md",
            "docs/09-vault-brain/02-agents/sales/SAM.md",
            "docs/09-vault-brain/02-agents/sales/MEAT_SALES_AGENT.md",
            "docs/09-vault-brain/02-agents/sales/SAM_MEAT_PERSONALITY.md",
            "docs/09-vault-brain/05-playbooks/SAM_MEAT_HUMAN_SALES_PLAYBOOK.md",
            "docs/09-vault-brain/09-examples/SAM_MEAT_GOLD_STANDARD_REPLIES.md",
        ],
        "app_routes": [
            "/sales/meat-leads",
            "/sales/meat-driver",
            "/sales/meat-production",
            "/meat-planning",
            "/api/sales/meat-leads",
            "/api/sales/meat-production/batches",
            "/api/sales/meat-pilot-readiness",
            "/api/sales/meat-pricing",
            "/api/sales/channels/chatwoot/sam-meat/inbound",
            "/api/sales/channels/chatwoot/sam-meat/policy",
        ],
        "code_paths": [
            "modules/sales/sam_meat_runtime.py",
            "modules/sales/meat_pilot_readiness.py",
            "modules/sales/meat_production.py",
            "modules/sales/meat_documents.py",
            "modules/sales/meat_match_engine.py",
            "modules/sales/meat_ops.py",
            "modules/sales/meat_fulfillment.py",
            "modules/sales/meat_reconciliation.py",
            "modules/sales/meat_template_pack.py",
            "modules/sales/sales_transaction_routes.py",
            "modules/oom_sakkie/sales_campaign_store.py",
            "templates/meat-sales-leads.html",
            "templates/meat-production.html",
            "templates/meat-driver.html",
            "templates/meat-planning.html",
            "static/js/meatSalesLeads.js",
            "static/js/meatProduction.js",
            "static/js/meatDriver.js",
            "static/js/meatPlanning.js",
            "static/css/meatSalesLeads.css",
            "static/css/meatProduction.css",
            "static/css/meatDriver.css",
        ],
        "tests": [
            "tests/test_sam_meat_runtime.py",
            "tests/test_sam_meat_stress.py",
            "tests/test_sam_meat_intake_remote_smoke.py",
            "tests/test_sam_command_state.py",
            "tests/sam_meat_command_room_playwright.spec.js",
            "tests/test_meat_launch_readiness.py",
            "tests/test_meat_production.py",
            "tests/test_meat_price_book.py",
            "tests/test_meat_match_engine.py",
            "tests/test_meat_ops.py",
            "tests/test_meat_documents.py",
            "tests/test_meat_fulfillment.py",
            "tests/test_meat_reconciliation.py",
            "tests/test_sales_conversation_learning.py",
        ],
        "migrations": [
            "supabase/migrations/202606140002_create_oom_sakkie_sales_leads.sql",
            "supabase/migrations/202606160001_allow_sales_lead_owner_money_path_approval.sql",
            "supabase/migrations/202606160002_allow_sales_lead_customer_followup_send_events.sql",
            "supabase/migrations/202606160003_allow_sales_lead_booking_order_events.sql",
            "supabase/migrations/202606160004_allow_sam_meat_autoreply_events.sql",
            "supabase/migrations/202606160005_create_meat_price_book.sql",
            "supabase/migrations/202606160006_create_meat_ops_rails.sql",
            "supabase/migrations/202606160007_create_meat_instruction_events.sql",
            "supabase/migrations/202606160008_create_meat_fulfillment_events.sql",
            "supabase/migrations/202606160009_create_meat_journey_notification_events.sql",
            "supabase/migrations/202606170001_create_meat_reservation_events.sql",
            "supabase/migrations/202606170002_extend_meat_deposit_event_types.sql",
            "supabase/migrations/202606170003_create_meat_reconciliation_events.sql",
            "supabase/migrations/202606180001_create_meat_sales_conversation_learning_events.sql",
            "supabase/migrations/202607130001_create_meat_processing_batches.sql",
        ],
        "legacy_sources": [
            "docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md",
            "docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/MEAT_INTAKE_HANDOFF_PLAN.md",
        ],
        "must_inspect_before_advice": True,
    },
    "beacon_marketing": {
        "label": "Beacon Marketing",
        "status": "built_gated",
        "summary": "Beacon media library, campaign draft selection, publish packets, manual post evidence, Facebook execution gate, and performance tracking.",
        "keywords": ["beacon", "marketing", "campaign", "facebook", "facebook post", "beacon media", "media asset", "campaign launch"],
        "vault_docs": [
            "docs/09-vault-brain/03-business/BEACON_MARKETING.md",
            "docs/09-vault-brain/04-workflows/BEACON_CAMPAIGN_WORKFLOW.md",
            "docs/09-vault-brain/02-agents/marketing/BEACON.md",
            "docs/09-vault-brain/08-business-rules/MARKETING_RULES.md",
            "docs/09-vault-brain/08-business-rules/MEDIA_PRIVACY_RULES.md",
        ],
        "app_routes": [
            "/sales/beacon-media",
            "/api/beacon/media-policy",
            "/api/beacon/media-assets",
            "/api/beacon/campaign-draft-selection",
            "/api/beacon/campaign-publish-packet",
            "/api/beacon/facebook-image-launch-packet",
            "/api/beacon/manual-post-evidence",
            "/api/beacon/campaign-performance",
            "/api/beacon/facebook-post-executions",
        ],
        "code_paths": [
            "modules/beacon/media_library.py",
            "modules/sales/beacon_campaign.py",
            "modules/sales/sales_transaction_routes.py",
            "templates/beacon-media.html",
            "static/js/beaconMedia.js",
            "static/css/beaconMedia.css",
        ],
        "tests": [
            "tests/test_beacon_media_library.py",
            "tests/test_beacon_campaign.py",
        ],
        "migrations": [
            "supabase/migrations/202606180002_create_beacon_media_library.sql",
            "supabase/migrations/202606180003_create_beacon_manual_post_events.sql",
            "supabase/migrations/202606180004_create_beacon_campaign_performance_events.sql",
            "supabase/migrations/202606180005_create_beacon_facebook_post_execution_events.sql",
            "supabase/migrations/202606180006_extend_beacon_facebook_post_execution_statuses.sql",
        ],
        "legacy_sources": [
            "docs/05-ai/agents/beacon/BEACON_SCOPE.md",
            "docs/05-ai/agents/beacon/MEDIA_STORAGE_DECISION.md",
            "docs/08-business-modules/MEAT_LAUNCH_CAMPAIGN_PACKET.md",
        ],
        "must_inspect_before_advice": True,
    },
    "orders_sales_transactions": {
        "label": "Orders And Sales Transactions",
        "status": "built_supabase_backed",
        "summary": "Orders, order lines, reservations, sales transactions, sale stream totals, and sales dashboard.",
        "keywords": ["order", "orders", "sales transaction", "transaction", "livestock", "slaughter", "sales dashboard", "income"],
        "vault_docs": [
            "docs/09-vault-brain/06-data/ORDER_DATA_MODEL.md",
            "docs/09-vault-brain/08-business-rules/PAYMENT_RULES.md",
            "docs/09-vault-brain/03-business/LIVE_PIG_SALES.md",
        ],
        "app_routes": [
            "/orders",
            "/orders/new",
            "/sales-dashboard",
            "/sales-availability",
            "/api/orders",
            "/api/sales-transactions",
            "/api/pig-weights/sales-dashboard",
        ],
        "code_paths": [
            "modules/orders/order_routes.py",
            "modules/orders/order_service.py",
            "modules/orders/order_read.py",
            "modules/orders/order_write.py",
            "modules/orders/order_reservation.py",
            "modules/orders/order_lifecycle.py",
            "modules/sales/sales_transaction_read.py",
            "modules/sales/sales_transaction_create.py",
            "modules/sales/sales_transaction_update.py",
            "modules/sales/sales_transaction_lifecycle.py",
            "modules/pig_weights/pig_weights_service.py",
            "templates/orders.html",
            "templates/order-detail.html",
            "templates/add-order.html",
            "templates/sales-dashboard.html",
            "templates/sales-availability.html",
            "static/js/orders.js",
            "static/js/orderDetail.js",
            "static/js/salesDashboard.js",
            "static/js/salesAvailability.js",
        ],
        "tests": [
            "tests/test_order_routes.py",
            "tests/test_order_service_crud.py",
            "tests/test_order_service_lifecycle.py",
            "tests/test_order_service_reservation.py",
            "tests/test_order_service_sync.py",
            "tests/test_sales_transaction_routes.py",
            "tests/test_sales_transaction_read.py",
            "tests/test_sales_transaction_create.py",
            "tests/test_sales_transaction_update.py",
            "tests/test_sales_transaction_lifecycle.py",
        ],
        "migrations": [
            "supabase/migrations/202605210002_create_order_sales_tables.sql",
            "supabase/migrations/202605210003_create_sales_transaction_tables.sql",
            "supabase/migrations/202605210004_add_sales_transaction_payment_date.sql",
        ],
        "legacy_sources": [
            "docs/03-google-sheets/sheets/SALES_STOCK_TOTALS.md",
            "docs/04-n8n/workflows/ORDER_STEWARD_HANDOFF_CONTRACTS.md",
        ],
        "must_inspect_before_advice": True,
    },
    "sam_live_stock_sales": {
        "label": "SAM Live Stock Sales",
        "status": "stage_4_env_gated_intake_write",
        "summary": "SAM live pig sales lane authority, router, backend-native runtime, env-gated order-intake write rail, future stock matching, and owner-gated draft/reservation flow.",
        "keywords": [
            "sam live stock",
            "sam livestock",
            "live pig sales",
            "live stock sales",
            "livestock sales",
            "live pig",
            "live pigs",
            "piglets for sale",
            "weaners",
            "growers",
            "finishers",
            "sell pigs",
            "pigs ready to be sold",
            "telegram control card",
            "owner surface",
            "process_sam_live_stock_owner_callback",
        ],
        "vault_docs": [
            "docs/09-vault-brain/02-agents/sales/SAM.md",
            "docs/09-vault-brain/02-agents/sales/LIVE_PIG_SALES_AGENT.md",
            "docs/09-vault-brain/03-business/LIVE_PIG_SALES.md",
            "docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md",
            "docs/09-vault-brain/04-workflows/BEACON_LIVE_STOCK_AWARENESS_WORKFLOW.md",
            "docs/09-vault-brain/05-playbooks/SAM_LIVE_STOCK_HUMAN_SALES_PLAYBOOK.md",
            "docs/09-vault-brain/08-business-rules/LIVE_STOCK_SALES_RULES.md",
            "docs/09-vault-brain/09-examples/SAM_LIVE_STOCK_GOLD_STANDARD_REPLIES.md",
            "docs/09-vault-brain/06-data/ORDER_DATA_MODEL.md",
            "docs/09-vault-brain/08-business-rules/PIG_PURPOSE_RULES.md",
            "docs/09-vault-brain/08-business-rules/HERDMASTER_PIG_ALLOCATION_ALERT_RULES.md",
        ],
        "app_routes": [
            "/sales-dashboard",
            "/sales-availability",
            "/orders",
            "/api/order-intake/context",
            "/api/order-intake/update",
            "/api/orders/active-customer-context",
            "/api/orders/available-pigs",
            "/api/master/orders",
            "/api/master/order-lines",
            "/api/pig-weights/sales-dashboard",
            "/api/pig-weights/pig-allocation-readiness",
        ],
        "code_paths": [
            "modules/sales/sam_sales_router.py",
            "modules/sales/sam_live_stock_runtime.py",
            "modules/sales/sam_live_stock_launch_control.py",
            "modules/oom_sakkie/telegram_direct.py",
            "modules/oom_sakkie/routes.py",
            "modules/pig_weights/pig_weights_service.py",
            "modules/orders/order_intake_service.py",
            "modules/orders/order_service.py",
            "modules/orders/order_write.py",
            "modules/orders/order_routes.py",
            "modules/sales/sales_transaction_read.py",
            "modules/sales/sales_transaction_create.py",
            "templates/sales-dashboard.html",
            "templates/sales-availability.html",
            "templates/orders.html",
            "templates/order-detail.html",
            "static/js/salesDashboard.js",
            "static/js/salesAvailability.js",
            "static/js/orders.js",
        ],
        "tests": [
            "tests/test_sam_sales_router.py",
            "tests/test_sam_live_stock_runtime.py",
            "tests/test_sam_live_stock_launch_control.py",
            "tests/test_oom_sakkie_routes.py",
            "tests/test_order_intake_service.py",
            "tests/test_order_routes.py",
            "tests/test_order_service_reservation.py",
            "tests/test_sales_transaction_read.py",
            "tests/test_pig_allocation_readiness_service.py",
        ],
        "migrations": [
            "supabase/migrations/202605210002_create_order_sales_tables.sql",
            "supabase/migrations/202605210003_create_sales_transaction_tables.sql",
        ],
        "legacy_sources": [
            "docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md",
            "docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/workflow.json",
            "docs/03-google-sheets/sheets/SALES_PRICING.md",
            "docs/03-google-sheets/sheets/SALES_AVAILABILITY.md",
            "docs/03-google-sheets/sheets/SALES_STOCK_TOTALS.md",
            "docs/99-archive/legacy/planning_CHAT_2026-04_n8n_sales_agent_rewire.md",
        ],
        "must_inspect_before_advice": True,
    },
    "pig_allocation_herdmaster": {
        "label": "Pig Allocation And Herdmaster Purpose Intelligence",
        "status": "built_readiness_surface_to_expand",
        "summary": "Pig Allocation readiness, purpose review queue, meat/slaughter windows, stale weights, slow-grower risk, breeding candidates, and future Herdmaster alert logic.",
        "keywords": [
            "pig allocation",
            "allocation alert",
            "purpose review",
            "suggested purpose",
            "keep for breeding",
            "breeding candidate",
            "meat window",
            "slaughter candidate",
            "slow grower",
            "stale weight",
            "sow replacement",
            "herdmaster",
        ],
        "vault_docs": [
            "docs/09-vault-brain/02-agents/farm/HERDMASTER.md",
            "docs/09-vault-brain/04-workflows/HERDMASTER_PURPOSE_REVIEW_WORKFLOW.md",
            "docs/09-vault-brain/06-data/FARM_DATA_MODEL.md",
            "docs/09-vault-brain/08-business-rules/PIG_PURPOSE_RULES.md",
            "docs/09-vault-brain/08-business-rules/HERDMASTER_PIG_ALLOCATION_ALERT_RULES.md",
            "docs/09-vault-brain/00-governance/SOURCE_OF_TRUTH_RULES.md",
        ],
        "app_routes": [
            "/pig-allocation",
            "/api/pig-weights/pig-allocation-readiness",
            "/api/pig-weights/purpose-review",
            "/api/pig-weights/purpose-review/apply",
            "/api/pig-weights/purpose-review/recheck",
        ],
        "code_paths": [
            "modules/pig_weights/pig_weights_service.py",
            "templates/pig-allocation.html",
            "static/js/pigAllocation.js",
        ],
        "tests": [
            "tests/test_pig_allocation_readiness_service.py",
            "tests/test_frontend_route_contracts.py",
        ],
        "migrations": [],
        "legacy_sources": [
            "docs/03-google-sheets/sheets/PIG_MASTER.md",
            "docs/03-google-sheets/sheets/PIG_OVERVIEW.md",
            "docs/03-google-sheets/sheets/WEIGHT_LOG.md",
        ],
        "must_inspect_before_advice": True,
    },
    "pig_litter_attention": {
        "label": "Pig Litter Attention And Reconciliation",
        "status": "built_supabase_backed",
        "summary": "Litter overview, litter detail, farm attention summary, piglet lifecycle reconciliation, and false-positive attention rules.",
        "keywords": [
            "litter attention",
            "litters need attention",
            "needs attention",
            "attention reason",
            "litter detail",
            "litter overview",
            "piglets",
            "born alive",
            "active pig records",
            "sold piglets",
            "disposed piglets",
            "completed sale",
            "farm attention summary",
            "litter counts",
            "reconciliation",
        ],
        "vault_docs": [
            "docs/09-vault-brain/06-data/FARM_DATA_MODEL.md",
            "docs/09-vault-brain/07-standards/TESTING_STANDARD.md",
            "docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md",
        ],
        "app_routes": [
            "/litters",
            "/litter/<litter_id>",
            "/api/pig-weights/litters",
            "/api/pig-weights/litters/<litter_id>",
            "/api/reports/farm-attention-summary",
        ],
        "code_paths": [
            "modules/pig_weights/farm_supabase_read_service.py",
            "modules/pig_weights/pig_weights_service.py",
            "modules/reports/report_service.py",
            "templates/litters.html",
            "templates/litter-detail.html",
            "static/js/litters.js",
            "static/js/litterDetail.js",
        ],
        "tests": [
            "tests/test_farm_supabase_read_service.py",
            "tests/test_pig_weights_litter_service.py",
            "tests/test_pig_weights_dashboard_service.py",
            "tests/test_farm_attention_summary.py",
        ],
        "migrations": [
            "supabase/migrations/202606290003_add_litter_lifecycle_fields.sql",
        ],
        "legacy_sources": [
            "docs/03-google-sheets/sheets/PIG_MASTER.md",
            "docs/03-google-sheets/sheets/PIG_OVERVIEW.md",
            "docs/03-google-sheets/sheets/WEIGHT_LOG.md",
        ],
        "must_inspect_before_advice": True,
    },
    "live_pig_sales_legacy": {
        "label": "Live Pig Sales Legacy",
        "status": "legacy_n8n_to_rebuild_against_supabase",
        "summary": "Live pig sales behavior is primarily legacy n8n/Sheets-era behavior and must not be assumed current without Supabase/app inspection.",
        "keywords": ["live pig", "live sales", "livestock", "whatsapp api", "n8n", "sales stock totals"],
        "vault_docs": [
            "docs/09-vault-brain/03-business/LIVE_PIG_SALES.md",
            "docs/09-vault-brain/02-agents/sales/LIVE_PIG_SALES_AGENT.md",
            "docs/09-vault-brain/02-agents/sales/SAM.md",
        ],
        "app_routes": [
            "/sales-dashboard",
            "/sales-availability",
            "/orders",
            "/api/sales-transactions",
            "/api/pig-weights/sales-dashboard",
        ],
        "code_paths": [
            "modules/pig_weights/pig_weights_service.py",
            "modules/orders/order_service.py",
            "modules/sales/sales_transaction_read.py",
            "templates/sales-dashboard.html",
            "templates/sales-availability.html",
            "static/js/salesDashboard.js",
            "static/js/salesAvailability.js",
        ],
        "tests": [
            "tests/test_sales_transaction_read.py",
            "tests/test_order_service_reservation.py",
            "tests/test_order_sales_live_import.py",
        ],
        "migrations": [
            "supabase/migrations/202605210002_create_order_sales_tables.sql",
            "supabase/migrations/202605210003_create_sales_transaction_tables.sql",
        ],
        "legacy_sources": [
            "docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md",
            "docs/03-google-sheets/sheets/SALES_STOCK_TOTALS.md",
            "docs/99-archive/legacy/planning_CHAT_2026-04_n8n_sales_agent_rewire.md",
        ],
        "must_inspect_before_advice": True,
    },
}


def implementation_source_packet(mission=None, limit_sections=6):
    mission = mission if isinstance(mission, dict) else {}
    query = _mission_query(mission)
    matched = []
    for key, entry in IMPLEMENTATION_SOURCE_MAP.items():
        score, reasons = _score_entry(key, query, entry)
        if score:
            matched.append(_entry_packet(key, entry, score, reasons))
    matched = _filter_matched_sections(sorted(matched, key=lambda item: (-item["score"], item["key"])), query)
    matched = matched[: max(1, int(limit_sections or 6))]
    return {
        "version": SOURCE_MAP_VERSION,
        "query": query,
        "matched_sections": matched,
        "required_inspection_paths": _unique(
            path
            for section in matched
            for group in ("vault_docs", "code_paths", "tests", "migrations", "legacy_sources")
            for path in section.get(group, [])
        ),
        "required_routes": _unique(route for section in matched for route in section.get("app_routes", [])),
        "rule": "Before advising or building, inspect the matched implementation sources; Vault strategy alone is insufficient.",
    }


def _filter_matched_sections(matched, query=""):
    if not matched:
        return []
    filtered = [section for section in matched if int(section.get("score") or 0) >= 30]
    lower = str(query or "").lower()
    keys = {section.get("key") for section in filtered}
    if "sam_live_stock_sales" in keys and not _meat_context(lower):
        filtered = [section for section in filtered if section.get("key") != "sam_meat_sales"]
    if "sam_meat_sales" in keys and not _live_stock_context(lower):
        filtered = [section for section in filtered if section.get("key") != "sam_live_stock_sales"]
    return filtered


def validate_implementation_inspection(artifact, source_packet):
    artifact = artifact if isinstance(artifact, dict) else {}
    source_packet = source_packet if isinstance(source_packet, dict) else {}
    required = set(source_packet.get("required_inspection_paths") or [])
    inspected = set(str(path or "").replace("\\", "/") for path in artifact.get("files_inspected", []) if str(path or "").strip())
    implementation_sources = set(str(path or "").replace("\\", "/") for path in artifact.get("implementation_sources_used", []) if str(path or "").strip())
    cited = inspected | implementation_sources
    matched = sorted(required.intersection(cited))
    required_groups = _required_groups(source_packet)
    group_hits = {
        group: bool(set(paths).intersection(cited))
        for group, paths in required_groups.items()
    }
    missing_groups = [group for group, passed in group_hits.items() if not passed]
    return {
        "version": "charlie_implementation_inspection_v1",
        "passed": bool(matched) and not missing_groups,
        "matched_paths": matched,
        "missing_groups": missing_groups,
        "group_hits": group_hits,
        "required_path_count": len(required),
        "inspected_path_count": len(cited),
    }


def _entry_packet(key, entry, score, reasons):
    packet = {"key": key, "score": score, "reasons": reasons}
    for field in (
        "label",
        "status",
        "summary",
        "vault_docs",
        "app_routes",
        "code_paths",
        "tests",
        "migrations",
        "legacy_sources",
        "must_inspect_before_advice",
    ):
        packet[field] = list(entry[field]) if isinstance(entry.get(field), list) else entry.get(field)
    return packet


def _required_groups(source_packet):
    groups = {"code_paths": [], "tests": [], "vault_docs": []}
    sections = source_packet.get("matched_sections") if isinstance(source_packet.get("matched_sections"), list) else []
    for section in sections:
        for group in list(groups):
            groups[group].extend(section.get(group) if isinstance(section.get(group), list) else [])
        if section.get("legacy_sources"):
            groups.setdefault("legacy_sources", []).extend(section.get("legacy_sources"))
    return {group: _unique(paths) for group, paths in groups.items() if paths}


def _score_entry(key, query, entry):
    lower = query.lower()
    if key == "charlie_core_dashboard" and not _charlie_dashboard_context(lower):
        return 0, []
    score = 0
    reasons = []
    for keyword in entry.get("keywords", []):
        keyword = str(keyword or "").lower()
        if keyword and keyword in lower and not _keyword_is_negated(lower, keyword):
            score += 30 if " " in keyword or keyword in {"sam", "beacon", "herdmaster"} else 18
            reasons.append(f"keyword:{keyword}")
    return score, reasons


def _charlie_dashboard_context(lower):
    dashboard_terms = (
        "/charlie",
        "charlie dashboard",
        "dashboard ui",
        "mission control",
        "command center",
        "runner status",
        "mission queue",
        "owner review button",
        "owner review ui",
        "workflow ui",
    )
    return any(term in lower for term in dashboard_terms)


def _live_stock_context(lower):
    normalized = lower.replace("_", " ").replace("-", " ")
    live_terms = (
        "sam live stock",
        "sam livestock",
        "live stock",
        "livestock",
        "live pig",
        "live pigs",
        "piglet",
        "piglets",
        "weaner",
        "weaners",
        "grower pig",
        "grower pigs",
        "telegram control card",
    )
    return any(term in normalized for term in live_terms)


def _meat_context(lower):
    normalized = lower.replace("_", " ").replace("-", " ")
    meat_terms = (
        "meat",
        "pork",
        "carcass",
        "half carcass",
        "custom cut",
        "butcher",
        "slaughter",
        "abattoir",
        "set a",
        "meat lead",
        "meat sales",
    )
    return any(term in normalized for term in meat_terms)


def _keyword_is_negated(lower, keyword):
    start = 0
    seen = False
    while True:
        index = lower.find(keyword, start)
        if index < 0:
            return seen
        seen = True
        before, after = _keyword_clause_context(lower, keyword, index)
        if not any(marker in before for marker in ("hold all ", "no ", "not ", "do not ", "don't ", "without ", "forbidden ", "forbidden/", "out of scope ", "out-of-scope ", "ignore ", "exclude ", "excluded ")):
            if not any(marker in after for marker in (" forbidden", " forbidden context", " out of scope", " out-of-scope", " on hold", " posting work", " remains on hold", " clause", " clauses")):
                return False
        start = index + len(keyword)


def _keyword_clause_context(lower, keyword, index):
    clause_markers = [".", ";", "\n", "\r"]
    starts = [lower.rfind(marker, 0, index) for marker in clause_markers]
    clause_start = max(starts)
    ends = [lower.find(marker, index + len(keyword)) for marker in clause_markers]
    ends = [end for end in ends if end >= 0]
    clause_end = min(ends) if ends else len(lower)
    before = lower[clause_start + 1:index][-140:]
    after = lower[index:clause_end][: len(keyword) + 120]
    return before, after


def _mission_query(mission):
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    return " ".join(str(piece or "") for piece in [
        mission.get("mission_type", ""),
        mission.get("title", ""),
        mission.get("raw_text", ""),
        vault.get("problem_statement", ""),
        vault.get("desired_outcome", ""),
        metadata.get("owner_comments", ""),
    ]).strip()


def _unique(items):
    result = []
    seen = set()
    for item in items:
        text = str(item or "").replace("\\", "/").strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result
