SENTINEL_SINGLE_SHOT_SPECIALIST = "sentinel"
SENTINEL_SINGLE_SHOT_RESULT_MODE = "single_shot_sentinel_advisory_result"
SENTINEL_SINGLE_SHOT_RESULT_STATUS = "recorded_from_single_shot_sentinel_llm"
SENTINEL_SINGLE_SHOT_POLICY_MODE = "single_shot_advisory_only"

SENTINEL_SINGLE_SHOT_RESULT_FLAGS = {
    "runs_specialist": True,
    "dispatch_enabled": False,
    "runs_specialist_llm": True,
    "runs_specialist_tools": False,
    "writes": False,
    "applies_runtime_change": False,
}

SENTINEL_SINGLE_SHOT_FORBIDDEN_TRUE_FLAGS = (
    "dispatch_enabled",
    "runs_specialist_tools",
    "writes",
    "applies_runtime_change",
)

SENTINEL_SINGLE_SHOT_REQUIRED_TRUE_FLAGS = (
    "runs_specialist",
    "runs_specialist_llm",
)


def sentinel_single_shot_identity():
    return {
        "mode": SENTINEL_SINGLE_SHOT_RESULT_MODE,
        "status": SENTINEL_SINGLE_SHOT_RESULT_STATUS,
        "specialist_slug": SENTINEL_SINGLE_SHOT_SPECIALIST,
    }


def sentinel_single_shot_result_flags():
    return dict(SENTINEL_SINGLE_SHOT_RESULT_FLAGS)


def is_sentinel_single_shot_result(result):
    result = result if isinstance(result, dict) else {}
    return (
        result.get("mode") == SENTINEL_SINGLE_SHOT_RESULT_MODE
        and result.get("status") == SENTINEL_SINGLE_SHOT_RESULT_STATUS
        and str(result.get("specialist_slug") or "").strip().lower() == SENTINEL_SINGLE_SHOT_SPECIALIST
    )


def sentinel_single_shot_flag_errors(result):
    result = result if isinstance(result, dict) else {}
    errors = [flag for flag in SENTINEL_SINGLE_SHOT_FORBIDDEN_TRUE_FLAGS if result.get(flag)]
    for flag in SENTINEL_SINGLE_SHOT_REQUIRED_TRUE_FLAGS:
        if not result.get(flag):
            errors.append(f"missing_{flag}")
    return errors
