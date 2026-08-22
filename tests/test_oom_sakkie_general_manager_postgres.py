import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest

from modules.oom_sakkie.general_manager_worker import (
    PostgresManagerCaseStore, normalize_candidate,
)


URL = os.getenv("OOM_PROTECTED_ACTION_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.skipif(not URL, reason="disposable PostgreSQL URL is required")


def connect():
    return psycopg.connect(URL)


@pytest.fixture(scope="module", autouse=True)
def exact_migration():
    with connect() as db:
        db.execute("create schema if not exists app_private")
        db.execute("""create table if not exists app_private.migration_log(
            migration_id text primary key,description text not null)""")
        for role in ("anon", "authenticated"):
            db.execute("do $block$ begin execute 'create role %s'; exception when duplicate_object then null; end $block$" % role)
    with connect() as db:
        migrations = Path(__file__).parents[1] / "supabase" / "migrations"
        db.execute((migrations / "202608170002_create_oom_manager_case_runtime.sql").read_text(encoding="utf-8"))
        db.execute("""create table if not exists app_private.oom_protected_action_claims(
            callback_token text primary key,action_kind text not null,
            provider_message_id text,status text,result_payload jsonb,
            completed_at timestamptz)""")
        db.execute((migrations / "202608190002_create_beacon_protected_publication_consumer.sql").read_text(encoding="utf-8"))


def candidate(ref="event:one", due=None, **changes):
    value = {"dedupe_key": "rootline:current-plan", "specialist": "ROOTLINE",
        "urgency": "urgent", "evidence_refs": [ref],
        "unknowns": ["delivered_current_irrigation_plan"],
        "summary": "Current irrigation plan is contained.",
        "next_action": "Delegate to ROOTLINE and retain ownership.",
        "next_reassessment_at": (due or datetime.now(timezone.utc)).isoformat()}
    value.update(changes)
    return value


def test_exact_replay_is_one_case_and_delivery_is_not_duplicated():
    now = datetime.now(timezone.utc)
    store = PostgresManagerCaseStore(connect_factory=connect)
    sends = []
    deliver = lambda case: (sends.append(case["case_id"]) or {
        "success": True, "status": "delivery_confirmed", "delivery_confirmed": True})
    current = candidate(due=now)
    first = store.run_cycle([current], now=now, source_revision="test",
        deliver=deliver, refresh=lambda claimed: current)
    second = store.run_cycle([candidate(due=now)], now=now + timedelta(seconds=1),
        source_revision="test", deliver=deliver, refresh=lambda claimed: current)
    assert first["candidates_created"] == 1 and first["deliveries_confirmed"] == 1
    assert second["candidate_replays"] == 1 and second["deliveries_confirmed"] == 0
    assert sends and len(sends) == 1
    with connect() as db:
        assert db.execute("select count(*) from app_private.oom_manager_cases where dedupe_key='rootline:current-plan'").fetchone()[0] == 1


@pytest.mark.parametrize("material_kind", ["target-page", "enquiry-policy"])
def test_beacon_material_binding_change_creates_exactly_one_successor(material_kind):
    """Builder-bound Page/policy digest changes advance one manager generation."""
    now = datetime.now(timezone.utc) + timedelta(minutes=10)
    dedupe = f"beacon:material-binding:{material_kind}"

    def value(marker):
        return {"dedupe_key": dedupe, "specialist": "BEACON", "urgency": "due",
            "evidence_refs": [f"beacon_result:{marker * 64}",
                              f"packet:BEACON-{material_kind}-{marker}"],
            "unknowns": ["current_sale_opportunity_proposal_or_exact_media_request"],
            "summary": "Current protected BEACON proposal requires owner review.",
            "next_action": "Deliver only the exact current protected card.",
            "next_reassessment_at": now.isoformat()}

    store = PostgresManagerCaseStore(connect_factory=connect)
    with connect() as db, db.cursor() as cur:
        first = normalize_candidate(value("a"), now=now)
        successor = normalize_candidate(value("b"), now=now)
        assert store._reconcile(cur, first, now) == "created"
        assert store._reconcile(cur, first, now) == "replayed"
        assert store._reconcile(cur, successor, now) == "changed"
        assert store._reconcile(cur, successor, now) == "replayed"
    with connect() as db:
        generation, digest = db.execute("""select generation,evidence_digest
            from app_private.oom_manager_cases where dedupe_key=%s""", (dedupe,)).fetchone()
    assert generation == 2
    assert digest == successor["evidence_digest"]


def test_changed_evidence_advances_generation_and_append_only_events_reject_mutation():
    now = datetime.now(timezone.utc) + timedelta(minutes=1)
    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [candidate("event:two", now)], now=now, source_revision="test")
    assert result["candidates_changed"] == 1
    with connect() as db:
        generation = db.execute("select generation from app_private.oom_manager_cases where dedupe_key='rootline:current-plan'").fetchone()[0]
        assert generation == 2
        with pytest.raises(psycopg.errors.RaiseException):
            db.execute("delete from app_private.oom_manager_case_events where case_id=(select case_id from app_private.oom_manager_cases where dedupe_key='rootline:current-plan')")


def test_expired_lease_resumes_after_restart():
    now = datetime.now(timezone.utc) + timedelta(minutes=2)
    with connect() as db:
        db.execute("""update app_private.oom_manager_cases set status='delegated',
            lease_until=%s,next_reassessment_at=%s where dedupe_key='rootline:current-plan'""",
            (now - timedelta(seconds=1), now - timedelta(seconds=1)))
    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [candidate("event:two", now)], now=now, source_revision="test")
    assert result["candidate_replays"] == 1
    assert result["cases_claimed"] == 1
    with connect() as db:
        row = db.execute("select status,lease_until,next_reassessment_at from app_private.oom_manager_cases where dedupe_key='rootline:current-plan'").fetchone()
        assert row[0] == "waiting_reassessment" and row[1] is None
        assert row[2] == now + timedelta(minutes=5)


def test_reclaimed_delegated_generation_contains_changed_refresh_before_provider():
    now = datetime.now(timezone.utc) + timedelta(minutes=2, seconds=30)
    store = PostgresManagerCaseStore(connect_factory=connect)
    current = normalize_candidate(candidate("event:two", now), now=now)
    changed = candidate("event:new-after-expired-delegation", now,
        summary="Canonical evidence changed while the prior lease was outstanding.")
    with connect() as db:
        db.execute("""update app_private.oom_manager_cases set status='delegated',
            assigned_worker_id='expired-cycle',lease_until=%s,next_reassessment_at=%s
            where dedupe_key='rootline:current-plan'""",
            (now - timedelta(seconds=1), now - timedelta(seconds=1)))
    delivered = []
    result = store.run_cycle([candidate("event:two", now)], now=now,
        source_revision="test", refresh=lambda claimed: changed,
        deliver=lambda case: delivered.append(case))
    assert delivered == []
    assert result["case_results"][0]["outcome_status"] == (
        "manager_delivery_refreshed_generation_deferred")
    with connect() as db:
        row = db.execute("""select evidence_digest,status,assigned_worker_id,lease_until
            from app_private.oom_manager_cases where dedupe_key='rootline:current-plan'""").fetchone()
    assert row == (current["evidence_digest"], "waiting_reassessment", None, None)


def test_changed_case_refresh_supersedes_stale_generation_then_stable_cycle_delivers():
    now = datetime.now(timezone.utc) + timedelta(minutes=3)
    stale = candidate("event:stale-weight", now,
        summary="Weekly weighing: 81 eligible tagged pig(s) missing.")
    current = candidate("batch:69086c13-4436-4548-8ab0-bed5453f6000", now,
        summary="Weekly weighing: 2 eligible tagged pig(s) missing.",
        next_action="Weigh only these missing eligible tags: 123, 151.",
        unknowns=[])
    delivered = []
    store = PostgresManagerCaseStore(connect_factory=connect)
    result = store.run_cycle(
        [stale], now=now, source_revision="test",
        refresh=lambda claimed: current,
        deliver=lambda case: (delivered.append(case) or {
            "success": True, "status": "delivery_confirmed",
            "delivery_confirmed": True}))
    assert result["deliveries_confirmed"] == 0
    assert delivered == []
    assert result["case_results"][0]["outcome_status"] == "manager_delivery_refreshed_generation_deferred"
    stable = store.run_cycle([current], now=now + timedelta(seconds=1),
        source_revision="test", refresh=lambda claimed: current,
        deliver=lambda case: (delivered.append(case) or {
            "success": True, "status": "delivery_confirmed",
            "delivery_confirmed": True}))
    assert stable["deliveries_confirmed"] == 1
    assert delivered[0]["summary"] == current["summary"]
    assert delivered[0]["next_action"].endswith("123, 151.")
    with connect() as db:
        events = db.execute("""select event_type from app_private.oom_manager_case_events
            where case_id=%s order by occurred_at""", (delivered[0]["case_id"],)).fetchall()
    assert ("evidence_changed",) in events


def test_missing_refresh_contains_delivery_and_retains_case():
    now = datetime.now(timezone.utc) + timedelta(minutes=4)
    delivered = []
    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [candidate("event:refresh-unavailable", now)], now=now,
        source_revision="test", refresh=lambda claimed: None,
        deliver=lambda case: delivered.append(case))
    assert delivered == []
    assert result["deliveries_confirmed"] == 0
    assert result["exceptions"] == 1
    assert result["case_results"][0]["outcome_status"] == "manager_delivery_refresh_unavailable"


def test_delivery_without_refresh_callback_fails_closed():
    now = datetime.now(timezone.utc) + timedelta(minutes=4, seconds=30)
    delivered = []
    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [candidate("event:no-refresh", now)], now=now, source_revision="test",
        deliver=lambda case: delivered.append(case))
    assert delivered == []
    assert result["case_results"][0]["outcome_status"] == "manager_delivery_refresh_unavailable"


def test_unsuccessful_provider_confirmation_cannot_suppress_retry():
    now = datetime.now(timezone.utc) + timedelta(minutes=4, seconds=40)
    current = candidate("event:ambiguous-provider-confirmation", now)
    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [current], now=now, source_revision="test", refresh=lambda claimed: current,
        deliver=lambda case: {"success": False, "status": "ambiguous",
                              "delivery_confirmed": True})
    assert result["deliveries_confirmed"] == 0
    assert result["exceptions"] == 1
    with connect() as db:
        row = db.execute("""select status,last_delivery_digest,evidence_digest
            from app_private.oom_manager_cases where dedupe_key='rootline:current-plan'""").fetchone()
    assert row[0] == "exception"
    assert row[1] != row[2]


def test_older_observation_epoch_cannot_replace_newer_herd_evidence():
    now = datetime.now(timezone.utc) + timedelta(minutes=4, seconds=45)
    newer = candidate("observed:2026-08-17T13:10:00+00:00", now,
        summary="Current 79/81 coverage.")
    older = candidate("observed:2026-08-17T13:05:00+00:00", now,
        summary="Stale 0/81 coverage.")
    store = PostgresManagerCaseStore(connect_factory=connect)
    store.run_cycle([newer], now=now, source_revision="test")
    store.run_cycle([older], now=now + timedelta(seconds=1), source_revision="test")
    with connect() as db:
        row = db.execute("""select summary,evidence_refs from app_private.oom_manager_cases
            where dedupe_key=%s""", (newer["dedupe_key"],)).fetchone()
    assert row[0] == newer["summary"]
    assert row[1] == newer["evidence_refs"]


def test_exact_replay_advances_epoch_and_blocks_later_stale_material():
    now = datetime.now(timezone.utc) + timedelta(minutes=4, seconds=50)
    first = candidate("observed:2026-08-17T13:00:00+00:00", now,
        summary="Material A.")
    same_newer_epoch = candidate("observed:2026-08-17T13:10:00+00:00", now,
        summary="Material A.")
    stale_changed = candidate("observed:2026-08-17T13:05:00+00:00", now,
        summary="Stale material B.")
    store = PostgresManagerCaseStore(connect_factory=connect)
    store.run_cycle([first], now=now, source_revision="test")
    store.run_cycle([same_newer_epoch], now=now + timedelta(seconds=1), source_revision="test")
    store.run_cycle([stale_changed], now=now + timedelta(seconds=2), source_revision="test")
    with connect() as db:
        row = db.execute("""select summary,evidence_refs from app_private.oom_manager_cases
            where dedupe_key=%s""", (first["dedupe_key"],)).fetchone()
    assert row[0] == "Material A."
    assert "observed:2026-08-17T13:10:00+00:00" in row[1]


def test_concurrent_newer_hold_and_prince_evidence_is_never_overwritten_or_delivered_stale():
    now = datetime.now(timezone.utc) + timedelta(minutes=5)
    stale = candidate("event:old-zero-coverage", now,
        summary="Weekly weighing coverage is 0/81.")
    retained = candidate("event:concurrent-current", now,
        summary="Pig 151 withdrawal/sales hold remains; Prince observation remains requested.",
        next_action="Preserve both supported HERDMASTER boundaries.",
        unknowns=["pig_151_withdrawal_clearance", "prince_trial_observation"])
    delivered = []

    def concurrent_advance(_claimed):
        current = normalize_candidate(retained, now=now)
        with connect() as db:
            row = db.execute("""select generation from app_private.oom_manager_cases
                where dedupe_key=%s for update""", (current["dedupe_key"],)).fetchone()
            db.execute("""update app_private.oom_manager_cases set generation=%s,
                evidence_digest=%s,evidence_refs=%s::jsonb,unknowns=%s::jsonb,
                summary=%s,next_action=%s,assigned_worker_id=null,lease_until=null,
                updated_at=%s where dedupe_key=%s""", (int(row[0]) + 1,
                current["evidence_digest"], json.dumps(current["evidence_refs"]),
                json.dumps(current["unknowns"]), current["summary"],
                current["next_action"], now, current["dedupe_key"]))
        return stale

    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [stale], now=now, source_revision="test", refresh=concurrent_advance,
        deliver=lambda case: delivered.append(case))
    assert delivered == []
    assert result["case_results"][0]["outcome_status"] == "manager_delivery_refresh_unavailable"
    with connect() as db:
        row = db.execute("""select summary,unknowns from app_private.oom_manager_cases
            where dedupe_key=%s""", (stale["dedupe_key"],)).fetchone()
    assert row[0] == retained["summary"]
    assert set(row[1]) == set(retained["unknowns"])
