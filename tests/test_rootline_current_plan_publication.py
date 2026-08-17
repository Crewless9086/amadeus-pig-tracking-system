from datetime import datetime
from unittest import mock

from modules.telemetry.rootline_specialist_result import refresh_current_rootline_specialist_result


NOW = datetime.fromisoformat("2026-08-17T20:00:00+02:00")


def test_scheduler_publishes_and_reads_back_same_evidence_before_projection():
    evidence = {"power": {}, "weather": {}, "forecast": {}, "tanks": {}}
    plan = {"success": True, "plan_id": "ROOTLINE-WEP-20260817",
            "operating_date": "2026-08-17", "evidence_sha256": "a" * 64}
    with mock.patch("modules.telemetry.rootline_specialist_result.read_current_water_energy_evidence",
                    return_value=(evidence, "2026-08-17", NOW)), \
         mock.patch("modules.telemetry.rootline_specialist_result.build_water_energy_plan",
                    return_value=plan), \
         mock.patch("modules.telemetry.rootline_specialist_result.append_water_energy_plan",
                    return_value=({**plan, "generation": 2}, 201)) as append, \
         mock.patch("modules.telemetry.rootline_specialist_result.get_current_water_energy_plan",
                    return_value=({**plan, "generation": 2,
                        "evidence_observed_at": NOW.isoformat()}, 200)), \
         mock.patch("modules.telemetry.rootline_specialist_result.build_rootline_specialist_result",
                    return_value={"success": True, "result_id": "ROOTLINE-RESULT-1"}):
        result = refresh_current_rootline_specialist_result(now=NOW, database_url="db")
    assert result["canonical_plan"]["generation"] == 2
    assert result["canonical_plan"]["evidence_sha256"] == "a" * 64
    append.assert_called_once_with(plan, "OOM_SAKKIE_ROOTLINE_SCHEDULER", database_url="db")


def test_scheduler_refuses_projection_when_canonical_plan_readback_differs():
    plan = {"success": True, "plan_id": "ROOTLINE-WEP-20260817",
            "operating_date": "2026-08-17", "evidence_sha256": "a" * 64}
    with mock.patch("modules.telemetry.rootline_specialist_result.read_current_water_energy_evidence",
                    return_value=({}, "2026-08-17", NOW)), \
         mock.patch("modules.telemetry.rootline_specialist_result.build_water_energy_plan",
                    return_value=plan), \
         mock.patch("modules.telemetry.rootline_specialist_result.append_water_energy_plan",
                    return_value=({**plan, "generation": 1}, 201)), \
         mock.patch("modules.telemetry.rootline_specialist_result.get_current_water_energy_plan",
                    return_value=({**plan, "evidence_sha256": "b" * 64}, 200)):
        result = refresh_current_rootline_specialist_result(now=NOW, database_url="db")
    assert result["success"] is False
    assert result["reason"] == "canonical_plan_readback_mismatch"
