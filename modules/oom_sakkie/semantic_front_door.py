"""LLM-first meaning interpretation for authenticated owner Telegram text.

The model interprets language and bounded context only. Existing deterministic
specialist boundaries retain every write, send, publication and control gate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from typing import Any, Callable, Mapping
from urllib import error as urllib_error
from urllib import request as urllib_request

from modules.oom_sakkie.llm_router import API_KEY_ENV, API_URL_ENV, DEFAULT_API_URL, MODEL_ENV, TIMEOUT_ENV

ENABLED_ENV = "OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED"
DOMAINS = frozenset({"herd_health", "herd_management", "rootline", "manager_round", "sam", "beacon", "documents", "general"})
MESSAGE_KINDS = frozenset({"observation", "question", "request", "command", "confirmation", "correction", "general"})
MEDIA_SUBJECT_TAGS = frozenset({"live_stock", "piglets", "litter", "weaner", "sow", "farm_life"})
MAX_CONTEXT_ITEMS = 8
CONTEXT_MAX_AGE_SECONDS = 6 * 60 * 60
ACTIVE_SPECIALIST_CONTEXT_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
MAX_CONTEXT_SCAN_ITEMS = 64


@dataclass(frozen=True)
class SemanticInterpretation:
    domain: str
    intent: str
    message_kind: str = "general"
    entity_refs: tuple[str, ...] = ()
    continuation: bool = False
    observation: str = ""
    observation_facts: tuple[Mapping[str, Any], ...] = ()
    breeding_actions: tuple[Mapping[str, Any], ...] = ()
    farrowing_litter: Mapping[str, Any] | None = None
    litter_first_treatment: Mapping[str, Any] | None = None
    confirmation_facts: Mapping[str, bool] | None = None
    commissioning_facts: Mapping[str, bool] | None = None
    protected_preview_required: bool = False
    recording_prohibited: bool = False
    requested_action: str = ""
    language: str = "unknown"
    confidence: float = 0.0
    needs_clarification: bool = False
    clarification_question: str = ""

    def as_hint(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MediaSemanticUnderstanding:
    subject_tags: tuple[str, ...]
    confidence: float
    model: str
    semantic_digest: str
    observer_version: str = "oom_semantic_media_v1"


def interpret_media_owner_context(owner_context: str, asset_sha256: str, *, environ=None,
                                  http_open=None) -> MediaSemanticUnderstanding | None:
    """Classify bounded media context; never grants approval or publication authority."""
    source = environ if environ is not None else os.environ
    policy = semantic_front_door_policy(source)
    context = str(owner_context or "").strip()[:2000]
    digest = str(asset_sha256 or "").strip().lower()
    if (not policy["enabled"] or not policy["configured"] or not context
            or not re.fullmatch(r"[0-9a-f]{64}", digest)):
        return None
    request = urllib_request.Request(
        str(source.get(API_URL_ENV) or DEFAULT_API_URL).strip() or DEFAULT_API_URL,
        data=json.dumps(_media_payload(context, digest, source), separators=(",", ":")).encode(),
        headers={"Authorization": f"Bearer {str(source.get(API_KEY_ENV) or '').strip()}",
                 "Content-Type": "application/json"}, method="POST")
    try:
        opener = http_open or urllib_request.urlopen
        with opener(request, timeout=_timeout(source)) as response:
            body = response.read().decode("utf-8")
        envelope = json.loads(body or "{}")
        value = json.loads(_strip_fence(str(envelope["choices"][0]["message"]["content"] or "")))
        tags = tuple(sorted(set(str(tag).strip().casefold() for tag in
            (value.get("subject_tags") or []) if str(tag).strip() in MEDIA_SUBJECT_TAGS)))
        confidence = float(value.get("confidence") or 0)
        if (value.get("affirmative_current_subject") is not True
                or value.get("negated_or_absent") is not False
                or value.get("historical_or_future_only") is not False
                or value.get("conflicting_subject") is not False
                or value.get("needs_clarification") is not False
                or confidence < 0.8 or not tags or "live_stock" not in tags):
            return None
        semantic_digest = hashlib.sha256(json.dumps({"asset_sha256": digest,
            "owner_context": context, "subject_tags": tags, "confidence": confidence,
            "model": str(source.get(MODEL_ENV) or "")}, sort_keys=True).encode()).hexdigest()
        return MediaSemanticUnderstanding(tags, confidence,
            str(source.get(MODEL_ENV) or ""), semantic_digest)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError,
            urllib_error.HTTPError, urllib_error.URLError, TimeoutError, OSError):
        return None


def _media_payload(owner_context, asset_sha256, source):
    system = ("Classify only the current visible subject asserted by the authenticated owner's media context. "
        "Do not infer from a name. Handle English, Afrikaans, mixed language, negation, correction and time. "
        "Allowed subject_tags are live_stock,piglets,litter,weaner,sow,farm_life. "
        "If the subject is absent, negated, historical/future-only, conflicting or ambiguous, set the matching "
        "flag and needs_clarification true where appropriate; return no tags. Return JSON only with subject_tags, "
        "affirmative_current_subject,negated_or_absent,historical_or_future_only,conflicting_subject,"
        "needs_clarification,confidence. This classifies meaning only and grants no media, publication or sales authority.")
    return {"model": str(source.get(MODEL_ENV) or ""), "temperature": 0,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content":
            json.dumps({"owner_context": owner_context, "asset_sha256": asset_sha256}, separators=(",", ":"))}],
        "response_format": {"type": "json_object"}}


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
    result = parse_semantic_response(body)
    if result and result.observation_facts and not _facts_context_allowed(parsed, context):
        return replace(result, observation_facts=(), needs_clarification=True,
            clarification_question="Are you reporting the storage tanks, the reservoir, or both?")
    return result


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
        facts = _observation_facts(value.get("observation_facts"))
        breeding_actions = _breeding_actions(value.get("breeding_actions"))
        farrowing_litter = _farrowing_litter(value.get("farrowing_litter"))
        litter_first_treatment = _litter_first_treatment(value.get("litter_first_treatment"))
        if farrowing_litter and litter_first_treatment:
            return None
        confirmation_facts = _confirmation_facts(value.get("confirmation_facts"))
        commissioning_facts = _commissioning_facts(value.get("commissioning_facts"))
        return SemanticInterpretation(domain=domain,
            intent=str(value.get("intent") or domain).strip()[:100], entity_refs=refs,
            message_kind=message_kind,
            continuation=bool(value.get("continuation")),
            observation=str(value.get("observation") or "").strip()[:500],
            observation_facts=facts,
            breeding_actions=breeding_actions,
            farrowing_litter=farrowing_litter,
            litter_first_treatment=litter_first_treatment,
            confirmation_facts=confirmation_facts,
            commissioning_facts=commissioning_facts,
            protected_preview_required=value.get("protected_preview_required") is True,
            recording_prohibited=value.get("recording_prohibited") is True,
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
                     str(parsed.get("telegram_chat_id") or ""), MAX_CONTEXT_SCAN_ITEMS))
                rows = [row[0] for row in cursor.fetchall()]
    except Exception:
        return []
    eligible = _eligible_clarification_context(rows, parsed)
    return [{"specialist": str(row.get("specialist_identity") or "")[:40],
             "task_state": str(row.get("task_state") or "")[:40],
             "card_mission_id": str(row.get("card_mission_id") or "")[:80],
             "provider_message_id": str(row.get("provider_message_id") or "")[:40],
             "provider_timestamp": str(row.get("provider_timestamp") or "")[:40],
             "delivery_provider_timestamp": str(row.get("delivery_provider_timestamp") or "")[:40],
             "semantic_domain": str(row.get("semantic_domain") or "")[:40],
             "semantic_intent": str(row.get("semantic_intent") or "")[:100],
             "clarification_question": str(row.get("clarification_question") or "")[:240]}
            for row in eligible]


def _payload(parsed, context, source):
    system = (
        "You are Oom Sakkie's semantic front door for authenticated private farm-family messages. "
        "Understand natural English, Afrikaans, mixed-language text, typos, short follow-ups, and references to active cases. "
        "Identity and permissions are supplied by deterministic gateway policy; never infer either from a name or language. "
        "Classify meaning only; never claim a write, send, publication, sale, treatment, mating, or hardware action. "
        "Domains: herd_health only for a specific animal welfare/death/loss/health report; herd_management for herd, "
        "breeding, weighing, farrowing or animal-work planning; rootline for water, tanks, irrigation, power, valves "
        "or confirmation that a camp started/stopped; manager_round for farm briefs and priorities; "
        "sam for customers/livestock sales; beacon for marketing/media/posts; documents for requests to prepare or print the fixed weekly weighing sheet; general otherwise. "
        "For any natural English, Afrikaans, mixed-language, paraphrased or contextual request to print the weekly weighing sheet, use domain documents and stable intent weekly_weighing_sheet_print. A short follow-up may retain this intent only when bounded recent context identifies that same document. "
        "For a request to prepare farm-awareness, non-availability livestock content, or a farm story that must not sell, "
        "use domain beacon and the stable intent live_stock_awareness. Preserve that intent on English, Afrikaans, mixed-language "
        "and contextual follow-up requests; zero buyer demand does not change the awareness intent into a sales campaign. "
        "For requests to view, review, accept or reject private farm media or a completed album, use domain beacon and stable intent private_media_library_review. Preserve it for English, Afrikaans, paraphrases and bounded follow-ups. "
        "Treat broad requests such as 'what is the plan for today?', 'what needs attention today?', or their Afrikaans "
        "equivalents as manager_round and do not ask which domain. Treat a one-word domain reply as a continuation "
        "when recent context shows a clarification: Animals/Diere maps to herd_management, Irrigation/Besproeiing "
        "maps to rootline, Sales/Verkope maps to sam, and Marketing maps to beacon. A death or stopped-valve statement "
        "is new evidence, not a repeated question. "
        "For a request for a breeding or mating plan, including an update using recent weanings, use domain "
        "herd_management and the stable intent breeding_plan. Do not use breeding_plan for weights, animal lookup, "
        "inventory, welfare, farrowing-only status, or a broad whole-farm brief. "
        "Use active context and reply identity. Ask one clarification only when meaning or entity truly cannot be determined. "
        "Classify message_kind as observation only when the owner asserts a physical/current fact; use question or request "
        "when asking for information or a plan, command when asking for an action, confirmation for an approval/confirmation, "
        "and correction when replacing prior evidence. For a reply to a structured checklist, return confirmation_facts only "
        "for facts the owner affirmatively or negatively states; supported keys are interlock_off and no_enabled_scene with "
        "literal true/false values. Never turn presence alone into setting facts. Return JSON only with "
        "domain,intent,message_kind,entity_refs,continuation,"
        "observation,observation_facts,breeding_actions,farrowing_litter,litter_first_treatment,confirmation_facts,commissioning_facts,"
        "protected_preview_required,recording_prohibited,requested_action,language,confidence,"
        "needs_clarification,clarification_question."
        " For an owner report of actual boar placements, removals, a body-condition recovery hold or clearance, or a sow appearing close to farrowing, "
        "return breeding_actions with one object per supplied sow. Use animal_ref and, for exposure, boar_ref; supported action values are exposure, "
        "exposure_removal, recovery_hold, recovery_clearance, and near_farrowing. Preserve only explicitly supplied exposure_started_on, "
        "planned_days, planned_removal_on, actual_removed_on, exposure_identity, placement_pen_ref, body_condition_score, observed_at, "
        "prior_mating_known, father_known, and factual_note. Never infer a service, "
        "conception, pregnancy, father, mating date, animal identity, or omitted group member."
        " For a natural request to record a real farrowing/litter, use herd_management with stable intent record_farrowing_litter and return farrowing_litter. "
        "Allowed farrowing_litter keys are sow_ref,farrowing_date,total_born,born_alive,stillborn,mummified,died_after_live_birth,mating_ref,father_ref,correction_of_litter_id,correction_reason. "
        "For an already-born litter's first treatment, use herd_management with stable intent record_litter_first_treatment and return litter_first_treatment, never farrowing_litter. "
        "Allowed litter_first_treatment keys are sow_ref,litter_ref,action_date,male_count,female_count,total_count,earmarked,antiparasitic_product_ref,deworming_product_ref,vaccination_product_ref,dose,route,batch_lot_number,notes. Preserve only facts explicitly reported; never invent a product,dose,route or batch. "
        "Use correction_of_litter_id and correction_reason only when the owner explicitly corrects an existing litter; preserve both exactly. "
        "Separate dates and outcome counts from animal identity. Preserve omitted mating_ref and father_ref as null; never invent them. "
        "Use integer counts only when explicitly supplied and keep born_alive distinct from alive_now: died_after_live_birth is a subset of born_alive, not another birth outcome."
        " For physical water observations, observation_facts must contain zero, one, or two objects using only "
        "subject storage_tanks or reservoir and either state LOW/OK/FULL or an exact fraction numerator/denominator. "
        "Resolve phrases such as both tanks or their Afrikaans equivalents from the message and bounded active question; "
        "do not invent a missing tank or value. A short reply may answer only a chronologically earlier active question; "
        "never use stale context to satisfy a newer unrelated question. "
        "Treat natural readiness replies such as 'Done; at the valves now', 'Ek is nou by die kleppe', or mixed-language "
        "equivalents as a continuation of one unambiguous recent specialist setup question, not as a new physical tank observation."
        " When the active question asks about a supervised mixer proof, return commissioning_facts only for facts explicitly "
        "reported, using mixer_recirculating, pump_expected, and other_outputs_off with literal true/false values."
        " For a grouped breeding update, preserve every named female once in breeding_actions. Physical placement is "
        "exposure, never mating, service, conception, or pregnancy. Preserve a shared duration as planned_days; deterministic "
        "code calculates the removal date. Preserve explicit Unknown mating/father evidence with false prior_mating_known and "
        "father_known values. If the owner requests a preview or says not to record, set "
        "protected_preview_required true and recording_prohibited true. Such a direct protected update is not an answer "
        "to an unrelated active manager question, even if conversational context exists."
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


def _observation_facts(value):
    if not isinstance(value, list) or len(value) > 2:
        return ()
    result, seen = [], set()
    for raw in value:
        if not isinstance(raw, Mapping):
            return ()
        subject = str(raw.get("subject") or "").strip().lower()
        state = str(raw.get("state") or "").strip().upper()
        numerator, denominator = raw.get("numerator"), raw.get("denominator")
        if subject not in {"storage_tanks", "reservoir"}:
            return ()
        if state in {"LOW", "OK", "FULL"} and numerator is None and denominator is None:
            result.append({"subject": subject, "state": state})
        elif (not state and type(numerator) is int and type(denominator) is int
              and denominator > 0 and 0 <= numerator <= denominator):
            result.append({"subject": subject, "numerator": numerator, "denominator": denominator})
        else:
            return ()
    if len({row["subject"] for row in result}) != len(result):
        return ()
    return tuple(result)


def _breeding_actions(value):
    if value in (None, []):
        return ()
    if not isinstance(value, list) or not 1 <= len(value) <= 24:
        return ()
    allowed = {"exposure", "exposure_removal", "recovery_hold", "recovery_clearance", "near_farrowing"}
    keys = {"animal_ref", "boar_ref", "action", "exposure_started_on", "planned_days", "planned_removal_on", "placement_pen_ref",
            "actual_removed_on", "exposure_identity", "exposure_group_identity", "body_condition_score", "observed_at", "factual_note",
            "prior_mating_known", "father_known"}
    result, seen = [], set()
    for raw in value:
        if not isinstance(raw, Mapping) or set(raw) - keys:
            return ()
        action = str(raw.get("action") or "").strip().lower()
        animal_ref = str(raw.get("animal_ref") or "").strip()[:80]
        if action not in allowed or not animal_ref:
            return ()
        identity = animal_ref.casefold()
        if identity in seen:
            return ()
        seen.add(identity)
        item = {"action": action, "animal_ref": animal_ref}
        for key in keys - {"action", "animal_ref"}:
            if raw.get(key) not in (None, ""):
                item[key] = raw[key] if key in {"body_condition_score", "planned_days",
                    "prior_mating_known", "father_known"} else str(raw[key]).strip()[:500]
        if "planned_days" in item and (type(item["planned_days"]) is not int
                or not 1 <= item["planned_days"] <= 60):
            return ()
        if any(key in item and type(item[key]) is not bool
               for key in ("prior_mating_known", "father_known")):
            return ()
        result.append(item)
    return tuple(result)


def _farrowing_litter(value):
    if value in (None, {}):
        return None
    if not isinstance(value, Mapping):
        return None
    allowed = {"sow_ref", "farrowing_date", "total_born", "born_alive",
               "stillborn", "mummified", "died_after_live_birth",
               "mating_ref", "father_ref", "correction_of_litter_id", "correction_reason"}
    if set(value) - allowed:
        return None
    sow_ref = str(value.get("sow_ref") or "").strip()[:80]
    if not sow_ref:
        return None
    result = {"sow_ref": sow_ref}
    for key in ("farrowing_date", "mating_ref", "father_ref"):
        raw = value.get(key)
        result[key] = str(raw).strip()[:80] if raw not in (None, "") else None
    raw = value.get("correction_of_litter_id")
    result["correction_of_litter_id"] = str(raw).strip()[:80] if raw not in (None, "") else None
    raw = value.get("correction_reason")
    result["correction_reason"] = str(raw).strip()[:500] if raw not in (None, "") else None
    for key in ("total_born", "born_alive", "stillborn", "mummified",
                "died_after_live_birth"):
        raw = value.get(key)
        if raw is None:
            result[key] = None
        elif type(raw) is int and 0 <= raw <= 40:
            result[key] = raw
        else:
            return None
    return result


def _litter_first_treatment(value):
    if value in (None, {}):
        return None
    if not isinstance(value, Mapping):
        return None
    allowed = {"sow_ref", "litter_ref", "action_date", "male_count",
               "female_count", "total_count", "earmarked",
               "antiparasitic_product_ref", "deworming_product_ref",
               "vaccination_product_ref", "dose", "route",
               "batch_lot_number", "notes"}
    if set(value) - allowed:
        return None
    sow_ref = str(value.get("sow_ref") or "").strip()[:80]
    if not sow_ref:
        return None
    result = {"sow_ref": sow_ref}
    for key in ("litter_ref", "action_date", "antiparasitic_product_ref",
                "deworming_product_ref", "vaccination_product_ref", "route",
                "batch_lot_number", "notes"):
        raw = value.get(key)
        result[key] = str(raw).strip()[:500 if key == "notes" else 80] if raw not in (None, "") else None
    for key in ("male_count", "female_count", "total_count"):
        raw = value.get(key)
        if raw is None:
            result[key] = None
        elif type(raw) is int and 0 <= raw <= 40:
            result[key] = raw
        else:
            return None
    earmarked = value.get("earmarked")
    if earmarked is not None and type(earmarked) is not bool:
        return None
    result["earmarked"] = earmarked
    dose = value.get("dose")
    if dose is not None and not isinstance(dose, (int, float, str)):
        return None
    result["dose"] = dose
    return result


def _confirmation_facts(value):
    if value is None or not isinstance(value, Mapping):
        return None
    allowed = {"interlock_off", "no_enabled_scene"}
    if not value or any(key not in allowed or type(item) is not bool
                        for key, item in value.items()):
        return None
    return {key: value[key] for key in sorted(value)}


def _commissioning_facts(value):
    if value is None or not isinstance(value, Mapping):
        return None
    allowed = {"mixer_recirculating", "pump_expected", "other_outputs_off"}
    if not value or any(key not in allowed or type(item) is not bool
                        for key, item in value.items()):
        return None
    return {key: value[key] for key in sorted(value)}


def _eligible_clarification_context(rows, parsed):
    incoming = _timestamp(parsed.get("provider_timestamp"))
    if incoming is None:
        return []
    reply_to = str(parsed.get("reply_to_message_id") or "").strip()
    candidates = []
    for row_index, row in enumerate(rows):
        if (not isinstance(row, Mapping)
                or row.get("state") not in {"delivered", "notification_delivered"}):
            continue
        typed_wait = (row.get("state") == "notification_delivered"
            and row.get("task_state") == "waiting_for_input"
            and str(row.get("semantic_intent") or "") in {
                "fertilizer_commissioning_presence", "fertilizer_commissioning"})
        if typed_wait:
            mission = str(row.get("mission_id") or "")
            card = str(row.get("card_mission_id") or "")
            superseded = any(isinstance(newer, Mapping)
                and str(newer.get("mission_id") or "") == mission
                and str(newer.get("card_mission_id") or "") == card
                and newer.get("state") in {"delivered", "updated"}
                and newer.get("task_state") != "waiting_for_input"
                for newer in rows[:row_index])
            if superseded:
                continue
        if not str(row.get("clarification_question") or "").strip() and not typed_wait:
            continue
        delivered = _timestamp(row.get("delivery_provider_timestamp"))
        if delivered is None:
            continue
        age = (incoming - delivered).total_seconds()
        maximum_age = (ACTIVE_SPECIALIST_CONTEXT_MAX_AGE_SECONDS
                       if typed_wait else CONTEXT_MAX_AGE_SECONDS)
        if age < 0 or age > maximum_age:
            continue
        visible_id = str(row.get("notification_message_id")
                         or row.get("telegram_message_id") or "")
        if reply_to and visible_id != reply_to:
            continue
        projected = dict(row)
        projected["telegram_message_id"] = visible_id
        candidates.append((delivered, projected))
    if not candidates:
        return []
    candidates.sort(key=lambda item: item[0], reverse=True)
    newest = candidates[0][0]
    newest_rows = [row for delivered, row in candidates if delivered == newest]
    return newest_rows if len(newest_rows) == 1 else []


def _facts_context_allowed(parsed, context):
    text = str(parsed.get("text") or "").lower()
    explicit_subject = re.search(
        r"\b(reservoir|storage(?:\s+tanks?)?|opgaartenks?|both\s+tanks?|albei\s+tenks?|beide\s+tenks?)\b",
        text)
    if explicit_subject:
        return True
    recent = list(context.get("recent_turns") or [])
    if len(recent) != 1:
        return False
    row = recent[0]
    incoming = _timestamp(parsed.get("provider_timestamp"))
    delivered = _timestamp(row.get("delivery_provider_timestamp"))
    if (incoming is None or delivered is None
            or not 0 <= (incoming - delivered).total_seconds() <= CONTEXT_MAX_AGE_SECONDS):
        return False
    reply_to = str(parsed.get("reply_to_message_id") or "").strip()
    if reply_to and str(row.get("telegram_message_id") or "") != reply_to:
        return False
    question = str(row.get("clarification_question") or "").lower()
    return (str(row.get("semantic_domain") or "") == "rootline"
            and re.search(r"\b(reservoir|storage|opgaartenks?|tanks?|tenks?)\b", question) is not None)


def _timestamp(value):
    try:
        result = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (TypeError, ValueError):
        return None
