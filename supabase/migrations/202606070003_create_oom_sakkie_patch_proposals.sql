create table if not exists public.oom_sakkie_patch_proposals (
    patch_proposal_id text primary key,
    build_request_id text not null references public.oom_sakkie_build_requests(build_request_id),
    proposal_text text not null default '',
    proposed_by text not null default 'builder',
    risk_notes text not null default '',
    files_touched_json jsonb not null default '[]'::jsonb,
    verification_json jsonb not null default '[]'::jsonb,
    applies_patch boolean not null default false,
    deploys boolean not null default false,
    created_at timestamptz not null default now(),
    constraint oom_sakkie_patch_proposals_review_only_check check (
        applies_patch = false and deploys = false
    )
);

create index if not exists idx_oom_sakkie_patch_proposals_build_request_created
    on public.oom_sakkie_patch_proposals(build_request_id, created_at desc);

create index if not exists idx_oom_sakkie_patch_proposals_created_at
    on public.oom_sakkie_patch_proposals(created_at desc);

create or replace function public.prevent_oom_sakkie_patch_proposal_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'oom_sakkie_patch_proposals is append-only';
end;
$$;

drop trigger if exists prevent_oom_sakkie_patch_proposals_update on public.oom_sakkie_patch_proposals;
create trigger prevent_oom_sakkie_patch_proposals_update
    before update on public.oom_sakkie_patch_proposals
    for each row
    execute function public.prevent_oom_sakkie_patch_proposal_mutation();

drop trigger if exists prevent_oom_sakkie_patch_proposals_delete on public.oom_sakkie_patch_proposals;
create trigger prevent_oom_sakkie_patch_proposals_delete
    before delete on public.oom_sakkie_patch_proposals
    for each row
    execute function public.prevent_oom_sakkie_patch_proposal_mutation();

create table if not exists public.oom_sakkie_patch_proposal_events (
    event_id text primary key,
    patch_proposal_id text not null references public.oom_sakkie_patch_proposals(patch_proposal_id),
    event_type text not null,
    notes text not null default '',
    recorded_by text not null default 'owner',
    created_at timestamptz not null default now(),
    constraint oom_sakkie_patch_proposal_event_type_check check (
        event_type in ('approved_for_patch', 'rejected', 'review_note')
    )
);

create index if not exists idx_oom_sakkie_patch_proposal_events_proposal_created
    on public.oom_sakkie_patch_proposal_events(patch_proposal_id, created_at desc);

create index if not exists idx_oom_sakkie_patch_proposal_events_type_created
    on public.oom_sakkie_patch_proposal_events(event_type, created_at desc);

create or replace function public.prevent_oom_sakkie_patch_proposal_event_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'oom_sakkie_patch_proposal_events is append-only';
end;
$$;

drop trigger if exists prevent_oom_sakkie_patch_proposal_events_update on public.oom_sakkie_patch_proposal_events;
create trigger prevent_oom_sakkie_patch_proposal_events_update
    before update on public.oom_sakkie_patch_proposal_events
    for each row
    execute function public.prevent_oom_sakkie_patch_proposal_event_mutation();

drop trigger if exists prevent_oom_sakkie_patch_proposal_events_delete on public.oom_sakkie_patch_proposal_events;
create trigger prevent_oom_sakkie_patch_proposal_events_delete
    before delete on public.oom_sakkie_patch_proposal_events
    for each row
    execute function public.prevent_oom_sakkie_patch_proposal_event_mutation();
