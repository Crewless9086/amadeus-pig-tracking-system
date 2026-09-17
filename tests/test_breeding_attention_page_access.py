import os
from unittest.mock import patch

from app import app
from modules.auth.owner_access import configure_owner_access


READ_TOKEN = "read-owner-token-1234567890abcdef"
REMOTE = {"REMOTE_ADDR": "203.0.113.10"}
PAGE = "/api/pig-weights/breeding-attention/view"


def owner_env():
    return {
        "OWNER_ACCESS_ENABLED": "1",
        "OWNER_ACCESS_ALLOW_LOCAL_DEV": "0",
        "OWNER_READ_TOKEN": READ_TOKEN,
        "OWNER_ADMIN_TOKEN": "admin-owner-token-1234567890abcdef",
        "OWNER_SESSION_SECRET": "owner-session-secret-1234567890abcdef",
    }


def test_anonymous_page_redirects_to_owner_login_with_exact_return_path():
    app.testing = True
    with patch.dict(os.environ, owner_env(), clear=False):
        configure_owner_access(app)
        response = app.test_client().get(PAGE, environ_base=REMOTE)
    assert response.status_code == 302
    assert response.headers["Location"] == f"/owner/login?next={PAGE}"


def test_successful_owner_login_returns_to_breeding_attention_page():
    app.testing = True
    with patch.dict(os.environ, owner_env(), clear=False):
        configure_owner_access(app)
        client = app.test_client()
        login = client.post(
            "/owner/login",
            data={"owner_token": READ_TOKEN, "next": PAGE},
            environ_base=REMOTE,
        )
        page = client.get(login.headers["Location"], environ_base=REMOTE)
    assert login.status_code == 302
    assert login.headers["Location"] == PAGE
    assert page.status_code == 200
    assert b"Teel-aandag" in page.data


def test_expired_or_invalid_session_cookie_redirects_to_login():
    app.testing = True
    with patch.dict(os.environ, owner_env(), clear=False):
        configure_owner_access(app)
        client = app.test_client()
        client.set_cookie("session", "expired-or-invalid-signed-session")
        response = client.get(PAGE, environ_base=REMOTE)
    assert response.status_code == 302
    assert response.headers["Location"] == f"/owner/login?next={PAGE}"


def test_authenticated_owner_session_renders_page_normally():
    app.testing = True
    with patch.dict(os.environ, owner_env(), clear=False):
        configure_owner_access(app)
        client = app.test_client()
        client.post(
            "/owner/login",
            data={"owner_token": READ_TOKEN, "next": PAGE},
            environ_base=REMOTE,
        )
        response = client.get(PAGE, environ_base=REMOTE)
    assert response.status_code == 200
    assert b"Teel-aandag" in response.data


def test_malicious_return_destinations_are_rejected():
    app.testing = True
    with patch.dict(os.environ, owner_env(), clear=False):
        configure_owner_access(app)
        for destination in (
            "https://evil.example/steal",
            "//evil.example/steal",
            "/\\evil.example/steal",
            "/safe\r\nLocation: https://evil.example/steal",
        ):
            response = app.test_client().post(
                "/owner/login",
                data={"owner_token": READ_TOKEN, "next": destination},
                environ_base=REMOTE,
            )
            assert response.status_code == 302
            assert response.headers["Location"] == "/sales/meat-leads"


def test_anonymous_json_endpoint_retains_api_style_403_without_redirect():
    app.testing = True
    with patch.dict(os.environ, owner_env(), clear=False):
        configure_owner_access(app)
        response = app.test_client().get(
            "/api/pig-weights/breeding-attention", environ_base=REMOTE
        )
    assert response.status_code == 403
    assert response.is_json
    assert response.get_json()["status"] == "owner_read_access_denied"
    assert "Location" not in response.headers
