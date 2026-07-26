import json
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from app import app as production_app
from modules.auth.owner_access import configure_owner_access
from modules.pig_weights.pig_weights_routes import pig_weights_bp
from modules.sales.riversdale_auction import (
    build_riversdale_auction_packet,
    record_owner_auction_decision,
    sanitized_owner_surface,
)

READ_TOKEN = "read-owner-token-1234567890abcdef"
ADMIN_TOKEN = "admin-owner-token-1234567890abcdef"
SESSION_SECRET = "owner-session-secret-1234567890abcdef"


def owner_env():
    return {
        "OWNER_ACCESS_ENABLED": "1",
        "OWNER_ACCESS_ALLOW_LOCAL_DEV": "0",
        "OWNER_READ_TOKEN": READ_TOKEN,
        "OWNER_ADMIN_TOKEN": ADMIN_TOKEN,
        "OWNER_SESSION_SECRET": SESSION_SECRET,
    }


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


class _DecisionStoreCursor:
    def __init__(self):
        self.calls = []
        self.rows = {}
        self._result = None

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        normalized = " ".join(sql.split()).lower()
        if normalized.startswith("insert into public.riversdale_auction_cycles"):
            key = params[12]
            if key not in self.rows:
                self.rows[key] = {
                    "cycle_id": params[0],
                    "actor_id": params[4],
                    "confirmed_date": params[1],
                    "decision_status": params[3],
                    "decision_hash": params[13],
                    "evidence": params,
                }
                self._result = (params[0],)
            else:
                self._result = None
        elif "where idempotency_key=%s" in normalized:
            row = self.rows.get(params[0])
            self._result = (row["cycle_id"], row["decision_hash"]) if row else None

    def fetchone(self):
        result, self._result = self._result, None
        return result

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
        insert_call = next(call for call in cursor.calls if "insert into public.riversdale_auction_cycles" in call[0])
        self.assertIn("on conflict (idempotency_key) do nothing", insert_call[0])
        self.assertIn("pg_advisory_xact_lock", cursor.calls[0][0])

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

    @patch("modules.pig_weights.pig_weights_routes.owner_admin_principal", return_value="owner-admin:stable")
    @patch("modules.pig_weights.pig_weights_routes.require_owner_admin_access", return_value=None)
    @patch("modules.pig_weights.pig_weights_routes.update_riversdale_auction_list_data")
    def test_auction_list_uses_server_principal_and_ignores_browser_identity(
            self, update, _access, _principal):
        update.return_value = ({"success": True, "status": "auction_list_updated"}, 201)
        response = self.client.post(
            "/api/pig-weights/riversdale-auction-list/events",
            json={
                "action": "add", "pig_ids": ["PIG-1"],
                "auction_cycle_id": "cycle-a",
                "eligibility_tokens": {"PIG-1": "token"},
                "prior_event_ids": {"PIG-1": ""},
                "idempotency_key": "request-a",
                "owner_id": "browser-spoof",
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(update.call_args.kwargs["actor_id"], "owner-admin:stable")
        self.assertNotEqual(update.call_args.kwargs["actor_id"], "browser-spoof")

    def test_existing_page_has_one_panel_and_integrated_auction_table(self):
        html = Path("templates/pig-allocation.html").read_text(encoding="utf-8")
        js = Path("static/js/pigAllocation.js").read_text(encoding="utf-8")
        self.assertEqual(html.count('id="riversdale_auction_panel"'), 1)
        self.assertIn("/api/pig-weights/riversdale-auction-recommendation", js)
        self.assertIn("/api/pig-weights/riversdale-auction-confirmation", js)
        self.assertIn("/api/pig-weights/riversdale-auction-list", js)
        self.assertNotIn('id="riversdale_candidate_review"', html)
        self.assertIn("Fees beyond the confirmed 7% commission", html)
        self.assertIn("R200 remains an estimate", html)
        self.assertIn("data.owner_surface", js)
        self.assertIn("data.candidate_preview", js)
        self.assertNotIn("data.cohort", js)


class RiversdaleAuctionOwnerPrincipalAcceptanceTests(unittest.TestCase):
    def setUp(self):
        production_app.testing = True
        production_app.config.update(SERVER_NAME=None)
        self.client = production_app.test_client()

    def _configure(self):
        configure_owner_access(production_app)

    def _login(self, token):
        return self.client.post(
            "/owner/login",
            data={"owner_token": token, "next": "/pig-allocation"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )

    def _route_adapter(self, cursor):
        def record(payload, *, actor_id):
            return record_owner_auction_decision(
                payload,
                actor_id=actor_id,
                database_url="postgresql://test",
                connect_factory=lambda _url: _Connection(cursor),
            )
        return record

    def test_authenticated_admin_records_exact_decision_with_stable_server_principal(self):
        cursor = _DecisionStoreCursor()
        payload = {
            "operating": True,
            "confirmed_date": "2026-08-05",
            "location": "Riversdale",
            "owner_note": "Exact owner evidence",
            "idempotency_key": "auction-admin-exact",
            "owner_identity": "owner-admin:spoofed-browser-value",
            "owner_id": "spoofed-owner",
            "username": "spoofed-name",
        }
        with patch.dict(os.environ, owner_env(), clear=False):
            self._configure()
            self.assertEqual(self._login(ADMIN_TOKEN).status_code, 302)
            with self.client.session_transaction() as owner_session:
                expected_principal = owner_session["owner_access"]["principal_id"]
            with patch(
                "modules.pig_weights.pig_weights_routes.record_riversdale_auction_decision_data",
                side_effect=self._route_adapter(cursor),
            ):
                response = self.client.post(
                    "/api/pig-weights/riversdale-auction-confirmation",
                    json=payload,
                    environ_base={"REMOTE_ADDR": "203.0.113.10"},
                )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(cursor.rows), 1)
        stored = cursor.rows["auction-admin-exact"]
        self.assertEqual(stored["actor_id"], expected_principal)
        self.assertTrue(expected_principal.startswith("owner-admin:"))
        self.assertNotIn(ADMIN_TOKEN, expected_principal)
        self.assertNotIn("spoofed", json.dumps(stored["evidence"], default=str))
        insert_sql = next(
            call[0] for call in cursor.calls
            if "insert into public.riversdale_auction_cycles" in call[0]
        )
        self.assertIn("owner_confirmed_at", insert_sql)
        self.assertIn("now()", insert_sql)
        self.assertEqual(stored["decision_status"], "confirmed_operating")
        self.assertEqual(stored["confirmed_date"].isoformat(), "2026-08-05")
        self.assertEqual(len(stored["decision_hash"]), 64)

    def test_owner_read_and_anonymous_cannot_persist(self):
        for token in (None, READ_TOKEN):
            with self.subTest(token="anonymous" if token is None else "owner-read"):
                with patch.dict(os.environ, owner_env(), clear=False):
                    self._configure()
                    if token:
                        self.assertEqual(self._login(token).status_code, 302)
                    with patch(
                        "modules.pig_weights.pig_weights_routes.record_riversdale_auction_decision_data"
                    ) as record:
                        response = self.client.post(
                            "/api/pig-weights/riversdale-auction-confirmation",
                            json={"operating": False, "idempotency_key": "denied"},
                            environ_base={"REMOTE_ADDR": "203.0.113.10"},
                        )
                self.assertEqual(response.status_code, 403)
                record.assert_not_called()

    def test_arbitrary_or_missing_admin_principal_fails_before_persistence(self):
        incompatible_sessions = (
            {"role": "admin", "principal_id": "owner-admin:manually-injected"},
            {"role": "admin"},
            {"role": "admin", "principal_id": "owner-read:incompatible"},
        )
        for session_data in incompatible_sessions:
            with self.subTest(session_data=session_data):
                with patch.dict(os.environ, owner_env(), clear=False):
                    self._configure()
                    with self.client.session_transaction() as owner_session:
                        owner_session["owner_access"] = session_data
                    with patch(
                        "modules.pig_weights.pig_weights_routes.record_riversdale_auction_decision_data"
                    ) as record:
                        response = self.client.post(
                            "/api/pig-weights/riversdale-auction-confirmation",
                            json={"operating": False, "idempotency_key": "must-not-write"},
                            environ_base={"REMOTE_ADDR": "203.0.113.10"},
                        )
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.get_json()["status"], "owner_identity_required")
                record.assert_not_called()

    def test_replay_conflict_and_immutable_evidence_preserve_no_authority(self):
        cursor = _DecisionStoreCursor()
        connection = lambda _url: _Connection(cursor)
        exact = {
            "operating": False,
            "location": "Riversdale",
            "owner_note": "Immutable evidence",
            "idempotency_key": "auction-replay",
        }
        first, first_status = record_owner_auction_decision(
            exact, actor_id="owner-admin:stable", database_url="postgresql://test",
            connect_factory=connection,
        )
        replay, replay_status = record_owner_auction_decision(
            exact, actor_id="owner-admin:stable", database_url="postgresql://test",
            connect_factory=connection,
        )
        conflict, conflict_status = record_owner_auction_decision(
            {**exact, "owner_note": "Changed evidence"},
            actor_id="owner-admin:stable", database_url="postgresql://test",
            connect_factory=connection,
        )
        self.assertEqual((first_status, first["status"]), (201, "auction_decision_recorded"))
        self.assertEqual((replay_status, replay["status"]), (200, "auction_decision_replayed"))
        self.assertEqual(
            (conflict_status, conflict["status"]),
            (409, "auction_decision_idempotency_conflict"),
        )
        self.assertEqual(len(cursor.rows), 1)
        stored = cursor.rows["auction-replay"]
        self.assertEqual(stored["actor_id"], "owner-admin:stable")
        self.assertEqual(stored["evidence"][11], "Immutable evidence")
        for result in (first, replay, conflict):
            for key in (
                "creates_cohort", "creates_outlet_claim", "changes_pig_lifecycle",
                "changes_pig_purpose", "creates_order", "creates_reservation",
                "creates_sale", "books_auction", "contacts_customer_or_organizer",
                "sends_reminder",
            ):
                self.assertFalse(result[key])


if __name__ == "__main__":
    unittest.main()
