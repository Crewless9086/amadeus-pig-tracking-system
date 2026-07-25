-- ROOTLINE Phase B1 plan-only irrigation command and evidence ledger.
--
-- Additive and unapplied.  This schema has no dispatch, transport, retry,
-- schedule, IFTTT, n8n, valve, pump, borehole, or hardware authority.

create table if not exists public.irrigation_command_plans (
    command_id text primary key check (btrim(command_id) <> ''),
    generation integer not null check (generation > 0),
    zone_id text not null check (zone_id in ('B12345', 'C12345')),
    zone_name text not null check (btrim(zone_name) <> ''),
    intent text not null check (intent in ('ON', 'OFF')),
    requested_duration_minutes integer not null check (requested_duration_minutes > 0),
    created_at timestamptz not null,
    expires_at timestamptz not null check (expires_at > created_at),
    idempotency_key text not null unique check (btrim(idempotency_key) <> ''),
    request_sha256 text not null check (request_sha256 ~ '^[0-9a-f]{64}$'),
    paired_off_required boolean not null,
    paired_off_command_id text,
    weather_evidence jsonb not null check (jsonb_typeof(weather_evidence) = 'object'),
    power_evidence jsonb not null check (jsonb_typeof(power_evidence) = 'object'),
    water_infrastructure_evidence jsonb not null
        check (jsonb_typeof(water_infrastructure_evidence) = 'object'),
    controller_actuator_inventory jsonb not null
        check (jsonb_typeof(controller_actuator_inventory) = 'object'),
    safety_interlocks jsonb not null check (jsonb_typeof(safety_interlocks) = 'object'),
    prohibition_reasons jsonb not null check (jsonb_typeof(prohibition_reasons) = 'array'),
    command_json jsonb not null check (jsonb_typeof(command_json) = 'object'),
    recorded_by text not null check (btrim(recorded_by) <> ''),
    writes_farm_data boolean not null default false check (writes_farm_data = false),
    writes_telemetry boolean not null default false check (writes_telemetry = false),
    mutates_schedule boolean not null default false check (mutates_schedule = false),
    calls_ifttt boolean not null default false check (calls_ifttt = false),
    calls_n8n boolean not null default false check (calls_n8n = false),
    controls_hardware boolean not null default false check (controls_hardware = false),
    dispatchable boolean not null default false check (dispatchable = false),
    automatic_retry boolean not null default false check (automatic_retry = false),
    recorded_at timestamptz not null default now(),
    unique (zone_id, generation),
    check (intent = 'OFF' or paired_off_required),
    check (intent = 'OFF' or btrim(coalesce(paired_off_command_id, '')) <> '')
);

create table if not exists public.irrigation_command_state_events (
    event_id text primary key check (btrim(event_id) <> ''),
    command_id text not null
        references public.irrigation_command_plans(command_id) on delete restrict,
    generation integer not null check (generation > 0),
    event_sequence bigint generated always as identity,
    state text not null check (state in (
        'proposed',
        'awaiting_owner_approval',
        'approved_not_dispatched',
        'expired',
        'cancelled',
        'execution_prohibited'
    )),
    occurred_at timestamptz not null,
    owner_approval_identity text,
    evidence_json jsonb not null check (jsonb_typeof(evidence_json) = 'object'),
    writes_farm_data boolean not null default false check (writes_farm_data = false),
    writes_telemetry boolean not null default false check (writes_telemetry = false),
    mutates_schedule boolean not null default false check (mutates_schedule = false),
    calls_ifttt boolean not null default false check (calls_ifttt = false),
    calls_n8n boolean not null default false check (calls_n8n = false),
    controls_hardware boolean not null default false check (controls_hardware = false),
    dispatchable boolean not null default false check (dispatchable = false),
    automatic_retry boolean not null default false check (automatic_retry = false),
    recorded_at timestamptz not null default now(),
    unique (command_id, event_sequence),
    check (
        (state = 'approved_not_dispatched' and btrim(coalesce(owner_approval_identity, '')) <> '')
        or (state <> 'approved_not_dispatched' and owner_approval_identity is null)
    )
);

create index if not exists irrigation_command_plans_zone_created_idx
    on public.irrigation_command_plans(zone_id, created_at desc, command_id);
create index if not exists irrigation_command_state_events_command_sequence_idx
    on public.irrigation_command_state_events(command_id, event_sequence desc);

alter table public.irrigation_command_plans enable row level security;
alter table public.irrigation_command_state_events enable row level security;

create or replace function public.irrigation_command_ledger_block_update_delete()
returns trigger
language plpgsql
as $$
begin
    raise exception 'irrigation command ledger is append-only';
end;
$$;

drop trigger if exists trg_irrigation_command_plans_no_update_delete
    on public.irrigation_command_plans;
create trigger trg_irrigation_command_plans_no_update_delete
    before update or delete on public.irrigation_command_plans
    for each row execute function public.irrigation_command_ledger_block_update_delete();

drop trigger if exists trg_irrigation_command_state_events_no_update_delete
    on public.irrigation_command_state_events;
create trigger trg_irrigation_command_state_events_no_update_delete
    before update or delete on public.irrigation_command_state_events
    for each row execute function public.irrigation_command_ledger_block_update_delete();

insert into app_private.migration_log (migration_id, description)
values (
    '202607250002_create_irrigation_command_ledger',
    'Create append-only ROOTLINE plan-only irrigation command and evidence ledger with no dispatch authority.'
)
on conflict (migration_id) do nothing;
