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
        sha256="762825c57d9b6fd95a0e7197fb0cfb965f31988eabb059abc47fafbd6152ca62",
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
    if value != "herdmaster_record_farrowing_litter"
)
EXPECTED_MIGRATION_LOG_DESCRIPTIONS = {
    "202608220001_extend_litter_supersession_for_fact_corrections": (
        "Reuse append-only litter supersession rail for protected factual corrections"
    ),
    "202608220002_allow_herdmaster_farrowing_protected_claims": (
        "Admit exact-preview HERDMASTER farrowing claims through the canonical "
        "protected action spine."
    ),
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
                  pg_catalog.pg_get_triggerdef(t.oid,false)
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
    enabled, trigger_type, function_schema, function_name, function_args, definition = rows[0]
    if (
        enabled != "O"
        or trigger_type != 7  # ROW | BEFORE | INSERT
        or function_schema != "public"
        or function_name != "validate_litter_supersession"
        or function_args != ""
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
    return {
        "enabled": enabled,
        "trigger_type": trigger_type,
        "definition_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
    }


def _verify_protected_claim_acl(connection) -> dict:
    rows = connection.execute(
        """with target as (
               select c.oid,c.relacl,c.relowner
                 from pg_catalog.pg_class c
                 join pg_catalog.pg_namespace n on n.oid=c.relnamespace
                where n.nspname='app_private'
                  and c.relname='oom_protected_action_claims'
             ), privilege_names(privilege_type) as (
               values ('SELECT'),('INSERT'),('UPDATE'),('DELETE'),
                      ('TRUNCATE'),('REFERENCES'),('TRIGGER')
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
                 join pg_catalog.pg_roles r
                   on r.rolname in ('anon','authenticated')
                 cross join privilege_names p
                where pg_catalog.has_table_privilege(r.oid,t.oid,p.privilege_type)
             )
             select role_name,privilege_type from forbidden order by 1,2"""
    ).fetchall()
    if rows:
        raise RuntimeError(f"migration_readback_protected_claim_acl_mismatch:{rows}")
    return {"unauthorized_privilege_count": 0}


def _verify_receipt_guard(connection) -> dict:
    rows = connection.execute(
        """select t.tgenabled,t.tgtype,fn.nspname,p.proname,
                  pg_catalog.pg_get_function_identity_arguments(p.oid),
                  p.prosrc,l.lanname,p.prosecdef,p.proleakproof,p.provolatile,p.proparallel,p.proconfig
             from pg_catalog.pg_trigger t
             join pg_catalog.pg_class c on c.oid=t.tgrelid
             join pg_catalog.pg_namespace tn on tn.oid=c.relnamespace
             join pg_catalog.pg_proc p on p.oid=t.tgfoid
             join pg_catalog.pg_namespace fn on fn.oid=p.pronamespace
             join pg_catalog.pg_language l on l.oid=p.prolang
            where tn.nspname='app_private'
              and c.relname='production_migration_receipts'
              and t.tgname='trg_guard_production_migration_receipts'
              and not t.tgisinternal"""
    ).fetchall()
    if len(rows) != 1:
        raise RuntimeError("migration_receipt_guard_missing_or_ambiguous")
    (enabled, trigger_type, function_schema, function_name, function_args, body,
     language, security_definer, leakproof, volatility, parallel, config) = rows[0]
    normalized_body = re.sub(r"\s+", " ", str(body)).strip()
    if (
        enabled != "O"
        or trigger_type != 27  # ROW | BEFORE | UPDATE | DELETE
        or function_schema != "app_private"
        or function_name != "guard_production_migration_receipts"
        or function_args != ""
        or normalized_body != "begin raise exception 'production migration receipts are append-only'; end;"
        or (language, security_definer, leakproof, volatility, parallel, config)
        != ("plpgsql", False, False, "v", "u", None)
    ):
        raise RuntimeError("migration_receipt_guard_mismatch")
    return {
        "enabled": enabled,
        "trigger_type": trigger_type,
        "body_sha256": hashlib.sha256(normalized_body.encode("utf-8")).hexdigest(),
    }


def _verify_receipt_row(
    connection,
    item: AllowedMigration,
    ordinal: int,
    *,
    service_id: str,
    outcome: str,
    receipt_id: str | None = None,
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
        or row[4] != ordinal
        or row[5] != outcome
        or not HEX_COMMIT.fullmatch(str(row[6] or ""))
        or row[7] != service_id
        or not str(row[8] or "").strip()
        or (outcome == "applied" and row[9] is not None)
        or (outcome == "failed" and not str(expected_error or "").strip())
        or row[10] is None
    ):
        raise RuntimeError(f"migration_receipt_identity_mismatch:{item.migration_id}:{outcome}")
    return {
        "receipt_id": row[0],
        "migration_filename": row[2],
        "ordinal": row[4],
        "source_commit": row[6],
        "render_service_id": row[7],
        "render_instance_id": row[8],
        "applied_at": row[10],
    }


def _verify_migration_precondition(
    connection,
    item: AllowedMigration,
    *,
    already_applied: bool,
) -> str:
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
        if action_kinds == PREDECESSOR_PROTECTED_ACTION_KINDS:
            if already_applied:
                raise RuntimeError("migration_precondition_action_predecessor_mismatch")
            _verify_migration_log(connection, item.migration_id, required=False)
            return "predecessor"
        if action_kinds == EXPECTED_PROTECTED_ACTION_KINDS:
            _verify_migration_log(connection, item.migration_id, required=True)
            return "target"
        raise RuntimeError(f"migration_precondition_action_constraint_mismatch:{action_kinds}")
    return "not_applicable"


def _verify_migration_readback(connection, item: AllowedMigration) -> dict:
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
        if action_kinds != EXPECTED_PROTECTED_ACTION_KINDS:
            raise RuntimeError(f"migration_readback_action_constraint_mismatch:{action_kinds}")
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
    return {}


def run(database_url: str, environ: dict[str, str] | None = None) -> dict:
    import psycopg

    commit, service_id, instance_id = _metadata(environ or dict(os.environ))
    sql_by_id = [(item, _load_sql(item)) for item in ALLOWLIST]
    report = {"source_commit": commit, "service_id": service_id, "migrations": []}

    with psycopg.connect(database_url, connect_timeout=10) as connection:
        connection.execute("select pg_advisory_lock(%s)", (LOCK_KEY,))
        try:
            receipt_table_exists = connection.execute(
                "select to_regclass('app_private.production_migration_receipts') is not null"
            ).fetchone()[0]
            if receipt_table_exists:
                _verify_receipt_guard(connection)
            connection.execute(BOOTSTRAP_SQL)
            connection.commit()
            receipt_guard = _verify_receipt_guard(connection)
            for ordinal, (item, sql) in enumerate(sql_by_id, 1):
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
                        ordinal,
                        service_id=service_id,
                        outcome="applied",
                    )
                    _verify_migration_precondition(
                        connection, item, already_applied=True
                    )
                    readback = _verify_migration_readback(connection, item)
                    report["migrations"].append({
                        "migration_id": item.migration_id, "sha256": item.sha256,
                        "outcome": "already_applied", "receipt_id": prior["receipt_id"],
                        "applied_source_commit": prior["source_commit"],
                        "applied_at": prior["applied_at"].isoformat(),
                        "receipt_identity": {**prior, "applied_at": prior["applied_at"].isoformat()},
                        "receipt_guard": receipt_guard,
                        "readback": readback,
                    })
                    continue

                receipt_id = str(uuid.uuid4())
                try:
                    _verify_migration_precondition(
                        connection, item, already_applied=False
                    )
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
                    receipt = _verify_receipt_row(
                        connection,
                        item,
                        ordinal,
                        service_id=service_id,
                        outcome="applied",
                        receipt_id=receipt_id,
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
                    _verify_receipt_row(
                        connection,
                        item,
                        ordinal,
                        service_id=service_id,
                        outcome="failed",
                        receipt_id=failure_id,
                    )
                    connection.commit()
                    raise RuntimeError(
                        f"migration_failed_and_rolled_back:{item.migration_id}:receipt={failure_id}"
                    ) from exc
                report["migrations"].append({
                    "migration_id": item.migration_id, "sha256": item.sha256,
                    "outcome": "applied", "receipt_id": receipt_id,
                    "receipt_identity": {**receipt, "applied_at": receipt["applied_at"].isoformat()},
                    "receipt_guard": receipt_guard,
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
