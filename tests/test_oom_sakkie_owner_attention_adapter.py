import hashlib
import unittest
from datetime import datetime, timezone

from modules.oom_sakkie.owner_attention_adapter import (
    operate_owner_attention_queue,
    process_owner_attention_callback,
    project_sam_dispositions,
    repair_owner_attention_resolution,
)
from modules.sales.sam_live_stock_inbox_operator import operate_livestock_inbox


NOW = datetime(2026, 7, 31, 8, 0, tzinfo=timezone.utc)
ENV = {"OOM_SAKKIE_OWNER_ATTENTION_QUEUE_ENABLED": "1", "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token",
       "SAM_LIVE_STOCK_TELEGRAM_OWNER_CHAT_ID": "44", "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "77,88",
       "OOM_SAKKIE_OWNER_ATTENTION_OWNER_USER_ID": "77"}
OWNER_HASH = hashlib.sha256(b'{"telegram_owner_id":"77"}').hexdigest()


def disposition(state="new", **overrides):
    row = {"account_id": "account-1", "inbox_id": "inbox-1", "contact_id": "contact-1",
           "conversation_id": "conversation-1", "inbound_message_id": "101", "latest_inbound_at": 1785483000,
           "queue_relevant": True, "eligible": True, "selected_for_processing": False,
           "provider_confirmed": False, "owner_decision_required": False, "disposition": "deferred_to_next_autonomous_cycle",
           "provider_state": ""}
    if state == "answered":
        row.update(provider_confirmed=True, selected_for_processing=True, disposition="processed", provider_state="provider_delivered")
    elif state == "awaiting":
        row.update(eligible=False, disposition="awaiting_customer")
    elif state == "qualification":
        row.update(selected_for_processing=True, disposition="processed")
    row.update(overrides)
    return row


class Rail:
    def __init__(self):
        self.card = {}
        self.events = []
        self.sends = []
        self.edits = []

    def loader(self, _identity):
        return {"success": True, "card": dict(self.card)}, 200

    def recorder(self, event):
        self.events.append(event)
        owner = (event.get("review_json") or {}).get("owner_card") or {}
        if owner.get("state") == "active":
            self.card = dict(owner)
        return {"success": True, "created": not any(row.get("review_event_id") == event.get("review_event_id") for row in self.events[:-1]),
                "review_event_id": event.get("review_event_id")}, 200

    def sender(self, _token, chat_id, text, markup):
        self.sends.append((chat_id, text, markup))
        return {"ok": True, "result": {"message_id": "900"}}

    def editor(self, _token, chat_id, message_id, text, markup):
        self.edits.append((chat_id, message_id, text, markup))
        return {"ok": True, "result": {"message_id": message_id}}


class OwnerAttentionAdapterTests(unittest.TestCase):
    def test_real_sam_delivery_exception_projects_a_bound_protected_decision(self):
        captured = []
        row = {"id": "conversation-1", "account_id": "account-1", "inbox_id": "inbox-1", "can_reply": True,
               "meta": {"sender": {"id": "contact-1"}},
               "last_non_activity_message": {"id": 101, "message_type": 0, "created_at": 1785483000}}
        history = {"success": True, "messages": [{"id": "101", "message_type": 0, "created_at": 1785483000,
                                                   "private": False, "content": "Can you deliver pigs to Riversdale?"}]}
        packet = operate_livestock_inbox(environ={}, conversation_page_loader=lambda _page: {"data": {"meta": {"all_count": 1}, "payload": [row]}},
            history_loader=lambda *_: (history, 200), claim_exists=lambda *_: False,
            inbound_processor=lambda _payload: {"processed": True, "_operation_status_code": 200,
                "sam_decision": {"protected_owner_exception_required": True,
                    "delivery_owner_exception": {"eligible": True, "version": "sam_delivery_owner_exception_v1"},
                    "routine_reply_delivery": {"delivery_outcome": {"delivery_state": "provider_delivered"}}}},
            attention_queue_operator=lambda dispositions, **_kwargs: captured.extend(dispositions) or {"success": True}, now=NOW)
        self.assertTrue(packet["lane_active"])
        self.assertEqual(captured[0]["owner_attention_decision"]["source_contract"], "sam_delivery_owner_exception_v1")

    def test_missing_sam_account_identity_is_not_manufactured(self):
        projected = project_sam_dispositions([disposition(account_id="")], observed_at=NOW)
        self.assertEqual(projected, [])

    def test_ordinary_messages_create_only_one_buttonless_summary(self):
        rail = Rail()
        result = operate_owner_attention_queue([disposition(), disposition("answered", conversation_id="conversation-2", contact_id="contact-2", inbound_message_id="102")],
            environ=ENV, now=NOW, active_card_loader=rail.loader, evidence_recorder=rail.recorder,
            telegram_sender=rail.sender, telegram_editor=rail.editor)
        self.assertTrue(result["success"])
        self.assertEqual(result["individual_ordinary_notifications"], 0)
        self.assertEqual(len(result["deliveries"]), 1)
        self.assertEqual(len(rail.sends), 1)
        self.assertEqual(rail.sends[0][2], {"inline_keyboard": []})

    def test_repeated_period_events_edit_same_summary_instead_of_sending_clutter(self):
        rail = Rail()
        kwargs = dict(environ=ENV, now=NOW, active_card_loader=rail.loader, evidence_recorder=rail.recorder,
                      telegram_sender=rail.sender, telegram_editor=rail.editor)
        operate_owner_attention_queue([disposition()], **kwargs)
        operate_owner_attention_queue([disposition(), dict(disposition(), status="ignored")], **kwargs)
        self.assertEqual(len(rail.sends), 1)
        self.assertEqual(len(rail.edits), 1)
        self.assertEqual(rail.edits[0][1], "900")
        self.assertEqual(rail.edits[0][3], {"inline_keyboard": []})

    def test_summary_counts_current_conversations_and_supported_states(self):
        rows = [disposition(), disposition("answered", conversation_id="conversation-2", contact_id="contact-2", inbound_message_id="102"),
                disposition("awaiting", conversation_id="conversation-3", contact_id="contact-3", inbound_message_id="103"),
                disposition("qualification", conversation_id="conversation-4", contact_id="contact-4", inbound_message_id="104")]
        projected = project_sam_dispositions(rows, observed_at=NOW)
        self.assertEqual({item["status"] for item in projected}, {"new_enquiry", "automatically_answered", "awaiting_customer", "qualification_progress"})

    def test_incomplete_identity_blocks_only_unsupported_row(self):
        rail = Rail()
        result = operate_owner_attention_queue([disposition(contact_id=""), disposition(conversation_id="conversation-2", contact_id="contact-2")],
            environ=ENV, now=NOW, active_card_loader=rail.loader, evidence_recorder=rail.recorder, telegram_sender=rail.sender)
        self.assertEqual(result["queue"]["summary"]["counts"]["new_enquiries"], 1)

    def test_invalid_identity_chronology_and_reserved_decision_fields_are_not_trusted(self):
        decision = {"source_contract": "sam_delivery_owner_exception_v1", "requested_authority": "delivery_commitment",
                    "expires_at": "2026-07-31T09:00:00+00:00", "choices": [], "conversation_id": "forged"}
        rows = [disposition(contact_id="customer email@example.com"), disposition(latest_inbound_at="bad"),
                disposition(inbound_message_id="not-numeric"), disposition(owner_decision_required=True, owner_attention_decision=decision)]
        projected = project_sam_dispositions(rows, observed_at=NOW)
        self.assertEqual(len(projected), 1)
        self.assertEqual(projected[0]["conversation_id"], "conversation-1")
        self.assertEqual(projected[0]["status"], "qualification_progress")

    def test_disabled_adapter_preserves_sam_and_calls_no_telegram(self):
        result = operate_owner_attention_queue([disposition()], environ={}, now=NOW)
        self.assertEqual(result["status"], "owner_attention_queue_disabled")
        self.assertFalse(result["calls_telegram"])

    def test_only_supported_protected_decision_gets_an_individual_card(self):
        rail = Rail()
        decision = {"requested_authority": "delivery_commitment", "expires_at": "2026-07-31T09:00:00+00:00",
                    "source_contract": "sam_delivery_owner_exception_v1",
                    "choices": [{"id": "approve", "label_code": "approve_delivery", "actionable": True,
                                 "outcome_code": "delivery_approved", "follow_up_trigger_code": "prepare_governed_reply"}]}
        row = disposition(owner_decision_required=True, owner_attention_decision=decision)
        result = operate_owner_attention_queue([row], environ=ENV, now=NOW, active_card_loader=lambda identity: ({"success": True, "card": {}}, 200),
            evidence_recorder=rail.recorder, telegram_sender=rail.sender)
        self.assertEqual(len(result["queue"]["decision_cards"]), 1)
        self.assertEqual(len(rail.sends), 2)
        self.assertEqual(rail.sends[0][2], {"inline_keyboard": []})
        self.assertTrue(rail.sends[1][2]["inline_keyboard"])

    def test_unsupported_owner_flag_creates_no_buttons_or_fake_decision(self):
        rail = Rail()
        result = operate_owner_attention_queue([disposition(owner_decision_required=True)], environ=ENV, now=NOW,
            active_card_loader=rail.loader, evidence_recorder=rail.recorder, telegram_sender=rail.sender)
        self.assertEqual(result["queue"]["decision_cards"], [])
        self.assertEqual(result["queue"]["summary"]["counts"]["genuine_owner_decisions"], 0)

    def test_systemic_alert_is_separate_deduplicated_and_buttonless(self):
        rail = Rail()
        result = operate_owner_attention_queue([], sam_state={"state": "systemically_contained",
            "affected_work_codes": ["current_eligible_enquiries"], "manual_coverage_required": True,
            "manual_coverage_reason_code": "systemic_containment"}, environ=ENV, now=NOW,
            active_card_loader=lambda identity: ({"success": True, "card": {}}, 200), evidence_recorder=rail.recorder, telegram_sender=rail.sender)
        self.assertEqual(len(result["queue"]["system_alerts"]), 1)
        self.assertEqual(rail.sends[-1][2], {"inline_keyboard": []})

    def test_healthy_state_resolves_prior_system_alert_in_place(self):
        rail = Rail()
        incident = {"alert_id": hashlib.sha256(b"incident").hexdigest(), "identity": "OOMAQ-ALERT-1",
                    "telegram_chat_id": "44", "telegram_message_id": "901"}
        result = operate_owner_attention_queue([], environ=ENV, now=NOW, active_card_loader=rail.loader,
            evidence_recorder=rail.recorder, telegram_sender=rail.sender, telegram_editor=rail.editor,
            incident_loader=lambda _db: [incident])
        self.assertEqual(result["incident_resolutions"][0]["status"], "system_alert_resolved")
        self.assertEqual(rail.edits[-1][1], "901")
        self.assertEqual(rail.edits[-1][-1], {"inline_keyboard": []})

    def test_changed_system_alert_supersedes_old_card_without_false_recovery(self):
        rail = Rail()
        incident = {"alert_id": hashlib.sha256(b"old").hexdigest(), "identity": "OOMAQ-ALERT-OLD",
                    "telegram_chat_id": "44", "telegram_message_id": "901"}
        result = operate_owner_attention_queue([], sam_state={"state": "disabled",
            "affected_work_codes": ["current_eligible_enquiries"], "manual_coverage_required": True,
            "manual_coverage_reason_code": "sam_disabled"}, environ=ENV, now=NOW,
            active_card_loader=lambda _identity: ({"success": True, "card": {}}, 200), evidence_recorder=rail.recorder,
            telegram_sender=rail.sender, telegram_editor=rail.editor, incident_loader=lambda _db: [incident])
        self.assertEqual(result["incident_resolutions"][0]["status"], "system_alert_superseded")
        self.assertIn("newer system alert", rail.edits[-1][2])

    def test_prior_decision_is_proactively_expired_or_superseded_without_click(self):
        rail = Rail()
        prior = self._card()
        result = operate_owner_attention_queue([], environ=ENV, now=NOW, active_card_loader=rail.loader,
            evidence_recorder=rail.recorder, telegram_sender=rail.sender, telegram_editor=rail.editor,
            decision_loader=lambda _db: [prior])
        self.assertEqual(result["decision_expiries"][0]["status"], "decision_expired_in_place")
        self.assertEqual(result["decision_expiries"][0]["reason"], "chronology_or_evidence_superseded")
        self.assertEqual(rail.edits[-1][-1], {"inline_keyboard": []})

        expired = dict(prior, expires_at="2026-07-31T07:59:00+00:00")
        second = operate_owner_attention_queue([], environ=ENV, now=NOW, active_card_loader=rail.loader,
            evidence_recorder=rail.recorder, telegram_sender=rail.sender, telegram_editor=rail.editor,
            decision_loader=lambda _db: [expired])
        self.assertEqual(second["decision_expiries"][0]["reason"], "expired")

    def _card(self):
        rail = Rail()
        decision = {"requested_authority": "delivery_commitment", "expires_at": "2026-07-31T09:00:00+00:00",
                    "source_contract": "sam_delivery_owner_exception_v1",
                    "choices": [{"id": "approve", "label_code": "approve_delivery", "actionable": True,
                                 "outcome_code": "delivery_approved", "follow_up_trigger_code": "prepare_governed_reply"}]}
        result = operate_owner_attention_queue([disposition(owner_decision_required=True, owner_attention_decision=decision)],
            environ=ENV, now=NOW, active_card_loader=lambda identity: ({"success": True, "card": {}}, 200),
            evidence_recorder=rail.recorder, telegram_sender=rail.sender)
        card = result["queue"]["decision_cards"][0]
        card["telegram_message_id"] = "900"
        card["telegram_chat_id"] = "44"
        return card

    def test_changed_chronology_expires_and_removes_buttons(self):
        card = self._card()
        edits = []
        result, status = process_owner_attention_callback({"callback_data": f"sam_live_owner_decision:{card['decision_id']}:approve",
            "telegram_user_id": "77", "telegram_chat_id": "44", "telegram_message_id": "900"}, environ=ENV, now=NOW,
            evidence_loader=lambda *_: {"success": True, "card": card, "expected_owner_identity_hash": OWNER_HASH},
            current_binding_loader=lambda binding: dict(binding, latest_inbound_id="999"),
            telegram_editor=lambda *args: edits.append(args) or {"ok": True})
        self.assertEqual(status, 409)
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0][-1], {"inline_keyboard": []})

    def test_exact_once_consumption_edits_in_place_and_replay_is_silent(self):
        card = self._card()
        rail = Rail()
        result, status = process_owner_attention_callback({"callback_data": f"sam_live_owner_decision:{card['decision_id']}:approve",
            "telegram_user_id": "77", "telegram_chat_id": "44", "telegram_message_id": "900"}, environ=ENV, now=NOW,
            evidence_loader=lambda *_: {"success": True, "card": card, "expected_owner_identity_hash": OWNER_HASH}, current_binding_loader=lambda binding: binding,
            evidence_recorder=rail.recorder, telegram_editor=rail.editor)
        self.assertEqual(status, 200)
        self.assertEqual(result["follow_up_owner"], "SAM Livestock")
        self.assertEqual(rail.edits[0][-1], {"inline_keyboard": []})
        receipt = (rail.events[0]["review_json"])["owner_attention_receipt"]
        replay, replay_status = process_owner_attention_callback({"callback_data": f"sam_live_owner_decision:{card['decision_id']}:approve",
            "telegram_user_id": "77", "telegram_chat_id": "44", "telegram_message_id": "900"}, environ=ENV, now=NOW,
            evidence_loader=lambda *_: {"success": True, "card": card, "receipt": receipt, "expected_owner_identity_hash": OWNER_HASH},
            current_binding_loader=lambda binding: dict(binding, latest_inbound_id="changed"), telegram_editor=rail.editor)
        self.assertEqual(replay_status, 200)
        self.assertEqual(replay["status"], "owner_attention_callback_replay_noop")
        self.assertEqual(len(rail.edits), 1)

    def test_post_receipt_edit_failure_is_durable_and_repairable_without_second_decision(self):
        card = self._card()
        rail = Rail()
        failed, status = process_owner_attention_callback({"callback_data": f"sam_live_owner_decision:{card['decision_id']}:approve",
            "telegram_user_id": "77", "telegram_chat_id": "44", "telegram_message_id": "900"}, environ=ENV, now=NOW,
            evidence_loader=lambda *_: {"success": True, "card": card, "expected_owner_identity_hash": OWNER_HASH},
            current_binding_loader=lambda binding: binding, evidence_recorder=rail.recorder,
            telegram_editor=lambda *_: (_ for _ in ()).throw(OSError("ambiguous")))
        self.assertEqual(status, 503)
        self.assertTrue(failed["repair_required"])
        receipt = rail.events[0]["review_json"]["owner_attention_receipt"]
        repaired = repair_owner_attention_resolution(card, receipt, expected_owner_identity_hash=OWNER_HASH,
            environ=ENV, evidence_recorder=rail.recorder, telegram_editor=rail.editor)
        self.assertTrue(repaired["success"])
        self.assertEqual(len(rail.edits), 1)

    def test_invalid_choice_and_editor_exception_are_contained(self):
        card = self._card()
        invalid, invalid_status = process_owner_attention_callback({"callback_data": f"sam_live_owner_decision:{card['decision_id']}:forged",
            "telegram_user_id": "77", "telegram_chat_id": "44", "telegram_message_id": "900"}, environ=ENV, now=NOW,
            evidence_loader=lambda *_: {"success": True, "card": card, "expected_owner_identity_hash": OWNER_HASH},
            current_binding_loader=lambda binding: binding)
        self.assertEqual(invalid_status, 409)
        self.assertEqual(invalid["status"], "owner_attention_callback_evidence_invalid")

    def test_owner_and_telegram_identity_are_required(self):
        card = self._card()
        for payload, expected in (({"telegram_user_id": "88", "telegram_chat_id": "44", "telegram_message_id": "900"}, 403),
                                  ({"telegram_user_id": "77", "telegram_chat_id": "wrong", "telegram_message_id": "900"}, 409)):
            result, status = process_owner_attention_callback({"callback_data": f"sam_live_owner_decision:{card['decision_id']}:approve", **payload},
                environ=ENV, now=NOW, evidence_loader=lambda *_: {"success": True, "card": card, "expected_owner_identity_hash": OWNER_HASH})
            self.assertEqual(status, expected)
            self.assertFalse(result["calls_telegram"])


if __name__ == "__main__":
    unittest.main()
