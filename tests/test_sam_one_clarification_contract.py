from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from modules.sales.sam_live_stock_evaluation import INITIAL_PREAUTHORIZED_CLASSES
from modules.sales.sam_one_clarification_contract import (
    delivery_disposition,
    prepare_one_clarification,
)
from modules.sales.sam_response_class_authority import (
    AUTHORIZABLE_CLASSES,
    OWNER_PROMOTABLE_CLASSES,
    append_authority_decision,
    build_authority_event,
    one_clarification_envelope,
    resolve_runtime_authority,
)


NOW = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
ENV = {
    "SAM_RESPONSE_CLASS_AUTHORITY_CONTROLLER_ENABLED": "true",
    "SAM_RESPONSE_CLASS_AUTHORITY_GLOBAL_ENABLED": "true",
    "SAM_RESPONSE_CLASS_ONE_CLARIFICATION_ENABLED": "true",
}


def context():
    return {
        "account_id": "147387", "inbox_id": "livestock-wa",
        "conversation_id": "fresh-1", "inbound_message_id": "in-1",
        "contact_id": "contact-1", "chronology_hash": "chronology-sha256",
        "missing_fact_key": "quantity", "authority_event_id": "authority-1",
        "response_class": "one_clarification",
        "policy_version": "sam_response_class_graduation_v2",
        "envelope_version": "sam_livestock_one_clarification_v1",
        "lane": "livestock", "genuine_chatwoot_inbound": True,
        "inbound_at": NOW.isoformat(),
        "activated_at": (NOW - timedelta(minutes=1)).isoformat(),
        "exact_latest_inbound": True, "identity_certain": True,
        "reply_window_healthy": True, "missing_fact_unanswered": True,
        "customer_language": "en", "closing_or_thanks": False,
        "customer_opt_out": False, "complaint_or_dispute": False,
        "sensitive_or_welfare": False, "protected_action": False,
        "commercially_binding_instruction": False, "historical_backlog": False,
        "evidence_health": {key: True for key in (
            "canonical_context", "stock", "pricing", "eligibility",
            "identity_chronology", "provider",
        )},
        "evidence_identities": {"stock": "stock-1", "price": "price-1"},
        "neutral_acknowledgement": "Thanks —", "question": "how many are you looking for?",
        "question_count": 1, "question_missing_fact_key": "quantity",
        "contains_commercial_statement": False,
    }


def promoted_event(**changes):
    event = build_authority_event(
        "one_clarification", "promoted", {"evidence": {}, "gates": {}},
        actor_type="owner", actor_id="owner", reason="reviewed envelope",
        authorized_envelope=one_clarification_envelope(), environ=ENV, now=NOW,
    )
    event.update(changes)
    return event


class OneClarificationContractTests(unittest.TestCase):
    def test_allowlist_is_distinct_from_preauthorization(self):
        self.assertNotIn("one_clarification", INITIAL_PREAUTHORIZED_CLASSES)
        self.assertIn("one_clarification", OWNER_PROMOTABLE_CLASSES)
        self.assertIn("one_clarification", AUTHORIZABLE_CLASSES)

    def test_complete_envelope_round_trip_and_digest_stability(self):
        envelope = one_clarification_envelope()
        first = promoted_event()["authorized_envelope"]
        second = promoted_event()["authorized_envelope"]
        self.assertEqual(first, envelope)
        self.assertEqual(second, envelope)
        self.assertEqual(promoted_event()["authority_event_id"], promoted_event()["authority_event_id"])

    def test_strict_envelope_version_and_fields(self):
        for mutation in ("version", "policy_version"):
            envelope = one_clarification_envelope()
            envelope[mutation] = "wrong"
            with self.assertRaisesRegex(ValueError, "contract_mismatch"):
                build_authority_event(
                    "one_clarification", "promoted", {"evidence": {}, "gates": {}},
                    actor_type="owner", actor_id="owner", reason="bad",
                    authorized_envelope=envelope, now=NOW,
                )
        envelope = one_clarification_envelope(); envelope["extra"] = True
        with self.assertRaisesRegex(ValueError, "fields_invalid"):
            build_authority_event(
                "one_clarification", "promoted", {"evidence": {}, "gates": {}},
                actor_type="owner", actor_id="owner", reason="bad",
                authorized_envelope=envelope, now=NOW,
            )

    def test_effective_at_expiry_policy_and_paused_fail_closed(self):
        allowed = resolve_runtime_authority(
            "one_clarification", current_message_class="one_clarification",
            delivery_rail_available=True, latest_event=promoted_event(), environ=ENV, now=NOW,
        )
        self.assertTrue(allowed["allowed"])
        cases = (
            (promoted_event(effective_at=(NOW + timedelta(seconds=1)).isoformat()), "authority_not_yet_effective"),
            (promoted_event(expires_at=NOW.isoformat()), "authority_expired"),
            (promoted_event(evaluator_version="wrong"), "authority_policy_version_mismatch"),
            (promoted_event(decision="paused"), "persistent_state_not_promoted"),
            (promoted_event(decision="regressed"), "persistent_state_not_promoted"),
            (promoted_event(decision="retired"), "persistent_state_not_promoted"),
        )
        for event, blocker in cases:
            result = resolve_runtime_authority(
                "one_clarification", current_message_class="one_clarification",
                delivery_rail_available=True, latest_event=event, environ=ENV, now=NOW,
            )
            self.assertIn(blocker, result["blockers"])

    def test_transition_ordering(self):
        def loader(prior):
            return lambda **_kwargs: ({"events": [prior] if prior else []}, 200)
        original = __import__("modules.sales.sam_response_class_authority", fromlist=["x"])
        saved = original.list_latest_authority_events
        try:
            original.list_latest_authority_events = loader({})
            result, status = append_authority_decision(
                "one_clarification", "promoted", actor_type="owner", actor_id="owner",
                reason="skip", authorized_envelope=one_clarification_envelope(), database_url="unused",
            )
            self.assertEqual(status, 409)
            self.assertEqual(result["status"], "authority_prior_state_invalid")
        finally:
            original.list_latest_authority_events = saved

    def test_fresh_exact_missing_fact_is_prepared_and_bound(self):
        first = prepare_one_clarification(context(), now=NOW)
        second = prepare_one_clarification(context(), now=NOW)
        self.assertTrue(first["allowed"])
        self.assertEqual(first["proposal_digest"], second["proposal_digest"])
        self.assertEqual(first["claim_key"], second["claim_key"])
        self.assertEqual(first["maximum_provider_attempts"], 1)
        self.assertEqual(first["provider_calls"], 0)
        self.assertFalse(first["proactive_follow_up"])

    def test_historical_answered_protected_closing_and_unknown_are_withheld(self):
        changes = (
            {"inbound_at": (NOW - timedelta(minutes=2)).isoformat()},
            {"missing_fact_unanswered": False},
            {"protected_action": True},
            {"closing_or_thanks": True},
            {"customer_opt_out": True},
            {"evidence_health": {"canonical_context": True}},
            {"contains_commercial_statement": True},
        )
        for change in changes:
            value = context(); value.update(change)
            result = prepare_one_clarification(value, now=NOW)
            self.assertFalse(result["allowed"])
            self.assertEqual(result["provider_calls"], 0)

    def test_identity_chronology_and_missing_fact_are_digest_bound(self):
        baseline = prepare_one_clarification(context(), now=NOW)
        for key in ("account_id", "inbox_id", "conversation_id", "inbound_message_id",
                    "contact_id", "chronology_hash", "missing_fact_key", "authority_event_id"):
            changed = context(); changed[key] += "-other"
            if key == "missing_fact_key":
                changed["question_missing_fact_key"] = changed[key]
            self.assertNotEqual(
                baseline["proposal_digest"], prepare_one_clarification(changed, now=NOW)["proposal_digest"]
            )

    def test_provider_acceptance_is_nonterminal_and_all_outcomes_never_retry(self):
        self.assertFalse(delivery_disposition("provider_accepted")["complete"])
        self.assertFalse(delivery_disposition("provider_accepted")["quarantined"])
        for state in ("provider_rejected", "provider_failed", "provider_outcome_ambiguous",
                      "delivery_transition_missing", "provider_delivered", "provider_read"):
            result = delivery_disposition(state)
            self.assertFalse(result["retry_allowed"])
        self.assertTrue(delivery_disposition("provider_delivered")["complete"])
        self.assertTrue(delivery_disposition("provider_read")["complete"])

    def test_replay_and_concurrent_inputs_have_one_exact_claim_key(self):
        keys = {prepare_one_clarification(deepcopy(context()), now=NOW)["claim_key"] for _ in range(20)}
        self.assertEqual(len(keys), 1)


if __name__ == "__main__":
    unittest.main()
