"""LLM-first meaning interpretation for authenticated owner Telegram text.

The model interprets language and bounded context only. Existing deterministic
specialist boundaries retain every write, send, publication and control gate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from typing import Any, Callable, Mapping
from urllib import error as urllib_error
from urllib import request as urllib_request

from modules.oom_sakkie.llm_router import API_KEY_ENV, API_URL_ENV, DEFAULT_API_URL, MODEL_ENV, TIMEOUT_ENV

ENABLED_ENV = "OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED"
DOMAINS = frozenset({"herd_health", "herd_management", "rootline", "manager_round", "sam", "beacon", "general"})
MESSAGE_KINDS = frozenset({"observation", "question", "request", "command", "confirmation", "correction", "general"})
MAX_CONTEXT_ITEMS = 8


@dataclass(frozen=True)
class SemanticInterpretation:
    domain: str
    intent: str
    message_kind: str = "general"
    entity_refs: tuple[str, ...] = ()
    continuation: bool = False
    observation: str = ""
    requested_action: str = ""
    language: str = "unknown"
    confidence: float = 0.0
    needs_clarification: bool = False
    clarification_question: str = ""

    def as_hint(self) -> dict[str, Any]:
        return asdict(self)


def semantic_front_door_policy(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = environ if environ is not None else os.environ
    enabled = str(source.get(ENABLED_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}
    configured = bool(str(source.get(MODEL_ENV) or "").strip() and str(source.get(API_KEY_ENV) or "").strip())
    return {"enabled": enabled, "configured": configured, "llm_interprets_only": True,
            "can_execute": False, "can_write": False, "can_send": False,
            "can_control_hardware": False, "domains": sorted(DOMAINS)}


def interpret_owner_message(parsed: Mapping[str, Any], *, environ=None,
                            context_loader: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
                            http_open=None) -> SemanticInterpretation | None:
    source = environ if environ is not None else os.environ
    policy = semantic_front_door_policy(source)
    if not policy["enabled"] or not policy["configured"]:
        return None
    context = _bounded_context((context_loader or load_bounded_owner_context)(parsed))
    request = urllib_request.Request(
        str(source.get(API_URL_ENV) or DEFAULT_API_URL).strip() or DEFAULT_API_URL,
        data=json.dumps(_payload(parsed, context, source), separators=(",", ":")).encode("utf-8"),
        headers={"Authorization": f"Bearer {str(source.get(API_KEY_ENV) or '').strip()}",
                 "Content-Type": "application/json"}, method="POST")
    try:
        opener = http_open or urllib_request.urlopen
        with opener(request, timeout=_timeout(source)) as response:
            body = response.read().decode("utf-8")
    except (urllib_error.HTTPError, urllib_error.URLError, TimeoutError, OSError, ValueError):
        return None
    return parse_semantic_response(body)


def parse_semantic_response(body: str) -> SemanticInterpretation | None:
    try:
        envelope = json.loads(body or "{}")
        value = json.loads(_strip_fence(str(envelope["choices"][0]["message"]["content"] or "")))
        domain = str(value.get("domain") or "").strip()
        if domain not in DOMAINS:
            return None
        refs = tuple(dict.fromkeys(str(item).strip()[:80] for item in
                                   (value.get("entity_refs") or []) if str(item).strip()))[:8]
        message_kind = str(value.get("message_kind") or "general").strip().lower()
        if message_kind not in MESSAGE_KINDS:
            return None
        return SemanticInterpretation(domain=domain,
            intent=str(value.get("intent") or domain).strip()[:100], entity_refs=refs,
            message_kind=message_kind,
            continuation=bool(value.get("continuation")),
            observation=str(value.get("observation") or "").strip()[:500],
            requested_action=str(value.get("requested_action") or "").strip()[:120],
            language=str(value.get("language") or "unknown").strip()[:20],
            confidence=max(0.0, min(1.0, float(value.get("confidence") or 0))),
            needs_clarification=bool(value.get("needs_clarification")),
            clarification_question=str(value.get("clarification_question") or "").strip()[:240])
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return None


def load_bounded_owner_context(parsed: Mapping[str, Any]) -> dict[str, Any]:
    try:
        from modules.oom_sakkie.herdmaster_health_loss_runtime import _load_active_contexts
        rows = _load_active_contexts(str(parsed.get("telegram_chat_id") or ""),
            owner_user_id=str(parsed.get("telegram_user_id") or ""))
    except Exception:
        rows = []
    active = []
    for row in rows[:MAX_CONTEXT_ITEMS]:
        identity = ((row.get("preview") or {}).get("evaluator") or {}).get("identity") or {}
        active.append({"specialist": "HERDMASTER", "mission_id": str(row.get("mission_id") or "")[:80],
            "status": str(row.get("status") or "")[:40],
            "tag": str(identity.get("tag_number") or row.get("tag_number") or "")[:40],
            "card_message_id": str(row.get("card_message_id") or "")[:40]})
    recent = _load_recent_specialist_context(parsed)
    return {"reply_to_message_id": str(parsed.get("reply_to_message_id") or "")[:40],
            "active_cases": active, "recent_turns": recent}


def _load_recent_specialist_context(parsed):
    if not str(os.environ.get("DATABASE_URL") or "").strip():
        return []
    try:
        import psycopg
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5) as connection:
            connection.read_only = True
            with connection.cursor() as cursor:
                cursor.execute("""select review_json->'family_message_lifecycle'
                    from public.sam_live_stock_conversation_review_events
                    where event_source='oom_sakkie_family_message_lifecycle'
                      and review_json->'family_message_lifecycle'->>'owner_user_id'=%s
                      and review_json->'family_message_lifecycle'->>'chat_id'=%s
                    order by created_at desc,review_event_id desc limit %s""",
                    (str(parsed.get("telegram_user_id") or ""),
                     str(parsed.get("telegram_chat_id") or ""), MAX_CONTEXT_ITEMS))
                rows = [row[0] for row in cursor.fetchall()]
    except Exception:
        return []
    return [{"specialist": str(row.get("specialist_identity") or "")[:40],
             "task_state": str(row.get("task_state") or "")[:40],
             "card_mission_id": str(row.get("card_mission_id") or "")[:80],
             "provider_message_id": str(row.get("provider_message_id") or "")[:40],
             "semantic_domain": str(row.get("semantic_domain") or "")[:40],
             "semantic_intent": str(row.get("semantic_intent") or "")[:100],
             "clarification_question": str(row.get("clarification_question") or "")[:240]}
            for row in rows if isinstance(row, Mapping)]


def _payload(parsed, context, source):
    system = (
        "You are Oom Sakkie's semantic front door for authenticated private farm-family messages. "
        "Understand natural English, Afrikaans, mixed-language text, typos, short follow-ups, and references to active cases. "
        "Identity and permissions are supplied by deterministic gateway policy; never infer either from a name or language. "
        "Classify meaning only; never claim a write, send, publication, sale, treatment, mating, or hardware action. "
        "Domains: herd_health only for a specific animal welfare/death/loss/health report; herd_management for herd, "
        "breeding, weighing, farrowing or animal-work planning; rootline for water, tanks, irrigation, power, valves "
        "or confirmation that a camp started/stopped; manager_round for farm briefs and priorities; "
        "sam for customers/livestock sales; beacon for marketing/media/posts; general otherwise. "
        "Treat broad requests such as 'what is the plan for today?', 'what needs attention today?', or their Afrikaans "
        "equivalents as manager_round and do not ask which domain. Treat a one-word domain reply as a continuation "
        "when recent context shows a clarification: Animals/Diere maps to herd_management, Irrigation/Besproeiing "
        "maps to rootline, Sales/Verkope maps to sam, and Marketing maps to beacon. A death or stopped-valve statement "
        "is new evidence, not a repeated question. "
        "Use active context and reply identity. Ask one clarification only when meaning or entity truly cannot be determined. "
        "Classify message_kind as observation only when the owner asserts a physical/current fact; use question or request "
        "when asking for information or a plan, command when asking for an action, confirmation for an approval/confirmation, "
        "and correction when replacing prior evidence. Return JSON only with domain,intent,message_kind,entity_refs,continuation,"
        "observation,requested_action,language,confidence,"
        "needs_clarification,clarification_question."
    )
    user = {"message": str(parsed.get("text") or "")[:2000],
            "provider_message_id": str(parsed.get("provider_message_id") or "")[:80], "context": context}
    return {"model": str(source.get(MODEL_ENV) or "").strip(), "temperature": 0,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": json.dumps(user, separators=(",", ":"))}],
            "response_format": {"type": "json_object"}}


def _bounded_context(value):
    value = value if isinstance(value, Mapping) else {}
    return {"reply_to_message_id": str(value.get("reply_to_message_id") or "")[:40],
            "active_cases": list(value.get("active_cases") or [])[:MAX_CONTEXT_ITEMS],
            "recent_turns": list(value.get("recent_turns") or [])[-MAX_CONTEXT_ITEMS:]}


def _timeout(source):
    try:
        return max(1, min(20, int(source.get(TIMEOUT_ENV) or 8)))
    except (TypeError, ValueError):
        return 8


def _strip_fence(value):
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].startswith("```"):
            lines.pop()
        return "\n".join(lines).strip()
    return text
