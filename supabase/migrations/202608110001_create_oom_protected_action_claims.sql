create schema if not exists app_private;

create table if not exists app_private.oom_protected_action_claims (
    callback_token text primary key,
    action_kind text not null check (action_kind in ('mortality','grouped_weights')),
    owner_user_id text not null,
    private_chat_id text not null,
    mission_id text not null,
    provider_message_id text not null,
    preview_card_message_id text,
    preview_digest text not null,
    evidence_generation text not null,
    preview_payload jsonb not null,
    status text not null default 'active' check (status in ('active','executing','completed','changed','cancelled','expired','contained')),
    expires_at timestamptz not null,
    confirmation_provider_message_id text,
    confirmation_provider_timestamp timestamptz,
    result_payload jsonb,
    created_at timestamptz not null default now(),
    completed_at timestamptz,
    unique (action_kind, mission_id, preview_digest)
);
create unique index if not exists oom_protected_action_one_active_mission
on app_private.oom_protected_action_claims(mission_id) where status='active';

create table if not exists public.pig_lifecycle_corrections (
    correction_id text primary key,
    pig_id text not null references public.pigs(pig_id),
    supersedes_lifecycle_event_id text not null references public.pig_lifecycle_events(lifecycle_event_id),
    corrected_effective_date date not null,
    prior_effective_date date not null,
    correction_reason text not null,
    owner_evidence jsonb not null,
    source_operation_id text not null unique,
    actor_reference text not null,
    created_at timestamptz not null default now()
);

create or replace function public.block_oom_protected_history_mutation()
returns trigger language plpgsql as $$ begin
  raise exception 'protected action history is append-only';
end $$;
drop trigger if exists block_oom_protected_claim_mutation on app_private.oom_protected_action_claims;
-- Claims alone may transition through the service; canonical correction history may not mutate.
drop trigger if exists block_pig_lifecycle_correction_mutation on public.pig_lifecycle_corrections;
create trigger block_pig_lifecycle_correction_mutation before update or delete
on public.pig_lifecycle_corrections for each row execute function public.block_oom_protected_history_mutation();

revoke all on app_private.oom_protected_action_claims from public, anon, authenticated;
revoke all on public.pig_lifecycle_corrections from public, anon, authenticated;
grant select on public.pig_lifecycle_corrections to service_role;

insert into app_private.migration_log (migration_id, description)
values ('202608110001_create_oom_protected_action_claims', 'Protected owner claims and mortality correction evidence')
on conflict (migration_id) do nothing;
