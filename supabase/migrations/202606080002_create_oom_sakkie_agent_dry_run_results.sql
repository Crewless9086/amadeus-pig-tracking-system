create table if not exists public.oom_sakkie_agent_dry_run_results (
    dry_run_result_id text primary key,
    dry_run_request_id text not null references public.oom_sakkie_agent_dry_run_requests(dry_run_request_id),
    status text not null,
    mode text not null,
    specialist_slug text not null,
    result_text text not null default '',
    findings_json jsonb not null default '[]'::jsonb,
    recommended_next_gate text not null default '',
    recorded_by text not null default 'owner',
    runs_specialist boolean not null default false,
    dispatch_enabled boolean not null default false,
    runs_specialist_llm boolean not null default false,
    runs_specialist_tools boolean not null default false,
    writes boolean not null default false,
    applies_runtime_change boolean not null default false,
    created_at timestamptz not null default now(),
    constraint oom_sakkie_agent_dry_run_result_mode_check check (mode = 'dry_run_result_review_only'),
    constraint oom_sakkie_agent_dry_run_result_status_check check (
        status in ('recorded_for_owner_review')
    ),
    constraint oom_sakkie_agent_dry_run_result_no_execution_check check (
        runs_specialist = false
        and dispatch_enabled = false
        and runs_specialist_llm = false
        and runs_specialist_tools = false
        and writes = false
        and applies_runtime_change = false
    )
);

create index if not exists idx_oom_sakkie_agent_dry_run_results_request_created
    on public.oom_sakkie_agent_dry_run_results(dry_run_request_id, created_at desc);

create table if not exists public.oom_sakkie_agent_dry_run_result_events (
    event_id text primary key,
    dry_run_result_id text not null references public.oom_sakkie_agent_dry_run_results(dry_run_result_id),
    event_type text not null,
    notes text not null default '',
    recorded_by text not null default 'owner',
    created_at timestamptz not null default now(),
    constraint oom_sakkie_agent_dry_run_result_event_type_check check (
        event_type in ('accepted_for_learning', 'rejected', 'review_note')
    )
);

create index if not exists idx_oom_sakkie_agent_dry_run_result_events_result_created
    on public.oom_sakkie_agent_dry_run_result_events(dry_run_result_id, created_at desc);

create or replace function public.prevent_oom_sakkie_agent_dry_run_result_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'oom_sakkie_agent_dry_run_result tables are append-only';
end;
$$;

drop trigger if exists prevent_oom_sakkie_agent_dry_run_results_update on public.oom_sakkie_agent_dry_run_results;
create trigger prevent_oom_sakkie_agent_dry_run_results_update
    before update on public.oom_sakkie_agent_dry_run_results
    for each row
    execute function public.prevent_oom_sakkie_agent_dry_run_result_mutation();

drop trigger if exists prevent_oom_sakkie_agent_dry_run_results_delete on public.oom_sakkie_agent_dry_run_results;
create trigger prevent_oom_sakkie_agent_dry_run_results_delete
    before delete on public.oom_sakkie_agent_dry_run_results
    for each row
    execute function public.prevent_oom_sakkie_agent_dry_run_result_mutation();

drop trigger if exists prevent_oom_sakkie_agent_dry_run_result_events_update on public.oom_sakkie_agent_dry_run_result_events;
create trigger prevent_oom_sakkie_agent_dry_run_result_events_update
    before update on public.oom_sakkie_agent_dry_run_result_events
    for each row
    execute function public.prevent_oom_sakkie_agent_dry_run_result_mutation();

drop trigger if exists prevent_oom_sakkie_agent_dry_run_result_events_delete on public.oom_sakkie_agent_dry_run_result_events;
create trigger prevent_oom_sakkie_agent_dry_run_result_events_delete
    before delete on public.oom_sakkie_agent_dry_run_result_events
    for each row
    execute function public.prevent_oom_sakkie_agent_dry_run_result_mutation();
