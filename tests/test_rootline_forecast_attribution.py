from copy import deepcopy
import pytest
from modules.telemetry.rootline_water_energy_plan import _normalize_forecast, build_water_energy_plan
from modules.telemetry.rootline_specialist_result import project_water_energy_plan, build_rootline_specialist_result
from modules.oom_sakkie.rootline_daily_presentation import compose_daily_rootline_plan, compose_daily_rootline_manager_item
from tests.test_rootline_specialist_result import evidence, NOW


@pytest.mark.parametrize("provider,name", [("visual_crossing", "Visual Crossing Weather"),
    ("weatherapi", "WeatherAPI.com"), ("open_meteo", "Open-Meteo")])
def test_selected_provider_survives_plan_and_both_owner_reports_without_changing_weather(provider, name):
    original = evidence()
    packet = {"success": True, "source": {"provider": provider,
        "source_id": provider + "-forecast-main", "last_forecast_run_at": original["forecast"]["observed_at"],
        "stale_after_minutes": 360, "attribution": {"url": "javascript:bad", "name": "<bad>"}},
        "days": deepcopy(original["forecast"]["days"])}
    normalized = _normalize_forecast(packet)
    current = {**original, "forecast": normalized}
    plan = build_water_energy_plan(current, "2026-07-29", now=NOW)
    direct = build_rootline_specialist_result(current, "2026-07-29", now=NOW)
    projected = project_water_energy_plan(plan, now=NOW)
    for result in (direct, projected):
        assert result["forecast"]["source"]["provider"] == provider
        for language in ("en", "af"):
            visible = compose_daily_rootline_plan(result, language=language)
            assert name in visible and "https://" in visible
            assert "javascript:" not in visible and "<bad>" not in visible
            assert name in compose_daily_rootline_manager_item(result, language=language)["why"]
    baseline = build_rootline_specialist_result(original, "2026-07-29", now=NOW)
    assert direct["current_local_weather"] == baseline["current_local_weather"]
    assert direct["recommendations"] == baseline["recommendations"]
    assert plan["rain_capture"]["roof_capture_volume_litres"] == "Unavailable"


def test_unknown_provider_does_not_render_supplied_attribution():
    result = build_rootline_specialist_result(evidence(), "2026-07-29", now=NOW)
    result["forecast"]["source"] = {"provider": "unregistered", "attribution": {"name": "INJECTED", "url": "https://untrusted.invalid"}}
    assert "INJECTED" not in compose_daily_rootline_plan(result)
    assert "untrusted.invalid" not in compose_daily_rootline_plan(result)
