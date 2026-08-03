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
DOMAINS = frozenset({"herd_health", "rootline", "manager_round", "sam", "beacon", "general"})
MAX_CONTEXT_ITEMS = 8


@dataclass(frozen=True)
class SemanticInterpretation:
    domain: str
    intent: str
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
        return SemanticInterpretation(domain=domain,
            intent=str(value.get("intent") or domain).strip()[:100], entity_refs=refs,
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
    return {"reply_to_message_id": str(parsed.get("reply_to_message_id") or "")[:40], "active_cases": active}


def _payload(parsed, context, source):
    system = (
        "You are Oom Sakkie's semantic front door for authenticated private farm-owner messages. "
        "Understand natural English or Afrikaans, typos, short follow-ups, and references to active cases. "
        "Classify meaning only; never claim a write, send, publication, sale, treatment, mating, or hardware action. "
        "Domains: herd_health for animal welfare/death/loss/health updates; rootline for water, tanks, irrigation, "
        "power, valves or confirmation that a camp started/stopped; manager_round for farm briefs and priorities; "
        "sam for customers/livestock sales; beacon for marketing/media/posts; general otherwise. "
        "A death or stopped-valve statement is new evidence, not a request to repeat an old question. "
        "Use active context and reply identity. Ask one clarification only when meaning or entity truly cannot be determined. "
        "Return JSON only with domain,intent,entity_refs,continuation,observation,requested_action,language,confidence,"
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
