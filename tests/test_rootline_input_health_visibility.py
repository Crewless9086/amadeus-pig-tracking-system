"""Offline input health families. Real SQL/concurrency proof is a separate PG suite."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, Barrier
import json
from uuid import uuid4

import pytest


@pytest.fixture(autouse=True)
def enable_reviewed_visibility_paths(monkeypatch):
    monkeypatch.setenv("ROOTLINE_INPUT_HEALTH_ENABLED", "true")

from modules.telemetry import rootline_input_health as health
from modules.oom_sakkie import rootline_transition_notifications as notices

NOW = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
ENABLED = {health.OWNERSHIP_FLAG: "true"}
RECIPIENT = {"owner_user_id": "42", "chat_id": "42", "language": "en"}


def source(kind):
    identity, provider = health.INPUTS[kind]
    return {"source_id": identity, "source_type": kind, "provider": provider,
        "active": True, "timezone": "Africa/Johannesburg", "stale_after_minutes": 15 if kind == "power" else 30,
        "nightly_cycle": None, "provider_health": None}


def reading(kind, at=NOW):
    values = ({"rain_rate_mm_h": 0, "wind_speed_kmh": 0} if kind == "weather" else
        {"battery_soc_pct": 41, "solar_power_w": 1200, "load_power_w": 776,
         "grid_power_w": 0, "battery_power_w": -50})
    return {"source_id": health.INPUTS[kind][0], "reading_at": at.isoformat(),
        "flags": {}, "summary_status": "ok", **values}


def forecast(provider="visual_crossing", *, fallback=False):
    claimed = datetime(2026, 11, 19, 21, 30, tzinfo=timezone.utc)
    run = claimed + timedelta(minutes=2)
    ingested = run + timedelta(seconds=1)
    completed = run + timedelta(seconds=3)
    sources = {}
    for name, identity in health.SOURCES.items():
        sources[identity] = {**source("forecast"), "source_id": identity, "provider": name}
    attempt, cycle_id = str(uuid4()), str(uuid4())
    attempts = []
    if fallback:
        attempts.append({"provider": "visual_crossing", "attempt_id": str(uuid4()),
            "generation": 1, "status": "fetch_failed"})
    attempts.append({"provider": provider, "attempt_id": attempt, "generation": 2, "status": "ingested"})
    identity = health.SOURCES[provider]
    cycle = {"version": 1, "attempt_id": cycle_id, "cycle_date": "2026-11-19",
        "operating_date": "2026-11-20", "claimed_at": claimed.isoformat(),
        "completed_at": completed.isoformat(), "status": "ingested", "attempts": attempts,
        "result": {"status": "ingested", "source_id": identity, "forecast_run_at": run.isoformat()},
        "ingest": {"provider": provider, "source_id": identity, "attempt_id": attempt,
            "generation": 2, "forecast_run_at": run.isoformat()}}
    sources[health.INPUTS["forecast"][0]]["nightly_cycle"] = cycle
    snapshot = {"source_id": identity, "forecast_run_at": run.isoformat(), "forecast_date": "2026-11-20",
        "timezone": "Africa/Johannesburg", "ingested_at": ingested.isoformat(),
        "rain_sum_mm": 0, "rain_probability_max_pct": 0, "wind_max_kmh": 12, "gust_max_kmh": 14,
        "temp_min_c": 10, "temp_max_c": 22}
    return sources, snapshot, cycle


@pytest.mark.parametrize("kind", ["weather", "power"])
def test_valid_zero_is_available_and_not_absent(kind):
    value = health.project_sensor(kind, source(kind), reading(kind), now=NOW)
    assert value["state"] == "available" and value["notify"] is False
    assert health.project_sensor(kind, source(kind), None, now=NOW)["state"] == "unavailable"


@pytest.mark.parametrize("kind", ["weather", "power"])
@pytest.mark.parametrize("damage", ["source_missing", "inactive", "wrong_source", "wrong_provider", "wrong_type",
    "timezone", "future", "naive", "malformed", "stale", "conflict", "unhealthy", "partial", "nan", "negative", "freshness"])
def test_adversarial_sensor_inputs_never_imply_health(kind, damage):
    src, row = source(kind), reading(kind)
    if damage == "source_missing": src = None
    elif damage == "inactive": src["active"] = False
    elif damage == "wrong_source": row["source_id"] = "another-source"
    elif damage == "wrong_provider": src["provider"] = "another-provider"
    elif damage == "wrong_type": src["source_type"] = "irrigation"
    elif damage == "timezone": src["timezone"] = "UTC"
    elif damage == "future": row["reading_at"] = (NOW + timedelta(seconds=1)).isoformat()
    elif damage == "naive": row["reading_at"] = NOW.replace(tzinfo=None).isoformat()
    elif damage == "malformed": row["reading_at"] = "not a timestamp"
    elif damage == "stale": row["reading_at"] = (NOW - timedelta(hours=5)).isoformat()
    elif damage == "conflict": row["flags"]["telemetry_conflict"] = True
    elif damage == "unhealthy": row["summary_status"] = "unavailable"
    elif damage == "freshness": src["stale_after_minutes"] = 0
    else:
        key = "rain_rate_mm_h" if kind == "weather" else "battery_soc_pct"
        row[key] = {"partial": None, "nan": "NaN", "negative": -1}[damage]
    projected = health.project_sensor(kind, src, row, now=NOW)
    assert projected["state"] == "unavailable"
    assert projected["notify"] is True


def test_stale_power_values_do_not_become_present_tense_adverse_state():
    row = {**reading("power", NOW-timedelta(hours=5)), "battery_soc_pct": 5, "grid_power_w": 6000}
    result = health.project_sensor("power", source("power"), row, now=NOW)
    assert result["reason"] == "reading_stale"
    assert "battery_soc_pct" not in result and "grid_power_w" not in result


@pytest.mark.parametrize("provider,fallback", [("visual_crossing", False), ("weatherapi", True), ("open_meteo", True), ("weatherapi", False)])
def test_verified_daily_forecast_is_available_even_after_primary_failure(provider, fallback):
    sources, snapshot, cycle = forecast(provider, fallback=fallback)
    result = health.project_forecast(sources, snapshot, now=NOW)
    assert result["state"] == ("available_fallback" if fallback else "available")
    assert result["accepted_source_id"] == health.SOURCES[provider]
    assert result["notify"] is False


@pytest.mark.parametrize("damage", ["old_date", "wrong_cycle_date", "future_completed", "lost_result", "wrong_source",
    "wrong_attempt", "wrong_generation", "wrong_run", "missing_snapshot", "old_snapshot",
    "future_ingestion", "wrong_timezone", "malformed_date", "negative_rain", "nan", "provider_inactive"])
def test_forecast_recovery_needs_exact_current_cycle_ingestion(damage):
    sources, snapshot, cycle = forecast()
    if damage == "old_date": cycle["operating_date"] = "2026-11-19"
    elif damage == "wrong_cycle_date": cycle["cycle_date"] = "2026-11-18"
    elif damage == "future_completed": cycle["completed_at"] = (NOW+timedelta(hours=1)).isoformat()
    elif damage == "lost_result": cycle.pop("result")
    elif damage == "wrong_source": cycle["result"]["source_id"] = health.SOURCES["weatherapi"]
    elif damage == "wrong_attempt": cycle["ingest"]["attempt_id"] = str(uuid4())
    elif damage == "wrong_generation": cycle["ingest"]["generation"] = 3
    elif damage == "wrong_run": cycle["ingest"]["forecast_run_at"] = NOW.isoformat()
    elif damage == "missing_snapshot": snapshot = None
    elif damage == "old_snapshot": snapshot["forecast_date"] = "2026-11-19"
    elif damage == "future_ingestion": snapshot["ingested_at"] = (NOW+timedelta(seconds=1)).isoformat()
    elif damage == "wrong_timezone": snapshot["timezone"] = "UTC"
    elif damage == "malformed_date": snapshot["forecast_run_at"] = "unknown"
    elif damage == "negative_rain": snapshot["rain_sum_mm"] = -1
    elif damage == "nan": snapshot["wind_max_kmh"] = "NaN"
    elif damage == "provider_inactive": sources[snapshot["source_id"]]["active"] = False
    projected = health.project_forecast(sources, snapshot, now=NOW)
    assert projected["state"] == "acquisition_unconfirmed"
    assert projected["notify"] is True


def test_failed_nightly_cycle_is_not_claimed_all_providers_down():
    sources, snapshot, cycle = forecast()
    cycle.update(status="failed", result={"status": "failed", "source_id": None, "forecast_run_at": None})
    value = health.project_forecast(sources, snapshot, now=NOW)
    assert value["state"] == "failed"
    message = notices.input_health_text({"contract": health.CONTRACT, "inputs": {"forecast": value}})
    assert "acquisition" in message and "failed" in message and "providers" not in message


def test_pending_lease_then_unconfirmed_and_next_night_are_distinct():
    sources, snapshot, cycle = forecast()
    cycle.update(status="pending"); cycle.pop("completed_at"); cycle.pop("result")
    early = datetime.fromisoformat(cycle["claimed_at"]) + timedelta(minutes=4)
    assert health.project_forecast(sources, None, now=early)["state"] == "pending"
    assert health.project_forecast(sources, None, now=early+timedelta(minutes=16))["state"] == "acquisition_unconfirmed"
    future = health.project_forecast(sources, None, now=NOW, operating_date="2026-11-21")
    assert future["state"] == "not_yet_due" and future["notify"] is False
    # A late, separately admitted fallback still owns its existing 900s lease.
    attempt = cycle["attempts"][-1]; attempt["status"] = "pending"
    start = early+timedelta(minutes=10)
    sources[health.SOURCES["visual_crossing"]]["provider_health"] = {
        "status": "pending", "claimed_at": start.isoformat(),
        "lease_until": (start+timedelta(seconds=900)).isoformat(),
        "attempt_id": attempt["attempt_id"], "generation": attempt["generation"],
        "nightly_cycle": {key: cycle[key] for key in ("attempt_id", "cycle_date", "operating_date")}}
    assert health.project_forecast(sources, None, now=start+timedelta(minutes=5))["state"] == "pending"


def episode(kind="weather", restored=False):
    outage = health.project_sensor(kind, source(kind), None, now=NOW-timedelta(hours=1))
    result = {"contract": health.CONTRACT, "kind": kind, "source_id": health.INPUTS[kind][0],
        "incident_id": "ROOTLINE-INPUT-" + "A"*32, "status": "Resolved" if restored else "Open",
        "outage_started_at": (NOW-timedelta(hours=1)).isoformat(), "outage": outage,
        "restored_at": NOW.isoformat() if restored else None, "operating_date": None}
    if restored: result["recovery"] = health.project_sensor(kind, source(kind), reading(kind), now=NOW)
    return result


class Memory:
    def __init__(self, current=None):
        self.current = current or episode()
        self.receipts = {}; self.calls = []; self.persist = True; self.lock = Lock()
    def store(self, action, payload):
        assert action == "record_notification_delivery"
        if not self.persist: return {"success": False}
        with self.lock:
            prior = self.receipts.get(payload["notification_identity"], {})
            if not prior.get("delivery_confirmed"):
                self.receipts[payload["notification_identity"]] = {**deepcopy(payload), "event_id": "receipt-"+str(len(self.receipts)+1)}
        return {"success": True}
    def receipt(self, identity):
        with self.lock: return deepcopy(self.receipts.get(identity, {}))
    def state(self, kind, **_):
        return {"input": self.current.get("recovery") or self.current["outage"], "episode": deepcopy(self.current)}
    def notify(self, state, payload, **kw):
        self.calls.append((state, deepcopy(payload), kw))
        return {"provider_delivery_confirmed": True, "provider_message_id": "700", "telegram_sends": 1}
    def run(self, *, notify=None, recipient=None, state_loader=None):
        return notices.recover_input_notifications(notify=notify or self.notify, recipient=recipient or RECIPIENT,
            now=NOW, environ=ENABLED, clock=lambda: NOW,
            reconcile=lambda **_: {"contract": health.CONTRACT, "status": "observed", "episodes": [deepcopy(self.current)]},
            state_loader=state_loader or self.state, receipt_loader=self.receipt, store=self.store)


def test_outage_once_recovery_once_restart_and_long_outage_identity():
    memory = Memory()
    assert memory.run()["notification_count"] == 1
    assert memory.run()["telegram_sends"] == 0
    memory.current = episode(restored=True)
    assert memory.run()["notification_count"] == 1
    assert memory.run()["telegram_sends"] == 0
    assert [row[0] for row in memory.calls] == ["InputUnavailable", "InputRestored"]


def test_historical_recovery_without_confirmed_outage_is_silent():
    memory = Memory(episode(restored=True))
    assert memory.run()["telegram_sends"] == 0
    assert memory.calls == []


def test_recovery_is_exact_recipient_bound():
    memory = Memory(); memory.run(); memory.current = episode(restored=True)
    assert memory.run(recipient={**RECIPIENT, "owner_user_id": "43", "chat_id": "43"})["telegram_sends"] == 0
    assert memory.run()["notification_count"] == 1


def test_pending_ambiguous_delivery_is_never_resent():
    memory = Memory()
    assert memory.run(notify=lambda *a, **k: {"success": False, "status": "ambiguous"})["success"] is False
    assert memory.run()["telegram_sends"] == 0
    assert not memory.calls


def test_retry_retains_identity_content_and_recorded_no_send_proof():
    memory = Memory()
    memory.run(notify=lambda *a, **k: {"delivery_definitely_not_sent": True})
    first = deepcopy(next(iter(memory.receipts.values())))
    assert memory.run()["notification_count"] == 1
    assert memory.calls[0][1] == first["input_notice"]
    assert memory.calls[0][2]["retry_proof_identity"] == first["event_id"]


@pytest.mark.parametrize("damage", ["recipient", "source", "outage", "language", "incident"])
def test_changed_retry_evidence_fails_closed(damage):
    memory = Memory(); memory.run(notify=lambda *a, **k: {"delivery_definitely_not_sent": True})
    saved = next(iter(memory.receipts.values()))
    if damage == "recipient": saved["input_notice"]["recipient_key"] = "other"
    elif damage == "source": saved["input_notice"]["source_id"] = "other"
    elif damage == "outage": saved["input_notice"]["outage"]["observed_at"] = NOW.isoformat()
    elif damage == "language": saved["input_notice"]["recipient_language"] = "af"
    else: saved["execution_id"] = "other"
    with pytest.raises(ValueError):
        memory.run()
    assert memory.calls == []


def test_new_outage_supersedes_an_unsent_recovery():
    memory = Memory(); memory.run(); memory.current = episode(restored=True)
    newer = episode(); newer["incident_id"] = "ROOTLINE-INPUT-"+"B"*32
    assert memory.run(state_loader=lambda *a, **k: {"episode": newer, "input": newer["outage"]})["telegram_sends"] == 0
    assert len(memory.calls) == 1


def test_current_missing_read_cannot_replay_prior_recovery():
    memory = Memory(); memory.run(); memory.current = episode(restored=True)
    assert memory.run(state_loader=lambda *a, **k: {"episode": memory.current, "input": episode()["outage"]})["telegram_sends"] == 0


def test_deadline_deferred_is_not_receipted_as_ambiguous():
    memory = Memory()
    result = memory.run(notify=lambda *a, **k: {"status": "family_message_cycle_deadline_deferred"})
    assert result["status"] == "rootline_input_notifications_deferred"
    assert memory.receipts == {}


def test_disabled_ownership_performs_no_read_write_or_send():
    def forbidden(*a, **kw): pytest.fail("disabled means no producer or consumer")
    assert health.reconcile_input_health(environ={}, connect=forbidden)["status"] == "disabled"
    assert notices.recover_input_notifications(notify=forbidden, recipient={}, environ={}, reconcile=forbidden)["telegram_sends"] == 0


@pytest.mark.parametrize("kind", ["weather", "power"])
def test_ownership_suppresses_only_matching_legacy_health_type(kind, monkeypatch):
    alert_type = health.LEGACY_TYPES[kind]
    evaluation = {"sendable_alerts": [{"alert_type": alert_type}, {"alert_type": "POWER_BATTERY_LOW"},
        {"alert_type": "HEAVY_RAIN"}], "held_alerts": [{"alert_type": alert_type}], "suppressed_alerts": []}
    monkeypatch.delenv(health.OWNERSHIP_FLAG, raising=False)
    assert health.apply_legacy_ownership(evaluation, kind) == evaluation
    monkeypatch.setenv(health.OWNERSHIP_FLAG, "true")
    value = health.apply_legacy_ownership(evaluation, kind)
    assert value["sendable_alerts"] == evaluation["sendable_alerts"][1:]
    assert value["held_alerts"] == evaluation["held_alerts"]
    assert value["suppressed_alerts"][0]["alert_type"] == alert_type


@pytest.mark.parametrize("af", [False, True])
def test_direct_answer_marks_stale_power_and_hides_undated_numbers(af):
    from modules.oom_sakkie.owner_response_composer import compose_rootline
    lang = "af" if af else "en"
    result = {"success": True, "current_power": {"status": "stale", "observed_at": NOW.isoformat(),
        "battery_soc_pct": 41, "solar_power_w": 1200, "load_power_w": 776, "grid_power_w": 0}}
    text = compose_rootline(result, language=lang)
    assert ("Laas bekend op" if af else "Last known at") in text and "41%" in text
    assert ("nie beskikbaar" if af else "unavailable") in text
    result["current_power"].pop("observed_at")
    assert "41%" not in compose_rootline(result, language=lang)
    result["current_power"]["observed_at"] = "2999-01-01T00:00:00+00:00"
    assert "41%" not in compose_rootline(result, language=lang)


def test_forecast_fallback_and_weather_loss_render_separately():
    from modules.oom_sakkie.rootline_daily_presentation import compose_daily_rootline_plan
    sources, snapshot, _ = forecast("weatherapi", fallback=True)
    value = {"contract": health.CONTRACT, "inputs": {
        "weather": health.project_sensor("weather", source("weather"), None, now=NOW),
        "forecast": health.project_forecast(sources, snapshot, now=NOW)}}
    text = compose_daily_rootline_plan({"success": True, "input_health": value})
    assert "local weather readings are unavailable" in text
    assert "available from the backup source" in text and "acquisition" not in text


def test_afrikaans_input_notice_survives_actual_family_localization():
    from modules.oom_sakkie.family_message_lifecycle import localize_recipient_result
    text = notices.compose_input_notice("InputUnavailable", episode(), language="af")
    result = localize_recipient_result({"output_language": "af"},
        {"status": "inputunavailable", "answer": text,
         "recipient_render_contract": "specialist_structured_recipient_v1", "recipient_language": "af"}, "ROOTLINE")
    assert result["answer"] == text and not result.get("recipient_language_render_unrecognized")


class FamilyRail:
    def __init__(self):
        self.rows = {}; self.sent = []; self.lock = Lock(); self.barrier = None; self.fail = False
    def store(self, action, identity, payload):
        if action == "load":
            with self.lock: rows = [deepcopy(row) for row in self.rows.values() if row.get("card_mission_id") == identity]
            if self.barrier: self.barrier.wait(timeout=5)
            return rows
        with self.lock:
            created = identity not in self.rows
            if created: self.rows[identity] = deepcopy(payload)
        return {"success": True, "created": created}
    def send(self, chat, text):
        with self.lock: self.sent.append(text)
        if self.fail: return {"success": False, "delivery_definitely_not_sent": True}
        return {"success": True, "telegram_message_id": "700"}
    def notify(self, state, payload, retry_proof_identity=""):
        from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
        from modules.oom_sakkie.family_presentation import envelope
        from modules.oom_sakkie.delivery_retry_authority import issue_delivery_retry_authority
        identity = payload["notification_identity"]+":"+state.upper()
        text = notices.compose_input_notice(state, payload)
        retry = (issue_delivery_retry_authority(mission_id=identity, card_mission_id=identity,
            text=envelope(text), proof_identity=retry_proof_identity) if retry_proof_identity else None)
        result = deliver_family_result({"telegram_user_id": "42", "telegram_chat_id": "42",
            "provider_message_id": "scheduled:minute", "provider_timestamp": NOW.isoformat()},
            {"success": True, "status": state.lower(), "answer": text}, specialist="ROOTLINE",
            mission_id=identity, card_mission_id=identity, event_store=self.store, sender=self.send,
            editor=lambda *a: pytest.fail("must not edit unrelated cards"), delivery_retry_authority=retry)
        return {**result, "provider_delivery_confirmed": bool(result.get("telegram_message_id")) and
            (result.get("success") is True or result.get("provider_delivery_confirmed") is True),
            "provider_message_id": str(result.get("telegram_message_id") or "")}


def test_two_workers_use_real_family_claim_one_send():
    memory = Memory(); family = FamilyRail(); family.barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: memory.run(notify=family.notify), range(2)))
    assert sum(r["telegram_sends"] for r in results) == 1 and len(family.sent) == 1
    family.barrier = None
    assert memory.run(notify=family.notify)["telegram_sends"] == 0


def test_real_family_retry_and_execution_receipt_failure_replay():
    memory = Memory(); family = FamilyRail(); family.fail = True
    assert memory.run(notify=family.notify)["notification_count"] == 0
    family.fail = False; memory.persist = False
    assert memory.run(notify=family.notify)["success"] is False
    assert len(family.sent) == 2 and family.sent[0] == family.sent[1]
    memory.persist = True
    assert memory.run(notify=family.notify)["notification_count"] == 1
    assert len(family.sent) == 2


@pytest.mark.parametrize("report_due", [False, True])
def test_actual_minute_gateway_runs_health_after_off_before_failed_plan(report_due, monkeypatch):
    from modules.oom_sakkie import automatic_reassessment_scheduler as scheduler
    from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
    from modules.telemetry import rootline_water_energy_plan as planning
    calls, delivered = [], []
    monkeypatch.setattr(scheduler, "run_due_reassessment", lambda **kw: (kw["invoke"] if report_due else kw["invoke_not_due"])())
    monkeypatch.setattr(planning, "ensure_due_daily_program", lambda **kw: ({"success": True}, 200))
    def safety(**kw):
        calls.append("off_duties")
        return {"success": True, "status": "no_active_irrigation", "hardware_commands": 0, "telegram_sends": 0}
    def reporter(**kw):
        calls.append("input_notice")
        assert kw["recipient"]["owner_user_id"] == "42"
        value = episode()
        return {**kw["notify"]("InputUnavailable", {**value, "notification_identity": value["incident_id"]+":unavailable"}),
            "status": "input_observed"}
    def failed_plan():
        calls.append("plan"); raise RuntimeError("plan unavailable")
    def delivery(parsed, result, **kw):
        delivered.append(result)
        return {"success": True, "telegram_message_id": "700", "telegram_sends": 1}
    env = {"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "true", "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "x"*40,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42", **ENABLED}
    payload = {"scheduler_identity": scheduler.SCHEDULER_IDENTITY, "specialist": "ROOTLINE",
        "owner_user_id": "42", "chat_id": "42", "due_at": NOW.isoformat(), "evidence_cutoff": NOW.isoformat(),
        "trigger_id": "MINUTE1", "trigger": "declared_time", "trigger_timestamp": NOW.isoformat()}
    result, status = handle_rootline_reassessment_trigger(payload, {"X-Oom-Sakkie-Telegram-Token": "x"*40}, env,
        schedule_store=lambda *a: {}, state_store=lambda *a: {}, scheduler_now=NOW, specialist_loader=failed_plan,
        active_supervision_cycle=safety, managed_device_cycle=safety, input_notification_cycle=reporter,
        family_delivery=delivery)
    assert calls[:2] == ["off_duties", "off_duties"] and calls.count("input_notice") == 1
    assert result["telegram_sends"] == 1 and len(delivered) == 1
    if report_due: assert calls.index("input_notice") < calls.index("plan")
    else: assert "plan" not in calls
    assert delivered[0]["recipient_render_contract"] == "specialist_structured_recipient_v1"
    assert ("weather" in delivered[0]["answer"].lower() or "weer" in delivered[0]["answer"].lower())


def test_unavailable_plan_retains_separately_read_health(monkeypatch):
    from modules.telemetry import rootline_specialist_result as specialist, rootline_water_energy_plan as planning
    from modules.telemetry import rootline_provider_availability as provider
    monkeypatch.setattr(specialist, "read_current_water_energy_evidence", lambda **kw: ({}, "2026-11-20", NOW))
    monkeypatch.setattr(planning, "ensure_saved_daily_program", lambda *a, **kw: ({"success": False, "status": "nightly_forecast_missing"}, 503))
    monkeypatch.setattr(provider, "read_provider_availability", lambda **kw: {"contract": provider.CONTRACT, "status": "unobserved"})
    expected = {"contract": health.CONTRACT, "inputs": {"weather": health.project_sensor("weather", source("weather"), None, now=NOW)}}
    monkeypatch.setattr(health, "read_input_health", lambda **kw: expected)
    result = specialist.refresh_current_rootline_specialist_result(now=NOW)
    assert not result["success"] and result["input_health"] == expected
    from modules.oom_sakkie.owner_response_composer import compose_rootline
    assert "Current local weather readings are unavailable." in compose_rootline(result)



class EpisodeStore:
    """Transaction-shaped in-memory ledger; actual SQL qualified separately."""
    def __init__(self):
        self.rows = {}; self.stamp = NOW; self.lock = True; self.reject = False
        self.inputs = {k: health.project_sensor(k, source(k), None, now=NOW) for k in ("weather", "power")}
        self.inputs["forecast"] = {"kind": "forecast", "state": "pending", "notify": False}
        self.result = None; self.commits = 0
    def __call__(self, **kwargs):
        assert kwargs == {"database_url": None, "read_only": False, "read_committed": True}
        return self
    def __enter__(self):
        self.before = deepcopy(self.rows); return self
    def __exit__(self, *error):
        if error[0]: self.rows = self.before
        else: self.commits += 1
    def cursor(self):
        store = self
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def execute(self, sql, params=None):
                if "pg_try_advisory" in sql: store.result = (store.lock,)
                elif "clock_timestamp" in sql: store.result = (store.stamp,)
                elif "select alert_id" in sql: store.result = store.rows.get(params[0])
                elif "insert into" in sql:
                    identity, sid, kind, alert_type, message, at, body = params
                    row = (identity, sid, "Open", at, None, json.loads(body))
                    store.rows[kind] = row; store.result = None if store.reject else row
                elif "status='Resolved'" in sql:
                    at, body, identity = params
                    for kind, row in store.rows.items():
                        if row[0] == identity:
                            row = (identity, row[1], "Resolved", row[3], at, json.loads(body))
                            store.rows[kind] = row; store.result = None if store.reject else row; break
                else: raise AssertionError(sql)
            def fetchone(self): return store.result
        return Cursor()
    def project(self, cursor, now, **kw): return deepcopy(self.inputs), {health.INPUTS[k][0]: source(k) for k in ("weather", "power")}


def test_producer_persists_replays_and_recovers_exact_episode(monkeypatch):
    store = EpisodeStore()
    monkeypatch.setattr(health, "_read_projection", store.project)
    first = health.reconcile_input_health(connect=store, environ=ENABLED)
    assert len(first["episodes"]) == 2
    original = store.rows["power"][0]
    store.stamp += timedelta(days=30)
    again = health.reconcile_input_health(connect=store, environ=ENABLED)
    assert store.rows["power"][0] == original
    assert len(again["episodes"]) == 2
    store.inputs["power"] = health.project_sensor("power", source("power"), reading("power", store.stamp), now=store.stamp)
    recovered = health.reconcile_input_health(connect=store, environ=ENABLED)
    assert store.rows["power"][0] == original and store.rows["power"][2] == "Resolved"
    assert next(e for e in recovered["episodes"] if e["kind"] == "power")["recovery"]["observed_at"] == store.stamp.isoformat()
    store.stamp += timedelta(hours=1)
    store.inputs["power"] = health.project_sensor("power", source("power"), None, now=store.stamp)
    health.reconcile_input_health(connect=store, environ=ENABLED)
    assert store.rows["power"][0] != original


@pytest.mark.parametrize("failure", ["lock", "insert", "recovery", "budget"])
def test_producer_failure_rolls_back_without_fake_episode_or_recovery(failure, monkeypatch):
    store = EpisodeStore()
    monkeypatch.setattr(health, "_read_projection", store.project)
    if failure == "recovery":
        health.reconcile_input_health(connect=store, environ=ENABLED)
        store.stamp += timedelta(minutes=1)
        store.inputs["power"] = health.project_sensor("power", source("power"), reading("power", store.stamp), now=store.stamp)
    before = deepcopy(store.rows)
    if failure == "lock": store.lock = False
    if failure in {"insert", "recovery"}: store.reject = True
    if failure == "budget":
        from modules.telemetry import rootline_cycle_budget
        monkeypatch.setattr(rootline_cycle_budget, "remaining_seconds", lambda **kw: (_ for _ in ()).throw(ValueError("deadline")))
    with pytest.raises(ValueError): health.reconcile_input_health(connect=store, environ=ENABLED)
    assert store.rows == before


def test_producer_preincident_sample_cannot_restore(monkeypatch):
    store = EpisodeStore()
    monkeypatch.setattr(health, "_read_projection", store.project)
    health.reconcile_input_health(connect=store, environ=ENABLED)
    store.inputs["power"] = health.project_sensor("power", source("power"), reading("power", NOW-timedelta(minutes=1)), now=NOW)
    health.reconcile_input_health(connect=store, environ=ENABLED)
    assert store.rows["power"][2] == "Open"


@pytest.mark.parametrize("bad", [[], "invalid", 42])
def test_malformed_forecast_result_does_not_hide_sensor_health(bad):
    sources, snapshot, cycle = forecast()
    cycle["result"] = bad
    rows=[]
    for s in [source("weather"), source("power"), *sources.values()]:
        rows.append(tuple(s.get(k) for k in ("source_id", "source_type", "provider", "active", "timezone", "stale_after_minutes", "nightly_cycle", "provider_health")) + (reading("weather") if s["source_type"] == "weather" else None, reading("power") if s["source_type"] == "power" else None))
    class Cursor:
        def execute(self, *a): pass
        def fetchall(self): return rows
    projected, _ = health._read_projection(Cursor(), NOW)
    assert projected["weather"]["state"] == projected["power"]["state"] == "available"
    assert projected["forecast"]["state"] == "acquisition_unconfirmed"


def test_weather_caution_is_available_measurement_not_source_outage():
    value = reading("weather")
    value["summary_status"] = "caution"
    assert health.project_sensor("weather", source("weather"), value, now=NOW)["state"] == "available"


@pytest.mark.parametrize("bad", [[], {}, ["invalid"], None, 42, "unregistered"])
def test_malformed_nested_forecast_source_identity_preserves_sensors(bad):
    sources, snapshot, cycle = forecast()
    cycle["result"]["source_id"] = bad
    rows = []
    for s in [source("weather"), source("power"), *sources.values()]:
        rows.append(tuple(s.get(k) for k in ("source_id", "source_type", "provider", "active", "timezone", "stale_after_minutes", "nightly_cycle", "provider_health")) + (reading("weather") if s["source_type"] == "weather" else None, reading("power") if s["source_type"] == "power" else None))
    class Cursor:
        def execute(self, *a): pass
        def fetchall(self): return rows
    projected, _ = health._read_projection(Cursor(), NOW)
    assert projected["weather"]["state"] == projected["power"]["state"] == "available"
    assert projected["forecast"]["state"] == "acquisition_unconfirmed"
