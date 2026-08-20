from unittest.mock import patch

from app import app


def test_revision_health_reports_exact_render_provider_identity():
    with patch.dict("os.environ", {
        "RENDER": "true",
        "RENDER_GIT_COMMIT": "725653a6f19ea5eecdf1a56d0059ad647147d46b",
    }, clear=False):
        response = app.test_client().get("/health/revision")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "provider": "render",
        "revision": "725653a6f19ea5eecdf1a56d0059ad647147d46b",
        "identity_complete": True,
    }


def test_revision_health_fails_evidence_closed_when_identity_is_absent():
    with patch.dict("os.environ", {}, clear=True):
        response = app.test_client().get("/health/revision")

    assert response.status_code == 503
    assert response.get_json() == {
        "status": "deployment_identity_unavailable",
        "provider": "unknown",
        "revision": "",
        "identity_complete": False,
    }


def test_revision_health_rejects_spoofed_or_malformed_identity_without_echoing_it():
    cases = (
        {"RENDER_GIT_COMMIT": "a" * 40},
        {"RENDER": "true", "RENDER_GIT_COMMIT": "not-a-secret-but-forty-characters-long!!"},
    )
    for environment in cases:
        with patch.dict("os.environ", environment, clear=True):
            response = app.test_client().get("/health/revision")

        assert response.status_code == 503
        assert response.get_json()["identity_complete"] is False
        assert response.get_json()["revision"] == ""
