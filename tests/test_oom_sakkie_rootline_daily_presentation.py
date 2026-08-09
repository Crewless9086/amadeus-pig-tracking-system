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
    assert "<b>B Camp:</b> Hold" in text and "<b>C Camp:</b> Hold" in text
    assert "Observed rain supports Hold" in text
    assert "SOC" not in text and "solar" not in text.casefold() and "grid" not in text.casefold()
    assert "No action required from you" in text and "<b>What I need from you:</b> Nothing" in text


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
            return {"success": False, "status": "provider_rejected_before_send", "telegram_sends": 0}
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


def test_started_completed_and_intervention_are_separate_visible_event_words():
    source = __import__("inspect").getsource(
        __import__("modules.oom_sakkie.telegram_gateway", fromlist=["handle_rootline_reassessment_trigger"]))
    assert "Started" in source and "Completed" in source and "Intervention" in source
    assert "automatic segment two" not in compose_daily_rootline_plan(result())
