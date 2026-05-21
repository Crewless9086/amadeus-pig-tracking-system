-- Phase 10.2L4A sales transaction payment date extension.
-- Purpose: capture the date payment is actually received, which may be later than slaughter date.
-- This migration imports no data and does not change live Google Sheets-backed behavior.

alter table public.sales_transactions
add column if not exists payment_date date;

comment on column public.sales_transactions.payment_date is
'Date payment was received for the sale transaction. This can differ from sale_date/slaughter date.';

insert into app_private.migration_log (migration_id, description)
values (
    '202605210004_add_sales_transaction_payment_date',
    'Add nullable payment_date to sales_transactions for delayed slaughter/butcher payments.'
)
on conflict (migration_id) do nothing;
