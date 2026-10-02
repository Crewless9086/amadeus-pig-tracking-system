"""Transport qualification with native callback envelopes and a durable fake journal.

No provider/database calls: the domain handler is intentionally outside this suite.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import socket
from unittest.mock import Mock

import pytest

from modules.oom_sakkie import family_message_lifecycle as family
from modules.oom_sakkie import telegram_direct as direct
from modules.oom_sakkie.retained_mortality_continuation import feedback


SECRET = "synthetic-feedback-webhook-secret-32-chars"
OWNER = "9001"


def environment(language="en"):
    return {
        "OOM_SAKKIE_TELEGRAM_OWNER_USER_ID": OWNER,
        "OOM_SAKKIE_TELEGRAM_OWNER_LANGUAGE": language,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": OWNER,
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": "123456789:" + "x" * 40,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": SECRET,
    }


def native_callback(receipt="synthetic-callback-1"):
    return {"update_id": 7001, "callback_query": {
        "id": receipt, "from": {"id": int(OWNER), "language_code": "en"},
        "data": "oompa:SYNTHETIC-EXPIRED:confirm",
        "message": {"message_id": 7002, "date": 1786880000,
                    "chat": {"id": int(OWNER), "type": "private"}}}}


class Response:
    def __init__(self, raw=b'{"ok":true,"result":true}'):
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.raw


@pytest.fixture(autouse=True)
def refuse_unmocked_io(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("transport test attempted unmocked provider or database access")
    class AdvancingClock(datetime):
        tick = 0

        @classmethod
        def now(cls, tz=None):
            cls.tick += 1
            value = datetime(2026, 9, 1, 10, tzinfo=timezone.utc) + timedelta(seconds=cls.tick)
            return value.astimezone(tz) if tz is not None else value.replace(tzinfo=None)

    # A replay must remain exact after wall-clock time advances, not only when
    # Windows' coarse clock accidentally gives two calls the same timestamp.
    monkeypatch.setattr(direct, "datetime", AdvancingClock)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(direct.urllib_request, "urlopen", forbidden)
    monkeypatch.setattr(family, "_event_store", forbidden)
    monkeypatch.setattr(family, "_send_telegram", forbidden)
    monkeypatch.setattr(family, "_edit_telegram", forbidden)
    monkeypatch.setattr(direct, "handle_protected_action_input", forbidden)
    monkeypatch.setattr(direct, "deliver_family_result", forbidden)


def provider_ack(monkeypatch, raw=b'{"ok":true,"result":true}', error=None):
    requests = []
    def open_request(request, *, timeout):
        assert request.get_method() == "POST" and timeout == 15
        assert request.full_url.endswith("/answerCallbackQuery")
        requests.append(json.loads(request.data))
        if error:
            raise error
        return Response(raw)
    monkeypatch.setattr(direct.urllib_request, "urlopen", open_request)
    return requests


def webhook(monkeypatch, result, *, language="en", receipt="synthetic-callback-1", status=200):
    handler = Mock(return_value=(result, status))
    monkeypatch.setattr(direct, "handle_protected_action_input", handler)
    body, code = direct.handle_telegram_direct_webhook(native_callback(receipt),
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=environment(language))
    assert handler.call_count == 1, (code, body.get("status"))
    parsed = handler.call_args.args[0]
    assert parsed["telegram_user_id"] == parsed["telegram_chat_id"] == OWNER
    assert parsed["telegram_chat_type"] == "private"
    assert parsed["callback_query_id"] == parsed["provider_message_id"] == receipt
    assert parsed["reply_to_message_id"] == "7002"
    assert parsed["callback_data"] == native_callback(receipt)["callback_query"]["data"]
    assert parsed["output_language"] == language
    return body, code


@pytest.mark.parametrize("text", [None, ""])
def test_unadorned_ack_preserves_original_provider_payload(monkeypatch, text):
    requests = provider_ack(monkeypatch)
    result, code = direct.acknowledge_telegram_callback("receipt", environment(), text=text)
    assert code == 200 and result["success"] is True
    assert requests == [{"callback_query_id": "receipt"}]
    assert result["sends_telegram"] is False


def test_alert_serializes_at_most_200_unicode_characters(monkeypatch):
    requests = provider_ack(monkeypatch)
    text = "Hersien asseblief — " * 30
    result, code = direct.acknowledge_telegram_callback("receipt", environment(),
        text=text, show_alert=True)
    assert code == 200 and result["success"] is True
    assert requests == [{"callback_query_id": "receipt", "text": text[:200], "show_alert": True}]
    assert len(requests[0]["text"]) == 200


@pytest.mark.parametrize("raw", [b'{"ok":false,"description":"query is too old"}', b'not json'])
def test_negative_or_invalid_ack_is_a_failure_not_an_acknowledgement(monkeypatch, raw):
    provider_ack(monkeypatch, raw)
    result, code = direct.acknowledge_telegram_callback("receipt", environment(), text="Notice", show_alert=True)
    assert code >= 400 and result["success"] is False
    assert result["status"] == "telegram_callback_acknowledgement_failed"
    assert result["sends_telegram"] is False


@pytest.mark.parametrize("language,kind,words", [
    ("en", "ready", "confirm the new card"), ("af", "ready", "bevestig die nuwe kaart"),
    ("en", "refused", "This press did not record anything"), ("af", "refused", "Niks is aangeteken nie"),
    ("en", "latest", "newest confirmation card"), ("af", "latest", "nuutste bevestigingskaart"),
])
def test_feedback_is_localized_and_never_authorizes_a_farm_write(language, kind, words):
    result = feedback({"output_language": language}, "synthetic-status", kind)
    assert words in result["callback_feedback"]
    assert 0 < len(result["callback_feedback"]) <= 200
    assert result["writes_farm_data"] is False and result["success"] is False
    assert result["suppress_owner_delivery"] is True
    assert not result.get("reply_markup") and not result.get("callback_token")


@pytest.mark.parametrize("language", ["en", "af"])
@pytest.mark.parametrize("kind", ["refused", "latest"])
def test_native_refusal_is_visible_as_alert_without_retrying_the_webhook(monkeypatch, language, kind):
    requests = provider_ack(monkeypatch)
    result = feedback({"output_language": language}, "retained_continuation_refused", kind)
    body, code = webhook(monkeypatch, result, language=language, status=409)
    assert code == 200 and body["success"] is False and body["writes"] is False
    assert requests == [{"callback_query_id": "synthetic-callback-1",
        "text": result["callback_feedback"], "show_alert": True}]
    assert body["feedback_delivery"] is None and body["sends_telegram"] is False


@pytest.mark.parametrize("confirmed", [True, False])
@pytest.mark.parametrize("language", ["en", "af"])
def test_preview_alert_follows_delivery_truth_and_does_not_leak_policy(monkeypatch, confirmed, language):
    requests = provider_ack(monkeypatch)
    policy = object()  # Deliberately cannot be JSON-encoded.
    action = {"success": True, "status": "preview_ready", "continuation_requested": True,
        "answer": "Synthetic reviewed preview", "mission_id": "SYNTHETIC-SUCCESSOR",
        "card_mission_id": "SYNTHETIC-CARD", "writes_farm_data": False,
        "_retained_mortality_policy": policy}
    delivery = Mock(return_value={"success": confirmed,
        "status": "family_message_delivered" if confirmed else "family_message_delivery_ambiguous",
        "telegram_sends": int(confirmed), "telegram_edits": 0})
    monkeypatch.setattr(direct, "deliver_family_result", delivery)
    body, code = webhook(monkeypatch, action, language=language)
    assert code == 200 and body["success"] is confirmed and body["writes"] is False
    assert body["sends_telegram"] is confirmed
    assert delivery.call_count == 1
    assert delivery.call_args.args[1]["_retained_mortality_policy"] is policy
    assert delivery.call_args.kwargs["card_mission_id"] == "SYNTHETIC-CARD"
    expected = feedback({"output_language": language}, "", "ready" if confirmed else "refused")
    assert requests[0]["text"] == expected["callback_feedback"]
    assert not any(key.startswith("_") for key in body["protected_action"])
    assert "_retained_mortality_policy" not in json.dumps(body)
    assert "_retained_mortality_policy" in action  # Serialization must not mutate domain result.


class Journal:
    """Unique event identities and card-scoped reads, without an actual database."""
    def __init__(self, ambiguous=False):
        self.rows = {}
        self.sends = []
        self.deliveries = []
        self.ambiguous = ambiguous

    def store(self, operation, identity, payload):
        if operation == "load":
            return [deepcopy(row) for row in self.rows.values() if row["card_mission_id"] == identity]
        assert operation == "record"
        created = identity not in self.rows
        if created:
            self.rows[identity] = deepcopy(payload)
        return {"success": True, "created": created}

    def send(self, chat, text):
        self.sends.append((chat, text))
        if self.ambiguous:
            return {"success": False, "status": "telegram_delivery_ambiguous"}
        return {"success": True, "telegram_message_id": str(8000 + len(self.sends))}

    def deliver(self, parsed, result, **kwargs):
        self.deliveries.append((deepcopy(parsed), deepcopy(result), deepcopy(kwargs)))
        return family.deliver_family_result(parsed, result, **kwargs,
            event_store=self.store, sender=self.send,
            editor=lambda *_a, **_kw: pytest.fail("receipt feedback must never edit another card"))


@pytest.mark.parametrize("language", ["en", "af"])
@pytest.mark.parametrize("ack_failure", ["transport", "negative"])
def test_failed_ack_uses_one_receipt_bound_localized_family_message(monkeypatch, language, ack_failure):
    requests = provider_ack(monkeypatch,
        raw=b'{"ok":false,"description":"query is too old"}' if ack_failure == "negative" else b'{}',
        error=OSError("synthetic disconnected acknowledgement") if ack_failure == "transport" else None)
    journal = Journal()
    monkeypatch.setattr(direct, "deliver_family_result", journal.deliver)
    result = feedback({"output_language": language}, "retained_continuation_refused", "refused")
    first, code = webhook(monkeypatch, result, language=language)
    rows = deepcopy(journal.rows)
    replay, replay_code = webhook(monkeypatch, result, language=language)
    assert code == replay_code == 200 and first["success"] is replay["success"] is False
    assert first["feedback_delivery"]["success"] is replay["feedback_delivery"]["success"] is True
    assert first["sends_telegram"] is True and replay["sends_telegram"] is False
    assert first["writes"] is replay["writes"] is False
    assert journal.sends == [(OWNER, "<b>🌿 Oom Sakkie</b>\n\n" + result["callback_feedback"])]
    assert journal.rows == rows and len(requests) == 2
    assert sorted(row["state"] for row in rows.values()) == ["delivered", "delivery_attempted"]
    for row in rows.values():
        assert row["owner_user_id"] == row["chat_id"] == OWNER
        assert row["provider_message_id"] == "synthetic-callback-1"
        assert row["mission_id"] == row["card_mission_id"]
        assert not any(row.get(key) for key in ("callback_token", "preview_digest", "action_kind", "reply_markup"))
    first_identity = journal.deliveries[0][2]["mission_id"]
    assert journal.deliveries[1][2]["mission_id"] == first_identity
    first_clock = journal.deliveries[0][0]["provider_timestamp"]
    assert journal.deliveries[1][0]["provider_timestamp"] != first_clock
    assert all(row["provider_timestamp"] == first_clock for row in rows.values())
    for _, sent_result, _ in journal.deliveries:
        assert sent_result["writes_farm_data"] is False
        assert sent_result["recipient_language"] == language
        assert not sent_result.get("reply_markup")
    # A genuinely different receipt has its own notice; a duplicate has none.
    newer, _ = webhook(monkeypatch, result, language=language, receipt="synthetic-callback-2")
    assert newer["feedback_delivery"]["success"] is True and len(journal.sends) == 2
    assert journal.deliveries[-1][2]["mission_id"] != first_identity


def test_ambiguous_fallback_does_not_claim_delivery_or_retry_provider(monkeypatch):
    provider_ack(monkeypatch, error=OSError("synthetic ack failure"))
    journal = Journal(ambiguous=True)
    monkeypatch.setattr(direct, "deliver_family_result", journal.deliver)
    result = feedback({"output_language": "en"}, "retained_continuation_refused", "refused")
    first, code = webhook(monkeypatch, result)
    replay, replay_code = webhook(monkeypatch, result)
    assert code == replay_code == 200 and len(journal.sends) == 1
    for body in (first, replay):
        assert body["success"] is body["writes"] is body["sends_telegram"] is False
        assert body["feedback_delivery"]["success"] is False
        assert body["feedback_delivery"]["telegram_sends"] == 0
    assert not any(row["state"] == "delivered" for row in journal.rows.values())
    assert any(row["state"] == "contained" for row in journal.rows.values())


def test_ordinary_protected_callback_keeps_unadorned_ack_and_original_status(monkeypatch):
    requests = provider_ack(monkeypatch)
    action = {"success": False, "status": "protected_callback_expired", "writes_farm_data": False}
    body, code = webhook(monkeypatch, action, status=409)
    assert code == 409 and body["writes"] is False
    assert requests == [{"callback_query_id": "synthetic-callback-1"}]
    assert "feedback_delivery" not in body


@pytest.mark.parametrize("outside_scope", ["ordinary", "other_contract", "other_specialist", "farm_write_marker"])
def test_feedback_timestamp_reuse_cannot_relax_another_delivery_contract(outside_scope):
    parsed = {"telegram_user_id": OWNER, "telegram_chat_id": OWNER,
        "provider_message_id": "synthetic-receipt", "provider_timestamp": "2026-09-01T10:00:00+00:00",
        "output_language": "en", "text": ""}
    result = {"status": "retained_confirmation_feedback", "answer": "Synthetic notice",
        "recipient_render_contract": "retained_confirmation_feedback_v1", "writes_farm_data": False}
    specialist = "HERDMASTER"
    if outside_scope == "ordinary":
        result["status"] = "waiting_for_input"
    elif outside_scope == "other_contract":
        result["recipient_render_contract"] = "another_contract"
    elif outside_scope == "other_specialist":
        specialist = "ROOTLINE"
    else:
        result["writes_farm_data"] = True
    journal = Journal()
    kwargs = {"specialist": specialist, "mission_id": "SYNTHETIC-CONTROL", "card_mission_id": "SYNTHETIC-CONTROL"}
    first = journal.deliver(parsed, result, **kwargs)
    retry_input = {**parsed, "provider_timestamp": "2026-09-01T10:01:00+00:00"}
    original_retry = deepcopy(retry_input)
    replay = journal.deliver(retry_input, result, **kwargs)
    assert first["success"] is True
    assert replay["success"] is False and replay["status"] == "family_message_provider_replay_binding_conflict"
    assert len(journal.sends) == 1
    assert retry_input == original_retry
