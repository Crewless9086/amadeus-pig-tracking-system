"""Pure, evidence-bound SAM customer front-door interpretation.

This module deliberately performs no I/O.  Adapters must collect and bind the
Chatwoot chronology and pass the canonical Farm Knowledge snapshot explicitly.
The returned packet is a recommendation, not authority to send or mutate.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping


CONTRACT_VERSION = "sam_customer_front_door_v1"
CANONICAL_KNOWLEDGE_SHA256 = "aada28c4b0c92353bb83218c98b814ba17eea751019d57250b87218623ddc033"
SPECIALIST_LIVESTOCK = "livestock"
SPECIALIST_MEAT = "meat"
SPECIALIST_OWNER = "owner_exception"
SPECIALIST_FRONT_DOOR = "front_door"

_ACK_ONLY = re.compile(
    r"^(thanks|thank you|thank u|thx|dankie|baie dankie|ok|okay|cool|great|"
    r"lekker|reg so|all good|cheers|👍|👌|🙏|✅|❤️|❤|🙂|😊)[\s!.]*$",
    re.IGNORECASE,
)
_GREETING = re.compile(
    r"^(hi|hallo|hello|hey|hiya|howzit|morning|good morning|good afternoon|"
    r"good evening|môre|more|goeie môre|goeiemore|middag|aand|dag)(\b|[!,. ])",
    re.IGNORECASE,
)
_SMALL_TALK = re.compile(
    r"\b(how are you|how are things|hope you are well|hoe gaan dit|alles goed)\b",
    re.IGNORECASE,
)
_RESET = re.compile(
    r"\b(new question|different question|different thing|change topic|"
    r"not that|forget that|instead|ander vraag|iets anders)\b",
    re.IGNORECASE,
)
_PRICE = re.compile(r"\b(how much|price|cost|pricing|hoeveel|prys|kos)\b", re.IGNORECASE)
_VISIT = re.compile(
    r"\b(visit|come (?:to|see|by)|farm tour|open to public|visiting|"
    r"plaas besoek|kom kuier|kan ek kom)\b",
    re.IGNORECASE,
)
_LOCATION = re.compile(
    r"\b(where (?:are|is)|where.*based|where.*located|location|address|"
    r"waar is|waar.*gebaseer|ligging|adres)\b",
    re.IGNORECASE,
)
_WHAT_DO = re.compile(
    r"\b(what do you (?:guys )?do|what.*farm.*do|what do you sell|"
    r"tell me about.*farm|how does your farm work|how.*enquir|"
    r"wat doen julle|wat verkoop julle|hoe werk.*plaas)\b",
    re.IGNORECASE,
)
_STORY = re.compile(r"\b(farm story|your story|about amadeus|storie|julle storie)\b", re.IGNORECASE)
_LIVESTOCK = re.compile(
    r"\b(live pigs?|pigs?|livestock|piglets?|weaners?|growers?|finishers?|gilts?|"
    r"boars?|sows?|breeding pigs?|pigs? to raise|varke?|varkies?|speenvarke?|"
    r"soggies?|beertjies?)\b",
    re.IGNORECASE,
)
_MEAT = re.compile(
    r"\b(pork|pork meat|meat|half carcass|full carcass|carcass|freezer|"
    r"cut sets?|chops|belly|vleis|halwe karkas|karkas|vrieskas)\b",
    re.IGNORECASE,
)
_POST_REFERENCE = re.compile(
    r"\b(your post|the post|saw.*post|your ad|the ad|advert|facebook|"
    r"julle post|advertensie)\b",
    re.IGNORECASE,
)
_PROTECTED = re.compile(
    r"\b(book|reserve|order|confirm|available|availability|stock|deliver|"
    r"delivery|payment|paid|proof of payment|discount|exact address|"
    r"welfare|medical|medicine|provenance|slaughter date|collection time)\b",
    re.IGNORECASE,
)
_INTERNAL_TERMS = re.compile(
    r"\b(lane|auto_general|auto_specialist|sam livestock|sam meat|"
    r"confidence|blocker|governance|evidence packet|owner_handoff|"
    r"system prompt|taxonomy)\b",
    re.IGNORECASE,
)


def interpret_customer_front_door(
    evidence: Mapping[str, Any],
    farm_knowledge: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a deterministic, zero-authority front-door recommendation."""
    evidence = dict(evidence or {})
    knowledge = dict(farm_knowledge or {})
    identity, identity_errors = _identity(evidence)
    chronology = _chronology(evidence)
    latest = _latest_inbound(evidence, chronology)
    errors = list(identity_errors)
    if not latest["message_id"]:
        errors.append("latest_inbound_message_id_missing")
    elif identity["latest_inbound_message_id"] != latest["message_id"]:
        errors.append("latest_inbound_identity_mismatch")
    if chronology and chronology[-1]["message_id"] != latest["message_id"]:
        errors.append("chronology_not_current_at_latest_inbound")
    if chronology and chronology[-1]["role"] not in {"customer", "incoming"}:
        errors.append("chronology_tail_not_inbound")
    if chronology and _canonical_message_text(
        chronology[-1]["content"]
    ) != _canonical_message_text(latest["content"]):
        errors.append("latest_inbound_content_mismatch")
    message_ids = [row["message_id"] for row in chronology]
    if any(not item for item in message_ids) or len(message_ids) != len(set(message_ids)):
        errors.append("chronology_message_identity_invalid")
    timestamps = [row["created_at"] for row in chronology]
    if any(not item for item in timestamps) or timestamps != sorted(timestamps):
        errors.append("chronology_order_invalid")
    for row in chronology + [latest]:
        if any(row.get(field) != identity[field] for field in ("account_id", "inbox_id", "contact_id", "conversation_id")):
            errors.append("message_scope_identity_mismatch")
            break
    retained_scope_valid = _context_scope_matches(evidence.get("retained_context"), identity)
    campaign_scope_valid = _context_scope_matches(evidence.get("campaign_or_post"), identity)
    if not retained_scope_valid:
        errors.append("retained_context_scope_mismatch")
    if not campaign_scope_valid:
        errors.append("campaign_context_scope_mismatch")
    knowledge_errors = _knowledge_errors(knowledge)
    errors.extend(knowledge_errors)

    text = latest["content"].strip()
    safe_evidence = dict(evidence)
    if not retained_scope_valid:
        safe_evidence["retained_context"] = {}
    if not campaign_scope_valid:
        safe_evidence["campaign_or_post"] = {}
    retained = _retained_context(safe_evidence, chronology)
    campaign = _campaign_context(safe_evidence)
    attachment_context = _attachment_context(latest, evidence)
    intent = _interpret(text, retained, campaign)
    public_facts = _supported_public_facts(intent, knowledge)
    answer, clarification, owner_exception, specialist, should_reply, why = _decide(
        text=text,
        intent=intent,
        retained=retained,
        campaign=campaign,
        public_facts=public_facts,
        knowledge=knowledge,
    )

    if errors:
        answer = ""
        clarification = ""
        should_reply = False
        why = "identity_or_chronology_binding_failed"
        specialist = SPECIALIST_FRONT_DOOR
    if _INTERNAL_TERMS.search(answer) or _INTERNAL_TERMS.search(clarification):
        answer = ""
        clarification = ""
        should_reply = False
        why = "internal_taxonomy_leakage_blocked"

    reply = " ".join(part for part in (answer, clarification) if part).strip()
    packet = {
        "version": CONTRACT_VERSION,
        "front_door_interpretation": intent,
        "identity": identity,
        "identity_errors": errors,
        "idempotency_key": _idempotency_key(identity) if not errors else "",
        "valid_for_idempotency": not errors,
        "supported_public_answer": {
            "text": answer,
            "facts": public_facts,
            "knowledge_version": _clean(knowledge.get("version"), 120),
            "knowledge_status": _clean(knowledge.get("status"), 80),
        },
        "retained_conversation_context": retained,
        "campaign_or_post_context": campaign,
        "attachment_classification": attachment_context,
        "next_specialist_recommendation": specialist,
        "specialist_response_required": bool(
            not errors
            and not should_reply
            and specialist in {SPECIALIST_LIVESTOCK, SPECIALIST_MEAT}
            and why not in {"acknowledgement_or_natural_close"}
        ),
        "clarification": clarification,
        "clarification_count": 1 if clarification else 0,
        "protected_owner_exception": owner_exception,
        "should_reply": should_reply,
        "should_reply_why": why,
        "customer_reply": reply if should_reply else "",
        "zero_authority": {
            "performs_io": False,
            "may_send_customer_message": False,
            "may_call_chatwoot": False,
            "may_call_n8n": False,
            "may_mutate_conversation": False,
            "may_mark_read": False,
            "may_mutate_customer_or_farm": False,
            "may_quote_or_commit": False,
            "may_book_reserve_or_order": False,
        },
    }
    return packet


def _identity(evidence: Mapping[str, Any]) -> tuple[dict[str, str], list[str]]:
    raw = evidence.get("identity") if isinstance(evidence.get("identity"), Mapping) else {}
    fields = (
        "account_id", "inbox_id", "contact_id", "conversation_id",
        "latest_inbound_message_id",
    )
    identity = {}
    errors = []
    for field in fields:
        value = raw.get(field)
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            identity[field] = ""
            errors.append(f"{field}_invalid_type")
            continue
        exact = str(value)
        if not exact or exact != exact.strip() or len(exact) > 200:
            identity[field] = ""
            errors.append(f"{field}_invalid")
            continue
        identity[field] = exact
    return identity, errors


def _chronology(evidence: Mapping[str, Any]) -> list[dict[str, str]]:
    rows = evidence.get("chronology") if isinstance(evidence.get("chronology"), list) else []
    return [
        {
            "message_id": _clean(row.get("message_id") or row.get("id"), 120),
            "role": _clean(row.get("role"), 40).lower(),
            "content": _clean(row.get("content"), 1800),
            "created_at": _clean(row.get("created_at"), 80),
            **_scope(row),
        }
        for row in rows[-20:]
        if isinstance(row, Mapping)
    ]


def _latest_inbound(evidence: Mapping[str, Any], chronology: list[dict[str, str]]) -> dict[str, Any]:
    row = evidence.get("latest_inbound") if isinstance(evidence.get("latest_inbound"), Mapping) else {}
    if not row and chronology:
        row = chronology[-1]
    attachments = row.get("attachments") if isinstance(row.get("attachments"), list) else []
    return {
        "message_id": _clean(row.get("message_id") or row.get("id"), 120),
        "content": _clean(row.get("content"), 1800),
        "attachments": attachments[:8],
        **_scope(row),
    }


def _retained_context(evidence: Mapping[str, Any], chronology: list[dict[str, str]]) -> dict[str, Any]:
    supplied = evidence.get("retained_context") if isinstance(evidence.get("retained_context"), Mapping) else {}
    facts = supplied.get("facts") if isinstance(supplied.get("facts"), Mapping) else {}
    specialist = _specialist_hint(supplied.get("specialist") or supplied.get("sales_lane"))
    prior_customer_text = " ".join(
        row["content"] for row in chronology[:-1] if row["role"] in {"customer", "incoming"}
    )
    if not specialist:
        specialist = _specialist_from_text(prior_customer_text)
    reset = bool(_RESET.search(chronology[-1]["content"])) if chronology else False
    return {
        "specialist": specialist,
        "facts": {} if reset else _json_safe(facts),
        "historical_facts": _json_safe(facts) if reset else {},
        "summary": _clean(supplied.get("summary"), 800),
        "chronology": chronology,
        "context_reset": reset,
    }


def _campaign_context(evidence: Mapping[str, Any]) -> dict[str, Any]:
    raw = evidence.get("campaign_or_post") if isinstance(evidence.get("campaign_or_post"), Mapping) else {}
    text = " ".join(
        _clean(raw.get(field), 1200)
        for field in ("post_text", "product_focus", "call_to_action", "title")
    )
    return {
        "available": bool(text.strip()),
        "campaign_id": _clean(raw.get("campaign_id"), 120),
        "post_id": _clean(raw.get("post_id"), 120),
        "post_text": _clean(raw.get("post_text"), 1200),
        "product_focus": _clean(raw.get("product_focus"), 300),
        "specialist": _specialist_hint(raw.get("specialist")) or _specialist_from_text(text),
    }


def _attachment_context(latest: Mapping[str, Any], evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    supplied = evidence.get("attachment_classification")
    if isinstance(supplied, list):
        return [
            {
                "kind": _clean(item.get("kind"), 50).lower() or "file",
                "classification": _clean(item.get("classification"), 80).lower() or "unverified_attachment",
                "facts_trusted": False,
            }
            for item in supplied[:8] if isinstance(item, Mapping)
        ]
    result = []
    for item in latest.get("attachments", []):
        if not isinstance(item, Mapping):
            continue
        mime = _clean(item.get("content_type") or item.get("mime_type"), 100).lower()
        kind = _clean(item.get("kind") or item.get("file_type"), 50).lower()
        if not kind:
            kind = "image" if mime.startswith("image/") else "audio" if mime.startswith("audio/") else "file"
        result.append({"kind": kind, "classification": "unverified_attachment", "facts_trusted": False})
    return result


def _interpret(text: str, retained: Mapping[str, Any], campaign: Mapping[str, Any]) -> dict[str, Any]:
    reset = bool(_RESET.search(text))
    explicit = _specialist_from_text(text)
    prior = "" if reset else retained.get("specialist", "")
    # A vague response to an identified campaign is still campaign-bound.  The
    # customer must not have to repeat the product shown in the post.
    campaign_bound = bool(
        campaign.get("specialist")
        and (
            _POST_REFERENCE.search(text)
            or _PRICE.search(text)
            or re.search(r"\b(?:this|that|it|more info|information)\b", text, re.I)
        )
    )
    post = campaign.get("specialist", "") if campaign_bound else ""
    specialist = explicit or prior or post
    if _ACK_ONLY.fullmatch(text):
        kind = "acknowledgement_or_natural_close"
    elif _VISIT.search(text):
        kind = "farm_visit_request"
    elif _LOCATION.search(text):
        kind = "public_farm_location"
    elif _WHAT_DO.search(text):
        kind = "public_farm_activity"
    elif _STORY.search(text):
        kind = "public_farm_story"
    elif _PRICE.search(text):
        kind = "price_enquiry"
    elif explicit == SPECIALIST_LIVESTOCK:
        kind = "livestock_intent"
    elif explicit == SPECIALIST_MEAT:
        kind = "meat_intent"
    elif _POST_REFERENCE.search(text):
        kind = "post_reference"
    elif _GREETING.search(text) or _SMALL_TALK.search(text):
        kind = "greeting_or_small_talk"
    elif not text:
        kind = "attachment_or_empty"
    else:
        kind = "unclear_enquiry"
    mixed = bool(_LIVESTOCK.search(text) and _MEAT.search(text))
    return {
        "kind": "mixed_intent" if mixed else kind,
        "specialist_signal": "" if mixed else specialist,
        "used_prior_context": bool(prior and not explicit),
        "used_campaign_context": bool(post and not explicit and not prior),
        "context_reset": reset,
        "protected_signal": bool(_PROTECTED.search(text) or _VISIT.search(text)),
    }


def _supported_public_facts(intent: Mapping[str, Any], knowledge: Mapping[str, Any]) -> list[dict[str, str]]:
    profile = knowledge.get("public_profile") if isinstance(knowledge.get("public_profile"), Mapping) else {}
    menu = knowledge.get("product_menu") if isinstance(knowledge.get("product_menu"), list) else []
    facts = []
    if intent["kind"] == "public_farm_location":
        _add_fact(facts, "location_summary", profile.get("location_summary"), "public_profile.location_summary")
    elif intent["kind"] == "public_farm_story":
        _add_fact(facts, "one_line_story", profile.get("one_line_story"), "public_profile.one_line_story")
    elif intent["kind"] == "public_farm_activity":
        _add_fact(facts, "one_line_story", profile.get("one_line_story"), "public_profile.one_line_story")
        for index, item in enumerate(menu):
            if isinstance(item, Mapping):
                _add_fact(facts, f"product_menu.{item.get('key')}", item.get("summary"), f"product_menu[{index}].summary")
    return facts


def _add_fact(target: list[dict[str, str]], key: str, value: Any, path: str) -> None:
    cleaned = _clean(value, 500)
    if cleaned and cleaned.lower() != "unresolved":
        target.append({"key": key, "value": cleaned, "provenance": f"sam_farm_knowledge.{path}"})


def _decide(*, text, intent, retained, campaign, public_facts, knowledge):
    kind = intent["kind"]
    specialist = intent["specialist_signal"] or SPECIALIST_FRONT_DOOR
    answer = ""
    clarification = ""
    owner_exception = None
    should_reply = True
    why = "useful_front_door_response"

    if kind == "acknowledgement_or_natural_close":
        return "", "", None, specialist, False, "acknowledgement_or_natural_close"
    if kind == "farm_visit_request":
        answer = "Farm visits need to be confirmed by the farm first. I can pass your request on for review."
        owner_exception = {
            "type": "farm_visit_confirmation",
            "reason": "Visiting permission, date, time, and access details are protected.",
            "requested_customer_text": text,
        }
        return answer, "", owner_exception, SPECIALIST_OWNER, True, "protected_visit_request_requires_farm_confirmation"
    if kind.startswith("public_farm_"):
        if public_facts:
            answer = public_facts[0]["value"] if kind != "public_farm_activity" else _farm_activity_answer(public_facts)
            clarification = "What would you like help with?" if kind != "public_farm_location" else "What would you like to enquire about?"
        else:
            clarification = "What would you like to know about the farm?"
        return answer, clarification, None, SPECIALIST_FRONT_DOOR, True, "supported_public_farm_fact"
    if (
        kind == "greeting_or_small_talk"
        and (
            intent.get("used_campaign_context")
            or intent.get("used_prior_context")
        )
        and specialist in {SPECIALIST_LIVESTOCK, SPECIALIST_MEAT}
    ):
        # The specialist owns the warm response as well as the product answer;
        # this avoids a context-blind greeting that drops an established need.
        source = "prior" if intent.get("used_prior_context") else "campaign"
        return "", "", None, specialist, False, f"{source}_context_identified_for_specialist"
    if kind == "greeting_or_small_talk":
        answer = "Hi! I’m well, thank you." if _SMALL_TALK.search(text) else "Hi! Welcome to Amadeus Farm."
        if re.search(r"\b(môre|more|goeie|hoe gaan)\b", text, re.IGNORECASE):
            answer = "Môre! Dit gaan goed, dankie." if _SMALL_TALK.search(text) else "Môre! Welkom by Amadeus Farm."
            clarification = "Waarmee kan ek jou help?"
        else:
            clarification = "What can I help you with?"
        return answer, clarification, None, SPECIALIST_FRONT_DOOR, True, "warm_first_response"
    if kind in {"livestock_intent", "meat_intent"}:
        if intent["protected_signal"]:
            owner_exception = {
                "type": "protected_customer_detail",
                "reason": "Availability, delivery, payment, booking, or commitment needs supported specialist or farm confirmation.",
                "requested_customer_text": text,
            }
        return "", "", owner_exception, specialist, False, "transfer_with_retained_context"
    if kind == "price_enquiry":
        if specialist in {SPECIALIST_LIVESTOCK, SPECIALIST_MEAT}:
            return "", "", None, specialist, False, "price_context_identified_for_specialist"
        clarification = "Do you mean live pigs or pork?"
        if intent["protected_signal"]:
            owner_exception = {
                "type": "protected_customer_detail",
                "reason": "Price, availability, or delivery needs supported specialist or farm confirmation.",
                "requested_customer_text": text,
            }
        return "", clarification, owner_exception, SPECIALIST_FRONT_DOOR, True, "price_subject_still_unclear"
    if kind == "post_reference":
        if specialist in {SPECIALIST_LIVESTOCK, SPECIALIST_MEAT}:
            return "", "", None, specialist, False, "post_context_identified_for_specialist"
        clarification = "What would you like to know about the post?"
        return "", clarification, None, SPECIALIST_FRONT_DOOR, True, "post_reference_needs_one_clarification"
    if kind == "mixed_intent":
        clarification = "Are you asking about live pigs, pork, or both?"
        return "", clarification, None, SPECIALIST_FRONT_DOOR, True, "mixed_intent_needs_one_clarification"
    if intent["protected_signal"]:
        owner_exception = {
            "type": "protected_customer_detail",
            "reason": "Availability, delivery, payment, booking, or commitment needs supported specialist or farm confirmation.",
            "requested_customer_text": text,
        }
        clarification = "Is this about live pigs or pork?"
        return "", clarification, owner_exception, SPECIALIST_OWNER, True, "protected_detail_needs_subject_and_confirmation"
    if kind == "attachment_or_empty":
        clarification = "What would you like help with?"
        return "", clarification, None, SPECIALIST_FRONT_DOOR, True, "no_supported_text_intent"
    clarification = "What can I help you with today?"
    return "", clarification, None, SPECIALIST_FRONT_DOOR, True, "unclear_intent_needs_one_clarification"


def _farm_activity_answer(facts: list[dict[str, str]]) -> str:
    story = next((fact["value"] for fact in facts if fact["key"] == "one_line_story"), "")
    keys = {fact["key"] for fact in facts}
    activities = []
    if "product_menu.live_sales" in keys:
        activities.append("live pig enquiries")
    if "product_menu.meat_sales_guarded" in keys:
        activities.append("pre-booked pork freezer options")
    if "product_menu.farm_info" in keys:
        activities.append("general farm information")
    if activities:
        return f"We are a small farm helping customers with {', '.join(activities[:-1])}{' and ' if len(activities) > 1 else ''}{activities[-1]}."
    return story


def _specialist_from_text(text: str) -> str:
    live = bool(_LIVESTOCK.search(text or ""))
    meat = bool(_MEAT.search(text or ""))
    if live and not meat:
        return SPECIALIST_LIVESTOCK
    if meat and not live:
        return SPECIALIST_MEAT
    return ""


def _specialist_hint(value: Any) -> str:
    text = _clean(value, 100).lower()
    if text in {"livestock", "live_stock", "live_stock_sales", "live pigs", "live_pigs"}:
        return SPECIALIST_LIVESTOCK
    if text in {"meat", "meat_sales", "meat_preorder", "pork"}:
        return SPECIALIST_MEAT
    return ""


def _idempotency_key(identity: Mapping[str, str]) -> str:
    raw = "|".join(identity.get(key, "") for key in (
        "account_id", "inbox_id", "contact_id", "conversation_id", "latest_inbound_message_id",
    ))
    return "sam-front-door:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _scope(row: Mapping[str, Any]) -> dict[str, str]:
    raw = row.get("identity") if isinstance(row.get("identity"), Mapping) else row
    return {
        field: str(raw.get(field)) if isinstance(raw.get(field), (str, int)) and not isinstance(raw.get(field), bool) else ""
        for field in ("account_id", "inbox_id", "contact_id", "conversation_id")
    }


def _context_scope_matches(value: Any, identity: Mapping[str, str]) -> bool:
    if not isinstance(value, Mapping) or not value:
        return True
    if not _clean(value.get("source"), 120) or not _clean(value.get("version"), 80):
        return False
    scope = _scope(value)
    return all(scope[field] == identity[field] for field in scope)


def _knowledge_errors(knowledge: Mapping[str, Any]) -> list[str]:
    profile = knowledge.get("public_profile") if isinstance(knowledge.get("public_profile"), Mapping) else {}
    errors = []
    if knowledge.get("status") != "draft_owner_editable":
        errors.append("farm_knowledge_status_not_canonical_draft")
    if not isinstance(knowledge.get("version"), str) or not knowledge.get("version"):
        errors.append("farm_knowledge_version_missing")
    if profile.get("farm_name") != "Amadeus Farm":
        errors.append("farm_knowledge_identity_mismatch")
    digest = hashlib.sha256(
        json.dumps(knowledge, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()
    if digest != CANONICAL_KNOWLEDGE_SHA256:
        errors.append("farm_knowledge_snapshot_digest_mismatch")
    return errors


def _json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return {}


def _clean(value: Any, limit: int = 300) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _canonical_message_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
