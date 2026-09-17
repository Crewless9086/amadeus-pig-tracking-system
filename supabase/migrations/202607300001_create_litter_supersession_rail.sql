-- Append-only governed correction overlay for duplicate litter representations.
-- Base litter, pig and audit rows remain immutable historical evidence.

create table if not exists public.litter_correction_authorizations (
    authorization_id text primary key,
    operation_id text not null unique,
    preview_sha256 text not null check (preview_sha256 ~ '^[0-9a-f]{64}$'),
    owner_principal text not null check (btrim(owner_principal) <> ''),
    decision_status text not null check (decision_status in ('confirmed', 'revoked')),
    confirmed_at timestamptz not null,
    created_at timestamptz not null default now()
);

create table if not exists public.litter_supersessions (
    operation_id text primary key,
    retained_litter_id text not null references public.litters(litter_id),
    superseded_litter_id text not null unique references public.litters(litter_id),
    authorization_id text not null unique references public.litter_correction_authorizations(authorization_id),
    mating_id text not null references public.mating_events(mating_id),
    preview_sha256 text not null check (preview_sha256 ~ '^[0-9a-f]{64}$'),
    reason text not null check (reason in ('duplicate_creation_same_farrowing')),
    superseded_child_ids jsonb not null check (jsonb_typeof(superseded_child_ids) = 'array'),
    retained_child_ids jsonb not null check (jsonb_typeof(retained_child_ids) = 'array'),
    reference_allowlist_sha256 text not null check (reference_allowlist_sha256 ~ '^[0-9a-f]{64}$'),
    skipped_audit_rows_sha256 text not null check (skipped_audit_rows_sha256 ~ '^[0-9a-f]{64}$'),
    input_sha256 text not null check (input_sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz not null default now(),
    check (retained_litter_id <> superseded_litter_id),
    check (jsonb_array_length(superseded_child_ids) > 0),
    check (jsonb_array_length(retained_child_ids) > 0)
);

create table if not exists public.litter_correction_authorization_revocations (
    authorization_id text primary key
      references public.litter_correction_authorizations(authorization_id),
    revoked_by text not null check (btrim(revoked_by) <> ''),
    revoked_at timestamptz not null default now(),
    reason text not null check (btrim(reason) <> '')
);

create table if not exists public.litter_cohort_dispositions (
    operation_id text not null references public.litter_supersessions(operation_id),
    pig_id text not null unique references public.pigs(pig_id),
    source_litter_id text not null references public.litters(litter_id),
    disposition text not null check (disposition = 'superseded_duplicate_representation'),
    created_at timestamptz not null default now(),
    primary key (operation_id, pig_id)
);

create table if not exists public.litter_supersession_audit_rows (
    operation_id text not null references public.litter_supersessions(operation_id),
    row_id uuid not null unique references public.bulk_weight_batch_rows(row_id),
    batch_id uuid not null references public.bulk_weight_batches(batch_id),
    created_at timestamptz not null default now(),
    primary key (operation_id, row_id)
);

create or replace function public.block_litter_correction_update_delete()
returns trigger language plpgsql as $$
begin
    raise exception 'litter correction evidence is append-only';
end;
$$;

drop trigger if exists litter_authorizations_append_only on public.litter_correction_authorizations;
create trigger litter_authorizations_append_only
before update or delete on public.litter_correction_authorizations
for each row execute function public.block_litter_correction_update_delete();

drop trigger if exists litter_supersessions_append_only on public.litter_supersessions;
create trigger litter_supersessions_append_only
before update or delete on public.litter_supersessions
for each row execute function public.block_litter_correction_update_delete();

drop trigger if exists litter_authorization_revocations_append_only
  on public.litter_correction_authorization_revocations;
create trigger litter_authorization_revocations_append_only
before update or delete on public.litter_correction_authorization_revocations
for each row execute function public.block_litter_correction_update_delete();

drop trigger if exists litter_dispositions_append_only on public.litter_cohort_dispositions;
create trigger litter_dispositions_append_only
before update or delete on public.litter_cohort_dispositions
for each row execute function public.block_litter_correction_update_delete();

drop trigger if exists litter_audit_evidence_append_only on public.litter_supersession_audit_rows;
create trigger litter_audit_evidence_append_only
before update or delete on public.litter_supersession_audit_rows
for each row execute function public.block_litter_correction_update_delete();

create or replace function public.validate_litter_supersession()
returns trigger language plpgsql as $$
declare
    retained public.litters%rowtype;
    superseded public.litters%rowtype;
    auth_row public.litter_correction_authorizations%rowtype;
begin
    select * into retained from public.litters where litter_id = new.retained_litter_id;
    select * into superseded from public.litters where litter_id = new.superseded_litter_id;
    select * into auth_row from public.litter_correction_authorizations
      where authorization_id = new.authorization_id;
    if retained.sow_pig_id is distinct from superseded.sow_pig_id
       or retained.boar_pig_id is distinct from superseded.boar_pig_id
       or retained.farrowing_date is distinct from superseded.farrowing_date then
        raise exception 'cross-sow or cross-farrowing supersession denied';
    end if;
    if exists (
        select 1 from public.litter_supersessions prior
        where prior.superseded_litter_id = new.retained_litter_id
    ) then
        raise exception 'retained litter is already superseded';
    end if;
    if auth_row.operation_id <> new.operation_id
       or auth_row.preview_sha256 <> new.preview_sha256
       or auth_row.decision_status <> 'confirmed'
       or exists (
         select 1 from public.litter_correction_authorization_revocations
         where authorization_id=new.authorization_id
       ) then
        raise exception 'durable owner confirmation does not match operation';
    end if;
    if not exists (
      select 1 from public.mating_events mating
      where mating.mating_id=new.mating_id
        and mating.sow_pig_id=retained.sow_pig_id
        and mating.boar_pig_id=retained.boar_pig_id
        and mating.related_litter_id=retained.litter_id
    ) then
      raise exception 'retained litter mating linkage mismatch';
    end if;
    if (
      select jsonb_agg(pig_id order by pig_id)
      from public.pigs where litter_id=new.superseded_litter_id
    ) is distinct from (
      select jsonb_agg(value order by value)
      from jsonb_array_elements_text(new.superseded_child_ids)
    ) or (
      select jsonb_agg(pig_id order by pig_id)
      from public.pigs where litter_id=new.retained_litter_id
    ) is distinct from (
      select jsonb_agg(value order by value)
      from jsonb_array_elements_text(new.retained_child_ids)
    ) then
      raise exception 'exact litter child allowlists required';
    end if;
    return new;
end;
$$;

drop trigger if exists validate_litter_supersession_insert on public.litter_supersessions;
create trigger validate_litter_supersession_insert
before insert on public.litter_supersessions
for each row execute function public.validate_litter_supersession();

create or replace function public.validate_litter_cohort_disposition()
returns trigger language plpgsql as $$
declare correction public.litter_supersessions%rowtype;
begin
    select * into correction from public.litter_supersessions
      where operation_id=new.operation_id;
    if new.source_litter_id <> correction.superseded_litter_id
       or not (correction.superseded_child_ids ? new.pig_id)
       or not exists (
         select 1 from public.pigs
         where pig_id=new.pig_id and litter_id=new.source_litter_id
       ) then
        raise exception 'cohort disposition is outside exact superseded child set';
    end if;
    return new;
end;
$$;
drop trigger if exists validate_litter_disposition_insert on public.litter_cohort_dispositions;
create trigger validate_litter_disposition_insert
before insert on public.litter_cohort_dispositions
for each row execute function public.validate_litter_cohort_disposition();

create or replace function public.apply_litter_supersession_metadata(
    p_operation_id text, p_retained_litter_id text, p_superseded_litter_id text,
    p_authorization_id text, p_preview_sha256 text, p_mating_id text,
    p_superseded_child_ids jsonb, p_retained_child_ids jsonb,
    p_reference_sha256 text, p_audit_sha256 text, p_audit_row_ids jsonb,
    p_input_sha256 text
) returns void language plpgsql security definer set search_path=public as $$
declare child_id text;
begin
    -- A direct service_role session is used by Supabase.  SET ROLE is also
    -- accepted for disposable database tests; PostgreSQL itself enforces
    -- membership before that special setting can be changed.
    if session_user <> 'service_role'
       and current_setting('role', true) <> 'service_role' then
        raise exception 'service-only correction procedure';
    end if;
    insert into public.litter_supersessions(
      operation_id,retained_litter_id,superseded_litter_id,authorization_id,
      preview_sha256,mating_id,reason,superseded_child_ids,retained_child_ids,
      reference_allowlist_sha256,skipped_audit_rows_sha256,input_sha256
    ) values (
      p_operation_id,p_retained_litter_id,p_superseded_litter_id,p_authorization_id,
      p_preview_sha256,p_mating_id,'duplicate_creation_same_farrowing',
      p_superseded_child_ids,p_retained_child_ids,p_reference_sha256,
      p_audit_sha256,p_input_sha256
    );
    for child_id in select jsonb_array_elements_text(p_superseded_child_ids)
    loop
      insert into public.litter_cohort_dispositions(
        operation_id,pig_id,source_litter_id,disposition
      ) values (
        p_operation_id,child_id,p_superseded_litter_id,
        'superseded_duplicate_representation'
      );
    end loop;
    insert into public.litter_supersession_audit_rows(operation_id,row_id,batch_id)
    select p_operation_id, audit.row_id, audit.batch_id
    from public.bulk_weight_batch_rows audit
    where audit.row_id::text in (
      select jsonb_array_elements_text(p_audit_row_ids)
    );
    if (select count(*) from public.litter_supersession_audit_rows
        where operation_id=p_operation_id) <> jsonb_array_length(p_audit_row_ids) then
      raise exception 'exact skipped-audit evidence set required';
    end if;
    if (select count(*) from public.litter_cohort_dispositions
        where operation_id=p_operation_id) <> jsonb_array_length(p_superseded_child_ids) then
      raise exception 'partial cohort disposition denied';
    end if;
end;
$$;

create or replace view public.current_canonical_litters as
select litter.*
from public.litters litter
where not exists (
    select 1 from public.litter_supersessions correction
    where correction.superseded_litter_id = litter.litter_id
);

create or replace view public.historical_litter_representations as
select litter.*,
       correction.operation_id as supersession_operation_id,
       correction.retained_litter_id,
       (correction.operation_id is not null) as is_superseded
from public.litters litter
left join public.litter_supersessions correction
  on correction.superseded_litter_id = litter.litter_id;

create or replace view public.current_canonical_pigs as
select pig.*
from public.pigs pig
where not exists (
    select 1 from public.litter_cohort_dispositions disposition
    where disposition.pig_id = pig.pig_id
);

create or replace view public.current_canonical_pig_state as
select state.*
from public.pig_current_state state
where not exists (
    select 1 from public.litter_cohort_dispositions disposition
    where disposition.pig_id = state.pig_id
);

create or replace function public.reject_superseded_pig_fact()
returns trigger language plpgsql as $$
declare field record; row_json jsonb;
begin
  if tg_op='DELETE' then row_json := to_jsonb(old); else row_json := to_jsonb(new); end if;
  for field in
    select key,value from jsonb_each_text(row_json)
  loop
    if exists (
      select 1 from public.litter_cohort_dispositions disposition
      where position(disposition.pig_id in coalesce(field.value,'')) > 0
    ) then
      raise exception 'new references to a superseded duplicate pig identity are denied';
    end if;
  end loop;
  if tg_op='DELETE' then return old; end if;
  return new;
end;
$$;

create or replace function public.reject_superseded_pig_mutation()
returns trigger language plpgsql as $$
begin
  if exists (
    select 1 from public.litter_cohort_dispositions where pig_id=old.pig_id
  ) then
    raise exception 'mutation of a superseded duplicate pig identity is denied';
  end if;
  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

create or replace function public.reject_protected_litter_audit_mutation()
returns trigger language plpgsql as $$
begin
  if exists (
    select 1 from public.litter_supersession_audit_rows evidence
    where evidence.row_id=old.row_id
  ) then
    raise exception 'mutation of protected litter audit evidence is denied';
  end if;
  if tg_op='DELETE' then return old; end if;
  return new;
end;
$$;

drop trigger if exists reject_protected_litter_audit_mutation on public.bulk_weight_batch_rows;
create trigger reject_protected_litter_audit_mutation
before update or delete on public.bulk_weight_batch_rows
for each row execute function public.reject_protected_litter_audit_mutation();

drop trigger if exists reject_superseded_pig_mutation on public.pigs;
create trigger reject_superseded_pig_mutation
before update or delete on public.pigs
for each row execute function public.reject_superseded_pig_mutation();

create or replace function public.reject_superseded_litter_mutation()
returns trigger language plpgsql as $$
begin
  if exists (
    select 1 from public.litter_supersessions
    where superseded_litter_id=old.litter_id
  ) then
    raise exception 'mutation of a superseded litter representation is denied';
  end if;
  if tg_op = 'DELETE' then return old; end if;
  return new;
end;
$$;
drop trigger if exists reject_superseded_litter_mutation on public.litters;
create trigger reject_superseded_litter_mutation
before update or delete on public.litters
for each row execute function public.reject_superseded_litter_mutation();

create or replace function public.refresh_litter_supersession_write_guards()
returns void language plpgsql security definer set search_path=public as $$
declare target_table text;
begin
  for target_table in
    select distinct column_info.table_name
    from information_schema.columns column_info
    join information_schema.tables table_info
      on table_info.table_schema=column_info.table_schema
     and table_info.table_name=column_info.table_name
     and table_info.table_type='BASE TABLE'
    where column_info.table_schema='public'
      and (
        column_info.column_name ilike '%pig%'
        or column_info.column_name ilike '%animal%'
        or column_info.column_name ilike '%child%'
        or column_info.data_type in ('json','jsonb')
      )
      and column_info.table_name not in (
        'litters','litter_correction_authorizations',
        'litter_correction_authorization_revocations',
        'litter_supersessions','litter_cohort_dispositions',
        'litter_supersession_audit_rows'
      )
  loop
    execute format(
      'drop trigger if exists reject_superseded_pig_fact on public.%I', target_table
    );
    execute format(
      'create trigger reject_superseded_pig_fact before insert or update or delete on public.%I for each row execute function public.reject_superseded_pig_fact()',
      target_table
    );
  end loop;
end;
$$;

select public.refresh_litter_supersession_write_guards();
revoke all on function public.refresh_litter_supersession_write_guards() from public;

revoke insert, update, delete on public.litter_correction_authorizations,
    public.litter_correction_authorization_revocations,
    public.litter_supersessions, public.litter_cohort_dispositions,
    public.litter_supersession_audit_rows from public;
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
        execute 'revoke insert, update, delete on public.litter_correction_authorizations, public.litter_correction_authorization_revocations, public.litter_supersessions, public.litter_cohort_dispositions, public.litter_supersession_audit_rows from authenticated';
    end if;
    if exists (select 1 from pg_roles where rolname = 'service_role') then
        execute 'grant select on public.current_canonical_litters, public.historical_litter_representations, public.current_canonical_pigs, public.current_canonical_pig_state to service_role';
        execute 'grant select on public.litter_correction_authorizations, public.litter_correction_authorization_revocations, public.litter_supersessions, public.litter_cohort_dispositions, public.litter_supersession_audit_rows to service_role';
        execute 'grant execute on function public.apply_litter_supersession_metadata(text,text,text,text,text,text,jsonb,jsonb,text,text,jsonb,text) to service_role';
    end if;
end;
$$;

revoke all on function public.apply_litter_supersession_metadata(
  text,text,text,text,text,text,jsonb,jsonb,text,text,jsonb,text
) from public;
