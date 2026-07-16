-- Additive only. Owner authorized creation for review; this file is not applied by Builder.
alter table public.beacon_campaign_performance_events
    add column if not exists metric_evidence jsonb not null default '{}'::jsonb,
    add column if not exists source_snapshot_id text,
    add column if not exists source_ref text not null default '',
    add column if not exists retrieved_at timestamptz not null default now(),
    add column if not exists supersedes_performance_event_id text;

alter table public.beacon_campaign_performance_events
    drop constraint if exists beacon_campaign_performance_metric_evidence_object;
alter table public.beacon_campaign_performance_events
    add constraint beacon_campaign_performance_metric_evidence_object
    check (jsonb_typeof(metric_evidence) = 'object');

alter table public.beacon_campaign_performance_events
    drop constraint if exists beacon_campaign_performance_supersedes_fk;
alter table public.beacon_campaign_performance_events
    add constraint beacon_campaign_performance_supersedes_fk
    foreign key (supersedes_performance_event_id)
    references public.beacon_campaign_performance_events(performance_event_id);

create unique index if not exists uq_beacon_campaign_performance_source_snapshot
    on public.beacon_campaign_performance_events(source_snapshot_id)
    where source_snapshot_id is not null;

create unique index if not exists uq_beacon_campaign_performance_single_supersession
    on public.beacon_campaign_performance_events(supersedes_performance_event_id)
    where supersedes_performance_event_id is not null;
