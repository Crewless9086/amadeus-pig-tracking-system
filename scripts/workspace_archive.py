#!/usr/bin/env python3
"""Local encrypted preservation, verification and explicit empty-folder restore.

No source deletion, permission changes, external communication or plaintext
archive. Requires cryptography and Windows current-user DPAPI for key storage.
The archive preserves file bytes, directory topology and selected metadata;
it is not a volume image, ACL backup, or NTFS alternate-stream backup. Such
streams are detected and held on Windows. A successful snapshot is historical
evidence, never permission to delete a source that may since have changed.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import hmac
import json
import ntpath
import os
import re
import stat
import sys
import uuid
import zipfile
import zlib

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

FORMAT = "amadeus-workspace-archive-v1"
MAGIC = b"AWAR1\x00"
AAD = FORMAT.encode("ascii")
CHUNK = 1024 * 1024
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
LINK_TAGS = {0xA0000003, 0xA000000C}  # mount point / symbolic link


class ArchiveError(RuntimeError):
    """A preservation or restoration gate failed."""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def native(path):
    value = os.path.abspath(os.fspath(path))
    if os.name != "nt" or value.startswith("\\\\?\\"):
        return value
    return "\\\\?\\UNC\\" + value[2:] if value.startswith("\\\\") else "\\\\?\\" + value


def canon(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def within(path, root):
    try:
        return os.path.commonpath([canon(path), canon(root)]) == canon(root)
    except ValueError:
        return False


def is_link(info):
    return stat.S_ISLNK(info.st_mode) or getattr(info, "st_reparse_tag", 0) in LINK_TAGS


def no_link_ancestors(path):
    """Do not resolve links, including an existing ancestor of a new path."""
    absolute = os.path.abspath(os.fspath(path))
    chain = []
    while True:
        chain.append(absolute)
        parent = os.path.dirname(absolute)
        if parent == absolute:
            break
        absolute = parent
    for candidate in reversed(chain):
        try:
            info = os.lstat(native(candidate))
        except FileNotFoundError:
            continue
        if is_link(info):
            raise ArchiveError("link_or_junction_ancestor")


def relative_parts(value, allow_empty=False):
    if value == "" and allow_empty:
        return []
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ArchiveError("unsafe_relative_path")
    if ntpath.splitdrive(value)[0] or value.startswith("/"):
        raise ArchiveError("unsafe_relative_path")
    parts = value.split("/")
    for part in parts:
        # Colon can select an NTFS alternate data stream. Trailing spaces/dots
        # and DOS device names have alias semantics outside extended paths.
        if (not part or part in {".", ".."} or ":" in part or
                part.endswith((" ", ".")) or
                part.split(".", 1)[0].upper() in
                {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                 *(f"LPT{i}" for i in range(1, 10))}):
            raise ArchiveError("unsafe_relative_path")
    return parts


def identity(info):
    # Windows infers regular-file execute bits from the pathname (.exe etc.)
    # for lstat, but not from an open handle for fstat. Directory allocation
    # size can also change merely on enumeration. Neither is content identity.
    # Keep type, read/write bits, file size, mtime, inode/device and attributes.
    mode, size = info.st_mode, info.st_size
    if os.name == "nt":
        if stat.S_ISREG(mode):
            mode &= ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        elif stat.S_ISDIR(mode):
            size = None
    # Python 3.12 Windows lstat/fstat legacy ctime values can disagree too.
    return (info.st_dev, info.st_ino, mode, size,
            info.st_mtime_ns, (info.st_ctime_ns if os.name != "nt" else None),
            getattr(info, "st_file_attributes", 0),
            getattr(info, "st_reparse_tag", 0))


def metadata(info):
    return {"size": info.st_size, "mtime_ns": info.st_mtime_ns,
            "ctime_ns": info.st_ctime_ns, "mode": info.st_mode,
            "device": info.st_dev, "inode": info.st_ino,
            "file_attributes": getattr(info, "st_file_attributes", 0),
            "reparse_tag": getattr(info, "st_reparse_tag", 0)}


def error_code(exc):
    # Do not echo exception messages: they may include content or credentials.
    return {"error": type(exc).__name__, "errno": getattr(exc, "errno", None),
            "winerror": getattr(exc, "winerror", None),
            "reason": str(exc) if isinstance(exc, ArchiveError) else "read_failed"}


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def digest_file(path):
    result = hashlib.sha256()
    with open(native(path), "rb") as stream:
        while block := stream.read(CHUNK):
            result.update(block)
    return result.hexdigest()


def dpapi(data, protect):
    if os.name != "nt":
        raise ArchiveError("Windows_current_user_DPAPI_required")

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    incoming = Blob(len(data), buffer)
    outgoing = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = crypt.CryptProtectData if protect else crypt.CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                   wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    # CRYPTPROTECT_UI_FORBIDDEN; LOCAL_MACHINE deliberately NOT selected.
    if not fn(ctypes.byref(incoming), None, None, None, None, 1,
              ctypes.byref(outgoing)):
        raise ArchiveError("DPAPI_failed")
    try:
        return ctypes.string_at(outgoing.pbData, outgoing.cbData)
    finally:
        kernel.LocalFree(outgoing.pbData)


def alternate_streams(path):
    """Names only; never read alternate streams or change source metadata."""
    if os.name != "nt":
        return []

    class StreamData(ctypes.Structure):
        _fields_ = [("size", ctypes.c_longlong), ("name", wintypes.WCHAR * 296)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.FindFirstStreamW.argtypes = [wintypes.LPCWSTR, ctypes.c_int,
                                       ctypes.POINTER(StreamData), wintypes.DWORD]
    kernel.FindFirstStreamW.restype = wintypes.HANDLE
    kernel.FindNextStreamW.argtypes = [wintypes.HANDLE, ctypes.POINTER(StreamData)]
    kernel.FindNextStreamW.restype = wintypes.BOOL
    kernel.FindClose.argtypes = [wintypes.HANDLE]
    kernel.FindClose.restype = wintypes.BOOL
    item = StreamData()
    handle = kernel.FindFirstStreamW(native(path), 0, ctypes.byref(item), 0)
    invalid = ctypes.c_void_p(-1).value
    if handle == invalid:
        error = ctypes.get_last_error()
        if error in (38,):  # ERROR_HANDLE_EOF: no stream (e.g. directory)
            return []
        raise OSError(error, "stream_enumeration_failed")
    names = []
    try:
        while True:
            if item.name != "::$DATA":
                names.append(item.name)
            if not kernel.FindNextStreamW(handle, ctypes.byref(item)):
                if ctypes.get_last_error() != 38:
                    raise OSError(ctypes.get_last_error(), "stream_enumeration_failed")
                break
    finally:
        kernel.FindClose(handle)
    return names


def encrypt_file(path, initial, spool, key):
    """One read, hash and encrypt; reject mutation or replacement while reading."""
    nonce = os.urandom(12)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(AAD)
    compressor = zlib.compressobj(level=1)
    digest = hashlib.sha256()
    total = 0
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(native(path), flags)
    with os.fdopen(descriptor, "rb") as source, open(native(spool), "xb") as target:
        before = os.fstat(source.fileno())
        if is_link(before) or not stat.S_ISREG(before.st_mode) or identity(before) != identity(initial):
            raise ArchiveError("source_changed_before_read")
        target.write(MAGIC + nonce)
        while block := source.read(CHUNK):
            total += len(block)
            digest.update(block)
            target.write(encryptor.update(compressor.compress(block)))
        target.write(encryptor.update(compressor.flush()))
        target.write(encryptor.finalize())
        target.write(encryptor.tag)
        after = os.fstat(source.fileno())
    current = os.lstat(native(path))
    if identity(before) != identity(after) or identity(after) != identity(current) or total != before.st_size:
        raise ArchiveError("source_changed_during_read")
    return digest.hexdigest(), total


def decode_object(stream, info, key, expected_sha, expected_size, sink=None):
    """Bounded-memory decrypt/decompress. Caller must keep output quarantined."""
    if info.file_size < len(MAGIC) + 12 + 16:
        raise ArchiveError("object_truncated")
    header = stream.read(len(MAGIC) + 12)
    if header[:len(MAGIC)] != MAGIC:
        raise ArchiveError("object_format_invalid")
    decryptor = Cipher(algorithms.AES(key), modes.GCM(header[len(MAGIC):])).decryptor()
    decryptor.authenticate_additional_data(AAD)
    decompressor = zlib.decompressobj()
    digest = hashlib.sha256()
    count = 0

    def consume(compressed):
        nonlocal count
        while compressed:
            plain = decompressor.decompress(compressed, CHUNK)
            compressed = decompressor.unconsumed_tail
            count += len(plain)
            if count > expected_size:
                raise ArchiveError("object_size_exceeded")
            digest.update(plain)
            if sink:
                sink.write(plain)

    remaining = info.file_size - len(header) - 16
    while remaining:
        block = stream.read(min(CHUNK, remaining))
        if not block:
            raise ArchiveError("object_truncated")
        remaining -= len(block)
        consume(decryptor.update(block))
    tag = stream.read(16)
    if len(tag) != 16 or stream.read(1):
        raise ArchiveError("object_length_invalid")
    consume(decryptor.finalize_with_tag(tag))
    if not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail:
        raise ArchiveError("object_compression_invalid")
    if count != expected_size or digest.hexdigest() != expected_sha:
        raise ArchiveError("object_hash_or_size_mismatch")
    return count


def snapshot_selections(roots, selections):
    """Validate explicit supplementary scope before creating archive output."""
    roots_by_label = dict(roots)
    wanted = []
    ancestor_spellings = {}
    for selection in selections or []:
        label, separator, relative = selection.partition(":")
        if not separator or label not in roots_by_label:
            raise ArchiveError("snapshot_selection_invalid")
        parts = relative_parts(relative)
        if any(any(character in '<>"|?*' or ord(character) < 32 for character in part)
               for part in parts):
            raise ArchiveError("unsafe_relative_path")
        folded = relative.casefold()
        if any(label == other_label and
               (folded == other.casefold() or folded.startswith(other.casefold() + "/") or
                other.casefold().startswith(folded + "/")) for other_label, other in wanted):
            raise ArchiveError("snapshot_selections_overlap")
        for depth in range(1, len(parts)):
            ancestor = "/".join(parts[:depth])
            key = (label, ancestor.casefold())
            if ancestor_spellings.setdefault(key, ancestor) != ancestor:
                raise ArchiveError("snapshot_selection_case_alias")
        path = os.path.join(roots_by_label[label], *parts)
        no_link_ancestors(path)
        info = os.lstat(native(path))
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise ArchiveError("snapshot_selection_unsupported_type")
        # Unknown name-surrogate reparse points must not redirect selection.
        for depth in range(len(parts) + 1):
            ancestor = os.path.join(roots_by_label[label], *parts[:depth])
            if getattr(os.lstat(native(ancestor)), "st_reparse_tag", 0) & 0x20000000:
                raise ArchiveError("snapshot_selection_reparse_ancestor")
        wanted.append((label, relative))
    return wanted


def directory_members(path):
    with os.scandir(native(path)) as scan:
        return sorted((entry.name for entry in scan), key=lambda name: (name.casefold(), name))


def snapshot(roots, output, progress=2000, selections=None):
    """Read roots or explicit selected scope; any hold makes that scope incomplete."""
    started = utc_now()
    output = os.path.abspath(os.fspath(output))
    if not roots or len({label.lower() for label, _ in roots}) != len(roots):
        raise ArchiveError("unique_roots_required")
    roots = [(label, os.path.abspath(os.fspath(path))) for label, path in roots]
    for label, root in roots:
        if not LABEL.fullmatch(label):
            raise ArchiveError("invalid_root_label")
        if within(output, root) or within(root, output):
            raise ArchiveError("output_and_source_must_be_disjoint")
        # Root links become holds; ancestor links cannot be traversed to reach it.
        no_link_ancestors(os.path.dirname(root))
    for index, (_, root) in enumerate(roots):
        if any(within(root, other) or within(other, root) for _, other in roots[:index]):
            raise ArchiveError("source_roots_overlap")
    wanted = snapshot_selections(roots, selections)
    no_link_ancestors(output)
    os.makedirs(native(output), exist_ok=True)
    if os.listdir(native(output)):
        raise ArchiveError("output_must_be_empty")
    key = os.urandom(32)
    with open(native(os.path.join(output, "key.dpapi")), "xb") as handle:
        handle.write(dpapi(key, True))
    archive_path = os.path.join(output, "objects.zip")
    manifest_path = os.path.join(output, "manifest.jsonl")
    counts = {"files": 0, "directories": 0, "holds": 0, "source_bytes": 0,
              "unique_objects": 0, "unique_bytes": 0}
    seen = set()
    entries = 0
    with zipfile.ZipFile(native(archive_path), "x", compression=zipfile.ZIP_STORED,
                         allowZip64=True) as archive, open(native(manifest_path), "xb") as manifest:
        def record(value):
            nonlocal entries
            manifest.write(json_bytes(value) + b"\n")
            entries += 1
            if progress and entries % progress == 0:
                print(json.dumps({"progress_entries": entries, **counts}), flush=True)

        def hold(label, relative, reason, **extra):
            counts["holds"] += 1
            record({"type": "hold", "label": label, "relative": relative,
                    "reason": reason, **extra})

        def walk(label, root, relative=""):
            path = os.path.join(root, *relative.split("/")) if relative else root
            base = {"label": label, "relative": relative}
            spool = None
            try:
                info = os.lstat(native(path))
                if is_link(info):
                    hold(label, relative, "link_or_junction", metadata=metadata(info))
                    return
                # Unknown non-cloud reparse types are not followed.
                tag = getattr(info, "st_reparse_tag", 0)
                if tag and tag & 0x20000000:
                    hold(label, relative, "name_surrogate_reparse", metadata=metadata(info))
                    return
                if stat.S_ISDIR(info.st_mode):
                    counts["directories"] += 1
                    record({"type": "directory", **base, "metadata": metadata(info)})
                    streams = alternate_streams(path)
                    if streams:
                        hold(label, relative, "alternate_streams_not_archived", streams=streams)
                    included = not wanted or any(label == chosen_label and
                        (relative == chosen or relative.startswith(chosen + "/"))
                        for chosen_label, chosen in wanted)
                    if included:
                        children = directory_members(path)
                    else:
                        # Preserve only the necessary ancestor topology. Do not
                        # scan/capture unselected siblings of selected paths.
                        prefix = relative + "/" if relative else ""
                        children = sorted({chosen[len(prefix):].split("/", 1)[0]
                            for chosen_label, chosen in wanted
                            if label == chosen_label and chosen.startswith(prefix)},
                            key=lambda name: (name.casefold(), name))
                    for name in children:
                        child_relative = relative + "/" + name if relative else name
                        walk(label, root, child_relative)
                    if included and children != directory_members(path):
                        hold(label, relative, "directory_membership_changed_during_scan")
                    if identity(info) != identity(os.lstat(native(path))):
                        hold(label, relative, "directory_changed_during_scan")
                    return
                if not stat.S_ISREG(info.st_mode):
                    hold(label, relative, "unsupported_file_type", metadata=metadata(info))
                    return
                relative_parts(relative)
                streams = alternate_streams(path)
                spool = os.path.join(output, "pending-" + uuid.uuid4().hex + ".enc")
                digest, size = encrypt_file(path, info, spool, key)
                if digest not in seen:
                    archive.write(native(spool), "objects/" + digest + ".enc",
                                  compress_type=zipfile.ZIP_STORED)
                    seen.add(digest)
                    counts["unique_objects"] += 1
                    counts["unique_bytes"] += size
                counts["files"] += 1
                counts["source_bytes"] += size
                record({"type": "file", **base, "sha256": digest, "metadata": metadata(info)})
                if streams:
                    hold(label, relative, "alternate_streams_not_archived", streams=streams)
            except (OSError, ArchiveError) as exc:
                hold(label, relative, "entry_not_preserved", detail=error_code(exc))
            finally:
                if spool and os.path.exists(native(spool)):
                    # Only the freshly-created encrypted spool is removed.
                    os.unlink(native(spool))

        for label, root in roots:
            if not wanted or any(label == chosen_label for chosen_label, _ in wanted):
                walk(label, root)

    summary = {"format": FORMAT, "started_at": started, "finished_at": utc_now(),
               "roots": [{"label": label, "path": root} for label, root in roots],
               "counts": counts, "manifest_entries": entries,
               "archive_sha256": digest_file(archive_path),
               "manifest_sha256": digest_file(manifest_path),
               "key_file_sha256": digest_file(os.path.join(output, "key.dpapi")),
               "preservation_complete": counts["holds"] == 0,
               "deletion_authorized": False,
               "metadata_scope": "file bytes, directories, size, mtime, mode, identity; no ACL restore"}
    if wanted:
        summary["scope"] = "selected_paths_only"
        summary["selections"] = [{"label": label, "relative": relative} for label, relative in wanted]
    summary["summary_hmac_sha256"] = hmac.new(key, json_bytes(summary), hashlib.sha256).hexdigest()
    with open(native(os.path.join(output, "summary.json")), "xb") as handle:
        handle.write(json_bytes(summary) + b"\n")
    return summary


def load_archive(directory):
    no_link_ancestors(directory)
    for name in ("summary.json", "key.dpapi", "manifest.jsonl", "objects.zip"):
        no_link_ancestors(os.path.join(directory, name))
    with open(native(os.path.join(directory, "summary.json")), "rb") as handle:
        summary = json.load(handle)
    key_path = os.path.join(directory, "key.dpapi")
    with open(native(key_path), "rb") as handle:
        key = dpapi(handle.read(), False)
    if len(key) != 32:
        raise ArchiveError("key_length_invalid")
    signature = summary.get("summary_hmac_sha256", "")
    unsigned = {key: value for key, value in summary.items() if key != "summary_hmac_sha256"}
    if not hmac.compare_digest(signature, hmac.new(key, json_bytes(unsigned), hashlib.sha256).hexdigest()):
        raise ArchiveError("summary_authentication_failed")
    if summary.get("format") != FORMAT:
        raise ArchiveError("unknown_archive_format")
    for name, field in (("objects.zip", "archive_sha256"), ("manifest.jsonl", "manifest_sha256"),
                        ("key.dpapi", "key_file_sha256")):
        if digest_file(os.path.join(directory, name)) != summary.get(field):
            raise ArchiveError(field + "_mismatch")
    return summary, key


def read_manifest(directory, summary):
    labels = {root["label"] for root in summary["roots"]}
    if len(labels) != len(summary["roots"]) or any(not LABEL.fullmatch(label) for label in labels):
        raise ArchiveError("manifest_root_invalid")
    entries, sizes, occupied = [], {}, {}
    with open(native(os.path.join(directory, "manifest.jsonl")), "rb") as handle:
        for line in handle:
            value = json.loads(line)
            kind, label, relative = value.get("type"), value.get("label"), value.get("relative")
            if kind not in {"file", "directory", "hold"} or label not in labels:
                raise ArchiveError("manifest_entry_invalid")
            if kind != "hold":
                relative_parts(relative, allow_empty=kind == "directory")
                location = (label.casefold(), relative.casefold())
                if location in occupied:
                    raise ArchiveError("manifest_path_collision")
                occupied[location] = kind
            if kind == "file":
                digest, size = value.get("sha256", ""), value["metadata"]["size"]
                if not SHA.fullmatch(digest) or not isinstance(size, int) or size < 0:
                    raise ArchiveError("manifest_object_invalid")
                if digest in sizes and sizes[digest] != size:
                    raise ArchiveError("manifest_object_size_conflict")
                sizes[digest] = size
            entries.append(value)
    if len(entries) != summary["manifest_entries"]:
        raise ArchiveError("manifest_entry_count_mismatch")
    for (label, relative), kind in occupied.items():
        if not relative:
            continue
        parent = relative.rpartition("/")[0]
        if occupied.get((label, parent)) != "directory":
            raise ArchiveError("manifest_parent_missing")
    derived = {"files": sum(entry["type"] == "file" for entry in entries),
               "directories": sum(entry["type"] == "directory" for entry in entries),
               "holds": sum(entry["type"] == "hold" for entry in entries),
               "source_bytes": sum(entry["metadata"]["size"] for entry in entries if entry["type"] == "file"),
               "unique_objects": len(sizes), "unique_bytes": sum(sizes.values())}
    if derived != summary["counts"] or summary["preservation_complete"] != (derived["holds"] == 0):
        raise ArchiveError("manifest_summary_count_mismatch")
    return entries, sizes


def inspect_objects(archive, sizes):
    members = archive.infolist()
    expected = {"objects/" + digest + ".enc" for digest in sizes}
    if len(members) != len(expected) or {item.filename for item in members} != expected:
        raise ArchiveError("archive_object_inventory_mismatch")
    for item in members:
        if item.compress_type != zipfile.ZIP_STORED or item.flag_bits & 1:
            raise ArchiveError("archive_object_encoding_invalid")


def verify(directory, progress=2000):
    summary, key = load_archive(directory)
    _, sizes = read_manifest(directory, summary)
    objects, total = 0, 0
    with zipfile.ZipFile(native(os.path.join(directory, "objects.zip"))) as archive:
        inspect_objects(archive, sizes)
        for digest, size in sizes.items():
            info = archive.getinfo("objects/" + digest + ".enc")
            with archive.open(info) as source:
                total += decode_object(source, info, key, digest, size)
            objects += 1
            if progress and objects % progress == 0:
                print(json.dumps({"verified_objects": objects, "verified_bytes": total}), flush=True)
    return {"verified_at": utc_now(), "verification": "PASS",
            "archive_sha256": summary["archive_sha256"],
            "manifest_sha256": summary["manifest_sha256"],
            "verified_objects": objects, "verified_bytes": total,
            "holds": summary["counts"]["holds"],
            "preservation_complete": summary["preservation_complete"],
            "scope": summary.get("scope", "whole_roots"),
            "selections": summary.get("selections", []),
            "deletion_authorized": False}


def restore(directory, destination, selections=None):
    """Restore label/relative paths only into a new or empty explicit destination."""
    summary, key = load_archive(directory)
    entries, sizes = read_manifest(directory, summary)
    destination = os.path.abspath(os.fspath(destination))
    if within(destination, directory) or within(directory, destination):
        raise ArchiveError("restore_and_archive_must_be_disjoint")
    for root in summary["roots"]:
        if within(destination, root["path"]) or within(root["path"], destination):
            raise ArchiveError("restore_and_originals_must_be_disjoint")
    no_link_ancestors(destination)
    if os.path.exists(native(destination)) and (not os.path.isdir(native(destination)) or os.listdir(native(destination))):
        raise ArchiveError("restore_destination_must_be_empty")
    wanted = []
    for selection in selections or []:
        label, sep, relative = selection.partition(":")
        if not sep or label not in {root["label"] for root in summary["roots"]}:
            raise ArchiveError("restore_selection_invalid")
        relative_parts(relative, allow_empty=True)
        if not any(entry["label"] == label and entry["relative"] == relative for entry in entries):
            raise ArchiveError("restore_selection_not_found")
        wanted.append((label, relative))

    def selected(entry):
        return not wanted or any(entry["label"] == label and
                                 (not relative or entry["relative"] == relative or
                                  entry["relative"].startswith(relative + "/"))
                                 for label, relative in wanted)

    targets = [entry for entry in entries if selected(entry)]
    if any(entry["type"] == "hold" for entry in targets):
        raise ArchiveError("restore_selection_has_preservation_holds")
    with zipfile.ZipFile(native(os.path.join(directory, "objects.zip"))) as archive:
        inspect_objects(archive, sizes)
        # Authenticate all selected content before any plaintext output.
        for digest in {entry["sha256"] for entry in targets if entry["type"] == "file"}:
            info = archive.getinfo("objects/" + digest + ".enc")
            with archive.open(info) as source:
                decode_object(source, info, key, digest, sizes[digest])
        os.makedirs(native(destination), exist_ok=True)
        for entry in sorted(targets, key=lambda item: (item["relative"].count("/"), item["type"] != "directory")):
            parts = relative_parts(entry["relative"], allow_empty=entry["type"] == "directory")
            path = os.path.join(destination, entry["label"], *parts)
            if not within(path, destination):
                raise ArchiveError("restore_path_escape")
            no_link_ancestors(path)
            if entry["type"] == "directory":
                os.makedirs(native(path), exist_ok=True)
                continue
            os.makedirs(native(os.path.dirname(path)), exist_ok=True)
            no_link_ancestors(path)
            info = archive.getinfo("objects/" + entry["sha256"] + ".enc")
            # xb prevents overwriting even if another process created this path.
            with archive.open(info) as source, open(native(path), "xb") as target:
                decode_object(source, info, key, entry["sha256"], entry["metadata"]["size"], target)
            if digest_file(path) != entry["sha256"]:
                raise ArchiveError("restored_file_hash_mismatch")
            stamp = entry["metadata"]["mtime_ns"]
            os.utime(native(path), ns=(stamp, stamp))
        for entry in sorted((entry for entry in targets if entry["type"] == "directory"),
                            key=lambda item: item["relative"].count("/"), reverse=True):
            path = os.path.join(destination, entry["label"], *relative_parts(entry["relative"], True))
            stamp = entry["metadata"]["mtime_ns"]
            os.utime(native(path), ns=(stamp, stamp))
    return {"restored_at": utc_now(), "restore": "PASS",
            "files": sum(entry["type"] == "file" for entry in targets),
            "directories": sum(entry["type"] == "directory" for entry in targets),
            "archive_sha256": summary["archive_sha256"],
            "manifest_sha256": summary["manifest_sha256"], "originals_modified": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("snapshot")
    create.add_argument("--root", action="append", required=True, help="LABEL=absolute source directory")
    create.add_argument("--output", required=True, help="new or empty archive directory, outside sources")
    create.add_argument("--progress", type=int, default=2000)
    create.add_argument("--select", action="append", help="LABEL:relative/path (repeatable); supplementary selected scope only; default whole roots")
    check = commands.add_parser("verify")
    check.add_argument("--archive", required=True)
    check.add_argument("--progress", type=int, default=2000)
    recover = commands.add_parser("restore")
    recover.add_argument("--archive", required=True)
    recover.add_argument("--destination", required=True)
    recover.add_argument("--select", action="append", help="LABEL:relative/path (repeatable); default all")
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            roots = []
            for item in args.root:
                label, separator, path = item.partition("=")
                if not separator or not os.path.isabs(path):
                    raise ArchiveError("root_requires_label_and_absolute_path")
                roots.append((label, path))
            result = snapshot(roots, args.output, args.progress, args.select)
        elif args.command == "verify":
            result = verify(args.archive, args.progress)
        else:
            result = restore(args.archive, args.destination, args.select)
        print(json.dumps(result, sort_keys=True), flush=True)
        return 2 if result.get("preservation_complete") is False else 0
    except (ArchiveError, OSError, ValueError, KeyError, TypeError, InvalidTag,
            zlib.error, zipfile.BadZipFile) as exc:
        print(json.dumps({"result": "FAIL", **error_code(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
