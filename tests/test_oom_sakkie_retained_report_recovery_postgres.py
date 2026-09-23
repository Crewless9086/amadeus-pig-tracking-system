"""Actual retained-report SQL against disposable, isolated canonical rails."""
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from threading import Barrier, Lock
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest

from modules.oom_sakkie import manager_case_sources as sources
from modules.oom_sakkie import herdmaster_retained_recovery_runtime as recovery
from modules.oom_sakkie.general_manager_worker import normalize_candidate
from tests.test_oom_sakkie_herdmaster_retained_recovery_runtime import report

URL = os.environ.get("OOM_PROTECTED_ACTION_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.skipif(not URL, reason="explicit disposable PostgreSQL URL is required")
NOW = datetime(2026, 9, 22, tzinfo=timezone.utc)
OLD = NOW - timedelta(days=40)


class Cursor:
    def __init__(self, cursor, schema):
        self.cursor, self.schema = cursor, schema
    def execute(self, query, params=None):
        self.cursor.execute(query.replace("public.", self.schema + ".").replace(
            "app_private.", self.schema + "."), params)
        return self
    def __getattr__(self, name): return getattr(self.cursor, name)
    def __enter__(self): self.cursor.__enter__(); return self
    def __exit__(self, *args): return self.cursor.__exit__(*args)


class Connection:
    def __init__(self, connection, schema, read_only=False):
        self.connection, self.schema, self.read_only = connection, schema, read_only
    def cursor(self): return Cursor(self.connection.cursor(), self.schema)
    def __getattr__(self, name): return getattr(self.connection, name)
    def __enter__(self):
        self.connection.__enter__()
        if self.read_only: self.connection.execute("set transaction read only")
        return self
    def __exit__(self, *args): return self.connection.__exit__(*args)


def set_current_recipient_policy(monkeypatch, policy):
    """Use real gateway/family configuration for the synthetic private recipient."""
    assert policy in {"owner", "manager", "allowlist_revoked", "binding_revoked",
                      "unknown", "role_downgraded"}
    delegated = policy in {"manager", "binding_revoked", "role_downgraded"}
    owner_id = "900" if delegated or policy == "unknown" else "42"
    bindings = []
    if delegated:
        bindings = [{"telegram_user_id": "42", "family_key": "dad",
            "role": "read_only_family_member" if policy == "role_downgraded" else "farm_manager",
            "permissions": [], "summary_domains": [], "language": "af",
            "authorized_by_user_id": owner_id, "authorization_id": "SYNTHETIC-FAMILY-42",
            "authorized_at": "2026-08-01T00:00:00+00:00"}]
        if policy == "binding_revoked":
            bindings[0]["revoked_at"] = "2026-08-02T00:00:00+00:00"
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS",
                       "900" if policy == "allowlist_revoked" else "42,900")
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_OWNER_USER_ID", owner_id)
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_OWNER_LANGUAGE", "af")
    monkeypatch.setenv("OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON", json.dumps(bindings))


@pytest.fixture
def store(monkeypatch):
    set_current_recipient_policy(monkeypatch, "owner")
    parsed = urlsplit(URL)
    assert parsed.hostname in {"localhost", "127.0.0.1", "::1"} and "test" in parsed.path
    assert not parsed.query, "test connection must not inherit alternate libpq destinations"
    assert not any(os.environ.get(key) for key in ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS")), \
        "disposable fixture must not inherit alternate libpq connection selectors"
    raw_connect = psycopg.connect
    schema = "retained_reports_" + uuid4().hex
    migrations = Path(__file__).resolve().parents[1] / "supabase/migrations"
    def connect(read_only=False): return Connection(raw_connect(URL), schema, read_only)
    with raw_connect(URL) as db:
        db.execute(sql.SQL("create schema {}").format(sql.Identifier(schema)))
    try:
        with connect() as db:
            with db.cursor() as cur:
                for role in ("anon", "authenticated", "service_role"):
                    cur.execute("do $$ begin if not exists(select 1 from pg_roles where rolname='" + role +
                        "') then create role " + role + "; end if; end $$")
                cur.execute("create table app_private.migration_log(migration_id text primary key,description text)")
                cur.execute("create table public.pigs(pig_id text primary key,tag_number text,pig_name text,status text,on_farm boolean,exit_date date,exit_reason text,notes text,updated_at timestamptz,initial_pen_id text)")
                cur.execute("create table public.pig_active_outlets(pig_id text,active boolean,released_at timestamptz)")
                # Synthetic pen membership projection; canonical readback and all
                # lifecycle/welfare effects themselves use the actual runtime.
                cur.execute("create view public.pig_current_state as select pig_id,status,on_farm,case when status='Active' and on_farm then initial_pen_id end current_pen_id from public.pigs")
                cur.execute("create table public.litters(litter_id text primary key,sow_pig_id text,farrowing_date date,litter_status text)")
                cur.execute("create table public.litter_supersessions(superseded_litter_id text)")
                cur.execute("create table public.litter_cohort_dispositions(pig_id text)")
                for name in ("202607210001_create_pig_lifecycle_events.sql",
                             "202607070001_create_sam_live_stock_conversation_review_events.sql",
                             "202608110001_create_oom_protected_action_claims.sql",
                             "202608160004_add_protected_delivery_lifecycle.sql",
                             "202608170002_create_oom_manager_case_runtime.sql",
                             "202608200002_create_pig_welfare_case_lifecycle.sql",
                             "202607190001_create_operational_event_fabric.sql"):
                    ddl = (migrations / name).read_text(encoding="utf-8")
                    ddl = ddl.replace("create schema if not exists app_private;", "")
                    cur.execute(ddl)
                ddl = (migrations / "202607300001_create_litter_supersession_rail.sql").read_text(encoding="utf-8")
                for view in ("current_canonical_pigs", "current_canonical_litters"):
                    cur.execute(re.search(r"create or replace view public\." + view + r" as.*?;", ddl, re.S)[0])
                cur.execute("insert into public.pigs(pig_id,tag_number,pig_name,status,on_farm) values('P27','27','Synthetic pig','Active',true),('SOW-A','S-A','Linda','Active',true)")
        monkeypatch.setattr(recovery, "connect_bounded_read", lambda: connect(True))
        yield connect
    finally:
        with raw_connect(URL) as db:
            db.execute(sql.SQL("drop schema {} cascade").format(sql.Identifier(schema)))


def add_report(store, body, at=OLD):
    with store() as db, db.cursor() as cur:
        cur.execute("""insert into public.sam_live_stock_conversation_review_events
            (review_event_id,event_source,review_json,created_at) values(%s,%s,%s,%s)""",
            (uuid4().hex, recovery.REPORT_SOURCE, Jsonb({"herdmaster_health_loss": body}), at))


def retain(store, key="herdmaster:retained-mortality:101", refs=None, status="exception"):
    refs = refs or ["provider_message:101", "pig:P27", "tag:27"]
    with store() as db, db.cursor() as cur:
        cur.execute("""insert into app_private.oom_manager_cases
            (case_id,dedupe_key,specialist,urgency,status,evidence_digest,evidence_refs,
             summary,next_action,next_reassessment_at,generation)
            values(%s,%s,'HERDMASTER','urgent',%s,%s,%s,'synthetic','reassess',%s,1)""",
            (uuid4().hex, key, status, "0" * 64, Jsonb(refs), OLD))


def collect(store, now=NOW):
    return sources._retained_herd_report_recovery_candidates(now, connect=lambda: store(True))


def test_actual_age_query_keeps_only_exact_open_retained_reports_and_recent_intake(store):
    add_report(store, report()); retain(store)
    add_report(store, report("102", "UNTRACKED"))
    add_report(store, report("103", "NEW"), NOW - timedelta(days=1))
    add_report(store, report("104", "CLOSED"), NOW - timedelta(days=1))
    retain(store, "herdmaster:retained-mortality:104", ["provider_message:104", "pig:P27", "tag:27"], "completed")
    first = collect(store)
    assert {row["dedupe_key"] for row in first} == {
        "herdmaster:retained-mortality:101", "herdmaster:retained-mortality:103"}
    old = next(row for row in first if row["dedupe_key"].endswith(":101"))
    with store() as db, db.cursor() as cur:
        cur.execute("update app_private.oom_manager_cases set evidence_refs=%s where dedupe_key=%s",
                    (Jsonb(old["evidence_refs"]), old["dedupe_key"]))
    later = collect(store, NOW + timedelta(days=30))
    assert len(later) == 1 and later[0]["evidence_refs"] == old["evidence_refs"]
    assert normalize_candidate(later[0], now=NOW)["evidence_digest"] == normalize_candidate(old, now=NOW)["evidence_digest"]


@pytest.mark.parametrize("status", ["contained", "completed", "preview_correction_pending"])
def test_actual_latest_mission_query_sees_later_lifecycle_with_different_provider(store, status):
    add_report(store, report()); retain(store)
    add_report(store, report(provider="901", status=status), OLD + timedelta(days=1))
    assert collect(store) == []


@pytest.mark.parametrize("kind", ["principal_collision", "consumed", "superseded", "missing_member"])
def test_actual_related_identity_queries_contain_ambiguous_or_replaced_reports(store, kind):
    add_report(store, report()); retain(store)
    if kind == "principal_collision":
        add_report(store, report(owner_user_id="99", chat_id="99"))
    elif kind == "missing_member":
        with store() as db, db.cursor() as cur:
            cur.execute("update app_private.oom_manager_cases set evidence_refs=%s",
                        (Jsonb(["provider_message:101", "provider_message:102", "pig:P27", "tag:27"]),))
    else:
        link = ({"consumed_context_missions": ["REPORT-101"]} if kind == "consumed" else
                {"superseded_duplicate_bindings": [{"mission_id": "REPORT-101", "provider_message_id": "101", "tag_number": "27"}]})
        add_report(store, report("901", "CORRECTION", **link), OLD + timedelta(days=1))
    assert collect(store) == []


@pytest.mark.parametrize("status", ["cancelled", "completed", "active", "expired"])
def test_actual_claim_query_matches_original_mission_after_provider_changes(store, status):
    add_report(store, report()); retain(store)
    with store() as db, db.cursor() as cur:
        cur.execute("""insert into app_private.oom_protected_action_claims
            (callback_token,action_kind,owner_user_id,private_chat_id,mission_id,
             provider_message_id,preview_digest,evidence_generation,preview_payload,status,expires_at)
            values('SYNTHETIC','mortality','42','42','REPORT-101','901','D','G','{}',%s,%s)""",
            (status, OLD))
    # Existing terminal/expired attempts remain visible for explicit containment.
    # They do not become new claim authority or disappear from the manager queue.
    case = collect(store)[0]
    assert case["dedupe_key"] == "herdmaster:retained-mortality:101"
    with store(True) as db, db.cursor() as cur:
        cur.execute("select count(*) from app_private.oom_protected_action_claims")
        assert cur.fetchone()[0] == 1


@pytest.mark.parametrize("litter_date", [None, "2026-09-01", "2026-08-01"])
def test_actual_preview_query_never_substitutes_newer_litter_for_retained_incident(store, monkeypatch, litter_date):
    first = report("201", "REPORT-201", owner_text_verbatim="Linda 2 kleintjies dood",
        provider_timestamp="2026-08-20T08:00:00+00:00")
    second = report("202", "REPORT-202", owner_text_verbatim="Linda kleintjies dood op 19 Aug",
        provider_timestamp="2026-08-20T08:01:00+00:00",
        preview={"evaluator": {"identity": {"resolved": True, "pig_id": "SOW-A"}}})
    add_report(store, first); add_report(store, second)
    key = "herdmaster:retained-litter-loss:201:2026-08-19"
    retain(store, key, ["provider_message:201", "provider_message:202", "incident_date:2026-08-19"])
    if litter_date:
        with store() as db, db.cursor() as cur:
            cur.execute("insert into public.litters values('NEW-LITTER','SOW-A',%s,'Active')", (litter_date,))
    def forbidden(*args, **kwargs): raise AssertionError("no claim, farm mutation or provider effect")
    monkeypatch.setattr("modules.oom_sakkie.protected_action_claims.create_claim", forbidden)
    dry_calls = []
    def dry_selection(*args, **kwargs):
        assert kwargs["dry_run"] is True
        dry_calls.append((args, kwargs))
        return {"success": False, "errors": ["Exact selection remains unresolved"]}, 409
    monkeypatch.setattr("modules.pig_weights.pig_weights_service.mark_litter_piglets_dead", dry_selection)
    case = collect(store)[0]
    for _ in range(2):
        result = recovery.build_retained_protected_preview(case)
        expected = ("retained_litter_loss_selection_required" if litter_date == "2026-08-01"
                    else "retained_litter_loss_active_litter_unproven")
        assert result["status"] == expected
        assert result["telegram_sends"] == 0 and result["writes_farm_data"] is False
    assert len(dry_calls) == (2 if litter_date == "2026-08-01" else 0)


def test_actual_bounded_query_rejects_partial_history(store):
    retain(store)
    with store() as db, db.cursor() as cur:
        for index in range(recovery.REPORT_READ_LIMIT + 1):
            cur.execute("""insert into public.sam_live_stock_conversation_review_events
                (review_event_id,event_source,review_json,created_at) values(%s,%s,%s,%s)""",
                (str(index), recovery.REPORT_SOURCE, Jsonb({"herdmaster_health_loss": report()}), OLD))
    with pytest.raises(ValueError, match="retained_report_read_bound_exceeded"):
        collect(store)


def test_actual_current_canonical_identity_excludes_superseded_pig(store):
    add_report(store, report()); retain(store)
    assert len(collect(store)) == 1
    with store() as db, db.cursor() as cur:
        cur.execute("insert into public.litter_cohort_dispositions values('P27')")
    assert collect(store) == []


@pytest.fixture
def delivery_journey(store, monkeypatch):
    """Actual canonical SQL/recorders/claims/domain effects; fake evidence/provider edges."""
    from modules.oom_sakkie import herdmaster_health_loss_runtime as health
    from modules.oom_sakkie import bounded_postgres_read as bounded
    from modules.oom_sakkie import protected_action_claims as claims
    from modules.oom_sakkie import protected_delivery_lifecycle as delivery
    from modules.oom_sakkie import family_message_lifecycle as family
    from modules.pig_weights import pig_welfare_case_runtime as welfare
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("PIG_WELFARE_CASE_RUNTIME_ENABLED", "true")
    # store retains the original raw connector, so all runtime connections use
    # this disposable schema without monkeypatch recursion or external access.
    monkeypatch.setattr(psycopg, "connect", lambda *_a, **_k: store())
    monkeypatch.setattr(bounded, "connect_bounded_rootline_postgres", lambda **kw: store(kw.get("read_only", True)))
    monkeypatch.setattr(claims, "_connect", store)
    monkeypatch.setattr(delivery, "_connect", store)
    monkeypatch.setattr(welfare, "_connect", store)
    evidence = {"evidence_generation": "GEN-27", "as_of_timestamp": "2026-09-23T04:45:00+00:00",
        "animals": [{"pig_id": "P27", "tag_number": "27", "name": "Synthetic",
                     "lifecycle_status": "Active", "on_farm": True, "availability": "Herd", "pen": "PEN-A"}],
        "matings": [], "litters": []}
    monkeypatch.setattr(health, "load_canonical_health_loss_evidence", lambda **_k: evidence)
    with store() as db, db.cursor() as cur:
        cur.execute("update public.pigs set initial_pen_id='PEN-A' where pig_id='P27'")
        cur.execute("insert into public.pig_active_outlets(pig_id,active) values('P27',true)")
    source = report(provider_timestamp="2026-08-20T08:00:00+00:00", output_language="af",
        owner_text_verbatim="Vark nr 27 is dood op 19 Aug 2026. Hy is verwyder en begrawe.")
    add_report(store, source); retain(store)
    case = collect(store)[0]
    # Preserve the qualified binding on the existing case, as the real manager
    # reconciliation does before invoking its delivery adapter.
    with store() as db, db.cursor() as cur:
        cur.execute("update app_private.oom_manager_cases set evidence_refs=%s where dedupe_key=%s",
                    (Jsonb(case["evidence_refs"]), case["dedupe_key"]))
    sends, edits, effects = [], [], []
    def send(chat, text, **kwargs):
        sends.append((chat, text, kwargs))
        return {"success": True, "telegram_message_id": "701",
                "provider_timestamp": datetime.now(timezone.utc).isoformat()}
    def edit(chat, message_id, text, **kwargs):
        edits.append((chat, message_id, text, kwargs))
        return {"success": True, "telegram_message_id": message_id,
                "provider_timestamp": datetime.now(timezone.utc).isoformat()}
    monkeypatch.setattr(family, "_send_telegram", send)
    monkeypatch.setattr(family, "_edit_telegram", edit)
    def claim():
        with store(True) as db, db.cursor() as cur:
            cur.execute("select callback_token,preview_digest,preview_payload,status,expires_at,preview_card_message_id,delivery_state from app_private.oom_protected_action_claims")
            rows = cur.fetchall()
            assert len(rows) == 1
            return dict(zip(("token","digest","payload","status","expires","card","delivery_state"), rows[0]))
    from modules.pig_weights.herdmaster_health_loss_recording import _confirm_mortality_lifecycle
    def effect(lifecycle, evaluator, binding, operation, actor_id, **kwargs):
        current = claim()
        assert operation == current["payload"]["operation_id"]
        assert binding["preview_sha256"] == current["payload"]["preview_sha256"]
        assert lifecycle["mission_id"] == source["mission_id"] and actor_id == "42"
        assert kwargs["evidence_loader"]()["evidence_generation"] == binding["evidence_generation"]
        effects.append(operation)
        return _confirm_mortality_lifecycle(lifecycle, evaluator, binding, operation, actor_id, **kwargs)
    monkeypatch.setattr("modules.pig_weights.herdmaster_health_loss_recording._confirm_mortality_lifecycle", effect)
    return {"case": case, "source": source, "claim": claim, "sends": sends,
            "edits": edits, "effects": effects, "evidence": evidence}


@pytest.mark.parametrize("renewed_expired_claim", [False, True])
def test_actual_manager_preview_delivery_callback_and_exact_replays(store, delivery_journey, renewed_expired_claim):
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    from modules.oom_sakkie.protected_action_runtime import handle_protected_action_input
    from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
    from modules.oom_sakkie.protected_action_claims import protected_card_mission_id
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result, load_family_lifecycle
    from modules.oom_sakkie.herdmaster_health_loss_runtime import _load_active_contexts
    j = delivery_journey
    if renewed_expired_claim:
        expired_renewal_inputs(store, j)
    first = deliver_farm_manager_case(j["case"])
    assert first["success"] and first["delivery_confirmed"]
    claim = j["claim"](); card = protected_card_mission_id(first["mission_id"], claim["digest"])
    assert claim["card"] == "701" and claim["delivery_state"] == "delivery_confirmed"
    assert len(j["sends"]) == 1 and not j["effects"]
    with store(True) as db, db.cursor() as cur:
        cur.execute("select status,on_farm,current_pen_id from public.pig_current_state where pig_id='P27'")
        assert cur.fetchone() == ("Active", True, "PEN-A")
        cur.execute("select count(*) from public.pig_active_outlets where pig_id='P27' and active")
        assert cur.fetchone()[0] == 1
    assert "etiket 27" in j["sends"][0][1] and "2026-08-19" in j["sends"][0][1]
    current = _load_active_contexts("42", owner_user_id="42")[0]
    assert current["operation_id"] == claim["payload"]["operation_id"]
    assert current["mission_id"] == j["source"]["mission_id"]
    assert current["provider_timestamp"] == j["source"]["provider_timestamp"]
    def welfare_counts():
        with store(True) as db, db.cursor() as cur:
            cur.execute("select (select count(*) from public.pig_welfare_cases),(select count(*) from public.pig_welfare_case_events)")
            return cur.fetchone()
    assert welfare_counts() == (1, 1)
    again = deliver_farm_manager_case(collect(store)[0])
    assert again["success"] and again["status"] == "protected_delivery_replayed_noop"
    assert again["delivery_confirmed"] is False and len(j["sends"]) == 1
    assert j["claim"]()["token"] == claim["token"] and j["claim"]()["expires"] == claim["expires"]
    assert welfare_counts() == (1, 1)
    parsed = {"telegram_user_id": "42", "telegram_chat_id": "42", "provider_message_id": "702",
        "provider_timestamp": datetime.now(timezone.utc).isoformat(), "reply_to_message_id": "701",
        "text": "", "output_language": "af"}
    authority = issue_gateway_owner_authority("42", "42")
    callback = "oompa:" + claim["token"] + ":confirm"
    result, status = handle_protected_action_input(parsed, authority, callback_data=callback)
    assert status == 201 and result["success"] and result["card_mission_id"] == card, result
    assert len(j["effects"]) == 1 and j["claim"]()["status"] == "completed"
    visible = deliver_family_result(parsed, result, specialist="HERDMASTER",
        mission_id=result["mission_id"], card_mission_id=result["card_mission_id"])
    assert visible["success"] and visible["telegram_edits"] == 1 and visible["telegram_sends"] == 0
    assert j["edits"][0][1] == "701" and len(j["sends"]) == 1
    replay, replay_status = handle_protected_action_input(parsed, authority, callback_data=callback)
    assert replay_status == 200 and replay["success"] and replay["card_mission_id"] == card
    assert len(j["effects"]) == 1
    repeated = deliver_family_result(parsed, replay, specialist="HERDMASTER",
        mission_id=replay["mission_id"], card_mission_id=replay["card_mission_id"])
    assert repeated["telegram_sends"] == repeated["telegram_edits"] == 0
    assert all(row["card_mission_id"] == card for row in load_family_lifecycle(card))
    # Exact canonical completion projects back onto the same pre-existing manager
    # identity. The worker owns final closure and replay, without another send.
    terminal = collect(store)
    assert len(terminal) == 1 and terminal[0]["terminal_state"] == "completed"
    assert terminal[0]["dedupe_key"] == j["case"]["dedupe_key"]
    from modules.oom_sakkie.general_manager_worker import PostgresManagerCaseStore
    manager = PostgresManagerCaseStore(connect_factory=store)
    normalized = normalize_candidate(terminal[0], now=datetime.now(timezone.utc))
    with store() as db, db.cursor() as cur:
        cur.execute("select case_id from app_private.oom_manager_cases where dedupe_key=%s", (j["case"]["dedupe_key"],))
        original_case_id = cur.fetchone()[0]
        assert manager._reconcile(cur, normalized, datetime.now(timezone.utc)) == "changed"
    with store() as db, db.cursor() as cur:
        assert manager._reconcile(cur, normalized, datetime.now(timezone.utc)) == "replayed"
        cur.execute("select case_id,status from app_private.oom_manager_cases where dedupe_key=%s", (j["case"]["dedupe_key"],))
        assert cur.fetchone() == (original_case_id, "completed")
        cur.execute("select count(*) from app_private.oom_manager_case_events where case_id=%s and event_type='completed'", (original_case_id,))
        assert cur.fetchone()[0] == 1
        cur.execute("select count(*) from public.pig_lifecycle_events")
        assert cur.fetchone()[0] == 1
        cur.execute("select status,on_farm,current_pen_id from public.pig_current_state where pig_id='P27'")
        assert cur.fetchone() == ("Dead", False, None)
        cur.execute("select count(*) from public.pig_active_outlets where pig_id='P27' and active")
        assert cur.fetchone()[0] == 0
        cur.execute("select count(*) from public.pig_welfare_cases")
        assert cur.fetchone()[0] == 1
    assert len(j["effects"]) == len(j["sends"]) == len(j["edits"]) == 1
    assert len(renewal_events(store, claim["token"])) == int(renewed_expired_claim)


@pytest.mark.parametrize("state", ["expired", "cancelled", "delivery_pending", "delivery_ambiguous"])
def test_actual_prepared_claim_is_visible_but_unsafe_states_never_rearm(store, delivery_journey, state):
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    j = delivery_journey
    assert recovery.build_retained_protected_preview(j["case"])["success"]
    before = j["claim"]()
    with store() as db, db.cursor() as cur:
        if state == "expired":
            # An expired claim that has crossed the attempt boundary is never
            # eligible for the distinct, once-only never-attempted renewal.
            cur.execute("""update app_private.oom_protected_action_claims set status='expired',
                expires_at=now()-interval '1 minute',delivery_attempt_id='earlier',
                delivery_attempted_at=now()-interval '2 minutes'""")
        elif state == "cancelled":
            cur.execute("update app_private.oom_protected_action_claims set status='cancelled'")
        else:
            cur.execute("update app_private.oom_protected_action_claims set delivery_state=%s,delivery_attempt_id='earlier',delivery_attempted_at=now()", (state,))
    before = j["claim"]()
    retained = collect(store)
    assert len(retained) == 1 and retained[0]["dedupe_key"] == j["case"]["dedupe_key"]
    result = deliver_farm_manager_case(retained[0])
    assert not result["success"] and not result["delivery_confirmed"]
    assert not j["sends"] and not j["effects"]
    assert j["claim"]()["token"] == before["token"] and j["claim"]()["expires"] == before["expires"]


def test_actual_unattempted_prepared_claim_survives_restart_with_one_card(store, delivery_journey):
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    j = delivery_journey
    assert recovery.build_retained_protected_preview(j["case"])["success"]
    before = j["claim"]()
    assert not before["card"] and before["delivery_state"] == "claim_created" and not j["sends"]
    result = deliver_farm_manager_case(collect(store)[0])
    assert result["success"] and result["delivery_confirmed"] and len(j["sends"]) == 1
    assert j["claim"]()["token"] == before["token"] and j["claim"]()["expires"] == before["expires"]


def test_actual_later_correction_blocks_old_bridge_replay(store, delivery_journey):
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    j = delivery_journey
    assert recovery.build_retained_protected_preview(j["case"])["success"]
    add_report(store, report(provider="999", status="contained"), datetime.now(timezone.utc))
    assert collect(store) == []
    result = deliver_farm_manager_case(j["case"])
    assert not result["success"] and not j["sends"] and not j["effects"]
    assert j["claim"]()["delivery_state"] == "claim_created"



def claim_snapshot(store):
    with store(True) as db, db.cursor() as cur:
        cur.execute("select to_jsonb(c) from app_private.oom_protected_action_claims c")
        records = cur.fetchall()
        assert len(records) == 1
        return records[0][0]


def renewal_events(store, token):
    with store(True) as db, db.cursor() as cur:
        cur.execute("""select to_jsonb(e) from public.operational_events e
            where aggregate_type='protected_action_claim' and aggregate_id=%s
            order by event_id""", (sha256(token.encode()).hexdigest(),))
        return [row[0] for row in cur.fetchall()]


def expired_renewal_inputs(store, journey, *, expired_status="expired"):
    assert recovery.build_retained_protected_preview(journey["case"])["success"]
    with store() as db, db.cursor() as cur:
        cur.execute("""update app_private.oom_protected_action_claims
            set status=%s,delivery_state=%s,expires_at=clock_timestamp()-interval '1 minute'""",
            (expired_status, "expired" if expired_status == "expired" else "claim_created"))
    with store(True) as db, db.cursor() as cur:
        current = recovery.read_retained_health_reports(cur, ["101"])
    reports, failure = recovery.resolve_retained_health_reports(
        current, ["101"], retain_existing_attempts=True)
    assert reports and not failure
    assert len(current["claims"]) == 1
    owner, chat, mission, provider, _status, kind, payload, delivery = current["claims"][0]
    requested = dict(action_kind=kind, owner_user_id=owner, private_chat_id=chat,
        mission_id=mission, provider_message_id=provider,
        evidence_generation=delivery["evidence_generation"], preview_payload=payload)
    return reports, delivery, requested


@pytest.mark.parametrize("expired_status", ["active", "expired"])
def test_actual_never_attempted_expiry_renews_once_without_rearming_on_replay(
        store, delivery_journey, expired_status):
    j = delivery_journey
    rows, delivery, request = expired_renewal_inputs(store, j, expired_status=expired_status)
    before = claim_snapshot(store)
    with store(True) as db, db.cursor() as cur:
        cur.execute("select clock_timestamp()")
        lower_bound = cur.fetchone()[0]
    # High-level recovery revalidates current evidence before entering the helper.
    renewed = recovery.build_retained_protected_preview(collect(store)[0])
    assert renewed["success"] and renewed["confirmation_required"]
    after = claim_snapshot(store)
    expiry = datetime.fromisoformat(after["expires_at"])
    assert lower_bound + timedelta(minutes=30) <= expiry <= datetime.now(timezone.utc) + timedelta(minutes=30)
    assert after["status"] == "active" and after["delivery_state"] == "claim_created"
    mutable = {"status", "expires_at", "delivery_state"}
    assert {k: v for k, v in after.items() if k not in mutable} == {
        k: v for k, v in before.items() if k not in mutable}
    history = renewal_events(store, before["callback_token"])
    assert len(history) == 1
    event = history[0]
    assert event["event_type"] == "retained_protected_preview_expiry_renewed"
    audit = event["payload_json"]
    assert audit["one_time_only"] is True and audit["provider_attempts"] == audit["farm_writes"] == 0
    assert datetime.fromisoformat(audit["old_expires_at"]) == datetime.fromisoformat(before["expires_at"])
    assert datetime.fromisoformat(audit["new_expires_at"]) == expiry
    assert recovery.build_retained_protected_preview(collect(store)[0])["success"]
    assert claim_snapshot(store) == after
    assert renewal_events(store, before["callback_token"]) == history
    # A second elapsed TTL is not a new renewal entitlement, even with no send.
    with store() as db, db.cursor() as cur:
        cur.execute("update app_private.oom_protected_action_claims set expires_at=clock_timestamp()-interval '1 minute'")
    second_expiry = claim_snapshot(store)
    repeated = recovery.build_retained_protected_preview(collect(store)[0])
    assert not repeated["success"] and repeated["status"] == "retained_claim_renewal_already_consumed"
    assert claim_snapshot(store) == second_expiry
    assert renewal_events(store, before["callback_token"]) == history
    assert not j["sends"] and not j["edits"] and not j["effects"]


def test_actual_renewed_claim_still_requires_confirmation_and_sends_one_card(store, delivery_journey):
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    j = delivery_journey
    expired_renewal_inputs(store, j)
    before = claim_snapshot(store)
    first = deliver_farm_manager_case(collect(store)[0])
    assert first["success"] and first["delivery_confirmed"] and first["protected_preview_card_bound"]
    after = claim_snapshot(store)
    assert after["callback_token"] == before["callback_token"]
    assert after["preview_digest"] == before["preview_digest"]
    assert after["preview_payload"] == before["preview_payload"]
    assert after["status"] == "active" and after["delivery_state"] == "delivery_confirmed"
    replay = deliver_farm_manager_case(collect(store)[0])
    assert replay["success"] and replay["delivery_confirmed"] is False
    assert claim_snapshot(store) == after
    assert len(renewal_events(store, before["callback_token"])) == 1
    assert len(j["sends"]) == 1 and not j["edits"] and not j["effects"]
    with store(True) as db, db.cursor() as cur:
        cur.execute("select status,on_farm from public.pigs where pig_id='P27'")
        assert cur.fetchone() == ("Active", True)
        cur.execute("select count(*) from public.pig_lifecycle_events")
        assert cur.fetchone()[0] == 0


@pytest.mark.parametrize("marker", ["preview_card_message_id", "delivery_attempt_id", "delivery_attempted_at",
    "provider_accepted_at", "delivery_confirmed_at", "delivery_ambiguous_at", "delivery_result",
    "confirmation_provider_message_id", "confirmation_provider_timestamp", "result_payload", "completed_at"])
def test_actual_locked_renewal_rejects_every_late_attempt_or_confirmation_marker(
        store, delivery_journey, marker):
    rows, delivery, request = expired_renewal_inputs(store, delivery_journey)
    if marker in {"delivery_result", "result_payload"}:
        value = Jsonb({})  # Even empty persisted results cannot be read as never attempted.
    elif marker.endswith("_at") or marker.endswith("_timestamp"):
        value = datetime.now(timezone.utc)
    else:
        value = "synthetic-earlier"
    with store() as db, db.cursor() as cur:
        cur.execute("update app_private.oom_protected_action_claims set " + marker + "=%s", (value,))
    before = claim_snapshot(store)
    claim, failure = recovery._renew_unattempted_claim(rows, delivery, request)
    assert claim is None and failure == "retained_claim_expired_requires_current_review"
    assert claim_snapshot(store) == before and not renewal_events(store, delivery["callback_token"])
    assert not delivery_journey["sends"] and not delivery_journey["effects"]


@pytest.mark.parametrize("changed", ["owner_user_id", "private_chat_id", "evidence_generation", "preview_payload", "expires_at"])
def test_actual_locked_renewal_rejects_stale_binding_or_expiry_snapshot(store, delivery_journey, changed):
    rows, delivery, request = expired_renewal_inputs(store, delivery_journey)
    with store() as db, db.cursor() as cur:
        if changed == "preview_payload":
            value = Jsonb({**request["preview_payload"], "operation_id": "DIFFERENT-SYNTHETIC-OPERATION"})
        elif changed == "expires_at":
            value = datetime.now(timezone.utc) - timedelta(hours=2)
        else:
            value = "different-synthetic-binding"
        cur.execute("update app_private.oom_protected_action_claims set " + changed + "=%s", (value,))
    before = claim_snapshot(store)
    claim, failure = recovery._renew_unattempted_claim(rows, delivery, request)
    assert claim is None and failure == "retained_claim_expired_requires_current_review"
    assert claim_snapshot(store) == before and not renewal_events(store, delivery["callback_token"])
    assert not delivery_journey["sends"] and not delivery_journey["effects"]


def test_actual_locked_renewal_rechecks_later_source_correction(store, delivery_journey):
    rows, delivery, request = expired_renewal_inputs(store, delivery_journey)
    before = claim_snapshot(store)
    add_report(store, report(provider="901", status="contained"), datetime.now(timezone.utc))
    claim, failure = recovery._renew_unattempted_claim(rows, delivery, request)
    assert claim is None and failure == "retained_claim_source_changed_before_renewal"
    assert claim_snapshot(store) == before and not renewal_events(store, delivery["callback_token"])
    assert not delivery_journey["sends"] and not delivery_journey["effects"]


def test_actual_locked_renewal_does_not_displace_another_active_claim(store, delivery_journey):
    rows, delivery, request = expired_renewal_inputs(store, delivery_journey)
    before = claim_snapshot(store)
    with store() as db, db.cursor() as cur:
        cur.execute("""insert into app_private.oom_protected_action_claims
            (callback_token,action_kind,owner_user_id,private_chat_id,mission_id,provider_message_id,
             preview_digest,evidence_generation,preview_payload,expires_at)
            select callback_token||'-other',action_kind,owner_user_id,private_chat_id,mission_id,
                provider_message_id,repeat('1',64),evidence_generation,preview_payload,clock_timestamp()+interval '30 minutes'
            from app_private.oom_protected_action_claims where callback_token=%s""", (delivery["callback_token"],))
        cur.execute("select to_jsonb(c) from app_private.oom_protected_action_claims c order by callback_token")
        both_before = cur.fetchall()
    claim, failure = recovery._renew_unattempted_claim(rows, delivery, request)
    assert claim is None and failure == "retained_claim_other_active_attempt"
    with store(True) as db, db.cursor() as cur:
        cur.execute("select to_jsonb(c) from app_private.oom_protected_action_claims c order by callback_token")
        assert cur.fetchall() == both_before
    assert not renewal_events(store, before["callback_token"])
    assert not delivery_journey["sends"] and not delivery_journey["effects"]


@pytest.mark.parametrize("fault", ["audit_insert", "audit_readback"])
def test_actual_renewal_audit_failure_rolls_back_claim_and_event(store, delivery_journey, fault):
    rows, delivery, request = expired_renewal_inputs(store, delivery_journey)
    before = claim_snapshot(store)
    # Real PostgreSQL fault at the audit-table boundary after the claim CAS.
    body = ("raise exception 'synthetic audit insert rejection';" if fault == "audit_insert" else
            "new.payload_json=jsonb_set(new.payload_json,'{one_time_only}','false'::jsonb); return new;")
    with store() as db, db.cursor() as cur:
        cur.execute("create function public.renewal_audit_fault() returns trigger language plpgsql as $$ begin " + body + " end $$")
        cur.execute("""create trigger renewal_audit_fault before insert on public.operational_events
            for each row when (new.event_type='retained_protected_preview_expiry_renewed')
            execute function public.renewal_audit_fault()""")
    claim, failure = recovery._renew_unattempted_claim(rows, delivery, request)
    assert claim is None and failure == "retained_claim_renewal_persistence_unproven"
    assert claim_snapshot(store) == before and not renewal_events(store, delivery["callback_token"])
    with store() as db, db.cursor() as cur:
        cur.execute("drop trigger renewal_audit_fault on public.operational_events")
    # Rollback did not consume the one allowed renewal.
    claim, failure = recovery._renew_unattempted_claim(rows, delivery, request)
    assert claim and not failure and claim["retained_unattempted_expiry_renewed"]
    assert len(renewal_events(store, delivery["callback_token"])) == 1
    assert not delivery_journey["sends"] and not delivery_journey["effects"]


def test_actual_two_renewers_wait_on_same_claim_and_commit_one_extension(store, delivery_journey, monkeypatch):
    from modules.oom_sakkie import bounded_postgres_read as bounded
    rows, delivery, request = expired_renewal_inputs(store, delivery_journey)
    before = claim_snapshot(store)
    barrier, guard = Barrier(2), Lock()
    pids = []
    def concurrent_connection(**kwargs):
        db = store(kwargs.get("read_only", True))
        with guard:
            pids.append(db.connection.info.backend_pid)
        barrier.wait(timeout=10)
        return db
    monkeypatch.setattr(bounded, "connect_bounded_rootline_postgres", concurrent_connection)
    with ThreadPoolExecutor(max_workers=2) as executor:
        with store() as held, held.cursor() as cur:
            cur.execute("select callback_token from app_private.oom_protected_action_claims where callback_token=%s for update",
                        (delivery["callback_token"],))
            futures = [executor.submit(recovery._renew_unattempted_claim, rows, delivery, request) for _ in range(2)]
            deadline, blocked = time.monotonic() + 10, False
            while time.monotonic() < deadline:
                with guard:
                    waiting = list(pids)
                if len(waiting) == 2:
                    with store(True) as db, db.cursor() as probe:
                        probe.execute("select count(*) from pg_stat_activity where pid=any(%s) and wait_event_type='Lock'", (waiting,))
                        blocked = probe.fetchone()[0] == 2
                    if blocked:
                        break
                time.sleep(0.02)
            assert blocked, "both actual PostgreSQL sessions must wait on the held claim row"
        results = [future.result(timeout=10) for future in futures]
    assert sum(claim is not None and not failure for claim, failure in results) == 1
    assert sorted(failure for _claim, failure in results) == ["", "retained_claim_expired_requires_current_review"]
    after = claim_snapshot(store)
    assert after["callback_token"] == before["callback_token"]
    assert after["preview_payload"] == before["preview_payload"]
    assert after["status"] == "active" and after["delivery_state"] == "claim_created"
    assert len(renewal_events(store, delivery["callback_token"])) == 1
    assert not delivery_journey["sends"] and not delivery_journey["effects"]


def recipient_effect_snapshot(store):
    """Read complete isolated rows, including audit/claim history, before denial."""
    tables = ("app_private.oom_protected_action_claims", "public.operational_events",
        "public.sam_live_stock_conversation_review_events", "public.pig_welfare_cases",
        "public.pig_welfare_case_events", "public.pig_lifecycle_events", "public.pigs",
        "public.pig_active_outlets", "app_private.oom_manager_cases",
        "app_private.oom_manager_case_events")
    with store(True) as db, db.cursor() as cur:
        snapshot = {}
        for table in tables:
            cur.execute(f"select to_jsonb(r) from {table} r order by to_jsonb(r)::text")
            snapshot[table] = [row[0] for row in cur.fetchall()]
        return snapshot


@pytest.mark.parametrize("policy", ["allowlist_revoked", "binding_revoked", "unknown", "role_downgraded"])
@pytest.mark.parametrize("expired_claim", [False, True])
def test_actual_current_recipient_denial_has_no_claim_renewal_audit_or_delivery(
        store, delivery_journey, monkeypatch, policy, expired_claim):
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    j = delivery_journey
    renewal = expired_renewal_inputs(store, j) if expired_claim else None
    before = recipient_effect_snapshot(store)
    set_current_recipient_policy(monkeypatch, policy)
    # Exercise the real builder/manager and real family policy. A stored owner/chat
    # match cannot stand in for the recipient's current authority.
    result = deliver_farm_manager_case(j["case"])
    assert result["success"] is False and result["delivery_confirmed"] is False
    assert result["status"] == "retained_recipient_not_currently_authorized"
    if renewal is not None:
        claim, failure = recovery._renew_unattempted_claim(*renewal)
        assert claim is None and failure == "retained_recipient_not_currently_authorized"
    assert recipient_effect_snapshot(store) == before
    assert not j["sends"] and not j["edits"] and not j["effects"]


@pytest.mark.parametrize("expired_claim", [False, True])
def test_actual_current_delegated_manager_can_receive_same_claim_once(
        store, delivery_journey, monkeypatch, expired_claim):
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    from modules.oom_sakkie.family_access import resolve_family_principal, FamilyRole
    j = delivery_journey
    set_current_recipient_policy(monkeypatch, "manager")
    parsed = recovery._delivery_context(j["source"])
    assert resolve_family_principal(parsed, os.environ).role is FamilyRole.FARM_MANAGER
    if expired_claim:
        expired_renewal_inputs(store, j)
    result = deliver_farm_manager_case(j["case"])
    assert result["success"] is True and result["delivery_confirmed"] is True
    claim = j["claim"]()
    assert claim["card"] == "701" and claim["delivery_state"] == "delivery_confirmed"
    assert len(renewal_events(store, claim["token"])) == int(expired_claim)
    replay = deliver_farm_manager_case(collect(store)[0])
    assert replay["success"] is True and replay["status"] == "protected_delivery_replayed_noop"
    assert replay["delivery_confirmed"] is False and j["claim"]() == claim
    assert len(j["sends"]) == 1 and not j["edits"] and not j["effects"]
