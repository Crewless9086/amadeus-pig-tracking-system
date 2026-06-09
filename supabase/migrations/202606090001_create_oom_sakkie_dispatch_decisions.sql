create table if not exists public.oom_sakkie_dispatch_requests (
    dispatch_request_id text primary key,
    status text not null,
    mode text not null,
    specialist_slug text not null,
    requested_by text not null default 'owner',
    owner_text text not null default '',
    purpose text not null default '',
    source_trace_id text not null default '',
    proposed_scope_json jsonb not null default '{}'::jsonb,
    guardrails_json jsonb not null default '[]'::jsonb,
    next_gate text not null default '',
    dispatch_enabled boolean not null default false,
    runs_specialist_llm boolean not null default false,
    runs_specialist_tools boolean not null default false,
    writes boolean not null default false,
    applies_runtime_change boolean not null default false,
    created_at timestamptz not null default now(),
    constraint oom_sakkie_dispatch_request_mode_check check (mode = 'dispatch_decision_request_only'),
    constraint oom_sakkie_dispatch_request_status_check check (
        status in ('requested_for_dispatch_design_review')
    ),
    constraint oom_sakkie_dispatch_request_no_execution_check check (
        dispatch_enabled = false
        and runs_specialist_llm = false
        and runs_specialist_tools = false
        and writes = false
        and applies_runtime_change = false
    )
);

create index if not exists idx_oom_sakkie_dispatch_requests_created_at
    on public.oom_sakkie_dispatch_requests(created_at desc);

create table if not exists public.oom_sakkie_dispatch_decisions (
    decision_id text primary key,
    dispatch_request_id text not null references public.oom_sakkie_dispatch_requests(dispatch_request_id),
    decision_type text not null,
    notes text not null default '',
    recorded_by text not null default 'owner',
    dispatch_enabled boolean not null default false,
    runs_specialist_llm boolean not null default false,
    runs_specialist_tools boolean not null default false,
    writes boolean not null default false,
    applies_runtime_change boolean not null default false,
    created_at timestamptz not null default now(),
    constraint oom_sakkie_dispatch_decision_type_check check (
        decision_type in ('approved_for_design_review', 'rejected', 'deferred', 'review_note')
    ),
    constraint oom_sakkie_dispatch_decision_no_execution_check check (
        dispatch_enabled = false
        and runs_specialist_llm = false
        and runs_specialist_tools = false
        and writes = false
        and applies_runtime_change = false
    )
);

create index if not exists idx_oom_sakkie_dispatch_decisions_request_created
    on public.oom_sakkie_dispatch_decisions(dispatch_request_id, created_at desc);

create or replace function public.prevent_oom_sakkie_dispatch_decision_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'oom_sakkie_dispatch_decision tables are append-only';
end;
$$;

drop trigger if exists prevent_oom_sakkie_dispatch_requests_update on public.oom_sakkie_dispatch_requests;
create trigger prevent_oom_sakkie_dispatch_requests_update
    before update on public.oom_sakkie_dispatch_requests
    for each row
    execute function public.prevent_oom_sakkie_dispatch_decision_mutation();

drop trigger if exists prevent_oom_sakkie_dispatch_requests_delete on public.oom_sakkie_dispatch_requests;
create trigger prevent_oom_sakkie_dispatch_requests_delete
    before delete on public.oom_sakkie_dispatch_requests
    for each row
    execute function public.prevent_oom_sakkie_dispatch_decision_mutation();

drop trigger if exists prevent_oom_sakkie_dispatch_decisions_update on public.oom_sakkie_dispatch_decisions;
create trigger prevent_oom_sakkie_dispatch_decisions_update
    before update on public.oom_sakkie_dispatch_decisions
    for each row
    execute function public.prevent_oom_sakkie_dispatch_decision_mutation();

drop trigger if exists prevent_oom_sakkie_dispatch_decisions_delete on public.oom_sakkie_dispatch_decisions;
create trigger prevent_oom_sakkie_dispatch_decisions_delete
    before delete on public.oom_sakkie_dispatch_decisions
    for each row
    execute function public.prevent_oom_sakkie_dispatch_decision_mutation();
