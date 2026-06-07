create table if not exists public.oom_sakkie_build_requests (
    build_request_id text primary key,
    status text not null,
    mode text not null,
    approved_by text not null default 'owner',
    proposal_json jsonb not null default '{}'::jsonb,
    brief text not null default '',
    recommended_files_json jsonb not null default '[]'::jsonb,
    verification_json jsonb not null default '[]'::jsonb,
    next_gate text not null default '',
    builder_enabled boolean not null default false,
    writes_code_now boolean not null default false,
    applies_changes_now boolean not null default false,
    created_at timestamptz not null default now(),
    constraint oom_sakkie_build_requests_mode_check check (mode = 'build_request_only'),
    constraint oom_sakkie_build_requests_status_check check (status in ('approved_for_build')),
    constraint oom_sakkie_build_requests_no_live_builder_check check (
        builder_enabled = false and writes_code_now = false and applies_changes_now = false
    )
);

create index if not exists idx_oom_sakkie_build_requests_created_at
    on public.oom_sakkie_build_requests(created_at desc);

create or replace function public.prevent_oom_sakkie_build_request_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'oom_sakkie_build_requests is append-only';
end;
$$;

drop trigger if exists prevent_oom_sakkie_build_requests_update on public.oom_sakkie_build_requests;
create trigger prevent_oom_sakkie_build_requests_update
    before update on public.oom_sakkie_build_requests
    for each row
    execute function public.prevent_oom_sakkie_build_request_mutation();

drop trigger if exists prevent_oom_sakkie_build_requests_delete on public.oom_sakkie_build_requests;
create trigger prevent_oom_sakkie_build_requests_delete
    before delete on public.oom_sakkie_build_requests
    for each row
    execute function public.prevent_oom_sakkie_build_request_mutation();
