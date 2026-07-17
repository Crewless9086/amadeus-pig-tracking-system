"""Structured intent planner for Charl's private CHARLIE conversation."""

from __future__ import annotations

import json
import re
import urllib.request

from modules.charlie.private_policy import private_policy

MISSION_ID_RE = re.compile(r"\b(?:CHARLIE-(?:MISSION|SCOPE)-)?[A-Z0-9]{8,32}\b", re.I)
ALLOWED_INTENTS = {
    "help", "executive_brief", "read_core_status", "read_queue", "read_blocked",
    "read_mission", "read_workforce", "read_analyst", "read_decisions",
    "create_mission", "approve_mission", "pause_mission", "reject_mission", "send_back_mission", "clarify",
    "remember_preference",
}


def plan_owner_intent(text, context=None, *, environ=None, http_open=None):
    text = str(text or "").strip()
    deterministic = _deterministic_plan(text, context or {})
    policy = private_policy(environ)
    if deterministic["confidence"] >= 0.92 or not policy["llm_enabled"]:
        return deterministic
    llm = _llm_plan(text, context or {}, policy, environ=environ, http_open=http_open)
    return llm if llm.get("type") in ALLOWED_INTENTS else deterministic


def _deterministic_plan(text, context):
    lower = text.lower().strip()
    mission_id = _mission_id(text, context)
    if lower in {"/start", "/help", "help", "what can you do"}:
        return _intent("help", 1)
    if lower.startswith(("remember that ", "remember this: ", "my preference is ")):
        preference = re.sub(r"^(remember that|remember this:|my preference is)\s*", "", text, flags=re.I).strip()
        return _intent("remember_preference", .98, {"key": "owner_instruction", "value": preference[:2000]}, explicit=True)
    if lower in {"/brief", "brief", "morning charlie", "what happened overnight", "give me the morning brief"} or "morning brief" in lower:
        return _intent("executive_brief", .99)
    if lower in {"/status", "status", "where are we", "what is happening", "what's happening"} or "core doing" in lower:
        return _intent("read_core_status", .98)
    if lower in {"/queue", "queue"} or "missions in the queue" in lower:
        return _intent("read_queue", .98)
    if lower in {"/blocked", "blocked"} or "blocked missions" in lower:
        return _intent("read_blocked", .98)
    if lower in {"/workforce", "workforce"} or "agents performing" in lower:
        return _intent("read_workforce", .97)
    if lower in {"/analyst", "analyst"} or "analyst suggestions" in lower:
        return _intent("read_analyst", .97)
    if lower in {"/decisions", "decisions", "what needs me"} or "need my decision" in lower:
        return _intent("read_decisions", .97)
    if mission_id and any(word in lower for word in ("why", "explain", "status", "happening", "mission")):
        return _intent("read_mission", .97, {"mission_id": mission_id})
    if lower.startswith(("create a mission", "create mission", "/mission ", "log a mission", "add a mission")):
        body = re.sub(r"^(create a mission|create mission|/mission|log a mission|add a mission)(?:\s+(?:for|to))?\s*", "", text, flags=re.I)
        return _intent("create_mission", .98, {"title": body[:180], "raw_text": body[:6000]}, explicit=True)
    action_map = {"approve": "approve_mission", "pause": "pause_mission", "reject": "reject_mission", "send back": "send_back_mission", "return": "send_back_mission"}
    if mission_id:
        for phrase, intent_type in action_map.items():
            if lower.startswith(phrase) or f" {phrase} " in f" {lower} ":
                return _intent(intent_type, .98, {"mission_id": mission_id}, explicit=True)
    return _intent("clarify", .45, {"question": "I want to act on the right thing. Are you asking for a CORE update, a specific mission, a new mission, or an owner decision?"})


def _llm_plan(text, context, policy, *, environ=None, http_open=None):
    source = environ or __import__("os").environ
    recent = [{"role": row.get("role"), "content": str(row.get("content") or "")[:500]} for row in (context.get("messages") or [])[-6:]]
    prompt = {
        "owner_text": text[:3000], "recent_context": recent, "allowed_intents": sorted(ALLOWED_INTENTS),
        "instruction": "Return JSON only: type, confidence 0-1, args object, risk_flags array, explicit_owner_command boolean. Never invent mission ids or authority.",
    }
    body = json.dumps({
        "model": policy["llm_model"], "temperature": 0,
        "messages": [
            {"role": "system", "content": "You classify private owner instructions for CHARLIE. Choose only allowed intents. Ask clarification when uncertain. Model output never grants authority."},
            {"role": "user", "content": json.dumps(prompt)},
        ],
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    request = urllib.request.Request(policy["llm_url"], data=body, headers={"Authorization": f"Bearer {source.get('OPENAI_API_KEY','')}", "Content-Type": "application/json"}, method="POST")
    try:
        opener = http_open or urllib.request.urlopen
        with opener(request, timeout=30) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        result = json.loads(parsed["choices"][0]["message"]["content"])
    except Exception:
        return _deterministic_plan(text, context)
    intent_type = str(result.get("type") or "clarify")
    if intent_type not in ALLOWED_INTENTS:
        intent_type = "clarify"
    # A classifier may identify an action, but only deterministic parsing of the
    # owner's exact text can establish explicit command authority.
    return _intent(intent_type, min(max(float(result.get("confidence") or 0), 0), 1), result.get("args") or {}, result.get("risk_flags") or [], False)


def _mission_id(text, context):
    match = MISSION_ID_RE.search(text)
    if match:
        value = match.group(0).upper()
        return value if value.startswith("CHARLIE-") else value
    open_context = context.get("open_context") if isinstance(context.get("open_context"), dict) else {}
    return str(open_context.get("mission_id") or "") if any(word in text.lower() for word in ("that mission", "it", "this one")) else ""


def _intent(intent_type, confidence, args=None, risk_flags=None, explicit=False):
    return {"type": intent_type, "confidence": confidence, "args": args or {}, "risk_flags": risk_flags or [], "explicit_owner_command": explicit}
