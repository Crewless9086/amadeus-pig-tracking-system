import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app import app
from modules.beacon.opportunity_scanner import build_beacon_opportunity_cards
from modules.sales import sales_transaction_routes

NOW = datetime(2026, 7, 12, 12, tzinfo=timezone.utc)


def eligible_pig(pig_id='P1'):
    return {'pig_id': pig_id, 'status': 'Active', 'on_farm': 'Yes', 'purpose': 'Sale', 'reserved_status': '', 'reserved_for_order_id': '', 'animal_type': 'Grower', 'calculated_stage': 'Grower', 'latest_weight_kg': 35, 'latest_weight_date': '2026-07-12', 'days_since_weight': 0, 'withdrawal_clear': 'Yes', 'health_status': 'Healthy', 'medical_status': 'Clear', 'wean_date': '2026-05-01', 'sale_category': 'Grower'}


class BeaconOpportunityScannerTests(unittest.TestCase):
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

    def test_production_intake_item_shape_supplies_quantity_and_category(self):
        allocation = {'source': 'supabase_canonical', 'generated_date': '2026-07-12', 'thresholds': {'stale_weight_days': 14}, 'pigs': [eligible_pig(f'P{i}') for i in range(5)]}
        intakes = [{'conversation_id': 'C1', 'intake_status': 'Open', 'items': [{'quantity': 3, 'category': 'Grower'}]}]
        result = build_beacon_opportunity_cards(allocation=allocation, live_intakes=intakes, meat_leads=[], now=NOW)
        live = next(card for card in result['cards'] if card['lane'] == 'live_stock')
        self.assertEqual(live['demand_cap'], 3)
        self.assertEqual(live['status'], 'ready_for_owner_review')

    def test_route_is_owner_guarded(self):
        app.testing = True
        denied = ({'success': False, 'status': 'owner_access_required'}, 401)
        with patch.object(sales_transaction_routes, 'require_owner_read_access', return_value=denied), patch.object(sales_transaction_routes, 'build_beacon_opportunity_cards') as scanner:
            response = app.test_client().get('/api/sales/beacon/opportunities')
        self.assertEqual(response.status_code, 401)
        scanner.assert_not_called()
