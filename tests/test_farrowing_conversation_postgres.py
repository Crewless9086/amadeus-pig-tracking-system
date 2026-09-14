"""Real retained conversation, protected claim and canonical writer on a disposable fixture."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import os
from urllib.parse import urlparse
import uuid

import psycopg
import pytest

from modules.oom_sakkie import herdmaster_farrowing_runtime as runtime
from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_farrowing_conversation import EVENT_SOURCE, _FarrowingTransaction
from modules.oom_sakkie.protected_action_claims import bind_claim_card
from modules.oom_sakkie.protected_action_runtime import handle_protected_action_input


def connect(*_args):
    dsn = os.environ.get("CHARLIE_DISPOSABLE_POSTGRES_URL", "")
    if not dsn:
        pytest.skip("Explicit separate disposable herd database required")
    parsed = urlparse(dsn)
    assert parsed.hostname in {"127.0.0.1", "localhost"}
    assert parsed.path == "/herd_first_treatment_test_weaning_test"
    return psycopg.connect(dsn)


def seed():
    token = uuid.uuid4().hex[:10].upper()
    row = {"sow": "SOW-FARROW-" + token, "tag": "Synthetic Linda " + token,
           "actor": str(7000000000 + int(token[:8], 16)), "card": "9000" + str(int(token[:8], 16))}
    with connect() as db:
        db.execute("""insert into public.pigs(pig_id,tag_number,pig_name,status,on_farm,animal_type,sex,date_of_birth)
            values(%s,%s,null,'Active',true,'Sow','Female','2024-01-01')""", (row["sow"], row["tag"]))
    return row


def facts(row, **overrides):
    return {"sow_ref": row["tag"], "farrowing_date": "2026-08-22", "total_born": 9,
            "born_alive": 8, "mummified": 1, **overrides}


def parsed(row, supplied, *, provider="1", continuation=False, reply=""):
    return {"telegram_user_id": row["actor"], "telegram_chat_id": row["actor"],
        "provider_message_id": provider, "provider_timestamp": datetime.now(timezone.utc).isoformat(),
        "text": str(supplied), "reply_to_message_id": reply, "output_language": "en",
        "semantic": {"domain": "herd_management", "intent": "record_farrowing_litter",
            "message_kind": "observation", "confidence": 0.99, "continuation": continuation,
            "farrowing_litter": supplied}}


def report(row, message):
    return runtime.handle_farrowing_litter_message(message,
        issue_gateway_owner_authority(row["actor"], row["actor"]), connect_factory=connect)


def deliver(row, message, result):
    delivery = deliver_family_result(message, result, specialist="HERDMASTER",
        mission_id=result["mission_id"], card_mission_id=result["card_mission_id"],
        sender=lambda *_args, **_kwargs: {"success": True, "telegram_message_id": row["card"]},
        editor=lambda *_args, **_kwargs: {"success": True, "telegram_message_id": row["card"]})
    assert delivery["success"] is True, delivery
    if result.get("callback_token"):
        assert bind_claim_card(result["callback_token"], row["card"], connect_factory=connect)
    return delivery


def callback(row, preview, *, provider="100"):
    return {"telegram_user_id": row["actor"], "telegram_chat_id": row["actor"],
        "provider_message_id": provider, "provider_timestamp": datetime.now(timezone.utc).isoformat(),
        "reply_to_message_id": row["card"], "callback_data": "oompa:" + preview["callback_token"] + ":confirm",
        "text": "", "output_language": "en"}


def confirm(row, message):
    return handle_protected_action_input(message, issue_gateway_owner_authority(row["actor"], row["actor"]),
                                         connect_factory=connect)


def farm_snapshot(row):
    with connect() as db:
        return {
            "litters": db.execute("select litter_id,total_born,born_alive,stillborn_count,mummified_count from public.litters where sow_pig_id=%s order by litter_id", (row["sow"],)).fetchall(),
            "piglets": db.execute("select pig_id,status,on_farm,litter_id from public.pigs where mother_pig_id=%s order by pig_id", (row["sow"],)).fetchall(),
            "followups": db.execute("select case_id,dedupe_key from app_private.oom_manager_cases where dedupe_key in (select 'herdmaster-litter-follow-up:'||litter_id from public.litters where sow_pig_id=%s) order by case_id", (row["sow"],)).fetchall(),
        }


def claim_count(row):
    with connect() as db:
        return db.execute("select count(*) from app_private.oom_protected_action_claims where owner_user_id=%s", (row["actor"],)).fetchone()[0]


def test_question_card_short_reply_confirms_one_canonical_litter_and_replays_without_second_write():
    row = seed()
    first = parsed(row, facts(row, farrowing_date=None))
    question, code = report(row, first)
    assert code == 200 and question["question_count"] == 1
    deliver(row, first, question)
    second = parsed(row, {"farrowing_date": "2026-08-22"}, provider="2", continuation=True, reply=row["card"])
    context = runtime.load_farrowing_context(second, connect_factory=connect)
    assert context["facts"]["total_born"] == 9 and context["facts"]["born_alive"] == 8
    preview, code = report(row, second)
    assert code == 200 and preview["status"] == "farrowing_litter_preview_ready"
    assert farm_snapshot(row) == {"litters": [], "piglets": [], "followups": []}
    deliver(row, second, preview)
    confirmation = callback(row, preview)
    saved, code = confirm(row, confirmation)
    assert code == 201 and saved["canonical_readback_verified"] is True, saved
    assert "total 9, 8 born alive, 0 stillborn, 1 mummified" in saved["answer"]
    assert saved["mission_id"] == preview["mission_id"]
    deliver(row, confirmation, saved)
    context = runtime.load_farrowing_context(parsed(row, {}, provider="200"), connect_factory=connect)
    assert context["canonical_litters_source"] == "retained_confirmed_result"
    assert context["canonical_litters"][0]["litter_id"] == saved["litter_id"]
    before = farm_snapshot(row)
    assert len(before["litters"]) == 1 and len(before["piglets"]) == 8 and len(before["followups"]) == 1
    replay, code = confirm(row, confirmation)
    assert code == 200 and replay["success"] is True
    assert farm_snapshot(row) == before and claim_count(row) == 1
    initial_replay, code = report(row, second)
    assert code == 200 and initial_replay["writes_farm_data"] is False
    assert initial_replay["rows_created"] == 0 and initial_replay["protected_actions_performed"] is False
    assert farm_snapshot(row) == before and claim_count(row) == 1


def test_earlier_linda_eight_seven_one_report_cannot_replace_later_confirmed_nine_eight_one():
    row = seed()
    initial = parsed(row, facts(row))
    preview, _ = report(row, initial)
    deliver(row, initial, preview)
    saved, code = confirm(row, callback(row, preview))
    assert code == 201 and saved["success"] is True
    before = farm_snapshot(row)
    earlier_counts = parsed(row, facts(row, total_born=8, born_alive=7), provider="200")
    held, code = report(row, earlier_counts)
    assert code == 409 and held["status"] == "canonical_litter_count_conflict"
    assert "total 9, born alive 8" in held["answer"] and "total 8, born alive 7" in held["answer"]
    assert held["writes_farm_data"] is False and held["question_count"] == 0
    assert farm_snapshot(row) == before and claim_count(row) == 1


def test_explicit_reason_only_correction_reuses_reported_counts_and_exact_saved_litter():
    row = seed()
    initial = parsed(row, facts(row))
    preview, _ = report(row, initial)
    deliver(row, initial, preview)
    saved, code = confirm(row, callback(row, preview))
    assert code == 201 and saved["success"] is True
    before = farm_snapshot(row)
    counts = parsed(row, facts(row, total_born=8, born_alive=7), provider="200")
    held, code = report(row, counts)
    assert code == 409 and held["status"] == "canonical_litter_count_conflict"
    reason = parsed(row, {"correction_reason": "I counted one piglet twice"}, provider="201", continuation=True)
    reason["semantic"]["message_kind"] = "correction"
    context = runtime.load_farrowing_context(reason, connect_factory=connect)
    assert context["facts"]["total_born"] == 8 and context["facts"]["born_alive"] == 7
    revised, code = report(row, reason)
    assert code == 200 and revised["status"] == "farrowing_litter_preview_ready", revised
    with connect() as db:
        claim = db.execute("select preview_payload from app_private.oom_protected_action_claims where callback_token=%s", (revised["callback_token"],)).fetchone()[0]
    assert claim["correction_of_litter_id"] == saved["litter_id"]
    assert claim["counts"]["total_born"] == 8 and claim["counts"]["born_alive"] == 7
    assert revised["writes_farm_data"] is False
    assert farm_snapshot(row) == before and claim_count(row) == 2


def test_interrupted_readback_recovers_same_confirmed_operation_without_reentering_writer(monkeypatch):
    row = seed()
    incoming = parsed(row, facts(row))
    preview, _ = report(row, incoming)
    deliver(row, incoming, preview)
    confirmation = callback(row, preview)
    original_readback = runtime.load_litter_readback
    calls = 0
    def fail_after_commit(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("Synthetic interruption after farm commit")
        return original_readback(*args, **kwargs)
    monkeypatch.setattr(runtime, "load_litter_readback", fail_after_commit)
    interrupted, code = confirm(row, confirmation)
    assert code == 503 and interrupted["recovery_required"] is True
    before = farm_snapshot(row)
    assert len(before["litters"]) == 1 and len(before["piglets"]) == 8
    monkeypatch.setattr(runtime, "load_litter_readback", original_readback)
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Postcommit recovery must be read-only")
    monkeypatch.setattr(runtime, "create_governed_farrowing_litter", forbidden)
    recovered, code = confirm(row, confirmation)
    assert code == 200 and recovered["canonical_readback_verified"] is True, recovered
    assert recovered["writes_farm_data"] is False and farm_snapshot(row) == before


def test_incomplete_correction_retires_old_callback_then_latest_preview_saves_once():
    row = seed()
    initial = parsed(row, facts(row))
    preview, _ = report(row, initial)
    deliver(row, initial, preview)
    correction = parsed(row, {"born_alive": 9}, provider="2", continuation=True, reply=row["card"])
    question, code = report(row, correction)
    assert code == 200 and question["status"] == "litter_count_arithmetic_conflict"
    stale, code = confirm(row, callback(row, preview, provider="101"))
    assert code == 200 and stale["status"] == "protected_preview_change_requested"
    assert stale["writes_farm_data"] is False
    assert not farm_snapshot(row)["litters"]
    latest, code = report(row, parsed(row, {"total_born": 10}, provider="3", continuation=True, reply=row["card"]))
    assert code == 200 and latest["status"] == "farrowing_litter_preview_ready"
    assert latest["callback_token"] != preview["callback_token"]
    assert bind_claim_card(latest["callback_token"], row["card"], connect_factory=connect)
    saved, code = confirm(row, callback(row, latest, provider="102"))
    assert code == 201 and saved["success"] is True
    after = farm_snapshot(row)
    assert len(after["litters"]) == 1 and after["litters"][0][1:3] == (10, 9)
    assert len(after["piglets"]) == 9


def test_concurrent_delivery_of_same_source_message_retains_one_claim_and_one_turn():
    row = seed()
    incoming = parsed(row, facts(row))
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: report(row, deepcopy(incoming)), range(2)))
    assert all(code == 200 for _, code in outcomes), outcomes
    assert outcomes[0][0]["callback_token"] == outcomes[1][0]["callback_token"]
    with connect() as db:
        turns = db.execute("select count(*) from public.sam_live_stock_conversation_review_events where event_source=%s and chatwoot_conversation_id=%s", (EVENT_SOURCE, row["actor"])).fetchone()[0]
    assert turns == 1 and claim_count(row) == 1 and not farm_snapshot(row)["litters"]


def test_retained_receipt_failure_rolls_back_claim_and_retry_is_clean(monkeypatch):
    row = seed()
    incoming = parsed(row, facts(row))
    original_save = _FarrowingTransaction.save
    def interrupted(self, receipt):
        original_save(self, receipt)
        raise RuntimeError("Synthetic interruption after event insert before commit")
    monkeypatch.setattr(_FarrowingTransaction, "save", interrupted)
    held, code = report(row, incoming)
    assert code == 503 and held["writes_farm_data"] is False and claim_count(row) == 0
    with connect() as db:
        assert db.execute("select count(*) from public.sam_live_stock_conversation_review_events where event_source=%s and chatwoot_conversation_id=%s", (EVENT_SOURCE, row["actor"])).fetchone()[0] == 0
    monkeypatch.setattr(_FarrowingTransaction, "save", original_save)
    ready, code = report(row, incoming)
    assert code == 200 and ready["status"] == "farrowing_litter_preview_ready" and claim_count(row) == 1
