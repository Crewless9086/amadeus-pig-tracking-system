import hashlib
import unittest

from modules.oom_sakkie.owner_attention_queue import (
    build_owner_attention_queue,
    build_resolved_card_edit,
    consume_decision_card,
    reassess_decision_card,
)

NOW = "2026-07-31T08:00:00+00:00"
START = "2026-07-31T07:00:00+00:00"
END = NOW
HASH = hashlib.sha256(b"evidence").hexdigest()
OWNER = hashlib.sha256(b"owner").hexdigest()


def observation(status="new_enquiry", inbound="in-1", sequence=1, observed="2026-07-31T07:30:00+00:00", **overrides):
    item = {"status": status, "account_id": "account-1", "inbox_id": "inbox-1", "contact_id": "contact-1",
            "conversation_id": "conversation-1", "latest_inbound_id": inbound, "observed_at": observed,
            "latest_inbound_at": "2026-07-31T07:20:00+00:00", "chronology_sequence": sequence}
    item.update(overrides)
    return item


def protected(**overrides):
    item = observation("owner_decision", "in-protected", evidence_packet_hash=HASH,
        requested_authority="delivery_commitment", expires_at="2026-07-31T09:00:00+00:00",
        telegram_message_id="telegram-44", choices=[
            {"id": "approve", "label_code": "approve_delivery", "actionable": True,
             "outcome_code": "delivery_approved", "follow_up_trigger_code": "prepare_governed_reply"},
            {"id": "invalid", "actionable": False}])
    item.update(overrides)
    return item


class OwnerAttentionQueueTests(unittest.TestCase):
    def build(self, items, **kwargs):
        return build_owner_attention_queue(items, period_start=START, period_end=END, now=NOW, **kwargs)

    def card(self):
        return self.build([protected()])["decision_cards"][0]

    def test_ordinary_messages_are_one_buttonless_summary_only(self):
        result = self.build([observation("automatically_answered")])
        self.assertEqual(result["ordinary_individual_notifications"], [])
        self.assertEqual(result["decision_cards"], [])
        self.assertEqual(result["summary"]["buttons"], [])
        self.assertEqual(result["summary"]["counts"]["automatically_answered_customers"], 1)

    def test_latest_conversation_state_wins_independent_of_input_order(self):
        old = observation("new_enquiry", "in-1", 1, "2026-07-31T07:15:00+00:00", latest_inbound_at="2026-07-31T07:10:00+00:00")
        new = observation("awaiting_customer", "in-2", 2, "2026-07-31T07:40:00+00:00", latest_inbound_at="2026-07-31T07:35:00+00:00")
        for items in ([old, new], [new, old]):
            counts = self.build(items)["summary"]["counts"]
            self.assertEqual(counts["new_enquiries"], 0)
            self.assertEqual(counts["awaiting_customers"], 1)

    def test_exact_duplicate_is_suppressed_and_tie_conflict_fails_closed(self):
        row = observation()
        self.assertEqual(self.build([row, dict(row)])["summary"]["counts"]["new_enquiries"], 1)
        with self.assertRaisesRegex(ValueError, "conflicting observations"):
            self.build([row, dict(row, status="awaiting_customer")])

    def test_chronology_sequence_rollback_and_same_sequence_new_inbound_fail_closed(self):
        first = observation(sequence=2, observed="2026-07-31T07:20:00+00:00")
        rollback = observation(sequence=1, observed="2026-07-31T07:40:00+00:00")
        with self.assertRaisesRegex(ValueError, "rollback"):
            self.build([first, rollback])
        with self.assertRaisesRegex(ValueError, "conflicting observations"):
            self.build([first, dict(first, latest_inbound_id="in-other")])

    def test_out_of_period_or_future_chronology_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "proven period"):
            self.build([observation(observed="2026-07-31T08:01:00+00:00")])

    def test_decision_is_derived_bound_and_same_build_deduplicated(self):
        card = self.card()
        self.assertEqual(card["binding"]["evidence_packet_hash"], HASH)
        self.assertTrue(card["decision_id"].startswith("oaq_"))
        self.assertLessEqual(len(card["buttons"][0]["callback_data"].encode()), 64)
        duplicate = self.build([protected(), dict(protected())])
        self.assertEqual(len(duplicate["decision_cards"]), 1)
        self.assertEqual(self.build([protected()], existing_decision_ids=[card["decision_id"]])["decision_cards"], [])

    def test_changed_evidence_derives_a_different_decision(self):
        first = self.card()
        second = self.build([protected(evidence_packet_hash=hashlib.sha256(b"new").hexdigest())])["decision_cards"][0]
        self.assertNotEqual(first["decision_id"], second["decision_id"])

    def test_forged_card_or_partial_binding_fails_closed(self):
        card = self.card()
        forged = dict(card, requested_authority="reservation")
        with self.assertRaisesRegex(ValueError, "invalid"):
            reassess_decision_card(forged, card["binding"], expected_card_digest=card["card_digest"], now=NOW)
        with self.assertRaises(ValueError):
            reassess_decision_card(card, {"account_id": "account-1"}, expected_card_digest=card["card_digest"], now=NOW)

    def test_only_explicit_boolean_actionable_choice_becomes_a_button(self):
        for value in (None, "true", 1):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "actionable choices"):
                self.build([protected(choices=[{"id": "approve", "label_code": "approve_delivery",
                    "actionable": value, "outcome_code": "delivery_approved",
                    "follow_up_trigger_code": "prepare_governed_reply"}])])

    def test_changed_chronology_or_expiry_prepares_button_removal(self):
        card = self.card()
        changed = dict(card["binding"], latest_inbound_id="in-new")
        result = reassess_decision_card(card, changed, expected_card_digest=card["card_digest"], now=NOW)
        self.assertEqual(result["edit_intent"]["reason_code"], "chronology_or_evidence_changed")
        self.assertEqual(result["edit_intent"]["buttons"], [])
        expired = reassess_decision_card(card, card["binding"], expected_card_digest=card["card_digest"], now=card["expires_at"])
        self.assertEqual(expired["edit_intent"]["reason_code"], "expired")

    def test_consumption_requires_trusted_owner_and_prepares_zero_io_atomic_intent(self):
        card = self.card()
        with self.assertRaisesRegex(ValueError, "bound owner"):
            consume_decision_card(card, choice="approve", actor_identity_hash=hashlib.sha256(b"other").hexdigest(),
                expected_owner_identity_hash=OWNER, expected_card_digest=card["card_digest"], current_binding=card["binding"], now=NOW)
        result = consume_decision_card(card, choice="approve", actor_identity_hash=OWNER,
            expected_owner_identity_hash=OWNER, expected_card_digest=card["card_digest"], current_binding=card["binding"], now=NOW)
        self.assertTrue(result["atomic_consumption_intent"]["requires_atomic_unique_receipt"])
        self.assertEqual(result["writes_performed"], 0)
        self.assertEqual(result["telegram_calls_performed"], 0)

    def test_authoritative_receipt_builds_one_in_place_buttonless_edit_and_replay_noop(self):
        card = self.card()
        intent = consume_decision_card(card, choice="approve", actor_identity_hash=OWNER,
            expected_owner_identity_hash=OWNER, expected_card_digest=card["card_digest"], current_binding=card["binding"], now=NOW)
        atom = intent["atomic_consumption_intent"]
        receipt = {"status": "consumed", "receipt_id": "receipt-1", "decision_id": card["decision_id"],
                   "card_digest": card["card_digest"], "choice_id": "approve", "replay_key": atom["replay_key"],
                   "actor_identity_hash": OWNER}
        edit = build_resolved_card_edit(card, receipt, expected_card_digest=card["card_digest"],
                                        expected_owner_identity_hash=OWNER, expected_replay_key=atom["replay_key"])
        self.assertEqual(edit["edit_intent"]["telegram_message_id"], "telegram-44")
        self.assertEqual(edit["edit_intent"]["buttons"], [])
        replay = consume_decision_card(card, choice="approve", actor_identity_hash=OWNER,
            expected_owner_identity_hash=OWNER, expected_card_digest=card["card_digest"], current_binding=card["binding"],
            existing_consumption_receipt=receipt, now=NOW)
        self.assertEqual(replay["status"], "decision_replay_noop")
        self.assertEqual(replay["writes_performed"], 0)

    def test_consumed_replay_is_noop_even_after_expiry_or_chronology_change(self):
        card = self.card()
        intent = consume_decision_card(card, choice="approve", actor_identity_hash=OWNER,
            expected_owner_identity_hash=OWNER, expected_card_digest=card["card_digest"], current_binding=card["binding"], now=NOW)
        atom = intent["atomic_consumption_intent"]
        receipt = {"status": "consumed", "receipt_id": "receipt-1", "decision_id": card["decision_id"],
            "card_digest": card["card_digest"], "choice_id": "approve", "replay_key": atom["replay_key"],
            "actor_identity_hash": OWNER}
        for current, timestamp in ((card["binding"], card["expires_at"]),
                                   (dict(card["binding"], latest_inbound_id="in-new"), NOW)):
            replay = consume_decision_card(card, choice="approve", actor_identity_hash=OWNER,
                expected_owner_identity_hash=OWNER, expected_card_digest=card["card_digest"], current_binding=current,
                existing_consumption_receipt=receipt, now=timestamp)
            self.assertEqual(replay["status"], "decision_replay_noop")
            self.assertNotIn("edit_intent", replay)
            self.assertEqual(replay["telegram_calls_performed"], 0)

    def test_system_alert_is_typed_buttonless_and_dedupes_across_periods(self):
        state = {"state": "systemically_contained", "affected_work_codes": ["current_eligible_enquiries"],
                 "manual_coverage_required": True, "manual_coverage_reason_code": "systemic_containment"}
        first = self.build([], sam_state=state)
        alert = first["system_alerts"][0]
        self.assertEqual(alert["buttons"], [])
        second = build_owner_attention_queue([], period_start="2026-07-31T08:00:00+00:00", period_end="2026-07-31T09:00:00+00:00",
            now="2026-07-31T09:00:00+00:00", sam_state=state, existing_alert_ids=[alert["alert_id"]])
        self.assertEqual(second["system_alerts"], [])

    def test_alert_requires_safe_affected_scope_and_consistent_coverage(self):
        with self.assertRaises(ValueError):
            self.build([], sam_state={"state": "disabled"})
        with self.assertRaises(ValueError):
            self.build([], sam_state={"state": "disabled", "affected_work_codes": ["customer@example.com"],
                "manual_coverage_required": False, "manual_coverage_reason_code": "sam_disabled"})
        with self.assertRaisesRegex(ValueError, "boolean"):
            self.build([], sam_state={"state": "disabled", "affected_work_codes": ["current_livestock_inbox"],
                "manual_coverage_required": "false", "manual_coverage_reason_code": "no_manual_cover_safe"})

    def test_one_summary_per_period_edits_only_matching_message(self):
        first = self.build([])["summary"]
        second = self.build([], existing_summary={"summary_id": first["summary_id"], "telegram_message_id": "message-1"})["summary"]
        self.assertEqual(second["telegram_intent"], "edit_existing_summary")
        self.assertEqual(second["telegram_message_id"], "message-1")

    def test_kernel_has_zero_authority(self):
        self.assertTrue(all(value is False for value in self.build([protected()])["authority"].values()))


if __name__ == "__main__":
    unittest.main()
