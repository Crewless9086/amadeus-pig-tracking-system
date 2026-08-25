import json
from pathlib import Path


WORKFLOW = (Path(__file__).parents[1] / "docs" / "04-n8n" / "workflows" /
            "2 - The GateKeeper" / "workflow.json")


def _auth_node(nodes):
    matches = [node for node in nodes if node.get("name") == "Get User Info"]
    assert len(matches) == 1
    return matches[0]


def test_gatekeeper_retries_transient_authorization_dependency_before_routing():
    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8-sig"))
    collections = [workflow["nodes"]]
    active = workflow.get("activeVersion")
    if isinstance(active, dict) and isinstance(active.get("nodes"), list):
        collections.append(active["nodes"])

    assert len(collections) == 2
    for nodes in collections:
        auth = _auth_node(nodes)
        assert auth["type"] == "n8n-nodes-base.googleSheets"
        assert auth.get("retryOnFail") is True
        assert auth.get("maxTries") == 5
        assert auth.get("waitBetweenTries") == 2000
        assert auth.get("continueOnFail") is not True


def test_gatekeeper_still_fails_closed_after_bounded_retries():
    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8-sig"))
    auth = _auth_node(workflow["nodes"])
    assert auth.get("alwaysOutputData") is True
    assert auth.get("maxTries") <= 5
    names = {node.get("name") for node in workflow["nodes"]}
    assert {"Normalize Auth Check", "Security Check"}.issubset(names)
