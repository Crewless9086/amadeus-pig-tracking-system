"""
Inject Order Intent Extractor pipeline into 1.0 workflow.json.

Reads sibling .js files and updates nodes + connections in-place.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path


HERE = Path(__file__).resolve().parent
WF = HERE.parent / "workflow.json"


NODES = [
    {
        "name": "Code - Build Extractor Inputs",
        "pos": [2288, -96],
        "file": "Code-Build-Extractor-Inputs.js",
    },
    {
        "name": "Code - Should Run Extractor",
        "pos": [2348, -96],
        "file": "Code-Should-Run-Extractor.js",
    },
    {
        "name": "Code - Invoke Order Intent Extractor",
        "pos": [2408, -96],
        "file": "Code-Invoke-Order-Intent-Extractor.js",
        "credentials": {"openAiApi": {"id": "Lp7Z2HFOXfBCGvVg", "name": "OpenAi_Sales Agent"}},
    },
    {
        "name": "Code - Validate Extractor Output",
        "pos": [2468, -96],
        "file": "Code-Validate-Extractor-Output.js",
    },
    {
        "name": "Code - Merge Extractor Into Order State",
        "pos": [2528, -96],
        "file": "Code-Merge-Extractor-Into-Order-State.js",
    },
]


def mk_node(name: str, js: str, pos: list[int], credentials: dict | None = None) -> dict:
    node: dict = {
        "parameters": {"jsCode": js},
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": pos,
        "id": str(uuid.uuid4()),
        "name": name,
    }
    if credentials:
        node["credentials"] = credentials
    return node


def main() -> None:
    wf = json.loads(WF.read_text(encoding="utf-8"))
    nodes = wf.get("nodes", [])
    conn = wf.setdefault("connections", {})

    # Remove extractor nodes by name if re-running patch
    keep = [
        n
        for n in nodes
        if n.get("name")
        not in {spec["name"] for spec in NODES}
    ]
    wf["nodes"] = keep

    # Drop old connections keyed by extractor node names
    for spec in NODES:
        conn.pop(spec["name"], None)

    new_nodes = []
    for spec in NODES:
        fp = HERE / spec["file"]
        js = fp.read_text(encoding="utf-8")
        new_nodes.append(mk_node(spec["name"], js, spec["pos"], spec.get("credentials")))

    wf["nodes"].extend(new_nodes)

    names = {n.get("name") for n in wf["nodes"]}
    if "Code - Align Order Logic" not in names or "Code - Should Create Draft Order?" not in names:
        raise RuntimeError("Missing anchor nodes in workflow.")

    chain = [spec["name"] for spec in NODES]

    conn["Code - Align Order Logic"] = {
        "main": [[{"node": chain[0], "type": "main", "index": 0}]]
    }

    for a, b in zip(chain, chain[1:]):
        conn[a] = {"main": [[{"node": b, "type": "main", "index": 0}]]}

    conn[chain[-1]] = {
        "main": [[{"node": "Code - Should Create Draft Order?", "type": "main", "index": 0}]]
    }

    WF.write_text(json.dumps(wf, ensure_ascii=False), encoding="utf-8")
    print(
        "Patched:",
        WF,
        "; added ",
        ", ".join(chain),
    )


if __name__ == "__main__":
    main()
