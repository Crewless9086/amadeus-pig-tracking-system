import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row

from modules.pig_weights.herdmaster_live_transfer_contract import build_live_transfer_contract
from modules.pig_weights.herdmaster_transfer_evidence_action import (
    execute_evidence_action,
    preview_evidence_action,
)


URL = os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()


def _action_answers(packet, *, basis="Records do not establish administration count."):
    question = packet["consolidated_evidence_request"]["medical_pair_questions"][0]
    return {
        "medical_pair_answers": [{"event_ids": question["event_ids"],
                                  "choice": "Unknown_requires_veterinary_review",
                                  "factual_basis": basis}],
        "live_transfer_assessment": {
            "pig_id": "PIG-2026-B156", "fit_for_transport": "Unknown",
            "quarantine": "Unknown",
            "infectious_or_notifiable_disease_restriction": "Unknown",
            "veterinary_movement_stop": "Unknown",
            "serious_welfare_or_health_hold": "Unknown",
            "attributable_note": "Physical assessment remains required.",
        },
    }


def _create_action_database(admin, name):
    admin.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
    return URL.rsplit("/", 1)[0] + "/" + name


def _seed_action_database(url):
    migration = Path("supabase/migrations/202608160001_create_medical_correction_and_order_line_guard.sql").read_text(encoding="utf-8")
    with psycopg.connect(url) as db:
        db.execute("create schema app_private")
        db.execute("create table app_private.migration_log(migration_id text primary key,description text)")
        db.execute("""create table public.pigs(pig_id text primary key,tag_number text,pig_name text,
            animal_type text,status text,on_farm boolean,purpose text,sex text)""")
        db.execute("""create table public.pig_medical_events(medical_event_id text primary key,
            pig_id text references public.pigs(pig_id),product_id text,product_name text,treatment_date date,
            dose numeric,dose_unit text,withdrawal_days integer,withdrawal_end_date date,given_by text,
            source_sheet_row text,import_batch_id text,created_at timestamptz)""")
        db.execute("""create table public.orders(order_id text primary key,order_status text,
            approval_status text,requested_weight_range text,requested_quantity integer)""")
        db.execute("""create table public.order_lines(order_line_id text primary key,order_id text,
            pig_id text,line_status text,reserved_status text,created_at timestamptz default now())""")
        db.execute("""create table public.pig_observation_events(observation_event_id text primary key,
            pig_id text,observed_at timestamptz,recorded_at timestamptz,observer_reference text,
            observation_category text,severity text,factual_note text,measurements_json jsonb,
            source_system text,source_reference text,idempotency_key text unique,
            supersedes_observation_event_id text)""")
        db.execute("""create table public.pig_location_events(location_event_id text primary key,pig_id text,
            move_date date,from_pen_id text,to_pen_id text,reason_for_move text,moved_by text,
            move_notes text,source text,created_at timestamptz)""")
        db.execute("""create table public.sales_pricing(pricing_id text primary key,sale_category text,
            weight_band text,sex text,unit_price numeric,currency text,effective_from timestamptz,
            effective_to timestamptz,active boolean,change_reason text,created_by text,created_at timestamptz)""")
        db.execute("create table public.current_canonical_pig_state(pig_id text primary key,current_weight_kg numeric,last_weight_date date)")
        db.execute("create view public.current_canonical_pigs as select * from public.pigs")
        db.execute(migration)
        db.execute("""insert into public.pigs values
            ('PIG-2026-A643','123',null,'Weaner','Active',true,'Sale',null),
            ('PIG-2026-B156','151',null,'Weaner','Active',true,'Sale',null)""")
        db.execute("insert into public.current_canonical_pig_state values ('PIG-2026-A643',5.6,'2026-08-11'),('PIG-2026-B156',4.0,'2026-08-11')")
        db.execute("insert into public.orders values ('ORD-2026-A6EC6D','Draft','Pending','5_to_6_Kg',2)")
        db.execute("insert into public.order_lines(order_line_id,order_id,pig_id,line_status,reserved_status) values ('OL-2026-01E24C','ORD-2026-A6EC6D','PIG-2026-A643','Draft','Not_Reserved')")
        db.execute("""insert into public.pig_medical_events values
            ('MED-9123C224','PIG-2026-A643','PRD-1','Ecomectin 1%','2026-07-06',1,'ml',28,'2026-08-03','owner',null,null,'2026-07-06 19:18:15+00'),
            ('MED-F924E93D','PIG-2026-A643','PRD-1','Ecomectin 1%','2026-07-06',1,'ml',28,'2026-08-03','owner',null,null,'2026-07-06 19:27:59+00'),
            ('MED-6DEF1FD','PIG-2026-B156','PRD-1','Ecomectin 1%','2026-08-11',1,'ml',28,'2026-09-08','owner',null,null,'2026-08-11 10:00:00+00')""")
        db.execute("""insert into public.sales_pricing values
            ('PRICE-2','Young Piglets','2_to_4_Kg',null,350,'ZAR','2026-05-21',null,true,null,'owner','2026-05-21'),
            ('PRICE-5','Young Piglets','5_to_6_Kg',null,400,'ZAR','2026-05-21',null,true,null,'owner','2026-05-21')""")


@pytest.mark.skipif(not URL, reason="CHARLIE_DISPOSABLE_POSTGRES_URL not configured")
def test_append_only_medical_correction_and_active_line_uniqueness_in_disposable_postgres():
    suffix = uuid.uuid4().hex[:10]
    pig_id, order_id = f"MEDCOR-PIG-{suffix}", f"MEDCOR-ORDER-{suffix}"
    med_a, med_b = f"MEDCOR-A-{suffix}", f"MEDCOR-B-{suffix}"
    sql = Path("supabase/migrations/202608160001_create_medical_correction_and_order_line_guard.sql").read_text(encoding="utf-8")
    with psycopg.connect(URL, autocommit=False) as db:
        try:
            db.execute("create schema if not exists app_private")
            db.execute("create table if not exists app_private.migration_log(migration_id text primary key,description text)")
            db.execute("""create table if not exists public.pigs(
                pig_id text primary key,tag_number text,status text,on_farm boolean)""")
            db.execute("""create table if not exists public.pig_medical_events(
                medical_event_id text primary key,pig_id text not null references public.pigs(pig_id),
                treatment_date date not null,product_name text,withdrawal_days integer,
                withdrawal_end_date date)""")
            db.execute("""create table if not exists public.orders(
                order_id text primary key,order_status text not null default 'Draft')""")
            db.execute("""create table if not exists public.sales_pricing(
                pricing_id text primary key)""")
            db.execute("""create table if not exists public.order_lines(
                order_line_id text primary key,order_id text not null references public.orders(order_id),
                pig_id text,line_status text not null default 'Draft')""")
            db.execute(sql)
            db.execute("insert into public.pigs(pig_id) values(%s)", (pig_id,))
            for event_id in (med_a, med_b):
                db.execute("""insert into public.pig_medical_events
                    (medical_event_id,pig_id,treatment_date,product_name,withdrawal_days,withdrawal_end_date)
                    values(%s,%s,'2026-07-06',%s,28,'2026-08-03')""",
                    (event_id, pig_id, "Ecomectin 1%"))
            correction_id = f"MEDCOR-{suffix}"
            db.execute("""insert into public.pig_medical_correction_events
                (correction_event_id,pig_id,original_medical_event_id,retained_medical_event_id,
                 resolution,factual_basis,recorded_by,idempotency_key)
                values(%s,%s,%s,%s,'duplicate_record','Owner confirmed one administration','owner-test',%s)""",
                (correction_id, pig_id, med_b, med_a, f"idem-{suffix}"))
            assert db.execute("select count(*) from public.pig_medical_events where pig_id=%s", (pig_id,)).fetchone()[0] == 2
            db.execute("savepoint immutable_check")
            with pytest.raises(psycopg.Error):
                db.execute("update public.pig_medical_correction_events set factual_basis='changed' where correction_event_id=%s", (correction_id,))
            db.execute("rollback to savepoint immutable_check")

            db.execute("""insert into public.orders(order_id,order_status) values(%s,'Draft')""", (order_id,))
            db.execute("""insert into public.order_lines(order_line_id,order_id,pig_id,line_status)
                values(%s,%s,%s,'Draft')""", (f"LINE-A-{suffix}", order_id, pig_id))
            db.execute("savepoint duplicate_line")
            with pytest.raises(psycopg.errors.UniqueViolation):
                db.execute("""insert into public.order_lines(order_line_id,order_id,pig_id,line_status)
                    values(%s,%s,%s,'Draft')""", (f"LINE-B-{suffix}", order_id, pig_id))
            db.execute("rollback to savepoint duplicate_line")
        finally:
            db.rollback()


@pytest.mark.skipif(not URL, reason="CHARLIE_DISPOSABLE_POSTGRES_URL not configured")
def test_action_receipt_exact_replay_collision_and_atomic_rollback(monkeypatch):
    database = "op004_" + uuid.uuid4().hex[:12]
    with psycopg.connect(URL, autocommit=True) as admin:
        action_url = _create_action_database(admin, database)
    try:
        _seed_action_database(action_url)
        read_connect = lambda _url: psycopg.connect(action_url, row_factory=dict_row)
        action_connect = lambda _url: psycopg.connect(action_url)
        monkeypatch.setenv("OWNER_SESSION_SECRET", "postgres-action-secret")
        now = datetime(2026, 8, 16, 10, tzinfo=timezone.utc)
        packet = build_live_transfer_contract(
            ["PIG-2026-A643", "PIG-2026-B156"], "ORD-2026-A6EC6D",
            as_of=now.date(), connect_factory=read_connect,
        )
        supplied = _action_answers(packet)
        preview, preview_status = preview_evidence_action(packet, supplied, actor_id="owner-admin:charl", now=now)
        assert preview_status == 200
        result, status = execute_evidence_action(
            packet, supplied, actor_id="owner-admin:charl", idempotency_key="OP004-EXACT-1",
            confirmation_binding=preview["confirmation_binding"], connect_factory=action_connect, now=now,
        )
        assert status == 200, result
        assert result["evidence_rows_written"] == 3
        assert result["receipt_rows_written"] == 1
        assert result["total_rows_written"] == result["rows_written"] == 4
        assert result["receipt_idempotency_key"] == "OP004-EXACT-1"
        assert result["canonical_readback"]["pigs"][0]["medical_correction_authority"]["state"] == "available_append_only"

        mutated_packet = build_live_transfer_contract(
            ["PIG-2026-A643", "PIG-2026-B156"], "ORD-2026-A6EC6D",
            as_of=now.date(), connect_factory=read_connect,
        )
        replay, replay_status = execute_evidence_action(
            mutated_packet, supplied, actor_id="owner-admin:charl", idempotency_key="OP004-EXACT-1",
            confirmation_binding=preview["confirmation_binding"], connect_factory=action_connect, now=now,
        )
        assert replay_status == 200
        assert replay["status"] == "transfer_evidence_duplicate_execution"
        assert replay["total_rows_written"] == 0

        changed = _action_answers(packet, basis="A different asserted basis")
        conflict, conflict_status = execute_evidence_action(
            mutated_packet, changed, actor_id="owner-admin:charl", idempotency_key="OP004-EXACT-1",
            confirmation_binding=preview["confirmation_binding"], connect_factory=action_connect, now=now,
        )
        assert conflict_status == 409
        assert conflict["status"] == "transfer_evidence_idempotency_conflict"
        actor_conflict, actor_status = execute_evidence_action(
            mutated_packet, supplied, actor_id="owner-admin:another", idempotency_key="OP004-EXACT-1",
            confirmation_binding=preview["confirmation_binding"], connect_factory=action_connect, now=now,
        )
        assert actor_status == 409
        assert actor_conflict["status"] == "transfer_evidence_idempotency_conflict"
        altered_binding = dict(preview["confirmation_binding"], preview_digest="0" * 64)
        digest_conflict, digest_status = execute_evidence_action(
            mutated_packet, supplied, actor_id="owner-admin:charl", idempotency_key="OP004-EXACT-1",
            confirmation_binding=altered_binding, connect_factory=action_connect, now=now,
        )
        assert digest_status == 409
        assert digest_conflict["status"] == "transfer_evidence_idempotency_conflict"

        second_preview, _ = preview_evidence_action(mutated_packet, _action_answers(mutated_packet),
                                                    actor_id="owner-admin:charl", now=now)
        failed, failed_status = execute_evidence_action(
            mutated_packet, _action_answers(mutated_packet), actor_id="owner-admin:charl",
            idempotency_key="OP004-ROLLBACK-2",
            confirmation_binding=second_preview["confirmation_binding"], connect_factory=action_connect, now=now,
        )
        assert failed_status == 503
        assert failed["status"] == "transfer_evidence_atomic_execution_failed"
        assert failed["writes_performed"] is False
        with psycopg.connect(action_url) as verify:
            assert verify.execute("select count(*) from public.herdmaster_transfer_evidence_receipts").fetchone()[0] == 1
            assert verify.execute("select count(*) from public.pig_medical_correction_events").fetchone()[0] == 2
            assert verify.execute("select count(*) from public.pig_observation_events").fetchone()[0] == 1
    finally:
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(sql.SQL("drop database {} with (force)").format(sql.Identifier(database)))
