"""Resumable production reconciliation for immutable SAM review obligations.

The capture phases are read-only. ``--record`` invokes only the governed,
append-only resolution RPC after a complete two-pass provider verification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.sales.sam_review_obligation_resolution import (  # noqa:E402
    build_resolution_manifest, canonical_sha256, record_resolution_event,
    successor_work_item_identity,
)
from modules.sales.sam_review_resolution_checkpoint import (  # noqa:E402
    ResolutionCheckpoint, atomic_write_json,
)

EXPECTED_REVIEWS = 362
EXPECTED_CONVERSATIONS = 149
REPRESENTED_PIG_ID = "PIG-2026-1AC2"


def parse_timestamp(value) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("provider_timestamp_timezone_required")
    return parsed.astimezone(timezone.utc)


def iso_timestamp(value) -> str:
    return parse_timestamp(value).isoformat()


def bound_evidence(source: dict, prefix: str) -> dict:
    payload = dict(source)
    digest = canonical_sha256(payload)
    return {
        **source,
        "evidence_id": f"{prefix}-{digest[:24].upper()}",
        "evidence_sha256": digest,
        "evidence_payload": payload,
    }


class ProductionEvidenceSource:
    def __init__(self):
        load_dotenv(ROOT / ".env", override=False)
        fallback = Path(
            r"C:\Users\charl\OneDrive\1. Amadeus\AGENTS\amadeus-pig-tracking-system\.env"
        )
        if fallback.exists():
            load_dotenv(fallback, override=False)
        self.database_url = os.getenv("SUPABASE_DB_URL") or os.environ["DATABASE_URL"]
        self.chatwoot_base = os.environ["CHATWOOT_BASE_URL"].rstrip("/")
        self.account_id = str(os.environ["CHATWOOT_ACCOUNT_ID"])
        self.chatwoot_token = os.environ["CHATWOOT_API_ACCESS_TOKEN"]

    def db(self, *, read_only=True):
        options = "-c statement_timeout=60000"
        if read_only:
            options += " -c default_transaction_read_only=on"
        return psycopg.connect(self.database_url, connect_timeout=10, options=options)

    def api(self, path: str, params: dict | None = None):
        url = f"{self.chatwoot_base}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url, headers={"api_access_token": self.chatwoot_token, "Accept": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read())

    def population(self):
        with self.db() as connection:
            rows = connection.execute(
                """select review_event_id,chatwoot_conversation_id
                     from public.sam_live_stock_conversation_review_events
                    where decision_json::text like %s
                    order by review_event_id""",
                (f"%{REPRESENTED_PIG_ID}%",),
            ).fetchall()
        review_ids = [str(row[0]) for row in rows]
        conversation_ids = sorted({str(row[1]) for row in rows})
        if len(review_ids) != EXPECTED_REVIEWS or len(conversation_ids) != EXPECTED_CONVERSATIONS:
            raise RuntimeError(
                f"production_population_changed:{len(review_ids)}:{len(conversation_ids)}"
            )
        return review_ids, conversation_ids

    def review_page(self, review_ids: list[str]) -> list[dict]:
        with self.db() as connection:
            rows = connection.execute(
                """select review_event_id,chatwoot_conversation_id,chatwoot_message_id,
                          decision_json::text,event_source,safe_to_send,owner_send_required,
                          no_reply_recommended,escalation_required,created_at
                     from public.sam_live_stock_conversation_review_events
                    where review_event_id=any(%s)
                    order by review_event_id""",
                (review_ids,),
            ).fetchall()
        result = []
        for row in rows:
            decision_text = row[3]
            result.append({
                "review_event_id": str(row[0]),
                "chatwoot_conversation_id": str(row[1]),
                "chatwoot_message_id": str(row[2]),
                "decision_json": json.loads(decision_text),
                "decision_json_text": decision_text,
                "decision_json_sha256": hashlib.sha256(decision_text.encode()).hexdigest(),
                "event_source": str(row[4]),
                "safe_to_send": bool(row[5]),
                "owner_send_required": bool(row[6]),
                "no_reply_recommended": bool(row[7]),
                "escalation_required": bool(row[8]),
                "created_at": row[9].isoformat(),
            })
        if {row["review_event_id"] for row in result} != set(review_ids):
            raise RuntimeError("incomplete_review_page")
        return result

    def conversation_at_cutoff(self, conversation_id: str, cutoff_at: str) -> dict:
        cutoff = parse_timestamp(cutoff_at)
        conversation = self.api(
            f"/api/v1/accounts/{self.account_id}/conversations/{conversation_id}"
        )
        messages = []
        seen = set()
        before = None
        complete = False
        page_count = 0
        for _ in range(50):
            params = {"before": before} if before is not None else None
            envelope = self.api(
                f"/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/messages",
                params,
            )
            page = envelope.get("payload", envelope) if isinstance(envelope, dict) else envelope
            if not isinstance(page, list):
                raise RuntimeError("chatwoot_message_page_invalid")
            page_count += 1
            added = 0
            for message in page:
                message_id = str(message.get("id") or "")
                if not message_id or message_id in seen:
                    continue
                seen.add(message_id)
                added += 1
                created_at = parse_timestamp(message.get("created_at"))
                if created_at > cutoff or bool(message.get("private")):
                    continue
                content = str(message.get("content") or "")
                attributes = message.get("content_attributes") or {}
                messages.append({
                    "message_id": message_id,
                    "message_type": str(message.get("message_type") or ""),
                    "provider_observed_at": created_at.isoformat(),
                    "provider_status": str(message.get("status") or ""),
                    "sender_id": str((message.get("sender") or {}).get("id") or ""),
                    "in_reply_to": str(attributes.get("in_reply_to") or ""),
                    "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "content_length": len(content),
                })
            if not page or not added or len(page) < 20:
                complete = True
                break
            numeric = [int(str(row.get("id"))) for row in page if str(row.get("id") or "").isdigit()]
            if not numeric:
                raise RuntimeError("chatwoot_pagination_cursor_unavailable")
            next_before = min(numeric)
            if str(next_before) == str(before):
                raise RuntimeError("chatwoot_pagination_did_not_advance")
            before = next_before
        if not complete:
            raise RuntimeError("chatwoot_pagination_incomplete")
        messages.sort(key=lambda row: (row["provider_observed_at"], row["message_id"]))
        if not messages:
            raise RuntimeError("public_chronology_empty_at_cutoff")
        contact_id = str(((conversation.get("meta") or {}).get("sender") or {}).get("id") or "")
        packet = {
            "account_id": self.account_id,
            "inbox_id": str(conversation.get("inbox_id") or ""),
            "contact_id": contact_id,
            "conversation_id": str(conversation_id),
            "cutoff_at": cutoff_at,
            "page_count": page_count,
            "public_chronology": messages,
            "chronology_sha256": canonical_sha256(messages),
        }
        return packet


def capture(source: ProductionEvidenceSource, checkpoint: ResolutionCheckpoint,
            *, page_size: int, expected_reviews: int = EXPECTED_REVIEWS,
            expected_conversations: int = EXPECTED_CONVERSATIONS) -> dict:
    if checkpoint.metadata_path.exists():
        metadata = checkpoint.load_metadata()
        current_reviews, current_conversations = source.population()
        if current_reviews != metadata["review_ids"] or current_conversations != metadata["conversation_ids"]:
            raise RuntimeError("checkpoint_population_became_stale")
    else:
        review_ids, conversation_ids = source.population()
        cutoff_at = datetime.now(timezone.utc).isoformat()
        metadata = checkpoint.initialize(
            represented_pig_id=REPRESENTED_PIG_ID, cutoff_at=cutoff_at,
            review_ids=review_ids, conversation_ids=conversation_ids,
        )
    missing_reviews = [review_id for review_id in metadata["review_ids"]
                       if not (checkpoint.reviews_path / f"{review_id}.json").exists()]
    for offset in range(0, len(missing_reviews), page_size):
        page_ids = missing_reviews[offset:offset + page_size]
        for row in source.review_page(page_ids):
            checkpoint.store_review(row)
    missing_review_verification = [
        review_id for review_id in metadata["review_ids"]
        if not (checkpoint.reviews_path / f"{review_id}.verify.json").exists()
    ]
    for offset in range(0, len(missing_review_verification), page_size):
        page_ids = missing_review_verification[offset:offset + page_size]
        for row in source.review_page(page_ids):
            checkpoint.store_review(row, verification=True)
    missing_conversations = [conversation_id for conversation_id in metadata["conversation_ids"]
                             if not (checkpoint.conversations_path / f"{conversation_id}.json").exists()]
    for conversation_id in missing_conversations:
        checkpoint.store_conversation(
            conversation_id,
            source.conversation_at_cutoff(conversation_id, metadata["cutoff_at"]),
        )
    missing_verification = [conversation_id for conversation_id in metadata["conversation_ids"]
                            if not (checkpoint.conversations_path / f"{conversation_id}.verify.json").exists()]
    for conversation_id in missing_verification:
        checkpoint.store_conversation(
            conversation_id,
            source.conversation_at_cutoff(conversation_id, metadata["cutoff_at"]),
            verification=True,
        )
    return checkpoint.validate_complete(
        expected_review_count=expected_reviews,
        expected_conversation_count=expected_conversations,
    )


def build_evidence(complete: dict) -> dict:
    reviews = complete["reviews"]
    conversations = complete["conversations"]
    latest_review_by_conversation = {}
    for review in reviews:
        conversation_id = review["chatwoot_conversation_id"]
        key = (review["created_at"], review["review_event_id"])
        if conversation_id not in latest_review_by_conversation or key > latest_review_by_conversation[conversation_id][0]:
            latest_review_by_conversation[conversation_id] = (key, review["review_event_id"])
    evidence_by_review = {}
    for review in reviews:
        conversation_id = review["chatwoot_conversation_id"]
        captured = conversations[conversation_id]
        chronology = captured["public_chronology"]
        ids = [row["message_id"] for row in chronology]
        inbound_id = review["chatwoot_message_id"]
        if inbound_id not in ids:
            raise RuntimeError(f"review_inbound_absent_at_cutoff:{review['review_event_id']}")
        index = ids.index(inbound_id)
        later = chronology[index + 1:]
        later_inbounds = [row for row in later if row["message_type"] == "incoming"]
        latest = chronology[-1]
        latest_incoming = next(
            (row for row in reversed(chronology) if row["message_type"] == "incoming"), None
        )
        later_inbound = later_inbounds[-1]["message_id"] if later_inbounds else ""
        successor = None
        if later_inbound and latest["message_type"] == "incoming" and latest["message_id"] == later_inbound:
            successor_source = {
                "work_item_id": successor_work_item_identity(
                    account_id=captured["account_id"], inbox_id=captured["inbox_id"],
                    contact_id=captured["contact_id"], conversation_id=conversation_id,
                    inbound_message_id=later_inbound,
                ),
                "contact_id": captured["contact_id"],
                "conversation_id": conversation_id,
                "inbound_message_id": later_inbound,
                "current_actionable": True,
                "chronology_sha256": captured["chronology_sha256"],
            }
            successor = bound_evidence(successor_source, "SUCCESSOR")
        attributable_outgoing = next(
            (row for row in reversed(later)
             if row["message_type"] == "outgoing" and row["in_reply_to"] == inbound_id),
            None,
        )
        delivery_status = "not_attempted"
        if attributable_outgoing:
            provider_status = attributable_outgoing["provider_status"]
            delivery_status = {
                "read": "provider_read", "delivered": "provider_delivered",
                "sent": "chatwoot_accepted_unverified", "failed": "provider_failed",
            }.get(provider_status, "provider_outcome_ambiguous")
        latest_review = latest_review_by_conversation[conversation_id][1] == review["review_event_id"]
        protected_active = latest_review and bool(
            review["owner_send_required"] or review["escalation_required"]
        )
        window_state = "unknown"
        expires_at = None
        if latest_incoming:
            expires_at = parse_timestamp(latest_incoming["provider_observed_at"]) + timedelta(hours=24)
            window_state = "open" if parse_timestamp(captured["cutoff_at"]) < expires_at else "closed"
        delivery_source = {
            "status": delivery_status,
            "conversation_id": conversation_id,
            "inbound_message_id": inbound_id,
        }
        outgoing = None
        if attributable_outgoing:
            delivery_source["outgoing_message_id"] = attributable_outgoing["message_id"]
            outgoing = {
                "message_id": attributable_outgoing["message_id"],
                "bound_reply_to_inbound_id": inbound_id,
                "content_sha256": attributable_outgoing["content_sha256"],
                "response_class_evidence_id": "CONTENT-REVIEW-REQUIRED",
            }
        evidence = {
            "identity": {
                "review_event_id": review["review_event_id"],
                "account_id": captured["account_id"], "inbox_id": captured["inbox_id"],
                "contact_id": captured["contact_id"], "conversation_id": conversation_id,
                "bound_inbound_message_id": inbound_id,
                "latest_inbound_message_id": latest_incoming["message_id"] if latest_incoming else "",
                "latest_public_message_type": latest["message_type"],
            },
            "public_chronology": chronology,
            "chronology_cutoff_at": chronology[-1]["provider_observed_at"],
            "chronology_sha256": captured["chronology_sha256"],
            "later_inbound_message_id": later_inbound,
            "delivery": bound_evidence(delivery_source, "DELIVERY"),
            "content_obligation": bound_evidence({
                "supported_obligation_answered": False,
                "relied_on_superseded_identity": bool(attributable_outgoing),
            }, "OBLIGATION"),
            "protected_decision": bound_evidence({"active": protected_active}, "PROTECTED"),
            "quarantine": bound_evidence({
                "active": delivery_status in {
                    "chatwoot_accepted_unverified", "provider_outcome_ambiguous"
                }
            }, "QUARANTINE"),
            "whatsapp_window": bound_evidence({
                "state": window_state,
                "expires_at": expires_at.isoformat() if expires_at else None,
            }, "WINDOW"),
            "source_generation": complete["metadata"]["snapshot_id"],
        }
        if outgoing:
            evidence["later_public_outgoing"] = outgoing
        if successor:
            evidence["successor_work_item"] = successor
        evidence_by_review[review["review_event_id"]] = evidence
    return evidence_by_review


def build_manifest(complete: dict) -> dict:
    represented = {
        "represented_pig_id": REPRESENTED_PIG_ID,
        "status": "superseded",
        "canonical_same_animal_pig_id": None,
        "alias_evidence_id": None,
        "same_animal_mapping_prohibited": True,
        "governed_disposition_operation_id": "ZIGAY-DUPLICATE-LITTER-RESOLUTION-20260810",
    }
    manifest = build_resolution_manifest(
        reviews=complete["reviews"],
        evidence_by_review=build_evidence(complete),
        represented_identity=represented,
    )
    if manifest["row_count"] != EXPECTED_REVIEWS:
        raise RuntimeError("exact_manifest_population_required")
    manifest["snapshot_id"] = complete["metadata"]["snapshot_id"]
    manifest["review_export_sha256"] = complete["review_export_sha256"]
    manifest["provider_export_sha256"] = complete["provider_export_sha256"]
    manifest["artifact_sha256"] = canonical_sha256(manifest)
    return manifest


def record_manifest(source: ProductionEvidenceSource, checkpoint: ResolutionCheckpoint,
                    manifest: dict) -> dict:
    receipts_path = checkpoint.root / "record_receipts.json"
    receipts = json.loads(receipts_path.read_text()) if receipts_path.exists() else {}
    for row in manifest["rows"]:
        event_id = row["resolution_event_id"]
        if event_id in receipts:
            continue
        result, status = record_resolution_event(row, database_url=source.database_url)
        if status not in (200, 201) or not result.get("success"):
            raise RuntimeError(f"resolution_record_failed:{event_id}:{result.get('status')}")
        receipts[event_id] = result
        atomic_write_json(receipts_path, receipts)
    with source.db() as connection:
        count = connection.execute(
            "select count(*) from public.sam_review_obligation_resolution_events "
            "where resolution_event_id=any(%s)",
            ([row["resolution_event_id"] for row in manifest["rows"]],),
        ).fetchone()[0]
    if count != EXPECTED_REVIEWS:
        raise RuntimeError(f"durable_resolution_population_incomplete:{count}")
    return {"durable_rows": count, "receipts": len(receipts)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--page-size", type=int, default=5)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    if args.page_size < 1 or args.page_size > 20:
        raise SystemExit("page-size must be between 1 and 20")
    source = ProductionEvidenceSource()
    checkpoint = ResolutionCheckpoint(Path(args.checkpoint))
    complete = capture(source, checkpoint, page_size=args.page_size)
    manifest = build_manifest(complete)
    manifest_path = checkpoint.root / "resolution_manifest.json"
    atomic_write_json(manifest_path, manifest)
    result = {
        "snapshot_id": complete["metadata"]["snapshot_id"],
        "manifest_path": str(manifest_path),
        "artifact_sha256": manifest["artifact_sha256"],
        "row_count": manifest["row_count"],
        "disposition_counts": manifest["disposition_counts"],
        "recorded": False,
        "customer_sends": 0, "chatwoot_mutations": 0, "farm_writes": 0,
        "telegram_actions": 0,
    }
    if args.record:
        result.update(record_manifest(source, checkpoint, manifest))
        result["recorded"] = True
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
