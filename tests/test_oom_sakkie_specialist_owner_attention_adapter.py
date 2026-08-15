import hashlib
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from modules.oom_sakkie.owner_attention_adapter import (
    operate_owner_attention_queue,
    operate_specialist_owner_decision,
    process_owner_attention_callback,
    repair_specialist_owner_attention_resolution,
)
from modules.oom_sakkie.specialist_owner_decisions import (
    beacon_organic_publication_binding,
    rootline_supervised_commissioning_binding,
    specialist_choice,
)


NOW = datetime(2026, 8, 1, 5, 0, tzinfo=timezone.utc)
ENV = {"OOM_SAKKIE_OWNER_ATTENTION_QUEUE_ENABLED": "1", "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token",
       "SAM_LIVE_STOCK_TELEGRAM_OWNER_CHAT_ID": "44", "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "77,88",
       "OOM_SAKKIE_OWNER_ATTENTION_OWNER_USER_ID": "77", "DATABASE_URL": "postgres://unused"}
OWNER_HASH = hashlib.sha256(b'{"telegram_owner_id":"77"}').hexdigest()
PREVIEW = "https://example.test/private-preview?expires=1&token=opaque"


class Rail:
    def __init__(self):
        self.events, self.sends, self.edits = [], [], []
        self.owner_card = {}

    def active_loader(self, _identity):
        return {"success": True, "card": dict(self.owner_card)}, 200

    def recorder(self, event):
        created = not any(row.get("review_event_id") == event.get("review_event_id") for row in self.events)
        if created:
            self.events.append(event)
        owner = (event.get("review_json") or {}).get("owner_card") or {}
        if created and owner.get("state") == "active":
            self.owner_card = dict(owner)
        return {"success": True, "created": created, "review_event_id": event.get("review_event_id")}, 200

    def sender(self, _token, chat_id, text, markup):
        self.sends.append((chat_id, text, markup))
        return {"ok": True, "result": {"message_id": "901"}}

    def editor(self, _token, chat_id, message_id, text, markup):
        self.edits.append((chat_id, message_id, text, markup))
        return {"ok": True, "result": {"message_id": message_id}}

    def delivered(self):
        review = next(row["review_json"] for row in reversed(self.events)
                      if (row.get("review_json") or {}).get("owner_card", {}).get("state") == "active")
        item = dict(review["owner_attention"]["item"])
        item["telegram_chat_id"] = review["owner_card"]["telegram_chat_id"]
        item["telegram_message_id"] = review["owner_card"]["telegram_message_id"]
        return {"success": True, "card": item,
                "expected_owner_identity_hash": review["owner_attention"]["expected_owner_identity_hash"]}


class SpecialistOwnerAttentionAdapterTests(unittest.TestCase):
    def binding(self):
        return beacon_organic_publication_binding(preview_reference=PREVIEW,
            expires_at="2026-08-01T10:00:00+02:00")

    def test_delivery_is_one_card_and_replay_creates_no_additional_card(self):
        rail, binding = Rail(), self.binding()
        missing = lambda *_: {"success": False, "status": "owner_attention_card_not_found"}
        first = operate_specialist_owner_decision(binding, environ=ENV, now=NOW,
            chronology_loader=lambda valid, _source: valid["chronology_binding"], specialist_card_loader=missing,
            active_card_loader=rail.active_loader, evidence_recorder=rail.recorder, telegram_sender=rail.sender)
        self.assertTrue(first["success"])
        self.assertEqual(len(rail.sends), 1)
        self.assertIn("🐷", rail.sends[0][1])
        self.assertEqual(len(rail.sends[0][2]["inline_keyboard"]), 3)
        loaded = rail.delivered()
        replay = operate_specialist_owner_decision(binding, environ=ENV, now=NOW,
            chronology_loader=lambda valid, _source: valid["chronology_binding"],
            specialist_card_loader=lambda *_: loaded, active_card_loader=rail.active_loader,
            evidence_recorder=rail.recorder, telegram_sender=rail.sender)
        self.assertEqual(replay["status"], "specialist_owner_decision_duplicate_withheld")
        self.assertEqual(len(rail.sends), 1)

    def test_changed_chronology_sends_nothing(self):
        rail, binding = Rail(), self.binding()
        changed = dict(binding["chronology_binding"], publication_authorization_count=1)
        result = operate_specialist_owner_decision(binding, environ=ENV, now=NOW,
            chronology_loader=lambda *_: changed, specialist_card_loader=lambda *_: {},
            active_card_loader=rail.active_loader, evidence_recorder=rail.recorder, telegram_sender=rail.sender)
        self.assertEqual(result["status"], "specialist_owner_decision_stale")
        self.assertEqual(rail.sends, [])

    def test_normal_sam_cycle_does_not_expire_current_beacon_card(self):
        rail, binding = Rail(), self.binding()
        operate_specialist_owner_decision(binding, environ=ENV, now=NOW,
            chronology_loader=lambda valid, _source: valid["chronology_binding"],
            specialist_card_loader=lambda *_: {"success": False}, active_card_loader=rail.active_loader,
            evidence_recorder=rail.recorder, telegram_sender=rail.sender)
        loaded = rail.delivered()["card"]
        sam_edits = []
        operate_owner_attention_queue([], environ=ENV, now=NOW,
            active_card_loader=lambda _identity: ({"success": True, "card": {}}, 200),
            evidence_recorder=rail.recorder, telegram_sender=rail.sender,
            telegram_editor=lambda *args: sam_edits.append(args) or {"ok": True},
            decision_loader=lambda _db: [loaded])
        self.assertEqual(sam_edits, [])

    def test_specialist_rerun_proactively_expires_buttons_when_chronology_changes(self):
        rail, binding = Rail(), self.binding()
        operate_specialist_owner_decision(binding, environ=ENV, now=NOW,
            chronology_loader=lambda valid, _source: valid["chronology_binding"],
            specialist_card_loader=lambda *_: {"success": False}, active_card_loader=rail.active_loader,
            evidence_recorder=rail.recorder, telegram_sender=rail.sender)
        loaded = rail.delivered()
        changed = dict(binding["chronology_binding"], publication_authorization_count=1)
        result = operate_specialist_owner_decision(binding, environ=ENV, now=NOW,
            chronology_loader=lambda *_: changed, specialist_card_loader=lambda *_: loaded,
            evidence_recorder=rail.recorder, telegram_editor=rail.editor)
        self.assertEqual(result["status"], "decision_expired")
        self.assertEqual(rail.edits[-1][-1], {"inline_keyboard": []})
        self.assertEqual(rail.events[-1]["review_json"]["owner_card"]["state"], "expired")

    def test_specialist_rerun_proactively_expires_buttons_when_clock_expires(self):
        rail, binding = Rail(), self.binding()
        operate_specialist_owner_decision(binding, environ=ENV, now=NOW,
            chronology_loader=lambda valid, _source: valid["chronology_binding"],
            specialist_card_loader=lambda *_: {"success": False}, active_card_loader=rail.active_loader,
            evidence_recorder=rail.recorder, telegram_sender=rail.sender)
        loaded = rail.delivered()
        result = operate_specialist_owner_decision(binding, environ=ENV,
            now=datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc),
            chronology_loader=lambda valid, _source: valid["chronology_binding"],
            specialist_card_loader=lambda *_: loaded, evidence_recorder=rail.recorder, telegram_editor=rail.editor)
        self.assertEqual(result["status"], "decision_expired")
        self.assertEqual(rail.events[-1]["review_json"]["owner_card"]["action"], "expired")

    def test_exact_once_consumption_edits_in_place_and_notifies_beacon_without_publishing(self):
        rail, binding = Rail(), self.binding()
        operate_specialist_owner_decision(binding, environ=ENV, now=NOW,
            chronology_loader=lambda valid, _source: valid["chronology_binding"],
            specialist_card_loader=lambda *_: {"success": False}, active_card_loader=rail.active_loader,
            evidence_recorder=rail.recorder, telegram_sender=rail.sender)
        loaded = rail.delivered()
        token = loaded["card"]["decision_id"]
        payload = {"callback_data": f"sam_live_owner_decision:{token}:approve", "telegram_user_id": "77",
                   "telegram_chat_id": "44", "telegram_message_id": "901"}
        result, status = process_owner_attention_callback(payload, environ=ENV, now=NOW,
            evidence_loader=lambda *_: loaded,
            current_binding_loader=lambda valid: valid["chronology_binding"],
            evidence_recorder=rail.recorder, telegram_editor=rail.editor)
        self.assertEqual(status, 200)
        self.assertEqual(result["follow_up_owner"], "BEACON")
        self.assertFalse(result["publishes"])
        self.assertEqual(rail.edits[-1][-1], {"inline_keyboard": []})
        receipt = next(row["review_json"]["owner_attention_receipt"] for row in rail.events
                       if "owner_attention_receipt" in row.get("review_json", {}))
        replay_loaded = {**loaded, "receipt": receipt}
        replay, replay_status = process_owner_attention_callback(payload, environ=ENV, now=NOW,
            evidence_loader=lambda *_: replay_loaded,
            current_binding_loader=lambda valid: dict(valid["chronology_binding"], publication_authorization_count=1),
            evidence_recorder=rail.recorder, telegram_editor=rail.editor)
        self.assertEqual(replay_status, 200)
        self.assertEqual(replay["status"], "owner_attention_callback_replay_noop")
        self.assertEqual(len(rail.edits), 1)

    def test_expired_buttons_are_removed_without_outcome_callback(self):
        rail, binding = Rail(), self.binding()
        operate_specialist_owner_decision(binding, environ=ENV, now=NOW,
            chronology_loader=lambda valid, _source: valid["chronology_binding"],
            specialist_card_loader=lambda *_: {"success": False}, active_card_loader=rail.active_loader,
            evidence_recorder=rail.recorder, telegram_sender=rail.sender)
        loaded = rail.delivered()
        payload = {"callback_data": f"sam_live_owner_decision:{loaded['card']['decision_id']}:decline",
                   "telegram_user_id": "77", "telegram_chat_id": "44", "telegram_message_id": "901"}
        result, status = process_owner_attention_callback(payload, environ=ENV,
            now=datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc), evidence_loader=lambda *_: loaded,
            current_binding_loader=lambda valid: valid["chronology_binding"],
            evidence_recorder=rail.recorder, telegram_editor=rail.editor)
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "decision_expired")
        self.assertEqual(rail.edits[-1][-1], {"inline_keyboard": []})
        terminal = rail.events[-1]["review_json"]["owner_card"]
        self.assertEqual(terminal["state"], "expired")
        self.assertEqual(terminal["telegram_message_id"], "901")

    def test_post_receipt_edit_failure_has_specialist_repair_path(self):
        rail, binding = Rail(), self.binding()
        operate_specialist_owner_decision(binding, environ=ENV, now=NOW,
            chronology_loader=lambda valid, _source: valid["chronology_binding"],
            specialist_card_loader=lambda *_: {"success": False}, active_card_loader=rail.active_loader,
            evidence_recorder=rail.recorder, telegram_sender=rail.sender)
        loaded = rail.delivered()
        payload = {"callback_data": f"sam_live_owner_decision:{loaded['card']['decision_id']}:approve",
                   "telegram_user_id": "77", "telegram_chat_id": "44", "telegram_message_id": "901"}
        failed, status = process_owner_attention_callback(payload, environ=ENV, now=NOW,
            evidence_loader=lambda *_: loaded, current_binding_loader=lambda valid: valid["chronology_binding"],
            evidence_recorder=rail.recorder,
            telegram_editor=lambda *_: (_ for _ in ()).throw(OSError("ambiguous")))
        self.assertEqual(status, 503)
        self.assertTrue(failed["repair_required"])
        receipt = next(row["review_json"]["owner_attention_receipt"] for row in rail.events
                       if "owner_attention_receipt" in row.get("review_json", {}))
        repaired = repair_specialist_owner_attention_resolution(loaded["card"], receipt, environ=ENV,
            evidence_loader=lambda *_: {**loaded, "receipt": receipt},
            evidence_recorder=rail.recorder, telegram_editor=rail.editor)
        self.assertTrue(repaired["success"])
        self.assertEqual(repaired["follow_up_owner"], "BEACON")
        self.assertEqual(rail.edits[-1][-1], {"inline_keyboard": []})

        for target, field, value in (
            ("card", "telegram_chat_id", "999"), ("card", "telegram_message_id", "999"),
            ("card", "decision_id", "forged"), ("card", "card_digest", "a" * 64),
            ("receipt", "replay_key", "b" * 64), ("receipt", "receipt_id", "OOMAQ-RECEIPT-forged"),
            ("receipt", "actor_identity_hash", "c" * 64),
        ):
            forged_card, forged_receipt = dict(loaded["card"]), dict(receipt)
            (forged_card if target == "card" else forged_receipt)[field] = value
            edit_count = len(rail.edits)
            rejected = repair_specialist_owner_attention_resolution(forged_card, forged_receipt, environ=ENV,
                evidence_loader=lambda *_: {**loaded, "receipt": receipt},
                evidence_recorder=rail.recorder, telegram_editor=rail.editor)
            with self.subTest(target=target, field=field):
                self.assertFalse(rejected["success"])
                self.assertEqual(len(rail.edits), edit_count)


if __name__ == "__main__":
    unittest.main()


class RootlineCommissioningOwnerDecisionTests(unittest.TestCase):
    def binding(self):
        return rootline_supervised_commissioning_binding(expires_at="2026-08-03T12:00:00+02:00")

    def test_exact_rootline_decision_delivers_once_without_hardware_authority(self):
        rail, binding = Rail(), self.binding()
        missing = lambda *_: {"success": False, "status": "owner_attention_card_not_found"}
        first = operate_specialist_owner_decision(
            binding, environ=ENV, now=NOW,
            chronology_loader=lambda valid, _source: valid["chronology_binding"],
            specialist_card_loader=missing, active_card_loader=rail.active_loader,
            evidence_recorder=rail.recorder, telegram_sender=rail.sender,
        )
        self.assertTrue(first["success"])
        self.assertEqual(len(rail.sends), 1)
        self.assertIn("SUPERVISED COMMISSIONING DECISION", rail.sends[0][1])
        self.assertIn("not irrigation", rail.sends[0][1])
        self.assertEqual(len(rail.sends[0][2]["inline_keyboard"]), 2)
        authority = specialist_choice(binding, "authorize")
        self.assertEqual(authority["specialist_callback"], "prepare_supervised_commissioning_handover")
        self.assertFalse(authority["publish"])
        self.assertNotIn("hardware_action", authority)
        loaded = rail.delivered()
        replay = operate_specialist_owner_decision(
            binding, environ=ENV, now=NOW,
            chronology_loader=lambda valid, _source: valid["chronology_binding"],
            specialist_card_loader=lambda *_: loaded,
            active_card_loader=rail.active_loader, evidence_recorder=rail.recorder,
            telegram_sender=rail.sender,
        )
        self.assertEqual(replay["status"], "specialist_owner_decision_duplicate_withheld")
        self.assertEqual(len(rail.sends), 1)

    def test_changed_rootline_chronology_sends_nothing(self):
        rail, binding = Rail(), self.binding()
        changed = dict(binding["chronology_binding"], commissioning_authorization_count=1)
        result = operate_specialist_owner_decision(
            binding, environ=ENV, now=NOW, chronology_loader=lambda *_: changed,
            specialist_card_loader=lambda *_: {}, active_card_loader=rail.active_loader,
            evidence_recorder=rail.recorder, telegram_sender=rail.sender,
        )
        self.assertEqual(result["status"], "specialist_owner_decision_stale")
        self.assertEqual(rail.sends, [])

def _chronology_database_count(count):
    connection = MagicMock()
    cursor = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.return_value = (count,)
    return connection


class RootlineDefaultChronologyTests(unittest.TestCase):
    def binding(self):
        return rootline_supervised_commissioning_binding(expires_at="2026-08-03T12:00:00+02:00")

    def test_default_delivery_reads_authoritative_receipt_count(self):
        rail, binding = Rail(), self.binding()
        with patch("psycopg.connect", return_value=_chronology_database_count(1)):
            result = operate_specialist_owner_decision(
                binding, environ=ENV, now=NOW,
                specialist_card_loader=lambda *_: {}, active_card_loader=rail.active_loader,
                evidence_recorder=rail.recorder, telegram_sender=rail.sender,
            )
        self.assertEqual(result["status"], "specialist_owner_decision_stale")
        self.assertEqual(rail.sends, [])

    def test_default_callback_expires_when_authorization_already_exists(self):
        rail, binding = Rail(), self.binding()
        operate_specialist_owner_decision(
            binding, environ=ENV, now=NOW,
            chronology_loader=lambda valid, _source: valid["chronology_binding"],
            specialist_card_loader=lambda *_: {"success": False},
            active_card_loader=rail.active_loader, evidence_recorder=rail.recorder,
            telegram_sender=rail.sender,
        )
        loaded = rail.delivered()
        token = loaded["card"]["decision_id"]
        payload = {"callback_data": f"sam_live_owner_decision:{token}:authorize",
                   "telegram_user_id": "77", "telegram_chat_id": "44", "telegram_message_id": "901"}
        with patch("psycopg.connect", return_value=_chronology_database_count(1)):
            result, status = process_owner_attention_callback(
                payload, environ=ENV, now=NOW, evidence_loader=lambda *_: loaded,
                evidence_recorder=rail.recorder, telegram_editor=rail.editor,
            )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "decision_expired")
        self.assertEqual(rail.edits[-1][-1], {"inline_keyboard": []})