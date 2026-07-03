from datetime import datetime, timezone


TOOL_PERMISSION_VERSION = "charlie_tool_permissions_v1"


TOOL_CLASSES = {
    "vault_read": {"risk_level": "low", "requires_owner_approval": False},
    "vault_write": {"risk_level": "medium", "requires_owner_approval": False},
    "repo_read": {"risk_level": "low", "requires_owner_approval": False},
    "repo_write": {"risk_level": "medium", "requires_owner_approval": True},
    "test_run": {"risk_level": "low", "requires_owner_approval": False},
    "browser_check": {"risk_level": "low", "requires_owner_approval": False},
    "visual_check": {"risk_level": "low", "requires_owner_approval": False},
    "learning_write": {"risk_level": "medium", "requires_owner_approval": False},
    "git_commit": {"risk_level": "medium", "requires_owner_approval": True},
    "git_push": {"risk_level": "medium", "requires_owner_approval": True},
    "migration": {"risk_level": "high", "requires_owner_approval": True},
    "production_write": {"risk_level": "critical", "requires_owner_approval": True},
    "customer_send": {"risk_level": "critical", "requires_owner_approval": True},
    "public_post": {"risk_level": "critical", "requires_owner_approval": True},
    "payment": {"risk_level": "critical", "requires_owner_approval": True},
    "secret_read": {"risk_level": "critical", "requires_owner_approval": True},
}


AGENT_TOOL_ALLOWLIST = {
    "idea_expander": {"vault_read", "repo_read"},
    "concept_strategist": {"vault_read", "repo_read"},
    "product_architect": {"vault_read", "repo_read"},
    "visual_reference_interpreter": {"vault_read", "repo_read", "visual_check"},
    "creative_ui_designer": {"vault_read", "repo_read", "visual_check"},
    "ux_interaction_designer": {"vault_read", "repo_read", "browser_check", "visual_check"},
    "technical_architect": {"vault_read", "repo_read", "test_run"},
    "business_model_agent": {"vault_read", "repo_read"},
    "risk_agent": {"vault_read", "repo_read"},
    "council_synthesis": {"vault_read", "repo_read"},
    "planner": {"vault_read", "repo_read"},
    "architect": {"vault_read", "repo_read", "test_run"},
    "frontend_design_implementer": {"vault_read", "vault_write", "repo_read", "repo_write", "test_run", "browser_check", "visual_check", "git_commit", "git_push"},
    "builder": {"vault_read", "vault_write", "repo_read", "repo_write", "test_run", "browser_check", "visual_check", "git_commit", "git_push"},
    "tester": {"vault_read", "vault_write", "repo_read", "test_run", "browser_check", "visual_check"},
    "qa_red_team": {"vault_read", "vault_write", "repo_read", "test_run", "browser_check", "visual_check"},
    "visual_qa_reviewer": {"vault_read", "vault_write", "repo_read", "browser_check", "visual_check"},
    "security_reviewer": {"vault_read", "vault_write", "repo_read", "test_run"},
    "evidence_reviewer": {"vault_read", "vault_write", "repo_read", "test_run", "browser_check", "visual_check"},
    "product_reviewer": {"vault_read", "vault_write"},
    "business_reviewer": {"vault_read", "vault_write"},
    "reviewer": {"vault_read", "vault_write", "repo_read", "test_run", "browser_check", "visual_check", "learning_write"},
    "brain_guard": {"vault_read", "vault_write", "repo_read", "learning_write"},
    "improvement_analyst": {"vault_read", "vault_write", "repo_read", "learning_write"},
    "publisher": {"vault_read", "vault_write", "git_push"},
}


RED_ZONE_TOOLS = {"migration", "production_write", "customer_send", "public_post", "payment", "secret_read"}


def permission_packet(agent=""):
    agent = str(agent or "").strip().lower()
    allowed = sorted(AGENT_TOOL_ALLOWLIST.get(agent, {"vault_read"}))
    blocked = sorted(set(TOOL_CLASSES) - set(allowed))
    return {
        "version": TOOL_PERMISSION_VERSION,
        "agent": agent,
        "allowed_tool_classes": allowed,
        "blocked_tool_classes": blocked,
        "red_zone_tools": sorted(RED_ZONE_TOOLS),
        "rules": [
            "No tool outside the allowlist.",
            "Red-zone tools require explicit owner approval even if listed.",
            "Tool calls must be audited.",
            "Read/write authority must remain separate.",
        ],
    }


def check_tool_permission(agent, tool_class, owner_approved=False):
    agent = str(agent or "").strip().lower()
    tool_class = str(tool_class or "").strip().lower()
    allowed = tool_class in AGENT_TOOL_ALLOWLIST.get(agent, {"vault_read"})
    tool = TOOL_CLASSES.get(tool_class, {"risk_level": "unknown", "requires_owner_approval": True})
    owner_required = bool(tool.get("requires_owner_approval")) or tool_class in RED_ZONE_TOOLS
    permitted = allowed and (not owner_required or bool(owner_approved))
    return {
        "version": TOOL_PERMISSION_VERSION,
        "agent": agent,
        "tool_class": tool_class,
        "permitted": permitted,
        "allowed_by_role": allowed,
        "owner_approval_required": owner_required,
        "owner_approved": bool(owner_approved),
        "risk_level": tool.get("risk_level", "unknown"),
        "decision_reason": _decision_reason(allowed, owner_required, owner_approved),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def audit_tool_call(agent, tool_class, action, target="", owner_approved=False):
    permission = check_tool_permission(agent, tool_class, owner_approved=owner_approved)
    return {
        "version": TOOL_PERMISSION_VERSION,
        "agent": permission["agent"],
        "tool_class": permission["tool_class"],
        "action": str(action or "").strip()[:240],
        "target": str(target or "").strip()[:500],
        "permission": permission,
        "audit_status": "allowed" if permission["permitted"] else "blocked",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def tool_permission_registry():
    return {
        "version": TOOL_PERMISSION_VERSION,
        "tool_classes": TOOL_CLASSES,
        "agent_tool_allowlist": {agent: sorted(values) for agent, values in AGENT_TOOL_ALLOWLIST.items()},
        "red_zone_tools": sorted(RED_ZONE_TOOLS),
    }


def _decision_reason(allowed, owner_required, owner_approved):
    if not allowed:
        return "tool_class_not_allowed_for_agent"
    if owner_required and not owner_approved:
        return "owner_approval_required"
    return "allowed"
