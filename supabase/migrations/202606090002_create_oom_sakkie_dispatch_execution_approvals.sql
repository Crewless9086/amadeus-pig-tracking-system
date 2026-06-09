create table if not exists public.oom_sakkie_dispatch_execution_approvals (
    approval_id text primary key,
    dispatch_request_id text not null references public.oom_sakkie_dispatch_requests(dispatch_request_id),
    status text not null,
    mode text not null,
    specialist_slug text not null,
    approval_type text not null,
    notes text not null default '',
    approved_by text not null default 'owner',
    one_shot_scope_json jsonb not null default '{}'::jsonb,
    next_gate text not null default '',
    executes_now boolean not null default false,
    dispatch_enabled boolean not null default false,
    runs_specialist_llm boolean not null default false,
    runs_specialist_tools boolean not null default false,
    writes boolean not null default false,
    applies_runtime_change boolean not null default false,
    dispatches_further boolean not null default false,
    created_at timestamptz not null default now(),
    constraint oom_sakkie_dispatch_execution_approval_mode_check check (
        mode = 'single_dry_run_execution_approval_only'
    ),
    constraint oom_sakkie_dispatch_execution_approval_status_check check (
        status in ('recorded_for_single_dry_run_execution_gate')
    ),
    constraint oom_sakkie_dispatch_execution_approval_type_check check (
        approval_type in ('approved_for_single_dry_run_execution', 'rejected', 'deferred', 'review_note')
    ),
    constraint oom_sakkie_dispatch_execution_approval_sentinel_only_check check (
        specialist_slug = 'sentinel'
    ),
    constraint oom_sakkie_dispatch_execution_approval_no_execution_check check (
        executes_now = false
        and dispatch_enabled = false
        and runs_specialist_llm = false
        and runs_specialist_tools = false
        and writes = false
        and applies_runtime_change = false
        and dispatches_further = false
    )
);

create index if not exists idx_oom_sakkie_dispatch_execution_approvals_request_created
    on public.oom_sakkie_dispatch_execution_approvals(dispatch_request_id, created_at desc);

create table if not exists public.oom_sakkie_dispatch_execution_approval_events (
    event_id text primary key,
    approval_id text not null references public.oom_sakkie_dispatch_execution_approvals(approval_id),
    event_type text not null,
    notes text not null default '',
    recorded_by text not null default 'owner',
    created_at timestamptz not null default now(),
    constraint oom_sakkie_dispatch_execution_approval_event_type_check check (
        event_type in ('review_note', 'consumed_by_single_dry_run_result')
    )
);

create index if not exists idx_oom_sakkie_dispatch_execution_approval_events_approval_created
    on public.oom_sakkie_dispatch_execution_approval_events(approval_id, created_at desc);

create unique index if not exists idx_oom_sakkie_dispatch_execution_approval_consumed_once
    on public.oom_sakkie_dispatch_execution_approval_events(approval_id)
    where event_type = 'consumed_by_single_dry_run_result';

create or replace function public.prevent_oom_sakkie_dispatch_execution_approval_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'oom_sakkie_dispatch_execution_approval tables are append-only';
end;
$$;

drop trigger if exists prevent_oom_sakkie_dispatch_execution_approvals_update on public.oom_sakkie_dispatch_execution_approvals;
create trigger prevent_oom_sakkie_dispatch_execution_approvals_update
    before update on public.oom_sakkie_dispatch_execution_approvals
    for each row
    execute function public.prevent_oom_sakkie_dispatch_execution_approval_mutation();

drop trigger if exists prevent_oom_sakkie_dispatch_execution_approvals_delete on public.oom_sakkie_dispatch_execution_approvals;
create trigger prevent_oom_sakkie_dispatch_execution_approvals_delete
    before delete on public.oom_sakkie_dispatch_execution_approvals
    for each row
    execute function public.prevent_oom_sakkie_dispatch_execution_approval_mutation();

drop trigger if exists prevent_oom_sakkie_dispatch_execution_approval_events_update on public.oom_sakkie_dispatch_execution_approval_events;
create trigger prevent_oom_sakkie_dispatch_execution_approval_events_update
    before update on public.oom_sakkie_dispatch_execution_approval_events
    for each row
    execute function public.prevent_oom_sakkie_dispatch_execution_approval_mutation();

drop trigger if exists prevent_oom_sakkie_dispatch_execution_approval_events_delete on public.oom_sakkie_dispatch_execution_approval_events;
create trigger prevent_oom_sakkie_dispatch_execution_approval_events_delete
    before delete on public.oom_sakkie_dispatch_execution_approval_events
    for each row
    execute function public.prevent_oom_sakkie_dispatch_execution_approval_mutation();
