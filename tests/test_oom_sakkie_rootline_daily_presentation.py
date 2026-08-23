from datetime import datetime
from zoneinfo import ZoneInfo

from modules.oom_sakkie.rootline_daily_presentation import (
    compose_daily_rootline_plan, present_daily_rootline_plan,
)

SAST = ZoneInfo("Africa/Johannesburg")


def result(*, cutoff="2026-08-09T06:55:00+02:00", b="Hold", c="Hold", reason="Observed rain supports Hold."):
    return {"success": True, "evidence_cutoff": cutoff, "overall_status": "Hold",
        "recommendations": [
            {"subject": "B12345", "status": b, "reason": reason, "preferred_window": "07:30–08:30 SAST"},
            {"subject": "C12345", "status": c, "reason": reason, "preferred_window": "Unavailable"},
            {"subject": "borehole", "status": "Hold", "reason": "Not authorized."}],
        "owner_brief": {"family_fact_needed": "", "reassess": "At 07:15 SAST or on material evidence."},
        "current_power": {"battery_soc_pct": 2, "solar_power_w": 0, "grid_power_w": 0}}


def store():
    rows = {}
    def use(action, identity, payload):
        if action == "load_identity": return rows.get(identity)
        if action == "claim_pending":
            created = identity not in rows; rows.setdefault(identity, dict(payload)); return {"success": True, "created": created}
        if action.startswith("mark_") or action.startswith("claim_retry_"):
            rows[identity] = {**rows.get(identity, {}), **dict(payload)}; return {"success": True, "created": True}
    return rows, use


def delivery(calls):
    def send(parsed, packet, **kwargs):
        calls.append((parsed, packet, kwargs))
        return {"success": True, "status": "family_message_delivered",
                "telegram_message_id": "5001", "provider_timestamp": "2026-08-09T05:01:00+00:00",
                "telegram_sends": 1, "telegram_edits": 0}
    return send


def test_first_fresh_tick_after_0700_sends_one_daily_plan_and_replay_is_silent():
    rows, state = store(); calls = []; now = datetime(2026, 8, 9, 7, 1, tzinfo=SAST)
    first = present_daily_rootline_plan(owner_user_id="42", chat_id="42", specialist_loader=result,
        state_store=state, deliver=delivery(calls), now=now)
    replay = present_daily_rootline_plan(owner_user_id="42", chat_id="42", specialist_loader=result,
        state_store=state, deliver=delivery(calls), now=now)
    assert first["status"] == "rootline_daily_delivered" and first["telegram_sends"] == 1
    assert replay["status"] == "rootline_daily_replayed_noop" and replay["telegram_sends"] == 0
    assert len(calls) == 1 and len(rows) == 1


def test_delayed_refresh_waits_without_claim_then_sends_when_fresh():
    rows, state = store(); calls = []; now = datetime(2026, 8, 9, 7, 5, tzinfo=SAST)
    waiting = present_daily_rootline_plan(owner_user_id="42", chat_id="42",
        specialist_loader=lambda: result(cutoff="2026-08-09T05:00:00+02:00"),
        state_store=state, deliver=delivery(calls), now=now)
    fresh = present_daily_rootline_plan(owner_user_id="42", chat_id="42",
        specialist_loader=lambda: result(cutoff="2026-08-09T07:04:00+02:00"),
        state_store=state, deliver=delivery(calls), now=now)
    assert waiting["status"] == "rootline_daily_waiting_for_fresh_evidence"
    assert rows and fresh["status"] == "rootline_daily_delivered" and len(calls) == 1


def test_rain_hold_is_clean_and_power_does_not_rank_gravity_fed_zones():
    text = compose_daily_rootline_plan(result())
    assert "<b>B Camp:</b> Not running — does not need watering" in text
    assert "<b>C Camp:</b> Not running — does not need watering" in text
    assert "Lifecycle:" not in text and "ROOTLINE must claim" not in text
    assert "Started: no" not in text and "Completed: no" not in text
    assert "Observed rain supports Hold" in text
    assert "SOC" not in text and "solar" not in text.casefold() and "grid" not in text.casefold()
    assert "No action required from you" in text and "<b>What I need from you:</b> Nothing" in text


def test_recommendation_never_claims_irrigation_executed():
    text = compose_daily_rootline_plan(result(b="Recommend", c="Run"))
    assert "Needs watering" in text
    assert ">Run<" not in text and ":</b> Run" not in text


def test_completed_canonical_lifecycle_never_maps_to_hold():
    value = result(b="Do Not Run", c="Hold")
    value["irrigation_lifecycle"] = {
        "B12345": {"contract_version": "rootline_zone_lifecycle.v1",
                    "zone_id": "B12345", "state": "Completed",
                    "reason": "Verified shutdown and runtime.",
                    "next_action_owner": "ROOTLINE",
                    "next_action": "Reassess at the next governed due time."},
        "C12345": {"contract_version": "rootline_zone_lifecycle.v1",
                    "zone_id": "C12345", "state": "Held",
                    "reason": "Fresh observed rain.",
                    "next_action_owner": "ROOTLINE",
                    "next_action": "Reassess when weather changes."},
    }
    text = compose_daily_rootline_plan(value)
    assert "<b>B Camp:</b> Completed — off and verified" in text
    assert "Lifecycle:" not in text
    assert "B Camp:</b> Not running" not in text


def test_volatile_cutoff_and_formatting_never_change_material_decision_content():
    from modules.oom_sakkie.rootline_reassessment_lifecycle import _material_digest
    a = result(cutoff="2026-08-09T06:55:00+02:00")
    b = {**result(cutoff="2026-08-09T06:56:00+02:00"), "generated_at": "later"}
    assert _material_digest(a) == _material_digest(b)
    reordered = {**b, "overall_status": "  Hold ",
        "recommendations": list(reversed([{**row, "reason": "  " + str(row.get("reason") or "").replace(" ", "   ") + "  "}
                                            for row in b["recommendations"]]))}
    assert _material_digest(a) == _material_digest(reordered)


def test_proven_zero_delivery_failure_retries_once_then_is_silent():
    rows, state = store(); calls = []; now = datetime(2026, 8, 9, 7, 1, tzinfo=SAST)
    def send(parsed, packet, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            return {"success": False, "status": "provider_rejected_before_send", "telegram_sends": 0,
                    "delivery_definitely_not_sent": True}
        return {"success": True, "status": "family_message_delivered",
                "telegram_message_id": "5002", "telegram_sends": 1}
    first = present_daily_rootline_plan(owner_user_id="42", chat_id="42", specialist_loader=result,
        state_store=state, deliver=send, now=now)
    second = present_daily_rootline_plan(owner_user_id="42", chat_id="42", specialist_loader=result,
        state_store=state, deliver=send, now=now)
    replay = present_daily_rootline_plan(owner_user_id="42", chat_id="42", specialist_loader=result,
        state_store=state, deliver=send, now=now)
    assert first["status"] == "rootline_daily_delivery_failed_retryable"
    assert second["status"] == "rootline_daily_delivered" and second["telegram_sends"] == 1
    assert replay["status"] == "rootline_daily_replayed_noop" and len(calls) == 2


def test_contained_or_unknown_delivery_is_ambiguous_and_never_retried():
    for first_shape in (
        {"success": False, "status": "family_message_delivery_contained", "telegram_sends": 0},
        {"success": False, "status": "unexpected_transport_failure", "telegram_sends": 0},
    ):
        rows, state = store(); calls = []; now = datetime(2026, 8, 9, 7, 1, tzinfo=SAST)
        def send(*args, **kwargs):
            calls.append(1); return dict(first_shape)
        first = present_daily_rootline_plan(owner_user_id="42", chat_id="42", specialist_loader=result,
            state_store=state, deliver=send, now=now)
        replay = present_daily_rootline_plan(owner_user_id="42", chat_id="42", specialist_loader=result,
            state_store=state, deliver=send, now=now)
        assert first["status"] == replay["status"] == "rootline_daily_delivery_ambiguous"
        assert len(calls) == 1 and replay["telegram_sends"] == 0


def test_known_zero_retry_executes_through_real_family_delivery_lifecycle_once():
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    daily_rows, daily_state = store(); lifecycle_rows = {}; sender_calls = []
    now = datetime(2026, 8, 9, 7, 1, tzinfo=SAST)
    def event_store(action, identity, payload):
        if action == "load":
            return list(lifecycle_rows.values())
        if action == "record":
            created = identity not in lifecycle_rows
            lifecycle_rows.setdefault(identity, dict(payload)); return {"success": True, "created": created}
    def sender(chat, text):
        sender_calls.append(1)
        if len(sender_calls) == 1:
            return {"success": False, "status": "provider_rejected_before_send",
                    "delivery_definitely_not_sent": True}
        return {"success": True, "telegram_message_id": "5003",
                "provider_timestamp": "2026-08-09T05:16:00+00:00"}
    def real_delivery(parsed, packet, **kwargs):
        return deliver_family_result(parsed, packet, event_store=event_store, sender=sender, **kwargs)
    first = present_daily_rootline_plan(owner_user_id="42", chat_id="42", specialist_loader=result,
        state_store=daily_state, deliver=real_delivery, now=now)
    second = present_daily_rootline_plan(owner_user_id="42", chat_id="42", specialist_loader=result,
        state_store=daily_state, deliver=real_delivery, now=now)
    replay = present_daily_rootline_plan(owner_user_id="42", chat_id="42", specialist_loader=result,
        state_store=daily_state, deliver=real_delivery, now=now)
    assert first["status"] == "rootline_daily_delivery_failed_retryable"
    assert second["status"] == "rootline_daily_delivered"
    assert replay["status"] == "rootline_daily_replayed_noop"
    assert len(sender_calls) == 2
    assert any(key.endswith("-DELIVERY-ATTEMPT") for key in lifecycle_rows)
    assert any(key.endswith("-DELIVERY-RETRY-2") for key in lifecycle_rows)


def test_started_completed_and_intervention_are_separate_visible_event_words():
    source = __import__("inspect").getsource(
        __import__("modules.oom_sakkie.telegram_gateway", fromlist=["handle_rootline_reassessment_trigger"]))
    assert "Started" in source and "Completed" in source and "Intervention" in source
    assert "automatic segment two" not in compose_daily_rootline_plan(result())


def test_live_backend_tokens_are_not_exposed_and_hold_never_claims_eligibility():
    value = result(b="Recommend", c="Hold", reason="now_after_fresh_execution_revalidation")
    value["irrigation_lifecycle"] = {
        "B12345": {"contract_version": "rootline_zone_lifecycle.v1", "zone_id": "B12345",
                    "state": "Eligible", "reason": "now_after_fresh_execution_revalidation",
                    "next_action_owner": "ROOTLINE",
                    "next_action": "ROOTLINE must claim existing canonical execution exactly once"},
        "C12345": {"contract_version": "rootline_zone_lifecycle.v1", "zone_id": "C12345",
                    "state": "Eligible", "reason": "zone_decision_not_run_now",
                    "next_action_owner": "ROOTLINE",
                    "next_action": "ROOTLINE must claim existing canonical execution exactly once"},
    }
    text = compose_daily_rootline_plan(value)
    assert "B Camp:</b> Ready after the final safety check" in text
    assert "C Camp:</b> Ready after the final safety check" in text
    for internal in ("Lifecycle", "Eligible", "now_after", "zone_decision", "claim existing"):
        assert internal not in text


def test_next_check_aware_and_naive_sast_are_not_shifted_twice():
    for timestamp in ("2026-08-23T22:45:15+02:00", "2026-08-23T22:45:15"):
        value = result()
        value["owner_brief"] = {"family_fact_needed": "", "reassess": timestamp}
        text = compose_daily_rootline_plan(value)
        assert "around 22:45" in text
        assert "around 00:45" not in text


def test_validated_started_and_failed_lifecycle_override_conflicting_recommendations_en_af():
    value = result(b="Hold", c="Recommend", reason="now_after_fresh_execution_revalidation")
    value["irrigation_lifecycle"] = {
        "B12345": {"contract_version":"rootline_zone_lifecycle.v1","zone_id":"B12345",
            "state":"Started","reason":"active_execution","next_action_owner":"ROOTLINE",
            "next_action":"verify shutdown"},
        "C12345": {"contract_version":"rootline_zone_lifecycle.v1","zone_id":"C12345",
            "state":"Failed","reason":"contained","next_action_owner":"ROOTLINE",
            "next_action":"reconcile safely"},
    }
    english = compose_daily_rootline_plan(value, language="en")
    afrikaans = compose_daily_rootline_plan(value, language="af")
    assert "B Camp:</b> Currently running" in english
    assert "C Camp:</b> Held safely — problem under automatic review" in english
    assert "B Kamp:</b> Loop tans" in afrikaans
    assert "C Kamp:</b> Veilig teruggehou — probleem word outomaties nagegaan" in afrikaans
    for text in (english, afrikaans):
        assert "active_execution" not in text and "contained" not in text
        assert "Lifecycle" not in text and "Lewensiklus" not in text


def test_every_validated_lifecycle_state_has_human_en_af_projection():
    expected = {
        "Recommended": ("Needs watering", "Moet natgemaak word"),
        "Revalidating": ("Checking safely", "Kontroleer veiligheid"),
        "Eligible": ("Ready after the final safety check", "Gereed na die finale veiligheidskontrole"),
        "Authorized": ("Ready — starting safely", "Gereed — begin veilig"),
        "Started": ("Currently running", "Loop tans"),
        "Completed": ("Completed — off and verified", "Voltooi — af en geverifieer"),
        "Held": ("Not running — does not need watering", "Loop nie — het nie water nodig nie"),
        "Failed": ("Held safely — problem under automatic review",
                   "Veilig teruggehou — probleem word outomaties nagegaan"),
    }
    for state, (en, af) in expected.items():
        value = result(b="Hold", c="Hold")
        value["irrigation_lifecycle"] = {zone: {
            "contract_version":"rootline_zone_lifecycle.v1","zone_id":zone,
            "state":state,"reason":"internal_reason_token","next_action_owner":"ROOTLINE",
            "next_action":"internal_next_action"} for zone in ("B12345","C12345")}
        english = compose_daily_rootline_plan(value, language="en")
        afrikaans = compose_daily_rootline_plan(value, language="af")
        assert en in english and af in afrikaans
        assert "internal_reason_token" not in english + afrikaans
        assert "internal_next_action" not in english + afrikaans
