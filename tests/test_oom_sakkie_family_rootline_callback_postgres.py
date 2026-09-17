import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg

from tests.test_oom_sakkie_family_rootline_callback import (
    ANTON, ANTOINETTE, callback_parsed, parsed, principal,
)
from modules.oom_sakkie.family_rootline_callback import (
    CALLBACK_PREFIX, bind_family_rootline_preview_card, create_family_rootline_preview,
    handle_family_rootline_callback,
)


URL = os.getenv("OOM_PROTECTED_ACTION_POSTGRES_URL", "").strip()


@unittest.skipUnless(URL, "disposable PostgreSQL URL is required")
class FamilyRootlineCallbackPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(URL) as db:
            db.execute("create schema if not exists app_private")
            db.execute("""create table if not exists app_private.oom_protected_action_claims(
              callback_token text primary key, action_kind text not null, owner_user_id text not null,
              private_chat_id text not null, mission_id text not null, provider_message_id text not null,
              preview_card_message_id text, preview_digest text not null, evidence_generation text not null,
              preview_payload jsonb not null, status text not null default 'active', expires_at timestamptz not null,
              confirmation_provider_message_id text, confirmation_provider_timestamp timestamptz,
              result_payload jsonb, created_at timestamptz not null default now(), completed_at timestamptz,
              unique(action_kind,mission_id,preview_digest))""")
            db.execute("""create unique index if not exists oom_protected_action_one_active_mission
              on app_private.oom_protected_action_claims(mission_id) where status='active'""")

    def connect(self): return psycopg.connect(URL)

    def setUp(self): self.message = "PG-" + uuid.uuid4().hex

    def tearDown(self):
        with self.connect() as db:
            db.execute("delete from app_private.oom_protected_action_claims where provider_message_id=%s",
                       (self.message,))

    def preview(self):
        item = parsed(message=self.message)
        result = create_family_rootline_preview(parsed=item, principal=principal(),
            capability="irrigation_start", replay_identity="R-" + self.message,
            connect_factory=self.connect)
        self.assertTrue(result["success"])
        self.assertTrue(bind_family_rootline_preview_card(result,
            {"provider_message_id": "CARD-" + self.message}, connect_factory=self.connect))
        return result

    def invoke(self, token, callback_id, adapter):
        item = callback_parsed(message=callback_id)
        item["reply_to_message_id"] = "CARD-" + self.message
        return handle_family_rootline_callback(item, principal(),
            callback_data=f"{CALLBACK_PREFIX}{token}:confirm", rootline_adapter=adapter,
            replay_store=lambda *_: {"success": True, "created": True}, connect_factory=self.connect)

    def test_full_round_trip_concurrency_and_restart_replay_are_exactly_once(self):
        preview = self.preview(); calls = []
        def adapter(**_):
            calls.append(1)
            return {"success": True, "status": "delegated_dry_boundary_accepted",
                "answer": "Aanvaar.", "hardware_commands": 0, "writes_farm_data": False}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda index: self.invoke(preview["callback_token"],
                f"CB-{index}-{self.message}", adapter), (1, 2)))
        self.assertEqual(len(calls), 1)
        self.assertEqual(sum(result[0].get("status") == "delegated_dry_boundary_accepted"
                             for result in results), 1)
        replay, status = self.invoke(preview["callback_token"], "CB-REPLAY-" + self.message, adapter)
        self.assertEqual((status, replay["status"]), (200, "family_rootline_callback_replayed_noop"))
        self.assertEqual(len(calls), 1)
        with self.connect() as db:
            row = db.execute("select status,result_payload,confirmation_provider_message_id from app_private.oom_protected_action_claims where callback_token=%s",
                             (preview["callback_token"],)).fetchone()
        self.assertEqual(row[0], "completed")
        self.assertEqual(row[1]["hardware_commands"], 0)
        self.assertIn(row[2], {f"CB-1-{self.message}", f"CB-2-{self.message}"})

    def test_expired_substituted_and_ambiguous_states_make_zero_calls(self):
        preview = self.preview(); calls = []
        with self.connect() as db:
            db.execute("update app_private.oom_protected_action_claims set expires_at=now()-interval '1 second' where callback_token=%s",
                       (preview["callback_token"],))
        result, status = self.invoke(preview["callback_token"], "CB-EXPIRED-" + self.message,
            lambda **_: calls.append(1))
        self.assertEqual((status, result["status"], calls),
                         (409, "family_rootline_callback_expired", []))

    def test_wrong_identity_card_changed_binding_and_executing_state_are_zero_effect(self):
        for case, expected in (("antoinette", "family_rootline_callback_unauthorized"),
                               ("card", "family_rootline_callback_card_mismatch"),
                               ("binding", "family_rootline_callback_binding_changed"),
                               ("executing", "family_rootline_callback_execution_ambiguous")):
            self.message = "PG-" + uuid.uuid4().hex
            preview = self.preview(); calls = []
            item, actor = callback_parsed(), principal()
            item["reply_to_message_id"] = "CARD-" + self.message
            if case == "antoinette": item, actor = callback_parsed(ANTOINETTE), principal(ANTOINETTE)
            if case == "card": item["reply_to_message_id"] = "SUBSTITUTED"
            with self.connect() as db:
                if case == "binding":
                    db.execute("update app_private.oom_protected_action_claims set preview_payload=jsonb_set(preview_payload,'{family_binding_digest}','\"changed\"'::jsonb) where callback_token=%s",
                               (preview["callback_token"],))
                if case == "executing":
                    db.execute("update app_private.oom_protected_action_claims set status='executing' where callback_token=%s",
                               (preview["callback_token"],))
            result, status = handle_family_rootline_callback(item, actor,
                callback_data=f"{CALLBACK_PREFIX}{preview['callback_token']}:confirm",
                rootline_adapter=lambda **_: calls.append(1), replay_store=lambda *_: {},
                connect_factory=self.connect)
            self.assertGreaterEqual(status, 400)
            self.assertEqual((result["status"], calls), (expected, []))
            with self.connect() as db:
                db.execute("delete from app_private.oom_protected_action_claims where callback_token=%s",
                           (preview["callback_token"],))
