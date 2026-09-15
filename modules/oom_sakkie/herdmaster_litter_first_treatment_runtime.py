"""Actual first-treatment reports on the existing conversation and protected claims rails."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from html import escape
import json
import logging

from modules.oom_sakkie.gateway_authority import validates_gateway_owner_authority
from modules.oom_sakkie.protected_action_claims import (
    build_buttons, canonical_preview_digest, create_claim, protected_card_mission_id,
    resolve_natural_confirmation,
)
from modules.oom_sakkie.herdmaster_litter_weaning_runtime import (
    _connect, _service_factory, _time, _digest, _eligible_context, _source_order, _retained_context_rows,
    _actual_date as _shared_actual_date, WeaningClarification, ENGLISH as SHARED_ENGLISH,
)
from modules.pig_weights import farm_supabase_read_service as reader
from modules.pig_weights.herdmaster_litter_first_treatment_intake import (
    ACTION_KIND, prepare_litter_first_treatment_preview,
)
from modules.pig_weights.pig_weights_service import record_litter_newborn_health

EVENT_SOURCE = 'oom_sakkie_litter_first_treatment'
CONTEXT_KEY = 'litter_first_treatment'
LOGGER = logging.getLogger(__name__)
ENGLISH = {**SHARED_ENGLISH,
    'Jou eie rekening het nie behandelingstoestemming nie.': 'Your own account does not have treatment permission.',
    'Ek is onseker oor die behandelingsverslag. Gee die werpsel en die werklike behandelingsfeite.': 'The treatment report is unclear. Give the litter and actual treatment facts.',
    'Antwoord op die presiese behandelingsvoorskou wat jy wil bevestig.': 'Reply to the exact treatment preview you want to confirm.',
    'Ek kort die werpsel en die werklike behandelingsfeite.': 'I need the litter and actual treatment facts.',
    'Hierdie voorskou is nie meer aktief nie. Gebruik die jongste behandelingskaart.': 'This preview is no longer active. Use the latest treatment card.',
    'Die vorige behandelingsgesprek is nie meer duidelik nie. Gee weer die werpsel en behandelingsfeite.': 'The previous treatment context is no longer clear. Give the litter and treatment facts again.',
    "Hierdie behandelingsgesprek is gekanselleer. Begin met 'n nuwe verslag as jy weer wil voortgaan.": 'This treatment conversation was cancelled. Start a new report if you want to continue.',
    'Daar is reeds nuwer behandelingsfeite. Gebruik die jongste voorskou.': 'Newer treatment facts have arrived. Use the latest preview.',
    'Verduidelik asseblief die onseker behandelingsfeit.': 'Please clarify the uncertain treatment fact.',
    'Ek kon die behandelingsgesprek nie veilig behou nie. Niks is bevestig nie.': 'The treatment conversation could not be safely retained. Nothing was confirmed.',
    'Op watter datum het jy hulle werklik behandel?': 'On what date did you actually treat them?',
    'Die bevestiging stem nie met jou presiese behandelingsvoorskou ooreen nie.': 'The confirmation does not match your exact treatment preview.',
    'Die behandelingsinskrywing is nog nie bewys nie. Herstel hierdie presiese bevestiging voordat jy weer probeer.': 'The treatment result is not yet proven. Recover this exact confirmation before trying again.',
}


class TreatmentClarification(ValueError):
    pass


def _answer(status, text, *, success=False, language='af', **extra):
    af = str(language).startswith('af')
    return {'handled': True, 'success': success, 'status': status, 'specialist': 'HERDMASTER',
        'answer': ('<b>Eerste behandeling</b>\n' if af else '<b>First treatment</b>\n') + (text if af else ENGLISH.get(text, text)),
        'recipient_render_contract': 'specialist_structured_recipient_v1',
        'recipient_language': 'af' if af else 'en', 'writes_farm_data': False, **extra}


def _actual_date(raw, stamp):
    try:
        return _shared_actual_date(raw, stamp)
    except WeaningClarification:
        raise TreatmentClarification('Op watter datum het jy hulle werklik behandel?') from None


def _context_rows(cursor, actor):
    return _retained_context_rows(cursor, actor, EVENT_SOURCE, CONTEXT_KEY, ACTION_KIND)


def load_first_treatment_context(parsed, *, connect_factory=None):
    actor = str(parsed.get('telegram_user_id') or '')
    if not actor or actor != str(parsed.get('telegram_chat_id') or ''):
        return None
    try:
        with _connect(connect_factory) as db:
            db.read_only = True
            with db.cursor() as cursor:
                prior = _eligible_context(_context_rows(cursor, actor), parsed)
        if prior:
            if prior.get('_cancelled'):
                return {'status': 'first_treatment_context_cancelled'}
            return {key: prior.get(key) for key in ('context_id', 'facts', 'provider_timestamp', 'question')}
    except Exception:
        return None
    return None


def load_canonical_litter_treatment_evidence(*, connect_factory=None):
    factory = _service_factory(connect_factory)
    with _connect(connect_factory) as db:
        db.read_only = True
        with db.cursor() as cursor:
            cursor.execute("select pig_id,tag_number,pig_name as name from public.current_canonical_pigs")
            animals = [dict(zip(('pig_id','tag_number','name'), row)) for row in cursor.fetchall()]
            cursor.execute("select litter_id from public.current_canonical_litters where lower(litter_status)='active'")
            ids = [row[0] for row in cursor.fetchall()]
    litters = []
    for litter_id in ids:
        detail = reader.get_litter_detail(litter_id, connect_factory=factory)
        if detail:
            litters.append({**detail, 'sow_pig_id': detail.get('mother_pig_id'), 'detail': detail})
    return {'evidence_generation': _digest(litters), 'animals': animals,
        'litters': litters, 'products': reader.get_products(connect_factory=factory)}


def _validation_question(result, language='af'):
    af = language == 'af'
    status, missing = result.get('status', ''), result.get('missing') or []
    questions = {
        'sow_ref': ('Watter sog bedoel jy? Gee haar unieke oornommer of ID.', 'Which sow do you mean? Give her unique tag or ID.'),
        'litter_ref': ('Watter werpsel bedoel jy? Gee die unieke werpsel-ID of sog se ID.', 'Which litter do you mean? Give its unique ID or the sow ID.'),
        'action_date': ('Op watter datum het jy hulle werklik behandel? Die datum moet vanaf geboorte tot vandag wees.', 'On what date did you actually treat them? It must be between birth and today.'),
        'product': ('Watter presiese produk het jy gebruik? Gee die naam of produk-ID.', 'Which exact product did you use? Give its name or product ID.'),
        'dose': ('Wat was die werklike dosis per varkie, met die eenheid?', 'What was the actual dose per piglet, including the unit?'),
        'dose_unit': ('Watter eenheid hoort by die dosis wat jy toegedien het?', 'What unit belongs to the dose you administered?'),
        'route': ('Watter toedieningsroete het jy werklik gebruik?', 'What administration route did you actually use?'),
        'batch_lot_number': ('Wat was die produk se lotnommer?', 'What was the product batch number?'),
        'total_count': ('Hoeveel huidige varkies het jy behandel? Die getal moet met die huidige werpsel ooreenstem.', 'How many current piglets did you treat? The count must match the current litter.'),
        'male_count': ('Hoeveel manlike en vroulike varkies het jy getel? Albei getalle moet met die huidige werpsel ooreenstem.', 'How many male and female piglets did you count? Both counts must match the current litter.'),
        'earmarked': ('Het jy die varkies gemerk? Die bestaande oormerkgeskiedenis moet behoue bly.', 'Did you earmark the piglets? Existing earmark history must remain accurate.'),
    }
    if missing:
        pair = questions.get(missing[0], questions['total_count'])
        return pair[0 if af else 1]
    if 'already' in status:
        return ('Hierdie werpsel het reeds behandelings-, oorslaan- of speenbewys. Lees en kontroleer eers die bestaande rekord.' if af else
            'This litter already has treatment, skip or weaning evidence. Read and check the existing record first.')
    return ('Die huidige werpselrekords stem nie met die behandelingsverslag ooreen nie. Kontroleer die werpsel en huidige varkies.' if af else
        'The current litter records do not match the treatment report. Check the litter and current piglets.')


def _prepare(facts, actor, stamp, language, *, connect_factory=None):
    evidence = load_canonical_litter_treatment_evidence(connect_factory=connect_factory)
    if facts.get('action_date'):
        facts['action_date'] = _actual_date(facts['action_date'], stamp)
    prepared = prepare_litter_first_treatment_preview({'authenticated': True,
        'authenticated_principal_id': actor, 'provider_message_id': 'conversation_preview',
        'litter_first_treatment': facts}, evidence)
    if not prepared.get('success'):
        raise TreatmentClarification(_validation_question(prepared, language))
    preview = prepared['preview']
    p = {key: facts[key] for key in ('male_count','female_count','total_count','dose','dose_unit','route','batch_lot_number','notes') if key in facts}
    p.update(action_date_value=preview['action_date'], changed_by=actor, dry_run=True, earmarked=facts.get('earmarked'))
    for key in ('antiparasitic_product_ref','deworming_product_ref','vaccination_product_ref'):
        if facts.get(key):
            product = next(row for row in evidence['products'] if str(facts[key]).casefold() in
                (str(row['product_id']).casefold(), str(row['product_name']).casefold()))
            p[key.replace('_ref','_id')] = product['product_id']
    return preview['litter_id'], p


def _preview_answer(preview, language='af'):
    af = language == 'af'
    lines = [escape(str(preview.get('sow_name') or preview['sow_pig_id'])) + ' (' + escape(preview['sow_pig_id']) + ')',
        ('Werpsel: ' if af else 'Litter: ') + escape(preview['litter_id']),
        ('Werklik behandel: ' if af else 'Actually treated: ') + preview['action_date'],
        str(preview['total_count']) + (' huidige varkies: ' if af else ' current piglets: ') + ', '.join(map(escape, preview['pig_ids'])),
        ', '.join(escape(row['product_name']) + ' (' + escape(row['product_id']) + ')' for row in preview['products']),
        escape(f"{preview['dose']} {preview['dose_unit']}, {preview['route']}, lot {preview['batch_lot_number']}")]
    if preview.get('earmarked') is not None:
        lines.append(('Oormerke aangebring: ' + ('ja' if preview['earmarked'] else 'nee')) if af else 'Earmarked: ' + ('yes' if preview['earmarked'] else 'no'))
    if preview.get('male_count') is not None:
        lines.append(f"Opgegewe telling: {preview['male_count']} manlik, {preview['female_count']} vroulik. Individuele geslagte bly soos aangeteken." if af else
            f"Reported tally: {preview['male_count']} male, {preview['female_count']} female. Individual sexes remain as recorded.")
    if preview.get('notes'):
        lines.append(('Nota: ' if af else 'Note: ') + escape(preview['notes']))
    lines.append('Bevestig hierdie presiese eerste behandeling om dit een keer te stoor.' if af else 'Confirm this exact first treatment to save it once.')
    return '\n'.join(lines)


def handle_litter_first_treatment_message(parsed, authority, *, connect_factory=None):
    language = 'af' if str(parsed.get('output_language') or 'en').startswith('af') else 'en'
    def answer(status, text, **kwargs):
        return _answer(status, text, language=language, **kwargs)
    semantic = parsed.get('semantic') or {}
    if semantic.get('intent') != 'record_litter_first_treatment' or semantic.get('domain') != 'herd_management':
        return {'handled': False}, 200
    actor, chat = str(parsed.get('telegram_user_id') or ''), str(parsed.get('telegram_chat_id') or '')
    if (not validates_gateway_owner_authority(authority) or not actor or actor != chat
            or parsed.get('telegram_chat_type') != 'private'
            or authority.owner_user_id != actor or authority.private_chat_id != chat
            or (getattr(authority, 'principal_role', '') != 'owner' and 'treatment' not in authority.capabilities)):
        return answer('first_treatment_authority_required', 'Jou eie rekening het nie behandelingstoestemming nie.'), 403
    stamp = _time(parsed.get('provider_timestamp'))
    provider = str(parsed.get('provider_message_id') or '')
    if not stamp or not provider or not -30 <= (datetime.now(timezone.utc) - stamp).total_seconds() <= 6 * 3600:
        return answer('first_treatment_provider_identity_required', 'Hierdie boodskap se tyd of identiteit kon nie bevestig word nie.'), 409
    if semantic.get('message_kind') in ('question', 'request', 'general'):
        return {'handled': False}, 200
    if float(semantic.get('confidence') or 0) < 0.8:
        return answer('first_treatment_meaning_uncertain', 'Ek is onseker oor die behandelingsverslag. Gee die werpsel en die werklike behandelingsfeite.'), 409
    if semantic.get('message_kind') == 'confirmation':
        if semantic.get('needs_clarification') or not semantic.get('continuation') or semantic.get('litter_first_treatment'):
            return answer('first_treatment_confirmation_unclear', 'Bevestig die presiese voorskou of stuur die veranderde feite.'), 409
        # Recover this provider receipt before considering a newer active card.
        # This also covers a crash after farm commit but before claim completion.
        with _connect(connect_factory) as db:
            row = db.execute("""select callback_token,preview_payload,preview_card_message_id
                from app_private.oom_protected_action_claims where owner_user_id=%s
                and private_chat_id=%s and action_kind=%s and status in ('executing','completed')
                and confirmation_provider_message_id=%s""", (actor, chat, ACTION_KIND, provider)).fetchall()
        active = dict(zip(('callback_token', 'preview_payload', 'preview_card_message_id'), row[0])) if len(row) == 1 else None
        if not row:
            active = resolve_natural_confirmation(owner_user_id=actor, private_chat_id=chat,
                reply_to_message_id=str(parsed.get('reply_to_message_id') or ''), connect_factory=connect_factory)
        if not active or (active['preview_payload'] or {}).get('contract_version') != ACTION_KIND:
            return answer('first_treatment_confirmation_not_unambiguous', 'Antwoord op die presiese behandelingsvoorskou wat jy wil bevestig.'), 409
        from modules.oom_sakkie.protected_action_runtime import handle_protected_action_input
        result, code = handle_protected_action_input(parsed, authority,
            callback_data='oompa:' + active['callback_token'] + ':confirm', connect_factory=connect_factory,
            first_treatment_semantic_confirmation=True)
        if code == 409 and result.get('status') in {'first_treatment_confirmation_not_unambiguous',
                'protected_callback_card_mismatch', 'protected_callback_card_unbound', 'protected_callback_stale'}:
            return answer(result['status'], 'Antwoord op die presiese behandelingsvoorskou wat jy wil bevestig.'), code
        return result, code
    supplied = semantic.get('litter_first_treatment')
    if not isinstance(supplied, dict):
        return answer('first_treatment_typed_facts_required', 'Ek kort die werpsel en die werklike behandelingsfeite.'), 409
    try:
        with _connect(connect_factory) as db:
            with db.cursor() as cursor:
                cursor.execute("set local statement_timeout='15s'")
                cursor.execute('select pg_advisory_xact_lock(hashtextextended(%s,0))', (EVENT_SOURCE + ':' + actor,))
                rows = _context_rows(cursor, actor)
                identity = {'provider_message_id': provider, 'provider_timestamp': stamp.isoformat(),
                    'text_digest': _digest(str(parsed.get('text') or ''))}
                replay = next((row for row in rows if row['provider_message_id'] == provider), None)
                if replay:
                    if any(replay.get(key) != value for key, value in identity.items()):
                        return answer('first_treatment_provider_replay_conflict', 'Hierdie boodskap se herhaling verskil. Niks is gestoor nie.'), 409
                    token = replay['outcome'].get('callback_token')
                    if token:
                        cursor.execute("""select status,preview_payload,preview_digest,mission_id from
                            app_private.oom_protected_action_claims where callback_token=%s""", (token,))
                        claim = cursor.fetchone()
                        if claim and claim[0] == 'completed':
                            return execute_claimed_litter_first_treatment({'preview_payload': claim[1],
                                'preview_digest': claim[2], 'mission_id': claim[3]}, parsed, connect_factory=connect_factory)
                        if not claim or claim[0] != 'active':
                            return answer('first_treatment_preview_superseded', 'Hierdie voorskou is nie meer aktief nie. Gebruik die jongste behandelingskaart.'), 409
                    return replay['outcome'], replay['http_status']
                if rows and any(_source_order(row) > _source_order(parsed) for row in rows):
                    return answer('first_treatment_out_of_order', 'Daar is reeds nuwer behandelingsfeite. Gebruik die jongste voorskou.'), 409
                prior = _eligible_context(rows, parsed, supplied) if semantic.get('continuation') else None
                if prior and prior.get('_cancelled'):
                    return answer('first_treatment_context_cancelled', "Hierdie behandelingsgesprek is gekanselleer. Begin met 'n nuwe verslag as jy weer wil voortgaan."), 409
                if semantic.get('continuation') and not prior:
                    return answer('first_treatment_context_not_current', 'Die vorige behandelingsgesprek is nie meer duidelik nie. Gee weer die werpsel en behandelingsfeite.'), 409
                facts = {**(prior['facts'] if prior else {}), **supplied}
                context_id = prior['context_id'] if prior else 'OOM-TREAT-' + _digest(actor + ':' + provider)[:24].upper()
                # Retire an old confirmation before accepting corrections, even
                # if the corrected facts still need clarification.
                cursor.execute("""select status from app_private.oom_protected_action_claims
                    where mission_id=%s and action_kind=%s for update""", (context_id, ACTION_KIND))
                statuses = {row[0] for row in cursor.fetchall()}
                if 'cancelled' in statuses:
                    return answer('first_treatment_context_cancelled', "Hierdie behandelingsgesprek is gekanselleer. Begin met 'n nuwe verslag as jy weer wil voortgaan."), 409
                if statuses & {'executing', 'completed'}:
                    return answer('first_treatment_prior_operation_requires_readback', 'Die vorige bevestiging word reeds verwerk of is gestoor. Lees eers daardie uitslag terug.'), 409
                cursor.execute("""update app_private.oom_protected_action_claims set status='changed'
                    where mission_id=%s and action_kind=%s and status='active'""", (context_id, ACTION_KIND))
                try:
                    if supplied.get('action_date'):
                        facts['action_date'] = _actual_date(supplied['action_date'], stamp)
                    if semantic.get('needs_clarification'):
                        raise TreatmentClarification('Verduidelik asseblief die onseker behandelingsfeit.')
                    litter_id, p = _prepare(facts, actor, stamp, language, connect_factory=connect_factory)
                    preview, code = record_litter_newborn_health(litter_id, **p,
                        connect_factory=_service_factory(connect_factory), require_supabase=True)
                    if code != 200:
                        raise TreatmentClarification(_validation_question(preview, language))
                    bound = {'contract_version': ACTION_KIND, 'litter_id': litter_id, 'payload': p,
                        'confirmation_binding': preview['confirmation_binding'], 'facts': facts,
                        'provider_timestamp': stamp.isoformat(), 'provider_message_id': provider}
                    @contextmanager
                    def borrowed():
                        yield db
                    claim = create_claim(action_kind=ACTION_KIND, owner_user_id=actor, private_chat_id=chat,
                        mission_id=context_id, provider_message_id=provider, evidence_generation=preview['preview_digest'],
                        preview_payload=bound, connect_factory=borrowed, ttl_minutes=15)
                    result = answer('litter_first_treatment_preview_ready', _preview_answer(preview['preview'], language), success=True,
                        mission_id=context_id, card_mission_id=protected_card_mission_id(context_id, claim['preview_digest']),
                        callback_token=claim['callback_token'], preview_digest=claim['preview_digest'], action_kind=ACTION_KIND,
                        reply_markup=build_buttons(claim['callback_token'], language=language), retained_facts=facts, question_count=0)
                    code = 200
                except TreatmentClarification as exc:
                    result = answer('litter_first_treatment_clarification_required', str(exc), success=True,
                        question_count=1, clarification_question=(str(exc) if language == 'af' else ENGLISH.get(str(exc), str(exc))), retained_facts=facts,
                        mission_id=context_id, card_mission_id=context_id)
                    code = 200
                receipt = {**identity, 'context_id': context_id, 'facts': facts,
                    'question': result.get('clarification_question', ''), 'outcome': result, 'http_status': code}
                cursor.execute("""insert into public.sam_live_stock_conversation_review_events(
                    review_event_id,chatwoot_conversation_id,chatwoot_message_id,channel,source_agent,event_source,review_json)
                    values(%s,%s,%s,'telegram','HERDMASTER',%s,%s::jsonb)""",
                    ('TREAT-TURN-' + _digest(actor + ':' + provider), actor, provider, EVENT_SOURCE,
                     json.dumps({CONTEXT_KEY: receipt}, default=str)))
        return result, code
    except Exception:
        LOGGER.exception('First-treatment conversation receipt failed for actor %s', actor)
        return answer('first_treatment_context_store_unavailable', 'Ek kon die behandelingsgesprek nie veilig behou nie. Niks is bevestig nie.'), 503


def execute_claimed_litter_first_treatment(claimed, parsed, *, connect_factory=None):
    language = 'af' if str(parsed.get('output_language') or 'en').startswith('af') else 'en'
    bound = claimed.get('preview_payload') or {}
    if (bound.get('contract_version') != ACTION_KIND
            or canonical_preview_digest(ACTION_KIND, bound) != claimed.get('preview_digest')
            or bound.get('payload', {}).get('changed_by') != str(parsed.get('telegram_user_id') or '')):
        return _answer('first_treatment_claim_binding_mismatch', 'Die bevestiging stem nie met jou presiese behandelingsvoorskou ooreen nie.', language=language), 409
    result, code = record_litter_newborn_health(bound['litter_id'], **{**bound['payload'], 'dry_run': False,
        'confirmed': True, 'confirmation_binding': bound['confirmation_binding']},
        require_supabase=True, connect_factory=_service_factory(connect_factory))
    if not result.get('success'):
        return {**_answer(result['status'], 'Die behandelingsinskrywing is nog nie bewys nie. Herstel hierdie presiese bevestiging voordat jy weer probeer.', language=language), **result}, code
    with _connect(connect_factory) as db:
        confirmation = db.execute("""select confirmation_provider_message_id,confirmation_provider_timestamp
            from app_private.oom_protected_action_claims where mission_id=%s and preview_digest=%s
            and action_kind=%s""", (claimed['mission_id'], claimed['preview_digest'], ACTION_KIND)).fetchone()
    delivery_binding = {}
    if confirmation and str(confirmation[0]) == str(parsed.get('provider_message_id')):
        delivery_binding = {'actor_id': str(parsed['telegram_user_id']),
            'provider_message_id': str(confirmation[0]), 'provider_timestamp': confirmation[1].isoformat()}
    text = ('Eerste behandeling is gestoor en teruggelees.\n' if language == 'af' else 'First treatment saved and read back.\n')
    text += _preview_answer(bound['confirmation_binding']['packet'], language).rsplit('\n', 1)[0]
    return {**result, **_answer(result['status'], text, success=True, language=language,
        mission_id=claimed['mission_id'], card_mission_id=protected_card_mission_id(claimed['mission_id'], claimed['preview_digest']),
        first_treatment_delivery_binding=delivery_binding, reply_markup={'inline_keyboard': []},
        owner_visible_completion_policy='verified_edit_or_new_message', writes_farm_data=not result['replay_withheld'])}, code


def first_treatment_delivery_input(parsed, result):
    binding = result.get('first_treatment_delivery_binding') or {}
    if (binding.get('actor_id') == str(parsed.get('telegram_user_id')) == str(parsed.get('telegram_chat_id'))
            and binding.get('provider_message_id') == str(parsed.get('provider_message_id'))
            and _time(binding.get('provider_timestamp'))):
        return {**parsed, 'provider_timestamp': binding['provider_timestamp'],
            'text': str(parsed.get('callback_data') or parsed.get('text') or '')}
    return parsed
