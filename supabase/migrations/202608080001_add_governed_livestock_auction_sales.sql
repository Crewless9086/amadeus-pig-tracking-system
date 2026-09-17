-- Additive representation for governed completed livestock auction lots.
alter table public.sales_transactions add column if not exists sale_channel text;
alter table public.sales_transactions add column if not exists lot_total numeric(12,2);
alter table public.sales_transactions add column if not exists financial_interpretation text;
alter table public.sales_transactions add column if not exists received_total numeric(12,2);
alter table public.sales_transactions add column if not exists output_vat numeric(12,2);
alter table public.sales_transactions add column if not exists gross_including_vat numeric(12,2);
alter table public.sales_transactions add column if not exists commission_ex_vat numeric(12,2);
alter table public.sales_transactions add column if not exists commission_input_vat numeric(12,2);
alter table public.sales_transactions add column if not exists commission_including_vat numeric(12,2);
alter table public.sales_transactions add column if not exists other_deductions numeric(12,2);
alter table public.sales_transactions add column if not exists net_settlement_payable numeric(12,2);
alter table public.sales_transactions add column if not exists payment_received_evidence_json jsonb;
alter table public.sales_transactions add column if not exists payment_evidence_sha256 text;
alter table public.sales_transactions add column if not exists external_reference text;
alter table public.sales_transactions add column if not exists evidence_json jsonb not null default '{}'::jsonb;
alter table public.sales_transactions add column if not exists operation_id text;
alter table public.sales_transactions add column if not exists confirmed_preview_hash text;
alter table public.sales_transactions alter column deductions_total drop not null;
alter table public.sales_transactions alter column deductions_total drop default;
alter table public.sales_transactions drop constraint if exists sales_transactions_payment_status_check;
alter table public.sales_transactions add constraint sales_transactions_payment_status_check check(payment_status in ('Unknown','Unpaid','Deposit_Paid','Part_Paid','Paid','Cancelled'));
alter table public.sales_transactions drop constraint if exists sales_transactions_channel_check;
alter table public.sales_transactions add constraint sales_transactions_channel_check check(sale_channel is null or (sale_stream='Livestock' and sale_channel='Auction'));
alter table public.sales_transactions drop constraint if exists sales_transactions_financial_interpretation_check;
alter table public.sales_transactions add constraint sales_transactions_financial_interpretation_check check(financial_interpretation is null or financial_interpretation in ('gross_proceeds','net_proceeds','money_received','seller_settlement_payable','unknown'));
alter table public.sales_transactions drop constraint if exists sales_transactions_auction_lot_check;
alter table public.sales_transactions add constraint sales_transactions_auction_lot_check check(sale_channel is distinct from 'Auction' or (lot_total is not null and pig_count>0 and operation_id is not null and confirmed_preview_hash is not null));
alter table public.sales_transactions drop constraint if exists sales_transactions_auction_invoice_arithmetic_check;
alter table public.sales_transactions add constraint sales_transactions_auction_invoice_arithmetic_check check(
  sale_channel is distinct from 'Auction' or (
    gross_total is not null and output_vat is not null and gross_including_vat is not null and
    commission_ex_vat is not null and commission_input_vat is not null and commission_including_vat is not null and
    other_deductions is not null and net_total is not null and net_settlement_payable is not null and
    gross_total + output_vat = gross_including_vat and
    commission_ex_vat + commission_input_vat = commission_including_vat and
    deductions_total = commission_including_vat + other_deductions and
    gross_including_vat - commission_including_vat - other_deductions = net_settlement_payable and
    net_total = net_settlement_payable and lot_total = net_settlement_payable and
    (received_total is null or received_total <= net_settlement_payable)
  )
);
alter table public.sales_transactions drop constraint if exists sales_transactions_auction_paid_evidence_check;
alter table public.sales_transactions add constraint sales_transactions_auction_paid_evidence_check check(
  sale_channel is distinct from 'Auction' or
  (received_total is null and payment_status<>'Paid' and payment_date is null and payment_received_evidence_json is null and payment_evidence_sha256 is null) or
  (received_total=net_settlement_payable and payment_status='Paid' and payment_date is not null and payment_date>=sale_date and payment_received_evidence_json is not null and payment_evidence_sha256 is not null)
);
create unique index if not exists uq_sales_transactions_operation_id on public.sales_transactions(operation_id) where operation_id is not null;
create unique index if not exists uq_sales_transactions_auction_reference on public.sales_transactions(destination,external_reference) where sale_channel='Auction' and external_reference is not null;
create unique index if not exists uq_sales_transactions_auction_invoice_reference on public.sales_transactions(external_reference) where sale_channel='Auction' and external_reference is not null;
create unique index if not exists uq_sales_transactions_payment_evidence_sha256 on public.sales_transactions(payment_evidence_sha256) where payment_evidence_sha256 is not null;
create or replace function app_private.guard_reserved_pig_current_state() returns trigger language plpgsql as $$
declare v_status text; v_on_farm boolean;
begin
  if new.pig_id is null or not (new.reserved_status='Reserved' or new.line_status='Reserved') then return new; end if;
  select status,on_farm into v_status,v_on_farm from public.pigs where pig_id=new.pig_id for update;
  if lower(coalesce(v_status,''))<>'active' or v_on_farm is not true then raise exception 'reservation requires current active on-farm pig'; end if;
  return new;
end $$;
drop trigger if exists trg_order_line_current_pig_guard on public.order_lines;
create trigger trg_order_line_current_pig_guard before insert or update on public.order_lines for each row execute function app_private.guard_reserved_pig_current_state();
insert into app_private.migration_log(migration_id,description) values('202608080001_add_governed_livestock_auction_sales','Add governed lot-level Livestock/Auction representation without per-pig price invention.') on conflict(migration_id) do nothing;
