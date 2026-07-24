import unittest
from datetime import datetime, timezone

from modules.sales.sam_meat_launch_readiness import build_sam_meat_launch_packet, production_truth_readers

NOW = datetime(2026, 7, 24, 10, 0, tzinfo=timezone.utc)


def readers(unavailable=(), stale=False, zero=False):
    unavailable = set(unavailable)
    def item(name, data):
        return {"usable": False, "blockers": [name + "_offline"]} if name in unavailable else {"usable": True, "status": "verified_" + name, "freshness": "current", "data": data}
    price = {"product_type": "half_carcass", "cut_set": "Set A", "price_unit": "per_kg", "price_amount": 0 if zero else 130,
             "effective_from": "2026-07-01T00:00:00+00:00", "effective_to": "2026-07-10T00:00:00+00:00" if stale else "2026-08-31T00:00:00+00:00", "status": "active"}
    return {
        "catalogue": lambda **_: item("catalogue", {"products": ["half carcass", "full carcass"], "units": ["kg", "half_carcass", "carcass"], "packs": ["Set A"]}),
        "pricing": lambda **_: item("pricing", {"entries": [price]}),
        "availability": lambda **_: item("availability", {"state": "owner_review_only", "count": 0}),
        "fulfilment": lambda **_: item("fulfilment", {"mode": "delivery", "areas": ["Riversdale"]}),
        "butcher": lambda **_: item("butcher", {"truth_status": "blocked_unknown"}),
    }


def packet(messages, **kwargs):
    return build_sam_meat_launch_packet(messages, conversation_ref="conv-42",
        inbound_event_id=kwargs.pop("inbound_event_id", "msg-latest"),
        truth_readers=kwargs.pop("truth_readers", readers()), now=NOW, **kwargs)


class SamMeatLaunchReadinessTests(unittest.TestCase):
    def test_quantity_unit_and_known_fact_retention(self):
        result = packet([{"message_id": "m1", "content": "I want a half carcass Set A."},
                         {"message_id": "m2", "content": "Make that 2 half carcasses for delivery in Riversdale."}])
        self.assertEqual(result["facts"]["product_type"], "half_carcass")
        self.assertEqual(result["quantity"], {"value": 2, "unit": "half_carcass"})
        self.assertEqual(result["fact_evidence"]["quantity"]["message_id"], "m2")

    def test_explicit_correction_is_traceable(self):
        result = packet([{"message_id": "m1", "content": "I want 1 half carcass Set A."},
                         {"message_id": "m2", "content": "Actually make that 2 half carcasses."}], inbound_event_id="m2")
        correction = next(row for row in result["corrections"] if row["field"] == "quantity")
        self.assertEqual((correction["from"], correction["to"], correction["message_id"]), (1, 2, "m2"))
        self.assertTrue(result["correction_event"]["event_id"])

    def test_unknown_does_not_replace_known(self):
        self.assertEqual(packet(["Half carcass Set A.", "Hello again"])["facts"]["product_type"], "half_carcass")

    def test_address_only_required_for_delivery(self):
        collection = packet(["Half carcass Set A, 1 half carcass, collection next week."])
        delivery = packet(["Half carcass Set A, 1 half carcass, delivery in Riversdale next week."])
        self.assertNotEqual(collection["next_missing_field"], "delivery_address")
        self.assertEqual(delivery["next_missing_field"], "delivery_address")

    def test_question_order_delays_payment(self):
        result = packet(["Half carcass Set A."])
        self.assertEqual(result["next_missing_field"], "quantity")
        self.assertNotIn("EFT", result["next_safe_question"])
        stale = packet(["Half carcass Set A, 1 half carcass, collection next week."], truth_readers=readers(stale=True))
        self.assertEqual(stale["next_missing_field"], "")
        self.assertIn("current_matching_price_rule_required", stale["price_basis"]["blockers"])

    def test_english_afrikaans_and_mixed_localization(self):
        en = packet(["I want a half carcass Set A."])
        af = packet(["Ek wil 'n halwe karkas, Stel A."])
        mixed = packet(["Ek wil 'n halwe karkas, Stel A.", "Okay"])
        self.assertEqual(en["language"], "en"); self.assertIn("How much", en["next_safe_question"])
        self.assertEqual(af["language"], "af"); self.assertIn("Hoeveel", af["next_safe_question"])
        self.assertEqual(mixed["language"], "af"); self.assertIn("Hoeveel", mixed["next_safe_question"])

    def test_yes_alone_is_not_commitment(self):
        self.assertNotIn("commitment", packet(["Half carcass Set A.", "yes"])["facts"])
        self.assertEqual(packet(["Half carcass Set A.", "I want to order it"])["facts"]["commitment"], "explicit_customer_commitment")

    def test_unavailable_stale_and_verified_zero(self):
        offline = packet(["Half carcass Set A."], truth_readers=readers(unavailable={"availability"}))
        self.assertEqual(offline["availability"]["status"], "Unavailable")
        self.assertEqual(offline["availability"]["data"], {})
        self.assertNotIn("no stock", offline["prepared_reply"].lower())
        stale = packet(["Half carcass Set A."], truth_readers=readers(stale=True))
        self.assertFalse(stale["price_basis"]["current"]); self.assertIsNone(stale["price_basis"]["amount"])
        zero = packet(["Half carcass Set A."], truth_readers=readers(zero=True))
        self.assertTrue(zero["price_basis"]["verified_zero"]); self.assertEqual(zero["price_basis"]["amount"], 0)

    def test_injected_authoritative_adapters(self):
        calls = []
        def fake(**kwargs): calls.append(kwargs); return {"usable": False, "blockers": ["test"]}
        result = build_sam_meat_launch_packet(["Half carcass Set A."], conversation_ref="c", inbound_event_id="m",
            lead_id="LEAD-1", truth_readers={name: fake for name in production_truth_readers()}, now=NOW)
        self.assertEqual(len(calls), 5)
        self.assertTrue(all(call["lead_id"] == "LEAD-1" for call in calls))
        self.assertTrue(all(call["facts"]["product_type"] == "half_carcass" for call in calls))
        self.assertEqual(result["truth"]["butcher"]["status"], "Unavailable")

    def test_stable_replay_and_correction_ids(self):
        first = packet([{"message_id": "m1", "content": "Half carcass Set A."}], inbound_event_id="m1")
        replay = packet([{"message_id": "m1", "content": "Half carcass Set A."}], inbound_event_id="m1")
        corrected = packet([{"message_id": "m1", "content": "1 half carcass Set A."},
                            {"message_id": "m2", "content": "Actually 2 half carcasses."}], inbound_event_id="m2")
        self.assertEqual(first["review_event"]["event_id"], replay["review_event"]["event_id"])
        self.assertNotEqual(first["review_event"]["event_id"], corrected["review_event"]["event_id"])
        self.assertNotEqual(corrected["review_event"]["event_id"], corrected["correction_event"]["event_id"])
        self.assertTrue(first["review_event"]["prepared_in_memory"]); self.assertFalse(first["review_event"]["persisted"])

    def test_diagnostics_have_no_sensitive_values(self):
        result = packet(["Deliver to 10 Private Road, Riversdale. Half carcass Set A."])
        self.assertNotIn("10 Private Road", str(result["diagnostics"]))
        self.assertFalse(result["diagnostics"]["contains_sensitive_values"])

    def test_owner_packet_shape_authority_and_connection(self):
        result = packet(["Half carcass Set A, 1 half carcass, delivery in Riversdale next week."])
        for key in ("understood_request", "fact_evidence", "corrections", "next_safe_question", "catalogue_match",
                    "quantity", "price_basis", "availability", "fulfilment", "butcher_loop", "prepared_reply",
                    "protected_decision", "authority"):
            self.assertIn(key, result)
        self.assertFalse(any(result["authority"].values()))
        self.assertFalse(result["connection_state"]["operationally_testable"])

    def test_no_final_price_or_fake_selected_canary(self):
        result = packet(["Half carcass Set A, 2 half carcasses, collection next week, EFT."])
        self.assertEqual(result["final_total"]["status"], "not_calculated")
        self.assertIsNone(result["final_total"]["amount"])
        self.assertFalse(result["canary"]["selected"])
        self.assertEqual(result["canary"]["conversation_id"], "")


if __name__ == "__main__": unittest.main()
