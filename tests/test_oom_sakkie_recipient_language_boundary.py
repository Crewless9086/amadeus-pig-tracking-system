import pytest

from modules.oom_sakkie.family_message_lifecycle import deliver_family_result, localize_recipient_result


AF = {"output_language": "af"}


@pytest.mark.parametrize("specialist,action_kind", [
    ("SAM", "sam_sale_payment"),
    ("BEACON", "beacon_campaign_review"),
    ("DOCUMENTS", "documents_green_print"),
    ("ROOTLINE", "rootline_irrigation_segment"),
    ("HERDMASTER", "herdmaster_breeding_grouped"),
])
def test_every_shared_specialist_preview_is_wholly_afrikaans_with_afrikaans_buttons(
        specialist, action_kind):
    result = localize_recipient_result(AF, {
        "status": "protected_preview_ready", "specialist_identity": specialist,
        "action_kind": action_kind, "answer": "Confirm this protected preview.",
        "preview": {"pig_id": "PIG-126", "effective_date": "2026-08-23"},
        "reply_markup": {"inline_keyboard": [[
            {"text": "Confirm", "callback_data": "oompa:t:confirm"},
            {"text": "Correct", "callback_data": "oompa:t:change"},
            {"text": "Cancel", "callback_data": "oompa:t:cancel"},
        ]]},
    }, specialist)
    assert "BESKERMDE VOORSKOU" in result["answer"]
    assert "PIG-126" in result["answer"] and "2026-08-23" in result["answer"]
    assert all(word not in result["answer"] for word in ("Confirm", "protected", "Nothing"))
    assert [item["text"] for item in result["reply_markup"]["inline_keyboard"][0]] == [
        "Bevestig", "Maak reg", "Kanselleer"]


@pytest.mark.parametrize("status,expected", [
    ("protected_preview_change_requested", "reggestelde feite"),
    ("protected_preview_cancelled", "gekanselleer"),
    ("protected_action_failed", "veilig teruggehou"),
    ("payment_state_recorded", "VOLTOOI"),
    ("protected_callback_replay", "reeds veilig verwerk"),
])
def test_generic_protected_journey_states_are_afrikaans(status, expected):
    result = localize_recipient_result(AF, {"status": status,
        "answer": "English provider wording must not escape."}, "OOM_SAKKIE")
    assert expected in result["answer"]
    assert "English" not in result["answer"]


def test_charl_english_result_is_unchanged():
    original = {"status": "protected_preview_ready", "answer": "Confirm this preview.",
        "reply_markup": {"inline_keyboard": [[{"text": "Confirm",
            "callback_data": "oompa:t:confirm"}]]}}
    assert localize_recipient_result({"output_language": "en"}, original, "SAM") == original


def test_unrecognized_afrikaans_protected_status_fails_closed_before_delivery():
    sent = []
    result = deliver_family_result({"output_language": "af", "telegram_user_id": "2",
        "telegram_chat_id": "2", "provider_message_id": "9"}, {
        "status": "new_unrecognized_visible_state", "answer": "English leak",
        "callback_token": "t", "preview_digest": "d", "action_kind": "future_action",
    }, specialist="FUTURE", sender=lambda *args: sent.append(args))
    assert result["status"] == "recipient_language_render_unrecognized"
    assert result["telegram_sends"] == 0 and sent == []


def test_unrecognized_afrikaans_unbound_status_also_fails_closed_before_delivery():
    sent = []
    result = deliver_family_result({"output_language": "af", "telegram_user_id": "2",
        "telegram_chat_id": "2", "provider_message_id": "10"}, {
        "status": "future_unbound_clarification", "answer": "Which item do you mean?",
    }, specialist="FUTURE", sender=lambda *args: sent.append(args))
    assert result["status"] == "recipient_language_render_unrecognized"
    assert result["telegram_sends"] == 0 and sent == []
