"""Synthetic owner-reply regression; no real owner, animal or provider input."""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
import json
import unittest

from modules.oom_sakkie import farm_manager_runtime as runtime
from modules.oom_sakkie import family_message_lifecycle as family
from modules.oom_sakkie import telegram_gateway as gateway
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_mortality_adapter import consume_mortality_packet
from modules.oom_sakkie.herdmaster_mortality_runtime import consume_current_mortality_packet
from modules.pig_weights.herdmaster_mortality_intelligence import build_oom_sakkie_mortality_packet

NOW = datetime(2026, 9, 21, 13, 48, tzinfo=timezone.utc)
RETIRED = "SYNTHETIC-PIG-RETIRED"
OWNER = "42"


def packet():
    return build_oom_sakkie_mortality_packet({"mortality_events": [
        {"event_id": "SYNTHETIC-CURRENT-DEATH", "pig_id": "SYNTHETIC-PIG-CURRENT",
         "effective_date": "2026-09-20", "event_kind": "individual_death",
         "confirmation": "confirmed", "canonical_status": "current"},
        {"event_id": RETIRED + ":DEATH", "pig_id": RETIRED,
         "effective_date": "2026-08-01", "event_kind": "individual_death",
         "confirmation": "confirmed", "canonical_status": "superseded"},
    ]}, analysis_end=date(2026, 9, 21))


def parsed(language="en"):
    return {"telegram_user_id": OWNER, "telegram_chat_id": OWNER,
        "provider_message_id": "synthetic-farm-question", "provider_timestamp": NOW.isoformat(),
        "text": "Give today's irrigation and breeding priorities", "output_language": language,
        "semantic": {"domain": "manager_round", "language": language, "needs_clarification": False}}


def loaders(value):
    result, _ = consume_mortality_packet(value, observed_at=NOW)
    item = replace(result.work_items[0], metadata={"mortality_packet": value,
        "mortality_fingerprints": {"SYNTHETIC-CURRENT-DEATH": "active-fingerprint"}})
    herd = replace(result, work_items=(item,))
    return {name: (lambda n=name: herd if n == "herdmaster" else runtime._missing(n, NOW))
        for name in ("herdmaster", "rootline", "sam", "beacon")}


class FamilyStore:
    def __init__(self, fail=""):
        self.rows = {}; self.fail = fail
    def __call__(self, action, identity, payload):
        if action == "load":
            return [deepcopy(row) for row in self.rows.values() if row["card_mission_id"] == identity]
        if payload["state"] == self.fail:
            return {"success": False, "created": None}
        created = identity not in self.rows
        if created: self.rows[identity] = deepcopy(payload)
        return {"success": True, "created": created}


class FarmRoundPersistenceTests(unittest.TestCase):
    def test_projection_preserves_every_active_field_and_consumption_replay(self):
        original = packet(); before = deepcopy(original)
        projected = runtime._mortality_packet(SimpleNamespace(queue=[SimpleNamespace(
            metadata={"mortality_packet": original})]))
        self.assertEqual(projected, {k: v for k, v in original.items() if k != "excluded_dated_or_superseded"})
        self.assertNotIn(RETIRED, json.dumps(projected))
        self.assertEqual(original, before)
        self.assertEqual(consume_mortality_packet(original, observed_at=NOW),
                         consume_mortality_packet(projected, observed_at=NOW))
        rows = {}
        def store(action, identity, value):
            if action == "load": return rows.get(identity)
            rows[identity] = deepcopy(value)
            return {"success": True, "created": True}
        args = dict(authority=issue_gateway_owner_authority(OWNER, OWNER),
            owner_user_id=OWNER, observed_at=NOW, state_store=store)
        _, first = consume_current_mortality_packet(packet=original, **args)
        before_receipt = deepcopy(rows)
        _, replay = consume_current_mortality_packet(packet=projected, **args)
        self.assertEqual(first["status"], "mortality_consumption_ready")
        self.assertEqual(replay["status"], "mortality_consumption_replay_suppressed")
        self.assertEqual(rows, before_receipt)
        self.assertEqual(set(first["canonical_death_event_fingerprints"]), {"SYNTHETIC-CURRENT-DEATH"})

    def test_failed_round_has_safe_language_and_distinct_notice_card(self):
        for language in ("en", "af"):
            with self.subTest(language=language):
                result, status = runtime.handle_farm_manager_round(parsed(language),
                    issue_gateway_owner_authority(OWNER, OWNER), now=NOW, loaders=loaders(packet()),
                    event_store=lambda action, *_: None if action == "load" else {"success": False})
                self.assertEqual(status, 503); self.assertFalse(result["success"])
                self.assertFalse(result["records_audit_trace"])
                self.assertTrue(result["answer"]); self.assertNotIn(RETIRED, result["answer"])
                self.assertEqual(result["card_mission_id"], result["mission_id"] + "-PERSISTENCE-FAILURE")
                localized = family.localize_recipient_result(parsed(language), result, "OOM_SAKKIE")
                self.assertEqual(localized["answer"], result["answer"])
                self.assertNotIn("try again", result["answer"])

    def test_failure_notice_replay_is_silent_and_cannot_suppress_successful_card(self):
        store = FamilyStore(); sends = []
        def sender(*args, **kwargs):
            sends.append(args)
            return {"success": True, "telegram_message_id": str(800 + len(sends))}
        value = runtime._persistence_failure(parsed(), "SYNTHETIC-FARM-ROUND")
        with patch.object(family, "_event_store", store), patch.object(family, "_send_telegram", sender):
            first = gateway._deliver_farm_persistence_failure(parsed(), value)
            repeat = gateway._deliver_farm_persistence_failure(parsed(), value)
            later = family.deliver_family_result(parsed(), {"success": True,
                "status": "farm_manager_round_ready", "answer": "Current confirmed farm brief."},
                specialist="OOM_SAKKIE", mission_id=value["mission_id"], card_mission_id=value["mission_id"])
        self.assertEqual(len(sends), 2)
        self.assertTrue(first["success"]); self.assertEqual(repeat["telegram_sends"], 0)
        self.assertTrue(later["success"])
        self.assertEqual({row["card_mission_id"] for row in store.rows.values()},
            {value["mission_id"], value["card_mission_id"]})

    def test_failed_notice_claim_never_sends_and_postsend_failure_never_retries(self):
        for failed_state, expected_sends in (("delivery_attempted", 0), ("delivered", 1)):
            store = FamilyStore(failed_state); calls = []
            def sender(*_args, **_kwargs):
                calls.append(1); return {"success": True, "telegram_message_id": "801"}
            value = runtime._persistence_failure(parsed(), "SYNTHETIC-FARM-ROUND")
            with self.subTest(failed_state=failed_state), patch.object(family, "_event_store", store), patch.object(family, "_send_telegram", sender):
                first = gateway._deliver_farm_persistence_failure(parsed(), value)
                repeat = gateway._deliver_farm_persistence_failure(parsed(), value)
            self.assertFalse(first["success"]); self.assertFalse(repeat["success"])
            self.assertEqual(len(calls), expected_sends)
            self.assertNotIn("delivery_definitely_not_sent", first)

    def test_ambiguous_provider_notice_keeps_attempt_and_never_resends(self):
        store = FamilyStore(); calls = []
        def sender(*_args, **_kwargs):
            calls.append(1); return {"success": False}
        value = runtime._persistence_failure(parsed(), "SYNTHETIC-FARM-ROUND")
        with patch.object(family, "_event_store", store), patch.object(family, "_send_telegram", sender):
            first = gateway._deliver_farm_persistence_failure(parsed(), value)
            repeat = gateway._deliver_farm_persistence_failure(parsed(), value)
        self.assertEqual(len(calls), 1); self.assertFalse(first["success"])
        self.assertEqual(repeat["status"], "family_message_delivery_ambiguous")

    def test_actual_authenticated_gateway_keeps_failed_report_503_and_true_delivery_status(self):
        env = {"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1", "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "s" * 40,
               "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": OWNER}
        payload = {"message": {"message_id": 900, "date": int(NOW.timestamp()),
            "from": {"id": 42}, "chat": {"id": 42, "type": "private"}, "text": parsed()["text"]}}
        store = FamilyStore()
        with ExitStack() as stack:
            stack.enter_context(patch.object(gateway, "handle_message", side_effect=AssertionError("unexpected generic/provider fallback")))
            for name in ("handle_auction_confirmation", "handle_protected_action_input",
                "handle_litter_first_treatment_message", "handle_documents_green_request",
                "handle_grouped_weight_message", "handle_grouped_breeding_message", "handle_manager_question_reply",
                "handle_owner_operational_continuation", "handle_operational_specialist_message",
                "handle_authenticated_health_loss_message", "handle_farrowing_litter_message",
                "handle_herdmaster_request", "handle_beacon_request"):
                stack.enter_context(patch.object(gateway, name, return_value=({"handled": False}, 200)))
            stack.enter_context(patch("modules.oom_sakkie.herdmaster_litter_weaning_runtime.handle_litter_weaning_message", return_value=({"handled": False}, 200)))
            for name in ("recover_contextual_specialist_replay", "load_active_manager_question", "interpret_owner_message"):
                stack.enter_context(patch.object(gateway, name, return_value=None))
            stack.enter_context(patch.object(gateway, "handle_farm_manager_round", side_effect=lambda p, a:
                runtime.handle_farm_manager_round(p, a, now=NOW, loaders=loaders(packet()),
                    event_store=lambda action, *_: None if action == "load" else {"success": False})))
            stack.enter_context(patch.object(family, "_event_store", store))
            sender = stack.enter_context(patch.object(family, "_send_telegram", return_value={"success": True, "telegram_message_id": "802"}))
            body, status = gateway.handle_telegram_gateway_message(payload,
                headers={"Authorization": "Bearer " + "s" * 40}, environ=env)
            self.assertEqual((status, body["status"]), (503, "farm_manager_round_persistence_unproven"))
            self.assertFalse(body["success"]); self.assertFalse(body["records_audit_trace"])
            self.assertEqual(body["audit_trace_status"], "unproven")
            self.assertTrue(body["answer"]); self.assertTrue(body["failure_notice_delivery_confirmed"])
            sender.assert_called_once()
