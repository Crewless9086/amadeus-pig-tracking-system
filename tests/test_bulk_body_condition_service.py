from datetime import datetime, timezone
from unittest.mock import patch

from modules.pig_weights.bulk_body_condition_service import record_body_condition_batch

NOW = datetime(2026, 8, 24, 10, tzinfo=timezone.utc)


def payload(rows):
    return {"draft_id": "DRAFT-1", "observed_date": "2026-08-24", "rows": rows}


def test_blank_bcs_has_zero_observation_effect():
    with patch("modules.pig_weights.bulk_body_condition_service.record_observation") as writer:
        result, status = record_body_condition_batch(payload([
            {"pig_id": "P1", "body_condition_score": ""},
        ]), actor_id="owner", now=NOW)
    assert status == 200
    assert result["recorded_count"] == 0
    writer.assert_not_called()


def test_bcs_only_rows_record_separate_events_without_heat_fields():
    with patch("modules.pig_weights.bulk_body_condition_service.list_observations",
               return_value=({"history": []}, 200)), patch(
        "modules.pig_weights.bulk_body_condition_service.record_observation",
        side_effect=[({"status": "observation_recorded", "observation_event_id": "E1"}, 201),
                     ({"status": "observation_recorded", "observation_event_id": "E2"}, 201)],
    ) as writer:
        result, status = record_body_condition_batch(payload([
            {"pig_id": "P2", "body_condition_score": "3.5"},
            {"pig_id": "P1", "body_condition_score": "2"},
        ]), actor_id="manager", now=NOW)
    assert status == 201
    assert result["recorded_count"] == 2
    assert result["heat_fields_recorded"] is False
    calls = writer.call_args_list
    assert [call.args[0]["pig_id"] for call in calls] == ["P1", "P2"]
    assert all("standing_heat" not in call.args[0] for call in calls)


def test_correction_binds_latest_unsuperseded_body_condition():
    history = {"history": [
        {"observation_event_id": "NEW", "superseded": False,
         "measurements": {"body_condition_score": 2}},
        {"observation_event_id": "OLD", "superseded": True,
         "measurements": {"body_condition_score": 1}},
    ]}
    with patch("modules.pig_weights.bulk_body_condition_service.list_observations",
               return_value=(history, 200)), patch(
        "modules.pig_weights.bulk_body_condition_service.record_observation",
        return_value=({"status": "observation_recorded", "observation_event_id": "FIX"}, 201),
    ) as writer:
        result, status = record_body_condition_batch(payload([
            {"pig_id": "P1", "body_condition_score": 3},
        ]), actor_id="owner", now=NOW)
    assert status == 201
    assert writer.call_args.args[0]["supersedes_observation_event_id"] == "NEW"
    assert result["events"][0]["supersedes_observation_event_id"] == "NEW"


def test_replay_uses_stable_batch_and_pig_identity():
    with patch("modules.pig_weights.bulk_body_condition_service.list_observations",
               return_value=({"history": []}, 200)), patch(
        "modules.pig_weights.bulk_body_condition_service.record_observation",
        return_value=({"status": "observation_replayed_withheld", "observation_event_id": "E1"}, 200),
    ) as writer:
        result, status = record_body_condition_batch(payload([
            {"pig_id": "P1", "body_condition_score": 3},
        ]), actor_id="owner", now=NOW)
    assert status == 200
    assert result["replayed_count"] == 1
    assert writer.call_args.args[0]["idempotency_key"] == "bulk-bcs:DRAFT-1:P1"


def test_invalid_or_duplicate_selection_fails_before_write():
    for rows in ([{"pig_id": "P1", "body_condition_score": 6}], [
        {"pig_id": "P1", "body_condition_score": 2},
        {"pig_id": "P1", "body_condition_score": 3},
    ]):
        with patch("modules.pig_weights.bulk_body_condition_service.record_observation") as writer:
            result, status = record_body_condition_batch(payload(rows), actor_id="owner", now=NOW)
        assert status == 400
        writer.assert_not_called()
