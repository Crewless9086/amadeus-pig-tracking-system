import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from modules.sales.riversdale_auction_list import (
    eligibility_tokens, read_auction_list, record_auction_list_events,
)
from modules.pig_weights.pig_weights_service import get_riversdale_auction_list


def packet(cycle="cycle-a", pig_id="PIG-1", *, eligible=True):
    evidence = {
        "withdrawal_clear": "Yes" if eligible else "Unknown",
        "observed_quality": "Suitable" if eligible else "Unknown",
        "health_status": "Clear" if eligible else "Hold",
    }
    return {
        "success": True,
        "confirmation": {"auction_cycle_id": cycle},
        "candidate_preview": [{"pig_id": pig_id, "herdmaster_evidence": evidence}],
        "coordination_evidence": {"herdmaster": "canonical_allocation_rows"},
    }


class RiversdaleAuctionListTests(unittest.TestCase):
    class _Cursor:
        def __init__(self, rows=None, error=None):
            self.rows = rows if rows is not None else [
                ("cycle-a", None, None, None, None, None, None)
            ]
            self.error = error

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _sql, _params=None):
            if self.error:
                raise self.error

        def fetchall(self):
            return self.rows

    class _Connection:
        def __init__(self, cursor):
            self._cursor = cursor

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def cursor(self):
            return self._cursor

    def _capturing_factory(self, captured, *, rows=None, error=None):
        def factory(url):
            captured.append(url)
            return self._Connection(self._Cursor(rows=rows, error=error))
        return factory

    def test_reader_uses_canonical_database_url_when_farm_override_absent(self):
        captured = []
        with patch.dict("os.environ", {
            "DATABASE_URL": "postgresql://canonical",
            "FARM_SUPABASE_DATABASE_URL": "",
        }, clear=False):
            result, status = read_auction_list(
                connect_factory=self._capturing_factory(captured)
            )
        self.assertEqual((status, result["status"]), (200, "available"))
        self.assertEqual(captured, ["postgresql://canonical"])

    def test_explicit_farm_override_precedes_canonical_database_url(self):
        captured = []
        with patch.dict("os.environ", {
            "DATABASE_URL": "postgresql://canonical",
            "FARM_SUPABASE_DATABASE_URL": "postgresql://farm-override",
        }, clear=False):
            result, status = read_auction_list(
                connect_factory=self._capturing_factory(captured)
            )
        self.assertEqual((status, result["status"]), (200, "available"))
        self.assertEqual(captured, ["postgresql://farm-override"])

    def test_neither_connection_configured_fails_before_connect(self):
        with patch.dict("os.environ", {
            "DATABASE_URL": "", "FARM_SUPABASE_DATABASE_URL": "",
        }, clear=False):
            result, status = read_auction_list()
        self.assertEqual((status, result["status"]),
                         (503, "auction_list_store_unavailable"))

    def test_malformed_or_unavailable_connection_fails_closed(self):
        captured = []
        result, status = read_auction_list(
            database_url="malformed",
            connect_factory=self._capturing_factory(
                captured, error=ConnectionError("unavailable")
            ),
        )
        self.assertEqual((status, result["status"]),
                         (503, "auction_list_store_unavailable"))
        self.assertEqual(result["error_type"], "ConnectionError")
        self.assertEqual(captured, ["malformed"])

    def test_unavailable_table_fails_closed(self):
        class UndefinedTable(Exception):
            pass

        result, status = read_auction_list(
            database_url="postgresql://test",
            connect_factory=self._capturing_factory([], error=UndefinedTable()),
        )
        self.assertEqual((status, result["status"]),
                         (503, "auction_list_store_unavailable"))
        self.assertEqual(result["error_type"], "UndefinedTable")

    def test_successful_zero_state_read_reports_available_empty_list(self):
        result, status = read_auction_list(
            database_url="postgresql://test",
            connect_factory=self._capturing_factory([]),
        )
        self.assertEqual((status, result["status"]), (200, "available"))
        self.assertEqual(result["auction_cycle_id"], "cycle-a")
        self.assertEqual(result["items"], [])
        self.assertEqual(result["causal_heads"], {})

    def test_existing_append_only_events_project_current_membership(self):
        rows = [
            ("cycle-a", "PIG-1", "added", "owner note",
             datetime(2026, 7, 27, tzinfo=timezone.utc), "EVENT-1", 1),
            ("cycle-a", "PIG-2", "removed", "",
             datetime(2026, 7, 27, tzinfo=timezone.utc), "EVENT-2", 2),
        ]
        result, status = read_auction_list(
            database_url="postgresql://test",
            connect_factory=self._capturing_factory([], rows=rows),
        )
        self.assertEqual((status, result["status"]), (200, "available"))
        self.assertEqual([item["pig_id"] for item in result["items"]], ["PIG-1"])
        self.assertEqual(result["causal_heads"]["PIG-2"]["decision_sequence"], 2)

    def test_missing_identity_and_incomplete_contract_fail_before_database(self):
        called = []
        factory = lambda _: called.append(True)
        payload = {"action": "add", "pig_ids": ["PIG-1"], "idempotency_key": "key"}
        loader = lambda *_: packet()
        self.assertEqual(record_auction_list_events(
            payload, actor_id="", eligibility_loader=loader, connect_factory=factory,
        )[1], 403)
        self.assertEqual(record_auction_list_events(
            payload, actor_id="owner", eligibility_loader=loader, connect_factory=factory,
        )[1], 400)
        self.assertEqual(called, [])

    def test_tokens_are_only_issued_for_affirmatively_eligible_evidence(self):
        self.assertIn("PIG-1", eligibility_tokens(packet()))
        self.assertEqual(eligibility_tokens(packet(eligible=False)), {})

    def test_frontend_binds_cycle_evidence_and_prior_cause(self):
        js = Path("static/js/pigAllocation.js").read_text(encoding="utf-8")
        for contract_field in (
            "auction_cycle_id:auctionCycleId",
            "eligibility_tokens:Object.fromEntries",
            "prior_event_ids:Object.fromEntries",
        ):
            self.assertIn(contract_field, js)
        self.assertIn('action === "remove" && !window.confirm', js)

    def test_integrated_table_contract_and_zero_authority(self):
        html = Path("templates/pig-allocation.html").read_text(encoding="utf-8")
        js = Path("static/js/pigAllocation.js").read_text(encoding="utf-8")
        self.assertNotIn('id="riversdale_candidate_review"', html)
        self.assertNotIn("renderAuctionCandidateReviews", js)
        for text in ("Auction Candidates", "Auction List", "Select all visible",
                     "Clear selection", "Add selected to Auction List",
                     "Remove selected", "Print Auction List"):
            self.assertIn(text, html + js)
        source = Path("modules/sales/riversdale_auction_list.py").read_text()
        for marker in (
            '"creates_cohort": False', '"creates_outlet_assignment": False',
            '"creates_reservation": False', '"books_auction": False',
            '"creates_sale": False', '"contacts_customer": False',
            '"sends_reminder": False', '"changes_animal_or_farm_state": False',
        ):
            self.assertIn(marker, source)

    def test_migration_is_causal_append_only_and_not_assignment(self):
        sql = Path(
            "supabase/migrations/202607260009_create_riversdale_auction_list_events.sql"
        ).read_text(encoding="utf-8").lower()
        for marker in (
            "event_type in ('added','removed')",
            "decision_sequence bigint",
            "foreign key(prior_event_id,auction_cycle_id,pig_id)",
            "unique(auction_cycle_id,pig_id,decision_sequence)",
            "before update or delete",
            "grant select,insert",
        ):
            self.assertIn(marker, sql)
        self.assertNotIn("insert into public.pig_active_outlets", sql)
        self.assertNotIn("insert into public.riversdale_auction_cohort_members", sql)

    def test_writer_uses_one_serializable_locked_cycle_and_causal_projection(self):
        source = Path("modules/sales/riversdale_auction_list.py").read_text()
        self.assertIn("pg_advisory_xact_lock", source)
        self.assertIn("public.pig_weight_events,public.pig_medical_events", source)
        self.assertIn("in share mode", source)
        self.assertIn("limit 1 for update", source)
        self.assertIn("order by pig_id for update", source)
        self.assertNotIn("recorded_at desc,e.auction_list_event_id", source)
        decision_source = Path("modules/sales/riversdale_auction.py").read_text()
        self.assertIn("pg_advisory_xact_lock", decision_source)

    @patch("modules.pig_weights.pig_weights_service.get_riversdale_auction_recommendation")
    @patch("modules.pig_weights.pig_weights_service.read_auction_list")
    def test_unavailable_optional_store_fails_before_readiness_rebuild(
            self, read_list, recommendation):
        read_list.return_value = (
            {"success": False, "status": "auction_list_store_unavailable"}, 503
        )
        result, status = get_riversdale_auction_list()
        self.assertEqual((status, result["status"]),
                         (503, "auction_list_store_unavailable"))
        recommendation.assert_not_called()

    def test_optional_list_is_bounded_and_frontend_renders_candidates_first(self):
        backend = Path("modules/sales/riversdale_auction_list.py").read_text()
        self.assertIn("connect_timeout=3", backend)
        self.assertIn('statement_timeout=3000', backend)
        frontend = Path("static/js/pigAllocation.js").read_text()
        render_at = frontend.index("renderAuctionSurface(data.owner_surface)")
        optional_fetch_at = frontend.index(
            'fetch("/api/pig-weights/riversdale-auction-list")'
        )
        self.assertLess(render_at, optional_fetch_at)
        self.assertIn(
            "Auction List unavailable; candidates remain read-only", frontend
        )


if __name__ == "__main__":
    unittest.main()
