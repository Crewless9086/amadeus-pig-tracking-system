"""Disposable-Postgres contract tests for durable Green command outcomes."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from threading import Barrier
import os
from hashlib import sha256
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from modules.documents.green_print_api import (
    authorize_standing_weekly_print, recover_held_standing_weekly_print)
from modules.documents.weekly_weight_sheet import (
    build_weekly_sheet_revision, protected_print_preview,
)


URL = os.getenv("GREEN_PRINT_DISPOSABLE_POSTGRES_URL", "").strip()
MIGRATION = (Path(__file__).parents[1] / "supabase" / "migrations" /
             "202608210001_create_green_print_jobs.sql")
DEVICE_FENCE_MIGRATION = (MIGRATION.parent /
             "202608250001_fence_green_print_lease_device_binding.sql")
LOST_LEDGER_MIGRATION = (MIGRATION.parent /
             "202608250002_adopt_green_lost_pre_attempt_claim.sql")
PDF_SHA = "a" * 64
EVENT = "00000000-0000-0000-0000-000000000001"


def test_green_migration_has_a_unique_release_version():
    migration_dir = MIGRATION.parent
    version = MIGRATION.name.split("_", 1)[0]
    matches = sorted(path.name for path in migration_dir.glob(f"{version}_*.sql"))
    assert matches == [MIGRATION.name]


def test_migration_has_schema_safe_pgcrypto_and_least_privilege_grants():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "pg_catalog.pg_extension" in source
    assert "%I.gen_random_bytes" in source and "%I.digest" in source
    assert "documents_green_worker_executor" in source
    assert "documents_api_executor" in source
    assert "revoke all on app_private.document_print_jobs from public, anon, authenticated" in source
    assert "grant execute on function app_private.create_authorized_document_print_job" in source
    assert "grant select" not in source and "grant insert" not in source and "grant update" not in source


def test_lost_ledger_migration_is_same_job_preattempt_only():
    source = LOST_LEDGER_MIGRATION.read_text(encoding="utf-8").lower()
    assert "create or replace function app_private.claim_document_print_job" in source
    assert "state='claimed' and lease_expires_at<=clock_timestamp()" in source
    assert "attempt_id is null and cups_job_id is null and provider_id is null" in source
    assert "authorization_expires_at > clock_timestamp()" in source
    assert "retry_deadline > clock_timestamp()" in source
    assert "green_print_job_device_active(document_print_jobs)" in source
    assert "for update skip locked limit 1" in source
    assert source.count("attempt_id is null and cups_job_id is null and provider_id is null") == 2
    assert "returning job_id into v_job_id" in source
    assert "if not found then return" in source
    assert "insert into app_private.document_print_jobs" not in source
    assert "lost_local_ledger_adoption" in source


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
            cursor.execute("""create table if not exists app_private.oom_protected_action_claims(
                callback_token text primary key, action_kind text not null,
                owner_user_id text not null, private_chat_id text not null,
                mission_id text not null, provider_message_id text not null,
                preview_card_message_id text, preview_digest text not null,
                evidence_generation text not null, preview_payload jsonb not null,
                status text not null, expires_at timestamptz not null,
                confirmation_provider_message_id text,
                confirmation_provider_timestamp timestamptz,result_payload jsonb,
                created_at timestamptz default now(),completed_at timestamptz,
                unique(action_kind,mission_id,preview_digest))""")
            cursor.execute("create extension if not exists pgcrypto with schema app_private")
            cursor.execute("""select n.nspname from pg_extension e join pg_namespace n
                on n.oid=e.extnamespace where e.extname='pgcrypto'""")
            extension_schema = cursor.fetchone()[0]
            if extension_schema != "app_private":
                cursor.execute(sql.SQL("""create or replace function app_private.gen_random_bytes(integer)
                    returns bytea language sql as 'select {}.gen_random_bytes($1)'""").format(
                        sql.Identifier(extension_schema)))
            cursor.execute(MIGRATION.read_text(encoding="utf-8"))
            cursor.execute(DEVICE_FENCE_MIGRATION.read_text(encoding="utf-8"))
            cursor.execute(LOST_LEDGER_MIGRATION.read_text(encoding="utf-8"))
            cursor.execute("""insert into app_private.document_print_device_registry
                (farm_scope_id,green_id,printer_id,cups_queue_id,registry_version,
                 canonical_api_origin,active,commissioned_at,evidence_sha256)
                values('farm-amadeus','green','printer','weekly-a4','registry-v1',
                 'https://documents.internal',true,clock_timestamp(),%s)
                on conflict do nothing""", ("c" * 64,))
            cursor.execute("""insert into app_private.document_print_jobs
                (job_id,farm_scope_id,document_id,document_version,document_revision,document_type,
                 generator_id,pdf_sha256,canonical_input_sha256,pdf_bytes,retrieval_url,options_json,authenticated_principal_id,
                 requester,request_channel,green_id,printer_id,cups_queue_id,registry_version,
                 authorization_receipt_id,authorization_expires_at,lease_owner,lease_token,
                 lease_expires_at,attempt_id,cups_job_id,provider_id,command_kind,
                 command_receipt_id,command_authorized_at,command_status,command_outcome,
                 command_accepted_at,command_completed_at,state,retry_deadline)
                values ('JOB-DB-1','farm-amadeus','DOC-DB-1','DOC-DB-1.r1',1,
                 'farm.weekly_weight_sheet.v1','web.print_sheets.v1',%s,%s,%s,
                 'https://documents.internal/api/documents/DOC-DB-1/versions/DOC-DB-1.r1/pdf',
                 '{"media":"A4","copies":1,"color":"monochrome","sides":"one-sided"}'::jsonb,
                 'principal','requester','private','green','printer','weekly-a4','registry-v1',
                 'AUTH-DB-1',clock_timestamp()+interval '1 hour','old-worker','old-lease',
                 clock_timestamp()-interval '1 second','ATTEMPT-DB-1','weekly-a4-42','ipps://printer',
                 'continue','COMMAND-DB-1',clock_timestamp()-interval '2 minutes','completed',
                 'continued',clock_timestamp()-interval '2 minutes',clock_timestamp()-interval '1 minute',
                 'claimed',clock_timestamp()+interval '1 hour')
                on conflict do nothing""", (PDF_SHA, "b" * 64, b"%PDF-" + b"x" * 80))
        yield connection
    finally:
        if not connection.closed:
            connection.rollback()
        connection.close()


def transition(db, lease="old-lease", version="DOC-DB-1.r1", digest=PDF_SHA,
               authorization="AUTH-DB-1", receipt="COMMAND-DB-1", kind="continue"):
    with db.cursor() as cursor:
        cursor.execute("select app_private.transition_document_print_command(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                       ("JOB-DB-1", lease, version, digest, authorization, receipt, kind, "accepted",
                        "farm-amadeus", "green", "recovered-worker"))
        return cursor.fetchone()[0]


def worker_transition(db, target, metadata=None, event=EVENT, worker="green-worker", green="green",
                      farm="farm-amadeus"):
    with db.cursor() as cursor:
        cursor.execute("select app_private.transition_document_print_job(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                       ("JOB-DB-1", "worker-lease", "DOC-DB-1.r1", PDF_SHA,
                        "AUTH-DB-1", target, event, farm, green, worker,
                        Jsonb(metadata or {})))
        return cursor.fetchone()[0]


def prepare_worker_job(db, state="claimed", attempt=None, cups=None, provider=None):
    with db.cursor() as cursor:
        cursor.execute("""update app_private.document_print_jobs set state=%s,
            lease_owner='green-worker',lease_token='worker-lease',
            lease_expires_at=clock_timestamp()+interval '5 minutes',attempt_id=%s,
            cups_job_id=%s,provider_id=%s,command_kind=null,command_receipt_id=null,
            command_status=null,command_outcome=null where job_id='JOB-DB-1'""",
                       (state, attempt, cups, provider))


def test_fresh_ledger_adopts_same_expired_preattempt_claim_once(db):
    with db.cursor() as cursor:
        cursor.execute("""update app_private.document_print_jobs set
            state='claimed', lease_owner='lost-worker', lease_token='lost-token',
            lease_expires_at=clock_timestamp()-interval '1 second',
            attempt_id=null,cups_job_id=null,provider_id=null,
            authorization_expires_at=clock_timestamp()+interval '1 hour',
            retry_deadline=clock_timestamp()+interval '1 hour'
            where job_id='JOB-DB-1'""")
        before = cursor.execute(
            "select count(*) from app_private.document_print_jobs"
        ).fetchone()[0]
        adopted = cursor.execute(
            "select job_id,lease_owner,state from app_private.claim_document_print_job(%s,%s,%s,%s)",
            ("farm-amadeus", "green", "fresh-worker", 300),
        ).fetchone()
        assert adopted == ("JOB-DB-1", "fresh-worker", "claimed")
        assert cursor.execute(
            "select count(*) from app_private.document_print_jobs"
        ).fetchone()[0] == before
        assert cursor.execute(
            "select count(*) from app_private.claim_document_print_job(%s,%s,%s,%s)",
            ("farm-amadeus", "green", "other-worker", 300),
        ).fetchone()[0] == 0
        event = cursor.execute("""select event_type,metadata_json->>'lost_local_ledger_adoption'
            from app_private.document_print_job_events where job_id='JOB-DB-1'
            order by event_at desc,event_id desc limit 1""").fetchone()
        assert event == ("lease_recovered", "true")


@pytest.mark.parametrize("blocked", [
    "attempt", "cups", "provider", "authorization", "retry", "device",
])
def test_fresh_ledger_refuses_ineligible_canonical_claim(db, blocked):
    with db.cursor() as cursor:
        cursor.execute("""update app_private.document_print_jobs set
            state='claimed',lease_owner='lost-worker',lease_token='lost-token',
            lease_expires_at=clock_timestamp()-interval '1 second',
            attempt_id=null,cups_job_id=null,provider_id=null,
            authorization_expires_at=clock_timestamp()+interval '1 hour',
            retry_deadline=clock_timestamp()+interval '1 hour'
            where job_id='JOB-DB-1'""")
        if blocked == "attempt":
            cursor.execute("update app_private.document_print_jobs set attempt_id='ATTEMPT-X'")
        elif blocked == "cups":
            cursor.execute("update app_private.document_print_jobs set cups_job_id='weekly-a4-99'")
        elif blocked == "provider":
            cursor.execute("update app_private.document_print_jobs set provider_id='ipps://printer'")
        elif blocked == "authorization":
            cursor.execute("update app_private.document_print_jobs set authorization_expires_at=clock_timestamp()-interval '1 second'")
        elif blocked == "retry":
            cursor.execute("update app_private.document_print_jobs set retry_deadline=clock_timestamp()-interval '1 second'")
        else:
            cursor.execute("update app_private.document_print_device_registry set active=false")
        assert cursor.execute(
            "select count(*) from app_private.claim_document_print_job(%s,%s,%s,%s)",
            ("farm-amadeus", "green", "fresh-worker", 300),
        ).fetchone()[0] == 0


def producer_job(**changes):
    pdf=b"%PDF-1.4\n"+b"x"*80
    value={"job_id":"JOB-PRODUCER-1","farm_scope_id":"farm-amadeus",
        "document_id":"DOC-PRODUCER-1","document_version":"DOC-PRODUCER-1.r1",
        "document_revision":1,"document_type":"farm.weekly_weight_sheet.v1",
        "generator_id":"web.print_sheets.v1","pdf_sha256":sha256(pdf).hexdigest(),
        "canonical_input_sha256":"d"*64,
        "retrieval_url":"https://documents.internal/api/documents/DOC-PRODUCER-1/versions/DOC-PRODUCER-1.r1/pdf",
        "options":{"media":"A4","copies":1,"color":"monochrome","sides":"one-sided"},
        "green_id":"green","printer_id":"printer","cups_queue_id":"weekly-a4",
        "registry_version":"registry-v1","authorization_receipt_id":"AUTH-PRODUCER-1",
        "authorization_expires_at":"2099-08-21T10:00:00+00:00",
        "retry_deadline":"2099-08-21T10:00:00+00:00"}
    value.update(changes)
    return value,pdf


def install_producer_claim(db,job):
    preview={key:job[key] for key in ("job_id","document_id","document_version",
        "pdf_sha256","farm_scope_id","green_id","printer_id","cups_queue_id",
        "registry_version")}
    with db.cursor() as cursor:
        cursor.execute("""insert into app_private.oom_protected_action_claims(
          callback_token,action_kind,owner_user_id,private_chat_id,mission_id,
          provider_message_id,preview_digest,evidence_generation,preview_payload,status,expires_at)
          values(%s,'documents_green_print','owner-1','owner-1','DMQ-20260816-01',
          'provider-1','digest','generation',%s,'executing','2099-08-21T10:00:00Z')""",
          (job["authorization_receipt_id"],Jsonb(preview)))


def call_producer(db,job,pdf):
    with db.cursor() as cursor:
        cursor.execute("select (app_private.create_authorized_document_print_job(%s,%s,%s,%s,%s)).job_id",
            (Jsonb(job),pdf,"owner-1","oom_sakkie","telegram"))
        return cursor.fetchone()[0]


def standing_request_inputs(suffix="A"):
    owner=f"owner-standing-{suffix}"
    revision=build_weekly_sheet_revision(authenticated_principal_id=owner,
        requester="oom_sakkie",sheet_date=date(2026,8,25),
        rows=[{"pig_id":f"PIG-{suffix}","tag_number":suffix,"pen_id":"B1"}],
        document_id=f"WWS-STANDING-{suffix}")
    url=(f"https://documents.internal/api/documents/{revision.document_id}/versions/"
         f"{revision.version_id}/pdf")
    preview=protected_print_preview(revision=revision,
        job_id=f"GREEN-STANDING-{suffix}",farm_scope_id="farm-amadeus",
        green_id="green",printer_id="printer",cups_queue_id="weekly-a4",
        registry_version="registry-v1",retrieval_url=url,
        authorization_expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
    parsed={"telegram_user_id":owner,"telegram_chat_id":owner,
        "telegram_chat_type":"private","provider_message_id":f"MSG-{suffix}",
        "text":"Print the current weekly weighing sheet."}
    return preview,revision,parsed


def invoke_standing(preview,revision,parsed):
    connection=psycopg.connect(URL)
    try:
        return authorize_standing_weekly_print(preview,revision,parsed,
            connect_factory=lambda:connection)
    finally:
        if not connection.closed:
            connection.close()


def test_standing_authority_retains_receipt_when_job_fails(db,monkeypatch):
    monkeypatch.setenv("DOCUMENTS_FARM_SCOPE_ID","farm-amadeus")
    monkeypatch.setenv("DOCUMENTS_CANONICAL_API_ORIGIN","https://documents.internal")
    preview,revision,parsed=standing_request_inputs("ROLLBACK")
    preview={**preview,"green_id":"unregistered-green"}
    from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
    payload={key:value for key,value in preview.items() if key!="preview_digest"}
    preview["preview_digest"]=canonical_preview_digest("documents_green_print",payload)
    db.commit()
    with pytest.raises(psycopg.errors.RaiseException):
        invoke_standing(preview,revision,parsed)
    with psycopg.connect(URL) as verification, verification.cursor() as cursor:
        cursor.execute("""select status,result_payload->>'status',
          result_payload->>'request_text_sha256' from app_private.oom_protected_action_claims
          where mission_id like 'DMQ-20260816-01:WWS-STANDING-ROLLBACK%'""")
        status,held,digest=cursor.fetchone()
        assert status=="active" and held=="standing_print_request_held"
        assert digest==sha256(b"Print the current weekly weighing sheet.").hexdigest()
        cursor.execute("select count(*) from app_private.document_print_jobs where job_id='GREEN-STANDING-ROLLBACK'")
        assert cursor.fetchone()[0]==0


def test_held_request_resumes_after_registry_evidence_change_exactly_once(db,monkeypatch):
    monkeypatch.setenv("DOCUMENTS_FARM_SCOPE_ID","farm-amadeus")
    monkeypatch.setenv("DOCUMENTS_CANONICAL_API_ORIGIN","https://documents.internal")
    preview,revision,parsed=standing_request_inputs("HELD-RESUME")
    preview={**preview,"green_id":"held-green"}
    from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
    payload={key:value for key,value in preview.items() if key!="preview_digest"}
    preview["preview_digest"]=canonical_preview_digest("documents_green_print",payload)
    db.commit()
    with pytest.raises(psycopg.errors.RaiseException):
        invoke_standing(preview,revision,parsed)
    with psycopg.connect(URL) as activation, activation.cursor() as cursor:
        cursor.execute("""insert into app_private.document_print_device_registry(
          farm_scope_id,green_id,printer_id,cups_queue_id,registry_version,
          canonical_api_origin,active,commissioned_at,evidence_sha256)
          values('farm-amadeus','held-green','printer','weekly-a4','registry-v1',
          'https://documents.internal',true,clock_timestamp(),%s)""",("b"*64,))
    first=recover_held_standing_weekly_print(connect_factory=lambda:psycopg.connect(URL))
    second=recover_held_standing_weekly_print(connect_factory=lambda:psycopg.connect(URL))
    assert first["status"]=="documents_green_recovery_authorized"
    assert first["job_id"]=="GREEN-STANDING-HELD-RESUME"
    assert second["status"]=="documents_green_recovery_idle"
    with psycopg.connect(URL) as verification, verification.cursor() as cursor:
        cursor.execute("select count(*) from app_private.document_print_jobs where job_id=%s",
            (first["job_id"],));assert cursor.fetchone()[0]==1
        cursor.execute("""select status from app_private.oom_protected_action_claims
          where mission_id like 'DMQ-20260816-01:WWS-STANDING-HELD-RESUME%'""")
        assert cursor.fetchone()[0]=="completed"


def test_standing_authority_completed_response_loss_retry_is_one_job_no_provider_effect(db,monkeypatch):
    monkeypatch.setenv("DOCUMENTS_FARM_SCOPE_ID","farm-amadeus")
    monkeypatch.setenv("DOCUMENTS_CANONICAL_API_ORIGIN","https://documents.internal")
    preview,revision,parsed=standing_request_inputs("REPLAY")
    db.commit()
    first=invoke_standing(preview,revision,parsed)
    second=invoke_standing(preview,revision,
        {**parsed,"provider_message_id":"MSG-REPLAY-AFTER-LOSS"})
    assert first["job_id"]==second["job_id"]=="GREEN-STANDING-REPLAY"
    with psycopg.connect(URL) as verification, verification.cursor() as cursor:
        cursor.execute("""select cups_job_id,attempt_id,options_json,cups_queue_id,state
          from app_private.document_print_jobs where job_id=%s""",(first["job_id"],))
        rows=cursor.fetchall();assert len(rows)==1
        cups,attempt,options,queue,state=rows[0]
        assert (cups,attempt,queue,state)==(None,None,"weekly-a4","authorized")
        assert options=={"media":"A4","copies":1,"color":"monochrome","sides":"one-sided"}
        cursor.execute("select count(*) from app_private.document_print_job_events where job_id=%s",
            (first["job_id"],))
        assert cursor.fetchone()[0]==1


def test_concurrent_identical_standing_requests_converge_on_one_job(db,monkeypatch):
    monkeypatch.setenv("DOCUMENTS_FARM_SCOPE_ID","farm-amadeus")
    monkeypatch.setenv("DOCUMENTS_CANONICAL_API_ORIGIN","https://documents.internal")
    preview,revision,parsed=standing_request_inputs("CONCURRENT")
    # Registry/setup from the fixture must be visible to independent contenders.
    db.commit()
    def invoke(index):
        return invoke_standing(preview,revision,
            {**parsed,"provider_message_id":f"MSG-CONCURRENT-{index}"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(invoke,(1,2)))
    assert [item["job_id"] for item in results]==[
        "GREEN-STANDING-CONCURRENT","GREEN-STANDING-CONCURRENT"]
    with db.cursor() as cursor:
        cursor.execute("select count(*),count(cups_job_id),count(attempt_id) from app_private.document_print_jobs where job_id='GREEN-STANDING-CONCURRENT'")
        assert cursor.fetchone()==(1,0,0)
        cursor.execute("select count(*) from app_private.document_print_job_events where job_id='GREEN-STANDING-CONCURRENT'")
        assert cursor.fetchone()[0]==1


def test_producer_requires_claim_registered_pair_exact_origin_and_is_replay_stable(db):
    job,pdf=producer_job();install_producer_claim(db,job)
    assert call_producer(db,job,pdf)==job["job_id"]
    assert call_producer(db,job,pdf)==job["job_id"]
    with db.cursor() as cursor:
        cursor.execute("select count(*) from app_private.document_print_job_events where job_id=%s",
            (job["job_id"],))
        assert cursor.fetchone()[0]==1


@pytest.mark.parametrize("field,value,error",[
    ("farm_scope_id","other-farm","protected document claim invalid"),
    ("green_id","other-green","protected document claim invalid"),
    ("printer_id","other-printer","protected document claim invalid"),
    ("retrieval_url","https://evil.invalid/api/documents/DOC-PRODUCER-1/versions/DOC-PRODUCER-1.r1/pdf","registered document device pair invalid"),
])
def test_producer_wrong_scope_device_or_origin_has_zero_effects(db,field,value,error):
    job,pdf=producer_job();install_producer_claim(db,job);job[field]=value
    with db.cursor() as cursor: cursor.execute("savepoint rejected_producer")
    with pytest.raises(psycopg.errors.RaiseException,match=error): call_producer(db,job,pdf)
    with db.cursor() as cursor:
        cursor.execute("rollback to savepoint rejected_producer")
        cursor.execute("select count(*) from app_private.document_print_jobs where job_id=%s",(job["job_id"],))
        assert cursor.fetchone()[0]==0
        cursor.execute("select count(*) from app_private.document_print_job_events where job_id=%s",(job["job_id"],))
        assert cursor.fetchone()[0]==0


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
        cursor.execute("""select command_status,command_outcome,count(*) over()
          from app_private.document_print_jobs where job_id='JOB-DB-1'""")
        assert cursor.fetchone() == ("completed", "continued", 1)
        cursor.execute("select count(*) from app_private.document_print_job_events")
        assert cursor.fetchone()[0] == before


def test_reclaimed_current_lease_reads_same_outcome_without_mutation(db):
    with db.cursor() as cursor:
        cursor.execute("select * from app_private.claim_document_print_command('farm-amadeus','green','recovered-worker',300)")
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


@pytest.mark.parametrize("worker,green", [("wrong-worker", "green"), ("green-worker", "wrong-green")])
def test_transition_rejects_wrong_authenticated_execution_identity(db, worker, green):
    prepare_worker_job(db)
    with db.cursor() as cursor: cursor.execute("savepoint wrong_execution_identity")
    with pytest.raises(psycopg.errors.RaiseException, match="lease fence or binding invalid"):
        worker_transition(db, "submitting", {"attempt_id": "ATTEMPT-1"}, worker=worker, green=green)
    with db.cursor() as cursor: cursor.execute("rollback to savepoint wrong_execution_identity")


def test_transition_and_expired_recovery_reject_wrong_farm_or_green(db):
    prepare_worker_job(db)
    with db.cursor() as cursor: cursor.execute("savepoint wrong_scope")
    with pytest.raises(psycopg.errors.RaiseException, match="lease fence or binding invalid"):
        worker_transition(db, "submitting", {"attempt_id":"ATTEMPT-1"}, farm="wrong-farm")
    with db.cursor() as cursor:
        cursor.execute("rollback to savepoint wrong_scope")
        cursor.execute("update app_private.document_print_jobs set lease_expires_at=clock_timestamp()-interval '1 second'")
        cursor.execute("savepoint wrong_recovery_scope")
    with pytest.raises(psycopg.errors.RaiseException, match="lease recovery invalid"):
        with db.cursor() as cursor:
            cursor.execute("select app_private.recover_document_print_job_lease(%s,%s,%s,%s,%s,%s,%s,%s)",
                ("JOB-DB-1","recovered-worker",300,"DOC-DB-1.r1",PDF_SHA,"AUTH-DB-1",
                 "farm-amadeus","wrong-green"))
    with db.cursor() as cursor: cursor.execute("rollback to savepoint wrong_recovery_scope")


@pytest.mark.parametrize("registry_change", [
    "update app_private.document_print_device_registry set active=false",
    "update app_private.document_print_jobs set registry_version='registry-drift'",
    "update app_private.document_print_jobs set cups_queue_id='queue-drift'",
])
def test_lease_recovery_rejects_revoked_or_mismatched_device_binding(db,registry_change):
    prepare_worker_job(db)
    with db.cursor() as cursor:
        cursor.execute("update app_private.document_print_jobs set lease_expires_at=clock_timestamp()-interval '1 second'")
        cursor.execute(registry_change)
        cursor.execute("savepoint rejected_device_recovery")
    with pytest.raises(psycopg.errors.RaiseException,match="lease recovery invalid"):
        with db.cursor() as cursor:
            cursor.execute("select app_private.recover_document_print_job_lease(%s,%s,%s,%s,%s,%s,%s,%s)",
                ("JOB-DB-1","recovered-worker",300,"DOC-DB-1.r1",PDF_SHA,"AUTH-DB-1","farm-amadeus","green"))
    with db.cursor() as cursor: cursor.execute("rollback to savepoint rejected_device_recovery")


def test_lease_recovery_accepts_exact_active_device_binding(db):
    prepare_worker_job(db)
    with db.cursor() as cursor:
        cursor.execute("update app_private.document_print_jobs set lease_expires_at=clock_timestamp()-interval '1 second'")
        cursor.execute("select app_private.recover_document_print_job_lease(%s,%s,%s,%s,%s,%s,%s,%s)",
            ("JOB-DB-1","recovered-worker",300,"DOC-DB-1.r1",PDF_SHA,"AUTH-DB-1","farm-amadeus","green"))
        recovered=cursor.fetchone()[0]
    assert recovered is not None


def test_submitted_job_with_revoked_device_can_recover_for_readback_only(db):
    prepare_worker_job(db,"submitted","ATTEMPT-1","weekly-a4-42","ipps://printer/ipp/print")
    with db.cursor() as cursor:
        cursor.execute("update app_private.document_print_jobs set lease_expires_at=clock_timestamp()-interval '1 second'")
        cursor.execute("update app_private.document_print_device_registry set active=false")
        cursor.execute("select app_private.recover_document_print_job_lease(%s,%s,%s,%s,%s,%s,%s,%s)",
            ("JOB-DB-1","recovered-worker",300,"DOC-DB-1.r1",PDF_SHA,"AUTH-DB-1","farm-amadeus","green"))
        recovered=cursor.fetchone()[0]
    assert recovered is not None


def test_pre_attempt_renew_rejects_revoked_device_but_submitted_renew_allows_readback(db):
    prepare_worker_job(db)
    with db.cursor() as cursor:
        cursor.execute("update app_private.document_print_device_registry set active=false")
        cursor.execute("savepoint rejected_device_renew")
    with pytest.raises(psycopg.errors.RaiseException,match="lease renewal invalid"):
        with db.cursor() as cursor:
            cursor.execute("select app_private.renew_document_print_job_lease(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                ("JOB-DB-1","worker-lease","green-worker",300,"DOC-DB-1.r1",PDF_SHA,"AUTH-DB-1","farm-amadeus","green"))
    with db.cursor() as cursor:
        cursor.execute("rollback to savepoint rejected_device_renew")
        cursor.execute("update app_private.document_print_jobs set state='submitted',attempt_id='ATTEMPT-1',cups_job_id='weekly-a4-42'")
        cursor.execute("select app_private.renew_document_print_job_lease(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            ("JOB-DB-1","worker-lease","green-worker",300,"DOC-DB-1.r1",PDF_SHA,"AUTH-DB-1","farm-amadeus","green"))
        renewed=cursor.fetchone()[0]
    assert renewed is not None


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
        cursor.execute("select state,attempt_id,cups_job_id,provider_id,physical_follow_up_state from app_private.document_print_jobs where job_id='JOB-DB-1'")
        assert cursor.fetchone() == ("provider_completed", "ATTEMPT-1", "weekly-a4-42", "ipps://printer/ipp/print", "pending_owner_observation")


def record_physical_acceptance(db, evidence="PHYSICAL-DB-1", principal="principal",
                               version="DOC-DB-1.r1", digest=PDF_SHA,
                               cups="weekly-a4-42", provider="ipps://printer/ipp/print",
                               result="correct"):
    with db.cursor() as cursor:
        cursor.execute("""select state,physical_follow_up_state,physical_evidence_id
          from app_private.record_document_print_physical_acceptance(
            %s,%s,%s,%s,%s,%s,%s,clock_timestamp(),%s)""",
          ("JOB-DB-1", version, digest, cups, provider, principal, evidence, result))
        return cursor.fetchone()


def test_physical_acceptance_is_separate_exact_bound_and_replay_stable(db):
    prepare_worker_job(db, "provider_completed", "ATTEMPT-1", "weekly-a4-42",
                       "ipps://printer/ipp/print")
    with db.cursor() as cursor:
        cursor.execute("""update app_private.document_print_jobs
          set physical_follow_up_state='pending_owner_observation',updated_at=clock_timestamp()-interval '1 second'
          where job_id='JOB-DB-1'""")
    first = record_physical_acceptance(db)
    assert first == ("physically_confirmed", "resolved", "PHYSICAL-DB-1")
    with db.cursor() as cursor:
        cursor.execute("select physical_observed_at from app_private.document_print_jobs where job_id='JOB-DB-1'")
        observed_at = cursor.fetchone()[0]
        cursor.execute("""select state,physical_follow_up_state,physical_evidence_id
          from app_private.record_document_print_physical_acceptance(
            %s,%s,%s,%s,%s,%s,%s,%s,%s)""",
          ("JOB-DB-1", "DOC-DB-1.r1", PDF_SHA, "weekly-a4-42",
           "ipps://printer/ipp/print", "principal", "PHYSICAL-DB-1", observed_at, "correct"))
        assert cursor.fetchone() == first
        cursor.execute("select count(*) from app_private.document_print_job_events where event_type='physical_page_confirmed'")
        assert cursor.fetchone()[0] == 1


@pytest.mark.parametrize("field,value", [
    ("principal", "wrong-principal"), ("version", "DOC-DB-1.r2"),
    ("digest", "f" * 64), ("cups", "weekly-a4-99"),
    ("provider", "ipps://other/ipp/print"),
])
def test_physical_acceptance_binding_mismatch_has_zero_effect(db, field, value):
    prepare_worker_job(db, "provider_completed", "ATTEMPT-1", "weekly-a4-42",
                       "ipps://printer/ipp/print")
    with db.cursor() as cursor:
        cursor.execute("""update app_private.document_print_jobs
          set physical_follow_up_state='pending_owner_observation',updated_at=clock_timestamp()-interval '1 second'
          where job_id='JOB-DB-1'""")
        cursor.execute("savepoint rejected_physical_acceptance")
    with pytest.raises(psycopg.errors.RaiseException, match="physical acceptance binding invalid"):
        record_physical_acceptance(db, **{field: value})
    with db.cursor() as cursor:
        cursor.execute("rollback to savepoint rejected_physical_acceptance")
        cursor.execute("select state,physical_evidence_id from app_private.document_print_jobs where job_id='JOB-DB-1'")
        assert cursor.fetchone() == ("provider_completed", None)


def test_incorrect_physical_page_is_held_without_automatic_reprint(db):
    prepare_worker_job(db, "provider_completed", "ATTEMPT-1", "weekly-a4-42",
                       "ipps://printer/ipp/print")
    with db.cursor() as cursor:
        cursor.execute("""update app_private.document_print_jobs
          set physical_follow_up_state='pending_owner_observation',updated_at=clock_timestamp()-interval '1 second'
          where job_id='JOB-DB-1'""")
    assert record_physical_acceptance(db, evidence="PHYSICAL-EXCEPTION-1", result="incorrect") == (
        "held", "exception_owned", "PHYSICAL-EXCEPTION-1")


def test_uncertain_physical_page_is_distinct_canonical_exception(db):
    prepare_worker_job(db, "provider_completed", "ATTEMPT-1", "weekly-a4-42",
                       "ipps://printer/ipp/print")
    with db.cursor() as cursor:
        cursor.execute("""update app_private.document_print_jobs
          set physical_follow_up_state='pending_owner_observation',updated_at=clock_timestamp()-interval '1 second'
          where job_id='JOB-DB-1'""")
    assert record_physical_acceptance(db, evidence="PHYSICAL-UNCERTAIN-1", result="uncertain") == (
        "held", "exception_owned", "PHYSICAL-UNCERTAIN-1")
    with db.cursor() as cursor:
        cursor.execute("""select metadata_json->>'observation_result'
          from app_private.document_print_job_events
          where job_id='JOB-DB-1' and event_type='physical_page_exception'""")
        assert cursor.fetchone()==("uncertain",)


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


def test_two_fresh_ledgers_concurrently_adopt_exactly_once(db):
    with db.cursor() as cursor:
        cursor.execute("""update app_private.document_print_jobs set state='held'
            where job_id<>'JOB-DB-1' and state in ('authorized','claimed')""")
        cursor.execute("""update app_private.document_print_jobs set
            state='claimed',lease_owner='lost-worker',lease_token='lost-token',
            lease_expires_at=clock_timestamp()-interval '1 second',
            attempt_id=null,cups_job_id=null,provider_id=null,
            authorization_expires_at=clock_timestamp()+interval '1 hour',
            retry_deadline=clock_timestamp()+interval '1 hour'
            where job_id='JOB-DB-1'""")
    db.commit()
    barrier = Barrier(2)

    def claim(worker):
        with psycopg.connect(URL, autocommit=True) as connection:
            barrier.wait()
            return connection.execute(
                "select job_id from app_private.claim_document_print_job(%s,%s,%s,%s)",
                ("farm-amadeus", "green", worker, 300),
            ).fetchall()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ("fresh-a", "fresh-b")))
    assert sorted(len(rows) for rows in results) == [0, 1]
    assert [row[0] for rows in results for row in rows] == ["JOB-DB-1"]
    with db.cursor() as cursor:
        assert cursor.execute("""select count(*) from app_private.document_print_job_events
            where job_id='JOB-DB-1'
              and metadata_json->>'lost_local_ledger_adoption'='true'""").fetchone()[0] == 1
