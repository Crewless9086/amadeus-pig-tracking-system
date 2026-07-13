import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app import app
from modules.beacon.opportunity_scanner import build_beacon_opportunity_cards
from modules.sales import sales_transaction_routes

NOW = datetime(2026, 7, 12, 12, tzinfo=timezone.utc)


def eligible_pig(pig_id='P1', category='Grower', sex='Male'):
    return {'pig_id': pig_id, 'status': 'Active', 'on_farm': 'Yes', 'purpose': 'Sale', 'reserved_status': '', 'reserved_for_order_id': '', 'animal_type': category, 'calculated_stage': category, 'latest_weight_kg': 35, 'latest_weight_date': '2026-07-12', 'days_since_weight': 0, 'withdrawal_clear': 'Yes', 'health_status': 'Healthy', 'medical_status': 'Clear', 'wean_date': '2026-05-01', 'sale_category': category, 'sex': sex}


class BeaconOpportunityScannerTests(unittest.TestCase):
    def test_malformed_allocation_pigs_and_thresholds_fail_closed(self):
        demand = [{'conversation_id': 'C1', 'intake_status': 'Open', 'quantity': 2, 'category': 'Grower'}]
        malformed_values = ((None, 'bad-thresholds'), ({}, None), ('not-pigs', []), ([eligible_pig(), None], 'bad-thresholds'))
        for pigs, thresholds in malformed_values:
            with self.subTest(pigs=pigs, thresholds=thresholds):
                allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': thresholds, 'pigs': pigs}
                result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=demand, meat_leads=[], now=NOW)
                live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
                self.assertEqual(live['demand_cap'], 0)
                self.assertEqual(live['status'], 'blocked')
                self.assertIn('malformed_allocation_pigs_evidence', live['blockers'])
                self.assertIn('malformed_allocation_thresholds_evidence', live['blockers'])

    def test_malformed_allocation_pig_row_stops_eligibility_iteration(self):
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': [eligible_pig(), None]}
        demand = [{'conversation_id': 'C1', 'intake_status': 'Open', 'quantity': 2, 'category': 'Grower'}]
        with patch('modules.beacon.opportunity_scanner._live_stock_sale_eligibility') as eligibility:
            result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=demand, meat_leads=[], now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        eligibility.assert_not_called()
        self.assertEqual(live['capacity_calculation']['verified_available'], 0)
        self.assertEqual(live['demand_cap'], 0)
        self.assertIn('malformed_allocation_pigs_evidence', live['blockers'])

    def test_invalid_stale_weight_threshold_values_fail_closed(self):
        demand = [{'conversation_id': 'C1', 'intake_status': 'Open', 'quantity': 2, 'category': 'Grower'}]
        invalid_thresholds = (
            {},
            {'fresh_weight_days': 14},
            {'stale_weight_days': None},
            {'stale_weight_days': ''},
            {'stale_weight_days': 0},
            {'stale_weight_days': -1},
            {'stale_weight_days': True},
            {'stale_weight_days': float('nan')},
            {'stale_weight_days': float('inf')},
            {'stale_weight_days': []},
        )
        for thresholds in invalid_thresholds:
            with self.subTest(thresholds=thresholds):
                allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': thresholds, 'pigs': [eligible_pig(f'P{i}') for i in range(5)]}
                result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=demand, meat_leads=[], now=NOW)
                live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
                self.assertEqual(live['demand_cap'], 0)
                self.assertEqual(live['capacity_calculation']['verified_available'], 0)
                self.assertEqual(live['status'], 'blocked')
                self.assertIn('malformed_allocation_thresholds_evidence', live['blockers'])

    def test_numeric_stale_weight_threshold_is_normalized_and_enforced(self):
        pigs = [eligible_pig(f'P{i}') for i in range(5)]
        for pig in pigs:
            pig['days_since_weight'] = 15
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': '14'}, 'pigs': pigs}
        demand = [{'conversation_id': 'C1', 'intake_status': 'Open', 'quantity': 2, 'category': 'Grower'}]
        result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=demand, meat_leads=[], now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        self.assertEqual(live['capacity_calculation']['verified_available'], 0)
        self.assertEqual(live['demand_cap'], 0)
        self.assertNotIn('malformed_allocation_thresholds_evidence', live['blockers'])

    @patch('modules.beacon.opportunity_scanner.get_pig_allocation_readiness')
    @patch('modules.beacon.opportunity_scanner.list_sales_leads')
    @patch('modules.beacon.opportunity_scanner.list_sam_live_stock_open_intakes')
    def test_production_allocation_adapter_invalid_threshold_fails_closed(self, list_intakes, list_leads, get_allocation):
        get_allocation.return_value = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 'not-a-number'}, 'pigs': [eligible_pig(f'P{i}') for i in range(5)]}
        list_intakes.return_value = ({'success': True, 'open_intakes': [{'conversation_id': 'C1', 'intake_status': 'Open', 'quantity': 2, 'category': 'Grower'}]}, 200)
        list_leads.return_value = ({'success': True, 'sales_leads': []}, 200)
        result = build_beacon_opportunity_cards(now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        self.assertEqual(live['demand_cap'], 0)
        self.assertEqual(live['status'], 'blocked')
        self.assertIn('malformed_allocation_thresholds_evidence', live['blockers'])
        get_allocation.assert_called_once_with(today=NOW.date(), allow_sheet_fallback=False)

    def test_malformed_demand_rows_fail_closed_for_both_lanes(self):
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': [eligible_pig(f'P{i}') for i in range(5)]}
        malformed_rows = [None, 'bad-row', ['nested-row']]
        result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=malformed_rows, meat_leads=malformed_rows, now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        meat = next(card for card in result['cards'] if card['lane'] == 'meat')
        self.assertEqual(live['demand_cap'], 0)
        self.assertEqual(live['demand_summary']['malformed_records'], 3)
        self.assertIn('malformed_live_stock_demand_evidence', live['blockers'])
        self.assertEqual(meat['demand_cap'], 0)
        self.assertEqual(meat['demand_summary']['malformed_records'], 3)
        self.assertIn('malformed_meat_demand_evidence', meat['blockers'])

    @patch('modules.beacon.opportunity_scanner.list_sales_leads')
    @patch('modules.beacon.opportunity_scanner.list_sam_live_stock_open_intakes')
    def test_production_adapters_malformed_rows_return_blocked_cards(self, list_intakes, list_leads):
        list_intakes.return_value = ({'success': True, 'open_intakes': [None, 'bad-row']}, 200)
        list_leads.return_value = ({'success': True, 'sales_leads': [None, 'bad-row']}, 200)
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': [eligible_pig(f'P{i}') for i in range(5)]}
        result = build_beacon_opportunity_cards(allocation=allocation, now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        meat = next(card for card in result['cards'] if card['lane'] == 'meat')
        self.assertEqual(live['demand_cap'], 0)
        self.assertIn('malformed_live_stock_demand_evidence', live['blockers'])
        self.assertEqual(meat['demand_cap'], 0)
        self.assertIn('malformed_meat_demand_evidence', meat['blockers'])

    def test_live_cap_is_demand_and_buffer_bounded(self):
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': [eligible_pig(f'P{i}') for i in range(5)]}
        result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=[{'conversation_id': 'C1', 'intake_status': 'Open', 'quantity': 9, 'category': 'Grower'}], meat_leads=[], now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        self.assertEqual(live['demand_cap'], 3)
        self.assertEqual(live['status'], 'ready_for_owner_review')
        self.assertFalse(any(live['authority'].values()))

    def test_degraded_source_and_unknown_quantity_fail_closed(self):
        result = build_beacon_opportunity_cards(allocation={'source': 'google_sheets', 'generated_date': '2026-07-12', 'pigs': [eligible_pig()]}, live_intakes=[{'conversation_id': 'C1', 'intake_status': 'Open'}], meat_leads=[], now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        self.assertEqual(live['demand_cap'], 0)
        self.assertIn('supabase_allocation_readiness_unavailable', live['blockers'])

    def test_future_dated_allocation_evidence_fails_closed(self):
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-14', 'thresholds': {'stale_weight_days': 14}, 'pigs': [eligible_pig(f'P{i}') for i in range(5)]}
        result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=[{'conversation_id': 'C1', 'intake_status': 'Open', 'quantity': 3, 'category': 'Grower'}], meat_leads=[], now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        self.assertEqual(live['demand_cap'], 0)
        self.assertEqual(live['status'], 'blocked')
        self.assertFalse(live['freshness']['fresh'])
        self.assertIn('future_dated_allocation_evidence', live['blockers'])

    def test_any_unknown_live_demand_quantity_fails_closed(self):
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': [eligible_pig(f'P{i}') for i in range(5)]}
        intakes = [
            {'conversation_id': 'C1', 'intake_status': 'Open', 'quantity': 3, 'category': 'Grower'},
            {'conversation_id': 'C2', 'intake_status': 'Open'},
        ]
        result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=intakes, meat_leads=[], now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        self.assertEqual(live['demand_summary']['qualified_units'], 3)
        self.assertEqual(live['demand_summary']['unknown_quantity_records'], 1)
        self.assertEqual(live['demand_cap'], 0)
        self.assertEqual(live['status'], 'blocked')
        self.assertIn('unknown_live_stock_demand_quantity', live['blockers'])

    def test_meat_cap_is_zero_in_controlled_mode(self):
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'pigs': []}
        leads = [{'lead_id': 'L1', 'chatwoot_conversation_id': 'C1', 'status': 'interested', 'interest': {'quantity': 4, 'sam_intake_lane': 'meat_preorder'}}]
        result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=[], meat_leads=leads, now=NOW)
        meat = next(card for card in result['cards'] if card['lane'] == 'meat')
        self.assertEqual(meat['demand_summary']['qualified_units'], 4)
        self.assertEqual(meat['demand_cap'], 0)
        self.assertIn('butcher_loop_not_proven', meat['blockers'])

    def test_incompatible_live_stock_category_fails_closed(self):
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': [eligible_pig(f'P{i}') for i in range(5)]}
        intakes = [{'conversation_id': 'C1', 'intake_status': 'Open', 'items': [{'quantity': 3, 'category': 'Weaner'}]}]
        result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=intakes, meat_leads=[], now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        self.assertEqual(live['demand_cap'], 0)
        self.assertEqual(live['demand_summary']['incompatible_records'], 1)
        self.assertIn('incompatible_live_stock_demand', live['blockers'])

    def test_mixed_supply_counts_and_buffers_only_compatible_category(self):
        pigs = [eligible_pig('G1')] + [eligible_pig(f'F{i}', 'Finisher') for i in range(4)]
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': pigs}
        intakes = [{'conversation_id': 'C1', 'intake_status': 'Open', 'quantity': 3, 'category': 'Grower'}]
        result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=intakes, meat_leads=[], now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        self.assertEqual(live['demand_cap'], 0)
        self.assertEqual(live['capacity_calculation']['verified_available'], 1)
        self.assertEqual(live['capacity_calculation']['capacity_by_category']['grower']['verified_available'], 1)
        self.assertEqual(live['status'], 'blocked')

    def test_production_intake_item_shape_supplies_quantity_and_category(self):
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': [eligible_pig(f'P{i}') for i in range(5)]}
        intakes = [{'conversation_id': 'C1', 'intake_status': 'Open', 'items': [{'quantity': 3, 'category': 'Grower'}]}]
        result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=intakes, meat_leads=[], now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        self.assertEqual(live['demand_cap'], 3)
        self.assertEqual(live['status'], 'ready_for_owner_review')

    def test_category_match_with_weight_mismatch_fails_closed(self):
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': [eligible_pig(f'P{i}') for i in range(5)]}
        intakes = [{'conversation_id': 'C1', 'intake_status': 'Open', 'items': [{'quantity': 3, 'category': 'Grower', 'weight_range': '10-14 kg'}]}]
        result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=intakes, meat_leads=[], now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        self.assertEqual(live['demand_cap'], 0)
        self.assertEqual(live['capacity_calculation']['verified_available'], 0)
        self.assertIn('incompatible_live_stock_weight_requirement', live['blockers'])

    def test_same_category_and_weight_with_sex_mismatch_fails_closed(self):
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': [eligible_pig(f'P{i}', sex='Male') for i in range(5)]}
        intakes = [{'conversation_id': 'C1', 'intake_status': 'Open', 'items': [{'quantity': 3, 'category': 'Grower', 'weight_range': '30-40 kg', 'sex': 'Female'}]}]
        result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=intakes, meat_leads=[], now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        self.assertEqual(live['demand_cap'], 0)
        self.assertEqual(live['capacity_calculation']['verified_available'], 0)
        self.assertIn('incompatible_live_stock_weight_requirement', live['blockers'])

    def test_partial_same_category_sex_supply_fails_closed(self):
        pigs = [eligible_pig('F1', sex='Female')] + [eligible_pig(f'M{i}', sex='Male') for i in range(9)]
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': pigs}
        intakes = [
            {'conversation_id': 'C1', 'intake_status': 'Open', 'items': [
                {'quantity': 5, 'category': 'Grower', 'weight_range': '30-40 kg', 'sex': 'Female'},
                {'quantity': 5, 'category': 'Grower', 'weight_range': '30-40 kg', 'sex': 'Male'},
            ]},
        ]
        result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=intakes, meat_leads=[], now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        self.assertEqual(live['demand_cap'], 0)
        self.assertIn('incompatible_live_stock_weight_requirement', live['blockers'])

    def test_production_item_shape_matches_category_weight_and_sex(self):
        pigs = [eligible_pig('M1', sex='Male')] + [eligible_pig(f'F{i}', sex='Female') for i in range(4)]
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': pigs}
        intakes = [{'conversation_id': 'C1', 'intake_status': 'Open', 'items': [{'item_key': 'live_stock_primary', 'quantity': 2, 'category': 'Grower', 'weight_range': '30_to_40_Kg', 'sex': 'Female', 'status': 'active'}]}]
        result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=intakes, meat_leads=[], now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        self.assertEqual(live['capacity_calculation']['verified_available'], 4)
        self.assertEqual(live['demand_cap'], 2)

    @patch('modules.beacon.opportunity_scanner.list_sam_live_stock_open_intakes')
    def test_production_adapter_output_is_matched_by_category_weight_and_sex(self, list_intakes):
        list_intakes.return_value = ({'success': True, 'open_intakes': [{'conversation_id': 'C1', 'intake_status': 'Open', 'items': [{'item_key': 'live_stock_primary', 'quantity': 2, 'category': 'Grower', 'weight_range': '30_to_40_Kg', 'sex': 'Female', 'status': 'active'}]}]}, 200)
        pigs = [eligible_pig('M1', sex='Male')] + [eligible_pig(f'F{i}', sex='Female') for i in range(4)]
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': pigs}
        result = build_beacon_opportunity_cards(allocation=allocation, meat_leads=[], now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        self.assertEqual(live['capacity_calculation']['verified_available'], 4)
        self.assertEqual(live['demand_cap'], 2)
        list_intakes.assert_called_once_with(limit=100)

    @patch('modules.beacon.opportunity_scanner.list_sam_live_stock_open_intakes')
    def test_production_adapter_structured_weight_evidence_fails_closed(self, list_intakes):
        for weight_range in (
            {'min': 30, 'max': 40},
            [30, 40],
            '30 pigs needed in 40 days',
            'age 30 to 40 days',
            'call 30/40 before delivery',
        ):
            with self.subTest(weight_range=weight_range):
                list_intakes.return_value = ({'success': True, 'open_intakes': [{'conversation_id': 'C1', 'intake_status': 'Open', 'items': [{'item_key': 'live_stock_primary', 'quantity': 2, 'category': 'Grower', 'weight_range': weight_range, 'sex': 'Female', 'status': 'active'}]}]}, 200)
                allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': [eligible_pig(f'P{i}', sex='Female') for i in range(5)]}
                result = build_beacon_opportunity_cards(allocation=allocation, meat_leads=[], now=NOW)
                live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
                self.assertEqual(live['demand_cap'], 0)
                self.assertEqual(live['status'], 'blocked')
                self.assertEqual(live['demand_summary']['invalid_weight_records'], 1)
                self.assertIn('invalid_live_stock_weight_requirement', live['blockers'])

    def test_uninterpretable_sex_requirement_fails_closed(self):
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': [eligible_pig(f'P{i}') for i in range(5)]}
        intakes = [{'conversation_id': 'C1', 'intake_status': 'Open', 'items': [{'quantity': 2, 'category': 'Grower', 'weight_range': '30-40 kg', 'sex': 'unknown'}]}]
        result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=intakes, meat_leads=[], now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        self.assertEqual(live['demand_cap'], 0)
        self.assertIn('invalid_live_stock_sex_requirement', live['blockers'])

    def test_missing_supply_sex_fails_closed_even_for_any_preference(self):
        pigs = [eligible_pig(f'P{i}', sex='') for i in range(5)]
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': pigs}
        intakes = [{'conversation_id': 'C1', 'intake_status': 'Open', 'items': [{'quantity': 2, 'category': 'Grower', 'weight_range': '30-40 kg', 'sex': 'Any'}]}]
        result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=intakes, meat_leads=[], now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        self.assertEqual(live['demand_cap'], 0)
        self.assertEqual(live['capacity_calculation']['verified_available'], 0)
        self.assertIn('incompatible_live_stock_weight_requirement', live['blockers'])

    def test_weight_range_boundaries_are_inclusive(self):
        pigs = [eligible_pig(f'P{i}') for i in range(5)]
        pigs[0]['latest_weight_kg'] = 30
        pigs[1]['latest_weight_kg'] = 40
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': pigs}
        intakes = [{'conversation_id': 'C1', 'intake_status': 'Open', 'items': [{'quantity': 2, 'category': 'Grower', 'weight_range': '30_to_40_Kg'}]}]
        result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=intakes, meat_leads=[], now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        self.assertEqual(live['capacity_calculation']['verified_available'], 5)
        self.assertEqual(live['demand_cap'], 2)

    def test_contradictory_or_unparseable_weight_requirement_fails_closed(self):
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': [eligible_pig(f'P{i}') for i in range(5)]}
        for weight_range in ('40-30 kg', 'heavy grower'):
            with self.subTest(weight_range=weight_range):
                intakes = [{'conversation_id': 'C1', 'intake_status': 'Open', 'items': [{'quantity': 2, 'category': 'Grower', 'weight_range': weight_range}]}]
                result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=intakes, meat_leads=[], now=NOW)
                live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
                self.assertEqual(live['demand_cap'], 0)
                self.assertIn('invalid_live_stock_weight_requirement', live['blockers'])

    def test_route_is_owner_guarded(self):
        app.testing = True
        denied = ({'success': False, 'status': 'owner_access_required'}, 401)
        with patch.object(sales_transaction_routes, 'require_owner_read_access', return_value=denied), patch.object(sales_transaction_routes, 'build_beacon_opportunity_cards') as scanner:
            response = app.test_client().get('/api/sales/beacon/opportunities')
        self.assertEqual(response.status_code, 401)
        scanner.assert_not_called()
