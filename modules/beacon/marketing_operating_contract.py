from datetime import datetime, timezone
from math import isfinite


CONTRACT_VERSION = "beacon_marketing_operating_contract_v1"
SUPPORTED_SALE_STREAMS = ("meat", "live_stock", "live_stock_awareness")
FRESHNESS_HOURS = 24

AUTHORITY = {
    "posts_publicly": False,
    "schedules_content": False,
    "spends_money": False,
    "sends_customer_messages": False,
    "calls_meta": False,
    "calls_chatwoot": False,
    "creates_orders": False,
    "creates_reservations": False,
    "changes_stock": False,
    "writes_farm_lifecycle": False,
    "approval_executes_action": False,
}

CHANNELS = {
    "meat": ("facebook_organic", "instagram_organic", "whatsapp_status"),
    "live_stock": ("facebook_organic", "instagram_organic", "whatsapp_status"),
    "live_stock_awareness": ("facebook_organic", "instagram_organic"),
}


def _utc(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip().replace("Z", "+00:00")
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_fulfilment_target(evidence=None, now=None):
    evidence = evidence if isinstance(evidence, dict) else {}
    now = _utc(now) or datetime.now(timezone.utc)
    required = (
        "source_id", "observed_at", "unit", "verified_available",
        "existing_commitments", "operational_reserve", "safety_buffer",
    )
    missing = [
        key for key in required
        if evidence.get(key) is None
        or (isinstance(evidence.get(key), str) and not evidence.get(key).strip())
    ]
    errors = [f"missing_{key}" for key in missing]
    observed_at = _utc(evidence.get("observed_at"))
    if evidence.get("observed_at") and observed_at is None:
        errors.append("invalid_observed_at")
    age_hours = None
    if observed_at:
        age_hours = max(0, (now - observed_at).total_seconds() / 3600)
        if observed_at > now:
            errors.append("observed_at_in_future")
        elif age_hours > FRESHNESS_HOURS:
            errors.append("stale_fulfilment_evidence")

    values = {}
    for key in ("verified_available", "existing_commitments", "operational_reserve", "safety_buffer"):
        try:
            values[key] = float(evidence.get(key))
            if not isfinite(values[key]):
                errors.append(f"invalid_{key}")
            elif values[key] < 0:
                errors.append(f"negative_{key}")
        except (TypeError, ValueError):
            if key not in missing:
                errors.append(f"invalid_{key}")

    ceiling = 0
    if not errors:
        ceiling = max(0, values["verified_available"] - values["existing_commitments"] - values["operational_reserve"] - values["safety_buffer"])
    return {
        "status": "ready_for_owner_review" if not errors and ceiling > 0 else "blocked",
        "demand_ceiling": ceiling,
        "unit": str(evidence.get("unit") or ""),
        "source_id": str(evidence.get("source_id") or ""),
        "observed_at": observed_at.isoformat() if observed_at else "",
        "freshness_hours": FRESHNESS_HOURS,
        "evidence_age_hours": round(age_hours, 2) if age_hours is not None else None,
        "formula": "max(0, verified_available - existing_commitments - operational_reserve - safety_buffer)",
        "errors": sorted(set(errors)),
    }


def calculate_kpi(numerator, denominator):
    try:
        numerator = float(numerator)
        denominator = float(denominator)
    except (TypeError, ValueError):
        return {"status": "invalid_evidence", "value": None}
    if denominator <= 0:
        return {"status": "not_available_zero_denominator", "value": None}
    return {"status": "calculated", "value": round(numerator / denominator, 4)}


def build_beacon_marketing_operating_contract(sale_stream="meat", fulfilment_evidence=None, now=None):
    sale_stream = str(sale_stream or "meat").strip().lower()
    if sale_stream not in SUPPORTED_SALE_STREAMS:
        raise ValueError("unsupported_sale_stream")
    target = build_fulfilment_target(fulfilment_evidence, now=now)
    return {
        "success": True,
        "contract_version": CONTRACT_VERSION,
        "mode": "beacon_marketing_operating_contract_owner_review_only",
        "sale_stream": sale_stream,
        "approval_status": "owner_review_required",
        "objectives": [
            {"key": "qualified_demand", "status": "proposed", "rule": "Generate measurable qualified demand within the verified fulfilment ceiling."},
            {"key": "owner_efficiency", "status": "proposed", "rule": "Prepare exact review packets that reduce owner planning time without executing them."},
            {"key": "learning", "status": "proposed", "rule": "Use attributable evidence to improve future owner-reviewed recommendations."},
        ],
        "brand_kit": {
            "status": "proposed_owner_decision_required",
            "voice": ["plain_spoken", "warm", "credible", "specific", "never_pushy"],
            "copy_rules": ["state only verified availability", "avoid artificial urgency", "never promise final price timing delivery or booking"],
            "visual_rules": ["use approved farm-authentic media only", "show animals and products respectfully", "no sensitive or identifying media without explicit public-use evidence", "no misleading stock imagery"],
        },
        "campaign_target": target,
        "channel_policy": {
            "status": "proposed_owner_decision_required",
            "selection_mode": "allowlist",
            "allowed_channels": list(CHANNELS[sale_stream]),
            "unknown_channels_allowed": False,
            "paid_channels_allowed": False,
            "customer_direct_send_allowed": False,
        },
        "kpis": [
            {"key": "qualified_lead_rate", "status": "proposed", "numerator": "qualified_leads", "denominator": "attributed_inquiries", "formula": "qualified_leads / attributed_inquiries", "unit": "ratio", "attribution_window": "owner_decision_required", "evidence_source": "campaign_performance_events", "zero_denominator": "not_available"},
            {"key": "inquiry_conversion_rate", "status": "proposed", "numerator": "fulfilled_sales", "denominator": "attributed_inquiries", "formula": "fulfilled_sales / attributed_inquiries", "unit": "ratio", "attribution_window": "owner_decision_required", "evidence_source": "sales_and_fulfilment_records", "zero_denominator": "not_available"},
            {"key": "capacity_utilisation", "status": "proposed", "numerator": "attributed_fulfilled_units", "denominator": "demand_ceiling", "formula": "attributed_fulfilled_units / demand_ceiling", "unit": "ratio", "attribution_window": "campaign_window", "evidence_source": "verified_fulfilment_evidence", "zero_denominator": "not_available"},
        ],
        "approval_tiers": [
            {"tier": "advisory", "allows": ["inspect", "calculate", "draft"], "owner_gate": False, "executes_action": False},
            {"tier": "owner_review", "allows": ["approve_edit_reject_contract", "approve_edit_reject_exact_packet"], "owner_gate": True, "executes_action": False},
            {"tier": "execution", "status": "outside_this_contract", "allows": [], "owner_gate": True, "executes_action": False},
        ],
        "authority": dict(AUTHORITY),
        "provenance": {
            "policy_sources": [
                "docs/09-vault-brain/03-business/BEACON_MARKETING.md",
                "docs/09-vault-brain/02-agents/marketing/BEACON.md",
                "docs/09-vault-brain/08-business-rules/MARKETING_RULES.md",
                "docs/09-vault-brain/08-business-rules/MEDIA_PRIVACY_RULES.md",
            ],
            "fulfilment_source_id": target["source_id"],
        },
        "owner_decisions_required": [
            "approve_or_edit_brand_voice_and_visual_rules",
            "approve_channel_allowlists_by_sale_stream",
            "approve_kpi_attribution_windows_and_success_thresholds",
            "resolve_media_privacy_and_public_use_policy",
        ],
    }
