-- Unapplied: owner-admin candidate evidence only; no auction assignment authority.
create table public.riversdale_auction_candidate_reviews (
  review_id text primary key,
  auction_cycle_id text not null references public.riversdale_auction_cycles(auction_cycle_id) on delete restrict,
  pig_id text not null references public.pigs(pig_id) on delete restrict,
  withdrawal_state text not null check (withdrawal_state in ('not_applicable','cleared','hold','unknown')),
  quality_state text not null check (quality_state in ('suitable','hold','unknown')),
  observed_at timestamptz not null,
  observer_reference text not null check (btrim(observer_reference)<>''),
  observation_event_id text not null unique references public.pig_observation_events(observation_event_id) on delete restrict,
  medical_evidence_refs text[] not null default '{}',
  follow_up text not null default '',
  idempotency_key text not null unique check (btrim(idempotency_key)<>''),
  review_hash text not null check (length(review_hash)=64),
  recorded_at timestamptz not null default now(),
  check (observed_at <= recorded_at)
);
create index riversdale_candidate_reviews_cycle_pig_idx
  on public.riversdale_auction_candidate_reviews(auction_cycle_id,pig_id,recorded_at desc);
alter table public.riversdale_auction_candidate_reviews enable row level security;
revoke all on public.riversdale_auction_candidate_reviews from public;
do $$ begin
  if exists(select 1 from pg_roles where rolname='anon') then revoke all on public.riversdale_auction_candidate_reviews from anon; end if;
  if exists(select 1 from pg_roles where rolname='authenticated') then revoke all on public.riversdale_auction_candidate_reviews from authenticated; end if;
  if exists(select 1 from pg_roles where rolname='service_role') then
    revoke all on public.riversdale_auction_candidate_reviews from service_role;
    grant select,insert on public.riversdale_auction_candidate_reviews to service_role;
  end if;
end $$;
create function app_private.block_riversdale_candidate_review_mutation() returns trigger language plpgsql as $$
begin raise exception 'auction candidate reviews are append-only'; end $$;
create trigger riversdale_candidate_reviews_append_only before update or delete
on public.riversdale_auction_candidate_reviews for each row execute function app_private.block_riversdale_candidate_review_mutation();
revoke all on function app_private.block_riversdale_candidate_review_mutation() from public;
insert into app_private.migration_log(migration_id,description) values
('202607260004_create_riversdale_auction_candidate_reviews','Append-only owner Riversdale withdrawal and physical-quality reviews.')
on conflict(migration_id) do nothing;
