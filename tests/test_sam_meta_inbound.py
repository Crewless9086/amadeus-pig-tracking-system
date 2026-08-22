from datetime import datetime, timezone
from unittest.mock import patch

from modules.sales.sam_live_stock_runtime import (
    build_sam_front_door_adapter_packet,
    handle_sam_live_stock_chatwoot_inbound,
    parse_chatwoot_inbound,
)
from modules.sales.sam_meta_inbound import evaluate_meta_inbound_attribution
from modules.sales.sam_owner_reply_window import evaluate_reply_window
from modules.beacon.publication_attribution import (
    resolve_canonical_meta_publication_binding,
)

NOW = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)


def canonical_binding(**changes):
    binding = {
        "attribution_identity": "BEACON-CAMPAIGN-ABC",
        "post_id": "PAGE-1_POST-7",
        "target_page_id": "PAGE-1",
        "publication_time": "2026-08-19T10:00:00+00:00",
        "sam_boundary": "No quote, reservation, order or payment.",
        "post_text": "Molly and her piglets are enjoying a quiet morning.",
        "publish_packet_id": "BEACON-PACKET-1",
        "publication_binding_id": "BEACON-CONSUMER-1",
        "binding_source": "protected_publication_consumer",
    }
    binding.update(changes)
    return binding


def resolution(**changes):
    binding = canonical_binding(**changes)
    return {
        "success": True,
        "status": "resolved",
        "reason": "canonical_beacon_publication_binding_resolved",
        "binding": binding,
    }


def parse_bound(row=None, resolved=None):
    resolved = resolution() if resolved is None else resolved
    return parse_chatwoot_inbound(
        row or payload(),
        environ={"DATABASE_URL": "postgresql://read-only", "BEACON_FACEBOOK_PAGE_ID": "PAGE-1"},
        meta_publication_resolver=lambda *_args, **_kwargs: resolved,
    )


def payload(**changes):
    row = {
        "event": "message_created", "message_type": 0, "id": "META-MSG-1",
        "content": "Hi, can you tell me what pig sizes you sell?",
        "created_at": "2026-08-20T11:00:00Z", "account": {"id": "ACCOUNT-1"},
        "conversation": {"id": "CONV-1", "account_id": "ACCOUNT-1",
            "inbox": {"id": "INBOX-1", "channel_type": "Channel::FacebookPage"}},
        "sender": {"id": "PSID-1", "name": "Customer"},
        "content_attributes": {"referral": {
            "source_id": "PAGE-1_POST-7", "target_page_id": "PAGE-1",
            "attribution_identity": "BEACON-CAMPAIGN-ABC",
            "sam_boundary": "No quote, reservation, order or payment.",
            "publication_time": "2026-08-19T10:00:00Z"}},
    }
    row.update(changes)
    return row


def test_genuine_shaped_meta_inbound_preserves_customer_channel_post_and_campaign():
    inbound = parse_bound()
    assert inbound["processable"] is True
    assert inbound["channel"] == "chatwoot_facebook"
    assert inbound["contact_id"] == "PSID-1"
    assert inbound["identity_provenance"]["provider_identity_class"] == "genuine_meta"
    assert inbound["meta_attribution"]["campaign_id"] == "BEACON-CAMPAIGN-ABC"
    assert inbound["meta_attribution"]["post_id"] == "PAGE-1_POST-7"


def test_attribution_present_absent_stale_and_wrong_page_fail_independently():
    exact_resolution = resolution()
    exact = evaluate_meta_inbound_attribution(
        payload(), expected_binding=exact_resolution["binding"],
        binding_resolution=exact_resolution, now=NOW,
    )
    assert exact["status"] == "attributed"
    missing = payload(content_attributes={"referral": {"source_id": "PAGE-1_POST-7", "target_page_id": "PAGE-1"}})
    assert evaluate_meta_inbound_attribution(
        missing, expected_binding=exact_resolution["binding"],
        binding_resolution=exact_resolution, now=NOW,
    )["status"] == "absent"
    stale = payload()
    stale["content_attributes"]["referral"]["publication_time"] = "2026-06-01T10:00:00Z"
    stale_resolution = resolution(publication_time="2026-06-01T10:00:00+00:00")
    assert evaluate_meta_inbound_attribution(
        stale, expected_binding=stale_resolution["binding"],
        binding_resolution=stale_resolution, now=NOW,
    )["status"] == "stale"
    wrong_payload = payload()
    wrong_payload["content_attributes"]["referral"]["target_page_id"] = "OTHER-PAGE"
    wrong = evaluate_meta_inbound_attribution(
        wrong_payload, expected_binding=exact_resolution["binding"],
        binding_resolution=exact_resolution, now=NOW,
    )
    assert wrong["reason"] == "target_page_identity_mismatch"


def test_meta_reply_authority_uses_exact_provider_chronology_not_attribution():
    inbound = parse_bound()
    identity = {key: inbound[key] for key in ("account_id", "conversation_id", "contact_id", "inbox_id")}
    result = evaluate_reply_window(
        [{"id": "META-MSG-1", "message_type": 0, "created_at": "2026-08-20T11:00:00Z", "attachments": []}],
        conversation_identity=inbound,
        provider_evidence={"provider_identity_class": "genuine_meta",
            "latest_inbound_message_id": "META-MSG-1",
            "latest_inbound_at_utc": "2026-08-20T11:00:00Z",
            "identity_binding": identity, "expected_identity": identity}, now=NOW)
    assert result["reply_authority_state"] == "ordinary_reply_allowed"
    assert result["provider_identity_class"] == "genuine_meta"


def test_provider_ambiguity_blocks_meta_reply():
    inbound = parse_bound()
    result = evaluate_reply_window(
        [{"id": "META-MSG-1", "message_type": 0, "created_at": "2026-08-20T11:00:00Z", "attachments": []}],
        conversation_identity=inbound,
        provider_evidence={"provider_identity_class": "conflicting"}, now=NOW)
    assert result["reply_authority_state"] == "unavailable"


def test_duplicate_and_concurrent_evaluation_is_deterministic_and_side_effect_free():
    exact_resolution = resolution()
    first = evaluate_meta_inbound_attribution(
        payload(), expected_binding=exact_resolution["binding"],
        binding_resolution=exact_resolution, now=NOW,
    )
    second = evaluate_meta_inbound_attribution(
        payload(), expected_binding=exact_resolution["binding"],
        binding_resolution=exact_resolution, now=NOW,
    )
    assert first == second
    assert first["sends_message"] is False
    assert first["creates_order"] is False
    assert first["customer_response_authority_granted"] is False


def _front_door_packet(inbound):
    return build_sam_front_door_adapter_packet(
        inbound,
        {
            "chatwoot_authority_messages": [{
                "id": inbound["message_id"],
                "message_type": 0,
                "content": inbound["content"],
                "created_at": inbound["last_inbound_at"],
            }],
            "prior_sales_context": {},
            "recovered_reference": {},
        },
        {},
    )


def test_attributed_meta_provenance_reaches_customer_front_door_context():
    packet = _front_door_packet(parse_bound())
    campaign = packet["campaign_or_post_context"]
    assert campaign["campaign_id"] == "BEACON-CAMPAIGN-ABC"
    assert campaign["post_id"] == "PAGE-1_POST-7"
    assert campaign["target_page_id"] == "PAGE-1"
    assert campaign["attribution_status"] == "attributed"
    assert campaign["sam_boundary"] == "No quote, reservation, order or payment."
    assert campaign["post_text"].startswith("Molly")
    assert packet["next_specialist_recommendation"] == "livestock"


def test_canonical_attribution_reaches_final_evidence_to_offer_packet():
    with patch(
        "modules.sales.sam_live_stock_runtime.resolve_canonical_meta_publication_binding",
        return_value=resolution(),
    ):
        result, status = handle_sam_live_stock_chatwoot_inbound(
            payload(),
            environ={
                "DATABASE_URL": "postgresql://read-only",
                "BEACON_FACEBOOK_PAGE_ID": "PAGE-1",
            },
            intake_context_loader=lambda *_args: {
                "success": True,
                "known_fields": {},
                "items": [],
            },
            conversation_history_loader=lambda *_args: {
                "success": True,
                "messages": [{
                    "id": "META-MSG-1",
                    "message_type": 0,
                    "created_at": 1787223600,
                    "content": "Hi, can you tell me what pig sizes you sell?",
                }],
            },
            customer_context_loader=lambda *_args: {
                "success": True,
                "interest": {},
            },
            availability_loader=lambda: [],
        )
    assert status == 200
    campaign = result["sam_decision"]["canonical_evidence_offer"][
        "campaign_or_post_context"
    ]
    assert campaign["campaign_id"] == "BEACON-CAMPAIGN-ABC"
    assert campaign["post_id"] == "PAGE-1_POST-7"
    assert campaign["post_text"].startswith("Molly")
    assert campaign["attribution_status"] == "attributed"


def test_rejected_meta_attribution_cannot_become_campaign_context():
    row = payload(content_attributes={"referral": {
        "source_id": "PAGE-1_POST-7",
        "target_page_id": "",
        "attribution_identity": "BEACON-CAMPAIGN-ABC",
    }})
    packet = _front_door_packet(parse_bound(row))
    campaign = packet["campaign_or_post_context"]
    assert campaign["campaign_id"] == ""
    assert campaign["post_id"] == ""
    assert campaign["target_page_id"] == ""
    assert campaign["attribution_status"] == "unverified"
    assert campaign["available"] is False
    assert campaign["post_text"] == ""


def test_payload_mismatches_and_missing_or_invalid_chronology_never_promote_context():
    cases = []
    for key, value in (
        ("attribution_identity", "PAYLOAD-CAMPAIGN"),
        ("source_id", "PAGE-1_POST-OTHER"),
        ("publication_time", "2026-08-19T10:01:00Z"),
        ("publication_time", "not-a-time"),
        ("publication_time", ""),
    ):
        row = payload()
        row["content_attributes"]["referral"][key] = value
        cases.append(row)
    invalid_inbound = payload(created_at="not-a-time")
    missing_inbound = payload(created_at="", timestamp="")
    before_publication = payload(created_at="2026-08-19T09:59:59Z")
    cases.extend((invalid_inbound, missing_inbound, before_publication))
    for row in cases:
        inbound = parse_bound(row)
        assert inbound["processable"] is True
        assert inbound["meta_attribution"]["status"] != "attributed"
        campaign = _front_door_packet(inbound)["campaign_or_post_context"]
        assert campaign["campaign_id"] == ""
        assert campaign["post_id"] == ""
        assert campaign["available"] is False


def test_unavailable_canonical_binding_fails_only_attribution_and_preserves_ordinary_reply():
    unavailable = {
        "success": False,
        "status": "unavailable",
        "reason": "canonical_publication_binding_not_found",
        "binding": {},
    }
    inbound = parse_bound(resolved=unavailable)
    assert inbound["processable"] is True
    assert inbound["identity_provenance"]["provider_identity_class"] == "genuine_meta"
    assert inbound["meta_attribution"]["status"] == "unverified"
    assert _front_door_packet(inbound)["campaign_or_post_context"]["available"] is False
    identity = {key: inbound[key] for key in ("account_id", "conversation_id", "contact_id", "inbox_id")}
    reply = evaluate_reply_window(
        [{"id": "META-MSG-1", "message_type": 0, "created_at": "2026-08-20T11:00:00Z", "attachments": []}],
        conversation_identity=inbound,
        provider_evidence={
            "provider_identity_class": "genuine_meta",
            "latest_inbound_message_id": "META-MSG-1",
            "latest_inbound_at_utc": "2026-08-20T11:00:00Z",
            "identity_binding": identity,
            "expected_identity": identity,
        },
        now=NOW,
    )
    assert reply["reply_authority_state"] == "ordinary_reply_allowed"


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""
        self.params = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self._cursor


def test_canonical_publication_resolver_reads_one_exact_binding_without_payload_authority():
    row = canonical_binding()
    values = tuple(row[key] for key in (
        "attribution_identity", "post_id", "target_page_id", "publication_time",
        "sam_boundary", "post_text", "publish_packet_id", "publication_binding_id",
        "binding_source",
    ))
    cursor = _Cursor([values])
    connect_call = {}
    def connector(database_url, **kwargs):
        connect_call.update(database_url=database_url, **kwargs)
        return _Connection(cursor)
    result = resolve_canonical_meta_publication_binding(
        payload(), database_url="postgresql://read-only", expected_page_id="PAGE-1",
        connector=connector,
    )
    assert result["success"] is True
    assert result["binding"]["attribution_identity"] == "BEACON-CAMPAIGN-ABC"
    assert cursor.params == ("PAGE-1_POST-7", "PAGE-1", "PAGE-1")
    assert connect_call["database_url"] == "postgresql://read-only"
    assert "default_transaction_read_only=on" in connect_call["options"]
    assert "beacon_facebook_post_execution_events" in cursor.sql
    assert "beacon_protected_publication_consumers" in cursor.sql
    assert "beacon_organic_publication_bindings" in cursor.sql


def test_producer_consumer_readback_shape_mismatch_leaves_attribution_unresolved():
    cursor = _Cursor([])
    result = resolve_canonical_meta_publication_binding(
        payload(), database_url="postgresql://read-only", expected_page_id="PAGE-1",
        connector=lambda *_args, **_kwargs: _Connection(cursor),
    )
    assert result["success"] is False
    assert result["reason"] == "canonical_publication_binding_not_found"
    assert "p.status = 'confirmed'" in cursor.sql
    assert "{facebook_result,provider_readback_confirmed}" in cursor.sql
    assert "{facebook_result,provider_readback,id}" in cursor.sql
    inbound = parse_bound(resolved=result)
    assert inbound["processable"] is True
    assert inbound["meta_attribution"]["status"] == "unverified"
    assert inbound["meta_attribution"]["campaign_id"] == ""
