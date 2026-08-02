from datetime import datetime, timedelta, timezone
import json
from unittest.mock import patch

import pytest

from modules.sales.sam_live_stock_availability_observation import (
    AUTHORITY_FLAGS,
    build_availability_observation_preview,
    resolve_authoritative_availability,
)


OBSERVED = "2026-07-27T18:30:00+02:00"


def animal(identity, category, sex="Female", **overrides):
    row = {
        "pig_id": identity,
        "sale_category": category,
        "sex": sex,
        "purpose": "Sale",
        "live_stock_sale_eligible": True,
        "evidence_complete": True,
        "allocation_evidence_state": "known_unallocated",
        "reserved_status": "Not_Reserved",
        "medical_status": "Clear",
        "withdrawal_evidence_state": "Cleared",
        "status": "Active",
        "on_farm": "Yes",
    }
    row.update(overrides)
    return row


def test_preview_has_exact_category_sex_lineage_and_no_pig_ids():
    preview = build_availability_observation_preview(
        [
            animal("PRIVATE-1", "Young Piglets"),
            animal("PRIVATE-2", "Weaner Piglets"),
            animal("PRIVATE-3", "Weaner Piglets", sex="Male"),
        ],
        proposed_observed_at=OBSERVED,
    )
    assert preview["success"] is True
    assert preview["observed_at_utc"] == "2026-07-27T16:30:00+00:00"
    assert preview["eligible_totals"]["Young Piglets"]["female"] == 1
    assert preview["eligible_totals"]["Weaner Piglets"]["female"] == 1
    assert preview["eligible_totals"]["Weaner Piglets"]["male"] == 1
    assert preview["contains_pig_ids"] is False
    public = {key: value for key, value in preview.items() if key != "_lineage"}
    encoded = json.dumps(public)
    assert "PRIVATE-" not in encoded
    assert all(value is False for value in AUTHORITY_FLAGS.values())


def test_known_per_animal_exclusions_override_cohort_confirmation():
    preview = build_availability_observation_preview(
        [
            animal("PRIVATE-1", "Young Piglets"),
            animal("PRIVATE-2", "Young Piglets", reserved_status="Reserved"),
            animal(
                "PRIVATE-3",
                "Young Piglets",
                allocation_evidence_state="allocated",
            ),
            animal("PRIVATE-4", "Young Piglets", medical_status="Hold"),
        ],
        proposed_observed_at=OBSERVED,
    )
    assert preview["eligible_totals"]["Young Piglets"]["female"] == 1
    assert preview["exclusions"] == {
        "allocation_unavailable_or_conflicting": 1,
        "medical_clearance_unavailable": 1,
        "reserved_or_reservation_unknown": 1,
    }


def test_unresolved_identity_or_category_is_visible_not_silently_counted():
    preview = build_availability_observation_preview(
        [animal("", "", sex="")],
        proposed_observed_at=OBSERVED,
    )
    assert preview["unresolved_count"] == 1
    assert preview["eligible_totals"]["Young Piglets"]["all"] == 0
    assert preview["exclusions"]["identity_or_category_unavailable"] == 1


@pytest.mark.parametrize(
    "value",
    [
        "",
        "2026-07-27",
        "2026-07-27T18:30:00",
        "2026-02-30T18:30:00+02:00",
        123,
    ],
)
def test_missing_malformed_or_naive_owner_timestamp_fails_closed(value):
    preview = build_availability_observation_preview(
        [animal("PRIVATE-1", "Young Piglets")],
        proposed_observed_at=value,
    )
    assert preview["success"] is False
    assert preview["status"] == "authoritative_observed_at_required"
    assert preview["customer_send_allowed"] is False


def test_same_snapshot_is_deterministic_and_changed_state_changes_hash():
    rows = [animal("PRIVATE-1", "Young Piglets")]
    first = build_availability_observation_preview(
        rows, proposed_observed_at=OBSERVED
    )
    repeated = build_availability_observation_preview(
        rows, proposed_observed_at=OBSERVED
    )
    changed = build_availability_observation_preview(
        [animal("PRIVATE-1", "Young Piglets", reserved_status="Reserved")],
        proposed_observed_at=OBSERVED,
    )
    assert first["cohort_hash"] == repeated["cohort_hash"]
    assert first["_lineage"] == repeated["_lineage"]
    assert changed["cohort_hash"] != first["cohort_hash"]


def test_newer_individual_observation_changes_exact_lineage():
    older = build_availability_observation_preview(
        [
            animal(
                "PRIVATE-1",
                "Young Piglets",
                eligibility_observed_at="2026-07-27T15:00:00Z",
            )
        ],
        proposed_observed_at=OBSERVED,
    )
    newer = build_availability_observation_preview(
        [
            animal(
                "PRIVATE-1",
                "Young Piglets",
                eligibility_observed_at="2026-07-27T17:00:00Z",
            )
        ],
        proposed_observed_at=OBSERVED,
    )
    assert older["cohort_hash"] != newer["cohort_hash"]


def test_fresh_exact_observation_supplies_counts_and_lineage():
    rows = [animal("PRIVATE-1", "Young Piglets")]
    preview = build_availability_observation_preview(
        rows, proposed_observed_at=OBSERVED
    )
    observed = datetime.fromisoformat(preview["observed_at_utc"])
    stored = (
        "SAM-LIVE-STOCK-AVAIL-ONE",
        preview["cohort_hash"],
        observed,
        datetime.fromisoformat(preview["expires_at_utc"]),
        preview["eligible_totals"],
        preview["exclusions"],
        preview["unresolved_count"],
        preview["row_count"],
        preview["_lineage"],
    )
    with patch(
        "modules.sales.sam_live_stock_availability_observation._load_latest_observation",
        return_value=stored,
    ):
        result = resolve_authoritative_availability(
            rows,
            {"success": True, "matched_count": 1},
            database_url="postgresql://configured",
            now=observed + timedelta(hours=1),
        )
    assert result["observation_evidence_state"] == "fresh"
    assert result["evidence_complete"] is True
    assert result["customer_category_counts"]["Young Piglets"]["female"] == 1
    assert "PRIVATE-1" not in json.dumps(result)


def test_stale_or_conflicting_observation_fails_closed():
    rows = [animal("PRIVATE-1", "Young Piglets")]
    preview = build_availability_observation_preview(
        rows, proposed_observed_at=OBSERVED
    )
    observed = datetime.fromisoformat(preview["observed_at_utc"])
    base = (
        "SAM-LIVE-STOCK-AVAIL-ONE",
        preview["cohort_hash"],
        observed,
        datetime.fromisoformat(preview["expires_at_utc"]),
        preview["eligible_totals"],
        preview["exclusions"],
        0,
        preview["row_count"],
        preview["_lineage"],
    )
    with patch(
        "modules.sales.sam_live_stock_availability_observation._load_latest_observation",
        return_value=base,
    ):
        stale = resolve_authoritative_availability(
            rows,
            {"success": True, "matched_count": 1, "evidence_complete": True},
            database_url="postgresql://configured",
            now=observed + timedelta(hours=25),
        )
        conflict = resolve_authoritative_availability(
            [animal("PRIVATE-1", "Young Piglets", reserved_status="Reserved")],
            {"success": True, "matched_count": 1, "evidence_complete": True},
            database_url="postgresql://configured",
            now=observed + timedelta(hours=1),
        )
    for result, state in ((stale, "stale"), (conflict, "conflicting")):
        assert result["observation_evidence_state"] == state
        assert result["evidence_complete"] is False
        assert result["customer_category_counts_complete"] is False
        assert result["observation_timestamp"] == ""


@pytest.mark.parametrize("tampered_index,tampered_value", [
    (4, {"Young Piglets": {"all": 99, "female": 99, "male": 0, "unknown": 0}}),
    (5, {"fabricated_exclusion": 99}),
    (6, 99),
    (7, 99),
    (8, [{"animal_key_hash": "tampered"}]),
])
def test_tampered_persisted_summary_or_lineage_fails_closed(
    tampered_index, tampered_value
):
    rows = [animal("PRIVATE-1", "Young Piglets")]
    preview = build_availability_observation_preview(
        rows, proposed_observed_at=OBSERVED
    )
    observed = datetime.fromisoformat(preview["observed_at_utc"])
    stored = [
        "SAM-LIVE-STOCK-AVAIL-ONE",
        preview["cohort_hash"],
        observed,
        datetime.fromisoformat(preview["expires_at_utc"]),
        preview["eligible_totals"],
        preview["exclusions"],
        preview["unresolved_count"],
        preview["row_count"],
        preview["_lineage"],
    ]
    stored[tampered_index] = tampered_value
    with patch(
        "modules.sales.sam_live_stock_availability_observation._load_latest_observation",
        return_value=tuple(stored),
    ):
        result = resolve_authoritative_availability(
            rows,
            {"success": True, "matched_count": 1},
            database_url="postgresql://configured",
            now=observed + timedelta(hours=1),
        )
    assert result["observation_evidence_state"] == "conflicting"
    assert result["evidence_complete"] is False


def test_expected_observation_binding_rejects_concurrent_latest_event():
    rows = [animal("PRIVATE-1", "Young Piglets")]
    preview = build_availability_observation_preview(
        rows, proposed_observed_at=OBSERVED
    )
    observed = datetime.fromisoformat(preview["observed_at_utc"])
    stored = (
        "SAM-LIVE-STOCK-AVAIL-NEWER",
        preview["cohort_hash"],
        observed,
        datetime.fromisoformat(preview["expires_at_utc"]),
        preview["eligible_totals"],
        preview["exclusions"],
        0,
        1,
        preview["_lineage"],
    )
    with patch(
        "modules.sales.sam_live_stock_availability_observation._load_latest_observation",
        return_value=stored,
    ):
        result = resolve_authoritative_availability(
            rows,
            {"success": True, "matched_count": 1},
            database_url="postgresql://configured",
            now=observed + timedelta(hours=1),
            expected_observation_event_id="SAM-LIVE-STOCK-AVAIL-CONFIRMED",
            expected_cohort_hash=preview["cohort_hash"],
            expected_observed_at=preview["observed_at_utc"],
            expected_expires_at=preview["expires_at_utc"],
        )
    assert result["observation_evidence_state"] == "conflicting"
    assert result["evidence_complete"] is False
