from unittest.mock import patch

import pytest

from app import app
from modules.documents import green_print_api


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DOCUMENTS_GREEN_WORKER_TOKEN", "exact-secret")
    monkeypatch.setenv("DOCUMENTS_GREEN_ID", "green-registered")
    green_print_api._LIMITS.clear()
    app.config.update(TESTING=True)
    return app.test_client()


def headers(**extra):
    return {"Authorization": "Bearer exact-secret", "X-Amadeus-Green-Id": "green-registered",
            "X-Amadeus-Worker-Id": "green-worker-epoch", **extra}


def test_browser_roles_and_wrong_worker_identity_are_denied(client):
    assert client.post("/api/documents/print-jobs/claims", json={"worker_id": "green-worker-1"}).status_code == 401
    assert client.post("/api/documents/print-jobs/claims", headers={"Authorization": "Bearer exact-secret",
        "X-Amadeus-Green-Id": "wrong"}, json={"worker_id": "green-worker-1"}).status_code == 401


def test_claim_uses_authenticated_boundary_and_minimized_response(client):
    row = {"job_id": "JOB-1", "document_id": "DOC-1", "document_version": "VER-1",
           "lease_token": "LEASE-1", "lease_expires_at": "2026-08-21T12:00:00Z",
           "pdf_bytes": b"secret", "authenticated_principal_id": "owner"}
    with patch.object(green_print_api, "_call", return_value=[row]) as call:
        response = client.post("/api/documents/print-jobs/claims", headers=headers(),
                               json={"worker_id": "green-worker-epoch", "lease_seconds": 300})
    assert response.status_code == 200
    assert call.call_args.args[1] == ("green-registered", "green-worker-epoch", 300)
    assert "pdf_bytes" not in response.get_json()["job"]
    assert "authenticated_principal_id" not in response.get_json()["job"]


def test_client_supplied_principal_and_oversize_are_rejected_before_database(client):
    with patch.object(green_print_api, "_call") as call:
        response = client.post("/api/documents/print-jobs/claims", headers=headers(),
            json={"worker_id": "green-worker-1", "authenticated_principal_id": "forged"})
        assert response.status_code == 400
        call.assert_not_called()
        response = client.post("/api/documents/print-jobs/claims", headers={**headers(),
            "Content-Type": "application/json"}, data=b"{" + b" " * 20000 + b"}")
        assert response.status_code == 413
