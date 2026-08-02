-- Preserve append-only SAM review snapshots while excluding superseded animal
-- identities from current/actionable review projections.

alter table public.litter_supersessions
  add column if not exists historical_reference_rows_sha256 text
    not null default '4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945',
  add column if not exists historical_reference_row_count integer
    not null default 0 check (historical_reference_row_count >= 0),
  add column if not exists historical_reference_row_ids jsonb
    not null default '[]'::jsonb
    check (jsonb_typeof(historical_reference_row_ids) = 'array');

alter table public.litter_supersessions
  drop constraint if exists litter_supersessions_historical_reference_rows_sha256_check;
alter table public.litter_supersessions
  add constraint litter_supersessions_historical_reference_rows_sha256_check
  check (historical_reference_rows_sha256 ~ '^[0-9a-f]{64}$');

create or replace view public.current_actionable_sam_live_stock_review_events as
select review_event.*
from public.sam_live_stock_conversation_review_events review_event
where not exists (
  select 1
  from public.litter_supersessions correction
  cross join lateral jsonb_array_elements_text(
    correction.historical_reference_row_ids
  ) historical_review(review_event_id)
  where historical_review.review_event_id=review_event.review_event_id
);

drop function if exists public.apply_litter_supersession_metadata(
  text,text,text,text,text,text,jsonb,jsonb,text,text,jsonb,text
);

create or replace function public.apply_litter_supersession_metadata(
    p_operation_id text, p_retained_litter_id text, p_superseded_litter_id text,
    p_authorization_id text, p_preview_sha256 text, p_mating_id text,
    p_superseded_child_ids jsonb, p_retained_child_ids jsonb,
    p_reference_sha256 text, p_audit_sha256 text, p_audit_row_ids jsonb,
    p_input_sha256 text, p_historical_reference_sha256 text,
    p_historical_reference_row_count integer,
    p_historical_reference_row_ids jsonb
) returns void language plpgsql security definer set search_path=public as $$
declare child_id text;
begin
    if session_user <> 'service_role'
       and current_setting('role', true) <> 'service_role' then
        raise exception 'service-only correction procedure';
    end if;
    if jsonb_typeof(p_historical_reference_row_ids) <> 'array'
       or jsonb_array_length(p_historical_reference_row_ids)
          <> p_historical_reference_row_count then
        raise exception 'exact historical-reference evidence set required';
    end if;
    if (
      select count(distinct value)
      from jsonb_array_elements_text(p_historical_reference_row_ids)
    ) <> p_historical_reference_row_count then
      raise exception 'duplicate historical-reference identities denied';
    end if;
    insert into public.litter_supersessions(
      operation_id,retained_litter_id,superseded_litter_id,authorization_id,
      preview_sha256,mating_id,reason,superseded_child_ids,retained_child_ids,
      reference_allowlist_sha256,skipped_audit_rows_sha256,input_sha256,
      historical_reference_rows_sha256,historical_reference_row_count,
      historical_reference_row_ids
    ) values (
      p_operation_id,p_retained_litter_id,p_superseded_litter_id,p_authorization_id,
      p_preview_sha256,p_mating_id,'duplicate_creation_same_farrowing',
      p_superseded_child_ids,p_retained_child_ids,p_reference_sha256,
      p_audit_sha256,p_input_sha256,p_historical_reference_sha256,
      p_historical_reference_row_count,p_historical_reference_row_ids
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

revoke all on function public.apply_litter_supersession_metadata(
  text,text,text,text,text,text,jsonb,jsonb,text,text,jsonb,text,text,integer,jsonb
) from public;

do $$
begin
  if exists (select 1 from pg_roles where rolname='service_role') then
    execute 'grant select on public.current_actionable_sam_live_stock_review_events to service_role';
    execute 'grant execute on function public.apply_litter_supersession_metadata(text,text,text,text,text,text,jsonb,jsonb,text,text,jsonb,text,text,integer,jsonb) to service_role';
  end if;
end;
$$;
