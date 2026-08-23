"""Governed exact-preview recording for natural HERDMASTER observations.

Only the existing append-only factual pig-observation rail is writable here.
Lifecycle, medical treatment, mating, litter, movement and availability effects
remain blocked until their canonical services are explicitly coordinated.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Mapping


def confirm_health_loss_preview(lifecycle: Mapping[str, Any], confirmation_text: str,
                                *, actor_id: str, evidence_loader, connect_factory=None):
    preview = lifecycle.get("preview") if isinstance(lifecycle.get("preview"), Mapping) else {}
    binding = preview.get("confirmation_binding") if isinstance(preview.get("confirmation_binding"), Mapping) else {}
    operation_id = str(binding.get("operation_id") or "")
    expected = "CONFIRM " + operation_id
    if not operation_id or str(confirmation_text or "").strip() != expected:
        return _result(False, "exact_preview_confirmation_required"), 409
    if binding.get("confirmation_ready") is not True or preview.get("confirmation_ready") is not True:
        return _result(False, "preview_not_confirmation_ready"), 409
    bound_owner = str(binding.get("authenticated_principal_id") or "").strip()
    lifecycle_owner = str(lifecycle.get("owner_user_id") or "").strip()
    actor_id = str(actor_id or "").strip()
    if not bound_owner or not lifecycle_owner or actor_id != bound_owner or actor_id != lifecycle_owner:
        return _result(False, "authenticated_owner_confirmation_required"), 403
    prior = lifecycle.get("recording_result") if isinstance(lifecycle.get("recording_result"), Mapping) else {}
    if prior.get("success") is True and str(prior.get("operation_id") or "") == operation_id:
        return _result(True, "health_loss_replayed_withheld", rows_created=0,
                       operation_id=operation_id), 200
    evaluator = preview.get("evaluator") if isinstance(preview.get("evaluator"), Mapping) else {}
    supported = [row for row in evaluator.get("canonical_effects") or [] if row.get("supported")]
    supported_areas = {str(row.get("area") or "") for row in supported}
    if "lifecycle" in supported_areas:
        allowed = {"lifecycle", "availability", "movement_pen", "downstream_work"}
        if not supported_areas or not supported_areas.issubset(allowed):
            return _result(False, "canonical_effect_coordinator_unavailable",
                           blocked_areas=sorted(supported_areas - allowed)), 409
        return _confirm_mortality_lifecycle(
            lifecycle, evaluator, binding, operation_id, actor_id,
            evidence_loader=evidence_loader, connect_factory=connect_factory)
    current = evidence_loader()
    if str(current.get("evidence_generation") or "") != str(binding.get("evidence_generation") or ""):
        return _result(False, "canonical_evidence_changed_repreview_required"), 409
    if len(supported) != 1 or supported[0].get("area") != "medical_observation":
        return _result(False, "canonical_effect_coordinator_unavailable",
                       blocked_areas=sorted({str(row.get("area")) for row in supported
                                             if row.get("area") != "medical_observation"})), 409
    identity = evaluator.get("identity") if isinstance(evaluator.get("identity"), Mapping) else {}
    pig_id = str(identity.get("pig_id") or "")
    facts = dict(supported[0].get("facts") or {})
    canonical = {"operation_id": operation_id, "pig_id": pig_id,
        "provider_message_id": str(binding.get("provider_message_id") or ""),
        "preview_sha256": str(binding.get("preview_sha256") or ""),
        "evidence_generation": str(binding.get("evidence_generation") or ""),
        "facts": facts, "actor_id": str(actor_id or "")}
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    event_id = "OBS-HL-" + hashlib.sha256(operation_id.encode()).hexdigest()[:24].upper()
    note = _factual_note(facts)
    severity = "urgent" if str((evaluator.get("immediate_welfare_priority") or {}).get("level") or "") in {"emergency", "urgent_follow_up"} else "attention"
    try:
        connection_cm = connect_factory() if connect_factory else _connect()
        with connection_cm as connection:
            with connection.cursor() as cursor:
                cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",
                               ("herdmaster-health-loss:" + operation_id,))
                cursor.execute("""select observation_event_id,source_reference
                    from public.pig_observation_events where idempotency_key=%s""", (operation_id,))
                existing = cursor.fetchone()
                if existing:
                    if str(existing[1]) != digest:
                        return _result(False, "health_loss_idempotency_conflict"), 409
                    return _result(True, "health_loss_replayed_withheld",
                                   observation_event_id=str(existing[0]), rows_created=0), 200
                cursor.execute("""select 1 from public.pigs
                    where pig_id=%s and status='Active' and on_farm is true for share""", (pig_id,))
                if not cursor.fetchone():
                    return _result(False, "current_active_on_farm_pig_required"), 409
                cursor.execute("""insert into public.pig_observation_events(
                    observation_event_id,pig_id,observed_at,observer_reference,
                    observation_category,severity,factual_note,measurements_json,
                    source_system,source_reference,idempotency_key)
                    values(%s,%s,%s::timestamptz,%s,'welfare',%s,%s,%s::jsonb,
                           'owner',%s,%s) returning observation_event_id""", (
                    event_id, pig_id, str(lifecycle.get("provider_timestamp") or ""),
                    str(actor_id), severity, note, json.dumps({
                        "contract_version": "herdmaster_health_loss_recording_v1",
                        "observed": facts.get("observed") or [],
                        "owner_suspected_not_diagnosed": facts.get("owner_suspected") or [],
                        "owner_reported_veterinary_evidence": facts.get("veterinary_evidence") or [],
                        "diagnosis_inferred": False,
                        "provider_message_id": canonical["provider_message_id"],
                        "preview_sha256": canonical["preview_sha256"],
                    }, sort_keys=True), digest, operation_id))
                cursor.fetchone()
    except Exception:
        return _result(False, "health_loss_recording_store_unavailable"), 503
    return _result(True, "health_loss_observation_recorded",
                   observation_event_id=event_id, rows_created=1,
                   recommendation_refresh_required=True,
                   operation_id=operation_id), 201


def _confirm_mortality_lifecycle(lifecycle, evaluator, binding, operation_id, actor_id,
                                 *, evidence_loader, connect_factory=None):
    from modules.pig_weights.pig_welfare_case_runtime import welfare_case_runtime_enabled
    if not welfare_case_runtime_enabled():
        return _result(False, "welfare_case_runtime_required_for_atomic_mortality"), 503
    identity = evaluator.get("identity") if isinstance(evaluator.get("identity"), Mapping) else {}
    pig_id = str(identity.get("pig_id") or "")
    lifecycle_effect = next((row for row in evaluator.get("canonical_effects") or []
        if row.get("supported") and row.get("area") == "lifecycle"), None)
    facts = dict((lifecycle_effect or {}).get("facts") or {})
    if (not pig_id or (lifecycle_effect or {}).get("action") != "record_death"
            or not str(facts.get("date") or "") or facts.get("time") != "Unknown"):
        return _result(False, "mortality_lifecycle_effect_invalid"), 409
    movement = next((row for row in evaluator.get("canonical_effects") or []
        if row.get("supported") and row.get("area") == "movement_pen"), {})
    movement_facts = dict(movement.get("facts") or {})
    note_parts = ["Owner reported the pig found dead", "exact time of death Unknown"]
    if movement_facts.get("owner_reported_outcome"):
        note_parts.append("body " + str(movement_facts["owner_reported_outcome"]))
    provider_message_id = str(binding.get("provider_message_id") or "")
    preview_sha256 = str(binding.get("preview_sha256") or "")
    evidence_generation = str(binding.get("evidence_generation") or "")
    note_parts.append("source Telegram " + (provider_message_id or "Unknown"))
    canonical = {"operation_id": operation_id, "pig_id": pig_id,
        "provider_message_id": provider_message_id, "preview_sha256": preview_sha256,
        "evidence_generation": evidence_generation, "event_date": str(facts["date"]),
        "exact_time_of_death": "Unknown", "removal": movement_facts,
        "actor_id": str(actor_id)}
    source_digest = hashlib.sha256(json.dumps(
        canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    event_id = "LIFE-HL-" + hashlib.sha256(operation_id.encode()).hexdigest()[:24].upper()
    try:
        connection_cm = connect_factory() if connect_factory else _connect()
        with connection_cm as connection:
            with connection.cursor() as cursor:
                cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",
                               ("herdmaster-mortality:" + operation_id,))
                cursor.execute("""select lifecycle_event_id,pig_id,event_payload
                    from public.pig_lifecycle_events where idempotency_key=%s""",
                    (operation_id,))
                existing = cursor.fetchone()
                if existing:
                    payload = existing[2] if isinstance(existing[2], Mapping) else {}
                    if (str(existing[1]) != pig_id
                            or str(payload.get("source_digest") or "") != source_digest):
                        return _result(False, "mortality_lifecycle_idempotency_conflict"), 409
                    cursor.execute("""select current.welfare_case_id
                        from public.pig_welfare_case_current current
                        join public.pig_welfare_cases c using(welfare_case_id)
                        where current.pig_id=%s and c.episode_key=%s
                          and current.case_state='closed'
                          and current.closure_kind='death'
                        order by current.state_occurred_at desc,current.welfare_case_id
                        limit 1""", (pig_id, str(lifecycle.get("mission_id") or operation_id)))
                    replay_case = cursor.fetchone()
                    if not replay_case:
                        return _result(False, "mortality_lifecycle_replay_welfare_case_missing"), 409
                    replay_case_id = str(replay_case[0])
                    readback = _readback_mortality_welfare(
                        cursor, pig_id=pig_id, event_id=str(existing[0]),
                        welfare_case_id=replay_case_id)
                    if not readback["canonical_readback_verified"]:
                        return _result(False, "mortality_lifecycle_replay_readback_mismatch"), 409
                    return _result(True, "mortality_lifecycle_replayed_withheld",
                        rows_created=0, operation_id=operation_id, pig_id=pig_id,
                        lifecycle_event_id=str(existing[0]), replay=True,
                        lifecycle_status="Dead", on_farm=False,
                        event_date=str(facts["date"]), exact_time_of_death="Unknown",
                        historical_records_preserved=True,
                        welfare_case_id=replay_case_id, welfare_case_closed=True,
                        living_checks_reconciled=0,
                        preserved_distinct_work=readback["preserved_distinct_work"],
                        canonical_readback=readback), 200
                current = evidence_loader()
                if str(current.get("evidence_generation") or "") != evidence_generation:
                    return _result(False, "canonical_evidence_changed_repreview_required"), 409
                cursor.execute("""select status,on_farm,notes from public.pigs
                    where pig_id=%s for update""", (pig_id,))
                pig = cursor.fetchone()
                if not pig or str(pig[0] or "").casefold() != "active" or pig[1] is not True:
                    return _result(False, "current_active_on_farm_pig_required"), 409
                prior_notes = str(pig[2] or "").strip()
                lifecycle_note = f"{facts['date']} lifecycle outcome: Died recorded by oom_sakkie owner. Notes: {'; '.join(note_parts)}"
                updated_notes = f"{prior_notes}\n{lifecycle_note}" if prior_notes else lifecycle_note
                cursor.execute("""update public.pigs set status='Dead',on_farm=false,
                    exit_date=%s::date,exit_reason='Died',notes=%s,updated_at=now()
                    where pig_id=%s and status='Active' and on_farm is true""",
                    (str(facts["date"]), updated_notes, pig_id))
                if int(getattr(cursor, "rowcount", 0) or 0) != 1:
                    return _result(False, "mortality_lifecycle_concurrent_state_change"), 409
                cursor.execute("""insert into public.pig_lifecycle_events(
                    lifecycle_event_id,pig_id,lifecycle_event_type,effective_at,
                    actor_reference,source_system,source_reference,event_note,
                    event_payload,idempotency_key)
                    values(%s,%s,'exited_farm',%s::date::timestamptz,%s,'owner',%s,%s,%s::jsonb,%s)""", (
                    event_id, pig_id, str(facts["date"]), str(actor_id), source_digest,
                    "; ".join(note_parts), json.dumps({**canonical,
                        "source_digest": source_digest, "resulting_status": "Dead",
                        "resulting_on_farm": False}, sort_keys=True), operation_id))
                cursor.execute("""update public.pig_active_outlets
                    set active=false,released_at=now()
                    where pig_id=%s and active""", (pig_id,))
                coordinated = _coordinate_mortality_welfare(
                    cursor, lifecycle=lifecycle, pig_id=pig_id, event_id=event_id,
                    operation_id=operation_id, actor_id=actor_id,
                    occurred=str(lifecycle.get("provider_timestamp") or ""),
                    source_digest=source_digest)
                readback = _readback_mortality_welfare(
                    cursor, pig_id=pig_id, event_id=event_id,
                    welfare_case_id=coordinated["welfare_case_id"])
                if not readback["canonical_readback_verified"]:
                    raise RuntimeError("mortality_welfare_readback_mismatch")
    except Exception as exc:
        return _result(False, "mortality_lifecycle_recording_unavailable",
                       error_type=type(exc).__name__), 503
    return _result(True, "mortality_lifecycle_recorded", rows_created=1,
                   operation_id=operation_id, pig_id=pig_id,
                   lifecycle_event_id=event_id, lifecycle_status="Dead", on_farm=False,
                   event_date=str(facts["date"]),
                   exact_time_of_death="Unknown", historical_records_preserved=True,
                   welfare_case_id=coordinated["welfare_case_id"],
                   welfare_case_closed=True,
                   living_checks_reconciled=coordinated["living_checks_reconciled"],
                   preserved_distinct_work=readback["preserved_distinct_work"],
                   canonical_readback=readback,
                   recommendation_refresh_required=True), 201


def _coordinate_mortality_welfare(cursor, *, lifecycle, pig_id, event_id,
                                  operation_id, actor_id, occurred, source_digest):
    mission_id = str(lifecycle.get("mission_id") or operation_id)
    derived_case_id = _welfare_case_id(lifecycle, operation_id)
    cursor.execute("""select c.welfare_case_id,latest.urgency,latest.sequence_no
        from public.pig_welfare_cases c
        join lateral (
          select e.urgency,e.sequence_no,e.case_state
          from public.pig_welfare_case_events e
          where e.welfare_case_id=c.welfare_case_id
          order by e.sequence_no desc limit 1
        ) latest on true
        where c.pig_id=%s and c.episode_key=%s
          and latest.case_state=any(%s)
        order by c.episode_started_at desc,c.welfare_case_id
        for update of c""",
        (pig_id, mission_id, ["open", "monitoring", "escalated"]))
    current = cursor.fetchone()
    case_id = str(current[0]) if current else derived_case_id
    provenance = json.dumps({"contract_version": "herdmaster_mortality_welfare_v1",
        "operation_id": operation_id, "mission_id": mission_id,
        "source_digest": source_digest}, sort_keys=True)
    if not current:
        cursor.execute("""select welfare_case_id from public.pig_welfare_cases
            where welfare_case_id=%s for update""", (case_id,))
        existing = cursor.fetchone()
        if existing:
            raise RuntimeError("attributable_welfare_case_not_open")
        cursor.execute("""insert into public.pig_welfare_cases(
            welfare_case_id,pig_id,episode_key,concern_key,episode_started_at,
            first_reported_at,created_by,source_system,source_reference,
            provenance_json,idempotency_key)
            values(%s,%s,%s,'reported-death',%s::timestamptz,%s::timestamptz,
                   %s,'oom_sakkie',%s,%s::jsonb,%s)""",
            (case_id,pig_id,mission_id,occurred,occurred,"owner:"+actor_id,
             str(lifecycle.get("provider_message_id") or ""),provenance,"case:"+mission_id))
        opened_id = "WELFARE-EVENT-" + hashlib.sha256((operation_id+":opened").encode()).hexdigest()[:24].upper()
        cursor.execute("""insert into public.pig_welfare_case_events(
            welfare_case_event_id,welfare_case_id,sequence_no,event_type,case_state,urgency,
            responsible_owner,occurred_at,actor_reference,source_system,
            source_reference,provenance_json,idempotency_key)
            values(%s,%s,1,'opened','open','urgent','HERDMASTER',%s::timestamptz,
                   %s,'oom_sakkie',%s,%s::jsonb,%s)""",
            (opened_id,case_id,occurred,"owner:"+actor_id,source_digest,provenance,
             operation_id+":welfare-opened"))
        urgency, next_sequence = "urgent", 2
    else:
        urgency, next_sequence = str(current[1]), int(current[2]) + 1
    closed_id = "WELFARE-EVENT-" + hashlib.sha256((operation_id+":death-closed").encode()).hexdigest()[:24].upper()
    cursor.execute("""insert into public.pig_welfare_case_events(
        welfare_case_event_id,welfare_case_id,sequence_no,event_type,case_state,urgency,
        responsible_owner,closure_kind,closure_reason,occurred_at,actor_reference,
        source_system,source_reference,provenance_json,idempotency_key)
        values(%s,%s,%s,'closed','closed',%s,'HERDMASTER','death',
               'Canonical death closes this living-welfare concern',%s::timestamptz,
               %s,'herdmaster',%s,%s::jsonb,%s)""",
        (closed_id,case_id,next_sequence,urgency,occurred,"owner:"+actor_id,source_digest,
         provenance,operation_id+":welfare-death-closed"))
    link_id = "WELFARE-LINK-" + hashlib.sha256((operation_id+":death-link").encode()).hexdigest()[:24].upper()
    cursor.execute("""insert into public.pig_welfare_case_fact_links(
        welfare_case_fact_link_id,welfare_case_id,welfare_case_event_id,fact_domain,
        fact_id,relationship,linked_at,actor_reference,source_reference,
        provenance_json,idempotency_key)
        values(%s,%s,%s,'pig_lifecycle',%s,'closes_living_welfare_question',
               %s::timestamptz,%s,%s,%s::jsonb,%s)""",
        (link_id,case_id,closed_id,event_id,occurred,"owner:"+actor_id,
         source_digest,provenance,operation_id+":welfare-death-link"))
    cursor.execute("""update app_private.oom_manager_cases set status='completed',
        next_action='Closed because the pig is deceased',updated_at=now()
        where specialist='HERDMASTER' and status=any(%s)
          and evidence_refs @> %s::jsonb
          and (lower(summary) like '%%welfare%%' or lower(summary) like '%%health%%'
               or lower(next_action) like '%%check%%')
          and lower(summary) not like '%%mortality%%'
          and lower(summary) not like '%%disposal%%'
          and lower(summary) not like '%%biosecurity%%'
        returning case_id,generation""",
        (["open","delegated","waiting_reassessment","exception"],
         json.dumps([{"pig_id": pig_id}], sort_keys=True)))
    reconciled = list(cursor.fetchall())
    for manager_case_id, generation in reconciled:
        material = {"case_id": str(manager_case_id), "generation": int(generation),
            "event_type": "completed", "operation_id": operation_id,
            "reason": "canonical_pig_death"}
        manager_event_id = "OOM-MANAGER-EVENT-" + hashlib.sha256(
            json.dumps(material, sort_keys=True).encode()).hexdigest()[:32].upper()
        cursor.execute("""insert into app_private.oom_manager_case_events(
            event_id,case_id,generation,event_type,event_payload,occurred_at)
            values(%s,%s,%s,'completed',%s::jsonb,now())
            on conflict(event_id) do nothing""",
            (manager_event_id,str(manager_case_id),int(generation),
             json.dumps(material, sort_keys=True)))
    return {"welfare_case_id": case_id,
            "living_checks_reconciled": len(reconciled)}


def _welfare_case_id(lifecycle, operation_id):
    mission_id = str(lifecycle.get("mission_id") or operation_id)
    return "WELFARE-" + hashlib.sha256(mission_id.encode()).hexdigest()[:24].upper()


def _readback_mortality_welfare(cursor, *, pig_id, event_id, welfare_case_id):
    cursor.execute("""select p.status,p.on_farm,p.exit_reason,e.lifecycle_event_id,
        current.case_state,current.closure_kind,
        exists(select 1 from public.pig_welfare_case_fact_links l
          where l.welfare_case_id=current.welfare_case_id
            and l.fact_id=e.lifecycle_event_id
            and l.relationship='closes_living_welfare_question')
        from public.pigs p
        join public.pig_lifecycle_events e on e.pig_id=p.pig_id and e.lifecycle_event_id=%s
        join public.pig_welfare_case_current current on current.welfare_case_id=%s
        where p.pig_id=%s""", (event_id,welfare_case_id,pig_id))
    row = cursor.fetchone()
    cursor.execute("""select count(*) from public.pig_current_state
        where pig_id=%s and status='Active' and on_farm is true
          and current_pen_id is not null""", (pig_id,))
    pen_membership = int((cursor.fetchone() or [0])[0] or 0)
    cursor.execute("""select count(*) from public.pig_active_outlets
        where pig_id=%s and active""", (pig_id,))
    active_outlets = int((cursor.fetchone() or [0])[0] or 0)
    cursor.execute("""select count(*) from app_private.oom_manager_cases
        where specialist='HERDMASTER' and status=any(%s)
          and evidence_refs @> %s::jsonb
          and (lower(summary) like '%%mortality%%' or lower(summary) like '%%disposal%%'
               or lower(summary) like '%%biosecurity%%')""",
        (["open","delegated","waiting_reassessment","exception"],
         json.dumps([{"pig_id": pig_id}], sort_keys=True)))
    distinct = cursor.fetchone()
    verified = bool(row and str(row[0]).casefold()=="dead" and row[1] is False
                    and str(row[2]).casefold()=="died" and str(row[3])==event_id
                    and str(row[4])=="closed" and str(row[5])=="death" and row[6] is True
                    and pen_membership == 0 and active_outlets == 0)
    return {"canonical_readback_verified": verified,
            "pig_status": str(row[0]) if row else "Unknown",
            "on_farm": row[1] if row else "Unknown",
            "lifecycle_event_id": str(row[3]) if row else "",
            "welfare_case_id": welfare_case_id,
            "welfare_case_state": str(row[4]) if row else "Unknown",
            "welfare_closure_kind": str(row[5]) if row else "Unknown",
            "active_pen_occupancy_membership_count": pen_membership,
            "active_availability_outlet_count": active_outlets,
            "excluded_from_active_pen_and_availability_projections": bool(
                pen_membership == 0 and active_outlets == 0),
            "preserved_distinct_work": int((distinct or [0])[0] or 0)}


def _factual_note(facts):
    observed = facts.get("observed") if isinstance(facts.get("observed"), list) else []
    return "Owner-reported welfare observations: " + "; ".join(
        f"{row.get('fact')}: {row.get('value')}" for row in observed if isinstance(row, Mapping)
    )


def _connect():
    import psycopg
    return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10)


def _result(success, status, **extra):
    return {"success": success, "status": status, "writes_farm_data": bool(success and extra.get("rows_created")),
            "diagnosis_inferred": False, "treatment_recorded": False, **extra}
