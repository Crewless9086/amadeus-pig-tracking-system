from dataclasses import asdict, dataclass
import re

from modules.oom_sakkie.agent_dry_run_store import allowed_agent_dry_run_slugs
from modules.oom_sakkie.specialists import list_specialist_manifests


@dataclass(frozen=True)
class AgentRuntimeManifest:
    slug: str
    name: str
    personality: str
    role: str
    status: str
    runtime_enabled: bool
    dispatch_enabled: bool
    autonomous_loops_enabled: bool
    memory_sources: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    risk_limit: int
    output_contract: tuple[str, ...]
    approval_rules: tuple[str, ...]
    routing_hints: tuple[str, ...]


_AGENT_PERSONALITIES = {
    "sentinel": "calm, skeptical safety reviewer",
    "forge": "precise senior builder and test planner",
    "prism": "quiet visual systems designer",
    "ledger": "commercially sharp business advisor",
    "atlas": "pattern-focused farm analyst",
    "rootline": "practical weather, crop, and irrigation specialist",
    "herdmaster": "grounded herd operations specialist",
    "butcher": "meat pipeline and pork opportunity planner",
    "beacon": "brand and market voice drafter",
    "quartermaster": "operations and supplies organizer",
    "gatekeeper": "strict approval and routing controller",
}

_AGENT_TOOLS = {
    "sentinel": ("system_work_status", "farm_operating_brief"),
    "forge": ("system_work_status",),
    "prism": ("system_work_status",),
    "ledger": ("business_growth_brief", "sales_dashboard", "meat_planning"),
    "atlas": ("farm_operating_brief", "dashboard_summary", "pig_allocation_readiness", "power_recent"),
    "rootline": ("weather_now", "weather_today", "weather_forecast", "irrigation_status"),
    "herdmaster": ("dashboard_summary", "pig_allocation_readiness", "meat_planning", "farm_attention_summary"),
    "butcher": ("business_growth_brief", "meat_planning", "sales_dashboard", "pig_allocation_readiness"),
    "beacon": ("business_growth_brief", "sales_dashboard"),
    "quartermaster": ("farm_attention_summary", "dashboard_summary", "system_work_status"),
    "gatekeeper": ("system_work_status", "farm_operating_brief"),
}

_TOOL_PRIMARY_AGENT = {
    "agent_activation_plan": "gatekeeper",
    "agent_dry_run_status": "gatekeeper",
    "agent_crew_brief": "gatekeeper",
    "agent_crew_status": "gatekeeper",
    "sentinel_dry_run_review": "sentinel",
    "system_work_status": "forge",
    "farm_operating_brief": "atlas",
    "business_growth_brief": "ledger",
    "farm_attention_summary": "quartermaster",
    "power_current": "atlas",
    "power_recent": "atlas",
    "weather_now": "rootline",
    "weather_today": "rootline",
    "weather_forecast": "rootline",
    "irrigation_status": "rootline",
    "dashboard_summary": "herdmaster",
    "pig_allocation_readiness": "herdmaster",
    "meat_planning": "butcher",
    "sales_dashboard": "ledger",
}

_AGENT_COLOR = {
    "sentinel": "red",
    "forge": "blue",
    "prism": "violet",
    "ledger": "green",
    "atlas": "cyan",
    "rootline": "teal",
    "herdmaster": "amber",
    "butcher": "rose",
    "beacon": "magenta",
    "quartermaster": "olive",
    "gatekeeper": "white",
}

_ROUTING_PATTERNS = (
    ("sentinel", re.compile(r"\b(safety|security|risk|policy|secret|is this safe|review this)\b", re.I)),
    ("forge", re.compile(r"\b(build|code|patch|forge|test|deploy|implementation|fix the app)\b", re.I)),
    ("prism", re.compile(r"\b(ui|design|screen|interface|layout|visual|jarvis look|messy)\b", re.I)),
    ("ledger", re.compile(r"\b(money|profit|margin|business|revenue|price|cash|sell|sales)\b", re.I)),
    ("atlas", re.compile(r"\b(trend|anomaly|analytics|pattern|why is|compare|history)\b", re.I)),
    ("rootline", re.compile(r"\b(weather|rain|wind|irrigation|water|crop|plant|pump)\b", re.I)),
    ("herdmaster", re.compile(r"\b(pig|herd|litter|weight|wean|breeding|pen)\b", re.I)),
    ("butcher", re.compile(r"\b(meat|pork|slaughter|abattoir|preorder|butcher|carcass)\b", re.I)),
    ("beacon", re.compile(r"\b(media|post|facebook|instagram|marketing|advert|campaign|public)\b", re.I)),
    ("quartermaster", re.compile(r"\b(task|supply|inventory|shopping|feed|medicine|todo|to do)\b", re.I)),
    ("gatekeeper", re.compile(r"\b(approve|approval|allowed|permission|gate|who should handle)\b", re.I)),
)


_CREW_BRIEF_PATTERNS = (
    ("commercial_growth", re.compile(r"\b(grow|business|money|sales|sell|offer|marketing|market|revenue|profit)\b", re.I)),
    ("farm_operations", re.compile(r"\b(farm|operating|attention|today|status|brief|priority|worry|inspect)\b", re.I)),
    ("pig_pipeline", re.compile(r"\b(pig|herd|meat|pork|slaughter|abattoir|weaner|litter|pen)\b", re.I)),
    ("system_build", re.compile(r"\b(build|code|patch|deploy|fix|improve|forge|system|approval)\b", re.I)),
    ("weather_irrigation", re.compile(r"\b(weather|rain|wind|irrigation|water|pump|crop)\b", re.I)),
)

_CREW_BRIEF_AGENTS = {
    "commercial_growth": ("ledger", "butcher", "beacon", "sentinel", "gatekeeper"),
    "farm_operations": ("quartermaster", "atlas", "rootline", "herdmaster", "gatekeeper"),
    "pig_pipeline": ("herdmaster", "butcher", "ledger", "sentinel", "gatekeeper"),
    "system_build": ("sentinel", "forge", "prism", "gatekeeper"),
    "weather_irrigation": ("rootline", "atlas", "quartermaster", "gatekeeper"),
    "general": ("gatekeeper", "atlas", "quartermaster", "sentinel"),
}

_ACTIVATION_STAGES = (
    {
        "stage": "foundation_visible",
        "status": "ready",
        "summary": "Planned agents, personalities, tool allowlists, visual workspaces, handoff lane, and crew sequence are visible.",
    },
    {
        "stage": "read_only_dry_run",
        "status": "next",
        "summary": "Let one specialist produce advisory-only analysis from existing read-only tool results, with no new tool authority.",
    },
    {
        "stage": "human_approved_dispatch",
        "status": "locked",
        "summary": "Dispatch a specialist only after an explicit owner approval gate and append-only audit record exist.",
    },
    {
        "stage": "draft_only_outputs",
        "status": "locked",
        "summary": "Allow draft-only business, marketing, or build proposals after review gates are proven.",
    },
    {
        "stage": "controlled_writes",
        "status": "locked",
        "summary": "Only after weeks of read-only/draft-only use: add idempotent, confirmed, owner-approved write paths.",
    },
)

_FIRST_ACTIVATION_CANDIDATES = (
    {
        "slug": "sentinel",
        "reason": "Smallest safe first live slice: review risk, policy, and no-go rules without touching farm data.",
        "first_slice": "Advisory-only review of one trace/build/answer decision; no tools beyond existing status/read context.",
    },
    {
        "slug": "prism",
        "reason": "Useful for kiosk clarity without farm-data authority.",
        "first_slice": "Advisory-only UI review of one visible panel; output a review note, not a patch.",
    },
    {
        "slug": "atlas",
        "reason": "Useful farm intelligence, but should wait until read-only dry-run/audit patterns are proven.",
        "first_slice": "Advisory-only explanation of one read-only operating brief; no new backend calls.",
    },
    {
        "slug": "ledger",
        "reason": "Turns sales and pork-pipeline context into business questions without customer output.",
        "first_slice": "Advisory-only review of one business-growth brief; no pricing, quote, invoice, or customer message.",
    },
    {
        "slug": "rootline",
        "reason": "Weather and irrigation advice is high-value but must remain read-only before any physical control path exists.",
        "first_slice": "Advisory-only review of one weather/irrigation brief; no pump, valve, schedule, or hardware command.",
    },
    {
        "slug": "herdmaster",
        "reason": "Herd and litter attention can guide daily checks without changing pig records.",
        "first_slice": "Advisory-only review of one herd/litter attention brief; no pig, litter, medical, pen, or weight write.",
    },
    {
        "slug": "butcher",
        "reason": "Pork pipeline planning helps revenue without creating sales or bookings.",
        "first_slice": "Advisory-only review of one meat-planning brief; no slaughter booking, reservation, sale, or customer message.",
    },
    {
        "slug": "quartermaster",
        "reason": "Operations and supplies planning can organize work without purchasing or messaging suppliers.",
        "first_slice": "Advisory-only review of one farm-attention brief; no purchase, stock update, supplier message, or task write.",
    },
)


def list_agent_runtime_manifests():
    specialists = {item["slug"]: item for item in list_specialist_manifests()}
    return [
        asdict(_runtime_manifest(slug, specialists[slug]))
        for slug in sorted(specialists)
    ]


def get_agent_runtime_status():
    agents = list_agent_runtime_manifests()
    return {
        "success": True,
        "mode": "advisory_runtime_foundation",
        "runtime_enabled": False,
        "dispatch_enabled": False,
        "autonomous_loops_enabled": False,
        "writes_enabled": False,
        "agent_count": len(agents),
        "agents": agents,
        "next_gate": "owner_approval_before_live_agent_dispatch",
    }


def get_agent_activation_plan():
    agents = {item["slug"]: item for item in list_agent_runtime_manifests()}
    dry_run_allowed = allowed_agent_dry_run_slugs()
    candidates = []
    for item in _FIRST_ACTIVATION_CANDIDATES:
        agent = agents[item["slug"]]
        candidates.append({
            "slug": agent["slug"],
            "name": agent["name"],
            "personality": agent["personality"],
            "color": _AGENT_COLOR.get(agent["slug"], "white"),
            "reason": item["reason"],
            "first_slice": item["first_slice"],
            "allowed_now": False,
            "dry_run_request_allowed": agent["slug"] in dry_run_allowed,
            "requires_owner_approval": True,
        })
    return {
        "success": True,
        "mode": "activation_plan_only",
        "runtime_enabled": False,
        "dispatch_enabled": False,
        "autonomous_loops_enabled": False,
        "writes_enabled": False,
        "recommended_next_stage": "read_only_dry_run",
        "recommended_first_candidate": candidates[0],
        "stages": list(_ACTIVATION_STAGES),
        "first_candidates": candidates,
        "locked_until": [
            "owner approves a first read-only specialist dry-run",
            "append-only dispatch/audit trail exists",
            "dry-run output is reviewed manually",
            "Claude/Codex review confirms no widened authority",
        ],
        "blocked_capabilities": [
            "live specialist dispatch",
            "specialist autonomous loops",
            "specialist write tools",
            "customer/public output",
            "physical controls",
            "Builder/Forge execution from kiosk",
            "patch application",
            "deploy execution",
        ],
        "next_gate": "owner_approval_before_read_only_specialist_dry_run",
    }


def build_sentinel_dry_run_review(tool_catalog):
    agents = {item["slug"]: item for item in list_agent_runtime_manifests()}
    sentinel = agents["sentinel"]
    tools = list(tool_catalog or [])
    read_only_tools = [
        str(item.get("name") or "")
        for item in tools
        if int(item.get("risk_level") or 0) == 0 and not item.get("requires_confirmation")
    ]
    non_read_only_tools = [
        str(item.get("name") or "")
        for item in tools
        if int(item.get("risk_level") or 0) != 0
    ]
    confirmation_tools = [
        str(item.get("name") or "")
        for item in tools
        if item.get("requires_confirmation")
    ]
    blockers = [
        "append-only specialist dispatch/audit trail is not built yet",
        "owner approval gate for a live specialist dry-run is not built yet",
        "specialist runtime dispatch flag is still false",
        "specialist LLM execution remains disabled",
    ]
    if non_read_only_tools:
        blockers.append("non-read-only tool(s) exist and must stay outside Sentinel dry-run authority")
    if confirmation_tools:
        blockers.append("confirmation-required tool(s) exist and must stay outside Sentinel dry-run authority")

    return {
        "success": True,
        "mode": "sentinel_dry_run_review_only",
        "selected_agent": sentinel,
        "recommended_stage": "read_only_dry_run",
        "allowed_now": "advisory_review_only",
        "can_dispatch_specialist": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "runtime_flags": {
            "dispatch_enabled": False,
            "autonomous_loops_enabled": False,
            "writes_enabled": False,
            "specialist_llm_enabled": False,
        },
        "tool_audit": {
            "total_tools": len(tools),
            "read_only_tools": read_only_tools,
            "non_read_only_tools": non_read_only_tools,
            "requires_confirmation_tools": confirmation_tools,
        },
        "blockers_before_live_dry_run": blockers,
        "recommendation": (
            "Continue with Sentinel as an advisory-only dry-run review. Do not enable live dispatch until "
            "owner approval, append-only dispatch audit, and a separate review pass exist."
        ),
        "next_gate": "owner_approval_before_read_only_specialist_dry_run",
    }


def recommend_agent_for_text(text):
    clean = str(text or "").strip()[:500]
    agents = {item["slug"]: item for item in list_agent_runtime_manifests()}
    slug = "gatekeeper"
    reason = "fallback:gatekeeper"
    for candidate, pattern in _ROUTING_PATTERNS:
        if pattern.search(clean):
            slug = candidate
            reason = f"rule:{candidate}"
            break
    agent = agents.get(slug) or agents["gatekeeper"]
    return {
        "success": True,
        "mode": "dispatch_recommendation_only",
        "dispatch_enabled": False,
        "autonomous_loops_enabled": False,
        "runs_agent": False,
        "writes": False,
        "selected_agent": agent,
        "reason": reason,
        "owner_text": clean,
        "next_gate": "owner_approval_before_live_agent_dispatch",
    }


def build_agent_crew_brief(text):
    clean = str(text or "").strip()[:500]
    agents = {item["slug"]: item for item in list_agent_runtime_manifests()}
    scenario = "general"
    reason = "fallback:general"
    for candidate, pattern in _CREW_BRIEF_PATTERNS:
        if pattern.search(clean):
            scenario = candidate
            reason = f"rule:{candidate}"
            break

    sequence = []
    for index, slug in enumerate(_CREW_BRIEF_AGENTS.get(scenario, _CREW_BRIEF_AGENTS["general"]), start=1):
        agent = agents[slug]
        sequence.append({
            "order": index,
            "slug": agent["slug"],
            "name": agent["name"],
            "personality": agent["personality"],
            "role": agent["role"],
            "color": _AGENT_COLOR.get(agent["slug"], "white"),
            "would_inspect": _crew_inspection_for(agent["slug"], scenario),
            "allowed_tools": list(agent["allowed_tools"]),
            "runs_agent": False,
            "writes": False,
        })

    return {
        "success": True,
        "mode": "crew_plan_only",
        "scenario": scenario,
        "reason": reason,
        "owner_text": clean,
        "controller": "oom_sakkie",
        "sequence": sequence,
        "safety": {
            "runs_agents": False,
            "dispatch_enabled": False,
            "autonomous_loops_enabled": False,
            "writes": False,
            "requires_owner_approval_for_execution": True,
        },
        "next_gate": "owner_approval_before_live_multi_agent_dispatch",
    }


def build_agent_activity(*, tool_name, user_text="", tool_result=None):
    agents = {item["slug"]: item for item in list_agent_runtime_manifests()}
    selected = None
    result_context = (tool_result or {}).get("llm_context") if isinstance(tool_result, dict) else {}
    if isinstance(result_context, dict):
        selected = result_context.get("selected_agent")
    if isinstance(selected, dict) and selected.get("slug") in agents:
        slug = selected["slug"]
        reason = "tool_context:selected_agent"
    else:
        slug = _TOOL_PRIMARY_AGENT.get(str(tool_name or ""), "gatekeeper")
        reason = f"tool_map:{tool_name or 'unknown'}"
    agent = agents.get(slug) or agents["gatekeeper"]
    return {
        "success": True,
        "mode": "visual_activity_only",
        "controller": "oom_sakkie",
        "active_agent": {
            "slug": agent["slug"],
            "name": agent["name"],
            "personality": agent["personality"],
            "role": agent["role"],
            "color": _AGENT_COLOR.get(agent["slug"], "white"),
        },
        "workspace": {
            "title": f"{agent['name']} workspace",
            "state": "reviewing_read_only_result",
            "tool_name": str(tool_name or ""),
            "reason": reason,
            "owner_text": str(user_text or "")[:500],
            "visible_to_owner": True,
        },
        "crew_sequence": _activity_crew_sequence(result_context),
        "handoff_lane": _handoff_lane(agent=agent, tool_name=tool_name, reason=reason),
        "safety": {
            "runs_agent": False,
            "dispatch_enabled": False,
            "autonomous_loops_enabled": False,
            "writes": False,
        },
    }


def _activity_crew_sequence(result_context):
    if not isinstance(result_context, dict):
        return []
    brief = result_context.get("crew_brief")
    if not isinstance(brief, dict):
        return []
    sequence = []
    for item in (brief.get("sequence") or [])[:6]:
        if not isinstance(item, dict):
            continue
        sequence.append({
            "order": item.get("order"),
            "slug": item.get("slug"),
            "name": item.get("name"),
            "personality": item.get("personality"),
            "role": item.get("role"),
            "color": item.get("color") or _AGENT_COLOR.get(str(item.get("slug") or ""), "white"),
            "would_inspect": item.get("would_inspect"),
            "runs_agent": False,
            "writes": False,
        })
    return sequence


def _handoff_lane(*, agent, tool_name, reason):
    return [
        {
            "step": "controller",
            "actor": "Oom Sakkie",
            "status": "received",
            "detail": "Owner request bounded to one read-only turn.",
        },
        {
            "step": "specialist_workspace",
            "actor": agent["name"],
            "status": "visible_only",
            "detail": f"{agent['personality']} workspace opened from {reason}.",
        },
        {
            "step": "read_only_tool",
            "actor": str(tool_name or "none"),
            "status": "checked",
            "detail": "Existing backend read-only tool supplied the facts.",
        },
        {
            "step": "owner_gate",
            "actor": "Owner approval",
            "status": "required_for_action",
            "detail": "No write, post, sale, control, patch, or deploy can run here.",
        },
    ]


def _crew_inspection_for(slug, scenario):
    inspections = {
        "ledger": {
            "commercial_growth": "sales stock, margin angle, buyer segment, and internal offer outline",
            "pig_pipeline": "whether the pig pipeline has a clean commercial outlet",
            "general": "commercial impact and next approved sales move",
        },
        "butcher": {
            "commercial_growth": "ready meat candidates and slaughter/preorder timing",
            "pig_pipeline": "meat readiness, weight, pen, and abattoir fallback",
            "general": "pork and meat-pipeline implications",
        },
        "beacon": {
            "commercial_growth": "future draft-only marketing angle after owner approval",
            "general": "draft-only market voice, never public output without approval",
        },
        "sentinel": {
            "commercial_growth": "risk, customer/public-output boundary, and approval requirements",
            "system_build": "safety policy, no-go rules, and review gates",
            "pig_pipeline": "welfare/safety risk before commercial action",
            "general": "risk and approval boundaries",
        },
        "gatekeeper": {
            "commercial_growth": "what requires owner approval before action",
            "farm_operations": "who should handle the next read-only check",
            "pig_pipeline": "approval route before any sale or operational change",
            "system_build": "builder, patch, and deploy approval gates",
            "general": "routing and owner approval",
        },
        "quartermaster": {
            "farm_operations": "daily attention queue, supplies, and practical next checks",
            "weather_irrigation": "whether weather or irrigation creates work today",
            "general": "operational tasks and supplies",
        },
        "atlas": {
            "farm_operations": "patterns across attention, power, weather, and dashboard signals",
            "weather_irrigation": "power/weather trend and whether data looks stale",
            "general": "analytics and anomalies",
        },
        "rootline": {
            "farm_operations": "weather and irrigation conditions that affect work today",
            "weather_irrigation": "weather, rain, wind, irrigation status, and read-only water checks",
            "general": "weather and irrigation",
        },
        "herdmaster": {
            "farm_operations": "pig lifecycle, pens, litters, and herd attention items",
            "pig_pipeline": "herd readiness, pen context, weights, and lifecycle implications",
            "general": "herd operations",
        },
        "forge": {
            "system_build": "implementation files, tests, risks, and patch proposal shape",
            "general": "builder plan and verification",
        },
        "prism": {
            "system_build": "UI clarity, layout, and visual review before owner approval",
            "general": "visual design and kiosk usability",
        },
    }
    agent_inspections = inspections.get(slug, {})
    return agent_inspections.get(scenario) or agent_inspections.get("general") or "read-only specialist review"


def _runtime_manifest(slug, specialist):
    return AgentRuntimeManifest(
        slug=slug,
        name=specialist["name"],
        personality=_AGENT_PERSONALITIES.get(slug, "focused specialist"),
        role=specialist["role"],
        status="foundation_ready",
        runtime_enabled=False,
        dispatch_enabled=False,
        autonomous_loops_enabled=False,
        memory_sources=(
            "current_tool_results",
            "reviewed_traces",
            "current_state_docs",
            "approved_business_rules",
        ),
        allowed_tools=_AGENT_TOOLS.get(slug, ()),
        risk_limit=int(specialist["risk_level"]),
        output_contract=specialist["first_outputs"],
        approval_rules=specialist["approval_required_for"],
        routing_hints=_routing_hints_for(slug),
    )


def _routing_hints_for(slug):
    hints = {
        "sentinel": ("safety", "security", "policy", "risk review"),
        "forge": ("code", "tests", "patches", "builder plans"),
        "prism": ("kiosk UI", "visual design", "layout"),
        "ledger": ("profit", "sales", "business growth", "margin"),
        "atlas": ("trends", "anomalies", "analytics"),
        "rootline": ("weather", "irrigation", "plants"),
        "herdmaster": ("pig lifecycle", "litters", "weights"),
        "butcher": ("meat pipeline", "pork sales", "slaughter readiness"),
        "beacon": ("media", "marketing", "public drafts"),
        "quartermaster": ("tasks", "supplies", "operations"),
        "gatekeeper": ("approval", "routing", "permissions"),
    }
    return hints.get(slug, ())
