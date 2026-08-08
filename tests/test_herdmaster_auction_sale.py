from copy import deepcopy
import json
from pathlib import Path

from modules.pig_weights.herdmaster_auction_sale import build_auction_sale_preview
from modules.pig_weights.herdmaster_auction_sale_recording import record_confirmed_auction_sale
from modules.sales.sales_transaction_read import _complete_total

TAGS=["84","51","92","93","94","95","97","99","100","101","113","116","120","121","122","66","68","74"]
PIG_IDS=["PIG-"+tag for tag in TAGS]

def report(complete=True):
    row={"tags":TAGS,"lot_total":"4470.51","financial_interpretation":"gross_proceeds"}
    if complete: row.update(sale_date="2026-08-07",outlet_name="Riversdale Auction",invoice_reference="INV-1",payment_status="Unknown",payment_method="")
    return row

def evidence():
    return {"evidence_generation":"GEN-1","pigs":[{"tag_number":tag,"pig_id":"PIG-"+tag,"status":"Active","on_farm":True,"purpose":"Sale","current_pen_name":"Skeer 003","availability_state":"available","reservation_order_state":"none","withdrawal_state":"complete_through_no_active_withdrawal","active_reservation":False,"active_order":False,"prior_sale":False,"prior_sale_state":"none"} for tag in TAGS]}

def test_exact_18_map_and_lot_without_fake_individual_prices():
    result=build_auction_sale_preview(report(),evidence())
    assert result["success"] and result["ready_for_confirmation"]
    assert len(result["matrix"])==18 and {r["pig_id"] for r in result["matrix"]}==set(PIG_IDS)
    assert result["lot_total"]=="4470.51" and result["individual_proceeds"]=="Unknown"

def test_real_read_only_18_tag_fixture_resolves_exactly():
    fixture=json.loads(Path("tests/fixtures/herdmaster_auction_18_20260808.json").read_text(encoding="utf-8"))
    result=build_auction_sale_preview(report(),fixture)
    assert result["success"] and [r["pig_id"] for r in result["matrix"]]==[r["pig_id"] for r in fixture["pigs"]]

def test_missing_financial_and_date_facts_are_one_grouped_question():
    result=build_auction_sale_preview({"tags":TAGS,"lot_total":"4470.51"},evidence())
    assert result["success"] and not result["ready_for_confirmation"]
    assert len(result["missing_facts"])==5 and result["grouped_question"].startswith("Please provide")

def test_unresolved_duplicate_and_wrong_count_fail_closed():
    ev=evidence(); ev["pigs"]=ev["pigs"][:-1]
    assert build_auction_sale_preview(report(),ev)["success"] is False
    ev=evidence(); ev["pigs"].append(deepcopy(ev["pigs"][0]))
    assert build_auction_sale_preview(report(),ev)["success"] is False
    bad=report(); bad["tags"]=TAGS[:-1]+["84"]
    assert build_auction_sale_preview(bad,evidence())["reason"]=="exactly_18_unique_tags_required"

def test_sold_dead_reserved_and_withdrawal_conflicts_fail_whole_lot():
    for patch in ({"status":"Sold","on_farm":False},{"status":"Dead","on_farm":False},{"active_reservation":True},{"withdrawal_state":"hold"}):
        ev=evidence(); ev["pigs"][0].update(patch)
        result=build_auction_sale_preview(report(),ev)
        assert result["success"] is False and result["ready_for_confirmation"] is False

def test_missing_or_unknown_clearance_purpose_and_identity_fail_closed():
    for field,value in (("pig_id",""),("purpose","Unknown"),("availability_state","Unknown"),("reservation_order_state","Unknown"),("withdrawal_state","Unknown"),("prior_sale_state","Unknown")):
        ev=evidence(); ev["pigs"][0][field]=value
        assert build_auction_sale_preview(report(),ev)["success"] is False
    for field in ("active_reservation","active_order","prior_sale"):
        ev=evidence(); ev["pigs"][0].pop(field)
        assert build_auction_sale_preview(report(),ev)["success"] is False

def test_grouped_question_contains_only_missing_facts():
    partial=report(); partial.pop("invoice_reference")
    result=build_auction_sale_preview(partial,evidence())
    assert result["missing_facts"]==["invoice/reference number"]
    assert "actual auction/exit date" not in result["grouped_question"]

def test_preview_exposes_all_financial_and_lifecycle_confirmation_facts():
    result=build_auction_sale_preview(report(),evidence())
    for value in ("gross_proceeds","4470.51","Unknown","2026-08-07","Riversdale Auction","INV-1","Sold and off-farm"):
        assert value.lower() in result["english"].lower()
    assert "bruto" in result["afrikaans"] and "aftrekkings" in result["afrikaans"]

def test_invalid_future_date_or_payment_status_fails_before_confirmation():
    bad=report(); bad["sale_date"]="2099-01-01"
    assert build_auction_sale_preview(bad,evidence())["success"] is False
    bad=report(); bad["payment_status"]="Probably"
    assert build_auction_sale_preview(bad,evidence())["success"] is False
    bad=report(); bad["sale_date"]="2026-08-07 trailing"
    assert build_auction_sale_preview(bad,evidence())["success"] is False

def test_unknown_and_unsafe_public_header_values_remain_unready_or_normalized():
    for field in ("outlet_name","invoice_reference"):
        bad=report(); bad[field]="Unknown"
        assert field.replace("_name","").replace("_reference","") in build_auction_sale_preview(bad,evidence())["grouped_question"]
    safe=report(); safe["outlet_name"]=" Riversdale\nAuction\x07\x7f\u0085 "; safe["invoice_reference"]=" INV\n1 "
    preview=build_auction_sale_preview(safe,evidence())
    assert preview["outlet_name"]=="Riversdale Auction" and preview["invoice_reference"]=="INV 1"
    assert "\n" not in preview["english"] and "\x07" not in preview["afrikaans"]
    assert "\x7f" not in preview["english"] and "\u0085" not in preview["afrikaans"]
    long=report(); long["outlet_name"]="x"*161
    assert build_auction_sale_preview(long,evidence())["success"] is False

def test_bilingual_preview_is_deterministic_and_zero_authority():
    first=build_auction_sale_preview(report(),evidence()); second=build_auction_sale_preview(report(),deepcopy(evidence()))
    assert first==second and "Auction sale" in first["english"] and "Veilingverkoping" in first["afrikaans"]
    assert first["delivery_enabled"] is first["write_enabled"] is first["mating_execution_enabled"] is first["customer_contact_enabled"] is False

def test_confirmation_and_evidence_generation_are_bound_before_write():
    preview=build_auction_sale_preview(report(),evidence())
    confirm={"owner_confirmed":True,"confirmation_id":"CONF","preview_hash":"wrong","operation_id":preview["operation_id"],"evidence_generation":preview["evidence_generation"]}
    result,status=record_confirmed_auction_sale(report(),evidence,confirm,authority={"principal_type":"service","principal_id":"oom"},authority_verifier=lambda _:True,connect_factory=lambda:None)
    assert status==409 and result["status"]=="confirmation_preview_mismatch"
    result,status=record_confirmed_auction_sale(report(),evidence,{**confirm,"preview_hash":preview["preview_hash"]},authority={},authority_verifier=lambda _:True,connect_factory=lambda:None)
    assert status==403 and result["status"]=="trusted_service_authority_required"

class Cursor:
    def __init__(self,replay=False,fail=False,preview=None): self.replay=replay; self.fail=fail; self.preview=preview; self.calls=[]; self.rowcount=1; self.fetches=0
    def execute(self,sql,args=()):
        self.calls.append((" ".join(sql.split()),args))
        if self.fail and "insert into sales_transaction_items" in sql: raise RuntimeError("fixture failure")
    def fetchone(self):
        self.fetches+=1
        if self.fetches==1: return ("SALE-EXISTING",self.preview) if self.replay else None
    def fetchall(self):
        sql=self.calls[-1][0]
        return [(pid,"Active",True,"Sale",False) for pid in sorted(PIG_IDS)] if "select p.pig_id,p.status,p.on_farm,p.purpose" in sql else []
    def __enter__(self): return self
    def __exit__(self,*args): pass
class Conn:
    def __init__(self,cursor): self.value=cursor; self.committed=False; self.rolled_back=False
    def cursor(self): return self.value
    def __enter__(self): return self
    def __exit__(self,typ,*args): self.rolled_back=typ is not None; self.committed=typ is None

def test_atomic_success_and_exact_replay_zero_rows():
    preview=build_auction_sale_preview(report(),evidence()); confirm={"owner_confirmed":True,"preview_hash":preview["preview_hash"],"confirmation_id":"CONF-1","operation_id":preview["operation_id"],"evidence_generation":preview["evidence_generation"]}
    cur=Cursor(); conn=Conn(cur)
    result,status=record_confirmed_auction_sale(report(),evidence,confirm,authority={"principal_type":"service","principal_id":"oom","actor_reference":"owner"},authority_verifier=lambda _:True,connect_factory=lambda:conn)
    assert status==201 and result["rows_created"]==37 and conn.committed
    assert sum("insert into sales_transaction_items" in sql for sql,_ in cur.calls)==18
    assert sum("insert into pig_lifecycle_events" in sql for sql,_ in cur.calls)==18
    header_args=next(args for sql,args in cur.calls if "insert into sales_transactions" in sql)
    assert header_args[1:3]==("2026-08-07","4470.51")
    replay_cur=Cursor(replay=True,preview=preview["preview_hash"]); replay_conn=Conn(replay_cur)
    result,status=record_confirmed_auction_sale(report(),evidence,confirm,authority={"principal_type":"service","principal_id":"oom"},authority_verifier=lambda _:True,connect_factory=lambda:replay_conn)
    assert status==200 and result["rows_created"]==0 and result["replay"]

def test_transaction_failure_rolls_back_everything():
    preview=build_auction_sale_preview(report(),evidence()); cur=Cursor(fail=True); conn=Conn(cur)
    confirm={"owner_confirmed":True,"confirmation_id":"CONF","preview_hash":preview["preview_hash"],"operation_id":preview["operation_id"],"evidence_generation":preview["evidence_generation"]}
    result,status=record_confirmed_auction_sale(report(),evidence,confirm,authority={"principal_type":"service","principal_id":"oom"},authority_verifier=lambda _:True,connect_factory=lambda:conn)
    assert status==503 and result["status"]=="auction_sale_transaction_rolled_back" and conn.rolled_back

def test_migration_preserves_nullable_item_prices_and_adds_monthly_lot_fields():
    sql=Path("supabase/migrations/202608080001_add_governed_livestock_auction_sales.sql").read_text(encoding="utf-8")
    assert "lot_total numeric(12,2)" in sql and "financial_interpretation" in sql and "operation_id" in sql
    base=Path("supabase/migrations/202605210003_create_sales_transaction_tables.sql").read_text(encoding="utf-8")
    assert "line_total numeric(12, 2)" in base and "line_total numeric(12, 2) not null" not in base
    assert "alter column deductions_total drop not null" in sql

def test_monthly_money_totals_preserve_unknown_instead_of_zero():
    streams={"livestock":{"transaction_count":1,"gross_total":4470.51,"net_total":None,"received_total":None,"gross_unknown_count":0,"net_unknown_count":1,"received_unknown_count":1}}
    assert _complete_total(streams,"gross_total","gross_unknown_count")==4470.51
    assert _complete_total(streams,"net_total","net_unknown_count") is None
    assert _complete_total(streams,"received_total","received_unknown_count") is None

def test_invoice_evidence_identity_is_hash_bound_without_private_payload():
    first=report(); first["invoice_evidence"]={"evidence_id":"INV-UPLOAD-1","sha256":"a"*64,"private_text":"must not persist"}
    preview=build_auction_sale_preview(first,evidence())
    assert preview["invoice_evidence_identity"]=={"status":"bound","evidence_id":"INV-UPLOAD-1","sha256":"a"*64}
    changed=deepcopy(first); changed["invoice_evidence"]["sha256"]="b"*64
    assert build_auction_sale_preview(changed,evidence())["preview_hash"]!=preview["preview_hash"]
    invalid=deepcopy(first); invalid["invoice_evidence"]["sha256"]="not-a-hash"
    assert build_auction_sale_preview(invalid,evidence())["success"] is False
    assert "private_text" not in json.dumps(preview)

def test_afrikaans_preview_contains_no_english_unknown_or_raw_financial_enum():
    text=build_auction_sale_preview(report(),evidence())["afrikaans"]
    assert "Unknown" not in text and "gross_proceeds" not in text
