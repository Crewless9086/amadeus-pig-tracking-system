import json
from pathlib import Path
import subprocess


WORKFLOW = (Path(__file__).parents[1] / "docs" / "04-n8n" / "workflows" /
            "2 - The GateKeeper" / "workflow.json")


def _auth_node(nodes):
    matches = [node for node in nodes if node.get("name") == "Get User Info"]
    assert len(matches) == 1
    return matches[0]


def _node(nodes, name):
    matches = [node for node in nodes if node.get("name") == name]
    assert len(matches) == 1
    return matches[0]


def _run_classifier(code, payload):
    harness = f"""
const $json = {json.dumps(payload)};
const $items = () => [{{json: {{user_id: 'manager', chat_id: 'manager'}}}}];
try {{
  const result = (() => {{ {code} }})();
  process.stdout.write(JSON.stringify({{ok: true, result}}));
}} catch (error) {{
  process.stdout.write(JSON.stringify({{ok: false, error: error.message}}));
}}
"""
    completed = subprocess.run(["node", "-e", harness], check=True,
                               capture_output=True, text=True)
    return json.loads(completed.stdout)


def test_gatekeeper_classifies_only_transient_authorization_failures_for_retry():
    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8-sig"))
    collections = [workflow["nodes"]]
    active = workflow.get("activeVersion")
    if isinstance(active, dict) and isinstance(active.get("nodes"), list):
        collections.append(active["nodes"])

    assert len(collections) == 2
    for nodes in collections:
        auth = _auth_node(nodes)
        assert auth["type"] == "n8n-nodes-base.googleSheets"
        assert auth.get("retryOnFail") is not True
        assert auth.get("onError") == "continueErrorOutput"
        classifier = _node(nodes, "Classify Auth Lookup Failure")
        wait = _node(nodes, "Wait Before Auth Retry")
        assert wait["parameters"] == {"amount": 2, "unit": "seconds"}
        code = classifier["parameters"]["jsCode"]
        assert "status === 429 || status >= 500" in code
        assert "attempt >= 4" in code


def test_401_and_403_fail_after_one_lookup_without_retry():
    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8-sig"))
    code = _node(workflow["nodes"], "Classify Auth Lookup Failure")["parameters"]["jsCode"]
    for status in (401, 403):
        outcome = _run_classifier(code, {"statusCode": status, "auth_retry_attempt": 0})
        assert outcome == {"ok": False,
            "error": f"authorization_lookup_non_transient_{status}"}


def test_429_5xx_and_transport_retry_with_bounded_attempt_counter():
    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8-sig"))
    code = _node(workflow["nodes"], "Classify Auth Lookup Failure")["parameters"]["jsCode"]
    for failure in ({"statusCode": 429}, {"statusCode": 503},
                    {"message": "socket timeout"}):
        outcome = _run_classifier(code, {**failure, "auth_retry_attempt": 0})
        assert outcome["ok"] is True
        assert outcome["result"][0]["json"]["auth_retry_attempt"] == 1
    exhausted = _run_classifier(code, {"statusCode": 503, "auth_retry_attempt": 4})
    assert exhausted == {"ok": False,
        "error": "authorization_lookup_transient_exhausted_503"}


def test_gatekeeper_still_fails_closed_after_bounded_retries():
    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8-sig"))
    auth = _auth_node(workflow["nodes"])
    assert auth.get("alwaysOutputData") is True
    assert auth.get("onError") == "continueErrorOutput"
    names = {node.get("name") for node in workflow["nodes"]}
    assert {"Normalize Auth Check", "Security Check", "Classify Auth Lookup Failure",
            "Wait Before Auth Retry"}.issubset(names)
    connections = workflow["connections"]
    assert connections["Get User Info"]["main"][0][0]["node"] == "Merge"
    assert connections["Get User Info"]["main"][1][0]["node"] == (
        "Classify Auth Lookup Failure")
    assert connections["Classify Auth Lookup Failure"]["main"][0][0]["node"] == (
        "Wait Before Auth Retry")
    assert connections["Wait Before Auth Retry"]["main"][0][0]["node"] == "Get User Info"
    # Only a successful lookup can reach Merge/backend routing; retries never fork there.
    assert all(edge["node"] != "Merge" for edge in
               connections["Classify Auth Lookup Failure"]["main"][0])
