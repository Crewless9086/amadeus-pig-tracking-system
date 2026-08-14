"""Single-use, exact-preview owner claims for protected Oom Sakkie actions."""
from __future__ import annotations
import hashlib, json, os, secrets, uuid
from datetime import date, datetime, timedelta, timezone
from typing import Mapping

CALLBACK_PREFIX = "oompa:"
MAX_CALLBACK_BYTES = 64

def canonical_preview_digest(kind, payload):
    material={"kind":str(kind),"payload":payload}
    return hashlib.sha256(json.dumps(material,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()

def build_buttons(token, *, grouped=False):
    token=str(token); values=[("Bevestig alles" if grouped else "Bevestig","confirm"),("Verander","change"),("Kanselleer","cancel")]
    rows=[[{"text":label,"callback_data":f"{CALLBACK_PREFIX}{token}:{action}"} for label,action in values]]
    if any(len(button["callback_data"].encode())>MAX_CALLBACK_BYTES for row in rows for button in row):
        raise ValueError("protected callback exceeds Telegram limit")
    return {"inline_keyboard":rows}

def create_claim(*, action_kind, owner_user_id, private_chat_id, mission_id,
                 provider_message_id, evidence_generation, preview_payload,
                 ttl_minutes=30, connect_factory=None):
    digest=canonical_preview_digest(action_kind,preview_payload)
    token=secrets.token_urlsafe(12).replace("-","").replace("_","")[:16]
    expires=datetime.now(timezone.utc)+timedelta(minutes=ttl_minutes)
    with (connect_factory() if connect_factory else _connect()) as db:
      with db.cursor() as cur:
        cur.execute("""select callback_token,status,expires_at,owner_user_id,private_chat_id,
          provider_message_id,evidence_generation,preview_payload,preview_card_message_id
          from app_private.oom_protected_action_claims
          where action_kind=%s and mission_id=%s and preview_digest=%s""",
          (action_kind,mission_id,digest))
        prior=cur.fetchone()
        if prior:
            exact=(str(prior[3])==str(owner_user_id) and str(prior[4])==str(private_chat_id)
              and str(prior[5])==str(provider_message_id) and str(prior[6])==str(evidence_generation)
              and prior[7]==preview_payload)
            if prior[1]=="active" and prior[2]>datetime.now(timezone.utc) and exact:
                return {"success":True,"status":"protected_claim_existing","callback_token":prior[0],
                  "preview_digest":digest,"expires_at":prior[2].isoformat(),
                  "preview_card_message_id":str(prior[8] or "")}
            raise RuntimeError("protected_claim_identity_or_state_conflict")
        cur.execute("""update app_private.oom_protected_action_claims set status='changed'
          where mission_id=%s and status='active'""",(mission_id,))
        cur.execute("""insert into app_private.oom_protected_action_claims(
          callback_token,action_kind,owner_user_id,private_chat_id,mission_id,provider_message_id,
          preview_digest,evidence_generation,preview_payload,expires_at)
          values(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",
          (token,action_kind,owner_user_id,private_chat_id,mission_id,provider_message_id,
           digest,evidence_generation,json.dumps(preview_payload,sort_keys=True),expires))
    return {"success":True,"status":"protected_claim_created","callback_token":token,"preview_digest":digest,"expires_at":expires.isoformat()}

def resolve_natural_confirmation(*, owner_user_id, private_chat_id, reply_to_message_id="", connect_factory=None):
    with (connect_factory() if connect_factory else _connect()) as db:
      db.read_only=True
      with db.cursor() as cur:
        cur.execute("""select callback_token,mission_id,preview_payload,preview_card_message_id from app_private.oom_protected_action_claims
          where owner_user_id=%s and private_chat_id=%s and status='active' and expires_at>now()
          and preview_card_message_id is not null
          order by created_at desc limit 2""",(owner_user_id,private_chat_id))
        rows=cur.fetchall()
    reply=str(reply_to_message_id or "")
    if reply:rows=[row for row in rows if str(row[3] or "")==reply]
    if len(rows)!=1:return None
    return {"callback_token":rows[0][0],"mission_id":rows[0][1],"preview_payload":rows[0][2]}

def bind_claim_card(token, card_message_id, *, connect_factory=None):
    with (connect_factory() if connect_factory else _connect()) as db:
      with db.cursor() as cur:
        cur.execute("""update app_private.oom_protected_action_claims set preview_card_message_id=%s
          where callback_token=%s and status='active'
          and (preview_card_message_id is null or preview_card_message_id=%s)""",
          (str(card_message_id),str(token),str(card_message_id)))
        return cur.rowcount==1

def claim_callback(callback_data, *, owner_user_id, private_chat_id, provider_message_id,
                   provider_timestamp, source_card_message_id="", connect_factory=None):
    data=str(callback_data or "")
    try:
        provider_time=datetime.fromisoformat(str(provider_timestamp or "").replace("Z","+00:00"))
    except ValueError:
        provider_time=None
    if not str(provider_message_id or "").strip() or provider_time is None or provider_time.tzinfo is None:
        return {"success":False,"status":"protected_callback_provider_identity_required"},409
    if not data.startswith(CALLBACK_PREFIX) or data.count(":")!=2:return {"success":False,"status":"protected_callback_invalid"},400
    _,token,action=data.split(":")
    if action not in {"confirm","change","cancel"}:return {"success":False,"status":"protected_callback_invalid"},400
    with (connect_factory() if connect_factory else _connect()) as db:
      with db.cursor() as cur:
        cur.execute("select action_kind,owner_user_id,private_chat_id,mission_id,preview_digest,evidence_generation,preview_payload,status,expires_at,result_payload,preview_card_message_id from app_private.oom_protected_action_claims where callback_token=%s for update",(token,))
        row=cur.fetchone()
        if not row:return {"success":False,"status":"protected_callback_unknown"},404
        if str(row[1])!=str(owner_user_id) or str(row[2])!=str(private_chat_id):return {"success":False,"status":"protected_callback_unauthorized"},403
        if not row[10]:
            return {"success":False,"status":"protected_callback_card_unbound"},409
        if str(row[10])!=str(source_card_message_id or ""):
            return {"success":False,"status":"protected_callback_card_mismatch"},409
        if row[7]=="completed":
            if row[0]=="rootline_irrigation_segment":
                return {"success":True,"status":"protected_callback_completed_delivery_retry",
                  "action_kind":row[0],"mission_id":row[3],"preview_digest":row[4],
                  "result":row[9],"telegram_sends":0,"telegram_edits":0},200
            return {"success":True,"status":"protected_callback_replayed_noop","result":row[9],"telegram_sends":0,"telegram_edits":0},200
        if row[7]=="executing":
            if action!="confirm":
                return {"success":False,"status":"protected_callback_stale"},409
            cur.execute("""select confirmation_provider_message_id,
              confirmation_provider_timestamp from app_private.oom_protected_action_claims
              where callback_token=%s""",(token,))
            confirmation=cur.fetchone()
            # Telegram callback-query IDs are the stable provider receipt across
            # webhook retries; the gateway receipt timestamp is process-local.
            exact_confirmation=(confirmation and
              str(confirmation[0] or "")==str(provider_message_id) and
              confirmation[1] is not None)
            if not exact_confirmation:
                return {"success":False,"status":"protected_callback_stale"},409
            return {"success":True,"status":"protected_callback_recovered",
              "callback_token":token,"action_kind":row[0],"mission_id":row[3],
              "preview_digest":row[4],"evidence_generation":row[5],
              "preview_payload":row[6],"recovered_executing_receipt":True},200
        if row[7]!="active":return {"success":False,"status":"protected_callback_stale"},409
        if row[8]<=datetime.now(timezone.utc):
            cur.execute("update app_private.oom_protected_action_claims set status='expired' where callback_token=%s",(token,))
            return {"success":False,"status":"protected_callback_expired"},409
        if action in {"change","cancel"}:
            cur.execute("update app_private.oom_protected_action_claims set status=%s,confirmation_provider_message_id=%s,confirmation_provider_timestamp=%s::timestamptz where callback_token=%s",("changed" if action=="change" else "cancelled",provider_message_id,provider_timestamp,token))
            return {"success":True,"status":"protected_preview_change_requested" if action=="change" else "protected_preview_cancelled","mission_id":row[3]},200
        cur.execute("update app_private.oom_protected_action_claims set status='executing',confirmation_provider_message_id=%s,confirmation_provider_timestamp=%s::timestamptz where callback_token=%s and status='active'",(provider_message_id,provider_timestamp,token))
        return {"success":True,"status":"protected_callback_claimed","callback_token":token,"action_kind":row[0],"mission_id":row[3],"preview_digest":row[4],"evidence_generation":row[5],"preview_payload":row[6]},200

def complete_claim(token, result, *, connect_factory=None):
    with (connect_factory() if connect_factory else _connect()) as db:
      with db.cursor() as cur:
        cur.execute("""select status,result_payload from app_private.oom_protected_action_claims
          where callback_token=%s for update""",(token,))
        prior=cur.fetchone()
        if not prior:raise RuntimeError("protected claim missing")
        if prior[0]=="completed":
            return {"completed":False,"replayed":True,"result":prior[1]}
        if prior[0]!="executing":raise RuntimeError("protected claim not executing")
        cur.execute("update app_private.oom_protected_action_claims set status='completed',result_payload=%s::jsonb,completed_at=now() where callback_token=%s and status='executing'",(json.dumps(result,sort_keys=True,default=str),token))
        if cur.rowcount!=1:raise RuntimeError("protected claim not executing")
        return {"completed":True,"replayed":False,"result":result}

def contain_claim(token, result, *, connect_factory=None):
    """Retain a claimed confirmation and its exact failure for governed recovery."""
    with (connect_factory() if connect_factory else _connect()) as db:
      with db.cursor() as cur:
        cur.execute("""update app_private.oom_protected_action_claims
          set status='contained',result_payload=%s::jsonb,completed_at=now()
          where callback_token=%s and status='executing'""",
          (json.dumps(result,sort_keys=True,default=str),token))

def contain_unbound_preview_claim(token, result, *, connect_factory=None):
    """Contain a preview whose provider card was never durably bound."""
    with (connect_factory() if connect_factory else _connect()) as db:
      with db.cursor() as cur:
        cur.execute("""update app_private.oom_protected_action_claims
          set status='contained',result_payload=%s::jsonb,completed_at=now()
          where callback_token=%s and status='active'
          and preview_card_message_id is null""",
          (json.dumps(result,sort_keys=True,default=str),token))
        return cur.rowcount==1

def execute_grouped_weight_claim(claim, *, actor_id, connect_factory=None):
    """Atomically apply exactly the rows and movements bound into one claim."""
    payload=claim.get("preview_payload") if isinstance(claim.get("preview_payload"),Mapping) else {}
    rows=payload.get("rows") if isinstance(payload.get("rows"),list) else []
    canonical_contract=(payload.get("contract_version")=="canonical_grouped_weight_movement_preview_v1"
        and payload.get("confirmation_required") is True)
    legacy_contract=(payload.get("contract_version")=="herdmaster_telegram_grouped_weight_preview_v1"
        and len(rows)==int(payload.get("row_count") or 0))
    weight_date=str(payload.get("effective_date") if canonical_contract else payload.get("weight_date") or "")
    digest=canonical_preview_digest("grouped_weights",payload)
    try: date.fromisoformat(weight_date)
    except ValueError: weight_date=""
    if not (canonical_contract or legacy_contract) or not rows or not weight_date or digest!=claim.get("preview_digest"):
        result={"success":False,"status":"protected_preview_binding_mismatch","writes_farm_data":False}
        contain_claim(claim["callback_token"],result,connect_factory=connect_factory)
        return result,409
    batch_id=str(uuid.uuid4())
    with (connect_factory() if connect_factory else _connect()) as db:
      with db.cursor() as cur:
        cur.execute("set transaction isolation level serializable")
        cur.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",("oom-protected:"+str(claim["callback_token"]),))
        cur.execute("""select status,result_payload from app_private.oom_protected_action_claims
          where callback_token=%s for update""",(claim["callback_token"],))
        durable_claim=cur.fetchone()
        if not durable_claim:
            raise RuntimeError("protected claim missing during execution")
        if durable_claim[0]=="completed":
            prior=durable_claim[1] if isinstance(durable_claim[1],Mapping) else {}
            return {**prior,"success":True,"status":"grouped_weights_replayed_noop",
                "writes_farm_data":False,"telegram_sends":0,"telegram_edits":0},200
        if durable_claim[0]!="executing":
            raise RuntimeError("protected claim lost execution ownership")
        for pig_id in sorted(str(row["pig_id"]) for row in rows):
            cur.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",("oom-protected-pig:"+pig_id,))
        for row in rows:
            cur.execute("""select status,on_farm,current_pen_id from public.current_canonical_pig_state
              where pig_id=%s""",(row["pig_id"],)); current=cur.fetchone()
            expected_pen="" if row.get("current_pen_id")=="Unknown" else str(row.get("current_pen_id") or "")
            if (not current or str(current[0]).casefold()!="active" or current[1] is not True
                    or str(current[2] or "")!=expected_pen):
                result={"success":False,"status":"protected_row_changed_repreview_required","writes_farm_data":False}
                cur.execute("""update app_private.oom_protected_action_claims set status='contained',
                  result_payload=%s::jsonb,completed_at=now() where callback_token=%s and status='executing'""",
                  (json.dumps(result,sort_keys=True),claim["callback_token"]))
                return result,409
            destination_pen=_movement_destination(row)
            if destination_pen:
                cur.execute("select 1 from public.pens where pen_id=%s and is_active is true for share",(destination_pen,))
                if not cur.fetchone():
                    result={"success":False,"status":"protected_destination_changed_repreview_required","writes_farm_data":False}
                    cur.execute("""update app_private.oom_protected_action_claims set status='contained',
                      result_payload=%s::jsonb,completed_at=now() where callback_token=%s and status='executing'""",
                      (json.dumps(result,sort_keys=True),claim["callback_token"]))
                    return result,409
            cur.execute("select 1 from public.pig_weight_events where pig_id=%s and weight_date=%s::date",(row["pig_id"],weight_date))
            if cur.fetchone():
                result={"success":False,"status":"protected_weight_already_exists","writes_farm_data":False}
                cur.execute("""update app_private.oom_protected_action_claims set status='contained',
                  result_payload=%s::jsonb,completed_at=now() where callback_token=%s and status='executing'""",
                  (json.dumps(result,sort_keys=True),claim["callback_token"]))
                return result,409
        movement_count=sum(_movement_destination(r)!=_current_pen(r) and bool(_movement_destination(r)) for r in rows)
        cur.execute("""insert into public.bulk_weight_batches(batch_id,client_draft_id,weight_date,status,
          visible_row_count,actionable_row_count,weight_row_count,movement_row_count,skipped_row_count,
          success_count,failed_count,duplicate_count,source,notes,error_summary,payload_summary_json,completed_at)
          values(%s::uuid,%s,%s::date,'complete',%s,%s,%s,%s,0,%s,0,0,'oom_sakkie_protected',%s,'',%s::jsonb,now())""",
          (batch_id,claim["preview_digest"],weight_date,len(rows),len(rows),len(rows),movement_count,len(rows),
           "Exact owner-confirmed grouped preview",json.dumps({"preview_digest":claim["preview_digest"],"row_count":len(rows)},sort_keys=True)))
        results=[]
        for index,row in enumerate(rows):
            row_id=str(uuid.uuid4()); weight_event="WGT-"+secrets.token_hex(4).upper()
            current_pen=_current_pen(row); destination_pen=_movement_destination(row)
            moved=bool(destination_pen and destination_pen!=current_pen)
            original={**row,"weight_date":weight_date,"preview_digest":claim["preview_digest"]}
            cur.execute("""insert into public.bulk_weight_batch_rows(row_id,batch_id,row_index,pig_id,pig_name,
              weight_kg,from_pen_id,to_pen_id,movement_type,status,status_reason,processed_at,result_json,
              original_row_json,idempotency_key) values(%s::uuid,%s::uuid,%s,%s,%s,%s,%s,%s,%s,'success',
              'Exact protected preview recorded.',now(),%s::jsonb,%s::jsonb,%s)""",
              (row_id,batch_id,index,row["pig_id"],row.get("tag_number") or row.get("label"),row["weight_kg"],
               current_pen or None,destination_pen or None,"pen_change" if moved else "",
               json.dumps({"has_weight":True,"has_pen_change":moved,"preview_digest":claim["preview_digest"]},sort_keys=True),
               json.dumps(original,sort_keys=True),f"{claim['preview_digest']}:{index}"))
            cur.execute("""insert into public.pig_weight_events(weight_event_id,pig_id,weight_date,weight_kg,
              weighed_by,source,bulk_batch_id,bulk_row_id) values(%s,%s,%s::date,%s,%s,'oom_sakkie_protected',%s::uuid,%s::uuid)""",
              (weight_event,row["pig_id"],weight_date,row["weight_kg"],actor_id,batch_id,row_id))
            if moved:
                move_event="MOV-"+secrets.token_hex(4).upper()
                cur.execute("""insert into public.pig_location_events(location_event_id,pig_id,move_date,from_pen_id,to_pen_id,
                  reason_for_move,moved_by,move_notes,source,bulk_batch_id,bulk_row_id)
                  values(%s,%s,%s::date,%s,%s,'Moved during exact protected grouped weight confirmation',%s,'','oom_sakkie_protected',%s::uuid,%s::uuid)""",
                  (move_event,row["pig_id"],weight_date,current_pen or None,destination_pen,actor_id,batch_id,row_id))
            results.append({"pig_id":row["pig_id"],"weight_kg":row["weight_kg"],"moved_to_pen_id":destination_pen})
        result={"success":True,"status":"grouped_weights_completed","batch_id":batch_id,"row_count":len(rows),
                "movement_count":movement_count,"rows":results,"writes_farm_data":True}
        cur.execute("""update app_private.oom_protected_action_claims set status='completed',result_payload=%s::jsonb,
          completed_at=now() where callback_token=%s and status='executing'""",
          (json.dumps(result,sort_keys=True),claim["callback_token"]))
        if cur.rowcount!=1:raise RuntimeError("protected claim lost execution ownership")
    return result,201

def _current_pen(row):
    value=row.get("current_pen_id")
    return "" if value in (None,"","Unknown") else str(value)

def _movement_destination(row):
    value=row.get("moved_to_pen_id")
    return "" if value in (None,"","Unknown") else str(value)

def _connect():
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    return connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
                                             read_only=False)
