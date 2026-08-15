import os
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

from modules.sales.sales_payment_receipt import (
    _payment_preview, _preview_digest, _proposed_payment,
    preview_sale_payment_state, record_sale_payment_state)


def _driver(cursor):
    cursor_context = Mock(); cursor_context.__enter__ = Mock(return_value=cursor)
    cursor_context.__exit__ = Mock(return_value=False)
    connection = Mock(); connection.cursor.return_value = cursor_context
    connection_context = Mock(); connection_context.__enter__ = Mock(return_value=connection)
    connection_context.__exit__ = Mock(return_value=False)
    return Mock(connect=Mock(return_value=connection_context))


def payload(amount="4470.51", status="Paid"):
    return {"updated_by": "forged-family-name", "payment_status": status,
        "payment_method": "EFT", "payment_date": "2026-08-12",
        "received_amount": amount}


def confirmed(value, row, sale_id="SALE-1"):
    proposed, errors = _proposed_payment(sale_id, value, "owner:charl")
    assert not errors
    return {**value, "confirmed_preview_digest": _preview_digest(
        _payment_preview(sale_id, row, proposed))}


def test_received_money_requires_amount_method_and_date():
    result, status = record_sale_payment_state("SALE-1", {
        "updated_by": "Charl", "payment_status": "Paid"},
        database_url="postgresql://example", actor_id="owner:charl")
    assert status == 400 and result["status"] == "validation_failed"
    assert len(result["errors"]) == 4 and result["writes_to_supabase"] is False


@patch.dict(os.environ, {"DATABASE_URL": "postgresql://example"}, clear=True)
def test_bkb_paid_receipt_preserves_invoice_accounting_and_records_only_payment_state():
    cursor = Mock()
    row = ("Completed", "Unknown", "EFT", None, None, Decimal("4470.51"),
         Decimal("4470.51"), "Auction", "Invoice S-EE02-2710"),
    row = row[0]
    cursor.fetchone.side_effect = [
        row,
        ("SALE-AUCT", "Paid", "EFT", date(2026, 8, 12), Decimal("4470.51"),
         Decimal("4470.51"), Decimal("4470.51"), "Auction"),
    ]
    with patch.dict("sys.modules", {"psycopg": _driver(cursor)}):
        result, status = record_sale_payment_state("SALE-AUCT", confirmed(
            payload(), row, "SALE-AUCT"), database_url="postgresql://example",
            actor_id="owner:charl")
    assert status == 200 and result["status"] == "payment_state_recorded"
    assert result["received_amount"] == "4470.51"
    assert result["transaction_label"] == "Livestock — Auction"
    assert result["auction_completed"] is True
    assert result["settlement_received"] is True
    assert result["fully_reconciled"] is True
    update_sql = cursor.execute.call_args_list[1].args[0].lower()
    assert "received_total" in update_sql
    assert "gross_total" not in update_sql and "net_total=" not in update_sql
    assert "sales_transaction_items" not in update_sql


@patch.dict(os.environ, {"DATABASE_URL": "postgresql://example"}, clear=True)
def test_paid_amount_must_equal_canonical_due_and_writes_zero():
    row = (
        "Completed", "Unpaid", "Cash", None, None, Decimal("2250.00"),
        None, None, "")
    cursor = Mock(); cursor.fetchone.return_value = row
    with patch.dict("sys.modules", {"psycopg": _driver(cursor)}):
        result, status = record_sale_payment_state("SALE-1", confirmed(
            payload("2200.00"), row), actor_id="owner:charl")
    assert status == 409 and result["status"] == "paid_amount_must_equal_amount_due"
    assert cursor.execute.call_count == 1 and result["writes_to_supabase"] is False


@patch.dict(os.environ, {"DATABASE_URL": "postgresql://example"}, clear=True)
def test_exact_payment_replay_is_noop():
    row_without_note = (
        "Completed", "Paid", "EFT", date(2026, 8, 12), Decimal("4470.51"),
        Decimal("4470.51"), Decimal("4470.51"), "Auction", "")
    request = confirmed(payload(), row_without_note, "SALE-AUCT")
    row = (*row_without_note[:8], f"recorded from preview {request['confirmed_preview_digest']}")
    cursor = Mock(); cursor.fetchone.return_value = row
    with patch.dict("sys.modules", {"psycopg": _driver(cursor)}):
        result, status = record_sale_payment_state(
            "SALE-AUCT", request, actor_id="owner:charl")
    assert status == 200 and result["status"] == "payment_state_replay_noop"
    assert result["created"] is False and cursor.execute.call_count == 1
    assert result["transaction_label"] == "Livestock — Auction"
    assert result["fully_reconciled"] is True


def test_preexisting_exact_receipt_without_bound_digest_is_not_claimed_as_replay():
    row = ("Completed", "Paid", "EFT", date(2026, 8, 12), Decimal("4470.51"),
           Decimal("4470.51"), Decimal("4470.51"), "Auction", "legacy receipt")
    cursor = Mock(); cursor.fetchone.return_value = row
    with patch.dict("sys.modules", {"psycopg": _driver(cursor)}):
        result, status = record_sale_payment_state("SALE-AUCT", confirmed(
            payload(), row, "SALE-AUCT"), database_url="postgresql://example",
            actor_id="owner:charl")
    assert status == 409
    assert result["status"] == "existing_receipt_requires_governed_correction"
    assert cursor.execute.call_count == 1


def test_unpaid_records_no_receipt_and_never_infers_money():
    result, status = record_sale_payment_state("SALE-1", {
        "updated_by": "Charl", "payment_status": "Unpaid", "received_amount": 10},
        database_url="postgresql://example", actor_id="owner:charl")
    assert status == 400 and "Unpaid cannot record" in " ".join(result["errors"])


def test_caller_cannot_supply_payment_audit_actor():
    result, status = record_sale_payment_state("SALE-1", payload(),
        database_url="postgresql://example")
    assert status == 400 and "authenticated owner actor" in " ".join(result["errors"])


@patch.dict(os.environ, {"DATABASE_URL": "postgresql://example"}, clear=True)
def test_existing_paid_receipt_cannot_be_rewritten_as_partial_or_changed_evidence():
    for changed in (
        payload("1000.00", "Part_Paid"),
        {**payload(), "payment_date": "2026-08-13"},
        {**payload(), "payment_method": "Cash"},
    ):
        row = (
            "Completed", "Paid", "EFT", date(2026, 8, 12), Decimal("4470.51"),
            Decimal("4470.51"), Decimal("4470.51"), "Auction", "")
        cursor = Mock(); cursor.fetchone.return_value = row
        with patch.dict("sys.modules", {"psycopg": _driver(cursor)}):
            result, status = record_sale_payment_state(
                "SALE-AUCT", confirmed(changed, row, "SALE-AUCT"), actor_id="owner:charl")
        assert status == 409
        assert result["status"] == "existing_receipt_requires_governed_correction"
        assert cursor.execute.call_count == 1 and result["writes_to_supabase"] is False


def test_preview_is_zero_write_and_partial_preserves_actual_received_amount():
    row = ("Completed", "Unpaid", "EFT", None, None, Decimal("4470.51"),
           Decimal("4470.51"), "Auction", "")
    cursor = Mock(); cursor.fetchone.return_value = row
    partial = payload("1000.00", "Part_Paid")
    with patch.dict("sys.modules", {"psycopg": _driver(cursor)}):
        result, status = preview_sale_payment_state(
            "SALE-AUCT", partial, database_url="postgresql://example",
            actor_id="owner:charl")
    assert status == 200 and result["status"] == "payment_state_preview_ready"
    assert result["preview"]["received_amount"] == "1000.00"
    assert result["preview"]["amount_due"] == "4470.51"
    assert result["preview"]["transaction_label"] == "Livestock — Auction"
    assert result["preview"]["canonical_action_service"] == "sale_payment_receipt"
    assert result["preview"]["receipt_amount"] == "1000.00"
    assert result["preview"]["human_readable"] == (
        "Livestock — Auction · SALE-AUCT · receipt R1000.00; total received after this receipt R1000.00 of R4470.51 by EFT "
        "on 2026-08-12. No receipt has been recorded yet.")
    assert result["writes_to_supabase"] is False
    assert cursor.execute.call_count == 1


def test_confirmation_digest_mismatch_fails_before_update():
    row = ("Completed", "Unpaid", "EFT", None, None, Decimal("4470.51"),
           Decimal("4470.51"), "Auction", "")
    cursor = Mock(); cursor.fetchone.return_value = row
    request = {**payload(), "confirmed_preview_digest": "0" * 64}
    with patch.dict("sys.modules", {"psycopg": _driver(cursor)}):
        result, status = record_sale_payment_state(
            "SALE-AUCT", request, database_url="postgresql://example",
            actor_id="owner:charl")
    assert status == 409 and result["status"] == "payment_preview_stale_or_mismatched"
    assert "current_preview_digest" not in result
    assert cursor.execute.call_count == 1 and result["writes_to_supabase"] is False


def test_partial_receipt_can_progress_to_full_cumulative_settlement():
    row = ("Completed", "Part_Paid", "EFT", date(2026, 8, 12),
           Decimal("1000.00"), Decimal("4470.51"), Decimal("4470.51"),
           "Auction", "first partial receipt")
    request = confirmed(payload(), row, "SALE-AUCT")
    cursor = Mock(); cursor.fetchone.side_effect = [row,
        ("SALE-AUCT", "Paid", "EFT", date(2026, 8, 12), Decimal("4470.51"),
         Decimal("4470.51"), Decimal("4470.51"), "Auction")]
    with patch.dict("sys.modules", {"psycopg": _driver(cursor)}):
        result, status = record_sale_payment_state(
            "SALE-AUCT", request, database_url="postgresql://example",
            actor_id="owner:charl")
    assert status == 200 and result["status"] == "payment_state_recorded"
    assert result["received_amount"] == "4470.51"
    assert cursor.execute.call_count == 2


def test_exact_state_preview_is_read_only_and_needs_no_confirmation():
    row = ("Completed", "Paid", "EFT", date(2026, 8, 12), Decimal("4470.51"),
           Decimal("4470.51"), Decimal("4470.51"), "Auction", "")
    cursor = Mock(); cursor.fetchone.return_value = row
    with patch.dict("sys.modules", {"psycopg": _driver(cursor)}):
        result, status = preview_sale_payment_state(
            "SALE-AUCT", payload(), database_url="postgresql://example",
            actor_id="owner:charl")
    assert status == 200 and result["status"] == "payment_state_already_recorded"
    assert result["confirmation_required"] is False
    assert result["writes_to_supabase"] is False and cursor.execute.call_count == 1
