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
    "gatekeeper": ("agent_command_center", "jarvis_daily_command_brief", "system_work_status", "farm_operating_brief"),
}

_TOOL_PRIMARY_AGENT = {
    "agent_activation_plan": "gatekeeper",
    "agent_activation_preflight": "gatekeeper",
    "agent_authority_matrix": "gatekeeper",
    "agent_authority_unlock_readiness": "gatekeeper",
    "agent_command_center": "gatekeeper",
    "jarvis_daily_command_brief": "gatekeeper",
    "agent_dispatch_decision_rail_blueprint": "gatekeeper",
    "agent_runtime_review_packet": "gatekeeper",
    "agent_operating_contracts": "gatekeeper",
    "agent_runtime_readiness": "gatekeeper",
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

_AGENT_CONTRACT_FOCUS = {
    "sentinel": "Guardrails, unsafe requests, no-go rules, secrets exposure, audit gaps, and approval boundaries.",
    "forge": "Implementation plans, file impact, test plans, and patch/deploy readiness after owner approval.",
    "prism": "Kiosk layout clarity, visual hierarchy, operator flow, and Jarvis-style presence without hidden automation.",
    "ledger": "Business growth, sales stock, meat-pipeline opportunity, margins, and internal-only offer thinking.",
    "atlas": "Farm trends, anomalies, operating history, telemetry patterns, and cross-system explanations.",
    "rootline": "Weather, rain, wind, irrigation status, crop context, and stale physical-environment assumptions.",
    "herdmaster": "Pig, litter, weight, pen, and herd attention questions from existing read-only records.",
    "butcher": "Pork pipeline, slaughter readiness, stock opportunity, and internal meat planning.",
    "beacon": "Draft-only public voice and campaign ideas after later approval; locked out of dry-run request gate for now.",
    "quartermaster": "Farm attention, supplies, task-like operating context, and daily work organization.",
    "gatekeeper": "Routing, approval state, runtime readiness, locked gates, and what may happen next.",
}

_AGENT_CONTRACT_MUST_NOT = {
    "sentinel": (
        "run live specialists",
        "approve its own findings",
        "change policies",
        "read secrets",
    ),
    "forge": (
        "edit files from the kiosk",
        "apply patches",
        "run deploys",
        "skip owner patch review",
    ),
    "prism": (
        "edit UI files",
        "generate public assets automatically",
        "hide safety text",
        "start polling loops",
    ),
    "ledger": (
        "change prices",
        "create quotes or invoices",
        "send customer messages",
        "reserve stock",
    ),
    "atlas": (
        "write analytics back to farm data",
        "change telemetry sources",
        "claim uncertain correlations as facts",
        "override stale warnings",
    ),
    "rootline": (
        "start pumps or valves",
        "change irrigation schedules",
        "issue physical-control commands",
        "treat stale weather as current",
    ),
    "herdmaster": (
        "change pig records",
        "record medical actions",
        "move pens",
        "enter weights",
    ),
    "butcher": (
        "book slaughter",
        "create sales",
        "reserve pigs or meat",
        "message customers",
    ),
    "beacon": (
        "post publicly",
        "message customers",
        "publish marketing",
        "speak as Sam",
    ),
    "quartermaster": (
        "purchase supplies",
        "message suppliers",
        "write tasks",
        "change stock records",
    ),
    "gatekeeper": (
        "bypass owner approval",
        "enable runtime flags",
        "cut over Telegram",
        "weaken access controls",
    ),
}

_AGENT_CONTRACT_OWNER_GATES = {
    "sentinel": "Owner accepts dry-run learning before it can influence future planning.",
    "forge": "Owner approves plan, patch proposal, and manual deploy decision outside the kiosk.",
    "prism": "Owner approves any visual/code change through the build and patch gates.",
    "ledger": "Owner approves any quote, price, invoice, customer message, or sale workflow separately.",
    "atlas": "Owner approves any new analytics source, recurring analysis, or dashboard change separately.",
    "rootline": "Owner approval plus a separate physical-control safety gate is required before any irrigation/control action.",
    "herdmaster": "Owner approval plus a record-write gate is required before pig, litter, weight, pen, or medical changes.",
    "butcher": "Owner approval plus sales/slaughter workflow gates are required before bookings, reservations, or customer output.",
    "beacon": "Owner approval plus public/customer-output gates are required before any published draft.",
    "quartermaster": "Owner approval plus a task/purchase/write gate is required before any operational mutation.",
    "gatekeeper": "Owner approval, append-only audit, browser-behavior proof, and Claude/Codex review are required before live authority.",
}

_AUTHORITY_AREAS = (
    {
        "authority": "live_specialist_dispatch",
        "label": "Live specialist dispatch",
        "blocked_capability": "live specialist dispatch",
        "enabled": False,
        "current_state": "locked",
        "risk_level": 3,
        "why_locked": "No dispatch runtime exists and no specialist may run from a chat request.",
        "required_gates": (
            "owner approves a dispatch design",
            "append-only dispatch audit rail exists",
            "browser behavior suite proves no hidden dispatch",
            "Claude/Codex review passes",
        ),
    },
    {
        "authority": "specialist_llm_loop",
        "label": "Specialist LLM loop",
        "blocked_capability": "specialist LLM loops",
        "enabled": False,
        "current_state": "locked",
        "risk_level": 3,
        "why_locked": "Specialists are contracts/dry-run records only; no specialist-specific LLM loop is allowed.",
        "required_gates": (
            "prompt-injection review",
            "tool allowlist enforcement",
            "cost/privacy policy display",
            "owner-approved bounded dry run",
        ),
    },
    {
        "authority": "specialist_tool_execution",
        "label": "Specialist tool execution",
        "blocked_capability": "specialist tool execution",
        "enabled": False,
        "current_state": "locked",
        "risk_level": 3,
        "why_locked": "Oom Sakkie may call existing read-only tools directly; specialists do not execute tools.",
        "required_gates": (
            "per-agent tool allowlist",
            "read-only registry enforcement",
            "trace-level tool audit",
            "owner approval before widening",
        ),
    },
    {
        "authority": "farm_data_writes",
        "label": "Farm data writes",
        "blocked_capability": "farm data writes",
        "enabled": False,
        "current_state": "locked",
        "risk_level": 4,
        "why_locked": "Pig, litter, weight, sales, task, and operating records must not be mutated by agents.",
        "required_gates": (
            "idempotency keys",
            "exact confirmation payload",
            "append-only write decision rail",
            "rollback and live verification plan",
        ),
    },
    {
        "authority": "customer_or_public_output",
        "label": "Customer/public output",
        "blocked_capability": "customer/public output",
        "enabled": False,
        "current_state": "locked",
        "risk_level": 4,
        "why_locked": "No agent may message customers, speak as Sam, post publicly, or publish marketing.",
        "required_gates": (
            "draft-only phase",
            "human copy approval",
            "channel-specific ACL",
            "brand/customer safety review",
        ),
    },
    {
        "authority": "builder_or_patch_execution",
        "label": "Builder/patch execution",
        "blocked_capability": "Builder/Forge execution from kiosk",
        "enabled": False,
        "current_state": "locked",
        "risk_level": 4,
        "why_locked": "The kiosk can prepare handoff packets and record patch proposals, but cannot edit files or apply patches.",
        "required_gates": (
            "separate builder tool review",
            "owner patch approval",
            "manual patch application",
            "test evidence recorded",
        ),
    },
    {
        "authority": "deploy_execution",
        "label": "Deploy execution",
        "blocked_capability": "deploy execution",
        "enabled": False,
        "current_state": "locked",
        "risk_level": 5,
        "why_locked": "Deploy decisions are recorded only; deployment remains manual outside the kiosk.",
        "required_gates": (
            "approved patch proposal",
            "manual deploy approval",
            "operator deploy outside kiosk",
            "post-deploy smoke result",
        ),
    },
    {
        "authority": "telegram_cutover",
        "label": "Telegram cutover",
        "blocked_capability": "Telegram cutover",
        "enabled": False,
        "current_state": "locked",
        "risk_level": 4,
        "why_locked": "n8n Telegram routing remains untouched until the kiosk brain has a separate parallel-run plan.",
        "required_gates": (
            "feature flag",
            "one-user parallel run",
            "answer-diff review",
            "30-day archive plan for old workflows",
        ),
    },
    {
        "authority": "physical_controls",
        "label": "Physical controls",
        "blocked_capability": "physical controls",
        "enabled": False,
        "current_state": "locked",
        "risk_level": 5,
        "why_locked": "Irrigation, pumps, valves, power controls, and any physical action remain read-only/status-only.",
        "required_gates": (
            "separate hardware safety design",
            "exact payload confirmation",
            "idempotency and lockouts",
            "manual emergency stop procedure",
        ),
    },
)


_JARVIS_PROGRESS_AREAS = (
    {
        "area": "foundation_safety_rails",
        "label": "Foundation / safety rails",
        "percent": 90,
        "status": "strong",
        "evidence": "Tool registry, access guards, trace store, audit rails, CI, browser smoke, and review handoff exist.",
        "next_step": "Confirm CI stays green and keep all authority flags false.",
    },
    {
        "area": "local_kiosk_voice",
        "label": "Local kiosk + voice basics",
        "percent": 70,
        "status": "usable",
        "evidence": "Browser speech, voice loop cap, top controls, presence strip, and no-hidden-POST smoke exist.",
        "next_step": "Improve command-center clarity and real-browser checks as the UI grows.",
    },
    {
        "area": "read_only_farm_intelligence",
        "label": "Read-only farm intelligence",
        "percent": 65,
        "status": "useful_but_growing",
        "evidence": "Operating brief, power, weather, irrigation, dashboard, meat, sales, and business brief tools are read-only.",
        "next_step": "Make briefings more multi-signal and decision-oriented without writing data.",
    },
    {
        "area": "agent_roster_contracts",
        "label": "Agent roster + contracts",
        "percent": 80,
        "status": "well_defined",
        "evidence": "Specialist manifests, contracts, authority matrix, activation plan, and dry-run cohort are documented.",
        "next_step": "Keep Beacon, Forge, and Gatekeeper locked out of dry-run request records.",
    },
    {
        "area": "agent_dry_run_learning",
        "label": "Agent dry-run / learning rails",
        "percent": 70,
        "status": "ready_for_evidence",
        "evidence": "Append-only dry-run requests/results, review packets, accepted learning, and ledger summaries exist.",
        "next_step": "Collect reviewed specialist dry-run evidence before live execution design.",
    },
    {
        "area": "builder_patch_deploy_gates",
        "label": "Builder / patch / deploy gates",
        "percent": 70,
        "status": "gated_manual",
        "evidence": "Build request, Forge handoff, patch proposal, and deploy decision rails are append-only and manual.",
        "next_step": "Use the gates on small real changes; do not let the kiosk apply patches or deploy.",
    },
    {
        "area": "live_specialist_execution",
        "label": "Live specialist execution",
        "percent": 20,
        "status": "locked",
        "evidence": "Dispatch rail is append-only/no-execution and observable, but no decision consumer exists.",
        "next_step": "Owner and Claude must review the dispatch runtime packet before any execution design.",
    },
    {
        "area": "business_advisor_automation",
        "label": "Business advisor automation",
        "percent": 40,
        "status": "seeded",
        "evidence": "Ledger-style business brief and internal offer outline are read-only and approval-safe.",
        "next_step": "Expand daily business briefing with demand/order context before customer-facing drafts.",
    },
    {
        "area": "customer_public_selling",
        "label": "Customer/public selling tools",
        "percent": 10,
        "status": "hard_locked",
        "evidence": "Public/customer output remains blocked by the authority matrix and no customer sender exists in Oom Sakkie.",
        "next_step": "Do not build until drafts, approval payloads, and public/customer-output gates are designed.",
    },
    {
        "area": "alive_jarvis_interface",
        "label": "True alive Jarvis UI/feel",
        "percent": 30,
        "status": "early",
        "evidence": "Presence orb, agent activity lane, and command-center concepts exist, but the UI is not yet a live workspace.",
        "next_step": "Build clearer agent workspace panels and visual stage transitions after runtime review.",
    },
)


def _authority_area_rows():
    rows = []
    for item in _AUTHORITY_AREAS:
        rows.append({
            "authority": item["authority"],
            "label": item["label"],
            "blocked_capability": item["blocked_capability"],
            "enabled": False,
            "current_state": item["current_state"],
            "risk_level": item["risk_level"],
            "why_locked": item["why_locked"],
            "required_gates": list(item["required_gates"]),
        })
    return rows


def _progress_bar(percent, width=10):
    clamped = max(0, min(100, int(percent or 0)))
    filled = round((clamped / 100) * width)
    return "{}{}".format("█" * filled, "░" * (width - filled))


def get_jarvis_product_progress():
    areas = []
    total = 0
    for item in _JARVIS_PROGRESS_AREAS:
        percent = max(0, min(100, int(item["percent"])))
        total += percent
        areas.append({
            "area": item["area"],
            "label": item["label"],
            "percent": percent,
            "bar": _progress_bar(percent),
            "status": item["status"],
            "evidence": item["evidence"],
            "next_step": item["next_step"],
        })
    overall = round(total / len(areas)) if areas else 0
    return {
        "success": True,
        "mode": "jarvis_product_progress_only",
        "summary_status": "foundation_strong_live_authority_locked",
        "overall_percent": overall,
        "overall_bar": _progress_bar(overall),
        "runtime_enabled": False,
        "dispatch_enabled": False,
        "autonomous_loops_enabled": False,
        "writes_enabled": False,
        "specialist_llm_enabled": False,
        "specialist_tools_enabled": False,
        "public_output_enabled": False,
        "physical_controls_enabled": False,
        "areas": areas,
        "next_milestone": {
            "name": "Read-only Agent Command Center",
            "goal": "Make Oom Sakkie show who is working, what they inspected, what needs approval, and what remains locked.",
            "authority": "read_only_visibility_only",
        },
        "blocked_until": [
            "owner and Claude review the dispatch runtime review packet",
            "a dedicated gate is designed before any code consumes dispatch decisions",
            "runtime flags remain false",
        ],
        "next_gate": "owner_and_claude_review_before_any_live_runtime_authority",
    }


_COMMAND_CENTER_LANES = (
    {
        "lane": "control_tower",
        "specialist_slug": "gatekeeper",
        "label": "Oom Sakkie Control Tower",
        "would_show": "Current phase, next gate, locked authority, and owner approvals.",
        "current_state": "watching_read_only",
        "color": "white",
    },
    {
        "lane": "safety_review",
        "specialist_slug": "sentinel",
        "label": "Sentinel Safety Desk",
        "would_show": "Guardrails, no-go rules, runtime flags, and dry-run safety evidence.",
        "current_state": "dry_run_evidence_only",
        "color": "red",
    },
    {
        "lane": "business_growth",
        "specialist_slug": "ledger",
        "label": "Ledger Business Desk",
        "would_show": "Read-only sales, meat pipeline, stock, and growth brief context.",
        "current_state": "read_only_briefing",
        "color": "green",
    },
    {
        "lane": "farm_operations",
        "specialist_slug": "rootline",
        "label": "Rootline Farm Desk",
        "would_show": "Read-only weather, irrigation, power, and farm-attention context.",
        "current_state": "read_only_monitoring",
        "color": "teal",
    },
    {
        "lane": "interface",
        "specialist_slug": "prism",
        "label": "Prism Interface Desk",
        "would_show": "Kiosk clarity, agent stage display, and Jarvis-style workspace polish.",
        "current_state": "design_review_only",
        "color": "violet",
    },
    {
        "lane": "builder_gates",
        "specialist_slug": "forge",
        "label": "Forge Build Desk",
        "would_show": "Build requests, Forge handoff packets, patch proposals, and deploy decisions.",
        "current_state": "manual_gate_only",
        "color": "blue",
    },
)


def get_agent_command_center():
    progress = get_jarvis_product_progress()
    activation_plan = get_agent_activation_plan()
    preflight = get_agent_activation_preflight()
    matrix = get_agent_authority_matrix()
    lanes = []
    for item in _COMMAND_CENTER_LANES:
        lanes.append({
            "lane": item["lane"],
            "specialist_slug": item["specialist_slug"],
            "label": item["label"],
            "would_show": item["would_show"],
            "current_state": item["current_state"],
            "color": item["color"],
            "runs_agent": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        })
    return {
        "success": True,
        "mode": "agent_command_center_only",
        "summary_status": "read_only_command_center_live_authority_locked",
        "runtime_enabled": False,
        "dispatch_enabled": False,
        "autonomous_loops_enabled": False,
        "writes_enabled": False,
        "specialist_llm_enabled": False,
        "specialist_tools_enabled": False,
        "public_output_enabled": False,
        "physical_controls_enabled": False,
        "overall_percent": progress.get("overall_percent", 0),
        "overall_bar": progress.get("overall_bar", ""),
        "lanes": lanes,
        "panels": [
            {
                "panel": "progress",
                "label": "Jarvis progress",
                "source": "jarvis_product_progress",
                "authority": "read_only_visibility_only",
            },
            {
                "panel": "approvals",
                "label": "Owner approval queue",
                "source": "system_work_status",
                "authority": "read_only_status_only",
            },
            {
                "panel": "agent_learning",
                "label": "Accepted dry-run learning",
                "source": "agent_learning_evidence",
                "authority": "read_only_evidence_only",
            },
            {
                "panel": "dispatch_review",
                "label": "Dispatch design review",
                "source": "dispatch_runtime_review_packet",
                "authority": "review_packet_only",
            },
            {
                "panel": "authority_locks",
                "label": "Locked authority matrix",
                "source": "agent_authority_matrix",
                "authority": "inspection_only",
            },
        ],
        "queue_sources": [
            "system_work_status",
            "agent_dry_run_status",
            "dispatch_decision_status",
        ],
        "blocked_authority_count": matrix.get("locked_count", 0),
        "dry_run_candidate_count": len(activation_plan.get("first_candidates", [])),
        "manual_check_count": len(preflight.get("manual_checks", [])),
        "locked_check_count": len(preflight.get("locked_checks", [])),
        "not_done": [
            "No specialist runtime is enabled.",
            "No specialist LLM loop is enabled.",
            "No specialist tool execution is enabled.",
            "No dispatch decision is consumed to change behavior.",
            "No farm-data write, public/customer output, patch, deploy, Telegram cutover, or physical control is enabled.",
        ],
        "next_action": "Use this as a read-only control-tower view; owner and Claude review remain required before any live authority.",
        "next_gate": "owner_and_claude_review_before_any_live_runtime_authority",
    }


def _blocked_capabilities_from_authorities():
    return [item["blocked_capability"] for item in _AUTHORITY_AREAS]


def _locked_checks_from_authorities():
    return [
        {
            "check": item["authority"],
            "status": "locked",
            "detail": item["why_locked"],
            "risk_level": item["risk_level"],
            "required_gates": list(item["required_gates"]),
        }
        for item in _AUTHORITY_AREAS
    ]

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
        "blocked_capabilities": _blocked_capabilities_from_authorities(),
        "next_gate": "owner_approval_before_read_only_specialist_dry_run",
    }


def get_agent_runtime_readiness():
    plan = get_agent_activation_plan()
    status = get_agent_runtime_status()
    dry_run_candidates = [
        item["slug"]
        for item in plan.get("first_candidates", [])
        if item.get("dry_run_request_allowed")
    ]
    checklist = [
        {
            "gate": "foundation_visible",
            "status": "ready",
            "meaning": "The planned crew, visual workspace, handoff lane, dry-run request rail, result review rail, learning ledger, and roadmap are visible.",
        },
        {
            "gate": "read_only_dry_run_records",
            "status": "ready",
            "meaning": "Approved specialists can have append-only dry-run request and result records, but the specialists do not run.",
        },
        {
            "gate": "audit_rail_ci",
            "status": "ready",
            "meaning": "The audit rail has a disposable-Postgres CI workflow scoped to Oom Sakkie append-only/no-execution tests.",
        },
        {
            "gate": "browser_behavior_pass",
            "status": "manual_check_required",
            "meaning": "The owner should run the browser behavior checklist before any wider runtime work.",
        },
        {
            "gate": "live_specialist_dispatch",
            "status": "locked",
            "meaning": "No live specialist dispatch path exists and no runtime flag enables it.",
        },
        {
            "gate": "specialist_llm_or_tools",
            "status": "locked",
            "meaning": "No specialist LLM loop or specialist tool execution is enabled.",
        },
        {
            "gate": "writes_public_output_and_controls",
            "status": "locked",
            "meaning": "Farm writes, customer/public output, patch application, deploy, Telegram cutover, and physical controls remain outside this runtime.",
        },
    ]
    return {
        "success": True,
        "mode": "runtime_readiness_checklist_only",
        "runtime_enabled": False,
        "dispatch_enabled": False,
        "autonomous_loops_enabled": False,
        "writes_enabled": False,
        "specialist_llm_enabled": False,
        "specialist_tools_enabled": False,
        "public_output_enabled": False,
        "physical_controls_enabled": False,
        "dry_run_candidates": dry_run_candidates,
        "ready_gates": [item for item in checklist if item["status"] == "ready"],
        "manual_gates": [item for item in checklist if item["status"] == "manual_check_required"],
        "locked_gates": [item for item in checklist if item["status"] == "locked"],
        "checklist": checklist,
        "blocked_capabilities": plan.get("blocked_capabilities", []),
        "next_safe_action": "Run the browser behavior checklist and keep collecting accepted read-only dry-run evidence.",
        "next_gate": "owner_review_before_any_live_specialist_dispatch",
        "agent_count": status.get("agent_count", 0),
    }


def get_agent_operating_contracts():
    agents = list_agent_runtime_manifests()
    dry_run_allowed = allowed_agent_dry_run_slugs()
    contracts = []
    for agent in agents:
        slug = agent["slug"]
        contracts.append({
            "slug": slug,
            "name": agent["name"],
            "personality": agent["personality"],
            "role": agent["role"],
            "status": agent["status"],
            "dry_run_request_allowed": slug in dry_run_allowed,
            "runtime_enabled": False,
            "dispatch_enabled": False,
            "autonomous_loops_enabled": False,
            "writes_enabled": False,
            "specialist_llm_enabled": False,
            "specialist_tools_enabled": False,
            "public_output_enabled": False,
            "physical_controls_enabled": False,
            "focus": _AGENT_CONTRACT_FOCUS.get(slug, agent["role"]),
            "allowed_read_only_tools": list(agent["allowed_tools"]),
            "memory_sources": list(agent["memory_sources"]),
            "output_contract": list(agent["output_contract"]),
            "must_not_do": list(_AGENT_CONTRACT_MUST_NOT.get(slug, ())),
            "owner_gate": _AGENT_CONTRACT_OWNER_GATES.get(slug, "Owner approval required before any live authority."),
        })
    return {
        "success": True,
        "mode": "agent_operating_contracts_only",
        "runtime_enabled": False,
        "dispatch_enabled": False,
        "autonomous_loops_enabled": False,
        "writes_enabled": False,
        "specialist_llm_enabled": False,
        "specialist_tools_enabled": False,
        "public_output_enabled": False,
        "physical_controls_enabled": False,
        "contract_count": len(contracts),
        "dry_run_allowed": sorted(dry_run_allowed),
        "locked_out_of_dry_run": [
            item["slug"]
            for item in contracts
            if not item["dry_run_request_allowed"]
        ],
        "contracts": contracts,
        "next_gate": "owner_review_before_any_contract_becomes_runtime_authority",
    }


def get_agent_activation_preflight():
    readiness = get_agent_runtime_readiness()
    contracts = get_agent_operating_contracts()
    plan = get_agent_activation_plan()
    locked_out = set(contracts.get("locked_out_of_dry_run") or [])
    dry_run_allowed = set(contracts.get("dry_run_allowed") or [])
    expected_locked = {"beacon", "forge", "gatekeeper"}
    ready_checks = [
        {
            "check": "runtime_flags_locked",
            "status": "pass",
            "detail": "Runtime, dispatch, autonomous loops, specialist LLM/tools, writes, public output, and physical controls are all false.",
        },
        {
            "check": "dry_run_cohort_bounded",
            "status": "pass" if expected_locked.issubset(locked_out) else "needs_review",
            "detail": "Beacon, Forge, and Gatekeeper must stay out of dry-run requests until separate authority gates exist.",
        },
        {
            "check": "approved_dry_run_candidates_present",
            "status": "pass" if {"sentinel", "prism"}.issubset(dry_run_allowed) else "needs_review",
            "detail": "Sentinel and Prism are the smallest safe dry-run candidates; wider cohort remains no-execution.",
        },
        {
            "check": "audit_rail_ci",
            "status": "configured",
            "detail": "Disposable-Postgres audit rail CI gate is configured for append-only/no-execution checks; GitHub green status remains a manual check.",
        },
        {
            "check": "browser_behavior_smoke",
            "status": "configured",
            "detail": "Node smoke gate is configured to execute the real kiosk JS and check no hidden startup POSTs or interval polling.",
        },
    ]
    manual_checks = [
        {
            "check": "github_actions_green",
            "status": "manual_check_required",
            "detail": "Confirm the GitHub Actions audit-rail workflow has a green run on the published branch.",
        },
        {
            "check": "owner_browser_pass",
            "status": "manual_check_required",
            "detail": "Run the browser behavior checklist before any live-authority phase.",
        },
        {
            "check": "claude_review",
            "status": "manual_check_required",
            "detail": "Batch a Claude review before any phase that flips runtime or dispatch authority.",
        },
    ]
    blocked_checks = _locked_checks_from_authorities()
    checks = ready_checks + manual_checks + blocked_checks
    return {
        "success": True,
        "mode": "agent_activation_preflight_only",
        "runtime_enabled": False,
        "dispatch_enabled": False,
        "autonomous_loops_enabled": False,
        "writes_enabled": False,
        "specialist_llm_enabled": False,
        "specialist_tools_enabled": False,
        "public_output_enabled": False,
        "physical_controls_enabled": False,
        "summary_status": "not_ready_for_live_dispatch",
        "ready_count": len(ready_checks),
        "manual_check_count": len(manual_checks),
        "locked_count": len(blocked_checks),
        "checks": checks,
        "ready_checks": ready_checks,
        "manual_checks": manual_checks,
        "locked_checks": blocked_checks,
        "dry_run_allowed": sorted(dry_run_allowed),
        "locked_out_of_dry_run": sorted(locked_out),
        "recommended_next_safe_action": "Confirm GitHub Actions is green, run the owner browser pass, and continue no-execution dry-run evidence.",
        "next_gate": "claude_and_owner_review_before_any_live_runtime_authority",
        "source_modes": {
            "readiness": readiness.get("mode"),
            "contracts": contracts.get("mode"),
            "activation_plan": plan.get("mode"),
        },
    }


def get_agent_authority_matrix():
    areas = _authority_area_rows()
    return {
        "success": True,
        "mode": "agent_authority_matrix_only",
        "runtime_enabled": False,
        "dispatch_enabled": False,
        "autonomous_loops_enabled": False,
        "writes_enabled": False,
        "specialist_llm_enabled": False,
        "specialist_tools_enabled": False,
        "public_output_enabled": False,
        "physical_controls_enabled": False,
        "authority_count": len(areas),
        "enabled_count": 0,
        "locked_count": len(areas),
        "max_locked_risk_level": max(item["risk_level"] for item in areas),
        "areas": areas,
        "next_gate": "owner_and_claude_review_before_any_authority_changes",
    }


def get_agent_authority_unlock_readiness():
    matrix = get_agent_authority_matrix()
    candidates = sorted(
        matrix["areas"],
        key=lambda item: (item["risk_level"], item["authority"]),
    )
    lowest_risk = candidates[0]["risk_level"] if candidates else 0
    lowest_risk_candidates = [
        {
            "authority": item["authority"],
            "label": item["label"],
            "risk_level": item["risk_level"],
            "current_state": item["current_state"],
            "enabled": False,
            "why_locked": item["why_locked"],
            "required_gates": item["required_gates"],
            "recommendation": "Do not unlock yet; use this only as planning input for a future owner/Claude-reviewed design.",
        }
        for item in candidates
        if item["risk_level"] == lowest_risk
    ]
    hard_no = [
        item
        for item in candidates
        if item["risk_level"] >= 4
    ]
    return {
        "success": True,
        "mode": "agent_authority_unlock_readiness_only",
        "runtime_enabled": False,
        "dispatch_enabled": False,
        "autonomous_loops_enabled": False,
        "writes_enabled": False,
        "specialist_llm_enabled": False,
        "specialist_tools_enabled": False,
        "public_output_enabled": False,
        "physical_controls_enabled": False,
        "summary_status": "planning_only_no_unlock_recommended",
        "enabled_count": 0,
        "candidate_count": len(lowest_risk_candidates),
        "lowest_risk_level": lowest_risk,
        "lowest_risk_candidates": lowest_risk_candidates,
        "hard_no_authorities": [
            {
                "authority": item["authority"],
                "label": item["label"],
                "risk_level": item["risk_level"],
                "why_locked": item["why_locked"],
            }
            for item in hard_no
        ],
        "required_before_any_unlock": [
            "owner names one authority area explicitly",
            "Claude/Codex reviews the design before code changes",
            "append-only decision rail exists for that authority",
            "browser behavior suite covers hidden action surfaces",
            "runtime flags remain false until the reviewed gate is built",
        ],
        "next_gate": "owner_named_authority_design_before_any_unlock_work",
        "source_mode": matrix.get("mode"),
    }


def get_agent_dispatch_decision_rail_blueprint():
    authority = next(
        item for item in _authority_area_rows()
        if item["authority"] == "live_specialist_dispatch"
    )
    tables = [
        {
            "name": "oom_sakkie_dispatch_requests",
            "purpose": "Append-only owner request to design or rehearse one live specialist dispatch boundary.",
            "must_force_false": [
                "dispatch_enabled",
                "runs_specialist_llm",
                "runs_specialist_tools",
                "writes",
                "applies_runtime_change",
            ],
        },
        {
            "name": "oom_sakkie_dispatch_decisions",
            "purpose": "Append-only owner decisions on whether a dispatch proposal may proceed to another review gate.",
            "allowed_events": [
                "approved_for_design_review",
                "rejected",
                "deferred",
                "review_note",
            ],
        },
    ]
    required_tests = [
        "DB CHECK constraints reject dispatch_enabled=true and applies_runtime_change=true.",
        "UPDATE/DELETE triggers reject mutation on both dispatch tables.",
        "Non-local requests to dispatch review endpoints return 403.",
        "Browser behavior smoke proves no dispatch POST happens on page load or timer.",
        "A rejected/deferred decision never changes runtime status.",
    ]
    return {
        "success": True,
        "mode": "dispatch_decision_rail_blueprint_only",
        "authority": authority,
        "runtime_enabled": False,
        "dispatch_enabled": False,
        "autonomous_loops_enabled": False,
        "writes_enabled": False,
        "specialist_llm_enabled": False,
        "specialist_tools_enabled": False,
        "public_output_enabled": False,
        "physical_controls_enabled": False,
        "summary_status": "blueprint_only_no_dispatch",
        "proposed_tables": tables,
        "required_endpoints": [
            "GET /api/oom-sakkie/dispatch-requests",
            "POST /api/oom-sakkie/dispatch-requests",
            "POST /api/oom-sakkie/dispatch-requests/<id>/decisions",
        ],
        "required_tests": required_tests,
        "non_goals": [
            "do not run a specialist",
            "do not call a specialist LLM",
            "do not execute specialist tools",
            "do not write farm data",
            "do not enable runtime flags",
            "do not expose customer/public output",
        ],
        "owner_gate": "owner_and_claude_must_approve_before_any_dispatch_rail_code",
        "next_gate": "claude_review_before_dispatch_decision_rail_implementation",
    }


def get_agent_runtime_review_packet():
    status = get_agent_runtime_status()
    readiness = get_agent_runtime_readiness()
    contracts = get_agent_operating_contracts()
    preflight = get_agent_activation_preflight()
    matrix = get_agent_authority_matrix()
    unlock = get_agent_authority_unlock_readiness()
    dispatch_blueprint = get_agent_dispatch_decision_rail_blueprint()
    source_modes = {
        "runtime_status": status.get("mode"),
        "runtime_readiness": readiness.get("mode"),
        "operating_contracts": contracts.get("mode"),
        "activation_preflight": preflight.get("mode"),
        "authority_matrix": matrix.get("mode"),
        "unlock_readiness": unlock.get("mode"),
        "dispatch_blueprint": dispatch_blueprint.get("mode"),
    }
    return {
        "success": True,
        "mode": "agent_runtime_review_packet_only",
        "summary_status": "ready_for_bulk_claude_review_not_live_dispatch",
        "runtime_enabled": False,
        "dispatch_enabled": False,
        "autonomous_loops_enabled": False,
        "writes_enabled": False,
        "specialist_llm_enabled": False,
        "specialist_tools_enabled": False,
        "public_output_enabled": False,
        "physical_controls_enabled": False,
        "source_modes": source_modes,
        "review_focus": [
            "agent inspection surfaces keep all authority flags false",
            "dry-run cohort remains bounded and no-execution",
            "authority matrix remains the source of locked capability truth",
            "dispatch decision rail blueprint remains blueprint-only",
            "browser smoke and audit rail CI remain configured",
        ],
        "payloads": {
            "runtime_status": status,
            "runtime_readiness": readiness,
            "operating_contracts": contracts,
            "activation_preflight": preflight,
            "authority_matrix": matrix,
            "unlock_readiness": unlock,
            "dispatch_blueprint": dispatch_blueprint,
        },
        "claude_prompt": "Read docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md and run the current review.",
        "next_gate": "bulk_claude_review_before_dispatch_decision_rail_implementation",
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
