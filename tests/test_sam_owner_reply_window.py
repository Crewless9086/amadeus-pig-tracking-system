from datetime import datetime, timedelta, timezone
import json

import pytest

from modules.sales.sam_owner_reply_window import (
    ReplyWindowEvidenceError,
    evaluate_reply_window,
    prepare_window_alert,
    thresholds,
)


NOW = datetime(2026, 7, 26, 12, tzinfo=timezone.utc)
IDENTITY = {
    "account_id": "147387",
    "conversation_id": "2025",
    "contact_id": "699428938",
    "inbox_id": "96568",
    "channel": "Channel::Whatsapp",
}


def incoming(message_id="101", hours_ago=1, **extra):
    return {
        "id": message_id,
        "message_type": 0,
        "private": False,
        "created_at": (NOW - timedelta(hours=hours_ago)).isoformat(),
        **extra,
    }


def outgoing(message_id="100", hours_ago=2):
    return {
        "id": message_id,
        "message_type": 1,
        "private": False,
        "created_at": (NOW - timedelta(hours=hours_ago)).isoformat(),
    }


def evaluate(messages, **kwargs):
    return evaluate_reply_window(
        messages,
        conversation_identity=IDENTITY,
        now=NOW,
        environ={},
        **kwargs,
    )


def test_open_window_preserves_utc_and_displays_johannesburg():
    result = evaluate([incoming(hours_ago=1)])
    assert result["window_state"] == "open"
    assert result["reply_authority_state"] == "ordinary_reply_allowed"
    assert result["ordinary_reply_allowed"] is True
    assert result["send_reply_action_visible"] is True
    assert result["remaining_seconds"] == 23 * 3600
    assert result["expires_at_utc"] == "2026-07-27T11:00:00+00:00"
    assert result["expires_at_johannesburg"] == "2026-07-27T13:00:00+02:00"


@pytest.mark.parametrize(
    ("hours_ago", "band"),
    [(19, "warning"), (23, "urgent")],
)
def test_approaching_expiry_threshold_bands(hours_ago, band):
    result = evaluate([incoming(hours_ago=hours_ago)])
    assert result["window_state"] == "approaching_expiry"
    assert result["alert_band"] == band
    assert result["ordinary_reply_allowed"] is True


def test_expired_removes_ordinary_reply_and_requires_template_without_enabling_it():
    result = evaluate([incoming(hours_ago=25)])
    assert result["window_state"] == "expired"
    assert result["reply_authority_state"] == "template_required"
    assert result["template_required"] is True
    assert result["ordinary_reply_allowed"] is False
    assert result["send_reply_action_visible"] is False
    assert result["uses_template"] is False
    assert result["alert_band"] == "missed_window"


def test_unavailable_provider_identity_fails_closed():
    result = evaluate_reply_window(
        [incoming()],
        conversation_identity={key: value for key, value in IDENTITY.items() if key != "channel"},
        now=NOW,
        environ={},
    )
    assert result["window_state"] == "unavailable"
    assert result["ordinary_reply_allowed"] is False
    assert result["send_reply_action_visible"] is False


def test_handled_or_missing_inbound_is_not_applicable():
    result = evaluate([incoming(hours_ago=2), outgoing(hours_ago=1)])
    assert result["window_state"] == "not_applicable"
    assert result["reason"] == "authoritative_later_owner_reply"
    result = evaluate([outgoing()])
    assert result["window_state"] == "not_applicable"
    assert result["reason"] == "no_public_inbound"


def test_second_inbound_recalculates_window_from_new_exact_identity():
    first = evaluate([incoming("101", hours_ago=10)])
    second = evaluate([
        incoming("101", hours_ago=10),
        incoming("102", hours_ago=1),
    ])
    assert first["latest_inbound_message_id"] == "101"
    assert second["latest_inbound_message_id"] == "102"
    assert second["expires_at_utc"] != first["expires_at_utc"]
    assert second["window_evidence_hash"] != first["window_evidence_hash"]


def test_provider_identity_or_timestamp_conflict_is_unavailable():
    result = evaluate(
        [incoming()],
        provider_evidence={
            "provider_identity_class": "genuine_whatsapp",
            "latest_inbound_message_id": "999",
        },
    )
    assert result["window_state"] == "unavailable"
    assert result["reason"] == "provider_latest_inbound_identity_conflict"


def test_exact_whatsapp_message_accepts_webhook_fractional_second_timestamp():
    result = evaluate(
        [incoming()],
        provider_evidence={
            "provider_identity_class": "genuine_whatsapp",
            "latest_inbound_message_id": "101",
            "latest_inbound_at_utc": "2026-07-26T11:00:00.897Z",
        },
    )
    assert result["window_state"] == "open"
    assert result["reply_authority_state"] == "ordinary_reply_allowed"


def test_webwidget_exact_current_inbound_has_bounded_channel_authority():
    result = evaluate_reply_window(
        [incoming()],
        conversation_identity={**IDENTITY, "channel": "Channel::WebWidget"},
        provider_evidence={
            "provider_identity_class": "genuine_webwidget",
            "latest_inbound_message_id": "101",
        },
        now=NOW,
        environ={},
    )
    assert result["provider_identity_class"] == "genuine_webwidget"
    assert result["window_state"] == "not_applicable"
    assert result["reply_authority_state"] == "ordinary_reply_allowed"
    assert result["ordinary_reply_allowed"] is True


def test_suspicious_link_evidence_withholds_without_content():
    result = evaluate([incoming()], suspicious_link_evidence=True)
    encoded = json.dumps(result, sort_keys=True)
    assert result["reply_authority_state"] == "customer_reply_prohibited"
    assert result["suspicious_link_withheld"] is True
    assert result["send_reply_action_visible"] is False
    assert "http" not in encoded.lower()
    assert result["contains_customer_content"] is False


def test_attachment_presence_withholds_without_persisting_attachment():
    result = evaluate([incoming(attachments=[{"data_url": "secret"}])])
    assert result["reply_authority_state"] == "customer_reply_prohibited"
    assert result["attachment_withheld"] is True
    assert "secret" not in json.dumps(result)


def test_alert_identity_is_stable_and_delivery_is_disabled():
    evaluation = evaluate([incoming(hours_ago=23)])
    first = prepare_window_alert("WORK-1", "OBS-1", evaluation, prepared_at=NOW)
    second = prepare_window_alert(
        "WORK-1", "OBS-1", evaluation, prepared_at=NOW + timedelta(minutes=1)
    )
    assert first["alert_event_id"] == second["alert_event_id"]
    assert first["alert_deduplication_hash"] == second["alert_deduplication_hash"]
    assert first["delivery_enabled"] is False
    assert first["delivered"] is False
    assert first["contains_customer_content"] is False


def test_no_alert_is_prepared_for_healthy_open_window():
    assert prepare_window_alert("WORK-1", "OBS-1", evaluate([incoming()])) is None


def test_thresholds_default_and_fail_closed_configuration():
    assert thresholds({}) == (6, 2)
    assert thresholds({
        "SAM_OWNER_INBOX_WINDOW_WARNING_HOURS": "8",
        "SAM_OWNER_INBOX_WINDOW_URGENT_HOURS": "3",
    }) == (8, 3)
    with pytest.raises(ReplyWindowEvidenceError):
        thresholds({
            "SAM_OWNER_INBOX_WINDOW_WARNING_HOURS": "2",
            "SAM_OWNER_INBOX_WINDOW_URGENT_HOURS": "6",
        })
