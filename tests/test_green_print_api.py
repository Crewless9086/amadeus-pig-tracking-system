from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app import app
from modules.documents import green_print_api
from modules.documents.weekly_weight_sheet import (
    PRINT_ACTION_KIND, build_weekly_sheet_revision, protected_print_preview,
)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DOCUMENTS_GREEN_WORKER_TOKEN", "exact-secret")
    monkeypatch.setenv("DOCUMENTS_GREEN_ID", "green-registered")
    monkeypatch.setenv("DOCUMENTS_FARM_SCOPE_ID", "farm-amadeus")
    green_print_api._LIMITS.clear()
    app.config.update(TESTING=True)
    return app.test_client()


def headers(**extra):
    return {"Authorization": "Bearer exact-secret", "X-Amadeus-Farm-Scope-Id": "farm-amadeus",
            "X-Amadeus-Green-Id": "green-registered",
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
    assert call.call_args.args[1] == ("farm-amadeus", "green-registered", "green-worker-epoch", 300)
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


def test_transition_binds_authenticated_green_and_exact_worker(client):
    body = {"lease_token": "LEASE-1", "document_version": "VER-1", "pdf_sha256": "a" * 64,
            "authorization_receipt_id": "AUTH-1", "target_state": "submitting",
            "event_id": "00000000-0000-0000-0000-000000000001", "attempt_id": "ATTEMPT-1"}
    with patch.object(green_print_api, "_call", return_value={"job_id": "JOB-1"}) as call:
        response = client.post("/api/documents/print-jobs/JOB-1/transition", headers=headers(), json=body)
    assert response.status_code == 200
    args = call.call_args.args[1]
    assert args[-4:-1] == ("farm-amadeus", "green-registered", "green-worker-epoch")
    with patch.object(green_print_api, "_call", return_value={"job_id": "JOB-1"}) as blocked:
        response = client.post("/api/documents/print-jobs/JOB-1/transition",
            headers=headers(**{"X-Amadeus-Worker-Id": "other-worker"}), json=body)
        # The alternate authenticated epoch is forwarded and then fenced by the
        # canonical lease_owner comparison; it cannot impersonate the claimant.
        assert response.status_code == 200
        assert blocked.call_args.args[1][-2] == "other-worker"


def test_server_producer_binds_protected_claim_revision_scope_and_exact_url():
    revision = build_weekly_sheet_revision(authenticated_principal_id="owner-admin.1",
        requester="oom_sakkie", sheet_date=date(2026, 8, 20),
        rows=[{"pig_id":"PIG-1","tag_number":"Alpha","pen_id":"PEN-1"}])
    url = (f"https://documents.internal/api/documents/{revision.document_id}/versions/"
           f"{revision.version_id}/pdf")
    preview = protected_print_preview(revision=revision, job_id="JOB-1",
        farm_scope_id="farm-amadeus", green_id="green-registered",
        printer_id="printer-1", cups_queue_id="weekly-a4",
        registry_version="registry-v1", retrieval_url=url,
        authorization_expires_at=datetime.now(timezone.utc) + timedelta(minutes=10))
    digest = preview.pop("preview_digest")
    claim = {"action_kind": PRINT_ACTION_KIND, "callback_token": "AUTH-1",
        "status":"protected_callback_claimed", "preview_digest":digest,
        "preview_payload":preview}
    row = {**preview, "authorization_receipt_id":"AUTH-1", "state":"authorized"}
    connection = MagicMock(); cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = tuple(row.values())
    cursor.description = [MagicMock(name=key) for key in row]
    for item, key in zip(cursor.description, row): item.name = key
    result = green_print_api.create_authorized_job_from_claim(claim, revision,
        authenticated_principal_id="owner-admin.1", request_channel="telegram",
        farm_scope_id="farm-amadeus", canonical_api_origin="https://documents.internal",
        connect_factory=lambda: connection)
    persisted = cursor.execute.call_args.args[1][0].obj
    assert persisted["retry_deadline"] == persisted["authorization_expires_at"]
    assert persisted["retrieval_url"] == url
    assert result["farm_scope_id"] == "farm-amadeus"

    with pytest.raises(ValueError, match="scope_or_retrieval"):
        green_print_api.create_authorized_job_from_claim(claim, revision,
            authenticated_principal_id="owner-admin.1", request_channel="telegram",
            farm_scope_id="other-farm", canonical_api_origin="https://documents.internal",
            connect_factory=lambda: connection)
    with pytest.raises(ValueError, match="canonical_private_origin"):
        green_print_api.create_authorized_job_from_claim(claim, revision,
            authenticated_principal_id="owner-admin.1", request_channel="telegram",
            farm_scope_id="farm-amadeus", canonical_api_origin="http://documents.internal",
            connect_factory=lambda: connection)


def test_standing_owner_request_creates_executing_digest_receipt_without_card(monkeypatch):
    monkeypatch.setenv("DOCUMENTS_FARM_SCOPE_ID", "farm-amadeus")
    monkeypatch.setenv("DOCUMENTS_CANONICAL_API_ORIGIN", "https://documents.internal")
    revision = build_weekly_sheet_revision(authenticated_principal_id="owner-1",
        requester="oom_sakkie", sheet_date=date(2026, 8, 25),
        rows=[{"pig_id":"PIG-1","tag_number":"1","pen_id":"B1"}])
    url = (f"https://documents.internal/api/documents/{revision.document_id}/versions/"
           f"{revision.version_id}/pdf")
    preview = protected_print_preview(revision=revision, job_id="GREEN-JOB-1",
        farm_scope_id="farm-amadeus", green_id="green-1", printer_id="printer-1",
        cups_queue_id="weekly-a4", registry_version="registry-v1", retrieval_url=url,
        authorization_expires_at=datetime.now(timezone.utc)+timedelta(minutes=10))
    payload={key:value for key,value in preview.items() if key!="preview_digest"}
    connection=MagicMock();cursor=connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value=("GREEN-SA-RECEIPT","executing","owner-1",payload)
    cursor.rowcount=1
    captured=[]
    def persist(claim, actual_revision, **kwargs):
        captured.append((claim,actual_revision,kwargs));return {"job_id":"GREEN-JOB-1"}
    monkeypatch.setattr(green_print_api,"create_authorized_job_from_claim",persist)
    result=green_print_api.authorize_standing_weekly_print(preview,revision,{
        "telegram_user_id":"owner-1","telegram_chat_id":"owner-1",
        "telegram_chat_type":"private","provider_message_id":"MSG-25"},
        connect_factory=lambda:connection)
    insert_sql=cursor.execute.call_args_list[0].args[0]
    assert "'executing'" in insert_sql and "preview_card_message_id" not in insert_sql
    assert captured[0][0]["preview_digest"]==preview["preview_digest"]
    assert captured[0][0]["preview_payload"]==payload
    assert result["job_id"]=="GREEN-JOB-1"


def test_physical_acceptance_is_owner_and_exact_job_bound_without_green_authority():
    preview={"contract_version":"documents_green_physical_acceptance_v1",
        "job_id":"JOB-1","document_version":"VER-1","pdf_sha256":"a"*64,
        "cups_job_id":"weekly-a4-7","provider_id":"ipps://192.168.1.20/ipp/print",
        "evidence_id":"OWNER-PAGE-1","observed_at":"2026-08-21T12:00:00+00:00"}
    claim={"action_kind":"documents_green_physical_acceptance",
        "status":"protected_callback_claimed","preview_payload":preview}
    row={**preview,"state":"physically_confirmed"}
    connection=MagicMock();cursor=connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value=tuple(row.values())
    cursor.description=[MagicMock(name=key) for key in row]
    for item,key in zip(cursor.description,row):item.name=key
    result=green_print_api.execute_claimed_physical_page_acceptance(claim,
        {"telegram_user_id":"owner-1","telegram_chat_id":"owner-1"},
        connect_factory=lambda:connection)
    args=cursor.execute.call_args.args[1]
    assert args[:5]==("JOB-1","VER-1","a"*64,"weekly-a4-7",
        "ipps://192.168.1.20/ipp/print")
    assert result["physical_page_confirmed"] is True
    assert result["physical_observation_result"]=="correct"
    assert result["automatic_reprint"] is False

    with pytest.raises(ValueError,match="authenticated_owner"):
        green_print_api.execute_claimed_physical_page_acceptance(claim,
            {"telegram_user_id":"owner-1","telegram_chat_id":"group"},
            connect_factory=lambda:connection)


@pytest.mark.parametrize("selected_action,expected,follow_up", [
    ("incorrect",False,"exception_owned"),
    ("uncertain",False,"exception_owned"),
])
def test_physical_exception_result_is_explicit_and_never_auto_reprints(
        selected_action,expected,follow_up):
    preview={"contract_version":"documents_green_physical_acceptance_v1",
        "job_id":"JOB-1","document_version":"VER-1","pdf_sha256":"a"*64,
        "cups_job_id":"weekly-a4-7","provider_id":"ipps://192.168.1.20/ipp/print",
        "evidence_id":"OWNER-PAGE-1"}
    claim={"action_kind":"documents_green_physical_acceptance",
        "status":"protected_callback_claimed","selected_action":selected_action,
        "preview_payload":preview}
    row={**preview,"state":"held"}
    connection=MagicMock();cursor=connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value=tuple(row.values())
    cursor.description=[MagicMock(name=key) for key in row]
    for item,key in zip(cursor.description,row):item.name=key
    result=green_print_api.execute_claimed_physical_page_acceptance(claim,
        {"telegram_user_id":"owner-1","telegram_chat_id":"owner-1",
         "provider_timestamp":"2026-08-21T12:00:00+00:00"},
        connect_factory=lambda:connection)
    assert result["physical_page_confirmed"] is expected
    assert result["physical_observation_result"]==selected_action
    assert result["follow_up_state"]==follow_up and result["automatic_reprint"] is False
    assert cursor.execute.call_args.args[1][-1]==selected_action
