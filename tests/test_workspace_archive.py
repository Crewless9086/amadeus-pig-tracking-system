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
import unittest
from unittest import mock
import uuid
import zipfile

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "workspace_archive.py"
SPEC = importlib.util.spec_from_file_location("workspace_archive", MODULE_PATH)
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)
TEST_ROOT = Path(r"C:\Amadeus\.runtime\archive-tests")


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


if __name__ == "__main__":
    unittest.main()
