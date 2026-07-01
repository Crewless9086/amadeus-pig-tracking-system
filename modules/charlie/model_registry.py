from datetime import datetime, timezone


MODEL_REGISTRY_VERSION = "charlie_model_registry_v1"


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
}


TASK_MODEL_MAP = {
    "summary": "cheap_summary",
    "classification": "cheap_summary",
    "security_review": "security_review",
    "income_stream": "business_review",
    "business_plan": "business_review",
    "review": "default_reasoning",
    "build": "default_reasoning",
    "orchestration": "default_reasoning",
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


def estimate_model_cost(model_key, input_tokens=0, output_tokens=0):
    model = MODEL_REGISTRY.get(model_key, MODEL_REGISTRY["default_reasoning"])
    input_cost = (max(int(input_tokens or 0), 0) / 1000) * float(model.get("input_cost_per_1k") or 0)
    output_cost = (max(int(output_tokens or 0), 0) / 1000) * float(model.get("output_cost_per_1k") or 0)
    return {
        "model_key": model_key if model_key in MODEL_REGISTRY else "default_reasoning",
        "input_tokens": max(int(input_tokens or 0), 0),
        "output_tokens": max(int(output_tokens or 0), 0),
        "estimated_cost": round(input_cost + output_cost, 6),
        "currency": "USD",
        "cost_source": "manual_registry_config",
    }


def model_registry_packet():
    return {
        "version": MODEL_REGISTRY_VERSION,
        "models": MODEL_REGISTRY,
        "task_model_map": TASK_MODEL_MAP,
        "safety_note": "Model routing is advisory until live provider/model prices are explicitly configured and benchmarked.",
    }
