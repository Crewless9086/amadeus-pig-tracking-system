import unittest
from unittest.mock import patch

from app import app
from modules.sales import sam_command_state, sales_transaction_routes


LEAD_ID = "OSK-SALES-LEAD-TEST"


def contract_response(missing=None, contract_status="needs_owner_confirmation", events=None, window="open"):
    interest = {
        "product_type": "half_carcass",
        "cut_set": "Set A",
        "location": "Riversdale",
        "timing": "next available",
        "delivery_or_collection": "delivery",
    }
    for field in missing or []:
        interest.pop(field, None)
    return {
        "success": True,
        "status": "ok",
        "lead_id": LEAD_ID,
        "lead": {
            "lead_id": LEAD_ID,
            "contact_label": "Charl Buyer",
            "status": "launch_test",
            "whatsapp_window_state": window,
            "interest": interest,
            "events": list(events or []),
            "latest_event": (list(events or []) or [{}])[0],
        },
        "contract": {
            "contract_status": contract_status,
            "missing_fields": list(missing or []),
            "lead_summary": interest,
        },
    }


def ok_pricing():
    return {"success": True, "status": "ok", "pricing_estimate": {"estimated_total_label": "R3,250.00"}}, 200


def ok_match():
    return {
        "success": True,
        "status": "ok",
        "meat_match": {"recommendation": {"pig_id": "PIG-1"}},
    }, 200


def ok_ops(payment_state="deposit_not_received", reservations=None, drafts=None):
    payment_gate = {
        "state": payment_state,
        "pop_received_unverified": payment_state == "pop_received_unverified",
        "deposit_confirmed_in_bank": payment_state == "deposit_confirmed_in_bank",
        "unlocks_slaughter_or_delivery": payment_state == "deposit_confirmed_in_bank",
    }
    return {
        "success": True,
        "status": "ok",
        "reservations": list(reservations or []),
        "deposits": [],
        "instruction_drafts": list(drafts or []),
        "assembly": {"status": "none"},
        "payment_gate": payment_gate,
    }, 200


def ok_fulfillment():
    return {"success": True, "status": "ok", "fulfillment": {"next_gate": "record_final_packed_weight"}}, 200


def ok_reconciliation():
    return {"success": True, "status": "ok", "reconciliation": {"next_gate": "record_actual_packed_weight"}}, 200


class SamCommandStateTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()

    def _patch_read_sources(self, contract=None, pricing=None, match=None, ops=None, fulfillment=None, reconciliation=None):
        patches = [
            patch.object(sam_command_state, "get_sales_lead_preorder_contract", return_value=(contract or contract_response(), 200)),
            patch.object(sam_command_state, "get_sales_lead_pricing_estimate", return_value=pricing or ok_pricing()),
            patch.object(sam_command_state, "get_sales_lead_meat_match", return_value=match or ok_match()),
            patch.object(sam_command_state, "get_meat_ops_status", return_value=ops or ok_ops()),
            patch.object(sam_command_state, "get_meat_fulfillment_timeline", return_value=fulfillment or ok_fulfillment()),
            patch.object(sam_command_state, "get_meat_reconciliation_status", return_value=reconciliation or ok_reconciliation()),
        ]
        return patches

    def _service_result(self, **kwargs):
        patches = self._patch_read_sources(**kwargs)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            return sam_command_state.get_sam_command_state(LEAD_ID)

    def test_valid_lead_returns_200_and_ok_true(self):
        result, status = self._service_result()
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertEqual(result["lead_id"], LEAD_ID)

    def test_unknown_lead_returns_404(self):
        with patch.object(
            sam_command_state,
            "get_sales_lead_preorder_contract",
            return_value=({"success": False, "status": "not_found"}, 404),
        ):
            result, status = sam_command_state.get_sam_command_state("missing")
        self.assertEqual(status, 404)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "sales_lead_not_found")

    def test_remote_access_is_denied_when_guard_applies(self):
        response = self.client.get(
            f"/api/sales/meat-leads/{LEAD_ID}/command-state",
            environ_base={"REMOTE_ADDR": "8.8.8.8"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["status"], "sam_command_state_access_denied")

    def test_local_owner_read_access_is_allowed(self):
        with patch.object(sales_transaction_routes, "get_sam_command_state", return_value=({"ok": True}, 200)) as command_state:
            response = self.client.get(
                f"/api/sales/meat-leads/{LEAD_ID}/command-state",
                environ_base={"REMOTE_ADDR": "127.0.0.1"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        command_state.assert_called_once_with(LEAD_ID)

    @patch.dict("os.environ", {"SAM_COMMAND_STATE_OWNER_TOKEN": "x" * 40}, clear=False)
    def test_remote_owner_token_read_access_is_allowed(self):
        with patch.object(sales_transaction_routes, "get_sam_command_state", return_value=({"ok": True}, 200)) as command_state:
            response = self.client.get(
                f"/api/sales/meat-leads/{LEAD_ID}/command-state",
                headers={"Authorization": f"Bearer {'x' * 40}"},
                environ_base={"REMOTE_ADDR": "8.8.8.8"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])
        command_state.assert_called_once_with(LEAD_ID)

    def test_missing_facts_returns_missing_facts_next_action(self):
        result, _ = self._service_result(contract=contract_response(missing=["product_type"]))
        self.assertEqual(result["next_action"]["key"], "missing_facts")
        self.assertIn("product_type", result["missing_facts"]["missing"])

    def test_money_review_lead_returns_owner_price_deposit_review(self):
        result, _ = self._service_result(contract=contract_response(missing=[]))
        self.assertEqual(result["next_action"]["key"], "owner_price_deposit_review")

    def test_draft_ready_lead_returns_build_draft_reply(self):
        result, _ = self._service_result(contract=contract_response(missing=[], contract_status="owner_money_path_ready"))
        self.assertEqual(result["next_action"]["key"], "build_draft_reply")
        self.assertEqual(result["draft_reply"]["status"], "not_generated")

    def test_approved_draft_returns_send_review_but_cannot_send(self):
        event = {"event_type": "owner_customer_followup_send_approved"}
        result, _ = self._service_result(
            contract=contract_response(missing=[], contract_status="owner_money_path_ready", events=[event], window="unknown")
        )
        self.assertEqual(result["next_action"]["key"], "ready_for_owner_send_review")
        self.assertFalse(result["draft_reply"]["can_send"])
        self.assertIn("whatsapp_window_not_open", result["next_action"]["blocked_reasons"])

    def test_pop_only_does_not_unlock_money_or_slaughter_gate(self):
        events = [{"event_type": "customer_followup_sent"}, {"event_type": "customer_booking_confirmed"}]
        result, _ = self._service_result(
            contract=contract_response(missing=[], contract_status="owner_money_path_ready", events=events),
            ops=ok_ops(payment_state="pop_received_unverified"),
        )
        self.assertEqual(result["money_gate"]["status"], "blocked")
        self.assertEqual(result["next_action"]["key"], "confirm_money_in_bank")
        self.assertIn("bank_confirmation_required", result["next_action"]["blocked_reasons"])

    def test_no_reservation_public_post_or_send_is_created(self):
        with patch.object(sam_command_state, "get_sales_lead_preorder_contract", return_value=(contract_response(), 200)), \
             patch.object(sam_command_state, "get_sales_lead_pricing_estimate", return_value=ok_pricing()), \
             patch.object(sam_command_state, "get_sales_lead_meat_match", return_value=ok_match()), \
             patch.object(sam_command_state, "get_meat_ops_status", return_value=ok_ops()), \
             patch.object(sam_command_state, "get_meat_fulfillment_timeline", return_value=ok_fulfillment()), \
             patch.object(sam_command_state, "get_meat_reconciliation_status", return_value=ok_reconciliation()):
            result, status = sam_command_state.get_sam_command_state(LEAD_ID)
        self.assertEqual(status, 200)
        self.assertFalse(result["sends_customer_message"])
        self.assertFalse(result["posts_publicly"])
        self.assertFalse(result["reserves_stock"])
        self.assertIn("reserve_carcass", result["forbidden_actions"])
        self.assertIn("create_public_post", result["forbidden_actions"])
        self.assertIn("send_customer_message", result["forbidden_actions"])

    def test_degraded_pricing_returns_degraded_money_gate(self):
        result, _ = self._service_result(
            pricing=({"success": False, "status": "pricing_unavailable"}, 503)
        )
        self.assertEqual(result["money_gate"]["status"], "degraded")
        self.assertIn("pricing_estimate", [item["source"] for item in result["degraded_sources"]])

    def test_degraded_beacon_returns_non_blocking_beacon_gate(self):
        patches = self._patch_read_sources()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            result, status = sam_command_state.get_sam_command_state(LEAD_ID, beacon_provider=lambda: (_ for _ in ()).throw(RuntimeError("down")))
        self.assertEqual(status, 200)
        self.assertEqual(result["beacon_gate"]["status"], "degraded")
        self.assertNotIn("create_public_post", result["safe_actions"])

    def test_history_summary_uses_existing_lead_events(self):
        events = [{"event_type": "customer_followup_sent"}, {"event_type": "owner_money_path_approved"}]
        result, _ = self._service_result(
            contract=contract_response(missing=[], contract_status="owner_money_path_ready", events=events)
        )
        self.assertEqual(result["history"]["event_count"], 2)
        self.assertEqual(result["history"]["latest_event"]["event_type"], "customer_followup_sent")

    def test_response_includes_source_refs(self):
        result, _ = self._service_result()
        self.assertIn("source_refs", result)
        self.assertIn("contract", [item["source"] for item in result["source_refs"]])

    def test_forbidden_actions_always_include_mutating_external_actions(self):
        result, _ = self._service_result()
        for action in ("send_customer_message", "create_public_post", "record_deposit", "reserve_carcass", "create_order"):
            self.assertIn(action, result["forbidden_actions"])

    def test_endpoint_does_not_mutate_supabase_state(self):
        result, _ = self._service_result()
        self.assertFalse(result["writes_to_supabase"])
        self.assertFalse(result["creates_order"])
        self.assertFalse(result["changes_stock"])


if __name__ == "__main__":
    unittest.main()
