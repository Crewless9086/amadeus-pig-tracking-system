"""Owner shortlist events for Riversdale; not cohort or outlet assignments."""
import hashlib,json,os,uuid

VERSION="riversdale_auction_list_v1"

def _result(ok,status,**extra):
 return {"success":ok,"status":status,"version":VERSION,"creates_cohort":False,
  "creates_outlet_assignment":False,"creates_reservation":False,"books_auction":False,
  "creates_sale":False,"contacts_customer":False,"sends_reminder":False,
  "changes_animal_or_farm_state":False,**extra}

def _factory(url,connect_factory):
 if connect_factory:return lambda:connect_factory(url)
 import psycopg
 return lambda:psycopg.connect(url,connect_timeout=10)

def read_auction_list(*,database_url=None,connect_factory=None):
 url=(database_url if database_url is not None else os.getenv("FARM_SUPABASE_DATABASE_URL","")).strip()
 if not url and connect_factory is None:return _result(False,"auction_list_store_unavailable"),503
 try:
  with _factory(url,connect_factory)() as connection:
   with connection.cursor() as cursor:
    cursor.execute("""with cycle as (
      select auction_cycle_id from public.riversdale_auction_cycles where operating_confirmed
      order by owner_confirmed_at desc limit 1), latest as (
      select distinct on(e.pig_id) e.pig_id,e.event_type,e.owner_note,e.recorded_at
      from public.riversdale_auction_list_events e join cycle c using(auction_cycle_id)
      order by e.pig_id,e.recorded_at desc,e.auction_list_event_id desc)
      select pig_id,owner_note,recorded_at from latest where event_type='added' order by pig_id""")
    rows=cursor.fetchall()
  return _result(True,"available",items=[{"pig_id":r[0],"owner_note":r[1],"listed_at":r[2].isoformat()} for r in rows]),200
 except Exception as exc:return _result(False,"auction_list_store_unavailable",error_type=exc.__class__.__name__),503

def record_auction_list_events(payload,*,actor_id,selectable_ids,current_ids,database_url=None,connect_factory=None):
 payload=payload if isinstance(payload,dict) else {}; actor_id=str(actor_id or "").strip()
 action=str(payload.get("action") or "").strip().lower(); pig_ids=payload.get("pig_ids")
 idem=str(payload.get("idempotency_key") or "").strip(); note=str(payload.get("owner_note") or "").strip()
 if not actor_id:return _result(False,"owner_identity_required"),403
 if action not in {"add","remove"} or not isinstance(pig_ids,list) or not pig_ids or not idem:return _result(False,"invalid_auction_list_event"),400
 ids=sorted({str(x).strip() for x in pig_ids if str(x).strip()})
 allowed=set(selectable_ids if action=="add" else current_ids)
 if not ids or any(x not in allowed for x in ids):return _result(False,"auction_list_selection_not_allowed"),409
 canonical={"version":VERSION,"action":action,"pig_ids":ids,"actor_id":actor_id,"owner_note":note}
 digest=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(",",":")).encode()).hexdigest()
 url=(database_url if database_url is not None else os.getenv("FARM_SUPABASE_DATABASE_URL","")).strip()
 if not url and connect_factory is None:return _result(False,"auction_list_store_unavailable"),503
 try:
  with _factory(url,connect_factory)() as connection:
   with connection.cursor() as cursor:
    cursor.execute("""select auction_cycle_id from public.riversdale_auction_cycles where operating_confirmed
      order by owner_confirmed_at desc limit 1"""); cycle=cursor.fetchone()
    if not cycle:
     connection.rollback()
     return _result(False,"confirmed_auction_cycle_required"),409
    for pig_id in ids:
     key=f"{idem}:{pig_id}"; event_id="RIV-LIST-"+uuid.uuid5(uuid.NAMESPACE_URL,key).hex.upper()
     cursor.execute("""insert into public.riversdale_auction_list_events
      (auction_list_event_id,auction_cycle_id,pig_id,event_type,owner_principal,owner_note,idempotency_key,event_hash)
      values(%s,%s,%s,%s,%s,%s,%s,%s) on conflict(idempotency_key) do nothing returning auction_list_event_id""",
      (event_id,cycle[0],pig_id,"added" if action=="add" else "removed",actor_id,note,key,digest))
     if not cursor.fetchone():
      cursor.execute("select event_hash from public.riversdale_auction_list_events where idempotency_key=%s",(key,))
      existing=cursor.fetchone()
      if not existing or existing[0]!=digest:
       connection.rollback()
       return _result(False,"auction_list_idempotency_conflict"),409
  return _result(True,"auction_list_updated",event_count=len(ids)),201
 except Exception as exc:return _result(False,"auction_list_store_unavailable",error_type=exc.__class__.__name__),503
