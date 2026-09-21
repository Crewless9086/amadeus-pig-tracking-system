r"""Integrity-focused tests; all fixture files stay in the approved runtime root.

Run from the checkout with:
  C:\Users\charl\venv\Scripts\python.exe -B -m unittest tests.test_workspace_archive -v
No provider access or source-directory deletion. Fixtures remain for inspection.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace
import unittest
from unittest import mock
import uuid
import zipfile

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "workspace_archive.py"
SPEC = importlib.util.spec_from_file_location("workspace_archive", MODULE_PATH)
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)
TEST_ROOT = Path(r"C:\Amadeus\.runtime\archive-repair-tests")


@unittest.skipUnless(os.name == "nt", "DPAPI preservation tool targets Windows")
class WorkspaceArchiveTests(unittest.TestCase):
    def setUp(self):
        self.base = TEST_ROOT / uuid.uuid4().hex
        self.source = self.base / "source"
        self.output = self.base / "archive"
        self.destination = self.base / "restored"
        self.source.mkdir(parents=True)

    def snapshot(self):
        return archive.snapshot([("source", self.source)], self.output, progress=0)

    def read_rows(self):
        return [json.loads(line) for line in (self.output / "manifest.jsonl").read_text().splitlines()]

    def resign(self, edit=None):
        summary_path = self.output / "summary.json"
        summary = json.loads(summary_path.read_bytes())
        summary.pop("summary_hmac_sha256")
        key = archive.dpapi((self.output / "key.dpapi").read_bytes(), False)
        summary["manifest_sha256"] = archive.digest_file(self.output / "manifest.jsonl")
        summary["archive_sha256"] = archive.digest_file(self.output / "objects.zip")
        if edit:
            edit(summary)
        summary["summary_hmac_sha256"] = hmac.new(key, archive.json_bytes(summary), hashlib.sha256).hexdigest()
        summary_path.write_bytes(archive.json_bytes(summary))

    def test_round_trip_deduplicates_bytes_and_preserves_empty_files_and_directories(self):
        (self.source / "empty-dir").mkdir()
        payload = b"private-test-fixture-no-real-secret" * 10000
        (self.source / "a.bin").write_bytes(payload)
        (self.source / "b.bin").write_bytes(payload)
        (self.source / "empty.bin").write_bytes(b"")
        original_mtime = (self.source / "a.bin").stat().st_mtime_ns
        summary = self.snapshot()
        self.assertTrue(summary["preservation_complete"])
        self.assertEqual(summary["counts"]["files"], 3)
        self.assertEqual(summary["counts"]["unique_objects"], 2)
        self.assertEqual(summary["counts"]["directories"], 2)
        result = archive.verify(self.output, progress=0)
        self.assertEqual(result["verification"], "PASS")
        self.assertFalse(result["deletion_authorized"])
        self.assertNotIn(payload[:128], (self.output / "objects.zip").read_bytes())
        restored = archive.restore(self.output, self.destination)
        self.assertEqual(restored["files"], 3)
        self.assertEqual((self.destination / "source" / "a.bin").read_bytes(), payload)
        self.assertEqual((self.destination / "source" / "a.bin").stat().st_mtime_ns, original_mtime)
        self.assertTrue((self.destination / "source" / "empty-dir").is_dir())
        self.assertEqual((self.destination / "source" / "empty.bin").read_bytes(), b"")
        self.assertFalse(any(self.output.glob("pending-*")))

    def test_streaming_larger_than_chunk_and_selected_restore(self):
        data = os.urandom(archive.CHUNK * 3 + 123)
        (self.source / "large").write_bytes(data)
        (self.source / "other").write_bytes(b"not selected")
        self.snapshot()
        self.assertEqual(archive.verify(self.output, 0)["verified_objects"], 2)
        result = archive.restore(self.output, self.destination, ["source:large"])
        self.assertEqual(result["files"], 1)
        self.assertEqual((self.destination / "source" / "large").read_bytes(), data)
        self.assertFalse((self.destination / "source" / "other").exists())

    def test_archive_byte_corruption_is_detected_before_restore_writes(self):
        (self.source / "a").write_bytes(b"content")
        self.snapshot()
        path = self.output / "objects.zip"
        value = bytearray(path.read_bytes())
        value[len(value) // 2] ^= 1
        path.write_bytes(value)
        with self.assertRaisesRegex(archive.ArchiveError, "archive_sha256_mismatch"):
            archive.verify(self.output, 0)
        with self.assertRaises(archive.ArchiveError):
            archive.restore(self.output, self.destination)
        self.assertFalse(self.destination.exists())

    def test_gcm_corruption_detected_even_with_updated_outer_hash(self):
        (self.source / "a").write_bytes(b"content" * 2000)
        self.snapshot()
        path = self.output / "objects.zip"
        with zipfile.ZipFile(path) as source:
            name = source.namelist()[0]
            value = bytearray(source.read(name))
        value[-1] ^= 1
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as target:
            target.writestr(name, value)
        self.resign()
        from cryptography.exceptions import InvalidTag
        with self.assertRaises(InvalidTag):
            archive.verify(self.output, 0)
        with self.assertRaises(InvalidTag):
            archive.restore(self.output, self.destination)
        self.assertFalse(self.destination.exists())

    def test_manifest_tampering_and_summary_tampering_detected(self):
        (self.source / "a").write_bytes(b"content")
        self.snapshot()
        manifest = self.output / "manifest.jsonl"
        manifest.write_bytes(manifest.read_bytes() + b"\n")
        with self.assertRaisesRegex(archive.ArchiveError, "manifest_sha256_mismatch"):
            archive.verify(self.output, 0)
        summary = self.output / "summary.json"
        value = json.loads(summary.read_bytes())
        value["preservation_complete"] = False
        summary.write_bytes(archive.json_bytes(value))
        with self.assertRaisesRegex(archive.ArchiveError, "summary_authentication_failed"):
            archive.verify(self.output, 0)

    def test_path_traversal_absolute_and_windows_aliases_rejected(self):
        (self.source / "a").write_bytes(b"content")
        self.snapshot()
        for value in ("../outside", "/absolute", "C:/outside", "a/../../outside",
                      "a\\..\\outside", "a:stream", "x//y", "NUL", "a.", "a "):
            with self.subTest(value=value):
                with self.assertRaises(archive.ArchiveError):
                    archive.relative_parts(value)
        rows = self.read_rows()
        next(row for row in rows if row["type"] == "file")["relative"] = "../outside"
        (self.output / "manifest.jsonl").write_bytes(b"".join(archive.json_bytes(row) + b"\n" for row in rows))
        self.resign()
        with self.assertRaisesRegex(archive.ArchiveError, "unsafe_relative_path"):
            archive.restore(self.output, self.destination)
        self.assertFalse(self.destination.exists())

    def test_existing_destination_and_source_overlap_cannot_be_overwritten(self):
        (self.source / "a").write_bytes(b"source")
        with self.assertRaisesRegex(archive.ArchiveError, "disjoint"):
            archive.snapshot([("source", self.source)], self.source / "backup", 0)
        self.snapshot()
        self.destination.mkdir()
        marker = self.destination / "untouched"
        marker.write_bytes(b"retained")
        with self.assertRaisesRegex(archive.ArchiveError, "must_be_empty"):
            archive.restore(self.output, self.destination)
        self.assertEqual(marker.read_bytes(), b"retained")
        with self.assertRaisesRegex(archive.ArchiveError, "originals_must_be_disjoint"):
            archive.restore(self.output, self.source / "new-empty")
        self.assertEqual((self.source / "a").read_bytes(), b"source")

    def test_unreadable_file_records_hold_and_still_preserves_other_files(self):
        (self.source / "denied").write_bytes(b"never read")
        (self.source / "good").write_bytes(b"readable")
        original = archive.encrypt_file

        def deny(path, *args):
            if Path(path).name == "denied":
                raise PermissionError(13, "simulated access denial")
            return original(path, *args)

        with mock.patch.object(archive, "encrypt_file", side_effect=deny):
            summary = self.snapshot()
        self.assertFalse(summary["preservation_complete"])
        self.assertEqual(summary["counts"]["holds"], 1)
        self.assertEqual(summary["counts"]["files"], 1)
        verified = archive.verify(self.output, 0)
        self.assertFalse(verified["preservation_complete"])
        with self.assertRaisesRegex(archive.ArchiveError, "preservation_holds"):
            archive.restore(self.output, self.destination)
        archive.restore(self.output, self.destination, ["source:good"])
        self.assertEqual((self.destination / "source" / "good").read_bytes(), b"readable")

    def test_simulated_symbolic_link_never_opened_or_traversed(self):
        (self.source / "linked").write_bytes(b"do not read")
        (self.source / "good").write_bytes(b"ok")
        original = archive.os.lstat
        original_encrypt = archive.encrypt_file
        opened = []

        def mark_link(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if str(path).endswith("\\linked"):
                return mock.Mock(st_mode=stat.S_IFLNK, st_reparse_tag=0xA000000C,
                                 st_size=0, st_mtime_ns=0, st_ctime_ns=0,
                                 st_dev=0, st_ino=0, st_file_attributes=0x400)
            return info

        def watch(path, *args):
            opened.append(Path(path).name)
            return original_encrypt(path, *args)

        with mock.patch.object(archive.os, "lstat", side_effect=mark_link), \
                mock.patch.object(archive, "encrypt_file", side_effect=watch):
            summary = self.snapshot()
        self.assertEqual(summary["counts"]["holds"], 1)
        self.assertNotIn("linked", opened)
        self.assertEqual(next(row for row in self.read_rows() if row["type"] == "hold")["reason"], "link_or_junction")

    def test_source_mutation_during_stream_read_is_held(self):
        path = self.source / "changing"
        path.write_bytes(b"x" * 8000)
        original = archive.os.fstat
        count = 0

        def mutate(descriptor):
            nonlocal count
            count += 1
            if count == 2:
                # The original handle has finished reading. Change size before
                # its post-read fstat, with no fake metadata or expected hash.
                with open(path, "ab") as handle:
                    handle.write(b"changed")
            return original(descriptor)

        with mock.patch.object(archive.os, "fstat", side_effect=mutate):
            summary = self.snapshot()
        self.assertFalse(summary["preservation_complete"])
        self.assertEqual(summary["counts"]["files"], 0)
        self.assertEqual(summary["counts"]["unique_objects"], 0)
        holds = [row for row in self.read_rows() if row["type"] == "hold"]
        self.assertEqual(holds[0]["detail"]["reason"], "source_changed_during_read")
        self.assertEqual(archive.verify(self.output, 0)["verified_objects"], 0)

    def test_directory_enumeration_failure_records_hold(self):
        (self.source / "blocked").mkdir()
        original = archive.os.scandir

        def deny(path):
            if str(path).endswith("\\blocked"):
                raise PermissionError(13, "simulated")
            return original(path)

        with mock.patch.object(archive.os, "scandir", side_effect=deny):
            summary = self.snapshot()
        self.assertFalse(summary["preservation_complete"])
        self.assertEqual(summary["counts"]["holds"], 1)
        self.assertFalse(archive.verify(self.output, 0)["preservation_complete"])

    def test_ntfs_alternate_stream_blocks_deletion_candidacy(self):
        path = self.source / "a"
        path.write_bytes(b"main bytes")
        with open(str(path) + ":private-test", "wb") as stream:
            stream.write(b"not a real secret")
        summary = self.snapshot()
        self.assertFalse(summary["preservation_complete"])
        self.assertEqual(summary["counts"]["files"], 1)
        self.assertTrue(any(row.get("reason") == "alternate_streams_not_archived" for row in self.read_rows()))
        self.assertFalse(archive.verify(self.output, 0)["preservation_complete"])

    def test_long_windows_path_round_trip(self):
        folder = str(self.source)
        relative = []
        for index in range(5):
            component = f"directory-{index}-" + "x" * 50
            relative.append(component)
            folder = os.path.join(folder, component)
            os.mkdir(archive.native(folder))
        path = os.path.join(folder, "long-file")
        with open(archive.native(path), "wb") as stream:
            stream.write(b"long-path")
        summary = self.snapshot()
        self.assertTrue(summary["preservation_complete"])
        archive.verify(self.output, 0)
        archive.restore(self.output, self.destination)
        restored_path = os.path.join(self.destination, "source", *relative, "long-file")
        with open(archive.native(restored_path), "rb") as stream:
            self.assertEqual(stream.read(), b"long-path")

    def test_key_is_dpapi_protected_and_missing_key_fails(self):
        (self.source / "a").write_bytes(b"content")
        self.snapshot()
        protected = (self.output / "key.dpapi").read_bytes()
        raw = archive.dpapi(protected, False)
        self.assertEqual(len(raw), 32)
        self.assertNotIn(raw, protected)
        (self.output / "key.dpapi").rename(self.output / "key-held.dpapi")
        with self.assertRaises(FileNotFoundError):
            archive.verify(self.output, 0)

    def test_duplicate_labels_overlapping_roots_and_nonempty_output_rejected(self):
        (self.source / "nested").mkdir()
        with self.assertRaisesRegex(archive.ArchiveError, "unique_roots"):
            archive.snapshot([("source", self.source), ("SOURCE", self.source / "nested")], self.output, 0)
        with self.assertRaisesRegex(archive.ArchiveError, "source_roots_overlap"):
            archive.snapshot([("source", self.source), ("nested", self.source / "nested")], self.output, 0)
        self.output.mkdir()
        (self.output / "retain").write_bytes(b"retained")
        with self.assertRaisesRegex(archive.ArchiveError, "output_must_be_empty"):
            self.snapshot()
        self.assertEqual((self.output / "retain").read_bytes(), b"retained")

    def altered_stat(self, info, **changes):
        values = {name: getattr(info, name) for name in dir(info) if name.startswith("st_")}
        return SimpleNamespace(**(values | changes))

    def test_real_executable_lstat_fstat_identity_and_round_trip(self):
        path = self.source / "synthetic.exe"
        path.write_bytes(b"fixture bytes; never executed")
        initial = os.lstat(path)
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
        self.assertEqual(archive.identity(initial), archive.identity(opened))
        self.assertTrue(self.snapshot()["preservation_complete"])
        archive.verify(self.output, 0)
        archive.restore(self.output, self.destination)
        self.assertEqual((self.destination / "source" / path.name).read_bytes(), path.read_bytes())

    def test_directory_allocation_size_change_on_enumeration_is_normalized(self):
        (self.source / "file").write_bytes(b"preserve me")
        original = archive.os.lstat
        target = archive.native(self.source)
        calls = 0

        def allocation_change(path, *args, **kwargs):
            nonlocal calls
            info = original(path, *args, **kwargs)
            if str(path) == target:
                calls += 1
                return self.altered_stat(info, st_size=0 if calls == 1 else 4096)
            return info

        with mock.patch.object(archive.os, "lstat", side_effect=allocation_change):
            summary = self.snapshot()
        self.assertGreaterEqual(calls, 2)
        self.assertTrue(summary["preservation_complete"], self.read_rows())
        self.assertEqual(archive.verify(self.output, 0)["verification"], "PASS")

    def test_identity_keeps_file_size_type_permissions_and_other_stable_fields(self):
        path = self.source / "file.exe"
        path.write_bytes(b"same bytes")
        info = os.lstat(path)
        for field, value in {
            "st_size": info.st_size + 1,
            "st_mtime_ns": info.st_mtime_ns + 1,
            "st_ino": info.st_ino + 1,
            "st_dev": info.st_dev + 1,
            "st_mode": info.st_mode & ~stat.S_IWUSR,
            "st_file_attributes": info.st_file_attributes ^ 1,
            "st_reparse_tag": info.st_reparse_tag ^ 1,
        }.items():
            with self.subTest(field=field):
                self.assertNotEqual(archive.identity(info), archive.identity(self.altered_stat(info, **{field: value})))
        changed_type = stat.S_IFDIR | stat.S_IMODE(info.st_mode)
        self.assertNotEqual(archive.identity(info), archive.identity(self.altered_stat(info, st_mode=changed_type)))

    def test_real_file_mtime_drift_is_held_even_when_bytes_and_size_match(self):
        path = self.source / "changing"
        path.write_bytes(b"same content")
        original = archive.os.fstat
        calls = 0

        def mutate(descriptor):
            nonlocal calls
            calls += 1
            if calls == 2:
                info = path.stat()
                os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 10_000_000_000))
            return original(descriptor)

        with mock.patch.object(archive.os, "fstat", side_effect=mutate):
            self.assertFalse(self.snapshot()["preservation_complete"])
        self.assertTrue(any(row.get("detail", {}).get("reason") == "source_changed_during_read" for row in self.read_rows()))

    def test_real_path_replacement_is_held_even_when_bytes_size_and_mtime_match(self):
        path = self.source / "changing"
        path.write_bytes(b"same content")
        original = archive.os.lstat
        target = archive.native(path)
        calls = 0

        def replace_after_close(name, *args, **kwargs):
            nonlocal calls
            if str(name) == target:
                calls += 1
                if calls == 2:
                    before = path.stat()
                    path.rename(path.with_name("retained-original"))
                    path.write_bytes(b"same content")
                    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
            return original(name, *args, **kwargs)

        with mock.patch.object(archive.os, "lstat", side_effect=replace_after_close):
            self.assertFalse(self.snapshot()["preservation_complete"])
        self.assertTrue(any(row.get("detail", {}).get("reason") == "source_changed_during_read" for row in self.read_rows()))

    def test_directory_membership_drift_is_held_even_if_mtime_restored(self):
        (self.source / "first").write_bytes(b"first")
        original = archive.encrypt_file

        def add_after_read(path, *args):
            info = self.source.stat()
            result = original(path, *args)
            (self.source / "appeared-late").write_bytes(b"not in original enumeration")
            os.utime(self.source, ns=(info.st_atime_ns, info.st_mtime_ns))
            return result

        with mock.patch.object(archive, "encrypt_file", side_effect=add_after_read):
            self.assertFalse(self.snapshot()["preservation_complete"])
        self.assertTrue(any(row.get("reason") == "directory_membership_changed_during_scan" for row in self.read_rows()))

    def test_directory_mtime_drift_still_held(self):
        (self.source / "first").write_bytes(b"first")
        original = archive.encrypt_file

        def change_mtime(path, *args):
            result = original(path, *args)
            info = self.source.stat()
            os.utime(self.source, ns=(info.st_atime_ns, info.st_mtime_ns + 10_000_000_000))
            return result

        with mock.patch.object(archive, "encrypt_file", side_effect=change_mtime):
            self.assertFalse(self.snapshot()["preservation_complete"])
        self.assertTrue(any(row.get("reason") == "directory_changed_during_scan" for row in self.read_rows()))

    def test_selected_snapshot_and_restore_exclude_unselected_siblings(self):
        nested = self.source / "nested"
        nested.mkdir()
        (nested / "selected.exe").write_bytes(b"selected file")
        (nested / "second").write_bytes(b"another selected file")
        (nested / "ignored").write_bytes(b"unselected sibling")
        subtree = self.source / "selected-tree"
        subtree.mkdir()
        (subtree / "empty").mkdir()
        (subtree / "child").write_bytes(b"subtree child")
        (self.source / "ignored-root").write_bytes(b"unselected root sibling")
        selections = ["source:nested/selected.exe", "source:nested/second", "source:selected-tree"]
        summary = archive.snapshot([("source", self.source)], self.output, 0, selections)
        self.assertTrue(summary["preservation_complete"], self.read_rows())
        self.assertEqual(summary["scope"], "selected_paths_only")
        rows = self.read_rows()
        self.assertEqual({row["relative"] for row in rows},
                         {"", "nested", "nested/selected.exe", "nested/second", "selected-tree", "selected-tree/empty", "selected-tree/child"})
        self.assertEqual(archive.verify(self.output, 0)["selections"], summary["selections"])
        archive.restore(self.output, self.destination)
        self.assertEqual((self.destination / "source" / "nested" / "selected.exe").read_bytes(), b"selected file")
        self.assertEqual((self.destination / "source" / "selected-tree" / "child").read_bytes(), b"subtree child")
        self.assertFalse((self.destination / "source" / "nested" / "ignored").exists())
        self.assertFalse((self.destination / "source" / "ignored-root").exists())
        # Selection is covered by the same HMAC as all other summary fields.
        summary["selections"][0]["relative"] = "nested/ignored"
        (self.output / "summary.json").write_bytes(archive.json_bytes(summary))
        with self.assertRaisesRegex(archive.ArchiveError, "summary_authentication_failed"):
            archive.verify(self.output, 0)

    def test_snapshot_rejects_unsafe_missing_or_overlapping_selections_before_output(self):
        nested = self.source / "nested"
        nested.mkdir()
        (nested / "file").write_bytes(b"file")
        (nested / "other").write_bytes(b"another file")
        selections = (["source:nested", "source:nested/file"],
                      ["source:nested/file", "source:NESTED/FILE"],
                      ["source:nested/file", "source:NESTED/other"],
                      ["unknown:nested"], ["source:"], ["source:../outside"],
                      ["source:nested/../file"], ["source:nested/*"], ["source:nested/file:stream"],
                      ["source:C:/absolute"], ["source:nested\\file"], ["source:missing"])
        for selection in selections:
            with self.subTest(selection=selection):
                with self.assertRaises((archive.ArchiveError, FileNotFoundError)):
                    archive.snapshot([("source", self.source)], self.output, 0, selection)
                self.assertFalse(self.output.exists())

    def test_selected_link_ancestor_is_rejected_before_output(self):
        folder = self.source / "linked"
        folder.mkdir()
        (folder / "file").write_bytes(b"never read")
        original = archive.os.lstat
        target = archive.native(folder)

        def mark_link(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            return self.altered_stat(info, st_reparse_tag=0xA000000C) if str(path) == target else info

        with mock.patch.object(archive.os, "lstat", side_effect=mark_link):
            with self.assertRaisesRegex(archive.ArchiveError, "link_or_junction_ancestor"):
                archive.snapshot([("source", self.source)], self.output, 0, ["source:linked/file"])
        self.assertFalse(self.output.exists())

    def test_snapshot_cli_passes_explicit_selection(self):
        with mock.patch.object(archive, "snapshot", return_value={"preservation_complete": True}) as snapshot, \
                mock.patch("builtins.print"):
            result = archive.main(["snapshot", "--root", f"source={self.source}",
                                   "--output", str(self.output), "--select", "source:nested/file", "--progress", "0"])
        self.assertEqual(result, 0)
        snapshot.assert_called_once_with([("source", str(self.source))], str(self.output), 0, ["source:nested/file"])


if __name__ == "__main__":
    unittest.main()
