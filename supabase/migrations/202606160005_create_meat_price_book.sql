create table if not exists public.oom_sakkie_meat_price_book_entries (
    price_entry_id text primary key,
    product_type text not null check (product_type in (
        'half_carcass',
        'full_carcass',
        'custom_cut',
        'assisted_slaughter',
        'live_pig'
    )),
    cut_set text not null default '',
    price_unit text not null default 'per_kg' check (price_unit in ('per_kg', 'per_pig_fee')),
    price_amount numeric(12, 2) not null check (price_amount >= 0),
    currency text not null default 'ZAR' check (currency = 'ZAR'),
    deposit_rule text not null default '',
    balance_rule text not null default '',
    yield_basis text not null default '',
    effective_from timestamptz not null default now(),
    active boolean not null default true,
    notes text not null default '',
    created_by text not null default 'Farm App',
    created_at timestamptz not null default now()
);

create index if not exists idx_oom_sakkie_meat_price_book_lookup
    on public.oom_sakkie_meat_price_book_entries(product_type, cut_set, active, effective_from desc);

drop trigger if exists trg_oom_sakkie_meat_price_book_no_update on public.oom_sakkie_meat_price_book_entries;
create trigger trg_oom_sakkie_meat_price_book_no_update
    before update on public.oom_sakkie_meat_price_book_entries
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

drop trigger if exists trg_oom_sakkie_meat_price_book_no_delete on public.oom_sakkie_meat_price_book_entries;
create trigger trg_oom_sakkie_meat_price_book_no_delete
    before delete on public.oom_sakkie_meat_price_book_entries
    for each row execute function public.oom_sakkie_sales_campaigns_block_update_delete();

insert into public.oom_sakkie_meat_price_book_entries (
    price_entry_id,
    product_type,
    cut_set,
    price_unit,
    price_amount,
    deposit_rule,
    balance_rule,
    yield_basis,
    effective_from,
    active,
    notes,
    created_by
) values
    (
        'OSK-MEAT-PRICE-DEFAULT-HALF-SET-A-20260616',
        'half_carcass',
        'Set A',
        'per_kg',
        130.00,
        '50% deposit to confirm',
        'Balance due before delivery or collection',
        'Estimated packed half-carcass weight from 60kg live pig: 19-21kg; final amount uses actual packed weight.',
        '2026-06-16 00:00:00+02',
        true,
        'Seeded from Pork Sales Model pilot: half carcass, Set A first.',
        'migration'
    ),
    (
        'OSK-MEAT-PRICE-DEFAULT-HALF-ALL-20260616',
        'half_carcass',
        '',
        'per_kg',
        130.00,
        '50% deposit to confirm',
        'Balance due before delivery or collection',
        'Estimated packed half-carcass weight from 60kg live pig: 19-21kg; final amount uses actual packed weight.',
        '2026-06-16 00:00:00+02',
        true,
        'Seeded standard half-carcass fallback from Pork Sales Model.',
        'migration'
    ),
    (
        'OSK-MEAT-PRICE-DEFAULT-FULL-ALL-20260616',
        'full_carcass',
        '',
        'per_kg',
        130.00,
        '50% deposit to confirm',
        'Balance due before delivery or collection',
        'Estimated packed full-carcass weight from 60kg live pig: 38-42kg; final amount uses actual packed weight.',
        '2026-06-16 00:00:00+02',
        true,
        'Seeded standard full-carcass fallback from Pork Sales Model.',
        'migration'
    ),
    (
        'OSK-MEAT-PRICE-DEFAULT-CUSTOM-ALL-20260616',
        'custom_cut',
        '',
        'per_kg',
        145.00,
        '70% deposit to confirm custom cut order',
        'Balance due before delivery or collection',
        'Custom cut yield is estimated before slaughter and finalized from actual packed weight.',
        '2026-06-16 00:00:00+02',
        true,
        'Seeded custom cut planning price from Pork Sales Model.',
        'migration'
    ),
    (
        'OSK-MEAT-PRICE-DEFAULT-ASSISTED-20260616',
        'assisted_slaughter',
        '',
        'per_pig_fee',
        250.00,
        'Coordination fee confirmed before booking',
        'Balance due before collection',
        'Assisted slaughter is a coordination fee, not a carcass price/kg.',
        '2026-06-16 00:00:00+02',
        true,
        'Seeded assisted slaughter coordination fee from Pork Sales Model.',
        'migration'
    )
on conflict (price_entry_id) do nothing;
