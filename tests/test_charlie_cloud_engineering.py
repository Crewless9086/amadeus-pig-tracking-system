"""Pure admission/state boundaries; no provider, model, database or filesystem effects."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import os
import unittest
from unittest.mock import patch

from modules.charlie import cloud_engineering as core
from modules.charlie.native_runner.execution import NativeExecutionError

NOW = datetime(2026, 10, 18, 18, tzinfo=timezone.utc)
REVISION = "b" * 40
TOKEN = "synthetic_engineering_token_" + "a" * 40
OWNER = "owner-admin:synthetic"
INSTANCE = "c" * 32
ACCEPTANCE = "def test_conflicting_duplicate_order():\n    assert False\n"


def manifest():
    return {"generation": "d" * 32, "base_sha": REVISION,
        "worker_revision": REVISION, "api_revision": REVISION,
        "allowed_files": ["modules/pig_weights/feed_data.py"],
        "test_paths": ["tests/test_pig_weights_feed.py"],
        "context_paths": ["modules/pig_weights/feed_data.py", "tests/test_pig_weights_feed.py"],
        "instruction": "Repair the synthetic duplicate conflict; private artifact only.",
        "acceptance_source": ACCEPTANCE,
        "acceptance_sha256": hashlib.sha256(ACCEPTANCE.encode()).hexdigest(),
        "budget_micro_usd": 800000, "max_seconds": 1200}


def mission():
    return {"mission_id": "CORE-SYNTHETIC-ENGINEERING", "status": "paused", "source": "synthetic",
        "raw_text": "Synthetic bounded repair", "title": "Synthetic repair",
        "metadata_json": {"original_history": {"retained": True}}}


def grant():
    row = mission()
    return {"contract": core.CONTRACT, "manifest": manifest(), "state": "issued",
        "mission_id": row["mission_id"], "mission_binding": core.mission_binding(row),
        "owner_binding": "e" * 64, "owner_principal": OWNER,
        "token_sha256": hashlib.sha256(TOKEN.encode()).hexdigest(),
        "issued_at": NOW.isoformat(), "expires_at": (NOW + timedelta(minutes=20)).isoformat(),
        "reservations": [], "reserved_micro_usd": 0, "instance": ""}


def claimed():
    return core.transition(grant(), "claim", {"instance": INSTANCE,
        "worker_revision": REVISION, "worker_service": core.WORKER}, now=NOW)


def reservation(number=1, **changes):
    return {"instance": INSTANCE, "request_id": f"{number:032x}", "request_sha256": hashlib.sha256(f"synthetic-request-{number}".encode()).hexdigest(),
        "input_bytes": 100, "max_tokens": 300, "task": "charlie_native_builder", **changes}


def completion_ready():
    value = claimed()
    for number, role in enumerate(("builder", "security_reviewer", "functional_reviewer"), 1):
        value = core.transition(value, "reserve", reservation(number, task="charlie_native_" + role), now=NOW)
    for stage in ("baseline_verified", "candidate_prepared", "tests_passed", "reviews_passed"):
        value = core.transition(value, "progress", {"instance": INSTANCE, "stage": stage,
            "artifact_sha256": "a" * 64}, now=NOW)
    return value


def sandbox_receipt(*, baseline):
    immutable = "tests/test_core_immutable_acceptance.py::test_conflicting_duplicate_order"
    collected = [immutable] if baseline else [immutable, "tests/test_pig_weights_feed.py::test_feed_regression"]
    outcomes = {node: {"setup": "passed", "call": "failed" if baseline else "passed",
                      "teardown": "passed"} for node in collected}
    return {"returncode": 1 if baseline else 0, "containment": {"verified": True},
        "stdout": "test_conflicting_duplicate_order AssertionError" if baseline else "",
        "completion": {"verified": True, "completed": True, "collected": collected,
            "outcomes": outcomes, "collection_errors": 0, "exitstatus": 1 if baseline else 0,
            "expected_test_ids": [immutable], "expected_passed": not baseline, "all_passed": not baseline}}


def complete_artifact(value):
    diff = "diff --git a/modules/pig_weights/feed_data.py b/modules/pig_weights/feed_data.py\n--- a/modules/pig_weights/feed_data.py\n+++ b/modules/pig_weights/feed_data.py\n@@ -1 +1 @@\n-old\n+new\n"
    binding = {"pr_number": 0, "base_sha": REVISION, "head_sha": REVISION,
        "candidate_diff_sha256": hashlib.sha256(diff.encode()).hexdigest(),
        "changed_files": manifest()["allowed_files"]}
    provider_ids = {item["task"]: "synthetic-provider-" + item["request_id"] for item in value["reservations"]}
    reviews = [{"role": role, "verdict": "APPROVE", "reviewer_identity": "HNR-" + role.lower(),
        "reviewer_provider": "openrouter", "reviewer_model": "openai/gpt-5-mini",
        "reviewer_task": "charlie_native_" + role.lower() + "_reviewer",
        "reviewer_agent_id": provider_ids.get("charlie_native_" + role.lower() + "_reviewer", "unreserved"), "candidate_binding": deepcopy(binding)}
        for role in ("SECURITY", "FUNCTIONAL")]
    return {"contract": core.CONTRACT, "generation": manifest()["generation"], "base_sha": REVISION,
        "mission_id": mission()["mission_id"], "worker_revision": REVISION, "instance": INSTANCE,
        "candidate": {"diff": diff, "changed_files": manifest()["allowed_files"],
            "builder_identity": "HNW-synthetic-builder", "builder_agent_id": provider_ids.get("charlie_native_builder", "unreserved")},
        "candidate_diff": diff, "candidate_binding": binding,
        "baseline": sandbox_receipt(baseline=True),
        "tests": sandbox_receipt(baseline=False), "reviews": reviews,
        "model_calls": [{**{key: item[key] for key in ("request_sha256", "input_bytes", "max_tokens", "task")},
            "strict_budget": True, "attempt_count": 1, "tools_count": 0,
            "provider_request_id": "synthetic-provider-" + item["request_id"],
            "invocation_id": "native-" + item["request_id"]} for item in value["reservations"]],
        "acceptance_sha256": manifest()["acceptance_sha256"],
        "model_reservations": deepcopy(value["reservations"]),
        "reserved_micro_usd": value["reserved_micro_usd"],
        "publications": 0, "farm_actions": 0, "messages": 0, "deployments": 0}


class ManifestTests(unittest.TestCase):
    def test_only_registered_cross_system_documents_are_readable_context(self):
        value = manifest()
        for path in ("docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md",
                     "docs/06-operations/CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md"):
            value["context_paths"].append(path)
        self.assertEqual(core.validate_manifest(value), value)
        for field, path in (("context_paths", "docs/06-operations/OTHER.md"),
                            ("allowed_files", value["context_paths"][-1]),
                            ("test_paths", value["context_paths"][-1])):
            invalid = deepcopy(value); invalid[field].append(path)
            with self.subTest(field=field), self.assertRaises(core.EngineeringRefused):
                core.validate_manifest(invalid)

    def test_valid_manifest_is_copied_and_acceptance_pinned(self):
        original = manifest(); accepted = core.validate_manifest(original)
        self.assertEqual(accepted, original); accepted["allowed_files"].append("tests/other.py")
        self.assertEqual(original["allowed_files"], ["modules/pig_weights/feed_data.py"])

    def test_revision_deadline_budget_and_shape_fail_closed(self):
        mutations = [("api_revision", "a" * 40), ("worker_revision", "a" * 40),
            ("generation", "bad"), ("max_seconds", True), ("max_seconds", 299),
            ("max_seconds", 3601), ("budget_micro_usd", 99999), ("budget_micro_usd", 800001),
            ("budget_micro_usd", True), ("acceptance_source", ACCEPTANCE + "# altered"),
            ("instruction", "")]
        for key, value in mutations:
            with self.subTest(key=key, value=value), self.assertRaises(core.EngineeringRefused):
                changed = manifest(); changed[key] = value; core.validate_manifest(changed)
        changed = manifest(); changed["publish"] = True
        with self.assertRaises(core.EngineeringRefused): core.validate_manifest(changed)

    def test_path_traversal_hidden_paths_outside_scope_and_duplicates_refused(self):
        for field in ("allowed_files", "test_paths", "context_paths"):
            for paths in ([], ["../outside.py"], ["/tmp/file.py"], ["modules/charlie/cloud_engineering.py"],
                    ["tests/.secret.py"], ["tests/test_a.py", "tests/test_a.py"]):
                with self.subTest(field=field, paths=paths), self.assertRaises((core.EngineeringRefused, ValueError, NativeExecutionError)):
                    changed = manifest(); changed[field] = paths; core.validate_manifest(changed)
        changed = manifest(); changed["context_paths"] = ["tests/test_pig_weights_feed.py"]
        with self.assertRaisesRegex(core.EngineeringRefused, "context_scope"): core.validate_manifest(changed)

    def test_registered_cross_system_documents_are_context_only(self):
        registered = ["docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md",
                      "docs/06-operations/CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md"]
        value = manifest(); value["context_paths"] += registered
        self.assertEqual(core.validate_manifest(value)["context_paths"], value["context_paths"])
        for path in registered:
            for field in ("allowed_files", "test_paths"):
                changed = manifest(); changed[field] = [path]
                with self.subTest(path=path, field=field), self.assertRaises(core.EngineeringRefused):
                    core.validate_manifest(changed)
        for path in ("docs/01-architecture/OTHER.md", "docs/06-operations/OTHER.md",
                     "docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md/extra"):
            changed = manifest(); changed["context_paths"].append(path)
            with self.subTest(unregistered=path), self.assertRaises(core.EngineeringRefused):
                core.validate_manifest(changed)

    def test_read_only_public_view_excludes_authentication_secrets(self):
        for owner in (False, True):
            public = core._public(grant(), owner=owner)["grant"]
            self.assertNotIn("token_sha256", public); self.assertNotIn("owner_binding", public)
            if not owner: self.assertNotIn("mission_binding", public)


class StateTests(unittest.TestCase):
    def test_exact_instance_claim_is_once_only_and_original_unmodified(self):
        original = grant(); current = claimed()
        self.assertEqual(original["state"], "issued"); self.assertEqual(current["instance"], INSTANCE)
        with self.assertRaisesRegex(core.EngineeringRefused, "claim_already_consumed"):
            core.transition(current, "claim", {"instance": INSTANCE, "worker_revision": REVISION,
                "worker_service": core.WORKER}, now=NOW)

    def test_claim_worker_revision_service_and_shape(self):
        payload = {"instance": INSTANCE, "worker_revision": REVISION, "worker_service": core.WORKER}
        for key, value in (("worker_revision", "a" * 40), ("worker_service", core.API), ("instance", "short")):
            with self.subTest(key=key), self.assertRaises(core.EngineeringRefused):
                core.transition(grant(), "claim", dict(payload, **{key:value}), now=NOW)

    def test_eight_reservations_are_charged_once_and_never_refunded_on_block(self):
        value = claimed()
        for n in range(1, 9): value = core.transition(value, "reserve", reservation(n), now=NOW)
        self.assertEqual(value["reserved_micro_usd"], 800000); self.assertEqual(len(value["reservations"]), 8)
        for payload in (reservation(8), reservation(9)):
            with self.assertRaises(core.EngineeringRefused): core.transition(value, "reserve", payload, now=NOW)
        blocked = core.transition(value, "block", {"instance": INSTANCE, "reason": "synthetic_failure"}, now=NOW)
        self.assertEqual(blocked["reservations"], value["reservations"])
        self.assertEqual(blocked["reserved_micro_usd"], 800000)

    def test_small_budget_and_request_bounds(self):
        bound = core.transition(claimed(), "reserve", reservation(input_bytes=340000), now=NOW)
        self.assertEqual(bound["reservations"][0]["input_bytes"], 340000)
        value = claimed(); value["manifest"]["budget_micro_usd"] = 100000
        value = core.transition(value, "reserve", reservation(), now=NOW)
        with self.assertRaisesRegex(core.EngineeringRefused, "model_budget_exhausted"):
            core.transition(value, "reserve", reservation(2), now=NOW)
        for changes in ({"max_tokens":0}, {"max_tokens":6001}, {"max_tokens":True},
                {"input_bytes":340001}, {"input_bytes":True}, {"task":"arbitrary_model"},
                {"request_id":"bad"}, {"instance":"d"*32}):
            with self.subTest(changes=changes), self.assertRaises(core.EngineeringRefused):
                core.transition(claimed(), "reserve", reservation(**changes), now=NOW)

    def test_progress_cannot_skip_or_replay_a_stage(self):
        value = claimed()
        for stage in ("tests_passed", "claimed", "artifact_ready"):
            with self.subTest(stage=stage), self.assertRaises(core.EngineeringRefused):
                core.transition(value, "progress", {"instance":INSTANCE, "stage":stage,
                    "artifact_sha256":"a"*64}, now=NOW)
        for stage in ("baseline_verified", "candidate_prepared", "tests_passed", "reviews_passed"):
            value = core.transition(value, "progress", {"instance":INSTANCE, "stage":stage,
                "artifact_sha256":"a"*64}, now=NOW)
        self.assertEqual(value["state"], "reviews_passed")

    def test_active_validator_rechecks_owner_mission_source_deadline_and_terminal(self):
        for change in ("owner", "mission", "api", "expiry", *sorted(core.TERMINAL)):
            value = grant(); row = mission(); binding = "e"*64; revision = REVISION
            if change == "owner": binding = "f"*64
            elif change == "mission": row["raw_text"] += " changed"
            elif change == "api": revision = "a"*40
            elif change == "expiry": value["expires_at"] = NOW.isoformat()
            else: value["state"] = change
            with self.subTest(change=change), self.assertRaises(core.EngineeringRefused):
                core.validate_active(row, value, NOW, api_revision=revision, binding=binding)

    def test_completion_requires_reviews_and_artifact_integrity(self):
        value = claimed(); artifact = complete_artifact(value)
        with self.assertRaisesRegex(core.EngineeringRefused, "reviews_required"):
            core.transition(value, "complete", {"instance":INSTANCE, "artifact":artifact,
                "artifact_sha256":core.digest(artifact)}, now=NOW)
        value["state"] = "reviews_passed"
        with self.assertRaisesRegex(core.EngineeringRefused, "artifact_digest"):
            core.transition(value, "complete", {"instance":INSTANCE, "artifact":artifact,
                "artifact_sha256":"0"*64}, now=NOW)

    def test_valid_final_artifact_is_copied_and_bound_to_private_candidate(self):
        value = completion_ready(); artifact = complete_artifact(value)
        done = core.transition(value, "complete", {"instance":INSTANCE, "artifact":artifact,
            "artifact_sha256":core.digest(artifact)}, now=NOW)
        self.assertEqual(done["state"], "artifact_ready")
        self.assertEqual(done["artifact_sha256"], core.digest(artifact))
        self.assertEqual(value["state"], "reviews_passed")

    def test_completion_rejects_false_scope_review_containment_and_spend(self):
        def mutate(a, change):
            if change == "scope": a["candidate"]["changed_files"] = ["modules/charlie/mission_store.py"]
            elif change == "diff": a["candidate_diff"] += "tamper"
            elif change == "review_binding": a["reviews"][0]["candidate_binding"]["head_sha"] = "a"*40
            elif change == "acceptance": a["acceptance_sha256"] = "0"*64
            elif change == "containment": a["tests"]["containment"]["verified"] = False
            elif change == "publication": a["publications"] = 1
            elif change == "refund": a["reserved_micro_usd"] = -1
            elif change == "worker": a["worker_revision"] = "a"*40
            elif change == "mission": a["mission_id"] = "OTHER"
            elif change == "instance": a["instance"] = "a"*32
            elif change == "review_provider": a["reviews"][0]["reviewer_provider"] = "other"
            elif change == "review_role": a["reviews"][1]["role"] = "SECURITY"
            elif change == "same_reviewer":
                a["reviews"][1]["reviewer_identity"] = a["reviews"][0]["reviewer_identity"]
                a["reviews"][1]["reviewer_agent_id"] = a["reviews"][0]["reviewer_agent_id"]
            elif change == "bool_returncode": a["tests"]["returncode"] = False
        value = completion_ready()
        for change in ("scope","diff","review_binding","acceptance","containment","publication",
                       "refund","worker","mission","instance","review_provider","review_role",
                       "same_reviewer","bool_returncode"):
            artifact = complete_artifact(value); mutate(artifact, change)
            with self.subTest(change=change), self.assertRaises(core.EngineeringRefused):
                core.transition(value, "complete", {"instance":INSTANCE, "artifact":artifact,
                    "artifact_sha256":core.digest(artifact)}, now=NOW)


    def test_completion_requires_actual_immutable_test_execution(self):
        value = completion_ready()
        for label in ("missing", "unverified", "unfinished", "empty", "missing_immutable", "skipped",
                      "failed", "wrong_ids", "collection_error", "false_success", "baseline_setup_only",
                      "baseline_passed", "wrong_exit", "extra_outcome"):
            artifact = complete_artifact(value)
            receipt = artifact["baseline"] if label.startswith("baseline_") else artifact["tests"]
            c = receipt["completion"]; immutable = c["expected_test_ids"][0]
            if label == "missing": receipt.pop("completion")
            elif label == "unverified": c["verified"] = False
            elif label == "unfinished": c["completed"] = False
            elif label == "empty": c.update(collected=[], outcomes={})
            elif label == "missing_immutable": c["collected"].remove(immutable); c["outcomes"].pop(immutable)
            elif label in ("skipped", "failed"): c["outcomes"][immutable]["call"] = label
            elif label == "wrong_ids": c["expected_test_ids"] = []
            elif label == "collection_error": c["collection_errors"] = 1
            elif label == "false_success": c["expected_passed"] = False
            elif label == "baseline_setup_only": c["outcomes"][immutable] = {"setup": "failed"}
            elif label == "baseline_passed": c["outcomes"][immutable]["call"] = "passed"
            elif label == "wrong_exit": c["exitstatus"] = True
            elif label == "extra_outcome": c["outcomes"]["tests/test_other.py::test_fake"] = {"call": "passed"}
            with self.subTest(label=label), self.assertRaises(core.EngineeringRefused):
                core.transition(value, "complete", {"instance": INSTANCE, "artifact": artifact,
                    "artifact_sha256": core.digest(artifact)}, now=NOW)

    def test_model_evidence_must_match_all_three_durable_role_reservations(self):
        value = completion_ready()
        for label in ("missing", "duplicate_hash", "wrong_hash", "strict", "retry", "tool", "size",
                      "tokens", "role", "missing_provider_id", "invalid_provider_id", "duplicate_provider_id",
                      "shared_invocation", "wrong_invocation", "review_agent", "builder_agent", "review_task"):
            artifact = complete_artifact(value); calls = artifact["model_calls"]
            if label == "missing": calls.pop()
            elif label == "duplicate_hash": calls[1]["request_sha256"] = calls[0]["request_sha256"]
            elif label == "wrong_hash": calls[0]["request_sha256"] = "0" * 64
            elif label == "strict": calls[0]["strict_budget"] = False
            elif label == "retry": calls[0]["attempt_count"] = 2
            elif label == "tool": calls[0]["tools_count"] = 1
            elif label == "size": calls[0]["input_bytes"] += 1
            elif label == "tokens": calls[0]["max_tokens"] += 1
            elif label == "role": calls[1]["task"] = "charlie_native_builder"
            elif label == "missing_provider_id": calls[0].pop("provider_request_id")
            elif label == "invalid_provider_id": calls[0]["provider_request_id"] = "private\nvalue"
            elif label == "duplicate_provider_id": calls[1]["provider_request_id"] = calls[0]["provider_request_id"]
            elif label == "shared_invocation": calls[1]["invocation_id"] = calls[0]["invocation_id"]
            elif label == "wrong_invocation": calls[1]["invocation_id"] = "native-not-an-identity"
            elif label == "review_agent": artifact["reviews"][0]["reviewer_agent_id"] = "unrelated-provider-call"
            elif label == "builder_agent": artifact["candidate"]["builder_agent_id"] = "unrelated-provider-call"
            elif label == "review_task": artifact["reviews"][0]["reviewer_task"] = "charlie_native_functional_reviewer"
            with self.subTest(label=label), self.assertRaises(core.EngineeringRefused):
                core.transition(value, "complete", {"instance": INSTANCE, "artifact": artifact,
                    "artifact_sha256": core.digest(artifact)}, now=NOW)



if __name__ == "__main__": unittest.main()
