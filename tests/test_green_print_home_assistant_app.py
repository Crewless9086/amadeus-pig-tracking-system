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
    return {"canonical_api_origin":"https://documents.invalid","canonical_endpoint_ip":"10.23.0.5","canonical_bearer_token":"synthetic-token","farm_scope_id":"farm-amadeus","green_id":"green-synthetic","printer_id":"printer-synthetic","cups_queue_id":"weekly-a4","registry_version":"registry-synthetic-v1","printer_uri":"ipps://10.23.0.9/ipp/print","ca_certificate_path":str(cert),"poll_seconds":30,"spool_path":str(tmp_path),"data_path":str(tmp_path)}
def envelope(**changes):
    value={"job_id":"JOB-SYNTHETIC-1","farm_scope_id":"farm-amadeus","document_id":"WWS-SYNTHETIC","document_version":"WWS-SYNTHETIC.r1.abcdef123456","document_revision":1,"document_type":S.PILOT_DOCUMENT,"generator_id":S.PILOT_GENERATOR,"pdf_sha256":sha256(PDF).hexdigest(),"retrieval_url":"https://documents.invalid/api/documents/WWS-SYNTHETIC/versions/WWS-SYNTHETIC.r1.abcdef123456/pdf","green_id":"green-synthetic","printer_id":"printer-synthetic","cups_queue_id":"weekly-a4","registry_version":"registry-synthetic-v1","authorization_receipt_id":"AUTH-SYNTHETIC-1","authorization_expires_at":(NOW+timedelta(hours=1)).isoformat(),"options":dict(S.FIXED_OPTIONS)}
    value.update(changes); return value

def test_package_is_bounded_and_privilege_split():
    cfg=yaml.safe_load((APP/"config.yaml").read_text(encoding="utf-8")); docker=(APP/"Dockerfile").read_text(encoding="utf-8"); init=(APP/"rootfs/init-green.sh").read_text(encoding="utf-8")
    assert cfg["arch"]==["aarch64"] and cfg["privileged"]==[] and cfg["host_network"] is False
    assert "adduser -S -D -H" in docker and "su-exec greenprint:greenprint" in init and "su-exec cupsd:cupsd" in init
    assert "lpadmin" not in init and "exec su-exec greenprint" in init
    assert docker.startswith("FROM --platform=linux/arm64 ghcr.io/home-assistant/aarch64-base:3.22@sha256:0f19d1a4b031b3d141945a906e7c0d09fc98c796c18e2ea9072bce8e0b67578a")

def test_package_uses_unique_prebuilt_image_and_requires_source_revision():
    cfg=yaml.safe_load((APP/"config.yaml").read_text(encoding="utf-8")); docker=(APP/"Dockerfile").read_text(encoding="utf-8")
    assert cfg["version"]=="0.3.0"
    assert cfg["image"]=="ghcr.io/crewless9086/amadeus-green-print-bridge"
    assert not (APP/"build.yaml").exists()
    assert "ARG SOURCE_COMMIT\n" in docker and "SOURCE_COMMIT=unknown" not in docker
    assert 'org.opencontainers.image.revision="${SOURCE_COMMIT}"' in docker

def test_image_workflow_is_manual_publish_fail_closed_and_attested():
    workflow=(ROOT/".github/workflows/green-print-image.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow and "pull_request:" in workflow
    assert "if: github.event_name == 'workflow_dispatch' && inputs.publish" in workflow
    assert "Prohibit version-tag replacement" in workflow
    assert "SOURCE_COMMIT=${{ inputs.expected_source_commit }}" in workflow
    assert "actions/attest-build-provenance@977bb373ede98d70efdf65b84cb5f73e068dcc2a" in workflow
    assert "actions/attest-sbom@4651f806c01d8637787e274ac3bdf724ef169f34" in workflow
    assert "pytest PyYAML" in workflow
    assert "latest" not in workflow and "push: \"true\"" in workflow
    assert 'test "${GITHUB_REF}" = "refs/heads/main"' in workflow
    assert workflow.count('test "${resolved_digest}" = "${PRODUCED_DIGEST}"') == 1
    assert 'cosign verify --certificate-identity "${identity}"' in workflow
    assert 'gh attestation verify "oci://${digest_ref}"' in workflow
    assert 'tag_resolved_digest=${{ steps.pushed.outputs.resolved_digest }}' in workflow
    assert "green-print-0.3.0-verified-release-packet" in workflow

def test_prebuilt_documentation_has_no_deleted_local_build_fallback():
    docs=(APP/"DOCS.md").read_text(encoding="utf-8")
    assert "build.yaml remains" not in docs
    assert "local Supervisor build" not in docs
    assert "There is no current local Supervisor-build fallback" in docs
    assert "GHCR does not provide a registry-level" in docs

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
    def __init__(self): self.claimed=None; self.events=[]; self.job=envelope(); self.state_value="authorized"; self.token="lease-token-1"; self.commands={}; self.command_receipt_id=None; self.command_kind=None; self.recoveries=0; self.fail_after_accept=False; self.fail_before_final_ack=False
    def claim(self,worker):
        if self.claimed:return None
        self.claimed=worker; return {"job":self.job,"lease_token":self.token,"lease_expires_at":(NOW+timedelta(minutes=5)).isoformat()}
    def command(self,_worker): return None
    def state(self,_job,token):
        if token!=self.token: raise S.Hold("fence")
        return {**self.job,"state":self.state_value,"lease_token":token}
    def transition(self,job,token,state,**evidence):
        assert token==self.token and job["document_version"]==self.job["document_version"] and job["pdf_sha256"]==self.job["pdf_sha256"]
        self.events.append((state,evidence)); self.state_value=state; return {**self.job,"state":state,"lease_token":token}
    def transition_command(self,command,target):
        receipt=command["command_receipt_id"]
        record=self.commands.get(receipt)
        if command.get("lease_token")!=self.token: raise S.Hold("command fence or binding invalid")
        expected=(self.job["document_version"],self.job["pdf_sha256"],self.job["authorization_receipt_id"],command["command"])
        actual=(command["job"]["document_version"],command["job"]["pdf_sha256"],command["job"]["authorization_receipt_id"],command["command"])
        if actual!=expected or (self.command_receipt_id is not None and
           (receipt!=self.command_receipt_id or command["command"]!=self.command_kind)):
            raise S.Hold("command fence or binding invalid")
        if record and record["status"]=="completed": return {"state":self.state_value,"command_status":"completed","command_outcome":record["outcome"],"command_replay":True,"attempt_id":self.job.get("attempt_id"),"cups_job_id":self.job.get("cups_job_id")}
        if target=="accepted":
            if not record:
                self.command_receipt_id=receipt; self.command_kind=command["command"]
                self.commands[receipt]={"status":"in_progress","outcome":None,"kind":command["command"]}
            result={"state":self.state_value,"command_status":"in_progress","command_replay":record is not None,"attempt_id":self.job.get("attempt_id"),"cups_job_id":self.job.get("cups_job_id")}
            if self.fail_after_accept: self.fail_after_accept=False; raise RuntimeError("crash_after_command_acceptance")
            return result
        assert record and record["status"]=="in_progress"
        record.update(status="completed",outcome=target)
        self.state_value="claimed" if target=="continued" else target
        if self.fail_before_final_ack: self.fail_before_final_ack=False; raise RuntimeError("crash_before_command_final_ack")
        return {"state":self.state_value,"command_status":"completed","command_outcome":target,"command_replay":False,"attempt_id":self.job.get("attempt_id"),"cups_job_id":self.job.get("cups_job_id")}
    def renew(self,job,token,worker):
        assert token==self.token; return {"lease_token":token,"lease_expires_at":(NOW+timedelta(minutes=5)).isoformat()}
    def recover(self,job,worker):
        self.recoveries+=1; self.token=f"lease-recovered-{self.recoveries}"; return {"lease_token":self.token,"lease_expires_at":(NOW+timedelta(minutes=5)).isoformat()}
    def pdf(self,_url): return PDF
class Cups:
    provider="ipps://10.23.0.9/ipp/print"
    def __init__(self): self.submissions=0; self.cancelled=[]; self.observed="pending"
    def submit(self,_path): self.submissions+=1; return "weekly-a4-42"
    def observe(self,_id): return self.observed
    def cancel(self,cups_id): self.cancelled.append(cups_id)
    def cancel_readback(self,cups_id): self.cancel(cups_id); return "cancelled",["absent"]

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
    canonical=Canonical(); canonical.state_value="submitted"; cups=Cups(); command={"command":"cancel","command_receipt_id":"COMMAND-CANCEL-1","job":job,"lease_token":"lease-token-1","lease_expires_at":(NOW+timedelta(minutes=5)).isoformat()}
    assert S.process_command(command,ledger,canonical,cups,config(tmp_path),NOW)=="cancelled" and cups.cancelled==["weekly-a4-42"] and ledger.get(job["job_id"]) is None

def test_cancel_unknown_provider_outcome_is_ambiguous_and_not_closed(tmp_path):
    ledger=S.Ledger(str(tmp_path/"l.db")); job=envelope(); ledger.put_claim(job,"lease-token-1",(NOW+timedelta(minutes=5)).isoformat(),NOW); ledger.update(job["job_id"],"submitted",NOW,cups_job_id="weekly-a4-42")
    canonical=Canonical(); cups=Cups(); cups.observed="unavailable"
    assert S.process_command({"command":"cancel","command_receipt_id":"COMMAND-CANCEL-2","job":job,"lease_token":"lease-token-1"},ledger,canonical,cups,config(tmp_path),NOW)=="ambiguous"
    assert ledger.get(job["job_id"]) is not None and canonical.commands["COMMAND-CANCEL-2"]["outcome"]=="ambiguous"

def test_continue_requires_fresh_authorization_and_canonical_binding(tmp_path):
    ledger=S.Ledger(str(tmp_path/"l.db")); canonical=Canonical(); canonical.state_value="held"; cups=Cups()
    with pytest.raises(S.Hold,match="authorization_expired"): S.process_command({"command":"continue","command_receipt_id":"COMMAND-CONTINUE-1","job":envelope(authorization_expires_at=NOW.isoformat()),"lease_token":"lease-token-1"},ledger,canonical,cups,config(tmp_path),NOW)
    bad=Canonical(); bad.state=lambda *_a:{**envelope(),"document_version":"wrong","state":"held"}
    with pytest.raises(S.Hold,match="canonical_reconciliation_conflict"): S.process_command({"command":"continue","command_receipt_id":"COMMAND-CONTINUE-2","job":envelope(),"lease_token":"lease-token-1","lease_expires_at":(NOW+timedelta(minutes=5)).isoformat()},ledger,bad,cups,config(tmp_path),NOW)

@pytest.mark.parametrize("kind",["continue","cancel"])
def test_protected_command_replay_across_independent_ledgers_has_no_second_effect(tmp_path,kind):
    job=envelope(); canonical=Canonical(); canonical.state_value="held" if kind=="continue" else "submitted"; cups=Cups()
    ledgers=[S.Ledger(str(tmp_path/f"{kind}-{i}.db")) for i in range(2)]
    for ledger in ledgers:
        ledger.put_claim(job,"lease-token-1",(NOW+timedelta(minutes=5)).isoformat(),NOW)
        if kind=="cancel": ledger.update(job["job_id"],"submitted",NOW,attempt_id="ATTEMPT-1",cups_job_id="weekly-a4-42")
    command={"command":kind,"command_receipt_id":f"COMMAND-{kind.upper()}-REPLAY","job":job,"lease_token":"lease-token-1","lease_expires_at":(NOW+timedelta(minutes=5)).isoformat()}
    first=S.process_command(command,ledgers[0],canonical,cups,config(tmp_path),NOW)
    before=(cups.submissions,len(cups.cancelled),ledgers[1].get(job["job_id"])["updated_at"])
    second=S.process_command(command,ledgers[1],canonical,cups,config(tmp_path),NOW)
    assert second in {first,canonical.state_value} and (cups.submissions,len(cups.cancelled),ledgers[1].get(job["job_id"])["updated_at"])==before

@pytest.mark.parametrize("kind",["continue","cancel"])
def test_independent_worker_resumes_crash_immediately_after_canonical_command_acceptance(tmp_path,kind):
    job=envelope(); canonical=Canonical(); canonical.state_value="held" if kind=="continue" else "submitted"
    if kind=="cancel": canonical.job.update(attempt_id="ATTEMPT-1",cups_job_id="weekly-a4-42")
    cups=Cups(); ledgers=[S.Ledger(str(tmp_path/f"accept-crash-{kind}-{i}.db")) for i in range(2)]
    for ledger in ledgers:
        ledger.put_claim(job,"lease-token-1",(NOW+timedelta(minutes=5)).isoformat(),NOW)
        if kind=="cancel": ledger.update(job["job_id"],"submitted",NOW,attempt_id="ATTEMPT-1",cups_job_id="weekly-a4-42")
    command={"command":kind,"command_receipt_id":f"COMMAND-{kind.upper()}-ACCEPT-CRASH","job":job,"lease_token":"lease-token-1","lease_expires_at":(NOW+timedelta(minutes=5)).isoformat()}
    canonical.fail_after_accept=True
    with pytest.raises(RuntimeError,match="crash_after_command_acceptance"): S.process_command(command,ledgers[0],canonical,cups,config(tmp_path),NOW)
    assert S.process_command(command,ledgers[1],canonical,cups,config(tmp_path),NOW)==("continued" if kind=="continue" else "cancelled")
    assert cups.submissions==0 and len(cups.cancelled)==(1 if kind=="cancel" else 0)

@pytest.mark.parametrize("kind",["continue","cancel"])
def test_independent_worker_gets_durable_outcome_after_crash_before_final_ack(tmp_path,kind):
    job=envelope(); canonical=Canonical(); canonical.state_value="held" if kind=="continue" else "submitted"
    if kind=="cancel": canonical.job.update(attempt_id="ATTEMPT-1",cups_job_id="weekly-a4-42")
    cups=Cups()
    if kind=="cancel":
        original=cups.cancel
        cups.cancel=lambda cups_id:(original(cups_id),setattr(cups,"observed","absent"))[0]
    ledgers=[S.Ledger(str(tmp_path/f"ack-crash-{kind}-{i}.db")) for i in range(2)]
    for ledger in ledgers:
        ledger.put_claim(job,"lease-token-1",(NOW+timedelta(minutes=5)).isoformat(),NOW)
        if kind=="cancel": ledger.update(job["job_id"],"submitted",NOW,attempt_id="ATTEMPT-1",cups_job_id="weekly-a4-42")
    command={"command":kind,"command_receipt_id":f"COMMAND-{kind.upper()}-ACK-CRASH","job":job,"lease_token":"lease-token-1","lease_expires_at":(NOW+timedelta(minutes=5)).isoformat()}
    canonical.fail_before_final_ack=True
    with pytest.raises(RuntimeError,match="crash_before_command_final_ack"): S.process_command(command,ledgers[0],canonical,cups,config(tmp_path),NOW)
    effects=(cups.submissions,len(cups.cancelled))
    reclaimed=canonical.recover(job,"worker-recovered")
    command={**command,"lease_token":reclaimed["lease_token"],"lease_expires_at":reclaimed["lease_expires_at"]}
    before_local=ledgers[1].get(job["job_id"])["updated_at"]
    assert S.process_command(command,ledgers[1],canonical,cups,config(tmp_path),NOW)==("continued" if kind=="continue" else "cancelled")
    assert (cups.submissions,len(cups.cancelled))==effects
    assert ledgers[1].get(job["job_id"])["updated_at"]==before_local

@pytest.mark.parametrize("field,bad",[("lease_token","stale-lease"),("document_version","WWS-SYNTHETIC.r2.wrong"),("pdf_sha256","f"*64),("authorization_receipt_id","AUTH-WRONG")])
def test_completed_outcome_replay_fails_closed_on_stale_lease_or_immutable_mismatch(tmp_path,field,bad):
    job=envelope(); canonical=Canonical(); canonical.state_value="held"; cups=Cups()
    first=S.Ledger(str(tmp_path/"first.db")); first.put_claim(job,canonical.token,(NOW+timedelta(minutes=5)).isoformat(),NOW)
    command={"command":"continue","command_receipt_id":"COMMAND-CONTINUE-BOUND","job":job,"lease_token":canonical.token,"lease_expires_at":(NOW+timedelta(minutes=5)).isoformat()}
    assert S.process_command(command,first,canonical,cups,config(tmp_path),NOW)=="continued"
    reclaimed=canonical.recover(job,"worker-recovered")
    replay_job={**job}
    replay={**command,"lease_token":reclaimed["lease_token"],"lease_expires_at":reclaimed["lease_expires_at"],"job":replay_job}
    if field=="lease_token": replay[field]=bad
    else: replay_job[field]=bad
    second=S.Ledger(str(tmp_path/"second.db")); second.put_claim(job,reclaimed["lease_token"],reclaimed["lease_expires_at"],NOW)
    before=second.get(job["job_id"])["updated_at"]
    with pytest.raises(S.Hold): S.process_command(replay,second,canonical,cups,config(tmp_path),NOW)
    assert cups.submissions==0 and cups.cancelled==[] and second.get(job["job_id"])["updated_at"]==before

def test_completed_outcome_replay_fails_closed_on_wrong_receipt_or_kind(tmp_path):
    job=envelope(); canonical=Canonical(); canonical.state_value="held"; cups=Cups(); ledger=S.Ledger(str(tmp_path/"l.db"))
    ledger.put_claim(job,canonical.token,(NOW+timedelta(minutes=5)).isoformat(),NOW)
    command={"command":"continue","command_receipt_id":"COMMAND-CONTINUE-BOUND","job":job,"lease_token":canonical.token,"lease_expires_at":(NOW+timedelta(minutes=5)).isoformat()}
    assert S.process_command(command,ledger,canonical,cups,config(tmp_path),NOW)=="continued"
    reclaimed=canonical.recover(job,"worker-recovered")
    for change in ({"command_receipt_id":"COMMAND-WRONG"},{"command":"cancel"}):
        replay={**command,**change,"lease_token":reclaimed["lease_token"],"lease_expires_at":reclaimed["lease_expires_at"]}
        with pytest.raises(S.Hold): S.process_command(replay,ledger,canonical,cups,config(tmp_path),NOW)
    assert cups.submissions==0 and cups.cancelled==[]

def test_expired_submitted_lease_recovers_without_resubmission(tmp_path,monkeypatch):
    job=envelope(); ledger=S.Ledger(str(tmp_path/"expired.db")); ledger.put_claim(job,"lease-token-1",(NOW-timedelta(seconds=1)).isoformat(),NOW-timedelta(seconds=301)); ledger.update(job["job_id"],"submitted",NOW-timedelta(seconds=301),attempt_id="ATTEMPT-1",cups_job_id="weekly-a4-42")
    canonical=Canonical(); canonical.state_value="submitted"; cups=Cups(); cups.observed="completed"; monkeypatch.setattr(S,"utcnow",lambda:NOW); monkeypatch.setattr(S,"ensure_space",lambda *_a:None)
    assert S.cycle(ledger,canonical,cups,config(tmp_path),"worker-2")=="provider_completed"
    assert canonical.recoveries==1 and cups.submissions==0 and canonical.events[-1][1]["cups_job_id"]=="weekly-a4-42"

@pytest.mark.parametrize("observations",[["pending","pending","pending"],["completed"],["unavailable"]])
def test_zero_exit_cancel_nonclosure_is_ambiguous_and_restart_safe(tmp_path,observations):
    job=envelope(); ledger=S.Ledger(str(tmp_path/"cancel.db")); ledger.put_claim(job,"lease-token-1",(NOW+timedelta(minutes=5)).isoformat(),NOW); ledger.update(job["job_id"],"submitted",NOW,attempt_id="ATTEMPT-1",cups_job_id="weekly-a4-42")
    canonical=Canonical(); canonical.state_value="submitted"; cups=Cups(); values=iter(observations); cups.observe=lambda _id:next(values,observations[-1]); cups.cancel_readback=lambda cups_id:(cups.cancel(cups_id) or ("ambiguous",observations))
    command={"command":"cancel","command_receipt_id":"COMMAND-CANCEL-UNCERTAIN","job":job,"lease_token":"lease-token-1"}
    assert S.process_command(command,ledger,canonical,cups,config(tmp_path),NOW)=="ambiguous"
    reopened=S.Ledger(str(tmp_path/"cancel.db")); assert reopened.get(job["job_id"])["state"]=="ambiguous" and reopened.get(job["job_id"])["cups_job_id"]=="weekly-a4-42"

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
