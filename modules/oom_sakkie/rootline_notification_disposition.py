"""Read-only proof that the current ROOTLINE notification obligation is delivered.

This closes only the manager's delivery advisory, never irrigation, shutdown or
other ROOTLINE work. It grants no provider or hardware authority.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import re
from typing import Mapping
from zoneinfo import ZoneInfo

CONTRACT = 'rootline.manager_delivery_disposition.v1'
FAMILY = 'rootline_delivery_disposition'
ADVISORY_FAMILY = 'rootline_delivery_advisory'
KEY = 'rootline:current-plan'
_FIELDS = ('identity', 'event_id', 'owner_user_id', 'chat_id', 'operating_date',
           'material_digest', 'result_id', 'evidence_generation', 'delivery_state')


def current_recipient():
    """Reuse the existing family owner policy; an allowlist order is not identity."""
    from modules.oom_sakkie.family_access import OWNER_USER_ID_ENV, resolve_family_principal
    allowed_ids = [value.strip() for value in os.getenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "").split(",") if value.strip()]
    allowed = set(allowed_ids)
    owner = str(os.getenv(OWNER_USER_ID_ENV) or "").strip()
    if not owner and len(allowed) == 1:
        owner = next(iter(allowed))
    principal = resolve_family_principal({"telegram_user_id": owner,
        "telegram_chat_id": owner, "telegram_chat_type": "private"}, os.environ)
    scheduler_owner = str(os.getenv("ROOTLINE_REASSESSMENT_OWNER_USER_ID") or "").strip()
    # The unchanged generic manager sender still uses the first allowlist row.
    # A conflict is not permission to redirect either rail.
    return owner if (owner in allowed and principal.is_owner and allowed_ids[0] == owner
        and (not scheduler_owner or scheduler_owner == owner)) else None


def notification_material_refs(candidate, *, now):
    """Only this complete notification family has snapshot-independent material."""
    if (candidate.get("dedupe_key") != KEY or candidate.get("specialist") != "ROOTLINE"
            or candidate.get("message_family") != ADVISORY_FAMILY
            or candidate.get("terminal_state")
            or candidate.get("unknowns") != ["provider_confirmed_family_delivery_bound_to_current_plan"]):
        return None
    prefixes = ("event", "operating_date", "material", "result", "generation", "owner", "chat", "observed")
    refs = candidate.get("evidence_refs")
    if not isinstance(refs, (list, tuple)):
        return None
    facts = {}
    for ref in refs:
        if ref == "manager_message_family:" + ADVISORY_FAMILY:
            continue
        if not isinstance(ref, str) or ":" not in ref:
            return None
        key, value = ref.split(":", 1)
        if key not in prefixes or key in facts or not _text(value) or value == "missing":
            return None
        facts[key] = value
    if (set(facts) != set(prefixes) or not re.fullmatch(r"[a-f0-9]{64}", facts["material"])
            or facts["owner"] != facts["chat"] or facts["owner"] != current_recipient()
            or facts["operating_date"] != now.astimezone(ZoneInfo("Africa/Johannesburg")).date().isoformat()
            or not _time(facts["observed"]) or _time(facts["observed"]) > now):
        return None
    return [ref for ref in refs if not ref.startswith(("event:", "result:", "generation:"))]


def _text(value):
    return value if isinstance(value, str) and value.strip() == value and 0 < len(value) <= 180 else None


def _time(value):
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def _packet(row, state, now):
    if not isinstance(row, (tuple, list)) or len(row) != 3 or not isinstance(row[2], Mapping):
        return None
    event_id, recorded, payload = row
    at = _time(recorded)
    if not at or at > now or not all(_text(payload.get(key)) for key in _FIELDS):
        return None
    suffix = '-RECORD_OBSERVATION' if state == 'observation_only' else '-MARK_DELIVERED'
    if (not re.fullmatch(r'[a-f0-9]{64}', payload['material_digest'])
            or payload['delivery_state'] != state or event_id != payload['event_id']
            or event_id != payload['identity'] + suffix
            or payload['owner_user_id'] != payload['chat_id']):
        return None
    result = {key: payload[key] for key in _FIELDS}
    result['recorded_at'] = at.isoformat()
    if state == 'delivered':
        provider = _text(payload.get('provider_message_id'))
        timestamp = payload.get('provider_timestamp') or ''
        if not provider or (timestamp and (not _time(timestamp) or _time(timestamp) > now)):
            return None
        result.update(provider_message_id=provider, provider_timestamp=timestamp)
    return result


def completion_candidate(observation_row, delivery_row, retained_row, *, now):
    now = _time(now)
    if now is None:
        return None
    observation = _packet(observation_row, 'observation_only', now)
    delivery = _packet(delivery_row, 'delivered', now)
    if (not observation or not delivery
            or current_recipient() != observation['owner_user_id']
            or observation['operating_date'] != now.astimezone(ZoneInfo('Africa/Johannesburg')).date().isoformat()
            or any(observation[key] != delivery[key] for key in
                   ('owner_user_id', 'chat_id', 'operating_date', 'material_digest'))):
        return None
    # The owning lifecycle intentionally suppresses fresher result/generation
    # identities when owner/chat/date/material already have a delivered receipt.
    retained = None
    if retained_row is not None:
        if (not isinstance(retained_row, (tuple, list)) or len(retained_row) != 6
                or retained_row[1:3] not in ((KEY, 'ROOTLINE'), [KEY, 'ROOTLINE'])
                or not isinstance(retained_row[3], int) or isinstance(retained_row[3], bool)
                or retained_row[3] < 1 or not _text(retained_row[0]) or not _text(retained_row[4])
                or not isinstance(retained_row[5], list)
                or len(retained_row[5]) > 20 or not all(_text(v) for v in retained_row[5])):
            return None
        retained = dict(zip(('case_id', 'dedupe_key', 'specialist', 'generation',
                             'evidence_digest', 'evidence_refs'), retained_row))
        for prefix, key in (('owner:', 'owner_user_id'), ('chat:', 'chat_id')):
            values = [ref[len(prefix):] for ref in retained['evidence_refs'] if ref.startswith(prefix)]
            if values and values != [observation[key]]:
                return None
    proof = {'contract': CONTRACT, 'observation': observation, 'delivery': delivery, 'retained': retained}
    refs = ['rootline_delivery:' + delivery['event_id'],
            'rootline_delivery_identity:' + delivery['identity'],
            'rootline_provider_message:' + delivery['provider_message_id'],
            'operating_date:' + delivery['operating_date'], 'material:' + delivery['material_digest'],
            'owner:' + delivery['owner_user_id'], 'chat:' + delivery['chat_id'],
            'delivery_result:' + delivery['result_id'], 'delivery_generation:' + delivery['evidence_generation'],
            'observed:' + observation['recorded_at']]
    return {'dedupe_key': KEY, 'specialist': 'ROOTLINE', 'urgency': 'urgent',
        'evidence_refs': refs, 'unknowns': [], 'terminal_state': 'completed', 'message_family': FAMILY,
        'summary': 'The current ROOTLINE plan notification has a verified canonical delivery receipt.',
        'next_action': 'Retain the exact notification receipt and continue normal ROOTLINE reassessment. No hardware completion is implied.',
        'next_reassessment_at': (now + timedelta(minutes=5)).isoformat(),
        '_rootline_delivery_proof': proof}


def validate_completion(candidate, *, now):
    proof = candidate.get('_rootline_delivery_proof')
    if not isinstance(proof, dict) or proof.get('contract') != CONTRACT:
        return None
    observation, delivery, retained = (proof.get(key) for key in ('observation', 'delivery', 'retained'))
    if not isinstance(observation, dict) or not isinstance(delivery, dict):
        return None
    retained_row = None
    if retained is not None:
        if not isinstance(retained, dict):
            return None
        retained_row = tuple(retained.get(key) for key in ('case_id','dedupe_key','specialist',
            'generation','evidence_digest','evidence_refs'))
    expected = completion_candidate((observation.get('event_id'), observation.get('recorded_at'), observation),
        (delivery.get('event_id'), delivery.get('recorded_at'), delivery), retained_row, now=now)
    if not expected or any(candidate.get(key) != expected[key] for key in
            ('dedupe_key','specialist','urgency','unknowns','terminal_state','message_family','summary','next_action')):
        return None
    refs = [ref for ref in candidate.get('evidence_refs') or [] if ref != 'manager_message_family:' + FAMILY]
    if sorted(refs) != sorted(expected['evidence_refs']):
        return None
    return expected['_rootline_delivery_proof'] if proof == expected['_rootline_delivery_proof'] else None


def prior_matches(proof, prior):
    """Fence the exact retained projection observed by the source read."""
    if current_recipient() != proof['observation']['owner_user_id']:
        return False
    expected = proof['retained']
    if prior is None:
        return expected is None
    return bool(expected and len(prior) > 6 and expected['case_id'] == prior[6]
        and expected['generation'] == prior[1] and expected['evidence_digest'] == prior[0]
        and expected['evidence_refs'] == prior[5])
