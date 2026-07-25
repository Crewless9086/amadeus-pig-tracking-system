import unittest

from modules.sales import sam_delivery_truth as truth


def attempt():
    return truth.build_delivery_attempt(
        {
            "conversation_id": "2013",
            "contact_id": "699428938",
            "inbox_id": "96568",
            "message_id": "759446521",
        },
        {
            "suggested_reply_text": "Hi Charl! How can I help you today?",
            "response_class": "greeting",
        },
        {"review_event_id": "SAM-LIVE-REVIEW-A17F2169ED0F"},
        response_class="greeting",
    )


class SamDeliveryTruthTests(unittest.TestCase):
    def test_attempt_identity_is_distinct_stable_and_sanitized(self):
        first = attempt()
        second = attempt()
        claim = truth.build_delivery_claim_event(first)
        self.assertTrue(first["success"])
        self.assertEqual(first["delivery_attempt_id"], second["delivery_attempt_id"])
        self.assertTrue(first["delivery_attempt_id"].startswith("SAM-DELIVERY-ATTEMPT-"))
        self.assertNotEqual(first["delivery_attempt_id"], first["review_id"])
        self.assertEqual(first["previous_delivery_state"], truth.PREPARED)
        self.assertEqual(first["delivery_state"], truth.ATTEMPT_CLAIMED)
        self.assertEqual(claim["event_source"], "sam_outbound_delivery_attempt_claim")
        serialized = str(claim)
        self.assertNotIn("Hi Charl", serialized)
        self.assertNotIn("wamid.", serialized)
        self.assertNotIn("+447", serialized)
        self.assertTrue(claim["review_json"]["automatic_retry_prohibited"])

    def test_attempt_requires_complete_exact_identity(self):
        value = truth.build_delivery_attempt(
            {"conversation_id": "2013"},
            {"suggested_reply_text": "Hi"},
            {},
        )
        self.assertFalse(value["success"])
        self.assertIn("contact_id", value["missing_fields"])
        self.assertIn("review_id", value["missing_fields"])

    def test_http_2xx_sent_is_accepted_unverified(self):
        outcome = truth.classify_chatwoot_response({
            "status_code": 200,
            "body": {"id": 10, "status": "sent"},
        })
        self.assertEqual(outcome["delivery_state"], truth.CHATWOOT_ACCEPTED_UNVERIFIED)
        self.assertFalse(outcome["customer_send_confirmed"])
        self.assertFalse(outcome["handled_autonomously"])
        self.assertTrue(outcome["automatic_retry_prohibited"])

    def test_delivered_and_read_are_confirmed(self):
        for status, expected in (
            ("delivered", truth.PROVIDER_DELIVERED),
            ("read", truth.PROVIDER_READ),
        ):
            with self.subTest(status=status):
                outcome = truth.classify_chatwoot_response({
                    "status_code": 200,
                    "body": {"id": 10, "status": status},
                })
                self.assertEqual(outcome["delivery_state"], expected)
                self.assertTrue(outcome["customer_send_confirmed"])
                self.assertTrue(outcome["handled_autonomously"])

    def test_failed_missing_and_malformed_statuses(self):
        failed = truth.classify_chatwoot_response({
            "status_code": 200,
            "body": {"id": 10, "status": "failed"},
        })
        missing = truth.classify_chatwoot_response({
            "status_code": 200,
            "body": {"id": 10},
        })
        malformed = truth.classify_chatwoot_response({
            "status_code": 200,
            "body": {"id": 10, "status": {"unexpected": True}},
        })
        identity_missing = truth.classify_chatwoot_response({
            "status_code": 200,
            "body": {"status": "sent"},
        })
        self.assertEqual(failed["delivery_state"], truth.PROVIDER_FAILED)
        self.assertEqual(missing["delivery_state"], truth.PROVIDER_OUTCOME_AMBIGUOUS)
        self.assertEqual(malformed["delivery_state"], truth.PROVIDER_OUTCOME_AMBIGUOUS)
        self.assertEqual(identity_missing["delivery_state"], truth.PROVIDER_OUTCOME_AMBIGUOUS)
        self.assertFalse(failed["customer_send_confirmed"])
        self.assertTrue(missing["automatic_retry_prohibited"])

    def test_timeout_after_dispatch_is_ambiguous_without_retry(self):
        outcome = truth.classify_dispatch_exception(TimeoutError("timeout"))
        self.assertEqual(outcome["delivery_state"], truth.PROVIDER_OUTCOME_AMBIGUOUS)
        self.assertFalse(outcome["customer_send_confirmed"])
        self.assertTrue(outcome["automatic_retry_prohibited"])

    def test_provider_identity_is_classified_without_raw_value(self):
        for value, expected in (
            ("wamid.SECRET", "whatsapp_provider"),
            ("sam_live_stock:abc", "application_supplied"),
            ("other-id", "other"),
            ("", "absent"),
        ):
            with self.subTest(value=value):
                self.assertEqual(truth.classify_provider_identity(value), expected)
        outcome = truth.classify_chatwoot_response({
            "status_code": 200,
            "body": {"id": 10, "status": "sent", "source_id": "wamid.SECRET"},
        })
        self.assertEqual(outcome["provider_identity_class"], "whatsapp_provider")
        self.assertNotIn("wamid.SECRET", str(outcome))

    def test_transition_retains_exact_conversation_inbound_outgoing_and_attempt(self):
        current = attempt()
        outcome = truth.classify_chatwoot_response({
            "status_code": 200,
            "body": {"id": "759446597", "status": "sent", "source_id": "wamid.SECRET"},
        })
        event = truth.build_delivery_transition_event(current, outcome)
        evidence = event["review_json"]
        self.assertEqual(event["chatwoot_conversation_id"], "2013")
        self.assertEqual(event["chatwoot_message_id"], "759446597")
        self.assertEqual(evidence["inbound_message_id"], "759446521")
        self.assertEqual(evidence["delivery_attempt_id"], current["delivery_attempt_id"])
        self.assertEqual(evidence["provider_identity_class"], "whatsapp_provider")
        self.assertNotIn("wamid.SECRET", str(event))

    def test_reconciliation_sent_to_delivered_and_replay_is_idempotent(self):
        current = {
            **attempt(),
            "chatwoot_outgoing_message_id": "759446597",
        }
        created_ids = set()

        def record(event):
            event_id = event["review_event_id"]
            created = event_id not in created_ids
            created_ids.add(event_id)
            return {"success": True, "created": created}

        def load(conversation_id, message_id):
            return {
                "status_code": 200,
                "body": {
                    "id": message_id,
                    "conversation_id": conversation_id,
                    "status": "delivered",
                    "source_id": "wamid.SECRET",
                },
            }

        first = truth.reconcile_delivery_attempt(current, load, record)
        replay = truth.reconcile_delivery_attempt(current, load, record)
        self.assertEqual(first["delivery_state"], truth.PROVIDER_DELIVERED)
        self.assertTrue(first["transition_created"])
        self.assertFalse(replay["transition_created"])
        self.assertFalse(first["send_attempted"])
        self.assertTrue(first["customer_send_confirmed"])

    def test_reconciliation_identity_mismatch_fails_closed(self):
        current = {
            **attempt(),
            "chatwoot_outgoing_message_id": "759446597",
        }
        result = truth.reconcile_delivery_attempt(
            current,
            lambda *_args: {
                "status_code": 200,
                "body": {
                    "id": "different",
                    "conversation_id": "2013",
                    "status": "delivered",
                },
            },
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "delivery_reconciliation_identity_mismatch")
        self.assertFalse(result["send_attempted"])

    def test_short_unverified_latency_has_no_exception_and_aged_has_one(self):
        self.assertFalse(truth.delivery_exception_required(
            truth.CHATWOOT_ACCEPTED_UNVERIFIED,
            age_seconds=299,
        ))
        self.assertTrue(truth.delivery_exception_required(
            truth.CHATWOOT_ACCEPTED_UNVERIFIED,
            age_seconds=300,
        ))
        self.assertTrue(truth.delivery_exception_required(truth.PROVIDER_FAILED))
        self.assertTrue(truth.delivery_exception_required(truth.PROVIDER_OUTCOME_AMBIGUOUS))

    def test_conversation_chain_recovers_attempt_and_distinct_outcomes(self):
        current = attempt()
        claim = truth.build_delivery_claim_event(current)
        sent = truth.build_delivery_transition_event(
            current,
            truth.classify_chatwoot_response({
                "status_code": 200,
                "body": {"id": "759446597", "status": "sent"},
            }),
        )
        delivered = truth.build_delivery_transition_event(
            current,
            truth.classify_chatwoot_response({
                "status_code": 200,
                "body": {"id": "759446597", "status": "delivered"},
            }),
        )
        chain = truth.sanitized_attempt_chain(
            [claim, sent, delivered],
            "2013",
            current["delivery_attempt_id"],
        )
        self.assertEqual(
            [row["delivery_state"] for row in chain],
            [
                truth.ATTEMPT_CLAIMED,
                truth.CHATWOOT_ACCEPTED_UNVERIFIED,
                truth.PROVIDER_DELIVERED,
            ],
        )
        self.assertEqual(len({row["review_event_id"] for row in chain}), 3)
        self.assertTrue(chain[-1]["customer_send_confirmed"])


if __name__ == "__main__":
    unittest.main()
