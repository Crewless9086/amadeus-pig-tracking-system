"""
Inject Code-Build-Sync-Existing-Draft-Payload.js into workflow.json (single node).

Run after editing extractor-pipeline/Code-Build-Sync-Existing-Draft-Payload.js .
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WF = HERE.parent / "workflow.json"
JS_FILE = HERE / "Code-Build-Sync-Existing-Draft-Payload.js"
NODE_NAME = "Code - Build Sync Existing Draft Payload"


def main() -> None:
    js = JS_FILE.read_text(encoding="utf-8")
    wf = json.loads(WF.read_text(encoding="utf-8"))
    for n in wf.get("nodes", []):
        if n.get("name") == NODE_NAME:
            n.setdefault("parameters", {})["jsCode"] = js
            break
    else:
        raise SystemExit(f"Node not found: {NODE_NAME}")
    WF.write_text(json.dumps(wf, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Updated {NODE_NAME} in {WF}")


if __name__ == "__main__":
    main()
