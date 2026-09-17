import json
from pathlib import Path


def workflow():
    return json.loads(Path("docs/04-n8n/workflows/ALERT - Power Backend Delivery/workflow.json").read_text(encoding="utf-8"))


def test_n8n_power_transport_does_not_own_rootline_reassessment():
    data = workflow(); nodes = {node["name"]: node for node in data["nodes"]}
    schedule = data["connections"]["Schedule - Power Alert Delivery"]["main"][0]
    assert {edge["node"] for edge in schedule} == {"Code - Build Evaluate Request"}
    http = nodes["HTTP - Run Oom Sakkie Reassessment"]
    assert http["parameters"]["url"].endswith("/api/oom-sakkie/management/rootline/reassess")
    assert "Code - Build Oom Sakkie Reassessment" not in data["connections"]
    assert http["name"] not in data["connections"]
    assert "telegram" not in http["type"].lower()


def test_retired_n8n_payload_is_inert_and_source_has_no_secret():
    encoded = json.dumps(workflow())
    code = next(n for n in workflow()["nodes"] if n["name"] == "Code - Build Oom Sakkie Reassessment")["parameters"]["jsCode"]
    assert "15" in code and "+02:00" in code and "specialist:'ROOTLINE'" in code
    assert "ALERT-POWER-BACKEND-DELIVERY:OOM-SAKKIE-REASSESSMENT" in code
    assert "CONFIGURE_EXISTING_OOM_SAKKIE_GATEWAY_CREDENTIAL" in encoded
    assert "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN=" not in encoded
