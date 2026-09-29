"""Real isolated PostgreSQL qualification of the retained mortality window.

Provider responses are synthetic; source, canonical readers, claim admission,
family journal, callback executor and manager closure use production code/SQL.
Never accepts a production URL. Missing disposable PostgreSQL is a skip, not proof.
"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Lock, current_thread
from types import SimpleNamespace
import json
import re
import time

import psycopg
from psycopg.types.json import Jsonb
import pytest

from tests.test_oom_sakkie_retained_report_recovery_postgres import (
    URL, store as base_store, add_report, collect,
)
from tests.test_oom_sakkie_herdmaster_retained_recovery_runtime import report
from modules.oom_sakkie import bounded_postgres_read as bounded
from modules.oom_sakkie import family_message_lifecycle as family
from modules.oom_sakkie import general_manager_worker as manager
from modules.oom_sakkie import herdmaster_health_loss_runtime as health
from modules.oom_sakkie import herdmaster_retained_recovery_runtime as retained
from modules.oom_sakkie import herdmaster_source_transaction as source_tx
from modules.oom_sakkie import protected_action_claims as claims
from modules.oom_sakkie import protected_action_runtime as callback
from modules.oom_sakkie import protected_delivery_lifecycle as delivery
from modules.oom_sakkie import protected_payment_recovery as recovery
from modules.oom_sakkie import retained_mortality_history as history
from modules.oom_sakkie import retained_mortality_presentation as presentation
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.pig_weights import pig_welfare_case_runtime as welfare
from modules.sales import sam_live_stock_launch_control as recorder

pytestmark = pytest.mark.skipif(not URL, reason="explicit disposable PostgreSQL URL is required")


class InstrumentedCursor:
    def __init__(self, cursor, rail):
        self.cursor, self.rail = cursor, rail

    def __enter__(self):
        self.cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self.cursor.__exit__(*args)

    def execute(self, query, params=None):
        self.rail.charge("execute", query)
        if self.rail.before:
            self.rail.before(self, query, params)
        result = self.cursor.execute(query, params)
        if self.rail.after:
            self.rail.after(self, query, params)
        return self

    def fetchone(self):
        self.rail.charge("fetch")
        return self.cursor.fetchone()

    def fetchall(self):
        self.rail.charge("fetch")
        return self.cursor.fetchall()

    def __getattr__(self, key):
        return getattr(self.cursor, key)


class InstrumentedConnection:
    def __init__(self, connection, rail):
        self.connection, self.rail = connection, rail

    def __enter__(self):
        self.rail.charge("begin")
        self.connection.__enter__()
        return self

    def __exit__(self, kind, *args):
        self.rail.charge("rollback" if kind else "commit")
        if kind is None and self.rail.before_commit:
            self.rail.before_commit(self)
        return self.connection.__exit__(kind, *args)

    def cursor(self):
        return InstrumentedCursor(self.connection.cursor(), self.rail)

    def execute(self, query, params=None):
        return self.cursor().execute(query, params)

    def rollback(self):
        self.rail.charge("rollback")
        return self.connection.rollback()

    def __getattr__(self, key):
        return getattr(self.connection, key)


class Rail:
    def __init__(self, connect):
        self.raw = connect
        self.token = None
        self.before = self.after = self.before_commit = None
        self.clock = None
        self.costs = {"connect": .08, "begin": .02, "execute": .12,
                      "fetch": .01, "commit": .06, "rollback": .06}
        self.counts, self.statements = Counter(), []
        self.lock = Lock()

    def charge(self, kind, query=None):
        with self.lock:
            self.counts[kind] += 1
            if query is not None:
                self.statements.append(query)
            if self.clock is not None:
                self.clock[0] += self.costs[kind]

    def __call__(self, read_only=False):
        self.charge("connect")
        return InstrumentedConnection(self.raw(read_only), self)

    def row(self, query, params=()):
        with self.raw(True) as db, db.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()

    def claim(self):
        return self.row("select to_jsonb(c) from app_private.oom_protected_action_claims c" +
            (" where callback_token=%s" if self.token else ""),
            (self.token,) if self.token else ())[0]

    def current_source(self):
        return self.row("""select review_json->'herdmaster_health_loss'
            from public.sam_live_stock_conversation_review_events where event_source=%s
            order by created_at desc,review_event_id desc limit 1""", (source_tx.SOURCE,))[0]

    def snapshot(self):
        with self.raw(True) as db, db.cursor() as cur:
            tables = ("app_private.oom_protected_action_claims", "public.operational_events",
                      "public.sam_live_stock_conversation_review_events", "public.pigs",
                      "public.pig_lifecycle_events", "public.pig_welfare_cases",
                      "public.pig_welfare_case_events", "public.pig_active_outlets")
            result = {}
            for table in tables:
                cur.execute("select to_jsonb(t) from " + table + " t order by to_jsonb(t)::text")
                result[table] = cur.fetchall()
            return result


def _canonical_reader_schema(connect):
    """Add real reader dependencies to the existing isolated rail fixture."""
    migrations = Path(__file__).resolve().parents[1] / "supabase/migrations"
    with connect() as db, db.cursor() as cur:
        cur.execute("""alter table public.pigs
            add column animal_type text,add column sex text,add column date_of_birth date,
            add column mother_pig_id text,add column father_pig_id text,add column litter_id text,
            add column purpose text,add column exit_order_id text,add column litter_size_born integer,
            add column litter_size_weaned integer,add column wean_date date,add column wean_weight_kg numeric,
            add column earmarked boolean,add column earmark_date date""")
        cur.execute("""alter table public.litters add column boar_pig_id text,
            add column total_born integer,add column born_alive integer,add column stillborn_count integer,
            add column mummified_count integer,add column male_count integer,add column female_count integer,
            add column unknown_sex_count integer,add column weaned_count integer,add column wean_date date,
            add column litter_notes text""")
        for table, key, kind in (("bulk_weight_batches", "batch_id", "uuid"),
                ("bulk_weight_batch_rows", "row_id", "uuid"), ("orders", "order_id", "text"),
                ("order_lines", "order_line_id", "text")):
            cur.execute(f"create table public.{table}({key} {kind} primary key)")
        for filename, table in (
                ("202606290001_create_farm_canonical_tables.sql", "pens"),
                ("202606290001_create_farm_canonical_tables.sql", "mating_events"),
                ("202606290001_create_farm_canonical_tables.sql", "pig_location_events"),
                ("202608120001_create_breeding_exposure_events.sql", "pig_breeding_exposure_events"),
                ("202605210003_create_sales_transaction_tables.sql", "sales_transactions"),
                ("202605210003_create_sales_transaction_tables.sql", "sales_transaction_items")):
            ddl = (migrations / filename).read_text(encoding="utf-8")
            cur.execute(re.search(r"create table if not exists public\." + table + r"\s*\(.*?\n\);", ddl, re.S)[0])
        cur.execute("alter table public.mating_events add column source_exposure_identity text,add column exposure_group_identity text")
        cur.execute("alter table public.pig_breeding_exposure_events add column exposure_group_identity text")
        cur.execute("alter table public.sales_transactions add column sale_channel text")
        ddl = (migrations / "202607300001_create_litter_supersession_rail.sql").read_text(encoding="utf-8")
        for view in ("current_canonical_pigs", "current_canonical_litters"):
            cur.execute(re.search(r"create or replace view public\." + view + r" as.*?;", ddl, re.S)[0])
        cur.execute("""create view public.current_canonical_pig_state as
            select p.*,null::numeric current_weight_kg,null::date last_weight_date,
                case when p.status='Active' and p.on_farm then coalesce(latest.to_pen_id,p.initial_pen_id) end current_pen_id,
                pen.pen_name current_pen_name
            from public.current_canonical_pigs p left join lateral (select l.to_pen_id from public.pig_location_events l
                where l.pig_id=p.pig_id order by l.move_date desc,l.created_at desc,l.location_event_id desc limit 1) latest on true
            left join public.pens pen on pen.pen_id=coalesce(latest.to_pen_id,p.initial_pen_id)""")
        cur.execute("insert into public.pens(pen_id,pen_name) values('PEN-A','Pen A'),('PEN-B','Pen B')")
        cur.execute("update public.pigs set purpose='Herd',initial_pen_id='PEN-A'")
        cur.execute("insert into public.pig_active_outlets(pig_id,active) values('P27',true)")
        for filename in ("202607200001_create_pig_observation_events.sql",
                         "202608150006_create_protected_payment_recovery_runtime.sql"):
            cur.execute((migrations / filename).read_text(encoding="utf-8"))


@pytest.fixture
def journey(base_store, monkeypatch, request):
    language = getattr(request, "param", "af")
    _canonical_reader_schema(base_store)
    rail = Rail(base_store)
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("PIG_WELFARE_CASE_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_BOT_TOKEN", "synthetic-test-token")
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_OWNER_LANGUAGE", language)
    monkeypatch.setattr(psycopg, "connect", lambda *_a, **_k: rail())
    monkeypatch.setattr(bounded, "connect_bounded_rootline_postgres", lambda **kw: rail(kw.get("read_only", True)))
    monkeypatch.setattr(retained, "connect_bounded_read", lambda: rail(True))
    monkeypatch.setattr(claims, "_connect", rail)
    monkeypatch.setattr(delivery, "_connect", rail)
    monkeypatch.setattr(welfare, "_connect", rail)
    source = report(provider_timestamp="2026-08-20T08:00:00+00:00", output_language=language,
        owner_text_verbatim="Vark nr 27 is dood op 19 Aug 2026. Hy is verwyder en begrawe.")
    from modules.oom_sakkie.herdmaster_health_loss_preview import prepare_health_loss_owner_preview
    material = health.load_canonical_health_loss_evidence()
    evaluated = prepare_health_loss_owner_preview({"gateway_authority": issue_gateway_owner_authority("42", "42"),
        "provider_message_id": "101", "provider_timestamp": source["provider_timestamp"],
        "provider_timezone": "Africa/Johannesburg", "output_language": language,
        "text": source["owner_text_verbatim"]}, material)
    assert evaluated["confirmation_ready"], evaluated
    # Synthetic legacy source clarification with genuine canonical identity.
    # It is inserted once: the actual append-only store is never bypassed.
    question = "Op watter datum is vark 27 dood?"
    source.update(event_phase="preview_generated", owner_text=question, preview={
        "status": "event_date_required", "success": False, "question_count": 1,
        "owner_text": question, "zero_io": True, "evaluator": deepcopy(evaluated["evaluator"]),
        **{key: False for key in ("confirmation_ready", "confirmation_required", "consumes_confirmation",
            "protected_actions_performed", "writes_farm_data", "routes_messages", "sends_telegram")}})
    add_report(base_store, source, datetime.now(timezone.utc) - timedelta(days=1))
    now = datetime.now(timezone.utc) - timedelta(hours=6)
    candidate = manager.normalize_candidate({"dedupe_key": "herdmaster:retained-mortality:101",
        "specialist": "HERDMASTER", "urgency": "critical", "message_family": "retained_protected_recovery",
        "evidence_refs": ["provider_message:101", "pig:P27", "tag:27", retained.retained_report_binding([source])],
        "unknowns": [], "summary": "Retained synthetic mortality confirmation",
        "next_action": "Present exact retained confirmation", "next_reassessment_at": now.isoformat()}, now=now)
    queue = manager.PostgresManagerCaseStore(connect_factory=rail)
    with rail() as db, db.cursor() as cur:
        assert queue._reconcile(cur, candidate, now) == "created"
    candidate.update(generation=1, message_family="retained_protected_recovery")
    prepared = retained.build_retained_protected_preview(candidate)
    assert prepared["status"] == "retained_mortality_prepared_not_presented", prepared
    rail.token = rail.claim()["callback_token"]
    assert all(rail.claim()[key] is None for key in history.EMPTY_MARKERS)
    calls = []
    def provider(_token, method, body):
        calls.append((method, deepcopy(body)))
        assert str(body["chat_id"]) == "42"
        return {"ok": True, "result": {"message_id": int(body.get("message_id") or 701),
            "date": int(datetime.now(timezone.utc).timestamp())}}
    monkeypatch.setattr(recorder, "_telegram_api", provider)
    return SimpleNamespace(rail=rail, case=candidate, queue=queue, source=source, calls=calls)


def present(j, **kwargs):
    return manager.deliver_farm_manager_case(j.case, **kwargs)


def confirmation(j, receipt="702", action="confirm"):
    claim = j.rail.claim()
    parsed = {"telegram_user_id": "42", "telegram_chat_id": "42", "telegram_chat_type": "private",
        "provider_message_id": receipt, "provider_timestamp": datetime.now(timezone.utc).isoformat(),
        "reply_to_message_id": "701", "text": "", "output_language": "af"}
    return callback.handle_protected_action_input(parsed, issue_gateway_owner_authority("42", "42"),
        callback_data=f"oompa:{claim['callback_token']}:{action}", connect_factory=j.rail)


def window_rows(j):
    with j.rail.raw(True) as db, db.cursor() as cur:
        cur.execute("select to_jsonb(e) from public.operational_events e where event_type=%s", (history.WINDOW,))
        return [row[0] for row in cur.fetchall()]


def cancel_source(j, *, supersede=False, connect_factory=None, current=None):
    current = current or j.rail.current_source()
    changed = {**current, "status": "contained", "event_phase": "preview_declined",
               "provider_message_id": "CANCEL-703"}
    if supersede:
        changed.update(mission_id="SYNTHETIC-SUCCESSOR", status="waiting_for_input",
                       superseded_duplicate_missions=[current["mission_id"]])
    return health._record_lifecycle_event(changed,
        expected_sources={current["mission_id"]: source_tx.digest(current)},
        connect_factory=connect_factory or j.rail)


def test_atomic_window_delivery_confirmation_and_same_case_closure(journey):
    j = journey
    before = j.rail.claim()
    # Preparation expiry is not an attempted/presented decision expiry.
    with j.rail.raw() as db, db.cursor() as cur:
        cur.execute("update app_private.oom_protected_action_claims set expires_at=created_at+interval '1 microsecond',status='expired'")
    result = present(j)
    assert result["success"] and result["delivery_confirmed"], result
    after, audits = j.rail.claim(), window_rows(j)
    assert len(audits) == 1 and after["callback_token"] == before["callback_token"]
    assert history._time(after["expires_at"]) - history._time(after["delivery_attempted_at"]) == timedelta(minutes=30)
    assert after["preview_payload"] == before["preview_payload"]
    assert after["delivery_state"] == "delivery_confirmed" and after["preview_card_message_id"] == "701"
    assert j.rail.row("select status,on_farm from public.pigs where pig_id='P27'") == ("Active", True)
    first_attempt = after["delivery_attempt_id"]
    replay = present(j)
    assert replay["telegram_sends"] == 0 and len(j.calls) == 1
    assert j.rail.claim() == after and window_rows(j) == audits
    done, status = confirmation(j)
    assert status == 201 and done["success"] and done["rows_created"] == 1, done
    assert j.rail.row("select status,on_farm from public.pigs where pig_id='P27'") == ("Dead", False)
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (1,)
    assert j.rail.claim()["status"] == "completed"
    assert j.rail.current_source()["status"] == "completed"
    assert j.rail.claim()["delivery_attempt_id"] == first_attempt
    repeated, replay_status = confirmation(j)
    assert replay_status == 200 and repeated["success"], repeated
    assert repeated["writes_farm_data"] is False
    terminal = collect(j.rail.raw, now=datetime.now(timezone.utc), claimed_cases=[j.case])
    assert len(terminal) == 1 and terminal[0]["terminal_state"] == "completed", terminal
    closed = manager.normalize_candidate(terminal[0], now=datetime.now(timezone.utc))
    with j.rail() as db, db.cursor() as cur:
        assert j.queue._reconcile(cur, closed, datetime.now(timezone.utc)) == "changed"
        assert j.queue._reconcile(cur, closed, datetime.now(timezone.utc)) == "replayed"
    assert j.rail.row("select case_id,status from app_private.oom_manager_cases") == (j.case["case_id"], "completed")
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (1,)
    assert len(window_rows(j)) == len(j.calls) == 1


def seed_legacy_history(j):
    """Entirely synthetic renewal, correction, extension and old question rows.

    Setup reconstructs history before the tested operation. Runtime never edits
    these records; the test later compares every pre-existing row byte-for-byte.
    """
    c, source = j.rail.claim(), j.rail.current_source()
    base = datetime.now(timezone.utc) - timedelta(hours=3)
    at = lambda minutes: (base + timedelta(minutes=minutes)).isoformat()
    h = history._sha(c["callback_token"])
    common = {"case_id": j.case["case_id"], "generation": 1,
        "evidence_digest": j.case["evidence_digest"], "plan_sha256": "d" * 64,
        "preimage_sha256": "e" * 64, "prevention_revision": "1" * 40,
        "prevention_tree": "2" * 40, "deployed_revision": "3" * 40,
        "authority_reference": "SYNTHETIC-HISTORICAL-APPROVAL", "scheduler_triggers": 0}
    def audit(kind, minute, event_id, key, system, cause, payload):
        return {"event_id": event_id, "idempotency_key": key, "schema_version": "1",
            "event_type": kind, "domain": "approvals", "aggregate_type": "protected_action_claim",
            "aggregate_id": h, "source_system": system, "source_record_id": j.case["case_id"],
            "authority_tier": "owner_approved", "privacy_class": "owner_private",
            "actor_type": "system", "actor_id": "synthetic-maintainer", "correlation_id": c["mission_id"],
            "causation_id": cause, "occurred_at": at(minute), "recorded_at": at(minute),
            "freshness_at": at(minute), "provenance_json": {"source_ref": "sha256:" + "e" * 64},
            "payload_json": {"claim_hash": h, "preview_digest": c["preview_digest"],
                "one_time_only": True, "provider_attempts": 0, "farm_writes": 0,
                "new_expires_at": at(minute + 30), **payload}}
    renewal = audit(history.RENEWAL, 0, "OOM-RETAINED-RENEWAL-" + h[:32].upper(),
        "retained-preview-renewal:" + h + ":" + at(-60), "oom_sakkie", "SYNTHETIC-OLD-CYCLE", {
            "contract_version": "retained_preview_renewal_v1", "old_expires_at": at(-60),
            "mission_id": c["mission_id"], "evidence_generation": c["evidence_generation"],
            "source_binding": source["retained_repreview"]["source_binding"],
            "old_status": "active", "new_status": "active", "old_delivery_state": "claim_created",
            "new_delivery_state": "claim_created"})
    correction = audit(history.CORRECTION, 60, "OOM-PRESEND-CORRECTION-" + h[:32].upper(),
        "oom-presend-timeout-correction:" + h, "manual_presend_timeout_correction", "SYNTHETIC-OLD-CYCLE", {
            **common, "contract_version": "oom_presend_timeout_correction.v1",
            "original_renewal": {k: deepcopy(renewal[k]) for k in
                ("event_id", "event_type", "idempotency_key", "payload_json", "occurred_at")},
            "archived_claim_markers": {"status": "active", "delivery_state": "delivery_ambiguous",
                "expires_at": at(30), "delivery_attempt_id": history._sha("oom_protected_delivery.v1|" +
                    c["callback_token"] + "|" + c["preview_digest"]),
                "delivery_attempted_at": at(2), "delivery_ambiguous_at": at(3),
                "delivery_result": {"success": False, "status": "family_message_cycle_deadline_deferred",
                    "telegram_message_id": None, "telegram_sends": 0, "telegram_edits": 0}}})
    extension = audit(history.EXTENSION, 120, "OOM-UNSENT-EXTENSION-" + h[:32].upper(),
        "oom-unsent-confirmation-extension:" + h, "manual_unsent_confirmation_extension", correction["event_id"], {
            **common, "contract_version": "oom_unsent_confirmation_extension.v1",
            "old_expires_at": at(90), "original_correction_event_id": correction["event_id"],
            "original_correction_plan_sha256": common["plan_sha256"], "owner_user_id": c["owner_user_id"],
            "original_renewal_consumed": True, "metadata_writes": 2, "ttl_seconds": 1800})
    question = "Op watter datum is vark 27 dood?"
    shared = {"mission_id": j.source["mission_id"], "card_mission_id": j.source["mission_id"],
        "owner_user_id": "42", "chat_id": "42", "provider_message_id": "101",
        "provider_timestamp": j.source["provider_timestamp"], "specialist_identity": "HERDMASTER",
        "task_state": "waiting_for_input", "semantic_domain": "herd_health", "semantic_intent": "mortality_report",
        "semantic_continuation": False, "read_query": {}, "clarification_question": question,
        "text_sha256": history._sha(question),
        "inbound_text_sha256": history._sha(" ".join(j.source["owner_text_verbatim"].split()))}
    with j.rail.raw() as db, db.cursor() as cur:
        cur.execute("update app_private.oom_protected_action_claims set created_at=%s,expires_at=%s,status='expired'",
                    (at(-90), at(150)))
        for state, minute, suffix in (("delivery_attempted", -100, "-DELIVERY-ATTEMPT"),
                                     ("delivered", -99, "-DELIVERED")):
            event_id = j.source["mission_id"] + suffix
            record = {**shared, "event_id": event_id, "state": state}
            if state == "delivered":
                record.update(telegram_message_id="600", delivery_provider_timestamp=at(minute))
            cur.execute("""insert into public.sam_live_stock_conversation_review_events
                (review_event_id,event_source,chatwoot_conversation_id,review_json,created_at)
                values(%s,'oom_sakkie_family_message_lifecycle',%s,%s,%s)""",
                (event_id, j.source["mission_id"], Jsonb({"family_message_lifecycle": record}), at(minute)))
        for row in (renewal, correction, extension):
            cur.execute("insert into public.operational_events(" + ",".join(row) + ") values(" +
                        ",".join(["%s"] * len(row)) + ")",
                        tuple(Jsonb(v) if isinstance(v, dict) else v for v in row.values()))
        cur.execute("""insert into app_private.oom_manager_worker_cycles
            (cycle_id,worker_id,trigger_identity,source_revision,started_at,heartbeat_at,next_cycle_at,status)
            values('SYNTHETIC-OLD-CYCLE','synthetic','synthetic',%s,%s,%s,%s,'completed')""",
            ("4" * 40, at(1), at(4), at(6)))
        j.queue._event(cur, j.case, "contained", history._time(at(4)), cycle_id="SYNTHETIC-OLD-CYCLE",
            outcome_status="protected_delivery_ambiguous", failure_kind="", provider_ambiguity_contained=True)
        payload = {"case_id": j.case["case_id"], "generation": 1, "event_type": "reassessment_scheduled",
            "occurred_at": at(60), "outcome_status": "proven_presend_timeout_classification_corrected",
            "correction_audit_event_id": correction["event_id"], "plan_sha256": common["plan_sha256"]}
        cur.execute("""insert into app_private.oom_manager_case_events
            (event_id,case_id,generation,event_type,event_payload,occurred_at) values(%s,%s,1,%s,%s,%s)""",
            (correction["event_id"] + "-REASSESS", j.case["case_id"], "reassessment_scheduled", Jsonb(payload), at(60)))
        # Complete history intentionally exceeds the old 128-row sampling bound.
        for i in range(140):
            j.queue._event(cur, j.case, "exception", history._time(at(151)) + timedelta(seconds=i),
                cycle_id="SYNTHETIC-RETRY-" + str(i), outcome_status=history.RENEWAL_CONSUMED,
                failure_kind=history.RENEWAL_CONSUMED, provider_ambiguity_contained=False,
                deadline_phase="", processing_timings_ms={"dispatch_wait": 7021, "refresh_and_delivery": 8655})


def test_expired_corrected_legacy_claim_starts_one_window_preserving_all_history(journey):
    j = journey
    seed_legacy_history(j)
    before, claim = j.rail.snapshot(), j.rail.claim()
    result = present(j)
    assert result["delivery_confirmed"], result
    after = j.rail.snapshot()
    for table in ("public.operational_events", "public.sam_live_stock_conversation_review_events"):
        assert all(row in after[table] for row in before[table]), table
    assert len(after["public.operational_events"]) == len(before["public.operational_events"]) + 1
    assert j.rail.claim()["callback_token"] == claim["callback_token"]
    assert j.rail.claim()["preview_payload"] == claim["preview_payload"]
    assert len(j.calls) == len(window_rows(j)) == 1
    assert not present(j).get("delivery_confirmed") and len(j.calls) == 1


@pytest.mark.parametrize("relation", ["foreign_provider", "same_principal", "same_mission_foreign_principal"])
def test_related_claim_sql_scopes_provider_collisions_but_never_ignores_mission(journey, relation):
    j = journey
    c = j.rail.claim()
    other = deepcopy(c)
    other.update(callback_token="SYNTHETIC-OTHER-CLAIM", preview_digest="9" * 64,
                 mission_id="SYNTHETIC-OTHER-MISSION", owner_user_id="900", private_chat_id="900")
    if relation == "same_principal":
        other.update(owner_user_id="42", private_chat_id="42")
    elif relation == "same_mission_foreign_principal":
        other.update(mission_id=c["mission_id"], status="expired")
    with j.rail.raw() as db, db.cursor() as cur:
        cur.execute("""insert into app_private.oom_protected_action_claims
            select * from jsonb_populate_record(null::app_private.oom_protected_action_claims,%s)""", (Jsonb(other),))
    before = j.rail.claim()
    result = present(j)
    if relation == "foreign_provider":
        assert result["delivery_confirmed"] and len(j.calls) == 1, result
    else:
        assert not result["success"] and not j.calls and not window_rows(j), result
        assert j.rail.claim() == before


@pytest.mark.parametrize("write", ["audit", "claim"])
def test_failure_after_either_admission_write_rolls_back_everything(journey, write):
    j = journey
    before = j.rail.snapshot()
    seen = []
    def fail(_cur, query, _params):
        marker = "insert into public.operational_events" if write == "audit" else "update app_private.oom_protected_action_claims c set status='active',expires_at"
        if marker in query:
            seen.append(write)
            raise RuntimeError("synthetic failure after actual " + write)
    j.rail.after = fail
    outcome = present(j)
    j.rail.after = None
    assert seen == [write] and not outcome["success"]
    assert j.rail.snapshot() == before and j.calls == []


def test_two_workers_commit_one_window_and_provider_attempt(journey):
    j = journey
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: present(j), range(2)))
    assert sum(result.get("delivery_confirmed") is True for result in results) == 1, results
    assert len(j.calls) == len(window_rows(j)) == 1
    assert j.rail.claim()["delivery_state"] == "delivery_confirmed"


@pytest.mark.parametrize("change", ["cancel", "supersede", "material", "recipient"])
def test_staged_card_cannot_bypass_fresh_admission(journey, monkeypatch, change):
    j = journey
    staged = retained.build_retained_protected_preview(j.case)
    before = j.rail.claim()
    if change in {"cancel", "supersede"}:
        assert cancel_source(j, supersede=change == "supersede")["success"]
    elif change == "material":
        with j.rail.raw() as db, db.cursor() as cur:
            cur.execute("update public.pigs set initial_pen_id='PEN-B' where pig_id='P27'")
    else:
        monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "900")
    parsed = retained._delivery_context(j.source)
    outcome = family.deliver_family_result(parsed, staged, specialist="HERDMASTER",
        mission_id=staged["mission_id"], card_mission_id=staged["card_mission_id"])
    assert not outcome["success"], outcome
    assert j.rail.claim() == before and not window_rows(j) and not j.calls


def test_real_source_lock_timeout_rolls_back_and_next_manager_cycle_sends(journey):
    j = journey
    before = j.rail.snapshot()
    # Actual PostgreSQL timeout, no raised mock error. The lock is held by a
    # separate transaction and the short test timeout replaces only the wait.
    with j.rail.raw() as locker, locker.cursor() as cur:
        source_tx.lock_sources(cur, "42", "42", [j.source["mission_id"]])
        def short_timeout(cursor, query, _params):
            if query == "set local lock_timeout='5000ms'":
                cursor.cursor.execute("set local lock_timeout='50ms'")
        j.rail.after = short_timeout
        outcome = present(j)
        j.rail.after = None
    assert outcome["status"] == "retained_mortality_presend_statement_deferred", outcome
    assert j.rail.snapshot() == before and not j.calls
    at = datetime.now(timezone.utc)
    with j.rail() as db, db.cursor() as cur:
        j.queue._event(cur, j.case, "exception", at, cycle_id="SYNTHETIC-LOCK-CYCLE",
            outcome_status=outcome["status"], failure_kind=outcome["failure_kind"],
            provider_ambiguity_contained=False,
            deadline_phase="", processing_timings_ms={"dispatch_wait": 0, "refresh_and_delivery": 0})
    result = j.queue.run_cycle([j.case], now=at, source_revision="synthetic-test", deadline_monotonic=time.monotonic()+80,
        refresh_batch=lambda cases: {c["case_id"]: j.case for c in cases}, deliver=manager.deliver_farm_manager_case)
    assert result["success"] and result["deliveries_confirmed"] == 1, result
    assert len(window_rows(j)) == len(j.calls) == 1


@pytest.mark.parametrize("failure", ["restart_pending", "ambiguous_provider", "expired_after_attempt"])
def test_admitted_attempt_is_never_renewed_or_resent(journey, monkeypatch, failure):
    j = journey
    if failure == "restart_pending":
        staged = retained.build_retained_protected_preview(j.case)
        c = j.rail.claim()
        admitted = delivery._claim_delivery(callback_token=c["callback_token"], preview_digest=c["preview_digest"],
            owner_user_id="42", private_chat_id="42", action_kind="mortality", factory=j.rail,
            start_attempt=True, deadline_monotonic=None, presentation_policy=staged["_retained_mortality_policy"])
        assert admitted["attempt_owned"]
    else:
        if failure == "ambiguous_provider":
            def uncertain(*args):
                j.calls.append(("uncertain", {}))
                raise TimeoutError("synthetic provider response lost")
            monkeypatch.setattr(recorder, "_telegram_api", uncertain)
        present(j)
        if failure == "expired_after_attempt":
            with j.rail.raw() as db, db.cursor() as cur:
                cur.execute("update app_private.oom_protected_action_claims set expires_at=clock_timestamp()-interval '1 second'")
    before, audits, calls_before = j.rail.claim(), window_rows(j), len(j.calls)
    for _ in range(2):
        outcome = present(j)
        assert outcome.get("delivery_confirmed") is not True
    assert j.rail.claim()["expires_at"] == before["expires_at"]
    assert j.rail.claim()["delivery_attempt_id"] == before["delivery_attempt_id"]
    assert window_rows(j) == audits and len(j.calls) == calls_before


@pytest.mark.parametrize("changed", ["cancel", "canonical"])
def test_confirmation_revalidates_source_and_material_before_farm_write(journey, changed):
    j = journey
    assert present(j)["delivery_confirmed"]
    if changed == "cancel":
        assert cancel_source(j)["success"]
    else:
        with j.rail.raw() as db, db.cursor() as cur:
            cur.execute("update public.pigs set initial_pen_id='PEN-B' where pig_id='P27'")
    result, status = confirmation(j)
    assert status >= 400 and not result["success"], result
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (0,)
    assert j.rail.row("select status,on_farm from public.pigs where pig_id='P27'") == ("Active", True)


@pytest.mark.parametrize("failure", ["source_completion", "domain_returned_false", "claim_completion"])
def test_confirmation_partial_failure_rolls_back_or_recovers_same_receipt(journey, monkeypatch, failure):
    from modules.pig_weights import herdmaster_health_loss_recording as domain
    j = journey
    assert present(j)["delivery_confirmed"]
    before = j.rail.snapshot()
    with monkeypatch.context() as patch:
        if failure == "source_completion":
            original = health._record_lifecycle_event
            def fail(lifecycle, **kwargs):
                if lifecycle["status"] == "completed":
                    raise RuntimeError("synthetic source completion failure")
                return original(lifecycle, **kwargs)
            patch.setattr(health, "_record_lifecycle_event", fail)
        elif failure == "domain_returned_false":
            original = domain.confirm_health_loss_preview
            def fail(*args, **kwargs):
                result, status = original(*args, **kwargs)
                assert result["success"] and status == 201
                return {"success": False, "status": "synthetic_after_domain_write"}, 503
            patch.setattr(domain, "confirm_health_loss_preview", fail)
        else:
            patch.setattr(claims, "complete_claim", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("synthetic completion receipt failure")))
        result, status = confirmation(j)
        assert status == 503 and not result["success"], result
    assert j.rail.claim()["status"] == "executing"
    current = j.rail.snapshot()
    for table in before:
        if table != "app_private.oom_protected_action_claims":
            assert current[table] == before[table], table
    result, status = confirmation(j)
    assert status in {200, 201} and result["success"], result
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (1,)
    assert j.rail.claim()["status"] == "completed"
    assert j.rail.current_source()["status"] == "completed"


@pytest.mark.parametrize("boundary", ["admission", "confirmation"])
def test_source_cancellation_commits_before_waited_gate_and_prevents_effect(journey, boundary):
    j = journey
    if boundary == "confirmation":
        assert present(j)["delivery_confirmed"]
    original = j.rail.current_source()
    reached_lock = Event()
    def before(_cursor, query, params):
        if "pg_advisory_xact_lock" in query and str(params[0]).startswith("herdmaster-health-source:"):
            reached_lock.set()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with j.rail.raw() as locker, locker.cursor() as cur:
            source_tx.lock_sources(cur, "42", "42", [j.source["mission_id"]])
            j.rail.before = before
            pending = pool.submit(present if boundary == "admission" else confirmation, j)
            assert reached_lock.wait(3), "contending runtime never reached source fence"
            saved = cancel_source(j, current=original, connect_factory=source_tx.TransactionReader(locker))
            assert saved["success"]
        result = pending.result(timeout=5)
    j.rail.before = None
    outcome = result if boundary == "admission" else result[0]
    assert not outcome["success"], result
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (0,)
    assert j.rail.current_source()["status"] == "contained"
    if boundary == "admission":
        assert not window_rows(j) and not j.calls
        assert all(j.rail.claim()[key] is None for key in history.EMPTY_MARKERS)


@pytest.mark.parametrize("boundary", ["admission", "confirmation"])
def test_source_fence_serializes_later_cancellation_after_winning_gate(journey, monkeypatch, boundary):
    from modules.oom_sakkie import retained_mortality_confirmation as coordinator
    j = journey
    if boundary == "confirmation":
        assert present(j)["delivery_confirmed"]
    held, release, cancellation_waits = Event(), Event(), Event()
    module = presentation if boundary == "admission" else coordinator
    validate = module.validate_material
    def gated(*args):
        result = validate(*args)  # actual four-reader evidence and material proof
        held.set()
        assert release.wait(3)
        return result
    monkeypatch.setattr(module, "validate_material", gated)
    def before(_cursor, query, params):
        if (current_thread().name.endswith("_1") and "pg_advisory_xact_lock" in query
                and str(params[0]).startswith("herdmaster-health-source:")):
            cancellation_waits.set()
    j.rail.before = before
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="source-race") as pool:
        winner = pool.submit(present if boundary == "admission" else confirmation, j)
        assert held.wait(3)
        cancellation = pool.submit(cancel_source, j)
        assert cancellation_waits.wait(3), "cancellation did not wait behind common source fence"
        release.set()
        result = winner.result(timeout=5)
        if boundary == "confirmation":
            cancelled = cancellation.result(timeout=5)
            assert cancelled == {"success": False, "status": "health_source_append_conflict_or_unavailable"}
        else:
            assert cancellation.result(timeout=5)["success"]
    j.rail.before = None
    if boundary == "confirmation":
        assert result[0]["success"] and result[1] == 201, result
        assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (1,)
        assert j.rail.current_source()["status"] == "completed"
    else:
        assert result["delivery_confirmed"] and len(window_rows(j)) == len(j.calls) == 1, result
        refused, status = confirmation(j)
        assert status == 409 and not refused["success"]
        assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (0,)


@pytest.mark.parametrize("failure", ["query_timeout", "cas_mismatch", "post_write_deadline"])
def test_actual_admission_transaction_refuses_partial_window(journey, monkeypatch, failure):
    j = journey
    original = j.rail.snapshot()
    clock, observed = [0.0], []
    monkeypatch.setattr(presentation, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    def after(cursor, query, _params):
        if "insert into public.operational_events" in query:
            observed.append("audit")
            if failure == "query_timeout":
                cursor.cursor.execute("set local statement_timeout='20ms'")
                cursor.cursor.execute("select pg_sleep(0.1)")
            elif failure == "cas_mismatch":
                cursor.cursor.execute("update app_private.oom_protected_action_claims set expires_at=expires_at+interval '1 second'")
        if "update app_private.oom_protected_action_claims c set status='active',expires_at" in query:
            observed.append("cas")
            if failure == "post_write_deadline":
                clock[0] = 50.0
    j.rail.after = after
    # Stage before passing the synthetic absolute deadline to the actual gate;
    # the manager itself uses its unrelated real clock in this focused test.
    staged = retained.build_retained_protected_preview(j.case)
    c = j.rail.claim()
    outcome = delivery._claim_delivery(callback_token=c["callback_token"], preview_digest=c["preview_digest"],
        owner_user_id="42", private_chat_id="42", action_kind="mortality", factory=j.rail,
        start_attempt=True, deadline_monotonic=80.0, presentation_policy=staged["_retained_mortality_policy"])
    j.rail.after = None
    assert not outcome["success"] and observed[0] == "audit", outcome
    if failure == "query_timeout":
        assert outcome["status"] == "retained_mortality_presend_statement_deferred"
    assert j.rail.snapshot() == original and not j.calls


def test_duplicate_confirmation_receipts_complete_one_canonical_operation(journey):
    j = journey
    assert present(j)["delivery_confirmed"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: confirmation(j), range(2)))
    assert all(body["success"] and status in {200, 201} for body, status in results), results
    assert sum(body.get("rows_created", 0) for body, _status in results) == 1, results
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (1,)
    assert j.rail.claim()["status"] == j.rail.current_source()["status"] == "completed"


@pytest.mark.parametrize("slow", [False, True])
def test_317_case_real_positive_gate_charges_every_command_connection_and_commit(journey, monkeypatch, slow):
    j = journey
    seed_legacy_history(j)
    now = datetime.now(timezone.utc)
    values = [manager.normalize_candidate({"dedupe_key": "sam:window-budget:" + str(i),
        "specialist": "SAM", "urgency": "due", "evidence_refs": ["synthetic-budget:" + str(i)],
        "summary": "Synthetic stable candidate", "next_action": "Reassess unchanged evidence",
        "next_reassessment_at": (now if i < 4 else now + timedelta(days=1)).isoformat()}, now=now)
        for i in range(316)]
    absent = set(range(10, 42))
    with j.rail() as db, db.cursor() as cur:
        for i, value in enumerate(values):
            if i not in absent:
                assert j.queue._reconcile(cur, value, now) == "created"
    values = [{**v, **({"terminal_state": "completed"} if i in absent else {})}
              for i, v in enumerate(values)] + [j.case]
    by_key = {v["dedupe_key"]: v for v in values}
    clock = [15.021]  # observed collection aggregate, charged once explicitly
    j.rail.clock = clock
    j.rail.counts.clear()
    j.rail.statements.clear()
    timer = SimpleNamespace(monotonic=lambda: clock[0])
    for module in (manager, presentation, family, retained):
        monkeypatch.setattr(module, "time", timer)
    provider_times, provider_counts, outcomes, queue_lookups = [], [], [], []
    material_loads = []
    load_material = health.load_canonical_health_loss_evidence
    def material(**kwargs):
        material_loads.append(True)
        return load_material(**kwargs)
    monkeypatch.setattr(health, "load_canonical_health_loss_evidence", material)
    api = recorder._telegram_api
    def provider(*args):
        assert family._provider_deadline_available(80.0)
        assert len(window_rows(j)) == 1
        assert j.rail.row("""select count(*) from public.sam_live_stock_conversation_review_events
            where review_json->'family_message_lifecycle'->>'state'='delivery_attempted'
              and review_json->'family_message_lifecycle'->>'card_mission_id'=%s""",
            (claims.protected_card_mission_id(j.rail.claim()["mission_id"], j.rail.claim()["preview_digest"]),)) == (1,)
        provider_times.append(clock[0])
        provider_counts.append(dict(j.rail.counts))
        return api(*args)
    monkeypatch.setattr(recorder, "_telegram_api", provider)
    def before(_cursor, query, _params):
        if "for update of m skip locked limit" in " ".join(query.split()):
            queue_lookups.append(sum("select dedupe_key,evidence_digest,generation,status" in q
                                     for q in j.rail.statements))
    j.rail.before = before
    def refresh(cases):
        clock[0] += 7.021  # aggregate fresh ownership discovery cost
        return {case["case_id"]: by_key[case["dedupe_key"]] for case in cases}
    def deliver(case, **kwargs):
        if case["case_id"] != j.case["case_id"]:
            return {"success": True, "status": "non_farm_case_delivery_suppressed",
                    "delivery_confirmed": False, "telegram_sends": 0}
        # Conservative synthetic non-SQL preparation cost; every real SQL/control,
        # readback, connection and commit is additionally charged by Rail.
        clock[0] += 15.475 + (15 if slow else 0)
        outcome = manager.deliver_farm_manager_case(case, **kwargs)
        outcomes.append(outcome)
        return outcome
    result = j.queue.run_cycle(values, now=now, source_revision="4" * 40,
        source_collection_ms=15021, deadline_monotonic=80.0, refresh_batch=refresh, deliver=deliver)
    counts, statements, elapsed = dict(j.rail.counts), list(j.rail.statements), clock[0]
    j.rail.clock = j.rail.before = None
    print("PRESENTATION_BUDGET " + json.dumps({"slow_control": slow, "elapsed_seconds": round(elapsed, 3),
        "provider_gate_seconds": provider_times, "command_counts": counts,
        "charged_seconds_per_operation": j.rail.costs, "collection_seconds": 15.021,
        "refresh_seconds": 7.021, "preparation_seconds": 15.475 + (15 if slow else 0)}, sort_keys=True))
    assert result["candidate_replays"] == 317, result
    assert result["cases_claimed"] == 5 and queue_lookups == [2], result
    assert counts["connect"] >= 5 and counts["commit"] >= 5 and counts["execute"] > 20
    assert elapsed < 80
    assert j.rail.row("select count(*) from app_private.oom_manager_cases") == (285,)
    if slow:
        assert result["success"] is False
        assert material_loads == []
        assert not j.calls and not window_rows(j) and not provider_times
        assert result["deliveries_confirmed"] == 0 and result["deadline_deferrals"] >= 1, result
        assert all(j.rail.claim()[key] is None for key in history.EMPTY_MARKERS)
    else:
        assert result["success"] is True, result
        assert material_loads == [True], "preparation must not duplicate the authoritative canonical rebuild"
        assert result["deliveries_confirmed"] == 1 and outcomes[0]["protected_preview_card_bound"], result
        assert len(provider_times) == len(window_rows(j)) == 1 and provider_times[0] < 50
        # Admission commit and the family attempt journal both precede provider.
        assert provider_counts[0]["commit"] >= 5
        assert any("set transaction isolation level read committed" in q for q in statements)
        claim = j.rail.claim()
        assert history._time(claim["expires_at"]) - history._time(claim["delivery_attempted_at"]) == timedelta(minutes=30)
        assert claim["delivery_state"] == "delivery_confirmed"


@pytest.mark.parametrize("cost_boundary", ["admission_commit", "family_journal"])
def test_reserve_lost_after_admission_never_sends_or_restarts_window(journey, monkeypatch, cost_boundary):
    j = journey
    clock, admission_written = [0.0], [False]
    for module in (manager, presentation, family, retained):
        monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    def after(_cursor, query, params):
        if "update app_private.oom_protected_action_claims c set status='active',expires_at" in query:
            admission_written[0] = True
        if (cost_boundary == "family_journal" and "insert into" in query
                and "sam_live_stock_conversation_review_events" in query
                and "delivery_attempted" in str(params)):
            clock[0] = 51.0
    def commit(_connection):
        if cost_boundary == "admission_commit" and admission_written[0]:
            clock[0] = 51.0
    j.rail.after, j.rail.before_commit = after, commit
    outcome = present(j, deadline_monotonic=80.0)
    j.rail.after = j.rail.before_commit = None
    before, audits = j.rail.claim(), window_rows(j)
    assert admission_written[0] and len(audits) == 1 and not j.calls and not outcome["success"], outcome
    assert before["delivery_attempt_id"] and before["delivery_state"] != "delivery_confirmed"
    clock[0] = 0
    assert not present(j, deadline_monotonic=80.0).get("delivery_confirmed")
    assert j.rail.claim()["expires_at"] == before["expires_at"] and window_rows(j) == audits and not j.calls


@pytest.mark.parametrize("winner_action", ["confirm", "cancel"])
def test_genuine_callback_cancel_and_confirmation_are_first_receipt_wins(journey, winner_action):
    j = journey
    assert present(j)["delivery_confirmed"]
    held, release, waits = Event(), Event(), Event()
    def after(_cursor, query, _params):
        if (current_thread().name.endswith("_0")
                and query.startswith("update app_private.oom_protected_action_claims set status=")
                and "confirmation_provider_message_id" in query):
            held.set()
            assert release.wait(3)
    def before(_cursor, query, _params):
        if (current_thread().name.endswith("_1") and query.startswith("select action_kind,")
                and "for update" in query):
            waits.set()
    j.rail.before, j.rail.after = before, after
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="callback-race") as pool:
        winner = pool.submit(confirmation, j, "702", winner_action)
        assert held.wait(3)
        loser = pool.submit(confirmation, j, "703", "cancel" if winner_action == "confirm" else "confirm")
        assert waits.wait(3)
        release.set()
        first, second = winner.result(timeout=5), loser.result(timeout=5)
    j.rail.before = j.rail.after = None
    if winner_action == "confirm":
        assert first[0]["success"] and first[1] == 201, first
        assert second[1] == 409 and second[0]["status"] == "protected_callback_stale", second
        assert j.rail.claim()["status"] == "completed"
        assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (1,)
    else:
        assert first[0]["status"] == second[0]["status"] == "protected_preview_cancelled"
        assert j.rail.claim()["status"] == "cancelled"
        assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (0,)
        assert j.rail.current_source()["status"] == "preview_ready"
    assert j.rail.claim()["confirmation_provider_message_id"] == "702"
    assert not present(j).get("delivery_confirmed") and len(j.calls) == len(window_rows(j)) == 1


@pytest.mark.parametrize("unsafe", ["unknown_failure", "history_overflow"])
def test_actual_complete_history_query_refuses_unknown_or_overflowed_history(journey, unsafe):
    j = journey
    at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with j.rail.raw() as db, db.cursor() as cur:
        if unsafe == "unknown_failure":
            j.queue._event(cur, j.case, "exception", at, cycle_id="SYNTHETIC-UNKNOWN-CYCLE",
                outcome_status="provider_timeout", failure_kind="provider_timeout", provider_ambiguity_contained=False)
        else:
            payload = {"case_id": j.case["case_id"], "generation": 1, "event_type": "exception",
                "occurred_at": at.isoformat(), "cycle_id": "SYNTHETIC-OVERFLOW-CYCLE",
                "outcome_status": "manager_cycle_deadline_deferred", "failure_kind": "manager_cycle_deadline_deferred",
                "provider_ambiguity_contained": False}
            cur.execute("""insert into app_private.oom_manager_case_events
                (event_id,case_id,generation,event_type,event_payload,occurred_at)
                select 'SYNTHETIC-OVERFLOW-'||n,%s,1,'exception',%s,%s from generate_series(1,4096) n""",
                (j.case["case_id"], Jsonb(payload), at))
    before = j.rail.snapshot()
    outcome = present(j)
    assert not outcome["success"] and not j.calls and not window_rows(j), outcome
    assert j.rail.snapshot() == before


def scheduled_completion(j, *, now=None, deliverer=None):
    def no_executor(*_args, **_kwargs):
        pytest.fail("completed-mortality delivery recovery must not invoke a farm executor")
    kwargs = {"now": now or datetime.now(timezone.utc), "connect_factory": j.rail, "executor": no_executor}
    if deliverer is not None:
        kwargs["deliverer"] = deliverer
    return recovery.run_payment_recovery_cycle(**kwargs)


@pytest.mark.parametrize("interruption", ["none", "abandoned_lease", "exception_pending", "delivery_pending"])
def test_completed_callback_commit_is_recovered_by_actual_scheduler_without_new_farm_write(journey, monkeypatch, interruption):
    j = journey
    assert present(j)["delivery_confirmed"]
    done, code = confirmation(j)
    assert done["success"] and code == 201
    # Exercise canonical scheduled readback directly too, so an unexpected
    # lower-layer failure is visible rather than hidden in worker containment.
    committed = j.rail.claim()
    assert recovery._verify_retained_completion(committed, committed["result_payload"], j.rail) is None
    before = j.rail.snapshot()
    now = datetime.now(timezone.utc)
    if interruption == "abandoned_lease":
        store = recovery._RecoveryStore(j.rail)
        store.start_cycle("SYNTHETIC-ABANDONED", now, now + timedelta(minutes=5))
        acquired = store.acquire("SYNTHETIC-ABANDONED", now)
        assert acquired["callback_token"] == j.rail.token and acquired["status"] == "completed"
        assert scheduled_completion(j, now=now)["status"] == "payment_recovery_idle"
        now += timedelta(seconds=recovery.LEASE_SECONDS + 1)
    elif interruption == "exception_pending":
        def unavailable(*_args, **_kwargs):
            raise ConnectionError("synthetic interruption before completion presentation")
        failed = scheduled_completion(j, now=now, deliverer=unavailable)
        assert failed["status"] == "payment_recovery_pending" and not failed["success"]
        assert len(j.calls) == 1
        now += timedelta(seconds=recovery.INTERVAL_SECONDS + 1)
    elif interruption == "delivery_pending":
        def ambiguous(_token, method, body):
            assert method == "editMessageText"
            j.calls.append((method, deepcopy(body)))
            raise TimeoutError("synthetic completion edit reply lost")
        with monkeypatch.context() as patch:
            patch.setattr(recorder, "_telegram_api", ambiguous)
            failed = scheduled_completion(j, now=now)
        assert failed["status"] == "payment_recovery_delivery_pending" and not failed["success"], failed
        assert len(j.calls) == 2
        now += timedelta(seconds=recovery.INTERVAL_SECONDS + 1)
    recovered = scheduled_completion(j, now=now)
    assert recovered["success"] and recovered["status"] == "payment_recovery_completed", recovered
    assert recovered["telegram_edits"] == 1 and recovered["telegram_sends"] == 0
    assert all(method == "editMessageText" and str(body["message_id"]) == "701" for method, body in j.calls[1:])
    assert scheduled_completion(j, now=now + timedelta(minutes=5))["status"] == "payment_recovery_idle"
    after = j.rail.snapshot()
    for table in before:
        if table != "public.sam_live_stock_conversation_review_events":
            assert after[table] == before[table], table
    assert j.rail.claim()["status"] == "completed" and j.rail.current_source()["status"] == "completed"
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (1,)


def test_completed_delivery_scheduler_rechecks_revoked_recipient(journey, monkeypatch):
    j = journey
    assert present(j)["delivery_confirmed"]
    assert confirmation(j)[1] == 201
    before = j.rail.snapshot()
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "900")
    result = scheduled_completion(j)
    assert not result["success"] and len(j.calls) == 1, result
    assert j.rail.snapshot() == before


def test_scheduler_does_not_invent_authority_for_pre_domain_executing_receipt(journey):
    j = journey
    assert present(j)["delivery_confirmed"]
    c = j.rail.claim()
    accepted, status = claims.claim_callback(f"oompa:{c['callback_token']}:confirm",
        owner_user_id="42", private_chat_id="42", provider_message_id="702",
        provider_timestamp=datetime.now(timezone.utc).isoformat(), source_card_message_id="701", connect_factory=j.rail)
    assert accepted["status"] == "protected_callback_claimed" and status == 200
    assert scheduled_completion(j)["status"] == "payment_recovery_idle"
    assert j.rail.claim()["status"] == "executing"
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (0,)
    # Existing provider retry authority is the original receipt, not a scheduler
    # manufactured confirmation. This test makes that remaining boundary explicit.
    done, status = confirmation(j, "702")
    assert done["success"] and status == 201
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (1,)


def test_scheduled_completion_keeps_unknown_canonical_binding_contained(journey):
    j = journey
    assert present(j)["delivery_confirmed"]
    assert confirmation(j)[1] == 201
    with j.rail.raw() as db, db.cursor() as cur:
        cur.execute("""update app_private.oom_protected_action_claims
            set result_payload=jsonb_set(result_payload,'{operation_id}','\"SYNTHETIC-UNBOUND-OPERATION\"')""")
    now = datetime.now(timezone.utc)
    refused = scheduled_completion(j, now=now)
    assert refused["success"] is False and len(j.calls) == 1, refused
    assert j.rail.row("select last_status from app_private.oom_protected_payment_recovery_leases") == ("effect_unresolved",)
    assert scheduled_completion(j, now=now + timedelta(hours=1))["status"] == "payment_recovery_idle"
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (1,)
