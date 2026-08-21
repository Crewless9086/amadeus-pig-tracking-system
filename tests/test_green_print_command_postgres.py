"""Disposable-Postgres contract tests for durable Green command outcomes."""
import os
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb


URL = os.getenv("GREEN_PRINT_DISPOSABLE_POSTGRES_URL", "").strip()
MIGRATION = (Path(__file__).parents[1] / "supabase" / "migrations" /
             "202608210001_create_green_print_jobs.sql")
PDF_SHA = "a" * 64
EVENT = "00000000-0000-0000-0000-000000000001"


def test_green_migration_has_a_unique_release_version():
    migration_dir = MIGRATION.parent
    version = MIGRATION.name.split("_", 1)[0]
    matches = sorted(path.name for path in migration_dir.glob(f"{version}_*.sql"))
    assert matches == [MIGRATION.name]


@pytest.fixture
def db():
    if not URL:
        pytest.skip("GREEN_PRINT_DISPOSABLE_POSTGRES_URL not configured")
    connection = psycopg.connect(URL)
    try:
        with connection.cursor() as cursor:
            cursor.execute("""do $$ begin
                if not exists (select 1 from pg_roles where rolname='anon') then create role anon; end if;
                if not exists (select 1 from pg_roles where rolname='authenticated') then create role authenticated; end if;
            end $$""")
            cursor.execute("create schema if not exists app_private")
            cursor.execute("create extension if not exists pgcrypto with schema app_private")
            cursor.execute("""select n.nspname from pg_extension e join pg_namespace n
                on n.oid=e.extnamespace where e.extname='pgcrypto'""")
            extension_schema = cursor.fetchone()[0]
            if extension_schema != "app_private":
                cursor.execute(sql.SQL("""create or replace function app_private.gen_random_bytes(integer)
                    returns bytea language sql as 'select {}.gen_random_bytes($1)'""").format(
                        sql.Identifier(extension_schema)))
            cursor.execute(MIGRATION.read_text(encoding="utf-8"))
            cursor.execute("""insert into app_private.document_print_jobs
                (job_id,document_id,document_version,document_revision,document_type,
                 generator_id,pdf_sha256,canonical_input_sha256,authenticated_principal_id,
                 requester,request_channel,green_id,printer_id,cups_queue_id,registry_version,
                 authorization_receipt_id,authorization_expires_at,lease_owner,lease_token,
                 lease_expires_at,attempt_id,cups_job_id,provider_id,command_kind,
                 command_receipt_id,command_authorized_at,command_status,command_outcome,
                 command_accepted_at,command_completed_at,state,retry_deadline)
                values ('JOB-DB-1','DOC-DB-1','DOC-DB-1.r1',1,
                 'farm.weekly_weight_sheet.v1','web.print_sheets.v1',%s,%s,
                 'principal','requester','private','green','printer','weekly-a4','registry-v1',
                 'AUTH-DB-1',clock_timestamp()+interval '1 hour','old-worker','old-lease',
                 clock_timestamp()-interval '1 second','ATTEMPT-DB-1','weekly-a4-42','ipps://printer',
                 'continue','COMMAND-DB-1',clock_timestamp()-interval '2 minutes','completed',
                 'continued',clock_timestamp()-interval '2 minutes',clock_timestamp()-interval '1 minute',
                 'claimed',clock_timestamp()+interval '1 hour')""", (PDF_SHA, "b" * 64))
        yield connection
    finally:
        connection.rollback()
        connection.close()


def transition(db, lease="old-lease", version="DOC-DB-1.r1", digest=PDF_SHA,
               authorization="AUTH-DB-1", receipt="COMMAND-DB-1", kind="continue"):
    with db.cursor() as cursor:
        cursor.execute("select app_private.transition_document_print_command(%s,%s,%s,%s,%s,%s,%s,%s)",
                       ("JOB-DB-1", lease, version, digest, authorization, receipt, kind, "accepted"))
        return cursor.fetchone()[0]


def worker_transition(db, target, metadata=None, event=EVENT):
    with db.cursor() as cursor:
        cursor.execute("select app_private.transition_document_print_job(%s,%s,%s,%s,%s,%s,%s,%s)",
                       ("JOB-DB-1", "worker-lease", "DOC-DB-1.r1", PDF_SHA,
                        "AUTH-DB-1", target, event, Jsonb(metadata or {})))
        return cursor.fetchone()[0]


def prepare_worker_job(db, state="claimed", attempt=None, cups=None, provider=None):
    with db.cursor() as cursor:
        cursor.execute("""update app_private.document_print_jobs set state=%s,
            lease_owner='green-worker',lease_token='worker-lease',
            lease_expires_at=clock_timestamp()+interval '5 minutes',attempt_id=%s,
            cups_job_id=%s,provider_id=%s,command_kind=null,command_receipt_id=null,
            command_status=null,command_outcome=null where job_id='JOB-DB-1'""",
                       (state, attempt, cups, provider))


def rejected_worker_transition(db, target, metadata=None):
    with db.cursor() as cursor:
        cursor.execute("savepoint rejected_worker_transition")
    with pytest.raises(psycopg.errors.RaiseException):
        worker_transition(db, target, metadata)
    with db.cursor() as cursor:
        cursor.execute("rollback to savepoint rejected_worker_transition")


@pytest.mark.parametrize("field,value", [
    ("lease", "old-lease"),
    ("version", "DOC-DB-1.r2"),
    ("digest", "f" * 64),
    ("authorization", "AUTH-WRONG"),
    ("receipt", "COMMAND-WRONG"),
    ("kind", "cancel"),
])
def test_completed_outcome_rejects_stale_lease_and_every_wrong_binding(db, field, value):
    with db.cursor() as cursor:
        cursor.execute("select count(*) from app_private.document_print_job_events")
        before = cursor.fetchone()[0]
        cursor.execute("savepoint rejected_replay")
    kwargs = {field: value}
    with pytest.raises(psycopg.errors.RaiseException, match="command fence or binding invalid"):
        transition(db, **kwargs)
    with db.cursor() as cursor:
        cursor.execute("rollback to savepoint rejected_replay")
        cursor.execute("select command_status,command_outcome,count(*) over() from app_private.document_print_jobs")
        assert cursor.fetchone() == ("completed", "continued", 1)
        cursor.execute("select count(*) from app_private.document_print_job_events")
        assert cursor.fetchone()[0] == before


def test_reclaimed_current_lease_reads_same_outcome_without_mutation(db):
    with db.cursor() as cursor:
        cursor.execute("select * from app_private.claim_document_print_command('recovered-worker',300)")
        claimed = cursor.fetchone()
        lease = claimed[next(i for i, column in enumerate(cursor.description) if column.name == "lease_token")]
        cursor.execute("select row_to_json(j), (select count(*) from app_private.document_print_job_events) from app_private.document_print_jobs j where job_id='JOB-DB-1'")
        before, event_count = cursor.fetchone()
    outcome = transition(db, lease=lease)
    assert outcome["command_status"] == "completed"
    assert outcome["command_outcome"] == "continued"
    assert outcome["command_replay"] is True
    with db.cursor() as cursor:
        cursor.execute("select row_to_json(j), (select count(*) from app_private.document_print_job_events) from app_private.document_print_jobs j where job_id='JOB-DB-1'")
        after, after_events = cursor.fetchone()
    # Claiming legitimately changes only lease ownership/token/expiry. Reading the
    # completed outcome performs no further canonical mutation or event append.
    for key in ("lease_owner", "lease_token", "lease_expires_at", "updated_at"):
        before.pop(key, None); after.pop(key, None)
    assert after == before
    assert after_events == event_count


@pytest.mark.parametrize("target", ["submitted", "provider_completed", "cancelled", "physically_confirmed"])
def test_ordinary_worker_cannot_skip_or_claim_protected_outcomes(db, target):
    prepare_worker_job(db)
    rejected_worker_transition(db, target, {"attempt_id": "ATTEMPT-1", "cups_job_id": "weekly-a4-42",
                                             "provider_id": "ipps://printer/ipp/print"})
    with db.cursor() as cursor:
        cursor.execute("select state,attempt_id,cups_job_id,provider_id from app_private.document_print_jobs where job_id='JOB-DB-1'")
        assert cursor.fetchone() == ("claimed", None, None, None)


@pytest.mark.parametrize("state,target", [
    ("submitting", "claimed"), ("submitted", "submitting"),
    ("provider_completed", "submitted"), ("held", "claimed"),
    ("ambiguous", "submitted"),
])
def test_ordinary_worker_cannot_regress_or_escape_terminal_hold(db, state, target):
    prepare_worker_job(db, state, "ATTEMPT-1", "weekly-a4-42", "ipps://printer/ipp/print")
    rejected_worker_transition(db, target, {"attempt_id": "ATTEMPT-1",
                                             "cups_job_id": "weekly-a4-42",
                                             "provider_id": "ipps://printer/ipp/print"})


def test_lawful_worker_path_preserves_immutable_provider_identities(db):
    prepare_worker_job(db)
    worker_transition(db, "submitting", {"attempt_id": "ATTEMPT-1", "observed_at": "2026-08-21T12:00:00Z"})
    worker_transition(db, "submitted", {"attempt_id": "ATTEMPT-1", "cups_job_id": "weekly-a4-42",
                                        "provider_id": "ipps://printer/ipp/print",
                                        "observed_at": "2026-08-21T12:00:01Z"},
                      "00000000-0000-0000-0000-000000000002")
    worker_transition(db, "provider_completed", {"attempt_id": "ATTEMPT-1", "cups_job_id": "weekly-a4-42",
                                                   "provider_id": "ipps://printer/ipp/print",
                                                   "observed_at": "2026-08-21T12:00:02Z"},
                      "00000000-0000-0000-0000-000000000003")
    with db.cursor() as cursor:
        cursor.execute("select state,attempt_id,cups_job_id,provider_id from app_private.document_print_jobs where job_id='JOB-DB-1'")
        assert cursor.fetchone() == ("provider_completed", "ATTEMPT-1", "weekly-a4-42", "ipps://printer/ipp/print")


def test_provider_completion_cannot_replace_established_identities(db):
    prepare_worker_job(db, "submitted", "ATTEMPT-1", "weekly-a4-42", "ipps://printer/ipp/print")
    rejected_worker_transition(db, "provider_completed", {"attempt_id": "ATTEMPT-1", "cups_job_id": "weekly-a4-99",
                                                        "provider_id": "ipps://printer/ipp/print"})


@pytest.mark.parametrize("metadata", [
    {"attempt_id": "ATTEMPT-2"},
    {"attempt_id": "ATTEMPT-1", "cups_job_id": "weekly a4 99", "provider_id": "ipps://printer/ipp/print"},
    {"attempt_id": "ATTEMPT-1", "cups_job_id": "weekly-a4-42", "provider_id": "http://untrusted"},
    {"attempt_id": "ATTEMPT-1", "actor_id": "forged-physical-observer"},
])
def test_worker_cannot_replace_or_forge_identity_metadata(db, metadata):
    prepare_worker_job(db, "submitting", "ATTEMPT-1")
    rejected_worker_transition(db, "submitted", metadata)
