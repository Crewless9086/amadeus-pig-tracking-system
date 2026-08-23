"""Fail-closed inventory of the two retained Green native Sigstore bundles."""

import base64
import hashlib
import json
import sys

from cryptography import x509

NATIVE = "https://sigstore.dev/cosign/sign/v1"
RUN_INVOCATION_OID = x509.ObjectIdentifier("1.3.6.1.4.1.57264.1.21")


def _decode_utf8_extension(extension):
    raw = getattr(extension.value, "value", None)
    if not isinstance(raw, bytes) or len(raw) < 2 or raw[0] != 0x0C:
        raise ValueError("native_certificate_run_uri_malformed")
    length = raw[1]
    offset = 2
    if length & 0x80:
        width = length & 0x7F
        if width < 1 or len(raw) < offset + width:
            raise ValueError("native_certificate_run_uri_malformed")
        length = int.from_bytes(raw[offset:offset + width], "big")
        offset += width
    value = raw[offset:offset + length]
    if len(value) != length or offset + length != len(raw):
        raise ValueError("native_certificate_run_uri_malformed")
    return value.decode("utf-8")


def inspect(lines, expected):
    rows = []
    for line in lines:
        try:
            bundle = json.loads(line)
            envelope = bundle["content"]["dsseEnvelope"]
            payload = json.loads(base64.b64decode(envelope["payload"] + "==="))
            if payload.get("critical", {}).get("type") != NATIVE:
                continue
            raw = base64.b64decode(
                bundle["verificationMaterial"]["certificate"]["rawBytes"],
                validate=True)
            certificate = x509.load_der_x509_certificate(raw)
            fingerprint = hashlib.sha256(raw).hexdigest()
            run_uri = _decode_utf8_extension(
                certificate.extensions.get_extension_for_oid(RUN_INVOCATION_OID))
            rows.append({"certificate_sha256": fingerprint,
                         "runInvocationURI": run_uri})
        except (KeyError, TypeError, ValueError, json.JSONDecodeError,
                x509.ExtensionNotFound):
            raise ValueError("native_sigstore_bundle_malformed") from None
    rows.sort(key=lambda row: row["certificate_sha256"])
    wanted = sorted(expected, key=lambda row: row["certificate_sha256"])
    if rows != wanted:
        raise ValueError("native_sigstore_bundle_identity_mismatch")
    return rows


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: bundle-jsonl expected-json")
    with open(sys.argv[1], encoding="utf-8") as handle:
        lines = list(handle)
    with open(sys.argv[2], encoding="utf-8") as handle:
        expected = json.load(handle)
    print(json.dumps(inspect(lines, expected), sort_keys=True))


if __name__ == "__main__":
    main()
