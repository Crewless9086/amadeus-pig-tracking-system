"""Disposable PostgreSQL proof of the bounded legacy orphan replacement.

All canonical/source/claim/provider-journal/callback code is real. Only Telegram
responses are synthetic. The predecessor lacks its old full preview on purpose.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import hashlib
import json
import time

import psycopg
from psycopg.types.json import Jsonb
import pytest

from tests.test_oom_sakkie_retained_mortality_presentation_postgres import (
    URL, base_store, Rail, _canonical_reader_schema, add_report, report,
    present, confirmation, collect, window_rows, InstrumentedCursor,
)
from modules.oom_sakkie import bounded_postgres_read as bounded
from modules.oom_sakkie import general_manager_worker as manager
from modules.oom_sakkie import herdmaster_health_loss_runtime as health
from modules.oom_sakkie import herdmaster_retained_recovery_runtime as retained
from modules.oom_sakkie import herdmaster_source_transaction as tx
from modules.oom_sakkie import protected_action_claims as claims
from modules.oom_sakkie import protected_delivery_lifecycle as delivery
from modules.oom_sakkie import retained_mortality_history as history
from modules.oom_sakkie import retained_mortality_orphan_recovery as orphan
from modules.pig_weights import pig_welfare_case_runtime as welfare
from modules.sales import sam_live_stock_launch_control as recorder

pytestmark = pytest.mark.skipif(not URL, reason="explicit disposable PostgreSQL URL is required")


@pytest.fixture
def legacy(base_store, monkeypatch):
    _canonical_reader_schema(base_store)
    rail = Rail(base_store)
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("PIG_WELFARE_CASE_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_BOT_TOKEN", "synthetic-test-token")
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_OWNER_LANGUAGE", "af")
    monkeypatch.setattr(psycopg, "connect", lambda *_a, **_k: rail())
    monkeypatch.setattr(bounded, "connect_bounded_rootline_postgres", lambda **kw: rail(kw.get("read_only", True)))
    monkeypatch.setattr(retained, "connect_bounded_read", lambda: rail(True))
    monkeypatch.setattr(claims, "_connect", rail)
    monkeypatch.setattr(delivery, "_connect", rail)
    monkeypatch.setattr(welfare, "_connect", rail)
    source = report(provider_timestamp="2026-08-20T08:00:00+00:00", output_language="af",
        owner_text_verbatim="Vark nr 27 is dood op 19 Aug 2026. Hy is verwyder en begrawe.",
        event_phase="preview_generated", preview={"success":False,"status":"identity_required",
            "confirmation_ready":False,"question_count":1,"owner_text":"Watter vark?",
            "evaluator":{"status":"identity_required","event_family":"unknown",
                "identity":{"resolved":False,"pig_id":None,"candidate_tag_numbers":["27","19"]}}})
    add_report(base_store, source, datetime.now(timezone.utc) - timedelta(days=2))
    evidence = health.load_canonical_health_loss_evidence()
    preview = retained._prepare_retained_report(source, evidence)
    assert preview["confirmation_ready"] and preview["question_count"] == 0
    old_payload = {"operation_id":"LEGACY-ORPHAN-OPERATION", "preview_sha256":"f"*64,
        "identity":deepcopy(preview["evaluator"]["identity"]),"event_family":"found_dead","effect_kind":"mortality"}
    old = claims.create_claim(action_kind="mortality",owner_user_id="42",private_chat_id="42",
        mission_id="LEGACY-ORPHAN-MORTALITY",provider_message_id="101",evidence_generation="old-global-generation",
        preview_payload=old_payload,connect_factory=rail)
    rail.token = old["callback_token"]
    with rail.raw() as db, db.cursor() as cur:
        cur.execute("update app_private.oom_protected_action_claims set created_at=now()-interval '1 day',expires_at=now()-interval '23 hours'")
    now = datetime.now(timezone.utc) - timedelta(hours=6)
    case = manager.normalize_candidate({"dedupe_key":"herdmaster:retained-mortality:101",
        "specialist":"HERDMASTER","urgency":"critical","message_family":"retained_protected_recovery",
        "evidence_refs":["provider_message:101","pig:P27","tag:27","retained_identity_reassessment:required",retained.retained_report_binding([source])],
        "unknowns":[],"summary":"Retained synthetic orphan","next_action":"Present current confirmation",
        "next_reassessment_at":now.isoformat()},now=now)
    queue = manager.PostgresManagerCaseStore(connect_factory=rail)
    with rail() as db, db.cursor() as cur:
        assert queue._reconcile(cur,case,now) == "created"
    case.update(generation=1,message_family="retained_protected_recovery")
    calls=[]
    def provider(_token,method,body):
        calls.append((method,deepcopy(body)))
        return {"ok":True,"result":{"message_id":int(body.get("message_id") or 701),
            "date":int(datetime.now(timezone.utc).timestamp())}}
    monkeypatch.setattr(recorder,"_telegram_api",provider)
    return SimpleNamespace(rail=rail,source=source,case=case,queue=queue,calls=calls,
        old=rail.claim(),preview=preview,evidence=evidence)


def prepare(j):
    result=retained.build_retained_protected_preview(j.case)
    assert result["success"] and result["status"] == "retained_mortality_prepared_not_presented",result
    digest=j.rail.current_source()["retained_repreview"]["claim_preview_digest"]
    j.rail.token=j.rail.row("select callback_token from app_private.oom_protected_action_claims where preview_digest=%s",(digest,))[0]
    assert j.rail.token != j.old["callback_token"]
    return result


def test_prepare_present_confirm_replay_and_manager_close(legacy):
    j=legacy
    prepare(j)
    old=j.rail.row("select to_jsonb(c) from app_private.oom_protected_action_claims c where callback_token=%s",(j.old["callback_token"],))[0]
    assert old == {**j.old,"status":"changed"}
    audit=j.rail.row("select payload_json from public.operational_events where event_type=%s",(orphan.EVENT,))[0]
    assert audit["predecessor"] == orphan._archive(j.old)
    assert audit["equivalence_claimed"] is False and audit["confirmation_required"] is True
    assert j.old["callback_token"] not in json.dumps(audit)
    assert all(j.rail.claim()[k] is None for k in history.EMPTY_MARKERS)
    assert not j.calls and j.rail.row("select count(*) from public.pig_lifecycle_events") == (0,)
    assert present(j)["delivery_confirmed"]
    assert present(j)["telegram_sends"] == 0 and len(j.calls)==1
    done,status=confirmation(j)
    assert status==201 and done["success"],done
    replay,status=confirmation(j)
    assert status==200 and replay["success"] and not replay["writes_farm_data"],replay
    assert j.rail.row("select status,on_farm from public.pigs where pig_id='P27'") == ("Dead",False)
    assert j.rail.row("select count(*) from public.pig_lifecycle_events") == (1,)
    terminal=collect(j.rail.raw,now=datetime.now(timezone.utc),claimed_cases=[j.case])
    assert len(terminal)==1 and terminal[0]["terminal_state"]=="completed",terminal
    closed=manager.normalize_candidate(terminal[0],now=datetime.now(timezone.utc))
    with j.rail() as db,db.cursor() as cur:
        assert j.queue._reconcile(cur,closed,datetime.now(timezone.utc))=="changed"
    assert j.rail.row("select status from app_private.oom_manager_cases")==("completed",)
    assert j.rail.row("select count(*) from app_private.oom_protected_action_claims")== (2,)


@pytest.mark.parametrize("field,value",[(k,
    datetime(2026,9,30,tzinfo=timezone.utc) if k.endswith("_at") or k=="confirmation_provider_timestamp" else
    Jsonb({"success":False}) if k in {"delivery_result","result_payload"} else "fault") for k in history.EMPTY_MARKERS]
    +[("delivery_state","delivery_pending"),("status","cancelled"),("status","completed"),("status","expired")])
def test_attempted_or_terminal_predecessor_never_replaced(legacy,field,value):
    j=legacy
    with j.rail.raw() as db,db.cursor() as cur:
        cur.execute("update app_private.oom_protected_action_claims set "+field+"=%s",(value,))
    before=j.rail.snapshot()
    result=retained.build_retained_protected_preview(j.case)
    assert result["success"] is False,result
    assert j.rail.snapshot()==before and not j.calls


@pytest.mark.parametrize("fault",["unexpired","identity","source","manager","duplicate","prospective_foreign","effect"])
def test_drift_competitors_and_effects_fail_closed(legacy,fault):
    j=legacy
    with j.rail.raw() as db,db.cursor() as cur:
        if fault=="unexpired":
            cur.execute("update app_private.oom_protected_action_claims set expires_at=now()+interval '1 day'")
        elif fault=="identity":
            payload={**j.old["preview_payload"],"identity":{**j.old["preview_payload"]["identity"],"pig_id":"OTHER"}}
            cur.execute("update app_private.oom_protected_action_claims set preview_payload=%s,preview_digest=%s",(Jsonb(payload),claims.canonical_preview_digest("mortality",payload)))
        elif fault=="source":
            assert health._record_lifecycle_event({**j.source,"status":"contained","event_phase":"preview_declined"},
                connect_factory=j.rail,expected_sources={j.source["mission_id"]:tx.digest(j.source)})["success"]
        elif fault=="manager":
            cur.execute("update app_private.oom_manager_cases set generation=generation+1")
        elif fault in {"duplicate","prospective_foreign"}:
            operation=j.preview["confirmation_binding"]["operation_id"]
            mission=("OOM-HERDMASTER-MORTALITY-"+hashlib.sha256(("101|P27|"+operation).encode()).hexdigest()[:24].upper()
                if fault=="prospective_foreign" else "SECOND-LEGACY")
            claims.create_claim(action_kind="mortality",owner_user_id="999" if fault=="prospective_foreign" else "42",private_chat_id="42",
                mission_id=mission,provider_message_id="foreign" if fault=="prospective_foreign" else "101",
                evidence_generation="x",preview_payload=j.old["preview_payload"],connect_factory=j.rail)
        elif fault=="effect":
            cur.execute("update public.pigs set status='Dead',on_farm=false where pig_id='P27'")
    before=j.rail.snapshot()
    result=retained.build_retained_protected_preview(j.case)
    assert result["success"] is False,result
    assert j.rail.snapshot()==before and not j.calls


@pytest.mark.parametrize("needle",["set status='changed'","insert into app_private.oom_protected_action_claims",
    "insert into public.operational_events","insert into public.sam_live_stock_conversation_review_events"])
def test_any_mid_transaction_failure_rolls_back(legacy,needle):
    j=legacy
    before=j.rail.snapshot()
    def fail(_cur,query,_params):
        if needle in " ".join(query.split()).lower():
            raise RuntimeError("synthetic_transaction_failure")
    j.rail.after=fail
    with pytest.raises(RuntimeError,match="synthetic_transaction_failure|health_source_append_failed"):
        retained.build_retained_protected_preview(j.case)
    j.rail.after=None
    assert j.rail.snapshot()==before and not j.calls


def test_two_recovery_transactions_have_one_successor(legacy):
    j=legacy
    def run():
        return retained.build_retained_protected_preview(j.case)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:run(),range(2)))
    assert sum(r["status"]=="retained_mortality_prepared_not_presented" for r in results)==1,results
    assert j.rail.row("select count(*) from app_private.oom_protected_action_claims")== (2,)
    assert j.rail.row("select count(*) from public.operational_events where event_type=%s",(orphan.EVENT,))==(1,)
    assert j.rail.row("select count(*) from public.pig_lifecycle_events")== (0,)
    assert not j.calls


@pytest.mark.parametrize("phase",["presentation","confirmation","replay"])
def test_retired_claim_drift_is_rechecked_at_every_gate(legacy,phase):
    j=legacy
    prepare(j)
    if phase!="presentation":
        assert present(j)["delivery_confirmed"]
    if phase=="replay":
        assert confirmation(j)[1]==201
    with j.rail.raw() as db,db.cursor() as cur:
        cur.execute("update app_private.oom_protected_action_claims set evidence_generation='tampered' where callback_token=%s",(j.old["callback_token"],))
    before=j.rail.snapshot()
    result=present(j) if phase=="presentation" else confirmation(j)[0]
    assert result["success"] is False,result
    after=j.rail.snapshot()
    assert all(after[k]==v for k,v in before.items() if k!="app_private.oom_protected_action_claims")
    assert j.rail.row("select to_jsonb(c) from app_private.oom_protected_action_claims c where callback_token=%s",(j.old["callback_token"],))[0]=={**j.old,"status":"changed","evidence_generation":"tampered"}


def history_like_production(j):
    """4,808 complete historical events, both generations and all old outcomes."""
    now=datetime.now(timezone.utc)-timedelta(hours=5)
    with j.rail.raw() as db,db.cursor() as cur:
        changed={**j.case,"evidence_digest":hashlib.sha256(b"evolved-historical-case-digest").hexdigest()}
        assert j.queue._reconcile(cur,changed,now)=="changed"
        j.case.update(evidence_digest=changed["evidence_digest"],generation=2)
        outcomes=[("claimed","",""),("delegated","",""),("reassessment_scheduled",None,None),
            ("exception","manager_delivery_refresh_unavailable","manager_delivery_refresh_unavailable"),
            ("exception","retained_mortality_removed_disposal_required","retained_mortality_removed_disposal_required"),
            ("exception","retained_protected_repreview_unproven",""),
            ("reassessment_scheduled","manager_cycle_deadline_deferred","manager_cycle_deadline_deferred"),
            ("delivery_suppressed","mortality_preview_ready","")]
        for i in range(4806):
            kind,outcome,failure=outcomes[i%len(outcomes)]
            j.queue._event(cur,j.case,kind,now+timedelta(microseconds=i+1),cycle_id="OLD-CYCLE-"+str(i),
                outcome_status=outcome,failure_kind=failure,provider_ambiguity_contained=False)
    assert j.rail.row("select count(*) from app_private.oom_manager_case_events")== (4808,)


def later_clock(monkeypatch):
    """Advance test clocks without rewriting immutable historic proof rows."""
    import sys
    from modules.oom_sakkie import telegram_direct,retained_mortality_confirmation
    from tests import test_oom_sakkie_retained_mortality_continuation_postgres as native_tests
    from tests import test_oom_sakkie_retained_mortality_presentation_postgres as presentation_tests
    real=datetime
    class Later(real):
        @classmethod
        def now(cls,tz=None):
            return real.now(tz)+timedelta(hours=1)
    for module in (claims,delivery,retained,telegram_direct,retained_mortality_confirmation,
                   native_tests,presentation_tests,sys.modules[__name__]):
        monkeypatch.setattr(module,"datetime",Later)
    execute=InstrumentedCursor.execute
    def advanced(self,query,params=None):
        query=query.replace("clock_timestamp()","(clock_timestamp()+interval '1 hour')")
        query=query.replace("now()","(now()+interval '1 hour')")
        # DB defaults are normally evaluated by PostgreSQL; advance the new
        # synthetic claim's created_at explicitly to the same simulated clock.
        if "insert into app_private.oom_protected_action_claims" in query.lower():
            query=query.replace("preview_payload)","preview_payload,created_at)").replace("%s::jsonb)","%s::jsonb,now()+interval '1 hour')")
        return execute(self,query,params)
    monkeypatch.setattr(InstrumentedCursor,"execute",advanced)


def test_large_original_history_then_expiry_native_confirmation_and_replay(legacy,monkeypatch):
    from tests.test_oom_sakkie_retained_mortality_continuation_postgres import native
    from modules.oom_sakkie import retained_mortality_continuation as continuation
    j=legacy
    history_like_production(j)
    prepare(j)
    assert present(j)["delivery_confirmed"]
    first=j.rail.claim()
    noise_at=datetime.now(timezone.utc)
    with j.rail.raw() as db,db.cursor() as cur:
        cur.execute("""insert into app_private.oom_manager_case_events(event_id,case_id,generation,event_type,event_payload,occurred_at)
            select 'LATER-NOISE-'||i,%s,2,'claimed',jsonb_build_object('case_id',%s::text,'generation',2,'event_type','claimed',
                'occurred_at',%s::timestamptz+i*interval '1 microsecond','cycle_id','QUIET-'||i),
                %s::timestamptz+i*interval '1 microsecond' from generate_series(1,9000) i""",
            (j.case["case_id"],j.case["case_id"],noise_at,noise_at))
    later_clock(monkeypatch)
    (renewed,status),_acks=native(j,monkeypatch)
    assert status==200 and renewed["delivery"].get("delivery_confirmed") is True,renewed.get("protected_action",renewed)
    successor=renewed["protected_action"]
    assert successor["callback_token"]!=first["callback_token"]
    assert j.rail.row("select count(*) from app_private.oom_protected_action_claims")== (3,)
    assert j.rail.row("select count(*) from public.pig_lifecycle_events")== (0,)
    (duplicate,status),_=native(j,monkeypatch,receipt="second-old-press")
    assert status==200 and duplicate["protected_action"]["status"]=="retained_continuation_already_presented",duplicate
    (done,status),_=native(j,monkeypatch,token=successor["callback_token"],card="702",receipt="fresh-confirm")
    assert status==201 and done["protected_action"]["success"],done
    (replay,status),_=native(j,monkeypatch,token=successor["callback_token"],card="702",receipt="fresh-confirm")
    assert status==200 and replay["writes"] is False,replay.get("delivery",replay)
    assert j.rail.row("select count(*) from public.pig_lifecycle_events")== (1,)
    terminal=collect(j.rail.raw,now=datetime.now(timezone.utc),claimed_cases=[j.case])
    assert len(terminal)==1 and terminal[0]["terminal_state"]=="completed",terminal
    assert j.rail.row("select count(*) from public.operational_events where event_type=%s",(continuation.EVENT,))==(1,)


def test_appended_missing_lineage_flag_cannot_confirm(legacy):
    j=legacy
    prepare(j)
    assert present(j)["delivery_confirmed"]
    source=j.rail.current_source()
    changed=deepcopy(source)
    changed["event_phase"] += ":lineage_flag_removed"
    changed["retained_repreview"].pop(orphan.FIELD)
    assert health._record_lifecycle_event(changed,expected_sources={source["mission_id"]:tx.digest(source)},connect_factory=j.rail)["success"]
    result,status=confirmation(j)
    assert status==409 and result["success"] is False,result
    assert j.rail.row("select count(*) from public.pig_lifecycle_events")== (0,)


@pytest.mark.parametrize("tamper",["missing_old","foreign_competitor","old_drift","missing_audit"])
def test_completion_and_scheduled_recovery_require_full_ancestry(legacy,tamper):
    from modules.oom_sakkie import protected_payment_recovery as recovery
    j=legacy
    prepare(j)
    assert present(j)["delivery_confirmed"]
    assert confirmation(j)[1]==201
    with j.rail.raw() as db,db.cursor() as cur:
        if tamper=="missing_old":
            cur.execute("delete from app_private.oom_protected_action_claims where callback_token=%s",(j.old["callback_token"],))
        elif tamper=="old_drift":
            cur.execute("update app_private.oom_protected_action_claims set evidence_generation='tampered' where callback_token=%s",(j.old["callback_token"],))
        elif tamper=="missing_audit":
            cur.execute("alter table public.operational_events disable trigger user")
            cur.execute("delete from public.operational_events where event_type=%s",(orphan.EVENT,))
            cur.execute("alter table public.operational_events enable trigger user")
        else:
            claims.create_claim(action_kind="mortality",owner_user_id="999",private_chat_id="999",
                mission_id=j.rail.claim()["mission_id"],provider_message_id="foreign",evidence_generation="foreign",
                preview_payload=j.old["preview_payload"],connect_factory=j.rail)
    completed=j.rail.claim()
    with pytest.raises((ValueError,RuntimeError)):
        recovery._verify_retained_completion(completed,completed["result_payload"],j.rail)
    terminal=collect(j.rail.raw,now=datetime.now(timezone.utc),claimed_cases=[j.case])
    assert not any(c.get("terminal_state")=="completed" for c in terminal),terminal
    before=len(j.calls)
    cycle=recovery.run_payment_recovery_cycle(connect_factory=j.rail)
    assert cycle["status"]=="payment_recovery_pending" and cycle["success"] is False,cycle
    assert len(j.calls)==before and j.rail.row("select count(*) from public.pig_lifecycle_events")== (1,)


def test_real_waited_source_lock_defers_only_this_manager_case(legacy):
    j=legacy
    with j.rail.raw() as blocker,blocker.cursor() as cursor:
        tx.lock_sources(cursor,"42","42",[j.source["mission_id"]])
        def short_timeout(cur,query,_params):
            if "set_config('statement_timeout'" in query:
                cur.cursor.execute("set local lock_timeout='50ms'")
        j.rail.after=short_timeout
        result=j.queue.run_cycle([j.case],now=datetime.now(timezone.utc),source_revision="synthetic-test",
            deadline_monotonic=time.monotonic()+80,
            refresh_batch=lambda cases:{c["case_id"]:j.case for c in cases},deliver=manager.deliver_farm_manager_case)
        j.rail.after=None
    assert result["status"]!="general_manager_cycle_failed",result
    assert result["deadline_deferrals"]==1 and result["deliveries_confirmed"]==0,result
    assert j.rail.claim()==j.old and j.rail.current_source()==j.source
    assert j.rail.row("select count(*) from public.operational_events where event_type=%s",(orphan.EVENT,))==(0,)
    assert not j.calls
    with j.rail.raw() as db,db.cursor() as cur:
        cur.execute("update app_private.oom_manager_cases set next_reassessment_at=now()-interval '1 second'")
    prepare(j)


def test_late_metadata_deadline_rolls_back_the_entire_replacement(legacy,monkeypatch):
    j=legacy
    clock=[0.0]
    monkeypatch.setattr(orphan.time,"monotonic",lambda:clock[0])
    def after(_cur,query,_params):
        if "set status='changed'" in query:
            clock[0]=51.0
    j.rail.after=after
    before=j.rail.snapshot()
    result=orphan.prepare(j.source,j.case,deadline_monotonic=80,connect_factory=j.rail)
    j.rail.after=None
    assert result["status"]=="manager_cycle_deadline_deferred",result
    assert j.rail.snapshot()==before and not j.calls


def test_default_scheduled_completion_store_accepts_verified_orphan(legacy):
    from modules.oom_sakkie import protected_payment_recovery as recovery
    j=legacy
    prepare(j)
    assert present(j)["delivery_confirmed"]
    assert confirmation(j)[1]==201
    result=recovery.run_payment_recovery_cycle(connect_factory=j.rail)
    assert result["success"] and result["status"]=="payment_recovery_completed",result
    assert j.rail.row("select count(*) from public.pig_lifecycle_events")== (1,)


@pytest.mark.parametrize("fault",["text_false","naive_timestamp","farm_write","future","wrong_generation","null_failure","null_outcome"])
def test_quiet_tail_does_not_hide_invalid_history(legacy,monkeypatch,fault):
    from tests.test_oom_sakkie_retained_mortality_continuation_postgres import native
    j=legacy
    prepare(j)
    assert present(j)["delivery_confirmed"]
    at=datetime.now(timezone.utc)
    with j.rail.raw() as db,db.cursor() as cur:
        material={"case_id":j.case["case_id"],"generation":1,"event_type":"claimed","occurred_at":at.isoformat()}
        if fault=="text_false":material["provider_ambiguity_contained"]="false"
        if fault=="naive_timestamp":material["occurred_at"]=at.replace(tzinfo=None).isoformat()
        if fault=="farm_write":material["writes_farm_data"]=True
        if fault=="null_failure":material["failure_kind"]=None
        if fault=="null_outcome":material["outcome_status"]=None
        if fault=="future":
            at+=timedelta(hours=2)
            material["occurred_at"]=at.isoformat()
        if fault=="wrong_generation":material["generation"]=2
        cur.execute("""insert into app_private.oom_manager_case_events(event_id,case_id,generation,event_type,event_payload,occurred_at)
            values('UNSAFE-NOISE',%s,1,'claimed',%s,%s)""",(j.case["case_id"],Jsonb(material),at))
    later_clock(monkeypatch)
    (result,_status),_=native(j,monkeypatch)
    assert not result["protected_action"]["success"],result
    assert j.rail.row("select count(*) from app_private.oom_protected_action_claims")== (2,)
    assert j.rail.row("select count(*) from public.pig_lifecycle_events")== (0,)
