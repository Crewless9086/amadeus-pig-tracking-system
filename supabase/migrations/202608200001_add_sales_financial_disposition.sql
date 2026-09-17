alter table public.sales_transactions
    add column if not exists financial_disposition text not null default 'Commercial',
    add column if not exists receivable_total numeric(12,2),
    add column if not exists financial_disposition_evidence_json jsonb,
    add column if not exists financial_disposition_evidence_sha256 text;

alter table public.sales_transactions
    drop constraint if exists sales_transactions_financial_disposition_check;
alter table public.sales_transactions
    add constraint sales_transactions_financial_disposition_check check (
        financial_disposition in ('Commercial','Charitable_Giveaway')
    );

alter table public.sales_transactions
    drop constraint if exists sales_transactions_receivable_total_check;
alter table public.sales_transactions
    add constraint sales_transactions_receivable_total_check check (
        receivable_total is null or receivable_total >= 0
    );

alter table public.sales_transactions
    drop constraint if exists sales_transactions_payment_status_check;
alter table public.sales_transactions
    add constraint sales_transactions_payment_status_check check (
        payment_status in ('Unknown','Unpaid','Deposit_Paid','Part_Paid','Paid','Not_Applicable','Cancelled')
    );

alter table public.sales_transactions
    drop constraint if exists sales_transactions_charitable_disposition_check;
alter table public.sales_transactions
    add constraint sales_transactions_charitable_disposition_check check (
        financial_disposition <> 'Charitable_Giveaway' or (
            sale_stream = 'Livestock' and
            sale_status = 'Completed' and
            receivable_total = 0 and
            received_total = 0 and
            payment_status = 'Not_Applicable' and
            payment_received_evidence_json is null and
            payment_evidence_sha256 is null and
            financial_disposition_evidence_json is not null and
            financial_disposition_evidence_sha256 is not null
        )
    );

create unique index if not exists uq_sales_transactions_financial_disposition_evidence
    on public.sales_transactions(financial_disposition_evidence_sha256)
    where financial_disposition_evidence_sha256 is not null;

create or replace function app_private.guard_charitable_sales_evidence()
returns trigger language plpgsql as $$
begin
    if old.financial_disposition = 'Charitable_Giveaway' and (
        new.financial_disposition is distinct from old.financial_disposition or
        new.financial_disposition_evidence_json is distinct from old.financial_disposition_evidence_json or
        new.financial_disposition_evidence_sha256 is distinct from old.financial_disposition_evidence_sha256 or
        new.sale_stream is distinct from old.sale_stream or
        new.linked_order_id is distinct from old.linked_order_id or
        new.gross_total is distinct from old.gross_total or
        new.deductions_total is distinct from old.deductions_total or
        new.net_total is distinct from old.net_total
    ) then
        raise exception 'charitable sale evidence and list value are immutable';
    end if;
    return new;
end;
$$;

drop trigger if exists trg_guard_charitable_sales_evidence on public.sales_transactions;
create trigger trg_guard_charitable_sales_evidence
before update on public.sales_transactions
for each row execute function app_private.guard_charitable_sales_evidence();

insert into app_private.migration_log(migration_id,description)
values('202608200001_add_sales_financial_disposition',
       'Separate list-value history from receivable and payment truth for governed charitable livestock transfers.')
on conflict(migration_id) do nothing;
