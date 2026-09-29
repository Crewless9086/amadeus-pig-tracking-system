"""Disposable PostgreSQL qualification of offline renderer; synthetic approval only."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import os
import unittest
from unittest.mock import patch
import time
from urllib.parse import parse_qsl, urlsplit

import psycopg
from scripts import render_oom_desktop_registration_sql as prototype
from tests import test_oom_desktop_candidate_reconciliation as f
a = prototype.adapter


class OfflineTests(unittest.TestCase):
    def test_real_source_verification_is_not_disabled_by_renderer(self):
        args = f.arguments()
        with patch.object(a, 'verify_source_and_candidate', side_effect=ValueError('required_source_gate')) as check:
            with self.assertRaisesRegex(ValueError,'required_source_gate'):
                prototype.capture_plan(args, authenticated_owner_principal=f.OWNER,
                    authenticated_desktop_principal=f.PRINCIPAL)
        check.assert_called_once()

    def test_principal_mismatch_fails_before_source_or_capture(self):
        with patch.object(a, 'verify_source_and_candidate') as check:
            with self.assertRaisesRegex(a.ReconciliationError,'independent_authentication_required'):
                prototype.capture_plan(f.arguments(), authenticated_owner_principal='not-owner',
                    authenticated_desktop_principal=f.PRINCIPAL)
        check.assert_not_called()

    def test_literal_delimiter_and_dollar_text_cannot_escape_payload(self):
        value = {'text': "$registration_payload_0$'); COMMIT; -- \\ '"}
        literal = prototype._literal(value)
        self.assertTrue(literal.startswith('$registration_payload_1$'))
        self.assertEqual(literal.count('$registration_payload_1$'),2)
        rendered=prototype.render_sql({'text':'$bounded_registration$ $bounded_registration_0$ __PINNED_PACKAGE__'})
        self.assertIn('DO $bounded_registration_1$',rendered)
        self.assertEqual(rendered.count('$bounded_registration_1$'),2)
        self.assertIn('__PINNED_PACKAGE__',rendered)

    def test_capture_protocol_rejects_sql_changes_and_never_imports_fixtures(self):
        plan=a.prepare_reconciliation(**f.arguments())
        db=prototype.CaptureDB(plan)
        cursor=db.cursor()
        for sql in ('delete from public.charlie_missions',
                    'select to_jsonb(m) from public.charlie_missions m where mission_id=%s or true',
                    'update public.charlie_missions set metadata_json=%(metadata)s::jsonb,updated_at=now() where true'):
            with self.subTest(sql=sql),self.assertRaisesRegex(ValueError,'capture_unknown_sql'):
                cursor.execute(sql,{'mission_id':a.MISSION_ID})
        self.assertEqual(db.writes,[])
        self.assertNotIn('fixture',prototype.CaptureDB.__bases__[0].__module__)
        self.assertEqual(prototype.CaptureDB.__bases__,(object,))


class DashboardPostgresTests(f.ReconciliationPostgresTests):
    @classmethod
    def setUpClass(cls):
        # The qualification runner must provision and explicitly name its local
        # disposable database. Never discover a production connection or create one.
        parsed=urlsplit(os.getenv('OOM_DESKTOP_REBIND_TEST_DATABASE_URL',''))
        if parsed.hostname not in {'localhost','127.0.0.1'} or not parsed.path.startswith('/oom_desktop_rebind_test'):
            raise ValueError('explicit_local_disposable_postgres_required')
        if parsed.fragment or any(k not in {'sslmode','connect_timeout'} for k,v in parse_qsl(parsed.query)):
            raise ValueError('disposable_connection_override_refused')
        if any(os.environ.get(k) for k in ('PGHOSTADDR','PGSERVICE','PGSERVICEFILE','PGOPTIONS')):
            raise ValueError('ambient_connection_override_refused')
        super().setUpClass()
        with cls.pg.connect(cls.url) as db:
            db.execute('''create table if not exists public.charlie_owner_execution_hold_events(
                event_id text primary key,mission_id text,event_type text,release_of_event_id text)''')

    def setUp(self):
        super().setUp()
        with self.pg.connect(self.url) as db:
            db.execute('delete from public.charlie_owner_execution_hold_events')
        with patch.object(a, 'verify_source_and_candidate'):
            self.package = prototype.capture_plan(self.args, authenticated_owner_principal=f.OWNER,
                authenticated_desktop_principal=f.PRINCIPAL)
        self.compact = self.compact_for(self.package)
        self.sql = prototype.render_sql(self.compact)

    def compact_for(self, package):
        with self.pg.connect(self.url) as db:
            hashes = {k:db.execute("select encode(sha256(convert_to(%s::jsonb::text,'UTF8')),'hex')",
                (json.dumps(package['plan']['manifest']['expected_'+k+'_record']),)).fetchone()[0] for k in ('parent','child')}
        return prototype.compact_package(package, expected_parent_pg_sha256=hashes['parent'],expected_child_pg_sha256=hashes['child'])

    def run_sql(self, sql=None):
        result = None
        with self.pg.connect(self.url, autocommit=True) as db:
            cur = db.execute(sql or self.sql, prepare=False)
            while True:
                if cur.description:
                    result = cur.fetchone()[0]
                if not cur.nextset():
                    break
        return result

    def fail_unchanged(self, sql, reason):
        before = self.snapshot()
        with self.assertRaisesRegex(psycopg.Error, reason):
            self.run_sql(sql)
        self.assertEqual(before, self.snapshot())

    def test_dashboard_five_writes_and_exact_zero_write_replay(self):
        before = self.snapshot()
        self.assertEqual(self.run_sql()['writes'],5)
        applied = self.snapshot()
        self.assertEqual(self.run_sql()['writes'],0)
        self.assertEqual(applied,self.snapshot())
        parent_before = [row for row in before[0] if row[0]['mission_id']==a.PARENT_ID]
        self.assertEqual(parent_before,[row for row in applied[0] if row[0]['mission_id']==a.PARENT_ID])
        self.assertEqual(len(applied[1])-len(before[1]),2)
        self.assertEqual(len(applied[2])-len(before[2]),1)

    def test_dashboard_payloads_match_original_python_semantics(self):
        initial = self.snapshot()
        self.run_sql()
        sql_state = self.snapshot()
        with self.pg.connect(self.url) as db:
            db.execute('delete from public.operational_events')
            db.execute('delete from public.charlie_mission_events')
            db.execute('delete from public.charlie_missions')
            for row in initial[0]:db.execute('insert into public.charlie_missions select * from jsonb_populate_record(NULL::public.charlie_missions,%s::jsonb)',(json.dumps(row[0]),))
            for row in initial[1]:db.execute('insert into public.charlie_mission_events select * from jsonb_populate_record(NULL::public.charlie_mission_events,%s::jsonb)',(json.dumps(row[0]),))
        self.assertEqual(f.apply(self.args,self.connect)['writes'],5)
        python_state = self.snapshot()
        def normalized(x):
            if isinstance(x,dict):
                return {k:normalized(v) for k,v in x.items() if k not in {'updated_at','created_at','recorded_at','occurred_at','freshness_at'}}
            if isinstance(x,(tuple,list)):return [normalized(v) for v in x]
            return x
        self.assertEqual(normalized(sql_state),normalized(python_state))

    def test_dashboard_stale_parent_refuses(self):
        with self.pg.connect(self.url) as db: db.execute('update public.charlie_missions set title=%s where mission_id=%s',('changed',a.PARENT_ID))
        self.fail_unchanged(self.sql,'parent_state_changed')

    def test_dashboard_stale_child_refuses(self):
        with self.pg.connect(self.url) as db: db.execute("update public.charlie_missions set metadata_json=metadata_json || '{\"other\":true}'::jsonb where mission_id=%s",(a.MISSION_ID,))
        self.fail_unchanged(self.sql,'predecessor_state_changed')

    def test_dashboard_stale_correction_refuses(self):
        with self.pg.connect(self.url) as db: db.execute("update public.charlie_mission_events set recorded_by='changed'")
        self.fail_unchanged(self.sql,'predecessor_correction_changed')

    def test_dashboard_expiry_refuses(self):
        package=deepcopy(self.package)
        package['plan']['approval']['expires_at']=(f.NOW-timedelta(seconds=1)).isoformat()
        package['plan']['manifest']['expires_at']=package['plan']['approval']['expires_at']
        self.fail_unchanged(prototype.render_sql(self.compact_for(package)),'approval_expired_under_lock')

    def test_dashboard_active_hold_refuses(self):
        with self.pg.connect(self.url) as db: db.execute("insert into public.charlie_owner_execution_hold_events values('hold',%s,'hold_created',NULL)",(a.MISSION_ID,))
        self.fail_unchanged(self.sql,'owner_execution_hold_active')

    def test_dashboard_partial_audit_refuses(self):
        correction=self.package['correction']
        with self.pg.connect(self.url) as db:
            db.execute("insert into public.charlie_mission_events(event_id,mission_id,event_type,recorded_by,metadata_json,created_at) values(%s,%s,'finding_recorded',%s,%s::jsonb,now()-interval '1 day')",
                (correction['event_id'],a.MISSION_ID,f.OWNER,json.dumps(correction)))
        self.fail_unchanged(self.sql,'partial_audit_conflict')

    def test_dashboard_final_write_failure_rolls_back_all_five(self):
        with self.pg.connect(self.url) as db: db.execute("alter table public.charlie_mission_events add constraint reject_oom_rebind_history check(event_type<>'workflow_updated')")
        self.fail_unchanged(self.sql,'reject_oom_rebind_history')

    def test_dashboard_missing_operational_audit_refuses_replay(self):
        self.run_sql()
        with self.pg.connect(self.url) as db: db.execute('delete from public.operational_events')
        self.fail_unchanged(self.sql,'replay_operational_audit_conflict')

    def test_dashboard_empty_admission_refuses_replay(self):
        self.run_sql()
        with self.pg.connect(self.url) as db: db.execute("update public.charlie_missions set metadata_json=jsonb_set(metadata_json,'{mission_admission}','{}') where mission_id=%s",(a.MISSION_ID,))
        self.fail_unchanged(self.sql,'replay_admission_conflict')

    def test_dashboard_wrong_candidate_signed_receipt_refuses_replay(self):
        self.run_sql()
        changed={'mission_id':a.MISSION_ID,'root_mission_id':a.PARENT_ID,'generation':self.package['plan']['manifest']['generation'],
            'base_sha':a.BASE,'head_sha':'0'*40,'signed_receipt':{}}
        with self.pg.connect(self.url) as db: db.execute("update public.charlie_missions set metadata_json=jsonb_set(metadata_json,'{mission_admission}',%s::jsonb) where mission_id=%s",(json.dumps(changed),a.MISSION_ID))
        self.fail_unchanged(self.sql,'replay_admission_conflict')

    def test_dashboard_replay_metadata_drift_refuses(self):
        self.run_sql()
        with self.pg.connect(self.url) as db: db.execute("update public.charlie_missions set metadata_json=metadata_json || '{\"unreviewed\":true}'::jsonb where mission_id=%s",(a.MISSION_ID,))
        self.fail_unchanged(self.sql,'replay_binding_conflict')

    def test_dashboard_concurrent_same_package_one_apply_one_replay(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.run_sql(),range(2)))
        self.assertEqual(sorted(r['writes'] for r in results),[0,5])
        with self.pg.connect(self.url) as db:
            self.assertEqual(db.execute('select count(*) from public.operational_events').fetchone()[0],1)

    def test_compact_matches_full_payload_and_stays_small(self):
        self.assertNotIn('expected_child_record',self.compact['plan']['manifest'])
        self.assertNotIn('expected_parent_record',self.compact['plan']['manifest'])
        self.assertNotIn('payload_json',self.compact['operational_row'])
        self.assertEqual(set(self.compact['invalidation_changes']),{'status','invalidated_by_correction_event_id','correction_digest','replacement_generation'})
        self.assertLess(len(self.sql.encode()),len(prototype.render_sql(self.package).encode()))
        self.run_sql()
        before=self.snapshot()
        self.assertEqual(self.run_sql(prototype.render_sql(self.package))['writes'],0)
        self.assertEqual(before,self.snapshot())

    def test_compact_preimage_hash_drift_refuses(self):
        for key in ('expected_parent_pg_sha256','expected_child_pg_sha256'):
            p=deepcopy(self.compact);p[key]='0'*64
            self.fail_unchanged(prototype.render_sql(p),'state_changed')

    def test_compact_immutable_history_previous_row_drift_refuses(self):
        self.run_sql()
        with self.pg.connect(self.url) as db:
            db.execute("update public.charlie_mission_events set metadata_json=jsonb_set(metadata_json,'{previous_record,title}','\"changed\"') where event_type='workflow_updated'")
        self.fail_unchanged(self.sql,'predecessor_state_changed')

    def test_dashboard_server_expiry_rechecked_after_lock_delay(self):
        p=deepcopy(self.compact)
        cutoff=prototype.datetime.now(prototype.timezone.utc)+timedelta(seconds=1)
        p['plan']['approval']['expires_at']=cutoff.isoformat()
        p['plan']['manifest']['expires_at']=cutoff.isoformat()
        before=self.snapshot()
        with self.pg.connect(self.url) as holder:
            holder.execute('select pg_advisory_xact_lock(hashtextextended(%s,0))',(a.PARENT_ID,))
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.run_sql,prototype.render_sql(p))
                time.sleep(1.2)
                holder.commit()
                with self.assertRaisesRegex(psycopg.Error,'approval_expired_under_lock'):future.result()
        self.assertEqual(before,self.snapshot())

    def test_dashboard_concurrent_hold_is_seen_after_wait(self):
        before=self.snapshot()
        with self.pg.connect(self.url) as holder:
            holder.execute('select pg_advisory_xact_lock(hashtextextended(%s,0))',(a.PARENT_ID,))
            holder.execute("insert into public.charlie_owner_execution_hold_events values('concurrent-hold',%s,'hold_created',NULL)",(a.PARENT_ID,))
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.run_sql)
                time.sleep(.25)
                holder.commit()
                with self.assertRaisesRegex(psycopg.Error,'owner_execution_hold_active'):future.result()
        self.assertEqual(before,self.snapshot())

    def test_dashboard_protected_issuer_then_zero_write_replay(self):
        rendered={}
        def dashboard_apply(args,connect):
            key=args['expected_manifest_sha256']
            if key not in rendered:
                with patch.object(a,'verify_source_and_candidate'):
                    package=prototype.capture_plan(args,authenticated_owner_principal=f.OWNER,
                        authenticated_desktop_principal=f.PRINCIPAL)
                rendered[key]=prototype.render_sql(self.compact_for(package))
            return self.run_sql(rendered[key])
        with patch.object(f,'apply',side_effect=dashboard_apply):
            f.issuer_chain(self,self.connect,self.snapshot)

    def test_dashboard_each_write_failure_rolls_back(self):
        failure_specs=[
            ('charlie_mission_events',"event_type<>'owner_correction_recorded'",True),
            ('operational_events',"event_type<>'mission_admission_invalidated'",False),
            ('charlie_missions',"metadata_json->'mission_admission'->>'status'<>'invalidated'",False),
            ('charlie_missions',"metadata_json->'review_packet'->>'pr_number'<>'"+str(a.CANDIDATE_PR)+"'",False)]
        for table,condition,not_valid in failure_specs:
            with self.subTest(table=table,condition=condition):
                with self.pg.connect(self.url) as db:
                    db.execute('alter table public.'+table+' add constraint injected_write_failure check('+condition+')'+(' not valid' if not_valid else ''))
                try:self.fail_unchanged(self.sql,'injected_write_failure')
                finally:
                    with self.pg.connect(self.url) as db:db.execute('alter table public.'+table+' drop constraint injected_write_failure')

    def test_large_preimages_and_receipt_stay_compact_without_audit_truncation(self):
        with self.pg.connect(self.url) as db:
            for mid,n in ((a.PARENT_ID,75000),(a.MISSION_ID,65000)):
                db.execute("update public.charlie_missions set metadata_json=metadata_json || %s::jsonb where mission_id=%s",
                    (json.dumps({'large_preserved_fixture':'x'*n}),mid))
            db.execute("update public.charlie_missions set metadata_json=jsonb_set(metadata_json,'{mission_admission,large_signed_fixture}',%s::jsonb) where mission_id=%s",
                (json.dumps('s'*30000),a.MISSION_ID))
        rows=f.read_records(self.connect)
        args=f.arguments(rows[a.MISSION_ID],rows[a.PARENT_ID],self.package['plan']['manifest']['expected_correction']['metadata'])
        with patch.object(a,'verify_source_and_candidate'):
            package=prototype.capture_plan(args,authenticated_owner_principal=f.OWNER,authenticated_desktop_principal=f.PRINCIPAL)
        full=prototype.render_sql(package);compact=prototype.render_sql(self.compact_for(package))
        self.assertGreater(len(full.encode()),600000)
        self.assertLess(len(compact.encode()),80000)
        self.assertEqual(self.run_sql(compact)['writes'],5)
        with self.pg.connect(self.url) as db:
            stored=db.execute("select metadata_json from public.charlie_mission_events where event_type='workflow_updated'").fetchone()[0]
        self.assertEqual(stored,package['history'])
        self.assertEqual(len(stored['previous_record']['metadata_json']['large_preserved_fixture']),65000)
        self.assertEqual(len(stored['invalidated_admission']['large_signed_fixture']),30000)
        self.assertEqual(self.run_sql(compact)['writes'],0)

    def test_outer_do_delimiter_in_owner_text_remains_data(self):
        m,approval=json.loads(self.args['manifest_bytes']),json.loads(self.args['approval_bytes'])
        payload="$bounded_registration$; DELETE FROM public.charlie_missions; DO $bounded_registration_0$ __PINNED_PACKAGE__ $registration_payload_0$"
        approval['instruction_text']=payload
        args=f.encode(m,approval)
        with patch.object(a,'verify_source_and_candidate'):
            package=prototype.capture_plan(args,authenticated_owner_principal=f.OWNER,authenticated_desktop_principal=f.PRINCIPAL)
        sql=prototype.render_sql(self.compact_for(package))
        self.assertIn('DO $bounded_registration_1$',sql)
        self.assertEqual(self.run_sql(sql)['writes'],5)
        with self.pg.connect(self.url) as db:
            self.assertEqual(db.execute('select count(*) from public.charlie_missions').fetchone()[0],2)
            self.assertEqual(db.execute("select notes from public.charlie_mission_events where event_type='owner_correction_recorded' order by created_at desc limit 1").fetchone()[0],payload)
        self.assertEqual(self.run_sql(sql)['writes'],0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
