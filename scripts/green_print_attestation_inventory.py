"""Validate the bounded GitHub attestation inventory for Green recovery."""

import base64
import json
import re
import subprocess
import sys

RECOVERY = "https://amadeus.farm/attestations/green-partial-publication-recovery/v1"
SBOM = "https://spdx.dev/Document/v2.3"
EXACT_NOT_FOUND = re.compile(r"gh: Not Found \(HTTP 404\)\r?\n?\Z")


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
    if result.returncode == 1 and not result.stdout and EXACT_NOT_FOUND.fullmatch(
            result.stderr or ""):
        return {"attestations": []}
    raise RuntimeError("attestation_inventory_fetch_failed")


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


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "fetch":
        print(json.dumps(fetch(sys.argv[2], sys.argv[3]), sort_keys=True))
        return
    if len(sys.argv) not in {5, 6, 9} or sys.argv[1] != "inspect":
        raise SystemExit("usage: fetch repo digest | inspect inventory image digest [sbom-output source manifest run-id]")
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
