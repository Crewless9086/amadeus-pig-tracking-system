-- Reuse irrigation_events as ROOTLINE's append-only typed execution/history rail.
-- No scheduler, transport, command or hardware authority is created here.

create or replace function public.irrigation_events_block_update_delete()
returns trigger language plpgsql as $$
begin
    raise exception 'irrigation_events is append-only';
end;
$$;

drop trigger if exists trg_irrigation_events_no_update_delete on public.irrigation_events;
create trigger trg_irrigation_events_no_update_delete
before update or delete on public.irrigation_events
for each row execute function public.irrigation_events_block_update_delete();

create unique index if not exists irrigation_events_rootline_execution_phase_uq
on public.irrigation_events (
    (details->>'execution_id'), event_type, (coalesce(details->>'attempt',''))
)
where details->>'contract_version' = 'rootline_irrigation_outcome_v1';

create index if not exists irrigation_events_rootline_zone_cutoff_idx
on public.irrigation_events (zone_id, event_at desc, irrigation_event_id)
where zone_id in ('B12345','C12345');

create or replace function public.rootline_append_typed_irrigation_event(
    p_event_id text, p_event_at timestamptz, p_event_type text, p_zone_id text,
    p_planned_minutes numeric, p_actual_minutes numeric, p_details jsonb
) returns boolean
language plpgsql security definer set search_path=public,pg_temp as $$
begin
    if p_zone_id not in ('B12345','C12345')
       or p_event_type not in ('PLANNING_EPOCH_STARTED','PLANNED','STARTED',
          'TRANSPORT_ACCEPTED','NATIVE_FAIL_STOP_ARMED','TEST_PULSE','PARTIAL',
          'STOPPED','SHUTDOWN_VERIFIED','COMPLETED','CONTAINED','AMBIGUOUS','OFF_ATTEMPT')
       or p_details->>'contract_version' <> 'rootline_irrigation_outcome_v1'
       or coalesce(p_details->>'event_sha256','') !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid typed ROOTLINE irrigation event';
    end if;
    insert into public.irrigation_events(
        irrigation_event_id,source_id,event_at,event_type,actor,zone_id,
        planned_minutes,actual_minutes,details)
    values (p_event_id,'irrigation-controller-main',p_event_at,p_event_type,'ROOTLINE',
            p_zone_id,p_planned_minutes,p_actual_minutes,p_details)
    on conflict (irrigation_event_id) do nothing;
    return found;
end; $$;

revoke insert, update, delete, truncate on public.irrigation_events
from public, anon, authenticated, service_role;
revoke execute on function public.rootline_append_typed_irrigation_event(
    text,timestamptz,text,text,numeric,numeric,jsonb) from public,anon,authenticated;
grant execute on function public.rootline_append_typed_irrigation_event(
    text,timestamptz,text,text,numeric,numeric,jsonb) to service_role;

revoke execute on function public.irrigation_events_block_update_delete()
from public, anon, authenticated;

insert into app_private.migration_log (migration_id, description)
values ('202608050001_harden_irrigation_events_history',
        'Make existing irrigation_events append-only and bind unique typed ROOTLINE execution phases.')
on conflict (migration_id) do nothing;
