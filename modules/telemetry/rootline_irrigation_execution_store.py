"""Durable ROOTLINE coordinator state on the existing append-only audit rail."""
from __future__ import annotations

import hashlib
import json
import os

EVENT_SOURCE = "rootline_irrigation_execution"


class RootlineExecutionStoreUnavailable(RuntimeError):
    """Durable execution truth could not be loaded within its read deadline."""

    def __init__(self, action):
        super().__init__("rootline_execution_store_unavailable:" + str(action))
        self.action = str(action)


def rootline_irrigation_execution_store(action, payload):
    if action in {"load_active", "load_off_attempts", "load_zone_containment",
                  "load_active_auxiliary", "load_auxiliary_off_attempts",
                  "load_auxiliary_containment", "load_auxiliary_history",
                  "load_auxiliary_physical_outcome", "load_job_events",
                  "load_active_borehole", "load_borehole_off_attempts"}:
        return _load(action, payload)
    body = dict(payload or {})
    if action == "dispatch_auxiliary_on_edge":
        return _dispatch_auxiliary_on_edge(body)
    execution_id = str(body.get("execution_id") or "").strip()
    if not execution_id:
        return {"success": False, "created": False}
    if action == "claim_before_on":
        return _bounded_claim(action, _claim_irrigation_output, body)
    if action == "claim_auxiliary_before_on":
        return _bounded_claim(action, _claim_single_auxiliary, body)
    if action == "claim_borehole_before_on":
        return _bounded_claim(action, _claim_borehole_material_load, body)
    history_created = None
    if action == "record_completed":
        history_created = _append_history(action, body)
        if history_created is not True:
            return {"success": False, "created": False,
                    "status": "canonical_history_completion_unproven"}
    event_id = _event_id(action, body)
    from modules.sales.sam_live_stock_launch_control import (
        build_sam_live_stock_review_event, record_sam_live_stock_review_event,
    )
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    event = build_sam_live_stock_review_event(
        {"conversation_id": execution_id}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": action},
        event_source=EVENT_SOURCE)
    event.update({"review_event_id": event_id,
        "chatwoot_conversation_id": execution_id,
        "review_json": {"rootline_execution": _stored_event_body(action, body, event_id)},
        "decision_json": {}, "facts_json": {},
        "customer_message_excerpt": "", "sam_reply_excerpt": ""})
    def connect_for_event():
        connection=connect_bounded_rootline_postgres(
            database_url=os.environ.get("DATABASE_URL"),read_only=False)
        if action in {"mark_active","mark_stopping","record_completed","contain_zone",
                "record_ambiguous_shutdown","record_claim_recovery"}:
            # Serialize parent state transitions with an injection claim's final
            # active-parent check. Lock order is identical everywhere.
            connection.execute("select pg_advisory_xact_lock(%s)",(1874320911,))
            connection.execute("select pg_advisory_xact_lock(%s)",(1874320912,))
        return connection
    result, status = record_sam_live_stock_review_event(event,
        connect_factory=connect_for_event)
    if status >= 500 and str(result.get("error_type") or "") in {
            "OperationalError", "ConnectionTimeout", "PoolTimeout",
            "QueryCanceled", "QueryCanceledError", "LockNotAvailable"}:
        raise RootlineExecutionStoreUnavailable(action)
    success = status < 400 and result.get("success") is True
    if history_created is None:
        history_created = _append_history(action, body) if success else False
    return {**result, "success": success,
            "created": result.get("created", status < 300),
            "history_event_created": history_created}


def _stored_event_body(action, body, event_id):
    """Canonical action is store-owned and cannot be shadowed by loaded state."""
    return {**dict(body or {}), "action": action, "event_id": event_id}


def _event_id(action, body):
    execution = str(body.get("execution_id") or "")
    if action in {"claim_before_on", "claim_auxiliary_before_on", "claim_borehole_before_on"}:
        material = f"{execution}:CLAIM"
    elif action == "claim_notification":
        material = f"{execution}:NOTIFY:{body.get('notification_state')}"
    elif (action == "record_job_resolution"
            and body.get("contract_version") == "rootline_parent_job_terminal_resolution.v1"
            and body.get("resolution") == "Cancelled"):
        material = f"{body.get('job_id')}:{body.get('job_sha256')}:CANCELLED"
    elif (action == "record_job_resolution" and body.get("resolution") == "Deferred"
            and body.get("terminal") is True):
        material = f"{body.get('job_id')}:{body.get('job_sha256')}:DEFERRED"
    elif action in {"claim_off_attempt", "claim_auxiliary_off_attempt",
                    "claim_borehole_off_attempt"}:
        material = f"{execution}:OFF:{int(body.get('attempt') or 0)}"
    else:
        material = json.dumps({"action": action, "body": body}, sort_keys=True,
                              separators=(",", ":"), default=str)
    return "ROOTLINE-EXEC-" + hashlib.sha256(material.encode()).hexdigest()[:32].upper()


def _load(action, payload):
    from modules.oom_sakkie.bounded_postgres_read import (
        connect_bounded_rootline_postgres, is_database_unavailable,
    )
    try:
      with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL")) as connection:
        with connection.cursor() as cursor:
            if action in {"load_active", "load_active_auxiliary", "load_active_borehole"}:
                borehole=action=="load_active_borehole"; auxiliary=action=="load_active_auxiliary"
                claim_action=("claim_borehole_before_on" if borehole else
                    "claim_auxiliary_before_on" if auxiliary else "claim_before_on")
                active_action=("mark_borehole_active" if borehole else
                    "mark_auxiliary_active" if auxiliary else "mark_active")
                terminal_actions=({"record_borehole_completed","contain_borehole"}
                    if borehole else {"record_auxiliary_completed",
                    "record_auxiliary_control_pulse_stopped","contain_auxiliary_device"}
                    if auxiliary else {"record_completed","contain_zone",
                        "record_ambiguous_shutdown","record_claim_recovery"})
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s order by created_at desc""", (EVENT_SOURCE,))
                terminal = set(); candidates = {}
                for row in cursor.fetchall():
                    item = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                    identity = str(item.get("execution_id") or "")
                    if item.get("action") in terminal_actions:
                        if _terminal_closes_active(item, auxiliary=auxiliary, borehole=borehole):
                            terminal.add(identity)
                    elif not auxiliary and item.get("action") == "mark_stopping":
                        candidates.setdefault(identity,item)
                    elif _is_active_candidate(item, active_action, claim_action):
                        candidates.setdefault(identity, item)
                for identity, item in candidates.items():
                    if identity not in terminal:
                        if item.get("action") == claim_action:
                            item = {**item, "state": "claimed_recovery_required"}
                        return item
                return None
            if action == "load_job_events":
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_execution'->>'job_id'=%s
                      and review_json->'rootline_execution'->>'action'
                          in ('claim_before_on','mark_active','record_completed','record_job_resolution')
                    order by created_at,review_event_id""", (EVENT_SOURCE, str(payload or "")))
                return [row[0] if isinstance(row[0],dict) else json.loads(row[0])
                        for row in cursor.fetchall()]
            if action in {"load_off_attempts","load_auxiliary_off_attempts","load_borehole_off_attempts"}:
                outcome_action=("record_borehole_off_outcome" if action=="load_borehole_off_attempts"
                    else "record_auxiliary_off_outcome" if action=="load_auxiliary_off_attempts"
                    else "record_off_outcome")
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_execution'->>'execution_id'=%s
                      and review_json->'rootline_execution'->>'action'=%s
                    order by created_at""", (EVENT_SOURCE, str(payload or ""),outcome_action))
                return [row[0] if isinstance(row[0], dict) else json.loads(row[0])
                        for row in cursor.fetchall()]
            if action == "load_auxiliary_containment":
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_execution'->>'auxiliary_device_id'=%s
                      and review_json->'rootline_execution'->>'action'='contain_auxiliary_device'
                    order by created_at desc limit 1""", (EVENT_SOURCE,str(payload or "")))
                row=cursor.fetchone()
                return {"contained":True,"evidence":row[0]} if row else {"contained":False}
            if action == "load_auxiliary_history":
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_execution'->>'action'=
                          'record_auxiliary_completed'
                      and review_json->'rootline_execution'->>'auxiliary_device_id'=%s
                    order by created_at""", (EVENT_SOURCE, str(payload or "")))
                return [row[0] if isinstance(row[0], dict) else json.loads(row[0])
                        for row in cursor.fetchall()]
            if action == "load_auxiliary_physical_outcome":
                cursor.execute("""select review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s
                      and review_json->'rootline_execution'->>'execution_id'=%s
                      and review_json->'rootline_execution'->>'action'=
                          'record_auxiliary_physical_outcome'
                    order by created_at desc limit 1""", (EVENT_SOURCE, str(payload or "")))
                row = cursor.fetchone()
                return row[0] if row and isinstance(row[0], dict) else json.loads(row[0]) if row else None
            cursor.execute("""select created_at,review_json->'rootline_execution'
                from public.sam_live_stock_conversation_review_events
                where event_source=%s
                  and review_json->'rootline_execution'->>'zone_id'=%s
                  and review_json->'rootline_execution'->>'action'
                      in ('contain_zone','release_zone_containment')
                order by created_at desc limit 1""", (EVENT_SOURCE, str(payload or "")))
            row = cursor.fetchone()
            if not row or row[1].get("action") == "release_zone_containment":
                return {"contained": False}
            contained_at, evidence = row
            execution_id = str(evidence.get("execution_id") or "")
            cursor.execute("""select review_json->'rootline_execution'
                from public.sam_live_stock_conversation_review_events
                where event_source=%s
                  and review_json->'rootline_execution'->>'execution_id'=%s
                  and review_json->'rootline_execution'->>'action'
                      in ('record_on_outcome','record_ambiguous_shutdown',
                          'record_completed','record_claim_recovery')
                  and created_at>%s
                order by created_at""", (EVENT_SOURCE, execution_id, contained_at))
            for detail_row in cursor.fetchall():
                detail = detail_row[0]
                if _verified_terminal_containment_resolution(evidence, detail):
                    return {"contained": False, "resolution_evidence": detail}
                if detail.get("action") == "record_on_outcome":
                    evidence["transport_status"] = (detail.get("on_outcome") or {}).get("status")
                elif detail.get("action") == "record_ambiguous_shutdown":
                    evidence["shutdown_verified"] = detail.get("shutdown_verified") is True
                    evidence["shutdown_evidence"] = detail.get("shutdown_evidence")
            return {"contained": True, "evidence": evidence}
    except Exception as exc:
      if is_database_unavailable(exc):
        raise RootlineExecutionStoreUnavailable(action) from exc
      raise


def _verified_terminal_containment_resolution(containment, terminal):
    """Accept only later canonical OFF proof for the exact contained execution."""
    if not isinstance(containment, dict) or not isinstance(terminal, dict):
        return False
    if (terminal.get("action") not in {"record_completed", "record_claim_recovery"}
            or terminal.get("execution_id") != containment.get("execution_id")
            or terminal.get("zone_id") != containment.get("zone_id")
            or terminal.get("shutdown_verified") is not True):
        return False
    shutdown = terminal.get("shutdown_evidence")
    return (isinstance(shutdown, dict)
            and shutdown.get("authoritative") is True
            and shutdown.get("state") == "OFF")


def _terminal_closes_active(item, *, auxiliary=False, borehole=False):
    action = str(item.get("action") or "") if isinstance(item, dict) else ""
    if borehole:
        # Containment records the unresolved safety incident; it cannot prove
        # that the physical pump and water flow stopped.  Only the strict,
        # execution-bound three-domain completion contract releases a borehole
        # claim.
        return _verified_borehole_completion(item)
    if auxiliary:
        return (action in {"record_auxiliary_completed",
                "record_auxiliary_control_pulse_stopped"}
            or (action == "contain_auxiliary_device"
                and item.get("shutdown_verified") is True))
    if action == "record_completed":
        return True
    if action in {"contain_zone", "record_ambiguous_shutdown", "record_claim_recovery"}:
        return item.get("shutdown_verified") is True
    return False


_EVIDENCE_ID_TRIM_CODEPOINTS = (
    9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760,
    8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202,
    8232, 8233, 8239, 8287, 12288,
)
_EVIDENCE_ID_TRIM_CHARS = "".join(chr(value) for value in _EVIDENCE_ID_TRIM_CODEPOINTS)
_EVIDENCE_ID_TRIM_SQL = "(" + "||".join(
    f"chr({value})" for value in _EVIDENCE_ID_TRIM_CODEPOINTS) + ")"


def _normalize_evidence_id(value):
    """Apply the explicit evidence-ID boundary contract shared with PostgreSQL."""
    return str(value or "").strip(_EVIDENCE_ID_TRIM_CHARS)


def _verified_borehole_completion(item):
    """Require execution-bound canonical and authoritative provider final OFF."""
    if not isinstance(item, dict) or item.get("action") != "record_borehole_completed":
        return False
    execution_id = str(item.get("execution_id") or "")
    canonical = item.get("canonical_completion_evidence") or {}
    provider = item.get("provider_final_off_evidence") or {}
    physical = item.get("physical_completion_evidence") or {}
    provider_mode = item.get("operational_proof") == "provider_app_on_to_off"
    evidence = (canonical, provider) if provider_mode else (canonical, provider, physical)
    evidence_ids = tuple(_normalize_evidence_id(row.get("evidence_id"))
        for row in evidence)
    identities_match = bool(execution_id) and all(
        str(row.get("execution_id") or "") == execution_id
        for row in evidence)
    evidence_domains_distinct = (all(evidence_ids)
        and len(set(evidence_ids)) == len(evidence_ids))
    return (item.get("shutdown_verified") is True and identities_match
        and evidence_domains_distinct
        and canonical.get("final_state") == "OFF"
        and provider.get("authoritative") is True and provider.get("state") == "OFF"
        and ((provider_mode
              and (item.get("provider_start_evidence") or {}).get("authoritative") is True
              and (item.get("provider_start_evidence") or {}).get("state") == "ON")
             or (not provider_mode and physical.get("pump_stopped") is True
                 and physical.get("water_flow_stopped") is True)))


def _is_active_candidate(item, active_action, claim_action):
    action = item.get("action") if isinstance(item, dict) else None
    return (action == claim_action
            or (action == active_action and item.get("state") == "Active"))


def _bounded_claim(action, claim, body):
    from modules.oom_sakkie.bounded_postgres_read import is_database_unavailable
    try:
        return claim(body)
    except Exception as exc:
        if is_database_unavailable(exc):
            raise RootlineExecutionStoreUnavailable(action) from exc
        raise


def _claim_irrigation_output(body):
    """Atomically serialize irrigation and consume one governed output authority."""
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    execution_id = str(body["execution_id"])
    consumption_key = str(body.get("consumption_key") or "").strip()
    zone_id = str(body.get("zone_id") or "").strip()
    operating_date = str(body.get("operating_date") or "").strip()
    eligibility_id = str(body.get("eligibility_id") or "").strip()
    eligibility_sha256 = str(body.get("eligibility_sha256") or "").strip()
    try:
        from modules.telemetry.rootline_device_registry import commissioned_irrigation_contract
        commissioned_irrigation_contract(zone_id)
    except ValueError:
        return {"success": False, "created": False,
                "status": "irrigation_output_not_commissioned"}
    if (not consumption_key or not _valid_iso_date(operating_date) or not eligibility_id
            or len(eligibility_sha256) != 64):
        return {"success": False, "created": False,
                "status": "daily_dispatch_identity_incomplete"}
    event_id = _event_id("claim_before_on", body)
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
                                           read_only=False) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(%s)", (1874320911,))
            cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
                where review_event_id=%s""", (event_id,))
            if cursor.fetchone():
                return {"success": True, "created": False, "status": "execution_replay"}
            cursor.execute("""select 1
                from public.sam_live_stock_conversation_review_events
                where event_source=%s
                  and review_json->'rootline_execution'->>'action'='claim_before_on'
                  and review_json->'rootline_execution'->>'consumption_key'=%s
                limit 1""", (EVENT_SOURCE, consumption_key))
            if cursor.fetchone():
                return {"success": True, "created": False,
                        "status": "eligibility_already_consumed"}
            blocked = _daily_dispatch_blocker(cursor, execution_id=execution_id,
                eligibility_id=eligibility_id, eligibility_sha256=eligibility_sha256,
                zone_id=zone_id, operating_date=operating_date,
                job_id=str(body.get("job_id") or ""),
                segment_number=int(body.get("segment_number") or 0))
            if blocked:
                return {"success": True, "created": False, "status": blocked}
            cursor.execute(f"""select 1
                from public.sam_live_stock_conversation_review_events claim
                where claim.event_source=%s
                  and claim.review_json->'rootline_execution'->>'action'
                      in ('claim_before_on','claim_borehole_before_on')
                  and not exists (
                    select 1 from public.sam_live_stock_conversation_review_events terminal
                    where terminal.event_source=%s
                      and terminal.review_json->'rootline_execution'->>'execution_id'=
                          claim.review_json->'rootline_execution'->>'execution_id'
                      and ((claim.review_json->'rootline_execution'->>'action'='claim_before_on'
                        and (terminal.review_json->'rootline_execution'->>'action'='record_completed'
                          or (terminal.review_json->'rootline_execution'->>'action'
                                in ('contain_zone','record_ambiguous_shutdown','record_claim_recovery')
                              and terminal.review_json->'rootline_execution'->>'shutdown_verified'='true')))
                        or (claim.review_json->'rootline_execution'->>'action'='claim_borehole_before_on'
                          and terminal.review_json->'rootline_execution'->>'action'='record_borehole_completed'
                          and terminal.review_json->'rootline_execution'->>'shutdown_verified'='true'
                          and length(btrim(coalesce(terminal.review_json->'rootline_execution'->'canonical_completion_evidence'->>'evidence_id',''),{_EVIDENCE_ID_TRIM_SQL}))>0
                          and terminal.review_json->'rootline_execution'->'canonical_completion_evidence'->>'execution_id'=
                            terminal.review_json->'rootline_execution'->>'execution_id'
                          and terminal.review_json->'rootline_execution'->'canonical_completion_evidence'->>'final_state'='OFF'
                          and length(btrim(coalesce(terminal.review_json->'rootline_execution'->'provider_final_off_evidence'->>'evidence_id',''),{_EVIDENCE_ID_TRIM_SQL}))>0
                          and terminal.review_json->'rootline_execution'->'provider_final_off_evidence'->>'execution_id'=
                            terminal.review_json->'rootline_execution'->>'execution_id'
                          and terminal.review_json->'rootline_execution'->'provider_final_off_evidence'->>'authoritative'='true'
                          and terminal.review_json->'rootline_execution'->'provider_final_off_evidence'->>'state'='OFF'
                          and length(btrim(coalesce(terminal.review_json->'rootline_execution'->'physical_completion_evidence'->>'evidence_id',''),{_EVIDENCE_ID_TRIM_SQL}))>0
                          and terminal.review_json->'rootline_execution'->'physical_completion_evidence'->>'execution_id'=
                            terminal.review_json->'rootline_execution'->>'execution_id'
                          and btrim(terminal.review_json->'rootline_execution'->'canonical_completion_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL}) <>
                            btrim(terminal.review_json->'rootline_execution'->'provider_final_off_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL})
                          and btrim(terminal.review_json->'rootline_execution'->'canonical_completion_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL}) <>
                            btrim(terminal.review_json->'rootline_execution'->'physical_completion_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL})
                          and btrim(terminal.review_json->'rootline_execution'->'provider_final_off_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL}) <>
                            btrim(terminal.review_json->'rootline_execution'->'physical_completion_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL})
                          and terminal.review_json->'rootline_execution'->'physical_completion_evidence'->>'pump_stopped'='true'
                          and terminal.review_json->'rootline_execution'->'physical_completion_evidence'->>'water_flow_stopped'='true')))
                limit 1""", (EVENT_SOURCE, EVENT_SOURCE))
            if cursor.fetchone():
                return {"success": True, "created": False, "status": "controller_active"}
            cursor.execute("""insert into public.sam_live_stock_conversation_review_events
                (review_event_id, chatwoot_conversation_id, source_agent, event_source,
                 recommended_action, review_json)
                values (%s,%s,'rootline_backend',%s,'claim_before_on',%s::jsonb)
                on conflict (review_event_id) do nothing""",
                (event_id, execution_id, EVENT_SOURCE, json.dumps({
                    "rootline_execution": {"action": "claim_before_on",
                                           "event_id": event_id, **body}},
                    sort_keys=True, separators=(",", ":"), default=str)))
            return {"success": True, "created": cursor.rowcount == 1,
                    "status": "claimed" if cursor.rowcount == 1 else "execution_replay"}


def _daily_dispatch_blocker(cursor, *, execution_id, eligibility_id,
                            eligibility_sha256, zone_id, operating_date,
                            job_id="", segment_number=0):
    """Evaluate signed authority, completion and accepted-ON under caller's lock."""
    cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
        where event_source=%s
          and review_json->'rootline_execution'->>'action'='record_eligibility'
          and review_json->'rootline_execution'->>'execution_id'=%s
          and review_json->'rootline_execution'->>'eligibility_id'=%s
          and review_json->'rootline_execution'->>'eligibility_sha256'=%s
          and review_json->'rootline_execution'->>'operating_date'=%s
          and review_json->'rootline_execution'->>'zone_id'=%s
          and (%s <= 1 or review_json->'rootline_execution'->>'predecessor_off_rearm_verified'='true')
          limit 1""",
        (EVENT_SOURCE, execution_id, eligibility_id, eligibility_sha256,
         operating_date, zone_id, segment_number))
    if not cursor.fetchone():
        return "canonical_eligibility_unproven"
    if segment_number > 1:
        if not job_id:
            return "job_identity_incomplete"
        cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
            where event_source=%s
              and review_json->'rootline_execution'->>'action'='record_completed'
              and review_json->'rootline_execution'->>'job_id'=%s
              and (review_json->'rootline_execution'->>'segment_number')::int=%s
              and review_json->'rootline_execution'->>'shutdown_verified'='true'
            limit 1""", (EVENT_SOURCE, job_id, segment_number-1))
        if not cursor.fetchone():
            return "prior_segment_off_rearm_unproven"
        cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
            where event_source=%s
              and review_json->'rootline_execution'->>'action'='claim_before_on'
              and review_json->'rootline_execution'->>'job_id'=%s
              and (review_json->'rootline_execution'->>'segment_number')::int=%s
            limit 1""", (EVENT_SOURCE, job_id, segment_number))
        return "job_segment_already_claimed" if cursor.fetchone() else None
    # Reuse the canonical typed-history verifier rather than approximating its
    # digest, evidence, cutoff, runtime and replay rules in SQL. These rows and
    # the database clock are read inside the same advisory-locked transaction.
    cursor.execute("select clock_timestamp()")
    snapshot_cutoff = cursor.fetchone()[0]
    cursor.execute("""select irrigation_event_id,event_at,event_type,zone_id,
        planned_minutes,actual_minutes,details,source_id,actor,created_at
        from public.irrigation_events
        where zone_id=%s or event_type='PLANNING_EPOCH_STARTED'
        order by event_at,irrigation_event_id""", (zone_id,))
    from modules.telemetry.rootline_irrigation_history import project_canonical_irrigation_history
    history = project_canonical_irrigation_history(
        cursor.fetchall(), snapshot_cutoff=snapshot_cutoff)
    completed_days = history["zones"][zone_id]["verified_completed_days"]
    if operating_date in completed_days:
        return "zone_daily_completion_already_credited"
    cursor.execute("""select 1
        from public.sam_live_stock_conversation_review_events claim
        where claim.event_source=%s
          and claim.review_json->'rootline_execution'->>'action'='claim_before_on'
          and claim.review_json->'rootline_execution'->>'zone_id'=%s
          and claim.review_json->'rootline_execution'->>'operating_date'=%s
          and exists (select 1
            from public.sam_live_stock_conversation_review_events outcome
            where outcome.event_source=%s
              and outcome.review_json->'rootline_execution'->>'action'='record_on_outcome'
              and outcome.review_json->'rootline_execution'->>'execution_id'=
                  claim.review_json->'rootline_execution'->>'execution_id'
              and outcome.review_json->'rootline_execution'->'on_outcome'->>
                  'accepted_unambiguous'='true') limit 1""",
        (EVENT_SOURCE, zone_id, operating_date, EVENT_SOURCE))
    if cursor.fetchone():
        return "zone_daily_on_already_accepted"
    return None


def _valid_iso_date(value):
    from datetime import date
    try:
        return date.fromisoformat(str(value)).isoformat() == str(value)
    except (TypeError, ValueError):
        return False


def _claim_single_auxiliary(body):
    """Atomically consume one auxiliary artifact without blocking its B/C zone."""
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    execution_id=str(body["execution_id"]);consumption_key=str(body.get("consumption_key") or "")
    auxiliary_id=str(body.get("auxiliary_device_id") or "")
    if not consumption_key or not auxiliary_id:
        return {"success":False,"created":False,"status":"auxiliary_claim_incomplete"}
    event_id=_event_id("claim_auxiliary_before_on",body)
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
                                           read_only=False) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(%s)",(1874320911,))
            cursor.execute("select pg_advisory_xact_lock(%s)",(1874320912,))
            if body.get("device_type") == "fertilizer_injection_valve":
                job_id=str(body.get("job_id") or "");job_sha=str(body.get("job_sha256") or "")
                segment=str(body.get("segment_identity") or "");zone=str(body.get("zone_id") or "")
                zone_execution=str(body.get("zone_execution_id") or "")
                if (not job_id.startswith("ROOTLINE-IRRIGATION-JOB-") or len(job_sha)!=64
                        or not segment.startswith("ROOTLINE-JOB-SEGMENT-") or not zone
                        or not zone_execution):
                    return {"success":False,"created":False,
                        "status":"irrigation_job_binding_incomplete"}
                cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events claim
                    where claim.event_source=%s
                      and claim.review_json->'rootline_execution'->>'action'='claim_before_on'
                      and claim.review_json->'rootline_execution'->>'job_id'=%s
                      and claim.review_json->'rootline_execution'->>'job_sha256'=%s
                      and claim.review_json->'rootline_execution'->>'segment_identity'=%s
                      and claim.review_json->'rootline_execution'->>'zone_id'=%s
                      and claim.review_json->'rootline_execution'->>'execution_id'=%s
                      and exists (select 1 from public.sam_live_stock_conversation_review_events active
                        where active.event_source=%s
                          and active.review_json->'rootline_execution'->>'action'='mark_active'
                          and active.review_json->'rootline_execution'->>'execution_id'=
                              claim.review_json->'rootline_execution'->>'execution_id')
                      and not exists (select 1 from public.sam_live_stock_conversation_review_events terminal
                        where terminal.event_source=%s
                          and terminal.review_json->'rootline_execution'->>'execution_id'=
                              claim.review_json->'rootline_execution'->>'execution_id'
                          and terminal.review_json->'rootline_execution'->>'action'
                              in ('record_completed','contain_zone','record_ambiguous_shutdown',
                                  'record_claim_recovery'))
                      and not exists (select 1 from public.sam_live_stock_conversation_review_events stopping
                        where stopping.event_source=%s
                          and stopping.review_json->'rootline_execution'->>'execution_id'=
                              claim.review_json->'rootline_execution'->>'execution_id'
                          and stopping.review_json->'rootline_execution'->>'action'='mark_stopping')
                    limit 1""",(EVENT_SOURCE,job_id,job_sha,segment,zone,zone_execution,
                        EVENT_SOURCE,EVENT_SOURCE,EVENT_SOURCE))
                if not cursor.fetchone():
                    return {"success":True,"created":False,
                        "status":"eligible_irrigation_segment_not_active"}
            cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
                where event_source=%s and (review_event_id=%s or
                  (review_json->'rootline_execution'->>'action'='claim_auxiliary_before_on'
                   and review_json->'rootline_execution'->>'consumption_key'=%s)) limit 1""",
                (EVENT_SOURCE,event_id,consumption_key))
            if cursor.fetchone():
                return {"success":True,"created":False,"status":"eligibility_already_consumed"}
            cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events claim
                where claim.event_source=%s
                  and claim.review_json->'rootline_execution'->>'action'='claim_auxiliary_before_on'
                  and not exists (select 1 from public.sam_live_stock_conversation_review_events terminal
                    where terminal.event_source=%s
                      and terminal.review_json->'rootline_execution'->>'execution_id'=
                          claim.review_json->'rootline_execution'->>'execution_id'
                      and (terminal.review_json->'rootline_execution'->>'action'
                          in ('record_auxiliary_completed','record_auxiliary_control_pulse_stopped')
                        or (terminal.review_json->'rootline_execution'->>'action'=
                              'contain_auxiliary_device'
                            and terminal.review_json->'rootline_execution'->>
                              'shutdown_verified'='true'))) limit 1""",
                (EVENT_SOURCE,EVENT_SOURCE))
            if cursor.fetchone():
                return {"success":True,"created":False,"status":"auxiliary_active"}
            cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events
                where event_source=%s
                  and review_json->'rootline_execution'->>'auxiliary_device_id'=%s
                  and review_json->'rootline_execution'->>'action'='contain_auxiliary_device' limit 1""",
                (EVENT_SOURCE,auxiliary_id))
            if cursor.fetchone():
                return {"success":True,"created":False,"status":"auxiliary_contained"}
            cursor.execute("""insert into public.sam_live_stock_conversation_review_events
                (review_event_id,chatwoot_conversation_id,source_agent,event_source,
                 recommended_action,review_json)
                values (%s,%s,'rootline_backend',%s,'claim_auxiliary_before_on',%s::jsonb)
                on conflict (review_event_id) do nothing""",(event_id,execution_id,EVENT_SOURCE,
                json.dumps({"rootline_execution":{"action":"claim_auxiliary_before_on",
                    "event_id":event_id,**body}},sort_keys=True,separators=(",",":"),default=str)))
            return {"success":True,"created":cursor.rowcount==1,
                "status":"claimed" if cursor.rowcount==1 else "execution_replay"}


def _claim_borehole_material_load(body):
    """Reserve the existing ROOTLINE material-load rail; this issues no command."""
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    execution_id=str(body.get("execution_id") or "")
    digest=str(body.get("eligibility_sha256") or "")
    key=str(body.get("consumption_key") or "")
    if (not execution_id or len(digest)!=64 or key != "borehole:"+digest
            or body.get("device_key") != "ewelink:ewelink_owner_account:1002851416:1"):
        return {"success":False,"created":False,"status":"borehole_claim_incomplete"}
    event_id=_event_id("claim_borehole_before_on",body)
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
                                           read_only=False) as connection:
      with connection.cursor() as cursor:
        # Same lock as irrigation: borehole pumping and irrigation are exclusive
        # material loads unless a future commissioned policy explicitly changes it.
        cursor.execute("select pg_advisory_xact_lock(%s)",(1874320911,))
        cursor.execute("""select review_json->'rootline_execution'
          from public.sam_live_stock_conversation_review_events
          where event_source=%s and review_json->'rootline_execution'->>'action'='record_borehole_eligibility'
          and review_json->'rootline_execution'->>'execution_id'=%s
          and review_json->'rootline_execution'->>'eligibility_sha256'=%s
          order by created_at desc limit 1""",
          (EVENT_SOURCE,execution_id,digest))
        row=cursor.fetchone()
        canonical=row[0] if row and isinstance(row[0],dict) else None
        immutable=("execution_id","eligibility_sha256","consumption_key","device_key",
          "baseline_sha256","registry_generation","need_sha256","evidence_sha256",
          "requested_seconds","assessed_at","gates","blockers")
        if (not _valid_borehole_eligibility(canonical)
                or any(body.get(field)!=canonical.get(field) for field in immutable)):
            return {"success":True,"created":False,"status":"canonical_borehole_eligibility_unproven"}
        cursor.execute(f"""select 1 from public.sam_live_stock_conversation_review_events c
          where c.event_source=%s and c.review_json->'rootline_execution'->>'action'
            in ('claim_before_on','claim_auxiliary_before_on','claim_borehole_before_on') and not exists(
              select 1 from public.sam_live_stock_conversation_review_events t
              where t.event_source=%s and t.review_json->'rootline_execution'->>'execution_id'=
                c.review_json->'rootline_execution'->>'execution_id' and
                ((c.review_json->'rootline_execution'->>'action'='claim_before_on' and
                  (t.review_json->'rootline_execution'->>'action'='record_completed' or
                   (t.review_json->'rootline_execution'->>'action'='contain_zone' and
                    t.review_json->'rootline_execution'->>'shutdown_verified'='true'))) or
                 (c.review_json->'rootline_execution'->>'action'='claim_auxiliary_before_on' and
                  (t.review_json->'rootline_execution'->>'action' in
                    ('record_auxiliary_completed','record_auxiliary_control_pulse_stopped') or
                   (t.review_json->'rootline_execution'->>'action'='contain_auxiliary_device' and
                    t.review_json->'rootline_execution'->>'shutdown_verified'='true'))) or
                 (c.review_json->'rootline_execution'->>'action'='claim_borehole_before_on' and
                  t.review_json->'rootline_execution'->>'action'='record_borehole_completed' and
                  t.review_json->'rootline_execution'->>'shutdown_verified'='true' and
                  length(btrim(coalesce(t.review_json->'rootline_execution'->'canonical_completion_evidence'->>'evidence_id',''),{_EVIDENCE_ID_TRIM_SQL}))>0 and
                  t.review_json->'rootline_execution'->'canonical_completion_evidence'->>'execution_id'=
                    t.review_json->'rootline_execution'->>'execution_id' and
                  t.review_json->'rootline_execution'->'canonical_completion_evidence'->>'final_state'='OFF' and
                  length(btrim(coalesce(t.review_json->'rootline_execution'->'provider_final_off_evidence'->>'evidence_id',''),{_EVIDENCE_ID_TRIM_SQL}))>0 and
                  t.review_json->'rootline_execution'->'provider_final_off_evidence'->>'execution_id'=
                    t.review_json->'rootline_execution'->>'execution_id' and
                  t.review_json->'rootline_execution'->'provider_final_off_evidence'->>'authoritative'='true' and
                  t.review_json->'rootline_execution'->'provider_final_off_evidence'->>'state'='OFF' and
                  btrim(t.review_json->'rootline_execution'->'canonical_completion_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL}) <>
                    btrim(t.review_json->'rootline_execution'->'provider_final_off_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL}) and
                  ((t.review_json->'rootline_execution'->>'operational_proof'='provider_app_on_to_off' and
                    t.review_json->'rootline_execution'->'provider_start_evidence'->>'authoritative'='true' and
                    t.review_json->'rootline_execution'->'provider_start_evidence'->>'state'='ON') or
                   (length(btrim(coalesce(t.review_json->'rootline_execution'->'physical_completion_evidence'->>'evidence_id',''),{_EVIDENCE_ID_TRIM_SQL}))>0 and
                    t.review_json->'rootline_execution'->'physical_completion_evidence'->>'execution_id'=
                      t.review_json->'rootline_execution'->>'execution_id' and
                    btrim(t.review_json->'rootline_execution'->'canonical_completion_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL}) <>
                      btrim(t.review_json->'rootline_execution'->'physical_completion_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL}) and
                    btrim(t.review_json->'rootline_execution'->'provider_final_off_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL}) <>
                      btrim(t.review_json->'rootline_execution'->'physical_completion_evidence'->>'evidence_id',{_EVIDENCE_ID_TRIM_SQL}) and
                    t.review_json->'rootline_execution'->'physical_completion_evidence'->>'pump_stopped'='true' and
                    t.review_json->'rootline_execution'->'physical_completion_evidence'->>'water_flow_stopped'='true'))))) limit 1""",
          (EVENT_SOURCE,EVENT_SOURCE))
        if cursor.fetchone():
            return {"success":True,"created":False,"status":"material_load_active"}
        cursor.execute("""insert into public.sam_live_stock_conversation_review_events
          (review_event_id,chatwoot_conversation_id,source_agent,event_source,recommended_action,review_json)
          values (%s,%s,'rootline_backend',%s,'claim_borehole_before_on',%s::jsonb)
          on conflict(review_event_id) do nothing""",(event_id,execution_id,EVENT_SOURCE,
          json.dumps({"rootline_execution":{"action":"claim_borehole_before_on",
            "event_id":event_id,**body}},sort_keys=True,separators=(",",":"),default=str)))
        return {"success":True,"created":cursor.rowcount==1,
          "status":"claimed" if cursor.rowcount==1 else "execution_replay"}


def _valid_borehole_eligibility(value):
    if not isinstance(value,dict) or value.get("eligible") is not True:
        return False
    material={key:value.get(key) for key in ("contract_version","device_key",
      "baseline_sha256","registry_generation","need_sha256","evidence_sha256",
      "requested_seconds","assessed_at","gates","blockers")}
    digest=hashlib.sha256(json.dumps(material,sort_keys=True,separators=(",",":"),
      default=str).encode()).hexdigest()
    required_gates={"canonical_need","commissioned_baseline","standing_authority",
      "provider_off","dry_run","low_water","supply_pressure","full_tank",
      "energy","concurrency","bounded_runtime"}
    return (material["contract_version"]=="rootline_borehole_runtime_eligibility.v1"
      and material["device_key"]=="ewelink:ewelink_owner_account:1002851416:1"
      and value.get("eligibility_sha256")==digest
      and value.get("execution_id")=="ROOTLINE-BOREHOLE-"+digest[:24].upper()
      and value.get("consumption_key")=="borehole:"+digest
      and value.get("command_authority") is False
      and isinstance(material["gates"],dict) and set(material["gates"])==required_gates
      and all(passed is True for passed in material["gates"].values())
      and material["blockers"]==[])


def _dispatch_auxiliary_on_edge(body):
    """Hold parent and auxiliary locks through the injection provider ON edge."""
    dispatch=body.pop("dispatch",None)
    if not callable(dispatch) or body.get("device_type")!="fertilizer_injection_valve":
        return {"accepted_unambiguous":False,"status":"atomic_on_edge_invalid"}
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
                                           read_only=False) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select pg_advisory_xact_lock(%s)",(1874320911,))
            cursor.execute("select pg_advisory_xact_lock(%s)",(1874320912,))
            cursor.execute("""select 1 from public.sam_live_stock_conversation_review_events claim
                where claim.event_source=%s
                  and claim.review_json->'rootline_execution'->>'action'='claim_before_on'
                  and claim.review_json->'rootline_execution'->>'execution_id'=%s
                  and claim.review_json->'rootline_execution'->>'job_id'=%s
                  and claim.review_json->'rootline_execution'->>'job_sha256'=%s
                  and claim.review_json->'rootline_execution'->>'segment_identity'=%s
                  and claim.review_json->'rootline_execution'->>'zone_id'=%s
                  and not exists (select 1 from public.sam_live_stock_conversation_review_events stop
                    where stop.event_source=%s
                      and stop.review_json->'rootline_execution'->>'execution_id'=%s
                      and stop.review_json->'rootline_execution'->>'action' in
                        ('mark_stopping','record_completed','contain_zone',
                         'record_ambiguous_shutdown','record_claim_recovery')) limit 1""",
                (EVENT_SOURCE,body.get("zone_execution_id"),body.get("job_id"),
                 body.get("job_sha256"),body.get("segment_identity"),body.get("zone_id"),
                 EVENT_SOURCE,body.get("zone_execution_id")))
            if not cursor.fetchone():
                return {"accepted_unambiguous":False,
                    "status":"parent_edge_authority_revoked"}
            return dispatch()


def _append_history(action, body):
    event_type = {"mark_active": "STARTED", "contain_zone": "AMBIGUOUS",
                  "record_completed": ("COMPLETED" if body.get("objective_satisfied") is True
                                       else "PARTIAL")}.get(action)
    if not event_type:
        return False
    from datetime import datetime, timezone
    from modules.telemetry.rootline_irrigation_history import build_typed_history_event
    event_at = _time(body.get("completed_at") or body.get("claimed_at")) or datetime.now(timezone.utc)
    actual = _verified_runtime(body)
    details = {"execution_id": body.get("execution_id"),
        "operating_date": body.get("operating_date"),
        "start_evidence_id": (body.get("start_evidence") or {}).get("evidence_id") or "Unavailable",
        "maximum_runtime_minutes": body.get("planned_runtime_minutes"),
        "verified_runtime_minutes": actual,
        "shutdown_evidence_id": (body.get("shutdown_evidence") or {}).get("evidence_id") or "Unavailable",
        "shutdown_verified": body.get("shutdown_verified") is True,
        "objective_satisfied": body.get("objective_satisfied") is True,
        "evidence_cutoff": body.get("completed_at") or body.get("claimed_at"),
        "shutdown_observed_at": body.get("completed_at"),
        "provenance": "rootline_execution_coordinator",
        "classification": event_type.lower()}
    event_id = "ROOTLINE-HISTORY-" + hashlib.sha256(
        f"{body.get('execution_id')}:{event_type}".encode()).hexdigest()[:24].upper()
    event = build_typed_history_event(event_id=event_id,event_at=event_at,event_type=event_type,
        zone_id=str(body.get("zone_id") or ""),details=details,
        planned_minutes=body.get("planned_runtime_minutes"),actual_minutes=actual)
    try:
        from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
        with connect_bounded_rootline_postgres(
                database_url=os.environ.get("DATABASE_URL"), read_only=False) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select public.rootline_append_typed_irrigation_event(
                    %s::text,%s::timestamptz,%s::text,%s::text,
                    %s::numeric,%s::numeric,%s::jsonb)""",
                    (event["irrigation_event_id"],event["event_at"],event["event_type"],event["zone_id"],
                     event["planned_minutes"],event["actual_minutes"],json.dumps(event["details"],
                     sort_keys=True,separators=(",",":"),default=str)))
                row=cursor.fetchone()
                if row and row[0]:
                    return True
                cursor.execute("""select event_at,event_type,zone_id,planned_minutes,
                    actual_minutes,details from public.irrigation_events
                    where irrigation_event_id=%s""", (event["irrigation_event_id"],))
                existing = cursor.fetchone()
                if not existing:
                    return False
                existing_details = (existing[5] if isinstance(existing[5], dict)
                                    else json.loads(existing[5]))
                return (existing[0].isoformat() == event["event_at"]
                        and existing[1] == event["event_type"]
                        and existing[2] == event["zone_id"]
                        and _numeric_equal(existing[3], event["planned_minutes"])
                        and _numeric_equal(existing[4], event["actual_minutes"])
                        and existing_details == event["details"])
    except Exception:
        return False


def _time(value):
    try: return __import__("datetime").datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except (TypeError,ValueError): return None


def _numeric_equal(left, right):
    if left is None or right is None:
        return left is None and right is None
    try:
        from decimal import Decimal, ROUND_HALF_UP
        scale = Decimal("0.01")
        return (Decimal(str(left)).quantize(scale, rounding=ROUND_HALF_UP)
                == Decimal(str(right)).quantize(scale, rounding=ROUND_HALF_UP))
    except (TypeError, ValueError):
        return False


def _verified_runtime(body):
    evidence = body.get("objective_evidence")
    if not isinstance(evidence, dict):
        return None
    value = evidence.get("verified_runtime_minutes")
    try:
        runtime = float(value)
        maximum = float(body.get("planned_runtime_minutes") or 0)
    except (TypeError, ValueError):
        return None
    return runtime if 0 <= runtime <= maximum else None
