"""Separate pending capture and optional local disposable PostgreSQL qualification."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
import os
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qsl
import zlib
from scripts import reconcile_rootline_pending_registration as pending
from scripts import render_oom_desktop_registration_sql as renderer
from tests import test_rootline_pending_registration as f


def capture(m,a):
    with patch.object(pending,'verify_source_and_candidate'):
        return renderer.capture_pending_plan(f.encoded(m,a),authenticated_owner_principal=f.OWNER,
            authenticated_desktop_principal=f.PRINCIPAL)


class OfflineTests(unittest.TestCase):
    def setUp(self):self.m,self.a,self.db=f.fixture()
    def test_capture_three_writes_without_operations_or_invalidation(self):
        p=capture(self.m,self.a)
        self.assertEqual(p['original_helper_writes'],3)
        self.assertEqual(p['updated_metadata']['mission_admission'],self.m['expected_child_record']['metadata_json']['mission_admission'])
        self.assertEqual(renderer.CaptureDB.__bases__,(object,))
        self.assertEqual(renderer.PendingCaptureDB.__bases__,(renderer.CaptureDB,))
    def test_real_source_gate_and_owner_auth_are_not_skipped(self):
        with patch.object(pending,'verify_source_and_candidate',side_effect=ValueError('source_required')):
            with self.assertRaisesRegex(ValueError,'source_required'):
                renderer.capture_pending_plan(f.encoded(self.m,self.a),authenticated_owner_principal=f.OWNER,authenticated_desktop_principal=f.PRINCIPAL)
        with patch.object(pending,'verify_source_and_candidate') as gate:
            with self.assertRaisesRegex(pending.ReconciliationError,'independent_authentication_required'):
                renderer.capture_pending_plan(f.encoded(self.m,self.a),authenticated_owner_principal='wrong',authenticated_desktop_principal=f.PRINCIPAL)
            gate.assert_not_called()
    def test_closed_capture_refuses_old_invalidation_and_arbitrary_sql(self):
        c=renderer.PendingCaptureDB(pending.prepare_pending_succession(**f.encoded(self.m,self.a))).cursor()
        for sql in ('delete from public.charlie_missions',
                    'update public.charlie_missions set metadata_json=%(metadata)s::jsonb,updated_at=now() where mission_id=%(mission_id)s'):
            with self.assertRaisesRegex(ValueError,'pending_capture_unknown_sql'):c.execute(sql,{})
    def test_render_refuses_postimage_or_shape_tampering(self):
        p=capture(self.m,self.a)
        for key in ('shape','original_helper_writes','history_notes','history','updated_metadata'):
            altered=deepcopy(p);altered[key]='wrong'
            with self.subTest(key=key),self.assertRaises((ValueError,TypeError,KeyError)):renderer.render_pending_sql(altered)
    def test_compact_roundtrip_and_transfer_limits(self):
        p=capture(self.m,self.a)
        hashes={'expected_parent_pg_sha256':'a'*64,'expected_child_pg_sha256':'b'*64,'expected_registration_pg_sha256':'c'*64}
        compact=renderer.compact_pending_package(p,**hashes)
        self.assertNotIn('expected_child_record',compact['plan']['manifest'])
        self.assertNotIn('metadata',compact['plan']['manifest']['expected_registration'])
        # Model the SQL's reconstruction with the exact canonical rows, not a valid-receipt fiction.
        restored=deepcopy(compact);m=restored['plan']['manifest']
        for k in ('expected_child_record','expected_parent_record'):m[k]=deepcopy(p['plan']['manifest'][k])
        m['expected_registration']['metadata']=deepcopy(p['plan']['manifest']['expected_registration']['metadata'])
        bindings={**restored.pop('binding_changes'),'mission_admission_contract':m['contract']}
        updated={**m['expected_child_record']['metadata_json'],**bindings,'mission_control_projection':restored.pop('projection')}
        restored['updated_metadata']=updated
        restored['history']={'version':pending.VERSION,'manifest':m,'approval':restored['plan']['approval'],
            'manifest_sha256':restored['plan']['manifest_sha256'],'approval_sha256':restored['plan']['approval_sha256'],
            'previous_record':m['expected_child_record'],'parent_record':m['expected_parent_record'],
            'preserved_admission':m['expected_child_record']['metadata_json']['mission_admission'],
            'correction':restored['correction'],'bindings':bindings,'updated_metadata':updated}
        for k in hashes:restored.pop(k)
        self.assertEqual(restored,p)
        raw=renderer.render_pending_sql(p,**hashes).encode();compressed=zlib.compress(raw,9)
        self.assertLessEqual(len(raw),131072);self.assertLessEqual(len(compressed),65536)
        self.assertEqual(zlib.decompress(compressed),raw)
        self.assertNotIn('INSERT INTO public.operational_events',raw.decode())
    def test_literal_delimiters_do_not_escape_owner_text(self):
        self.a['instruction_text']="SYNTHETIC $pending_registration_0$ $registration_payload_0$ ' ; COMMIT; --"
        p=capture(self.m,self.a)
        rendered=renderer.render_pending_sql(p)
        self.assertIn('DO $pending_registration_1$',rendered)
        self.assertEqual(rendered.count('$pending_registration_1$'),2)


@unittest.skipUnless(os.environ.get('OOM_DESKTOP_REBIND_TEST_DATABASE_URL'),'explicit disposable Postgres not supplied')
class PendingPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.pg=psycopg;cls.url=os.environ['OOM_DESKTOP_REBIND_TEST_DATABASE_URL'];url=urlsplit(cls.url)
        if url.hostname not in {'localhost','127.0.0.1'} or not url.path.startswith('/oom_desktop_rebind_test') or url.fragment or any(k not in {'sslmode','connect_timeout'} for k,v in parse_qsl(url.query)):
            raise ValueError('explicit_local_disposable_postgres_required')
        if any(os.environ.get(k) for k in ('PGHOSTADDR','PGSERVICE','PGSERVICEFILE','PGOPTIONS')):raise ValueError('ambient_connection_override_refused')
        f.old.ReconciliationPostgresTests.setUpClass.__func__(cls)
        with cls.pg.connect(cls.url) as db:
            db.execute('create table if not exists public.charlie_owner_execution_hold_events(event_id text primary key,mission_id text,event_type text,release_of_event_id text)')
    def setUp(self):
        f.old.ReconciliationPostgresTests.setUp(self)
        with self.pg.connect(self.url) as db:
            db.execute('delete from public.charlie_owner_execution_hold_events')
            child=db.execute('select to_jsonb(m) from public.charlie_missions m where mission_id=%s',(pending.MISSION_ID,)).fetchone()[0]
            parent=db.execute('select to_jsonb(m) from public.charlie_missions m where mission_id=%s',(pending.PARENT_ID,)).fetchone()[0]
            # Use only the structural synthetic receipt from the in-memory production-shaped fixture.
            _,_,memory=f.fixture()
            historic=next(v[0] for v in memory.events.values() if v[2]=='workflow_updated')
            child['metadata_json']['mission_admission']=deepcopy(historic['previous_record']['metadata_json']['mission_admission'])
            db.execute('update public.charlie_missions set metadata_json=%s::jsonb where mission_id=%s',(json.dumps(child['metadata_json']),pending.MISSION_ID))
            child=db.execute('select to_jsonb(m) from public.charlie_missions m where mission_id=%s',(pending.MISSION_ID,)).fetchone()[0]
        args=f.old.arguments(child,parent)
        f.old.apply(args,lambda _:self.pg.connect(self.url))
        prior_id=f.ordinary.prepare_reconciliation(**args)['event_id']
        with self.pg.connect(self.url) as db:
            rows={mid:db.execute('select to_jsonb(m) from public.charlie_missions m where mission_id=%s',(mid,)).fetchone()[0] for mid in (pending.MISSION_ID,pending.PARENT_ID)}
            history,actor,kind=db.execute('select metadata_json,recorded_by,event_type from public.charlie_mission_events where event_id=%s',(prior_id,)).fetchone()
        memory.rows=rows;memory.events={prior_id:(history,actor,kind)}
        self.m,self.a,_=f.arguments_from_history(memory,prior_id)
        self.package=capture(self.m,self.a)
        with self.pg.connect(self.url) as db:
            self.hashes={name:db.execute("select encode(sha256(convert_to(%s::jsonb::text,'UTF8')),'hex')",(json.dumps(value),)).fetchone()[0] for name,value in (
                ('expected_parent_pg_sha256',self.m['expected_parent_record']),('expected_child_pg_sha256',self.m['expected_child_record']),
                ('expected_registration_pg_sha256',self.m['expected_registration']['metadata']))}
        self.sql=renderer.render_pending_sql(self.package,**self.hashes)
    def snapshot(self):return f.old.ReconciliationPostgresTests.snapshot(self)
    def run_sql(self,sql=None):
        result=None
        with self.pg.connect(self.url,autocommit=True) as db:
            cursor=db.execute(sql or self.sql,prepare=False)
            while True:
                if cursor.description:result=cursor.fetchone()[0]
                if not cursor.nextset():break
        return result
    def test_three_writes_and_exact_zero_write_replay(self):
        before=self.snapshot();self.assertEqual(self.run_sql()['writes'],3);after=self.snapshot()
        self.assertEqual(len(after[1])-len(before[1]),2);self.assertEqual(before[2],after[2])
        self.assertEqual(self.run_sql()['writes'],0);self.assertEqual(self.snapshot(),after)
    def test_protected_rootline_issuer_callback_check_and_admitted_replay(self):
        connect=lambda _:self.pg.connect(self.url)
        # Match the existing issuer fixture's synthetic Git diff without masking
        # persisted paths, current authority, callback or canonical receipt writes.
        self.m['candidate']['diff_sha256']=f.old.canonical_candidate_diff(pending.PATHS,b'synthetic candidate diff')
        self.package=capture(self.m,self.a)
        self.sql=renderer.render_pending_sql(self.package,**self.hashes)
        original=deepcopy(self.m['expected_child_record']['metadata_json']['mission_admission'])
        self.assertEqual(original['status'],'invalidated')
        self.assertEqual(self.run_sql()['writes'],3)
        self.assertEqual(f.old.mission(connect)['metadata']['mission_admission'],original)
        receipt=f.old.issue_candidate(self,connect,self.m['candidate'])
        current=f.old.mission(connect)['metadata']
        self.assertEqual(current['mission_admission']['status'],'valid')
        self.assertEqual(receipt['candidate']['head_sha'],pending.HEAD)
        self.assertEqual(receipt['candidate']['changed_files'],pending.PATHS)
        self.assertEqual(receipt['mission']['generation'],self.m['generation'])
        self.assertEqual(current['mission_admission_contract'],self.m['contract'])
        before=self.snapshot()
        # Even a genuine newly issued receipt cannot be used for the old PR.
        self.assertEqual(f.old.callback(self,connect,receipt,pending.PREDECESSOR_PR).status_code,409)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.run_sql()['writes'],0)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(f.old.mission(connect)['metadata']['mission_admission']['signed_receipt'],receipt)

    def test_python_and_sql_postimages_match(self):
        args=f.encoded(self.m,self.a)
        with patch.object(pending,'verify_source_and_candidate'):
            result=pending.reconcile_pending_succession(**args,dry_run=False,authenticated_owner_principal=f.OWNER,
                authenticated_desktop_principal=f.PRINCIPAL,connect_factory=lambda _:self.pg.connect(self.url))
        self.assertEqual(result['writes'],3)
        with self.pg.connect(self.url) as db:
            md=db.execute('select metadata_json from public.charlie_missions where mission_id=%s',(pending.MISSION_ID,)).fetchone()[0]
        self.assertEqual(md,self.package['updated_metadata'])
    def test_parent_or_child_hold_blocks_python_and_sql(self):
        for mid in (pending.PARENT_ID,pending.MISSION_ID):
            with self.pg.connect(self.url) as db:
                db.execute('delete from public.charlie_owner_execution_hold_events')
                db.execute("insert into public.charlie_owner_execution_hold_events values('hold',%s,'hold_created',null)",(mid,))
            before=self.snapshot()
            with self.assertRaisesRegex(self.pg.Error,'owner_execution_hold_active'):self.run_sql()
            with patch.object(pending,'verify_source_and_candidate'),self.assertRaisesRegex(pending.ReconciliationError,'owner_execution_hold_active'):
                pending.reconcile_pending_succession(**f.encoded(self.m,self.a),dry_run=False,authenticated_owner_principal=f.OWNER,authenticated_desktop_principal=f.PRINCIPAL,connect_factory=lambda _:self.pg.connect(self.url))
            self.assertEqual(self.snapshot(),before)
    def test_advisory_lock_serializes_hold_creation(self):
        with self.pg.connect(self.url) as holder:
            holder.execute('select pg_advisory_xact_lock(hashtextextended(%s,0))',(pending.MISSION_ID,))
            holder.execute("insert into public.charlie_owner_execution_hold_events values('race-hold',%s,'hold_created',null)",(pending.MISSION_ID,))
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(self.run_sql);time.sleep(.1);self.assertFalse(future.done());holder.commit()
                with self.assertRaisesRegex(self.pg.Error,'owner_execution_hold_active'):future.result(timeout=10)
    def test_concurrent_replay_has_only_one_three_write_transition(self):
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.run_sql(),range(2)))
        self.assertEqual(sorted(r['writes'] for r in results),[0,3])
    def test_each_sql_write_failure_rolls_back(self):
        for marker in ('GET DIAGNOSTICS n=ROW_COUNT;',):
            # Inject immediately after each of the three writes, not before BEGIN.
            for index in range(3):
                parts=self.sql.split(marker);altered=marker.join(parts[:index+1])+marker+" RAISE EXCEPTION 'synthetic_write_failure';"+marker.join(parts[index+1:])
                before=self.snapshot()
                with self.assertRaisesRegex(self.pg.Error,'synthetic_write_failure'):self.run_sql(altered)
                self.assertEqual(self.snapshot(),before)
    def test_changed_prior_history_hash_refuses_without_writes(self):
        bad=renderer.render_pending_sql(self.package,**{**self.hashes,'expected_registration_pg_sha256':'0'*64})
        before=self.snapshot()
        with self.assertRaisesRegex(self.pg.Error,'pending_registration_state_changed'):self.run_sql(bad)
        self.assertEqual(self.snapshot(),before)


if __name__=='__main__':unittest.main()
