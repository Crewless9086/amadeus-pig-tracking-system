-- Supabase installs pgcrypto in the extensions schema. Plain PostgreSQL may
-- install it in public, so normalize both environments to one protected
-- extension schema before changing the SECURITY DEFINER function.
create schema if not exists extensions;
revoke create on schema extensions from public, anon, authenticated, service_role;
alter extension pgcrypto set schema extensions;

alter function public.rootline_append_water_balance_event(
  text,text,timestamptz,timestamptz,text,jsonb
) set search_path = pg_catalog, extensions, pg_temp;

insert into app_private.migration_log(migration_id,description)
values('202608090002_fix_rootline_water_balance_pgcrypto_search_path',
  'Allow the ROOTLINE water-balance append function to resolve pgcrypto from the protected Supabase extensions schema.')
on conflict(migration_id) do nothing;
