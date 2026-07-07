import os
from datetime import datetime, timezone


MODEL_REGISTRY_VERSION = "charlie_model_registry_v1"
DEFAULT_CLAUDE_MODEL = "claude-sonnet-5"
CLAUDE_REVIEW_AGENTS = {
    "council_synthesis",
    "risk_agent",
    "qa_red_team",
    "product_reviewer",
    "business_reviewer",
    "security_reviewer",
    "evidence_reviewer",
}


MODEL_REGISTRY = {
    "default_reasoning": {
        "provider": "manual",
        "model": "configured_by_runner",
        "approved_use_cases": ["orchestration", "planning", "review"],
        "blocked_use_cases": ["secret_access", "unapproved_external_send"],
        "input_cost_per_1k": 0.0,
        "output_cost_per_1k": 0.0,
        "risk_level": "medium",
    },
    "cheap_summary": {
        "provider": "manual",
        "model": "configured_by_runner_small",
        "approved_use_cases": ["summarization", "classification", "formatting"],
        "blocked_use_cases": ["final_security_review", "legal_commitment", "money_path_decision"],
        "input_cost_per_1k": 0.0,
        "output_cost_per_1k": 0.0,
        "risk_level": "low",
    },
    "security_review": {
        "provider": "manual",
        "model": "configured_by_runner_high_reasoning",
        "approved_use_cases": ["security_review", "prompt_injection_review", "permission_review"],
        "blocked_use_cases": ["self_approval", "production_secret_access"],
        "input_cost_per_1k": 0.0,
        "output_cost_per_1k": 0.0,
        "risk_level": "high",
    },
    "business_review": {
        "provider": "manual",
        "model": "configured_by_runner_high_reasoning",
        "approved_use_cases": ["income_stream", "business_model", "risk_register"],
        "blocked_use_cases": ["binding_pricing", "customer_send_without_owner"],
        "input_cost_per_1k": 0.0,
        "output_cost_per_1k": 0.0,
        "risk_level": "high",
    },
    "vision_design": {
        "provider": "manual",
        "model": "configured_by_runner_vision_design",
        "approved_use_cases": ["visual_reference_analysis", "ui_design", "ux_design", "screenshot_review"],
        "blocked_use_cases": ["self_approval", "production_secret_access", "customer_send_without_owner"],
        "input_cost_per_1k": 0.0,
        "output_cost_per_1k": 0.0,
        "risk_level": "medium",
    },
    "frontend_build": {
        "provider": "manual",
        "model": "configured_by_runner_frontend_coding",
        "approved_use_cases": ["frontend_implementation", "browser_test_repair", "responsive_layout"],
        "blocked_use_cases": ["self_approval", "production_secret_access", "unapproved_external_send"],
        "input_cost_per_1k": 0.0,
        "output_cost_per_1k": 0.0,
        "risk_level": "medium",
    },
}


TASK_MODEL_MAP = {
    "summary": "cheap_summary",
    "classification": "cheap_summary",
    "security_review": "security_review",
    "income_stream": "business_review",
    "business_plan": "business_review",
    "review": "default_reasoning",
    "build": "default_reasoning",
    "ui_design": "vision_design",
    "frontend": "frontend_build",
    "visual_review": "vision_design",
    "orchestration": "default_reasoning",
}


AGENT_MODEL_MAP = {
    "idea_expander": "default_reasoning",
    "concept_strategist": "business_review",
    "product_architect": "default_reasoning",
    "visual_reference_interpreter": "vision_design",
    "creative_ui_designer": "vision_design",
    "ux_interaction_designer": "vision_design",
    "technical_architect": "default_reasoning",
    "source_mapper": "default_reasoning",
    "business_model_agent": "business_review",
    "risk_agent": "security_review",
    "council_synthesis": "default_reasoning",
    "planner": "default_reasoning",
    "architect": "default_reasoning",
    "frontend_design_implementer": "frontend_build",
    "builder": "default_reasoning",
    "tester": "default_reasoning",
    "qa_red_team": "security_review",
    "visual_qa_reviewer": "vision_design",
    "product_reviewer": "default_reasoning",
    "business_reviewer": "business_review",
    "security_reviewer": "security_review",
    "evidence_reviewer": "default_reasoning",
    "reviewer": "default_reasoning",
    "publisher": "default_reasoning",
    "brain_guard": "security_review",
    "improvement_analyst": "business_review",
}


def choose_model(task_type="", risk_level="medium", required_use_case=""):
    task = str(task_type or "").strip().lower().replace(" ", "_")
    key = TASK_MODEL_MAP.get(task, "default_reasoning")
    if str(risk_level or "").lower() in {"high", "critical"} and task not in {"summary", "classification"}:
        if required_use_case in {"security_review", "prompt_injection_review", "permission_review"}:
            key = "security_review"
        elif required_use_case in {"income_stream", "business_model", "risk_register"}:
            key = "business_review"
        else:
            key = "default_reasoning"
    model = dict(MODEL_REGISTRY[key])
    model["registry_key"] = key
    model["selected_at"] = datetime.now(timezone.utc).isoformat()
    model["selection_reason"] = f"task_type={task or 'default'} risk_level={risk_level or 'medium'}"
    return model


def choose_agent_model(agent="", mission_type="", risk_level="medium"):
    agent = str(agent or "").strip().lower()
    model_key = AGENT_MODEL_MAP.get(agent, "default_reasoning")
    if str(risk_level or "").lower() in {"high", "critical"} and agent not in {"idea_expander", "product_architect"}:
        if agent in {"risk_agent", "qa_red_team", "security_reviewer", "brain_guard"}:
            model_key = "security_review"
        elif "income" in str(mission_type or "").lower() or agent in {"business_model_agent", "business_reviewer"}:
            model_key = "business_review"
    model = dict(MODEL_REGISTRY.get(model_key, MODEL_REGISTRY["default_reasoning"]))
    model["registry_key"] = model_key if model_key in MODEL_REGISTRY else "default_reasoning"
    model["agent"] = agent
    model["mission_type"] = str(mission_type or "").strip()
    model["selected_at"] = datetime.now(timezone.utc).isoformat()
    model["selection_reason"] = f"agent={agent or 'unknown'} mission_type={mission_type or 'unknown'} risk_level={risk_level or 'medium'}"
    runtime = _runtime_model_config(agent, model["registry_key"])
    model.update(runtime)
    return model


def _runtime_model_config(agent, registry_key):
    agent_key = str(agent or "").strip().upper().replace("-", "_")
    registry_env_key = str(registry_key or "").strip().upper().replace("-", "_")
    explicit_provider = (
        os.getenv(f"CHARLIE_AGENT_PROVIDER_{agent_key}")
        or os.getenv(f"CHARLIE_PROVIDER_{registry_env_key}")
        or ""
    ).strip()
    model_name = (
        os.getenv(f"CHARLIE_AGENT_MODEL_{agent_key}")
        or os.getenv(f"CHARLIE_MODEL_{registry_env_key}")
        or ""
    ).strip()
    provider = explicit_provider or "codex_cli"
    anthropic_key_present = _anthropic_api_key_present()
    if not explicit_provider and not model_name and _claude_default_enabled(agent, registry_key):
        provider = "anthropic"
        model_name = os.getenv("CHARLIE_CLAUDE_MODEL", DEFAULT_CLAUDE_MODEL).strip() or DEFAULT_CLAUDE_MODEL
    input_cost = os.getenv(f"CHARLIE_MODEL_{registry_env_key}_INPUT_COST_PER_1K")
    output_cost = os.getenv(f"CHARLIE_MODEL_{registry_env_key}_OUTPUT_COST_PER_1K")
    return {
        "runtime_provider": provider,
        "runtime_model": model_name,
        "runtime_configured": bool(model_name) and (provider != "anthropic" or anthropic_key_present),
        "provider_ready": provider != "anthropic" or anthropic_key_present,
        "api_key_env": _anthropic_api_key_env_name() if provider == "anthropic" else "",
        "runtime_note": (
            "Runner will call the Anthropic Messages API for this review/specialist agent."
            if provider == "anthropic" and anthropic_key_present
            else "Anthropic provider selected but ANTHROPIC_API_KEY is missing; ANTROPIC_API_KEY is accepted as a temporary typo alias."
            if provider == "anthropic"
            else
            "Runner will request this per-agent model from the Codex CLI."
            if model_name
            else "No per-agent runtime model env configured; runner uses the Codex CLI default while recording advisory routing."
        ),
        "runtime_cost_overrides": {
            "input_cost_per_1k": _float_or_none(input_cost),
            "output_cost_per_1k": _float_or_none(output_cost),
        },
    }


def _claude_default_enabled(agent, registry_key):
    if str(os.getenv("CHARLIE_CLAUDE_REVIEW_ENABLED") or "1").strip().lower() in {"0", "false", "no", "off"}:
        return False
    return str(agent or "").strip().lower() in CLAUDE_REVIEW_AGENTS and registry_key in {
        "default_reasoning",
        "security_review",
        "business_review",
    }


def _anthropic_api_key_present():
    return bool(_anthropic_api_key_env_name())


def _anthropic_api_key_env_name():
    if str(os.getenv("ANTHROPIC_API_KEY") or "").strip():
        return "ANTHROPIC_API_KEY"
    if str(os.getenv("ANTROPIC_API_KEY") or "").strip():
        return "ANTROPIC_API_KEY"
    return ""


def estimate_model_cost(model_key, input_tokens=0, output_tokens=0):
    model = MODEL_REGISTRY.get(model_key, MODEL_REGISTRY["default_reasoning"])
    runtime = _runtime_model_config("", model_key)
    overrides = runtime.get("runtime_cost_overrides") if isinstance(runtime.get("runtime_cost_overrides"), dict) else {}
    input_rate = overrides.get("input_cost_per_1k") if overrides.get("input_cost_per_1k") is not None else model.get("input_cost_per_1k")
    output_rate = overrides.get("output_cost_per_1k") if overrides.get("output_cost_per_1k") is not None else model.get("output_cost_per_1k")
    input_cost = (max(int(input_tokens or 0), 0) / 1000) * float(input_rate or 0)
    output_cost = (max(int(output_tokens or 0), 0) / 1000) * float(output_rate or 0)
    return {
        "model_key": model_key if model_key in MODEL_REGISTRY else "default_reasoning",
        "input_tokens": max(int(input_tokens or 0), 0),
        "output_tokens": max(int(output_tokens or 0), 0),
        "estimated_cost": round(input_cost + output_cost, 6),
        "currency": "USD",
        "cost_source": "manual_registry_config",
        "runtime_model": runtime.get("runtime_model", ""),
    }


def model_registry_packet():
    return {
        "version": MODEL_REGISTRY_VERSION,
        "models": MODEL_REGISTRY,
        "task_model_map": TASK_MODEL_MAP,
        "agent_model_map": AGENT_MODEL_MAP,
        "runtime_env": {
            "agent_model_pattern": "CHARLIE_AGENT_MODEL_<AGENT_NAME>",
            "registry_model_pattern": "CHARLIE_MODEL_<REGISTRY_KEY>",
            "claude_enabled_pattern": "CHARLIE_CLAUDE_REVIEW_ENABLED=1",
            "claude_model_pattern": "CHARLIE_CLAUDE_MODEL",
            "anthropic_api_key": "ANTHROPIC_API_KEY",
            "anthropic_typo_alias_supported": "ANTROPIC_API_KEY",
            "claude_default_review_agents": sorted(CLAUDE_REVIEW_AGENTS),
            "cost_patterns": [
                "CHARLIE_MODEL_<REGISTRY_KEY>_INPUT_COST_PER_1K",
                "CHARLIE_MODEL_<REGISTRY_KEY>_OUTPUT_COST_PER_1K",
            ],
        },
        "safety_note": "Claude routing is active for configured review/specialist stages only; Builder/Test execution stays local until tool-execution authority is separately reviewed.",
    }


def _float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
