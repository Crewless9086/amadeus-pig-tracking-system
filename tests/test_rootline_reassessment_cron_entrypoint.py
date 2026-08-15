import json
import os
from pathlib import Path
import subprocess
import sys


def test_direct_cron_entrypoint_imports_application_outside_repository(tmp_path):
    repository = Path(__file__).resolve().parents[1]
    script = repository / "scripts" / "rootline_reassessment_cron.py"
    environment = dict(os.environ)
    environment.pop("ROOTLINE_REASSESSMENT_SCHEDULER_URL", None)
    environment.pop("OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN", None)
    environment.pop("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", None)
    environment.pop("ROOTLINE_REASSESSMENT_OWNER_USER_ID", None)

    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 1
    assert "ModuleNotFoundError" not in completed.stderr
    assert json.loads(completed.stdout) == {
        "hardware_commands": 0,
        "status": "rootline_scheduler_configuration_invalid",
        "success": False,
        "telegram_sends": 0,
    }
