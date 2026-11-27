"""Per-controller reachability episodes on ROOTLINE's existing execution audit rail.
Reachability never proves relay state. No provider calls or equipment commands.
"""
from datetime import datetime, timezone
from hashlib import sha256
import os

CONTRACT = "rootline_controller_availability.v1"
ACTION = "record_controller_availability"
CONTROLLERS = {"100204e9bc": "Camps A, B, C and E", "100204d497": "Mixer and injection", "1002851416": "Borehole"}
TABLE = "public.sam_live_stock_conversation_review_events"


def moment(value):
    try:
        value = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return value if value.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def project_availability(device_id, observation, previous=None, *, now):
    now = moment(now); previous = previous or {}
    if device_id not in CONTROLLERS or now is None or not isinstance(observation, dict):
        raise ValueError("controller_availability_binding_invalid")
    checked = moment(observation.get("checked_at"))
    state = observation.get("state")
    if (state not in {"online", "offline", "unknown"} or checked is None or
            not 0 <= (now-checked).total_seconds() <= 300 or
            observation.get("source") not in {"online": {"correlated_controller_query", "controller_command_response"},
                "offline": {"controller_query_unanswered"}, "unknown": {"correlated_controller_query"}}.get(state,set()) or
            observation.get("output_state") != "Unknown"):
        raise ValueError("controller_availability_observation_invalid")
    if previous and (previous.get("contract") != CONTRACT or previous.get("device_id") != device_id):
        raise ValueError("controller_availability_preimage_invalid")
    prior_check = moment(previous.get("checked_at"))
    if prior_check and checked <= prior_check:
        return {**previous, "changed": False}
    offline_since = previous.get("offline_since")
    incident = previous.get("incident_id")
    recovered_at = previous.get("recovered_at")
    duration = previous.get("recovery_duration_seconds")
    transition = None
    if state == "offline" and (not offline_since or recovered_at):
        offline_since = checked.isoformat(); recovered_at = None; duration = None
        incident = "ROOTLINE-CONTROLLER-" + sha256((device_id+"|"+offline_since).encode()).hexdigest()[:32].upper()
        transition = "ControllerOffline"
    elif state == "online" and offline_since and not recovered_at:
        recovered_at = checked.isoformat()
        duration = max(0, int((checked-moment(offline_since)).total_seconds()))
        transition = "ControllerRecovered"
    # Unknown preserves an open episode; it neither declares an outage nor recovery.
    return {"contract": CONTRACT, "device_id": device_id, "state": state,
        "checked_at": checked.isoformat(), "source": observation["source"], "output_state": "Unknown",
        "offline_since": offline_since, "incident_id": incident, "recovered_at": recovered_at,
        "recovery_duration_seconds": duration, "transition": transition, "changed": True}


def _latest(cursor, device_id):
    cursor.execute(f"""select review_json->'rootline_execution' from {TABLE}
        where event_source='rootline_irrigation_execution' and chatwoot_conversation_id=%s
          and review_json->'rootline_execution'->>'action'=%s
        order by created_at desc,review_event_id desc limit 1""", ("ROOTLINE-CONTROLLER-STATE-"+device_id, ACTION))
    row=cursor.fetchone()
    return row[0] if row else None


def reconcile_controller_availability(device_id, observation, *, now=None, database_url=None, connect=None):
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    from modules.telemetry.rootline_irrigation_execution_store import _insert_managed_event
    now = now or datetime.now(timezone.utc)
    # Validate identity and evidence before opening a connection.
    project_availability(device_id, observation, now=now)
    connect = connect or connect_bounded_rootline_postgres
    with connect(database_url=database_url or os.environ.get("DATABASE_URL"), read_only=False, read_committed=True) as connection:
        with connection.cursor() as cursor:
            lock = int.from_bytes(sha256((CONTRACT+device_id).encode()).digest()[:8], "big", signed=True)
            cursor.execute("select pg_advisory_xact_lock(%s)", (lock,))
            result = project_availability(device_id, observation, _latest(cursor,device_id), now=now)
            if not result["changed"]:
                return result
            body={k:v for k,v in result.items() if k != "changed"}
            body["execution_id"]="ROOTLINE-CONTROLLER-STATE-"+device_id
            saved=_insert_managed_event(cursor,ACTION,body)
            if not saved.get("success"):
                raise ValueError("controller_availability_persistence_unproven")
            return {**result,"event_id":saved["event_id"]}


def read_controller_availability(*, now=None, database_url=None, connect=None):
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    now=moment(now or datetime.now(timezone.utc))
    if now is None: raise ValueError("aware_clock_required")
    result={};connect=connect or connect_bounded_rootline_postgres
    with connect(database_url=database_url or os.environ.get("DATABASE_URL")) as connection:
        with connection.cursor() as cursor:
            for device_id in CONTROLLERS:
                row=_latest(cursor,device_id)
                if not row:continue
                if row.get("contract")!=CONTRACT or row.get("device_id")!=device_id:
                    raise ValueError("controller_availability_history_invalid")
                checked=moment(row.get("checked_at"));since=moment(row.get("offline_since"))
                if checked is None or checked>now:raise ValueError("controller_availability_clock_invalid")
                state=row.get("state") if (now-checked).total_seconds()<=300 else "unknown"
                result[device_id]={**row,"state":state,"stale":state!=row.get("state"),
                    "offline_elapsed_seconds":max(0,int((now-since).total_seconds())) if since and not row.get("recovered_at") else None}
    return result


def notify_controller_availability(*, notify, store, now=None, database_url=None, connect=None):
    """One stable family-delivery identity per episode edge; never replay ambiguity."""
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    from modules.telemetry.rootline_cycle_budget import remaining_seconds
    rows=read_controller_availability(now=now,database_url=database_url,connect=connect)
    connect=connect or connect_bounded_rootline_postgres
    result={"success":True,"telegram_sends":0,"status":"controller_availability_notifications_observed"}
    for row in rows.values():
        if not row.get("incident_id"):continue
        state="ControllerRecovered" if row.get("recovered_at") else "ControllerOffline"
        # A stale/unknown first observation is never a new offline assertion.
        identity=row["incident_id"]+":"+state
        with connect(database_url=database_url or os.environ.get("DATABASE_URL")) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"""select review_json->'rootline_execution' from {TABLE}
                    where event_source='rootline_irrigation_execution' and chatwoot_conversation_id=%s
                      and review_json->'rootline_execution'->>'action'='record_notification_delivery'
                    order by created_at desc,review_event_id desc limit 1""",(identity,))
                found=cursor.fetchone();prior=found[0] if found else {}
        if prior.get("delivery_confirmed") or prior.get("delivery_ambiguous"):continue
        remaining_seconds(minimum=5)
        payload={**row,"execution_id":identity,"notification_identity":identity,"notification_state":state,
            "controller_label":CONTROLLERS[row["device_id"]]}
        delivery=notify(state,payload,retry_proof_identity=prior.get("event_id","") if prior.get("delivery_definitely_not_sent") else "")
        if delivery.get("status")=="family_message_cycle_deadline_deferred":
            return {**result,"success":False,"status":"controller_availability_notifications_deferred"}
        confirmed=delivery.get("provider_delivery_confirmed") is True and bool(delivery.get("provider_message_id"))
        unsent=delivery.get("delivery_definitely_not_sent") is True
        saved=store("record_notification_delivery",{**payload,"delivery_confirmed":confirmed,
            "delivery_ambiguous":not confirmed and not unsent,"delivery_definitely_not_sent":unsent,
            "provider_message_id":str(delivery.get("provider_message_id") or "")})
        result["telegram_sends"]+=int(delivery.get("telegram_sends") or 0)
        if not saved.get("success") or not confirmed:result["success"]=False
    return result
