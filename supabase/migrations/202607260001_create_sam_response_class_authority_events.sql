create table if not exists public.sam_response_class_authority_events (
    authority_event_id text primary key,
    response_class text not null,
    evidence_window_id text not null,
    evidence_window_hash text not null,
    evaluator_version text not null,
    decision text not null check (decision in (
        'candidate', 'canary_authorized', 'promoted', 'paused', 'regressed', 'retired'
    )),
    prior_event_id text,
    authorized_envelope_json jsonb not null default '{}'::jsonb,
    actor_type text not null check (actor_type in ('owner', 'server', 'charlie')),
    actor_id text not null,
    reason text not null,
    evidence_json jsonb not null default '{}'::jsonb,
    blockers_json jsonb not null default '[]'::jsonb,
    global_kill_switch_clear boolean not null default false,
    class_kill_switch_clear boolean not null default false,
    created_at timestamptz not null default now(),
    effective_at timestamptz not null,
    expires_at timestamptz not null,
    contains_customer_content boolean not null default false,
    sends_customer_message boolean not null default false,
    mutates_business_state boolean not null default false,
    constraint sam_response_class_authority_no_content check (
        contains_customer_content = false
        and sends_customer_message = false
        and mutates_business_state = false
    ),
    constraint sam_response_class_authority_time_order check (
        effective_at >= created_at - interval '5 minutes'
        and expires_at > effective_at
    ),
    constraint sam_response_class_authority_prior_fk
        foreign key (prior_event_id)
        references public.sam_response_class_authority_events(authority_event_id)
);

create unique index if not exists uq_sam_response_class_authority_decision
    on public.sam_response_class_authority_events(
        response_class, evidence_window_hash, decision
    );

create unique index if not exists uq_sam_response_class_authority_prior_transition
    on public.sam_response_class_authority_events(response_class, prior_event_id)
    where prior_event_id is not null;

create index if not exists idx_sam_response_class_authority_latest
    on public.sam_response_class_authority_events(
        response_class, effective_at desc, created_at desc, authority_event_id desc
    );

create or replace function public.prevent_sam_response_class_authority_mutation()
returns trigger
language plpgsql
as $$
begin
    raise exception 'sam_response_class_authority_events is append-only';
end;
$$;

drop trigger if exists prevent_sam_response_class_authority_update
    on public.sam_response_class_authority_events;
create trigger prevent_sam_response_class_authority_update
    before update on public.sam_response_class_authority_events
    for each row execute function public.prevent_sam_response_class_authority_mutation();

drop trigger if exists prevent_sam_response_class_authority_delete
    on public.sam_response_class_authority_events;
create trigger prevent_sam_response_class_authority_delete
    before delete on public.sam_response_class_authority_events
    for each row execute function public.prevent_sam_response_class_authority_mutation();

alter table public.sam_response_class_authority_events enable row level security;

revoke all privileges
    on table public.sam_response_class_authority_events
    from public, anon, authenticated;
revoke select, insert, update, delete, truncate, references, trigger
    on table public.sam_response_class_authority_events
    from public, anon, authenticated;
revoke all privileges
    on table public.sam_response_class_authority_events
    from service_role;
revoke select, insert, update, delete, truncate, references, trigger
    on table public.sam_response_class_authority_events
    from service_role;

revoke all privileges
    on function public.prevent_sam_response_class_authority_mutation()
    from public, anon, authenticated;
revoke execute
    on function public.prevent_sam_response_class_authority_mutation()
    from public, anon, authenticated;
revoke all privileges
    on function public.prevent_sam_response_class_authority_mutation()
    from service_role;
revoke execute
    on function public.prevent_sam_response_class_authority_mutation()
    from service_role;

-- Authority identities are caller supplied, so this table must own no
-- sequence. Fail migration if a later schema change silently introduces one.
do $$
begin
    if exists (
        select 1
        from pg_class sequence_object
        join pg_namespace namespace_object
          on namespace_object.oid = sequence_object.relnamespace
        join pg_depend dependency
          on dependency.objid = sequence_object.oid
        join pg_class table_object
          on table_object.oid = dependency.refobjid
        where sequence_object.relkind = 'S'
          and namespace_object.nspname = 'public'
          and table_object.relname = 'sam_response_class_authority_events'
    ) then
        raise exception 'sam_response_class_authority_events must not own a sequence';
    end if;
end;
$$;

grant select, insert on public.sam_response_class_authority_events to service_role;
