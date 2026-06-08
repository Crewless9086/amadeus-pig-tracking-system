create table if not exists public.oom_sakkie_agent_dry_run_requests (
    dry_run_request_id text primary key,
    status text not null,
    mode text not null,
    specialist_slug text not null,
    requested_by text not null default 'owner',
    owner_text text not null default '',
    purpose text not null default '',
    source_trace_id text not null default '',
    allowed_tools_json jsonb not null default '[]'::jsonb,
    guardrails_json jsonb not null default '[]'::jsonb,
    next_gate text not null default '',
    dry_run_enabled boolean not null default false,
    dispatch_enabled boolean not null default false,
    runs_specialist_llm boolean not null default false,
    runs_specialist_tools boolean not null default false,
    writes boolean not null default false,
    created_at timestamptz not null default now(),
    constraint oom_sakkie_agent_dry_run_mode_check check (mode = 'read_only_dry_run_request_only'),
    constraint oom_sakkie_agent_dry_run_status_check check (
        status in ('approved_for_read_only_dry_run')
    ),
    constraint oom_sakkie_agent_dry_run_no_execution_check check (
        dry_run_enabled = false
        and dispatch_enabled = false
        and runs_specialist_llm = false
        and runs_specialist_tools = false
        and writes = false
    )
);

create index if not exists idx_oom_sakkie_agent_dry_run_requests_created_at
    on public.oom_sakkie_agent_dry_run_requests(created_at desc);

create table if not exists public.oom_sakkie_agent_dry_run_events (
    event_id text primary key,
    dry_run_request_id text not null references public.oom_sakkie_agent_dry_run_requests(dry_run_request_id),
    event_type text not null,
    notes text not null default '',
    recorded_by text not null default 'owner',
    created_at timestamptz not null default now(),
    constraint oom_sakkie_agent_dry_run_event_type_check check (
        event_type in ('approved', 'cancelled', 'review_note')
    )
);

create index if not exists idx_oom_sakkie_agent_dry_run_events_request_created
    on public.oom_sakkie_agent_dry_run_events(dry_run_request_id, created_at desc);

create or replace function public.prevent_oom_sakkie_agent_dry_run_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'oom_sakkie_agent_dry_run tables are append-only';
end;
$$;

drop trigger if exists prevent_oom_sakkie_agent_dry_run_requests_update on public.oom_sakkie_agent_dry_run_requests;
create trigger prevent_oom_sakkie_agent_dry_run_requests_update
    before update on public.oom_sakkie_agent_dry_run_requests
    for each row
    execute function public.prevent_oom_sakkie_agent_dry_run_mutation();

drop trigger if exists prevent_oom_sakkie_agent_dry_run_requests_delete on public.oom_sakkie_agent_dry_run_requests;
create trigger prevent_oom_sakkie_agent_dry_run_requests_delete
    before delete on public.oom_sakkie_agent_dry_run_requests
    for each row
    execute function public.prevent_oom_sakkie_agent_dry_run_mutation();

drop trigger if exists prevent_oom_sakkie_agent_dry_run_events_update on public.oom_sakkie_agent_dry_run_events;
create trigger prevent_oom_sakkie_agent_dry_run_events_update
    before update on public.oom_sakkie_agent_dry_run_events
    for each row
    execute function public.prevent_oom_sakkie_agent_dry_run_mutation();

drop trigger if exists prevent_oom_sakkie_agent_dry_run_events_delete on public.oom_sakkie_agent_dry_run_events;
create trigger prevent_oom_sakkie_agent_dry_run_events_delete
    before delete on public.oom_sakkie_agent_dry_run_events
    for each row
    execute function public.prevent_oom_sakkie_agent_dry_run_mutation();
