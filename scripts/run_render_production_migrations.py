"""Closed Render production-migration rail.

This entry point intentionally accepts no migration or SQL arguments.  The
ordered allowlist below is source-reviewed, and a Render one-off job supplies
the existing service environment (including DATABASE_URL) without credential
copying.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sys
import uuid
from datetime import timezone
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCK_KEY = 8_260_820_000_1
HEX_COMMIT = re.compile(r"^[0-9a-f]{40}$")
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class AllowedMigration:
    migration_id: str
    filename: str
    sha256: str


# Ordered. Append-only review changes are required for every future migration.
ALLOWLIST = (
    AllowedMigration(
        migration_id="202608190002_create_beacon_protected_publication_consumer",
        filename="202608190002_create_beacon_protected_publication_consumer.sql",
        sha256="2d033bdcdf011f9dd417c5d9ae2659c334e139f7815b20a910b12b50e4df7edd",
    ),
    AllowedMigration(
        migration_id="202608200001_add_sales_financial_disposition",
        filename="202608200001_add_sales_financial_disposition.sql",
        sha256="626808c3f6d4e4ee2862cfd78bc6a3bae5f05992006559618d5fb7740db8c920",
    ),
    AllowedMigration(
        migration_id="202608200002_create_pig_welfare_case_lifecycle",
        filename="202608200002_create_pig_welfare_case_lifecycle.sql",
        sha256="f82972f872a3aa6080d9e1d9a4fc45c117a22a0c4f5e328407caefeb044ab14c",
    ),
    AllowedMigration(
        migration_id="202608220001_extend_litter_supersession_for_fact_corrections",
        filename="202608220001_extend_litter_supersession_for_fact_corrections.sql",
        sha256="fccbc84ca2c2b0cf736d079d2341fbb80b218f202df0b1b14b1582e27ef15963",
    ),
    AllowedMigration(
        migration_id="202608220002_allow_herdmaster_farrowing_protected_claims",
        filename="202608220002_allow_herdmaster_farrowing_protected_claims.sql",
        sha256="762825c57d9b6fd95a0e7197fb0cfb965f31988eabb059abc47fafbd6152ca62",
    ),
    AllowedMigration(
        migration_id="202608250001_fence_green_print_lease_device_binding",
        filename="202608250001_fence_green_print_lease_device_binding.sql",
        sha256="7607ddc4f7fb3c6cd77d638525854929545026af0e9160eb751633b29f51459b",
    ),
    AllowedMigration(
        migration_id="202608250002_adopt_green_lost_pre_attempt_claim",
        filename="202608250002_adopt_green_lost_pre_attempt_claim.sql",
        sha256="977f45d6f935d3bf7b39b6bfbe9c696c52fd88db743f8c86c5b73719ff28475e",
    ),
    AllowedMigration(
        migration_id="202608260001_allow_herdmaster_litter_actions_protected_claims",
        filename="202608260001_allow_herdmaster_litter_actions_protected_claims.sql",
        sha256="1470c98984b982597433e9ac5d9fe9b3db81f14bc335441a40d9ac69965ea6c2",
    ),
)


EXPECTED_LITTER_SUPERSESSION_REASONS = (
    "duplicate_creation_same_farrowing",
    "fact_correction",
)
PREDECESSOR_LITTER_SUPERSESSION_REASONS = (
    "duplicate_creation_same_farrowing",
)
EXPECTED_PROTECTED_ACTION_KINDS = (
    "beacon_campaign_review",
    "beacon_media_review",
    "beacon_private_album_finish",
    "documents_green_physical_acceptance",
    "documents_green_print",
    "grouped_weights",
    "herdmaster_breeding_grouped",
    "herdmaster_record_farrowing_litter",
    "herdmaster_record_litter_first_treatment",
    "herdmaster_record_litter_piglet_deaths",
    "mortality",
    "rootline_delegated_family",
    "rootline_fertilizer_mixer_commissioning",
    "rootline_fertilizer_mixer_presence_refresh",
    "rootline_irrigation_segment",
    "sam_sale_payment",
)
PREDECESSOR_PROTECTED_ACTION_KINDS = tuple(
    value
    for value in EXPECTED_PROTECTED_ACTION_KINDS
    if value not in {"herdmaster_record_litter_first_treatment",
                     "herdmaster_record_litter_piglet_deaths"}
)
FARROWING_PREDECESSOR_ACTION_KINDS = tuple(
    value for value in PREDECESSOR_PROTECTED_ACTION_KINDS
    if value != "herdmaster_record_farrowing_litter"
)
EXPECTED_MIGRATION_LOG_DESCRIPTIONS = {
    "202608260001_allow_herdmaster_litter_actions_protected_claims": (
        "Admit exact-preview HERDMASTER litter treatment and piglet-loss claims "
        "through the canonical protected action spine."
    ),
    "202608250002_adopt_green_lost_pre_attempt_claim": (
        "Allow one exact active and authorized expired pre-attempt GREEN claim "
        "to be adopted by a fresh local ledger"
    ),
    "202608220001_extend_litter_supersession_for_fact_corrections": (
        "Reuse append-only litter supersession rail for protected factual corrections"
    ),
    "202608220002_allow_herdmaster_farrowing_protected_claims": (
        "Admit exact-preview HERDMASTER farrowing claims through the canonical "
        "protected action spine."
    ),
}

HISTORICAL_CREATED_RELATIONS = {
    "202608190002_create_beacon_protected_publication_consumer": (
        "app_private.beacon_protected_publication_consumers",
    ),
    "202608200002_create_pig_welfare_case_lifecycle": (
        "public.pig_welfare_cases", "public.pig_welfare_case_events",
        "public.pig_welfare_case_fact_links", "public.pig_welfare_case_current",
    ),
}

# Only this reviewed historical prefix may be admitted by the separate one-time
# baseline ceremony.  Later semantic migrations must always execute normally.
BASELINE_ELIGIBLE_IDS = tuple(item.migration_id for item in ALLOWLIST[:3])
LEGACY_ADOPTION_BASELINE_IDS = (ALLOWLIST[3].migration_id,)
LEGACY_ADOPTION_RECEIPT_IDS = tuple(item.migration_id for item in ALLOWLIST[:3])
AUTHORIZED_PRIVATE_SCHEMA_ACL = (
    ("documents_api_executor", "USAGE", False),
    ("documents_green_worker_executor", "USAGE", False),
)
AUTHORIZED_MANAGED_PROTECTED_CLAIM_READ_ROLES = (
    "pg_read_all_data",
    "supabase_etl_admin",
    "supabase_read_only_user",
)

# The drift gate deliberately inventories complete catalog state for the bounded
# objects governed by this closed rail.  Adding a migration means adding only its
# object identities here; columns, constraints, indexes, defaults, functions,
# triggers, RLS and ACLs are discovered generically rather than hand-coded.
CATALOG_RELATIONS = (
    "app_private.migration_log",
    "app_private.oom_protected_action_claims",
    "app_private.beacon_protected_publication_consumers",
    "app_private.production_migration_receipts",
    "app_private.production_migration_receipt_identity_anchors",
    "app_private.production_migration_baselines",
    "app_private.production_migration_catalog_checkpoints",
    "public.sales_transactions",
    "public.pig_welfare_cases",
    "public.pig_welfare_case_events",
    "public.pig_welfare_case_fact_links",
    "public.pig_welfare_case_current",
    "public.litter_supersessions",
)
CATALOG_FUNCTIONS = (
    "app_private.claim_document_print_job",
    "app_private.green_print_job_device_active",
    "app_private.guard_charitable_sales_evidence",
    "app_private.guard_production_migration_receipts",
    "app_private.recover_document_print_job_lease",
    "app_private.renew_document_print_job_lease",
    "public.pig_welfare_case_validate_insert",
    "public.pig_welfare_case_event_validate_insert",
    "public.pig_welfare_case_fact_link_validate_insert",
    "public.pig_welfare_case_validate_death_closure",
    "public.pig_welfare_case_block_mutation",
    "public.validate_litter_supersession",
)

GREEN_DEVICE_FENCE_MIGRATION_ID = (
    "202608250001_fence_green_print_lease_device_binding"
)
GREEN_LOST_LEDGER_MIGRATION_ID = "202608250002_adopt_green_lost_pre_attempt_claim"
GREEN_DEVICE_FUNCTIONS = {
    "green_print_job_device_active": {
        "arguments": "p_job app_private.document_print_jobs",
        "language": "sql", "return_type": "boolean", "volatility": "s",
        "acl": (),
    },
    "renew_document_print_job_lease": {
        "arguments": (
            "p_job_id text, p_lease_token text, p_worker_id text, "
            "p_lease_seconds integer, p_document_version text, p_pdf_sha256 text, "
            "p_authorization_receipt_id text, p_farm_scope_id text, p_green_id text"
        ),
        "language": "plpgsql", "return_type": "app_private.document_print_jobs",
        "volatility": "v", "acl": (("documents_green_worker_executor", "EXECUTE"),),
    },
    "recover_document_print_job_lease": {
        "arguments": (
            "p_job_id text, p_worker_id text, p_lease_seconds integer, "
            "p_document_version text, p_pdf_sha256 text, p_authorization_receipt_id text, "
            "p_farm_scope_id text, p_green_id text"
        ),
        "language": "plpgsql", "return_type": "app_private.document_print_jobs",
        "volatility": "v", "acl": (("documents_green_worker_executor", "EXECUTE"),),
    },
}
GREEN_DEVICE_PREDECESSOR_FUNCTIONS = {
    name: GREEN_DEVICE_FUNCTIONS[name]
    for name in (
        "renew_document_print_job_lease",
        "recover_document_print_job_lease",
    )
}
GREEN_CLAIM_FUNCTION = {
    "claim_document_print_job": {
        "arguments": (
            "p_farm_scope_id text, p_green_id text, p_worker_id text, "
            "p_lease_seconds integer"
        ),
        "language": "plpgsql", "return_type": "app_private.document_print_jobs",
        "returns_set": True,
        "volatility": "v", "acl": (("documents_green_worker_executor", "EXECUTE"),),
    }
}


BOOTSTRAP_SQL = """
create schema if not exists app_private;
create table if not exists app_private.production_migration_receipts (
    receipt_id uuid primary key,
    migration_id text not null,
    migration_filename text not null,
    migration_sha256 text not null check (migration_sha256 ~ '^[0-9a-f]{64}$'),
    ordinal integer not null check (ordinal > 0),
    outcome text not null check (outcome in ('applied','failed')),
    source_commit text not null check (source_commit ~ '^[0-9a-f]{40}$'),
    render_service_id text not null,
    render_instance_id text not null,
    error_class text,
    applied_at timestamptz not null default clock_timestamp(),
    check ((outcome = 'applied' and error_class is null) or
           (outcome = 'failed' and error_class is not null))
);
create unique index if not exists uq_production_migration_applied
    on app_private.production_migration_receipts(migration_id)
    where outcome = 'applied';
create table if not exists app_private.production_migration_receipt_identity_anchors (
    receipt_id uuid primary key references app_private.production_migration_receipts(receipt_id),
    identity_sha256 text not null check (identity_sha256 ~ '^[0-9a-f]{64}$'),
    anchored_at timestamptz not null default clock_timestamp()
);
create table if not exists app_private.production_migration_baselines (
    baseline_id uuid primary key,
    migration_ids_json jsonb not null check (jsonb_typeof(migration_ids_json) = 'array'),
    migration_checksums_json jsonb not null check (jsonb_typeof(migration_checksums_json) = 'object'),
    source_catalog_sha256 text not null check (source_catalog_sha256 ~ '^[0-9a-f]{64}$'),
    source_catalog_json jsonb not null check (jsonb_typeof(source_catalog_json) = 'object'),
    source_commit text not null check (source_commit ~ '^[0-9a-f]{40}$'),
    render_service_id text not null,
    render_instance_id text not null,
    authorized_at timestamptz not null default clock_timestamp()
);
create unique index if not exists uq_production_migration_baseline_prefix
    on app_private.production_migration_baselines(migration_ids_json);
create table if not exists app_private.production_migration_catalog_checkpoints (
    checkpoint_id uuid primary key,
    allowlist_json jsonb not null check (jsonb_typeof(allowlist_json) = 'array'),
    allowlist_sha256 text not null check (allowlist_sha256 ~ '^[0-9a-f]{64}$'),
    catalog_sha256 text not null check (catalog_sha256 ~ '^[0-9a-f]{64}$'),
    catalog_json jsonb not null check (jsonb_typeof(catalog_json) = 'object'),
    source_commit text not null check (source_commit ~ '^[0-9a-f]{40}$'),
    render_service_id text not null,
    render_instance_id text not null,
    created_at timestamptz not null default clock_timestamp()
);
create unique index if not exists uq_production_migration_catalog_allowlist
    on app_private.production_migration_catalog_checkpoints(allowlist_sha256);
create or replace function app_private.guard_production_migration_receipts()
returns trigger language plpgsql as $$
begin
    raise exception 'production migration receipts are append-only';
end;
$$;
drop trigger if exists trg_guard_production_migration_receipts
    on app_private.production_migration_receipts;
create trigger trg_guard_production_migration_receipts
before update or delete on app_private.production_migration_receipts
for each row execute function app_private.guard_production_migration_receipts();
drop trigger if exists trg_guard_production_migration_receipt_identity_anchors
    on app_private.production_migration_receipt_identity_anchors;
create trigger trg_guard_production_migration_receipt_identity_anchors
before update or delete on app_private.production_migration_receipt_identity_anchors
for each row execute function app_private.guard_production_migration_receipts();
drop trigger if exists trg_guard_production_migration_baselines
    on app_private.production_migration_baselines;
create trigger trg_guard_production_migration_baselines
before update or delete on app_private.production_migration_baselines
for each row execute function app_private.guard_production_migration_receipts();
drop trigger if exists trg_guard_production_migration_catalog_checkpoints
    on app_private.production_migration_catalog_checkpoints;
create trigger trg_guard_production_migration_catalog_checkpoints
before update or delete on app_private.production_migration_catalog_checkpoints
for each row execute function app_private.guard_production_migration_receipts();
"""


def _metadata(environ: dict[str, str]) -> tuple[str, str, str]:
    if environ.get("RENDER") != "true":
        raise RuntimeError("render_runtime_required")
    commit = environ.get("RENDER_GIT_COMMIT", "").strip().lower()
    service_id = environ.get("RENDER_SERVICE_ID", "").strip()
    instance_id = environ.get("RENDER_INSTANCE_ID", "").strip()
    if not HEX_COMMIT.fullmatch(commit):
        raise RuntimeError("exact_render_source_commit_required")
    expected_commit = environ.get("RENDER_MIGRATION_EXPECTED_COMMIT", "").strip().lower()
    if not HEX_COMMIT.fullmatch(expected_commit) or expected_commit != commit:
        raise RuntimeError("render_source_deploy_binding_mismatch")
    if not service_id.startswith(("srv-", "crn-")) or not instance_id:
        raise RuntimeError("exact_render_runtime_identity_required")
    return commit, service_id, instance_id


def _load_sql(item: AllowedMigration) -> str:
    path = (REPO_ROOT / "supabase" / "migrations" / item.filename).resolve()
    expected_parent = (REPO_ROOT / "supabase" / "migrations").resolve()
    if path.parent != expected_parent or path.name != item.filename:
        raise RuntimeError("allowlisted_migration_path_invalid")
    # Git's canonical blob uses LF. Normalize checkout newline materialization
    # before binding so Windows review and Render/Linux execute identical SQL.
    sql = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    if hashlib.sha256(sql.encode("utf-8")).hexdigest() != item.sha256:
        raise RuntimeError(f"allowlisted_migration_checksum_mismatch:{item.migration_id}")
    return sql


def _allowlist_payload(items=ALLOWLIST) -> list[dict[str, str]]:
    return [
        {
            "migration_id": item.migration_id,
            "filename": item.filename,
            "sha256": item.sha256,
        }
        for item in items
    ]


def _json_sha256(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


def _verify_private_schema(connection, *, required: bool) -> dict | None:
    row = connection.execute(
        """select pg_catalog.pg_get_userbyid(n.nspowner),current_user,n.oid
             from pg_catalog.pg_namespace n where n.nspname='app_private'"""
    ).fetchone()
    if not row:
        if required:
            raise RuntimeError("migration_private_schema_missing")
        return None
    if row[0] != row[1]:
        raise RuntimeError("migration_private_schema_owner_mismatch")
    acl = connection.execute(
        """select coalesce(r.rolname,'PUBLIC'),x.privilege_type,x.is_grantable
             from pg_catalog.pg_namespace n
             cross join lateral pg_catalog.aclexplode(
               coalesce(n.nspacl,pg_catalog.acldefault('n',n.nspowner))
             ) x
             left join pg_catalog.pg_roles r on r.oid=x.grantee
            where n.nspname='app_private' and x.grantee<>n.nspowner
            order by 1,2,3"""
    ).fetchall()
    normalized_acl = tuple(tuple(value for value in row) for row in acl)
    if any(entry not in AUTHORIZED_PRIVATE_SCHEMA_ACL for entry in normalized_acl):
        raise RuntimeError(f"migration_private_schema_acl_mismatch:{acl}")
    authorized_roles = {entry[0] for entry in normalized_acl}
    if authorized_roles:
        posture = connection.execute(
            """select rolname,rolcanlogin,rolinherit,rolsuper,rolcreatedb,rolcreaterole,
                      rolreplication,rolbypassrls
                 from pg_catalog.pg_roles where rolname=any(%s) order by 1""",
            (sorted(authorized_roles),),
        ).fetchall()
        expected = [(role, False, False, False, False, False, False, False)
                    for role in sorted(authorized_roles)]
        if posture != expected:
            raise RuntimeError(f"migration_private_schema_role_posture_mismatch:{posture}")
    return {"owner": row[0], "authorized_acl": [list(x) for x in normalized_acl],
            "unauthorized_privilege_count": 0}


def _catalog_manifest(connection, *, relations=None, functions=None) -> dict:
    """Return deterministic catalog state for this rail's bounded object set."""

    relations = list(relations if relations is not None else CATALOG_RELATIONS)
    functions = list(functions if functions is not None else CATALOG_FUNCTIONS)

    def rows(sql: str, params=()):
        return [list(row) for row in connection.execute(sql, params).fetchall()]

    manifest = {
        "version": "render_migration_catalog_manifest_v5",
        "scope": {
            "relations": relations,
            "functions": functions,
            "schemas": ["app_private"],
        },
        "schemas": rows(
            """select n.nspname,pg_catalog.pg_get_userbyid(n.nspowner)
                 from pg_catalog.pg_namespace n
                where n.nspname='app_private' order by 1"""
        ),
        "schema_acl": rows(
            """select n.nspname,coalesce(r.rolname,'PUBLIC'),x.privilege_type,x.is_grantable
                 from pg_catalog.pg_namespace n
                 cross join lateral pg_catalog.aclexplode(
                   coalesce(n.nspacl,pg_catalog.acldefault('n',n.nspowner))
                 ) x
                 left join pg_catalog.pg_roles r on r.oid=x.grantee
                where n.nspname='app_private' order by 1,2,3,4"""
        ),
        "relations": rows(
            """select n.nspname,c.relname,c.relkind,
                      pg_catalog.pg_get_userbyid(c.relowner),c.relpersistence,
                      c.relrowsecurity,c.relforcerowsecurity,c.relreplident,
                      c.relhasrules,
                      coalesce(array_to_string(c.reloptions,E'\n'),'')
                 from pg_catalog.pg_class c
                 join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                where (n.nspname||'.'||c.relname)=any(%s)
                order by 1,2""",
            (relations,),
        ),
        "relation_acl": rows(
            """select n.nspname,c.relname,coalesce(r.rolname,'PUBLIC'),
                      x.privilege_type,x.is_grantable
                 from pg_catalog.pg_class c
                 join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                 cross join lateral pg_catalog.aclexplode(
                   coalesce(c.relacl,pg_catalog.acldefault('r',c.relowner))
                 ) x
                 left join pg_catalog.pg_roles r on r.oid=x.grantee
                where (n.nspname||'.'||c.relname)=any(%s)
                order by 1,2,3,4,5""",
            (relations,),
        ),
        "columns": rows(
            """select n.nspname,c.relname,a.attnum,a.attname,
                      pg_catalog.format_type(a.atttypid,a.atttypmod),a.attnotnull,
                      a.attidentity,a.attgenerated,
                      coalesce(pg_catalog.pg_get_expr(d.adbin,d.adrelid),'')
                 from pg_catalog.pg_class c
                 join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                 join pg_catalog.pg_attribute a on a.attrelid=c.oid
                    and a.attnum>0 and not a.attisdropped
                 left join pg_catalog.pg_attrdef d
                    on d.adrelid=c.oid and d.adnum=a.attnum
                where (n.nspname||'.'||c.relname)=any(%s)
                order by 1,2,3""",
            (relations,),
        ),
        "column_acl": rows(
            """select n.nspname,c.relname,a.attname,
                      coalesce(r.rolname,'PUBLIC'),x.privilege_type,x.is_grantable
                 from pg_catalog.pg_class c
                 join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                 join pg_catalog.pg_attribute a on a.attrelid=c.oid
                    and a.attnum>0 and not a.attisdropped
                 cross join lateral pg_catalog.aclexplode(a.attacl) x
                 left join pg_catalog.pg_roles r on r.oid=x.grantee
                where (n.nspname||'.'||c.relname)=any(%s)
                order by 1,2,3,4,5,6""",
            (relations,),
        ),
        "constraints": rows(
            """select n.nspname,c.relname,k.conname,k.contype,k.condeferrable,
                      k.condeferred,k.convalidated,
                      pg_catalog.pg_get_constraintdef(k.oid,false)
                 from pg_catalog.pg_constraint k
                 join pg_catalog.pg_class c on c.oid=k.conrelid
                 join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                where (n.nspname||'.'||c.relname)=any(%s)
                order by 1,2,3""",
            (relations,),
        ),
        "foreign_keys": rows(
            """select kn.nspname,k.conname,
                      sn.nspname,src.relname,tn.nspname,tgt.relname,
                      k.condeferrable,k.condeferred,k.convalidated,
                      k.confmatchtype,k.confupdtype,k.confdeltype,
                      pg_catalog.pg_get_constraintdef(k.oid,false)
                 from pg_catalog.pg_constraint k
                 join pg_catalog.pg_class src on src.oid=k.conrelid
                 join pg_catalog.pg_namespace sn on sn.oid=src.relnamespace
                 join pg_catalog.pg_class tgt on tgt.oid=k.confrelid
                 join pg_catalog.pg_namespace tn on tn.oid=tgt.relnamespace
                 join pg_catalog.pg_namespace kn on kn.oid=k.connamespace
                where k.contype='f'
                  and ((sn.nspname||'.'||src.relname)=any(%s)
                    or (tn.nspname||'.'||tgt.relname)=any(%s))
                order by 1,2,3,4,5,6""",
            (relations, relations),
        ),
        "indexes": rows(
            """select n.nspname,c.relname,i.relname,x.indisunique,x.indisprimary,
                      x.indisvalid,x.indisready,
                      pg_catalog.pg_get_indexdef(i.oid)
                 from pg_catalog.pg_index x
                 join pg_catalog.pg_class c on c.oid=x.indrelid
                 join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                 join pg_catalog.pg_class i on i.oid=x.indexrelid
                where (n.nspname||'.'||c.relname)=any(%s)
                order by 1,2,3""",
            (relations,),
        ),
        "triggers": rows(
            """select n.nspname,c.relname,t.tgname,t.tgenabled,t.tgtype,
                      pg_catalog.pg_get_triggerdef(t.oid,false),
                      fn.nspname||'.'||p.proname,
                      pg_catalog.pg_get_function_identity_arguments(p.oid),
                      pg_catalog.pg_get_userbyid(p.proowner)
                 from pg_catalog.pg_trigger t
                 join pg_catalog.pg_class c on c.oid=t.tgrelid
                 join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                 join pg_catalog.pg_proc p on p.oid=t.tgfoid
                 join pg_catalog.pg_namespace fn on fn.oid=p.pronamespace
                where (n.nspname||'.'||c.relname)=any(%s) and not t.tgisinternal
                order by 1,2,3""",
            (relations,),
        ),
        "internal_triggers": rows(
            """with selected_foreign_keys as (
                 select k.oid
                   from pg_catalog.pg_constraint k
                   join pg_catalog.pg_class src on src.oid=k.conrelid
                   join pg_catalog.pg_namespace sn on sn.oid=src.relnamespace
                   join pg_catalog.pg_class tgt on tgt.oid=k.confrelid
                   join pg_catalog.pg_namespace tn on tn.oid=tgt.relnamespace
                  where k.contype='f'
                    and ((sn.nspname||'.'||src.relname)=any(%s)
                      or (tn.nspname||'.'||tgt.relname)=any(%s))
               )
               select n.nspname,c.relname,t.tgname,t.tgenabled,t.tgtype,
                      pg_catalog.pg_get_triggerdef(t.oid,false),
                      coalesce(kn.nspname,''),coalesce(k.conname,''),
                      coalesce(k.contype,' '),coalesce(k.condeferrable,false),
                      coalesce(k.condeferred,false),coalesce(k.convalidated,false),
                      coalesce(sn.nspname,''),coalesce(src.relname,''),
                      coalesce(tn.nspname,''),coalesce(tgt.relname,''),
                      fn.nspname,p.proname,
                      pg_catalog.pg_get_function_identity_arguments(p.oid),
                      pg_catalog.pg_get_userbyid(p.proowner)
                 from pg_catalog.pg_trigger t
                 join pg_catalog.pg_class c on c.oid=t.tgrelid
                 join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                 join pg_catalog.pg_proc p on p.oid=t.tgfoid
                 join pg_catalog.pg_namespace fn on fn.oid=p.pronamespace
                 left join pg_catalog.pg_constraint k on k.oid=t.tgconstraint
                 left join pg_catalog.pg_namespace kn on kn.oid=k.connamespace
                 left join pg_catalog.pg_class src on src.oid=k.conrelid
                 left join pg_catalog.pg_namespace sn on sn.oid=src.relnamespace
                 left join pg_catalog.pg_class tgt on tgt.oid=k.confrelid
                 left join pg_catalog.pg_namespace tn on tn.oid=tgt.relnamespace
                where t.tgisinternal
                  and ((n.nspname||'.'||c.relname)=any(%s)
                    or t.tgconstraint in (select oid from selected_foreign_keys))
                order by 1,2,3""",
            (relations, relations, relations),
        ),
        "rules": rows(
            """select n.nspname,c.relname,r.rulename,r.ev_enabled,
                      r.ev_type,r.is_instead,
                      pg_catalog.regexp_replace(
                        pg_catalog.pg_get_ruledef(r.oid,false),
                        '[[:space:]]+',' ','g'
                      )
                 from pg_catalog.pg_rewrite r
                 join pg_catalog.pg_class c on c.oid=r.ev_class
                 join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                where (n.nspname||'.'||c.relname)=any(%s)
                order by 1,2,3""",
            (relations,),
        ),
        "views": rows(
            """select n.nspname,c.relname,c.relkind,
                      pg_catalog.regexp_replace(
                        pg_catalog.pg_get_viewdef(c.oid,false),
                        '[[:space:]]+',' ','g'
                      ),
                      coalesce(array_to_string(c.reloptions,E'\n'),'')
                 from pg_catalog.pg_class c
                 join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                where (n.nspname||'.'||c.relname)=any(%s)
                  and c.relkind in ('v','m')
                order by 1,2""",
            (relations,),
        ),
        "functions": rows(
            """select n.nspname,p.proname,
                      pg_catalog.pg_get_function_identity_arguments(p.oid),
                      pg_catalog.pg_get_userbyid(p.proowner),l.lanname,
                      pg_catalog.format_type(p.prorettype,null),p.prosecdef,
                      p.proleakproof,p.provolatile,p.proparallel,
                      coalesce(array_to_string(p.proconfig,E'\\n'),''),
                      pg_catalog.pg_get_functiondef(p.oid)
                 from pg_catalog.pg_proc p
                 join pg_catalog.pg_namespace n on n.oid=p.pronamespace
                 join pg_catalog.pg_language l on l.oid=p.prolang
                where (n.nspname||'.'||p.proname)=any(%s)
                order by 1,2,3""",
            (functions,),
        ),
        "function_acl": rows(
            """select n.nspname,p.proname,
                      pg_catalog.pg_get_function_identity_arguments(p.oid),
                      coalesce(r.rolname,'PUBLIC'),x.privilege_type,x.is_grantable
                 from pg_catalog.pg_proc p
                 join pg_catalog.pg_namespace n on n.oid=p.pronamespace
                 cross join lateral pg_catalog.aclexplode(
                   coalesce(p.proacl,pg_catalog.acldefault('f',p.proowner))
                 ) x
                 left join pg_catalog.pg_roles r on r.oid=x.grantee
                where (n.nspname||'.'||p.proname)=any(%s)
                order by 1,2,3,4,5,6""",
            (functions,),
        ),
        "policies": rows(
            """select schemaname,tablename,policyname,permissive,
                      coalesce(array_to_string(roles,','),''),cmd,
                      coalesce(qual,''),coalesce(with_check,'')
                 from pg_catalog.pg_policies
                where (schemaname||'.'||tablename)=any(%s)
                order by 1,2,3""",
            (relations,),
        ),
    }
    return manifest


def _catalog_snapshot(connection, *, relations=None, functions=None) -> tuple[dict, str]:
    manifest = _catalog_manifest(connection, relations=relations, functions=functions)
    return manifest, _json_sha256(manifest)


def _parse_text_membership_check(definition: str, column: str) -> tuple[str, ...]:
    """Accept only PostgreSQL's positive equality/ANY rendering for a text check."""

    compact = re.sub(r"\s+", "", definition)
    escaped_column = re.escape(column)
    single = re.fullmatch(
        rf"CHECK\(\({escaped_column}='([a-z0-9_]+)'::text\)\)",
        compact,
    )
    if single:
        return (single.group(1),)
    array = re.fullmatch(
        rf"CHECK\(\({escaped_column}=ANY\(ARRAY\[(.+)\]\)\)\)",
        compact,
    )
    if not array:
        raise RuntimeError(f"migration_readback_constraint_structure_mismatch:{definition}")
    values = []
    for member in array.group(1).split(","):
        parsed = re.fullmatch(r"'([a-z0-9_]+)'::text", member)
        if not parsed:
            raise RuntimeError(
                f"migration_readback_constraint_structure_mismatch:{definition}"
            )
        values.append(parsed.group(1))
    if len(values) != len(set(values)):
        raise RuntimeError(f"migration_readback_constraint_duplicate_value:{definition}")
    return tuple(sorted(values))


def _constraint_readback(
    connection,
    schema: str,
    table: str,
    name: str,
    column: str | None = None,
) -> tuple[str, tuple[str, ...]]:
    row = connection.execute(
        """select pg_catalog.pg_get_constraintdef(c.oid)
             from pg_catalog.pg_constraint c
             join pg_catalog.pg_class t on t.oid=c.conrelid
             join pg_catalog.pg_namespace n on n.oid=t.relnamespace
            where n.nspname=%s and t.relname=%s and c.conname=%s and c.contype='c'""",
        (schema, table, name),
    ).fetchone()
    if not row or not row[0]:
        raise RuntimeError(f"migration_readback_constraint_missing:{schema}.{table}:{name}")
    definition = row[0]
    expected_column = column or {
        "litter_supersessions_reason_check": "reason",
        "oom_protected_action_claims_action_kind_check": "action_kind",
    }.get(name)
    if not expected_column:
        raise RuntimeError(f"migration_readback_constraint_column_unknown:{name}")
    values = _parse_text_membership_check(definition, expected_column)
    return definition, values


def _migration_log_description(connection, migration_id: str) -> str | None:
    row = connection.execute(
        "select description from app_private.migration_log where migration_id=%s",
        (migration_id,),
    ).fetchone()
    return str(row[0]) if row else None


def _verify_migration_log(connection, migration_id: str, *, required: bool) -> str | None:
    description = _migration_log_description(connection, migration_id)
    expected = EXPECTED_MIGRATION_LOG_DESCRIPTIONS[migration_id]
    if required and description != expected:
        raise RuntimeError(
            f"migration_readback_log_mismatch:{migration_id}:{description!r}"
        )
    if not required and description is not None:
        raise RuntimeError(
            f"migration_precondition_unexpected_log:{migration_id}:{description!r}"
        )
    return description


def _migration_function_body(filename: str) -> str:
    path = (REPO_ROOT / "supabase" / "migrations" / filename).resolve()
    expected_parent = (REPO_ROOT / "supabase" / "migrations").resolve()
    if path.parent != expected_parent or path.name != filename:
        raise RuntimeError("migration_function_source_path_invalid")
    sql = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    matches = re.findall(
        r"create\s+or\s+replace\s+function\s+public\.validate_litter_supersession\(\)"
        r"\s*returns\s+trigger\s+language\s+plpgsql\s+as\s+\$\$(.*?)\$\$;",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if len(matches) != 1:
        raise RuntimeError(f"migration_function_source_mismatch:{filename}")
    return matches[0].strip()


def _function_readback(connection, expected_filename: str) -> tuple[str, str]:
    rows = connection.execute(
        """select p.prosrc,pg_catalog.pg_get_functiondef(p.oid),l.lanname,
                  pg_catalog.format_type(p.prorettype,null),p.prosecdef,
                  p.proleakproof,p.provolatile,p.proparallel,p.proconfig
             from pg_catalog.pg_proc p
             join pg_catalog.pg_namespace n on n.oid=p.pronamespace
             join pg_catalog.pg_language l on l.oid=p.prolang
            where n.nspname='public' and p.proname='validate_litter_supersession'
              and pg_catalog.pg_get_function_identity_arguments(p.oid)=''"""
    ).fetchall()
    if len(rows) != 1:
        raise RuntimeError("migration_readback_validate_litter_supersession_missing_or_ambiguous")
    body, definition, language, return_type, security_definer, leakproof, volatility, parallel, config = rows[0]
    normalized_body = str(body).replace("\r\n", "\n").replace("\r", "\n").strip()
    expected_body = _migration_function_body(expected_filename)
    if normalized_body != expected_body or (
        language,
        return_type,
        security_definer,
        leakproof,
        volatility,
        parallel,
        config,
    ) != ("plpgsql", "trigger", False, False, "v", "u", None):
        raise RuntimeError("migration_readback_validate_litter_supersession_mismatch")
    normalized_definition = str(definition).replace("\r\n", "\n").replace("\r", "\n")
    return normalized_body, normalized_definition


def _green_device_function_bodies(
    filename: str, expected_functions: dict | None = None
) -> dict[str, str]:
    path = (REPO_ROOT / "supabase" / "migrations" / filename).resolve()
    expected_parent = (REPO_ROOT / "supabase" / "migrations").resolve()
    if path.parent != expected_parent or path.name != filename:
        raise RuntimeError("migration_green_function_source_path_invalid")
    sql = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    bodies = {}
    for name in (expected_functions or GREEN_DEVICE_FUNCTIONS):
        matches = re.findall(
            rf"create\s+or\s+replace\s+function\s+app_private\.{name}\s*\(.*?\)"
            rf"\s*returns\s+.*?\s+language\s+(?:sql|plpgsql).*?\s+as\s+\$\$(.*?)\$\$;",
            sql,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if len(matches) != 1:
            raise RuntimeError(f"migration_green_function_source_mismatch:{filename}:{name}")
        bodies[name] = matches[0].strip()
    return bodies


def _verify_green_device_functions(
    connection, filename: str, expected_functions: dict | None = None
) -> dict:
    expected_functions = expected_functions or GREEN_DEVICE_FUNCTIONS
    expected_bodies = _green_device_function_bodies(filename, expected_functions)
    readback = {}
    for name, expected in expected_functions.items():
        rows = connection.execute(
            """select p.prosrc,pg_catalog.pg_get_functiondef(p.oid),
                      pg_catalog.pg_get_function_identity_arguments(p.oid),l.lanname,
                      pg_catalog.format_type(p.prorettype,null),p.proretset,p.prosecdef,
                      p.proleakproof,p.provolatile,p.proparallel,p.proconfig,
                      pg_catalog.pg_get_userbyid(p.proowner),current_user,p.oid
                 from pg_catalog.pg_proc p
                 join pg_catalog.pg_namespace n on n.oid=p.pronamespace
                 join pg_catalog.pg_language l on l.oid=p.prolang
                where n.nspname='app_private' and p.proname=%s""",
            (name,),
        ).fetchall()
        if len(rows) != 1:
            raise RuntimeError(f"migration_green_function_missing_or_ambiguous:{name}")
        (body, definition, arguments, language, return_type, returns_set, security_definer,
         leakproof, volatility, parallel, config, owner, current_role, oid) = rows[0]
        normalized_body = str(body).replace("\r\n", "\n").replace("\r", "\n").strip()
        expected_config = ["search_path=pg_catalog, app_private"]
        if (
            normalized_body != expected_bodies[name]
            or arguments != expected["arguments"]
            or (language, return_type, returns_set, security_definer, leakproof, volatility, parallel)
            != (expected["language"], expected["return_type"],
                expected.get("returns_set", False), True, False,
                expected["volatility"], "u")
            or config != expected_config
            or owner != current_role
        ):
            raise RuntimeError(f"migration_green_function_definition_mismatch:{name}")
        acl = connection.execute(
            """select coalesce(r.rolname,'PUBLIC'),x.privilege_type
                 from pg_catalog.pg_proc p
                 cross join lateral pg_catalog.aclexplode(
                   coalesce(p.proacl,pg_catalog.acldefault('f',p.proowner))) x
                 left join pg_catalog.pg_roles r on r.oid=x.grantee
                where p.oid=%s and x.grantee<>p.proowner order by 1,2""",
            (oid,),
        ).fetchall()
        if tuple(acl) != expected["acl"]:
            raise RuntimeError(f"migration_green_function_acl_mismatch:{name}:{acl}")
        readback[name] = {
            "body_sha256": hashlib.sha256(normalized_body.encode("utf-8")).hexdigest(),
            "definition_sha256": hashlib.sha256(
                str(definition).replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
            ).hexdigest(),
            "acl": [list(row) for row in acl],
        }
    return readback


def _verify_green_device_predecessor(connection) -> dict:
    readback = _verify_green_device_functions(
        connection,
        "202608210001_create_green_print_jobs.sql",
        GREEN_DEVICE_PREDECESSOR_FUNCTIONS,
    )
    target_only = connection.execute(
        "select pg_catalog.to_regprocedure(%s)",
        ("app_private.green_print_job_device_active(app_private.document_print_jobs)",),
    ).fetchone()[0]
    if target_only is not None:
        raise RuntimeError("migration_green_predecessor_has_target_function")
    return readback


def _mating_id_nullable(connection) -> bool:
    row = connection.execute(
        """select not a.attnotnull
             from pg_catalog.pg_attribute a
            where a.attrelid='public.litter_supersessions'::regclass
              and a.attname='mating_id' and a.attnum > 0 and not a.attisdropped"""
    ).fetchone()
    if not row:
        raise RuntimeError("migration_precondition_mating_id_missing")
    return bool(row[0])


def _verify_litter_validator_trigger(connection) -> dict:
    rows = connection.execute(
        """select t.tgenabled,t.tgtype,fn.nspname,p.proname,
                  pg_catalog.pg_get_function_identity_arguments(p.oid),
                  pg_catalog.pg_get_triggerdef(t.oid,false),
                  pg_catalog.pg_get_userbyid(p.proowner),
                  pg_catalog.pg_get_userbyid(c.relowner),current_user
             from pg_catalog.pg_trigger t
             join pg_catalog.pg_class c on c.oid=t.tgrelid
             join pg_catalog.pg_namespace tn on tn.oid=c.relnamespace
             join pg_catalog.pg_proc p on p.oid=t.tgfoid
             join pg_catalog.pg_namespace fn on fn.oid=p.pronamespace
            where tn.nspname='public' and c.relname='litter_supersessions'
              and t.tgname='validate_litter_supersession_insert'
              and not t.tgisinternal"""
    ).fetchall()
    if len(rows) != 1:
        raise RuntimeError("migration_readback_litter_validator_trigger_missing_or_ambiguous")
    (enabled, trigger_type, function_schema, function_name, function_args,
     definition, function_owner, table_owner, current_role) = rows[0]
    if (
        enabled != "O"
        or trigger_type != 7  # ROW | BEFORE | INSERT
        or function_schema != "public"
        or function_name != "validate_litter_supersession"
        or function_args != ""
        or function_owner != current_role
        or table_owner != current_role
    ):
        raise RuntimeError("migration_readback_litter_validator_trigger_mismatch")
    normalized = re.sub(r"\s+", " ", str(definition)).strip()
    expected = (
        "CREATE TRIGGER validate_litter_supersession_insert BEFORE INSERT ON "
        "public.litter_supersessions FOR EACH ROW EXECUTE FUNCTION "
        "validate_litter_supersession()"
    )
    if normalized != expected:
        raise RuntimeError("migration_readback_litter_validator_trigger_definition_mismatch")
    before_insert_triggers = connection.execute(
        """select t.tgname
             from pg_catalog.pg_trigger t
             join pg_catalog.pg_class c on c.oid=t.tgrelid
             join pg_catalog.pg_namespace n on n.oid=c.relnamespace
            where n.nspname='public' and c.relname='litter_supersessions'
              and not t.tgisinternal and (t.tgtype & 2)=2 and (t.tgtype & 4)=4
            order by t.tgname"""
    ).fetchall()
    if before_insert_triggers != [("validate_litter_supersession_insert",)]:
        raise RuntimeError(
            f"migration_readback_litter_before_insert_trigger_inventory_mismatch:"
            f"{before_insert_triggers}"
        )
    return {
        "enabled": enabled,
        "trigger_type": trigger_type,
        "function_owner_matches_table_owner": True,
        "definition_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
    }


def _verify_protected_claim_acl(connection) -> dict:
    owner = connection.execute(
        """select pg_catalog.pg_get_userbyid(c.relowner),current_user
             from pg_catalog.pg_class c join pg_catalog.pg_namespace n on n.oid=c.relnamespace
            where n.nspname='app_private' and c.relname='oom_protected_action_claims'"""
    ).fetchone()
    if not owner or owner[0] != owner[1]:
        raise RuntimeError("migration_readback_protected_claim_owner_mismatch")
    rows = connection.execute(
        """with recursive target as (
               select c.oid,c.relacl,c.relowner
                 from pg_catalog.pg_class c
                 join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                where n.nspname='app_private'
                  and c.relname='oom_protected_action_claims'
             ), privilege_names(privilege_type) as (
               values ('SELECT'),('INSERT'),('UPDATE'),('DELETE'),
                      ('TRUNCATE'),('REFERENCES'),('TRIGGER')
             ), memberships(member,roleid) as (
               select m.member,m.roleid from pg_catalog.pg_auth_members m
               union
               select x.member,m.roleid from memberships x
               join pg_catalog.pg_auth_members m on m.member=x.roleid
             ), candidate_roles as (
               select r.oid,r.rolname from pg_catalog.pg_roles r
                where (r.rolcanlogin or r.rolname in ('anon','authenticated')) and not r.rolsuper
               union
               select g.oid,g.rolname from pg_catalog.pg_roles login
               join memberships m on m.member=login.oid
               join pg_catalog.pg_roles g on g.oid=m.roleid
                where (login.rolcanlogin or login.rolname in ('anon','authenticated')) and not login.rolsuper
             ), forbidden as (
               select 'PUBLIC'::text as role_name,x.privilege_type
                 from target t
                 cross join lateral pg_catalog.aclexplode(
                   coalesce(t.relacl,pg_catalog.acldefault('r',t.relowner))
                 ) x
                where x.grantee=0
               union all
               select r.rolname,p.privilege_type
                 from target t
                 join candidate_roles r on r.oid <> t.relowner
                 cross join privilege_names p
                where pg_catalog.has_table_privilege(r.oid,t.oid,p.privilege_type)
               union all
               select r.rolname,'COLUMN:'||a.attname||':'||p.privilege_type
                 from target t join pg_catalog.pg_attribute a on a.attrelid=t.oid
                 join candidate_roles r on r.oid <> t.relowner
                 cross join (values ('SELECT'),('INSERT'),('UPDATE'),('REFERENCES')) p(privilege_type)
                where a.attnum>0 and not a.attisdropped
                  and pg_catalog.has_column_privilege(r.oid,t.oid,a.attnum,p.privilege_type)
             )
             select role_name,privilege_type from forbidden order by 1,2"""
    ).fetchall()
    managed_read_roles = sorted(
        {
            role_name
            for role_name, privilege_type in rows
            if role_name in AUTHORIZED_MANAGED_PROTECTED_CLAIM_READ_ROLES
            and (
                privilege_type == "SELECT"
                or privilege_type.startswith("COLUMN:")
                and privilege_type.endswith(":SELECT")
            )
        }
    )
    unauthorized = [
        row
        for row in rows
        if not (
            row[0] in AUTHORIZED_MANAGED_PROTECTED_CLAIM_READ_ROLES
            and (
                row[1] == "SELECT"
                or row[1].startswith("COLUMN:") and row[1].endswith(":SELECT")
            )
        )
    ]
    if unauthorized:
        raise RuntimeError(
            f"migration_readback_protected_claim_acl_mismatch:{unauthorized}"
        )
    return {
        "unauthorized_privilege_count": 0,
        "managed_read_roles": managed_read_roles,
    }


def _verify_receipt_guard(connection, *, require_anchor: bool = True) -> dict:
    _verify_private_schema(connection, required=True)
    catalog = connection.execute(
        """select c.relname,pg_catalog.pg_get_userbyid(c.relowner),current_user,
                  array_agg(a.attname||':'||pg_catalog.format_type(a.atttypid,a.atttypmod)
                            ||':'||a.attnotnull order by a.attnum)
             from pg_catalog.pg_class c join pg_catalog.pg_namespace n on n.oid=c.relnamespace
             join pg_catalog.pg_attribute a on a.attrelid=c.oid and a.attnum>0 and not a.attisdropped
            where n.nspname='app_private' and c.relname in
             ('production_migration_receipts','production_migration_receipt_identity_anchors',
              'production_migration_baselines','production_migration_catalog_checkpoints')
            group by c.relname,c.relowner"""
    ).fetchall()
    expected_columns = {
        "production_migration_receipts": [
            "receipt_id:uuid:true","migration_id:text:true","migration_filename:text:true",
            "migration_sha256:text:true","ordinal:integer:true","outcome:text:true",
            "source_commit:text:true","render_service_id:text:true","render_instance_id:text:true",
            "error_class:text:false","applied_at:timestamp with time zone:true"],
        "production_migration_receipt_identity_anchors": [
            "receipt_id:uuid:true","identity_sha256:text:true","anchored_at:timestamp with time zone:true"],
        "production_migration_baselines": [
            "baseline_id:uuid:true","migration_ids_json:jsonb:true",
            "migration_checksums_json:jsonb:true","source_catalog_sha256:text:true",
            "source_catalog_json:jsonb:true","source_commit:text:true",
            "render_service_id:text:true","render_instance_id:text:true",
            "authorized_at:timestamp with time zone:true"],
        "production_migration_catalog_checkpoints": [
            "checkpoint_id:uuid:true","allowlist_json:jsonb:true",
            "allowlist_sha256:text:true","catalog_sha256:text:true",
            "catalog_json:jsonb:true","source_commit:text:true",
            "render_service_id:text:true","render_instance_id:text:true",
            "created_at:timestamp with time zone:true"],
    }
    found = {row[0]: row for row in catalog}
    required = set(expected_columns) if require_anchor else {"production_migration_receipts"}
    if set(found) != required or any(found[n][1] != found[n][2] or found[n][3] != expected_columns[n] for n in required):
        raise RuntimeError("migration_receipt_catalog_shape_or_owner_mismatch")
    if require_anchor:
        index_rows = connection.execute(
            """select i.relname,x.indisunique,x.indisprimary,
                      pg_catalog.pg_get_indexdef(i.oid)
                 from pg_catalog.pg_index x
                 join pg_catalog.pg_class t on t.oid=x.indrelid
                 join pg_catalog.pg_namespace n on n.oid=t.relnamespace
                 join pg_catalog.pg_class i on i.oid=x.indexrelid
                where n.nspname='app_private' and t.relname in
                 ('production_migration_receipts',
                  'production_migration_receipt_identity_anchors',
                  'production_migration_baselines',
                  'production_migration_catalog_checkpoints')"""
        ).fetchall()
        indexes = {row[0]: row for row in index_rows}
        required_indexes = {
            "production_migration_receipts_pkey": (True, True, "(receipt_id)"),
            "uq_production_migration_applied": (
                True,
                False,
                "(migration_id) WHERE (outcome = 'applied'::text)",
            ),
            "production_migration_receipt_identity_anchors_pkey": (
                True,
                True,
                "(receipt_id)",
            ),
            "production_migration_baselines_pkey": (True, True, "(baseline_id)"),
            "uq_production_migration_baseline_prefix": (
                True,
                False,
                "(migration_ids_json)",
            ),
            "production_migration_catalog_checkpoints_pkey": (
                True,
                True,
                "(checkpoint_id)",
            ),
            "uq_production_migration_catalog_allowlist": (
                True,
                False,
                "(allowlist_sha256)",
            ),
        }
        if set(indexes) != set(required_indexes):
            raise RuntimeError(
                f"migration_receipt_catalog_index_inventory_mismatch:{sorted(indexes)}"
            )
        for name, (unique, primary, definition_suffix) in required_indexes.items():
            row = indexes[name]
            if row[1] is not unique or row[2] is not primary or definition_suffix not in row[3]:
                raise RuntimeError(f"migration_receipt_catalog_index_mismatch:{name}")
    if require_anchor:
        fk = connection.execute(
            """select count(*) from pg_catalog.pg_constraint c
               join pg_catalog.pg_class t on t.oid=c.conrelid join pg_catalog.pg_namespace n on n.oid=t.relnamespace
              where n.nspname='app_private' and t.relname='production_migration_receipt_identity_anchors'
                and c.contype='f' and pg_catalog.pg_get_constraintdef(c.oid)=
                'FOREIGN KEY (receipt_id) REFERENCES app_private.production_migration_receipts(receipt_id)'"""
        ).fetchone()[0]
        if fk != 1:
            raise RuntimeError("migration_receipt_anchor_fk_mismatch")
    acl_drift = connection.execute(
        """select c.relname,coalesce(r.rolname,'PUBLIC'),x.privilege_type
             from pg_catalog.pg_class c join pg_catalog.pg_namespace n on n.oid=c.relnamespace
             cross join lateral pg_catalog.aclexplode(coalesce(c.relacl,pg_catalog.acldefault('r',c.relowner))) x
             left join pg_catalog.pg_roles r on r.oid=x.grantee
            where n.nspname='app_private' and c.relname in
             ('production_migration_receipts','production_migration_receipt_identity_anchors',
              'production_migration_baselines','production_migration_catalog_checkpoints')
              and x.grantee<>c.relowner
            union all
           select c.relname,coalesce(r.rolname,'PUBLIC'),'COLUMN:'||a.attname||':'||x.privilege_type
             from pg_catalog.pg_class c join pg_catalog.pg_namespace n on n.oid=c.relnamespace
             join pg_catalog.pg_attribute a on a.attrelid=c.oid and a.attnum>0 and not a.attisdropped
             cross join lateral pg_catalog.aclexplode(a.attacl) x
             left join pg_catalog.pg_roles r on r.oid=x.grantee
            where n.nspname='app_private' and c.relname in
             ('production_migration_receipts','production_migration_receipt_identity_anchors',
              'production_migration_baselines','production_migration_catalog_checkpoints')
              and x.grantee<>c.relowner"""
    ).fetchall()
    if acl_drift:
        raise RuntimeError(f"migration_receipt_catalog_acl_mismatch:{acl_drift}")
    rows = connection.execute(
        """select c.relname,t.tgname,t.tgenabled,t.tgtype,fn.nspname,p.proname,
                  pg_catalog.pg_get_function_identity_arguments(p.oid),
                  p.prosrc,l.lanname,p.prosecdef,p.proleakproof,p.provolatile,p.proparallel,p.proconfig,
                  p.proowner,c.relowner
             from pg_catalog.pg_trigger t
             join pg_catalog.pg_class c on c.oid=t.tgrelid
             join pg_catalog.pg_namespace tn on tn.oid=c.relnamespace
             join pg_catalog.pg_proc p on p.oid=t.tgfoid
             join pg_catalog.pg_namespace fn on fn.oid=p.pronamespace
             join pg_catalog.pg_language l on l.oid=p.prolang
            where tn.nspname='app_private'
              and ((c.relname='production_migration_receipts'
                    and t.tgname='trg_guard_production_migration_receipts')
                or (c.relname='production_migration_receipt_identity_anchors'
                    and t.tgname='trg_guard_production_migration_receipt_identity_anchors')
                or (c.relname='production_migration_baselines'
                    and t.tgname='trg_guard_production_migration_baselines')
                or (c.relname='production_migration_catalog_checkpoints'
                    and t.tgname='trg_guard_production_migration_catalog_checkpoints'))
              and not t.tgisinternal"""
    ).fetchall()
    expected_triggers = {
        "production_migration_receipts": "trg_guard_production_migration_receipts",
    }
    if require_anchor:
        expected_triggers["production_migration_receipt_identity_anchors"] = (
            "trg_guard_production_migration_receipt_identity_anchors"
        )
        expected_triggers["production_migration_baselines"] = (
            "trg_guard_production_migration_baselines"
        )
        expected_triggers["production_migration_catalog_checkpoints"] = (
            "trg_guard_production_migration_catalog_checkpoints"
        )
    inventory = connection.execute(
        """select c.relname,t.tgname from pg_catalog.pg_trigger t
             join pg_catalog.pg_class c on c.oid=t.tgrelid
             join pg_catalog.pg_namespace n on n.oid=c.relnamespace
            where n.nspname='app_private' and c.relname in
             ('production_migration_receipts','production_migration_receipt_identity_anchors',
              'production_migration_baselines','production_migration_catalog_checkpoints')
              and not t.tgisinternal order by 1,2"""
    ).fetchall()
    expected_inventory = sorted(expected_triggers.items())
    if inventory != expected_inventory:
        raise RuntimeError(f"migration_receipt_guard_trigger_inventory_mismatch:{inventory}")
    rows = [row for row in rows if row[0] in expected_triggers]
    if len(rows) != len(expected_triggers):
        raise RuntimeError("migration_receipt_guard_missing_or_ambiguous")
    normalized_body = ""
    for row in rows:
        (table_name, trigger_name, enabled, trigger_type, function_schema,
         function_name, function_args, body, language, security_definer,
         leakproof, volatility, parallel, config, function_owner, table_owner) = row
        normalized_body = re.sub(r"\s+", " ", str(body)).strip()
        if (
            expected_triggers.get(table_name) != trigger_name
            or enabled != "O"
            or trigger_type != 27  # ROW | BEFORE | UPDATE | DELETE
            or function_schema != "app_private"
            or function_name != "guard_production_migration_receipts"
            or function_args != ""
            or normalized_body
            != "begin raise exception 'production migration receipts are append-only'; end;"
            or (language, security_definer, leakproof, volatility, parallel, config)
            != ("plpgsql", False, False, "v", "u", None)
            or function_owner != table_owner
        ):
            raise RuntimeError("migration_receipt_guard_mismatch")
    return {
        "enabled": "O",
        "trigger_type": 27,
        "guarded_tables": sorted(expected_triggers),
        "function_owner_matches_table_owner": True,
        "body_sha256": hashlib.sha256(normalized_body.encode("utf-8")).hexdigest(),
    }


def _verify_receipt_row(
    connection,
    item: AllowedMigration,
    ordinal: int | None,
    *,
    service_id: str,
    outcome: str,
    receipt_id: str | None = None,
    create_anchor: bool = True,
) -> dict:
    rows = connection.execute(
        """select receipt_id::text,migration_id,migration_filename,migration_sha256,
                  ordinal,outcome,source_commit,render_service_id,render_instance_id,
                  error_class,applied_at
             from app_private.production_migration_receipts
            where migration_id=%s and outcome=%s""",
        (item.migration_id, outcome),
    ).fetchall()
    if receipt_id is not None:
        rows = [row for row in rows if row[0] == receipt_id]
    if len(rows) != 1:
        raise RuntimeError(
            f"migration_receipt_missing_or_ambiguous:{item.migration_id}:{outcome}"
        )
    row = rows[0]
    if row[3] != item.sha256:
        raise RuntimeError(f"applied_migration_checksum_conflict:{item.migration_id}")
    expected_error = None if outcome == "applied" else row[9]
    if (
        row[1] != item.migration_id
        or row[2] != item.filename
        or (ordinal is not None and row[4] != ordinal)
        or not isinstance(row[4], int) or row[4] <= 0
        or row[5] != outcome
        or not HEX_COMMIT.fullmatch(str(row[6] or ""))
        or row[7] != service_id
        or not str(row[8] or "").strip()
        or (outcome == "applied" and row[9] is not None)
        or (outcome == "failed" and not str(expected_error or "").strip())
        or row[10] is None
    ):
        raise RuntimeError(f"migration_receipt_identity_mismatch:{item.migration_id}:{outcome}")
    identity_payload = {
        "receipt_id": row[0],
        "migration_id": row[1],
        "migration_filename": row[2],
        "migration_sha256": row[3],
        "ordinal": row[4],
        "outcome": row[5],
        "source_commit": row[6],
        "render_service_id": row[7],
        "render_instance_id": row[8],
        "error_class": row[9],
        "applied_at": row[10].astimezone(timezone.utc).isoformat(timespec="microseconds"),
    }
    identity_sha256 = hashlib.sha256(
        json.dumps(
            identity_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()
    anchor = connection.execute(
        """select identity_sha256
             from app_private.production_migration_receipt_identity_anchors
            where receipt_id=%s""",
        (row[0],),
    ).fetchone()
    anchored_now = False
    if anchor is None:
        if create_anchor:
            connection.execute(
                """insert into app_private.production_migration_receipt_identity_anchors
                   (receipt_id,identity_sha256) values(%s,%s)""",
                (row[0], identity_sha256),
            )
            anchored_now = True
            stored = connection.execute(
                "select identity_sha256 from app_private.production_migration_receipt_identity_anchors where receipt_id=%s",
                (row[0],),
            ).fetchone()
            if stored != (identity_sha256,):
                raise RuntimeError("migration_receipt_identity_anchor_insert_mismatch")
    elif anchor[0] != identity_sha256:
        raise RuntimeError(
            f"migration_receipt_identity_anchor_mismatch:{item.migration_id}:{outcome}"
        )
    return {
        "receipt_id": row[0],
        "migration_filename": row[2],
        "ordinal": row[4],
        "source_commit": row[6],
        "render_service_id": row[7],
        "render_instance_id": row[8],
        "applied_at": row[10],
        "identity_sha256": identity_sha256,
        "identity_anchored_now": anchored_now,
        "identity_anchor_missing": anchor is None and not create_anchor,
    }


def _validate_legacy_adoption_transport(environ):
    """Validate compact transport syntax without reading canonical state."""
    raw = environ.get("RENDER_MIGRATION_LEGACY_ADOPTION_JSON", "").strip()
    compact_id = environ.get("RENDER_MIGRATION_LEGACY_ADOPTION_AUTHORIZATION_ID", "").strip()
    compact_digest = environ.get("RENDER_MIGRATION_LEGACY_ADOPTION_PACKET_SHA256", "").strip()
    if raw:
        raise RuntimeError("migration_legacy_adoption_raw_transport_forbidden")
    if bool(compact_id) != bool(compact_digest):
        raise RuntimeError("migration_legacy_adoption_authorization_transport_incomplete")
    if not compact_id:
        return None
    if not re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
        compact_id,
    ) or not re.fullmatch(r"[0-9a-f]{64}", compact_digest):
        raise RuntimeError("migration_legacy_adoption_authorization_invalid")
    return compact_id, compact_digest


def _requested_legacy_adoption(connection, environ, *, commit: str, service_id: str):
    """Validate the externally authorized, catalog-bound pre-trust shape."""
    transport = _validate_legacy_adoption_transport(environ)
    if transport is None:
        return None
    authorization_id, compact_digest = transport
    value = None
    manifest, digest = _catalog_snapshot(connection)
    guard = connection.execute("""select t.tgenabled,t.tgtype,p.proname,n.nspname
      from pg_catalog.pg_trigger t join pg_catalog.pg_class c on c.oid=t.tgrelid
      join pg_catalog.pg_namespace cn on cn.oid=c.relnamespace
      join pg_catalog.pg_proc p on p.oid=t.tgfoid join pg_catalog.pg_namespace n on n.oid=p.pronamespace
      where cn.nspname='app_private' and c.relname='production_migration_receipts'
      and t.tgname='trg_guard_production_migration_receipts' and not t.tgisinternal""").fetchall()
    if guard != [("O", 27, "guard_production_migration_receipts", "app_private")]:
        raise RuntimeError("migration_legacy_adoption_receipt_guard_mismatch")
    rows = connection.execute("""select receipt_id::text,migration_id,migration_filename,migration_sha256,
      ordinal,outcome,source_commit,render_service_id,render_instance_id,error_class,applied_at
      from app_private.production_migration_receipts""").fetchall()
    if value is None:
        canonical_receipts = []
        for row in sorted(rows, key=lambda item: item[1]):
            canonical_receipts.append({
                "legacy_batch_id": row[1],
                "identity": {
                    "receipt_id": row[0], "migration_id": row[1],
                    "migration_filename": row[2], "migration_sha256": row[3],
                    "ordinal": row[4], "outcome": row[5], "source_commit": row[6],
                    "render_service_id": row[7], "render_instance_id": row[8],
                    "error_class": row[9],
                    "applied_at": row[10].astimezone(timezone.utc).isoformat(timespec="microseconds"),
                },
            })
        value = {
            "authorization_id": authorization_id,
            "expected_commit": commit,
            "render_service_id": service_id,
            "source_catalog_sha256": digest,
            "receipts": canonical_receipts,
        }
        actual_packet_digest = hashlib.sha256(json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")).hexdigest()
        if not hmac.compare_digest(actual_packet_digest, compact_digest):
            raise RuntimeError("migration_legacy_adoption_authorization_digest_mismatch")
    if value.get("expected_commit") != commit or value.get("render_service_id") != service_id:
        raise RuntimeError("migration_legacy_adoption_runtime_binding_mismatch")
    if value.get("source_catalog_sha256") != digest:
        raise RuntimeError("migration_legacy_adoption_catalog_mismatch")
    expected = value.get("receipts")
    if not isinstance(expected, list):
        raise RuntimeError("migration_legacy_adoption_receipt_set_mismatch")
    authorized_by_id = {}
    for authorized in expected:
        if not isinstance(authorized, dict) or not isinstance(authorized.get("identity"), dict):
            raise RuntimeError("migration_legacy_adoption_receipt_set_mismatch")
        migration_id = authorized["identity"].get("migration_id")
        if migration_id in authorized_by_id:
            raise RuntimeError("migration_legacy_adoption_receipt_set_mismatch")
        authorized_by_id[migration_id] = authorized
    if set(authorized_by_id) != set(LEGACY_ADOPTION_RECEIPT_IDS):
        raise RuntimeError("migration_legacy_adoption_receipt_set_mismatch")
    rows_by_id = {}
    for row in rows:
        if row[1] in rows_by_id:
            raise RuntimeError("migration_legacy_adoption_receipt_set_mismatch")
        rows_by_id[row[1]] = row
    if set(rows_by_id) != set(LEGACY_ADOPTION_RECEIPT_IDS):
        raise RuntimeError("migration_legacy_adoption_receipt_count_mismatch")
    verified = []
    for item in ALLOWLIST[:3]:
        authorized = authorized_by_id[item.migration_id]
        row = rows_by_id[item.migration_id]
        actual = {"receipt_id": row[0], "migration_id": row[1], "migration_filename": row[2],
          "migration_sha256": row[3], "ordinal": row[4], "outcome": row[5], "source_commit": row[6],
          "render_service_id": row[7], "render_instance_id": row[8], "error_class": row[9],
          "applied_at": row[10].astimezone(timezone.utc).isoformat(timespec="microseconds")}
        if (not str(authorized.get("legacy_batch_id") or "").strip()
                or authorized.get("identity") != actual
                or (actual["migration_id"], actual["migration_filename"], actual["migration_sha256"], actual["outcome"])
                   != (item.migration_id, item.filename, item.sha256, "applied")):
            raise RuntimeError(f"migration_legacy_adoption_receipt_identity_mismatch:{item.migration_id}")
        verified.append((item, actual["ordinal"], actual["receipt_id"]))
    fourth = ALLOWLIST[3]
    _verify_migration_precondition(connection, fourth, already_applied=True)
    _verify_migration_readback(connection, fourth)
    return {"baseline_id": authorization_id, "migration_ids": list(LEGACY_ADOPTION_BASELINE_IDS),
      "migration_checksums": {fourth.migration_id: fourth.sha256}, "source_catalog_sha256": digest,
      "source_catalog": manifest, "verified_receipts": verified}


def _requested_baseline(connection, environ: dict[str, str]) -> dict | None:
    raw_ids = environ.get("RENDER_MIGRATION_BASELINE_IDS", "").strip()
    raw_digest = environ.get("RENDER_MIGRATION_BASELINE_CATALOG_SHA256", "").strip().lower()
    raw_id = environ.get("RENDER_MIGRATION_BASELINE_AUTHORIZATION_ID", "").strip()
    supplied = (bool(raw_ids), bool(raw_digest), bool(raw_id))
    if not any(supplied):
        return None
    if not all(supplied):
        raise RuntimeError("migration_baseline_authorization_incomplete")
    ids = tuple(value.strip() for value in raw_ids.split(",") if value.strip())
    if not ids or ids != BASELINE_ELIGIBLE_IDS[: len(ids)]:
        raise RuntimeError(f"migration_baseline_prefix_not_eligible:{ids}")
    if not HEX_SHA256.fullmatch(raw_digest):
        raise RuntimeError("migration_baseline_catalog_sha256_invalid")
    try:
        baseline_id = str(uuid.UUID(raw_id))
    except ValueError as exc:
        raise RuntimeError("migration_baseline_authorization_id_invalid") from exc
    manifest, digest = _catalog_snapshot(connection)
    if digest != raw_digest:
        raise RuntimeError(
            f"migration_baseline_catalog_mismatch:expected={raw_digest}:actual={digest}"
        )
    checksums = {
        item.migration_id: item.sha256 for item in ALLOWLIST if item.migration_id in ids
    }
    return {
        "baseline_id": baseline_id,
        "migration_ids": list(ids),
        "migration_checksums": checksums,
        "source_catalog_sha256": digest,
        "source_catalog": manifest,
    }


def _insert_baseline(
    connection,
    baseline: dict,
    *,
    commit: str,
    service_id: str,
    instance_id: str,
) -> None:
    connection.execute(
        """insert into app_private.production_migration_baselines
           (baseline_id,migration_ids_json,migration_checksums_json,
            source_catalog_sha256,source_catalog_json,source_commit,
            render_service_id,render_instance_id)
           values(%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            baseline["baseline_id"],
            json.dumps(baseline["migration_ids"], separators=(",", ":")),
            json.dumps(baseline["migration_checksums"], sort_keys=True, separators=(",", ":")),
            baseline["source_catalog_sha256"],
            json.dumps(baseline["source_catalog"], sort_keys=True, separators=(",", ":")),
            commit,
            service_id,
            instance_id,
        ),
    )
    row = connection.execute(
        """select baseline_id::text,migration_ids_json,migration_checksums_json,
                  source_catalog_sha256,source_catalog_json
             from app_private.production_migration_baselines
            where baseline_id=%s""",
        (baseline["baseline_id"],),
    ).fetchone()
    expected = (
        baseline["baseline_id"],
        baseline["migration_ids"],
        baseline["migration_checksums"],
        baseline["source_catalog_sha256"],
        baseline["source_catalog"],
    )
    if row != expected:
        raise RuntimeError("migration_baseline_insert_readback_mismatch")


def _load_baseline(connection) -> dict | None:
    rows = connection.execute(
        """select baseline_id::text,migration_ids_json,migration_checksums_json,
                  source_catalog_sha256,source_catalog_json,source_commit,
                  render_service_id,render_instance_id
             from app_private.production_migration_baselines"""
    ).fetchall()
    if not rows:
        return None
    if len(rows) != 1:
        raise RuntimeError("migration_baseline_missing_or_ambiguous")
    row = rows[0]
    ids = tuple(row[1])
    if not ids or (
        ids != BASELINE_ELIGIBLE_IDS[: len(ids)]
        and ids != LEGACY_ADOPTION_BASELINE_IDS
    ):
        raise RuntimeError(f"migration_baseline_stored_prefix_invalid:{ids}")
    expected_checksums = {
        item.migration_id: item.sha256 for item in ALLOWLIST if item.migration_id in ids
    }
    if row[2] != expected_checksums:
        raise RuntimeError("migration_baseline_stored_checksum_mismatch")
    if row[3] != _json_sha256(row[4]):
        raise RuntimeError("migration_baseline_stored_catalog_digest_mismatch")
    if (
        not HEX_COMMIT.fullmatch(str(row[5] or ""))
        or not str(row[6] or "").startswith(("srv-", "crn-"))
        or not str(row[7] or "").strip()
    ):
        raise RuntimeError("migration_baseline_stored_identity_mismatch")
    return {
        "baseline_id": row[0],
        "migration_ids": ids,
        "migration_checksums": row[2],
        "source_catalog_sha256": row[3],
    }


def _verify_catalog_checkpoint(connection) -> dict:
    rows = connection.execute(
        """select checkpoint_id::text,allowlist_json,allowlist_sha256,
                  catalog_sha256,catalog_json,source_commit,
                  render_service_id,render_instance_id
             from app_private.production_migration_catalog_checkpoints
            order by jsonb_array_length(allowlist_json) desc,created_at desc"""
    ).fetchall()
    if not rows:
        raise RuntimeError("migration_catalog_checkpoint_required")
    current_payload = _allowlist_payload()
    validated = []
    for row in rows:
        payload = row[1]
        if (
            not isinstance(payload, list)
            or not payload
            or payload != current_payload[: len(payload)]
            or row[2] != _json_sha256(payload)
            or row[3] != _json_sha256(row[4])
            or not HEX_COMMIT.fullmatch(str(row[5] or ""))
            or not str(row[6] or "").startswith(("srv-", "crn-"))
            or not str(row[7] or "").strip()
        ):
            raise RuntimeError("migration_catalog_checkpoint_identity_mismatch")
        validated.append(row)
    latest = validated[0]
    # Scope is derived from the exact migration identities recorded in the
    # checkpoint, not from its distance from today's allowlist tail.  A later
    # migration may add no catalog functions (as with the HERDMASTER action-
    # kind admission), so positional inference would incorrectly subtract a
    # function that the prior checkpoint already and immutably covered.
    checkpoint_ids = {str(item.get("migration_id") or "") for item in latest[1]}
    unavailable_functions = set()
    if "202608250001_fence_green_print_lease_device_binding" not in checkpoint_ids:
        unavailable_functions.update({
            "app_private.green_print_job_device_active",
            "app_private.recover_document_print_job_lease",
            "app_private.renew_document_print_job_lease",
        })
    if "202608250002_adopt_green_lost_pre_attempt_claim" not in checkpoint_ids:
        unavailable_functions.add("app_private.claim_document_print_job")
    expected_functions = [
        name for name in CATALOG_FUNCTIONS if name not in unavailable_functions
    ]
    expected_scope = {
        "relations": list(CATALOG_RELATIONS),
        "functions": expected_functions,
        "schemas": ["app_private"],
    }
    if latest[4].get("scope") != expected_scope:
        raise RuntimeError("migration_catalog_checkpoint_scope_mismatch")
    manifest, digest = _catalog_snapshot(
        connection, relations=CATALOG_RELATIONS, functions=expected_functions
    )
    if digest != latest[3] or manifest != latest[4]:
        raise RuntimeError(
            f"migration_catalog_drift:checkpoint={latest[3]}:current={digest}"
        )
    return {
        "checkpoint_id": latest[0],
        "allowlist": latest[1],
        "allowlist_sha256": latest[2],
        "catalog_sha256": latest[3],
    }


def _ensure_catalog_checkpoint(
    connection,
    *,
    commit: str,
    service_id: str,
    instance_id: str,
) -> dict:
    payload = _allowlist_payload()
    allowlist_sha256 = _json_sha256(payload)
    manifest, catalog_sha256 = _catalog_snapshot(connection)
    existing = connection.execute(
        """select checkpoint_id::text,catalog_sha256,catalog_json
             from app_private.production_migration_catalog_checkpoints
            where allowlist_sha256=%s""",
        (allowlist_sha256,),
    ).fetchall()
    if existing:
        if len(existing) != 1 or existing[0][1] != catalog_sha256 or existing[0][2] != manifest:
            raise RuntimeError("migration_catalog_checkpoint_conflict")
        return {
            "checkpoint_id": existing[0][0],
            "allowlist_sha256": allowlist_sha256,
            "catalog_sha256": catalog_sha256,
            "created_now": False,
        }
    checkpoint_id = str(uuid.uuid4())
    connection.execute(
        """insert into app_private.production_migration_catalog_checkpoints
           (checkpoint_id,allowlist_json,allowlist_sha256,catalog_sha256,
            catalog_json,source_commit,render_service_id,render_instance_id)
           values(%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            checkpoint_id,
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            allowlist_sha256,
            catalog_sha256,
            json.dumps(manifest, sort_keys=True, separators=(",", ":")),
            commit,
            service_id,
            instance_id,
        ),
    )
    stored = connection.execute(
        """select allowlist_json,allowlist_sha256,catalog_sha256,catalog_json
             from app_private.production_migration_catalog_checkpoints
            where checkpoint_id=%s""",
        (checkpoint_id,),
    ).fetchone()
    if stored != (payload, allowlist_sha256, catalog_sha256, manifest):
        raise RuntimeError("migration_catalog_checkpoint_insert_readback_mismatch")
    return {
        "checkpoint_id": checkpoint_id,
        "allowlist_sha256": allowlist_sha256,
        "catalog_sha256": catalog_sha256,
        "created_now": True,
    }


def _anchor_verified_receipt_identity(connection, receipt: dict) -> dict:
    if receipt.get("identity_anchor_missing"):
        connection.execute(
            """insert into app_private.production_migration_receipt_identity_anchors
               (receipt_id,identity_sha256) values(%s,%s)""",
            (receipt["receipt_id"], receipt["identity_sha256"]),
        )
        receipt = {**receipt, "identity_anchored_now": True, "identity_anchor_missing": False}
    return receipt


def _verify_migration_precondition(
    connection,
    item: AllowedMigration,
    *,
    already_applied: bool,
) -> str:
    if item.migration_id == GREEN_LOST_LEDGER_MIGRATION_ID:
        target_error = None
        try:
            _verify_green_device_functions(connection, item.filename, GREEN_CLAIM_FUNCTION)
        except RuntimeError as exc:
            target_error = exc
        if target_error is None:
            if not already_applied:
                raise RuntimeError("migration_precondition_green_claim_target_without_receipt")
            return "target"
        try:
            _verify_green_device_functions(
                connection,
                "202608210001_create_green_print_jobs.sql",
                GREEN_CLAIM_FUNCTION,
            )
        except RuntimeError as exc:
            raise RuntimeError(
                f"migration_precondition_green_claim_function_drift:{exc}"
            ) from exc
        if already_applied:
            raise RuntimeError("migration_precondition_green_claim_predecessor_with_receipt")
        return "predecessor"
    if item.migration_id == GREEN_DEVICE_FENCE_MIGRATION_ID:
        target_error = None
        try:
            _verify_green_device_functions(connection, item.filename)
        except RuntimeError as exc:
            target_error = exc
        if target_error is None:
            if not already_applied:
                raise RuntimeError("migration_precondition_green_target_without_receipt")
            return "target"
        try:
            _verify_green_device_predecessor(connection)
        except RuntimeError as exc:
            raise RuntimeError(
                f"migration_precondition_green_function_drift:{exc}"
            ) from exc
        if already_applied:
            raise RuntimeError("migration_precondition_green_predecessor_with_receipt")
        return "predecessor"
    historical_relations = HISTORICAL_CREATED_RELATIONS.get(item.migration_id, ())
    if historical_relations and not already_applied:
        existing = [name for name in historical_relations if connection.execute(
            "select pg_catalog.to_regclass(%s) is not null", (name,)
        ).fetchone()[0]]
        if existing:
            raise RuntimeError(f"migration_precondition_historical_object_exists:{existing}")
    if item.migration_id == "202608220001_extend_litter_supersession_for_fact_corrections":
        _verify_litter_validator_trigger(connection)
        _, reasons = _constraint_readback(
            connection,
            "public",
            "litter_supersessions",
            "litter_supersessions_reason_check",
        )
        nullable = _mating_id_nullable(connection)
        if reasons == PREDECESSOR_LITTER_SUPERSESSION_REASONS:
            if already_applied or nullable:
                raise RuntimeError("migration_precondition_litter_predecessor_mismatch")
            _function_readback(
                connection, "202607300001_create_litter_supersession_rail.sql"
            )
            _verify_migration_log(connection, item.migration_id, required=False)
            return "predecessor"
        if reasons == EXPECTED_LITTER_SUPERSESSION_REASONS:
            if not nullable:
                raise RuntimeError("migration_precondition_litter_target_mismatch")
            _function_readback(
                connection,
                "202608220001_extend_litter_supersession_for_fact_corrections.sql",
            )
            _verify_migration_log(connection, item.migration_id, required=True)
            return "target"
        raise RuntimeError(f"migration_precondition_litter_constraint_mismatch:{reasons}")
    if item.migration_id == "202608220002_allow_herdmaster_farrowing_protected_claims":
        _verify_protected_claim_acl(connection)
        _, action_kinds = _constraint_readback(
            connection,
            "app_private",
            "oom_protected_action_claims",
            "oom_protected_action_claims_action_kind_check",
        )
        if action_kinds == FARROWING_PREDECESSOR_ACTION_KINDS:
            if already_applied:
                raise RuntimeError("migration_precondition_action_predecessor_mismatch")
            _verify_migration_log(connection, item.migration_id, required=False)
            return "predecessor"
        if action_kinds == PREDECESSOR_PROTECTED_ACTION_KINDS:
            _verify_migration_log(connection, item.migration_id, required=True)
            return "target"
        if action_kinds == EXPECTED_PROTECTED_ACTION_KINDS and already_applied:
            # A later append-only migration legitimately supersedes this
            # migration's target.  Prove both ordered migration-log facts;
            # never treat an unreceipted constraint expansion as replay.
            _verify_migration_log(connection, item.migration_id, required=True)
            _verify_migration_log(
                connection,
                "202608260001_allow_herdmaster_litter_actions_protected_claims",
                required=True,
            )
            return "downstream_target"
        raise RuntimeError(f"migration_precondition_action_constraint_mismatch:{action_kinds}")
    if item.migration_id == "202608260001_allow_herdmaster_litter_actions_protected_claims":
        _verify_protected_claim_acl(connection)
        _, action_kinds = _constraint_readback(connection, "app_private",
            "oom_protected_action_claims", "oom_protected_action_claims_action_kind_check")
        if action_kinds == PREDECESSOR_PROTECTED_ACTION_KINDS:
            if already_applied:
                raise RuntimeError("migration_precondition_litter_actions_predecessor_mismatch")
            _verify_migration_log(connection, item.migration_id, required=False)
            return "predecessor"
        if action_kinds == EXPECTED_PROTECTED_ACTION_KINDS:
            _verify_migration_log(connection, item.migration_id, required=True)
            return "target"
        raise RuntimeError(f"migration_precondition_litter_actions_constraint_mismatch:{action_kinds}")
    if item.migration_id == "202608200001_add_sales_financial_disposition" and not already_applied:
        columns = connection.execute(
            """select column_name from information_schema.columns where table_schema='public'
               and table_name='sales_transactions' and column_name in
               ('financial_disposition','receivable_total','financial_disposition_evidence_json','financial_disposition_evidence_sha256')"""
        ).fetchall()
        if columns:
            raise RuntimeError("migration_precondition_historical_financial_columns_exist")
    return "historical_absent" if not already_applied else "historical_receipted"


def _verify_migration_readback(connection, item: AllowedMigration) -> dict:
    if item.migration_id == GREEN_LOST_LEDGER_MIGRATION_ID:
        functions = _verify_green_device_functions(
            connection, item.filename, GREEN_CLAIM_FUNCTION
        )
        description = _verify_migration_log(connection, item.migration_id, required=True)
        return {
            "migration_receipt_required": True,
            "lost_ledger_adoption_function_count": len(functions),
            "migration_log_description_sha256": hashlib.sha256(
                description.encode("utf-8")
            ).hexdigest(),
            "functions": functions,
        }
    if item.migration_id == GREEN_DEVICE_FENCE_MIGRATION_ID:
        functions = _verify_green_device_functions(connection, item.filename)
        return {
            "migration_receipt_required": True,
            "device_fence_function_count": len(functions),
            "functions": functions,
        }
    if item.migration_id == "202608220001_extend_litter_supersession_for_fact_corrections":
        trigger = _verify_litter_validator_trigger(connection)
        constraint, reasons = _constraint_readback(
            connection,
            "public",
            "litter_supersessions",
            "litter_supersessions_reason_check",
        )
        if reasons != EXPECTED_LITTER_SUPERSESSION_REASONS:
            raise RuntimeError(f"migration_readback_reason_constraint_mismatch:{reasons}")
        if not _mating_id_nullable(connection):
            raise RuntimeError("migration_readback_mating_id_not_nullable")
        function_body, function_definition = _function_readback(
            connection,
            "202608220001_extend_litter_supersession_for_fact_corrections.sql",
        )
        log_description = _verify_migration_log(
            connection, item.migration_id, required=True
        )
        return {
            "migration_log_present": True,
            "migration_log_description_sha256": hashlib.sha256(
                log_description.encode("utf-8")
            ).hexdigest(),
            "reason_constraint_sha256": hashlib.sha256(constraint.encode("utf-8")).hexdigest(),
            "reason_values": list(reasons),
            "validate_litter_supersession_body_sha256": hashlib.sha256(
                function_body.encode("utf-8")
            ).hexdigest(),
            "validate_litter_supersession_sha256": hashlib.sha256(
                function_definition.encode("utf-8")
            ).hexdigest(),
            "validator_trigger": trigger,
        }
    if item.migration_id == "202608220002_allow_herdmaster_farrowing_protected_claims":
        acl = _verify_protected_claim_acl(connection)
        constraint, action_kinds = _constraint_readback(
            connection,
            "app_private",
            "oom_protected_action_claims",
            "oom_protected_action_claims_action_kind_check",
        )
        if action_kinds not in (
            PREDECESSOR_PROTECTED_ACTION_KINDS,
            EXPECTED_PROTECTED_ACTION_KINDS,
        ):
            raise RuntimeError(f"migration_readback_action_constraint_mismatch:{action_kinds}")
        if action_kinds == EXPECTED_PROTECTED_ACTION_KINDS:
            _verify_migration_log(
                connection,
                "202608260001_allow_herdmaster_litter_actions_protected_claims",
                required=True,
            )
        log_description = _verify_migration_log(
            connection, item.migration_id, required=True
        )
        return {
            "migration_log_present": True,
            "migration_log_description_sha256": hashlib.sha256(
                log_description.encode("utf-8")
            ).hexdigest(),
            "action_kind_constraint_sha256": hashlib.sha256(
                constraint.encode("utf-8")
            ).hexdigest(),
            "action_kinds": list(action_kinds),
            "protected_claim_acl": acl,
        }
    if item.migration_id == "202608260001_allow_herdmaster_litter_actions_protected_claims":
        acl = _verify_protected_claim_acl(connection)
        constraint, action_kinds = _constraint_readback(connection, "app_private",
            "oom_protected_action_claims", "oom_protected_action_claims_action_kind_check")
        if action_kinds != EXPECTED_PROTECTED_ACTION_KINDS:
            raise RuntimeError(f"migration_readback_litter_actions_constraint_mismatch:{action_kinds}")
        description = _verify_migration_log(connection, item.migration_id, required=True)
        return {"migration_log_present": True,
            "migration_log_description_sha256": hashlib.sha256(description.encode()).hexdigest(),
            "action_kind_constraint_sha256": hashlib.sha256(constraint.encode()).hexdigest(),
            "action_kinds": list(action_kinds), "protected_claim_acl": acl}
    description = _migration_log_description(connection, item.migration_id)
    if not description:
        raise RuntimeError(f"migration_readback_historical_log_missing:{item.migration_id}")
    for relation in HISTORICAL_CREATED_RELATIONS.get(item.migration_id, ()):
        if not connection.execute("select pg_catalog.to_regclass(%s) is not null", (relation,)).fetchone()[0]:
            raise RuntimeError(f"migration_readback_historical_relation_missing:{relation}")
    return {"migration_log_present": True, "migration_log_description_sha256": hashlib.sha256(description.encode()).hexdigest()}


def run(database_url: str, environ: dict[str, str] | None = None) -> dict:
    import psycopg

    runtime_env = environ or dict(os.environ)
    commit, service_id, instance_id = _metadata(runtime_env)
    _validate_legacy_adoption_transport(runtime_env)
    sql_by_id = [(item, _load_sql(item)) for item in ALLOWLIST]
    report = {"source_commit": commit, "service_id": service_id, "migrations": []}
    active_item: AllowedMigration | None = None
    applying_new_item = False

    # Session advisory locking is deliberately outside the one mutation
    # transaction. Every bootstrap, migration, receipt, anchor, baseline and
    # checkpoint mutation commits together or rolls back together.
    with psycopg.connect(database_url, connect_timeout=10, autocommit=True) as connection:
        connection.execute("select pg_advisory_lock(%s)", (LOCK_KEY,))
        try:
            try:
                with connection.transaction():
                    receipt_table_exists = connection.execute(
                        "select pg_catalog.to_regclass('app_private.production_migration_receipts') is not null"
                    ).fetchone()[0]
                    if receipt_table_exists:
                        if any(
                            runtime_env.get(name, "").strip()
                            for name in (
                                "RENDER_MIGRATION_BASELINE_IDS",
                                "RENDER_MIGRATION_BASELINE_CATALOG_SHA256",
                                "RENDER_MIGRATION_BASELINE_AUTHORIZATION_ID",
                            )
                        ):
                            raise RuntimeError("migration_baseline_already_initialized")
                        _verify_private_schema(connection, required=True)
                        trust_table_flags = [
                            connection.execute("select pg_catalog.to_regclass(%s) is not null", (name,)).fetchone()[0]
                            for name in (
                                "app_private.production_migration_receipt_identity_anchors",
                                "app_private.production_migration_baselines",
                                "app_private.production_migration_catalog_checkpoints",
                            )]
                        trust_tables_exist = all(trust_table_flags)
                        if any(trust_table_flags) and not trust_tables_exist:
                            raise RuntimeError("migration_trust_tables_partial_state")
                        if trust_tables_exist:
                            if any(runtime_env.get(name, "").strip() for name in (
                                "RENDER_MIGRATION_LEGACY_ADOPTION_JSON",
                                "RENDER_MIGRATION_LEGACY_ADOPTION_AUTHORIZATION_ID",
                                "RENDER_MIGRATION_LEGACY_ADOPTION_PACKET_SHA256",
                            )):
                                raise RuntimeError("migration_legacy_adoption_already_initialized")
                            receipt_guard = _verify_receipt_guard(connection)
                            report["prior_catalog_checkpoint"] = _verify_catalog_checkpoint(connection)
                        else:
                            adoption = _requested_legacy_adoption(
                                connection, runtime_env, commit=commit, service_id=service_id
                            )
                            if adoption is None:
                                raise RuntimeError("migration_legacy_adoption_authorization_required")
                            connection.execute(BOOTSTRAP_SQL)
                            receipt_guard = _verify_receipt_guard(connection)
                            for item, legacy_ordinal, receipt_id in adoption.pop("verified_receipts"):
                                receipt = _verify_receipt_row(
                                    connection, item, legacy_ordinal, service_id=service_id,
                                    outcome="applied", receipt_id=receipt_id,
                                )
                                if not receipt["identity_anchored_now"]:
                                    raise RuntimeError("migration_legacy_adoption_anchor_not_created")
                            _insert_baseline(
                                connection, adoption, commit=commit,
                                service_id=service_id, instance_id=instance_id,
                            )
                            report["legacy_adoption"] = {
                                "authorization_id": adoption["baseline_id"],
                                "source_catalog_sha256": adoption["source_catalog_sha256"],
                                "receipt_count": len(LEGACY_ADOPTION_RECEIPT_IDS),
                            }
                    else:
                        _verify_private_schema(connection, required=False)
                        requested_baseline = _requested_baseline(connection, runtime_env)
                        connection.execute(BOOTSTRAP_SQL)
                        receipt_guard = _verify_receipt_guard(connection)
                        if requested_baseline:
                            _insert_baseline(
                                connection,
                                requested_baseline,
                                commit=commit,
                                service_id=service_id,
                                instance_id=instance_id,
                            )

                    baseline = _load_baseline(connection)
                    baseline_ids = set(baseline["migration_ids"] if baseline else ())
                    for ordinal, (item, sql) in enumerate(sql_by_id, 1):
                        active_item = item
                        applying_new_item = False
                        if item.migration_id in baseline_ids:
                            applied_exists = connection.execute(
                                """select exists(select 1
                                     from app_private.production_migration_receipts
                                    where migration_id=%s and outcome='applied')""",
                                (item.migration_id,),
                            ).fetchone()[0]
                            if applied_exists:
                                raise RuntimeError(
                                    f"migration_baseline_receipt_overlap:{item.migration_id}"
                                )
                            report["migrations"].append(
                                {
                                    "migration_id": item.migration_id,
                                    "sha256": item.sha256,
                                    "outcome": "baseline_verified",
                                    "baseline_id": baseline["baseline_id"],
                                    "baseline_catalog_sha256": baseline[
                                        "source_catalog_sha256"
                                    ],
                                    "receipt_guard": receipt_guard,
                                }
                            )
                            continue

                        prior_exists = connection.execute(
                            """select exists(select 1
                                 from app_private.production_migration_receipts
                                where migration_id=%s and outcome='applied')""",
                            (item.migration_id,),
                        ).fetchone()[0]
                        if prior_exists:
                            prior = _verify_receipt_row(
                                connection,
                                item,
                                None,
                                service_id=service_id,
                                outcome="applied",
                                create_anchor=False,
                            )
                            _verify_migration_precondition(
                                connection, item, already_applied=True
                            )
                            readback = _verify_migration_readback(connection, item)
                            if prior.get("identity_anchor_missing"):
                                raise RuntimeError(
                                    f"legacy_migration_receipt_identity_unverifiable:"
                                    f"{item.migration_id}"
                                )
                            report["migrations"].append(
                                {
                                    "migration_id": item.migration_id,
                                    "sha256": item.sha256,
                                    "outcome": "already_applied",
                                    "receipt_id": prior["receipt_id"],
                                    "applied_source_commit": prior["source_commit"],
                                    "applied_at": prior["applied_at"].isoformat(),
                                    "receipt_identity": {
                                        **prior,
                                        "applied_at": prior["applied_at"].isoformat(),
                                    },
                                    "receipt_guard": receipt_guard,
                                    "readback": readback,
                                }
                            )
                            continue

                        applying_new_item = True
                        _verify_migration_precondition(
                            connection, item, already_applied=False
                        )
                        connection.execute(sql)
                        readback = _verify_migration_readback(connection, item)
                        receipt_id = str(uuid.uuid4())
                        connection.execute(
                            """insert into app_private.production_migration_receipts
                               (receipt_id,migration_id,migration_filename,migration_sha256,
                                ordinal,outcome,source_commit,render_service_id,render_instance_id)
                               values(%s,%s,%s,%s,%s,'applied',%s,%s,%s)""",
                            (
                                receipt_id,
                                item.migration_id,
                                item.filename,
                                item.sha256,
                                ordinal,
                                commit,
                                service_id,
                                instance_id,
                            ),
                        )
                        receipt = _verify_receipt_row(
                            connection,
                            item,
                            ordinal,
                            service_id=service_id,
                            outcome="applied",
                            receipt_id=receipt_id,
                        )
                        report["migrations"].append(
                            {
                                "migration_id": item.migration_id,
                                "sha256": item.sha256,
                                "outcome": "applied",
                                "receipt_id": receipt_id,
                                "receipt_identity": {
                                    **receipt,
                                    "applied_at": receipt["applied_at"].isoformat(),
                                },
                                "receipt_guard": receipt_guard,
                                "readback": readback,
                            }
                        )

                    report["catalog_checkpoint"] = _ensure_catalog_checkpoint(
                        connection,
                        commit=commit,
                        service_id=service_id,
                        instance_id=instance_id,
                    )
            except Exception as exc:
                if active_item is not None and applying_new_item:
                    raise RuntimeError(
                        f"migration_failed_and_rolled_back:{active_item.migration_id}:receipt=none"
                    ) from exc
                raise
        finally:
            connection.execute("select pg_advisory_unlock(%s)", (LOCK_KEY,))
    return report


def main() -> int:
    if len(sys.argv) != 1:
        raise SystemExit("This rail accepts no migration or SQL arguments.")
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is not configured in the Render service environment.")
    print(json.dumps(run(database_url), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
