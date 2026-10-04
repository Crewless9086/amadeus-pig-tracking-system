"""Bounded owning proof for retained purpose cases; never a farm writer."""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import time

from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read, ReadBudgetCursor
from modules.oom_sakkie.herdmaster_case_disposition import FENCE, FAMILY
from modules.oom_sakkie.herdmaster_purpose_decision import PREFIX, purpose_decision_binding
from modules.pig_weights.purpose_correction_batch_service import (
    CONTRACT_VERSION, _decisions, _decision_hash, _preview_digest,
)

from modules.pig_weights.herdmaster_purpose_work import UNKNOWN_PURPOSES

MAX_CASES = 64
MAX_ROWS = 2048
UNKNOWN = UNKNOWN_PURPOSES | {"none", "n/a", "na", "not recorded"}


def _instant(value):
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def retained_members(case):
    """The legacy producer retained first twelve IDs; twelve cannot prove all."""
    refs = case.get("evidence_refs")
    if not isinstance(refs, list) or any(not isinstance(v, str) for v in refs):
        return None
    phases = [v for v in refs if v.startswith("phase:")]
    if len(phases) != 1 or phases[0] not in {
            "phase:owner_decision", "phase:post_wean_weight", "phase:held"}:
        return None
    # Reuse the owning producer's identity contract, not its delivery eligibility.
    binding = purpose_decision_binding({**case, "message_family": "purpose_review",
        "unknowns": [], "evidence_refs": ["phase:owner_decision" if v == phases[0] else v for v in refs]})
    pigs = [v[4:] for v in refs if v.startswith("pig:")]
    if not binding or not 0 < len(pigs) < 12:
        return None
    return {**binding, "pig_ids": sorted(pigs)}


def _event_proof(event, batch, pig, epoch, now):
    """Bind the executed immutable approved snapshot to its exact event/current row."""
    if not isinstance(event, dict) or not isinstance(batch, dict):
        return None
    occurred, approved, executed = (_instant(event.get("occurred_at")),
        _instant(batch.get("owner_approved_at")), _instant(batch.get("executed_at")))
    payload, envelope = event.get("payload_json"), batch.get("decisions_json")
    actor = batch.get("created_by")
    if (not all((occurred, approved, executed, actor)) or not epoch <= occurred <= now
            or not approved <= occurred or not approved <= executed <= now
            or batch.get("status") != "executed"
            or actor != batch.get("owner_approved_by") or actor != batch.get("executed_by")
            or not isinstance(payload, dict) or not isinstance(envelope, dict)
            or envelope.get("contract_version") != CONTRACT_VERSION
            or event.get("event_type") != "pig.purpose_corrected"
            or event.get("source_system") != "herdmaster_purpose_correction"
            or event.get("authority_tier") != "owner_approved"
            or event.get("privacy_class") != "owner_private"
            or not event.get("event_id")
            or _instant(event.get("recorded_at")) != occurred
            or _instant(event.get("freshness_at")) != occurred
            or event.get("domain") != "animals" or event.get("aggregate_type") != "pig"
            or event.get("actor_type") != "owner" or event.get("actor_id") != actor
            or event.get("aggregate_id") != pig["pig_id"]
            or event.get("correlation_id") != batch.get("batch_id")
            or payload.get("batch_id") != batch.get("batch_id")
            or payload.get("approved_by") != actor
            or _instant(payload.get("approved_at")) != approved):
        return None
    decisions, errors = _decisions(envelope.get("decisions"))
    if (errors or decisions != envelope.get("decisions")
            or _decision_hash(decisions) != batch.get("decision_hash")
            or _preview_digest(decisions, envelope.get("effects"), envelope.get("return_to") or "")
                != envelope.get("preview_digest")):
        return None
    selected = [v for v in decisions if v["pig_id"] == pig["pig_id"]]
    effects = envelope.get("effects")
    if not isinstance(effects, list) or any(not isinstance(v, dict) for v in effects):
        return None
    matching = [v for v in effects if v.get("pig_id") == pig["pig_id"]]
    if len(selected) != 1 or len(matching) != 1:
        return None
    item, effect = selected[0], matching[0]
    expected_key = hashlib.sha256(f"{batch['batch_id']}|{pig['pig_id']}|{batch['decision_hash']}".encode()).hexdigest()
    if (event.get("provenance_json") != {"source_ref": "pig_current_state", "weight_date": effect.get("latest_weight_date")}
            or event.get("idempotency_key") != expected_key
            or payload.get("new_purpose") != item["purpose"] or pig.get("purpose") != item["purpose"]
            or effect.get("new_purpose") != item["purpose"]
            or effect.get("tag_number") != (pig.get("tag_number") or "")
            or payload.get("old_purpose") != effect.get("old_purpose")
            or any(payload.get(k) != item[k] or effect.get(k) != item[k] for k in ("reason", "note"))):
        return None
    return {"event": event, "batch": batch}


def completion_candidate(case, pigs, history, *, now):
    """An omission or partial group never becomes a terminal projection."""
    from modules.oom_sakkie.manager_case_sources import _candidate
    bound = retained_members(case)
    epoch = _instant(case.get("generation_started_at"))
    if (not bound or not epoch or epoch > now or not case.get("evidence_digest")
            or type(case.get("generation")) is not int or case["generation"] < 1):
        return None
    if len(pigs) != len({v.get("pig_id") for v in pigs}):
        return None
    by_id = {v.get("pig_id"): v for v in pigs}
    targets = [by_id.get(identity) for identity in bound["pig_ids"]]
    if any(v is None for v in targets):
        return None
    cohort = [v for v in pigs if (v.get("litter_id") or "") == bound["litter_id"]] if bound["litter_id"] else targets
    if (any((v.get("litter_id") or "") != bound["litter_id"] for v in targets)
            or any(str(v.get("purpose") or "").strip().casefold() in UNKNOWN for v in cohort)
            or any(v.get("status") != "Active" or v.get("on_farm") is not True for v in targets)):
        return None
    proofs = []
    for pig in targets:
        events = [(event, batch) for event, batch in history if event.get("aggregate_id") == pig["pig_id"]]
        if not events:
            return None
        dated = [(_instant(event.get("occurred_at")), event, batch) for event, batch in events]
        if any(value[0] is None or value[0] > now for value in dated):
            return None
        dated.sort(key=lambda v: v[0], reverse=True)
        if len(dated) > 1 and dated[0][0] == dated[1][0]:
            return None
        proof = _event_proof(dated[0][1], dated[0][2], pig, epoch, now)
        if not proof:
            return None
        proofs.append(proof)
    refs = [v for v in case["evidence_refs"] if v.startswith(("pig:", "litter:", "purpose_work:"))]
    refs += [FENCE + str(case["generation"]) + ":" + case["evidence_digest"],
        "herdmaster_disposition:approved_purpose_correction_complete",
        "disposition_evidence:" + _digest({"members": targets, "proofs": proofs}),
        "observed:" + now.isoformat()]
    return _candidate(case["dedupe_key"], "HERDMASTER", "watch", refs, [],
        "The retained purpose review is complete from approved canonical corrections.",
        "The existing case is closed from recorded purpose evidence; no farm action or owner message is required.",
        now + timedelta(minutes=30), message_family=FAMILY, terminal_state="completed")


def collect_purpose_completions(now, *, connect=None):
    """One read-only snapshot, fixed row caps and one six-second budget."""
    if not _instant(now):
        raise ValueError("purpose_completion_time_invalid")
    deadline = time.monotonic() + 6
    with (connect or connect_bounded_read)() as db, db.cursor() as raw:
        raw.execute("set transaction isolation level repeatable read read only")
        cur = ReadBudgetCursor(raw, deadline, failure_kind="purpose_completion_read_deadline")
        cur.execute("""select case_id,dedupe_key,generation,evidence_digest,evidence_refs
            from app_private.oom_manager_cases
            where specialist='HERDMASTER' and status in ('open','delegated','waiting_reassessment','exception')
              and starts_with(dedupe_key,'herdmaster:purpose-review:')
            order by case_id limit 65""")
        rows = cur.fetchall()
        if len(rows) > MAX_CASES:
            raise ValueError("purpose_completion_case_bound_exceeded")
        cases = [dict(zip(("case_id", "dedupe_key", "generation", "evidence_digest", "evidence_refs"), row), specialist="HERDMASTER") for row in rows]
        cases = [row for row in cases if retained_members(row)]
        if not cases:
            return []
        ids = sorted({v for row in cases for v in retained_members(row)["pig_ids"]})
        litters = sorted({retained_members(row)["litter_id"] for row in cases} - {""})
        cur.execute("""select e.case_id,e.generation,e.occurred_at from app_private.oom_manager_case_events e
            join app_private.oom_manager_cases c on c.case_id=e.case_id and c.generation=e.generation
            where e.case_id=any(%s) and e.event_type in ('created','evidence_changed')
            order by e.case_id,e.occurred_at limit 129""", ([row["case_id"] for row in cases],))
        epochs = cur.fetchall()
        if len(epochs) > 128:
            raise ValueError("purpose_completion_epoch_bound_exceeded")
        for row in cases:
            matches = [value[2] for value in epochs if value[:2] == (row["case_id"], row["generation"])]
            row["generation_started_at"] = matches[0] if len(matches) == 1 else None
        cur.execute("""select pig_id,tag_number,litter_id,purpose,status,on_farm
            from public.current_canonical_pigs where pig_id=any(%s) or litter_id=any(%s)
            order by pig_id limit 2049""", (ids, litters))
        pigs = [dict(zip(("pig_id", "tag_number", "litter_id", "purpose", "status", "on_farm"), row)) for row in cur.fetchall()]
        if len(pigs) > MAX_ROWS:
            raise ValueError("purpose_completion_member_bound_exceeded")
        cur.execute("""select to_jsonb(e),to_jsonb(b) from public.operational_events e
            left join public.pig_purpose_correction_batches b on b.batch_id=e.correlation_id
            where e.aggregate_id=any(%s) and e.event_type='pig.purpose_corrected'
            order by e.aggregate_id,e.occurred_at desc,e.event_id limit 2049""", (ids,))
        history = cur.fetchall()
        if len(history) > MAX_ROWS:
            raise ValueError("purpose_completion_history_bound_exceeded")
        result = [completion_candidate(case, pigs, history, now=now) for case in cases]
        if time.monotonic() >= deadline:
            raise TimeoutError("purpose_completion_read_deadline")
        return [row for row in result if row is not None]
