-- Extend the existing append-only typed irrigation history to A only.
-- This creates no device, commissioning, standing authority, policy or water credit.
-- Historical B/C rows, the original index and all append-only triggers remain intact.

do $$ begin
    if not exists (
        select 1 from pg_proc p join pg_language l on l.oid=p.prolang
        where p.oid=to_regprocedure('public.rootline_append_typed_irrigation_event(text,timestamp with time zone,text,text,numeric,numeric,jsonb)')
          and p.prosecdef is true and p.prorettype='boolean'::regtype
          and l.lanname='plpgsql' and p.proconfig=array['search_path=public, pg_temp']
          and md5(btrim(replace(p.prosrc, chr(13), ''), E' \n\r\t')) in ('1f14429f393db0f46a8044c4af8c1e6f','43e52b641c83edf408885a3ecb524abd')
    ) then
        raise exception 'ROOTLINE typed irrigation history prerequisite differs';
    end if;
end $$;

create index if not exists irrigation_events_rootline_abc_zone_cutoff_idx
on public.irrigation_events (zone_id, event_at desc, irrigation_event_id)
where zone_id in ('A12345','B12345','C12345');

create or replace function public.rootline_append_typed_irrigation_event(
    p_event_id text, p_event_at timestamptz, p_event_type text, p_zone_id text,
    p_planned_minutes numeric, p_actual_minutes numeric, p_details jsonb
) returns boolean
language plpgsql security definer set search_path=public,pg_temp as $$
begin
    if p_zone_id not in ('A12345','B12345','C12345')
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


-- Preserve the existing service-only append boundary and execution signature.
revoke execute on function public.rootline_append_typed_irrigation_event(
    text,timestamptz,text,text,numeric,numeric,jsonb) from public,anon,authenticated;
grant execute on function public.rootline_append_typed_irrigation_event(
    text,timestamptz,text,text,numeric,numeric,jsonb) to service_role;

insert into app_private.migration_log (migration_id, description)
values ('20261101150806_extend_rootline_a_irrigation_history',
        'Extend existing typed append-only irrigation history to independently governed A; no water credit or activation.')
on conflict (migration_id) do nothing;
