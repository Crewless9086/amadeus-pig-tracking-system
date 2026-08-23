"""Fail-closed inventory of the two retained Green native Sigstore bundles."""

import base64
import hashlib
import json
import sys

from cryptography import x509

NATIVE = "https://sigstore.dev/cosign/sign/v1"
SIMPLE_SIGNING = "cosign container image signature"
MEDIA_TYPE = "application/vnd.dev.sigstore.bundle.v0.3+json"
PAYLOAD_TYPE = "application/vnd.in-toto+json"
STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
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


def _decode_base64(value):
    if not isinstance(value, str) or not value:
        raise ValueError("native_sigstore_base64_malformed")
    padded = value + "=" * (-len(value) % 4)
    return base64.b64decode(padded, altchars=b"-_", validate=True)


def _decode_canonical_base64(value):
    if not isinstance(value, str) or not value:
        raise ValueError("native_signature_base64_malformed")
    raw = base64.b64decode(value, validate=True)
    if base64.b64encode(raw).decode("ascii") != value:
        raise ValueError("native_signature_base64_noncanonical")
    return raw


def _certificate_and_native(bundle, image, digest):
    if "critical" in bundle:
        if set(bundle) != {"critical", "optional", "signature", "cert",
                           "bundle"}:
            raise ValueError("native_simple_signing_shape_mismatch")
        critical = bundle["critical"]
        if not (critical.get("type") == SIMPLE_SIGNING and
                set(critical) == {"type", "identity", "image"} and
                critical.get("identity") == {"docker-reference": image} and
                critical.get("image") == {"docker-manifest-digest": digest} and
                isinstance(bundle.get("optional"), dict)):
            raise ValueError("native_simple_signing_payload_mismatch")
        _decode_canonical_base64(bundle["signature"])
        transparency = bundle.get("bundle")
        if not (isinstance(transparency, dict) and
                set(transparency) == {"SignedEntryTimestamp", "Payload"} and
                isinstance(transparency.get("Payload"), dict) and
                set(transparency["Payload"]) == {
                    "body", "integratedTime", "logIndex", "logID"} and
                isinstance(transparency["Payload"]["integratedTime"], int) and
                transparency["Payload"]["integratedTime"] > 0 and
                isinstance(transparency["Payload"]["logIndex"], int) and
                transparency["Payload"]["logIndex"] >= 0 and
                isinstance(transparency["Payload"]["logID"], str) and
                transparency["Payload"]["logID"]):
            raise ValueError("native_transparency_bundle_malformed")
        _decode_canonical_base64(transparency["SignedEntryTimestamp"])
        _decode_canonical_base64(transparency["Payload"]["body"])
        certificate = x509.load_pem_x509_certificate(
            bundle["cert"].encode("ascii"))
        return certificate
    if "dsseEnvelope" in bundle and "critical" in bundle:
        raise ValueError("native_sigstore_bundle_ambiguous")
    if bundle.get("mediaType") != MEDIA_TYPE:
        raise ValueError("native_sigstore_bundle_media_type_mismatch")
    envelope = bundle["dsseEnvelope"]
    if (envelope.get("payloadType") != PAYLOAD_TYPE or
            not isinstance(envelope.get("signatures"), list) or
            len(envelope["signatures"]) != 1 or
            not isinstance(envelope["signatures"][0].get("sig"), str) or
            not envelope["signatures"][0]["sig"]):
        raise ValueError("native_sigstore_envelope_malformed")
    payload = json.loads(_decode_base64(envelope["payload"]))
    if payload.get("_type") != STATEMENT_TYPE:
        raise ValueError("native_sigstore_statement_malformed")
    if payload.get("predicateType") != NATIVE:
        return None
    algorithm, value = digest.split(":", 1)
    if payload.get("subject") != [{"name": image,
                                    "digest": {algorithm: value}}]:
        raise ValueError("native_sigstore_subject_mismatch")
    raw = _decode_base64(
        bundle["verificationMaterial"]["certificate"]["rawBytes"])
    return x509.load_der_x509_certificate(raw)


def inspect(lines, expected, image, digest):
    rows = []
    for line in lines:
        try:
            bundle = json.loads(line)
            certificate = _certificate_and_native(bundle, image, digest)
            if certificate is None:
                continue
            raw = certificate.public_bytes(
                __import__("cryptography").hazmat.primitives.serialization.Encoding.DER)
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
    if len(sys.argv) != 5:
        raise SystemExit("usage: bundle-jsonl expected-json image digest")
    with open(sys.argv[1], encoding="utf-8") as handle:
        lines = list(handle)
    with open(sys.argv[2], encoding="utf-8") as handle:
        expected = json.load(handle)
    print(json.dumps(inspect(lines, expected, sys.argv[3], sys.argv[4]),
                     sort_keys=True))


if __name__ == "__main__":
    main()
