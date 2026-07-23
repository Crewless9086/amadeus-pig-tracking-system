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
        # The watchdog runs daily.  Queue each reminder on its own due day;
        # the outbox key makes retries safe without turning a missed run into
        # a pair of misleading late reminders on auction day.
        if today == due_date:
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
    health = " ".join(str(pig.get(key) or "") for key in (
        "health_status", "medical_status", "withdrawal_clear", "brand_quality_status",
        "quality_status", "observed_quality",
    )).lower()
    return any(marker in health for marker in (
        "hold", "brand risk", "quality hold", "not suitable", "unfit",
    )) or "no" == str(pig.get("withdrawal_clear") or "").lower()


def _truthy(value):
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes"}


def _exclusion_reason(pig):
    if pig.get("readiness_bucket") in {"Allocated", "Exited", "Retain / Breeding Candidate", "Needs Data", "Needs Classification"}:
        return "allocation state is already allocated, exited, retained, or insufficient for safe auction review"
    if pig.get("reserved_for_order_id") or str(pig.get("reserved_status") or "").lower() == "reserved":
        return "existing customer order or reservation has priority"
    if _has_health_or_quality_hold(pig):
        return "health, withdrawal, welfare, or brand-quality hold blocks auction review"
    if str(pig.get("available_for_sale") or "").lower() == "yes":
        return "current customer-sale suitability has priority over auction"
    if pig.get("growth_class") != "Extremely Slow" and not _truthy(pig.get("owner_approved_auction_candidate")):
        return "not an extremely slow grower or separately owner-approved auction candidate"
    return ""


def _candidate(pig):
    return not _exclusion_reason(pig)


def _canonical_pig_id(pig):
    """Return a stable identity or an empty value that must fail cohort assembly."""
    return str(pig.get("pig_id") or "").strip()


def _money(value):
    """Return a finite non-negative money value, or None when not evidenced."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    return amount if amount >= 0 else None


def _profitability_evidence(ledger):
    """Make an auction margin disposition explicit instead of inferring one.

    `auction_costs` is optional only when it is supplied as zero.  This keeps a
    missing fee/transport estimate from being silently treated as a profit.
    """
    ledger = ledger if isinstance(ledger, dict) else {}
    feed_cost = _money(ledger.get("feed_cost_to_date"))
    likely_price = _money(ledger.get("likely_auction_price"))
    auction_costs = _money(ledger.get("auction_costs"))
    if feed_cost is None or likely_price is None or auction_costs is None:
        return {"disposition": "unknown", "net_auction_margin": None}
    margin = likely_price - feed_cost - auction_costs
    return {
        "disposition": "positive" if margin > 0 else "break_even_or_loss",
        "net_auction_margin": margin,
    }


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

    # An auction cohort is only safe to describe as non-overlapping when every
    # source row has one non-empty canonical identity.  Duplicate source rows
    # are an allocation-data conflict, not evidence that one animal may appear
    # twice in an owner packet.  Exclude every affected row rather than picking
    # a winner or silently collapsing potentially conflicting facts.
    identity_counts = {}
    for pig in pigs:
        pig_id = _canonical_pig_id(pig) if isinstance(pig, dict) else ""
        identity_counts[pig_id] = identity_counts.get(pig_id, 0) + 1
    invalid_identities = {pig_id for pig_id, count in identity_counts.items() if not pig_id or count > 1}

    candidates = []
    excluded = []
    for pig in pigs:
        pig_id = _canonical_pig_id(pig) if isinstance(pig, dict) else ""
        if not pig_id:
            excluded.append({"pig_id": "", "reason": "missing canonical pig identity blocks non-overlapping auction review"})
        elif pig_id in invalid_identities:
            excluded.append({"pig_id": pig_id, "reason": "duplicate canonical pig identity blocks non-overlapping auction review"})
        elif _candidate(pig):
            candidates.append({
                "pig_id": pig_id, "tag_number": pig.get("tag_number", ""),
                "outlet": AUCTION_OUTLET, "active_outlet": "auction_advisory" if confirmation_valid else "none",
                "growth_class": pig.get("growth_class", ""), "growth_reason": pig.get("growth_reason", ""),
                "herdmaster_evidence": {
                    "litter_quality": pig.get("litter_quality", ""),
                    "health_status": pig.get("health_status", ""),
                    "withdrawal_clear": pig.get("withdrawal_clear", ""),
                    "observed_quality": pig.get("observed_quality", pig.get("quality_status", "")),
                },
                "ledger_evidence": ledger_evidence.get(pig_id, ledger_evidence.get("default", {})),
                "sam_demand_evidence": sam_demand.get("summary", "not_supplied"),
                "oom_sakkie_preparation": oom_sakkie_preparation.get("summary", "not_supplied"),
                "owner_approval_required": True,
            })
        else:
            excluded.append({"pig_id": pig_id, "reason": _exclusion_reason(pig)})

    for item in candidates:
        item["profitability_evidence"] = _profitability_evidence(item["ledger_evidence"])
    commercial_evidence_complete = all(
        item["profitability_evidence"]["disposition"] == "positive" for item in candidates
    )
    observed_quality_complete = all(
        str(item["herdmaster_evidence"].get("observed_quality") or "").strip()
        for item in candidates
    )
    sam_evidence_complete = bool(sam_demand.get("summary"))
    preparation_complete = bool(oom_sakkie_preparation.get("summary"))
    coordination_complete = commercial_evidence_complete and observed_quality_complete and sam_evidence_complete and preparation_complete
    recommendation_status = (
        "cohort_ready_for_owner_review" if confirmation_valid and coordination_complete
        else "cohort_needs_coordinated_evidence" if confirmation_valid
        else "awaiting_owner_auction_confirmation"
    )
    return {
        "success": True,
        "status": recommendation_status,
        "owner_agent": "sam-live-stock",
        "outlet": AUCTION_OUTLET,
        "generated_date": today.isoformat(),
        "scheduled_auction_date": next_auction_date(today).isoformat(),
        "owner_prompts": build_owner_prompts(today),
        "confirmation": {"operating": operating, "confirmed_date": confirmed_date.isoformat() if confirmed_date else "", "valid": confirmation_valid},
        "cohort": candidates if confirmation_valid else [],
        "candidate_preview": candidates,
        "excluded": excluded,
        "one_pig_one_active_outlet": not invalid_identities and len({item["pig_id"] for item in candidates}) == len(candidates),
        "coordination_evidence": {
            "herdmaster": "canonical_allocation_rows",
            "observed_quality_complete": observed_quality_complete,
            "ledger_complete": commercial_evidence_complete,
            "sam_demand_complete": sam_evidence_complete,
            "oom_sakkie_preparation_complete": preparation_complete,
        },
        "profitability_recommendation": (
            "ready_for_owner_review" if candidates and coordination_complete
            else "blocked_negative_or_unknown_auction_margin" if candidates and not commercial_evidence_complete
            else "blocked_missing_required_coordination_evidence"
        ),
        "forbidden_actions": FORBIDDEN_ACTIONS,
        "writes_to_supabase": False, "writes_to_sheets": False, "writes_orders": False,
        "creates_reservations": False, "creates_sales": False, "changes_farm_lifecycle": False,
    }
