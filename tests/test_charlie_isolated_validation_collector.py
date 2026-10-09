import json
import hashlib
import os
import subprocess
import shutil
import zlib
import tempfile
import unittest
from pathlib import Path

from modules.charlie.isolated_validation_collector import (
    collect_docker_validation_evidence, _mount_source_identity, _source_binding,
)
from modules.charlie.validation_receipt import ValidationReceiptError


SOURCE = "a" * 40
IMAGE_ID = "b" * 64
MANIFEST_DIGEST = "c" * 64


class DockerProvider:
    def __init__(self, source, *, weaken=None, failed=False, repo_digest=True, linked=True):
        fixture = Path(source).resolve()
        self.source = fixture / "selected-checkout"
        self.source.mkdir(parents=True, exist_ok=True)
        self.common = fixture / "common.git" if linked else self.source / ".git"
        self.private = self.common / "worktrees" / "fixture" if linked else self.common
        self.private.mkdir(parents=True, exist_ok=True)
        for name in ("objects", "refs"):
            (self.common / name).mkdir(exist_ok=True)
        (self.private / "HEAD").write_text(SOURCE + "\n")
        (self.private / "index").write_bytes(b"fake index; Docker is not executed")
        if linked:
            (self.source / ".git").write_text("gitdir: " + str(self.private))
        self.head = SOURCE
        self.dirty = ""
        self.image_env = ["PATH=/usr/local/bin:/usr/bin"]
        self.weaken = weaken
        self.failed = failed
        self.repo_digest = repo_digest
        self.created = 0
        self.commands = []

    def __call__(self, command, allow_failure=False):
        self.commands.append(command)
        if command[0] == "git":
            if command[-3:] == ["--path-format=absolute", "--git-dir", "--git-common-dir"]:
                return str(self.private) + "\n" + str(self.common) + "\n"
            if command[-2:] == ["rev-parse", "HEAD"]:
                return self.head + "\n"
            if "status" in command:
                return self.dirty
            if command[-3:] == ["config", "--get", "core.autocrlf"]:
                return ("true\n", 0)
            if command[-3:] == ["config", "--get", "core.filemode"]:
                return ("false\n", 0)
            raise AssertionError(command)
        if command[:3] == ["docker", "image", "inspect"]:
            return json.dumps([{"Id": f"sha256:{IMAGE_ID}",
                                "RepoDigests": [command[3]] if self.repo_digest else [],
                                "Config": {"Env": self.image_env}}])
        if command[:2] == ["docker", "create"]:
            self.created += 1
            return str(self.created) * 64
        if command[:2] == ["docker", "inspect"]:
            create = next(row for row in reversed(self.commands) if row[:2] == ["docker", "create"])
            row = {
                "Image": f"sha256:{IMAGE_ID}",
                "HostConfig": {"NetworkMode": "none", "ReadonlyRootfs": True,
                               "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges"],
                               "PidMode": "", "PidsLimit": 256,
                               "Tmpfs": {"/tmp": "rw,noexec,nosuid,size=64m"}},
                "Config": {"User": "65532:65532", "WorkingDir": "/source",
                           "Entrypoint": None, "Cmd": ["sh", "-lc", create[-1]],
                           "Env": self.image_env + [create[i+1] for i,v in enumerate(create) if v=="--env"]},
                "Mounts": [],
            }
            for i, value in enumerate(create):
                if value == "--mount":
                    fields = dict(item.split("=", 1) for item in create[i+1].split(",") if "=" in item)
                    row["Mounts"].append({"Type": "bind", "Destination": fields["dst"],
                        "RW": False, "Source": fields["src"]})
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
                provider.source, SOURCE, "core-validator@sha256:" + MANIFEST_DIGEST, runner=provider
            )
        self.assertEqual(result["source_commit"], SOURCE)
        self.assertEqual([row["failed"] for row in result["suites"]], [0, 0])
        self.assertEqual(result["isolation"]["provider"], "docker_engine")
        self.assertEqual(result["isolation"]["image_manifest_sha256"], MANIFEST_DIGEST)
        self.assertEqual(result["isolation"]["image_config_sha256"], IMAGE_ID)
        self.assertEqual(len(result["isolation"]["provider_execution_id"]), 64)
        self.assertEqual(result["isolation"]["provider_execution_ids"], ["1" * 64, "2" * 64])
        self.assertEqual(sum(1 for row in provider.commands if row[:2] == ["docker", "create"]), 2)
        creates = [row for row in provider.commands if row[:2] == ["docker", "create"]]
        self.assertTrue(all('source_head=$(git rev-parse HEAD)' in row[-1] for row in creates))

    def test_weakened_provider_boundary_fails_closed_and_removes_container(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = DockerProvider(directory, weaken=lambda row: row["HostConfig"].update(
                {"NetworkMode": "default"}))
            with self.assertRaisesRegex(ValidationReceiptError, "attestation_invalid"):
                collect_docker_validation_evidence(
                    provider.source, SOURCE, "core-validator@sha256:" + MANIFEST_DIGEST, runner=provider
                )
        self.assertTrue(any(row[:3] == ["docker", "rm", "--force"] for row in provider.commands))

    def test_failed_provider_suite_is_preserved_as_rejected_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = DockerProvider(directory, failed=True)
            result = collect_docker_validation_evidence(
                provider.source, SOURCE, "core-validator@sha256:" + MANIFEST_DIGEST,
                runner=provider,
            )
        self.assertEqual([row["failed"] for row in result["suites"]], [1, 1])
        self.assertEqual([row["passed"] for row in result["suites"]], [11, 11])

    def test_mutable_or_mismatched_image_reference_fails_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = DockerProvider(directory)
            with self.assertRaisesRegex(ValidationReceiptError, "digest_reference_required"):
                collect_docker_validation_evidence(provider.source, SOURCE, "core-validator:latest",
                                                   runner=provider)
            with self.assertRaisesRegex(ValidationReceiptError, "image_mismatch"):
                provider = DockerProvider(directory, repo_digest=False)
                collect_docker_validation_evidence(
                    provider.source, SOURCE, "core-validator@sha256:" + "c" * 64, runner=provider
                )
        self.assertFalse(any(row[:2] == ["docker", "create"] for row in provider.commands))


    def test_linked_metadata_is_explicit_read_only_and_excludes_host_config(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "checkout"; source.mkdir()
            provider = DockerProvider(source, linked=True)
            (provider.common / "config").write_text("sensitive host configuration not mounted")
            (provider.common / "packed-refs").write_text("# packed-refs fixture")
            collect_docker_validation_evidence(provider.source, SOURCE,
                "core-validator@sha256:" + MANIFEST_DIGEST, runner=provider)
            creates = [x for x in provider.commands if x[:2] == ["docker", "create"]]
            for command in creates:
                mounts = [command[i+1] for i,x in enumerate(command) if x == "--mount"]
                self.assertEqual(len(mounts), 6)
                self.assertTrue(all(x.endswith(",readonly") for x in mounts))
                self.assertFalse(any("/config," in x.replace("\\", "/") for x in mounts))
                for value in ("GIT_DIR=/git-private", "GIT_COMMON_DIR=/git-common",
                              "GIT_WORK_TREE=/source", "GIT_OPTIONAL_LOCKS=0",
                              "GIT_CONFIG_VALUE_1=true", "GIT_CONFIG_VALUE_2=false"):
                    self.assertIn(value, command)
                self.assertIn('git status --porcelain', command[-1])

    def test_embedded_git_directory_is_refused_before_provider_access(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = DockerProvider(directory, linked=False)
            with self.assertRaisesRegex(ValidationReceiptError, "linked_checkout_required"):
                collect_docker_validation_evidence(provider.source, SOURCE,
                    "core-validator@sha256:"+MANIFEST_DIGEST, runner=provider)
            self.assertEqual(provider.commands, [])

    def test_collected_provider_evidence_signs_and_validates_without_fixture_translation(self):
        from modules.charlie.validation_receipt import sign_validation_receipt, validate_validation_receipt
        with tempfile.TemporaryDirectory() as directory:
            provider = DockerProvider(directory)
            evidence = collect_docker_validation_evidence(provider.source, SOURCE,
                "core-validator@sha256:"+MANIFEST_DIGEST, runner=provider)
            key=b"collector-integration-synthetic-key-32-bytes"
            receipt=sign_validation_receipt(evidence,key,validation_id="a"*32)
            self.assertEqual(validate_validation_receipt(receipt,SOURCE,key)["validation_id"],"a"*32)
            self.assertEqual(receipt["isolation"]["git_binding"],evidence["isolation"]["git_binding"])
            receipt["isolation"]["git_binding"]["mounts"][0]["read_only"]=False
            with self.assertRaises(ValidationReceiptError):validate_validation_receipt(receipt,SOURCE,key)

    def test_container_git_failures_cannot_reach_fixed_suite(self):
        shell = shutil.which("sh")
        if shell is None and os.name == "nt":
            git = shutil.which("git")
            candidate = Path(git).parent.parent / "bin" / "sh.exe" if git else Path("missing")
            shell = str(candidate) if candidate.is_file() else None
        self.assertIsNotNone(shell, "Git qualification requires a POSIX shell")
        with tempfile.TemporaryDirectory() as directory:
            provider = DockerProvider(directory)
            collect_docker_validation_evidence(provider.source, SOURCE,
                "core-validator@sha256:" + MANIFEST_DIGEST, runner=provider)
            command = next(c[-1] for c in provider.commands if c[:2] == ["docker", "create"])
            # Exercise the actual collected shell gate with a harmless suite sentinel.
            gate, fixed_suite = command.rsplit(" && exec ", 1)
            self.assertTrue(fixed_suite.startswith("python -B -m unittest "))
            for name, head, head_rc, dirty, status_rc, reaches in (
                ("clean", SOURCE, 0, "", 0, True),
                ("head_failure_empty", "", 1, "", 0, False),
                ("head_failure_matching_output", SOURCE, 1, "", 0, False),
                ("wrong_head", "b" * 40, 0, "", 0, False),
                ("status_failure_empty", SOURCE, 0, "", 1, False),
                ("dirty", SOURCE, 0, " M tracked.py", 0, False),
            ):
                script = ("git() { case \"$1\" in rev-parse) printf '%s' '" + head +
                    "'; return " + str(head_rc) + ";; status) printf '%s' '" + dirty +
                    "'; return " + str(status_rc) + ";; *) return 99;; esac; }; " +
                    gate + " && printf suite_reached")
                environment = {"PATH": os.defpath, "TMPDIR": directory}
                if os.name == "nt": environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
                result = subprocess.run([shell, "-c", script], cwd=directory,
                    env=environment, text=True, capture_output=True, timeout=10)
                with self.subTest(case=name):
                    self.assertEqual(result.stdout, "suite_reached" if reaches else "")
                    self.assertEqual(result.returncode == 0, reaches)

    def test_host_source_mismatch_or_dirt_stops_before_docker(self):
        for head, dirty in (("d"*40, ""), (SOURCE, " M tracked.py")):
            with self.subTest(head=head, dirty=bool(dirty)), tempfile.TemporaryDirectory() as directory:
                provider = DockerProvider(directory); provider.head=head; provider.dirty=dirty
                with self.assertRaisesRegex(ValidationReceiptError, "source_not_exact_clean"):
                    collect_docker_validation_evidence(provider.source, SOURCE,
                        "core-validator@sha256:" + MANIFEST_DIGEST, runner=provider)
                self.assertFalse(any(x[0] == "docker" for x in provider.commands))

    def test_missing_index_or_external_objects_fail_closed(self):
        for fault in ("index", "alternates", "grafts", "reftable"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                provider = DockerProvider(directory)
                if fault == "index":
                    (provider.private / "index").unlink()
                else:
                    target = provider.common / {"alternates":"objects/info/alternates", "grafts":"info/grafts", "reftable":"reftable"}[fault]
                    target.parent.mkdir(parents=True, exist_ok=True); target.write_text("outside")
                with self.assertRaises(ValidationReceiptError):
                    collect_docker_validation_evidence(provider.source, SOURCE,
                        "core-validator@sha256:" + MANIFEST_DIGEST, runner=provider)
                self.assertFalse(any(x[0] == "docker" for x in provider.commands))

    def test_each_mount_and_environment_boundary_is_attested_before_start(self):
        faults = {
            "metadata_writable": lambda r: r["Mounts"][1].update(RW=True),
            "metadata_wrong_source": lambda r: r["Mounts"][1].update(Source="/unrelated"),
            "metadata_missing": lambda r: r["Mounts"].pop(),
            "extra_mount": lambda r: r["Mounts"].append({"Type":"bind","Destination":"/host","Source":"/","RW":False}),
            "duplicate_mount": lambda r: r["Mounts"].append(dict(r["Mounts"][1])),
            "missing_env": lambda r: r["Config"]["Env"].pop(),
            "extra_env": lambda r: r["Config"]["Env"].append("GIT_CONFIG=/outside"),
            "duplicate_env": lambda r: r["Config"]["Env"].append("GIT_DIR=/git-private"),
            "wrong_env": lambda r: r["Config"]["Env"].append("GIT_WORK_TREE=/other"),
            "tmpfs": lambda r: r["HostConfig"].update(Tmpfs={"/tmp":"rw,exec"}),
            "privileged": lambda r: r["HostConfig"].update(Privileged=True),
            "extra_cap": lambda r: r["HostConfig"].update(CapAdd=["SYS_ADMIN"]),
        }
        for name, fault in faults.items():
            with self.subTest(fault=name), tempfile.TemporaryDirectory() as directory:
                provider = DockerProvider(directory, weaken=fault)
                with self.assertRaises(ValidationReceiptError):
                    collect_docker_validation_evidence(provider.source, SOURCE,
                        "core-validator@sha256:" + MANIFEST_DIGEST, runner=provider)
                self.assertFalse(any(x[:2] == ["docker", "start"] for x in provider.commands))
                self.assertTrue(any(x[:3] == ["docker", "rm", "--force"] for x in provider.commands))

    def test_mount_delimiter_in_source_path_is_refused_before_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source,not-an-option"; source.mkdir()
            provider = DockerProvider(source)
            with self.assertRaisesRegex(ValidationReceiptError, "git_path_invalid"):
                collect_docker_validation_evidence(provider.source, SOURCE,
                    "core-validator@sha256:" + MANIFEST_DIGEST, runner=provider)
            self.assertFalse(any(x[0] == "docker" for x in provider.commands))

    def test_unexpected_image_git_environment_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = DockerProvider(directory); provider.image_env.append("GIT_CONFIG=/host/config")
            with self.assertRaisesRegex(ValidationReceiptError, "image_environment_invalid"):
                collect_docker_validation_evidence(provider.source, SOURCE,
                    "core-validator@sha256:" + MANIFEST_DIGEST, runner=provider)
            self.assertFalse(any(x[:2] == ["docker", "create"] for x in provider.commands))

    def test_windows_docker_bridge_paths_are_exact_not_suffix_matches(self):
        expected = _mount_source_identity("C:/Amadeus/repo/.git/objects")
        for value in ("C:\\Amadeus\\repo\\.git\\objects", "/host_mnt/c/Amadeus/repo/.git/objects",
                      "/run/desktop/mnt/host/c/Amadeus/repo/.git/objects"):
            with self.subTest(value=value): self.assertEqual(_mount_source_identity(value), expected)
        for value in ("/host_mnt/d/Amadeus/repo/.git/objects", "/other/c/Amadeus/repo/.git/objects",
                      "C:/Amadeus/repo/../other/.git/objects", "relative/path"):
            with self.subTest(value=value): self.assertNotEqual(_mount_source_identity(value), expected)

    def test_real_git_native_view_ignores_unreachable_windows_marker_but_detects_dirt(self):
        # Synthetic loose Git objects; no registered checkout, Docker or network.
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory); source=base/"source"; private=base/"private"; common=base/"common"
            source.mkdir(); private.mkdir(); (common/"objects").mkdir(parents=True); (common/"refs").mkdir()
            (source/".git").write_text("gitdir: C:/unreachable/windows/metadata")
            payload=b"tracked content\n"; (source/"tracked.txt").write_bytes(payload.replace(b"\n", b"\r\n"))
            def obj(kind,data):
                encoded=kind.encode()+b" "+str(len(data)).encode()+b"\0"+data
                digest=hashlib.sha1(encoded).hexdigest(); path=common/"objects"/digest[:2]/digest[2:]
                path.parent.mkdir(exist_ok=True); path.write_bytes(zlib.compress(encoded)); return digest
            blob=obj("blob",payload)
            tree=obj("tree",b"100644 tracked.txt\0"+bytes.fromhex(blob))
            commit=obj("commit",("tree "+tree+"\nauthor Fixture <fixture@example.invalid> 1 +0000\ncommitter Fixture <fixture@example.invalid> 1 +0000\n\nfixture\n").encode())
            (private/"HEAD").write_text(commit+"\n")
            env={k:v for k,v in os.environ.items() if not k.upper().startswith("GIT_")}
            env.update(GIT_DIR=str(private),GIT_COMMON_DIR=str(common),GIT_WORK_TREE=str(source),
                GIT_CONFIG_NOSYSTEM="1",GIT_CONFIG_GLOBAL=os.devnull,GIT_OPTIONAL_LOCKS="0",
                GIT_CONFIG_COUNT="3",GIT_CONFIG_KEY_0="safe.directory",GIT_CONFIG_VALUE_0=str(source),
                GIT_CONFIG_KEY_1="core.filemode",GIT_CONFIG_VALUE_1="false",
                GIT_CONFIG_KEY_2="core.autocrlf",GIT_CONFIG_VALUE_2="true")
            def git(*args):
                return subprocess.run(["git",*args],cwd=source,env=env,capture_output=True,text=True,timeout=10,check=True).stdout.strip()
            git("read-tree",commit)
            self.assertEqual(git("rev-parse","HEAD"),commit)
            self.assertEqual(git("status","--porcelain"),"")
            (source/"tracked.txt").write_text("changed\n")
            self.assertIn("tracked.txt",git("status","--porcelain"))


if __name__ == "__main__":
    unittest.main()
