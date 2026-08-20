import hashlib
import copy
import tempfile
import unittest
from pathlib import Path

from modules.charlie.validation_receipt import (
    ValidationReceiptError,
    VALIDATION_COMMANDS,
    record_validation_receipt,
    sign_validation_receipt,
    validate_validation_receipt,
    write_validation_receipt,
)


SOURCE = "a" * 40
KEY = b"canonical-validation-receipt-test-key-material"


def evidence(failed=0):
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
            "unprivileged": True, "image_sha256": "c" * 64,
        },
    }


class ValidationReceiptTests(unittest.TestCase):
    def receipt(self, failed=0):
        return sign_validation_receipt(
            evidence(failed), KEY, validation_id="d" * 32,
            issued_at="2026-08-20T10:00:00Z",
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
            candidate, KEY, validation_id="d" * 32, issued_at="2026-08-20T10:00:00Z"
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
                candidate, KEY, validation_id="d" * 32, issued_at="2026-08-20T10:00:00Z"
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


if __name__ == "__main__":
    unittest.main()
