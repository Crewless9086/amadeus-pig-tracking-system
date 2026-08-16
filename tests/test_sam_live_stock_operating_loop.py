import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from modules.sales import sam_live_stock_operating_loop as loop


class Store:
    def __init__(self, acquired=True):
        self.acquired = acquired
        self.proposals = []
        self.completions = []

    def acquire_cycle(self, **kwargs):
        return {"acquired": self.acquired,
                "next_cycle_at": kwargs["next_cycle_at"].isoformat()}

    def record_proposal(self, proposal):
        self.proposals.append(proposal)

    def proposal_exists(self, identity):
        return any(all(row[key] == value for key, value in identity.items())
                   for row in self.proposals)

    def record_dispositions(self, dispositions, **identity):
        self.dispositions = list(dispositions)

    def complete_cycle(self, **kwargs):
        self.completions.append(kwargs)


class SamLiveStockOperatingLoopTests(unittest.TestCase):
    def test_disabled_loop_is_inert(self):
        result = loop.run_sam_live_stock_operating_cycle(environ={})
        self.assertEqual(result["status"], "sam_live_stock_operating_loop_disabled")
        self.assertEqual(result["customer_sends"], 0)

    def test_non_shadow_mode_is_contained(self):
        result = loop.run_sam_live_stock_operating_cycle(environ={
            loop.ENABLED_ENV: "true", loop.MODE_ENV: "dispatch",
        })
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "sam_live_stock_operating_loop_mode_contained")

    def test_lease_prevents_duplicate_cycle(self):
        calls = []
        result = loop.run_sam_live_stock_operating_cycle(
            environ={loop.ENABLED_ENV: "true"}, store=Store(False),
            operator=lambda *_args: calls.append(True),
            now=datetime(2026, 8, 16, tzinfo=timezone.utc),
        )
        self.assertEqual(calls, [])
        self.assertEqual(result["status"], "sam_live_stock_operating_loop_lease_held")

    def test_shadow_cycle_persists_exact_digest_without_effects(self):
        store = Store()

        def operator(_source, processor):
            payload = {"id": "m1", "created_at": 1786874400,
                       "account": {"id": "a1"},
                       "conversation": {"id": "c1"},
                       "sender": {"id": "p1"}}
            processor(payload)
            return {"inventory_count": 1,
                    "dispositions": [{"eligible": True}]}

        with patch.object(loop, "_compose_shadow_proposal", return_value={
            "sam_decision": {"suggested_reply_text": "One useful question"}
        }):
            result = loop.run_sam_live_stock_operating_cycle(
                environ={loop.ENABLED_ENV: "true", "RENDER_INSTANCE_ID": "worker-1"},
                store=store, operator=operator,
                now=datetime(2026, 8, 16, tzinfo=timezone.utc),
            )
        self.assertEqual(result["shadow_proposal_count"], 1)
        self.assertEqual(store.proposals[0]["response_digest"],
                         "e4aeecb35592b9e16ccafdac1a2074d116a9d5d05e264fd82fc2e38cdfe6aafd")
        self.assertEqual(result["customer_sends"], 0)
        self.assertEqual(result["owner_cards"], 0)
        self.assertEqual(store.completions[0]["status"], "completed")

    def test_shadow_proposal_replay_has_zero_composition_effect(self):
        store = Store()
        store.proposals.append({"account_id": "a1", "conversation_id": "c1",
                                "inbound_message_id": "m1", "contact_id": "p1"})

        def operator(_source, processor):
            result = processor({"id": "m1", "created_at": 1786874400,
                                "account": {"id": "a1"},
                                "conversation": {"id": "c1"},
                                "sender": {"id": "p1"}})
            self.assertEqual(result["status"], "shadow_proposal_replay_suppressed")
            return {"inventory_count": 1, "dispositions": []}

        with patch.object(loop, "_compose_shadow_proposal") as compose:
            result = loop.run_sam_live_stock_operating_cycle(
                environ={loop.ENABLED_ENV: "true"}, store=store,
                operator=operator,
                now=datetime(2026, 8, 16, tzinfo=timezone.utc),
            )
        compose.assert_not_called()
        self.assertEqual(result["shadow_proposal_count"], 0)

    def test_start_gate_never_starts_dispatch_mode(self):
        with patch.object(loop.threading, "Thread") as thread:
            self.assertFalse(loop.start_sam_live_stock_operating_loop(environ={
                loop.ENABLED_ENV: "true", loop.MODE_ENV: "dispatch",
            }))
            thread.assert_not_called()


if __name__ == "__main__":
    unittest.main()
