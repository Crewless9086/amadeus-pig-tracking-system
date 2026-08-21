from datetime import datetime, timezone
import inspect

from modules.oom_sakkie.manager_case_sources import _herdmaster, _sam
from modules.oom_sakkie.owner_attention_projection import build_owner_attention_projection
from modules.oom_sakkie.telegram_direct import _format_daily_command_brief
from modules.pig_weights.farm_supabase_read_service import _first_treatment_timing


NOW = datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)


def candidate(key, specialist, summary, action, *, urgency="due", unknowns=(), lifecycle="open",
              welfare_priority=False, identity=None, task_class=None, operational_status="open",
              assigned_worker_id=None, physical_work_ready=False,
              owner_question_eligible=False, irreducible_owner_exception=False):
    return ({"dedupe_key": key, "specialist": specialist, "urgency": urgency,
             "summary": summary, "next_action": action, "unknowns": list(unknowns),
             "evidence_refs": ["event:E1", "observed:2026-08-19T09:50:00+00:00"],
             "next_reassessment_at": "2026-08-19T10:05:00+00:00", "lifecycle": lifecycle,
             "operational_status": operational_status,
             "assigned_worker_id": assigned_worker_id}
            | ({"welfare_priority": True} if welfare_priority else {})
            | ({"presentation_identity": identity} if identity else {})
            | ({"task_class": task_class} if task_class else {})
            | ({"physical_work_ready": True} if physical_work_ready else {})
            | ({"owner_question_eligible": True} if owner_question_eligible else {})
            | ({"irreducible_owner_exception": True} if irreducible_owner_exception else {}))


def test_supported_name_leads_and_reference_is_secondary_with_channel_title_parity():
    projection = build_owner_attention_projection([
        candidate("herdmaster:welfare:pig-125", "HERDMASTER", "Welfare follow-up is due.",
                  "Review the current welfare observation.",
                  identity={"human_name": "Molly", "stable_reference": "tag 125"},
                  task_class="protected_decision", owner_question_eligible=True),
    ], generated_at=NOW)
    item = projection["items"][0]
    assert item["title"] == "Molly — Welfare follow-up is due."
    assert item["primary_label"] == "Molly"
    assert item["secondary_reference"] == "tag 125"
    assert item["identity_state"] == "supported_human_name"
    assert item["title"] in _format_daily_command_brief(
        {"owner_attention": projection, "sections": {}})


def test_missing_and_duplicate_names_are_explicit_safe_and_never_guessed():
    projection = build_owner_attention_projection([
        candidate("sam:conversation:a", "SAM", "Customer reply needs reconciliation.",
                  "SAM owns reconciliation.", task_class="status_reconciliation"),
        candidate("sam:conversation:b", "SAM", "Customer decision is protected.",
                  "Review the protected decision.", task_class="status_reconciliation"),
    ], generated_at=NOW)
    assert all(item["primary_label"] == "Customer name unavailable" for item in projection["items"])
    assert all(item["identity_state"] == "supported_familiar_meaning_disambiguated"
               for item in projection["items"])
    assert {item["secondary_reference"] for item in projection["items"]} == {
        "Reference unavailable"}
    assert all(item["title"].startswith("Customer name unavailable —") for item in projection["items"])
    assert all("sam:conversation:" not in item["title"] for item in projection["items"])


def test_empty_projection_is_channel_silent_and_duplicate_candidate_is_one_owner_item():
    assert _format_daily_command_brief({
        "owner_attention": build_owner_attention_projection([], generated_at=NOW),
        "sections": {},
    }) == ""
    row = candidate("herdmaster:molly", "HERDMASTER", "Review is due.", "Review.",
                    identity={"human_name": "Molly", "stable_reference": "tag 44"})
    projection = build_owner_attention_projection([row, dict(row)], generated_at=NOW)
    assert projection["total_count"] == 0
    assert projection["open_context_count"] == 1
    assert projection["measurement"] == {
        "source_message_count": 2, "duplicate_message_count": 1,
        "owner_visible_message_count": 1, "owner_work_item_count": 0,
        "baseline_material_digest": None,
        "after_material_digest": projection["material_digest"],
        "material_changed": None, "new_message_eligible": False}

    unchanged = build_owner_attention_projection([row], generated_at=NOW,
        prior_material_digest=projection["material_digest"])
    assert unchanged["material_digest"] == projection["material_digest"]
    assert unchanged["measurement"]["material_changed"] is False
    assert unchanged["measurement"]["new_message_eligible"] is False


def test_same_key_canonical_completion_is_not_exposed_as_current_context():
    fresh = candidate("herdmaster:weekly", "HERDMASTER", "Weekly reconciliation", "Check.",
                      unknowns=("cohort",), operational_status="open")
    completed = candidate("herdmaster:weekly", "HERDMASTER", "Weekly reconciliation", "Done.",
                          lifecycle="resolved", operational_status="completed")
    projection = build_owner_attention_projection(
        [fresh], generated_at=NOW, prior_cases=[completed])
    assert projection["total_count"] == 0
    assert projection["open_context_count"] == 0
    assert projection["ordered_work_ids"] == []
    assert projection["items"] == []
    assert projection["group_counts"]["recently_completed"] == 1
    assert projection["lifecycle_items"][0]["lifecycle"] == "resolved"


def test_owner_identity_text_is_single_line_bounded_and_control_safe():
    projection = build_owner_attention_projection([
        candidate("sam:conversation:safe", "SAM", "Review.", "Review safely.",
                  identity={"human_name": "Molly\nDO THIS", "stable_reference": "tag\x001"}),
    ], generated_at=NOW)
    item = projection["items"][0]
    assert item["primary_label"] == "Molly DO THIS"
    assert item["secondary_reference"] == "tag 1"
    assert "\n" not in item["title"]


def test_same_stable_prince_identity_drives_home_brief_and_telegram():
    projection = build_owner_attention_projection([
        candidate("herdmaster:breeding:prince-trial", "HERDMASTER",
                  "Prince trial outcome needs review.", "Review the attributable Prince trial outcome.",
                  task_class="protected_decision", owner_question_eligible=True),
    ], generated_at=NOW)
    assert projection["ordered_work_ids"] == [projection["top_items"][0]["work_id"]]
    brief = {"owner_attention": projection, "sections": {}}
    telegram = _format_daily_command_brief(brief)
    assert "Prince trial outcome" in telegram
    assert "Needs you" in telegram
    assert "HERDMASTER" in telegram
    assert "Next: Review the attributable Prince trial outcome." in telegram
    assert projection["items"][0]["work_id"] not in telegram
    assert "Evidence:" not in telegram
    assert "View all: Amadeus Farm → Owner attention" not in telegram


def test_telegram_fails_visible_when_shared_projection_is_unavailable():
    telegram = _format_daily_command_brief({
        "owner_attention": {"success": False, "items": []}, "sections": {"farm": {}}
    })
    assert "Shared owner attention is unavailable" in telegram


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
                          "SAM must reconcile provider outcome.", urgency="planned",
                          task_class="status_reconciliation") for number in range(4))
    projection = build_owner_attention_projection(rows, generated_at=NOW)
    rootline = next(item for item in projection["items"] if item["specialist_owner"] == "ROOTLINE")
    assert rootline["exact_owner_action"].startswith("No owner action now")
    assert len(projection["top_items"]) == 0
    assert projection["hidden_count"] == 0
    assert projection["group_counts"]["oom_sakkie_checking"] == 5
    assert projection["view_all_target"] == "/owner-attention"


def test_welfare_priority_precedes_urgent_delivery_and_stays_in_top_three():
    rows = [candidate("delivery:SAM:provider", "SAM", "Customer delivery is ambiguous.",
                      "Reconcile provider delivery.", urgency="urgent")]
    rows.extend(candidate(f"runtime:internal:{number}", "RUNTIME", f"Internal issue {number}",
                          "Reconcile internal evidence.", urgency="urgent") for number in range(3))
    rows.append(candidate("herdmaster:welfare:pig-125", "HERDMASTER",
                          "Pig 125 welfare follow-up is due.",
                          "HERDMASTER must retain the welfare lifecycle.", urgency="due",
                          welfare_priority=True, task_class="status_reconciliation"))

    projection = build_owner_attention_projection(rows, generated_at=NOW)

    assert projection["items"][0]["source_key"] == "herdmaster:welfare:pig-125"
    assert projection["items"][0]["welfare_priority"] is True
    assert projection["top_items"] == []
    assert projection["groups"]["oom_sakkie_checking"][0]["source_key"] == "herdmaster:welfare:pig-125"


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
    assert projection["total_count"] == 0
    assert projection["open_context_count"] == 1
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


def test_retained_supported_name_survives_collector_outage_without_name_storage():
    failed = candidate("runtime:collector:herdmaster", "RUNTIME", "HERDMASTER unavailable",
                       "Retry collector.", urgency="urgent", unknowns=("herdmaster_evidence",))
    prior = candidate("herdmaster:welfare:case-1", "HERDMASTER",
                      "Molly has an active welfare case.", "Retain lifecycle.")
    prior["evidence_refs"].append("pig:PIG-44")
    projection = build_owner_attention_projection([failed], generated_at=NOW, prior_cases=[prior])
    retained = next(item for item in projection["items"]
                    if item["source_key"] == "herdmaster:welfare:case-1")
    assert retained["primary_label"] == "Molly"
    assert retained["secondary_reference"] == "PIG-44"
    assert retained["title"].startswith("Molly")


def test_retained_welfare_priority_survives_specialist_outage_from_durable_evidence():
    failed = candidate("runtime:collector:herdmaster", "RUNTIME", "HERDMASTER unavailable",
                       "Retry collector.", urgency="urgent", unknowns=("herdmaster_evidence",))
    welfare = candidate("herdmaster:welfare:pig-125", "HERDMASTER", "Pig 125 welfare follow-up",
                        "Retain the welfare lifecycle.", urgency="due")
    welfare["evidence_refs"].append("attention:welfare_priority")
    delivery = candidate("delivery:SAM:provider", "SAM", "Delivery is ambiguous.",
                         "Reconcile provider delivery.", urgency="urgent")

    projection = build_owner_attention_projection([failed, delivery], generated_at=NOW,
                                                   prior_cases=[welfare])

    assert projection["items"][0]["source_key"] == "herdmaster:welfare:pig-125"
    assert projection["items"][0]["welfare_priority"] is True


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


def test_herdmaster_exact_charl_question_is_owner_eligible_until_consumed(monkeypatch):
    class Value:
        def __init__(self, value): self.value = value
    class Provenance:
        observed_at = NOW
        source_refs = ("canonical:welfare-case",)
    class WorkItem:
        state = Value("urgent")
        authority = Value("advisory")
        assignee = "charl"
        question_for = "charl"
        genuine_question = "Is Prince standing and drinking now?"
        due_at = NOW
        dedupe_key = "prince-welfare"
        title = "Prince welfare follow-up"
        why = "One physical fact is unavailable from canonical evidence."
        next_action = genuine_question
        provenance = Provenance()
        metadata = {}
    class Result:
        result_id = "herd-result-question"
        work_items = (WorkItem(),)
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "owner-1")
    monkeypatch.setattr("modules.oom_sakkie.farm_manager_runtime._load_herdmaster",
                        lambda *_args: Result())
    monkeypatch.setattr("modules.pig_weights.farm_supabase_read_service.get_allocation_input_rows",
                        lambda: {"overview_rows": [], "litter_rows": []})
    rows = _herdmaster(NOW)
    projection = build_owner_attention_projection(rows, generated_at=NOW)
    assert rows[0]["owner_question_eligible"] is True
    assert projection["groups"]["needs_you"][0]["exact_owner_action"] == WorkItem.genuine_question
    assert projection["total_count"] == 1


def test_generic_planned_weigh_wording_is_not_physical_readiness(monkeypatch):
    class Value:
        def __init__(self, value): self.value = value
    class Provenance:
        observed_at = NOW
        source_refs = ("canonical:planning",)
    class WorkItem:
        state = Value("planned")
        authority = Value("advisory")
        assignee = "farm_team"
        question_for = ""
        genuine_question = ""
        due_at = NOW
        dedupe_key = "planned-weigh"
        title = "Later weighing"
        why = "Planning context only."
        next_action = "Weigh now when the cohort is proven ready."
        provenance = Provenance()
        metadata = {}
    class Result:
        result_id = "herd-result-planned"
        work_items = (WorkItem(),)
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "owner-1")
    monkeypatch.setattr("modules.oom_sakkie.farm_manager_runtime._load_herdmaster",
                        lambda *_args: Result())
    monkeypatch.setattr("modules.pig_weights.farm_supabase_read_service.get_allocation_input_rows",
                        lambda: {"overview_rows": [], "litter_rows": []})
    rows = _herdmaster(NOW)
    projection = build_owner_attention_projection(rows, generated_at=NOW)
    assert rows[0].get("physical_work_ready") is not True
    assert projection["total_count"] == 0
    assert projection["groups"]["oom_sakkie_checking"][0]["source_key"].endswith("planned-weigh")


def test_sam_unresolved_work_does_not_expire_by_age():
    source = inspect.getsource(_sam)
    assert "timedelta(days=" not in source
    assert "limit 50" not in source.casefold()
    assert "distinct on (decision_json->'inbound'->>'conversation_id')" in source


def test_molly_missing_weaning_date_remains_status_reconciliation(monkeypatch):
    class Result:
        result_id = "herd-result-molly"
        work_items = ()

    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "owner-1")
    monkeypatch.delenv("PIG_WELFARE_CASE_RUNTIME_ENABLED", raising=False)
    monkeypatch.setattr("modules.oom_sakkie.farm_manager_runtime._load_herdmaster",
                        lambda *_args: Result())
    monkeypatch.setattr("modules.pig_weights.farm_supabase_read_service.get_allocation_input_rows",
                        lambda: {"snapshot_observed_at": NOW.isoformat(), "overview_rows": [],
                                 "litter_rows": [{"Sow_Tag_Number": "Molly",
                                                  "Litter_Status": "Active",
                                                  "Litter_ID": "LIT-MOLLY",
                                                  "Farrowing_Date": "2026-08-11",
                                                  "Wean_Date": None,
                                                  "Weaned_Count": None}]})

    rows = _herdmaster(NOW)

    assert rows[0]["dedupe_key"] == "herdmaster:molly-active-litter"
    assert rows[0]["task_class"] == "status_reconciliation"
    projection = build_owner_attention_projection(rows, generated_at=NOW)
    assert projection["items"][0]["primary_label"] == "Molly"
    assert projection["items"][0]["title"].startswith("Molly")


def test_routine_weekly_weighing_is_primary_only_on_farm_local_monday():
    row = candidate("herdmaster:weekly-weighing:cohort", "HERDMASTER",
                    "Weekly weighing is ready", "Weigh now and record weight.",
                    task_class="physical_action_due", physical_work_ready=True)
    sunday = build_owner_attention_projection(
        [row], generated_at=datetime(2026, 8, 23, 10, tzinfo=timezone.utc))
    monday = build_owner_attention_projection(
        [row], generated_at=datetime(2026, 8, 24, 10, tzinfo=timezone.utc))
    tuesday = build_owner_attention_projection(
        [row], generated_at=datetime(2026, 8, 25, 10, tzinfo=timezone.utc))
    assert sunday["total_count"] == tuesday["total_count"] == 0
    assert sunday["groups"]["watch"][0]["detail_target"] == "/bulk-weights"
    assert monday["total_count"] == 1
    assert monday["groups"]["farm_work_ready"][0]["detail_target"] == "/bulk-weights"


def test_explicit_canonical_exception_allows_individual_weighing_outside_monday():
    row = candidate("herdmaster:weekly-weighing:exception", "HERDMASTER",
                    "Weekly weighing exception is due", "Weigh now and record weight.",
                    task_class="physical_action_due", physical_work_ready=True)
    row["exceptional_weighing_due_now"] = True
    projection = build_owner_attention_projection(
        [row], generated_at=datetime(2026, 8, 25, 10, tzinfo=timezone.utc))
    assert projection["total_count"] == 1
    assert projection["groups"]["farm_work_ready"][0]["detail_target"] == "/bulk-weights"


def test_due_molly_treatment_is_names_first_primary_and_routes_to_exact_litter(monkeypatch):
    class Result:
        result_id = "herd-result-molly-treatment"
        work_items = ()

    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "owner-1")
    monkeypatch.delenv("PIG_WELFARE_CASE_RUNTIME_ENABLED", raising=False)
    monkeypatch.setattr("modules.oom_sakkie.farm_manager_runtime._load_herdmaster",
                        lambda *_args: Result())
    monkeypatch.setattr("modules.pig_weights.farm_supabase_read_service.get_allocation_input_rows",
                        lambda **_kwargs: {"snapshot_observed_at": NOW.isoformat(),
                            "overview_rows": [], "litter_rows": [{
                                "Sow_Tag_Number": "Molly", "Litter_Status": "Active",
                                "Litter_ID": "LIT-MOLLY", "Farrowing_Date": "2026-08-11",
                                "Wean_Date": None, "Weaned_Count": None,
                                "Active_Pig_Count": 8,
                                "first_treatment_attention_due": True,
                                "first_treatment_evidence_state": "due",
                                "first_treatment_attention_date": "2026-08-14"}]})
    projection = build_owner_attention_projection(_herdmaster(NOW), generated_at=NOW)
    item = projection["groups"]["farm_work_ready"][0]
    assert projection["total_count"] == 1
    assert item["primary_label"] == "Molly"
    assert item["title"].startswith("Molly")
    assert item["message_family"] == "litter_first_treatment"
    assert item["detail_target"] == "/litter/LIT-MOLLY"
    assert "product" not in item["exact_owner_action"].casefold()
    assert "dose" not in item["exact_owner_action"].casefold()


def test_valid_individual_and_specialist_focused_routes_exist():
    animal = candidate("herdmaster:individual-weighing:PIG-44", "HERDMASTER",
                       "Pig 44 weighing is due", "Weigh now.",
                       task_class="physical_action_due", physical_work_ready=True)
    animal["exceptional_weighing_due_now"] = True
    animal["evidence_refs"].append("pig:PIG-44")
    beacon = candidate("beacon:current-sale-opportunity", "BEACON", "Media review",
                       "Review.", task_class="informational_watch")
    policy = candidate("rootline:policy-review", "ROOTLINE", "Policy review",
                       "Review.", task_class="informational_watch")
    projection = build_owner_attention_projection([animal, beacon, policy], generated_at=NOW)
    routes = {item["source_key"]: item["detail_target"] for item in projection["items"]}
    assert routes[animal["dedupe_key"]] == "/pig/PIG-44"
    assert routes[beacon["dedupe_key"]] == "/sales/beacon-media"
    assert routes[policy["dedupe_key"]] == "/rootline/policy-review"


def test_unknown_or_completed_molly_treatment_never_becomes_primary():
    for due in (None, False):
        row = candidate("herdmaster:molly-active-litter", "HERDMASTER",
                        "Molly's litter remains under care.", "HERDMASTER checks.",
                        task_class="status_reconciliation" if due is None else "informational_watch",
                        unknowns=("first_treatment_due_state",) if due is None else ())
        row["evidence_refs"].append("litter:LIT-MOLLY")
        projection = build_owner_attention_projection([row], generated_at=NOW)
        assert projection["total_count"] == 0
        assert projection["items"][0]["detail_target"] == "/litter/LIT-MOLLY"
    completed = candidate("herdmaster:molly-active-litter", "HERDMASTER",
                          "Molly's litter first treatment completed.", "No action.",
                          lifecycle="resolved", operational_status="completed",
                          task_class="physical_action_due", physical_work_ready=True)
    completed["evidence_refs"].append("litter:LIT-MOLLY")
    projection = build_owner_attention_projection([], generated_at=NOW,
                                                   prior_cases=[completed])
    assert projection["total_count"] == 0
    assert projection["groups"]["recently_completed"][0]["detail_target"] == "/litter/LIT-MOLLY"


def test_canonical_treatment_timing_distinguishes_unknown_zero_partial_and_completed():
    today = datetime(2026, 8, 21, tzinfo=timezone.utc).date()
    litter = {"farrowing_date": "2026-08-11", "first_treatment_skipped_at": None}
    assert _first_treatment_timing(litter, (), today=today, active_count=0)[
        "first_treatment_evidence_state"] == "unknown"
    assert _first_treatment_timing(litter, (), today=today, active_count=8, partial=True)[
        "first_treatment_evidence_state"] == "partial"
    assert _first_treatment_timing(litter, (), today=today, active_count=8, complete=True)[
        "first_treatment_evidence_state"] == "completed"
    due = _first_treatment_timing(litter, (), today=today, active_count=8)
    assert due["first_treatment_evidence_state"] == "due"
    assert due["first_treatment_attention_due"] is True


def test_treatment_completion_query_counts_only_current_active_on_farm_piglets():
    source = inspect.getsource(__import__(
        "modules.pig_weights.farm_supabase_read_service", fromlist=["x"]
    )._get_allocation_input_rows_queries)
    treatment_case = source.split("as first_treatment_treated_count", 1)[0].rsplit(
        "count(distinct case", 1)[1]
    assert "pig.on_farm is true" in treatment_case
    assert "lower(coalesce(pig.status, '')) = 'active'" in treatment_case
    # Exited/dead/weaned treated members therefore cannot compensate for an
    # untreated member of the current performable population.


def test_focused_routes_reject_unsafe_or_missing_identifiers():
    unsafe = candidate("herdmaster:welfare:unsafe", "HERDMASTER", "Animal welfare",
                       "Reconcile.", task_class="status_reconciliation")
    unsafe["evidence_refs"].append("pig:../owner-attention")
    missing = candidate("herdmaster:molly-active-litter", "HERDMASTER", "Molly care",
                        "Watch.", task_class="informational_watch")
    projection = build_owner_attention_projection([unsafe, missing], generated_at=NOW)
    routes = {item["source_key"]: item["detail_target"] for item in projection["items"]}
    assert routes["herdmaster:welfare:unsafe"] == "/pigs"
    assert routes["herdmaster:molly-active-litter"] == "/litters"
    assert all(".." not in route for route in routes.values())


def test_primary_count_includes_only_protected_decision_and_proven_physical_work():
    rows = [
        candidate("herdmaster:decision", "HERDMASTER", "Purpose choice", "Choose A or B.",
                  task_class="protected_decision", owner_question_eligible=True),
        candidate("herdmaster:weigh", "HERDMASTER", "Physical weighing is ready",
                  "Weigh now and record weight.", task_class="physical_action_due",
                  physical_work_ready=True),
        candidate("sam:delegated", "SAM", "Customer outcome is being reconciled",
                  "SAM must reconcile provider outcome.", unknowns=("provider_outcome",),
                  operational_status="delegated", assigned_worker_id="oom-manager-cycle"),
        candidate("rootline:waiting", "ROOTLINE", "Plan evidence is pending",
                  "Reassess canonical evidence.", unknowns=("current_plan",),
                  operational_status="waiting_reassessment"),
        candidate("beacon:watch", "BEACON", "Useful campaign context", "Watch demand.",
                  task_class="informational_watch"),
    ]
    projection = build_owner_attention_projection(rows, generated_at=NOW)
    assert projection["total_count"] == 2
    assert projection["measurement"]["owner_work_item_count"] == 2
    assert projection["group_counts"] == {
        "needs_you": 1, "farm_work_ready": 1, "oom_sakkie_checking": 2,
        "watch": 1, "recently_completed": 0}
    delegated = next(item for item in projection["items"] if item["source_key"] == "sam:delegated")
    assert delegated["owner_action_eligible"] is False
    assert delegated["owner_urgency"] == "none"
    assert delegated["assigned_to"] == "oom-manager-cycle"


def test_operational_urgency_does_not_create_owner_urgency():
    projection = build_owner_attention_projection([
        candidate("runtime:urgent", "RUNTIME", "Worker status urgent", "Retry worker.",
                  urgency="critical", unknowns=("worker_heartbeat",),
                  operational_status="exception"),
    ], generated_at=NOW)
    item = projection["items"][0]
    assert item["priority"] == "critical"
    assert item["attention_group"] == "oom_sakkie_checking"
    assert item["owner_urgency"] == "none"
    assert projection["total_count"] == 0


def test_urgent_physical_exception_and_completed_history_are_separate():
    projection = build_owner_attention_projection([
        candidate("herdmaster:welfare:urgent", "HERDMASTER", "Urgent welfare check",
                  "Physically inspect now.", urgency="urgent", task_class="physical_action_due",
                  operational_status="exception", welfare_priority=True,
                  physical_work_ready=True, irreducible_owner_exception=True),
        candidate("rootline:shutdown:done", "ROOTLINE", "Shutdown completed", "No action.",
                  lifecycle="resolved", task_class="physical_action_due",
                  operational_status="completed"),
    ], generated_at=NOW)
    assert projection["total_count"] == 1
    assert projection["groups"]["needs_you"][0]["source_key"] == "herdmaster:welfare:urgent"
    assert projection["groups"]["recently_completed"][0]["source_key"] == "rootline:shutdown:done"


def test_seventy_eight_reconciliation_tags_never_become_seventy_eight_owner_actions():
    rows = [candidate(f"herdmaster:weekly-status:{tag}", "HERDMASTER",
                      f"Tag {tag} weekly status is unknown.",
                      "HERDMASTER must reconcile the canonical weighing status.",
                      urgency="urgent", unknowns=("current_weighing_status",),
                      operational_status="waiting_reassessment") for tag in range(1, 79)]
    projection = build_owner_attention_projection(rows, generated_at=NOW)
    assert projection["open_context_count"] == 78
    assert projection["total_count"] == 0
    assert projection["group_counts"]["oom_sakkie_checking"] == 78
    assert projection["top_items"] == []
    assert "Tag 1" not in _format_daily_command_brief(
        {"owner_attention": projection, "sections": {}})


def test_one_work_identity_survives_reconciling_ready_and_completed_states():
    key = "herdmaster:weekly-weighing:cohort"
    reconciling = build_owner_attention_projection([
        candidate(key, "HERDMASTER", "Weekly cohort is being reconciled", "Reassess.",
                  unknowns=("true_cohort",), operational_status="waiting_reassessment")],
        generated_at=NOW)
    ready = build_owner_attention_projection([
        candidate(key, "HERDMASTER", "Weekly weighing is ready", "Weigh now.",
                  task_class="physical_action_due", physical_work_ready=True)], generated_at=NOW)
    completed = build_owner_attention_projection([], generated_at=NOW,
        prior_cases=[candidate(key, "HERDMASTER", "Weekly weighing completed", "No action.",
                               operational_status="completed")])
    identities = {
        reconciling["lifecycle_items"][0]["work_id"], ready["lifecycle_items"][0]["work_id"],
        completed["lifecycle_items"][0]["work_id"]}
    assert len(identities) == 1
    assert completed["groups"]["recently_completed"][0]["owner_action_eligible"] is False


def test_unproven_or_agent_owned_physical_and_protected_work_fails_closed():
    projection = build_owner_attention_projection([
        candidate("herdmaster:unproven-weigh", "HERDMASTER", "Weighing due", "Weigh now.",
                  task_class="physical_action_due"),
        candidate("herdmaster:delegated-weigh", "HERDMASTER", "Weighing due", "Weigh now.",
                  task_class="physical_action_due", physical_work_ready=True,
                  operational_status="delegated", assigned_worker_id="herdmaster-worker"),
        candidate("herdmaster:delegated-decision", "HERDMASTER", "Decision", "Choose.",
                  task_class="protected_decision", owner_question_eligible=True,
                  operational_status="waiting_reassessment", assigned_worker_id="herdmaster-worker"),
    ], generated_at=NOW)
    assert projection["total_count"] == 0
    assert projection["group_counts"]["oom_sakkie_checking"] == 3
    assert all(item["assigned_to"] != "Charl" for item in projection["items"])


def test_canonical_manager_assignment_overrides_fresh_collector_wording():
    current = candidate("herdmaster:ready", "HERDMASTER", "Physical weighing is ready",
                        "Weigh now.", task_class="physical_action_due",
                        physical_work_ready=True)
    prior = candidate("herdmaster:ready", "HERDMASTER", "Earlier generation", "Reassess.",
                      operational_status="delegated", assigned_worker_id="herdmaster-worker")
    projection = build_owner_attention_projection([current], generated_at=NOW,
                                                  prior_cases=[prior])
    item = projection["items"][0]
    assert item["attention_group"] == "oom_sakkie_checking"
    assert item["owner_action_eligible"] is False
    assert item["assigned_to"] == "herdmaster-worker"


def test_context_change_does_not_retrigger_unchanged_primary_owner_work():
    primary = candidate("herdmaster:decision", "HERDMASTER", "Purpose choice", "Choose.",
                        task_class="protected_decision", owner_question_eligible=True)
    before = build_owner_attention_projection([primary], generated_at=NOW)
    after = build_owner_attention_projection([
        primary,
        candidate("rootline:context", "ROOTLINE", "Plan check", "Reassess.",
                  unknowns=("current_plan",), operational_status="waiting_reassessment"),
    ], generated_at=NOW, prior_material_digest=before["material_digest"])
    assert after["material_digest"] == before["material_digest"]
    assert after["context_digest"] != before["context_digest"]
    assert after["measurement"]["material_changed"] is False
    assert after["measurement"]["new_message_eligible"] is False


def test_purpose_review_day_boundary_uses_one_stable_grouped_work_identity(monkeypatch):
    from modules.oom_sakkie.manager_case_sources import _purpose_review_candidates

    base = {"pig_id": "PIG-1", "tag_number": "Rosie", "litter_id": "LIT-1",
            "sow_tag_number": "Molly", "status": "Active", "on_farm": "Yes",
            "purpose": "Unknown", "suggested_purpose": "Breeding Review",
            "purpose_review_due_after_days": 14}
    state = {"rows": []}
    monkeypatch.setattr("modules.pig_weights.pig_weights_service.get_pig_allocation_readiness",
                        lambda **_kwargs: {"success": True, "pigs": state["rows"]})
    args = {"now": NOW, "today": NOW.date(), "observed_at": NOW}
    assert _purpose_review_candidates({}, **args) == []

    state["rows"] = [{**base, "purpose_review_state": "weight_due",
                      "purpose_review_eligible": True}]
    weight = _purpose_review_candidates({}, **args)[0]
    assert weight["dedupe_key"] == "herdmaster:purpose-review:LIT-1"
    assert weight["task_class"] == "physical_action_due"
    assert weight["physical_work_ready"] is True

    state["rows"] = [{**base, "purpose_review_state": "decision_due",
                      "purpose_review_eligible": True}]
    decision = _purpose_review_candidates({}, **args)[0]
    assert decision["dedupe_key"] == weight["dedupe_key"]
    assert decision["task_class"] == "protected_decision"
    assert decision["owner_question_eligible"] is True
    assert decision["detail_target"] == "/pig-allocation?mode=purpose-review&litter_id=LIT-1"


def test_purpose_review_resolved_and_deferred_lifecycle_do_not_repeat(monkeypatch):
    from modules.oom_sakkie.manager_case_sources import _purpose_review_candidates

    row = {"pig_id": "PIG-1", "tag_number": "Rosie", "litter_id": "LIT-1",
           "sow_tag_number": "Molly", "status": "Active", "on_farm": "Yes",
           "purpose": "Unknown", "suggested_purpose": "Breeding Review",
           "purpose_review_state": "decision_due", "purpose_review_eligible": True,
           "purpose_review_due_after_days": 14}
    monkeypatch.setattr("modules.pig_weights.pig_weights_service.get_pig_allocation_readiness",
                        lambda **_kwargs: {"success": True, "pigs": [row]})
    current = _purpose_review_candidates({}, now=NOW, today=NOW.date(), observed_at=NOW)[0]
    deferred = {**current, "operational_status": "waiting_reassessment",
                "assigned_worker_id": "herdmaster-worker"}
    projection = build_owner_attention_projection([current], generated_at=NOW,
                                                  prior_cases=[deferred])
    assert projection["total_count"] == 0
    assert projection["items"][0]["attention_group"] == "oom_sakkie_checking"

    resolved = {**current, "operational_status": "completed", "lifecycle": "resolved"}
    projection = build_owner_attention_projection([], generated_at=NOW,
                                                  prior_cases=[resolved])
    assert projection["total_count"] == 0
    assert projection["groups"]["recently_completed"][0]["source_key"] == current["dedupe_key"]


def test_purpose_review_deep_link_rejects_unsafe_canonical_identifier(monkeypatch):
    from modules.oom_sakkie.manager_case_sources import _purpose_review_candidates

    row = {"pig_id": "PIG-1", "tag_number": "Rosie", "litter_id": "../owner-attention",
           "sow_tag_number": "Molly", "status": "Active", "on_farm": "Yes",
           "purpose": "Unknown", "suggested_purpose": "Grow Out",
           "purpose_review_state": "decision_due", "purpose_review_eligible": True,
           "purpose_review_due_after_days": 14}
    monkeypatch.setattr("modules.pig_weights.pig_weights_service.get_pig_allocation_readiness",
                        lambda **_kwargs: {"success": True, "pigs": [row]})
    candidate_row = _purpose_review_candidates(
        {}, now=NOW, today=NOW.date(), observed_at=NOW,
    )[0]
    assert candidate_row["detail_target"] == "/pig-allocation?mode=purpose-review"


def test_telegram_preserves_shared_group_meaning_without_raw_tag_dump():
    projection = build_owner_attention_projection([
        candidate("herdmaster:decision", "HERDMASTER", "Molly purpose choice", "Choose.",
                  task_class="protected_decision", owner_question_eligible=True),
        candidate("herdmaster:ready", "HERDMASTER", "Weekly work ready", "Weigh now.",
                  task_class="physical_action_due", physical_work_ready=True),
        candidate("rootline:checking", "ROOTLINE", "Tag 78 status", "Reassess.",
                  unknowns=("status",), operational_status="waiting_reassessment"),
        candidate("beacon:watch", "BEACON", "Demand context", "Watch.",
                  task_class="informational_watch"),
    ], generated_at=NOW, prior_cases=[
        candidate("sam:done", "SAM", "Customer work completed", "No action.",
                  operational_status="completed")])
    message = _format_daily_command_brief({"owner_attention": projection, "sections": {}})
    for label in ("Needs you", "Farm work ready", "Oom Sakkie is checking", "Watch",
                  "Recently completed"):
        assert label in message
    assert "Tag 78" not in message


def test_telegram_hidden_count_matches_shared_global_top_three():
    rows = []
    for index in range(4):
        rows.append(candidate(
            f"herdmaster:decision:{index}", "HERDMASTER", f"Decision {index}", "Choose.",
            task_class="protected_decision", owner_question_eligible=True))
        rows.append(candidate(
            f"herdmaster:ready:{index}", "HERDMASTER", f"Ready work {index}", "Do it.",
            task_class="physical_action_due", physical_work_ready=True))
    projection = build_owner_attention_projection(rows, generated_at=NOW)
    message = _format_daily_command_brief({"owner_attention": projection, "sections": {}})
    assert projection["total_count"] == 8
    assert projection["hidden_count"] == 5
    assert message.count("  Next:") == 3
    assert "5 more in What needs attention" in message
