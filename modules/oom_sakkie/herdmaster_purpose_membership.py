"""Full purpose membership on the existing append-only manager event rail.

Membership is completion/approval evidence, never material or delivery identity.
A narrowed current cohort cannot erase the original correction obligations.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
import time

from modules.oom_sakkie.bounded_postgres_read import ReadBudgetCursor, connect_bounded_read
from modules.oom_sakkie.herdmaster_purpose_decision import purpose_decision_binding

CONTRACT = "herdmaster.purpose_membership.v1"
MAX_MEMBERS = 5000
FIELD = "purpose_membership"
TRANSIENT = "_purpose_membership"
_PIG = re.compile(r"PIG-[A-Za-z0-9][A-Za-z0-9._-]{0,115}\Z")
_SHA = re.compile(r"[0-9a-fA-F]{64}\Z")


class PurposeMembershipError(ValueError):
    pass


def _fail(reason):
    raise PurposeMembershipError("purpose_membership_" + reason)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _instant(value):
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo is not None and result.utcoffset() is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _members(rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_MEMBERS:
        _fail("member_bound")
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"pig_id", "tag"}:
            _fail("member_shape")
        pig, tag = row["pig_id"], row["tag"]
        if (not isinstance(pig, str) or not _PIG.fullmatch(pig)
                or not isinstance(tag, str) or not tag.strip() or len(tag) > 120
                or tag != tag.strip() or any(ord(c) < 32 for c in tag)):
            _fail("member_identity")
        result.append(dict(row))
    if (len({v["pig_id"] for v in result}) != len(result)
            or len({v["tag"].casefold() for v in result}) != len(result)):
        _fail("member_duplicate")
    return sorted(result, key=lambda v: v["pig_id"])


def producer_membership(cohort):
    """Extract only exact identities from the canonical full producer packet."""
    if not isinstance(cohort, dict):
        _fail("source_shape")
    rows = cohort.get("members")
    if not isinstance(rows, list) or any(not isinstance(v, dict) for v in rows):
        _fail("source_members")
    members = _members([{"pig_id": v.get("pig_id"), "tag": v.get("tag")} for v in rows])
    ids = [v["pig_id"] for v in members]
    if (cohort.get("member_ids") != ids or not _SHA.fullmatch(str(cohort.get("material_digest") or ""))
            or cohort.get("case_key") != "herdmaster:purpose-review:" + str(cohort.get("cohort_key") or "")
            or any(v.get("litter_id") != cohort.get("litter_id") for v in cohort["members"])):
        _fail("source_identity")
    # The producer hash covers every material field, including full membership.
    if _digest({k: v for k, v in cohort.items() if k != "material_digest"}).upper() != cohort["material_digest"]:
        _fail("source_digest")
    return {"cohort_key": cohort["cohort_key"], "litter_id": cohort["litter_id"],
            "material_digest": cohort["material_digest"], "members": members,
            "member_ids": ids, "member_count": len(ids), "membership_digest": _digest(members)}


def validate_candidate_membership(candidate, value):
    """Validate transient metadata without adding it to the material digest."""
    if not isinstance(value, dict) or set(value) != {"cohort_key", "litter_id", "material_digest",
            "members", "member_ids", "member_count", "membership_digest"}:
        _fail("candidate_shape")
    refs = candidate.get("evidence_refs")
    if not isinstance(refs, list) or any(not isinstance(v, str) for v in refs):
        _fail("references")
    phases = [v for v in refs if v.startswith("phase:")]
    if len(phases) != 1 or phases[0] not in {"phase:owner_decision", "phase:held", "phase:post_wean_weight"}:
        _fail("phase")
    binding = purpose_decision_binding({**candidate, "message_family": "purpose_review", "unknowns": [],
        "evidence_refs": ["phase:owner_decision" if v.startswith("phase:") else v for v in refs]})
    members = _members(value["members"])
    ids = [v["pig_id"] for v in members]
    if (not binding or any(value.get(k) != binding[k] for k in binding)
            or members != value["members"] or ids != value["member_ids"]
            or type(value["member_count"]) is not int or value["member_count"] != len(ids)
            or value["membership_digest"] != _digest(members)
            or sorted(v[4:] for v in refs if v.startswith("pig:")) != ids[:12]):
        _fail("candidate_identity")
    return dict(value)


def build_record(candidate, *, generation, now, previous=None, legacy_epoch=None):
    value = validate_candidate_membership(candidate, candidate[TRANSIENT])
    if type(generation) is not int or generation < 1 or not _instant(now):
        _fail("epoch")
    if legacy_epoch is not None and (not _instant(legacy_epoch) or legacy_epoch > now or previous is not None):
        _fail("legacy_epoch")
    obligations = {}
    if previous is not None:
        previous = validate_record(previous)
        if (previous["case_id"] != candidate["case_id"] or previous["cohort_key"] != value["cohort_key"]
                or previous["generation"] >= generation):
            _fail("lineage")
        obligations = {v["pig_id"]: dict(v) for v in previous["obligations"]}
    for member in value["members"]:
        # An existing ID retains its first proof epoch and original visible tag.
        obligations.setdefault(member["pig_id"], {**member, "required_since": (legacy_epoch or now).isoformat()})
    if len(obligations) > MAX_MEMBERS:
        _fail("obligation_bound")
    origin = previous["origin"] if previous else {"generation": generation,
        "scope": "legacy_current_generation" if legacy_epoch is not None else "new_case_lineage",
        "proof_epoch": (legacy_epoch or now).isoformat(),
        "evidence_digest": candidate["evidence_digest"], "material_digest": value["material_digest"],
        "member_ids": value["member_ids"], "membership_digest": value["membership_digest"],
        "recorded_at": now.isoformat()}
    record = {"contract": CONTRACT, "case_id": candidate["case_id"], "dedupe_key": candidate["dedupe_key"],
        "generation": generation, "evidence_digest": candidate["evidence_digest"], **value,
        "recorded_at": now.isoformat(), "origin": origin,
        "obligations": sorted(obligations.values(), key=lambda v: v["pig_id"])}
    return validate_record({**record, "snapshot_digest": _digest(record)})


def validate_record(record):
    if not isinstance(record, dict) or record.get("contract") != CONTRACT:
        _fail("record_missing")
    if record.get("snapshot_digest") != _digest({k: v for k, v in record.items() if k != "snapshot_digest"}):
        _fail("record_digest")
    generation, recorded = record.get("generation"), _instant(record.get("recorded_at"))
    if (type(generation) is not int or generation < 1 or not recorded
            or not _SHA.fullmatch(str(record.get("evidence_digest") or ""))
            or not isinstance(record.get("case_id"), str)):
        _fail("record_identity")
    members = _members(record.get("members"))
    ids = [v["pig_id"] for v in members]
    if (record.get("member_ids") != ids or record.get("member_count") != len(ids)
            or type(record.get("member_count")) is not int or members != record["members"]
            or record.get("membership_digest") != _digest(members)
            or record.get("dedupe_key") != "herdmaster:purpose-review:" + str(record.get("cohort_key") or "")):
        _fail("record_members")
    obligations = record.get("obligations")
    if not isinstance(obligations, list) or any(not isinstance(v, dict) for v in obligations):
        _fail("obligations")
    full = _members([{k: v.get(k) for k in ("pig_id", "tag")} for v in obligations])
    if (any(set(v) != {"pig_id", "tag", "required_since"} or not _instant(v["required_since"])
            or _instant(v["required_since"]) > recorded for v in obligations)
            or [v["pig_id"] for v in obligations] != [v["pig_id"] for v in full]
            or not set(ids) <= {v["pig_id"] for v in full}):
        _fail("obligations")
    origin = record.get("origin")
    if (not isinstance(origin, dict) or type(origin.get("generation")) is not int
            or origin.get("scope") not in {"legacy_current_generation", "new_case_lineage"}
            or not _instant(origin.get("proof_epoch"))
            or _instant(origin["proof_epoch"]) > recorded
            or not 1 <= origin["generation"] <= generation or not _instant(origin.get("recorded_at"))
            or _instant(origin["recorded_at"]) > recorded
            or not isinstance(origin.get("member_ids"), list) or not origin["member_ids"]
            or any(not isinstance(v, str) or not _PIG.fullmatch(v) for v in origin["member_ids"])
            or origin["member_ids"] != sorted(set(origin["member_ids"]))
            or not set(origin["member_ids"]) <= {v["pig_id"] for v in full}
            or any(not _SHA.fullmatch(str(origin.get(k) or "")) for k in
                   ("evidence_digest", "material_digest", "membership_digest"))):
        _fail("origin")
    origin_members = [{"pig_id": v["pig_id"], "tag": v["tag"]} for v in obligations if v["pig_id"] in origin["member_ids"]]
    if _digest(origin_members) != origin["membership_digest"]:
        _fail("origin_members")
    return record


def event_record(event, *, case_id, generation=None):
    """Only a same-case append-only event can supply the retained snapshot."""
    if not isinstance(event, dict):
        _fail("event_shape")
    payload = event.get("event_payload", event)
    record = validate_record(payload.get(FIELD) if isinstance(payload, dict) else None)
    if (event.get("case_id") != case_id or payload.get("case_id") != case_id
            or event.get("generation") != record["generation"]
            or payload.get("generation") != record["generation"]
            or record["case_id"] != case_id
            or (generation is not None and record["generation"] != generation)
            or event.get("event_type") not in {"created", "evidence_changed", "reassessment_scheduled"}
            or _instant(event.get("occurred_at")) != _instant(record["recorded_at"])):
        _fail("event_binding")
    return record


def read_latest_event(cur, case_id, generation):
    cur.execute("""select case_id,generation,event_type,event_payload,occurred_at
        from app_private.oom_manager_case_events where case_id=%s and generation<=%s
          and event_payload ? 'purpose_membership'
        order by generation desc,occurred_at desc,event_id desc limit 2""", (case_id, generation))
    rows = cur.fetchall()
    if not rows:
        return None
    if len(rows) > 1 and rows[0][1] == rows[1][1]:
        _fail("ambiguous_events")
    event = dict(zip(("case_id", "generation", "event_type", "event_payload", "occurred_at"), rows[0]))
    event_record(event, case_id=case_id)
    return event


def read_latest_record(cur, case_id, generation):
    event = read_latest_event(cur, case_id, generation)
    return event_record(event, case_id=case_id) if event else None


def legacy_adoption_epoch(cur, candidate, generation):
    """Only the already-proven uncapped current generation can be adopted.

    Capped legacy history remains unknown. A material transition observed after
    rollout without prior full metadata is explicitly ineligible for adoption.
    """
    if candidate[TRANSIENT]["member_count"] >= 12:
        return None
    cur.execute("""select occurred_at,event_payload from app_private.oom_manager_case_events
        where case_id=%s and generation=%s and event_type in ('created','evidence_changed')
        order by occurred_at,event_id limit 2""", (candidate["case_id"], generation))
    rows = cur.fetchall()
    if len(rows) != 1 or rows[0][1].get("purpose_membership_unavailable"):
        return None
    return _instant(rows[0][0])


def verify_current_membership(case, snapshot, *, membership_events, now,
                              expected_generation=None, expected_evidence_digest=None):
    """Pure exact-current read gate; never adopts metadata or authorizes a write."""
    if (not _instant(now) or case.get("status") not in {"open", "waiting_reassessment", "exception"}
            or case.get("assigned_worker_id") or case.get("lease_until")
            or (expected_generation is not None and case.get("generation") != expected_generation)
            or (expected_evidence_digest is not None and case.get("evidence_digest") != expected_evidence_digest)):
        _fail("case_stale_or_leased")
    case = {**case, "message_family": "purpose_review"}
    if not purpose_decision_binding(case):
        _fail("decision_unavailable")
    if not isinstance(membership_events, list) or len(membership_events) != 1:
        _fail("event_missing_or_ambiguous")
    observed = _instant(snapshot.get("snapshot_observed_at"))
    if not observed or not 0 <= (now - observed).total_seconds() <= 120:
        _fail("source_timestamp")
    record = event_record(membership_events[0], case_id=case["case_id"], generation=case["generation"])
    if record["evidence_digest"] != case["evidence_digest"] or _instant(record["recorded_at"]) > now:
        _fail("case_stale")
    work = snapshot.get("purpose_work") or {}
    from modules.pig_weights.herdmaster_purpose_work import CONTRACT as WORK_CONTRACT
    if work.get("contract") != WORK_CONTRACT or work.get("state") != "checked":
        _fail("source_unavailable")
    found = [v for v in work.get("cohorts", []) if v.get("case_key") == case["dedupe_key"]]
    if len(found) != 1 or found[0].get("phase") != "decision_due" or found[0].get("blocked") != []:
        _fail("source_held_or_missing")
    current = validate_candidate_membership(case, producer_membership(found[0]))
    if any(current[k] != record[k] for k in current):
        _fail("source_changed")
    original_tags = {v["pig_id"]: v["tag"] for v in record["obligations"]}
    if any(original_tags[v["pig_id"]] != v["tag"] for v in current["members"]):
        _fail("original_identity_changed")
    return {"case_id": case["case_id"], "generation": case["generation"],
        "evidence_digest": case["evidence_digest"], **current,
        "snapshot_digest": record["snapshot_digest"], "origin": record["origin"],
        "completion_member_ids": [v["pig_id"] for v in record["obligations"]]}


def load_current_membership(case_id, snapshot, *, now, expected_generation=None,
                            expected_evidence_digest=None, connect=None, transaction_managed=False,
                            lock_case=False, deadline_monotonic=None):
    """Two exact bounded SELECTs in a read-only snapshot; no metadata adoption."""
    deadline = min(time.monotonic() + 5, deadline_monotonic) if deadline_monotonic is not None else time.monotonic() + 5
    if time.monotonic() >= deadline:
        raise TimeoutError("purpose_membership_read_deadline")
    with (connect or connect_bounded_read)() as db, db.cursor() as raw:
        if not transaction_managed:
            raw.execute("set transaction isolation level repeatable read read only")
        cur = ReadBudgetCursor(raw, deadline, failure_kind="purpose_membership_read_deadline")
        if lock_case and not transaction_managed:
            _fail("lock_requires_owned_transaction")
        cur.execute("""select case_id,dedupe_key,specialist,generation,evidence_digest,evidence_refs,
            unknowns,status,assigned_worker_id,lease_until from app_private.oom_manager_cases
            where case_id=%s limit 1""" + (" for update" if lock_case else ""), (case_id,))
        row = cur.fetchone()
        if not row:
            _fail("case_missing")
        case = dict(zip(("case_id", "dedupe_key", "specialist", "generation", "evidence_digest", "evidence_refs",
            "unknowns", "status", "assigned_worker_id", "lease_until"), row))
        event = read_latest_event(cur, case_id, case["generation"])
        events = [event] if event else []
        result = verify_current_membership(case, snapshot, membership_events=events, now=now,
            expected_generation=expected_generation, expected_evidence_digest=expected_evidence_digest)
        if time.monotonic() >= deadline:
            raise TimeoutError("purpose_membership_read_deadline")
        return result


def list_current_review_cases(snapshot, *, now, connect=None, transaction_managed=False,
                              owning_cycle_id=None, deadline_monotonic=None):
    """Bounded owner overview, explicitly retaining unavailable/legacy entries."""
    deadline = min(time.monotonic() + 5, deadline_monotonic) if deadline_monotonic is not None else time.monotonic() + 5
    if time.monotonic() >= deadline:
        raise TimeoutError("purpose_membership_read_deadline")
    with (connect or connect_bounded_read)() as db, db.cursor() as raw:
        if not transaction_managed:
            raw.execute("set transaction isolation level repeatable read read only")
        cur = ReadBudgetCursor(raw, deadline, failure_kind="purpose_membership_read_deadline")
        cur.execute("""select case_id,dedupe_key,specialist,generation,evidence_digest,evidence_refs,
            unknowns,status,assigned_worker_id,lease_until,last_delivery_digest from app_private.oom_manager_cases
            where specialist='HERDMASTER' and starts_with(dedupe_key,'herdmaster:purpose-review:')
              and status in ('open','waiting_reassessment','exception','delegated')
            order by case_id limit 65""")
        rows = cur.fetchall()
        if len(rows) > 64:
            _fail("case_bound")
        cases = [dict(zip(("case_id", "dedupe_key", "specialist", "generation", "evidence_digest", "evidence_refs",
            "unknowns", "status", "assigned_worker_id", "lease_until", "last_delivery_digest"), row)) for row in rows]
        if not cases:
            return {"cases": [], "unavailable_count": 0}
        cur.execute("""select e.case_id,e.generation,e.event_type,e.event_payload,e.occurred_at
            from app_private.oom_manager_cases c cross join lateral (
                select * from app_private.oom_manager_case_events h
                where h.case_id=c.case_id and h.generation=c.generation
                  and h.event_payload ? 'purpose_membership'
                order by h.occurred_at desc,h.event_id desc limit 2) e
            where c.case_id=any(%s) order by e.case_id,e.occurred_at limit 129""",
            ([c["case_id"] for c in cases],))
        events = [dict(zip(("case_id", "generation", "event_type", "event_payload", "occurred_at"), row)) for row in cur.fetchall()]
        if len(events) > 128:
            _fail("event_bound")
        result = []
        for case in cases:
            row = {k: case[k] for k in ("case_id", "dedupe_key", "generation", "evidence_digest", "last_delivery_digest")}
            try:
                own_lease = bool(owning_cycle_id and case.get("status") == "delegated"
                    and case.get("assigned_worker_id") == owning_cycle_id
                    and _instant(case.get("lease_until")) and _instant(case["lease_until"]) > now)
                read_case = ({**case, "status": "waiting_reassessment", "assigned_worker_id": None,
                    "lease_until": None} if own_lease else case)
                row["membership"] = verify_current_membership(read_case, snapshot,
                    membership_events=[e for e in events if e["case_id"] == case["case_id"]], now=now)
                if own_lease:
                    row["membership"]["read_only_cycle_membership"] = True
                row["available"] = True
            except PurposeMembershipError as exc:
                row.update(available=False, reason=str(exc))
            result.append(row)
        if time.monotonic() >= deadline:
            raise TimeoutError("purpose_membership_read_deadline")
        return {"cases": result, "unavailable_count": sum(not row["available"] for row in result)}
