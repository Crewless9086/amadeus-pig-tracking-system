from datetime import datetime, timedelta, timezone

from scripts.oom_sakkie_morning_cron import run_job


START = datetime(2026, 8, 14, 4, 45, tzinfo=timezone.utc)


def test_one_provider_invocation_retries_recovery_then_presents_once():
    calls = []
    moments = iter((START, START + timedelta(minutes=1)))
    outcomes = iter((
        {"success": False, "status": "morning_runtime_recovery_pending",
         "telegram_sends": 0, "hardware_commands": 0},
        {"success": True, "status": "daily_manager_presented",
         "telegram_sends": 1, "telegram_message_id": "provider-id",
         "hardware_commands": 0},
    ))
    result, code = run_job(cycle=lambda **kw: (calls.append(kw["now"]) or next(outcomes)),
                           now_fn=lambda: next(moments), sleep_fn=lambda seconds: None)
    assert code == 0
    assert result["status"] == "daily_manager_presented"
    assert calls == [START, START + timedelta(minutes=1)]


def test_restart_replay_is_silent_success():
    result, code = run_job(
        cycle=lambda **_: {"success": True, "status": "daily_manager_replay_suppressed",
                           "telegram_sends": 0, "hardware_commands": 0},
        now_fn=lambda: START, sleep_fn=lambda _: None)
    assert code == 0
    assert result["telegram_sends"] == 0


def test_provider_ambiguous_delivery_fails_closed_without_retry():
    calls = []
    result, code = run_job(
        cycle=lambda **_: (calls.append(1) or {
            "success": False, "status": "daily_manager_delivery_ambiguous",
            "telegram_sends": 0, "hardware_commands": 0}),
        now_fn=lambda: START, sleep_fn=lambda _: None)
    assert code == 1
    assert len(calls) == 1
    assert result["hardware_commands"] == 0


def test_success_status_fails_closed_on_authority_or_delivery_violation():
    unsafe = (
        {"status": "daily_manager_presented", "telegram_sends": 2,
         "telegram_message_id": "id", "hardware_commands": 0},
        {"status": "daily_manager_presented", "telegram_sends": 1,
         "telegram_message_id": "id", "hardware_commands": 1},
        {"status": "daily_manager_presented", "telegram_sends": 1,
         "telegram_message_id": "id", "hardware_commands": 0,
         "writes_farm_data": True},
        {"status": "daily_manager_replay_suppressed", "telegram_sends": 1,
         "hardware_commands": 0},
    )
    for outcome in unsafe:
        _, code = run_job(cycle=lambda **_: outcome,
                          now_fn=lambda: START, sleep_fn=lambda _: None)
        assert code == 1


def test_unproven_claim_retries_inside_bounded_window():
    outcomes = iter((
        {"success": False, "status": "daily_manager_claim_unproven",
         "telegram_sends": 0, "hardware_commands": 0},
        {"success": True, "status": "daily_manager_replay_suppressed",
         "telegram_sends": 0, "hardware_commands": 0},
    ))
    moments = iter((START, START + timedelta(minutes=1)))
    result, code = run_job(cycle=lambda **_: next(outcomes),
                           now_fn=lambda: next(moments), sleep_fn=lambda _: None)
    assert code == 0
    assert result["status"] == "daily_manager_replay_suppressed"


def test_explicit_failure_requires_provider_confirmation():
    for confirmed, expected in ((True, 0), (False, 1)):
        _, code = run_job(
            cycle=lambda **_: {"success": False,
                "status": "morning_runtime_failure_escalated",
                "provider_delivery_confirmed": confirmed,
                "telegram_sends": 1 if confirmed else 0,
                "hardware_commands": 0},
            now_fn=lambda: START, sleep_fn=lambda _: None)
        assert code == expected
