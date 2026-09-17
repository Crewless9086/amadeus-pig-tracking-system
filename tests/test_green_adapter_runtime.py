from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from modules.documents.green_adapter_runtime import GreenAdapterLedger, run_cycle
from modules.documents.green_print_adapter import RegisteredPair

NOW=datetime(2026,8,20,8,tzinfo=timezone.utc)
PDF=b"%PDF-1.4\nfixture\n%%EOF"
PAIR=RegisteredPair("green-1","printer-1","weekly-a4","registry-v1")


def envelope(**changes):
    value={"job_id":"JOB-1","document_id":"WWS-20260820","document_version":"WWS-20260820.r1.abcdef123456",
      "document_revision":1,"document_type":"farm.weekly_weight_sheet.v1","generator_id":"web.print_sheets.v1",
      "pdf_sha256":sha256(PDF).hexdigest(),"canonical_input_sha256":"b"*64,
      "retrieval_url":"https://documents.internal/api/documents/WWS-20260820/versions/WWS-20260820.r1.abcdef123456/pdf",
      "green_id":"green-1","printer_id":"printer-1","cups_queue_id":"weekly-a4","registry_version":"registry-v1",
      "authorization_receipt_id":"AUTH-1","authorization_expires_at":NOW+timedelta(hours=1),
      "options":{"media":"A4","copies":1,"color":"monochrome","sides":"one-sided"}}
    value.update(changes); return value


def test_cycle_persists_attempt_before_one_submission_and_deletes_pdf(tmp_path):
    ledger=GreenAdapterLedger(tmp_path/"ledger.db"); calls=[]
    result=run_cycle(ledger=ledger,envelope=envelope(),registered_pair=PAIR,
      allowed_origin="https://documents.internal",worker_id="worker-1",observer_id="observer-1",
      retrieve_pdf=lambda _url:PDF,
      submit_cups=lambda path,queue,options,attempt:(calls.append((path,queue,options,attempt)) or "CUPS-42"),
      observe_cups=lambda _id:None,temp_dir=tmp_path,now=NOW)
    assert result["status"]=="submitted" and len(calls)==1
    assert any(event["event_type"]=="pre_submission_attempt" for event in ledger.events("JOB-1"))
    assert list(tmp_path.glob("JOB-1.*.pdf"))==[]


def test_restart_reconciles_known_cups_job_before_retry(tmp_path):
    ledger=GreenAdapterLedger(tmp_path/"ledger.db"); submissions=[]
    kwargs=dict(ledger=ledger,envelope=envelope(),registered_pair=PAIR,allowed_origin="https://documents.internal",
      worker_id="worker-1",observer_id="observer-1",retrieve_pdf=lambda _url:PDF,
      submit_cups=lambda *_args:(submissions.append(1) or "CUPS-42"),temp_dir=tmp_path,now=NOW)
    run_cycle(observe_cups=lambda _id:None,**kwargs)
    evidence={"observer_id":"observer-1","job_id":"JOB-1","document_id":"WWS-20260820",
      "document_version":"WWS-20260820.r1.abcdef123456","pdf_sha256":sha256(PDF).hexdigest(),
      "printer_id":"printer-1","cups_queue_id":"weekly-a4","submission_attempt_id":ledger.get("JOB-1")["attempt_id"],
      "cups_job_id":"CUPS-42","cups_state":"completed","observed_at":NOW+timedelta(minutes=1)}
    result=run_cycle(observe_cups=lambda _id:evidence,**{**kwargs,"now":NOW+timedelta(minutes=1)})
    assert result=={"status":"provider_completed","submitted":False}
    assert len(submissions)==1


def test_concurrent_claim_has_one_winner(tmp_path):
    ledger=GreenAdapterLedger(tmp_path/"ledger.db")
    stored={**envelope(),"authorization_expires_at":envelope()["authorization_expires_at"].isoformat()}
    ledger.ingest(stored,now=NOW)
    with ThreadPoolExecutor(max_workers=2) as pool:
        tokens=list(pool.map(lambda worker:ledger.claim("JOB-1",worker_id=worker,now=NOW),["w1","w2"]))
    assert sum(bool(token) for token in tokens)==1


def test_ambiguous_submission_never_retries(tmp_path):
    ledger=GreenAdapterLedger(tmp_path/"ledger.db"); calls=[]
    result=run_cycle(ledger=ledger,envelope=envelope(),registered_pair=PAIR,allowed_origin="https://documents.internal",
      worker_id="worker-1",observer_id="observer-1",retrieve_pdf=lambda _url:PDF,
      submit_cups=lambda *_args:(calls.append(1) or (_ for _ in ()).throw(TimeoutError())),
      observe_cups=lambda _id:None,temp_dir=tmp_path,now=NOW)
    assert result["status"]=="ambiguous" and len(calls)==1
    again=run_cycle(ledger=ledger,envelope=envelope(),registered_pair=PAIR,allowed_origin="https://documents.internal",
      worker_id="worker-2",observer_id="observer-1",retrieve_pdf=lambda _url:PDF,
      submit_cups=lambda *_args:calls.append(1),observe_cups=lambda _id:None,temp_dir=tmp_path,now=NOW+timedelta(minutes=1))
    assert again["status"]=="ambiguous" and len(calls)==1


def test_held_continue_keeps_job_and_requires_fresh_bound_authorization(tmp_path):
    ledger=GreenAdapterLedger(tmp_path/"ledger.db")
    stored={**envelope(),"authorization_expires_at":envelope()["authorization_expires_at"].isoformat()}
    ledger.ingest(stored,now=NOW)
    with ledger._connect() as db:
        db.execute("update jobs set state='held' where job_id='JOB-1'")
    continued={**stored,"authorization_receipt_id":"AUTH-2",
               "authorization_expires_at":(NOW+timedelta(hours=2)).isoformat()}
    ledger.continue_held("JOB-1",continued_envelope=continued,now=NOW+timedelta(hours=1))
    assert ledger.get("JOB-1")["state"]=="pending"
    assert "AUTH-2" in ledger.get("JOB-1")["envelope_json"]
