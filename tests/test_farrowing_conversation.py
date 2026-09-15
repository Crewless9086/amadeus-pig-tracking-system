from copy import deepcopy
from datetime import timedelta

import pytest

from modules.oom_sakkie import herdmaster_farrowing_runtime as runtime
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
from modules.pig_weights.herdmaster_farrowing_litter_intake import ACTION_KIND, prepare_farrowing_litter_preview
from tests.farrowing_conversation_test_support import (
    STAMP, MemoryFarrowingStore, canonical, complete_facts, message, saved_readback,
)


def turn(store, parsed, evidence=None, authority=None, **kwargs):
    return runtime.handle_farrowing_litter_message(parsed,
        authority or issue_gateway_owner_authority("42", "42"), context_store=store,
        evidence_loader=lambda **_: evidence or canonical(), claim_creator=store.create_claim,
        now=STAMP + timedelta(minutes=2), **kwargs)


def test_short_date_reply_keeps_counts_and_immediately_builds_exact_preview():
    store = MemoryFarrowingStore()
    first = complete_facts(farrowing_date=None)
    question, code = turn(store, message(first))
    assert code == 200 and question["question_count"] == 1
    assert question["answer"] == "On what date did she actually give birth?"
    assert not store.claims
    context = runtime.load_farrowing_context(message({}, provider=2, seconds=1), context_store=store)
    assert context["facts"]["total_born"] == 9 and context["question"] == question["answer"]
    ready, code = turn(store, message({"farrowing_date": "2026-08-22", "total_born": None},
        provider=2, seconds=1, continuation=True, text="22 August"))
    assert code == 200 and ready["status"] == "farrowing_litter_preview_ready"
    assert ready["question_count"] == 0 and ready["retained_facts"]["born_alive"] == 8
    assert "Linda (SOW-LINDA)" in ready["answer"]
    assert len(store.claims) == 1 and ready["writes_farm_data"] is False


def test_only_next_missing_count_is_asked_and_zero_is_retained():
    store = MemoryFarrowingStore()
    first, _ = turn(store, message({"sow_ref": "Linda", "farrowing_date": "2026-08-22", "mummified": 0}))
    assert first["answer"] == "How many piglets were born in total?"
    second, _ = turn(store, message({"total_born": 8}, provider=2, seconds=1, continuation=True))
    assert second["answer"] == "How many were born alive?"
    third, _ = turn(store, message({"born_alive": 8}, provider=3, seconds=2, continuation=True))
    assert third["status"] == "farrowing_litter_preview_ready"
    assert third["retained_facts"]["mummified"] == 0


def test_exact_provider_replay_reuses_original_question_and_preview():
    store = MemoryFarrowingStore()
    incomplete = message(complete_facts(farrowing_date=None))
    first = turn(store, incomplete)
    assert turn(store, incomplete) == first and len(store.receipts) == 1
    complete = message({"farrowing_date": "2026-08-22"}, provider=2, seconds=1, continuation=True)
    preview = turn(store, complete)
    assert turn(store, complete) == preview
    assert len(store.receipts) == 2 and len(store.claims) == 1
    changed = deepcopy(complete)
    changed["text"] = "Actually 23 August"
    rejected, code = turn(store, changed)
    assert code == 409 and rejected["status"] == "farrowing_provider_replay_conflict"
    assert len(store.receipts) == 2 and len(store.claims) == 1


def test_correction_retires_previous_preview_even_when_it_needs_another_fact():
    store = MemoryFarrowingStore()
    initial, _ = turn(store, message(complete_facts()))
    old = initial["callback_token"]
    held, code = turn(store, message({"born_alive": 9}, provider=2, seconds=1, continuation=True))
    assert code == 200 and held["question_count"] == 1
    assert held["status"] == "litter_count_arithmetic_conflict"
    assert store.claims[old]["status"] == "changed"
    latest, code = turn(store, message({"total_born": 10}, provider=3, seconds=2, continuation=True))
    assert code == 200 and latest["callback_token"] != old
    assert latest["retained_facts"]["born_alive"] == 9
    stale, code = turn(store, message(complete_facts()))
    assert code == 409 and stale["status"] == "farrowing_preview_superseded"


def test_two_sow_contexts_require_identity_and_a_foreign_card_cannot_bind():
    store = MemoryFarrowingStore()
    linda, _ = turn(store, message(complete_facts(farrowing_date=None)))
    bonnie, _ = turn(store, message(complete_facts(sow_ref="Bonnie", farrowing_date=None), provider=2, seconds=1))
    store.cards[linda["mission_id"]] = ["7001"]
    store.cards[bonnie["mission_id"]] = ["7002"]
    ambiguous, code = turn(store, message({"farrowing_date": "2026-08-22"}, provider=3, seconds=2, continuation=True))
    assert code == 409 and ambiguous["status"] == "farrowing_context_ambiguous"
    wrong, code = turn(store, message({"farrowing_date": "2026-08-22"}, provider=4, seconds=3, continuation=True, reply="other"))
    assert code == 409 and wrong["status"] == "farrowing_reply_context_mismatch"
    selected, code = turn(store, message({"farrowing_date": "2026-08-22"}, provider=5, seconds=4, continuation=True, reply="7002"))
    assert code == 200 and "Bonnie (SOW-BONNIE)" in selected["answer"]
    assert selected["retained_facts"]["sow_ref"] == "Bonnie"


def test_source_chronology_prevents_late_reply_from_replacing_new_facts():
    store = MemoryFarrowingStore()
    turn(store, message(complete_facts(farrowing_date=None), seconds=20))
    late, code = turn(store, message({"farrowing_date": "2026-08-21"}, provider=2, seconds=10, continuation=True))
    assert code == 409 and late["status"] == "farrowing_out_of_order"
    assert len(store.receipts) == 1 and not store.claims
    stale = message({"farrowing_date": "2026-08-21"}, provider=3, continuation=True)
    stale["provider_timestamp"] = (STAMP - timedelta(hours=7)).isoformat()
    assert turn(store, stale)[0]["status"] == "farrowing_provider_identity_required"


def test_wrong_owner_or_nonprivate_actor_is_rejected_before_store_access():
    class NoStore:
        def create_claim(self, **_):
            raise AssertionError("Unauthenticated claim creation")
        def locked(self, *_):
            raise AssertionError("Unauthenticated store access")
    for changes, authority in (({}, issue_gateway_owner_authority("7", "7")),
                               ({"telegram_chat_id": "99"}, issue_gateway_owner_authority("42", "42"))):
        parsed = {**message(complete_facts()), **changes}
        result, code = turn(NoStore(), parsed, authority=authority)
        assert code == 403 and result["status"] == "farrowing_owner_authority_required"


def test_receipt_failure_rolls_back_the_new_preview_claim_and_retry_recovers():
    store = MemoryFarrowingStore()
    store.fail_save = True
    failed, code = turn(store, message(complete_facts()))
    assert code == 503 and failed["writes_farm_data"] is False
    assert not store.receipts and not store.claims
    store.fail_save = False
    ready, code = turn(store, message(complete_facts()))
    assert code == 200 and ready["callback_token"] and len(store.claims) == 1


def test_prior_confirmed_linda_counts_are_explained_without_new_claim_or_overwrite():
    store = MemoryFarrowingStore()
    saved = {"litter_id": "LIT-SAVED", "sow_pig_id": "SOW-LINDA", "farrowing_date": "2026-08-22",
             "total_born": 9, "born_alive": 8, "stillborn_count": 0, "mummified_count": 1}
    evidence = canonical(litters=[saved])
    before = deepcopy(evidence)
    result, code = turn(store, message(complete_facts(total_born=8, born_alive=7)), evidence)
    assert code == 409 and result["status"] == "canonical_litter_count_conflict"
    assert "Linda (SOW-LINDA)" in result["answer"]
    assert "total 9, born alive 8" in result["answer"] and "total 8, born alive 7" in result["answer"]
    assert "unchanged" in result["answer"] and result["question_count"] == 0
    assert evidence == before and not store.claims and result["writes_farm_data"] is False


def test_already_saved_litter_does_not_ask_for_counts_again():
    store = MemoryFarrowingStore()
    saved = {"litter_id": "LIT-SAVED", "sow_pig_id": "SOW-LINDA", "farrowing_date": "2026-08-22",
             "total_born": 9, "born_alive": 8, "stillborn_count": 0, "mummified_count": 1}
    result, code = turn(store, message({"sow_ref": "Linda", "farrowing_date": "2026-08-22"}), canonical(litters=[saved]))
    assert code == 409 and result["status"] == "canonical_litter_already_exists"
    assert result["question_count"] == 0 and "total 9" in result["answer"]


def test_explicit_saved_correction_gets_new_context_and_retains_original_completion():
    store = MemoryFarrowingStore()
    ready, _ = turn(store, message(complete_facts()))
    old = store.claims[ready["callback_token"]]
    old.update(status="completed", result={"success": True, "litter_id": "LIT-SAVED"})
    saved = {"litter_id": "LIT-SAVED", "sow_pig_id": "SOW-LINDA", "farrowing_date": "2026-08-22",
             "total_born": 9, "born_alive": 8, "stillborn_count": 0, "mummified_count": 1}
    evidence = canonical(litters=[saved])
    reason, _ = turn(store, message({"correction_of_litter_id": "LIT-SAVED", "total_born": 10, "born_alive": 9},
        provider=2, seconds=1, continuation=True), evidence)
    assert reason["status"] == "litter_correction_reason_required" and reason["question_count"] == 1
    assert reason["mission_id"] != ready["mission_id"] and old["status"] == "completed"
    corrected, _ = turn(store, message({"correction_reason": "I recounted the piglets"},
        provider=3, seconds=2, continuation=True), evidence)
    assert corrected["status"] == "farrowing_litter_preview_ready"
    assert corrected["retained_facts"]["total_born"] == 10
    assert old["status"] == "completed"


def test_relative_birth_date_is_retained_across_midnight_and_afrikaans_question_is_specific():
    store = MemoryFarrowingStore()
    first = message({"sow_ref": "Linda", "farrowing_date": "today", "mummified": 1}, language="af")
    first["provider_timestamp"] = "2026-08-22T23:59:00+02:00"
    clock = STAMP.replace(hour=23, minute=59) + timedelta(minutes=2)
    ask, _ = runtime.handle_farrowing_litter_message(first, issue_gateway_owner_authority("42", "42"),
        context_store=store, evidence_loader=lambda **_: canonical(), claim_creator=store.create_claim, now=clock)
    assert ask["answer"] == "Hoeveel varkies is altesaam gebore?"
    second = message({"total_born": 9, "born_alive": 8}, provider=2, continuation=True, language="af")
    second["provider_timestamp"] = "2026-08-23T00:00:00+02:00"
    ready, _ = runtime.handle_farrowing_litter_message(second, issue_gateway_owner_authority("42", "42"),
        context_store=store, evidence_loader=lambda **_: canonical(), claim_creator=store.create_claim, now=clock)
    assert ready["retained_facts"]["farrowing_date"] == "2026-08-22"
    assert ready["recipient_language"] == "af" and ready["question_count"] == 0


def test_semantic_confirmation_or_uncertainty_cannot_mint_a_recording_claim():
    store = MemoryFarrowingStore()
    confirmation = message(complete_facts())
    confirmation["semantic"]["message_kind"] = "confirmation"
    assert turn(store, confirmation)[0]["status"] == "farrowing_exact_preview_required"
    uncertain = message(complete_facts(), provider=2, seconds=1)
    uncertain["semantic"]["needs_clarification"] = True
    result, _ = turn(store, uncertain)
    assert result["status"] == "farrowing_meaning_uncertain" and result["question_count"] == 1
    assert not store.claims


def prepared():
    result = prepare_farrowing_litter_preview({"authenticated": True, "authenticated_principal_id": "42",
        "provider_message_id": "1", "farrowing_litter": complete_facts()}, canonical())
    preview = result["preview"]
    return {"preview_payload": preview, "preview_digest": canonical_preview_digest(ACTION_KIND, preview)}


def test_postcommit_recovery_reads_exact_saved_operation_without_reentering_writer(monkeypatch):
    claim = prepared()
    record = saved_readback(claim["preview_payload"])
    monkeypatch.setattr(runtime, "load_litter_readback", lambda *_args, **_kwargs: record)
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Recovery must not recompose or write")
    monkeypatch.setattr(runtime, "load_canonical_farrowing_evidence", forbidden)
    monkeypatch.setattr(runtime, "create_governed_farrowing_litter", forbidden)
    recovered, code = runtime.execute_claimed_farrowing_litter(claim, {"telegram_user_id": "42"})
    assert code == 200 and recovered["status"] == "farrowing_litter_replayed_noop"
    assert recovered["canonical_readback_verified"] is True and recovered["writes_farm_data"] is False


@pytest.mark.parametrize("changed", [
    {"mummified_count": 2}, {"born_alive": 7}, {"pig_ids": []},
    {"follow_up_case_id": None}, {"sow_pig_id": "OTHER"}, {"boar_pig_id": "OTHER"},
])
def test_incomplete_or_conflicting_saved_readback_is_never_called_complete(monkeypatch, changed):
    claim = prepared()
    record = {**saved_readback(claim["preview_payload"]), **changed}
    monkeypatch.setattr(runtime, "load_litter_readback", lambda *_args, **_kwargs: record)
    result, code = runtime.execute_claimed_farrowing_litter(claim, {"telegram_user_id": "42"})
    assert code == 503 and result["recovery_required"] is True and result["writes_farm_data"] is False


def test_claim_actor_and_digest_are_checked_before_any_canonical_read(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("No canonical read before bound actor validation")
    monkeypatch.setattr(runtime, "load_litter_readback", forbidden)
    for claim, actor in ((prepared(), "99"), ({**prepared(), "preview_digest": "changed"}, "42")):
        result, code = runtime.execute_claimed_farrowing_litter(claim, {"telegram_user_id": actor})
        assert code == 409 and result["status"] == "farrowing_claim_binding_mismatch"


def test_completed_initial_message_replay_resets_all_new_write_indicators():
    store = MemoryFarrowingStore()
    incoming = message(complete_facts())
    preview, _ = turn(store, incoming)
    store.claims[preview["callback_token"]].update(status="completed", result={
        "success": True, "writes_farm_data": True, "protected_actions_performed": True,
        "rows_created": 9, "answer": "Saved once", "litter_id": "LIT-SAVED"})
    replay, code = turn(store, incoming)
    assert code == 200 and replay["writes_farm_data"] is False
    assert replay["protected_actions_performed"] is False and replay["rows_created"] == 0
    assert replay["suppress_owner_delivery"] is True and len(store.receipts) == 1


def test_initial_request_without_typed_details_retains_its_one_sow_question():
    store = MemoryFarrowingStore()
    ask, code = turn(store, message(None))
    assert code == 200 and ask["question_count"] == 1 and ask["retained_facts"] == {}
    next_question, code = turn(store, message({"sow_ref": "Linda"}, provider=2, seconds=1, continuation=True))
    assert code == 200 and next_question["answer"] == "On what date did she actually give birth?"
    assert len(store.receipts) == 2 and not store.claims


def test_completed_context_exposes_exact_retained_saved_litter_for_an_explicit_correction():
    store = MemoryFarrowingStore()
    ready, _ = turn(store, message(complete_facts()))
    claim = store.claims[ready["callback_token"]]
    readback = saved_readback(claim["preview_payload"])
    claim.update(status="completed", result={"canonical_readback_verified": True,
                                              "canonical_readback": readback})
    context = runtime.load_farrowing_context(message({}, provider=2, seconds=1), context_store=store)
    assert context["canonical_litters_source"] == "retained_confirmed_result"
    assert context["canonical_litters"][0]["litter_id"] == readback["litter_id"]
    assert context["canonical_litters"][0]["born_alive"] == 8


def test_explicit_correction_reason_reuses_known_counts_and_unique_saved_litter():
    store = MemoryFarrowingStore()
    saved = {"litter_id": "LIT-SAVED", "sow_pig_id": "SOW-LINDA", "farrowing_date": "2026-08-22",
             "total_born": 9, "born_alive": 8, "stillborn_count": 0, "mummified_count": 1}
    evidence = canonical(litters=[saved])
    held, _ = turn(store, message(complete_facts(total_born=8, born_alive=7)), evidence)
    assert "tell me why" in held["answer"] and not store.claims
    ordinary = message({"correction_reason": "I miscounted"}, provider=2, seconds=1, continuation=True)
    ordinary["semantic"]["message_kind"] = "observation"
    still_held, _ = turn(store, ordinary, evidence)
    assert still_held["status"] == "canonical_litter_count_conflict" and not store.claims
    ready, code = turn(store, message({"correction_reason": "Please correct it; I recounted"},
        provider=3, seconds=2, continuation=True), evidence)
    assert code == 200 and ready["status"] == "farrowing_litter_preview_ready"
    assert ready["retained_facts"]["correction_of_litter_id"] == "LIT-SAVED"
    assert ready["retained_facts"]["total_born"] == 8 and ready["retained_facts"]["born_alive"] == 7
