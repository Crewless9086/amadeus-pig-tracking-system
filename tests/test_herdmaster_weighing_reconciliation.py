"""Synthetic current records; no farm, provider or model operations."""
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from modules.pig_weights.herdmaster_daily_manager_evidence import build_daily_manager_evidence
from modules.pig_weights.herdmaster_weighing_reconciliation import reconcile_weighing
from modules.oom_sakkie.herdmaster_daily_manager_adapter import consume_daily_manager_evidence
from modules.oom_sakkie.herd_read_queries import _weighing
from modules.oom_sakkie.owner_response_composer import compose_manager_brief
from modules.oom_sakkie.farm_manager_loop import build_family_brief
from modules.oom_sakkie.general_manager_worker import normalize_candidate
from modules.oom_sakkie.manager_case_sources import _candidate

TODAY = date(2026, 10, 2)
NOW = datetime(2026, 10, 2, 6, tzinfo=timezone.utc)


def pig(index=1, **changes):
    return dict(pig_id=f"PIG-SYNTHETIC-{index}", tag_number=f"T{index}",
        pig_name=f"Animal {index}", status="Active", on_farm=True,
        animal_type="Grower", purpose="Grow_Out", **changes)


def packet(pigs=None, rows=None, events=(), **kwargs):
    return build_daily_manager_evidence(pigs=pigs or [pig()], window_weights=[],
        prior_weights=[], reconciliation_rows={} if rows is None else rows,
        lifecycle_events=events, analysis_date=TODAY, **kwargs)


def event(kind, at, identity="E1"):
    return {"lifecycle_event_id": identity, "pig_id": pig()["pig_id"],
            "event_type": "individual_weighing_" + kind, "effective_at": at}


def candidate(value, now=NOW):
    result = consume_daily_manager_evidence(value, observed_at=now)
    item = next(item for item in result.work_items if item.dedupe_key == "herdmaster:weekly-weight-evidence")
    return _candidate("herdmaster:" + item.dedupe_key, "HERDMASTER", "watch",
        [*item.provenance.source_refs, "observed:" + now.isoformat()], [],
        item.title + ": " + item.why, item.next_action, now,
        task_class="status_reconciliation", routine_weekly_weighing=True)


def test_current_weight_is_separate_from_previous_capture_window_and_not_a_new_instruction():
    value = packet(rows={"latest_weights": [{"pig_id": pig()["pig_id"],
        "weight_event_id": "WEIGHT-OCT1", "weight_date": "2026-10-01", "weight_kg": 41}]})
    weight = value["weight"]
    assert weight["window"] == {"start": "2026-09-29", "end": "2026-09-30", "timezone": "Africa/Johannesburg"}
    assert weight["current_snapshot"]["covered"] == 0
    assert weight["reconciliation"]["rows"][0]["latest_weight"] == {
        "date": "2026-10-01", "kg": 41, "event_ids": ["WEIGHT-OCT1"]}
    assert weight["individual_weighing_due_now"] == []
    assert weight["reconciliation"]["authorizes_routine_weighing"] is False
    answer = "\n".join(_weighing(value, False))
    assert "29 September 2026" in answer and "1 October 2026" in answer
    assert "41 kg" in answer and "0/1" in answer and "PIG-" not in answer
    assert "do not authorize" in answer


@pytest.mark.parametrize("kind", ["cancelled", "completed"])
def test_current_cancellation_or_completion_after_reporting_window_closes_explicit_due(kind):
    value = packet(events=[event("due", "2026-09-29T08:00:00+02:00"),
        event(kind, "2026-10-01T09:00:00+02:00", "E2")])
    assert value["weight"]["individual_weighing_due_now"] == []
    assert [row["lifecycle_event_id"] for row in value["weight"]["individual_schedule_sources"]] == ["E2"]


def test_current_due_after_window_and_older_overdue_are_not_lost_or_created_from_scheduled():
    for timestamp in ("2026-10-01T08:00:00+02:00", "2026-08-01T08:00:00+02:00"):
        value = packet(events=[event("due", timestamp)])
        assert len(value["weight"]["individual_weighing_due_now"]) == 1
    assert packet(events=[event("scheduled", "2026-09-29T08:00:00+02:00")])["weight"]["individual_weighing_due_now"] == []
    assert packet(events=[event("due", "2026-10-03T08:00:00+02:00")])["weight"]["individual_weighing_due_now"] == []


def test_simultaneous_conflicting_schedule_events_do_not_choose_by_id():
    value = packet(events=[event("due", "2026-10-01T08:00:00+02:00"),
        event("cancelled", "2026-10-01T08:00:00+02:00", "E2")])
    assert value["weight"]["individual_weighing_due_now"] == []
    assert value["weight"]["individual_schedule_conflicts"] == [pig()["pig_id"]]


@pytest.mark.parametrize("status,expected", [("Draft", "allocation_hold"),
    ("Confirmed", "allocation_hold"), ("Completed", "unresolved"), ("Cancelled", "current_on_farm")])
def test_sale_status_never_infers_physical_exit_or_weighing_authority(status, expected):
    result = reconcile_weighing([pig()], {"sales": [{"pig_id": pig()["pig_id"],
        "tag_number": "T1", "sale_item_id": "SI1", "sale_id": "S1", "sale_status": status}]}, analysis_date=TODAY)
    assert result["rows"][0]["state"] == expected
    assert result["rows"][0]["canonical"]["on_farm"] is True
    assert result["rows"][0]["authorizes_routine_weighing"] is False


def test_exact_reservation_is_a_hold_and_cancelled_reservation_with_active_outlet_conflicts():
    rows = {"orders": [{"pig_id": pig()["pig_id"], "tag_number": "T1", "order_id": "O1",
        "order_line_id": "OL1", "line_status": "Reserved", "order_status": "Approved"}],
        "outlets": [{"pig_id": pig()["pig_id"], "outlet_assignment_id": "reservation:OL1",
        "outlet_type": "reservation", "source_record_id": "OL1", "active": True}]}
    assert packet(rows=rows)["weight"]["reconciliation"]["rows"][0]["state"] == "allocation_hold"
    due = packet(rows=rows, events=[event("due", "2026-10-01T08:00:00+02:00")])
    assert due["weight"]["individual_weighing_due_now"] == []
    rows["orders"][0]["line_status"] = "Cancelled"
    assert "reservation_source_conflict" in packet(rows=rows)["weight"]["reconciliation"]["rows"][0]["reasons"]


@pytest.mark.parametrize("foreign", [None, "PIG-FOREIGN"])
def test_tag_only_or_foreign_sale_identity_remains_unresolved(foreign):
    value = packet(rows={"sales": [{"pig_id": foreign, "tag_number": "T1",
        "sale_item_id": "SI1", "sale_id": "S1", "sale_status": "Completed"}]})
    assert "sales_identity_unproven" in value["weight"]["reconciliation"]["rows"][0]["reasons"]


def test_duplicate_tag_or_conflicting_canonical_rows_never_authorizes_due():
    first, second = pig(), pig(2)
    second["tag_number"] = first["tag_number"]
    value = packet(pigs=[first, second], events=[event("due", "2026-10-01T08:00:00+02:00")])
    assert value["weight"]["individual_weighing_due_now"] == []
    assert all(row["state"] == "unresolved" for row in value["weight"]["reconciliation"]["rows"])
    changed = {**first, "on_farm": False}
    assert packet(pigs=[first, changed])["weight"]["individual_weighing_due_now"] == []


@pytest.mark.parametrize("language", ["en", "af"])
def test_large_cohort_has_bounded_case_and_truthful_compact_brief(language):
    value = packet(pigs=[pig(index) for index in range(1000)])
    material = normalize_candidate(candidate(value), now=NOW)
    assert material["dedupe_key"] == "herdmaster:herdmaster:weekly-weight-evidence"
    assert len(material["next_action"]) < 300 and len(material["summary"]) < 500
    result = consume_daily_manager_evidence(value, observed_at=NOW, language=language)
    text = compose_manager_brief(build_family_brief([result], now=NOW), language=language)
    assert "0/1000" in text and len(text) < 650
    assert "PIG-" not in text and "T999" not in text
    assert "will check" not in text and "sal dié" not in text
    assert "checked" in text if language == "en" else "nagegaan" in text
    assert all(not item.metadata.get("physical_work_ready") for item in result.work_items)


def test_deterministic_evidence_changes_only_for_source_change_not_observation_time_or_row_order():
    animals = [pig(1), pig(2)]
    before = packet(pigs=animals)
    after = packet(pigs=list(reversed(animals)))
    assert before["material_digest"] == after["material_digest"]
    assert candidate(before)["evidence_refs"] == candidate(after)["evidence_refs"]
    changed = packet(pigs=animals, rows={"orders": [{"pig_id": pig()["pig_id"],
        "order_id": "NEW", "order_line_id": "NEW-LINE", "line_status": "Reserved", "order_status": "Approved"}]})
    assert changed["material_digest"] != before["material_digest"]
    assert candidate(changed)["dedupe_key"] == candidate(before)["dedupe_key"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), None, 0, -1])
def test_nonfinite_or_invalid_latest_weight_is_unresolved(value):
    result = packet(rows={"latest_weights": [{"pig_id": pig()["pig_id"],
        "weight_event_id": "W1", "weight_date": TODAY, "weight_kg": value}]})
    check = result["weight"]["reconciliation"]["rows"][0]
    assert check["state"] == "unresolved" and check["latest_weight"] is None
    assert "latest_weight_conflict" in check["reasons"]


@pytest.mark.parametrize("field", ["order_status", "line_status"])
def test_unsupported_order_state_is_unresolved(field):
    order = {"pig_id": pig()["pig_id"], "order_id": "O1", "order_line_id": "L1",
             "order_status": "Approved", "line_status": "Reserved", field: "Unsupported"}
    assert packet(rows={"orders": [order]})["weight"]["reconciliation"]["rows"][0]["state"] == "unresolved"


def test_absent_reconciliation_never_promotes_legacy_due_authority():
    value = build_daily_manager_evidence(pigs=[pig()], window_weights=[], prior_weights=[],
        lifecycle_events=[event("due", "2026-10-01T08:00:00+02:00")], analysis_date=TODAY)
    assert value["weight"]["reconciliation"]["state"] == "unavailable"
    assert value["weight"]["individual_weighing_due_now"] == []


@pytest.mark.parametrize("language", ["en", "af"])
def test_missing_familiar_label_never_exposes_internal_identity(language):
    from modules.oom_sakkie.herd_read_queries import _names
    assert _names([{"pig_id": "PIG-INTERNAL", "name": "PIG-INTERNAL", "tag": None}],
        af=language == "af") == ("Onbekende dier" if language == "af" else "Unknown animal")


def test_reconciled_conflict_stays_visible_even_when_weekly_weight_is_recorded():
    value = build_daily_manager_evidence(pigs=[pig()], prior_weights=[], analysis_date=TODAY,
        window_weights=[{"pig_id": pig()["pig_id"], "weight_date": "2026-09-29", "weight_kg": 40}],
        reconciliation_rows={"sales": [{"pig_id": pig()["pig_id"], "tag_number": "T1",
            "sale_item_id": "SI1", "sale_id": "S1", "sale_status": "Completed"}]})
    assert value["weight"]["current_snapshot"]["covered"] == 1
    item = consume_daily_manager_evidence(value, observed_at=NOW).work_items[0]
    assert item.dedupe_key == "herdmaster:weekly-weight-evidence"
    assert item.state.value == "waiting_for_evidence" and "1 unresolved" in item.next_action


def test_nonfinite_weekly_weight_does_not_count_as_coverage():
    value = build_daily_manager_evidence(pigs=[pig()], prior_weights=[], analysis_date=TODAY,
        window_weights=[{"pig_id": pig()["pig_id"], "weight_date": "2026-09-29", "weight_kg": float("nan")}],
        reconciliation_rows={})
    assert value["weight"]["current_snapshot"]["covered"] == 0
    assert value["weight"]["current_snapshot"]["status"] == "conflicting"


@pytest.mark.parametrize("second,conflicting", [("40.0", False),
    ("40.000000", False), ("40.000000000000000001", True), ("41.0", True)])
def test_latest_numeric_weights_compare_values_not_scale_and_preserve_source(second, conflicting):
    weights = [{"pig_id": pig()["pig_id"], "weight_event_id": f"W{index}",
        "weight_date": TODAY, "weight_kg": Decimal(value)}
        for index, value in enumerate(("40", second))]
    value = packet(rows={"latest_weights": weights})
    check = value["weight"]["reconciliation"]["rows"][0]
    assert ("latest_weight_conflict" in check["reasons"]) is conflicting
    assert check["state"] == ("unresolved" if conflicting else "current_on_farm")
    if conflicting:
        assert check["latest_weight"] is None
    else:
        assert check["latest_weight"] == {"date": TODAY.isoformat(), "kg": 40.0,
            "event_ids": ["W0", "W1"]}
    assert {row["weight_event_id"]: str(row["weight_kg"])
        for row in check["sources"]["latest_weights"]} == {"W0": "40", "W1": second}
    # Numeric comparison does not normalize or erase the immutable source rows.
    normalized = deepcopy(weights)
    normalized[1]["weight_kg"] = Decimal("40")
    baseline = packet(rows={"latest_weights": normalized})
    assert check["source_digest"] != baseline["weight"]["reconciliation"]["rows"][0]["source_digest"]
