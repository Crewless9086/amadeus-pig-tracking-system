"""Read-only Riversdale auction recommendation support for SAM Live Stock.

This module deliberately does not create an outlet commitment.  The caller must
provide a persisted owner-confirmed cycle before a cohort can be prepared.
"""
import os
from datetime import date, datetime, timedelta

from services.database_service import DATABASE_URL_ENV


AUCTION_OUTLET = "riversdale_monthly_auction"
FORBIDDEN_ACTIONS = [
    "change_pig_lifecycle", "change_pig_purpose", "create_order", "reserve_stock",
    "create_sale", "book_auction", "send_customer_message", "post_publicly",
]


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def first_wednesday(value):
    """Return the first Wednesday for the month containing value."""
    value = _as_date(value) or date.today()
    first = value.replace(day=1)
    return first + timedelta(days=(2 - first.weekday()) % 7)


def next_auction_date(today=None):
    today = _as_date(today) or date.today()
    candidate = first_wednesday(today)
    if candidate < today:
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        candidate = first_wednesday(next_month)
    return candidate


def build_owner_prompts(today=None):
    today = _as_date(today) or date.today()
    auction_date = next_auction_date(today)
    prompts = []
    for days_before in (14, 7):
        due_date = auction_date - timedelta(days=days_before)
        if today >= due_date and today <= auction_date:
            prompts.append({
                "outlet": AUCTION_OUTLET,
                "auction_date": auction_date.isoformat(),
                "due_date": due_date.isoformat(),
                "days_before": days_before,
                "idempotency_key": f"riversdale-auction:{auction_date.isoformat()}:{days_before}",
                "question": "Is the Riversdale auction operating, and what is its confirmed date?",
                "owner_action_required": True,
            })
    return prompts


def queue_due_owner_prompts(queue_outbox, *, today=None):
    """Queue due prompts using stable outbox keys; it never sends them."""
    results = []
    for prompt in build_owner_prompts(today):
        result = queue_outbox(
            "NEEDS_OWNER_AUCTION_CONFIRMATION",
            {**prompt, "notification_kind": "riversdale_auction_confirmation"},
            idempotency_key=prompt["idempotency_key"], channel="telegram",
        )
        results.append(result)
    return results


def load_owner_confirmed_cycle(*, today=None, database_url=None, connect_factory=None):
    """Read the current owner-confirmed advisory auction cycle.

    The migration-backed table is the only operational source for auction
    activation. If it is unavailable, the caller must keep the cohort advisory.
    """
    today = _as_date(today) or date.today()
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url and connect_factory is None:
        return {"operating": False, "confirmed_date": "", "valid": False,
                "status": "auction_cycle_store_not_configured", "source": "public.riversdale_auction_cycles"}
    try:
        if connect_factory is None:
            import psycopg
            connection_factory = lambda: psycopg.connect(database_url, connect_timeout=10)
        else:
            connection_factory = lambda: connect_factory(database_url)
        with connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    select auction_date, operating_confirmed, owner_confirmed_at
                    from public.riversdale_auction_cycles
                    where operating_confirmed = true and auction_date >= %s
                    order by auction_date asc limit 1
                """, (today,))
                row = cursor.fetchone()
    except Exception as exc:
        return {"operating": False, "confirmed_date": "", "valid": False,
                "status": "auction_cycle_read_unavailable", "error_type": exc.__class__.__name__,
                "source": "public.riversdale_auction_cycles"}
    confirmed_date = _as_date(row[0]) if row else None
    return {"operating": bool(row and row[1]), "confirmed_date": confirmed_date.isoformat() if confirmed_date else "",
            "valid": bool(row and confirmed_date), "status": "owner_confirmed_cycle_loaded" if row else "no_owner_confirmed_cycle",
            "confirmed_at": row[2].isoformat() if row and row[2] else "", "source": "public.riversdale_auction_cycles"}


def _has_health_or_quality_hold(pig):
    health = " ".join(str(pig.get(key) or "") for key in ("health_status", "medical_status", "withdrawal_clear")).lower()
    return any(marker in health for marker in ("hold", "brand risk", "quality hold")) or "no" == str(pig.get("withdrawal_clear") or "").lower()


def _truthy(value):
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes"}


def _candidate(pig):
    if pig.get("readiness_bucket") in {"Allocated", "Exited", "Retain / Breeding Candidate", "Needs Data", "Needs Classification"}:
        return False
    if pig.get("reserved_for_order_id") or str(pig.get("reserved_status") or "").lower() == "reserved":
        return False
    if _has_health_or_quality_hold(pig):
        return False
    return pig.get("growth_class") == "Extremely Slow" or _truthy(pig.get("owner_approved_auction_candidate"))


def build_riversdale_auction_packet(allocation, *, today=None, confirmation=None, ledger_evidence=None, sam_demand=None, oom_sakkie_preparation=None):
    """Compose an owner-gated, non-overlapping recommendation cohort.

    Evidence is passed in from the owning agent runtime; missing commercial
    evidence blocks profitability wording rather than inventing a margin.
    """
    today = _as_date(today) or date.today()
    confirmation = confirmation if isinstance(confirmation, dict) else {}
    confirmed_date = _as_date(confirmation.get("confirmed_date"))
    operating = confirmation.get("operating") is True
    confirmation_valid = operating and confirmed_date is not None and confirmed_date >= today
    ledger_evidence = ledger_evidence if isinstance(ledger_evidence, dict) else {}
    sam_demand = sam_demand if isinstance(sam_demand, dict) else {}
    oom_sakkie_preparation = oom_sakkie_preparation if isinstance(oom_sakkie_preparation, dict) else {}
    pigs = allocation.get("pigs", []) if isinstance(allocation, dict) else []

    candidates = []
    excluded = []
    for pig in pigs:
        if _candidate(pig):
            candidates.append({
                "pig_id": pig.get("pig_id", ""), "tag_number": pig.get("tag_number", ""),
                "outlet": AUCTION_OUTLET, "active_outlet": "auction_advisory" if confirmation_valid else "none",
                "growth_class": pig.get("growth_class", ""), "growth_reason": pig.get("growth_reason", ""),
                "herdmaster_evidence": {"litter_quality": pig.get("litter_quality", ""), "health_status": pig.get("health_status", ""), "withdrawal_clear": pig.get("withdrawal_clear", "")},
                "ledger_evidence": ledger_evidence.get(pig.get("pig_id"), ledger_evidence.get("default", {})),
                "sam_demand_evidence": sam_demand.get("summary", "not_supplied"),
                "oom_sakkie_preparation": oom_sakkie_preparation.get("summary", "not_supplied"),
                "owner_approval_required": True,
            })
        else:
            excluded.append({"pig_id": pig.get("pig_id", ""), "reason": "existing outlet, retention, data, reservation, health, or eligibility rule blocks auction advisory"})

    commercial_evidence_complete = all(bool(item["ledger_evidence"].get("feed_cost_to_date") is not None and item["ledger_evidence"].get("likely_auction_price") is not None) for item in candidates)
    return {
        "success": True,
        "status": "cohort_ready_for_owner_review" if confirmation_valid else "awaiting_owner_auction_confirmation",
        "owner_agent": "sam-live-stock",
        "outlet": AUCTION_OUTLET,
        "generated_date": today.isoformat(),
        "scheduled_auction_date": next_auction_date(today).isoformat(),
        "owner_prompts": build_owner_prompts(today),
        "confirmation": {"operating": operating, "confirmed_date": confirmed_date.isoformat() if confirmed_date else "", "valid": confirmation_valid},
        "cohort": candidates if confirmation_valid else [],
        "candidate_preview": candidates,
        "excluded": excluded,
        "one_pig_one_active_outlet": True,
        "profitability_recommendation": "ready_for_owner_review" if candidates and commercial_evidence_complete else "blocked_missing_feed_cost_or_likely_price_evidence",
        "forbidden_actions": FORBIDDEN_ACTIONS,
        "writes_to_supabase": False, "writes_to_sheets": False, "writes_orders": False,
        "creates_reservations": False, "creates_sales": False, "changes_farm_lifecycle": False,
    }
