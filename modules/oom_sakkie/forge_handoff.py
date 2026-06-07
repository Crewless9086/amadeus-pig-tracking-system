FORGE_NO_GO_RULES = [
    "Do not edit files outside the approved recommended_files scope without asking the owner.",
    "Do not add write tools, physical controls, Telegram cutover, wake word, or always-on microphone behavior.",
    "Do not read or print secrets, .env values, API keys, SSH keys, or database credentials.",
    "Do not apply a patch unless the owner explicitly approves the Builder/Forge execution step.",
    "Do not deploy. Deployment requires a separate approval gate after patch review.",
]


def build_forge_handoff(build_request):
    build_request = build_request if isinstance(build_request, dict) else {}
    if build_request.get("mode") != "build_request_only":
        return {"success": False, "status": "invalid_build_request_mode"}, 400
    if build_request.get("builder_enabled") or build_request.get("writes_code_now") or build_request.get("applies_changes_now"):
        return {"success": False, "status": "unsafe_build_request_rejected"}, 400

    proposal = build_request.get("proposal") if isinstance(build_request.get("proposal"), dict) else {}
    packet = {
        "success": True,
        "status": "ok",
        "mode": "forge_handoff_only",
        "runs_builder": False,
        "writes_code": False,
        "applies_changes": False,
        "deploys": False,
        "requires_owner_to_run_builder": True,
        "requires_patch_review": True,
        "requires_deploy_approval": True,
        "build_request_id": _clean(build_request.get("build_request_id", ""), 80),
        "objective": _clean(proposal.get("title") or "Approved Oom Sakkie build request", 220),
        "evidence": _clean(proposal.get("evidence") or "", 1000),
        "recommended_action": _clean(proposal.get("recommended_action") or "", 1000),
        "approved_by": _clean(build_request.get("approved_by") or "owner", 80),
        "recommended_files": _clean_list(build_request.get("recommended_files"), 18, 240),
        "verification": _clean_list(build_request.get("verification"), 10, 300),
        "no_go_rules": FORGE_NO_GO_RULES,
    }
    packet["prompt"] = _forge_prompt(packet, build_request)
    return packet, 200


def _forge_prompt(packet, build_request):
    brief = _clean(build_request.get("brief", ""), 5000)
    lines = [
        "# Forge Handoff Packet",
        "",
        "You are preparing to work on an approved Oom Sakkie build request.",
        "Do not change code yet unless the owner explicitly tells you to run the Builder/Forge execution step.",
        "",
        "## Build Request",
        f"- ID: {packet['build_request_id'] or 'unknown'}",
        f"- Approved by: {packet['approved_by']}",
        f"- Objective: {packet['objective']}",
        "",
        "## Evidence",
        packet["evidence"] or "No evidence supplied.",
        "",
        "## Recommended Action",
        packet["recommended_action"] or "Inspect the brief and propose the smallest safe implementation.",
        "",
        "## Approved Scope",
    ]
    lines.extend(f"- {path}" for path in packet["recommended_files"])
    lines.extend(["", "## Required Verification"])
    lines.extend(f"- {item}" for item in packet["verification"])
    lines.extend(["", "## No-Go Rules"])
    lines.extend(f"- {item}" for item in packet["no_go_rules"])
    lines.extend([
        "",
        "## Original Build Brief",
        brief or "No build brief supplied.",
        "",
        "## Output Required Before Any Patch",
        "Return a short implementation plan, files you intend to touch, risks, and exact tests to run. Wait for owner approval before editing.",
    ])
    return "\n".join(lines)


def _clean(value, max_length):
    return str(value or "").strip()[:max_length]


def _clean_list(value, limit, item_length):
    if not isinstance(value, list):
        return []
    return [_clean(item, item_length) for item in value if str(item or "").strip()][:limit]
