from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import importlib.util,json,sqlite3,sys
from pathlib import Path
import pytest,yaml

ROOT=Path(__file__).parents[1]; APP=ROOT/"green_print_bridge"
SPEC=importlib.util.spec_from_file_location("green_app",APP/"app"/"service.py"); S=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(S)
sys.modules["service"]=S
QUEUE_SPEC=importlib.util.spec_from_file_location("green_init_queue",APP/"app"/"init_queue.py"); Q=importlib.util.module_from_spec(QUEUE_SPEC); QUEUE_SPEC.loader.exec_module(Q)
NOW=datetime(2026,8,21,8,tzinfo=timezone.utc); PDF=b"%PDF-1.4\nsynthetic\n%%EOF"
def config(tmp_path):
    cert=tmp_path/"private-ca.crt"; cert.write_text("synthetic",encoding="utf-8")
    return {"canonical_transport_profile":"private_pinned","canonical_api_origin":"https://documents.invalid","canonical_endpoint_ip":"10.23.0.5","canonical_bearer_token":"synthetic-token","farm_scope_id":"farm-amadeus","green_id":"green-synthetic","printer_id":"printer-synthetic","cups_queue_id":"weekly-a4","registry_version":"registry-synthetic-v1","printer_transport_profile":"private_ipps","printer_uri":"ipps://10.23.0.9/ipp/print","printer_endpoint_ip":"10.23.0.9","ca_certificate_path":str(cert),"poll_seconds":30,"spool_path":str(tmp_path),"data_path":str(tmp_path)}
def envelope(**changes):
    value={"job_id":"JOB-SYNTHETIC-1","farm_scope_id":"farm-amadeus","document_id":"WWS-SYNTHETIC","document_version":"WWS-SYNTHETIC.r1.abcdef123456","document_revision":1,"document_type":S.PILOT_DOCUMENT,"generator_id":S.PILOT_GENERATOR,"pdf_sha256":sha256(PDF).hexdigest(),"retrieval_url":"https://documents.invalid/api/documents/WWS-SYNTHETIC/versions/WWS-SYNTHETIC.r1.abcdef123456/pdf","green_id":"green-synthetic","printer_id":"printer-synthetic","cups_queue_id":"weekly-a4","registry_version":"registry-synthetic-v1","authorization_receipt_id":"AUTH-SYNTHETIC-1","authorization_expires_at":(NOW+timedelta(hours=1)).isoformat(),"options":dict(S.FIXED_OPTIONS)}
    value.update(changes); return value

def test_package_is_bounded_and_privilege_split():
    cfg=yaml.safe_load((APP/"config.yaml").read_text(encoding="utf-8")); docker=(APP/"Dockerfile").read_text(encoding="utf-8"); init=(APP/"rootfs/init-green.sh").read_text(encoding="utf-8"); run=(APP/"rootfs/run.sh").read_text(encoding="utf-8")
    assert cfg["arch"]==["aarch64"] and cfg["privileged"]==[] and cfg["host_network"] is False
    assert "adduser -S -D -H" in docker and "/sbin/su-exec greenprint:greenprint" in init
    assert "/usr/sbin/cupsd -f -c /etc/cups/cupsd.conf -s /etc/cups/cups-files.conf 2>/dev/null &" in init and "/sbin/su-exec cupsd" not in init
    assert "lpadmin" not in init and "/sbin/su-exec greenprint:greenprint /usr/bin/python3 /opt/green/service.py 2>/dev/null || fail_startup service_exec service_process_failed" in init
    assert "PYTHONPATH=/opt/green /usr/bin/python3 /opt/green/init_queue.py" in init
    assert init.startswith("#!/bin/sh\nset -eu\numask 0077\n") and run.startswith("#!/bin/sh\nset -eu\numask 0077\n")
    assert "install -d -o greenprint -g greenprint -m 0700 /data/green-runtime" in init
    assert "install -d -o greenprint -g greenprint -m 0700 /data " not in init
    assert "install -o greenprint -g greenprint -m 0600 /data/options.json /data/green-runtime/options.json" in init
    assert 'green_startup_failed stage=$1 reason=$2' in init
    assert "green_startup_failed stage=bootstrap_exec reason=$1" in run and "fail_bootstrap init_script_unreadable" in run and "fail_bootstrap init_script_failed" in run
    assert "green_startup_failed stage=s6_exec reason=run_script_unreadable" in docker
    for stage in ("mount_validation","runtime_directory","options_population","cups_directories","ca_install","queue_initializer","queue_ownership","cups_start","cups_readiness","service_exec"):
        assert f"step {stage} " in init or f"fail_startup {stage} " in init
    assert b"\r" not in (APP/"rootfs/init-green.sh").read_bytes() and b"\r" not in (APP/"rootfs/run.sh").read_bytes()
    assert docker.startswith("FROM --platform=linux/arm64 ghcr.io/home-assistant/aarch64-base:3.22@sha256:0f19d1a4b031b3d141945a906e7c0d09fc98c796c18e2ea9072bce8e0b67578a")
    assert "chown root:cupsd /etc/cups/cups-files.conf && chmod 0640 /etc/cups/cups-files.conf" in docker
    for directive in ("User cupsd","Group cupsd","CreateSelfSignedCerts no","Printcap /run/cups/printcap","ErrorLog stderr","ServerRoot /run/cups"):
        assert directive in docker
    assert "sed -i -E '/^[[:space:]]*(User|Group|CreateSelfSignedCerts|Printcap|ErrorLog|ServerRoot)[[:space:]]+/d'" in docker
    assert docker.count("grep -Ec '^[[:space:]]*") == 6 and "/usr/sbin/cupsd -t -c /etc/cups/cupsd.conf -s /etc/cups/cups-files.conf" in docker
    assert "ln -s /run/cups/printers.conf /etc/cups/printers.conf" not in docker
    assert "/var/cache/cups" in docker
    assert "fail_startup cups_readiness cups_or_queue_not_ready" in init

def test_private_ipps_has_pinned_resolution_and_strict_certificate_policy():
    cfg=yaml.safe_load((APP/"config.yaml").read_text(encoding="utf-8")); queue=(APP/"app/init_queue.py").read_text(encoding="utf-8"); init=(APP/"rootfs/init-green.sh").read_text(encoding="utf-8"); docker=(APP/"Dockerfile").read_text(encoding="utf-8")
    policy=(APP/"rootfs/etc/cups/client.conf").read_text(encoding="utf-8"); cupsd=(APP/"rootfs/etc/cups/cupsd.conf").read_text(encoding="utf-8")
    assert 'path.open("a"' in queue and 'hosts.write(f"{pin} {hostname}\\n")' in queue
    assert "printer_tls_preflight(uri.hostname,str(pin)" in queue and 'uri.scheme=="ipps"' in queue
    assert "install_binding(Path(hosts_path),uri.hostname,pin)" in queue
    assert queue.index("printer_tls_preflight(uri.hostname,str(pin)") < queue.index("install_binding(Path(hosts_path),uri.hostname,pin)")
    assert "/homeassistant/private-ca.crt /etc/cups/ssl/site.crt" in init
    assert cfg["map"]==[{"type":"addon_config","read_only":True},{"type":"homeassistant_config","read_only":True}]
    apparmor=(APP/"apparmor.txt").read_text(encoding="utf-8")
    assert "/homeassistant/private-ca.crt r," in apparmor
    assert "/homeassistant/**" not in apparmor and "/homeassistant/ r" not in apparmor and "/config/private-ca.crt" not in apparmor
    assert "mkdir -p" in docker and "/etc/cups/ssl" in docker and "install -d -o root -g root -m 0755 /etc/cups/ssl" not in init
    for required in ("AllowAnyRoot No","AllowExpiredCerts No","Encryption IfRequested","TrustOnFirstUse No","ValidateCerts Yes"):
        assert required in policy
    assert "ServerName /run/cups/cups.sock" in policy
    assert "Listen /run/cups/cups.sock" in cupsd and "Listen localhost:631" not in cupsd
    assert "ServerRoot /run/cups" in cupsd and "ServerRoot /etc/cups" not in cupsd
    assert "DeviceURI {uri.geturl()}" in queue and "printer_transport_profile" in queue

def test_every_shell_bootstrap_failure_has_fixed_non_secret_stage_and_reason():
    init=(APP/"rootfs/init-green.sh").read_text(encoding="utf-8")
    run=(APP/"rootfs/run.sh").read_text(encoding="utf-8")
    docker=(APP/"Dockerfile").read_text(encoding="utf-8")
    probe=(ROOT/"scripts/green_print_startup_apparmor_probe.py").read_text(encoding="utf-8")
    expected=(
        ("mount_validation","data_mount_invalid"),("mount_validation","options_missing_or_empty"),
        ("mount_validation","options_unreadable"),("mount_validation","ca_missing_or_empty"),
        ("mount_validation","ca_unreadable"),
        ("runtime_directory","data_runtime_prepare_failed"),("runtime_directory","spool_prepare_failed"),
        ("options_population","runtime_options_install_failed"),("cups_directories","cups_runtime_prepare_failed"),
        ("cups_directories","cups_spool_prepare_failed"),("ca_install","ca_install_failed"),
        ("queue_initializer","initializer_interpreter_missing"),("queue_initializer","queue_initializer_failed"),
        ("queue_ownership","queue_owner_failed"),
        ("queue_ownership","queue_mode_failed"),("cups_start","cups_process_start_failed"),
        ("cups_readiness","cups_stopped_during_startup"),("cups_readiness","cups_or_queue_not_ready"),
        ("service_exec","service_launcher_missing"),("service_exec","service_interpreter_missing"),
        ("service_exec","service_script_unreadable"),("service_exec","service_process_failed"),
    )
    for stage,reason in expected:
        assert f"{stage} {reason}" in init
    diagnostic='marker="green_startup_failed stage=$1 reason=$2"'
    assert init.count(diagnostic)==1
    assert all(token not in diagnostic for token in ("options.json","private-ca.crt","canonical_bearer_token","printer_uri"))
    assert "green_startup_failed stage=bootstrap_exec reason=$1" in run
    assert "fail_bootstrap init_script_unreadable" in run and "fail_bootstrap init_script_failed" in run
    assert "green_startup_failed stage=s6_exec reason=run_script_unreadable" in docker
    for case in ("missing_options","empty_options","readonly_data","ownership_conflict","missing_cert","empty_cert","invalid_options","broken_interpreter","init_exec","run_exec","cups_start","service_exec"):
        assert f'negative_case("{case}"' in probe
    assert "if markers != [expected]" in probe
    for forbidden in ("synthetic-startup-probe-token",'options.get("printer_uri")',"BEGIN CERTIFICATE","/data/options.json","/homeassistant/private-ca.crt"):
        assert forbidden in probe
    assert 'any(addon_config_dir.iterdir())' in probe
    assert "test ! -e /config/private-ca.crt && test -s /homeassistant/private-ca.crt" in probe
    assert 'AppArmor exposed non-certificate Home Assistant configuration' in probe
    assert 'name="/homeassistant/secrets.yaml"' in probe

def test_printer_tls_preflight_requires_san_and_connects_only_to_pin(monkeypatch):
    calls=[]
    class Raw:
        def close(self): calls.append("raw_closed")
    class TLS:
        def close(self): calls.append("tls_closed")
    class Context:
        check_hostname=False; hostname_checks_common_name=True
        def wrap_socket(self,raw,server_hostname): calls.append((raw,server_hostname)); return TLS()
    context=Context()
    monkeypatch.setattr(S.ssl,"create_default_context",lambda cafile:(calls.append(("ca",cafile)) or context))
    monkeypatch.setattr(S.socket,"create_connection",lambda target,timeout:(calls.append((target,timeout)) or Raw()))
    S.printer_tls_preflight("printer.internal","10.23.0.9",631,"private-ca.crt")
    assert context.check_hostname is True and context.hostname_checks_common_name is False
    assert (("10.23.0.9",631),10) in calls and ("ca","private-ca.crt") in calls
    assert any(isinstance(x,tuple) and len(x)==2 and x[1]=="printer.internal" for x in calls) and "tls_closed" in calls

def test_printer_tls_preflight_fails_closed_on_untrusted_or_wrong_san(monkeypatch):
    class Raw:
        def __init__(self): self.closed=False
        def close(self): self.closed=True
    class Context:
        check_hostname=False; hostname_checks_common_name=True
        def wrap_socket(self,_raw,server_hostname): raise S.ssl.SSLCertVerificationError("SAN mismatch")
    raw=Raw(); monkeypatch.setattr(S.ssl,"create_default_context",lambda cafile:Context()); monkeypatch.setattr(S.socket,"create_connection",lambda *_a,**_k:raw)
    with pytest.raises(S.ssl.SSLCertVerificationError): S.printer_tls_preflight("printer.internal","10.23.0.9",631,"private-ca.crt")
    assert raw.closed

def queue_options():
    return {"cups_queue_id":"weekly-a4","printer_transport_profile":"private_ipps","printer_uri":"ipps://AmadeusKantoor:8631/ipp/print","printer_endpoint_ip":"10.23.0.9"}

def test_queue_startup_needs_no_ambient_printer_dns_and_verifies_fixed_binding(tmp_path,monkeypatch):
    options=tmp_path/"options.json"; queue=tmp_path/"printers.conf"; hosts=tmp_path/"hosts"
    options.write_text(json.dumps(queue_options()),encoding="utf-8"); hosts.write_text("127.0.0.1 localhost\n",encoding="ascii")
    calls=[]
    monkeypatch.setattr(Q,"printer_tls_preflight",lambda host,pin,port,ca:calls.append((host,pin,port,ca,hosts.read_text(encoding="ascii"))))
    def resolve(host,*_a,**_k):
        assert host=="amadeuskantoor" and "10.23.0.9 amadeuskantoor" in hosts.read_text(encoding="ascii")
        return [(None,None,None,None,("10.23.0.9",0))]
    monkeypatch.setattr(Q.socket,"getaddrinfo",resolve)
    Q.main(str(options),str(queue),str(hosts))
    assert calls==[("amadeuskantoor","10.23.0.9",8631,"/homeassistant/private-ca.crt","127.0.0.1 localhost\n")]
    assert hosts.read_text(encoding="ascii").count("10.23.0.9 amadeuskantoor")==1
    assert "DeviceURI ipps://AmadeusKantoor:8631/ipp/print" in queue.read_text(encoding="utf-8")

@pytest.mark.parametrize("failure",[S.ssl.SSLCertVerificationError("wrong SAN"),OSError("unreachable")])
def test_queue_tls_failures_are_sanitized_and_do_not_bind(tmp_path,monkeypatch,capsys,failure):
    options=tmp_path/"options.json"; queue=tmp_path/"printers.conf"; hosts=tmp_path/"hosts"
    options.write_text(json.dumps(queue_options()),encoding="utf-8"); hosts.write_text("127.0.0.1 localhost\n",encoding="ascii")
    def reject(*_a): raise failure
    monkeypatch.setattr(Q,"printer_tls_preflight",reject)
    with pytest.raises(SystemExit): Q.main(str(options),str(queue),str(hosts))
    assert capsys.readouterr().err=="green_startup_failed stage=printer_tls reason=identity_or_connection_failed\n"
    assert "AmadeusKantoor" not in hosts.read_text(encoding="ascii") and not queue.exists()

def test_queue_conflicting_binding_fails_before_queue_write(tmp_path,monkeypatch,capsys):
    options=tmp_path/"options.json"; queue=tmp_path/"printers.conf"; hosts=tmp_path/"hosts"
    options.write_text(json.dumps(queue_options()),encoding="utf-8"); hosts.write_text("10.23.0.10 AmadeusKantoor\n",encoding="ascii")
    monkeypatch.setattr(Q,"printer_tls_preflight",lambda *_a:None)
    with pytest.raises(SystemExit): Q.main(str(options),str(queue),str(hosts))
    assert capsys.readouterr().err=="green_startup_failed stage=printer_binding reason=hosts_binding_conflict\n"
    assert not queue.exists()

def test_queue_unwritable_binding_has_bounded_failure(tmp_path,monkeypatch,capsys):
    options=tmp_path/"options.json"; queue=tmp_path/"printers.conf"; hosts=tmp_path/"hosts"
    options.write_text(json.dumps(queue_options()),encoding="utf-8"); hosts.write_text("127.0.0.1 localhost\n",encoding="ascii")
    monkeypatch.setattr(Q,"printer_tls_preflight",lambda *_a:None); original=Q.Path.open
    def guarded(path,mode="r",*args,**kwargs):
        if path==hosts and "a" in mode: raise PermissionError("synthetic")
        return original(path,mode,*args,**kwargs)
    monkeypatch.setattr(Q.Path,"open",guarded)
    with pytest.raises(SystemExit): Q.main(str(options),str(queue),str(hosts))
    assert capsys.readouterr().err=="green_startup_failed stage=printer_binding reason=hosts_write_failed\n"
    assert not queue.exists()

def test_queue_wrong_literal_pin_fails_without_tls_or_queue(tmp_path,monkeypatch,capsys):
    value={**queue_options(),"printer_uri":"ipps://10.23.0.10/ipp/print"}
    options=tmp_path/"options.json"; queue=tmp_path/"printers.conf"
    options.write_text(json.dumps(value),encoding="utf-8")
    monkeypatch.setattr(Q,"printer_tls_preflight",lambda *_a:pytest.fail("TLS must not run"))
    with pytest.raises(SystemExit): Q.main(str(options),str(queue),str(tmp_path/"hosts"))
    assert capsys.readouterr().err=="green_startup_failed stage=configuration reason=private_ipps_endpoint_invalid\n"
    assert not queue.exists()

def test_package_uses_unique_prebuilt_image_and_requires_source_revision():
    cfg=yaml.safe_load((APP/"config.yaml").read_text(encoding="utf-8")); docker=(APP/"Dockerfile").read_text(encoding="utf-8")
    assert cfg["version"]=="0.3.6"
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
    assert "latest" not in workflow and "push: true" in workflow
    assert 'test "${GITHUB_REF}" = "refs/heads/main"' in workflow
    assert "platforms: linux/arm64" in workflow
    assert "pushed-index.json" in workflow and 'architecture == "arm64"' in workflow
    assert "--platform linux/arm64" in workflow
    assert 'cosign verify --certificate-identity "${identity}"' in workflow
    assert 'gh attestation verify "oci://${digest_ref}"' in workflow
    assert 'GH_TOKEN: ${{ github.token }}' in workflow
    assert 'tag_resolved_digest=${{ steps.pushed.outputs.resolved_digest }}' in workflow
    assert "green-print-0.3.6-verified-release-packet" in workflow
    assert "load: true" in workflow
    assert "Run real arm64 zero-job startup under package AppArmor" in workflow
    assert "green_print_startup_apparmor_probe.py" in workflow
    probe=(ROOT/"scripts/green_print_startup_apparmor_probe.py").read_text(encoding="utf-8")
    assert '"--add-host", f"printer.test:' not in probe
    assert 'DNS:AmadeusKantoor' in probe and 'ipps://AmadeusKantoor:' in probe
    assert '"printer_dns_preseeded": False' in probe and '"printer_fixed_binding_verified": True' in probe
    assert '"pid,uid,gid,comm,args"' in probe
    for proof in ("docker\", \"top","cups_scheduler_identity","cups_worker_identity","green_runtime_identity","tcp_631_listener","tls_key_files","test ! -e /etc/printcap","test ! -e /etc/cups/ssl/*.key","unexpected AppArmor denials"):
        assert proof in probe

def test_prebuilt_documentation_has_no_deleted_local_build_fallback():
    docs=(APP/"DOCS.md").read_text(encoding="utf-8")
    assert "build.yaml remains" not in docs
    assert "local Supervisor build" not in docs
    assert "There is no current local Supervisor-build fallback" in docs
    assert "GHCR does not provide a registry-level" in docs
    assert "0.3.0 publication is permanently quarantined" in docs
    assert "sha256:48d8d871740be4e315a1f108897da6617ce5c08cc5d20715398094140a8068f3" in docs
    assert "sha256:4b738c69245a6b4721a7f4b58135acf3d2308f355b7c8c4008c4149763e11b32" in docs

def test_036_publish_verifies_descriptor_and_config_before_signing_or_attesting():
    path=ROOT/".github/workflows/green-print-image.yml"
    workflow=path.read_text(encoding="utf-8")
    parsed=yaml.safe_load(workflow)
    assert parsed["env"]["VERSION"]=="0.3.6"
    steps=parsed["jobs"]["publish"]["steps"]
    names=[step.get("name") for step in steps]
    verify=names.index("Verify pushed index descriptor, config and OCI bindings")
    assert verify < names.index("Keylessly sign verified arm64 index")
    assert verify < names.index("Generate SPDX SBOM from exact linux arm64 digest")
    assert verify < names.index("Attest build provenance")
    raw=steps[verify]["run"]
    assert '.mediaType == "application/vnd.oci.image.index.v1+json"' in raw
    assert '(.manifests | length) == 1' in raw
    assert '.platform.os == "linux" and .platform.architecture == "arm64"' in raw
    assert '.architecture == "arm64" and .os == "linux"' in raw
    assert "push-by-digest=true" in workflow and "name-canonical=true" in workflow
    assert parsed["jobs"]["publish"]["outputs"]["digest"] == "${{ steps.pushed.outputs.resolved_digest }}"
    assert "home-assistant/builder/actions/build-image" not in workflow

def test_private_attestation_token_is_step_scoped_and_failure_blocks_packet():
    path=ROOT/".github/workflows/green-print-image.yml"
    workflow=path.read_text(encoding="utf-8")
    parsed=yaml.safe_load(workflow)
    steps=parsed["jobs"]["publish"]["steps"]
    names=[step.get("name") for step in steps]
    verify=steps[names.index("Verify signature and digest-bound attestations")]
    assert verify["env"]["GH_TOKEN"]=="${{ github.token }}"
    assert workflow.count("GH_TOKEN: ${{ github.token }}")==2
    assert "gh attestation verify" in verify["run"] and "|| true" not in verify["run"]
    assert names.index("Verify signature and digest-bound attestations") < names.index("Emit digest-bound non-secret release receipt") < names.index("Preserve non-secret verified release packet")

def test_035_recovery_is_verification_only_exact_bound_and_replay_safe():
    workflow=(ROOT/".github/workflows/green-print-image.yml").read_text(encoding="utf-8")
    parsed=yaml.safe_load(workflow)
    inputs=parsed.get("on",parsed[True])["workflow_dispatch"]["inputs"]
    assert inputs["recover_existing"]["type"]=="boolean" and inputs["recover_existing"]["default"] is False
    assert inputs["expected_digest"]["required"] is False
    recovery=parsed["jobs"]["recover"]
    assert recovery["if"]=="github.event_name == 'workflow_dispatch' && inputs.recover_existing"
    assert recovery["permissions"]=={"contents":"read","packages":"read","attestations":"read"}
    steps=recovery["steps"]; names=[step.get("name") for step in steps]
    binding=steps[names.index("Bind recovery to exact source, digest, main and package version")]["run"]
    assert '^sha256:[0-9a-f]{64}$' in binding and '^[0-9a-f]{40}$' in binding
    assert 'test "${PUBLISH_REQUESTED}" = "false"' in binding
    assert 'git merge-base --is-ancestor "${EXPECTED_SOURCE_COMMIT}" "${GITHUB_SHA}"' in binding
    existing=steps[names.index("Verify existing tag, index, arm64 config and immutable bindings")]["run"]
    assert 'test "${tag_digest}" = "${EXPECTED_DIGEST}"' in existing
    assert '(.manifests | length) == 1' in existing and '.platform.architecture == "arm64"' in existing
    assert 'org.opencontainers.image.revision' in existing and 'org.opencontainers.image.version' in existing
    verifier=steps[names.index("Verify existing signature and digest-bound attestations")]
    assert verifier["env"]["GH_TOKEN"]=="${{ github.token }}"
    assert "cosign verify" in verifier["run"] and verifier["run"].count("gh attestation verify")==2
    assert "--source-digest \"${EXPECTED_SOURCE_COMMIT}\"" in verifier["run"]
    assert "|| true" not in verifier["run"]
    assert names.index("Verify existing signature and digest-bound attestations") < names.index("Emit recovered digest-bound non-secret release receipt") < names.index("Preserve recovered non-secret verified release packet")
    forbidden=("docker/build-push-action","cosign sign","actions/attest-build-provenance","actions/attest-sbom","imagetools create","push: true")
    recovery_text=json.dumps(recovery)
    assert not any(token in recovery_text for token in forbidden)

def test_apparmor_denies_admin_and_broad_writes():
    policy=(APP/"apparmor.txt").read_text(encoding="utf-8")
    assert "deny /usr/sbin/lpadmin x" in policy and "/etc/cups/** rwk" not in policy and "/tmp/** rwk" not in policy
    assert "/tmp/green-spool/** rwk" in policy and "/data/** rwk" in policy
    assert "/etc/cups/ssl/site.crt rw," in policy and "/etc/hosts rw," in policy
    assert "/etc/cups/** w" not in policy
    assert "deny /etc/printcap rwklx," in policy and "deny /etc/cups/ssl/*.key rwklx," in policy

def test_apparmor_covers_inherited_s6_entrypoint_without_broad_shell_exec():
    policy=(APP/"apparmor.txt").read_text(encoding="utf-8")
    for required in ("capability fowner,","capability fsetid,","/ r,","/init rix,","/command/** ix,","/package/admin/execline*/** rix,","/package/admin/s6*/** rix,","/package/prog/skalibs*/** rix,","/etc/fix-attrs.d/ r,","/etc/services.d/ r,","/run/ rw,","/run/s6/ rwk,","/run/s6/** rwkix,","/run/service/ rwk,","/run/service/** rwkix,","/run/s6-rc* rwkl,","/run/s6-rc*/** rwkix,","/run/s6-linux-init-container-results/** rwkix,","/run/uncaught-logs/** rwkix,","/healthcheck.py rix,","/opt/green/ r,","/usr/bin/python3.12 ix,","/sbin/su-exec ix,","/data/ rwk,","/run/cups/ rwk,","/tmp/green-spool/ rwk,","/var/spool/cups/ rwk,","/var/log/cups/ rwk,","/var/cache/cups/ rwk,","/usr/share/cups/ r,","/etc/cups/ rw,","/etc/cups/ppd/ rw,","/etc/cups/ssl/ rw,","/etc/cups/cupsd.conf rw,","/etc/cups/cups-files.conf rw,","deny /etc/printcap rwklx,","deny /etc/cups/ssl/*.key rwklx,"):
        assert required in policy
    assert "/usr/bin/su-exec" not in policy
    assert "/bin/** ix" not in policy and "/usr/bin/** ix" not in policy
    assert "update-ca-certificates" not in policy
    assert "/usr/local/share/ca-certificates" not in policy
    assert "/etc/ssl/certs/** rw" not in policy

def test_home_assistant_public_profile_default_is_explicit_blank():
    cfg=yaml.safe_load((APP/"config.yaml").read_text(encoding="utf-8"))
    assert cfg["options"]["canonical_endpoint_ip"]==""
    assert cfg["schema"]["canonical_endpoint_ip"]=="str"

def test_contract_and_authorization_fail_closed(tmp_path):
    cfg=config(tmp_path); S.validate(envelope(),cfg,NOW)
    for change in ({"cups_queue_id":"other"},{"options":{**S.FIXED_OPTIONS,"copies":2}},{"authorization_expires_at":NOW.isoformat()},{"retrieval_url":envelope()["retrieval_url"]+"?x=1"}):
        with pytest.raises(S.Hold): S.validate(envelope(**change),cfg,NOW)

def test_config_preserves_private_canonical_pin_and_ip_san_printer(tmp_path,monkeypatch):
    cfg=config(tmp_path); monkeypatch.setattr(S,"CA_CERTIFICATE_PATH",cfg["ca_certificate_path"]); path=tmp_path/"options.json"
    monkeypatch.setattr(S.socket,"getaddrinfo",lambda *_a,**_k:[(None,None,None,None,("10.23.0.5",0))]); path.write_text(json.dumps(cfg),encoding="utf-8")
    assert S.load_config(str(path))["canonical_endpoint_ip"]=="10.23.0.5"
    path.write_text(json.dumps({**cfg,"printer_uri":"ipps://printer.invalid/ipp/print"}),encoding="utf-8")
    monkeypatch.setattr(S.socket,"getaddrinfo",lambda host,*_a,**_k:[(None,None,None,None,(("10.23.0.5" if host=="documents.invalid" else "10.23.0.9"),0))])
    assert S.load_config(str(path))["printer_endpoint_ip"]=="10.23.0.9"

def test_public_pki_profile_allows_only_exact_render_origin_without_pin(tmp_path,monkeypatch):
    cfg={**config(tmp_path),"canonical_transport_profile":"public_pki_exact_origin","canonical_api_origin":S.APPROVED_PUBLIC_CANONICAL_ORIGIN,"canonical_endpoint_ip":""}
    monkeypatch.setattr(S,"CA_CERTIFICATE_PATH",cfg["ca_certificate_path"])
    path=tmp_path/"options.json"; path.write_text(json.dumps(cfg),encoding="utf-8")
    loaded=S.load_config(str(path))
    assert loaded["canonical_transport_profile"]=="public_pki_exact_origin" and loaded["canonical_endpoint_ip"] is None
    without_pin={key:value for key,value in cfg.items() if key!="canonical_endpoint_ip"}
    path.write_text(json.dumps(without_pin),encoding="utf-8")
    assert S.load_config(str(path))["canonical_endpoint_ip"] is None
    for origin in ("https://example.com","https://amadeus-pig-tracking-system.onrender.com/extra","http://amadeus-pig-tracking-system.onrender.com"):
        path.write_text(json.dumps({**cfg,"canonical_api_origin":origin}),encoding="utf-8")
        with pytest.raises(S.Hold): S.load_config(str(path))
    path.write_text(json.dumps({**cfg,"canonical_endpoint_ip":"10.23.0.5"}),encoding="utf-8")
    with pytest.raises(S.Hold,match="public_canonical_origin_not_approved"): S.load_config(str(path))

def test_private_profile_still_requires_nonempty_exact_pin(tmp_path,monkeypatch):
    cfg=config(tmp_path); monkeypatch.setattr(S,"CA_CERTIFICATE_PATH",cfg["ca_certificate_path"]); path=tmp_path/"options.json"
    for value in ("",None):
        candidate={**cfg,"canonical_endpoint_ip":value}
        if value is None: candidate.pop("canonical_endpoint_ip")
        path.write_text(json.dumps(candidate),encoding="utf-8")
        with pytest.raises(S.Hold,match="commissioned_ip_literal_required"): S.load_config(str(path))

def test_printer_hostname_dns_is_single_private_bound_address(tmp_path,monkeypatch):
    cfg={**config(tmp_path),"printer_uri":"ipps://printer.internal/ipp/print"}; path=tmp_path/"options.json"; path.write_text(json.dumps(cfg),encoding="utf-8")
    monkeypatch.setattr(S,"CA_CERTIFICATE_PATH",cfg["ca_certificate_path"])
    for answers in (["10.23.0.9"],["10.23.0.9","10.23.0.10"],["8.8.8.8"]):
        monkeypatch.setattr(S.socket,"getaddrinfo",lambda host,*_a,_answers=answers,**_k:[(None,None,None,None,(x,0)) for x in (["10.23.0.5"] if host=="documents.invalid" else _answers)])
        if answers==["10.23.0.9"]: assert S.load_config(str(path))["printer_endpoint_ip"]=="10.23.0.9"
        else:
            with pytest.raises(S.Hold): S.load_config(str(path))

def test_printer_dns_drift_holds_before_any_canonical_or_cups_effect(tmp_path,monkeypatch):
    cfg={**config(tmp_path),"printer_uri":"ipps://printer.internal/ipp/print"}
    monkeypatch.setattr(S.socket,"getaddrinfo",lambda *_a,**_k:[(None,None,None,None,("10.23.0.10",0))])
    canonical=Canonical(); cups=Cups()
    with pytest.raises(S.Hold,match="printer_dns_binding_ambiguous_or_drifted"): S.cycle(S.Ledger(str(tmp_path/"drift.db")),canonical,cups,cfg,"worker")
    assert canonical.claimed is None and cups.submissions==0

def test_public_client_uses_system_pki_and_never_pinned_connection(tmp_path,monkeypatch):
    cfg={**config(tmp_path),"canonical_transport_profile":"public_pki_exact_origin","canonical_api_origin":S.APPROVED_PUBLIC_CANONICAL_ORIGIN,"canonical_endpoint_ip":""}
    monkeypatch.setattr(S.ssl,"create_default_context",lambda **kwargs:("context",kwargs)); client=S.CanonicalClient(cfg)
    assert client.context==("context",{})
    conn=client.connection(20); assert type(conn) is S.http.client.HTTPSConnection and conn.host=="amadeus-pig-tracking-system.onrender.com"

def test_public_client_rejects_redirect_and_binds_auth_farm_green_and_host(tmp_path):
    cfg={**config(tmp_path),"canonical_transport_profile":"public_pki_exact_origin","canonical_api_origin":S.APPROVED_PUBLIC_CANONICAL_ORIGIN,"canonical_endpoint_ip":""}
    class Response:
        status=302
        def read(self,_limit): return b""
    class Connection:
        def __init__(self): self.sent=None; self.closed=False
        def request(self,*args,**kwargs): self.sent=(args,kwargs)
        def getresponse(self): return Response()
        def close(self): self.closed=True
    client=object.__new__(S.CanonicalClient); client.config=cfg; client.worker_id="green-worker-bound"; connection=Connection(); client.connection=lambda _timeout:connection
    with pytest.raises(S.Hold,match="canonical_redirect_forbidden"): client.request("POST",S.CLAIM_PATH,{"worker_id":"green-worker-bound"})
    headers=connection.sent[1]["headers"]
    assert headers["Authorization"]=="Bearer synthetic-token" and headers["X-Amadeus-Farm-Scope-Id"]=="farm-amadeus"
    assert headers["X-Amadeus-Green-Id"]=="green-synthetic" and headers["Host"]=="amadeus-pig-tracking-system.onrender.com" and connection.closed

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
    assert '["/usr/bin/lpstat", "-r"]' in text and 'scheduler.stdout.strip() == "scheduler is running"' in text

def test_no_plain_claimable_get_or_runtime_lpadmin():
    source=(APP/"app/service.py").read_text(encoding="utf-8"); init=(APP/"rootfs/init-green.sh").read_text(encoding="utf-8")
    assert "/claimable" not in source and 'request("GET",CLAIM_PATH' not in source and "lpadmin" not in source+init

def test_no_sensitive_values_committed():
    material="\n".join(p.read_text(encoding="utf-8",errors="ignore") for p in APP.rglob("*") if p.is_file())
    assert not any(x in material for x in ("service_role","SUPABASE_SERVICE_ROLE_KEY=","BEGIN CERTIFICATE","192.168."))
