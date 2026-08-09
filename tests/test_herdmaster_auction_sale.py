from copy import deepcopy
import json
from pathlib import Path

from modules.pig_weights.herdmaster_auction_sale import build_auction_sale_preview
from modules.pig_weights.herdmaster_auction_sale_recording import record_confirmed_auction_sale, reconcile_auction_payment

TAGS = ["84","51","92","93","94","95","97","99","100","101","113","116","120","121","122","66","68","74"]
PIG_IDS = ["PIG-" + tag for tag in TAGS]

def report(**changes):
    value = {"tags": TAGS, "invoice_evidence": {"evidence_id": "PRIVATE-BKB-SETTLEMENT", "sha256": "a" * 64}}
    value.update(changes)
    return value

def evidence():
    return {"evidence_generation":"GEN-1","pigs":[{"tag_number":tag,"pig_id":"PIG-"+tag,"status":"Active","on_farm":True,"purpose":"Sale","current_pen_name":"Skeer 003","availability_state":"available","reservation_order_state":"none","withdrawal_state":"complete_through_no_active_withdrawal","active_reservation":False,"active_order":False,"prior_sale":False,"prior_sale_state":"none","latest_weight_kg":"8.5888889","latest_weight_date":"2026-08-03"} for tag in TAGS]}

def test_exact_18_map_invoice_truth_and_no_fake_individual_prices():
    result = build_auction_sale_preview(report(), evidence())
    assert result["success"] and result["ready_for_confirmation"]
    assert len(result["matrix"]) == 18 and {row["pig_id"] for row in result["matrix"]} == set(PIG_IDS)
    assert result["gross_revenue_ex_vat"] == "4180.00"
    assert result["output_vat"] == "627.00" and result["gross_including_vat"] == "4807.00"
    assert result["commission_ex_vat"] == "292.60" and result["commission_input_vat"] == "43.89"
    assert result["commission_including_vat"] == "336.49" and result["other_deductions"] == "0.00"
    assert result["net_settlement_payable"] == "4470.51"
    assert result["payment_status"] == result["payment_received_total"] == "Unknown"
    assert result["individual_proceeds"] == result["v10_tags"] == "Unknown"

def test_real_read_only_fixture_and_management_estimates():
    fixture = json.loads(Path("tests/fixtures/herdmaster_auction_18_20260808.json").read_text(encoding="utf-8"))
    result = build_auction_sale_preview(report(), fixture)
    assert result["success"]
    assert [row["pig_id"] for row in result["matrix"]] == [row["pig_id"] for row in fixture["pigs"]]
    assert result["management_analysis"] == {
        "basis":"Analytical estimates using latest recorded weights dated 2026-08-03; invoice auction mass is zero/absent.",
        "combined_latest_weight_kg":"154.6", "average_latest_weight_kg":"8.59",
        "gross_including_vat_per_pig":"267.06", "net_settlement_per_pig":"248.36",
        "net_settlement_per_latest_kg":"28.92",
        "recommendation":"Unavailable until attributable feed-cost, growth-rate, direct-sale value, and pen-capacity evidence exists.",
    }

def test_sanitized_invoice_fixture_preserves_only_supported_public_accounting_facts():
    settlement=json.loads(Path("tests/fixtures/herdmaster_bkb_settlement_sanitized_20260809.json").read_text(encoding="utf-8"))
    assert settlement["gross_revenue_ex_vat"]=="4180.00" and settlement["net_settlement_payable"]=="4470.51"
    assert settlement["payment_received"]==settlement["buyer_identity"]=="Unknown"
    assert settlement["lots"][0]["tag_membership"]=="Unknown" and settlement["private_identifiers_included"] is False

def test_optional_grouped_question_never_blocks_sale_confirmation():
    result = build_auction_sale_preview(report(), evidence())
    assert result["ready_for_confirmation"] and result["question_optional_for_sale"]
    assert result["grouped_question"] == "Has the R4,470.51 EFT reached the bank account, and if known, which eight pigs were in V10?"
    complete = build_auction_sale_preview(report(payment_received=True, v10_tags=TAGS[:8]), evidence())
    assert complete["grouped_question"] is None and complete["v11_tags"] == TAGS[8:]

def test_invoice_mismatch_invalid_lot_membership_and_private_binding_fail_closed():
    assert not build_auction_sale_preview(report(gross_revenue_ex_vat="4470.51"), evidence())["success"]
    assert not build_auction_sale_preview(report(v10_tags=TAGS[:7]), evidence())["success"]
    assert not build_auction_sale_preview({"tags":TAGS}, evidence())["success"]

def test_unresolved_duplicate_sold_dead_reserved_and_withdrawal_fail_whole_lot():
    missing = evidence(); missing["pigs"] = missing["pigs"][:-1]
    duplicate = evidence(); duplicate["pigs"].append(deepcopy(duplicate["pigs"][0]))
    assert not build_auction_sale_preview(report(), missing)["success"]
    assert not build_auction_sale_preview(report(), duplicate)["success"]
    for patch in ({"status":"Sold","on_farm":False},{"status":"Dead","on_farm":False},{"active_reservation":True},{"withdrawal_state":"hold"}):
        changed = evidence(); changed["pigs"][0].update(patch)
        assert not build_auction_sale_preview(report(), changed)["success"]

def test_preview_is_bilingual_deterministic_zero_authority_and_private_safe():
    private = report(); private["invoice_evidence"]["private_text"] = "bank and tax identifiers"
    first = build_auction_sale_preview(private, evidence())
    second = build_auction_sale_preview(deepcopy(private), deepcopy(evidence()))
    assert first == second and "Gross revenue excluding VAT R4,180.00" in first["english"]
    assert "Bruto inkomste uitgesluit BTW R4 180,00" in first["afrikaans"]
    assert "bank and tax identifiers" not in json.dumps(first)
    assert first["delivery_enabled"] is first["write_enabled"] is first["payment_reconciliation_enabled"] is False

def test_payable_does_not_imply_received_and_payment_can_reconcile_later():
    unpaid = build_auction_sale_preview(report(), evidence())
    paid = build_auction_sale_preview(report(payment_received=True), evidence())
    assert unpaid["net_settlement_payable"] == paid["net_settlement_payable"] == "4470.51"
    assert unpaid["payment_received_total"] == "Unknown" and paid["payment_received_total"] == "4470.51"
    assert unpaid["operation_id"] != paid["operation_id"]

def test_confirmation_binding_atomic_success_replay_and_rollback():
    preview = build_auction_sale_preview(report(), evidence())
    confirm = {"owner_confirmed":True,"confirmation_id":"CONF-1","preview_hash":preview["preview_hash"],"operation_id":preview["operation_id"],"evidence_generation":preview["evidence_generation"]}
    mismatch, status = record_confirmed_auction_sale(report(), evidence, {**confirm,"preview_hash":"wrong"}, authority={"principal_type":"service","principal_id":"oom"}, authority_verifier=lambda _:True, connect_factory=lambda:None)
    assert status == 409 and mismatch["status"] == "confirmation_preview_mismatch"
    cur, conn = Cursor(), Conn()
    result, status = record_confirmed_auction_sale(report(), evidence, confirm, authority={"principal_type":"service","principal_id":"oom","actor_reference":"owner"}, authority_verifier=lambda _:True, connect_factory=lambda:conn.bind(cur))
    assert status == 201 and result["rows_created"] == 37 and conn.committed
    assert sum("insert into sales_transaction_items" in sql for sql,_ in cur.calls) == 18
    header = next(args for sql,args in cur.calls if "insert into sales_transactions" in sql)
    assert header[1:7] == ("2026-08-05","4470.51","4180.00","627.00","4807.00","336.49")
    replay_cur, replay_conn = Cursor(replay=True, preview=preview["preview_hash"]), Conn()
    replay, status = record_confirmed_auction_sale(report(), evidence, confirm, authority={"principal_type":"service","principal_id":"oom"}, authority_verifier=lambda _:True, connect_factory=lambda:replay_conn.bind(replay_cur))
    assert status == 200 and replay["rows_created"] == 0
    fail_cur, fail_conn = Cursor(fail=True), Conn()
    failed, status = record_confirmed_auction_sale(report(), evidence, confirm, authority={"principal_type":"service","principal_id":"oom"}, authority_verifier=lambda _:True, connect_factory=lambda:fail_conn.bind(fail_cur))
    assert status == 503 and fail_conn.rolled_back

def test_migration_has_vat_commission_payable_and_duplicate_guards():
    sql = Path("supabase/migrations/202608080001_add_governed_livestock_auction_sales.sql").read_text(encoding="utf-8")
    for field in ("output_vat","gross_including_vat","commission_ex_vat","commission_input_vat","commission_including_vat","other_deductions","net_settlement_payable","payment_received_evidence_json"):
        assert field in sql
    assert "uq_sales_transactions_auction_reference" in sql and "sales_transactions_auction_invoice_arithmetic_check" in sql

def test_later_payment_reconciliation_updates_same_sale_and_replays_zero():
    evidence_row={"amount":"4470.51","received_date":"2026-08-09","evidence_id":"BANK-PRIVATE-1","evidence_sha256":"b"*64}
    cur, conn = PaymentCursor(), Conn()
    result,status=reconcile_auction_payment("SALE-1",evidence_row,authority={"principal_type":"service","principal_id":"ledger"},authority_verifier=lambda _:True,connect_factory=lambda:conn.bind(cur))
    assert status==200 and result["rows_changed"]==1 and sum("update sales_transactions" in sql for sql,_ in cur.calls)==1
    replay_cur,replay_conn=PaymentCursor(received=True),Conn()
    replay,status=reconcile_auction_payment("SALE-1",evidence_row,authority={"principal_type":"service","principal_id":"ledger"},authority_verifier=lambda _:True,connect_factory=lambda:replay_conn.bind(replay_cur))
    assert status==200 and replay["status"]=="payment_replayed_zero_rows" and replay["rows_changed"]==0

class Cursor:
    def __init__(self,replay=False,fail=False,preview=None): self.replay=replay; self.fail=fail; self.preview=preview; self.calls=[]; self.rowcount=1; self.fetches=0
    def execute(self,sql,args=()):
        self.calls.append((" ".join(sql.split()),args))
        if self.fail and "insert into sales_transaction_items" in sql: raise RuntimeError("fixture failure")
    def fetchone(self):
        self.fetches += 1
        if self.fetches == 1: return ("SALE-EXISTING",self.preview) if self.replay else None
    def fetchall(self):
        sql=self.calls[-1][0]
        return [(pid,"Active",True,"Sale",False) for pid in sorted(PIG_IDS)] if "select p.pig_id,p.status,p.on_farm,p.purpose" in sql else []
    def __enter__(self): return self
    def __exit__(self,*args): pass
class Conn:
    def __init__(self): self.value=None; self.committed=False; self.rolled_back=False
    def bind(self,cursor): self.value=cursor; return self
    def cursor(self): return self.value
    def __enter__(self): return self
    def __exit__(self,typ,*args): self.rolled_back=typ is not None; self.committed=typ is None
class PaymentCursor(Cursor):
    def __init__(self,received=False): super().__init__(); self.received=received
    def fetchone(self):
        identity={"evidence_id":"BANK-PRIVATE-1","sha256":"b"*64,"received_date":"2026-08-09","amount":"4470.51"}
        return ("Auction","4470.51","4470.51" if self.received else None,identity if self.received else None)
