"""Retained farrowing facts on the existing conversation and claim tables."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os

from modules.pig_weights.herdmaster_farrowing_litter_intake import ACTION_KIND

EVENT_SOURCE = "oom_sakkie_farrowing_litter"
CONTEXT_KEY = "farrowing_litter"
CONTEXT_SECONDS = 6 * 3600


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def source_time(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp if stamp.tzinfo else None
    except (TypeError, ValueError):
        return None


def source_order(row):
    provider = str(row.get("provider_message_id") or "")
    return (source_time(row.get("provider_timestamp")) or datetime.min.replace(tzinfo=timezone.utc),
            int(provider) if provider.isdecimal() else 0)


class FarrowingContextError(ValueError):
    def __init__(self, status):
        self.status = status
        super().__init__(status)


def select_context(rows, parsed, supplied=None):
    """Select a single current conversation without falling back past new facts."""
    stamp = source_time(parsed.get("provider_timestamp"))
    if not stamp:
        raise FarrowingContextError("farrowing_provider_identity_required")
    latest = {}
    for row in rows:
        context_id = row.get("context_id")
        if context_id and (context_id not in latest or source_order(row) > source_order(latest[context_id])):
            latest[context_id] = row
    superseded = {row.get("supersedes_context_id") for row in latest.values()}
    current = [row for key, row in latest.items() if key not in superseded
               and 0 <= (stamp - source_order(row)[0]).total_seconds() <= CONTEXT_SECONDS
               and source_order(row) <= source_order(parsed)]
    referenced_saved = {item.get("litter_id") for row in current if row.get("_claim_status") != "completed"
                        for item in row.get("canonical_litters", ()) if isinstance(item, dict)}
    current = [row for row in current if not (row.get("_claim_status") == "completed"
               and (row.get("_saved_result") or {}).get("litter_id") in referenced_saved)]
    reply = str(parsed.get("reply_to_message_id") or "")
    if reply:
        current = [row for row in current if reply in row.get("_card_ids", ())]
        if not current:
            raise FarrowingContextError("farrowing_reply_context_mismatch")
    if len(current) > 1:
        supplied = supplied or {}
        sow_ref = str(supplied.get("sow_ref") or "").strip().casefold()
        if sow_ref:
            current = [row for row in current if sow_ref in
                       {str(ref).casefold() for ref in row.get("sow_refs", ())}]
        birth = supplied.get("farrowing_date")
        if birth and len(current) > 1 and all((row.get("facts") or {}).get("farrowing_date") for row in current):
            current = [row for row in current if (row.get("facts") or {}).get("farrowing_date") == birth]
    if len(current) != 1:
        raise FarrowingContextError("farrowing_context_ambiguous" if len(current) > 1
                                    else "farrowing_context_not_current")
    return current[0]


class PostgresFarrowingStore:
    def __init__(self, connect_factory=None):
        self.connect_factory = connect_factory

    def _connect(self):
        if self.connect_factory:
            return self.connect_factory()
        import psycopg
        return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5)

    def read(self, actor, chat):
        with self._connect() as db:
            db.read_only = True
            with db.cursor() as cursor:
                cursor.execute("set local statement_timeout='5s'")
            return _FarrowingTransaction(db, actor, chat).rows()

    @contextmanager
    def locked(self, actor, chat):
        with self._connect() as db:
            with db.cursor() as cursor:
                cursor.execute("set local statement_timeout='15s'")
                cursor.execute("set local lock_timeout='5s'")
                cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",
                               (EVENT_SOURCE + ":" + actor + ":" + chat,))
            yield _FarrowingTransaction(db, actor, chat)


class _FarrowingTransaction:
    def __init__(self, db, actor, chat):
        self.db, self.actor, self.chat = db, actor, chat

    @contextmanager
    def connection(self):
        # A claim and its retained question/facts commit or roll back together.
        yield self.db

    def rows(self):
        with self.db.cursor() as cursor:
            cursor.execute("""select review_json->'farrowing_litter'
                from public.sam_live_stock_conversation_review_events
                where event_source=%s and chatwoot_conversation_id=%s
                order by created_at desc,review_event_id desc limit 100""", (EVENT_SOURCE, self.actor))
            rows = [dict(row[0]) for row in cursor.fetchall() if isinstance(row[0], dict)
                    and row[0].get("owner_user_id") == self.actor
                    and row[0].get("private_chat_id") == self.chat]
            tokens = list({str((row.get("outcome") or {}).get("callback_token")) for row in rows
                           if (row.get("outcome") or {}).get("callback_token")})
            if tokens:
                cursor.execute("""select callback_token,status,result_payload
                    from app_private.oom_protected_action_claims where callback_token=any(%s)
                    and action_kind=%s and owner_user_id=%s and private_chat_id=%s""",
                    (tokens, ACTION_KIND, self.actor, self.chat))
                claims = {str(row[0]): (row[1], row[2]) for row in cursor.fetchall()}
                for row in rows:
                    claim = claims.get(str((row.get("outcome") or {}).get("callback_token")))
                    if claim:
                        row["_claim_status"], row["_saved_result"] = claim
            cards = list({str((row.get("outcome") or {}).get("card_mission_id") or row["context_id"])
                          for row in rows})
            if cards:
                cursor.execute("""select review_json->'family_message_lifecycle'
                    from public.sam_live_stock_conversation_review_events
                    where event_source='oom_sakkie_family_message_lifecycle'
                    and chatwoot_conversation_id=any(%s)
                    and review_json->'family_message_lifecycle'->>'owner_user_id'=%s
                    and review_json->'family_message_lifecycle'->>'chat_id'=%s
                    and review_json->'family_message_lifecycle'->>'telegram_message_id' is not null
                    order by created_at desc,review_event_id desc limit 200""", (cards, self.actor, self.chat))
                bindings = [item[0] for item in cursor.fetchall() if isinstance(item[0], dict)]
                for row in rows:
                    card = str((row.get("outcome") or {}).get("card_mission_id") or row["context_id"])
                    row["_card_ids"] = [str(item["telegram_message_id"]) for item in bindings
                                        if item.get("card_mission_id") == card]
        return rows

    def claim(self, token):
        with self.db.cursor() as cursor:
            cursor.execute("""select status,expires_at,result_payload,preview_payload,preview_digest,mission_id
                from app_private.oom_protected_action_claims
                where callback_token=%s and action_kind=%s and owner_user_id=%s and private_chat_id=%s
                for update""", (token, ACTION_KIND, self.actor, self.chat))
            row = cursor.fetchone()
        return dict(zip(("status", "expires_at", "result", "preview_payload", "preview_digest", "mission_id"), row)) if row else None

    def retire(self, context_id):
        with self.db.cursor() as cursor:
            cursor.execute("""select status,result_payload from app_private.oom_protected_action_claims
                where mission_id=%s and action_kind=%s and owner_user_id=%s and private_chat_id=%s
                for update""", (context_id, ACTION_KIND, self.actor, self.chat))
            protected = [dict(zip(("status", "result"), row)) for row in cursor.fetchall()
                         if row[0] in ("executing", "completed")]
            if not protected:
                cursor.execute("""update app_private.oom_protected_action_claims set status='changed'
                    where mission_id=%s and action_kind=%s and owner_user_id=%s and private_chat_id=%s
                    and status='active'""", (context_id, ACTION_KIND, self.actor, self.chat))
        return protected

    def save(self, receipt):
        with self.db.cursor() as cursor:
            cursor.execute("""insert into public.sam_live_stock_conversation_review_events(
                review_event_id,chatwoot_conversation_id,chatwoot_message_id,channel,source_agent,event_source,review_json)
                values(%s,%s,%s,'telegram','HERDMASTER',%s,%s::jsonb)""",
                ("FARROW-TURN-" + digest([self.actor, self.chat, receipt["provider_message_id"]]),
                 self.actor, receipt["provider_message_id"], EVENT_SOURCE,
                 json.dumps({CONTEXT_KEY: receipt}, default=str)))
