-- Additive only. Owner authorized creation for review; do not apply automatically.
alter table public.beacon_campaign_performance_events
  add column if not exists metric_evidence jsonb not null default '{}'::jsonb,
  add column if not exists evidence_source text not null default 'legacy_unlabelled',
  add column if not exists source_reference text,
  add column if not exists retrieved_at timestamptz,
  add column if not exists source_snapshot_key text,
  add column if not exists supersedes_event_id text references public.beacon_campaign_performance_events(performance_event_id);

create unique index if not exists beacon_campaign_performance_source_snapshot_uidx
  on public.beacon_campaign_performance_events(source_snapshot_key)
  where source_snapshot_key is not null;

create unique index if not exists beacon_campaign_performance_one_correction_uidx
  on public.beacon_campaign_performance_events(supersedes_event_id)
  where supersedes_event_id is not null;

alter table public.beacon_campaign_performance_events
  add constraint beacon_campaign_performance_not_self_superseding
  check (supersedes_event_id is null or supersedes_event_id <> performance_event_id);

create or replace function public.guard_beacon_performance_evidence_immutable()
returns trigger language plpgsql as $$
begin
  raise exception 'Beacon performance evidence is append-only';
end;
$$;

drop trigger if exists beacon_performance_evidence_immutable on public.beacon_campaign_performance_events;
create trigger beacon_performance_evidence_immutable before update or delete
on public.beacon_campaign_performance_events for each row
execute function public.guard_beacon_performance_evidence_immutable();
