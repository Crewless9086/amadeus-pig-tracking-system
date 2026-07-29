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

    def page_with_total(self, rows, total):
        return {
            "data": {
                "meta": {"all_count": total},
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

    def test_provider_row_prefilter_avoids_history_for_noncandidate_pages(self):
        rows = []
        for value in range(25):
            row = self.row(str(value), can_reply=False)
            row["last_non_activity_message"] = {
                "id": 1000 + value,
                "created_at": 100,
                "message_type": 1,
                "private": False,
            }
            rows.append(row)
        loaded_pages = []
        histories = []
        packet = operate_livestock_inbox(
            environ={},
            conversation_page_loader=lambda page: (
                loaded_pages.append(page) or self.page(rows)
            ),
            history_loader=lambda cid, _env: (
                histories.append(cid) or ({}, 500)
            ),
            claim_exists=lambda cid, mid: False,
            inbound_processor=lambda payload: self.fail(
                "noncandidate must never process"
            ),
        )
        self.assertEqual(loaded_pages, [1])
        self.assertEqual(histories, [])
        self.assertEqual(packet["inventory_scope"], "recent_open_window_boundary")

    def test_provider_latest_exact_claim_skips_history_and_never_retries(self):
        row = self.row("2102")
        row["last_non_activity_message"] = {
            "id": 766572767,
            "created_at": 1785356464,
            "message_type": 0,
            "private": False,
        }
        histories = []
        packet = operate_livestock_inbox(
            environ={},
            conversation_page_loader=lambda page: self.page([row]),
            history_loader=lambda cid, _env: (
                histories.append(cid) or ({}, 500)
            ),
            claim_exists=lambda cid, mid: (
                cid == "2102" and mid == "766572767"
            ),
            inbound_processor=lambda payload: self.fail(
                "claimed inbound must never process"
            ),
        )
        self.assertEqual(histories, [])
        self.assertEqual(
            packet["dispositions"][0]["disposition"], "already_claimed"
        )

    def test_replyable_pending_livestock_conversation_remains_eligible(self):
        row = self.row("2200")
        row["status"] = "pending"
        row["last_non_activity_message"] = {
            "id": 800001,
            "created_at": 1785357000,
            "message_type": 0,
            "private": False,
        }
        calls = []
        packet = operate_livestock_inbox(
            environ={},
            conversation_page_loader=lambda page: self.page([row]),
            history_loader=lambda cid, _env: (
                self.history("800001", "I want five weaned piglets"),
                200,
            ),
            claim_exists=lambda cid, mid: False,
            inbound_processor=lambda payload: (
                calls.append(payload["id"]) or {"sam_decision": {}}
            ),
        )
        self.assertEqual(calls, ["800001"])
        self.assertTrue(packet["dispositions"][0]["eligible"])

    def test_short_first_page_with_larger_total_fails_closed(self):
        with self.assertRaisesRegex(
            RuntimeError, "chatwoot_inventory_short_page_unproven"
        ):
            operate_livestock_inbox(
                environ={},
                conversation_page_loader=lambda page: self.page_with_total(
                    [self.row("1")], 2
                ),
                history_loader=lambda cid, _env: ({}, 500),
                claim_exists=lambda cid, mid: False,
                inbound_processor=lambda payload: {},
            )

    def test_short_later_page_with_remaining_total_fails_closed(self):
        first = [self.row(str(value)) for value in range(25)]
        later = [self.row("25")]
        with self.assertRaisesRegex(
            RuntimeError, "chatwoot_inventory_short_page_unproven"
        ):
            operate_livestock_inbox(
                environ={},
                conversation_page_loader=lambda page: (
                    self.page_with_total(first, 50)
                    if page == 1
                    else self.page_with_total(later, 50)
                ),
                history_loader=lambda cid, _env: ({}, 500),
                claim_exists=lambda cid, mid: False,
                inbound_processor=lambda payload: {},
            )

    def test_provider_total_change_fails_closed(self):
        first = [self.row(str(value)) for value in range(25)]
        second = [self.row(str(25 + value)) for value in range(25)]
        with self.assertRaisesRegex(
            RuntimeError, "chatwoot_inventory_changed"
        ):
            operate_livestock_inbox(
                environ={},
                conversation_page_loader=lambda page: (
                    self.page_with_total(first, 50)
                    if page == 1
                    else self.page_with_total(second, 51)
                ),
                history_loader=lambda cid, _env: ({}, 500),
                claim_exists=lambda cid, mid: False,
                inbound_processor=lambda payload: {},
            )

    def test_ten_full_replyable_pages_fail_closed(self):
        def load(page):
            rows = [
                self.row(str((page - 1) * 25 + value))
                for value in range(25)
            ]
            return self.page_with_total(rows, 1000)

        with self.assertRaisesRegex(
            RuntimeError, "chatwoot_open_window_inventory_boundary_unproven"
        ):
            operate_livestock_inbox(
                environ={},
                conversation_page_loader=load,
                history_loader=lambda cid, _env: ({}, 500),
                claim_exists=lambda cid, mid: False,
                inbound_processor=lambda payload: {},
            )


if __name__ == "__main__":
    unittest.main()
