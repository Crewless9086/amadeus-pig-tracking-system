-- Unapplied: append-only owner shortlist events; never an outlet assignment.
create table public.riversdale_auction_list_events (
  auction_list_event_id text primary key,
  auction_cycle_id text not null references public.riversdale_auction_cycles(auction_cycle_id) on delete restrict,
  pig_id text not null references public.pigs(pig_id) on delete restrict,
  event_type text not null check(event_type in ('added','removed')),
  decision_sequence bigint not null check(decision_sequence > 0),
  prior_event_id text,
  eligibility_evidence_hash text not null check(
    eligibility_evidence_hash = '' or length(eligibility_evidence_hash)=64
  ),
  owner_principal text not null check(btrim(owner_principal)<>''),
  owner_note text not null default '',
  idempotency_key text not null unique check(btrim(idempotency_key)<>''),
  request_hash text not null check(length(request_hash)=64),
  event_hash text not null check(length(event_hash)=64),
  recorded_at timestamptz not null default now(),
  unique(auction_list_event_id,auction_cycle_id,pig_id),
  unique(auction_cycle_id,pig_id,decision_sequence),
  foreign key(prior_event_id,auction_cycle_id,pig_id)
    references public.riversdale_auction_list_events(
      auction_list_event_id,auction_cycle_id,pig_id
    ) on delete restrict,
  check((decision_sequence=1 and prior_event_id is null) or
        (decision_sequence>1 and prior_event_id is not null))
);
create index riversdale_auction_list_cycle_pig_idx
 on public.riversdale_auction_list_events(auction_cycle_id,pig_id,decision_sequence desc);
alter table public.riversdale_auction_list_events enable row level security;
revoke all on public.riversdale_auction_list_events from public;
do $$ begin
 if exists(select 1 from pg_roles where rolname='anon') then revoke all on public.riversdale_auction_list_events from anon; end if;
 if exists(select 1 from pg_roles where rolname='authenticated') then revoke all on public.riversdale_auction_list_events from authenticated; end if;
 if exists(select 1 from pg_roles where rolname='service_role') then
  revoke all on public.riversdale_auction_list_events from service_role;
  grant select,insert on public.riversdale_auction_list_events to service_role;
 end if;
end $$;
create function app_private.block_riversdale_auction_list_mutation() returns trigger language plpgsql as $$
begin raise exception 'auction list history is append-only'; end $$;
create trigger riversdale_auction_list_append_only before update or delete
 on public.riversdale_auction_list_events for each row execute function app_private.block_riversdale_auction_list_mutation();
revoke all on function app_private.block_riversdale_auction_list_mutation() from public;
do $$ declare role_name text; begin
 foreach role_name in array array['anon','authenticated','service_role'] loop
  if exists(select 1 from pg_roles where rolname=role_name) then
   execute format('revoke all on function app_private.block_riversdale_auction_list_mutation() from %I',role_name);
  end if;
 end loop;
end $$;
insert into app_private.migration_log(migration_id,description) values
('202607260009_create_riversdale_auction_list_events','Append-only owner Riversdale shortlist events without assignment authority.')
on conflict(migration_id) do nothing;
