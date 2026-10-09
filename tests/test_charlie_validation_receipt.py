import hashlib
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from modules.charlie.validation_receipt import (
    ValidationReceiptError,
    git_validation_environment,
    VALIDATION_COMMANDS,
    record_validation_receipt,
    sign_validation_receipt,
    validate_validation_receipt,
    write_validation_receipt,
)


SOURCE = "a" * 40
KEY = b"canonical-validation-receipt-test-key-material"


def git_binding():
    common = "/synthetic/common.git"
    private = common + "/worktrees/selected"
    return {"version": "charlie_linked_git_binding_v1", "mounts": [
        {"source": "/synthetic/checkout", "destination": "/source", "read_only": True},
        {"source": common + "/objects", "destination": "/git-common/objects", "read_only": True},
        {"source": common + "/refs", "destination": "/git-common/refs", "read_only": True},
        {"source": private + "/HEAD", "destination": "/git-private/HEAD", "read_only": True},
        {"source": private + "/index", "destination": "/git-private/index", "read_only": True}],
        "environment": {"PATH": "/usr/bin", **git_validation_environment("true", "false")},
        "git_file_sha256": {"/git-private/HEAD": "d"*64, "/git-private/index": "e"*64}}


def evidence(failed=0):
    provider_config = {
        "provider": "docker_engine", "network": "none", "rootfs_read_only": True,
        "source_read_only": True, "cap_drop": ["ALL"], "no_new_privileges": True,
        "user": "65532:65532", "pid_mode": "private", "pids_limit": 256,
        "image_manifest_sha256": "b" * 64, "image_config_sha256": "c" * 64,
        "git_binding": git_binding(),
    }
    return {
        "source_commit": SOURCE,
        "suites": [
            {"name": "focused", "command_sha256": hashlib.sha256(
                VALIDATION_COMMANDS["focused"].encode()).hexdigest(),
             "passed": 12, "failed": failed, "skipped": 1},
            {"name": "proportional", "command_sha256": hashlib.sha256(
                VALIDATION_COMMANDS["proportional"].encode()).hexdigest(),
             "passed": 137, "failed": 0, "skipped": 0},
        ],
        "isolation": {
            "boundary": "disposable_process_boundary", "host_processes_visible": False,
            "outside_boundary_targets": 0, "network_enabled": False,
            "source_read_only": True, "capabilities_dropped": True,
            "unprivileged": True, "image_manifest_sha256": "b" * 64,
            "image_config_sha256": "c" * 64,
            "provider": "docker_engine",
            "provider_actor": "control_tower_isolated_validator_v2",
            "provider_execution_ids": ["1" * 64, "2" * 64],
            "provider_execution_id": hashlib.sha256(json.dumps(
                ["1" * 64, "2" * 64], separators=(",", ":")
            ).encode()).hexdigest(),
            "git_binding": git_binding(),
            "provider_config_sha256": hashlib.sha256(json.dumps(
                provider_config, sort_keys=True, separators=(",", ":")
            ).encode()).hexdigest(),
        },
    }


class ValidationReceiptTests(unittest.TestCase):
    def receipt(self, failed=0):
        return sign_validation_receipt(
            evidence(failed), KEY, validation_id="d" * 32,
        )

    def test_producer_signs_canonical_receipt_accepted_by_validator(self):
        receipt = self.receipt()
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(
            validate_validation_receipt(receipt, SOURCE, KEY)["validation_id"], "d" * 32
        )

    def test_any_signed_or_unsigned_mutation_fails_closed(self):
        mutations = []
        changed = copy.deepcopy(self.receipt())
        changed["suites"][0]["passed"] += 1
        mutations.append(changed)
        extra = copy.deepcopy(self.receipt())
        extra["unexpected"] = True
        mutations.append(extra)
        weak = copy.deepcopy(self.receipt())
        weak["isolation"]["network_enabled"] = True
        mutations.append(weak)
        for receipt in mutations:
            with self.subTest(receipt=receipt), self.assertRaises(ValidationReceiptError):
                validate_validation_receipt(receipt, SOURCE, KEY)

    def test_rejected_receipt_is_signed_evidence_but_never_authorized(self):
        receipt = self.receipt(failed=1)
        self.assertEqual(receipt["status"], "rejected")
        with self.assertRaisesRegex(ValidationReceiptError, "rejected"):
            validate_validation_receipt(receipt, SOURCE, KEY)

    def test_zero_pass_failure_is_preserved_as_signed_non_authorizing_evidence(self):
        candidate = evidence()
        candidate["suites"][0].update({"passed": 0, "failed": 1})
        receipt = sign_validation_receipt(
            candidate, KEY, validation_id="d" * 32
        )
        self.assertEqual(receipt["status"], "rejected")
        with tempfile.TemporaryDirectory() as directory:
            recorded = record_validation_receipt(receipt, directory)
            self.assertIn("validation-identities", recorded["path"])
        with self.assertRaisesRegex(ValidationReceiptError, "rejected"):
            validate_validation_receipt(receipt, SOURCE, KEY)

    def test_all_skipped_suite_is_preserved_as_signed_rejection(self):
        for counts in ({"passed": 0, "failed": 0, "skipped": 1},
                       {"passed": 0, "failed": 0, "skipped": 0}):
            candidate = evidence()
            candidate["suites"][0].update(counts)
            receipt = sign_validation_receipt(
                candidate, KEY, validation_id="d" * 32
            )
            self.assertEqual(receipt["status"], "rejected")
            with tempfile.TemporaryDirectory() as directory:
                record_validation_receipt(receipt, directory)
                with self.assertRaisesRegex(ValidationReceiptError, "already_recorded"):
                    record_validation_receipt(receipt, directory)
            with self.assertRaisesRegex(ValidationReceiptError, "rejected"):
                validate_validation_receipt(receipt, SOURCE, KEY)

    def test_evidence_path_is_create_once_for_pass_or_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            write_validation_receipt(self.receipt(failed=1), path)
            original = path.read_bytes()
            with self.assertRaisesRegex(ValidationReceiptError, "already_recorded"):
                write_validation_receipt(self.receipt(), path)
            self.assertEqual(path.read_bytes(), original)

    def test_canonical_identity_namespace_prevents_pass_rejection_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            rejected = self.receipt(failed=1)
            recorded = record_validation_receipt(rejected, directory)
            self.assertIn("validation-identities", recorded["path"])
            with self.assertRaisesRegex(ValidationReceiptError, "already_recorded"):
                record_validation_receipt(self.receipt(), directory)

    def test_receipt_is_bound_to_exact_source_and_key(self):
        receipt = self.receipt()
        for source, key in (("e" * 40, KEY), (SOURCE, b"other-key-material-that-is-long-enough")):
            with self.subTest(source=source), self.assertRaises(ValidationReceiptError):
                validate_validation_receipt(receipt, source, key)

    def test_required_suite_names_cannot_be_missing_or_renamed(self):
        for suites in (evidence()["suites"][:1], [
            {**evidence()["suites"][0], "name": "arbitrary"}, evidence()["suites"][1]
        ]):
            candidate = evidence()
            candidate["suites"] = suites
            with self.subTest(suites=suites), self.assertRaises(ValidationReceiptError):
                sign_validation_receipt(candidate, KEY, validation_id="d" * 32)

    def test_required_suite_command_digest_cannot_be_substituted(self):
        candidate = evidence()
        candidate["suites"][0]["command_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValidationReceiptError, "schema_invalid"):
            sign_validation_receipt(candidate, KEY, validation_id="d" * 32)

    def test_expiry_is_signed_bounded_and_enforced_at_eligibility(self):
        issued = datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)
        receipt = sign_validation_receipt(
            evidence(), KEY, validation_id="d" * 32,
            issued_at=issued.isoformat().replace("+00:00", "Z"),
            expires_at=(issued + timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
        )
        validate_validation_receipt(receipt, SOURCE, KEY, now="2026-08-21T10:29:59Z")
        with self.assertRaisesRegex(ValidationReceiptError, "expired"):
            validate_validation_receipt(receipt, SOURCE, KEY, now="2026-08-21T10:30:00Z")

    def test_future_and_overlong_receipts_fail_closed(self):
        receipt = sign_validation_receipt(
            evidence(), KEY, validation_id="d" * 32,
            issued_at="2026-08-21T10:10:01Z", expires_at="2026-08-21T10:30:00Z",
        )
        with self.assertRaisesRegex(ValidationReceiptError, "not_yet_valid"):
            validate_validation_receipt(receipt, SOURCE, KEY, now="2026-08-21T10:05:00Z")
        with self.assertRaisesRegex(ValidationReceiptError, "expiry_invalid"):
            sign_validation_receipt(
                evidence(), KEY, validation_id="1" * 32,
                issued_at="2026-08-21T10:00:00Z", expires_at="2026-08-21T10:30:01Z",
            )


    def test_v2_and_stripped_current_binding_never_authorize_v3(self):
        receipt = self.receipt()
        self.assertEqual(receipt["version"], "charlie_isolated_validation_receipt_v3")
        for version in ("charlie_isolated_validation_receipt_v2", "charlie_isolated_validation_receipt_v1"):
            older = copy.deepcopy(receipt); older["version"] = version
            with self.subTest(version=version), self.assertRaisesRegex(ValidationReceiptError, "schema_invalid"):
                validate_validation_receipt(older, SOURCE, KEY)
        stripped = evidence(); stripped["isolation"].pop("git_binding")
        with self.assertRaisesRegex(ValidationReceiptError, "schema_invalid"):
            sign_validation_receipt(stripped, KEY)

    def test_bound_git_evidence_cannot_be_mutated_after_signing(self):
        for field, change in (
            ("mounts", lambda b: b["mounts"][0].update(source="/other/checkout")),
            ("environment", lambda b: b["environment"].update(PATH="/other/bin")),
            ("hashes", lambda b: b["git_file_sha256"].update({"/git-private/index":"f"*64})),
        ):
            receipt = self.receipt(); change(receipt["isolation"]["git_binding"])
            with self.subTest(field=field), self.assertRaises(ValidationReceiptError):
                validate_validation_receipt(receipt,SOURCE,KEY)

    def test_bad_git_contract_refused_before_provider_digest_or_signing(self):
        changes = {
            "writable": lambda b:b["mounts"][0].update(read_only=False),
            "extra_host_mount": lambda b:b["mounts"].append({"source":"/host","destination":"/host","read_only":True}),
            "duplicate": lambda b:b["mounts"].append(dict(b["mounts"][0])),
            "missing": lambda b:b["mounts"].pop(),
            "other_common": lambda b:b["mounts"][2].update(source="/other/refs"),
            "embedded_common": lambda b:b["mounts"][0].update(source="/synthetic"),
            "bad_environment": lambda b:b["environment"].update(GIT_WORK_TREE="/other"),
            "extra_git_environment": lambda b:b["environment"].update(GIT_CONFIG="/host/config"),
            "missing_hash": lambda b:b["git_file_sha256"].pop("/git-private/index"),
        }
        for name, change in changes.items():
            candidate=evidence(); change(candidate["isolation"]["git_binding"])
            # A signer with a key still cannot admit a disallowed isolation contract.
            with self.subTest(fault=name), self.assertRaisesRegex(ValidationReceiptError,"git_binding_invalid"):
                sign_validation_receipt(candidate,KEY)


if __name__ == "__main__":
    unittest.main()
