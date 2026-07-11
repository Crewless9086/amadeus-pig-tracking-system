"""Deterministic input understanding before SAM Live Stock planning."""

from __future__ import annotations

import re
from typing import Any, Callable, Mapping


AFRIKAANS_WORDS = {
    "waar", "julle", "vark", "varke", "varkie", "varkies", "prys", "hoeveel",
    "afhaal", "aflewer", "môre", "vrydag", "week", "foto", "fotos",
    "soek", "wil", "kan", "asseblief", "dankie", "groot", "klein", "boer",
}
ENGLISH_WORDS = {
    "where", "price", "pig", "pigs", "piglet", "piglets", "collect", "delivery",
    "tomorrow", "friday", "week", "photo", "photos", "want", "need", "please",
    "thanks", "business", "available", "stock", "quote",
}
ACK_EMOJI_PATTERN = re.compile(r"^[\s👍👌🙏✅❤️❤🙂😊👏]+$")


def understand_live_stock_inbound(
    inbound: Mapping[str, Any],
    payload: Mapping[str, Any] | None = None,
    *,
    voice_transcriber: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]] | None = None,
    image_classifier: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    inbound = dict(inbound or {})
    payload = dict(payload or {})
    original_text = clean_text(inbound.get("content"), 1800)
    attachments = normalize_attachments(payload)
    voice = _voice_packet(attachments, payload, voice_transcriber)
    images = _image_packets(attachments, payload, image_classifier)
    effective_text = original_text
    if not effective_text and voice.get("transcript"):
        effective_text = clean_text(voice.get("transcript"), 1800)
    language = detect_language(effective_text)
    intent = classify_message_intent(effective_text, attachments)
    return {
        "version": "sam_live_stock_input_understanding_v1",
        "original_text": original_text,
        "effective_text": effective_text,
        "language": language,
        "message_intent": intent,
        "emoji_only": bool(effective_text and ACK_EMOJI_PATTERN.fullmatch(effective_text)),
        "attachments": attachments,
        "voice": voice,
        "images": images,
        "requires_media_review": bool(
            (voice.get("present") and not voice.get("transcript"))
            or any(item.get("classification") in {"unknown_image", "payment_proof_possible"} for item in images)
        ),
    }


def normalize_attachments(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
    normalized = []
    for item in rows[:8]:
        if not isinstance(item, Mapping):
            continue
        kind = clean_text(
            item.get("file_type") or item.get("type") or item.get("attachment_type") or item.get("content_type"),
            80,
        ).lower()
        content_type = clean_text(item.get("content_type") or item.get("mime_type"), 100).lower()
        if not kind:
            if content_type.startswith("audio/"):
                kind = "audio"
            elif content_type.startswith("image/"):
                kind = "image"
            else:
                kind = "file"
        normalized.append({
            "kind": kind,
            "content_type": content_type,
            "file_name": clean_text(item.get("file_name") or item.get("filename"), 160),
            "url": clean_text(item.get("data_url") or item.get("file_url") or item.get("url"), 700),
        })
    return normalized


def detect_language(text: str) -> str:
    words = set(re.findall(r"[a-zA-ZÀ-ÿ]+", str(text or "").lower()))
    if not words:
        return "nonverbal"
    afrikaans = len(words & AFRIKAANS_WORDS)
    english = len(words & ENGLISH_WORDS)
    if afrikaans and english:
        return "mixed_afrikaans_english"
    if afrikaans:
        return "afrikaans"
    return "english"


def classify_message_intent(text: str, attachments: list[Mapping[str, Any]] | None = None) -> str:
    lower = clean_text(text, 1800).lower()
    attachments = list(attachments or [])
    if lower and ACK_EMOJI_PATTERN.fullmatch(lower):
        return "social_acknowledgement"
    if not lower and any(item.get("kind") in {"audio", "voice"} for item in attachments):
        return "voice_note"
    if not lower and any(item.get("kind") == "image" for item in attachments):
        return "image_only"
    rules = [
        ("job_request", r"\b(job|work|hiring|employment|cv|werk|werksgeleentheid)\b"),
        ("location_question", r"\b(where|location|province|address|waar|ligging|adres|provinsie)\b"),
        ("business_question", r"\b(business|advert|ad|about you|what do you do|besigheid|advertensie|vertel my meer)\b"),
        ("picture_request", r"\b(pic|pics|picture|pictures|photo|photos|foto|fotos|prentjie)\b"),
        ("delivery_question", r"\b(deliver|delivery|transport|aflewer|vervoer)\b"),
        ("price_question", r"\b(price|cost|how much|quote|prys|hoeveel|kwotasie)\b|\br\s?\d+"),
        ("breeding_request", r"\b(breed|breeding|boar|sow|gilt|teel|beer|sog)\b"),
        ("buying_intent", r"\b(want|need|take|buy|looking for|soek|wil|koop|vat)\b"),
        ("timing_or_collection", r"\b(today|tomorrow|friday|monday|collect|pickup|vandag|m[oô]re|vrydag|maandag|afhaal)\b"),
        ("order_change", r"\b(another|one more|change|add|remove|instead|nog een|verander|voeg by)\b"),
        ("availability_question", r"\b(available|availability|stock|have any|beskikbaar|voorraad)\b"),
        ("social_close", r"\b(thanks|thank you|bye|dankie|totsiens)\b"),
    ]
    for intent, pattern in rules:
        if re.search(pattern, lower):
            return intent
    return "unclear" if lower else "empty"


def _voice_packet(attachments, payload, transcriber):
    voice_attachment = next((item for item in attachments if item.get("kind") in {"audio", "voice"}), None)
    attrs = payload.get("content_attributes") if isinstance(payload.get("content_attributes"), Mapping) else {}
    transcript = clean_text(attrs.get("transcript") or attrs.get("voice_transcript"), 1800)
    status = "not_present"
    if voice_attachment:
        status = "transcript_supplied" if transcript else "transcription_required"
        if not transcript and transcriber:
            result = dict(transcriber(voice_attachment, payload) or {})
            transcript = clean_text(result.get("transcript"), 1800)
            status = "transcribed" if transcript else clean_text(result.get("status"), 80) or "transcription_failed"
    return {"present": bool(voice_attachment), "status": status, "transcript": transcript, "stores_audio": False}


def _image_packets(attachments, payload, classifier):
    packets = []
    caption = clean_text(payload.get("content") or payload.get("message"), 500).lower()
    for item in attachments:
        if item.get("kind") != "image":
            continue
        classification = "unknown_image"
        if re.search(r"\b(pop|proof|payment|paid|eft)\b", caption):
            classification = "payment_proof_possible"
        elif re.search(r"\b(pig|piglet|weaner|vark|varkie)\b", caption):
            classification = "customer_pig_image"
        elif re.search(r"\b(ad|advert|screenshot|advertensie)\b", caption):
            classification = "advert_screenshot"
        if classifier:
            result = dict(classifier(item, payload) or {})
            classification = clean_text(result.get("classification"), 80) or classification
        packets.append({**item, "classification": classification, "facts_trusted": False})
    return packets


def clean_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").strip().split())[:limit]
