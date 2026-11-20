import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest import mock
from tests.test_rootline_specialist_result import evidence, NOW
from modules.telemetry import rootline_specialist_result as specialist
from modules.telemetry import rootline_water_energy_plan as plan
from modules.telemetry import power_service as power
from modules.telemetry import weather_service as weather

class ReportingCutoffTests(unittest.TestCase):
    def refresh(self, facts, *, cutoff=NOW):
        stored={}
        def append(value,*args,**kwargs):
            stored.update(value)
            return {"success":True},200
        with mock.patch.object(specialist,'read_current_water_energy_evidence',return_value=(facts,'2026-07-29',NOW)) as reader, mock.patch.object(specialist,'append_water_energy_plan',side_effect=append) as writer, mock.patch.object(specialist,'get_current_water_energy_plan',side_effect=lambda *a,**k:({"success":True,**stored},200)):
            result=specialist.refresh_current_rootline_specialist_result(now=NOW,**({'evidence_cutoff':cutoff} if cutoff is not None else {}))
        return result,writer,reader,stored

    def test_fresh_telemetry_race_rejected_before_append(self):
        facts=evidence();facts['power']['observed_at']=(NOW+timedelta(seconds=1)).isoformat()
        result,writer,_,_=self.refresh(facts)
        self.assertFalse(result['success']);self.assertEqual(result['status'],'scheduled_reassessment_evidence_after_cutoff')
        writer.assert_not_called()

    def test_bounded_past_evidence_retains_useful_report_and_replay(self):
        result,writer,reader,stored=self.refresh(evidence())
        self.assertTrue(result['success']);writer.assert_called_once()
        self.assertEqual(reader.call_args.kwargs['evidence_cutoff'],NOW)
        self.assertEqual(result['evidence']['freshness']['power'],'fresh')
        self.assertTrue(any(row['status']=='Recommend' for row in result['recommendations']))
        replay,_,_,again=self.refresh(evidence())
        self.assertEqual(stored['evidence_sha256'],again['evidence_sha256'])
        self.assertEqual(result['result_id'],replay['result_id'])

    def test_future_nested_observation_and_naive_time_fail_before_append(self):
        for value in ((NOW+timedelta(seconds=1)).isoformat(), '2026-07-29T11:58:00'):
            facts=evidence();facts['fertilizer_batch_observations']=[{'observed_at':value}]
            result,writer,_,_=self.refresh(facts)
            self.assertFalse(result['success']);writer.assert_not_called()

    def test_no_cutoff_preserves_legacy_current_semantics(self):
        facts=evidence();facts['power']['observed_at']=(NOW+timedelta(seconds=1)).isoformat()
        result,writer,reader,_=self.refresh(facts,cutoff=None)
        self.assertTrue(result['success']);writer.assert_called_once()
        self.assertNotIn('evidence_cutoff',reader.call_args.kwargs)

    def test_aware_equivalent_offset_and_future_forecast_target_allowed(self):
        facts=evidence();facts['forecast']['days'][0]['forecast_date']='2026-07-31'
        self.assertIsNone(specialist._reporting_evidence_error(facts,NOW.astimezone(timezone.utc),NOW))

    def test_hold_inputs_preserve_hold(self):
        facts=evidence();facts['weather']['rain_rate_mm_h']=5
        result,writer,_,_=self.refresh(facts)
        self.assertTrue(result['success']);writer.assert_called_once()
        self.assertTrue(any(row['status']=='Hold' for row in result['recommendations']))

    def test_read_only_builder_applies_same_guard(self):
        facts=evidence();facts['tanks']['storage_observed_at']=(NOW+timedelta(seconds=1)).isoformat()
        with mock.patch.object(specialist,'read_current_water_energy_evidence',return_value=(facts,'2026-07-29',NOW)),mock.patch.object(specialist,'append_water_energy_plan') as writer:
            result=specialist.build_current_rootline_specialist_result(now=NOW,evidence_cutoff=NOW)
        self.assertFalse(result['success']);writer.assert_not_called()

    def test_nested_advisor_uses_only_bounded_readers(self):
        calls=[]
        def packet(*args,**kwargs):
            calls.append(kwargs)
            return {'success':True,'source':{},'current':{}},200
        def brief(*args,**kwargs):
            self.assertEqual(set(kwargs['readers']),{'weather_snapshot','forecast','power'})
            for reader in kwargs['readers'].values():reader()
            return {'success':True},200
        def advisor(*args,**kwargs):
            kwargs['brief_reader']()
            return {'zones':[],'current_weather_packet':{},'generated_at':NOW.isoformat()},200
        with mock.patch.object(power,'get_current_power_state',side_effect=packet),mock.patch.object(weather,'get_weather_forecast',side_effect=packet),mock.patch.object(weather,'get_weather_control_snapshot',side_effect=packet),mock.patch('modules.telemetry.rootline_daily_brief.get_rootline_daily_brief',side_effect=brief),mock.patch('modules.telemetry.rootline_daily_advisor.get_rootline_daily_advisor',side_effect=advisor),mock.patch.object(plan,'read_latest_zone_water_balances',return_value={}),mock.patch.object(plan,'_read_historical_context',return_value={}),mock.patch.object(plan,'_read_recent_irrigation_history',return_value={}),mock.patch.object(plan,'_read_latest_tank_observation',return_value={}),mock.patch.object(plan,'_read_latest_owner_zone_need',return_value={}),mock.patch.object(plan,'_read_managed_device_evidence',return_value={}):
            facts,_,_=plan.read_current_water_energy_evidence(now=NOW,evidence_cutoff=NOW)
        self.assertEqual(sum(k.get('as_of')==NOW for k in calls),4)
        self.assertIsNone(specialist._reporting_evidence_error(facts,NOW,NOW))

    def test_gateway_threads_explicit_cutoff_only_into_reporting_builder(self):
        from tests.test_oom_sakkie_automatic_reassessment_scheduler import memory_store, scheduled_payload, NOW as scheduled_now
        from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
        _,schedules=memory_store()
        payload={**scheduled_payload(),'owner_user_id':'42','chat_id':'42','trigger':'declared_time',
            'trigger_id':'REPORTING-CUTOFF-OFFLINE','trigger_timestamp':scheduled_now.isoformat()}
        env={'OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED':'true','OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN':'x'*40,
            'OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS':'42'}
        no_effect={'success':True,'status':'no_active_irrigation','active_execution_found':False,
            'hardware_commands':0,'telegram_sends':0,'writes_farm_data':False}
        with mock.patch.object(specialist,'build_current_rootline_specialist_result',return_value={
                'success':False,'status':'scheduled_reassessment_evidence_after_cutoff'}) as builder, mock.patch('modules.telemetry.rootline_execution_runtime.supervise_rootline_active_execution',return_value=no_effect):
            handle_rootline_reassessment_trigger(payload,{'X-Oom-Sakkie-Telegram-Token':'x'*40},env,
                schedule_store=schedules,state_store=lambda *a:None,scheduler_now=scheduled_now,
                execution_cycle=lambda **k:no_effect,active_supervision_cycle=lambda **k:no_effect,
                equipment_notification_cycle=lambda **k:no_effect,
                family_delivery=lambda *a,**k:(_ for _ in ()).throw(AssertionError('unexpected send')))
        builder.assert_called_once()
        self.assertEqual(builder.call_args.kwargs,{'now':datetime.fromisoformat(payload['evidence_cutoff']),
            'evidence_cutoff':datetime.fromisoformat(payload['evidence_cutoff'])})

    def test_future_legacy_advisor_diagnostics_never_enter_evidence_hash(self):
        from contextlib import ExitStack
        import json
        from modules.telemetry import rootline_daily_brief as brief
        future=(NOW+timedelta(minutes=2)).isoformat()
        power_packet={'success':True,'source':{'last_reading_at':NOW.isoformat(),'stale_after_minutes':15},
            'current':{'battery_soc_pct':75,'solar_power_w':3500,'load_power_w':900}}
        forecast_packet={'success':True,'source':{'last_forecast_run_at':NOW.isoformat(),'stale_after_minutes':360},
            'days':[{'rain_sum_mm':0,'rain_probability_max_pct':10}]}
        weather_packet={'success':True,'source':{'last_reading_at':NOW.isoformat(),'stale_after_minutes':30},
            'current':{'rain_rate_mm_h':0,'rain_today_mm':0,'temperature_c':24,'wind_speed_kmh':8}}
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(power,'get_current_power_state',return_value=(power_packet,200)))
            stack.enter_context(mock.patch.object(weather,'get_weather_forecast',return_value=(forecast_packet,200)))
            stack.enter_context(mock.patch.object(weather,'get_weather_control_snapshot',return_value=({'success':True,'weather_current':weather_packet,'rain_release':{}},200)))
            stack.enter_context(mock.patch('modules.telemetry.rootline_daily_advisor.list_policy_review',return_value=({'success':True},200)))
            for name in ('read_latest_zone_water_balances','_read_historical_context','_read_recent_irrigation_history','_read_latest_tank_observation','_read_latest_owner_zone_need','_read_managed_device_evidence'):
                stack.enter_context(mock.patch.object(plan,name,return_value={}))
            legacy=[stack.enter_context(mock.patch.object(brief,name,return_value=({'success':True,'observed_at':future},200)))
                for name in ('get_weather_today_summary','get_irrigation_status','get_daily_rollup_compare','get_weather_forecast','get_current_power_state')]
            first,date,at=plan.read_current_water_energy_evidence(now=NOW,evidence_cutoff=NOW)
            for reader in legacy:reader.return_value=({'success':True,'observed_at':future,'changed':True},200)
            second,_,_=plan.read_current_water_energy_evidence(now=NOW,evidence_cutoff=NOW)
            for reader in legacy:reader.assert_not_called()
        self.assertNotIn(future,json.dumps(first))
        self.assertEqual(plan.build_water_energy_plan(first,date,now=at)['evidence_sha256'],
            plan.build_water_energy_plan(second,date,now=at)['evidence_sha256'])

if __name__=='__main__':unittest.main()


def _validate_reporting_test_url(url):
    import os
    from psycopg.conninfo import conninfo_to_dict
    target = conninfo_to_dict(url)
    if (set(target) - {'host', 'port', 'user', 'dbname', 'password'}
            or target.get('host') != '127.0.0.1'
            or target.get('user') != 'postgres'
            or target.get('dbname') != 'rootline_reporting_cutoff_20261120'
            or target.get('port') not in {'56439', '5432'}
            or any(os.environ.get(key) for key in
                   ('PGHOSTADDR', 'PGSERVICE', 'PGSERVICEFILE', 'PGOPTIONS'))):
        raise RuntimeError('only the dedicated loopback reporting test database is authorized')
    return url


class ReportingCutoffPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os, psycopg, re
        from pathlib import Path
        cls.url=os.getenv('ROOTLINE_REPORTING_CUTOFF_TEST_URL','')
        if not cls.url:raise unittest.SkipTest('dedicated local reporting database not configured')
        _validate_reporting_test_url(cls.url)
        cls.psycopg=psycopg
        migrations=Path('supabase/migrations')
        names=['202605210001_foundation_migration_log.sql','202605210005_create_telemetry_power_tables.sql',
            '202605220001_create_telemetry_weather_tables.sql','202605230001_create_irrigation_tables.sql',
            '202605230003_create_telemetry_rollup_tables.sql','202607280001_create_rootline_water_energy_plans.sql',
            '202608030001_extend_rootline_fraction_observations.sql']
        with psycopg.connect(cls.url) as c:
            for name in names:
                if name==names[0] or not c.execute('select 1 from app_private.migration_log where migration_id=%s',(name[:-4],)).fetchone():
                    ddl=(migrations/name).read_text(encoding='utf-8')
                    # Local query/persistence proof does not create cluster roles
                    # or claim Supabase permission coverage. Keep schema/functions,
                    # omit deployment-only role grants/revokes in this fixture.
                    ddl=re.sub(r'(?ims)^\s*(?:grant|revoke)\b[^;]+;', '', ddl)
                    c.execute(ddl)
            # Only the columns consumed by these existing readers are needed.
            # Names/types match production; the fixtures create no alternate rail.
            c.execute('create table if not exists sam_live_stock_conversation_review_events (\n                review_event_id text primary key,event_source text,review_json jsonb,created_at timestamptz);\n                create table if not exists irrigation_water_credit_events (\n                credit_id text primary key,credit_json jsonb,created_at timestamptz);')

    def setUp(self):
        with self.psycopg.connect(self.url) as c:
            c.execute('truncate power_readings_5min,power_latest_state,weather_forecast_snapshots,rootline_tank_observations,sam_live_stock_conversation_review_events,irrigation_events,irrigation_water_credit_events,power_daily_rollups,rootline_water_energy_plan_identities,rootline_water_energy_plan_generations cascade')

    def insert_power(self,at,soc,*,ingested=None):
        with self.psycopg.connect(self.url) as c:
            c.execute("insert into power_readings_5min(reading_id,source_id,reading_at,battery_soc_pct,battery_power_w,\n                solar_power_w,load_power_w,grid_power_w,grid_active,generator_active,battery_charging,battery_discharging,ingested_at)\n                values (%s,'sunsynk-main-inverter',%s,%s,-200,3500,900,0,false,false,true,false,%s)",(at.isoformat(),at,soc,ingested or at))

    def insert_forecast(self,source,provider,run,days,*,ingested=None):
        from psycopg.types.json import Jsonb
        with self.psycopg.connect(self.url) as c:
            c.execute("insert into telemetry_sources(source_id,source_type,provider,display_name,stale_after_minutes) values (%s,'forecast',%s,%s,360) on conflict(source_id) do nothing",(source,provider,provider))
            for day,rain in days:
                c.execute('insert into weather_forecast_snapshots(forecast_snapshot_id,source_id,forecast_run_at,forecast_date,offset_days,\n                    rain_sum_mm,rain_probability_max_pct,ingested_at,raw_payload)\n                    values (%s,%s,%s,%s,%s,%s,10,%s,%s)',(source+run.isoformat()+day.isoformat(),source,run,day,max(0,(day-run.date()).days),rain,ingested or run,Jsonb({'provenance':{'provider':provider}})))

    def test_power_uses_prior_history_and_reference_time_not_future_latest(self):
        old=NOW-timedelta(minutes=2);future=NOW+timedelta(seconds=30)
        self.insert_power(old,75);self.insert_power(future,5)
        self.insert_power(NOW-timedelta(minutes=1),9,ingested=future)
        with self.psycopg.connect(self.url) as c:
            c.execute("insert into power_latest_state(source_id,reading_at,battery_soc_pct) values ('sunsynk-main-inverter',%s,5)",(future,))
        packet,status=power.get_current_power_state(database_url=self.url,as_of=NOW)
        self.assertEqual(status,200);self.assertEqual(packet['current']['battery_soc_pct'],75)
        self.assertEqual(packet['source']['data_age_minutes'],2)
        self.assertEqual(packet['current']['battery_state'],'charging')
        self.assertEqual(datetime.fromisoformat(packet['source']['last_reading_at']),old)
        current,_=power.get_current_power_state(database_url=self.url)
        self.assertEqual(current['current']['battery_soc_pct'],5)
        again,_=power.get_current_power_state(database_url=self.url,as_of=NOW.astimezone(timezone.utc))
        self.assertEqual(packet,again)

    def test_forecast_selects_whole_past_provider_run_with_partial_horizon(self):
        day=NOW.date();old=NOW-timedelta(hours=1)
        self.insert_forecast('open-meteo-forecast-main','open_meteo',old,[(day,1),(day+timedelta(days=1),2)])
        self.insert_forecast('weatherapi-forecast-main','weatherapi',NOW+timedelta(seconds=1),[(day,99),(day+timedelta(days=2),99)])
        self.insert_forecast('weatherapi-forecast-main','weatherapi',NOW-timedelta(seconds=1),[(day,88)],ingested=NOW+timedelta(seconds=1))
        packet,status=weather.get_weather_forecast(3,database_url=self.url,as_of=NOW)
        self.assertEqual(status,200);self.assertEqual(packet['source']['provider'],'open_meteo')
        self.assertEqual([d['rain_sum_mm'] for d in packet['days']],[1,2])
        self.assertFalse(packet['window']['complete_requested_horizon']);self.assertTrue(packet['window']['covers_today'])
        self.assertEqual(packet['source']['data_age_minutes'],60)

    def test_forecast_sast_midnight_does_not_use_wall_clock_day_or_stitch(self):
        cutoff=datetime.fromisoformat('2026-07-29T22:01:00+00:00')
        day=cutoff.astimezone(plan.ZA_TZ).date()
        self.insert_forecast('open-meteo-forecast-main','open_meteo',cutoff-timedelta(minutes=2),[(day-timedelta(days=1),7),(day,3)])
        self.insert_forecast('weatherapi-forecast-main','weatherapi',cutoff-timedelta(minutes=1),[(day+timedelta(days=1),99)])
        packet,status=weather.get_weather_forecast(3,database_url=self.url,as_of=cutoff)
        self.assertEqual(status,200);self.assertEqual(packet['source']['provider'],'open_meteo')
        self.assertEqual([d['forecast_date'] for d in packet['days']],[day.isoformat()])
        self.assertTrue(packet['window']['covers_today'])
        self.assertEqual(packet['window']['returned_days'],1)

    def test_tanks_keep_independent_prior_observations(self):
        with self.psycopg.connect(self.url) as c:
            for i,(storage,reservoir,at) in enumerate([(4,None,NOW-timedelta(minutes=4)),(None,8,NOW-timedelta(minutes=3)),(0,0,NOW+timedelta(seconds=30))]):
                c.execute("insert into rootline_tank_observations(observation_id,idempotency_key,storage_reported_count,reservoir_reported_count,\n                    observed_at,recorded_at,reporter_identity,source) values (%s,%s,%s,%s,%s,%s,'owner','oom_sakkie_owner')",('ROOTLINE-TANK-'+f'{i:024X}',str(i),storage,reservoir,at,at))
        selected=plan._read_latest_tank_observation(self.url,evidence_cutoff=NOW)
        self.assertEqual(selected['storage_reported_count'],4);self.assertEqual(selected['reservoir_reported_count'],8)
        self.assertNotEqual(selected['storage_observed_at'],selected['reservoir_observed_at'])
        self.assertEqual(plan._read_latest_tank_observation(self.url)['storage_reported_count'],0)

    def test_owner_need_selects_earlier_eligible_provider_time(self):
        from psycopg.types.json import Jsonb
        with self.psycopg.connect(self.url) as c:
            for i,(zone,observed,created) in enumerate([('B12345',NOW-timedelta(minutes=2),NOW-timedelta(minutes=2)),('C12345',NOW+timedelta(seconds=30),NOW-timedelta(seconds=1)),('E12345',NOW,NOW+timedelta(seconds=30))]):
                payload={'rootline_operational_intake':{'state':'completed','outcome':{'visible_irrigation_need_zone':zone,'writes_farm_data':True,'provider_timestamp':observed.isoformat(),'provider_message_id':str(i)}}}
                c.execute('insert into sam_live_stock_conversation_review_events values (%s,%s,%s,%s)',(str(i),'oom_sakkie_rootline_operational_intake',Jsonb(payload),created))
        selected=plan._read_latest_owner_zone_need(self.url,NOW,evidence_cutoff=NOW)
        self.assertEqual(selected['zone_id'],'B12345');self.assertEqual(selected['provider_message_id'],'0')

    def test_managed_history_and_credits_exclude_post_cutoff_rows(self):
        from psycopg.types.json import Jsonb
        from modules.telemetry import rootline_irrigation_history as history
        from modules.telemetry import rootline_water_credit as credit
        with self.psycopg.connect(self.url) as c:
            for i,at in enumerate([NOW-timedelta(seconds=1),NOW+timedelta(seconds=1)]):
                payload={'action':'record_auxiliary_completed','auxiliary_device_id':'FERTILIZER-MIXER-CH2','execution_id':str(i),'recorded_at':at.isoformat()}
                c.execute('insert into sam_live_stock_conversation_review_events values (%s,%s,%s,%s)',(str(i),'rootline_irrigation_execution',Jsonb({'rootline_execution':payload}),at))
                c.execute('insert into irrigation_water_credit_events values (%s,%s,%s)',(str(i),Jsonb({'fixture_identity':i}),at))
        managed=plan._read_managed_device_evidence(self.url,NOW,evidence_cutoff=NOW)
        self.assertEqual([row['execution_id'] for row in managed['fertilizer_executions']],['0'])
        with mock.patch.object(credit,'project_water_credits',return_value={'credits':[],'by_execution':{}}) as project:
            result=history.read_canonical_irrigation_history(self.url,now=NOW,evidence_cutoff=NOW)
        self.assertEqual(result['status'],'Available');self.assertEqual(project.call_args.args[0],[{'fixture_identity':0}])

    def test_future_rejected_without_canonical_generation_then_past_appends(self):
        facts=evidence();facts['power']['observed_at']=(NOW+timedelta(seconds=1)).isoformat()
        with mock.patch.object(specialist,'read_current_water_energy_evidence',return_value=(facts,'2026-07-29',NOW)):
            result=specialist.refresh_current_rootline_specialist_result(now=NOW,evidence_cutoff=NOW,database_url=self.url)
        self.assertFalse(result['success'])
        with self.psycopg.connect(self.url) as c:self.assertEqual(c.execute('select count(*) from rootline_water_energy_plan_generations').fetchone()[0],0)
        with mock.patch.object(specialist,'read_current_water_energy_evidence',return_value=(evidence(),'2026-07-29',NOW)):
            first=specialist.refresh_current_rootline_specialist_result(now=NOW,evidence_cutoff=NOW,database_url=self.url)
            second=specialist.refresh_current_rootline_specialist_result(now=NOW,evidence_cutoff=NOW,database_url=self.url)
        self.assertTrue(first['success']);self.assertEqual(first['canonical_plan'],second['canonical_plan'])
        with self.psycopg.connect(self.url) as c:self.assertEqual(c.execute('select count(*) from rootline_water_energy_plan_generations').fetchone()[0],1)

    def test_reporting_race_retains_prior_power_and_same_canonical_generation(self):
        old=NOW-timedelta(minutes=2)
        self.insert_power(old,75)
        def load(**kwargs):
            packet,_=power.get_current_power_state(database_url=self.url,as_of=kwargs['evidence_cutoff'])
            facts=evidence();facts['power']=plan._normalize_power(packet)
            return facts,'2026-07-29',NOW
        with mock.patch.object(specialist,'read_current_water_energy_evidence',side_effect=load):
            before=specialist.refresh_current_rootline_specialist_result(now=NOW,evidence_cutoff=NOW,database_url=self.url)
            self.insert_power(NOW+timedelta(seconds=30),5)
            after=specialist.refresh_current_rootline_specialist_result(now=NOW,evidence_cutoff=NOW,database_url=self.url)
        self.assertTrue(before['success']);self.assertTrue(after['success'])
        self.assertEqual(before['canonical_plan'],after['canonical_plan'])
        self.assertEqual(before['result_id'],after['result_id'])

    def test_historical_rollups_exclude_current_day_and_later_revisions(self):
        with self.psycopg.connect(self.url) as c:
            for i,(day,updated) in enumerate([(NOW.date()-timedelta(days=2),NOW-timedelta(hours=1)),(NOW.date()-timedelta(days=1),NOW+timedelta(seconds=1)),(NOW.date(),NOW-timedelta(hours=1))]):
                c.execute("insert into power_daily_rollups(rollup_id,source_id,rollup_date,source_window_end,coverage_pct,generated_at,updated_at) values (%s,'sunsynk-main-inverter',%s,%s,100,%s,%s)",(str(i),day,NOW-timedelta(hours=1),updated,updated))
        past=plan._read_historical_context(self.url,evidence_cutoff=NOW)
        self.assertEqual(past['daily_rollup_count'],1)
        self.assertEqual(past['current_day'],'Unavailable')
        self.assertEqual(plan._read_historical_context(self.url)['daily_rollup_count'],3)
