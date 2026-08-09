"""Versioned, append-only ROOTLINE B/C effective-rainfall projection.

Schedule debt remains in the canonical irrigation history. This module owns a
separate crop-water-equivalent ledger beginning at an explicit activation
boundary. It never commands hardware or turns forecast rain into crop water.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

CONTRACT="rootline_zone_water_balance.v1"
RULE_VERSION="rootline_effective_rainfall_provisional_v1"
ZONES={
    "B12345":{"crop":"lucerne","area_m2":2400,"coefficient":0.60,
        "root_zone":"established_deeper_rooted","nominal_flow_l_h":16800},
    "C12345":{"crop":"mixed vegetables including spinach and beetroot","area_m2":300,
        "coefficient":0.45,"root_zone":"generally_shallower_rooted","nominal_flow_l_h":2100},
}
SUPPORTED_NEED_MM=14.0
NOMINAL_APPLICATION_MM_H=7.0


def build_zone_water_balance(zone_id, *, activation_at, complete_through,
                             observed_rain=None, forecast=None,
                             irrigation_outcomes=None, prior_balance_mm=0,
                             estimated_demand_mm=0, now=None):
    now=_aware(now or datetime.now(timezone.utc));activation=_time(activation_at)
    cutoff=_time(complete_through);zone=ZONES.get(str(zone_id))
    if not zone or activation is None or cutoff is None or cutoff>now or activation>cutoff:
        return _unavailable(zone_id,"activation_or_complete_through_invalid")
    rain=_rain(observed_rain,activation,cutoff)
    irrigation=_irrigation(irrigation_outcomes,str(zone_id),zone,activation,cutoff)
    forecast_packet=_forecast(forecast)
    raw_effective=rain["observed_mm"]*zone["coefficient"] if rain["credit_supported"] else 0.0
    effective=min(SUPPORTED_NEED_MM,max(0.0,raw_effective))
    irrigation_mm=min(SUPPORTED_NEED_MM,max(0.0,irrigation["credited_mm"]))
    demand=max(0.0,_number(estimated_demand_mm) or 0.0)
    prior=max(-SUPPORTED_NEED_MM,min(SUPPORTED_NEED_MM,_number(prior_balance_mm) or 0.0))
    supported_supply=min(SUPPORTED_NEED_MM,effective+irrigation_mm)
    remaining=max(0.0,min(SUPPORTED_NEED_MM,SUPPORTED_NEED_MM+ demand-prior-supported_supply))
    credit=min(SUPPORTED_NEED_MM,supported_supply)
    if rain["status"] in {"stale","conflicting","incomplete",
            "coverage_crosses_activation_boundary"} or irrigation["conflicting"]:
        effect="Needs Data"
    elif credit>=SUPPORTED_NEED_MM:
        effect="satisfied"
    elif credit>0:
        effect="partial credit"
    elif rain["observed_mm"]>0:
        effect="Hold with no credit"
    else:
        effect="no credit"
    material={"contract_version":CONTRACT,"rule_version":RULE_VERSION,
        "zone_id":str(zone_id),"activation_at":activation.isoformat(),
        "complete_through":cutoff.isoformat(),"crop":zone["crop"],
        "soil":"very sandy","root_zone_assumption":zone["root_zone"],
        "area_m2":zone["area_m2"],"supported_need_mm":SUPPORTED_NEED_MM,
        "observed_rain":rain,"forecast":forecast_packet,
        "effective_rainfall_mm":round(effective,3),
        "effective_rainfall_confidence":rain["confidence"],
        "verified_irrigation":irrigation,"prior_balance_mm":prior,
        "estimated_demand_mm":demand,"credited_supply_mm":round(credit,3),
        "remaining_water_need_mm":round(remaining,3),"obligation_effect":effect,
        "partial_obligation_credit":round(credit/SUPPORTED_NEED_MM,4),
        "full_obligation_credit":effect=="satisfied",
        "schedule_debt_rewritten":False,"forecast_water_credit_mm":0.0,
        "reservoir_water_credit_mm":0.0,"on_receipts_counted":0,
        "provisional":True,"command_authority":False,"hardware_control":False}
    digest=_digest(material)
    return {"status":"Available",**material,
        "water_balance_event_id":"ROOTLINE-WB-"+digest[:24].upper(),
        "evidence_digest":digest,
        "family_explanation":_explanation(zone_id,effect,effective,remaining),
        "material_notification":effect in {"partial credit","satisfied","Needs Data"}}


def build_learning_proposal(*, current_rule_version, proposed_changes, evidence_ids,
                            rationale, now=None):
    if current_rule_version!=RULE_VERSION or not isinstance(proposed_changes,dict):
        raise ValueError("learning_proposal_invalid")
    material={"contract_version":"rootline_water_balance_learning_proposal.v1",
        "current_rule_version":current_rule_version,"proposed_changes":deepcopy(proposed_changes),
        "evidence_ids":sorted(set(str(x) for x in evidence_ids or [] if str(x))),
        "rationale":str(rationale or ""),"created_at":_aware(now or datetime.now(
            timezone.utc)).isoformat(),"status":"review_required","auto_apply":False,
        "production_policy_changed":False}
    digest=_digest(material)
    return {**material,"proposal_id":"ROOTLINE-WB-PROPOSAL-"+digest[:24].upper(),
        "proposal_sha256":digest}


def append_zone_water_balance(value, database_url):
    if not _valid(value):return {"success":False,"created":False,"status":"invalid_balance"}
    import psycopg
    with psycopg.connect(database_url,connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select public.rootline_append_water_balance_event(%s,%s,%s,%s,%s,%s::jsonb)",
                (value["water_balance_event_id"],value["zone_id"],value["activation_at"],
                 value["complete_through"],value["evidence_digest"],json.dumps(value,
                 sort_keys=True,separators=(",",":"),default=str)))
            created=bool(cursor.fetchone()[0])
    return {"success":True,"created":created,"status":"recorded" if created else "exact_replay",
        "water_balance_event_id":value["water_balance_event_id"]}


def read_latest_zone_water_balances(database_url, *, now=None):
    now=_aware(now or datetime.now(timezone.utc))
    try:
        import psycopg
        with psycopg.connect(database_url,connect_timeout=10) as connection:
            connection.read_only=True
            with connection.cursor() as cursor:
                cursor.execute("""select distinct on (zone_id) balance_json
                    from public.irrigation_water_balance_events
                    where complete_through<=%s order by zone_id,complete_through desc,event_id desc""",(now,))
                rows=cursor.fetchall()
        values={row[0]["zone_id"]:row[0] for row in rows}
        return {"status":"Available","contract_version":CONTRACT,"zones":values,
            "complete_through":max((row["complete_through"] for row in values.values()),default=None)}
    except Exception as exc:
        return {"status":"Unavailable","reason":exc.__class__.__name__,"zones":{}}


def notification_projection(current, previous_evidence_digest=None):
    changed=current.get("evidence_digest")!=previous_evidence_digest
    return {"emit":bool(changed and current.get("material_notification")),
        "message":current.get("family_explanation") if changed else None,
        "unchanged_silent":not changed,"raw_calculations_included":False}


def _rain(value,activation,cutoff):
    row=value if isinstance(value,dict) else {};observed=_time(row.get("observed_at"))
    amount=_number(row.get("rain_mm"));station=str(row.get("station_id") or "")
    coverage_start=_time(row.get("coverage_start"))
    status=("conflicting" if row.get("conflicting") is True else "incomplete"
        if observed is None or amount is None or not station else "outside_activation_boundary"
        if observed<activation or observed>cutoff else "coverage_crosses_activation_boundary"
        if coverage_start is not None and coverage_start<activation else "fresh"
        if row.get("fresh") is True else "stale")
    supported=status=="fresh" and amount>=2.0
    return {"status":status,"station_id":station or None,
        "observed_at":observed.isoformat() if observed else None,
        "coverage_start":coverage_start.isoformat() if coverage_start else None,
        "coverage":row.get("coverage"),
        "observed_mm":max(0.0,amount or 0.0),"credit_supported":supported,
        "trace_hold_threshold_mm":2.0,"confidence":"Provisional" if supported else "Low",
        "source":"observed_local_weather_station","forecast":False}


def _forecast(value):
    row=value if isinstance(value,dict) else {}
    return {"status":row.get("status","Unavailable"),"rain_mm":_number(row.get("rain_mm")),
        "observed_at":row.get("observed_at"),"delivered_water_credit_mm":0.0}


def _irrigation(rows,zone_id,zone,activation,cutoff):
    credited=0.0;items=[];seen={};conflict=False
    for row in rows or []:
        if not isinstance(row,dict) or row.get("zone_id")!=zone_id:
            continue
        identity=str(row.get("execution_id") or "");completed=_time(row.get("completed_at"))
        digest=_digest(row)
        if identity in seen:
            conflict=conflict or seen[identity]!=digest
            continue
        seen[identity]=digest
        runtime=_number(row.get("verified_runtime_minutes"))
        eligible=(bool(identity) and completed is not None and activation<=completed<=cutoff
            and row.get("shutdown_verified") is True and runtime is not None and 0<runtime<=60)
        mm=0.0
        method="none"
        measured=_number(row.get("measured_volume_l"))
        if eligible and measured is not None and measured>=0:
            mm=measured/zone["area_m2"];method="measured_volume_over_area"
        elif eligible:
            mm=runtime/60*NOMINAL_APPLICATION_MM_H;method="layout_derived_runtime_estimate"
        credited+=mm
        items.append({"execution_id":identity,"eligible":eligible,"credited_mm":round(mm,3),
            "method":method,"confidence":"Measured" if measured is not None else "Provisional",
            "flow_inferred":False,"on_receipt_counted":False})
    return {"credited_mm":round(min(SUPPORTED_NEED_MM,credited),3),"outcomes":items,
        "conflicting":conflict,"nominal_application_mm_h":NOMINAL_APPLICATION_MM_H}


def _valid(value):
    if not isinstance(value,dict) or value.get("contract_version")!=CONTRACT:return False
    material={key:item for key,item in value.items() if key not in {
        "status","water_balance_event_id","evidence_digest","family_explanation",
        "material_notification"}}
    digest=_digest(material)
    return (value.get("evidence_digest")==digest and
        value.get("water_balance_event_id")=="ROOTLINE-WB-"+digest[:24].upper())


def _explanation(zone,effect,effective,remaining):
    if effect=="satisfied":return f"Observed rain satisfied {zone}'s current water-equivalent obligation provisionally."
    if effect=="partial credit":return f"Observed rain reduced {zone}'s current obligation; {remaining:.1f} mm remains provisionally."
    if effect=="Needs Data":return f"{zone}'s rain evidence is stale or conflicting, so existing obligation remains unchanged."
    return f"{zone}'s current obligation remains; observed rain did not earn supported water credit."


def _unavailable(zone,reason):return {"status":"Unavailable","zone_id":zone,
    "reason":reason,"contract_version":CONTRACT,"command_authority":False,
    "hardware_control":False}
def _number(value):
    try:return float(value)
    except (TypeError,ValueError):return None
def _time(value):
    try:return _aware(datetime.fromisoformat(str(value).replace("Z","+00:00")))
    except (TypeError,ValueError):return None
def _aware(value):return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
def _digest(value):return sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
