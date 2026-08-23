"""Validate the bounded GitHub attestation inventory for Green recovery."""

import base64
import json
import re
import subprocess
import sys
from urllib.parse import urlsplit

RECOVERY = "https://amadeus.farm/attestations/green-partial-publication-recovery/v1"
SBOM = "https://spdx.dev/Document/v2.3"
EXACT_NOT_FOUND = re.compile(r"gh: Not Found \(HTTP 404\)\r?\n?\Z")
NOT_FOUND_DOCUMENTATION = (
    "https://docs.github.com/rest/repos/attestations#list-attestations")
RECOVERY_JOB = "Complete exact partial publication without image or tag push"
RECOVERY_STEP_TRUTH = [
    ("Keylessly sign exact existing arm64 index when absent", "success"),
    ("Attest truthful post-build recovery evidence when absent", "success"),
    ("Attest exact existing SBOM when absent", "success"),
    ("Verify completed signature, attestations and immutable tag", "failure"),
    ("Emit partial-publication recovery receipt", "skipped"),
    ("Preserve partial-publication verified release packet", "skipped"),
]
DEVIATION_JOB = "Complete exact partial publication without image or tag push"
DEVIATION_STEP_TRUTH = [
    ("Keylessly sign exact existing arm64 index when absent", "success"),
    ("Attest truthful post-build recovery evidence when absent", "skipped"),
    ("Attest exact existing SBOM when absent", "skipped"),
    ("Verify completed signature, attestations and immutable tag", "success"),
    ("Emit partial-publication recovery receipt", "success"),
    ("Preserve partial-publication verified release packet", "success"),
]


def _decode_payload(value):
    encoded = str(value or "")
    encoded += "=" * (-len(encoded) % 4)
    return json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))


def fetch(repository, expected_digest, runner=subprocess.run):
    result = runner([
        "gh", "api", "-H", "Accept: application/vnd.github+json",
        f"/repos/{repository}/attestations/{expected_digest}",
    ], capture_output=True, text=True, check=False)
    if result.returncode == 0:
        document = json.loads(result.stdout)
        if not isinstance(document, dict) or not isinstance(
                document.get("attestations"), list):
            raise ValueError("attestation_inventory_malformed")
        return document
    if result.returncode == 1 and EXACT_NOT_FOUND.fullmatch(result.stderr or ""):
        try:
            error = json.loads(result.stdout)
        except (TypeError, json.JSONDecodeError):
            error = None
        if error == {
                "message": "Not Found",
                "documentation_url": NOT_FOUND_DOCUMENTATION,
                "status": "404",
        }:
            return {"attestations": []}
    raise RuntimeError("attestation_inventory_fetch_failed")


def validate_recovery_run(run, jobs, expected_source, expected_run_id):
    if not (run.get("id") == int(expected_run_id) and
            run.get("run_attempt") == 1 and
            run.get("head_sha") == expected_source and
            run.get("event") == "workflow_dispatch" and
            run.get("name") == "Green Print immutable image" and
            run.get("conclusion") == "failure"):
        raise ValueError("recovery_run_identity_mismatch")
    candidates = [job for job in jobs.get("jobs", [])
                  if job.get("name") == RECOVERY_JOB]
    if len(candidates) != 1 or candidates[0].get("conclusion") != "failure":
        raise ValueError("recovery_job_identity_mismatch")
    steps = candidates[0].get("steps")
    if not isinstance(steps, list):
        raise ValueError("recovery_step_chronology_mismatch")
    positions = []
    for name, conclusion in RECOVERY_STEP_TRUTH:
        matches = [step for step in steps if step.get("name") == name and
                   step.get("conclusion") == conclusion and
                   isinstance(step.get("number"), int)]
        if len(matches) != 1:
            raise ValueError("recovery_step_chronology_mismatch")
        positions.append(matches[0]["number"])
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        raise ValueError("recovery_step_chronology_mismatch")


def validate_deviation_run(run, jobs, expected_source, expected_run_id):
    if not (run.get("id") == int(expected_run_id) and
            run.get("run_attempt") == 1 and
            run.get("head_sha") == expected_source and
            run.get("event") == "workflow_dispatch" and
            run.get("name") == "Green Print immutable image" and
            run.get("conclusion") == "success"):
        raise ValueError("deviation_run_identity_mismatch")
    candidates = [job for job in jobs.get("jobs", [])
                  if job.get("name") == DEVIATION_JOB]
    if len(candidates) != 1 or candidates[0].get("conclusion") != "success":
        raise ValueError("deviation_job_identity_mismatch")
    steps = candidates[0].get("steps")
    if not isinstance(steps, list):
        raise ValueError("deviation_step_chronology_mismatch")
    positions = []
    for name, conclusion in DEVIATION_STEP_TRUTH:
        matches = [step for step in steps if step.get("name") == name and
                   step.get("conclusion") == conclusion and
                   isinstance(step.get("number"), int)]
        if len(matches) != 1:
            raise ValueError("deviation_step_chronology_mismatch")
        positions.append(matches[0]["number"])
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        raise ValueError("deviation_step_chronology_mismatch")


def validate_verification_run(document, repository, run_id, attempt="1"):
    if not (str(run_id).isdigit() and str(attempt) == "1"):
        raise ValueError("attestation_run_identity_mismatch")
    if not isinstance(document, list) or len(document) != 1:
        raise ValueError("attestation_verification_result_ambiguous")
    try:
        certificate = document[0]["verificationResult"]["signature"]["certificate"]
        actual = certificate["runInvocationURI"]
    except (KeyError, TypeError):
        raise ValueError("attestation_run_identity_missing") from None
    expected = f"https://github.com/{repository}/actions/runs/{run_id}/attempts/1"
    if actual != expected:
        raise ValueError("attestation_run_identity_mismatch")


def validate_cosign_verification(document, image, digest):
    if not isinstance(document, list):
        raise ValueError("cosign_verification_result_malformed")
    digest_ref = f"{image}@{digest}"
    native = []
    for item in document:
        try:
            if item["critical"]["type"] == \
                    "https://sigstore.dev/cosign/sign/v1":
                native.append(item)
        except (KeyError, TypeError):
            raise ValueError("cosign_verification_result_malformed") from None
    if len(native) != 1:
        raise ValueError("cosign_native_signature_ambiguous")
    item = native[0]
    if not (item["critical"]["identity"]["docker-reference"] == digest_ref and
            item["critical"]["image"]["docker-manifest-digest"] == digest):
        raise ValueError("cosign_native_signature_mismatch")


def inventory(document, expected_name, expected_digest, *, expected_source="",
        expected_manifest="", expected_run_id=""):
    records = document.get("attestations") if isinstance(document, dict) else None
    if not isinstance(records, list):
        raise ValueError("attestation_inventory_malformed")
    counts = {RECOVERY: 0, SBOM: 0}
    foreign = 0
    statements = []
    algorithm, digest = expected_digest.split(":", 1)
    for record in records:
        try:
            statement = _decode_payload(record["bundle"]["dsseEnvelope"]["payload"])
            subjects = statement.get("subject")
            bound = isinstance(subjects, list) and len(subjects) == 1
            if bound:
                subject = subjects[0]
                bound = (subject.get("name") == expected_name and
                    subject.get("digest") == {algorithm: digest})
            predicate = statement.get("predicateType")
            if bound and predicate == RECOVERY:
                recovery = statement.get("predicate")
                bound = (isinstance(recovery, dict) and
                    recovery.get("recoveryKind") ==
                        "post_build_release_evidence_completion" and
                    recovery.get("claimsBuildProvenance") is False and
                    recovery.get("originalPublication") == {
                        "workflow": ".github/workflows/green-print-image.yml",
                        "runId": expected_run_id,
                        "sourceCommit": expected_source,
                        "verifyJob": "success",
                        "publishJob": "failed_after_tag_creation",
                    } and
                    recovery.get("artifact") == {
                        "indexDigest": expected_digest,
                        "soleLinuxArm64ManifestDigest": expected_manifest,
                    } and recovery.get("permittedEffects") == [
                        "signature_if_absent", "sbom_attestation_if_absent",
                        "recovery_attestation_if_absent",
                    ] and recovery.get("prohibitedEffects") == [
                        "image_build", "image_push", "tag_create", "retag",
                        "delete", "install", "print",
                    ])
            if not bound or predicate not in counts:
                foreign += 1
            else:
                counts[predicate] += 1
                statements.append(statement)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            foreign += 1
    return counts[RECOVERY], counts[SBOM], foreign, statements


def canonical_inventory(document):
    """Return a stable, complete representation of every fetched attestation."""
    records = document.get("attestations") if isinstance(document, dict) else None
    if not isinstance(records, list):
        raise ValueError("attestation_inventory_malformed")
    encoded = []
    for record in records:
        if (not isinstance(record, dict) or set(record) != {
                "repository_id", "bundle_url", "initiator", "bundle"} or
                not isinstance(record["repository_id"], int) or
                record["repository_id"] <= 0 or
                not isinstance(record["initiator"], str) or
                not record["initiator"] or
                not isinstance(record["bundle"], dict)):
            raise ValueError("attestation_inventory_malformed")
        location = urlsplit(record["bundle_url"])
        if (location.scheme != "https" or not location.hostname or
                location.username is not None or location.password is not None or
                not location.path or location.fragment or not location.query):
            raise ValueError("attestation_inventory_bundle_url_malformed")
        stable = {
            "repository_id": record["repository_id"],
            "initiator": record["initiator"],
            "bundle_url_identity": f"https://{location.netloc}{location.path}",
            "bundle": record["bundle"],
        }
        encoded.append(json.dumps(stable, sort_keys=True, separators=(",", ":")))
    return {"attestations": [json.loads(item) for item in sorted(encoded)]}


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "fetch":
        print(json.dumps(fetch(sys.argv[2], sys.argv[3]), sort_keys=True))
        return
    if len(sys.argv) == 3 and sys.argv[1] == "canonical":
        with open(sys.argv[2], encoding="utf-8") as handle:
            document = json.load(handle)
        print(json.dumps(canonical_inventory(document), sort_keys=True,
                         separators=(",", ":")))
        return
    if len(sys.argv) == 6 and sys.argv[1] == "validate-recovery-run":
        with open(sys.argv[2], encoding="utf-8") as handle:
            run = json.load(handle)
        with open(sys.argv[3], encoding="utf-8") as handle:
            jobs = json.load(handle)
        validate_recovery_run(run, jobs, sys.argv[4], sys.argv[5])
        return
    if len(sys.argv) == 6 and sys.argv[1] == "validate-deviation-run":
        with open(sys.argv[2], encoding="utf-8") as handle:
            run = json.load(handle)
        with open(sys.argv[3], encoding="utf-8") as handle:
            jobs = json.load(handle)
        validate_deviation_run(run, jobs, sys.argv[4], sys.argv[5])
        return
    if len(sys.argv) == 6 and sys.argv[1] == "validate-verification-run":
        with open(sys.argv[2], encoding="utf-8") as handle:
            document = json.load(handle)
        validate_verification_run(document, sys.argv[3], sys.argv[4], sys.argv[5])
        return
    if len(sys.argv) == 5 and sys.argv[1] == "validate-cosign":
        with open(sys.argv[2], encoding="utf-8") as handle:
            document = json.load(handle)
        validate_cosign_verification(document, sys.argv[3], sys.argv[4])
        return
    if len(sys.argv) not in {5, 6, 9} or sys.argv[1] != "inspect":
        raise SystemExit("usage: fetch repo digest | canonical inventory | inspect inventory image digest [sbom-output source manifest run-id]")
    with open(sys.argv[2], encoding="utf-8") as handle:
        document = json.load(handle)
    recovery, sbom, foreign, statements = inventory(
        document, sys.argv[3], sys.argv[4],
        expected_source=sys.argv[6] if len(sys.argv) == 9 else "",
        expected_manifest=sys.argv[7] if len(sys.argv) == 9 else "",
        expected_run_id=sys.argv[8] if len(sys.argv) == 9 else "")
    if len(sys.argv) in {6, 9} and sbom == 1:
        statement = next(item for item in statements
            if item.get("predicateType") == SBOM)
        with open(sys.argv[5], "w", encoding="utf-8") as handle:
            json.dump(statement["predicate"], handle, sort_keys=True)
            handle.write("\n")
    print(f"recovery_count={recovery}")
    print(f"sbom_count={sbom}")
    print(f"foreign_count={foreign}")


if __name__ == "__main__":
    main()
