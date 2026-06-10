create table if not exists public.oom_sakkie_learning_influence_proposals (
    proposal_id text primary key,
    source_result_id text not null references public.oom_sakkie_agent_dry_run_results(dry_run_result_id),
    status text not null,
    mode text not null,
    specialist_slug text not null,
    proposal_title text not null default '',
    proposal_text text not null default '',
    evidence_json jsonb not null default '{}'::jsonb,
    proposed_rules_json jsonb not null default '[]'::jsonb,
    next_gate text not null default '',
    proposed_by text not null default 'oom_sakkie_learning_influence',
    applies_learning_now boolean not null default false,
    changes_prompt_now boolean not null default false,
    changes_runtime_now boolean not null default false,
    dispatch_enabled boolean not null default false,
    writes boolean not null default false,
    created_at timestamptz not null default now(),
    constraint oom_sakkie_learning_influence_proposal_mode_check check (
        mode = 'learning_influence_proposal_only'
    ),
    constraint oom_sakkie_learning_influence_proposal_status_check check (
        status = 'proposed_for_owner_review'
    ),
    constraint oom_sakkie_learning_influence_proposal_no_apply_check check (
        applies_learning_now = false
        and changes_prompt_now = false
        and changes_runtime_now = false
        and dispatch_enabled = false
        and writes = false
    )
);

create unique index if not exists idx_oom_sakkie_learning_influence_source_once
    on public.oom_sakkie_learning_influence_proposals(source_result_id);

create index if not exists idx_oom_sakkie_learning_influence_created
    on public.oom_sakkie_learning_influence_proposals(created_at desc);

create table if not exists public.oom_sakkie_learning_influence_proposal_events (
    event_id text primary key,
    proposal_id text not null references public.oom_sakkie_learning_influence_proposals(proposal_id),
    event_type text not null,
    notes text not null default '',
    recorded_by text not null default 'owner',
    applies_learning_now boolean not null default false,
    changes_prompt_now boolean not null default false,
    changes_runtime_now boolean not null default false,
    dispatch_enabled boolean not null default false,
    writes boolean not null default false,
    created_at timestamptz not null default now(),
    constraint oom_sakkie_learning_influence_event_type_check check (
        event_type in ('approved_for_future_planning', 'rejected', 'review_note')
    ),
    constraint oom_sakkie_learning_influence_event_no_apply_check check (
        applies_learning_now = false
        and changes_prompt_now = false
        and changes_runtime_now = false
        and dispatch_enabled = false
        and writes = false
    )
);

create index if not exists idx_oom_sakkie_learning_influence_events_proposal_created
    on public.oom_sakkie_learning_influence_proposal_events(proposal_id, created_at desc);

create or replace function public.prevent_oom_sakkie_learning_influence_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'oom_sakkie_learning_influence tables are append-only';
end;
$$;

drop trigger if exists prevent_oom_sakkie_learning_influence_proposals_update on public.oom_sakkie_learning_influence_proposals;
create trigger prevent_oom_sakkie_learning_influence_proposals_update
    before update on public.oom_sakkie_learning_influence_proposals
    for each row
    execute function public.prevent_oom_sakkie_learning_influence_mutation();

drop trigger if exists prevent_oom_sakkie_learning_influence_proposals_delete on public.oom_sakkie_learning_influence_proposals;
create trigger prevent_oom_sakkie_learning_influence_proposals_delete
    before delete on public.oom_sakkie_learning_influence_proposals
    for each row
    execute function public.prevent_oom_sakkie_learning_influence_mutation();

drop trigger if exists prevent_oom_sakkie_learning_influence_events_update on public.oom_sakkie_learning_influence_proposal_events;
create trigger prevent_oom_sakkie_learning_influence_events_update
    before update on public.oom_sakkie_learning_influence_proposal_events
    for each row
    execute function public.prevent_oom_sakkie_learning_influence_mutation();

drop trigger if exists prevent_oom_sakkie_learning_influence_events_delete on public.oom_sakkie_learning_influence_proposal_events;
create trigger prevent_oom_sakkie_learning_influence_events_delete
    before delete on public.oom_sakkie_learning_influence_proposal_events
    for each row
    execute function public.prevent_oom_sakkie_learning_influence_mutation();
