"""Owner-policy to continuous planning regressions with a synthetic offline policy."""
import unittest
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from modules.telemetry.rootline_operating_policy import normalize_policy_snapshot,PolicyValidationError
from modules.telemetry.rootline_daily_advisor import build_rootline_daily_advisor
from modules.telemetry.rootline_adaptive_irrigation import build_adaptive_irrigation_decisions,project_weekly_delivery_obligation,build_run_outcome_evidence
from modules.telemetry.rootline_irrigation_job_contract import build_irrigation_job,project_next_segment
NOW=datetime(2026,11,15,20,0,tzinfo=timezone.utc)
RAW={'zones': {'B12345': {'daylight_window': 'any_time', 'minimum_useful_runtime_minutes': 'Unknown', 'maximum_continuous_runtime_minutes': 120}, 'C12345': {'daylight_window': 'any_time', 'minimum_useful_runtime_minutes': 'Unknown', 'maximum_continuous_runtime_minutes': 120}, 'A12345': {'daylight_window': 'any_time', 'minimum_useful_runtime_minutes': 'Unknown', 'maximum_continuous_runtime_minutes': 120, 'requested_total_duration_minutes': 120, 'target_days_per_week': 4, 'water_supply': 'gravity_fed_downhill', 'evidence_source': 'owner-a-camp-target-supply-20261101.json SHA256 9dd48f4e33c21811fa0434ccceebf1ac54d2800c31f448497a49ead31b5e84fa; owner continuous-run/all-hours instruction 20261115'}, 'E12345': {'daylight_window': 'any_time', 'minimum_useful_runtime_minutes': 'Unknown', 'maximum_continuous_runtime_minutes': 120, 'requested_total_duration_minutes': 120, 'target_days_per_week': 4, 'water_supply': 'Unknown', 'evidence_source': 'owner-camp-e-schedule-20261115.json: Same as Camp A: 2 hours, 4 days a week; supply/crop Unknown'}}, 'forecast_rain': 'Unknown', 'live_rain_hold': {'comparison': 'greater_than', 'evidence_field': 'current_rain_rate_mm_per_hour', 'release_policy': {'dry_interval_minutes': 30, 'owner_review_required': False, 'dry_rain_rate_mm_per_hour': 0.0, 'minimum_fresh_station_readings': 2, 'visible_rain_confirmation_required': False}, 'threshold_mm_per_hour': 0.2}, 'crop_need_bands': {'B12345': 'Unknown', 'C12345': 'Unknown', 'A12345': 'Unknown', 'E12345': 'Unknown'}, 'residual_drainage': 'Unknown', 'temperature_limits': 'Unknown', 'seasonal_boundaries': 'Unknown', 'controller_power_loss': 'Unknown', 'contract_version': 'rootline_operating_policy_abce.v3'}
def payload(now=NOW):
    normalized=normalize_policy_snapshot(RAW)
    start=now-timedelta(minutes=30)
    brief={"success":True,"current_conditions":{"availability":"Available","freshness":"fresh","rain_rate_mm_h":0,"last_reading_at":now.isoformat()},"irrigation":{"availability":"Available"},"rain_release_evidence":{"availability":"Available","source":"governed_local_weather_station","source_healthy":True,"conflicting":False,"continuous_zero_rain_confirmed":True,"interval_start_at":start.isoformat(),"interval_end_at":now.isoformat(),"station_readings":[{"observed_at":t.isoformat(),"rain_rate_mm_h":0,"freshness":"fresh"} for t in (start,now)]}}
    advisor=build_rootline_daily_advisor(brief,now.astimezone(__import__('zoneinfo').ZoneInfo('Africa/Johannesburg')).date().isoformat(),{"policy":normalized},now)
    assert len(advisor['zones'])==4
    assert all(z['live_rain_release_proven'] for z in advisor['zones'])
    evidence={"zones":[],"local_weather":{"observed_at":now.isoformat(),"rain_rate_mm_h":0},"policy":{"target_days_per_week":4}}
    for z in advisor['zones']:
        evidence['zones'].append({"zone_id":z['zone_id'],"operating_policy":z['operating_policy'],"planning_epoch_start":now.isoformat(),"completion_ledger_complete_through":now.isoformat(),"completion_events":[]})
    return evidence,advisor
class PlannerProposalTests(unittest.TestCase):
    def test_full_policy_advisor_planner_all_four_continuous(self):
        for hour in (0,10,20):
            now=NOW.replace(hour=hour);e,a=payload(now)
            result=build_adaptive_irrigation_decisions(e,now=now)
            self.assertEqual(len(result['zones']),4)
            for z in result['zones']:
                self.assertEqual(z['decision'],'Run now',z)
                self.assertEqual(z['proposed_segment_minutes'],120)
                self.assertEqual(z['requested_total_duration_minutes'],120)
                self.assertEqual(z['expected_segment_count'],1)
                self.assertEqual(z['stop_mode'],'scheduled')
            ez=next(z for z in a['zones'] if z['zone_id']=='E12345')
            self.assertEqual(ez['operating_policy']['water_supply'],'Unknown')
            self.assertEqual(ez['operating_policy']['minimum_useful_runtime_minutes'],'Unknown')
            self.assertEqual(a['operating_knowledge']['zones']['E12345']['irrigation_type'],'Unknown')
    def test_rain_shortage_and_verified_completion_still_hold(self):
        for alteration in ('rain','shortage','completed'):
            e,_=payload()
            if alteration=='rain':e['local_weather']['rain_rate_mm_h']=2
            if alteration=='shortage':e['water']={'observed_at':NOW.isoformat(),'dry_supply':True}
            if alteration=='completed':
                for z in e['zones']:z['completion_events']=[{'outcome_id':z['zone_id']+'done','source':'canonical','completed_at':NOW.isoformat(),'state':'Completed','shutdown_verified':True,'verified_runtime_minutes':120,'objective_satisfied':True}]
            rows=build_adaptive_irrigation_decisions(e,now=NOW)['zones']
            self.assertEqual({z['decision'] for z in rows},{'Completed' if alteration=='completed' else 'Hold'})
    def test_timed_current_rain_threshold_not_historical_rain_or_stale_balance(self):
        e,_=payload();e['local_weather'].update(rain_today_mm=10,rain_rate_mm_h=0)
        for z in e['zones']:z['water_balance']={'status':'Available','ledger_current':True,'obligation_effect':'Needs Data'}
        rows=build_adaptive_irrigation_decisions(e,now=NOW)['zones']
        self.assertTrue(all(z['decision']=='Run now' for z in rows))
        self.assertTrue(all('water_balance_stale_no_credit' in z['evidence_gaps'] for z in rows))
        for rate,expected in ((0.2,'Run now'),(0.21,'Hold')):
            e['local_weather']['rain_rate_mm_h']=rate
            rows=build_adaptive_irrigation_decisions(e,now=NOW)['zones']
            self.assertEqual({z['decision'] for z in rows},{expected})
    def test_epoch_never_imports_old_week_debt(self):
        e,_=payload();z=e['zones'][0]
        z['completion_events']=[{'outcome_id':'old','source':'canonical','completed_at':(NOW-timedelta(days=1)).isoformat(),'state':'Completed','shutdown_verified':True,'verified_runtime_minutes':120,'objective_satisfied':True}]
        q=project_weekly_delivery_obligation(z,now=NOW)
        self.assertEqual(q['completed_days'],0);self.assertEqual(q['expected_days_by_now'],1);self.assertEqual(q['remaining_weekly_obligation_days'],1)
        z.pop('planning_epoch_start');q=project_weekly_delivery_obligation(z,now=NOW)
        self.assertEqual(q['expected_days_by_now'],4);self.assertEqual(q['completed_days'],1)
    def test_existing_scheduled_and_legacy_parent_jobs(self):
        for scheduled in (True,False):
            e,_=payload()
            for z in e['zones']:
                job=build_irrigation_job(zone_id=z['zone_id'],operating_date='2026-11-15',requested_total_seconds=7200,maximum_segment_seconds=7200 if scheduled else 3599,plan_identity='fixture',stop_mode='scheduled' if scheduled else None)
                z['incomplete_parent_job']={'job':job,'projection':project_next_segment(job,[],rearm_readback_off=True)}
            rows=build_adaptive_irrigation_decisions(e,now=NOW)['zones']
            for z in rows:
                self.assertEqual(z['decision'],'Run now',z)
                self.assertEqual(z['proposed_segment_minutes'],120 if scheduled else 60)
                self.assertEqual(z['stop_mode'],'scheduled' if scheduled else 'native_fail_stop')
    def test_legacy_policy_not_silently_upgraded(self):
        e,_=payload()
        for z in e['zones']:
            z['operating_policy'].pop('contract_version');z['operating_policy'].pop('stop_mode')
            z['operating_policy']['maximum_continuous_runtime_minutes']=60
            z['operating_policy']['minimum_useful_runtime_minutes']=1
        rows=build_adaptive_irrigation_decisions(e,now=NOW)['zones']
        self.assertTrue(all(z['max_segment_minutes']==60 for z in rows))
        self.assertTrue(all(z['stop_mode']=='native_fail_stop' for z in rows))
    def test_unknown_policy_with_legacy_parent_is_needs_data_not_crash(self):
        for unknown in (None,"Unknown"):
            e,_=payload()
            for z in e['zones']:
                if z['zone_id'] not in ('A12345','E12345'):continue
                z['operating_policy']['maximum_continuous_runtime_minutes']=unknown
                job=build_irrigation_job(zone_id=z['zone_id'],operating_date='2026-11-15',requested_total_seconds=7200,maximum_segment_seconds=3599,plan_identity='fixture')
                z['incomplete_parent_job']={'job':job,'projection':project_next_segment(job,[],rearm_readback_off=True)}
            rows=build_adaptive_irrigation_decisions(e,now=NOW)['zones']
            self.assertTrue(all(z['decision']=='Needs Data' for z in rows if z['zone_id'] in ('A12345','E12345')))
    def test_policy_identity_and_upper_bound(self):
        for kind in ('missing_e','oversize','version'):
            p=deepcopy(RAW)
            if kind=='missing_e':p['zones'].pop('E12345')
            if kind=='oversize':p['zones']['B12345']['maximum_continuous_runtime_minutes']=121
            if kind=='version':p['contract_version']='fake'
            with self.assertRaises(PolicyValidationError):normalize_policy_snapshot(p)
    def test_continuous_outcome_and_legacy_bound(self):
        outcome={'zone_id':'E12345','planned_runtime_minutes':120,'verified_runtime_minutes':120,'stop_mode':'scheduled'}
        self.assertEqual(build_run_outcome_evidence(outcome)['verified_runtime_minutes'],120)
        outcome.pop('stop_mode')
        with self.assertRaises(ValueError):build_run_outcome_evidence(outcome)


def test_live_reader_closes_nested_forecast_and_historical_power_reads(monkeypatch):
    from modules.telemetry import rootline_water_energy_plan as plan
    from modules.telemetry import rootline_daily_brief as brief
    from modules.telemetry import weather_service as weather, power_service as power
    from unittest.mock import Mock
    calls=[]
    power_packet={'success':True,'source':{'last_reading_at':NOW.isoformat(),'stale_after_minutes':15},
        'current':{'battery_soc_pct':80,'solar_power_w':2000,'load_power_w':900,'grid_power_w':0}}
    weather_packet={'success':True,'source':{'last_reading_at':NOW.isoformat(),'stale_after_minutes':30},
        'current':{'rain_rate_mm_h':0,'rain_today_mm':0}}
    monkeypatch.setattr(power,'get_current_power_state',lambda **_: (calls.append('power') or power_packet,200))
    monkeypatch.setattr(weather,'get_weather_control_snapshot',lambda **_:({'success':True,
        'weather_current':weather_packet,'rain_release':{}},200))
    outer=Mock(side_effect=AssertionError('outer forecast'));inner=Mock(side_effect=AssertionError('nested forecast'))
    monkeypatch.setattr(weather,'get_weather_forecast',outer);monkeypatch.setattr(brief,'get_weather_forecast',inner)
    historical=Mock(side_effect=AssertionError('historical power read'))
    monkeypatch.setattr(plan,'_read_historical_context',historical)
    monkeypatch.setattr('modules.telemetry.rootline_daily_advisor.list_policy_review',lambda **_:({'success':True},200))
    for name in ('read_latest_zone_water_balances','_read_recent_irrigation_history',
        '_read_latest_tank_observation','_read_latest_owner_zone_need','_read_managed_device_evidence'):
        monkeypatch.setattr(plan,name,lambda *a,**k:{})
    monkeypatch.setattr(plan,'get_current_water_energy_plan',lambda *a,**k:({'success':False,'status':'missing'},200))
    facts,_,_=plan.read_current_water_energy_evidence(now=NOW,forecast_mode='live_only')
    assert facts['forecast']=={} and facts['forecast_mode']=='live_only'
    assert calls==['power']
    outer.assert_not_called();inner.assert_not_called();historical.assert_not_called()


def test_week_rollover_uses_canonical_operating_date_not_midnight_receipt_date():
    at=datetime.fromisoformat('2026-11-23T00:30:00+02:00')
    zone={'completion_ledger_complete_through':at.isoformat(),'completion_events':[{
        'outcome_id':'overnight','completed_at':'2026-11-23T00:20:00+02:00',
        'operating_date':'2026-11-22','state':'Completed','shutdown_verified':True,
        'verified_runtime_minutes':120,'objective_satisfied':True,'source':'canonical'}]}
    monday=project_weekly_delivery_obligation(zone,now=at,operating_date='2026-11-23')
    assert monday['week_start']=='2026-11-23' and monday['completed_days']==0
    sunday=project_weekly_delivery_obligation(zone,now=at,operating_date='2026-11-22')
    assert sunday['completed_days']==1 and sunday['verified_runtime_minutes']==120
