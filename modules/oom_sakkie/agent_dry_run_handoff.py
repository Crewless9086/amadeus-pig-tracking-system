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
        "Hard no-go rules:\n"
        f"{no_go}\n\n"
        "Return:\n"
        "1. What you would inspect.\n"
        "2. Which read-only context you would need.\n"
        "3. The exact risks you would check.\n"
        "4. A short owner approval question.\n\n"
        "Do not claim you inspected anything yet. Do not call tools. Do not produce code. Do not approve yourself."
    )


def _clean_text(value, limit):
    return str(value or "").strip()[:limit]
