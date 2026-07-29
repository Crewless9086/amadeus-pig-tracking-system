import unittest
from datetime import datetime, timezone

from modules.sales.sam_live_stock_inbox_operator import (
    operate_livestock_inbox,
)


class SamLiveStockInboxOperatorTests(unittest.TestCase):
    def row(self, cid, can_reply=True):
        return {
            "id": cid,
            "account_id": 147387,
            "inbox_id": 96568,
            "can_reply": can_reply,
            "meta": {"sender": {"id": f"contact-{cid}", "name": "Customer"}},
        }

    def page(self, rows):
        return {
            "data": {
                "meta": {"all_count": len(rows)},
                "payload": rows,
            }
        }

    def history(self, message_id, content, incoming=True):
        return {
            "success": True,
            "status": "chatwoot_conversation_history_loaded",
            "messages": [
                {
                    "id": message_id,
                    "created_at": 100,
                    "message_type": 0 if incoming else 1,
                    "private": False,
                    "content": content,
                }
            ],
        }

    def test_processes_current_livestock_and_not_meat(self):
        rows = [self.row("1"), self.row("2")]
        histories = {
            "1": self.history("101", "I want five weaned piglets"),
            "2": self.history("102", "I want pork chops"),
        }
        calls = []
        packet = operate_livestock_inbox(
            environ={},
            conversation_page_loader=lambda page: self.page(rows),
            history_loader=lambda cid, _env: (histories[cid], 200),
            claim_exists=lambda cid, mid: False,
            inbound_processor=lambda payload: (
                calls.append(str(payload["conversation"]["id"]))
                or {
                    "sam_decision": {
                        "routine_reply_delivery": {
                            "delivery_outcome": {
                                "delivery_state": "provider_delivered"
                            }
                        }
                    }
                }
            ),
            now=datetime(2026, 7, 29, tzinfo=timezone.utc),
        )
        self.assertEqual(calls, ["1"])
        self.assertEqual(packet["customers_answered"], 1)

    def test_exact_claim_suppresses_only_that_inbound(self):
        rows = [self.row("1"), self.row("2")]
        histories = {
            "1": self.history("101", "I want piglets"),
            "2": self.history("202", "I want weaned piglets"),
        }
        calls = []
        operate_livestock_inbox(
            environ={},
            conversation_page_loader=lambda page: self.page(rows),
            history_loader=lambda cid, _env: (histories[cid], 200),
            claim_exists=lambda cid, mid: mid == "101",
            inbound_processor=lambda payload: (
                calls.append(str(payload["conversation"]["id"]))
                or {"sam_decision": {}}
            ),
        )
        self.assertEqual(calls, ["2"])

    def test_closed_window_is_not_sent(self):
        rows = [self.row("1", can_reply=False)]
        calls = []
        packet = operate_livestock_inbox(
            environ={},
            conversation_page_loader=lambda page: self.page(rows),
            history_loader=lambda cid, _env: (
                self.history("101", "I want piglets"),
                200,
            ),
            claim_exists=lambda cid, mid: False,
            inbound_processor=lambda payload: calls.append(payload),
        )
        self.assertFalse(calls)
        self.assertEqual(
            packet["dispositions"][0]["disposition"],
            "closed_window_reengagement_required",
        )

    def test_real_loader_shape_is_eligible_without_synthetic_evidence_flag(self):
        calls = []
        packet = operate_livestock_inbox(
            environ={},
            conversation_page_loader=lambda page: self.page([self.row("1")]),
            history_loader=lambda cid, _env: (
                self.history("101", "I want five weaned piglets"),
                200,
            ),
            claim_exists=lambda cid, mid: False,
            inbound_processor=lambda payload: (
                calls.append(payload["id"]) or {"sam_decision": {}}
            ),
        )
        self.assertEqual(calls, ["101"])
        self.assertTrue(packet["dispositions"][0]["eligible"])

    def test_authoritative_livestock_context_preserves_terse_followup(self):
        history = {
            "success": True,
            "status": "chatwoot_conversation_history_loaded",
            "messages": [
                {
                    "id": 100,
                    "created_at": 100,
                    "message_type": 0,
                    "private": False,
                    "content": "I want five weaned piglets",
                },
                {
                    "id": 101,
                    "created_at": 101,
                    "message_type": 0,
                    "private": False,
                    "content": "Riversdale",
                },
            ],
        }
        calls = []
        packet = operate_livestock_inbox(
            environ={},
            conversation_page_loader=lambda page: self.page([self.row("1")]),
            history_loader=lambda cid, _env: (history, 200),
            claim_exists=lambda cid, mid: False,
            inbound_processor=lambda payload: (
                calls.append(payload["id"]) or {"sam_decision": {}}
            ),
        )
        self.assertEqual(calls, [101])
        self.assertEqual(
            packet["dispositions"][0]["final_route"], "AUTO_SPECIALIST"
        )


if __name__ == "__main__":
    unittest.main()
