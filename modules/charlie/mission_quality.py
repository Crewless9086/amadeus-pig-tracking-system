from datetime import datetime, timezone
from pathlib import Path

from modules.charlie.runner_preflight import python_test_command


REPO_ROOT = Path(__file__).resolve().parents[2]

KNOWN_FAILURE_PATTERNS = [
    {
        "code": "pytest_missing",
        "severity": "medium",
        "needles": ("no module named pytest", "pytest is not installed", "pytest unavailable", "pytest is unavailable"),
        "summary": "Agent tried pytest in a repo that currently uses unittest for local Python verification.",
        "recovery_steps": [
            "Stop retrying pytest unless pytest is added to repo dependencies.",
            "Run the focused unittest command for the changed module.",
            "Record the pytest miss as advisory only when unittest evidence passes.",
        ],
    },
    {
        "code": "stale_review_packet",
        "severity": "high",
        "needles": ("stale_review_packet_status", "stale blocked review packet", "stale_send_back", "send_back packet"),
        "summary": "Review packet persistence read-back found stale or non-owner-review status.",
        "recovery_steps": [
            "Do not mark the mission pr_ready.",
            "Rewrite the review packet with review_status ready_for_owner_review or keep the mission blocked.",
            "Verify the packet by reading it back from mission storage before owner review.",
        ],
    },
    {
        "code": "branch_mismatch",
        "severity": "high",
        "needles": ("branch mismatch", "pr branch", "head branch", "wrong branch", "not pushed"),
        "summary": "PR/review evidence may point at a branch or commit different from the worktree result.",
        "recovery_steps": [
            "Check git branch, git status, and PR head commit.",
            "Push the correct branch head.",
            "Refresh review evidence after GitHub checks run on the right commit.",
        ],
    },
    {
        "code": "powershell_redirect_conflict",
        "severity": "medium",
        "needles": ("stdout and stderr cannot be redirected to the same file", "redirect standard output and standard error"),
        "summary": "PowerShell preview/test command used an invalid same-file stdout/stderr redirect.",
        "recovery_steps": [
            "Use separate stdout and stderr files or no redirect.",
            "Prefer Start-Process with explicit ArgumentList for local preview servers.",
            "Record the working local URL in review evidence.",
        ],
    },
    {
        "code": "powershell_quoting",
        "severity": "medium",
        "needles": ("parsererror", "unexpected token", "missing closing", "unterminated string", "syntaxerror"),
        "summary": "Inline shell quoting or inline Python failed before the intended command could run.",
        "recovery_steps": [
            "Avoid complex inline quoting for runner commands.",
            "Use checked repo scripts or simple one-command invocations.",
            "Rerun the smallest focused command and record exact output.",
        ],
    },
    {
        "code": "windows_temp_lock",
        "severity": "low",
        "needles": ("permissionerror", "tempfile", "temporary directory", "being used by another process"),
        "summary": "Local Windows temp/worktree lock interfered with a command or test run.",
        "recovery_steps": [
            "Rerun the focused test once after confirming the worktree is writable.",
            "If it repeats, include the lock path in the recovery packet.",
            "Do not treat a one-off temp lock as a code regression without a repeat.",
        ],
    },
    {
        "code": "review_media_missing",
        "severity": "high",
        "needles": ("visual review media was not captured", "review media not found", "screenshot", "generated_owner_review_packet"),
        "summary": "Owner review reached a visual or UI mission without durable clickable media evidence.",
        "recovery_steps": [
            "Regenerate local preview and screenshot evidence.",
            "Store review media under the mission review-media path.",
            "Do not approve owner review until screenshots or a working local URL are clickable.",
        ],
    },
]


def classify_known_failures(*texts):
    combined = "\n".join(str(text or "") for text in texts).lower()
    findings = []
    if not combined.strip():
        return findings
    for pattern in KNOWN_FAILURE_PATTERNS:
        if any(needle in combined for needle in pattern["needles"]):
            findings.append({
                "code": pattern["code"],
                "severity": pattern["severity"],
                "summary": pattern["summary"],
                "recovery_steps": list(pattern["recovery_steps"]),
            })
    return findings


def repo_test_command_memory(changed_files=None):
    changed = [str(path or "").replace("\\", "/") for path in (changed_files or []) if str(path or "").strip()]
    commands = []
    notes = [
        "This repo's Python tests are unittest-based. Do not guess pytest unless repo dependencies prove pytest is installed.",
        "Prefer focused unittest modules plus node --check for changed JavaScript.",
    ]

    def add(command, reason):
        if command and command not in [item["command"] for item in commands]:
            commands.append({"command": command, "reason": reason})

    if not changed:
        add(python_test_command("-m unittest tests.test_charlie_execution_bridge tests.test_charlie_core_workflow"), "Default CHARLIE CORE focused regression suite.")
    if any(path.startswith("modules/charlie/") or path.startswith("scripts/charlie_") for path in changed):
        add(python_test_command("-m unittest tests.test_charlie_execution_bridge tests.test_charlie_core_workflow tests.test_charlie_mission_store tests.test_charlie_improvement_analyst"), "CHARLIE runner, workflow, store, and Analyst regression suite.")
    if any(path.startswith("modules/pig_weights/") for path in changed):
        add(python_test_command("-m unittest tests.test_pig_weights_bulk_service tests.test_pig_weights_litter_service tests.test_farm_supabase_read_service"), "Pig tracking focused service tests.")
    if any(path.startswith("modules/sales/") for path in changed):
        add(python_test_command("-m unittest tests.test_sales_transaction_routes tests.test_sam_meat_runtime tests.test_sam_command_state"), "SAM/meat sales focused backend tests.")
    for path in changed:
        if path.startswith("static/js/") and path.endswith(".js"):
            win_path = path.replace("/", "\\")
            add(f"node --check {win_path}", f"JavaScript syntax check for {path}.")
        if path.startswith("tests/") and path.endswith(".js"):
            win_path = path.replace("/", "\\")
            add(f"node --check {win_path}", f"JavaScript test syntax check for {path}.")
    if any(path.startswith("templates/") or path.startswith("static/") for path in changed):
        add(python_test_command("-m unittest tests.test_frontend_route_contracts"), "Frontend route contract smoke coverage.")
    if not commands:
        add(python_test_command("-m unittest"), "Fallback full unittest suite when no focused mapping exists.")

    return {
        "version": "repo_test_command_memory_v2",
        "commands": commands,
        "notes": notes,
        "pytest_allowed": _repo_declares_pytest(),
    }


def build_recovery_packet(agent="", blocked_reason="", artifact=None, ledger=None, changed_files=None, stdout_text="", stderr_text=""):
    artifact = artifact if isinstance(artifact, dict) else {}
    ledger = ledger if isinstance(ledger, dict) else {}
    files = changed_files or artifact.get("changed_files") or []
    known = classify_known_failures(
        blocked_reason,
        artifact.get("summary", ""),
        artifact.get("stderr_tail", ""),
        artifact.get("stdout_tail", ""),
        stdout_text,
        stderr_text,
        " ".join(str(item) for item in artifact.get("errors", []) or []),
        " ".join(str(item) for item in artifact.get("bugs", []) or []),
    )
    recommended = []
    for item in known:
        recommended.extend(item.get("recovery_steps", []))
    if not recommended:
        recommended = [
            "Inspect the blocked artifact and unresolved blockers.",
            "Rerun from the smallest responsible stage instead of restarting the entire mission.",
            "Run the focused commands from repo test command memory before owner review.",
        ]
    return {
        "version": "charlie_recovery_packet_v2",
        "agent": str(agent or artifact.get("agent") or "").strip(),
        "blocked_reason": str(blocked_reason or artifact.get("summary") or "").strip(),
        "known_failures": known,
        "recommended_recovery_steps": _dedupe(recommended),
        "preferred_test_commands": repo_test_command_memory(files),
        "rerun_from_stage": _rerun_stage(agent, artifact, ledger),
        "owner_safe": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def score_mission_quality(mission=None, review_packet=None, agent_execution=None):
    mission = mission if isinstance(mission, dict) else {}
    packet = review_packet if isinstance(review_packet, dict) else {}
    execution = agent_execution if isinstance(agent_execution, dict) else packet.get("agent_execution", {})
    if not isinstance(execution, dict):
        execution = {}
    components = {}
    components["workflow"] = _score_bool(bool(execution.get("stages") or mission.get("agent_workflow")), 12)
    components["review_board"] = _score_bool(bool(packet.get("review_board") or packet.get("quality_gates")), 12)
    components["tests"] = _score_list(packet.get("test_evidence"), 18)
    components["pr_or_diff"] = _score_bool(bool(packet.get("pr_url") or (packet.get("links") or {}).get("pr") or packet.get("changed_files")), 12)
    visual = packet.get("visual_review") if isinstance(packet.get("visual_review"), dict) else {}
    local = packet.get("local_preview") if isinstance(packet.get("local_preview"), dict) else {}
    components["owner_visual_evidence"] = _score_bool(bool(visual.get("screenshots") or visual.get("media") or local.get("url")), 12)
    components["vault_brain"] = _score_bool(bool(packet.get("brain_guard") or packet.get("normalized_vault_writes") or _artifact_vault_sources(packet)), 12)
    components["recovery_hygiene"] = _score_bool(bool(packet.get("recovery_packet") or packet.get("partial_recovery") or packet.get("backflow_events") is not None), 10)
    components["unresolved_blockers"] = 0 if packet.get("unresolved_blockers") else 12
    score = max(0, min(100, sum(components.values())))
    blockers = []
    if not packet.get("test_evidence"):
        blockers.append("Review packet has no test evidence.")
    if packet.get("review_status") == "agent_blocked" or mission.get("status") == "blocked":
        blockers.append("Mission is blocked and requires recovery before final approval.")
    if packet.get("unresolved_blockers"):
        blockers.append("Unresolved blockers remain in the review packet.")
    return {
        "version": "charlie_mission_quality_score_v1",
        "score": score,
        "grade": _grade(score),
        "components": components,
        "blockers": blockers,
        "known_failures": classify_known_failures(str(packet), str(execution)),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _repo_declares_pytest():
    for name in ("requirements.txt", "requirements-dev.txt", "pyproject.toml", "package.json"):
        path = REPO_ROOT / name
        if path.exists() and "pytest" in path.read_text(encoding="utf-8", errors="ignore").lower():
            return True
    return False


def _rerun_stage(agent, artifact, ledger):
    target = str((artifact or {}).get("return_to_stage") or "").strip()
    if target:
        return target
    backflows = ledger.get("backflow_events") if isinstance(ledger.get("backflow_events"), list) else []
    if backflows:
        last = backflows[-1] if isinstance(backflows[-1], dict) else {}
        if last.get("to_agent"):
            return str(last["to_agent"])
    clean = str(agent or "").strip().lower()
    if clean in {"reviewer", "evidence_reviewer", "security_reviewer", "product_reviewer"}:
        return "builder"
    return clean or "planner"


def _score_bool(value, points):
    return int(points) if value else 0


def _score_list(value, points):
    return int(points) if isinstance(value, list) and any(str(item).strip() for item in value) else 0


def _artifact_vault_sources(packet):
    artifacts = packet.get("agent_artifacts") if isinstance(packet.get("agent_artifacts"), dict) else {}
    for artifact in artifacts.values():
        if isinstance(artifact, dict) and artifact.get("vault_sources_used"):
            return True
    return False


def _grade(score):
    if score >= 96:
        return "release_confident"
    if score >= 88:
        return "supervised_ready"
    if score >= 75:
        return "needs_owner_review"
    if score >= 60:
        return "needs_recovery"
    return "blocked_or_incomplete"


def _dedupe(values):
    seen = set()
    result = []
    for value in values:
        text = str(value or "").strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            result.append(text)
    return result
