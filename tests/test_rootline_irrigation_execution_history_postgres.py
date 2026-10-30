"""Real PostgreSQL differential coverage for ROOTLINE's active-history readers.

The reference changes only the SELECT back to the pre-optimization query. Both
paths execute the production loader and its unchanged reducer. Payload metrics
are reserialized JSON bytes, not PostgreSQL wire bytes or measured live egress.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

store = importlib.import_module("modules.telemetry.rootline_irrigation_execution_store")
bounded = importlib.import_module("modules.oom_sakkie.bounded_postgres_read")

pytestmark = pytest.mark.skipif(
    not os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL"),
    reason="disposable ROOTLINE PostgreSQL URL is required",
)
OLD_QUERY = """select review_json->'rootline_execution'
    from public.sam_live_stock_conversation_review_events
    where event_source=%s order by created_at desc"""
FAMILIES = [
    ("load_active", "claim_before_on", "mark_active"),
    ("load_active_auxiliary", "claim_auxiliary_before_on", "mark_auxiliary_active"),
    ("load_active_borehole", "claim_borehole_before_on", "mark_borehole_active"),
]
BASE_TIME = datetime(2000, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def disposable_url():
    import psycopg

    url = os.environ["ROOTLINE_DISPOSABLE_POSTGRES_URL"]
    migration = Path(__file__).resolve().parents[1] / "supabase/migrations/202607070001_create_sam_live_stock_conversation_review_events.sql"
    with psycopg.connect(url, connect_timeout=3) as connection:
        connection.execute(migration.read_text(encoding="utf-8"))
    return url


class MeasuredCursor:
    def __init__(self, cursor, reference, metrics):
        self.cursor, self.reference, self.metrics = cursor, reference, metrics

    def __enter__(self):
        self.cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self.cursor.__exit__(*args)

    def execute(self, query, params):
        self.metrics["selects"] += 1
        if self.reference:
            query, params = OLD_QUERY, (params[0],)
        return self.cursor.execute(query, params)

    def fetchall(self):
        rows = self.cursor.fetchall()
        self.metrics["rows"] += len(rows)
        self.metrics["json_payload_bytes"] += sum(
            len(json.dumps(row[0], ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8"))
            for row in rows
        )
        return rows


class MeasuredConnection:
    def __init__(self, connection, reference, metrics):
        self.connection, self.reference, self.metrics = connection, reference, metrics

    def cursor(self):
        return MeasuredCursor(self.connection.cursor(), self.reference, self.metrics)


@pytest.fixture
def history(disposable_url, monkeypatch, record_property):
    import psycopg
    from psycopg.types.json import Jsonb

    event_source = "rootline-history-test-" + uuid.uuid4().hex
    monkeypatch.setattr(store, "EVENT_SOURCE", event_source)
    monkeypatch.setenv("DATABASE_URL", disposable_url)
    real_factory = bounded.connect_bounded_rootline_postgres

    def seed(envelopes, *, start=0, raw=False, same_time=False):
        # Each test owns a unique source; the canonical table remains append-only.
        with psycopg.connect(disposable_url, connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.executemany("""insert into public.sam_live_stock_conversation_review_events
                    (review_event_id,event_source,review_json,created_at)
                    values (%s,%s,%s,%s)""", [
                        ("rootline-history-test-" + uuid.uuid4().hex, event_source,
                         Jsonb(envelope if raw else {"rootline_execution": envelope}),
                         BASE_TIME + timedelta(seconds=start + (0 if same_time else index)))
                        for index, envelope in enumerate(envelopes)
                    ])

    def run(action, reference):
        metrics = {"selects": 0, "rows": 0, "json_payload_bytes": 0}
        connections = []

        @contextmanager
        def measured_factory(**kwargs):
            assert kwargs == {"database_url": disposable_url}
            # Preserve the actual bounded, read-only connector and its cleanup.
            with real_factory(**kwargs) as connection:
                connections.append(connection)
                yield MeasuredConnection(connection, reference, metrics)

        with monkeypatch.context() as patch:
            patch.setattr(bounded, "connect_bounded_rootline_postgres", measured_factory)
            try:
                outcome = (store.rootline_irrigation_execution_store(action, None), None)
            except Exception as exc:
                outcome = (None, (type(exc).__module__, type(exc).__name__, str(exc)))
        assert metrics["selects"] == 1
        assert len(connections) == 1 and connections[0].closed
        return outcome, metrics

    def compare(action):
        old, before = run(action, True)
        new, after = run(action, False)
        assert new == old
        assert after["rows"] <= before["rows"]
        assert after["json_payload_bytes"] <= before["json_payload_bytes"]
        for phase, metrics in (("before", before), ("after", after)):
            for key, value in metrics.items():
                record_property(f"{phase}_{key}", value)
        return SimpleNamespace(value=new[0], error=new[1], before=before, after=after)

    return SimpleNamespace(seed=seed, compare=compare)


@pytest.mark.parametrize("load,claim,active", FAMILIES)
def test_unrelated_heavy_history_retains_old_unresolved_claim(history, load, claim, active):
    pending = {"action": claim, "execution_id": "old-unresolved"}
    history.seed([pending], start=-86400 * 365)
    history.seed([
        {"action": "record_eligibility", "execution_id": f"other-{index}",
         "evidence": "unrelated synthetic evidence " * 80}
        for index in range(1500)
    ])
    # A different family's terminal cannot retire this family's frozen claim.
    other_terminal = "record_completed" if load != "load_active" else "record_auxiliary_completed"
    history.seed([{"action": other_terminal, "execution_id": "old-unresolved"}], start=2000)
    result = history.compare(load)
    assert result.error is None
    assert result.value == {**pending, "state": "claimed_recovery_required"}
    assert result.before["rows"] == 1502 and result.after["rows"] == 1
    assert result.after["json_payload_bytes"] < result.before["json_payload_bytes"] // 100


@pytest.mark.parametrize("load,claim,terminal,unconditional", [
    ("load_active", "claim_before_on", "record_completed", True),
    ("load_active", "claim_before_on", "contain_zone", False),
    ("load_active", "claim_before_on", "record_ambiguous_shutdown", False),
    ("load_active", "claim_before_on", "record_claim_recovery", False),
    ("load_active_auxiliary", "claim_auxiliary_before_on", "record_auxiliary_completed", True),
    ("load_active_auxiliary", "claim_auxiliary_before_on", "record_auxiliary_control_pulse_stopped", True),
    ("load_active_auxiliary", "claim_auxiliary_before_on", "contain_auxiliary_device", False),
])
@pytest.mark.parametrize("shutdown", [None, False, True, "true", 1])
def test_terminal_verification_semantics_are_unchanged(history, load, claim, terminal,
                                                      unconditional, shutdown):
    history.seed([{"action": claim, "execution_id": "pending"},
                  {"action": terminal, "execution_id": "pending", "shutdown_verified": shutdown}])
    result = history.compare(load)
    assert result.error is None
    assert (result.value is None) == (unconditional or shutdown is True)
    assert result.after["rows"] == 2


@pytest.mark.parametrize("load,claim,active", FAMILIES)
def test_stopping_state_is_recoverable_only_for_irrigation(history, load, claim, active):
    running = {"action": active, "execution_id": "pending", "state": "Active"}
    stopping = {"action": "mark_stopping", "execution_id": "pending", "state": "stopping"}
    history.seed([running, stopping])
    result = history.compare(load)
    assert result.error is None
    assert result.value == (stopping if load == "load_active" else running)


def completion():
    return {"action": "record_borehole_completed", "execution_id": "pending",
            "shutdown_verified": True,
            "canonical_completion_evidence": {"evidence_id": "canonical", "execution_id": "pending", "final_state": "OFF"},
            "provider_final_off_evidence": {"evidence_id": "provider-off", "execution_id": "pending", "authoritative": True, "state": "OFF"},
            "physical_completion_evidence": {"evidence_id": "physical", "execution_id": "pending", "pump_stopped": True, "water_flow_stopped": True}}


@pytest.mark.parametrize("variant", ["physical", "provider-app", "missing-physical",
    "different-execution", "duplicate-evidence", "blank-evidence", "non-authoritative",
    "water-unknown", "unverified", "containment", "malformed-evidence"])
def test_borehole_completion_keeps_strict_evidence_checks(history, variant):
    terminal = completion()
    if variant == "provider-app":
        terminal.pop("physical_completion_evidence")
        terminal["operational_proof"] = "provider_app_on_to_off"
        terminal["provider_start_evidence"] = {"authoritative": True, "state": "ON"}
    elif variant == "missing-physical":
        terminal.pop("physical_completion_evidence")
    elif variant == "different-execution":
        terminal["provider_final_off_evidence"]["execution_id"] = "different"
    elif variant == "duplicate-evidence":
        terminal["provider_final_off_evidence"]["evidence_id"] = " canonical "
    elif variant == "blank-evidence":
        terminal["physical_completion_evidence"]["evidence_id"] = " \u00a0\t"
    elif variant == "non-authoritative":
        terminal["provider_final_off_evidence"]["authoritative"] = False
    elif variant == "water-unknown":
        terminal["physical_completion_evidence"]["water_flow_stopped"] = None
    elif variant == "unverified":
        terminal["shutdown_verified"] = False
    elif variant == "containment":
        terminal["action"] = "contain_borehole"
    elif variant == "malformed-evidence":
        terminal["canonical_completion_evidence"] = ["invalid"]
    history.seed([{"action": "claim_borehole_before_on", "execution_id": "pending"}, terminal])
    result = history.compare("load_active_borehole")
    if variant == "malformed-evidence":
        assert result.error[1] == "AttributeError"
    else:
        assert result.error is None
        assert (result.value is None) == (variant in {"physical", "provider-app"})
    assert result.after["rows"] == 2


@pytest.mark.parametrize("load,claim,active", FAMILIES)
def test_replay_order_and_inactive_rows_preserve_latest_candidate(history, load, claim, active):
    latest = {"action": active, "execution_id": "new", "state": "Active", "evidence": "latest"}
    # Insert out of timestamp order; duplicate replays must not resurrect older work.
    history.seed([latest, deepcopy(latest)], start=200)
    history.seed([{"action": claim, "execution_id": "old"}], start=-200)
    history.seed([{"action": active, "execution_id": "inactive", "state": "Idle"}], start=400)
    history.seed([{"action": "record_eligibility", "execution_id": "noise"}], start=600)
    if load == "load_active_auxiliary":
        # Independent auxiliary work must all survive the replay reducer. A
        # scalar read cannot silently choose one when identity is ambiguous.
        ambiguous = history.compare(load)
        assert ambiguous.error[1] == "RootlineExecutionStoreUnavailable"
        assert "auxiliary_device_selector_required" in ambiguous.error[2]
        result = history.compare("load_active_auxiliaries")
        assert result.error is None and result.value == [latest, {
            "action": claim, "execution_id": "old", "state": "claimed_recovery_required"}]
    else:
        result = history.compare(load)
        assert result.error is None and result.value == latest
    assert result.before["rows"] == 5 and result.after["rows"] == 4


@pytest.mark.parametrize("terminal_first", [False, True])
def test_same_timestamp_claim_and_terminal_replay_is_closed_in_either_order(history, terminal_first):
    claim = {"action": "claim_before_on", "execution_id": "same-time"}
    terminal = {"action": "record_completed", "execution_id": "same-time"}
    rows = [claim, terminal, deepcopy(claim), deepcopy(terminal)]
    history.seed(list(reversed(rows)) if terminal_first else rows, same_time=True)
    result = history.compare("load_active")
    assert result.error is None and result.value is None
    # No tie-breaker is introduced: distinct active identities tied on created_at
    # retain the old query's unspecified relative ordering.


@pytest.mark.parametrize("load,claim,active", FAMILIES)
def test_legacy_json_string_claim_and_active_are_processed(history, load, claim, active):
    running = {"action": active, "execution_id": "legacy", "state": "Active"}
    history.seed([json.dumps({"action": claim, "execution_id": "legacy"}), json.dumps(running)])
    result = history.compare(load)
    assert result.error is None and result.value == running
    assert result.after["rows"] == 2


@pytest.mark.parametrize("raw", [
    {}, {"rootline_execution": None}, {"rootline_execution": True},
    {"rootline_execution": 17}, {"rootline_execution": []},
    {"rootline_execution": "not-json"}, {"rootline_execution": "[]"},
    {"rootline_execution": "null"}, {"rootline_execution": "17"},
    {"rootline_execution": {"action": []}},
    {"rootline_execution": {"action": {"unexpected": "action"}}},
])
@pytest.mark.parametrize("load,claim,active", FAMILIES)
def test_malformed_envelopes_and_actions_still_fail_closed(history, raw, load, claim, active):
    history.seed([{"action": claim, "execution_id": "still-pending"}])
    history.seed([raw], start=50, raw=True)
    result = history.compare(load)
    assert result.error is not None
    assert result.after["rows"] == 2


@pytest.mark.parametrize("envelope", [{}, {"action": None}, {"action": False}, {"action": 27}])
@pytest.mark.parametrize("load,claim,active", FAMILIES)
def test_non_string_scalar_or_missing_actions_keep_previous_behavior(history, envelope, load, claim, active):
    pending = {"action": claim, "execution_id": "pending"}
    history.seed([pending, envelope])
    result = history.compare(load)
    assert result.error is None and result.value == {**pending, "state": "claimed_recovery_required"}
    assert result.after["rows"] == 2

@pytest.mark.parametrize("load,claim,active", FAMILIES)
def test_legacy_json_string_terminal_still_closes_the_matching_claim(history, load, claim, active):
    if load == "load_active_borehole":
        terminal = completion()
    else:
        terminal = {"action": "record_completed" if load == "load_active" else "record_auxiliary_completed",
                    "execution_id": "pending"}
    history.seed([json.dumps(terminal)], start=-100)
    history.seed([{"action": claim, "execution_id": "pending"}], start=100)
    result = history.compare(load)
    assert result.error is None and result.value is None
    assert result.after["rows"] == 2
