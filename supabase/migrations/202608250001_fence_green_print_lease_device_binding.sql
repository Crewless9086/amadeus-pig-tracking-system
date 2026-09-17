-- Renew/recover only while the job's exact commissioned device binding is active.
create or replace function app_private.green_print_job_device_active(p_job app_private.document_print_jobs)
returns boolean language sql stable security definer set search_path=pg_catalog,app_private as $$
 select exists(select 1 from app_private.document_print_device_registry r
  where r.farm_scope_id=p_job.farm_scope_id and r.green_id=p_job.green_id
    and r.printer_id=p_job.printer_id and r.cups_queue_id=p_job.cups_queue_id
    and r.registry_version=p_job.registry_version and r.active)
$$;
revoke all on function app_private.green_print_job_device_active(app_private.document_print_jobs) from public,anon,authenticated;

create or replace function app_private.renew_document_print_job_lease(
 p_job_id text,p_lease_token text,p_worker_id text,p_lease_seconds integer,
 p_document_version text,p_pdf_sha256 text,p_authorization_receipt_id text,p_farm_scope_id text,p_green_id text)
returns app_private.document_print_jobs language plpgsql security definer set search_path=pg_catalog,app_private as $$
declare v_job app_private.document_print_jobs;
begin
 select * into v_job from app_private.document_print_jobs where job_id=p_job_id for update;
 if not found then raise exception 'lease renewal job missing'; end if;
 if v_job.lease_token is distinct from p_lease_token or v_job.lease_owner<>p_worker_id
  or v_job.lease_expires_at<=clock_timestamp() or p_lease_seconds not between 30 and 300
  or v_job.state not in ('claimed','submitting','submitted','held')
  or v_job.farm_scope_id is distinct from p_farm_scope_id or v_job.green_id is distinct from p_green_id
  or v_job.document_version<>p_document_version or v_job.pdf_sha256<>p_pdf_sha256
  or v_job.authorization_receipt_id<>p_authorization_receipt_id
  or (v_job.state='claimed' and v_job.attempt_id is null and v_job.cups_job_id is null
      and not app_private.green_print_job_device_active(v_job)) then raise exception 'lease renewal invalid'; end if;
 update app_private.document_print_jobs set lease_expires_at=clock_timestamp()+make_interval(secs=>p_lease_seconds),updated_at=clock_timestamp()
  where job_id=p_job_id returning * into v_job; return v_job;
end; $$;

create or replace function app_private.recover_document_print_job_lease(
 p_job_id text,p_worker_id text,p_lease_seconds integer,p_document_version text,
 p_pdf_sha256 text,p_authorization_receipt_id text,p_farm_scope_id text,p_green_id text)
returns app_private.document_print_jobs language plpgsql security definer set search_path=pg_catalog,app_private as $$
declare v_job app_private.document_print_jobs; v_token text:=app_private.pgcrypto_random_hex(24);
begin
 select * into v_job from app_private.document_print_jobs where job_id=p_job_id for update;
 if not found then raise exception 'lease recovery job missing'; end if;
 if v_job.lease_expires_at>clock_timestamp() or p_lease_seconds not between 30 and 300
  or v_job.state not in ('claimed','submitting','submitted','held')
  or v_job.farm_scope_id is distinct from p_farm_scope_id or v_job.green_id is distinct from p_green_id
  or v_job.document_version<>p_document_version or v_job.pdf_sha256<>p_pdf_sha256
  or v_job.authorization_receipt_id<>p_authorization_receipt_id
  or (v_job.state='claimed' and v_job.attempt_id is null and v_job.cups_job_id is null
      and not app_private.green_print_job_device_active(v_job)) then raise exception 'lease recovery invalid'; end if;
 update app_private.document_print_jobs set lease_owner=p_worker_id,lease_token=v_token,
  lease_expires_at=clock_timestamp()+make_interval(secs=>p_lease_seconds),updated_at=clock_timestamp()
  where job_id=p_job_id returning * into v_job;
 insert into app_private.document_print_job_events(job_id,event_type,actor_id,worker_id,attempt_id,cups_job_id,metadata_json)
 values(p_job_id,'lease_recovered','documents-claim-service',p_worker_id,v_job.attempt_id,v_job.cups_job_id,
  jsonb_build_object('provider_id',v_job.provider_id)); return v_job;
end; $$;
