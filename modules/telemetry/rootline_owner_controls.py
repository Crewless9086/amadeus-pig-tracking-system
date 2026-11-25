"""Confirmed owner controls on the existing ROOTLINE operational intake rail.

Preview is inert. Apply records a typed, actor-bound decision under the same
locks used by command edges. It never calls a device transport.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
import os
import re
from zoneinfo import ZoneInfo

ZA = ZoneInfo("Africa/Johannesburg")
VERSION = "rootline_owner_control.v1"
SOURCE = "oom_sakkie_rootline_operational_intake"
DEVICES = {"camp_a": "A12345", "camp_b": "B12345", "camp_c": "C12345",
    "camp_e": "E12345", "mixer": "FERTILIZER-MIXER-CH2",
    "injection": "FERTILIZER-INJECTION-CH1", "borehole": "BOREHOLE-1-MINI-R4-CH1",
    "eskom": "ESKOM-GRID"}
NAMES = {"camp_a": "Camp A", "camp_b": "Camp B", "camp_c": "Camp C", "camp_e": "Camp E",
    "mixer": "Mixer", "injection": "Injection", "borehole": "Borehole", "eskom": "Eskom"}
LOCKS = (1874320911, 1874320912, 1874320914)


class ControlError(ValueError):
    def __init__(self, status, http=409):
        super().__init__(status)
        self.status, self.http = status, http


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _time(value):
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("aware_timestamp_required")
    return result.astimezone(timezone.utc)


def _now(connection, supplied=None):
    return _time(supplied or connection.execute("select clock_timestamp()").fetchone()[0])


def _connect(database_url, *, read_only):
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    return connect_bounded_rootline_postgres(database_url=database_url, read_only=read_only,
        read_committed=True)


def _lock(connection):
    for key in LOCKS:
        connection.execute("select pg_advisory_xact_lock(%s)", (key,))


def _read_records(connection):
    rows = connection.execute("""select review_json->'rootline_operational_intake'
        from public.sam_live_stock_conversation_review_events
        where event_source=%s
          and review_json->'rootline_operational_intake'->'context'->>'contract_version'=%s
        order by created_at,review_event_id""", (SOURCE, VERSION)).fetchall()
    return [row[0] for row in rows if isinstance(row[0], dict)]


def _valid_record(record, state):
    context = record.get("context") or {}
    return (record.get("state") == state and context.get("contract_version") == VERSION
        and context.get("event_type") == "owner_control" and bool(context.get("actor"))
        and context.get("source") == "authenticated_owner_controls"
        and record.get("mission_id") == "ROOTLINE-OWNER-CONTROLS")


def _validate_records(records):
    """Malformed typed controls cannot silently become automatic permission."""
    from modules.telemetry.rootline_energy_policy import validate_energy_control_fields
    for record in records:
        state = record.get("state")
        if state not in {"preview", "confirmed", "consumed"} or not _valid_record(record, state):
            raise ControlError("owner_control_record_invalid", 503)
        context = record["context"]
        if state == "preview":
            continue
        if state == "consumed":
            if (not context.get("request_id") or not context.get("execution_id")
                    or context.get("device_id") not in DEVICES):
                raise ControlError("owner_control_consumption_invalid", 503)
            _time(context["at"])
            continue
        change = context.get("change") or {}
        kind, device = change.get("kind"), change.get("device_id")
        if (not context.get("request_id") or kind not in {"settings", "plan", "run", "stop"}
                or kind != "plan" and device not in DEVICES or not isinstance(change.get("changes"), dict)):
            raise ControlError("owner_control_record_invalid", 503)
        _time(context["effective_at"])
        if context.get("expires_at"):
            _time(context["expires_at"])
        if kind == "settings":
            settings = change["changes"]
            if (settings.get("mode") not in {"automatic", "paused", "manual_today"}
                    or settings.get("scope") not in {"ongoing", "today"}
                    or settings.get("scope") == "today" and not context.get("expires_at")
                    or settings.get("mode") == "manual_today" and settings.get("scope") != "today"):
                raise ControlError("owner_control_settings_invalid", 503)
            _validate_owner_fields(device, settings.get("fields"))
        elif kind in {"run", "stop"} and not context.get("expires_at"):
            raise ControlError("owner_control_request_expiry_missing", 503)


def project_owner_controls(records, *, now):
    now = _time(now)
    _validate_records(records)
    active = {key: {"mode": "automatic", "scope": "ongoing", "fields": {},
        "reason": "Standing automatic operation", "revision": _digest([VERSION, key]),
        "effective_at": None, "expires_at": None} for key in DEVICES}
    confirmed = [r for r in records if _valid_record(r, "confirmed") and _time(r["context"]["effective_at"]) <= now]
    history, requests = [], []
    consumed = [deepcopy(r["context"]) for r in records if _valid_record(r, "consumed") and _time(r["context"]["at"]) <= now]
    for record in confirmed:
        context = record["context"]
        change = context.get("change") or {}
        device = change.get("device_id")
        kind = change.get("kind")
        history.append({"id": context.get("request_id"), "at": context.get("effective_at"),
            "device_id": device, "kind": kind, "summary": change.get("reason"),
            "actor": context["actor"], "status": "saved" if kind in {"settings", "plan"} else "request recorded"})
        if kind in {"run", "stop"}:
            requests.append(deepcopy(context))
        if kind not in {"settings", "stop"} or device not in active:
            continue
        expires = context.get("expires_at")
        if expires and _time(expires) <= now:
            continue
        if _time(context["effective_at"]) > now:
            continue
        settings = (change["changes"] if kind == "settings" else
            {"mode": "paused", "scope": "today", "fields": deepcopy(active[device]["fields"])})
        active[device] = {**active[device], **deepcopy(settings), "reason": change["reason"],
            "revision": context["request_id"], "effective_at": context["effective_at"],
            "expires_at": expires}
    # Include expired writes in the CAS identity: an old preview cannot silently
    # overwrite an intervening owner decision even when its one-day scope ended.
    revision = _digest([r["context"].get("request_id") for r in confirmed])
    for key, value in active.items():
        value["revision"] = _digest([revision, key, value])
    return {"revision": revision, "devices": active, "requests": requests, "consumed": consumed,
        "history": list(reversed(history))}


def read_owner_controls(connection, *, now=None):
    return project_owner_controls(_read_records(connection), now=_now(connection, now))


def load_runtime_owner_controls(database_url=None, *, now=None):
    with _connect(database_url or os.environ.get("DATABASE_URL"), read_only=True) as connection:
        return read_owner_controls(connection, now=now)


def apply_controls_to_plan(plan, controls, *, now):
    """Restrict existing eligible work; never manufacture weather/energy clearance."""
    if not controls:
        return plan
    for task in plan.get("candidate_tasks", []):
        device = next((k for k, v in DEVICES.items() if task.get("task_id") == "irrigation_" + v), None)
        if device is None and task.get("task_id") == "borehole":
            device = "borehole"
        if device is None:
            continue
        setting = controls["devices"][device]
        pending = pending_owner_request(controls, device, now, kind="run")
        if device.startswith("camp_") and not task.get("owner_edited") and not task.get("incomplete_parent_job"):
            duration = setting["fields"].get("duration_minutes")
            if duration is not None:
                task.update(planned_duration_minutes=duration, requested_total_duration_minutes=duration,
                    expected_segment_count=1, owner_settings_revision=setting["revision"])
        if task.get("owner_skip") or setting["mode"] != "automatic" and pending is None:
            task.update(zone_decision="Hold", recommendation="Hold",
                live_adjustment_reason="owner_skipped_today" if task.get("owner_skip") else "owner_automatic_start_paused")
    for task in plan.get("irrigation_auxiliary_tasks", []):
        device = next((k for k, v in DEVICES.items() if task.get("auxiliary_device_id") == v), None)
        if device is not None and controls["devices"][device]["mode"] != "automatic" and pending_owner_request(controls, device, now, kind="run") is None:
            task.update(decision="Hold", reason="owner_automatic_start_paused")
    return plan


def owner_start_allowed(connection, canonical_device, *, now=None, execution=None):
    """Called while the device's command-edge lock remains held."""
    key = next((key for key, value in DEVICES.items() if value == canonical_device), None)
    if key is None:
        return False
    observed = _now(connection, now)
    state = read_owner_controls(connection, now=observed)
    body = execution or {}
    bound = owner_request_for_execution(state, key, body.get("execution_id"), observed)
    consumed = any(r.get("execution_id") == body.get("execution_id") for r in state["consumed"])
    if bound and (bound["change"]["kind"] != "run" if key != "eskom" else
            body.get("desired_state") != ("ON" if bound["change"]["kind"] == "run" else "OFF")):
        return False
    if body.get("owner_request_id") and (bound is None or bound["request_id"] != body["owner_request_id"]):
        return False
    permitted = bound is not None if consumed else state["devices"][key]["mode"] == "automatic"
    return (permitted and _owner_plan_gate(connection, key, body, observed, controls=state)
        and _owner_auxiliary_gate(connection, key, body, observed, state)
        and _owner_energy_gate(connection, key, body, observed, state))


def _request_current(context, controls, device, now):
    change = context.get("change") or {}
    if change.get("device_id") != device or change.get("kind") not in {"run", "stop"}:
        return False
    if _time(context["effective_at"]) > now or _time(context["expires_at"]) <= now:
        return False
    setting = controls["devices"][device]
    # Any later mode decision supersedes an older one-off request.
    effective = setting.get("effective_at")
    return not effective or _time(effective) <= _time(context["effective_at"])


def pending_owner_request(control_state, device, now, kind=None):
    observed = _time(now)
    consumed = {r["request_id"] for r in control_state.get("consumed", [])}
    return next((r for r in reversed(control_state.get("requests", []))
        if r["request_id"] not in consumed and _request_current(r, control_state, device, observed)
        and (kind is None or r["change"]["kind"] == kind)), None)


def owner_request_for_execution(control_state, device, execution_id, now):
    if not execution_id:
        return None
    consumed = {r["request_id"] for r in control_state.get("consumed", [])
        if r.get("execution_id") == execution_id and r.get("device_id") == device}
    return next((r for r in control_state.get("requests", []) if r["request_id"] in consumed
        and _request_current(r, control_state, device, _time(now))), None)


def bind_owner_start(connection, canonical_device, body):
    """Consume one request inside the existing command-claim transaction."""
    device = next((k for k, v in DEVICES.items() if v == canonical_device), None)
    if device is None:
        return False
    now = _now(connection)
    controls = read_owner_controls(connection, now=now)
    request = pending_owner_request(controls, device, now,
        kind=None if device == "eskom" else "run")
    if request is None:
        return (not body.get("owner_request_id") and controls["devices"][device]["mode"] == "automatic"
            and _owner_plan_gate(connection, device, body, now, controls=controls)
            and _owner_auxiliary_gate(connection, device, body, now, controls)
            and _owner_energy_gate(connection, device, body, now, controls))
    if body.get("owner_request_id") not in {None, request["request_id"]}:
        return False
    if (not _owner_plan_gate(connection, device, body, now, controls=controls)
            or not _owner_auxiliary_gate(connection, device, body, now, controls)
            or not _owner_energy_gate(connection, device, body, now, controls)):
        return False
    owned = getattr(connection, "connection", connection)
    _write(owned, request["request_id"] + "-CONSUMED", {
        "actor": request["actor"], "request_id": request["request_id"],
        "execution_id": body["execution_id"], "device_id": device, "at": now.isoformat()},
        "consumed", database_url=os.environ.get("DATABASE_URL"))
    return True


def _owner_plan_gate(connection, device, body, now, *, controls=None):
    if not device.startswith("camp_"):
        return True
    cursor = connection.execute("""select g.plan_json from public.rootline_water_energy_plan_identities i
        join public.rootline_water_energy_plan_generations g
          on g.plan_id=i.plan_id and g.generation=i.current_generation
        where i.operating_date=%s""", (now.astimezone(ZA).date().isoformat(),))
    row = cursor.fetchone()
    program = ((row[0] if row else {}).get("daily_program") or {})
    task = next((t for t in program.get("base_tasks", [])
        if t.get("task_id") == "irrigation_" + DEVICES[device]), None)
    duration = (((controls or {}).get("devices", {}).get(device) or {}).get("fields") or {}).get("duration_minutes")
    if not task or not task.get("owner_edited"):
        if type(body.get("segment_number")) is int and body["segment_number"] > 1 and body.get("job_id"):
            prior = connection.execute("""select 1 from public.sam_live_stock_conversation_review_events
                where event_source='rootline_irrigation_execution'
                  and review_json->'rootline_execution'->>'action'='claim_before_on'
                  and review_json->'rootline_execution'->>'job_id'=%s
                  and review_json->'rootline_execution'->>'zone_id'=%s
                  and review_json->'rootline_execution'->>'segment_number'=%s limit 1""",
                (body["job_id"], DEVICES[device], str(body["segment_number"] - 1))).fetchone()
            if prior:
                return True
        return duration is None or body.get("planned_runtime_seconds") == duration * 60
    return bool(task and not task.get("owner_skip")
        and _time(task["planned_start_at"]) <= now < _time(program["end_at"])
        and body.get("planned_runtime_seconds") == task.get("planned_duration_minutes", 0) * 60)


def _owner_auxiliary_gate(connection, device, body, now, controls):
    from modules.telemetry.rootline_owner_auxiliary_policy import effective_auxiliary_settings, mixer_owner_capacity_seconds
    settings = effective_auxiliary_settings(controls, now=now)
    if device == "injection":
        pulse = body.get("pulse_number")
        return type(pulse) is int and 1 <= pulse <= settings["injection"]["max_pulses_per_run"]
    if device != "mixer":
        return True
    # Canonical fixed-budget checks already enforce the unchanged defaults.
    if settings["mixer"] == {"session_minutes": 10, "daily_minutes": 30}:
        return True
    from modules.telemetry.rootline_irrigation_execution_store import _mixer_reservation_rows
    from modules.telemetry.rootline_auxiliary_management import mixing_daily_accounting
    history = [r for r in _mixer_reservation_rows(connection) if r.get("execution_id") != body.get("execution_id")]
    accounting = mixing_daily_accounting(history, now=now)
    duration = body.get("maximum_duration_seconds")
    return (accounting.get("history_valid") is True and type(duration) is int and duration > 0
        and duration <= mixer_owner_capacity_seconds(accounting, controls, now=now))


def energy_policy_digest(device, control_state, now):
    from modules.telemetry.rootline_energy_policy import effective_energy_settings
    # Validated JSON integers and floats have identical policy meaning.
    return _digest({key: float(value) for key, value in effective_energy_settings(control_state, now=now)[device].items()})


def _owner_energy_gate(connection, device, body, now, control_state):
    if device not in {"mixer", "borehole"}:
        return True  # Eskom recomputes its complete decision under its own lock.
    if not any(row.get("device_id") == device and row.get("kind") == "settings"
            for row in control_state.get("history", [])):
        return True
    action = "record_auxiliary_eligibility" if device == "mixer" else "record_borehole_eligibility"
    row = connection.execute("""select review_json->'rootline_execution'
        from public.sam_live_stock_conversation_review_events where event_source='rootline_irrigation_execution'
          and review_json->'rootline_execution'->>'action'=%s
          and review_json->'rootline_execution'->>'execution_id'=%s
        order by created_at desc,review_event_id desc limit 1""", (action, body.get("execution_id"))).fetchone()
    artifact = row[0] if row else {}
    digest = artifact.get("owner_energy_policy_sha256") if device == "mixer" else (artifact.get("energy_context") or {}).get("owner_energy_policy_sha256")
    current = energy_policy_digest(device, control_state, now)
    if digest is not None:
        return digest == current
    # Existing artifacts remain valid only for the unchanged standing policy.
    return current == energy_policy_digest(device, None, now)


def _write(connection, identity, context, state, *, database_url):
    from modules.oom_sakkie.operational_specialist_intake import _operation_event_store
    payload = {"mission_id": "ROOTLINE-OWNER-CONTROLS", "state": state, "context": {
        **context, "contract_version": VERSION, "event_type": "owner_control",
        "source": "authenticated_owner_controls"}}
    result = _operation_event_store("append", identity, payload, connection=connection,
        database_url=database_url)
    if result.get("success") is not True:
        raise ControlError("owner_control_persistence_unavailable", 503)
    return payload


def _failure(exc):
    if isinstance(exc, ControlError):
        return {"success": False, "status": exc.status, "message": exc.status.replace("_", " ")}, exc.http
    return {"success": False, "status": "owner_controls_unavailable",
        "message": "Current controls could not be verified. Refresh before trying again."}, 503


def _request_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", value):
        raise ControlError("idempotency_key_invalid", 400)
    return value


def _actor(value):
    if not isinstance(value, str) or not value.strip():
        raise ControlError("owner_identity_required", 403)
    return value.strip()


def _midnight(now):
    local = now.astimezone(ZA)
    return datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), ZA).astimezone(timezone.utc)


def owner_device_settings(device_id, control_state, plan, now):
    from modules.telemetry.rootline_auxiliary_management import MAX_MIX_SECONDS, MAX_DAILY_MIX_MINUTES, INJECTION_SECONDS
    from modules.telemetry.rootline_energy_policy import managed_energy_decision, ENERGY_CONTROL_FIELDS, effective_energy_settings
    from modules.telemetry.rootline_owner_auxiliary_policy import AUXILIARY_CONTROL_FIELDS, effective_auxiliary_settings
    settings = deepcopy(control_state["devices"][device_id])
    energy = managed_energy_decision({}, now=now)
    fields = []
    def fixed(key, label, value, unit, reason):
        fields.append({"key": key, "label": label, "type": "number", "value": value,
            "unit": unit, "editable": False, "reason": reason})
    if device_id.startswith("camp_"):
        task = next((t for t in (plan.get("daily_program") or {}).get("base_tasks", [])
            if t.get("task_id") == "irrigation_" + DEVICES[device_id]), {})
        from modules.telemetry.rootline_timed_control import MAX_IRRIGATION_SECONDS
        fields.append({"key": "duration_minutes", "label": "Run duration", "type": "number",
            "value": settings["fields"].get("duration_minutes", task.get("planned_duration_minutes")),
            "required": settings["fields"].get("duration_minutes", task.get("planned_duration_minutes")) is not None,
            "unit": "minutes", "min": 1, "max": min(task.get("max_execution_minutes") or MAX_IRRIGATION_SECONDS // 60,
                MAX_IRRIGATION_SECONDS // 60), "editable": True,
            "reason": "Future unstarted work; today's explicit plan edits take precedence."})
    elif device_id == "mixer":
        fixed("maximum_session_minutes", "Hard device timing ceiling", MAX_MIX_SECONDS / 60, "minutes", "Commissioned device timing ceiling")
        fixed("maximum_daily_minutes", "Hard daily ceiling", MAX_DAILY_MIX_MINUTES, "minutes", "Canonical daily mixing budget")
    elif device_id == "injection":
        fixed("pulse_seconds", "Fixed injection pulse target", INJECTION_SECONDS, "seconds", "The commissioned pulse programme uses this fixed target; change the number of future pulses below.")
    elif device_id == "borehole":
        fixed("solar_proxy_w", "Sunshine threshold", energy["borehole_solar_proxy_w"], "W", "Standing backup-supply policy")
    elif device_id == "eskom":
        fixed("on_soc_pct", "Connect grid at battery", energy["eskom_on_soc_pct"], "%", "Commissioned grid policy")
        fixed("off_soc_pct", "Disconnect after solar recovery", energy["eskom_off_soc_pct"], "%", "Commissioned grid policy")
    values = effective_energy_settings(control_state, now=now)
    values.setdefault(device_id, {}).update(effective_auxiliary_settings(control_state, now=now).get(device_id, {}))
    editable = {**ENERGY_CONTROL_FIELDS.get(device_id, {}), **AUXILIARY_CONTROL_FIELDS.get(device_id, {})}
    fields = [field for field in fields if field["key"] not in editable]
    fields.extend({"key": key, "type": "number", "value": values[device_id][key], "editable": True,
        **{name: spec[name] for name in ("label", "unit", "min", "max")}} for key, spec in editable.items())
    return {**settings, "fields": fields}


def owner_device_actions(device_id, control_state, plan, now):
    return {kind: {"supported": True, "reason": (
        "Queue one eligible execution. Weather, supply, daily budgets and device protection still apply."
        if kind == "run" else "Request supervised stopping of the active duty and pause automatic starts for today."
        if device_id != "eskom" else "Queue grid OFF when battery and solar-recovery safeguards allow it.")}
        for kind in ("run", "stop")}


def _plan_revision(plan):
    return _digest([plan.get("plan_id"), plan.get("generation"), plan.get("evidence_sha256")])


def get_owner_plan(connection, now):
    from modules.telemetry.rootline_water_energy_plan import get_current_water_energy_plan
    from modules.telemetry.rootline_timed_control import MAX_IRRIGATION_SECONDS
    plan, status = get_current_water_energy_plan(now.astimezone(ZA).date().isoformat(), connection=connection)
    if not plan.get("daily_program"):
        return {"status": "unavailable", "revision": None, "operating_date": now.astimezone(ZA).date().isoformat(),
            "reason": "No saved programme is available for today.", "rows": []}
    started = _started_tasks(connection, plan)
    rows = []
    for task in plan["daily_program"].get("base_tasks", []):
        key = next((k for k, v in DEVICES.items() if task.get("task_id") == "irrigation_" + v), None)
        if key is None:
            continue
        rows.append({"id": task["task_id"], "device_id": key, "name": NAMES[key],
            "order": len(rows) + 1, "duration_minutes": task.get("planned_duration_minutes"),
            "maximum_duration_minutes": min(task.get("max_execution_minutes") or MAX_IRRIGATION_SECONDS // 60, MAX_IRRIGATION_SECONDS // 60),
            "priority": task.get("owner_priority", "normal"), "reason": task.get("reason") or "Saved daily programme",
            "skip": task.get("owner_skip") is True, "start_at": task.get("planned_start_at"),
            "end_at": task.get("planned_end_at"), "editable": task["task_id"] not in started})
    return {"status": plan.get("status"), "revision": _plan_revision(plan),
        "operating_date": plan["operating_date"], "reason": "Changes apply to unstarted work today only.", "rows": rows}


def _started_tasks(connection, plan):
    rows = connection.execute("""select distinct review_json->'rootline_execution'->>'zone_id'
        from public.sam_live_stock_conversation_review_events where event_source='rootline_irrigation_execution'
        and review_json->'rootline_execution'->>'action'='claim_before_on'
        and (review_json->'rootline_execution'->>'operating_date'=%s
             or (created_at at time zone 'Africa/Johannesburg')::date=%s::date)""",
        (plan["operating_date"], plan["operating_date"])).fetchall()
    return {"irrigation_" + row[0] for row in rows if row[0]}


def get_owner_controls(*, panel=None, database_url=None, now=None):
    database_url = database_url or os.environ.get("DATABASE_URL")
    try:
        with _connect(database_url, read_only=True) as connection:
            observed = _now(connection, now)
            controls = read_owner_controls(connection, now=observed)
            result = {"success": True, "observed_at": observed.isoformat(), "constraints": [
                "Current commands do not prove physical water delivery.",
                "Pausing prevents new automatic starts; accepted shutdown duties remain supervised."]}
            if panel in {None, "plan"}:
                result["plan"] = get_owner_plan(connection, observed)
        from modules.telemetry.rootline_owner_control_projection import build_owner_control_projection
        for selected in (("forecast", "devices", "history") if panel is None else (panel,)):
            if selected != "plan":
                result.update(build_owner_control_projection(selected, control_state=controls,
                    now=observed, database_url=database_url))
        return result, 200
    except Exception as exc:
        return _failure(exc)


def _normalize_change(payload, controls, connection, now):
    if not isinstance(payload, dict) or set(payload) - {"kind", "device_id", "expected_revision", "reason", "idempotency_key", "changes"}:
        raise ControlError("owner_control_payload_invalid", 400)
    kind, device = payload.get("kind"), payload.get("device_id")
    reason = payload.get("reason")
    if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
        raise ControlError("reason_required", 400)
    changes = payload.get("changes")
    if not isinstance(changes, dict):
        raise ControlError("changes_required", 400)
    if kind == "settings":
        if device not in DEVICES:
            raise ControlError("device_unknown", 400)
        if payload.get("expected_revision") != controls["devices"][device]["revision"]:
            raise ControlError("settings_revision_changed")
        if set(changes) != {"mode", "scope", "fields"} or not isinstance(changes["fields"], dict):
            raise ControlError("unsupported_settings_field", 400)
        try:
            normalized = _validate_owner_fields(device, changes["fields"], require_full=True)
            if device.startswith("camp_") and not normalized:
                normalized = deepcopy(controls["devices"][device]["fields"])
            changes = {**changes, "fields": normalized}
        except ValueError as exc:
            raise ControlError(str(exc), 400) from exc
        if changes["mode"] not in {"automatic", "paused", "manual_today"} or changes["scope"] not in {"ongoing", "today"}:
            raise ControlError("mode_or_scope_invalid", 400)
        if changes["mode"] == "manual_today" and changes["scope"] != "today":
            raise ControlError("manual_mode_requires_today", 400)
    elif kind == "plan":
        current = get_owner_plan(connection, now)
        if not current.get("revision") or payload.get("expected_revision") != current["revision"]:
            raise ControlError("plan_revision_changed")
        changes = _validate_plan_rows(changes, current)
    elif kind in {"run", "stop"}:
        if device not in DEVICES:
            raise ControlError("device_unknown", 400)
        if payload.get("expected_revision") != controls["devices"][device]["revision"]:
            raise ControlError("settings_revision_changed")
        if set(changes) - {"execution_id"}:
            raise ControlError("manual_changes_invalid", 400)
        if pending_owner_request(controls, device, now) is not None:
            raise ControlError("manual_request_already_pending")
        if device != "eskom":
            active = _active_owner_target(connection, device)
            if kind == "run" and active:
                raise ControlError("device_already_has_owned_execution")
            if kind == "stop":
                if not active or not active.get("execution_id"):
                    raise ControlError("no_active_execution_to_stop")
                if changes.get("execution_id") not in {None, active["execution_id"]}:
                    raise ControlError("active_execution_changed")
                if device != "borehole":
                    from modules.telemetry.rootline_command_acceptance import command_execution
                    if not command_execution(active):
                        raise ControlError("manual_stop_requires_current_command_contract")
                changes = {"execution_id": active["execution_id"]}
            elif device.startswith("camp_"):
                plan = get_owner_plan(connection, now)
                task = next((r for r in plan["rows"] if r["device_id"] == device), None)
                if not task or task["skip"] or not task["editable"]:
                    raise ControlError("current_unstarted_programme_required")
        else:
            if changes:
                raise ControlError("manual_changes_invalid", 400)
            pending = connection.execute("""select 1 from public.sam_live_stock_conversation_review_events c
                where c.event_source='rootline_irrigation_execution'
                  and c.review_json->'rootline_execution'->>'action'='claim_eskom_before_command'
                  and not exists (select 1 from public.sam_live_stock_conversation_review_events t
                    where t.event_source=c.event_source
                      and t.review_json->'rootline_execution'->>'execution_id'=c.review_json->'rootline_execution'->>'execution_id'
                      and t.review_json->'rootline_execution'->>'action'='record_eskom_completed') limit 1""").fetchone()
            if pending:
                raise ControlError("device_already_has_owned_execution")
    else:
        raise ControlError("control_kind_unknown", 400)
    return {"kind": kind, "device_id": device, "expected_revision": payload["expected_revision"],
        "reason": reason.strip(), "changes": deepcopy(changes)}


def _validate_plan_rows(changes, current):
    rows = changes.get("rows")
    existing = {row["id"]: row for row in current["rows"]}
    if set(changes) != {"rows"} or not isinstance(rows, list) or len(rows) != len(existing):
        raise ControlError("plan_rows_invalid", 400)
    if {r.get("id") for r in rows if isinstance(r, dict)} != set(existing):
        raise ControlError("plan_row_identity_changed", 400)
    for index, row in enumerate(rows):
        if set(row) != {"id", "order", "duration_minutes", "priority", "reason", "skip"}:
            raise ControlError("plan_row_fields_invalid", 400)
        if type(row["order"]) is not int or row["order"] != index + 1:
            raise ControlError("plan_order_invalid", 400)
        if type(row["duration_minutes"]) is not int or not 1 <= row["duration_minutes"] <= existing[row["id"]]["maximum_duration_minutes"]:
            raise ControlError("plan_duration_invalid", 400)
        if row["priority"] not in {"high", "normal", "low"} or type(row["skip"]) is not bool:
            raise ControlError("plan_priority_or_skip_invalid", 400)
        if not isinstance(row["reason"], str) or not 1 <= len(row["reason"].strip()) <= 500:
            raise ControlError("plan_reason_required", 400)
        prior = existing[row["id"]]
        if not prior["editable"] and any(row[key] != prior[key] for key in row):
            raise ControlError("started_work_cannot_be_edited")
    normalized = deepcopy(rows)
    ranked = sorted((r for r in normalized if existing[r["id"]]["editable"]),
        key=lambda row: ({"high": 0, "normal": 1, "low": 2}[row["priority"]], row["order"]))
    choices = iter(ranked)
    normalized = [next(choices) if existing[row["id"]]["editable"] else row for row in normalized]
    for index, row in enumerate(normalized):
        row["order"] = index + 1
    return {"rows": normalized}


def _validate_camp_fields(fields):
    from modules.telemetry.rootline_timed_control import MAX_IRRIGATION_SECONDS
    if fields == {}:
        return {}
    if (not isinstance(fields, dict) or set(fields) != {"duration_minutes"}
            or type(fields["duration_minutes"]) is not int
            or not 1 <= fields["duration_minutes"] <= MAX_IRRIGATION_SECONDS // 60):
        raise ValueError("camp_duration_out_of_range")
    return dict(fields)


def _validate_owner_fields(device, fields, *, require_full=False):
    from modules.telemetry.rootline_energy_policy import ENERGY_CONTROL_FIELDS, validate_energy_control_fields
    from modules.telemetry.rootline_owner_auxiliary_policy import AUXILIARY_CONTROL_FIELDS, validate_auxiliary_control_fields
    if device.startswith("camp_"):
        return _validate_camp_fields(fields)
    energy = set(ENERGY_CONTROL_FIELDS.get(device, {}))
    auxiliary = set(AUXILIARY_CONTROL_FIELDS.get(device, {}))
    if not isinstance(fields, dict) or set(fields) - energy - auxiliary:
        raise ValueError("unsupported_settings_field")
    if require_full and set(fields) != energy | auxiliary:
        raise ValueError("settings_full_snapshot_required")
    return {**validate_energy_control_fields(device, {k: v for k, v in fields.items() if k in energy}),
        **validate_auxiliary_control_fields(device, {k: v for k, v in fields.items() if k in auxiliary})}


def preview_owner_control(payload, actor_identity, *, database_url=None, now=None):
    database_url = database_url or os.environ.get("DATABASE_URL")
    try:
        actor = _actor(actor_identity)
        key = _request_key(payload.get("idempotency_key") if isinstance(payload, dict) else None)
        identity = "ROOTLINE-OWNER-PREVIEW-" + _digest([actor, key])
        with _connect(database_url, read_only=False) as connection:
            _lock(connection)
            observed = _now(connection, now)
            records = _read_records(connection)
            prior = next((r for r in records if _valid_record(r, "preview")
                and r["context"].get("preview_id") == identity), None)
            request_digest = _digest(payload)
            if prior:
                if prior["context"]["request_digest"] != request_digest:
                    raise ControlError("idempotency_key_conflict")
                return {"success": True, "status": "preview_ready", "preview": prior["context"]["preview"]}, 200
            controls = project_owner_controls(records, now=observed)
            change = _normalize_change(payload, controls, connection, observed)
            expiry = _midnight(observed) if change["kind"] in {"plan", "run", "stop"} or change["changes"].get("scope") == "today" else None
            material = {"actor": actor, "change": change, "effective_at": observed.isoformat(),
                "expires_at": expiry.isoformat() if expiry else None, "preview_id": identity,
                "preview_expires_at": min(observed + timedelta(minutes=10), _midnight(observed)).isoformat(),
                "request_digest": request_digest}
            digest = _digest(material)
            preview = {"id": identity, "digest": digest, "effective_at": material["effective_at"],
                "expires_at": material["preview_expires_at"], "effective_until": material["expires_at"], "changes": _preview_changes(change, controls, connection, observed),
                "warnings": ["Existing accepted shutdown deadlines remain unchanged."]}
            _write(connection, identity, {**material, "digest": digest, "preview": preview}, "preview", database_url=database_url)
        return {"success": True, "status": "preview_ready", "preview": preview}, 200
    except Exception as exc:
        return _failure(exc)


def _preview_changes(change, controls, connection, now):
    if change["kind"] == "settings":
        prior = controls["devices"][change["device_id"]]
        from modules.telemetry.rootline_water_energy_plan import get_current_water_energy_plan
        plan, _ = get_current_water_energy_plan(now.astimezone(ZA).date().isoformat(), connection=connection)
        schema = owner_device_settings(change["device_id"], controls, plan, now)
        result = [{"label": NAMES[change["device_id"]] + " " + key,
            "before": str(prior.get(key)).replace("_", " "), "after": str(change["changes"][key]).replace("_", " ")}
            for key in ("mode", "scope") if prior.get(key) != change["changes"][key]]
        for field in schema["fields"]:
            if field["key"] in change["changes"]["fields"]:
                value = change["changes"]["fields"][field["key"]]
                if value != field["value"]:
                    result.append({"label": field["label"] + " (" + field["unit"] + ")",
                        "before": field["value"], "after": value})
        return result
    if change["kind"] in {"run", "stop"}:
        return [{"label": NAMES[change["device_id"]], "before": "Current programme",
            "after": "One eligible execution queued for today" if change["kind"] == "run"
                else "Supervised stop requested; automatic starts paused for today"}]
    return [{"label": next((NAMES[k] for k, v in DEVICES.items() if row["id"] == "irrigation_" + v), row["id"]), "before": "Saved programme", "after":
        f"{row['order']}. {row['duration_minutes']} minutes; {row['priority']}; "
        f"{'skip today' if row['skip'] else 'include today'}; {row['reason']}"}
        for row in change["changes"]["rows"]]


def apply_owner_control(payload, actor_identity, *, database_url=None, now=None):
    database_url = database_url or os.environ.get("DATABASE_URL")
    try:
        actor = _actor(actor_identity)
        if not isinstance(payload, dict) or set(payload) != {"preview_id", "preview_digest", "idempotency_key"}:
            raise ControlError("apply_payload_invalid", 400)
        key = _request_key(payload["idempotency_key"])
        request_id = "ROOTLINE-OWNER-APPLY-" + _digest([actor, key])
        request_digest = _digest(payload)
        with _connect(database_url, read_only=False) as connection:
            _lock(connection)
            observed = _now(connection, now)
            records = _read_records(connection)
            prior = next((r for r in records if _valid_record(r, "confirmed")
                and r["context"].get("request_id") == request_id), None)
            # Successful retries always read their original receipt, even after
            # a preview expires or a later owner decision changes the revision.
            if prior:
                if prior["context"].get("request_digest") != request_digest:
                    raise ControlError("idempotency_key_conflict")
                return deepcopy(prior["context"]["receipt"]), 200
            preview = next((r["context"] for r in records if _valid_record(r, "preview")
                and r["context"].get("preview_id") == payload["preview_id"]), None)
            if not preview or preview["actor"] != actor or preview["digest"] != payload["preview_digest"]:
                raise ControlError("preview_binding_invalid", 403)
            if _time(preview["preview_expires_at"]) <= observed:
                raise ControlError("preview_expired", 410)
            if any(r["context"].get("preview_id") == payload["preview_id"] for r in records if _valid_record(r, "confirmed")):
                raise ControlError("preview_already_applied")
            controls = project_owner_controls(records, now=observed)
            change = _normalize_change(preview["change"], controls, connection, observed)
            revision = request_id
            if change["kind"] == "plan":
                revision = _apply_plan(connection, change, observed, actor, database_url)
            receipt = {"success": True, "status": "queued" if change["kind"] in {"run", "stop"} else "saved", "readback_bound": True,
                "revision": revision, "effective_at": observed.isoformat()}
            context = {"actor": actor, "change": change, "request_id": request_id,
                "request_digest": request_digest, "preview_id": payload["preview_id"],
                "preview_digest": payload["preview_digest"], "effective_at": observed.isoformat(),
                "expires_at": preview["expires_at"], "receipt": receipt}
            _write(connection, request_id, context, "confirmed", database_url=database_url)
            if change["kind"] == "stop" and change["device_id"] != "eskom":
                _write(connection, request_id + "-CONSUMED", {"actor": actor,
                    "request_id": request_id, "execution_id": change["changes"]["execution_id"],
                    "device_id": change["device_id"], "at": observed.isoformat()},
                    "consumed", database_url=database_url)
            readback = _read_records(connection)
            stored = next((r for r in readback if _valid_record(r, "confirmed")
                and r["context"].get("request_id") == request_id), None)
            if not stored or stored["context"] != {**context, "contract_version": VERSION,
                    "event_type": "owner_control", "source": "authenticated_owner_controls"}:
                raise ControlError("owner_control_readback_failed", 503)
        return receipt, 200
    except Exception as exc:
        return _failure(exc)


def _active_owner_target(connection, device):
    from modules.telemetry.rootline_irrigation_execution_store import _load
    if device.startswith("camp_"):
        active = _load("load_active", None, connection=connection)
        return active if active and active.get("zone_id") == DEVICES[device] else None
    if device == "borehole":
        return _load("load_active_borehole", None, connection=connection)
    if device in {"mixer", "injection"}:
        return _load("load_active_auxiliary", DEVICES[device], connection=connection)
    return None


def owner_stop_for_execution(active, *, database_url=None):
    """A saved exact-duty stop stays binding until that duty reaches terminal."""
    with _connect(database_url or os.environ.get("DATABASE_URL"), read_only=True) as connection:
        controls = read_owner_controls(connection)
    return next((r for r in reversed(controls["requests"]) if r["change"]["kind"] == "stop"
        and r["change"]["changes"].get("execution_id") == active.get("execution_id")
        and DEVICES.get(r["change"]["device_id"]) in {
            active.get("zone_id"), active.get("auxiliary_device_id"),
            "BOREHOLE-1-MINI-R4-CH1" if active.get("device_key") == "ewelink:ewelink_owner_account:1002851416:1" else None}), None)


def satisfy_owner_eskom_request(payload, *, database_url=None):
    database_url = database_url or os.environ.get("DATABASE_URL")
    try:
        with _connect(database_url, read_only=False) as connection:
            connection.execute("select pg_advisory_xact_lock(%s)", (1874320914,))
            now = _now(connection)
            controls = read_owner_controls(connection, now=now)
            request = pending_owner_request(controls, "eskom", now)
            if request is None or request["request_id"] != payload.get("owner_request_id"):
                return {"success": False, "status": "owner_request_changed"}
            expected = "ON" if request["change"]["kind"] == "run" else "OFF"
            previous = payload.get("previous_readback") or {}
            if (payload.get("desired_state") != expected or previous.get("state") != expected
                    or previous.get("authoritative") is not True or not previous.get("evidence_id")
                    or payload.get("device_key") != "ifttt_smartlife:smartlife_owner_account:" + str(previous.get("device_id")) + ":1"
                    or not timedelta(0) <= now - _time(previous.get("retrieved_at")) <= timedelta(minutes=2)):
                return {"success": False, "status": "owner_request_readback_unproven"}
            _write(connection, request["request_id"] + "-CONSUMED", {"actor": request["actor"],
                "request_id": request["request_id"], "execution_id": "ROOTLINE-OWNER-NOOP-" + request["request_id"],
                "device_id": "eskom", "at": now.isoformat(), "satisfied_without_command": True,
                "evidence_id": previous["evidence_id"]}, "consumed", database_url=database_url)
        return {"success": True, "created": True, "status": "owner_request_satisfied_without_command", "hardware_commands": 0}
    except Exception:
        return {"success": False, "status": "owner_request_satisfaction_unavailable", "hardware_commands": 0}


def _apply_plan(connection, change, now, actor, database_url):
    from modules.telemetry.rootline_water_energy_plan import get_current_water_energy_plan, _hash_program, _append_program_readback
    day = now.astimezone(ZA).date().isoformat()
    connection.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", ("rootline-water-energy:" + day,))
    current, _ = get_current_water_energy_plan(day, connection=connection)
    if _plan_revision(current) != change["expected_revision"]:
        raise ControlError("plan_revision_changed")
    _validate_plan_rows(change["changes"], get_owner_plan(connection, now))
    plan = deepcopy(current)
    rows = {r["id"]: r for r in change["changes"]["rows"]}
    started = _started_tasks(connection, current)
    tasks = plan["daily_program"]["base_tasks"]
    for task in tasks:
        row = rows.get(task["task_id"])
        if row is None or task["task_id"] in started:
            continue
        total = row["duration_minutes"]
        segment = min(total, task.get("max_execution_minutes") or total)
        task.update(requested_total_duration_minutes=total, planned_duration_minutes=segment,
            expected_segment_count=math.ceil(total / segment), owner_priority=row["priority"],
            owner_order=row["order"], scheduled_order=row["order"], rank=row["order"], owner_skip=row["skip"],
            owner_edited=True, reason=row["reason"])
        if row["skip"]:
            task.update(zone_decision="Hold", recommendation="Hold", live_adjustment_reason="owner_skipped_today")
        # An edit may reduce existing carry allocation, never create additional
        # carry credit or rewrite the underlying outstanding obligation.
        remaining = total
        for allocation in task.get("carry_allocations", []):
            allocation["minutes"] = min(allocation["minutes"], remaining)
            remaining -= allocation["minutes"]
    tasks.sort(key=lambda task: rows.get(task["task_id"], {}).get("order", len(rows) + 1))
    eligible = [t for t in tasks if t["task_id"] in rows and t["task_id"] not in started]
    starts = [_time(t["planned_start_at"]) for t in eligible if t.get("planned_start_at")]
    cursor = max(now, min(starts)) if starts else now
    end = _time(plan["daily_program"]["end_at"])
    for task in eligible:
        finish = cursor + timedelta(minutes=task["requested_total_duration_minutes"])
        if finish > end and not task.get("owner_skip"):
            raise ControlError("edited_programme_exceeds_today")
        task.update(planned_start_at=cursor.isoformat(), planned_end_at=finish.isoformat(),
            due_window={"start": cursor.isoformat(), "end": finish.isoformat()}, preferred_window=cursor.isoformat())
        if not task.get("owner_skip"):
            cursor = finish
    plan["candidate_tasks"] = deepcopy(tasks)
    plan["daily_program"]["owner_edit"] = {"actor": actor, "at": now.isoformat(), "reason": change["reason"]}
    plan["replacement_reason"] = "owner_confirmed_remaining_programme"
    _hash_program(plan)
    saved, status = _append_program_readback(plan, actor, database_url, connection)
    if status >= 400 or saved.get("evidence_sha256") != plan["evidence_sha256"]:
        raise ControlError("plan_readback_failed", 503)
    return _plan_revision(saved)
