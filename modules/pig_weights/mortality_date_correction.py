"""Append-only correction of an already-confirmed mortality effective date."""
from __future__ import annotations
import hashlib,json,os

def mortality_correction_preview_digest(packet):
    bound={key:packet.get(key) for key in ("operation_id","pig_id","supersedes_operation_id",
      "prior_date","corrected_date","actor_reference","owner_evidence","evidence_generation")}
    return hashlib.sha256(json.dumps(bound,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def correct_mortality_effective_date(packet, authority=None, *, connect_factory=None):
    required={"operation_id","pig_id","supersedes_operation_id","prior_date","corrected_date",
              "actor_reference","owner_evidence","evidence_generation","preview_digest"}
    if not isinstance(packet,dict) or required-set(packet):
        return {"success":False,"status":"mortality_correction_packet_invalid","writes_farm_data":False},400
    if str(packet["preview_digest"])!=mortality_correction_preview_digest(packet):
        return {"success":False,"status":"mortality_correction_preview_binding_invalid","writes_farm_data":False},409
    from modules.oom_sakkie.gateway_authority import validates_mortality_correction_authority
    if not validates_mortality_correction_authority(authority,operation_id=packet["operation_id"],
          evidence_generation=packet["evidence_generation"],preview_digest=packet["preview_digest"]):
        return {"success":False,"status":"mortality_correction_authority_denied","writes_farm_data":False},403
    correction_id="MORT-CORR-"+hashlib.sha256(str(packet["operation_id"]).encode()).hexdigest()[:24].upper()
    lifecycle_id="LIFE-CORR-"+hashlib.sha256(str(packet["operation_id"]).encode()).hexdigest()[:24].upper()
    with (connect_factory() if connect_factory else _connect()) as db:
      with db.cursor() as cur:
        cur.execute("""select correction.correction_id,correction.pig_id,
          correction.prior_effective_date,correction.corrected_effective_date,
          correction.owner_evidence,correction.actor_reference,prior.idempotency_key
          from public.pig_lifecycle_corrections correction
          join public.pig_lifecycle_events prior
            on prior.lifecycle_event_id=correction.supersedes_lifecycle_event_id
          where correction.source_operation_id=%s""",
          (packet["operation_id"],))
        existing=cur.fetchone()
        if existing:
            expected_evidence=dict(packet["owner_evidence"]);expected_evidence.update({
              "exact_time":"Unknown","cause":"Unknown","diagnosis":"Unknown","treatment":"Unknown",
              "evidence_generation":packet["evidence_generation"],"preview_digest":packet["preview_digest"]})
            exact=(str(existing[1])==str(packet["pig_id"])
              and str(existing[2])==str(packet["prior_date"])
              and str(existing[3])==str(packet["corrected_date"])
              and existing[4]==expected_evidence
              and str(existing[5])==str(packet["actor_reference"])
              and str(existing[6])==str(packet["supersedes_operation_id"]))
            if not exact:
                return {"success":False,"status":"mortality_correction_idempotency_conflict","writes_farm_data":False},409
            return {"success":True,"status":"mortality_correction_replayed_noop","correction_id":existing[0],
              "corrected_date":str(existing[3]),"rows_changed":0,"writes_farm_data":False},200
        cur.execute("select status,on_farm,exit_date,exit_reason,notes from public.pigs where pig_id=%s for update",(packet["pig_id"],));pig=cur.fetchone()
        if not pig or str(pig[0])!="Dead" or pig[1] is not False or str(pig[2])!=packet["prior_date"] or str(pig[3])!="Died":
            return {"success":False,"status":"mortality_correction_current_state_mismatch","writes_farm_data":False},409
        cur.execute("select lifecycle_event_id,effective_at::date,event_payload from public.pig_lifecycle_events where pig_id=%s and idempotency_key=%s and lifecycle_event_type='exited_farm' for share",(packet["pig_id"],packet["supersedes_operation_id"]));prior=cur.fetchone()
        if not prior or str(prior[1])!=packet["prior_date"]:
            return {"success":False,"status":"mortality_correction_history_mismatch","writes_farm_data":False},409
        evidence=dict(packet["owner_evidence"]);evidence.update({"exact_time":"Unknown","cause":"Unknown",
          "diagnosis":"Unknown","treatment":"Unknown","evidence_generation":packet["evidence_generation"],
          "preview_digest":packet["preview_digest"]})
        cur.execute("""insert into public.pig_lifecycle_corrections(correction_id,pig_id,supersedes_lifecycle_event_id,
          corrected_effective_date,prior_effective_date,correction_reason,owner_evidence,source_operation_id,actor_reference)
          values(%s,%s,%s,%s::date,%s::date,%s,%s::jsonb,%s,%s)""",
          (correction_id,packet["pig_id"],prior[0],packet["corrected_date"],packet["prior_date"],
           "Attributable owner-reported date supersedes intake/provider date",json.dumps(evidence,sort_keys=True),packet["operation_id"],packet["actor_reference"]))
        cur.execute("""insert into public.pig_lifecycle_events(lifecycle_event_id,pig_id,lifecycle_event_type,effective_at,
          actor_reference,source_system,source_reference,event_note,event_payload,idempotency_key,
          supersedes_lifecycle_event_id)
          values(%s,%s,'lifecycle_correction',%s::date::timestamptz,%s,'owner',%s,
          'Correct mortality effective date; preserve original event',%s::jsonb,%s,%s)""",
          (lifecycle_id,packet["pig_id"],packet["corrected_date"],packet["actor_reference"],correction_id,
           json.dumps({"supersedes_lifecycle_event_id":prior[0],"prior_date":packet["prior_date"],
             "corrected_date":packet["corrected_date"],"resulting_status":"Dead","resulting_on_farm":False,
             "owner_evidence":evidence},sort_keys=True),packet["operation_id"],prior[0]))
        note=f"{packet['corrected_date']} governed mortality-date correction {correction_id}; original {prior[0]} preserved."
        cur.execute("update public.pigs set exit_date=%s::date,notes=concat_ws(E'\\n',nullif(notes,''),%s),updated_at=now() where pig_id=%s",(packet["corrected_date"],note,packet["pig_id"]))
    return {"success":True,"status":"mortality_effective_date_corrected","correction_id":correction_id,
      "lifecycle_event_id":lifecycle_id,"pig_id":packet["pig_id"],"corrected_date":packet["corrected_date"],
      "lifecycle_status":"Dead","on_farm":False,"rows_changed":3,"writes_farm_data":True},201

def _connect():
    import psycopg
    return psycopg.connect(os.environ["DATABASE_URL"],connect_timeout=10)
