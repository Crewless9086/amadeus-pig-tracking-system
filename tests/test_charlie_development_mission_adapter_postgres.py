import copy
import json
import os
import threading
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg import sql

from modules.charlie.development_mission_adapter import (
    create_development_authorization,
    create_development_dispatch_grant,
    prepare_development_mission,
)
from modules.charlie.development_mission_store_adapter import (
    authorize_and_insert_development_mission,
    record_development_authorization,
    record_development_dispatch,
    record_development_dispatch_authorization,
    record_development_state,
    release_development_mission,
)
from modules.charlie import development_mission_store_adapter as secure_adapter
from scripts.charlie_mission_pickup import pick_up_exact_development_mission, prepare_exact_development_dispatch


SECRET = "development-adapter-owner-secret-at-least-32-bytes"


class CharlieDevelopmentMissionAdapterPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.getenv("DATABASE_URL", "").strip()
        if not cls.database_url:
            raise unittest.SkipTest("DATABASE_URL required for disposable PostgreSQL adapter tests")
        with psycopg.connect(cls.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("create schema if not exists app_private")
                cursor.execute("create table if not exists app_private.migration_log(migration_id text primary key,description text,applied_at timestamptz default now())")
                cursor.execute(Path("supabase/migrations/202606300001_create_charlie_mission_queue.sql").read_text(encoding="utf-8"))
                for role in ("anon", "authenticated", "service_role"):
                    cursor.execute("select 1 from pg_roles where rolname=%s", (role,))
                    if not cursor.fetchone():
                        cursor.execute(f"create role {role} nologin")
                cursor.execute(Path("supabase/migrations/202608040001_create_charlie_development_mission_adapter.sql").read_text(encoding="utf-8"))
        separator = "&" if "?" in cls.database_url else "?"
        cls.writer_url = cls.database_url + separator + "options=-c%20role%3Dcharlie_development_mission_writer"
        cls.authorizer_url = cls.database_url + separator + "options=-c%20role%3Dcharlie_development_mission_authorizer"
        cls.dispatch_authorizer_url = cls.database_url + separator + "options=-c%20role%3Dcharlie_development_dispatch_authorizer"
        cls.lineage_authorizer_url = cls.database_url + separator + "options=-c%20role%3Dcharlie_development_lineage_authorizer"

    def setUp(self):
        source = json.loads(Path("docs/06-operations/contracts/CORE_T1_POST_P0_HANDOVER_CORRECTION_PROPOSAL.json").read_text(encoding="utf-8"))
        self.proposal = {"mission": copy.deepcopy(source["mission"])}
        suffix = uuid.uuid4().hex[:10].upper()
        self.proposal["mission"]["mission_id"] += "-" + suffix
        self.proposal["mission"]["parent_lineage"]["root_mission_id"] = self.proposal["mission"]["mission_id"]
        self.prepared = prepare_development_mission(self.proposal)

    def _auth(self, action):
        return create_development_authorization(self.prepared, action=action, owner_principal="charlie", secret=SECRET)

    def _record_auth(self, action):
        auth = self._auth(action)
        result, code = record_development_authorization(self.prepared, auth, action=action,
                                                        database_url=self.authorizer_url, secret=SECRET)
        self.assertLess(code, 400, result)
        return auth

    def _record_dispatch(self, grant, *, now=None):
        result, code = record_development_dispatch_authorization(
            self.prepared, grant, database_url=self.dispatch_authorizer_url, secret=SECRET, now=now,
        )
        self.assertLess(code, 400, result)

    def test_exact_end_to_end_replay_visibility_and_artifact_enforcement(self):
        with self.assertRaises(ValueError):
            authorize_and_insert_development_mission(self.proposal, {}, database_url=self.database_url, secret=SECRET)
        insert_auth = self._record_auth("authorize_insert")
        created, code = authorize_and_insert_development_mission(self.proposal, insert_auth, database_url=self.writer_url, secret=SECRET)
        self.assertEqual(code, 201, created)
        replay, code = authorize_and_insert_development_mission(self.proposal, insert_auth, database_url=self.writer_url, secret=SECRET)
        self.assertEqual((code, replay["rows_changed"]), (200, 0))

        release_auth = self._record_auth("release")
        released, code = release_development_mission(self.proposal, release_auth, database_url=self.writer_url, secret=SECRET)
        self.assertEqual(code, 201, released)
        now = datetime.now(timezone.utc).isoformat()
        with patch("scripts.charlie_mission_pickup._runtime_pickup_authorized", return_value=(True, "")):
            dispatched, code = prepare_exact_development_dispatch(
                self.proposal, worker_id="builder-1", dispatch_id="D-1", dispatch_secret=SECRET,
                authorizer_database_url=self.dispatch_authorizer_url, writer_database_url=self.writer_url,
            )
        self.assertEqual(code, 201, dispatched)
        grant = dispatched["dispatch_grant"]
        with self.assertRaisesRegex(ValueError, "selected_worker_required"):
            pick_up_exact_development_mission(
                self.proposal, worker_id="tester-1", worker_role="tester", dispatch_id="D-1",
                acknowledged_at=now, event_id="ACK-WRONG", dispatch_grant=grant, database_url=self.writer_url,
                now=datetime.now(timezone.utc), dispatch_secret=SECRET,
            )
        ack, code = pick_up_exact_development_mission(
            self.proposal, worker_id="builder-1", worker_role="builder", dispatch_id="D-1",
            acknowledged_at=now, event_id="ACK-1", dispatch_grant=grant, database_url=self.writer_url,
            now=datetime.now(timezone.utc), dispatch_secret=SECRET,
        )
        self.assertEqual(code, 201, ack)
        worker = {"worker_id": "builder-1", "worker_role": "builder", "dispatch_id": "D-1"}
        started, code = record_development_state(self.proposal, {"type": "started", "event_id": "START-1", **worker, "dispatch_grant": grant, "heartbeat_at": now}, database_url=self.writer_url, now=datetime.now(timezone.utc), dispatch_secret=SECRET)
        self.assertEqual(code, 201, started)
        waiting, code = record_development_state(self.proposal, {"type": "waiting_for_evidence", "event_id": "WAIT-1", **worker, "dispatch_grant": grant, "heartbeat_at": now, "progress": "one file corrected"}, database_url=self.writer_url, now=datetime.now(timezone.utc), dispatch_secret=SECRET)
        self.assertEqual(code, 201, waiting)
        with psycopg.connect(self.writer_url) as connection:
            with connection.cursor() as cursor:
                forged_coordination = {"proposal_digest": self.prepared["proposal_digest"], "state": "completed_with_artifact"}
                forged_event = secure_adapter._event(self.prepared, "completed", {**worker, "artifact": {"business_outcome": "forged", "artifact_evidence": []}}, "FORGED-DONE")
                forged = secure_adapter._command(self.prepared, "event", event_kind="completed", event_identity="FORGED-DONE",
                                                 expected_state="waiting_for_evidence", new_status="pr_ready",
                                                 new_coordination=forged_coordination,
                                                 dispatch_grant_digest=grant["dispatch_grant_digest"], events=[forged_event])
                with self.assertRaises(psycopg.Error):
                    cursor.execute("select public.apply_charlie_development_command(%s::jsonb)", (json.dumps(forged),))
        incomplete = {"business_outcome": "Text corrected.", "artifact_evidence": [{"path": "docs/other.md", "commit_sha": "a" * 40, "result_identity": "wrong"}], "next_dependency": None}
        with self.assertRaisesRegex(ValueError, "declared_artifact_required"):
            record_development_state(self.proposal, {"type": "completed", "event_id": "DONE-WRONG", **worker, "dispatch_grant": grant, "artifact": incomplete}, database_url=self.writer_url, dispatch_secret=SECRET)
        artifact = {"business_outcome": "Obsolete S01 instruction removed.", "base_revision": self.proposal["mission"]["source_base_revision"], "candidate_revision": "a" * 40, "changed_files": self.proposal["mission"]["expected_files"], "artifact_evidence": [{"path": self.proposal["mission"]["expected_files"][0], "commit_sha": "a" * 40, "result_identity": "doc-correction-proof"}], "next_dependency": None}
        def lineage_verifier(_mission, value):
            proof = {"verified_by": "charlie_repo_gate", "mission_id": self.prepared["mission"]["mission_id"],
                     "proposal_digest": self.prepared["proposal_digest"], "base_revision": value["base_revision"],
                     "candidate_revision": value["candidate_revision"], "changed_files": value["changed_files"]}
            return {**proof, "proof_digest": secure_adapter._sha(secure_adapter._canonical(proof))}
        completed, code = record_development_state(self.proposal, {"type": "completed", "event_id": "DONE-1", **worker, "dispatch_grant": grant, "artifact": artifact}, database_url=self.writer_url, dispatch_secret=SECRET, lineage_verifier=lineage_verifier, lineage_authorizer_database_url=self.lineage_authorizer_url)
        self.assertEqual(code, 201, completed)
        replay, code = record_development_state(self.proposal, {"type": "completed", "event_id": "DONE-1", **worker, "dispatch_grant": grant, "artifact": artifact}, database_url=self.writer_url, dispatch_secret=SECRET, lineage_verifier=lineage_verifier, lineage_authorizer_database_url=self.lineage_authorizer_url)
        self.assertEqual((code, replay["rows_changed"]), (200, 0))
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select status,metadata_json from public.charlie_missions where mission_id=%s", (self.proposal["mission"]["mission_id"],))
                status, metadata = cursor.fetchone()
                self.assertEqual(status, "pr_ready")
                self.assertEqual(metadata["development_coordination"]["state"], "completed_with_artifact")
                self.assertEqual(metadata["development_coordination"]["parent_lineage"]["root_mission_id"], self.proposal["mission"]["mission_id"])
                cursor.execute("select count(*) from public.charlie_mission_events where mission_id=%s", (self.proposal["mission"]["mission_id"],))
                self.assertEqual(cursor.fetchone()[0], 8)

    def test_rejected_tamper_is_zero_mutation_and_legacy_rows_stay_non_runnable(self):
        tampered = copy.deepcopy(self.proposal)
        tampered["mission"]["expected_files"] = ["docs/wrong.md"]
        with self.assertRaises(ValueError):
            authorize_and_insert_development_mission(tampered, self._auth("authorize_insert"), database_url=self.database_url, secret=SECRET)
        statuses = ["new"] * 55 + ["paused"] * 27 + ["blocked"] * 3 + ["pr_ready"]
        legacy_ids = [f"LEGACY-{uuid.uuid4().hex[:12]}" for _ in statuses]
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.executemany("insert into public.charlie_missions(mission_id,status,source,raw_text,title,urgency,mission_type,approval_level) values(%s,%s,'reconciliation','legacy','legacy','P4','historical','LEVEL 0')", list(zip(legacy_ids, statuses)))
                cursor.execute("select count(*) from public.charlie_missions where mission_id=%s", (self.proposal["mission"]["mission_id"],))
                self.assertEqual(cursor.fetchone()[0], 0)
                cursor.execute("select count(*) from public.charlie_missions where mission_id=any(%s) and status in ('approved','in_progress','release_approved')", (legacy_ids,))
                self.assertEqual(cursor.fetchone()[0], 0)

    def test_concurrent_exact_insert_creates_once_and_roles_reject_direct_sql(self):
        auth = self._record_auth("authorize_insert")
        outcomes = []
        def run():
            outcomes.append(authorize_and_insert_development_mission(
                self.proposal, auth, database_url=self.writer_url, secret=SECRET,
            ))
        threads = [threading.Thread(target=run) for _ in range(2)]
        [thread.start() for thread in threads]
        [thread.join() for thread in threads]
        self.assertEqual(sorted(code for _, code in outcomes), [200, 201], outcomes)
        with psycopg.connect(self.writer_url) as connection:
            with connection.cursor() as cursor:
                with self.assertRaises(psycopg.Error):
                    cursor.execute("update public.charlie_missions set status='approved' where mission_id=%s", (self.proposal["mission"]["mission_id"],))
        separator = "&" if "?" in self.database_url else "?"
        service_url = self.database_url + separator + "options=-c%20role%3Dservice_role"
        with psycopg.connect(service_url) as connection:
            with connection.cursor() as cursor:
                with self.assertRaises(psycopg.Error):
                    cursor.execute("select public.apply_charlie_development_command('{}'::jsonb)")

    def test_writer_cannot_forge_command_digest_or_unrecorded_dispatch_grant(self):
        insert_auth = self._record_auth("authorize_insert")
        self.assertEqual(authorize_and_insert_development_mission(
            self.proposal, insert_auth, database_url=self.writer_url, secret=SECRET,
        )[1], 201)
        release_auth = self._record_auth("release")
        self.assertEqual(release_development_mission(
            self.proposal, release_auth, database_url=self.writer_url, secret=SECRET,
        )[1], 201)
        fake_grant = create_development_dispatch_grant(
            self.prepared, worker_id="builder-forged", worker_role="builder",
            dispatch_id="D-FORGED", secret=SECRET,
        )
        forged = secure_adapter._command(
            self.prepared, "dispatch", expected_state="released", new_status="paused",
            dispatch_grant=fake_grant,
            events=[secure_adapter._event(self.prepared, "dispatch_granted", {"dispatch_grant_digest": fake_grant["dispatch_grant_digest"]}, "D-FORGED")],
        )
        with psycopg.connect(self.writer_url) as connection:
            with connection.cursor() as cursor:
                altered = {**forged, "new_status": "approved"}
                with self.assertRaises(psycopg.Error):
                    cursor.execute("select public.apply_charlie_development_command(%s::jsonb)", (json.dumps(altered),))
            connection.rollback()
            with connection.cursor() as cursor:
                with self.assertRaises(psycopg.Error):
                    cursor.execute("select public.apply_charlie_development_command(%s::jsonb)", (json.dumps(forged),))

    def test_privileged_roles_cannot_forge_transitions_or_ledger_digests(self):
        insert_auth = self._record_auth("authorize_insert")
        self.assertEqual(authorize_and_insert_development_mission(
            self.proposal, insert_auth, database_url=self.writer_url, secret=SECRET,
        )[1], 201)
        release_auth = self._record_auth("release")
        prepared, _status, _metadata, coordination = secure_adapter._current(
            self.proposal, database_url=self.writer_url,
        )
        poisoned_release_coordination = {**coordination, "state": "released",
                                          "release_authorization_digest": release_auth["authorization_digest"],
                                          "selected_worker": "reviewer"}
        poisoned_release = secure_adapter._command(
            prepared, "release", expected_state="owner_authorized", new_status="paused",
            new_coordination=poisoned_release_coordination,
            authorization_digest=release_auth["authorization_digest"],
            events=[secure_adapter._event(prepared, "released", {
                "authorization_digest": release_auth["authorization_digest"]})],
        )
        with psycopg.connect(self.writer_url) as connection:
            with connection.cursor() as cursor, self.assertRaises(psycopg.Error):
                cursor.execute("select public.apply_charlie_development_command(%s::jsonb)",
                               (json.dumps(poisoned_release),))
        self.assertEqual(release_development_mission(
            self.proposal, release_auth, database_url=self.writer_url, secret=SECRET,
        )[1], 201)

        grant = create_development_dispatch_grant(
            prepared, worker_id="builder-privileged", worker_role="builder",
            dispatch_id="D-PRIVILEGED", secret=SECRET,
        )
        self._record_dispatch(grant)
        active_dispatch = secure_adapter._command(
            prepared, "dispatch", expected_state="released", new_status="approved",
            dispatch_grant=grant,
            events=[secure_adapter._event(prepared, "dispatch_granted", {
                "dispatch_grant_digest": grant["dispatch_grant_digest"]}, grant["dispatch_id"])],
        )
        with psycopg.connect(self.writer_url) as connection:
            with connection.cursor() as cursor, self.assertRaises(psycopg.Error):
                cursor.execute("select public.apply_charlie_development_command(%s::jsonb)",
                               (json.dumps(active_dispatch),))
        altered_grant = {**grant, "worker_id": "builder-envelope-poison"}
        poisoned_envelope_dispatch = secure_adapter._command(
            prepared, "dispatch", expected_state="released", new_status="paused",
            dispatch_grant=altered_grant,
            events=[secure_adapter._event(prepared, "dispatch_granted", {
                "dispatch_grant_digest": grant["dispatch_grant_digest"]}, grant["dispatch_id"])],
        )
        with psycopg.connect(self.writer_url) as connection:
            with connection.cursor() as cursor, self.assertRaises(psycopg.Error):
                cursor.execute("select public.apply_charlie_development_command(%s::jsonb)",
                               (json.dumps(poisoned_envelope_dispatch),))
        self.assertEqual(record_development_dispatch(
            self.proposal, grant, database_url=self.writer_url, secret=SECRET,
        )[1], 201)

        prepared, status, _metadata, coordination = secure_adapter._current(
            self.proposal, database_url=self.writer_url,
        )
        forged_coordination = {**coordination, "state": "forged", "selected_worker": "reviewer",
                               "last_event_id": "FORGED-STATE"}
        forged_event = secure_adapter._command(
            prepared, "event", event_kind="forged", event_identity="FORGED-STATE",
            expected_state="released", new_status="release_approved",
            new_coordination=forged_coordination,
            dispatch_grant_digest=grant["dispatch_grant_digest"],
            events=[secure_adapter._event(prepared, "forged", {
                "resulting_state": "forged", "raw_event_digest": "a" * 64}, "FORGED-STATE")],
        )
        with psycopg.connect(self.writer_url) as connection:
            with connection.cursor() as cursor, self.assertRaises(psycopg.Error):
                cursor.execute("select public.apply_charlie_development_command(%s::jsonb)",
                               (json.dumps(forged_event),))
        acknowledged_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        receipt = {"worker_id": grant["worker_id"], "worker_role": grant["worker_role"],
                   "dispatch_id": grant["dispatch_id"], "acknowledged_at": acknowledged_at}
        poisoned_ack_coordination = {**coordination, "state": "acknowledged", "receipt": receipt,
                                      "last_event_id": "ACK-POISONED", "scope": ["docs/poisoned.md"]}
        poisoned_ack = secure_adapter._command(
            prepared, "event", event_kind="acknowledged", event_identity="ACK-POISONED",
            expected_state="released", new_status="paused", new_coordination=poisoned_ack_coordination,
            dispatch_grant_digest=grant["dispatch_grant_digest"],
            events=[secure_adapter._event(prepared, "acknowledged", {
                "resulting_state": "acknowledged", "raw_event_digest": "b" * 64, **receipt,
            }, "ACK-POISONED")],
        )
        with psycopg.connect(self.writer_url) as connection:
            with connection.cursor() as cursor, self.assertRaises(psycopg.Error):
                cursor.execute("select public.apply_charlie_development_command(%s::jsonb)",
                               (json.dumps(poisoned_ack),))
        escalated_ack_coordination = {**coordination, "state": "acknowledged", "receipt": receipt,
                                      "last_event_id": "ACK-ESCALATED"}
        escalated_ack = secure_adapter._command(
            prepared, "event", event_kind="acknowledged", event_identity="ACK-ESCALATED",
            expected_state="released", new_status="approved", new_coordination=escalated_ack_coordination,
            dispatch_grant_digest=grant["dispatch_grant_digest"],
            events=[secure_adapter._event(prepared, "acknowledged", {
                "resulting_state": "acknowledged", "raw_event_digest": "c" * 64, **receipt,
            }, "ACK-ESCALATED")],
        )
        with psycopg.connect(self.writer_url) as connection:
            with connection.cursor() as cursor, self.assertRaises(psycopg.Error):
                cursor.execute("select public.apply_charlie_development_command(%s::jsonb)",
                               (json.dumps(escalated_ack),))
        _prepared, persisted_status, _metadata, persisted = secure_adapter._current(
            self.proposal, database_url=self.writer_url,
        )
        self.assertEqual((status, persisted_status, persisted["state"], persisted["selected_worker"]),
                         ("paused", "paused", "released", "builder"))

        auth_envelope = {key: value for key, value in insert_auth.items() if key != "authorization_digest"}
        dispatch_envelope = {key: value for key, value in grant.items() if key != "dispatch_grant_digest"}
        proof = {"verified_by": "charlie_repo_gate", "base_revision": self.proposal["mission"]["source_base_revision"],
                 "candidate_revision": "a" * 40, "changed_files": self.proposal["mission"]["expected_files"],
                 "proof_digest": "0" * 64}
        for url, statement, values in (
            (self.authorizer_url, "select public.append_charlie_development_authorization(%s::jsonb,%s)",
             (json.dumps(auth_envelope), "0" * 64)),
            (self.dispatch_authorizer_url, "select public.append_charlie_development_dispatch_grant(%s::jsonb,%s)",
             (json.dumps(dispatch_envelope), "0" * 64)),
            (self.lineage_authorizer_url, "select public.append_charlie_development_lineage_grant(%s,%s,%s::jsonb)",
             (self.proposal["mission"]["mission_id"], prepared["proposal_digest"], json.dumps(proof))),
        ):
            with psycopg.connect(url) as connection:
                with connection.cursor() as cursor, self.assertRaises(psycopg.Error):
                    cursor.execute(statement, values)

    def test_injected_event_failure_rolls_back_mission_and_audit(self):
        auth = self._record_auth("authorize_insert")
        mission_id = self.proposal["mission"]["mission_id"]
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("""create or replace function public.test_development_event_failure() returns trigger language plpgsql as $$
                                  begin if new.mission_id={} then raise exception 'injected_event_failure'; end if; return new; end $$""").format(sql.Literal(mission_id)))
                cursor.execute("create trigger test_development_event_failure before insert on public.charlie_mission_events for each row execute function public.test_development_event_failure()")
        try:
            result, code = authorize_and_insert_development_mission(self.proposal, auth, database_url=self.writer_url, secret=SECRET)
            self.assertEqual(code, 409, result)
            with psycopg.connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("select count(*) from public.charlie_missions where mission_id=%s", (mission_id,))
                    self.assertEqual(cursor.fetchone()[0], 0)
                    cursor.execute("select count(*) from public.charlie_mission_events where mission_id=%s", (mission_id,))
                    self.assertEqual(cursor.fetchone()[0], 0)
        finally:
            with psycopg.connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("drop trigger if exists test_development_event_failure on public.charlie_mission_events")
                    cursor.execute("drop function if exists public.test_development_event_failure()")

    def test_database_rejects_recorded_but_expired_authority_before_first_use(self):
        insert_auth = self._record_auth("authorize_insert")
        self.assertEqual(authorize_and_insert_development_mission(
            self.proposal, insert_auth, database_url=self.writer_url, secret=SECRET,
        )[1], 201)
        issued = datetime.now(timezone.utc)
        release_auth = create_development_authorization(
            self.prepared, action="release", owner_principal="charlie", secret=SECRET,
            issued_at=issued, expires_at=issued + timedelta(seconds=1),
        )
        self.assertLess(record_development_authorization(
            self.prepared, release_auth, action="release", database_url=self.authorizer_url,
            secret=SECRET,
        )[1], 400)
        time.sleep(1.1)
        _prepared, _status, _metadata, coordination = secure_adapter._current(
            self.proposal, database_url=self.writer_url,
        )
        release_coordination = {**coordination, "state": "released",
                                "release_authorization_digest": release_auth["authorization_digest"]}
        expired_release = secure_adapter._command(
            self.prepared, "release", expected_state="owner_authorized", new_status="paused",
            new_coordination=release_coordination,
            authorization_digest=release_auth["authorization_digest"],
            events=[secure_adapter._event(self.prepared, "released", {
                "authorization_digest": release_auth["authorization_digest"]})],
        )
        with psycopg.connect(self.writer_url) as connection:
            with connection.cursor() as cursor, self.assertRaises(psycopg.Error):
                cursor.execute("select public.apply_charlie_development_command(%s::jsonb)",
                               (json.dumps(expired_release),))
        self.assertEqual(secure_adapter._current(
            self.proposal, database_url=self.writer_url,
        )[3]["state"], "owner_authorized")
        live_release = self._record_auth("release")
        self.assertEqual(release_development_mission(
            self.proposal, live_release, database_url=self.writer_url, secret=SECRET,
        )[1], 201)
        issued = datetime.now(timezone.utc)
        stale_grant = create_development_dispatch_grant(
            self.prepared, worker_id="builder-stale", worker_role="builder", dispatch_id="D-STALE",
            secret=SECRET, issued_at=issued, expires_at=issued + timedelta(seconds=1),
        )
        self._record_dispatch(stale_grant)
        time.sleep(1.1)
        expired_dispatch = secure_adapter._command(
            self.prepared, "dispatch", expected_state="released", new_status="paused",
            dispatch_grant=stale_grant,
            events=[secure_adapter._event(self.prepared, "dispatch_granted", {
                "dispatch_grant_digest": stale_grant["dispatch_grant_digest"]}, "D-STALE")],
        )
        with psycopg.connect(self.writer_url) as connection:
            with connection.cursor() as cursor, self.assertRaises(psycopg.Error):
                cursor.execute("select public.apply_charlie_development_command(%s::jsonb)",
                               (json.dumps(expired_dispatch),))
        persisted = secure_adapter._current(self.proposal, database_url=self.writer_url)[3]
        self.assertEqual((persisted["state"], persisted["dispatch_grant"]), ("released", None))

    def test_missing_acknowledgement_is_one_deduplicated_containment(self):
        self.proposal["mission"]["acknowledgement_timeout_seconds"] = 60
        self.prepared = prepare_development_mission(self.proposal)
        insert_auth = self._record_auth("authorize_insert")
        self.assertEqual(authorize_and_insert_development_mission(
            self.proposal, insert_auth, database_url=self.writer_url, secret=SECRET,
        )[1], 201)
        release_auth = self._record_auth("release")
        self.assertEqual(release_development_mission(
            self.proposal, release_auth, database_url=self.writer_url, secret=SECRET,
        )[1], 201)
        issued = datetime.now(timezone.utc) - timedelta(seconds=61)
        grant = create_development_dispatch_grant(
            self.prepared, worker_id="builder-timeout", worker_role="builder",
            dispatch_id="D-TIMEOUT", secret=SECRET, issued_at=issued,
            expires_at=issued + timedelta(seconds=62),
        )
        self._record_dispatch(grant, now=issued + timedelta(seconds=1))
        self.assertEqual(record_development_dispatch(
            self.proposal, grant, database_url=self.writer_url, secret=SECRET,
            now=issued + timedelta(seconds=1),
        )[1], 201)
        time.sleep(1.1)
        event = {"type": "contain_missing_ack", "event_id": "ACK-TIMEOUT-1",
                 "worker_id": "builder-timeout", "worker_role": "builder",
                 "dispatch_id": "D-TIMEOUT", "dispatch_grant": grant}
        with self.assertRaisesRegex(ValueError, "timeout_not_elapsed"):
            record_development_state(
                self.proposal, event, database_url=self.writer_url, dispatch_secret=SECRET,
                now=issued + timedelta(seconds=59),
            )
        first, first_code = record_development_state(
            self.proposal, event, database_url=self.writer_url, dispatch_secret=SECRET,
            now=datetime.now(timezone.utc),
        )
        replay, replay_code = record_development_state(
            self.proposal, event, database_url=self.writer_url, dispatch_secret=SECRET,
        )
        self.assertEqual((first_code, replay_code, replay["rows_changed"]), (201, 200, 0))
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select count(*) from public.charlie_mission_events where mission_id=%s and metadata_json->>'state'='contain_missing_ack'", (self.proposal["mission"]["mission_id"],))
                self.assertEqual(cursor.fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
