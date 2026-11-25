from datetime import datetime, timezone
import pytest
from modules.telemetry.rootline_owner_auxiliary_policy import (
    mixer_owner_capacity_seconds, owner_injection_pulse_limit, validate_auxiliary_control_fields,
)

NOW = datetime(2026, 11, 25, 16, tzinfo=timezone.utc)


def controls(device, **fields):
    return {"devices": {device: {"fields": fields}}}


def test_defaults_preserve_existing_session_and_daily_caps():
    assert mixer_owner_capacity_seconds({"reserved_seconds": 0}, now=NOW) == 600
    assert mixer_owner_capacity_seconds({"reserved_seconds": 1800}, now=NOW) == 0
    assert owner_injection_pulse_limit(now=NOW, existing_limit=2) == 2
    assert owner_injection_pulse_limit(now=NOW, existing_limit=4) == 4


def test_lower_session_and_daily_limit_apply_only_to_remaining_work():
    setting = controls("mixer", session_minutes=3, daily_minutes=5)
    assert mixer_owner_capacity_seconds({"reserved_seconds": 0}, setting, now=NOW) == 180
    assert mixer_owner_capacity_seconds({"reserved_seconds": 250}, setting, now=NOW) == 50
    assert mixer_owner_capacity_seconds({"reserved_seconds": 400}, setting, now=NOW) == 0


def test_known_continuation_remainder_preserved_without_refunding_unknown_time():
    setting = controls("mixer", session_minutes=10, daily_minutes=5)
    accounting = {"reserved_seconds": 600, "known_residual_microseconds": 501_622_881}
    assert mixer_owner_capacity_seconds(accounting, setting, now=NOW) == 201
    assert mixer_owner_capacity_seconds({"reserved_seconds": 600}, setting, now=NOW) == 0
    assert accounting == {"reserved_seconds": 600, "known_residual_microseconds": 501_622_881}


def test_owner_cannot_expand_existing_pulse_ceiling():
    setting = controls("injection", max_pulses_per_run=4)
    assert owner_injection_pulse_limit(setting, now=NOW, existing_limit=2) == 2
    setting = controls("injection", max_pulses_per_run=1)
    assert owner_injection_pulse_limit(setting, now=NOW, existing_limit=4) == 1


@pytest.mark.parametrize("fields", [{"session_minutes":11}, {"daily_minutes":31},
    {"daily_minutes":0}, {"daily_minutes":True}, {"daily_minutes":1.5}, {"daily_minutes":float("inf")}])
def test_invalid_mixer_limits_rejected(fields):
    with pytest.raises(ValueError):
        validate_auxiliary_control_fields("mixer", fields)


def test_malformed_accounting_never_grants_new_time():
    for value in ({}, {"reserved_seconds":float("nan")}, {"reserved_seconds":0,"known_residual_microseconds":1}):
        assert mixer_owner_capacity_seconds(value, now=NOW) == 0
