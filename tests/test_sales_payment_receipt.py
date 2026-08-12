import os
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

from modules.sales.sales_payment_receipt import record_sale_payment_state


def _driver(cursor):
    cursor_context = Mock(); cursor_context.__enter__ = Mock(return_value=cursor)
    cursor_context.__exit__ = Mock(return_value=False)
    connection = Mock(); connection.cursor.return_value = cursor_context
    connection_context = Mock(); connection_context.__enter__ = Mock(return_value=connection)
    connection_context.__exit__ = Mock(return_value=False)
    return Mock(connect=Mock(return_value=connection_context))


def payload(amount="4470.51", status="Paid"):
    return {"updated_by": "Charl", "payment_status": status,
        "payment_method": "EFT", "payment_date": "2026-08-12",
        "received_amount": amount}


def test_received_money_requires_amount_method_and_date():
    result, status = record_sale_payment_state("SALE-1", {
        "updated_by": "Charl", "payment_status": "Paid"},
        database_url="postgresql://example")
    assert status == 400 and result["status"] == "validation_failed"
    assert len(result["errors"]) == 3 and result["writes_to_supabase"] is False


@patch.dict(os.environ, {"DATABASE_URL": "postgresql://example"}, clear=True)
def test_bkb_paid_receipt_preserves_invoice_accounting_and_records_only_payment_state():
    cursor = Mock()
    cursor.fetchone.side_effect = [
        ("Completed", "Unknown", "EFT", None, None, Decimal("4470.51"),
         Decimal("4470.51"), "Auction", "Invoice S-EE02-2710"),
        ("SALE-AUCT", "Paid", "EFT", date(2026, 8, 12), Decimal("4470.51"),
         Decimal("4470.51"), Decimal("4470.51"), "Auction"),
    ]
    with patch.dict("sys.modules", {"psycopg": _driver(cursor)}):
        result, status = record_sale_payment_state("SALE-AUCT", payload())
    assert status == 200 and result["status"] == "payment_state_recorded"
    assert result["received_amount"] == "4470.51"
    update_sql = cursor.execute.call_args_list[1].args[0].lower()
    assert "received_total" in update_sql
    assert "gross_total" not in update_sql and "net_total=" not in update_sql
    assert "sales_transaction_items" not in update_sql


@patch.dict(os.environ, {"DATABASE_URL": "postgresql://example"}, clear=True)
def test_paid_amount_must_equal_canonical_due_and_writes_zero():
    cursor = Mock(); cursor.fetchone.return_value = (
        "Completed", "Unpaid", "Cash", None, None, Decimal("2250.00"),
        None, None, "")
    with patch.dict("sys.modules", {"psycopg": _driver(cursor)}):
        result, status = record_sale_payment_state("SALE-1", payload("2200.00"))
    assert status == 409 and result["status"] == "paid_amount_must_equal_amount_due"
    assert cursor.execute.call_count == 1 and result["writes_to_supabase"] is False


@patch.dict(os.environ, {"DATABASE_URL": "postgresql://example"}, clear=True)
def test_exact_payment_replay_is_noop():
    cursor = Mock(); cursor.fetchone.return_value = (
        "Completed", "Paid", "EFT", date(2026, 8, 12), Decimal("4470.51"),
        Decimal("4470.51"), Decimal("4470.51"), "Auction", "")
    with patch.dict("sys.modules", {"psycopg": _driver(cursor)}):
        result, status = record_sale_payment_state("SALE-AUCT", payload())
    assert status == 200 and result["status"] == "payment_state_replay_noop"
    assert result["created"] is False and cursor.execute.call_count == 1


def test_unpaid_records_no_receipt_and_never_infers_money():
    result, status = record_sale_payment_state("SALE-1", {
        "updated_by": "Charl", "payment_status": "Unpaid", "received_amount": 10},
        database_url="postgresql://example")
    assert status == 400 and "Unpaid cannot record" in " ".join(result["errors"])
