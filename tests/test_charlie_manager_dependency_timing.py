"""Latency-shaped consumer tests; no sockets, threads or external database.

The fixture implements only the actual SQL shapes used by the consumer and its
canonical receipt helpers. Transactions copy/commit/rollback real fixture rows;
no consumer, authority validator, packet builder or receipt helper is replaced.
This is timing/transaction control proof, not PostgreSQL isolation qualification.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
import unittest
from unittest.mock import Mock, patch

from modules.charlie import manager_dependency_intake as intake
from modules.charlie.native_runner import intake_service as worker
from modules.oom_sakkie.herdmaster_case_disposition import MortalityReconciliationPending
from tests.test_oom_sakkie_mortality_reconciliation import legacy

NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


class LatencyStore:
    def __init__(self, *, cloud=False, latency=0.12, second_latency=None):
        self.elapsed = 0.0
        self.latency, self.second_latency = latency, second_latency
        self.opens, self.commits, self.rollbacks, self.closes = 0, 0, 0, 0
        self.settings, self.acquisitions, self.committed_counts = [], [], []
        self.queries = 0
        owner = intake._mortality_owner_binding()
        cases, events, cycles, deps = {}, {}, {}, []
        for i in range(2):
            case = {**legacy(NOW, cluster=bool(i)), "case_id": "CASE-TIMING-"+str(i),
                    "generation": 3, "evidence_digest": str(i+1)*64,
                    "status": "waiting_reassessment", "assigned_worker_id": None, "lease_until": None}
            proof = MortalityReconciliationPending(json.dumps(case), owner, NOW).metadata()
            dep = {k: proof[k] for k in ("case_id", "generation", "evidence_digest", "evidence_refs_digest", "dependency_id")}
            dep.update(anchor_event_id="EVENT-TIMING-"+str(i), anchor_cycle_id="CYCLE-TIMING-"+str(i))
            event = {"event_id": dep["anchor_event_id"], "case_id": case["case_id"], "generation": 3,
                     "occurred_at": NOW.isoformat(), "event_type": "delivery_suppressed",
                     "event_payload": {"cycle_id": dep["anchor_cycle_id"], "delivery_confirmed": False,
                         "outcome_status": "herdmaster_owning_reconciliation_pending", "technical_dependency": proof}}
            cycle = {"cycle_id": dep["anchor_cycle_id"], "status": "completed", "started_at": NOW.isoformat(),
                     "source_revision": "d"*40, "worker_id": "oom-sakkie-general-manager-v1",
                     "trigger_identity": "oom-sakkie-morning-scheduler:general-manager"}
            cases[case["case_id"]], events[event["event_id"]], cycles[cycle["cycle_id"]] = case, event, cycle
            deps.append(dep)
        mission = {"mission_id": "CORE-TIMING", "status": "approved", "source": "owner_authorized_test",
                   "telegram_user_id": "42", "telegram_chat_id": "42", "raw_text": "Synthetic receipt timing",
                   "title": "Receipt timing", "urgency": "P1", "mission_type": "bug fix", "approval_level": "LEVEL 3",
                   "selected_next_step": "Existing governed workflow", "owner_decision": "Synthetic admission",
                   "codex_chat_write_status": "", "metadata_json": {}, "created_at": NOW, "updated_at": NOW}
        scope = {"contract": intake.CONTRACT, "mission_id": mission["mission_id"],
                 "mission_identity_digest": intake.mission_identity_digest(mission), "owner_user_id": "42",
                 "owner_binding": owner, "producer_revision": "d"*40, "dependencies": deps,
                 "allowed_effects": list(intake._EFFECTS)}
        expiry = (NOW+timedelta(minutes=20)).isoformat()
        self.policy = {"policy_id": "POLICY-TIMING", "capability": intake.CAPABILITY, "scope": scope,
                       "authority_tier": "auto", "enabled": True, "expires_at": expiry, "max_actions": 2,
                       "max_cost": 0, "rollback_required": True, "deterministic_gate_required": True}
        mission["metadata_json"]["manager_dependency_intake"] = {"contract": intake.CONTRACT,
            "policy_id": self.policy["policy_id"], "scope_digest": intake.digest(scope),
            "authorization_identity": "synthetic-owner-authority", "receipt_only": True}
        self.context = None
        if cloud:
            self.context = {"contract": "core.cloud_receipt_intake.v1", "epoch_id": "a"*32,
                "issued_at": NOW.isoformat(), "expires_at": expiry, "scope_sha256": intake.digest(scope),
                "worker_token_sha256": "b"*64, "worker_instance": "c"*32,
                "provider": {"worker_service_id": worker.WORKER_SERVICE, "worker_deploy_id": "dep-test-worker",
                    "worker_revision": "e"*40, "api_service_id": "srv-test-api", "api_deploy_id": "dep-test-api",
                    "api_revision": "e"*40, "observed_at": NOW.isoformat(), "evidence_sha256": "f"*64}}
            self.policy["metadata_json"] = {"cloud_receipt_epoch": {**deepcopy(self.context), "status": "enabled", "cycles": []}}
        self.rows = {"policy": deepcopy(self.policy), "mission": mission, "cases": cases, "events": events,
                     "cycles": cycles, "commands": {}, "findings": {}, "links": {}}

    def connect(self, url):
        assert url == "synthetic://timing-only"
        self.opens += 1
        self.elapsed += 0.2
        return LatencyConnection(self, self.opens)

    def counts(self):
        return tuple(len(self.rows[k]) for k in ("commands", "findings", "links"))


class LatencyConnection:
    def __init__(self, store, number): self.store, self.number = store, number
    def __enter__(self): self.rows = deepcopy(self.store.rows); return self
    def __exit__(self, kind, value, traceback):
        if kind is None:
            self.store.rows = self.rows
            self.store.commits += 1
            self.store.committed_counts.append(self.store.counts())
        else:
            self.store.rollbacks += 1
        self.close()
        return False
    def close(self): self.store.closes += 1
    def cursor(self): return LatencyCursor(self)


class LatencyCursor:
    def __init__(self, db): self.db, self.result = db, []
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def fetchone(self): return self.result.pop(0) if self.result else None
    def fetchall(self): result, self.result = self.result, []; return result
    def execute(self, sql, params=None):
        s, rows = self.db.store, self.db.rows
        s.elapsed += s.second_latency if self.db.number == 2 and s.second_latency is not None else s.latency
        s.queries += 1
        q = " ".join(sql.lower().split())
        self.result = []
        if q.startswith("select set_config"):
            s.settings.append(tuple(map(int, params)))
        elif q == "select clock_timestamp()": self.result = [(NOW+timedelta(seconds=s.elapsed),)]
        elif "select to_jsonb(p)" in q: self.result = [(deepcopy(rows["policy"]),)]
        elif "select pg_advisory_xact_lock" in q: self.result = [(None,)]
        elif "select to_jsonb(m) from public.charlie_missions" in q: self.result = [(deepcopy(rows["mission"]),)]
        elif "charlie_owner_execution_hold_events" in q: pass
        elif "select to_jsonb(m) from app_private.oom_manager_cases" in q: self.result = [(deepcopy(rows["cases"][params[0]]),)]
        elif "select to_jsonb(e),to_jsonb(c)" in q:
            event = next(e for e in rows["events"].values() if e["case_id"] == params[0])
            self.result = [(deepcopy(event), deepcopy(rows["cycles"][event["event_payload"]["cycle_id"]]))]
        elif "select to_jsonb(e)" in q: self.result = [(deepcopy(rows["events"][params[0]]),)]
        elif "select to_jsonb(c)" in q: self.result = [(deepcopy(rows["cycles"][params[0]]),)]
        elif q.startswith("insert into public.charlie_control_commands"):
            if params["command_id"] not in rows["commands"]:
                rows["commands"][params["command_id"]] = {**deepcopy(params), "payload": json.loads(params["payload"]), "attempt_count": 0}
                self.result = [(params["command_id"],)]
        elif q.startswith("select status from public.charlie_control_commands"):
            self.result = [(next(v for v in rows["commands"].values() if v["key"] == params["key"])["status"],)]
        elif q.startswith("select mission_id,status,source"):
            fields = ("mission_id", "status", "source", "telegram_user_id", "telegram_chat_id", "raw_text", "title",
                "urgency", "mission_type", "approval_level", "selected_next_step", "owner_decision", "codex_chat_write_status",
                "metadata_json", "created_at", "updated_at")
            self.result = [tuple(deepcopy(rows["mission"][k]) for k in fields)]
        elif q.startswith("insert into public.charlie_mission_events"):
            if params["event_id"] not in rows["findings"]:
                rows["findings"][params["event_id"]] = {**deepcopy(params), "metadata": json.loads(params["metadata"])}
                self.result = [(params["event_id"],)]
        elif q.startswith("update public.charlie_missions"):
            rows["mission"]["metadata_json"] = json.loads(params["metadata"])
        elif q.startswith("update public.charlie_control_commands"):
            command = rows["commands"][params["command_id"]]
            command.update(status=params["status"], result=json.loads(params["result"]), attempt_count=command["attempt_count"]+1)
            self.result = [(params["command_id"],)]
        elif q.startswith("select mission_id,event_type,recorded_by"):
            row = rows["findings"].get(params[0])
            if row: self.result = [(row["mission_id"], row["event_type"], row["recorded_by"], deepcopy(row["metadata"]), row["notes"], row["created_at"])]
        elif q.startswith("select mission_id,policy_id,status"):
            row = rows["commands"].get(params[0])
            if row: self.result = [(row["mission_id"], row["policy_id"], row["status"], deepcopy(row["payload"]),
                deepcopy(row["result"]), row["command_type"], row["authority_tier"], row["key"], row["goal_id"])]
        elif q.startswith("insert into app_private.oom_manager_case_events"):
            if params[0] not in rows["links"]:
                rows["links"][params[0]] = (params[1], params[2], "delivery_suppressed", json.loads(params[3]))
                self.result = [(params[0],)]
        elif q.startswith("select case_id,generation,event_type,event_payload"):
            row = rows["links"].get(params[0])
            if row: self.result = [deepcopy(row)]
        else: raise AssertionError("Unexpected fixture SQL: "+q)
        return self


class ManagerDependencyTimingTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"OOM_SAKKIE_TELEGRAM_OWNER_USER_ID": "42", "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42",
            "OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON": "", "DATABASE_URL": "", "SUPABASE_DB_URL": ""})
        env.start(); self.addCleanup(env.stop)

    def consume(self, store):
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None): return (NOW+timedelta(seconds=store.elapsed)).astimezone(tz)
        def acquire(callback, target, kwargs, timeout):
            store.acquisitions.append(timeout)
            self.assertGreater(timeout, 0); self.assertLessEqual(timeout, 3)
            return callback(target, **kwargs)
        with patch.object(intake.time, "monotonic", side_effect=lambda: store.elapsed), \
             patch.object(intake, "datetime", Clock), \
             patch("modules.oom_sakkie.bounded_postgres_read._connect_with_wall_clock_deadline", side_effect=acquire):
            return intake.consume_manager_dependencies(mode="active", policies=[store.policy],
                database_url="synthetic://timing-only", connect_factory=store.connect, cloud_epoch=store.context)

    def assert_query_bounds(self, store):
        self.assertTrue(store.settings)
        for statement, lock in store.settings:
            self.assertLessEqual(statement, 3000); self.assertGreater(statement, 0)
            self.assertLessEqual(lock, 1000); self.assertGreater(lock, 0)

    def test_ordinary_ten_seconds_retains_first_commit_and_refuses_unfinished_link(self):
        store = LatencyStore(latency=0.18)
        result = self.consume(store)
        self.assertEqual(result["failures"], 2, result)
        self.assertEqual(store.counts(), (1, 1, 0))
        self.assertEqual(store.commits, 1)
        self.assertEqual(store.rollbacks, 1)
        self.assertEqual(store.opens, 2)
        self.assertLess(store.elapsed, 10.5)
        self.assert_query_bounds(store)

    def test_cloud_two_dependencies_commit_then_independently_readback_and_replay(self):
        store = LatencyStore(cloud=True, latency=0.18)
        result = self.consume(store)
        self.assertEqual(result["failures"], 0, result)
        self.assertGreater(store.elapsed, 10)
        self.assertLess(store.elapsed, 60)
        self.assertEqual(store.committed_counts, [(1,1,0), (1,1,1), (2,2,1), (2,2,2)])
        before = deepcopy(store.rows)
        again = self.consume(store)
        self.assertEqual(again["failures"], 0, again)
        self.assertTrue(all(r["status"] == "intake_exact_replay" for r in again["results"]))
        self.assertEqual(store.rows, before)
        self.assertEqual(store.opens, 8)
        self.assertEqual(store.closes, 8)
        self.assertTrue(all(c["attempt_count"] == 1 for c in store.rows["commands"].values()))
        self.assert_query_bounds(store)

    def test_sixty_seconds_is_shared_and_link_transaction_rolls_back(self):
        store = LatencyStore(cloud=True, latency=0.18, second_latency=1.6)
        result = self.consume(store)
        self.assertEqual(result["failures"], 2, result)
        self.assertEqual(store.counts(), (1,1,0))
        self.assertEqual(store.opens, 2)  # No fresh budget/connection for dependency two.
        self.assertEqual(store.commits, 1)
        self.assertEqual(store.rollbacks, 1)
        self.assertGreaterEqual(store.elapsed, 60)
        self.assertLess(store.elapsed, 62)
        self.assert_query_bounds(store)

    def test_cloud_claim_does_not_bypass_context_validation_before_connect(self):
        for mutation in ("missing", "extra", "wrong_epoch", "revoked", "expired", "scope"):
            with self.subTest(mutation=mutation):
                store = LatencyStore(cloud=True)
                if mutation == "missing": store.context = None
                elif mutation == "extra": store.context["unbound"] = True
                elif mutation == "wrong_epoch": store.context["epoch_id"] = "f"*32
                elif mutation == "revoked": store.policy["metadata_json"]["cloud_receipt_epoch"]["status"] = "revoked"
                elif mutation == "expired": store.elapsed = 1201
                else: store.context["scope_sha256"] = "f"*64
                result = self.consume(store)
                self.assertEqual(result["status"], "manager_dependency_scope_invalid")
                self.assertEqual(store.opens, 0)
                self.assertEqual(store.counts(), (0,0,0))

    def test_current_database_revocation_still_refuses_before_receipt(self):
        store = LatencyStore(cloud=True)
        store.rows["policy"]["enabled"] = False
        result = self.consume(store)
        self.assertEqual(result["failures"], 2)
        self.assertEqual(store.counts(), (0,0,0))
        self.assertEqual(store.commits, 0)

    def test_http_budget_accommodates_all_three_phases_without_retry(self):
        store = LatencyStore(cloud=True, latency=0.4)
        observed = {}
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(inner, limit): return json.dumps(observed["reply"]).encode()
        def open_request(request, timeout):
            observed["timeout"] = timeout
            store.elapsed += 9  # Cloud admission transaction, separately bounded at10s.
            intake_result = self.consume(store)
            self.assertEqual(intake_result["failures"], 0, intake_result)
            store.elapsed += 9  # Completion transaction, separately bounded at10s.
            observed["reply"] = {"contract": worker.CONTRACT, "success": True, "intake": intake_result}
            return Response()
        opener = Mock(); opener.open.side_effect = open_request
        response = worker.ReceiptClient("a"*64, opener=opener).request("/cycles", {"request_id":"synthetic"})
        self.assertTrue(response["success"])
        self.assertGreater(store.elapsed, 25)
        self.assertLess(store.elapsed, observed["timeout"])
        self.assertGreaterEqual(observed["timeout"], 2*intake.INTAKE_BUDGET_SECONDS+intake.CLOUD_INTAKE_BUDGET_SECONDS)
        self.assertEqual(opener.open.call_count, 1)

    def test_ambiguous_http_timeout_is_not_retried(self):
        opener = Mock(); opener.open.side_effect = TimeoutError("synthetic transport timeout")
        with self.assertRaises(TimeoutError):
            worker.ReceiptClient("a"*64, opener=opener).request("/cycles", {"request_id":"synthetic"})
        self.assertEqual(opener.open.call_count, 1)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 90)


# These two cases additionally qualify the same timing decisions against real
# PostgreSQL when the existing isolated fixture URL is explicitly supplied.
import pytest
from tests.test_charlie_manager_dependency_intake_postgres import dbcase


@pytest.mark.skipif(not os.getenv("OOM_PROTECTED_ACTION_POSTGRES_URL"), reason="explicit isolated PostgreSQL required")
@pytest.mark.parametrize("cloud", [False, True])
def test_actual_postgres_consumer_with_elapsed_roundtrips(dbcase, monkeypatch, cloud):
    from tests.test_charlie_manager_dependency_intake_postgres import CoreCursor, snapshot
    h = dbcase
    context = None
    if cloud:
        context = {"contract": "core.cloud_receipt_intake.v1", "epoch_id": "a"*32,
            "issued_at": h.now.isoformat(), "expires_at": h.policy["expires_at"],
            "scope_sha256": intake.digest(h.policy["scope"]), "worker_token_sha256": "b"*64,
            "worker_instance": "c"*32, "provider": {"worker_revision": "d"*40}}
        metadata = {"cloud_receipt_epoch": {**deepcopy(context), "status": "enabled", "cycles": []}}
        with h.db() as db:
            db.execute("update public.charlie_delegation_policies set metadata_json=%s::jsonb where policy_id=%s",
                       (json.dumps(metadata), h.policy["policy_id"]))
        h.policy["metadata_json"] = metadata
    elapsed = [0.0]
    real_execute = CoreCursor.execute
    def timed_execute(self, sql, params=None):
        result = real_execute(self, sql, params)
        elapsed[0] += 0.18  # Includes the separate set_config round trip.
        return result
    monkeypatch.setattr(CoreCursor, "execute", timed_execute)
    monkeypatch.setattr(intake.time, "monotonic", lambda: elapsed[0])
    result = intake.consume_manager_dependencies(mode="active", policies=[h.policy],
        database_url="synthetic://isolated-fixture", connect_factory=h.connect, cloud_epoch=context)
    first = snapshot(h)
    links = [e for e in first["manager_events"] if e[0]["event_payload"].get("engineering_intake")]
    if not cloud:
        assert result["failures"] == 2, result
        assert len(first["commands"]) == len(first["findings"]) == 1
        assert not links
    else:
        assert result["failures"] == 0, result
        assert len(first["commands"]) == len(first["findings"]) == len(links) == 2
        assert 10 < elapsed[0] < 60
        again = intake.consume_manager_dependencies(mode="active", policies=[h.policy],
            database_url="synthetic://isolated-fixture", connect_factory=h.connect, cloud_epoch=context)
        assert again["failures"] == 0, again
        assert all(r["status"] == "intake_exact_replay" for r in again["results"])
        assert snapshot(h) == first


if __name__ == "__main__":
    unittest.main()
