-- Canonical ROOTLINE daily irrigation plans. Additive; no scheduler or execution authority.

create table public.irrigation_daily_plan_identities (
    daily_plan_id text primary key check (btrim(daily_plan_id) <> ''),
    operating_date date not null unique,
    operating_timezone text not null check (operating_timezone = 'Africa/Johannesburg'),
    current_generation integer not null check (current_generation > 0),
    created_at timestamptz not null default now(),
    current_selected_at timestamptz not null default now()
);

create table public.irrigation_daily_plan_generations (
    daily_plan_id text not null references public.irrigation_daily_plan_identities(daily_plan_id)
        on delete restrict,
    generation integer not null check (generation > 0),
    operating_date date not null,
    status text not null check (status in (
        'planned','missed','stale','unavailable','no_irrigation_required'
    )),
    evidence_observed_at timestamptz not null,
    replacement_reason text not null check (btrim(replacement_reason) <> ''),
    evidence_sha256 text not null check (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    evidence_json jsonb not null check (jsonb_typeof(evidence_json) = 'object'),
    zones_json jsonb not null check (jsonb_typeof(zones_json) = 'array'),
    created_at timestamptz not null default now(),
    primary key (daily_plan_id, generation),
    unique (daily_plan_id, evidence_sha256),
    unique (daily_plan_id, generation, operating_date)
);

alter table public.irrigation_daily_plan_identities
    add constraint irrigation_daily_plan_current_generation_fk
    foreign key (daily_plan_id, current_generation)
    references public.irrigation_daily_plan_generations(daily_plan_id, generation)
    deferrable initially deferred;

alter table public.irrigation_command_plans
    add column daily_plan_id text not null,
    add column daily_plan_generation integer not null,
    add column daily_plan_operating_date date not null,
    add constraint irrigation_commands_daily_plan_fk
        foreign key (daily_plan_id, daily_plan_generation, daily_plan_operating_date)
        references public.irrigation_daily_plan_generations
            (daily_plan_id, generation, operating_date) on delete restrict;

create index irrigation_daily_plan_generations_date_history_idx
    on public.irrigation_daily_plan_generations(operating_date, generation desc);

create function public.irrigation_daily_plan_block_history_mutation()
returns trigger language plpgsql as $$
begin
    raise exception 'daily irrigation plan generations are immutable';
end;
$$;

create trigger trg_irrigation_daily_plan_generations_immutable
before update or delete on public.irrigation_daily_plan_generations
for each row execute function public.irrigation_daily_plan_block_history_mutation();

create function public.irrigation_command_require_current_daily_plan()
returns trigger language plpgsql as $$
declare selected integer;
begin
    select current_generation into selected
      from public.irrigation_daily_plan_identities
     where daily_plan_id=new.daily_plan_id
       and operating_date=new.daily_plan_operating_date;
    if selected is null or selected <> new.daily_plan_generation then
        raise exception 'command must reference current daily plan generation';
    end if;
    return new;
end;
$$;

create trigger trg_irrigation_command_current_daily_plan
before insert on public.irrigation_command_plans
for each row execute function public.irrigation_command_require_current_daily_plan();

create function public.irrigation_command_approval_require_current_daily_plan()
returns trigger language plpgsql as $$
declare selected integer;
begin
    if new.state = 'approved_not_dispatched' then
        select i.current_generation into selected
          from public.irrigation_command_plans p
          join public.irrigation_daily_plan_identities i
            on i.daily_plan_id=p.daily_plan_id
           and i.operating_date=p.daily_plan_operating_date
         where p.command_id=new.command_id;
        if selected is null or selected <> (
            select daily_plan_generation from public.irrigation_command_plans
             where command_id=new.command_id
        ) then
            raise exception 'only the current daily plan generation may be approved';
        end if;
    end if;
    return new;
end;
$$;

create trigger trg_irrigation_command_approval_current_daily_plan
before insert on public.irrigation_command_state_events
for each row execute function public.irrigation_command_approval_require_current_daily_plan();

create function public.rootline_generate_daily_irrigation_plan(
    p_daily_plan_id text, p_operating_date date, p_timezone text,
    p_status text, p_evidence_sha256 text, p_evidence_observed_at timestamptz,
    p_replacement_reason text, p_evidence jsonb, p_zones jsonb,
    out created boolean, out superseded_generation integer, out generation integer
) returns record
language plpgsql security definer set search_path = public, pg_temp as $$
declare current_hash text;
begin
    if p_timezone <> 'Africa/Johannesburg' then
        raise exception 'invalid operating timezone';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('rootline-daily-plan:' || p_operating_date, 0));
    select i.current_generation, g.evidence_sha256
      into superseded_generation, current_hash
      from irrigation_daily_plan_identities i
      join irrigation_daily_plan_generations g
        on g.daily_plan_id=i.daily_plan_id and g.generation=i.current_generation
     where i.operating_date=p_operating_date;
    if current_hash = p_evidence_sha256 then
        created := false; generation := superseded_generation; superseded_generation := null;
        return;
    end if;
    generation := coalesce(superseded_generation, 0) + 1;
    if superseded_generation is null then
        insert into irrigation_daily_plan_identities
          (daily_plan_id,operating_date,operating_timezone,current_generation)
        values (p_daily_plan_id,p_operating_date,p_timezone,generation);
    end if;
    insert into irrigation_daily_plan_generations
      (daily_plan_id,generation,operating_date,status,evidence_observed_at,
       replacement_reason,evidence_sha256,evidence_json,zones_json)
    values (p_daily_plan_id,generation,p_operating_date,
       p_status,
       p_evidence_observed_at,p_replacement_reason,p_evidence_sha256,p_evidence,p_zones);
    if superseded_generation is not null then
        update irrigation_daily_plan_identities
           set current_generation=generation,current_selected_at=now()
         where daily_plan_id=p_daily_plan_id;
    end if;
    created := true;
end;
$$;

alter table public.irrigation_daily_plan_identities enable row level security;
alter table public.irrigation_daily_plan_generations enable row level security;

revoke all on table public.irrigation_daily_plan_identities,
    public.irrigation_daily_plan_generations from public, anon, authenticated, service_role;
revoke execute on function public.irrigation_daily_plan_block_history_mutation(),
    public.irrigation_command_require_current_daily_plan(),
    public.irrigation_command_approval_require_current_daily_plan(),
    public.rootline_generate_daily_irrigation_plan(text,date,text,text,text,timestamptz,text,jsonb,jsonb)
    from public, anon, authenticated;
revoke all on function public.irrigation_daily_plan_block_history_mutation(),
    public.irrigation_command_require_current_daily_plan(),
    public.irrigation_command_approval_require_current_daily_plan(),
    public.rootline_generate_daily_irrigation_plan(text,date,text,text,text,timestamptz,text,jsonb,jsonb)
    from service_role;
grant select on table public.irrigation_daily_plan_identities,
    public.irrigation_daily_plan_generations to service_role;
grant execute on function
    public.rootline_generate_daily_irrigation_plan(text,date,text,text,text,timestamptz,text,jsonb,jsonb)
    to service_role;

insert into app_private.migration_log (migration_id, description)
values ('202607260005_create_irrigation_daily_plans',
        'Create canonical immutable-generation ROOTLINE daily irrigation plans.')
on conflict (migration_id) do nothing;
