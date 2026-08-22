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
        default=Path(".codex-runtime/missions/PR-1169"),
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
        config_dir = root / "config"
        data_dir = root / "data"
        config_dir.mkdir()
        data_dir.mkdir()
        cert = config_dir / "private-ca.crt"
        key = root / "private-ca.key"
        run(
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-days", "1", "-subj", "/CN=green-startup-probe",
            "-addext", "subjectAltName=DNS:canonical.test,DNS:AmadeusKantoor",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-keyout", str(key), "-out", str(cert),
        )
        run("docker", "network", "create", "--internal", network)
        gateway = run(
            "docker", "network", "inspect", "-f",
            "{{(index .IPAM.Config 0).Gateway}}", network,
        ).stdout.strip()
        canonical = tls_server(cert, key)
        printer = tls_server(cert, key)
        servers.extend((canonical, printer))
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
            "printer_transport_profile": "private_ipps",
            "printer_uri": f"ipps://AmadeusKantoor:{printer.server_port}/ipp/print",
            "printer_endpoint_ip": gateway,
            "poll_seconds": 5,
        }
        (data_dir / "options.json").write_text(json.dumps(options), encoding="utf-8")
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
        data_dir.chmod(0o700)
        run("sudo", "chown", "-R", f"{green_uid}:{green_gid}", str(data_dir))

        try:
            run("sudo", "apparmor_parser", "-r", str(args.profile.resolve()))
            run(
                "docker", "run", "-d", "--name", container,
                "--platform", "linux/arm64", "--network", network,
                "--add-host", f"canonical.test:{gateway}",
                "--security-opt", "apparmor=amadeus-green-print-bridge",
                "--mount", f"type=bind,src={config_dir},dst=/config,readonly",
                "--mount", f"type=bind,src={data_dir},dst=/data",
                args.image,
            )
            deadline = time.monotonic() + 45
            health: dict[str, object] | None = None
            while time.monotonic() < deadline:
                health_readback = run(
                    "docker", "exec", container, "/bin/sh", "-c", "cat /data/health.json",
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
            binding = run(
                "docker", "exec", container, "/bin/sh", "-c",
                f"test \"$(getent ahostsv4 AmadeusKantoor | awk '{{print $1}}' | sort -u)\" = '{gateway}'"
                f" && grep -Fx '{gateway} amadeuskantoor' /etc/hosts",
                check=False,
            )
            if binding.returncode != 0:
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
            denied = apparmor_denials()
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
