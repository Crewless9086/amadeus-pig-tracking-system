import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path

import pytest

from modules.sales.sales_financial_disposition import (
    confirm_charitable_disposition, preview_charitable_disposition)
from modules.sales.sales_payment_receipt import preview_sale_payment_state


DATABASE_URL = os.getenv("TEST_DATABASE_URL", "").strip()
DESTRUCTIVE_TEST_ENABLED = os.getenv("CHARITY_DISPOSITION_POSTGRES_TEST_ALLOW_DROP") == "1"
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or not DESTRUCTIVE_TEST_ENABLED,
    reason="explicit disposable charity PostgreSQL test database not configured")


@pytest.fixture(scope="module", autouse=True)
def migrated_database():
    import psycopg
    with psycopg.connect(DATABASE_URL, autocommit=True) as db:
        database_name = db.execute("select current_database()").fetchone()[0]
        if database_name != "charity_test":
            pytest.fail("refusing destructive fixture outside disposable charity_test database")
        db.execute("create schema if not exists app_private")
        db.execute("create table if not exists app_private.migration_log(migration_id text primary key, description text)")
        db.execute("drop table if exists public.sales_transactions cascade")
        db.execute("drop table if exists public.orders cascade")
        db.execute("create table public.orders(order_id text primary key, payment_status text, updated_at timestamptz default now())")
        db.execute("""create table public.sales_transactions(
            sale_id text primary key, sale_status text not null, sale_stream text not null,
            payment_status text not null, payment_method text, received_total numeric(12,2),
            net_total numeric(12,2) not null, gross_total numeric(12,2) not null,
            deductions_total numeric(12,2) not null default 0, payment_date date,
            payment_received_evidence_json jsonb, payment_evidence_sha256 text,
            linked_order_id text references public.orders(order_id),
            net_settlement_payable numeric(12,2), sale_channel text, notes text,
            buyer_name text, destination text, external_reference text,
            updated_at timestamptz default now())""")
        db.execute(Path("supabase/migrations/202608200001_add_sales_financial_disposition.sql").read_text(encoding="utf-8"))
    yield


def _insert(sale_id, order_id, stream="Livestock"):
    import psycopg
    with psycopg.connect(DATABASE_URL) as db:
        db.execute("insert into public.orders(order_id,payment_status) values(%s,'Part_Paid')", (order_id,))
        db.execute("""insert into public.sales_transactions(
            sale_id,sale_status,sale_stream,payment_status,payment_method,received_total,
            net_total,gross_total,deductions_total,payment_received_evidence_json,
            payment_evidence_sha256,linked_order_id)
            values(%s,'Completed',%s,'Part_Paid','Cash',0.01,750,750,0,%s::jsonb,%s,%s)""",
            (sale_id, stream, '{"received_amount":"0.01"}', "4" * 64, order_id))


def _payload(digest=None):
    value = {"reason": "Charity support for the recipient farm.",
             "correction_reason": "R0.01 was entered because zero was rejected."}
    if digest:
        value["confirmed_preview_digest"] = digest
    return value


def test_migration_service_concurrency_and_stale_payment_are_fail_closed():
    import psycopg
    sale_id, order_id = "SALE-CHARITY-PG-1", "ORDER-CHARITY-PG-1"
    _insert(sale_id, order_id)
    preview, status = preview_charitable_disposition(
        sale_id, _payload(), DATABASE_URL, actor_id="owner:test")
    assert status == 200
    request = _payload(preview["preview_digest"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: confirm_charitable_disposition(
            sale_id, request, DATABASE_URL, actor_id="owner:test"), range(2)))
    assert sorted(status for _, status in results) == [200, 409]
    with psycopg.connect(DATABASE_URL) as db:
        sale = db.execute("""select sale_stream,financial_disposition,net_total,
            receivable_total,received_total,payment_status from public.sales_transactions
            where sale_id=%s""", (sale_id,)).fetchone()
        order = db.execute("select payment_status from public.orders where order_id=%s", (order_id,)).fetchone()
        assert sale == ("Livestock", "Charitable_Giveaway", Decimal("750.00"),
                        Decimal("0.00"), Decimal("0.00"), "Not_Applicable")
        assert order == ("Not_Applicable",)
        with pytest.raises(psycopg.errors.RaiseException):
            db.execute("update public.sales_transactions set net_total=0 where sale_id=%s", (sale_id,))
    payment, payment_status = preview_sale_payment_state(sale_id, {
        "payment_status": "Paid", "payment_method": "EFT", "payment_date": "2026-08-20",
        "received_amount": "750.00"}, DATABASE_URL, actor_id="owner:test")
    assert payment_status == 409 and payment["status"] == "payment_not_applicable_no_receivable"


def test_non_livestock_charity_and_linked_order_failure_roll_back_atomically():
    import psycopg
    with psycopg.connect(DATABASE_URL) as db:
        with pytest.raises(psycopg.errors.CheckViolation):
            db.execute("""insert into public.sales_transactions(
                sale_id,sale_status,sale_stream,payment_status,received_total,net_total,
                gross_total,deductions_total,financial_disposition,receivable_total,
                financial_disposition_evidence_json,financial_disposition_evidence_sha256)
                values('SALE-CHARITY-PG-MEAT','Completed','Meat','Not_Applicable',0,750,750,0,
                'Charitable_Giveaway',0,'{}'::jsonb,%s)""", ("5" * 64,))
    sale_id, order_id = "SALE-CHARITY-PG-2", "ORDER-CHARITY-PG-2"
    _insert(sale_id, order_id)
    with psycopg.connect(DATABASE_URL, autocommit=True) as db:
        db.execute("""create or replace function public.reject_order_update() returns trigger
            language plpgsql as $$ begin raise exception 'test rollback'; end $$""")
        db.execute("create trigger reject_order_update before update on public.orders for each row execute function public.reject_order_update()")
    preview, _ = preview_charitable_disposition(sale_id, _payload(), DATABASE_URL, actor_id="owner:test")
    result, status = confirm_charitable_disposition(
        sale_id, _payload(preview["preview_digest"]), DATABASE_URL, actor_id="owner:test")
    assert status == 503 and result["writes_to_supabase"] is False
    with psycopg.connect(DATABASE_URL) as db:
        row = db.execute("select financial_disposition,payment_status,received_total from public.sales_transactions where sale_id=%s", (sale_id,)).fetchone()
        assert row == ("Commercial", "Part_Paid", Decimal("0.01"))
    with psycopg.connect(DATABASE_URL, autocommit=True) as db:
        db.execute("drop trigger reject_order_update on public.orders")
        db.execute("drop function public.reject_order_update()")
