-- Let a fresh GREEN ledger adopt one exact expired pre-attempt canonical claim.
-- This never creates a print job and never touches any post-attempt claim.
create or replace function app_private.claim_document_print_job(
  p_farm_scope_id text, p_green_id text, p_worker_id text,
  p_lease_seconds integer default 300)
returns setof app_private.document_print_jobs
language plpgsql security definer set search_path = pg_catalog, app_private as $$
declare
  v_job_id text;
  v_previous_state text;
  v_token text := app_private.pgcrypto_random_hex(24);
begin
  if p_worker_id is null or p_lease_seconds not between 30 and 300 then
    raise exception 'invalid claim';
  end if;
  select job_id,state into v_job_id,v_previous_state
    from app_private.document_print_jobs
   where farm_scope_id=p_farm_scope_id and green_id=p_green_id
     and retry_deadline > clock_timestamp()
     and authorization_expires_at > clock_timestamp()
     and app_private.green_print_job_device_active(document_print_jobs)
     and (state='authorized' or (
       state='claimed' and lease_expires_at<=clock_timestamp()
       and attempt_id is null and cups_job_id is null and provider_id is null))
   order by case when state='claimed' then 0 else 1 end,created_at,job_id
   for update skip locked limit 1;
  if v_job_id is null then return; end if;
  update app_private.document_print_jobs set state='claimed',lease_owner=p_worker_id,
    lease_token=v_token,lease_expires_at=clock_timestamp()+make_interval(secs=>p_lease_seconds),
    updated_at=clock_timestamp()
   where job_id=v_job_id
     and farm_scope_id=p_farm_scope_id and green_id=p_green_id
     and retry_deadline > clock_timestamp()
     and authorization_expires_at > clock_timestamp()
     and app_private.green_print_job_device_active(document_print_jobs)
     and (state='authorized' or (
       state='claimed' and lease_expires_at<=clock_timestamp()
       and attempt_id is null and cups_job_id is null and provider_id is null))
   returning job_id into v_job_id;
  if not found then return; end if;
  insert into app_private.document_print_job_events(
    job_id,event_type,actor_id,worker_id,metadata_json)
  values(v_job_id,case when v_previous_state='claimed' then 'lease_recovered' else 'lease_claimed' end,
    'documents-claim-service',p_worker_id,jsonb_build_object(
      'lease_token_fingerprint',md5(v_token),
      'lost_local_ledger_adoption',v_previous_state='claimed'));
  return query select * from app_private.document_print_jobs where job_id=v_job_id;
end; $$;

revoke all on function app_private.claim_document_print_job(text,text,text,integer)
  from public,anon,authenticated;
grant execute on function app_private.claim_document_print_job(text,text,text,integer)
  to documents_green_worker_executor;

insert into app_private.migration_log(migration_id,description)
values('202608250002_adopt_green_lost_pre_attempt_claim',
 'Allow one exact active and authorized expired pre-attempt GREEN claim to be adopted by a fresh local ledger')
on conflict (migration_id) do nothing;
