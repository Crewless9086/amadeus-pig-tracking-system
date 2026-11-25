"""Real append-only intake, CAS, replay and command-lock tests; local DB only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import threading
import time
from urllib.parse import urlparse

import psycopg
import pytest

from modules.telemetry import rootline_owner_controls as controls
from modules.telemetry import rootline_water_energy_plan as planner
from modules.telemetry import rootline_irrigation_execution_store as execution_store
from modules.telemetry.rootline_timed_control import timed_control_scope
from tests.test_rootline_command_mode import ENV, start
from tests.test_rootline_water_energy_plan import daily_program_facts

ACTOR = "owner-admin:isolated-sql"


@pytest.fixture(scope="module")
def database_url():
    url = os.getenv("ROOTLINE_OWNER_CONTROL_TEST_URL", "").strip()
    if not url:
        pytest.skip("ROOTLINE_OWNER_CONTROL_TEST_URL not configured")
    parsed = urlparse(url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.path.lstrip("/") not in {
            "rootline_owner_controls_test", "rootline_ha_command_mode_test"}:
        pytest.fail("Owner control SQL tests require an explicitly named local disposable database")
    migrations = Path("supabase/migrations")
    with psycopg.connect(url) as connection:
        for role in ("anon", "authenticated", "service_role"):
            connection.execute(f"do $$ begin create role {role} nologin; exception when duplicate_object then null; end $$")
        connection.execute((migrations / "202605210001_foundation_migration_log.sql").read_text("utf-8"))
        connection.execute((migrations / "202607070001_create_sam_live_stock_conversation_review_events.sql").read_text("utf-8"))
        if connection.execute("select to_regclass('public.rootline_water_energy_plan_identities')").fetchone()[0] is None:
            connection.execute((migrations / "202607280001_create_rootline_water_energy_plans.sql").read_text("utf-8"))
    return url


@pytest.fixture
def sql(database_url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    with psycopg.connect(database_url) as connection:
        connection.execute("truncate public.sam_live_stock_conversation_review_events, public.rootline_water_energy_plan_generations, public.rootline_water_energy_plan_identities cascade")
    return database_url


def clock():
    return datetime.now(timezone.utc)


def settings_request(url, *, device="borehole", mode="automatic", scope="ongoing", fields=None, now=None, key="preview-settings-001"):
    now = now or clock()
    state = controls.load_runtime_owner_controls(url, now=now)
    if fields is None:
        fields = {"solar_proxy_w": 1800, "battery_floor_pct": 30}
    return {"kind": "settings", "device_id": device, "expected_revision": state["devices"][device]["revision"],
        "reason": "Isolated owner setting", "idempotency_key": key,
        "changes": {"mode": mode, "scope": scope, "fields": fields}}


def preview_apply(url, body, *, now=None, key="apply-settings-001"):
    preview, status = controls.preview_owner_control(body, ACTOR, database_url=url, now=now)
    assert status == 200, preview
    payload = {"preview_id": preview["preview"]["id"], "preview_digest": preview["preview"]["digest"], "idempotency_key": key}
    receipt, status = controls.apply_owner_control(payload, ACTOR, database_url=url, now=now)
    assert status == 200, receipt
    return receipt, payload


def seed_program(url, now=None):
    now = now or clock().astimezone(planner.ZA_TZ).replace(hour=8, minute=0, second=0, microsecond=0)
    with timed_control_scope(ENV):
        plan = planner.build_daily_program(daily_program_facts(now), now.date().isoformat(), now=now)
    saved, status = planner.append_water_energy_plan(plan, ACTOR, database_url=url)
    assert status == 201, saved
    return saved, now


def test_persisted_settings_replay_and_expiry_restore(sql):
    now = clock()
    receipt, payload = preview_apply(sql, settings_request(sql, now=now), now=now)
    state = controls.load_runtime_owner_controls(sql, now=now)
    assert state["devices"]["borehole"]["fields"]["solar_proxy_w"] == 1800
    replay, status = controls.apply_owner_control(payload, ACTOR, database_url=sql, now=now + timedelta(days=2))
    assert status == 200 and replay == receipt
    later = now + timedelta(seconds=1)
    preview_apply(sql, settings_request(sql, mode="paused", scope="today", now=later,
        key="preview-temporary-002", fields={"solar_proxy_w": 2000, "battery_floor_pct": 40}), now=later, key="apply-temporary-002")
    assert controls.load_runtime_owner_controls(sql, now=later)["devices"]["borehole"]["mode"] == "paused"
    restored = controls.load_runtime_owner_controls(sql, now=controls._midnight(now))["devices"]["borehole"]
    assert restored["mode"] == "automatic" and restored["fields"]["solar_proxy_w"] == 1800
    with psycopg.connect(sql) as connection:
        assert connection.execute("select count(*) from public.sam_live_stock_conversation_review_events where review_json->'rootline_operational_intake'->>'state'='confirmed'").fetchone()[0] == 2


def test_concurrent_duplicate_apply_commits_one_canonical_decision(sql):
    now = clock()
    preview, status = controls.preview_owner_control(settings_request(sql, now=now), ACTOR, database_url=sql, now=now)
    assert status == 200
    payload = {"preview_id": preview["preview"]["id"], "preview_digest": preview["preview"]["digest"], "idempotency_key": "same-apply-request"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: controls.apply_owner_control(payload, ACTOR, database_url=sql), range(2)))
    assert all(status == 200 for _, status in results), results
    assert results[0][0] == results[1][0]
    with psycopg.connect(sql) as connection:
        assert len([r for r in controls._read_records(connection) if r["state"] == "confirmed"]) == 1


def test_plan_priority_duration_skip_persist_and_drive_real_live_projection(sql):
    saved, now = seed_program(sql)
    with psycopg.connect(sql) as connection:
        projection = controls.get_owner_plan(connection, now)
    rows = [{key: row[key] for key in ("id", "order", "duration_minutes", "priority", "reason", "skip")} for row in projection["rows"]]
    for row in rows:
        row.update(duration_minutes=20, priority="high" if row["id"] == "irrigation_B12345" else "normal",
            skip=row["id"] == "irrigation_E12345", reason="Owner changed remaining work")
    body = {"kind": "plan", "expected_revision": projection["revision"], "reason": "Prioritize Camp B", "idempotency_key": "preview-plan-001", "changes": {"rows": rows}}
    receipt, _ = preview_apply(sql, body, now=now, key="apply-plan-001")
    current, _ = planner.get_current_water_energy_plan(saved["operating_date"], sql)
    assert current["generation"] == saved["generation"] + 1
    tasks = [t for t in current["daily_program"]["base_tasks"] if t["task_id"].startswith("irrigation_")]
    assert tasks[0]["task_id"] == "irrigation_B12345" and tasks[0]["scheduled_order"] == 1
    assert tasks[0]["planned_duration_minutes"] == 20
    facts = daily_program_facts(now)
    facts["owner_controls"] = controls.load_runtime_owner_controls(sql, now=now)
    with timed_control_scope(ENV):
        live = planner.project_saved_program_for_execution(current, facts, now=now)
    skipped = next(t for t in live["candidate_tasks"] if t["task_id"] == "irrigation_E12345")
    assert skipped["owner_skip"] and skipped["zone_decision"] == "Hold"
    # The final claim/ON boundary independently consumes current saved skip.
    with psycopg.connect(sql) as connection:
        assert controls.owner_start_allowed(connection, "E12345", now=now,
            execution={"execution_id": "stale-prepared", "planned_runtime_seconds": 1200}) is False


def test_manual_request_consumes_once_and_expired_binding_cannot_dispatch(sql):
    now = clock()
    preview_apply(sql, settings_request(sql, mode="manual_today", scope="today", now=now), now=now)
    state = controls.load_runtime_owner_controls(sql, now=now)
    body = {"kind": "run", "device_id": "borehole", "expected_revision": state["devices"]["borehole"]["revision"],
        "reason": "One safe supply run", "idempotency_key": "preview-manual-001", "changes": {}}
    receipt, _ = preview_apply(sql, body, now=now, key="apply-manual-001")
    assert receipt["status"] == "queued"
    execution = {"execution_id": "isolated-manual-execution"}
    with psycopg.connect(sql) as connection, connection.cursor() as cursor:
        execution_store._insert_managed_event(cursor, "record_borehole_eligibility", {**execution,
            "energy_context": {"owner_energy_policy_sha256": controls.energy_policy_digest("borehole", state, now)}})
    with psycopg.connect(sql) as connection:
        controls._lock(connection)
        assert controls.bind_owner_start(connection, "BOREHOLE-1-MINI-R4-CH1", execution)
    with psycopg.connect(sql) as connection:
        assert controls.owner_start_allowed(connection, "BOREHOLE-1-MINI-R4-CH1", execution=execution)
        assert not controls.owner_start_allowed(connection, "BOREHOLE-1-MINI-R4-CH1", execution=execution, now=controls._midnight(now))
        assert not controls.bind_owner_start(connection, "BOREHOLE-1-MINI-R4-CH1", {"execution_id": "second-execution"})


def test_locked_on_edge_observes_pause_committed_while_reader_waits(sql, monkeypatch):
    now = clock()
    _, _, fixture_store, _, _ = start("A12345", at=now)
    claim = next(deepcopy(r) for r in fixture_store.rows if r["action"] == "claim_before_on")
    claim.pop("action", None)
    claim.pop("event_id", None)
    with psycopg.connect(sql) as connection:
        execution_store._write_terminal_review(connection, "claim_before_on", claim)
    blocker = psycopg.connect(sql)
    blocker.execute("select pg_advisory_xact_lock(%s)", (1874320911,))
    from modules.oom_sakkie import bounded_postgres_read
    original = bounded_postgres_read.connect_bounded_rootline_postgres
    entered = threading.Event()
    isolation = []
    def before_lock(**kwargs):
        isolation.append(kwargs.get("read_committed"))
        connection = original(**kwargs)
        connection.execute("select count(*) from public.sam_live_stock_conversation_review_events").fetchone()
        entered.set()
        return connection
    monkeypatch.setattr(bounded_postgres_read, "connect_bounded_rootline_postgres", before_lock)
    sent = []
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(execution_store._dispatch_managed_on_edge,
            {**claim, "dispatch": lambda: sent.append("ON") or {"accepted_unambiguous": True}}, borehole=False, irrigation=True)
        assert entered.wait(3)
        assert not future.done()
        context = {"actor": ACTOR, "request_id": "pause-race", "request_digest": "pause-race", "effective_at": clock().isoformat(),
            "expires_at": None, "change": {"kind": "settings", "device_id": "camp_a", "reason": "Pause before ON",
                "changes": {"mode": "paused", "scope": "ongoing", "fields": {"duration_minutes": 120}}}}
        controls._write(blocker, "pause-race", context, "confirmed", database_url=sql)
        blocker.commit()
        result = future.result(timeout=5)
    blocker.close()
    assert isolation and all(isolation)
    assert result["accepted_unambiguous"] is False and sent == []


def test_stop_saved_after_claim_is_not_on_authority(sql):
    now = clock()
    _, _, fixture_store, _, _ = start("A12345", at=now)
    claim = next(deepcopy(r) for r in fixture_store.rows if r["action"] == "claim_before_on")
    claim.pop("action", None)
    claim.pop("event_id", None)
    with psycopg.connect(sql) as connection:
        execution_store._write_terminal_review(connection, "claim_before_on", claim)
    state = controls.load_runtime_owner_controls(sql, now=now)
    body = {"kind": "stop", "device_id": "camp_a", "expected_revision": state["devices"]["camp_a"]["revision"],
        "reason": "Stop before provider send", "idempotency_key": "preview-stop-race", "changes": {}}
    receipt, _ = preview_apply(sql, body, now=now, key="apply-stop-race")
    assert receipt["status"] == "queued"
    sent = []
    result = execution_store._dispatch_managed_on_edge({**claim, "dispatch": lambda: sent.append("ON")}, borehole=False, irrigation=True)
    assert result["accepted_unambiguous"] is False and sent == []


def test_missing_plan_allows_mode_only_camp_pause(sql):
    now = clock()
    state = controls.load_runtime_owner_controls(sql, now=now)
    field = controls.owner_device_settings("camp_a", state, {}, now)["fields"][0]
    assert field["value"] is None and field["required"] is False
    preview_apply(sql, settings_request(sql, device="camp_a", mode="paused", fields={}, now=now), now=now)
    readback = controls.load_runtime_owner_controls(sql, now=now)["devices"]["camp_a"]
    assert readback["mode"] == "paused" and readback["fields"] == {}


def test_new_camp_duration_preserves_only_canonical_owned_parent_continuation(sql):
    now = clock()
    preview_apply(sql, settings_request(sql, device="camp_a", fields={"duration_minutes": 20}, now=now), now=now)
    prior = {"execution_id": "prior-segment", "zone_id": "A12345", "job_id": "owned-job", "segment_number": 1,
        "planned_runtime_seconds": 2400}
    with psycopg.connect(sql) as connection:
        execution_store._write_terminal_review(connection, "claim_before_on", prior)
    with psycopg.connect(sql) as connection:
        continuation = {"execution_id": "next-segment", "zone_id": "A12345", "job_id": "owned-job", "segment_number": 2,
            "planned_runtime_seconds": 2400}
        assert controls.owner_start_allowed(connection, "A12345", now=now, execution=continuation)
        assert not controls.owner_start_allowed(connection, "A12345", now=now, execution={**continuation, "job_id": "invented-job"})
        wrong_zone = controls.load_runtime_owner_controls(sql, now=now)
        wrong_zone["devices"]["camp_b"]["fields"] = {"duration_minutes": 20}
        assert not controls._owner_plan_gate(connection, "camp_b", continuation, now, controls=wrong_zone)
        assert not controls.owner_start_allowed(connection, "A12345", now=now, execution={**continuation, "segment_number": 1})


@pytest.mark.parametrize("lower_after_claim", [False, True])
def test_mixer_actual_claim_and_edge_do_not_double_charge_and_recheck_lower_limit(sql, monkeypatch, lower_after_claim):
    from tests.test_rootline_mixer_reservations import artifact, ENV as MIX_ENV
    for key, value in MIX_ENV.items():
        monkeypatch.setenv(key, value)
    now = clock()
    fields = {"reserve_soc_pct": 70, "session_minutes": 10, "daily_minutes": 10}
    preview_apply(sql, settings_request(sql, device="mixer", fields=fields, now=now), now=now)
    value, _, _ = artifact([], now=now, duration=600)
    assert value["eligible"], value
    with psycopg.connect(sql) as connection, connection.cursor() as cursor:
        execution_store._insert_managed_event(cursor, "record_auxiliary_eligibility", value)
    body = {key: value.get(key) for key in ("execution_id", "eligibility_id", "eligibility_sha256", "consumption_key",
        "auxiliary_device_id", "device_type", "device_id", "channel", "zone_id", "job_id", "job_sha256",
        "segment_identity", "zone_execution_id", "pulse_number", "phase_number", "batch_generation",
        "maximum_duration_seconds", "stop_mode", "acceptance_mode", "mixer_session")}
    body.update(claimed_at=now.isoformat(), primary_stop_deadline=(now + timedelta(seconds=600)).isoformat(),
        state="claimed", on_attempts=0, off_attempts=0)
    claimed = execution_store._claim_single_auxiliary(body)
    assert claimed["created"], claimed
    if lower_after_claim:
        later = clock()
        preview_apply(sql, settings_request(sql, device="mixer", fields={**fields, "session_minutes": 5},
            now=later, key="preview-lower-limit"), now=later, key="apply-lower-limit")
    sent = []
    result = execution_store._dispatch_managed_on_edge({**body,
        "dispatch": lambda: sent.append("ON") or {"accepted_unambiguous": True}}, borehole=False)
    assert result["accepted_unambiguous"] is (not lower_after_claim), result
    assert sent == ([] if lower_after_claim else ["ON"])
    replay = execution_store._dispatch_managed_on_edge({**body, "dispatch": lambda: sent.append("DUPLICATE")}, borehole=False)
    assert replay["accepted_unambiguous"] is False
    assert "DUPLICATE" not in sent


def test_energy_change_after_eligibility_holds_actual_on_edge(sql, monkeypatch):
    from tests.test_rootline_mixer_reservations import artifact, ENV as MIX_ENV
    from modules.telemetry.rootline_auxiliary_management import build_auxiliary_eligibility
    for key, value in MIX_ENV.items():
        monkeypatch.setenv(key, value)
    now = clock()
    fields = {"reserve_soc_pct": 80, "session_minutes": 10, "daily_minutes": 30}
    preview_apply(sql, settings_request(sql, device="mixer", fields=fields, now=now), now=now)
    _, context, safety = artifact([], now=now, duration=600)
    context["owner_energy_policy_sha256"] = controls.energy_policy_digest("mixer", controls.load_runtime_owner_controls(sql, now=now), now)
    with timed_control_scope(MIX_ENV):
        value = build_auxiliary_eligibility(task={"auxiliary_device_id": "FERTILIZER-MIXER-CH2", "planned_seconds": 600},
            context=context, safety=safety, flags={"ROOTLINE_FERTILIZER_MIXING_ENABLED": True}, now=now)
    assert value["eligible"]
    with psycopg.connect(sql) as connection, connection.cursor() as cursor:
        execution_store._insert_managed_event(cursor, "record_auxiliary_eligibility", value)
    body = {key: value.get(key) for key in ("execution_id", "eligibility_id", "eligibility_sha256", "consumption_key",
        "auxiliary_device_id", "device_type", "device_id", "channel", "zone_id", "job_id", "job_sha256",
        "segment_identity", "zone_execution_id", "pulse_number", "phase_number", "batch_generation",
        "maximum_duration_seconds", "stop_mode", "acceptance_mode", "mixer_session")}
    body.update(claimed_at=now.isoformat(), primary_stop_deadline=(now + timedelta(seconds=600)).isoformat(),
        state="claimed", on_attempts=0, off_attempts=0)
    assert execution_store._claim_single_auxiliary(body)["created"]
    with psycopg.connect(sql) as connection, connection.cursor() as cursor:
        assert controls.owner_start_allowed(cursor, "FERTILIZER-MIXER-CH2", execution=body)
    later = clock()
    preview_apply(sql, settings_request(sql, device="mixer", fields={**fields, "reserve_soc_pct": 90},
        now=later, key="preview-new-energy"), now=later, key="apply-new-energy")
    sent = []
    result = execution_store._dispatch_managed_on_edge({**body, "dispatch": lambda: sent.append("ON")}, borehole=False)
    assert result["accepted_unambiguous"] is False and sent == []


def test_borehole_nested_energy_binding_matches_and_changes_invalidate(sql):
    now = clock()
    preview_apply(sql, settings_request(sql, now=now), now=now)
    state = controls.load_runtime_owner_controls(sql, now=now)
    body = {"execution_id": "nested-borehole-eligibility"}
    with psycopg.connect(sql) as connection, connection.cursor() as cursor:
        execution_store._insert_managed_event(cursor, "record_borehole_eligibility", {**body,
            "energy_context": {"owner_energy_policy_sha256": controls.energy_policy_digest("borehole", state, now)}})
    with psycopg.connect(sql) as connection:
        assert controls.owner_start_allowed(connection, "BOREHOLE-1-MINI-R4-CH1", execution=body)
    later = clock()
    preview_apply(sql, settings_request(sql, fields={"solar_proxy_w": 1800, "battery_floor_pct": 45},
        now=later, key="preview-borehole-energy"), now=later, key="apply-borehole-energy")
    with psycopg.connect(sql) as connection:
        assert not controls.owner_start_allowed(connection, "BOREHOLE-1-MINI-R4-CH1", execution=body)
