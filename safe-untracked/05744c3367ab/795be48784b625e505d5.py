import hashlib
import json
from pathlib import Path

from modules.charlie.runtime_staging import plan_runtime_staging, read_staging_state, stage_runtime


SOURCE = "86fb87a39fd92fb430f683fb1b10c935cbdd0d8f"
ROLLBACK = "98d13d87a1aac63a37ec2dcf7ad6cad35f79a9c2"
CANONICAL = Path(r"C:\Users\charl\OneDrive\1. Amadeus\AGENTS\amadeus-pig-tracking-system")
STATE = CANONICAL / ".charlie_runner"
RUNTIME = STATE / "core-runtime-current"
EXECUTION = STATE / "core-execution-current"
RECEIPT = Path(__file__).with_name("validation-receipt-86fb87a3.json")
EXPECTED_TASK_SHA256 = "5ed7dc9b85eb13f6bd0ac46f67d22680935d2d8c79e800d319298bad8de66fb5"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


before_lane = read_staging_state(STATE)
if before_lane.get("status") != "no_active_release_lane":
    raise SystemExit(json.dumps({"status": "release_lane_not_free", "evidence": before_lane}))
plan = plan_runtime_staging(
    source_ref=SOURCE,
    runtime_root=RUNTIME,
    execution_root=EXECUTION,
    state_root=STATE,
    receipt_path=RECEIPT,
    receipt_sha256=sha256(RECEIPT),
    expected_runtime_head=ROLLBACK,
    expected_execution_head=ROLLBACK,
    expected_manifest_commit=ROLLBACK,
    expected_task_sha256=EXPECTED_TASK_SHA256,
)
result = stage_runtime(plan)
print(json.dumps({"plan": plan, "result": result, "after_lane": read_staging_state(STATE)}, indent=2))
