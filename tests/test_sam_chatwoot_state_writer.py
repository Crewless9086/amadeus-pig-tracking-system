import unittest

from modules.sales.sam_chatwoot_state_writer import (
    apply_delivery_state,
    apply_new_inbound_state,
)
from modules.sales import sam_chatwoot_state_writer


class SamChatwootStateWriterTests(unittest.TestCase):
    def test_state_write_timeout_is_proportionally_bounded(self):
        self.assertEqual(
            sam_chatwoot_state_writer._bounded_timeout(
                None, default=5.0, minimum=1.0, maximum=10.0
            ),
            5.0,
        )
        self.assertEqual(
            sam_chatwoot_state_writer._bounded_timeout(
                30, default=5.0, minimum=1.0, maximum=10.0
            ),
            10.0,
        )

    def inbound(self):
        return {
            "account_id": "147387",
            "inbox_id": "96568",
            "conversation_id": "2100",
            "contact_id": "987405668",
            "message_id": "766412831",
        }

    def decision(self):
        return {
            "sales_lane": "live_stock_sales",
            "specialist_lane_selected": True,
            "missing_fields": ["location"],
        }

    def chronology(self, inbound_id="766412831"):
        return {
            "messages": [
                {
                    "id": inbound_id,
                    "created_at": 100,
                    "message_type": 0,
                    "private": False,
                }
            ]
        }

    def test_confirmed_delivery_replaces_only_sam_labels_and_marks_seen(self):
        writes = []
        result = apply_delivery_state(
            self.inbound(),
            self.decision(),
            "provider_delivered",
            authoritative_latest_inbound_id="766412831",
            chronology_loader=lambda _cid: self.chronology(),
            conversation_loader=lambda _cid: {
                "labels": ["vip", "new_customer_inbound"]
            },
            label_writer=lambda cid, labels: (
                writes.append(("labels", cid, labels))
                or {"success": True}
            ),
            last_seen_writer=lambda cid: (
                writes.append(("seen", cid)) or {"success": True}
            ),
        )
        self.assertTrue(result["applied"])
        self.assertEqual(
            result["labels_after"],
            ["awaiting_customer", "qualification_in_progress", "vip"],
        )
        self.assertEqual(writes[-1], ("seen", "2100"))

    def test_ambiguous_delivery_labels_quarantine_without_seen(self):
        writes = []
        result = apply_delivery_state(
            self.inbound(),
            self.decision(),
            "provider_outcome_ambiguous",
            authoritative_latest_inbound_id="766412831",
            chronology_loader=lambda _cid: self.chronology(),
            conversation_loader=lambda _cid: {"labels": ["vip"]},
            label_writer=lambda cid, labels: (
                writes.append(("labels", cid, labels))
                or {"success": True}
            ),
            last_seen_writer=lambda cid: (
                writes.append(("seen", cid)) or {"success": True}
            ),
        )
        self.assertTrue(result["applied"])
        self.assertFalse(result["last_seen_applied"])
        self.assertNotIn(("seen", "2100"), writes)
        self.assertIn(
            "delivery_quarantined_do_not_retry", result["labels_after"]
        )

    def test_new_inbound_before_label_write_aborts_all_mutation(self):
        writes = []
        result = apply_delivery_state(
            self.inbound(),
            self.decision(),
            "provider_delivered",
            authoritative_latest_inbound_id="766412831",
            conversation_loader=lambda _cid: {"labels": ["vip"]},
            chronology_loader=lambda _cid: self.chronology("766500000"),
            label_writer=lambda cid, labels: (
                writes.append(("labels", cid, labels))
                or {"success": True}
            ),
            last_seen_writer=lambda cid: (
                writes.append(("seen", cid)) or {"success": True}
            ),
        )
        self.assertFalse(result["applied"])
        self.assertEqual(result["status"], "chronology_changed_before_label_write")
        self.assertEqual(writes, [])

    def test_new_inbound_after_label_write_never_marks_seen(self):
        writes = []
        chronologies = iter(
            [self.chronology(), self.chronology("766500000")]
        )
        result = apply_delivery_state(
            self.inbound(),
            self.decision(),
            "provider_delivered",
            authoritative_latest_inbound_id="766412831",
            conversation_loader=lambda _cid: {"labels": ["vip"]},
            chronology_loader=lambda _cid: next(chronologies),
            label_writer=lambda cid, labels: (
                writes.append(("labels", cid, labels))
                or {"success": True}
            ),
            last_seen_writer=lambda cid: (
                writes.append(("seen", cid)) or {"success": True}
            ),
        )
        self.assertFalse(result["applied"])
        self.assertEqual(result["status"], "chronology_changed_before_last_seen")
        self.assertTrue(any(row[0] == "labels" for row in writes))
        self.assertFalse(any(row[0] == "seen" for row in writes))

    def test_raw_chatwoot_payload_shape_is_rechecked_before_both_writes(self):
        writes = []
        raw = {"payload": self.chronology()["messages"]}
        result = apply_delivery_state(
            self.inbound(),
            self.decision(),
            "provider_delivered",
            authoritative_latest_inbound_id="766412831",
            conversation_loader=lambda _cid: {"labels": ["vip"]},
            chronology_loader=lambda _cid: raw,
            label_writer=lambda cid, labels: (
                writes.append(("labels", cid, labels))
                or {"success": True}
            ),
            last_seen_writer=lambda cid: (
                writes.append(("seen", cid)) or {"success": True}
            ),
        )
        self.assertTrue(result["applied"])
        self.assertEqual(
            [row[0] for row in writes], ["labels", "seen"]
        )

    def test_new_inbound_reactivates_exact_conversation_without_seen(self):
        writes = []
        result = apply_new_inbound_state(
            self.inbound(),
            conversation_loader=lambda _cid: {
                "labels": ["vip", "awaiting_customer"]
            },
            label_writer=lambda cid, labels: (
                writes.append((cid, labels)) or {"success": True}
            ),
        )
        self.assertTrue(result["applied"])
        self.assertEqual(writes, [("2100", ["new_customer_inbound", "vip"])])


if __name__ == "__main__":
    unittest.main()
