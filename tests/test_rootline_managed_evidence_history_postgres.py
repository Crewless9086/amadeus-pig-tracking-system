"""Differential PostgreSQL checks for managed-device history projection.

Only the reference's first SELECT is replaced. Both paths use the real bounded
connector, actual production reducers and fixed NOW. Metrics are reserialized
JSON payload bytes per query, not protocol bytes or live billing savings.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

from modules.oom_sakkie import bounded_postgres_read as bounded
from modules.telemetry import rootline_water_energy_plan as plan

pytestmark = pytest.mark.skipif(
    not os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL"),
    reason="disposable ROOTLINE PostgreSQL URL is required",
)
NOW = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)
BASE = datetime(2000, 1, 1, tzinfo=timezone.utc)
OLD_EXECUTION_QUERY = """select review_json->'rootline_execution'
    from public.sam_live_stock_conversation_review_events
    where event_source='rootline_irrigation_execution'
    order by created_at,review_event_id"""


class MeasuredCursor:
    def __init__(self, cursor, reference, metrics):
        self.cursor, self.reference, self.metrics = cursor, reference, metrics
        self.query_index = 0

    def __enter__(self):
        self.cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self.cursor.__exit__(*args)

    def execute(self, query, params=None):
        assert self.query_index < 2
        self.label = ("executions", "outcomes")[self.query_index]
        self.query_index += 1
        if self.reference and self.label == "executions":
            query = OLD_EXECUTION_QUERY
        self.metrics[self.label]["query"] = query
        self.metrics[self.label]["selects"] += 1
        return self.cursor.execute(query, params)

    def fetchall(self):
        rows = self.cursor.fetchall()
        self.metrics[self.label]["rows"] = len(rows)
        self.metrics[self.label]["json_payload_bytes"] = sum(
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
def history(monkeypatch, record_property):
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    from psycopg.types.json import Jsonb

    # This fixture never uses DATABASE_URL or a default connector/remote host.
    # A fresh database avoids rewriting hard-coded production event sources or
    # deleting from the canonical append-only event table between cases.
    admin_url = os.environ["ROOTLINE_DISPOSABLE_POSTGRES_URL"]
    target = conninfo_to_dict(admin_url)
    assert target.get("host") == "127.0.0.1"
    assert target.get("port", "").isdigit() and 0 < int(target["port"]) < 65536
    assert target.get("dbname") == "rootline_managed"
    name = "rootline_managed_test_" + uuid.uuid4().hex
    fixture_url = make_conninfo(admin_url, dbname=name)

    def check_admin(connection):
        assert connection.info.host == target["host"]
        assert connection.info.port == int(target["port"])
        assert connection.info.dbname == target["dbname"]
        assert name.startswith("rootline_managed_test_") and name != target["dbname"]

    with psycopg.connect(admin_url, autocommit=True, connect_timeout=3) as admin:
        check_admin(admin)
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        migration = Path(__file__).resolve().parents[1] / "supabase/migrations/202607070001_create_sam_live_stock_conversation_review_events.sql"
        with psycopg.connect(fixture_url, connect_timeout=3) as connection:
            connection.execute(migration.read_text(encoding="utf-8"))
        real_factory = bounded.connect_bounded_read
        serial = 0

        def seed(values, *, outcomes=False, start=0, same_time=False, reverse_insert=False,
                 state="completed", raw=False):
            nonlocal serial
            rows = []
            for index, value in enumerate(values):
                serial += 1
                if raw:
                    body = value
                elif outcomes:
                    body = {"rootline_operational_intake": {"state": state, "outcome": value}}
                else:
                    body = {"rootline_execution": value}
                rows.append((f"managed-test-{serial:08d}",
                    "oom_sakkie_rootline_operational_intake" if outcomes else "rootline_irrigation_execution",
                    Jsonb(body), BASE + timedelta(seconds=start + (0 if same_time else index))))
            with psycopg.connect(fixture_url, connect_timeout=3) as connection:
                with connection.cursor() as cursor:
                    cursor.executemany("""insert into public.sam_live_stock_conversation_review_events
                        (review_event_id,event_source,review_json,created_at)
                        values (%s,%s,%s,%s)""", list(reversed(rows)) if reverse_insert else rows)

        def run(reference):
            metrics = {label: {"selects": 0, "rows": 0, "json_payload_bytes": 0}
                       for label in ("executions", "outcomes")}
            connections = []

            @contextmanager
            def measured_factory(**kwargs):
                assert kwargs == {"database_url": fixture_url}
                with real_factory(**kwargs) as connection:
                    assert connection.info.dbname == name
                    connections.append(connection)
                    yield MeasuredConnection(connection, reference, metrics)

            with monkeypatch.context() as patch:
                patch.setattr(bounded, "connect_bounded_read", measured_factory)
                try:
                    result = (plan._read_managed_device_evidence(fixture_url, NOW), None)
                except Exception as exc:
                    result = (None, (type(exc).__module__, type(exc).__name__, str(exc)))
            assert len(connections) == 1 and connections[0].closed
            assert metrics["executions"]["selects"] == metrics["outcomes"]["selects"] == 1
            return result, metrics

        def compare():
            old, before = run(True)
            new, after = run(False)
            assert new == old
            assert after["executions"]["rows"] <= before["executions"]["rows"]
            assert after["executions"]["json_payload_bytes"] <= before["executions"]["json_payload_bytes"]
            assert after["outcomes"] == before["outcomes"]
            for phase, queries in (("before", before), ("after", after)):
                for label, metrics in queries.items():
                    for key, value in metrics.items():
                        if key != "query":
                            record_property(f"{phase}_{label}_{key}", value)
            return SimpleNamespace(value=new[0], error=new[1], before=before, after=after)

        yield SimpleNamespace(seed=seed, compare=compare, fixture_url=fixture_url)
    finally:
        # All test connections have exited. No FORCE, termination or broad cleanup.
        with psycopg.connect(admin_url, autocommit=True, connect_timeout=3) as admin:
            check_admin(admin)
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            assert admin.execute("select count(*) from pg_database where datname=%s", (name,)).fetchone()[0] == 0
        record_property("owned_fixture_database_removed", True)


def active(identity="zone-run", zone="B12345"):
    return {"action": "mark_active", "state": "Active", "execution_id": identity,
        "zone_id": zone, "device_id": "100204e9bc", "channel": 1 if zone == "B12345" else 2,
        "job_id": "synthetic-job", "job_sha256": "a" * 64, "segment_identity": "synthetic-segment",
        "evidence_generation": "synthetic-plan", "primary_stop_deadline": (NOW + timedelta(minutes=30)).isoformat(),
        "start_evidence": {"authoritative": True, "state": "ON", "evidence_id": "synthetic-on",
                           "observed_at": (NOW - timedelta(minutes=20)).isoformat()}}


def completed_auxiliary(identity="mix", device_type="fertilizer_mixer", **extra):
    return {"action": "record_auxiliary_completed", "execution_id": identity,
        "auxiliary_device_id": "FERTILIZER-MIXER-CH2" if device_type == "fertilizer_mixer" else "FERTILIZER-INJECTION-CH1",
        "device_type": device_type, "shutdown_verified": True, "zone_execution_id": "zone-run",
        "control_completed": True, "pulse_number": 1,
        "completed_at": (NOW - timedelta(minutes=5)).isoformat(),
        "shutdown_evidence": {"state": "OFF", "authoritative": True,
            "retrieved_at": (NOW - timedelta(minutes=5)).isoformat(), "evidence_id": identity + "-off"}, **extra}


def interlocks(when=NOW, **extra):
    return {"observed_at": when.isoformat(), "dry_run_safe": True, "low_water_clear": True,
        "supply_pressure_safe": True, "full_tank_not_blocking": True, **extra}


def need(value=True, when=NOW):
    return {"fertilizer_needed": value, "fertilizer_need_observed_at": when.isoformat()}


@pytest.mark.parametrize("zone", ["B12345", "C12345"])
def test_unrelated_heavy_history_preserves_old_unfinished_run_and_all_outcomes(history, zone):
    history.seed([active(zone=zone)], start=-86400 * 365)
    history.seed([{"action": "record_eligibility", "execution_id": f"noise-{i}",
                   "evidence": "synthetic unrelated planning evidence " * 80} for i in range(1500)])
    history.seed([completed_auxiliary(), completed_auxiliary("pulse", "fertilizer_injection_valve")], start=2000)
    outcomes = [{"fertilizer_batch_observation": {"event_type": "fertilizer_batch_prepared",
                    "observed_at": (NOW - timedelta(hours=2)).isoformat()}},
                need(), {"provider_message_id":"synthetic-safe-1","borehole_interlocks": interlocks()}]
    history.seed(outcomes, outcomes=True)
    result = history.compare()
    assert result.error is None and result.value["status"] == "Available"
    assert result.value["active_irrigation_context"]["zone_execution_id"] == "zone-run"
    assert result.value["active_irrigation_context"]["active_zone_ids"] == [zone]
    assert result.value["active_irrigation_context"]["completed_pulses"] == 1
    assert len(result.value["fertilizer_executions"]) == 2
    assert result.value["borehole_interlocks"] == interlocks()
    assert result.before["executions"]["rows"] == 1503 and result.after["executions"]["rows"] == 3
    assert result.after["executions"]["json_payload_bytes"] < result.before["executions"]["json_payload_bytes"] // 100
    assert result.after["outcomes"]["rows"] == 3


@pytest.mark.parametrize("action", ["record_completed", "record_ambiguous_shutdown", "record_claim_recovery", "contain_zone"])
@pytest.mark.parametrize("verified", [None, False, True, "true"])
def test_existing_terminal_semantics_are_not_changed(history, action, verified):
    history.seed([active(), {"action": action, "execution_id": "zone-run", "shutdown_verified": verified}])
    result = history.compare()
    assert result.error is None
    # Managed projection already treats ambiguous shutdown/claim recovery as
    # terminal regardless of verification; this efficiency change preserves it.
    closes = action != "contain_zone" or verified is True
    assert (result.value["active_irrigation_context"] is None) == closes
    assert result.after["executions"]["rows"] == 2


@pytest.mark.parametrize("device_type", ["fertilizer_mixer", "fertilizer_injection_valve", "borehole_pump_power"])
@pytest.mark.parametrize("verified", [None, False, True, "true"])
def test_auxiliary_completion_types_and_verification_are_preserved(history, device_type, verified):
    item = completed_auxiliary(device_type=device_type, shutdown_verified=verified)
    history.seed([active(), item])
    result = history.compare()
    assert result.error is None
    # Preserve uncertain reservations in the ledger: discarding them could
    # restart a mixer indefinitely. Consumers still require exact proof.
    assert result.value["fertilizer_executions"] == [item]
    context=result.value["active_irrigation_context"]
    assert context["completed_pulses"] == (1 if verified is True and device_type == "fertilizer_injection_valve" else 0)


@pytest.mark.parametrize("changes", [
    {"device_id": "100204d497", "channel": 2}, {"channel": 2}, {"channel": "1"},
    {"zone_id": "Unknown"}, {"start_evidence": {"authoritative": False, "state": "ON", "evidence_id": "untrusted"}},
    {"start_evidence": ["malformed"]}, {"state": "Idle"},
])
def test_wrong_device_binding_or_inactive_run_cannot_unlock_context(history, changes):
    history.seed([{**active(), **changes}])
    result = history.compare()
    assert result.error is None and result.value["active_irrigation_context"] is None


def test_batch_need_and_interlock_chronology_remains_exact(history):
    prepared = {"event_type": "fertilizer_batch_prepared", "observed_at": (NOW - timedelta(hours=2)).isoformat(),
                "batch_generation": "reported-batch", "recipe": "synthetic recipe"}
    refill = {"event_type": "water_only_refill", "observed_at": (NOW - timedelta(hours=1)).isoformat()}
    old_batch = {"event_type": "fertilizer_batch_prepared", "observed_at": (NOW - timedelta(days=8)).isoformat()}
    history.seed([active(), completed_auxiliary(batch_generation="reported-batch"),
                  completed_auxiliary("wrong-batch", batch_generation="other-batch")])
    history.seed([{**need(True), "fertilizer_batch_observation": old_batch,
                   "borehole_interlocks": interlocks(NOW - timedelta(minutes=14))},
                  {**need(False), "fertilizer_batch_observation": prepared,
                   "borehole_interlocks": interlocks(supply_pressure_safe=False)},
                  {**need(True, NOW + timedelta(seconds=1)), "fertilizer_batch_observation": refill,
                   "borehole_interlocks": interlocks(NOW + timedelta(seconds=1))},
                  {**need(True, NOW - timedelta(hours=25)), "borehole_interlocks": interlocks(NOW - timedelta(minutes=16))},
                  {**need("true"), "borehole_interlocks": interlocks(dry_run_safe="true")}],
                 outcomes=True, reverse_insert=True)
    # Excluded intake states must stay excluded, irrespective of fresh payload.
    history.seed([need(True)], outcomes=True, start=100, state="waiting_for_confirmation")
    result = history.compare()
    assert result.error is None
    assert result.value["fertilizer_batch_observations"] == [old_batch, prepared, refill]
    assert result.value["active_irrigation_context"]["fertilizer_needed"] is False
    # Unattributed positive assertions cannot clear/establish safe facts;
    # the attributable unsafe fact is retained independently of omissions.
    assert result.value["borehole_interlocks"] == {
        "observed_at":NOW.isoformat(),"supply_pressure_safe":False}
    assert result.after["outcomes"]["rows"] == 5


@pytest.mark.parametrize("reverse_insert", [False, True])
def test_replays_and_same_timestamp_use_existing_event_id_order(history, reverse_insert):
    newer = active(identity="second", zone="C12345")
    # Existing dictionary insertion order keeps the second identity last even
    # when a later replay updates the first identity's value.
    history.seed([active(), newer, {**active(), "evidence_generation": "replayed"}],
                 same_time=True, reverse_insert=reverse_insert)
    pulse = completed_auxiliary("pulse", "fertilizer_injection_valve", zone_execution_id="second")
    history.seed([pulse, deepcopy(pulse)], same_time=True, start=20, reverse_insert=reverse_insert)
    history.seed([need(True), need(False)], outcomes=True, same_time=True, reverse_insert=reverse_insert,
                 state="contextual_followup_completed")
    result = history.compare()
    assert result.error is None
    context = result.value["active_irrigation_context"]
    assert context["zone_execution_id"] == "second" and context["fertilizer_needed"] is False
    assert context["completed_pulses"] == 1  # Same execution replay is one pulse.


@pytest.mark.parametrize("action", ["mark_active", "record_auxiliary_completed", "record_completed",
                                    "record_ambiguous_shutdown", "record_claim_recovery", "contain_zone"])
def test_legacy_json_string_relevant_execution_is_still_processed(history, action):
    row = active() if action == "mark_active" else completed_auxiliary() if action == "record_auxiliary_completed" else {
        "action": action, "execution_id": "zone-run", "shutdown_verified": True}
    history.seed([active(), json.dumps(row)])
    history.seed([json.dumps(need(True))], outcomes=True)
    result = history.compare()
    assert result.error is None
    if action == "record_auxiliary_completed":
        assert result.value["fertilizer_executions"] == [row]
    elif action == "mark_active":
        # Standing programme does not manufacture a prepared physical batch.
        assert result.value["active_irrigation_context"]["fertilizer_needed"] is False
    else:
        assert result.value["active_irrigation_context"] is None
    assert result.after["executions"]["rows"] == 2


@pytest.mark.parametrize("value", [None, True, 17, [], "not-json", "[]", "null", "17", {},
                                  {"action": None}, {"action": False}, {"action": 27}])
def test_malformed_or_non_string_execution_values_keep_previous_ignored_behavior(history, value):
    history.seed([active(), value])
    result = history.compare()
    assert result.error is None and result.value["active_irrigation_context"] is not None
    assert result.after["executions"]["rows"] == 2


@pytest.mark.parametrize("action", [[], {"unexpected": "action"}])
@pytest.mark.parametrize("legacy", [False, True])
def test_malformed_action_with_identity_still_raises_after_read_cleanup(history, action, legacy):
    row = {"action": action, "execution_id": "nonempty"}
    history.seed([active(), json.dumps(row) if legacy else row])
    result = history.compare()
    assert result.error[1] == "TypeError"
    assert result.after["executions"]["rows"] == 2


@pytest.mark.parametrize("outcome", [None, [], "invalid-json", {"fertilizer_batch_observation": []},
                                    {"fertilizer_batch_observation": {"event_type": "water_only_refill", "observed_at": "invalid"}},
                                    {"borehole_interlocks": []}, {"fertilizer_needed": True, "fertilizer_need_observed_at": "invalid"}])
def test_malformed_outcomes_keep_previous_projection(history, outcome):
    history.seed([active()])
    history.seed([outcome], outcomes=True)
    result = history.compare()
    assert result.error is None and result.value["borehole_interlocks"] is None
    assert result.value["fertilizer_batch_observations"] == []
    assert result.value["active_irrigation_context"]["fertilizer_needed"] is False
    assert result.after["outcomes"]["rows"] == 1


@pytest.mark.parametrize("kind", [[], {}])
def test_malformed_batch_event_type_preserves_existing_failure(history, kind):
    history.seed([{"fertilizer_batch_observation": {"event_type": kind, "observed_at": NOW.isoformat()}}], outcomes=True)
    result = history.compare()
    assert result.error[1] == "TypeError"


@pytest.fixture
def grid_store(history,monkeypatch):
    """Actual production SQL in a fresh loopback-only database and real schema."""
    import psycopg
    from modules.telemetry.rootline_irrigation_execution_store import rootline_irrigation_execution_store
    from modules.telemetry.rootline_energy_policy import managed_energy_decision
    url=history.fixture_url; monkeypatch.setenv("DATABASE_URL",url)
    with psycopg.connect(url) as connection:
        connection.execute("create schema if not exists app_private")
        connection.execute("create table app_private.migration_log(migration_id text primary key,description text)")
        for role in ("anon","authenticated"):
            if not connection.execute("select 1 from pg_roles where rolname=%s",(role,)).fetchone():
                from psycopg import sql
                connection.execute(sql.SQL("create role {}").format(sql.Identifier(role)))
        connection.execute(Path("supabase/migrations/202608170001_add_rootline_device_registry.sql").read_text(encoding="utf-8"))
        connection.execute("""insert into app_private.rootline_standing_authorities
            (standing_authority_id,version,issuer,policy_sha256,active,policy_payload)
            values('synthetic-grid','1','synthetic-owner',%s,true,'{}')""",("a"*64,))
        connection.execute("""insert into app_private.rootline_device_registry
            (device_key,contract_version,device_record,commissioning_stage,standing_authority_id,
                standing_authority_version,evidence_digest,registry_generation)
            values('ifttt_smartlife:smartlife_owner_account:synthetic-grid-001:1','rootline_device_spine.v1',
                '{}','standing_active','synthetic-grid','1',%s,1)""",("a"*64,))
    def body(identity="synthetic-grid-run",expected=None,age_seconds=0):
        now=datetime.now(timezone.utc)
        power={"observed_at":(now-timedelta(seconds=age_seconds)).isoformat(),
            "battery_soc_pct":29,"solar_power_w":0,"load_power_w":1000,
            "grid_power_w":0,"battery_power_w":1000,"battery_state":"discharging"}
        return {"execution_id":identity,"device_key":"ifttt_smartlife:smartlife_owner_account:synthetic-grid-001:1",
            "device_id":"synthetic-grid-001","desired_state":"ON","expected_transition_id":expected,
            "baseline_sha256":"a"*64,"power_evidence":power,
            "decision":managed_energy_decision(power,now=now),"previous_readback":{
                "authoritative":True,"device_id":"synthetic-grid-001","state":"OFF",
                "retrieved_at":now.isoformat(),"evidence_id":"synthetic-off"}}
    def readback():
        # Use the disposable database clock for this synthetic provider receipt;
        # Windows and the container may have distinct subsecond clock offsets.
        with psycopg.connect(url) as connection:
            observed=connection.execute("select clock_timestamp()").fetchone()[0]
        return {"authoritative":True,"device_id":"synthetic-grid-001","state":"ON",
            "retrieved_at":observed.isoformat(),"evidence_id":"synthetic-on"}
    return SimpleNamespace(store=rootline_irrigation_execution_store,body=body,readback=readback,url=url)


def test_grid_stale_observer_cannot_claim_after_completed_transition(grid_store):
    g=grid_store; first=g.body(); stale=g.body("stale-observer")
    assert g.store("claim_eskom_before_command",first)["created"]
    edge=g.store("dispatch_eskom_command_edge",{**first,"dispatch":lambda:{"accepted_unambiguous":True}})
    assert edge["dispatched"]
    assert g.store("record_eskom_completed",{**first,"readback":g.readback()})["success"]
    refused=g.store("claim_eskom_before_command",stale)
    assert not refused["created"] and refused["status"]=="eskom_observation_version_changed"


def test_grid_final_edge_fences_sender_and_requires_post_return_observation(grid_store):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    g=grid_store; body=g.body();entered=Event();release=Event()
    assert g.store("claim_eskom_before_command",body)["created"]
    def send():
        entered.set(); assert release.wait(2)
        return {"accepted_unambiguous":True}
    with ThreadPoolExecutor(max_workers=2) as pool:
        edge=pool.submit(g.store,"dispatch_eskom_command_edge",{**body,"dispatch":send})
        assert entered.wait(2)
        premature=g.readback()
        completion=pool.submit(g.store,"record_eskom_completed",{**body,"readback":premature})
        assert not completion.done()
        release.set()
        assert edge.result(timeout=3)["dispatched"]
        assert not completion.result(timeout=3)["success"]
    assert g.store("record_eskom_completed",{**body,"readback":g.readback()})["success"]
    assert not g.store("dispatch_eskom_command_edge",{**body,
        "dispatch":lambda:pytest.fail("completed sender cannot replay")})["dispatched"]


def test_grid_crash_without_outcome_cannot_complete_or_resend(grid_store):
    g=grid_store;body=g.body();assert g.store("claim_eskom_before_command",body)["created"]
    calls=[]
    def interrupted():
        calls.append("one attempt");raise RuntimeError("synthetic interruption before durable outcome")
    with pytest.raises(RuntimeError):
        g.store("dispatch_eskom_command_edge",{**body,"dispatch":interrupted})
    assert not g.store("record_eskom_completed",{**body,"readback":g.readback()})["success"]
    assert not g.store("claim_eskom_before_command",g.body("replacement"))["created"]
    assert not g.store("dispatch_eskom_command_edge",{**body,
        "dispatch":lambda:pytest.fail("interrupted sender cannot replay")})["dispatched"]
    assert len(calls)==1


def test_grid_final_edge_rechecks_energy_after_waiting_for_lock(grid_store):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    import psycopg
    g=grid_store;body=g.body(age_seconds=901)
    # Simulate the previously fresh decision retained while provider calls took
    # it beyond the 15-minute boundary. Production SQL reevaluates raw evidence.
    body["decision"]={**body["decision"],"fresh":True,"eskom_requested_state":"ON"}
    assert g.store("claim_eskom_before_command",body)["created"]
    result=g.store("dispatch_eskom_command_edge",{**body,"dispatch":lambda:pytest.fail("stale edge cannot send")})
    assert not result["dispatched"] and result["status"]=="eskom_edge_evidence_stale"
