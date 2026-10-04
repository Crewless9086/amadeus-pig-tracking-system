"""Typed purpose-decision admission and presentation; no farm-write authority."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
import re
import time
from urllib.parse import urlencode, urlsplit

from modules.oom_sakkie.bounded_postgres_read import (
    ReadBudgetCursor, connect_bounded_read, is_database_unavailable)

PREFIX = "herdmaster:purpose-review:"
FAMILY = "purpose_review"
_IDENTIFIER = r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}"
_PIG = r"PIG-[A-Za-z0-9][A-Za-z0-9._-]{0,115}"


def purpose_decision_binding(case):
    """Recognize only the existing producer's fully attributed decision phase."""
    if (case.get("specialist") != "HERDMASTER" or case.get("unknowns") != []
            or case.get("message_family") != FAMILY):
        return None
    key = str(case.get("dedupe_key") or "")
    if not key.startswith(PREFIX) or not re.fullmatch(_IDENTIFIER, key[len(PREFIX):]):
        return None
    cohort = key[len(PREFIX):]
    refs = case.get("evidence_refs")
    if not isinstance(refs, (tuple, list)) or any(not isinstance(r, str) for r in refs):
        return None
    def values(prefix):
        return [r[len(prefix):] for r in refs if r.startswith(prefix)]
    if (values("manager_message_family:") != [FAMILY]
            or values("phase:") != ["owner_decision"] or values("rule_day:") != ["14"]
            or values("purpose_work:") != [cohort]):
        return None
    digests, litters, pigs = values("purpose_evidence:"), values("litter:"), values("pig:")
    if (len(digests) != 1 or not re.fullmatch(r"[0-9A-Fa-f]{64}", digests[0])
            or not 1 <= len(pigs) <= 12 or len(set(pigs)) != len(pigs)
            or any(not re.fullmatch(_PIG, pig) for pig in pigs)
            or not (litters == [cohort] or (not litters and pigs == [cohort]))):
        return None
    return {"cohort_key": cohort, "litter_id": cohort if litters else "",
            "material_digest": digests[0]}


# Same closed reference contract for persisted cases. SQL has no presentation
# columns or new schema: it inspects only the immutable existing producer refs.
PURPOSE_DECISION_SQL = r"""(m.specialist='HERDMASTER' and m.unknowns='[]'::jsonb
 and m.dedupe_key ~ '^herdmaster:purpose-review:[A-Za-z0-9][A-Za-z0-9._-]{0,119}$'
 and not exists(select 1 from jsonb_array_elements(
    case when jsonb_typeof(m.evidence_refs)='array' then m.evidence_refs else '[]'::jsonb end) value
    where jsonb_typeof(value)<>'string')
 and (select
    count(*) filter(where starts_with(ref,'manager_message_family:'))=1
    and count(*) filter(where ref='manager_message_family:purpose_review')=1
    and count(*) filter(where starts_with(ref,'phase:'))=1
    and count(*) filter(where ref='phase:owner_decision')=1
    and count(*) filter(where starts_with(ref,'rule_day:'))=1
    and count(*) filter(where ref='rule_day:14')=1
    and count(*) filter(where starts_with(ref,'purpose_work:'))=1
    and count(*) filter(where ref='purpose_work:' || substr(m.dedupe_key,length('herdmaster:purpose-review:')+1))=1
    and count(*) filter(where starts_with(ref,'purpose_evidence:'))=1
    and count(*) filter(where ref ~ '^purpose_evidence:[0-9A-Fa-f]{64}$')=1
    and count(*) filter(where starts_with(ref,'pig:')) between 1 and 12
    and count(*) filter(where starts_with(ref,'pig:'))=
        count(distinct ref) filter(where ref ~ '^pig:PIG-[A-Za-z0-9][A-Za-z0-9._-]{0,115}$')
    and ((count(*) filter(where starts_with(ref,'litter:'))=1
          and count(*) filter(where ref='litter:' || substr(m.dedupe_key,length('herdmaster:purpose-review:')+1))=1)
      or (count(*) filter(where starts_with(ref,'litter:'))=0
          and count(*) filter(where starts_with(ref,'pig:'))=1
          and count(*) filter(where ref='pig:' || substr(m.dedupe_key,length('herdmaster:purpose-review:')+1))=1))
    from jsonb_array_elements_text(case when jsonb_typeof(m.evidence_refs)='array'
        then m.evidence_refs else '[]'::jsonb end) as refs(ref)))"""


def purpose_refresh_receipt(raw, current, *, now, cycle_id):
    """Carry the successful owning refresh to delivery without changing digests."""
    binding = purpose_decision_binding(current)
    facts = raw.get("_purpose_review") or {}
    if not _valid_facts(binding, facts):
        return None
    return {"case_id": current["case_id"], "generation": current["generation"],
            "evidence_digest": current["evidence_digest"], "cycle_id": cycle_id,
            "refreshed_at": now.isoformat(), "binding": binding, "facts": dict(facts)}


def _valid_facts(binding, facts):
    return bool(binding and isinstance(facts, dict) and facts.get("phase") == "decision_due"
        and facts.get("material_digest") == binding["material_digest"]
        and facts.get("cohort_key") == binding["cohort_key"]
        and type(facts.get("member_count")) is int and 1 <= facts["member_count"] <= 5000
        and isinstance(facts.get("label"), str) and len(facts["label"]) <= 60)


def current_purpose_owner():
    from modules.oom_sakkie.family_access import OWNER_USER_ID_ENV, resolve_family_principal
    # This scheduled decision never infers an owner from allowlist membership.
    owner = str(os.getenv(OWNER_USER_ID_ENV) or "").strip()
    allowed = {v.strip() for v in os.getenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "").split(",")}
    principal = resolve_family_principal({"telegram_user_id": owner,
        "telegram_chat_id": owner, "telegram_chat_type": "private"}, os.environ)
    return principal if owner and owner in allowed and principal.is_owner else None


def purpose_delivery_current(case, *, now=None, deadline_monotonic=None, clock=None):
    """Read one durable lease fence; do not rerun the broad herd collector."""
    from modules.oom_sakkie.general_manager_worker import CASE_COMPLETION_RESERVE_SECONDS, LEASE
    clock = clock or (lambda: datetime.now(timezone.utc))
    now = now or clock()
    binding = purpose_decision_binding(case)
    receipt = case.get("_purpose_review_refresh") or {}
    try:
        refreshed = datetime.fromisoformat(str(receipt.get("refreshed_at") or ""))
    except (TypeError, ValueError):
        return False
    if (not binding or receipt.get("binding") != binding
            or not _valid_facts(binding, receipt.get("facts")) or refreshed.tzinfo is None
            or refreshed > now or now-refreshed >= LEASE
            or any(receipt.get(key) != case.get(key) for key in ("case_id", "generation", "evidence_digest"))
            or not case.get("_manager_cycle_id") or receipt.get("cycle_id") != case["_manager_cycle_id"]):
        return False
    deadline = min(time.monotonic()+6, deadline_monotonic-CASE_COMPLETION_RESERVE_SECONDS
                   if deadline_monotonic is not None else float("inf"))
    if deadline-time.monotonic() < 3:
        return False
    try:
        with connect_bounded_read() as connection, connection.cursor() as raw:
            raw.execute("set transaction read only")
            raw.execute("set local lock_timeout='1000ms'")
            cur = ReadBudgetCursor(raw, deadline, failure_kind="purpose_delivery_read_deadline")
            cur.execute("""select status,generation,evidence_digest,assigned_worker_id,lease_until,
                last_heartbeat_at,last_delivery_digest,evidence_refs,unknowns
                from app_private.oom_manager_cases
                where case_id=%s and dedupe_key=%s and specialist='HERDMASTER'""",
                (case["case_id"], case["dedupe_key"]))
            row = cur.fetchone()
        # A lease may expire while its SELECT is in flight. The provider gate
        # uses a fresh clock after that read, not only the preparation instant.
        checked_at = clock()
        return bool(checked_at >= now and checked_at-refreshed < LEASE
            and row and row[0] == "delegated" and row[1] == case["generation"]
            and row[2] == case["evidence_digest"] and row[3] == receipt["cycle_id"]
            and row[4] is not None and row[4] > checked_at and row[5] == refreshed
            and row[6] != row[2] and row[7] == case["evidence_refs"] and row[8] == []
            and time.monotonic() < deadline)
    except Exception as exc:
        if isinstance(exc, (ValueError, RuntimeError, OSError)) or is_database_unavailable(exc):
            return False
        raise


def build_purpose_review(case, *, principal, now=None, deadline_monotonic=None):
    if not purpose_delivery_current(case, now=now, deadline_monotonic=deadline_monotonic):
        return {"success": False, "status": "purpose_review_delivery_context_changed",
                "delivery_confirmed": False, "telegram_sends": 0, "writes_farm_data": False}
    from modules.oom_sakkie.family_presentation import heading
    receipt = case["_purpose_review_refresh"]
    facts, binding = receipt["facts"], receipt["binding"]
    af = principal.language == "af"
    label = facts["label"] or ("Groep vir doelkeuse" if af else "Purpose review group")
    count = facts["member_count"]
    lines = [heading(label + (" — doelkeuse" if af else " — purpose review"), emoji="🐷"), "",
        (f"• Die {count} diere se gewigte ná speen is gereed vir hierdie hersiening." if af else
         f"• The {count} animals have the post-weaning weights needed for this review."), "",
        ("<b>Volgende:</b> Hersien HERDMASTER se groepsaanbeveling in Pig Allocation en kies hul doel daar." if af else
         "<b>Next:</b> Review HERDMASTER's grouped recommendation in Pig Allocation and choose their purpose there."),
        ("Niks is goedgekeur, toegewys, gereserveer of verkoop nie." if af else
         "Nothing has been approved, allocated, reserved or sold."), "",
        ("Ek sal weer kyk wanneer die bewyse of jou besluit verander." if af else
         "I'll reassess when the evidence or your decision changes.")]
    result = {"success": True, "status": "purpose_review_owner_attention", "answer": "\n".join(lines),
        "result_digest": case["evidence_digest"], "recipient_language": principal.language,
        "recipient_render_contract": "specialist_structured_recipient_v1", "writes_farm_data": False,
        "hardware_commands": 0}
    # Existing owner-read Pig Allocation surface; URL buttons never consume a
    # protected decision. Missing/unsafe base configuration produces text only.
    base = str(os.getenv("AMADEUS_BACKEND_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    try:
        url = urlsplit(base)
    except ValueError:
        return result
    if (url.scheme == "https" and url.netloc and not url.username and not url.password
            and not url.query and not url.fragment and url.path in ("", "/")):
        query = {"mode": "purpose-review"}
        if binding["litter_id"]:
            query["litter_id"] = binding["litter_id"]
        result["reply_markup"] = {"inline_keyboard": [[{
            "text": "Hersien in Pig Allocation" if af else "Review in Pig Allocation",
            "url": base + "/pig-allocation?" + urlencode(query)}]]}
    return result


def load_purpose_delivery_events(card_id, *, deadline_monotonic=None):
    """Read at most three retained rows: more than two cannot authorize retry."""
    from modules.oom_sakkie.general_manager_worker import CASE_COMPLETION_RESERVE_SECONDS
    from modules.oom_sakkie.family_message_lifecycle import EVENT_SOURCE
    deadline = min(time.monotonic()+6, deadline_monotonic-CASE_COMPLETION_RESERVE_SECONDS
                   if deadline_monotonic is not None else float("inf"))
    if deadline-time.monotonic() < 3:
        return []
    try:
        with connect_bounded_read() as connection, connection.cursor() as raw:
            raw.execute("set transaction read only")
            raw.execute("set local lock_timeout='1000ms'")
            cur = ReadBudgetCursor(raw, deadline, failure_kind="purpose_retry_read_deadline")
            cur.execute("""select review_json->'family_message_lifecycle'
                from public.sam_live_stock_conversation_review_events
                where event_source=%s
                  and review_json->'family_message_lifecycle'->>'card_mission_id'=%s
                order by created_at,review_event_id limit 3""", (EVENT_SOURCE, card_id))
            return [row[0] for row in cur.fetchall()] if time.monotonic() < deadline else []
    except Exception as exc:
        if isinstance(exc, (ValueError, RuntimeError, OSError)) or is_database_unavailable(exc):
            return []
        raise


def purpose_delivery_retry_authority(case, parsed, result, *, mission_id,
                                     deadline_monotonic=None):
    """One exact initial-send retry; no authority for ambiguity or card edits."""
    from modules.oom_sakkie.delivery_retry_authority import issue_delivery_retry_authority
    from modules.oom_sakkie.family_message_lifecycle import localize_recipient_result, _event
    from modules.oom_sakkie.family_presentation import envelope
    owner = current_purpose_owner()
    card_id = str(case.get("case_id") or "")
    if (not purpose_decision_binding(case) or not owner or not card_id
            or mission_id != f"{card_id}:G{case.get('generation')}"
            or parsed.get("telegram_user_id") != owner.telegram_user_id
            or parsed.get("telegram_chat_id") != owner.telegram_user_id
            or parsed.get("telegram_chat_type") != "private"
            or result.get("status") != "purpose_review_owner_attention"
            or result.get("result_digest") != case.get("evidence_digest")):
        return None
    localized = localize_recipient_result(parsed, result, "HERDMASTER")
    if localized.get("recipient_language_render_unrecognized") is True:
        return None
    text = envelope(localized.get("answer"))
    if not text:
        return None
    events = load_purpose_delivery_events(card_id, deadline_monotonic=deadline_monotonic)
    if len(events) != 2 or any(not isinstance(row, dict) for row in events):
        return None
    expected = _event(parsed, mission_id, card_id, "HERDMASTER",
                      "purpose_review_owner_attention", hashlib.sha256(text.encode()).hexdigest())
    attempt_id = card_id + "-DELIVERY-ATTEMPT"
    by_id = {row.get("event_id"): row for row in events}
    if set(by_id) != {attempt_id, attempt_id+"-CONTAINED"}:
        return None
    attempt, proof = by_id[attempt_id], by_id[attempt_id+"-CONTAINED"]
    if (attempt.get("state") != "delivery_attempted" or proof.get("state") != "contained"
            or proof.get("reason") != "telegram_delivery_definitely_not_sent"
            or any(row.get(key) != value for row in events for key, value in expected.items())
            or any(row.get(key) for row in events for key in
                   ("telegram_message_id", "provider_delivery_confirmed", "delivery_provider_timestamp"))):
        return None
    return issue_delivery_retry_authority(mission_id=mission_id, card_mission_id=card_id,
        text=text, proof_identity=proof["event_id"])
