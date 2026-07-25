import json
import unittest
from datetime import date

from modules.pig_weights.herdmaster_daily_brief_service import (
    build_herdmaster_daily_brief,
    format_weight_band_label,
)


TODAY = date(2026, 7, 25)
CONTRACT = "herdmaster_exact_animal_eligibility_v1"


def allocation_row(**overrides):
    row = {
        "pig_id": "PRIVATE-PIG-1",
        "tag_number": "PRIVATE-TAG-1",
        "status": "Active",
        "on_farm": "Yes",
        "sex": "Female",
        "purpose": "Sale",
        "calculated_stage": "Grower",
        "readiness_bucket": "Livestock Candidate",
        "latest_weight_kg": 42,
        "latest_weight_date": "2026-07-24",
        "days_since_weight": 1,
        "growth_class": "Normal",
        "withdrawal_evidence_state": "not_applicable",
        "medical_status": "Clear",
        "health_status": "Clear",
        "allocation_query_status": "known",
        "allocation_evidence_state": "known_unallocated",
        "reserved_status": "Not_Reserved",
        "current_pen_id": "PRIVATE-PEN-1",
    }
    row.update(overrides)
    return row


def sales_row(**overrides):
    row = {
        "pig_id": "PRIVATE-PIG-1",
        "tag_number": "PRIVATE-TAG-1",
        "source": "supabase_allocation_readiness",
        "eligibility_observed_at": "2026-07-25",
        "status": "Active",
        "on_farm": "Yes",
        "sex": "Male",
        "purpose": "Sale",
        "calculated_stage": "Grower",
        "sale_category": "Grower Pigs",
        "current_weight_kg": 28,
        "latest_weight_date": "2026-07-24",
        "days_since_weight": 1,
        "weight_band": "25_to_29_Kg",
        "withdrawal_evidence_state": "not_applicable",
        "medical_status": "Clear",
        "allocation_query_status": "known",
        "allocation_evidence_state": "known_unallocated",
        "reserved_status": "Not_Reserved",
        "exact_animal_eligibility_contract_version": CONTRACT,
        "evidence_complete": True,
        "live_stock_sale_eligible": True,
        "live_stock_sale_reason": "eligible",
    }
    row.update(overrides)
    return row


def complete_envelopes():
    allocation = {
        "success": True,
        "source": "supabase_canonical",
        "generated_date": "2026-07-25",
        "allocation_query_status": "known",
        "thresholds": {"stale_weight_days": 30},
        "pigs": [
            allocation_row(),
            allocation_row(
                pig_id="PRIVATE-PIG-2",
                tag_number="PRIVATE-TAG-2",
                sex="Male",
                purpose="Breeding",
                calculated_stage="Boar",
                latest_weight_kg=85,
                growth_class="Slow",
            ),
            allocation_row(
                pig_id="PRIVATE-PIG-3",
                tag_number="PRIVATE-TAG-3",
                status="Sold",
                on_farm="No",
                purpose="Grow_Out",
                calculated_stage="Finisher",
            ),
        ],
    }
    sales = {
        "count": 2,
        "allocation_query_status": "known",
        "generated_date": "2026-07-25",
        "pigs": [
            sales_row(),
            sales_row(
                pig_id="PRIVATE-PIG-X",
                tag_number="PRIVATE-TAG-X",
                sex="Female",
                current_weight_kg=62,
                weight_band="60_to_64_Kg",
                sale_category="Finisher Pigs",
            ),
        ],
    }
    litters = {
        "success": True,
        "count": 1,
        "source": {"reads_from": "supabase_canonical"},
        "litters": [{
            "litter_id": "PRIVATE-LITTER-1",
            "litter_status": "Active",
            "days_until_estimated_wean": 4,
            "reconciliation": {"mismatch": False},
            "lifecycle_outcomes": {"dead": 2, "sold": 1},
        }],
    }
    breeding = {
        "success": True,
        "mode": "read_only",
        "source": {
            "mating_source": "supabase_canonical",
            "litter_source": "supabase_canonical",
        },
        "sows": [{
            "pig_id": "PRIVATE-SOW-1",
            "open_count": 1,
            "repeat_service_count": 0,
            "mating_count": 2,
            "pregnancy_rate": 1.0,
        }],
        "boars": [{"pig_id": "PRIVATE-BOAR-1", "mating_count": 2}],
    }
    return allocation, sales, litters, breeding


def build(**overrides):
    allocation, sales, litters, breeding = complete_envelopes()
    values = {
        "allocation_envelope": allocation,
        "sales_envelope": sales,
        "litter_envelope": litters,
        "breeding_envelope": breeding,
        "today": TODAY,
    }
    values.update(overrides)
    return build_herdmaster_daily_brief(**values)


class HerdmasterDailyBriefServiceTests(unittest.TestCase):
    def test_supported_weight_ranges_keep_an_unambiguous_separator(self):
        self.assertEqual(format_weight_band_label("24_to_29_Kg"), "24–29 kg")
        self.assertEqual(format_weight_band_label("30_to_34_Kg"), "30–34 kg")
        self.assertEqual(format_weight_band_label("60_to_64_Kg"), "60–64 kg")
        self.assertEqual(format_weight_band_label("24-29 kg"), "24–29 kg")
        self.assertEqual(format_weight_band_label("30–34 kg"), "30–34 kg")

    def test_exact_numeric_weight_remains_distinct_from_a_range(self):
        self.assertEqual(format_weight_band_label(60), "60 kg")
        self.assertEqual(format_weight_band_label("60"), "60 kg")
        self.assertEqual(format_weight_band_label("60_Kg"), "60 kg")
        self.assertEqual(format_weight_band_label(60.5), "60.5 kg")
        self.assertNotEqual(
            format_weight_band_label("60_to_64_Kg"),
            format_weight_band_label(60),
        )

    def test_malformed_and_missing_weight_bands_remain_unknown(self):
        for value in (None, "", "60_64_Kg", "broken_60_64", "64_to_60_Kg", True):
            with self.subTest(value=value):
                self.assertEqual(format_weight_band_label(value), "Unknown")

    def test_serialized_json_and_plain_text_never_collapse_weight_ranges(self):
        allocation, sales, litters, breeding = complete_envelopes()
        sales["pigs"] = [
            sales_row(weight_band="24_to_29_Kg"),
            sales_row(
                pig_id="PRIVATE-PIG-2",
                tag_number="PRIVATE-TAG-2",
                weight_band="30_to_34_Kg",
            ),
            sales_row(
                pig_id="PRIVATE-PIG-3",
                tag_number="PRIVATE-TAG-3",
                weight_band="60_to_64_Kg",
                current_weight_kg=62,
            ),
        ]
        result = build(
            allocation_envelope=allocation,
            sales_envelope=sales,
            litter_envelope=litters,
            breeding_envelope=breeding,
        )
        bands = result["sales_readiness"]["eligible_weight_bands"]
        plain_text = result["sales_readiness"]["eligible_weight_bands_plain_text"]
        executive_text = result["sanitized_executive_summary"]["sales_weight_bands"]
        unicode_json = json.dumps(bands, ensure_ascii=False)
        ascii_json = json.dumps(bands)

        self.assertEqual(
            bands,
            {"24–29 kg": 1, "30–34 kg": 1, "60–64 kg": 1},
        )
        for expected, collapsed in (
            ("24–29 kg", "2429 kg"),
            ("30–34 kg", "3034 kg"),
            ("60–64 kg", "6064 kg"),
        ):
            self.assertIn(expected, unicode_json)
            self.assertIn(expected, plain_text)
            self.assertIn(expected, executive_text)
            self.assertNotIn(collapsed, unicode_json)
            self.assertNotIn(collapsed, ascii_json)
            self.assertNotIn(collapsed, plain_text)
            self.assertNotIn(collapsed, executive_text)
        self.assertIn(r"60\u201364 kg", ascii_json)

    def test_complete_current_shaped_evidence_builds_sanitized_brief(self):
        result = build()

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["brief_date"], "2026-07-25")
        self.assertEqual(result["herd_overview"]["active_on_farm"], 2)
        self.assertEqual(result["herd_overview"]["terminal"], 1)
        self.assertEqual(
            result["herd_overview"]["sex_distribution"],
            {"Female": 1, "Male": 1},
        )
        self.assertEqual(
            result["herd_overview"]["purpose_distribution"],
            {"Breeding": 1, "Sale": 1},
        )
        self.assertEqual(
            result["herd_overview"]["lifecycle_distribution"],
            {"Boar": 1, "Grower": 1},
        )
        self.assertEqual(result["source_status"]["allocation_query"]["state"], "known")
        self.assertEqual(result["source_status"]["sales"]["observation_timestamp"], "2026-07-25")
        self.assertEqual(result["sales_readiness"]["affirmatively_eligible"], 2)
        self.assertEqual(
            result["sales_readiness"]["eligible_weight_bands"],
            {"25–29 kg": 1, "60–64 kg": 1},
        )

    def test_missing_envelopes_are_unavailable_not_zero(self):
        result = build_herdmaster_daily_brief(today=TODAY)

        self.assertEqual(result["status"], "evidence_incomplete")
        self.assertEqual(result["herd_overview"]["status"], "Unavailable")
        self.assertIsNone(result["herd_overview"]["active_on_farm"])
        self.assertIsNone(result["evidence_work_queue"]["missing_current_weight"])
        self.assertEqual(result["sales_readiness"]["status"], "Unavailable")
        self.assertIsNone(result["sales_readiness"]["affirmatively_eligible"])
        self.assertFalse(result["sales_readiness"]["known_zero"])
        self.assertIn("allocation_envelope_unavailable", result["evidence_blockers"])

    def test_stale_and_missing_weight_queue_remains_explicit(self):
        allocation, sales, litters, breeding = complete_envelopes()
        allocation["pigs"] = [
            allocation_row(latest_weight_kg=None, latest_weight_date="", days_since_weight=None),
            allocation_row(pig_id="PRIVATE-PIG-2", days_since_weight=31),
        ]
        result = build(
            allocation_envelope=allocation,
            sales_envelope=sales,
            litter_envelope=litters,
            breeding_envelope=breeding,
        )

        self.assertEqual(result["evidence_work_queue"]["missing_current_weight"], 1)
        self.assertEqual(result["evidence_work_queue"]["stale_weight"], 1)
        weight_task = next(
            item for item in result["owner_worklist"]["today"]
            if item["category"] == "weight_evidence"
        )
        self.assertEqual(weight_task["count"], 2)
        self.assertEqual(weight_task["action_type"], "physical_farm_check")

    def test_unknown_allocation_query_state_fails_closed(self):
        allocation, sales, litters, breeding = complete_envelopes()
        allocation.pop("allocation_query_status")
        sales.pop("allocation_query_status")
        for row in allocation["pigs"] + sales["pigs"]:
            row.pop("allocation_query_status", None)
        result = build(
            allocation_envelope=allocation,
            sales_envelope=sales,
            litter_envelope=litters,
            breeding_envelope=breeding,
        )

        state = result["source_status"]["allocation_query"]
        self.assertEqual(state["state"], "Unavailable")
        self.assertEqual(state["exposure"], "Not exposed")
        self.assertEqual(result["sales_readiness"]["status"], "Unavailable")
        self.assertIsNone(result["sales_readiness"]["affirmatively_eligible"])
        self.assertEqual(
            result["sales_readiness"]["tested_enquiry_shortfalls"]
            ["one_male_grower_25_29_kg"]["status"],
            "evidence_unavailable",
        )

    def test_known_zero_is_distinct_from_unavailable_allocation(self):
        allocation, sales, litters, breeding = complete_envelopes()
        sales["pigs"] = []
        known = build(
            allocation_envelope=allocation,
            sales_envelope=sales,
            litter_envelope=litters,
            breeding_envelope=breeding,
        )
        allocation.pop("allocation_query_status")
        sales.pop("allocation_query_status")
        for row in allocation["pigs"]:
            row.pop("allocation_query_status", None)
        unavailable = build(
            allocation_envelope=allocation,
            sales_envelope=sales,
            litter_envelope=litters,
            breeding_envelope=breeding,
        )

        self.assertEqual(known["sales_readiness"]["status"], "available")
        self.assertTrue(known["sales_readiness"]["known_zero"])
        self.assertEqual(known["sales_readiness"]["affirmatively_eligible"], 0)
        self.assertEqual(unavailable["sales_readiness"]["status"], "Unavailable")
        self.assertFalse(unavailable["sales_readiness"]["known_zero"])
        self.assertIsNone(unavailable["sales_readiness"]["affirmatively_eligible"])

    def test_overdue_weaning_is_prioritized_today(self):
        allocation, sales, litters, breeding = complete_envelopes()
        litters["litters"][0]["days_until_estimated_wean"] = -3
        result = build(
            allocation_envelope=allocation,
            sales_envelope=sales,
            litter_envelope=litters,
            breeding_envelope=breeding,
        )

        self.assertEqual(result["litter_management"]["overdue_weaning_evidence"], 1)
        self.assertEqual(
            [item["category"] for item in result["owner_worklist"]["today"]],
            ["overdue_weaning"],
        )

    def test_medical_hold_is_counted_without_private_detail(self):
        allocation, sales, litters, breeding = complete_envelopes()
        allocation["pigs"][0].update({
            "medical_status": "Follow Up",
            "medical_notes": "PRIVATE MEDICAL NARRATIVE",
        })
        result = build(
            allocation_envelope=allocation,
            sales_envelope=sales,
            litter_envelope=litters,
            breeding_envelope=breeding,
        )
        serialized = json.dumps(result)

        self.assertEqual(result["evidence_work_queue"]["medical_or_follow_up_holds"], 1)
        self.assertNotIn("PRIVATE MEDICAL NARRATIVE", serialized)
        self.assertFalse(result["privacy"]["contains_private_medical_details"])

    def test_purpose_review_queue_is_deterministic(self):
        allocation, sales, litters, breeding = complete_envelopes()
        allocation["pigs"][0].update({
            "purpose": "",
            "readiness_bucket": "Needs Classification",
        })
        result = build(
            allocation_envelope=allocation,
            sales_envelope=sales,
            litter_envelope=litters,
            breeding_envelope=breeding,
        )

        self.assertEqual(result["evidence_work_queue"]["unknown_purpose"], 1)
        self.assertEqual(result["evidence_work_queue"]["needs_classification"], 1)
        self.assertEqual(
            [item["category"] for item in result["owner_worklist"]["next_3_days"]],
            ["purpose_review", "breeding_review"],
        )

    def test_overlapping_exclusion_counts_count_each_reason(self):
        allocation, sales, litters, breeding = complete_envelopes()
        sales["pigs"] = [{
            **sales_row(
                live_stock_sale_eligible=False,
                evidence_complete=False,
            ),
            "exclusion_reasons": [
                "Pig is not active.",
                "Only pigs with Purpose = Sale may enter SAM Live stock sales.",
                "withdrawal evidence unknown",
            ],
        }]
        result = build(
            allocation_envelope=allocation,
            sales_envelope=sales,
            litter_envelope=litters,
            breeding_envelope=breeding,
        )
        counts = result["sales_readiness"]["overlapping_exclusion_counts"]

        self.assertEqual(counts["inactive_or_off_farm"], 1)
        self.assertEqual(counts["purpose_not_sale"], 1)
        self.assertEqual(counts["withdrawal_unknown_or_active"], 1)
        self.assertGreater(sum(counts.values()), 1)

    def test_slow_growth_is_aggregated_as_a_cohort(self):
        allocation, sales, litters, breeding = complete_envelopes()
        allocation["pigs"] = [
            allocation_row(growth_class="Slow"),
            allocation_row(pig_id="PRIVATE-PIG-2", growth_class="Slow"),
            allocation_row(pig_id="PRIVATE-PIG-3", growth_class="Extremely Slow"),
        ]
        result = build(
            allocation_envelope=allocation,
            sales_envelope=sales,
            litter_envelope=litters,
            breeding_envelope=breeding,
        )

        self.assertEqual(result["growth_cohorts"]["cohorts"]["Slow"], 2)
        self.assertEqual(result["growth_cohorts"]["slow_or_extremely_slow"], 3)
        task = next(
            item for item in result["owner_worklist"]["next_7_days"]
            if item["category"] == "growth_cohort_review"
        )
        self.assertEqual(task["count"], 3)
        self.assertIn("cohort", task["action"].lower())

    def test_historical_deaths_without_dates_are_not_recent_incident(self):
        result = build()

        self.assertEqual(result["litter_management"]["historical_loss_totals"]["dead"], 2)
        recent = result["litter_management"]["recent_loss_assessment"]
        self.assertEqual(recent["status"], "Unavailable")
        self.assertIn("date-bounded", recent["reason"])
        self.assertNotIn("incident", result["sanitized_executive_summary"]["headline"].lower())

    def test_no_exact_animal_or_customer_leakage(self):
        result = build()
        serialized = json.dumps(result)

        for private_value in (
            "PRIVATE-PIG",
            "PRIVATE-TAG",
            "PRIVATE-PEN",
            "PRIVATE-LITTER",
            "PRIVATE-SOW",
            "PRIVATE-BOAR",
        ):
            self.assertNotIn(private_value, serialized)
        keys = set()

        def collect_keys(value):
            if isinstance(value, dict):
                keys.update(value)
                for nested in value.values():
                    collect_keys(nested)
            elif isinstance(value, list):
                for nested in value:
                    collect_keys(nested)

        collect_keys(result)
        self.assertTrue(
            {"pig_id", "tag_number", "current_pen_id", "medical_notes"}.isdisjoint(keys)
        )
        self.assertFalse(result["privacy"]["contains_pig_ids"])
        self.assertFalse(result["privacy"]["customer_visible"])
        self.assertFalse(result["sales_readiness"]["customer_private_details_visible"])

    def test_zero_write_and_protected_action_authority_is_fixed(self):
        result = build()

        self.assertFalse(result["writes_performed"])
        self.assertFalse(result["protected_actions_performed"])
        self.assertTrue(result["authority"]["read_only"])
        self.assertFalse(result["authority"]["writes_performed"])
        self.assertFalse(result["authority"]["protected_actions_performed"])
        for key in (
            "creates_order",
            "reserves_or_allocates_stock",
            "changes_farm_data",
            "sends_customer_message",
            "sends_telegram",
        ):
            self.assertFalse(result["authority"][key])

    def test_today_three_day_seven_day_prioritization_is_deterministic(self):
        allocation, sales, litters, breeding = complete_envelopes()
        allocation["pigs"] = [
            allocation_row(
                purpose="",
                readiness_bucket="Needs Classification",
                latest_weight_kg=None,
                days_since_weight=None,
                medical_status="Hold",
                growth_class="Slow",
            )
        ]
        litters["litters"][0]["days_until_estimated_wean"] = -1
        first = build(
            allocation_envelope=allocation,
            sales_envelope=sales,
            litter_envelope=litters,
            breeding_envelope=breeding,
        )
        second = build(
            allocation_envelope=allocation,
            sales_envelope=sales,
            litter_envelope=litters,
            breeding_envelope=breeding,
        )

        self.assertEqual(first["owner_worklist"], second["owner_worklist"])
        self.assertEqual(
            [item["category"] for item in first["owner_worklist"]["today"]],
            ["medical_follow_up", "overdue_weaning", "weight_evidence"],
        )
        self.assertEqual(
            [item["category"] for item in first["owner_worklist"]["next_3_days"]],
            ["purpose_review", "breeding_review"],
        )
        self.assertEqual(
            [item["category"] for item in first["owner_worklist"]["next_7_days"]],
            ["growth_cohort_review", "recent_loss_evidence"],
        )

    def test_breeding_opportunities_are_advisory_not_current_readiness(self):
        result = build()
        breeding = result["breeding_review"]

        self.assertTrue(breeding["advisory_only"])
        for prohibited_claim in ("current heat", "pregnancy", "body condition", "relatedness"):
            self.assertIn(prohibited_claim, breeding["qualification"])


if __name__ == "__main__":
    unittest.main()
