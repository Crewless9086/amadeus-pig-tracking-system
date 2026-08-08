"""Pure, zero-I/O reconciliation and preview for completed livestock auction lots."""
from __future__ import annotations

import hashlib, json, re, unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

CONTRACT_VERSION="herdmaster_auction_sale_v1"
FINANCIAL_INTERPRETATIONS={"gross_proceeds","net_proceeds","money_received","unknown"}

def build_auction_sale_preview(report, evidence):
    if not isinstance(report,dict) or not isinstance(evidence,dict): return _fail("typed_report_and_evidence_required")
    tags=[_tag(v) for v in report.get("tags",[]) if _tag(v)]
    if len(tags)!=18 or len(set(tags))!=18: return _fail("exactly_18_unique_tags_required")
    try: lot=Decimal(str(report.get("lot_total"))).quantize(Decimal("0.01"))
    except (InvalidOperation,ValueError,TypeError): return _fail("valid_lot_total_required")
    if lot!=Decimal("4470.51"): return _fail("owner_reported_lot_total_mismatch")
    rows=evidence.get("pigs") if isinstance(evidence.get("pigs"),list) else []
    if not all(isinstance(r,dict) for r in rows): return _fail("canonical_pig_rows_required")
    matrix=[]; conflicts=[]
    for tag in tags:
        matches=[r for r in rows if _tag(r.get("tag_number"))==tag]
        if len(matches)!=1:
            conflicts.append({"tag":tag,"reason":"unresolved" if not matches else "duplicate_identity"}); continue
        pig=matches[0]; reasons=[]
        if not _text(pig.get("pig_id")): reasons.append("canonical_pig_id_missing")
        if _norm(pig.get("status"))!="active" or pig.get("on_farm") is not True: reasons.append("not_currently_active_on_farm")
        if _norm(pig.get("purpose"))!="sale": reasons.append("sale_purpose_not_proven")
        if _norm(pig.get("availability_state"))!="available": reasons.append("availability_not_proven")
        if _norm(pig.get("reservation_order_state")) not in {"none","clear","unreserved"}: reasons.append("reservation_or_order_clearance_not_proven")
        if pig.get("active_reservation") is not False or pig.get("active_order") is not False: reasons.append("reserved_or_ordered_elsewhere_or_unknown")
        if pig.get("prior_sale") is not False or _norm(pig.get("prior_sale_state")) not in {"none","clear"}: reasons.append("prior_sale_clearance_not_proven")
        if _norm(pig.get("withdrawal_state")) not in {"explicitly_cleared","complete_through_no_active_withdrawal"}: reasons.append("withdrawal_or_medical_clearance_not_proven")
        matrix.append({"tag":tag,"pig_id":_text(pig.get("pig_id")),"status":_text(pig.get("status")),"on_farm":pig.get("on_farm"),"purpose":_known(pig.get("purpose")),"pen":_known(pig.get("current_pen_name")),"availability":_known(pig.get("availability_state")),"reservation_order":_known(pig.get("reservation_order_state")),"withdrawal_medical":_known(pig.get("withdrawal_state")),"identity_conflict":False,"eligible":not reasons,"conflicts":reasons})
        conflicts.extend({"tag":tag,"pig_id":pig.get("pig_id"),"reason":reason} for reason in reasons)
    ids=[r["pig_id"] for r in matrix]
    if len(ids)!=len(set(ids)): conflicts.append({"reason":"duplicate_canonical_pig"})
    interpretation=_norm(report.get("financial_interpretation") or "unknown")
    if interpretation not in FINANCIAL_INTERPRETATIONS: conflicts.append({"reason":"invalid_financial_interpretation"})
    missing=[]
    for field,label in (("sale_date","actual auction/exit date"),("outlet_name","auction house/outlet"),("invoice_reference","invoice/reference number")):
        if _unknown(report.get(field)): missing.append(label)
    for field,limit in (("outlet_name",160),("invoice_reference",160),("payment_method",80)):
        if len(_text(report.get(field)))>limit: conflicts.append({"reason":field+"_too_long"})
    sale_date=_date(report.get("sale_date"))
    if _text(report.get("sale_date")) and (sale_date is None or sale_date>date.today()): conflicts.append({"reason":"sale_date_invalid_or_future"})
    if interpretation=="unknown": missing.append("whether R4,470.51 is gross proceeds, net proceeds, or money received")
    payment=_text(report.get("payment_status"))
    if not payment: missing.append("payment status/method only if the invoice does not prove it")
    elif payment not in {"Unknown","Unpaid","Deposit_Paid","Part_Paid","Paid","Cancelled"}: conflicts.append({"reason":"unsupported_payment_status"})
    normalized={"sale_date":sale_date.isoformat() if sale_date else "Unknown","outlet_name":_public(report.get("outlet_name")) if not _unknown(report.get("outlet_name")) else "Unknown","invoice_reference":_public(report.get("invoice_reference")) if not _unknown(report.get("invoice_reference")) else "Unknown","payment_status":payment or "Unknown","payment_method":_public(report.get("payment_method")) or "Unknown"}
    invoice_identity=_invoice_identity(report.get("invoice_evidence"))
    if invoice_identity is None: conflicts.append({"reason":"invoice_evidence_identity_invalid"}); invoice_identity={"status":"invalid","evidence_id":"Unknown","sha256":"Unknown"}
    question=None if not missing else "Please provide " + "; ".join(missing) + "."
    payload={"success":not conflicts,"contract_version":CONTRACT_VERSION,"evidence_generation":evidence.get("evidence_generation"),"tags":tags,"pig_count":len(matrix),"matrix":matrix,"lot_total":"4470.51","currency":"ZAR","sale_stream":"Livestock","sale_channel":"Auction","financial_interpretation":interpretation,"gross_total":"4470.51" if interpretation=="gross_proceeds" else "Unknown","net_total":"4470.51" if interpretation=="net_proceeds" else "Unknown","received_total":"4470.51" if interpretation=="money_received" else "Unknown","deductions_total":"Unknown","individual_proceeds":"Unknown","invoice_evidence_identity":invoice_identity,**normalized,"missing_facts":missing,"conflicts":conflicts,"ready_for_confirmation":not conflicts and not missing,"grouped_question":question,"proposed_effects":["one completed Livestock/Auction sale","18 linked pig items with individual prices Unknown","each pig Sold and off-farm with Auction Sale exit","18 immutable exited-farm lifecycle events","release only the sale's own availability projection","preserve all historical animal records","include the exact lot total in monthly livestock reporting without claiming receipt unless proven"],"delivery_enabled":False,"write_enabled":False,"mating_execution_enabled":False,"customer_contact_enabled":False}
    payload["operation_id"]="HERD-AUCTION-"+_digest({"tags":sorted(tags),"lot_total":"4470.51",**normalized})[:32].upper()
    payload["english"]=_render(payload,"en"); payload["afrikaans"]=_render(payload,"af")
    payload["preview_hash"]="AUCT-PREVIEW-"+_digest(payload)[:32].upper()
    return payload

def _render(p,lang):
    tags=", ".join(r["tag"] for r in p["matrix"])
    effects="; ".join(p["proposed_effects"])
    if lang=="af":
        interpretation={"gross_proceeds":"bruto opbrengs","net_proceeds":"netto opbrengs","money_received":"geld ontvang","unknown":"Onbekend"}.get(p["financial_interpretation"],"Onbekend")
        af_effects="een voltooide Lewendehawe/Veiling-verkoping; 18 gekoppelde varkitems met individuele pryse Onbekend; elke vark Verkoop en van die plaas af met Veilingverkoping as uitgang; 18 onveranderlike plaasverlatingsgebeure; stel slegs die verkoping se eie beskikbaarheidsprojeksie vry; behou alle historiese diererekords; sluit die presiese lottotaal by maandelikse lewendehaweverslagdoening in sonder om ontvangs te beweer tensy dit bewys is"
        af=lambda value: "Onbekend" if value=="Unknown" else value
        payment={"Unknown":"Onbekend","Unpaid":"Onbetaald","Deposit_Paid":"Deposito betaal","Part_Paid":"Gedeeltelik betaal","Paid":"Betaal","Cancelled":"Gekanselleer"}.get(p["payment_status"],p["payment_status"])
        return f"Veilingverkoping: {len(p['matrix'])} varke ({tags}). Datum {p['sale_date']}; veiling {p['outlet_name']}; faktuur {p['invoice_reference']}; faktuurbewys {af(p['invoice_evidence_identity']['evidence_id'])}. Lottotaal R4 470,51; betekenis {interpretation}; bruto {af(p['gross_total'])}; netto {af(p['net_total'])}; ontvang {af(p['received_total'])}; aftrekkings Onbekend; individuele pryse Onbekend; betaling {payment} / {af(p['payment_method'])}. Gevolge: {af_effects}. Geen rekord word geskryf voor die presiese voorskou bevestig is nie."
    return f"Auction sale: {len(p['matrix'])} pigs ({tags}). Date {p['sale_date']}; outlet {p['outlet_name']}; invoice {p['invoice_reference']}; invoice evidence {p['invoice_evidence_identity']['evidence_id']}. Lot R4,470.51; interpretation {p['financial_interpretation']}; gross {p['gross_total']}; net {p['net_total']}; received {p['received_total']}; deductions Unknown; individual prices Unknown; payment {p['payment_status']} / {p['payment_method']}. Effects: {effects}. Nothing is recorded until the exact preview is confirmed."
def _fail(reason): return {"success":False,"contract_version":CONTRACT_VERSION,"reason":reason,"delivery_enabled":False,"write_enabled":False,"mating_execution_enabled":False,"customer_contact_enabled":False}
def _tag(v): return _public(_text(v).lstrip("#"))
def _text(v): return str(v or "").strip()
def _norm(v): return _text(v).lower().replace(" ","_").replace("-","_")
def _known(v): return _text(v) or "Unknown"
def _unknown(v): return _norm(v) in {"","unknown","onbekend","n/a","na"}
def _public(v): return " ".join("".join(" " if ch in "\r\n\t" else ch for ch in _text(v) if not unicodedata.category(ch).startswith("C") or ch in "\r\n\t").split())
def _invoice_identity(value):
    if value in (None,""): return {"status":"not_supplied","evidence_id":"Unknown","sha256":"Unknown"}
    if not isinstance(value,dict): return None
    evidence_id=_public(value.get("evidence_id")); digest=_text(value.get("sha256")).lower()
    if not evidence_id or len(evidence_id)>160 or not re.fullmatch(r"[0-9a-f]{64}",digest): return None
    return {"status":"bound","evidence_id":evidence_id,"sha256":digest}
def _date(v):
    try:return date.fromisoformat(_text(v))
    except ValueError:return None
def _digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
