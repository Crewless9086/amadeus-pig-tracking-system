from datetime import date, datetime, timedelta, timezone

import pytest

from modules.documents.weekly_weight_sheet import (
    PRINT_ACTION_KIND, authorized_job_from_claim, build_weekly_sheet_revision,
    protected_print_preview,
)

NOW = datetime(2026, 8, 20, 8, tzinfo=timezone.utc)
ROWS = [{"pig_id": "PIG-2", "tag_number": "Beta", "pen_id": "PEN-2"},
        {"pig_id": "PIG-1", "tag_number": "Alpha", "pen_id": "PEN-1"}]


def revision(rows=ROWS):
    return build_weekly_sheet_revision(authenticated_principal_id="owner-admin.1",
        requester="oom_sakkie", sheet_date=date(2026, 8, 20), rows=rows)


def test_pdf_revision_is_deterministic_and_digest_bound():
    first, second = revision(), revision(list(reversed(ROWS)))
    assert first.pdf_bytes.startswith(b"%PDF")
    assert first.pdf_sha256 == second.pdf_sha256
    assert first.version_id == second.version_id


def test_duplicate_or_untrusted_rows_fail_closed():
    with pytest.raises(ValueError, match="duplicate_weekly_pig_id"):
        revision([ROWS[0], ROWS[0]])
    with pytest.raises(PermissionError):
        build_weekly_sheet_revision(authenticated_principal_id="owner-admin.1",
            requester="sam", sheet_date=date(2026, 8, 20), rows=ROWS)


def test_protected_claim_binds_every_print_dimension():
    item = revision()
    payload = protected_print_preview(revision=item, job_id="JOB-1",
        green_id="green-1", printer_id="printer-1", cups_queue_id="weekly-a4",
        registry_version="registry-v1",
        retrieval_url=f"https://documents.internal/api/documents/{item.document_id}/versions/{item.version_id}/pdf",
        authorization_expires_at=NOW + timedelta(minutes=10))
    claim = {"action_kind": PRINT_ACTION_KIND, "callback_token": "AUTH-1",
             "preview_digest": payload.pop("preview_digest"), "preview_payload": payload}
    envelope = authorized_job_from_claim(claim)
    assert envelope["pdf_sha256"] == item.pdf_sha256
    assert envelope["options"] == {"media":"A4","copies":1,"color":"monochrome","sides":"one-sided"}
    with pytest.raises(ValueError, match="digest_mismatch"):
        authorized_job_from_claim({**claim, "preview_digest": "0" * 64})
