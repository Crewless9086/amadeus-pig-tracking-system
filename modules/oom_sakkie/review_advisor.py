from modules.oom_sakkie.trace_store import get_trace_review_summary, list_recent_traces


def get_review_advisor(channel="kiosk", days=14, limit=12):
    channel = str(channel or "kiosk").strip()[:40] or "kiosk"
    summary, summary_status = get_trace_review_summary(channel=channel, days=days)
    issue_traces, issues_status = list_recent_traces(
        limit=limit,
        channel=channel,
        review="issues",
        search="",
    )
    unreviewed_traces, unreviewed_status = list_recent_traces(
        limit=limit,
        channel=channel,
        review="unreviewed",
        search="",
    )

    advisor = build_review_advice(
        summary=summary,
        issue_traces=issue_traces,
        unreviewed_traces=unreviewed_traces,
        statuses={
            "review_summary": summary_status,
            "issue_traces": issues_status,
            "unreviewed_traces": unreviewed_status,
        },
    )
    advisor["channel"] = channel
    advisor["days"] = summary.get("days", days) if isinstance(summary, dict) else days
    return advisor, max(summary_status, issues_status, unreviewed_status)


def build_review_advice(summary, issue_traces, unreviewed_traces, statuses):
    summary = summary if isinstance(summary, dict) else {}
    issue_traces = issue_traces if isinstance(issue_traces, dict) else {}
    unreviewed_traces = unreviewed_traces if isinstance(unreviewed_traces, dict) else {}
    statuses = statuses if isinstance(statuses, dict) else {}

    configured = all(
        payload.get("configured", True)
        for payload in (summary, issue_traces, unreviewed_traces)
        if isinstance(payload, dict)
    )
    successful = all(status == 200 for status in statuses.values()) if statuses else False
    metrics = summary.get("summary") or {}
    review_queue = _review_queue(issue_traces.get("traces", []), unreviewed_traces.get("traces", []))
    suggestions = _suggestions(metrics, review_queue, configured)

    return {
        "success": successful,
        "configured": configured,
        "status": "ok" if successful else "review_advisor_unavailable",
        "mode": "advisory_only",
        "autonomous_marking_enabled": False,
        "writes_feedback": False,
        "summary": metrics,
        "review_queue": review_queue,
        "suggested_actions": suggestions,
        "statuses": statuses,
    }


def _review_queue(issue_rows, unreviewed_rows):
    queued = []
    seen = set()
    for row in issue_rows or []:
        trace_id = row.get("trace_id", "")
        if trace_id:
            seen.add(trace_id)
        queued.append(_queue_item(row, "reviewed_issue", "high"))
    for row in unreviewed_rows or []:
        trace_id = row.get("trace_id", "")
        if trace_id in seen:
            continue
        queued.append(_queue_item(row, _unreviewed_reason(row), _priority_for_unreviewed(row)))
    return queued


def _queue_item(row, reason, priority):
    feedback = row.get("latest_feedback") or {}
    return {
        "trace_id": row.get("trace_id", ""),
        "priority": priority,
        "reason": reason,
        "tool_name": row.get("tool_name") or "clarification",
        "user_text": row.get("user_text", ""),
        "answer": row.get("answer", ""),
        "created_at": row.get("created_at", ""),
        "latest_feedback_type": feedback.get("feedback_type", ""),
    }


def _unreviewed_reason(row):
    if row.get("stale_warnings"):
        return "unreviewed_with_stale_warning"
    if row.get("safety_notes"):
        return "unreviewed_with_safety_note"
    if not row.get("tool_name"):
        return "unreviewed_clarification"
    return "unreviewed"


def _priority_for_unreviewed(row):
    if row.get("stale_warnings") or row.get("safety_notes"):
        return "medium"
    if not row.get("tool_name"):
        return "medium"
    return "normal"


def _suggestions(metrics, review_queue, configured):
    if not configured:
        return [
            "Trace storage is not configured, so the advisor cannot inspect real kiosk history yet.",
        ]
    total = int(metrics.get("total_traces", 0) or 0)
    unreviewed = int(metrics.get("unreviewed_traces", 0) or 0)
    problems = int(metrics.get("problem_traces", 0) or 0)
    problem_rate = float(metrics.get("problem_rate_pct", 0) or 0)
    suggestions = []
    if total == 0:
        suggestions.append("No traces found in the review window. Use the kiosk for real checks before expanding tools.")
    if problems:
        suggestions.append("Review high-priority problem traces first and fix repeated wrong-tool or stale-data patterns before adding tools.")
    if problem_rate >= 20:
        suggestions.append("Problem rate is high for daily use. Hold expansion and harden routing or tool wording first.")
    if unreviewed:
        suggestions.append("Mark a small batch of unreviewed traces as correct or issue so the next build slice is based on evidence.")
    if review_queue:
        suggestions.append("Use the review queue as advisory input only; it does not mark feedback or change farm data.")
    if not suggestions:
        suggestions.append("Recent traces look reviewed and quiet. Keep using the kiosk daily before widening channels.")
    return suggestions
