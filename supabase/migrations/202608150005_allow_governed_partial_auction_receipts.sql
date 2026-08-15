alter table public.sales_transactions
  drop constraint if exists sales_transactions_auction_paid_evidence_check;

alter table public.sales_transactions
  add constraint sales_transactions_auction_paid_evidence_check check (
    sale_channel is distinct from 'Auction' or
    (received_total is null and payment_status not in ('Deposit_Paid','Part_Paid','Paid')
      and payment_date is null and payment_received_evidence_json is null
      and payment_evidence_sha256 is null) or
    (received_total > 0 and received_total < net_settlement_payable
      and payment_status in ('Deposit_Paid','Part_Paid') and payment_date is not null
      and payment_date >= sale_date and payment_received_evidence_json is not null
      and payment_evidence_sha256 is not null) or
    (received_total = net_settlement_payable and payment_status = 'Paid'
      and payment_date is not null and payment_date >= sale_date
      and payment_received_evidence_json is not null and payment_evidence_sha256 is not null)
  );

insert into app_private.migration_log(migration_id,description)
values('202608150005_allow_governed_partial_auction_receipts',
 'Require digest-bound evidence for full and actual cumulative partial auction receipts')
on conflict(migration_id) do nothing;
