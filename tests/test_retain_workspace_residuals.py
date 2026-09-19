"""Bounded synthetic tests; no original source paths are moved."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import uuid

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "retain_workspace_residuals.ps1"
FIXTURES = Path(r"C:\Amadeus\.runtime\retention-tests")
PWSH = shutil.which("pwsh")


def native(path):
    return Path('\\\\?\\' + str(path))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@unittest.skipUnless(os.name == "nt" and PWSH, "Windows NTFS required")
class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.base = FIXTURES / uuid.uuid4().hex
        self.agents, self.tmp, self.recovery = (self.base / name for name in ("agents", "tmp", "recovery"))
        for path in (self.agents, self.tmp, self.recovery):
            path.mkdir(parents=True)
        self.source = self.tmp / "amadeus-leftover"
        self.source.mkdir()
        (self.source / "nested").mkdir()
        (self.source / "nested" / "private.txt").write_bytes(b"synthetic opaque bytes")
        self.destination = self.recovery / "retained-originals" / "tmp" / self.source.name
        self.classification = self.base / "classification.json"
        self.allowlist = self.base / "retirement-allowlist.json"
        self.retirement = self.base / "retirement-apply.jsonl"
        self.plan = self.base / "retention-plan.json"
        self.classified = {"allowlist_candidates": [
            {"path": str(self.source), "disposition": "obsolete-amadeus-copy"}], "held_entries": []}
        self.write(self.classification, self.classified)
        self.write(self.allowlist, {"version": 1, "owner_authorization": "synthetic owner",
                                  "writers_stopped": True, "roots": [
                                      {"path": str(self.source), "disposition": "obsolete-amadeus-copy",
                                       "ownership_evidence": "synthetic classification"}]})
        self.run_rows = [
            {"kind": "start", "mode": "APPLY", "allowlist_sha256": digest(self.allowlist),
             "archive_sha256": "a" * 64, "manifest_sha256": "b" * 64},
            {"source": str(self.source), "action": "held", "reason": "fixture_residual"},
            {"status": "HOLDS_REMAIN", "mode": "APPLY", "finished_at": "2026-09-19T12:00:00Z",
             "archive_sha256": "a" * 64, "manifest_sha256": "b" * 64,
             "totals": {"removal_pending": 0, "directory_removal_pending": 0}}]
        self.write_run()
        self.config = {"version": 1, "owner_authorization": "synthetic owner",
                       "writers_stopped": True, "intact_retention_only": True,
                       "classification_manifest": str(self.classification),
                       "classification_sha256": digest(self.classification),
                       "retirement_runs": [{"allowlist": str(self.allowlist), "outcome_log": str(self.retirement)}],
                       "roots": [{"path": str(self.source), "disposition": "obsolete-amadeus-copy",
                                  "ownership_evidence": "synthetic classification"}]}
        self.write(self.plan, self.config)

    def write(self, path, data):
        path.write_text(json.dumps(data), encoding="utf-8")

    def write_run(self):
        self.retirement.write_text("".join(json.dumps(row) + "\n" for row in self.run_rows), encoding="utf-8")

    def invoke(self, apply=False, fixture=None):
        self.write(self.plan, self.config)
        log = self.base / ("mapping-" + uuid.uuid4().hex + ".jsonl")
        args = [PWSH, "-NoProfile", "-NonInteractive", "-File", str(SCRIPT),
                "-Plan", str(self.plan), "-OutcomeLog", str(log),
                "-TestFixtureRoot", str(fixture or self.base)]
        if apply:
            args.append("-Apply")
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
        return result, rows

    def success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_default_plan_leaves_sources_and_destination_absent(self):
        result, rows = self.invoke()
        self.success(result)
        self.assertTrue(self.source.is_dir())
        self.assertFalse(self.destination.exists())
        self.assertEqual(rows[-1]["totals"]["planned"], 1)

    def test_apply_preserves_directory_file_and_alternate_streams(self):
        root_id = self.source.stat().st_ino
        child = self.source / "nested" / "private.txt"
        child_id = child.stat().st_ino
        with open(str(self.source) + ":root-note", "wb") as output:
            output.write(b"synthetic root ADS")
        with open(str(child) + ":private-stream", "wb") as output:
            output.write(b"synthetic child ADS")
        result, rows = self.invoke(apply=True)
        self.success(result)
        self.assertFalse(self.source.exists())
        self.assertEqual(self.destination.stat().st_ino, root_id)
        restored_child = self.destination / "nested" / "private.txt"
        self.assertEqual(restored_child.stat().st_ino, child_id)
        self.assertEqual(restored_child.read_bytes(), b"synthetic opaque bytes")
        for path, expected in ((str(self.destination) + ":root-note", b"synthetic root ADS"),
                               (str(restored_child) + ":private-stream", b"synthetic child ADS")):
            with open(path, "rb") as source:
                self.assertEqual(source.read(), expected)
        mapping = next(row for row in rows if row.get("action") == "retained")
        self.assertEqual(mapping["before"], mapping["after"])

    def test_existing_destination_never_overwritten(self):
        self.destination.mkdir(parents=True)
        marker = self.destination / "keep"
        marker.write_bytes(b"existing unique bytes")
        result, rows = self.invoke(apply=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertTrue(self.source.exists())
        self.assertEqual(marker.read_bytes(), b"existing unique bytes")
        self.assertTrue(any(row.get("reason") == "destination_exists" for row in rows))

    def test_unknown_ownership_requires_separate_intact_disposition(self):
        self.classified["held_entries"] = [
            {"path": str(self.source), "disposition": "hold-ownership-unverified"}]
        self.classified["allowlist_candidates"] = []
        self.write(self.classification, self.classified)
        self.config["classification_sha256"] = digest(self.classification)
        self.config["retirement_runs"] = []
        self.config["roots"][0]["disposition"] = "retain-ownership-unverified"
        result, rows = self.invoke(apply=True)
        self.success(result)
        self.assertTrue(self.destination.is_dir())
        self.assertEqual(next(row for row in rows if row.get("action") == "retained")["disposition"],
                         "retain-ownership-unverified")

    def test_absent_unverified_source_remains_unresolved(self):
        self.classified["held_entries"] = [
            {"path": str(self.source), "disposition": "hold-ownership-unverified"}]
        self.classified["allowlist_candidates"] = []
        self.write(self.classification, self.classified)
        self.config["classification_sha256"] = digest(self.classification)
        self.config["retirement_runs"] = []
        self.config["roots"][0]["disposition"] = "retain-ownership-unverified"
        self.source.rename(self.base / "unexplained-location")
        result, rows = self.invoke(apply=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertFalse(self.destination.exists())
        self.assertTrue(any(row.get("reason") == "unverified_source_absent_unresolved" for row in rows))
        self.assertEqual(rows[-1]["totals"]["absent"], 0)

    def test_pending_or_incomplete_retirement_blocks_all_moves(self):
        self.run_rows.insert(1, {"action": "removal_pending"})
        self.write_run()
        result, _ = self.invoke(apply=True)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(self.source.exists())
        self.run_rows.pop(1)
        self.run_rows.pop()
        self.write_run()
        result, _ = self.invoke(apply=True)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(self.source.exists())

    def test_classification_and_retirement_allowlist_digest_must_match(self):
        with self.classification.open("ab") as output:
            output.write(b" ")
        result, _ = self.invoke(apply=True)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(self.source.exists())
        self.config["classification_sha256"] = digest(self.classification)
        with self.allowlist.open("ab") as output:
            output.write(b" ")
        result, _ = self.invoke(apply=True)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(self.source.exists())

    def test_broad_nested_unknown_and_original_roots_rejected(self):
        for target in (self.tmp, self.source / "nested", self.tmp / "unknown",
                       self.agents / "amadeus-pig-tracking-system"):
            self.config["roots"][0]["path"] = str(target)
            result, _ = self.invoke(apply=True)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertTrue(self.source.exists())

    def test_fixture_switch_cannot_escape_synthetic_runtime(self):
        result, _ = self.invoke(apply=True, fixture=self.base.parent)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(self.source.exists())

    def junction(self, link, target):
        command = "New-Item -ItemType Junction -Path '" + str(link).replace("'", "''") + "' -Value '" + str(target).replace("'", "''") + "' | Out-Null"
        result = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", command],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_nested_junction_remains_opaque_and_target_untouched(self):
        outside = self.base / "outside"
        outside.mkdir()
        marker = outside / "keep"
        marker.write_bytes(b"outside bytes")
        link = self.source / "nested-link"
        self.junction(link, outside)
        identity = link.lstat().st_ino
        target_bytes = os.readlink(link)
        result, _ = self.invoke(apply=True)
        self.success(result)
        retained_link = self.destination / link.name
        self.assertEqual(retained_link.lstat().st_ino, identity)
        self.assertEqual(marker.read_bytes(), b"outside bytes")
        self.assertEqual(os.readlink(retained_link), target_bytes)

    def test_top_level_reparse_point_is_held_without_following(self):
        opaque = self.base / "opaque-original"
        self.source.rename(opaque)
        self.junction(self.source, opaque)
        result, rows = self.invoke(apply=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertTrue(self.source.exists())
        self.assertFalse(self.destination.exists())
        self.assertTrue((opaque / "nested" / "private.txt").exists())
        self.assertTrue(any(row.get("reason") == "reparse_root_or_ancestor" for row in rows))

    def test_exact_loose_file_and_ads_are_retained(self):
        loose = self.agents / "receipt[1].txt"
        loose.write_bytes(b"synthetic loose receipt")
        with open(str(loose) + ":note", "wb") as stream:
            stream.write(b"synthetic loose ADS")
        self.classified["held_entries"] = [
            {"path": str(loose), "disposition": "hold-ownership-unverified"}]
        self.write(self.classification, self.classified)
        self.config["classification_sha256"] = digest(self.classification)
        self.config["retirement_runs"] = []
        self.config["roots"] = [{"path": str(loose), "disposition": "retain-ownership-unverified",
                                 "ownership_evidence": "explicit synthetic intact retention"}]
        identity = loose.stat().st_ino
        result, _ = self.invoke(apply=True)
        self.success(result)
        retained = self.recovery / "retained-originals" / "agents" / loose.name
        self.assertFalse(loose.exists())
        self.assertEqual(retained.stat().st_ino, identity)
        self.assertEqual(retained.read_bytes(), b"synthetic loose receipt")
        with open(str(retained) + ":note", "rb") as stream:
            self.assertEqual(stream.read(), b"synthetic loose ADS")
        self.assertTrue(self.source.exists())

    def test_native_rename_preserves_exact_unicode_and_long_names(self):
        names = ["a.txt", "multi-\\u00e9-\\u6e2c\\u8a66-\\U0001f400.txt",
                 "long-" + "x" * 190 + ".txt", "literal[receipt].dat"]
        names = [name.encode("ascii").decode("unicode_escape") for name in names]
        sources = [self.agents / name for name in names]
        identities = {}
        for source in sources:
            native(source).write_bytes(b"synthetic exact name")
            identities[source.name] = native(source).stat().st_ino
        self.classified["held_entries"] = [
            {"path": str(source), "disposition": "hold-ownership-unverified"} for source in sources]
        self.write(self.classification, self.classified)
        self.config["classification_sha256"] = digest(self.classification)
        self.config["retirement_runs"] = []
        self.config["roots"] = [
            {"path": str(source), "disposition": "retain-ownership-unverified",
             "ownership_evidence": "synthetic exact-name retention"} for source in sources]
        result, _ = self.invoke(apply=True)
        self.success(result)
        destination = self.recovery / "retained-originals" / "agents"
        self.assertEqual({path.name for path in destination.iterdir()}, set(names))
        for name in names:
            self.assertEqual(native(destination / name).stat().st_ino, identities[name])
            self.assertEqual(native(destination / name).read_bytes(), b"synthetic exact name")
        self.assertFalse(any(native(source).exists() for source in sources))

    def test_destination_ancestor_junction_is_held(self):
        outside = self.base / "outside-recovery"
        outside.mkdir()
        self.junction(self.recovery / "retained-originals", outside)
        result, rows = self.invoke(apply=True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertTrue(self.source.exists())
        self.assertEqual(list(outside.iterdir()), [])
        self.assertTrue(any(row.get("reason") == "reparse_root_or_ancestor" for row in rows))

    def test_obsolete_root_requires_completed_exact_apply_coverage(self):
        self.config["retirement_runs"] = []
        result, _ = self.invoke(apply=True)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(self.source.exists())

    def test_explicit_intact_retention_and_stopped_writers_required(self):
        for field in ("intact_retention_only", "writers_stopped"):
            self.config[field] = False
            result, _ = self.invoke(apply=True)
            self.assertEqual(result.returncode, 1)
            self.assertTrue(self.source.exists())
            self.config[field] = True

    def open_native(self, path, access, sharing):
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateFileW(str(path), access, sharing, None, 3, 0x02000000, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value, ctypes.get_last_error())
        return kernel, handle

    def test_busy_root_holds_without_partial_move(self):
        kernel, handle = self.open_native(self.source, 0x80000000, 1)
        try:
            result, _ = self.invoke(apply=True)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertTrue(self.source.exists())
            self.assertFalse(self.destination.exists())
        finally:
            kernel.CloseHandle(handle)

    def test_busy_unreadable_child_holds_then_can_be_retained_intact(self):
        child = self.source / "nested" / "private.txt"
        kernel, handle = self.open_native(child, 0x80000000, 4)
        try:
            with self.assertRaises(PermissionError):
                child.read_bytes()
            result, _ = self.invoke(apply=True)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertTrue(self.source.is_dir())
            self.assertFalse(self.destination.exists())
        finally:
            kernel.CloseHandle(handle)
        result, _ = self.invoke(apply=True)
        self.success(result)
        self.assertEqual((self.destination / "nested" / "private.txt").read_bytes(), b"synthetic opaque bytes")


if __name__ == "__main__":
    unittest.main()
