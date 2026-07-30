import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from app import app
from modules.sales import meat_pilot_readiness, sales_transaction_routes


class SalesTransactionRoutesTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()
        self.owner_money_path_guard = patch.object(
            sales_transaction_routes,
            "_require_owner_meat_money_path_access",
            return_value=None,
        )
        self.owner_money_path_guard.start()
        self.addCleanup(self.owner_money_path_guard.stop)

    def test_inbox_operator_admits_only_provider_current_backlog_path(self):
        history = {"success": True, "messages": [{"id": "INBOUND"}]}
        with patch.object(
            sales_transaction_routes,
            "handle_sam_live_stock_chatwoot_inbound",
            return_value=({"processed": False}, 200),
        ) as handle:
            result = (
                sales_transaction_routes
                ._operate_sam_live_stock_exact_payload({
                    "id": "INBOUND",
                    "_sam_authoritative_history": history,
                })
            )
        self.assertEqual(result["_operation_status_code"], 200)
        self.assertTrue(
            handle.call_args.kwargs["allow_provider_current_backlog"]
        )
        self.assertIs(
            handle.call_args.kwargs["conversation_history_loader"](),
            history,
        )
        self.assertIs(
            handle.call_args.kwargs["preclaim_chronology_verifier"],
            sales_transaction_routes.verify_chatwoot_current_inbound,
        )

    def test_operator_isolates_post_send_review_adjunct_failure(self):
        result = {
            "processed": True,
            "sent": True,
            "sam_decision": {
                "sales_lane": "live_stock_sales",
                "specialist_lane_selected": True,
                "routine_reply_delivery": {
                    "claim": {
                        "success": True,
                        "created": True,
                        "delivery_attempt_id": "ATTEMPT-EXACT",
                    },
                    "delivery_outcome": {
                        "delivery_state": "provider_delivered",
                    },
                },
            },
        }
        with patch.object(
            sales_transaction_routes,
            "handle_sam_live_stock_chatwoot_inbound",
            return_value=(result, 200),
        ), patch.object(
            sales_transaction_routes,
            "_attach_sam_live_stock_review_event",
            side_effect=RuntimeError("post-send observer failed"),
        ), patch.object(
            sales_transaction_routes,
            "_apply_sam_live_stock_operational_state",
            return_value={
                "applied": True,
                "status": "awaiting_customer",
            },
        ) as apply_state:
            operated = (
                sales_transaction_routes
                ._operate_sam_live_stock_exact_payload({
                    "id": "INBOUND-EXACT",
                    "_sam_authoritative_history": {
                        "success": True,
                        "messages": [{"id": "INBOUND-EXACT"}],
                    },
                })
            )
        self.assertEqual(operated["_operation_status_code"], 200)
        self.assertTrue(operated["sent"])
        self.assertEqual(
            operated["conversation_review_event"]["status"],
            "post_send_review_adjunct_failed_isolated",
        )
        self.assertFalse(
            operated["conversation_review_event"][
                "automatic_retry_authorized"
            ]
        )
        self.assertFalse(
            operated["conversation_review_event"][
                "adjunct_side_effects_known"
            ]
        )
        self.assertEqual(
            operated["conversation_review_event"][
                "telegram_notification_state"
            ],
            "unknown_after_exception",
        )
        self.assertTrue(operated["chatwoot_operational_state"]["applied"])
        apply_state.assert_called_once()

    def test_post_send_adjunct_failure_without_durable_outcome_fails_closed(
        self,
    ):
        result = {
            "processed": True,
            "sent": False,
            "sam_decision": {
                "routine_reply_delivery": {
                    "status": "routine_reply_review_blocked",
                },
            },
        }
        with patch.object(
            sales_transaction_routes,
            "_attach_sam_live_stock_review_event",
            side_effect=RuntimeError("audit unavailable"),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "audit unavailable"
            ):
                (
                    sales_transaction_routes
                    ._attach_sam_live_stock_review_event_safely(
                        result,
                        {"id": "INBOUND-NO-SEND"},
                    )
                )

    def test_accepted_send_reconciles_exact_terminal_attempt_without_resend(self):
        result = {
            "processed": True,
            "sent": False,
            "sam_decision": {
                "routine_reply_delivery": {
                    "claim": {
                        "success": True,
                        "created": True,
                        "conversation_id": "2100",
                        "delivery_attempt_id": "ATTEMPT-2100",
                    },
                    "delivery_outcome": {
                        "delivery_state": "chatwoot_accepted_unverified",
                        "customer_send_confirmed": False,
                    },
                },
            },
        }
        chains = [
            {
                "success": True,
                "conversation_id": "2100",
                "delivery_attempt_id": "ATTEMPT-2100",
                "latest_delivery_state": "chatwoot_accepted_unverified",
            },
            {
                "success": True,
                "conversation_id": "2100",
                "delivery_attempt_id": "ATTEMPT-2100",
                "latest_delivery_state": "provider_delivered",
                "customer_send_confirmed": True,
            },
        ]
        calls = []
        clock = [0.0]

        def load_chain(database_url, conversation_id, attempt_id):
            calls.append((conversation_id, attempt_id))
            return chains.pop(0)

        reconciled = (
            sales_transaction_routes
            ._reconcile_sam_live_stock_terminal_delivery(
                result,
                result["sam_decision"]["routine_reply_delivery"]["claim"],
                timeout_seconds=1,
                interval_seconds=0,
                chain_loader=load_chain,
                sleeper=lambda _seconds: clock.__setitem__(
                    0, clock[0] + 0.1
                ),
                monotonic=lambda: clock[0],
            )
        )
        self.assertTrue(reconciled)
        self.assertEqual(
            calls,
            [("2100", "ATTEMPT-2100"), ("2100", "ATTEMPT-2100")],
        )
        self.assertTrue(result["sent"])
        self.assertEqual(
            result["sam_decision"]["reason"],
            "routine_reply_confirmed_delivered",
        )
        self.assertEqual(
            result["sam_decision"]["routine_reply_delivery"][
                "delivery_outcome"
            ]["delivery_state"],
            "provider_delivered",
        )

    def test_accepted_send_reconciles_even_when_adjunct_succeeds(self):
        result = {
            "processed": True,
            "sent": False,
            "sam_decision": {
                "routine_reply_delivery": {
                    "claim": {
                        "success": True,
                        "created": True,
                        "conversation_id": "2100",
                        "delivery_attempt_id": "ATTEMPT-SUCCESSFUL-ADJUNCT",
                    },
                    "delivery_outcome": {
                        "delivery_state": "chatwoot_accepted_unverified",
                    },
                },
            },
        }
        with patch.object(
            sales_transaction_routes,
            "load_attempt_chain",
            return_value={
                "success": True,
                "conversation_id": "2100",
                "delivery_attempt_id": "ATTEMPT-SUCCESSFUL-ADJUNCT",
                "latest_delivery_state": "provider_delivered",
            },
        ) as load_chain, patch.object(
            sales_transaction_routes,
            "_attach_sam_live_stock_review_event",
        ) as attach:
            packet = (
                sales_transaction_routes
                ._attach_sam_live_stock_review_event_safely(
                    result,
                    {"id": "INBOUND-EXACT"},
                )
            )
        self.assertTrue(packet["success"])
        self.assertTrue(result["sent"])
        load_chain.assert_called_once()
        attach.assert_called_once()

    def test_accepted_send_without_terminal_chain_stays_fail_closed(self):
        result = {
            "processed": True,
            "sent": False,
            "sam_decision": {
                "routine_reply_delivery": {
                    "claim": {
                        "success": True,
                        "created": True,
                        "conversation_id": "2100",
                        "delivery_attempt_id": "ATTEMPT-PENDING",
                    },
                    "delivery_outcome": {
                        "delivery_state": "chatwoot_accepted_unverified",
                    },
                },
            },
        }
        with patch.object(
            sales_transaction_routes,
            "_attach_sam_live_stock_review_event",
            side_effect=RuntimeError("adjunct failed"),
        ), patch.object(
            sales_transaction_routes,
            "load_attempt_chain",
            return_value={
                "success": True,
                "conversation_id": "2100",
                "delivery_attempt_id": "ATTEMPT-PENDING",
                "latest_delivery_state": "chatwoot_accepted_unverified",
            },
        ), patch.object(
            sales_transaction_routes.time,
            "monotonic",
            side_effect=[0.0, 6.0],
        ), patch.object(sales_transaction_routes.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "adjunct failed"):
                (
                    sales_transaction_routes
                    ._attach_sam_live_stock_review_event_safely(
                        result,
                        {"id": "INBOUND-PENDING"},
                    )
                )

    def test_ambiguous_terminal_chain_is_quarantined_without_retry(self):
        result = {
            "processed": True,
            "sent": False,
            "sam_decision": {
                "routine_reply_delivery": {
                    "claim": {
                        "success": True,
                        "created": True,
                        "conversation_id": "198",
                        "delivery_attempt_id": "ATTEMPT-AMBIGUOUS",
                    },
                    "delivery_outcome": {
                        "delivery_state": "chatwoot_accepted_unverified",
                    },
                },
            },
        }
        reconciled = (
            sales_transaction_routes
            ._reconcile_sam_live_stock_terminal_delivery(
                result,
                result["sam_decision"]["routine_reply_delivery"]["claim"],
                timeout_seconds=0,
                interval_seconds=0,
                chain_loader=lambda *_args: {
                    "success": True,
                    "conversation_id": "198",
                    "delivery_attempt_id": "ATTEMPT-AMBIGUOUS",
                    "latest_delivery_state": "provider_outcome_ambiguous",
                },
                sleeper=lambda _seconds: None,
            )
        )
        self.assertTrue(reconciled)
        self.assertFalse(result["sent"])
        self.assertEqual(
            result["sam_decision"]["reason"],
            "routine_reply_delivery_ambiguous",
        )
        self.assertTrue(
            result["sam_decision"]["transition_visibility"][
                "automatic_retry_prohibited"
            ]
        )

    def test_terminal_chain_with_mismatched_identity_is_not_trusted(self):
        result = {
            "processed": True,
            "sent": False,
            "sam_decision": {
                "routine_reply_delivery": {
                    "claim": {
                        "success": True,
                        "created": True,
                        "conversation_id": "2100",
                        "delivery_attempt_id": "ATTEMPT-EXACT",
                    },
                    "delivery_outcome": {
                        "delivery_state": "chatwoot_accepted_unverified",
                    },
                },
            },
        }
        reconciled = (
            sales_transaction_routes
            ._reconcile_sam_live_stock_terminal_delivery(
                result,
                result["sam_decision"]["routine_reply_delivery"]["claim"],
                timeout_seconds=0,
                interval_seconds=0,
                chain_loader=lambda *_args: {
                    "success": True,
                    "conversation_id": "OTHER",
                    "delivery_attempt_id": "ATTEMPT-OTHER",
                    "latest_delivery_state": "provider_delivered",
                },
                sleeper=lambda _seconds: None,
            )
        )
        self.assertFalse(reconciled)
        self.assertFalse(result["sent"])
        self.assertEqual(
            result["sam_decision"]["routine_reply_delivery"][
                "delivery_outcome"
            ]["delivery_state"],
            "chatwoot_accepted_unverified",
        )

    def test_post_send_adjunct_partial_effects_are_reported_unknown(self):
        result = {
            "processed": True,
            "sent": True,
            "sam_decision": {
                "routine_reply_delivery": {
                    "claim": {
                        "success": True,
                        "created": True,
                        "delivery_attempt_id": "ATTEMPT-PARTIAL",
                    },
                    "delivery_outcome": {
                        "delivery_state": "provider_delivered",
                    },
                },
            },
        }
        with patch.object(
            sales_transaction_routes,
            "_attach_sam_live_stock_review_event",
            side_effect=RuntimeError("telegram outcome unknown"),
        ):
            isolated = (
                sales_transaction_routes
                ._attach_sam_live_stock_review_event_safely(
                    result,
                    {"id": "INBOUND-PARTIAL"},
                )
            )
        self.assertFalse(isolated["success"])
        packet = result["conversation_review_event"]
        self.assertFalse(packet["adjunct_side_effects_known"])
        self.assertEqual(
            packet["review_recording_state"],
            "unknown_after_exception",
        )
        self.assertEqual(
            packet["owner_work_state"],
            "unknown_after_exception",
        )
        self.assertEqual(
            packet["telegram_notification_state"],
            "unknown_after_exception",
        )

    def test_sam_owner_inbox_read_and_reconciliation_authorities_are_separate(self):
        loaded = {
            "success": True, "status": "owner_work_items_loaded", "items": [],
            "counts": {}, "evidence_complete": True,
        }
        with patch.object(sales_transaction_routes, "require_owner_read_access", return_value=None), \
             patch.object(sales_transaction_routes, "list_owner_work_items", return_value=(loaded, 200)):
            response = self.client.get("/api/sales/channels/chatwoot/sam/owner-inbox")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["items"], [])

        denied = ({"success": False, "status": "owner_admin_access_denied"}, 403)
        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=denied), \
             patch.object(sales_transaction_routes, "reconcile_live_human_conversation") as reconcile:
            response = self.client.post("/api/sales/channels/chatwoot/sam/owner-inbox/reconcile")
        self.assertEqual(response.status_code, 403)
        reconcile.assert_not_called()

    def test_sam_owner_inbox_reconciliation_does_not_accept_browser_evidence(self):
        result = {
            "success": True, "status": "owner_work_reconciliation_completed",
            "sends_customer_message": False, "changes_conversation_ownership": False,
            "calls_telegram": False, "mutates_business_state": False,
        }
        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=None), \
             patch.object(sales_transaction_routes, "owner_admin_principal", return_value="owner-admin:stable-server-derived"), \
             patch.object(sales_transaction_routes, "reconcile_live_human_conversation", return_value=(result, 200)) as reconcile:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam/owner-inbox/reconcile",
                json={
                    "conversation_id": "2025",
                    "expected_classification": "OWNERSHIP_DECISION_REQUIRED",
                    "owner_identity": "browser-spoof",
                },
            )
        self.assertEqual(response.status_code, 200)
        reconcile.assert_called_once_with(
            "2025",
            reconciliation_actor_id="owner-admin:stable-server-derived",
            expected_classification="OWNERSHIP_DECISION_REQUIRED",
        )

    def test_sam_owner_inventory_reconciliation_is_owner_admin_bounded_and_no_send(self):
        result = {
            "success": False,
            "status": "owner_inventory_reconciliation_incomplete",
            "evidence_complete": False,
            "next_cursor": "2029",
            "remaining_count": 1,
            "sends_customer_message": False,
            "changes_conversation_ownership": False,
            "calls_telegram": False,
            "mutates_business_state": False,
        }
        with patch.object(
            sales_transaction_routes, "require_owner_admin_access",
            return_value=None,
        ), patch.object(
            sales_transaction_routes, "owner_admin_principal",
            return_value="owner-admin:stable-server-derived",
        ), patch.object(
            sales_transaction_routes,
            "reconcile_configured_owner_inventory_batch",
            return_value=(result, 409),
        ) as reconcile:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam/owner-inbox/reconcile-inventory",
                json={
                    "cursor": "server-signed-cursor",
                    "limit": 2,
                    "expected_classification": "OWNERSHIP_DECISION_REQUIRED",
                    "owner_identity": "browser-spoof",
                },
            )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.get_json()["sends_customer_message"])
        reconcile.assert_called_once_with(
            reconciliation_actor_id="owner-admin:stable-server-derived",
            expected_classification="OWNERSHIP_DECISION_REQUIRED",
            cursor_token="server-signed-cursor",
            limit=2,
        )

    def test_sam_owner_inventory_reconciliation_preserves_invalid_zero_limit(self):
        with patch.object(
            sales_transaction_routes, "require_owner_admin_access",
            return_value=None,
        ), patch.object(
            sales_transaction_routes, "owner_admin_principal",
            return_value="owner-admin:stable-server-derived",
        ), patch.object(
            sales_transaction_routes,
            "reconcile_configured_owner_inventory_batch",
            return_value=({
                "success": False,
                "status": "owner_inventory_limit_invalid",
            }, 400),
        ) as reconcile:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam/owner-inbox/reconcile-inventory",
                json={"limit": 0},
            )
        self.assertEqual(response.status_code, 400)
        reconcile.assert_called_once_with(
            reconciliation_actor_id="owner-admin:stable-server-derived",
            expected_classification=None,
            cursor_token="",
            limit=0,
        )

    def test_owner_ownership_resolution_uses_only_server_principal(self):
        result = {
            "success": True, "status": "ownership_resolution_completed",
            "sends_customer_message": False, "calls_telegram": False,
            "mutates_business_state": False,
        }
        payload = {"work_item_id": "SAM-OWNER-WORK-1", "target_mode": "HUMAN"}
        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=None), \
             patch.object(sales_transaction_routes, "owner_admin_principal", return_value="owner-admin:server"), \
             patch.object(sales_transaction_routes, "resolve_owner_work_ownership", return_value=(result, 200)) as resolve:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam/owner-inbox/ownership",
                json={**payload, "actor_id": "browser-spoof"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["sends_customer_message"])
        resolve.assert_called_once_with(
            {**payload, "actor_id": "browser-spoof"}, actor_id="owner-admin:server"
        )

    def test_owner_ownership_resolution_requires_owner_admin(self):
        denied = ({"success": False, "status": "owner_admin_access_denied"}, 403)
        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=denied), \
             patch.object(sales_transaction_routes, "resolve_owner_work_ownership") as resolve:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam/owner-inbox/ownership",
                json={"target_mode": "HUMAN"},
            )
        self.assertEqual(response.status_code, 403)
        resolve.assert_not_called()

    def test_owner_ownership_recovery_is_owner_admin_and_server_derived(self):
        result = {
            "success": True, "status": "ownership_recovery_completed",
            "sends_customer_message": False, "calls_telegram": False,
            "mutates_business_state": False,
        }
        payload = {"work_item_id": "SAM-OWNER-WORK-1", "actor_id": "spoof"}
        with patch.object(
            sales_transaction_routes, "require_owner_admin_access",
            return_value=None,
        ), patch.object(
            sales_transaction_routes, "owner_admin_principal",
            return_value="owner-admin:server",
        ), patch.object(
            sales_transaction_routes,
            "recover_owner_work_ownership_observation",
            return_value=(result, 200),
        ) as recover:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam/owner-inbox/ownership/recover",
                json=payload,
            )
        self.assertEqual(response.status_code, 200)
        recover.assert_called_once_with(payload, actor_id="owner-admin:server")

    def test_owner_ownership_recovery_denied_has_zero_operation(self):
        denied = ({"success": False, "status": "owner_admin_access_denied"}, 403)
        with patch.object(
            sales_transaction_routes, "require_owner_admin_access",
            return_value=denied,
        ), patch.object(
            sales_transaction_routes,
            "recover_owner_work_ownership_observation",
        ) as recover:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam/owner-inbox/ownership/recover",
                json={},
            )
        self.assertEqual(response.status_code, 403)
        recover.assert_not_called()

    def test_charlie_daily_report_write_requires_owner_admin(self):
        denied = ({"success": False, "status": "owner_admin_access_denied"}, 403)
        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=denied), \
             patch.object(sales_transaction_routes, "run_daily_backlog_report") as report:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam/owner-inbox/charlie-report"
            )
        self.assertEqual(response.status_code, 403)
        report.assert_not_called()

    def test_beacon_follow_up_preview_is_read_only_and_owner_creation_is_separate(self):
        events = [{"performance_event_id": "e1"}, {"performance_event_id": "e2"}]
        suggestion = {"suggestion_id": "BEACON-FOLLOWUP-1", "title": "Follow up"}
        with patch.object(sales_transaction_routes, "require_owner_read_access", return_value=None), \
             patch.object(sales_transaction_routes, "list_beacon_campaign_performance_events", return_value=({"performance_events": events}, 200)), \
             patch.object(sales_transaction_routes, "build_beacon_follow_up_suggestions", return_value={"success": True, "suggestions": [suggestion]}) as analyze, \
             patch.object(sales_transaction_routes, "record_mission") as record:
            response = self.client.get("/api/beacon/follow-up-suggestions")
        self.assertEqual(response.status_code, 200)
        analyze.assert_called_once_with(events)
        record.assert_not_called()

        mission = {"mission_id": suggestion["suggestion_id"], "status": "new", "owner_decision": ""}
        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=None), \
             patch.object(sales_transaction_routes, "list_beacon_campaign_performance_events", return_value=({"performance_events": events}, 200)), \
             patch.object(sales_transaction_routes, "build_beacon_follow_up_suggestions", return_value={"suggestions": [suggestion]}), \
             patch.object(sales_transaction_routes, "beacon_follow_up_mission", return_value=mission), \
             patch.object(sales_transaction_routes, "record_mission", return_value=({"stored": True, "mission_id": suggestion["suggestion_id"]}, 201)) as record:
            response = self.client.post("/api/beacon/follow-up-suggestions/create-mission", json={"suggestion_id": suggestion["suggestion_id"], "status": "approved", "safety_level": "low"})
        self.assertEqual(response.status_code, 201)
        record.assert_called_once_with(mission, source_context={"source": "beacon_follow_up_suggestion"})

    def test_beacon_follow_up_creation_requires_admin_and_current_server_suggestion(self):
        denied = ({"success": False, "status": "owner_admin_required"}, 403)
        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=denied), \
             patch.object(sales_transaction_routes, "record_mission") as record:
            response = self.client.post("/api/beacon/follow-up-suggestions/create-mission", json={"suggestion_id": "x"})
        self.assertEqual(response.status_code, 403)
        record.assert_not_called()

        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=None), \
             patch.object(sales_transaction_routes, "list_beacon_campaign_performance_events", return_value=({"performance_events": []}, 200)), \
             patch.object(sales_transaction_routes, "build_beacon_follow_up_suggestions", return_value={"suggestions": []}), \
             patch.object(sales_transaction_routes, "record_mission") as record:
            response = self.client.post("/api/beacon/follow-up-suggestions/create-mission", json={"suggestion_id": "stale"})
        self.assertEqual(response.status_code, 409)
        record.assert_not_called()

    def test_sales_transaction_list_route_is_read_only(self):
        service_result = {
            "success": True,
            "status": "ok",
            "count": 0,
            "sales_transactions": [],
            "source": {
                "source": "supabase",
                "writes_to_sheets": False,
                "writes_to_supabase": False,
            },
        }

        with patch.object(
            sales_transaction_routes,
            "list_sales_transactions",
            return_value=(service_result, 200),
        ) as list_transactions:
            response = self.client.get("/api/sales-transactions?sale_stream=Slaughter&limit=10")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        list_transactions.assert_called_once_with(sale_stream="Slaughter", limit="10")

    def test_sales_transaction_list_route_returns_400_for_invalid_stream(self):
        with patch.object(
            sales_transaction_routes,
            "list_sales_transactions",
            side_effect=ValueError("sale_stream must be Livestock, Slaughter, or Meat."),
        ):
            response = self.client.get("/api/sales-transactions?sale_stream=Auction")

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["success"])
        self.assertIn("sale_stream must be Livestock", payload["errors"][0])
        self.assertFalse(payload["source"]["writes_to_sheets"])
        self.assertFalse(payload["source"]["writes_to_supabase"])

    def test_sales_transaction_dry_run_route_never_writes(self):
        service_result = {
            "success": True,
            "status": "ok",
            "mode": "dry_run",
            "source": {
                "source": "validation_only",
                "writes_to_sheets": False,
                "writes_to_supabase": False,
            },
        }

        with patch.object(
            sales_transaction_routes,
            "dry_run_sales_transaction",
            return_value=(service_result, 200),
        ) as dry_run:
            response = self.client.post("/api/sales-transactions/dry-run", json={
                "sale_stream": "Slaughter",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        dry_run.assert_called_once()

    def test_sales_transaction_create_route_calls_create_service(self):
        service_result = {
            "success": True,
            "status": "created",
            "sale_id": "SALE-1",
            "source": {
                "source": "supabase",
                "writes_to_sheets": False,
                "writes_to_supabase": True,
            },
        }

        with patch.object(
            sales_transaction_routes,
            "create_sales_transaction",
            return_value=(service_result, 201),
        ) as create_transaction:
            response = self.client.post("/api/sales-transactions", json={
                "sale_stream": "Slaughter",
            })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        create_transaction.assert_called_once()

    def test_sales_transaction_detail_route_calls_read_service(self):
        service_result = {
            "success": True,
            "status": "ok",
            "sales_transaction": {"sale_id": "SALE-1"},
            "items": [],
            "source": {
                "source": "supabase",
                "writes_to_sheets": False,
                "writes_to_supabase": False,
            },
        }

        with patch.object(
            sales_transaction_routes,
            "get_sales_transaction",
            return_value=(service_result, 200),
        ) as get_transaction:
            response = self.client.get("/api/sales-transactions/SALE-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        get_transaction.assert_called_once_with("SALE-1")

    def test_sales_transaction_cancel_route_calls_cancel_service(self):
        service_result = {
            "success": True,
            "status": "cancelled",
            "sale_id": "SALE-1",
            "source": {
                "source": "supabase",
                "writes_to_sheets": False,
                "writes_to_supabase": True,
            },
        }

        with patch.object(
            sales_transaction_routes,
            "cancel_sales_transaction",
            return_value=(service_result, 200),
        ) as cancel_transaction:
            response = self.client.post("/api/sales-transactions/SALE-1/cancel", json={
                "cancelled_by": "Charl",
                "cancel_reason": "Test complete",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        cancel_transaction.assert_called_once()

    def test_sales_transaction_payment_update_route_calls_update_service(self):
        service_result = {
            "success": True,
            "status": "updated",
            "sale_id": "SALE-1",
            "source": {
                "source": "supabase",
                "writes_to_sheets": False,
                "writes_to_supabase": True,
            },
        }

        with patch.object(
            sales_transaction_routes,
            "update_slaughter_sale_payment",
            return_value=(service_result, 200),
        ) as update_transaction:
            response = self.client.patch("/api/sales-transactions/SALE-1/payment", json={
                "updated_by": "Charl",
                "line_total": 1500,
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        update_transaction.assert_called_once()

    def test_sales_transaction_confirm_pig_exits_route_calls_lifecycle_service(self):
        service_result = {
            "success": True,
            "status": "pig_exits_confirmed",
            "sale_id": "SALE-1",
            "source": {
                "source": "supabase_sales_transaction_to_google_sheets_pig_master",
                "writes_to_sheets": True,
                "writes_to_supabase": False,
            },
        }

        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=None), patch.object(
            sales_transaction_routes,
            "confirm_slaughter_pig_exits",
            return_value=(service_result, 200),
        ) as confirm_exits:
            response = self.client.post("/api/sales-transactions/SALE-1/confirm-pig-exits", json={
                "changed_by": "Charl",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        confirm_exits.assert_called_once()

    def test_sales_transaction_confirm_pig_exits_denial_prevents_lifecycle_service(self):
        denied = ({"success": False, "status": "owner_admin_access_denied"}, 403)
        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=denied), patch.object(
            sales_transaction_routes, "confirm_slaughter_pig_exits"
        ) as confirm_exits:
            response = self.client.post("/api/sales-transactions/SALE-1/confirm-pig-exits", json={})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), denied[0])
        confirm_exits.assert_not_called()

    def test_sales_transaction_reconcile_pig_exits_route_calls_lifecycle_service(self):
        service_result = {
            "success": True,
            "status": "pig_exits_reconcile_preview",
            "sale_id": "SALE-1",
            "source": {
                "source": "supabase_sales_transaction_to_google_sheets_pig_master",
                "writes_to_sheets": False,
                "writes_to_supabase": False,
            },
        }

        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=None), patch.object(
            sales_transaction_routes,
            "reconcile_closed_slaughter_pig_exits",
            return_value=(service_result, 200),
        ) as reconcile_exits:
            response = self.client.post("/api/sales-transactions/SALE-1/reconcile-pig-exits", json={
                "dry_run": True,
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        reconcile_exits.assert_called_once()

    def test_sales_transaction_reconcile_pig_exits_denial_prevents_lifecycle_service(self):
        denied = ({"success": False, "status": "owner_admin_access_denied"}, 403)
        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=denied), patch.object(
            sales_transaction_routes, "reconcile_closed_slaughter_pig_exits"
        ) as reconcile_exits:
            response = self.client.post("/api/sales-transactions/SALE-1/reconcile-pig-exits", json={})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json(), denied[0])
        reconcile_exits.assert_not_called()

    def test_meat_sales_leads_list_route_uses_sales_lead_store(self):
        service_result = {
            "success": True,
            "status": "ok",
            "sales_leads": [{"lead_id": "OSK-SALES-LEAD-1"}],
            "source": {
                "writes_to_sheets": False,
                "writes_to_supabase": False,
            },
        }

        with patch.object(
            sales_transaction_routes,
            "list_sales_leads",
            return_value=(service_result, 200),
        ) as list_leads, patch.object(
            sales_transaction_routes,
            "require_owner_read_access",
            return_value=None,
        ):
            response = self.client.get("/api/sales/meat-leads?limit=12&status=launch_test")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        list_leads.assert_called_once_with(limit="12", status_filter="launch_test")

    def test_meat_money_path_routes_stop_before_service_when_owner_access_denied(self):
        denied = {
            "success": False,
            "status": "owner_read_access_denied",
            "requires_owner_session": True,
        }
        routes = [
            ("get", "/api/sales/meat-leads/OSK-SALES-LEAD-1/estimated-quote", "build_meat_estimated_quote_packet"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/estimated-quote/pdf", "generate_meat_estimated_quote_pdf"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/estimated-quote/send", "send_meat_estimated_quote_to_chatwoot"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/deposit-pro-forma/pdf", "generate_meat_deposit_pro_forma_pdf"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/final-invoice/pdf", "generate_meat_final_invoice_pdf"),
            ("get", "/api/sales/meat-leads/OSK-SALES-LEAD-1/payment-gate", "get_meat_payment_gate"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/carcass-reservations", "create_carcass_reservation_from_lead"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/reservation-events", "record_carcass_reservation_event"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/deposit-events", "record_meat_deposit_event"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/instruction-drafts", "build_meat_instruction_drafts"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/reconciliation-events", "record_meat_reconciliation_event"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/dad-booking-packet", "build_dad_booking_packet"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/fulfillment-events", "record_meat_fulfillment_event"),
            ("get", "/api/sales/meat-deliveries/driver-route", "list_meat_driver_route"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/driver-events", "record_meat_driver_delivery_event"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/journey-notification-draft", "build_meat_journey_notification_draft"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/journey-notification-approval", "approve_meat_journey_notification"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/journey-notification-send", "send_meat_journey_notification"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/instruction-drafts/DRAFT-1/approval", "approve_meat_instruction_draft"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/instruction-drafts/DRAFT-1/send", "send_approved_meat_instruction"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/instruction-drafts/DRAFT-1/exception", "record_meat_instruction_exception"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/owner-money-path-approval", "record_owner_money_path_approval"),
            ("get", "/api/sales/meat-leads/OSK-SALES-LEAD-1/customer-followup-draft", "get_sales_lead_customer_followup_draft"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/customer-followup-send-approval", "record_customer_followup_send_approval"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/customer-followup-send", "send_customer_followup_to_chatwoot"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/customer-booking-confirmation", "record_customer_booking_confirmation"),
            ("post", "/api/sales/meat-leads/OSK-SALES-LEAD-1/draft-order", "create_draft_order_from_sales_lead"),
        ]

        for method, path, service_name in routes:
            with self.subTest(path=path), patch.object(
                sales_transaction_routes,
                "_require_owner_meat_money_path_access",
                return_value=(denied, 403),
            ), patch.object(sales_transaction_routes, service_name) as service:
                response = getattr(self.client, method)(path, json={"test": True})

            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.get_json()["status"], "owner_read_access_denied")
            service.assert_not_called()

    def test_beacon_media_policy_route_returns_storage_policy(self):
        with patch.object(
            sales_transaction_routes,
            "beacon_media_storage_policy",
            return_value={"success": True, "farm_app_standard_upload_enabled": False},
        ) as policy, patch.object(sales_transaction_routes, "require_owner_read_access", return_value=None):
            response = self.client.get("/api/beacon/media-policy")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["farm_app_standard_upload_enabled"])
        policy.assert_called_once()

    def test_meat_document_delivery_status_route_requires_valid_token(self):
        with patch.object(
            sales_transaction_routes,
            "authorize_meat_document_delivery_webhook",
            return_value=(False, {"success": False, "status": "meat_sales_delivery_webhook_auth_denied"}),
        ) as authorize:
            response = self.client.post(
                "/api/sales/channels/chatwoot/meat-documents/delivery-status",
                json={"status": "delivered"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["status"], "meat_sales_delivery_webhook_auth_denied")
        authorize.assert_called_once()

    def test_meat_document_delivery_status_route_calls_handler_when_authorized(self):
        service_result = {
            "success": True,
            "status": "estimated_quote_delivery_delivered",
            "processed": True,
        }
        with patch.object(
            sales_transaction_routes,
            "authorize_meat_document_delivery_webhook",
            return_value=(True, {}),
        ) as authorize, patch.object(
            sales_transaction_routes,
            "handle_meat_document_delivery_status_webhook",
            return_value=(service_result, 201),
        ) as handler:
            response = self.client.post(
                "/api/sales/channels/chatwoot/meat-documents/delivery-status",
                json={"status": "delivered"},
                headers={"Authorization": "Bearer test"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        authorize.assert_called_once()
        handler.assert_called_once_with({"status": "delivered"})

    def test_shared_delivery_status_route_prefers_exact_sam_attempt(self):
        sam_result = {
            "success": True,
            "status": "sam_delivery_confirmed_card_cleaned",
            "processed": True,
        }
        with patch.object(
            sales_transaction_routes,
            "authorize_meat_document_delivery_webhook",
            return_value=(True, {}),
        ), patch.object(
            sales_transaction_routes,
            "handle_sam_live_stock_delivery_status_webhook",
            return_value=(sam_result, 200),
        ) as sam_handler, patch.object(
            sales_transaction_routes,
            "handle_meat_document_delivery_status_webhook",
        ) as meat_handler:
            payload = {"event": "message_updated", "message": {"id": 902}}
            response = self.client.post(
                "/api/sales/channels/chatwoot/meat-documents/delivery-status",
                json=payload,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), sam_result)
        sam_handler.assert_called_once_with(payload)
        meat_handler.assert_not_called()

    def test_meat_whatsapp_templates_route_returns_pack(self):
        with patch.object(
            sales_transaction_routes,
            "meat_whatsapp_template_pack",
            return_value={"success": True, "configured_count": 1, "required_count": 5},
        ) as pack:
            response = self.client.get("/api/sales/meat-whatsapp-templates")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["required_count"], 5)
        pack.assert_called_once()

    def test_meat_pilot_readiness_route_returns_dashboard(self):
        service_result = {
            "success": True,
            "mode": "meat_sales_pilot_readiness_dashboard",
            "pilot_percent": 78,
        }
        with patch.object(
            sales_transaction_routes,
            "get_meat_pilot_readiness",
            return_value=(service_result, 200),
        ) as readiness:
            response = self.client.get("/api/sales/meat-pilot-readiness?limit=6&status=launch_test")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["pilot_percent"], 78)
        readiness.assert_called_once_with(limit="6", status_filter="launch_test")

    def test_meat_pilot_readiness_service_degrades_contract_failure(self):
        leads = [
            {"lead_id": "LEAD-GOOD", "lead_label": "Good lead", "status": "new", "interest": {}},
            {"lead_id": "LEAD-BAD", "lead_label": "Bad lead", "status": "new", "interest": {}},
        ]

        def contract(lead_id):
            if lead_id == "LEAD-BAD":
                raise RuntimeError("simulated contract failure")
            return ({"contract": {"contract_status": "owner_money_path_ready"}}, 200)

        with patch.object(meat_pilot_readiness, "list_sales_leads", return_value=({"sales_leads": leads}, 200)), \
             patch.object(meat_pilot_readiness, "get_sales_lead_preorder_contract", side_effect=contract), \
             patch.object(meat_pilot_readiness, "build_meat_estimated_quote_packet", return_value=({"quote_safe": True, "status": "ok"}, 200)), \
             patch.object(meat_pilot_readiness, "get_meat_ops_status", return_value=({"assembly": {}, "payment_gate": {"state": "deposit_not_received"}}, 200)), \
             patch.object(meat_pilot_readiness, "meat_whatsapp_template_pack", return_value={"configured_count": 0, "required_count": 1, "all_configured": False, "missing_envs": ["template"]}):
            result, status = meat_pilot_readiness.get_meat_pilot_readiness(limit=2, status_filter="launch_test")

        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "degraded")
        self.assertTrue(result["source_degraded"])
        self.assertEqual(len(result["lead_stages"]), 2)
        bad_row = next(row for row in result["lead_stages"] if row["lead_id"] == "LEAD-BAD")
        self.assertTrue(bad_row["source_degraded"])
        self.assertIn("contract_read_failed", bad_row["blockers"])
        self.assertEqual(result["degraded_sources"][0]["source"], "contract")
        self.assertNotIn("simulated contract failure", str(result))
        self.assertFalse(result["sends_customer_message"])
        self.assertFalse(result["creates_order"])
        self.assertFalse(result["changes_stock"])
        self.assertFalse(result["customer_public_output_enabled"])

    def test_meat_pilot_readiness_service_degrades_quote_and_ops_failures(self):
        leads = [{"lead_id": "LEAD-BAD", "lead_label": "Bad lead", "status": "new", "interest": {}}]

        with patch.object(meat_pilot_readiness, "list_sales_leads", return_value=({"sales_leads": leads}, 200)), \
             patch.object(meat_pilot_readiness, "get_sales_lead_preorder_contract", return_value=({"contract": {}}, 200)), \
             patch.object(meat_pilot_readiness, "build_meat_estimated_quote_packet", side_effect=RuntimeError("simulated quote failure")), \
             patch.object(meat_pilot_readiness, "get_meat_ops_status", side_effect=RuntimeError("simulated ops failure")), \
             patch.object(meat_pilot_readiness, "meat_whatsapp_template_pack", return_value={"configured_count": 0, "required_count": 1, "all_configured": False, "missing_envs": ["template"]}):
            result, status = meat_pilot_readiness.get_meat_pilot_readiness(limit=1, status_filter="launch_test")

        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "degraded")
        sources = {item["source"] for item in result["degraded_sources"]}
        self.assertEqual(sources, {"quote", "ops"})
        row = result["lead_stages"][0]
        self.assertIn("quote_read_failed", row["blockers"])
        self.assertIn("ops_status_unavailable", row["blockers"])
        self.assertNotIn("simulated quote failure", str(result))
        self.assertNotIn("simulated ops failure", str(result))
    def test_meat_payment_gate_route_returns_gate(self):
        service_result = {
            "success": True,
            "mode": "meat_payment_state_gate",
            "payment_gate": {"state": "pop_received_unverified"},
        }
        with patch.object(
            sales_transaction_routes,
            "get_meat_payment_gate",
            return_value=(service_result, 200),
        ) as gate:
            response = self.client.get("/api/sales/meat-leads/OSK-SALES-LEAD-1/payment-gate")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["payment_gate"]["state"], "pop_received_unverified")
        gate.assert_called_once_with("OSK-SALES-LEAD-1")

    def test_meat_lead_test_cleanup_soft_closes_marked_test_flow(self):
        contract_result = {
            "success": True,
            "lead": {
                "lead_id": "OSK-SALES-LEAD-TEST",
                "lead_label": "Charl N - Half Carcass interest",
                "interest": {"notes": "TEST FLOW - delete after test. Half carcass Set A."},
                "latest_event": {"event_type": "customer_followup_sent"},
                "events": [],
            },
        }
        event_result = {
            "success": True,
            "status": "ok",
            "lead_id": "OSK-SALES-LEAD-TEST",
            "event_type": "closed",
        }

        with patch.object(
            sales_transaction_routes,
            "get_sales_lead_preorder_contract",
            return_value=(contract_result, 200),
        ) as contract, patch.object(
            sales_transaction_routes,
            "record_sales_lead_event",
            return_value=(event_result, 201),
        ) as record_event:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-TEST/test-cleanup",
                json={"closed_by": "Charl"},
            )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertTrue(payload["removes_from_launch_test_queue"])
        self.assertFalse(payload["deletes_physical_records"])
        self.assertEqual(payload["status"], "test_flow_soft_closed")
        contract.assert_called_once_with("OSK-SALES-LEAD-TEST")
        record_event.assert_called_once()
        self.assertEqual(record_event.call_args.args[0], "OSK-SALES-LEAD-TEST")
        self.assertEqual(record_event.call_args.args[1]["event_type"], "closed")

    def test_meat_lead_test_cleanup_refuses_unmarked_real_lead(self):
        contract_result = {
            "success": True,
            "lead": {
                "lead_id": "OSK-SALES-LEAD-REAL",
                "lead_label": "Real buyer",
                "interest": {"notes": "Half carcass Set A."},
                "latest_event": {"event_type": "customer_followup_sent"},
                "events": [],
            },
        }

        with patch.object(
            sales_transaction_routes,
            "get_sales_lead_preorder_contract",
            return_value=(contract_result, 200),
        ), patch.object(sales_transaction_routes, "record_sales_lead_event") as record_event:
            response = self.client.post("/api/sales/meat-leads/OSK-SALES-LEAD-REAL/test-cleanup")

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertEqual(payload["status"], "test_cleanup_denied_not_marked_test_flow")
        self.assertFalse(payload["sends_customer_message"])
        record_event.assert_not_called()

    def test_beacon_media_assets_list_and_register_routes(self):
        service_result = {
            "success": True,
            "status": "ok",
            "assets": [{"asset_id": "BEACON-ASSET-1"}],
        }

        with patch.object(
            sales_transaction_routes,
            "list_beacon_media_assets",
            return_value=(service_result, 200),
        ) as list_assets, patch.object(sales_transaction_routes, "require_owner_read_access", return_value=None):
            response = self.client.get("/api/beacon/media-assets?limit=12&approval_status=needs_review&media_type=image")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        list_assets.assert_called_once_with(limit="12", approval_status="needs_review", media_type="image")

        with patch.object(
            sales_transaction_routes,
            "register_beacon_media_asset",
            return_value=({"success": True, "asset_id": "BEACON-ASSET-2"}, 201),
        ) as register_asset, patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=None):
            response = self.client.post("/api/beacon/media-assets", json={
                "storage_path": "2026/06/18/test.jpg",
                "media_type": "image",
            })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["asset_id"], "BEACON-ASSET-2")
        register_asset.assert_called_once_with({
            "storage_path": "2026/06/18/test.jpg",
            "media_type": "image",
            "created_by": "authenticated_owner_admin",
        })

    def test_beacon_media_asset_upload_and_event_routes(self):
        with patch.object(
            sales_transaction_routes,
            "upload_beacon_media_asset",
            return_value=({"success": True, "asset_id": "BEACON-ASSET-UPLOAD"}, 201),
        ) as upload_asset, patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=None):
            response = self.client.post(
                "/api/beacon/media-assets/upload",
                data={"file": (BytesIO(b"fake"), "test.jpg"), "uploader_label": "Charl"},
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["asset_id"], "BEACON-ASSET-UPLOAD")
        upload_asset.assert_called_once()

        with patch.object(
            sales_transaction_routes,
            "record_beacon_media_asset_event",
            return_value=({"success": True, "event_id": "BEACON-ASSET-EVENT-1"}, 201),
        ) as record_event, patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=None):
            response = self.client.post(
                "/api/beacon/media-assets/BEACON-ASSET-1/events",
                json={"event_type": "review_note", "notes": "Good photo."},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["event_id"], "BEACON-ASSET-EVENT-1")
        record_event.assert_called_once_with("BEACON-ASSET-1", {
            "event_type": "review_note",
            "notes": "Good photo.",
            "recorded_by": "authenticated_owner_admin",
        })

    def test_beacon_facebook_image_launch_packet_uses_approved_images(self):
        with patch.object(
            sales_transaction_routes,
            "list_beacon_media_assets",
            return_value=({"success": True, "assets": [{"asset_id": "A1", "media_type": "image", "public_use_approved": True}]}, 200),
        ) as list_assets, patch.object(
            sales_transaction_routes,
            "build_beacon_facebook_image_launch_packet",
            return_value={"success": True, "ready_for_owner_post_approval": True},
        ) as packet:
            response = self.client.get("/api/beacon/facebook-image-launch-packet")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ready_for_owner_post_approval"])
        list_assets.assert_called_once_with(limit=25, approval_status="approved", media_type="image")
        packet.assert_called_once()

    def test_beacon_campaign_draft_selection_route_uses_only_approved_media(self):
        assets_result = {
            "success": True,
            "assets": [{"asset_id": "BEACON-ASSET-APPROVED", "effective_approval_status": "approved"}],
        }
        selection_result = {
            "success": True,
            "mode": "beacon_meat_launch_campaign_media_selection_review_only",
            "approved_media_count": 1,
        }

        with patch.object(sales_transaction_routes, "require_owner_read_access", return_value=None), patch.object(
            sales_transaction_routes,
            "list_beacon_media_assets",
            return_value=(assets_result, 200),
        ) as list_assets, patch.object(
            sales_transaction_routes,
            "build_beacon_campaign_selection",
            return_value=selection_result,
        ) as build_selection:
            response = self.client.get("/api/beacon/campaign-draft-selection?limit=9&media_type=image&area=Riversdale&campaign_lane=meat_launch")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), selection_result)
        list_assets.assert_called_once_with(limit="9", approval_status="approved", media_type="image")
        build_selection.assert_called_once()
        self.assertEqual(build_selection.call_args.kwargs["approved_assets"], assets_result["assets"])
        self.assertEqual(build_selection.call_args.args[0]["area"], "Riversdale")
        self.assertEqual(build_selection.call_args.args[0]["campaign_lane"], "meat_launch")

    def test_beacon_campaign_publish_packet_route_validates_against_approved_media(self):
        assets_result = {
            "success": True,
            "assets": [{"asset_id": "BEACON-ASSET-APPROVED", "effective_approval_status": "approved"}],
        }
        publish_result = {
            "success": True,
            "mode": "beacon_campaign_publish_packet_owner_review_only",
            "publish_packet_id": "BEACON-PUBLISH-PACKET-1",
        }

        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=None), patch.object(
            sales_transaction_routes,
            "list_beacon_media_assets",
            return_value=(assets_result, 200),
        ) as list_assets, patch.object(
            sales_transaction_routes,
            "build_beacon_campaign_publish_packet",
            return_value=publish_result,
        ) as build_packet:
            response = self.client.post("/api/beacon/campaign-publish-packet", json={
                "campaign_lane": "meat_launch",
                "draft_id": "facebook_post",
                "asset_id": "BEACON-ASSET-APPROVED",
                "media_type": "image",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), publish_result)
        list_assets.assert_called_once_with(limit=25, approval_status="approved", media_type="image")
        build_packet.assert_called_once()
        self.assertEqual(build_packet.call_args.kwargs["approved_assets"], assets_result["assets"])
        self.assertEqual(build_packet.call_args.args[0]["campaign_lane"], "meat_launch")

    def test_beacon_post_composer_uses_stored_owner_history(self):
        history = {"success": True, "manual_post_events": [{"evidence_notes": "Exact text: Past farm post"}]}
        suggestions = {"success": True, "status": "caption_suggestions_ready", "suggestions": ["New farm post"]}
        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=None), patch.object(
            sales_transaction_routes, "list_beacon_manual_post_evidence", return_value=(history, 200)
        ) as list_history, patch.object(
            sales_transaction_routes, "build_beacon_caption_suggestions", return_value=(suggestions, 200)
        ) as compose:
            response = self.client.post("/api/beacon/post-composer/suggestions", json={
                "campaign_lane": "live_stock_awareness", "brief": "Twelve piglets growing well",
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), suggestions)
        list_history.assert_called_once_with(limit=30)
        self.assertEqual(compose.call_args.kwargs["historical_events"], history["manual_post_events"])

    def test_beacon_post_composer_revision_uses_stored_owner_history(self):
        history = {"success": True, "manual_post_events": [{"evidence_notes": "Exact text: Past farm post"}]}
        revised = {"success": True, "status": "caption_revised", "caption": "Warmer farm post"}
        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=None), patch.object(
            sales_transaction_routes, "list_beacon_manual_post_evidence", return_value=(history, 200)
        ), patch.object(sales_transaction_routes, "revise_beacon_caption", return_value=(revised, 200)) as revise:
            response = self.client.post("/api/beacon/post-composer/revision", json={
                "campaign_lane": "live_stock_awareness", "caption": "Farm post", "revision_instruction": "Make it warmer",
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), revised)
        self.assertEqual(revise.call_args.kwargs["historical_events"], history["manual_post_events"])

    def test_beacon_campaign_routes_require_owner_access_before_service_calls(self):
        denied = ({"success": False, "status": "owner_access_denied"}, 403)
        with patch.object(sales_transaction_routes, "require_owner_read_access", return_value=denied), patch.object(
            sales_transaction_routes, "list_beacon_media_assets"
        ) as list_assets:
            response = self.client.get("/api/beacon/campaign-draft-selection")
        self.assertEqual(response.status_code, 403)
        list_assets.assert_not_called()

        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=denied), patch.object(
            sales_transaction_routes, "list_beacon_media_assets"
        ) as list_assets:
            response = self.client.post("/api/beacon/campaign-publish-packet", json={})
        self.assertEqual(response.status_code, 403)
        list_assets.assert_not_called()

    def test_beacon_manual_post_evidence_routes_record_owner_post_history_only(self):
        list_result = {
            "success": True,
            "mode": "beacon_manual_public_post_evidence_only",
            "manual_post_events": [{"manual_post_event_id": "BEACON-MANUAL-POST-1"}],
        }
        record_result = {
            "success": True,
            "mode": "beacon_manual_public_post_evidence_only",
            "manual_post_event_id": "BEACON-MANUAL-POST-2",
            "posts_publicly": False,
            "boosts_post": False,
            "spends_money": False,
        }

        with patch.object(
            sales_transaction_routes,
            "list_beacon_manual_post_evidence",
            return_value=(list_result, 200),
        ) as list_evidence:
            response = self.client.get("/api/beacon/manual-post-evidence?limit=6&publish_packet_id=BEACON-PUBLISH-PACKET-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), list_result)
        list_evidence.assert_called_once_with(limit="6", publish_packet_id="BEACON-PUBLISH-PACKET-1")

        payload = {
            "publish_packet_id": "BEACON-PUBLISH-PACKET-1",
            "channel": "Facebook",
            "post_url": "https://example.test/post",
        }
        with patch.object(
            sales_transaction_routes,
            "record_beacon_manual_post_evidence",
            return_value=(record_result, 201),
        ) as record_evidence:
            response = self.client.post("/api/beacon/manual-post-evidence", json=payload)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), record_result)
        record_evidence.assert_called_once_with(payload)

    def test_beacon_campaign_performance_routes_are_recommendation_only(self):
        list_result = {
            "success": True,
            "mode": "beacon_campaign_performance_evidence_only",
            "performance_events": [{"performance_event_id": "BEACON-PERF-1"}],
        }
        record_result = {
            "success": True,
            "mode": "beacon_campaign_performance_evidence_only",
            "performance_event_id": "BEACON-PERF-2",
            "boost_packet": {
                "recommended_action": "light_boost_owner_review",
                "calls_meta_now": False,
                "spends_money_now": False,
            },
            "calls_meta": False,
            "boosts_post": False,
            "spends_money": False,
        }

        with patch.object(
            sales_transaction_routes,
            "list_beacon_campaign_performance_events",
            return_value=(list_result, 200),
        ) as list_events:
            response = self.client.get("/api/beacon/campaign-performance?limit=6&publish_packet_id=BEACON-PUBLISH-PACKET-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), list_result)
        list_events.assert_called_once_with(
            limit="6",
            publish_packet_id="BEACON-PUBLISH-PACKET-1",
            manual_post_event_id="",
        )

        payload = {
            "manual_post_event_id": "BEACON-MANUAL-POST-1",
            "publish_packet_id": "BEACON-PUBLISH-PACKET-1",
            "messages_to_sam": 3,
        }
        with patch.object(
            sales_transaction_routes,
            "record_beacon_campaign_performance_event",
            return_value=(record_result, 201),
        ) as record_event:
            response = self.client.post("/api/beacon/campaign-performance", json=payload)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), record_result)
        record_event.assert_called_once_with(payload)

    def test_beacon_weekly_command_routes_require_owner_and_prepare_without_execution(self):
        source = {"success": True, "performance_events": [{"performance_event_id": "BEACON-PERF-1"}]}
        brief = {"mode": "beacon_weekly_command_brief_read_only", "recommendations": []}
        with patch.object(sales_transaction_routes, "require_owner_read_access", return_value=None), patch.object(
            sales_transaction_routes, "list_beacon_campaign_performance_events", return_value=(source, 200)
        ) as list_events, patch.object(
            sales_transaction_routes, "build_beacon_weekly_command_brief", return_value=brief
        ) as build_brief:
            response = self.client.get("/api/beacon/weekly-command-brief?limit=50")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["weekly_command_brief"], brief)
        list_events.assert_called_once_with(limit="50")
        build_brief.assert_called_once_with(source["performance_events"])

        prepared = {"success": True, "status": "owner_decision_packet_prepared", "creates_core_work": False, "approves_campaign": False}
        performance_event = {"performance_event_id": "BEACON-PERF-1", "spend_amount": 0, "qualified_buyer_leads": 0}
        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=None), patch.object(
            sales_transaction_routes, "list_beacon_campaign_performance_events", return_value=({"success": True, "performance_events": [performance_event]}, 200)
        ) as list_events, patch.object(
            sales_transaction_routes, "prepare_beacon_owner_decision", return_value=(prepared, 200)
        ) as prepare:
            response = self.client.post("/api/beacon/weekly-command-brief/prepare-decision", json={"performance_event_id": "BEACON-PERF-1", "classification": "BOOST", "destination": "core_work"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["creates_core_work"])
        list_events.assert_called_once_with(limit=100)
        prepare.assert_called_once_with(performance_event, "core_work")

        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=None), patch.object(
            sales_transaction_routes, "list_beacon_campaign_performance_events", return_value=({"success": True, "performance_events": []}, 200)
        ):
            missing = self.client.post("/api/beacon/weekly-command-brief/prepare-decision", json={"performance_event_id": "fabricated", "destination": "core_work"})
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.get_json()["status"], "recommendation_source_not_found")

    def test_beacon_weekly_command_routes_fail_closed_when_unauthorized(self):
        denied = ({"success": False, "status": "owner_access_denied"}, 403)
        with patch.object(sales_transaction_routes, "require_owner_read_access", return_value=denied):
            self.assertEqual(self.client.get("/api/beacon/weekly-command-brief").status_code, 403)
        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=denied):
            self.assertEqual(self.client.post("/api/beacon/weekly-command-brief/prepare-decision", json={}).status_code, 403)

    def test_beacon_facebook_post_execution_routes_are_gated(self):
        policy_result = {
            "success": True,
            "mode": "beacon_facebook_page_post_execution_gate",
            "enabled": False,
        }
        list_result = {
            "success": True,
            "mode": "beacon_facebook_page_post_execution_gate",
            "execution_events": [],
        }
        execute_result = {
            "success": False,
            "status": "facebook_posting_disabled",
            "posts_publicly": False,
            "calls_meta": False,
            "spends_money": False,
        }

        with patch.object(
            sales_transaction_routes,
            "facebook_posting_policy",
            return_value=policy_result,
        ) as policy:
            response = self.client.get("/api/beacon/facebook-posting-policy")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), policy_result)
        policy.assert_called_once()

        with patch.object(
            sales_transaction_routes,
            "require_owner_admin_access",
            return_value=None,
        ), patch.object(
            sales_transaction_routes,
            "list_beacon_facebook_post_execution_events",
            return_value=(list_result, 200),
        ) as list_events:
            response = self.client.get("/api/beacon/facebook-post-executions?limit=3&publish_packet_id=BEACON-PUBLISH-PACKET-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), list_result)
        list_events.assert_called_once_with(limit="3", publish_packet_id="BEACON-PUBLISH-PACKET-1")

        payload = {
            "publish_packet_id": "BEACON-PUBLISH-PACKET-1",
            "channel": "Facebook",
            "exact_text": "Limited preorder test post.",
            "owner_confirmation": "POST EXACT BEACON PACKET",
        }
        with patch.object(
            sales_transaction_routes,
            "require_owner_admin_access",
            return_value=None,
        ), patch.object(
            sales_transaction_routes,
            "execute_beacon_facebook_page_post",
            return_value=(execute_result, 503),
        ) as execute_post:
            response = self.client.post("/api/beacon/facebook-post-executions", json=payload)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), execute_result)
        execute_post.assert_called_once_with(payload)

        denied = ({"success": False, "status": "owner_access_denied"}, 403)
        with patch.object(
            sales_transaction_routes,
            "require_owner_admin_access",
            return_value=denied,
        ), patch.object(
            sales_transaction_routes,
            "list_beacon_facebook_post_execution_events",
        ) as list_events, patch.object(
            sales_transaction_routes,
            "execute_beacon_facebook_page_post",
        ) as execute_post:
            denied_get = self.client.get("/api/beacon/facebook-post-executions")
            denied_post = self.client.post("/api/beacon/facebook-post-executions", json=payload)

        self.assertEqual(denied_get.status_code, 403)
        self.assertEqual(denied_post.status_code, 403)
        list_events.assert_not_called()
        execute_post.assert_not_called()

    def test_beacon_facebook_post_execution_resolves_approved_image_asset(self):
        execute_result = {
            "success": True,
            "status": "facebook_page_post_sent",
            "posts_publicly": True,
            "calls_meta": True,
            "spends_money": False,
        }
        payload = {
            "publish_packet_id": "BEACON-PUBLISH-PACKET-1",
            "channel": "Facebook",
            "exact_text": "Limited preorder image post.",
            "asset_id": "BEACON-ASSET-APPROVED",
            "owner_confirmation": "POST EXACT BEACON PACKET",
        }
        approved_asset = {
            "asset_id": "BEACON-ASSET-APPROVED",
            "media_type": "image",
            "effective_public_use_approved": True,
        }

        with patch.object(
            sales_transaction_routes,
            "require_owner_admin_access",
            return_value=None,
        ), patch.object(
            sales_transaction_routes,
            "list_beacon_media_assets",
            return_value=({"success": True, "assets": [approved_asset]}, 200),
        ) as list_assets, patch.object(
            sales_transaction_routes,
            "execute_beacon_facebook_page_post",
            return_value=(execute_result, 200),
        ) as execute_post:
            response = self.client.post("/api/beacon/facebook-post-executions", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), execute_result)
        list_assets.assert_called_once_with(limit=100, approval_status="approved")
        execute_post.assert_called_once()
        sent_payload = execute_post.call_args.args[0]
        self.assertEqual(sent_payload["selected_asset"], approved_asset)

    @patch.dict("os.environ", {"SAM_MEAT_PUBLIC_OFFER_ENABLED": "1"})
    def test_meat_launch_execution_rebuilds_authoritative_packet_before_execute(self):
        approved_asset = {
            "asset_id": "BEACON-ASSET-MEAT",
            "title": "Approved meat pilot image",
            "media_type": "image",
            "effective_approval_status": "approved",
            "effective_public_use_approved": True,
            "public_use_approved": True,
            "storage_bucket": "beacon-approved-media",
            "storage_path": "pilot/meat.jpg",
        }
        authoritative = sales_transaction_routes.build_beacon_campaign_publish_packet({
            "campaign_lane": "meat_launch", "draft_id": "facebook_post",
            "asset_id": approved_asset["asset_id"], "channel": "Facebook", "pilot_cap": "2",
        }, approved_assets=[approved_asset])
        payload = {
            "campaign_lane": "meat_launch",
            "publish_packet_id": authoritative["publish_packet_id"],
            "channel": "Facebook",
            "exact_text": authoritative["selected_draft"]["exact_text"],
            "asset_id": approved_asset["asset_id"],
            "pilot_cap": "2",
            "owner_confirmation": "POST EXACT BEACON PACKET",
        }
        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=None), patch.object(
            sales_transaction_routes, "list_beacon_media_assets",
            return_value=({"success": True, "assets": [approved_asset]}, 200),
        ), patch.object(
            sales_transaction_routes, "execute_beacon_facebook_page_post",
            return_value=({"success": True, "facebook_post_id": "PAGE_123"}, 200),
        ) as execute_post:
            response = self.client.post("/api/beacon/facebook-post-executions", json=payload)

        self.assertEqual(response.status_code, 200)
        execute_post.assert_called_once()
        self.assertTrue(execute_post.call_args.kwargs["meat_launch_authorized"])
        self.assertEqual(
            execute_post.call_args.args[0]["selected_asset"]["asset_id"], approved_asset["asset_id"]
        )

    @patch.dict("os.environ", {"SAM_MEAT_PUBLIC_OFFER_ENABLED": "1"})
    def test_meat_launch_execution_rejects_changed_cap_before_execute(self):
        approved_asset = {
            "asset_id": "BEACON-ASSET-MEAT", "media_type": "image",
            "effective_approval_status": "approved", "effective_public_use_approved": True,
            "public_use_approved": True, "storage_bucket": "beacon-approved-media",
            "storage_path": "pilot/meat.jpg",
        }
        authoritative = sales_transaction_routes.build_beacon_campaign_publish_packet({
            "campaign_lane": "meat_launch", "draft_id": "facebook_post",
            "asset_id": approved_asset["asset_id"], "channel": "Facebook", "pilot_cap": "2",
        }, approved_assets=[approved_asset])
        payload = {
            "campaign_lane": "meat_launch", "publish_packet_id": authoritative["publish_packet_id"],
            "channel": "Facebook", "exact_text": authoritative["selected_draft"]["exact_text"],
            "asset_id": approved_asset["asset_id"], "pilot_cap": "3",
            "owner_confirmation": "POST EXACT BEACON PACKET",
        }
        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=None), patch.object(
            sales_transaction_routes, "list_beacon_media_assets",
            return_value=({"success": True, "assets": [approved_asset]}, 200),
        ), patch.object(sales_transaction_routes, "execute_beacon_facebook_page_post") as execute_post:
            response = self.client.post("/api/beacon/facebook-post-executions", json=payload)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["status"], "meat_launch_packet_not_ready_or_stale")

    def test_beacon_facebook_post_execution_prohibits_live_stock_sales_meta_lane(self):
        with patch.object(
            sales_transaction_routes,
            "require_owner_admin_access",
            return_value=None,
        ), patch.object(
            sales_transaction_routes,
            "execute_beacon_facebook_page_post",
        ) as execute_post:
            response = self.client.post("/api/beacon/facebook-post-executions", json={
                "campaign_lane": "live_stock_sales",
                "publish_packet_id": "PACKET-SALES",
                "channel": "Facebook",
                "exact_text": "Livestock sales text",
                "owner_confirmation": "POST EXACT BEACON PACKET",
            })

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["status"], "live_stock_sales_meta_posting_prohibited")
        self.assertFalse(response.get_json()["calls_meta"])
        execute_post.assert_not_called()

    def test_meat_sales_learning_list_route_uses_learning_store(self):
        service_result = {
            "success": True,
            "status": "ok",
            "learning_events": [{"learning_event_id": "MSCL-1"}],
            "summary": {"total_events": 1},
        }

        with patch.object(
            sales_transaction_routes,
            "list_sales_conversation_learning_events",
            return_value=(service_result, 200),
        ) as list_learning:
            response = self.client.get("/api/sales/meat-learning?limit=12&lead_id=OSK-SALES-LEAD-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        list_learning.assert_called_once_with(limit="12", lead_id="OSK-SALES-LEAD-1")

    def test_meat_price_book_list_route_uses_store(self):
        service_result = {
            "success": True,
            "status": "ok",
            "price_entries": [{"product_type": "half_carcass"}],
        }

        with patch.object(
            sales_transaction_routes,
            "list_meat_price_book_entries",
            return_value=(service_result, 200),
        ) as list_prices:
            response = self.client.get("/api/sales/meat-pricing?limit=12")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        list_prices.assert_called_once_with(limit="12")

    def test_meat_price_book_create_route_records_entry(self):
        service_result = {
            "success": True,
            "status": "ok",
            "price_entry_id": "OSK-MEAT-PRICE-TEST",
        }

        with patch.object(
            sales_transaction_routes,
            "record_meat_price_book_entry",
            return_value=(service_result, 201),
        ) as record_price:
            response = self.client.post(
                "/api/sales/meat-pricing",
                json={"product_type": "half_carcass", "price_amount": 130},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_price.assert_called_once_with({"product_type": "half_carcass", "price_amount": 130})

    def test_meat_sales_lead_contract_route_uses_preorder_contract(self):
        service_result = {
            "success": True,
            "status": "ok",
            "lead_id": "OSK-SALES-LEAD-1",
            "contract": {"contract_status": "owner_money_path_ready"},
        }

        with patch.object(
            sales_transaction_routes,
            "get_sales_lead_preorder_contract",
            return_value=(service_result, 200),
        ) as get_contract, patch.object(
            sales_transaction_routes,
            "require_owner_read_access",
            return_value=None,
        ):
            response = self.client.get("/api/sales/meat-leads/OSK-SALES-LEAD-1/contract")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        get_contract.assert_called_once_with("OSK-SALES-LEAD-1")

    def test_meat_sales_lead_learning_events_get_and_post_routes(self):
        service_result = {
            "success": True,
            "status": "ok",
            "learning_events": [{"learning_event_id": "MSCL-1"}],
            "summary": {"total_events": 1},
        }

        with patch.object(
            sales_transaction_routes,
            "list_sales_conversation_learning_events",
            return_value=(service_result, 200),
        ) as list_learning:
            response = self.client.get("/api/sales/meat-leads/OSK-SALES-LEAD-1/learning-events?limit=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        list_learning.assert_called_once_with(limit="7", lead_id="OSK-SALES-LEAD-1")

        with patch.object(
            sales_transaction_routes,
            "build_owner_review_learning_event",
            return_value={"lead_id": "OSK-SALES-LEAD-1", "event_type": "owner_review_note"},
        ) as build_event, patch.object(
            sales_transaction_routes,
            "record_sales_conversation_learning_event",
            return_value=({"success": True, "learning_event_id": "MSCL-OWNER"}, 201),
        ) as record_event:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/learning-events",
                json={"notes": "Customer asked about price."},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["learning_event_id"], "MSCL-OWNER")
        build_event.assert_called_once_with("OSK-SALES-LEAD-1", {"notes": "Customer asked about price."})
        record_event.assert_called_once_with({"lead_id": "OSK-SALES-LEAD-1", "event_type": "owner_review_note"})

    def test_meat_sales_lead_pricing_estimate_route_uses_estimator(self):
        service_result = {
            "success": True,
            "status": "ok",
            "pricing_estimate": {"price_label": "R130.00/kg"},
        }

        with patch.object(
            sales_transaction_routes,
            "get_sales_lead_pricing_estimate",
            return_value=(service_result, 200),
        ) as get_estimate, patch.object(
            sales_transaction_routes,
            "require_owner_read_access",
            return_value=None,
        ):
            response = self.client.get(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/pricing-estimate?selected_pig_live_weight_kg=62"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        get_estimate.assert_called_once_with(
            "OSK-SALES-LEAD-1",
            {"selected_pig_live_weight_kg": "62"},
        )

    def test_meat_sales_lead_match_route_uses_butcher_match_engine(self):
        service_result = {
            "success": True,
            "status": "ok",
            "meat_match": {"decision": "recommend"},
        }

        with patch.object(
            sales_transaction_routes,
            "get_sales_lead_meat_match",
            return_value=(service_result, 200),
        ) as get_match, patch.object(
            sales_transaction_routes,
            "require_owner_read_access",
            return_value=None,
        ):
            response = self.client.get(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/meat-match?preference=heaviest&target_packed_kg=25&budget_amount=3000"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        get_match.assert_called_once_with(
            "OSK-SALES-LEAD-1",
            {"preference": "heaviest", "target_packed_kg": "25", "budget_amount": "3000"},
        )

    def test_meat_sales_lead_ops_status_route_reads_gate(self):
        service_result = {
            "success": True,
            "status": "ok",
            "assembly": {"ready_for_instruction_drafts": False},
        }

        with patch.object(
            sales_transaction_routes,
            "get_meat_ops_status",
            return_value=(service_result, 200),
        ) as get_status, patch.object(
            sales_transaction_routes,
            "require_owner_read_access",
            return_value=None,
        ):
            response = self.client.get("/api/sales/meat-leads/OSK-SALES-LEAD-1/meat-ops")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        get_status.assert_called_once_with("OSK-SALES-LEAD-1")

    def test_meat_sales_lead_carcass_reservation_route_writes_reservation(self):
        service_result = {
            "success": True,
            "status": "half_reserved_pending_pair",
            "records_meat_ops": True,
        }

        with patch.object(
            sales_transaction_routes,
            "create_carcass_reservation_from_lead",
            return_value=(service_result, 201),
        ) as create_reservation:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/carcass-reservations",
                json={"pig_id": "PIG-1"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        create_reservation.assert_called_once_with("OSK-SALES-LEAD-1", {"pig_id": "PIG-1"})

    def test_meat_sales_lead_reservation_event_route_records_cancellation(self):
        service_result = {
            "success": True,
            "status": "reservation_cancelled",
            "records_meat_ops": True,
        }

        with patch.object(
            sales_transaction_routes,
            "record_carcass_reservation_event",
            return_value=(service_result, 201),
        ) as record_event:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/reservation-events",
                json={"reservation_id": "RES-1", "event_type": "reservation_cancelled", "reason": "Test cleanup"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_event.assert_called_once_with(
            "OSK-SALES-LEAD-1",
            {"reservation_id": "RES-1", "event_type": "reservation_cancelled", "reason": "Test cleanup"},
        )

    def test_meat_sales_lead_deposit_event_route_records_gate(self):
        service_result = {
            "success": True,
            "status": "deposit_confirmed_in_bank",
            "records_meat_ops": True,
        }

        with patch.object(
            sales_transaction_routes,
            "record_meat_deposit_event",
            return_value=(service_result, 201),
        ) as record_deposit:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/deposit-events",
                json={"reservation_id": "RES-1", "event_type": "deposit_confirmed_in_bank", "amount": "1250"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_deposit.assert_called_once_with(
            "OSK-SALES-LEAD-1",
            {"reservation_id": "RES-1", "event_type": "deposit_confirmed_in_bank", "amount": "1250"},
        )

    def test_meat_sales_lead_instruction_drafts_route_builds_internal_drafts(self):
        service_result = {
            "success": True,
            "status": "instruction_drafts_created",
            "sends_customer_message": False,
            "calls_chatwoot": False,
        }

        with patch.object(
            sales_transaction_routes,
            "build_meat_instruction_drafts",
            return_value=(service_result, 201),
        ) as build_drafts:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/instruction-drafts",
                json={"butcher_label": "Local Butcher"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        build_drafts.assert_called_once_with("OSK-SALES-LEAD-1", {"butcher_label": "Local Butcher"})

    def test_meat_fulfillment_timeline_route_reads_timeline(self):
        service_result = {
            "success": True,
            "status": "ok",
            "fulfillment": {"next_gate": "find_second_half_buyer"},
        }

        with patch.object(
            sales_transaction_routes,
            "get_meat_fulfillment_timeline",
            return_value=(service_result, 200),
        ) as get_timeline, patch.object(
            sales_transaction_routes,
            "require_owner_read_access",
            return_value=None,
        ):
            response = self.client.get("/api/sales/meat-leads/OSK-SALES-LEAD-1/fulfillment")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        get_timeline.assert_called_once_with("OSK-SALES-LEAD-1")

    def test_meat_reconciliation_status_route_reads_status(self):
        service_result = {
            "success": True,
            "status": "ok",
            "reconciliation": {"status": "awaiting_packed_weight"},
        }

        with patch.object(
            sales_transaction_routes,
            "get_meat_reconciliation_status",
            return_value=(service_result, 200),
        ) as get_status, patch.object(
            sales_transaction_routes,
            "require_owner_read_access",
            return_value=None,
        ):
            response = self.client.get("/api/sales/meat-leads/OSK-SALES-LEAD-1/reconciliation")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        get_status.assert_called_once_with("OSK-SALES-LEAD-1")

    def test_meat_reconciliation_event_route_records_event(self):
        service_result = {
            "success": True,
            "status": "packed_weight_recorded",
            "records_meat_reconciliation": True,
        }

        with patch.object(
            sales_transaction_routes,
            "record_meat_reconciliation_event",
            return_value=(service_result, 201),
        ) as record_event:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/reconciliation-events",
                json={"reservation_id": "RES-1", "actual_packed_weight_kg": "24.8", "price_per_kg": "130"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_event.assert_called_once_with(
            "OSK-SALES-LEAD-1",
            {"reservation_id": "RES-1", "actual_packed_weight_kg": "24.8", "price_per_kg": "130"},
        )

    def test_meat_dad_booking_packet_route_builds_draft_only_packet(self):
        service_result = {
            "success": True,
            "status": "ok",
            "dad_booking_packet": {"readiness": "ready_for_dad_booking"},
            "calls_abattoir": False,
            "calls_butcher": False,
        }

        with patch.object(
            sales_transaction_routes,
            "build_dad_booking_packet",
            return_value=(service_result, 200),
        ) as build_packet:
            response = self.client.get("/api/sales/meat-leads/OSK-SALES-LEAD-1/dad-booking-packet")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        build_packet.assert_called_once_with("OSK-SALES-LEAD-1", {})

    def test_meat_fulfillment_event_route_records_event(self):
        service_result = {
            "success": True,
            "status": "delivery_scheduled",
            "records_meat_fulfillment": True,
        }

        with patch.object(
            sales_transaction_routes,
            "record_meat_fulfillment_event",
            return_value=(service_result, 201),
        ) as record_event:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/fulfillment-events",
                json={"event_type": "delivery_scheduled", "scheduled_date": "2026-06-20"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_event.assert_called_once_with(
            "OSK-SALES-LEAD-1",
            {"event_type": "delivery_scheduled", "scheduled_date": "2026-06-20"},
        )

    def test_meat_driver_route_calls_route_reader(self):
        service_result = {
            "success": True,
            "status": "ok",
            "stops": [],
        }

        with patch.object(
            sales_transaction_routes,
            "list_meat_driver_route",
            return_value=(service_result, 200),
        ) as list_route:
            response = self.client.get("/api/sales/meat-deliveries/driver-route?driver=Dad&date=2026-06-20")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        list_route.assert_called_once_with(driver_label="Dad", scheduled_date="2026-06-20")

    def test_meat_driver_event_route_records_driver_event(self):
        service_result = {
            "success": True,
            "status": "delivery_on_way",
            "records_meat_fulfillment": True,
        }

        with patch.object(
            sales_transaction_routes,
            "record_meat_driver_delivery_event",
            return_value=(service_result, 201),
        ) as record_driver:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/driver-events",
                json={"event_type": "delivery_on_way", "assigned_to": "Dad"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_driver.assert_called_once_with("OSK-SALES-LEAD-1", {"event_type": "delivery_on_way", "assigned_to": "Dad"})

    def test_meat_journey_notification_draft_route_builds_draft(self):
        service_result = {
            "success": True,
            "status": "draft_created",
            "notification_event": {"message": "Customer update"},
        }

        with patch.object(
            sales_transaction_routes,
            "build_meat_journey_notification_draft",
            return_value=(service_result, 201),
        ) as build_draft:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/journey-notification-draft",
                json={"recorded_by": "Farm App"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        build_draft.assert_called_once_with("OSK-SALES-LEAD-1", {"recorded_by": "Farm App"})

    def test_meat_journey_notification_approval_route_records_exact_approval(self):
        service_result = {
            "success": True,
            "status": "approved_to_send",
        }

        with patch.object(
            sales_transaction_routes,
            "approve_meat_journey_notification",
            return_value=(service_result, 201),
        ) as approve:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/journey-notification-approval",
                json={"approved_message": "Customer update"},
            )

        self.assertEqual(response.status_code, 201)
        approve.assert_called_once_with("OSK-SALES-LEAD-1", {"approved_message": "Customer update"})

    def test_meat_journey_notification_send_route_calls_sender(self):
        service_result = {
            "success": False,
            "status": "meat_journey_notification_send_disabled",
            "sent": False,
        }

        with patch.object(
            sales_transaction_routes,
            "send_meat_journey_notification",
            return_value=(service_result, 503),
        ) as send:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/journey-notification-send",
                json={"message": "Customer update"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), service_result)
        send.assert_called_once_with("OSK-SALES-LEAD-1", {"message": "Customer update"})

    def test_meat_instruction_approval_route_records_exact_approval(self):
        service_result = {
            "success": True,
            "status": "approved_to_send",
            "records_meat_ops": True,
        }

        with patch.object(
            sales_transaction_routes,
            "approve_meat_instruction_draft",
            return_value=(service_result, 201),
        ) as approve_draft:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/instruction-drafts/DRAFT-1/approval",
                json={"approved_message": "Exact draft"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        approve_draft.assert_called_once_with("OSK-SALES-LEAD-1", "DRAFT-1", {"approved_message": "Exact draft"})

    def test_meat_instruction_send_route_calls_gated_sender(self):
        service_result = {
            "success": True,
            "status": "sent",
            "sent": True,
            "informs_external_party": True,
        }

        with patch.object(
            sales_transaction_routes,
            "send_approved_meat_instruction",
            return_value=(service_result, 200),
        ) as send_instruction:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/instruction-drafts/DRAFT-1/send",
                json={"message": "Exact draft"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        send_instruction.assert_called_once_with("OSK-SALES-LEAD-1", "DRAFT-1", {"message": "Exact draft"})

    def test_meat_instruction_exception_route_records_review_state(self):
        service_result = {
            "success": True,
            "status": "exception_review_required",
            "records_meat_ops": True,
        }

        with patch.object(
            sales_transaction_routes,
            "record_meat_instruction_exception",
            return_value=(service_result, 201),
        ) as record_exception:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/instruction-drafts/DRAFT-1/exception",
                json={"reason": "Need abattoir slot date"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_exception.assert_called_once_with("OSK-SALES-LEAD-1", "DRAFT-1", {"reason": "Need abattoir slot date"})

    def test_meat_sales_lead_owner_approval_route_records_event(self):
        service_result = {
            "success": True,
            "status": "ok",
            "records_owner_money_path_approval": True,
        }

        with patch.object(
            sales_transaction_routes,
            "record_owner_money_path_approval",
            return_value=(service_result, 201),
        ) as record_approval:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/owner-money-path-approval",
                json={"price_per_kg": "R100.00"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_approval.assert_called_once_with("OSK-SALES-LEAD-1", {"price_per_kg": "R100.00"})

    def test_meat_sales_lead_followup_draft_route_reads_draft(self):
        service_result = {
            "success": True,
            "status": "ok",
            "customer_followup_draft": {"message": "Hi Charl"},
        }

        with patch.object(
            sales_transaction_routes,
            "get_sales_lead_customer_followup_draft",
            return_value=(service_result, 200),
        ) as get_draft:
            response = self.client.get("/api/sales/meat-leads/OSK-SALES-LEAD-1/customer-followup-draft")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        get_draft.assert_called_once_with("OSK-SALES-LEAD-1")

    def test_meat_sales_lead_send_approval_route_records_exact_message_approval(self):
        service_result = {
            "success": True,
            "status": "ok",
            "records_customer_followup_send_approval": True,
        }

        with patch.object(
            sales_transaction_routes,
            "record_customer_followup_send_approval",
            return_value=(service_result, 201),
        ) as record_send_approval:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/customer-followup-send-approval",
                json={"message": "Approved text"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_send_approval.assert_called_once_with("OSK-SALES-LEAD-1", {"message": "Approved text"})

    def test_meat_sales_lead_send_route_requires_env_unlock(self):
        with patch.dict("os.environ", {"OOM_SAKKIE_MEAT_FOLLOWUP_SEND_ENABLED": "0"}):
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/customer-followup-send",
                json={"message": "Approved text"},
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 503)
        self.assertFalse(payload["sent"])
        self.assertEqual(payload["status"], "meat_followup_send_disabled")
        self.assertFalse(payload["creates_order"])
        self.assertFalse(payload["changes_stock"])

    def test_meat_sales_lead_send_route_calls_chatwoot_sender_when_enabled(self):
        service_result = {
            "success": True,
            "status": "sent",
            "sent": True,
            "sends_customer_message": True,
            "calls_chatwoot": True,
            "creates_quote": False,
            "creates_order": False,
            "changes_stock": False,
        }

        with patch.dict("os.environ", {"OOM_SAKKIE_MEAT_FOLLOWUP_SEND_ENABLED": "1"}), patch.object(
            sales_transaction_routes,
            "send_customer_followup_to_chatwoot",
            return_value=(service_result, 200),
        ) as send_followup:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/customer-followup-send",
                json={"message": "Approved text"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        send_followup.assert_called_once_with("OSK-SALES-LEAD-1", {"message": "Approved text"})

    def test_meat_sales_lead_customer_booking_confirmation_route_records_event(self):
        service_result = {
            "success": True,
            "status": "ok",
            "records_customer_booking_confirmation": True,
        }

        with patch.object(
            sales_transaction_routes,
            "record_customer_booking_confirmation",
            return_value=(service_result, 201),
        ) as record_confirmation:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/customer-booking-confirmation",
                json={"customer_confirmation": "Yes, please book it."},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_confirmation.assert_called_once_with(
            "OSK-SALES-LEAD-1",
            {"customer_confirmation": "Yes, please book it."},
        )

    def test_meat_sales_lead_draft_order_route_creates_draft_order(self):
        service_result = {
            "success": True,
            "status": "draft_order_created",
            "order_id": "ORD-2026-TEST",
            "creates_order": True,
            "writes_farm_data": True,
        }

        with patch.object(
            sales_transaction_routes,
            "create_draft_order_from_sales_lead",
            return_value=(service_result, 201),
        ) as create_draft_order:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/draft-order",
                json={"created_by": "Farm App"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        create_draft_order.assert_called_once_with("OSK-SALES-LEAD-1", {"created_by": "Farm App"})

    def test_sam_meat_backend_policy_route_reports_configuration(self):
        with patch.object(
            sales_transaction_routes,
            "sam_meat_webhook_policy",
            return_value={"enabled": False, "mode": "backend_native_sam_meat_chatwoot"},
        ):
            response = self.client.get("/api/sales/channels/chatwoot/sam-meat/policy")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["policy"]["mode"], "backend_native_sam_meat_chatwoot")

    def test_sam_meat_backend_inbound_route_requires_auth(self):
        with patch.object(
            sales_transaction_routes,
            "authorize_sam_meat_webhook",
            return_value=(False, {"success": False, "status": "sam_meat_backend_webhook_auth_denied"}),
        ) as authorize:
            response = self.client.post("/api/sales/channels/chatwoot/sam-meat/inbound", json={})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["status"], "sam_meat_backend_webhook_auth_denied")
        authorize.assert_called_once()

    def test_sam_meat_backend_inbound_route_calls_runtime_after_auth(self):
        service_result = {
            "success": True,
            "status": "processed",
            "processed": True,
            "sent": False,
        }

        with patch.object(
            sales_transaction_routes,
            "authorize_sam_meat_webhook",
            return_value=(True, {}),
        ), patch.object(
            sales_transaction_routes,
            "handle_sam_meat_chatwoot_inbound",
            return_value=(service_result, 200),
        ) as handle_inbound:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-meat/inbound",
                json={"event": "message_created"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        handle_inbound.assert_called_once_with(
            {"event": "message_created"},
            routine_delivery_claim=sales_transaction_routes._claim_sam_meat_routine_delivery,
            routine_delivery_evidence_recorder=sales_transaction_routes._record_sam_live_stock_delivery_outcome,
            conversation_history_loader=sales_transaction_routes.load_chatwoot_conversation_history,
        )

    def test_sam_meat_backend_routes_live_stock_handoff_to_live_runtime(self):
        meat_result = {
            "success": True,
            "status": "sam_meat_live_stock_handoff",
            "processed": True,
            "sent": False,
            "lane_decision": {
                "version": "sam_sales_lane_decision_v1",
                "current_message_classification": {"lane": "live_stock_sales", "confidence": 0.99},
                "final_route": "live_stock_sales",
                "cross_lane_handoff_allowed": True,
            },
        }
        live_result = {
            "success": True,
            "status": "sam_live_stock_read_only_processed",
            "processed": True,
            "sent": False,
            "sam_decision": {
                "inbound": {"conversation_id": "1822", "message_id": "1", "content": "weaners"},
                "facts": {"sales_lane": "live_stock_sales"},
                "conversation_review": {"score": 96, "safe_to_send": False},
            },
            "policy": {"customer_send_allowed": False},
        }

        with patch.object(
            sales_transaction_routes,
            "authorize_sam_meat_webhook",
            return_value=(True, {}),
        ), patch.object(
            sales_transaction_routes,
            "handle_sam_meat_chatwoot_inbound",
            return_value=(meat_result, 200),
        ), patch.object(
            sales_transaction_routes,
            "handle_sam_live_stock_chatwoot_inbound",
            return_value=(live_result, 200),
        ) as live_runtime, patch.object(
            sales_transaction_routes,
            "record_sam_live_stock_review_event",
            return_value=({"success": True, "status": "recorded", "review_event_id": "REV-1", "conversation_event_count": 1}, 201),
        ), patch.object(
            sales_transaction_routes,
            "send_sam_live_stock_new_lead_telegram",
            return_value=({"success": False, "status": "sam_live_stock_new_lead_telegram_send_disabled"}, 409),
        ):
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-meat/inbound",
                json={"event": "message_created", "content": "weaners"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "sam_meat_live_stock_handoff")
        self.assertFalse(payload["sent"])
        self.assertEqual(payload["sam_live_stock_handoff"]["status"], "sam_live_stock_read_only_processed")
        self.assertTrue(payload["sam_live_stock_handoff"]["conversation_review_event"]["recorded"])
        self.assertEqual(payload["sam_live_stock_handoff"]["conversation_review_event"]["owner_notification"]["type"], "new_lead")
        live_runtime.assert_called_once_with({"content": "weaners", "event": "message_created"})

    def test_sam_meat_backend_routes_live_stock_owner_review_notification_after_first_event(self):
        meat_result = {
            "success": True,
            "status": "sam_meat_live_stock_handoff",
            "processed": True,
            "sent": False,
            "lane_decision": {
                "version": "sam_sales_lane_decision_v1",
                "current_message_classification": {"lane": "live_stock_sales", "confidence": 0.99},
                "final_route": "live_stock_sales",
                "cross_lane_handoff_allowed": True,
            },
        }
        live_result = {
            "success": True,
            "status": "sam_live_stock_read_only_processed",
            "processed": True,
            "sent": False,
            "sam_decision": {
                "inbound": {"conversation_id": "1822", "message_id": "2", "content": "What is the price?"},
                "facts": {"sales_lane": "live_stock_sales", "quote_requested": True},
                "suggested_reply_text": "Current price estimate:\n- 2 x Weaner: R500 each",
                "conversation_review": {
                    "score": 99,
                    "safe_to_send": True,
                    "recommended_action": "owner_review_send_candidate",
                },
            },
            "policy": {"customer_send_allowed": False},
        }

        with patch.object(
            sales_transaction_routes,
            "authorize_sam_meat_webhook",
            return_value=(True, {}),
        ), patch.object(
            sales_transaction_routes,
            "handle_sam_meat_chatwoot_inbound",
            return_value=(meat_result, 200),
        ), patch.object(
            sales_transaction_routes,
            "handle_sam_live_stock_chatwoot_inbound",
            return_value=(live_result, 200),
        ), patch.object(
            sales_transaction_routes,
            "record_sam_live_stock_review_event",
            return_value=({"success": True, "status": "recorded", "review_event_id": "REV-2", "conversation_event_count": 2}, 201),
        ), patch.object(
            sales_transaction_routes,
            "send_sam_live_stock_owner_review_telegram",
            return_value=({"success": True, "status": "sam_live_stock_owner_review_telegram_sent"}, 200),
        ) as owner_review:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-meat/inbound",
                json={"event": "message_created", "content": "What is the price?"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        notification = payload["sam_live_stock_handoff"]["conversation_review_event"]["owner_notification"]
        self.assertEqual(notification["type"], "owner_review")
        self.assertTrue(notification["sent"])
        owner_review.assert_called_once()

    def test_sam_meat_backend_prioritizes_owner_review_notification_on_first_event(self):
        meat_result = {
            "success": True,
            "status": "sam_meat_live_stock_handoff",
            "processed": True,
            "sent": False,
            "lane_decision": {
                "version": "sam_sales_lane_decision_v1",
                "current_message_classification": {"lane": "live_stock_sales", "confidence": 0.99},
                "final_route": "live_stock_sales",
                "cross_lane_handoff_allowed": True,
            },
        }
        live_result = {
            "success": True,
            "status": "sam_live_stock_read_only_processed",
            "processed": True,
            "sent": False,
            "sam_decision": {
                "inbound": {"conversation_id": "1478", "message_id": "1", "content": "How much are 7-9kg piglets?"},
                "facts": {"sales_lane": "live_stock_sales", "quote_requested": True},
                "suggested_reply_text": "Current price estimate:\n- Piglet, 7-9 kg: R450 each",
                "conversation_review": {
                    "score": 99,
                    "safe_to_send": True,
                    "recommended_action": "owner_review_send_candidate",
                },
            },
            "policy": {"customer_send_allowed": False},
        }

        with patch.object(
            sales_transaction_routes,
            "authorize_sam_meat_webhook",
            return_value=(True, {}),
        ), patch.object(
            sales_transaction_routes,
            "handle_sam_meat_chatwoot_inbound",
            return_value=(meat_result, 200),
        ), patch.object(
            sales_transaction_routes,
            "handle_sam_live_stock_chatwoot_inbound",
            return_value=(live_result, 200),
        ), patch.object(
            sales_transaction_routes,
            "record_sam_live_stock_review_event",
            return_value=({"success": True, "status": "recorded", "review_event_id": "REV-FIRST", "conversation_event_count": 1}, 201),
        ), patch.object(
            sales_transaction_routes,
            "send_sam_live_stock_owner_review_telegram",
            return_value=({"success": True, "status": "sam_live_stock_owner_review_telegram_sent"}, 200),
        ) as owner_review, patch.object(
            sales_transaction_routes,
            "send_sam_live_stock_new_lead_telegram",
            return_value=({"success": True, "status": "sam_live_stock_new_lead_telegram_sent"}, 200),
        ) as new_lead:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-meat/inbound",
                json={"event": "message_created", "content": "How much are 7-9kg piglets?"},
            )

        self.assertEqual(response.status_code, 200)
        notification = response.get_json()["sam_live_stock_handoff"]["conversation_review_event"]["owner_notification"]
        self.assertEqual(notification["type"], "owner_review")
        self.assertTrue(notification["sent"])
        owner_review.assert_called_once()
        new_lead.assert_not_called()

    def test_sam_live_stock_duplicate_review_event_does_not_send_duplicate_telegram(self):
        event = {
            "review_event_id": "SAM-LIVE-REVIEW-DUPE",
            "chatwoot_conversation_id": "1478",
            "sam_reply_excerpt": "I will check the current list before anything is promised.",
            "recommended_action": "owner_review_send_candidate",
            "review_json": {"safe_to_send": True},
            "decision_json": {"suggested_reply_text": "I will check the current list before anything is promised."},
        }
        learning_result = {
            "success": True,
            "created": False,
            "status": "sam_live_stock_review_event_already_recorded",
            "review_event_id": "SAM-LIVE-REVIEW-DUPE",
            "conversation_event_count": 2,
        }

        with patch.object(sales_transaction_routes, "send_sam_live_stock_owner_review_telegram") as owner_review, patch.object(
            sales_transaction_routes,
            "send_sam_live_stock_new_lead_telegram",
        ) as new_lead, patch.object(
            sales_transaction_routes,
            "send_sam_live_stock_telegram_escalation",
        ) as escalation:
            notification = sales_transaction_routes._send_sam_live_stock_owner_notification_if_needed(event, learning_result)

        self.assertFalse(notification["attempted"])
        self.assertEqual(notification["status"], "review_event_already_recorded_no_duplicate_telegram")
        owner_review.assert_not_called()
        new_lead.assert_not_called()
        escalation.assert_not_called()

    @patch.object(sales_transaction_routes, "require_owner_read_access", return_value=None)
    @patch.object(sales_transaction_routes, "live_stock_learning_scorecard")
    def test_live_stock_learning_scorecard_route_is_owner_read_only(self, scorecard, _guard):
        scorecard.return_value = ({
            "success": True,
            "status": "sam_live_stock_learning_scorecard_ready",
            "scorecard": {"captured_owner_replies": 12, "auto_send_enabled": False},
        }, 200)
        response = self.client.get("/api/sales/live-stock-learning/scorecard?limit=200")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["scorecard"]["auto_send_enabled"])
        scorecard.assert_called_once_with(limit="200")

    def test_response_class_authority_visibility_is_owner_read_only_and_sanitized(self):
        with patch.object(
            sales_transaction_routes, "require_owner_read_access", return_value=None
        ), patch.object(
            sales_transaction_routes,
            "load_canonical_evidence",
            return_value=({"success": True, "events": []}, 200),
        ), patch.object(
            sales_transaction_routes,
            "list_latest_authority_events",
            return_value=({"success": True, "events": []}, 200),
        ):
            response = self.client.get("/api/sales/live-stock-learning/authority")
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["contains_customer_content"])
        self.assertFalse(payload["sends_customer_message"])
        self.assertFalse(payload["charlie"]["may_promote"])

    def test_response_class_authority_decision_requires_owner_admin_and_sends_nothing(self):
        with patch.object(
            sales_transaction_routes, "require_owner_admin_access", return_value=None
        ), patch.object(
            sales_transaction_routes,
            "append_authority_decision",
            return_value=({
                "success": True,
                "status": "authority_event_recorded",
                "sends_customer_message": False,
                "mutates_business_state": False,
            }, 201),
        ) as decide:
            response = self.client.post(
                "/api/sales/live-stock-learning/authority/decision",
                json={
                    "response_class": "greeting",
                    "decision": "canary_authorized",
                    "reason": "owner canary",
                    "authorized_envelope": {"response_classes": ["greeting"]},
                },
            )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.get_json()["sends_customer_message"])
        decide.assert_called_once()

    def test_level1_control_uses_server_derived_owner_and_sends_nothing(self):
        current = {
            "success": True,
            "status": "level1_control_not_configured",
            "event": {},
        }
        event = {
            "control_event_id": "SAM-L1-CONTROL-1",
            "state": "enabled",
        }
        with patch.object(
            sales_transaction_routes,
            "require_strict_owner_admin_access",
            return_value=None,
        ), patch.object(
            sales_transaction_routes,
            "strict_owner_admin_principal",
            return_value="owner-admin:stable",
        ), patch.object(
            sales_transaction_routes,
            "load_current_level1_control",
            return_value=(current, 200),
        ), patch.object(
            sales_transaction_routes,
            "build_level1_control_event",
            return_value=event,
        ) as build, patch.object(
            sales_transaction_routes,
            "append_level1_control_event",
            return_value=({
                "success": True,
                "status": "level1_control_event_recorded",
                "sends_customer_message": False,
                "mutates_business_state": False,
            }, 201),
        ) as append:
            response = self.client.post(
                "/api/sales/live-stock-level1/control",
                json={
                    "state": "enabled",
                    "reason": "standing owner authority",
                    "actor_id": "browser-forged",
                },
            )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.get_json()["sends_customer_message"])
        self.assertEqual(
            build.call_args.kwargs["actor_id"],
            "owner-admin:stable",
        )
        append.assert_called_once_with(event)

    def test_level1_control_rejects_missing_strict_owner_principal(self):
        with patch.object(
            sales_transaction_routes,
            "require_strict_owner_admin_access",
            return_value=None,
        ), patch.object(
            sales_transaction_routes,
            "strict_owner_admin_principal",
            return_value="",
        ), patch.object(
            sales_transaction_routes,
            "append_level1_control_event",
        ) as append:
            response = self.client.post(
                "/api/sales/live-stock-level1/control",
                json={"state": "enabled", "reason": "forged"},
            )
        self.assertEqual(response.status_code, 403)
        append.assert_not_called()

    def test_owner_read_session_cannot_append_authority_decision(self):
        with patch.object(
            sales_transaction_routes,
            "require_owner_admin_access",
            return_value=({"success": False, "status": "owner_admin_required"}, 403),
        ), patch.object(
            sales_transaction_routes, "append_authority_decision"
        ) as decide:
            response = self.client.post(
                "/api/sales/live-stock-learning/authority/decision",
                json={"response_class": "greeting", "decision": "candidate"},
            )
        self.assertEqual(response.status_code, 403)
        decide.assert_not_called()

    def test_sam_meat_backend_inbound_route_returns_json_for_unhandled_runtime_error(self):
        with patch.object(
            sales_transaction_routes,
            "authorize_sam_meat_webhook",
            return_value=(True, {}),
        ), patch.object(
            sales_transaction_routes,
            "handle_sam_meat_chatwoot_inbound",
            side_effect=RuntimeError("production-only mismatch"),
        ):
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-meat/inbound",
                json={"event": "message_created"},
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 500)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["status"], "sam_meat_inbound_unhandled_exception")
        self.assertEqual(payload["error_type"], "RuntimeError")
        self.assertFalse(payload["sent"])
        self.assertFalse(payload["sends_customer_message"])
        self.assertFalse(payload["calls_chatwoot"])

    def test_sam_live_stock_policy_route_reports_controlled_launch_gates(self):
        with patch.object(
            sales_transaction_routes,
            "sam_live_stock_webhook_policy",
            return_value={
                "enabled": True,
                "mode": "backend_native_sam_live_stock_chatwoot_read_only",
                "owner_approved_send_enabled": False,
            },
        ):
            response = self.client.get("/api/sales/channels/chatwoot/sam-live-stock/policy")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["policy"]["mode"], "backend_native_sam_live_stock_chatwoot_read_only")
        self.assertFalse(payload["policy"]["owner_approved_send_enabled"])

    def test_sam_live_stock_inbound_route_requires_auth(self):
        with patch.object(
            sales_transaction_routes,
            "authorize_sam_live_stock_webhook",
            return_value=(False, {"success": False, "status": "sam_live_stock_backend_webhook_auth_denied"}),
        ):
            response = self.client.post("/api/sales/channels/chatwoot/sam-live-stock/inbound", json={})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["status"], "sam_live_stock_backend_webhook_auth_denied")

    def test_sam_live_stock_inbound_route_calls_runtime_after_auth(self):
        service_result = {
            "success": True,
            "status": "sam_live_stock_read_only_processed",
            "processed": True,
            "sent": False,
        }

        with patch.object(
            sales_transaction_routes,
            "authorize_sam_live_stock_webhook",
            return_value=(True, {}),
        ), patch.object(
            sales_transaction_routes,
            "handle_sam_live_stock_chatwoot_inbound",
            return_value=(service_result, 200),
        ) as handle_inbound:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/inbound",
                json={"event": "message_created"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        handle_inbound.assert_called_once_with(
            {"event": "message_created"},
            routine_delivery_claim=sales_transaction_routes._claim_sam_live_stock_routine_delivery,
            routine_delivery_evidence_recorder=sales_transaction_routes._record_sam_live_stock_delivery_outcome,
        )

    def test_sam_live_stock_webhook_observes_exact_owner_work_after_review_persistence(self):
        service_result = {
            "success": True,
            "status": "sam_live_stock_read_only_processed",
            "processed": True,
            "sent": False,
            "sam_decision": {
                "inbound": {
                    "conversation_id": "2031",
                    "message_id": "761497234",
                },
                "facts": {},
                "conversation_review": {},
            },
        }
        observed = {
            "success": True,
            "status": "owner_work_reconciliation_completed",
            "evidence_complete": True,
            "created_count": 1,
        }
        order = []
        with patch.object(
            sales_transaction_routes, "authorize_sam_live_stock_webhook",
            return_value=(True, {}),
        ), patch.object(
            sales_transaction_routes, "handle_sam_live_stock_chatwoot_inbound",
            return_value=(service_result, 200),
        ), patch.object(
            sales_transaction_routes, "build_sam_live_stock_review_event",
            return_value={"review_event_id": "SAM-LIVE-REVIEW-2031"},
        ), patch.object(
            sales_transaction_routes, "record_sam_live_stock_review_event",
            return_value=({
                "success": True,
                "created": True,
                "status": "sam_live_stock_review_event_recorded",
                "review_event_id": "SAM-LIVE-REVIEW-2031",
                "conversation_event_count": 1,
            }, 201),
        ), patch.object(
            sales_transaction_routes,
            "_send_sam_live_stock_owner_notification_if_needed",
            side_effect=lambda *args: (
                order.append("telegram"),
                {"attempted": False, "status": "not_required"},
            )[1],
        ), patch.object(
            sales_transaction_routes, "observe_owner_work_message_event",
            side_effect=lambda *args, **kwargs: (
                order.append("owner_work"),
                (observed, 200),
            )[1],
        ) as reconcile:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/inbound",
                json={"event": "message_created"},
            )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["owner_work_observation"]["evidence_complete"])
        self.assertFalse(payload["owner_work_observation"]["sends_customer_message"])
        reconcile.assert_called_once_with(
            service_result["sam_decision"]["inbound"],
            {"review_event_id": "SAM-LIVE-REVIEW-2031"},
            {"event": "message_created"},
            reconciliation_actor_id="server:sam-live-stock-webhook-observer",
        )
        self.assertEqual(order, ["owner_work", "telegram"])

    def test_sam_live_stock_routine_delivery_claim_uses_distinct_append_only_attempt(self):
        with patch.object(
            sales_transaction_routes,
            "build_sam_live_stock_review_event",
            return_value={"review_event_id": "SAM-LIVE-REVIEW-CANARY"},
        ), patch.object(
            sales_transaction_routes,
            "record_sam_live_stock_review_event",
            return_value=({
                "success": True,
                "created": True,
                "status": "sam_live_stock_review_event_recorded",
                "conversation_event_count": 2,
            }, 201),
        ) as record:
            claim = sales_transaction_routes._claim_sam_live_stock_routine_delivery(
                {
                    "conversation_id": "2013",
                    "contact_id": "699428938",
                    "inbox_id": "96568",
                    "message_id": "759446521",
                },
                {
                    "facts": {},
                    "suggested_reply_text": "Hi Charl! How can I help you today?",
                    "autoreply_canary": {"response_class": "greeting"},
                },
                {"safe_to_send": True},
            )
        self.assertTrue(claim["success"])
        self.assertTrue(claim["created"])
        self.assertFalse(claim["contains_secret_values"])
        self.assertTrue(claim["delivery_attempt_id"].startswith("SAM-DELIVERY-ATTEMPT-"))
        self.assertNotEqual(claim["delivery_attempt_id"], claim["review_event_id"])
        self.assertEqual(claim["delivery_claim_event_id"], claim["delivery_attempt_id"])
        event = record.call_args.args[0]
        self.assertEqual(event["event_source"], "sam_outbound_delivery_attempt_claim")
        self.assertEqual(event["chatwoot_conversation_id"], "2013")
        self.assertEqual(event["chatwoot_message_id"], "759446521")
        self.assertNotIn("Hi Charl", str(event))

    def test_sam_live_stock_delivery_outcome_is_separate_append_only_event(self):
        with patch.object(
            sales_transaction_routes,
            "record_sam_live_stock_review_event",
            return_value=({"success": True, "created": True, "review_event_id": "DELIVERY-1"}, 201),
        ) as record:
            result = sales_transaction_routes._record_sam_live_stock_delivery_outcome(
                {
                    "success": True,
                    "created": True,
                    "delivery_attempt_id": "SAM-DELIVERY-ATTEMPT-1",
                    "delivery_contract_version": "sam_outbound_delivery_v1",
                    "conversation_id": "2013",
                    "contact_id": "699428938",
                    "inbox_id": "96568",
                    "inbound_message_id": "759446521",
                    "review_id": "SAM-LIVE-REVIEW-1",
                    "reply_hash": "a" * 64,
                    "response_class": "greeting",
                    "attempt_generation": 1,
                },
                {
                    "delivery_state": "chatwoot_accepted_unverified",
                    "chatwoot_outgoing_message_id": "759446597",
                    "chatwoot_response_status": "sent",
                    "provider_identity_class": "whatsapp_provider",
                },
            )
        event = record.call_args.args[0]
        self.assertTrue(result["success"])
        self.assertEqual(event["event_source"], "sam_outbound_delivery_transition")
        self.assertEqual(event["chatwoot_conversation_id"], "2013")
        self.assertEqual(event["chatwoot_message_id"], "759446597")
        self.assertEqual(event["review_json"]["delivery_state"], "chatwoot_accepted_unverified")
        self.assertTrue(event["review_json"]["automatic_retry_prohibited"])
        serialized = str(event)
        self.assertNotIn("wamid.", serialized)
        self.assertNotIn("api_access_token", serialized)
        self.assertEqual(event["facts_json"], {})
        self.assertEqual(event["decision_json"], {})

    def test_sam_live_stock_delivery_claim_persistence_failure_is_fail_closed(self):
        with patch.object(
            sales_transaction_routes,
            "build_sam_live_stock_review_event",
            return_value={"review_event_id": "SAM-LIVE-REVIEW-FAIL"},
        ), patch.object(
            sales_transaction_routes,
            "record_sam_live_stock_review_event",
            return_value=({
                "success": False,
                "created": False,
                "status": "sam_live_stock_review_event_write_failed",
            }, 500),
        ):
            claim = sales_transaction_routes._claim_sam_live_stock_routine_delivery(
                {
                    "conversation_id": "2013",
                    "contact_id": "699428938",
                    "inbox_id": "96568",
                    "message_id": "759446521",
                },
                {
                    "facts": {},
                    "suggested_reply_text": "Hi Charl! How can I help you today?",
                    "autoreply_canary": {"response_class": "greeting"},
                },
                {"safe_to_send": True},
            )
        self.assertFalse(claim["success"])
        self.assertFalse(claim["created"])
        self.assertEqual(claim["status"], "sam_live_stock_review_event_write_failed")

    def test_sam_live_stock_outgoing_owner_reply_records_learning(self):
        latest_event = {
            "review_event_id": "SAM-LIVE-REVIEW-1",
            "chatwoot_conversation_id": "1840",
            "customer_message_excerpt": "Location",
            "sam_reply_excerpt": "Just so I help you correctly: are you looking for live pigs, pork for the freezer, or slaughter help?",
            "facts_json": {"sales_lane": "live_stock_sales"},
            "decision_json": {"missing_fields": ["category"]},
            "review_json": {"escalation_required": True},
            "recommended_action": "owner_handoff",
            "created_at": "2026-07-08T13:00:00+00:00",
        }

        with patch.object(
            sales_transaction_routes,
            "authorize_sam_live_stock_webhook",
            return_value=(True, {}),
        ), patch.object(
            sales_transaction_routes,
            "get_latest_sam_live_stock_review_event_for_conversation",
            return_value=({"success": True, "status": "sam_live_stock_latest_review_event_loaded", "event": latest_event}, 200),
        ) as latest, patch.object(
            sales_transaction_routes,
            "record_sales_conversation_learning_event",
            return_value=({"success": True, "status": "sales_conversation_learning_event_recorded", "learning_event_id": "MSCL-LIVE-1"}, 201),
        ) as record, patch.object(
            sales_transaction_routes,
            "refresh_sam_live_stock_resolve_card_from_outgoing_event",
            return_value={"success": False, "attempted": False, "status": "resolve_card_canary_disabled"},
        ) as refresh, patch.object(
            sales_transaction_routes,
            "handle_sam_live_stock_chatwoot_inbound",
        ) as handle_inbound:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/inbound",
                json={
                    "event": "message_created",
                    "message_type": "outgoing",
                    "id": 9001,
                    "account": {"id": 147387},
                    "created_at": "2026-07-08T13:05:00+00:00",
                    "content": "We are near Riversdale in the Western Cape.",
                    "conversation": {
                        "id": 1840,
                        "inbox": {"id": 96568, "channel_type": "Channel::Whatsapp"},
                        "meta": {"sender": {"id": 699428938}},
                    },
                    "sender": {"name": "Charl"},
                },
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["captured"])
        self.assertEqual(payload["learning_status_code"], 201)
        self.assertEqual(payload["learning_event_id"], "MSCL-LIVE-1")
        latest.assert_called_once_with("1840")
        learning_event = record.call_args.args[0]
        self.assertEqual(learning_event["source_agent"], "sam_live_stock_backend")
        self.assertEqual(learning_event["captured_facts"]["owner_reply_classification"], "owner_replaced")
        self.assertEqual(learning_event["captured_facts"]["review_reply_delta_seconds"], 300)
        refresh.assert_called_once()
        refresh_identity = refresh.call_args.args[0]
        self.assertEqual(refresh_identity["conversation_id"], "1840")
        self.assertEqual(refresh_identity["account_id"], 147387)
        self.assertEqual(refresh_identity["contact_id"], 699428938)
        self.assertEqual(refresh_identity["inbox_id"], 96568)
        self.assertEqual(refresh_identity["message_id"], 9001)
        self.assertTrue(refresh_identity["public"])
        handle_inbound.assert_not_called()

    def test_conversation_2021_sanitized_outgoing_fixture_reaches_exact_refresh(self):
        payload = __import__("json").loads(
            Path("tests/fixtures/sam_chatwoot_outgoing_2021_sanitized.json").read_text(
                encoding="utf-8"
            )
        )
        with patch.object(
            sales_transaction_routes,
            "authorize_sam_live_stock_webhook",
            return_value=(True, {}),
        ), patch.object(
            sales_transaction_routes,
            "get_latest_sam_live_stock_review_event_for_conversation",
            return_value=({
                "success": True,
                "event": {
                    "review_event_id": "SAM-LIVE-REVIEW-85A567BA6AC1",
                    "chatwoot_conversation_id": "2021",
                    "created_at": "2026-07-26T06:32:07.531704+00:00",
                    "decision_json": {},
                    "facts_json": {},
                    "review_json": {},
                },
            }, 200),
        ), patch.object(
            sales_transaction_routes,
            "record_sales_conversation_learning_event",
            return_value=({"success": True, "created_count": 1}, 201),
        ), patch.object(
            sales_transaction_routes,
            "notify_new_graduation_candidates",
            return_value={"attempted": False},
        ), patch.object(
            sales_transaction_routes,
            "observe_owner_work_message_event",
            return_value=({
                "success": True,
                "status": "owner_work_observation_recorded",
                "evidence_complete": True,
                "created_count": 1,
            }, 201),
        ) as observe_owner_work, patch.object(
            sales_transaction_routes,
            "refresh_sam_live_stock_resolve_card_from_outgoing_event",
            return_value={"success": True, "status": "resolve_card_refresh_completed"},
        ) as refresh:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/inbound",
                json=payload,
            )

        self.assertEqual(response.status_code, 200)
        observed = refresh.call_args.args[0]
        self.assertEqual(observed, {
            "account_id": 147387,
            "conversation_id": "2021",
            "contact_id": 699428938,
            "inbox_id": 96568,
            "message_id": 760224858,
            "public": True,
            "identity_conflicting": False,
        })
        self.assertTrue(response.get_json()["captured"])
        self.assertEqual(
            response.get_json()["owner_work_observation"]["status"],
            "owner_work_observation_recorded",
        )
        self.assertTrue(
            response.get_json()["owner_work_observation"]["evidence_complete"]
        )
        self.assertEqual(
            observe_owner_work.call_args.kwargs["direction"], "outgoing"
        )

    def test_attachment_only_public_owner_reply_reaches_owner_work_observer(self):
        payload = {
            "event": "message_created",
            "message_type": "outgoing",
            "id": 9002,
            "account": {"id": 147387},
            "created_at": "2026-07-27T08:05:00+00:00",
            "content": "",
            "attachments": [{"file_type": "image"}],
            "conversation": {
                "id": 2031,
                "inbox": {"id": 96568, "channel_type": "Channel::Whatsapp"},
                "meta": {"sender": {"id": 699428938}},
            },
        }
        with patch.object(
            sales_transaction_routes,
            "get_latest_sam_live_stock_review_event_for_conversation",
            return_value=({"success": True, "event": {}}, 200),
        ), patch.object(
            sales_transaction_routes,
            "record_sales_conversation_learning_event",
            return_value=({"success": False, "created": False}, 409),
        ) as record_learning, patch.object(
            sales_transaction_routes,
            "observe_owner_work_message_event",
            return_value=({
                "success": True,
                "status": "owner_work_observation_recorded",
                "evidence_complete": True,
                "created_count": 1,
            }, 201),
        ) as observe_owner_work, patch.object(
            sales_transaction_routes,
            "refresh_sam_live_stock_resolve_card_from_outgoing_event",
            return_value={"success": False, "attempted": False},
        ):
            result = sales_transaction_routes._capture_sam_live_stock_owner_reply_if_needed(
                payload
            )

        self.assertEqual(
            result["owner_work_observation"]["status"],
            "owner_work_observation_recorded",
        )
        observe_owner_work.assert_called_once()
        record_learning.assert_not_called()
        self.assertEqual(
            result["status"], "attachment_only_owner_reply_learning_withheld"
        )
        self.assertEqual(observe_owner_work.call_args.kwargs["direction"], "outgoing")

    def test_owner_admin_exact_resolve_refresh_route_has_no_send_or_ownership_authority(self):
        request_identity = {
            "account_id": "147387",
            "conversation_id": "2021",
            "contact_id": "699428938",
            "inbox_id": "96568",
            "customer_message_id": "760211638",
            "outgoing_message_id": "760224858",
            "review_event_id": "SAM-LIVE-REVIEW-85A567BA6AC1",
            "lifecycle_card_identity": "SAM-LIVE-CARD-9AC5E2FD901D",
            "telegram_chat_id": "555",
            "telegram_message_id": "2913",
        }
        with patch.object(
            sales_transaction_routes,
            "require_owner_admin_access",
            return_value=None,
        ), patch.object(
            sales_transaction_routes,
            "refresh_sam_live_stock_resolve_card_exact",
            return_value={
                "success": True,
                "status": "resolve_card_refresh_completed",
                "sends_customer_message": False,
                "calls_chatwoot": False,
                "changes_conversation_ownership": False,
            },
        ) as refresh:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/resolve-card-refresh",
                json=request_identity,
            )
        self.assertEqual(response.status_code, 200)
        refresh.assert_called_once_with(request_identity)
        body = response.get_json()
        self.assertFalse(body["sends_customer_message"])
        self.assertFalse(body["calls_chatwoot"])
        self.assertFalse(body["changes_conversation_ownership"])

        with patch.object(
            sales_transaction_routes,
            "require_owner_admin_access",
            return_value=({"success": False, "status": "owner_admin_required"}, 403),
        ), patch.object(
            sales_transaction_routes,
            "refresh_sam_live_stock_resolve_card_exact",
        ) as refresh:
            denied = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/resolve-card-refresh",
                json=request_identity,
            )
        self.assertEqual(denied.status_code, 403)
        refresh.assert_not_called()

    def test_sam_live_stock_outgoing_private_note_is_not_captured(self):
        with patch.object(
            sales_transaction_routes,
            "authorize_sam_live_stock_webhook",
            return_value=(True, {}),
        ), patch.object(
            sales_transaction_routes,
            "record_sales_conversation_learning_event",
        ) as record, patch.object(
            sales_transaction_routes,
            "handle_sam_live_stock_chatwoot_inbound",
        ) as handle_inbound:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/inbound",
                json={
                    "event": "message_created",
                    "message_type": "outgoing",
                    "private": True,
                    "content": "Internal note",
                    "conversation": {"id": 1840, "inbox": {"channel_type": "Channel::Whatsapp"}},
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "private_note_skipped")
        record.assert_not_called()
        handle_inbound.assert_not_called()

    def test_sam_live_stock_unrelated_outgoing_event_is_not_captured_or_refreshed(self):
        with patch.object(
            sales_transaction_routes,
            "authorize_sam_live_stock_webhook",
            return_value=(True, {}),
        ), patch.object(
            sales_transaction_routes,
            "record_sales_conversation_learning_event",
        ) as record, patch.object(
            sales_transaction_routes,
            "refresh_sam_live_stock_resolve_card_from_outgoing_event",
        ) as refresh, patch.object(
            sales_transaction_routes,
            "handle_sam_live_stock_chatwoot_inbound",
        ) as handle_inbound:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/inbound",
                json={
                    "event": "conversation_updated",
                    "message_type": "outgoing",
                    "id": 760224858,
                    "content": "Test received.",
                    "conversation": {"id": 2021},
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["status"],
            "outgoing_owner_reply_event_not_supported",
        )
        record.assert_not_called()
        refresh.assert_not_called()
        handle_inbound.assert_not_called()

    def test_sam_live_stock_approved_send_echo_is_not_captured(self):
        with patch.object(
            sales_transaction_routes,
            "authorize_sam_live_stock_webhook",
            return_value=(True, {}),
        ), patch.object(
            sales_transaction_routes,
            "record_sales_conversation_learning_event",
        ) as record, patch.object(
            sales_transaction_routes,
            "handle_sam_live_stock_chatwoot_inbound",
        ) as handle_inbound:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/inbound",
                json={
                    "event": "message_created",
                    "message_type": "outgoing",
                    "source_id": "sam_live_stock:abc123",
                    "content_attributes": {"amadeus_source": "sam_live_stock_owner_approved_send"},
                    "content": "Owner-approved SAM reply",
                    "conversation": {"id": 1840, "inbox": {"channel_type": "Channel::Whatsapp"}},
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "sam_live_stock_send_echo_skipped")
        record.assert_not_called()
        handle_inbound.assert_not_called()

    def test_protected_action_creates_one_owner_decision_notification_without_escalation(self):
        event = {
            "sam_reply_excerpt": "I can ask the farm to approve the exact animals before confirming anything.",
            "recommended_action": "owner_authority_decision",
            "no_reply_recommended": False,
            "escalation_required": False,
            "review_json": {
                "owner_authority_required": True,
                "protected_action_reasons": ["reservation_owner_authority"],
            },
        }

        self.assertTrue(sales_transaction_routes._sam_live_stock_owner_review_notification_needed(event))
        event["review_json"]["owner_authority_required"] = False
        self.assertFalse(sales_transaction_routes._sam_live_stock_owner_review_notification_needed(event))

    def test_order_document_delivery_echo_is_not_captured_as_owner_reply(self):
        with patch.object(
            sales_transaction_routes,
            "authorize_sam_live_stock_webhook",
            return_value=(True, {}),
        ), patch.object(
            sales_transaction_routes,
            "record_sales_conversation_learning_event",
        ) as record, patch.object(
            sales_transaction_routes,
            "handle_sam_live_stock_chatwoot_inbound",
        ) as handle_inbound:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/inbound",
                json={
                    "event": "message_created",
                    "message_type": "outgoing",
                    "source_id": "order_document:DOC-1",
                    "content_attributes": {"amadeus_source": "order_document_delivery"},
                    "content": "Please find your quote attached: Q-1",
                    "conversation": {"id": 1840, "inbox": {"channel_type": "Channel::Whatsapp"}},
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "sam_live_stock_send_echo_skipped")
        record.assert_not_called()
        handle_inbound.assert_not_called()

    def test_sam_live_stock_owner_reply_learning_failure_still_returns_200(self):
        with patch.object(
            sales_transaction_routes,
            "authorize_sam_live_stock_webhook",
            return_value=(True, {}),
        ), patch.object(
            sales_transaction_routes,
            "get_latest_sam_live_stock_review_event_for_conversation",
            return_value=({"success": False, "status": "database_url_not_configured"}, 503),
        ), patch.object(
            sales_transaction_routes,
            "record_sales_conversation_learning_event",
            return_value=({"success": False, "status": "not_configured"}, 503),
        ), patch.object(
            sales_transaction_routes,
            "handle_sam_live_stock_chatwoot_inbound",
        ) as handle_inbound:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/inbound",
                json={
                    "event": "message_created",
                    "message_type": "outgoing",
                    "id": 9002,
                    "content": "Owner reply",
                    "conversation": {"id": 1840, "inbox": {"channel_type": "Channel::Whatsapp"}},
                },
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["captured"])
        self.assertEqual(payload["learning_status_code"], 503)
        handle_inbound.assert_not_called()

    def test_sam_live_stock_review_and_owner_send_routes_are_gated(self):
        with patch.object(
            sales_transaction_routes,
            "review_sam_live_stock_conversation",
            return_value={"score": 88, "escalation_required": True},
        ) as review:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/review",
                json={"inbound": {"content": "scam"}, "facts": {}, "decision": {}},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["review"]["escalation_required"])
        review.assert_called_once()

        with patch.object(
            sales_transaction_routes,
            "send_owner_approved_live_stock_reply",
            return_value=({"success": False, "status": "sam_live_stock_owner_send_disabled"}, 409),
        ) as send_reply:
            send_response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/owner-send",
                json={"conversation_id": "2401", "message": "Owner approved"},
            )

        self.assertEqual(send_response.status_code, 409)
        self.assertEqual(send_response.get_json()["status"], "sam_live_stock_owner_send_disabled")
        send_reply.assert_called_once()

    def test_sam_live_stock_cleanup_packet_route_is_non_destructive(self):
        response = self.client.post(
            "/api/sales/channels/chatwoot/sam-live-stock/escalations/SAM-LIVE-ESC-1/cleanup-packet",
            json={"telegram_chat_id": "5721652188", "telegram_message_id": "99", "conversation_id": "2401"},
        )

        self.assertEqual(response.status_code, 200)
        packet = response.get_json()["cleanup_packet"]
        self.assertTrue(packet["delete_allowed"])
        self.assertEqual(packet["recommended_action"], "delete_telegram_notification")
        self.assertFalse(packet["calls_chatwoot"])

    def test_sam_live_stock_launch_control_routes_call_services(self):
        with patch.object(
            sales_transaction_routes,
            "send_sam_live_stock_telegram_escalation",
            return_value=({"success": False, "status": "sam_live_stock_telegram_send_disabled"}, 409),
        ) as send_telegram:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/escalations/send-telegram",
                json={"telegram_packet": {"text": "Escalation"}},
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["status"], "sam_live_stock_telegram_send_disabled")
        send_telegram.assert_called_once()

        with patch.object(
            sales_transaction_routes,
            "process_sam_live_stock_owner_callback",
            return_value=({"success": True, "status": "sam_live_stock_escalation_closed_without_reply"}, 200),
        ) as callback:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/escalations/callback",
                json={"callback_data": "sam_live_close:SAM-LIVE-ESC-1"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "sam_live_stock_escalation_closed_without_reply")
        callback.assert_called_once()

        with patch.object(
            sales_transaction_routes,
            "delete_sam_live_stock_telegram_escalation",
            return_value=({"success": False, "status": "sam_live_stock_telegram_cleanup_disabled"}, 409),
        ) as delete_telegram:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/escalations/SAM-LIVE-ESC-1/delete-telegram",
                json={"telegram_chat_id": "555", "telegram_message_id": "123"},
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["status"], "sam_live_stock_telegram_cleanup_disabled")
        delete_telegram.assert_called_once_with("SAM-LIVE-ESC-1", "555", "123")

        with patch.object(
            sales_transaction_routes,
            "list_sam_live_stock_open_intakes",
            return_value=({"success": True, "open_intakes": [{"intake_id": "INTAKE-1"}]}, 200),
        ) as open_intakes:
            response = self.client.get("/api/sales/channels/chatwoot/sam-live-stock/open-intakes?limit=10")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["open_intakes"][0]["intake_id"], "INTAKE-1")
        open_intakes.assert_called_once_with(limit="10")

        with patch.object(
            sales_transaction_routes,
            "build_sam_live_stock_launch_readiness",
            return_value=({"success": True, "boost_ready": False, "score": 92}, 200),
        ) as readiness:
            response = self.client.get("/api/sales/channels/chatwoot/sam-live-stock/launch-readiness")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["boost_ready"])
        readiness.assert_called_once()

    def test_sam_live_stock_human_audit_route_never_returns_generic_500(self):
        with patch.object(
            sales_transaction_routes,
            "audit_sam_live_stock_human_conversations",
            side_effect=AttributeError("customer-secret"),
        ):
            response = self.client.get(
                "/api/sales/channels/chatwoot/sam-live-stock/human-mode-audit"
            )

        self.assertEqual(response.status_code, 500)
        payload = response.get_json()
        self.assertEqual(payload["failure_stage"], "audit_execution")
        self.assertEqual(payload["error_type"], "AttributeError")
        self.assertFalse(payload["bulk_reset_allowed"])
        self.assertNotIn("customer-secret", str(payload))

    def test_sam_live_stock_human_audit_route_catches_serialization_failure(self):
        with patch.object(
            sales_transaction_routes,
            "audit_sam_live_stock_human_conversations",
            return_value=({"success": True, "unsafe": object()}, 200),
        ):
            response = self.client.get(
                "/api/sales/channels/chatwoot/sam-live-stock/human-mode-audit"
            )

        self.assertEqual(response.status_code, 500)
        payload = response.get_json()
        self.assertEqual(payload["failure_stage"], "json_serialization")
        self.assertFalse(payload["conversation_count_known"])
        self.assertFalse(payload["bulk_reset_allowed"])

    def test_sam_live_stock_takeover_and_reservation_routes_call_services(self):
        with patch.object(
            sales_transaction_routes,
            "apply_sam_live_stock_chatwoot_takeover",
            return_value=({"success": False, "status": "sam_live_stock_chatwoot_takeover_write_disabled"}, 409),
        ) as takeover:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/takeover",
                json={"conversation_id": "2401", "mode": "HUMAN", "reason": "test"},
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["status"], "sam_live_stock_chatwoot_takeover_write_disabled")
        takeover.assert_called_once_with("2401", mode="HUMAN", reason="test")

        response = self.client.post(
            "/api/sales/channels/chatwoot/sam-live-stock/reservation-plan",
            json={"order_id": "ORD-1", "match_packet": {"matched_sample": [{"pig_id": "PIG-1"}]}},
        )

        self.assertEqual(response.status_code, 200)
        plan = response.get_json()["reservation_plan"]
        self.assertTrue(plan["owner_gate_required"])
        self.assertFalse(plan["reserves_stock"])

        with patch.object(
            sales_transaction_routes,
            "execute_live_stock_order_reservation",
            return_value=({"success": False, "status": "sam_live_stock_order_reservation_disabled"}, 409),
        ) as reserve:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/order-reservation",
                json={"order_id": "ORD-1", "action": "reserve"},
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["status"], "sam_live_stock_order_reservation_disabled")
        reserve.assert_called_once_with("ORD-1", action="reserve")

    def test_auto_general_prepared_reply_creates_one_actionable_owner_card(self):
        event = {
            "review_event_id": "SAM-GENERAL-1994",
            "chatwoot_conversation_id": "1994",
            "sam_reply_excerpt": "Hi Henry! What would you like to know about Ms. Piggy and her litter?",
            "recommended_action": "auto_general_reply_candidate",
            "decision_json": {
                "conversation_ownership": "AUTO_GENERAL",
                "handled_autonomously": False,
                "owner_escalation_required": False,
                "specialist_tools_called": [],
                "reason": "routine_reply_waiting_for_owner",
                "transition_visibility": {
                    "status": "routine_reply_waiting_for_owner",
                    "notification_class": "owner_review",
                    "owner_action_required": True,
                },
            },
            "review_json": {
                "safe_to_send": True,
                "escalation_required": False,
            },
        }
        learning = {
            "success": True,
            "created": True,
            "review_event_id": "SAM-GENERAL-1994",
            "conversation_event_count": 1,
        }
        with patch.object(
            sales_transaction_routes,
            "send_sam_live_stock_owner_review_telegram",
            return_value=({"success": True, "status": "sent"}, 200),
        ) as review_send, patch.object(
            sales_transaction_routes,
            "send_sam_live_stock_new_lead_telegram",
        ) as new_lead_send:
            notification = sales_transaction_routes._send_sam_live_stock_owner_notification_if_needed(
                event,
                learning,
            )
        self.assertTrue(notification["attempted"])
        self.assertEqual(notification["type"], "owner_review")
        self.assertEqual(notification["reason"], "routine_reply_waiting_for_owner")
        review_send.assert_called_once_with(event)
        new_lead_send.assert_not_called()

    def test_auto_general_confirmed_send_and_replay_do_not_create_telegram_card(self):
        learning = {
            "success": True,
            "created": True,
            "review_event_id": "SAM-GENERAL-CONFIRMED",
            "conversation_event_count": 1,
        }
        with patch.object(
            sales_transaction_routes,
            "send_sam_live_stock_owner_review_telegram",
        ) as review_send:
            for transition_status, expected_status in (
                ("routine_reply_confirmed_delivered", "auto_general_confirmed_delivered_no_telegram"),
                ("routine_reply_accepted_unverified", "auto_general_accepted_unverified_observation_window"),
                ("routine_reply_replay_withheld", "auto_general_replay_owned_no_duplicate_telegram"),
            ):
                event = {
                    "decision_json": {
                        "conversation_ownership": "AUTO_GENERAL",
                        "owner_escalation_required": False,
                        "transition_visibility": {"status": transition_status},
                    },
                    "review_json": {"escalation_required": False},
                }
                notification = sales_transaction_routes._send_sam_live_stock_owner_notification_if_needed(
                    event,
                    learning,
                )
                self.assertFalse(notification["attempted"])
                self.assertEqual(notification["status"], expected_status)
        review_send.assert_not_called()

    def test_auto_general_failed_and_ambiguous_send_create_one_exception_card(self):
        learning = {
            "success": True,
            "created": True,
            "review_event_id": "SAM-GENERAL-DELIVERY",
            "conversation_event_count": 1,
        }
        for transition_status in (
            "routine_reply_delivery_failed",
            "routine_reply_delivery_ambiguous",
        ):
            event = {
                "decision_json": {
                    "conversation_ownership": "AUTO_GENERAL",
                    "owner_escalation_required": False,
                    "transition_visibility": {"status": transition_status},
                },
                "review_json": {"escalation_required": False},
            }
            with self.subTest(transition_status=transition_status), patch.object(
                sales_transaction_routes,
                "send_sam_live_stock_owner_review_telegram",
                return_value=({"success": True, "status": "sent"}, 200),
            ) as review_send:
                notification = sales_transaction_routes._send_sam_live_stock_owner_notification_if_needed(
                    event,
                    learning,
                )
                self.assertTrue(notification["attempted"])
                self.assertEqual(notification["type"], "delivery_exception")
                self.assertEqual(notification["reason"], transition_status)
                review_send.assert_called_once_with(event)

    def test_auto_general_explicit_human_request_remains_exception_telegram(self):
        event = {
            "review_event_id": "SAM-GENERAL-HUMAN",
            "chatwoot_conversation_id": "2401",
            "sam_reply_excerpt": "Of course, I will ask Charl to help.",
            "recommended_action": "owner_handoff",
            "decision_json": {
                "conversation_ownership": "AUTO_GENERAL",
                "handled_autonomously": False,
                "owner_escalation_required": True,
                "escalation_packet": {"reason": "customer_explicitly_requested_human"},
            },
            "review_json": {
                "safe_to_send": False,
                "escalation_required": True,
                "escalation_reasons": ["customer_explicitly_requested_human"],
            },
        }
        learning = {
            "success": True,
            "created": True,
            "review_event_id": "SAM-GENERAL-HUMAN",
            "conversation_event_count": 1,
        }
        with patch.object(
            sales_transaction_routes,
            "send_sam_live_stock_owner_review_telegram",
            return_value=({"success": True, "status": "sent"}, 200),
        ) as review_send:
            notification = sales_transaction_routes._send_sam_live_stock_owner_notification_if_needed(
                event,
                learning,
            )
        self.assertTrue(notification["attempted"])
        self.assertEqual(notification["legacy_reason"], "escalation")
        review_send.assert_called_once()


    def test_sam_meat_readiness_probe_denies_anonymous_and_is_disabled_by_default(self):
        denied = ({"success": False, "status": "owner_read_access_denied"}, 403)
        with patch.object(sales_transaction_routes, "require_owner_read_access", return_value=denied), patch.object(
            sales_transaction_routes, "run_sam_meat_readiness_probe"
        ) as probe:
            response = self.client.get("/api/sales/channels/chatwoot/sam-meat/readiness-probe")
        self.assertEqual(response.status_code, 403)
        probe.assert_not_called()

        with patch.object(sales_transaction_routes, "require_owner_read_access", return_value=None), patch.object(
            sales_transaction_routes,
            "run_sam_meat_readiness_probe",
            return_value=({"success": False, "status": "sam_meat_readiness_probe_disabled", "writes_performed": False}, 503),
        ) as probe:
            response = self.client.get("/api/sales/channels/chatwoot/sam-meat/readiness-probe")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.get_json()["writes_performed"])
        probe.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
