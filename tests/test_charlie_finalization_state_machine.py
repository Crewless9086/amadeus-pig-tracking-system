import unittest

from modules.charlie import execution_bridge
from modules.charlie.evidence_reconciliation import (
    bind_artifact_to_candidate,
    build_candidate_manifest,
    resolve_effective_agent_results,
)
from modules.charlie.mission_store import _update_workflow_items
from modules.charlie.pr_reconciliation import reconciliation_decision


REVISION = "3051aebe157cd344b0e2e01a11dc68af0bdf6cd8"
MIGRATION = "supabase/migrations/202607200001_create_pig_observation_events.sql"


class CharlieFinalizationStateMachineTests(unittest.TestCase):
    def _mission(self, status="in_progress"):
        return {
            "mission_id": "CHARLIE-SCOPE-1C564A1B7E1C7681",
            "status": status,
            "title": "Herdmaster observation data model",
            "metadata": {"acceptance_criteria": ["Add the bounded observation fact rail."]},
            "agent_workflow": [
                {"agent": "idea_expander", "status": "complete"},
                {"agent": "source_mapper", "status": "complete"},
                {"agent": "builder", "status": "complete"},
                {"agent": "tester", "status": "complete"},
                {"agent": "security_reviewer", "status": "complete"},
                {"agent": "reviewer", "status": "complete"},
                {"agent": "publisher", "status": "complete"},
            ],
        }

    def test_real_mixed_artifact_shape_passes_and_pr_ready_survives_three_reconciliations(self):
        mission = self._mission()
        manifest = build_candidate_manifest(
            mission,
            {"builder": {"changed_files": [MIGRATION], "source_commit": REVISION}},
            source_commit=REVISION,
        )
        legacy_planning = {
            "idea_expander": {"status": "complete", "summary": "Frozen scope expanded.", "handoff_report": {"status": "complete"}},
            "source_mapper": {"status": "complete", "summary": "Sources mapped.", "handoff_report": {"status": "complete"}},
        }
        security = bind_artifact_to_candidate({
            "agent": "security_reviewer",
            "summary": "Security review passed; the migration remains unapplied.",
            "status": "complete",
            "errors": [],
            "bugs": [],
            "recommended_owner_decision": "approve_final_release",
            "changed_files": [MIGRATION],
            "acceptance_results": [{"id": "authority-boundary", "status": "passed"}],
            "next_action": "Owner may approve merge/release of PR #320, but must not approve migration application.",
            "quality_gate": {"passed": True},
        }, "security_reviewer", "EXEC-CANARY", 1, manifest)
        compact_security = execution_bridge._compact_agent_artifacts_for_review(
            {"security_reviewer": security}
        )["security_reviewer"]
        reviewer = bind_artifact_to_candidate({
            "agent": "reviewer",
            "status": "complete",
            "summary": "Current candidate passed final review.",
            "recommended_owner_decision": "approve_final_release",
            "changed_files": [MIGRATION],
            "test_evidence": ["67 focused tests passed"],
            "qa_evidence": ["QA passed"],
            "quality_gate": {"passed": True},
        }, "reviewer", "EXEC-CANARY", 1, manifest)
        artifacts = {**legacy_planning, "security_reviewer": compact_security, "reviewer": reviewer}
        reconciliation = resolve_effective_agent_results(
            artifacts, manifest,
            workflow=[{"agent": agent} for agent in artifacts],
            judgement=execution_bridge._judgement_evidence_quality_gate,
        )

        self.assertTrue(reconciliation["passed"], reconciliation)
        self.assertFalse(reconciliation["active_blockers"])
        self.assertFalse(reconciliation["requires_revalidation"])

        ready = self._mission(status="pr_ready")
        ready["metadata"]["review_packet"] = {
            "tested_revision": REVISION,
            "recommended_owner_decision": "approve_final_release",
            "evidence_reconciliation": reconciliation,
            "protected_operations": [{"operation": "apply_migration", "status": "owner_gated"}],
        }
        pr_state = {
            "success": True,
            "state": "OPEN",
            "mergeable": "MERGEABLE",
            "headRefOid": REVISION,
            "baseRefName": "main",
            "statusCheckRollup": [{"conclusion": "SUCCESS"}] * 3,
        }
        for _ in range(3):
            decision = reconciliation_decision(ready, pr_state)
            self.assertEqual(decision["action"], "none")
            self.assertEqual(decision["reason"], "pr_ready_is_sticky")

    def test_reactivation_clears_completed_timestamp(self):
        workflow = [{"agent": "reviewer", "status": "complete", "completed_at": "2026-07-20T21:00:00+00:00"}]
        updated = _update_workflow_items(workflow, "reviewer", "active", "recheck", "")
        self.assertEqual(updated[0]["status"], "active")
        self.assertNotIn("completed_at", updated[0])

    def test_circuit_breaker_identity_ignores_stage_churn(self):
        status = {
            "evidence_reconciliation": {
                "candidate_manifest": {"source_commit": REVISION},
                "requires_revalidation": [{"agent": "idea_expander", "reason": "legacy"}],
            }
        }
        first = execution_bridge._owner_review_gate_failure(self._mission(), "idea_expander", "legacy", status)
        mission = self._mission()
        mission["metadata"]["review_packet"] = {"owner_review_gate_failure": first}
        second = execution_bridge._owner_review_gate_failure(mission, "evidence_reviewer", "different wording", status)
        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertEqual(second["occurrence"], 2)


if __name__ == "__main__":
    unittest.main()
