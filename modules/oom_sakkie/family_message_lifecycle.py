"""Exact-once visible lifecycle for authenticated owner farm messages.

The existing Telegram gateway owns authentication and intent reasoning.  This
module only persists a deterministic mission and delivers/edits one owner card;
it creates no router, bot, specialist service, or farm-write authority.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import time
from typing import Any, Callable, Mapping

EVENT_SOURCE = "oom_sakkie_family_message_lifecycle"
PROVIDER_DELIVERY_RESERVE_SECONDS = 30


def _provider_deadline_available(deadline_monotonic):
    return (deadline_monotonic is None
            or time.monotonic() + PROVIDER_DELIVERY_RESERVE_SECONDS
                <= deadline_monotonic)


def _visible_notification_identity(card_mission_id, text_sha, parsed, specialist):
    inbound = _inbound_binding(parsed, specialist)
    inbound_sha = hashlib.sha256(json.dumps(inbound, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    return (card_mission_id + "-VISIBLE-WAIT-V2-" + text_sha[:20].upper()
            + "-" + inbound_sha[:20].upper())


def _visible_notification_events(events, card_mission_id, text_sha, parsed, specialist):
    identity = _visible_notification_identity(card_mission_id, text_sha, parsed, specialist)
    current = [row for row in events
        if str(row.get("event_id") or "").startswith(identity)]
    if current:
        return identity, current
    # Compatibility for notices written before inbound-bound V2 identity. A
    # legacy notice can suppress only the same authenticated provider inbound;
    # identical wording from a later inbound is a distinct must-notice event.
    legacy = card_mission_id + "-VISIBLE-WAIT-" + text_sha[:20].upper()
    inbound = _inbound_binding(parsed, specialist)
    legacy_events = [row for row in events
        if str(row.get("event_id") or "").startswith(legacy)
        and all(str(row.get(key) or "") == value for key, value in inbound.items())]
    return (legacy, legacy_events) if legacy_events else (identity, [])


def mission_identity(parsed: Mapping[str, Any], specialist: str) -> str:
    raw = "|".join((str(parsed.get("telegram_user_id") or ""),
                    str(parsed.get("telegram_chat_id") or ""),
                    str(parsed.get("provider_message_id") or ""), specialist))
    return "OOM-FAMILY-" + hashlib.sha256(raw.encode()).hexdigest()[:24].upper()


def localize_recipient_result(parsed: Mapping[str, Any], result: Mapping[str, Any],
                              specialist: str) -> dict[str, Any]:
    """Final provider boundary: one language for every Oom Sakkie specialist."""
    localized = dict(result)
    if not str(parsed.get("output_language") or "en").casefold().startswith("af"):
        return localized
    status = str(localized.get("status") or "").casefold()
    answer = str(localized.get("answer") or "").strip()
    original_answer = answer
    if answer:
        identity = str(localized.get("specialist_identity") or localized.get("specialist")
                       or specialist or "OOM SAKKIE").replace("_", " ")
        campaign = localized.get("campaign_review_preview")
        if status == "media_album_received":
            count = int(localized.get("album_stored_count") or 0)
            answer = (f"<b>BEACON — PRIVAAT GESTOOR</b>\n\n{count} foto('s) is veilig in hierdie album gestoor. "
                "Voeg die oorblywende foto's by en kies Voltooi album. Biblioteekaanvaarding, openbare gebruik, "
                "veldtoghersiening en publikasie bly afsonderlike beskermde handelinge.")
        elif status == "documents_green_request_clarification_required":
            answer = "Wil jy hê ek moet die weeklikse weegblad vir drukwerk voorberei?"
        elif isinstance(campaign, Mapping):
            budget = campaign.get("budget_cap") if isinstance(campaign.get("budget_cap"), Mapping) else {}
            duration = campaign.get("duration") if isinstance(campaign.get("duration"), Mapping) else {}
            objective = _afrikaans_campaign_objective(
                campaign.get("campaign_objective") or campaign.get("campaign_lane"))
            exact_copy = str(campaign.get("exact_post_copy") or "")
            answer = "\n".join(("<b>BEACON — BESKERMDE VELDTOGVOORSKOU</b>",
                f"<b>Doel:</b> {objective}",
                "<b>Gebonde publikasie-inhoud (presies; die inhoudstaal kan van jou kennisgewingstaal verskil):</b>",
                f"<blockquote>{html.escape(exact_copy)}</blockquote>",
                f"<b>Facebook-blad-ID:</b> {campaign.get('target_page_id')}",
                f"<b>Publiseer teen:</b> {campaign.get('publication_time')}",
                f"<b>Begroting:</b> ZAR {budget.get('total', '0.00')} totaal; ZAR {budget.get('daily', '0.00')} per dag; {duration.get('days', 0)} dae.",
                "Bevestig slegs hierdie presiese gebonde pakket. Geen outomatiese herprobeer word toegelaat nie."))
        elif all(localized.get(key) not in (None, "") for key in
                 ("received_amount", "payment_method", "payment_date")):
            answer = (f"<b>SAM — VEREFFENING VOLTOOI</b>\n\nVeiling afgehandel. "
                f"Ontvang: R{localized['received_amount']} via {localized['payment_method']} "
                f"op {localized['payment_date']}. Volledig gerekonsilieer.")
        elif (localized.get("recipient_render_contract") == "specialist_structured_recipient_v1"
              and str(localized.get("recipient_language") or "").casefold().startswith("af")
              and answer.startswith("<b>") and "</b>" in answer
              and _looks_afrikaans(answer)):
            # A specialist structured renderer already owns recipient wording.
            answer = original_answer
        elif "change" in status or "correct" in status:
            answer = "Stuur die reggestelde feite wanneer jy gereed is. Niks is uitgevoer nie."
        elif "cancel" in status or "declin" in status:
            answer = "Die beskermde handeling is gekanselleer. Niks is uitgevoer nie."
        elif any(word in status for word in ("preview", "review_ready", "waiting_for_confirmation")):
            facts = _afrikaans_bound_facts(localized)
            answer = (f"<b>{identity} — BESKERMDE VOORSKOU</b>\n\n"
                + (facts + "\n\n" if facts else "") +
                "Hersien die gebonde besonderhede en bevestig slegs as dit korrek is. "
                "Niks word uitgevoer voordat jy bevestig nie.")
        elif any(word in status for word in ("completed", "recorded", "started", "accepted")):
            answer = (f"<b>{identity} — VOLTOOI</b>\n\n"
                "Die bevestigde handeling is een keer voltooi en die kanonieke resultaat is behou.")
        elif any(word in status for word in ("replay", "duplicate")):
            answer = "Hierdie bevestiging is reeds veilig verwerk. Geen duplikaat is geskep nie."
        elif any(word in status for word in ("fail", "unavailable", "invalid", "contained", "hold")):
            answer = "Die handeling is veilig teruggehou. Niks is uitgevoer nie; probeer later weer."
        localized["answer"] = answer
    markup = localized.get("reply_markup")
    if isinstance(markup, Mapping):
        labels = {"confirm": "Bevestig", "change": "Maak reg", "cancel": "Kanselleer"}
        rows = []
        for row in markup.get("inline_keyboard", []):
            translated = []
            for button in row:
                item = dict(button)
                action = str(item.get("callback_data") or "").rsplit(":", 1)[-1]
                if action in labels:
                    item["text"] = labels[action]
                elif str(item.get("text") or "").casefold() == "finish album":
                    item["text"] = "Voltooi album"
                translated.append(item)
            rows.append(translated)
        localized["reply_markup"] = {**markup, "inline_keyboard": rows}
    localized["recipient_language"] = "af"
    if answer and answer == original_answer and not _looks_afrikaans(answer):
        localized["recipient_language_render_unrecognized"] = True
    return localized


def _afrikaans_campaign_objective(value: Any) -> str:
    key = str(value or "").strip().casefold()
    return {"farm_awareness": "bewusmaking van die plaas",
        "organic_awareness": "organiese bewusmaking",
        "live_stock_enquiry_capture": "gekwalifiseerde lewendehawe-navrae",
        "qualified_livestock_enquiries": "gekwalifiseerde lewendehawe-navrae",
        "sale_ready_demand": "vraag na verkoopsgereed vee",
        "litter_awareness": "bewusmaking van die werpsel"}.get(
            key, "gebinde plaasveldtog")


def _looks_afrikaans(text: str) -> bool:
    words = {word.strip(".,:;!?()[]<>").casefold() for word in str(text).split()}
    english = {"the", "and", "confirm", "please", "which", "want", "completed",
        "received", "recorded", "nothing", "printed", "stored", "remaining"}
    afrikaans = words & {"die", "het", "is", "nie", "geen", "word", "bevestig",
        "vark", "plaas", "besproeiing", "veilig", "wanneer", "hierdie", "jou",
        "foto", "foto's", "voltooi", "reggestelde", "gekanselleer", "aksie",
        "nodig", "staan", "drink", "kontroleer", "outomaties", "welstandsopdatering"}
    return len(afrikaans) >= 2 and not bool(words & english)


def _afrikaans_bound_facts(result: Mapping[str, Any]) -> str:
    labels = {"pig_id": "Vark", "pig_number": "Vark", "tag_number": "Oormerk",
        "effective_date": "Datum", "weight_date": "Datum", "zone_id": "Sone",
        "segment_requested_seconds": "Tyd (sekondes)", "amount": "Bedrag",
        "payment_amount": "Bedrag", "publication_time": "Publikasietyd",
        "printer_id": "Drukker", "copies": "Kopieë", "row_count": "Aantal"}
    sources = [result]
    for key in ("preview", "preview_payload", "proposal", "canonical_preview", "document_preview"):
        if isinstance(result.get(key), Mapping):
            sources.append(result[key])
    lines, seen = [], set()
    for source in sources:
        for key, label in labels.items():
            value = source.get(key)
            if value in (None, "", [], {}) or (key, str(value)) in seen:
                continue
            seen.add((key, str(value)))
            lines.append(f"<b>{label}:</b> {value}")
        rows = source.get("rows") if isinstance(source.get("rows"), (list, tuple)) else ()
        for row in rows[:5]:
            if not isinstance(row, Mapping):
                continue
            values = [str(row.get(key) or "") for key in
                ("pig_id", "animal_ref", "boar_id", "boar_ref", "to_pen_id")]
            if row.get("action"):
                values.append(_afrikaans_farm_action(row.get("action")))
            values = [value for value in values if value]
            if values:
                lines.append("<b>Dierhandeling:</b> " + " — ".join(values))
    return "\n".join(lines[:8])


def _afrikaans_farm_action(value: Any) -> str:
    key = str(value or "").strip().casefold()
    return {"exposure": "dekking", "recovery_hold": "herstelwaarneming",
        "near_farrowing": "naby kraam", "movement": "skuif",
        "record_weight": "teken gewig aan", "mortality": "teken afsterwe aan"}.get(
            key, "gebinde plaasaksie")


def deliver_family_result(parsed: Mapping[str, Any], result: Mapping[str, Any], *,
                          specialist: str, mission_id: str = "", card_mission_id: str = "",
                          event_store=None, sender=None, editor=None,
                          delivery_retry_authority=None, protected_delivery=None,
                          deadline_monotonic=None) -> dict[str, Any]:
    """Persist and visibly deliver one result; duplicate input is a no-op."""
    result = localize_recipient_result(parsed, result, specialist)
    if result.get("recipient_language_render_unrecognized") is True:
        return {"success": False, "status": "recipient_language_render_unrecognized",
            "telegram_sends": 0, "telegram_edits": 0, "hardware_commands": 0,
            "writes_farm_data": False}
    mission_id = mission_id or mission_identity(parsed, specialist)
    card_mission_id = card_mission_id or mission_id
    protected_fields = tuple(bool(result.get(key)) for key in
        ("callback_token", "preview_digest", "action_kind"))
    if any(protected_fields) and not all(protected_fields):
        return {"success": False, "status": "protected_delivery_binding_incomplete",
            "mission_id": mission_id, "card_mission_id": card_mission_id,
            "telegram_sends": 0, "telegram_edits": 0, "hardware_commands": 0,
            "writes_farm_data": False}
    if all(protected_fields) and result.get("_protected_delivery_owned") is not True:
        if protected_delivery is None:
            from modules.oom_sakkie.protected_delivery_lifecycle import recover_protected_card
            protected_delivery = recover_protected_card
        return protected_delivery(callback_token=str(result["callback_token"]),
            preview_digest=str(result["preview_digest"]),
            owner_user_id=str(parsed.get("telegram_user_id") or ""),
            private_chat_id=str(parsed.get("telegram_chat_id") or ""),
            action_kind=str(result["action_kind"]),
            deliver=lambda: deliver_family_result(parsed,
                {**result, "_protected_delivery_owned": True}, specialist=specialist,
                mission_id=mission_id, card_mission_id=card_mission_id,
                event_store=event_store, sender=sender, editor=editor,
                delivery_retry_authority=delivery_retry_authority,
                protected_delivery=protected_delivery,
                deadline_monotonic=deadline_monotonic))
    if (result.get("album_progress_serialization_required") is True
            and result.get("album_progress_verified") is True
            and result.get("_album_progress_lock_held") is not True):
        try:
            from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
            with connect_bounded_rootline_postgres(database_url=os.environ.get("DATABASE_URL"),
                    read_only=False) as connection, connection.cursor() as cursor:
                cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",
                    ("beacon-album-card:"+card_mission_id,))
                return deliver_family_result(parsed,{**result,"_album_progress_lock_held":True},
                    specialist=specialist,mission_id=mission_id,card_mission_id=card_mission_id,
                    event_store=event_store,sender=sender,editor=editor,
                    delivery_retry_authority=delivery_retry_authority,
                    protected_delivery=protected_delivery,
                    deadline_monotonic=deadline_monotonic)
        except Exception:
            return {"success":False,"status":"family_message_album_progress_lock_unavailable",
                "mission_id":mission_id,"card_mission_id":card_mission_id,
                "telegram_sends":0,"telegram_edits":0}
    store = event_store or _event_store
    events = list(store("load", card_mission_id, None) or [])
    text = str(result.get("answer") or "").strip()
    if not text:
        return {"success": False, "status": "family_message_visible_text_required",
                "mission_id": mission_id, "telegram_sends": 0, "telegram_edits": 0}
    text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    reply_markup = result.get("reply_markup") if isinstance(result.get("reply_markup"), Mapping) else None
    exclusive_completion = (
        result.get("owner_visible_completion_policy") == "verified_edit_or_new_message"
        and str(result.get("status") or "") in {
            "completed", "grouped_weights_completed", "mortality_lifecycle_recorded",
            "payment_state_recorded", "payment_state_replay_noop",
            "protected_preview_cancelled", "protected_preview_change_requested",
            "segment_started", "active_segment_owned", "private_media_review_recorded",
            "private_media_review_presented"
        }
    )
    if exclusive_completion and reply_markup is None:
        reply_markup={"inline_keyboard":[]}
    delivered = next((row for row in events if row.get("state") == "delivered"), None)
    latest = next((row for row in reversed(events) if row.get("state") in {"delivered", "updated"}), delivered)
    card_id = str((latest or {}).get("telegram_message_id") or "")
    immutable_initial_card = (
        specialist == "BEACON_MEDIA"
        and result.get("status") == "media_album_received"
        and result.get("owner_visible_card_policy") == "immutable_initial_card"
    )
    album_progress_card = (specialist == "BEACON_MEDIA"
        and result.get("status") == "media_album_received"
        and result.get("owner_visible_card_policy") == "album_progress_card")
    if album_progress_card and latest:
        exact_card_binding=(str(latest.get("mission_id") or "")==mission_id
            and str(latest.get("card_mission_id") or "")==card_mission_id
            and str(latest.get("specialist_identity") or "")==specialist
            and str(latest.get("owner_user_id") or "")==str(parsed.get("telegram_user_id") or "")
            and str(latest.get("chat_id") or "")==str(parsed.get("telegram_chat_id") or "")
            and bool(card_id))
        if not exact_card_binding:
            return {"success":False,"status":"family_message_album_progress_binding_conflict",
                "mission_id":mission_id,"card_mission_id":card_mission_id,
                "telegram_sends":0,"telegram_edits":0}
        if str(latest.get("task_state") or "") == "completed":
            return {"success": True, "status": "family_message_completed_album_progress_noop",
            "mission_id": mission_id, "card_mission_id": card_mission_id,
            "telegram_message_id": card_id, "telegram_sends": 0, "telegram_edits": 0}
        if int(latest.get("album_stored_count") or 0)>=int(result.get("album_stored_count") or 0):
            return {"success":True,"status":"family_message_album_progress_stale_noop",
                "mission_id":mission_id,"card_mission_id":card_mission_id,
                "telegram_message_id":card_id,"telegram_sends":0,"telegram_edits":0}
    if immutable_initial_card and latest:
        exact_card_binding = (
            str(latest.get("mission_id") or "") == mission_id
            and str(latest.get("card_mission_id") or "") == card_mission_id
            and str(latest.get("specialist_identity") or "") == specialist
            and str(latest.get("owner_user_id") or "")
                == str(parsed.get("telegram_user_id") or "")
            and str(latest.get("chat_id") or "")
                == str(parsed.get("telegram_chat_id") or "")
            and bool(card_id)
        )
        if not exact_card_binding:
            return {"success": False,
                "status": "family_message_immutable_card_binding_conflict",
                "mission_id": mission_id, "card_mission_id": card_mission_id,
                "telegram_sends": 0, "telegram_edits": 0}
        return {"success": True,
            "status": "family_message_immutable_card_replayed_noop",
            "mission_id": mission_id, "card_mission_id": card_mission_id,
            "telegram_message_id": card_id,
            "telegram_sends": 0, "telegram_edits": 0}
    inbound_binding = _inbound_binding(parsed, specialist)
    material_update = _material_update_authorized(parsed, result, specialist,
        mission_id, card_mission_id)
    contextual_delivery_resume = (
        result.get("delivery_recovery_required") is True
        and result.get("response_contract_version") == "contextual_specialist_response_v2"
        and result.get("replay_suppressed") is False
        and result.get("suppress_owner_delivery") is False
        and result.get("hardware_commands") == 0
        and result.get("provider_control_calls") == 0
        and result.get("writes_farm_data") is False
        and result.get("authority") == {"configuration_write": False,
            "hardware_control": False, "farm_write": False, "telegram_send": False}
        and str(result.get("provider_message_id") or "") == inbound_binding["provider_message_id"]
        and str(result.get("mission_id") or "") == mission_id
        and str(result.get("card_mission_id") or "") == card_mission_id)
    payload = _event(parsed, mission_id, card_mission_id, specialist,
                     str(result.get("status") or "working"), text_sha)
    if int(result.get("question_count") or 0) == 1:
        payload["clarification_question"] = str(
            result.get("clarification_question") or text)[:240]
    for key in ("execution_id", "entity_id", "domain", "contextual_task_kind",
                "confirmation_prompt_sha256", "operation_id", "preview_hash",
                "evidence_generation", "confirmation_token",
                "confirmation_provider_message_id", "confirmation_provider_timestamp",
                "confirmation_text_sha256"):
        if str(result.get(key) or "").strip():
            payload[key] = str(result.get(key))
    if album_progress_card:
        payload["album_stored_count"]=int(result.get("album_stored_count") or 0)
        payload["album_canonical_digest"]=str(result.get("album_canonical_digest") or "")
    if isinstance(result.get("required_owner_confirmations"), (list, tuple)):
        payload["required_owner_confirmations"] = list(result["required_owner_confirmations"])
    if isinstance(result.get("accepted_owner_confirmation_binding"), Mapping):
        payload["accepted_owner_confirmation_binding"] = dict(result["accepted_owner_confirmation_binding"])
    provider_replay = next((row for row in reversed(events)
        if row.get("state") in {"delivered", "updated", "provider_binding"}
        and (row.get("state") == "provider_binding"
             or (not str(row.get("recovery_provider_message_id") or "")
                 and (not str(row.get("event_id") or "")
                      or str(row.get("event_id") or "").endswith("-DELIVERED"))))
        and str(row.get("provider_message_id") or "") == inbound_binding["provider_message_id"]), None)
    if provider_replay and not provider_replay.get("inbound_text_sha256"):
        return {"success": False, "status": "family_message_provider_replay_binding_unavailable",
                "mission_id": mission_id, "card_mission_id": card_mission_id,
                "telegram_message_id": str(provider_replay.get("telegram_message_id") or card_id),
                "telegram_sends": 0, "telegram_edits": 0}
    if provider_replay and any(str(provider_replay.get(key) or "") != value
            for key, value in inbound_binding.items()):
        return {"success": False, "status": "family_message_provider_replay_binding_conflict",
                "mission_id": mission_id, "card_mission_id": card_mission_id,
                "telegram_message_id": str(provider_replay.get("telegram_message_id") or card_id),
                "telegram_sends": 0, "telegram_edits": 0}
    exclusive_completion_restore = bool(provider_replay and exclusive_completion
        and str((latest or {}).get("text_sha256") or "") != text_sha)
    if provider_replay and exclusive_completion and not exclusive_completion_restore:
        return {"success": True, "status": "family_message_completion_replayed_noop",
            "mission_id": mission_id, "card_mission_id": card_mission_id,
            "telegram_message_id": str(provider_replay.get("telegram_message_id") or card_id),
            "telegram_sends": 0, "telegram_edits": 0}
    if (provider_replay and result.get("requires_visible_notification") is True
            and provider_replay.get("state") == "updated"
            and str(provider_replay.get("text_sha256") or "") == text_sha):
        _notification_id, notification_events = _visible_notification_events(
            events, card_mission_id, text_sha, parsed, specialist)
        if any(row.get("state") == "notification_delivered" for row in notification_events):
            return {"success": True, "status": "family_message_provider_replay_noop",
                "mission_id": mission_id, "card_mission_id": card_mission_id,
                "telegram_message_id": card_id, "telegram_sends": 0, "telegram_edits": 0}
        if notification_events:
            return {"success": False, "status": "family_message_notification_ambiguous",
                "mission_id": mission_id, "card_mission_id": card_mission_id,
                "telegram_message_id": card_id, "telegram_sends": 0, "telegram_edits": 0}
        return _deliver_visible_notification(parsed, payload, text, mission_id,
            card_mission_id, card_id, text_sha, store, sender,
            specialist=specialist, prior_edits=0,
            deadline_monotonic=deadline_monotonic)
    if (provider_replay and not material_update and not contextual_delivery_resume
            and not exclusive_completion_restore):
        return {"success": True, "status": "family_message_provider_replay_noop",
                "mission_id": mission_id, "card_mission_id": card_mission_id,
                "telegram_message_id": str(provider_replay.get("telegram_message_id") or card_id),
                "telegram_sends": 0, "telegram_edits": 0}
    if (card_id and result.get("requires_visible_notification") is True):
        update_id = card_mission_id + "-UPDATE-" + text_sha[:20].upper()
        prior_update = [row for row in events
            if str(row.get("event_id") or "").startswith(update_id)]
        if any(row.get("state") == "updated" for row in prior_update):
            # The exact presentation was already provider-confirmed under an
            # earlier inbound identity. Do not edit it again; the current
            # must-notice lifecycle gets only its separately claimed notice.
            _notification_id, notification_events = _visible_notification_events(
                events, card_mission_id, text_sha, parsed, specialist)
            if any(row.get("state") == "notification_delivered"
                    for row in notification_events):
                return {"success": True, "status": "family_message_replayed_noop",
                    "mission_id": mission_id, "card_mission_id": card_mission_id,
                    "telegram_message_id": card_id,
                    "telegram_sends": 0, "telegram_edits": 0}
            if notification_events:
                return {"success": False, "status": "family_message_notification_ambiguous",
                    "mission_id": mission_id, "card_mission_id": card_mission_id,
                    "telegram_message_id": card_id,
                    "telegram_sends": 0, "telegram_edits": 0}
            return _deliver_visible_notification(parsed, payload, text, mission_id,
                card_mission_id, card_id, text_sha, store, sender,
                specialist=specialist, prior_edits=0,
                deadline_monotonic=deadline_monotonic)
    if latest and str(latest.get("text_sha256") or "") == text_sha:
        return {"success": True, "status": "family_message_replayed_noop",
                "mission_id": mission_id, "card_mission_id": card_mission_id,
                "telegram_message_id": card_id, "telegram_sends": 0, "telegram_edits": 0}

    if card_id:
        update_id = card_mission_id + "-UPDATE-" + text_sha[:20].upper()
        if exclusive_completion_restore:
            update_id += "-MONOTONIC-RESTORE-2"
        prior_update = [row for row in events
            if str(row.get("event_id") or "").startswith(update_id)]
        ambiguous_edit = any(row.get("state") == "contained"
            and row.get("reason") == "telegram_edit_unconfirmed" for row in prior_update)
        orphaned_edit_claim = (
            any(row.get("state") == "update_attempted" for row in prior_update)
            and not any(row.get("state") in {"updated", "contained"}
                        for row in prior_update)
        )
        if (ambiguous_edit or orphaned_edit_claim) and exclusive_completion:
            # Editing the same provider card to the same text with empty
            # buttons is idempotent. Permit one separately claimed recovery
            # attempt after either an unconfirmed edit or a process stop after
            # the claim; never send a replacement card.
            update_id += "-RECOVERY-2"
        if ((ambiguous_edit or orphaned_edit_claim)
                and result.get("requires_visible_notification") is True):
            # Never retry the ambiguous edit. A must-notice lifecycle question
            # gets one separately claimed provider notification instead. The
            # same rule applies when the worker stopped after the edit claim:
            # provider edit truth is then ambiguous and must not be retried.
            _notification_id, notification_events = _visible_notification_events(
                events, card_mission_id, text_sha, parsed, specialist)
            if any(row.get("state") == "notification_delivered"
                    for row in notification_events):
                return {"success": True, "status": "family_message_replayed_noop",
                    "mission_id": mission_id, "card_mission_id": card_mission_id,
                    "telegram_message_id": card_id,
                    "telegram_sends": 0, "telegram_edits": 0}
            if notification_events:
                return {"success": False, "status": "family_message_notification_ambiguous",
                    "mission_id": mission_id, "card_mission_id": card_mission_id,
                    "telegram_message_id": card_id,
                    "telegram_sends": 0, "telegram_edits": 0}
            return _deliver_visible_notification(parsed, payload, text, mission_id,
                card_mission_id, card_id, text_sha, store, sender,
                specialist=specialist, prior_edits=0,
                deadline_monotonic=deadline_monotonic)
        if not _provider_deadline_available(deadline_monotonic):
            return {"success": False, "status": "family_message_cycle_deadline_deferred",
                    "mission_id": mission_id, "card_mission_id": card_mission_id,
                    "telegram_message_id": card_id,
                    "telegram_sends": 0, "telegram_edits": 0}
        claimed = store("record", update_id, {**payload, "event_id": update_id,
            "state": "update_attempted", "telegram_message_id": card_id})
        if claimed.get("created") is False:
            return {"success": False, "status": "family_message_update_delivery_ambiguous",
                    "mission_id": mission_id, "telegram_sends": 0, "telegram_edits": 0}
        provider_editor = editor or _edit_telegram
        editor_args = (str(parsed.get("telegram_chat_id") or ""), card_id, text)
        editor_kwargs = ({"deadline_monotonic": deadline_monotonic}
                         if deadline_monotonic is not None else {})
        if editor is None:
            editor_kwargs["reply_markup"] = reply_markup
        response = provider_editor(*editor_args, **editor_kwargs)
        edit_verified = bool(response.get("success") and (
            not exclusive_completion
            or str(response.get("telegram_message_id") or "") == card_id
        ))
        if not edit_verified:
            store("record", update_id + "-CONTAINED", {**payload, "event_id": update_id + "-CONTAINED",
                "state": "contained", "reason": "telegram_edit_unconfirmed"})
            return {"success": False, "status": "family_message_update_contained",
                    "mission_id": mission_id, "telegram_sends": 0, "telegram_edits": 0}
        store("record", update_id + "-DELIVERED", {**payload, "event_id": update_id + "-DELIVERED",
            "state": "updated", "telegram_message_id": card_id})
        if exclusive_completion:
            return {"success": True, "status": "family_message_completion_card_updated",
                "mission_id": mission_id, "card_mission_id": card_mission_id,
                "telegram_message_id": card_id, "telegram_sends": 0,
                "telegram_edits": 1}
        if result.get("requires_visible_notification") is True:
            return _deliver_visible_notification(parsed, payload, text, mission_id,
                card_mission_id, card_id, text_sha, store, sender,
                specialist=specialist, prior_edits=1,
                deadline_monotonic=deadline_monotonic)
        return {"success": True, "status": "family_message_card_updated",
                "mission_id": mission_id, "card_mission_id": card_mission_id,
                "telegram_message_id": card_id, "telegram_sends": 0, "telegram_edits": 1}

    from modules.oom_sakkie.delivery_retry_authority import validates_delivery_retry_authority
    retry_two = validates_delivery_retry_authority(delivery_retry_authority,
        mission_id=mission_id, card_mission_id=card_mission_id, text=text)
    attempt_id = card_mission_id + ("-DELIVERY-RETRY-2" if retry_two else "-DELIVERY-ATTEMPT")
    if not _provider_deadline_available(deadline_monotonic):
        return {"success": False, "status": "family_message_cycle_deadline_deferred",
                "mission_id": mission_id, "card_mission_id": card_mission_id,
                "telegram_sends": 0, "telegram_edits": 0}
    claimed = store("record", attempt_id, {**payload, "event_id": attempt_id, "state": "delivery_attempted"})
    if claimed.get("created") is False:
        return {"success": False, "status": "family_message_delivery_ambiguous",
                "mission_id": mission_id, "telegram_sends": 0, "telegram_edits": 0}
    provider_sender = sender or _send_telegram
    sender_args = (str(parsed.get("telegram_chat_id") or ""), text)
    sender_kwargs = ({"deadline_monotonic": deadline_monotonic}
                     if deadline_monotonic is not None else {})
    if sender is None:
        sender_kwargs["reply_markup"] = reply_markup
    response = provider_sender(*sender_args, **sender_kwargs)
    message_id = str(response.get("telegram_message_id") or "")
    if not response.get("success") or not message_id:
        reason = ("telegram_delivery_definitely_not_sent"
                  if response.get("delivery_definitely_not_sent") is True
                  else "telegram_delivery_unconfirmed")
        store("record", attempt_id + "-CONTAINED", {**payload, "event_id": attempt_id + "-CONTAINED",
            "state": "contained", "reason": reason})
        return {"success": False, "status": "family_message_delivery_contained",
                "mission_id": mission_id, "telegram_sends": 0, "telegram_edits": 0,
                "delivery_definitely_not_sent": response.get("delivery_definitely_not_sent") is True}
    delivered_id = card_mission_id + "-DELIVERED"
    delivered = store("record", delivered_id, {**payload, "event_id": delivered_id, "state": "delivered",
        "telegram_message_id": message_id,
        "delivery_provider_timestamp": str(response.get("provider_timestamp") or "")})
    if not isinstance(delivered, dict) or delivered.get("success") is not True:
        return {"success": False,
            "status": "family_message_provider_confirmed_receipt_unavailable",
            "provider_delivery_confirmed": True,
            "mission_id": mission_id, "card_mission_id": card_mission_id,
            "telegram_message_id": message_id, "telegram_sends": 1,
            "telegram_edits": 0}
    return {"success": True, "status": "family_message_delivered",
            "provider_delivery_confirmed": True,
            "mission_id": mission_id, "card_mission_id": card_mission_id,
            "telegram_message_id": message_id, "telegram_sends": 1, "telegram_edits": 0}


def replace_current_brief(parsed: Mapping[str, Any], result: Mapping[str, Any], *,
                          mission_id: str, card_mission_id: str,
                          previous_message_id: str, generation_digest: str,
                          event_store=None, sender=None, deleter=None,
                          projection_lock=None, _projection_lock_held=False) -> dict[str, Any]:
    """Confirm a new Brief generation before superseding and cleaning the old one."""
    text = str(result.get("answer") or "").strip()
    digest = str(generation_digest or "").lower()
    prior_id = str(previous_message_id or "").strip()
    if (result.get("status") != "daily_farm_manager_ready"
            or result.get("rolling_brief_replacement") is not True
            or not text or len(digest) != 64 or not prior_id):
        return {"success": False, "status": "brief_replacement_binding_incomplete",
                "telegram_sends": 0, "telegram_edits": 0, "telegram_deletes": 0}
    if not _projection_lock_held:
        if projection_lock is not None:
            with projection_lock(card_mission_id):
                return replace_current_brief(parsed, result, mission_id=mission_id,
                    card_mission_id=card_mission_id, previous_message_id=prior_id,
                    generation_digest=digest, event_store=event_store, sender=sender,
                    deleter=deleter, projection_lock=projection_lock,
                    _projection_lock_held=True)
        if event_store is None:
            from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
            with connect_bounded_rootline_postgres(
                    database_url=os.environ.get("DATABASE_URL"), read_only=False) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("select pg_advisory_lock(hashtextextended(%s,0))",
                        ("oom-current-brief:" + card_mission_id,))
                try:
                    return replace_current_brief(parsed, result, mission_id=mission_id,
                        card_mission_id=card_mission_id, previous_message_id=prior_id,
                        generation_digest=digest, event_store=event_store, sender=sender,
                        deleter=deleter, _projection_lock_held=True)
                finally:
                    with connection.cursor() as cursor:
                        cursor.execute("select pg_advisory_unlock(hashtextextended(%s,0))",
                            ("oom-current-brief:" + card_mission_id,))
    store = event_store or _event_store
    events = list(store("load", card_mission_id, None) or [])
    owner_scope = hashlib.sha256((str(parsed.get("telegram_user_id") or "") + "|"
        + str(parsed.get("telegram_chat_id") or "")).encode()).hexdigest()[:16].upper()
    generation_id = (card_mission_id + "-OWNER-" + owner_scope
        + "-GENERATION-" + digest[:20].upper())
    generation_events = [row for row in events
        if str(row.get("event_id") or "").startswith(generation_id)]
    delivered = next((row for row in reversed(generation_events)
        if row.get("state") == "brief_generation_delivered"), None)
    superseded_receipt = next((row for row in reversed(generation_events)
        if row.get("state") == "brief_generation_superseded"), None)
    confirmed_generation_ids = {str(row.get("event_id") or "").removesuffix("-SUPERSEDED")
        for row in events if row.get("state") == "brief_generation_superseded"}
    brief_deliveries = [row for row in events
        if ((row.get("state") in {"delivered", "updated"}
             and row.get("task_state") == "daily_farm_manager_ready")
            or (row.get("state") == "brief_generation_delivered"
                and str(row.get("event_id") or "").removesuffix("-DELIVERED")
                    in confirmed_generation_ids))
        and str(row.get("owner_user_id") or "") == str(parsed.get("telegram_user_id") or "")
        and str(row.get("chat_id") or "") == str(parsed.get("telegram_chat_id") or "")
        and str(row.get("specialist_identity") or "") == "OOM_SAKKIE"]
    prior = brief_deliveries[-1] if brief_deliveries else None
    if not prior or str(prior.get("telegram_message_id") or "") != prior_id:
        return {"success": False, "status": "brief_replacement_prior_binding_unproven",
            "telegram_sends": 0, "telegram_edits": 0, "telegram_deletes": 0}
    if str(prior.get("generation_digest") or "").lower() == digest:
        return {"success": True, "status": "brief_replacement_unchanged_suppressed",
            "mission_id": mission_id, "card_mission_id": card_mission_id,
            "telegram_message_id": prior_id, "previous_telegram_message_id": prior_id,
            "telegram_sends": 0, "telegram_edits": 0, "telegram_deletes": 0}
    if generation_events and any(
            str(row.get("owner_user_id") or "") != str(parsed.get("telegram_user_id") or "")
            or str(row.get("chat_id") or "") != str(parsed.get("telegram_chat_id") or "")
            or str(row.get("generation_digest") or "") != digest
            or str(row.get("previous_telegram_message_id") or "") != prior_id
            for row in generation_events):
        return {"success": False, "status": "brief_replacement_generation_binding_conflict",
            "telegram_sends": 0, "telegram_edits": 0, "telegram_deletes": 0}
    cleanup_receipt = next((row for row in reversed(generation_events)
        if row.get("state") in {"brief_previous_deleted", "brief_cleanup_debt"}), None)
    if delivered and superseded_receipt and cleanup_receipt:
        return {"success": True, "status": "brief_replacement_replayed_noop",
            "mission_id": mission_id, "card_mission_id": card_mission_id,
            "telegram_message_id": str(delivered.get("telegram_message_id") or ""),
            "previous_telegram_message_id": prior_id,
            "telegram_sends": 0, "telegram_edits": 0, "telegram_deletes": 0}
    if delivered and superseded_receipt and not cleanup_receipt:
        recovery = store("record", generation_id + "-CLEANUP", {
            **dict(delivered), "event_id": generation_id + "-CLEANUP",
            "state": "brief_cleanup_debt", "telegram_message_id": str(
                delivered.get("telegram_message_id") or ""),
            "superseded_telegram_message_id": prior_id,
            "cleanup_failure_class": "cleanup_outcome_unknown_after_interruption"})
        return {"success": isinstance(recovery, dict) and recovery.get("success") is True,
            "status": "brief_replaced_cleanup_debt" if isinstance(recovery, dict)
                and recovery.get("success") is True else "brief_cleanup_receipt_unavailable",
            "provider_delivery_confirmed": True,
            "telegram_message_id": str(delivered.get("telegram_message_id") or ""),
            "previous_telegram_message_id": prior_id,
            "telegram_sends": 0, "telegram_edits": 0, "telegram_deletes": 0}
    if generation_events and not delivered:
        return {"success": False, "status": "brief_replacement_delivery_ambiguous",
            "mission_id": mission_id, "card_mission_id": card_mission_id,
            "previous_telegram_message_id": prior_id,
            "telegram_sends": 0, "telegram_edits": 0, "telegram_deletes": 0}
    payload = _event(parsed, mission_id, card_mission_id, "OOM_SAKKIE",
                     "brief_generation", digest)
    payload.update({"generation_digest": digest,
                    "previous_telegram_message_id": prior_id})
    sends = 0
    if delivered:
        new_id = str(delivered.get("telegram_message_id") or "")
    else:
        claim = store("record", generation_id, {**payload, "event_id": generation_id,
            "state": "brief_generation_delivery_attempted"})
        if not isinstance(claim, dict) or claim.get("created") is not True:
            return {"success": False, "status": "brief_replacement_delivery_ambiguous",
                    "telegram_sends": 0, "telegram_edits": 0, "telegram_deletes": 0}
        response = ((sender)(str(parsed.get("telegram_chat_id") or ""), text)
                    if sender else _send_telegram(str(parsed.get("telegram_chat_id") or ""), text))
        new_id = str((response or {}).get("telegram_message_id") or "")
        if not (response or {}).get("success") or not new_id:
            store("record", generation_id + "-CONTAINED", {**payload,
                "event_id": generation_id + "-CONTAINED", "state": "contained",
                "reason": "brief_replacement_delivery_unconfirmed"})
            return {"success": False, "status": "brief_replacement_delivery_ambiguous",
                    "previous_telegram_message_id": prior_id,
                    "telegram_sends": 0, "telegram_edits": 0, "telegram_deletes": 0}
        sends = 1
        receipt = store("record", generation_id + "-DELIVERED", {**payload,
            "event_id": generation_id + "-DELIVERED", "state": "brief_generation_delivered",
            "telegram_message_id": new_id,
            "delivery_provider_timestamp": str((response or {}).get("provider_timestamp") or "")})
        if not isinstance(receipt, dict) or receipt.get("success") is not True:
            return {"success": False, "status": "brief_replacement_provider_confirmed_receipt_unavailable",
                "provider_delivery_confirmed": True, "telegram_message_id": new_id,
                "previous_telegram_message_id": prior_id,
                "telegram_sends": 1, "telegram_edits": 0, "telegram_deletes": 0}
    superseded = store("record", generation_id + "-SUPERSEDED", {**payload,
        "event_id": generation_id + "-SUPERSEDED", "state": "brief_generation_superseded",
        "telegram_message_id": new_id, "superseded_telegram_message_id": prior_id})
    if not isinstance(superseded, dict) or superseded.get("success") is not True:
        return {"success": False, "status": "brief_replacement_supersession_receipt_unavailable",
            "provider_delivery_confirmed": True, "telegram_message_id": new_id,
            "previous_telegram_message_id": prior_id,
            "telegram_sends": sends, "telegram_edits": 0, "telegram_deletes": 0}
    cleanup = ((deleter)(str(parsed.get("telegram_chat_id") or ""), prior_id)
               if deleter else _delete_telegram(str(parsed.get("telegram_chat_id") or ""), prior_id))
    deleted = bool((cleanup or {}).get("success"))
    cleanup_receipt = store("record", generation_id + "-CLEANUP", {**payload,
        "event_id": generation_id + "-CLEANUP",
        "state": "brief_previous_deleted" if deleted else "brief_cleanup_debt",
        "telegram_message_id": new_id, "superseded_telegram_message_id": prior_id,
        "cleanup_failure_class": "" if deleted else str((cleanup or {}).get("status") or "unconfirmed")})
    cleanup_recorded = isinstance(cleanup_receipt, dict) and cleanup_receipt.get("success") is True
    return {"success": cleanup_recorded,
        "status": "brief_replaced" if deleted else "brief_replaced_cleanup_debt",
        **({"status": "brief_cleanup_receipt_unavailable"} if not cleanup_recorded else {}),
        "provider_delivery_confirmed": True, "mission_id": mission_id,
        "card_mission_id": card_mission_id, "telegram_message_id": new_id,
        "previous_telegram_message_id": prior_id,
        "telegram_sends": sends, "telegram_edits": 0, "telegram_deletes": int(deleted)}


def _deliver_visible_notification(parsed, payload, text, mission_id, card_mission_id,
                                   card_id, text_sha, store, sender, *, specialist,
                                   prior_edits, deadline_monotonic=None):
    if not _provider_deadline_available(deadline_monotonic):
        return {"success": False, "status": "family_message_cycle_deadline_deferred",
            "mission_id": mission_id, "card_mission_id": card_mission_id,
            "telegram_message_id": card_id, "telegram_sends": 0,
            "telegram_edits": prior_edits}
    notification_id = _visible_notification_identity(
        card_mission_id, text_sha, parsed, specialist)
    notification_claim = store("record", notification_id, {**payload,
        "event_id": notification_id, "state": "notification_attempted",
        "telegram_message_id": card_id})
    if notification_claim.get("created") is not True:
        return {"success": False, "status": "family_message_notification_ambiguous",
            "mission_id": mission_id, "card_mission_id": card_mission_id,
            "telegram_message_id": card_id, "telegram_sends": 0, "telegram_edits": prior_edits}
    provider_sender = sender or _send_telegram
    sender_kwargs = ({"deadline_monotonic": deadline_monotonic}
                     if deadline_monotonic is not None else {})
    notification = provider_sender(
        str(parsed.get("telegram_chat_id") or ""), text, **sender_kwargs)
    notification_message_id = str(notification.get("telegram_message_id") or "")
    if not notification.get("success") or not notification_message_id:
        store("record", notification_id + "-CONTAINED", {**payload,
            "event_id": notification_id + "-CONTAINED", "state": "contained",
            "reason": "telegram_notification_unconfirmed", "telegram_message_id": card_id})
        return {"success": False, "status": "family_message_notification_contained",
            "mission_id": mission_id, "card_mission_id": card_mission_id,
            "telegram_message_id": card_id, "telegram_sends": 0, "telegram_edits": prior_edits}
    notification_receipt = store("record", notification_id + "-DELIVERED", {**payload,
        "event_id": notification_id + "-DELIVERED", "state": "notification_delivered",
        "telegram_message_id": card_id, "notification_message_id": notification_message_id,
        "delivery_provider_timestamp": str(notification.get("provider_timestamp") or "")})
    if not isinstance(notification_receipt, dict) or notification_receipt.get("success") is not True:
        return {"success": False,
            "status": "family_message_notification_provider_confirmed_receipt_unavailable",
            "provider_delivery_confirmed": True,
            "mission_id": mission_id, "card_mission_id": card_mission_id,
            "telegram_message_id": card_id,
            "notification_message_id": notification_message_id,
            "telegram_sends": 1, "telegram_edits": prior_edits}
    return {"success": True, "status": "family_message_card_updated_and_notified",
        "provider_delivery_confirmed": True,
        "mission_id": mission_id, "card_mission_id": card_mission_id,
        "telegram_message_id": card_id, "notification_message_id": notification_message_id,
        "telegram_sends": 1, "telegram_edits": prior_edits}


def bind_existing_card(parsed: Mapping[str, Any], *, specialist: str, mission_id: str,
                       telegram_message_id: str, text_sha256: str,
                       expected_bot_identity: str, provider_evidence_loader,
                       event_store=None):
    """Bind provider-proven legacy delivery without sending or editing it."""
    if not all(str(value or "").strip() for value in
               (mission_id, telegram_message_id, text_sha256, expected_bot_identity)):
        return {"success": False, "status": "existing_card_binding_incomplete"}
    evidence = provider_evidence_loader(str(parsed.get("telegram_chat_id") or ""),
                                        str(telegram_message_id))
    evidence = evidence if isinstance(evidence, Mapping) else {}
    expected = {"delivered": True, "bot_identity": str(expected_bot_identity),
        "chat_id": str(parsed.get("telegram_chat_id") or ""),
        "telegram_message_id": str(telegram_message_id),
        "text_sha256": str(text_sha256).lower()}
    actual = {"delivered": evidence.get("delivered"),
        "bot_identity": str(evidence.get("bot_identity") or ""),
        "chat_id": str(evidence.get("chat_id") or ""),
        "telegram_message_id": str(evidence.get("telegram_message_id") or ""),
        "text_sha256": str(evidence.get("text_sha256") or "").lower()}
    if actual != expected:
        return {"success": False, "status": "existing_card_provider_evidence_mismatch",
                "telegram_sends": 0, "telegram_edits": 0}
    store = event_store or _event_store
    if list(store("load", mission_id, None) or []):
        return {"success": False, "status": "existing_card_binding_conflict"}
    payload = _event(parsed, mission_id, mission_id, specialist,
                     "waiting_for_input", str(text_sha256).lower())
    event_id = mission_id + "-DELIVERED"
    recorded = store("record", event_id, {**payload, "event_id": event_id,
        "state": "delivered", "telegram_message_id": str(telegram_message_id),
        "recovered_provider_delivery": True})
    return {"success": recorded.get("success") is True,
            "status": "existing_card_bound" if recorded.get("success") is True else "existing_card_binding_failed",
            "mission_id": mission_id, "telegram_message_id": str(telegram_message_id),
            "telegram_sends": 0, "telegram_edits": 0}


def bind_legacy_provider_request(parsed: Mapping[str, Any], *, specialist: str, card_mission_id: str,
                                 telegram_message_id: str, provider_evidence_loader, event_store=None):
    """Append an exact inbound binding to a legacy delivered card after authoritative provider proof."""
    store = event_store or _event_store
    events = list(store("load", card_mission_id, None) or [])
    card = next((row for row in reversed(events) if row.get("state") in {"delivered", "updated"}
                 and str(row.get("telegram_message_id") or "") == str(telegram_message_id)), None)
    if not card:
        return {"success": False, "status": "legacy_provider_card_not_found"}
    binding = _inbound_binding(parsed, specialist)
    evidence = provider_evidence_loader(binding["provider_message_id"])
    evidence = evidence if isinstance(evidence, Mapping) else {}
    expected = {**binding, "telegram_message_id": str(telegram_message_id)}
    actual = {key: str(evidence.get(key) or "") for key in expected}
    if actual != expected:
        return {"success": False, "status": "legacy_provider_binding_evidence_mismatch"}
    event_id = card_mission_id + "-PROVIDER-BINDING-" + binding["inbound_text_sha256"][:20].upper()
    payload = {**_event(parsed, card_mission_id, card_mission_id, specialist,
                       "provider_binding", str(card.get("text_sha256") or "")),
               "event_id": event_id, "state": "provider_binding",
               "telegram_message_id": str(telegram_message_id)}
    recorded = store("record", event_id, payload)
    return {"success": recorded.get("success") is True,
            "status": "legacy_provider_binding_recorded" if recorded.get("success") is True else "legacy_provider_binding_failed",
            "created": recorded.get("created"), "telegram_sends": 0, "telegram_edits": 0}


def _event(parsed, mission_id, card_mission_id, specialist, task_state, text_sha):
    semantic = parsed.get("semantic") if isinstance(parsed.get("semantic"), Mapping) else {}
    return {"mission_id": mission_id, "card_mission_id": card_mission_id,
        "owner_user_id": str(parsed.get("telegram_user_id") or ""),
        "chat_id": str(parsed.get("telegram_chat_id") or ""),
        "provider_message_id": str(parsed.get("provider_message_id") or ""),
        "provider_timestamp": str(parsed.get("provider_timestamp") or ""),
        "inbound_text_sha256": _inbound_binding(parsed, specialist)["inbound_text_sha256"],
        "specialist_identity": specialist, "task_state": task_state,
        "text_sha256": text_sha,
        "semantic_domain": str(semantic.get("domain") or "")[:40],
        "semantic_intent": str(semantic.get("intent") or "")[:100],
        "semantic_continuation": semantic.get("continuation") is True,
        "clarification_question": str(semantic.get("clarification_question") or "")[:240]}


def _inbound_binding(parsed, specialist):
    normalized = " ".join(str(parsed.get("text") or "").split())
    return {"owner_user_id": str(parsed.get("telegram_user_id") or ""),
        "chat_id": str(parsed.get("telegram_chat_id") or ""),
        "specialist_identity": str(specialist),
        "provider_message_id": str(parsed.get("provider_message_id") or ""),
        "provider_timestamp": str(parsed.get("provider_timestamp") or ""),
        "inbound_text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest()}


def _material_update_authorized(parsed, result, specialist, mission_id="", card_mission_id=""):
    authority = result.get("material_recomposition_authority")
    binding = result.get("binding")
    if not isinstance(authority, Mapping) or not isinstance(binding, Mapping):
        return False
    expected_binding = {
        "owner": str(parsed.get("telegram_user_id") or ""),
        "chat": str(parsed.get("telegram_chat_id") or ""),
        "provider_message_id": str(parsed.get("provider_message_id") or ""),
        "provider_timestamp": str(parsed.get("provider_timestamp") or ""),
        "content_digest": hashlib.sha256(
            str(parsed.get("text") or "").encode("utf-8")).hexdigest(),
        "contract_version": str(binding.get("contract_version") or ""),
    }
    binding_digest = hashlib.sha256(json.dumps(
        dict(binding), sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    manager_update = (specialist == "OOM_SAKKIE"
        and result.get("status") == "farm_manager_round_ready"
        and binding.get("contract_version") == "oom_sakkie_farm_manager_round_v5"
        and dict(binding) == expected_binding
        and authority.get("from_contract") == "oom_sakkie_farm_manager_round_v4"
        and authority.get("to_contract") == "oom_sakkie_farm_manager_round_v5"
        and authority.get("provider_binding_digest") == binding_digest)
    observation_candidate = (specialist == "ROOTLINE"
        and result.get("status") == "specialist_accepted"
        and binding.get("contract_version") == "oom_rootline_observation_recovery_v1"
        and dict(binding) == expected_binding
        and authority.get("from_systemic_exception") == "rootline_canonical_observation_bridge_failed"
        and authority.get("to_contract") == "oom_rootline_observation_recovery_v1"
        and len(str(authority.get("prior_result_digest") or "")) == 64
        and str(authority.get("current_result_digest") or "") == str(result.get("result_digest") or "")
        and str(authority.get("replacement_text_digest") or "") == hashlib.sha256(
            str(result.get("answer") or "").encode("utf-8")).hexdigest()
        and authority.get("provider_binding_digest") == binding_digest)
    observation_recovery = observation_candidate and _validate_rootline_recovery_authority(
        authority, binding, mission_id, card_mission_id)
    return manager_update or observation_recovery


def _validate_rootline_recovery_authority(authority, binding, mission_id, card_mission_id):
    if not mission_id or card_mission_id != mission_id or not str(os.environ.get("DATABASE_URL") or "").strip():
        return False
    try:
        from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
        with connect_bounded_rootline_postgres(
                database_url=os.environ.get("DATABASE_URL")) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select review_json->'rootline_operational_intake'
                    from public.sam_live_stock_conversation_review_events
                    where event_source='oom_sakkie_rootline_operational_intake'
                      and review_json->'rootline_operational_intake'->>'mission_id'=%s
                    order by created_at,review_event_id""", (mission_id,))
                rows = [row[0] for row in cursor.fetchall()]
    except Exception:
        return False
    prior_valid = False
    current_valid = False
    for row in rows:
        context = row.get("context") if isinstance(row, Mapping) else None
        outcome = row.get("outcome") if isinstance(row, Mapping) else None
        if not isinstance(context, Mapping) or not isinstance(outcome, Mapping):
            continue
        exact = {"owner": str(context.get("owner_user_id") or ""),
            "chat": str(context.get("chat_id") or ""),
            "provider_message_id": str(context.get("provider_message_id") or ""),
            "provider_timestamp": str(context.get("provider_timestamp") or ""),
            "content_digest": str(context.get("content_sha256") or ""),
            "contract_version": "oom_rootline_observation_recovery_v1"}
        if (dict(binding) == exact
                and outcome.get("systemic_exception") == "rootline_canonical_observation_bridge_failed"
                and outcome.get("writes_farm_data") is False
                and str(outcome.get("result_digest") or "") == str(authority.get("prior_result_digest") or "")):
            prior_valid = True
        canonical = outcome.get("canonical_observation")
        if (dict(binding) == exact and outcome.get("success") is True
                and outcome.get("status") == "specialist_accepted"
                and outcome.get("writes_farm_data") is True
                and isinstance(canonical, Mapping) and canonical.get("success") is True
                and len(canonical.get("observation_ids") or []) == 2
                and str(outcome.get("result_digest") or "") == str(authority.get("current_result_digest") or "")
                and hashlib.sha256(str(outcome.get("answer") or "").encode("utf-8")).hexdigest()
                    == str(authority.get("replacement_text_digest") or "")):
            current_valid = True
    return prior_valid and current_valid


def _event_store(action, identity, payload):
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    if action == "load":
        with connect_bounded_rootline_postgres(
                database_url=os.environ.get("DATABASE_URL")) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select review_json->'family_message_lifecycle'
                    from public.sam_live_stock_conversation_review_events
                    where event_source=%s and review_json->'family_message_lifecycle'->>'card_mission_id'=%s
                    order by created_at,review_event_id""", (EVENT_SOURCE, identity))
                return [row[0] for row in cursor.fetchall()]
    from modules.sales.sam_live_stock_launch_control import build_sam_live_stock_review_event, record_sam_live_stock_review_event
    event = build_sam_live_stock_review_event({"conversation_id": payload["card_mission_id"]}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "family_message_lifecycle"}, event_source=EVENT_SOURCE)
    event["review_event_id"] = identity; event["chatwoot_conversation_id"] = payload["card_mission_id"]
    event["review_json"] = {"family_message_lifecycle": dict(payload)}
    event["decision_json"] = {}; event["facts_json"] = {}; event["customer_message_excerpt"] = ""; event["sam_reply_excerpt"] = ""
    result, status = record_sam_live_stock_review_event(event,
        connect_factory=lambda: connect_bounded_rootline_postgres(
            database_url=os.environ.get("DATABASE_URL"), read_only=False))
    return {**result, "success": status < 400 and result.get("success") is True}


def load_family_lifecycle(card_mission_id: str, *, event_store=None):
    """Read one existing family lifecycle without creating a second store."""
    return list((event_store or _event_store)("load", str(card_mission_id or ""), None) or [])


def _send_telegram(chat_id, text, reply_markup=None, *, deadline_monotonic=None):
    if not _provider_deadline_available(deadline_monotonic):
        return {"success": False, "status": "family_message_cycle_deadline_deferred",
                "delivery_definitely_not_sent": True}
    from modules.sales.sam_live_stock_launch_control import _telegram_api
    token=str(os.environ.get("SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN") or os.environ.get("OOM_SAKKIE_TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:return {"success":False,"status":"telegram_token_not_configured","delivery_definitely_not_sent":True}
    body={"chat_id":str(chat_id),"text":str(text),"parse_mode":"HTML","disable_web_page_preview":True}
    if reply_markup:body["reply_markup"]=reply_markup
    try:response=_telegram_api(token,"sendMessage",body)
    except Exception:return {"success":False,"status":"telegram_delivery_ambiguous"}
    result=response.get("result") if isinstance(response,dict) else {}
    return {"success":response.get("ok") is True and bool((result or {}).get("message_id")),
            "telegram_message_id":str((result or {}).get("message_id") or "")}


def _edit_telegram(chat_id, message_id, text, reply_markup=None, *,
                   deadline_monotonic=None):
    if not _provider_deadline_available(deadline_monotonic):
        return {"success": False, "status": "family_message_cycle_deadline_deferred"}
    from modules.sales.sam_live_stock_launch_control import _telegram_api
    token = str(os.environ.get("SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN") or
                os.environ.get("OOM_SAKKIE_TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        return {"success": False, "status": "telegram_token_not_configured"}
    try:
        body={"chat_id": str(chat_id),
            "message_id": str(message_id), "text": str(text), "parse_mode": "HTML",
            "disable_web_page_preview": True}
        if reply_markup:body["reply_markup"]=reply_markup
        response = _telegram_api(token, "editMessageText", body)
    except Exception:
        return {"success": False, "status": "telegram_edit_ambiguous"}
    return {"success": response.get("ok") is True,
            "telegram_message_id": str(((response.get("result") or {}).get("message_id") if isinstance(response, dict) else "") or "")}


def _delete_telegram(chat_id, message_id):
    from modules.sales.sam_live_stock_launch_control import _telegram_api
    token = str(os.environ.get("SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN") or
                os.environ.get("OOM_SAKKIE_TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        return {"success": False, "status": "telegram_token_not_configured"}
    try:
        response = _telegram_api(token, "deleteMessage", {
            "chat_id": str(chat_id), "message_id": str(message_id)})
    except Exception:
        return {"success": False, "status": "telegram_delete_ambiguous"}
    return {"success": isinstance(response, dict) and response.get("ok") is True,
            "status": "telegram_message_deleted" if isinstance(response, dict)
            and response.get("ok") is True else "telegram_delete_unconfirmed"}
