"""Secrets-safe environment key ownership audit for Phase 0 governance."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "config" / "environment_ownership.json"
KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def dotenv_key_names(path):
    keys = []
    for raw in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if KEY_PATTERN.fullmatch(key):
            keys.append(key)
    return sorted(set(keys))


def snapshot_key_names(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return sorted(set(str(key) for key in payload.get("keys", []) if KEY_PATTERN.fullmatch(str(key))))


def matching_rule(key, rules):
    exact = [rule for rule in rules if rule.get("match") == "exact" and rule.get("value") == key]
    if exact:
        return exact[0]
    prefixes = [rule for rule in rules if rule.get("match") == "prefix" and key.startswith(str(rule.get("value") or ""))]
    return max(prefixes, key=lambda rule: len(str(rule.get("value") or "")), default=None)


def audit_keys(keys, contract, plane):
    rows, unknown, plane_mismatches, ambiguous, legacy = [], [], [], [], []
    for key in sorted(set(keys)):
        rule = matching_rule(key, contract.get("rules", []))
        if not rule:
            unknown.append(key)
            continue
        row = {
            "key": key, "owner": rule.get("owner"), "planes": rule.get("planes", []),
            "secret_class": rule.get("secret"), "ambiguous": bool(rule.get("ambiguous")),
            "legacy_family": bool(rule.get("legacy_family")),
        }
        rows.append(row)
        if plane not in row["planes"]:
            plane_mismatches.append(key)
        if row["ambiguous"]:
            ambiguous.append(key)
        if row["legacy_family"]:
            legacy.append(key)
    return {
        "version": "environment_ownership_audit_v1", "plane": plane, "values_read": False,
        "key_count": len(set(keys)), "classified_count": len(rows), "unknown_keys": unknown,
        "plane_mismatches": plane_mismatches, "ambiguous_keys": ambiguous,
        "legacy_keys": legacy, "ready": not unknown and not plane_mismatches, "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description="Audit environment key ownership without reading or printing values.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--env-file", type=Path)
    source.add_argument("--keys-snapshot", type=Path)
    parser.add_argument("--plane", required=True)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    keys = dotenv_key_names(args.env_file) if args.env_file else snapshot_key_names(args.keys_snapshot)
    result = audit_keys(keys, contract, args.plane)
    print(json.dumps(result, indent=2))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
