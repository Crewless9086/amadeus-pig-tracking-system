from datetime import datetime, timezone

from modules.pig_weights.pig_welfare_case_runtime import (
    load_open_welfare_attention_cases,
    load_open_welfare_case_contexts,
    project_welfare_case_attention,
    welfare_case_readiness,
    welfare_case_runtime_enabled,
)


class Cursor:
    def __init__(self, rows): self.rows = rows; self.one = None
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, sql, params=()):
        if "to_regclass" in sql:
            self.one = (True, True, True)
    def fetchall(self): return self.rows
    def fetchone(self): return self.one


class Connection:
    def __init__(self, rows): self.rows = rows
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def cursor(self): return Cursor(self.rows)


def test_open_case_context_has_no_conversation_age_cutoff_and_preserves_identity():
    context = {"chat_id": "42", "owner_user_id": "42", "mission_id": "OOM-1",
               "status": "waiting_for_input", "provider_timestamp": "2026-01-01T00:00:00+00:00"}
    rows = [("WELFARE-1", "monitoring", "due", "HERDMASTER",
             datetime(2026, 8, 20, 12, tzinfo=timezone.utc), None,
             {"intake_context": context}, datetime(2026, 1, 1, tzinfo=timezone.utc))]
    loaded = load_open_welfare_case_contexts("42", "42", connect_factory=lambda: Connection(rows))
    assert loaded[0]["mission_id"] == "OOM-1"
    assert loaded[0]["welfare_case_id"] == "WELFARE-1"
    assert loaded[0]["welfare_case_next_check_at"] == "2026-08-20T12:00:00+00:00"


def test_wrong_principal_context_fails_closed_even_if_store_returns_it():
    rows = [("WELFARE-1", "open", "urgent", "HERDMASTER", None, None,
             {"intake_context": {"chat_id": "42", "owner_user_id": "99"}},
             datetime.now(timezone.utc))]
    assert load_open_welfare_case_contexts("42", "42", connect_factory=lambda: Connection(rows)) == []


def test_shared_attention_projection_keeps_case_and_work_identity_equal():
    item = project_welfare_case_attention({"welfare_case_id": "WELFARE-1",
        "welfare_case_state": "escalated", "welfare_case_urgency": "critical",
        "welfare_case_next_check_at": "2026-08-20T12:00:00+00:00"})
    assert item["work_identity"] == item["case_identity"] == "WELFARE-1"
    assert item["specialist_owner"] == "HERDMASTER"
    assert item["task_class"] == "status_reconciliation"


def test_attention_projection_requires_explicit_physical_weighing_evidence():
    item = project_welfare_case_attention({"welfare_case_id": "WELFARE-1",
        "welfare_case_state": "escalated", "welfare_case_urgency": "critical",
        "required_action": "Physical weighing due; weigh now and record weight."})
    assert item["task_class"] == "status_reconciliation"


def test_attention_projection_reads_canonical_nested_welfare_action():
    item = project_welfare_case_attention({"welfare_case_id": "WELFARE-PRINCE",
        "welfare_case_state": "monitoring", "welfare_case_urgency": "due",
        "welfare_case_provenance": {"intake_context": {"preview": {"evaluator": {
            "immediate_welfare_priority": {"action": "Weigh now and record weight."}
        }}}}})
    assert item["task_class"] == "physical_action_due"

    negated = project_welfare_case_attention({"welfare_case_id": "WELFARE-PRINCE",
        "welfare_case_provenance": {"intake_context": {"preview": {"evaluator": {
            "immediate_welfare_priority": {"action": "Do not weigh now; reconcile status."}
        }}}}})
    assert negated["task_class"] == "status_reconciliation"
    for action in ("Physical weighing is not required; record weight only after reconciliation.",
                   "No need to weigh now; reconcile status."):
        projected = project_welfare_case_attention({"welfare_case_id": "WELFARE-PRINCE",
            "welfare_case_provenance": {"intake_context": {"preview": {"evaluator": {
                "immediate_welfare_priority": {"action": action}
            }}}}})
        assert projected["task_class"] == "status_reconciliation"


def test_shared_attention_loader_reads_all_open_cases_without_channel_cutoff():
    observed = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)
    rows = [("WELFARE-PRINCE", "PIG-PRINCE", "monitoring", "due", "HERDMASTER",
             None, None, observed, {"intake_context": {}})]
    loaded = load_open_welfare_attention_cases(connect_factory=lambda: Connection(rows))
    assert loaded[0]["welfare_case_id"] == "WELFARE-PRINCE"
    assert loaded[0]["welfare_case_state"] == "monitoring"


def test_readiness_probe_reads_schema_only_and_zero_business_rows():
    body, status = welfare_case_readiness(connect_factory=lambda: Connection([]))
    assert status == 200 and body["success"] is True
    assert body["business_rows_read"] == body["business_rows_written"] == 0


def test_migrated_runtime_defaults_active_with_exact_kill_switch():
    assert welfare_case_runtime_enabled({}) is False
    assert welfare_case_runtime_enabled({"DATABASE_URL": "postgresql://configured"}) is True
    assert welfare_case_runtime_enabled({"PIG_WELFARE_CASE_RUNTIME_ENABLED": "true"}) is True
    assert welfare_case_runtime_enabled({"PIG_WELFARE_CASE_RUNTIME_ENABLED": "1"}) is False
    assert welfare_case_runtime_enabled({"PIG_WELFARE_CASE_RUNTIME_ENABLED": "false"}) is False
