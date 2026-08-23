from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import ssl
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from service import printer_tls_preflight

HOSTNAME = re.compile(r"(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?")


def bootstrap(options_path: str, output_path: str) -> None:
    options = json.loads(Path(options_path).read_text(encoding="utf-8"))
    uri = urlsplit(str(options.get("printer_uri") or ""))
    endpoint_ip = str(options.get("printer_endpoint_ip") or "").strip()
    expected_fingerprint = str(options.get("printer_certificate_sha256") or "").strip().lower()
    queue = str(options.get("cups_queue_id") or "")
    try:
        pin = ipaddress.ip_address(endpoint_ip)
        literal_hostname = ipaddress.ip_address(uri.hostname or "")
    except ValueError:
        try:
            pin = ipaddress.ip_address(endpoint_ip)
        except ValueError as error:
            raise ValueError("invalid printer endpoint pin") from error
        literal_hostname = None
    try:
        port = uri.port or 631
    except ValueError as error:
        raise ValueError("invalid printer port") from error
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", queue)
        or options.get("printer_transport_profile") != "private_ipps"
        or uri.scheme.lower() != "ipps"
        or not uri.hostname
        or (literal_hostname is None and not HOSTNAME.fullmatch(uri.hostname))
        or not pin.is_private
        or (literal_hostname is not None and literal_hostname != pin)
        or uri.username is not None
        or uri.password is not None
        or uri.query
        or uri.fragment
        or not endpoint_ip
        or len(expected_fingerprint) != 64
        or any(character not in "0123456789abcdef" for character in expected_fingerprint)
    ):
        raise ValueError("invalid printer trust identity")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((str(pin), port), timeout=10) as raw:
        with context.wrap_socket(raw, server_hostname=uri.hostname) as tls:
            certificate = tls.getpeercert(binary_form=True)
    if hashlib.sha256(certificate).hexdigest() != expected_fingerprint:
        raise ssl.SSLCertVerificationError("printer certificate fingerprint mismatch")

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix="printer-ca-", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="ascii", newline="\n") as handle:
            handle.write(ssl.DER_cert_to_PEM_cert(certificate))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, target)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    printer_tls_preflight(uri.hostname, str(pin), port, str(target))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(2)
    try:
        bootstrap(sys.argv[1], sys.argv[2])
    except Exception:
        raise SystemExit(1)
