from pathlib import Path


MIGRATION = Path("supabase/migrations/202608160001_create_medical_correction_and_order_line_guard.sql")


def test_medical_correction_rail_is_append_only_same_pig_and_idempotent():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "create table if not exists public.pig_medical_correction_events" in sql
    assert "idempotency_key text not null unique" in sql
    assert "supersedes_correction_event_id" in sql
    assert "original must belong to the same pig" in sql
    assert "retained event must belong to the same pig" in sql
    assert "before update or delete" in sql
    assert "grant select, insert" in sql
    assert "update public.pig_medical_events" not in sql.lower()
    assert "delete from public.pig_medical_events" not in sql.lower()
    assert "create table if not exists public.herdmaster_transfer_evidence_receipts" in sql
    assert "submitted_answers_digest" in sql


def test_active_order_line_guard_is_transaction_safe_and_partial():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "create unique index if not exists order_lines_one_active_pig_per_order_idx" in sql
    assert "on public.order_lines(order_id, pig_id)" in sql
    assert "not in ('cancelled', 'removed')" in sql
