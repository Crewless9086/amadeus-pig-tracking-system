import json
from pathlib import Path


def workflow():
    return json.loads(Path("docs/04-n8n/workflows/ALERT - Power Backend Delivery/workflow.json").read_text(encoding="utf-8"))


def test_existing_scheduler_invokes_existing_endpoint_without_a_telegram_branch():
    data = workflow(); nodes = {node["name"]: node for node in data["nodes"]}
    schedule = data["connections"]["Schedule - Power Alert Delivery"]["main"][0]
    assert {edge["node"] for edge in schedule} == {
        "Code - Build Evaluate Request", "Code - Build Oom Sakkie Reassessment"}
    http = nodes["HTTP - Run Oom Sakkie Reassessment"]
    assert http["parameters"]["url"].endswith("/api/oom-sakkie/management/rootline/reassess")
    assert data["connections"]["Code - Build Oom Sakkie Reassessment"]["main"][0][0]["node"] == http["name"]
    assert http["name"] not in data["connections"]
    assert "telegram" not in http["type"].lower()


def test_schedule_is_sast_bucketed_closed_typed_and_source_has_no_secret():
    encoded = json.dumps(workflow())
    code = next(n for n in workflow()["nodes"] if n["name"] == "Code - Build Oom Sakkie Reassessment")["parameters"]["jsCode"]
    assert "15" in code and "+02:00" in code and "specialist:'ROOTLINE'" in code
    assert "ALERT-POWER-BACKEND-DELIVERY:OOM-SAKKIE-REASSESSMENT" in code
    assert "CONFIGURE_EXISTING_OOM_SAKKIE_GATEWAY_CREDENTIAL" in encoded
    assert "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN=" not in encoded
