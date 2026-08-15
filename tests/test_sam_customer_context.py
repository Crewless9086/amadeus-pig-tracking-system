import json

from modules.sales.sam_customer_context import (
    canonical_customer_identity,
    load_canonical_customer_context,
    project_canonical_customer_context,
)


def test_identity_is_channel_neutral_for_same_verified_phone():
    whatsapp = canonical_customer_identity({
        "account_id": "147387", "contact_id": "11", "customer_phone": "+27 82 123 4567",
    })
    widget = canonical_customer_identity({
        "account_id": "147387", "contact_id": "99", "customer_phone": "27821234567",
    })
    assert whatsapp["canonical_customer_id"] == widget["canonical_customer_id"]
    assert whatsapp["contains_private_identity"] is False


def test_identity_fails_closed_without_account_or_customer_evidence():
    assert canonical_customer_identity({"customer_phone": "2782"})["resolved"] is False
    assert canonical_customer_identity({"account_id": "1"})["resolved"] is False


def test_projection_retains_latest_customer_facts_and_open_question():
    rows = [
        (
            "wa-1", "m1", "Channel::Whatsapp",
            {"customer_language": "af", "location": "George", "category": "weaner"},
            {"next_action": "ask_one_missing_detail", "suggested_reply_text": "Hoeveel soek jy?",
             "inbound": {"customer_name": "Ada"}},
            "2026-08-15T08:00:00+00:00",
        ),
        (
            "web-2", "m2", "Channel::WebWidget",
            json.dumps({"quantity": 6, "timing": "September"}),
            json.dumps({"next_action": "prepare_offer", "suggested_reply_text": "Dankie, ek het dit."}),
            "2026-08-15T09:00:00+00:00",
        ),
    ]
    projected = project_canonical_customer_context(list(reversed(rows)), identity={"resolved": True})
    assert projected["interest"] == {
        "customer_language": "af", "location": "George", "category": "weaner",
        "customer_name": "Ada", "quantity": 6, "timing": "September",
        "current_conversation_goal": "prepare_offer",
        "last_unanswered_question": "Hoeveel soek jy?",
    }
    assert projected["conversation_ids"] == ["wa-1", "web-2"]


class _Cursor:
    def __init__(self):
        self.params = None

    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, _sql, params): self.params = params
    def fetchall(self): return []


class _Connection:
    def __init__(self): self.cursor_value = _Cursor()
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self.cursor_value


def test_loader_is_read_only_and_uses_normalized_phone_scope():
    connection = _Connection()
    result = load_canonical_customer_context(
        {"account_id": "147387", "contact_id": "9", "customer_phone": "+27 82-123-4567"},
        connect_factory=lambda: connection,
    )
    assert result["status"] == "canonical_customer_context_empty"
    assert result["writes_performed"] is False
    assert connection.cursor_value.params[1:4] == ("27821234567",) * 3
