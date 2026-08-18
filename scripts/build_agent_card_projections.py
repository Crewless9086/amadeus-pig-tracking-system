"""Generate or verify static agent cards from canonical Vault sources."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.charlie.agent_card_projection import AGENT_CARD_SOURCES, projection_findings, write_agent_cards


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        write_agent_cards(ROOT)
    findings, checked = projection_findings(ROOT)
    print(json.dumps({"passed": not findings, "cards": len(AGENT_CARD_SOURCES), "findings": findings}, indent=2))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
