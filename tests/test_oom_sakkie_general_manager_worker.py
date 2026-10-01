import json
from datetime import datetime, timedelta, timezone
import time
from concurrent.futures import Future
from types import SimpleNamespace

import pytest

from modules.oom_sakkie.general_manager_worker import (
    CLAIM_LIMIT, ManagerCaseError, PostgresManagerCaseStore,
    build_scheduled_brain_guard_audit,
    normalize_candidate, run_general_manager_cycle)


NOW = datetime(2026, 8, 17, 10, 0, tzinfo=timezone.utc)


class _ReconciliationCursor:
    def __init__(self, snapshots):
        self.snapshots = iter(snapshots)
        self.commands = []

    def execute(self, sql, params=None):
        self.commands.append((sql, params))
        if sql.startswith('select dedupe_key,'):
            self.rows = next(self.snapshots)

    def fetchall(self):
        return self.rows


def _prior_row(candidate, **changes):
    row = dict(evidence_digest=candidate['evidence_digest'], generation=1,
        status='waiting_reassessment', assigned_worker_id=None, lease_until=None,
        evidence_refs=candidate['evidence_refs'], case_id=candidate['case_id'])
    row.update(changes)
    return (candidate['dedupe_key'], *(row[key] for key in (
        'evidence_digest', 'generation', 'status', 'assigned_worker_id',
        'lease_until', 'evidence_refs', 'case_id')))


@pytest.mark.parametrize('count', [314, 317])
def test_terminal_only_gaps_use_two_fresh_cohort_reads_without_point_queries(count):
    candidates = [normalize_candidate(_candidate(dedupe_key=f'herdmaster:bulk:{i}'), now=NOW)
                  for i in range(count)]
    gaps = {(i + 1) * count // 33 for i in range(32)}
    for i in gaps:
        candidates[i]['terminal_state'] = 'completed'
    rows = [_prior_row(row) for i, row in enumerate(candidates) if i not in gaps]
    cur = _ReconciliationCursor([rows, rows])
    store = PostgresManagerCaseStore(connect_factory=lambda: None)
    priors = list(store._reconciliation_priors(cur, candidates))
    assert len(cur.commands) == 7  # failed first prefetch (4), retained second (3)
    assert sum('order by case_id for update' in sql for sql, _ in cur.commands) == 2
    assert sum(prior is None for _, prior in priors) == 32
    assert all(store._reconcile(cur, row, NOW, locked_prior=prior) == 'replayed'
               for row, prior in priors)
    assert len(cur.commands) == 7


@pytest.mark.parametrize('reason', ['insertable', 'beacon', 'duplicate_terminal', 'mixed_duplicate'])
def test_insertion_or_later_locking_keeps_original_gap_path(reason):
    from modules.oom_sakkie import general_manager_worker as worker
    lower = normalize_candidate(_candidate(dedupe_key='herdmaster:gap'), now=NOW)
    higher = normalize_candidate(_candidate(dedupe_key='herdmaster:present'), now=NOW)
    lower['terminal_state'] = 'completed'
    if reason == 'insertable':
        lower.pop('terminal_state')
    if reason == 'beacon':
        lower['specialist'] = 'BEACON'
    candidates = [lower, higher]
    if reason.endswith('duplicate') or reason == 'duplicate_terminal':
        duplicate = dict(lower)
        if reason == 'mixed_duplicate':
            duplicate.pop('terminal_state')
        candidates.append(duplicate)
    cur = _ReconciliationCursor([[_prior_row(higher)]])
    priors = list(PostgresManagerCaseStore(connect_factory=lambda: None)
                  ._reconciliation_priors(cur, candidates))
    assert len(cur.commands) == 4
    assert all(prior is worker._RECONCILIATION_PRIOR_UNREAD for _, prior in priors)


def _prepared_retained_budget_journey(monkeypatch):
    """Real retained preview and protected/family state machines; synthetic I/O."""
    from tests.test_oom_sakkie_herdmaster_retained_recovery_runtime import retained_journey
    from modules.oom_sakkie import herdmaster_retained_recovery_runtime as recovery
    from modules.oom_sakkie import herdmaster_health_loss_runtime as health
    from modules.oom_sakkie import protected_delivery_lifecycle as protected
    from modules.oom_sakkie import family_message_lifecycle as family
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS', '42')
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID', '42')
    monkeypatch.setenv('OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON', '[]')
    j = retained_journey.__wrapped__(monkeypatch)
    assert recovery.build_retained_protected_preview(j['case'])['success']
    # An already-created, never-sent claim whose UTC TTL advances with the same
    # synthetic clock as the cycle. Neither expiry nor ordinary renewal helps.
    j['clock'] = 0.
    utc_base = datetime.now(timezone.utc) + timedelta(seconds=1)
    j['claim']['expires_at'] = utc_base + timedelta(minutes=30)
    class CycleTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return utc_base + timedelta(seconds=j['clock'])
    j['utc_now'] = lambda: CycleTime.now(timezone.utc)
    for module in (recovery, health, protected, family):
        monkeypatch.setattr(module, 'datetime', CycleTime)
    j.update(provider_gate_times=[], preparation_cost=15.475, delivery_started=0.)
    store = family._event_store
    def costed_store(action, identity, payload):
        result = store(action, identity, payload)
        if action == 'load':
            # Charge the observed aggregate preparation cost through the final
            # family history load. Individual I/O timings are not live claims.
            # The one canonical loader now runs after family preparation.
            minimum = j['delivery_started'] + j['preparation_cost'] - j['load_cost']
            assert j['clock'] <= minimum
            j['clock'] = minimum
            j['provider_gate_times'].append(j['clock'] + j['load_cost'])
        return result
    monkeypatch.setattr(family, '_event_store', costed_store)
    return j


@pytest.mark.parametrize('reconciliation_seconds,confirmed', [(3.6, True), (15.174, False)])
def test_unexpired_retained_card_obeys_full_positive_path_budget(
        monkeypatch, reconciliation_seconds, confirmed):
    from modules.oom_sakkie import general_manager_worker as worker
    from modules.oom_sakkie import family_message_lifecycle as family
    j = _prepared_retained_budget_journey(monkeypatch)
    token, expiry = j['claim']['callback_token'], j['claim']['expires_at']
    j['clock'] = 15.021 + reconciliation_seconds + 7.021
    j['delivery_started'] = j['clock']
    case = normalize_candidate(_candidate(**j['case']), now=NOW)
    case['generation'] = j['case']['generation']
    j['case'].update({key:case[key] for key in ('case_id','dedupe_key','generation','evidence_digest')})
    result = worker.deliver_farm_manager_case(case, deadline_monotonic=80.)
    assert worker.GENERAL_MANAGER_CYCLE_DEADLINE_SECONDS == 80
    assert worker.CASE_COMPLETION_RESERVE_SECONDS == family.PROVIDER_DELIVERY_RESERVE_SECONDS == 30
    assert j['provider_gate_times'] == [pytest.approx(15.021 + reconciliation_seconds + 7.021 + 15.475)]
    assert result['delivery_confirmed'] is confirmed
    assert len(j['sends']) == int(confirmed)
    assert bool(j['claim'].get('delivery_attempt_id')) is confirmed
    assert bool(j['claim'].get('preview_card_message_id')) is confirmed
    assert j['claim']['callback_token'] == token
    assert len(j['window_audits']) == int(confirmed)
    if confirmed:
        assert j['claim']['expires_at'] - j['claim']['delivery_attempted_at'] == timedelta(minutes=30)
    else:
        assert j['claim']['expires_at'] == expiry
    assert not j['renewal_audits'] and j['creates'] == 1
    if confirmed:
        assert result['protected_preview_card_bound']
        assert j['sends'][0][2]['deadline_monotonic'] == 80.
    else:
        assert result['status'] == 'family_message_cycle_deadline_deferred'
        assert not j['events'] and j['claim']['delivery_state'] == 'claim_created'


def test_scheduled_brain_guard_audit_is_revision_bound_and_time_stable():
    result = {"version": "alignment.v1", "passed": True, "findings": [],
              "checked_files": ["b.md", "a.md"]}
    first = build_scheduled_brain_guard_audit(
        source_revision="abc123", now=NOW, alignment_result=result)
    later = build_scheduled_brain_guard_audit(
        source_revision="abc123", now=NOW + timedelta(minutes=5), alignment_result=result)
    assert first["passed"] is True
    assert first["status"] == "brain_guard_alignment_passed"
    assert first["checked_files"] == ["a.md", "b.md"]
    assert first["checked_count"] == 2
    assert first["evidence_digest"] == later["evidence_digest"]
    assert first["observed_at"] != later["observed_at"]
    changed = build_scheduled_brain_guard_audit(
        source_revision="def456", now=NOW, alignment_result=result)
    assert changed["evidence_digest"] != first["evidence_digest"]


def test_scheduled_brain_guard_audit_preserves_failure_findings():
    audit = build_scheduled_brain_guard_audit(
        source_revision="abc123", now=NOW,
        alignment_result={"version": "alignment.v1", "passed": False,
                          "findings": ["missing authority"], "checked_files": []})
    assert audit["passed"] is False
    assert audit["status"] == "brain_guard_alignment_failed"
    assert audit["findings"] == ["missing authority"]


def test_current_beacon_generation_retires_every_older_unconsumed_card():
    commands = []

    class Cursor:
        def execute(self, sql, params):
            commands.append((sql, params))
        def fetchone(self):
            return ("OOM-CASE-BEACON", 26)

    PostgresManagerCaseStore._retire_stale_beacon_claims(
        Cursor(), "general-manager:beacon", NOW)
    update, params = commands[-1]
    assert "c.status in ('active','executing','completed')" in update
    assert "beacon_protected_publication_consumers" in update
    assert "coalesce(result_payload,'{}'::jsonb)" in update
    assert params[2] == "scheduled:OOM-CASE-BEACON:G%"
    assert params[3] == "scheduled:OOM-CASE-BEACON:G26"
    assert "c.provider_message_id like %s" in update
    assert "superseded_by_current_manager_generation" in params[0]


def test_beacon_reconciliation_checks_claimed_publication_point_of_no_return():
    commands = []

    class Cursor:
        responses = [("old", 26, "waiting_reassessment", None, None, []), (1,)]
        def execute(self, sql, params):
            commands.append((sql, params))
        def fetchone(self):
            return self.responses.pop(0)

    candidate = {"case_id": "CASE-A", "dedupe_key": "beacon:a",
        "specialist": "BEACON", "urgency": "planned", "evidence_digest": "new",
        "evidence_refs": [], "unknowns": [], "summary": "summary",
        "next_action": "next", "next_reassessment_at": NOW.isoformat()}
    result = PostgresManagerCaseStore(connect_factory=lambda: None)._reconcile(
        Cursor(), candidate, NOW)
    assert result == "deferred"
    assert "beacon_protected_publication_consumers" in commands[-1][0]
    assert commands[-1][1] == ("scheduled:CASE-A:G26",)


def test_terminal_completed_candidate_closes_existing_case_without_delivery():
    commands = []
    class Cursor:
        responses = [("old", 2, "waiting_reassessment", None, None,
                      ["pig:PIG-A", "observation:OLD"])]
        def execute(self, sql, params): commands.append((sql, params))
        def fetchone(self): return self.responses.pop(0)
    candidate = normalize_candidate(_candidate(dedupe_key="herdmaster:bulk-condition:PIG-A",
        evidence_refs=["pig:PIG-A", "observation:NEW"], terminal_state="completed"), now=NOW)
    result = PostgresManagerCaseStore(connect_factory=lambda: None)._reconcile(Cursor(), candidate, NOW)
    assert result == "changed"
    assert any("status='completed'" in sql for sql, _ in commands)
    assert any("oom_manager_case_events" in sql and params[3] == "completed"
               for sql, params in commands)


def test_cycle_wrapper_supplies_current_brain_guard_audit_to_store():
    class Store:
        def run_cycle(self, candidates, **kwargs):
            return {"candidates": list(candidates), **kwargs}

    result = run_general_manager_cycle(
        candidates=[], now=NOW, source_revision="abc123", store=Store())
    audit = result["brain_guard_audit"]
    assert audit["source_revision"] == "abc123"
    assert audit["passed"] is True
    assert audit["checked_count"] > 0


def test_cycle_wrapper_refreshes_claimed_specialists_as_one_batch(monkeypatch):
    calls = []
    cases = [
        {"case_id": "CASE-ONE", "dedupe_key": "herdmaster:first",
         "specialist": "HERDMASTER"},
        {"case_id": "CASE-TWO", "dedupe_key": "herdmaster:second",
         "specialist": "HERDMASTER"},
    ]
    snapshot = {
        ("herdmaster:first", "HERDMASTER"): {"dedupe_key": "herdmaster:first"},
        ("herdmaster:second", "HERDMASTER"): {"dedupe_key": "herdmaster:second"},
    }
    monkeypatch.setattr(
        "modules.oom_sakkie.manager_case_sources.collect_manager_candidates",
        lambda **_kwargs: [])
    monkeypatch.setattr(
        "modules.oom_sakkie.manager_case_sources.collect_manager_refresh_snapshot",
        lambda **kwargs: (calls.append(tuple(kwargs["cases"])) or snapshot))

    class Store:
        def run_cycle(self, _candidates, **kwargs):
            batch = kwargs["refresh_batch"](cases)
            try:
                while len(batch.poll()) < len(cases):
                    batch.wait_for_ready()
                return batch.poll()
            finally:
                batch.close()

    result = run_general_manager_cycle(
        now=NOW, source_revision="abc123", store=Store(),
        collectors=(lambda _now: [],))

    assert calls == [tuple(cases)]
    assert result == {
        "CASE-ONE": snapshot[("herdmaster:first", "HERDMASTER")],
        "CASE-TWO": snapshot[("herdmaster:second", "HERDMASTER")],
    }


def test_refresh_batch_distinguishes_pending_missing_and_frozen_late_result(monkeypatch):
    from modules.oom_sakkie import general_manager_worker as worker
    clock, futures, closed = [0.0], [], []
    class Executor:
        def __init__(self, **_kwargs): pass
        def submit(self, *_args):
            future = Future()
            future.set_running_or_notify_cancel()
            futures.append(future)
            return future
        def shutdown(self, **kwargs): closed.append(kwargs)
    monkeypatch.setattr(worker, 'ThreadPoolExecutor', Executor)
    monkeypatch.setattr(worker, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    cases = [{'case_id': 'CASE-' + str(i), 'dedupe_key': 'herdmaster:' + str(i),
              'specialist': 'HERDMASTER'} for i in range(3)]
    batch = worker._ManagerRefreshBatch([((case,), lambda: {}) for case in cases], deadline_monotonic=80)
    futures[0].set_result((1.0, {}))
    futures[1].set_result((20.0, {('herdmaster:1', 'HERDMASTER'): cases[1]}))
    assert batch.poll()['CASE-0'] is None
    assert isinstance(batch.poll()['CASE-1'], TimeoutError)
    assert 'CASE-2' not in batch.poll()
    clock[0] = 20.0
    timeout = batch.poll()['CASE-2']
    assert isinstance(timeout, TimeoutError)
    futures[2].set_result((21.0, {('herdmaster:2', 'HERDMASTER'): cases[2]}))
    assert batch.poll()['CASE-2'] is timeout
    batch.close()
    assert closed == [{'wait': False, 'cancel_futures': True}]


def test_refresh_batch_does_not_wait_past_a_just_completed_future(monkeypatch):
    from modules.oom_sakkie import general_manager_worker as worker
    ready, slow = Future(), Future()
    ready.set_result((1.0, {}))
    batch = worker._ManagerRefreshBatch.__new__(worker._ManagerRefreshBatch)
    batch.jobs, batch.deadline = {ready: (), slow: ()}, 20.0
    monkeypatch.setattr(worker, 'wait', lambda *_args, **_kwargs: pytest.fail('ready result bypassed'))
    batch.wait_for_ready()


def test_refresh_batch_checks_completion_after_observing_timeout_boundary(monkeypatch):
    from modules.oom_sakkie import general_manager_worker as worker
    future = Future()
    row = {'case_id': 'CASE-A', 'dedupe_key': 'herdmaster:a', 'specialist': 'HERDMASTER'}
    def observe_deadline():
        # The on-time read becomes visible as the caller observes the cutoff.
        if not future.done():
            future.set_result((19.9, {('herdmaster:a', 'HERDMASTER'): row}))
        return 20.0
    batch = worker._ManagerRefreshBatch.__new__(worker._ManagerRefreshBatch)
    batch.results, batch.jobs, batch.deadline = {}, {future: (row,)}, 20.0
    monkeypatch.setattr(worker, 'time', SimpleNamespace(monotonic=observe_deadline))
    assert batch.poll() == {'CASE-A': row}


@pytest.mark.parametrize('failure', [KeyError('unexpected'), ManagerCaseError('manager_failure')])
def test_refresh_batch_submission_failure_closes_executor(monkeypatch, failure):
    from modules.oom_sakkie import general_manager_worker as worker
    closed = []
    class Executor:
        def __init__(self, **_kwargs): pass
        def submit(self, *_args): raise failure
        def shutdown(self, **kwargs): closed.append(kwargs)
    monkeypatch.setattr(worker, 'ThreadPoolExecutor', Executor)
    with pytest.raises(type(failure)):
        worker._ManagerRefreshBatch([(({},), lambda: {})], deadline_monotonic=time.monotonic() + 80)
    assert closed == [{'wait': False, 'cancel_futures': True}]


def test_failed_brain_guard_is_persisted_and_blocks_case_delivery():
    commands = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, params): commands.append((sql, params))

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
        def close(self): pass

    delivered = []
    audit = build_scheduled_brain_guard_audit(
        source_revision="abc123", now=NOW,
        alignment_result={"version": "alignment.v1", "passed": False,
                          "findings": ["conflicting doctrine"], "checked_files": ["bad.md"]})
    result = PostgresManagerCaseStore(connect_factory=Connection).run_cycle(
        [_candidate()], now=NOW, source_revision="abc123",
        deliver=lambda case: delivered.append(case), brain_guard_audit=audit)
    assert result["success"] is False
    assert result["brain_guard"]["status"] == "brain_guard_alignment_failed"
    assert delivered == []
    assert not any("from app_private.oom_manager_cases" in sql for sql, _ in commands)
    failure_writes = [(sql, params) for sql, params in commands
                      if "status,case_counts,completed_at" in sql]
    assert len(failure_writes) == 1
    assert "brain_guard_alignment_failed" in failure_writes[0][1][-2]
    assert '"kind": "ManagerCaseError"' in failure_writes[0][1][-2]
    assert '"code": "scheduled_brain_guard_alignment_failed"' in failure_writes[0][1][-2]


def test_audit_commit_uses_separate_connection_from_manager_work():
    connections = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, _sql, _params): pass
        def fetchall(self): return []

    class Connection:
        def __init__(self):
            self.closed = False
            connections.append(self)
        def __enter__(self):
            if self.closed:
                raise RuntimeError("closed connection reused")
            return self
        def __exit__(self, *_args):
            self.closed = True
            return False
        def cursor(self): return Cursor()
        def close(self): self.closed = True

    audit = build_scheduled_brain_guard_audit(
        source_revision="abc123", now=NOW,
        alignment_result={"version": "alignment.v1", "passed": True,
                          "findings": [], "checked_files": ["one.md"]})
    result = PostgresManagerCaseStore(connect_factory=Connection).run_cycle(
        [], now=NOW, source_revision="abc123", brain_guard_audit=audit)
    assert result["success"] is True
    assert len(connections) == 3
    assert len({id(connection) for connection in connections}) == 3


def test_audit_checkpoint_uses_existing_started_status_vocabulary():
    commands = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, params): commands.append((sql, params))
        def fetchall(self): return []

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
        def close(self): pass

    audit = build_scheduled_brain_guard_audit(
        source_revision="abc123", now=NOW,
        alignment_result={"version": "alignment.v1", "passed": True,
                          "findings": [], "checked_files": ["one.md"]})
    result = PostgresManagerCaseStore(connect_factory=Connection).run_cycle(
        [], now=NOW, source_revision="abc123", brain_guard_audit=audit)
    assert result["success"] is True
    checkpoint = next(params for sql, params in commands
                      if "next_cycle_at,status,case_counts" in sql)
    assert checkpoint[-2] == "started"
    assert "brain_guard_alignment_passed" in checkpoint[-1]


def test_due_selection_orders_then_locks_with_skip_locked_and_limit():
    commands = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, params): commands.append((sql, params))
        def fetchall(self): return []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
        def close(self): pass
    audit = build_scheduled_brain_guard_audit(source_revision="abc", now=NOW,
        alignment_result={"version":"v1","passed":True,"findings":[],"checked_files":[]})
    result = PostgresManagerCaseStore(connect_factory=Connection).run_cycle(
        [], now=NOW, source_revision="abc", brain_guard_audit=audit)
    assert result["success"] is True
    selection = next(sql for sql, _ in commands if "join eligible" in sql)
    assert "for update of m skip locked limit %s" in selection
    selection_params = next(params for sql, params in commands if "join eligible" in sql)
    assert selection_params[-1] == CLAIM_LIMIT
    assert "partition by work_class,specialist" in selection


def test_expired_cycle_budget_defers_claim_without_specialist_or_provider_call():
    delivered = []
    case_row = ("OOM-CASE-BUDGET", "herdmaster:budget", "HERDMASTER", "urgent",
        "delegated", "d" * 64, ["event:one"], ["current_fact"],
        "Current case.", "Reassess.", NOW, 1, None)

    class Cursor:
        def __init__(self):
            self.last_sql = ""
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, _params): self.last_sql = sql
        def fetchall(self):
            return [case_row] if "join eligible" in self.last_sql else []

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
        def close(self): pass

    store = PostgresManagerCaseStore(connect_factory=Connection)
    deferred = []
    store._defer_claims = lambda cases, *_args, **_kwargs: (
        deferred.extend(case["case_id"] for case in cases)
        or {case["case_id"] for case in cases})
    audit = build_scheduled_brain_guard_audit(
        source_revision="abc", now=NOW,
        alignment_result={"version":"v1","passed":True,
                          "findings":[],"checked_files":[]})

    result = store.run_cycle([], now=NOW, source_revision="abc",
        deliver=lambda case: delivered.append(case),
        refresh=lambda case: (_ for _ in ()).throw(AssertionError()),
        refresh_batch=lambda cases: (_ for _ in ()).throw(AssertionError("expired refresh batch started")),
        deadline_monotonic=time.monotonic(),
        brain_guard_audit=audit)

    assert result["success"] is False
    assert result["status"] == "general_manager_cycle_deadline_contained"
    assert delivered == []
    assert deferred == ["OOM-CASE-BUDGET"]
    assert result["case_results"][0]["outcome_status"] == \
        "manager_cycle_deadline_deferred"


def test_bulk_deadline_release_requires_exact_lease_generation_and_digest():
    commands = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, params): commands.append((sql, params))
        def fetchall(self): return [("CASE-A",), ("CASE-B",)]
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
    cases = [
        {"case_id":"CASE-A","generation":1,"evidence_digest":"a"*64},
        {"case_id":"CASE-B","generation":2,"evidence_digest":"b"*64},
    ]

    released = PostgresManagerCaseStore(
        connect_factory=Connection)._defer_claims(
            cases, NOW, "CYCLE-ONE",
            outcome_status="manager_cycle_deadline_deferred")

    sql, params = commands[0]
    assert released == {"CASE-A", "CASE-B"}
    assert "m.generation=e.generation" in sql
    assert "m.evidence_digest=e.evidence_digest" in sql
    assert "m.assigned_worker_id=%s" in sql and "m.lease_until>=%s" in sql
    assert params[4] == "CYCLE-ONE"
    expected = json.loads(params[0])
    assert [(row["case_id"], row["generation"], row["evidence_digest"])
            for row in expected] == [
        ("CASE-A", 1, "a"*64), ("CASE-B", 2, "b"*64)]


def test_slow_first_delivery_cannot_cross_deadline_or_starve_unrelated_case(monkeypatch):
    from modules.oom_sakkie import general_manager_worker as worker
    clock = [35.0]
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock[0])
    rows = [
        (f"OOM-CASE-{index}", f"herdmaster:deadline:{index}", "HERDMASTER",
         "urgent", "open", str(index) * 64, [f"event:{index}"],
         ["current_fact"], f"Case {index}.", "Reassess.", NOW, 1, None)
        for index in range(1, 4)
    ]

    class Cursor:
        def __init__(self): self.last_sql = ""
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, _params): self.last_sql = sql
        def fetchall(self): return rows if "join eligible" in self.last_sql else []

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
        def close(self): pass

    effects = []
    store = PostgresManagerCaseStore(connect_factory=Connection)
    store._refresh_claim = lambda case, *_args: case
    store._finish_claim = lambda *_args: True
    deferred = []
    store._defer_claims = lambda cases, *_args, **_kwargs: (
        deferred.extend(case["case_id"] for case in cases)
        or {case["case_id"] for case in cases})
    audit = build_scheduled_brain_guard_audit(
        source_revision="abc", now=NOW,
        alignment_result={"version":"v1","passed":True,
                          "findings":[],"checked_files":[]})

    def cooperative_delivery(case, *, deadline_monotonic):
        clock[0] += 10
        assert clock[0] <= deadline_monotonic
        effects.append(case["case_id"])
        return {"success": True, "status": "delivery_confirmed",
                "delivery_confirmed": True}

    result = store.run_cycle([], now=NOW, source_revision="abc",
        deliver=cooperative_delivery,
        refresh_batch=lambda cases: {
            case["case_id"]: case for case in cases},
        deadline_monotonic=80.0, brain_guard_audit=audit)

    assert result["processing_timings_ms"] == {
        "source_collection": 0, "reconciliation_and_claim": 0, "dispatch": 20000}
    assert effects == ["OOM-CASE-1", "OOM-CASE-2"]
    assert deferred == ["OOM-CASE-3"]
    assert result["success"] is False
    assert result["status"] == "general_manager_cycle_deadline_contained"
    assert result["deadline_deferrals"] == 1
    assert [row["outcome_status"] for row in result["case_results"]] == [
        "delivery_confirmed", "delivery_confirmed",
        "manager_cycle_deadline_deferred"]


def _candidate(**changes):
    value = {
        "dedupe_key": "rootline:current-plan",
        "specialist": "ROOTLINE",
        "urgency": "urgent",
        "evidence_refs": ["event:one"],
        "unknowns": ["delivered_current_irrigation_plan"],
        "summary": "Current plan remains contained.",
        "next_action": "Delegate to ROOTLINE and retain ownership.",
        "next_reassessment_at": (NOW + timedelta(minutes=15)).isoformat(),
    }
    value.update(changes)
    return value


def test_candidate_identity_is_stable_when_only_reassessment_time_moves():
    first = normalize_candidate(_candidate(), now=NOW)
    later = normalize_candidate(_candidate(
        next_reassessment_at=(NOW + timedelta(minutes=30)).isoformat()), now=NOW)
    assert first["case_id"] == later["case_id"]
    assert first["evidence_digest"] == later["evidence_digest"]


def test_evidence_change_changes_generation_digest():
    first = normalize_candidate(_candidate(), now=NOW)
    changed = normalize_candidate(_candidate(evidence_refs=["event:two"]), now=NOW)
    assert first["evidence_digest"] != changed["evidence_digest"]


def test_observation_epoch_does_not_create_a_new_material_digest():
    first = normalize_candidate(_candidate(
        evidence_refs=["event:one", "observed:2026-08-17T10:00:00+00:00"]), now=NOW)
    later = normalize_candidate(_candidate(
        evidence_refs=["event:one", "observed:2026-08-17T10:05:00+00:00"]), now=NOW)
    assert first["evidence_digest"] == later["evidence_digest"]


@pytest.mark.parametrize(("lease_until", "expected"), [
    (NOW + timedelta(minutes=2), "deferred"),
    (NOW - timedelta(minutes=2), "replayed")])
def test_changed_evidence_cannot_replace_a_delegated_generation(lease_until, expected):
    class Cursor:
        def __init__(self): self.commands=[]
        def execute(self, sql, params): self.commands.append((sql, params))
        def fetchone(self):
            return ("a"*64, 1, "delegated", "oom-sakkie-general-manager-v1",
                    lease_until, ["observed:2026-08-17T10:00:00+00:00"])
    cursor=Cursor()
    candidate=normalize_candidate(_candidate(evidence_refs=["event:new"]), now=NOW)
    result=PostgresManagerCaseStore(connect_factory=lambda: None)._reconcile(cursor,candidate,NOW)
    assert result == expected
    assert len(cursor.commands) == 1


def test_failed_reclaimed_worker_cannot_downgrade_confirmed_generation():
    class Cursor:
        def __init__(self): self.commands=[]
        def __enter__(self): return self
        def __exit__(self,*_args): return False
        def execute(self,sql,params): self.commands.append((sql,params))
        def fetchone(self):
            return (1,"d"*64,"d"*64,"waiting_reassessment","cycle-two",
                    NOW + timedelta(minutes=2))
    class Connection:
        def __init__(self,cursor): self.value=cursor
        def __enter__(self): return self
        def __exit__(self,*_args): return False
        def cursor(self): return self.value
    cursor=Cursor()
    store=PostgresManagerCaseStore(connect_factory=lambda: Connection(cursor))
    case={"case_id":"OOM-CASE-ONE","generation":1,"evidence_digest":"d"*64,
          "next_reassessment_at":NOW.isoformat()}
    store._finish_claim(case,{"success":False,"status":"ambiguous"},NOW,"cycle-two")
    assert len(cursor.commands) == 3
    update = next(params for sql,params in cursor.commands
                  if "status='waiting_reassessment',next_reassessment_at=%s" in sql)
    assert update[0] == NOW + timedelta(minutes=5)
    assert update[3] == "OOM-CASE-ONE"
    event = next(params for sql,params in cursor.commands
                 if "oom_manager_case_events" in sql)
    payload = json.loads(event[4])
    assert payload["outcome_status"] == "ambiguous"
    assert payload["confirmed_generation_preserved"] is True


def test_confirmed_duplicate_releases_claim_and_reschedules_without_delivery():
    class Cursor:
        def __init__(self): self.commands=[]
        def __enter__(self): return self
        def __exit__(self,*_args): return False
        def execute(self,sql,params): self.commands.append((sql,params))
        def fetchone(self):
            return (1,"d"*64,"d"*64,"delegated","cycle-two",
                    NOW + timedelta(minutes=2))
    class Connection:
        def __init__(self,cursor): self.value=cursor
        def __enter__(self): return self
        def __exit__(self,*_args): return False
        def cursor(self): return self.value
    cursor=Cursor(); store=PostgresManagerCaseStore(connect_factory=lambda: Connection(cursor))
    case={"case_id":"OOM-CASE-ONE","generation":1,"evidence_digest":"d"*64,
          "next_reassessment_at":NOW.isoformat()}
    store._finish_claim(case,{"success":True,"status":"manager_delivery_duplicate_suppressed",
        "next_reassessment_at":(NOW+timedelta(minutes=5)).isoformat()},NOW,"cycle-two")
    assert any("update app_private.oom_manager_cases set status" in sql for sql,_ in cursor.commands)


@pytest.mark.parametrize("field,value", [
    ("specialist", "UNKNOWN"), ("urgency", "panic"),
    ("evidence_refs", []), ("dedupe_key", "bad key"),
])
def test_candidate_contract_fails_closed(field, value):
    with pytest.raises(ManagerCaseError):
        normalize_candidate(_candidate(**{field: value}), now=NOW)


@pytest.mark.parametrize("dedupe,prior_refs,candidate_refs", [
    ("herdmaster:bulk-condition:PIG-A",
     ["observation:NEW", "observed:2026-08-17T10:00:00Z"],
     ["observation:OLD", "observed:2026-08-16T10:00:00Z"]),
    ("herdmaster:bulk-weight-change:PIG-A",
     ["weight_event:NEW", "weight_date:2026-08-17"],
     ["weight_event:OLD", "weight_date:2026-08-16"]),
    ("herdmaster:bulk-weight-change:PIG-A",
     ["weight_event:NEW", "weight_date:2026-08-17", "weight_recorded:2026-08-17T10:00:00Z"],
     ["weight_event:OLD", "weight_date:2026-08-17", "weight_recorded:2026-08-17T09:00:00Z"]),
    ("herdmaster:bulk-weight-change:PIG-A",
     ["weight_event:WGT-Z", "weight_date:2026-08-17", "weight_recorded:2026-08-17T10:00:00Z"],
     ["weight_event:WGT-A", "weight_date:2026-08-17", "weight_recorded:2026-08-17T10:00:00Z"]),
    ("herdmaster:bulk-condition:PIG-A",
     ["observation:NEW", "observed:2026-08-17T10:00:00Z", "observation_recorded:2026-08-17T10:10:00Z"],
     ["observation:OLD", "observed:2026-08-17T10:00:00Z", "observation_recorded:2026-08-17T10:05:00Z"]),
    ("herdmaster:bulk-condition:PIG-A",
     ["observation:CORRECTED", "supersedes_observation:OLD", "observed:2026-08-16T10:00:00Z"],
     ["observation:OLD", "observed:2026-08-17T10:00:00Z"]),
    ("herdmaster:bulk-condition:PIG-A",
     ["observation:CORRECTED-C", "supersedes_observation:CORRECTED-B",
      "supersedes_observation:OLD-A", "observed:2026-08-15T10:00:00Z"],
     ["observation:OLD-A", "observed:2026-08-17T10:00:00Z"]),
])
def test_terminal_reconciliation_rejects_provably_stale_canonical_evidence(
        dedupe, prior_refs, candidate_refs):
    commands = []
    class Cursor:
        def execute(self, sql, params): commands.append((sql, params))
        def fetchone(self):
            return ("old", 8, "waiting_reassessment", None, None, prior_refs)
    candidate = normalize_candidate(_candidate(dedupe_key=dedupe,
        specialist="HERDMASTER", evidence_refs=candidate_refs,
        terminal_state="completed"), now=NOW)
    assert PostgresManagerCaseStore(connect_factory=lambda: None)._reconcile(
        Cursor(), candidate, NOW) == "stale"
    assert len(commands) == 1  # Only the locked read; no update or event.


@pytest.mark.parametrize("state,lease_until,owner,replace_owner,expected", [
    ("delegated", NOW + timedelta(minutes=2), "OTHER", True, "deferred"),
    ("waiting_reassessment", NOW + timedelta(minutes=2), "OTHER", True, "deferred"),
    ("delegated", NOW - timedelta(minutes=2), "OTHER", True, "replayed"),
    ("delegated", NOW + timedelta(minutes=2), "THIS", False, "replayed"),
    ("delegated", NOW + timedelta(minutes=2), "THIS", True, "changed"),
])
def test_terminal_reconciliation_preserves_other_delivery_owner(
        state, lease_until, owner, replace_owner, expected):
    commands = []
    class Cursor:
        def execute(self, sql, params): commands.append((sql, params))
        def fetchone(self):
            return ("old", 8, state, owner, lease_until,
                    ["observation:OLD", "observed:2026-08-16T10:00:00Z"])
    candidate = normalize_candidate(_candidate(
        dedupe_key="herdmaster:bulk-condition:PIG-A", specialist="HERDMASTER",
        evidence_refs=["observation:NEW", "observed:2026-08-17T10:00:00Z"],
        terminal_state="completed"), now=NOW)
    assert PostgresManagerCaseStore(connect_factory=lambda: None)._reconcile(
        Cursor(), candidate, NOW, lease_owner="THIS",
        replace_delegated_owner=replace_owner) == expected
    if expected != "changed":
        assert len(commands) == 1
    else:
        assert any("status='completed'" in sql for sql, _ in commands)


@pytest.mark.parametrize("ancestors,expected", [
    (["OLD"], "changed"), (["INTERMEDIATE", "OLD"], "changed"),
    (["UNRELATED"], "stale")])
def test_backdated_terminal_correction_requires_exact_canonical_lineage(ancestors, expected):
    commands = []
    class Cursor:
        def execute(self, sql, params): commands.append((sql, params))
        def fetchone(self):
            return ("old", 8, "waiting_reassessment", None, None,
                    ["observation:OLD", "observed:2026-08-17T10:00:00Z",
                     "observation_recorded:2026-08-17T10:01:00Z"])
    candidate = normalize_candidate(_candidate(
        dedupe_key="herdmaster:bulk-condition:PIG-A", specialist="HERDMASTER",
        evidence_refs=["observation:CORRECTED",
            *("supersedes_observation:" + ancestor for ancestor in ancestors),
            "observed:2026-08-16T10:00:00Z", "observation_recorded:2026-08-18T10:00:00Z"],
        terminal_state="completed"), now=NOW)
    assert PostgresManagerCaseStore(connect_factory=lambda: None)._reconcile(
        Cursor(), candidate, NOW) == expected
    if expected == "changed":
        assert any("oom_manager_case_events" in sql and params[3] == "completed"
                   for sql, params in commands)
    else:
        assert len(commands) == 1


@pytest.mark.parametrize("readback,proven", [
    ((2, "fresh", None, "completed", None, None), True),
    ((3, "newer", None, "open", None, None), False),
    ((2, "fresh", None, "delegated", "OWN", NOW + timedelta(minutes=2)), False),
    ((2, "fresh", None, "completed", "OTHER", NOW + timedelta(minutes=2)), False),
    ((2, "fresh", None, "completed", None, NOW - timedelta(minutes=2)), False),
    (None, False),
])
def test_completion_outcome_requires_exact_lease_free_final_readback(monkeypatch, readback, proven):
    commands, delivered = [], []
    claim = ("OOM-CASE-COMPLETE", "herdmaster:bulk-condition:PIG-A", "HERDMASTER",
             "urgent", "open", "old", ["observation:OLD"], [],
             "Existing follow-up.", "Reassess.", NOW, 1, None)
    class Cursor:
        def __init__(self): self.last_sql = ""
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, params):
            self.last_sql = sql
            commands.append((sql, params))
        def fetchall(self): return [claim] if "join eligible" in self.last_sql else []
        def fetchone(self):
            assert "select generation,evidence_digest,last_delivery_digest,status" in self.last_sql
            if readback and readback[4] == "OWN":
                owner = next(params[0] for sql, params in commands
                    if "assigned_worker_id=%s,lease_until=%s,last_heartbeat_at=%s" in sql)
                return (*readback[:4], owner, datetime.now(timezone.utc) + timedelta(minutes=2))
            return readback
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
        def close(self): pass
    store = PostgresManagerCaseStore(connect_factory=Connection)
    monkeypatch.setattr(store, "_refresh_claim", lambda case, *_args: {
        **case, "status": "completed", "generation": 2, "evidence_digest": "fresh"})
    audit = build_scheduled_brain_guard_audit(source_revision="test", now=NOW,
        alignment_result={"version": "v1", "passed": True, "findings": [], "checked_files": []})
    result = store.run_cycle([], now=NOW, source_revision="test",
        deliver=lambda case: delivered.append(case), refresh=lambda case: case,
        brain_guard_audit=audit)
    assert delivered == []
    assert result["deliveries_confirmed"] == 0
    assert result["exceptions"] == (0 if proven else 1)
    assert result["case_results"][0]["outcome_status"] == (
        "manager_case_completed_from_current_evidence" if proven
        else "manager_case_completion_persistence_unproven")
    finish_index = next(index for index, (sql, _) in enumerate(commands)
        if "select generation,evidence_digest,last_delivery_digest,status" in sql)
    assert all("oom_manager_cases" not in sql and "oom_manager_case_events" not in sql
               for sql, _ in commands[finish_index + 1:])


@pytest.mark.parametrize("claimed_status,completed", [
    ("waiting_reassessment", True), ("delegated", False)])
def test_refresh_terminal_evidence_preserves_reclaimed_delegated_fence(claimed_status, completed):
    commands = []
    raw = _candidate(dedupe_key="herdmaster:bulk-condition:PIG-A",
        specialist="HERDMASTER", evidence_refs=["observation:RECOVERED"],
        terminal_state="completed")
    fresh = normalize_candidate(raw, now=NOW)
    claimed = {**fresh, "generation": 1, "evidence_digest": "old", "status": claimed_status}
    current = (fresh["case_id"], fresh["dedupe_key"], "HERDMASTER", "urgent",
        "completed" if completed else "delegated", fresh["evidence_digest"] if completed else "old",
        fresh["evidence_refs"], [], fresh["summary"], fresh["next_action"], NOW,
        2 if completed else 1, None)
    responses = [(1, "old", "THIS", NOW + timedelta(minutes=2)),
        ("old", 1, "delegated", "THIS", NOW + timedelta(minutes=2), ["observation:OLD"]), current]
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, params): commands.append((sql, params))
        def fetchone(self): return responses.pop(0)
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
    result = PostgresManagerCaseStore(connect_factory=Connection)._refresh_claim(
        claimed, raw, NOW, "THIS")
    assert not responses
    assert (result["status"] == "completed") is completed
    assert any("status='completed'" in sql for sql, _ in commands) is completed
    assert any("status='delegated'" in sql for sql, _ in commands) is not completed
    if not completed:
        assert result["_refreshed_generation"] is True
        assert not any("oom_manager_case_events" in sql and params[3] == "completed"
                       for sql, params in commands)


def test_retained_recovery_refresh_is_ready_while_full_herd_refresh_is_blocked(monkeypatch):
    from threading import Event
    from modules.oom_sakkie import manager_case_sources as sources
    release, blocked, ready = Event(), Event(), Event()
    retained = {"case_id": "RETAINED", "dedupe_key": "herdmaster:retained-mortality:5097",
                "specialist": "HERDMASTER"}
    routine = {"case_id": "ROUTINE", "dedupe_key": "herdmaster:welfare:OTHER",
               "specialist": "HERDMASTER"}
    groups = []
    monkeypatch.setattr(sources, "collect_manager_candidates", lambda **kwargs: [])
    def snapshot(**kwargs):
        cases = tuple(kwargs["cases"])
        groups.append(tuple(row["case_id"] for row in cases))
        if routine in cases:
            blocked.set()
            assert release.wait(3), "test must release the blocked collector"
        else:
            ready.set()
        return {(row["dedupe_key"], row["specialist"]): row for row in cases}
    monkeypatch.setattr(sources, "collect_manager_refresh_snapshot", snapshot)
    class Store:
        def run_cycle(self, _candidates, **kwargs):
            batch = kwargs["refresh_batch"]([routine, retained])
            try:
                assert blocked.wait(1)
                assert ready.wait(1), "retained case must have an independent refresh"
                batch.wait_for_ready()
                result = batch.poll()
                assert result == {"RETAINED": retained}
                return result
            finally:
                release.set()
                batch.close()
    result = run_general_manager_cycle(now=NOW, source_revision="test", store=Store(),
        collectors=(lambda _now: [],))
    assert result == {"RETAINED": retained}
    assert sorted(groups) == [("RETAINED",), ("ROUTINE",)]


def test_deadline_phase_and_numeric_timings_survive_existing_case_event():
    commands = []
    case = {"case_id": "CASE-A", "generation": 1, "evidence_digest": "d" * 64,
            "next_reassessment_at": NOW.isoformat()}
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, params): commands.append((sql, params))
        def fetchone(self):
            return (1, "d" * 64, None, "delegated", "CYCLE-A", NOW + timedelta(minutes=4))
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
    outcome = {"success": False, "status": "manager_cycle_deadline_deferred",
        "deadline_phase": "after_retained_preview",
        "processing_timings_ms": {"dispatch_wait": 11000, "refresh_and_delivery": 15000}}
    assert PostgresManagerCaseStore(connect_factory=Connection)._finish_claim(
        case, outcome, NOW, "CYCLE-A")
    events = [json.loads(params[4]) for sql, params in commands
              if "insert into app_private.oom_manager_case_events" in sql]
    failure = next(event for event in events if event["event_type"] == "exception")
    assert failure["deadline_phase"] == "after_retained_preview"
    assert failure["processing_timings_ms"] == outcome["processing_timings_ms"]
    assert failure["provider_ambiguity_contained"] is False


def test_exact_advisory_refresh_and_retained_refresh_do_not_wait_for_full_herd(monkeypatch):
    from threading import Event
    from modules.oom_sakkie import manager_case_sources as sources
    from modules.oom_sakkie import herdmaster_case_disposition as disposition
    release, blocked, advisory_ready, retained_ready = Event(), Event(), Event(), Event()
    advisory = {"case_id": "ADVISORY", "dedupe_key": "herdmaster:herdmaster:PIG-A", "specialist": "HERDMASTER"}
    retained = {"case_id": "RETAINED", "dedupe_key": "herdmaster:retained-mortality:101", "specialist": "HERDMASTER"}
    routine = {"case_id": "ROUTINE", "dedupe_key": "herdmaster:welfare:OTHER", "specialist": "HERDMASTER"}
    monkeypatch.setattr("modules.telemetry.rootline_mixer_readiness_observer.collect_mixer_readiness", lambda **kwargs: [])
    def collect(**kwargs):
        if kwargs.get("collectors"):
            blocked.set()
            assert release.wait(3)
        return []
    monkeypatch.setattr(sources, "collect_manager_candidates", collect)
    def exact_advisory(now, *, claimed_cases):
        assert claimed_cases == (advisory,)
        advisory_ready.set()
        return [advisory], ()
    def exact_retained(now, *, claimed_cases):
        assert claimed_cases == (retained,)
        retained_ready.set()
        raise TimeoutError("isolated retained failure")
    monkeypatch.setattr(disposition, "collect_advisory_refresh", exact_advisory)
    monkeypatch.setattr(sources, "_retained_herd_report_recovery_candidates", exact_retained)
    class Store:
        def run_cycle(self, candidates, **kwargs):
            batch = kwargs["refresh_batch"]([routine, advisory, retained])
            try:
                assert blocked.wait(1) and advisory_ready.wait(1) and retained_ready.wait(1)
                batch.wait_for_ready()
                result = batch.poll()
                assert result["ADVISORY"] == advisory
                assert isinstance(result["RETAINED"], sources.ManagerCollectorRefreshError)
                assert "ROUTINE" not in result
                return result
            finally:
                release.set()
                batch.close()
    run_general_manager_cycle(now=NOW, source_revision="test", store=Store())
