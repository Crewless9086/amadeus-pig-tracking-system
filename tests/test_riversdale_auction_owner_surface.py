import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from modules.pig_weights.pig_weights_routes import pig_weights_bp
from modules.sales.riversdale_auction import (
    build_riversdale_auction_packet,
    record_owner_auction_decision,
    sanitized_owner_surface,
)


class _Cursor:
    def __init__(self, existing=None):
        self.existing = existing
        self.calls = []
        self._inserted = None

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if sql.lstrip().startswith("insert"):
            self._inserted = ("cycle",) if self.existing is None else None

    def fetchone(self):
        if self._inserted:
            value, self._inserted = self._inserted, None
            return value
        return self.existing

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class RiversdaleAuctionOwnerSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(pig_weights_bp, url_prefix="/api/pig-weights")
        self.client = self.app.test_client()

    def _packet(self):
        allocation = {"pigs": [
            {
                "pig_id": "PRIVATE-PIG", "tag_number": "PRIVATE-TAG",
                "growth_class": "Extremely Slow", "readiness_bucket": "Livestock Candidate",
                "health_status": "Healthy", "withdrawal_clear": "Yes",
                "observed_quality": "Suitable", "customer_suitability": "No direct buyer",
            },
            {"pig_id": "ALLOCATED-PIG", "readiness_bucket": "Allocated",
             "reserved_for_order_id": "PRIVATE-ORDER"},
        ]}
        return build_riversdale_auction_packet(
            allocation, today=date(2026, 8, 1),
            confirmation={
                "operating": True, "confirmed_date": "2026-08-05", "valid": True,
                "confirmed_at": "2026-07-26T10:00:00+02:00",
            },
            ledger_evidence={"PRIVATE-PIG": {
                "feed_cost_to_date": 100, "likely_auction_price": 180, "auction_costs": 20,
            }},
            sam_demand={"summary": "No direct-sale demand"},
            oom_sakkie_preparation={"summary": "Preparation evidenced"},
        )

    def test_aggregate_surface_has_counts_financials_and_no_private_identity(self):
        surface = sanitized_owner_surface(self._packet(), today=date(2026, 8, 1))
        self.assertEqual(surface["candidate_preview_count"], 1)
        self.assertEqual(surface["eligible_cohort_count"], 1)
        self.assertEqual(surface["excluded_count"], 1)
        self.assertEqual(surface["financials"]["likely_proceeds"], 180)
        self.assertEqual(surface["financials"]["net_margin"], 60)
        self.assertFalse(surface["reminders"]["delivery_operational"])
        serialized = json.dumps(surface)
        for private in ("PRIVATE-PIG", "PRIVATE-TAG", "PRIVATE-ORDER", "pig_id", "tag_number"):
            self.assertNotIn(private, serialized)
        self.assertFalse(surface["private_animal_evidence_present"])

    def test_missing_financial_evidence_is_unavailable_not_zero(self):
        packet = self._packet()
        packet["candidate_preview"][0]["ledger_evidence"] = {}
        financials = sanitized_owner_surface(packet)["financials"]
        self.assertEqual(financials["state"], "Unavailable")
        self.assertIsNone(financials["likely_proceeds"])
        self.assertIsNone(financials["net_margin"])

    def test_decision_is_append_only_idempotent_and_has_no_protected_side_effect(self):
        cursor = _Cursor()
        result, status = record_owner_auction_decision(
            {"operating": True, "confirmed_date": "2026-08-05",
             "idempotency_key": "owner-key"},
            actor_id="owner-admin:test", database_url="postgresql://test",
            connect_factory=lambda _url: _Connection(cursor),
        )
        self.assertEqual(status, 201)
        self.assertTrue(result["writes_auction_decision"])
        for key in (
            "creates_cohort", "creates_outlet_claim", "changes_pig_lifecycle",
            "changes_pig_purpose", "creates_order", "creates_reservation",
            "creates_sale", "books_auction", "contacts_customer_or_organizer",
            "sends_reminder",
        ):
            self.assertFalse(result[key])
        self.assertIn("on conflict (idempotency_key) do nothing", cursor.calls[0][0])

    def test_invalid_decision_never_writes(self):
        result, status = record_owner_auction_decision(
            {"operating": True, "idempotency_key": "owner-key"},
            actor_id="owner-admin:test",
        )
        self.assertEqual(status, 400)
        self.assertFalse(result["writes_auction_decision"])

    @patch("modules.pig_weights.pig_weights_routes.require_owner_admin_access")
    def test_anonymous_post_returns_structured_403(self, require_access):
        require_access.return_value = ({"success": False, "error": "owner_admin_required"}, 403)
        response = self.client.post("/api/pig-weights/riversdale-auction-confirmation", json={})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.get_json()["success"])

    @patch("modules.pig_weights.pig_weights_routes.owner_admin_principal", return_value="owner-admin:test")
    @patch("modules.pig_weights.pig_weights_routes.require_owner_admin_access", return_value=None)
    @patch("modules.pig_weights.pig_weights_routes.record_riversdale_auction_decision_data")
    def test_owner_admin_post_records_only_decision(self, record, _access, _principal):
        record.return_value = ({"success": True, "status": "auction_decision_recorded"}, 201)
        response = self.client.post(
            "/api/pig-weights/riversdale-auction-confirmation",
            json={"operating": False, "idempotency_key": "owner-key"},
        )
        self.assertEqual(response.status_code, 201)
        record.assert_called_once()

    def test_existing_page_has_one_panel_and_no_private_render_contract(self):
        html = Path("templates/pig-allocation.html").read_text(encoding="utf-8")
        js = Path("static/js/pigAllocation.js").read_text(encoding="utf-8")
        self.assertEqual(html.count('id="riversdale_auction_panel"'), 1)
        self.assertIn("/api/pig-weights/riversdale-auction-recommendation", js)
        self.assertIn("/api/pig-weights/riversdale-auction-confirmation", js)
        self.assertIn("data.owner_surface", js)
        self.assertNotIn("data.candidate_preview", js)
        self.assertNotIn("data.cohort", js)


if __name__ == "__main__":
    unittest.main()
