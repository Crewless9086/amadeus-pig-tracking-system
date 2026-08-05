from datetime import datetime, timezone

import pytest

from modules.sales.sam_live_stock_runtime import (
    parse_chatwoot_inbound,
    resolve_sam_general_inbound_identity,
)
from modules.sales.sam_manager_summary import build_sam_manager_summary
from modules.sales.sam_sales_autonomy import bind_authoritative_conversation_evidence


NOW = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)


def payload(conversation_id="2101", message_id="777634477", **overrides):
    value = {
        "event": "message_created",
        "message_type": "incoming",
        "id": message_id,
        "created_at": "2026-08-05T07:12:00Z",
        "content": "I am looking for pigs",
        "account": {"id": "147387"},
        "conversation": {
            "id": conversation_id,
            "account_id": "147387",
            "inbox": {"id": "96568", "channel_type": "Channel::Whatsapp"},
        },
        "sender": {"id": "699428938", "name": "Untrusted display label"},
    }
    value.update(overrides)
    return value


def chronology(message_id="777634477", created_at="2026-08-05T07:12:00Z"):
    return [{
        "id": message_id,
        "message_type": 0,
        "private": False,
        "created_at": created_at,
        "attachments": [],
    }]


def resolved(value):
    parsed = parse_chatwoot_inbound(value)
    return resolve_sam_general_inbound_identity(parsed, value, environ={})


@pytest.mark.parametrize("conversation_id,message_id", [("2101", "777634477"), ("2202", "888000002")])
def test_authenticated_whatsapp_shapes_bind_multiple_conversations(conversation_id, message_id):
    inbound = resolved(payload(conversation_id, message_id))
    result = bind_authoritative_conversation_evidence(
        inbound, chronology(message_id), now=NOW,
    )
    assert inbound["identity_provenance"]["provider_identity_class"] == "genuine_whatsapp"
    assert result["chronology_current"] is True
    assert result["reply_window_evidence"]["provider_identity_class"] == "genuine_whatsapp"


def test_supported_top_level_inbox_shape_recovers_provider_without_display_name():
    value = payload()
    value["inbox"] = value["conversation"].pop("inbox")
    value["conversation"]["inbox_id"] = "96568"
    value["sender"]["name"] = "🐷 BUY NOW 🐷"
    inbound = resolved(value)
    assert inbound["identity_provenance"]["provider_identity_class"] == "genuine_whatsapp"
    assert inbound["inbox_id"] == "96568"


def test_missing_webhook_provider_recovers_only_from_exact_authoritative_record():
    value = payload()
    value["conversation"]["inbox"].pop("channel_type")
    parsed = parse_chatwoot_inbound(value)
    inbound = resolve_sam_general_inbound_identity(
        parsed,
        value,
        environ={},
        conversation_identity_loader=lambda *_args: {
            "success": True,
            "status": "loaded",
            "account_id": "147387",
            "conversation_id": "2101",
            "contact_id": "699428938",
            "inbox_id": "96568",
            "provider_identity_class": "genuine_whatsapp",
        },
    )
    result = bind_authoritative_conversation_evidence(inbound, chronology(), now=NOW)
    assert inbound["identity_provenance"]["provider_identity_class"] == "genuine_whatsapp"
    assert result["chronology_current"] is True


@pytest.mark.parametrize(
    "mutate,reason",
    [
        (lambda value: value["conversation"]["inbox"].pop("channel_type"), "whatsapp_provider_identity_unavailable"),
        (lambda value: value.update({"channel": "Channel::FacebookPage"}), "whatsapp_provider_identity_unavailable"),
    ],
)
def test_missing_conflicting_or_non_whatsapp_provider_fails_only_inbound(mutate, reason):
    value = payload()
    mutate(value)
    inbound = resolved(value)
    result = bind_authoritative_conversation_evidence(inbound, chronology(), now=NOW)
    assert result["chronology_current"] is False
    assert result["reply_window_evidence"]["reason"] == reason


def test_provider_timestamp_staleness_and_cross_tenant_identity_fail_closed():
    inbound = resolved(payload())
    stale = bind_authoritative_conversation_evidence(
        inbound,
        chronology(),
        provider_evidence={
            "provider_identity_class": "genuine_whatsapp",
            "identity_binding": {
                "account_id": "147387",
                "conversation_id": "2101",
                "contact_id": "699428938",
                "inbox_id": "96568",
            },
            "latest_inbound_message_id": "777634477",
            "latest_inbound_at_utc": "2026-08-05T06:00:00Z",
        },
        now=NOW,
    )
    assert stale["reply_window_evidence"]["reason"] == "provider_latest_inbound_timestamp_conflict"

    cross_tenant = dict(inbound)
    cross_tenant["account_id"] = "OTHER-ACCOUNT"
    result = bind_authoritative_conversation_evidence(cross_tenant, chronology(), now=NOW)
    assert result["reply_window_evidence"]["reason"] == "provider_account_id_conflict"


@pytest.mark.parametrize(
    "key,bad_value",
    [
        ("account_id", "OTHER-ACCOUNT"),
        ("conversation_id", "OTHER-CONVERSATION"),
        ("contact_id", "OTHER-CONTACT"),
        ("inbox_id", "OTHER-INBOX"),
    ],
)
def test_explicit_provider_evidence_requires_exact_four_part_binding(key, bad_value):
    inbound = resolved(payload())
    binding = {
        "account_id": "147387",
        "conversation_id": "2101",
        "contact_id": "699428938",
        "inbox_id": "96568",
    }
    binding[key] = bad_value
    result = bind_authoritative_conversation_evidence(
        inbound,
        chronology(),
        provider_evidence={
            "provider_identity_class": "genuine_whatsapp",
            "identity_binding": binding,
            "latest_inbound_message_id": "777634477",
        },
        now=NOW,
    )
    assert result["chronology_current"] is False
    assert result["reply_window_evidence"]["reason"] == f"provider_{key}_conflict"


def test_explicit_provider_evidence_without_binding_is_unavailable():
    result = bind_authoritative_conversation_evidence(
        resolved(payload()),
        chronology(),
        provider_evidence={"provider_identity_class": "genuine_whatsapp"},
        now=NOW,
    )
    assert result["chronology_current"] is False
    assert result["reply_window_evidence"]["reason"] == "provider_account_id_unbound"


def test_cross_inbox_binding_conflict_fails_closed():
    inbound = resolved(payload())
    inbound["inbox_id"] = "OTHER-INBOX"
    result = bind_authoritative_conversation_evidence(inbound, chronology(), now=NOW)
    assert result["chronology_current"] is False
    assert result["reply_window_evidence"]["reason"] == "provider_inbox_id_conflict"


@pytest.mark.parametrize(
    "rows",
    [
        chronology("OLDER"),
        chronology() + [{
            "id": "OUT-LATER", "message_type": 1, "private": False,
            "created_at": "2026-08-05T07:20:00Z", "attachments": [],
        }],
        chronology(created_at="2026-08-03T07:12:00Z"),
    ],
)
def test_replay_changed_chronology_and_stale_window_are_not_eligible(rows):
    result = bind_authoritative_conversation_evidence(resolved(payload()), rows, now=NOW)
    assert result["chronology_current"] is False


def test_identity_failure_remains_visible_in_compact_manager_summary():
    failed = bind_authoritative_conversation_evidence(
        resolved(payload()),
        chronology(),
        provider_evidence={"provider_identity_class": "genuine_whatsapp"},
        now=NOW,
    )
    summary = build_sam_manager_summary(
        [],
        period_started_at_utc="2026-08-05T00:00:00+00:00",
        observed_at_utc="2026-08-05T08:00:00+00:00",
        reply_window_evaluations=[failed["reply_window_evidence"]],
    )
    assert summary["coverage_exceptions"] == [{
        "exception_type": "whatsapp_provider_identity_unavailable",
        "count": 1,
        "systemic": False,
    }]
    assert summary["contains_individual_messages"] is False


def test_manager_summary_rejects_customer_text_in_exception_type():
    with pytest.raises(ValueError, match="coverage_exception_type"):
        build_sam_manager_summary(
            [],
            period_started_at_utc="2026-08-05T00:00:00+00:00",
            coverage_exceptions=[{
                "exception_type": "Call Customer +27820000000 about pigs",
                "systemic": False,
            }],
        )
