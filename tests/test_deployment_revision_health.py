from unittest.mock import patch

from app import app


def test_revision_health_reports_exact_render_provider_identity():
    with patch.dict("os.environ", {
        "RENDER": "true",
        "ROOTLINE_INPUT_HEALTH_ENABLED": "false",
        "RENDER_SERVICE_ID": "", "RENDER_INSTANCE_ID": "",
        "RENDER_GIT_COMMIT": "725653a6f19ea5eecdf1a56d0059ad647147d46b",
    }, clear=False):
        response = app.test_client().get("/health/revision")

    assert response.headers["Cache-Control"] == "no-store"
    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "provider": "render",
        "revision": "725653a6f19ea5eecdf1a56d0059ad647147d46b",
        "identity_complete": True,
        "rootline_input_health_enabled": False,
        "service_id": "unknown",
        "instance_id": "unknown",
    }


def test_revision_health_fails_evidence_closed_when_identity_is_absent():
    with patch.dict("os.environ", {}, clear=True):
        response = app.test_client().get("/health/revision")

    assert response.headers["Cache-Control"] == "no-store"
    assert response.status_code == 503
    assert response.get_json() == {
        "status": "deployment_identity_unavailable",
        "provider": "unknown",
        "revision": "",
        "identity_complete": False,
        "rootline_input_health_enabled": False,
        "service_id": "unknown",
        "instance_id": "unknown",
    }


def test_revision_health_rejects_spoofed_or_malformed_identity_without_echoing_it():
    cases = (
        {"RENDER_GIT_COMMIT": "a" * 40},
        {"RENDER": "true", "RENDER_GIT_COMMIT": "not-a-secret-but-forty-characters-long!!"},
    )
    for environment in cases:
        with patch.dict("os.environ", environment, clear=True):
            response = app.test_client().get("/health/revision")

        assert response.headers["Cache-Control"] == "no-store"
        assert response.status_code == 503
        assert response.get_json()["identity_complete"] is False
        assert response.get_json()["revision"] == ""


def test_revision_health_reports_loaded_flag_without_changing_readiness():
    from modules.telemetry.rootline_input_health import input_health_enabled
    for value in (None, "false", "true", " TRUE ", "1"):
        environment = {"RENDER": "true", "RENDER_GIT_COMMIT": "a"*40,
            "RENDER_SERVICE_ID": "srv-d6sijjkhg0os73f7regg", "RENDER_INSTANCE_ID": "instance_1:pod-2.3"}
        if value is not None: environment["ROOTLINE_INPUT_HEALTH_ENABLED"] = value
        with patch.dict("os.environ", environment, clear=True):
            response = app.test_client().get("/health/revision")
            expected = input_health_enabled()
        assert response.headers["Cache-Control"] == "no-store"
        assert response.status_code == 200
        assert response.get_json()["rootline_input_health_enabled"] is expected
        assert response.get_json()["service_id"] == environment["RENDER_SERVICE_ID"]
        assert response.get_json()["instance_id"] == environment["RENDER_INSTANCE_ID"]
        assert response.get_json()["identity_complete"] is True


def test_revision_health_omits_malformed_metadata_and_never_echoes_secrets():
    cases = [("wrong-service", "https://secret.invalid/key"),
        ("srv-"+"x"*200, "x"*161), ("srv-d6sijjkhg0os73f7regg\n", "bad\ninstance")]
    for service, instance in cases:
        environment = {"RENDER": "true", "RENDER_GIT_COMMIT": "a"*40,
            "RENDER_SERVICE_ID": service, "RENDER_INSTANCE_ID": instance,
            "DATABASE_URL": "SECRET-DATABASE", "OPENAI_API_KEY": "SECRET-API",
            "ROOTLINE_INPUT_HEALTH_ENABLED": "true"}
        with patch.dict("os.environ", environment, clear=True):
            response = app.test_client().get("/health/revision")
        assert response.headers["Cache-Control"] == "no-store"
        assert response.status_code == 200 and response.get_json()["identity_complete"] is True
        assert response.get_json()["service_id"] == response.get_json()["instance_id"] == "unknown"
        assert "SECRET-" not in response.get_data(as_text=True)
        assert "secret.invalid" not in response.get_data(as_text=True)
    with patch.dict("os.environ", {"RENDER_SERVICE_ID":"srv-d6sijjkhg0os73f7regg", "RENDER_INSTANCE_ID":"valid-instance", "ROOTLINE_INPUT_HEALTH_ENABLED":"true"}, clear=True):
        response = app.test_client().get("/health/revision")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.status_code == 503
    assert response.get_json()["rootline_input_health_enabled"] is True
    assert response.get_json()["service_id"] == response.get_json()["instance_id"] == "unknown"


def test_revision_health_never_calls_database_or_provider(monkeypatch):
    import psycopg
    import socket
    import requests
    from modules.oom_sakkie import bounded_postgres_read
    from modules.telemetry import rootline_input_health, rootline_provider_availability
    calls=[]
    def blocked(*a, **kw):
        calls.append("forbidden")
        raise AssertionError("revision_health_external_effect")
    monkeypatch.setattr(psycopg, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(requests.sessions.Session, "request", blocked)
    monkeypatch.setattr(bounded_postgres_read, "connect_bounded_rootline_postgres", blocked)
    monkeypatch.setattr(rootline_input_health, "read_input_health", blocked)
    monkeypatch.setattr(rootline_provider_availability, "read_provider_availability", blocked)
    for flag in ("false", "true"):
        with patch.dict("os.environ", {"RENDER":"true", "RENDER_GIT_COMMIT":"a"*40,
                "ROOTLINE_INPUT_HEALTH_ENABLED":flag}, clear=True):
            response=app.test_client().get("/health/revision")
        assert response.status_code==200
        assert response.headers["Cache-Control"]=="no-store"
        assert response.get_json()["rootline_input_health_enabled"] is (flag=="true")
    assert calls==[]
