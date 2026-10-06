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
