import tempfile
import unittest
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from modules.charlie import execution_bridge


MISSION = {
    "mission_id": "CHARLIE-MISSION-EXEC123",
    "status": "in_progress",
    "title": "Build execution bridge",
    "raw_text": "Make Codex execute the mission.",
    "urgency": "P1",
    "mission_type": "agent build",
    "approval_level": "LEVEL 3",
    "vault": {
        "problem_statement": "Approved missions need a local Codex execution bridge.",
        "desired_outcome": "Codex can run locally and stop at owner review.",
        "acceptance_criteria": ["Bridge prepares a prompt.", "Bridge records review evidence."],
        "test_plan": ["Run focused bridge tests."],
        "forbidden_actions": ["No web-triggered shell execution."],
    },
    "agent_workflow": [{"agent": "planner", "status": "active", "purpose": "Scope execution."}],
    "mission_context_pack": {"version": "charlie_context_pack_v1"},
}


def _mission_with_persisted_review_packet(source=None):
    mission = dict(source or MISSION)
    metadata = dict(mission.get("metadata") or {})
    metadata["review_packet"] = {
        "review_status": "ready_for_owner_review",
        "summary": "Persisted owner review packet.",
        "test_evidence": ["unit tests passed"],
    }
    mission["metadata"] = metadata
    return mission


def _mission_readback_sequence(initial_mission, readback_mission):
    calls = {"count": 0}

    def _readback(*_args, **_kwargs):
        calls["count"] += 1
        mission = initial_mission if calls["count"] == 1 else readback_mission
        return {"success": True, "status": "ok", "mission": mission}, 200

    return _readback


def _agent_from_prompt(prompt):
    match = re.search(r"You are the CHARLIE CORE ([A-Z_]+) agent", prompt)
    if match:
        return match.group(1).lower()
    for candidate in execution_bridge.all_agent_names():
        if f"{candidate.upper()} agent" in prompt:
            return candidate
    return "reviewer"


def _successful_stage_payload(agent):
    payload = {
        "summary": f"{agent} completed",
        "errors": [],
        "bugs": [],
        "vault_sources_used": [
            "docs/09-vault-brain/INDEX.md",
            "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md",
        ],
        "vault_updates": [],
        "no_vault_update_required": "No agent/workflow/business/data/standard doctrine changed in this stage.",
        "files_inspected": [
            "modules/charlie/execution_bridge.py",
            "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md",
            "tests/test_charlie_execution_bridge.py",
        ] if agent == "source_mapper" else ["modules/charlie/execution_bridge.py"],
        "commands_run": ["python -m unittest tests.test_charlie_execution_bridge"],
        "stdout_tail": "",
        "stderr_tail": "",
        "confidence": "98%",
        "confidence_reason": "Based on Vault Brain source docs, inspected repo files, and focused test evidence.",
        "next_action": "continue",
        "opportunity": "clear owner opportunity" if agent == "idea_expander" else None,
        "owner_value": "owner value clear" if agent == "idea_expander" else None,
        "non_goals": ["no broad rebuild"] if agent == "idea_expander" else None,
        "user_flow": ["owner creates mission", "agents execute", "owner reviews"] if agent == "product_architect" else None,
        "acceptance_boundaries": ["owner approval remains required"] if agent == "product_architect" else None,
        "implementation_inventory": ["Mapped current app and legacy sources"] if agent == "source_mapper" else None,
        "current_sources": ["modules/charlie/execution_bridge.py"] if agent == "source_mapper" else None,
        "legacy_sources": ["none"] if agent == "source_mapper" else None,
        "routes_found": ["/api/charlie/runner-status"] if agent == "source_mapper" else None,
        "tests_to_run": ["tests.test_charlie_execution_bridge"] if agent == "source_mapper" else None,
        "migrations_found": ["none"] if agent == "source_mapper" else None,
        "source_truth_summary": "Current source mapped" if agent == "source_mapper" else None,
        "files_to_inspect": ["modules/charlie/execution_bridge.py"] if agent in {"technical_architect", "architect"} else None,
        "risk_notes": ["risk checked"] if agent in {"product_architect", "technical_architect", "architect"} else None,
        "implementation_plan": ["patch runner"] if agent in {"technical_architect", "architect"} else None,
        "implementation_sources_used": [
            "modules/charlie/execution_bridge.py",
            "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md",
            "tests/test_charlie_execution_bridge.py",
        ] if agent == "source_mapper" else ["modules/charlie/execution_bridge.py"] if agent == "technical_architect" else None,
        "agreements": ["owner intent preserved"] if agent == "council_synthesis" else None,
        "conflicts_resolved": ["product and technical brief aligned"] if agent == "council_synthesis" else None,
        "unresolved_blockers": [] if agent == "council_synthesis" else None,
        "build_brief": "build the scoped owner workflow" if agent == "council_synthesis" else None,
        "acceptance_priorities": ["visible owner actions"] if agent == "council_synthesis" else None,
        "acceptance_criteria": ["acceptance"] if agent == "planner" else None,
        "test_plan": ["tests"] if agent == "planner" else None,
        "changed_files": ["modules/charlie/execution_bridge.py"] if agent in {"builder", "reviewer"} else None,
        "build_notes": ["patched"] if agent == "builder" else None,
        "branch_name": "charlie/test-pr-evidence" if agent == "builder" else None,
        "commit_sha": "abc1234" if agent == "builder" else None,
        "pr_url": "https://github.com/org/repo/pull/61" if agent in {"builder", "reviewer"} else None,
        "links": {"pr": "https://github.com/org/repo/pull/61"} if agent in {"builder", "reviewer"} else None,
        "tests_run": ["unit tests passed"] if agent == "tester" else None,
        "test_status": "pass" if agent == "tester" else None,
        "qa_findings": ["no high risk found"] if agent == "qa_red_team" else None,
        "red_team_status": "pass" if agent == "qa_red_team" else None,
        "risk_rating": "low" if agent == "qa_red_team" else None,
        "recommended_owner_decision": "approve_final_release" if agent in {"product_reviewer", "business_reviewer", "security_reviewer", "evidence_reviewer", "reviewer", "publisher"} else None,
        "release_notes": ["owner review ready"] if agent in {"reviewer", "publisher"} else None,
        "changed_files": ["modules/charlie/execution_bridge.py"] if agent in {"builder", "product_reviewer", "business_reviewer", "security_reviewer", "evidence_reviewer", "reviewer", "publisher"} else None,
        "test_evidence": ["unit tests passed"] if agent in {"product_reviewer", "business_reviewer", "security_reviewer", "evidence_reviewer", "reviewer", "publisher"} else None,
        "qa_evidence": ["QA/red-team passed"] if agent in {"product_reviewer", "business_reviewer", "security_reviewer", "evidence_reviewer", "reviewer", "publisher"} else None,
    }
    return {key: value for key, value in payload.items() if value is not None}


class CharlieExecutionBridgeTests(unittest.TestCase):
    def setUp(self):
        self.builder_admission = patch(
            "modules.charlie.execution_bridge.build_admission",
            return_value={
                "allowed": True,
                "status": "build_admitted",
                "canonical_root": "C:/tmp/test-control",
                "declared_files": ["modules/charlie/execution_bridge.py"],
                "lease": {"lease_id": "test-builder-lease"},
            },
        )
        self.build_admission = self.builder_admission.start()
        self.addCleanup(self.builder_admission.stop)
        self.builder_lease_release = patch(
            "modules.charlie.execution_bridge.release_file_lease",
            return_value={"released": True, "status": "file_scope_released"},
        )
        self.release_file_lease = self.builder_lease_release.start()
        self.addCleanup(self.builder_lease_release.stop)
        self.owner_review_finalizer = patch(
            "modules.charlie.execution_bridge.finalize_owner_review_transaction",
            return_value=({"success": True, "status": "owner_review_finalized", "mission_status": "pr_ready"}, 200),
        )
        self.finalize_owner_review = self.owner_review_finalizer.start()
        self.addCleanup(self.owner_review_finalizer.stop)
        self.github_finalization_gate = patch(
            "modules.charlie.execution_bridge._build_github_finalization_gate",
            return_value={
                "version": "charlie_github_finalization_gate_v1",
                "passed": True,
                "reasons": [],
                "head_revision": "test-candidate",
            },
        )
        self.build_github_finalization_gate = self.github_finalization_gate.start()
        self.addCleanup(self.github_finalization_gate.stop)
        self.git_head_revision_patch = patch(
            "modules.charlie.execution_bridge._git_head_revision",
            return_value="abc1234",
        )
        self.git_head_revision = self.git_head_revision_patch.start()
        self.addCleanup(self.git_head_revision_patch.stop)

    def test_builder_concurrency_admission_uses_declared_scope_and_execution_holder(self):
        mission = {
            "mission_id": "MISSION-SAFE-BUILDER",
            "metadata": {"review_packet": {"changed_files": ["modules/charlie/execution_bridge.py"]}},
        }

        result = execution_bridge._builder_concurrency_admission(mission, {}, "EXEC-123")

        self.assertTrue(result["allowed"])
        self.build_admission.assert_called_once_with(
            execution_bridge.REPO_ROOT,
            "MISSION-SAFE-BUILDER",
            ["modules/charlie/execution_bridge.py"],
            holder="execution:EXEC-123:builder",
        )

    def test_builder_concurrency_lease_release_uses_admission_registry(self):
        result = execution_bridge._release_builder_concurrency_admission({
            "canonical_root": "C:/tmp/control",
            "lease": {"lease_id": "lease-123"},
        })

        self.assertTrue(result["released"])
        self.release_file_lease.assert_called_once_with("C:/tmp/control", "lease-123")

    def test_owner_review_artifact_gate_rejects_send_back_stage(self):
        mission = {"mission_context_pack": {"agent_order": ["builder", "business_reviewer", "evidence_reviewer"]}}
        artifacts = {
            "builder": {"summary": "Built.", "changed_files": ["module.py"]},
            "business_reviewer": {"summary": "Not ready.", "recommended_owner_decision": "send_back"},
        }

        ready, detail = execution_bridge._verify_owner_review_artifacts_ready(mission, artifacts)

        self.assertFalse(ready)
        self.assertEqual(detail["blocked_agent"], "business_reviewer")
        self.assertEqual(detail["stage_status"], "non_passing")

    def test_owner_review_artifact_gate_accepts_passing_artifacts(self):
        mission = {"mission_context_pack": {"agent_order": ["builder", "reviewer"]}}
        artifacts = {
            "builder": {"summary": "Built.", "changed_files": ["module.py"]},
            "reviewer": {
                "summary": "Approved.",
                "recommended_owner_decision": "approve_final_release",
                "quality_gate": {"passed": True},
            },
        }

        ready, detail = execution_bridge._verify_owner_review_artifacts_ready(mission, artifacts)

        self.assertTrue(ready)
        self.assertEqual(detail["reason"], "all_workflow_artifacts_passing")

    def test_ledger_stage_persists_duration_attempt_and_changed_file_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            paths = {
                "prompt_path": base / "prompt.md",
                "stdout_path": base / "stdout.txt",
                "stderr_path": base / "stderr.txt",
                "final_path": base / "final.md",
            }
            ledger = {"stages": []}
            execution_bridge._append_ledger_stage(
                ledger,
                "builder",
                "complete",
                "2026-07-14T08:00:00+00:00",
                paths,
                artifact={"changed_files": ["a.py", "b.py"]},
                attempt=2,
            )

        stage = ledger["stages"][0]
        self.assertEqual(stage["attempt"], 2)
        self.assertEqual(stage["changed_files_count"], 2)
        self.assertIn("completed_at", stage)
        self.assertGreaterEqual(stage["duration_seconds"], 0)
    def test_internal_recovery_caps_second_identical_fingerprint(self):
        artifact = {"errors": ["wrong revision"]}
        disposition = {
            "recoverable": True,
            "owner_required": False,
            "responsible_stage": "evidence_reviewer",
            "block_class": "stale_state_reconciliation_required",
        }
        fingerprint = execution_bridge._backflow_fingerprint(
            "business_reviewer", "evidence_reviewer", "reviewed wrong revision", artifact,
        )
        mission = {
            "metadata": {
                "mission_memory": {
                    "recurring_block_patterns": {
                        f"fingerprint:{fingerprint}": {"count": 1},
                    },
                },
            },
        }

        bounded, repeat = execution_bridge._bounded_internal_recovery(
            "MISSION-1", "business_reviewer", "reviewed wrong revision", artifact, disposition, mission=mission,
        )

        self.assertTrue(repeat["capped"])
        self.assertEqual(repeat["occurrence"], 2)
        self.assertFalse(bounded["recoverable"])
        self.assertTrue(bounded["owner_required"])
        self.assertEqual(bounded["block_class"], "recovery_attempts_exhausted")

    def test_internal_recovery_allows_first_occurrence(self):
        disposition = {"recoverable": True, "owner_required": False, "responsible_stage": "tester"}

        bounded, repeat = execution_bridge._bounded_internal_recovery(
            "MISSION-1", "tester", "temporary timeout", {}, disposition, mission={"metadata": {}},
        )

        self.assertFalse(repeat["capped"])
        self.assertEqual(repeat["occurrence"], 1)
        self.assertTrue(bounded["recoverable"])
    @patch("modules.charlie.execution_bridge._record_mission_memory_event")
    @patch("modules.charlie.execution_bridge.record_mission")
    def test_bounded_discovery_records_owner_gated_child_mission(self, record_mission, record_memory):
        record_mission.return_value = ({"stored": True, "status": "recorded", "mission_id": "CHARLIE-FOLLOWUP-1"}, 201)
        decision = {
            "followup_findings": [{
                "summary": "Malformed threshold hardening discovered after the parent correction budget.",
                "family": "input_validation",
                "severity": "high",
                "affected_paths": ["modules/beacon/opportunity_scanner.py"],
            }],
        }

        recorded = execution_bridge._record_discovered_followups(MISSION, "qa_red_team", decision)

        self.assertEqual(recorded[0]["mission_id"], "CHARLIE-FOLLOWUP-1")
        child = record_mission.call_args.args[0]
        self.assertEqual(child["status"], "new")
        self.assertEqual(child["metadata"]["mission_family"]["parent_mission_id"], MISSION["mission_id"])
        self.assertEqual(child["metadata"]["mission_family"]["finding_family"], "input_validation")
        record_memory.assert_called_once()

    def test_blocked_packet_resume_starts_from_blocked_agent(self):
        mission = {
            **MISSION,
            "metadata": {
                "review_packet": {
                    "review_status": "agent_blocked",
                    "blocked_agent": "tester",
                    "summary": "Blocked at tester.",
                },
            },
        }
        sequence = ["idea_expander", "source_mapper", "builder", "tester", "reviewer"]

        start_agent = execution_bridge._execution_start_agent(mission, sequence)

        self.assertEqual(start_agent, "tester")
        self.assertEqual(
            execution_bridge._parallel_read_only_prefix(execution_bridge._agent_queue_from(start_agent, sequence)),
            [],
        )

    def test_recovery_hint_cannot_skip_earlier_incomplete_durable_stage(self):
        mission = {
            **MISSION,
            "metadata": {"review_packet": {
                "return_to_stage": "builder",
                "review_status": "internal_recovery_queued",
                "blocked_reason": "final_artifact_stage_mismatch",
            }},
            "agent_workflow": [
                {"agent": "idea_expander", "status": "pending"},
                {"agent": "source_mapper", "status": "complete"},
                {"agent": "architect", "status": "pending"},
                {"agent": "builder", "status": "blocked"},
            ],
        }
        sequence = ["idea_expander", "source_mapper", "architect", "builder"]

        self.assertEqual(execution_bridge._execution_start_agent(mission, sequence), "idea_expander")

    def test_blocked_at_mission_stage_resume_starts_from_agent(self):
        mission = {
            **MISSION,
            "metadata": {"review_packet": {}},
            "vault": {"mission_stage": "blocked_at_builder"},
        }
        sequence = ["idea_expander", "source_mapper", "builder", "tester", "reviewer"]

        start_agent = execution_bridge._execution_start_agent(mission, sequence)

        self.assertEqual(start_agent, "builder")
        self.assertEqual(
            execution_bridge._parallel_read_only_prefix(execution_bridge._agent_queue_from(start_agent, sequence)),
            [],
        )

    def test_refreshed_workflow_uses_active_stage_when_stale_blocked_agent_was_removed(self):
        mission = {
            **MISSION,
            "metadata": {"review_packet": {"blocked_agent": "business_reviewer"}},
            "vault": {"mission_stage": "blocked_at_business_reviewer"},
            "agent_workflow": [
                {"agent": "source_mapper", "status": "complete"},
                {"agent": "technical_architect", "status": "active"},
                {"agent": "builder", "status": "pending"},
            ],
        }
        sequence = ["source_mapper", "technical_architect", "builder", "tester"]

        self.assertEqual(execution_bridge._execution_start_agent(mission, sequence), "technical_architect")

    def test_rerun_recovers_upstream_artifacts_from_mission_memory(self):
        # Stage 1 fix B (evidence threading): when the review packet has lost the
        # upstream agent artifacts across a runner session, a resumed downstream
        # agent must still receive builder/tester evidence from durable mission
        # memory instead of an empty previous_agent_artifacts (the exact overnight
        # stall: qa_red_team blocked because "previous_agent_artifacts is empty").
        sequence = ["idea_expander", "source_mapper", "builder", "tester", "qa_red_team", "reviewer"]
        mission = {
            **MISSION,
            "metadata": {
                "review_packet": {"agent_artifacts": {}},
                "mission_memory": {
                    "version": "charlie_mission_memory_v1",
                    "latest_by_agent": {
                        "builder": {
                            "agent": "builder",
                            "type": "agent_complete",
                            "summary": "Implemented pre-wean tagless exclusion.",
                            "changed_files": ["modules/pig_weights/pig_weights_service.py"],
                            "commands_run": ["python -m unittest tests.test_pig_allocation_readiness_service"],
                            "tests_run": ["Ran 190 tests OK"],
                            "files_inspected": ["modules/pig_weights/pig_weights_service.py"],
                            "confidence": "0.97",
                        },
                        "tester": {
                            "agent": "tester",
                            "type": "agent_complete",
                            "summary": "Focused suite passed.",
                            "tests_run": ["Ran 190 tests OK"],
                            "files_inspected": ["tests/test_pig_allocation_readiness_service.py"],
                        },
                    },
                },
            },
        }

        recovered = execution_bridge._existing_agent_artifacts_for_rerun(mission, "qa_red_team", sequence)

        self.assertIn("builder", recovered)
        self.assertIn("tester", recovered)
        self.assertEqual(
            recovered["builder"]["changed_files"],
            ["modules/pig_weights/pig_weights_service.py"],
        )
        self.assertEqual(recovered["builder"]["recovered_from"], "mission_memory_latest_by_agent")
        self.assertTrue(recovered["tester"]["test_evidence"])
        # Never recover the current/downstream stage's own artifact.
        self.assertNotIn("qa_red_team", recovered)
        self.assertNotIn("reviewer", recovered)

    def test_durable_backflow_count_persists_across_sessions(self):
        # Stage 1 fix A (durable loop cap): the per-run ledger resets every runner
        # session, so a repeated blocker used to loop forever overnight. The count
        # must survive across sessions via mission memory so the hard-loop cap can
        # convert an infinite retry into an honest owner block.
        mission = {
            **MISSION,
            "metadata": {
                "mission_memory": {
                    "version": "charlie_mission_memory_v1",
                    "events": [
                        {"type": "agent_backflow", "metadata": {"backflow_fingerprint": "abc123"}},
                        {"type": "agent_complete", "metadata": {"backflow_fingerprint": "abc123"}},
                        {"type": "agent_backflow", "metadata": {"backflow_fingerprint": "abc123"}},
                        {"type": "agent_backflow", "metadata": {"backflow_fingerprint": "different"}},
                    ],
                },
            },
        }

        self.assertEqual(execution_bridge._durable_backflow_fingerprint_count(mission, "abc123"), 2)
        self.assertEqual(execution_bridge._durable_backflow_fingerprint_count(mission, "different"), 1)
        self.assertEqual(execution_bridge._durable_backflow_fingerprint_count(mission, "missing"), 0)
        self.assertEqual(execution_bridge._durable_backflow_fingerprint_count({}, "abc123"), 0)

    def test_builder_revision_sha_prefers_current_artifact_and_falls_back_to_memory(self):
        mission = {
            "metadata": {
                "mission_memory": {
                    "latest_by_agent": {"builder": {"commit_sha": "memory-sha"}},
                }
            }
        }

        self.assertEqual(
            execution_bridge._builder_revision_sha(mission, {"builder": {"commit_sha": "artifact-sha"}}),
            "artifact-sha",
        )
        self.assertEqual(execution_bridge._builder_revision_sha(mission, {}), "memory-sha")

    def test_builder_revision_sha_reads_candidate_bound_lineage_before_legacy_memory(self):
        mission = {
            "metadata": {
                "mission_memory": {
                    "latest_by_agent": {"builder": {"commit_sha": "old-candidate-sha"}},
                }
            }
        }
        artifacts = {
            "builder": {
                "source_commit": "current-candidate-sha",
                "evidence_lineage": {"source_commit": "current-candidate-sha"},
            }
        }

        self.assertEqual(
            execution_bridge._builder_revision_sha(mission, artifacts),
            "current-candidate-sha",
        )

    def test_release_candidate_revision_prefers_exact_release_review_over_stale_builder(self):
        artifacts = {
            "builder": {"source_commit": "old-builder-sha"},
            "tester": {"tested_revision": "old-builder-sha", "expected_revision": "old-builder-sha"},
            "reviewer": {"tested_revision": "current-pr-head", "expected_revision": "current-pr-head"},
        }

        self.assertEqual(
            execution_bridge._release_candidate_revision_sha({}, artifacts),
            "current-pr-head",
        )

    def test_release_candidate_revision_rejects_mismatched_release_review(self):
        artifacts = {
            "builder": {"source_commit": "builder-sha"},
            "reviewer": {"tested_revision": "other-sha", "expected_revision": "current-pr-head"},
        }

        self.assertEqual(
            execution_bridge._release_candidate_revision_sha({}, artifacts),
            "builder-sha",
        )

    def test_publisher_revision_is_bound_to_checkout_after_rebase(self):
        revision = "24c59127cb3ec8712f978acadfa814fd387dd823"
        artifact = execution_bridge._bind_publisher_revision(
            {"summary": "Publisher rebased and verified the PR."},
            revision=revision,
        )

        self.assertEqual(artifact["expected_revision"], revision)
        self.assertEqual(artifact["tested_revision"], revision)
        self.assertEqual(artifact["commit_sha"], revision)
        self.assertEqual(
            execution_bridge._release_candidate_revision_sha(
                {}, {"builder": {"source_commit": "old"}, "publisher": artifact}
            ),
            revision,
        )

    def test_publisher_contract_requires_candidate_revision_fields(self):
        schema = execution_bridge._agent_required_schema("publisher")
        self.assertIn("expected_revision", schema)
        self.assertIn("tested_revision", schema)
        self.assertIn("commit_sha", schema)

    def test_owner_review_gate_failure_counts_only_identical_candidate_failure(self):
        status = {
            "evidence_reconciliation": {
                "candidate_manifest": {"source_commit": "current-pr-head", "scope_hash": "scope-1"},
                "requires_revalidation": [{"agent": "idea_expander", "reason": "legacy evidence"}],
            }
        }
        first = execution_bridge._owner_review_gate_failure({}, "idea_expander", "refresh", status)
        mission = {"metadata": {"review_packet": {"owner_review_gate_failure": first}}}
        second = execution_bridge._owner_review_gate_failure(mission, "idea_expander", "refresh", status)
        changed = execution_bridge._owner_review_gate_failure(mission, "source_mapper", "refresh", status)

        self.assertEqual(first["occurrence"], 1)
        self.assertEqual(second["occurrence"], 2)
        self.assertEqual(changed["occurrence"], 2)

    def test_compacted_security_migration_advisory_remains_non_blocking(self):
        artifact = {
            "agent": "security_reviewer",
            "summary": "Security review passed; migration remains unapplied.",
            "errors": [],
            "bugs": [],
            "recommended_owner_decision": "approve_final_release",
            "changed_files": ["supabase/migrations/202607200001_create_pig_observation_events.sql"],
            "next_action": "Owner may approve merge of PR #320, but must not approve migration application.",
            "acceptance_results": [{"id": "scope", "status": "passed"}],
            "quality_gate": {"passed": True},
        }
        compact = execution_bridge._compact_agent_artifacts_for_review({"security_reviewer": artifact})["security_reviewer"]
        self.assertEqual(compact["acceptance_results"], artifact["acceptance_results"])
        result = execution_bridge._judgement_evidence_quality_gate("security_reviewer", compact)
        self.assertTrue(result["passed"], result)

    def test_owner_review_gate_targets_first_stale_stage_after_pr_head_rewrite(self):
        current = "3051aebe157cd344b0e01a11dc68af0bdf6cd8"
        old = "101032db690f001891c80a6b109be5dbd6fa659a"
        sequence = ["idea_expander", "source_mapper", "builder", "tester", "reviewer"]
        mission = {"mission_id": "CHARLIE-SCOPE-1C564A1B7E1C7681", "mission_context_pack": {"agent_order": sequence}}
        artifacts = {
            "idea_expander": {"agent": "idea_expander", "quality_gate": {"passed": True}},
            "source_mapper": {"agent": "source_mapper", "quality_gate": {"passed": True}},
            "builder": {"agent": "builder", "source_commit": old, "evidence_lineage": {"source_commit": old}, "quality_gate": {"passed": True}},
            "tester": {"agent": "tester", "tested_revision": old, "expected_revision": old, "quality_gate": {"passed": True}},
            "reviewer": {"agent": "reviewer", "tested_revision": current, "expected_revision": current, "quality_gate": {"passed": True}},
        }

        ready, detail = execution_bridge._verify_owner_review_artifacts_ready(mission, artifacts)

        self.assertFalse(ready)
        self.assertEqual(detail["blocked_agent"], "idea_expander")
        self.assertEqual(detail["evidence_reconciliation"]["candidate_manifest"]["source_commit"], current)

    def test_reviewer_adjacent_migration_follow_ups_do_not_trigger_builder_backflow(self):
        artifact = {
            "recommended_owner_decision": "approve_final_release",
            "acceptance_results": [
                {"id": "scope", "status": "passed"},
                {"id": "authority-boundary", "status": "passed"},
            ],
            "finding_contract": (
                "Advisory follow-up: scope_relation=adjacent_follow_up; "
                "introduced_by_current_diff=false; severity=medium; acceptance impact=none."
            ),
        }
        values = [
            "Before migration application, rehearse RLS and trigger behavior in non-production PostgreSQL.",
            "Capture roles, correction authorization, and retention/deletion policy remain owner decisions. Do not build capture or apply this migration until resolved.",
        ]

        self.assertEqual(execution_bridge._blocking_artifact_items("reviewer", artifact, values), [])

    def test_reviewer_current_diff_defect_still_blocks_with_advisory_contract(self):
        artifact = {
            "recommended_owner_decision": "approve_final_release",
            "acceptance_results": [{"id": "scope", "status": "passed"}],
            "finding_contract": (
                "scope_relation=adjacent_follow_up; introduced_by_current_diff=false; acceptance impact=none"
            ),
        }
        values = [
            "Before migration application, use a non-production rehearsal.",
            "Current-diff defect: cross-pig correction validation is missing and must fix before merge.",
        ]

        self.assertEqual(
            execution_bridge._blocking_artifact_items("reviewer", artifact, values),
            [values[1]],
        )

    def test_security_merge_approval_is_not_blocked_by_separate_migration_application_gate(self):
        artifact = {
            "summary": "Security review passed. The migration remains unapplied.",
            "errors": [],
            "bugs": [],
            "recommended_owner_decision": "approve_final_release",
            "acceptance_results": [
                {"id": "scope", "status": "passed"},
                {"id": "authority-boundary", "status": "passed"},
            ],
            "changed_files": ["supabase/migrations/202607200001_create_pig_observation_events.sql"],
            "release_notes": ["The migration is unapplied."],
            "next_action": (
                "Hand off to evidence review. Owner may approve merge of PR #320, but must not approve "
                "migration application until owner decisions and a non-production rehearsal are complete."
            ),
        }

        result = execution_bridge._judgement_evidence_quality_gate("security_reviewer", artifact)

        self.assertTrue(result["passed"], result)

    def test_separate_migration_gate_never_hides_current_security_defect(self):
        artifact = {
            "summary": "The migration remains unapplied.",
            "errors": [],
            "bugs": [],
            "recommended_owner_decision": "approve_final_release",
            "acceptance_results": [{"id": "scope", "status": "passed"}],
            "changed_files": ["supabase/migrations/202607200001_create_pig_observation_events.sql"],
            "next_action": (
                "Owner may approve merge of PR #320, but must not approve migration application. "
                "Current-diff security defect: an unsafe grant is present and must fix before merge."
            ),
        }

        result = execution_bridge._judgement_evidence_quality_gate("security_reviewer", artifact)

        self.assertFalse(result["passed"])

    def test_owner_review_gate_does_not_send_current_lineage_back_to_builder(self):
        current_revision = "8456b69730a6a3f1d2e4ed0b73a23ae180d73ba5"
        mission = {
            "mission_id": "MISSION-MIXED-HISTORY",
            "mission_context_pack": {"agent_order": ["builder", "tester"]},
            "metadata": {
                "mission_memory": {
                    "latest_by_agent": {"builder": {"commit_sha": "stale-revision"}},
                }
            },
        }
        artifacts = {
            agent: {
                "agent": agent,
                "source_commit": current_revision,
                "evidence_lineage": {
                    "agent": agent,
                    "source_commit": current_revision,
                },
                "quality_gate": {"passed": True},
            }
            for agent in ("builder", "tester")
        }

        ready, detail = execution_bridge._verify_owner_review_artifacts_ready(mission, artifacts)

        self.assertTrue(ready, detail)
        self.assertEqual(
            detail["evidence_reconciliation"]["candidate_manifest"]["source_commit"],
            current_revision,
        )

    def test_rerun_recovers_done_lock_when_latest_agent_event_is_backflow(self):
        sequence = ["builder", "tester", "qa_red_team", "reviewer"]
        mission = {
            **MISSION,
            "metadata": {
                "review_packet": {"agent_artifacts": {}},
                "mission_memory": {
                    "version": "charlie_mission_memory_v1",
                    "latest_by_agent": {
                        "tester": {
                            "agent": "tester",
                            "type": "agent_backflow",
                            "summary": "Reviewer asked for one more check.",
                        },
                    },
                    "done_locks": {
                        "tester": {
                            "agent": "tester",
                            "type": "agent_complete",
                            "summary": "Focused tests passed before send-back.",
                            "tests_run": ["python -m unittest tests.test_charlie_execution_bridge OK"],
                            "files_inspected": ["tests/test_charlie_execution_bridge.py"],
                            "confidence": "0.90",
                            "done_lock_version": "charlie_done_lock_v1",
                        },
                    },
                },
            },
        }

        recovered = execution_bridge._existing_agent_artifacts_for_rerun(mission, "qa_red_team", sequence)

        self.assertEqual(recovered["tester"]["summary"], "Focused tests passed before send-back.")
        self.assertTrue(recovered["tester"]["done_lock"])
        self.assertEqual(recovered["tester"]["recovered_from"], "mission_memory_done_locks")

    def test_objective_evidence_gate_allows_low_confidence_pass_with_concrete_evidence(self):
        artifact = _successful_stage_payload("qa_red_team")
        artifact.update({
            "confidence": "88%",
            "files_inspected": ["modules/charlie/execution_bridge.py"],
            "tests_run": ["python -m unittest tests.test_charlie_execution_bridge OK"],
            "red_team_status": "pass",
            "risk_rating": "low",
        })

        gate = execution_bridge._artifact_confidence_quality_gate("qa_red_team", artifact)

        self.assertTrue(gate["passed"])
        self.assertTrue(gate["objective_gate"])
        self.assertIn("objective evidence gate", gate["reason"])

    def test_objective_evidence_gate_still_blocks_high_risk_or_failed_tests(self):
        artifact = _successful_stage_payload("qa_red_team")
        artifact.update({
            "confidence": "88%",
            "files_inspected": ["modules/charlie/execution_bridge.py"],
            "tests_run": ["tests failed with traceback"],
            "red_team_status": "pass",
            "risk_rating": "low",
        })
        failed_test_gate = execution_bridge._artifact_confidence_quality_gate("qa_red_team", artifact)

        artifact["tests_run"] = ["python -m unittest tests.test_charlie_execution_bridge OK"]
        artifact["risk_rating"] = "high"
        high_risk_gate = execution_bridge._artifact_confidence_quality_gate("qa_red_team", artifact)

        self.assertFalse(failed_test_gate["passed"])
        self.assertFalse(high_risk_gate["passed"])
        self.assertEqual(high_risk_gate["reason"], "qa_red_team confidence 88% is below the required 96%; clarify or inspect more evidence.")

    def test_review_agent_structured_pass_allows_out_of_scope_release_note(self):
        artifact = _successful_stage_payload("business_reviewer")
        artifact.update({
            "recommended_owner_decision": "approve_final_release",
            "release_notes": [
                "Auto-reply, payment confirmation, reservations, stock changes, and farm lifecycle writes remain out of scope for this gate.",
            ],
            "stdout_tail": "\"quality_gate\": {\"passed\": true} - writes remain out of scope for this gate.",
            "stderr_tail": "\"quality_gate\": {\"passed\": true} - writes remain out of scope for this gate.",
            "quality_gate": {
                "passed": True,
                "reason": "Business reviewer gate passed.",
            },
        })

        quality = execution_bridge._agent_quality_gate("business_reviewer", artifact)

        self.assertTrue(quality["passed"], quality)

    def test_builder_artifact_accepts_empty_changed_files_for_verification_mission(self):
        artifact = _successful_stage_payload("builder")
        artifact["changed_files"] = []
        artifact["pr_url"] = ""
        artifact["links"] = {"pr": ""}

        validation = execution_bridge._validate_agent_artifact("builder", artifact)
        quality = execution_bridge._agent_quality_gate("builder", artifact)

        self.assertTrue(validation["valid"], validation)
        self.assertTrue(quality["passed"], quality)

    def test_agent_artifact_requires_confidence_fields(self):
        artifact = _successful_stage_payload("planner")
        artifact.pop("confidence")

        validation = execution_bridge._validate_agent_artifact("planner", artifact)

        self.assertFalse(validation["valid"])
        self.assertIn("confidence", validation["missing_keys"])

    def test_source_mapper_allows_empty_legacy_sources_for_current_only_section(self):
        artifact = _successful_stage_payload("source_mapper")
        artifact["legacy_sources"] = []

        validation = execution_bridge._validate_agent_artifact("source_mapper", artifact)

        self.assertTrue(validation["valid"], validation)

    def test_visual_reference_interpreter_allows_empty_media_when_no_reference_attached(self):
        artifact = _successful_stage_payload("visual_reference_interpreter")
        artifact["media_references_used"] = []
        artifact["layout_requirements"] = ["Show new missions as first-class owner review cards."]
        artifact["visual_hierarchy"] = ["Approval context before technical debug detail."]
        artifact["reference_match_checklist"] = ["No attached screenshot; use owner text and Vault UI standard."]

        validation = execution_bridge._validate_agent_artifact("visual_reference_interpreter", artifact)

        self.assertTrue(validation["valid"], validation)

    def test_agent_quality_gate_blocks_below_ninety_six_confidence(self):
        artifact = _successful_stage_payload("planner")
        artifact["confidence"] = "95%"
        artifact["confidence_reason"] = "Based on Vault Brain docs and inspected repo files."

        quality = execution_bridge._agent_quality_gate("planner", artifact)

        self.assertFalse(quality["passed"])
        self.assertIn("below the required 96", quality["reason"])

    def test_ui_quality_gate_accepts_structured_ui_council_evidence(self):
        contract = {
            "ui_related": True,
            "reference_media_required": True,
        }
        interpreter_artifact = {
            "ui_quality_contract": contract,
            "media_references_used": ["screenshots/reference.png"],
            "layout_requirements": ["left mission rail, central agent flow, right mission summary"],
            "reference_match_checklist": ["preserve three-zone command-center layout"],
        }
        designer_artifact = {
            "ui_quality_contract": contract,
            "media_references_used": ["screenshots/reference.png"],
            "ui_concept": "Operational command center",
            "layout_system": ["left rail", "center workflow", "right summary"],
            "what_not_to_do": ["Do not only change colors."],
        }
        visual_reviewer_artifact = {
            "ui_quality_contract": contract,
            "media_references_used": ["screenshots/reference.png"],
            "visual_acceptance_decision": "approve",
            "visual_review_notes": ["Matches the reference structure on desktop and mobile."],
            "reference_match_assessment": "Reference layout and owner actions are preserved.",
        }

        self.assertTrue(execution_bridge._ui_agent_quality_gate("visual_reference_interpreter", interpreter_artifact)["passed"])
        self.assertTrue(execution_bridge._ui_agent_quality_gate("creative_ui_designer", designer_artifact)["passed"])
        self.assertTrue(execution_bridge._ui_agent_quality_gate("visual_qa_reviewer", visual_reviewer_artifact)["passed"])

    def test_ui_design_agent_schemas_include_reference_media_field(self):
        for agent in ["creative_ui_designer", "ux_interaction_designer"]:
            schema = execution_bridge._agent_required_schema(agent)
            required = execution_bridge._validate_agent_artifact(agent, {
                **{key: "value" for key in schema},
                "errors": [],
                "bugs": [],
                "vault_sources_used": ["docs/09-vault-brain/INDEX.md"],
                "vault_updates": [],
                "files_inspected": ["static/js/charlieMissionControl.js"],
                "commands_run": ["rg charlie static/js/charlieMissionControl.js"],
                "media_references_used": ["screenshots/reference.png"],
                "confidence": "97%",
                "confidence_reason": "Based on Vault Brain source docs, repo file inspection, and screenshot evidence.",
            })

            self.assertIn("media_references_used", schema)
            self.assertTrue(required["valid"], required)

    def test_technical_architect_schema_requires_implementation_sources(self):
        schema = execution_bridge._agent_required_schema("technical_architect")
        artifact = _successful_stage_payload("technical_architect")
        artifact.update({
            "files_to_inspect": ["static/js/charlieMissionControl.js"],
            "risk_notes": ["review evidence must be proven"],
            "implementation_plan": ["preserve owner review controls"],
            "implementation_sources_used": ["static/js/charlieMissionControl.js"],
        })

        validation = execution_bridge._validate_agent_artifact("technical_architect", artifact)

        self.assertIn("implementation_sources_used", schema)
        self.assertTrue(validation["valid"], validation)

    @patch("modules.charlie.execution_bridge.shutil.which")
    @patch("modules.charlie.execution_bridge.os.name", "nt")
    def test_codex_executable_prefers_windows_cmd_shim(self, which):
        def fake_which(name):
            return "C:/Users/charl/AppData/Roaming/npm/codex.cmd" if name == "codex.cmd" else None

        which.side_effect = fake_which

        self.assertEqual(
            execution_bridge._codex_executable(),
            "C:/Users/charl/AppData/Roaming/npm/codex.cmd",
        )

    @patch("modules.charlie.execution_bridge.get_mission")
    def test_prepare_codex_execution_writes_prompt_without_running_codex(self, get_mission):
        get_mission.return_value = ({"success": True, "status": "ok", "mission": MISSION}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.prepare_codex_execution(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
            )
            prompt = Path(result["prompt_path"]).read_text(encoding="utf-8")

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "execution_prepared")
        self.assertFalse(result["will_execute_codex"])
        self.assertIn("Build execution bridge", prompt)
        self.assertIn("No web-triggered shell execution.", prompt)
        self.assertIn("CHARLIE Vault Brain context", prompt)
        self.assertIn("docs/09-vault-brain/INDEX.md", prompt)
        self.assertIn("Stop at owner review", prompt)

    @patch("modules.charlie.execution_bridge.get_mission")
    def test_run_codex_execution_bridge_defaults_to_dry_run(self, get_mission):
        get_mission.return_value = ({"success": True, "status": "ok", "mission": MISSION}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_codex_execution_bridge(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "execution_dry_run")
        self.assertIn("prompt_path", result)

    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_agent_runner_v2_defaults_to_dry_run(self, get_mission, update_vault):
        get_mission.return_value = ({"success": True, "status": "ok", "mission": MISSION}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "agent_execution_dry_run")
        self.assertEqual(result["agent_runner_version"], "charlie_agent_runner_v2")
        self.assertIn("ledger_path", result)
        governance_write = update_vault.call_args.args[1]["mission_governance"]
        self.assertTrue(governance_write["matrix_frozen"])
        self.assertEqual(governance_write["matrix_source"], "mission_vault")

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/execution_bridge.py"])
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_agent_runner_v2_records_stage_artifacts_and_review_packet(
        self,
        get_mission,
        update_status,
        update_vault,
        update_workflow,
        write_heartbeat,
        _changed_files,
    ):
        get_mission.side_effect = _mission_readback_sequence(
            MISSION,
            _mission_with_persisted_review_packet(),
        )
        update_status.return_value = ({"success": True, "status": "ok", "mission_status": "pr_ready"}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        def fake_runner(*_args, **kwargs):
            prompt = kwargs["input"]
            agent = _agent_from_prompt(prompt)
            payload = _successful_stage_payload(agent)
            return SimpleNamespace(returncode=0, stdout=f"```json\n{json.dumps(payload)}\n```", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=fake_runner,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "agent_execution_completed")
        self.assertEqual(result["mission_status"], "pr_ready")
        self.assertEqual(result["agent_runner_version"], "charlie_agent_runner_v2")
        self.assertGreaterEqual(update_workflow.call_count, 10)
        packet = self.finalize_owner_review.call_args.args[1]
        self.assertIn("agent_artifacts", packet)
        self.assertIn("handoff_reports", packet)
        self.assertTrue(packet["brain_guard"]["passed"])
        self.assertIn("qa_red_team", packet["agent_artifacts"])
        self.assertNotIn("stdout_tail", packet["agent_artifacts"]["qa_red_team"])
        self.assertNotIn("stderr_tail", packet["agent_artifacts"]["qa_red_team"])
        self.assertIn("QA/red-team passed", packet["qa_evidence"])
        self.assertIn("quality_gates", packet)
        self.assertEqual(packet["links"]["pr"], "https://github.com/org/repo/pull/61")
        self.assertEqual(packet["pr_url"], "https://github.com/org/repo/pull/61")
        self.assertEqual(packet["review_status"], "ready_for_owner_review")
        self.assertEqual(packet["tested_revision"], self.finalize_owner_review.call_args.kwargs["candidate_revision"])
        self.assertFalse(any(call.args[1] == "pr_ready" for call in update_status.call_args_list))
        self.assertTrue(any(call.args[0].get("current_agent") == "planner" for call in write_heartbeat.call_args_list))
        self.assertTrue(any(call.args[0].get("status") == "parallel_read_only_agents_running" for call in write_heartbeat.call_args_list))
        self.assertIn("parallel_planning_execution", packet["agent_execution"])

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/execution_bridge.py"])
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge._run_agent_model_process")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_agent_runner_v2_default_runner_uses_provider_aware_process(
        self,
        get_mission,
        run_agent_model_process,
        update_status,
        update_vault,
        update_workflow,
        _write_heartbeat,
        _changed_files,
    ):
        get_mission.side_effect = _mission_readback_sequence(
            MISSION,
            _mission_with_persisted_review_packet(),
        )
        update_status.return_value = ({"success": True, "status": "ok", "mission_status": "pr_ready"}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        def fake_provider_process(*_args, **kwargs):
            agent = _agent_from_prompt(kwargs["input"])
            payload = _successful_stage_payload(agent)
            return SimpleNamespace(returncode=0, stdout=f"```json\n{json.dumps(payload)}\n```", stderr="")

        run_agent_model_process.side_effect = fake_provider_process

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "agent_execution_completed")
        self.assertTrue(run_agent_model_process.called)
        self.assertGreaterEqual(run_agent_model_process.call_count, 5)

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/execution_bridge.py"])
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_malformed_json_final_triggers_one_contract_retry_then_passes(
        self,
        get_mission,
        update_status,
        update_vault,
        update_workflow,
        _write_heartbeat,
        _changed_files,
    ):
        mission = {
            **MISSION,
            "mission_context_pack": {"agent_order": ["business_reviewer", "reviewer"]},
            "metadata": {"review_packet": {"blocked_agent": "business_reviewer"}},
        }
        get_mission.side_effect = _mission_readback_sequence(
            mission,
            _mission_with_persisted_review_packet(mission),
        )
        update_status.return_value = ({"success": True, "status": "ok", "mission_status": "pr_ready"}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        business_calls = {"count": 0}

        def fake_runner(*_args, **kwargs):
            agent = _agent_from_prompt(kwargs["input"])
            payload = _successful_stage_payload(agent)
            if agent == "business_reviewer":
                business_calls["count"] += 1
                if business_calls["count"] == 1:
                    return SimpleNamespace(returncode=0, stdout="```json\n{\"summary\": \"truncated\"", stderr="")
            return SimpleNamespace(returncode=0, stdout=f"```json\n{json.dumps(payload)}\n```", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=fake_runner,
            )
            ledger = json.loads(Path(result["agent_ledger_path"]).read_text(encoding="utf-8"))
            failed_artifact_exists = Path(ledger["contract_retries"][0]["failed_artifact_path"]).exists()

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "agent_execution_completed")
        self.assertEqual(business_calls["count"], 2)
        self.assertEqual(ledger["contract_retries"][0]["reason"], "malformed_json")
        self.assertTrue(failed_artifact_exists)
        self.assertTrue(any(stage["agent"] == "business_reviewer" and stage["attempt"] == 2 for stage in ledger["stages"]))

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/execution_bridge.py"])
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_missing_required_keys_triggers_contract_retry_then_passes(
        self,
        get_mission,
        update_status,
        update_vault,
        update_workflow,
        _write_heartbeat,
        _changed_files,
    ):
        mission = {
            **MISSION,
            "mission_context_pack": {"agent_order": ["business_reviewer", "reviewer"]},
            "metadata": {"review_packet": {"blocked_agent": "business_reviewer"}},
        }
        get_mission.side_effect = _mission_readback_sequence(
            mission,
            _mission_with_persisted_review_packet(mission),
        )
        update_status.return_value = ({"success": True, "status": "ok", "mission_status": "pr_ready"}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        business_calls = {"count": 0}

        def fake_runner(*_args, **kwargs):
            agent = _agent_from_prompt(kwargs["input"])
            payload = _successful_stage_payload(agent)
            if agent == "business_reviewer":
                business_calls["count"] += 1
                if business_calls["count"] == 1:
                    payload.pop("vault_sources_used")
                    payload.pop("confidence")
                    payload.pop("confidence_reason")
            return SimpleNamespace(returncode=0, stdout=f"```json\n{json.dumps(payload)}\n```", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=fake_runner,
            )
            ledger = json.loads(Path(result["agent_ledger_path"]).read_text(encoding="utf-8"))

        self.assertEqual(status_code, 200)
        self.assertEqual(business_calls["count"], 2)
        self.assertEqual(ledger["contract_retries"][0]["reason"], "missing_keys")
        self.assertEqual(
            set(ledger["contract_retries"][0]["missing_keys"]),
            {"vault_sources_used", "confidence", "confidence_reason"},
        )

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/execution_bridge.py"])
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_contract_retry_failure_blocks_with_contract_reason_and_paths(
        self,
        get_mission,
        update_status,
        update_vault,
        update_workflow,
        _write_heartbeat,
        _changed_files,
    ):
        mission = {
            **MISSION,
            "mission_context_pack": {"agent_order": ["business_reviewer", "reviewer"]},
            "metadata": {"review_packet": {"blocked_agent": "business_reviewer"}},
        }
        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)
        update_status.return_value = ({"success": True, "status": "ok", "mission_status": "blocked"}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        def fake_runner(*_args, **_kwargs):
            return SimpleNamespace(returncode=0, stdout="```json\n{\"summary\": \"still truncated\"", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=fake_runner,
            )
            ledger = json.loads(Path(result["agent_ledger_path"]).read_text(encoding="utf-8"))

        self.assertEqual(status_code, 202)
        self.assertEqual(result["status"], "agent_stage_recovery_queued")
        self.assertEqual(result["mission_status"], "approved")
        self.assertEqual(result["block_disposition"]["block_class"], "evidence_repair_required")
        self.assertIn("after contract retry", result["blocked_reason"])
        self.assertEqual(len(ledger["contract_retries"]), 1)
        vault_metadata = update_vault.call_args.args[1]
        blocked_artifact = vault_metadata["review_packet"]["agent_artifacts"]["business_reviewer"]
        self.assertTrue(blocked_artifact["first_attempt_artifact_path"])
        self.assertTrue(blocked_artifact["contract_retry_exhausted"])

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/execution_bridge.py"])
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_contract_retry_prompt_and_no_backflow_or_prefix_replay(
        self,
        get_mission,
        update_status,
        update_vault,
        update_workflow,
        _write_heartbeat,
        _changed_files,
    ):
        mission = {
            **MISSION,
            "mission_context_pack": {"agent_order": ["idea_expander", "source_mapper", "business_reviewer", "reviewer"]},
            "metadata": {"review_packet": {"blocked_agent": "business_reviewer"}},
        }
        get_mission.side_effect = _mission_readback_sequence(
            mission,
            _mission_with_persisted_review_packet(mission),
        )
        update_status.return_value = ({"success": True, "status": "ok", "mission_status": "pr_ready"}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        prompts = []
        called_agents = []

        def fake_runner(*_args, **kwargs):
            prompt = kwargs["input"]
            prompts.append(prompt)
            agent = _agent_from_prompt(prompt)
            called_agents.append(agent)
            payload = _successful_stage_payload(agent)
            if agent == "business_reviewer" and called_agents.count("business_reviewer") == 1:
                payload.pop("confidence")
            return SimpleNamespace(returncode=0, stdout=f"```json\n{json.dumps(payload)}\n```", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=fake_runner,
            )
            ledger = json.loads(Path(result["agent_ledger_path"]).read_text(encoding="utf-8"))

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "agent_execution_completed")
        self.assertEqual(called_agents, ["business_reviewer", "business_reviewer", "reviewer"])
        self.assertNotIn("CHARLIE CONTRACT REMINDER", prompts[0])
        self.assertIn("CHARLIE CONTRACT REMINDER", prompts[1])
        self.assertIn("Put the required keys first", prompts[1])
        self.assertIn("summary, errors, bugs, vault_sources_used, confidence, confidence_reason", prompts[1])
        self.assertIn("summary under 90 words", prompts[1])
        self.assertEqual(ledger.get("backflow_events"), [])

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/execution_bridge.py"])
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_zero_exit_missing_final_retries_but_nonzero_exit_blocks(
        self,
        get_mission,
        update_status,
        update_vault,
        update_workflow,
        _write_heartbeat,
        _changed_files,
    ):
        mission = {
            **MISSION,
            "mission_context_pack": {"agent_order": ["business_reviewer"]},
            "metadata": {"review_packet": {"blocked_agent": "business_reviewer"}},
        }
        get_mission.side_effect = _mission_readback_sequence(
            mission,
            _mission_with_persisted_review_packet(mission),
        )
        update_status.return_value = ({"success": True, "status": "ok", "mission_status": "pr_ready"}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        calls = {"count": 0}

        def missing_then_valid(*_args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            payload = _successful_stage_payload(_agent_from_prompt(kwargs["input"]))
            return SimpleNamespace(returncode=0, stdout=f"```json\n{json.dumps(payload)}\n```", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=missing_then_valid,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(calls["count"], 2)

        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)
        get_mission.side_effect = None
        update_status.return_value = ({"success": True, "status": "ok", "mission_status": "blocked"}, 200)
        calls["count"] = 0

        def nonzero_runner(*_args, **_kwargs):
            calls["count"] += 1
            return SimpleNamespace(returncode=124, stdout="", stderr="timed out")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=nonzero_runner,
            )

        self.assertEqual(status_code, 202)
        self.assertEqual(calls["count"], 1)

    def test_review_agent_parse_fallback_never_recommends_approval(self):
        artifact = execution_bridge._agent_artifact_from_final("business_reviewer", "```json\n{\"summary\": \"truncated\"")

        self.assertTrue(artifact["contract_parse_fallback"])
        self.assertEqual(artifact["recommended_owner_decision"], "send_back")

    def test_revision_gate_rejects_review_of_wrong_pr_head(self):
        artifact = _successful_stage_payload("tester")
        artifact["expected_revision"] = "abc123"
        artifact["tested_revision"] = "def456"

        result = execution_bridge._revision_evidence_quality_gate("tester", artifact)

        self.assertFalse(result["passed"])
        self.assertIn("wrong revision", result["reason"])

    def test_revision_gate_accepts_full_sha_for_short_builder_sha(self):
        result = execution_bridge._revision_evidence_quality_gate("reviewer", {
            "expected_revision": "abc1234",
            "tested_revision": "abc1234ffffeeee",
        })

        self.assertTrue(result["passed"])

    def test_revision_gate_ignores_placeholder_revision_text(self):
        result = execution_bridge._revision_evidence_quality_gate("reviewer", {
            "expected_revision": "mission-specific packaged pr head not supplied",
            "tested_revision": "main",
        })

        self.assertTrue(result["passed"])
        self.assertEqual(result["reason"], "no_packaged_revision_yet")

    def test_council_synthesis_parsed_artifact_gets_contract_defaults(self):
        final = """Council-approved build brief:
        Keep the Pig Allocation change frontend-only.

        ```json
        {
          "summary": "Council aligned on compact Pig Allocation table.",
          "errors": [],
          "bugs": [],
          "vault_sources_used": ["docs/09-vault-brain/INDEX.md"],
          "files_inspected": ["static/js/pigAllocation.js"],
          "commands_run": ["node --check static/js/pigAllocation.js"],
          "confidence": 0.96,
          "confidence_reason": "Based on upstream agent artifacts.",
          "next_action": "Planner should hand the scoped table cleanup to Builder."
        }
        ```
        """

        artifact = execution_bridge._agent_artifact_from_final("council_synthesis", final)
        validation = execution_bridge._validate_agent_artifact("council_synthesis", artifact)

        self.assertTrue(validation["valid"], validation)
        self.assertIn("Council aligned", artifact["build_brief"])
        self.assertEqual(artifact["agreements"], ["Council aligned on compact Pig Allocation table."])
        self.assertEqual(artifact["conflicts_resolved"], ["No council conflicts were recorded in the parsed artifact."])

    def test_council_synthesis_without_commands_run_normalizes_to_empty_evidence(self):
        final = """```json
        {
          "summary": "Council aligned on compact Pig Allocation table.",
          "errors": [],
          "bugs": [],
          "vault_sources_used": ["docs/09-vault-brain/INDEX.md"],
          "files_inspected": ["static/js/pigAllocation.js"],
          "confidence": 0.96,
          "confidence_reason": "Based on upstream agent artifacts.",
          "next_action": "Planner should continue."
        }
        ```"""

        artifact = execution_bridge._agent_artifact_from_final("council_synthesis", final)
        validation = execution_bridge._validate_agent_artifact("council_synthesis", artifact)

        self.assertTrue(validation["valid"], validation)
        self.assertEqual(artifact["commands_run"], [])

    def test_qa_red_team_parsed_artifact_gets_contract_keys_from_findings(self):
        final = """```json
        {
          "summary": "QA cannot approve because evidence is missing.",
          "errors": [],
          "bugs": ["No fresh tester evidence was attached."],
          "vault_sources_used": ["docs/09-vault-brain/INDEX.md"],
          "commands_run": ["git status --short"],
          "files_inspected": ["tests/test_pig_allocation_readiness_service.py"],
          "confidence": 0.55,
          "confidence_reason": "Evidence bundle is incomplete.",
          "recommended_owner_decision": "pause",
          "next_action": "Send back to builder."
        }
        ```"""

        artifact = execution_bridge._agent_artifact_from_final("qa_red_team", final)

        self.assertEqual(artifact["qa_findings"], ["No fresh tester evidence was attached."])
        self.assertEqual(artifact["red_team_status"], "blocked")
        self.assertEqual(artifact["risk_rating"], "high")

    def test_qa_red_team_allows_empty_commands_for_read_only_review(self):
        artifact = {
            "summary": "QA review passed from attached evidence.",
            "errors": [],
            "bugs": [],
            "qa_findings": [],
            "red_team_status": "pass",
            "risk_rating": "low",
            "commands_run": [],
            "files_inspected": ["mission evidence bundle"],
            "vault_sources_used": ["docs/09-vault-brain/INDEX.md"],
            "confidence": 0.96,
            "confidence_reason": "Evidence bundle contains test and screenshot proof.",
        }

        validation = execution_bridge._validate_agent_artifact("qa_red_team", artifact)

        self.assertTrue(validation["valid"], validation)

    def test_read_only_product_reviewer_allows_empty_commands_with_upstream_evidence(self):
        artifact = {
            "summary": "Product review passed from attached evidence.",
            "errors": [],
            "bugs": [],
            "vault_sources_used": ["docs/09-vault-brain/INDEX.md"],
            "confidence": 0.97,
            "confidence_reason": "Reviewed upstream test evidence and repo files.",
            "commands_run": [],
            "files_inspected": ["modules/pig_weights/pig_weights_service.py"],
            "recommended_owner_decision": "approve_final_release",
            "release_notes": ["Pre-wean tagless piglets are deferred from Needs Data."],
            "changed_files": ["modules/pig_weights/pig_weights_service.py"],
            "test_evidence": ["190 upstream regression tests passed."],
        }

        quality = execution_bridge._agent_quality_gate("product_reviewer", artifact)

        self.assertTrue(quality["passed"], quality)

    def test_builder_still_requires_command_evidence(self):
        artifact = {
            "summary": "Builder changed files.",
            "errors": [],
            "bugs": [],
            "vault_sources_used": ["docs/09-vault-brain/INDEX.md"],
            "confidence": 0.97,
            "confidence_reason": "Reviewed repo files.",
            "commands_run": [],
            "files_inspected": ["modules/pig_weights/pig_weights_service.py"],
            "changed_files": ["modules/pig_weights/pig_weights_service.py"],
            "build_notes": ["Changed service behavior."],
        }

        quality = execution_bridge._agent_quality_gate("builder", artifact)

        self.assertFalse(quality["passed"], quality)
        self.assertIn("commands_run", quality["reason"])

    def test_agent_prompt_artifacts_prioritize_recent_upstream_evidence(self):
        artifacts = {
            "builder": {
                "summary": "Builder artifact.",
                "commands_run": [f"builder command {index}" for index in range(80)],
                "files_inspected": [f"builder_file_{index}.py" for index in range(80)],
                "changed_files": ["modules/pig_weights/pig_weights_service.py"],
                "vault_sources_used": ["docs/09-vault-brain/INDEX.md"],
            },
            "tester": {
                "summary": "Tester independently verified the change.",
                "commands_run": ["python -m unittest tests.test_pig_allocation_readiness_service"],
                "tests_run": [{"command": "python -m unittest tests.test_pig_allocation_readiness_service", "result": "pass"}],
                "test_status": "pass",
                "vault_sources_used": ["docs/09-vault-brain/07-standards/TESTING_STANDARD.md"],
            },
        }

        prompt_artifacts = execution_bridge._agent_artifacts_for_prompt(
            artifacts,
            "qa_red_team",
            ["builder", "tester", "qa_red_team", "product_reviewer"],
        )
        encoded = json.dumps(prompt_artifacts, indent=2)[:12000]

        self.assertLess(encoded.index('"tester"'), encoded.index('"builder"'))
        self.assertIn("Tester independently verified the change", encoded)
        self.assertIn("commands_run_truncated_count", encoded)

    def test_extract_json_object_multiple_fenced_blocks_and_trailing_commas(self):
        text = """
        ```json
        {"summary": "bad",
        ```
        ```json
        {"summary": "ok", "items": ["one",],}
        ```
        """

        parsed = execution_bridge._extract_json_object(text)

        self.assertEqual(parsed["summary"], "ok")
        self.assertEqual(parsed["items"], ["one"])

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/execution_bridge.py"])
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_agent_runner_v2_blocks_cleanly_when_stage_runner_times_out(
        self,
        get_mission,
        update_status,
        update_vault,
        update_workflow,
        _write_heartbeat,
        _changed_files,
    ):
        get_mission.return_value = ({"success": True, "status": "ok", "mission": MISSION}, 200)
        update_status.return_value = ({"success": True, "status": "ok", "mission_status": "blocked"}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        def timeout_runner(command, *_args, **_kwargs):
            raise subprocess.TimeoutExpired(command, 11)

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=timeout_runner,
            )

        self.assertEqual(status_code, 202)
        self.assertEqual(result["status"], "agent_stage_recovery_queued")
        self.assertEqual(result["mission_status"], "approved")
        update_status.assert_called()
        self.assertEqual(update_status.call_args.args[1], "approved")
        vault_metadata = update_vault.call_args.args[1]
        self.assertEqual(vault_metadata["review_packet"]["review_status"], "internal_recovery_queued")
        self.assertIn(
            "agent_stage_runner_exception",
            json.dumps(vault_metadata["review_packet"]).lower(),
        )

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/execution_bridge.py"])
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_agent_runner_v2_blocks_when_atomic_finalizer_fails(
        self,
        get_mission,
        update_status,
        update_vault,
        update_workflow,
        _write_heartbeat,
        _changed_files,
    ):
        get_mission.side_effect = _mission_readback_sequence(
            MISSION,
            _mission_with_persisted_review_packet(),
        )
        update_status.return_value = ({"success": True, "status": "ok", "mission_status": "pr_ready"}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        self.finalize_owner_review.return_value = (
            {"success": False, "status": "owner_review_finalization_failed", "error_type": "write_failed"}, 503,
        )

        def fake_runner(*_args, **kwargs):
            prompt = kwargs["input"]
            agent = _agent_from_prompt(prompt)
            payload = _successful_stage_payload(agent)
            payload["stdout_tail"] = "x" * 5000
            payload["stderr_tail"] = "y" * 5000
            return SimpleNamespace(returncode=0, stdout=f"```json\n{json.dumps(payload)}\n```", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=fake_runner,
            )

        self.assertEqual(status_code, 503)
        self.assertEqual(result["status"], "owner_review_finalization_failed")
        self.assertFalse(any(call.args[1] == "pr_ready" for call in update_status.call_args_list))
        compact_artifact = self.finalize_owner_review.call_args.args[1]["agent_artifacts"]["reviewer"]
        self.assertNotIn("stdout_tail", compact_artifact)
        self.assertNotIn("stderr_tail", compact_artifact)
        self.assertLessEqual(len(compact_artifact["stdout_tail_excerpt"]), 500)
        if compact_artifact.get("stderr_tail_excerpt"):
            self.assertLessEqual(len(compact_artifact["stderr_tail_excerpt"]), 500)

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/execution_bridge.py"])
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_agent_runner_v2_stops_when_atomic_finalizer_loses_claim(
        self,
        get_mission,
        update_status,
        update_vault,
        update_workflow,
        _write_heartbeat,
        _changed_files,
    ):
        get_mission.side_effect = _mission_readback_sequence(MISSION, MISSION)
        update_status.return_value = ({"success": True, "status": "ok", "mission_status": "pr_ready"}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        self.finalize_owner_review.return_value = (
            {"success": False, "status": "status_claim_lost", "current_status": "blocked"}, 409,
        )

        def fake_runner(*_args, **kwargs):
            prompt = kwargs["input"]
            agent = _agent_from_prompt(prompt)
            payload = _successful_stage_payload(agent)
            return SimpleNamespace(returncode=0, stdout=f"```json\n{json.dumps(payload)}\n```", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=fake_runner,
            )

        self.assertEqual(status_code, 409)
        self.assertEqual(result["status"], "status_claim_lost")
        self.assertFalse(any(call.args[1] == "pr_ready" for call in update_status.call_args_list))

    @patch("modules.charlie.execution_bridge.get_mission")
    def test_review_packet_persist_verify_rejects_stale_send_back_packet(self, get_mission):
        mission = _mission_with_persisted_review_packet()
        mission["metadata"]["review_packet"]["review_status"] = "send_back"
        mission["metadata"]["review_packet"]["return_to_stage"] = "builder"
        get_mission.return_value = {"success": True, "status": "ok", "mission": mission}, 200

        persisted, status = execution_bridge._verify_owner_review_packet_persisted("CHARLIE-MISSION-EXEC123")

        self.assertFalse(persisted)
        self.assertEqual(status, "stale_review_packet_status_send_back")

    @patch.dict(os.environ, {"CHARLIE_AGENT_MODEL_IDEA_EXPANDER": "reasoning-model-a"}, clear=False)
    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/execution_bridge.py"])
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_parallel_read_only_agents_use_readonly_sandbox_and_agent_model(
        self,
        get_mission,
        update_status,
        update_vault,
        update_workflow,
        write_heartbeat,
        _changed_files,
    ):
        get_mission.side_effect = _mission_readback_sequence(
            MISSION,
            _mission_with_persisted_review_packet(),
        )
        update_status.return_value = ({"success": True, "status": "ok", "mission_status": "pr_ready"}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        commands_by_agent = {}

        def fake_runner(command, *_args, **kwargs):
            prompt = kwargs["input"]
            agent = _agent_from_prompt(prompt)
            commands_by_agent[agent] = command
            payload = _successful_stage_payload(agent)
            return SimpleNamespace(returncode=0, stdout=f"```json\n{json.dumps(payload)}\n```", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=fake_runner,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "agent_execution_completed")
        self.assertEqual(commands_by_agent["idea_expander"][commands_by_agent["idea_expander"].index("--sandbox") + 1], "read-only")
        self.assertIn("--model", commands_by_agent["idea_expander"])
        self.assertIn("reasoning-model-a", commands_by_agent["idea_expander"])
        vault_metadata = {"review_packet": self.finalize_owner_review.call_args.args[1]}
        self.assertEqual(
            vault_metadata["review_packet"]["agent_artifacts"]["idea_expander"]["model_assignment"]["runtime_model"],
            "reasoning-model-a",
        )

    def test_codex_fallback_command_removes_model_flag_for_parallel_anthropic_ledgers(self):
        command = ["codex", "exec", "--sandbox", "read-only", "--model", "claude-sonnet-5", "--output-last-message", "final.md", "-"]

        cleaned = execution_bridge._codex_fallback_command(command)

        self.assertNotIn("--model", cleaned)
        self.assertNotIn("claude-sonnet-5", cleaned)
        self.assertIn("--sandbox", cleaned)
        self.assertIn("read-only", cleaned)

    def test_codex_worker_uses_windowless_creation_flag_on_windows(self):
        self.assertEqual(
            execution_bridge._windowless_process_kwargs("nt"),
            {"creationflags": 0x08000000},
        )
        self.assertEqual(execution_bridge._windowless_process_kwargs("posix"), {})

    @patch("modules.charlie.execution_bridge.run_anthropic_prompt")
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch("modules.charlie.execution_bridge._changed_files", return_value=[])
    def test_agent_model_process_routes_anthropic_provider_to_claude_api(
        self,
        _changed_files,
        write_heartbeat,
        run_anthropic_prompt,
    ):
        run_anthropic_prompt.return_value = ({
            "success": True,
            "status": "anthropic_completed",
            "text": "{\"summary\":\"review ok\"}",
            "model": "claude-test",
        }, 200)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            completed = execution_bridge._run_agent_model_process(
                ["codex", "exec"],
                input="review prompt",
                stdout_path=tmp_path / "stdout.txt",
                stderr_path=tmp_path / "stderr.txt",
                final_path=tmp_path / "final.md",
                mission_id="CHARLIE-MISSION-EXEC123",
                model_assignment={
                    "runtime_provider": "anthropic",
                    "runtime_model": "claude-test",
                },
            )

            self.assertEqual(completed.returncode, 0)
            self.assertEqual((tmp_path / "final.md").read_text(encoding="utf-8"), "{\"summary\":\"review ok\"}")

        run_anthropic_prompt.assert_called_once()
        self.assertTrue(any(call.args[0].get("status") == "anthropic_agent_final_artifact_seen" for call in write_heartbeat.call_args_list))

    @patch("modules.charlie.execution_bridge._run_codex_process")
    @patch("modules.charlie.execution_bridge.run_anthropic_prompt")
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch("modules.charlie.execution_bridge._changed_files", return_value=[])
    def test_agent_model_process_falls_back_to_codex_when_anthropic_fails(
        self,
        _changed_files,
        write_heartbeat,
        run_anthropic_prompt,
        run_codex_process,
    ):
        run_anthropic_prompt.return_value = ({
            "success": False,
            "status": "anthropic_api_unreachable",
            "error": "temporary",
        }, 502)
        run_codex_process.return_value = SimpleNamespace(returncode=0, stdout="{\"summary\":\"fallback ok\"}", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            completed = execution_bridge._run_agent_model_process(
                ["codex", "exec", "--model", "claude-sonnet-5", "-"],
                input="review prompt",
                stdout_path=tmp_path / "stdout.txt",
                stderr_path=tmp_path / "stderr.txt",
                final_path=tmp_path / "final.md",
                mission_id="CHARLIE-MISSION-EXEC123",
                model_assignment={
                    "runtime_provider": "anthropic",
                    "runtime_model": "claude-sonnet-5",
                },
            )

        self.assertEqual(completed.returncode, 0)
        fallback_command = run_codex_process.call_args.args[0]
        self.assertNotIn("--model", fallback_command)
        self.assertNotIn("claude-sonnet-5", fallback_command)
        self.assertTrue(any(call.args[0].get("status") == "anthropic_agent_fallback_to_codex" for call in write_heartbeat.call_args_list))

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/execution_bridge.py"])
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_agent_runner_v2_sends_failed_tester_back_to_builder(
        self,
        get_mission,
        update_status,
        update_vault,
        update_workflow,
        write_heartbeat,
        _changed_files,
    ):
        get_mission.side_effect = _mission_readback_sequence(
            MISSION,
            _mission_with_persisted_review_packet(),
        )
        update_status.return_value = ({"success": True, "status": "ok", "mission_status": "pr_ready"}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        tester_calls = {"count": 0}
        builder_calls = {"count": 0}

        def fake_runner(*_args, **kwargs):
            prompt = kwargs["input"]
            agent = _agent_from_prompt(prompt)
            if agent == "builder":
                builder_calls["count"] += 1
            if agent == "tester":
                tester_calls["count"] += 1
            payload = _successful_stage_payload(agent)
            if agent == "tester" and tester_calls["count"] == 1:
                payload["test_status"] = "fail"
            return SimpleNamespace(returncode=0, stdout=f"```json\n{json.dumps(payload)}\n```", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=fake_runner,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "agent_execution_completed")
        self.assertGreaterEqual(builder_calls["count"], 2)
        self.assertGreaterEqual(tester_calls["count"], 2)
        self.assertTrue(self.finalize_owner_review.call_args.args[1]["backflow_events"])
        self.assertTrue(any(call.args[0].get("status") == "agent_backflow" for call in write_heartbeat.call_args_list))

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/execution_bridge.py"])
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.transition_mission_review_state")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_agent_runner_v2_send_back_reruns_from_target_stage_only(
        self,
        get_mission,
        transition_review_state,
        update_status,
        update_vault,
        update_workflow,
        _write_heartbeat,
        _changed_files,
    ):
        mission = dict(MISSION)
        mission["metadata"] = {
            "review_packet": {
                "return_to_stage": "builder",
                "agent_artifacts": {
                    "planner": {
                        "summary": "planner preserved",
                        "acceptance_criteria": ["acceptance"],
                        "test_plan": ["tests"],
                        "files_inspected": ["docs/00-start-here/CURRENT_STATE.md"],
                        "commands_run": ["rg CHARLIE docs"],
                    },
                    "architect": {
                        "summary": "architect preserved",
                        "files_to_inspect": ["modules/charlie/execution_bridge.py"],
                        "risk_notes": ["risk"],
                        "implementation_plan": ["plan"],
                        "files_inspected": ["modules/charlie/execution_bridge.py"],
                        "commands_run": ["rg run_agent_execution_bridge_v2 modules/charlie/execution_bridge.py"],
                    },
                },
            }
        }
        get_mission.side_effect = _mission_readback_sequence(
            mission,
            _mission_with_persisted_review_packet(mission),
        )
        update_status.return_value = ({"success": True, "status": "ok", "mission_status": "pr_ready"}, 200)
        transition_review_state.return_value = ({"success": True, "status": "review_state_transitioned", "mission_status": "blocked"}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        called_agents = []

        def fake_runner(*_args, **kwargs):
            prompt = kwargs["input"]
            agent = _agent_from_prompt(prompt)
            called_agents.append(agent)
            payload = _successful_stage_payload(agent)
            return SimpleNamespace(returncode=0, stdout=f"```json\n{json.dumps(payload)}\n```", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_agent_execution_bridge_v2(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=fake_runner,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(called_agents, [
            "builder",
            "tester",
            "qa_red_team",
            "product_reviewer",
            "security_reviewer",
            "evidence_reviewer",
            "reviewer",
            "publisher",
        ])
        packet = self.finalize_owner_review.call_args.args[1]
        self.assertEqual(packet["agent_artifacts"]["planner"]["summary"], "planner preserved")
        self.assertEqual(packet["agent_execution"]["rerun_from_stage"], "builder")

    def test_runner_resume_uses_completed_mission_stage_next_agent(self):
        sequence = [
            "idea_expander",
            "source_mapper",
            "visual_reference_interpreter",
            "creative_ui_designer",
            "ux_interaction_designer",
            "product_architect",
            "technical_architect",
        ]
        mission = {
            **MISSION,
            "vault": {"mission_stage": "ui_concept_ready"},
            "mission_context_pack": {"agent_order": sequence},
        }

        self.assertEqual(
            execution_bridge._execution_start_agent(mission, sequence),
            "ux_interaction_designer",
        )

    def test_runner_resume_recovers_upstream_handoff_reports_as_context(self):
        sequence = ["idea_expander", "source_mapper", "ux_interaction_designer"]
        mission = {
            **MISSION,
            "vault": {
                "mission_stage": "implementation_mapped",
                "handoff_reports": [
                    {
                        "agent": "idea_expander",
                        "summary": "Owner needs visible mission approval cards.",
                        "pass_fail_status": "complete",
                        "tests_run": [],
                        "files_changed": [],
                    },
                    {
                        "agent": "source_mapper",
                        "summary": "Mapped /charlie JS and CSS.",
                        "pass_fail_status": "complete",
                        "tests_run": ["node --check static/js/charlieMissionControl.js"],
                        "files_changed": ["static/js/charlieMissionControl.js"],
                    },
                ],
            },
            "mission_context_pack": {"agent_order": sequence},
        }

        artifacts = execution_bridge._existing_agent_artifacts_for_rerun(
            mission,
            "ux_interaction_designer",
            sequence,
        )

        self.assertEqual(artifacts["idea_expander"]["summary"], "Owner needs visible mission approval cards.")
        self.assertEqual(artifacts["source_mapper"]["summary"], "Mapped /charlie JS and CSS.")
        self.assertIn("node --check static/js/charlieMissionControl.js", artifacts["source_mapper"]["commands_run"])

    def test_reviewer_quality_gate_requires_pr_for_changed_files(self):
        artifact = {
            "summary": "review complete",
            "errors": [],
            "bugs": [],
            "files_inspected": ["modules/charlie/execution_bridge.py"],
            "commands_run": ["git diff --stat"],
            "recommended_owner_decision": "approve_final_release",
            "release_notes": ["ready"],
            "changed_files": ["modules/charlie/execution_bridge.py"],
            "test_evidence": ["unit tests passed"],
            "vault_sources_used": ["docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md"],
            "no_vault_update_required": "Runner behavior was unchanged.",
            "confidence": "98%",
            "confidence_reason": "Based on Vault Brain source docs, inspected repo files, and unit test evidence.",
        }

        result = execution_bridge._agent_quality_gate("reviewer", artifact)

        self.assertFalse(result["passed"])
        self.assertIn("local branch commit", result["reason"])

    def test_builder_quality_gate_requires_pr_for_changed_files(self):
        artifact = {
            "summary": "build complete",
            "errors": [],
            "bugs": [],
            "files_inspected": ["modules/charlie/execution_bridge.py"],
            "commands_run": ["git diff --stat"],
            "changed_files": ["modules/charlie/execution_bridge.py"],
            "build_notes": ["patched"],
            "vault_sources_used": ["docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md"],
            "no_vault_update_required": "Runner behavior was unchanged.",
            "confidence": "98%",
            "confidence_reason": "Based on Vault Brain source docs, inspected repo files, and diff evidence.",
        }

        result = execution_bridge._agent_quality_gate("builder", artifact)

        self.assertFalse(result["passed"])
        self.assertIn("local branch commit", result["reason"])

    def test_builder_quality_gate_accepts_local_branch_commit_reference(self):
        artifact = _successful_stage_payload("builder")
        artifact["changed_files"] = ["modules/charlie/mission_store.py"]
        artifact["branch_name"] = "charlie/example"
        artifact["commit_sha"] = "abc1234"

        result = execution_bridge._agent_quality_gate("builder", artifact)

        self.assertTrue(result["passed"])

    def test_reviewer_quality_gate_accepts_local_branch_commit_reference(self):
        artifact = {
            "summary": "review complete",
            "errors": [],
            "bugs": [],
            "files_inspected": ["modules/charlie/execution_bridge.py"],
            "commands_run": ["git diff --stat"],
            "recommended_owner_decision": "approve_final_release",
            "release_notes": ["ready"],
            "changed_files": ["modules/charlie/execution_bridge.py"],
            "test_evidence": ["unit tests passed"],
            "branch_name": "charlie/example",
            "commit_sha": "abc1234",
            "vault_sources_used": ["docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md"],
            "no_vault_update_required": "Runner behavior was unchanged.",
            "qa_evidence": ["QA/red-team passed"],
            "confidence": "98%",
            "confidence_reason": "Based on Vault Brain source docs, inspected repo files, local branch commit evidence, and unit tests.",
        }

        result = execution_bridge._agent_quality_gate("reviewer", artifact)

        self.assertTrue(result["passed"])

    def test_reviewer_quality_gate_treats_missing_pytest_as_advisory_with_unittest_pass(self):
        artifact = {
            "summary": "review complete",
            "errors": [],
            "bugs": [],
            "files_inspected": ["modules/charlie/execution_bridge.py"],
            "commands_run": ["python -m pytest tests/test_charlie_execution_bridge.py", "python -m unittest tests.test_charlie_execution_bridge"],
            "recommended_owner_decision": "approve_final_release",
            "release_notes": ["verification only"],
            "changed_files": [],
            "test_evidence": [
                {"command": "python -m unittest tests.test_charlie_execution_bridge", "result": "pass", "output": "Ran 77 tests OK"},
                {"command": "python -m pytest ...", "result": "not_run", "output": "No module named pytest"},
            ],
            "vault_sources_used": ["docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md"],
            "no_vault_update_required": "Reviewer verification only.",
            "qa_evidence": ["QA passed"],
            "confidence": "97%",
            "confidence_reason": "Based on Vault Brain source docs, inspected repo files, reviewer evidence, and unittest test evidence.",
        }

        result = execution_bridge._agent_quality_gate("reviewer", artifact)

        self.assertTrue(result["passed"])

    def test_auto_package_builder_changes_adds_pr_evidence(self):
        calls = []

        def fake_runner(command, **_kwargs):
            calls.append(command)
            if command[:3] == ["git", "branch", "--show-current"]:
                return SimpleNamespace(returncode=0, stdout="main\n", stderr="")
            if command[:3] == ["git", "switch", "-c"]:
                return SimpleNamespace(returncode=0, stdout="switched", stderr="")
            if command[:2] == ["git", "add"]:
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if command[:4] == ["git", "diff", "--cached", "--quiet"]:
                return SimpleNamespace(returncode=1, stdout="", stderr="")
            if command[:2] == ["git", "commit"]:
                return SimpleNamespace(returncode=0, stdout="committed", stderr="")
            if command[:3] == ["git", "rev-parse", "--short"]:
                return SimpleNamespace(returncode=0, stdout="abc1234\n", stderr="")
            if command[:2] == ["git", "push"]:
                return SimpleNamespace(returncode=0, stdout="pushed", stderr="")
            if command[:3] == ["gh", "pr", "create"]:
                return SimpleNamespace(returncode=0, stdout="https://github.com/org/repo/pull/77\n", stderr="")
            return SimpleNamespace(returncode=1, stdout="", stderr="unexpected")

        artifact = _successful_stage_payload("builder")
        artifact["changed_files"] = ["static/js/charlieMissionControl.js"]
        artifact["pr_url"] = ""
        artifact["links"] = {"pr": ""}
        artifact["errors"] = [
            "Could not create branch/commit/PR because git branch creation failed: Permission denied creating .git/refs/heads/example.lock",
        ]

        packaged = execution_bridge._auto_package_builder_changes(
            {"mission_id": "CHARLIE-MISSION-EXEC123", "title": "Mission Control Dashboard"},
            artifact,
            runner=fake_runner,
        )

        self.assertEqual(packaged["pr_url"], "https://github.com/org/repo/pull/77")
        self.assertEqual(packaged["commit_sha"], "abc1234")
        self.assertEqual(packaged["git_packaging"]["status"], "pr_created")
        self.assertEqual(packaged["errors"], [])
        self.assertTrue(any(call[:3] == ["git", "switch", "-c"] for call in calls))

    def test_auto_package_builder_changes_records_failure_without_pr(self):
        def fake_runner(command, **_kwargs):
            if command[:3] == ["git", "branch", "--show-current"]:
                return SimpleNamespace(returncode=0, stdout="main\n", stderr="")
            if command[:3] == ["git", "switch", "-c"]:
                return SimpleNamespace(returncode=1, stdout="", stderr="permission denied")
            if command[:2] == ["git", "switch"]:
                return SimpleNamespace(returncode=1, stdout="", stderr="not found")
            return SimpleNamespace(returncode=1, stdout="", stderr="unexpected")

        artifact = _successful_stage_payload("builder")
        artifact["changed_files"] = ["static/js/charlieMissionControl.js"]
        artifact["pr_url"] = ""
        artifact["links"] = {"pr": ""}

        packaged = execution_bridge._auto_package_builder_changes(
            {"mission_id": "CHARLIE-MISSION-EXEC123", "title": "Mission Control Dashboard"},
            artifact,
            runner=fake_runner,
        )

        self.assertEqual(packaged["git_packaging"]["status"], "branch_create_or_switch_failed")
        self.assertFalse(execution_bridge._artifact_pr_reference(packaged))
        self.assertTrue(execution_bridge._builder_packaging_is_terminal(packaged["git_packaging"]))

    def test_builder_packaging_accepts_reviewable_local_commit(self):
        self.assertFalse(execution_bridge._builder_packaging_is_terminal({
            "attempted": True,
            "status": "local_commit_ready",
        }))

    def test_auto_package_builder_changes_accepts_local_commit_when_pr_create_fails(self):
        calls = []

        def fake_runner(command, **_kwargs):
            calls.append(command)
            if command[:3] == ["git", "branch", "--show-current"]:
                return SimpleNamespace(returncode=0, stdout="charlie/example\n", stderr="")
            if command[:3] == ["git", "switch", "-c"]:
                return SimpleNamespace(returncode=0, stdout="switched", stderr="")
            if command[:2] == ["git", "add"]:
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if command[:4] == ["git", "diff", "--cached", "--quiet"]:
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if command[:3] == ["git", "rev-parse", "--short"]:
                return SimpleNamespace(returncode=0, stdout="abc1234\n", stderr="")
            if command[:2] == ["git", "push"]:
                return SimpleNamespace(returncode=0, stdout="pushed", stderr="")
            if command[:3] == ["gh", "pr", "create"]:
                return SimpleNamespace(returncode=1, stdout="", stderr="offline")
            return SimpleNamespace(returncode=1, stdout="", stderr="unexpected")

        artifact = _successful_stage_payload("builder")
        artifact["changed_files"] = ["static/js/charlieMissionControl.js"]
        artifact["branch_name"] = "charlie/example"
        artifact["commit_sha"] = "abc1234"
        artifact["pr_url"] = ""
        artifact["links"] = {"pr": ""}

        packaged = execution_bridge._auto_package_builder_changes(
            {"mission_id": "CHARLIE-MISSION-EXEC123", "title": "Mission Control Dashboard"},
            artifact,
            runner=fake_runner,
        )

        self.assertEqual(packaged["git_packaging"]["status"], "local_commit_ready")
        self.assertEqual(packaged["git_packaging"]["remote_status"], "gh_pr_create_failed")
        self.assertEqual(packaged["commit_sha"], "abc1234")
        self.assertTrue(execution_bridge._artifact_local_commit_reference(packaged))
        self.assertFalse(execution_bridge._artifact_pr_reference(packaged))
        self.assertTrue(any(call[:3] == ["gh", "pr", "create"] for call in calls))

    def test_reviewer_quality_gate_accepts_pr_for_changed_files(self):
        artifact = {
            "summary": "review complete",
            "errors": [],
            "bugs": [],
            "files_inspected": ["modules/charlie/execution_bridge.py"],
            "commands_run": ["git diff --stat"],
            "recommended_owner_decision": "approve_final_release",
            "release_notes": ["ready"],
            "changed_files": ["modules/charlie/execution_bridge.py"],
            "test_evidence": ["unit tests passed"],
            "links": {"pr": "https://github.com/org/repo/pull/61"},
            "vault_sources_used": ["docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md"],
            "no_vault_update_required": "Runner behavior was unchanged.",
            "qa_evidence": ["QA/red-team passed"],
            "confidence": "98%",
            "confidence_reason": "Based on Vault Brain source docs, inspected repo files, PR evidence, and unit tests.",
        }

        result = execution_bridge._agent_quality_gate("reviewer", artifact)

        self.assertTrue(result["passed"])

    def test_agent_quality_gate_requires_vault_source(self):
        artifact = _successful_stage_payload("planner")
        artifact["vault_sources_used"] = []

        result = execution_bridge._agent_quality_gate("planner", artifact)

        self.assertFalse(result["passed"])
        self.assertIn("Vault Brain sources", result["reason"])

    def test_agent_quality_gate_blocks_sensitive_change_without_vault_update_decision(self):
        artifact = _successful_stage_payload("builder")
        artifact["changed_files"] = ["modules/charlie/execution_bridge.py"]
        artifact["vault_updates"] = []
        artifact["no_vault_update_required"] = ""
        artifact["pr_url"] = "https://github.com/org/repo/pull/61"
        artifact["links"] = {"pr": "https://github.com/org/repo/pull/61"}

        result = execution_bridge._agent_quality_gate("builder", artifact)

        self.assertFalse(result["passed"])
        self.assertIn("Vault-sensitive files", result["reason"])

    @patch("modules.charlie.execution_bridge.vault_store.write_audit_event")
    @patch("modules.charlie.execution_bridge.vault_store.write_quality_gate")
    @patch("modules.charlie.execution_bridge.vault_store.write_agent_run")
    @patch("modules.charlie.execution_bridge.vault_store.write_artifact")
    @patch("modules.charlie.execution_bridge.vault_store.write_project")
    def test_normalized_vault_write_short_circuits_after_db_unavailable(
        self,
        write_project,
        write_artifact,
        write_agent_run,
        write_quality_gate,
        write_audit_event,
    ):
        write_project.return_value = (
            {
                "success": False,
                "configured": True,
                "status": "project_written_failed",
                "error_type": "OperationalError",
            },
            503,
        )

        result = execution_bridge._write_normalized_vault_records(
            {"mission_id": "CHARLIE-MISSION-EXEC123", "vault": {}},
            "EXEC123",
            {"started_at": "2026-07-04T00:00:00+00:00"},
            {"builder": _successful_stage_payload("builder")},
            {"passed": True, "reason": "ok"},
            database_url="postgres://offline",
        )

        self.assertEqual(result["failed_count"], len(result["writes"]))
        self.assertEqual(result["writes"][0]["status"], "project_written_failed")
        self.assertTrue(any(item["status"] == "skipped_after_vault_write_unavailable" for item in result["writes"][1:]))
        write_project.assert_called_once()
        write_artifact.assert_not_called()
        write_agent_run.assert_not_called()
        write_quality_gate.assert_not_called()
        write_audit_event.assert_not_called()

    def test_brain_guard_blocks_owner_review_without_vault_citations(self):
        artifacts = {
            "planner": {
                "summary": "planned",
                "vault_sources_used": [],
            }
        }

        result = execution_bridge._brain_guard_review_gate(MISSION, artifacts, ["modules/charlie/execution_bridge.py"])

        self.assertFalse(result["passed"])
        self.assertIn("Vault Brain discipline", result["reason"])
        self.assertTrue(result["findings"])

    def test_brain_guard_accepts_vault_docs_cited_in_canonical_inputs(self):
        artifacts = {
            "planner": {
                "summary": "planned",
                "vault_sources_used": ["mission_vault", "mission_context_pack"],
                "no_vault_update_required": "No Vault doctrine changed.",
                "canonical": {
                    "inputs_used": [
                        "docs/09-vault-brain/INDEX.md",
                        "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md",
                    ],
                },
            }
        }

        result = execution_bridge._brain_guard_review_gate(MISSION, artifacts, ["README.md"])

        self.assertTrue(result["passed"])
        self.assertFalse(result["findings"])

    def test_brain_guard_counts_valid_preserved_citations_during_targeted_resume(self):
        artifacts = {
            "planner": {
                "summary": "Frozen upstream plan.",
                "vault_sources_used": [
                    "docs/09-vault-brain/INDEX.md",
                    "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md",
                ],
                "no_vault_update_required": "No doctrine changed.",
            },
            "publisher": {
                "summary": "Publisher verified the rebased PR.",
                "vault_sources_used": ["docs/09-vault-brain/02-agents/charlie-core/PUBLISHER.md"],
                "no_vault_update_required": "No doctrine changed.",
            },
        }
        ledger = {"preserved_upstream_artifacts": ["planner"]}

        result = execution_bridge._brain_guard_review_gate(
            MISSION, artifacts, ["README.md"], ledger=ledger
        )

        self.assertTrue(result["source_coverage"]["passed"], result)
        self.assertIn("docs/09-vault-brain/INDEX.md", result["source_coverage"]["cited_sources"])

    def test_passed_quality_gate_reason_is_not_unresolved_issue(self):
        issues = execution_bridge._artifact_issue_items(
            "qa_red_team",
            {"qa_findings": [], "errors": [], "bugs": []},
            {"passed": True, "reason": "qa_red_team quality gate passed."},
        )

        self.assertEqual(issues, [])

    def test_write_process_text_retries_transient_permission_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "stage.stdout.txt"
            calls = {"count": 0}
            original_write_text = Path.write_text

            def fake_write_text(path, text, *args, **kwargs):
                calls["count"] += 1
                if Path(path) == target and calls["count"] == 1:
                    raise PermissionError("locked")
                return original_write_text(path, text, *args, **kwargs)

            with patch.object(Path, "write_text", fake_write_text):
                result = execution_bridge._write_process_text(target, "runner output")

            self.assertTrue(result["success"])
            self.assertEqual(calls["count"], 2)
            self.assertEqual(target.read_text(encoding="utf-8"), "runner output")

    def test_agent_stage_prompt_includes_vault_context_and_required_fields(self):
        prompt = execution_bridge.build_agent_stage_prompt(MISSION, "planner", artifacts={}, ledger={})

        self.assertIn("CHARLIE Vault Brain context", prompt)
        self.assertIn("docs/09-vault-brain/INDEX.md", prompt)
        self.assertIn("vault_sources_used", prompt)
        self.assertIn("vault_updates", prompt)

    def test_reviewer_inherits_builder_pr_reference(self):
        reviewer = {
            "summary": "review complete",
            "changed_files": ["modules/charlie/execution_bridge.py"],
        }
        artifacts = {
            "builder": {
                "pr_url": "https://github.com/org/repo/pull/61",
                "links": {"pr": "https://github.com/org/repo/pull/61"},
            }
        }

        inherited = execution_bridge._inherit_pr_reference("reviewer", reviewer, artifacts)

        self.assertEqual(inherited["pr_url"], "https://github.com/org/repo/pull/61")
        self.assertEqual(inherited["links"]["pr"], "https://github.com/org/repo/pull/61")

    def test_ui_prompt_includes_media_references_and_quality_contract(self):
        mission = dict(MISSION)
        mission["mission_type"] = "ui dashboard"
        mission["raw_text"] = "Build a dashboard from the attached screenshot."
        mission["media_references"] = [
            {
                "label": "Owner reference",
                "reference": "screenshots/Screenshot 2026-07-02 201251.png",
                "media_type": "image",
            }
        ]

        prompt = execution_bridge.build_agent_stage_prompt(mission, "builder", artifacts={}, ledger={})

        self.assertIn("Mission media/reference attachments", prompt)
        self.assertIn("Owner reference (image): screenshots/Screenshot 2026-07-02 201251.png", prompt)
        self.assertIn("charlie_ui_quality_contract_v1", prompt)
        self.assertIn("CHARLIE_CORE_UI_MISSION_STANDARD.md", prompt)

    def test_prompt_materializes_inline_image_data_urls_instead_of_embedding_base64(self):
        mission = dict(MISSION)
        mission["mission_type"] = "ui dashboard"
        mission["raw_text"] = "Use the pasted screenshot."
        mission["media_references"] = [
            {
                "label": "Pasted screenshot",
                "reference": "data:image/png;base64,ZmFrZQ==",
                "media_type": "image",
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(execution_bridge, "MISSION_MEDIA_DIR", Path(tmp)):
                media = execution_bridge._mission_media_references(mission)
                prompt = execution_bridge.build_agent_stage_prompt(mission, "builder", artifacts={}, ledger={})

            materialized_path = Path(media[0]["reference"])
            self.assertTrue(materialized_path.exists())

        self.assertEqual(media[0]["reference_kind"], "inline_image_materialized_to_local_file")
        self.assertTrue(media[0]["materialized"])
        self.assertIn("Pasted screenshot (image):", prompt)
        self.assertNotIn("data:image/png;base64", prompt)
        self.assertNotIn("ZmFrZQ==", prompt)

    def test_ui_builder_gate_requires_reference_media_and_preview(self):
        artifact = _successful_stage_payload("builder")
        artifact["ui_quality_contract"] = {
            "ui_related": True,
            "reference_media_required": True,
            "media_references": [{"reference": "screenshots/ref.png"}],
        }
        artifact["media_references_used"] = []
        artifact["visual_reference_analysis"] = ""
        artifact["local_preview"] = {}
        artifact["viewport_plan"] = []

        result = execution_bridge._agent_quality_gate("builder", artifact)

        self.assertFalse(result["passed"])
        self.assertIn("reference media", result["reason"])

    def test_ui_tester_gate_requires_desktop_and_mobile_browser_evidence(self):
        artifact = _successful_stage_payload("tester")
        artifact["ui_quality_contract"] = {"ui_related": True, "reference_media_required": False}
        artifact["browser_checks"] = ["desktop 1440 screenshot passed"]
        artifact["screenshots_captured"] = []

        result = execution_bridge._agent_quality_gate("tester", artifact)

        self.assertFalse(result["passed"])
        self.assertIn("desktop/laptop and mobile", result["reason"])

    def test_tester_gate_blocks_packaging_workspace_warning_even_when_checks_pass(self):
        artifact = _successful_stage_payload("tester")
        artifact["test_status"] = "fail"
        artifact["errors"] = [
            "Recovered Playwright selector issues caused by non-exact text matches and modal click interception during test harness development.",
            "One PowerShell file discovery command failed because Get-ChildItem was given multiple positional paths incorrectly.",
        ]
        artifact["bugs"] = [
            "Workspace is still not clean for owner-review packaging: git status shows unrelated deleted screenshot/media files and untracked test-results/."
        ]
        artifact["tests_run"] = [
            {"command": "node --check static/js/charlieMissionControl.js", "status": "pass"},
            {"command": "python -m unittest tests.test_frontend_route_contracts", "status": "pass"},
        ]
        artifact["browser_checks"] = [
            {"viewport": "desktop-1440x1000", "status": "pass"},
            {"viewport": "mobile-390x844", "status": "pass"},
        ]

        result = execution_bridge._agent_quality_gate("tester", artifact)

        self.assertFalse(result["passed"], result)
        self.assertIn("test_status=fail", result["reason"])

    def test_tester_gate_treats_recovered_setup_errors_as_advisory_when_tests_pass(self):
        artifact = _successful_stage_payload("tester")
        artifact["test_status"] = "fail"
        artifact["errors"] = [
            "Initial browser text assertion looked for exact mixed-case 'Latest Weight Date' in visible text, but CSS text-transform exposed it as uppercase; reran against case-insensitive visible text and rendered HTML.",
            "Initial npx screenshots captured /sales-availability before async cards loaded; recaptured with an explicit .pig-list-card wait.",
        ]
        artifact["bugs"] = []
        artifact["tests_run"] = [
            {"command": "node --check static/js/salesAvailability.js", "status": "pass"},
            {"command": "python -m unittest tests.test_frontend_route_contracts", "result": "Ran 40 tests OK"},
        ]

        result = execution_bridge._agent_quality_gate("tester", artifact)

        self.assertTrue(result["passed"], result)
        self.assertEqual(artifact["test_status"], "pass")
        self.assertTrue(artifact.get("warnings"))

    def test_planner_source_gate_accepts_exact_pig_allocation_source_map_paths(self):
        artifact = _successful_stage_payload("planner")
        artifact["implementation_source_map"] = {
            "matched_sections": [
                {
                    "key": "pig_allocation_herdmaster",
                    "must_inspect_before_advice": True,
                    "vault_docs": ["docs/09-vault-brain/02-agents/farm/HERDMASTER.md"],
                    "code_paths": ["modules/pig_weights/pig_weights_service.py"],
                    "tests": ["tests/test_pig_allocation_readiness_service.py"],
                    "legacy_sources": ["docs/03-google-sheets/sheets/FARM.md"],
                }
            ],
            "required_inspection_paths": [
                "docs/09-vault-brain/02-agents/farm/HERDMASTER.md",
                "modules/pig_weights/pig_weights_service.py",
                "tests/test_pig_allocation_readiness_service.py",
                "docs/03-google-sheets/sheets/FARM.md",
            ],
        }
        artifact["files_inspected"] = [
            "docs/09-vault-brain/02-agents/farm/HERDMASTER.md",
            "modules/pig_weights/pig_weights_service.py",
            "tests/test_pig_allocation_readiness_service.py",
        ]
        artifact["implementation_sources_used"] = [
            "modules/pig_weights/pig_weights_service.py",
            "tests/test_pig_allocation_readiness_service.py",
        ]

        result = execution_bridge._agent_quality_gate("planner", artifact)

        self.assertTrue(result["passed"], result)

    def test_builder_source_gate_accepts_changed_matched_implementation_file(self):
        artifact = _successful_stage_payload("builder")
        artifact["implementation_source_map"] = {
            "matched_sections": [
                {
                    "key": "sam_live_stock_sales",
                    "must_inspect_before_advice": True,
                    "code_paths": ["modules/sales/sam_live_stock_launch_control.py"],
                    "tests": ["tests/test_sam_live_stock_launch_control.py"],
                }
            ],
            "required_inspection_paths": [
                "modules/sales/sam_live_stock_launch_control.py",
                "tests/test_sam_live_stock_launch_control.py",
            ],
        }
        artifact["files_inspected"] = ["docs/09-vault-brain/02-agents/sales/SAM.md"]
        artifact["implementation_sources_used"] = []
        artifact["changed_files"] = ["modules/sales/sam_live_stock_launch_control.py"]
        artifact["links"] = {"pr": "https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/131"}

        result = execution_bridge._agent_quality_gate("builder", artifact)

        self.assertTrue(result["passed"], result)

    def test_tester_source_gate_accepts_matched_code_and_test_paths_without_doc_citation(self):
        artifact = _successful_stage_payload("tester")
        artifact["implementation_source_map"] = {
            "matched_sections": [
                {
                    "key": "sam_live_stock_sales",
                    "must_inspect_before_advice": True,
                    "vault_docs": [
                        "docs/09-vault-brain/02-agents/sales/SAM.md",
                        "docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md",
                    ],
                    "code_paths": [
                        "modules/sales/sam_live_stock_launch_control.py",
                        "modules/oom_sakkie/telegram_direct.py",
                    ],
                    "tests": [
                        "tests/test_sam_live_stock_launch_control.py",
                        "tests/test_oom_sakkie_routes.py",
                    ],
                    "legacy_sources": [
                        "docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md",
                    ],
                }
            ],
            "required_inspection_paths": [
                "docs/09-vault-brain/02-agents/sales/SAM.md",
                "docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md",
                "docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md",
            ],
        }
        artifact["files_inspected"] = [
            "modules/sales/sam_live_stock_launch_control.py",
            "modules/oom_sakkie/telegram_direct.py",
            "tests/test_sam_live_stock_launch_control.py",
            "tests/test_oom_sakkie_routes.py",
        ]
        artifact["commands_run"] = [
            "python -m unittest tests.test_sam_live_stock_launch_control tests.test_oom_sakkie_routes"
        ]
        artifact["tests_run"] = [
            {"command": "python -m unittest tests.test_sam_live_stock_launch_control tests.test_oom_sakkie_routes", "status": "pass"}
        ]

        result = execution_bridge._agent_quality_gate("tester", artifact)

        self.assertTrue(result["passed"], result)

    def test_ui_reviewer_gate_requires_visual_acceptance_decision(self):
        artifact = _successful_stage_payload("reviewer")
        artifact["ui_quality_contract"] = {"ui_related": True, "reference_media_required": False}
        artifact["visual_review_notes"] = ["Desktop and mobile screenshots inspected."]
        artifact["visual_acceptance_decision"] = ""

        result = execution_bridge._agent_quality_gate("reviewer", artifact)

        self.assertFalse(result["passed"])
        self.assertIn("visual acceptance", result["reason"])

    def test_reviewer_owner_approval_gate_instruction_is_not_send_back_blocker(self):
        artifact = _successful_stage_payload("reviewer")
        artifact.update({
            "recommended_owner_decision": "approve_final_release",
            "next_action": "Owner final review: approve PR #89 for merge/release, or send back with comments if the visual emphasis should be stronger/different.",
            "release_notes": [
                "Owner should review PR #89 and either approve final release or send back with comments. Do not merge or deploy until owner final approval is recorded."
            ],
            "qa_evidence": ["Focused tests, API checks, and browser screenshots passed."],
            "visual_acceptance_decision": "approve",
            "visual_review_notes": ["Desktop and mobile visual evidence passed."],
        })

        result = execution_bridge._agent_quality_gate("reviewer", artifact)

        self.assertTrue(result["passed"], result)

    def test_visual_qa_approved_notes_are_not_send_back_blockers(self):
        artifact = _successful_stage_payload("visual_qa_reviewer")
        artifact.update({
            "ui_quality_contract": {"ui_related": True, "reference_media_required": False},
            "recommended_owner_decision": "approve_final_release",
            "visual_acceptance_decision": "approve",
            "visual_review_notes": [
                "Review and Reset controls remain visible in desktop, laptop, mobile, and empty-state evidence.",
                "Non-blocking polish note: summary metric cards above the table are low contrast.",
            ],
            "reference_match_assessment": "The compact table matches the written owner request.",
            "media_references_used": [],
            "commands_run": ["node --check static\\js\\pigAllocation.js"],
            "files_inspected": ["static/js/pigAllocation.js", "static/css/main.css"],
            "vault_sources_used": ["docs/09-vault-brain/07-standards/CHARLIE_CORE_UI_MISSION_STANDARD.md"],
        })

        result = execution_bridge._agent_quality_gate("visual_qa_reviewer", artifact)

        self.assertTrue(result["passed"], result)

    def test_evidence_reviewer_approved_visual_notes_are_not_false_blockers(self):
        artifact = _successful_stage_payload("evidence_reviewer")
        artifact.update({
            "recommended_owner_decision": "approve_final_release",
            "visual_acceptance_decision": "approve",
            "visual_review_notes": [
                "Needs Data pill uses text label + color, avoiding color-only accessibility failure.",
                "Desktop and mobile screenshots captured with no overflow/layout breakage.",
            ],
            "test_evidence": [
                "node --check static/js/pigAllocation.js -> pass",
                ".\\venv\\Scripts\\python.exe -m unittest tests.test_frontend_route_contracts -> 39 tests OK",
            ],
            "media_references_used": [
                ".charlie_runner/review-media/CHARLIE-MISSION-20C3BC66A8BAD3C5/purpose-review-desktop-1440x1000.png",
            ],
        })

        result = execution_bridge._agent_quality_gate("evidence_reviewer", artifact)

        self.assertTrue(result["passed"], result)

    def test_visual_qa_approved_tail_json_is_not_send_back_blocker(self):
        artifact = _successful_stage_payload("visual_qa_reviewer")
        approved_tail = (
            '"visual_review_notes": ["Pig ID is no longer duplicated in the primary Pig cell; '
            'it remains available under More/details.", "Review actions remain visible on desktop, '
            'laptop, and mobile.", "Residual polish: summary metric cards are low contrast, '
            'but this is not a blocker."], "send_back_stage": ""'
        )
        artifact.update({
            "ui_quality_contract": {"ui_related": True, "reference_media_required": False},
            "recommended_owner_decision": "approve_final_release",
            "visual_acceptance_decision": "approve",
            "visual_review_notes": [
                "Review actions remain visible on desktop, laptop, and mobile.",
            ],
            "reference_match_assessment": "The compact table matches the written owner request.",
            "media_references_used": [],
            "commands_run": ["node --check static\\js\\pigAllocation.js"],
            "files_inspected": ["static/js/pigAllocation.js", "static/css/main.css"],
            "vault_sources_used": ["docs/09-vault-brain/07-standards/CHARLIE_CORE_UI_MISSION_STANDARD.md"],
            "stdout_tail": approved_tail,
            "stderr_tail": approved_tail,
        })

        result = execution_bridge._agent_quality_gate("visual_qa_reviewer", artifact)

        self.assertTrue(result["passed"], result)

    def test_review_board_owner_approval_gate_instruction_is_not_send_back_blocker(self):
        for agent in ["product_reviewer", "business_reviewer", "security_reviewer", "evidence_reviewer"]:
            with self.subTest(agent=agent):
                artifact = _successful_stage_payload(agent)
                artifact.update({
                    "recommended_owner_decision": "approve_final_release",
                    "next_action": "Owner review PR #93 and either approve final release or send back with comments. Do not merge or deploy until owner final approval is recorded.",
                    "release_notes": [
                        "Fixed owner-visible behavior; owner should review before final release."
                    ],
                })

                result = execution_bridge._agent_quality_gate(agent, artifact)

                self.assertTrue(result["passed"], result)

    def test_review_board_send_back_decision_still_blocks(self):
        artifact = _successful_stage_payload("product_reviewer")
        artifact.update({
            "recommended_owner_decision": "send_back",
            "next_action": "Owner review PR #93 and send back because accepted behavior is still wrong.",
        })

        result = execution_bridge._agent_quality_gate("product_reviewer", artifact)

        self.assertFalse(result["passed"])
        self.assertIn("recommended_owner_decision=send_back", result["reason"])

    def test_risk_agent_blocks_send_back_and_failed_browser_evidence(self):
        artifact = _successful_stage_payload("risk_agent")
        artifact.update({
            "recommended_owner_decision": "send_back",
            "visual_acceptance_decision": "send_back",
            "test_evidence": [
                "node --check static/js/charlieMissionControl.js: pass",
                "npm run test:charlie:browser on PR branch: fail, 2 failed",
                "python -m pytest focused suite in main worktree: not run, pytest module missing",
            ],
            "changed_files": [
                "Diff against current main also includes many out-of-scope files and must not be approved as-is",
            ],
            "visual_review_notes": [
                "Reviewer cannot approve visual acceptance while Playwright cannot reach the expected /charlie command center.",
            ],
        })

        result = execution_bridge._agent_quality_gate("risk_agent", artifact)

        self.assertFalse(result["passed"])
        self.assertIn("recommended_owner_decision=send_back", result["reason"])

    def test_parallel_read_only_risk_agent_defers_downstream_evidence_warning(self):
        artifact = _successful_stage_payload("risk_agent")
        artifact.update({
            "recommended_owner_decision": "pause",
            "changed_files": [],
            "risks": [
                "Cannot certify persisted owner review packet because review packet persistence happens in a later stage.",
                "Migration compatibility must be verified before any later owner-approved migration.",
            ],
            "next_action": "Require final reviewer to prove persisted review packet and test evidence before pr_ready.",
        })

        result = execution_bridge._parallel_read_only_quality_gate("risk_agent", artifact)

        self.assertTrue(result["passed"], result)
        self.assertNotIn("deferred_blocker", result)
        self.assertIn("quality gate passed", result["reason"])

    def test_risk_agent_pause_is_advisory_without_present_violation(self):
        artifact = _successful_stage_payload("risk_agent")
        artifact.update({
            "summary": "Owner review packet readback must be proven by later final review before pr_ready.",
            "recommended_owner_decision": "pause",
            "changed_files": [],
            "risks": ["Final reviewer must prove persisted review packet readback."],
        })

        result = execution_bridge._agent_quality_gate("risk_agent", artifact)

        self.assertTrue(result["passed"], result)

    def test_parallel_read_only_risk_agent_defers_read_only_environment_test_failure(self):
        artifact = _successful_stage_payload("risk_agent")
        artifact.update({
            "recommended_owner_decision": "pause",
            "changed_files": [],
            "errors": [
                "Focused unittest suite failed because Python tempfile found no usable temporary directory and .charlie_runner writes were denied by the read-only environment.",
            ],
            "test_evidence": [
                "python -m unittest ... => FAILED in this read-only sandbox with environment write/temp errors, not a proven code regression.",
            ],
            "confidence_reason": "Failures are attributable to read-only environment constraints rather than asserted product defects.",
            "next_action": "Tester must rerun focused unittest suite in a writable local runner before owner review.",
        })

        result = execution_bridge._parallel_read_only_quality_gate("risk_agent", artifact)

        self.assertTrue(result["passed"], result)
        self.assertTrue(result["deferred_blocker"])

    def test_parallel_read_only_risk_agent_defers_advisory_broad_test_timeout(self):
        artifact = _successful_stage_payload("risk_agent")
        artifact.update({
            "status": "pass_with_required_mitigations",
            "summary": "Risk review found no present red-zone action. Builder must add authority matrix tests before owner review.",
            "recommended_owner_decision": "approve_final_release",
            "changed_files": [],
            "test_evidence": [
                {
                    "command": ".\\venv\\Scripts\\python.exe -m unittest tests.test_charlie_execution_bridge tests.test_charlie_core_workflow",
                    "result": "pass",
                    "summary": "108 tests passed.",
                },
                {
                    "command": ".\\venv\\Scripts\\python.exe -m unittest broad CHARLIE/SAM/Oom Sakkie suite",
                    "result": "timeout",
                    "summary": "Timed out after 124 seconds; no pass/fail claim made.",
                },
            ],
            "quality_gate": {
                "risk_stage_ready": True,
                "send_back_required": False,
                "required_mitigations_for_later_agents": [
                    "Tests must prove no authority unlock without owner approval and runtime gate.",
                ],
            },
            "next_action": "Handoff to later Builder/Tester stages for focused implementation tests before pr_ready.",
        })

        low_level_quality = {
            "passed": False,
            "reason": (
                "risk_agent recorded blocking evidence: "
                '"result": "timeout", "summary": "Timed out after 124 seconds; no pass/fail claim made."'
            ),
        }
        deferred = execution_bridge._read_only_block_is_downstream_evidence_only(
            "risk_agent",
            artifact,
            low_level_quality,
        )

        self.assertTrue(deferred)

    def test_parallel_read_only_risk_agent_still_blocks_present_red_zone_violation(self):
        artifact = _successful_stage_payload("risk_agent")
        artifact.update({
            "recommended_owner_decision": "send_back",
            "changed_files": [],
            "risks": [
                "Mission attempted a production data write without owner approval.",
            ],
            "next_action": "Stop and require owner approval before any production data write.",
        })

        result = execution_bridge._parallel_read_only_quality_gate("risk_agent", artifact)

        self.assertFalse(result["passed"])
        self.assertIn("recommended_owner_decision=send_back", result["reason"])

    def test_parallel_risk_planning_findings_continue_to_builder(self):
        artifact = _successful_stage_payload("risk_agent")
        artifact.update({
            "recommended_owner_decision": "pause",
            "changed_files": [],
            "bugs": ["No database-enforced idempotent order-to-sales upsert exists yet."],
            "next_action": "Council and Planner must carry mandatory mitigations into Builder acceptance tests.",
        })

        result = execution_bridge._parallel_read_only_quality_gate("risk_agent", artifact)

        self.assertTrue(result["passed"], result)
        self.assertTrue(result["deferred_blocker"])
        self.assertIn("deferred_planning_risk", result["reason"])

    def test_parallel_risk_present_unauthorized_send_still_blocks(self):
        artifact = _successful_stage_payload("risk_agent")
        artifact.update({
            "recommended_owner_decision": "pause",
            "changed_files": [],
            "bugs": ["Mission attempted customer send without owner approval."],
            "next_action": "Builder must repair the route.",
        })

        result = execution_bridge._parallel_read_only_quality_gate("risk_agent", artifact)

        self.assertFalse(result["passed"])

    def test_tester_defers_screenshot_runtime_only_block_to_visual_qa(self):
        artifact = _successful_stage_payload("tester")
        artifact.update({
            "test_status": "blocked",
            "tests_run": [{"command": "python -m unittest focused", "result": "pass", "summary": "73 tests passed"}],
            "errors": [
                "Browser-control discovery exposed no node_repl js runtime.",
                "No real screenshots could be captured for the preview URL.",
            ],
            "bugs": [],
        })

        result = execution_bridge._agent_quality_gate("tester", artifact)

        self.assertTrue(result["passed"], result)
        self.assertTrue(result["visual_evidence_deferred"])

    def test_non_ui_risk_agent_visual_pause_is_not_a_judgement_block(self):
        artifact = _successful_stage_payload("risk_agent")
        artifact.update({
            "test_evidence": ["focused risk checks passed"],
            "visual_acceptance_decision": "pause",
            "visual_review_notes": ["Mission is not UI-related. No visual evidence required."],
            "risk_notes": ["Present blockers: none found."],
        })

        result = execution_bridge._agent_quality_gate("risk_agent", artifact)

        self.assertTrue(result["passed"], result)

    def test_security_reviewer_owner_review_stop_is_not_a_send_back_block(self):
        artifact = _successful_stage_payload("security_reviewer")
        artifact.update({
            "recommended_owner_decision": "approve_final_release",
            "summary": "Security review passed for owner review.",
            "next_action": "Stop at owner review. Owner may approve this docs/design pack or send back comments.",
            "test_evidence": ["Focused tests passed."],
            "risk_notes": ["No production writes are authorized by this docs pack."],
            "changed_files": ["docs/09-vault-brain/08-business-rules/HERDMASTER_PIG_ALLOCATION_ALERT_RULES.md"],
        })

        result = execution_bridge._agent_quality_gate("security_reviewer", artifact)

        self.assertTrue(result["passed"], result)

    def test_risk_agent_ui_send_back_targets_frontend_implementation(self):
        artifact = _successful_stage_payload("risk_agent")
        artifact.update({
            "recommended_owner_decision": "send_back",
            "visual_acceptance_decision": "send_back",
            "visual_review_notes": ["Mobile screenshot is too tall and owner buttons are buried."],
        })
        quality = execution_bridge._agent_quality_gate("risk_agent", artifact)

        target = execution_bridge._agent_backflow_target("risk_agent", artifact, quality)

        self.assertFalse(quality["passed"])
        self.assertEqual(target, "frontend_design_implementer")

    def test_non_ui_visual_notes_do_not_count_as_ui_evidence(self):
        artifact = _successful_stage_payload("security_reviewer")
        artifact.update({
            "visual_acceptance_decision": "approve",
            "visual_review_notes": ["Not a UI mission. No frontend, dashboard, screenshot, or visual evidence gate was required."],
            "visual_reference_analysis": "Not applicable: mission is explicitly no-UI.",
        })

        self.assertFalse(execution_bridge._artifact_has_ui_evidence(artifact))

    def test_backflow_target_resolves_ui_agent_to_builder_when_not_in_sequence(self):
        target = execution_bridge._resolve_agent_backflow_target(
            "frontend_design_implementer",
            ["idea_expander", "source_mapper", "builder", "tester", "reviewer"],
        )

        self.assertEqual(target, "builder")

    def test_technical_architect_can_record_risks_without_judgement_block(self):
        artifact = _successful_stage_payload("technical_architect")
        artifact["risk_notes"] = [
            "A stale PR or failed browser gate would require send back during review.",
        ]

        result = execution_bridge._agent_quality_gate("technical_architect", artifact)

        self.assertTrue(result["passed"], result)

    def test_visual_review_capture_writes_local_screenshot_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("modules.charlie.execution_bridge.REVIEW_MEDIA_DIR", Path(tmp)):
                def fake_runner(command, **_kwargs):
                    Path(command[-1]).write_bytes(b"fake png")
                    return SimpleNamespace(returncode=0, stdout="screenshot saved", stderr="")

                capture = execution_bridge._capture_visual_review_media(
                    "CHARLIE-MISSION-EXEC123",
                    {"url": "http://127.0.0.1:5000/charlie"},
                    changed_files=["templates/charlie.html", "static/js/charlieMissionControl.js"],
                    run_subprocess=fake_runner,
                )
                media = execution_bridge._review_media_items("CHARLIE-MISSION-EXEC123")

        self.assertTrue(capture["captured"])
        self.assertEqual(capture["status"], "captured")
        self.assertEqual(capture["capture_source"], "local_preview")
        self.assertEqual(capture["fallback_reason"], "")
        filenames = {item["filename"] for item in media}
        self.assertEqual(filenames, {"owner_review_preview.png", "owner_review_mobile.png"})
        self.assertTrue(any(
            "/api/charlie/build-relay/review-media/CHARLIE-MISSION-EXEC123/owner_review_preview.png" in item["reference"]
            for item in media
        ))

    def test_review_media_items_accepts_legacy_hyphen_media_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            canonical_root = Path(tmp) / "review_media"
            legacy_root = Path(tmp) / "review-media"
            media_dir = legacy_root / "CHARLIE-MISSION-EXEC123"
            media_dir.mkdir(parents=True)
            (media_dir / "purpose-review-desktop.png").write_bytes(b"fake png")
            with patch("modules.charlie.execution_bridge.REVIEW_MEDIA_DIR", canonical_root):
                with patch("modules.charlie.execution_bridge.LEGACY_REVIEW_MEDIA_DIR", legacy_root):
                    media = execution_bridge._review_media_items("CHARLIE-MISSION-EXEC123")

        self.assertEqual(len(media), 1)
        self.assertEqual(media[0]["filename"], "purpose-review-desktop.png")
        self.assertIn(
            "/api/charlie/build-relay/review-media/CHARLIE-MISSION-EXEC123/purpose-review-desktop.png",
            media[0]["reference"],
        )

    def test_visual_review_capture_uses_local_preview_for_mission_specific_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("modules.charlie.execution_bridge.REVIEW_MEDIA_DIR", Path(tmp)):
                def fake_runner(command, **_kwargs):
                    Path(command[-1]).write_bytes(b"fake png")
                    return SimpleNamespace(returncode=0, stdout="screenshot saved", stderr="")

                capture = execution_bridge._capture_visual_review_media(
                    "CHARLIE-MISSION-EXEC123",
                    {"url": "http://127.0.0.1:5000/sales/beacon-media"},
                    run_subprocess=fake_runner,
                )

        self.assertTrue(capture["captured"])
        self.assertEqual(capture["capture_source"], "local_preview")
        self.assertEqual(capture["fallback_reason"], "")
        self.assertEqual(capture["capture_url"], "http://127.0.0.1:5000/sales/beacon-media")
        self.assertEqual(len(capture["captures"]), 2)

    @patch("modules.charlie.execution_bridge._probe_local_http_url", return_value={"ok": True, "status": "ok", "http_status": 200})
    def test_visual_review_capture_infers_sales_dashboard_for_sales_availability_js(self, _probe):
        seen_urls = []
        with tempfile.TemporaryDirectory() as tmp:
            with patch("modules.charlie.execution_bridge.REVIEW_MEDIA_DIR", Path(tmp)):
                def fake_runner(command, **_kwargs):
                    seen_urls.append(command[-2])
                    Path(command[-1]).write_bytes(b"fake png")
                    return SimpleNamespace(returncode=0, stdout="screenshot saved", stderr="")

                capture = execution_bridge._capture_visual_review_media(
                    "CHARLIE-MISSION-HERDMASTER",
                    {"url": "http://127.0.0.1:5000/charlie"},
                    changed_files=["static/js/salesAvailability.js"],
                    final_message="Herdmaster stock cards now show latest weight date.",
                    run_subprocess=fake_runner,
                )

        self.assertTrue(capture["captured"])
        self.assertEqual(capture["capture_source"], "local_preview")
        self.assertEqual(capture["fallback_reason"], "")
        self.assertEqual(capture["capture_url"], "http://127.0.0.1:5000/sales-dashboard")
        self.assertEqual(seen_urls, [
            "http://127.0.0.1:5000/sales-dashboard",
            "http://127.0.0.1:5000/sales-dashboard",
        ])
        self.assertEqual(
            capture["capture_url_recovery"]["changed_ui_preview_inference"]["status"],
            "inferred_changed_ui_route",
        )

    @patch("modules.charlie.execution_bridge._probe_local_http_url")
    def test_visual_review_capture_recovers_dead_preview_url_from_command_port(self, probe):
        probe.side_effect = [
            {"ok": False, "status": "probe_failed", "error_type": "URLError"},
            {"ok": True, "status": "ok", "http_status": 200},
        ]
        seen_urls = []
        with tempfile.TemporaryDirectory() as tmp:
            with patch("modules.charlie.execution_bridge.REVIEW_MEDIA_DIR", Path(tmp)):
                def fake_runner(command, **_kwargs):
                    seen_urls.append(command[-2])
                    Path(command[-1]).write_bytes(b"fake png")
                    return SimpleNamespace(returncode=0, stdout="screenshot saved", stderr="")

                capture = execution_bridge._capture_visual_review_media(
                    "CHARLIE-MISSION-EXEC123",
                    {
                        "url": "http://127.0.0.1:5003/pig/SOW-1/family-tree",
                        "command": ".\\venv\\Scripts\\python.exe -m flask --app app run --host 127.0.0.1 --port 5000",
                    },
                    changed_files=["templates/family-tree.html"],
                    run_subprocess=fake_runner,
                )

        self.assertTrue(capture["captured"])
        self.assertEqual(capture["url"], "http://127.0.0.1:5003/pig/SOW-1/family-tree")
        self.assertEqual(capture["capture_url"], "http://127.0.0.1:5000/pig/SOW-1/family-tree")
        self.assertEqual(capture["capture_url_recovery"]["status"], "recovered_from_preview_command_port")
        self.assertEqual(seen_urls, [
            "http://127.0.0.1:5000/pig/SOW-1/family-tree",
            "http://127.0.0.1:5000/pig/SOW-1/family-tree",
        ])

    @patch("modules.charlie.execution_bridge._probe_local_http_url", return_value={"ok": True, "status": "ok", "http_status": 200})
    def test_visual_review_capture_reuses_durable_stage_media_when_playwright_fails(self, _probe):
        with tempfile.TemporaryDirectory() as tmp:
            review_root = Path(tmp) / "review_media"
            source_dir = review_root / "stage-evidence"
            source_dir.mkdir(parents=True)
            desktop = source_dir / "family-tree-desktop-1440.png"
            mobile = source_dir / "family-tree-mobile-390.png"
            desktop.write_bytes(b"desktop")
            mobile.write_bytes(b"mobile")

            with patch("modules.charlie.execution_bridge.REVIEW_MEDIA_DIR", review_root):
                def failing_runner(command, **_kwargs):
                    return SimpleNamespace(returncode=1, stdout="", stderr="ERR_CONNECTION_REFUSED")

                capture = execution_bridge._capture_visual_review_media(
                    "CHARLIE-MISSION-EXEC123",
                    {"url": "http://127.0.0.1:5000/pig/SOW-1/family-tree"},
                    artifacts={
                        "tester": {
                            "screenshots_captured": [
                                {"viewport": "desktop/laptop", "path": str(desktop)},
                                {"viewport": "mobile", "path": str(mobile)},
                            ],
                        }
                    },
                    run_subprocess=failing_runner,
                )
                media = execution_bridge._review_media_items("CHARLIE-MISSION-EXEC123")

        self.assertTrue(capture["captured"])
        self.assertEqual(capture["capture_method"], "durable_stage_media_reuse")
        self.assertEqual(capture["durable_media_reuse"]["status"], "promoted_from_durable_stage_media")
        self.assertEqual({item["filename"] for item in media}, {"owner_review_preview.png", "owner_review_mobile.png"})

    def test_visual_review_blocks_owner_review_without_required_viewport_media(self):
        packet = {
            "ui_related": True,
            "status": "captured",
            "capture": {"capture_source": "local_preview"},
            "media": [{"filename": "owner_review_preview.png"}],
        }

        self.assertTrue(execution_bridge._visual_review_blocks_owner_review(packet))

    def test_visual_review_packet_generates_fallback_media_without_preview_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("modules.charlie.execution_bridge.REVIEW_MEDIA_DIR", Path(tmp)):
                def fake_capture(mission_id, _local_preview, **kwargs):
                    media_dir = execution_bridge._review_media_path(mission_id)
                    media_dir.mkdir(parents=True, exist_ok=True)
                    (media_dir / "owner_review_preview.png").write_bytes(b"fake png")
                    return {
                        "captured": True,
                        "status": "captured",
                        "capture_source": "generated_owner_review_packet",
                        "fallback_reason": "preview_url_not_captured",
                    }

                with patch("modules.charlie.execution_bridge._capture_visual_review_media", side_effect=fake_capture):
                    packet = execution_bridge._build_visual_review_packet(
                        mission_id="CHARLIE-MISSION-EXEC123",
                        mission_type="feature build",
                        changed_files=["templates/charlie.html"],
                        local_preview={"url": "", "status": "not_captured"},
                        artifacts={"builder": {"summary": "Changed owner review UI."}},
                    )

        self.assertTrue(packet["ui_related"])
        self.assertEqual(packet["status"], "captured")
        self.assertEqual(packet["capture"]["fallback_reason"], "preview_url_not_captured")
        self.assertEqual(packet["media"][0]["filename"], "owner_review_preview.png")
        self.assertTrue(execution_bridge._visual_review_blocks_owner_review(packet))

    def test_visual_review_packet_blocks_when_capture_fallback_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("modules.charlie.execution_bridge.REVIEW_MEDIA_DIR", Path(tmp)):
                with patch("modules.charlie.execution_bridge._capture_visual_review_media", return_value={
                    "captured": False,
                    "status": "capture_command_failed",
                    "fallback_reason": "preview_url_not_captured",
                }):
                    packet = execution_bridge._build_visual_review_packet(
                        mission_id="CHARLIE-MISSION-EXEC123",
                        mission_type="feature build",
                        changed_files=["templates/charlie.html"],
                        local_preview={"url": "", "status": "not_captured"},
                        artifacts={"builder": {"summary": "Changed owner review UI."}},
                    )

        self.assertTrue(packet["ui_related"])
        self.assertEqual(packet["status"], "not_captured_blocked")
        self.assertEqual(packet["capture"]["status"], "capture_command_failed")
        self.assertEqual(packet["media"], [])
        self.assertIn("screenshot capture is blocked", packet["summary"])

    @patch("modules.charlie.execution_bridge._probe_local_preview_url")
    def test_local_preview_infers_reachable_runner_url(self, probe):
        probe.side_effect = [
            {"ok": False, "status": "login_redirect"},
            {"ok": True, "status": "ok", "http_status": 200},
        ]

        preview = execution_bridge._local_preview_from_reviewer({
            "summary": "Preview command only.",
            "links": {},
        })

        self.assertEqual(preview["url"], "http://127.0.0.1:5002/charlie")
        self.assertEqual(preview["source"], "local_runner_probe")

    def test_visual_review_blocks_owner_review_for_ui_without_media(self):
        self.assertTrue(execution_bridge._visual_review_blocks_owner_review({
            "ui_related": True,
            "status": "not_captured_blocked",
        }))
        self.assertTrue(execution_bridge._visual_review_blocks_owner_review({
            "ui_related": True,
            "status": "captured",
            "capture": {"capture_source": "generated_owner_review_packet"},
            "media": [{"filename": "owner_review_preview.png"}],
        }))
        self.assertFalse(execution_bridge._visual_review_blocks_owner_review({
            "ui_related": True,
            "status": "captured",
            "capture": {"capture_source": "local_preview"},
            "media": [{"filename": "owner_review_preview.png"}, {"filename": "owner_review_mobile.png"}],
        }))

    def test_agent_build_mission_type_is_not_ui_by_substring(self):
        self.assertFalse(execution_bridge._is_ui_related_mission(
            mission_type="agent build",
            changed_files=["modules/charlie/execution_bridge.py"],
            final_message="backend runner update",
        ))

    def test_explicit_no_ui_language_overrides_visual_review_terms(self):
        self.assertFalse(execution_bridge._is_ui_related_mission(
            mission_type="system improvement",
            changed_files=["modules/charlie/execution_bridge.py"],
            final_message="Run a no UI owner review packet canary. Do not change UI. Visual review is not required.",
        ))

    def test_extract_local_preview_strips_trailing_quote(self):
        preview = execution_bridge._extract_local_preview('Open "http://127.0.0.1:5003/charlie"')

        self.assertEqual(preview["url"], "http://127.0.0.1:5003/charlie")

    @patch("modules.charlie.execution_bridge.shutil.which")
    def test_npx_executable_prefers_windows_cmd_shim(self, which):
        def fake_which(name):
            return "C:/node/npx.cmd" if name == "npx.cmd" else None

        which.side_effect = fake_which

        with patch("modules.charlie.execution_bridge.os.name", "nt"):
            self.assertEqual(execution_bridge._npx_executable(), "C:/node/npx.cmd")

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["planning/CODEX_CHAT.md"])
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    def test_run_codex_process_writes_final_heartbeat_after_artifact_stop(self, write_heartbeat, _changed_files):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            final_path = tmp_path / "final.md"
            command = [
                sys.executable,
                "-c",
                "import pathlib,sys,time; pathlib.Path(sys.argv[1]).write_text('done', encoding='utf-8'); time.sleep(5)",
                str(final_path),
            ]

            with patch("modules.charlie.execution_bridge.FINAL_ARTIFACT_GRACE_SECONDS", 0), patch(
                "modules.charlie.execution_bridge.POLL_SECONDS",
                0.05,
            ):
                completed = execution_bridge._run_codex_process(
                    command,
                    cwd=tmp,
                    timeout_seconds=3,
                    stdout_path=tmp_path / "stdout.txt",
                    stderr_path=tmp_path / "stderr.txt",
                    final_path=final_path,
                    mission_id="CHARLIE-MISSION-EXEC123",
                )
                final_exists = final_path.exists()

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(final_exists)
        self.assertTrue(any(
            call.args[0].get("status") == "codex_final_artifact_seen"
            and call.args[0].get("final_artifact_present") is True
            for call in write_heartbeat.call_args_list
        ))

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/beacon/creative_studio.py"])
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    def test_run_codex_process_does_not_kill_agent_while_output_is_advancing(self, write_heartbeat, _changed_files):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            final_path = tmp_path / "final.md"
            command = [
                sys.executable,
                "-c",
                (
                    "import pathlib,sys,time; "
                    "[(print(i, file=sys.stderr, flush=True), time.sleep(0.35)) for i in range(6)]; "
                    "pathlib.Path(sys.argv[1]).write_text('done', encoding='utf-8'); time.sleep(0.2)"
                ),
                str(final_path),
            ]

            with patch("modules.charlie.execution_bridge.NO_FINAL_ARTIFACT_TIMEOUT_SECONDS", 1), patch(
                "modules.charlie.execution_bridge.NO_FINAL_ARTIFACT_WARNING_SECONDS", 0.5,
            ), patch("modules.charlie.execution_bridge.FINAL_ARTIFACT_GRACE_SECONDS", 0), patch(
                "modules.charlie.execution_bridge.POLL_SECONDS", 0.05,
            ):
                completed = execution_bridge._run_codex_process(
                    command,
                    cwd=tmp,
                    timeout_seconds=4,
                    stdout_path=tmp_path / "stdout.txt",
                    stderr_path=tmp_path / "stderr.txt",
                    final_path=final_path,
                    mission_id="CHARLIE-MISSION-ACTIVE-BUILDER",
                )
                final_exists = final_path.exists()

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(final_exists)
        statuses = [call.args[0].get("status") for call in write_heartbeat.call_args_list]
        self.assertIn("codex_final_artifact_seen", statuses)
        self.assertNotIn("codex_no_final_artifact_warning", statuses)
        self.assertNotIn("codex_no_final_artifact_timeout", statuses)

    @patch("modules.charlie.execution_bridge.update_mission_vault")
    def test_process_visual_review_cleanup_intent_updates_local_cleanup_status(self, update_vault):
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        mission = {
            "mission_id": "CHARLIE-MISSION-EXEC123",
            "metadata": {
                "review_packet": {
                    "summary": "Ready",
                    "visual_review": {
                        "ui_related": True,
                        "cleanup": {"required": True, "status": "cleanup_requested"},
                    },
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch("modules.charlie.execution_bridge.REVIEW_MEDIA_DIR", Path(tmp)):
                media_dir = Path(tmp) / "CHARLIE-MISSION-EXEC123"
                media_dir.mkdir()
                (media_dir / "owner_review_preview.png").write_bytes(b"fake png")

                result = execution_bridge.process_visual_review_cleanup_intent(
                    "CHARLIE-MISSION-EXEC123",
                    mission=mission,
                )

                self.assertFalse(media_dir.exists())

        self.assertTrue(result["processed"])
        self.assertEqual(result["status"], "cleaned")
        update_vault.assert_called_once()
        review_packet = update_vault.call_args.args[1]["review_packet"]
        cleanup = review_packet["visual_review"]["cleanup"]
        self.assertEqual(cleanup["status"], "cleaned")
        self.assertEqual(cleanup["result"]["status"], "review_media_cleaned")

    @patch("modules.charlie.execution_bridge.get_mission")
    def test_prepare_codex_execution_rejects_release_approved_mission(self, get_mission):
        mission = dict(MISSION)
        mission["status"] = "release_approved"
        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)

        result, status_code = execution_bridge.prepare_codex_execution(
            mission_id="CHARLIE-MISSION-EXEC123",
        )

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "mission_not_ready_for_codex_execution")
        self.assertEqual(result["required_status"], "in_progress")

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/execution_bridge.py"])
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_run_codex_execution_bridge_records_review_packet_on_success(
        self,
        get_mission,
        update_vault,
        update_workflow,
        _changed_files,
    ):
        get_mission.return_value = ({"success": True, "status": "ok", "mission": MISSION}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        def fake_runner(*_args, **kwargs):
            output_path = kwargs["cwd"]
            self.assertIn("input", kwargs)
            return SimpleNamespace(
                returncode=0,
                stdout="Summary complete\nTests run: bridge tests passed",
                stderr="",
            )

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_codex_execution_bridge(
                mission_id="CHARLIE-MISSION-EXEC123",
                execute_codex=True,
                output_dir=tmp,
                run_subprocess=fake_runner,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "codex_execution_completed")
        self.assertEqual(result["mission_status"], "pr_ready")
        self.assertGreaterEqual(update_workflow.call_count, 6)
        update_vault.assert_called()
        vault_metadata = update_vault.call_args.args[1]
        self.assertIn("review_packet", vault_metadata)
        self.assertIn("modules/charlie/execution_bridge.py", vault_metadata["review_packet"]["changed_files"])

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["static/js/charlieMissionControl.js"])
    @patch("modules.charlie.execution_bridge._capture_visual_review_media", return_value={"captured": True, "status": "captured", "capture_source": "generated_owner_review_packet"})
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    def test_complete_codex_execution_from_existing_final_artifact(
        self,
        update_vault,
        update_workflow,
        _capture,
        _changed_files,
    ):
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            final_path = Path(tmp) / "EXEC123-20260630T000000Z-1.final.md"
            final_path.write_text(
                "Summary complete\nOpen: http://127.0.0.1:5002/charlie\nTests run: checks passed",
                encoding="utf-8",
            )
            result, status_code = execution_bridge.complete_codex_execution_from_artifact(
                "CHARLIE-MISSION-EXEC123",
                final_path=final_path,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "codex_execution_completed")
        self.assertEqual(result["mission_status"], "pr_ready")
        self.assertGreaterEqual(update_workflow.call_count, 6)
        vault_metadata = update_vault.call_args.args[1]
        self.assertEqual(vault_metadata["review_packet"]["local_preview"]["url"], "http://127.0.0.1:5002/charlie")
        self.assertEqual(vault_metadata["review_packet"]["local_preview"]["status"], "captured")
        self.assertTrue(vault_metadata["review_packet"]["visual_review"]["ui_related"])
        self.assertEqual(vault_metadata["review_packet"]["visual_review"]["local_preview"]["url"], "http://127.0.0.1:5002/charlie")

    def test_visual_review_packet_collects_local_runner_media_for_ui_changes(self):
        mission_id = "CHARLIE-MISSION-VISUAL123"
        media_dir = execution_bridge._review_media_path(mission_id)
        if media_dir.exists():
            shutil.rmtree(media_dir)
        media_dir.mkdir(parents=True)
        try:
            (media_dir / "owner-review.png").write_bytes(b"not-real-image-but-route-contract")
            with patch("modules.charlie.execution_bridge._capture_visual_review_media", return_value={"captured": True, "status": "captured"}):
                packet = execution_bridge._build_visual_review_packet(
                    mission_id=mission_id,
                    changed_files=["templates/charlie.html"],
                    local_preview={"url": "http://127.0.0.1:5000/charlie", "status": "captured"},
                )
        finally:
            shutil.rmtree(media_dir, ignore_errors=True)

        self.assertTrue(packet["ui_related"])
        self.assertEqual(packet["status"], "captured")
        self.assertEqual(packet["media"][0]["reference"], "/api/charlie/build-relay/review-media/CHARLIE-MISSION-VISUAL123/owner-review.png")
        self.assertEqual(packet["cleanup"]["status"], "pending_owner_decision")

    def test_cleanup_visual_review_media_removes_only_runner_media_dir(self):
        mission_id = "CHARLIE-MISSION-CLEANUP123"
        media_dir = execution_bridge._review_media_path(mission_id)
        media_dir.mkdir(parents=True, exist_ok=True)
        (media_dir / "capture.png").write_bytes(b"temporary")

        result = execution_bridge.cleanup_visual_review_media(mission_id)

        self.assertTrue(result["cleaned"])
        self.assertEqual(result["status"], "review_media_cleaned")
        self.assertFalse(media_dir.exists())

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["static/js/charlieMissionControl.js"])
    @patch("modules.charlie.execution_bridge._capture_visual_review_media", return_value={"captured": True, "status": "captured", "capture_source": "generated_owner_review_packet"})
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    def test_complete_codex_execution_does_not_default_local_preview_to_control_dashboard(
        self,
        update_vault,
        update_workflow,
        _capture,
        _changed_files,
    ):
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            final_path = Path(tmp) / "EXEC123-20260630T000000Z-1.final.md"
            final_path.write_text(
                "Summary complete\nTests run: checks passed\nNo local preview was provided.",
                encoding="utf-8",
            )
            result, status_code = execution_bridge.complete_codex_execution_from_artifact(
                "CHARLIE-MISSION-EXEC123",
                final_path=final_path,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "codex_execution_completed")
        vault_metadata = update_vault.call_args.args[1]
        local_preview = vault_metadata["review_packet"]["local_preview"]
        self.assertEqual(local_preview["url"], "")
        self.assertEqual(local_preview["status"], "not_captured")
        self.assertIn("No mission-specific local preview URL", local_preview["message"])
        self.assertEqual(vault_metadata["review_packet"]["links"]["local_preview"], "")

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/routes.py"])
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    def test_block_codex_execution_without_final_artifact_creates_blocked_review_packet(
        self,
        update_vault,
        update_workflow,
        update_status,
        _changed_files,
    ):
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_status.return_value = ({"success": True, "status": "ok"}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            prompt_path = Path(tmp) / "EXEC123.prompt.md"
            stdout_path = Path(tmp) / "EXEC123.stdout.txt"
            stderr_path = Path(tmp) / "EXEC123.stderr.txt"
            final_path = Path(tmp) / "EXEC123.final.md"
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text("supervisor timeout", encoding="utf-8")
            result, status_code = execution_bridge.block_codex_execution_without_final_artifact(
                "CHARLIE-MISSION-EXEC123",
                execution_id="EXEC123",
                prompt_path=prompt_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                final_path=final_path,
            )

        self.assertEqual(status_code, 504)
        self.assertEqual(result["status"], "codex_no_final_artifact_timeout")
        self.assertEqual(result["mission_status"], "blocked")
        update_vault.assert_called_once()
        packet = update_vault.call_args.args[1]["review_packet"]
        self.assertIn("no final artifact", packet["summary"].lower())
        self.assertIn("modules/charlie/routes.py", packet["changed_files"])
        self.assertTrue(packet["partial_work"]["recoverable"])
        self.assertEqual(packet["partial_work"]["changed_files_count"], 1)
        self.assertIn("modules/charlie/routes.py", packet["partial_work"]["changed_files"])
        self.assertIn("commit/push", packet["recommended_next_action"])
        self.assertEqual(result["partial_work"]["changed_files_count"], 1)
        update_status.assert_called_once()
        self.assertEqual(update_status.call_args.args[1], "blocked")

    @patch("modules.charlie.execution_bridge._changed_files", return_value=["modules/charlie/routes.py"])
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    def test_block_agent_stage_preserves_failed_qa_artifact_for_owner_review(
        self,
        update_vault,
        update_workflow,
        update_status,
        _changed_files,
    ):
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_status.return_value = ({"success": True, "status": "ok"}, 200)
        ledger = {
            "version": "charlie_agent_runner_v2",
            "execution_id": "EXEC123",
            "mission_id": "CHARLIE-MISSION-EXEC123",
            "stages": [],
            "backflow_events": [
                {"from_agent": "qa_red_team", "to_agent": "builder", "reason": "QA failed", "attempt": 1},
                {"from_agent": "qa_red_team", "to_agent": "builder", "reason": "QA failed", "attempt": 2},
            ],
            "quality_gates": [],
        }
        artifact = {
            "summary": "QA found release-blocking risks.",
            "errors": [],
            "bugs": ["Mutation routes allow read-role writes."],
            "files_inspected": ["modules/charlie/routes.py"],
            "commands_run": ["python -m unittest tests.test_charlie_build_relay"],
            "qa_findings": ["Owner mutation route requires stronger access gate."],
            "red_team_status": "fail",
            "risk_rating": "high",
            "quality_gate": {"passed": False, "reason": "QA/red-team reported red_team_status=fail."},
        }

        with tempfile.TemporaryDirectory() as tmp:
            final_path = Path(tmp) / "EXEC123.qa_red_team.final.md"
            stdout_path = Path(tmp) / "EXEC123.qa_red_team.stdout.txt"
            stderr_path = Path(tmp) / "EXEC123.qa_red_team.stderr.txt"
            prompt_path = Path(tmp) / "EXEC123.qa_red_team.prompt.md"
            for path in (final_path, stdout_path, stderr_path, prompt_path):
                path.write_text("", encoding="utf-8")
            result, status_code = execution_bridge._block_agent_stage(
                "CHARLIE-MISSION-EXEC123",
                "EXEC123",
                ledger,
                "qa_red_team",
                {
                    "final_path": final_path,
                    "stdout_path": stdout_path,
                    "stderr_path": stderr_path,
                    "prompt_path": prompt_path,
                },
                SimpleNamespace(returncode=0, stdout="", stderr=""),
                "2026-07-01T06:00:00+00:00",
                blocked_reason="QA/red-team reported red_team_status=fail.",
                artifact=artifact,
                artifacts={"qa_red_team": artifact},
            )

        self.assertEqual(status_code, 202)
        self.assertEqual(result["status"], "agent_stage_recovery_queued")
        packet = update_vault.call_args.args[1]["review_packet"]
        self.assertEqual(packet["blocked_agent"], "qa_red_team")
        self.assertEqual(packet["blocked_reason"], "QA/red-team reported red_team_status=fail.")
        self.assertIn("qa_red_team", packet["agent_artifacts"])
        self.assertEqual(packet["agent_artifacts"]["qa_red_team"]["risk_rating"], "high")
        self.assertIn("Owner mutation route requires stronger access gate.", packet["qa_evidence"])
        self.assertEqual(len(packet["backflow_events"]), 2)
        self.assertEqual(packet["blocked_summary"]["blocked_at"], "qa_red_team")
        self.assertEqual(packet["blocked_summary"]["send_back_attempts"], 2)
        self.assertTrue(packet["unresolved_blockers"])
        self.assertEqual(packet["review_status"], "internal_recovery_queued")
        self.assertEqual(packet["block_disposition"]["responsible_stage"], "builder")
        self.assertEqual(update_status.call_args.args[1], "approved")
        self.assertTrue(any(
            "Owner mutation route requires stronger access gate." in item.get("finding", "")
            for item in packet["unresolved_blockers"]
        ))

    @patch("modules.charlie.execution_bridge._changed_files", return_value=[])
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.update_mission_workflow_step")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    def test_exhausted_acceptance_matrix_stops_in_owner_block_instead_of_requeueing_qa(
        self,
        update_vault,
        update_workflow,
        update_status,
        _changed_files,
    ):
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)
        update_workflow.return_value = ({"success": True, "status": "ok"}, 200)
        update_status.return_value = ({"success": True, "status": "ok"}, 200)
        ledger = {
            "version": "charlie_agent_runner_v2",
            "execution_id": "EXEC-MATRIX-STOP",
            "mission_id": "CHARLIE-MISSION-MATRIX-STOP",
            "stages": [],
            "backflow_events": [],
            "quality_gates": [],
        }
        artifact = {
            "summary": "The scoped diff is empty; there is no implementation for owner review.",
            "errors": [],
            "bugs": [],
            "acceptance_results": [
                {"id": "acceptance-storage", "status": "failed", "evidence": ["No implementation exists."]},
            ],
            "mission_governance_decision": {
                "route": "owner_block",
                "reason": "Frozen acceptance criteria remain failed after the bounded correction budget was exhausted.",
                "failed_acceptance_ids": ["acceptance-storage"],
                "red_zone_findings": [],
            },
            "red_team_status": "blocked",
            "risk_rating": "high",
        }

        with tempfile.TemporaryDirectory() as tmp:
            paths = {
                name: Path(tmp) / f"EXEC-MATRIX-STOP.qa_red_team.{suffix}"
                for name, suffix in (
                    ("final_path", "final.md"),
                    ("stdout_path", "stdout.txt"),
                    ("stderr_path", "stderr.txt"),
                    ("prompt_path", "prompt.md"),
                )
            }
            for path in paths.values():
                path.write_text("", encoding="utf-8")
            result, status_code = execution_bridge._block_agent_stage(
                "CHARLIE-MISSION-MATRIX-STOP",
                "EXEC-MATRIX-STOP",
                ledger,
                "qa_red_team",
                paths,
                SimpleNamespace(returncode=0, stdout="", stderr=""),
                "2026-07-13T10:00:00+00:00",
                blocked_reason=artifact["mission_governance_decision"]["reason"],
                artifact=artifact,
                artifacts={"qa_red_team": artifact},
            )

        self.assertEqual(status_code, 504)
        self.assertEqual(result["status"], "agent_stage_blocked")
        self.assertEqual(result["mission_status"], "blocked")
        self.assertFalse(result["block_disposition"]["recoverable"])
        packet = update_vault.call_args.args[1]["review_packet"]
        self.assertEqual(packet["review_status"], "agent_blocked")
        self.assertEqual(packet["block_disposition"]["responsible_stage"], "owner")
        self.assertEqual(update_status.call_args.args[1], "blocked")

    def test_agent_stage_prompt_includes_unresolved_backflow_issues(self):
        ledger = {
            "backflow_events": [
                {
                    "from_agent": "qa_red_team",
                    "to_agent": "builder",
                    "reason": "QA failed",
                    "unresolved_blockers": [
                        {
                            "severity": "high",
                            "file": "modules/charlie/routes.py",
                            "finding": "Dashboard route performs destructive cleanup.",
                        }
                    ],
                }
            ],
            "unresolved_blockers": [
                {
                    "severity": "high",
                    "file": "modules/charlie/routes.py",
                    "finding": "Dashboard route performs destructive cleanup.",
                }
            ],
        }

        prompt = execution_bridge.build_agent_stage_prompt(MISSION, "builder", artifacts={}, ledger=ledger)

        self.assertIn("Unresolved agent send-back issues", prompt)
        self.assertIn("Dashboard route performs destructive cleanup.", prompt)

    def test_backflow_fingerprint_detects_repeated_same_blocker(self):
        ledger = {"backflow_events": []}
        artifact = {
            "summary": "Visual evidence is missing.",
            "send_back_stage": "builder",
            "bugs": ["No screenshot proof attached."],
            "next_action": "Capture browser evidence.",
        }
        fingerprint = execution_bridge._backflow_fingerprint(
            "reviewer",
            "builder",
            "Reviewer requires screenshot proof.",
            artifact,
        )

        execution_bridge._append_backflow_event(
            ledger,
            from_agent="reviewer",
            to_agent="builder",
            reason="Reviewer requires screenshot proof.",
            attempt=1,
            artifact=artifact,
            fingerprint=fingerprint,
        )
        execution_bridge._append_backflow_event(
            ledger,
            from_agent="reviewer",
            to_agent="builder",
            reason="Reviewer requires screenshot proof.",
            attempt=2,
            artifact=artifact,
            fingerprint=fingerprint,
            loop_detected=True,
        )

        self.assertEqual(execution_bridge._backflow_fingerprint_count(ledger, fingerprint), 2)
        self.assertTrue(ledger["backflow_events"][-1]["loop_detected"])
        recovery = execution_bridge._loop_recovery_next_action(
            "reviewer",
            "builder",
            "Reviewer requires screenshot proof.",
            artifact,
        )
        self.assertIn("Stop automatic retries", recovery)
        self.assertIn("Capture browser evidence", recovery)

    def test_backflow_fingerprint_groups_equivalent_acceptance_wording(self):
        first = execution_bridge._backflow_fingerprint(
            "qa_red_team", "builder",
            "Frozen acceptance criteria failed: lifecycle transition matrix and canonical order linkage evidence missing.",
            {"bugs": ["Add focused lifecycle matrix tests", "Prove canonical order creation and /orders/{order_id} deep-link"]},
        )
        second = execution_bridge._backflow_fingerprint(
            "qa_red_team", "builder",
            "Acceptance evidence remains incomplete for status transitions, order creation, and named action deep links.",
            {"bugs": ["Lifecycle transition matrix not exhaustive", "Order linkage and deep link proof required"]},
        )
        self.assertEqual(first, second)

    def test_agent_command_base_replaces_global_model_with_agent_model(self):
        command = execution_bridge._agent_command_base(
            ["codex", "exec", "--model", "base-model", "--sandbox", "workspace-write"],
            {"runtime_model": "agent-specific-model"},
        )

        self.assertEqual(command[command.index("--model") + 1], "agent-specific-model")
        self.assertNotIn("base-model", command)

    @patch.dict(os.environ, {"CHARLIE_REQUIRE_AGENT_MODEL_ROUTING": "1"}, clear=False)
    def test_strict_agent_model_routing_flag_is_enabled_by_env(self):
        self.assertTrue(execution_bridge._strict_agent_model_routing_required())

    def test_validate_qa_artifact_allows_empty_findings_when_qa_passes(self):
        artifact = _successful_stage_payload("qa_red_team")
        artifact["qa_findings"] = []

        result = execution_bridge._validate_agent_artifact("qa_red_team", artifact)

        self.assertTrue(result["valid"])
        self.assertEqual(result["missing_keys"], [])

    def test_qa_quality_gate_treats_medium_pass_findings_as_advisory(self):
        artifact = _successful_stage_payload("qa_red_team")
        artifact["red_team_status"] = "pass"
        artifact["risk_rating"] = "medium"
        artifact["qa_findings"] = [
            "No release-blocking runner reliability defect was proven by this QA stage.",
            "Owner review evidence must disclose the dirty worktree caveat.",
        ]
        artifact["stdout_tail"] = (
            "confidence 0.97 based on execution_bridge evidence; "
            "git status shows unrelated dirty planning/CODEX_CHAT.md plus untracked test-results."
        )
        artifact["stderr_tail"] = ""
        artifact["confidence"] = "97%"
        artifact["confidence_reason"] = "Based on Vault Brain source docs, inspected repo files, QA evidence, and unit test evidence."

        result = execution_bridge._agent_quality_gate("qa_red_team", artifact)

        self.assertTrue(result["passed"])

    def test_qa_quality_gate_treats_timeout_only_failure_as_advisory_with_pass_evidence(self):
        artifact = _successful_stage_payload("qa_red_team")
        artifact["red_team_status"] = "fail"
        artifact["risk_rating"] = "high"
        artifact["errors"] = [
            "tests.test_charlie_execution_bridge timed out after 120s.",
            "tests.test_charlie_mission_pickup timed out after 120s.",
        ]
        artifact["qa_findings"] = [
            "Changed-file regression evidence is incomplete because CHARLIE execution bridge and mission pickup test modules timed out.",
        ]
        artifact["tests_run"] = [
            {"command": "python -m unittest tests.test_charlie_source_map", "status": "pass", "output": "Ran 16 tests in 0.307s OK"},
            {"command": "python -m unittest tests.test_sam_live_stock_launch_control", "status": "pass", "output": "Ran 82 tests in 2.939s OK"},
        ]
        artifact["stdout_tail"] = "Focused suites passed. Ran 16 tests OK. Ran 82 tests OK."

        result = execution_bridge._agent_quality_gate("qa_red_team", artifact)

        self.assertTrue(result["passed"], result)
        self.assertTrue(result.get("timeout_advisory"), result)

    def test_qa_quality_gate_defers_browser_environment_failure_with_pass_evidence(self):
        artifact = _successful_stage_payload("qa_red_team")
        artifact["red_team_status"] = "fail"
        artifact["risk_rating"] = "high"
        artifact["errors"] = ["Browser list was empty and the local runner could not capture screenshot media."]
        artifact["tests_run"] = [{
            "command": "python -m unittest tests.test_beacon_campaign tests.test_sales_transaction_routes",
            "status": "pass",
            "output": "Ran 122 tests OK",
        }]
        artifact["visual_quality_findings"] = [
            "Focused implementation checks passed; visual proof remains for the dedicated Visual QA gate.",
        ]

        result = execution_bridge._agent_quality_gate("qa_red_team", artifact)

        self.assertTrue(result["passed"], result)
        self.assertTrue(result.get("visual_evidence_deferred"), result)

    def test_qa_quality_gate_does_not_defer_real_failure_with_browser_noise(self):
        artifact = _successful_stage_payload("qa_red_team")
        artifact["red_team_status"] = "fail"
        artifact["risk_rating"] = "high"
        artifact["errors"] = [
            "Browser list was empty and the local runner could not capture screenshot media.",
            "Campaign decision endpoint writes without owner approval.",
        ]
        artifact["tests_run"] = [
            {"command": "python -m unittest tests.test_beacon_campaign", "status": "pass", "output": "Ran 20 tests OK"},
        ]
        artifact["visual_quality_findings"] = ["Browser evidence was unavailable."]

        result = execution_bridge._agent_quality_gate("qa_red_team", artifact)

        self.assertFalse(result["passed"], result)

    def test_qa_quality_gate_still_blocks_real_failure_with_timeout_noise(self):
        artifact = _successful_stage_payload("qa_red_team")
        artifact["red_team_status"] = "fail"
        artifact["risk_rating"] = "high"
        artifact["errors"] = [
            "tests.test_charlie_execution_bridge timed out after 120s.",
            "Prepared action can create an order without owner approval.",
        ]
        artifact["tests_run"] = [
            {"command": "python -m unittest tests.test_charlie_source_map", "status": "pass", "output": "Ran 16 tests in 0.307s OK"},
        ]

        result = execution_bridge._agent_quality_gate("qa_red_team", artifact)

        self.assertFalse(result["passed"], result)

    def test_tester_quality_gate_treats_broad_timeout_as_advisory_with_focused_pass_evidence(self):
        artifact = _successful_stage_payload("tester")
        artifact["test_status"] = "fail"
        artifact["tests_run"] = [
            {
                "command": "python -m unittest tests.test_sam_live_stock_runtime tests.test_sam_live_stock_launch_control",
                "status": "pass",
                "result": "89 focused SAM Live Stock tests passed",
            },
            {
                "command": "python -m unittest tests.test_charlie_mission_pickup",
                "status": "fail",
                "result": "broad CHARLIE runner suite timed out after 124 seconds",
            },
        ]
        artifact["errors"] = [
            "tests.test_charlie_mission_pickup timed out after 124 seconds.",
            "Full CHARLIE core regression command timed out after 124 seconds.",
        ]
        artifact["stdout_tail"] = "Focused SAM suites passed. Ran 89 tests OK. Broad runner command timed out."

        result = execution_bridge._agent_quality_gate("tester", artifact)

        self.assertTrue(result["passed"], result)
        self.assertTrue(result.get("timeout_advisory"), result)
        self.assertTrue(result.get("focused_tests_passed"), result)

    def test_tester_quality_gate_keeps_pass_when_timeout_is_only_reported_error(self):
        artifact = _successful_stage_payload("tester")
        artifact["test_status"] = "pass"
        artifact["tests_run"] = [
            {
                "command": "python -m unittest tests.test_farm_supabase_read_service tests.test_pig_allocation_readiness_service",
                "status": "pass",
                "result": "49 tests passed",
            },
            {
                "command": "python -m unittest tests.test_frontend_route_contracts",
                "status": "pass",
                "result": "39 tests passed",
            },
            {
                "command": "python -m unittest tests.test_frontend_route_contracts tests.test_sam_live_stock_runtime",
                "status": "timeout_advisory",
                "result": "Runner outer timeout after 124 seconds; no assertion failure observed",
            },
        ]
        artifact["errors"] = [
            "The combined tests.test_frontend_route_contracts tests.test_sam_live_stock_runtime command exceeded the runner's 124-second outer timeout before returning results."
        ]
        artifact["stdout_tail"] = "Focused verification passed: 88 tests and JavaScript syntax checks succeeded."

        result = execution_bridge._agent_quality_gate("tester", artifact)

        self.assertTrue(result["passed"], result)
        self.assertTrue(result.get("timeout_advisory"), result)
        self.assertTrue(result.get("focused_tests_passed"), result)

    def test_tester_quality_gate_still_blocks_real_safety_failure_with_timeout_noise(self):
        artifact = _successful_stage_payload("tester")
        artifact["test_status"] = "fail"
        artifact["tests_run"] = [
            {
                "command": "python -m unittest tests.test_sam_live_stock_runtime",
                "status": "pass",
                "result": "focused tests passed",
            },
            {
                "command": "python -m unittest tests.test_charlie_mission_pickup",
                "status": "fail",
                "result": "timed out after 124 seconds",
            },
        ]
        artifact["errors"] = [
            "tests.test_charlie_mission_pickup timed out after 124 seconds.",
            "Owner-approved send path can create an order without owner approval.",
        ]

        result = execution_bridge._agent_quality_gate("tester", artifact)

        self.assertFalse(result["passed"], result)

    def test_tester_quality_gate_ignores_corrected_informational_command_note(self):
        artifact = _successful_stage_payload("tester")
        artifact["tests_run"] = [{
            "command": "python -m unittest tests.test_sam_farm_knowledge",
            "status": "pass",
            "result": "44/44 stress scenarios passing",
        }]
        artifact["errors"] = [{
            "scope_relation": "tester command only",
            "introduced_by_current_diff": False,
            "affected_file/path": "modules/sales/sam_meat_stress.py:534",
            "severity": "informational",
            "acceptance_relation": "Does not violate acceptance-4dc264ae53",
            "detail": "The unsupported argument was corrected and the subsequent run returned 44/44 passing.",
        }]

        result = execution_bridge._agent_quality_gate("tester", artifact)

        self.assertTrue(result["passed"], result)

    def test_tester_quality_gate_keeps_current_diff_error_blocking(self):
        artifact = _successful_stage_payload("tester")
        artifact["tests_run"] = [{
            "command": "python -m unittest tests.test_sam_farm_knowledge",
            "status": "pass",
            "result": "focused tests passed",
        }]
        artifact["errors"] = [{
            "scope_relation": "product implementation",
            "introduced_by_current_diff": True,
            "severity": "high",
            "acceptance_relation": "Violates the public-copy acceptance criterion",
            "detail": "The current diff still exposes internal pilot wording.",
        }]

        result = execution_bridge._agent_quality_gate("tester", artifact)

        self.assertFalse(result["passed"], result)

    def test_tester_quality_gate_does_not_treat_fail_closed_safety_handoff_as_failure(self):
        artifact = _successful_stage_payload("tester")
        artifact["next_action"] = (
            "Continue to QA Red Team for authority-boundary and fail-closed gate verification, "
            "then proceed through owner review without rebuilding."
        )

        result = execution_bridge._agent_quality_gate("tester", artifact)

        self.assertTrue(result["passed"], result)

    def test_tester_quality_gate_still_blocks_explicit_failure_handoff(self):
        artifact = _successful_stage_payload("tester")
        artifact["next_action"] = "The public-copy acceptance check failed; send back to Builder."

        result = execution_bridge._agent_quality_gate("tester", artifact)

        self.assertFalse(result["passed"], result)

    def test_validate_technical_architect_allows_explicit_empty_planning_lists(self):
        artifact = _successful_stage_payload("technical_architect")
        artifact["files_to_inspect"] = []
        artifact["implementation_plan"] = []

        result = execution_bridge._validate_agent_artifact("technical_architect", artifact)

        self.assertTrue(result["valid"])
        self.assertEqual(result["missing_keys"], [])

    @patch("modules.charlie.execution_bridge.get_mission")
    def test_prepare_release_execution_writes_release_packet(self, get_mission):
        mission = dict(MISSION)
        mission["status"] = "release_approved"
        mission["metadata"] = {"review_packet": {"summary": "Owner approved.", "test_evidence": ["tests passed"]}}
        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.prepare_release_execution(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
            )
            packet = Path(result["release_packet_path"]).read_text(encoding="utf-8")

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "release_execution_prepared")
        self.assertIn("no_release_closeout", packet)
        self.assertIn("Owner approved.", packet)
        self.assertIn("live_release_verification", packet)

    @patch.dict(os.environ, {"CHARLIE_RELEASE_VERIFY_URL": "https://example.com/charlie"}, clear=True)
    def test_default_release_verify_url_prefers_explicit_charlie_url(self):
        self.assertEqual(execution_bridge._default_release_verify_url(), "https://example.com/charlie")

    def test_release_verification_reports_missing_url_as_unconfigured(self):
        result = execution_bridge._wait_for_release_verification("", attempts=3, interval_seconds=0)

        self.assertFalse(result["verified"])
        self.assertEqual(result["status"], "verify_url_not_configured")
        self.assertEqual(result["attempts"], 0)

    @patch("modules.charlie.execution_bridge.get_mission")
    def test_prepare_release_execution_rejects_non_release_approved_mission(self, get_mission):
        get_mission.return_value = ({"success": True, "status": "ok", "mission": MISSION}, 200)

        result, status_code = execution_bridge.prepare_release_execution(
            mission_id="CHARLIE-MISSION-EXEC123",
        )

        self.assertEqual(status_code, 409)
        self.assertEqual(result["status"], "mission_not_ready_for_release_execution")
        self.assertEqual(result["required_status"], "release_approved")

    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_complete_no_release_marks_release_approved_done(self, get_mission, update_vault, update_status):
        mission = dict(MISSION)
        mission["status"] = "release_approved"
        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)
        update_status.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.complete_no_release_mission(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "release_no_release_completed")
        statuses = [call.args[1] for call in update_status.call_args_list]
        self.assertEqual(statuses, ["release_in_progress", "done"])
        update_vault.assert_called_once()

    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_run_release_execution_blocks_without_pr_reference(self, get_mission, update_status):
        mission = dict(MISSION)
        mission["status"] = "release_approved"
        mission["metadata"] = {"review_packet": {"summary": "Approved but no PR."}}
        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)
        update_status.return_value = ({"success": True, "status": "ok"}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_release_execution(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
                merge_pr=True,
            )

        self.assertEqual(status_code, 409)
        self.assertEqual(result["status"], "release_pr_reference_required")
        statuses = [call.args[1] for call in update_status.call_args_list]
        self.assertEqual(statuses, ["blocked"])

    @patch("modules.charlie.execution_bridge.ReleaseCoordinator")
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_run_release_execution_keeps_approval_state_when_coordinator_is_locked(
        self, get_mission, update_status, coordinator
    ):
        mission = dict(MISSION)
        mission["status"] = "release_approved"
        mission["metadata"] = {"review_packet": {"links": {"pr": "https://github.com/org/repo/pull/56"}}}
        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)
        coordinator.return_value.acquire.return_value = (False, {"mission_id": "OTHER-MISSION"})

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_release_execution(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
                merge_pr=True,
            )

        self.assertEqual(status_code, 409)
        self.assertEqual(result["status"], "release_coordination_locked")
        self.assertEqual(result["mission_status"], "release_approved")
        update_status.assert_not_called()

    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_run_release_execution_records_failed_merge_packet(self, get_mission, update_vault, update_status):
        mission = dict(MISSION)
        mission["status"] = "release_approved"
        mission["metadata"] = {"review_packet": {"links": {"pr": "https://github.com/org/repo/pull/56"}}}
        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)
        update_status.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        def fake_runner(command, **_kwargs):
            if command[:4] == ["gh", "pr", "merge", "56"]:
                return SimpleNamespace(returncode=1, stdout="", stderr="merge failed")
            if command[:4] == ["gh", "pr", "view", "56"]:
                return SimpleNamespace(returncode=0, stdout=json.dumps({"state": "OPEN"}), stderr="")
            return SimpleNamespace(returncode=1, stdout="", stderr="unexpected command")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_release_execution(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
                merge_pr=True,
                run_subprocess=fake_runner,
            )

        self.assertEqual(status_code, 502)
        self.assertEqual(result["status"], "release_pr_merge_failed")
        statuses = [call.args[1] for call in update_status.call_args_list]
        self.assertEqual(statuses, ["release_in_progress", "blocked"])
        update_vault.assert_called_once()
        release_packet = update_vault.call_args.args[1]["release_packet"]
        self.assertEqual(release_packet["status"], "release_pr_merge_failed")
        self.assertEqual(release_packet["merge_result"]["stderr"], "merge failed")

    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_run_release_execution_classifies_merge_conflict(self, get_mission, update_vault, update_status):
        mission = dict(MISSION)
        mission["status"] = "release_approved"
        mission["metadata"] = {"review_packet": {"links": {"pr": "https://github.com/org/repo/pull/56"}}}
        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)
        update_status.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        def fake_runner(command, **_kwargs):
            if command[:4] == ["gh", "pr", "merge", "56"]:
                return SimpleNamespace(returncode=1, stdout="", stderr="GraphQL: Pull Request has merge conflicts")
            if command[:4] == ["gh", "pr", "view", "56"]:
                return SimpleNamespace(returncode=0, stdout=json.dumps({"state": "OPEN"}), stderr="")
            return SimpleNamespace(returncode=1, stdout="", stderr="unexpected command")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_release_execution(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
                merge_pr=True,
                run_subprocess=fake_runner,
            )

        self.assertEqual(status_code, 502)
        self.assertEqual(result["status"], "release_pr_merge_conflict")
        self.assertEqual(result["failure_class"], "release_conflict")
        release_packet = update_vault.call_args.args[1]["release_packet"]
        self.assertEqual(release_packet["status"], "release_pr_merge_conflict")
        self.assertEqual(release_packet["failure_class"], "release_conflict")
        review_packet = update_vault.call_args.args[1]["review_packet"]
        self.assertEqual(review_packet["review_status"], "release_pr_merge_conflict")
        self.assertIn("rebase", review_packet["recommended_next_action"].lower())

    @patch("modules.charlie.execution_bridge._wait_for_release_verification", return_value={"verified": False, "status": "verify_url_not_provided", "attempts": 1})
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_run_release_execution_reconciles_already_merged_pr(self, get_mission, update_vault, update_status, _verify):
        mission = dict(MISSION)
        mission["status"] = "release_approved"
        mission["metadata"] = {"review_packet": {"links": {"pr": "https://github.com/org/repo/pull/56"}}}
        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)
        update_status.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        def fake_runner(command, **_kwargs):
            if command[:4] == ["gh", "pr", "merge", "56"]:
                return SimpleNamespace(returncode=1, stdout="", stderr="local checkout failed")
            if command[:4] == ["gh", "pr", "view", "56"]:
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps({"state": "MERGED", "mergedAt": "2026-06-30T20:48:26Z", "number": 56}),
                    stderr="",
                )
            return SimpleNamespace(returncode=1, stdout="", stderr="unexpected command")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_release_execution(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
                merge_pr=True,
                run_subprocess=fake_runner,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "release_pr_merged")
        self.assertEqual(result["mission_status"], "merged")
        statuses = [call.args[1] for call in update_status.call_args_list]
        self.assertEqual(statuses, ["release_in_progress", "merged"])
        release_packet = update_vault.call_args.args[1]["release_packet"]
        self.assertTrue(release_packet["merge_result"]["reconciled_as_merged"])
        self.assertTrue(release_packet["merge_result"]["reconciliation"]["merged"])

    @patch("modules.charlie.execution_bridge._wait_for_release_verification", return_value={"verified": False, "status": "verify_url_not_provided", "attempts": 1})
    @patch("modules.charlie.execution_bridge.update_mission_status")
    @patch("modules.charlie.execution_bridge.update_mission_vault")
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_run_release_execution_merges_referenced_pr(self, get_mission, update_vault, update_status, _verify):
        mission = dict(MISSION)
        mission["status"] = "release_approved"
        mission["metadata"] = {"review_packet": {"links": {"pr": "https://github.com/org/repo/pull/56"}}}
        get_mission.return_value = ({"success": True, "status": "ok", "mission": mission}, 200)
        update_status.return_value = ({"success": True, "status": "ok"}, 200)
        update_vault.return_value = ({"success": True, "status": "ok"}, 200)

        def fake_runner(command, **_kwargs):
            self.assertEqual(command[:4], ["gh", "pr", "merge", "56"])
            return SimpleNamespace(returncode=0, stdout="Merged pull request", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            result, status_code = execution_bridge.run_release_execution(
                mission_id="CHARLIE-MISSION-EXEC123",
                output_dir=tmp,
                merge_pr=True,
                run_subprocess=fake_runner,
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "release_pr_merged")
        self.assertEqual(result["mission_status"], "merged")
        statuses = [call.args[1] for call in update_status.call_args_list]
        self.assertEqual(statuses, ["release_in_progress", "merged"])
        update_vault.assert_called_once()
        release_packet = update_vault.call_args.args[1]["release_packet"]
        self.assertIn("deployment_watch", release_packet)

    def test_reviewer_send_back_does_not_require_release_notes(self):
        artifact = {
            "summary": "Two blockers remain.", "recommended_owner_decision": "send_back",
            "changed_files": ["modules/a.py"], "test_evidence": ["focused tests failed"],
            "commands_run": ["python -m unittest focused"], "files_inspected": ["modules/a.py"],
            "vault_sources_used": ["docs/09-vault-brain/README.md"],
            "confidence": 0.99, "confidence_reason": "Current failure reproduced.",
        }
        self.assertTrue(execution_bridge._validate_agent_artifact("reviewer", artifact)["valid"])

    def test_reviewer_approval_still_requires_release_notes(self):
        artifact = {
            "summary": "Ready.", "recommended_owner_decision": "approve_final_release",
            "changed_files": ["modules/a.py"], "test_evidence": ["focused tests passed"],
            "commands_run": ["python -m unittest focused"], "files_inspected": ["modules/a.py"],
            "vault_sources_used": ["docs/09-vault-brain/README.md"],
            "confidence": 0.99, "confidence_reason": "All evidence passed.",
        }
        result = execution_bridge._validate_agent_artifact("reviewer", artifact)
        self.assertFalse(result["valid"])
        self.assertIn("release_notes", result["missing_keys"])


if __name__ == "__main__":
    unittest.main()
