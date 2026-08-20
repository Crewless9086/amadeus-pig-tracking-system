"""Sign one isolated-validation evidence packet without running or retrying it."""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.validation_receipt import (
    ValidationReceiptError,
    record_validation_receipt,
    sign_validation_receipt,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--signing-key", required=True)
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--validation-id", required=True)
    args = parser.parse_args()
    try:
        evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
        key = Path(args.signing_key).read_bytes()
        receipt = sign_validation_receipt(evidence, key, validation_id=args.validation_id)
        recorded = record_validation_receipt(receipt, args.state_root)
        print(json.dumps({"success": receipt["status"] == "passed", "status": receipt["status"],
                          "validation_id": receipt["validation_id"], **recorded}, sort_keys=True))
        return 0 if receipt["status"] == "passed" else 2
    except (OSError, ValueError, ValidationReceiptError) as exc:
        print(json.dumps({"success": False, "status": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
