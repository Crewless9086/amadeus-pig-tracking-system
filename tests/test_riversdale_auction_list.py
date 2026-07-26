import unittest
from pathlib import Path

from modules.sales.riversdale_auction_list import (
    eligibility_tokens, record_auction_list_events,
)


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


if __name__ == "__main__":
    unittest.main()
