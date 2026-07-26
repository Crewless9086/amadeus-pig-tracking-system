from datetime import datetime, timezone
import json

import pytest

from modules.sales.sam_owner_work_queue import (
    OwnerWorkEvidenceError,
    build_charlie_backlog_report,
    build_owner_work_observation,
    reconcile_human_backlog,
    record_owner_work_observation,
    run_daily_backlog_report,
    load_bounded_conversation_messages,
)


IDENTITY = {
    "account_id": 147387, "id": 2025, "contact_id": 699428938,
    "inbox_id": 96568, "custom_attributes": {"conversation_mode": "HUMAN"},
    "labels": ["sam_live_stock"], "channel": "Channel::Whatsapp",
}


def message(message_id, direction, timestamp, **extra):
    return {
        "id": message_id, "message_type": 0 if direction == "incoming" else 1,
        "created_at": timestamp, "private": False, **extra,
    }


def conversation(messages, **updates):
    return {**IDENTITY, "messages": messages, **updates}


def review(message_id=101):
    return {
        "review_event_id": "SAM-LIVE-REVIEW-TEST",
        "chatwoot_conversation_id": "2025",
        "chatwoot_message_id": str(message_id),
    }


ACTOR = "owner-admin:server-derived-test"


def test_orders_complete_unanswered_bundle_and_hashes_chronology():
    observed = build_owner_work_observation(
        conversation([
            message(102, "incoming", "2026-07-26T10:02:00Z"),
            message(100, "outgoing", "2026-07-26T10:00:00Z"),
            message(101, "incoming", "2026-07-26T10:01:00Z"),
        ]),
        review=review(), observed_at=datetime(2026, 7, 26, 11, tzinfo=timezone.utc),
        reconciliation_actor_id=ACTOR,
    )
    assert [row["message_id"] for row in observed["unanswered_inbound_bundle"]] == ["101", "102"]
    assert [row["sequence"] for row in observed["unanswered_inbound_bundle"]] == [1, 2]
    assert observed["classification"] == "WAITING_FOR_OWNER_REPLY"
    assert observed["missed_message_classification"] == "multiple_unanswered_inbounds"
    assert observed["actionable"] is True
    assert observed["contains_customer_content"] is False
    assert "content" not in json.dumps(observed["unanswered_inbound_bundle"])


def test_later_owner_reply_removes_item_from_actionable_state():
    observed = build_owner_work_observation(
        conversation([
            message(101, "incoming", "2026-07-26T10:01:00Z"),
            message(102, "outgoing", "2026-07-26T10:02:00Z"),
        ]), review=review(), reconciliation_actor_id=ACTOR,
    )
    assert observed["classification"] == "CUSTOMER_ALREADY_HANDLED"
    assert observed["missed_message_classification"] == "handled_by_later_public_owner_reply"
    assert observed["actionable"] is False
    assert observed["unanswered_count"] == 0


def test_newer_inbound_produces_new_sequence_identity_without_telegram_effect():
    first = build_owner_work_observation(
        conversation([message(101, "incoming", "2026-07-26T10:01:00Z")]),
        review=review(), reconciliation_actor_id=ACTOR,
    )
    second = build_owner_work_observation(
        conversation([
            message(101, "incoming", "2026-07-26T10:01:00Z"),
            message(102, "incoming", "2026-07-26T10:02:00Z"),
        ]), review=review(), reconciliation_actor_id=ACTOR,
    )
    assert first["work_item_id"] == second["work_item_id"]
    assert first["chronology_hash"] != second["chronology_hash"]
    assert first["work_event_id"] != second["work_event_id"]
    assert second["calls_telegram"] is False
    assert first["window_evidence_hash"] != second["window_evidence_hash"]


def test_repeated_same_chronology_reuses_work_observation_and_alert_identity():
    payload = conversation([
        message(101, "incoming", "2026-07-25T13:00:00Z"),
    ])
    first = build_owner_work_observation(
        payload, review=review(), reconciliation_actor_id=ACTOR,
        observed_at=datetime(2026, 7, 26, 12, tzinfo=timezone.utc),
    )
    second = build_owner_work_observation(
        payload, review=review(), reconciliation_actor_id=ACTOR,
        observed_at=datetime(2026, 7, 26, 12, 5, tzinfo=timezone.utc),
    )
    assert first["work_item_id"] == second["work_item_id"]
    assert first["work_event_id"] == second["work_event_id"]
    assert first["window_state"] == "approaching_expiry"
    assert first["prepared_window_alert"]["alert_event_id"] == second["prepared_window_alert"]["alert_event_id"]
    assert first["prepared_window_alert"]["delivery_enabled"] is False


def test_expiry_removes_reply_authority_and_records_missed_window_evidence():
    observed = build_owner_work_observation(
        conversation([message(101, "incoming", "2026-07-25T10:00:00Z")]),
        review=review(), reconciliation_actor_id=ACTOR,
        observed_at=datetime(2026, 7, 26, 12, tzinfo=timezone.utc),
    )
    assert observed["window_state"] == "expired"
    assert observed["reply_authority_state"] == "template_required"
    assert observed["ordinary_reply_allowed"] is False
    assert observed["send_reply_action_visible"] is False
    assert observed["actionable"] is False
    assert "provider_reply_window_expired" in observed["withheld_reasons"]
    assert observed["prepared_window_alert"]["alert_band"] == "missed_window"
    assert observed["prepared_window_alert"]["uses_template"] is False


def test_alert_identity_or_authority_tampering_fails_before_database(monkeypatch):
    observed = build_owner_work_observation(
        conversation([message(101, "incoming", "2026-07-25T13:00:00Z")]),
        review=review(), reconciliation_actor_id=ACTOR,
        observed_at=datetime(2026, 7, 26, 12, tzinfo=timezone.utc),
    )
    observed["prepared_window_alert"]["conversation_id"] = "wrong"
    result, status = record_owner_work_observation(observed, database_url="unused")
    assert status == 400
    assert result["status"] == "window_alert_identity_mismatch"
    observed["prepared_window_alert"]["conversation_id"] = observed["conversation_id"]
    observed["prepared_window_alert"]["delivery_enabled"] = True
    result, status = record_owner_work_observation(observed, database_url="unused")
    assert status == 400
    assert result["status"] == "window_alert_authority_forbidden"


@pytest.mark.parametrize(
    ("labels", "classification", "lane", "reason"),
    [
        (["payment"], "PROTECTED_ACTION_REQUIRED", "PROTECTED", "protected_work_requires_owner"),
        (["sam_meat"], "SPECIALIST_REVIEW_REQUIRED", "SPECIALIST", "specialist_work_separated"),
    ],
)
def test_protected_and_specialist_are_separated(labels, classification, lane, reason):
    observed = build_owner_work_observation(
        conversation([message(101, "incoming", "2026-07-26T10:01:00Z")], labels=labels),
        review=review(), reconciliation_actor_id=ACTOR,
    )
    assert observed["classification"] == classification
    assert observed["lane"] == lane
    assert reason in observed["withheld_reasons"]


def test_activity_and_private_rows_do_not_enter_public_bundle():
    observed = build_owner_work_observation(
        conversation([
            {"id": 90, "message_type": 2, "created_at": "2026-07-26T09:59:00Z"},
            message(101, "incoming", "2026-07-26T10:01:00Z"),
            message(102, "incoming", "2026-07-26T10:02:00Z", private=True),
        ]), review=review(), reconciliation_actor_id=ACTOR,
    )
    assert [row["message_id"] for row in observed["unanswered_inbound_bundle"]] == ["101"]


@pytest.mark.parametrize("key", ["contact_id", "inbox_id", "account_id"])
def test_missing_exact_identity_fails_closed(key):
    with pytest.raises(OwnerWorkEvidenceError, match="identity_missing"):
        build_owner_work_observation(
            conversation(
                [message(101, "incoming", "2026-07-26T10:01:00Z")], **{key: None}
            ), review=review(), reconciliation_actor_id=ACTOR,
        )


def test_non_human_review_conflict_and_bad_time_fail_closed():
    observed = build_owner_work_observation(
        conversation(
            [message(101, "incoming", "2026-07-26T10:01:00Z")],
            custom_attributes={"conversation_mode": "AUTO_GENERAL"},
        ), review=review(), reconciliation_actor_id=ACTOR,
    )
    assert observed["actionable"] is False
    with pytest.raises(OwnerWorkEvidenceError, match="review_conversation_mismatch"):
        build_owner_work_observation(
            conversation([message(101, "incoming", "2026-07-26T10:01:00Z")]),
            review={**review(), "chatwoot_conversation_id": "999"},
            reconciliation_actor_id=ACTOR,
        )
    with pytest.raises(OwnerWorkEvidenceError, match="timestamp_invalid"):
        build_owner_work_observation(
            conversation([message(101, "incoming", "yesterday")]), review=review(),
            reconciliation_actor_id=ACTOR,
        )


def test_reconciliation_is_bounded_and_replay_safe_through_recorder():
    recorded = {}

    def recorder(event):
        created = event["work_event_id"] not in recorded
        recorded[event["work_event_id"]] = event
        return {"success": True, "status": "recorded", "created": created}, 201 if created else 200

    rows = [conversation([message(101, "incoming", "2026-07-26T10:01:00Z")])]
    first, status1 = reconcile_human_backlog(
        rows, review_by_conversation={"2025": review()}, recorder=recorder,
        reconciliation_actor_id=ACTOR,
    )
    second, status2 = reconcile_human_backlog(
        rows, review_by_conversation={"2025": review()}, recorder=recorder,
        reconciliation_actor_id=ACTOR,
    )
    assert status1 == status2 == 200
    assert first["created_count"] == 1
    assert second["created_count"] == 0
    assert len(recorded) == 1


def test_charlie_report_is_sanitized_and_has_no_authority():
    item = build_owner_work_observation(
        conversation([message(101, "incoming", "2026-07-26T10:01:00Z")]),
        review=review(), reconciliation_actor_id=ACTOR,
    )
    report = build_charlie_backlog_report([item], report_date="2026-07-26")
    assert report["classification_counts"] == {"WAITING_FOR_OWNER_REPLY": 1}
    assert report["contains_customer_content"] is False
    assert report["sends_customer_message"] is False
    assert report["mutates_business_state"] is False
    assert report["window_state_counts"] == {"open": 1}
    assert report["alert_band_counts"] == {"none": 1}


def test_daily_report_reuses_current_queue_and_persists_idempotent_snapshot(monkeypatch):
    item = build_owner_work_observation(
        conversation([message(101, "incoming", "2026-07-26T10:01:00Z")]),
        review=review(), reconciliation_actor_id=ACTOR,
    )
    monkeypatch.setattr(
        "modules.sales.sam_owner_work_queue.list_owner_work_items",
        lambda **kwargs: ({"success": True, "items": [item]}, 200),
    )
    seen = []
    monkeypatch.setattr(
        "modules.sales.sam_owner_work_queue.record_charlie_backlog_report",
        lambda report, **kwargs: (
            seen.append(report) or {
                "success": True, "status": "owner_backlog_report_recorded", "created": True
            },
            201,
        ),
    )
    result, status = run_daily_backlog_report(report_date="2026-07-26")
    assert status == 201
    assert result["created"] is True
    assert len(seen) == 1
    assert seen[0]["contains_customer_content"] is False


def test_bounded_message_reader_handles_canonical_envelope_without_content_persistence():
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self):
            return json.dumps({
                "payload": [
                    message(101, "incoming", "2026-07-26T10:01:00Z", content="private text")
                ]
            }).encode()

    result, status = load_bounded_conversation_messages(
        "2025",
        {
            "CHATWOOT_BASE_URL": "https://chatwoot.example",
            "CHATWOOT_ACCOUNT_ID": "147387",
            "CHATWOOT_API_ACCESS_TOKEN": "test-token",
        },
        opener=lambda request, timeout: Response(),
    )
    assert status == 200
    assert result["evidence_complete"] is True
    assert result["messages"][0]["id"] == 101
