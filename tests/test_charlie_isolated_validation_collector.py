import json
import tempfile
import unittest
from pathlib import Path

from modules.charlie.isolated_validation_collector import collect_docker_validation_evidence
from modules.charlie.validation_receipt import ValidationReceiptError


SOURCE = "a" * 40
IMAGE_ID = "b" * 64


class DockerProvider:
    def __init__(self, source, *, weaken=None, failed=False, repo_digest=True):
        self.source = Path(source).resolve()
        self.weaken = weaken
        self.failed = failed
        self.repo_digest = repo_digest
        self.created = 0
        self.commands = []

    def __call__(self, command, allow_failure=False):
        self.commands.append(command)
        if command[:3] == ["docker", "image", "inspect"]:
            return json.dumps([{"Id": f"sha256:{IMAGE_ID}",
                                "RepoDigests": [command[3]] if self.repo_digest else []}])
        if command[:2] == ["docker", "create"]:
            self.created += 1
            return str(self.created) * 64
        if command[:2] == ["docker", "inspect"]:
            create = next(row for row in reversed(self.commands) if row[:2] == ["docker", "create"])
            row = {
                "Image": f"sha256:{IMAGE_ID}",
                "HostConfig": {"NetworkMode": "none", "ReadonlyRootfs": True,
                               "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges"],
                               "PidMode": "", "PidsLimit": 256},
                "Config": {"User": "65532:65532", "WorkingDir": "/source",
                           "Entrypoint": None, "Cmd": ["sh", "-lc", create[-1]]},
                "Mounts": [{"Destination": "/source", "RW": False,
                            "Source": str(self.source)}],
            }
            if self.weaken:
                self.weaken(row)
            return json.dumps([row])
        if command[:3] == ["docker", "start", "--attach"]:
            return ("Ran 12 tests in 0.2s\n\nFAILED (failures=1)\n", 1) if self.failed else (
                "Ran 12 tests in 0.2s\n\nOK\n", 0)
        if command[:3] == ["docker", "rm", "--force"]:
            return ("", 0) if allow_failure else ""
        raise AssertionError(command)


class IsolatedCollectorTests(unittest.TestCase):
    def test_provider_attestation_is_collected_not_caller_asserted(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = DockerProvider(directory)
            result = collect_docker_validation_evidence(
                directory, SOURCE, "core-validator@sha256:" + IMAGE_ID, runner=provider
            )
        self.assertEqual(result["source_commit"], SOURCE)
        self.assertEqual([row["failed"] for row in result["suites"]], [0, 0])
        self.assertEqual(result["isolation"]["provider"], "docker_engine")
        self.assertEqual(result["isolation"]["image_sha256"], IMAGE_ID)
        self.assertEqual(len(result["isolation"]["provider_execution_id"]), 64)
        self.assertEqual(result["isolation"]["provider_execution_ids"], ["1" * 64, "2" * 64])
        self.assertEqual(sum(1 for row in provider.commands if row[:2] == ["docker", "create"]), 2)
        creates = [row for row in provider.commands if row[:2] == ["docker", "create"]]
        self.assertTrue(all(f'git rev-parse HEAD)" = "{SOURCE}"' in row[-1] for row in creates))

    def test_weakened_provider_boundary_fails_closed_and_removes_container(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = DockerProvider(directory, weaken=lambda row: row["HostConfig"].update(
                {"NetworkMode": "default"}))
            with self.assertRaisesRegex(ValidationReceiptError, "attestation_invalid"):
                collect_docker_validation_evidence(
                    directory, SOURCE, "core-validator@sha256:" + IMAGE_ID, runner=provider
                )
        self.assertTrue(any(row[:3] == ["docker", "rm", "--force"] for row in provider.commands))

    def test_failed_provider_suite_is_preserved_as_rejected_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            result = collect_docker_validation_evidence(
                directory, SOURCE, "core-validator@sha256:" + IMAGE_ID,
                runner=DockerProvider(directory, failed=True),
            )
        self.assertEqual([row["failed"] for row in result["suites"]], [1, 1])
        self.assertEqual([row["passed"] for row in result["suites"]], [11, 11])

    def test_mutable_or_mismatched_image_reference_fails_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = DockerProvider(directory)
            with self.assertRaisesRegex(ValidationReceiptError, "digest_reference_required"):
                collect_docker_validation_evidence(directory, SOURCE, "core-validator:latest",
                                                   runner=provider)
            with self.assertRaisesRegex(ValidationReceiptError, "image_mismatch"):
                provider = DockerProvider(directory, repo_digest=False)
                collect_docker_validation_evidence(
                    directory, SOURCE, "core-validator@sha256:" + "c" * 64, runner=provider
                )
        self.assertFalse(any(row[:2] == ["docker", "create"] for row in provider.commands))


if __name__ == "__main__":
    unittest.main()
