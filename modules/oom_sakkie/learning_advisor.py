from collections import Counter

from modules.oom_sakkie.learning_llm import analyze_learning_with_llm, llm_learning_policy
from modules.oom_sakkie.trace_store import get_trace_review_summary, list_review_advisor_traces


def get_learning_advisor(channel="kiosk", days=14, limit=12):
    channel = str(channel or "kiosk").strip()[:40] or "kiosk"
    summary, summary_status = get_trace_review_summary(channel=channel, days=days)
    advisor_traces, traces_status = list_review_advisor_traces(
        limit=limit,
        channel=channel,
        days=days,
    )
    result = build_learning_advice(
        summary=summary,
        issue_traces=advisor_traces.get("issue_traces", []) if isinstance(advisor_traces, dict) else [],
        statuses={"review_summary": summary_status, "advisor_traces": traces_status},
    )
    result["channel"] = channel
    result["days"] = summary.get("days", days) if isinstance(summary, dict) else days
    return result, max(summary_status, traces_status)


def run_learning_analysis(channel="kiosk", days=14, limit=12):
    channel = str(channel or "kiosk").strip()[:40] or "kiosk"
    summary, summary_status = get_trace_review_summary(channel=channel, days=days)
    advisor_traces, traces_status = list_review_advisor_traces(
        limit=limit,
        channel=channel,
        days=days,
    )
    issue_traces = advisor_traces.get("issue_traces", []) if isinstance(advisor_traces, dict) else []
    deterministic = build_learning_advice(
        summary=summary,
        issue_traces=issue_traces,
        statuses={"review_summary": summary_status, "advisor_traces": traces_status},
    )
    analysis = analyze_learning_with_llm(
        summary=summary.get("summary", {}) if isinstance(summary, dict) else {},
        issue_traces=issue_traces,
        deterministic_proposals=deterministic.get("proposals", []),
    )
    return {
        "success": summary_status == 200 and traces_status == 200 and analysis.get("status") == "ok",
        "configured": bool(summary.get("configured", True)) if isinstance(summary, dict) else False,
        "status": analysis.get("status", "unknown"),
        "mode": "advisory_only",
        "policy": llm_learning_policy(),
        "writes_code": False,
        "writes_feedback": False,
        "runs_llm": bool(analysis.get("ran")),
        "requires_human_approval": True,
        "channel": channel,
        "days": summary.get("days", days) if isinstance(summary, dict) else days,
        "deterministic_proposals": deterministic.get("proposals", []),
        "llm_proposals": analysis.get("proposals", []),
        "statuses": {"review_summary": summary_status, "advisor_traces": traces_status},
    }, max(summary_status, traces_status)


def build_learning_advice(summary, issue_traces, statuses):
    summary = summary if isinstance(summary, dict) else {}
    issue_traces = issue_traces if isinstance(issue_traces, list) else []
    statuses = statuses if isinstance(statuses, dict) else {}
    configured = bool(summary.get("configured", True))
    successful = all(status == 200 for status in statuses.values()) if statuses else False
    metrics = summary.get("summary") or {}
    proposals = _learning_proposals(issue_traces)
    return {
        "success": successful,
        "configured": configured,
        "status": "ok" if successful else "learning_advisor_unavailable",
        "mode": "advisory_only",
        "writes_code": False,
        "writes_feedback": False,
        "runs_llm": False,
        "llm_learning": llm_learning_policy(),
        "requires_human_approval": True,
        "summary": metrics,
        "proposals": proposals,
        "suggested_next_step": _suggested_next_step(metrics, proposals, configured),
        "statuses": statuses,
    }


def _learning_proposals(issue_traces):
    proposals = []
    feedback_counts = Counter()
    tool_counts = Counter()
    for row in issue_traces:
        feedback_type = ((row.get("latest_feedback") or {}).get("feedback_type") or "").strip()
        tool_name = (row.get("tool_name") or "clarification").strip() or "clarification"
        if not feedback_type:
            continue
        feedback_counts[feedback_type] += 1
        tool_counts[(feedback_type, tool_name)] += 1

    for feedback_type, count in feedback_counts.most_common():
        proposal = _proposal_for_feedback(feedback_type, count, issue_traces)
        if proposal:
            proposals.append(proposal)

    for (feedback_type, tool_name), count in tool_counts.most_common(5):
        if count < 2:
            continue
        proposals.append({
            "kind": "tool_pattern_review",
            "priority": "medium",
            "title": f"Repeated {feedback_type} on {tool_name}",
            "evidence": f"{count} reviewed issue trace(s) in the current window.",
            "recommended_action": "Inspect the repeated traces before changing routing or tool wording.",
            "approval_required": True,
        })

    return proposals[:8]


def _proposal_for_feedback(feedback_type, count, issue_traces):
    examples = [
        row.get("user_text", "")
        for row in issue_traces
        if ((row.get("latest_feedback") or {}).get("feedback_type") == feedback_type)
    ][:2]
    evidence = f"{count} reviewed issue trace(s)."
    if examples:
        evidence = f"{evidence} Example: {examples[0]}"

    mapping = {
        "wrong_tool": (
            "routing_review",
            "high",
            "Review routing aliases or LLM fallback guidance",
            "Add or adjust deterministic aliases only after confirming the repeated owner phrasing.",
        ),
        "stale_or_missing_data": (
            "data_freshness_review",
            "high",
            "Review stale or missing data source behavior",
            "Check whether the source endpoint should expose clearer stale warnings or refresh timing.",
        ),
        "bad_wording": (
            "answer_style_review",
            "medium",
            "Review answer wording and composer instructions",
            "Tighten the deterministic summary or answer-composer prompt for the affected tool.",
        ),
        "needs_follow_up": (
            "tool_gap_review",
            "medium",
            "Review whether a new read-only tool or composite brief is needed",
            "Define the smallest read-only tool contract before adding any new surface area.",
        ),
    }
    if feedback_type not in mapping:
        return None
    kind, priority, title, action = mapping[feedback_type]
    return {
        "kind": kind,
        "priority": priority,
        "title": title,
        "evidence": evidence,
        "recommended_action": action,
        "approval_required": True,
    }


def _suggested_next_step(metrics, proposals, configured):
    if not configured:
        return "Configure trace storage before trying to learn from kiosk use."
    if not int(metrics.get("reviewed_traces", 0) or 0):
        return "Mark several traces first; learning proposals require human feedback."
    if proposals:
        return "Pick one proposal, inspect its evidence traces, then approve a narrow code change manually."
    return "No learning proposal is strong enough yet. Keep using the kiosk and marking traces."
