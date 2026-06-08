import re
from dataclasses import dataclass

from modules.oom_sakkie.llm_answer import compose_answer_with_llm
from modules.oom_sakkie.llm_router import route_with_llm
from modules.oom_sakkie.tools import RiskLevel, get_tool
from modules.oom_sakkie.trace_store import build_trace_id, hash_tool_result, write_trace


CONFIDENCE_FLOOR = 0.65
MAX_USER_TEXT_CHARS = 2000


ACTION_GUARD_PATTERN = re.compile(
    r"\b("
    r"delete|remove|save|create|update|edit|change|send|email|message|post|publish|"
    r"start|stop|switch on|switch off|turn on|turn off|open|close|run|activate|deactivate"
    r")\b",
    re.I,
)
ACTION_GUARD_DYNAMIC_PATTERN = re.compile(
    r"\b(turn|switch)\s+(?:\w+\s+){0,4}(on|off)\b",
    re.I,
)
CAPABILITY_PATTERN = re.compile(
    r"\b(what can you do|what can i ask|available checks|help|help me|how do i use)\b",
    re.I,
)


@dataclass(frozen=True)
class IntentMatch:
    intent: str
    tool_name: str
    confidence: float
    reason: str


RULES = [
    (
        re.compile(r"\b(system work|work status|approval status|waiting for approval|needs my approval|need my approval|what are you building|what did you build|builder status|forge status|patch status|deploy status|what needs review)\b", re.I),
        IntentMatch("system_work_status", "system_work_status", 0.95, "rule:system_work_status"),
    ),
    (
        re.compile(r"\b(operating brief|farm brief|daily brief|morning brief|status report|jarvis check|full farm check|what should i know|bring me up to speed)\b", re.I),
        IntentMatch("farm_operating_brief", "farm_operating_brief", 0.95, "rule:farm_operating_brief"),
    ),
    (
        re.compile(r"\b(business advisor|business growth|grow sales|grow the business|make money|generate money|what should we sell|what can we sell|what should i promote|sales opportunity|commercial focus|next offer)\b", re.I),
        IntentMatch("business_growth_brief", "business_growth_brief", 0.95, "rule:business_growth_brief"),
    ),
    (
        re.compile(r"\b(irrigation|water zone|water zones|watering|water anything|need to water|do we need to water|sprinkler|sprinklers|pump)\b", re.I),
        IntentMatch("irrigation_status", "irrigation_status", 0.95, "rule:irrigation_status"),
    ),
    (
        re.compile(r"\b(meat planning|meat pipeline|ready for meat|meat candidate|preorder|preorders|abattoir fallback|fallback abattoir|slaughter|slaughtering)\b", re.I),
        IntentMatch("meat_planning", "meat_planning", 0.95, "rule:meat_planning"),
    ),
    (
        re.compile(r"\b(pig allocation|allocation|allocate|purpose|livestock candidate|slow grower|slow growers|growth class|breeding candidate|which pigs.*sell|what pigs.*sell)\b", re.I),
        IntentMatch("pig_allocation", "pig_allocation_readiness", 0.95, "rule:pig_allocation_readiness"),
    ),
    (
        re.compile(r"\b(sales|sales dashboard|sales overview|sales issues|sales problem|sales problems|stock availability|available stock|sales stock|what.*available.*sale)\b", re.I),
        IntentMatch("sales_dashboard", "sales_dashboard", 0.95, "rule:sales_dashboard"),
    ),
    (
        re.compile(r"\b(how'?s the farm|how is the farm|farm overview|farm dashboard|dashboard summary|farm status|overall farm|what animals|animals.*farm|pigs.*farm|how many pigs|what about the pigs)\b", re.I),
        IntentMatch("dashboard_summary", "dashboard_summary", 0.95, "rule:dashboard_summary"),
    ),
    (
        re.compile(r"\b(attention|need(s)? attention|what needs|to do|todo|worry|anything today|problems today|today.*farm)\b", re.I),
        IntentMatch("farm_attention", "farm_attention_summary", 0.95, "rule:farm_attention"),
    ),
    (
        re.compile(r"\b(power.*(24|recent|yesterday|profile|trend)|battery.*(24|recent|yesterday|profile|trend)|solar.*(24|recent|yesterday|profile|trend))\b", re.I),
        IntentMatch("power_recent", "power_recent", 0.95, "rule:power_recent"),
    ),
    (
        re.compile(r"\b(power|battery|solar|sunsynk|grid|loadshedding|load shedding|inverter)\b", re.I),
        IntentMatch("power_current", "power_current", 0.95, "rule:power_current"),
    ),
    (
        re.compile(r"\b(weather forecast|forecast|next few days|next 3 days|rain forecast|wind forecast)\b", re.I),
        IntentMatch("weather_forecast", "weather_forecast", 0.95, "rule:weather_forecast"),
    ),
    (
        re.compile(r"\b(weather now|weather current|current weather|rain now|wind now|temperature now|temp now)\b", re.I),
        IntentMatch("weather_now", "weather_now", 0.95, "rule:weather_now"),
    ),
    (
        re.compile(r"\b(weather|rain|wind|temperature|temp|forecast today|today.*weather)\b", re.I),
        IntentMatch("weather_today", "weather_today", 0.95, "rule:weather_today"),
    ),
]


def handle_message(payload):
    text = str((payload or {}).get("text") or "").strip()[:MAX_USER_TEXT_CHARS]
    channel = str((payload or {}).get("channel") or "kiosk").strip()[:40]
    session_id = str((payload or {}).get("session_id") or "").strip()[:120]
    trace_id = build_trace_id()

    if not text:
        return {
            "success": False,
            "answer": "Ask me a farm question first.",
            "tool_used": "",
            "trace_id": trace_id,
            "risk_level": int(RiskLevel.READ_ONLY),
            "links": [],
            "stale_warnings": [],
            "safety_notes": [],
            "needs_clarification": True,
            "pipeline": _pipeline(
                route_source="empty",
                answer_source="local",
                state="needs_input",
            ),
            "trace_store": {"stored": False, "status": "not_written_empty_text"},
        }, 400

    match = classify_intent(text)
    if not match and is_unsupported_action_request(text):
        answer = (
            "This Oom Sakkie kiosk is read-only right now. "
            "Ask me to check farm attention, power, weather, irrigation status, pig readiness, meat planning, or sales stock."
        )
        trace = _trace_payload(
            trace_id=trace_id,
            channel=channel,
            session_id=session_id,
            user_text=text,
            intent="unsupported_action",
            confidence=0,
            tool_name="",
            tool_result={},
            answer=answer,
            risk_level=RiskLevel.READ_ONLY,
            stale_warnings=[],
            safety_notes=["No write, control, message, or physical action was performed."],
            links=[],
        )
        trace_status = write_trace(trace)
        return {
            "success": True,
            "answer": answer,
            "tool_used": "",
            "trace_id": trace_id,
            "risk_level": int(RiskLevel.READ_ONLY),
            "links": [],
            "stale_warnings": [],
            "safety_notes": ["No write, control, message, or physical action was performed."],
            "needs_clarification": True,
            "action_blocked": True,
            "pipeline": _pipeline(
                route_source="action_guard",
                answer_source="local",
                state="blocked",
            ),
            "trace_store": trace_status,
        }, 200

    if not match and is_capability_request(text):
        answer = (
            "I can do read-only farm checks right now: farm attention, current or recent power, "
            "weather now/today/forecast, irrigation status, farm dashboard, pig allocation, meat planning, and sales stock. "
            "I cannot send messages, change records, start irrigation, post publicly, or perform physical actions."
        )
        safety_notes = ["Capabilities only. No tool, write, control, message, or physical action was performed."]
        trace = _trace_payload(
            trace_id=trace_id,
            channel=channel,
            session_id=session_id,
            user_text=text,
            intent="capabilities",
            confidence=1.0,
            tool_name="",
            tool_result={"summary": answer},
            answer=answer,
            risk_level=RiskLevel.READ_ONLY,
            stale_warnings=[],
            safety_notes=safety_notes,
            links=[],
        )
        trace_status = write_trace(trace)
        return {
            "success": True,
            "answer": answer,
            "tool_used": "",
            "trace_id": trace_id,
            "risk_level": int(RiskLevel.READ_ONLY),
            "links": [],
            "stale_warnings": [],
            "safety_notes": safety_notes,
            "needs_clarification": False,
            "pipeline": _pipeline(
                route_source="capability",
                answer_source="local",
                state="answered",
            ),
            "trace_store": trace_status,
            "intent": {
                "name": "capabilities",
                "confidence": 1.0,
                "reason": "rule:capabilities",
            },
        }, 200

    if not match:
        llm_match = route_with_llm(text)
        if llm_match:
            if llm_match.needs_clarification:
                answer = llm_match.clarification_question or "Which farm system should I check?"
                trace = _trace_payload(
                    trace_id=trace_id,
                    channel=channel,
                    session_id=session_id,
                    user_text=text,
                    intent=llm_match.intent,
                    confidence=llm_match.confidence,
                    tool_name="",
                    tool_result={},
                    answer=answer,
                    risk_level=RiskLevel.READ_ONLY,
                    stale_warnings=[],
                    safety_notes=[],
                    links=[],
                )
                trace_status = write_trace(trace)
                return {
                    "success": True,
                    "answer": answer,
                    "tool_used": "",
                    "trace_id": trace_id,
                    "risk_level": int(RiskLevel.READ_ONLY),
                    "links": [],
                    "stale_warnings": [],
                    "safety_notes": [],
                    "needs_clarification": True,
                    "pipeline": _pipeline(
                        route_source="llm_router",
                        answer_source="local",
                        state="needs_clarification",
                        llm_router_used=True,
                    ),
                    "trace_store": trace_status,
                    "intent": {
                        "name": llm_match.intent,
                        "confidence": llm_match.confidence,
                        "reason": llm_match.reason,
                    },
                }, 200
            match = IntentMatch(
                llm_match.intent,
                llm_match.tool_name,
                llm_match.confidence,
                llm_match.reason,
            )

    if not match or match.confidence < CONFIDENCE_FLOOR:
        answer = "I am not sure which farm system to check. Ask about farm attention, power, or weather for this first version."
        trace = _trace_payload(
            trace_id=trace_id,
            channel=channel,
            session_id=session_id,
            user_text=text,
            intent="unknown",
            confidence=0,
            tool_name="",
            tool_result={},
            answer=answer,
            risk_level=RiskLevel.READ_ONLY,
            stale_warnings=[],
            safety_notes=[],
            links=[],
        )
        trace_status = write_trace(trace)
        return {
            "success": True,
            "answer": answer,
            "tool_used": "",
            "trace_id": trace_id,
            "risk_level": int(RiskLevel.READ_ONLY),
            "links": [],
            "stale_warnings": [],
            "safety_notes": [],
            "needs_clarification": True,
            "pipeline": _pipeline(
                route_source="unknown",
                answer_source="local",
                state="needs_clarification",
            ),
            "trace_store": trace_status,
        }, 200

    tool = get_tool(match.tool_name)
    if not tool:
        answer = "That tool is not available in this Oom Sakkie build."
        trace_status = write_trace(_trace_payload(
            trace_id, channel, session_id, text, match.intent, match.confidence,
            match.tool_name, {}, answer, RiskLevel.READ_ONLY, [], [], []
        ))
        return {
            "success": False,
            "answer": answer,
            "tool_used": match.tool_name,
            "trace_id": trace_id,
            "risk_level": int(RiskLevel.READ_ONLY),
            "links": [],
            "stale_warnings": [],
            "safety_notes": [],
            "needs_clarification": True,
            "pipeline": _pipeline(
                route_source=_route_source(match),
                answer_source="local",
                state="error",
            ),
            "trace_store": trace_status,
        }, 500

    tool_result = tool.handler({})
    stale_warnings = list(tool_result.get("stale_warnings") or [])
    safety_notes = list(tool_result.get("safety_notes") or [])
    links = list(tool_result.get("links") or [])
    if is_unsupported_action_request(text):
        safety_notes.append("I treated this as a read-only check. No write, message, control, or physical action was performed.")
    deterministic_answer = build_answer(tool_result, stale_warnings, safety_notes)
    composed_answer = compose_answer_with_llm(
        user_text=text,
        tool_name=tool.name,
        deterministic_answer=deterministic_answer,
        stale_warnings=stale_warnings,
        safety_notes=safety_notes,
        raw_context=tool_result.get("llm_context") or tool_result.get("raw") or tool_result,
    )
    answer = composed_answer or deterministic_answer
    answer_source = "llm_composer" if composed_answer else "deterministic"
    trace = _trace_payload(
        trace_id=trace_id,
        channel=channel,
        session_id=session_id,
        user_text=text,
        intent=match.intent,
        confidence=match.confidence,
        tool_name=tool.name,
        tool_result=tool_result,
        answer=answer,
        risk_level=tool.risk_level,
        stale_warnings=stale_warnings,
        safety_notes=safety_notes,
        links=links,
    )
    trace_status = write_trace(trace)

    return {
        "success": True,
        "answer": answer,
        "tool_used": tool.name,
        "trace_id": trace_id,
        "risk_level": int(tool.risk_level),
        "links": links,
        "stale_warnings": stale_warnings,
        "safety_notes": safety_notes,
        "needs_clarification": False,
        "pipeline": _pipeline(
            route_source=_route_source(match),
            answer_source=answer_source,
            state="answered",
            llm_router_used=_route_source(match) == "llm_router",
            llm_answer_used=answer_source == "llm_composer",
            tool_checked=True,
        ),
        "trace_store": trace_status,
        "intent": {
            "name": match.intent,
            "confidence": match.confidence,
            "reason": match.reason,
        },
    }, 200


def classify_intent(text):
    for pattern, match in RULES:
        if pattern.search(text or ""):
            return match
    return None


def is_unsupported_action_request(text):
    return bool(
        ACTION_GUARD_PATTERN.search(text or "")
        or ACTION_GUARD_DYNAMIC_PATTERN.search(text or "")
    )


def is_capability_request(text):
    return bool(CAPABILITY_PATTERN.search(text or ""))


def build_answer(tool_result, stale_warnings, safety_notes=None):
    summary = str(tool_result.get("summary") or "").strip()
    if not summary:
        summary = "I checked the farm system, but it did not return a summary."
    if stale_warnings:
        return f"{summary} Note: {stale_warnings[0]}"
    if safety_notes:
        return f"{summary} Note: {safety_notes[0]}"
    return summary


def _route_source(match):
    if not match:
        return "unknown"
    return "rule" if str(match.reason or "").startswith("rule:") else "llm_router"


def _pipeline(
    route_source,
    answer_source,
    state,
    llm_router_used=False,
    llm_answer_used=False,
    tool_checked=False,
):
    return {
        "route_source": route_source,
        "answer_source": answer_source,
        "state": state,
        "llm_router_used": bool(llm_router_used),
        "llm_answer_used": bool(llm_answer_used),
        "tool_checked": bool(tool_checked),
    }


def _trace_payload(
    trace_id,
    channel,
    session_id,
    user_text,
    intent,
    confidence,
    tool_name,
    tool_result,
    answer,
    risk_level,
    stale_warnings,
    safety_notes,
    links,
):
    return {
        "trace_id": trace_id,
        "channel": channel,
        "session_id": session_id,
        "user_text": user_text,
        "intent": intent,
        "confidence": confidence,
        "tool_name": tool_name,
        "tool_args_json": {},
        "tool_result_summary": str((tool_result or {}).get("summary") or "")[:1000],
        "tool_result_hash": hash_tool_result((tool_result or {}).get("raw") or tool_result),
        "answer": answer,
        "risk_level": int(risk_level),
        "stale_warnings_json": stale_warnings,
        "safety_notes_json": safety_notes,
        "links_json": links,
    }
