import unittest
from unittest.mock import patch

from app import app
from modules.sales import sales_transaction_routes as routes


class SamLiveStockAvailabilityRoutesTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()

    def test_preview_is_owner_read_only_and_never_exposes_lineage(self):
        preview = {
            "success": True,
            "status": "availability_observation_preview_ready",
            "eligible_totals": {},
            "_lineage": [{"animal_key_hash": "private-internal"}],
            "sends_customer_message": False,
            "mutates_business_state": False,
        }
        with patch.object(routes, "require_owner_read_access", return_value=None), patch.object(
            routes, "get_sales_availability", return_value=[]
        ), patch.object(
            routes, "build_availability_observation_preview", return_value=preview
        ):
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/availability/preview",
                json={"observed_at": "2026-07-27T10:00:00+02:00"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_lineage", response.get_json())

    def test_confirmation_uses_server_derived_owner_only(self):
        recorded = {
            "success": True,
            "status": "availability_observation_recorded",
            "sends_customer_message": False,
            "mutates_business_state": False,
        }
        with patch.object(routes, "require_owner_admin_access", return_value=None), patch.object(
            routes, "owner_admin_principal", return_value="owner-admin:server"
        ), patch.object(routes, "get_sales_availability", return_value=[]), patch.object(
            routes, "append_availability_observation", return_value=(recorded, 201)
        ) as append:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/availability/confirm",
                json={"actor_id": "browser-spoof", "owner_confirmed": True},
            )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.get_json()["sends_customer_message"])
        self.assertEqual(append.call_args.kwargs["actor_id"], "owner-admin:server")

    def test_recommendation_requires_exact_account_conversation_contact_inbox(self):
        identity = {
            "success": True,
            "account_id": "1",
            "conversation_id": "67",
            "contact_id": "704639709",
            "inbox_id": "96568",
        }
        with patch.object(routes, "require_owner_read_access", return_value=None), patch.object(
            routes, "load_chatwoot_conversation_identity", return_value=identity
        ), patch.object(routes, "load_chatwoot_conversation_history") as history:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/availability/recommendation",
                json={
                    "observation_event_id": "event",
                    "cohort_hash": "a" * 64,
                    "observed_at_utc": "2026-07-27T10:00:00Z",
                    "expires_at_utc": "2026-07-28T10:00:00Z",
                    "account_id": "wrong",
                    "conversation_id": "67",
                    "contact_id": "704639709",
                    "inbox_id": "96568",
                    "latest_inbound_id": "761948125",
                },
            )
        self.assertEqual(response.status_code, 409)
        history.assert_not_called()

    def test_recommendation_rejects_private_and_stale_latest_inbound(self):
        identity = {
            "success": True,
            "account_id": "1",
            "conversation_id": "67",
            "contact_id": "704639709",
            "inbox_id": "96568",
        }
        history = {
            "success": True,
            "messages": [
                {"id": "761948125", "message_type": 0, "private": True, "content": "hidden"},
                {"id": "761948126", "message_type": 0, "private": False, "content": "current"},
            ],
        }
        with patch.object(routes, "require_owner_read_access", return_value=None), patch.object(
            routes, "load_chatwoot_conversation_identity", return_value=identity
        ), patch.object(routes, "load_chatwoot_conversation_history", return_value=history), patch.object(
            routes, "get_sales_availability"
        ) as availability:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/availability/recommendation",
                json={
                    "observation_event_id": "event",
                    "cohort_hash": "a" * 64,
                    "observed_at_utc": "2026-07-27T10:00:00Z",
                    "expires_at_utc": "2026-07-28T10:00:00Z",
                    "account_id": "1",
                    "conversation_id": "67",
                    "contact_id": "704639709",
                    "inbox_id": "96568",
                    "latest_inbound_id": "761948125",
                },
            )
        self.assertEqual(response.status_code, 409)
        availability.assert_not_called()

    def test_recommendation_requires_confirmed_observation_binding(self):
        with patch.object(routes, "require_owner_read_access", return_value=None), patch.object(
            routes, "load_chatwoot_conversation_identity"
        ) as identity:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/availability/recommendation",
                json={"conversation_id": "67"},
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.get_json()["status"],
            "recommendation_observation_binding_required",
        )
        identity.assert_not_called()

    def test_recommendation_binds_exact_confirmed_observation(self):
        identity = {
            "success": True, "account_id": "1", "conversation_id": "67",
            "contact_id": "704639709", "inbox_id": "96568",
        }
        history = {"success": True, "messages": [
            {"id": "761948125", "message_type": 0, "private": False,
             "content": "Soggies to bay 10"},
        ]}
        packet = {
            "status": "commercial_recommendation_ready",
            "interpretation": {}, "recommendation": "Owner draft",
            "next_action": "owner_review",
            "herdmaster_aggregate": {"evidence_complete": True},
        }
        payload = {
            "account_id": "1", "conversation_id": "67",
            "contact_id": "704639709", "inbox_id": "96568",
            "latest_inbound_id": "761948125",
            "observation_event_id": "SAM-LIVE-STOCK-AVAIL-ONE",
            "cohort_hash": "a" * 64,
            "observed_at_utc": "2026-07-27T10:00:00Z",
            "expires_at_utc": "2026-07-28T10:00:00Z",
        }
        with patch.object(routes, "require_owner_read_access", return_value=None), patch.object(
            routes, "load_chatwoot_conversation_identity", return_value=identity
        ), patch.object(routes, "load_chatwoot_conversation_history", return_value=history), patch.object(
            routes, "get_sales_availability", return_value=[]
        ), patch.object(routes, "summarize_live_stock_availability", return_value={}), patch.object(
            routes, "resolve_authoritative_availability", return_value={
                "cohort_observation_event_id": payload["observation_event_id"],
                "cohort_expires_at_utc": payload["expires_at_utc"],
            }
        ) as resolve, patch.object(
            routes, "build_contextual_sales_recommendation", return_value=packet
        ):
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-live-stock/availability/recommendation",
                json=payload,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            resolve.call_args.kwargs,
            {
                "expected_observation_event_id": payload["observation_event_id"],
                "expected_cohort_hash": payload["cohort_hash"],
                "expected_observed_at": payload["observed_at_utc"],
                "expected_expires_at": payload["expires_at_utc"],
            },
        )


if __name__ == "__main__":
    unittest.main()
