"""One read-only purpose-work projection shared by manager and owner queries."""
from __future__ import annotations

from collections import defaultdict
from contextlib import nullcontext
from datetime import date, datetime, timedelta
import hashlib
import json
import time

from modules.oom_sakkie.bounded_postgres_read import ReadBudgetCursor, connect_bounded_read
from modules.pig_weights.herdmaster_weighing_reconciliation import (
    CONTRACT as RECONCILIATION_CONTRACT, _positive_finite,
    load_reconciliation_rows, reconcile_weighing)

CONTRACT = "herdmaster.purpose_work.v1"
UNKNOWN_PURPOSES = {"", "unknown", "unallocated", "not allocated", "not_allocated"}
PURPOSE_STAGES = {"piglet", "weaner", "grower", "finisher"}
ALLOCATION_STAGE_ROW_BOUND = 10000


class _PurposeReadCursor:
    """Contain every borrowed allocation stage before projecting its rows."""
    def __init__(self, cursor, deadline):
        self.cursor = cursor
        self.budget = ReadBudgetCursor(cursor, deadline, failure_kind="purpose_work_read_deadline")

    def __enter__(self):
        self.cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self.cursor.__exit__(*args)

    def execute(self, sql, params=()):
        return self.budget.execute(sql, params)

    def fetchall(self):
        rows = self.cursor.fetchmany(ALLOCATION_STAGE_ROW_BOUND + 1)
        if len(rows) > ALLOCATION_STAGE_ROW_BOUND:
            raise ValueError("purpose_work_allocation_source_row_bound_exceeded")
        return rows

    def __getattr__(self, name):
        return getattr(self.cursor, name)


class _PurposeReadConnection:
    def __init__(self, connection, deadline):
        self.connection, self.deadline = connection, deadline

    def cursor(self):
        return _PurposeReadCursor(self.connection.cursor(), self.deadline)


def build_purpose_work(allocation, reconciliation, *, analysis_date):
    """Consume canonical eligibility; weekly absence never establishes due work."""
    from modules.pig_weights.pig_weights_service import POST_WEAN_PURPOSE_REVIEW_DAYS
    from modules.pig_weights.herdmaster_daily_manager_evidence import _usable_tag
    if allocation.get("success") is not True:
        return {"contract": CONTRACT, "state": "unavailable", "cohorts": [], "material_digest": ""}
    rows = list(allocation.get("pigs") or ())
    if len(rows) > 5000:
        raise ValueError("purpose_work_row_bound_exceeded")
    checked = (reconciliation.get("contract") == RECONCILIATION_CONTRACT
               and reconciliation.get("state") == "checked")
    checks, identities, grouped = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in reconciliation.get("rows", ()):
        checks[str(row.get("pig_id") or "")].append(row)
    for row in rows:
        identities[str(row.get("pig_id") or "")].append(row)
    for row in rows:
        if (str(row.get("purpose") or "").strip().casefold() not in UNKNOWN_PURPOSES
                or str(row.get("animal_type") or "").casefold() in {"sow", "boar"}
                or row.get("purpose_review_eligible") is not True
                or (str(row.get("status") or "").casefold() in {"sold", "dead", "inactive", "slaughtered", "culled"}
                    and str(row.get("on_farm") or "").casefold() == "no")):
            continue
        pig_id = str(row.get("pig_id") or "")
        key = str(row.get("litter_id") or pig_id)
        if not pig_id or not key:
            raise ValueError("purpose_work_identity_missing")
        if any(item["pig_id"] == pig_id for item in grouped[key]):
            continue
        reasons = []
        if str(row.get("animal_type") or "").casefold() not in PURPOSE_STAGES:
            reasons.append("purpose_stage_unproven")
        check = checks[pig_id][0] if len(checks[pig_id]) == 1 else {}
        if len(identities[pig_id]) != 1 or len(checks[pig_id]) > 1:
            reasons.append("canonical_identity_conflict")
        if not checked or not check:
            reasons.append("reconciliation_unavailable")
        elif check.get("state") != "current_on_farm":
            reasons.extend(check.get("reasons") or [str(check.get("state") or "reconciliation_unknown")])
        canonical = check.get("canonical") or {}
        if check and (str(canonical.get("pig_id") or "") != pig_id
                or str(canonical.get("tag_number") or "").strip().casefold() != str(row.get("tag_number") or "").strip().casefold()
                or str(canonical.get("status") or "").casefold() != str(row.get("status") or "").casefold()
                or canonical.get("on_farm") is not True
                or str(row.get("on_farm") or "").casefold() != "yes"
                or str(canonical.get("animal_type") or "").casefold() != str(row.get("animal_type") or "").casefold()
                or str(canonical.get("purpose") or "").strip().casefold() != str(row.get("purpose") or "").strip().casefold()):
            reasons.append("allocation_reconciliation_identity_conflict")
        tag = str(row.get("tag_number") or "").strip()
        if not _usable_tag(tag):
            reasons.append("visible_identity_missing")
        wean, latest = _day(row.get("wean_date")), _day(row.get("latest_weight_date"))
        due = wean + timedelta(days=POST_WEAN_PURPOSE_REVIEW_DAYS) if wean else None
        if (wean is None or due > analysis_date or (latest and latest > analysis_date)
                or (row.get("latest_weight_date") and latest is None)):
            reasons.append("purpose_chronology_unproven")
        phase = row.get("purpose_review_state")
        current_weight = check.get("latest_weight") or {}
        current_day = _day(current_weight.get("date"))
        if phase == "decision_due":
            if (not latest or not wean or latest <= wean or current_day != latest
                    or isinstance(row.get("latest_weight_kg"), bool)
                    or not _positive_finite(row.get("latest_weight_kg"))
                    or current_weight.get("kg") != row.get("latest_weight_kg")):
                reasons.append("qualifying_weight_unproven")
        elif (phase != "weight_due" or (latest and wean and latest > wean)
                or (current_day and wean and current_day > wean)):
            reasons.append("purpose_phase_unproven")
        grouped[key].append({"pig_id": pig_id, "tag": tag,
            "name": (check.get("canonical") or {}).get("pig_name"),
            "wean_date": wean.isoformat() if wean else None,
            "due_date": due.isoformat() if due else None,
            "latest_weight_date": latest.isoformat() if latest else None,
            "latest_weight_kg": row.get("latest_weight_kg"),
            "phase": phase,
            "reconciliation_state": check.get("state") or "unavailable",
            "source_digest": check.get("source_digest") or "",
            "reasons": sorted(set(reasons)),
            "litter_id": str(row.get("litter_id") or ""),
            "sow_label": str(row.get("sow_tag_number") or "").strip()})
    cohorts = []
    for key, values in sorted(grouped.items()):
        members = sorted(values, key=lambda row: row["pig_id"])
        blocked = [{"pig_id": row["pig_id"], "reasons": row["reasons"]}
                   for row in members if row["reasons"]]
        weighing = [row["pig_id"] for row in members
                    if row["phase"] == "weight_due" and not row["reasons"]]
        phase = "weight_due" if weighing else "held" if blocked else "decision_due"
        cohort = {"case_key": "herdmaster:purpose-review:" + key, "cohort_key": key,
            "litter_id": members[0]["litter_id"],
            "label": next((row["sow_label"] for row in members if row["sow_label"]), ""),
            "phase": phase, "member_ids": [row["pig_id"] for row in members],
            "weighing_ids": weighing,
            "members": members, "blocked": blocked,
            "rule_days": POST_WEAN_PURPOSE_REVIEW_DAYS, "physical_work_ready": phase == "weight_due"}
        cohorts.append({**cohort, "material_digest": _digest(cohort)})
    material = {"contract": CONTRACT, "state": "checked" if checked else "unavailable", "cohorts": cohorts}
    return {**material, "material_digest": _digest(material)}


def load_purpose_work_snapshot(*, analysis_date, connection=None, deadline=None,
                               reconciliation=None, database_url=None, connect=None):
    """Allocation and commercial evidence belongs to one bounded snapshot."""
    from modules.pig_weights.farm_supabase_read_service import get_allocation_input_rows
    from modules.pig_weights.pig_weights_service import get_pig_allocation_readiness
    deadline = deadline if deadline is not None else time.monotonic() + 10
    owns_connection = connection is None
    context = connect_bounded_read(database_url=database_url, connect=connect) if owns_connection else nullcontext(connection)
    with context as connection:
        with connection.cursor() as raw:
            if owns_connection:
                raw.execute("set transaction isolation level repeatable read read only")
            cursor = ReadBudgetCursor(raw, deadline, failure_kind="purpose_work_read_deadline")
            def borrowed(_url):
                return nullcontext(_PurposeReadConnection(connection, deadline))
            borrowed.transaction_managed = True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("purpose_work_read_deadline")
            snapshot = get_allocation_input_rows(connect_factory=borrowed,
                deadline_seconds=remaining, today=analysis_date)
            if reconciliation is None:
                cursor.execute("""select pig_id,tag_number,pig_name,status,on_farm,animal_type,purpose
                    from public.current_canonical_pigs order by pig_id limit 5001""")
                names = [column.name for column in cursor.description]
                pigs = [dict(zip(names, row)) for row in cursor.fetchall()]
                if len(pigs) > 5000:
                    raise ValueError("purpose_work_row_bound_exceeded")
                reconciliation = reconcile_weighing(pigs,
                    load_reconciliation_rows(cursor, pigs, analysis_date), analysis_date=analysis_date)
            allocation = get_pig_allocation_readiness(today=analysis_date,
                allow_sheet_fallback=False, canonical_inputs=snapshot)
            result = {**snapshot, "purpose_work": build_purpose_work(
                allocation, reconciliation, analysis_date=analysis_date)}
            if time.monotonic() >= deadline:
                raise TimeoutError("purpose_work_read_deadline")
            return result


def _day(value):
    try:
        return value.date() if isinstance(value, datetime) else value if isinstance(value, date) else date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest().upper()
