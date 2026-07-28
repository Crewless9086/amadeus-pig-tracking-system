-- ROOTLINE Phase 1 canonical Water & Energy Plan.
-- Advisory evidence only: no scheduler, command, retry, workflow, transport,
-- SmartLife, SONOFF, IFTTT, n8n or hardware authority.

create table public.rootline_tank_observations (
    observation_id text primary key check (
        observation_id ~ '^ROOTLINE-TANK-[0-9A-F]{24}$'
    ),
    idempotency_key text not null unique check (btrim(idempotency_key) <> ''),
    storage_reported_count integer check (storage_reported_count between 0 and 5),
    reservoir_reported_count integer check (reservoir_reported_count between 0 and 12),
    storage_state text not null default 'Unknown'
        check (storage_state in ('LOW','OK','FULL','Unknown')),
    reservoir_state text not null default 'Unknown'
        check (reservoir_state in ('LOW','OK','FULL','Unknown')),
    observed_at timestamptz not null,
    reporter_identity text not null check (btrim(reporter_identity) <> ''),
    source text not null check (source in ('owner_dashboard', 'oom_sakkie_owner')),
    evidence_json jsonb not null default '{}'::jsonb
        check (jsonb_typeof(evidence_json) = 'object'),
    recorded_at timestamptz not null default now(),
    check (storage_reported_count is not null or reservoir_reported_count is not null),
    check (observed_at <= recorded_at + interval '1 minute')
);

create table public.rootline_water_energy_plan_identities (
    plan_id text primary key check (plan_id ~ '^ROOTLINE-WEP-[0-9]{8}$'),
    operating_date date not null unique,
    operating_timezone text not null
        check (operating_timezone = 'Africa/Johannesburg'),
    current_generation integer not null check (current_generation > 0),
    created_at timestamptz not null default now(),
    current_selected_at timestamptz not null default now()
);

create table public.rootline_water_energy_plan_generations (
    plan_id text not null references public.rootline_water_energy_plan_identities(plan_id)
        on delete restrict,
    generation integer not null check (generation > 0),
    operating_date date not null,
    evidence_sha256 text not null check (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    evidence_observed_at timestamptz not null,
    replacement_reason text not null check (btrim(replacement_reason) <> ''),
    status text not null check (status in ('recommend', 'hold', 'needs_data')),
    evidence_json jsonb not null check (jsonb_typeof(evidence_json) = 'object'),
    plan_json jsonb not null check (jsonb_typeof(plan_json) = 'object'),
    writes_farm_data boolean not null default false check (writes_farm_data = false),
    creates_irrigation_plan boolean not null default false check (creates_irrigation_plan = false),
    creates_command boolean not null default false check (creates_command = false),
    mutates_schedule boolean not null default false check (mutates_schedule = false),
    activates_workflow boolean not null default false check (activates_workflow = false),
    calls_smartlife boolean not null default false check (calls_smartlife = false),
    calls_sonoff boolean not null default false check (calls_sonoff = false),
    calls_ifttt boolean not null default false check (calls_ifttt = false),
    calls_n8n boolean not null default false check (calls_n8n = false),
    controls_hardware boolean not null default false check (controls_hardware = false),
    automatic_retry boolean not null default false check (automatic_retry = false),
    created_by text not null check (btrim(created_by) <> ''),
    created_at timestamptz not null default now(),
    primary key (plan_id, generation),
    unique (plan_id, evidence_sha256),
    unique (plan_id, generation, operating_date)
);

alter table public.rootline_water_energy_plan_identities
    add constraint rootline_water_energy_current_generation_fk
    foreign key (plan_id, current_generation)
    references public.rootline_water_energy_plan_generations(plan_id, generation)
    deferrable initially deferred;

create index rootline_water_energy_history_idx
    on public.rootline_water_energy_plan_generations(operating_date, generation desc);
create index rootline_tank_observations_observed_idx
    on public.rootline_tank_observations(observed_at desc);

create function public.rootline_block_water_energy_history_mutation()
returns trigger language plpgsql as $$
begin
    raise exception 'ROOTLINE Water & Energy evidence is append-only';
end;
$$;

create trigger trg_rootline_tank_observations_immutable
before update or delete on public.rootline_tank_observations
for each row execute function public.rootline_block_water_energy_history_mutation();

create trigger trg_rootline_water_energy_generations_immutable
before update or delete on public.rootline_water_energy_plan_generations
for each row execute function public.rootline_block_water_energy_history_mutation();

create function public.rootline_append_water_energy_plan(
    p_plan_id text,
    p_operating_date date,
    p_evidence_sha256 text,
    p_evidence_observed_at timestamptz,
    p_replacement_reason text,
    p_status text,
    p_evidence_json jsonb,
    p_plan_json jsonb,
    p_created_by text,
    out created boolean,
    out superseded_generation integer,
    out generation integer
) returns record
language plpgsql security definer set search_path = public, pg_temp as $$
declare current_hash text;
begin
    if p_plan_id <> ('ROOTLINE-WEP-' || to_char(p_operating_date, 'YYYYMMDD')) then
        raise exception 'plan identity does not match Johannesburg operating date';
    end if;
    if p_plan_json->>'plan_id' <> p_plan_id
       or p_plan_json->>'operating_date' <> p_operating_date::text
       or p_plan_json->>'operating_timezone' <> 'Africa/Johannesburg'
       or p_plan_json->>'status' <> p_status
       or p_plan_json->>'evidence_sha256' <> p_evidence_sha256 then
        raise exception 'plan payload identity mismatch';
    end if;
    if p_plan_json->'authority' is distinct from '{
      "writes_performed": false,
      "creates_irrigation_plan": false,
      "creates_command": false,
      "mutates_schedule": false,
      "activates_workflow": false,
      "calls_smartlife": false,
      "calls_sonoff": false,
      "calls_ifttt": false,
      "calls_n8n": false,
      "controls_hardware": false,
      "automatic_retry": false
    }'::jsonb then
        raise exception 'plan payload authority must remain false';
    end if;
    if jsonb_typeof(p_plan_json->'candidate_tasks') is distinct from 'array'
       or exists (
         select 1
           from jsonb_array_elements(p_plan_json->'candidate_tasks') task
          where jsonb_typeof(task->'command_created') is distinct from 'boolean'
             or task->>'command_created' <> 'false'
             or jsonb_typeof(task->'dispatchable') is distinct from 'boolean'
             or task->>'dispatchable' <> 'false'
             or jsonb_typeof(task->'electrical_operation_confirmed') is distinct from 'boolean'
             or task->>'electrical_operation_confirmed' <> 'false'
             or jsonb_typeof(task->'physical_water_flow_confirmed') is distinct from 'boolean'
             or task->>'physical_water_flow_confirmed' <> 'false'
       ) then
        raise exception 'candidate tasks must remain advisory and unexecuted';
    end if;
    perform pg_advisory_xact_lock(
        hashtextextended('rootline-water-energy:' || p_operating_date::text, 0)
    );
    select i.current_generation, g.evidence_sha256
      into superseded_generation, current_hash
      from rootline_water_energy_plan_identities i
      join rootline_water_energy_plan_generations g
        on g.plan_id=i.plan_id and g.generation=i.current_generation
     where i.operating_date=p_operating_date;

    if current_hash = p_evidence_sha256 then
        created := false;
        generation := superseded_generation;
        superseded_generation := null;
        return;
    end if;

    generation := coalesce(superseded_generation, 0) + 1;
    if superseded_generation is null then
        insert into rootline_water_energy_plan_identities
            (plan_id, operating_date, operating_timezone, current_generation)
        values (p_plan_id, p_operating_date, 'Africa/Johannesburg', generation);
    end if;

    insert into rootline_water_energy_plan_generations (
        plan_id, generation, operating_date, evidence_sha256,
        evidence_observed_at, replacement_reason, status, evidence_json,
        plan_json, created_by
    ) values (
        p_plan_id, generation, p_operating_date, p_evidence_sha256,
        p_evidence_observed_at, p_replacement_reason, p_status, p_evidence_json,
        p_plan_json, p_created_by
    );

    if superseded_generation is not null then
        update rootline_water_energy_plan_identities
           set current_generation=generation, current_selected_at=now()
         where operating_date=p_operating_date;
    end if;
    created := true;
end;
$$;

alter table public.rootline_tank_observations enable row level security;
alter table public.rootline_water_energy_plan_identities enable row level security;
alter table public.rootline_water_energy_plan_generations enable row level security;

revoke all on table public.rootline_tank_observations,
    public.rootline_water_energy_plan_identities,
    public.rootline_water_energy_plan_generations
    from public, anon, authenticated, service_role;
revoke execute on function public.rootline_block_water_energy_history_mutation(),
    public.rootline_append_water_energy_plan(
        text,date,text,timestamptz,text,text,jsonb,jsonb,text
    ) from public, anon, authenticated, service_role;

grant select, insert on table public.rootline_tank_observations to service_role;
grant select on table public.rootline_water_energy_plan_identities,
    public.rootline_water_energy_plan_generations to service_role;
grant execute on function public.rootline_append_water_energy_plan(
    text,date,text,timestamptz,text,text,jsonb,jsonb,text
) to service_role;

insert into app_private.migration_log (migration_id, description)
values (
    '202607280001_create_rootline_water_energy_plans',
    'Create command-inert canonical ROOTLINE Water & Energy Plan and manual tank evidence.'
)
on conflict (migration_id) do nothing;
