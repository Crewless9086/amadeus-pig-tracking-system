from datetime import datetime, timezone
import inspect

from modules.oom_sakkie.manager_case_sources import _herdmaster, _sam
from modules.oom_sakkie.owner_attention_projection import build_owner_attention_projection
from modules.oom_sakkie.telegram_direct import _format_daily_command_brief


NOW = datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)


def candidate(key, specialist, summary, action, *, urgency="due", unknowns=(), lifecycle="open"):
    return {"dedupe_key": key, "specialist": specialist, "urgency": urgency,
            "summary": summary, "next_action": action, "unknowns": list(unknowns),
            "evidence_refs": ["event:E1", "observed:2026-08-19T09:50:00+00:00"],
            "next_reassessment_at": "2026-08-19T10:05:00+00:00", "lifecycle": lifecycle}


def test_same_stable_prince_identity_drives_home_brief_and_telegram():
    projection = build_owner_attention_projection([
        candidate("herdmaster:breeding:prince-trial", "HERDMASTER",
                  "Prince trial outcome needs review.", "Review the attributable Prince trial outcome."),
    ], generated_at=NOW)
    assert projection["ordered_work_ids"] == [projection["top_items"][0]["work_id"]]
    brief = {"owner_attention": projection, "sections": {}}
    telegram = _format_daily_command_brief(brief)
    assert "Prince trial outcome" in telegram
    assert "What needs attention" in telegram
    assert "HERDMASTER" in telegram
    assert "Next: Review the attributable Prince trial outcome." in telegram
    assert projection["items"][0]["work_id"] not in telegram
    assert "Evidence:" not in telegram


def test_molly_and_clovy_status_evidence_classifies_identically_not_as_weighing():
    projection = build_owner_attention_projection([
        candidate("herdmaster:molly-cycle", "HERDMASTER", "Molly status is unresolved.",
                  "HERDMASTER must reconcile canonical cycle status.", unknowns=("cycle_status",)),
        candidate("herdmaster:clovy-cycle", "HERDMASTER", "Clovy status is unresolved.",
                  "HERDMASTER must reconcile canonical cycle status.", unknowns=("cycle_status",)),
    ], generated_at=NOW)
    assert {item["task_class"] for item in projection["items"]} == {"status_reconciliation"}
    assert all(item["semantic_emoji"] == "🔄" for item in projection["items"])


def test_physical_weighing_requires_explicit_physical_evidence():
    projection = build_owner_attention_projection([
        candidate("herdmaster:animal:status", "HERDMASTER", "Weight status is missing.",
                  "Refresh the canonical status.", unknowns=("current_weight_status",)),
        candidate("herdmaster:animal:weigh", "HERDMASTER", "Physical weighing due.",
                  "Weigh now and record weight."),
    ], generated_at=NOW)
    by_key = {item["source_key"]: item for item in projection["items"]}
    assert by_key["herdmaster:animal:status"]["task_class"] == "status_reconciliation"
    assert by_key["herdmaster:animal:weigh"]["task_class"] == "physical_action_due"
    mixed = build_owner_attention_projection([
        candidate("herdmaster:animal:mixed", "HERDMASTER", "Physical weighing due but status unknown.",
                  "Weigh now after status is reconciled.", unknowns=("current_status",)),
    ], generated_at=NOW)
    assert mixed["items"][0]["task_class"] == "status_reconciliation"


def test_rootline_retry_stays_agent_owned_and_top_three_reports_hidden_count():
    rows = [candidate("rootline:current-plan", "ROOTLINE", "Current plan refresh failed.",
                      "Retry canonical ROOTLINE collector.", urgency="urgent",
                      unknowns=("current_plan",))]
    rows.extend(candidate(f"sam:conversation:{number}", "SAM", f"Conversation {number}",
                          "SAM must reconcile provider outcome.", urgency="planned") for number in range(4))
    projection = build_owner_attention_projection(rows, generated_at=NOW)
    rootline = next(item for item in projection["items"] if item["specialist_owner"] == "ROOTLINE")
    assert rootline["exact_owner_action"].startswith("No owner action now")
    assert len(projection["top_items"]) == 3
    assert projection["hidden_count"] == 2
    assert projection["view_all_target"] == "/owner-attention"


def test_resolved_and_superseded_items_are_not_current():
    rows = [candidate(f"herdmaster:prince:{state}", "HERDMASTER", "Prince", "Review.", lifecycle=state)
            for state in ("resolved", "superseded")]
    projection = build_owner_attention_projection(rows, generated_at=NOW)
    assert projection["items"] == []
    assert projection["ordered_work_ids"] == []
    assert {item["lifecycle"] for item in projection["lifecycle_items"]} == {"resolved", "superseded"}


def test_prior_manager_identity_resolves_when_no_longer_canonical_and_duplicates_collapse():
    row = candidate("herdmaster:prince", "HERDMASTER", "Prince", "Review.")
    projection = build_owner_attention_projection([row, dict(row)], generated_at=NOW,
        prior_cases=[candidate("herdmaster:clovy", "HERDMASTER", "Clovy", "Reconcile.")])
    assert projection["total_count"] == 1
    prince = projection["items"][0]
    clovy = next(item for item in projection["lifecycle_items"] if item["source_key"] == "herdmaster:clovy")
    assert clovy["lifecycle"] == "resolved"
    assert clovy["work_id"] != prince["work_id"]


def test_failed_specialist_does_not_resolve_its_prior_work():
    failed = candidate("runtime:collector:herdmaster", "RUNTIME", "HERDMASTER unavailable",
                       "Retry collector.", urgency="urgent", unknowns=("herdmaster_evidence",))
    prior = candidate("herdmaster:prince", "HERDMASTER", "Prince", "Review.")
    projection = build_owner_attention_projection([failed], generated_at=NOW, prior_cases=[prior])
    prince = next(item for item in projection["lifecycle_items"] if item["source_key"] == "herdmaster:prince")
    assert prince["lifecycle"] == "open"
    delivery_failed = candidate("runtime:collector:delivery_gaps", "RUNTIME", "Delivery evidence unavailable",
                                "Retry collector.", urgency="urgent", unknowns=("delivery_evidence",))
    delivery_prior = candidate("delivery:HERDMASTER:abc", "HERDMASTER", "Delivery pending", "Retry safely.")
    delivery_projection = build_owner_attention_projection([delivery_failed], generated_at=NOW,
                                                           prior_cases=[delivery_prior])
    retained = next(item for item in delivery_projection["lifecycle_items"]
                    if item["source_key"] == "delivery:HERDMASTER:abc")
    assert retained["lifecycle"] == "open"


def test_herdmaster_protected_state_is_typed_as_owner_decision(monkeypatch):
    class State:
        value = "protected_owner_decision"

    class Provenance:
        observed_at = NOW
        source_refs = ("canonical:herd",)

    class WorkItem:
        state = State()
        genuine_question = None
        due_at = NOW
        dedupe_key = "purpose-choice"
        title = "Purpose needs Charl's choice"
        why = "Two materially different supported outcomes remain."
        next_action = "Choose the intended purpose."
        provenance = Provenance()

    class Result:
        result_id = "herd-result-1"
        work_items = (WorkItem(),)

    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "owner-1")
    monkeypatch.setattr("modules.oom_sakkie.farm_manager_runtime._load_herdmaster",
                        lambda *_args: Result())
    monkeypatch.setattr("modules.pig_weights.farm_supabase_read_service.get_allocation_input_rows",
                        lambda: {"overview_rows": [], "litter_rows": []})

    rows = _herdmaster(NOW)

    assert rows[0]["task_class"] == "protected_decision"


def test_sam_unresolved_work_does_not_expire_by_age():
    source = inspect.getsource(_sam)
    assert "timedelta(days=" not in source
    assert "limit 50" not in source.casefold()
