from modules.oom_sakkie.agent_runtime import recommend_agent_for_text
from modules.oom_sakkie.agent_dry_run_store import allowed_agent_dry_run_slugs


NO_GO_RULES = (
    "Do not dispatch or simulate a live specialist runtime.",
    "Do not call a specialist LLM from this codebase.",
    "Do not execute specialist tools from this packet.",
    "Do not write farm data, send messages, post publicly, sell, reserve stock, control hardware, edit code, apply patches, or deploy.",
    "Return a short dry-run plan and wait for owner approval before any separate execution step.",
)

_SPECIALIST_NAMES = {
    "atlas": "Atlas",
    "butcher": "Butcher",
    "herdmaster": "Herdmaster",
    "ledger": "Ledger",
    "quartermaster": "Quartermaster",
    "rootline": "Rootline",
    "sentinel": "Sentinel",
    "prism": "Prism",
}

_SPECIALIST_ROLES = {
    "atlas": "the farm data and anomaly reviewer",
    "butcher": "the pork pipeline and slaughter-readiness reviewer",
    "herdmaster": "the pig lifecycle and herd-attention reviewer",
    "ledger": "the business and profit reviewer",
    "quartermaster": "the operations, supplies, and task reviewer",
    "rootline": "the weather, crop, and irrigation reviewer",
    "sentinel": "the safety and readiness reviewer",
    "prism": "the kiosk and interface design reviewer",
}

_SPECIALIST_REVIEW_GUIDES = {
    "sentinel": {
        "focus": (
            "Check whether the requested slice stays inside read-only/local-only scope.",
            "Identify any no-go rule, secret, write, dispatch, public-output, or deployment risk.",
            "Name the exact owner gate required before any next action.",
        ),
        "context": ("runtime policy", "tool registry", "review packet", "route/test results"),
        "risks": ("hidden write path", "secret exposure", "LLM egress", "unsafe approval shortcut"),
        "approval_question": "Do you want Sentinel to perform a separate read-only review of this exact slice?",
    },
    "prism": {
        "focus": (
            "Review whether the kiosk screen is easy to scan from normal room distance.",
            "Identify clutter, unclear grouping, and confusing agent/workbench states.",
            "Recommend one small visual improvement that does not add new behavior.",
        ),
        "context": ("kiosk template", "kiosk CSS", "owner screenshots/video notes", "frontend contract tests"),
        "risks": ("misleading automation", "hidden action buttons", "over-busy layout", "text overflow"),
        "approval_question": "Do you want Prism to review one visible UI panel and return design findings only?",
    },
    "ledger": {
        "focus": (
            "Inspect the sales and pork pipeline context for the next sensible business question.",
            "Separate real stock/opportunity evidence from guesses or missing margin data.",
            "Recommend what the owner should decide next, without drafting customer messages.",
        ),
        "context": ("business growth brief", "sales dashboard", "meat planning", "accepted owner rules"),
        "risks": ("fake revenue claim", "unapproved price change", "customer-facing wording", "missing cost data"),
        "approval_question": "Do you want Ledger to perform a read-only business review and return owner questions only?",
    },
    "atlas": {
        "focus": (
            "Look for patterns, stale data, anomalies, or conflicting farm signals.",
            "Explain what data is trustworthy and what needs owner confirmation.",
            "Recommend the next read-only metric or trace to inspect.",
        ),
        "context": ("farm operating brief", "dashboard summary", "power recent", "pig allocation readiness"),
        "risks": ("stale telemetry", "false trend", "missing sample window", "overstated certainty"),
        "approval_question": "Do you want Atlas to perform a read-only anomaly/pattern review of this context?",
    },
    "rootline": {
        "focus": (
            "Inspect weather, irrigation, and water-risk context for practical farm impact.",
            "Separate read-only observation from any physical control or schedule change.",
            "Return inspection questions the owner can answer before any action is considered.",
        ),
        "context": ("weather now", "weather today", "weather forecast", "irrigation status"),
        "risks": ("pump/control command", "stale weather", "unsafe irrigation advice", "hardware assumption"),
        "approval_question": "Do you want Rootline to perform a read-only weather/irrigation review only?",
    },
    "herdmaster": {
        "focus": (
            "Inspect pig, litter, pen, and weight context for herd-attention priorities.",
            "Keep every recommendation read-only unless a later owner-approved form exists.",
            "Name missing records or owner checks before any pig/litter action.",
        ),
        "context": ("dashboard summary", "farm attention summary", "pig allocation readiness", "meat planning"),
        "risks": ("pig record write", "medical write", "pen move", "unsupported welfare conclusion"),
        "approval_question": "Do you want Herdmaster to perform a read-only herd-attention review only?",
    },
    "butcher": {
        "focus": (
            "Inspect pork, slaughter, and livestock-readiness context for pipeline opportunities.",
            "Separate ready-now animals from future candidates and unknown constraints.",
            "Return internal planning notes only, not sales commitments or bookings.",
        ),
        "context": ("meat planning", "sales dashboard", "pig allocation readiness", "business growth brief"),
        "risks": ("unapproved sale", "slaughter booking", "customer promise", "stock reservation"),
        "approval_question": "Do you want Butcher to perform a read-only pork-pipeline review only?",
    },
    "quartermaster": {
        "focus": (
            "Inspect farm-attention and operational context for practical work sequencing.",
            "Identify supplies/tasks that need owner confirmation before any record or purchase path.",
            "Return a short owner checklist only.",
        ),
        "context": ("farm attention summary", "dashboard summary", "system work status", "future inventory tables"),
        "risks": ("purchase action", "supplier message", "stock write", "task write"),
        "approval_question": "Do you want Quartermaster to perform a read-only operations checklist review only?",
    },
}


def build_agent_dry_run_handoff(dry_run_request):
    dry_run_request = dry_run_request if isinstance(dry_run_request, dict) else {}
    if dry_run_request.get("mode") != "read_only_dry_run_request_only":
        return {
            "success": False,
            "status": "invalid_dry_run_request_mode",
        }, 400
    unsafe_flags = [
        "dry_run_enabled",
        "dispatch_enabled",
        "runs_specialist_llm",
        "runs_specialist_tools",
        "writes",
    ]
    if any(bool(dry_run_request.get(name)) for name in unsafe_flags):
        return {
            "success": False,
            "status": "unsafe_dry_run_request_flags",
            "unsafe_flags": [name for name in unsafe_flags if bool(dry_run_request.get(name))],
        }, 400

    specialist_slug = str(dry_run_request.get("specialist_slug") or "").strip().lower()
    allowed = allowed_agent_dry_run_slugs()
    if specialist_slug not in allowed:
        return {
            "success": False,
            "status": "dry_run_handoff_not_approved_for_specialist",
            "approved_specialists": sorted(allowed),
        }, 400

    owner_text = _clean_text(dry_run_request.get("owner_text") or "", 1200)
    specialist_name = _SPECIALIST_NAMES.get(specialist_slug, specialist_slug.title())
    review_guide = _review_guide_for(specialist_slug)
    recommendation = recommend_agent_for_text(owner_text or f"{specialist_slug} dry-run review")
    packet = {
        "success": True,
        "mode": "agent_dry_run_handoff_only",
        "dry_run_request_id": dry_run_request.get("dry_run_request_id", ""),
        "specialist_slug": specialist_slug,
        "specialist_name": specialist_name,
        "owner_text": owner_text,
        "purpose": _clean_text(dry_run_request.get("purpose") or "", 1200),
        "source_trace_id": _clean_text(dry_run_request.get("source_trace_id") or "", 80),
        "allowed_tools": list(dry_run_request.get("allowed_tools") or [])[:12],
        "guardrails": list(dry_run_request.get("guardrails") or [])[:12],
        "focus_questions": list(review_guide["focus"]),
        "required_context": list(review_guide["context"]),
        "risk_checks": list(review_guide["risks"]),
        "owner_approval_question": review_guide["approval_question"],
        "no_go_rules": list(NO_GO_RULES),
        "runs_specialist": False,
        "runs_specialist_llm": False,
        "runs_specialist_tools": False,
        "writes": False,
        "dispatch_enabled": False,
        "requires_owner_execution_approval": True,
        "requires_output_review": True,
        "next_gate": f"owner_approval_before_any_separate_{specialist_slug}_dry_run_execution",
        "agent_recommendation": recommendation,
    }
    packet["prompt"] = _handoff_prompt(packet)
    return packet, 200


def _handoff_prompt(packet):
    tools = ", ".join(packet["allowed_tools"]) or "none"
    guardrails = "\n".join(f"- {item}" for item in packet["guardrails"]) or "- No extra guardrails supplied."
    focus = "\n".join(f"- {item}" for item in packet["focus_questions"]) or "- Review the request safely."
    context = "\n".join(f"- {item}" for item in packet["required_context"]) or "- Existing read-only context only."
    risks = "\n".join(f"- {item}" for item in packet["risk_checks"]) or "- Any widened authority."
    no_go = "\n".join(f"- {item}" for item in packet["no_go_rules"])
    specialist_role = _SPECIALIST_ROLES.get(packet["specialist_slug"], "a planned Oom Sakkie specialist")
    return (
        f"You are {packet['specialist_name']}, {specialist_role} for Oom Sakkie.\n\n"
        "This is a DRY-RUN HANDOFF ONLY. You are not being executed by the kiosk runtime.\n"
        "Your job is to propose how you would review this request safely, then stop.\n\n"
        f"Dry-run request ID: {packet['dry_run_request_id']}\n"
        f"Owner request: {packet['owner_text'] or '(none supplied)'}\n"
        f"Purpose: {packet['purpose'] or '(none supplied)'}\n"
        f"Source trace ID: {packet['source_trace_id'] or '(none)'}\n"
        f"Allowed read-only context/tools for a future reviewed dry-run: {tools}\n\n"
        "Guardrails from the stored request:\n"
        f"{guardrails}\n\n"
        "Specialist focus for this dry-run:\n"
        f"{focus}\n\n"
        "Read-only context you may ask the owner to provide later:\n"
        f"{context}\n\n"
        "Risks you must explicitly check:\n"
        f"{risks}\n\n"
        "Hard no-go rules:\n"
        f"{no_go}\n\n"
        "Return:\n"
        "1. What you would inspect.\n"
        "2. Which read-only context you would need.\n"
        "3. The exact risks you would check.\n"
        f"4. This owner approval question, adjusted only for grammar: {packet['owner_approval_question']}\n\n"
        "Do not claim you inspected anything yet. Do not call tools. Do not produce code. Do not approve yourself."
    )


def _review_guide_for(specialist_slug):
    return _SPECIALIST_REVIEW_GUIDES.get(specialist_slug, {
        "focus": ("Review the request safely inside read-only scope.",),
        "context": ("existing read-only context",),
        "risks": ("any widened authority",),
        "approval_question": "Do you want this planned specialist to perform a separate read-only review only?",
    })


def _clean_text(value, limit):
    return str(value or "").strip()[:limit]
