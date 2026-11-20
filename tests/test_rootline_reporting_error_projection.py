import json
from datetime import datetime, timezone
import pytest
from modules.oom_sakkie.automatic_reassessment_scheduler import run_due_reassessment, SCHEDULER_IDENTITY
from scripts.rootline_reassessment_cron import run
from tests.test_rootline_reassessment_cron import Response, ENV

NOW = datetime(2026, 11, 19, 17, 12, tzinfo=timezone.utc)

@pytest.mark.parametrize("label,expected", [
    ("RootlineCycleDeadlineExceeded", "RootlineCycleDeadlineExceeded"),
    ("OperationalError", "OperationalError"), ("AttributeError", "AttributeError"),
    ("private-password-class", "other"), ({"password": "secret"}, "other"),
    (None, None), ("", None),
])
def test_failure_label_survives_persistence_and_cron_without_exception_text(label, expected):
    saved = []
    def store(action, identity, payload):
        if action.startswith("load_"):
            return None
        if action == "record_outcome":
            saved.append(payload)
        return {"success": True, "created": True}
    result = run_due_reassessment(payload={"scheduler_identity": SCHEDULER_IDENTITY,
        "specialist": "ROOTLINE", "due_at": NOW.isoformat(), "evidence_cutoff": NOW.isoformat()},
        now=NOW, store=store, invoke=lambda: {"success": False,
            "status": "scheduled_rootline_reporting_unproven", "error_type": label,
            "exception_message": "private-password-and-provider-body", "telegram_sends": 0,
            "hardware_commands": 0, "report_effects_unknown": True, "writes_farm_data": None})
    calls = []
    def opener(request, timeout):
        calls.append(1)
        return Response(result)
    cron = run(environ=ENV, now=NOW, opener=opener)
    assert calls == [1] and len(saved) == 1
    for projected in (saved[0], cron):
        assert projected.get("error_type") == expected
        assert ("error_type" in projected) is (expected is not None)
        assert "private-password" not in json.dumps(projected)
        assert projected["telegram_sends"] == projected["hardware_commands"] == 0
        assert projected.get("terminal_outcome", projected.get("status")) == "scheduled_rootline_reporting_unproven"
    assert saved[0]["report_effects_unknown"] is True and saved[0]["writes_farm_data"] is None
    assert cron["success"] is False and saved[0]["status"] == "contained"
