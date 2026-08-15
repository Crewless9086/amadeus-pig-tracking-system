from datetime import datetime, timezone
from pathlib import Path
from hashlib import sha256
import json
import os
import uuid

import pytest

from modules.telemetry.rootline_water_credit import (
    append_water_credit, build_water_credit, read_water_credits, record_water_credit,
    validate_water_credit,
)

NOW = datetime(2026, 8, 15, 15, 30, tzinfo=timezone.utc)
EXECUTION = {"execution_id": "ROOTLINE-EXECUTION-TEST", "zone_id": "B12345",
    "state": "Completed", "verified_runtime_seconds": 3599, "shutdown_verified": True,
    "start_evidence": {"state": "ON"}, "shutdown_evidence": {"state": "OFF"}}
ACCEPTANCE = {"acceptance_sha256": "a" * 64, "observations": [{
    "execution_id": "ROOTLINE-EXECUTION-TEST", "zone_id": "B12345",
    "water_flow": "normal", "stopped_flow": "normal", "physically_off_now": True}]}


def volume_evidence(kind="measured_volume", zone="B12345", **fields):
    value = {"contract_version": "rootline_water_volume_evidence.v1",
        "evidence_id": "VOLUME-EVIDENCE-1", "evidence_type": kind, "zone_id": zone,
        "source": "verified_volume_measurement" if kind == "measured_volume"
                  else "commissioned_zone_calibration",
        "verified": True, "observed_at": NOW.isoformat(), **fields}
    value["evidence_sha256"] = sha256(json.dumps(value, sort_keys=True,
        separators=(",", ":"), default=str).encode()).hexdigest()
    return value


def test_runtime_and_owner_flow_alone_keep_litres_unknown():
    value = build_water_credit(execution=EXECUTION, physical_acceptance=ACCEPTANCE,
                               recorded_at=NOW)
    assert value["status"] == "Unknown"
    assert value["delivered_volume_litres"] == "Unknown"
    assert value["writes_farm_data"] is False


def test_verified_measurement_binds_execution_acceptance_and_separate_evidence():
    value = build_water_credit(execution=EXECUTION, physical_acceptance=ACCEPTANCE,
        measurement=volume_evidence(measured_volume_litres=1234.5), recorded_at=NOW)
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
        calibration=volume_evidence("governed_calibration", litres_per_minute=10),
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
            measurement=volume_evidence(measured_volume_litres=1),
            recorded_at=NOW)
        assert result["status"] == "Unknown" and result["hardware_control"] is False
    wrong_zone = build_water_credit(execution=EXECUTION, physical_acceptance=ACCEPTANCE,
        measurement=volume_evidence(zone="C12345", measured_volume_litres=1), recorded_at=NOW)
    assert wrong_zone["status"] == "Unknown"


class FakeDatabase:
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self
    def execute(self, *_args): pass
    def fetchone(self): return [False]


def test_exact_replay_returns_zero_new_credit(monkeypatch):
    monkeypatch.setattr("modules.oom_sakkie.bounded_postgres_read.connect_bounded_rootline_postgres",
                        lambda **_kwargs: FakeDatabase())
    value = build_water_credit(execution=EXECUTION, physical_acceptance=ACCEPTANCE,
        measurement=volume_evidence(measured_volume_litres=1),
        recorded_at=NOW)
    result = append_water_credit(value, "postgres://disposable")
    assert result["status"] == "exact_replay" and result["created"] is False


def test_append_uses_bounded_write_helper(monkeypatch):
    calls = []
    monkeypatch.setattr("modules.oom_sakkie.bounded_postgres_read.connect_bounded_rootline_postgres",
        lambda **kwargs: (calls.append(kwargs) or FakeDatabase()))
    value = build_water_credit(execution=EXECUTION, physical_acceptance=ACCEPTANCE,
        measurement=volume_evidence(measured_volume_litres=1), recorded_at=NOW)
    append_water_credit(value, "postgres://disposable")
    assert calls == [{"database_url": "postgres://disposable", "read_only": False}]


def test_record_level_retry_rebuilds_identical_credit(monkeypatch):
    evidence = volume_evidence(measured_volume_litres=1)
    class Canonical(FakeDatabase):
        def execute(self, sql, _params): self.sql = sql
        def fetchone(self):
            if "rootline_irrigation_execution" in self.sql: return [EXECUTION]
            if "rootline_physical_acceptance" in self.sql: return [ACCEPTANCE]
            if "irrigation_water_volume_evidence" in self.sql: return [evidence]
            return None
    monkeypatch.setattr("modules.oom_sakkie.bounded_postgres_read.connect_bounded_rootline_postgres",
                        lambda **_kwargs: Canonical())
    captured = []
    monkeypatch.setattr("modules.telemetry.rootline_water_credit.append_water_credit",
        lambda value, _url: (captured.append(value) or {"success": True, "created": not captured[:-1]}))
    first = record_water_credit(execution_id=EXECUTION["execution_id"],
        physical_acceptance_sha256=ACCEPTANCE["acceptance_sha256"],
        volume_evidence_id=evidence["evidence_id"], database_url="postgres://fixture")
    second = record_water_credit(execution_id=EXECUTION["execution_id"],
        physical_acceptance_sha256=ACCEPTANCE["acceptance_sha256"],
        volume_evidence_id=evidence["evidence_id"], database_url="postgres://fixture")
    assert first["water_credit"]["credit_sha256"] == second["water_credit"]["credit_sha256"]
    assert captured[0] == captured[1]


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
    evidence = volume_evidence(evidence_id="VOLUME-" + uuid.uuid4().hex,
                               measured_volume_litres=100)
    with psycopg.connect(url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select public.rootline_append_water_volume_evidence(%s,%s,%s,%s,%s::jsonb)",
                (evidence["evidence_id"], evidence["evidence_type"], evidence["zone_id"],
                 evidence["evidence_sha256"], json.dumps(evidence, sort_keys=True,
                    separators=(",", ":"))))
            assert cursor.fetchone()[0] is True
    value = build_water_credit(execution=execution, physical_acceptance=acceptance,
        measurement=evidence, recorded_at=NOW)
    first = append_water_credit(value, url); replay = append_water_credit(value, url)
    assert first["created"] is True and replay["created"] is False
    mismatched = {key: item for key, item in value.items() if key != "status"}
    mismatched["credit_id"] = "ROOTLINE-WATER-CREDIT-" + uuid.uuid4().hex[:24].upper()
    mismatched["volume_evidence_sha256"] = "f" * 64
    digest_material = {key: item for key, item in mismatched.items() if key != "credit_sha256"}
    mismatched["credit_sha256"] = sha256(json.dumps(digest_material, sort_keys=True,
        separators=(",", ":"), default=str).encode()).hexdigest()
    with psycopg.connect(url, connect_timeout=10) as connection:
        with connection.cursor() as cursor, pytest.raises(psycopg.Error,
                match="canonical ROOTLINE volume evidence missing or mismatched"):
            cursor.execute("select public.rootline_append_water_credit_event(%s,%s,%s,%s,%s,%s::jsonb)",
                (mismatched["credit_id"], mismatched["execution_id"], mismatched["zone_id"],
                 mismatched["physical_acceptance_sha256"], mismatched["credit_sha256"],
                 json.dumps(mismatched, sort_keys=True, separators=(",", ":"))))
    changed = {**value, "delivered_volume_litres": 101}
    changed["credit_sha256"] = "0" * 64
    assert validate_water_credit(changed) is False
    projection = read_water_credits(url)
    assert projection["by_execution"][execution["execution_id"]]["credit_id"] == value["credit_id"]
