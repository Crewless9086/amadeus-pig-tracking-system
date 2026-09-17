-- HERDMASTER longitudinal welfare-case foundation.
--
-- Additive and unapplied. This schema records case identity and append-only
-- coordination evidence only. It does not diagnose, prescribe, record a
-- treatment/observation/movement/death, change public.pigs, send Telegram, or
-- close any separate mortality/disposal work.

create table if not exists public.pig_welfare_cases (
    welfare_case_id text primary key check (btrim(welfare_case_id) <> ''),
    pig_id text not null references public.pigs(pig_id) on delete restrict,
    episode_key text not null check (btrim(episode_key) <> ''),
    concern_key text not null check (btrim(concern_key) <> ''),
    episode_started_at timestamptz not null,
    first_reported_at timestamptz not null,
    first_recorded_at timestamptz not null default now(),
    recurrence_of_welfare_case_id text references public.pig_welfare_cases(welfare_case_id) on delete restrict,
    created_by text not null check (btrim(created_by) <> ''),
    source_system text not null check (source_system in (
        'oom_sakkie', 'herdmaster', 'owner', 'farm_staff', 'veterinary', 'import', 'other'
    )),
    source_reference text not null check (btrim(source_reference) <> ''),
    provenance_json jsonb not null check (jsonb_typeof(provenance_json) = 'object'),
    idempotency_key text not null unique check (btrim(idempotency_key) <> ''),
    created_at timestamptz not null default now(),
    constraint pig_welfare_case_episode_identity_unique unique (pig_id, episode_key, concern_key),
    check (first_reported_at <= first_recorded_at),
    check (episode_started_at <= first_recorded_at),
    check (recurrence_of_welfare_case_id is null or recurrence_of_welfare_case_id <> welfare_case_id)
);

create index if not exists pig_welfare_cases_pig_episode_idx
    on public.pig_welfare_cases(pig_id, episode_started_at desc, welfare_case_id);
create index if not exists pig_welfare_cases_recurrence_idx
    on public.pig_welfare_cases(recurrence_of_welfare_case_id)
    where recurrence_of_welfare_case_id is not null;

create table if not exists public.pig_welfare_case_events (
    welfare_case_event_id text primary key check (btrim(welfare_case_event_id) <> ''),
    welfare_case_id text not null references public.pig_welfare_cases(welfare_case_id) on delete restrict,
    sequence_no bigint not null check (sequence_no > 0),
    event_type text not null check (event_type in (
        'opened', 'evidence_added', 'assessed', 'urgency_changed',
        'owner_assigned', 'next_check_scheduled', 'escalated', 'closed',
        'reopened', 'correction'
    )),
    case_state text not null check (case_state in ('open', 'monitoring', 'escalated', 'closed')),
    urgency text not null check (urgency in ('critical', 'urgent', 'due', 'watch')),
    responsible_owner text not null check (btrim(responsible_owner) <> ''),
    next_check_at timestamptz,
    escalation_reason text,
    closure_kind text check (closure_kind in ('recovered', 'death', 'resolved', 'transferred', 'other')),
    closure_reason text,
    event_note text not null default '',
    occurred_at timestamptz not null,
    recorded_at timestamptz not null default now(),
    actor_reference text not null check (btrim(actor_reference) <> ''),
    source_system text not null check (source_system in (
        'oom_sakkie', 'herdmaster', 'owner', 'farm_staff', 'veterinary', 'system', 'import', 'other'
    )),
    source_reference text not null check (btrim(source_reference) <> ''),
    provenance_json jsonb not null check (jsonb_typeof(provenance_json) = 'object'),
    idempotency_key text not null unique check (btrim(idempotency_key) <> ''),
    created_at timestamptz not null default now(),
    constraint pig_welfare_case_event_sequence_unique unique (welfare_case_id, sequence_no),
    check (occurred_at <= recorded_at),
    check (event_type <> 'closed' or case_state = 'closed'),
    check (case_state <> 'closed' or event_type in ('closed', 'correction')),
    check (case_state <> 'closed' or (
        closure_kind is not null and btrim(coalesce(closure_reason, '')) <> ''
    )),
    check (case_state = 'closed' or (closure_kind is null and closure_reason is null)),
    check (event_type <> 'escalated' or (
        case_state = 'escalated' and btrim(coalesce(escalation_reason, '')) <> ''
    )),
    check (event_type <> 'next_check_scheduled' or next_check_at is not null),
    check (next_check_at is null or next_check_at >= occurred_at),
    check (event_type <> 'reopened' or case_state in ('open', 'monitoring', 'escalated'))
);

create unique index if not exists pig_welfare_case_one_opened_event
    on public.pig_welfare_case_events(welfare_case_id)
    where event_type = 'opened';
create index if not exists pig_welfare_case_events_current_idx
    on public.pig_welfare_case_events(welfare_case_id, sequence_no desc);
create index if not exists pig_welfare_case_events_due_idx
    on public.pig_welfare_case_events(next_check_at)
    where case_state <> 'closed' and next_check_at is not null;

create table if not exists public.pig_welfare_case_fact_links (
    welfare_case_fact_link_id text primary key check (btrim(welfare_case_fact_link_id) <> ''),
    welfare_case_id text not null references public.pig_welfare_cases(welfare_case_id) on delete restrict,
    welfare_case_event_id text references public.pig_welfare_case_events(welfare_case_event_id) on delete restrict,
    fact_domain text not null check (fact_domain in (
        'observation', 'medical', 'treatment', 'movement', 'pig_lifecycle', 'mortality'
    )),
    fact_id text not null check (btrim(fact_id) <> ''),
    relationship text not null check (relationship in (
        'reported_with', 'supports', 'contradicts', 'supersedes', 'closes_living_welfare_question', 'context_only'
    )),
    linked_at timestamptz not null,
    recorded_at timestamptz not null default now(),
    actor_reference text not null check (btrim(actor_reference) <> ''),
    source_reference text not null check (btrim(source_reference) <> ''),
    provenance_json jsonb not null check (jsonb_typeof(provenance_json) = 'object'),
    idempotency_key text not null unique check (btrim(idempotency_key) <> ''),
    created_at timestamptz not null default now(),
    constraint pig_welfare_case_fact_once unique (welfare_case_id, fact_domain, fact_id, relationship),
    check (linked_at <= recorded_at),
    check (
        relationship <> 'closes_living_welfare_question'
        or (fact_domain in ('pig_lifecycle', 'mortality') and welfare_case_event_id is not null)
    )
);

create index if not exists pig_welfare_case_fact_links_case_idx
    on public.pig_welfare_case_fact_links(welfare_case_id, linked_at, welfare_case_fact_link_id);
create index if not exists pig_welfare_case_fact_links_fact_idx
    on public.pig_welfare_case_fact_links(fact_domain, fact_id);

create or replace function public.pig_welfare_case_validate_insert()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
    if new.recurrence_of_welfare_case_id is not null and not exists (
        select 1 from public.pig_welfare_cases prior_case
        where prior_case.welfare_case_id = new.recurrence_of_welfare_case_id
          and prior_case.pig_id = new.pig_id
          and prior_case.concern_key = new.concern_key
          and prior_case.episode_started_at < new.episode_started_at
    ) then
        raise exception 'welfare recurrence must reference an earlier case for the same pig and concern';
    end if;
    return new;
end;
$$;

create or replace function public.pig_welfare_case_event_validate_insert()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
declare
    prior_state text;
    prior_occurred_at timestamptz;
    prior_owner text;
    prior_urgency text;
    prior_closure_kind text;
    next_sequence bigint;
begin
    -- Serialize every lifecycle decision on the immutable case identity. This
    -- prevents two workers from both validating against the same prior state.
    perform 1 from public.pig_welfare_cases case_record
     where case_record.welfare_case_id = new.welfare_case_id
     for update;

    select event.case_state, event.occurred_at, event.responsible_owner,
           event.urgency, event.closure_kind, event.sequence_no + 1
      into prior_state, prior_occurred_at, prior_owner,
           prior_urgency, prior_closure_kind, next_sequence
      from public.pig_welfare_case_events event
     where event.welfare_case_id = new.welfare_case_id
     order by event.sequence_no desc
     limit 1
     for update;

    if prior_state is null and new.event_type <> 'opened' then
        raise exception 'welfare case lifecycle must begin with opened';
    end if;
    if prior_state is not null and new.event_type = 'opened' then
        raise exception 'welfare case may be opened only once';
    end if;
    if prior_occurred_at is not null and new.occurred_at < prior_occurred_at then
        raise exception 'welfare case events must preserve chronology';
    end if;
    if prior_closure_kind = 'death' then
        raise exception 'death-closed living welfare case is terminal';
    end if;
    if prior_state = 'closed' and new.event_type not in ('reopened', 'correction') then
        raise exception 'closed welfare case requires explicit reopening';
    end if;
    if new.event_type = 'reopened' and prior_state is distinct from 'closed' then
        raise exception 'only a closed welfare case may be reopened';
    end if;
    if new.event_type = 'correction' and new.case_state is distinct from prior_state then
        raise exception 'welfare correction must preserve current case state';
    end if;
    if new.event_type = 'owner_assigned' and new.responsible_owner is not distinct from prior_owner then
        raise exception 'welfare owner assignment must change responsible owner';
    end if;
    if new.event_type = 'urgency_changed' and new.urgency is not distinct from prior_urgency then
        raise exception 'welfare urgency change must change urgency';
    end if;
    new.sequence_no := coalesce(next_sequence, 1);
    return new;
end;
$$;

create or replace function public.pig_welfare_case_fact_link_validate_insert()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
    if new.welfare_case_event_id is not null and not exists (
        select 1 from public.pig_welfare_case_events event
        where event.welfare_case_event_id = new.welfare_case_event_id
          and event.welfare_case_id = new.welfare_case_id
    ) then
        raise exception 'welfare fact link event must belong to the same case';
    end if;
    if new.relationship = 'closes_living_welfare_question' and not exists (
        select 1 from public.pig_welfare_case_events event
        where event.welfare_case_event_id = new.welfare_case_event_id
          and event.welfare_case_id = new.welfare_case_id
          and event.case_state = 'closed'
          and event.closure_kind = 'death'
          and event.sequence_no = (
              select max(current_event.sequence_no)
              from public.pig_welfare_case_events current_event
              where current_event.welfare_case_id = new.welfare_case_id
          )
    ) then
        raise exception 'living welfare closure link requires a death-closed case event';
    end if;
    return new;
end;
$$;

create or replace function public.pig_welfare_case_validate_death_closure()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
    if new.closure_kind = 'death' and not exists (
        select 1 from public.pig_welfare_case_fact_links link
        where link.welfare_case_event_id = new.welfare_case_event_id
          and link.welfare_case_id = new.welfare_case_id
          and link.relationship = 'closes_living_welfare_question'
          and link.fact_domain in ('pig_lifecycle', 'mortality')
    ) then
        raise exception 'death-closed welfare case requires canonical death fact link';
    end if;
    return null;
end;
$$;

create or replace function public.pig_welfare_case_block_mutation()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
    raise exception 'pig welfare case records are append-only';
end;
$$;

drop trigger if exists trg_pig_welfare_cases_validate_insert on public.pig_welfare_cases;
create trigger trg_pig_welfare_cases_validate_insert
    before insert on public.pig_welfare_cases
    for each row execute function public.pig_welfare_case_validate_insert();
drop trigger if exists trg_pig_welfare_case_events_validate_insert on public.pig_welfare_case_events;
create trigger trg_pig_welfare_case_events_validate_insert
    before insert on public.pig_welfare_case_events
    for each row execute function public.pig_welfare_case_event_validate_insert();
drop trigger if exists trg_pig_welfare_case_fact_links_validate_insert on public.pig_welfare_case_fact_links;
create trigger trg_pig_welfare_case_fact_links_validate_insert
    before insert on public.pig_welfare_case_fact_links
    for each row execute function public.pig_welfare_case_fact_link_validate_insert();
drop trigger if exists trg_pig_welfare_case_death_closure on public.pig_welfare_case_events;
create constraint trigger trg_pig_welfare_case_death_closure
    after insert on public.pig_welfare_case_events
    deferrable initially deferred
    for each row execute function public.pig_welfare_case_validate_death_closure();

drop trigger if exists trg_pig_welfare_cases_no_update_delete on public.pig_welfare_cases;
create trigger trg_pig_welfare_cases_no_update_delete before update or delete
    on public.pig_welfare_cases for each row execute function public.pig_welfare_case_block_mutation();
drop trigger if exists trg_pig_welfare_case_events_no_update_delete on public.pig_welfare_case_events;
create trigger trg_pig_welfare_case_events_no_update_delete before update or delete
    on public.pig_welfare_case_events for each row execute function public.pig_welfare_case_block_mutation();
drop trigger if exists trg_pig_welfare_case_fact_links_no_update_delete on public.pig_welfare_case_fact_links;
create trigger trg_pig_welfare_case_fact_links_no_update_delete before update or delete
    on public.pig_welfare_case_fact_links for each row execute function public.pig_welfare_case_block_mutation();

create or replace view public.pig_welfare_case_current
with (security_invoker = true) as
select case_record.welfare_case_id,
       case_record.pig_id,
       case_record.episode_key,
       case_record.concern_key,
       case_record.episode_started_at,
       case_record.recurrence_of_welfare_case_id,
       latest.event_type,
       latest.case_state,
       latest.urgency,
       latest.responsible_owner,
       latest.next_check_at,
       latest.escalation_reason,
       latest.closure_kind,
       latest.closure_reason,
       latest.occurred_at as state_occurred_at,
       latest.welfare_case_event_id,
       latest.sequence_no
from public.pig_welfare_cases case_record
join lateral (
    select event.* from public.pig_welfare_case_events event
    where event.welfare_case_id = case_record.welfare_case_id
    order by event.sequence_no desc
    limit 1
) latest on true;

alter table public.pig_welfare_cases enable row level security;
alter table public.pig_welfare_case_events enable row level security;
alter table public.pig_welfare_case_fact_links enable row level security;

revoke all privileges on table public.pig_welfare_cases from public;
revoke all privileges on table public.pig_welfare_case_events from public;
revoke all privileges on table public.pig_welfare_case_fact_links from public;
revoke all privileges on table public.pig_welfare_case_current from public;
revoke all privileges on function public.pig_welfare_case_validate_insert() from public;
revoke all privileges on function public.pig_welfare_case_event_validate_insert() from public;
revoke all privileges on function public.pig_welfare_case_fact_link_validate_insert() from public;
revoke all privileges on function public.pig_welfare_case_validate_death_closure() from public;
revoke all privileges on function public.pig_welfare_case_block_mutation() from public;
do $$
declare role_name text;
begin
    foreach role_name in array array['anon', 'authenticated', 'service_role'] loop
        if exists (select 1 from pg_roles where rolname = role_name) then
            execute format('revoke all privileges on table public.pig_welfare_cases from %I', role_name);
            execute format('revoke all privileges on table public.pig_welfare_case_events from %I', role_name);
            execute format('revoke all privileges on table public.pig_welfare_case_fact_links from %I', role_name);
            execute format('revoke all privileges on table public.pig_welfare_case_current from %I', role_name);
            execute format('revoke all privileges on function public.pig_welfare_case_validate_insert() from %I', role_name);
            execute format('revoke all privileges on function public.pig_welfare_case_event_validate_insert() from %I', role_name);
            execute format('revoke all privileges on function public.pig_welfare_case_fact_link_validate_insert() from %I', role_name);
            execute format('revoke all privileges on function public.pig_welfare_case_validate_death_closure() from %I', role_name);
            execute format('revoke all privileges on function public.pig_welfare_case_block_mutation() from %I', role_name);
        end if;
    end loop;
end;
$$;

comment on table public.pig_welfare_cases is
    'Stable per-pig episode identities only; no diagnosis, treatment, lifecycle, movement, mortality, disposal, notification or owner-decision authority.';
comment on table public.pig_welfare_case_events is
    'Append-only welfare coordination lifecycle. Silence or elapsed time never closes or improves a case.';
comment on table public.pig_welfare_case_fact_links is
    'Append-only references to separately canonical observation, medical/treatment, movement, pig-lifecycle and mortality facts; linked facts are never merged into case truth.';

insert into app_private.migration_log (migration_id, description)
values (
    '202608200002_create_pig_welfare_case_lifecycle',
    'Create additive stable welfare episodes, append-only lifecycle events and non-merging canonical fact links.'
)
on conflict (migration_id) do nothing;
