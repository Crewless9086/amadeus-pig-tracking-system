import hashlib
import json
from datetime import datetime, timezone

from modules.oom_sakkie.family_access import resolve_family_principal
from modules.oom_sakkie.riversdale_auction_manager import (
    build_anton_prompt, build_owner_cohort_prompt, collect_auction_manager_case,
    execute_owner_cohort_claim, handle_anton_callback, handle_anton_date_reply,
    reminder_window,
)


NOW = datetime(2026, 8, 21, 8, tzinfo=timezone.utc)


def environment():
    owner = "100"
    anton = "200"
    binding = {"telegram_user_id": anton, "role": "farm_manager", "family_key": "dad",
        "permissions": ["herdmaster_management_input"], "summary_domains": ["herd"],
        "authorization_id": "AUTH-ANTON", "authorized_by_user_id": owner,
        "authorized_at": "2026-08-15T08:00:00+00:00", "language": "af"}
    return {"OOM_SAKKIE_TELEGRAM_OWNER_USER_ID": owner,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": f"{owner},{anton}",
        "OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON": json.dumps([binding])}


def recommendation(**_kwargs):
    eligible = {"withdrawal_clear": "yes", "observed_quality": "suitable",
        "health_status": "healthy", "medical_status": "clear"}
    return {"candidate_preview": [
        {"pig_id": "P1", "herdmaster_evidence": eligible},
        {"pig_id": "P2", "herdmaster_evidence": {}}],
        "excluded_preview": [{"pig_id": "P3", "reason": "health hold"}],
        "evidence_digest": "a" * 64}


def no_cycle(**_kwargs):
    return {"valid": False, "status": "no_owner_confirmed_cycle"}


def test_missed_14_day_window_recovers_once_without_fanning_out_old_prompts():
    assert reminder_window(NOW) == {"auction_date": "2026-09-02", "days_before": 14,
        "due_date": "2026-08-19", "late": True, "observed_date": "2026-08-21"}
    rows = collect_auction_manager_case(NOW, cycle_loader=no_cycle,
        recommendation_loader=recommendation)
    assert len(rows) == 1
    assert rows[0]["dedupe_key"] == "herdmaster:riversdale-auction:2026-09-02"
    assert "reminder_phase:14-day" in rows[0]["evidence_refs"]
    assert "1 tans geskik, Onbekend geprojekteer, 1 uitgesluit" in rows[0]["summary"]
    assert "projected_cohort_evidence" in rows[0]["unknowns"]


def test_after_second_window_only_latest_phase_is_projected():
    rows = collect_auction_manager_case(
        datetime(2026, 8, 27, 8, tzinfo=timezone.utc), cycle_loader=no_cycle,
        recommendation_loader=recommendation)
    assert len(rows) == 1
    assert "reminder_phase:7-day" in rows[0]["evidence_refs"]
    assert "reminder_phase:14-day" not in rows[0]["evidence_refs"]


def test_confirmed_current_cycle_suppresses_prompt():
    def packet(**_):
        return {**recommendation(), "confirmation": {"auction_cycle_id": "C1"}}
    rows = collect_auction_manager_case(NOW,
        cycle_loader=lambda **_: {"valid": True, "confirmed_date": "2026-09-02"},
        recommendation_loader=packet,
        list_loader=lambda: ({"auction_cycle_id": "C1",
            "items": [{"pig_id": "P1"}],
            "causal_heads": {}}, 200))
    assert rows == []


def test_prompt_is_bound_to_anton_and_has_three_concise_options():
    case = collect_auction_manager_case(NOW, cycle_loader=no_cycle,
        recommendation_loader=recommendation)[0]
    result = build_anton_prompt(case, environ=environment())
    assert result["success"] is True
    assert result["principal"].telegram_user_id == "200"
    buttons = result["reply_markup"]["inline_keyboard"][0]
    assert [button["text"] for button in buttons] == ["Ja, dié datum", "Nee", "Datum verskil"]
    assert all(len(button["callback_data"].encode()) <= 64 for button in buttons)
    assert "Geen varke" in result["answer"]


def parsed(user="200", callback="cb-1"):
    return {"telegram_user_id": user, "telegram_chat_id": user,
        "telegram_chat_type": "private", "provider_message_id": callback,
        "provider_timestamp": "2026-08-21T08:00:00+00:00", "callback_query_id": callback,
        "text": ""}


def principal(user="200"):
    return resolve_family_principal(parsed(user), environment())


def test_yes_records_one_stable_cycle_decision_but_never_adds_animals():
    calls = []
    def writer(payload, *, actor_id):
        calls.append((payload, actor_id))
        return {"success": True, "status": "auction_decision_recorded",
            "writes_auction_decision": True}, 201
    result, status = handle_anton_callback(parsed(), principal(),
        callback_data="oomauction:2026-09-02:14-day:yes", decision_writer=writer, now=NOW)
    assert status == 201 and result["success"] is True
    assert calls[0][0]["idempotency_key"] == "riversdale-auction:2026-09-02:14-day:anton-confirmation"
    assert calls[0][0]["confirmed_date"] == "2026-09-02"
    assert calls[0][1] == "200"
    assert "Veilingslys" in result["answer"]
    assert result["hardware_commands"] == 0


def test_wrong_identity_stale_date_and_date_change_fail_closed():
    unknown = resolve_family_principal(parsed("999"), environment())
    denied, status = handle_anton_callback(parsed("999"), unknown,
        callback_data="oomauction:2026-09-02:14-day:yes", decision_writer=lambda *_a, **_k: None,
        now=NOW)
    assert status == 403 and denied["writes_farm_data"] is False
    stale, status = handle_anton_callback(parsed(), principal(),
        callback_data="oomauction:2026-10-07:14-day:yes", decision_writer=lambda *_a, **_k: None,
        now=NOW)
    assert status == 409 and stale["writes_farm_data"] is False
    changed, status = handle_anton_callback(parsed(), principal(),
        callback_data="oomauction:2026-09-02:14-day:change",
        decision_writer=lambda payload, **_: ({"success": True,
            "status": "auction_decision_recorded", "writes_auction_decision": True}, 201),
        now=NOW)
    assert status == 201 and changed["writes_farm_data"] is True
    assert "korrekte" in changed["answer"]


def test_no_can_be_revised_at_later_window_without_idempotency_collision():
    calls = []
    writer = lambda payload, **kwargs: (calls.append(payload) or
        ({"success": True, "status": "auction_decision_recorded",
          "writes_auction_decision": True}, 201))
    no_result, _ = handle_anton_callback(parsed("200", "cb-no"), principal(),
        callback_data="oomauction:2026-09-02:14-day:no", decision_writer=writer, now=NOW)
    yes_result, _ = handle_anton_callback(parsed("200", "cb-yes"), principal(),
        callback_data="oomauction:2026-09-02:7-day:yes", decision_writer=writer,
        now=datetime(2026, 8, 26, 8, tzinfo=timezone.utc))
    assert no_result["success"] and yes_result["success"]
    assert calls[0]["idempotency_key"] != calls[1]["idempotency_key"]


def test_identical_callback_replay_is_silent_and_zero_write():
    result, status = handle_anton_callback(parsed(), principal(),
        callback_data="oomauction:2026-09-02:14-day:yes",
        decision_writer=lambda *_a, **_k: ({"success": True,
            "status": "auction_decision_replayed", "writes_auction_decision": False}, 200),
        now=NOW)
    assert status == 200
    assert result["status"] == "auction_callback_replayed_noop"
    assert result["answer"] == ""
    assert result["suppress_owner_delivery"] is True
    assert result["writes_farm_data"] is False


def test_pending_date_correction_is_completed_by_next_authenticated_reply():
    calls = []
    result, status = handle_anton_date_reply(
        {**parsed(), "text": "Dit is 09-09-2026"}, principal(),
        cycle_loader=lambda: {"owner_note": "PENDING_DATE_CORRECTION:2026-09-02:14-day"},
        decision_writer=lambda payload, **kwargs: (calls.append((payload, kwargs)) or
            ({"success": True, "status": "auction_decision_recorded",
              "writes_auction_decision": True}, 201)))
    assert status == 201 and result["success"] is True
    assert calls[0][0]["confirmed_date"] == "2026-09-09"
    assert calls[0][1]["actor_id"] == "200"


def test_date_reply_without_pending_context_is_not_intercepted():
    result, status = handle_anton_date_reply({**parsed(), "text": "09-09-2026"}, principal(),
        cycle_loader=lambda: {"owner_note": "ordinary decision"})
    assert status == 200 and result["handled"] is False


def eligible_packet(**_):
    evidence = {"withdrawal_clear": "yes", "observed_quality": "suitable",
        "health_status": "healthy", "medical_status": "clear"}
    return {"confirmation": {"auction_cycle_id": "C1"},
        "candidate_preview": [{"pig_id": "P1", "herdmaster_evidence": evidence}],
        "coordination_evidence": {"source": "canonical"}}


def current_list():
    from modules.sales.riversdale_auction_list import eligibility_tokens
    tokens = eligibility_tokens(eligible_packet())
    return ({"auction_cycle_id": "C1", "items": [], "causal_heads": {},
             "eligibility_tokens": tokens}, 200)


def test_exact_cohort_card_is_owner_protected_and_execution_rechecks_evidence():
    case = {"case_id": "OOM-CASE-X", "generation": 2}
    claims = []
    def create(**kwargs):
        claims.append(kwargs)
        return {"callback_token": "TOKEN", "preview_digest": "d" * 64}
    prepared = build_owner_cohort_prompt(case, environ=environment(),
        recommendation_loader=eligible_packet, list_loader=current_list,
        claim_creator=create)
    assert prepared["success"] is True
    assert claims[0]["action_kind"] == "riversdale_auction_list_add"
    assert claims[0]["owner_user_id"] == "100"
    assert claims[0]["preview_payload"]["pig_ids"] == ["P1"]
    writes = []
    claimed = {"preview_payload": claims[0]["preview_payload"]}
    result, status = execute_owner_cohort_claim(claimed, actor_id="100",
        list_loader=current_list,
        list_writer=lambda payload, **kwargs: (writes.append((payload, kwargs)) or
            ({"success": True, "status": "auction_list_updated"}, 201)))
    assert status == 201 and result["writes_farm_data"] is True
    assert writes[0][0]["pig_ids"] == ["P1"]


def test_exact_cohort_change_is_contained_before_append():
    from modules.sales.riversdale_auction_list import eligibility_tokens
    tokens = eligibility_tokens(eligible_packet())
    preview = {"contract_version": "riversdale_auction_manager_cohort.v1",
        "auction_cycle_id": "C1", "pig_ids": ["P1"], "eligibility_tokens": tokens,
        "prior_event_ids": {"P1": ""}, "cohort_digest": "wrong"}
    result, status = execute_owner_cohort_claim({"preview_payload": preview}, actor_id="100",
        list_loader=current_list, list_writer=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError()))
    assert status == 409 and result["writes_farm_data"] is False


def test_exact_cohort_claim_contains_only_newly_eligible_animals():
    packet = eligible_packet()
    packet["candidate_preview"].append({"pig_id": "P2",
        "herdmaster_evidence": packet["candidate_preview"][0]["herdmaster_evidence"]})
    from modules.sales.riversdale_auction_list import eligibility_tokens
    tokens = eligibility_tokens(packet)
    listing = ({"auction_cycle_id": "C1", "items": [{"pig_id": "P1"}],
        "causal_heads": {"P1": {"event_id": "E1"}},
        "eligibility_tokens": tokens}, 200)
    claims = []
    prepared = build_owner_cohort_prompt({"case_id": "OOM-CASE-X", "generation": 3},
        environ=environment(), recommendation_loader=lambda **_: packet,
        list_loader=lambda: listing,
        claim_creator=lambda **kwargs: (claims.append(kwargs) or
            {"callback_token": "TOKEN", "preview_digest": "d" * 64}))
    assert prepared["success"] is True
    assert claims[0]["preview_payload"]["pig_ids"] == ["P2"]
    writes = []
    result, status = execute_owner_cohort_claim(
        {"preview_payload": claims[0]["preview_payload"]}, actor_id="100",
        list_loader=lambda: listing,
        list_writer=lambda payload, **kwargs: (writes.append((payload, kwargs)) or
            ({"success": True, "status": "auction_list_updated"}, 201)))
    assert status == 201 and result["success"] is True
    assert writes[0][0]["pig_ids"] == ["P2"]
    assert set(writes[0][0]["eligibility_tokens"]) == {"P2"}
