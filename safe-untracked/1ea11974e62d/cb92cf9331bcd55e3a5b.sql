-- CMQ-20260813-05-SLACK-GATEWAY: additive connection separation only.
-- Never alter the shared postgres/service_role principals or the applied hold
-- migration. Password provisioning and environment selection are separate,
-- explicitly approved release operations. No password is contained here.
do $roles$
begin
    if not exists (select 1 from pg_roles where rolname = 'charlie_mission_application') then
        create role charlie_mission_application login nosuperuser nobypassrls
            nocreatedb nocreaterole noreplication noinherit;
    end if;
    if exists (
        select 1 from pg_roles r
        where r.rolname in ('charlie_mission_application', 'charlie_owner_execution_hold_writer')
          and (r.rolsuper or r.rolbypassrls or r.rolcreatedb or r.rolcreaterole
               or r.rolreplication or r.rolinherit or not r.rolcanlogin
               or exists (select 1 from pg_auth_members m where m.member = r.oid))
    ) or not exists (select 1 from pg_roles where rolname = 'charlie_owner_execution_hold_writer') then
        raise exception 'charlie_database_principal_requires_owner_reconciliation';
    end if;
end
$roles$;

grant usage on schema public, app_private
    to charlie_mission_application, charlie_owner_execution_hold_writer;

-- Finite caller inventory: mission_store and its explicitly delegated vault
-- writes. No ALL TABLES, default privileges, role membership or BYPASSRLS.
grant select, insert, update on public.charlie_missions,
    public.charlie_mission_events, public.operational_projection_checkpoints,
    public.charlie_vault_projects, public.charlie_vault_artifacts,
    public.charlie_agent_runs, public.charlie_handoff_reports,
    public.charlie_quality_gates, public.charlie_deployments,
    public.charlie_lessons, public.charlie_income_stream_reviews
    to charlie_mission_application;
grant select, insert on public.operational_events, public.charlie_owner_decisions,
    public.charlie_audit_log to charlie_mission_application;
grant select on public.charlie_owner_execution_hold_events to charlie_mission_application;

-- Existing importers of mission_store._connect/_database_url share this
-- canonical application principal. Preserve their actual finite SQL surface.
grant select, insert, update on public.charlie_executive_goals,
    public.charlie_control_commands, public.charlie_recovery_cases,
    public.charlie_capability_trust, public.charlie_eval_registry,
    public.charlie_research_radar, public.charlie_notification_outbox,
    public.charlie_owner_bindings, public.charlie_conversation_threads,
    public.charlie_brief_subscriptions, public.charlie_inbound_updates,
    public.charlie_approval_bundles, public.charlie_owner_preferences,
    public.domain_observer_feedback to charlie_mission_application;
grant select, insert on public.charlie_conversation_messages,
    public.charlie_owner_intents, public.charlie_tool_executions,
    public.domain_observer_runs to charlie_mission_application;
grant select on public.charlie_delegation_policies to charlie_mission_application;

do $policies$
declare target text;
begin
    foreach target in array array[
        'charlie_missions', 'charlie_mission_events', 'operational_events',
        'operational_projection_checkpoints', 'charlie_vault_projects',
        'charlie_vault_artifacts', 'charlie_agent_runs', 'charlie_handoff_reports',
        'charlie_quality_gates', 'charlie_owner_decisions', 'charlie_deployments',
        'charlie_audit_log', 'charlie_lessons', 'charlie_income_stream_reviews',
        'charlie_executive_goals', 'charlie_control_commands', 'charlie_recovery_cases',
        'charlie_capability_trust', 'charlie_eval_registry', 'charlie_research_radar',
        'charlie_notification_outbox', 'charlie_owner_bindings', 'charlie_conversation_threads',
        'charlie_brief_subscriptions', 'charlie_inbound_updates', 'charlie_approval_bundles',
        'charlie_owner_preferences', 'domain_observer_feedback', 'charlie_conversation_messages',
        'charlie_owner_intents', 'charlie_tool_executions', 'domain_observer_runs',
        'charlie_delegation_policies'
    ] loop
        -- Preserve each relation's existing RLS enablement and other policies.
        execute format('drop policy if exists charlie_mission_application_access on public.%I', target);
        execute format('create policy charlie_mission_application_access on public.%I to charlie_mission_application using (true) with check (true)', target);
    end loop;
end
$policies$;

drop policy if exists charlie_mission_application_hold_read on public.charlie_owner_execution_hold_events;
create policy charlie_mission_application_hold_read
    on public.charlie_owner_execution_hold_events for select
    to charlie_mission_application using (true);

-- Check effective privileges rather than silently removing somebody else's
-- grants. Role attributes/memberships above stop migration; effective privilege
-- drift below stops connection qualification before application SQL runs.
create or replace function app_private.assert_charlie_mission_connection(requested_purpose text)
returns table(contract text, database_role name, connection_purpose text, hold_visibility boolean)
language plpgsql security invoker
set search_path = pg_catalog
as $connection$
declare
    principal pg_catalog.pg_roles%rowtype;
    hold_relation pg_catalog.pg_class%rowtype;
    writer boolean;
    function_name text;
    relation_name text;
    relation_oid oid;
    relation_rls boolean;
begin
    select * into strict principal from pg_catalog.pg_roles where rolname = current_user;
    writer := principal.rolname = 'charlie_owner_execution_hold_writer';
    if session_user <> current_user
       or principal.rolname not in ('charlie_mission_application', 'charlie_owner_execution_hold_writer')
       or requested_purpose not in ('application', 'hold_writer', 'hold_read')
       or requested_purpose is null
       or (requested_purpose = 'application' and writer)
       or (requested_purpose = 'hold_writer' and not writer)
       or principal.rolsuper or principal.rolbypassrls or principal.rolcreatedb
       or principal.rolcreaterole or principal.rolreplication or principal.rolinherit
       or not principal.rolcanlogin
       or exists (select 1 from pg_catalog.pg_auth_members where member = principal.oid)
       or exists (select 1 from pg_catalog.pg_class where relowner = principal.oid)
       or exists (select 1 from pg_catalog.pg_proc where proowner = principal.oid)
       or exists (select 1 from pg_catalog.pg_database where datdba = principal.oid)
       or pg_catalog.has_schema_privilege(current_user, 'public', 'CREATE')
       or pg_catalog.has_schema_privilege(current_user, 'app_private', 'CREATE') then
        raise exception 'charlie_database_principal_unsafe' using errcode = '42501';
    end if;

    if writer and exists (
        select 1 from pg_catalog.pg_class c
        join pg_catalog.pg_namespace n on n.oid = c.relnamespace
        where n.nspname in ('public', 'app_private') and c.relkind in ('r','p','v','f')
          and (pg_catalog.has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
               or exists (select 1 from pg_catalog.pg_attribute a
                          where a.attrelid=c.oid and a.attnum>0 and not a.attisdropped
                            and pg_catalog.has_column_privilege(current_user,c.oid,a.attnum,'INSERT,UPDATE,REFERENCES')))
    ) then
        raise exception 'charlie_hold_writer_direct_write_unsafe' using errcode = '42501';
    end if;

    -- ACCESS SHARE permits the existing append/veto path, but conflicts with
    -- policy DDL's ACCESS EXCLUSIVE lock. The caller retains this transaction.
    lock table public.charlie_owner_execution_hold_events in access share mode;
    select * into strict hold_relation from pg_catalog.pg_class
        where oid = 'public.charlie_owner_execution_hold_events'::pg_catalog.regclass;
    if hold_relation.relowner = principal.oid or not hold_relation.relrowsecurity
       or not pg_catalog.has_table_privilege(current_user, hold_relation.oid, 'SELECT')
       or pg_catalog.has_table_privilege(current_user, hold_relation.oid, 'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
       or exists (select 1 from pg_catalog.pg_attribute a
                  where a.attrelid = hold_relation.oid and a.attnum > 0 and not a.attisdropped
                    and pg_catalog.has_column_privilege(current_user, a.attrelid, a.attnum, 'INSERT,UPDATE,REFERENCES')) then
        raise exception 'charlie_hold_privileges_unsafe' using errcode = '42501';
    end if;

    -- With no inherited roles, only PUBLIC and this exact role can apply.
    -- An unconditional permissive SELECT must exist. Every applicable
    -- restrictive SELECT must also be literally true; arbitrary predicates
    -- are deliberately not guessed/evaluated against today's row sample.
    if not exists (
        select 1 from pg_catalog.pg_policy p
        where p.polrelid = hold_relation.oid and p.polcmd in ('r', '*')
          and p.polpermissive and (0::oid = any(p.polroles) or principal.oid = any(p.polroles))
          and pg_catalog.pg_get_expr(p.polqual, p.polrelid) = 'true'
    ) or exists (
        select 1 from pg_catalog.pg_policy p
        where p.polrelid = hold_relation.oid and p.polcmd in ('r', '*')
          and not p.polpermissive and (0::oid = any(p.polroles) or principal.oid = any(p.polroles))
          and pg_catalog.pg_get_expr(p.polqual, p.polrelid) is distinct from 'true'
    ) then
        raise exception 'charlie_hold_visibility_unverified' using errcode = '42501';
    end if;

    -- A hidden competing mission or recovery receipt must not look like zero
    -- writers or an unused budget. Preserve existing RLS enablement, but attest
    -- complete SELECT visibility for the canonical relations this role reads.
    foreach relation_name in array case when writer then array['charlie_missions'] else
        array['charlie_missions','charlie_mission_events','operational_events','operational_projection_checkpoints'] end
    loop
        execute format('lock table public.%I in access share mode',relation_name);
        select c.oid,c.relrowsecurity into strict relation_oid,relation_rls
          from pg_catalog.pg_class c join pg_catalog.pg_namespace n on n.oid=c.relnamespace
          where n.nspname='public' and c.relname=relation_name;
        if not pg_catalog.has_table_privilege(current_user,relation_oid,'SELECT') then
            raise exception 'charlie_canonical_read_access_missing' using errcode = '42501';
        end if;
        if relation_rls and (
            not exists (select 1 from pg_catalog.pg_policy p where p.polrelid=relation_oid
                and p.polcmd in ('r','*') and p.polpermissive
                and (0::oid=any(p.polroles) or principal.oid=any(p.polroles))
                and pg_catalog.pg_get_expr(p.polqual,p.polrelid)='true')
            or exists (select 1 from pg_catalog.pg_policy p where p.polrelid=relation_oid
                and p.polcmd in ('r','*') and not p.polpermissive
                and (0::oid=any(p.polroles) or principal.oid=any(p.polroles))
                and pg_catalog.pg_get_expr(p.polqual,p.polrelid) is distinct from 'true')
        ) then
            raise exception 'charlie_canonical_visibility_unverified' using errcode = '42501';
        end if;
    end loop;

    foreach function_name in array array[
        'public.append_charlie_owner_execution_hold(text,text,text,text,text,text,jsonb)',
        'public.append_charlie_owner_execution_hold_release(text,text,text,text,text,text,text,jsonb)'
    ] loop
        if pg_catalog.has_function_privilege(current_user, function_name, 'EXECUTE') is distinct from writer then
            raise exception 'charlie_hold_function_authority_unsafe' using errcode = '42501';
        end if;
    end loop;
    return query select 'charlie_mission_connection_v1'::text, current_user,
                        requested_purpose, true;
end
$connection$;
revoke all on function app_private.assert_charlie_mission_connection(text) from public;
grant execute on function app_private.assert_charlie_mission_connection(text)
    to charlie_mission_application, charlie_owner_execution_hold_writer;

insert into app_private.migration_log(migration_id, description)
values ('20260908141447_qualify_charlie_mission_database_privileges',
        'Separate mission application and owner hold-writer connections; fail closed on unsafe identity or incomplete hold visibility.')
on conflict (migration_id) do nothing;
