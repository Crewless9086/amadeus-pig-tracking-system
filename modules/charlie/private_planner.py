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
    "read_business_status", "read_sam_status", "read_beacon_status", "read_orders_status", "read_farm_status",
    "create_mission", "approve_mission", "pause_mission", "reject_mission", "send_back_mission", "clarify",
    "remember_preference",
    "protected_business_action",
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
    open_context = context.get("open_context") if isinstance(context.get("open_context"), dict) else {}
    active_subject = open_context.get("active_subject") if isinstance(open_context.get("active_subject"), dict) else {}
    if lower in {"/start", "/help", "help", "what can you do"}:
        return _intent("help", 1)
    if lower.startswith(("remember that ", "remember this: ", "my preference is ")):
        preference = re.sub(r"^(remember that|remember this:|my preference is)\s*", "", text, flags=re.I).strip()
        return _intent("remember_preference", .98, {"key": "owner_instruction", "value": preference[:2000]}, explicit=True)
    protected = _protected_action(text)
    if protected:
        return _intent("protected_business_action", .99, {"action_summary": text[:2000]}, [protected], explicit=True)
    if lower in {"/brief", "brief", "morning charlie", "what happened overnight", "give me the morning brief"} or "morning brief" in lower:
        return _intent("executive_brief", .99)
    active_mission_question = "mission" in lower and any(
        phrase in lower for phrase in ("running now", "active mission", "currently running", "running mission", "working on now")
    )
    if active_mission_question or lower in {"/status", "status", "where are we", "what is happening", "what's happening"} or "core doing" in lower or ("core" in lower and any(word in lower for word in ("happening", "status", "running", "doing", "progress"))):
        return _intent("read_core_status", .98)
    if lower in {"why", "why?", "what changed", "any update", "update", "how is it going", "what happens next"}:
        if active_subject.get("type") == "mission" and active_subject.get("mission_id"):
            return _intent("read_mission", .98, {"mission_id": active_subject["mission_id"]})
        if open_context.get("last_intent") in {"read_core_status", "executive_brief"}:
            return _intent("read_core_status", .98)
    if lower in {"/business", "business", "business status", "how is the business"}:
        return _intent("read_business_status", .98)
    if lower in {"/sam", "sam", "sam status", "how is sam"} or "livestock sales agent" in lower:
        return _intent("read_sam_status", .98)
    if lower in {"/beacon", "beacon", "beacon status", "marketing status"} or "how is beacon" in lower:
        return _intent("read_beacon_status", .98)
    if lower in {"/orders", "orders", "orders status", "sales orders"}:
        return _intent("read_orders_status", .98)
    if lower in {"/farm", "farm", "farm status", "farm operations"}:
        return _intent("read_farm_status", .98)
    if lower in {"/queue", "queue", "/next", "/missions", "missions"} or "missions in the queue" in lower:
        return _intent("read_queue", .98)
    if lower in {"/blocked", "blocked"} or "blocked missions" in lower:
        return _intent("read_blocked", .98)
    if lower in {"/workforce", "workforce"} or "agents performing" in lower:
        return _intent("read_workforce", .97)
    if lower in {"/analyst", "analyst"} or "analyst suggestions" in lower:
        return _intent("read_analyst", .97)
    if lower in {"/decisions", "decisions", "/review", "review", "what needs me"} or "need my decision" in lower:
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
    args = result.get("args") if isinstance(result.get("args"), dict) else {}
    if intent_type == "read_mission" and not str(args.get("mission_id") or "").strip():
        return _intent("clarify", .5, {"question": "Which CORE mission do you want me to inspect? Send its mission ID."})
    # A classifier may identify an action, but only deterministic parsing of the
    # owner's exact text can establish explicit command authority.
    return _intent(intent_type, min(max(float(result.get("confidence") or 0), 0), 1), args, result.get("risk_flags") or [], False)


def _mission_id(text, context):
    match = MISSION_ID_RE.search(text)
    if match:
        value = match.group(0).upper()
        if value.startswith("CHARLIE-") or any(char.isdigit() for char in value):
            return value
    open_context = context.get("open_context") if isinstance(context.get("open_context"), dict) else {}
    subject = open_context.get("active_subject") if isinstance(open_context.get("active_subject"), dict) else {}
    return str(subject.get("mission_id") or open_context.get("mission_id") or "") if any(word in text.lower() for word in ("that mission", "it", "this one")) else ""


def _intent(intent_type, confidence, args=None, risk_flags=None, explicit=False):
    return {"type": intent_type, "confidence": confidence, "args": args or {}, "risk_flags": risk_flags or [], "explicit_owner_command": explicit}


def _protected_action(text):
    lower = str(text or "").lower()
    groups = (
        ("customer_send", ("send the quote", "send quote", "message the customer", "send to the customer")),
        ("public_post", ("publish the post", "post this ad", "boost the post", "publish this")),
        ("payment", ("take payment", "confirm payment", "mark as paid", "confirm deposit")),
        ("reservation", ("reserve the pigs", "reserve stock", "move stock")),
        ("lifecycle_write", ("mark the pig sold", "change lifecycle", "change purpose")),
        ("destructive_migration", ("delete production", "drop table", "destructive migration")),
        ("credential_access", ("show me the api key", "send me the password", "reveal the token")),
    )
    return next((risk for risk, phrases in groups if any(phrase in lower for phrase in phrases)), "")
