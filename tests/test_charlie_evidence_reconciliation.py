import unittest

from modules.charlie.evidence_reconciliation import (
    applicable_passing_agents,
    bind_artifact_to_candidate,
    build_candidate_manifest,
    resolve_effective_agent_results,
    targeted_workflow_return,
)
from modules.charlie import execution_bridge


MISSION = {
    "mission_id": "MISSION-RECONCILE",
    "title": "Candidate reconciliation",
    "metadata": {"acceptance_criteria": ["Only the bounded commercial slice changes."]},
    "agent_workflow": [
        {"agent": "risk_agent", "status": "complete"},
        {"agent": "builder", "status": "complete"},
        {"agent": "tester", "status": "complete"},
        {"agent": "security_reviewer", "status": "complete"},
        {"agent": "reviewer", "status": "complete"},
    ],
}


def artifact(agent, manifest, result="pass", execution="EXEC-1", attempt=1, previous=None, **extra):
    payload = {
        "agent": agent,
        "summary": f"{agent} {result}",
        "status": result,
        "completed_at": f"2026-07-17T00:00:{attempt:02d}+00:00",
        **extra,
    }
    return bind_artifact_to_candidate(payload, agent, execution, attempt, manifest, previous_artifact=previous)


class CharlieEvidenceReconciliationTests(unittest.TestCase):
    def test_legacy_planning_handoff_is_accepted_for_frozen_scope(self):
        manifest = build_candidate_manifest(MISSION, source_commit="current-sha")
        legacy = {
            "summary": "Planning completed before lineage support.",
            "status": "complete",
            "handoff_report": {"status": "complete"},
        }
        result = resolve_effective_agent_results(
            {"idea_expander": legacy}, manifest, workflow=[{"agent": "idea_expander"}],
        )
        self.assertTrue(result["passed"])
        self.assertEqual(
            result["effective_results"]["idea_expander"]["applicability"],
            "accepted_legacy_frozen_scope",
        )

    def test_old_risk_failure_does_not_override_corrected_candidate(self):
        old_manifest = build_candidate_manifest(MISSION, source_commit="old-sha")
        old_risk = artifact("risk_agent", old_manifest, result="blocked")
        current_manifest = build_candidate_manifest(MISSION, {"builder": {"commit_sha": "new-sha", "changed_files": ["modules/a.py"]}}, source_commit="new-sha")
        builder = artifact("builder", current_manifest, commit_sha="new-sha", changed_files=["modules/a.py"])
        tester = artifact("tester", current_manifest, tested_revision="new-sha")
        reviewer = artifact("reviewer", current_manifest, recommended_owner_decision="approve_final_release")

        result = resolve_effective_agent_results(
            {"risk_agent": [old_risk], "builder": builder, "tester": tester, "reviewer": reviewer},
            current_manifest,
            workflow=MISSION["agent_workflow"],
        )

        self.assertFalse(result["active_blockers"])
        self.assertEqual(result["requires_revalidation"][0]["agent"], "risk_agent")
        self.assertEqual(result["recommended_action"]["action"], "targeted_recheck")

    def test_current_risk_failure_remains_a_real_blocker(self):
        manifest = build_candidate_manifest(MISSION, source_commit="current-sha")
        risk = artifact("risk_agent", manifest, result="blocked", recommended_owner_decision="send_back")
        result = resolve_effective_agent_results({"risk_agent": risk}, manifest, workflow=[{"agent": "risk_agent"}])
        self.assertFalse(result["passed"])
        self.assertEqual(result["active_blockers"][0]["agent"], "risk_agent")
        self.assertEqual(result["recommended_action"]["action"], "send_back")

    def test_latest_applicable_artifact_supersedes_earlier_failure(self):
        manifest = build_candidate_manifest(MISSION, source_commit="same-sha")
        failed = artifact("risk_agent", manifest, result="blocked", execution="EXEC-1", attempt=1)
        passed = artifact("risk_agent", manifest, result="pass", execution="EXEC-2", attempt=2, previous=failed)
        result = resolve_effective_agent_results({"risk_agent": [failed, passed]}, manifest, workflow=[{"agent": "risk_agent"}])
        self.assertTrue(result["passed"])
        self.assertEqual(result["effective_results"]["risk_agent"]["artifact_id"], passed["artifact_id"])
        self.assertTrue(any(item["artifact_id"] == failed["artifact_id"] for item in result["historical_results"]))

    def test_structured_findings_keep_resolved_and_follow_up_separate(self):
        manifest = build_candidate_manifest(MISSION, source_commit="same-sha")
        review = artifact(
            "reviewer",
            manifest,
            bugs=[
                {"id": "fixed", "state": "resolved", "finding": "Old branch issue fixed."},
                {"id": "later", "state": "follow_up", "finding": "Adjacent report can be improved."},
            ],
            recommended_owner_decision="approve_final_release",
        )
        result = resolve_effective_agent_results({"reviewer": review}, manifest, workflow=[{"agent": "reviewer"}])
        self.assertTrue(result["passed"])
        self.assertEqual(result["resolved_findings"][0]["finding_id"], "fixed")
        self.assertEqual(result["follow_ups"][0]["finding_id"], "later")

    def test_scope_planning_pass_remains_applicable_after_builder_revision(self):
        planning_manifest = build_candidate_manifest(MISSION)
        planner = artifact("planner", planning_manifest)
        current_manifest = build_candidate_manifest(MISSION, source_commit="new-sha")
        result = resolve_effective_agent_results({"planner": planner}, current_manifest, workflow=[{"agent": "planner"}])
        self.assertTrue(result["passed"])
        self.assertEqual(result["effective_results"]["planner"]["applicability"], "same_frozen_scope")

    def test_targeted_return_preserves_applicable_completed_downstream(self):
        manifest = build_candidate_manifest(MISSION, source_commit="same-sha")
        artifacts = {
            "risk_agent": artifact("risk_agent", manifest),
            "tester": artifact("tester", manifest),
            "security_reviewer": artifact("security_reviewer", manifest, recommended_owner_decision="approve_final_release"),
        }
        preserved = applicable_passing_agents(artifacts, manifest)
        workflow = targeted_workflow_return(MISSION["agent_workflow"], "risk_agent", "Recheck exact candidate.", preserved)
        by_agent = {item["agent"]: item for item in workflow}
        self.assertEqual(by_agent["risk_agent"]["status"], "active")
        self.assertEqual(by_agent["tester"]["status"], "complete")
        self.assertEqual(by_agent["security_reviewer"]["status"], "complete")

    def test_runner_queue_executes_target_only_when_downstream_evidence_is_preserved(self):
        sequence = ["risk_agent", "builder", "tester", "security_reviewer", "reviewer"]
        mission = {
            "metadata": {
                "targeted_invalidation": {
                    "target_agent": "risk_agent",
                    "preserved_agents": ["builder", "tester", "security_reviewer", "reviewer"],
                },
            },
        }
        queue, preserved = execution_bridge._targeted_agent_queue(mission, "risk_agent", sequence)
        self.assertEqual(queue, ["risk_agent"])
        self.assertEqual(preserved, {"builder", "tester", "security_reviewer", "reviewer"})

    def test_changed_scope_invalidates_old_artifact(self):
        old = build_candidate_manifest(MISSION, source_commit="same-sha")
        risk = artifact("risk_agent", old)
        changed = {**MISSION, "metadata": {"acceptance_criteria": ["Expanded scope"]}}
        current = build_candidate_manifest(changed, source_commit="same-sha")
        result = resolve_effective_agent_results({"risk_agent": risk}, current, workflow=[{"agent": "risk_agent"}])
        self.assertEqual(result["requires_revalidation"][0]["reason"], "different_scope")

    def test_manifest_fingerprint_is_deterministic_for_same_candidate(self):
        first = build_candidate_manifest(MISSION, source_commit="same-sha")
        second = build_candidate_manifest(MISSION, source_commit="same-sha")
        self.assertEqual(first["candidate_fingerprint"], second["candidate_fingerprint"])
        self.assertEqual(first["scope_hash"], second["scope_hash"])


if __name__ == "__main__":
    unittest.main()
