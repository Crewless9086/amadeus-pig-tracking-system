import unittest
from unittest.mock import patch

from flask import Flask

from modules.orders.livestock_quote_preview import build_livestock_quote_preview, build_already_sold_recording_preview
from modules.orders.order_routes import orders_bp


REQUEST = [
    {"request_item_key": "f5", "category": "Piglet", "weight_range": "5_to_6_Kg", "sex": "Female", "quantity": 10},
    {"request_item_key": "m5", "category": "Piglet", "weight_range": "5_to_6_Kg", "sex": "Male", "quantity": 10},
    {"request_item_key": "f15", "category": "Piglet", "weight_range": "15_to_19_Kg", "sex": "Female", "quantity": 1},
    {"request_item_key": "m15", "category": "Piglet", "weight_range": "15_to_19_Kg", "sex": "Male", "quantity": 1},
]


def axis(state="eligible", reason="supported", evidence_ids=()):
    return {"state": state, "reason": reason, "evidence_ids": list(evidence_ids)}


def candidate(pig_id, tag, sex, weight, *, transfer="eligible_on_current_evidence",
              purpose="Sale", adg=.2, disclosure=None):
    blocked = transfer != "eligible_on_current_evidence"
    return {
        "identity": {"pig_id": pig_id, "tag_number": tag, "name": None, "animal_type": "Weaner"},
        "current_state": {"purpose": purpose, "status": "Active", "on_farm": True,
                          "sex": sex, "latest_weight_kg": weight,
                          "latest_weight_date": "2026-08-11", "average_daily_gain_kg": adg},
        "livestock_transfer_eligibility": axis(
            transfer, "Current live-transfer evidence is incomplete." if blocked else "Every gate is supported.",
            ["OBS-1"] if blocked else []),
        "food_chain_eligibility": axis("blocked", "Food-chain withdrawal applies.", ["MED-1"]) if disclosure else axis("eligible"),
        "fit_for_transport": axis("Unknown", "Transport fitness is Unknown.", ["OBS-1"]) if blocked else axis("eligible"),
        "quarantine": axis("eligible"), "notifiable_or_infectious_disease": axis("eligible"),
        "veterinary_movement_stop": axis("eligible"), "serious_health_or_welfare_hold": axis("eligible"),
        "treatment_evidence_completeness": axis("eligible"), "treatment_evidence_conflicts": [],
        "medical_ambiguity": axis("clear"),
        "current_purpose_eligibility": axis("eligible" if purpose == "Sale" else "blocked", f"Current canonical purpose is {purpose}."),
        "active_on_farm_eligibility": axis("eligible"),
        "current_order_eligibility": axis("candidate_not_added"),
        "order_line_duplication_protection": axis("no_existing_line"),
        "price_band_compatibility": {"state": "compatible", "reason": "supported",
                                     "evidence_ids": [], "separate_price_rule":
                                     {"unit_price": 650, "currency": "ZAR"}},
        "canonical_dependency_evidence": {}, "canonical_treatment_events": [],
        "treatment_disclosure": disclosure,
    }


def packet(pigs):
    return {"contract_version": "herdmaster_live_transfer_disclosure_v1",
            "packet_digest": "digest-123", "evidence_cutoff_date": "2026-08-17",
            "pigs": pigs, "writes_performed": False}


class LivestockQuotePreviewTests(unittest.TestCase):
    def test_already_sold_report_requires_irreducible_fields_without_writes(self):
        result = build_already_sold_recording_preview(
            {"tag_numbers": ["123", "151"], "sold_date": "2026-08-16"},
            packet([candidate("P123", "123", "Male", 5.6), candidate("P151", "151", "Male", 4.0)]),
        )
        self.assertFalse(result["ready_for_protected_confirmation"])
        self.assertEqual(set(result["missing_fields"]), {"buyer_name", "sale_channel", "movement_destination"})
        self.assertFalse(result["writes_performed"])
        self.assertFalse(result["changes_pig_state"])

    def test_already_sold_complete_form_binds_exact_pigs(self):
        payload = {"tag_numbers":["123","151"], "sold_date":"2026-08-16", "buyer_name":"Named buyer", "sale_channel":"Farm gate", "movement_destination":"Named destination", "movement_evidence_reference":"MOVE-REF", "health_evidence_reference":"HEALTH-REF"}
        result = build_already_sold_recording_preview(payload, packet([candidate("P123", "123", "Male", 5.6), candidate("P151", "151", "Male", 4.0)]))
        self.assertFalse(result["ready_for_protected_confirmation"])
        self.assertIn("protected Livestock order completion rail", result["confirmation_scope"])
        self.assertEqual([row["tag_number"] for row in result["selected_pigs"]], ["123", "151"])
        self.assertRegex(result["preview_digest"], r"^[0-9a-f]{64}$")
        self.assertFalse(result["creates_order"])

    def test_exact_four_lines_total_22_and_candidates_never_repeat(self):
        pigs = []
        for sex, prefix in (("Female", "F"), ("Male", "M")):
            pigs.extend(candidate(f"{prefix}{i}", f"{prefix}{i}", sex, 5.5) for i in range(1, 11))
            pigs.append(candidate(f"{prefix}15", f"{prefix}15", sex, 16))
        result = build_livestock_quote_preview(REQUEST, packet(pigs), observed_at="2026-08-17T12:00:00Z")
        self.assertEqual(sum(row["requested_quantity"] for row in result["recommendations"]), 22)
        self.assertEqual([row["request_item_key"] for row in result["recommendations"]], ["f5", "m5", "f15", "m15"])
        selected = [pig["pig_id"] for row in result["recommendations"] for pig in row["candidates"]]
        self.assertEqual(len(selected), 22)
        self.assertEqual(len(set(selected)), 22)
        self.assertFalse(result["writes_performed"])
        self.assertEqual(result["reservation_state"], "not_reserved")
        self.assertTrue(all(row["recommended_subtotal"] is not None
                            for row in result["recommendations"]))
        self.assertTrue(all(pig["medicine_indicator"]
                            for row in result["recommendations"] for pig in row["candidates"]))

    def test_exact_near_projected_and_shortfall_are_separate(self):
        pigs = [candidate("E", "1", "Male", 5.5), candidate("N", "2", "Male", 6.8, adg=0),
                candidate("P", "3", "Male", 4.5, adg=.2)]
        result = build_livestock_quote_preview([
            {"request_item_key": "m", "category": "Piglet", "weight_range": "5_to_6_Kg", "sex": "Male", "quantity": 4}
        ], packet(pigs))
        line = result["recommendations"][0]
        self.assertEqual((line["exact_match_count"], line["near_match_count"], line["projected_count"]), (1, 1, 1))
        self.assertEqual((line["supported_count"], line["shortfall_quantity"]), (3, 1))
        projected = next(row for row in line["candidates"] if row["match_state"] == "projected_growth")
        self.assertEqual(projected["projected_target_date"], "2026-08-20")

    def test_available_quantity_reports_all_eligible_not_only_requested_recommendations(self):
        pigs = [candidate(f"M{i}", f"M{i}", "Male", 5.5) for i in range(1, 5)]
        result = build_livestock_quote_preview([{
            "request_item_key": "m", "category": "Piglet", "weight_range": "5_to_6_Kg",
            "sex": "Male", "quantity": 2,
        }], packet(pigs))
        line = result["recommendations"][0]
        self.assertEqual(line["available_quantity"], 4)
        self.assertEqual(line["supported_count"], 2)
        self.assertEqual(len(line["candidates"]), 2)
        self.assertEqual(line["shortfall_quantity"], 0)

    def test_category_mismatch_and_stale_or_future_growth_fail_closed(self):
        wrong_category = candidate("S", "S1", "Male", 5.5)
        wrong_category["identity"]["animal_type"] = "Sow"
        stale = candidate("OLD", "O1", "Male", 4.5)
        stale["current_state"]["latest_weight_date"] = "2026-07-01"
        future = candidate("FUT", "F1", "Male", 4.5)
        future["current_state"]["latest_weight_date"] = "2026-08-18"
        result = build_livestock_quote_preview([
            {"request_item_key": "m", "category": "Piglet", "weight_range": "5_to_6_Kg", "sex": "Male", "quantity": 3}
        ], packet([wrong_category, stale, future]))
        line = result["recommendations"][0]
        self.assertEqual(line["projected_count"], 0)
        self.assertEqual(line["near_match_count"], 0)
        self.assertEqual(line["supported_count"], 0)
        self.assertEqual(line["shortfall_quantity"], 3)
        weight_review = next(group for group in result["purpose_or_evidence_review"]
                             if group["blocking_axis"] == "weight_evidence")
        self.assertEqual({row["pig_id"] for row in weight_review["candidates"]}, {"OLD", "FUT"})

    def test_stale_exact_weight_is_recommended_with_fresh_weight_request(self):
        stale = candidate("OLD-EXACT", "OE", "Male", 5.5)
        stale["current_state"]["latest_weight_date"] = "2026-07-01"
        result = build_livestock_quote_preview([
            {"request_item_key": "m", "category": "Piglet", "weight_range": "5_to_6_Kg", "sex": "Male", "quantity": 1}
        ], packet([stale]))
        self.assertEqual(result["recommendations"][0]["supported_count"], 1)
        self.assertEqual(result["recommendations"][0]["shortfall_quantity"], 0)
        self.assertEqual(result["recommendations"][0]["candidates"][0]["weight_confidence"], "fresh_weight_requested")

    def test_unknown_and_non_sale_are_grouped_and_never_counted(self):
        disclosure = {"medical_event_id": "MED-1", "safe_buyer_wording": "Food-chain withdrawal applies."}
        pigs = [candidate("U", "151", "Male", 5.5, transfer="Unknown", disclosure=disclosure),
                candidate("B", "152", "Male", 5.6, purpose="Breeding")]
        result = build_livestock_quote_preview([
            {"request_item_key": "m", "category": "Piglet", "weight_range": "5_to_6_Kg", "sex": "Male", "quantity": 1}
        ], packet(pigs))
        self.assertEqual(result["recommendations"][0]["supported_count"], 0)
        self.assertEqual(result["recommendations"][0]["shortfall_quantity"], 1)
        groups = result["purpose_or_evidence_review"]
        self.assertTrue(any(group["blocking_axis"] == "livestock_transfer_eligibility" for group in groups))
        self.assertTrue(any(group["blocking_axis"] == "current_purpose_eligibility" for group in groups))
        unknown = next(group for group in groups if group["blocking_axis"] == "livestock_transfer_eligibility")
        self.assertEqual(unknown["evidence_ids"], ["OBS-1"])
        self.assertEqual(unknown["candidates"][0]["treatment_disclosure"], disclosure)

    def test_active_line_conflict_fails_closed(self):
        pig = candidate("D", "123", "Male", 5.5)
        pig["order_line_duplication_protection"] = axis("conflicting_duplicate_lines", "Two active lines.", ["OL-1", "OL-2"])
        result = build_livestock_quote_preview([REQUEST[1]], packet([pig]))
        self.assertEqual(result["recommendations"][0]["supported_count"], 0)
        self.assertTrue(any(group["blocking_axis"] == "order_line_duplication_protection"
                            for group in result["purpose_or_evidence_review"]))


class LivestockQuotePreviewRouteTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(orders_bp, url_prefix="/api")
        app.config.update(TESTING=True)
        self.client = app.test_client()
        self.payload = {"requested_items": [REQUEST[1]]}

    def test_auth_guard_runs_before_canonical_read(self):
        denied = ({"success": False}, 403)
        with patch("modules.orders.order_routes.require_owner_read_access", return_value=denied), patch(
            "modules.orders.order_routes.build_live_transfer_preview_contract"
        ) as loader:
            response = self.client.post("/api/orders/livestock-quote-preview", json=self.payload)
        self.assertEqual(response.status_code, 403)
        loader.assert_not_called()

    def test_failed_canonical_snapshot_fails_closed_without_internal_detail(self):
        with patch("modules.orders.order_routes.require_owner_read_access", return_value=None), patch(
            "modules.orders.order_routes.build_live_transfer_preview_contract",
            side_effect=RuntimeError("private-provider-detail"),
        ):
            response = self.client.post("/api/orders/livestock-quote-preview", json=self.payload)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["errors"], ["Preview evidence is currently unavailable."])
        self.assertFalse(response.get_json()["writes_performed"])

    def test_successful_route_preserves_zero_write_flags(self):
        forbidden = {
            name: unittest.mock.DEFAULT for name in (
                "create_order", "create_order_line", "create_order_with_lines",
                "sync_order_lines_from_request", "reserve_order_lines",
                "auto_generate_quote_if_ready", "generate_quote_for_order", "send_order_document",
            )
        }
        with patch("modules.orders.order_routes.require_owner_read_access", return_value=None), patch(
            "modules.orders.order_routes.build_live_transfer_preview_contract",
            return_value=packet([]),
        ), patch.multiple("modules.orders.order_routes", **forbidden) as prohibited:
            response = self.client.post("/api/orders/livestock-quote-preview", json=self.payload)
        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(body["writes_performed"])
        self.assertFalse(body["creates_order"])
        self.assertFalse(body["creates_order_line"])
        self.assertFalse(body["creates_reservation"])
        self.assertFalse(body["generates_document"])
        for mocked in prohibited.values():
            mocked.assert_not_called()

    def test_already_sold_preview_is_owner_read_guarded_and_zero_write(self):
        payload = {"tag_numbers": ["123", "151"], "sold_date": "2026-08-16"}
        with patch("modules.orders.order_routes.require_owner_read_access", return_value=None), patch(
            "modules.orders.order_routes.build_live_transfer_preview_contract",
            return_value=packet([candidate("P123", "123", "Male", 5.6), candidate("P151", "151", "Male", 4.0)]),
        ):
            response = self.client.post("/api/orders/already-sold-preview", json=payload)
        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(body["writes_performed"])
        self.assertFalse(body["ready_for_protected_confirmation"])
        self.assertEqual([row["tag_number"] for row in body["selected_pigs"]], ["123", "151"])


if __name__ == "__main__":
    unittest.main()
