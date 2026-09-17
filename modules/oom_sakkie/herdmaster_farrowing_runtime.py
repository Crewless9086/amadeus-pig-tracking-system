"""Oom Sakkie -> HERDMASTER protected farrowing/litter action."""

from __future__ import annotations

import html
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Mapping
from zoneinfo import ZoneInfo

from modules.oom_sakkie.gateway_authority import validates_gateway_owner_authority
from modules.oom_sakkie.protected_action_claims import build_buttons, canonical_preview_digest, create_claim
from modules.oom_sakkie.herdmaster_farrowing_conversation import (
    CONTEXT_SECONDS, FarrowingContextError, PostgresFarrowingStore, digest,
    select_context, source_order, source_time,
)
from modules.pig_weights.farm_supabase_write_service import create_governed_farrowing_litter
from modules.pig_weights.herdmaster_farrowing_litter_intake import (
    ACTION_KIND, FarrowingEvidenceError, prepare_farrowing_litter_preview,
)

LOGGER = logging.getLogger(__name__)
FACT_FIELDS = frozenset({"sow_ref", "farrowing_date", "total_born", "born_alive", "stillborn",
    "mummified", "died_after_live_birth", "mating_ref", "father_ref",
    "correction_of_litter_id", "correction_reason"})


def _language(parsed):
    semantic = parsed.get("semantic") or {}
    return "af" if str(parsed.get("output_language") or semantic.get("language") or "en").startswith("af") else "en"


def _reply(language, status, english, afrikaans=None, **extra):
    return {"handled": True, "success": False, "status": status,
        "answer": (afrikaans or english) if language == "af" else english,
        "specialist": "HERDMASTER", "recipient_render_contract": "herdmaster_farrowing_recipient_v1",
        "recipient_language": language, "question_count": 0,
        "writes_farm_data": False, "protected_actions_performed": False, **extra}


def _context_failure(language, status):
    messages = {
        "farrowing_provider_identity_required": (
            "This message's identity or time could not be verified. Please send the birth report again.",
            "Hierdie boodskap se identiteit of tyd kon nie bevestig word nie. Stuur asseblief die geboorteverslag weer."),
        "farrowing_context_ambiguous": (
            "Which sow's birth report are you answering? Give her unique name, tag or ID.",
            "Watter sog se geboorteverslag beantwoord jy? Gee haar unieke naam, oornommer of ID."),
        "farrowing_context_cancelled": (
            "This birth conversation was cancelled. Start a new report if you want to continue.",
            "Hierdie geboortegesprek is gekanselleer. Begin met 'n nuwe verslag as jy weer wil voortgaan."),
        "farrowing_reply_context_mismatch": (
            "That reply does not match the current birth question or preview. Please use its latest card.",
            "Daardie antwoord pas nie by die huidige geboortevraag of voorskou nie. Gebruik asseblief die jongste kaart."),
        "farrowing_out_of_order": (
            "A newer birth report is already retained. Please use the latest question or preview.",
            "'n Nuwer geboorteverslag is reeds behou. Gebruik asseblief die jongste vraag of voorskou."),
        "farrowing_context_not_current": (
            "Which sow and birth date does this reply describe? The earlier birth conversation is no longer current.",
            "Watter sog en geboortedatum beskryf hierdie antwoord? Die vorige geboortegesprek is nie meer geldig nie."),
    }
    english, afrikaans = messages.get(status, messages["farrowing_context_not_current"])
    question = status in {"farrowing_context_ambiguous", "farrowing_context_not_current"}
    return _reply(language, status, english, afrikaans, question_count=int(question))


def load_farrowing_context(parsed, *, connect_factory=None, context_store=None):
    """Read bounded private facts for semantic understanding; this grants no authority."""
    actor, chat = str(parsed.get("telegram_user_id") or ""), str(parsed.get("telegram_chat_id") or "")
    if not actor or actor != chat:
        return None
    try:
        rows = (context_store or PostgresFarrowingStore(connect_factory)).read(actor, chat)
        if not rows:
            return None
        row = select_context(rows, parsed)
        context = {key: row.get(key) for key in ("context_id", "facts", "question", "provider_timestamp",
                                                "canonical_litters", "sow_refs")}
        saved = row.get("_saved_result") or {}
        if row.get("_claim_status") == "completed" and saved.get("canonical_readback_verified") is True:
            readback = saved.get("canonical_readback") or {}
            context["canonical_litters"] = [{key: readback.get(key) for key in (
                "litter_id", "sow_pig_id", "farrowing_date", "total_born", "born_alive",
                "stillborn_count", "mummified_count")}]
            context["canonical_litters_source"] = "retained_confirmed_result"
        return context
    except FarrowingContextError as exc:
        return {"status": exc.status, "question": _context_failure(_language(parsed), exc.status)["answer"]}
    except Exception:
        return {"status": "farrowing_context_unavailable"}


def handle_farrowing_litter_message(parsed: Mapping, authority, *, connect_factory=None,
                                    evidence_loader=None, claim_creator=None, context_store=None, now=None):
    parsed = dict(parsed or {})
    semantic = parsed.get("semantic") if isinstance(parsed.get("semantic"), Mapping) else {}
    supplied = semantic.get("farrowing_litter")
    if semantic.get("intent") != "record_farrowing_litter":
        return {"handled": False, "status": "farrowing_litter_not_applicable"}, 200
    owner, chat = str(parsed.get("telegram_user_id") or ""), str(parsed.get("telegram_chat_id") or "")
    language = _language(parsed)
    if (not validates_gateway_owner_authority(authority) or not owner or owner != chat
            or authority.owner_user_id != owner or authority.private_chat_id != chat
            or getattr(authority, "principal_role", "owner") != "owner"):
        return _reply(language, "farrowing_owner_authority_required",
            "This birth record needs your authenticated private owner account.",
            "Hierdie geboorterekord vereis jou bevestigde private eienaarsrekening."), 403
    if semantic.get("message_kind") == "confirmation":
        return _reply(language, "farrowing_exact_preview_required",
            "Use Confirm on the exact birth preview, or send the facts that should change.",
            "Gebruik Bevestig op die presiese geboortevoorskou, of stuur die feite wat moet verander."), 409
    supplied = {} if supplied is None else supplied
    if not isinstance(supplied, Mapping) or set(supplied) - FACT_FIELDS:
        return _reply(language, "farrowing_typed_facts_required",
            "Which sow gave birth? Give her unique name, tag or ID.",
            "Watter sog het gekraam? Gee haar unieke naam, oornommer of ID.", question_count=1), 200
    supplied = {key: value for key, value in supplied.items() if value is not None and value != ""}
    stamp = source_time(parsed.get("provider_timestamp"))
    provider = str(parsed.get("provider_message_id") or "")
    now = now or datetime.now(timezone.utc)
    if not stamp or not provider or not -30 <= (now - stamp).total_seconds() <= CONTEXT_SECONDS:
        return _context_failure(language, "farrowing_provider_identity_required"), 409
    identity = {"provider_message_id": provider, "provider_timestamp": stamp.isoformat(),
        "content_sha256": digest({"text": str(parsed.get("text") or ""),
            "reply_to_message_id": str(parsed.get("reply_to_message_id") or ""),
            "supplied_facts": supplied, "continuation": semantic.get("continuation") is True})}
    try:
        with (context_store or PostgresFarrowingStore(connect_factory)).locked(owner, chat) as conversation:
            rows = conversation.rows()
            replay = next((row for row in rows if row.get("provider_message_id") == provider), None)
            if replay:
                if any(replay.get(key) != value for key, value in identity.items()):
                    return _reply(language, "farrowing_provider_replay_conflict",
                        "This repeated message has different content. The retained report was kept.",
                        "Hierdie herhaalde boodskap se inhoud verskil. Die behoue verslag is onveranderd."), 409
                token = (replay.get("outcome") or {}).get("callback_token")
                if token:
                    claim = conversation.claim(token)
                    if claim and claim["status"] == "completed" and (claim.get("result") or {}).get("success") is True:
                        return {**claim["result"], "handled": True, "writes_farm_data": False,
                            "protected_actions_performed": False, "rows_created": 0, "replay": True,
                            "status": "farrowing_litter_replayed_noop", "suppress_owner_delivery": True}, 200
                    if (not claim or claim["status"] != "active"
                            or source_time(claim.get("expires_at")) is None
                            or source_time(claim["expires_at"]) <= now):
                        return _reply(language, "farrowing_preview_superseded",
                            "This birth preview is no longer active. Please use the latest birth card.",
                            "Hierdie geboortevoorskou is nie meer aktief nie. Gebruik asseblief die jongste geboortekaart."), 409
                return replay["outcome"], replay["http_status"]
            if any(source_order(row) > source_order(parsed) for row in rows):
                raise FarrowingContextError("farrowing_out_of_order")
            prior = select_context(rows, parsed, supplied) if semantic.get("continuation") else None
            if prior and source_order(parsed) <= source_order(prior):
                raise FarrowingContextError("farrowing_out_of_order")
            facts = {**(prior.get("facts") or {} if prior else {}), **supplied}
            explicit_correction = (semantic.get("message_kind") == "correction"
                and bool(supplied.get("correction_reason")) and semantic.get("needs_clarification") is not True
                and float(semantic.get("confidence") or 0) >= 0.8)
            if prior and explicit_correction and not facts.get("correction_of_litter_id"):
                targets = prior.get("canonical_litters") or []
                saved = prior.get("_saved_result") or {}
                if not targets and prior.get("_claim_status") == "completed" and saved.get("canonical_readback_verified") is True:
                    targets = [saved.get("canonical_readback") or {}]
                if len(targets) == 1 and targets[0].get("litter_id"):
                    facts["correction_of_litter_id"] = str(targets[0]["litter_id"])
            relative_days = {"today": 0, "vandag": 0, "yesterday": 1, "gister": 1,
                             "day before yesterday": 2, "eergister": 2}
            relative = str(supplied.get("farrowing_date") or "").strip().casefold()
            if relative in relative_days:
                facts["farrowing_date"] = (stamp.astimezone(ZoneInfo("Africa/Johannesburg")).date()
                    - timedelta(days=relative_days[relative])).isoformat()
            new_context = "OOM-FARROW-" + digest([owner, chat, provider])[:24].upper()
            context_id = prior["context_id"] if prior else new_context
            protected = conversation.retire(context_id)
            supersedes = ""
            if protected:
                saved = [row for row in protected if row["status"] == "completed"
                         and (row.get("result") or {}).get("litter_id") == facts.get("correction_of_litter_id")]
                if len(saved) == 1 and len(protected) == 1 and (supplied.get("correction_of_litter_id") or explicit_correction):
                    # A saved correction gets a new claim; the original remains immutable.
                    supersedes, context_id = context_id, new_context
                else:
                    return _reply(language, "farrowing_prior_operation_requires_readback",
                        "The previous birth confirmation is processing or saved. Recover that result before changing its facts.",
                        "Die vorige geboortebevestiging word verwerk of is gestoor. Lees daardie uitslag terug voordat die feite verander."), 409
            canonical = (evidence_loader or load_canonical_farrowing_evidence)(connect_factory=connect_factory)
            prepared = prepare_farrowing_litter_preview({"authenticated": True,
                "authenticated_principal_id": owner, "provider_message_id": provider,
                "language": language, "reported_on": stamp.astimezone(ZoneInfo("Africa/Johannesburg")).date(),
                "farrowing_litter": facts}, canonical)
            if prepared.get("success") is True and (semantic.get("needs_clarification") is True
                    or (semantic.get("confidence") is not None and float(semantic["confidence"]) < 0.8)):
                prepared = {"success": False, "status": "farrowing_meaning_uncertain",
                    "question": ("Watter deel van die geboorteverslag moet opgeklaar word?" if language == "af" else
                                 "Which part of the birth report needs clarifying?")}
            if prepared.get("success") is True:
                preview = prepared["preview"]
                claim = (claim_creator or create_claim)(action_kind=ACTION_KIND,
                    owner_user_id=owner, private_chat_id=chat, mission_id=context_id,
                    provider_message_id=provider, evidence_generation=str(preview["evidence_generation"]),
                    preview_payload=preview, connect_factory=conversation.connection, ttl_minutes=15)
                result = _reply(language, "farrowing_litter_preview_ready", _preview_answer(prepared),
                    success=True, mission_id=context_id, card_mission_id=context_id,
                    callback_token=claim["callback_token"], preview_digest=claim["preview_digest"],
                    action_kind=ACTION_KIND, reply_markup=build_buttons(claim["callback_token"], language=language))
                code = 200
            else:
                question = str(prepared.get("question") or "")
                result = _reply(language, prepared["status"], question or _hold_answer(prepared, language=language),
                    mission_id=context_id, card_mission_id=context_id, question_count=int(bool(question)),
                    clarification_question=question, canonical_litters=prepared.get("existing_litters") or [],
                    reply_markup={"inline_keyboard": []})
                code = 200 if question else 409
            result["retained_facts"] = facts
            sow = prepared.get("sow") or {}
            sow_refs = [str(sow.get(key)) for key in ("pig_id", "name", "tag_number") if sow.get(key)]
            if facts.get("sow_ref"):
                sow_refs.append(str(facts["sow_ref"]))
            receipt = {**identity, "owner_user_id": owner, "private_chat_id": chat,
                "context_id": context_id, "supersedes_context_id": supersedes, "facts": facts,
                "sow_refs": sorted(set(sow_refs)), "question": result.get("clarification_question", ""),
                "canonical_litters": result.get("canonical_litters") or [], "outcome": result, "http_status": code}
            conversation.save(receipt)
        return result, code
    except FarrowingContextError as exc:
        return _context_failure(language, exc.status), 409
    except Exception:
        LOGGER.exception("Farrowing conversation could not be retained")
        return _reply(language, "farrowing_context_store_unavailable",
            "The birth conversation could not be safely retained. Nothing was confirmed; please try the same message again.",
            "Die geboortegesprek kon nie veilig behou word nie. Niks is bevestig nie; probeer asseblief dieselfde boodskap weer."), 503


def execute_claimed_farrowing_litter(claimed, parsed, *, connect_factory=None):
    preview = dict(claimed.get("preview_payload") or {})
    language = "af" if str(preview.get("language") or "en").startswith("af") else "en"
    actor = str(parsed.get("telegram_user_id") or "")
    if (not actor or preview.get("principal") != actor
            or preview.get("action_kind") != ACTION_KIND
            or canonical_preview_digest(ACTION_KIND, preview) != claimed.get("preview_digest")):
        return _reply(language, "farrowing_claim_binding_mismatch",
            "This confirmation does not match your exact birth preview.",
            "Hierdie bevestiging stem nie met jou presiese geboortevoorskou ooreen nie."), 409
    litter_id, pig_ids = _operation_ids(preview)
    # A crash after the canonical commit must recover that exact operation
    # before fresh duplicate checks. It must never call the writer a second time.
    saved = load_litter_readback(litter_id, connect_factory=connect_factory)
    if saved:
        if not _readback_matches(preview, saved, litter_id, pig_ids):
            return _reply(language, "farrowing_readback_recovery_required",
                "The saved birth record no longer matches this preview. Its retained result needs review.",
                "Die gestoorde geboorterekord stem nie meer met hierdie voorskou ooreen nie. Die behoue uitslag moet nagegaan word.",
                recovery_required=True), 503
        return _completion_result(preview, {"success": True, "status": "farrowing_litter_replayed_noop",
            "litter_id": litter_id, "pig_ids": pig_ids, "rows_created": 0,
            "writes_farm_data": False, "replay": True}, saved, mission_id=claimed.get("mission_id")), 200
    fresh = load_canonical_farrowing_evidence(connect_factory=connect_factory)
    # Recompose from the exact typed preview against fresh canonical truth. This
    # is the mandatory duplicate/mating check immediately before mutation.
    report = {"authenticated": True,
              "authenticated_principal_id": str(parsed.get("telegram_user_id") or ""),
              "provider_message_id": str(preview.get("provider_message_id") or ""),
              "language": str(preview.get("language") or "en"),
              "farrowing_litter": {"sow_ref": preview.get("sow_pig_id"),
                  "farrowing_date": preview.get("farrowing_date"), **dict(preview.get("counts") or {}),
                  "mating_ref": preview.get("requested_mating_ref"),
                  "father_ref": preview.get("requested_father_ref"),
                  "correction_of_litter_id": preview.get("correction_of_litter_id"),
                  "correction_reason": preview.get("correction_reason")}}
    refreshed = prepare_farrowing_litter_preview(report, fresh)
    if (refreshed.get("success") is not True
            or canonical_preview_digest(ACTION_KIND, refreshed.get("preview") or {}) != claimed.get("preview_digest")):
        return _reply(language, "farrowing_evidence_changed_repreview_required",
            _hold_answer(refreshed, language=language) if refreshed.get("success") is not True else
            "The birth evidence changed. Please review a fresh preview before confirming.",
            _hold_answer(refreshed, language=language) if refreshed.get("success") is not True else
            "Die geboortebewyse het verander. Hersien asseblief 'n nuwe voorskou voordat jy bevestig."), 409
    result = create_governed_farrowing_litter(
        preview, actor_id=str(parsed.get("telegram_user_id") or ""), connect_factory=connect_factory)
    readback = load_litter_readback(result["litter_id"], connect_factory=connect_factory)
    if not _readback_matches(preview, readback, litter_id, pig_ids):
        return {**result, "success": False, "status": "farrowing_readback_recovery_required",
                "recovery_required": True}, 503
    return _completion_result(preview, result, readback, mission_id=claimed.get("mission_id")), 201


def _operation_ids(preview):
    operation = str(preview.get("operation_id") or "")
    litter_id = "LIT-OOM-" + hashlib.sha256(operation.encode()).hexdigest()[:16].upper()
    pig_ids = ["PIG-OOM-" + hashlib.sha256(f"{operation}:{index}".encode()).hexdigest()[:16].upper()
               for index in range(int((preview.get("counts") or {}).get("born_alive") or 0))]
    return litter_id, pig_ids


def _readback_matches(preview, readback, litter_id, pig_ids):
    if not isinstance(readback, Mapping):
        return False
    counts = preview.get("counts") or {}
    fields = {"total_born": "total_born", "born_alive": "born_alive",
              "stillborn_count": "stillborn", "mummified_count": "mummified"}
    return (str(readback.get("litter_id") or "") == litter_id
        and str(readback.get("sow_pig_id") or "") == preview.get("sow_pig_id")
        and str(readback.get("farrowing_date") or "")[:10] == preview.get("farrowing_date")
        and (readback.get("boar_pig_id") or None) == (preview.get("father_pig_id") or None)
        and all(readback.get(column) is not None and readback[column] == counts.get(key)
                for column, key in fields.items())
        and sorted(readback.get("pig_ids") or []) == sorted(pig_ids)
        and bool(readback.get("follow_up_case_id")))


def _completion_result(preview, result, readback, *, mission_id=None):
    label = _sow_label(preview)
    af = str(preview.get("language") or "").startswith("af")
    if af:
        answer = (f"{label} se werpsel is aangeteken: totaal {preview['counts']['total_born']}, "
                  f"{preview['counts']['born_alive']} lewend gebore, {preview['counts']['stillborn']} doodgebore, "
                  f"{preview['counts']['mummified']} gemummifiseer op {preview['farrowing_date']}. "
                  + ("Paring en vader bly Onbekend. " if not preview.get("mating_id") else "Die toepaslike paring is as Gekry gemerk. ")
                  + f"Werpsel {html.escape(result['litter_id'])}. "
                  + "HERDMASTER se opvolg vir werpselsorg, merk, weeg en speen is behou.")
    else:
        answer = (f"Litter recorded for {label}: total {preview['counts']['total_born']}, "
                  f"{preview['counts']['born_alive']} born alive, {preview['counts']['stillborn']} stillborn, "
                  f"{preview['counts']['mummified']} mummified on {preview['farrowing_date']}. "
                  + ("Mating and father remain Unknown. " if not preview.get("mating_id") else "The attributable mating was marked Farrowed. ")
                  + f"Litter {html.escape(result['litter_id'])}. "
                  + "HERDMASTER's litter-care, tagging, weighing and weaning follow-up is retained.")
    mission_id = str(mission_id or "OOM-" + preview["operation_id"])
    return {**result, "handled": True, "specialist": "HERDMASTER", "answer": answer, "canonical_readback": readback,
            "mission_id": mission_id, "card_mission_id": mission_id,
            "protected_actions_performed": result.get("writes_farm_data") is True,
            "canonical_readback_verified": True, "follow_up_owner": "HERDMASTER",
            "follow_up_case_id": readback["follow_up_case_id"],
            "recipient_render_contract": "herdmaster_farrowing_recipient_v1",
            "recipient_language": "af" if af else "en",
            "owner_visible_completion_policy": "verified_edit_or_new_message",
            "reply_markup": {"inline_keyboard": []}}


def load_canonical_farrowing_evidence(*, connect_factory=None):
    with _connect(connect_factory) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("select pig_id,tag_number,pig_name as name,status,on_farm,sex,animal_type from public.current_canonical_pigs")
            animals = _rows(cursor)
            cursor.execute("""select mating_id,sow_pig_id,boar_pig_id,mating_date,outcome,
                (expected_farrowing_date - interval '10 days')::date as expected_farrowing_window_start,
                (expected_farrowing_date + interval '10 days')::date as expected_farrowing_window_end,
                related_litter_id as linked_litter_id
                from public.mating_events order by mating_date,mating_id""")
            matings = _rows(cursor)
            cursor.execute("""select litter_id,sow_pig_id,boar_pig_id,farrowing_date,total_born,born_alive,
                stillborn_count,mummified_count from public.current_canonical_litters""")
            litters = _rows(cursor)
    generation = "farrowing:" + digest({
        "animals": sorted(animals, key=lambda row: str(row.get("pig_id") or "")),
        "matings": sorted(matings, key=lambda row: str(row.get("mating_id") or "")),
        "litters": sorted(litters, key=lambda row: str(row.get("litter_id") or ""))})
    return {"evidence_generation": generation, "animals": animals, "matings": matings, "litters": litters}


def load_litter_readback(litter_id, *, connect_factory=None):
    with _connect(connect_factory) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("""select litter_id,sow_pig_id,boar_pig_id,farrowing_date,total_born,
                born_alive,stillborn_count,mummified_count,litter_status from public.current_canonical_litters
                where litter_id=%s""", (litter_id,))
            rows = _rows(cursor)
            if len(rows) != 1:
                return None
            readback = rows[0]
            cursor.execute("select pig_id from public.current_canonical_pigs where litter_id=%s order by pig_id",
                           (litter_id,))
            readback["pig_ids"] = [str(row[0]) for row in cursor.fetchall()]
            cursor.execute("select case_id from app_private.oom_manager_cases where dedupe_key=%s",
                           ("herdmaster-litter-follow-up:" + litter_id,))
            cases = cursor.fetchall()
            readback["follow_up_case_id"] = str(cases[0][0]) if len(cases) == 1 else None
    return readback


def _connect(factory):
    if factory:
        return factory()
    import psycopg
    return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10)


def _rows(cursor):
    names = [item.name if hasattr(item, "name") else item[0] for item in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _hold_answer(result, *, language="en"):
    af = language == "af"
    sow = result.get("sow") or {}
    label = _sow_label({"sow_pig_id": sow.get("pig_id"),
                       "sow_display_name": sow.get("name") or sow.get("tag_number")})
    existing = result.get("existing_litters") or []
    if result.get("status") in {"canonical_litter_already_exists", "canonical_litter_count_conflict"}:
        if len(existing) != 1:
            return (f"Daar is meer as een bestaande werpselrekord vir {label} op hierdie datum. Die presiese rekord moet eers nagegaan word." if af else
                    f"There is more than one saved litter for {label} on this date. The exact record needs review first.")
        row = existing[0]
        unknown = "Onbekend" if af else "Unknown"
        count = lambda key: html.escape(str(row[key])) if row.get(key) is not None else unknown
        litter = html.escape(str(row.get("litter_id") or ""))
        birth = html.escape(str(row.get("farrowing_date") or "")[:10])
        text = (f"{label} se werpsel op {birth} is reeds gestoor ({litter}): totaal {count('total_born')}, "
                f"lewend gebore {count('born_alive')}, doodgebore {count('stillborn_count')}, gemummifiseer {count('mummified_count')}. " if af else
                f"{label}'s litter on {birth} is already saved ({litter}): total {count('total_born')}, "
                f"born alive {count('born_alive')}, stillborn {count('stillborn_count')}, mummified {count('mummified_count')}. ")
        if result.get("status") == "canonical_litter_count_conflict":
            names = {"total_born": "totaal" if af else "total", "born_alive": "lewend gebore" if af else "born alive",
                     "stillborn": "doodgebore" if af else "stillborn", "mummified": "gemummifiseer" if af else "mummified"}
            supplied = ", ".join(f"{names[key]} {html.escape(str(value))}"
                                 for key, value in (result.get("reported_counts") or {}).items())
            text += (f"Hierdie verslag gee {supplied}; dit verskil van die gestoorde rekord. " if af else
                     f"This report gives {supplied}; it differs from the saved record. ")
            text += ("Die gestoorde rekord bly onveranderd. As jy hierdie werpsel wil regstel, sê vir my waarom; ek sal jou opgegewe tellings gebruik en 'n nuwe bevestiging voorberei." if af else
                     "The saved record is unchanged. If you want to correct this saved litter, tell me why; I will use the counts you supplied and prepare a new confirmation.")
        else:
            text += "Geen nuwe werpsel is aangeteken nie." if af else "No new litter was recorded."
        return text
    if result.get("status") == "current_active_on_farm_sow_required":
        return (f"{label} is nie as 'n aktiewe sog op die plaas aangeteken nie. Haar huidige status moet eers nagegaan word." if af else
                f"{label} is not recorded as an active sow on farm. Her current status needs review first.")
    if result.get("status") == "litter_correction_target_invalid":
        return ("Die regstelling pas nie by een bestaande werpsel vir hierdie sog en datum nie. Kontroleer die presiese werpsel-ID." if af else
                "The correction does not match one saved litter for this sow and date. Check the exact litter ID.")
    question = str(result.get("question") or "")
    return question or ("Die geboortebesonderhede moet eers nagegaan word. Niks is aangeteken nie." if af else
                        "The birth details need review first. Nothing was recorded.")


def _preview_answer(result):
    p, c = result["preview"], result["counts"]
    label = _sow_label(p)
    af = str(p.get("language") or "").startswith("af")
    linkage = (f"Mating {p['mating_id']} and father {p['father_pig_id']} will be linked."
               if p.get("mating_id") else "Mating and father will remain Unknown; neither will be invented.")
    if af:
        linkage = (f"Paring {p['mating_id']} en vader {p['father_pig_id']} sal gekoppel word."
                   if p.get("mating_id") else "Paring en vader bly Onbekend; niks word uitgedink nie.")
        return (f"HERDMASTER werpselvoorskou: {label}, {p['farrowing_date']}; "
                f"totaal {c['total_born']}, lewend gebore {c['born_alive']}, doodgebore {c['stillborn']}, "
                f"gemummifiseer {c['mummified']}. {linkage} Bevestig die presiese beskermde rekord.")
    return (f"HERDMASTER litter preview: {label}, {p['farrowing_date']}; "
            f"total {c['total_born']}, born alive {c['born_alive']}, stillborn {c['stillborn']}, "
            f"mummified {c['mummified']}. {linkage} Confirm the exact protected record.")


def _sow_label(preview):
    pig_id = html.escape(str(preview.get("sow_pig_id") or "").strip())
    name = html.escape(str(preview.get("sow_display_name") or "").strip())
    return f"{name} ({pig_id})" if name and name.casefold() != pig_id.casefold() else pig_id
