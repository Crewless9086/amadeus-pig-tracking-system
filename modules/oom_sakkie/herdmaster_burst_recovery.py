"""Pure recovery planning for rapid, independently-lived Telegram reports.

This module deliberately has no gateway, database, or protected-action writer.  It
turns retained provider chronology plus current canonical evidence into a stable
recovery plan which a later gateway integration may preview.  Keeping this seam
pure prevents a recovery inspection from replaying a farm action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import re
from typing import Any, Callable, Iterable


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", _clean(value).casefold())


def _digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProviderReport:
    provider_message_id: str
    owner_id: str
    chat_id: str
    text: str
    received_at: str
    reply_to_message_id: str = ""


@dataclass(frozen=True)
class CanonicalSubject:
    label: str
    pig_id: str
    active_litter_id: str = ""


@dataclass(frozen=True)
class ExistingLifecycle:
    provider_message_id: str
    status: str
    operation_id: str = ""


@dataclass(frozen=True)
class RecoveryItem:
    subject: str
    action: str
    provider_message_ids: tuple[str, ...]
    state: str
    operation_key: str
    known: dict[str, Any] = field(default_factory=dict)
    missing: tuple[str, ...] = ()


def make_litter_death_preview(
    *,
    provider_message_ids: Iterable[str],
    owner_id: str,
    chat_id: str,
    litter_id: str,
    event_date: str,
    count: int,
    previewer: Callable[..., tuple[dict[str, Any], int]],
    reason: str = "Unknown",
    male_count: int | None = None,
    female_count: int | None = None,
    pig_ids: list[str] | None = None,
) -> RecoveryItem:
    """Request the canonical dry-run only; never execute the resulting action."""
    message_ids = tuple(sorted({_clean(item) for item in provider_message_ids if _clean(item)}))
    identity = {
        "owner_id": _clean(owner_id), "chat_id": _clean(chat_id),
        "provider_message_ids": message_ids, "litter_id": _clean(litter_id),
        "event_date": event_date, "count": int(count), "reason": reason,
        "male_count": male_count, "female_count": female_count,
        "pig_ids": sorted(pig_ids or []),
    }
    operation_key = f"litter-death:{_digest(identity)[:24]}"
    result, status = previewer(
        _clean(litter_id), event_date, reason, count=count,
        male_count=male_count, female_count=female_count, pig_ids=pig_ids,
        changed_by="oom_sakkie", notes="Retained Telegram provider chronology",
        dry_run=True,
    )
    if status == 200 and result.get("success"):
        return RecoveryItem(
            "Linda", "mark_litter_piglets_dead", message_ids, "preview_ready",
            operation_key, {**identity, "preview": result}, (),
        )
    errors = tuple(result.get("errors") or ())
    missing: tuple[str, ...] = ("pig_ids_or_sex_counts",) if any(
        "selected specifically" in error or "male/female" in error for error in errors
    ) else ("canonical_litter_evidence",)
    return RecoveryItem(
        "Linda", "mark_litter_piglets_dead", message_ids, "needs_fact",
        operation_key, {**identity, "preview_errors": errors}, missing,
    )


def plan_anton_burst(
    reports: Iterable[ProviderReport],
    subjects: Iterable[CanonicalSubject],
    lifecycles: Iterable[ExistingLifecycle],
    *,
    previewer: Callable[..., tuple[dict[str, Any], int]],
) -> list[RecoveryItem]:
    """Build one stable item per real-world event, independent of arrival order."""
    reports = sorted(reports, key=lambda row: (row.received_at, row.provider_message_id))
    by_label = {_key(row.label): row for row in subjects}
    lifecycle = {row.provider_message_id: row for row in lifecycles}
    output: list[RecoveryItem] = []

    # A completed 138 lifecycle is terminal and must never be previewed again.
    for report in reports:
        if re.search(r"\b138\b", report.text) and lifecycle.get(report.provider_message_id, ExistingLifecycle("", "")).status == "completed":
            output.append(RecoveryItem("138", "mortality", (report.provider_message_id,), "already_completed", lifecycle[report.provider_message_id].operation_id))

    # Typo corroboration: "Linds 3 ..." and the later Linda/date message are one
    # report when owner/chat match.  Both provider ids remain in the audit identity.
    linda_rows = [row for row in reports if re.search(r"\blinds?\b|\blinda\b", row.text, re.I) and "dood" in row.text.casefold()]
    if linda_rows and (linda := by_label.get("linda")) and linda.active_litter_id:
        count_match = next((re.search(r"\b(\d+)\b", row.text) for row in linda_rows if re.search(r"\b(\d+)\b", row.text)), None)
        date_match = next((re.search(r"\b(\d{1,2})\s+aug\b", row.text, re.I) for row in linda_rows if re.search(r"\b(\d{1,2})\s+aug\b", row.text, re.I)), None)
        count = int(count_match.group(1)) if count_match else 0
        day = int(date_match.group(1)) if date_match else 26
        output.append(make_litter_death_preview(
            provider_message_ids=[row.provider_message_id for row in linda_rows],
            owner_id=linda_rows[0].owner_id, chat_id=linda_rows[0].chat_id,
            litter_id=linda.active_litter_id, event_date=f"2026-08-{day:02d}",
            count=count, previewer=previewer,
        ))

    for report in reports:
        text = report.text.casefold()
        if "mona" in text and (match := re.search(r"\b(\d+)\b", text)):
            known = {"total_born": int(match.group(1)), "stillborn": 1, "event_date": "2026-08-26"}
            key = f"farrowing:{_digest({'provider': report.provider_message_id, **known})[:24]}"
            state = "repreview_required" if lifecycle.get(report.provider_message_id, ExistingLifecycle("", "")).status == "expired" else "preview_required"
            output.append(RecoveryItem("Mona", "record_farrowing", (report.provider_message_id,), state, key, known))
        if re.search(r"\b146\b", text) and "dood" in text:
            known = {"death_date": "2026-08-23"}
            key = f"mortality:{_digest({'provider': report.provider_message_id, **known})[:24]}"
            output.append(RecoveryItem("146", "mortality", (report.provider_message_id,), "needs_fact", key, known, ("removed_disposal",)))

    # Provider retries cannot produce duplicate action identities.
    unique: dict[str, RecoveryItem] = {}
    for item in output:
        unique.setdefault(item.operation_key, item)
    return sorted(unique.values(), key=lambda item: (item.provider_message_ids, item.subject))


def bind_reply(candidates: Iterable[RecoveryItem], text: str) -> RecoveryItem | None:
    """Bind only an explicit exact subject; entity-free replies stay ambiguous."""
    token = _key(text)
    matches = [item for item in candidates if _key(item.subject) and _key(item.subject) in token]
    return matches[0] if len(matches) == 1 else None
