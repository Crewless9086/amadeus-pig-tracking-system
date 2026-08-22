"""Fail-closed Green worker for the fixed weekly-sheet pilot.

Supabase/Documents owns claims, leases, commands and transitions. SQLite is
only content-free crash evidence and never an authority/fencing rail.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import http.client, ipaddress, json, os, re, shutil, socket, sqlite3, ssl, subprocess, time, uuid
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

PILOT_DOCUMENT="farm.weekly_weight_sheet.v1"; PILOT_GENERATOR="web.print_sheets.v1"
CLAIM_PATH="/api/documents/print-jobs/claims"; COMMAND_PATH="/api/documents/print-jobs/commands/claim"
CANONICAL_INTAKE_PATH=CLAIM_PATH; CA_CERTIFICATE_PATH="/config/private-ca.crt"
PRIVATE_PINNED="private_pinned"; PUBLIC_PKI_EXACT_ORIGIN="public_pki_exact_origin"
APPROVED_PUBLIC_CANONICAL_ORIGIN="https://amadeus-pig-tracking-system.onrender.com"
FIXED_OPTIONS={"media":"A4","copies":1,"color":"monochrome","sides":"one-sided"}
ID=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"); DIGEST=re.compile(r"^[0-9a-f]{64}$")
TERMINAL={"provider_completed","physically_confirmed","cancelled","ambiguous"}; MIN_FREE_BYTES=64*1024*1024
CANCEL_READBACK_ATTEMPTS=3

class Hold(RuntimeError): pass
def utcnow(): return datetime.now(timezone.utc)
def iso(v): return v.astimezone(timezone.utc).isoformat()
def canonical_json(v): return json.dumps(v,sort_keys=True,separators=(",",":"),default=str)
def parse_time(v):
    parsed=datetime.fromisoformat(str(v).replace("Z","+00:00")) if v else None
    if parsed is not None and parsed.tzinfo is None: raise Hold("timestamp_timezone_required")
    return parsed

class Ledger:
    """Disposable local recovery evidence; canonical state is checked first."""
    def __init__(self,path):
        self.path=path; Path(path).parent.mkdir(parents=True,exist_ok=True)
        try:
            with self.connect() as db:
                db.executescript("""create table if not exists jobs(job_id text primary key,envelope_json text not null,envelope_sha256 text not null,state text not null,lease_token text not null,lease_until text not null,attempt_id text,cups_job_id text,updated_at text not null,last_error text);create table if not exists events(event_id text primary key,job_id text not null,event_type text not null,event_at text not null,metadata_json text not null);""")
                if db.execute("pragma integrity_check").fetchone()[0] != "ok": raise Hold("local_ledger_corrupt")
        except sqlite3.DatabaseError as exc: raise Hold("local_ledger_corrupt") from exc
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10,isolation_level=None); db.row_factory=sqlite3.Row
        db.execute("pragma journal_mode=WAL"); db.execute("pragma synchronous=FULL"); return db
    def put_claim(self,envelope,token,lease_until,now):
        material=canonical_json(envelope); digest=sha256(material.encode()).hexdigest()
        with self.connect() as db:
            db.execute("begin immediate"); row=db.execute("select envelope_sha256 from jobs where job_id=?",(envelope["job_id"],)).fetchone()
            if row and row[0]!=digest: raise Hold("job_identity_envelope_conflict")
            db.execute("insert into jobs values(?,?,?,?,?,?,?,?,?,?) on conflict(job_id) do update set lease_token=excluded.lease_token,lease_until=excluded.lease_until,updated_at=excluded.updated_at",(envelope["job_id"],material,digest,"claimed",token,lease_until,None,None,iso(now),None))
    def renew(self,job_id,token,lease_until,now):
        with self.connect() as db:
            db.execute("begin immediate")
            if db.execute("update jobs set lease_token=?,lease_until=?,updated_at=? where job_id=?",(token,lease_until,iso(now),job_id)).rowcount!=1: raise Hold("local_recovery_row_missing")
    def get(self,job_id):
        try:
            with self.connect() as db:
                row=db.execute("select * from jobs where job_id=?",(job_id,)).fetchone(); return dict(row) if row else None
        except sqlite3.DatabaseError as exc: raise Hold("local_ledger_corrupt") from exc
    def recoverable(self):
        try:
            with self.connect() as db: return [dict(x) for x in db.execute("select * from jobs where attempt_id is not null and state in ('submitting','submitted') order by updated_at")]
        except sqlite3.DatabaseError as exc: raise Hold("local_ledger_corrupt") from exc
    def update(self,job_id,state,now,attempt_id=None,cups_job_id=None,error=None):
        with self.connect() as db:
            db.execute("begin immediate")
            if not db.execute("select 1 from jobs where job_id=?",(job_id,)).fetchone(): raise Hold("local_recovery_row_missing")
            db.execute("update jobs set state=?,attempt_id=coalesce(?,attempt_id),cups_job_id=coalesce(?,cups_job_id),updated_at=?,last_error=? where job_id=?",(state,attempt_id,cups_job_id,iso(now),error,job_id))
    def clear(self,job_id):
        with self.connect() as db: db.execute("delete from jobs where job_id=?",(job_id,))

def validate(e,c,now):
    required=("job_id","farm_scope_id","document_id","document_version","document_revision","pdf_sha256","retrieval_url","green_id","printer_id","cups_queue_id","registry_version","authorization_receipt_id","authorization_expires_at")
    if any(e.get(k) in (None,"") for k in required): raise Hold("required_binding_missing")
    if e.get("document_type")!=PILOT_DOCUMENT or e.get("generator_id")!=PILOT_GENERATOR: raise Hold("document_or_generator_not_allowlisted")
    if e.get("options")!=FIXED_OPTIONS: raise Hold("print_options_not_allowlisted")
    for k in ("job_id","farm_scope_id","document_id","document_version","green_id","printer_id","cups_queue_id","registry_version","authorization_receipt_id"):
        if not ID.fullmatch(str(e[k])): raise Hold("invalid_identity")
    for k in ("farm_scope_id","green_id","printer_id","cups_queue_id","registry_version"):
        if e[k]!=c[k]: raise Hold("registered_identity_pair_mismatch")
    if not DIGEST.fullmatch(str(e["pdf_sha256"]).lower()): raise Hold("invalid_pdf_digest")
    if parse_time(e["authorization_expires_at"])<=now: raise Hold("authorization_expired")
    origin,url=urlparse(c["canonical_api_origin"]),urlparse(e["retrieval_url"]); expected=f"/api/documents/{e['document_id']}/versions/{e['document_version']}/pdf"
    if (url.scheme,url.hostname,url.port)!=("https",origin.hostname,origin.port) or url.username or url.password or url.query or url.fragment or unquote(url.path)!=expected: raise Hold("unsafe_or_unbound_retrieval_url")

def private_addresses(hostname):
    try: values={ipaddress.ip_address(x[4][0]) for x in socket.getaddrinfo(hostname,None,type=socket.SOCK_STREAM)}
    except (OSError,ValueError,TypeError) as exc: raise Hold("private_endpoint_resolution_failed") from exc
    if not values or any(not (x.is_private or x.is_link_local) for x in values): raise Hold("public_endpoint_forbidden")
    return tuple(sorted(map(str,values)))

def printer_tls_preflight(hostname,pinned_ip,port,ca_certificate_path):
    """Require a trusted SAN identity while connecting only to the commissioned IP."""
    context=ssl.create_default_context(cafile=ca_certificate_path)
    context.check_hostname=True
    context.hostname_checks_common_name=False
    raw=socket.create_connection((pinned_ip,port),10)
    try:
        tls=context.wrap_socket(raw,server_hostname=hostname)
        tls.close()
    except Exception:
        raw.close()
        raise

class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to commissioned IP while verifying the configured TLS name."""
    def __init__(self,hostname,pinned_ip,port,context,timeout): super().__init__(hostname,port=port,context=context,timeout=timeout); self.pinned_ip=pinned_ip
    def connect(self):
        raw=socket.create_connection((self.pinned_ip,self.port),self.timeout); self.sock=self._context.wrap_socket(raw,server_hostname=self.host)

class CanonicalClient:
    def __init__(self,c):
        self.config=c
        self.context=ssl.create_default_context(cafile=c["ca_certificate_path"]) if c["canonical_transport_profile"]==PRIVATE_PINNED else ssl.create_default_context()
        self.worker_id=None
    def connection(self,timeout):
        parsed=urlparse(self.config["canonical_api_origin"])
        if self.config["canonical_transport_profile"]==PRIVATE_PINNED:
            return PinnedHTTPSConnection(parsed.hostname,self.config["canonical_endpoint_ip"],parsed.port or 443,self.context,timeout)
        return http.client.HTTPSConnection(parsed.hostname,port=parsed.port or 443,context=self.context,timeout=timeout)
    def request(self,method,path,body=None):
        parsed=urlparse(self.config["canonical_api_origin"])
        if not path.startswith("/") or "?" in path or "#" in path: raise Hold("canonical_path_invalid")
        payload=canonical_json(body).encode() if body is not None else None; headers={"Authorization":"Bearer "+self.config["canonical_bearer_token"],"X-Amadeus-Farm-Scope-Id":self.config["farm_scope_id"],"X-Amadeus-Green-Id":self.config["green_id"],"Accept":"application/json","Host":parsed.netloc}
        if self.worker_id: headers["X-Amadeus-Worker-Id"]=self.worker_id
        if payload is not None: headers["Content-Type"]="application/json"
        conn=self.connection(20)
        try:
            conn.request(method,path,body=payload,headers=headers); response=conn.getresponse()
            if 300<=response.status<400: raise Hold("canonical_redirect_forbidden")
            if not 200<=response.status<300: raise Hold("canonical_http_"+str(response.status))
            data=response.read(1024*1024)
        finally: conn.close()
        return json.loads(data) if data else None
    def claim(self,worker_id):
        self.worker_id=worker_id
        value=self.request("POST",CLAIM_PATH,{"worker_id":worker_id,"lease_seconds":300}) or {}
        if not value.get("job"): return None
        if not ID.fullmatch(str(value.get("lease_token",""))) or parse_time(value.get("lease_expires_at"))<=utcnow(): raise Hold("canonical_claim_invalid")
        return value
    def state(self,job_id,token): return self.request("POST",f"/api/documents/print-jobs/{quote(job_id,safe='')}/reconcile",{"lease_token":token})
    def transition(self,job,token,state,**evidence):
        event_material=canonical_json({"job_id":job["job_id"],"state":state,**evidence})
        event_id=str(uuid.uuid5(uuid.NAMESPACE_URL,event_material))
        body={"event_id":event_id,"lease_token":token,"document_version":job["document_version"],"pdf_sha256":job["pdf_sha256"],"authorization_receipt_id":job["authorization_receipt_id"],"target_state":state,**evidence}
        return self.request("POST",f"/api/documents/print-jobs/{quote(job['job_id'],safe='')}/transition",body)
    def command(self,worker_id): self.worker_id=worker_id; return self.request("POST",COMMAND_PATH,{"worker_id":worker_id})
    def transition_command(self,command,target_state):
        job=command["job"]
        body={"lease_token":command["lease_token"],"document_version":job["document_version"],"pdf_sha256":job["pdf_sha256"],"authorization_receipt_id":job["authorization_receipt_id"],"command_receipt_id":command["command_receipt_id"],"command_kind":command["command"],"target_state":target_state}
        return self.request("POST",f"/api/documents/print-jobs/{quote(job['job_id'],safe='')}/commands/transition",body)
    def renew(self,job,token,worker_id):
        self.worker_id=worker_id
        body={"lease_token":token,"worker_id":worker_id,"lease_seconds":300,"document_version":job["document_version"],"pdf_sha256":job["pdf_sha256"],"authorization_receipt_id":job["authorization_receipt_id"]}
        return self.request("POST",f"/api/documents/print-jobs/{quote(job['job_id'],safe='')}/lease/renew",body)
    def recover(self,job,worker_id):
        self.worker_id=worker_id
        body={"worker_id":worker_id,"lease_seconds":300,"document_version":job["document_version"],"pdf_sha256":job["pdf_sha256"],"authorization_receipt_id":job["authorization_receipt_id"]}
        return self.request("POST",f"/api/documents/print-jobs/{quote(job['job_id'],safe='')}/lease/recover",body)
    def pdf(self,url):
        parsed=urlparse(url); origin=urlparse(self.config["canonical_api_origin"])
        if (parsed.scheme,parsed.hostname,parsed.port)!=("https",origin.hostname,origin.port): raise Hold("pdf_origin_mismatch")
        if parsed.query or parsed.fragment: raise Hold("pdf_url_invalid")
        conn=self.connection(30)
        try:
            headers={"Authorization":"Bearer "+self.config["canonical_bearer_token"],"X-Amadeus-Farm-Scope-Id":self.config["farm_scope_id"],"X-Amadeus-Green-Id":self.config["green_id"],"Host":parsed.netloc}
            if self.worker_id: headers["X-Amadeus-Worker-Id"]=self.worker_id
            conn.request("GET",parsed.path,headers=headers); response=conn.getresponse()
            if response.status!=200 or response.getheader("Content-Type","").split(";",1)[0].lower()!="application/pdf": raise Hold("pdf_response_invalid")
            return response.read(25*1024*1024+1)
        finally: conn.close()

class Cups:
    def __init__(self,queue,provider): self.queue=queue; self.provider=provider
    def submit(self,path):
        result=subprocess.run(["lp","-d",self.queue,"-n","1","-o","media=A4","-o","ColorModel=Gray","-o","sides=one-sided",path],check=True,capture_output=True,text=True,timeout=30)
        match=re.fullmatch(r"request id is ([A-Za-z0-9._-]+) \(\d+ file\(s\)\)\s*",result.stdout)
        if not match or not match.group(1).startswith(self.queue+"-") or not match.group(1)[len(self.queue)+1:].isdigit(): raise Hold("cups_submission_receipt_invalid")
        return match.group(1)
    def observe(self,cups_id):
        if not cups_id.startswith(self.queue+"-"): raise Hold("cups_queue_identity_mismatch")
        pending=subprocess.run(["lpstat","-W","all","-o",self.queue],capture_output=True,text=True,timeout=15)
        if pending.returncode!=0: return "unavailable"
        if cups_id in cups_job_ids(pending.stdout): return "pending"
        done=subprocess.run(["lpstat","-W","completed","-o",self.queue],capture_output=True,text=True,timeout=15)
        if done.returncode!=0: return "unavailable"
        return "completed" if cups_id in cups_job_ids(done.stdout) else "absent"
    def cancel(self,cups_id):
        if not cups_id.startswith(self.queue+"-"): raise Hold("cups_queue_identity_mismatch")
        result=subprocess.run(["cancel",cups_id],capture_output=True,text=True,timeout=15)
        if result.returncode!=0: raise Hold("cups_cancel_ambiguous")
    def cancel_readback(self,cups_id):
        self.cancel(cups_id); observations=[]
        for _ in range(CANCEL_READBACK_ATTEMPTS):
            observed=self.observe(cups_id); observations.append(observed)
            if observed=="absent": return "cancelled",observations
            if observed in {"completed","unavailable"}: break
        return "ambiguous",observations
def cups_job_ids(output): return {line.split()[0] for line in output.splitlines() if line.split()}
def ensure_space(path,required=MIN_FREE_BYTES):
    if shutil.disk_usage(path).free<required: raise Hold("disk_space_fail_safe")
def verify_printer_binding(config):
    hostname=urlparse(config["printer_uri"]).hostname
    try: literal=ipaddress.ip_address(hostname)
    except ValueError: literal=None
    answers=(str(literal),) if literal else private_addresses(hostname)
    if len(answers)!=1 or answers[0]!=config["printer_endpoint_ip"]: raise Hold("printer_dns_binding_ambiguous_or_drifted")

def process_command(command,ledger,client,cups,config,now):
    if not command: return None
    job=command.get("job") or {}; token=command.get("lease_token"); kind=command.get("command"); validate(job,config,now)
    receipt=command.get("command_receipt_id")
    if kind not in {"continue","cancel"} or not token or not ID.fullmatch(str(receipt or "")): raise Hold("protected_command_invalid")
    current=client.state(job["job_id"],token)
    if current.get("document_version")!=job["document_version"] or current.get("pdf_sha256")!=job["pdf_sha256"] or current.get("authorization_receipt_id")!=job["authorization_receipt_id"]: raise Hold("canonical_reconciliation_conflict")
    local=ledger.get(job["job_id"])
    accepted=client.transition_command(command,"accepted") or {}
    if accepted.get("command_status")=="completed":
        return accepted.get("command_outcome")
    if accepted.get("command_status")!="in_progress": raise Hold("command_acceptance_invalid")
    canonical_cups_id=accepted.get("cups_job_id") or current.get("cups_job_id")
    canonical_attempt=accepted.get("attempt_id") or current.get("attempt_id")
    if local and ((local.get("cups_job_id") and canonical_cups_id and local["cups_job_id"]!=canonical_cups_id) or
                  (local.get("attempt_id") and canonical_attempt and local["attempt_id"]!=canonical_attempt)):
        raise Hold("command_provider_identity_conflict")
    if kind=="cancel":
        cups_job_id=canonical_cups_id or (local or {}).get("cups_job_id")
        if cups_job_id:
            state=cups.observe(cups_job_id)
            if state=="pending": target,observations=cups.cancel_readback(cups_job_id)
            elif state=="absent": target,observations="cancelled",[state]
            else: target,observations="ambiguous",[state]
        else: target,observations="cancelled",["no_provider_job"]
        acknowledged=client.transition_command(command,target) or {}
        if target=="cancelled" and acknowledged.get("command_outcome")=="cancelled": ledger.clear(job["job_id"])
        elif local: ledger.update(job["job_id"],"ambiguous",now,error="cups_cancel_readback_ambiguous")
        return target
    if current.get("state") not in {"held","claimed"}: raise Hold("continue_state_invalid")
    if not local:
        ledger.put_claim(job,token,command["lease_expires_at"],now)
        if canonical_attempt or canonical_cups_id: ledger.update(job["job_id"],current.get("state","claimed"),now,attempt_id=canonical_attempt,cups_job_id=canonical_cups_id)
    else: ledger.renew(job["job_id"],token,command["lease_expires_at"],now)
    completed=client.transition_command(command,"continued") or {}
    if completed.get("command_outcome")!="continued": raise Hold("command_completion_invalid")
    return "continued"

def ensure_live_lease(local,job,client,ledger,worker_id,now):
    if parse_time(local["lease_until"])<=now:
        lease=client.recover(job,worker_id)
    else:
        lease=client.renew(job,local["lease_token"],worker_id)
    if not lease or not ID.fullmatch(str(lease.get("lease_token",""))) or parse_time(lease.get("lease_expires_at"))<=now: raise Hold("canonical_lease_refresh_invalid")
    ledger.renew(job["job_id"],lease["lease_token"],lease["lease_expires_at"],now); return lease["lease_token"]

def cycle(ledger,client,cups,config,worker_id):
    spool=config.get("spool_path","/tmp/green-spool")
    now=utcnow(); verify_printer_binding(config); ensure_space(config.get("data_path","/data")); ensure_space(spool)
    result=process_command(client.command(worker_id),ledger,client,cups,config,now)
    if result: return result
    for local in ledger.recoverable():
        job=json.loads(local["envelope_json"]); token=ensure_live_lease(local,job,client,ledger,worker_id,now)
        canonical=client.state(local["job_id"],token)
        if canonical.get("state") in TERMINAL: ledger.clear(local["job_id"]); return canonical["state"]
        if canonical.get("lease_token")!=token: raise Hold("restore_lease_conflict")
        if not local["cups_job_id"]:
            client.transition(job,token,"ambiguous",reason="submission_outcome_unknown"); ledger.update(local["job_id"],"ambiguous",now,error="submission_outcome_unknown"); return "ambiguous"
        observed=cups.observe(local["cups_job_id"])
        if observed in {"absent","unavailable"}: raise Hold("cups_observation_ambiguous")
        target="provider_completed" if observed=="completed" else "submitted"
        client.transition(job,token,target,cups_job_id=local["cups_job_id"],provider_id=cups.provider,observed_at=iso(now)); ledger.update(local["job_id"],target,now); return target
    claim=client.claim(worker_id)
    if not claim: return "event_waiting"
    job=claim["job"]; token=claim["lease_token"]; validate(job,config,now); ledger.put_claim(job,token,claim["lease_expires_at"],now)
    path=Path(spool)/(job["job_id"]+"."+uuid.uuid4().hex+".pdf")
    try:
        pdf=client.pdf(job["retrieval_url"])
        if len(pdf)>25*1024*1024 or sha256(pdf).hexdigest()!=job["pdf_sha256"]: raise Hold("pdf_digest_mismatch")
        path.write_bytes(pdf); attempt="ATTEMPT-"+uuid.uuid4().hex
        client.transition(job,token,"submitting",attempt_id=attempt,observed_at=iso(now)); ledger.update(job["job_id"],"submitting",now,attempt_id=attempt)
        cups_id=cups.submit(str(path)); client.transition(job,token,"submitted",attempt_id=attempt,cups_job_id=cups_id,provider_id=cups.provider,observed_at=iso(now)); ledger.update(job["job_id"],"submitted",now,cups_job_id=cups_id); return "submitted"
    except Exception:
        local=ledger.get(job["job_id"])
        if local and local.get("attempt_id"):
            client.transition(job,token,"ambiguous",attempt_id=local["attempt_id"],reason="cups_submission_exception"); ledger.update(job["job_id"],"ambiguous",now,error="cups_submission_exception")
        raise
    finally: path.unlink(missing_ok=True)

def load_config(path="/data/green-runtime/options.json"):
    value=json.loads(Path(path).read_text(encoding="utf-8")); required=("canonical_transport_profile","canonical_api_origin","canonical_bearer_token","farm_scope_id","green_id","printer_id","cups_queue_id","registry_version","printer_transport_profile","printer_uri","printer_endpoint_ip","poll_seconds")
    if any(value.get(k) in (None,"") for k in required): raise Hold("runtime_option_missing")
    origin,printer=urlparse(value["canonical_api_origin"]),urlparse(value["printer_uri"])
    if origin.scheme!="https" or origin.username or origin.password or origin.query or origin.fragment: raise Hold("canonical_origin_invalid")
    profile=value["canonical_transport_profile"]
    if profile==PRIVATE_PINNED:
        try: endpoint=ipaddress.ip_address(value.get("canonical_endpoint_ip",""))
        except ValueError as exc: raise Hold("commissioned_ip_literal_required") from exc
        if not endpoint.is_private or value["canonical_endpoint_ip"] not in private_addresses(origin.hostname): raise Hold("canonical_pin_not_in_resolution_set")
    elif profile==PUBLIC_PKI_EXACT_ORIGIN:
        if value["canonical_api_origin"]!=APPROVED_PUBLIC_CANONICAL_ORIGIN or value.get("canonical_endpoint_ip") not in (None,""): raise Hold("public_canonical_origin_not_approved")
        # Home Assistant renders a blank string for this profile. Normalize it
        # away so the runtime contract contains no endpoint pin at all.
        value["canonical_endpoint_ip"]=None
    else: raise Hold("canonical_transport_profile_invalid")
    if value["printer_transport_profile"]!="private_ipps" or printer.scheme!="ipps" or printer.username or printer.password or printer.query or printer.fragment: raise Hold("private_ipps_profile_required")
    try: printer_pin=ipaddress.ip_address(value["printer_endpoint_ip"])
    except ValueError as exc: raise Hold("printer_endpoint_pin_invalid") from exc
    if not printer_pin.is_private: raise Hold("private_printer_endpoint_required")
    try: printer_literal=ipaddress.ip_address(printer.hostname)
    except ValueError: printer_literal=None
    answers=(str(printer_literal),) if printer_literal else private_addresses(printer.hostname)
    if len(answers)!=1 or answers[0]!=str(printer_pin): raise Hold("printer_dns_binding_ambiguous_or_drifted")
    value["ca_certificate_path"]=CA_CERTIFICATE_PATH; value["canonical_intake_path"]=CLAIM_PATH
    if not Path(value["ca_certificate_path"]).is_file(): raise Hold("private_printer_ca_missing")
    if not all(ID.fullmatch(str(value[k])) for k in ("farm_scope_id","green_id","printer_id","cups_queue_id","registry_version")): raise Hold("invalid_registered_option")
    return value

def write_health(status,worker_id,result,next_poll):
    value={"contract_version":"green_print_health_v2","liveness":"alive","business_state":status,"worker_id":worker_id,"heartbeat_at":iso(utcnow()),"last_result":result,"next_poll_at":iso(next_poll),"authority_mode":"fixed_weekly_sheet_only","terminal_participated":False}
    target=Path("/data/green-runtime/health.json"); temporary=target.with_suffix(".tmp"); temporary.write_text(canonical_json(value),encoding="utf-8"); os.replace(temporary,target)
def main():
    os.umask(0o077); config=load_config(); worker_id="green-worker-"+uuid.uuid4().hex; ledger=Ledger("/data/green-runtime/green-print-ledger.sqlite3"); client=CanonicalClient(config); cups=Cups(config["cups_queue_id"],config["printer_uri"])
    while True:
        next_poll=utcnow()+timedelta(seconds=int(config["poll_seconds"]))
        try: result=cycle(ledger,client,cups,config,worker_id); write_health(result,worker_id,result,next_poll)
        except Exception as exc: write_health("held",worker_id,str(exc.args[0] if isinstance(exc,Hold) and exc.args else type(exc).__name__)[:120],next_poll)
        time.sleep(max(1,int(config["poll_seconds"])))
if __name__=="__main__": main()
