import os
from unittest.mock import patch

from app import app


TOKEN = "general-manager-route-token-at-least-32-characters"


@patch.dict(os.environ, {"OOM_SAKKIE_MORNING_SCHEDULER_TOKEN": TOKEN}, clear=False)
def test_general_manager_route_denies_unauthenticated_request():
    response = app.test_client().post("/api/oom-sakkie/management/general-manager-cycle", json={})
    assert response.status_code == 403
    body = response.get_json()
    assert body["status"] == "general_manager_auth_denied"
    assert body["telegram_sends"] == 0
    assert body["provider_actions"] == 0
    assert body["hardware_commands"] == 0


@patch.dict(os.environ, {"OOM_SAKKIE_MORNING_SCHEDULER_TOKEN": TOKEN}, clear=False)
@patch("modules.oom_sakkie.routes.run_general_manager_cycle")
def test_general_manager_route_runs_authenticated_worker(run_cycle):
    run_cycle.return_value = {
        "success": True, "status": "general_manager_cycle_completed",
        "worker_id": "oom-sakkie-general-manager-v1", "telegram_sends": 0,
        "provider_actions": 0, "hardware_commands": 0,
    }
    response = app.test_client().post(
        "/api/oom-sakkie/management/general-manager-cycle", json={},
        headers={"Authorization": "Bearer " + TOKEN})
    assert response.status_code == 200
    assert response.get_json()["worker_id"] == "oom-sakkie-general-manager-v1"
    run_cycle.assert_called_once_with()
