create table if not exists public.sam_live_stock_level1_control_events (
    control_event_id text primary key,
    prior_event_id text,
    state text not null check (state in ('enabled', 'disabled', 'killed')),
    policy_version text not null,
    activation_cutoff_utc timestamptz not null,
    carried_bindings_json jsonb not null default '[]'::jsonb,
    actor_id text not null,
    intake_write_authorized boolean not null default false,
    reason text not null,
    created_at timestamptz not null default now(),
    effective_at timestamptz not null,
    expires_at timestamptz not null,
    contains_customer_content boolean not null default false,
    sends_customer_message boolean not null default false,
    mutates_business_state boolean not null default false,
    constraint sam_live_stock_level1_control_prior_fk
      foreign key (prior_event_id)
      references public.sam_live_stock_level1_control_events(control_event_id),
    constraint sam_live_stock_level1_control_no_side_effects check (
      contains_customer_content = false
      and sends_customer_message = false
      and mutates_business_state = false
    ),
    constraint sam_live_stock_level1_control_time_order check (
      effective_at >= created_at - interval '5 minutes'
      and expires_at > effective_at
    ),
    constraint sam_live_stock_level1_control_bindings_array check (
      jsonb_typeof(carried_bindings_json) = 'array'
      and jsonb_array_length(carried_bindings_json) <= 25
    )
);

create unique index if not exists
  uq_sam_live_stock_level1_control_prior_transition
  on public.sam_live_stock_level1_control_events(
    coalesce(prior_event_id, '__ROOT__')
  );

create index if not exists idx_sam_live_stock_level1_control_latest
  on public.sam_live_stock_level1_control_events(
    effective_at desc, created_at desc, control_event_id desc
  );

create or replace function public.prevent_sam_live_stock_level1_control_mutation()
returns trigger
language plpgsql
as $$
begin
  raise exception 'sam_live_stock_level1_control_events is append-only';
end;
$$;

drop trigger if exists prevent_sam_live_stock_level1_control_update
  on public.sam_live_stock_level1_control_events;
create trigger prevent_sam_live_stock_level1_control_update
  before update on public.sam_live_stock_level1_control_events
  for each row execute function
    public.prevent_sam_live_stock_level1_control_mutation();

drop trigger if exists prevent_sam_live_stock_level1_control_delete
  on public.sam_live_stock_level1_control_events;
create trigger prevent_sam_live_stock_level1_control_delete
  before delete on public.sam_live_stock_level1_control_events
  for each row execute function
    public.prevent_sam_live_stock_level1_control_mutation();

alter table public.sam_live_stock_level1_control_events enable row level security;

revoke all privileges
  on table public.sam_live_stock_level1_control_events
  from public, anon, authenticated, service_role;
revoke select, insert, update, delete, truncate, references, trigger
  on table public.sam_live_stock_level1_control_events
  from public, anon, authenticated, service_role;
revoke all privileges
  on function public.prevent_sam_live_stock_level1_control_mutation()
  from public, anon, authenticated, service_role;
revoke execute
  on function public.prevent_sam_live_stock_level1_control_mutation()
  from public, anon, authenticated, service_role;

grant select, insert
  on public.sam_live_stock_level1_control_events
  to service_role;
