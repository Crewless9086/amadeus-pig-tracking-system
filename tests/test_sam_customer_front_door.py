import json
from pathlib import Path
import unittest

from modules.sales.sam_customer_front_door import interpret_customer_front_door


KNOWLEDGE = json.loads(Path("config/sam_farm_knowledge.json").read_text(encoding="utf-8"))


def evidence(message, *, prior=None, campaign=None, attachments=None, message_id="M-2"):
    scope = {
        "account_id": "147387", "inbox_id": "116199",
        "contact_id": "C-9", "conversation_id": "CONV-7",
    }
    chronology = [
        {"message_id": "M-1", "role": "sam_or_farm", "content": "How can I help?", "created_at": "2026-07-29T08:00:00Z", **scope},
        {"message_id": message_id, "role": "customer", "content": message, "created_at": "2026-07-29T08:01:00Z", **scope},
    ]
    prior = dict(prior or {})
    campaign = dict(campaign or {})
    if prior:
        prior["identity"] = scope
        prior["source"] = "authenticated_chatwoot_chronology"
        prior["version"] = "v1"
    if campaign:
        campaign["identity"] = scope
        campaign["source"] = "authenticated_campaign_reference"
        campaign["version"] = "v1"
    return {
        "identity": {
            **scope,
            "latest_inbound_message_id": message_id,
        },
        "latest_inbound": {"message_id": message_id, "content": message, "attachments": attachments or [], **scope},
        "chronology": chronology,
        "retained_context": prior or {},
        "campaign_or_post": campaign or {},
    }


class SamCustomerFrontDoorTests(unittest.TestCase):
    def test_greetings_and_small_talk_are_warm_and_ask_once(self):
        for text in ("Hi", "Morning, how are you?", "Howzit", "Môre, hoe gaan dit?"):
            with self.subTest(text=text):
                result = interpret_customer_front_door(evidence(text), KNOWLEDGE)
                self.assertTrue(result["should_reply"])
                self.assertEqual(result["clarification_count"], 1)
                self.assertTrue(result["customer_reply"])
                self.assertNotRegex(result["customer_reply"].lower(), r"\blane\b|\bconfidence\b")

    def test_public_farm_facts_are_canonical_and_provenanced(self):
        cases = (
            ("Where are you based?", "Riversdale area", "public_profile.location_summary"),
            ("What do you guys do?", "small farm helping customers", "public_profile.one_line_story"),
            ("How does your farm work?", "small farm helping customers", "public_profile.one_line_story"),
        )
        for text, phrase, provenance in cases:
            with self.subTest(text=text):
                result = interpret_customer_front_door(evidence(text), KNOWLEDGE)
                self.assertIn(phrase, result["customer_reply"])
                self.assertIn(provenance, result["supported_public_answer"]["facts"][0]["provenance"])
                self.assertEqual(result["supported_public_answer"]["knowledge_status"], "draft_owner_editable")
                self.assertLessEqual(result["clarification_count"], 1)

    def test_unclear_first_contact_and_unclear_price_ask_only_one_question(self):
        unclear = interpret_customer_front_door(evidence("Can you help me?"), KNOWLEDGE)
        self.assertEqual(unclear["front_door_interpretation"]["kind"], "unclear_enquiry")
        self.assertEqual(unclear["clarification_count"], 1)
        price = interpret_customer_front_door(evidence("How much?"), KNOWLEDGE)
        self.assertEqual(price["clarification"], "Do you mean live pigs or pork?")

    def test_prior_context_preserves_facts_and_transfers_terse_followup(self):
        prior = {"specialist": "live_stock_sales", "facts": {"size": "7-19 kg", "quantity": 3}}
        result = interpret_customer_front_door(evidence("How much?", prior=prior), KNOWLEDGE)
        self.assertEqual(result["next_specialist_recommendation"], "livestock")
        self.assertEqual(result["retained_conversation_context"]["facts"]["quantity"], 3)
        self.assertFalse(result["should_reply"])
        self.assertEqual(result["clarification_count"], 0)

    def test_campaign_post_context_resolves_specialist_without_reasking(self):
        campaign = {
            "campaign_id": "BEACON-9",
            "post_id": "POST-4",
            "post_text": "Amadeus Farm pork freezer options",
            "product_focus": "half carcass pork",
        }
        result = interpret_customer_front_door(evidence("I saw your post", campaign=campaign), KNOWLEDGE)
        self.assertEqual(result["next_specialist_recommendation"], "meat")
        self.assertTrue(result["front_door_interpretation"]["used_campaign_context"])
        self.assertFalse(result["should_reply"])

    def test_livestock_and_meat_transfer_remain_separate(self):
        livestock = interpret_customer_front_door(evidence("Do you have pigs?"), KNOWLEDGE)
        meat = interpret_customer_front_door(evidence("Do you sell pork?"), KNOWLEDGE)
        self.assertEqual(livestock["next_specialist_recommendation"], "livestock")
        self.assertEqual(meat["next_specialist_recommendation"], "meat")
        self.assertFalse(livestock["should_reply"])
        self.assertFalse(meat["should_reply"])
        self.assertTrue(livestock["specialist_response_required"])
        self.assertTrue(meat["specialist_response_required"])

    def test_mixed_intent_gets_one_customer_facing_question(self):
        result = interpret_customer_front_door(evidence("Do you sell live pigs and pork?"), KNOWLEDGE)
        self.assertEqual(result["front_door_interpretation"]["kind"], "mixed_intent")
        self.assertEqual(result["clarification_count"], 1)
        self.assertNotIn("lane", result["customer_reply"].lower())

    def test_context_reset_does_not_reuse_old_specialist(self):
        prior = {"specialist": "meat_preorder", "facts": {"product_type": "half_carcass"}}
        result = interpret_customer_front_door(evidence("Different question: where are you based?", prior=prior), KNOWLEDGE)
        self.assertTrue(result["front_door_interpretation"]["context_reset"])
        self.assertEqual(result["next_specialist_recommendation"], "front_door")
        self.assertIn("Riversdale", result["customer_reply"])

    def test_acknowledgements_and_natural_closes_do_not_force_reply(self):
        for text in ("Thanks", "Baie dankie", "👍", "Okay!"):
            with self.subTest(text=text):
                result = interpret_customer_front_door(evidence(text), KNOWLEDGE)
                self.assertFalse(result["should_reply"])
                self.assertEqual(result["customer_reply"], "")
                self.assertEqual(result["clarification_count"], 0)

    def test_visit_creates_one_protected_exception_without_promising_access(self):
        result = interpret_customer_front_door(evidence("Can I come visit?"), KNOWLEDGE)
        self.assertTrue(result["should_reply"])
        self.assertEqual(result["next_specialist_recommendation"], "owner_exception")
        self.assertEqual(result["protected_owner_exception"]["type"], "farm_visit_confirmation")
        self.assertEqual(
            result["customer_reply"],
            "Farm visits need to be confirmed by the farm first. I can pass your request on for review.",
        )
        self.assertNotRegex(result["customer_reply"].lower(), r"\byes\b|\bbooked\b|\bcome at\b")
        self.assertEqual(result["clarification_count"], 0)

    def test_unsupported_claims_are_never_drawn_from_protected_knowledge(self):
        result = interpret_customer_front_door(evidence("How much and is it available for delivery?"), KNOWLEDGE)
        reply = result["customer_reply"].lower()
        self.assertNotIn("130", reply)
        self.assertNotIn("available", reply)
        self.assertNotIn("delivery only", reply)
        self.assertTrue(all("meat_sales" not in fact["provenance"] for fact in result["supported_public_answer"]["facts"]))
        self.assertIsNotNone(result["protected_owner_exception"])

    def test_attachment_is_classified_but_never_trusted_as_fact(self):
        result = interpret_customer_front_door(
            evidence("", attachments=[{"content_type": "image/jpeg", "url": "https://example.invalid/a.jpg"}]),
            KNOWLEDGE,
        )
        self.assertEqual(result["attachment_classification"][0]["classification"], "unverified_attachment")
        self.assertFalse(result["attachment_classification"][0]["facts_trusted"])

    def test_exact_identity_idempotency_and_zero_write_authority(self):
        first = interpret_customer_front_door(evidence("Hi"), KNOWLEDGE)
        second = interpret_customer_front_door(evidence("Hi"), KNOWLEDGE)
        self.assertEqual(first["idempotency_key"], second["idempotency_key"])
        self.assertTrue(first["idempotency_key"].startswith("sam-front-door:"))
        self.assertTrue(all(value is False for value in first["zero_authority"].values()))

        mismatched = evidence("Hi")
        mismatched["identity"]["latest_inbound_message_id"] = "OTHER"
        blocked = interpret_customer_front_door(mismatched, KNOWLEDGE)
        self.assertFalse(blocked["should_reply"])
        self.assertIn("latest_inbound_identity_mismatch", blocked["identity_errors"])
        self.assertEqual(blocked["idempotency_key"], "")

    def test_chronology_must_end_at_exact_latest_inbound(self):
        payload = evidence("Hi")
        payload["chronology"].append({
            "message_id": "M-3", "role": "customer", "content": "Do you sell pork?", "created_at": "2026-07-29T08:02:00Z"
        })
        result = interpret_customer_front_door(payload, KNOWLEDGE)
        self.assertFalse(result["should_reply"])
        self.assertIn("chronology_not_current_at_latest_inbound", result["identity_errors"])

    def test_contract_contains_no_io_and_serializes_cleanly(self):
        result = interpret_customer_front_door(evidence("What do you guys do?"), KNOWLEDGE)
        encoded = json.dumps(result, ensure_ascii=False)
        self.assertIn("performs_io", encoded)
        self.assertNotIn("AUTO_GENERAL", result["customer_reply"])

    def test_same_id_different_content_and_outbound_tail_fail_closed(self):
        payload = evidence("Hi")
        payload["chronology"][-1]["content"] = "Do you sell pork?"
        self.assertIn(
            "latest_inbound_content_mismatch",
            interpret_customer_front_door(payload, KNOWLEDGE)["identity_errors"],
        )
        payload = evidence("Hi")
        payload["chronology"][-1]["role"] = "sam_or_farm"
        self.assertIn(
            "chronology_tail_not_inbound",
            interpret_customer_front_door(payload, KNOWLEDGE)["identity_errors"],
        )

    def test_cross_conversation_context_is_rejected(self):
        payload = evidence("How much?", prior={"specialist": "meat_preorder", "facts": {"secret": "x"}})
        payload["retained_context"]["identity"]["conversation_id"] = "OTHER"
        result = interpret_customer_front_door(payload, KNOWLEDGE)
        self.assertFalse(result["should_reply"])
        self.assertIn("retained_context_scope_mismatch", result["identity_errors"])
        self.assertNotIn("secret", result["retained_conversation_context"]["facts"])
        self.assertFalse(result["front_door_interpretation"]["used_prior_context"])

    def test_supplied_attachment_classification_cannot_grant_fact_trust(self):
        payload = evidence("")
        payload["attachment_classification"] = [{
            "kind": "image", "classification": "payment_confirmed", "facts_trusted": True,
        }]
        result = interpret_customer_front_door(payload, KNOWLEDGE)
        self.assertFalse(result["attachment_classification"][0]["facts_trusted"])

    def test_context_reset_separates_historical_facts(self):
        result = interpret_customer_front_door(
            evidence("Different question: where are you based?", prior={
                "specialist": "meat_preorder", "facts": {"product_type": "half_carcass"},
            }),
            KNOWLEDGE,
        )
        self.assertEqual(result["retained_conversation_context"]["facts"], {})
        self.assertEqual(
            result["retained_conversation_context"]["historical_facts"]["product_type"],
            "half_carcass",
        )

    def test_invalid_identity_types_and_oversize_values_fail_closed(self):
        for bad in ({"nested": "id"}, "X" * 201):
            with self.subTest(bad=type(bad).__name__):
                payload = evidence("Hi")
                payload["identity"]["contact_id"] = bad
                result = interpret_customer_front_door(payload, KNOWLEDGE)
                self.assertFalse(result["valid_for_idempotency"])
                self.assertEqual(result["idempotency_key"], "")

    def test_hostile_or_noncanonical_knowledge_fails_closed(self):
        hostile = json.loads(json.dumps(KNOWLEDGE))
        hostile["status"] = "untrusted"
        hostile["faq"]["can_i_visit"] = "Yes, come any time."
        result = interpret_customer_front_door(evidence("Can I come visit?"), hostile)
        self.assertFalse(result["should_reply"])
        self.assertIn("farm_knowledge_status_not_canonical_draft", result["identity_errors"])

        same_identity_tamper = json.loads(json.dumps(KNOWLEDGE))
        same_identity_tamper["public_profile"]["location_summary"] = "Exact private address; pigs are always available."
        result = interpret_customer_front_door(evidence("Where are you based?"), same_identity_tamper)
        self.assertFalse(result["should_reply"])
        self.assertIn("farm_knowledge_snapshot_digest_mismatch", result["identity_errors"])
        self.assertEqual(result["customer_reply"], "")

    def test_explicit_specialist_protected_requests_keep_exception_without_extra_question(self):
        cases = (
            ("Do you have pigs available?", "livestock"),
            ("Can I book pork?", "meat"),
            ("Can you deliver pork?", "meat"),
            ("I paid for the pork", "meat"),
        )
        for text, specialist in cases:
            with self.subTest(text=text):
                result = interpret_customer_front_door(evidence(text), KNOWLEDGE)
                self.assertEqual(result["next_specialist_recommendation"], specialist)
                self.assertEqual(result["clarification_count"], 0)
                self.assertEqual(result["protected_owner_exception"]["type"], "protected_customer_detail")
                self.assertTrue(result["specialist_response_required"])

    def test_cross_conversation_campaign_is_not_returned_or_used(self):
        payload = evidence("I saw your post", campaign={
            "post_text": "private unrelated pork post", "product_focus": "pork",
        })
        payload["campaign_or_post"]["identity"]["conversation_id"] = "OTHER"
        result = interpret_customer_front_door(payload, KNOWLEDGE)
        self.assertFalse(result["campaign_or_post_context"]["available"])
        self.assertNotIn("private unrelated", json.dumps(result))
        self.assertFalse(result["front_door_interpretation"]["used_campaign_context"])


if __name__ == "__main__":
    unittest.main()
