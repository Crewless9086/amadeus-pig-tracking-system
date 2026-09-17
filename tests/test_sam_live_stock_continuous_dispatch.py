import unittest

from modules.sales.sam_live_stock_continuous_dispatch import (
    build_continuous_dispatch,
    build_delivery_owner_exception,
)


class SamLiveStockContinuousDispatchTests(unittest.TestCase):
    def payload(self, message_id="766408519"):
        return {
            "event": "message_created",
            "id": message_id,
            "message_type": "incoming",
            "private": False,
            "account": {"id": "147387"},
            "conversation": {
                "id": "2102",
                "inbox": {
                    "id": "96568",
                    "channel_type": "Channel::Whatsapp",
                },
            },
            "sender": {"id": "987120708"},
        }

    def dispatch(self, payload=None, **changes):
        return build_continuous_dispatch(
            payload or self.payload(),
            expected_account_id="147387",
            expected_inbox_id="96568",
            presented_webhook_token="x" * 40,
            expected_webhook_token="x" * 40,
            **changes,
        )

    def test_post_cohort_inbound_builds_fresh_automatic_operation(self):
        result = self.dispatch(
            prior_consumed_inbound_ids=["765858272"],
        )
        self.assertTrue(result["should_relay"])
        self.assertEqual(
            result["identity"]["inbound_message_id"],
            "766408519",
        )
        self.assertTrue(result["identity"]["operation_id"].startswith(
            "SAM-CONTINUOUS-"
        ))

    def test_only_same_inbound_idempotency_suppresses(self):
        prior = self.dispatch(
            prior_consumed_inbound_ids=["765858272"],
        )
        replay = self.dispatch(
            prior_consumed_inbound_ids=["765858272", "766408519"],
        )
        self.assertTrue(prior["should_relay"])
        self.assertFalse(replay["should_relay"])
        self.assertIn("same_inbound_not_consumed", replay["blockers"])

    def test_ambiguous_historical_attempt_does_not_block_new_inbound(self):
        result = self.dispatch(
            quarantined_inbound_ids=["765549270", "765538547", "765507219"],
        )
        self.assertTrue(result["should_relay"])
        self.assertFalse(result["automatic_retry_authorized"])

    def test_same_ambiguous_inbound_never_retries(self):
        result = self.dispatch(
            quarantined_inbound_ids=["766408519"],
        )
        self.assertFalse(result["should_relay"])
        self.assertIn("same_inbound_not_quarantined", result["blockers"])

    def test_customer_silence_has_no_webhook_and_no_operation(self):
        payload = self.payload()
        payload["event"] = "conversation_updated"
        self.assertFalse(self.dispatch(payload)["should_relay"])

    def test_missing_or_invalid_webhook_auth_never_relays(self):
        missing = build_continuous_dispatch(
            self.payload(),
            expected_account_id="147387",
            expected_inbox_id="96568",
        )
        invalid = build_continuous_dispatch(
            self.payload(),
            expected_account_id="147387",
            expected_inbox_id="96568",
            presented_webhook_token="a" * 40,
            expected_webhook_token="b" * 40,
        )
        self.assertFalse(missing["should_relay"])
        self.assertFalse(invalid["should_relay"])
        self.assertIn("webhook_authenticated", invalid["blockers"])

    def test_non_livestock_inbox_is_not_relayed(self):
        payload = self.payload()
        payload["conversation"]["inbox"]["id"] = "other"
        self.assertFalse(self.dispatch(payload)["should_relay"])

    def test_riversdale_delivery_builds_one_precise_owner_exception(self):
        exception = build_delivery_owner_exception(
            inbound={
                "account_id": "147387",
                "inbox_id": "96568",
                "conversation_id": "1338",
                "contact_id": "766787061",
                "message_id": "766413218",
            },
            facts={
                "location": "Riversdale",
                "transport_expectation": "delivery_requested",
            },
        )
        self.assertTrue(exception["telegram_required"])
        self.assertIn("delivery to Riversdale", exception["decision_required"])
        self.assertFalse(exception["customer_delivery_promised"])


if __name__ == "__main__":
    unittest.main()
