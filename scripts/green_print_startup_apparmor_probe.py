#!/usr/bin/env python3
"""Run the built arm64 app through its real OCI entrypoint and AppArmor profile."""

from __future__ import annotations

import argparse
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
from threading import Thread
import time
import uuid


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=True, text=True)


def failure_diagnostics(container: str) -> str:
    logs = run("docker", "logs", container, check=False)
    state = run(
        "docker", "inspect", "-f", "{{json .State}}", container, check=False,
    )
    denied = apparmor_denials()[-80:]
    return "\n".join(
        (
            "docker-state: " + state.stdout.strip(),
            "container-stdout: " + logs.stdout.strip(),
            "container-stderr: " + logs.stderr.strip(),
            "apparmor-denials:\n" + "\n".join(denied),
        )
    )


def apparmor_denials() -> list[str]:
    kernel = run("sudo", "dmesg", "--ctime", check=False)
    return [
        line for line in kernel.stdout.splitlines()
        if "apparmor=\"DENIED\"" in line
        and "amadeus-green-print-bridge" in line
    ]


class EmptyCanonicalHandler(BaseHTTPRequestHandler):
    seen: list[str] = []

    def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        type(self).seen.append(self.path)
        body = b"{}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def tls_server(cert: Path, key: Path) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", 0), EmptyCanonicalHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument(
        "--work-root",
        type=Path,
        default=Path(".codex-runtime/missions/GREEN-0.3.8"),
    )
    args = parser.parse_args()
    suffix = uuid.uuid4().hex[:10]
    network = f"green-startup-probe-{suffix}"
    container = f"green-startup-probe-{suffix}"
    servers: list[ThreadingHTTPServer] = []

    args.work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="green-startup-probe-", dir=args.work_root.resolve(),
    ) as raw:
        root = Path(raw)
        addon_config_dir = root / "addon-config"
        ha_config_dir = root / "homeassistant-config"
        data_dir = root / "data"
        addon_config_dir.mkdir()
        ha_config_dir.mkdir()
        data_dir.mkdir()
        cert = ha_config_dir / "private-ca.crt"
        forbidden_ha_file = ha_config_dir / "secrets.yaml"
        forbidden_ha_file.write_text("must-not-be-readable\n", encoding="ascii")
        key = root / "private-ca.key"
        run(
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-days", "1", "-subj", "/CN=green-startup-probe",
            "-addext", "subjectAltName=DNS:canonical.test,DNS:AmadeusKantoor",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-keyout", str(key), "-out", str(cert),
        )
        wrong_root_cert = root / "wrong-root.crt"
        wrong_root_key = root / "wrong-root.key"
        run(
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-days", "1", "-subj", "/CN=green-wrong-root",
            "-addext", "subjectAltName=DNS:AmadeusKantoor",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-keyout", str(wrong_root_key), "-out", str(wrong_root_cert),
        )
        wrong_san_cert = root / "wrong-san.crt"
        wrong_san_key = root / "wrong-san.key"
        run(
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-days", "1", "-subj", "/CN=green-wrong-san",
            "-addext", "subjectAltName=DNS:not-the-printer.test",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-keyout", str(wrong_san_key), "-out", str(wrong_san_cert),
        )
        run("docker", "network", "create", "--internal", network)
        gateway = run(
            "docker", "network", "inspect", "-f",
            "{{(index .IPAM.Config 0).Gateway}}", network,
        ).stdout.strip()
        canonical = tls_server(cert, key)
        servers.append(canonical)
        options = {
            "canonical_transport_profile": "private_pinned",
            "canonical_api_origin": f"https://canonical.test:{canonical.server_port}",
            "canonical_endpoint_ip": gateway,
            "canonical_bearer_token": "synthetic-startup-probe-token",
            "farm_scope_id": "farm-startup-probe",
            "green_id": "green-startup-probe",
            "printer_id": "printer-startup-probe",
            "cups_queue_id": "weekly-a4",
            "registry_version": "registry-startup-probe-v1",
            "printer_transport_profile": "local_ipp_fixed",
            "printer_uri": f"ipp://{gateway}/printers/weekly-a4",
            "printer_endpoint_ip": gateway,
            "poll_seconds": 5,
        }
        options_path = data_dir / "options.json"
        options_path.write_text(json.dumps(options), encoding="utf-8")
        green_uid = run(
            "docker", "run", "--rm", "--platform", "linux/arm64",
            "--entrypoint", "/usr/bin/id", args.image, "-u", "greenprint",
        ).stdout.strip()
        green_gid = run(
            "docker", "run", "--rm", "--platform", "linux/arm64",
            "--entrypoint", "/usr/bin/id", args.image, "-g", "greenprint",
        ).stdout.strip()
        if not green_uid.isdigit() or not green_gid.isdigit():
            raise RuntimeError("image runtime identity invalid")
        # Reproduce the Supervisor boundary: Supervisor populates root-owned
        # options on a writable /data mount. Never pre-own the mount or its
        # contents for the image's runtime user.
        run("sudo", "chown", "root:root", str(data_dir), str(options_path), str(addon_config_dir), str(ha_config_dir), str(cert), str(forbidden_ha_file))
        run("sudo", "chmod", "0755", str(data_dir), str(addon_config_dir), str(ha_config_dir))
        run("sudo", "chmod", "0600", str(options_path))
        run("sudo", "chmod", "0644", str(cert))

        try:
            run("sudo", "apparmor_parser", "-r", str(args.profile.resolve()))

            if any(addon_config_dir.iterdir()):
                raise RuntimeError("Supervisor-shaped addon_config must remain empty")
            scope_denial_baseline = len(apparmor_denials())
            denied_ha_read = run(
                "docker", "run", "--rm", "--platform", "linux/arm64",
                "--security-opt", "apparmor=amadeus-green-print-bridge",
                "--entrypoint", "/bin/busybox",
                "--mount", f"type=bind,src={addon_config_dir},dst=/config,readonly",
                "--mount", f"type=bind,src={ha_config_dir},dst=/homeassistant,readonly",
                args.image, "cat", "/homeassistant/secrets.yaml", check=False,
            )
            if denied_ha_read.returncode == 0 or "must-not-be-readable" in (denied_ha_read.stdout + denied_ha_read.stderr):
                raise RuntimeError("AppArmor exposed non-certificate Home Assistant configuration")
            scope_denials = apparmor_denials()[scope_denial_baseline:]
            if not any('name="/homeassistant/secrets.yaml"' in line for line in scope_denials):
                raise RuntimeError("AppArmor did not prove denial of non-certificate Home Assistant configuration")

            def negative_case(name: str, expected: str, *, options_mode: str = "valid", cert_mode: str = "valid", data_readonly: bool = False, shadow: tuple[str, str] | None = None) -> None:
                case_root=root/f"negative-{name}"; case_addon_config=case_root/"addon-config"; case_ha_config=case_root/"homeassistant-config"; case_data=case_root/"data"
                case_addon_config.mkdir(parents=True); case_ha_config.mkdir(); case_data.mkdir()
                if options_mode != "missing":
                    case_options={**options}
                    material=json.dumps(case_options) if options_mode == "valid" else ("" if options_mode == "empty" else "{}")
                    (case_data/"options.json").write_text(material,encoding="utf-8")
                if cert_mode != "missing":
                    cert_source={"valid":cert,"wrong_root":wrong_root_cert,
                        "wrong_san":wrong_san_cert}.get(cert_mode)
                    (case_ha_config/"private-ca.crt").write_bytes(
                        cert_source.read_bytes() if cert_source else b"")
                if name == "ownership_conflict": (case_data/"green-runtime").write_text("not-a-directory",encoding="ascii")
                source=None
                if shadow:
                    source=case_root/shadow[0]
                    if shadow[0].endswith("-empty"):
                        source.write_bytes(b""); source.chmod(0o644)
                    elif shadow[0].endswith("-silent-python"):
                        source.write_text("raise SystemExit(1)\n",encoding="ascii"); source.chmod(0o644)
                    elif shadow[0].endswith("-unrecognized-python"):
                        source.write_text("import sys\nprint('not-an-allowed-marker',file=sys.stderr)\nraise SystemExit(1)\n",encoding="ascii"); source.chmod(0o644)
                    elif shadow[0].endswith("-multiline-unterminated-python"):
                        source.write_text("import sys\nsys.stderr.write('green_startup_failed stage=printer_tls reason=identity_or_connection_failed\\nuntrusted-arbitrary-output')\nraise SystemExit(1)\n",encoding="ascii"); source.chmod(0o644)
                    elif shadow[0].endswith("-multiline-terminated-python"):
                        source.write_text("import sys\nsys.stderr.write('green_startup_failed stage=printer_tls reason=identity_or_connection_failed\\nuntrusted-arbitrary-output\\n')\nraise SystemExit(1)\n",encoding="ascii"); source.chmod(0o644)
                    elif shadow[0].endswith("-python"):
                        source.write_text("this is not valid python\n",encoding="ascii"); source.chmod(0o644)
                    elif shadow[0].endswith("-exit"):
                        source.write_text("#!/bin/sh\nexit 1\n",encoding="ascii"); source.chmod(0o755)
                    else:
                        source.write_text("this is not valid shell syntax (\n",encoding="ascii"); source.chmod(0o644)
                run("sudo","chown","-R","root:root",str(case_root)); run("sudo","chmod","0755",str(case_root),str(case_addon_config),str(case_ha_config),str(case_data))
                if (case_data/"options.json").exists(): run("sudo","chmod","0600",str(case_data/"options.json"))
                if (case_ha_config/"private-ca.crt").exists(): run("sudo","chmod","0644",str(case_ha_config/"private-ca.crt"))
                case_container=f"{container}-{name}"
                command=["docker","run","-d","--name",case_container,"--platform","linux/arm64","--network",network,"--add-host",f"canonical.test:{gateway}","--security-opt","apparmor=amadeus-green-print-bridge","--mount",f"type=bind,src={case_addon_config},dst=/config,readonly","--mount",f"type=bind,src={case_ha_config},dst=/homeassistant,readonly","--mount",f"type=bind,src={case_data},dst=/data" + (",readonly" if data_readonly else "")]
                if shadow:
                    command.extend(["--mount",f"type=bind,src={source},dst={shadow[1]},readonly"])
                seen_before=list(EmptyCanonicalHandler.seen)
                command.append(args.image); run(*command)
                try:
                    deadline=time.monotonic()+20
                    while time.monotonic()<deadline:
                        state=run("docker","inspect","-f","{{.State.Running}}",case_container).stdout.strip()
                        if state!="true": break
                        time.sleep(.5)
                    if state=="true": raise RuntimeError(f"negative case remained running: {name}")
                    logs=run("docker","logs",case_container,check=False); combined=logs.stdout+logs.stderr
                    markers=[line for line in combined.splitlines() if "green_startup_failed" in line]
                    if markers != [expected]: raise RuntimeError(f"negative diagnostic mismatch {name}: {markers}")
                    forbidden=("synthetic-startup-probe-token",options.get("printer_uri"),"BEGIN CERTIFICATE","/data/options.json","/homeassistant/private-ca.crt")
                    if any(value and value in combined for value in forbidden): raise RuntimeError(f"negative diagnostic leaked bounded material: {name}")
                    if "untrusted-arbitrary-output" in combined:
                        raise RuntimeError(f"negative diagnostic leaked untrusted child output: {name}")
                    if run("docker","inspect","-f","{{.State.ExitCode}}",case_container).stdout.strip()=="0": raise RuntimeError(f"negative case exited zero: {name}")
                    if EmptyCanonicalHandler.seen != seen_before:
                        raise RuntimeError(f"negative case reached canonical provider: {name}")
                    capture_copy=case_root/"captured-child-output"
                    if (run("docker","cp",f"{case_container}:/run/cups/queue-initializer-error",str(capture_copy),check=False).returncode==0
                            or capture_copy.exists()):
                        raise RuntimeError(f"negative case retained private child output: {name}")
                finally: run("docker","rm","-f",case_container,check=False)

            negative_case("missing_options","green_startup_failed stage=mount_validation reason=options_missing_or_empty",options_mode="missing")
            negative_case("empty_options","green_startup_failed stage=mount_validation reason=options_missing_or_empty",options_mode="empty")
            negative_case("readonly_data","green_startup_failed stage=runtime_directory reason=data_runtime_prepare_failed",data_readonly=True)
            negative_case("ownership_conflict","green_startup_failed stage=runtime_directory reason=data_runtime_prepare_failed")
            negative_case("missing_cert","green_startup_failed stage=mount_validation reason=ca_missing_or_empty",cert_mode="missing")
            negative_case("empty_cert","green_startup_failed stage=mount_validation reason=ca_missing_or_empty",cert_mode="empty")
            negative_case("invalid_options","green_startup_failed stage=configuration reason=queue_invalid",options_mode="invalid")
            negative_case("silent_initializer","green_startup_failed stage=queue_initializer reason=queue_initializer_failed",shadow=("initializer-silent-python","/opt/green/init_queue.py"))
            negative_case("unrecognized_initializer","green_startup_failed stage=queue_initializer reason=queue_initializer_failed",shadow=("initializer-unrecognized-python","/opt/green/init_queue.py"))
            negative_case("multiline_unterminated_initializer","green_startup_failed stage=queue_initializer reason=queue_initializer_failed",shadow=("initializer-multiline-unterminated-python","/opt/green/init_queue.py"))
            negative_case("multiline_terminated_initializer","green_startup_failed stage=queue_initializer reason=queue_initializer_failed",shadow=("initializer-multiline-terminated-python","/opt/green/init_queue.py"))
            negative_case("broken_interpreter","green_startup_failed stage=queue_initializer reason=initializer_interpreter_missing",shadow=("python-empty","/usr/bin/python3.12"))
            negative_case("init_exec","green_startup_failed stage=bootstrap_exec reason=init_script_failed",shadow=("init-shell","/init-green.sh"))
            negative_case("run_exec","green_startup_failed stage=s6_exec reason=run_script_failed",shadow=("run-shell","/run.sh"))
            negative_case("cups_start","green_startup_failed stage=cups_readiness reason=cups_stopped_during_startup",shadow=("cups-fail","/usr/sbin/cupsd"))
            negative_case("service_exec","green_startup_failed stage=service_exec reason=service_process_failed",shadow=("service-exit","/sbin/su-exec"))
            # A deliberately shadowed executable can itself produce an expected
            # denial. Only denials created by the following healthy journey are
            # evidence against the production profile.
            positive_denial_baseline = len(apparmor_denials())
            run(
                "docker", "run", "-d", "--name", container,
                "--platform", "linux/arm64", "--network", network,
                "--add-host", f"canonical.test:{gateway}",
                "--security-opt", "apparmor=amadeus-green-print-bridge",
                "--mount", f"type=bind,src={addon_config_dir},dst=/config,readonly",
                "--mount", f"type=bind,src={ha_config_dir},dst=/homeassistant,readonly",
                "--mount", f"type=bind,src={data_dir},dst=/data",
                args.image,
            )
            mount_contract = run(
                "docker", "exec", container, "/bin/sh", "-c",
                "test ! -e /config/private-ca.crt && test -s /homeassistant/private-ca.crt",
                check=False,
            )
            if mount_contract.returncode != 0:
                raise RuntimeError("Supervisor add-on/Home Assistant config mount separation failed\n" + failure_diagnostics(container))
            deadline = time.monotonic() + 45
            health: dict[str, object] | None = None
            while time.monotonic() < deadline:
                health_readback = run(
                    "docker", "exec", container, "/bin/sh", "-c", "cat /data/green-runtime/health.json",
                    check=False,
                )
                if health_readback.returncode == 0:
                    health = json.loads(health_readback.stdout)
                    if health.get("business_state") == "event_waiting":
                        break
                state = run("docker", "inspect", "-f", "{{.State.Running}}", container).stdout.strip()
                if state != "true":
                    raise RuntimeError("container stopped before event_waiting\n" + failure_diagnostics(container))
                time.sleep(1)
            if not health or health.get("business_state") != "event_waiting":
                raise RuntimeError("event_waiting health not reached\n" + failure_diagnostics(container))
            if health.get("terminal_participated") is not False or health.get("authority_mode") != "fixed_weekly_sheet_only":
                raise RuntimeError(f"unexpected health contract: {health}")
            data_contract = run(
                "docker", "exec", container, "/bin/sh", "-c",
                "test \"$(/bin/busybox stat -c %u:%g /data)\" = '0:0'"
                f" && test \"$(/bin/busybox stat -c %u:%g /data/options.json)\" = '0:0'"
                f" && test \"$(/bin/busybox stat -c %u:%g /data/green-runtime)\" = '{green_uid}:{green_gid}'"
                f" && test \"$(/bin/busybox stat -c %a /data/green-runtime/options.json)\" = '600'",
                check=False,
            )
            if data_contract.returncode != 0:
                raise RuntimeError("Supervisor-shaped data ownership contract mismatch\n" + failure_diagnostics(container))
            scheduler = run("docker", "exec", container, "/usr/bin/lpstat", "-r", check=False)
            destination = run(
                "docker", "exec", container, "/usr/bin/lpstat", "-v", "weekly-a4",
                check=False,
            )
            if (
                scheduler.returncode != 0
                or scheduler.stdout.strip() != "scheduler is running"
                or destination.returncode != 0
            ):
                raise RuntimeError(
                    "CUPS scheduler or destination unavailable\n"
                    f"scheduler: rc={scheduler.returncode} stdout={scheduler.stdout!r} stderr={scheduler.stderr!r}\n"
                    f"destination: rc={destination.returncode} stdout={destination.stdout!r} stderr={destination.stderr!r}\n"
                    + failure_diagnostics(container)
                )
            queue = run("docker", "exec", container, "/usr/bin/lpstat", "-W", "all", "-o", "weekly-a4", check=False)
            if queue.returncode != 0 or queue.stdout.strip():
                raise RuntimeError(
                    f"queue was not empty: rc={queue.returncode} stdout={queue.stdout!r} stderr={queue.stderr!r}\n"
                    + failure_diagnostics(container)
                )
            binding = run("docker", "exec", container, "/bin/cat", "/etc/hosts", check=False)
            bound_rows = [line.split() for line in binding.stdout.splitlines()]
            matching = [row for row in bound_rows if len(row) >= 2 and "amadeuskantoor" in {value.casefold() for value in row[1:]}]
            if binding.returncode != 0 or matching != [[gateway, "amadeuskantoor"]]:
                raise RuntimeError("fixed printer binding missing or mismatched\n" + failure_diagnostics(container))
            cups_contract = run(
                "docker", "exec", container, "/bin/sh", "-c",
                "grep -Fx 'User cupsd' /etc/cups/cups-files.conf"
                " && grep -Fx 'Group cupsd' /etc/cups/cups-files.conf"
                " && grep -Fx 'CreateSelfSignedCerts no' /etc/cups/cups-files.conf"
                " && grep -Fx 'Printcap /run/cups/printcap' /etc/cups/cups-files.conf"
                " && grep -Fx 'ErrorLog stderr' /etc/cups/cups-files.conf"
                " && grep -Fx 'ServerRoot /run/cups' /etc/cups/cups-files.conf"
                " && test \"$(grep -Ec '^[[:space:]]*User[[:space:]]+' /etc/cups/cups-files.conf)\" -eq 1"
                " && test \"$(grep -Ec '^[[:space:]]*Group[[:space:]]+' /etc/cups/cups-files.conf)\" -eq 1"
                " && test -S /run/cups/cups.sock"
                " && test -f /run/cups/printers.conf"
                " && test ! -e /etc/printcap"
                " && test ! -e /etc/cups/printers.conf"
                " && test ! -e /etc/cups/ssl/*.key",
                check=False,
            )
            if cups_contract.returncode != 0:
                raise RuntimeError(
                    "CUPS privilege or local-only contract mismatch\n"
                    f"rc={cups_contract.returncode} stdout={cups_contract.stdout!r} "
                    f"stderr={cups_contract.stderr!r}\n"
                    + failure_diagnostics(container)
                )
            process_readback = run(
                "docker", "top", container, "-eo", "pid,uid,gid,comm,args",
                check=False,
            )
            process_rows = [line.split(None, 4) for line in process_readback.stdout.splitlines()[1:]]
            root_cupsd = any(
                len(row) == 5 and row[1:4] == ["0", "0", "cupsd"]
                for row in process_rows
            )
            green_service = any(
                len(row) == 5
                and row[1] == green_uid
                and row[2] == green_gid
                and "/opt/green/service.py" in row[4]
                for row in process_rows
            )
            if process_readback.returncode != 0 or not root_cupsd or not green_service:
                raise RuntimeError(
                    "runtime process identity mismatch\n"
                    f"rc={process_readback.returncode} stdout={process_readback.stdout!r} "
                    f"stderr={process_readback.stderr!r}\n"
                    + failure_diagnostics(container)
                )
            tcp_listener = run(
                "docker", "exec", container, "/bin/sh", "-c",
                "! grep -qi ':0277 ' /proc/net/tcp /proc/net/tcp6",
                check=False,
            )
            if tcp_listener.returncode != 0:
                raise RuntimeError("unexpected CUPS TCP listener\n" + failure_diagnostics(container))
            required_paths = {"/api/documents/print-jobs/commands/claim", "/api/documents/print-jobs/claims"}
            if not required_paths.issubset(set(EmptyCanonicalHandler.seen)):
                raise RuntimeError(f"canonical zero-job cycle incomplete: {EmptyCanonicalHandler.seen}")
            health_deadline = time.monotonic() + 70
            docker_health = ""
            while time.monotonic() < health_deadline:
                docker_health = run(
                    "docker", "inspect", "-f", "{{.State.Health.Status}}", container,
                ).stdout.strip()
                if docker_health == "healthy":
                    break
                if docker_health == "unhealthy":
                    raise RuntimeError("container became unhealthy\n" + failure_diagnostics(container))
                time.sleep(1)
            if docker_health != "healthy":
                raise RuntimeError("container health did not become healthy\n" + failure_diagnostics(container))
            denied = apparmor_denials()[positive_denial_baseline:]
            if denied:
                raise RuntimeError(
                    "unexpected AppArmor denials after successful startup\n"
                    + "\n".join(denied[-80:])
                    + "\n"
                    + failure_diagnostics(container)
                )
            print(json.dumps({
                "apparmor": "enforced",
                "business_state": "event_waiting",
                "container_health": "healthy",
                "container_running": True,
                "cups_scheduler_identity": "root-bootstrap",
                "cups_worker_identity": "cupsd:cupsd",
                "green_runtime_identity": "greenprint:greenprint",
                "local_transport": "unix_socket",
                "printcap": "/run/cups/printcap",
                "queue_jobs": 0,
                "printer_dns_preseeded": False,
                "printer_fixed_binding_verified": True,
                "supervisor_data_prechown": False,
                "supervisor_options_root_owned": True,
                "tcp_631_listener": False,
                "tls_key_files": 0,
            }, sort_keys=True))
        finally:
            run("docker", "rm", "-f", container, check=False)
            for server in servers:
                with suppress(Exception):
                    server.shutdown()
                    server.server_close()
            run("sudo", "apparmor_parser", "-R", str(args.profile.resolve()), check=False)
            run("docker", "network", "rm", network, check=False)
            # The initializer deliberately re-owns the mounted app data. Give
            # the synthetic temporary tree back to the runner for cleanup.
            run(
                "sudo", "chown", "-R", f"{os.getuid()}:{os.getgid()}", str(root),
                check=False,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
