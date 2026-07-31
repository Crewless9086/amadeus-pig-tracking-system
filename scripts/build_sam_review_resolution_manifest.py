"""Build the deterministic HERDMASTER manifest from an authoritative export.

This tool is deliberately offline: it never queries Chatwoot, PostgreSQL or
production. The input must contain the exact immutable reviews and the SAM-
owned canonical evidence packet for each review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from modules.sales.sam_review_obligation_resolution import (
    build_resolution_manifest, canonical_sha256,
)


def build(source):
    source = dict(source or {})
    reviews = list(source.get("reviews") or [])
    if len(reviews) != 362:
        raise ValueError("complete_362_review_export_required")
    review_ids = sorted(str(row.get("review_event_id") or "") for row in reviews)
    for row in reviews:
        decision_text = row.get("decision_json_text")
        decision_sha = str(row.get("decision_json_sha256") or "")
        if not isinstance(decision_text, str) or len(decision_sha) != 64:
            raise ValueError("authoritative_decision_text_and_digest_required")
        try:
            semantic_decision = json.loads(decision_text)
        except (TypeError, ValueError) as exc:
            raise ValueError("authoritative_decision_text_invalid") from exc
        if semantic_decision != row.get("decision_json"):
            raise ValueError("authoritative_decision_semantic_mismatch")
        if hashlib.sha256(decision_text.encode()).hexdigest() != decision_sha:
            raise ValueError("authoritative_decision_digest_mismatch")
    expected_ids = sorted(str(value) for value in (source.get("expected_review_event_ids") or []))
    if review_ids != expected_ids:
        raise ValueError("authoritative_review_identity_set_mismatch")
    export_digest = canonical_sha256(sorted(reviews, key=lambda row: str(row.get("review_event_id") or "")))
    if source.get("review_export_sha256") != export_digest:
        raise ValueError("authoritative_review_export_digest_mismatch")
    represented = dict(source.get("represented_identity") or {})
    if represented.get("represented_pig_id") != "PIG-2026-1AC2":
        raise ValueError("exact_represented_identity_required")
    manifest = build_resolution_manifest(
        reviews=reviews,
        evidence_by_review=dict(source.get("evidence_by_review") or {}),
        represented_identity=represented,
    )
    if any(row["represented_pig_id"] != "PIG-2026-1AC2" for row in manifest["rows"]):
        raise ValueError("mixed_represented_identity_denied")
    manifest["authoritative_review_event_ids_sha256"] = canonical_sha256(expected_ids)
    manifest["authoritative_review_export_sha256"] = export_digest
    manifest["manifest_sha256"] = canonical_sha256({
        key: value for key, value in manifest.items() if key != "manifest_sha256"
    })
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    manifest = build(json.loads(args.input.read_text(encoding="utf-8")))
    args.output.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
