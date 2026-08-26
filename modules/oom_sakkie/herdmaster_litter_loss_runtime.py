"""Telegram adapter for exact active-litter piglet-loss operations."""
from __future__ import annotations

import json
import os
from typing import Mapping

from services.database_service import DATABASE_URL_ENV
from modules.oom_sakkie.gateway_authority import validates_gateway_owner_authority
from modules.oom_sakkie.protected_action_claims import create_claim
from modules.pig_weights.herdmaster_litter_first_treatment_action import (
    load_first_treatment_evidence,
)
from modules.pig_weights.herdmaster_litter_loss_action import (
    ACTION_KIND,
    prepare_litter_loss_preview,
    render_litter_loss_preview,
)


def handle_litter_loss_message(
    parsed: Mapping,
    authority,
    *,
    connect_factory=None,
    evidence_loader=None,
    history_loader=None,
    retained_context_loader=None,
    claim_creator=None,
):
    parsed = dict(parsed or {})
    semantic = (
        parsed.get("semantic")
        if isinstance(parsed.get("semantic"), Mapping)
        else {}
    )
    facts = semantic.get("litter_piglet_loss")
    if (
        semantic.get("intent") != "record_litter_piglet_deaths"
        or not isinstance(facts, Mapping)
    ):
        return {"handled": False, "status": "litter_loss_not_applicable"}, 200
    owner = str(parsed.get("telegram_user_id") or "")
    chat = str(parsed.get("telegram_chat_id") or "")
    if (
        not validates_gateway_owner_authority(authority)
        or not owner
        or owner != chat
        or "mortality_confirmation"
        not in frozenset(getattr(authority, "capabilities", ()))
    ):
        return {
            "handled": True,
            "success": False,
            "status": "litter_loss_authority_required",
            "writes_farm_data": False,
        }, 403
    provider_id = str(parsed.get("provider_message_id") or "").strip()
    if not provider_id:
        return {
            "handled": True,
            "success": False,
            "status": "litter_loss_provider_identity_required",
            "writes_farm_data": False,
        }, 409
    try:
        canonical = (evidence_loader or load_first_treatment_evidence)(
            connect_factory=connect_factory
        )
        history = (history_loader or load_litter_loss_history)(
            owner,
            chat,
            connect_factory=connect_factory,
        )
        retained = (retained_context_loader or load_retained_litter_loss_context)(
            owner,
            chat,
            connect_factory=connect_factory,
        )
    except Exception:
        return {
            "handled": True,
            "success": False,
            "status": "litter_loss_evidence_unavailable",
            "writes_farm_data": False,
        }, 503

    action_facts = dict(facts)
    action_facts["source_event_ids"] = [provider_id]
    matching_retained = _matching_retained_context(action_facts, retained)
    if matching_retained:
        action_facts = {
            **matching_retained,
            **{
                key: value
                for key, value in action_facts.items()
                if value not in (None, "", [])
            },
            "source_event_ids": sorted(
                set(matching_retained.get("source_event_ids") or []) | {provider_id}
            ),
        }
    if semantic.get("continuation") is True and not action_facts.get("event_date"):
        prior_date = _continuation_event_date(action_facts, history)
        if prior_date:
            action_facts["event_date"] = prior_date

    reserved = {
        pig_id
        for row in history
        if row.get("status") in {"active", "executing"}
        for pig_id in row.get("pig_ids") or []
    }
    prepared = prepare_litter_loss_preview(
        action_facts, canonical, reserved_pig_ids=reserved
    )
    if prepared.get("success") is not True:
        question = str(prepared.get("question") or "")
        mission = "OOM-HERDMASTER-LITTER-LOSS-INPUT-" + provider_id
        return {
            "handled": True,
            **prepared,
            "status": "waiting_for_input" if question else prepared["status"],
            "answer": question
            or "The litter-loss facts conflict with current active membership. Nothing was recorded.",
            "clarification_question": question,
            "question_count": 1 if question else 0,
            "mission_id": mission,
            "card_mission_id": mission,
            "writes_farm_data": False,
        }, 200 if question else 409
    preview = prepared["preview"]
    mission = "OOM-" + preview["operation_id"]
    claim = (claim_creator or create_claim)(
        action_kind=ACTION_KIND,
        owner_user_id=owner,
        private_chat_id=chat,
        mission_id=mission,
        provider_message_id=provider_id,
        evidence_generation=str(canonical.get("evidence_generation") or ""),
        preview_payload={
            **preview,
            "owner_user_id": owner,
            "private_chat_id": chat,
        },
        connect_factory=connect_factory,
    )
    return {
        "handled": True,
        "success": True,
        "status": "litter_piglet_deaths_preview_ready",
        "answer": render_litter_loss_preview(preview),
        "question_count": 0,
        "mission_id": mission,
        "card_mission_id": mission,
        "callback_token": claim["callback_token"],
        "preview_digest": claim["preview_digest"],
        "action_kind": ACTION_KIND,
        "reply_markup": {
            "inline_keyboard": [
                [
                    {
                        "text": "Confirm and record",
                        "callback_data": f"oompa:{claim['callback_token']}:confirm",
                    },
                    {
                        "text": "Change",
                        "callback_data": f"oompa:{claim['callback_token']}:change",
                    },
                    {
                        "text": "Cancel",
                        "callback_data": f"oompa:{claim['callback_token']}:cancel",
                    },
                ]
            ]
        },
        "writes_farm_data": False,
    }, 200


def load_litter_loss_history(owner, chat, *, connect_factory=None):
    with _connect(connect_factory) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute(
                """select status,preview_payload,provider_message_id,created_at
                from app_private.oom_protected_action_claims
                where action_kind=%s and owner_user_id=%s and private_chat_id=%s
                order by created_at desc""",
                (ACTION_KIND, str(owner), str(chat)),
            )
            rows = cursor.fetchall()
    return [
        {
            "status": str(row[0] or ""),
            **dict(row[1] or {}),
            "provider_message_id": str(row[2] or ""),
            "created_at": row[3],
        }
        for row in rows
        if isinstance(row[1], dict)
    ]


def load_retained_litter_loss_context(owner, chat, *, connect_factory=None):
    """Recover original provider IDs/facts after a manager sex-only question."""
    with _connect(connect_factory) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute(
                """select evidence_refs
                from app_private.oom_manager_cases
                where dedupe_key like 'herdmaster:retained-litter-loss:%'
                  and status=any(%s)
                order by updated_at desc limit 20""",
                (["open", "delegated", "waiting_reassessment", "exception"],),
            )
            cases = [row[0] for row in cursor.fetchall()]
            result = []
            for refs in cases:
                refs = list(refs or [])
                provider_ids = [
                    str(value).split(":", 1)[1]
                    for value in refs
                    if str(value).startswith("provider_message:")
                ]
                incident = next(
                    (
                        str(value).split(":", 1)[1]
                        for value in refs
                        if str(value).startswith("incident_date:")
                    ),
                    "",
                )
                if not provider_ids or not incident:
                    continue
                cursor.execute(
                    """select review_json->'herdmaster_health_loss'
                    from public.sam_live_stock_conversation_review_events
                    where event_source='oom_sakkie_herdmaster_health_loss_runtime'
                      and review_json->'herdmaster_health_loss'->>'provider_message_id'=any(%s)
                    order by created_at""",
                    (provider_ids,),
                )
                payloads = [
                    dict(row[0] or {})
                    for row in cursor.fetchall()
                    if row and isinstance(row[0], dict)
                ]
                if not payloads or any(
                    str(row.get("owner_user_id") or "") != str(owner)
                    or str(row.get("chat_id") or "") != str(chat)
                    for row in payloads
                ):
                    continue
                counts = {
                    int(match.group(1))
                    for row in payloads
                    for match in [
                        __import__("re").search(
                            r"\b(\d+)\s+kleintjies\s+dood\b",
                            str(row.get("owner_text_verbatim") or ""),
                            __import__("re").I,
                        )
                    ]
                    if match
                }
                if len(counts) == 1:
                    result.append(
                        {
                            "sow_ref": "Linda",
                            "event_date": incident,
                            "count": next(iter(counts)),
                            "source_event_ids": sorted(provider_ids),
                        }
                    )
    return result


def _matching_retained_context(facts, retained):
    sow = str(facts.get("sow_ref") or "").casefold()
    count = facts.get("count")
    event_date = str(facts.get("event_date") or "")
    matches = [
        row
        for row in retained
        if (not sow or sow == str(row.get("sow_ref") or "").casefold())
        and (count is None or count == row.get("count"))
        and (not event_date or event_date == str(row.get("event_date") or ""))
    ]
    return dict(matches[0]) if len(matches) == 1 else None


def _continuation_event_date(facts, history):
    sow = str(facts.get("sow_ref") or "").casefold()
    litter = str(facts.get("litter_ref") or "").casefold()
    matches = [
        row
        for row in history
        if (not sow or sow in {
            str(row.get("sow_name") or "").casefold(),
            str(row.get("sow_tag_number") or "").casefold(),
            str(row.get("sow_pig_id") or "").casefold(),
        })
        and (not litter or litter == str(row.get("litter_id") or "").casefold())
        and str(row.get("event_date") or "")
    ]
    return str(matches[0]["event_date"]) if matches else ""


def _connect(connect_factory=None):
    database_url = str(os.getenv(DATABASE_URL_ENV) or "")
    if connect_factory is not None:
        return connect_factory(database_url)
    import psycopg

    return psycopg.connect(database_url, connect_timeout=10)
