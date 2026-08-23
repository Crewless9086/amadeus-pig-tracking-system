"""Validate the bounded GitHub attestation inventory for Green recovery."""

import base64
import json
import sys

PROVENANCE = "https://slsa.dev/provenance/v1"
SBOM = "https://spdx.dev/Document/v2.3"


def _decode_payload(value):
    encoded = str(value or "")
    encoded += "=" * (-len(encoded) % 4)
    return json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))


def inventory(document, expected_name, expected_digest):
    records = document.get("attestations") if isinstance(document, dict) else None
    if not isinstance(records, list):
        raise ValueError("attestation_inventory_malformed")
    counts = {PROVENANCE: 0, SBOM: 0}
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
            if not bound or predicate not in counts:
                foreign += 1
            else:
                counts[predicate] += 1
                statements.append(statement)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            foreign += 1
    return counts[PROVENANCE], counts[SBOM], foreign, statements


def main():
    if len(sys.argv) not in {4, 5}:
        raise SystemExit("usage: inventory.json image sha256:digest [sbom-output]")
    with open(sys.argv[1], encoding="utf-8") as handle:
        document = json.load(handle)
    provenance, sbom, foreign, statements = inventory(
        document, sys.argv[2], sys.argv[3])
    if len(sys.argv) == 5 and sbom == 1:
        statement = next(item for item in statements
            if item.get("predicateType") == SBOM)
        with open(sys.argv[4], "w", encoding="utf-8") as handle:
            json.dump(statement["predicate"], handle, sort_keys=True)
            handle.write("\n")
    print(f"provenance_count={provenance}")
    print(f"sbom_count={sbom}")
    print(f"foreign_count={foreign}")


if __name__ == "__main__":
    main()
