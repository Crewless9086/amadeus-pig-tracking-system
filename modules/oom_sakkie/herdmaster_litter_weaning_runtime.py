"""Typed weaning adapter on the existing conversation, claims and farm records."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from html import escape
import hashlib
import json
import logging
import os
from zoneinfo import ZoneInfo

from modules.oom_sakkie.gateway_authority import validates_gateway_owner_authority
from modules.oom_sakkie.protected_action_claims import (
    build_buttons, canonical_preview_digest, create_claim, protected_card_mission_id,
    resolve_natural_confirmation,
)
from modules.pig_weights import farm_supabase_read_service as reader
from modules.pig_weights.pig_weights_service import process_litter_weaning_day

ACTION_KIND = 'herdmaster_record_litter_weaning'
EVENT_SOURCE = 'oom_sakkie_litter_weaning'
CONTEXT_KEY = 'litter_weaning'
LOGGER = logging.getLogger(__name__)


def _service_factory(factory):
    return (lambda _url: factory()) if factory else None


def _connect(factory=None):
    if factory:
        return factory()
    import psycopg
    return psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=5)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def _time(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def _context_rows(cursor, actor):
    return _retained_context_rows(cursor, actor, EVENT_SOURCE, CONTEXT_KEY, ACTION_KIND)


def _retained_context_rows(cursor, actor, event_source, context_key, action_kind):
    """Read the existing claim/card state with the retained private facts."""
    cursor.execute("""select review_json->%s
        from public.sam_live_stock_conversation_review_events
        where event_source=%s and chatwoot_conversation_id=%s
        order by created_at desc,review_event_id desc limit 100""", (context_key, event_source, actor))
    rows = [dict(row[0]) for row in cursor.fetchall() if isinstance(row[0], dict)]
    tokens = list({str((row.get('outcome') or {}).get('callback_token')) for row in rows
                   if (row.get('outcome') or {}).get('callback_token')})
    claims = {}
    if tokens:
        cursor.execute("""select callback_token,status,preview_card_message_id
            from app_private.oom_protected_action_claims where callback_token=any(%s)
            and action_kind=%s and owner_user_id=%s and private_chat_id=%s""",
            (tokens, action_kind, actor, actor))
        claims = {str(row[0]): row[1:] for row in cursor.fetchall()}
    cards = list({str((row.get('outcome') or {}).get('card_mission_id') or row.get('context_id'))
                  for row in rows if row.get('context_id')})
    bindings = []
    if cards:
        cursor.execute("""select review_json->'family_message_lifecycle'
            from public.sam_live_stock_conversation_review_events
            where event_source='oom_sakkie_family_message_lifecycle'
            and chatwoot_conversation_id=any(%s)
            and review_json->'family_message_lifecycle'->>'owner_user_id'=%s
            and review_json->'family_message_lifecycle'->>'chat_id'=%s
            and review_json->'family_message_lifecycle'->>'telegram_message_id' is not null
            order by created_at desc,review_event_id desc limit 200""", (cards, actor, actor))
        bindings = [row[0] for row in cursor.fetchall() if isinstance(row[0], dict)]
    for row in rows:
        outcome = row.get('outcome') or {}
        claim = claims.get(str(outcome.get('callback_token') or ''))
        row['_claim_status'] = claim[0] if claim else ''
        card = str(outcome.get('card_mission_id') or row.get('context_id') or '')
        row['_card_ids'] = [str(item['telegram_message_id']) for item in bindings
                            if item.get('card_mission_id') == card]
        if claim and claim[1]:
            row['_card_ids'].append(str(claim[1]))
    return rows


def _eligible_context(rows, parsed, supplied=None):
    stamp = _time(parsed.get('provider_timestamp'))
    if not stamp:
        return None
    # First retain the latest facts in each conversation, then require an
    # exact card or a unique current context. Never borrow another litter's
    # facts because its message happened to arrive last.
    latest = {}
    for row in rows:
        key = row.get('context_id')
        if key and _time(row.get('provider_timestamp')) and (
                key not in latest or _source_order(row) > _source_order(latest[key])):
            latest[key] = row
    current = [row for row in latest.values()
        if 0 <= (stamp - _time(row['provider_timestamp'])).total_seconds() <= 6 * 3600
        and _source_order(row) <= _source_order(parsed)]
    reply = str(parsed.get('reply_to_message_id') or '')
    if reply:
        current = [row for row in current if reply in row.get('_card_ids', ())]
    supplied = supplied or {}
    if len(current) > 1:
        for key in ('sow_ref', 'litter_ref'):
            ref = str(supplied.get(key) or '').strip().casefold()
            if ref:
                current = [row for row in current if
                    str((row.get('facts') or {}).get(key) or '').strip().casefold() == ref]
    if current:
        newest = max(current, key=_source_order)
        if newest.get('_claim_status') == 'cancelled':
            return {'context_id': newest['context_id'], '_cancelled': True}
    current = [row for row in current if row.get('_claim_status') != 'cancelled']
    return current[0] if len(current) == 1 else None


def _source_order(row):
    provider = str(row.get('provider_message_id') or '')
    return (_time(row.get('provider_timestamp')), int(provider) if provider.isdecimal() else 0)


def load_weaning_context(parsed, *, connect_factory=None):
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
                return {'status': 'weaning_context_cancelled'}
            return {key: prior.get(key) for key in ('context_id', 'facts', 'provider_timestamp', 'question')}
    except Exception:
        return None
    return None


ENGLISH = {
    'Ek kort die werpsel, werklike datum en watter varkies gespeen is.': 'I need the litter, actual date and which piglets were weaned.',
    'Op watter datum het jy hulle werklik gespeen?': 'On what date did you actually wean them?',
    'Watter sog bedoel jy? Gee haar unieke oornommer of ID.': 'Which sow do you mean? Give her unique tag or ID.',
    'Watter werpsel het jy gespeen? Gee die sog se unieke ID en, indien nodig, die werpsel-ID.': 'Which litter did you wean? Give the unique sow ID and, if needed, the litter ID.',
    'Het jy al die huidige lewende varkies in hierdie werpsel gespeen?': 'Did you wean all the current live piglets in this litter?',
    'Watter huidige varkie hoort by hierdie besonderhede? Gee sy unieke ID of oornommer.': 'Which current piglet do these details describe? Give its unique ID or tag.',
    'Gee elke gespeende varkie se unieke ID; die hele huidige werpsel moet ooreenstem.': 'Give each weaned piglet’s unique ID; the complete current litter must match.',
    'Een varkie se identiteit is onseker. Gee sy unieke ID.': 'One piglet’s identity is unclear. Give its unique ID.',
    'Watter presiese produk het jy gebruik? Gee die produk-ID of unieke naam.': 'Which exact product did you use? Give its product ID or unique name.',
    'Die getal stem nie met die huidige varkies ooreen nie. Hoeveel het jy gespeen, en watter varkies was dit?': 'The count does not match the current piglets. How many did you wean, and which piglets were they?',
    'Gee die werklike dosis, toedieningsroete en lotnommer vir die behandeling wat jy genoem het.': 'Give the actual dose, route and batch number for the treatment you reported.',
    'Die speendatum moet ná geboorte wees en mag nie in die toekoms wees nie. Wat was die werklike datum?': 'Weaning must follow birth and cannot be in the future. What was the actual date?',
    'Die opgegewe besonderhede bots. Kontroleer die getalle en elke varkie se gewig, geslag en oornommer.': 'The supplied details conflict. Check the counts and each piglet’s weight, sex and tag.',
    'Die huidige werpselrekords stem nie met die verslag ooreen nie. Kontroleer die werpsel-ID en al die huidige varkies voordat ons bevestig.': 'The current litter records do not match the report. Check the litter ID and every current piglet before confirmation.',
    'Jou eie rekening het nie speentoestemming nie.': 'Your own account does not have weaning permission.',
    'Hierdie boodskap se tyd of identiteit kon nie bevestig word nie.': 'This message’s time or identity could not be verified.',
    'Ek is onseker oor die speenverslag. Gee die werpsel, werklike datum en watter varkies jy bedoel.': 'The weaning report is unclear. Give the litter, actual date and which piglets you mean.',
    'Bevestig die presiese voorskou of stuur die veranderde feite.': 'Confirm the exact preview or send the corrected facts.',
    'Antwoord op die presiese speenvoorskou wat jy wil bevestig.': 'Reply to the exact weaning preview you want to confirm.',
    'Hierdie boodskap se herhaling verskil. Niks is gestoor nie.': 'This repeated message has conflicting content. Nothing was saved.',
    'Hierdie voorskou is nie meer aktief nie. Gebruik die jongste speenkaart.': 'This preview is no longer active. Use the latest weaning card.',
    'Die vorige speengesprek is nie meer duidelik nie. Gee weer die werpsel, datum en omvang.': 'The previous weaning context is no longer clear. Give the litter, date and scope again.',
    "Hierdie speengesprek is gekanselleer. Begin met 'n nuwe verslag as jy weer wil voortgaan.": 'This weaning conversation was cancelled. Start a new report if you want to continue.',
    'Daar is reeds nuwer speenfeite. Gebruik die jongste voorskou.': 'Newer weaning facts have already arrived. Use the latest preview.',
    'Die vorige bevestiging word reeds verwerk of is gestoor. Lees eers daardie uitslag terug.': 'The previous confirmation is processing or saved. Recover its result first.',
    'Bevestig asseblief die werpsel, werklike speendatum en watter varkies jy bedoel.': 'Please clarify the litter, actual weaning date and which piglets you mean.',
    'Ek kon die speengesprek nie veilig behou nie. Niks is bevestig nie.': 'The weaning conversation could not be safely retained. Nothing was confirmed.',
    'Die bevestiging stem nie met jou presiese voorskou ooreen nie.': 'The confirmation does not match your exact preview.',
    'Die speeninskrywing is nog nie bewys nie. Herstel hierdie presiese bevestiging voordat jy weer probeer.': 'The weaning result is not yet proven. Recover this exact confirmation before trying again.',
}


def _answer(status, text, *, success=False, language='af', **extra):
    af = str(language).startswith('af')
    text = text if af else ENGLISH.get(text, text)
    return {'handled': True, 'success': success, 'status': status,
        'specialist': 'HERDMASTER', 'answer': ('<b>Speen</b>\n' if af else '<b>Weaning</b>\n') + text,
        'recipient_render_contract': 'specialist_structured_recipient_v1',
        'recipient_language': 'af' if af else 'en', 'writes_farm_data': False, **extra}


class WeaningClarification(ValueError):
    pass


def _unique(ref, rows, keys, question):
    value = str(ref or '').strip().casefold()
    matched = [row for row in rows if value and any(str(row.get(key) or '').casefold() == value for key in keys)]
    if len(matched) != 1:
        raise WeaningClarification(question)
    return matched[0]


def _actual_date(raw, stamp):
    words = {'today': 0, 'vandag': 0, 'yesterday': 1, 'gister': 1,
             'day before yesterday': 2, 'eergister': 2}
    value = str(raw or '').strip().casefold()
    if value in words:
        return (stamp.astimezone(ZoneInfo('Africa/Johannesburg')).date() - timedelta(days=words[value])).isoformat()
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() == value:
            return value
    except ValueError:
        pass
    raise WeaningClarification('Op watter datum het jy hulle werklik gespeen?')


def _merge(prior, supplied):
    merged = {**prior, **supplied}
    if 'assignments' in supplied:
        by_ref = {row.get('pig_ref'): row for row in prior.get('assignments', [])}
        for row in supplied['assignments']:
            ref = row.get('pig_ref')
            by_ref[ref] = {**by_ref.get(ref, {}), **row}
        merged['assignments'] = list(by_ref.values())
    if 'medicine' in supplied:
        merged['medicine'] = {**prior.get('medicine', {}), **supplied['medicine']}
    return merged


def _prepare(facts, actor, stamp, *, connect_factory=None):
    with _connect(connect_factory) as db:
        db.read_only = True
        with db.cursor() as cursor:
            cursor.execute("select pig_id,tag_number,pig_name from public.current_canonical_pigs where sex='Female'")
            sows = [dict(zip(('pig_id', 'tag_number', 'pig_name'), row)) for row in cursor.fetchall()]
            cursor.execute("select litter_id,sow_pig_id from public.current_canonical_litters where litter_status='Active' and coalesce(weaned_count,0)=0")
            litters = [dict(zip(('litter_id', 'sow_pig_id'), row)) for row in cursor.fetchall()]
    if facts.get('sow_ref'):
        sow = _unique(facts['sow_ref'], sows, ('pig_id', 'tag_number', 'pig_name'),
            'Watter sog bedoel jy? Gee haar unieke oornommer of ID.')
        litters = [row for row in litters if row['sow_pig_id'] == sow['pig_id']]
    if facts.get('litter_ref'):
        litters = [row for row in litters if row['litter_id'].casefold() == facts['litter_ref'].casefold()]
    if not (facts.get('sow_ref') or facts.get('litter_ref')) or len(litters) != 1:
        raise WeaningClarification('Watter werpsel het jy gespeen? Gee die sog se unieke ID en, indien nodig, die werpsel-ID.')
    litter_id = litters[0]['litter_id']
    if facts.get('scope') not in ('all_current', 'exact_piglets'):
        raise WeaningClarification('Het jy al die huidige lewende varkies in hierdie werpsel gespeen?')
    action_date = _actual_date(facts.get('action_date'), stamp)
    facts['action_date'] = action_date  # Retain the resolved date across midnight/interruptions.
    snapshot = reader.get_litter_weaning_snapshot(litter_id, connect_factory=_service_factory(connect_factory))
    current = [row for row in snapshot['piglets'] if row['status'] == 'Active' and row['on_farm'] is True]
    p = {key: facts[key] for key in ('total_count', 'male_count', 'female_count', 'notes', 'target_pen_id') if key in facts}
    p.update(wean_date=action_date, changed_by=actor, dry_run=True)
    p['assignments'] = []
    for row in facts.get('assignments', []):
        pig = _unique(row.get('pig_ref'), current, ('pig_id', 'tag_number'), 'Watter huidige varkie hoort by hierdie besonderhede? Gee sy unieke ID of oornommer.')
        p['assignments'].append({**{key: value for key, value in row.items() if key != 'pig_ref'}, 'pig_id': pig['pig_id']})
    if facts.get('scope') == 'exact_piglets':
        if not facts.get('piglet_refs'):
            raise WeaningClarification('Gee elke gespeende varkie se unieke ID; die hele huidige werpsel moet ooreenstem.')
        p['piglet_ids'] = [_unique(ref, current, ('pig_id', 'tag_number'), 'Een varkie se identiteit is onseker. Gee sy unieke ID.')['pig_id'] for ref in facts['piglet_refs']]
    if facts.get('medicine'):
        medicine = dict(facts['medicine'])
        products = reader.get_products(connect_factory=_service_factory(connect_factory))
        if isinstance(products, dict):
            products = products.get('products', [])
        for key in ('antiparasitic_product_id', 'deworming_product_id', 'vaccination_product_id'):
            if medicine.get(key):
                medicine[key] = _unique(medicine[key], products, ('product_id', 'product_name'),
                    'Watter presiese produk het jy gebruik? Gee die produk-ID of unieke naam.')['product_id']
        p['medicine'] = medicine
    return litter_id, p


def _validation_question(result):
    status = result.get('status', '')
    if status == 'reported_weaning_count_conflict':
        return 'Die getal stem nie met die huidige varkies ooreen nie. Hoeveel het jy gespeen, en watter varkies was dit?'
    if status == 'weaning_treatment_details_required':
        return 'Gee die werklike dosis, toedieningsroete en lotnommer vir die behandeling wat jy genoem het.'
    if status == 'weaning_treatment_product_required':
        return 'Watter presiese produk het jy gebruik? Gee die produk-ID of unieke naam.'
    if 'date' in status:
        return 'Die speendatum moet ná geboorte wees en mag nie in die toekoms wees nie. Wat was die werklike datum?'
    if status == 'weaning_facts_invalid':
        return 'Die opgegewe besonderhede bots. Kontroleer die getalle en elke varkie se gewig, geslag en oornommer.'
    return 'Die huidige werpselrekords stem nie met die verslag ooreen nie. Kontroleer die werpsel-ID en al die huidige varkies voordat ons bevestig.'


def _sow_state(sow, language):
    af = str(language).startswith('af')
    status = str(sow.get('status') or ('Onbekend' if af else 'Unknown'))
    if af:
        status = {'Active':'Aktief', 'Dead':'Dood', 'Sold':'Verkoop', 'Removed':'Verwyder', 'Slaughtered':'Geslag'}.get(status, status)
    on_farm = ('op die plaas' if af else 'on farm') if sow.get('on_farm') is True else ('nie op die plaas nie' if af else 'not on farm')
    return escape(status + ', ' + on_farm)


def _preview_answer(preview, language='af'):
    af = str(language).startswith('af')
    sow = preview['sow']
    lines = [f"{escape(str(sow.get('pig_name') or sow['pig_id']))} ({escape(sow['pig_id'])})",
        f"{'Werpsel' if af else 'Litter'}: {escape(preview['litter_id'])}",
        f"{'Werklik gespeen' if af else 'Actual weaning'}: {preview['wean_date']} — {preview['weaned_count']} {'varkies' if af else 'piglets'}."]
    for pig in preview['piglet_effects']:
        facts = []
        if pig.get('weight_kg') is not None:
            facts.append(f"{pig['weight_kg']} kg")
        if pig.get('sex'):
            facts.append({'Male': 'manlik', 'Female': 'vroulik', 'Castrated_Male': 'gekastreerde mannetjie'}[pig['sex']] if af else pig['sex'])
        if pig.get('tag_number'):
            facts.append(('oornommer ' if af else 'tag ') + escape(pig['tag_number']))
        if pig.get('earmarked') is not None:
            facts.append(('oormerk aangebring' if pig['earmarked'] else 'geen oormerk aangebring nie') if af else ('earmarked' if pig['earmarked'] else 'not earmarked'))
        if pig.get('to_pen_id') != pig.get('from_pen_id'):
            facts.append(('skuif na ' if af else 'move to ') + escape(pig['to_pen_id']))
        lines.append('• ' + escape(pig['pig_id']) + (': ' + ', '.join(facts) if facts else ''))
    if preview.get('reported_sex_counts'):
        tally = preview['reported_sex_counts']
        lines.append(f"Opgegewe telling: {tally['male_count']} manlik, {tally['female_count']} vroulik; individuele geslagte bly soos aangeteken." if af else
            f"Reported tally: {tally['male_count']} male, {tally['female_count']} female; individual sexes remain as recorded.")
    packet = preview['confirmation_binding']['packet']
    for row in packet.get('treatment_rows', []):
        lines.append(('Behandeling: ' if af else 'Treatment: ') + escape(f'{row[1]}: {row[5]}, {row[6]} {row[7]}, {row[8]}, lot {row[10]}'))
        if row[16]:
            lines.append(('Behandelingsnota: ' if af else 'Treatment note: ') + escape(str(row[16])))
    notes = next((row.get('notes') for row in packet['piglets'] if row.get('notes')), '')
    if notes:
        lines.append(('Nota: ' if af else 'Note: ') + escape(notes))
    for item in (packet.get('observation_action') or {}).get('observations', []):
        lines.append(('Waarneming: ' if af else 'Observation: ') + escape(json.dumps(item, ensure_ascii=False)))
    lines.append(('Sog: ' if af else 'Sow: ') + _sow_state(sow, language))
    lines += (['Dooie en verkoopte varkies se geskiedenis bly behoue.', 'Bevestig hierdie presiese speeninskrywing om dit een keer te stoor.'] if af else
              ['Dead and sold piglets remain in history.', 'Confirm this exact weaning record to save it once.'])
    return '\n'.join(lines)


def handle_litter_weaning_message(parsed, authority, *, connect_factory=None):
    language = 'af' if str(parsed.get('output_language') or 'en').startswith('af') else 'en'
    def answer(status, text, **kwargs):
        return _answer(status, text, language=language, **kwargs)
    semantic = parsed.get('semantic') or {}
    if semantic.get('intent') != 'record_litter_weaning' or semantic.get('domain') != 'herd_management':
        return {'handled': False}, 200
    actor, chat = str(parsed.get('telegram_user_id') or ''), str(parsed.get('telegram_chat_id') or '')
    if (not validates_gateway_owner_authority(authority) or not actor or actor != chat
            or authority.owner_user_id != actor or authority.private_chat_id != chat
            or (getattr(authority, 'principal_role', '') != 'owner' and 'weaning' not in authority.capabilities)):
        return answer('weaning_authority_required', 'Jou eie rekening het nie speentoestemming nie.'), 403
    stamp = _time(parsed.get('provider_timestamp'))
    provider = str(parsed.get('provider_message_id') or '')
    if not stamp or not provider or not -30 <= (datetime.now(timezone.utc) - stamp).total_seconds() <= 6 * 3600:
        return answer('weaning_provider_identity_required', 'Hierdie boodskap se tyd of identiteit kon nie bevestig word nie.'), 409
    if semantic.get('message_kind') in ('question', 'request', 'general'):
        return {'handled': False}, 200
    if float(semantic.get('confidence') or 0) < 0.8:
        return answer('weaning_meaning_uncertain', 'Ek is onseker oor die speenverslag. Gee die werpsel, werklike datum en watter varkies jy bedoel.'), 409
    if semantic.get('message_kind') == 'confirmation':
        if semantic.get('needs_clarification') or not semantic.get('continuation') or semantic.get('litter_weaning'):
            return answer('weaning_confirmation_unclear', 'Bevestig die presiese voorskou of stuur die veranderde feite.'), 409
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
            return answer('weaning_confirmation_not_unambiguous', 'Antwoord op die presiese speenvoorskou wat jy wil bevestig.'), 409
        from modules.oom_sakkie.protected_action_runtime import handle_protected_action_input
        result, code = handle_protected_action_input(parsed, authority,
            callback_data='oompa:' + active['callback_token'] + ':confirm', connect_factory=connect_factory,
            weaning_semantic_confirmation=True)
        if code == 409 and result.get('status') in {'weaning_confirmation_not_unambiguous',
                'protected_callback_card_mismatch', 'protected_callback_card_unbound', 'protected_callback_stale'}:
            return answer(result['status'], 'Antwoord op die presiese speenvoorskou wat jy wil bevestig.'), code
        return result, code
    supplied = semantic.get('litter_weaning')
    if not isinstance(supplied, dict):
        return answer('weaning_typed_facts_required', 'Ek kort die werpsel, werklike datum en watter varkies gespeen is.'), 409
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
                        return answer('weaning_provider_replay_conflict', 'Hierdie boodskap se herhaling verskil. Niks is gestoor nie.'), 409
                    token = replay['outcome'].get('callback_token')
                    if token:
                        cursor.execute("""select status,preview_payload,preview_digest,mission_id from
                            app_private.oom_protected_action_claims where callback_token=%s""", (token,))
                        claim = cursor.fetchone()
                        if claim and claim[0] == 'completed':
                            return execute_claimed_litter_weaning({'preview_payload': claim[1],
                                'preview_digest': claim[2], 'mission_id': claim[3]}, parsed, connect_factory=connect_factory)
                        if not claim or claim[0] != 'active':
                            return answer('weaning_preview_superseded', 'Hierdie voorskou is nie meer aktief nie. Gebruik die jongste speenkaart.'), 409
                    return replay['outcome'], replay['http_status']
                if rows and any(_source_order(row) > _source_order(parsed) for row in rows):
                    return answer('weaning_out_of_order', 'Daar is reeds nuwer speenfeite. Gebruik die jongste voorskou.'), 409
                prior = _eligible_context(rows, parsed, supplied) if semantic.get('continuation') else None
                if prior and prior.get('_cancelled'):
                    return answer('weaning_context_cancelled', "Hierdie speengesprek is gekanselleer. Begin met 'n nuwe verslag as jy weer wil voortgaan."), 409
                if semantic.get('continuation') and not prior:
                    return answer('weaning_context_not_current', 'Die vorige speengesprek is nie meer duidelik nie. Gee weer die werpsel, datum en omvang.'), 409
                facts = _merge(prior['facts'] if prior else {}, supplied)
                context_id = prior['context_id'] if prior else 'OOM-WEAN-' + _digest(actor + ':' + provider)[:24].upper()
                # Retire an old confirmation before accepting corrections, even
                # if the corrected facts still need clarification.
                cursor.execute("""select status from app_private.oom_protected_action_claims
                    where mission_id=%s and action_kind=%s for update""", (context_id, ACTION_KIND))
                statuses = {row[0] for row in cursor.fetchall()}
                if 'cancelled' in statuses:
                    return answer('weaning_context_cancelled', "Hierdie speengesprek is gekanselleer. Begin met 'n nuwe verslag as jy weer wil voortgaan."), 409
                if statuses & {'executing', 'completed'}:
                    return answer('weaning_prior_operation_requires_readback', 'Die vorige bevestiging word reeds verwerk of is gestoor. Lees eers daardie uitslag terug.'), 409
                cursor.execute("""update app_private.oom_protected_action_claims set status='changed'
                    where mission_id=%s and action_kind=%s and status='active'""", (context_id, ACTION_KIND))
                try:
                    if supplied.get('action_date'):
                        facts['action_date'] = _actual_date(supplied['action_date'], stamp)
                    if semantic.get('needs_clarification'):
                        raise WeaningClarification('Bevestig asseblief die werpsel, werklike speendatum en watter varkies jy bedoel.')
                    litter_id, p = _prepare(facts, actor, stamp, connect_factory=connect_factory)
                    preview, code = process_litter_weaning_day(litter_id, p,
                        connect_factory=_service_factory(connect_factory), channel='telegram')
                    if code != 200:
                        raise WeaningClarification(_validation_question(preview))
                    bound = {'contract_version': ACTION_KIND, 'litter_id': litter_id, 'payload': p,
                        'confirmation_binding': preview['confirmation_binding'], 'facts': facts,
                        'provider_timestamp': stamp.isoformat(), 'provider_message_id': provider}
                    @contextmanager
                    def borrowed():
                        yield db
                    claim = create_claim(action_kind=ACTION_KIND, owner_user_id=actor, private_chat_id=chat,
                        mission_id=context_id, provider_message_id=provider, evidence_generation=preview['preview_digest'],
                        preview_payload=bound, connect_factory=borrowed, ttl_minutes=15)
                    result = answer('litter_weaning_preview_ready', _preview_answer(preview, language), success=True,
                        mission_id=context_id, card_mission_id=protected_card_mission_id(context_id, claim['preview_digest']),
                        callback_token=claim['callback_token'], preview_digest=claim['preview_digest'], action_kind=ACTION_KIND,
                        reply_markup=build_buttons(claim['callback_token'], language=language), retained_facts=facts, question_count=0)
                    code = 200
                except WeaningClarification as exc:
                    result = answer('litter_weaning_clarification_required', str(exc), success=True,
                        question_count=1, clarification_question=(str(exc) if language == 'af' else ENGLISH.get(str(exc), str(exc))), retained_facts=facts,
                        mission_id=context_id, card_mission_id=context_id)
                    code = 200
                receipt = {**identity, 'context_id': context_id, 'facts': facts,
                    'question': result.get('clarification_question', ''), 'outcome': result, 'http_status': code}
                cursor.execute("""insert into public.sam_live_stock_conversation_review_events(
                    review_event_id,chatwoot_conversation_id,chatwoot_message_id,channel,source_agent,event_source,review_json)
                    values(%s,%s,%s,'telegram','HERDMASTER',%s,%s::jsonb)""",
                    ('WEAN-TURN-' + _digest(actor + ':' + provider), actor, provider, EVENT_SOURCE,
                     json.dumps({CONTEXT_KEY: receipt}, default=str)))
        return result, code
    except Exception:
        LOGGER.exception('Weaning conversation receipt failed for actor %s', actor)
        return answer('weaning_context_store_unavailable', 'Ek kon die speengesprek nie veilig behou nie. Niks is bevestig nie.'), 503


def execute_claimed_litter_weaning(claimed, parsed, *, connect_factory=None):
    language = 'af' if str(parsed.get('output_language') or 'en').startswith('af') else 'en'
    af = language == 'af'
    bound = claimed.get('preview_payload') or {}
    if (bound.get('contract_version') != ACTION_KIND
            or canonical_preview_digest(ACTION_KIND, bound) != claimed.get('preview_digest')
            or bound.get('payload', {}).get('changed_by') != str(parsed.get('telegram_user_id') or '')):
        return _answer('weaning_claim_binding_mismatch', 'Die bevestiging stem nie met jou presiese voorskou ooreen nie.', language=language), 409
    result, code = process_litter_weaning_day(bound['litter_id'], {**bound['payload'], 'dry_run': False,
        'confirmed': True, 'confirmation_binding': bound['confirmation_binding']},
        channel='telegram', connect_factory=_service_factory(connect_factory))
    if not result.get('success'):
        return {**_answer(result['status'], 'Die speeninskrywing is nog nie bewys nie. Herstel hierdie presiese bevestiging voordat jy weer probeer.', language=language),
            **result}, code
    with _connect(connect_factory) as db:
        with db.cursor() as cursor:
            cursor.execute("""select confirmation_provider_message_id,confirmation_provider_timestamp
                from app_private.oom_protected_action_claims where mission_id=%s and preview_digest=%s
                and action_kind=%s""", (claimed['mission_id'], claimed['preview_digest'], ACTION_KIND))
            confirmation = cursor.fetchone()
    delivery_binding = {}
    if confirmation and str(confirmation[0]) == str(parsed.get('provider_message_id')):
        delivery_binding = {'actor_id': str(parsed['telegram_user_id']),
            'provider_message_id': str(confirmation[0]), 'provider_timestamp': confirmation[1].isoformat()}
    text = (f"Speen is gestoor en teruggelees: {result['weaned_count']} varkies, {escape(result['litter_id'])}, {result['wean_date']}.\n"
        f"Sog: {_sow_state(result['sow_readback'], language)}. Aktiewe kudde: {result['active_herd_count']}.\n"
        f"Voorgestelde kontrole vir {escape(result['changed_by'])} op {result['follow_up']['due_date']}: die sog en gespeende varkies. "
        "Hierdie opvolgvoorneme is behou; dit is nog nie geskeduleer nie." if af else
        f"Weaning saved and read back: {result['weaned_count']} piglets, {escape(result['litter_id'])}, {result['wean_date']}.\n"
        f"Sow: {_sow_state(result['sow_readback'], language)}. Active herd: {result['active_herd_count']}.\n"
        f"Suggested review for {escape(result['changed_by'])} on {result['follow_up']['due_date']}: the sow and weaners. "
        "This follow-up intent is retained; it is not scheduled yet.")
    return {**result, **_answer(result['status'], text,
        success=True, language=language, mission_id=claimed['mission_id'],
        card_mission_id=protected_card_mission_id(claimed['mission_id'], claimed['preview_digest']),
        weaning_delivery_binding=delivery_binding,
        reply_markup={'inline_keyboard': []}, owner_visible_completion_policy='verified_edit_or_new_message',
        writes_farm_data=not result['replay_withheld'])}, code


def weaning_delivery_input(parsed, result):
    """Use the persisted confirmation time for retries of one callback ID.

    Telegram callbacks have no event timestamp; ingress receipt time changes on
    retry. A callback's own data binds its text independently of later card edits.
    """
    binding = result.get('weaning_delivery_binding') or {}
    if (binding.get('actor_id') == str(parsed.get('telegram_user_id')) == str(parsed.get('telegram_chat_id'))
            and binding.get('provider_message_id') == str(parsed.get('provider_message_id'))
            and _time(binding.get('provider_timestamp'))):
        return {**parsed, 'provider_timestamp': binding['provider_timestamp'],
            'text': str(parsed.get('callback_data') or parsed.get('text') or '')}
    return parsed
