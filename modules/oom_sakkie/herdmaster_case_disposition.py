"""Owning, read-only disposition of retained HERDMASTER advisories.

Only the two existing per-animal advisory families are addressed. Protected
reports, confirmations and farm operations are never completed by this reader.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import re
import time

from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read

FENCE = "herdmaster_case_fence:"
FAMILY = "herdmaster_disposition"


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


class _ReadBudgetCursor:
    def __init__(self, cursor, deadline):
        self.cursor, self.deadline = cursor, deadline

    def execute(self, statement, params=None):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("herdmaster_disposition_read_deadline")
        self.cursor.execute("select set_config('statement_timeout',%s,true)",
                            (str(max(1, min(3000, int(remaining * 1000)))),))
        return self.cursor.execute(statement, params)

    def __getattr__(self, name):
        return getattr(self.cursor, name)


def collect_advisory_dispositions(now, *, current_keys=(), connect=None):
    """Acquire one consistent, bounded snapshot; omission is never completion."""
    from modules.oom_sakkie.manager_case_sources import _candidate
    deadline = time.monotonic() + 6
    with (connect or connect_bounded_read)() as db, db.cursor() as raw_cur:
        raw_cur.execute("set transaction isolation level repeatable read read only")
        cur = _ReadBudgetCursor(raw_cur, deadline)
        cur.execute("""select case_id,dedupe_key,generation,evidence_digest,evidence_refs
            from app_private.oom_manager_cases where specialist='HERDMASTER'
              and status in ('open','delegated','waiting_reassessment','exception')
              and (dedupe_key like 'herdmaster:herdmaster:PIG-%%'
                or dedupe_key ~ '^herdmaster:pig-[A-Za-z0-9-]+-withdrawal-sales$')
            order by case_id limit 65""")
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
            return []
        ids = sorted({row[-1][0] for row in selected})
        cur.execute("""select pig_id,tag_number,status,on_farm
            from public.current_canonical_pigs where pig_id=any(%s)
            order by pig_id limit 65""", (ids,))
        pigs = cur.fetchall()
        if len(pigs) != len({row[0] for row in pigs}) or len(pigs) > 64:
            raise ValueError("herdmaster_disposition_identity_ambiguous")
        by_id = {row[0]: row for row in pigs}
        result = []
        for case_id, key, generation, digest, refs, (pig, tag) in selected:
            row = by_id.get(pig)
            terminal = bool(row and (not tag or str(row[1]).casefold() == tag.casefold())
                and str(row[2] or "").casefold() in {"dead", "deceased", "died", "sold", "culled"}
                and row[3] is False)
            proof = "canonical_off_farm" if terminal else "source_reconciliation_required"
            proof_refs = []
            if not terminal and not tag and row:
                proof_refs = _completed_observation(cur, pig, refs)
                terminal = bool(proof_refs)
                if terminal:
                    proof = "confirmed_observation_recorded"
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
        return result


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
            for row in history if row[0].get("mission_id") in missions}) != 1:
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
