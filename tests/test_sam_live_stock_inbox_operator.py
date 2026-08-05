import unittest
import threading
import urllib.error
from datetime import datetime, timezone

from modules.sales.sam_live_stock_inbox_operator import (
    SamInboxOperationFailure,
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

    def test_exact_accepted_attempt_is_durable_pending_provider_work(self):
        packet = operate_livestock_inbox(
            environ={},
            conversation_page_loader=lambda page: self.page([self.row("1")]),
            history_loader=lambda cid, _env: (
                self.history("101", "I want five weaned piglets"),
                200,
            ),
            claim_exists=lambda cid, mid: False,
            inbound_processor=lambda payload: {
                "processed": True,
                "sent": False,
                "_operation_status_code": 200,
                "sam_decision": {
                    "routine_reply_delivery": {
                        "claim": {
                            "success": True,
                            "created": True,
                            "delivery_attempt_id": "ATTEMPT-EXACT",
                        },
                        "delivery_outcome": {
                            "delivery_state": (
                                "chatwoot_accepted_unverified"
                            ),
                        },
                        "automatic_retry_prohibited": True,
                    }
                },
            },
        )
        self.assertEqual(
            sum(
                row["selected_for_processing"]
                for row in packet["dispositions"]
            ),
            1,
        )
        self.assertEqual(
            packet["dispositions"][0]["provider_state"],
            "chatwoot_accepted_unverified",
        )
        self.assertFalse(packet["dispositions"][0]["provider_confirmed"])

    def test_selected_payload_reuses_exact_authoritative_history(self):
        row = self.row("1")
        history = self.history("101", "I want five weaned piglets")
        captured = []
        operate_livestock_inbox(
            environ={},
            conversation_page_loader=lambda page: self.page([row]),
            history_loader=lambda cid, _env: (history, 200),
            claim_exists=lambda cid, mid: False,
            inbound_processor=lambda payload: (
                captured.append(payload)
                or {"sam_decision": {}}
            ),
        )
        self.assertIs(
            captured[0]["_sam_authoritative_history"], history
        )

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
                or {
                    "processed": True,
                    "sent": True,
                    "_operation_status_code": 200,
                    "sam_decision": {},
                }
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
        self.assertEqual(
            packet["inventory_scope"], "full_provider_conversation_inventory"
        )

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
            RuntimeError, "chatwoot_inventory_incomplete"
        ):
            operate_livestock_inbox(
                environ={},
                conversation_page_loader=lambda page: (
                    self.page_with_total([self.row("1")], 2)
                    if page == 1
                    else self.page_with_total([], 2)
                ),
                history_loader=lambda cid, _env: ({}, 500),
                claim_exists=lambda cid, mid: False,
                inbound_processor=lambda payload: {},
            )

    def test_short_later_page_with_remaining_total_fails_closed(self):
        first = [self.row(str(value)) for value in range(25)]
        later = [self.row("25")]
        with self.assertRaisesRegex(
            RuntimeError, "chatwoot_inventory_incomplete"
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

    def test_provider_total_change_remains_systemic_when_transport_isolation_enabled(self):
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
                isolate_provider_read_failures=True,
            )

    def test_http_auth_failure_is_systemic_not_partial_transport(self):
        first = [self.row(str(value)) for value in range(25)]

        def page_loader(page):
            if page == 1:
                return self.page_with_total(first, 50)
            raise urllib.error.HTTPError(
                "https://chatwoot.test/page/2", 401, "denied", {}, None
            )

        with self.assertRaises(urllib.error.HTTPError):
            operate_livestock_inbox(
                environ={},
                conversation_page_loader=page_loader,
                history_loader=lambda cid, _env: ({}, 500),
                claim_exists=lambda cid, mid: False,
                inbound_processor=lambda payload: {},
                isolate_provider_read_failures=True,
            )

    def test_nontransport_history_failure_is_systemic(self):
        row = self.row("1")
        row["last_non_activity_message"] = {
            "id": 750001,
            "created_at": 100,
            "message_type": 0,
            "private": False,
        }
        with self.assertRaisesRegex(ValueError, "malformed chronology"):
            operate_livestock_inbox(
                environ={},
                conversation_page_loader=lambda page: self.page([row]),
                history_loader=lambda cid, _env: (_ for _ in ()).throw(
                    ValueError("malformed chronology")
                ),
                claim_exists=lambda cid, mid: False,
                inbound_processor=lambda payload: {},
                isolate_provider_read_failures=True,
            )

    def test_structured_history_auth_failure_is_systemic(self):
        row = self.row("1")
        row["last_non_activity_message"] = {
            "id": 760001,
            "created_at": 100,
            "message_type": 0,
            "private": False,
        }
        with self.assertRaisesRegex(
            RuntimeError, "chatwoot_candidate_history_unavailable"
        ):
            operate_livestock_inbox(
                environ={},
                conversation_page_loader=lambda page: self.page([row]),
                history_loader=lambda cid, _env: ({
                    "success": False,
                    "status": "chatwoot_history_http_401",
                    "messages": [],
                }, 503),
                claim_exists=lambda cid, mid: False,
                inbound_processor=lambda payload: {},
                isolate_provider_read_failures=True,
            )

    def test_later_replyable_pending_row_survives_noncandidate_first_page(self):
        first = []
        for value in range(25):
            row = self.row(str(value), can_reply=False)
            row["last_non_activity_message"] = {
                "id": 1000 + value,
                "created_at": 200 - value,
                "message_type": 1,
                "private": False,
            }
            first.append(row)
        pending = self.row("2200")
        pending["status"] = "pending"
        pending["last_non_activity_message"] = {
            "id": 800001,
            "created_at": 100,
            "message_type": 0,
            "private": False,
        }
        calls = []
        packet = operate_livestock_inbox(
            environ={},
            conversation_page_loader=lambda page: (
                self.page_with_total(first, 26)
                if page == 1
                else self.page_with_total([pending], 26)
            ),
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
        self.assertEqual(packet["inventory_count"], 26)

    def test_candidate_histories_are_prefetched_concurrently(self):
        rows = [self.row("1"), self.row("2")]
        for index, row in enumerate(rows, start=1):
            row["last_non_activity_message"] = {
                "id": 900000 + index,
                "created_at": 100 + index,
                "message_type": 0,
                "private": False,
            }
        barrier = threading.Barrier(2, timeout=2)

        def history(cid, _env):
            barrier.wait()
            return self.history(
                str(900000 + int(cid)), "I want weaned piglets"
            ), 200

        calls = []
        operate_livestock_inbox(
            environ={},
            conversation_page_loader=lambda page: self.page(rows),
            history_loader=history,
            claim_exists=lambda cid, mid: False,
            inbound_processor=lambda payload: (
                calls.append(str(payload["conversation"]["id"]))
                or {"sam_decision": {}}
            ),
        )
        self.assertEqual(sorted(calls), ["1", "2"])

    def test_one_candidate_history_failure_stops_before_any_processing(self):
        rows = [self.row("1"), self.row("2")]
        for index, row in enumerate(rows, start=1):
            row["last_non_activity_message"] = {
                "id": 910000 + index,
                "created_at": 100 + index,
                "message_type": 0,
                "private": False,
            }
        calls = []

        def history(cid, _env):
            if cid == "2":
                return {
                    "success": False,
                    "status": "chatwoot_history_http_503",
                    "messages": [],
                }, 200
            return self.history(
                str(910000 + int(cid)), "I want weaned piglets"
            ), 200

        with self.assertRaisesRegex(
            RuntimeError, "chatwoot_candidate_history_unavailable"
        ):
            operate_livestock_inbox(
                environ={},
                conversation_page_loader=lambda page: self.page(rows),
                history_loader=history,
                claim_exists=lambda cid, mid: False,
                inbound_processor=lambda payload: calls.append(payload),
            )
        self.assertEqual(calls, [])

    def test_exact_candidate_claims_are_loaded_in_one_batch(self):
        rows = [self.row("1"), self.row("2")]
        for index, row in enumerate(rows, start=1):
            row["last_non_activity_message"] = {
                "id": 920000 + index,
                "created_at": 100 + index,
                "message_type": 0,
                "private": False,
            }
        batches = []
        histories = []
        calls = []
        packet = operate_livestock_inbox(
            environ={},
            conversation_page_loader=lambda page: self.page(rows),
            history_loader=lambda cid, _env: (
                histories.append(cid)
                or self.history(
                    str(920000 + int(cid)), "I want weaned piglets"
                ),
                200,
            ),
            claim_exists=lambda cid, mid: self.fail(
                "provider latest claims must use the batch loader"
            ),
            claimed_inbound_loader=lambda identities: (
                batches.append(list(identities))
                or {("1", "920001")}
            ),
            inbound_processor=lambda payload: (
                calls.append(str(payload["conversation"]["id"]))
                or {"sam_decision": {}}
            ),
        )
        self.assertEqual(
            batches, [[("1", "920001"), ("2", "920002")]]
        )
        self.assertEqual(histories, ["2"])
        self.assertEqual(calls, ["2"])
        self.assertEqual(
            packet["dispositions"][0]["disposition"], "already_claimed"
        )

    def test_unresolved_ambiguous_attempt_quarantines_conversation(self):
        rows = [self.row("1159"), self.row("2")]
        for index, row in enumerate(rows, start=1):
            row["last_non_activity_message"] = {
                "id": 925000 + index,
                "created_at": 100 + index,
                "message_type": 0,
                "private": False,
            }
        histories = []
        calls = []
        packet = operate_livestock_inbox(
            environ={},
            conversation_page_loader=lambda page: self.page(rows),
            history_loader=lambda cid, _env: (
                histories.append(cid)
                or self.history(
                    str(925000 + (1 if cid == "1159" else 2)),
                    "I want weaned piglets",
                ),
                200,
            ),
            claim_exists=lambda cid, mid: False,
            claimed_inbound_loader=lambda identities: set(),
            quarantined_conversation_loader=lambda identities: {"1159"},
            inbound_processor=lambda payload: (
                calls.append(str(payload["conversation"]["id"]))
                or {"sam_decision": {}}
            ),
        )
        self.assertEqual(histories, ["2"])
        self.assertEqual(calls, ["2"])
        quarantined = next(
            row for row in packet["dispositions"]
            if row["conversation_id"] == "1159"
        )
        self.assertEqual(
            quarantined["disposition"],
            "delivery_quarantined_do_not_retry",
        )

    def test_bounded_cycle_processes_one_and_defers_other_eligible_work(self):
        rows = [self.row("1"), self.row("2")]
        for index, row in enumerate(rows, start=1):
            row["last_non_activity_message"] = {
                "id": 930000 + index,
                "created_at": 100 + index,
                "message_type": 0,
                "private": False,
            }
        calls = []
        packet = operate_livestock_inbox(
            environ={},
            conversation_page_loader=lambda page: self.page(rows),
            history_loader=lambda cid, _env: (
                self.history(
                    str(930000 + int(cid)), "I want weaned piglets"
                ),
                200,
            ),
            claim_exists=lambda cid, mid: False,
            claimed_inbound_loader=lambda identities: set(),
            max_process_count=1,
            inbound_processor=lambda payload: (
                calls.append(str(payload["conversation"]["id"]))
                or {
                    "processed": True,
                    "sent": True,
                    "_operation_status_code": 200,
                    "sam_decision": {},
                }
            ),
        )
        self.assertEqual(calls, ["1"])
        self.assertEqual(
            [row["disposition"] for row in packet["dispositions"]],
            ["processed", "deferred_to_next_autonomous_cycle"],
        )

    def test_oldest_eligible_is_selected_then_claim_advances_next_cycle(self):
        newer = self.row("2")
        older = self.row("1")
        newer["last_non_activity_message"] = {
            "id": 940002,
            "created_at": 200,
            "message_type": 0,
            "private": False,
        }
        older["last_non_activity_message"] = {
            "id": 940001,
            "created_at": 100,
            "message_type": 0,
            "private": False,
        }
        claims = set()
        calls = []

        def run():
            return operate_livestock_inbox(
                environ={},
                conversation_page_loader=lambda page: self.page(
                    [newer, older]
                ),
                history_loader=lambda cid, _env: (
                    self.history(
                        str(940000 + int(cid)), "I want weaned piglets"
                    ),
                    200,
                ),
                claim_exists=lambda cid, mid: (cid, mid) in claims,
                claimed_inbound_loader=lambda identities: claims,
                max_process_count=1,
                inbound_processor=lambda payload: (
                    calls.append(str(payload["conversation"]["id"]))
                    or claims.add(
                        (
                            str(payload["conversation"]["id"]),
                            str(payload["id"]),
                        )
                    )
                    or {
                        "processed": True,
                        "sent": True,
                        "_operation_status_code": 200,
                        "sam_decision": {},
                    }
                ),
            )

        first = run()
        self.assertEqual(calls, ["1"])
        self.assertEqual(
            [row["conversation_id"] for row in first["dispositions"][:2]],
            ["1", "2"],
        )
        run()
        self.assertEqual(calls, ["1", "2"])

    def test_failed_oldest_candidate_stops_lane_without_false_progress(self):
        rows = [self.row("1"), self.row("2")]
        for index, row in enumerate(rows, start=1):
            row["last_non_activity_message"] = {
                "id": 950000 + index,
                "created_at": 100 + index,
                "message_type": 0,
                "private": False,
            }
        calls = []
        with self.assertRaisesRegex(
            RuntimeError, "sam_selected_candidate_without_durable_disposition"
        ):
            operate_livestock_inbox(
                environ={},
                conversation_page_loader=lambda page: self.page(rows),
                history_loader=lambda cid, _env: (
                    self.history(
                        str(950000 + int(cid)), "I want weaned piglets"
                    ),
                    200,
                ),
                claim_exists=lambda cid, mid: False,
                claimed_inbound_loader=lambda identities: set(),
                max_process_count=1,
                inbound_processor=lambda payload: (
                    calls.append(str(payload["conversation"]["id"]))
                    or {
                        "processed": False,
                        "sent": False,
                        "_operation_status_code": 503,
                        "sam_decision": {},
                    }
                ),
            )
        self.assertEqual(calls, ["1"])

    def test_slow_inventory_page_isolated_before_claim_and_other_work_continues(self):
        first = []
        for value in range(25):
            row = self.row(str(value), can_reply=value == 0)
            row["last_non_activity_message"] = {
                "id": 960000 + value,
                "created_at": 100 + value,
                "message_type": 0 if value == 0 else 1,
                "private": False,
            }
            first.append(row)
        calls = []
        attention_states = []

        def page_loader(page):
            if page == 2:
                raise TimeoutError("bounded provider read")
            return self.page_with_total(first, 50)

        packet = operate_livestock_inbox(
            environ={},
            conversation_page_loader=page_loader,
            history_loader=lambda cid, _env: (
                self.history("960000", "I want weaned piglets"), 200
            ),
            claim_exists=lambda cid, mid: False,
            claimed_inbound_loader=lambda identities: set(),
            inbound_processor=lambda payload: (
                calls.append(payload["id"])
                or {
                    "processed": True,
                    "sent": True,
                    "_operation_status_code": 200,
                    "sam_decision": {
                        "routine_reply_delivery": {
                            "delivery_outcome": {
                                "delivery_state": "provider_delivered"
                            }
                        }
                    },
                }
            ),
            isolate_provider_read_failures=True,
            max_process_count=1,
            attention_queue_operator=lambda rows, **kwargs: (
                attention_states.append(kwargs["sam_state"])
                or {"success": True}
            ),
        )
        self.assertEqual(calls, ["960000"])
        self.assertEqual(
            packet["inventory_scope"],
            "partial_provider_inventory_isolated",
        )
        self.assertEqual(packet["coverage_exception_count"], 1)
        self.assertEqual(
            packet["provider_read_failures"][0]["error_type"],
            "TimeoutError",
        )
        self.assertEqual(
            packet["owner_status_summary"]["lane_state"],
            "degraded_partial_provider_coverage",
        )
        self.assertEqual(
            packet["owner_status_summary"]["oldest_eligible_scope"],
            "unknown_partial_provider_inventory",
        )
        self.assertEqual(
            packet["owner_status_summary"]["oldest_eligible_unanswered_lead"],
            "",
        )
        self.assertEqual(
            attention_states[0]["state"],
            "degraded_partial_provider_coverage",
        )

    def test_one_slow_history_isolated_without_stopping_unrelated_candidate(self):
        rows = [self.row("1"), self.row("2")]
        for index, row in enumerate(rows, start=1):
            row["last_non_activity_message"] = {
                "id": 970000 + index,
                "created_at": 100 + index,
                "message_type": 0,
                "private": False,
            }
        calls = []

        def history(cid, _env):
            if cid == "1":
                raise TimeoutError("bounded chronology read")
            return self.history("970002", "I want weaned piglets"), 200

        packet = operate_livestock_inbox(
            environ={},
            conversation_page_loader=lambda page: self.page(rows),
            history_loader=history,
            claim_exists=lambda cid, mid: False,
            claimed_inbound_loader=lambda identities: set(),
            inbound_processor=lambda payload: (
                calls.append(str(payload["conversation"]["id"]))
                or {
                    "processed": True,
                    "sent": True,
                    "_operation_status_code": 200,
                    "sam_decision": {
                        "routine_reply_delivery": {
                            "delivery_outcome": {
                                "delivery_state": "provider_delivered"
                            }
                        }
                    },
                }
            ),
            isolate_provider_read_failures=True,
            max_process_count=1,
        )
        self.assertEqual(calls, ["2"])
        failed = next(
            row for row in packet["dispositions"]
            if row["conversation_id"] == "1"
        )
        self.assertEqual(
            failed["disposition"], "provider_chronology_unavailable"
        )
        self.assertEqual(packet["coverage_exception_count"], 1)
        self.assertEqual(
            packet["owner_status_summary"]["customers_awaiting_sam"], 1
        )
        self.assertEqual(
            packet["owner_status_summary"]["coverage_exceptions"],
            [{"dependency": "chatwoot_conversation_history", "count": 1}],
        )

    def test_ambiguous_after_claim_is_durable_and_replay_never_sends(self):
        row = self.row("1")
        row["last_non_activity_message"] = {
            "id": 980001,
            "created_at": 100,
            "message_type": 0,
            "private": False,
        }
        claims = set()
        calls = []

        def run():
            return operate_livestock_inbox(
                environ={},
                conversation_page_loader=lambda page: self.page([row]),
                history_loader=lambda cid, _env: (
                    self.history("980001", "I want weaned piglets"), 200
                ),
                claim_exists=lambda cid, mid: (cid, mid) in claims,
                claimed_inbound_loader=lambda identities: claims,
                inbound_processor=lambda payload: (
                    calls.append(payload["id"])
                    or claims.add(("1", "980001"))
                    or {
                        "processed": True,
                        "sent": False,
                        "_operation_status_code": 200,
                        "sam_decision": {
                            "reason": "routine_reply_delivery_ambiguous",
                            "routine_reply_delivery": {
                                "claim": {
                                    "success": True,
                                    "created": True,
                                    "delivery_attempt_id": "ATTEMPT-980001",
                                },
                                "delivery_outcome": {
                                    "delivery_state": "provider_outcome_ambiguous"
                                },
                                "automatic_retry_prohibited": True,
                            },
                        },
                    }
                ),
                max_process_count=1,
            )

        first = run()
        second = run()
        self.assertEqual(calls, ["980001"])
        self.assertEqual(
            first["dispositions"][0]["provider_state"],
            "provider_outcome_ambiguous",
        )
        self.assertEqual(
            second["dispositions"][0]["disposition"], "already_claimed"
        )

    def test_timeout_before_claim_is_explicit_and_creates_no_claim(self):
        row = self.row("1")
        row["last_non_activity_message"] = {
            "id": 990001,
            "created_at": 100,
            "message_type": 0,
            "private": False,
        }
        claims = set()
        with self.assertRaises(SamInboxOperationFailure) as raised:
            operate_livestock_inbox(
                environ={},
                conversation_page_loader=lambda page: self.page([row]),
                history_loader=lambda cid, _env: (
                    self.history("990001", "I want weaned piglets"), 200
                ),
                claim_exists=lambda cid, mid: (cid, mid) in claims,
                claimed_inbound_loader=lambda identities: claims,
                inbound_processor=lambda payload: (_ for _ in ()).throw(
                    TimeoutError("planning deadline")
                ),
                max_process_count=1,
            )
        self.assertEqual(raised.exception.stage, "preclaim_response_processing")
        self.assertEqual(raised.exception.effect_boundary, "not_crossed")
        self.assertEqual(claims, set())

    def test_timeout_after_claim_is_explicit_and_replay_is_withheld(self):
        row = self.row("1")
        row["last_non_activity_message"] = {
            "id": 995001,
            "created_at": 100,
            "message_type": 0,
            "private": False,
        }
        claims = set()
        calls = []

        def processor(payload):
            calls.append(payload["id"])
            claims.add(("1", "995001"))
            raise TimeoutError("provider boundary indeterminate")

        with self.assertRaises(SamInboxOperationFailure) as raised:
            operate_livestock_inbox(
                environ={},
                conversation_page_loader=lambda page: self.page([row]),
                history_loader=lambda cid, _env: (
                    self.history("995001", "I want weaned piglets"), 200
                ),
                claim_exists=lambda cid, mid: (cid, mid) in claims,
                claimed_inbound_loader=lambda identities: claims,
                inbound_processor=processor,
                max_process_count=1,
            )
        self.assertEqual(raised.exception.stage, "post_claim_processing")
        self.assertEqual(raised.exception.effect_boundary, "crossed")

        replay = operate_livestock_inbox(
            environ={},
            conversation_page_loader=lambda page: self.page([row]),
            history_loader=lambda cid, _env: self.fail(
                "claimed replay must not load chronology"
            ),
            claim_exists=lambda cid, mid: (cid, mid) in claims,
            claimed_inbound_loader=lambda identities: claims,
            inbound_processor=processor,
            max_process_count=1,
        )
        self.assertEqual(calls, ["995001"])
        self.assertEqual(
            replay["dispositions"][0]["disposition"], "already_claimed"
        )


if __name__ == "__main__":
    unittest.main()
