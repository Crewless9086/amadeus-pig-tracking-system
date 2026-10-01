"""Read an exact delivered historical report into the existing birth dialogue.

Nothing here records a birth, renews a claim or impersonates the old reporter.
The original claim remains immutable. A genuine current owner reply can prepare
a new preview under the existing farrowing conversation transaction.
"""
from __future__ import annotations

from contextlib import nullcontext
from datetime import timedelta
import os

from modules.oom_sakkie.herdmaster_farrowing_conversation import (
    CONTEXT_SECONDS, FarrowingContextError, source_time,
)


def discover_retained_farrowing_review_context(parsed):
    """Read historical conversation data only; never prepare or create a claim."""
    return _load_context(parsed, lock=False)


def validate_retained_farrowing_review_context(parsed, *, connection):
    """Revalidate a selected fresh owner statement inside its existing lock.

    Discovery is never authority. Unrelated intents and confirmation commands
    cannot enter this path; the caller may only prepare a new protected preview.
    """
    semantic = parsed.get('semantic') or {}
    if (connection is None or semantic.get('intent') != 'record_farrowing_litter'
            or semantic.get('continuation') is not True
            or semantic.get('message_kind') not in {'observation','correction'}
            or semantic.get('needs_clarification') is True
            or float(semantic.get('confidence') or 0) < 0.8):
        return None
    return _load_context(parsed, connection=connection, lock=True)


def _load_context(parsed, *, connection=None, lock):
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import (
        FARROWING_REVIEW_FAMILY, current_farrowing_review_owner, read_retained_farrowing_reviews,
    )
    from modules.oom_sakkie.general_manager_worker import normalize_candidate
    owner = str(parsed.get('telegram_user_id') or '')
    chat = str(parsed.get('telegram_chat_id') or '')
    stamp = source_time(parsed.get('provider_timestamp'))
    if (not owner or owner != chat or owner != current_farrowing_review_owner()
            or not stamp or not str(parsed.get('provider_message_id') or '').isdigit()):
        return None
    context = (nullcontext(connection) if connection is not None else
        connect_bounded_rootline_postgres(database_url=os.environ.get('DATABASE_URL')))
    reply = str(parsed.get('reply_to_message_id') or '')
    with context as db, db.cursor() as cur:
        cur.execute("""select c.case_id,c.dedupe_key,c.specialist,c.status,c.generation,
              c.evidence_digest,c.evidence_refs,c.last_delivery_digest,
              f.receipt
            from app_private.oom_manager_cases c
            join lateral (
              select r.review_json->'family_message_lifecycle' as receipt, r.created_at
              from public.sam_live_stock_conversation_review_events r
              where r.event_source='oom_sakkie_family_message_lifecycle'
                and r.review_json->'family_message_lifecycle'->>'card_mission_id'=c.case_id
                and r.review_json->'family_message_lifecycle'->>'owner_user_id'=%s
                and r.review_json->'family_message_lifecycle'->>'chat_id'=%s
                and r.review_json->'family_message_lifecycle'->>'state' in ('delivered','updated')
              order by r.created_at desc,r.review_event_id desc limit 1
            ) f on true
            where c.specialist='HERDMASTER'
              and c.evidence_refs ? %s
              and c.status in ('open','waiting_reassessment','delegated')
              and c.last_delivery_digest=c.evidence_digest
              and f.created_at between %s and %s
              and f.receipt->>'specialist_identity'='HERDMASTER'
              and f.receipt->>'task_state'='retained_farrowing_owner_attention'
              and f.receipt->>'mission_id'=c.case_id || ':G' || c.generation::text
              and f.receipt->>'provider_message_id'='scheduled:' || c.case_id || ':G' || c.generation::text
              and coalesce(f.receipt->>'telegram_message_id','') <> ''
              and (%s='' or f.receipt->>'telegram_message_id'=%s)
            order by c.case_id limit 17""" + (' for update of c' if lock else ''),
            (owner, chat, 'manager_message_family:' + FARROWING_REVIEW_FAMILY,
             stamp - timedelta(seconds=CONTEXT_SECONDS), stamp, reply, reply))
        rows = cur.fetchall()
        if len(rows) > 16:
            raise FarrowingContextError('farrowing_context_ambiguous')
        eligible = []
        for case_id, key, specialist, status, generation, evidence_digest, refs, delivered_digest, receipt in rows:
            if not isinstance(receipt, dict):
                continue
            message_id = str(receipt.get('telegram_message_id') or '')
            delivered_at = source_time(receipt.get('delivery_provider_timestamp'))
            mission = f'{case_id}:G{generation}'
            if (status not in {'open','waiting_reassessment','delegated'}
                    or delivered_digest != evidence_digest or not message_id or not delivered_at
                    or not 0 <= (stamp-delivered_at).total_seconds() <= CONTEXT_SECONDS
                    or (reply and reply != message_id)
                    or receipt.get('specialist_identity') != 'HERDMASTER'
                    or receipt.get('task_state') != 'retained_farrowing_owner_attention'
                    or receipt.get('mission_id') != mission
                    or receipt.get('provider_message_id') != 'scheduled:' + mission):
                continue
            eligible.append((case_id, key, status, generation, evidence_digest, refs, receipt, delivered_at))
        if len(eligible) != 1:
            if len(eligible) > 1:
                raise FarrowingContextError('farrowing_context_ambiguous')
            return None
        case_id, key, status, generation, evidence_digest, refs, receipt, delivered_at = eligible[0]
        mission = key.removeprefix('herdmaster:expired-farrowing:')
        if not lock:
            # Discovery is two bounded SELECTs, independent of canonical history.
            # It tells the semantic reader what was shown, not what may be saved.
            cur.execute("""select case when octet_length(preview_payload::text)<=32768
                then to_jsonb(c)-'callback_token' end
                from app_private.oom_protected_action_claims c
                where action_kind='herdmaster_record_farrowing_litter' and mission_id=%s
                limit 2""", (mission,))
            originals = cur.fetchall()
            if len(originals) != 1 or not isinstance(originals[0][0], dict):
                return None
            original = originals[0][0]
            from modules.oom_sakkie.herdmaster_retained_recovery_runtime import _farrowing_digest
            if 'retained_farrowing_source:' + _farrowing_digest(original) not in refs:
                return None
            preview = original.get('preview_payload') or {}
            return {'context_id': 'HISTORICAL-REVIEW-' + case_id,
                'status': 'historical_unconfirmed_owner_review',
                'historical_review': True, 'confirmation_required': True,
                'facts': {'sow_ref': preview.get('sow_pig_id'),
                    'farrowing_date': preview.get('farrowing_date'), **(preview.get('counts') or {})},
                'sow_refs': [preview.get('sow_pig_id'), preview.get('sow_display_name')],
                'question': ('Is hierdie besonderhede korrek, of wat moet ek verander?'
                    if str(parsed.get('output_language') or '').startswith('af') else
                    'Are these details correct, or what should I change?'),
                'provider_timestamp': delivered_at.isoformat(),
                'context_authority': 'historical_data_only'}
        if lock:
            # Serialize with edits/cancellation of every claim for this source.
            # The principal's existing farrowing advisory lock serializes replies.
            cur.execute("""select callback_token from app_private.oom_protected_action_claims
                where action_kind='herdmaster_record_farrowing_litter'
                  and (mission_id=%s or mission_id like %s)
                order by callback_token for update""", (mission, mission + '-RECOVERY-%'))
            cur.fetchall()
        candidates = read_retained_farrowing_reviews(cur, stamp, [(key, refs, status)])
        if len(candidates) != 1:
            return None
        raw = candidates[0]
        current = normalize_candidate(raw, now=stamp)
        if (current['evidence_digest'] != evidence_digest
                or current.get('message_family') != FARROWING_REVIEW_FAMILY):
            return None
        display = raw['_farrowing_review']
        source_refs = sorted(ref for ref in refs if str(ref).startswith(
            ('mission:', 'provider_message:', 'sow:', 'retained_farrowing_source:', 'retained_farrowing_context:')))
        facts = {'sow_ref': display['sow_pig_id'], 'farrowing_date': display['date'], **display['counts']}
        return {'context_id': 'HISTORICAL-REVIEW-' + case_id,
            'facts': facts, 'sow_refs': display['sow_aliases'],
            'question': ('Is hierdie besonderhede korrek, of wat moet ek verander?'
                if str(parsed.get('output_language') or '').startswith('af') else
                'Are these details correct, or what should I change?'),
            'provider_message_id': receipt['provider_message_id'],
            'provider_timestamp': delivered_at.isoformat(),
            '_card_ids': [str(receipt['telegram_message_id'])],
            'historical_review_binding': {'case_id': case_id, 'generation': generation,
                'evidence_digest': evidence_digest, 'source_refs': source_refs,
                'reporting_principal': display['source_principal'],
                'source_mission': display['source_mission'], 'source_provider': display['source_provider'],
                'owner': owner, 'card_message_id': str(receipt['telegram_message_id']),
                'delivered_at': delivered_at.isoformat()},
            'status': 'historical_unconfirmed_owner_review', 'confirmation_required': True}
