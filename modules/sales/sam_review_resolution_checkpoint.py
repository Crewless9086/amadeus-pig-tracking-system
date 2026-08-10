"""Resumable, cutoff-bound evidence capture for SAM review resolution."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from modules.sales.sam_review_obligation_resolution import canonical_sha256


CHECKPOINT_VERSION = "sam_review_resolution_checkpoint_v1"


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def checkpoint_identity(*, represented_pig_id: str, cutoff_at: str,
                        review_ids: Iterable[str]) -> str:
    material = {
        "version": CHECKPOINT_VERSION,
        "represented_pig_id": str(represented_pig_id),
        "cutoff_at": str(cutoff_at),
        "review_ids": sorted(str(value) for value in review_ids),
    }
    return "SAM-REVIEW-SNAPSHOT-" + canonical_sha256(material)[:24].upper()


class ResolutionCheckpoint:
    """Filesystem checkpoint with immutable allowlist and per-item evidence."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.metadata_path = self.root / "checkpoint.json"
        self.reviews_path = self.root / "reviews"
        self.conversations_path = self.root / "conversations"

    def initialize(self, *, represented_pig_id: str, cutoff_at: str,
                   review_ids: Iterable[str], conversation_ids: Iterable[str]) -> dict:
        review_ids = sorted(set(str(value) for value in review_ids))
        conversation_ids = sorted(set(str(value) for value in conversation_ids))
        if not review_ids or not conversation_ids:
            raise ValueError("nonempty_snapshot_population_required")
        metadata = {
            "version": CHECKPOINT_VERSION,
            "snapshot_id": checkpoint_identity(
                represented_pig_id=represented_pig_id,
                cutoff_at=cutoff_at,
                review_ids=review_ids,
            ),
            "represented_pig_id": represented_pig_id,
            "cutoff_at": cutoff_at,
            "review_ids": review_ids,
            "conversation_ids": conversation_ids,
            "review_allowlist_sha256": canonical_sha256(review_ids),
            "conversation_allowlist_sha256": canonical_sha256(conversation_ids),
        }
        if self.metadata_path.exists():
            existing = self.load_metadata()
            if existing != metadata:
                raise ValueError("checkpoint_identity_conflict")
            return existing
        atomic_write_json(self.metadata_path, metadata)
        return metadata

    def load_metadata(self) -> dict:
        value = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        if value.get("version") != CHECKPOINT_VERSION:
            raise ValueError("checkpoint_version_mismatch")
        expected = checkpoint_identity(
            represented_pig_id=value.get("represented_pig_id"),
            cutoff_at=value.get("cutoff_at"),
            review_ids=value.get("review_ids") or [],
        )
        if value.get("snapshot_id") != expected:
            raise ValueError("checkpoint_digest_mismatch")
        return value

    def store_review(self, review: Mapping[str, Any], *, verification: bool = False) -> bool:
        metadata = self.load_metadata()
        review_id = str(review.get("review_event_id") or "")
        if review_id not in metadata["review_ids"]:
            raise ValueError("review_outside_allowlist")
        suffix = ".verify.json" if verification else ".json"
        path = self.reviews_path / f"{review_id}{suffix}"
        packet = dict(review)
        if path.exists():
            if json.loads(path.read_text(encoding="utf-8")) != packet:
                raise ValueError("immutable_review_checkpoint_conflict")
            return False
        atomic_write_json(path, packet)
        return True

    def store_conversation(self, conversation_id: str,
                           evidence: Mapping[str, Any], *, verification: bool = False) -> bool:
        metadata = self.load_metadata()
        conversation_id = str(conversation_id)
        if conversation_id not in metadata["conversation_ids"]:
            raise ValueError("conversation_outside_allowlist")
        packet = dict(evidence)
        if str(packet.get("conversation_id") or "") != conversation_id:
            raise ValueError("conversation_identity_mismatch")
        if str(packet.get("cutoff_at") or "") != metadata["cutoff_at"]:
            raise ValueError("conversation_cutoff_mismatch")
        chronology = packet.get("public_chronology")
        if not isinstance(chronology, list) or not chronology:
            raise ValueError("complete_public_chronology_required")
        if packet.get("chronology_sha256") != canonical_sha256(chronology):
            raise ValueError("conversation_chronology_digest_mismatch")
        suffix = ".verify.json" if verification else ".json"
        path = self.conversations_path / f"{conversation_id}{suffix}"
        if path.exists():
            if json.loads(path.read_text(encoding="utf-8")) != packet:
                raise ValueError("conversation_checkpoint_conflict")
            return False
        atomic_write_json(path, packet)
        return True

    def validate_complete(self, *, expected_review_count: int,
                          expected_conversation_count: int) -> dict:
        metadata = self.load_metadata()
        if len(metadata["review_ids"]) != expected_review_count:
            raise ValueError("exact_review_population_required")
        if len(metadata["conversation_ids"]) != expected_conversation_count:
            raise ValueError("exact_conversation_population_required")
        review_packets = []
        for review_id in metadata["review_ids"]:
            path = self.reviews_path / f"{review_id}.json"
            verify_path = self.reviews_path / f"{review_id}.verify.json"
            if not path.exists() or not verify_path.exists():
                raise ValueError(f"review_checkpoint_missing:{review_id}")
            packet = json.loads(path.read_text(encoding="utf-8"))
            verified_packet = json.loads(verify_path.read_text(encoding="utf-8"))
            if str(packet.get("review_event_id") or "") != review_id:
                raise ValueError(f"review_checkpoint_identity_mismatch:{review_id}")
            if packet != verified_packet:
                raise ValueError(f"review_changed_during_snapshot:{review_id}")
            review_packets.append(packet)
        conversation_packets = {}
        for conversation_id in metadata["conversation_ids"]:
            captured_path = self.conversations_path / f"{conversation_id}.json"
            verified_path = self.conversations_path / f"{conversation_id}.verify.json"
            if not captured_path.exists() or not verified_path.exists():
                raise ValueError(f"conversation_verification_missing:{conversation_id}")
            captured = json.loads(captured_path.read_text(encoding="utf-8"))
            verified = json.loads(verified_path.read_text(encoding="utf-8"))
            stable_keys = (
                "account_id", "inbox_id", "contact_id", "conversation_id",
                "cutoff_at", "public_chronology", "chronology_sha256",
            )
            if any(captured.get(key) != verified.get(key) for key in stable_keys):
                raise ValueError(f"conversation_changed_during_snapshot:{conversation_id}")
            conversation_packets[conversation_id] = captured
        return {
            "metadata": metadata,
            "reviews": review_packets,
            "conversations": conversation_packets,
            "review_export_sha256": canonical_sha256(review_packets),
            "provider_export_sha256": canonical_sha256(conversation_packets),
        }
