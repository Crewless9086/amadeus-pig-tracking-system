-- ROOTLINE owner-reviewed Operating Knowledge policy versions.
--
-- Additive and unapplied. This stores immutable advice-policy proposals and
-- lifecycle evidence only. It has no plan, command, schedule, workflow,
-- transport, retry, IFTTT, n8n, telemetry-write, or hardware authority.

create table public.rootline_operating_policy_versions (
    policy_id text not null check (policy_id = 'ROOTLINE-OPERATING-KNOWLEDGE'),
    version integer not null check (version > 0),
    proposal_id text primary key check (proposal_id ~ '^ROOTLINE-POLICY-[0-9A-F]{24}$'),
    proposal_sha256 text not null check (proposal_sha256 ~ '^[0-9a-f]{64}$'),
    idempotency_key text not null unique check (btrim(idempotency_key) <> ''),
    policy_json jsonb not null check (jsonb_typeof(policy_json) = 'object'),
    evidence_json jsonb not null check (jsonb_typeof(evidence_json) = 'object'),
    proposed_by text not null check (btrim(proposed_by) <> ''),
    proposed_at timestamptz not null,
    canary_runtime_used boolean not null default false check (canary_runtime_used = false),
    measured_water_inferred boolean not null default false check (measured_water_inferred = false),
    successful_routine_irrigation_inferred boolean not null default false
        check (successful_routine_irrigation_inferred = false),
    writes_farm_data boolean not null default false check (writes_farm_data = false),
    writes_telemetry boolean not null default false check (writes_telemetry = false),
    generates_plan boolean not null default false check (generates_plan = false),
    creates_command boolean not null default false check (creates_command = false),
    mutates_schedule boolean not null default false check (mutates_schedule = false),
    activates_workflow boolean not null default false check (activates_workflow = false),
    calls_ifttt boolean not null default false check (calls_ifttt = false),
    calls_n8n boolean not null default false check (calls_n8n = false),
    controls_hardware boolean not null default false check (controls_hardware = false),
    automatic_retry boolean not null default false check (automatic_retry = false),
    recorded_at timestamptz not null default now(),
    unique (policy_id, version)
);

create table public.rootline_operating_policy_events (
    event_id text primary key check (event_id ~ '^ROOTLINE-POLICY-EVENT-[0-9A-F]{24}$'),
    proposal_id text not null
        references public.rootline_operating_policy_versions(proposal_id) on delete restrict,
    policy_id text not null check (policy_id = 'ROOTLINE-OPERATING-KNOWLEDGE'),
    version integer not null check (version > 0),
    event_sequence bigint generated always as identity,
    state text not null check (state in ('proposed', 'owner_reviewed', 'active_for_advice')),
    actor_identity text not null check (btrim(actor_identity) <> ''),
    evidence_json jsonb not null check (jsonb_typeof(evidence_json) = 'object'),
    idempotency_key text not null unique check (btrim(idempotency_key) <> ''),
    occurred_at timestamptz not null,
    effective_at timestamptz,
    transition_sha256 text,
    writes_farm_data boolean not null default false check (writes_farm_data = false),
    writes_telemetry boolean not null default false check (writes_telemetry = false),
    generates_plan boolean not null default false check (generates_plan = false),
    creates_command boolean not null default false check (creates_command = false),
    mutates_schedule boolean not null default false check (mutates_schedule = false),
    activates_workflow boolean not null default false check (activates_workflow = false),
    calls_ifttt boolean not null default false check (calls_ifttt = false),
    calls_n8n boolean not null default false check (calls_n8n = false),
    controls_hardware boolean not null default false check (controls_hardware = false),
    automatic_retry boolean not null default false check (automatic_retry = false),
    recorded_at timestamptz not null default now(),
    unique (proposal_id, state),
    check (
        (state = 'active_for_advice' and effective_at is not null)
        or (state <> 'active_for_advice' and effective_at is null)
    ),
    check (
        (state = 'proposed' and transition_sha256 is null)
        or (state <> 'proposed' and transition_sha256 ~ '^[0-9a-f]{64}$')
    )
);

create index rootline_operating_policy_versions_latest_idx
    on public.rootline_operating_policy_versions(policy_id, version desc);
create index rootline_operating_policy_events_current_idx
    on public.rootline_operating_policy_events(policy_id, event_sequence desc);

alter table public.rootline_operating_policy_versions enable row level security;
alter table public.rootline_operating_policy_events enable row level security;

create function public.rootline_policy_event_id(
    p_proposal_id text, p_state text, p_idempotency_key text
) returns text
language sql
immutable
strict
set search_path = public, pg_temp
as $$
    select 'ROOTLINE-POLICY-EVENT-' ||
           upper(substr(md5(p_proposal_id || ':' || p_state || ':' || p_idempotency_key), 1, 24))
$$;

create function public.rootline_append_operating_policy_proposal(
    p_policy_id text,
    p_proposal_id text,
    p_proposal_sha256 text,
    p_idempotency_key text,
    p_policy_json jsonb,
    p_evidence_json jsonb,
    p_proposed_by text,
    p_proposed_at timestamptz
) returns table(version integer, created boolean, stored_proposed_at timestamptz)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    existing public.rootline_operating_policy_versions%rowtype;
    next_version integer;
begin
    if p_policy_id <> 'ROOTLINE-OPERATING-KNOWLEDGE' then
        raise exception 'invalid_policy_identity';
    end if;
    perform pg_advisory_xact_lock(hashtext(p_policy_id));

    select * into existing
    from public.rootline_operating_policy_versions
    where idempotency_key = p_idempotency_key;
    if found then
        if existing.proposal_sha256 is distinct from p_proposal_sha256
           or existing.proposal_id is distinct from p_proposal_id
           or existing.policy_json is distinct from p_policy_json
           or existing.evidence_json is distinct from p_evidence_json
           or existing.proposed_by is distinct from p_proposed_by then
            raise exception 'proposal_idempotency_conflict';
        end if;
        return query select existing.version, false, existing.proposed_at;
        return;
    end if;

    select coalesce(max(v.version), 0) + 1 into next_version
    from public.rootline_operating_policy_versions v
    where v.policy_id = p_policy_id;

    insert into public.rootline_operating_policy_versions (
        policy_id, version, proposal_id, proposal_sha256, idempotency_key,
        policy_json, evidence_json, proposed_by, proposed_at
    ) values (
        p_policy_id, next_version, p_proposal_id, p_proposal_sha256,
        p_idempotency_key, p_policy_json, p_evidence_json, p_proposed_by,
        p_proposed_at
    );

    insert into public.rootline_operating_policy_events (
        event_id, proposal_id, policy_id, version, state, actor_identity,
        evidence_json, idempotency_key, occurred_at
    ) values (
        public.rootline_policy_event_id(p_proposal_id, 'proposed', p_idempotency_key),
        p_proposal_id, p_policy_id, next_version, 'proposed', p_proposed_by,
        p_evidence_json, 'proposal:' || p_idempotency_key, p_proposed_at
    );
    return query select next_version, true, p_proposed_at;
end;
$$;

create function public.rootline_append_operating_policy_transition(
    p_proposal_id text,
    p_state text,
    p_actor_identity text,
    p_evidence_json jsonb,
    p_idempotency_key text,
    p_occurred_at timestamptz,
    p_effective_at timestamptz,
    p_transition_sha256 text
) returns table(created boolean, stored_effective_at timestamptz)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
    proposal public.rootline_operating_policy_versions%rowtype;
    existing public.rootline_operating_policy_events%rowtype;
    latest_version integer;
    has_required boolean;
begin
    if p_state not in ('owner_reviewed', 'active_for_advice') then
        raise exception 'invalid_policy_transition';
    end if;
    if p_transition_sha256 is null
       or p_transition_sha256 !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid_transition_sha256';
    end if;
    select * into proposal
    from public.rootline_operating_policy_versions
    where proposal_id = p_proposal_id;
    if not found then
        raise exception 'policy_proposal_not_found';
    end if;
    perform pg_advisory_xact_lock(hashtext(proposal.policy_id));

    select * into existing
    from public.rootline_operating_policy_events
    where idempotency_key = p_idempotency_key;
    if found then
        if existing.proposal_id is distinct from p_proposal_id
           or existing.state is distinct from p_state
           or existing.actor_identity is distinct from p_actor_identity
           or existing.evidence_json is distinct from p_evidence_json
           or existing.effective_at is distinct from p_effective_at
           or existing.transition_sha256 is distinct from p_transition_sha256 then
            raise exception 'transition_idempotency_conflict';
        end if;
        return query select false, existing.effective_at;
        return;
    end if;

    select max(v.version) into latest_version
    from public.rootline_operating_policy_versions v
    where v.policy_id = proposal.policy_id;
    if proposal.version <> latest_version then
        raise exception 'stale_policy_version';
    end if;

    if exists (
        select 1 from public.rootline_operating_policy_events e
        where e.proposal_id = p_proposal_id and e.state = p_state
    ) then
        raise exception 'conflicting_transition';
    end if;

    select exists (
        select 1 from public.rootline_operating_policy_events e
        where e.proposal_id = p_proposal_id
          and e.state = case when p_state = 'owner_reviewed'
                             then 'proposed' else 'owner_reviewed' end
    ) into has_required;
    if not has_required then
        if p_state = 'owner_reviewed' then
            raise exception 'proposed_state_required';
        else
            raise exception 'owner_reviewed_state_required';
        end if;
    end if;

    if (p_state = 'active_for_advice') <> (p_effective_at is not null) then
        raise exception 'activation_effective_time_required';
    end if;
    if p_state = 'active_for_advice' and p_effective_at < p_occurred_at then
        raise exception 'effective_time_must_not_precede_activation';
    end if;

    insert into public.rootline_operating_policy_events (
        event_id, proposal_id, policy_id, version, state, actor_identity,
        evidence_json, idempotency_key, occurred_at, effective_at,
        transition_sha256
    ) values (
        public.rootline_policy_event_id(p_proposal_id, p_state, p_idempotency_key),
        p_proposal_id, proposal.policy_id, proposal.version, p_state,
        p_actor_identity, p_evidence_json, p_idempotency_key, p_occurred_at,
        p_effective_at, p_transition_sha256
    );
    return query select true, p_effective_at;
end;
$$;

create function public.rootline_policy_ledger_block_mutation()
returns trigger
language plpgsql
set search_path = public, pg_temp
as $$
begin
    raise exception 'rootline operating policy history is append-only';
end;
$$;

create trigger trg_rootline_policy_versions_no_update_delete
    before update or delete on public.rootline_operating_policy_versions
    for each row execute function public.rootline_policy_ledger_block_mutation();
create trigger trg_rootline_policy_events_no_update_delete
    before update or delete on public.rootline_operating_policy_events
    for each row execute function public.rootline_policy_ledger_block_mutation();

revoke all privileges on table public.rootline_operating_policy_versions
    from public, anon, authenticated, service_role;
revoke all privileges on table public.rootline_operating_policy_events
    from public, anon, authenticated, service_role;
revoke all privileges on sequence public.rootline_operating_policy_events_event_sequence_seq
    from public, anon, authenticated, service_role;
revoke execute on function public.rootline_policy_event_id(text,text,text)
    from public, anon, authenticated, service_role;
revoke execute on function public.rootline_append_operating_policy_proposal(
    text,text,text,text,jsonb,jsonb,text,timestamptz
) from public, anon, authenticated, service_role;
revoke execute on function public.rootline_append_operating_policy_transition(
    text,text,text,jsonb,text,timestamptz,timestamptz,text
) from public, anon, authenticated, service_role;
revoke execute on function public.rootline_policy_ledger_block_mutation()
    from public, anon, authenticated, service_role;

grant select on table public.rootline_operating_policy_versions to service_role;
grant select on table public.rootline_operating_policy_events to service_role;
grant execute on function public.rootline_append_operating_policy_proposal(
    text,text,text,text,jsonb,jsonb,text,timestamptz
) to service_role;
grant execute on function public.rootline_append_operating_policy_transition(
    text,text,text,jsonb,text,timestamptz,timestamptz,text
) to service_role;

insert into app_private.migration_log (migration_id, description)
values (
    '202607270002_create_rootline_operating_policies',
    'Create immutable owner-reviewed ROOTLINE advice-policy versions and lifecycle events with zero irrigation authority.'
)
on conflict (migration_id) do nothing;
