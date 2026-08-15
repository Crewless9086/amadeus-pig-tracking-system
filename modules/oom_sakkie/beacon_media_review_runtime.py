"""Owner-bound private album Library/public-use review for Oom Sakkie."""
from __future__ import annotations

import html
import os
from typing import Mapping

from modules.beacon.media_intake import (
    ALBUM_REVIEW_CONTRACT_VERSION,
    latest_private_album_review,
    private_album_review,
    record_media_group_review,
    telegram_media_owner_binding,
)
from modules.oom_sakkie.protected_action_claims import CALLBACK_PREFIX, create_claim

ACTION_KIND="beacon_media_review"
ZERO={"publishes":False,"schedules":False,"customer_sends":False,"spends_money":False,
      "writes_farm_data":False,"hardware_commands":0,"meta_calls":0,"n8n_mutations":0,
      "google_sheets_mutations":0}


def present_private_media_review(parsed, *, album_loader=latest_private_album_review,
                                 claim_creator=create_claim):
    packet,status=album_loader(owner_user_id=parsed.get("telegram_user_id"),
        private_chat_id=parsed.get("telegram_chat_id"))
    if status>=400 or packet.get("success") is not True:
        return {"handled":True,"success":False,"status":packet.get("status") or "private_album_review_unavailable",
                "answer":"BEACON could not load a complete private album for review. Nothing was approved or published.",**ZERO},status
    try:
        return _present_packet(packet,parsed,claim_creator=claim_creator)
    except Exception as exc:
        return {"handled":True,"success":False,"status":"private_media_review_claim_contained",
            "answer":"BEACON could not safely bind the private review buttons. Nothing was approved or published.",
            "error_type":exc.__class__.__name__,**ZERO},503


def _present_packet(packet, parsed, *, claim_creator=create_claim):
    if packet.get("contract_version")!=ALBUM_REVIEW_CONTRACT_VERSION:
        raise ValueError("private_album_review_contract_invalid")
    language=str((parsed.get("semantic") or {}).get("language") or "en")
    af=language in {"af","mixed"}
    library=packet.get("library_state")
    if library!="accepted":
        decision_type="library"
        approve_event,decline_event="library_accepted","library_rejected"
        approve_label,decline_label=("Aanvaar in Privaat Biblioteek","Weier album vir Privaat Biblioteek") if af else ("Accept into Private Library","Decline album for Private Library")
        decline_reason="Owner selected: not suitable for the private Library." if not af else "Eienaar se keuse: nie geskik vir die privaat Biblioteek nie."
        boundary=("Biblioteek-aanvaarding hou die album privaat en gee geen Publieke Gebruik-, Veldtoghersiening- of Publikasiegesag nie."
            if af else "Library acceptance keeps the album private and grants no Public Use, Campaign Review or Publication authority.")
    else:
        decision_type="public_use"
        approve_event,decline_event="public_use_approved","public_use_revoked"
        approve_label,decline_label=("Keur Publieke Gebruik goed","Weier — hou privaat") if af else ("Approve Public Use","Decline — keep private")
        decline_reason="Owner selected: keep this album private." if not af else "Eienaar se keuse: hou hierdie album privaat."
        boundary=(("Publieke Gebruik is beperk tot latere organiese plaasbewustheid-hersiening. "
            "Dit gee geen veldtog-, skedulering-, publikasie-, klantkontak- of bestedingsgesag nie.") if af else
            ("Public-use approval is limited to later organic farm-awareness review. "
             "It grants no campaign approval, scheduling, publication, customer contact or spend."))
    preview={"contract_version":ALBUM_REVIEW_CONTRACT_VERSION,
        "decision_type":decision_type,"intake_group_id":packet["intake_group_id"],
        "album_digest":packet["album_digest"],"stored_count":packet["stored_count"],
        "owner_context":packet.get("owner_context") or "","approve_event":approve_event,
        "decline_event":decline_event,"decline_reason":decline_reason,"language":language,
        "public_use_eligible":packet.get("public_use_eligible") is True,
        "ordered_assets":[{"position":item["album_position"],"binary_asset_id":item["binary_asset_id"],
          "content_sha256":item["content_sha256"],
          "understanding_event_id":item.get("understanding_event_id") or "",
          "library_event_id":item.get("library_event_id") or ""}
          for item in packet.get("ordered_media") or []]}
    if decision_type=="public_use" and not preview["public_use_eligible"]:
        return {"handled":True,"success":True,"status":"private_media_public_use_checks_pending",
            "specialist":"BEACON_MEDIA","mission_id":packet["intake_group_id"],
            "card_mission_id":packet["intake_group_id"]+":PUBLIC-USE",
            "answer":((f"<b>BEACON — PRIVAAT MEDIA-HERSIENING</b>\n\n{packet['stored_count']} geordende foto's: {html.escape(str(packet.get('owner_context') or ''))}.\nPublieke Gebruik bly gesluit totdat elke privaatheid-, dierewelsyn-, handelsmerk-, Meta-bewustheid- en lêerintegriteitskontrole positief bewys is. Niks is goedgekeur of gepubliseer nie.") if af else
                f"<b>BEACON — PRIVATE MEDIA REVIEW</b>\n\n{packet['stored_count']} ordered photos: {html.escape(str(packet.get('owner_context') or ''))}.\nPublic Use remains locked until every privacy, animal-welfare, brand, Meta-awareness and file-integrity check is affirmatively proven. Nothing was approved or published."),
            "reply_markup":{"inline_keyboard":[]},**ZERO},200
    claim=claim_creator(action_kind=ACTION_KIND,
        owner_user_id=str(parsed.get("telegram_user_id") or ""),
        private_chat_id=str(parsed.get("telegram_chat_id") or ""),
        mission_id=packet["intake_group_id"]+":"+decision_type.upper(),
        provider_message_id=str(parsed.get("provider_message_id") or ""),
        evidence_generation=packet["album_digest"],preview_payload=preview,ttl_minutes=10080)
    base_url=str(os.getenv("AMADEUS_BACKEND_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if not base_url.startswith(("https://","http://")):
        raise RuntimeError("private_contact_sheet_url_unavailable")
    buttons={"inline_keyboard":[[
        {"text":approve_label,"callback_data":f"{CALLBACK_PREFIX}{claim['callback_token']}:confirm"},
        {"text":decline_label,"callback_data":f"{CALLBACK_PREFIX}{claim['callback_token']}:cancel"},
    ],[{"text":"Bekyk privaat kontakblad" if af else "View private contact sheet",
        "url":base_url+"/sales/beacon-media#beacon_intake_contact_sheet"}]]}
    answer=((f"<b>BEACON — PRIVAAT MEDIA-HERSIENING</b>\n\n"
        f"{packet['stored_count']} geordende privaat foto's. Behoue konteks: {html.escape(str(packet.get('owner_context') or ''))}.\n"
        f"Besluit nou: {approve_label} of {decline_label}.\n{boundary}\n"
        "Gebruik Bekyk privaat kontakblad om al die foto's voor die besluit te sien.") if af else
        (f"<b>BEACON — PRIVATE MEDIA REVIEW</b>\n\n"
        f"{packet['stored_count']} ordered private photos. Retained context: {html.escape(str(packet.get('owner_context') or ''))}.\n"
        f"Decision now: {approve_label} or {decline_label}.\n{boundary}\n"
        "Use View private contact sheet to inspect every photo before deciding."))
    return {"handled":True,"success":True,"status":"private_media_review_presented",
        "specialist":"BEACON_MEDIA","mission_id":packet["intake_group_id"]+":"+decision_type.upper(),
        "card_mission_id":packet["intake_group_id"]+":"+decision_type.upper(),
        "answer":answer,"reply_markup":buttons,"callback_token":claim["callback_token"],
        "review_packet":packet,**ZERO},200


def execute_private_media_review(claimed, parsed, *, recorder=record_media_group_review,
                                 packet_loader=private_album_review, claim_creator=create_claim):
    preview=claimed.get("preview_payload") if isinstance(claimed.get("preview_payload"),Mapping) else {}
    assets=preview.get("ordered_assets") if isinstance(preview.get("ordered_assets"),list) else []
    expected_mission=f"{preview.get('intake_group_id')}:{str(preview.get('decision_type') or '').upper()}"
    coherent=(preview.get("contract_version")==ALBUM_REVIEW_CONTRACT_VERSION
        and str(claimed.get("mission_id") or "")==expected_mission
        and str(claimed.get("evidence_generation") or "")==str(preview.get("album_digest") or "")
        and int(preview.get("stored_count") or 0)==len(assets)>0
        and [item.get("position") for item in assets]==list(range(1,len(assets)+1))
        and all(len(str(item.get("content_sha256") or ""))==64
          and str(item.get("understanding_event_id") or "") for item in assets))
    if not coherent:
        return {"success":False,"status":"private_media_review_binding_invalid",**ZERO},409
    selected=str(claimed.get("selected_action") or "approve")
    event_type=preview["decline_event"] if selected=="decline" else preview["approve_event"]
    notes=(str(preview.get("decline_reason") or "Owner declined this exact album decision.")
        if selected=="decline" else "Owner approved this exact album decision through the bound Telegram review button.")
    binding=telegram_media_owner_binding(parsed.get("telegram_user_id"),parsed.get("telegram_chat_id"))
    principal=binding["owner_principal"]
    decision={"contract_version":ALBUM_REVIEW_CONTRACT_VERSION,"album_digest":preview["album_digest"],
        "event_type":event_type,"notes":notes,
        "subject_owner_principal":binding["owner_principal"],"subject_chat_hmac":binding["chat_hmac"],
        "owner_action_id":str(claimed.get("callback_token") or claimed.get("preview_digest") or ""),
        "expected_predecessors":{item["binary_asset_id"]:item.get("library_event_id") or ""
          for item in preview.get("ordered_assets") or []}}
    result,status=recorder(preview["intake_group_id"],decision,principal)
    if status>=400 or result.get("success") is not True:
        return {**result,**ZERO},status
    packet,packet_status=packet_loader(preview["intake_group_id"])
    af=str(preview.get("language") or "") in {"af","mixed"}
    answer=((f"BEACON het {event_type.replace('_',' ')} presies een keer vir al {preview['stored_count']} geordende foto's aangeteken. "
        "Biblioteek, Publieke Gebruik, Veldtoghersiening en Publikasie bly apart. Niks is gepubliseer, geskeduleer, gestuur of bestee nie.") if af else
        (f"BEACON recorded {event_type.replace('_',' ')} for all {preview['stored_count']} ordered photos exactly once. "
        "Library, Public Use, Campaign Review and Publication remain separate. Nothing was published, scheduled, sent or spent."))
    output={"success":True,"status":"private_media_review_recorded","answer":answer,
        "specialist":"BEACON_MEDIA","mission_id":claimed["mission_id"],
        "card_mission_id":claimed["mission_id"],"reply_markup":{"inline_keyboard":[]},
        "owner_visible_completion_policy":"verified_edit_or_new_message",**ZERO,**result}
    if event_type=="library_accepted" and packet_status<400:
        try:
            follow,follow_status=_present_packet(packet,parsed,claim_creator=claim_creator)
        except Exception:
            follow,follow_status={},503
        if follow_status<400 and follow.get("callback_token"):
            output.update({"answer":answer+"\n\n"+follow["answer"],"reply_markup":follow["reply_markup"],
                "callback_token":follow["callback_token"]})
        else:
            output["answer"] += " Public Use remains undecided and can be reviewed later from the same canonical album."
    return output,status
