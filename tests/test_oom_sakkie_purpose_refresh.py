"""Purpose refresh uses its canonical producer within the real manager budget."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Event
from types import SimpleNamespace

import pytest

from modules.oom_sakkie import general_manager_worker as worker
from modules.oom_sakkie import manager_case_sources as sources
from modules.oom_sakkie import herdmaster_purpose_decision as purpose
from modules.oom_sakkie import family_message_lifecycle as family
from modules.oom_sakkie import bounded_postgres_read
from modules.pig_weights import herdmaster_purpose_work as domain
from tests.test_herdmaster_purpose_work import inputs, DAY, NOW
from tests.test_oom_sakkie_purpose_decision import owner, pg


def family_delivery(monkeypatch, effects):
    """Mirror the production store's exact-card scope for multiple siblings."""
    events = {}
    def load(card_id):
        return [row for row in events.values() if row["card_mission_id"] == card_id]
    def store(action, identity, payload):
        if action == "load": return load(identity)
        created = identity not in events
        if created: events[identity] = dict(payload)
        return {"success": True, "created": created}
    def provider(destination, text, **kwargs):
        effects.append((destination, text, kwargs))
        return {"success": True, "telegram_message_id": str(9000+len(effects))}
    monkeypatch.setattr(purpose, "load_purpose_delivery_events", lambda card_id, **_: load(card_id)[:3])
    monkeypatch.setattr(family, "_send_telegram", provider)
    monkeypatch.setattr(family, "_edit_telegram", lambda *_a, **_k: pytest.fail("no duplicate edit"))
    return (lambda parsed, result, **kwargs: family.deliver_family_result(
        parsed, result, event_store=store, **kwargs)), events


def snapshot(*, now=NOW, outcome="ready"):
    allocation, checks, _ = inputs(count=6,
        weight_day=None if outcome == "weight_due" else DAY-timedelta(days=1),
        kilograms=13 if outcome == "changed" else 12)
    for index, row in enumerate(allocation["pigs"]):
        row["litter_id"] = "COHORT-" + "ABC"[index // 2]
        row["sow_tag_number"] = "Example " + "ABC"[index // 2]
        if outcome == "missing":
            row["purpose"] = "Breeding"
            checks["rows"][index]["canonical"]["purpose"] = "Breeding"
        elif outcome == "held":
            checks["rows"][index].update(state="unresolved", reasons=["canonical_status_unknown"])
    return {"snapshot_observed_at": now.isoformat(), "purpose_work": domain.build_purpose_work(
        allocation, checks, analysis_date=DAY)}


def candidates(*, now=NOW, outcome="ready"):
    return sources._purpose_review_candidates(snapshot(now=now, outcome=outcome),
        now=now, today=DAY, observed_at=now)


def claimed(rows):
    return [{**worker.normalize_candidate(row, now=NOW), "generation": 1,
             "status": "delegated", "last_delivery_digest": None} for row in rows]


def test_exact_siblings_share_canonical_snapshot_and_preserve_producer_material(monkeypatch):
    rows = candidates()
    cases = claimed(rows[:2])
    reads = []
    monkeypatch.setattr(sources, "time", SimpleNamespace(monotonic=lambda: 100.0))
    def load(**kwargs):
        reads.append(kwargs)
        return snapshot()
    monkeypatch.setattr(domain, "load_purpose_work_snapshot", load)
    monkeypatch.setattr(sources, "_herdmaster", lambda *_: pytest.fail("unrelated herd read"))
    result = sources.collect_manager_refresh_snapshot(now=NOW, cases=cases,
        deadline_monotonic=104.0)
    assert reads == [{"analysis_date": DAY, "deadline": 104.0}]
    assert set(result) == {(row["dedupe_key"], "HERDMASTER") for row in rows[:2]}
    for row in rows[:2]:
        refreshed = result[(row["dedupe_key"], "HERDMASTER")]
        assert refreshed == row
        assert worker.normalize_candidate(refreshed, now=NOW)["evidence_digest"] == (
            worker.normalize_candidate(row, now=NOW)["evidence_digest"])


@pytest.mark.parametrize("remaining", [0, -1, 4, 20])
def test_short_shared_deadline_is_not_reset_and_late_result_is_rejected(monkeypatch, remaining):
    clock, reads = [100.0], []
    monkeypatch.setattr(sources, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    def load(**kwargs):
        reads.append(kwargs)
        clock[0] = kwargs["deadline"]
        return snapshot()
    monkeypatch.setattr(domain, "load_purpose_work_snapshot", load)
    cases = claimed(candidates()[:2])
    result = sources.collect_manager_refresh_snapshot(now=NOW, cases=cases,
        deadline_monotonic=100.0+remaining)
    assert all(isinstance(value, sources.ManagerCollectorRefreshError) for value in result.values())
    assert all(value.collector_failure_kind == "collector:herdmaster_purpose:TimeoutError"
               for value in result.values())
    assert len(reads) == (1 if remaining > 0 else 0)
    if reads:
        assert reads[0]["deadline"] == 100.0+min(10, remaining)


@pytest.mark.parametrize("change", ["duplicate_id", "duplicate_key", "missing_id", "too_many"])
def test_invalid_claim_selectors_never_start_purpose_read(monkeypatch, change):
    cases = claimed(candidates()[:2])
    if change == "duplicate_id": cases[1]["case_id"] = cases[0]["case_id"]
    elif change == "duplicate_key": cases[1] = {**cases[0], "case_id": "OTHER"}
    elif change == "missing_id": cases[0]["case_id"] = ""
    else: cases = cases * 3
    monkeypatch.setattr(domain, "load_purpose_work_snapshot", lambda **_: pytest.fail("invalid selectors"))
    result = sources.collect_manager_refresh_snapshot(now=NOW, cases=cases)
    assert result and all(isinstance(value, sources.ManagerCollectorRefreshError) for value in result.values())


@pytest.mark.parametrize("outcome", ["held", "weight_due", "changed", "missing", "failure"])
def test_owning_refresh_returns_current_phase_or_explicit_absence_failure(monkeypatch, outcome):
    cases = claimed(candidates()[:2])
    def load(**_):
        if outcome == "failure": raise RuntimeError("private diagnostic text")
        return snapshot(outcome=outcome)
    monkeypatch.setattr(domain, "load_purpose_work_snapshot", load)
    result = sources.collect_manager_refresh_snapshot(now=NOW, cases=cases)
    if outcome == "missing":
        assert result == {}
    elif outcome == "failure":
        assert all(isinstance(value, sources.ManagerCollectorRefreshError) for value in result.values())
        assert "private diagnostic" not in str(result)
    else:
        for case in cases:
            current = result[(case["dedupe_key"], "HERDMASTER")]
            assert current["_purpose_review"]["phase"] == ("decision_due" if outcome == "changed" else outcome)
            assert worker.normalize_candidate(current, now=NOW)["evidence_digest"] != case["evidence_digest"]


def install_default_sources(monkeypatch, initial, loader):
    monkeypatch.setattr("modules.telemetry.rootline_mixer_readiness_observer.collect_mixer_readiness",
                        lambda **_: [])
    monkeypatch.setattr(worker, "build_scheduled_brain_guard_audit", lambda **_: {"passed": True})
    monkeypatch.setattr(domain, "load_purpose_work_snapshot", loader)
    monkeypatch.setattr(sources, "collect_manager_candidates", lambda **_: initial)


def test_default_groups_keep_purpose_siblings_independent_of_unrelated_herd(monkeypatch):
    release, blocked, purpose_ready = Event(), Event(), Event()
    rows = candidates()[:2]
    cases = claimed(rows)
    routine = {"case_id": "GENERAL", "dedupe_key": "herdmaster:welfare:OTHER", "specialist": "HERDMASTER"}
    retained = {"case_id": "RETAINED", "dedupe_key": "herdmaster:retained-mortality:101", "specialist": "HERDMASTER"}
    advisory = {"case_id": "ADVISORY", "dedupe_key": "herdmaster:herdmaster:PIG-A", "specialist": "HERDMASTER"}
    reads = []
    def load(**kwargs):
        reads.append(kwargs)
        purpose_ready.set()
        return snapshot()
    install_default_sources(monkeypatch, rows, load)
    def collect(**kwargs):
        if kwargs.get("collectors"):
            blocked.set()
            assert release.wait(3)
        return rows
    monkeypatch.setattr(sources, "collect_manager_candidates", collect)
    monkeypatch.setattr(sources, "_retained_herd_report_recovery_candidates",
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("retained failure")))
    monkeypatch.setattr("modules.oom_sakkie.herdmaster_case_disposition.collect_advisory_refresh",
                        lambda *_a, **_k: ([advisory], ()))
    class Store:
        def run_cycle(self, _initial, **kwargs):
            batch = kwargs["refresh_batch"]([routine, *cases, retained, advisory])
            try:
                assert blocked.wait(1) and purpose_ready.wait(1)
                while not all(case["case_id"] in batch.poll() for case in cases):
                    batch.wait_for_ready()
                result = batch.poll()
                assert "GENERAL" not in result
                assert len(reads) == 1
                assert reads[0]["deadline"] <= batch.deadline
                for case in cases:
                    assert result[case["case_id"]]["dedupe_key"] == case["dedupe_key"]
                # Independent sibling failures never turn purpose truth into a fallback.
                while "RETAINED" not in result or "ADVISORY" not in result:
                    batch.wait_for_ready()
                    result = batch.poll()
                assert isinstance(result["RETAINED"], sources.ManagerCollectorRefreshError)
                assert result["ADVISORY"] == advisory
                return result
            finally:
                release.set()
                batch.close()
    worker.run_general_manager_cycle(now=NOW, source_revision="test", store=Store())


@pytest.mark.parametrize("outcome", ["ready", "held", "weight_due", "changed", "missing", "failure"])
def test_default_producer_store_family_path_uses_only_fresh_exact_purpose_work(pg, owner, monkeypatch, outcome):
    initial = candidates(now=pg.now)[:2]
    reads, effects = [], []
    deliver, events = family_delivery(monkeypatch, effects)
    monkeypatch.setattr(purpose, "connect_bounded_read", pg.db)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return pg.now
    monkeypatch.setattr(worker, "datetime", Clock)
    monkeypatch.setattr(purpose, "datetime", Clock)
    def load(**kwargs):
        reads.append(kwargs)
        if outcome == "failure": raise RuntimeError("canonical unavailable")
        return snapshot(now=pg.now, outcome=outcome)
    install_default_sources(monkeypatch, initial, load)
    result = worker.run_general_manager_cycle(now=pg.now, source_revision="local-purpose-refresh",
        store=pg.store, deliver=lambda case, **kwargs: worker.deliver_farm_manager_case(
            case, deliver=deliver, **kwargs))
    assert len(reads) == 1
    assert result["deadline_deferrals"] == 0
    assert len(effects) == (2 if outcome == "ready" else 0)
    assert result["deliveries_confirmed"] == len(effects)
    with pg.db() as db:
        states = db.execute("select status,generation,last_delivery_digest,evidence_digest from app_private.oom_manager_cases order by case_id").fetchall()
    assert len(states) == 2
    if outcome == "ready":
        assert all(row[2] == row[3] for row in states)
        prior_events = deepcopy(events)
        pg.now += timedelta(minutes=6)
        repeated = worker.run_general_manager_cycle(now=pg.now, source_revision="local-purpose-refresh",
            store=pg.store, deliver=lambda *_a, **_k: pytest.fail("confirmed repeat"))
        assert repeated["success"] and repeated["deliveries_suppressed"] == 2
        assert len(reads) == 1 and len(effects) == 2 and events == prior_events
    elif outcome in {"held", "weight_due", "changed"}:
        assert all(row[1] == 2 and row[2] is None for row in states)
    else:
        assert all(row[1] == 1 and row[2] is None for row in states)


def test_default_cycles_make_bounded_sibling_progress_without_repeating_delivery(pg, owner, monkeypatch):
    urgent = pg.value("priority", dedupe_key="herdmaster:retained-mortality:priority",
        urgency="urgent", message_family="retained_protected_recovery",
        evidence_refs=["event:protected"], next_reassessment_at=pg.now)
    initial = [urgent, *candidates(now=pg.now)[:2]]
    elapsed, reads, effects, order = [0.0], [], [], []
    deliver, _events = family_delivery(monkeypatch, effects)
    monkeypatch.setattr(purpose, "connect_bounded_read", pg.db)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return pg.now
    monkeypatch.setattr(worker, "datetime", Clock)
    monkeypatch.setattr(purpose, "datetime", Clock)
    monotonic = SimpleNamespace(monotonic=lambda: elapsed[0])
    monkeypatch.setattr(worker, "time", monotonic)
    monkeypatch.setattr(sources, "time", monotonic)
    monkeypatch.setattr(purpose, "time", monotonic)
    monkeypatch.setattr(bounded_postgres_read, "time", monotonic)
    monkeypatch.setattr(family, "time", monotonic)
    def load(**kwargs):
        reads.append(kwargs)
        return snapshot(now=pg.now)
    install_default_sources(monkeypatch, initial, load)
    monkeypatch.setattr(sources, "_retained_herd_report_recovery_candidates",
                        lambda *_a, **_k: [urgent])
    def collect(**_):
        elapsed[0] += 39.0  # Existing source/reconciliation work can leave little time.
        return initial
    monkeypatch.setattr(sources, "collect_manager_candidates", collect)
    def present(case, **kwargs):
        order.append(case["dedupe_key"])
        if case["dedupe_key"] == urgent["dedupe_key"]:
            elapsed[0] += 2.0
            return {"success": True, "status": "synthetic_priority_receipt",
                    "delivery_confirmed": True}
        result = worker.deliver_farm_manager_case(case, deliver=deliver, **kwargs)
        if result.get("delivery_confirmed"):
            elapsed[0] += 12.0
        return result
    first = worker.run_general_manager_cycle(now=pg.now, source_revision="local-purpose-refresh",
        store=pg.store, deliver=present)
    assert first["deliveries_confirmed"] == 2 and first["deadline_deferrals"] == 1, [
        row["outcome_status"] for row in first["case_results"]]
    assert order[0] == urgent["dedupe_key"]
    assert not first["success"] and len(effects) == 1
    deferred = next(item["case_id"] for item in first["case_results"]
                    if item["outcome_status"] == "manager_cycle_deadline_deferred")
    pg.now += timedelta(minutes=6)
    elapsed[0] = 0.0
    second = worker.run_general_manager_cycle(now=pg.now, source_revision="local-purpose-refresh",
        store=pg.store, deliver=present)
    assert second["deliveries_confirmed"] == 1 and len(effects) == 2
    assert any(item["case_id"] == deferred and item["delivery_confirmed"] for item in second["case_results"])
    assert len(reads) == 2
    pg.now += timedelta(minutes=6)
    elapsed[0] = 0.0
    final = worker.run_general_manager_cycle(now=pg.now, source_revision="local-purpose-refresh",
        store=pg.store, deliver=present)
    assert final["success"] and final["deadline_deferrals"] == 0
    assert final["deliveries_confirmed"] == 0 and final["deliveries_suppressed"] == 3
    assert len(reads) == 2 and len(effects) == 2
    assert worker.GENERAL_MANAGER_CYCLE_DEADLINE_SECONDS == 80
    assert worker.CASE_COMPLETION_RESERVE_SECONDS == 30
