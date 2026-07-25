"""Disabled-by-default, sanitized SAM Meat truth timing probe."""

import os
from time import monotonic

from modules.sales.sam_meat_database_deadline import (
    DEFAULT_TOTAL_SECONDS,
    SamMeatDatabaseDeadline,
)
from modules.sales.sam_meat_truth_snapshot import load_sam_meat_truth_snapshot


ENABLED_ENV = "SAM_MEAT_READINESS_PROBE_ENABLED"
LEAD_ID_ENV = "SAM_MEAT_READINESS_PROBE_LEAD_ID"
MAX_STATEMENTS = 10


def probe_policy(environ=None):
    source = environ if environ is not None else os.environ
    return {
        "enabled": _truthy(source.get(ENABLED_ENV)),
        "enabled_env": ENABLED_ENV,
        "owner_authentication_required": True,
        "read_only": True,
        "persistence_enabled": False,
        "writes_performed": False,
        "customer_send_enabled": False,
        "telegram_enabled": False,
        "retry_enabled": False,
        "maximum_connections": 1,
        "maximum_statements": MAX_STATEMENTS,
    }


def run_sam_meat_readiness_probe(
    *,
    environ=None,
    snapshot_loader=None,
    deadline_factory=None,
    clock=monotonic,
):
    source = environ if environ is not None else os.environ
    policy = probe_policy(source)
    if not policy["enabled"]:
        return {
            "success": False,
            "status": "sam_meat_readiness_probe_disabled",
            "policy": policy,
            **_authority(),
        }, 503
    lead_id = str(source.get(LEAD_ID_ENV) or "").strip()[:100]
    if not lead_id:
        return {
            "success": False,
            "status": "sam_meat_readiness_probe_subject_unconfigured",
            "policy": policy,
            **_authority(),
        }, 503

    loader = snapshot_loader or load_sam_meat_truth_snapshot
    make_deadline = deadline_factory or (
        lambda: SamMeatDatabaseDeadline(total_seconds=DEFAULT_TOTAL_SECONDS)
    )
    started = clock()
    try:
        snapshot = loader(lead_id, database_deadline=make_deadline())
        budget = snapshot.get("query_budget") if isinstance(snapshot, dict) else {}
        budget = budget if isinstance(budget, dict) else {}
        statement_count = _bounded_int(budget.get("total"), MAX_STATEMENTS + 1)
        connection_count = _bounded_int(budget.get("connections"), 2)
        sections = {
            "catalogue": "Available",
            "pricing": _section_state(snapshot, "pricing"),
            "availability": _section_state(snapshot, "availability"),
            "fulfilment": _section_state(snapshot, "fulfilment"),
            "butcher": _section_state(snapshot, "butcher"),
        }
        complete = (
            statement_count <= MAX_STATEMENTS
            and connection_count == 1
            and all(value == "Available" for value in sections.values())
        )
        status = "sam_meat_readiness_probe_complete" if complete else "Unavailable"
    except Exception:
        statement_count = 0
        connection_count = 0
        sections = {
            name: "Unavailable"
            for name in ("catalogue", "pricing", "availability", "fulfilment", "butcher")
        }
        complete = False
        status = "Unavailable"
    elapsed_ms = max(0, int(round((clock() - started) * 1000)))
    return {
        "success": complete,
        "status": status,
        "elapsed_ms": elapsed_ms,
        "connection_count": connection_count,
        "statement_count": statement_count,
        "unique_query_family_count": statement_count,
        "deadline_enforcement_active": True,
        "sections": sections,
        "policy": policy,
        **_authority(),
    }, 200 if complete else 503


def _section_state(snapshot, key):
    if not isinstance(snapshot, dict) or key not in snapshot:
        return "Unavailable"
    value = snapshot.get(key)
    if value is None:
        return "Unavailable"
    if isinstance(value, dict):
        status = str(value.get("status") or "").strip().lower()
        if status == "unavailable" or value.get("success") is False:
            return "Unavailable"
    return "Available"


def _bounded_int(value, maximum):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return maximum
    return max(0, min(value, maximum))


def _authority():
    return {
        "writes_performed": False,
        "creates_lead": False,
        "persists_review": False,
        "creates_delivery_attempt": False,
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_telegram": False,
        "creates_order": False,
        "confirms_payment": False,
        "reserves_stock": False,
        "allocates_stock": False,
        "changes_stock": False,
        "writes_farm_data": False,
    }


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
