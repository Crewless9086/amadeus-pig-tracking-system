"""Single read-only owner-attention projection shared by every channel.

The projection consumes the existing general-manager candidate adapters.  It
does not persist, schedule, dispatch, or infer new specialist work.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from datetime import timedelta
import hashlib
import re
from typing import Any, Callable, Iterable, Mapping
from zoneinfo import ZoneInfo

from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read
from modules.oom_sakkie.manager_case_sources import collect_manager_candidates


VERSION = "oom_sakkie_owner_attention_projection.v3"
LIFECYCLES = frozenset({"open", "resolved", "superseded"})
TASK_CLASSES = frozenset({"status_reconciliation", "physical_action_due", "informational_watch", "protected_decision"})
ATTENTION_GROUPS = (
    "needs_you", "farm_work_ready", "oom_sakkie_checking", "watch", "recently_completed",
)
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
    primary_label: str
    secondary_reference: str
    identity_state: str
    message_family: str
    title: str
    exact_owner_action: str
    provenance: tuple[str, ...]
    observed_at: str | None
    freshness: str
    detail_target: str
    lifecycle: str
    semantic_emoji: str
    attention_group: str
    owner_action_eligible: bool
    owner_urgency: str
    operational_status: str
    assigned_to: str
    equipment_identity: str
    equipment_lifecycle: str
    equipment_evidence: Mapping[str, bool]


def build_owner_attention_projection(
    candidates: Iterable[Mapping[str, Any]], *, generated_at: datetime | None = None,
    prior_cases: Iterable[Mapping[str, Any]] = (), prior_material_digest: str | None = None,
) -> dict[str, Any]:
    """Normalize existing specialist candidates into one stable ordered view."""
    now = _aware(generated_at or datetime.now(timezone.utc))
    prior_case_rows = [dict(row) for row in prior_cases]
    prior_by_key = {str(row.get("dedupe_key") or ""): row for row in prior_case_rows}
    current_by_key: dict[str, Mapping[str, Any]] = {}
    normalized_by_key: dict[str, Mapping[str, Any]] = {}
    suppressed_keys: set[str] = set()
    source_candidate_count = 0
    for candidate in candidates:
        source_candidate_count += 1
        key = _required(candidate.get("dedupe_key"), "dedupe_key")
        equipment_lifecycle, equipment_evidence = _equipment_state(candidate)
        normalized = {**dict(candidate), "equipment_lifecycle": equipment_lifecycle,
                      "equipment_evidence": equipment_evidence}
        prior_normalized = normalized_by_key.get(key)
        if prior_normalized is not None and dict(prior_normalized) != normalized:
            raise ValueError("conflicting owner-attention candidates share one stable identity")
        normalized_by_key[key] = normalized
        if _attention_visibility(normalized) == "equipment_health_only":
            # This projection has no Equipment Health surface.  Keep healthy,
            # no-action readiness entirely out of Owner Attention instead of
            # creating a second channel-specific status calculation.
            suppressed_keys.add(key)
            continue
        prior_case = prior_by_key.get(key) or {}
        prior_status = str(prior_case.get("operational_status") or "").lower()
        prior_lifecycle = str(prior_case.get("lifecycle") or "").lower()
        terminal_lifecycle = (
            prior_lifecycle if prior_lifecycle in {"resolved", "superseded"} else "resolved"
        ) if prior_status in {"completed", "contained", "resolved", "superseded", "stale"} else None
        current_by_key[key] = {
            **normalized,
            **({"operational_status": prior_case.get("operational_status"),
                "assigned_worker_id": prior_case.get("assigned_worker_id"),
                **({"lifecycle": terminal_lifecycle} if terminal_lifecycle else {})}
               if prior_case.get("operational_status") else {}),
        }
    unavailable_specialists = {
        key.rsplit(":", 1)[-1].upper()
        for key in current_by_key if key.startswith("runtime:collector:")
    }
    items = [_item(candidate, now) for candidate in current_by_key.values()]
    for prior in prior_case_rows:
        key = _required(prior.get("dedupe_key"), "dedupe_key")
        if key in current_by_key or key in suppressed_keys:
            continue
        if _attention_visibility(prior) == "equipment_health_only":
            suppressed_keys.add(key)
            continue
        unavailable = (
            _required(prior.get("specialist"), "specialist").upper() in unavailable_specialists
            or ("DELIVERY_GAPS" in unavailable_specialists and key.startswith("delivery:"))
        )
        ledger_lifecycle = str(prior.get("lifecycle") or "open").lower()
        lifecycle = "open" if unavailable else (
            ledger_lifecycle if ledger_lifecycle in {"resolved", "superseded"} else "resolved")
        items.append(_item({**dict(prior), "lifecycle": lifecycle}, now))
    items = _disambiguate_duplicate_labels(items)
    ordered = sorted(items, key=lambda item: (
        item.lifecycle != "open", not item.welfare_priority,
        PRIORITY_ORDER[item.priority], _routine_weighing_item(item), item.category,
        item.work_id,
    ))
    lifecycle_items = [asdict(item) for item in ordered]
    current = [item for item in lifecycle_items if item["lifecycle"] == "open"]
    primary = [item for item in current if item["owner_action_eligible"]]
    groups = {name: [] for name in ATTENTION_GROUPS}
    for item in lifecycle_items:
        groups[item["attention_group"]].append(item)
    material_digest = _material_digest(primary)
    context_digest = _material_digest(current)
    material_changed = (None if prior_material_digest is None
                        else prior_material_digest != material_digest)
    return {
        "success": True,
        "version": VERSION,
        "generated_at": now.isoformat(),
        "ordered_work_ids": [item["work_id"] for item in current],
        "items": current,
        "lifecycle_items": lifecycle_items,
        # total_count is deliberately the primary owner-attention count. Agent
        # reconciliation and useful context remain visible without becoming
        # owner work.
        "total_count": len(primary),
        "open_context_count": len(current),
        "suppressed_equipment_health_count": len(suppressed_keys),
        "top_items": primary[:3],
        "hidden_count": max(0, len(primary) - 3),
        "groups": groups,
        "group_counts": {name: len(values) for name, values in groups.items()},
        "measurement": {
            "source_message_count": source_candidate_count,
            "duplicate_message_count": source_candidate_count - len(normalized_by_key),
            "owner_visible_message_count": len(current),
            "owner_work_item_count": len(primary),
            "baseline_material_digest": prior_material_digest,
            "after_material_digest": material_digest,
            "material_changed": material_changed,
            "new_message_eligible": bool(primary) and material_changed is not False,
        },
        "material_digest": material_digest,
        "context_digest": context_digest,
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
                    summary,next_action,updated_at,assigned_worker_id,next_reassessment_at
                from app_private.oom_manager_cases
                where status in ('open','delegated','waiting_reassessment','exception')
                   or updated_at >= %s
                order by updated_at desc,dedupe_key""",
                (now - timedelta(days=7),))
            return [{"dedupe_key": row[0], "specialist": row[1], "urgency": row[2],
                     "lifecycle": ("resolved" if row[3] in {"completed", "contained"}
                                   else (row[3] if row[3] in LIFECYCLES else "open")),
                     "evidence_refs": row[4] or [f"manager_case:{row[0]}"],
                     "unknowns": row[5] or [], "summary": row[6], "next_action": row[7],
                     "operational_status": row[3], "assigned_worker_id": row[9],
                     "next_reassessment_at": row[10].isoformat() if row[10] else None,
                     "updated_at": row[8].isoformat() if row[8] else None}
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
    primary_label, secondary_reference, identity_state = _presentation_identity(raw, source_key)
    summary = _required(raw.get("summary"), "summary")
    display_title = (summary if summary.casefold().startswith(primary_label.casefold())
                     else f"{primary_label} — {summary}")
    operational_status = str(raw.get("operational_status") or "open").strip().lower()
    attention_group, eligible = _attention_eligibility(
        raw, task_class=task_class, lifecycle=lifecycle,
        operational_status=operational_status, priority=priority, now=now)
    assigned_to = _assigned_to(raw, specialist, attention_group)
    equipment_lifecycle, equipment_evidence = _equipment_state(raw)
    return OwnerAttentionItem(
        work_id="attn_" + hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:24],
        source_key=source_key,
        category=_category(source_key, specialist),
        task_class=task_class,
        priority=priority,
        welfare_priority=(raw.get("welfare_priority") is True
                          or "attention:welfare_priority" in refs),
        specialist_owner=specialist,
        primary_label=primary_label,
        secondary_reference=secondary_reference,
        identity_state=identity_state,
        message_family=str(raw.get("message_family") or _category(source_key, specialist)),
        title=display_title,
        exact_owner_action=owner_action,
        provenance=refs,
        observed_at=_observed_at(refs),
        freshness=_freshness(refs, now),
        detail_target=_detail_target(raw, source_key, specialist),
        lifecycle=lifecycle,
        semantic_emoji=SEMANTIC_EMOJI[task_class],
        attention_group=attention_group,
        owner_action_eligible=eligible,
        owner_urgency=(priority if eligible else "none"),
        operational_status=operational_status,
        assigned_to=assigned_to,
        equipment_identity=_owner_text(raw.get("equipment_identity") or (
            "FERTILIZER-MIXER-CH2" if source_key ==
            "rootline-readiness:fertilizer-mixer-ch2" else ""), 120),
        equipment_lifecycle=equipment_lifecycle,
        equipment_evidence=equipment_evidence,
    )


def _equipment_state(raw: Mapping[str, Any]) -> tuple[str, dict[str, bool]]:
    """Accept equipment labels only when their required evidence is explicit."""
    source_key = str(raw.get("dedupe_key") or "")
    retained_mixer_readiness = source_key == "rootline-readiness:fertilizer-mixer-ch2"
    retained_ready = retained_mixer_readiness and not tuple(raw.get("unknowns") or ())
    lifecycle = str(raw.get("equipment_lifecycle") or (
        "ready_for_commissioning" if retained_ready else
        ("held" if retained_mixer_readiness else "not_applicable")
    )).strip().lower()
    allowed = {
        "not_applicable", "registered", "ready_for_commissioning",
        "commissioning_required", "commissioned",
        "autonomous_authority_enabled", "active", "completed", "held", "failed",
    }
    if lifecycle not in allowed:
        raise ValueError("unsupported equipment lifecycle")
    supplied = raw.get("equipment_evidence")
    evidence = ({str(key): value for key, value in supplied.items()}
                if isinstance(supplied, Mapping) else ({
                    "provider_readiness_proven": retained_ready,
                    "current_state_off": retained_ready,
                } if retained_mixer_readiness else {}))
    if any(type(value) is not bool for value in evidence.values()):
        raise ValueError("equipment lifecycle evidence must be boolean")
    required = {
        "ready_for_commissioning": ("provider_readiness_proven", "current_state_off"),
        "commissioned": ("physical_commissioning_proven",),
        "autonomous_authority_enabled": ("physical_commissioning_proven",
                                           "autonomous_authority_enabled"),
        "active": ("autonomous_authority_enabled", "canonical_execution_active",
                   "provider_execution_active"),
        "completed": ("canonical_execution_completed", "provider_final_state_verified",
                      "physical_outcome_verified"),
    }.get(lifecycle, ())
    if any(evidence.get(key) is not True for key in required):
        raise ValueError("equipment lifecycle lacks required evidence")
    return lifecycle, evidence


def _attention_visibility(raw: Mapping[str, Any]) -> str:
    explicit = str(raw.get("attention_visibility") or "").strip().lower()
    if explicit and explicit not in {"equipment_health_only", "owner_attention_exception"}:
        raise ValueError("unsupported attention visibility")
    readiness_key = str(raw.get("dedupe_key") or "") == "rootline-readiness:fertilizer-mixer-ch2"
    if readiness_key:
        lifecycle, evidence = _equipment_state(raw)
        healthy = (
            not tuple(raw.get("unknowns") or ())
            and lifecycle == "ready_for_commissioning"
            and evidence.get("provider_readiness_proven") is True
            and evidence.get("current_state_off") is True
        )
        return "equipment_health_only" if healthy else "owner_attention_exception"
    if explicit == "equipment_health_only":
        # Health-only suppression is reserved for normalized known equipment
        # readiness.  Unknown item classes fail visible instead of disappearing.
        return "owner_attention_exception"
    if explicit:
        return explicit
    return "owner_attention"


def _attention_eligibility(raw: Mapping[str, Any], *, task_class: str, lifecycle: str,
                           operational_status: str, priority: str,
                           now: datetime) -> tuple[str, bool]:
    """Derive owner eligibility only from existing canonical case semantics."""
    if lifecycle != "open" or operational_status in {"completed", "contained", "resolved", "superseded", "stale"}:
        return "recently_completed", False
    agent_owned = operational_status in {"delegated", "waiting_reassessment"}
    if agent_owned:
        return "oom_sakkie_checking", False
    if (task_class == "protected_decision"
            and raw.get("owner_question_eligible") is True):
        return "needs_you", True
    if task_class == "physical_action_due" and raw.get("physical_work_ready") is True:
        if (_routine_weighing_raw(raw)
                and _aware(now).astimezone(ZoneInfo("Africa/Johannesburg")).weekday() != 0
                and raw.get("exceptional_weighing_due_now") is not True):
            return "watch", False
        # A physical task is owner-visible work only when the specialist has
        # proved it ready. Urgent welfare/shutdown exceptions remain an exact
        # owner need; ordinary physical work stays farm work ready.
        if (operational_status == "exception" and priority in {"critical", "urgent"}
                and raw.get("irreducible_owner_exception") is True):
            return "needs_you", True
        return "farm_work_ready", True
    if task_class in {"status_reconciliation", "physical_action_due", "protected_decision"} or operational_status == "exception":
        return "oom_sakkie_checking", False
    return "watch", False


def _assigned_to(raw: Mapping[str, Any], specialist: str, attention_group: str) -> str:
    worker = _owner_text(raw.get("assigned_worker_id"), 120)
    if attention_group == "needs_you":
        return "Charl"
    if attention_group == "farm_work_ready":
        return _owner_text(raw.get("physical_assignee"), 120) or "Farm team"
    if attention_group == "oom_sakkie_checking":
        return worker or ("Oom Sakkie / " + specialist.title())
    return specialist.title()


def _presentation_identity(raw: Mapping[str, Any], source_key: str) -> tuple[str, str, str]:
    """Resolve only source-declared owner meaning; never manufacture a name."""
    identity = raw.get("presentation_identity")
    identity = identity if isinstance(identity, Mapping) else {}
    refs = tuple(str(value) for value in raw.get("evidence_refs") or ())
    human_name = _owner_text(identity.get("human_name") or _ref_value(refs, "owner_name:"), 100)
    familiar_meaning = _owner_text(identity.get("familiar_meaning") or
                                   _ref_value(refs, "owner_meaning:"), 140)
    reference = _owner_text(identity.get("stable_reference") or
                            _ref_value(refs, "owner_reference:"), 120)
    if not human_name and not familiar_meaning:
        human_name, familiar_meaning, legacy_reference = _supported_retained_identity(raw, source_key)
        reference = reference or legacy_reference
    if human_name:
        return human_name, reference or "Reference unavailable", "supported_human_name"
    if familiar_meaning:
        return familiar_meaning, reference or "Reference unavailable", "supported_familiar_meaning"
    return "Name unavailable", reference or "Reference unavailable", "missing_name_explicit"


def _disambiguate_duplicate_labels(items: list[OwnerAttentionItem]) -> list[OwnerAttentionItem]:
    """Keep a shared name first while exposing stable references for collisions."""
    counts: dict[tuple[str, str], int] = {}
    for item in items:
        key = (item.attention_group, item.primary_label.casefold())
        counts[key] = counts.get(key, 0) + 1
    result = []
    ordinal = {item.work_id: index for index, item in enumerate(
        sorted(items, key=lambda value: value.work_id), 1)}
    for item in items:
        if counts[(item.attention_group, item.primary_label.casefold())] <= 1:
            result.append(item)
            continue
        title = item.title
        disambiguator = (f"ref: {item.secondary_reference}"
                         if item.secondary_reference != "Reference unavailable"
                         else f"item {ordinal[item.work_id]}")
        title = f"{title} ({disambiguator})"
        result.append(OwnerAttentionItem(**{**asdict(item), "title": title,
                                            "identity_state": item.identity_state + "_disambiguated"}))
    return result


def _owner_text(value: Any, limit: int) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or ""))
    return " ".join(text.split())[:limit].strip()


def _material_digest(items: list[dict[str, Any]]) -> str:
    material = [{key: item[key] for key in (
        "work_id", "primary_label", "secondary_reference", "message_family", "title",
        "task_class", "priority", "specialist_owner", "exact_owner_action", "lifecycle",
        "attention_group", "owner_action_eligible", "owner_urgency", "operational_status",
        "assigned_to")}
        for item in items]
    import json
    return hashlib.sha256(json.dumps(material, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _ref_value(refs: tuple[str, ...], prefix: str) -> str:
    return next((value[len(prefix):] for value in refs if value.startswith(prefix)), "")


def _supported_retained_identity(raw: Mapping[str, Any], source_key: str) -> tuple[str, str, str]:
    """Recover only meanings already explicit in retained canonical case text."""
    summary = _owner_text(raw.get("summary"), 500)
    refs = tuple(str(value) for value in raw.get("evidence_refs") or ())
    reference = _ref_value(refs, "litter:") or _ref_value(refs, "pig:")
    if source_key == "herdmaster:molly-active-litter":
        return "Molly", "", reference
    if source_key.startswith("herdmaster:welfare:") and " has an active " in summary:
        label = summary.split(" has an active ", 1)[0].strip()
        if label and label.casefold() not in {"name unavailable", "animal name unavailable"}:
            return _owner_text(label, 100), "", reference
        return "", "Animal name unavailable", reference
    meanings = {
        "rootline:current-plan": "Current water and energy plan",
        "herdmaster:pig-151-withdrawal-sales": "Pig 151",
        "beacon:current-sale-opportunity": "Current sales opportunity",
        "runtime:scheduled-worker-health": "Oom Sakkie scheduled operation",
        "rootline-readiness:fertilizer-mixer-ch2": "Fertilizer mixer",
    }
    if source_key.startswith("sam:conversation:"):
        return "", "Customer name unavailable", ""
    if source_key.startswith("delivery:"):
        specialist = str(raw.get("specialist") or "Specialist").title()
        return "", f"{specialist} owner result", ""
    return "", meanings.get(source_key, ""), reference


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


def _detail_target(raw: Mapping[str, Any], source_key: str, specialist: str) -> str:
    declared = str(raw.get("detail_target") or "").strip()
    if declared.startswith("/") and not declared.startswith("//") and ".." not in declared:
        return declared
    refs = tuple(str(value) for value in raw.get("evidence_refs") or ())
    litter_id = _safe_identifier(_ref_value(refs, "litter:"))
    pig_id = _safe_identifier(_ref_value(refs, "pig:"))
    if litter_id:
        return f"/litter/{litter_id}"
    if "molly-active-litter" in source_key:
        return "/litters"
    if specialist == "HERDMASTER" and pig_id:
        return f"/pig/{pig_id}"
    if _routine_weighing_raw(raw):
        return "/bulk-weights"
    if "pig-151" in source_key:
        return "/pig-allocation"
    if specialist == "ROOTLINE" and "policy" in source_key.casefold():
        return "/rootline/policy-review"
    return {"HERDMASTER": "/pigs", "ROOTLINE": "/irrigation", "SAM": "/sales-dashboard",
            "BEACON": "/sales/beacon-media", "RUNTIME": "/oom-sakkie"}.get(specialist, "/oom-sakkie")


def _safe_identifier(value: str) -> str:
    return value if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value or "") else ""


def _routine_weighing_raw(raw: Mapping[str, Any]) -> bool:
    if raw.get("routine_weekly_weighing") is True:
        return True
    text = " ".join(str(raw.get(key) or "") for key in (
        "dedupe_key", "summary", "next_action", "message_family")).casefold()
    return "monday weigh" in text or "weekly weigh" in text


def _routine_weighing_item(item: OwnerAttentionItem) -> bool:
    text = " ".join((item.source_key, item.title, item.message_family)).casefold()
    return "monday weigh" in text or "weekly weigh" in text


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
