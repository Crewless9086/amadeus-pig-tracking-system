"""Pure mixer admission from existing immutable execution events.

An accepted early stop can leave capacity in its original reservation. A new
execution consumes that capacity; neither the original claim nor its deadline
changes. Receipt precision is retained in integer microseconds. This projection
is advisory until the existing claim transaction repeats it under its locks.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from modules.telemetry.rootline_command_acceptance import (
    MODE, accepted, digest, duty_closed, moment, terminal_matches_rows)

CONTRACT = "rootline_mixer_reservation_session.v1"
DEVICE = "FERTILIZER-MIXER-CH2"
MICROSECOND = timedelta(microseconds=1)
SECOND = 1_000_000
DAY_CAP = 1800 * SECOND
SESSION_CAP = 6
_CLAIM = "claim_auxiliary_before_on"
_REQUIRED = (_CLAIM, "claim_auxiliary_dispatch", "record_auxiliary_on_outcome",
    "mark_auxiliary_active", "claim_auxiliary_off_attempt",
    "record_auxiliary_off_outcome", "record_auxiliary_completed")
_IMMUTABLE = ("execution_id", "eligibility_id", "eligibility_sha256", "consumption_key",
    "auxiliary_device_id", "device_type", "device_id", "channel", "claimed_at",
    "maximum_duration_seconds", "primary_stop_deadline", "stop_mode", "acceptance_mode",
    "batch_generation", "mixer_session")


def _micros(delta):
    return delta // MICROSECOND


def _body(row):
    return {key: value for key, value in row.items() if key not in {"action", "event_id"}}


def _canonical(row):
    from modules.telemetry.rootline_irrigation_execution_store import _event_id
    return (isinstance(row, dict) and isinstance(row.get("action"), str)
        and row.get("event_id") == _event_id(row["action"], _body(row)))


def _canonical_closed_chain(rows):
    selected = {}
    for action in _REQUIRED:
        matching = [row for row in rows if row.get("action") == action]
        if len(matching) != 1:
            return None
        selected[action] = matching[0]
    from modules.telemetry.rootline_irrigation_execution_store import _event_id
    for action, row in selected.items():
        if _canonical(row):
            continue
        # A supervisor resumes a stored Active row. The existing writer hashes
        # its inherited action/event_id before replacing them with this event's
        # identity. Validate that exact predecessor rather than relaxing hashes.
        active = selected["mark_auxiliary_active"]
        if (action != "record_auxiliary_completed" or row.get("event_id") != _event_id(action,
                {**_body(row), "action": active["action"], "event_id": active["event_id"]})):
            return None
    return selected


def closed_command_session(rows, *, now, _final_off_attempt=1):
    """Require one complete, unambiguous canonical command chain.

    completed_at historically uses the supervisor's pre-OFF clock snapshot.
    The validated receipt times, not that field or rounded accounting, measure
    the interval. Sparse OFF records deliberately carry only execution/attempt.
    """
    selected = _canonical_closed_chain(rows)
    if selected is None:
        return None
    claim = selected[_CLAIM]
    terminal = selected["record_auxiliary_completed"]
    duration = claim.get("maximum_duration_seconds")
    claimed = moment(claim.get("claimed_at"))
    deadline = moment(claim.get("primary_stop_deadline"))
    if (claim.get("auxiliary_device_id") != DEVICE or claim.get("device_type") != "fertilizer_mixer"
            or claim.get("device_id") != "100204d497" or type(claim.get("channel")) is not int
            or claim["channel"] != 2 or claim.get("acceptance_mode") != MODE
            or claim.get("stop_mode") != "scheduled" or claim.get("state") != "claimed"
            or type(claim.get("on_attempts")) is not int or claim["on_attempts"] != 0
            or type(duration) is not int or not 0 < duration <= 1800
            or claimed is None or deadline != claimed + timedelta(seconds=duration)
            or not duty_closed(terminal) or not terminal_matches_rows(terminal, rows)):
        return None
    if terminal.get("reason") in {"manual_isolation", "manual_off", "emergency_stop"}:
        return None
    for action in (_CLAIM, "claim_auxiliary_dispatch", "record_auxiliary_on_outcome",
                   "mark_auxiliary_active", "record_auxiliary_completed"):
        if any(selected[action].get(key) != claim.get(key) for key in _IMMUTABLE):
            return None
    if len({row.get("event_id") for row in selected.values()}) != len(selected):
        return None
    # The full history is ordered by canonical ingestion; an OFF barrier cannot
    # precede dispatch/activation, and an outcome cannot precede its barrier.
    positions = [rows.index(selected[action]) for action in _REQUIRED]
    if positions != sorted(positions):
        return None
    on = selected["record_auxiliary_on_outcome"].get("on_outcome")
    off_row = selected["record_auxiliary_off_outcome"]
    off = off_row.get("outcome")
    barrier = selected["claim_auxiliary_off_attempt"]
    if (not accepted(on, claim, "ON") or not accepted(off, claim, "OFF")
            or on != terminal.get("command_on_receipt")
            or on != selected["mark_auxiliary_active"].get("command_on_receipt")
            or off != terminal.get("command_off_receipt")
            or on.get("entity_id") != off.get("entity_id")
            or type(_final_off_attempt) is not int or not 1 <= _final_off_attempt <= 3
            or type(barrier.get("attempt")) is not int or barrier["attempt"] != _final_off_attempt
            or off_row.get("attempt") != _final_off_attempt
            or off["idempotency_key"] != claim["execution_id"] + ":OFF:" + str(_final_off_attempt)
            or selected["mark_auxiliary_active"].get("on_attempts") != 1
            or selected["record_auxiliary_on_outcome"].get("on_attempts") != 1
            or terminal.get("on_attempts") != 1):
        return None
    start = moment(on["accepted_at"])
    stop = moment(off["accepted_at"])
    if not claimed <= moment(on["command_attempted_at"]) <= start < deadline:
        return None
    if not start <= moment(off["command_attempted_at"]) <= stop <= now:
        return None
    for row in rows:
        if (row.get("execution_id") != claim["execution_id"]
                or row.get("manual_isolation_active") is True or row.get("manual_off_active") is True
                or row.get("action") in {"contain_auxiliary_device", "record_auxiliary_exception",
                    "record_auxiliary_control_pulse_stopped", "record_auxiliary_startup_aborted",
                    "record_execution_not_dispatched"}
                or (row.get("command_on_receipt") is not None and row["command_on_receipt"] != on)
                or (row.get("command_off_receipt") is not None and row["command_off_receipt"] != off)):
            return None
    return {"claim": claim, "terminal": terminal, "elapsed_microseconds": _micros(stop-start),
        "stopped_at": stop, "started_at": start}


def closed_recovered_command_session(rows, *, now):
    """Resolve contiguous canonical OFF retries, without reusable allowance.

    Earlier unsuccessful/uncertain OFF requests make elapsed delivery unknown.
    A final accepted OFF can close the duty, but cannot refund its reservation.
    """
    barriers = [row for row in rows if row.get("action") == "claim_auxiliary_off_attempt"]
    outcomes = [row for row in rows if row.get("action") == "record_auxiliary_off_outcome"]
    count = len(barriers)
    if count not in {2, 3} or len(outcomes) != count:
        return None
    for number, (barrier, outcome) in enumerate(zip(barriers, outcomes), 1):
        if (type(barrier.get("attempt")) is not int or barrier["attempt"] != number
                or type(outcome.get("attempt")) is not int or outcome["attempt"] != number
                or not _canonical(barrier) or not _canonical(outcome)
                or not isinstance(outcome.get("outcome"), dict)
                or (number < count and outcome["outcome"].get("accepted_unambiguous") is True)):
            return None
    positions = [rows.index(row) for pair in zip(barriers, outcomes) for row in pair]
    if positions != sorted(positions):
        return None
    reduced = [row for row in rows if row not in barriers[:-1]+outcomes[:-1]]
    proven = closed_command_session(reduced, now=now, _final_off_attempt=count)
    if proven is None:
        return None
    active = next(row for row in reduced if row.get("action") == "mark_auxiliary_active")
    if positions[0] <= rows.index(active):
        return None
    identity = proven["claim"]["execution_id"]
    if any(row.get("execution_id") != identity for row in barriers+outcomes):
        return None
    for number, row in enumerate(outcomes[:-1], 1):
        outcome = row["outcome"]
        expected = {"device_id": proven["claim"]["device_id"], "channel": proven["claim"]["channel"],
            "requested_state": "OFF", "idempotency_key": identity+":OFF:"+str(number)}
        if any(key in outcome and outcome[key] != value for key, value in expected.items()):
            return None
        for key in ("command_attempted_at", "accepted_at"):
            if key in outcome:
                at = moment(outcome[key])
                if at is None or not proven["started_at"] <= at <= proven["stopped_at"]:
                    return None
    return {key: proven[key] for key in ("terminal", "started_at", "stopped_at")}


def closed_legacy_provider_session(rows, *, now):
    """Resolve a verified old controller duty without command credit/refund."""
    selected = _canonical_closed_chain(rows)
    if selected is None:
        return None
    claim = selected[_CLAIM]
    active = selected["mark_auxiliary_active"]
    terminal = selected["record_auxiliary_completed"]
    duration = claim.get("maximum_duration_seconds")
    claimed = moment(claim.get("claimed_at"))
    deadline = moment(claim.get("primary_stop_deadline"))
    from modules.telemetry.rootline_irrigation_lifecycle import controller_readback_time
    start = controller_readback_time(terminal, "start_evidence", "ON")
    stop = controller_readback_time(terminal, "shutdown_evidence", "OFF")
    if (claim.get("acceptance_mode") is not None or claim.get("mixer_session") is not None
            or claim.get("auxiliary_device_id") != DEVICE or claim.get("device_type") != "fertilizer_mixer"
            or claim.get("device_id") != "100204d497" or type(claim.get("channel")) is not int
            or claim["channel"] != 2 or claim.get("state") != "claimed" or claim.get("on_attempts") != 0
            or type(duration) is not int or not 0 < duration <= 1800
            or claimed is None or deadline != claimed+timedelta(seconds=duration)
            or start is None or stop is None or not claimed <= start < deadline <= stop <= now
            or terminal.get("state") != "Completed" or terminal.get("shutdown_verified") is not True
            or terminal.get("control_completed") is not True
            or terminal.get("control_completion_proof") != "authoritative_provider_on_then_off"
            or terminal.get("accounted_mixing_seconds") != duration
            or active.get("state") != "Active" or active.get("on_attempts") != 1
            or terminal.get("on_attempts") != 1
            or active.get("start_evidence") != terminal.get("start_evidence")):
        return None
    for action in (_CLAIM, "claim_auxiliary_dispatch", "record_auxiliary_on_outcome",
                   "mark_auxiliary_active", "record_auxiliary_completed"):
        if any(selected[action].get(key) != claim.get(key) for key in _IMMUTABLE):
            return None
    on = selected["record_auxiliary_on_outcome"].get("on_outcome")
    off = selected["record_auxiliary_off_outcome"].get("outcome")
    if (not isinstance(on, dict) or not isinstance(off, dict)
            or on.get("accepted_unambiguous") is not True or off.get("accepted_unambiguous") is not True
            or on.get("event") != "controller_1_ch2_on" or off.get("event") != "controller_1_ch2_off"
            or selected["record_auxiliary_on_outcome"].get("on_attempts") != 1
            or selected["claim_auxiliary_off_attempt"].get("attempt") != 1
            or selected["record_auxiliary_off_outcome"].get("attempt") != 1
            or [rows.index(selected[action]) for action in _REQUIRED] !=
                sorted(rows.index(selected[action]) for action in _REQUIRED)):
        return None
    for row in rows:
        if (row.get("execution_id") != claim["execution_id"]
                or row.get("manual_isolation_active") is True or row.get("manual_off_active") is True
                or row.get("action") in {"contain_auxiliary_device", "record_auxiliary_exception",
                    "record_auxiliary_control_pulse_stopped", "record_auxiliary_startup_aborted",
                    "record_execution_not_dispatched"}
                or row.get("command_on_receipt") is not None or row.get("command_off_receipt") is not None
                or (row.get("start_evidence") is not None and row["start_evidence"] != terminal["start_evidence"])
                or (row.get("shutdown_evidence") is not None and row["shutdown_evidence"] != terminal["shutdown_evidence"])):
            return None
    return {"terminal": terminal, "started_at": start, "stopped_at": stop}


def _candidate(*, day, now, reserved, sessions, roots, predecessor):
    if sessions >= SESSION_CAP:
        return None
    root = next((root for root in roots if root["remaining_microseconds"] >= SECOND), None)
    remaining = root["remaining_microseconds"] if root else max(0, DAY_CAP-reserved)
    # Slot identity must not vary as the clock approaches midnight. Callers
    # shorten the requested runtime; the locked claim checks its actual day.
    maximum = min(600, remaining // SECOND)
    if maximum < 1:
        return None
    prior = ({"predecessor_execution_id": predecessor["execution_id"],
        "predecessor_terminal_event_id": predecessor["event_id"],
        "predecessor_terminal_sha256": digest(predecessor)} if predecessor else
        {"predecessor_execution_id": None, "predecessor_terminal_event_id": None,
         "predecessor_terminal_sha256": None})
    identity = {"operating_date": day, "auxiliary_device_id": DEVICE, **prior}
    return {"contract_version": CONTRACT, **identity, "session_number": sessions+1,
        "kind": "continuation" if root else "reservation",
        "reservation_id": root["reservation_id"] if root else "ROOTLINE-MIX-RESERVATION-"+digest(identity)[:24].upper(),
        "root_execution_id": root["claim"]["execution_id"] if root else None,
        "root_claim_sha256": digest(root["claim"]) if root else None,
        "remaining_microseconds": remaining, "maximum_duration_seconds": maximum}


def session_key(session):
    return "ROOTLINE-AUX-CONSUME-"+digest(session)[:24].upper()


def initial_session(now):
    day = now.astimezone(ZoneInfo("Africa/Johannesburg")).date().isoformat()
    return _candidate(day=day, now=now, reserved=0, sessions=0, roots=[], predecessor=None)


def session_for_context(context, *, now):
    if "mixer_session" in context:
        return context["mixer_session"]
    # Older callers can propose only an empty-day first slot. The locked store
    # still derives its own complete history; this is never admission authority.
    if context.get("reserved_mixing_seconds_today", 0) == 0 and context.get("verified_mixing_sessions_today", 0) == 0:
        return initial_session(now)
    return None


def session_shape(session, *, now, duration):
    return (isinstance(session, dict) and session.get("contract_version") == CONTRACT
        and session.get("operating_date") == now.astimezone(ZoneInfo("Africa/Johannesburg")).date().isoformat()
        and session.get("auxiliary_device_id") == DEVICE
        and session.get("kind") in {"reservation", "continuation"}
        and type(session.get("session_number")) is int and 1 <= session["session_number"] <= SESSION_CAP
        and type(session.get("remaining_microseconds")) is int and 0 < session["remaining_microseconds"] <= DAY_CAP
        and type(session.get("maximum_duration_seconds")) is int
        and type(duration) is int and 1 <= duration <= session["maximum_duration_seconds"] <= 600
        and duration * SECOND <= session["remaining_microseconds"])


def project_mixer_sessions(executions, *, now):
    """Derive same-day envelopes, children and the next single-use proposal.

    Unknown or malformed execution chains preserve their reserved allowance and
    grant no continuation. Children share their root allowance and each count
    toward the existing six-session limit. Plan and batch are provenance only.
    """
    from modules.telemetry.rootline_irrigation_execution_store import (
        _verified_not_dispatched, _verified_auxiliary_startup_abort, _verified_unstarted_auxiliary_reconciliation)
    now = now.astimezone(timezone.utc)
    day_start = now.astimezone(ZoneInfo("Africa/Johannesburg")).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    day = day_start.date().isoformat()
    rows = [row for row in executions or [] if isinstance(row, dict)]
    mixer_ids = {row.get("execution_id") for row in rows if row.get("auxiliary_device_id") == DEVICE
        or row.get("device_type") == "fertilizer_mixer"
        or (row.get("device_id") == "100204d497" and row.get("channel") == 2)}
    groups = {identity: [] for identity in mixer_ids}
    for row in rows:
        if row.get("execution_id") in groups:
            groups[row.get("execution_id")].append(row)
    claims = []
    valid = True
    for identity, history in groups.items():
        if any(_verified_not_dispatched(row, history) for row in history):
            continue
        found = [row for row in history if row.get("action") == _CLAIM]
        if not found and all(row.get("action") == "record_auxiliary_eligibility" for row in history):
            continue
        if len(found) != 1 or not identity:
            valid = False
            continue
        claim = found[0]
        at = moment(claim.get("claimed_at")); duration = claim.get("maximum_duration_seconds")
        if at is None or type(duration) is not int or not 0 < duration <= 1800:
            valid = False
            continue
        if at > now:
            valid = False
        claims.append((at, str(identity), claim, history))
    claims.sort(key=lambda item: (item[0], item[1]))
    reserved = sessions = commanded = 0
    roots = []
    predecessor = None
    child_ids = []
    for at, identity, claim, history in claims:
        duration = claim["maximum_duration_seconds"]
        overlap = max(0, _micros(min(at+timedelta(seconds=duration), day_end)-max(at, day_start)))
        session = claim.get("mixer_session")
        closed = closed_command_session(history, now=now)
        legacy = (closed_recovered_command_session(history, now=now)
            or closed_legacy_provider_session(history, now=now)) if closed is None else None
        legacy_overlap = (max(0, _micros(min(legacy["stopped_at"], day_end)-max(legacy["started_at"], day_start)))
            if legacy else 0)
        actual_overlap = (max(0, _micros(min(closed["stopped_at"], day_end)-max(closed["started_at"], day_start)))
            if closed else 0)
        relevant = overlap > 0 or actual_overlap > 0 or legacy_overlap > 0 or (isinstance(session, dict) and session.get("operating_date") == day)
        abort = next((row for row in history if row.get("action") == "record_auxiliary_startup_aborted"
            and _verified_auxiliary_startup_abort(row, history)), None)
        if abort is None:
            abort = next((row for row in history if row.get("action") == "reconcile_unstarted_auxiliary"
                and _verified_unstarted_auxiliary_reconciliation(row, history)), None)
        if closed is None and abort is None and legacy is None:
            valid = False
        if any(row.get("manual_isolation_active") is True or row.get("manual_off_active") is True for row in history):
            valid = False
        if not relevant:
            continue
        if at < day_start:
            # A prior day's accepted OFF can arrive after midnight. Charge its
            # current-day interval as well as any legacy reservation overlap;
            # never transfer its unused allowance into today's new envelopes.
            if session is not None and not session_shape(session, now=at, duration=duration):
                valid = False
            reserved += max(overlap, actual_overlap, legacy_overlap)
            commanded += actual_overlap
            sessions += 1
            predecessor = closed["terminal"] if closed else legacy["terminal"] if legacy else abort
            continue
        previous_stop = moment((predecessor or {}).get("command_off_receipt", {}).get("accepted_at"))
        if previous_stop is not None and at < previous_stop:
            valid = False
        root = None
        if session is not None:
            expected = _candidate(day=day, now=at, reserved=reserved, sessions=sessions,
                roots=roots, predecessor=predecessor)
            if (not session_shape(session, now=at, duration=duration) or session != expected
                    or at < day_start or at+timedelta(seconds=duration) > day_end
                    or not _canonical(claim)):
                valid = False
            elif session["kind"] == "continuation":
                root = next((root for root in roots if root["claim"]["execution_id"] == session["root_execution_id"]), None)
                if root:
                    child_ids.append(identity)
        sessions += 1
        if root is None:
            reserved += overlap
            root = {"claim": claim, "reservation_id": (session["reservation_id"]
                if isinstance(session, dict) and session.get("kind") == "reservation" else claim.get("event_id")),
                "remaining_microseconds": 0, "charged_microseconds": overlap,
                "consumed_microseconds": 0, "envelope_microseconds": duration*SECOND}
            roots.append(root)
        if closed:
            elapsed = closed["elapsed_microseconds"]
            root["consumed_microseconds"] += elapsed
            # An observed overrun cannot buy another allowance. Its excess is
            # charged, even though the original reservation stays immutable.
            reserved += max(0, root["consumed_microseconds"]-root["charged_microseconds"])
            root["charged_microseconds"] = max(root["charged_microseconds"], root["consumed_microseconds"])
            root["remaining_microseconds"] = (max(0, root["envelope_microseconds"]-root["consumed_microseconds"])
                if day_start <= at and at+timedelta(seconds=duration) <= day_end
                and day_start <= closed["stopped_at"] < day_end else 0)
            commanded += actual_overlap
            predecessor = closed["terminal"]
        else:
            # Provider closure resolves the duty without converting controller
            # history into accepted-command seconds or unused allowance.
            reserved += max(0, legacy_overlap-overlap)
            root["remaining_microseconds"] = 0
            predecessor = legacy["terminal"] if legacy else abort
    proposal = (_candidate(day=day, now=now, reserved=reserved, sessions=sessions,
        roots=roots, predecessor=predecessor) if valid and reserved <= DAY_CAP else None)
    return {"session_history_valid": valid, "mixer_session": proposal,
        "session_reserved_microseconds": reserved, "session_count": sessions,
        "child_execution_ids": child_ids, "command_accounted_microseconds": commanded,
        "known_residual_microseconds": sum(root["remaining_microseconds"] for root in roots),
        "command_shortfall_microseconds": max(0, DAY_CAP-commanded), "physical_outcome": "Unknown"}
