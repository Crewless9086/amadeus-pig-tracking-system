"""Native callbacks and actual isolated SQL; only external Telegram is fake."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
import pytest
from psycopg.types.json import Jsonb

from tests.test_oom_sakkie_retained_mortality_presentation_postgres import (
    URL, base_store, journey, present, window_rows, cancel_source, collect,
    InstrumentedCursor,
)
from modules.oom_sakkie import telegram_direct as direct
from modules.oom_sakkie import herdmaster_source_transaction as tx
from modules.oom_sakkie import retained_mortality_history as history
from modules.oom_sakkie import retained_mortality_continuation as continuation
from modules.oom_sakkie import retained_mortality_presentation as presentation
from modules.oom_sakkie import protected_action_claims as claims
from modules.oom_sakkie import protected_action_runtime as runtime
from modules.oom_sakkie import general_manager_worker as manager
from modules.oom_sakkie import family_message_lifecycle as family
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie import herdmaster_retained_recovery_runtime as retained
from modules.sales import sam_live_stock_launch_control as recorder

pytestmark = pytest.mark.skipif(not URL, reason="explicit disposable PostgreSQL URL is required")


def historical_delivery(j):
    """Move synthetic metadata chronology back one hour, preserving its proof.

    Production code first creates/admits/delivers the card. This fixture then
    represents that exact sequence an hour ago; physical observation dates and
    original report text/operation remain untouched. No runtime clock is patched.
    """
    assert present(j)["delivery_confirmed"]
    delta = timedelta(hours=1)
    c = j.rail.claim()
    with j.rail.raw() as db, db.cursor() as cur:
        finished = datetime.now(timezone.utc)
        j.queue._event(cur, j.case, "delivery_confirmed", finished, cycle_id="SYNTHETIC-FIRST-CYCLE",
            outcome_status="protected_delivery_confirmed", failure_kind="", provider_ambiguity_contained=False,
            deadline_phase="", processing_timings_ms={"dispatch_wait": 1, "refresh_and_delivery": 1})
        j.queue._event(cur, j.case, "reassessment_scheduled", finished, next_reassessment_at=finished.isoformat())
        cur.execute("update app_private.oom_manager_cases set last_delivery_digest=evidence_digest,last_delivery_at=%s,status='waiting_reassessment'", (finished - delta,))
        # Fixture construction only, inside this test's disposable schema.
        # Restore append-only enforcement before invoking the native callback.
        for table in ("public.sam_live_stock_conversation_review_events", "app_private.oom_manager_case_events", "public.operational_events"):
            cur.execute("alter table " + table + " disable trigger user")
        for col in ("created_at", "expires_at", "delivery_attempted_at", "provider_accepted_at", "delivery_confirmed_at"):
            cur.execute("update app_private.oom_protected_action_claims set " + col + "=" + col + "-interval '1 hour'")
        cur.execute("update public.sam_live_stock_conversation_review_events set created_at=created_at-interval '1 hour'")
        cur.execute("select event_id,event_payload from app_private.oom_manager_case_events")
        for key, p in cur.fetchall():
            p["occurred_at"] = (history._time(p["occurred_at"]) - delta).isoformat()
            cur.execute("update app_private.oom_manager_case_events set occurred_at=occurred_at-interval '1 hour',event_payload=%s where event_id=%s", (Jsonb(p), key))
        cur.execute("select event_id,payload_json from public.operational_events where event_type=%s", (history.WINDOW,))
        key, p = cur.fetchone()
        for name in ("started_at", "new_expires_at", "old_expires_at"):
            p[name] = (history._time(p[name]) - delta).isoformat()
        source = j.rail.current_source()
        source_rows = tx.read_history(cur, [source["mission_id"]])
        p["source_history_sha256"] = tx.digest(source_rows)
        cur.execute("select to_jsonb(e) from app_private.oom_manager_case_events e order by occurred_at,event_id")
        p["case_history_sha256"] = tx.digest([r[0] for r in cur.fetchall()
            if history._time(r[0]["occurred_at"]) <= history._time(p["started_at"])])
        cur.execute("update public.operational_events set occurred_at=occurred_at-interval '1 hour',recorded_at=recorded_at-interval '1 hour',freshness_at=freshness_at-interval '1 hour',payload_json=%s where event_id=%s", (Jsonb(p), key))
        for table in ("public.sam_live_stock_conversation_review_events", "app_private.oom_manager_case_events", "public.operational_events"):
            cur.execute("alter table " + table + " enable trigger user")
    assert history._time(j.rail.claim()["expires_at"]) < datetime.now(timezone.utc)
    return j.rail.claim()


def native(j, monkeypatch, *, token=None, card="701", receipt="expired-click-1", action="confirm", ack_ok=True, send_ok=True):
    token = token or j.rail.token
    env = dict(os.environ, OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED="true",
        OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED="true", OOM_SAKKIE_TELEGRAM_BOT_TOKEN="123456:synthetic-bot-token-value",
        OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET="synthetic-private-webhook-secret-123456")
    acknowledgements = []
    def ack(request, **kw):
        assert request.full_url.endswith("/answerCallbackQuery")
        acknowledgements.append(json.loads(request.data))
        if not ack_ok:
            raise OSError("synthetic expired query id")
        return BytesIO(b'{"ok":true}')
    monkeypatch.setattr(direct.urllib_request, "urlopen", ack)
    def provider(_token, method, body):
        j.calls.append((method, deepcopy(body)))
        if not send_ok:
            raise OSError("synthetic uncertain provider response")
        return {"ok": True, "result": {"message_id": int(body.get("message_id") or (700 + len(j.calls))),
            "date": int(datetime.now(timezone.utc).timestamp())}}
    monkeypatch.setattr(recorder, "_telegram_api", provider)
    payload = {"update_id": 9100, "callback_query": {"id": receipt,
        "from": {"id": 42, "is_bot": False, "first_name": "Synthetic"},
        "message": {"message_id": int(card), "date": int(datetime.now(timezone.utc).timestamp()) - 3600,
            "chat": {"id": 42, "type": "private"}, "text": "Original protected preview"},
        "chat_instance": "synthetic-chat", "data": f"oompa:{token}:{action}"}}
    result = direct.handle_telegram_direct_webhook(payload,
        {"X-Telegram-Bot-Api-Secret-Token": env["OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET"]}, env)
    return result, acknowledgements


@pytest.mark.parametrize("journey", ["en", "af"], indirect=True)
def test_native_expired_click_presents_new_review_then_genuine_confirmation_once(journey, monkeypatch):
    j = journey
    original = historical_delivery(j)
    (body, status), acks = native(j, monkeypatch)
    assert status == 200, body
    assert body["delivery"].get("delivery_confirmed") is True, body
    assert len(j.calls) == 2 and acks[-1]["show_alert"] is True
    assert "30" in j.calls[-1][1]["text"]
    new = body["protected_action"]
    assert new["callback_token"] != original["callback_token"]
    assert new["preview_digest"] != original["preview_digest"]
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (0,)
    old = j.rail.claim()
    assert {k:v for k,v in old.items() if k != "status"} == {k:v for k,v in original.items() if k != "status"}
    assert old["status"] == "expired" and old["confirmation_provider_message_id"] is None
    audits = j.rail.row("select payload_json from public.operational_events where event_type=%s", (continuation.EVENT,))[0]
    assert original["callback_token"] not in json.dumps(audits) and new["callback_token"] not in json.dumps(audits)
    (duplicate, status), acks = native(j, monkeypatch, receipt="another-old-press")
    assert status == 200 and len(j.calls) == 2 and acks[-1].get("text")
    assert duplicate["protected_action"]["status"] == "retained_continuation_already_presented"
    assert retained.build_retained_protected_preview(j.case)["status"] == "retained_mortality_continuation_owner_review"
    (done, status), _ = native(j, monkeypatch, token=new["callback_token"], card="702", receipt="fresh-confirm")
    assert status == 201 and done["protected_action"]["success"], done
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (1,)
    (replay, status), _ = native(j, monkeypatch, token=new["callback_token"], card="702", receipt="fresh-confirm")
    assert status == 200 and replay["writes"] is False, replay["delivery"]
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (1,)
    result = collect(j.rail.raw, now=datetime.now(timezone.utc), claimed_cases=[j.case])
    assert len(result) == 1 and result[0]["terminal_state"] == "completed", result
    closed = j.queue.run_cycle(result, now=datetime.now(timezone.utc), source_revision="synthetic-test")
    assert closed["success"] and j.rail.row("select case_id,status from app_private.oom_manager_cases") == (j.case["case_id"], "completed")
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (1,)


def test_changed_material_at_admission_has_feedback_and_no_card_attempt(journey, monkeypatch):
    j = journey
    historical_delivery(j)
    with j.rail.raw() as db, db.cursor() as cur:
        cur.execute("update public.pigs set initial_pen_id='PEN-B' where pig_id='P27'")
    (body, status), acks = native(j, monkeypatch, ack_ok=False)
    assert status == 200 and body["delivery"]["success"] is False, body
    assert body["feedback_delivery"]["success"] is True and len(j.calls) == 2, body
    assert "reply_markup" not in j.calls[-1][1] or not j.calls[-1][1]["reply_markup"]
    assert j.rail.row("select count(*) from app_private.oom_protected_action_claims where confirmation_provider_message_id is not null") == (0,)
    assert len(window_rows(j)) == 1
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (0,)


def test_cancelled_source_refuses_without_new_claim(journey, monkeypatch):
    j = journey
    historical_delivery(j)
    assert cancel_source(j)["success"]
    (body, status), acks = native(j, monkeypatch)
    assert status == 200 and body["protected_action"]["success"] is False, body
    assert acks[-1].get("text") and len(j.calls) == 1
    assert j.rail.row("select count(*) from app_private.oom_protected_action_claims") == (1,)


def test_uncertain_successor_delivery_is_not_resent_or_called_presented(journey, monkeypatch):
    j = journey
    historical_delivery(j)
    (first, status), alerts = native(j, monkeypatch, send_ok=False)
    assert status == 200 and first["delivery"]["status"] == "protected_delivery_ambiguous", first
    assert "onseker" in alerts[-1]["text"] and len(j.calls) == 2
    (again, status), alerts = native(j, monkeypatch, receipt="distinct-repeat-after-uncertainty")
    assert status == 200 and again["protected_action"]["status"] == "retained_continuation_delivery_uncertain"
    assert "onseker" in alerts[-1]["text"] and len(j.calls) == 2
    assert j.rail.row("select count(*) from app_private.oom_protected_action_claims") == (2,)
    assert len(window_rows(j)) == 2 and j.rail.row("select count(*) from public.pig_lifecycle_events") == (0,)


def request_only(j, receipt="prepare-only", token=None, card="701"):
    token = token or j.rail.token
    data = f"oompa:{token}:confirm"
    parsed = {"telegram_user_id": "42", "telegram_chat_id": "42", "telegram_chat_type": "private",
        "provider_message_id": receipt, "provider_timestamp": datetime.now(timezone.utc).isoformat(),
        "callback_query_id": receipt, "callback_data": data, "reply_to_message_id": card,
        "text": "", "output_language": "af"}
    result, status = runtime.handle_protected_action_input(parsed, issue_gateway_owner_authority("42", "42"),
        callback_data=data, connect_factory=j.rail)
    return result, status, parsed


@pytest.mark.parametrize("transition_first", [False, True])
def test_restart_resumes_only_existing_requested_generation_in_normal_manager_cycle(journey, monkeypatch, transition_first):
    j = journey
    original = historical_delivery(j)
    with j.rail.raw() as db, db.cursor() as cur:
        cur.execute("update app_private.oom_manager_cases set last_delivery_digest=evidence_digest,last_delivery_at=%s",
            (history._time(original["delivery_confirmed_at"]),))
    prepared, status, _ = request_only(j)
    assert status == 200 and prepared["status"] == "preview_ready", prepared
    assert len(j.calls) == 1  # process stops after request commit, before provider
    now = datetime.now(timezone.utc)
    candidates = collect(j.rail.raw, now=now, claimed_cases=[j.case])
    assert len(candidates) == 1 and candidates[0]["dedupe_key"] == j.case["dedupe_key"]
    assert "retained_confirmation:" + prepared["preview_digest"] in candidates[0]["evidence_refs"]
    read_rows = continuation._rows
    def tied_order(cur, query, params):
        rows = read_rows(cur, query, params)
        if "oom_manager_case_events" in query:
            # Both are valid event-ID orders for one real cycle instant.
            rows.sort(key=lambda e: (history._time(e["occurred_at"]),
                (e["event_type"] != "evidence_changed") if transition_first else (e["event_type"] == "evidence_changed"),
                e["event_id"]))
        return rows
    monkeypatch.setattr(continuation, "_rows", tied_order)
    result = j.queue.run_cycle(candidates, now=now, source_revision="synthetic-test", deadline_monotonic=time.monotonic()+80,
        refresh_batch=lambda cs: {c["case_id"]: candidates[0] for c in cs}, deliver=manager.deliver_farm_manager_case)
    assert result["success"] and result["deliveries_confirmed"] == 1, (result["case_results"], j.rail.row(
        "select event_payload from app_private.oom_manager_case_events where event_type='exception' order by occurred_at desc limit 1"))
    assert len(j.calls) == len(window_rows(j)) == 2
    assert j.rail.row("select case_id,generation from app_private.oom_manager_cases") == (j.case["case_id"], 2)
    next_at = j.rail.row("select next_reassessment_at from app_private.oom_manager_cases")[0]
    later = j.queue.run_cycle(candidates, now=next_at, source_revision="synthetic-test",
        refresh_batch=lambda cs: {c["case_id"]: candidates[0] for c in cs}, deliver=manager.deliver_farm_manager_case)
    assert later["success"] and later["deliveries_confirmed"] == 0 and len(j.calls) == 2, later
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (0,)


def test_racing_requests_recover_one_durable_successor(journey):
    j = journey
    historical_delivery(j)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda r: request_only(j, receipt=r), ["race-a", "race-b"]))
    assert all(status == 200 and r["status"] == "preview_ready" for r, status, _ in results), results
    assert len({r["callback_token"] for r, _, _ in results}) == 1
    assert j.rail.row("select count(*) from app_private.oom_protected_action_claims where status='active'") == (1,)
    assert j.rail.row("select count(*) from public.operational_events where event_type=%s", (continuation.EVENT,)) == (1,)
    assert len(j.calls) == 1


@pytest.mark.parametrize("change", ["unknown_audit", "unknown_lineage", "unknown_case", "ambiguous_family", "earlier_provider_claim"])
def test_complete_history_drift_prevents_continuation(journey, monkeypatch, change):
    j = journey
    if change == "earlier_provider_claim":
        from tests.test_oom_sakkie_retained_report_recovery_postgres import add_report
        older = {**j.source, "provider_message_id": "100", "event_phase": "earlier_original_fragment"}
        add_report(j.rail.raw, older, datetime.now(timezone.utc) - timedelta(days=2))
    old = historical_delivery(j)
    with j.rail.raw() as db, db.cursor() as cur:
        if change in {"unknown_audit", "unknown_lineage"}:
            row = deepcopy(window_rows(j)[0])
            row.update(event_id="SYNTHETIC-UNKNOWN", idempotency_key="synthetic-unknown", event_type="unknown_authority")
            if change == "unknown_lineage":
                row.update(event_type=continuation.EVENT, aggregate_id="f"*64, correlation_id=old["mission_id"])
            cur.execute("insert into public.operational_events select * from jsonb_populate_record(null::public.operational_events,%s)", (Jsonb(row),))
        elif change == "unknown_case":
            j.queue._event(cur, j.case, "exception", datetime.now(timezone.utc), outcome_status="unknown_failure")
        elif change == "earlier_provider_claim":
            other = deepcopy(old)
            other.update(callback_token="SYNTHETIC-COMPETITOR", mission_id="SYNTHETIC-OTHER-MISSION",
                provider_message_id="100", preview_digest="f"*64, status="expired",
                delivery_attempt_id="synthetic-competing-attempt")
            cur.execute("insert into app_private.oom_protected_action_claims select * from jsonb_populate_record(null::app_private.oom_protected_action_claims,%s)", (Jsonb(other),))
    if change == "ambiguous_family":
        card = claims.protected_card_mission_id(old["mission_id"], old["preview_digest"])
        row = next(r for r in family._event_store("load", card, None) if r["state"] == "delivered")
        family._event_store("record", card + "-UNKNOWN", {**row, "event_id": card+"-UNKNOWN", "state": "contained", "reason": "unknown_provider_effect"})
    (body, status), acks = native(j, monkeypatch)
    assert status == 200 and body["protected_action"]["success"] is False, body
    assert acks[-1].get("text") and len(j.calls) == 1
    assert j.rail.row("select count(*) from public.operational_events where event_type=%s", (continuation.EVENT,)) == ((1,) if change == "unknown_lineage" else (0,))


@pytest.mark.parametrize("action", ["cancel", "change"])
def test_expired_old_cancel_change_cannot_change_successor(journey, monkeypatch, action):
    j = journey
    historical_delivery(j)
    (first, _), _ = native(j, monkeypatch)
    token = first["protected_action"]["callback_token"]
    before = j.rail.row("select to_jsonb(c) from app_private.oom_protected_action_claims c where callback_token=%s", (token,))[0]
    native(j, monkeypatch, action=action, receipt="old-"+action)
    assert j.rail.row("select to_jsonb(c) from app_private.oom_protected_action_claims c where callback_token=%s", (token,))[0] == before
    assert len(j.calls) == 2 and j.rail.row("select count(*) from public.pig_lifecycle_events") == (0,)


@pytest.mark.parametrize("boundary", ["audit", "source"])
def test_request_creation_failure_rolls_back_successor_audit_and_source(journey, boundary):
    j = journey
    historical_delivery(j)
    source = j.rail.current_source()
    def fail(_cur, query, params):
        if ((boundary == "audit" and "insert into public.operational_events" in query)
                or (boundary == "source" and "insert into public.sam_live_stock_conversation_review_events" in query)):
            raise RuntimeError("synthetic after-" + boundary + " failure")
    j.rail.after = fail
    result, status, _ = request_only(j)
    j.rail.after = None
    assert status == 200 and not result["success"], result
    assert j.rail.current_source() == source
    assert j.rail.row("select count(*) from app_private.oom_protected_action_claims") == (1,)
    assert j.rail.row("select count(*) from public.operational_events where event_type=%s", (continuation.EVENT,)) == (0,)


def test_revoked_principal_cannot_request_or_admit_successor(journey, monkeypatch):
    from tests.test_oom_sakkie_retained_report_recovery_postgres import set_current_recipient_policy
    j = journey
    historical_delivery(j)
    prepared, _, parsed = request_only(j)
    set_current_recipient_policy(monkeypatch, "allowlist_revoked")
    outcome = family.deliver_family_result(parsed, prepared, specialist="HERDMASTER",
        mission_id=prepared["mission_id"], card_mission_id=prepared["card_mission_id"])
    assert outcome["success"] is False and len(j.calls) == 1, outcome
    assert len(window_rows(j)) == 1
    (body, status), _ = native(j, monkeypatch, receipt="revoked-click")
    assert status == 403 and not body["success"]


def test_successor_expiry_needs_its_own_real_press_and_preserves_linear_operation(journey, monkeypatch):
    j = journey
    historical_delivery(j)
    (first, _), _ = native(j, monkeypatch)
    new = first["protected_action"]
    now = datetime.now(timezone.utc)
    candidates = collect(j.rail.raw, now=now, claimed_cases=[j.case])
    quiet = j.queue.run_cycle(candidates, now=now, source_revision="synthetic-test",
        refresh_batch=lambda cs: {c["case_id"]: candidates[0] for c in cs}, deliver=manager.deliver_farm_manager_case)
    assert quiet["exceptions"] == quiet["deliveries_confirmed"] == 0 and quiet["deliveries_suppressed"] == 1, quiet["case_results"]
    assert len(j.calls) == 2
    # Advance only observation clocks, without modifying either durable window.
    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(minutes=31)
    monkeypatch.setattr(direct, "datetime", Later)
    monkeypatch.setattr(claims, "datetime", Later)
    original_execute = InstrumentedCursor.execute
    def execute(cursor, query, params=None):
        return original_execute(cursor, query.replace("clock_timestamp()", "(clock_timestamp()+interval '31 minutes')"), params)
    monkeypatch.setattr(InstrumentedCursor, "execute", execute)
    (old_retry, status), _ = native(j, monkeypatch, receipt="old-after-successor-expiry")
    assert status == 200 and old_retry["protected_action"]["success"] is False
    assert j.rail.row("select count(*) from app_private.oom_protected_action_claims") == (2,)
    (next_one, status), _ = native(j, monkeypatch, token=new["callback_token"], card="702", receipt="new-card-expired-click")
    assert status == 200 and next_one["protected_action"]["status"] == "preview_ready", next_one
    assert next_one["delivery"].get("delivery_confirmed") is True and len(j.calls) == 3, json.dumps(next_one["delivery"])
    assert j.rail.row("select count(*) from app_private.oom_protected_action_claims") == (3,)
    assert j.rail.row("select count(distinct preview_payload->>'operation_id') from app_private.oom_protected_action_claims") == (1,)
    assert j.rail.row("select count(*) from app_private.oom_protected_action_claims where status='active'") == (1,)
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (0,)
    latest = next_one["protected_action"]
    (done, status), _ = native(j, monkeypatch, token=latest["callback_token"], card="703", receipt="third-card-confirm")
    assert status == 201 and done["protected_action"]["success"], done
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (1,)
    terminal = collect(j.rail.raw, now=Later.now(timezone.utc), claimed_cases=[j.case])
    assert len(terminal) == 1 and terminal[0].get("terminal_state") == "completed", terminal
    closed = j.queue.run_cycle(terminal, now=Later.now(timezone.utc), source_revision="synthetic-test")
    assert closed["success"] and j.rail.row("select case_id,status from app_private.oom_manager_cases") == (j.case["case_id"], "completed")


def test_successor_presend_rollback_then_next_manager_cycle_delivers(journey, monkeypatch):
    j = journey
    historical_delivery(j)
    prepared, _, _ = request_only(j)
    candidates = collect(j.rail.raw, now=datetime.now(timezone.utc), claimed_cases=[j.case])
    initial = time.monotonic()
    clock, expired = [initial], []
    monkeypatch.setattr(presentation, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    def expire(_cur, query, _params):
        if "update app_private.oom_protected_action_claims c set status='active',expires_at" in query:
            clock[0] = initial + 51.0
            expired.append(True)
    j.rail.after = expire
    first = j.queue.run_cycle(candidates, now=datetime.now(timezone.utc), source_revision="synthetic-test",
        refresh_batch=lambda cs: {c["case_id"]: candidates[0] for c in cs},
        deliver=lambda c: manager.deliver_farm_manager_case(c, deadline_monotonic=initial+80))
    j.rail.after = None
    assert expired and first["exceptions"] == 1 and len(j.calls) == len(window_rows(j)) == 1, first["case_results"]
    assert first["case_results"][0]["outcome_status"] == "family_message_cycle_deadline_deferred"
    clock[0] = time.monotonic()
    second = j.queue.run_cycle(candidates, now=datetime.now(timezone.utc), source_revision="synthetic-test",
        refresh_batch=lambda cs: {c["case_id"]: candidates[0] for c in cs},
        deliver=lambda c: manager.deliver_farm_manager_case(c, deadline_monotonic=clock[0]+80))
    assert second["deliveries_confirmed"] == 1 and len(j.calls) == len(window_rows(j)) == 2, second["case_results"]
