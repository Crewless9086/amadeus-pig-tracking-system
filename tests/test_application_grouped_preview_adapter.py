from copy import deepcopy
from unittest.mock import patch

from modules.pig_weights import pig_weights_controller
from modules.pig_weights.application_grouped_preview_adapter import attach_canonical_preview
from modules.pig_weights.canonical_grouped_preview import preview_application_typed


PIGS = [
    {"pig_id": "PIG-OPAQUE-A", "tag_number": "A1", "status": "Active", "on_farm": True, "current_pen_id": "PEN-OLD"},
    {"pig_id": "PIG-OPAQUE-B", "tag_number": "B2", "status": "Active", "on_farm": True, "current_pen_id": "PEN-OLD"},
]
PENS = [{"pen_id": "PEN-OPAQUE-D3", "pen_name": "D3", "active": True}]
LEGACY = {
    "ok": True, "success": True, "accepted_count": 2,
    "accepted_rows": [
        {"pig_id": "PIG-OPAQUE-A", "tag_number": "A1", "weight_date": "2026-08-13", "weight_kg": 47.2, "moved_to_pen_id": "PEN-OPAQUE-D3", "condition_notes": "", "current_pen_id": "PEN-OLD"},
        {"pig_id": "PIG-OPAQUE-B", "tag_number": "B2", "weight_date": "2026-08-13", "weight_kg": 118.0, "moved_to_pen_id": "PEN-OPAQUE-D3", "condition_notes": "", "current_pen_id": "PEN-OLD"},
    ],
}


def test_application_adapter_matches_direct_canonical_contract():
    actual = attach_canonical_preview(deepcopy(LEGACY), pig_snapshot=PIGS, pen_snapshot=PENS)
    expected = preview_application_typed({
        "effective_date": "2026-08-13",
        "rows": [
            {"identity": "PIG-OPAQUE-A", "weight_kg": 47.2, "moved_to_pen_id": "PEN-OPAQUE-D3", "condition_notes": ""},
            {"identity": "PIG-OPAQUE-B", "weight_kg": 118.0, "moved_to_pen_id": "PEN-OPAQUE-D3", "condition_notes": ""},
        ],
    }, pigs=PIGS, pens=PENS)
    assert actual["canonical_preview"] == expected
    assert actual["preview_digest"] == expected["preview_digest"]
    assert actual["confirmation_required"] is True
    assert actual["accepted_rows"] == LEGACY["accepted_rows"]


def test_optional_per_row_movement_and_unknowns_are_preserved():
    legacy = deepcopy(LEGACY)
    legacy["accepted_rows"][0]["moved_to_pen_id"] = ""
    legacy["accepted_rows"][0]["condition_notes"] = ""
    actual = attach_canonical_preview(legacy, pig_snapshot=PIGS, pen_snapshot=PENS)
    first, second = actual["canonical_preview"]["rows"]
    assert first["moved_to_pen_id"] == "Unknown"
    assert first["condition_notes"] == "Unknown"
    assert second["moved_to_pen_id"] == "PEN-OPAQUE-D3"


def test_movement_only_row_remains_explicit_without_calling_an_executor():
    legacy = deepcopy(LEGACY)
    legacy["accepted_count"] = 1
    legacy["accepted_rows"] = [{**legacy["accepted_rows"][0], "weight_kg": None, "action_type": "movement_only"}]
    actual = attach_canonical_preview(legacy, pig_snapshot=PIGS, pen_snapshot=PENS)
    assert actual["canonical_preview"]["rows"][0]["weight_kg"] == "Unknown"
    assert actual["canonical_preview"]["farm_writes"] == 0


def test_ambiguous_inactive_and_invalid_snapshot_evidence_fail_closed():
    ambiguous = attach_canonical_preview(deepcopy(LEGACY), pig_snapshot=PIGS + [{**PIGS[0], "pig_id": "PIG-OTHER", "tag_number": "PIG-OPAQUE-A"}], pen_snapshot=PENS)
    inactive_pigs = [{**PIGS[0], "status": "Sold"}, PIGS[1]]
    inactive = attach_canonical_preview(deepcopy(LEGACY), pig_snapshot=inactive_pigs, pen_snapshot=PENS)
    invalid_pen = attach_canonical_preview(deepcopy(LEGACY), pig_snapshot=PIGS, pen_snapshot=[])
    assert ambiguous["success"] is False and ambiguous["canonical_preview"]["status"] == "animal_identity_ambiguous"
    assert inactive["success"] is False and inactive["canonical_preview"]["status"] == "animal_not_active_on_farm"
    assert invalid_pen["success"] is False and invalid_pen["canonical_preview"]["status"] == "destination_pen_invalid"


def test_controller_wires_only_successful_preview_and_performs_no_execution():
    legacy = deepcopy(LEGACY)
    with patch.object(pig_weights_controller, "preflight_bulk_weight_entries", return_value=(legacy, 200)) as preflight, \
         patch.object(pig_weights_controller, "get_active_pigs") as extra_pig_read, \
         patch.object(pig_weights_controller, "get_pens") as extra_pen_read, \
         patch.object(pig_weights_controller, "save_bulk_weight_entries") as executor:
        result, status = pig_weights_controller.preview_bulk_weight_entries({"weight_date": "2026-08-13", "rows": []})
    assert status == 200 and result["canonical_preview"]["success"] is True
    preflight.assert_called_once()
    extra_pig_read.assert_not_called()
    extra_pen_read.assert_not_called()
    executor.assert_not_called()


def test_existing_save_controller_remains_direct_to_unchanged_executor():
    expected = ({"success": True, "batch_id": "BATCH-1"}, 201)
    with patch.object(pig_weights_controller, "save_bulk_weight_entries", return_value=expected) as executor, \
         patch("modules.pig_weights.pig_weights_controller.attach_canonical_preview") as adapter:
        assert pig_weights_controller.create_bulk_weight_entries({"rows": []}) == expected
    executor.assert_called_once_with({"rows": []})
    adapter.assert_not_called()


def test_failed_or_malformed_preflight_is_returned_without_adapter_or_effect():
    failed = {"ok": False, "success": False, "error": "validation_error", "accepted_rows": []}
    with patch.object(pig_weights_controller, "preflight_bulk_weight_entries", return_value=(failed, 400)), \
         patch("modules.pig_weights.pig_weights_controller.attach_canonical_preview") as adapter, \
         patch.object(pig_weights_controller, "save_bulk_weight_entries") as executor:
        result, status = pig_weights_controller.preview_bulk_weight_entries(None)
    assert (result, status) == (failed, 400)
    adapter.assert_not_called()
    executor.assert_not_called()
