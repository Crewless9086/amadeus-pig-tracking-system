from datetime import datetime, timezone
import json
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.error import URLError

import pytest

from modules.sales.sam_live_stock_runtime import (
    load_chatwoot_conversation_identity,
    parse_chatwoot_inbound,
    resolve_sam_general_inbound_identity,
)
from modules.sales.sam_manager_summary import build_sam_manager_summary
from modules.sales.sam_sales_autonomy import bind_authoritative_conversation_evidence


NOW = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)


class Response:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


class RawResponse(Response):
    def __init__(self, body):
        self.body = body


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
            "account_id": 147387,
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
    "conversation_id,inbox_id",
    [("2101", "96568"), ("2202", "97569")],
)
def test_authoritative_conversation_recovers_provider_from_exact_inbox_endpoint(
    conversation_id, inbox_id,
):
    responses = iter([
        Response({
            "id": conversation_id,
            "account_id": 147387,
            "inbox_id": inbox_id,
            "can_reply": True,
            "meta": {"sender": {"id": 699428938}},
            "last_non_activity_message": {"id": 777634477, "message_type": 0},
        }),
        Response({
            "id": inbox_id,
            "channel_type": "Channel::Whatsapp",
            "provider": "whatsapp_cloud",
        }),
    ])
    with patch(
        "modules.sales.sam_live_stock_runtime.urllib_request.urlopen",
        side_effect=lambda *_args, **_kwargs: next(responses),
    ):
        result = load_chatwoot_conversation_identity(
            conversation_id,
            {
                "CHATWOOT_BASE_URL": "https://chatwoot.example",
                "CHATWOOT_ACCOUNT_ID": "147387",
                "CHATWOOT_API_ACCESS_TOKEN": "secret",
            },
        )
    assert result["provider_identity_class"] == "genuine_whatsapp"
    assert result["provider_identity_status"] == "chatwoot_inbox_provider_identity_loaded"
    assert result["inbox_id"] == inbox_id


def test_authoritative_inbox_identity_conflict_fails_provider_closed():
    responses = iter([
        Response({
            "id": 2101,
            "account_id": 147387,
            "inbox_id": 96568,
            "meta": {"sender": {"id": 699428938}},
        }),
        Response({"id": 99999, "channel_type": "Channel::Whatsapp"}),
    ])
    with patch(
        "modules.sales.sam_live_stock_runtime.urllib_request.urlopen",
        side_effect=lambda *_args, **_kwargs: next(responses),
    ):
        result = load_chatwoot_conversation_identity(
            "2101",
            {
                "CHATWOOT_BASE_URL": "https://chatwoot.example",
                "CHATWOOT_ACCOUNT_ID": "147387",
                "CHATWOOT_API_ACCESS_TOKEN": "secret",
            },
        )
    assert result["provider_identity_class"] == ""
    assert result["provider_identity_status"] == "chatwoot_inbox_identity_conflict"


@pytest.mark.parametrize(
    "inbox_payload,status",
    [
        ({"channel_type": "Channel::Whatsapp", "provider": "whatsapp_cloud"},
         "chatwoot_inbox_identity_unavailable"),
        ({"id": 96568, "channel_type": "Channel::Whatsapp"},
         "chatwoot_inbox_provider_identity_unavailable"),
        ({"id": 96568, "provider": "whatsapp_cloud"},
         "chatwoot_inbox_provider_identity_unavailable"),
        ({"id": 96568, "channel_type": "Channel::FacebookPage", "provider": "facebook"},
         "chatwoot_inbox_provider_identity_loaded"),
        ({"id": 96568, "channel_type": "Channel::Whatsapp", "provider": "other"},
         "chatwoot_inbox_provider_identity_conflict"),
    ],
)
def test_inbox_record_requires_exact_identity_channel_and_cloud_provider(
    inbox_payload, status,
):
    responses = iter([
        Response({"id": 2101, "account_id": 147387, "inbox_id": 96568, "meta": {"sender": {"id": 699428938}}}),
        Response(inbox_payload),
    ])
    with patch(
        "modules.sales.sam_live_stock_runtime.urllib_request.urlopen",
        side_effect=lambda *_args, **_kwargs: next(responses),
    ):
        result = load_chatwoot_conversation_identity(
            "2101",
            {
                "CHATWOOT_BASE_URL": "https://chatwoot.example",
                "CHATWOOT_ACCOUNT_ID": "147387",
                "CHATWOOT_API_ACCESS_TOKEN": "secret",
            },
        )
    assert result["provider_identity_class"] != "genuine_whatsapp"
    assert result["provider_identity_status"] == status


def test_missing_inbox_record_fails_provider_closed():
    responses = iter([
        Response({"id": 2101, "account_id": 147387, "inbox_id": 96568, "meta": {"sender": {"id": 699428938}}}),
        HTTPError("https://chatwoot.example/inboxes/96568", 404, "missing", {}, None),
    ])

    def urlopen(*_args, **_kwargs):
        value = next(responses)
        if isinstance(value, Exception):
            raise value
        return value

    with patch(
        "modules.sales.sam_live_stock_runtime.urllib_request.urlopen",
        side_effect=urlopen,
    ):
        result = load_chatwoot_conversation_identity(
            "2101",
            {
                "CHATWOOT_BASE_URL": "https://chatwoot.example",
                "CHATWOOT_ACCOUNT_ID": "147387",
                "CHATWOOT_API_ACCESS_TOKEN": "secret",
            },
        )
    assert result["provider_identity_class"] == ""
    assert result["provider_identity_status"] == "chatwoot_inbox_identity_http_404"


def test_conversation_provider_class_avoids_inbox_lookup():
    with patch(
        "modules.sales.sam_live_stock_runtime.urllib_request.urlopen",
        return_value=Response({
            "id": 2101,
            "account_id": 147387,
            "inbox_id": 96568,
            "channel_type": "Channel::Whatsapp",
            "meta": {"sender": {"id": 699428938}},
        }),
    ) as urlopen:
        result = load_chatwoot_conversation_identity(
            "2101",
            {
                "CHATWOOT_BASE_URL": "https://chatwoot.example",
                "CHATWOOT_ACCOUNT_ID": "147387",
                "CHATWOOT_API_ACCESS_TOKEN": "secret",
            },
        )
    assert urlopen.call_count == 1
    assert result["provider_identity_class"] == "genuine_whatsapp"
    assert result["provider_identity_status"] == "conversation_provider_identity_loaded"


@pytest.mark.parametrize(
    "failure,status",
    [
        (RawResponse(b"{malformed"), "chatwoot_inbox_identity_read_failed"),
        (URLError("unavailable"), "chatwoot_inbox_identity_read_failed"),
    ],
)
def test_malformed_or_unavailable_inbox_record_fails_downstream_closed(failure, status):
    values = iter([
        Response({
            "id": 2101, "account_id": 147387, "inbox_id": 96568,
            "meta": {"sender": {"id": 699428938}},
        }),
        failure,
    ])

    def urlopen(*_args, **_kwargs):
        value = next(values)
        if isinstance(value, Exception):
            raise value
        return value

    with patch(
        "modules.sales.sam_live_stock_runtime.urllib_request.urlopen",
        side_effect=urlopen,
    ):
        identity = load_chatwoot_conversation_identity(
            "2101",
            {
                "CHATWOOT_BASE_URL": "https://chatwoot.example",
                "CHATWOOT_ACCOUNT_ID": "147387",
                "CHATWOOT_API_ACCESS_TOKEN": "secret",
            },
        )
    assert identity["provider_identity_class"] == ""
    assert identity["provider_identity_status"] == status
    inbound = resolved(payload())
    inbound["channel"] = "chatwoot"
    inbound["identity_provenance"]["provider_identity_class"] = identity["provider_identity_class"]
    bound = bind_authoritative_conversation_evidence(inbound, chronology(), now=NOW)
    assert bound["chronology_current"] is False


@pytest.mark.parametrize("account_value", ["OTHER", None])
def test_conversation_account_must_match_authenticated_account(account_value):
    conversation = {
        "id": 2101,
        "inbox_id": 96568,
        "meta": {"sender": {"id": 699428938}},
    }
    if account_value is not None:
        conversation["account_id"] = account_value
    with patch(
        "modules.sales.sam_live_stock_runtime.urllib_request.urlopen",
        return_value=Response(conversation),
    ) as urlopen:
        result = load_chatwoot_conversation_identity(
            "2101",
            {
                "CHATWOOT_BASE_URL": "https://chatwoot.example",
                "CHATWOOT_ACCOUNT_ID": "147387",
                "CHATWOOT_API_ACCESS_TOKEN": "secret",
            },
        )
    assert urlopen.call_count == 1
    assert result["provider_identity_class"] == ""
    assert result["account_identity_status"] in {
        "account_identity_conflict", "account_identity_unavailable",
    }


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
