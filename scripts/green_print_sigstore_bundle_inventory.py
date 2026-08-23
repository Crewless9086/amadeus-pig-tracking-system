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
    if "critical" in bundle and "dsseEnvelope" in bundle:
        raise ValueError("native_sigstore_bundle_ambiguous")
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
    if (set(bundle) != {"mediaType", "dsseEnvelope",
                        "verificationMaterial"} or
            bundle.get("mediaType") != MEDIA_TYPE):
        raise ValueError("native_sigstore_bundle_media_type_mismatch")
    envelope = bundle["dsseEnvelope"]
    if (not isinstance(envelope, dict) or
            set(envelope) != {"payload", "payloadType", "signatures"} or
            envelope.get("payloadType") != PAYLOAD_TYPE or
            not isinstance(envelope.get("signatures"), list) or
            len(envelope["signatures"]) != 1 or
            not isinstance(envelope["signatures"][0], dict) or
            set(envelope["signatures"][0]) != {"sig"} or
            not isinstance(envelope["signatures"][0].get("sig"), str) or
            not envelope["signatures"][0]["sig"]):
        raise ValueError("native_sigstore_envelope_malformed")
    _decode_canonical_base64(envelope["signatures"][0]["sig"])
    payload = json.loads(_decode_canonical_base64(envelope["payload"]))
    if payload.get("_type") != STATEMENT_TYPE:
        raise ValueError("native_sigstore_statement_malformed")
    verification = bundle["verificationMaterial"]
    if (not isinstance(verification, dict) or set(verification) != {
            "certificate", "timestampVerificationData", "tlogEntries"} or
            not isinstance(verification.get("certificate"), dict) or
            set(verification["certificate"]) != {"rawBytes"} or
            not isinstance(verification.get("timestampVerificationData"), dict) or
            set(verification["timestampVerificationData"]) != {
                "rfc3161Timestamps"} or
            not isinstance(verification["timestampVerificationData"]
                           ["rfc3161Timestamps"], list) or
            len(verification["timestampVerificationData"]
                ["rfc3161Timestamps"]) != 1):
        raise ValueError("native_sigstore_verification_material_malformed")
    timestamp = verification["timestampVerificationData"]\
        ["rfc3161Timestamps"][0]
    if not isinstance(timestamp, dict) or set(timestamp) != {"signedTimestamp"}:
        raise ValueError("native_sigstore_timestamp_malformed")
    _decode_canonical_base64(timestamp["signedTimestamp"])
    entries = verification.get("tlogEntries")
    if not isinstance(entries, list) or len(entries) != 1:
        raise ValueError("native_sigstore_tlog_malformed")
    entry = entries[0]
    if (not isinstance(entry, dict) or set(entry) != {
            "canonicalizedBody", "inclusionPromise", "inclusionProof",
            "integratedTime", "kindVersion", "logId", "logIndex"} or
            not isinstance(entry.get("kindVersion"), dict) or
            entry["kindVersion"] != {"kind": "dsse", "version": "0.0.1"} or
            not isinstance(entry.get("logId"), dict) or
            set(entry["logId"]) != {"keyId"} or
            not isinstance(entry.get("inclusionPromise"), dict) or
            set(entry["inclusionPromise"]) != {"signedEntryTimestamp"} or
            not isinstance(entry.get("integratedTime"), str) or
            not entry["integratedTime"].isdigit() or
            int(entry["integratedTime"]) <= 0 or
            not isinstance(entry.get("logIndex"), str) or
            not entry["logIndex"].isdigit()):
        raise ValueError("native_sigstore_tlog_malformed")
    _decode_canonical_base64(entry["canonicalizedBody"])
    _decode_canonical_base64(entry["logId"]["keyId"])
    _decode_canonical_base64(entry["inclusionPromise"]["signedEntryTimestamp"])
    proof = entry.get("inclusionProof")
    if (not isinstance(proof, dict) or set(proof) != {
            "checkpoint", "hashes", "logIndex", "rootHash", "treeSize"} or
            not isinstance(proof.get("checkpoint"), dict) or
            set(proof["checkpoint"]) != {"envelope"} or
            not isinstance(proof["checkpoint"]["envelope"], str) or
            not proof["checkpoint"]["envelope"] or
            not isinstance(proof.get("hashes"), list) or not proof["hashes"] or
            not all(isinstance(item, str) and item for item in proof["hashes"]) or
            not isinstance(proof.get("logIndex"), str) or
            proof["logIndex"] != entry["logIndex"] or
            not isinstance(proof.get("treeSize"), str) or
            not proof["treeSize"].isdigit() or int(proof["treeSize"]) <= 0):
        raise ValueError("native_sigstore_inclusion_proof_malformed")
    _decode_canonical_base64(proof["rootHash"])
    for item in proof["hashes"]:
        _decode_canonical_base64(item)
    raw = _decode_canonical_base64(
        verification["certificate"]["rawBytes"])
    if payload.get("predicateType") != NATIVE:
        return None
    algorithm, value = digest.split(":", 1)
    if payload.get("subject") != [{"name": image,
                                    "digest": {algorithm: value}}]:
        raise ValueError("native_sigstore_subject_mismatch")
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
