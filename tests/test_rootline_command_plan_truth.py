"""Offline command duty -> canonical reader -> saved plan -> owner delivery proofs."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import re

import pytest

from modules.telemetry import rootline_water_energy_plan as plan
from modules.telemetry import rootline_command_acceptance as ca
from modules.telemetry.rootline_irrigation_lifecycle import project_execution_shutdown_exceptions
from modules.telemetry.rootline_irrigation_history import _attach_latest_zone_executions
from modules.telemetry.rootline_specialist_result import project_water_energy_plan
from modules.telemetry.rootline_timed_control import timed_control_scope
from modules.oom_sakkie.rootline_reassessment_lifecycle import reassess_rootline
from tests.test_rootline_command_mode import start, receipt, recover, ENV, confirm_fixture
from tests.test_rootline_water_energy_plan import daily_program_facts
from tests.test_oom_sakkie_rootline_reassessment_delivery import memory_store

CLAIM = datetime.fromisoformat("2026-11-22T00:08:20.445882+00:00")
FIRST = datetime.fromisoformat("2026-11-22T00:59:59+00:00")
SECOND = datetime.fromisoformat("2026-11-22T01:03:06+00:00")


@pytest.fixture(autouse=True)
def approved_mode():
    with timed_control_scope(ENV):
        yield


def execution(zone="E12345", at=CLAIM):
    _, _, store, transport, clock = start(zone, at=at)
    # Provider acceptance follows the original claim; it does not renew OFF.
    accepted = receipt(store.active, "ON", at=at+timedelta(seconds=14))
    for row in [*store.rows, store.active]:
        if row.get("command_on_receipt") is not None:
            row["command_on_receipt"] = deepcopy(accepted)
            confirm_fixture(row, at=at+timedelta(seconds=15))
        if row.get("action") == "record_on_outcome":
            row["on_outcome"] = deepcopy(accepted)
    return store, transport, clock


class ReadConnection:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def cursor(self): return self
    def execute(self, sql, params=None): self.queries.append((sql, params))
    def fetchall(self):
        sql = self.queries[-1][0]
        if "select review_json->'rootline_execution'" not in sql: return []
        # Emulate the production SELECT's action restriction, so missing claim
        # or OFF-outcome rows in that real query cannot be hidden by a mock.
        selected = set(re.findall(r"'([^']+)'", sql))
        return [(deepcopy(row),) for row in self.rows if row.get("action") in selected]


def read_managed(monkeypatch, rows, now):
    from modules.oom_sakkie import bounded_postgres_read
    connection = ReadConnection(rows)
    monkeypatch.setattr(bounded_postgres_read, "connect_bounded_read", lambda **_: connection)
    result = plan._read_managed_device_evidence("offline://fixture", now, evidence_cutoff=now)
    assert result["status"] == "Available", result
    assert all(params == (now,) for _, params in connection.queries)
    return result


def saved_program():
    midnight = FIRST.astimezone(plan.ZA_TZ).replace(hour=0, minute=0, second=0)
    saved = plan.build_daily_program(daily_program_facts(midnight), "2026-11-22", now=midnight)
    # Exact published order: E02:00, B04:00, C06:00, A08:00 SAST.
    for order, zone in enumerate(("E12345", "B12345", "C12345", "A12345"), 1):
        for tasks in (saved["candidate_tasks"], saved["daily_program"]["base_tasks"]):
            task = next(t for t in tasks if t["task_id"] == "irrigation_"+zone)
            at = midnight+timedelta(hours=order*2)
            end = at+timedelta(hours=2)
            task.update(scheduled_order=order, planned_start_at=at.isoformat(),
                planned_end_at=end.isoformat(), preferred_window=at.isoformat(),
                due_window={"start": at.isoformat(), "end": end.isoformat()})
    return saved


def projected(monkeypatch, rows, now, saved=None, *, rain=False):
    saved = saved or saved_program()
    facts = daily_program_facts(now.astimezone(plan.ZA_TZ))
    facts.update(read_managed(monkeypatch, rows, now))
    facts["irrigation_history"]["snapshot_cutoff"] = now.isoformat()
    _attach_latest_zone_executions(facts["irrigation_history"], rows, canonical_ordered=True)
    if rain:
        facts["weather"]["rain_rate_mm_h"] = 5
        for zone in facts["irrigation"]["zones"]: zone["live_rain_release_proven"] = False
    current = plan.project_saved_program_for_execution(saved, facts, now=now)
    return current, project_water_energy_plan(current, now=now)


def exceptions(rows, now=SECOND):
    return project_execution_shutdown_exceptions(rows, evidence_cutoff=now, canonical_ordered=True)


def test_real_e_duty_reader_plan_owner_notice_is_stable_on_cutoff_only(monkeypatch):
    store, transport, _ = execution()
    saved = saved_program(); before = deepcopy(saved)
    first, current = projected(monkeypatch, store.rows, FIRST, saved)
    second, later = projected(monkeypatch, store.rows, SECOND, saved)
    one = {t["task_id"]: t for t in first["candidate_tasks"] if t.get("scheduled_order")}
    two = {t["task_id"]: t for t in second["candidate_tasks"] if t.get("scheduled_order")}
    for key in one:
        for field in ("planned_start_at", "planned_end_at", "preferred_window", "due_window"):
            assert one[key][field] == two[key][field]
        assert one[key]["requested_total_duration_minutes"] == 120
    e = one["irrigation_E12345"]
    assert datetime.fromisoformat(e["planned_start_at"]) == CLAIM+timedelta(seconds=14)
    assert datetime.fromisoformat(e["planned_end_at"]) == CLAIM+timedelta(hours=2)
    assert one["irrigation_B12345"]["planned_start_at"] == e["planned_end_at"]
    assert current["irrigation_lifecycle"]["E12345"]["state"] == "Started"
    assert not current["irrigation_lifecycle"]["E12345"].get("execution_exceptions")
    assert saved == before and len(transport.calls) == 1
    rows, state_store = memory_store()
    def run(result):
        return reassess_rootline(owner_user_id="42", chat_id="42", trigger="canonical_plan_reassessment",
            specialist_loader=lambda: result, state_store=state_store)
    notice = run(current)
    assert notice["notify_owner"] is True
    packet = rows[notice["notification_identity"]]
    assert "unverified shutdown" not in packet["answer"]
    state_store("mark_delivered", notice["notification_identity"],
        {"delivery_state": "delivered", "provider_message_id": "offline-confirmed"})
    assert run(later)["notify_owner"] is False
    _, changed = projected(monkeypatch, store.rows, SECOND, saved, rain=True)
    assert run(changed)["notify_owner"] is True


@pytest.mark.parametrize("zone", ["A12345", "B12345", "C12345", "E12345"])
def test_all_irrigation_occupies_schedule_and_confirmed_parent_supports_fertilizer(monkeypatch, zone):
    store, _, _ = execution(zone)
    result = read_managed(monkeypatch, store.rows, SECOND)
    assert result["irrigation_schedule_context"]["zone_id"] == zone
    assert bool(result["active_irrigation_context"])
    assert exceptions(store.rows) == []


@pytest.mark.parametrize("change", ["no_claim", "no_outcome", "receipt_digest", "receipt_binding",
    "future_on", "primary_missing", "primary_conflict", "native_conflict", "mixed_mode", "failed",
    "stopping", "uncertain_on", "off_attempt", "two_open", "expired"])
def test_missing_conflicting_or_overdue_command_data_never_clears_alarm_or_occupancy(monkeypatch, change):
    store, _, _ = execution(); rows = deepcopy(store.rows); now = SECOND
    active = next(r for r in reversed(rows) if r.get("action") == "mark_active")
    if change == "no_claim": rows = [r for r in rows if r.get("action") != "claim_before_on"]
    elif change == "no_outcome": rows = [r for r in rows if r.get("action") != "record_on_outcome"]
    elif change == "receipt_digest": active["command_on_receipt"]["receipt_sha256"] = "invalid"
    elif change == "receipt_binding": active["command_on_receipt"]["channel"] = 1
    elif change == "future_on": active["command_on_receipt"] = receipt(active, "ON", at=SECOND+timedelta(seconds=1))
    elif change == "primary_missing": active["primary_stop_deadline"] = None
    elif change == "primary_conflict": active["primary_stop_deadline"] = (CLAIM+timedelta(hours=3)).isoformat()
    elif change == "native_conflict": active["native_fail_stop_deadline"] = "malformed"
    elif change == "mixed_mode": next(r for r in rows if r.get("action") == "claim_before_on")["acceptance_mode"] = "legacy"
    elif change in {"failed", "stopping", "off_attempt"}:
        rows.append({**active, "action": {"failed":"contain_zone", "stopping":"mark_stopping", "off_attempt":"claim_off_attempt"}[change]})
    elif change == "uncertain_on": active["command_on_receipt"]["accepted_unambiguous"] = False
    elif change == "two_open": rows += execution("B12345")[0].rows
    elif change == "expired": now = CLAIM+timedelta(hours=2)
    if change != "two_open": assert exceptions(rows, now)
    managed = read_managed(monkeypatch, rows, now)
    assert managed["irrigation_schedule_context"] == {"status": "Unknown"}
    current, _ = projected(monkeypatch, rows, now)
    assert all(t.get("zone_decision") == "Hold" for t in current["candidate_tasks"] if t["task_id"].startswith("irrigation_"))


def test_accepted_off_resolves_occupancy_without_physical_credit(monkeypatch):
    store, transport, clock = execution(); clock[0] = CLAIM+timedelta(hours=2, seconds=1)
    result = recover(store, transport, clock)
    assert result["status"] == "irrigation_off_command_accepted"
    managed = read_managed(monkeypatch, store.rows, clock[0])
    assert managed["irrigation_schedule_context"] is None
    assert result["execution"]["shutdown_verified"] is False
    assert result["execution"]["verified_runtime_seconds"] == 0
    for row in store.rows:
        if row.get("action") == "record_off_outcome": row["outcome"] = {}
    assert read_managed(monkeypatch, store.rows, clock[0])["irrigation_schedule_context"] == {"status": "Unknown"}


def test_legacy_and_historical_exceptions_remain_visible():
    store, _, _ = execution(); legacy = deepcopy(store.rows)
    for row in legacy: row.pop("acceptance_mode", None)
    assert exceptions(legacy)
    assert plan._irrigation_schedule_context(legacy, now=SECOND) is None
    history = daily_program_facts(SECOND)["irrigation_history"]
    history["snapshot_cutoff"] = SECOND.isoformat()
    for row in legacy: row["execution_id"] = "LEGACY-E"
    _attach_latest_zone_executions(history, legacy+store.rows, canonical_ordered=True)
    pending = history["zones"]["E12345"]["execution_exceptions"]
    assert pending and {r["execution_id"] for r in pending} == {"LEGACY-E"}


def test_cross_midnight_owned_duty_keeps_original_deadline(monkeypatch):
    at = CLAIM.replace(hour=21, minute=30)-timedelta(days=1)
    store, _, _ = execution(at=at)
    now = at+timedelta(hours=1)
    result = read_managed(monkeypatch, store.rows, now)["irrigation_schedule_context"]
    assert result["status"] == "Active"
    assert datetime.fromisoformat(result["primary_stop_deadline"]) == at+timedelta(hours=2)
    assert datetime.fromisoformat(result["accepted_start_at"]) == at+timedelta(seconds=14)


def test_failed_canonical_read_never_becomes_idle(monkeypatch):
    from modules.oom_sakkie import bounded_postgres_read
    def fail(**_): raise RuntimeError("offline read failure")
    monkeypatch.setattr(bounded_postgres_read, "connect_bounded_read", fail)
    result = plan._read_managed_device_evidence("offline://fixture", SECOND, evidence_cutoff=SECOND)
    assert result["irrigation_schedule_context"] == {"status": "Unknown"}


@pytest.mark.parametrize("change", ["future_off", "later_failure", "conflicting_claim", "malformed_terminal"])
def test_uncertain_terminal_never_discards_owned_schedule(monkeypatch, change):
    store, transport, clock = execution(); clock[0] = CLAIM+timedelta(hours=2, seconds=1)
    done = recover(store, transport, clock)["execution"]
    if change == "future_off":
        future = receipt(done, "OFF", at=clock[0]+timedelta(seconds=1))
        for row in store.rows:
            if row.get("action") == "record_completed": row["command_off_receipt"] = future
            if row.get("action") == "record_off_outcome": row["outcome"] = future
    elif change == "later_failure": store.rows.append({**done, "action": "contain_zone", "state": "Failed"})
    elif change == "conflicting_claim":
        row = next(r for r in store.rows if r.get("action") == "claim_before_on")
        row["primary_stop_deadline"] = (CLAIM+timedelta(hours=3)).isoformat()
    else: store.rows.append({**done, "action": "record_completed", "command_off_receipt": {}})
    assert read_managed(monkeypatch, store.rows, clock[0])["irrigation_schedule_context"] == {"status": "Unknown"}


def test_malformed_active_identity_fails_closed():
    store, _, _ = execution()
    active = next(row for row in store.rows if row.get("action") == "mark_active")
    active["execution_id"] = {"unexpected": "object"}
    assert ca.active_irrigation_duty(store.rows, now=SECOND) is None
    assert plan._irrigation_schedule_context(store.rows, now=SECOND) == {"status": "Unknown"}



def test_unknown_occupancy_preserves_completed_objectives():
    saved = saved_program()
    complete = next(t for t in saved["candidate_tasks"] if t["task_id"] == "irrigation_B12345")
    complete.update(zone_decision="Completed", recommendation="Do not run")
    before = deepcopy(complete)
    plan._adjust_live_slots(saved, {"irrigation_schedule_context": {"status": "Unknown"}}, SECOND)
    assert complete == before
