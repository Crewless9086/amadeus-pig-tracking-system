import os
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import psycopg

from modules.oom_sakkie.protected_action_claims import (
    bind_claim_card, claim_callback, complete_claim, create_claim,
)
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.protected_action_runtime import handle_protected_action_input


URL = os.getenv("OOM_PROTECTED_ACTION_POSTGRES_URL", "").strip()


@unittest.skipUnless(URL, "disposable PostgreSQL URL is required")
class ProtectedBreedingClaimPostgresTests(unittest.TestCase):
    def connect(self):
        return psycopg.connect(URL)

    def setUp(self):
        self.suffix = uuid.uuid4().hex
        # The PR workflow definition is loaded from the protected base branch,
        # so this disposable suite applies and therefore tests the new migration
        # before exercising its new action kind.
        with self.connect() as db, db.cursor() as cur:
            for name in ("202608210001_create_green_print_jobs.sql",
                         "202608220002_allow_herdmaster_farrowing_protected_claims.sql",
                         "202608260001_allow_herdmaster_litter_actions_protected_claims.sql"):
                migration = Path("supabase/migrations") / name
                cur.execute(migration.read_text(encoding="utf-8"))

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

    def test_litter_first_treatment_action_kind_is_admitted(self):
        claim=create_claim(action_kind="herdmaster_record_litter_first_treatment",
            owner_user_id="5721652188",private_chat_id="5721652188",
            mission_id="MISSION-"+self.suffix,provider_message_id="MSG-"+self.suffix,
            evidence_generation="GEN-"+self.suffix,
            preview_payload={"contract_version":"herdmaster_litter_first_treatment_v1"},
            connect_factory=self.connect)
        self.assertTrue(claim["success"])
        self.assertEqual(claim["action_kind"],"herdmaster_record_litter_first_treatment")

    def test_exact_expired_active_claim_is_rearmed_without_new_token_or_card(self):
        mission="MISSION-"+self.suffix
        payload={"contract_version":"beacon_private_album_review_v1","album_digest":"d"*64}
        claim=create_claim(action_kind="beacon_media_review",owner_user_id="5721652188",
            private_chat_id="5721652188",mission_id=mission,provider_message_id="CANONICAL-"+self.suffix,
            evidence_generation="d"*64,preview_payload=payload,ttl_minutes=1,
            connect_factory=self.connect)
        self.assertTrue(bind_claim_card(claim["callback_token"],"3637",connect_factory=self.connect))
        with self.connect() as db,db.cursor() as cur:
            cur.execute("update app_private.oom_protected_action_claims set expires_at=now()-interval '1 minute' where callback_token=%s",
                (claim["callback_token"],))
        rearmed=create_claim(action_kind="beacon_media_review",owner_user_id="5721652188",
            private_chat_id="5721652188",mission_id=mission,provider_message_id="CANONICAL-"+self.suffix,
            evidence_generation="d"*64,preview_payload=payload,ttl_minutes=10080,
            connect_factory=self.connect)
        self.assertEqual(rearmed["status"],"protected_claim_rearmed")
        self.assertEqual(rearmed["callback_token"],claim["callback_token"])
        self.assertEqual(rearmed["preview_card_message_id"],"3637")
        with self.connect() as db,db.cursor() as cur:
            cur.execute("update app_private.oom_protected_action_claims set status='expired' where callback_token=%s",
                (claim["callback_token"],))
        clicked_expired=create_claim(action_kind="beacon_media_review",owner_user_id="5721652188",
            private_chat_id="5721652188",mission_id=mission,provider_message_id="CANONICAL-"+self.suffix,
            evidence_generation="d"*64,preview_payload=payload,ttl_minutes=10080,
            connect_factory=self.connect)
        self.assertEqual(clicked_expired["status"],"protected_claim_rearmed")
        self.assertEqual(clicked_expired["callback_token"],claim["callback_token"])

    def test_expired_non_beacon_claim_is_not_rearmed(self):
        mission="MISSION-"+self.suffix
        payload={"plan":"protected"}
        claim=create_claim(action_kind="rootline_irrigation_segment",owner_user_id="5721652188",
            private_chat_id="5721652188",mission_id=mission,provider_message_id="MSG-"+self.suffix,
            evidence_generation="GEN-"+self.suffix,preview_payload=payload,ttl_minutes=1,
            connect_factory=self.connect)
        with self.connect() as db,db.cursor() as cur:
            cur.execute("update app_private.oom_protected_action_claims set status='expired' where callback_token=%s",
                (claim["callback_token"],))
        with self.assertRaises(RuntimeError):
            create_claim(action_kind="rootline_irrigation_segment",owner_user_id="5721652188",
                private_chat_id="5721652188",mission_id=mission,provider_message_id="MSG-"+self.suffix,
                evidence_generation="GEN-"+self.suffix,preview_payload=payload,ttl_minutes=30,
                connect_factory=self.connect)

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
        wrong_action, wrong_action_status = claim_callback(
            f"oompa:{claim['callback_token']}:cancel",
            owner_user_id="5721652188", private_chat_id="5721652188",
            provider_message_id="CALLBACK-" + self.suffix,
            provider_timestamp=confirmed_at, source_card_message_id="3566",
            connect_factory=self.connect)
        self.assertEqual(wrong_action_status, 409)
        self.assertEqual(wrong_action["status"], "protected_callback_stale")
        missing_card, missing_card_status = claim_callback(callback,
            owner_user_id="5721652188", private_chat_id="5721652188",
            provider_message_id="CALLBACK-" + self.suffix,
            provider_timestamp=confirmed_at, source_card_message_id="",
            connect_factory=self.connect)
        self.assertEqual(missing_card_status, 409)
        self.assertEqual(missing_card["status"], "protected_callback_card_mismatch")

    def test_litter_loss_commit_then_completion_failure_recovers_exactly_once(self):
        mission="MISSION-"+self.suffix
        operation="HERD-LITTER-LOSS-"+self.suffix.upper()
        payload={"contract_version":"herdmaster_litter_piglet_deaths_v1",
            "owner_user_id":"5721652188","private_chat_id":"5721652188",
            "litter_id":"L1","event_date":"2026-08-26","reason":"Unknown",
            "operation_id":operation,"pig_ids":["P1","P2","P3"]}
        claim=create_claim(action_kind="herdmaster_record_litter_piglet_deaths",
            owner_user_id="5721652188",private_chat_id="5721652188",mission_id=mission,
            provider_message_id="MSG-"+self.suffix,evidence_generation="GEN-"+self.suffix,
            preview_payload=payload,connect_factory=self.connect)
        self.assertTrue(bind_claim_card(claim["callback_token"],"CARD-"+self.suffix,
                                        connect_factory=self.connect))
        receipt="CALLBACK-"+self.suffix
        stamp=datetime.now(timezone.utc).isoformat()
        parsed={"telegram_user_id":"5721652188","telegram_chat_id":"5721652188",
            "provider_message_id":receipt,"provider_timestamp":stamp,
            "reply_to_message_id":"CARD-"+self.suffix,"output_language":"en"}
        authority=issue_gateway_owner_authority("5721652188","5721652188")
        rows=[]; mutations=[]
        def mutate(*_args,**_kwargs):
            mutations.append(operation)
            rows.extend({"Pig_ID":pig,"Status":"Dead","On_Farm":"No",
                "General_Notes":"oom_sakkie:"+operation} for pig in payload["pig_ids"])
            return {"success":True,"piglet_count":3,"pig_ids":payload["pig_ids"]},200
        callback=f"oompa:{claim['callback_token']}:confirm"
        with patch("modules.pig_weights.pig_weights_service._get_pig_master_rows",
                   side_effect=lambda:list(rows)), \
             patch("modules.pig_weights.pig_weights_service.mark_litter_piglets_dead",
                   side_effect=mutate), \
             patch("modules.oom_sakkie.protected_action_runtime.complete_claim",
                   side_effect=RuntimeError("completion store interrupted")):
            with self.assertRaises(RuntimeError):
                handle_protected_action_input(parsed,authority,callback_data=callback,
                                              connect_factory=self.connect)
        with patch("modules.pig_weights.pig_weights_service._get_pig_master_rows",
                   side_effect=lambda:list(rows)), \
             patch("modules.pig_weights.pig_weights_service.mark_litter_piglets_dead") as duplicate:
            recovered,status=handle_protected_action_input(parsed,authority,
                callback_data=callback,connect_factory=self.connect)
        self.assertEqual(status,200)
        self.assertEqual(recovered["status"],"litter_piglet_deaths_recovered_from_canonical")
        self.assertEqual(mutations,[operation])
        duplicate.assert_not_called()
        with self.connect() as db,db.cursor() as cur:
            cur.execute("select status,result_payload->>'status' from app_private.oom_protected_action_claims where callback_token=%s",
                        (claim["callback_token"],))
            self.assertEqual(cur.fetchone(),("completed","litter_piglet_deaths_recovered_from_canonical"))


if __name__ == "__main__":
    unittest.main()
