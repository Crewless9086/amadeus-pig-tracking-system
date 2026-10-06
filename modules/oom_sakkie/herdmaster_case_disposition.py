"""Owning, read-only disposition of retained HERDMASTER advisories.

Positive terminal proof addresses the two existing per-animal advisory families.
Exact legacy mortality projections may retain a nonterminal technical dependency.
Protected reports, confirmations and farm operations are never completed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
import time

from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read, ReadBudgetCursor

FENCE = "herdmaster_case_fence:"
FAMILY = "herdmaster_disposition"


def conclusively_departed(status, on_farm):
    """Unknown or contradictory canonical state cannot retire an advisory."""
    return (str(status or "").strip().casefold() in
            {"dead", "deceased", "died", "sold", "culled"} and on_farm is False)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def advisory_target(key, refs):
    if key.startswith("herdmaster:herdmaster:"):
        pig = key.removeprefix("herdmaster:herdmaster:")
        if re.fullmatch(r"PIG-[A-Za-z0-9-]+", pig):
            bound = {v[4:] for v in refs if v.startswith("pig:")}
            return (pig, "") if not bound or bound == {pig} else None
    match = re.fullmatch(r"herdmaster:pig-([A-Za-z0-9-]+)-withdrawal-sales", key)
    pigs = {v[4:] for v in refs if v.startswith("pig:")}
    if match and len(pigs) == 1:
        return next(iter(pigs)), match[1]
    return None


def collect_advisory_dispositions(now, *, current_keys=(), connect=None, claimed_cases=None):
    rows, _current = _collect_advisory_snapshot(now, current_keys=current_keys,
        connect=connect, claimed_cases=claimed_cases)
    return rows


def collect_advisory_refresh(now, *, claimed_cases=None, connect=None):
    """Return owning proof and exact durable ordinary cases needing current work."""
    return _collect_advisory_snapshot(now, connect=connect, claimed_cases=claimed_cases)


def _collect_advisory_snapshot(now, *, current_keys=(), connect=None, claimed_cases=None):
    """Acquire one consistent, bounded snapshot; omission is never completion."""
    from modules.oom_sakkie.manager_case_sources import _candidate, is_advisory_herd_refresh_case
    selectors = None
    if claimed_cases is not None:
        selectors = []
        for case in claimed_cases:
            if (not isinstance(case, dict) or not is_advisory_herd_refresh_case(case)
                    or not isinstance(case.get("case_id"), str) or not case["case_id"].strip()):
                raise ValueError("advisory_refresh_case_identity_invalid")
            selectors.append({"case_id": case["case_id"], "dedupe_key": case["dedupe_key"]})
        if not selectors:
            return [], ()
        if len(selectors) > 64:
            raise ValueError("herdmaster_disposition_case_bound_exceeded")
    deadline = time.monotonic() + 6
    with (connect or connect_bounded_read)() as db, db.cursor() as raw_cur:
        raw_cur.execute("set transaction isolation level repeatable read read only")
        cur = ReadBudgetCursor(raw_cur, deadline, failure_kind="herdmaster_disposition_read_deadline")
        # Caller data select only identities; source, status and fences always
        # come from the durable manager row within this read-only snapshot.
        selection = ("" if selectors is None else """and (case_id,dedupe_key) in (
            select i.case_id,i.dedupe_key from jsonb_to_recordset(%s::jsonb)
              as i(case_id text,dedupe_key text))""")
        cur.execute("""select case_id,dedupe_key,generation,evidence_digest,evidence_refs
            from app_private.oom_manager_cases where specialist='HERDMASTER'
              and status in ('open','delegated','waiting_reassessment','exception')
              and (dedupe_key like 'herdmaster:herdmaster:PIG-%%'
                or dedupe_key ~ '^herdmaster:pig-[A-Za-z0-9-]+-withdrawal-sales$')
            """ + selection + " order by case_id limit 65",
            () if selectors is None else (json.dumps(selectors),))
        retained = cur.fetchall()
        if len(retained) > 64:
            raise ValueError("herdmaster_disposition_case_bound_exceeded")
        selected = []
        for case_id, key, generation, digest, refs in retained:
            if key in current_keys:
                continue
            if not isinstance(refs, list) or not all(isinstance(v, str) for v in refs):
                raise ValueError("herdmaster_disposition_source_invalid")
            target = advisory_target(key, refs)
            if target:
                selected.append((case_id, key, generation, digest, refs, target))
        if not selected:
            return [], ()
        ids = sorted({row[-1][0] for row in selected})
        tags = sorted({row[-1][1].casefold() for row in selected if row[-1][1]})
        cur.execute("""select pig_id,tag_number,status,on_farm
            from public.current_canonical_pigs where pig_id=any(%s) or lower(tag_number)=any(%s)
            order by pig_id limit 65""", (ids, tags))
        pigs = cur.fetchall()
        if len(pigs) != len({row[0] for row in pigs}) or len(pigs) > 64:
            raise ValueError("herdmaster_disposition_identity_ambiguous")
        by_id = {row[0]: row for row in pigs}
        result, current = [], []
        for case_id, key, generation, digest, refs, (pig, tag) in selected:
            row = by_id.get(pig)
            terminal = bool(row and (not tag or (str(row[1]).casefold() == tag.casefold()
                and len([v for v in pigs if str(v[1]).casefold() == tag.casefold()]) == 1))
                and conclusively_departed(row[2], row[3]))
            # These exact keys have two owning producers: active welfare and
            # the withdrawal hold. Canonical departure suppresses both. For a
            # live animal, original completed observation proof below also
            # verifies the latest lifecycle, never absence from an overview.
            proof = "canonical_off_farm" if terminal else "source_reconciliation_required"
            proof_refs = []
            if not terminal and not tag and row:
                proof_refs = _completed_observation(cur, pig, refs)
                terminal = bool(proof_refs)
                if terminal:
                    proof = "confirmed_observation_recorded"
            if not terminal and "manager_message_family:" + FAMILY not in refs:
                # A failed overview or unproved disposition cannot replace a
                # genuine current question. Only a durable prior disposition
                # retains the silent technical reconciliation projection.
                current.append((key, "HERDMASTER"))
                continue
            # Preserve original attribution, but replace previous disposition
            # metadata so an unresolved reassessment does not grow its own refs.
            source_refs = [v for v in refs if not v.startswith((FENCE, "observed:",
                "herdmaster_disposition:", "disposition_evidence:", "advisory_proof_", "manager_message_family:"))]
            if (any(v.startswith("HERD-NEXT-") for v in source_refs)
                    and not any(v.startswith("advisory_source_observed:") for v in source_refs)):
                source_refs.extend("advisory_source_" + v for v in refs if v.startswith("observed:"))
            evidence_refs = source_refs + proof_refs + [FENCE + str(generation) + ":" + digest,
                "herdmaster_disposition:" + proof, "disposition_evidence:" + _digest([row, proof_refs]),
                "observed:" + now.isoformat()]
            label = str(row[1] or pig) if row else pig
            result.append(_candidate(key, "HERDMASTER", "watch", evidence_refs,
                [] if terminal else ["owning_specialist_disposition_unproven"],
                (f"HERDMASTER retired the old advisory for {label}: {proof.replace('_', ' ')}."
                 if terminal else f"HERDMASTER is reconciling the retained advisory for {label}."),
                ("The existing advisory is complete from owning evidence; no farm effect or owner message is required."
                 if terminal else "Verify the original advisory source and current canonical outcome before closure; do not ask the owner to debug internal records."),
                now + timedelta(minutes=30), message_family=FAMILY,
                **({"terminal_state": "completed"} if terminal else {})))
        return result, tuple(current)


def _completed_observation(cur, pig, refs):
    missions = {v for v in refs if re.fullmatch(r"OOM-HERDMASTER-[A-Z0-9-]+", v)}
    if not missions:
        missions = _legacy_advisory_missions(cur, pig, refs)
    if not missions or len(missions) > 4:
        return []
    cur.execute("""select review_json->'herdmaster_health_loss'
        from public.sam_live_stock_conversation_review_events
        where event_source='oom_sakkie_herdmaster_health_loss_runtime'
          and (review_json#>>'{herdmaster_health_loss,preview,evaluator,identity,pig_id}'=%s
            or review_json#>>'{herdmaster_health_loss,mission_id}'=any(%s)
            or review_json#>'{herdmaster_health_loss,consumed_context_missions}' ?| %s
            or review_json#>'{herdmaster_health_loss,superseded_duplicate_missions}' ?| %s
            or exists (select 1 from jsonb_array_elements(coalesce(
                review_json#>'{herdmaster_health_loss,superseded_duplicate_bindings}', '[]'::jsonb)) b
                where b->>'mission_id'=any(%s)))
        order by created_at desc,review_event_id desc limit 513""", (pig, sorted(missions), sorted(missions), sorted(missions), sorted(missions)))
    history = cur.fetchall()
    if len(history) > 512:
        raise ValueError("herdmaster_disposition_history_bound_exceeded")
    if not history:
        return []
    latest = history[0][0] or {}
    from modules.oom_sakkie.herdmaster_source_transaction import superseded_missions
    if any(missions & superseded_missions(row[0] or {}) for row in history):
        return []
    if len({(row[0].get("owner_user_id"), row[0].get("chat_id"))
            for row in history}) != 1:
        return []
    preview = latest.get("preview") or {}
    evaluator, binding = preview.get("evaluator") or {}, preview.get("confirmation_binding") or {}
    identity, recorded = evaluator.get("identity") or {}, latest.get("recording_result") or {}
    operation = str(latest.get("operation_id") or "")
    owner = str(latest.get("owner_user_id") or "")
    effects = [v for v in evaluator.get("canonical_effects") or () if v.get("supported")]
    if (latest.get("mission_id") not in missions or latest.get("status") != "completed"
        or latest.get("event_phase") != "recording_completed" or not operation or not owner
        or latest.get("chat_id") != owner or latest.get("correction_digest")
        or latest.get("invalidated_operation_ids") or identity.get("pig_id") != pig
        or identity.get("resolved") is not True or preview.get("confirmation_ready") is not True
        or binding.get("confirmation_ready") is not True or binding.get("authenticated_principal_id") != owner
        or operation != binding.get("operation_id") or recorded.get("success") is not True
        or recorded.get("operation_id") != operation or not recorded.get("observation_event_id")
        or len(effects) != 1 or effects[0].get("area") != "medical_observation"):
        return []
    facts = dict(effects[0].get("facts") or {})
    canonical = {"operation_id": operation, "pig_id": pig,
        "provider_message_id": str(binding.get("provider_message_id") or ""),
        "preview_sha256": str(binding.get("preview_sha256") or ""),
        "evidence_generation": str(binding.get("evidence_generation") or ""),
        "facts": facts, "actor_id": owner}
    cur.execute("""select observation_event_id,source_reference,observer_reference
        from public.pig_observation_events e where observation_event_id=%s
          and pig_id=%s and idempotency_key=%s
          and not exists(select 1 from public.pig_observation_events later
              where later.supersedes_observation_event_id=e.observation_event_id) limit 2""",
        (recorded["observation_event_id"], pig, operation))
    effects = cur.fetchall()
    if len(effects) != 1 or effects[0][1:] != (_digest(canonical), owner):
        return []
    return ["advisory_proof_mission:" + latest["mission_id"],
        "advisory_proof_operation:" + operation,
        "advisory_proof_observation:" + effects[0][0],
        "advisory_proof_source_sha256:" + effects[0][1]]


def _legacy_advisory_missions(cur, pig, refs):
    """Reconstruct only the old whole-herd projection's exact as-of lifecycle.

    Older composition overwrote per-item references. Preserve the original
    observation epoch and require a uniquely current, delivered question for this
    animal at that epoch. Current completion alone cannot identify the old case.
    """
    packets = {v for v in refs if re.fullmatch(r"HERD-NEXT-[0-9A-F]{24}", v)}
    worklists = {v for v in refs if re.fullmatch(r"HERD-WEEK-[0-9A-F]{32}", v)}
    dates = {v.split(":", 1)[1] for v in refs if v.startswith("advisory_source_observed:")}
    if not dates:
        dates = {v.split(":", 1)[1] for v in refs if v.startswith("observed:")}
    if len(packets) != 1 or len(worklists) != 1 or len(dates) != 1:
        return set()
    packet = next(iter(packets))
    if not any(v.startswith("result:" + packet + ":HERD-DAILY-EVIDENCE-") for v in refs):
        return set()
    try:
        observed = datetime.fromisoformat(next(iter(dates)).replace("Z", "+00:00"))
        if observed.tzinfo is None:
            return set()
    except ValueError:
        return set()
    cur.execute("""select review_json->'herdmaster_health_loss',created_at
        from public.sam_live_stock_conversation_review_events
        where event_source='oom_sakkie_herdmaster_health_loss_runtime'
          and review_json#>>'{herdmaster_health_loss,preview,evaluator,identity,pig_id}'=%s
          and created_at<=%s order by created_at desc,review_event_id desc limit 513""", (pig, observed))
    rows = cur.fetchall()
    if len(rows) > 512:
        raise ValueError("herdmaster_disposition_history_bound_exceeded")
    # The legacy packet lost its principal too. A global newest row cannot
    # establish which owner's projection created the retained advisory.
    if len({(r[0].get("owner_user_id"), r[0].get("chat_id")) for r in rows}) != 1:
        return set()
    if not rows or (len(rows) >= 2 and rows[0][1] == rows[1][1]):
        return set()
    source = rows[0][0] or {}
    evaluated = (source.get("preview") or {}).get("evaluator") or {}
    identity = evaluated.get("identity") or {}
    mission, owner = source.get("mission_id"), source.get("owner_user_id")
    if (not mission or not owner or source.get("chat_id") != owner
        or source.get("status") != "waiting_for_input" or source.get("correction_digest")
        or source.get("invalidated_operation_ids") or identity.get("resolved") is not True
        or identity.get("pig_id") != pig or not evaluated.get("smallest_missing_follow_up_question")):
        return set()
    cur.execute("""select review_json->'family_message_lifecycle'
        from public.sam_live_stock_conversation_review_events
        where event_source='oom_sakkie_family_message_lifecycle'
          and review_json#>>'{family_message_lifecycle,card_mission_id}'=%s
          and review_json#>>'{family_message_lifecycle,state}' in ('delivered','updated')
          and created_at<=%s order by created_at desc,review_event_id desc limit 1""", (mission, observed))
    delivered = cur.fetchone()
    receipt = delivered[0] if delivered else {}
    if (not receipt or not receipt.get("telegram_message_id")
            or receipt.get("owner_user_id") != owner or receipt.get("chat_id") != owner):
        return set()
    return {mission}


MORTALITY_DEPENDENCY = "mortality_source_lineage_unproven"
_MORTALITY_KEY = re.compile(r"herdmaster:herdmaster:mortality(?:-cluster)?:[a-f0-9]{20}")


def is_legacy_mortality_case(case):
    """Recognize the complete old advisory projection, never welfare completion."""
    if (not isinstance(case, dict) or case.get("specialist") != "HERDMASTER"
            or not _MORTALITY_KEY.fullmatch(str(case.get("dedupe_key") or ""))
            or case.get("message_family") or case.get("unknowns")):
        return False
    refs = case.get("evidence_refs")
    if (not isinstance(refs, (list, tuple)) or not all(isinstance(v, str) for v in refs)
            or len(set(refs)) != len(refs)):
        return False
    digests = [v for v in refs if re.fullmatch(r"[A-F0-9]{64}", v)]
    observed = [v for v in refs if v.startswith("observed:")]
    results = [v for v in refs if v.startswith("result:")]
    if len(digests) != 1 or len(observed) != 1 or len(results) != 1:
        return False
    expected = {digests[0], observed[0], results[0], "herdmaster.daily_manager_evidence.v1"}
    if set(refs) not in (expected, expected | {"attention:welfare_priority"}):
        return False
    if not re.fullmatch(r"result:HERD-NEXT-[A-F0-9]{24}:HERD-DAILY-EVIDENCE-" + digests[0][:24], results[0]):
        return False
    try:
        epoch = datetime.fromisoformat(observed[0][len("observed:"):].replace("Z", "+00:00"))
        return epoch.utcoffset() is not None
    except (ValueError, TypeError):
        return False


def _mortality_owner_binding():
    """Current private owner only; this cannot establish a historical reporter."""
    from modules.oom_sakkie.family_access import family_access_policy, resolve_family_principal
    allowed = [v.strip() for v in os.getenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "").split(",") if v.strip()]
    owner = os.getenv("OOM_SAKKIE_TELEGRAM_OWNER_USER_ID", "").strip() or (allowed[0] if len(allowed) == 1 else "")
    if not owner or not allowed or allowed[0] != owner or not family_access_policy(os.environ)["configuration_valid"]:
        raise ValueError("mortality_reconciliation_owner_unavailable")
    principal = resolve_family_principal({"telegram_user_id": owner, "telegram_chat_id": owner,
        "telegram_chat_type": "private"}, os.environ)
    if not principal.is_owner:
        raise ValueError("mortality_reconciliation_owner_unavailable")
    return _digest({"owner": owner, "private_chat": owner, "binding": principal.binding_digest})


@dataclass(frozen=True)
class MortalityReconciliationPending:
    """Internal read receipt. No changed candidate material or terminal authority."""
    projection_json: str
    owner_binding: str
    observed_at: datetime

    @property
    def projection(self):
        return json.loads(self.projection_json)

    def metadata(self):
        row = self.projection
        proof = {"contract": "herdmaster.mortality_technical_dependency.v1",
            "reason": MORTALITY_DEPENDENCY, "case_id": row["case_id"],
            "generation": row["generation"], "evidence_digest": row["evidence_digest"],
            "evidence_refs_digest": _digest(row["evidence_refs"]), "owner_binding": self.owner_binding,
            "completion_proven": False, "core_acknowledged": False}
        return {**proof, "dependency_id": "OOM-MORTALITY-DEPENDENCY-" + _digest(proof)[:32].upper()}


def _projection_json(row):
    return json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)


def mortality_pending_matches(receipt, row, claimed, *, now, cycle_id):
    """Fresh exact row, claim and recipient fences, checked again at persistence."""
    if not isinstance(receipt, MortalityReconciliationPending) or not isinstance(row, dict):
        return False
    try:
        if (not is_legacy_mortality_case(row) or _projection_json(row) != receipt.projection_json
                or receipt.owner_binding != _mortality_owner_binding()
                or not 0 <= (now - receipt.observed_at).total_seconds() <= 30
                or row.get("status") != "delegated" or row.get("assigned_worker_id") != cycle_id
                or datetime.fromisoformat(row["lease_until"]) < now):
            return False
        # The claim's status preceded delegation; all its material and delivery
        # fields must still match. The full current row also fences scheduling.
        for key in ("case_id", "dedupe_key", "specialist", "urgency", "generation", "evidence_digest",
                    "evidence_refs", "unknowns", "summary", "next_action", "last_delivery_digest"):
            if key not in claimed or row.get(key) != claimed[key]:
                return False
        return datetime.fromisoformat(row["next_reassessment_at"]) == datetime.fromisoformat(claimed["next_reassessment_at"])
    except (KeyError, TypeError, ValueError):
        return False


def collect_mortality_reconciliation(now, *, claimed_cases, connect=None, deadline_monotonic=None):
    """One bounded read of exact retained projections, not historical farm data."""
    cases = tuple(claimed_cases)
    if (not 0 < len(cases) <= 64 or any(not is_legacy_mortality_case(v) or not v.get("case_id") for v in cases)
            or len({v["case_id"] for v in cases}) != len(cases)):
        raise ValueError("mortality_reconciliation_identity_invalid")
    owner = _mortality_owner_binding()
    deadline = min(time.monotonic() + 6, deadline_monotonic if deadline_monotonic is not None else float("inf"))
    with (connect or connect_bounded_read)() as db, db.cursor() as raw_cur:
        raw_cur.execute("set transaction isolation level repeatable read read only")
        cur = ReadBudgetCursor(raw_cur, deadline, failure_kind="mortality_reconciliation_read_deadline")
        cur.execute("""select to_jsonb(m) from app_private.oom_manager_cases m
            where case_id=any(%s) order by case_id limit 65""", ([v["case_id"] for v in cases],))
        rows = [v[0] for v in cur.fetchall()]
    if time.monotonic() >= deadline:
        raise TimeoutError("mortality_reconciliation_read_deadline")
    if len(rows) != len(cases) or {v.get("case_id") for v in rows} != {v["case_id"] for v in cases}:
        raise ValueError("mortality_reconciliation_rows_unproven")
    result = {}
    for row in rows:
        if (not is_legacy_mortality_case(row)
                or not re.fullmatch(r"[a-f0-9]{64}", str(row.get("evidence_digest") or ""))
                or type(row.get("generation")) is not int or row["generation"] < 1):
            raise ValueError("mortality_reconciliation_projection_changed")
        epoch = next(v[len("observed:"):] for v in row["evidence_refs"] if v.startswith("observed:"))
        if datetime.fromisoformat(epoch.replace("Z", "+00:00")) > now:
            raise ValueError("mortality_reconciliation_observation_future")
        result[(row["dedupe_key"], row["specialist"])] = MortalityReconciliationPending(_projection_json(row), owner, now)
    return result
