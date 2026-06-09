_RESULT_REVIEW_PROFILES = {
    "sentinel": {
        "evidence_kind": "safety_guardrail_evidence",
        "may_influence": (
            "future safety checklist wording",
            "review questions before runtime or build gates",
            "no-go rule refinements",
        ),
        "must_not_influence": (
            "automatic approval",
            "runtime enablement",
            "secret access",
        ),
        "owner_question": "Should this safety evidence shape future planning notes only?",
    },
    "prism": {
        "evidence_kind": "interface_review_evidence",
        "may_influence": (
            "future kiosk layout priorities",
            "UI clarity tasks",
            "visual review questions",
        ),
        "must_not_influence": (
            "automatic UI changes",
            "generated asset creation",
            "patch application",
        ),
        "owner_question": "Should this UI evidence guide future design planning only?",
    },
    "ledger": {
        "evidence_kind": "business_review_evidence",
        "may_influence": (
            "future business brief questions",
            "internal offer planning",
            "margin-data gaps to investigate",
        ),
        "must_not_influence": (
            "customer messages",
            "price changes",
            "quotes or invoices",
        ),
        "owner_question": "Should this business evidence guide future internal planning only?",
    },
    "atlas": {
        "evidence_kind": "farm_analytics_evidence",
        "may_influence": (
            "future anomaly review questions",
            "dashboard investigation priorities",
            "data-quality follow-up notes",
        ),
        "must_not_influence": (
            "alert-rule changes",
            "data writes",
            "automated decisions",
        ),
        "owner_question": "Should this analytics evidence guide future read-only investigations only?",
    },
    "rootline": {
        "evidence_kind": "weather_irrigation_review_evidence",
        "may_influence": (
            "future weather/irrigation inspection questions",
            "stale-data warnings to watch",
            "read-only field-check priorities",
        ),
        "must_not_influence": (
            "pump or valve commands",
            "irrigation schedule changes",
            "physical controls",
        ),
        "owner_question": "Should this weather/irrigation evidence guide future read-only checks only?",
    },
    "herdmaster": {
        "evidence_kind": "herd_attention_evidence",
        "may_influence": (
            "future pig/litter review questions",
            "herd attention prioritization",
            "record-quality follow-up notes",
        ),
        "must_not_influence": (
            "pig record writes",
            "medical writes",
            "pen moves",
        ),
        "owner_question": "Should this herd evidence guide future read-only herd planning only?",
    },
    "butcher": {
        "evidence_kind": "pork_pipeline_evidence",
        "may_influence": (
            "future pork pipeline review questions",
            "internal slaughter-readiness planning",
            "preorder-gap notes",
        ),
        "must_not_influence": (
            "sales creation",
            "slaughter bookings",
            "stock reservations",
        ),
        "owner_question": "Should this pork-pipeline evidence guide future internal planning only?",
    },
    "quartermaster": {
        "evidence_kind": "operations_planning_evidence",
        "may_influence": (
            "future operations checklist questions",
            "supplies/task planning notes",
            "attention-queue review priorities",
        ),
        "must_not_influence": (
            "purchase orders",
            "supplier messages",
            "inventory or task writes",
        ),
        "owner_question": "Should this operations evidence guide future checklist planning only?",
    },
}


def build_agent_dry_run_result_review_packet(dry_run_result):
    dry_run_result = dry_run_result if isinstance(dry_run_result, dict) else {}
    if not _is_supported_result_mode(dry_run_result):
        return {
            "success": False,
            "status": "invalid_dry_run_result_mode",
            "message": "Only stored dry-run review results can become review packets.",
        }, 400

    enabled = _unsafe_result_flags(dry_run_result)
    if enabled:
        return {
            "success": False,
            "status": "dry_run_result_has_execution_flags",
            "unsafe_flags": enabled,
        }, 400

    latest_event = dry_run_result.get("latest_event") or {}
    specialist_slug = str(dry_run_result.get("specialist_slug") or "").strip().lower()
    review_profile = _review_profile_for(specialist_slug)
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
        "specialist_slug": specialist_slug,
        "result_text": dry_run_result.get("result_text", ""),
        "findings": list(dry_run_result.get("findings") or [])[:20],
        "recommended_next_gate": dry_run_result.get("recommended_next_gate", ""),
        "latest_event": latest_event,
        "evidence_kind": review_profile["evidence_kind"],
        "may_influence": list(review_profile["may_influence"]),
        "must_not_influence": list(review_profile["must_not_influence"]),
        "owner_review_question": review_profile["owner_question"],
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


def _is_supported_result_mode(dry_run_result):
    mode = dry_run_result.get("mode")
    if mode == "dry_run_result_review_only":
        return True
    return (
        mode == "single_shot_sentinel_advisory_result"
        and dry_run_result.get("status") == "recorded_from_single_shot_sentinel_llm"
        and str(dry_run_result.get("specialist_slug") or "").strip().lower() == "sentinel"
    )


def _unsafe_result_flags(dry_run_result):
    if dry_run_result.get("mode") == "single_shot_sentinel_advisory_result":
        unsafe_flags = [
            "dispatch_enabled",
            "runs_specialist_tools",
            "writes",
            "applies_runtime_change",
        ]
        enabled = [flag for flag in unsafe_flags if dry_run_result.get(flag)]
        if not dry_run_result.get("runs_specialist"):
            enabled.append("missing_runs_specialist")
        if not dry_run_result.get("runs_specialist_llm"):
            enabled.append("missing_runs_specialist_llm")
        return enabled
    unsafe_flags = [
        "runs_specialist",
        "dispatch_enabled",
        "runs_specialist_llm",
        "runs_specialist_tools",
        "writes",
        "applies_runtime_change",
    ]
    return [flag for flag in unsafe_flags if dry_run_result.get(flag)]


def _next_action(latest_event):
    event_type = latest_event.get("event_type") if isinstance(latest_event, dict) else ""
    if event_type == "accepted_for_learning":
        return "Already accepted for learning. Do not run or apply anything from this packet."
    if event_type == "rejected":
        return "Already rejected. Keep it as audit history only."
    return "Owner should accept, reject, or add a review note. No specialist or runtime action is performed."


def _review_profile_for(specialist_slug):
    return _RESULT_REVIEW_PROFILES.get(specialist_slug, {
        "evidence_kind": "agent_review_evidence",
        "may_influence": ("future planning notes",),
        "must_not_influence": ("runtime changes", "writes", "dispatch"),
        "owner_question": "Should this evidence guide future planning only?",
    })
