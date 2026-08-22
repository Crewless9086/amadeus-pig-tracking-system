"""Closed Render production-migration rail.

This entry point intentionally accepts no migration or SQL arguments.  The
ordered allowlist below is source-reviewed, and a Render one-off job supplies
the existing service environment (including DATABASE_URL) without credential
copying.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCK_KEY = 8_260_820_000_1
HEX_COMMIT = re.compile(r"^[0-9a-f]{40}$")


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
        sha256="1cfffdb4d01b7d6d0d2b35ede77eb478071151ceb5cda28b4c230ed3be2c3ee6",
    ),
)


EXPECTED_LITTER_SUPERSESSION_REASONS = (
    "duplicate_creation_same_farrowing",
    "fact_correction",
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
    "mortality",
    "rootline_delegated_family",
    "rootline_fertilizer_mixer_commissioning",
    "rootline_fertilizer_mixer_presence_refresh",
    "rootline_irrigation_segment",
    "sam_sale_payment",
)


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


def _constraint_readback(connection, schema: str, table: str, name: str) -> tuple[str, tuple[str, ...]]:
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
    values = tuple(sorted(set(re.findall(r"'([^']+)'", definition))))
    return definition, values


def _migration_log_readback(connection, migration_id: str) -> bool:
    row = connection.execute(
        "select exists(select 1 from app_private.migration_log where migration_id=%s)",
        (migration_id,),
    ).fetchone()
    return bool(row and row[0])


def _verify_migration_readback(connection, item: AllowedMigration) -> dict:
    if item.migration_id == "202608220001_extend_litter_supersession_for_fact_corrections":
        constraint, reasons = _constraint_readback(
            connection,
            "public",
            "litter_supersessions",
            "litter_supersessions_reason_check",
        )
        if reasons != EXPECTED_LITTER_SUPERSESSION_REASONS:
            raise RuntimeError(f"migration_readback_reason_constraint_mismatch:{reasons}")
        row = connection.execute(
            """select pg_catalog.pg_get_functiondef(p.oid)
                 from pg_catalog.pg_proc p
                 join pg_catalog.pg_namespace n on n.oid=p.pronamespace
                where n.nspname='public' and p.proname='validate_litter_supersession'
                  and pg_catalog.pg_get_function_identity_arguments(p.oid)=''"""
        ).fetchone()
        if not row or not row[0]:
            raise RuntimeError("migration_readback_validate_litter_supersession_missing")
        function_definition = row[0].replace("\r\n", "\n").replace("\r", "\n")
        required_fragments = (
            "cross-sow or cross-farrowing supersession denied",
            "duplicate supersession father mismatch",
            "durable owner confirmation does not match operation",
            "retained litter mating linkage mismatch",
            "exact litter child allowlists required",
        )
        if any(fragment not in function_definition for fragment in required_fragments):
            raise RuntimeError("migration_readback_validate_litter_supersession_mismatch")
        if not _migration_log_readback(connection, item.migration_id):
            raise RuntimeError(f"migration_readback_log_missing:{item.migration_id}")
        return {
            "migration_log_present": True,
            "reason_constraint_sha256": hashlib.sha256(constraint.encode("utf-8")).hexdigest(),
            "reason_values": list(reasons),
            "validate_litter_supersession_sha256": hashlib.sha256(
                function_definition.encode("utf-8")
            ).hexdigest(),
        }
    if item.migration_id == "202608220002_allow_herdmaster_farrowing_protected_claims":
        constraint, action_kinds = _constraint_readback(
            connection,
            "app_private",
            "oom_protected_action_claims",
            "oom_protected_action_claims_action_kind_check",
        )
        if action_kinds != EXPECTED_PROTECTED_ACTION_KINDS:
            raise RuntimeError(f"migration_readback_action_constraint_mismatch:{action_kinds}")
        if not _migration_log_readback(connection, item.migration_id):
            raise RuntimeError(f"migration_readback_log_missing:{item.migration_id}")
        return {
            "migration_log_present": True,
            "action_kind_constraint_sha256": hashlib.sha256(
                constraint.encode("utf-8")
            ).hexdigest(),
            "action_kinds": list(action_kinds),
        }
    return {}


def run(database_url: str, environ: dict[str, str] | None = None) -> dict:
    import psycopg

    commit, service_id, instance_id = _metadata(environ or dict(os.environ))
    sql_by_id = [(item, _load_sql(item)) for item in ALLOWLIST]
    report = {"source_commit": commit, "service_id": service_id, "migrations": []}

    with psycopg.connect(database_url, connect_timeout=10) as connection:
        connection.execute("select pg_advisory_lock(%s)", (LOCK_KEY,))
        try:
            connection.execute(BOOTSTRAP_SQL)
            connection.commit()
            for ordinal, (item, sql) in enumerate(sql_by_id, 1):
                prior = connection.execute(
                    """select receipt_id::text,migration_sha256,source_commit,applied_at
                       from app_private.production_migration_receipts
                       where migration_id=%s and outcome='applied'""",
                    (item.migration_id,),
                ).fetchone()
                if prior:
                    if prior[1] != item.sha256:
                        raise RuntimeError(f"applied_migration_checksum_conflict:{item.migration_id}")
                    readback = _verify_migration_readback(connection, item)
                    report["migrations"].append({
                        "migration_id": item.migration_id, "sha256": item.sha256,
                        "outcome": "already_applied", "receipt_id": prior[0],
                        "applied_source_commit": prior[2], "applied_at": prior[3].isoformat(),
                        "readback": readback,
                    })
                    continue

                receipt_id = str(uuid.uuid4())
                try:
                    connection.execute(sql)
                    readback = _verify_migration_readback(connection, item)
                    connection.execute(
                        """insert into app_private.production_migration_receipts
                           (receipt_id,migration_id,migration_filename,migration_sha256,
                            ordinal,outcome,source_commit,render_service_id,render_instance_id)
                           values(%s,%s,%s,%s,%s,'applied',%s,%s,%s)""",
                        (receipt_id, item.migration_id, item.filename, item.sha256,
                         ordinal, commit, service_id, instance_id),
                    )
                    connection.commit()
                except Exception as exc:
                    connection.rollback()
                    failure_id = str(uuid.uuid4())
                    connection.execute(
                        """insert into app_private.production_migration_receipts
                           (receipt_id,migration_id,migration_filename,migration_sha256,
                            ordinal,outcome,source_commit,render_service_id,render_instance_id,error_class)
                           values(%s,%s,%s,%s,%s,'failed',%s,%s,%s,%s)""",
                        (failure_id, item.migration_id, item.filename, item.sha256,
                         ordinal, commit, service_id, instance_id, type(exc).__name__),
                    )
                    connection.commit()
                    raise RuntimeError(
                        f"migration_failed_and_rolled_back:{item.migration_id}:receipt={failure_id}"
                    ) from exc
                report["migrations"].append({
                    "migration_id": item.migration_id, "sha256": item.sha256,
                    "outcome": "applied", "receipt_id": receipt_id,
                    "readback": readback,
                })
        finally:
            connection.execute("select pg_advisory_unlock(%s)", (LOCK_KEY,))
            connection.commit()
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
