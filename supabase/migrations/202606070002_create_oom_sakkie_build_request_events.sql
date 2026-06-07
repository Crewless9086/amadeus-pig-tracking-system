create table if not exists public.oom_sakkie_build_request_events (
    event_id text primary key,
    build_request_id text not null references public.oom_sakkie_build_requests(build_request_id),
    event_type text not null,
    notes text not null default '',
    recorded_by text not null default 'owner',
    created_at timestamptz not null default now(),
    constraint oom_sakkie_build_request_event_type_check check (
        event_type in ('approved', 'ignored', 'review_note')
    )
);

create index if not exists idx_oom_sakkie_build_request_events_request_created
    on public.oom_sakkie_build_request_events(build_request_id, created_at desc);

create index if not exists idx_oom_sakkie_build_request_events_type_created
    on public.oom_sakkie_build_request_events(event_type, created_at desc);

create or replace function public.prevent_oom_sakkie_build_request_event_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'oom_sakkie_build_request_events is append-only';
end;
$$;

drop trigger if exists prevent_oom_sakkie_build_request_events_update on public.oom_sakkie_build_request_events;
create trigger prevent_oom_sakkie_build_request_events_update
    before update on public.oom_sakkie_build_request_events
    for each row
    execute function public.prevent_oom_sakkie_build_request_event_mutation();

drop trigger if exists prevent_oom_sakkie_build_request_events_delete on public.oom_sakkie_build_request_events;
create trigger prevent_oom_sakkie_build_request_events_delete
    before delete on public.oom_sakkie_build_request_events
    for each row
    execute function public.prevent_oom_sakkie_build_request_event_mutation();
