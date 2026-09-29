"""Retained mortality confirmation on the existing claim and domain executor.

The genuine gateway callback first consumes the existing
claim receipt; this coordinator rechecks that durable receipt, locks the source,
and commits domain effects and source completion together. No send occurs here.
"""
from datetime import datetime, timezone

from modules.oom_sakkie import herdmaster_source_transaction as source_tx
from modules.oom_sakkie import retained_mortality_history as history
from modules.oom_sakkie.retained_mortality_presentation import _validate_source, validate_material


class DomainRefusal(Exception):
    def __init__(self, result, status):
        self.result, self.status = result, status


def confirm_retained_mortality(claimed, parsed, *, gateway_authority, connect_factory=None):
    from modules.oom_sakkie.gateway_authority import validates_gateway_owner_authority
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import retained_recipient_authorized
    from modules.oom_sakkie.protected_delivery_lifecycle import _connect
    from modules.oom_sakkie.protected_action_claims import complete_claim, protected_card_mission_id
    from modules.oom_sakkie.herdmaster_health_loss_runtime import (
        load_canonical_health_loss_evidence, _record_lifecycle_event, _mortality_completion_message)
    from modules.pig_weights.herdmaster_health_loss_recording import (
        confirm_health_loss_preview, _welfare_case_id)
    owner, chat = str(parsed.get('telegram_user_id') or ''), str(parsed.get('telegram_chat_id') or '')
    if (not validates_gateway_owner_authority(gateway_authority)
            or (gateway_authority.owner_user_id, gateway_authority.private_chat_id) != (owner, chat)
            or not owner or owner != chat or not retained_recipient_authorized(parsed)
            or claimed.get('success') is not True
            or claimed.get('status') not in {'protected_callback_claimed', 'protected_callback_recovered'}
            or claimed.get('action_kind') != 'mortality'):
        return {'success': False, 'status': 'retained_mortality_callback_authority_unproven',
            'writes_farm_data': False}, 403
    receipt = str(parsed.get('provider_message_id') or parsed.get('callback_query_id') or '')
    card = str(parsed.get('reply_to_message_id') or '')
    try:
        with (connect_factory or _connect)() as db, db.cursor() as cur:
            source_tx.begin(cur)
            # This first lookup is only a source-lock key. Nothing is authorized
            # until all-status chronology is reloaded after that lock.
            cur.execute("""select distinct review_json->'herdmaster_health_loss'->>'mission_id'
                from public.sam_live_stock_conversation_review_events where event_source=%s
                and review_json->'herdmaster_health_loss'->'retained_repreview'->>'claim_mission_id'=%s
                limit 2""", (source_tx.SOURCE, claimed['mission_id']))
            hints = cur.fetchall()
            source_tx.require(len(hints) == 1 and hints[0][0], 'retained_mortality_callback_source_not_unique')
            mission = hints[0][0]
            source_tx.lock_sources(cur, owner, chat, [mission])
            rows = source_tx.read_history(cur, [mission])
            current = source_tx.latest_for(rows, mission)
            source_tx.require(current is not None, 'retained_mortality_callback_source_missing')
            source_tx.require_current(rows, current)
            source_tx.require(current.get('status') in {'preview_ready', 'completed'},
                'retained_mortality_callback_source_terminal')
            prepared = next((row['record'] for row in rows if row['record'].get('mission_id') == mission
                and row['record'].get('status') == 'preview_ready'
                and (row['record'].get('retained_repreview') or {}).get('claim_mission_id') == claimed['mission_id']
                and (row['record'].get('retained_repreview') or {}).get('claim_preview_digest') == claimed['preview_digest']), None)
            source_tx.require(prepared is not None, 'retained_mortality_callback_preview_missing')
            cur.execute('select to_jsonb(c),clock_timestamp() from app_private.oom_protected_action_claims c where callback_token=%s for update',
                (claimed['callback_token'],))
            stored = cur.fetchone()
            source_tx.require(stored is not None, 'retained_mortality_callback_claim_missing')
            claim, observed = stored
            source_tx.require(all(history._time(row['created_at']) <= observed for row in rows),
                'retained_mortality_callback_source_future')
            source_tx.require(claim['status'] in {'executing', 'completed'} and claim['action_kind'] == 'mortality'
                and claim['owner_user_id'] == owner and claim['private_chat_id'] == chat
                and all(claim[key] == claimed[key] for key in
                    ('callback_token','mission_id','preview_digest','evidence_generation','preview_payload'))
                and bool(receipt) and claim['confirmation_provider_message_id'] == receipt
                and claim['confirmation_provider_timestamp'] is not None
                and history._time(claim['confirmation_provider_timestamp']) <= history._time(claim['expires_at'])
                and history._time(claim['confirmation_provider_timestamp']) <= observed
                and bool(card) and claim['preview_card_message_id'] == card
                and claim['delivery_state'] == 'delivery_confirmed'
                and bool(claim['delivery_attempt_id']) and claim['delivery_attempted_at'] is not None
                and claim['provider_accepted_at'] is not None and claim['delivery_confirmed_at'] is not None
                and claim['delivery_ambiguous_at'] is None
                and isinstance(claim['delivery_result'], dict) and claim['delivery_result'].get('success') is True
                and str(claim['delivery_result'].get('telegram_message_id') or '') == card,
                'retained_mortality_callback_receipt_unproven')
            _validate_source(prepared, claim)
            source_tx.require(all(current.get(key) == prepared.get(key) for key in
                ('mission_id','owner_user_id','chat_id','preview','operation_id','retained_repreview'))
                and not any(current.get(key) for key in ('invalidated_operation_ids','correction_digest',
                    'consumed_context_missions','superseded_duplicate_missions','superseded_duplicate_bindings')),
                'retained_mortality_callback_binding_changed')
            operation = claim['preview_payload']['operation_id']
            if claim['status'] == 'completed':
                # A concurrent callback may complete after this request claimed
                # its receipt. Recover only the exact durable winner, never an
                # unfinished source or a second owner's confirmation.
                winner = claim.get('result_payload') or {}
                prior = current.get('recording_result') or {}
                source_tx.require(current['status'] == 'completed'
                    and winner.get('success') is True and winner.get('status') == 'completed'
                    and winner.get('mission_id') == claim['mission_id']
                    and winner.get('source_mission_id') == mission
                    and winner.get('operation_id') == operation
                    and winner.get('pig_id') == claim['preview_payload']['identity']['pig_id']
                    and winner.get('lifecycle_event_id') == prior.get('lifecycle_event_id'),
                    'retained_mortality_completed_claim_unproven')
            cur.execute('select pg_advisory_xact_lock(hashtextextended(%s,0))', ('herdmaster-mortality:' + operation,))
            cur.execute('select pg_advisory_xact_lock(hashtextextended(%s,0))', (_welfare_case_id(prepared, operation),))
            reader = source_tx.TransactionReader(db)
            def fresh_material():
                evidence = load_canonical_health_loss_evidence(connect_factory=reader)
                validate_material(prepared, claim, evidence)
                return evidence
            # The existing executor checks exact completed-operation identity
            # before calling fresh_material; death must not defeat safe recovery.
            recorded, status = confirm_health_loss_preview(prepared, 'CONFIRM ' + operation,
                actor_id=owner, evidence_loader=fresh_material, connect_factory=reader)
            if recorded.get('success') is not True:
                raise DomainRefusal(recorded, status)
            identity = claim['preview_payload']['identity']
            recorded = {**recorded, 'pig_name': identity.get('name'), 'tag_number': identity.get('tag_number')}
            answer = _mortality_completion_message(recorded, prepared.get('output_language') or 'en')
            if current['status'] == 'completed':
                prior = current.get('recording_result') or {}
                source_tx.require(recorded.get('status') == 'mortality_lifecycle_replayed_withheld'
                    and prior.get('success') is True and prior.get('operation_id') == operation
                    and prior.get('pig_id') == recorded.get('pig_id')
                    and prior.get('lifecycle_event_id') == recorded.get('lifecycle_event_id'),
                    'retained_mortality_completed_source_unproven')
            else:
                completed = {**current, 'status': 'completed', 'event_phase': 'recording_completed',
                    'provider_message_id': receipt,
                    'provider_timestamp': history._time(claim['confirmation_provider_timestamp']).isoformat(),
                    'owner_text': answer, 'recording_result': recorded}
                saved = _record_lifecycle_event(completed,
                    expected_sources={mission: source_tx.digest(current)}, connect_factory=reader)
                if saved.get('success') is not True:
                    raise RuntimeError('retained_mortality_source_completion_failed')
            result = {**recorded, 'success': True, 'status': 'completed', 'answer': answer,
                'mission_id': claim['mission_id'], 'source_mission_id': mission,
                'card_mission_id': protected_card_mission_id(claim['mission_id'], claim['preview_digest']),
                'recipient_render_contract': 'specialist_structured_recipient_v1',
                'recipient_language': prepared.get('output_language') or 'en', 'records_audit_trace': True,
                'protected_actions_performed': bool(recorded.get('writes_farm_data')),
                'reply_markup': {'inline_keyboard': []}}
            # Complete the existing receipt in the same transaction as the
            # canonical domain event and source completion. A crash can expose
            # either all three or none, never a farm write awaiting another press.
            completion = complete_claim(claim['callback_token'], result, connect_factory=reader)
            canonical = completion.get('result')
            source_tx.require(isinstance(canonical, dict) and canonical.get('success') is True
                and canonical.get('status') == 'completed'
                and all(canonical.get(key) == result.get(key) for key in
                    ('operation_id','pig_id','lifecycle_event_id','mission_id','source_mission_id','card_mission_id')),
                'retained_mortality_completion_binding_unproven')
            result = dict(canonical)
            if completion.get('replayed') is True:
                result.update(answer='',suppress_owner_delivery=True,writes_farm_data=False,
                    protected_actions_performed=False,rows_created=0)
        return result, status
    except DomainRefusal as exc:
        # Even a lower layer that swallowed an exception or returned False after
        # a write cannot commit: this exception exited the outer transaction.
        return {**exc.result, 'writes_farm_data': False, 'rows_created': 0}, exc.status
    except source_tx.SourceConflict as exc:
        return {'success': False, 'status': str(exc), 'writes_farm_data': False}, 409
    except Exception as exc:
        # Keep the original executing receipt for exact callback recovery; never
        # consume a second confirmation or manufacture a successful completion.
        return {'success': False, 'status': 'retained_mortality_execution_recovery_pending',
            'writes_farm_data': False, 'recovery_required': True, 'error_type': type(exc).__name__}, 503
