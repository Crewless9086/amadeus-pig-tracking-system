"""Natural collector/default store regression on the assigned isolated database."""
from datetime import datetime, timedelta
from copy import deepcopy
import json
from modules.oom_sakkie import herdmaster_case_disposition as disposition
import pytest
from tests.test_oom_sakkie_purpose_decision import pg
from tests.test_oom_sakkie_mortality_reconciliation import legacy
from modules.oom_sakkie import general_manager_worker as worker
from modules.oom_sakkie import manager_case_sources as sources

@pytest.fixture
def mortality_db(pg, monkeypatch):
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_OWNER_USER_ID", "42")
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "42")
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return pg.now.astimezone(tz) if tz else pg.now.replace(tzinfo=None)
    monkeypatch.setattr(worker, "datetime", Clock)
    monkeypatch.setattr(worker, "build_scheduled_brain_guard_audit", lambda **kw: {"passed": True})
    return pg


def rows(pg):
    with pg.db() as db:
        return db.execute("select to_jsonb(m) from app_private.oom_manager_cases m order by case_id").fetchall()


def run(pg, values=()):
    def _herdmaster(now): return list(values)
    return worker.run_general_manager_cycle(now=pg.now, source_revision="mortality-local-test",
        store=pg.store, collectors=(_herdmaster,),
        deliver=lambda *a, **kw: pytest.fail("historical mortality must not resend"))


def test_real_default_store_retains_missing_lineage_as_dependency(mortality_db):
    pg = mortality_db
    pg.seed([legacy(pg.now), legacy(pg.now, cluster=True)])
    before = rows(pg)
    result = run(pg)
    assert result["exceptions"] == 0
    assert result["reconciliation_pending"] == 2
    assert result["deliveries_confirmed"] == 0
    for old, new in zip(before, rows(pg)):
        for field in ("case_id", "generation", "evidence_digest", "evidence_refs", "summary", "next_action", "last_delivery_digest", "last_delivery_at"):
            assert new[0][field] == old[0][field]
        assert new[0]["status"] == "waiting_reassessment"
        assert new[0]["assigned_worker_id"] is None and new[0]["lease_until"] is None
    with pg.db() as db:
        assert db.execute("select count(*) from app_private.oom_manager_case_events where event_type='completed'").fetchone()[0] == 0


def dependencies(pg):
    with pg.db() as db:
        return [v[0] for v in db.execute("select event_payload from app_private.oom_manager_case_events where event_payload ? 'technical_dependency' order by occurred_at,event_id").fetchall()]


def test_three_due_cycles_stable_dependency_and_no_early_due_postponement(mortality_db):
    pg = mortality_db; pg.seed([legacy(pg.now)])
    original = rows(pg)[0][0]
    results = [run(pg)]; first = rows(pg)
    for _ in range(2):
        pg.now += timedelta(minutes=1)
        early = run(pg)
        assert early["cases_claimed"] == 0 and rows(pg) == first
    pg.now += timedelta(minutes=3)
    results.append(run(pg)); pg.now += timedelta(minutes=5); results.append(run(pg))
    proofs = dependencies(pg)
    assert len(proofs) == 3
    assert len({p["technical_dependency"]["dependency_id"] for p in proofs}) == 1
    assert all(v["reconciliation_pending"] == 1 and v["exceptions"] == 0 for v in results)
    after = rows(pg)[0][0]
    assert after["generation"] == original["generation"] and after["evidence_digest"] == original["evidence_digest"]
    assert all(p["delivery_confirmed"] is False and p["technical_dependency"]["completion_proven"] is False for p in proofs)


def test_six_purpose_siblings_and_independent_welfare_are_byte_preserved(mortality_db):
    pg = mortality_db; pg.seed([legacy(pg.now)])
    siblings = [pg.value("sibling-"+str(i), dedupe_key="herdmaster:purpose-review:SYNTHETIC-"+str(i),
        next_reassessment_at=(pg.now+timedelta(days=1)).isoformat()) for i in range(6)]
    siblings.append(pg.value("welfare", dedupe_key="herdmaster:welfare:SYNTHETIC",
        next_reassessment_at=(pg.now+timedelta(days=1)).isoformat()))
    pg.seed(siblings)
    before = {r[0]["dedupe_key"]: r[0] for r in rows(pg) if r[0]["dedupe_key"] != legacy(pg.now)["dedupe_key"]}
    assert run(pg)["reconciliation_pending"] == 1
    after = {r[0]["dedupe_key"]: r[0] for r in rows(pg) if r[0]["dedupe_key"] in before}
    assert after == before


def test_current_changed_candidate_progresses_and_does_not_inherit_pending(mortality_db):
    pg = mortality_db; raw = legacy(pg.now); pg.seed([raw]); run(pg)
    old = rows(pg)[0][0]
    current = deepcopy(raw); current["summary"] = "Fresh canonical review with changed facts"
    current["next_reassessment_at"] = (pg.now+timedelta(minutes=5)).isoformat()
    result = run(pg, [current]); updated = rows(pg)[0][0]
    assert result["candidates_changed"] == 1 and result["reconciliation_pending"] == 0
    assert updated["generation"] == old["generation"]+1 and updated["summary"] == current["summary"]
    assert len(dependencies(pg)) == 1


def test_current_same_candidate_follows_normal_dispatch_not_pending(mortality_db):
    pg = mortality_db; raw = legacy(pg.now); pg.seed([raw]); calls=[]
    def _herdmaster(now): return [raw]
    result = worker.run_general_manager_cycle(now=pg.now, source_revision="current-source", store=pg.store,
        collectors=(_herdmaster,), deliver=lambda *a, **kw: calls.append(a[0]) or
        {"success": True, "delivery_confirmed": False, "status": "synthetic_current_work"})
    assert len(calls) == 1 and result["reconciliation_pending"] == 0 and dependencies(pg) == []


@pytest.mark.parametrize("change", ["generation", "digest", "refs", "summary", "owner", "foreign_lease", "expired_foreign_lease", "expired_own_lease"])
def test_snapshot_to_lock_race_refuses_pending(mortality_db, monkeypatch, change):
    pg = mortality_db; pg.seed([legacy(pg.now)])
    original = disposition.collect_mortality_reconciliation
    def read_then_change(*a, **kw):
        result = original(*a, **kw)
        with pg.db() as db:
            if change == "generation": db.execute("update app_private.oom_manager_cases set generation=generation+1")
            elif change == "digest": db.execute("update app_private.oom_manager_cases set evidence_digest=%s", ("d"*64,))
            elif change == "refs": db.execute("update app_private.oom_manager_cases set evidence_refs=evidence_refs||'[\"new:fact\"]'::jsonb")
            elif change == "summary": db.execute("update app_private.oom_manager_cases set summary='new source projection'")
            elif change == "owner":
                monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_OWNER_USER_ID", "43")
                monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "43")
            else:
                db.execute("update app_private.oom_manager_cases set assigned_worker_id=case when %s then assigned_worker_id else 'foreign' end,lease_until=%s",
                    (change == "expired_own_lease", pg.now+timedelta(minutes=1) if change == "foreign_lease" else pg.now-timedelta(seconds=1)))
        return result
    monkeypatch.setattr(disposition, "collect_mortality_reconciliation", read_then_change)
    result = run(pg)
    assert result["reconciliation_pending"] == 0 and result["exceptions"] == 1
    assert dependencies(pg) == [] and rows(pg)[0][0]["status"] != "completed"


def test_after_query_clock_expiry_refuses_before_pending_admission(mortality_db, monkeypatch):
    pg = mortality_db; pg.seed([legacy(pg.now)])
    original = disposition.mortality_pending_matches
    def expire(receipt, row, claimed, *, now, cycle_id):
        return original(receipt, row, claimed, now=now+timedelta(minutes=5), cycle_id=cycle_id)
    monkeypatch.setattr(disposition, "mortality_pending_matches", expire)
    result = run(pg)
    assert result["reconciliation_pending"] == 0 and result["exceptions"] == 1 and dependencies(pg) == []


def test_persistence_rechecks_projection_and_cannot_count_failed_pending(mortality_db, monkeypatch):
    pg = mortality_db; pg.seed([legacy(pg.now)])
    original = pg.store._finish_claim
    def finish(case, outcome, now, cycle_id):
        assert case.get("_mortality_pending") is not None
        with pg.db() as db: db.execute("update app_private.oom_manager_cases set summary='changed after refresh'")
        return original(case, outcome, now, cycle_id)
    monkeypatch.setattr(pg.store, "_finish_claim", finish)
    result = run(pg)
    assert result["reconciliation_pending"] == 0 and result["exceptions"] == 1
    assert result["case_results"][0]["outcome_status"] == "manager_reconciliation_persistence_unproven"
    assert dependencies(pg) == [] and rows(pg)[0][0]["summary"] == "changed after refresh"


def test_failed_event_insert_rolls_back_pending_update(mortality_db, monkeypatch):
    pg = mortality_db; pg.seed([legacy(pg.now)])
    original = pg.store._event
    def event(cur, case, kind, now, **payload):
        if payload.get("technical_dependency"): raise RuntimeError("synthetic persistence failure")
        return original(cur, case, kind, now, **payload)
    monkeypatch.setattr(pg.store, "_event", event)
    result = run(pg)
    assert result["success"] is False and result["status"] == "general_manager_cycle_failed"
    assert dependencies(pg) == [] and rows(pg)[0][0]["status"] == "delegated"


def test_read_timeout_is_sanitized_exception_not_dependency(mortality_db, monkeypatch):
    pg = mortality_db; pg.seed([legacy(pg.now)])
    def fail(*a, **kw): raise TimeoutError("private SQL details must not persist")
    monkeypatch.setattr(disposition, "collect_mortality_reconciliation", fail)
    result = run(pg)
    assert result["exceptions"] == 1 and result["reconciliation_pending"] == 0 and dependencies(pg) == []
    with pg.db() as db:
        payload = db.execute("select event_payload from app_private.oom_manager_case_events where event_type='exception'").fetchone()[0]
    assert payload["failure_kind"] == "collector:herdmaster_mortality:TimeoutError"
    assert "private SQL" not in json.dumps(payload)


def test_already_delivered_generation_remains_quiet_without_new_dependency(mortality_db):
    pg = mortality_db; pg.seed([legacy(pg.now)])
    with pg.db() as db:
        db.execute("update app_private.oom_manager_cases set last_delivery_digest=evidence_digest,last_delivery_at=%s", (pg.now,))
    result = run(pg)
    assert result["exceptions"] == 0 and result["reconciliation_pending"] == 0 and dependencies(pg) == []
    assert result["case_results"][0]["outcome_status"] == "manager_delivery_duplicate_suppressed"


def test_production_default_collector_pipeline_reads_herd_once_for_both_legacy_cases(mortality_db, monkeypatch):
    from types import SimpleNamespace
    pg = mortality_db; pg.seed([legacy(pg.now), legacy(pg.now, cluster=True)])
    calls=[]
    def load(*args):
        calls.append(args)
        return SimpleNamespace(work_items=())
    monkeypatch.setattr("modules.oom_sakkie.farm_manager_runtime._load_herdmaster", load)
    monkeypatch.setattr("modules.pig_weights.pig_welfare_case_runtime.load_open_welfare_attention_cases", lambda: [])
    monkeypatch.setattr("modules.pig_weights.herdmaster_purpose_work.load_purpose_work_snapshot",
        lambda **kw: {"snapshot_observed_at": pg.now.isoformat(), "litter_rows": [], "overview_rows": []})
    monkeypatch.setattr("modules.telemetry.rootline_mixer_readiness_observer.collect_mixer_readiness", lambda **kw: [])
    for name in ("_rootline", "_herdmaster_retained", "_herdmaster_advisories", "_herdmaster_purpose_completions",
                 "_sam", "_beacon", "_delivery_gaps", "_runtime", "_completed_bulk_batch_findings",
                 "_retained_litter_followup_candidates", "_purpose_review_candidates"):
        monkeypatch.setattr(sources, name, lambda *a, **kw: [])
    outcome = worker.run_general_manager_cycle(now=pg.now, source_revision="default-collector-local-proof",
        store=pg.store, deliver=lambda *a, **kw: pytest.fail("no historical resend"))
    assert outcome["exceptions"] == 0 and outcome["reconciliation_pending"] == 2
    assert len(calls) == 1 and len(dependencies(pg)) == 2


def test_active_foreign_lease_not_claimed_or_modified(mortality_db):
    pg = mortality_db; pg.seed([legacy(pg.now)])
    with pg.db() as db:
        db.execute("update app_private.oom_manager_cases set status='delegated',assigned_worker_id='foreign',lease_until=%s",
            (pg.now+timedelta(minutes=2),))
    before=rows(pg); result=run(pg)
    assert result["cases_claimed"] == 0 and result["reconciliation_pending"] == 0
    assert rows(pg) == before and dependencies(pg) == []


def test_collector_timeout_counts_failure_even_when_legacy_row_is_valid(mortality_db):
    pg = mortality_db; pg.seed([legacy(pg.now)])
    def _herdmaster(now): raise TimeoutError("synthetic private collector error")
    result = worker.run_general_manager_cycle(now=pg.now, source_revision="failed-initial-source",
        store=pg.store, collectors=(_herdmaster,), deliver=lambda *a, **kw: {"success": True, "delivery_confirmed": False})
    assert result["exceptions"] == 1 and result["reconciliation_pending"] == 0 and dependencies(pg) == []


def queue_fixture(pg, *, quiet_count=280):
    originals = [legacy(pg.now), legacy(pg.now, cluster=True)]
    pg.seed(originals)
    keys = [v["dedupe_key"] for v in originals]
    with pg.db() as db:
        db.execute("""update app_private.oom_manager_cases set status='exception',
            generation=case when dedupe_key=%s then 15 else 82 end,
            last_heartbeat_at=%s where dedupe_key=any(%s)""",
            (keys[0], pg.now-timedelta(hours=1), keys))
        db.execute("""insert into app_private.oom_manager_case_events
            (event_id,case_id,generation,event_type,event_payload,occurred_at)
            select 'synthetic-prior-failure:'||case_id,case_id,generation,'exception',
                '{"outcome_status":"manager_delivery_refresh_unavailable"}'::jsonb,%s
            from app_private.oom_manager_cases where dedupe_key=any(%s)""",
            (pg.now-timedelta(hours=1), keys))
    quiet = [pg.value("quiet-backlog-"+str(i), unknowns=[],
        next_reassessment_at=(pg.now-timedelta(days=2)).isoformat()) for i in range(quiet_count)]
    pg.seed(quiet)
    with pg.db() as db:
        db.execute("""update app_private.oom_manager_cases set last_delivery_digest=evidence_digest,
            last_delivery_at=%s where not (dedupe_key=any(%s))""", (pg.now-timedelta(days=2),keys))
    return keys, quiet


def queue_run(pg, current, delivered):
    def _herdmaster(now): return [v for v in current if v["specialist"]=="HERDMASTER"]
    def _rootline(now): return [v for v in current if v["specialist"]=="ROOTLINE"]
    def _beacon(now): return [v for v in current if v["specialist"]=="BEACON"]
    def suppress(case, **kwargs):
        delivered.append(case["dedupe_key"])
        return {"success": True, "delivery_confirmed": False, "status": "synthetic_no_provider_effect"}
    return worker.run_general_manager_cycle(now=pg.now, source_revision="mortality-queue-local-test",
        store=pg.store, collectors=(_herdmaster,_rootline,_beacon), deliver=suppress)


def test_282_due_cases_select_exception_targets_then_pending_returns_to_quiet(mortality_db):
    pg=mortality_db;keys,quiet=queue_fixture(pg);before={r[0]["dedupe_key"]:r[0] for r in rows(pg)}
    delivered=[];first=queue_run(pg,quiet,delivered)
    assert first["cases_claimed"]==5 and first["exceptions"]==0
    assert first["reconciliation_pending"]==2 and first["deliveries_confirmed"]==0
    assert not set(keys).intersection(delivered)
    after={r[0]["dedupe_key"]:r[0] for r in rows(pg)}
    for key in keys:
        assert after[key]["status"]=="waiting_reassessment"
        for field in ("case_id","generation","evidence_digest","evidence_refs","summary","next_action","last_delivery_digest","last_delivery_at"):
            assert after[key][field]==before[key][field]
    assert len(dependencies(pg))==2
    pg.now+=timedelta(minutes=5)
    second=queue_run(pg,quiet,delivered)
    assert second["cases_claimed"]==5 and second["exceptions"]==0 and second["reconciliation_pending"]==0
    final={r[0]["dedupe_key"]:r[0] for r in rows(pg)}
    assert all(final[key]==after[key] for key in keys) and len(dependencies(pg))==2


@pytest.mark.parametrize("key,specialist,status,expected", [
    ("herdmaster:herdmaster:mortality:"+"a"*20,"HERDMASTER","exception",True),
    ("herdmaster:herdmaster:mortality-cluster:"+"b"*20,"HERDMASTER","exception",True),
    ("herdmaster:herdmaster:mortality:"+"a"*20,"ROOTLINE","exception",False),
    ("herdmaster:herdmaster:mortality:"+"a"*20,"HERDMASTER","waiting_reassessment",False),
    ("herdmaster:herdmaster:mortality:"+"a"*20,"HERDMASTER","open",False),
    ("herdmaster:herdmaster:mortality:"+"a"*20,"HERDMASTER","completed",False),
    ("herdmaster:herdmaster:mortality:"+"a"*19,"HERDMASTER","exception",False),
    ("herdmaster:herdmaster:mortality:"+"a"*21,"HERDMASTER","exception",False),
    ("herdmaster:herdmaster:mortality:"+"A"*20,"HERDMASTER","exception",False),
    ("herdmaster:herdmaster:mortality:"+"a"*20+"\n","HERDMASTER","exception",False),
    ("prefix:herdmaster:herdmaster:mortality:"+"a"*20,"HERDMASTER","exception",False),
    ("herdmaster:retained-mortality:"+"a"*20,"HERDMASTER","exception",False),
    ("herdmaster:herdmaster:mortality-new:"+"a"*20,"HERDMASTER","exception",False),
])
def test_exception_priority_sql_is_exact_family_specialist_and_status(mortality_db,key,specialist,status,expected):
    with mortality_db.db() as db:
        actual=db.execute("select "+disposition.MORTALITY_EXCEPTION_PRIORITY_SQL+
            " from (select %s::text dedupe_key,%s::text specialist,%s::text status) m",(key,specialist,status)).fetchone()[0]
    assert actual is expected


@pytest.mark.parametrize("kind",["missing_refs","invalid_timestamp","mixed_json_types"])
def test_matching_key_malformed_evidence_gets_work_but_remains_error(mortality_db,kind):
    pg=mortality_db;pg.seed([legacy(pg.now)])
    with pg.db() as db:
        refs=db.execute("select evidence_refs from app_private.oom_manager_cases").fetchone()[0]
        if kind=="missing_refs":refs=["unproven"]
        elif kind=="invalid_timestamp":refs=["observed:not-a-time" if r.startswith("observed:") else r for r in refs]
        else:refs=[None,42,{"synthetic":"invalid"}]
        db.execute("update app_private.oom_manager_cases set status='exception',evidence_refs=%s::jsonb",(json.dumps(refs),))
    before=rows(pg)[0][0];result=run(pg);after=rows(pg)[0][0]
    assert result["cases_claimed"]==1 and result["exceptions"]==1 and result["reconciliation_pending"]==0
    assert after["status"]=="exception" and dependencies(pg)==[]
    assert datetime.fromisoformat(after["next_reassessment_at"])==pg.now+worker.CADENCE
    for field in ("generation","evidence_digest","evidence_refs","last_delivery_digest","last_delivery_at"):
        assert after[field]==before[field]


def test_fresh_urgent_fairness_and_following_cycle_handles_remaining_exception(mortality_db):
    pg=mortality_db;keys,quiet=queue_fixture(pg,quiet_count=12)
    urgent=[pg.value("urgent-"+str(i),dedupe_key=specialist.lower()+":current-synthetic-"+str(i),
        specialist=specialist,urgency="critical",unknowns=["synthetic current fact"],
        next_reassessment_at=(pg.now-timedelta(minutes=1)).isoformat())
        for i,specialist in enumerate(("HERDMASTER","ROOTLINE","BEACON","HERDMASTER"))]
    pg.seed(urgent);delivered=[];result=queue_run(pg,quiet+urgent,delivered)
    assert result["exceptions"]==0 and result["reconciliation_pending"]==1
    assert set(delivered)=={v["dedupe_key"] for v in urgent}
    assert len(dependencies(pg))==1
    pg.now+=worker.CADENCE
    second=queue_run(pg,quiet+urgent,delivered)
    assert second["exceptions"]==0 and second["reconciliation_pending"]==1
    assert {p["technical_dependency"]["case_id"] for p in dependencies(pg)}=={
        r[0]["case_id"] for r in rows(pg) if r[0]["dedupe_key"] in keys}


def test_read_failure_stays_actionable_until_next_due_recovery_with_282_cases(mortality_db,monkeypatch):
    pg=mortality_db;keys,quiet=queue_fixture(pg)
    def fail(*args,**kwargs):raise TimeoutError("synthetic unavailable read")
    with monkeypatch.context() as failure:
        failure.setattr(disposition,"collect_mortality_reconciliation",fail)
        first=queue_run(pg,quiet,[])
    assert first["exceptions"]==2 and first["reconciliation_pending"]==0 and dependencies(pg)==[]
    failed={r[0]["dedupe_key"]:r[0] for r in rows(pg) if r[0]["dedupe_key"] in keys}
    assert all(r["status"]=="exception" and datetime.fromisoformat(r["next_reassessment_at"])==pg.now+worker.CADENCE for r in failed.values())
    with pg.db() as db:
        failures=db.execute("""select event_payload->>'outcome_status',event_payload->>'failure_kind'
            from app_private.oom_manager_case_events where event_type='exception'
            and occurred_at=%s""",(pg.now,)).fetchall()
    assert failures==[("manager_specialist_processing_exception_contained","collector:herdmaster_mortality:TimeoutError")]*2
    pg.now+=timedelta(minutes=1);early=queue_run(pg,quiet,[])
    assert early["exceptions"]==0 and early["reconciliation_pending"]==0
    assert failed=={r[0]["dedupe_key"]:r[0] for r in rows(pg) if r[0]["dedupe_key"] in keys}
    pg.now+=timedelta(minutes=4);retry=queue_run(pg,quiet,[])
    assert retry["exceptions"]==0 and retry["reconciliation_pending"]==2 and len(dependencies(pg))==2
    recovered={r[0]["dedupe_key"]:r[0] for r in rows(pg) if r[0]["dedupe_key"] in keys}
    assert all(r["status"]=="waiting_reassessment" for r in recovered.values())
    for key in keys:
        for field in ("case_id","generation","evidence_digest","evidence_refs","summary","next_action","last_delivery_digest","last_delivery_at"):
            assert failed[key][field]==recovered[key][field]
    pg.now+=worker.CADENCE;later=queue_run(pg,quiet,[])
    assert later["exceptions"]==0 and later["reconciliation_pending"]==0 and len(dependencies(pg))==2
    assert recovered=={r[0]["dedupe_key"]:r[0] for r in rows(pg) if r[0]["dedupe_key"] in keys}


def test_current_legacy_delivery_exception_preserves_generic_containment(mortality_db):
    pg=mortality_db;raw=legacy(pg.now);pg.seed([raw]);attempts=[]
    def _herdmaster(now):return [raw]
    def delivery(case,**kwargs):
        attempts.append(case["case_id"])
        raise TimeoutError("synthetic delivery uncertainty")
    result=worker.run_general_manager_cycle(now=pg.now,source_revision="mortality-delivery-test",
        store=pg.store,collectors=(_herdmaster,),deliver=delivery)
    saved=rows(pg)[0][0]
    assert len(attempts)==1 and result["exceptions"]==1 and result["reconciliation_pending"]==0
    assert saved["status"]=="waiting_reassessment" and dependencies(pg)==[]
    assert datetime.fromisoformat(saved["next_reassessment_at"])==pg.now+worker.CADENCE
    assert saved["last_delivery_digest"] is None and result["deliveries_confirmed"]==0
