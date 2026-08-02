import unittest
from datetime import datetime, timedelta, timezone

from modules.sales.sam_live_stock_level1_control import (
    build_level1_control_event,
    resolve_level1_runtime_control,
)
from modules.sales import sam_live_stock_runtime


NOW = datetime(2026, 7, 28, 20, 0, tzinfo=timezone.utc)


def inbound(**overrides):
    row = {
        "account_id": "147387",
        "inbox_id": "96568",
        "conversation_id": "2100",
        "contact_id": "CONTACT-2100",
        "message_id": "INBOUND-2100",
        "latest_observed_at": (NOW + timedelta(seconds=1)).isoformat(),
    }
    row.update(overrides)
    return row


class SamLiveStockLevel1ControlTests(unittest.TestCase):
    def event(self, state="enabled", **overrides):
        return build_level1_control_event(
            state,
            actor_id="owner-admin:stable-principal",
            reason="owner standing Livestock Level 1 authority",
            now=NOW,
            **overrides,
        )

    def test_new_exact_inbound_is_authorized_without_shared_environment(self):
        event = self.event(intake_write_authorized=True)
        result = resolve_level1_runtime_control(
            inbound(),
            loaded={"status": "level1_control_loaded", "event": event},
            now=NOW + timedelta(minutes=1),
        )
        self.assertTrue(result["allowed"])
        self.assertTrue(result["new_event"])
        self.assertFalse(result["carried_followup"])
        self.assertFalse(result["automatic_retry_authorized"])
        self.assertFalse(result["protected_actions_authorized"])
        self.assertTrue(result["intake_write_authorized"])

    def test_historical_inbound_requires_exact_carried_binding(self):
        old = inbound(
            latest_observed_at=(NOW - timedelta(minutes=1)).isoformat()
        )
        withheld = resolve_level1_runtime_control(
            old,
            loaded={"status": "level1_control_loaded", "event": self.event()},
            now=NOW + timedelta(minutes=1),
        )
        self.assertFalse(withheld["allowed"])
        self.assertIn("historical_event_not_authorized", withheld["blockers"])

        carried_event = self.event(carried_bindings=[{
            "conversation_id": "2100",
            "inbound_message_id": "INBOUND-2100",
        }])
        carried = resolve_level1_runtime_control(
            old,
            loaded={
                "status": "level1_control_loaded",
                "event": carried_event,
            },
            now=NOW + timedelta(minutes=1),
        )
        self.assertTrue(carried["allowed"])
        self.assertTrue(carried["carried_followup"])

    def test_provider_current_backlog_requires_an_enabled_current_control(self):
        old = inbound(
            latest_observed_at=(NOW - timedelta(minutes=1)).isoformat()
        )
        admitted = resolve_level1_runtime_control(
            old,
            loaded={
                "status": "level1_control_loaded",
                "event": self.event(),
            },
            now=NOW + timedelta(minutes=1),
            allow_provider_current_backlog=True,
        )
        self.assertTrue(admitted["allowed"])
        self.assertTrue(admitted["provider_current_backlog"])
        self.assertFalse(admitted["new_event"])
        self.assertFalse(admitted["carried_followup"])

        killed = resolve_level1_runtime_control(
            old,
            loaded={
                "status": "level1_control_loaded",
                "event": self.event("killed"),
            },
            now=NOW + timedelta(minutes=1),
            allow_provider_current_backlog=True,
        )
        self.assertFalse(killed["allowed"])
        self.assertFalse(killed["provider_current_backlog"])
        self.assertIn(
            "kill_switch_or_control_disabled", killed["blockers"]
        )

    def test_kill_disabled_expired_or_missing_storage_fails_closed(self):
        cases = (
            (
                {"status": "level1_control_loaded", "event": self.event("killed")},
                "kill_switch_or_control_disabled",
            ),
            (
                {"status": "level1_control_loaded", "event": self.event("disabled")},
                "kill_switch_or_control_disabled",
            ),
            (
                {"status": "level1_control_loaded", "event": self.event()},
                "control_not_current",
            ),
            (
                {"status": "level1_control_storage_unavailable", "event": {}},
                "isolated_control_unavailable",
            ),
        )
        for index, (loaded, blocker) in enumerate(cases):
            with self.subTest(index=index):
                at = (
                    NOW + timedelta(days=31)
                    if index == 2
                    else NOW + timedelta(minutes=1)
                )
                result = resolve_level1_runtime_control(
                    inbound(), loaded=loaded, now=at
                )
                self.assertFalse(result["allowed"])
                self.assertIn(blocker, result["blockers"])
                self.assertFalse(result["legacy_fallback_permitted"])

    def test_identity_time_and_policy_mismatch_fail_closed(self):
        event = self.event()
        cases = (
            inbound(contact_id=""),
            inbound(latest_observed_at="not-a-time"),
            inbound(latest_observed_at="2026-07-28T20:01:00"),
        )
        for row in cases:
            with self.subTest(row=row):
                result = resolve_level1_runtime_control(
                    row,
                    loaded={"status": "level1_control_loaded", "event": event},
                    now=NOW + timedelta(minutes=1),
                )
                self.assertFalse(result["allowed"])

        bad_policy = {**event, "policy_version": "unexpected"}
        result = resolve_level1_runtime_control(
            inbound(),
            loaded={
                "status": "level1_control_loaded",
                "event": bad_policy,
            },
            now=NOW + timedelta(minutes=1),
        )
        self.assertFalse(result["allowed"])
        self.assertIn("policy_version_mismatch", result["blockers"])

    def test_control_event_is_replay_stable_and_bounded(self):
        first = self.event()
        replay = self.event()
        self.assertEqual(first, replay)
        self.assertFalse(first["contains_customer_content"])
        self.assertFalse(first["sends_customer_message"])
        self.assertFalse(first["mutates_business_state"])
        with self.assertRaisesRegex(ValueError, "server_derived"):
            build_level1_control_event(
                "enabled",
                actor_id="browser-supplied",
                reason="invalid",
                now=NOW,
            )
        with self.assertRaisesRegex(ValueError, "exceed_bound"):
            self.event(carried_bindings=[
                {
                    "conversation_id": str(index),
                    "inbound_message_id": str(index),
                }
                for index in range(26)
            ])

    def test_isolated_control_allows_intake_but_no_protected_write(self):
        writes = []
        result = sam_live_stock_runtime.write_live_stock_intake_if_enabled(
            {
                "conversation_id": "2100",
                "customer_name": "Customer",
                "content": "I need pigs",
            },
            {
                "customer_name": "Customer",
                "quantity": 2,
                "category": "piglet",
                "sex": "female",
            },
            {
                "sales_lane": "live_stock_sales",
                "next_action": "ask_one_missing_detail",
                "blockers": [],
            },
            {},
            intake_writer=lambda payload: (
                writes.append(payload) or {"success": True}
            ),
            isolated_runtime={
                "allowed": True,
                "control_event_id": "SAM-L1-CONTROL-1",
                "intake_write_authorized": True,
            },
        )
        self.assertTrue(result["success"])
        self.assertEqual(len(writes), 1)
        self.assertNotIn("order_id", result["payload"])
        self.assertNotIn("reservation_id", result["payload"])
        self.assertNotIn("stock_write", result["payload"])

        withheld = sam_live_stock_runtime.write_live_stock_intake_if_enabled(
            {"conversation_id": "2100", "content": "I need pigs"},
            {"quantity": 2, "category": "piglet", "sex": "female"},
            {"sales_lane": "live_stock_sales", "blockers": []},
            {},
            intake_writer=lambda payload: writes.append(payload),
            isolated_runtime={
                "allowed": True,
                "control_event_id": "SAM-L1-CONTROL-1",
                "intake_write_authorized": False,
            },
        )
        self.assertFalse(withheld["attempted"])
        self.assertEqual(len(writes), 1)

    def test_legacy_business_write_env_cannot_spill_into_isolated_level1(self):
        intake_writes = []
        intake = sam_live_stock_runtime.write_live_stock_intake_if_enabled(
            {"conversation_id": "2100", "content": "I need pigs"},
            {"quantity": 2, "category": "piglet", "sex": "female"},
            {"sales_lane": "live_stock_sales", "blockers": []},
            {
                sam_live_stock_runtime.INTAKE_WRITE_ENABLED_ENV: "true",
            },
            intake_writer=lambda payload: intake_writes.append(payload),
            isolated_runtime={
                "allowed": True,
                "control_event_id": "SAM-L1-CONTROL-1",
                "intake_write_authorized": False,
            },
        )
        self.assertFalse(intake["attempted"])
        self.assertEqual(intake_writes, [])

        order_creates = []
        draft = sam_live_stock_runtime.create_live_stock_draft_order_if_enabled(
            {"conversation_id": "2100"},
            {"quantity": 2, "category": "piglet", "sex": "female"},
            {
                "sales_lane": "live_stock_sales",
                "draft_order_packet": {"draft_ready": True},
            },
            {
                sam_live_stock_runtime.DRAFT_ORDER_CREATE_ENABLED_ENV: "true",
            },
            draft_order_creator=lambda payload: order_creates.append(payload),
            isolated_runtime={
                "allowed": True,
                "control_event_id": "SAM-L1-CONTROL-1",
                "intake_write_authorized": True,
            },
        )
        self.assertFalse(draft["attempted"])
        self.assertEqual(
            draft["status"],
            "sam_live_stock_draft_order_isolated_level1_prohibited",
        )
        self.assertEqual(order_creates, [])

    def test_legacy_business_write_requires_proven_not_configured_state(self):
        source = {
            sam_live_stock_runtime.INTAKE_WRITE_ENABLED_ENV: "true",
            sam_live_stock_runtime.DRAFT_ORDER_CREATE_ENABLED_ENV: "true",
        }
        intake_writes = []
        base_args = (
            {"conversation_id": "2100", "content": "I need pigs"},
            {"quantity": 2, "category": "piglet", "sex": "female"},
            {"sales_lane": "live_stock_sales", "blockers": []},
        )
        unavailable = {
            "allowed": False,
            "control_event_id": "",
            "legacy_fallback_permitted": False,
        }
        intake = sam_live_stock_runtime.write_live_stock_intake_if_enabled(
            *base_args,
            source,
            intake_writer=lambda payload: intake_writes.append(payload),
            isolated_runtime=unavailable,
        )
        draft = sam_live_stock_runtime.create_live_stock_draft_order_if_enabled(
            *base_args,
            source,
            draft_order_creator=lambda payload: None,
            isolated_runtime=unavailable,
        )
        self.assertFalse(intake["attempted"])
        self.assertFalse(draft["attempted"])
        self.assertEqual(intake_writes, [])

        no_event = {
            "allowed": False,
            "control_event_id": "",
            "legacy_fallback_permitted": True,
        }
        legacy_intake = sam_live_stock_runtime.write_live_stock_intake_if_enabled(
            *base_args,
            source,
            intake_writer=lambda payload: {"success": True},
            isolated_runtime=no_event,
        )
        self.assertTrue(legacy_intake["attempted"])


if __name__ == "__main__":
    unittest.main()
