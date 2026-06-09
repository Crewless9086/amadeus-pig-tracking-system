def build_agent_dry_run_result_review_packet(dry_run_result):
    dry_run_result = dry_run_result if isinstance(dry_run_result, dict) else {}
    if dry_run_result.get("mode") != "dry_run_result_review_only":
        return {
            "success": False,
            "status": "invalid_dry_run_result_mode",
            "message": "Only stored dry-run review results can become review packets.",
        }, 400

    unsafe_flags = [
        "runs_specialist",
        "dispatch_enabled",
        "runs_specialist_llm",
        "runs_specialist_tools",
        "writes",
        "applies_runtime_change",
    ]
    enabled = [flag for flag in unsafe_flags if dry_run_result.get(flag)]
    if enabled:
        return {
            "success": False,
            "status": "dry_run_result_has_execution_flags",
            "unsafe_flags": enabled,
        }, 400

    latest_event = dry_run_result.get("latest_event") or {}
    owner_options = [
        {
            "event_type": "accepted_for_learning",
            "label": "Accept For Learning",
            "meaning": "Record that this result is useful evidence for future planning.",
            "runs_specialist": False,
            "applies_runtime_change": False,
        },
        {
            "event_type": "rejected",
            "label": "Reject Result",
            "meaning": "Record that this result should not influence future planning.",
            "runs_specialist": False,
            "applies_runtime_change": False,
        },
        {
            "event_type": "review_note",
            "label": "Add Review Note",
            "meaning": "Add owner context without accepting or rejecting the result.",
            "runs_specialist": False,
            "applies_runtime_change": False,
        },
    ]

    return {
        "success": True,
        "status": "ok",
        "mode": "dry_run_result_review_packet",
        "dry_run_result_id": dry_run_result.get("dry_run_result_id", ""),
        "dry_run_request_id": dry_run_result.get("dry_run_request_id", ""),
        "specialist_slug": dry_run_result.get("specialist_slug", ""),
        "result_text": dry_run_result.get("result_text", ""),
        "findings": list(dry_run_result.get("findings") or [])[:20],
        "recommended_next_gate": dry_run_result.get("recommended_next_gate", ""),
        "latest_event": latest_event,
        "owner_options": owner_options,
        "review_guard": {
            "review_only": True,
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
            "builder_or_forge_runs": False,
            "patch_or_deploy_runs": False,
        },
        "next_action": _next_action(latest_event),
    }, 200


def _next_action(latest_event):
    event_type = latest_event.get("event_type") if isinstance(latest_event, dict) else ""
    if event_type == "accepted_for_learning":
        return "Already accepted for learning. Do not run or apply anything from this packet."
    if event_type == "rejected":
        return "Already rejected. Keep it as audit history only."
    return "Owner should accept, reject, or add a review note. No specialist or runtime action is performed."
