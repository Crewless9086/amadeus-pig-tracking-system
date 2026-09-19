"""Synthetic-only retirement safety tests; fixtures remain under the approved runtime."""
from __future__ import annotations
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import uuid

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "retire_preserved_workspace.ps1"
SPEC = importlib.util.spec_from_file_location("preservation", REPO / "scripts" / "workspace_archive.py")
ARCHIVE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ARCHIVE)
PWSH = shutil.which("pwsh")
FIXTURES = Path(r"C:\Amadeus\.runtime\retirement-tests")


@unittest.skipUnless(os.name == "nt" and PWSH, "Windows PowerShell and DPAPI required")
class RetirementTests(unittest.TestCase):
    def setUp(self):
        self.base = FIXTURES / uuid.uuid4().hex
        self.source = self.base / "sources"
        self.old = self.source / "amadeus-obsolete-copy"
        self.old.mkdir(parents=True)
        (self.old / "empty-dir").mkdir()
        (self.old / "a.txt").write_bytes(b"preserved fixture A")
        (self.old / "b.txt").write_bytes(b"preserved fixture B")
        self.original = self.source / "original-checkout"
        self.original.mkdir()
        (self.original / "retained.txt").write_bytes(b"original stays")
        self.canonical = self.base / "canonical"
        self.canonical.mkdir()
        self.backup = self.base / "archive"
        self.destination = self.base / "restore-rehearsal"
        self.allow = self.base / "allowlist.json"
        self.verified = self.base / "verified.json"
        self.restored = self.base / "restored.json"
        ARCHIVE.snapshot([("fixture", self.source)], self.backup, 0)
        self.config = {
            "version": 1, "owner_authorization": "synthetic fixture authorization",
            "writers_stopped": True, "canonical_checkout": str(self.canonical),
            "protected_original_checkout": str(self.original),
            "roots": [{"path": str(self.old), "disposition": "obsolete-amadeus-copy",
                       "ownership_evidence": "synthetic Amadeus fixture"}],
        }
        self.write(self.allow, self.config)

    def write(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def proof(self):
        verification = ARCHIVE.verify(self.backup, 0)
        verification["archive"] = str(self.backup)
        self.write(self.verified, verification)
        selection = "amadeus-obsolete-copy/a.txt"
        restore = ARCHIVE.restore(self.backup, self.destination, ["fixture:" + selection])
        restore.update({"archive": str(self.backup), "destination": str(self.destination),
                        "selections": [{"label": "fixture", "relative": selection}]})
        self.write(self.restored, restore)

    def add_hold(self, relative, reason):
        manifest = self.backup / "manifest.jsonl"
        with manifest.open("ab") as output:
            output.write(ARCHIVE.json_bytes({"type": "hold", "label": "fixture",
                                            "relative": relative, "reason": reason}) + b"\n")
        summary_path = self.backup / "summary.json"
        summary = json.loads(summary_path.read_bytes())
        summary.pop("summary_hmac_sha256")
        summary["counts"]["holds"] += 1
        summary["manifest_entries"] += 1
        summary["preservation_complete"] = False
        summary["manifest_sha256"] = ARCHIVE.digest_file(manifest)
        key = ARCHIVE.dpapi((self.backup / "key.dpapi").read_bytes(), False)
        summary["summary_hmac_sha256"] = hmac.new(key, ARCHIVE.json_bytes(summary), hashlib.sha256).hexdigest()
        summary_path.write_bytes(ARCHIVE.json_bytes(summary))

    def invoke(self, apply=False, rebind=None):
        log = self.base / ("outcomes-" + uuid.uuid4().hex + ".jsonl")
        command = [PWSH, "-NoProfile", "-NonInteractive", "-File", str(SCRIPT),
                   "-Archive", str(self.backup), "-Allowlist", str(self.allow),
                   "-VerificationReceipt", str(self.verified), "-RestoreReceipt", str(self.restored),
                   "-OutcomeLog", str(log), "-PythonExe", sys.executable]
        if apply:
            command.append("-Apply")
        if rebind:
            command.extend(["-DesktopRebindReceipt", str(rebind)])
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        rows = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return result, rows

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_held(self, result):
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_plan_default_keeps_every_source(self):
        self.proof()
        result, rows = self.invoke()
        self.assert_success(result)
        self.assertEqual(sum(row.get("action") == "planned" for row in rows), 2)
        self.assertEqual((self.old / "a.txt").read_bytes(), b"preserved fixture A")
        self.assertTrue((self.old / "empty-dir").is_dir())
        self.assertTrue((self.original / "retained.txt").exists())

    def test_apply_removes_only_verified_files_and_empty_directories(self):
        self.proof()
        result, rows = self.invoke(apply=True)
        self.assert_success(result)
        self.assertFalse(self.old.exists())
        self.assertTrue((self.original / "retained.txt").exists())
        self.assertTrue((self.destination / "fixture" / "amadeus-obsolete-copy" / "a.txt").exists())
        self.assertEqual(sum(row.get("action") == "removed" for row in rows), 2)
        self.assertEqual(sum(row.get("action") == "directory_removed" for row in rows), 2)

    def test_same_size_same_mtime_modified_bytes_are_held(self):
        self.proof()
        target = self.old / "a.txt"
        before = target.stat()
        target.write_bytes(b"modified  fixture A")
        self.assertEqual(target.stat().st_size, before.st_size)
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
        result, rows = self.invoke(apply=True)
        self.assert_held(result)
        self.assertEqual(target.read_bytes(), b"modified  fixture A")
        self.assertTrue(any("file_content_changed" in row.get("reason", "") for row in rows))

    def test_replaced_file_same_bytes_and_timestamps_is_held(self):
        self.proof()
        target = self.old / "a.txt"
        before, parent = target.stat(), self.old.stat()
        target.rename(self.base / "original-object")
        target.write_bytes(b"preserved fixture A")
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
        os.utime(self.old, ns=(parent.st_atime_ns, parent.st_mtime_ns))
        result, rows = self.invoke(apply=True)
        self.assert_held(result)
        self.assertTrue(target.exists())
        self.assertTrue(any("file_metadata_or_stream_changed" in row.get("reason", "") for row in rows))

    def test_new_unlisted_file_holds_directory_and_is_never_removed(self):
        self.proof()
        parent = self.old.stat()
        extra = self.old / "new-owner-work.txt"
        extra.write_bytes(b"new unique bytes")
        os.utime(self.old, ns=(parent.st_atime_ns, parent.st_mtime_ns))
        result, _ = self.invoke(apply=True)
        self.assert_held(result)
        self.assertEqual(extra.read_bytes(), b"new unique bytes")
        self.assertTrue((self.old / "a.txt").exists())

    def test_directory_scan_hold_retains_directory_but_allows_verified_descendants(self):
        self.add_hold("amadeus-obsolete-copy", "directory_changed_during_scan")
        self.proof()
        result, rows = self.invoke(apply=True)
        self.assert_held(result)
        self.assertTrue(self.old.is_dir())
        self.assertFalse((self.old / "a.txt").exists())
        self.assertFalse((self.old / "b.txt").exists())
        self.assertEqual(sum(row.get("action") == "removed" for row in rows), 2)
        self.assertTrue(any(row.get("reason") == "archive_hold:directory_changed_during_scan" for row in rows))
        self.assertFalse(any(row.get("path") == str(self.old) and row.get("action") == "directory_removed" for row in rows))

    def test_directory_scan_hold_does_not_allow_unknown_new_entries(self):
        self.add_hold("amadeus-obsolete-copy", "directory_changed_during_scan")
        self.proof()
        parent = self.old.stat()
        (self.old / "unknown").write_bytes(b"keep")
        os.utime(self.old, ns=(parent.st_atime_ns, parent.st_mtime_ns))
        result, _ = self.invoke(apply=True)
        self.assert_held(result)
        self.assertTrue((self.old / "a.txt").exists())
        self.assertEqual((self.old / "unknown").read_bytes(), b"keep")

    def test_other_directory_hold_blocks_every_descendant(self):
        self.add_hold("amadeus-obsolete-copy", "entry_not_preserved")
        self.proof()
        result, rows = self.invoke(apply=True)
        self.assert_held(result)
        self.assertTrue((self.old / "a.txt").exists())
        self.assertFalse(any(row.get("action") == "removed" for row in rows))

    def test_exact_file_allowlist_cannot_bypass_ancestor_hold(self):
        self.add_hold("amadeus-obsolete-copy", "entry_not_preserved")
        self.proof()
        self.config["roots"][0]["path"] = str(self.old / "a.txt")
        self.write(self.allow, self.config)
        result, rows = self.invoke(apply=True)
        self.assert_held(result)
        self.assertTrue((self.old / "a.txt").exists())
        self.assertTrue(any(row.get("reason") == "archive_ancestor_hold:entry_not_preserved"
                            for row in rows))
        self.assertFalse(any(row.get("action") == "removed" for row in rows))

    def test_fresh_alternate_stream_is_never_discarded(self):
        self.proof()
        with open(str(self.old / "a.txt") + ":test-private-stream", "wb") as output:
            output.write(b"synthetic stream")
        result, _ = self.invoke(apply=True)
        self.assert_held(result)
        with open(str(self.old / "a.txt") + ":test-private-stream", "rb") as source:
            self.assertEqual(source.read(), b"synthetic stream")

    def test_protected_original_requires_matching_desktop_rebind(self):
        self.proof()
        self.config["protected_original_checkout"] = str(self.old)
        self.write(self.allow, self.config)
        result, rows = self.invoke(apply=True)
        self.assert_held(result)
        self.assertTrue((self.old / "a.txt").exists())
        self.assertFalse(any(row.get("action") == "removed" for row in rows))

    def test_invalid_verification_and_restore_evidence_fail_before_removal(self):
        self.proof()
        receipt = json.loads(self.verified.read_text())
        receipt["verified_objects"] = 0
        self.write(self.verified, receipt)
        result, _ = self.invoke(apply=True)
        self.assertEqual(result.returncode, 1)
        self.assertTrue((self.old / "a.txt").exists())
        receipt["verified_objects"] = json.loads((self.backup / "summary.json").read_text())["counts"]["unique_objects"]
        self.write(self.verified, receipt)
        restored = self.destination / "fixture" / "amadeus-obsolete-copy" / "a.txt"
        restored.write_bytes(b"tampered")
        result, _ = self.invoke(apply=True)
        self.assertEqual(result.returncode, 1)
        self.assertTrue((self.old / "a.txt").exists())

    def test_missing_ownership_or_broad_root_is_rejected(self):
        self.proof()
        self.config["roots"][0]["ownership_evidence"] = ""
        self.write(self.allow, self.config)
        result, _ = self.invoke(apply=True)
        self.assertEqual(result.returncode, 1)
        self.config["roots"][0]["ownership_evidence"] = "fixture"
        self.config["roots"][0]["path"] = str(self.source)
        self.write(self.allow, self.config)
        result, _ = self.invoke(apply=True)
        self.assertEqual(result.returncode, 1)
        self.assertTrue((self.old / "a.txt").exists())

    def test_tampered_archive_cannot_authorize_removal(self):
        self.proof()
        path = self.backup / "objects.zip"
        data = bytearray(path.read_bytes())
        data[len(data) // 2] ^= 1
        path.write_bytes(data)
        result, _ = self.invoke(apply=True)
        self.assertEqual(result.returncode, 1)
        self.assertTrue((self.old / "a.txt").exists())

    def test_replaced_directory_junction_never_traverses_target(self):
        self.proof()
        parent_stamp = self.old.stat()
        (self.old / "empty-dir").rename(self.base / "old-empty-object")
        outside = self.base / "outside"
        outside.mkdir()
        marker = outside / "keep.txt"
        marker.write_bytes(b"outside must remain")
        junction = self.old / "empty-dir"
        command = "New-Item -ItemType Junction -Path '" + str(junction).replace("'", "''") + "' -Value '" + str(outside).replace("'", "''") + "' | Out-Null"
        made = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", command],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(made.returncode, 0, made.stderr)
        os.utime(self.old, ns=(parent_stamp.st_atime_ns, parent_stamp.st_mtime_ns))
        result, _ = self.invoke(apply=True)
        self.assert_held(result)
        self.assertEqual(marker.read_bytes(), b"outside must remain")
        self.assertTrue(junction.exists())



    def test_exact_loose_file_with_brackets_is_removed_literally(self):
        bracket = self.old / "b[1].txt"
        (self.old / "b.txt").rename(bracket)
        self.backup = self.base / "second-archive"
        ARCHIVE.snapshot([("fixture", self.source)], self.backup, 0)
        self.config["roots"][0]["path"] = str(bracket)
        self.write(self.allow, self.config)
        self.proof()
        result, rows = self.invoke(apply=True)
        self.assert_success(result)
        self.assertFalse(bracket.exists())
        self.assertTrue((self.old / "a.txt").exists())
        self.assertTrue(self.old.is_dir())
        self.assertEqual(sum(row.get("action") == "removed" for row in rows), 1)

    def test_directory_scan_hold_still_checks_each_files_current_bytes(self):
        self.add_hold("amadeus-obsolete-copy", "directory_changed_during_scan")
        self.proof()
        target = self.old / "a.txt"
        before = target.stat()
        target.write_bytes(b"modified  fixture A")
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
        result, _ = self.invoke(apply=True)
        self.assert_held(result)
        self.assertEqual(target.read_bytes(), b"modified  fixture A")
        self.assertTrue((self.old / "b.txt").exists())
        self.assertTrue(self.old.is_dir())

    def make_scoped_archive(self):
        import zipfile
        manifest = self.backup / "manifest.jsonl"
        rows = [json.loads(line) for line in manifest.read_text().splitlines()]
        keep = {"", "amadeus-obsolete-copy", "amadeus-obsolete-copy/a.txt"}
        rows = [row for row in rows if row["relative"] in keep]
        file_row = next(row for row in rows if row["type"] == "file")
        name = "objects/" + file_row["sha256"] + ".enc"
        zip_path = self.backup / "objects.zip"
        with zipfile.ZipFile(zip_path) as source:
            encrypted = source.read(name)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as output:
            output.writestr(name, encrypted)
        manifest.write_bytes(b"".join(ARCHIVE.json_bytes(row) + b"\n" for row in rows))
        summary_path = self.backup / "summary.json"
        summary = json.loads(summary_path.read_bytes())
        summary.pop("summary_hmac_sha256")
        summary.update({
            "scope": "selected_paths_only",
            "selections": [{"label": "fixture", "relative": "amadeus-obsolete-copy/a.txt"}],
            "manifest_entries": len(rows),
            "manifest_sha256": ARCHIVE.digest_file(manifest),
            "archive_sha256": ARCHIVE.digest_file(zip_path),
            "counts": {"files": 1, "directories": 2, "holds": 0,
                       "source_bytes": file_row["metadata"]["size"], "unique_objects": 1,
                       "unique_bytes": file_row["metadata"]["size"]},
        })
        key = ARCHIVE.dpapi((self.backup / "key.dpapi").read_bytes(), False)
        summary["summary_hmac_sha256"] = hmac.new(key, ARCHIVE.json_bytes(summary), hashlib.sha256).hexdigest()
        summary_path.write_bytes(ARCHIVE.json_bytes(summary))

    def test_selected_scope_preserves_unselected_siblings_and_partial_parent(self):
        self.make_scoped_archive()
        self.proof()
        result, rows = self.invoke(apply=True)
        self.assert_held(result)
        self.assertFalse((self.old / "a.txt").exists())
        self.assertEqual((self.old / "b.txt").read_bytes(), b"preserved fixture B")
        self.assertTrue((self.old / "empty-dir").is_dir())
        self.assertTrue(self.old.is_dir())
        self.assertEqual(sum(row.get("action") == "removed" for row in rows), 1)

    def test_empty_partial_scope_ancestor_is_retained(self):
        self.make_scoped_archive()
        (self.old / "b.txt").unlink()
        (self.old / "empty-dir").rmdir()
        self.proof()
        result, rows = self.invoke(apply=True)
        self.assert_held(result)
        self.assertTrue(self.old.is_dir())
        self.assertEqual(list(self.old.iterdir()), [])
        self.assertTrue(any(row.get("reason") == "partial_scope_ancestor_retained" for row in rows))

    def test_overlapping_allowlist_roots_fail_before_removal(self):
        self.proof()
        self.config["roots"].insert(0, {
            "path": str(self.old / "a.txt"), "disposition": "obsolete-amadeus-copy",
            "ownership_evidence": "synthetic exact-file ownership"})
        self.write(self.allow, self.config)
        result, _ = self.invoke(apply=True)
        self.assertEqual(result.returncode, 1)
        self.assertTrue((self.old / "a.txt").exists())

    def test_active_write_handle_holds_file(self):
        self.proof()
        with open(self.old / "a.txt", "r+b"):
            result, _ = self.invoke(apply=True)
        self.assert_held(result)
        self.assertTrue((self.old / "a.txt").exists())
        self.assertTrue((self.old / "b.txt").exists())

    def test_compatible_reader_reports_pending_disposition_truthfully(self):
        import ctypes
        from ctypes import wintypes
        self.proof()
        target = self.old / "a.txt"
        self.config["roots"][0]["path"] = str(target)
        self.write(self.allow, self.config)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.CreateFileW(str(target), 0x80000000, 1 | 4, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value, ctypes.get_last_error())
        try:
            result, rows = self.invoke(apply=True)
            self.assert_held(result)
            self.assertTrue(any(row.get("action") == "removal_pending" for row in rows),
                            result.stdout + result.stderr + repr(rows))
            self.assertEqual(rows[-1]["status"], "DISPOSITIONS_PENDING")
            self.assertFalse(any(row.get("action") == "removed" for row in rows))
        finally:
            kernel.CloseHandle(handle)
        self.assertFalse(target.exists())
        self.assertTrue((self.old / "b.txt").exists())

    def test_matching_desktop_rebind_allows_only_the_exact_original_root(self):
        self.proof()
        self.config["protected_original_checkout"] = str(self.old)
        self.write(self.allow, self.config)
        rebind = self.base / "desktop-rebind.json"
        binding = {"version": 1, "kind": "codex-desktop-project-rebind", "status": "PASS",
                   "evidence": "synthetic fixture rebind", "observed_at": ARCHIVE.utc_now(),
                   "canonical_checkout": str(self.canonical), "previous_checkout": str(self.original)}
        self.write(rebind, binding)
        result, _ = self.invoke(apply=True, rebind=rebind)
        self.assertEqual(result.returncode, 1)
        self.assertTrue((self.old / "a.txt").exists())
        binding["previous_checkout"] = str(self.old)
        self.write(rebind, binding)
        result, _ = self.invoke(apply=True, rebind=rebind)
        self.assert_success(result)
        self.assertFalse(self.old.exists())
        self.assertTrue((self.original / "retained.txt").exists())


    def native_probe(self, body, *arguments):
        probe = self.base / ("native-probe-" + uuid.uuid4().hex + ".ps1")
        prefix = r"""
param([string]$SourceScript,[string]$Target,[string]$Directory,[string]$ArchiveDirectory)
$ErrorActionPreference='Stop'
$text=[IO.File]::ReadAllText($SourceScript)
$start=$text.IndexOf('Add-Type -TypeDefinition')
$end=$text.IndexOf('function Full')
& ([scriptblock]::Create($text.Substring($start,$end-$start)))
"""
        probe.write_text(prefix + body, encoding="utf-8")
        return subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", str(probe),
                               "-SourceScript", str(SCRIPT), "-Target", str(self.old / "a.txt"),
                               "-Directory", str(self.old / "empty-dir"),
                               "-ArchiveDirectory", str(self.backup), *arguments],
                              capture_output=True, text=True, timeout=30)

    def test_handle_excludes_replacement_but_detects_concurrent_ads_limitation(self):
        result = self.native_probe(r"""
$handle=[RetireNative]::OpenForDelete($Target)
$stream=[IO.FileStream]::new($handle,[IO.FileAccess]::Read)
try {
 $identity=[RetireNative]::Handle($stream.SafeFileHandle)
 $renameBlocked=$false;$writeBlocked=$false;$adsBlocked=$false
 try{[IO.File]::Move($Target,$Target+'.renamed')}catch [IO.IOException]{$renameBlocked=$true}
 try{$writer=[IO.FileStream]::new($Target,[IO.FileMode]::Open,[IO.FileAccess]::Write,[IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete);$writer.Dispose()}catch [IO.IOException]{$writeBlocked=$true}
 try{$writer=[IO.FileStream]::new($Target+':injected',[IO.FileMode]::Create,[IO.FileAccess]::Write,[IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete);$writer.WriteByte(42);$writer.Dispose()}catch [IO.IOException]{$adsBlocked=$true}
 $observedAdsHeld=$false
 if(-not $adsBlocked){
  try{[RetireNative]::DeleteVerifiedHandle($stream.SafeFileHandle,$Target)}catch{$observedAdsHeld=$true}
 }
 @{rename_blocked=$renameBlocked;write_blocked=$writeBlocked;ads_write_possible=(-not $adsBlocked);observed_ads_held=$observedAdsHeld;identity_unchanged=($identity.Inode -eq [RetireNative]::Info($Target).Inode)}|ConvertTo-Json -Compress
 if(-not ($renameBlocked -and $writeBlocked -and (-not $adsBlocked) -and $observedAdsHeld)){exit 3}
}finally{$stream.Dispose()}
""")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        facts = json.loads(result.stdout.strip())
        self.assertTrue(all(facts.values()))
        self.assertEqual((self.old / "a.txt").read_bytes(), b"preserved fixture A")

    def test_archive_input_locks_block_content_and_path_replacement(self):
        result = self.native_probe(r"""
$blocked=0
foreach($name in @('summary.json','key.dpapi','manifest.jsonl','objects.zip')){
 $path=Join-Path $ArchiveDirectory $name
 $locked=[RetireNative]::LockInput($path)
 try{
  try{$writer=[IO.FileStream]::new($path,[IO.FileMode]::Open,[IO.FileAccess]::Write,[IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete);$writer.Dispose()}catch [IO.IOException]{$blocked++}
  try{[IO.File]::Move($path,$path+'.replaced')}catch [IO.IOException]{$blocked++}
 }finally{$locked.Dispose()}
}
@{blocked_attempts=$blocked}|ConvertTo-Json -Compress
if($blocked -ne 8){exit 3}
""")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["blocked_attempts"], 8)
        self.assertEqual(ARCHIVE.verify(self.backup, 0)["verification"], "PASS")

    def test_directory_handle_cannot_delete_new_unarchived_child(self):
        result = self.native_probe(r"""
$handle=[RetireNative]::OpenForDelete($Directory)
try{
 $renameBlocked=$false
 try{[IO.Directory]::Move($Directory,$Directory+'.replacement')}catch [IO.IOException]{$renameBlocked=$true}
 # Force the race after an empty enumeration but before disposition.
 $empty=-not [IO.Directory]::EnumerateFileSystemEntries($Directory).GetEnumerator().MoveNext()
 $newChild=Join-Path $Directory 'new-unarchived-child.txt'
 [IO.File]::WriteAllText($newChild,'must remain')
 $deleteRejected=$false
 try{[RetireNative]::DeleteVerifiedHandle($handle,$Directory)}catch{$deleteRejected=$true}
 @{rename_blocked=$renameBlocked;initially_empty=$empty;nonempty_delete_rejected=$deleteRejected}|ConvertTo-Json -Compress
 if(-not ($renameBlocked -and $empty -and $deleteRejected)){exit 3}
}finally{$handle.Dispose()}
""")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(all(json.loads(result.stdout).values()))
        self.assertEqual((self.old / "empty-dir" / "new-unarchived-child.txt").read_text(), "must remain")

if __name__ == "__main__":
    unittest.main()
