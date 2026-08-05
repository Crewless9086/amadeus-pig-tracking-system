"""Governed operator CLI for the existing CHARLIE mission-store replacement rail."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.charlie.mission_store import execute_many_to_one_replacement, prepare_many_to_one_replacement, record_replacement_owner_authorization


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "authorize", "execute"):
        item = sub.add_parser(name)
        item.add_argument("--contract", required=True)
        item.add_argument("--predecessors", required=True)
        if name in {"authorize", "execute"}:
            item.add_argument("--authorization", required=True)
        if name == "execute":
            item.add_argument("--confirm-exact-transaction-digest", required=True)
    args = parser.parse_args()
    contract, predecessors = _read(args.contract), _read(args.predecessors)
    prepared = prepare_many_to_one_replacement(contract, predecessors)
    if args.command == "prepare":
        print(json.dumps({key: prepared[key] for key in (
            "version", "replacement_identity", "successor_mission_id", "predecessor_mission_ids",
            "contract_digest", "predecessor_set_digest", "transaction_digest")}, indent=2))
        return
    if args.command == "authorize":
        result, status_code = record_replacement_owner_authorization(prepared, _read(args.authorization))
        print(json.dumps({"status_code": status_code, **result}, indent=2))
        raise SystemExit(0 if status_code < 400 else 1)
    if args.confirm_exact_transaction_digest != prepared["transaction_digest"]:
        raise SystemExit("confirmed transaction digest does not match prepared contract")
    result, status_code = execute_many_to_one_replacement(contract, predecessors, _read(args.authorization))
    print(json.dumps({"status_code": status_code, **result}, indent=2))
    raise SystemExit(0 if status_code < 400 else 1)


if __name__ == "__main__":
    main()
