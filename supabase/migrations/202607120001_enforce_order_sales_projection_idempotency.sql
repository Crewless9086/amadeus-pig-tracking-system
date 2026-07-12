-- Enforce idempotent completed-order sales projection. Additive schema only.
do $$
begin
    if exists (select linked_order_id from public.sales_transactions where linked_order_id is not null group by linked_order_id having count(*) > 1) then
        raise exception 'Duplicate linked_order_id values must be reconciled before this migration';
    end if;
    if exists (select sale_id, order_line_id from public.sales_transaction_items where order_line_id is not null group by sale_id, order_line_id having count(*) > 1) then
        raise exception 'Duplicate sale/order_line pairs must be reconciled before this migration';
    end if;
end $$;

create unique index if not exists uq_sales_transactions_linked_order_id
on public.sales_transactions(linked_order_id) where linked_order_id is not null;

create unique index if not exists uq_sales_transaction_items_sale_order_line
on public.sales_transaction_items(sale_id, order_line_id) where order_line_id is not null;

insert into app_private.migration_log (migration_id, description)
values ('202607120001_enforce_order_sales_projection_idempotency', 'Enforce one sale per linked order and one item per sale/order line.')
on conflict (migration_id) do nothing;
