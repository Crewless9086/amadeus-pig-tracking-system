from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from modules.sales.sales_financial_disposition import (
    _digest, _preview, confirm_charitable_disposition,
    preview_charitable_disposition,
)


def _driver(cursor):
    cursor_context = Mock(); cursor_context.__enter__ = Mock(return_value=cursor)
    cursor_context.__exit__ = Mock(return_value=False)
    connection = Mock(); connection.cursor.return_value = cursor_context
    connection_context = Mock(); connection_context.__enter__ = Mock(return_value=connection)
    connection_context.__exit__ = Mock(return_value=False)
    return Mock(connect=Mock(return_value=connection_context))


def _row():
    return ("Completed", "Part_Paid", "Cash", Decimal("0.01"),
            Decimal("750.00"), None,
            {"source": "protected_owner_confirmation", "received_amount": "0.01"},
            "4" * 64, "Commercial", "Commercial", None, None,
            "ORD-2026-A6EC6D", "Livestock")


def _payload():
    return {"reason": "Charity support for the recipient farm.",
            "correction_reason": "R0.01 was entered only because zero was rejected."}


def test_preview_keeps_list_value_and_preserves_prior_payment_evidence():
    cursor = Mock(); cursor.fetchone.return_value = _row()
    with patch.dict("sys.modules", {"psycopg": _driver(cursor)}):
        result, status = preview_charitable_disposition(
            "SALE-A1", _payload(), database_url="postgresql://example", actor_id="owner:charl")
    assert status == 200 and result["confirmation_required"] is True
    assert result["preview"]["list_value"] == "750.00"
    assert result["preview"]["receivable_total"] == "0.00"
    assert result["preview"]["payment_status"] == "Not_Applicable"
    assert result["preview"]["prior_payment_state"]["received_total"] == "0.01"
    assert result["writes_to_supabase"] is False


def test_confirmation_is_digest_bound_and_updates_sale_and_linked_order():
    row = _row(); preview = _preview("SALE-A1", row, "owner:charl",
        _payload()["reason"], _payload()["correction_reason"])
    updated = ("Completed", "Not_Applicable", None, Decimal("0"), Decimal("750"),
        None, None, None, "Charitable_Giveaway", "Charitable_Giveaway",
        Decimal("0"), "e" * 64, "ORD-2026-A6EC6D", "Livestock")
    cursor = Mock(); cursor.fetchone.side_effect = [row, updated]
    with patch.dict("sys.modules", {"psycopg": _driver(cursor)}):
        result, status = confirm_charitable_disposition("SALE-A1", {
            **_payload(), "confirmed_preview_digest": _digest(preview)},
            database_url="postgresql://example", actor_id="owner:charl")
    assert status == 200 and result["fully_reconciled"] is True
    assert result["financial_disposition"] == "Charitable_Giveaway"
    assert result["receivable_total"] == "0.00"
    sql = [call.args[0].lower() for call in cursor.execute.call_args_list]
    assert any("update public.sales_transactions" in value for value in sql)
    assert any("update public.orders" in value for value in sql)


def test_confirmation_rejects_stale_preview_without_writing():
    cursor = Mock(); cursor.fetchone.return_value = _row()
    with patch.dict("sys.modules", {"psycopg": _driver(cursor)}):
        result, status = confirm_charitable_disposition("SALE-A1", {
            **_payload(), "confirmed_preview_digest": "0" * 64},
            database_url="postgresql://example", actor_id="owner:charl")
    assert status == 409 and result["status"].endswith("stale_or_mismatched")
    assert cursor.execute.call_count == 1


def test_only_completed_livestock_sales_are_eligible():
    row = list(_row()); row[0] = "Confirmed"
    cursor = Mock(); cursor.fetchone.return_value = tuple(row)
    with patch.dict("sys.modules", {"psycopg": _driver(cursor)}):
        result, status = preview_charitable_disposition(
            "SALE-A1", _payload(), database_url="postgresql://example", actor_id="owner:charl")
    assert status == 409 and result["status"] == "completed_livestock_sale_required"


def test_confirm_locks_row_and_replay_cannot_write_again():
    row = list(_row()); row[8] = "Charitable_Giveaway"; row[9] = "Charitable_Giveaway"
    row[10] = Decimal("0"); row[1] = "Not_Applicable"; row[3] = Decimal("0")
    cursor = Mock(); cursor.fetchone.return_value = tuple(row)
    with patch.dict("sys.modules", {"psycopg": _driver(cursor)}):
        result, status = confirm_charitable_disposition("SALE-A1", {
            **_payload(), "confirmed_preview_digest": "0" * 64},
            database_url="postgresql://example", actor_id="owner:charl")
    assert status == 409 and result["status"] == "charitable_disposition_already_recorded"
    assert "for update" in cursor.execute.call_args_list[0].args[0].lower()
    assert cursor.execute.call_count == 1


def test_migration_enforces_zero_consideration_truth_without_rewriting_list_value():
    sql = Path("supabase/migrations/202608200001_add_sales_financial_disposition.sql").read_text(
        encoding="utf-8").lower()
    assert "financial_disposition in ('commercial','charitable_giveaway')" in sql
    assert "receivable_total = 0" in sql
    assert "sale_stream = 'livestock'" in sql
    assert "received_total = 0" in sql
    assert "payment_status = 'not_applicable'" in sql
    assert "update public.sales_transactions" not in sql
    assert "update public.sales_transaction_items" not in sql
    assert "guard_charitable_sales_evidence" in sql
    assert "new.net_total is distinct from old.net_total" in sql
