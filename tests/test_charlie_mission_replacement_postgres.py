import hashlib
import json
import os
import threading
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
from psycopg import sql

from modules.charlie.adaptive_orchestration import build_orchestration_packet, validate_orchestration_binding
from modules.charlie.mission_store import create_replacement_owner_authorization, execute_many_to_one_replacement, record_replacement_owner_authorization


SECRET = "disposable-owner-authorization-secret-32-bytes"


class CharlieMissionReplacementPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.getenv("DATABASE_URL", "").strip()
        if not cls.database_url:
            raise unittest.SkipTest("DATABASE_URL required for disposable PostgreSQL replacement tests")
        migration = Path("supabase/migrations/202608020001_create_charlie_many_to_one_replacements.sql")
        with psycopg.connect(cls.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("create schema if not exists app_private")
                cursor.execute("create table if not exists app_private.migration_log(migration_id text primary key,description text,applied_at timestamptz default now())")
                for role in ("anon", "authenticated", "service_role"):
                    cursor.execute("select 1 from pg_roles where rolname=%s", (role,))
                    if not cursor.fetchone():
                        cursor.execute(f"create role {role} nologin")
                cursor.execute(Path("supabase/migrations/202606300001_create_charlie_mission_queue.sql").read_text(encoding="utf-8"))
                cursor.execute("""create table if not exists public.charlie_owner_execution_hold_events(
                    event_id text primary key, mission_id text not null references public.charlie_missions(mission_id),
                    event_type text not null, release_of_event_id text references public.charlie_owner_execution_hold_events(event_id))""")
                cursor.execute(migration.read_text(encoding="utf-8"))
        separator = "&" if "?" in cls.database_url else "?"
        cls.writer_url = cls.database_url + separator + "options=-c%20role%3Dcharlie_mission_replacement_writer"
        cls.authorizer_url = cls.database_url + separator + "options=-c%20role%3Dcharlie_mission_replacement_authorizer"
        cls.service_url = cls.database_url + separator + "options=-c%20role%3Dservice_role"

    def setUp(self):
        self.tag = uuid.uuid4().hex[:10].upper()
        self.predecessor_ids = [f"REPLACE-PRE-{self.tag}-{n}" for n in range(3)]
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for n, mission_id in enumerate(self.predecessor_ids):
                    metadata = {"orchestration": {"generation_identity": f"generation-{self.tag}-{n}"}, "artifacts": [{"path": f"immutable-{n}.md"}], "acceptance_criteria": [f"criterion-{n}"]}
                    cursor.execute("""insert into public.charlie_missions(mission_id,status,source,raw_text,title,urgency,mission_type,approval_level,metadata_json)
                                      values(%s,'new','test',%s,%s,'P1','system improvement','LEVEL 4',%s::jsonb)""",
                                   (mission_id, f"raw-{n}", f"old-{n}", json.dumps(metadata)))
        self.contract = self._contract()
        self.predecessors = self._predecessors()
        self.authorization_cache = {}

    def _contract(self):
        mission = {"title": "S01 Oom manager closure", "raw_text": "Build missing authenticated lifecycle software only.", "mission_type": "system improvement"}
        packet = build_orchestration_packet(mission)
        workflow = [{"agent": item["agent"], "status": "pending"} for item in packet["selected_agents"]]
        binding = validate_orchestration_binding(packet, workflow)
        return {"mission_id": f"REPLACE-SUCCESSOR-{self.tag}", "status": "paused", "source": "charlie_reconciliation", "raw_text": mission["raw_text"], "title": mission["title"], "urgency": "P1", "mission_type": mission["mission_type"], "approval_level": "LEVEL 4", "metadata_json": {"orchestration": packet, "agent_workflow": workflow, "orchestration_binding": {**binding, "validated": True, "generation_identity": packet["generation_identity"]}}}

    def _predecessors(self):
        result=[]
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for mission_id in self.predecessor_ids:
                    cursor.execute("select status,public.charlie_mission_replacement_content_digest(m),public.charlie_mission_replacement_metadata_generation(m) from public.charlie_missions m where mission_id=%s",(mission_id,))
                    status,digest,generation=cursor.fetchone()
                    result.append({"mission_id":mission_id,"expected_status":status,"expected_content_digest":digest,"expected_metadata_generation":generation,"unfinished_value_reference":f"artifacts/03#{mission_id}"})
        return result

    def _execute(self, contract=None, predecessors=None, authorization=None):
        from modules.charlie.mission_store import prepare_many_to_one_replacement
        prepared=prepare_many_to_one_replacement(contract or self.contract, predecessors or self.predecessors)
        auth=authorization or self.authorization_cache.get(prepared["transaction_digest"])
        if auth is None:
            auth=create_replacement_owner_authorization(prepared,owner_principal="owner:charl",secret=SECRET)
            self.authorization_cache[prepared["transaction_digest"]]=auth
        recorded,recorded_code=record_replacement_owner_authorization(prepared,auth,database_url=self.authorizer_url,secret=SECRET,expected_owner_identity_hash=hashlib.sha256(b"owner:charl").hexdigest())
        if recorded_code >= 400:
            return recorded,recorded_code
        return execute_many_to_one_replacement(contract or self.contract,predecessors or self.predecessors,auth,database_url=self.writer_url,secret=SECRET)

    def _counts(self):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select (select count(*) from public.charlie_missions where mission_id=%s),(select count(*) from public.charlie_mission_replacement_bindings where predecessor_mission_id=any(%s)),(select count(*) from public.charlie_mission_replacement_audit_events where mission_id=%s or mission_id=any(%s))",(self.contract["mission_id"],self.predecessor_ids,self.contract["mission_id"],self.predecessor_ids))
                return cursor.fetchone()

    def test_success_replay_pickup_exclusion_and_history(self):
        result,status=self._execute(); self.assertEqual((status,result["status"]),(201,"many_to_one_replacement_created")); self.assertEqual(result["predecessor_count"],3)
        replay,replay_status=self._execute(); self.assertEqual((replay_status,replay["rows_changed"]),(200,0))
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select status from public.charlie_missions where mission_id=%s",(self.contract["mission_id"],)); self.assertEqual(cursor.fetchone()[0],"paused")
                cursor.execute("select predecessor_snapshot_json->'metadata_json'->'artifacts' from public.charlie_mission_replacement_bindings where predecessor_mission_id=any(%s) order by predecessor_mission_id",(self.predecessor_ids,)); self.assertEqual(len(cursor.fetchall()),3)
                from modules.charlie.mission_store import list_owner_work_missions
                listed,code=list_owner_work_missions("new",limit=50,database_url=self.database_url); self.assertEqual(code,200,listed); self.assertTrue(set(self.predecessor_ids).isdisjoint({x["mission_id"] for x in listed["missions"]}))
                with self.assertRaises(psycopg.Error): cursor.execute("update public.charlie_missions set title='changed' where mission_id=%s",(self.predecessor_ids[0],))

    def test_concurrent_exact_attempts_create_once(self):
        outcomes=[]
        from modules.charlie.mission_store import prepare_many_to_one_replacement
        prepared=prepare_many_to_one_replacement(self.contract,self.predecessors)
        auth=create_replacement_owner_authorization(prepared,owner_principal="owner:charl",secret=SECRET)
        def run(): outcomes.append(self._execute(authorization=auth))
        threads=[threading.Thread(target=run) for _ in range(2)]
        [t.start() for t in threads]; [t.join() for t in threads]
        self.assertEqual(sorted(code for _,code in outcomes),[200,201],outcomes); self.assertEqual(self._counts()[0:2],(1,3))

    def test_missing_changed_duplicate_conflict_collision_and_rollback(self):
        cases=[]
        missing=json.loads(json.dumps(self.predecessors)); missing[0]["mission_id"]="MISSING"; cases.append((self.contract,missing))
        changed=json.loads(json.dumps(self.predecessors)); changed[0]["expected_content_digest"]="f"*64; cases.append((self.contract,changed))
        changed_status=json.loads(json.dumps(self.predecessors)); changed_status[0]["expected_status"]="paused"; cases.append((self.contract,changed_status))
        for contract,preds in cases:
            result,code=self._execute(contract,preds); self.assertEqual(code,409,result); self.assertEqual(self._counts(),(0,0,0))
        good,code=self._execute(); self.assertEqual(code,201)
        other=self._contract(); other["mission_id"] += "-OTHER"
        result,code=self._execute(other,self.predecessors); self.assertEqual(code,409,result)

    def test_successor_collision_and_forged_stale_authorization_are_zero_mutation(self):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor: cursor.execute("insert into public.charlie_missions(mission_id,status,source,raw_text,title,urgency,mission_type,approval_level) values(%s,'paused','test','x','x','P1','system improvement','LEVEL 4')",(self.contract["mission_id"],))
        result,code=self._execute(); self.assertEqual(code,409); self.assertEqual(self._counts()[1:],(0,0))
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor: cursor.execute("delete from public.charlie_missions where mission_id=%s",(self.contract["mission_id"],))
        from modules.charlie.mission_store import prepare_many_to_one_replacement
        prepared=prepare_many_to_one_replacement(self.contract,self.predecessors)
        forged=create_replacement_owner_authorization(prepared,owner_principal="owner:charl",secret=SECRET); forged["signature"]="0"*64
        with self.assertRaisesRegex(ValueError,"signature_invalid"): execute_many_to_one_replacement(self.contract,self.predecessors,forged,database_url=self.writer_url,secret=SECRET)
        old=datetime.now(timezone.utc)-timedelta(minutes=10)
        stale=create_replacement_owner_authorization(prepared,owner_principal="owner:charl",secret=SECRET,issued_at=old,expires_at=old+timedelta(minutes=5))
        with self.assertRaisesRegex(ValueError,"stale"): execute_many_to_one_replacement(self.contract,self.predecessors,stale,database_url=self.writer_url,secret=SECRET)
        self.assertEqual(self._counts(),(0,0,0))

    def test_injected_binding_failure_rolls_back_successor_and_prior_bindings(self):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("""create or replace function public.test_replacement_binding_failure() returns trigger language plpgsql as $$ begin if new.predecessor_mission_id={} then raise exception 'injected_binding_failure'; end if; return new; end $$""").format(sql.Literal(self.predecessor_ids[-1])))
                cursor.execute("create trigger test_replacement_binding_failure before insert on public.charlie_mission_replacement_bindings for each row execute function public.test_replacement_binding_failure()")
        try:
            result,code=self._execute(); self.assertEqual(code,409,result); self.assertEqual(self._counts(),(0,0,0))
        finally:
            with psycopg.connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("drop trigger if exists test_replacement_binding_failure on public.charlie_mission_replacement_bindings")
                    cursor.execute("drop function if exists public.test_replacement_binding_failure()")

    def test_expired_exact_replay_is_zero_row_but_expired_first_execution_rejected(self):
        from modules.charlie.mission_store import prepare_many_to_one_replacement
        prepared=prepare_many_to_one_replacement(self.contract,self.predecessors)
        now=datetime.now(timezone.utc)
        auth=create_replacement_owner_authorization(prepared,owner_principal="owner:charl",secret=SECRET,issued_at=now,expires_at=now+timedelta(seconds=1))
        created,code=self._execute(authorization=auth); self.assertEqual(code,201,created)
        time.sleep(1.1)
        replay,replay_code=execute_many_to_one_replacement(self.contract,self.predecessors,auth,database_url=self.writer_url,secret=SECRET)
        self.assertEqual((replay_code,replay["rows_changed"]),(200,0))
        other=self._contract(); other["mission_id"] += "-EXPIRED"
        other_prepared=prepare_many_to_one_replacement(other,self.predecessors)
        old=datetime.now(timezone.utc)-timedelta(minutes=5)
        stale=create_replacement_owner_authorization(other_prepared,owner_principal="owner:charl",secret=SECRET,issued_at=old,expires_at=old+timedelta(seconds=1))
        with self.assertRaisesRegex(ValueError,"stale"):
            execute_many_to_one_replacement(other,self.predecessors,stale,database_url=self.writer_url,secret=SECRET)

    def test_direct_writer_forgery_and_non_exact_replay_fail_closed(self):
        from modules.charlie.mission_store import prepare_many_to_one_replacement
        prepared=prepare_many_to_one_replacement(self.contract,self.predecessors)
        auth=create_replacement_owner_authorization(prepared,owner_principal="owner:charl",secret=SECRET)
        with psycopg.connect(self.writer_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set local transaction isolation level serializable")
                with self.assertRaises(psycopg.Error):
                    cursor.execute("select public.apply_charlie_many_to_one_replacement(%s,%s,%s,%s,%s,%s,%s::jsonb)",(prepared["replacement_identity"],prepared["contract_canonical"],prepared["predecessors_canonical"],prepared["contract_digest"],prepared["predecessor_set_digest"],prepared["transaction_digest"],json.dumps(auth)))
        self.assertEqual(self._counts(),(0,0,0))
        created,code=self._execute(); self.assertEqual(code,201,created)
        with psycopg.connect(self.writer_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set local transaction isolation level serializable")
                with self.assertRaises(psycopg.Error):
                    cursor.execute("select public.apply_charlie_many_to_one_replacement(%s,%s,%s,%s,%s,%s,%s::jsonb)",(prepared["replacement_identity"],"{}",prepared["predecessors_canonical"],prepared["contract_digest"],prepared["predecessor_set_digest"],prepared["transaction_digest"],json.dumps(auth)))

    def test_database_roles_separate_authorization_execution_and_service_access(self):
        from modules.charlie.mission_store import prepare_many_to_one_replacement
        prepared=prepare_many_to_one_replacement(self.contract,self.predecessors)
        auth=create_replacement_owner_authorization(prepared,owner_principal="owner:charl",secret=SECRET)
        signed={key:value for key,value in auth.items() if key != "authorization_digest"}
        for url,query,params in (
            (self.writer_url,"select public.append_charlie_mission_replacement_authorization(%s,%s)",(json.dumps(signed,sort_keys=True,separators=(",",":")),auth["authorization_digest"])),
            (self.authorizer_url,"select public.apply_charlie_many_to_one_replacement(%s,%s,%s,%s,%s,%s,%s::jsonb)",(prepared["replacement_identity"],prepared["contract_canonical"],prepared["predecessors_canonical"],prepared["contract_digest"],prepared["predecessor_set_digest"],prepared["transaction_digest"],json.dumps(auth))),
            (self.service_url,"select public.apply_charlie_many_to_one_replacement(%s,%s,%s,%s,%s,%s,%s::jsonb)",(prepared["replacement_identity"],prepared["contract_canonical"],prepared["predecessors_canonical"],prepared["contract_digest"],prepared["predecessor_set_digest"],prepared["transaction_digest"],json.dumps(auth))),
        ):
            with psycopg.connect(url) as connection:
                with connection.cursor() as cursor:
                    with self.assertRaises(psycopg.Error): cursor.execute(query,params)


if __name__ == "__main__": unittest.main()
