from modules.charlie.mission_memory import replay_packet


REPLAY_STRESS_VERSION = "charlie_replay_stress_v1"


def stress_replay_mission(mission):
    mission = mission if isinstance(mission, dict) else {}
    mission_status = str(mission.get("status") or "").strip().lower()
    replay = replay_packet(mission)
    review = replay.get("review_packet") if isinstance(replay.get("review_packet"), dict) else {}
    memory = replay.get("mission_memory") if isinstance(replay.get("mission_memory"), dict) else {}
    if mission_status in {"new", "triaged", "planned", "approved"} and not review and not (memory.get("events") or memory.get("latest_by_agent")):
        return {
            "version": REPLAY_STRESS_VERSION,
            "mission_id": replay.get("mission_id", ""),
            "status": "not_started",
            "score": None,
            "checks": [],
            "issues": [],
            "recommended_actions": ["Mission has not executed yet; replay stress starts after first runner artifact, block, or review packet."],
            "replay": replay,
        }
    issues = []
    checks = [
        _check("final_artifact_contract", bool(review.get("review_status") or review.get("blocked_reason")), "Review packet has no status or blocker reason."),
        _check("test_evidence", bool(review.get("test_evidence") or review.get("blocked_reason")), "No test evidence and no explicit blocker."),
        _check("memory_recorded", bool(memory.get("events") or memory.get("latest_by_agent")), "No mission memory captured."),
        _check("recovery_path", not review.get("blocked_reason") or bool(review.get("partial_recovery") or memory.get("recovery_notes")), "Blocked mission has no recovery packet."),
        _check("debug_next_actions", bool(replay.get("next_debug_actions")), "Replay packet has no next debug actions."),
    ]
    for check in checks:
        if not check["passed"]:
            issues.append(check)
    score = max(0, 100 - (len(issues) * 18))
    return {
        "version": REPLAY_STRESS_VERSION,
        "mission_id": replay.get("mission_id", ""),
        "status": "pass" if score >= 82 else "needs_repair",
        "score": score,
        "checks": checks,
        "issues": issues,
        "recommended_actions": _recommended_actions(issues),
        "replay": replay,
    }


def stress_replay_missions(missions):
    missions = [mission for mission in missions if isinstance(mission, dict)]
    results = [stress_replay_mission(mission) for mission in missions]
    scored = [item for item in results if isinstance(item.get("score"), (int, float))]
    average = round(sum(item["score"] for item in scored) / len(scored), 1) if scored else 0
    return {
        "version": REPLAY_STRESS_VERSION,
        "mission_count": len(results),
        "scored_mission_count": len(scored),
        "average_score": average,
        "status": "pass" if scored and average >= 82 else "needs_more_evidence",
        "results": results,
    }


def golden_example_candidate(mission):
    mission = mission if isinstance(mission, dict) else {}
    stress = stress_replay_mission(mission)
    replay = stress.get("replay", {})
    review = replay.get("review_packet") if isinstance(replay.get("review_packet"), dict) else {}
    qualifies = (
        (stress.get("score") or 0) >= 90
        and review.get("review_status") == "ready_for_owner_review"
        and bool(review.get("test_evidence"))
        and not review.get("blocked_reason")
    )
    return {
        "version": "charlie_golden_example_candidate_v1",
        "mission_id": mission.get("mission_id", ""),
        "qualifies": qualifies,
        "score": stress.get("score", 0),
        "example_type": _example_type(mission),
        "summary": review.get("summary") or mission.get("title", ""),
        "source_refs": [
            item for item in [
                ((review.get("execution_artifacts") or {}).get("agent_ledger_path") if isinstance(review.get("execution_artifacts"), dict) else ""),
                review.get("pr_url", ""),
            ]
            if item
        ],
        "promotion_rule": "Owner or Brain Guard approval required before writing a real golden example into docs/09-vault-brain/09-examples.",
        "stress_issues": stress.get("issues", []),
    }


def _check(name, passed, failure):
    return {"name": name, "passed": bool(passed), "failure": "" if passed else failure}


def _recommended_actions(issues):
    actions = []
    names = {issue.get("name") for issue in issues}
    if "memory_recorded" in names:
        actions.append("Rerun through Agent Runner v2 so stage memory is recorded.")
    if "recovery_path" in names:
        actions.append("Generate a partial recovery packet before send-back.")
    if "test_evidence" in names:
        actions.append("Require tester/reviewer test evidence before owner review.")
    if "final_artifact_contract" in names:
        actions.append("Block the mission until final artifact status is explicit.")
    if not actions:
        actions.append("Replay stress passed; consider promotion as a golden-example candidate if owner approves.")
    return actions


def _example_type(mission):
    haystack = f"{mission.get('mission_type', '')} {mission.get('title', '')} {mission.get('raw_text', '')}".lower()
    if any(term in haystack for term in ["ui", "dashboard", "frontend", "visual"]):
        return "dashboard_ui"
    if any(term in haystack for term in ["income", "sales", "sam", "beacon", "meat"]):
        return "income_stream"
    if any(term in haystack for term in ["blocked", "recovery", "failure"]):
        return "recovery"
    return "mission_delivery"
