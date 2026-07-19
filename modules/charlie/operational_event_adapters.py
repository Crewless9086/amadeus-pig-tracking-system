"""Non-destructive adapters from existing business records into operational events."""

from __future__ import annotations

from modules.charlie.operational_events import DOMAINS, build_event, utc_now


DOMAIN_DEFAULTS = {
    "leads": ("lead", "lead_id", "lead.observed", "customer_personal"),
    "conversations": ("conversation", "conversation_id", "conversation.observed", "customer_personal"),
    "orders": ("order", "order_id", "order.observed", "customer_personal"),
    "payments": ("payment", "payment_id", "payment.observed", "sensitive_business"),
    "animals": ("animal", "pig_id", "animal.observed", "internal"),
    "campaigns": ("campaign", "campaign_id", "campaign.observed", "internal"),
    "missions": ("mission", "mission_id", "mission.observed", "owner_private"),
    "incidents": ("incident", "incident_id", "incident.observed", "owner_private"),
    "approvals": ("approval", "approval_id", "approval.observed", "owner_private"),
    "outcomes": ("outcome", "outcome_id", "outcome.observed", "sensitive_business"),
}


def adapt_source_record(domain, record, *, source_system, observed_at=None, idempotency_namespace="backfill"):
    domain = str(domain or "").strip().lower()
    record = record if isinstance(record, dict) else {}
    if domain not in DOMAINS:
        return {"accepted": False, "status": "source_domain_invalid"}
    aggregate_type, id_field, event_type, privacy = DOMAIN_DEFAULTS[domain]
    aggregate_id = str(record.get(id_field) or record.get("id") or "").strip()
    if not aggregate_id:
        return {"accepted": False, "status": "source_record_id_required", "id_field": id_field}
    occurred_at = str(record.get("updated_at") or record.get("created_at") or observed_at or utc_now())
    source_ref = f"{source_system}/{aggregate_id}"
    packet = {
        "event_type": str(record.get("event_type") or event_type),
        "domain": domain,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "source_system": str(source_system or "unknown_source"),
        "source_record_id": aggregate_id,
        "authority_tier": "observe",
        "privacy_class": privacy,
        "occurred_at": occurred_at,
        "freshness_at": occurred_at,
        "payload": dict(record),
        "provenance": {"source_ref": source_ref, "adapter": "operational_event_adapters_v1", "non_destructive": True},
        "idempotency_key": f"{idempotency_namespace}:{domain}:{source_system}:{aggregate_id}:{occurred_at}",
        "actor_type": "source_reconciliation",
    }
    return build_event(packet, recorded_at=observed_at or utc_now())


def reconcile_source_records(domain, records, *, source_system, observed_at=None):
    ready, rejected = [], []
    for record in records or []:
        result = adapt_source_record(domain, record, source_system=source_system, observed_at=observed_at)
        (ready if result.get("accepted") else rejected).append(result.get("event") if result.get("accepted") else result)
    return {
        "status": "source_reconciliation_ready",
        "domain": domain,
        "source_system": source_system,
        "events": ready,
        "rejected": rejected,
        "source_records_changed": False,
    }
