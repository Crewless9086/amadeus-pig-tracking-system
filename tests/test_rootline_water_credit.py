from datetime import datetime, timezone
from pathlib import Path
import os
import uuid

import pytest

from modules.telemetry.rootline_water_credit import (
    append_water_credit, build_water_credit, read_water_credits, validate_water_credit,
)

NOW = datetime(2026, 8, 15, 15, 30, tzinfo=timezone.utc)
EXECUTION = {"execution_id": "ROOTLINE-EXECUTION-TEST", "zone_id": "B12345",
    "state": "Completed", "verified_runtime_seconds": 3599, "shutdown_verified": True,
    "start_evidence": {"state": "ON"}, "shutdown_evidence": {"state": "OFF"}}
ACCEPTANCE = {"acceptance_sha256": "a" * 64, "observations": [{
    "execution_id": "ROOTLINE-EXECUTION-TEST", "zone_id": "B12345",
    "water_flow": "normal", "stopped_flow": "normal", "physically_off_now": True}]}


def test_runtime_and_owner_flow_alone_keep_litres_unknown():
    value = build_water_credit(execution=EXECUTION, physical_acceptance=ACCEPTANCE,
                               recorded_at=NOW)
    assert value["status"] == "Unknown"
    assert value["delivered_volume_litres"] == "Unknown"
    assert value["writes_farm_data"] is False


def test_verified_measurement_binds_execution_acceptance_and_separate_evidence():
    value = build_water_credit(execution=EXECUTION, physical_acceptance=ACCEPTANCE,
        measurement={"measurement_id": "MEASURE-1", "measured_volume_litres": 1234.5,
                     "verified": True}, recorded_at=NOW)
    assert validate_water_credit(value)
    assert value["delivered_volume_litres"] == 1234.5
    assert value["provider_evidence"]["shutdown_state"] == "OFF"
    assert value["owner_observed_evidence"]["normal_flow"] is True
    assert value["physical_acceptance_sha256"] == "a" * 64


def test_governed_calibration_requires_identity_zone_and_evidence_digest():
    missing = build_water_credit(execution=EXECUTION, physical_acceptance=ACCEPTANCE,
        calibration={"calibration_id": "CAL-1", "litres_per_minute": 10,
                     "zone_id": "B12345", "verified": True}, recorded_at=NOW)
    assert missing["status"] == "Unknown"
    value = build_water_credit(execution=EXECUTION, physical_acceptance=ACCEPTANCE,
        calibration={"calibration_id": "CAL-1", "litres_per_minute": 10,
                     "zone_id": "B12345", "verified": True, "evidence_digest": "b" * 64},
        recorded_at=NOW)
    assert validate_water_credit(value)
    assert value["credit_method"] == "governed_calibration"
    assert value["delivered_volume_litres"] == pytest.approx(599.833)


def test_conflicting_or_unproven_identity_is_unknown():
    for execution, acceptance in [
        ({**EXECUTION, "shutdown_verified": False}, ACCEPTANCE),
        (EXECUTION, {**ACCEPTANCE, "acceptance_sha256": "short"}),
        (EXECUTION, {**ACCEPTANCE, "observations": []}),
    ]:
        result = build_water_credit(execution=execution, physical_acceptance=acceptance,
            measurement={"measurement_id": "M", "measured_volume_litres": 1, "verified": True},
            recorded_at=NOW)
        assert result["status"] == "Unknown" and result["hardware_control"] is False


class FakeDatabase:
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self
    def execute(self, *_args): pass
    def fetchone(self): return [False]


def test_exact_replay_returns_zero_new_credit(monkeypatch):
    import sys, types
    monkeypatch.setitem(sys.modules, "psycopg",
        types.SimpleNamespace(connect=lambda *_args, **_kwargs: FakeDatabase()))
    value = build_water_credit(execution=EXECUTION, physical_acceptance=ACCEPTANCE,
        measurement={"measurement_id": "M", "measured_volume_litres": 1, "verified": True},
        recorded_at=NOW)
    result = append_water_credit(value, "postgres://disposable")
    assert result["status"] == "exact_replay" and result["created"] is False


def test_migration_is_append_only_and_has_no_control_authority():
    sql = (Path(__file__).parents[1] / "supabase" / "migrations" /
           "202608150009_create_rootline_water_credit_lifecycle.sql").read_text().lower()
    assert "before update or delete" in sql
    assert "execution_id text not null unique" in sql
    assert "measured_volume','governed_calibration" in sql
    assert "ifttt" not in sql and "ewelink" not in sql and "n8n" not in sql


@pytest.mark.skipif(not os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL"),
    reason="disposable ROOTLINE PostgreSQL URL is required")
def test_disposable_postgres_one_credit_per_execution_and_conflict():
    import psycopg
    url = os.environ["ROOTLINE_DISPOSABLE_POSTGRES_URL"]
    execution = {**EXECUTION, "execution_id": "ROOTLINE-EXECUTION-" + uuid.uuid4().hex.upper()}
    acceptance = {"acceptance_sha256": uuid.uuid4().hex + uuid.uuid4().hex,
        "observations": [{**ACCEPTANCE["observations"][0], "execution_id": execution["execution_id"]}]}
    value = build_water_credit(execution=execution, physical_acceptance=acceptance,
        measurement={"measurement_id": "M-" + uuid.uuid4().hex,
                     "measured_volume_litres": 100, "verified": True}, recorded_at=NOW)
    first = append_water_credit(value, url); replay = append_water_credit(value, url)
    assert first["created"] is True and replay["created"] is False
    changed = {**value, "delivered_volume_litres": 101}
    changed["credit_sha256"] = "0" * 64
    assert validate_water_credit(changed) is False
    projection = read_water_credits(url)
    assert projection["by_execution"][execution["execution_id"]]["credit_id"] == value["credit_id"]
