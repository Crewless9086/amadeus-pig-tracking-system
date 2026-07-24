import unittest
from datetime import datetime, timedelta, timezone

from modules.charlie.executive_assurance import doctrine_promotion_decision, evaluate_autonomy_metrics
from modules.charlie.executive_control import (
    authority_decision, build_executive_cycle, capability_tier,
    portfolio_priority, recovery_decision, stable_fingerprint,
)


POLICIES = [{
    "policy_id": "POLICY-1", "capability": "core.internal_recovery",
    "authority_tier": "auto", "enabled": True, "expires_at": None,
}]
DELEGATED_POLICIES = POLICIES + [
    {"policy_id": "POLICY-REVIEW", "capability": "core.review_delegate", "authority_tier": "auto", "enabled": True},
    {"policy_id": "POLICY-SELECT", "capability": "core.queue_select", "authority_tier": "auto", "enabled": True},
]


def blocked(owner_required=False, block_class="implementation_fix_required"):
    return {
        "mission_id": "MISSION-1", "status": "blocked", "urgency": "P1",
        "metadata": {"review_packet": {"blocked_reason": "focused tests failed", "block_disposition": {
            "block_class": block_class, "owner_required": owner_required,
            "responsible_stage": "builder", "reason": "focused tests failed",
        }}},
    }


class CharlieExecutiveControlTests(unittest.TestCase):
    def test_cycle_delegates_green_low_risk_review(self):
        review = {
            "mission_id": "M-REVIEW", "status": "pr_ready", "title": "Docs", "raw_text": "Docs", "approval_level": "LEVEL 3",
            "metadata": {"review_packet": {"review_status": "ready_for_owner_review", "changed_files": ["docs/a.md"], "test_evidence": ["pass"], "pr_url": "https://github.com/o/r/pull/1"}},
        }
        cycle = build_executive_cycle([review], DELEGATED_POLICIES, runner={"active_mission_id": "ACTIVE"})
        self.assertIn("verify_and_delegate_review", [item["action"] for item in cycle["commands"]])

    def test_delegated_review_retries_in_a_later_hour(self):
        review = {
            "mission_id": "M-REVIEW", "status": "pr_ready", "title": "Docs", "raw_text": "Docs", "approval_level": "LEVEL 3",
            "metadata": {"review_packet": {"review_status": "ready_for_owner_review", "changed_files": ["docs/a.md"], "test_evidence": ["pass"], "pr_url": "https://github.com/o/r/pull/1"}},
        }
        first = build_executive_cycle([review], DELEGATED_POLICIES, runner={"active_mission_id": "ACTIVE"}, now=datetime(2026, 7, 17, 20, tzinfo=timezone.utc))
        later = build_executive_cycle([review], DELEGATED_POLICIES, runner={"active_mission_id": "ACTIVE"}, now=datetime(2026, 7, 17, 21, tzinfo=timezone.utc))
        first_key = next(item["idempotency_key"] for item in first["commands"] if item["action"] == "verify_and_delegate_review")
        later_key = next(item["idempotency_key"] for item in later["commands"] if item["action"] == "verify_and_delegate_review")
        self.assertNotEqual(first_key, later_key)

    def test_cycle_selects_only_one_mission_when_runway_is_empty(self):
        missions = [{"mission_id": f"M-{i}", "status": "new", "title": f"Safe {i}", "raw_text": "Improve docs", "urgency": "P1", "approval_level": "LEVEL 3", "metadata": {}} for i in range(5)]
        cycle = build_executive_cycle(missions, DELEGATED_POLICIES, runner={})
        selected = [item for item in cycle["commands"] if item["action"] == "approve_next_work"]
        self.assertEqual(len(selected), 1)

    def test_cycle_does_not_select_more_work_when_one_mission_is_runnable(self):
        missions = [
            {"mission_id": "M-ACTIVE-NEXT", "status": "approved", "metadata": {}},
            {"mission_id": "M-NEW", "status": "new", "title": "Safe", "raw_text": "Improve docs", "approval_level": "LEVEL 3", "metadata": {}},
        ]
        cycle = build_executive_cycle(missions, DELEGATED_POLICIES, runner={})
        self.assertFalse(any(item["action"] == "approve_next_work" for item in cycle["commands"]))

    def test_protected_new_mission_is_not_selected(self):
        mission = {"mission_id": "M-X", "status": "new", "title": "Payment migration", "raw_text": "Change payment schema migration", "approval_level": "LEVEL 3", "metadata": {}}
        cycle = build_executive_cycle([mission], DELEGATED_POLICIES, runner={})
        self.assertFalse(any(item["action"] == "approve_next_work" for item in cycle["commands"]))

    def test_protected_review_notification_changes_with_tested_revision(self):
        def review(revision):
            return {
                "mission_id": "M-PAY", "status": "pr_ready", "title": "Payment integration", "raw_text": "Payment integration",
                "metadata": {"review_packet": {"tested_revision": revision, "pr_url": "https://github.com/o/r/pull/1"}},
            }
        first = build_executive_cycle([review("sha-1")], DELEGATED_POLICIES, runner={})
        second = build_executive_cycle([review("sha-2")], DELEGATED_POLICIES, runner={})
        self.assertNotEqual(first["escalations"][0]["notification_fingerprint"], second["escalations"][0]["notification_fingerprint"])

    def test_cal_re_review_same_candidate_creates_fresh_generation_brief(self):
        def review(generation):
            return {
                "mission_id": "CAL", "status": "pr_ready", "title": "Payment integration", "raw_text": "Payment integration", "urgency": "P1",
                "metadata": {"review_packet": {
                    "tested_revision": "8456b697", "pr_url": "https://github.com/o/r/pull/316",
                    "review_generation": generation,
                }},
            }
        first = build_executive_cycle([review("EXEC-OLD:8456b697")], DELEGATED_POLICIES, runner={})
        second = build_executive_cycle([review("EXEC-NEW:8456b697")], DELEGATED_POLICIES, runner={})
        self.assertNotEqual(first["escalations"][0]["notification_fingerprint"], second["escalations"][0]["notification_fingerprint"])

    def test_high_priority_review_has_only_bounded_reminder_generations(self):
        mission = {
            "mission_id": "M-REMIND", "status": "pr_ready", "title": "Payment integration", "raw_text": "Payment integration", "urgency": "P1",
            "updated_at": "2026-07-17T09:00:00+00:00",
            "metadata": {"review_packet": {"tested_revision": "abc", "review_generation": "EXEC:abc"}},
        }
        cycle = build_executive_cycle([mission], DELEGATED_POLICIES, runner={}, now=datetime(2026, 7, 21, 9, tzinfo=timezone.utc))
        escalation = cycle["escalations"][0]
        self.assertEqual(escalation["brief_type"], "bounded_unresolved_review_reminder")
        self.assertEqual(escalation["realert_sequence"], 2)

    def test_red_zone_cannot_be_delegated_by_normal_policy(self):
        result = authority_decision("core.internal_recovery", POLICIES, risk_flags=["payment"])
        self.assertFalse(result["allowed"])
        self.assertEqual(result["authority_tier"], "charl_human")

    def test_missing_policy_fails_closed(self):
        self.assertFalse(authority_decision("core.unknown", POLICIES)["allowed"])

    def test_expired_policy_fails_closed(self):
        policy = {**POLICIES[0], "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()}
        self.assertFalse(authority_decision("core.internal_recovery", [policy])["allowed"])

    def test_recoverable_block_schedules_targeted_recovery(self):
        result = recovery_decision(blocked(), POLICIES)
        self.assertEqual(result["action"], "schedule_recovery")
        self.assertEqual(result["target_stage"], "builder")
        self.assertTrue(result["idempotency_key"].startswith("schedule_recovery:MISSION-1:"))

    def test_system_incident_creates_internal_repair_instead_of_owner_escalation(self):
        mission = blocked()
        mission["metadata"]["review_packet"].update({
            "review_status": "system_incident_halted",
            "blocked_agent": "security_reviewer",
            "blocked_reason": "Repeated evidence recovery halted.",
            "owner_review_gate_failure": {"fingerprint": "stable-incident"},
        })
        result = recovery_decision(mission, POLICIES)
        self.assertEqual(result["action"], "create_incident_repair")
        self.assertFalse(result["owner_required"])
        cycle = build_executive_cycle([mission], POLICIES, runner={"active_mission_id": "ACTIVE"})
        self.assertIn("create_incident_repair", [item["action"] for item in cycle["commands"]])
        self.assertFalse(any(item.get("mission_id") == "MISSION-1" for item in cycle["escalations"]))

    def test_owner_block_never_auto_recovers(self):
        owner_mission = blocked(owner_required=True)
        owner_mission["metadata"]["review_packet"]["blocked_reason"] = "Owner must decide the pricing business choice."
        result = recovery_decision(owner_mission, POLICIES)
        self.assertEqual(result["action"], "escalate_owner")
        self.assertEqual(result["requested_authority"], "material_owner_decision")
        self.assertIn("if_approved", result)
        self.assertIn("if_declined", result)

    def test_cycle_keeps_unrelated_queue_productive(self):
        missions = [blocked(), {"mission_id": "MISSION-2", "status": "approved", "urgency": "P0", "metadata": {}}]
        policies = POLICIES + [{"policy_id": "P2", "capability": "core.queue_continue", "authority_tier": "auto", "enabled": True}]
        cycle = build_executive_cycle(missions, policies, runner={})
        actions = [item["action"] for item in cycle["commands"]]
        self.assertIn("schedule_recovery", actions)
        self.assertIn("ensure_queue_progress", actions)

    def test_dependency_blocked_approved_rows_do_not_count_as_runway(self):
        missions = [
            {"mission_id": "BLOCKED-CHILD", "status": "approved", "metadata": {"depends_on_mission_ids": ["PARENT"]}},
            {"mission_id": "PARENT", "status": "blocked", "metadata": {"review_packet": {"block_disposition": {"block_class": "owner_decision_required", "owner_required": True}}}},
            {"mission_id": "SAFE-NEW", "status": "new", "title": "Safe docs", "raw_text": "Improve docs", "approval_level": "LEVEL 3", "metadata": {}},
        ]
        cycle = build_executive_cycle(missions, DELEGATED_POLICIES, runner={})
        selected = [item for item in cycle["commands"] if item["action"] == "approve_next_work"]
        self.assertEqual([item["mission_id"] for item in selected], ["SAFE-NEW"])
        self.assertTrue(cycle["queue_health"]["deadlocked"])

    def test_recovery_slice_is_runnable_while_parent_is_blocked(self):
        missions = [
            {"mission_id": "PARENT", "status": "blocked", "metadata": {"review_packet": {"block_disposition": {"block_class": "owner_decision_required", "owner_required": True}}}},
            {"mission_id": "RECOVERY", "status": "approved", "metadata": {
                "depends_on_mission_ids": ["PARENT"],
                "mission_family": {"relationship": "acceptance_recovery", "parent_mission_id": "PARENT"},
            }},
        ]
        cycle = build_executive_cycle(missions, DELEGATED_POLICIES, runner={})
        self.assertEqual(cycle["queue_health"]["runnable_count"], 1)
        self.assertEqual(cycle["queue_rank"][0]["mission_id"], "RECOVERY")

    def test_completed_recovery_children_resume_paused_parent(self):
        missions = [
            {"mission_id": "PARENT", "status": "paused", "metadata": {"mission_coordinator": {"child_mission_ids": ["CHILD-1", "CHILD-2"]}}},
            {"mission_id": "CHILD-1", "status": "done", "metadata": {"mission_family": {"parent_mission_id": "PARENT", "relationship": "acceptance_recovery"}}},
            {"mission_id": "CHILD-2", "status": "merged", "metadata": {"mission_family": {"parent_mission_id": "PARENT", "relationship": "acceptance_recovery"}}},
        ]
        cycle = build_executive_cycle(missions, POLICIES, runner={"active_mission_id": "ACTIVE"})
        command = next(item for item in cycle["commands"] if item["action"] == "reconcile_family")
        self.assertEqual(command["mission_id"], "PARENT")
        self.assertEqual(command["child_states"]["CHILD-1"], "done")

    def test_missing_parent_child_ids_are_repaired_before_family_resume(self):
        missions = [
            {"mission_id": "PARENT", "status": "paused", "metadata": {"mission_coordinator": {"child_mission_ids": []}}},
            {"mission_id": "CHILD-1", "status": "done", "metadata": {"mission_family": {"parent_mission_id": "PARENT"}}},
        ]
        cycle = build_executive_cycle(missions, POLICIES, runner={"active_mission_id": "ACTIVE"})
        repair = next(item for item in cycle["commands"] if item["action"] == "repair_family_links")
        self.assertEqual(repair["child_mission_ids"], ["CHILD-1"])
        self.assertFalse(any(item["action"] == "reconcile_family" for item in cycle["commands"]))

    def test_superseded_children_do_not_reappear_in_parent_links(self):
        missions = [
            {
                "mission_id": "PARENT",
                "status": "paused",
                "metadata": {"mission_coordinator": {"child_mission_ids": ["CHILD-1"]}},
            },
            {
                "mission_id": "CHILD-1",
                "status": "deployed",
                "metadata": {"mission_family": {"parent_mission_id": "PARENT"}},
            },
            {
                "mission_id": "CHILD-DUPLICATE",
                "status": "paused",
                "metadata": {
                    "mission_family": {"parent_mission_id": "PARENT"},
                    "portfolio_disposition": {
                        "status": "superseded",
                        "canonical_mission_id": "CHILD-1",
                        "history_preserved": True,
                    },
                },
            },
        ]
        cycle = build_executive_cycle(missions, POLICIES, runner={"active_mission_id": "ACTIVE"})
        self.assertFalse(any(item["action"] == "repair_family_links" for item in cycle["commands"]))
        command = next(item for item in cycle["commands"] if item["action"] == "reconcile_family")
        self.assertEqual(command["child_states"], {"CHILD-1": "deployed"})

    def test_deployed_but_unapplied_migration_creates_executive_follow_up(self):
        mission = {
            "mission_id": "M-MIG", "status": "deployed", "title": "Lifecycle rail",
            "metadata": {"review_packet": {
                "changed_files": ["supabase/migrations/202607210001.sql"],
                "test_evidence": ["pass"],
            }},
        }
        cycle = build_executive_cycle([mission], POLICIES, runner={})
        command = next(item for item in cycle["commands"] if item["action"] == "record_outcome_follow_up")
        escalation = next(item for item in cycle["escalations"] if item["action"] == "operational_outcome_owner_required")
        self.assertEqual(command["outcome_closure"]["business_capability_status"], "not_operational")
        self.assertEqual(escalation["follow_up_mission_id"], command["outcome_closure"]["follow_up_mission_id"])

    def test_recorded_outcome_and_notification_do_not_repeat_each_cycle(self):
        mission = {
            "mission_id": "M-MIG", "status": "deployed", "title": "Lifecycle rail",
            "metadata": {
                "review_packet": {"changed_files": ["supabase/migrations/202607210001.sql"], "test_evidence": ["pass"]},
                "unfinished_business": {
                    "status": "follow_up_proposed",
                    "follow_up_mission_id": "CHARLIE-OUTCOME-476366FC4C9EBC16",
                    "notification_status": "queued",
                },
            },
        }
        expected = __import__("modules.charlie.outcome_closure", fromlist=["operational_outcome_closure"]).operational_outcome_closure(mission)["follow_up_mission_id"]
        mission["metadata"]["unfinished_business"]["follow_up_mission_id"] = expected
        cycle = build_executive_cycle([mission], POLICIES, runner={"active_mission_id": "ACTIVE"})
        self.assertFalse(any(item["action"] == "record_outcome_follow_up" for item in cycle["commands"]))
        self.assertFalse(any(item.get("block_class") == "unfinished_operational_outcome" for item in cycle["escalations"]))

    def test_queue_progress_fails_closed_without_policy(self):
        cycle = build_executive_cycle([{"mission_id": "MISSION-2", "status": "approved"}], [], runner={})
        self.assertFalse(any(item.get("action") == "ensure_queue_progress" for item in cycle["commands"]))
        self.assertEqual(cycle["escalations"][0]["reason"], "delegation_policy_missing")

    def test_portfolio_prioritizes_revenue_and_urgency(self):
        high = {"status": "approved", "urgency": "P0", "metadata": {"queue": {"revenue_impact": 15}}}
        low = {"status": "approved", "urgency": "P3", "metadata": {}}
        self.assertGreater(portfolio_priority(high), portfolio_priority(low))

    def test_fingerprint_is_deterministic(self):
        self.assertEqual(stable_fingerprint({"b": 2, "a": 1}), stable_fingerprint({"a": 1, "b": 2}))

    def test_trust_requires_observed_history(self):
        self.assertEqual(capability_tier({"runs": 9, "clean_passes": 9}), "watch")
        self.assertEqual(capability_tier({"runs": 20, "clean_passes": 19}), "delegated")
        self.assertEqual(capability_tier({"runs": 50, "clean_passes": 49}), "auto")
        self.assertEqual(capability_tier({"runs": 50, "clean_passes": 50, "escaped_defects": 1}), "watch")

    def test_delegated_policy_requires_promoted_capability_trust(self):
        policy = [{"policy_id": "P-YELLOW", "capability": "orders.prepare_pack", "authority_tier": "charlie_delegated", "enabled": True}]
        denied = authority_decision("orders.prepare_pack", policy, trust=[{"capability_key": "orders.prepare_pack", "tier": "watch"}])
        allowed = authority_decision("orders.prepare_pack", policy, trust=[{"capability_key": "orders.prepare_pack", "tier": "delegated"}])
        self.assertFalse(denied["allowed"])
        self.assertTrue(allowed["allowed"])

    def test_assurance_requires_every_metric(self):
        result = evaluate_autonomy_metrics({"unattended_completion_rate": 1.0})
        self.assertFalse(result["promotion_allowed"])

    def test_assurance_passes_only_full_target_set(self):
        metrics = {
            "unattended_completion_rate": .96, "recoverable_resolution_rate": .99,
            "false_human_escalation_rate_max": .01, "deterministic_gate_pass_rate": 1,
            "unauthorized_red_zone_actions_max": 0, "crash_state_loss_max": 0,
            "substantial_owner_review_rate_max": .05, "delegated_acceptance_rate": .96,
            "improvement_effectiveness_rate": .81,
        }
        self.assertTrue(evaluate_autonomy_metrics(metrics)["promotion_allowed"])

    def test_doctrine_promotion_requires_source_tests_and_owner(self):
        evidence = {"source_refs": ["https://example.test/primary"]}
        self.assertFalse(doctrine_promotion_decision(evidence)["allowed"])
        self.assertTrue(doctrine_promotion_decision(evidence, owner_approved=True, deterministic_tests_passed=True)["allowed"])


if __name__ == "__main__":
    unittest.main()
