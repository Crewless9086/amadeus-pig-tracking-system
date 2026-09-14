"""Offline synthetic cancellation and correction-context gaps on actual protected claims."""
from datetime import datetime, timezone
import uuid

import psycopg
import pytest

from modules.oom_sakkie import herdmaster_farrowing_runtime as farrowing
from modules.oom_sakkie import herdmaster_litter_weaning_runtime as weaning
from modules.oom_sakkie import herdmaster_litter_first_treatment_runtime as treatment
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.protected_action_claims import bind_claim_card
from modules.oom_sakkie.protected_action_runtime import handle_protected_action_input
from tests import first_treatment_test_support as treatment_support
from tests import weaning_test_support as weaning_support
from tests import test_farrowing_conversation_postgres as farrowing_support


def connect():
    return psycopg.connect(treatment_support.database_url())


def fixture(kind, actor=None):
    actor = actor or str(8200000000 + int(uuid.uuid4().hex[:8], 16))
    if kind == "farrowing":
        row = farrowing_support.seed()
        row["actor"] = actor
        facts = farrowing_support.facts(row)
        handler, loader = farrowing.handle_farrowing_litter_message, farrowing.load_farrowing_context
        state = lambda: farrowing_support.farm_snapshot(row)
        field, intent, delta = "farrowing_litter", "record_farrowing_litter", {"total_born": 10, "born_alive": 9}
    elif kind == "weaning":
        row = weaning_support.seed()
        facts = {"sow_ref": row["sow"], "action_date": "2026-09-10", "scope": "all_current", "total_count": 2}
        handler, loader = weaning.handle_litter_weaning_message, weaning.load_weaning_context
        state = lambda: weaning_support.state(row)
        field, intent, delta = "litter_weaning", "record_litter_weaning", {"notes": "Offline corrected observation"}
    else:
        row = treatment_support.seed()
        facts = treatment_support.facts(row)
        handler, loader = treatment.handle_litter_first_treatment_message, treatment.load_first_treatment_context
        state = lambda: treatment_support.state(row)
        field, intent, delta = "litter_first_treatment", "record_litter_first_treatment", {"dose": "1.5 ml"}
    return {"row": row, "actor": actor, "facts": facts, "handler": handler, "loader": loader,
            "state": state, "field": field, "intent": intent, "delta": delta,
            "authority": issue_gateway_owner_authority(actor, actor)}


def message(j, provider, supplied, *, continuation=False, reply=""):
    return {"telegram_user_id": j["actor"], "telegram_chat_id": j["actor"],
        "telegram_chat_type": "private", "provider_message_id": str(provider),
        "provider_timestamp": datetime.now(timezone.utc).isoformat(),
        "text": "OFFLINE SYNTHETIC " + str(provider) + " " + str(supplied),
        "reply_to_message_id": reply, "output_language": "en",
        "semantic": {"domain": "herd_management", "intent": j["intent"],
            "confidence": 0.99, "message_kind": "correction" if continuation else "observation",
            "continuation": continuation, j["field"]: supplied}}


def report(j, incoming):
    return j["handler"](incoming, j["authority"], connect_factory=connect)


def preview(j, provider, card):
    result, code = report(j, message(j, provider, j["facts"]))
    assert code == 200 and result.get("callback_token"), result
    assert bind_claim_card(result["callback_token"], card, connect_factory=connect)
    return result


def callback(j, prepared, provider, card, action):
    incoming = message(j, provider, {}, reply=card)
    incoming["callback_data"] = "oompa:" + prepared["callback_token"] + ":" + action
    incoming["text"] = ""
    return handle_protected_action_input(incoming, j["authority"], connect_factory=connect)


def claims(j):
    with connect() as db:
        return dict(db.execute("select callback_token,status from app_private.oom_protected_action_claims where owner_user_id=%s", (j["actor"],)).fetchall())


@pytest.mark.parametrize("kind", ["farrowing", "weaning", "treatment"])
def test_cancelled_card_cannot_seed_short_continuation_but_fresh_report_can_start_again(kind):
    j = fixture(kind)
    prepared = preview(j, 1, "81001")
    before = j["state"]()
    cancelled, code = callback(j, prepared, 2, "81001", "cancel")
    assert code == 200 and cancelled["status"] == "protected_preview_cancelled"
    stale, code = callback(j, prepared, 3, "81001", "confirm")
    assert code == 200 and stale["status"] == "protected_preview_cancelled"
    incoming = message(j, 4, j["delta"], continuation=True)
    context = j["loader"](incoming, connect_factory=connect)
    result, code = report(j, incoming)
    assert not result.get("callback_token"), result
    assert not context or not context.get("facts"), context
    assert claims(j) == {prepared["callback_token"]: "cancelled"}
    assert j["state"]() == before
    restarted = preview(j, 5, "81002")
    assert restarted["mission_id"] != prepared["mission_id"]
    assert claims(j)[prepared["callback_token"]] == "cancelled"
    assert j["state"]() == before
    resumed = j["loader"](message(j, 6, {}, continuation=True), connect_factory=connect)
    assert resumed["context_id"] == restarted["mission_id"]


@pytest.mark.parametrize("kind", ["farrowing", "weaning", "treatment"])
def test_cancellation_winning_after_context_read_prevents_a_replacement_claim(kind, monkeypatch):
    j = fixture(kind)
    prepared = preview(j, 1, "81501")
    before = j["state"]()
    if kind == "farrowing":
        from modules.oom_sakkie.herdmaster_farrowing_conversation import _FarrowingTransaction
        target, name = _FarrowingTransaction, "rows"
    else:
        target, name = (weaning if kind == "weaning" else treatment), "_context_rows"
    original = getattr(target, name)
    def cancelled_after_read(*args, **kwargs):
        rows = original(*args, **kwargs)
        result, code = callback(j, prepared, 3, "81501", "cancel")
        assert code == 200 and result["status"] == "protected_preview_cancelled"
        return rows
    monkeypatch.setattr(target, name, cancelled_after_read)
    result, code = report(j, message(j, 2, j["delta"], continuation=True))
    assert code == 409 and not result.get("callback_token"), result
    assert claims(j) == {prepared["callback_token"]: "cancelled"}
    assert j["state"]() == before


@pytest.mark.parametrize("kind", ["weaning", "treatment"])
def test_correction_reply_uses_its_exact_litter_card_and_preserves_the_other_preview(kind):
    first = fixture(kind)
    second = fixture(kind, first["actor"])
    earlier = preview(first, 1, "82001")
    later = preview(second, 2, "82002")
    before = (first["state"](), second["state"]())
    incoming = message(first, 3, first["delta"], continuation=True, reply="82001")
    revised, code = report(first, incoming)
    assert code == 200 and revised.get("callback_token"), revised
    assert revised["retained_facts"]["sow_ref"] == first["facts"]["sow_ref"], revised
    assert revised["mission_id"] == earlier["mission_id"]
    assert claims(first)[later["callback_token"]] == "active"
    assert (first["state"](), second["state"]()) == before


@pytest.mark.parametrize("kind", ["weaning", "treatment"])
@pytest.mark.parametrize("reply", ["", "unrelated-card"])
def test_ambiguous_or_foreign_correction_context_does_not_select_the_latest_litter(kind, reply):
    first = fixture(kind)
    second = fixture(kind, first["actor"])
    earlier = preview(first, 1, "83001")
    later = preview(second, 2, "83002")
    before = claims(first)
    incoming = message(first, 3, first["delta"], continuation=True, reply=reply)
    revised, code = report(first, incoming)
    assert code == 409 and not revised.get("callback_token"), revised
    assert claims(first) == before == {earlier["callback_token"]: "active", later["callback_token"]: "active"}
