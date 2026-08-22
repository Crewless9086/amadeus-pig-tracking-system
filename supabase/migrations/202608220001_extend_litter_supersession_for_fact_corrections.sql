-- Extend the existing append-only litter supersession rail to governed fact
-- corrections. Historical litter and pig rows remain immutable; the current
-- canonical views select only the retained representation.

alter table public.litter_supersessions alter column mating_id drop not null;
alter table public.litter_supersessions drop constraint if exists litter_supersessions_reason_check;
alter table public.litter_supersessions add constraint litter_supersessions_reason_check
  check (reason in ('duplicate_creation_same_farrowing','fact_correction'));

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
       or retained.farrowing_date is distinct from superseded.farrowing_date then
        raise exception 'cross-sow or cross-farrowing supersession denied';
    end if;
    if new.reason='duplicate_creation_same_farrowing'
       and retained.boar_pig_id is distinct from superseded.boar_pig_id then
        raise exception 'duplicate supersession father mismatch';
    end if;
    if exists (select 1 from public.litter_supersessions prior
               where prior.superseded_litter_id = new.retained_litter_id) then
        raise exception 'retained litter is already superseded';
    end if;
    if auth_row.operation_id <> new.operation_id
       or auth_row.preview_sha256 <> new.preview_sha256
       or auth_row.decision_status <> 'confirmed'
       or exists (select 1 from public.litter_correction_authorization_revocations
                  where authorization_id=new.authorization_id) then
        raise exception 'durable owner confirmation does not match operation';
    end if;
    if new.mating_id is not null and not exists (
      select 1 from public.mating_events mating
      where mating.mating_id=new.mating_id
        and mating.sow_pig_id=retained.sow_pig_id
        and mating.related_litter_id=retained.litter_id
    ) then raise exception 'retained litter mating linkage mismatch'; end if;
    if (select jsonb_agg(pig_id order by pig_id) from public.pigs
        where litter_id=new.superseded_litter_id) is distinct from
       (select jsonb_agg(value order by value)
        from jsonb_array_elements_text(new.superseded_child_ids))
       or (select jsonb_agg(pig_id order by pig_id) from public.pigs
           where litter_id=new.retained_litter_id) is distinct from
          (select jsonb_agg(value order by value)
           from jsonb_array_elements_text(new.retained_child_ids)) then
      raise exception 'exact litter child allowlists required';
    end if;
    return new;
end;
$$;

insert into app_private.migration_log(migration_id,description)
values('202608220001_extend_litter_supersession_for_fact_corrections',
 'Reuse append-only litter supersession rail for protected factual corrections')
on conflict(migration_id) do nothing;
