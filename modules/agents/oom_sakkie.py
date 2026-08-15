"""Oom Sakkie Operational V1: governed farm coordination agent."""

from datetime import datetime, timezone

from modules.charlie.agent_runtime import AgentDefinition, delegate_to_agent


OOM_SAKKIE_DEFINITION = AgentDefinition(
    agent_id="oom-sakkie", name="Oom Sakkie", domain="farm_command", authority_tier="read_only",
    capabilities=("farm_operating_brief", "farm_question_coordination"),
    source_contract=("Herdmaster evidence", "approved farm specialist evidence"),
    handler=lambda request: run_oom_sakkie(request),
)


def run_oom_sakkie(request):
    request = request if isinstance(request, dict) else {}
    question = str(request.get("question") or request.get("goal") or "What needs attention on the farm?")
    herd, status = delegate_to_agent("herdmaster", {"goal": question, "question": question, "capability": "herd_overview", "required_freshness": "live"})
    sources = list(herd.get("sources") or []) if status < 400 else []
    direct = str(herd.get("direct_answer") or "Herdmaster evidence is currently unavailable.")
    proactive = None
    authority = request.get("gateway_authority") or request.get("scheduled_manager_context")
    owner_user_id = str(request.get("owner_user_id") or "")
    if authority is not None and owner_user_id:
        try:
            from modules.oom_sakkie.herdmaster_management_runtime import consume_current_herdmaster_management
            proactive = consume_current_herdmaster_management(authority=authority, owner_user_id=owner_user_id)
        except Exception:
            proactive = {"success": False, "status": "herdmaster_management_runtime_contained",
                "systemic_exception": {"reason": "proactive_manager_boundary_unavailable"},
                "specialist_result": None, "accepted_work_item_count": 0,
                "writes_farm_data": False, "sends_telegram": False,
                "protected_actions_performed": False}
    return {
        "success": status < 400, "status": "oom_sakkie_farm_evidence_ready" if status < 400 else "oom_sakkie_evidence_gap",
        "capability": "farm_question_coordination", "direct_answer": direct,
        "facts": list(herd.get("facts") or []), "metrics": dict(herd.get("metrics") or {}),
        "breakdown": dict(herd.get("breakdown") or {}), "anomalies": list(herd.get("anomalies") or []),
        "inferences": [], "recommendations": list(herd.get("recommendations") or []),
        "unresolved_questions": list(herd.get("unresolved_questions") or []), "sources": sources,
        "freshness": {"observed_at": datetime.now(timezone.utc).isoformat(), "mode": "coordinated_live_read"},
        "confidence": float(herd.get("confidence") or 0), "summary": f"Oom Sakkie coordinated Herdmaster: {herd.get('summary') or direct}",
        "delegations": [herd.get("agent")], "write_authority": False,
        "proactive_herdmaster_management": proactive,
    }
