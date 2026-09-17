from datetime import datetime,timedelta,timezone
import pytest
from modules.documents.green_print_adapter import ContractError,RegisteredPair,validate_authorized_job,validate_cups_evidence
NOW=datetime(2026,8,20,8,tzinfo=timezone.utc); PAIR=RegisteredPair("green-kitchen","hp-officejet-8123","weekly-a4","registry-v1")
def payload(**c):
    v={"job_id":"JOB-1","document_id":"DOC-1","document_version":"VER-1","document_type":"farm.weekly_weight_sheet.v1","generator_id":"web.print_sheets.v1","pdf_sha256":"a"*64,"retrieval_url":"https://documents.internal/api/documents/DOC-1/versions/VER-1/pdf","green_id":PAIR.green_id,"printer_id":PAIR.printer_id,"cups_queue_id":PAIR.cups_queue_id,"authorization_receipt_id":"AUTH-1","authorization_expires_at":NOW+timedelta(minutes=5),"options":{"media":"A4","copies":1,"color":"monochrome","sides":"one-sided"}}; v.update(c); return v
def valid(v): return validate_authorized_job(v,allowed_origin="https://documents.internal",registered_pair=PAIR,now=NOW)
def test_exact_envelope(): assert valid(payload()).job_id=="JOB-1"
@pytest.mark.parametrize("c",[{"document_type":"sales.quote.v1"},{"options":{"copies":2}},{"green_id":"other"},{"authorization_expires_at":NOW},{"retrieval_url":"https://evil.test/api/documents/DOC-1/versions/VER-1/pdf"},{"retrieval_url":"https://documents.internal/api/documents/DOC-1/versions/%2e%2e/pdf"},{"job_id":"unsafe:windows"}])
def test_rejections(c):
    with pytest.raises(ContractError): valid(payload(**c))
def test_bound_cups_evidence():
    j=valid(payload()); e={"observer_id":"cups-observer-1","job_id":j.job_id,"document_id":j.document_id,"document_version":j.document_version,"pdf_sha256":j.pdf_sha256,"printer_id":j.printer_id,"cups_queue_id":j.cups_queue_id,"submission_attempt_id":"ATTEMPT-1","cups_job_id":"CUPS-42","cups_state":"completed","observed_at":NOW,"secret":"must-not-pass"}
    assert validate_cups_evidence(e,job=j,observer_id="cups-observer-1")["cups_state"]=="completed"
    assert "secret" not in validate_cups_evidence(e,job=j,observer_id="cups-observer-1")
    with pytest.raises(ContractError): validate_cups_evidence({**e,"pdf_sha256":"b"*64},job=j,observer_id="cups-observer-1")
