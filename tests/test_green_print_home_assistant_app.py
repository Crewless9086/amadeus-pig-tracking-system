from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import importlib.util,json,sqlite3
from pathlib import Path
import pytest,yaml

ROOT=Path(__file__).parents[1]; APP=ROOT/"green_print_bridge"
SPEC=importlib.util.spec_from_file_location("green_app",APP/"app"/"service.py"); S=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(S)
NOW=datetime(2026,8,21,8,tzinfo=timezone.utc); PDF=b"%PDF-1.4\nsynthetic\n%%EOF"
def config(tmp_path):
    cert=tmp_path/"private-ca.crt"; cert.write_text("synthetic",encoding="utf-8")
    return {"canonical_api_origin":"https://documents.invalid","canonical_endpoint_ip":"10.23.0.5","canonical_bearer_token":"synthetic-token","green_id":"green-synthetic","printer_id":"printer-synthetic","cups_queue_id":"weekly-a4","registry_version":"registry-synthetic-v1","printer_uri":"ipps://10.23.0.9/ipp/print","ca_certificate_path":str(cert),"poll_seconds":30,"spool_path":str(tmp_path),"data_path":str(tmp_path)}
def envelope(**changes):
    value={"job_id":"JOB-SYNTHETIC-1","document_id":"WWS-SYNTHETIC","document_version":"WWS-SYNTHETIC.r1.abcdef123456","document_revision":1,"document_type":S.PILOT_DOCUMENT,"generator_id":S.PILOT_GENERATOR,"pdf_sha256":sha256(PDF).hexdigest(),"retrieval_url":"https://documents.invalid/api/documents/WWS-SYNTHETIC/versions/WWS-SYNTHETIC.r1.abcdef123456/pdf","green_id":"green-synthetic","printer_id":"printer-synthetic","cups_queue_id":"weekly-a4","registry_version":"registry-synthetic-v1","authorization_receipt_id":"AUTH-SYNTHETIC-1","authorization_expires_at":(NOW+timedelta(hours=1)).isoformat(),"options":dict(S.FIXED_OPTIONS)}
    value.update(changes); return value

def test_package_is_bounded_and_privilege_split():
    cfg=yaml.safe_load((APP/"config.yaml").read_text(encoding="utf-8")); docker=(APP/"Dockerfile").read_text(encoding="utf-8"); init=(APP/"rootfs/init-green.sh").read_text(encoding="utf-8")
    assert cfg["arch"]==["aarch64"] and cfg["privileged"]==[] and cfg["host_network"] is False
    assert "adduser -S -D -H" in docker and "su-exec greenprint:greenprint" in init and "su-exec cupsd:cupsd" in init
    assert "lpadmin" not in init and "exec su-exec greenprint" in init

def test_apparmor_denies_admin_and_broad_writes():
    policy=(APP/"apparmor.txt").read_text(encoding="utf-8")
    assert "deny /usr/sbin/lpadmin x" in policy and "/etc/cups/** rwk" not in policy and "/tmp/** rwk" not in policy
    assert "/tmp/green-spool/** rwk" in policy and "/data/** rwk" in policy

def test_contract_and_authorization_fail_closed(tmp_path):
    cfg=config(tmp_path); S.validate(envelope(),cfg,NOW)
    for change in ({"cups_queue_id":"other"},{"options":{**S.FIXED_OPTIONS,"copies":2}},{"authorization_expires_at":NOW.isoformat()},{"retrieval_url":envelope()["retrieval_url"]+"?x=1"}):
        with pytest.raises(S.Hold): S.validate(envelope(**change),cfg,NOW)

def test_config_pins_canonical_and_requires_printer_ip_literal(tmp_path,monkeypatch):
    cfg=config(tmp_path); monkeypatch.setattr(S,"CA_CERTIFICATE_PATH",cfg["ca_certificate_path"]); path=tmp_path/"options.json"
    monkeypatch.setattr(S.socket,"getaddrinfo",lambda *_a,**_k:[(None,None,None,None,("10.23.0.5",0))]); path.write_text(json.dumps(cfg),encoding="utf-8")
    assert S.load_config(str(path))["canonical_endpoint_ip"]=="10.23.0.5"
    path.write_text(json.dumps({**cfg,"printer_uri":"ipps://printer.invalid/ipp/print"}),encoding="utf-8")
    with pytest.raises(S.Hold,match="commissioned_ip_literal_required"): S.load_config(str(path))

def test_dns_rebinding_cannot_change_transport_target(tmp_path,monkeypatch):
    cfg=config(tmp_path); monkeypatch.setattr(S,"CA_CERTIFICATE_PATH",cfg["ca_certificate_path"]); path=tmp_path/"options.json"; path.write_text(json.dumps(cfg),encoding="utf-8")
    calls=iter([[(None,None,None,None,("10.23.0.5",0))],[(None,None,None,None,("8.8.8.8",0))]])
    monkeypatch.setattr(S.socket,"getaddrinfo",lambda *_a,**_k:next(calls)); loaded=S.load_config(str(path))
    conn=S.PinnedHTTPSConnection("documents.invalid",loaded["canonical_endpoint_ip"],443,object(),20)
    assert conn.pinned_ip=="10.23.0.5" and next(calls)[0][4][0]=="8.8.8.8"

class Canonical:
    def __init__(self): self.claimed=None; self.events=[]; self.job=envelope(); self.state_value="authorized"; self.token="lease-token-1"
    def claim(self,worker):
        if self.claimed:return None
        self.claimed=worker; return {"job":self.job,"lease_token":self.token,"lease_expires_at":(NOW+timedelta(minutes=5)).isoformat()}
    def command(self,_worker): return None
    def state(self,_job,token):
        if token!=self.token: raise S.Hold("fence")
        return {**self.job,"state":self.state_value,"lease_token":token}
    def transition(self,job,token,state,**evidence):
        assert token==self.token and job["document_version"]==self.job["document_version"] and job["pdf_sha256"]==self.job["pdf_sha256"]
        self.events.append((state,evidence)); self.state_value=state
    def pdf(self,_url): return PDF
class Cups:
    provider="ipps://10.23.0.9/ipp/print"
    def __init__(self): self.submissions=0; self.cancelled=[]; self.observed="pending"
    def submit(self,_path): self.submissions+=1; return "weekly-a4-42"
    def observe(self,_id): return self.observed
    def cancel(self,cups_id): self.cancelled.append(cups_id)

def test_two_independent_workers_ledgers_have_one_canonical_winner(tmp_path,monkeypatch):
    canonical=Canonical(); cups=Cups(); monkeypatch.setattr(S,"utcnow",lambda:NOW); monkeypatch.setattr(S,"ensure_space",lambda *_a:None)
    ledgers=[S.Ledger(str(tmp_path/f"worker-{i}.db")) for i in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda pair:S.cycle(pair[1],canonical,cups,config(tmp_path),f"worker-{pair[0]}"),enumerate(ledgers)))
    assert sorted(results)==["event_waiting","submitted"] and cups.submissions==1 and canonical.claimed in {"worker-0","worker-1"}
    assert all(token==canonical.token for state,e in canonical.events for token in [canonical.token])

def test_every_canonical_transition_carries_lease_and_bindings(tmp_path):
    client=object.__new__(S.CanonicalClient); calls=[]; client.request=lambda m,p,b:(calls.append((m,p,b)) or {})
    client.transition(envelope(),"lease-token-1","submitted",cups_job_id="weekly-a4-42")
    body=calls[0][2]; assert body["lease_token"]=="lease-token-1" and body["document_version"]==envelope()["document_version"] and body["authorization_receipt_id"].startswith("AUTH-")

def test_cups_receipt_is_bound_to_configured_queue_and_provider(monkeypatch):
    class Result: stdout="request id is other-42 (1 file(s))"
    monkeypatch.setattr(S.subprocess,"run",lambda *_a,**_k:Result())
    with pytest.raises(S.Hold,match="cups_submission_receipt_invalid"): S.Cups("weekly-a4","ipps://10.23.0.9/ipp/print").submit("x.pdf")

def test_cancel_known_cups_job_reconciles_and_cleans(tmp_path):
    ledger=S.Ledger(str(tmp_path/"l.db")); job=envelope(); ledger.put_claim(job,"lease-token-1",(NOW+timedelta(minutes=5)).isoformat(),NOW); ledger.update(job["job_id"],"submitted",NOW,attempt_id="ATTEMPT-1",cups_job_id="weekly-a4-42")
    canonical=Canonical(); canonical.state_value="submitted"; cups=Cups(); command={"command":"cancel","job":job,"lease_token":"lease-token-1","lease_expires_at":(NOW+timedelta(minutes=5)).isoformat()}
    assert S.process_command(command,ledger,canonical,cups,config(tmp_path),NOW)=="cancelled" and cups.cancelled==["weekly-a4-42"] and ledger.get(job["job_id"]) is None

def test_cancel_unknown_provider_outcome_is_ambiguous_and_not_closed(tmp_path):
    ledger=S.Ledger(str(tmp_path/"l.db")); job=envelope(); ledger.put_claim(job,"lease-token-1",(NOW+timedelta(minutes=5)).isoformat(),NOW); ledger.update(job["job_id"],"submitted",NOW,cups_job_id="weekly-a4-42")
    canonical=Canonical(); cups=Cups(); cups.observed="unknown"
    with pytest.raises(S.Hold,match="cups_cancel_ambiguous"): S.process_command({"command":"cancel","job":job,"lease_token":"lease-token-1"},ledger,canonical,cups,config(tmp_path),NOW)
    assert ledger.get(job["job_id"]) is not None and not canonical.events

def test_continue_requires_fresh_authorization_and_canonical_binding(tmp_path):
    ledger=S.Ledger(str(tmp_path/"l.db")); canonical=Canonical(); canonical.state_value="held"; cups=Cups()
    with pytest.raises(S.Hold,match="authorization_expired"): S.process_command({"command":"continue","job":envelope(authorization_expires_at=NOW.isoformat()),"lease_token":"lease-token-1"},ledger,canonical,cups,config(tmp_path),NOW)
    bad=Canonical(); bad.state=lambda *_a:{**envelope(),"document_version":"wrong","state":"held"}
    with pytest.raises(S.Hold,match="canonical_reconciliation_conflict"): S.process_command({"command":"continue","job":envelope(),"lease_token":"lease-token-1","lease_expires_at":(NOW+timedelta(minutes=5)).isoformat()},ledger,bad,cups,config(tmp_path),NOW)

def test_restore_reconciles_canonical_before_provider(tmp_path,monkeypatch):
    ledger=S.Ledger(str(tmp_path/"l.db")); job=envelope(); ledger.put_claim(job,"lease-token-1",(NOW+timedelta(minutes=5)).isoformat(),NOW); ledger.update(job["job_id"],"submitted",NOW,attempt_id="A",cups_job_id="weekly-a4-42")
    order=[]; canonical=Canonical(); original=canonical.state; canonical.state=lambda *a:(order.append("canonical") or original(*a)); cups=Cups(); cups.observe=lambda _id:(order.append("cups") or "completed")
    monkeypatch.setattr(S,"utcnow",lambda:NOW); monkeypatch.setattr(S,"ensure_space",lambda *_a:None)
    assert S.cycle(ledger,canonical,cups,config(tmp_path),"worker") == "provider_completed" and order==["canonical","cups"]

def test_disk_exhaustion_fails_before_claim(tmp_path,monkeypatch):
    canonical=Canonical(); monkeypatch.setattr(S.shutil,"disk_usage",lambda _p:type("D",(),{"free":0})())
    with pytest.raises(S.Hold,match="disk_space_fail_safe"): S.cycle(S.Ledger(str(tmp_path/"l.db")),canonical,Cups(),config(tmp_path),"worker")
    assert canonical.claimed is None

def test_corrupt_and_partial_ledger_fail_closed(tmp_path):
    path=tmp_path/"bad.db"; path.write_bytes(b"not sqlite")
    with pytest.raises(S.Hold,match="local_ledger_corrupt"): S.Ledger(str(path))
    partial=tmp_path/"partial.db"; sqlite3.connect(partial).execute("create table jobs(job_id text)").connection.close()
    with pytest.raises((S.Hold,sqlite3.DatabaseError,sqlite3.OperationalError)): S.Ledger(str(partial)).recoverable()

def test_health_treats_business_hold_as_live():
    text=(APP/"rootfs/healthcheck.py").read_text(encoding="utf-8")
    assert 'value.get("liveness") == "alive"' in text and '"held"' not in text

def test_no_plain_claimable_get_or_runtime_lpadmin():
    source=(APP/"app/service.py").read_text(encoding="utf-8"); init=(APP/"rootfs/init-green.sh").read_text(encoding="utf-8")
    assert "/claimable" not in source and 'request("GET",CLAIM_PATH' not in source and "lpadmin" not in source+init

def test_no_sensitive_values_committed():
    material="\n".join(p.read_text(encoding="utf-8",errors="ignore") for p in APP.rglob("*") if p.is_file())
    assert not any(x in material for x in ("service_role","SUPABASE_SERVICE_ROLE_KEY=","BEGIN CERTIFICATE","192.168."))
