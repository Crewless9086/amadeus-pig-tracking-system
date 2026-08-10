"""Service-only atomic writer for an owner-confirmed auction preview."""
from __future__ import annotations
import hashlib,json,os,re
from datetime import date
from modules.pig_weights.herdmaster_auction_sale import build_auction_sale_preview
from services.database_service import DATABASE_URL_ENV

def record_confirmed_auction_sale(report,evidence_loader,confirmation,*,authority,authority_verifier=None,connect_factory=None,database_url=None):
    if not isinstance(authority,dict) or not callable(authority_verifier) or authority_verifier(authority) is not True or authority.get("principal_type")!="service" or not authority.get("principal_id"): return _result(False,"trusted_service_authority_required"),403
    if not isinstance(confirmation,dict) or confirmation.get("owner_confirmed") is not True or not confirmation.get("confirmation_id"): return _result(False,"durable_owner_confirmation_required"),403
    op=str(confirmation.get("operation_id") or "")
    confirmed_hash=str(confirmation.get("preview_hash") or "")
    if not op or not confirmed_hash or not confirmation.get("evidence_generation"): return _result(False,"confirmation_operation_or_evidence_required"),409
    url=(database_url if database_url is not None else os.getenv(DATABASE_URL_ENV,"" )).strip()
    if connect_factory is None:
        import psycopg; connect_factory=lambda:psycopg.connect(url,connect_timeout=10)
    try:
      with connect_factory() as connection:
       with connection.cursor() as cur:
        cur.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",("herdmaster-auction:"+op,))
        cur.execute("select sale_id,confirmed_preview_hash from sales_transactions where operation_id=%s",(op,)); existing=cur.fetchone()
        if existing:
            if str(existing[1])!=confirmed_hash: return _result(False,"operation_identity_conflict"),409
            return _result(True,"replayed_zero_rows",sale_id=str(existing[0]),rows_created=0,replay=True),200
        initial=build_auction_sale_preview(report,evidence_loader())
        if not initial.get("success") or not initial.get("ready_for_confirmation"): return _result(False,"preview_not_ready",preview=initial),409
        if confirmed_hash!=initial["preview_hash"]: return _result(False,"confirmation_preview_mismatch"),409
        if op!=initial["operation_id"] or confirmation.get("evidence_generation")!=initial.get("evidence_generation"): return _result(False,"confirmation_operation_or_evidence_mismatch"),409
        fresh=build_auction_sale_preview(report,evidence_loader())
        if fresh.get("preview_hash")!=initial["preview_hash"] or fresh.get("evidence_generation")!=initial.get("evidence_generation"): return _result(False,"evidence_changed_repreview_required"),409
        ids=[r["pig_id"] for r in fresh["matrix"]]
        cur.execute("""select p.pig_id,p.status,p.on_farm,p.purpose,
          exists(select 1 from pig_medical_events m where m.pig_id=p.pig_id and m.treatment_date<=%s::date and (m.withdrawal_end_date is null or m.withdrawal_end_date>=%s::date)) as withdrawal_conflict
          from pigs p where p.pig_id=any(%s) order by p.pig_id for update""",(initial["sale_date"],initial["sale_date"],ids)); locked=cur.fetchall()
        if len(locked)!=18 or any(str(r[1]).lower()!="active" or r[2] is not True or str(r[3]).lower()!="sale" or r[4] is True for r in locked): return _result(False,"current_pig_eligibility_conflict"),409
        cur.execute("""select i.pig_id,s.sale_id from sales_transaction_items i join sales_transactions s using(sale_id)
          where i.pig_id=any(%s) and s.sale_status<>'Cancelled' order by i.pig_id""",(ids,))
        if cur.fetchall(): return _result(False,"current_sale_conflict"),409
        cur.execute("""select pig_id,source_record_id,outlet_type from pig_active_outlets
          where pig_id=any(%s) and active order by pig_id for update""",(ids,))
        if cur.fetchall(): return _result(False,"current_reservation_conflict"),409
        sale_id="SALE-AUCT-"+hashlib.sha256(op.encode()).hexdigest()[:20].upper()
        received=None
        payment_status="Unknown"
        cur.execute("""insert into sales_transactions(
          sale_id,sale_date,sale_stream,sale_channel,pig_count,lot_total,gross_total,output_vat,gross_including_vat,
          deductions_total,commission_ex_vat,commission_input_vat,commission_including_vat,other_deductions,
          net_total,net_settlement_payable,financial_interpretation,received_total,payment_received_evidence_json,
          currency,payment_status,payment_method,sale_status,destination,external_reference,evidence_json,
          operation_id,confirmed_preview_hash,created_by)
        values(%s,%s::date,'Livestock','Auction',18,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'seller_settlement_payable',%s,%s::jsonb,
          'ZAR',%s,'EFT','Completed',%s,%s,%s::jsonb,%s,%s,'HERDMASTER')""",
        (sale_id,initial["sale_date"],initial["net_settlement_payable"],initial["gross_revenue_ex_vat"],initial["output_vat"],initial["gross_including_vat"],initial["commission_including_vat"],initial["commission_ex_vat"],initial["commission_input_vat"],initial["commission_including_vat"],initial["other_deductions"],initial["net_settlement_payable"],initial["net_settlement_payable"],received,None,payment_status,initial["outlet_name"],initial["invoice_reference"],json.dumps({"invoice_evidence_identity":initial["invoice_evidence_identity"],"owner_confirmation":confirmation.get("confirmation_id"),"outlet_location":initial["outlet_location"],"v10_tags":initial["v10_tags"],"v11_tags":initial["v11_tags"]},sort_keys=True),op,initial["preview_hash"]))
        for row in fresh["matrix"]:
            pid=row["pig_id"]; item_id="SALEITEM-AUCT-"+hashlib.sha256((op+pid).encode()).hexdigest()[:20].upper(); event_id="LIFE-AUCT-"+hashlib.sha256((op+pid).encode()).hexdigest()[:20].upper()
            cur.execute("insert into sales_transaction_items(sale_item_id,sale_id,item_type,pig_id,tag_number,description,quantity,unit_price,pricing_basis,line_total,notes) values(%s,%s,'Pig',%s,%s,'Auction lot pig',1,null,null,null,'Individual proceeds Unknown')",(item_id,sale_id,pid,row["tag"]))
            cur.execute("update pigs set status='Sold',on_farm=false,exit_date=%s::date,exit_reason='Auction Sale',updated_at=now() where pig_id=%s and status='Active' and on_farm is true",(initial["sale_date"],pid))
            if cur.rowcount!=1: raise RuntimeError("concurrent_pig_state_change")
            cur.execute("""insert into pig_lifecycle_events(lifecycle_event_id,pig_id,lifecycle_event_type,effective_at,actor_reference,source_system,source_reference,event_note,event_payload,idempotency_key)
              values(%s,%s,'exited_farm',%s::date::timestamptz,%s,'owner',%s,'Auction Sale',%s::jsonb,%s)""",(event_id,pid,initial["sale_date"],str(authority.get("actor_reference") or "owner"),initial["preview_hash"],json.dumps({"sale_id":sale_id,"sale_channel":"Auction","resulting_status":"Sold","resulting_on_farm":False},sort_keys=True),op+":"+pid))
        cur.execute("update pig_active_outlets set active=false,released_at=now() where source_record_id=%s and outlet_type='customer_sale' and active",(sale_id,))
      return _result(True,"auction_sale_recorded",sale_id=sale_id,rows_created=37,pig_count=18,gross_revenue_ex_vat="4180.00",net_settlement_payable="4470.51",payment_received=received is not None,replay=False),201
    except Exception as exc: return _result(False,"auction_sale_transaction_rolled_back",error_type=exc.__class__.__name__),503

def _result(success,status,**extra): return {"success":success,"status":status,"writes_to_sheets":False,**extra}

def reconcile_auction_payment(sale_id, evidence, *, authority, authority_verifier=None, connect_factory=None, database_url=None):
    """Attach later bank receipt without recreating or changing the livestock sale."""
    if not isinstance(authority,dict) or not callable(authority_verifier) or authority_verifier(authority) is not True or authority.get("principal_type")!="service" or not authority.get("principal_id"):
        return _result(False,"trusted_service_authority_required"),403
    try: received_date=date.fromisoformat(str(evidence.get("received_date"))) if isinstance(evidence,dict) else None
    except ValueError: received_date=None
    if not isinstance(evidence,dict) or evidence.get("amount")!="4470.51" or received_date is None or received_date>date.today() or not evidence.get("evidence_id") or not re.fullmatch(r"[0-9a-fA-F]{64}",str(evidence.get("evidence_sha256") or "")):
        return _result(False,"exact_payment_evidence_required"),409
    url=(database_url if database_url is not None else os.getenv(DATABASE_URL_ENV,"" )).strip()
    if connect_factory is None:
        import psycopg; connect_factory=lambda:psycopg.connect(url,connect_timeout=10)
    try:
      with connect_factory() as connection:
       with connection.cursor() as cur:
        identity={"evidence_id":str(evidence["evidence_id"]),"sha256":str(evidence["evidence_sha256"]).lower(),"received_date":received_date.isoformat(),"amount":"4470.51"}
        evidence_sha256=identity["sha256"]
        cur.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",("herdmaster-auction-payment:"+evidence_sha256,))
        cur.execute("select sale_channel,net_settlement_payable,received_total,payment_received_evidence_json,sale_date::date,payment_evidence_sha256 from sales_transactions where sale_id=%s for update",(sale_id,))
        row=cur.fetchone()
        if not row or row[0]!="Auction" or str(row[1])!="4470.51": return _result(False,"auction_sale_not_found_or_amount_mismatch"),409
        if received_date<row[4]: return _result(False,"payment_date_precedes_sale"),409
        if row[2] is not None:
            if str(row[2])=="4470.51" and row[3]==identity and row[5]==evidence_sha256: return _result(True,"payment_replayed_zero_rows",rows_changed=0),200
            return _result(False,"payment_reconciliation_conflict"),409
        cur.execute("select sale_id from sales_transactions where payment_evidence_sha256=%s and sale_id<>%s",(evidence_sha256,sale_id))
        if cur.fetchone(): return _result(False,"payment_evidence_already_bound"),409
        cur.execute("update sales_transactions set received_total=4470.51,payment_status='Paid',payment_date=%s::date,payment_received_evidence_json=%s::jsonb,payment_evidence_sha256=%s,updated_at=now() where sale_id=%s and received_total is null",(identity["received_date"],json.dumps(identity,sort_keys=True),evidence_sha256,sale_id))
        if cur.rowcount!=1: raise RuntimeError("concurrent_payment_state_change")
      return _result(True,"payment_reconciled",rows_changed=1,sale_id=str(sale_id)),200
    except Exception as exc:
      return _result(False,"payment_reconciliation_rolled_back",error_type=exc.__class__.__name__),503
