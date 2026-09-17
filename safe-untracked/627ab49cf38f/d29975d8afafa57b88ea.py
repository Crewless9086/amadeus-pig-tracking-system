import json, os
from pathlib import Path
from dotenv import load_dotenv
import psycopg

load_dotenv(Path(r"C:\Users\charl\OneDrive\1. Amadeus\AGENTS\amadeus-pig-tracking-system\.env"))
dsn = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
mid = "202608250001_fence_green_print_lease_device_binding"
names = ("green_print_job_device_active", "renew_document_print_job_lease", "recover_document_print_job_lease")
with psycopg.connect(dsn) as db:
    with db.cursor() as cur:
        cur.execute("select migration_id,migration_filename,migration_sha256,ordinal,outcome,source_commit,render_service_id,render_instance_id,applied_at from app_private.production_migration_receipts where migration_id=%s", (mid,))
        receipt = cur.fetchone(); receipt_cols = [d.name for d in cur.description]
        cur.execute("""select p.proname,pg_get_function_identity_arguments(p.oid),l.lanname,
          format_type(p.prorettype,null),p.prosecdef,p.proleakproof,p.provolatile,p.proparallel,
          p.proconfig,pg_get_userbyid(p.proowner),
          coalesce((select jsonb_agg(jsonb_build_array(coalesce(r.rolname,'PUBLIC'),x.privilege_type) order by coalesce(r.rolname,'PUBLIC'),x.privilege_type)
            from aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) x left join pg_roles r on r.oid=x.grantee where x.grantee<>p.proowner),'[]'::jsonb)
          from pg_proc p join pg_namespace n on n.oid=p.pronamespace join pg_language l on l.oid=p.prolang
          where n.nspname='app_private' and p.proname=any(%s) order by p.proname""", (list(names),))
        funcs = cur.fetchall(); func_cols = [d.name for d in cur.description]
        cur.execute("select allowlist_sha256,catalog_sha256,source_commit,render_service_id,render_instance_id,created_at from app_private.production_migration_catalog_checkpoints order by created_at desc limit 2")
        cps = cur.fetchall(); cp_cols = [d.name for d in cur.description]
        cur.execute("select state,lease_owner,lease_expires_at,authorization_expires_at,retry_deadline,attempt_id,cups_job_id,provider_id,farm_scope_id,green_id,app_private.green_print_job_device_active(j) as device_active from app_private.document_print_jobs j where job_id=%s", ("GREEN-WWS-WWS-20260825.r1.a79d4a6effa6",))
        job = cur.fetchone(); job_cols = [d.name for d in cur.description]
print(json.dumps({"receipt": dict(zip(receipt_cols, receipt)) if receipt else None,
 "functions": [dict(zip(func_cols,row)) for row in funcs],
 "catalog_checkpoints": [dict(zip(cp_cols,row)) for row in cps],
 "job": dict(zip(job_cols,job)) if job else None}, default=str, sort_keys=True))
