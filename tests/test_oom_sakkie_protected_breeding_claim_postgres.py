import os
import unittest
import uuid
from datetime import datetime, timezone

import psycopg

from modules.oom_sakkie.protected_action_claims import (
    bind_claim_card, claim_callback, complete_claim, create_claim,
)


URL = os.getenv("OOM_PROTECTED_ACTION_POSTGRES_URL", "").strip()


@unittest.skipUnless(URL, "disposable PostgreSQL URL is required")
class ProtectedBreedingClaimPostgresTests(unittest.TestCase):
    def connect(self):
        return psycopg.connect(URL)

    def setUp(self):
        self.suffix = uuid.uuid4().hex

    def tearDown(self):
        with self.connect() as db, db.cursor() as cur:
            cur.execute("delete from app_private.oom_protected_action_claims where mission_id=%s",
                        ("MISSION-" + self.suffix,))

    def test_create_claim_confirm_complete_and_replay_once(self):
        mission = "MISSION-" + self.suffix
        provider = "MSG-" + self.suffix
        payload = {"success": True, "preview_sha256": "HERD-" + self.suffix,
                   "preview": {"row_count": 1, "rows": [{"pig_id": "PIG-1",
                       "action": "near_farrowing", "observed_at": "2026-08-12T11:41:25Z",
                       "factual_note": "Owner observation."}]}}
        claim = create_claim(action_kind="herdmaster_breeding_grouped",
            owner_user_id="5721652188", private_chat_id="5721652188",
            mission_id=mission, provider_message_id=provider,
            evidence_generation="GEN-" + self.suffix, preview_payload=payload,
            connect_factory=self.connect)
        self.assertTrue(claim["success"])
        self.assertTrue(bind_claim_card(claim["callback_token"], "3553",
                                        connect_factory=self.connect))
        callback = f"oompa:{claim['callback_token']}:confirm"
        claimed, status = claim_callback(callback, owner_user_id="5721652188",
            private_chat_id="5721652188", provider_message_id="CALLBACK-" + self.suffix,
            provider_timestamp=datetime.now(timezone.utc).isoformat(),
            source_card_message_id="3553", connect_factory=self.connect)
        self.assertEqual(status, 200)
        self.assertEqual(claimed["status"], "protected_callback_claimed")
        complete_claim(claim["callback_token"], {"success": True, "rows_changed": 1},
                       connect_factory=self.connect)
        replay, replay_status = claim_callback(callback, owner_user_id="5721652188",
            private_chat_id="5721652188", provider_message_id="CALLBACK-REPLAY-" + self.suffix,
            provider_timestamp=datetime.now(timezone.utc).isoformat(),
            source_card_message_id="3553", connect_factory=self.connect)
        self.assertEqual(replay_status, 200)
        self.assertEqual(replay["status"], "protected_callback_replayed_noop")
        self.assertEqual(replay["telegram_sends"], 0)
        self.assertEqual(replay["telegram_edits"], 0)

    def test_exact_executing_receipt_can_be_recovered_but_other_identity_cannot(self):
        mission = "MISSION-" + self.suffix
        provider = "MSG-" + self.suffix
        payload = {"success": True, "preview_sha256": "HERD-" + self.suffix,
                   "preview": {"row_count": 1, "rows": [{"pig_id": "PIG-1",
                       "action": "near_farrowing", "observed_at": "2026-08-12T11:41:25Z",
                       "factual_note": "Owner observation."}]}}
        claim = create_claim(action_kind="herdmaster_breeding_grouped",
            owner_user_id="5721652188", private_chat_id="5721652188",
            mission_id=mission, provider_message_id=provider,
            evidence_generation="GEN-" + self.suffix, preview_payload=payload,
            connect_factory=self.connect)
        self.assertTrue(bind_claim_card(claim["callback_token"], "3566", connect_factory=self.connect))
        callback = f"oompa:{claim['callback_token']}:confirm"
        confirmed_at = datetime.now(timezone.utc).isoformat()
        first, status = claim_callback(callback, owner_user_id="5721652188",
            private_chat_id="5721652188", provider_message_id="CALLBACK-" + self.suffix,
            provider_timestamp=confirmed_at, source_card_message_id="3566",
            connect_factory=self.connect)
        self.assertEqual(status, 200)
        recovered, recovery_status = claim_callback(callback, owner_user_id="5721652188",
            private_chat_id="5721652188", provider_message_id="CALLBACK-" + self.suffix,
            provider_timestamp=confirmed_at, source_card_message_id="3566",
            connect_factory=self.connect)
        self.assertEqual(recovery_status, 200)
        self.assertEqual(recovered["status"], "protected_callback_recovered")
        rejected, rejected_status = claim_callback(callback, owner_user_id="5721652188",
            private_chat_id="5721652188", provider_message_id="OTHER-CALLBACK",
            provider_timestamp=confirmed_at, source_card_message_id="3566",
            connect_factory=self.connect)
        self.assertEqual(rejected_status, 409)
        self.assertEqual(rejected["status"], "protected_callback_stale")


if __name__ == "__main__":
    unittest.main()
