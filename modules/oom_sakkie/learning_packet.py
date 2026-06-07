from datetime import datetime, timezone
import hashlib

from modules.oom_sakkie.learning_llm import ALLOWED_KINDS
from modules.oom_sakkie.learning_advisor import build_learning_advice
from modules.oom_sakkie.trace_store import get_trace_review_summary, list_review_advisor_traces


DEFAULT_FILES = [
    "modules/oom_sakkie/",
    "tests/test_oom_sakkie_service.py",
    "tests/test_oom_sakkie_routes.py",
    "tests/test_frontend_route_contracts.py",
    "templates/oom-sakkie.html",
    "static/js/oomSakkie.js",
    "static/css/main.css",
    "docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md",
    "docs/00-start-here/CURRENT_STATE.md",
    "docs/00-start-here/NEXT_STEPS.md",
]


def build_learning_packet(proposal):
    proposal = proposal if isinstance(proposal, dict) else {}
    kind = str(proposal.get("kind") or "").strip()
    if kind not in ALLOWED_KINDS:
        return {
            "success": False,
            "status": "invalid_proposal_kind",
            "allowed_kinds": sorted(ALLOWED_KINDS),
        }, 400

    packet = {
        "success": True,
        "status": "ok",
        "mode": "build_brief_only",
        "purpose": "turn_one_learning_proposal_into_a_human_review_packet",
        "writes_code": False,
        "applies_changes": False,
        "runs_llm": False,
        "writes_feedback": False,
        "changes_tools": False,
        "changes_prompts": False,
        "requires_human_approval": True,
        "proposal": _clean_proposal(proposal),
        "recommended_files": _recommended_files(kind),
        "verification": _verification(kind),
        "out_of_scope": _out_of_scope(),
    }
    packet["brief"] = _brief(packet)
    return packet, 200


def get_implementation_queue(channel="kiosk", days=14, limit=12):
    channel = str(channel or "kiosk").strip()[:40] or "kiosk"
    summary, summary_status = get_trace_review_summary(channel=channel, days=days)
    advisor_traces, traces_status = list_review_advisor_traces(
        limit=limit,
        channel=channel,
        days=days,
    )
    issue_traces = advisor_traces.get("issue_traces", []) if isinstance(advisor_traces, dict) else []
    advice = build_learning_advice(
        summary=summary,
        issue_traces=issue_traces,
        statuses={"review_summary": summary_status, "advisor_traces": traces_status},
    )
    proposals = advice.get("proposals", []) if isinstance(advice, dict) else []
    packets = []
    skipped = []
    for proposal in proposals:
        if _should_prepare_packet(proposal):
            packet, status_code = build_learning_packet(proposal)
            if status_code == 200:
                packets.append(packet)
            else:
                skipped.append({
                    "proposal": _clean_proposal(proposal),
                    "reason": packet.get("status", "packet_rejected"),
                })
        else:
            skipped.append({
                "proposal": _clean_proposal(proposal),
                "reason": "below_auto_prepare_threshold",
            })

    return {
        "success": summary_status == 200 and traces_status == 200,
        "configured": bool(summary.get("configured", True)) if isinstance(summary, dict) else False,
        "status": "ok" if summary_status == 200 and traces_status == 200 else "implementation_queue_unavailable",
        "mode": "auto_prepared_review_queue",
        "channel": channel,
        "days": summary.get("days", days) if isinstance(summary, dict) else days,
        "auto_prepare_policy": {
            "enabled": True,
            "writes_code": False,
            "applies_changes": False,
            "runs_llm": False,
            "writes_feedback": False,
            "requires_human_approval": True,
            "threshold": "high_priority_or_repeated_pattern_or_two_or_more_issue_traces",
        },
        "packets": packets[:6],
        "skipped": skipped[:6],
        "source_proposals": proposals[:8],
        "statuses": {"review_summary": summary_status, "advisor_traces": traces_status},
    }, max(summary_status, traces_status)


def approve_build_request(packet, approved_by="owner"):
    packet = packet if isinstance(packet, dict) else {}
    if not packet.get("success") or packet.get("mode") != "build_brief_only":
        return {
            "success": False,
            "status": "invalid_build_packet",
        }, 400
    if packet.get("writes_code") or packet.get("applies_changes"):
        return {
            "success": False,
            "status": "unsafe_packet_rejected",
        }, 400

    proposal = packet.get("proposal") if isinstance(packet.get("proposal"), dict) else {}
    request = {
        "success": True,
        "status": "approved_for_build",
        "mode": "build_request_only",
        "build_request_id": _build_request_id(packet),
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "approved_by": str(approved_by or "owner")[:80],
        "builder_enabled": False,
        "writes_code_now": False,
        "applies_changes_now": False,
        "requires_next_gate": "builder_agent_review_and_patch_approval",
        "proposal": _clean_proposal(proposal),
        "brief": str(packet.get("brief") or "")[:8000],
        "recommended_files": [
            str(path)[:220] for path in packet.get("recommended_files", [])
            if isinstance(path, str)
        ][:14],
        "verification": [
            str(item)[:260] for item in packet.get("verification", [])
            if isinstance(item, str)
        ][:8],
        "out_of_scope": _out_of_scope(),
        "handoff": (
            "This build request is approved for a future Forge/Builder step only. "
            "Do not edit files until the builder step is explicitly run and its patch is separately approved."
        ),
    }
    return request, 200


def _should_prepare_packet(proposal):
    proposal = proposal if isinstance(proposal, dict) else {}
    priority = str(proposal.get("priority") or "").strip().lower()
    kind = str(proposal.get("kind") or "").strip()
    evidence = str(proposal.get("evidence") or "")
    if priority == "high":
        return True
    if kind == "tool_pattern_review":
        return True
    return _evidence_count(evidence) >= 2


def _evidence_count(evidence):
    for token in evidence.replace("(", " ").replace(")", " ").split():
        cleaned = token.strip(".,:;")
        if cleaned.isdigit():
            return int(cleaned)
    return 0


def _build_request_id(packet):
    text = "|".join([
        str((packet.get("proposal") or {}).get("kind") or ""),
        str((packet.get("proposal") or {}).get("title") or ""),
        str(packet.get("brief") or ""),
    ])
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12].upper()
    return f"OSK-BUILD-{digest}"


def _clean_proposal(proposal):
    return {
        "kind": str(proposal.get("kind") or "")[:80],
        "priority": str(proposal.get("priority") or "normal")[:24],
        "title": str(proposal.get("title") or "Learning proposal")[:160],
        "evidence": str(proposal.get("evidence") or "")[:800],
        "recommended_action": str(proposal.get("recommended_action") or "")[:800],
        "approval_required": True,
    }


def _recommended_files(kind):
    extra = {
        "routing_review": ["modules/oom_sakkie/service.py", "modules/oom_sakkie/llm_router.py"],
        "data_freshness_review": ["modules/oom_sakkie/tools.py", "modules/telemetry/"],
        "answer_style_review": ["modules/oom_sakkie/llm_answer.py", "modules/oom_sakkie/tools.py"],
        "tool_gap_review": ["modules/oom_sakkie/tools.py", "modules/oom_sakkie/service.py"],
        "briefing_structure_review": ["modules/oom_sakkie/tools.py", "modules/oom_sakkie/llm_answer.py"],
        "test_gap_review": ["tests/"],
        "tool_pattern_review": ["modules/oom_sakkie/tools.py", "modules/oom_sakkie/service.py", "modules/oom_sakkie/llm_answer.py"],
    }.get(kind, [])
    files = []
    for item in extra + DEFAULT_FILES:
        if item not in files:
            files.append(item)
    return files[:14]


def _verification(kind):
    checks = [
        r".\venv\Scripts\python.exe -m unittest tests.test_oom_sakkie_service tests.test_oom_sakkie_routes tests.test_frontend_route_contracts",
        "node --check static/js/oomSakkie.js",
    ]
    if kind in {"routing_review", "answer_style_review", "briefing_structure_review"}:
        checks.append("Run a local Oom Sakkie smoke for the exact owner phrase(s) from the evidence.")
    if kind == "data_freshness_review":
        checks.append("Run the affected telemetry endpoint once and confirm stale_warnings/safety_notes are honest.")
    return checks


def _out_of_scope():
    return [
        "No Telegram cutover.",
        "No write tools.",
        "No physical controls.",
        "No always-on mic or wake word.",
        "No autonomous specialist delegation.",
        "No code application from the kiosk.",
    ]


def _brief(packet):
    proposal = packet["proposal"]
    lines = [
        "# Oom Sakkie Learning Build Brief",
        "",
        "## Objective",
        proposal["title"],
        "",
        "## Evidence",
        proposal["evidence"] or "No evidence text supplied.",
        "",
        "## Recommended Action",
        proposal["recommended_action"] or "Inspect the traces and propose the smallest safe change.",
        "",
        "## Constraints",
        "- Keep the change read-only unless the owner explicitly approves a separate write path.",
        "- Preserve backend-as-brain and the existing safety policy.",
        "- Add or update tests for the exact owner phrase or failure pattern.",
        "- Update CURRENT_STATE, NEXT_STEPS, and CLAUDE_REVIEW_HANDOFF if behavior changes.",
        "",
        "## Files To Inspect",
    ]
    lines.extend(f"- {path}" for path in packet["recommended_files"])
    lines.extend(["", "## Verification"])
    lines.extend(f"- {cmd}" for cmd in packet["verification"])
    lines.extend(["", "## Out Of Scope"])
    lines.extend(f"- {item}" for item in packet["out_of_scope"])
    lines.extend([
        "",
        "## Approval Rule",
        "This brief is advisory only. A human must approve implementation before code is changed.",
    ])
    return "\n".join(lines)
