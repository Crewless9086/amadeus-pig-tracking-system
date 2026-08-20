"""Single read-only owner-attention projection shared by every channel.

The projection consumes the existing general-manager candidate adapters.  It
does not persist, schedule, dispatch, or infer new specialist work.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
from typing import Any, Callable, Iterable, Mapping

from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read
from modules.oom_sakkie.manager_case_sources import collect_manager_candidates


VERSION = "oom_sakkie_owner_attention_projection.v1"
LIFECYCLES = frozenset({"open", "resolved", "superseded"})
TASK_CLASSES = frozenset({"status_reconciliation", "physical_action_due", "informational_watch", "protected_decision"})
PRIORITY_ORDER = {"critical": 0, "urgent": 1, "due": 2, "planned": 3, "watch": 4}
SEMANTIC_EMOJI = {
    "status_reconciliation": "🔄",
    "physical_action_due": "⚖️",
    "informational_watch": "👀",
    "protected_decision": "🔐",
}


@dataclass(frozen=True)
class OwnerAttentionItem:
    work_id: str
    source_key: str
    category: str
    task_class: str
    priority: str
    welfare_priority: bool
    specialist_owner: str
    title: str
    exact_owner_action: str
    provenance: tuple[str, ...]
    observed_at: str | None
    freshness: str
    detail_target: str
    lifecycle: str
    semantic_emoji: str


def build_owner_attention_projection(
    candidates: Iterable[Mapping[str, Any]], *, generated_at: datetime | None = None,
    prior_cases: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Normalize existing specialist candidates into one stable ordered view."""
    now = _aware(generated_at or datetime.now(timezone.utc))
    current_by_key: dict[str, Mapping[str, Any]] = {}
    for candidate in candidates:
        key = _required(candidate.get("dedupe_key"), "dedupe_key")
        prior = current_by_key.get(key)
        if prior is not None and dict(prior) != dict(candidate):
            raise ValueError("conflicting owner-attention candidates share one stable identity")
        current_by_key[key] = candidate
    unavailable_specialists = {
        key.rsplit(":", 1)[-1].upper()
        for key in current_by_key if key.startswith("runtime:collector:")
    }
    items = [_item(candidate, now) for candidate in current_by_key.values()]
    for prior in prior_cases:
        key = _required(prior.get("dedupe_key"), "dedupe_key")
        if key in current_by_key:
            continue
        unavailable = (
            _required(prior.get("specialist"), "specialist").upper() in unavailable_specialists
            or ("DELIVERY_GAPS" in unavailable_specialists and key.startswith("delivery:"))
        )
        ledger_lifecycle = str(prior.get("lifecycle") or "open").lower()
        lifecycle = "open" if unavailable else (
            ledger_lifecycle if ledger_lifecycle in {"resolved", "superseded"} else "resolved")
        items.append(_item({**dict(prior), "lifecycle": lifecycle}, now))
    ordered = sorted(items, key=lambda item: (
        item.lifecycle != "open", not item.welfare_priority,
        PRIORITY_ORDER[item.priority], item.category,
        item.work_id,
    ))
    lifecycle_items = [asdict(item) for item in ordered]
    current = [item for item in lifecycle_items if item["lifecycle"] == "open"]
    return {
        "success": True,
        "version": VERSION,
        "generated_at": now.isoformat(),
        "ordered_work_ids": [item["work_id"] for item in current],
        "items": current,
        "lifecycle_items": lifecycle_items,
        "total_count": len(current),
        "top_items": current[:3],
        "hidden_count": max(0, len(current) - 3),
        "view_all_target": "/owner-attention",
        "writes_performed": 0,
        "authority": "read_only_projection",
    }


def load_owner_attention_projection(
    *, now: datetime | None = None,
    collector: Callable[..., Iterable[Mapping[str, Any]]] = collect_manager_candidates,
) -> dict[str, Any]:
    observed = _aware(now or datetime.now(timezone.utc))
    return build_owner_attention_projection(collector(now=observed), generated_at=observed,
                                            prior_cases=_load_prior_cases(observed))


def _load_prior_cases(now: datetime) -> list[dict[str, Any]]:
    """Read recent identities from the existing manager ledger; perform no write."""
    with connect_bounded_read() as connection:
        with connection.cursor() as cur:
            cur.execute("""select dedupe_key,specialist,urgency,status,evidence_refs,unknowns,
                    summary,next_action,updated_at
                from app_private.oom_manager_cases
                order by updated_at desc,dedupe_key""")
            return [{"dedupe_key": row[0], "specialist": row[1], "urgency": row[2],
                     "lifecycle": (row[3] if row[3] in LIFECYCLES else "open"),
                     "evidence_refs": row[4] or [f"manager_case:{row[0]}"],
                     "unknowns": row[5] or [], "summary": row[6], "next_action": row[7]}
                    for row in cur.fetchall()]


def _item(raw: Mapping[str, Any], now: datetime) -> OwnerAttentionItem:
    source_key = _required(raw.get("dedupe_key"), "dedupe_key")
    specialist = _required(raw.get("specialist"), "specialist").upper()
    priority = str(raw.get("urgency") or "watch").strip().lower()
    if priority not in PRIORITY_ORDER:
        priority = "watch"
    lifecycle = str(raw.get("lifecycle") or "open").strip().lower()
    if lifecycle not in LIFECYCLES:
        raise ValueError("unsupported owner-attention lifecycle")
    refs = tuple(str(value).strip() for value in raw.get("evidence_refs") or () if str(value).strip())
    if not refs:
        raise ValueError("owner-attention provenance is required")
    task_class = _task_class(raw)
    owner_action = _owner_action(raw, task_class, specialist)
    return OwnerAttentionItem(
        work_id="attn_" + hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:24],
        source_key=source_key,
        category=_category(source_key, specialist),
        task_class=task_class,
        priority=priority,
        welfare_priority=(raw.get("welfare_priority") is True
                          or "attention:welfare_priority" in refs),
        specialist_owner=specialist,
        title=_required(raw.get("summary"), "summary"),
        exact_owner_action=owner_action,
        provenance=refs,
        observed_at=_observed_at(refs),
        freshness=_freshness(refs, now),
        detail_target=_detail_target(source_key, specialist),
        lifecycle=lifecycle,
        semantic_emoji=SEMANTIC_EMOJI[task_class],
    )


def _task_class(raw: Mapping[str, Any]) -> str:
    explicit = str(raw.get("task_class") or "").strip().lower()
    if explicit:
        if explicit not in TASK_CLASSES:
            raise ValueError("unsupported owner-attention task class")
        return explicit
    text = " ".join(str(raw.get(key) or "") for key in ("dedupe_key", "summary", "next_action")).casefold()
    unknowns = " ".join(str(value) for value in raw.get("unknowns") or ()).casefold()
    if any(term in text for term in ("protected", "approval", "decision needed")):
        return "protected_decision"
    # Only an explicit physical verb may create physical work. Missing status,
    # chronology, refresh, timeout or evidence always remains reconciliation.
    if unknowns or any(term in text for term in (
        "missing", "unknown", "unresolved", "status", "chronology", "refresh",
        "retry", "timeout", "delivery exception", "clearance", "eligibility",
    )):
        return "status_reconciliation"
    if any(term in text for term in ("record weight", "physical weighing", "weigh now", "weighing due")):
        return "physical_action_due"
    return "informational_watch"


def _owner_action(raw: Mapping[str, Any], task_class: str, specialist: str) -> str:
    action = _required(raw.get("next_action"), "next_action")
    if specialist in {"ROOTLINE", "RUNTIME"} and task_class == "status_reconciliation":
        return "No owner action now — Oom Sakkie/ROOTLINE owns the automatic retry and evidence refresh."
    if task_class == "status_reconciliation" and any(
        token in action.casefold() for token in ("delegate", "retain", "prepare", "reassess")
    ):
        return f"No owner action now — {specialist} owns reconciliation from canonical evidence."
    return action


def _category(source_key: str, specialist: str) -> str:
    if source_key.startswith("herdmaster:"):
        return "herd"
    if source_key.startswith("rootline:"):
        return "water_energy"
    if source_key.startswith("sam:"):
        return "sales"
    if source_key.startswith("delivery:"):
        return "delivery"
    return specialist.casefold()


def _detail_target(source_key: str, specialist: str) -> str:
    if "molly-active-litter" in source_key:
        return "/litters"
    if "pig-151" in source_key:
        return "/pig-allocation"
    return {"HERDMASTER": "/pigs", "ROOTLINE": "/irrigation", "SAM": "/sales-dashboard",
            "BEACON": "/beacon/media", "RUNTIME": "/oom-sakkie"}.get(specialist, "/oom-sakkie")


def _observed_at(refs: tuple[str, ...]) -> str | None:
    return next((ref.split(":", 1)[1] for ref in refs if ref.startswith("observed:")), None)


def _freshness(refs: tuple[str, ...], now: datetime) -> str:
    value = _observed_at(refs)
    if not value:
        return "source_time_unavailable"
    try:
        age = max(0, int((now - _aware(datetime.fromisoformat(value.replace("Z", "+00:00")))).total_seconds() // 60))
    except ValueError:
        return "source_time_unavailable"
    return "current" if age <= 30 else ("aging" if age <= 180 else "stale")


def _required(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
