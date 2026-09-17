import unittest

from modules.charlie.operational_events import build_event, replay_events


def event(**overrides):
    packet = {
        "event_type": "order.status_changed",
        "domain": "orders",
        "aggregate_type": "order",
        "aggregate_id": "ORD-1",
        "source_system": "order_service",
        "source_record_id": "ORD-1",
        "authority_tier": "owner_approved",
        "privacy_class": "customer_personal",
        "occurred_at": "2026-07-19T10:00:00+00:00",
        "recorded_at": "2026-07-19T10:01:00+00:00",
        "payload": {"status": "Approved"},
        "provenance": {"source_ref": "orders/ORD-1"},
    }
    packet.update(overrides)
    return packet


class OperationalEventTests(unittest.TestCase):
    def test_authority_privacy_and_provenance_are_mandatory(self):
        for field in ("authority_tier", "privacy_class", "provenance"):
            packet = event()
            packet.pop(field)
            self.assertFalse(build_event(packet)["accepted"], field)

    def test_duplicate_and_late_events_replay_once(self):
        late = event(idempotency_key="order-1-approved")
        result = replay_events([late, dict(late)])
        self.assertEqual(result["applied_count"], 1)
        self.assertEqual(result["state"]["aggregates"]["orders:order:ORD-1"]["status"], "Approved")

    def test_replay_is_deterministic_for_out_of_order_input(self):
        approved = event(idempotency_key="approved")
        paid = event(
            idempotency_key="paid",
            event_type="order.payment_recorded",
            occurred_at="2026-07-19T11:00:00+00:00",
            payload={"payment_status": "Paid"},
        )
        forward = replay_events([approved, paid])
        reverse = replay_events([paid, approved])
        self.assertEqual(forward["state"], reverse["state"])
        self.assertEqual(forward["event_ids"], reverse["event_ids"])

    def test_partial_invalid_event_is_rejected_without_stopping_replay(self):
        result = replay_events([{"domain": "orders"}, event()])
        self.assertEqual(result["applied_count"], 1)
        self.assertEqual(len(result["rejected"]), 1)


if __name__ == "__main__":
    unittest.main()
