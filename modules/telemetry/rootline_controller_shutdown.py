"""Owned controller OFF retries on the existing execution audit rail."""
import os
from datetime import timedelta

from modules.telemetry.rootline_command_acceptance import command_execution, controller_accepted, duty_closed


def dispatch_owned_off(body):
    from modules.telemetry import rootline_irrigation_execution_store as s
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    execution = body.get("execution") or {}
    dispatch = body.get("dispatch")
    if not command_execution(execution) or not callable(dispatch):
        return {"accepted_unambiguous": False, "provider_command_attempted": False, "status": "shutdown_binding_invalid"}
    family = ("borehole_" if execution["device_id"] == "1002851416" else
        "auxiliary_" if execution.get("auxiliary_device_id") else "")
    claim_action, outcome_action = f"claim_{family}off_attempt", f"record_{family}off_outcome"
    unchanged = ("device_id", "channel", "claimed_at", "primary_stop_deadline", "job_id", "job_sha256", "zone_id", "auxiliary_device_id")
    def inspect(cursor):
        rows = s._managed_edge_rows(cursor, execution["execution_id"])
        originals = [row for row in rows if row.get("action") in {
            "claim_before_on", "claim_auxiliary_before_on", "claim_borehole_before_on", "adopt_borehole_observed_on", "mark_borehole_active"}]
        valid = any(all(row.get(key) == execution.get(key) for key in unchanged) for row in originals)
        valid = valid and not any(duty_closed(row) or row.get("manual_isolation_active") is True
            or row.get("action") in {
                "record_execution_not_dispatched", "record_auxiliary_startup_aborted", "record_borehole_aborted"} for row in rows)
        cursor.execute("""select exists(select 1 from public.sam_live_stock_conversation_review_events
            where event_source=%s and review_json->'rootline_execution'->>'device_id'=%s
            and review_json->'rootline_execution'->>'channel'=%s
            and review_json->'rootline_execution'->>'execution_id'<>%s
            and review_json->'rootline_execution'->>'action' in
                ('claim_before_on','claim_auxiliary_before_on','claim_borehole_before_on','adopt_borehole_observed_on')
            and (review_json->'rootline_execution'->>'claimed_at')::timestamptz>%s::timestamptz)""",
            (s.EVENT_SOURCE, execution["device_id"], str(execution["channel"]),
                execution["execution_id"], execution["claimed_at"]))
        valid = valid and not cursor.fetchone()[0]
        receipt = next((row.get("outcome") for row in rows if row.get("action") == outcome_action
            and controller_accepted(row.get("outcome"), execution, "OFF")), None)
        return rows, valid, receipt
    def connect():
        return connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"), read_only=False, read_committed=True)
    def lock(cursor):
        cursor.execute("select pg_advisory_xact_lock(%s)", (1874320911,))
        cursor.execute("select pg_advisory_xact_lock(%s)", (1874320912,))
    with connect() as connection, connection.cursor() as cursor:
        lock(cursor)
        rows, valid, receipt = inspect(cursor)
        if receipt is not None:
            return {"reused_outcome": receipt}
        if not valid:
            return {"accepted_unambiguous": False, "provider_command_attempted": False, "status": "shutdown_ownership_retired"}
        attempts = [row for row in rows if row.get("action") == claim_action]
        number = max((int(row.get("attempt") or 0) for row in attempts), default=0)+1
        cursor.execute("select clock_timestamp()")
        now = cursor.fetchone()[0]
        if attempts:
            cursor.execute("""select max(created_at) from public.sam_live_stock_conversation_review_events
                where event_source=%s and review_json->'rootline_execution'->>'execution_id'=%s
                and review_json->'rootline_execution'->>'action'=%s""",
                (s.EVENT_SOURCE, execution["execution_id"], claim_action))
            last = cursor.fetchone()[0]
            pending = any(not any(row.get("action") == outcome_action and row.get("attempt") == attempt.get("attempt")
                for row in rows) for attempt in attempts)
            if (number > 3 or pending) and (last is None or now < last+timedelta(minutes=5)):
                return {"accepted_unambiguous": False, "provider_command_attempted": False, "status": "shutdown_retry_not_due"}
        slot = {"execution_id": execution["execution_id"], "attempt": number,
            "shutdown_retry_contract": "rootline_controller_shutdown.v1", "shutdown_attempt_claimed_at": now.isoformat()}
        for key in ("stop_reason", "stop_trigger"):
            original = next((row[key] for row in rows if row.get(key) is not None), execution.get(key))
            if original is not None:
                slot[key] = original
        saved = s._insert_managed_event(cursor, claim_action, slot)
        if saved.get("created") is not True:
            return {"accepted_unambiguous": False, "provider_command_attempted": False, "status": "shutdown_attempt_owned"}
    # Claim committed before I/O. The second lock serializes accepted receipt reuse.
    with connect() as connection, connection.cursor() as cursor:
        lock(cursor)
        rows, valid, receipt = inspect(cursor)
        if receipt is not None:
            return {"reused_outcome": receipt}
        if any(row.get("action") == claim_action and int(row.get("attempt") or 0) > number for row in rows):
            return {"accepted_unambiguous": False, "provider_command_attempted": False, "status": "shutdown_attempt_superseded"}
        if not valid:
            return {"accepted_unambiguous": False, "provider_command_attempted": False, "status": "shutdown_ownership_retired"}
        try:
            outcome = dispatch(number)
        except Exception:
            outcome = {"accepted_unambiguous": False, "provider_command_attempted": True, "status": "shutdown_response_unknown"}
        if not isinstance(outcome, dict):
            outcome = {"accepted_unambiguous": False, "provider_command_attempted": True, "status": "shutdown_response_unknown"}
        s._insert_managed_event(cursor, outcome_action, {**slot, "outcome": outcome})
        return outcome


def bounded_off(execution, store, transport):
    outcomes, commands = [], 0
    for _ in range(3):
        outcome = store("dispatch_controller_off", {"execution": execution,
            "dispatch": lambda attempt: transport.set_state(device_id=execution["device_id"], channel=execution["channel"],
                state="OFF", idempotency_key=f"{execution['execution_id']}:OFF:{attempt}")})
        if not isinstance(outcome, dict):
            break
        if isinstance(outcome.get("reused_outcome"), dict):
            outcomes.append(outcome["reused_outcome"])
            break
        outcomes.append(outcome)
        commands += int(outcome.get("provider_command_attempted") is True)
        if controller_accepted(outcome, execution, "OFF") or outcome.get("provider_command_attempted") is not True:
            break
    return {"commands": commands, "outcomes": outcomes}
