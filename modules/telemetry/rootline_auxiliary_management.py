"""Pure planning contracts for ROOTLINE irrigation auxiliary work.

Fertilizer support is deliberately separate from irrigation-zone ranking and
delivery debt.  These functions persist nothing, schedule nothing and command
nothing; they produce typed work/eligibility packets for the existing
coordinator boundary.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from modules.telemetry.rootline_device_registry import get_device_contract

SAST = ZoneInfo("Africa/Johannesburg")
BATCH_CONTRACT = "rootline_fertilizer_batch.v1"
TASK_CONTRACT = "rootline_irrigation_auxiliary_task.v1"
ELIGIBILITY_CONTRACT = "rootline_auxiliary_eligibility.v1"
MAX_MIX_SECONDS = 300
MAX_DAILY_MIX_MINUTES = 30
INJECTION_SECONDS = 120
MIN_PREFLOW_SECONDS = 600
MIN_PULSE_SPACING_SECONDS = 600
MIN_FLUSH_SECONDS = 600


def build_fertilizer_batch_lifecycle(*, observations=None, executions=None, now=None,
                                     previous_work_item_key=None):
    now = _aware(now or datetime.now(timezone.utc)).astimezone(SAST)
    observations = [deepcopy(row) for row in observations or [] if isinstance(row, dict)]
    executions = [deepcopy(row) for row in executions or [] if isinstance(row, dict)]
    monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0,
        second=0, microsecond=0)
    next_due = monday + timedelta(days=7)
    prepared = [row for row in observations
        if row.get("event_type") == "fertilizer_batch_prepared"
        and _time(row.get("observed_at")) is not None
        and monday <= _time(row.get("observed_at")).astimezone(SAST) <= now < next_due]
    latest = max(prepared, key=lambda row:_time(row.get("observed_at"))) if prepared else None
    batch_at = _time(latest.get("observed_at")) if latest else None
    period_start=batch_at or monday.astimezone(timezone.utc)
    refill = [row for row in observations if row.get("event_type") == "water_only_refill"
              and _time(row.get("observed_at")) is not None
              and period_start <= _time(row.get("observed_at")) <= now.astimezone(timezone.utc)]
    state = "batch_reported_prepared" if latest else "monday_batch_due"
    scoped_executions=[row for row in executions
        if row.get("shutdown_verified") is True
        and _time(row.get("completed_at")) is not None
        and period_start <= _time(row.get("completed_at")) <= now.astimezone(timezone.utc)
        and (not latest or not row.get("batch_generation")
             or row.get("batch_generation")==latest.get("batch_generation"))]
    material = {"contract_version":BATCH_CONTRACT,"week_start":monday.date().isoformat(),
        "state":state,"batch_timestamp":batch_at.isoformat() if batch_at else None,
        "recipe":latest.get("recipe","Unknown") if latest else "Unknown",
        "concentration":latest.get("concentration","Unknown") if latest else "Unknown",
        "nutrient_dose":"Unknown","water_only_refill_count":len(refill),
        "dilution_acknowledged":bool(refill),"next_batch_due":next_due.isoformat(),
        "mixing_execution_ids":sorted(str(row.get("execution_id")) for row in scoped_executions
            if row.get("device_type")=="fertilizer_mixer"),
        "injection_execution_ids":sorted(str(row.get("execution_id")) for row in scoped_executions
            if row.get("device_type")=="fertilizer_injection_valve"),
        "invalid_timestamp_evidence_count":sum(1 for row in observations
            if row.get("event_type") in {"fertilizer_batch_prepared","water_only_refill"}
            and _time(row.get("observed_at")) is None)}
    digest=_digest(material)
    reminder={"work_item_type":"fertilizer_batch_due","collection":"irrigation_auxiliary_tasks",
        "deduplication_key":f"ROOTLINE-FERTILIZER-BATCH-{monday.date().isoformat()}",
        "emit":state=="monday_batch_due" and previous_work_item_key !=
            f"ROOTLINE-FERTILIZER-BATCH-{monday.date().isoformat()}",
        "owner_text":"Please prepare this week's fertilizer batch."}
    return {**material,"batch_generation":"ROOTLINE-BATCH-"+digest[:24].upper(),
        "batch_sha256":digest,"monday_work_item":reminder,"command_authority":False,
        "hardware_control":False}


def mixer_configuration_preview():
    contract=get_device_contract("FERTILIZER-MIXER-CH2")
    return {"status":"preview_only","apply_configuration":False,
        "device_id":contract["device_id"],"channel":2,"physical_name":"Kunsmis Meng",
        "before":{"native_inching_enabled":"readback_required",
                  "native_inching_seconds":"readback_required"},
        "after":{"native_inching_enabled":True,"native_inching_seconds":300,
                 "power_restoration_state":"OFF"},
        "required_preconditions":["authoritative_provider_readback",
            "no_conflicting_schedule_timer_scene_or_interlock",
            "owner_present_for_supervised_physical_commissioning"],
        "command_authority":False,"configuration_authority":False}


def build_fertilized_irrigation_sequence(*, zone_id, irrigation_runtime_seconds=3599):
    if zone_id not in {"B12345","C12345"} or not 1800 <= int(irrigation_runtime_seconds) <= 3599:
        raise ValueError("fertilized_irrigation_envelope_invalid")
    stages=[
        {"stage":"pre_mix","device_type":"fertilizer_mixer","maximum_seconds":300,
         "optional_when":"fresh_verified_mix_already_exists"},
        {"stage":"verify_mixer_off","required":True},
        {"stage":"start_irrigation","zone_id":zone_id,"via":"existing_bc_coordinator"},
        {"stage":"clean_water_preflow","minimum_seconds":600},
        {"stage":"injection_pulse_1","device_type":"fertilizer_injection_valve",
         "maximum_seconds":120,"fresh_eligibility":True},
        {"stage":"verify_injection_off_1","required":True},
        {"stage":"pulse_spacing","minimum_seconds":600},
        {"stage":"injection_pulse_2","device_type":"fertilizer_injection_valve",
         "maximum_seconds":120,"fresh_eligibility":True},
        {"stage":"verify_injection_off_2","required":True},
        {"stage":"clean_water_flush","minimum_seconds":600},
        {"stage":"verified_irrigation_shutdown","via":"existing_bc_coordinator"},
    ]
    return {"contract_version":"rootline_fertilized_irrigation_sequence.v1",
        "collection":"irrigation_auxiliary_tasks","zone_id":zone_id,
        "irrigation_runtime_seconds":int(irrigation_runtime_seconds),"stages":stages,
        "mixing_and_injection_simultaneous":False,"max_injection_pulses":2,
        "irrigation_may_complete_if_fertilizer_fails":True,
        "fertilizer_debt_recorded_separately":True,"nutrient_dose":"Unknown",
        "concentration":"Unknown","delivered_volume":"Unavailable",
        "command_authority":False,"hardware_control":False}


def build_auxiliary_tasks(*, batch, power=None, verified_mixing=None,
                          mixing_history_complete_through=None, now=None):
    now=_aware(now or datetime.now(timezone.utc)); power=power if isinstance(power,dict) else {}
    verified_mixing=[row for row in verified_mixing or [] if isinstance(row,dict)
                     and row.get("shutdown_verified") is True]
    today=now.astimezone(SAST).date().isoformat()
    used=sum(float(row.get("verified_runtime_minutes") or 0) for row in verified_mixing
             if str(row.get("completed_at") or "")[:10]==today)
    remaining=max(0,MAX_DAILY_MIX_MINUTES-used)
    complete_at=_time(mixing_history_complete_through)
    history_complete=(complete_at is not None
        and timedelta(0)<=now-complete_at<=timedelta(minutes=5))
    has_power=all(power.get(field) is not None for field in
                  ("battery_soc_pct","solar_power_w","grid_power_w"))
    low_power=(has_power and float(power["battery_soc_pct"])<50
               and float(power["solar_power_w"])<1200
               and float(power["grid_power_w"])<=0)
    mixer_status=("Needs Data" if not history_complete else "Completed" if remaining==0
                  else "Needs Data" if not has_power
                  else "Run later" if low_power else "Run now")
    mixer={"contract_version":TASK_CONTRACT,"auxiliary_task_id":
        f"ROOTLINE-MIX-{today}","collection":"irrigation_auxiliary_tasks",
        "auxiliary_device_id":"FERTILIZER-MIXER-CH2","device_type":"fertilizer_mixer",
        "decision":mixer_status,"planned_seconds":min(MAX_MIX_SECONDS,int(remaining*60))
            if history_complete else 0,
        "verified_minutes_today":used if history_complete else "Unknown",
        "remaining_verified_minutes_today":remaining if history_complete else "Unknown",
        "reason":("mixing_history_incomplete" if not history_complete
                  else "daily_verified_mixing_cap_reached" if remaining==0
                  else "power_evidence_unavailable" if not has_power
                  else "prefer_solar_or_soc_window" if low_power
                  else "batch_support_mixing"),
        "does_not_block_bc_irrigation":True,"command_authority":False}
    injection={"contract_version":TASK_CONTRACT,"auxiliary_task_id":
        f"ROOTLINE-INJECTION-{today}","collection":"irrigation_auxiliary_tasks",
        "auxiliary_device_id":"FERTILIZER-INJECTION-CH1",
        "device_type":"fertilizer_injection_valve","decision":"Await eligible irrigation",
        "pulse_seconds":120,"maximum_pulses_per_segment":2,"nutrient_dose":"Unknown",
        "concentration":batch.get("concentration","Unknown"),
        "does_not_block_bc_irrigation":True,"command_authority":False}
    return {"irrigation_auxiliary_devices":["FERTILIZER-INJECTION-CH1",
        "FERTILIZER-MIXER-CH2"],"irrigation_auxiliary_tasks":[mixer,injection],
        "irrigation_zones":[],"zone_delivery_debt_changes":0}


def auxiliary_notification_projection(*, fertilizer_included=False, batch=None,
                                      previous_batch_work_item_key=None):
    batch=batch if isinstance(batch,dict) else {}
    work=batch.get("monday_work_item") if isinstance(batch.get("monday_work_item"),dict) else {}
    reminder=bool(work.get("emit") and work.get("deduplication_key")!=previous_batch_work_item_key)
    return {"daily_plan_fertilizer_status":("Fertilizer included"
            if fertilizer_included else "Fertilizer unavailable; irrigation continues"),
        "emit_monday_batch_reminder":reminder,
        "batch_reminder_identity":work.get("deduplication_key") if reminder else None,
        "mixing_notifications":["Started","Completed"],
        "irrigation_lifecycle_annotation":"Fertilizer Included" if fertilizer_included else None,
        "uncertain_shutdown_notification":"Intervention",
        "unchanged_auxiliary_tasks_silent":True,"telegram_send_performed":False}


def build_auxiliary_eligibility(*, task, safety, context, flags=None, now=None):
    now=_aware(now or datetime.now(timezone.utc)); flags=flags or {}
    if not isinstance(task,dict) or not isinstance(safety,dict) or not isinstance(context,dict):
        return _ineligible("auxiliary_context_incomplete")
    identity=str(task.get("auxiliary_device_id") or ""); contract=get_device_contract(identity)
    if not contract or contract["collection"]!="irrigation_auxiliary_devices":
        return _ineligible("auxiliary_device_not_registered")
    if flags.get(contract["authority_flag"]) is not True:
        return _ineligible("auxiliary_authority_disabled")
    if not _safe(contract,safety,now): return _ineligible("auxiliary_safety_unproven")
    if context.get("prior_shutdown_unverified") is True or context.get("fertilizer_exception"):
        return _ineligible("fertilizer_exception_or_shutdown_unverified")
    device_type=contract["device_type"]
    if device_type=="fertilizer_injection_valve":
        reason=_injection_gate(context,now)
        runtime=INJECTION_SECONDS
    else:
        reason=_mixing_gate(context,now)
        runtime=MAX_MIX_SECONDS
    if reason: return _ineligible(reason)
    generation=str(context.get("plan_generation") or "")
    if not generation: return _ineligible("plan_generation_missing")
    material={"contract_version":ELIGIBILITY_CONTRACT,"device_contract_sha256":
        contract["contract_sha256"],"auxiliary_device_id":identity,
        "device_type":device_type,"device_id":contract["device_id"],
        "channel":contract["channel"],"on_event":contract["on_event"],
        "off_event":contract["off_event"],"maximum_duration_seconds":runtime,
        "plan_generation":generation,"controller_safety_generation":
        safety["controller_safety_generation"],"provider_output_state":safety["output_state"],
        "decision_at":now.isoformat(),"expires_at":(now+timedelta(minutes=5)).isoformat(),
        "single_use":True,"simultaneous_with_other_auxiliary":False}
    if device_type=="fertilizer_injection_valve":
        start_evidence=context["zone_start_evidence"]
        output_evidence=context["zone_output_evidence"]
        material.update({"zone_id":context["active_zone_ids"][0],
            "job_id":context["job_id"],"job_sha256":context["job_sha256"],
            "segment_identity":context["segment_identity"],
            "zone_execution_id":context["zone_execution_id"],
            "pulse_number":int(context["completed_pulses"])+1,
            "batch_generation":context.get("batch_generation") or
                "explicit_owner_time_programme",
            "zone_start_evidence_id":start_evidence["evidence_id"],
            "zone_started_at":_time(start_evidence["observed_at"]).isoformat(),
            "zone_output_evidence_id":output_evidence["evidence_id"],
            "zone_output_observed_at":_time(output_evidence["observed_at"]).isoformat(),
            "irrigation_stop_deadline":_time(context["irrigation_stop_deadline"]).isoformat(),
            "prior_pulse_shutdown_evidence_id":(context.get(
                "prior_pulse_shutdown_evidence") or {}).get("evidence_id"),
            "prior_pulse_shutdown_observed_at":(_time((context.get(
                "prior_pulse_shutdown_evidence") or {}).get("observed_at")).isoformat()
                if _time((context.get("prior_pulse_shutdown_evidence") or {}).get(
                    "observed_at")) else None)})
    digest=_digest(material)
    return {"eligible":True,"status":"auxiliary_execution_eligible",
        "eligibility_id":"ROOTLINE-AUX-ELIGIBILITY-"+digest[:24].upper(),
        "execution_id":"ROOTLINE-AUX-EXECUTION-"+digest[:24].upper(),
        "consumption_key":"ROOTLINE-AUX-CONSUME-"+_digest({
            "plan":generation,"job":material.get("job_id"),
            "job_sha256":material.get("job_sha256"),
            "segment":material.get("segment_identity"),"device":identity,
            "pulse":material.get("pulse_number",1)})[:24].upper(),
        "eligibility_sha256":digest,"command_authority":True,"hardware_control":True,
        **material}


def validate_auxiliary_eligibility(value, *, now=None):
    now=_aware(now or datetime.now(timezone.utc))
    if not isinstance(value,dict) or value.get("eligible") is not True: return None
    excluded={"eligible","status","eligibility_id","execution_id","consumption_key",
              "eligibility_sha256","command_authority","hardware_control"}
    material={key:item for key,item in value.items() if key not in excluded}
    digest=_digest(material)
    contract=get_device_contract(value.get("auxiliary_device_id"))
    expected_consumption="ROOTLINE-AUX-CONSUME-"+_digest({
        "plan":value.get("plan_generation"),"job":value.get("job_id"),
        "job_sha256":value.get("job_sha256"),
        "segment":value.get("segment_identity"),"device":value.get("auxiliary_device_id"),
        "pulse":value.get("pulse_number",1)})[:24].upper()
    expected_runtime=(INJECTION_SECONDS if value.get("device_type")==
                      "fertilizer_injection_valve" else MAX_MIX_SECONDS)
    if (not contract or value.get("contract_version")!=ELIGIBILITY_CONTRACT
            or value.get("eligibility_sha256")!=digest
            or value.get("eligibility_id")!="ROOTLINE-AUX-ELIGIBILITY-"+digest[:24].upper()
            or value.get("execution_id")!="ROOTLINE-AUX-EXECUTION-"+digest[:24].upper()
            or value.get("command_authority") is not True
            or value.get("hardware_control") is not True
            or value.get("single_use") is not True
            or value.get("simultaneous_with_other_auxiliary") is not False
            or value.get("consumption_key")!=expected_consumption
            or value.get("device_contract_sha256")!=contract.get("contract_sha256")
            or value.get("device_id")!=contract.get("device_id")
            or value.get("channel")!=contract.get("channel")
            or value.get("on_event")!=contract.get("on_event")
            or value.get("off_event")!=contract.get("off_event")
            or value.get("maximum_duration_seconds")!=expected_runtime): return None
    decision=_time(value.get("decision_at")); expires=_time(value.get("expires_at"))
    return value if decision and expires and decision<=now<=expires else None


def revalidate_auxiliary_execution_edge(artifact, *, current_context, current_safety, now=None):
    """Revalidate changing evidence immediately before an auxiliary ON edge."""
    now=_aware(now or datetime.now(timezone.utc))
    value=validate_auxiliary_eligibility(artifact,now=now)
    if not value or not isinstance(current_context,dict) or not isinstance(current_safety,dict):
        return False
    contract=get_device_contract(value["auxiliary_device_id"])
    if not contract or not _safe(contract,current_safety,now):
        return False
    if current_safety.get("controller_safety_generation")!=value.get(
            "controller_safety_generation"):
        return False
    if value["device_type"]=="fertilizer_injection_valve":
        if (current_context.get("job_id")!=value.get("job_id")
                or current_context.get("job_sha256")!=value.get("job_sha256")
                or current_context.get("segment_identity")!=value.get("segment_identity")
                or current_context.get("zone_execution_id")!=value.get("zone_execution_id")
                or current_context.get("active_zone_ids")!=[value.get("zone_id")]
                or _time(current_context.get("irrigation_stop_deadline"))!=
                    _time(value.get("irrigation_stop_deadline"))):
            return False
        output=current_context.get("zone_output_evidence") or {}
        if (output.get("zone_execution_id")!=value.get("zone_execution_id")
                or output.get("state")!="ON"):
            return False
        if value.get("pulse_number")==2:
            prior=current_context.get("prior_pulse_shutdown_evidence") or {}
            if prior.get("evidence_id")!=value.get("prior_pulse_shutdown_evidence_id"):
                return False
        return _injection_gate(current_context,now) is None
    return _mixing_gate(current_context,now) is None


def _injection_gate(context,now):
    zones=context.get("active_zone_ids") if isinstance(context.get("active_zone_ids"),list) else []
    pulse=int(context.get("completed_pulses") or 0)
    if (not str(context.get("job_id") or "").startswith("ROOTLINE-IRRIGATION-JOB-")
            or len(str(context.get("job_sha256") or "")) != 64
            or not str(context.get("segment_identity") or "").startswith(
                "ROOTLINE-JOB-SEGMENT-")):
        return "irrigation_job_binding_incomplete"
    if len(zones)!=1 or zones[0] not in {"B12345","C12345"}: return "exactly_one_bc_zone_required"
    start=context.get("zone_start_evidence") if isinstance(
        context.get("zone_start_evidence"),dict) else {}
    output=context.get("zone_output_evidence") if isinstance(
        context.get("zone_output_evidence"),dict) else {}
    start_at=_time(start.get("observed_at"));output_at=_time(output.get("observed_at"))
    if (not start.get("evidence_id") or start.get("zone_execution_id")!=
            context.get("zone_execution_id") or start_at is None):
        return "clean_water_preflow_incomplete"
    if (not output.get("evidence_id") or output.get("zone_execution_id")!=
            context.get("zone_execution_id") or output.get("state")!="ON"
            or output_at is None or not timedelta(0)<=now-output_at<=timedelta(minutes=5)):
        return "active_zone_unverified"
    if now-start_at<timedelta(seconds=MIN_PREFLOW_SECONDS):
        return "clean_water_preflow_incomplete"
    if context.get("mixer_active") is True: return "mixer_must_be_off"
    if pulse not in (0,1): return "two_pulse_limit_reached"
    prior=context.get("prior_pulse_shutdown_evidence") if isinstance(
        context.get("prior_pulse_shutdown_evidence"),dict) else {}
    prior_at=_time(prior.get("observed_at"))
    if pulse==1 and (not prior.get("evidence_id") or prior.get("shutdown_verified") is not True
            or prior.get("zone_execution_id")!=context.get("zone_execution_id")
            or prior_at is None or now-prior_at<timedelta(seconds=MIN_PULSE_SPACING_SECONDS)):
        return "pulse_spacing_incomplete"
    required=(INJECTION_SECONDS+MIN_PULSE_SPACING_SECONDS+INJECTION_SECONDS+MIN_FLUSH_SECONDS
              if pulse==0 else INJECTION_SECONDS+MIN_FLUSH_SECONDS)
    stop_at=_time(context.get("irrigation_stop_deadline"))
    if stop_at is None or stop_at-now<timedelta(seconds=required):
        return "clean_water_flush_window_incomplete"
    if not context.get("batch_generation") and context.get("explicit_owner_time_programme") is not True:
        return "batch_or_owner_programme_required"
    return None


def _mixing_gate(context,now):
    if context.get("injection_active") is True: return "injection_must_be_off"
    complete_at=_time(context.get("mixing_history_complete_through"))
    if complete_at is None or not timedelta(0)<=now-complete_at<=timedelta(minutes=5):
        return "mixing_history_incomplete"
    used=float(context.get("verified_mixing_minutes_today") or 0)
    if int(context.get("verified_mixing_sessions_today") or 0)>=6:
        return "daily_mixing_session_cap_reached"
    if used+MAX_MIX_SECONDS/60>MAX_DAILY_MIX_MINUTES: return "daily_mixing_cap_reached"
    if context.get("power_suitable") is not True and context.get("mixing_urgent") is not True:
        return "low_power_mix_deferred"
    return None


def _safe(contract,safety,now):
    observed=_time(safety.get("observed_at"))
    return (safety.get("authoritative") is True and bool(safety.get("response_digest"))
        and safety.get("device_id")==contract["device_id"]
        and safety.get("channel")==contract["channel"] and safety.get("output_state")=="OFF"
        and safety.get("native_inching_enabled") is True
        and int(safety.get("native_inching_seconds") or 0)==contract["native_fail_stop_seconds"]
        and safety.get("power_restoration_state")=="OFF"
        and safety.get("schedules_enabled") is False and safety.get("timers_enabled") is False
        and safety.get("scenes_enabled") is False and safety.get("interlock_enabled") is False
        and bool(safety.get("controller_safety_generation"))
        and bool(safety.get("physical_commissioning_generation"))
        and safety.get("commissioned") is True and observed is not None
        and timedelta(0)<=now-observed<=timedelta(minutes=5)
    )


def _ineligible(status):
    return {"eligible":False,"status":status,"command_authority":False,"hardware_control":False}


def _time(value):
    try:return _aware(datetime.fromisoformat(str(value).replace("Z","+00:00")))
    except (TypeError,ValueError):return None


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _digest(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
