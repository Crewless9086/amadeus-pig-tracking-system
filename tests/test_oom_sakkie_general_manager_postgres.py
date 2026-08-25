import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest

from modules.oom_sakkie.manager_case_sources import _completed_bulk_batch_findings
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


def test_exact_pig_terminal_evidence_completes_case_once_without_delivery():
    now = datetime.now(timezone.utc) + timedelta(seconds=30)
    dedupe = "herdmaster:bulk-condition:PG-TERMINAL"
    material = candidate("observation:PG-LOW", now, dedupe_key=dedupe,
        specialist="HERDMASTER", summary="Exact pig has material low BCS evidence.",
        next_action="Retain exact-pig recovery monitoring.", unknowns=[])
    recovered = candidate("observation:PG-IN-RANGE", now, dedupe_key=dedupe,
        specialist="HERDMASTER", summary="Exact pig is back in range.",
        next_action="Complete the exact-pig BCS follow-up.", unknowns=[],
        terminal_state="completed")
    store = PostgresManagerCaseStore(connect_factory=connect)
    with connect() as db, db.cursor() as cur:
        opened = normalize_candidate(material, now=now)
        terminal = normalize_candidate(recovered, now=now)
        assert store._reconcile(cur, opened, now) == "created"
        assert store._reconcile(cur, terminal, now) == "changed"
        assert store._reconcile(cur, terminal, now) == "replayed"
    with connect() as db:
        row = db.execute("""select status,generation,evidence_digest,assigned_worker_id,lease_until
            from app_private.oom_manager_cases where dedupe_key=%s""", (dedupe,)).fetchone()
        events = db.execute("""select event_type from app_private.oom_manager_case_events
            where case_id=(select case_id from app_private.oom_manager_cases where dedupe_key=%s)
            order by occurred_at""", (dedupe,)).fetchall()
    assert row == ("completed", 2, terminal["evidence_digest"], None, None)
    assert events.count(("completed",)) == 1


def test_latest_batch_candidate_is_stable_across_repeated_and_concurrent_cycles():
    now = datetime.now(timezone.utc) + timedelta(seconds=45)
    dedupe = "herdmaster:bulk-condition:PG-MULTI-BATCH"
    older = candidate("observation:PG-BATCH-OLDER", now, dedupe_key=dedupe,
        specialist="HERDMASTER", summary="Older low BCS evidence.",
        next_action="Retain recovery monitoring.", unknowns=[])
    latest = candidate("observation:PG-BATCH-LATEST", now, dedupe_key=dedupe,
        specialist="HERDMASTER", summary="Latest exact-pig BCS is in range.",
        next_action="Complete the exact-pig follow-up.", unknowns=[],
        terminal_state="completed")
    store = PostgresManagerCaseStore(connect_factory=connect)
    with connect() as db, db.cursor() as cur:
        assert store._reconcile(cur, normalize_candidate(older, now=now), now) == "created"
        assert store._reconcile(cur, normalize_candidate(latest, now=now), now) == "changed"
    # Every subsequent five-minute collector returns only the latest row. Two
    # independent worker connections serialize on the same stable dedupe key.
    def replay_latest(_worker):
        with connect() as db, db.cursor() as cur:
            return store._reconcile(cur, normalize_candidate(latest, now=now), now)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(replay_latest, range(2))) == ["replayed", "replayed"]
    with connect() as db:
        row = db.execute("""select status,generation,evidence_digest
            from app_private.oom_manager_cases where dedupe_key=%s""", (dedupe,)).fetchone()
        count = db.execute("""select count(*) from app_private.oom_manager_case_events
            where case_id=(select case_id from app_private.oom_manager_cases where dedupe_key=%s)""",
            (dedupe,)).fetchone()[0]
    assert row == ("completed", 2, normalize_candidate(latest, now=now)["evidence_digest"])
    assert count == 2


def test_two_completed_batches_query_and_repeated_cycles_use_only_latest_exact_pig_evidence():
    """Exercise the production collector, not a hand-built candidate sequence."""
    now = datetime.now(timezone.utc)
    suffix = now.strftime("%Y%m%d%H%M%S%f")
    pig_id = f"PG-MULTI-{suffix}"
    older_batch = f"10000000-0000-4000-8000-{suffix[-12:]}"
    latest_batch = f"20000000-0000-4000-8000-{suffix[-12:]}"
    older_draft = f"DRAFT-OLDER-{suffix}"
    latest_draft = f"DRAFT-LATEST-{suffix}"
    with connect() as db:
        db.execute("""insert into public.pigs(pig_id,tag_number,pig_name,status,on_farm)
            values(%s,%s,'Latest Evidence Pig','Active',true)""",
            (pig_id, f"TAG-{suffix}"))
        db.execute("""insert into public.bulk_weight_batches(
            batch_id,client_draft_id,weight_date,status,updated_at,completed_at)
            values(%s,%s,%s,'complete',%s,%s),(%s,%s,%s,'complete',%s,%s)""",
            (older_batch, older_draft, (now - timedelta(days=7)).date(),
             now - timedelta(days=7), now - timedelta(days=7),
             latest_batch, latest_draft, now.date(), now, now))
        db.execute("""insert into public.pig_weight_events(
            weight_event_id,pig_id,weight_date,weight_kg,source,source_sheet_row,
            bulk_batch_id,created_at) values
            (%s,%s,%s,40,'app_bulk_weight',1,%s,%s),
            (%s,%s,%s,50,'app_bulk_weight',2,%s,%s)""",
            (f"WEIGHT-OLDER-{suffix}", pig_id, (now - timedelta(days=7)).date(),
             older_batch, now - timedelta(days=7),
             f"WEIGHT-LATEST-{suffix}", pig_id, now.date(), latest_batch, now))
        db.execute("""insert into public.pig_observation_events(
            observation_event_id,pig_id,observed_at,recorded_at,observer_reference,
            observation_category,severity,factual_note,measurements_json,source_system,
            source_reference,idempotency_key) values
            (%s,%s,%s,%s,'test','body_condition','attention','older low BCS',
             '{"body_condition_score":2}'::jsonb,'owner','test',%s),
            (%s,%s,%s,%s,'test','body_condition','attention','latest low BCS',
             '{"body_condition_score":2}'::jsonb,'owner','test',%s)""",
            (f"OBS-OLDER-{suffix}", pig_id, now - timedelta(days=7),
             now - timedelta(days=7), f"bulk-bcs:{older_draft}:{pig_id}",
             f"OBS-LATEST-{suffix}", pig_id, now, now,
             f"bulk-bcs:{latest_draft}:{pig_id}"))

    findings = [row for row in _completed_bulk_batch_findings(now, connect=connect)
                if f"pig:{pig_id}" in row["evidence_refs"]]
    assert len(findings) == 2
    by_key = {row["dedupe_key"]: row for row in findings}
    condition = by_key[f"herdmaster:bulk-condition:{pig_id}"]
    weight = by_key[f"herdmaster:bulk-weight-change:{pig_id}"]
    assert f"observation:OBS-LATEST-{suffix}" in condition["evidence_refs"]
    assert f"observation:OBS-OLDER-{suffix}" not in condition["evidence_refs"]
    assert condition.get("terminal_state") is None
    assert f"weight_event:WEIGHT-LATEST-{suffix}" in weight["evidence_refs"]
    assert weight.get("terminal_state") is None

    store = PostgresManagerCaseStore(connect_factory=connect)
    first = store.run_cycle(findings, now=now, source_revision="test")
    second_findings = [row for row in _completed_bulk_batch_findings(
        now + timedelta(minutes=5), connect=connect)
        if f"pig:{pig_id}" in row["evidence_refs"]]
    second = store.run_cycle(second_findings, now=now + timedelta(minutes=5),
                             source_revision="test")
    assert first["candidates_created"] == 2
    assert second["candidate_replays"] == 2
    with connect() as db:
        rows = db.execute("""select dedupe_key,status,generation from app_private.oom_manager_cases
            where dedupe_key in (%s,%s) order by dedupe_key""",
            (condition["dedupe_key"], weight["dedupe_key"])).fetchall()
        event_count = db.execute("""select count(*) from app_private.oom_manager_case_events
            where case_id in (select case_id from app_private.oom_manager_cases
                where dedupe_key in (%s,%s))""",
            (condition["dedupe_key"], weight["dedupe_key"])).fetchone()[0]
    assert rows == [(condition["dedupe_key"], "waiting_reassessment", 1),
                    (weight["dedupe_key"], "waiting_reassessment", 1)]
    assert event_count == 2


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


def test_provider_ambiguity_is_contained_without_five_minute_reclaim_or_duplicate_send():
    now = datetime.now(timezone.utc) + timedelta(minutes=4, seconds=42)
    dedupe = "beacon:provider-ambiguity-contained"
    current = candidate("beacon_result:" + "a" * 64, now,
        dedupe_key=dedupe, specialist="BEACON", urgency="due",
        summary="Current protected BEACON proposal requires owner review.",
        next_action="Retain the exact protected card without duplicate delivery.",
        unknowns=["provider_delivery_truth"])
    attempts = []

    def ambiguous(case):
        attempts.append(case["case_id"])
        return {"success": False, "status": "protected_delivery_ambiguous",
            "delivery_confirmed": False, "provider_outcome_ambiguous": True,
            "do_not_retry_provider_effect": True, "telegram_sends": 0}

    store = PostgresManagerCaseStore(connect_factory=connect)
    first = store.run_cycle([current], now=now, source_revision="test",
        refresh=lambda claimed: current, deliver=ambiguous)
    replay = store.run_cycle([current], now=now + timedelta(minutes=5),
        source_revision="test", refresh=lambda claimed: current, deliver=ambiguous)
    later_replay = store.run_cycle([current], now=now + timedelta(days=2),
        source_revision="test", refresh=lambda claimed: current, deliver=ambiguous)
    assert first["exceptions"] == 1
    assert replay["candidate_replays"] == 1
    assert replay["cases_claimed"] == 0
    assert later_replay["cases_claimed"] == 0
    assert len(attempts) == 1
    with connect() as db:
        row = db.execute("""select status,next_reassessment_at,last_delivery_digest,
            evidence_digest from app_private.oom_manager_cases where dedupe_key=%s""",
            (dedupe,)).fetchone()
        event = db.execute("""select event_payload from app_private.oom_manager_case_events
            where case_id=(select case_id from app_private.oom_manager_cases where dedupe_key=%s)
              and event_type='contained' order by occurred_at desc limit 1""",
            (dedupe,)).fetchone()
    assert row[0] == "contained"
    assert row[2] != row[3]
    assert event[0]["provider_ambiguity_contained"] is True


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
