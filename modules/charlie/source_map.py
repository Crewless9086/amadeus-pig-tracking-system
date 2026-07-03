from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_MAP_VERSION = "charlie_implementation_source_map_v1"


IMPLEMENTATION_SOURCE_MAP = {
    "sam_meat_sales": {
        "label": "SAM Meat Sales",
        "status": "built_active_pilot",
        "summary": "Backend-native SAM meat sales intake, command room, quote, payment, reservation, fulfilment, reconciliation, and learning rails.",
        "keywords": ["sam", "meat", "meat sales", "half carcass", "set a", "chatwoot", "whatsapp", "preorder", "quote", "deposit"],
        "vault_docs": [
            "docs/09-vault-brain/03-business/MEAT_SALES.md",
            "docs/09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md",
            "docs/09-vault-brain/08-business-rules/MEAT_SALES_RULES.md",
            "docs/09-vault-brain/02-agents/sales/SAM.md",
            "docs/09-vault-brain/02-agents/sales/MEAT_SALES_AGENT.md",
        ],
        "app_routes": [
            "/sales/meat-leads",
            "/sales/meat-driver",
            "/meat-planning",
            "/api/sales/meat-leads",
            "/api/sales/meat-pilot-readiness",
            "/api/sales/meat-pricing",
            "/api/sales/channels/chatwoot/sam-meat/inbound",
            "/api/sales/channels/chatwoot/sam-meat/policy",
        ],
        "code_paths": [
            "modules/sales/sam_meat_runtime.py",
            "modules/sales/meat_pilot_readiness.py",
            "modules/sales/meat_documents.py",
            "modules/sales/meat_match_engine.py",
            "modules/sales/meat_ops.py",
            "modules/sales/meat_fulfillment.py",
            "modules/sales/meat_reconciliation.py",
            "modules/sales/meat_template_pack.py",
            "modules/sales/sales_transaction_routes.py",
            "modules/oom_sakkie/sales_campaign_store.py",
            "templates/meat-sales-leads.html",
            "templates/meat-driver.html",
            "templates/meat-planning.html",
            "static/js/meatSalesLeads.js",
            "static/js/meatDriver.js",
            "static/js/meatPlanning.js",
            "static/css/meatSalesLeads.css",
            "static/css/meatDriver.css",
        ],
        "tests": [
            "tests/test_sam_meat_runtime.py",
            "tests/test_sam_meat_stress.py",
            "tests/test_sam_meat_intake_remote_smoke.py",
            "tests/test_sam_command_state.py",
            "tests/sam_meat_command_room_playwright.spec.js",
            "tests/test_meat_launch_readiness.py",
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
        "keywords": ["beacon", "marketing", "campaign", "post", "facebook", "media", "asset", "launch"],
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
        score, reasons = _score_entry(query, entry)
        if score:
            matched.append(_entry_packet(key, entry, score, reasons))
    matched = sorted(matched, key=lambda item: (-item["score"], item["key"]))[: max(1, int(limit_sections or 6))]
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


def _score_entry(query, entry):
    lower = query.lower()
    score = 0
    reasons = []
    for keyword in entry.get("keywords", []):
        keyword = str(keyword or "").lower()
        if keyword and keyword in lower:
            score += 30 if " " in keyword else 18
            reasons.append(f"keyword:{keyword}")
    return score, reasons


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
