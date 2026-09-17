"""Fail-closed Borehole 1 commissioning and protected-preview contract."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone

MAX_SECONDS=300
def build_preview(readback, *, ifttt_mapping_owner_verified, physical_owner_present,
                  restoration_setting_unavailable=False,
                  electrical_isolation_immediately_available=False, now=None):
    now=now or datetime.now(timezone.utc); blockers=[]
    if readback.get("device_name") not in {"Borehole 1 Pump","Borehole Pump 1"}: blockers.append("device_identity")
    if not readback.get("online"): blockers.append("provider_offline")
    if readback.get("switch")!="OFF": blockers.append("initial_state_not_off")
    if readback.get("current_ma")!=0 or readback.get("power_deciwatts")!=0: blockers.append("initial_power_not_idle")
    if readback.get("fault") not in {0,None}: blockers.append("provider_fault")
    timers=readback.get("timers") if isinstance(readback.get("timers"),list) else []
    if any(row.get("status")==1 and any(
            fn.get("code")=="switch_1" and fn.get("value") is True
            for fn in row.get("functions") or []) for row in timers):
        blockers.append("enabled_provider_on_schedule")
    restoration_contained=(restoration_setting_unavailable is True and
                            electrical_isolation_immediately_available is True and
                            physical_owner_present is True)
    if readback.get("power_restoration_state")!="OFF" and not restoration_contained:
        blockers.append("power_restoration_risk_uncontained")
    if ifttt_mapping_owner_verified is not True: blockers.append("ifttt_mapping_unverified")
    if physical_owner_present is not True: blockers.append("physical_observer_unavailable")
    material={"contract_version":"rootline_borehole_commissioning.v1","device":"Borehole 1 Pump",
      "device_id_fingerprint":readback.get("device_id_fingerprint"),"action":"one_supervised_test",
      "on_attempts":1,"maximum_seconds":MAX_SECONDS,"native_countdown_seconds":MAX_SECONDS,
      "provider_start_checks":["switch_ON","meaningful_power_draw","fault_clear"],
      "physical_start_checks":["normal_pump_sound","visible_water_flow","pump_controller_normal"],
      "abort_conditions":["abnormal_sound","missing_flow","controller_fault","unexpected_power","lost_readback","owner_abort"],
      "off_paths":["native_countdown","governed_provider_OFF","IFTTT_OFF","SmartLife_app","physical_button","electrical_supply"],
      "final_checks":["provider_OFF","idle_power","physical_pumping_stopped","water_flow_stopped"],
      "power_restoration_state":"Unknown",
      "power_restoration_evidence":"provider_and_owner_UI_setting_unavailable" if restoration_setting_unavailable else "provider_not_exposed",
      "power_restoration_containment":"supervised_test_only_with_immediate_electrical_isolation" if restoration_contained else "uncontained",
      "autonomous_authority_after_test":False,
      "power_restoration_risk":"loss and restoration of supply requires immediate owner isolation; commissioning authority ends with this test",
      "prepared_at":now.isoformat(),"evidence_digest":readback.get("response_digest"),"blockers":blockers,
      "visible_state":"Intervention" if blockers else "Planned",
      "command_authority":False,"hardware_control":False}
    material["preview_sha256"]=hashlib.sha256(json.dumps(material,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return material

def classify_fail_stop_capabilities(*, countdown_semantics, timer_service,
                                    independent_device_backup):
    countdown_safe=(countdown_semantics=="persistent_fail_off")
    paired_schedule_safe=(isinstance(timer_service,dict)
      and timer_service.get("absolute_off") is True
      and timer_service.get("provider_readback") is True
      and timer_service.get("device_local_enforcement_proven") is True)
    durable_workflow_safe=(isinstance(timer_service,dict)
      and timer_service.get("absolute_off") is True
      and timer_service.get("provider_readback") is True)
    independent_backup_safe=(isinstance(independent_device_backup,dict)
      and independent_device_backup.get("automatic_fail_off") is True
      and independent_device_backup.get("independent_of_cloud_and_worker") is True)
    return {"native_countdown_qualified":countdown_safe,
      "device_native_paired_off_qualified":paired_schedule_safe,
      "durable_cloud_off_workflow_available":durable_workflow_safe,
      "independent_device_backup_qualified":independent_backup_safe,
      "supervised_on_permitted":bool(countdown_safe or paired_schedule_safe
        or (durable_workflow_safe and independent_backup_safe)),
      "minimum_hardware_requirement":None if (countdown_safe or paired_schedule_safe
        or independent_backup_safe) else
        "persistent fail-OFF maximum-runtime/inching, or a normally-off contactor/controller with independently enforced runtime"}
