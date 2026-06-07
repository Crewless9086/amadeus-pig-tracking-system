from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SpecialistManifest:
    slug: str
    name: str
    role: str
    status: str
    risk_level: int
    allowed_mode: str
    approval_required_for: tuple[str, ...]
    first_inputs: tuple[str, ...]
    first_outputs: tuple[str, ...]


SPECIALIST_MANIFESTS = (
    SpecialistManifest(
        slug="sentinel",
        name="Sentinel",
        role="Security and safety advisor.",
        status="planned",
        risk_level=0,
        allowed_mode="read_only_advisory",
        approval_required_for=("any_code_change", "any_policy_change", "any_secret_access"),
        first_inputs=("runtime_policy", "tool_registry", "review_packet", "route_tests"),
        first_outputs=("security_findings", "risk_brief"),
    ),
    SpecialistManifest(
        slug="forge",
        name="Forge",
        role="Code steward for tests, diffs, and handoffs.",
        status="planned",
        risk_level=0,
        allowed_mode="read_only_advisory",
        approval_required_for=("any_code_change", "any_migration", "any_dependency_change"),
        first_inputs=("git_diff", "test_results", "route_contracts", "docs"),
        first_outputs=("code_review_findings", "handoff_notes"),
    ),
    SpecialistManifest(
        slug="prism",
        name="Prism",
        role="Design director for kiosk and farm UI.",
        status="planned",
        risk_level=0,
        allowed_mode="read_only_advisory",
        approval_required_for=("any_ui_change", "any_generated_asset", "any_new_surface"),
        first_inputs=("kiosk_template", "kiosk_css", "screenshots", "owner_feedback"),
        first_outputs=("design_findings", "ui_slice_recommendations"),
    ),
    SpecialistManifest(
        slug="ledger",
        name="Ledger",
        role="Business and profit advisor.",
        status="planned",
        risk_level=0,
        allowed_mode="read_only_advisory",
        approval_required_for=("any_customer_message", "any_quote", "any_invoice", "any_price_change"),
        first_inputs=("sales_dashboard", "meat_planning", "orders", "future_cost_tables"),
        first_outputs=("business_brief", "margin_questions"),
    ),
    SpecialistManifest(
        slug="atlas",
        name="Atlas",
        role="Farm data analyst for trends and anomalies.",
        status="planned",
        risk_level=0,
        allowed_mode="read_only_advisory",
        approval_required_for=("any_data_write", "any_alert_rule", "any_dashboard_change"),
        first_inputs=("weight_reports", "telemetry_rollups", "sales_dashboard", "pig_allocation"),
        first_outputs=("trend_brief", "anomaly_notes"),
    ),
    SpecialistManifest(
        slug="rootline",
        name="Rootline",
        role="Crop, plant, weather, and irrigation specialist.",
        status="planned",
        risk_level=0,
        allowed_mode="read_only_advisory",
        approval_required_for=("any_irrigation_control", "any_physical_action", "any_crop_schedule_write"),
        first_inputs=("weather_now", "weather_today", "weather_forecast", "irrigation_status"),
        first_outputs=("crop_attention_brief", "inspection_questions"),
    ),
    SpecialistManifest(
        slug="herdmaster",
        name="Herdmaster",
        role="Pig lifecycle and herd attention specialist.",
        status="planned",
        risk_level=0,
        allowed_mode="read_only_advisory",
        approval_required_for=("any_pig_update", "any_litter_update", "any_medical_write"),
        first_inputs=("pig_allocation", "litter_attention", "weight_report", "breeding_analytics"),
        first_outputs=("herd_attention_brief", "pig_review_questions"),
    ),
    SpecialistManifest(
        slug="butcher",
        name="Butcher",
        role="Pork pipeline, meat, livestock, and slaughter readiness specialist.",
        status="planned",
        risk_level=0,
        allowed_mode="read_only_advisory",
        approval_required_for=("any_sale_creation", "any_customer_message", "any_slaughter_booking"),
        first_inputs=("meat_planning", "sales_dashboard", "pig_allocation"),
        first_outputs=("pork_pipeline_brief", "preorder_gap_notes"),
    ),
    SpecialistManifest(
        slug="beacon",
        name="Beacon",
        role="Media, market voice, and public draft specialist.",
        status="planned",
        risk_level=1,
        allowed_mode="draft_only",
        approval_required_for=("any_public_post", "any_customer_message", "any_media_upload"),
        first_inputs=("approved_brand_rules", "owner_photos", "product_catalogue"),
        first_outputs=("draft_posts", "content_packets"),
    ),
    SpecialistManifest(
        slug="quartermaster",
        name="Quartermaster",
        role="Operations, inventory, supplies, and recurring task planner.",
        status="planned",
        risk_level=0,
        allowed_mode="read_only_advisory",
        approval_required_for=("any_purchase", "any_stock_write", "any_supplier_message"),
        first_inputs=("product_register", "medical_logs", "farm_attention", "future_inventory_tables"),
        first_outputs=("operations_brief", "shopping_questions"),
    ),
    SpecialistManifest(
        slug="gatekeeper",
        name="Gatekeeper",
        role="Routing and approval controller.",
        status="planned",
        risk_level=0,
        allowed_mode="internal_planning_only",
        approval_required_for=("any_delegation_loop", "any_write_tool", "any_channel_cutover"),
        first_inputs=("specialist_manifests", "tool_registry", "runtime_policy", "review_packet"),
        first_outputs=("routing_plan", "approval_requirements"),
    ),
)


def list_specialist_manifests():
    return [asdict(manifest) for manifest in SPECIALIST_MANIFESTS]
