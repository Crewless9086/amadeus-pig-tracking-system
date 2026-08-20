from datetime import datetime, timezone

from modules.sales.sam_live_stock_runtime import parse_chatwoot_inbound
from modules.sales.sam_meta_inbound import evaluate_meta_inbound_attribution
from modules.sales.sam_owner_reply_window import evaluate_reply_window

NOW = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)


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
    inbound = parse_chatwoot_inbound(payload())
    assert inbound["processable"] is True
    assert inbound["channel"] == "chatwoot_facebook"
    assert inbound["contact_id"] == "PSID-1"
    assert inbound["identity_provenance"]["provider_identity_class"] == "genuine_meta"
    assert inbound["meta_attribution"]["campaign_id"] == "BEACON-CAMPAIGN-ABC"
    assert inbound["meta_attribution"]["post_id"] == "PAGE-1_POST-7"


def test_attribution_present_absent_stale_and_wrong_page_fail_independently():
    exact = evaluate_meta_inbound_attribution(payload(), expected_page_id="PAGE-1", now=NOW)
    assert exact["status"] == "attributed"
    missing = payload(content_attributes={"referral": {"source_id": "PAGE-1_POST-7", "target_page_id": "PAGE-1"}})
    assert evaluate_meta_inbound_attribution(missing, expected_page_id="PAGE-1", now=NOW)["status"] == "absent"
    stale = payload()
    stale["content_attributes"]["referral"]["publication_time"] = "2026-06-01T10:00:00Z"
    assert evaluate_meta_inbound_attribution(stale, expected_page_id="PAGE-1", now=NOW)["status"] == "stale"
    wrong = evaluate_meta_inbound_attribution(payload(), expected_page_id="OTHER-PAGE", now=NOW)
    assert wrong["reason"] == "target_page_identity_mismatch"


def test_meta_reply_authority_uses_exact_provider_chronology_not_attribution():
    inbound = parse_chatwoot_inbound(payload())
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
    inbound = parse_chatwoot_inbound(payload())
    result = evaluate_reply_window(
        [{"id": "META-MSG-1", "message_type": 0, "created_at": "2026-08-20T11:00:00Z", "attachments": []}],
        conversation_identity=inbound,
        provider_evidence={"provider_identity_class": "conflicting"}, now=NOW)
    assert result["reply_authority_state"] == "unavailable"


def test_duplicate_and_concurrent_evaluation_is_deterministic_and_side_effect_free():
    first = evaluate_meta_inbound_attribution(payload(), expected_page_id="PAGE-1", now=NOW)
    second = evaluate_meta_inbound_attribution(payload(), expected_page_id="PAGE-1", now=NOW)
    assert first == second
    assert first["sends_message"] is False
    assert first["creates_order"] is False
    assert first["customer_response_authority_granted"] is False
