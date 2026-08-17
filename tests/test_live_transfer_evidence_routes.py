from unittest.mock import patch

from app import app


def client():
    app.testing = True
    return app.test_client()


@patch("modules.pig_weights.mating_routes.require_owner_read_access")
@patch("modules.pig_weights.mating_routes.build_live_transfer_contract")
def test_anonymous_read_is_denied_before_canonical_snapshot(build, guard):
    guard.return_value = ({"success": False, "error": "owner_read_required"}, 403)
    response = client().get(
        "/api/pig-weights/live-transfer-evidence/v1?order_id=ORD-2026-A6EC6D&pig_id=PIG-2026-A643"
    )
    assert response.status_code == 403
    build.assert_not_called()


@patch("modules.pig_weights.mating_routes.require_owner_read_access", return_value=None)
@patch("modules.pig_weights.mating_routes.build_live_transfer_contract")
def test_authenticated_read_is_private_zero_write(build, _guard):
    build.return_value = {"packet_digest": "abc", "writes_performed": False}
    response = client().get(
        "/api/pig-weights/live-transfer-evidence/v1?order_id=ORD-2026-A6EC6D"
        "&pig_id=PIG-2026-A643&pig_id=PIG-2026-B156"
    )
    assert response.status_code == 200
    assert response.get_json()["writes_performed"] is False
    assert response.headers["Cache-Control"] == "no-store, private"


@patch("modules.pig_weights.mating_routes.require_strict_owner_admin_access")
@patch("modules.pig_weights.mating_routes.build_live_transfer_contract")
def test_preview_and_execute_require_strict_admin_before_snapshot(build, guard):
    guard.return_value = ({"success": False, "error": "owner_admin_required"}, 403)
    payload = {"order_id": "ORD-2026-A6EC6D", "pig_ids": ["PIG-2026-A643", "PIG-2026-B156"]}
    assert client().post("/api/pig-weights/live-transfer-evidence/v1/preview", json=payload).status_code == 403
    assert client().post("/api/pig-weights/live-transfer-evidence/v1/execute", json=payload).status_code == 403
    build.assert_not_called()


@patch("modules.pig_weights.mating_routes.strict_owner_admin_principal", return_value="owner-admin:test")
@patch("modules.pig_weights.mating_routes.require_strict_owner_admin_access", return_value=None)
@patch("modules.pig_weights.mating_routes.preview_evidence_action")
@patch("modules.pig_weights.mating_routes.build_live_transfer_contract")
def test_preview_uses_one_canonical_packet_and_returns_zero_write(build, preview, _guard, _principal):
    build.return_value = {"packet_digest": "abc", "writes_performed": False}
    preview.return_value = ({"success": True, "writes_performed": False}, 200)
    payload = {"order_id": "ORD-2026-A6EC6D", "pig_ids": ["PIG-2026-A643", "PIG-2026-B156"],
               "answers": {"medical_pair_answers": []}}
    response = client().post("/api/pig-weights/live-transfer-evidence/v1/preview", json=payload)
    assert response.status_code == 200
    assert response.get_json()["writes_performed"] is False
    preview.assert_called_once()
