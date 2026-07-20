import base64
import hashlib
import json
import html
import os
import re
import shutil
import signal
import subprocess
import time
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib import request as url_request
from urllib.parse import urlparse
from urllib.error import URLError
from datetime import datetime, timezone
from pathlib import Path

from modules.charlie import runtime_path_root, vault_store
from modules.charlie.mission_store import (
    AGENT_SEQUENCE,
    AGENT_STAGE_MAP,
    agent_sequence_for_mission,
    all_agent_names,
    get_mission,
    list_missions,
    record_mission,
    consume_final_agent_artifact,
    finalize_owner_review_transaction,
    transition_mission_review_state,
    update_mission_status,
    update_mission_vault,
    update_mission_workflow_step,
)
from modules.charlie.runner_control import (
    emergency_process_cleanup_disabled,
    record_emergency_cleanup_refusal,
    runner_status,
    write_runner_heartbeat,
)
from modules.charlie.process_ownership import inspect_process, make_ownership_record, process_termination_enabled, validate_termination
from modules.charlie.environment import env_value
from modules.charlie.process_policy import background_process_kwargs, background_run_kwargs
from modules.charlie.concurrency_control import ReleaseCoordinator, build_admission, declared_source_files, release_file_lease
from modules.charlie.core_workflow import (
    AGENT_DOCTRINE_PATHS,
    build_handoff_report as build_core_handoff_report,
    build_review_board_packet,
    evaluate_core_readiness,
    explicit_non_ui_requested,
)
from modules.charlie.model_registry import choose_agent_model
from modules.charlie.anthropic_provider import run_anthropic_prompt
from modules.charlie.mission_memory import (
    build_memory_event,
    final_artifact_contract_packet,
    memory_patch_from_event,
    memory_prompt_context,
    mission_memory_from_metadata,
    partial_recovery_contract_packet,
)
from modules.charlie.mission_quality import (
    build_recovery_packet,
    repo_test_command_memory,
    score_mission_quality,
)
from modules.charlie.mission_governance import (
    build_followup_missions,
    analyze_pre_builder_scope,
    build_scope_child_missions,
    ensure_acceptance_matrix,
    evaluate_quality_failure,
    update_acceptance_matrix,
)
from modules.charlie.block_recovery import classify_block, normalize_findings
from modules.charlie.evidence_reconciliation import (
    bind_artifact_to_candidate,
    build_candidate_manifest,
    resolve_effective_agent_results,
)
from modules.charlie.pr_reconciliation import PASSING_CHECK_CONCLUSIONS, mission_pr_reference, query_pr_state
from modules.charlie.runner_preflight import runner_environment_preflight
from modules.charlie.source_map import (
    implementation_source_packet,
    validate_implementation_inspection,
)
from modules.charlie.vault_retrieval import (
    evaluate_vault_source_coverage,
    owner_preference_packet,
    retrieve_vault_sources,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = runtime_path_root(REPO_ROOT)
EXECUTION_DIR = RUNTIME_ROOT / ".charlie_runner" / "executions"
REVIEW_MEDIA_DIR = RUNTIME_ROOT / ".charlie_runner" / "review_media"
LEGACY_REVIEW_MEDIA_DIR = RUNTIME_ROOT / ".charlie_runner" / "review-media"
MISSION_MEDIA_DIR = RUNTIME_ROOT / ".charlie_runner" / "mission_media"
REVIEW_MEDIA_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm"}
INLINE_IMAGE_DATA_URL_RE = re.compile(r"^data:image/(?P<kind>png|jpe?g|webp|gif);base64,(?P<data>[A-Za-z0-9+/=\s]+)$", re.IGNORECASE)
DEFAULT_TIMEOUT_SECONDS = 3600
FINAL_ARTIFACT_GRACE_SECONDS = 20
NO_FINAL_ARTIFACT_TIMEOUT_SECONDS = 1200
NO_FINAL_ARTIFACT_WARNING_SECONDS = 600
POLL_SECONDS = 5
AGENT_RUNNER_VERSION = "charlie_agent_runner_v2"
READ_ONLY_PARALLEL_AGENTS = {
    "idea_expander",
    "concept_strategist",
    "product_architect",
    "visual_reference_interpreter",
    "creative_ui_designer",
    "ux_interaction_designer",
    "technical_architect",
    "source_mapper",
    "business_model_agent",
    "risk_agent",
}
AGENT_ARTIFACT_REQUIRED_KEYS = {
    "idea_expander": ["summary", "opportunity", "owner_value", "non_goals", "commands_run", "files_inspected", "vault_sources_used"],
    "product_architect": ["summary", "user_flow", "acceptance_boundaries", "risk_notes", "commands_run", "files_inspected", "vault_sources_used"],
    "visual_reference_interpreter": ["summary", "media_references_used", "layout_requirements", "visual_hierarchy", "reference_match_checklist", "commands_run", "files_inspected", "vault_sources_used"],
    "creative_ui_designer": ["summary", "ui_concept", "layout_system", "visual_direction", "design_requirements", "commands_run", "files_inspected", "vault_sources_used"],
    "ux_interaction_designer": ["summary", "primary_workflows", "owner_actions", "responsive_behavior", "interaction_requirements", "commands_run", "files_inspected", "vault_sources_used"],
    "technical_architect": ["summary", "files_to_inspect", "risk_notes", "implementation_plan", "implementation_sources_used", "commands_run", "files_inspected", "vault_sources_used"],
    "source_mapper": ["summary", "implementation_inventory", "current_sources", "legacy_sources", "tests_to_run", "implementation_sources_used", "commands_run", "files_inspected", "vault_sources_used"],
    "council_synthesis": ["summary", "build_brief", "agreements", "conflicts_resolved", "commands_run", "files_inspected", "vault_sources_used"],
    "planner": ["summary", "acceptance_criteria", "test_plan", "commands_run", "files_inspected", "vault_sources_used"],
    "architect": ["summary", "files_to_inspect", "risk_notes", "implementation_plan", "commands_run", "files_inspected", "vault_sources_used"],
    "builder": ["summary", "changed_files", "build_notes", "commands_run", "files_inspected", "vault_sources_used"],
    "frontend_design_implementer": ["summary", "changed_files", "implementation_notes", "local_preview", "media_references_used", "visual_reference_analysis", "viewport_plan", "browser_check_plan", "commands_run", "files_inspected", "vault_sources_used"],
    "tester": ["summary", "tests_run", "test_status", "commands_run", "files_inspected", "vault_sources_used"],
    "qa_red_team": ["summary", "qa_findings", "red_team_status", "risk_rating", "commands_run", "files_inspected", "vault_sources_used"],
    "product_reviewer": ["summary", "recommended_owner_decision", "commands_run", "files_inspected", "vault_sources_used"],
    "visual_qa_reviewer": ["summary", "recommended_owner_decision", "visual_acceptance_decision", "visual_review_notes", "reference_match_assessment", "media_references_used", "commands_run", "files_inspected", "vault_sources_used"],
    "business_reviewer": ["summary", "recommended_owner_decision", "commands_run", "files_inspected", "vault_sources_used"],
    "security_reviewer": ["summary", "recommended_owner_decision", "commands_run", "files_inspected", "vault_sources_used"],
    "evidence_reviewer": ["summary", "recommended_owner_decision", "commands_run", "files_inspected", "vault_sources_used"],
    "reviewer": ["summary", "recommended_owner_decision", "changed_files", "test_evidence", "commands_run", "files_inspected", "vault_sources_used"],
}
AGENT_CONFIDENCE_REQUIRED_KEYS = ["confidence", "confidence_reason"]
AGENT_CONFIDENCE_MINIMUM = 0.96
REVIEW_DECISION_AGENTS = {
    "product_reviewer",
    "business_reviewer",
    "security_reviewer",
    "evidence_reviewer",
    "visual_qa_reviewer",
    "reviewer",
    "publisher",
}
AGENT_ARTIFACT_ALLOW_EMPTY_KEYS = {
    "idea_expander": {"commands_run"},
    "product_architect": {"commands_run"},
    "source_mapper": {"legacy_sources", "commands_run"},
    "visual_reference_interpreter": {"media_references_used", "commands_run"},
    "creative_ui_designer": {"media_references_used", "commands_run"},
    "ux_interaction_designer": {"media_references_used", "commands_run"},
    "technical_architect": {"files_to_inspect", "implementation_plan", "commands_run"},
    "council_synthesis": {"commands_run"},
    "planner": {"commands_run"},
    "architect": {"files_to_inspect", "implementation_plan", "commands_run"},
    "builder": {"changed_files"},
    "frontend_design_implementer": {"changed_files", "media_references_used"},
    "tester": {"media_references_used"},
    "qa_red_team": {"qa_findings", "commands_run"},
    "visual_qa_reviewer": {"media_references_used"},
    "product_reviewer": {"commands_run"},
    "business_reviewer": {"commands_run"},
    "security_reviewer": {"commands_run"},
    "evidence_reviewer": {"commands_run"},
    "reviewer": {"changed_files", "media_references_used"},
}
AGENT_NO_PROGRESS_TIMEOUT_SECONDS = 1800
AGENT_BACKFLOW_LIMIT = 3
HARD_LOOP_REPEAT_LIMIT = 2
AGENT_RELEASE_VERIFY_ATTEMPTS = 12
AGENT_RELEASE_VERIFY_INTERVAL_SECONDS = 10
VAULT_BRAIN_ROOT = REPO_ROOT / "docs" / "09-vault-brain"
VAULT_CONTEXT_CHAR_BUDGET = 12000
VAULT_REQUIRED_BASE_DOCS = [
    "docs/09-vault-brain/INDEX.md",
    "docs/09-vault-brain/00-governance/SOURCE_OF_TRUTH_RULES.md",
    "docs/09-vault-brain/00-governance/UPDATE_RULES.md",
    "docs/09-vault-brain/00-governance/BRAIN_GUARD.md",
    "docs/09-vault-brain/01-identity/SYSTEM_HIERARCHY.md",
    "docs/09-vault-brain/01-identity/CHARLIE.md",
    "docs/09-vault-brain/01-identity/CHARLIE_CORE.md",
    "docs/09-vault-brain/02-agents/AGENT_REGISTRY.md",
    "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md",
    "docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md",
    "docs/09-vault-brain/07-standards/TESTING_STANDARD.md",
]
VAULT_CONTEXT_BY_TEMPLATE = {
    "software_build": [
        "docs/09-vault-brain/05-playbooks/FEATURE_BUILD.md",
        "docs/09-vault-brain/07-standards/DEPLOYMENT_STANDARD.md",
        "docs/09-vault-brain/07-standards/SECURITY_AND_SECRETS_STANDARD.md",
    ],
    "system_improvement": [
        "docs/09-vault-brain/05-playbooks/AGENT_BUILD.md",
        "docs/09-vault-brain/05-playbooks/LIVE_OPERATIONS_FIX.md",
        "docs/09-vault-brain/07-standards/DEPLOYMENT_STANDARD.md",
    ],
    "business_plan": [
        "docs/09-vault-brain/03-business/README.md",
        "docs/09-vault-brain/05-playbooks/INCOME_STREAM.md",
        "docs/09-vault-brain/08-business-rules/LEGAL_AND_POPIA_REVIEW.md",
    ],
    "content_engine": [
        "docs/09-vault-brain/03-business/BEACON_MARKETING.md",
        "docs/09-vault-brain/05-playbooks/MARKETING_CAMPAIGN.md",
        "docs/09-vault-brain/08-business-rules/MARKETING_RULES.md",
        "docs/09-vault-brain/08-business-rules/MEDIA_PRIVACY_RULES.md",
    ],
    "automation_workflow": [
        "docs/09-vault-brain/04-workflows/N8N_WORKFLOW_SUITE.md",
        "docs/09-vault-brain/05-playbooks/LIVE_OPERATIONS_FIX.md",
        "docs/09-vault-brain/07-standards/SECURITY_AND_SECRETS_STANDARD.md",
    ],
    "income_stream": [
        "docs/09-vault-brain/03-business/MEAT_SALES.md",
        "docs/09-vault-brain/03-business/LIVE_PIG_SALES.md",
        "docs/09-vault-brain/03-business/AMADEUS_PRIVATE_TRANSFERS.md",
        "docs/09-vault-brain/05-playbooks/INCOME_STREAM.md",
        "docs/09-vault-brain/08-business-rules/MEAT_SALES_RULES.md",
        "docs/09-vault-brain/08-business-rules/PAYMENT_RULES.md",
    ],
}
VAULT_CONTEXT_BY_KEYWORD = {
    "bulk weight": ["docs/09-vault-brain/06-data/FARM_DATA_MODEL.md", "docs/09-vault-brain/08-business-rules/FARM_RULES.md"],
    "weight": ["docs/09-vault-brain/06-data/FARM_DATA_MODEL.md", "docs/09-vault-brain/08-business-rules/FARM_RULES.md"],
    "pig": ["docs/09-vault-brain/06-data/FARM_DATA_MODEL.md", "docs/09-vault-brain/08-business-rules/PIG_PURPOSE_RULES.md"],
    "order": ["docs/09-vault-brain/06-data/ORDER_DATA_MODEL.md", "docs/09-vault-brain/08-business-rules/PAYMENT_RULES.md"],
    "sam": ["docs/09-vault-brain/02-agents/sales/SAM.md", "docs/09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md"],
    "beacon": ["docs/09-vault-brain/02-agents/marketing/BEACON.md", "docs/09-vault-brain/03-business/BEACON_MARKETING.md"],
    "fred": ["docs/09-vault-brain/02-agents/transport/FRED.md", "docs/09-vault-brain/03-business/AMADEUS_PRIVATE_TRANSFERS.md"],
    "dashboard": ["docs/09-vault-brain/07-standards/UI_DASHBOARD_STANDARD.md", "docs/09-vault-brain/09-examples/GOLD_STANDARD_DASHBOARD.md"],
    "supabase": ["docs/09-vault-brain/06-data/SUPABASE_CONTRACTS.md", "docs/09-vault-brain/05-playbooks/DATA_MIGRATION.md"],
    "n8n": ["docs/09-vault-brain/04-workflows/N8N_WORKFLOW_SUITE.md"],
}
VAULT_SENSITIVE_PATH_PREFIXES = (
    "modules/charlie/",
    "scripts/charlie_",
    "docs/09-vault-brain/02-agents/",
    "docs/09-vault-brain/04-workflows/",
)


def prepare_codex_execution(mission_id="", status="in_progress", output_dir=None, database_url=None, connect_factory=None):
    mission, status_code, error = _load_execution_mission(
        mission_id=mission_id,
        status=status,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status_code >= 400:
        return error, status_code

    mission = _ensure_execution_governance(
        mission,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    decomposition = _pause_decomposed_parent(
        mission,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if decomposition:
        return decomposition, 200

    output_dir = Path(output_dir or EXECUTION_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    execution_id = _execution_id(mission["mission_id"])
    prompt = build_codex_execution_prompt(mission)
    prompt_path = output_dir / f"{execution_id}.prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    return {
        "success": True,
        "status": "execution_prepared",
        "mission_id": mission["mission_id"],
        "title": mission.get("title", ""),
        "execution_id": execution_id,
        "prompt_path": str(prompt_path),
        "execute_command": f"codex exec --cd {REPO_ROOT} --sandbox workspace-write -",
        "will_execute_codex": False,
    }, 200


def run_codex_execution_bridge(
    mission_id="",
    status="in_progress",
    execute_codex=False,
    output_dir=None,
    timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
    database_url=None,
    connect_factory=None,
    codex_command=None,
    run_subprocess=None,
):
    prepared, status_code = prepare_codex_execution(
        mission_id=mission_id,
        status=status,
        output_dir=output_dir,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status_code >= 400:
        return prepared, status_code
    if not execute_codex:
        prepared["status"] = "execution_dry_run"
        return prepared, 200

    mission_id = prepared["mission_id"]
    prompt_path = Path(prepared["prompt_path"])
    output_dir = prompt_path.parent
    execution_id = prepared["execution_id"]
    stdout_path = output_dir / f"{execution_id}.stdout.txt"
    stderr_path = output_dir / f"{execution_id}.stderr.txt"
    final_path = output_dir / f"{execution_id}.final.md"

    _record_execution_stage(mission_id, "planner", "active", "Local Codex execution bridge started.")
    command = codex_command or [
        _codex_executable(),
        "exec",
        "--cd",
        str(REPO_ROOT),
        "--sandbox",
        "workspace-write",
        "--output-last-message",
        str(final_path),
        "-",
    ]
    started_at = datetime.now(timezone.utc).isoformat()
    runner = run_subprocess or _run_agent_model_process
    completed = runner(
        command,
        input=prompt_path.read_text(encoding="utf-8"),
        cwd=str(REPO_ROOT),
        timeout_seconds=int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS),
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        final_path=final_path,
        mission_id=mission_id,
    )
    _write_process_text(stdout_path, completed.stdout or "")
    _write_process_text(stderr_path, completed.stderr or "")
    final_message = _read_text(final_path) or (completed.stdout or "").strip()
    if final_message and not _read_text(final_path):
        _write_process_text(final_path, final_message)

    if completed.returncode != 0:
        if completed.returncode == 124 and not _read_text(final_path):
            return block_codex_execution_without_final_artifact(
                mission_id,
                execution_id=execution_id,
                prompt_path=prompt_path,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                final_path=final_path,
                started_at=started_at,
                returncode=completed.returncode,
                database_url=database_url,
                connect_factory=connect_factory,
            )
        update_mission_status(
            mission_id,
            "blocked",
            owner_decision="Local Codex execution bridge failed.",
            event_type="status_changed",
            notes="Local Codex execution bridge returned a non-zero exit code.",
            metadata={
                "script": "scripts/charlie_codex_execution_bridge.py",
                "returncode": completed.returncode,
                "stderr_path": str(stderr_path),
            },
            database_url=database_url,
            connect_factory=connect_factory,
        )
        return {
            "success": False,
            "status": "codex_execution_failed",
            "mission_id": mission_id,
            "returncode": completed.returncode,
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
        }, 502

    return complete_codex_execution_from_artifact(
        mission_id,
        execution_id=execution_id,
        prompt_path=prompt_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        final_path=final_path,
        started_at=started_at,
        database_url=database_url,
        connect_factory=connect_factory,
    )


def run_agent_execution_bridge_v2(
    mission_id="",
    status="in_progress",
    execute_codex=False,
    output_dir=None,
    timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
    database_url=None,
    connect_factory=None,
    codex_command=None,
    run_subprocess=None,
    artifact_consumer=None,
):
    mission, status_code, error = _load_execution_mission(
        mission_id=mission_id,
        status=status,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status_code >= 400:
        return error, status_code

    mission = _ensure_execution_governance(
        mission,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    decomposition = _pause_decomposed_parent(
        mission,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if decomposition:
        return decomposition, 200

    output_dir = Path(output_dir or EXECUTION_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    execution_id = _execution_id(mission["mission_id"])
    started_at = datetime.now(timezone.utc).isoformat()
    ledger = _agent_execution_ledger(mission, execution_id, started_at)
    agent_sequence = _mission_agent_sequence(mission)
    start_agent = _execution_start_agent(mission, agent_sequence)
    artifacts = _existing_agent_artifacts_for_rerun(mission, start_agent, agent_sequence)
    if start_agent != agent_sequence[0]:
        ledger["rerun_from_stage"] = start_agent
        ledger["preserved_upstream_artifacts"] = sorted(artifacts.keys())

    if not execute_codex:
        packet_path = output_dir / f"{execution_id}.agent-ledger.json"
        packet_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        return {
            "success": True,
            "status": "agent_execution_dry_run",
            "mission_id": mission["mission_id"],
            "execution_id": execution_id,
            "agent_runner_version": AGENT_RUNNER_VERSION,
            "ledger_path": str(packet_path),
            "will_execute_codex": False,
        }, 200

    runner = run_subprocess or _run_agent_model_process
    command_base = codex_command or [
        _codex_executable(),
        "exec",
        "--cd",
        str(REPO_ROOT),
        "--sandbox",
        "workspace-write",
    ]

    agent_queue, preserved_agents = _targeted_agent_queue(mission, start_agent, agent_sequence)
    if preserved_agents:
        agent_queue = [agent for agent in agent_queue if agent == start_agent or agent not in preserved_agents]
        ledger["targeted_invalidation"] = {
            "target_agent": start_agent,
            "preserved_agents": sorted(preserved_agents),
            "skipped_replay_agents": sorted(set(agent_sequence).intersection(preserved_agents) - {start_agent}),
        }
    stage_attempts = {agent: 0 for agent in agent_sequence}
    backflow_counts = {agent: 0 for agent in agent_sequence}
    contract_retry_used = {}
    contract_reminder_pending = set()
    parallel_agents = _parallel_read_only_prefix(agent_queue)
    if parallel_agents:
        parallel_result = _run_parallel_read_only_agents(
            mission=mission,
            execution_id=execution_id,
            ledger=ledger,
            artifacts=artifacts,
            agents=parallel_agents,
            output_dir=output_dir,
            command_base=command_base,
            runner=runner,
            timeout_seconds=timeout_seconds,
            stage_attempts=stage_attempts,
            database_url=database_url,
            connect_factory=connect_factory,
        )
        if parallel_result.get("blocked"):
            return parallel_result["result"], parallel_result["status_code"]
        artifacts.update(parallel_result.get("artifacts", {}))
        agent_queue = [agent for agent in agent_queue if agent not in set(parallel_agents)]
        ledger["parallel_planning_execution"] = parallel_result.get("parallel_execution", {})
        _write_agent_ledger(output_dir, execution_id, ledger)
    while agent_queue:
        agent = agent_queue.pop(0)
        stage_attempts[agent] = int(stage_attempts.get(agent, 0)) + 1
        _record_execution_stage(
            mission["mission_id"],
            agent,
            "active",
            f"CHARLIE Agent Runner v2 started {agent} attempt {stage_attempts[agent]}.",
            database_url=database_url,
            connect_factory=connect_factory,
        )
        stage_paths = _agent_stage_paths(output_dir, execution_id, agent, attempt=stage_attempts[agent])
        concurrency_admission = None
        if agent == "builder":
            concurrency_admission = _builder_concurrency_admission(mission, artifacts, execution_id)
            if not concurrency_admission.get("allowed"):
                stage_started = datetime.now(timezone.utc).isoformat()
                return _block_agent_stage(
                    mission["mission_id"],
                    execution_id,
                    ledger,
                    agent,
                    stage_paths,
                    SimpleNamespace(returncode=78, stdout="", stderr="Builder concurrency admission refused."),
                    stage_started,
                    blocked_reason=(
                        "Builder concurrency admission refused before model execution: "
                        f"{concurrency_admission.get('status') or 'unknown_status'}."
                    ),
                    artifact={
                        "summary": "Builder did not start because workspace/source ownership was not safe.",
                        "errors": [str(concurrency_admission.get("status") or "concurrency_admission_failed")],
                        "concurrency_admission": concurrency_admission,
                        "next_action": "Resolve the workspace overlap or declare a bounded source scope, then resume from Builder.",
                    },
                    artifacts=artifacts,
                    database_url=database_url,
                    connect_factory=connect_factory,
                )
        write_runner_heartbeat({
            "status": "agent_stage_preparing",
            "mission_id": mission["mission_id"],
            "agent_runner_version": AGENT_RUNNER_VERSION,
            "current_agent": agent,
            "current_action": f"Preparing {agent} prompt for attempt {stage_attempts[agent]}",
            "execution_artifact": str(stage_paths["final_path"]),
            "agent_ledger_path": str(output_dir / f"{execution_id}.agent-ledger.json"),
        })
        prompt = build_agent_stage_prompt(mission, agent, artifacts, ledger)
        if agent in contract_reminder_pending:
            contract_reminder_pending.discard(agent)
            prompt = _append_contract_retry_reminder(prompt)
        stage_paths["prompt_path"].write_text(prompt, encoding="utf-8")
        model_assignment = choose_agent_model(
            agent=agent,
            mission_type=mission.get("mission_type", ""),
            risk_level="high" if _ui_quality_contract_for_mission(mission).get("ui_related") else "medium",
        )
        if _strict_agent_model_routing_required() and not model_assignment.get("runtime_model"):
            stage_started = datetime.now(timezone.utc).isoformat()
            return _block_agent_stage(
                mission["mission_id"],
                execution_id,
                ledger,
                agent,
                stage_paths,
                SimpleNamespace(returncode=78, stdout="", stderr="Per-agent runtime model is not configured."),
                stage_started,
                blocked_reason=f"Strict per-agent model routing is enabled, but {agent} has no runtime model configured.",
                artifact={
                    "summary": "Per-agent model routing is required before this agent can run.",
                    "errors": [f"Missing CHARLIE_AGENT_MODEL_{agent.upper().replace('-', '_')} or CHARLIE_MODEL_<REGISTRY_KEY> env."],
                    "model_assignment": model_assignment,
                    "next_action": "Configure the per-agent or registry model env var, then rerun the mission from this stage.",
                },
                artifacts=artifacts,
                database_url=database_url,
                connect_factory=connect_factory,
            )
        command = [
            *_agent_command_base(command_base, model_assignment),
            "--output-last-message",
            str(stage_paths["final_path"]),
            "-",
        ]
        stage_started = datetime.now(timezone.utc).isoformat()
        _append_ledger_stage(
            ledger,
            agent,
            "running",
            stage_started,
            stage_paths,
            current_action=f"{agent} running attempt {stage_attempts[agent]}",
            command=command,
            attempt=stage_attempts[agent],
        )
        _write_agent_ledger(output_dir, execution_id, ledger)
        write_runner_heartbeat({
            "status": "agent_stage_running",
            "mission_id": mission["mission_id"],
            "agent_runner_version": AGENT_RUNNER_VERSION,
            "current_agent": agent,
            "current_action": f"{agent} running attempt {stage_attempts[agent]}",
            "execution_artifact": str(stage_paths["final_path"]),
            "agent_ledger_path": str(output_dir / f"{execution_id}.agent-ledger.json"),
        })
        try:
            completed = runner(
                command,
                input=prompt,
                cwd=str(REPO_ROOT),
                timeout_seconds=min(int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS), AGENT_NO_PROGRESS_TIMEOUT_SECONDS),
                stdout_path=stage_paths["stdout_path"],
                stderr_path=stage_paths["stderr_path"],
                final_path=stage_paths["final_path"],
                mission_id=mission["mission_id"],
                model_assignment=model_assignment,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            completed = _completed_process_from_stage_exception(command, exc, stage_paths)
        _write_process_text(stage_paths["stdout_path"], completed.stdout or "")
        _write_process_text(stage_paths["stderr_path"], completed.stderr or "")
        final_message = _read_text(stage_paths["final_path"]) or (completed.stdout or "").strip()
        if final_message and not _read_text(stage_paths["final_path"]):
            _write_process_text(stage_paths["final_path"], final_message)

        final_text = _read_text(stage_paths["final_path"])
        if completed.returncode == 0 and not final_text:
            if _retry_agent_contract_failure(
                ledger,
                agent_queue,
                contract_retry_used,
                contract_reminder_pending,
                agent,
                stage_attempts[agent],
                "missing_final",
                stage_started,
                stage_paths,
                output_dir,
                execution_id,
            ):
                continue
            completed.contract_failure_reason = "Agent completed without a final artifact after contract retry."
        if completed.returncode != 0 or not final_text:
            return _block_agent_stage(
                mission["mission_id"],
                execution_id,
                ledger,
                agent,
                stage_paths,
                completed,
                stage_started,
                blocked_reason=getattr(completed, "contract_failure_reason", "Agent did not produce a valid final artifact."),
                database_url=database_url,
                connect_factory=connect_factory,
            )

        parse_failed = not bool(_extract_json_object(final_text))
        artifact = _agent_artifact_from_final(agent, final_text)
        artifact = _inherit_pr_reference(agent, artifact, artifacts)
        ui_contract = _ui_quality_contract_for_mission(mission)
        if ui_contract.get("ui_related"):
            artifact["ui_quality_contract"] = ui_contract
        implementation_context = implementation_source_packet(mission)
        if implementation_context.get("matched_sections"):
            artifact["implementation_source_map"] = implementation_context
        artifact.update({
            "agent": agent,
            "artifact_path": str(stage_paths["final_path"]),
            "stdout_path": str(stage_paths["stdout_path"]),
            "stderr_path": str(stage_paths["stderr_path"]),
            "stdout_tail": _tail_text(completed.stdout or _read_text(stage_paths["stdout_path"]), 1200),
            "stderr_tail": _tail_text(completed.stderr or _read_text(stage_paths["stderr_path"]), 1200),
            "attempt": stage_attempts[agent],
            "model_assignment": model_assignment,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        if concurrency_admission:
            artifact["concurrency_admission"] = concurrency_admission
            artifact["concurrency_lease_release"] = _release_builder_concurrency_admission(concurrency_admission)
        if agent == "publisher":
            artifact = _bind_publisher_revision(artifact)
        validation = _validate_agent_artifact(agent, artifact)
        if not validation["valid"]:
            retry_reason = "malformed_json" if parse_failed else "missing_keys"
            if _retry_agent_contract_failure(
                ledger,
                agent_queue,
                contract_retry_used,
                contract_reminder_pending,
                agent,
                stage_attempts[agent],
                retry_reason,
                stage_started,
                stage_paths,
                output_dir,
                execution_id,
                missing_keys=validation["missing_keys"],
                artifact=artifact,
            ):
                continue
            artifact = {
                **artifact,
                "contract_retry_exhausted": True,
                "first_attempt_artifact_path": _first_contract_retry_artifact_path(ledger, agent),
            }
            return _block_agent_stage(
                mission["mission_id"],
                execution_id,
                ledger,
                agent,
                stage_paths,
                completed,
                stage_started,
                blocked_reason=f"Agent artifact missing required keys after contract retry: {', '.join(validation['missing_keys'])}.",
                artifact=artifact,
                artifacts=artifacts,
                database_url=database_url,
                connect_factory=connect_factory,
            )
        if agent == "builder":
            artifact = _auto_package_builder_changes(mission, artifact)
            packaging = artifact.get("git_packaging") if isinstance(artifact.get("git_packaging"), dict) else {}
            if _builder_packaging_is_terminal(packaging):
                packaging_status = str(packaging.get("status") or "builder_packaging_failed").strip()
                return _block_agent_stage(
                    mission["mission_id"],
                    execution_id,
                    ledger,
                    agent,
                    stage_paths,
                    completed,
                    stage_started,
                    blocked_reason=(
                        f"Builder packaging stopped at {packaging_status}; downstream test and review stages were not run "
                        "against an unreviewable branch."
                    ),
                    artifact={
                        **artifact,
                        "next_action": "Repair the Builder branch/commit/PR packaging, then resume from Builder.",
                        "return_to_stage": "builder",
                    },
                    artifacts=artifacts,
                    database_url=database_url,
                    connect_factory=connect_factory,
                )
        manifest_artifacts = {**artifacts, agent: artifact}
        candidate_manifest = build_candidate_manifest(
            mission,
            manifest_artifacts,
            source_commit=_release_candidate_revision_sha(mission, manifest_artifacts),
        )
        artifact = bind_artifact_to_candidate(
            artifact,
            agent,
            execution_id,
            stage_attempts[agent],
            candidate_manifest,
            previous_artifact=artifacts.get(agent),
        )
        quality = _agent_quality_gate(agent, artifact)
        if not quality["passed"]:
            governance_decision = evaluate_quality_failure(mission, agent, artifact, quality)
            artifact["mission_governance_decision"] = governance_decision
            if governance_decision["route"] == "continue_with_followups":
                followups = _record_discovered_followups(
                    mission,
                    agent,
                    governance_decision,
                    database_url=database_url,
                    connect_factory=connect_factory,
                )
                artifact["discovered_followup_missions"] = followups
                quality = {
                    "passed": True,
                    "reason": governance_decision["reason"],
                    "bounded_followup": True,
                    "original_quality_gate": quality,
                }
            elif governance_decision["route"] == "owner_block":
                return _block_agent_stage(
                    mission["mission_id"],
                    execution_id,
                    ledger,
                    agent,
                    stage_paths,
                    completed,
                    stage_started,
                    blocked_reason=governance_decision["reason"],
                    artifact={**artifact, "quality_gate": quality},
                    artifacts={**artifacts, agent: {**artifact, "quality_gate": quality}},
                    database_url=database_url,
                    connect_factory=connect_factory,
                )
        if not quality["passed"]:
            backflow_target = _resolve_agent_backflow_target(
                _agent_backflow_target(agent, artifact, quality),
                agent_sequence,
            )
            if backflow_target and backflow_counts.get(backflow_target, 0) < AGENT_BACKFLOW_LIMIT:
                blocker_fingerprint = _backflow_fingerprint(agent, backflow_target, quality["reason"], artifact)
                prior_same_loop = (
                    _backflow_fingerprint_count(ledger, blocker_fingerprint)
                    + _durable_backflow_fingerprint_count(mission, blocker_fingerprint)
                )
                if prior_same_loop >= HARD_LOOP_REPEAT_LIMIT - 1:
                    backflow_counts[backflow_target] = backflow_counts.get(backflow_target, 0) + 1
                    _append_backflow_event(
                        ledger,
                        from_agent=agent,
                        to_agent=backflow_target,
                        reason=quality["reason"],
                        attempt=backflow_counts[backflow_target],
                        artifact=artifact,
                        quality=quality,
                        fingerprint=blocker_fingerprint,
                        loop_detected=True,
                    )
                    return _block_agent_stage(
                        mission["mission_id"],
                        execution_id,
                        ledger,
                        agent,
                        stage_paths,
                        completed,
                        stage_started,
                        blocked_reason=f"Repeated same blocker loop detected for {agent} -> {backflow_target}: {quality['reason']}",
                        artifact={
                            **artifact,
                            "quality_gate": quality,
                            "loop_fingerprint": blocker_fingerprint,
                            "next_action": _loop_recovery_next_action(agent, backflow_target, quality["reason"], artifact),
                        },
                        artifacts={**artifacts, agent: {**artifact, "quality_gate": quality}},
                        database_url=database_url,
                        connect_factory=connect_factory,
                    )
                backflow_counts[backflow_target] = backflow_counts.get(backflow_target, 0) + 1
                _append_backflow_event(
                    ledger,
                    from_agent=agent,
                    to_agent=backflow_target,
                    reason=quality["reason"],
                    attempt=backflow_counts[backflow_target],
                    artifact=artifact,
                    quality=quality,
                    fingerprint=blocker_fingerprint,
                )
                _record_mission_memory_event(
                    mission,
                    build_memory_event(
                        agent,
                        "agent_backflow",
                        summary=f"{agent} sent work back to {backflow_target}: {quality['reason']}",
                        attempt=stage_attempts[agent],
                        artifact=artifact,
                        quality_gate=quality,
                        metadata={
                            "backflow_fingerprint": blocker_fingerprint,
                            "backflow_from": agent,
                            "backflow_to": backflow_target,
                            "finding_family": _primary_finding_family(artifact),
                            "revision_sha": _release_candidate_revision_sha(mission, artifacts),
                        },
                    ),
                    database_url=database_url,
                    connect_factory=connect_factory,
                )
                artifacts[agent] = artifact
                artifacts = _discard_downstream_artifacts(artifacts, backflow_target, agent_sequence)
                agent_queue = _agent_queue_from(backflow_target, agent_sequence)
                _write_agent_ledger(output_dir, execution_id, ledger)
                write_runner_heartbeat({
                    "status": "agent_backflow",
                    "mission_id": mission["mission_id"],
                    "agent_runner_version": AGENT_RUNNER_VERSION,
                    "current_agent": backflow_target,
                    "current_action": f"{agent} sent work back to {backflow_target}: {quality['reason']}",
                    "unresolved_blockers": ledger.get("unresolved_blockers", []),
                    "execution_artifact": str(stage_paths["final_path"]),
                    "agent_ledger_path": str(output_dir / f"{execution_id}.agent-ledger.json"),
                })
                continue
            return _block_agent_stage(
                mission["mission_id"],
                execution_id,
                ledger,
                agent,
                stage_paths,
                completed,
                stage_started,
                blocked_reason=quality["reason"],
                artifact={**artifact, "quality_gate": quality},
                artifacts={**artifacts, agent: {**artifact, "quality_gate": quality}},
                database_url=database_url,
                connect_factory=connect_factory,
            )
        artifact["quality_gate"] = quality
        artifact_hash = hashlib.sha256(final_text.encode("utf-8")).hexdigest()
        if artifact_consumer is None:
            ingestion, ingestion_status = ({"success": False, "status": "not_configured"}, 503)
        else:
            ingestion, ingestion_status = artifact_consumer(
                mission["mission_id"], agent, execution_id, stage_attempts[agent], artifact, artifact_hash,
                database_url=database_url, connect_factory=connect_factory,
            )
        ingestion_owned_stage = ingestion_status < 400 and ingestion.get("status") in {
            "final_artifact_consumed", "final_artifact_already_consumed"
        }
        if ingestion_status >= 400 and ingestion.get("status") != "not_configured":
            return _block_agent_stage(
                mission["mission_id"], execution_id, ledger, agent, stage_paths, completed, stage_started,
                blocked_reason=f"Valid final artifact could not be consumed: {ingestion.get('status', 'unknown')}.",
                artifact={**artifact, "artifact_ingestion": ingestion}, artifacts=artifacts,
                database_url=database_url, connect_factory=connect_factory,
            )
        artifact["artifact_ingestion"] = ingestion
        _record_acceptance_progress(
            mission,
            agent,
            artifact,
            passed=True,
            database_url=database_url,
            connect_factory=connect_factory,
        )
        artifact["handoff_report"] = _build_handoff_report(mission, agent, artifact, ledger)
        artifacts[agent] = artifact
        if not ingestion_owned_stage:
            _record_mission_memory_event(
                mission,
                build_memory_event(
                    agent, "agent_complete", attempt=stage_attempts[agent], artifact=artifact, quality_gate=quality,
                ),
                database_url=database_url, connect_factory=connect_factory,
            )
        _append_ledger_stage(
            ledger,
            agent,
            "complete",
            stage_started,
            stage_paths,
            artifact=artifact,
            command=command,
            attempt=stage_attempts[agent],
        )
        _write_agent_ledger(output_dir, execution_id, ledger)
        if not ingestion_owned_stage:
            _record_execution_stage(
                mission["mission_id"], agent, "complete",
                _truncate(artifact.get("summary") or f"{agent} completed.", 1000),
                database_url=database_url, connect_factory=connect_factory,
            )

    return _complete_agent_execution_v2(
        mission,
        execution_id,
        ledger,
        artifacts,
        output_dir,
        started_at,
        database_url=database_url,
        connect_factory=connect_factory,
    )


def recover_pending_final_agent_artifact(mission_id="", database_url=None, connect_factory=None, status_loader=None):
    """Consume the final artifact named by a stale/live heartbeat before a runner restart."""
    status = (status_loader or runner_status)(include_orphans=False, include_git=False, include_ledger=False)
    heartbeat_mission = str(status.get("last_mission_id") or "").strip()
    mission_id = str(mission_id or heartbeat_mission).strip()
    if not mission_id or (heartbeat_mission and mission_id != heartbeat_mission):
        return {"success": True, "status": "no_matching_pending_final_artifact"}, 200
    path = Path(str(status.get("execution_artifact") or "").strip())
    if not path.is_absolute():
        path = REPO_ROOT / path
    final_text = _read_text(path)
    if not final_text:
        return {"success": True, "status": "no_pending_final_artifact"}, 200
    loaded, load_status = get_mission(mission_id, database_url=database_url, connect_factory=connect_factory)
    if load_status >= 400:
        return loaded, load_status
    mission = loaded.get("mission") or {}
    workflow = mission.get("agent_workflow") if isinstance(mission.get("agent_workflow"), list) else []
    agent = str(status.get("current_agent") or "").strip().lower()
    if not agent:
        agent = next((str(item.get("agent") or "").lower() for item in workflow if isinstance(item, dict) and str(item.get("status") or "").lower() != "complete"), "")
    artifact = _agent_artifact_from_final(agent, final_text)
    artifact.update({"agent": agent, "artifact_path": str(path), "recovered_after_restart": True})
    validation = _validate_agent_artifact(agent, artifact)
    if not validation["valid"]:
        return _quarantine_pending_final_artifact(
            mission, agent,
            "Recovered final artifact is invalid; missing keys: " + ", ".join(validation["missing_keys"]),
            database_url=database_url, connect_factory=connect_factory,
        )
    quality = _agent_quality_gate(agent, artifact)
    if not quality["passed"]:
        return _quarantine_pending_final_artifact(
            mission, agent, quality["reason"],
            database_url=database_url, connect_factory=connect_factory,
        )
    artifact["quality_gate"] = quality
    execution_id = str(status.get("agent_ledger", {}).get("execution_id") or path.name.split(f".{agent}.")[0] or "recovered")
    result, status_code = consume_final_agent_artifact(
        mission_id, agent, execution_id, int(artifact.get("attempt") or 1), artifact,
        hashlib.sha256(final_text.encode("utf-8")).hexdigest(),
        database_url=database_url, connect_factory=connect_factory,
    )
    if status_code == 409 and result.get("status") == "final_artifact_stage_mismatch":
        return _quarantine_pending_final_artifact(
            mission,
            agent,
            (
                f"Recovered artifact belongs to {agent}, while the durable workflow expects "
                f"{result.get('expected_agent') or 'another stage'}. The stale artifact was quarantined "
                "so it cannot be picked repeatedly."
            ),
            database_url=database_url,
            connect_factory=connect_factory,
        )
    if status_code < 400:
        write_runner_heartbeat({
            "status": result.get("status"), "mission_id": mission_id,
            "agent_runner_version": AGENT_RUNNER_VERSION, "current_agent": result.get("next_agent", ""),
            "current_action": f"Recovered and consumed {agent} final artifact.",
            "execution_artifact": str(path), "final_artifact_present": True,
        })
    return result, status_code


def _quarantine_pending_final_artifact(mission, agent, reason, *, database_url=None, connect_factory=None):
    """Block one stale mission honestly without stopping the supervised queue."""
    mission_id = str((mission or {}).get("mission_id") or "").strip()
    metadata = mission.get("metadata") if isinstance((mission or {}).get("metadata"), dict) else {}
    packet = dict(metadata.get("review_packet") or {})
    packet.update({
        "review_status": "internal_recovery_required",
        "blocked_agent": str(agent or "reviewer"),
        "blocked_reason": str(reason or "Recovered final artifact failed validation."),
        "recommended_owner_decision": "",
        "recommended_next_action": "CHARLIE will adjudicate and recover this internal artifact failure; unrelated queue work continues.",
        "block_disposition": {
            "block_class": "evidence_repair_required",
            "owner_required": False,
            "responsible_stage": str(agent or "reviewer"),
            "reason": str(reason or "Recovered final artifact failed validation."),
        },
    })
    result, status_code = transition_mission_review_state(
        mission_id, "blocked", packet, expected_status="in_progress",
        notes="Supervisor quarantined a non-passing recovered artifact instead of stopping the queue.",
        database_url=database_url, connect_factory=connect_factory,
    )
    if status_code >= 400:
        return {
            "success": False, "status": "pending_final_artifact_quarantine_failed",
            "reason": reason, "transition": result,
        }, status_code
    write_runner_heartbeat({
        "status": "pending_final_artifact_quarantined", "mission_id": "",
        "current_agent": "", "current_action": "Stale artifact quarantined; queue may continue.",
        "execution_artifact": "", "final_artifact_present": False,
    })
    return {
        "success": True, "status": "pending_final_artifact_quarantined",
        "mission_id": mission_id, "reason": reason,
    }, 200


def complete_codex_execution_from_artifact(
    mission_id,
    execution_id="",
    prompt_path=None,
    stdout_path=None,
    stderr_path=None,
    final_path=None,
    started_at="",
    database_url=None,
    connect_factory=None,
):
    mission_id = str(mission_id or "").strip()
    if not mission_id:
        return {"success": False, "status": "mission_id_required"}, 400
    artifact = _resolve_execution_artifact(
        mission_id=mission_id,
        execution_id=execution_id,
        prompt_path=prompt_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        final_path=final_path,
    )
    final_message = _read_text(artifact["final_path"])
    if not final_message:
        return {
            "success": False,
            "status": "final_execution_artifact_required",
            "mission_id": mission_id,
            "final_message_path": str(artifact["final_path"]),
        }, 409

    for agent in AGENT_SEQUENCE:
        _record_execution_stage(
            mission_id,
            agent,
            "complete",
            _agent_completion_note(agent, final_message),
            database_url=database_url,
            connect_factory=connect_factory,
        )

    changed_files = _changed_files()
    local_preview = _extract_local_preview(final_message)
    mission = {
        "mission_id": mission_id,
        "mission_type": "",
        "raw_text": final_message,
        "metadata": {},
    }
    visual_review = _build_visual_review_packet(
        mission_id=mission_id,
        mission_type=mission.get("mission_type", ""),
        changed_files=changed_files,
        local_preview=local_preview,
        final_message=final_message,
        mission=mission,
    )
    review_packet = {
        "review_packet": {
            "summary": _truncate(final_message or "Codex execution completed.", 1600),
            "findings": [
                "Local Codex execution bridge completed successfully.",
                "Codex final response is stored in the execution artifact.",
            ],
            "errors": _extract_errors(final_message),
            "bugs": [],
            "changed_files": changed_files or ["No changed files detected by git diff."],
            "test_evidence": _extract_test_evidence(final_message),
            "local_preview": local_preview,
            "visual_review": visual_review,
            "links": {"local_preview": local_preview.get("url", "")},
            "release_notes": ["Review Codex execution artifact before final approval."],
            "execution_artifacts": {
                "execution_id": artifact["execution_id"],
                "prompt_path": str(artifact["prompt_path"]),
                "stdout_path": str(artifact["stdout_path"]),
                "stderr_path": str(artifact["stderr_path"]),
                "final_message_path": str(artifact["final_path"]),
                "started_at": started_at,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            },
        }
    }
    update_mission_vault(
        mission_id,
        review_packet,
        notes="Local Codex execution bridge populated owner review packet.",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    reviewer_result, reviewer_status = update_mission_workflow_step(
        mission_id,
        "reviewer",
        step_status="complete",
        findings="Local Codex execution bridge completed and prepared owner review packet.",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if reviewer_status >= 400:
        return reviewer_result, reviewer_status
    return {
        "success": True,
        "status": "codex_execution_completed",
        "mission_id": mission_id,
        "mission_status": "pr_ready",
        "execution_id": artifact["execution_id"],
        "prompt_path": str(artifact["prompt_path"]),
        "stdout_path": str(artifact["stdout_path"]),
        "stderr_path": str(artifact["stderr_path"]),
        "final_message_path": str(artifact["final_path"]),
    }, 200


def block_codex_execution_without_final_artifact(
    mission_id,
    execution_id="",
    prompt_path=None,
    stdout_path=None,
    stderr_path=None,
    final_path=None,
    started_at="",
    returncode=124,
    database_url=None,
    connect_factory=None,
):
    mission_id = str(mission_id or "").strip()
    if not mission_id:
        return {"success": False, "status": "mission_id_required"}, 400
    artifact = _resolve_execution_artifact(
        mission_id=mission_id,
        execution_id=execution_id,
        prompt_path=prompt_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        final_path=final_path,
    )
    changed_files = _changed_files()
    stderr_text = _read_text(artifact["stderr_path"])
    stdout_text = _read_text(artifact["stdout_path"])
    partial_work = _partial_work_recovery_packet(changed_files, stdout_text, stderr_text)
    summary = (
        "Codex execution was stopped by the CHARLIE supervisor because no final artifact was produced. "
        "Local file changes were detected and are preserved for owner/developer review."
        if changed_files
        else "Codex execution was stopped by the CHARLIE supervisor because no final artifact was produced and no local file changes were detected."
    )
    review_packet = {
        "review_packet": {
            "summary": summary,
            "findings": [
                "CHARLIE supervisor detected a no-final-artifact timeout.",
                f"Changed files detected: {len(changed_files)}.",
                "This mission is blocked instead of being silently left in progress.",
            ],
            "errors": [
                "Codex did not write a final response artifact before the supervisor timeout.",
            ],
            "bugs": [],
            "changed_files": changed_files or ["No changed files detected by git diff."],
            "test_evidence": [
                "Automated mission tests were not completed because Codex did not produce a final artifact.",
            ],
            "partial_work": partial_work,
            "recommended_next_action": partial_work["recommended_next_action"],
            "local_preview": {
                "url": "",
                "command": "",
            },
            "links": {},
            "release_notes": [
                "Do not final-approve until the partial work is reviewed, tested, and a PR is created.",
            ],
            "execution_artifacts": {
                "execution_id": artifact["execution_id"],
                "prompt_path": str(artifact["prompt_path"]),
                "stdout_path": str(artifact["stdout_path"]),
                "stderr_path": str(artifact["stderr_path"]),
                "final_message_path": str(artifact["final_path"]),
                "started_at": started_at,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "returncode": returncode,
                "stdout_excerpt": _truncate(stdout_text, 1200),
                "stderr_excerpt": _truncate(stderr_text, 1200),
                "supervisor_status": "codex_no_final_artifact_timeout",
            },
        }
    }
    vault_result, vault_status = update_mission_vault(
        mission_id,
        review_packet,
        notes="CHARLIE supervisor populated blocked review packet after Codex no-final-artifact timeout.",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if vault_status >= 400:
        return vault_result, vault_status
    _record_execution_stage(
        mission_id,
        "reviewer",
        "blocked",
        "CHARLIE supervisor blocked the mission because Codex did not produce a final artifact.",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    blocked, blocked_status = update_mission_status(
        mission_id,
        "blocked",
        owner_decision="CHARLIE supervisor blocked local Codex execution: no final artifact was produced.",
        event_type="status_changed",
        notes="Codex execution timeout without final artifact; partial work preserved for review.",
        metadata={
            "script": "scripts/charlie_codex_execution_bridge.py",
            "execution_id": artifact["execution_id"],
            "returncode": returncode,
            "changed_files": changed_files,
            "supervisor_status": "codex_no_final_artifact_timeout",
            "partial_work": partial_work,
        },
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if blocked_status >= 400:
        return blocked, blocked_status
    return {
        "success": False,
        "status": "codex_no_final_artifact_timeout",
        "mission_id": mission_id,
        "mission_status": "blocked",
        "changed_files": changed_files,
        "execution_id": artifact["execution_id"],
        "prompt_path": str(artifact["prompt_path"]),
        "stdout_path": str(artifact["stdout_path"]),
        "stderr_path": str(artifact["stderr_path"]),
        "final_message_path": str(artifact["final_path"]),
        "partial_work": partial_work,
    }, 504


def _partial_work_recovery_packet(changed_files, stdout_text="", stderr_text=""):
    changed_files = [str(path) for path in (changed_files or []) if str(path or "").strip()]
    combined = f"{stdout_text or ''}\n{stderr_text or ''}"
    pr_links = sorted(set(re.findall(r"https://github\.com/[^\s)]+/pull/\d+", combined)))
    commit_refs = sorted(set(re.findall(r"\b[0-9a-f]{7,40}\b", combined)))[:12]
    recoverable = bool(changed_files or pr_links or commit_refs)
    if changed_files:
        next_action = "Review the preserved local diff, run focused tests, commit/push the recovery, then rerun or close the mission as training."
    elif pr_links or commit_refs:
        next_action = "Inspect the referenced PR/commit evidence, verify checks, then update the mission manually or rerun from a clean mission."
    else:
        next_action = "Treat as failed execution with no recoverable diff; rerun from a clean mission after checking stderr."
    return {
        "recoverable": recoverable,
        "changed_files_count": len(changed_files),
        "changed_files": changed_files[:40],
        "pr_links": pr_links[:10],
        "commit_refs": commit_refs,
        "preferred_test_commands": repo_test_command_memory(changed_files),
        "known_failure_recovery": build_recovery_packet(
            agent="codex_supervisor",
            blocked_reason="No final artifact or partial execution recovery required.",
            changed_files=changed_files,
            stdout_text=stdout_text,
            stderr_text=stderr_text,
        ),
        "recommended_next_action": next_action,
        "supervisor_note": "No-final-artifact timeout is a blocking quality gate; this packet preserves recovery evidence without approving the mission.",
    }


def prepare_release_execution(mission_id="", output_dir=None, database_url=None, connect_factory=None):
    mission, status_code, error = _load_release_mission(
        mission_id=mission_id,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status_code >= 400:
        return error, status_code
    cleanup_result = process_visual_review_cleanup_intent(
        mission_id=mission["mission_id"],
        mission=mission,
        database_url=database_url,
        connect_factory=connect_factory,
    )

    output_dir = Path(output_dir or EXECUTION_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    execution_id = _execution_id(mission["mission_id"])
    packet = _release_packet(mission, execution_id)
    packet_path = output_dir / f"{execution_id}.release.json"
    packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
    return {
        "success": True,
        "status": "release_execution_prepared",
        "mission_id": mission["mission_id"],
        "title": mission.get("title", ""),
        "execution_id": execution_id,
        "release_packet_path": str(packet_path),
        "visual_review_cleanup": cleanup_result,
        "will_complete_no_release": False,
    }, 200


def complete_no_release_mission(mission_id="", output_dir=None, database_url=None, connect_factory=None):
    prepared, status_code = prepare_release_execution(
        mission_id=mission_id,
        output_dir=output_dir,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status_code >= 400:
        return prepared, status_code
    mission_id = prepared["mission_id"]
    release_packet_path = prepared["release_packet_path"]

    started, start_status = update_mission_status(
        mission_id,
        "release_in_progress",
        owner_decision="Local release bridge started no-release closeout.",
        event_type="status_changed",
        notes="Local release bridge moved release-approved mission into release_in_progress.",
        metadata={
            "script": "scripts/charlie_release_bridge.py",
            "release_packet_path": release_packet_path,
            "release_mode": "no_release_closeout",
        },
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if start_status >= 400:
        return started, start_status

    vault_result, vault_status = update_mission_vault(
        mission_id,
        {
            "release_packet": {
                "mode": "no_release_closeout",
                "release_packet_path": release_packet_path,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "result": "No merge/deploy was required; mission closed after owner final approval.",
            }
        },
        notes="Local release bridge recorded no-release closeout packet.",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if vault_status >= 400:
        return vault_result, vault_status

    done, done_status = update_mission_status(
        mission_id,
        "done",
        owner_decision="Mission completed after owner final approval; no release was required.",
        event_type="status_changed",
        notes="Local release bridge marked mission done after no-release closeout.",
        metadata={
            "script": "scripts/charlie_release_bridge.py",
            "release_packet_path": release_packet_path,
            "release_mode": "no_release_closeout",
        },
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if done_status >= 400:
        return done, done_status
    cleanup_result = cleanup_visual_review_media(mission_id)
    return {
        "success": True,
        "status": "release_no_release_completed",
        "mission_id": mission_id,
        "mission_status": "done",
        "release_packet_path": release_packet_path,
        "visual_review_cleanup": cleanup_result,
    }, 200


def run_release_execution(
    mission_id="",
    output_dir=None,
    merge_pr=False,
    verify_url="",
    verify_attempts=AGENT_RELEASE_VERIFY_ATTEMPTS,
    verify_interval_seconds=AGENT_RELEASE_VERIFY_INTERVAL_SECONDS,
    database_url=None,
    connect_factory=None,
    run_subprocess=None,
):
    prepared, status_code = prepare_release_execution(
        mission_id=mission_id,
        output_dir=output_dir,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status_code >= 400:
        return prepared, status_code
    mission_id = prepared["mission_id"]
    release_packet_path = prepared["release_packet_path"]

    mission, mission_status, error = _load_release_mission(
        mission_id=mission_id,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if mission_status >= 400:
        return error, mission_status

    pr_reference = ""
    release_coordinator = None
    if merge_pr:
        pr_reference = _review_pr_reference(mission)
        if not pr_reference:
            blocked, blocked_status = update_mission_status(
                mission_id,
                "blocked",
                owner_decision="Release bridge could not merge because no PR reference was found in the review packet.",
                event_type="status_changed",
                notes="Local release bridge requires a PR URL or PR number before automatic merge/deploy.",
                metadata={
                    "script": "scripts/charlie_release_bridge.py",
                    "release_packet_path": release_packet_path,
                    "release_mode": "merge_pr",
                },
                database_url=database_url,
                connect_factory=connect_factory,
            )
            if blocked_status >= 400:
                return blocked, blocked_status
            return {
                "success": False,
                "status": "release_pr_reference_required",
                "mission_id": mission_id,
                "mission_status": "blocked",
                "release_packet_path": release_packet_path,
            }, 409
        release_coordinator = ReleaseCoordinator(runtime_path_root(REPO_ROOT), mission_id, pr_reference)
        coordinated, coordination_owner = release_coordinator.acquire()
        if not coordinated:
            return {
                "success": False,
                "status": "release_coordination_locked",
                "mission_id": mission_id,
                "mission_status": "release_approved",
                "release_packet_path": release_packet_path,
                "lock_owner": coordination_owner,
            }, 409

    started, start_status = update_mission_status(
        mission_id,
        "release_in_progress",
        owner_decision="Local release bridge started final release execution.",
        event_type="status_changed",
        notes="Local release bridge moved release-approved mission into release_in_progress.",
        metadata={
            "script": "scripts/charlie_release_bridge.py",
            "release_packet_path": release_packet_path,
            "release_mode": "merge_pr" if merge_pr else "prepare_only",
        },
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if start_status >= 400:
        if release_coordinator:
            release_coordinator.release()
        return started, start_status

    if not merge_pr:
        return {
            "success": True,
            "status": "release_prepared_waiting_for_merge_mode",
            "mission_id": mission_id,
            "mission_status": "release_in_progress",
            "release_packet_path": release_packet_path,
            "next_action": "Run with merge_pr=True only when the review packet includes a PR link and owner final approval is recorded.",
        }, 200

    runner = run_subprocess or subprocess.run
    command = ["gh", "pr", "merge", pr_reference, "--squash", "--delete-branch"]
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(REPO_ROOT),
            timeout=900,
            check=False,
        )
    except Exception:
        release_coordinator.release()
        raise
    merge_result = {
        "pr_reference": pr_reference,
        "command": " ".join(command),
        "returncode": completed.returncode,
        "stdout": _truncate(completed.stdout or "", 2000),
        "stderr": _truncate(completed.stderr or "", 2000),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if completed.returncode != 0:
        reconciliation = _reconcile_merged_pr(pr_reference, runner)
        merge_result["reconciliation"] = reconciliation
        release_failure = _classify_release_merge_failure(merge_result)
        if reconciliation.get("merged"):
            merge_result["reconciled_as_merged"] = True
            result = _complete_release_merge(
                mission_id=mission_id,
                release_packet_path=release_packet_path,
                merge_result=merge_result,
                verify_url=verify_url,
                verify_attempts=verify_attempts,
                verify_interval_seconds=verify_interval_seconds,
                database_url=database_url,
                connect_factory=connect_factory,
            )
            release_coordinator.record("release_reconciled", merge_result=merge_result)
            release_coordinator.release()
            return result
        existing_metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
        existing_release = existing_metadata.get("release_packet") if isinstance(existing_metadata.get("release_packet"), dict) else {}
        existing_review = existing_metadata.get("review_packet") if isinstance(existing_metadata.get("review_packet"), dict) else {}
        update_mission_vault(
            mission_id,
            {
                "release_packet": {
                    **existing_release,
                    "mode": "merge_pr",
                    "release_packet_path": release_packet_path,
                    "merge_result": merge_result,
                    "status": release_failure["status"],
                    "failure_class": release_failure["failure_class"],
                    "recommended_next_action": release_failure["recommended_next_action"],
                },
                "review_packet": {
                    **existing_review,
                    "review_status": release_failure["status"],
                    "blocked_reason": release_failure["owner_reason"],
                    "recommended_next_action": release_failure["recommended_next_action"],
                    "release_packet_path": release_packet_path,
                    "release_failure": release_failure,
                }
            },
            notes="Local release bridge recorded failed PR merge result.",
            database_url=database_url,
            connect_factory=connect_factory,
        )
        update_mission_status(
            mission_id,
            "blocked",
            owner_decision=release_failure["owner_reason"],
            event_type="status_changed",
            notes=release_failure["recommended_next_action"],
            metadata={
                "script": "scripts/charlie_release_bridge.py",
                "release_packet_path": release_packet_path,
                "release_mode": "merge_pr",
                "returncode": completed.returncode,
                "release_failure_class": release_failure["failure_class"],
                "pr_reference": pr_reference,
            },
            database_url=database_url,
            connect_factory=connect_factory,
        )
        result = {
            "success": False,
            "status": release_failure["status"],
            "mission_id": mission_id,
            "mission_status": "blocked",
            "release_packet_path": release_packet_path,
            "merge_result": merge_result,
            "failure_class": release_failure["failure_class"],
            "recommended_next_action": release_failure["recommended_next_action"],
        }, 502
        release_coordinator.record("release_merge_failed", merge_result=merge_result)
        release_coordinator.release()
        return result

    result = _complete_release_merge(
        mission_id=mission_id,
        release_packet_path=release_packet_path,
        merge_result=merge_result,
        verify_url=verify_url,
        verify_attempts=verify_attempts,
        verify_interval_seconds=verify_interval_seconds,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    release_coordinator.record("release_completed", merge_result=merge_result)
    release_coordinator.release()
    return result


def _complete_release_merge(
    mission_id,
    release_packet_path,
    merge_result,
    verify_url="",
    verify_attempts=AGENT_RELEASE_VERIFY_ATTEMPTS,
    verify_interval_seconds=AGENT_RELEASE_VERIFY_INTERVAL_SECONDS,
    database_url=None,
    connect_factory=None,
):
    verify_result = _wait_for_release_verification(
        verify_url or _default_release_verify_url(),
        attempts=verify_attempts,
        interval_seconds=verify_interval_seconds,
    )
    final_status = "deployed" if verify_result.get("verified") else "merged"
    vault_result, vault_status = update_mission_vault(
        mission_id,
        {
            "release_packet": {
                "mode": "merge_pr",
                "release_packet_path": release_packet_path,
                "merge_result": merge_result,
                "verify_result": verify_result,
                "deployment_watch": {
                    "verify_url": verify_result.get("url", ""),
                    "attempts": verify_result.get("attempts", 0),
                    "verified": verify_result.get("verified", False),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                },
            }
        },
        notes="Local release bridge recorded PR merge result.",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if vault_status >= 400:
        return vault_result, vault_status

    final, final_update_status = update_mission_status(
        mission_id,
        final_status,
        owner_decision=f"Mission release completed by local release bridge; status {final_status}.",
        event_type="status_changed",
        notes="Local release bridge completed PR merge release path.",
        metadata={
            "script": "scripts/charlie_release_bridge.py",
            "release_packet_path": release_packet_path,
            "release_mode": "merge_pr",
            "final_status": final_status,
            "verify_url": verify_url,
        },
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if final_update_status >= 400:
        return final, final_update_status
    cleanup_result = cleanup_visual_review_media(mission_id)
    return {
        "success": True,
        "status": "release_pr_merged",
        "mission_id": mission_id,
        "mission_status": final_status,
        "release_packet_path": release_packet_path,
        "merge_result": merge_result,
        "verify_result": verify_result,
        "visual_review_cleanup": cleanup_result,
    }, 200


def _classify_release_merge_failure(merge_result):
    merge_result = merge_result if isinstance(merge_result, dict) else {}
    stderr = str(merge_result.get("stderr") or "")
    stdout = str(merge_result.get("stdout") or "")
    combined = f"{stderr}\n{stdout}".lower()
    pr_reference = str(merge_result.get("pr_reference") or "").strip()
    if any(marker in combined for marker in ("merge conflicts", "merge conflict", "not mergeable", "cannot be merged")):
        return {
            "status": "release_pr_merge_conflict",
            "failure_class": "release_conflict",
            "owner_reason": "Release bridge could not merge the approved PR because GitHub reports merge conflicts.",
            "recommended_next_action": (
                f"Rebase or recreate PR {pr_reference} onto current main, resolve conflicts, rerun focused tests, "
                "then approve release again. The mission review itself remains approved."
            ).strip(),
        }
    return {
        "status": "release_pr_merge_failed",
        "failure_class": "release_merge_failed",
        "owner_reason": "Local release bridge failed to merge the approved PR.",
        "recommended_next_action": "Inspect the release packet stderr/stdout, repair the PR or release command, then rerun release.",
    }


def build_codex_execution_prompt(mission):
    mission = mission if isinstance(mission, dict) else {}
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    workflow = mission.get("agent_workflow") if isinstance(mission.get("agent_workflow"), list) else []
    context_pack = mission.get("mission_context_pack") if isinstance(mission.get("mission_context_pack"), dict) else {}
    vault_context = build_vault_brain_context(mission)
    return f"""You are the local Codex executor for a CHARLIE mission.

Mission ID: {mission.get("mission_id", "")}
Title: {mission.get("title", "")}
Status: {mission.get("status", "")}
Approval level: {mission.get("approval_level", "")}
Urgency: {mission.get("urgency", "")}
Mission type: {mission.get("mission_type", "")}

Follow these documents before changing anything:
- docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md
- docs/00-start-here/CHARLIE_CORE_AGENT_RUNNER_V2.md
- docs/00-start-here/CURRENT_STATE.md
- docs/00-start-here/NEXT_STEPS.md
- docs/00-start-here/WORKFLOW.md
- docs/00-start-here/DEPLOYMENT_SOP.md

CHARLIE Vault Brain context:
{_format_vault_context(vault_context)}

Mission Vault:
- Problem: {vault.get("problem_statement") or mission.get("raw_text", "")}
- Desired outcome: {vault.get("desired_outcome") or ""}
- Scope summary: {vault.get("scope_summary") or ""}
- Acceptance criteria:
{_format_list(vault.get("acceptance_criteria"))}
- Test plan:
{_format_list(vault.get("test_plan"))}
- Forbidden actions:
{_format_list(vault.get("forbidden_actions"))}

Agent workflow:
{_format_workflow(workflow)}

Shared context pack:
{json.dumps(context_pack, indent=2)}

Required behavior:
1. Execute planner, architect, builder, tester, and reviewer responsibilities in order.
2. Use the Vault Brain before opinion. Do not rely on memory where Vault truth exists.
3. Cite the Vault docs used in your final evidence.
4. Stay within the recorded approval level and the forbidden actions.
5. Do not merge, deploy, apply migrations, send customers, post publicly, take payments, reserve stock, or change farm lifecycle records unless the mission explicitly authorizes that action and the deployment SOP is clean.
6. Run focused verification that fits the actual changes.
7. Stop at owner review. Do not mark the mission done.
8. In your final response, include: summary, files changed, tests run, errors/bugs, Vault sources used, local preview link or command, and recommended owner review decision.
"""


def build_agent_stage_prompt(mission, agent, artifacts=None, ledger=None):
    mission = mission if isinstance(mission, dict) else {}
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    review_packet = (mission.get("metadata") or {}).get("review_packet") if isinstance(mission.get("metadata"), dict) else {}
    owner_comments = review_packet.get("owner_comments_pending", "") if isinstance(review_packet, dict) else ""
    sequence = _mission_agent_sequence(mission)
    vault_context = build_vault_brain_context(mission, agent=agent)
    implementation_context = implementation_source_packet(mission)
    ui_contract = _ui_quality_contract_for_mission(mission)
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    mission_memory = memory_prompt_context(metadata)
    mission_governance = ensure_acceptance_matrix(mission)
    metadata_core = metadata.get("charlie_core") if isinstance(metadata.get("charlie_core"), dict) else {}
    agentic_architecture = metadata.get("agentic_architecture") or metadata_core.get("agentic_architecture") or (metadata_core.get("project_truth") or {}).get("agentic_architecture") or {}
    pre_builder_scope = analyze_pre_builder_scope(mission)
    test_command_memory = repo_test_command_memory(_mission_changed_files_from_artifacts(artifacts))
    runner_preflight = runner_environment_preflight(require_browser=bool(ui_contract.get("ui_related")))
    model_assignment = choose_agent_model(
        agent=agent,
        mission_type=mission.get("mission_type", ""),
        risk_level="high" if ui_contract.get("ui_related") else "medium",
    )
    doctrine_path = AGENT_DOCTRINE_PATHS.get(str(agent or "").strip().lower(), "")
    return f"""You are the CHARLIE CORE {agent.upper()} agent running inside Agent Runner v2.

Mission ID: {mission.get("mission_id", "")}
Title: {mission.get("title", "")}
Approval level: {mission.get("approval_level", "")}
Mission type: {mission.get("mission_type", "")}
Pre-Builder scope contract:
{json.dumps(pre_builder_scope, indent=2)}

The planner and architects must resolve every planning_gates item before Builder. If split_required is true, keep the frozen parent acceptance matrix bounded and record adjacent discoveries as linked child missions rather than expanding this mission indefinitely.
Agent doctrine file: {doctrine_path or "MISSING - Brain Guard must block this workflow until doctrine exists."}
Model assignment:
{json.dumps(model_assignment, indent=2)}

Final artifact contract:
{json.dumps(final_artifact_contract_packet(), indent=2)}

Partial recovery contract:
{json.dumps(partial_recovery_contract_packet(), indent=2)}

Repo test command memory:
{json.dumps(test_command_memory, indent=2)}

Focused test budget:
{_focused_test_budget_prompt(mission, agent, artifacts)}

Runner environment preflight:
{json.dumps(runner_preflight, indent=2)}

Mission:
{mission.get("raw_text", "")}

Required CHARLIE docs to follow:
- docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md
- docs/00-start-here/CHARLIE_CORE_AGENT_RUNNER_V2.md
- docs/00-start-here/CURRENT_STATE.md
- docs/00-start-here/NEXT_STEPS.md
- docs/00-start-here/WORKFLOW.md
- docs/00-start-here/DEPLOYMENT_SOP.md

CHARLIE Vault Brain context:
{_format_vault_context(vault_context)}

Implementation source map:
{json.dumps(implementation_context, indent=2)[:8000]}

Desired outcome:
{vault.get("desired_outcome") or ""}

Owner send-back comments:
{owner_comments or "None"}

Mission memory from previous attempts and handoffs:
{json.dumps(mission_memory, indent=2)[:5000]}

Frozen acceptance matrix and discovery rules:
{json.dumps(mission_governance, indent=2)[:7000]}

Frozen Agentic Architecture Packet:
{json.dumps(agentic_architecture, indent=2)[:7000]}

This packet is an acceptance contract. Do not solve domain reasoning with a question-specific route, UI branch, regex reply, or transport handler. Build or extend the owning operational agent and keep deterministic code limited to canonical reads, calculations, validation, permissions, idempotency, audit, and safe execution.

Mission media/reference attachments:
{_format_media_references(_mission_media_references(mission))}

UI mission quality contract:
{json.dumps(ui_contract, indent=2)}

Unresolved agent send-back issues:
{json.dumps(_agent_unresolved_issue_context(artifacts, ledger), indent=2)[:4000]}

Forbidden actions:
{_format_list(vault.get("forbidden_actions"))}

Previous agent artifacts:
{json.dumps(_agent_artifacts_for_prompt(artifacts, agent, sequence), indent=2)[:12000]}

Mission agent order:
{", ".join(sequence)}

You must work like an interactive coding agent:
- inspect the repo before asserting facts
- check the Vault Brain before opinion, and cite the docs you used
- read relevant files
- run focused commands when useful
- prefer focused tests for the changed surface first; broad runner/full-suite timeouts are advisory only when focused evidence passes and no owner/customer/order/stock safety risk is present
- verify the frozen acceptance matrix; do not silently expand the parent mission when an adjacent improvement is discovered
- label pre-existing or merge-base failures explicitly; they are follow-up evidence and do not fail the current mission
- report new actionable discoveries with affected paths and reproduction evidence so CORE can create a linked child mission
- patch only scoped files
- recover from errors
- record what you did and what remains
- if you change agents, workflows, CHARLIE CORE runtime, business rules, data contracts, or standards, update the matching Vault Brain doc; otherwise record why no Vault update was required
- if this is a UI mission, inspect and cite every attached reference image/path you can access, build against the actual owner workflow, provide a real local preview URL, and include desktop/laptop plus mobile browser evidence
- if this is an income, sales, SAM, Beacon, order, WhatsApp, Chatwoot, or n8n-related mission, inspect and cite the implementation source map paths before advising or building; strategy docs alone are not enough
- behave as this specific agent, not as a generic prompt; challenge upstream artifacts when they are weak, contradictory, or not aligned with your doctrine

Stage responsibility:
{_agent_stage_instruction(agent)}

Required final response format:
Return concise markdown, and include a JSON object fenced as ```json with these keys:
{json.dumps(_agent_required_schema(agent), indent=2)}

Every final JSON object is normalized into a CHARLIE handoff report with:
- mission_id, agent, status, summary
- vault_sources_used and vault_updates/no_vault_update_required
- files_inspected, commands_run, stdout_tail, stderr_tail
- changed_files, risks, tests, quality_gate, next_action
- artifact_path and completed_at

Do not merge, deploy, apply migrations, send customers, post publicly, take payments, reserve stock, or change farm lifecycle records.
Stop at the required artifact for this stage.
"""


def _ensure_execution_governance(mission, database_url=None, connect_factory=None):
    mission = mission if isinstance(mission, dict) else {}
    governance = ensure_acceptance_matrix(mission)
    pre_builder_scope = analyze_pre_builder_scope(mission)
    mission.setdefault("metadata", {})["mission_governance"] = governance
    mission["metadata"]["pre_builder_scope"] = pre_builder_scope
    from modules.charlie.agentic_architecture import build_agentic_architecture_packet
    architecture = build_agentic_architecture_packet(mission)
    mission["metadata"]["agentic_architecture"] = architecture
    update_mission_vault(
        mission.get("mission_id", ""),
        {"mission_governance": governance, "pre_builder_scope": pre_builder_scope, "agentic_architecture": architecture},
        notes="CHARLIE froze the mission acceptance matrix and pre-Builder scope contract before execution.",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if pre_builder_scope.get("split_required"):
        _record_scope_children(mission, pre_builder_scope, database_url=database_url, connect_factory=connect_factory)
    return mission


def _pause_decomposed_parent(mission, database_url=None, connect_factory=None):
    """Turn an oversized parent into a coordinator; only its ordered children execute."""
    mission = mission if isinstance(mission, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    family = metadata.get("mission_family") if isinstance(metadata.get("mission_family"), dict) else {}
    scope = metadata.get("pre_builder_scope") if isinstance(metadata.get("pre_builder_scope"), dict) else {}
    if family.get("parent_mission_id") or not scope.get("split_required"):
        return None
    children = [
        str(item.get("mission_id") or "").strip()
        for item in scope.get("linked_children", [])
        if isinstance(item, dict) and str(item.get("mission_id") or "").strip()
    ]
    coordinator = {
        "status": "waiting_children",
        "child_mission_ids": children,
        "completed_child_ids": [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    update_mission_vault(
        mission.get("mission_id", ""),
        {"mission_coordinator": coordinator},
        notes="Oversized parent paused as a coordinator for ordered child missions.",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    update_mission_status(
        mission.get("mission_id", ""),
        "paused",
        owner_decision="CORE decomposed this oversized mission; ordered child missions now carry delivery.",
        notes="Split parent paused at waiting_children and will not execute a duplicate pipeline.",
        expected_status="in_progress",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    return {
        "success": True,
        "status": "mission_decomposed_waiting_children",
        "mission_id": mission.get("mission_id", ""),
        "child_mission_ids": children,
        "owner_action_required": False,
    }


def _record_scope_children(mission, scope_analysis, database_url=None, connect_factory=None):
    recorded = []
    for child in build_scope_child_missions(mission, scope_analysis):
        result, status_code = record_mission(
            child,
            source_context={"source": "charlie_pre_builder_scope"},
            database_url=database_url,
            connect_factory=connect_factory,
        )
        recorded.append({
            "mission_id": result.get("mission_id") or child["mission_id"],
            "status": result.get("status", "record_failed"),
            "created": status_code < 400 and result.get("status") != "duplicate_open_mission",
        })
    update_mission_vault(
        mission.get("mission_id", ""),
        {"pre_builder_scope": {**scope_analysis, "linked_children": recorded}},
        notes="CHARLIE materialized linked child missions for oversized scope.",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    return recorded


def _record_acceptance_progress(mission, agent, artifact, passed, database_url=None, connect_factory=None):
    mission = mission if isinstance(mission, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    governance = ensure_acceptance_matrix(mission, planner_artifact=artifact if agent == "planner" else None)
    governance = update_acceptance_matrix(governance, agent, artifact, passed)
    mission.setdefault("metadata", {})["mission_governance"] = governance
    return update_mission_vault(
        mission.get("mission_id", ""),
        {"mission_governance": governance},
        notes=f"CHARLIE recorded {agent} acceptance-matrix evidence.",
        database_url=database_url,
        connect_factory=connect_factory,
    )


def _record_discovered_followups(mission, agent, decision, database_url=None, connect_factory=None):
    recorded = []
    for child in build_followup_missions(mission, decision.get("followup_findings", [])):
        result, status_code = record_mission(
            child,
            source_context={"source": "charlie_discovery"},
            database_url=database_url,
            connect_factory=connect_factory,
        )
        child_id = result.get("mission_id") or child.get("mission_id")
        item = {
            "mission_id": child_id,
            "title": child.get("title", ""),
            "status": result.get("status", "record_failed"),
            "finding_family": (child.get("metadata") or {}).get("mission_family", {}).get("finding_family", ""),
            "created": status_code < 400 and result.get("status") != "duplicate_open_mission",
        }
        recorded.append(item)
        _record_mission_memory_event(
            mission,
            build_memory_event(
                agent,
                "followup_discovered",
                summary=f"Discovered follow-up {child_id}: {item['finding_family']}",
                artifact={"next_action": "Owner may approve the linked child mission separately."},
                metadata={
                    "child_mission_id": child_id,
                    "finding_family": item["finding_family"],
                    "record_status": item["status"],
                },
            ),
            database_url=database_url,
            connect_factory=connect_factory,
        )
    return recorded


def _primary_finding_family(artifact):
    decision = artifact.get("mission_governance_decision") if isinstance(artifact, dict) and isinstance(artifact.get("mission_governance_decision"), dict) else {}
    findings = decision.get("blocking_findings") if isinstance(decision.get("blocking_findings"), list) else []
    return str(findings[0].get("family") or "implementation_defect") if findings and isinstance(findings[0], dict) else "implementation_defect"


def _mission_changed_files_from_artifacts(artifacts):
    files = []
    for artifact in (artifacts or {}).values():
        if not isinstance(artifact, dict):
            continue
        for value in artifact.get("changed_files") or []:
            text = str(value or "").strip()
            if text and text not in files:
                files.append(text)
    return files


def build_vault_brain_context(mission, agent=""):
    mission = mission if isinstance(mission, dict) else {}
    retrieval = retrieve_vault_sources(mission, limit=16, excerpt_chars=900, agent=agent)
    entries = []
    remaining = VAULT_CONTEXT_CHAR_BUDGET
    for source in retrieval.get("sources", []):
        relative_path = source.get("path", "") if isinstance(source, dict) else ""
        text = source.get("excerpt", "") if isinstance(source, dict) else ""
        status = source.get("status", "missing") if isinstance(source, dict) else "missing"
        excerpt = text
        if excerpt and remaining > 0:
            excerpt = _truncate(excerpt, min(remaining, 1600))
            remaining -= len(excerpt)
        entries.append({
            "path": relative_path,
            "status": status,
            "score": source.get("score", 0) if isinstance(source, dict) else 0,
            "reasons": source.get("reasons", []) if isinstance(source, dict) else [],
            "excerpt": excerpt,
        })
    return {
        "version": "charlie_vault_brain_context_v1",
        "agent": str(agent or "").strip().lower(),
        "root": "docs/09-vault-brain",
        "rule": "Vault Brain is canonical project truth for CHARLIE identity, agents, workflows, business rules, data rules, standards, and playbooks.",
        "retrieval": retrieval,
        "owner_preferences": owner_preference_packet(),
        "docs": entries,
        "missing_docs": [entry["path"] for entry in entries if entry["status"] != "loaded"],
    }


def _mission_media_references(mission):
    mission = mission if isinstance(mission, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    direct = mission.get("media_references") if isinstance(mission.get("media_references"), list) else []
    stored = metadata.get("media_references") if isinstance(metadata.get("media_references"), list) else []
    mission_id = str(mission.get("mission_id") or "mission").strip() or "mission"
    media = []
    seen = set()
    for item in [*direct, *stored]:
        if not isinstance(item, dict):
            continue
        reference = str(item.get("reference") or item.get("url") or item.get("path") or "").strip()
        if not reference or reference in seen:
            continue
        seen.add(reference)
        compact_reference = _compact_media_reference_for_prompt(mission_id, reference)
        media.append({
            "label": str(item.get("label") or reference).strip()[:120],
            "reference": compact_reference["reference"],
            "media_type": str(item.get("media_type") or "reference").strip()[:40],
            "reference_kind": compact_reference["kind"],
            "original_reference_length": compact_reference["original_length"],
            "materialized": compact_reference.get("materialized", False),
        })
    return media[:12]


def _compact_media_reference_for_prompt(mission_id, reference):
    reference = str(reference or "").strip()
    compact = {
        "reference": reference,
        "kind": "path_or_url",
        "original_length": len(reference),
        "materialized": False,
    }
    if not reference:
        return compact
    materialized = _materialize_inline_image_reference(mission_id, reference)
    if materialized:
        compact.update({
            "reference": materialized,
            "kind": "inline_image_materialized_to_local_file",
            "materialized": True,
        })
        return compact
    if len(reference) > 1000:
        digest = hashlib.sha256(reference.encode("utf-8", errors="replace")).hexdigest()[:16]
        compact.update({
            "reference": f"{reference[:240]}... [truncated {len(reference)} chars, sha256:{digest}]",
            "kind": "long_reference_truncated",
        })
    return compact


def _materialize_inline_image_reference(mission_id, reference):
    match = INLINE_IMAGE_DATA_URL_RE.match(str(reference or "").strip())
    if not match:
        return ""
    image_kind = match.group("kind").lower()
    extension = ".jpg" if image_kind in {"jpg", "jpeg"} else f".{image_kind}"
    encoded = re.sub(r"\s+", "", match.group("data") or "")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        return ""
    if not raw:
        return ""
    digest = hashlib.sha256(raw).hexdigest()[:20]
    mission_slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(mission_id or "mission")).strip("-") or "mission"
    media_dir = MISSION_MEDIA_DIR / mission_slug
    media_dir.mkdir(parents=True, exist_ok=True)
    target = media_dir / f"{digest}{extension}"
    if not target.exists():
        target.write_bytes(raw)
    try:
        return target.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(target)


def _format_media_references(items):
    items = items if isinstance(items, list) else []
    if not items:
        return "- No media references captured."
    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "Reference").strip()
        reference = str(item.get("reference") or "").strip()
        media_type = str(item.get("media_type") or "reference").strip()
        if reference:
            lines.append(f"- {label} ({media_type}): {reference}")
    return "\n".join(lines) or "- No media references captured."


def _ui_quality_contract_for_mission(mission):
    mission = mission if isinstance(mission, dict) else {}
    media = _mission_media_references(mission)
    image_media = [
        item for item in media
        if str(item.get("media_type") or "").lower() == "image"
        or re.search(r"\.(png|jpe?g|webp|gif)$", str(item.get("reference") or ""), re.IGNORECASE)
        or str(item.get("reference") or "").startswith("data:image/")
    ]
    text = " ".join([
        str(mission.get("mission_type") or ""),
        str(mission.get("title") or ""),
        str(mission.get("raw_text") or ""),
    ])
    ui_related = bool(image_media) or _is_ui_related_mission(mission.get("mission_type", ""), [], text)
    return {
        "version": "charlie_ui_quality_contract_v1",
        "ui_related": ui_related,
        "reference_media_required": bool(image_media),
        "media_references": media,
        "required_vault_docs": [
            "docs/09-vault-brain/07-standards/CHARLIE_CORE_UI_MISSION_STANDARD.md",
            "docs/09-vault-brain/07-standards/UI_DASHBOARD_STANDARD.md",
            "docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md",
            "docs/09-vault-brain/07-standards/TESTING_STANDARD.md",
        ],
        "required_viewports": ["desktop/laptop", "mobile"],
        "gate": (
            "UI missions must provide real local preview screenshots for desktop/laptop and mobile before owner review; "
            "generated fallback packets do not satisfy the gate. If the in-app browser is unavailable, use the repository's "
            "installed Playwright CLI against the real local preview and record the resulting durable screenshot paths."
        ),
    }


def _vault_context_doc_paths(mission):
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    core = metadata.get("charlie_core") if isinstance(metadata.get("charlie_core"), dict) else {}
    project_truth = core.get("project_truth") if isinstance(core.get("project_truth"), dict) else {}
    template = str(project_truth.get("workflow_template") or "").strip()
    if not template:
        vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
        project_truth = vault.get("project_truth") if isinstance(vault.get("project_truth"), dict) else {}
        template = str(project_truth.get("workflow_template") or "").strip()
    docs = list(VAULT_REQUIRED_BASE_DOCS)
    docs.extend(VAULT_CONTEXT_BY_TEMPLATE.get(template, []))
    haystack = " ".join([
        str(mission.get("mission_type") or ""),
        str(mission.get("title") or ""),
        str(mission.get("raw_text") or ""),
    ]).lower()
    for keyword, keyword_docs in VAULT_CONTEXT_BY_KEYWORD.items():
        if keyword in haystack:
            docs.extend(keyword_docs)
    return _unique_existing_order(docs)


def _format_vault_context(context):
    context = context if isinstance(context, dict) else {}
    lines = [
        f"- Version: {context.get('version', '')}",
        f"- Rule: {context.get('rule', '')}",
    ]
    missing = context.get("missing_docs") if isinstance(context.get("missing_docs"), list) else []
    if missing:
        lines.append(f"- Missing docs: {', '.join(missing)}")
    retrieval = context.get("retrieval") if isinstance(context.get("retrieval"), dict) else {}
    if retrieval:
        lines.append(f"- Selection rule: {retrieval.get('selection_rule', '')}")
        lines.append(f"- Workflow template: {retrieval.get('workflow_template', '')}")
    owner_preferences = context.get("owner_preferences") if isinstance(context.get("owner_preferences"), dict) else {}
    preferences = owner_preferences.get("preferences") if isinstance(owner_preferences.get("preferences"), list) else []
    if preferences:
        lines.append("\n### Owner Preferences")
        lines.extend(f"- {item}" for item in preferences)
    for entry in context.get("docs", []):
        if not isinstance(entry, dict):
            continue
        reasons = ", ".join(entry.get("reasons", [])) if isinstance(entry.get("reasons"), list) else ""
        lines.append(f"\n### {entry.get('path', '')} ({entry.get('status', '')}, score {entry.get('score', 0)})")
        if reasons:
            lines.append(f"Selected because: {reasons}")
        excerpt = str(entry.get("excerpt") or "").strip()
        lines.append(excerpt if excerpt else "No excerpt loaded.")
    return "\n".join(lines)


def _read_repo_text(relative_path):
    clean = str(relative_path or "").replace("\\", "/").lstrip("/")
    path = (REPO_ROOT / clean).resolve()
    try:
        path.relative_to(REPO_ROOT)
    except ValueError:
        return ""
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _unique_existing_order(items):
    result = []
    seen = set()
    for item in items:
        text = str(item or "").strip().replace("\\", "/")
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _agent_stage_instruction(agent):
    if agent == "idea_expander":
        return "Clarify the rough idea, expected owner value, target user/workflow, constraints, non-goals, and what must not be assumed."
    if agent == "visual_reference_interpreter":
        return (
            "Inspect every attached UI/reference image and convert it into a hard visual contract: layout zones, hierarchy, density, navigation, "
            "cards/panels, active states, side rails, bottom bars, colors only where meaningful, and the specific similarities the build must preserve."
        )
    if agent == "creative_ui_designer":
        return (
            "Create the UI design direction before code. Produce a distinctive concept, information architecture, layout system, visual hierarchy, "
            "component treatment, and reference-match requirements. Do not accept color-only restyling as a design."
        )
    if agent == "ux_interaction_designer":
        return (
            "Define the owner workflows, visible action placement, interaction states, responsive behavior, empty/loading/error states, and how the user moves through the screen."
        )
    if agent == "source_mapper":
        return (
            "Map what already exists before anyone plans or builds. Inspect the implementation source map, then read or verify relevant routes, modules, templates, JS, tests, migrations, active docs, and legacy n8n/Sheets sources. "
            "Separate current Supabase/app truth from legacy n8n/Google Sheets behavior and identify exact tests to prove the mission. "
            "For every matched source-map section, include at least one matched vault_docs path, one code_paths path, one tests path, and any matched legacy_sources path in files_inspected or implementation_sources_used; vault_sources_used alone is not enough for this gate."
        )
    if agent == "product_architect":
        return "Design the user/product flow, acceptance boundaries, business fit, and what the technical Planner must preserve."
    if agent == "risk_agent":
        return (
            "Find current technical, product, operational, business, legal, data, and owner-trust risks before build. "
            "In read-only planning, do not send_back solely because downstream final artifacts, test evidence, review-packet persistence, or owner approval evidence cannot exist yet; "
            "record those as required mitigations for later agents. Send back only for a present, proven violation of scope, safety, authority, data, or owner gates."
        )
    if agent == "council_synthesis":
        return "Read upstream agent artifacts, resolve conflicts, preserve owner intent, and produce one council-approved build brief before Planner and Builder proceed."
    if agent == "planner":
        return (
            "Read mission context and define scope, acceptance criteria, test plan, risks, and exact next handoff. "
            "When the implementation source map matches this mission, include exact matched implementation source-map paths in files_inspected or implementation_sources_used; "
            "Vault docs alone do not satisfy the source-truth gate."
        )
    if agent == "architect":
        return "Inspect implementation boundaries, source files, route/data contracts, risks, and the safest build approach."
    if agent == "builder":
        return (
            "Implement only the scoped change, keep diffs tight, and record changed files. "
            "When changed_files contains releaseable changes under LEVEL 3 or higher, create or update a branch, commit the scoped diff, push it, open a PR, "
            "and record branch_name, commit_sha, pr_url/pr_number, and PR link evidence. For UI missions, provide a real local_preview URL for the changed page, "
            "visual_reference_analysis, media_references_used, viewport_plan, and browser_check_plan. Do not merge."
        )
    if agent == "frontend_design_implementer":
        return (
            "Implement the approved UI concept and interaction spec in the real frontend. Preserve the visual-reference contract, keep owner actions visible, "
            "avoid overflow/hidden controls, capture a real local preview URL, and prepare desktop/mobile browser checks before Builder packaging."
        )
    if agent == "tester":
        return "Run focused verification, investigate failures, and return pass/fail evidence. For UI missions, run browser-level desktop/laptop and mobile checks against the actual changed route and record screenshots_captured or browser_checks."
    if agent == "qa_red_team":
        return "Pressure-test the work for regressions, weak evidence, unsafe actions, missing tests, security/privacy risk, owner-facing failure modes, and visual mismatch against attached reference media."
    if agent == "visual_qa_reviewer":
        return (
            "Compare the finished UI screenshots and local preview against the owner reference media and UI concept. Block if the result is only a color change, "
            "misses the reference layout, hides buttons, overflows, or lacks desktop/mobile proof."
        )
    if agent == "publisher":
        return (
            "Prepare the existing PR for owner review without merging. Query the authoritative PR head and checks. If it conflicts with main, fetch and rebase/update the mission branch, "
            "auto-resolve additive changelog conflicts by preserving both entries, rerun focused tests, push the repaired branch, and record branch_name, commit_sha, pr_url, expected_revision, and tested_revision. "
            "Semantic code conflicts must return to Builder; they are not owner decisions."
        )
    if agent in {"tester", "evidence_reviewer", "reviewer", "product_reviewer", "business_reviewer", "security_reviewer"}:
        return (
            "Review only the exact packaged PR head. Record expected_revision and tested_revision, classify every finding as current_diff, pre_existing, unrelated, or advisory, "
            "and never block the mission for an unrelated/pre-existing finding. Query current PR checks before recommending owner review."
        )
    return "Review diff, requirements, tests, safety gates, release notes, visual evidence for UI missions, and prepare owner review recommendation."


def _agent_required_schema(agent):
    base = {
        "summary": "short factual summary",
        "errors": [],
        "bugs": [],
        "vault_sources_used": ["docs/09-vault-brain/..."],
        "vault_updates": [],
        "no_vault_update_required": "reason when no Vault doc update was needed",
        "files_inspected": [],
        "commands_run": [],
        "stdout_tail": "short relevant command output tail or empty",
        "stderr_tail": "short relevant error output tail or empty",
        "confidence": "96% or higher when final; use a decimal like 0.97 or a percent like 97%",
        "confidence_reason": "evidence-backed reason citing source truth, tests, screenshots, logs, runtime data, or owner-approved context",
        "next_action": "next handoff",
        "agentic_architecture": {"compliant": True, "owning_agent": "agent id", "deterministic_code_only": [], "reasoning_delegated_to": [], "generalization_evidence": [], "reason": "short architecture verdict"},
    }
    if agent in {"tester", "qa_red_team", "product_reviewer", "business_reviewer", "security_reviewer", "evidence_reviewer", "reviewer"}:
        base["acceptance_results"] = [
            {
                "id": "acceptance row id from the frozen matrix",
                "status": "passed, failed, or pending",
                "evidence": ["focused evidence for this row"],
            }
        ]
        base["finding_contract"] = "Each bug/error/QA finding should state scope_relation, introduced_by_current_diff, affected file/path, severity, and whether it violates a named acceptance row or is adjacent follow-up work."
    if agent == "planner":
        base.update({
            "acceptance_criteria": [],
            "test_plan": [],
            "scope": "scoped work",
            "implementation_sources_used": [
                "Include exact matched implementation source-map paths inspected when this mission matches implementation sources."
            ],
        })
    elif agent == "idea_expander":
        base.update({"opportunity": "clear owner opportunity", "owner_value": "why this matters", "non_goals": []})
    elif agent == "visual_reference_interpreter":
        base.update({
            "media_references_used": [],
            "layout_requirements": [],
            "visual_hierarchy": [],
            "interaction_clues": [],
            "reference_match_checklist": [],
            "non_negotiable_visual_elements": [],
        })
    elif agent == "creative_ui_designer":
        base.update({
            "media_references_used": [],
            "ui_concept": "named design direction",
            "layout_system": [],
            "visual_direction": [],
            "component_requirements": [],
            "design_requirements": [],
            "what_not_to_do": ["Do not only change colors."],
        })
    elif agent == "ux_interaction_designer":
        base.update({
            "media_references_used": [],
            "primary_workflows": [],
            "owner_actions": [],
            "responsive_behavior": [],
            "interaction_requirements": [],
            "empty_loading_error_states": [],
        })
    elif agent == "source_mapper":
        base.update({
            "implementation_inventory": [],
            "current_sources": [],
            "legacy_sources": [],
            "routes_found": [],
            "tests_to_run": [],
            "migrations_found": [],
            "implementation_sources_used": [
                "Include matched vault_docs, code_paths, tests, migrations, and legacy_sources paths from the implementation source map here."
            ],
            "source_truth_summary": "what exists now, what is legacy, and what must be tested",
        })
    elif agent == "product_architect":
        base.update({"user_flow": [], "acceptance_boundaries": [], "risk_notes": []})
    elif agent == "technical_architect":
        base.update({
            "files_to_inspect": [],
            "risk_notes": [],
            "implementation_plan": [],
            "implementation_sources_used": [
                "Include matched implementation source-map paths that were inspected, not only Vault docs."
            ],
        })
    elif agent == "council_synthesis":
        base.update({
            "agreements": [],
            "conflicts_resolved": [],
            "unresolved_blockers": [],
            "build_brief": "single council-approved brief for Planner and Builder",
            "acceptance_priorities": [],
        })
    elif agent == "architect":
        base.update({"files_to_inspect": [], "risk_notes": [], "implementation_plan": []})
    elif agent == "builder":
        base.update({
            "changed_files": [],
            "build_notes": [],
            "local_preview": {"url": "http://127.0.0.1:PORT/actual-changed-route"},
            "media_references_used": [],
            "visual_reference_analysis": "required for UI missions with reference media",
            "viewport_plan": ["desktop/laptop viewport", "mobile viewport"],
            "browser_check_plan": [],
            "branch_name": "branch containing scoped changed files",
            "commit_sha": "commit containing scoped changed files",
            "pr_url": "pull request URL when changed_files contains releaseable changes",
            "pr_number": "pull request number when changed_files contains releaseable changes",
            "links": {"pr": "pull request URL"},
        })
    elif agent == "frontend_design_implementer":
        base.update({
            "changed_files": [],
            "implementation_notes": [],
            "local_preview": {"url": "http://127.0.0.1:PORT/actual-changed-route"},
            "media_references_used": [],
            "visual_reference_analysis": "how the implementation matches the reference and approved UI concept",
            "viewport_plan": ["desktop/laptop viewport", "mobile viewport"],
            "browser_check_plan": [],
            "design_requirements_met": [],
            "known_visual_gaps": [],
        })
    elif agent == "tester":
        base.update({
            "tests_run": [],
            "test_status": "pass|fail|blocked",
            "browser_checks": [],
            "screenshots_captured": [],
            "media_references_used": [],
            "visual_reference_analysis": "required for UI missions with reference media",
        })
    elif agent == "qa_red_team":
        base.update({
            "qa_findings": [],
            "red_team_status": "pass|fail|blocked",
            "risk_rating": "low|medium|high|critical",
            "send_back_stage": "builder|tester|reviewer when status is fail",
            "visual_quality_findings": [],
            "reference_match_assessment": "required for UI missions",
            "media_references_used": [],
        })
    elif agent == "visual_qa_reviewer":
        base.update({
            "recommended_owner_decision": "approve_final_release|send_back|pause",
            "visual_acceptance_decision": "approve|send_back|pause",
            "visual_review_notes": [],
            "reference_match_assessment": "clear assessment against owner reference media and UI concept",
            "media_references_used": [],
            "screenshots_reviewed": [],
            "send_back_stage": "frontend_design_implementer|builder|tester when visual evidence fails",
        })
    else:
        base.update({
            "recommended_owner_decision": "approve_final_release|send_back|pause",
            "release_notes": [],
            "changed_files": [],
            "test_evidence": [],
            "visual_acceptance_decision": "approve|send_back|pause for UI missions",
            "visual_review_notes": [],
            "media_references_used": [],
            "pr_url": "pull request URL when changed_files contains releaseable changes",
            "pr_number": "pull request number when changed_files contains releaseable changes",
            "links": {"pr": "pull request URL", "local_preview": "local preview URL if available"},
        })
        if agent == "publisher":
            base.update({
                "expected_revision": "full GitHub PR head SHA after any rebase/repair",
                "tested_revision": "same full SHA that focused tests and checks covered",
                "commit_sha": "published branch HEAD SHA",
            })
    return base


def _agent_execution_ledger(mission, execution_id, started_at):
    return {
        "version": AGENT_RUNNER_VERSION,
        "execution_id": execution_id,
        "mission_id": mission.get("mission_id", ""),
        "title": mission.get("title", ""),
        "started_at": started_at,
        "status": "running",
        "last_progress_at": started_at,
        "quality_gates": [],
        "backflow_events": [],
        "stages": [],
    }


def _mission_agent_sequence(mission):
    mission = mission if isinstance(mission, dict) else {}
    context_pack = mission.get("mission_context_pack") if isinstance(mission.get("mission_context_pack"), dict) else {}
    agent_order = context_pack.get("agent_order") if isinstance(context_pack.get("agent_order"), list) else []
    cleaned = [str(agent or "").strip().lower() for agent in agent_order if str(agent or "").strip().lower() in all_agent_names()]
    return cleaned or agent_sequence_for_mission(mission.get("mission_type", ""), mission.get("raw_text", ""))


def _execution_start_agent(mission, agent_sequence=None):
    agent_sequence = agent_sequence or _mission_agent_sequence(mission)
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    target = str(review_packet.get("return_to_stage") or "").strip().lower()
    stale_resume_hint = bool(target)
    if target in agent_sequence:
        internal_recovery = str(review_packet.get("review_status") or "").strip().lower().startswith("internal_recovery")
        mismatch_recovery = "stage_mismatch" in str(review_packet.get("blocked_reason") or "").lower()
        if internal_recovery or mismatch_recovery:
            workflow = mission.get("agent_workflow") if isinstance(mission.get("agent_workflow"), list) else []
            statuses = {
                str(item.get("agent") or "").strip().lower(): str(item.get("status") or "").strip().lower()
                for item in workflow if isinstance(item, dict)
            }
            target_index = agent_sequence.index(target)
            earlier_incomplete = next((
                agent for agent in agent_sequence[:target_index]
                if agent in statuses and statuses.get(agent) != "complete"
            ), "")
            if earlier_incomplete:
                return earlier_incomplete
        return target
    blocked_agent = str(review_packet.get("blocked_agent") or "").strip().lower()
    stale_resume_hint = stale_resume_hint or bool(blocked_agent)
    if blocked_agent in agent_sequence:
        return blocked_agent
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    stage = str(vault.get("mission_stage") or "").strip().lower()
    stale_resume_hint = stale_resume_hint or stage.startswith(("returned_to_", "blocked_at_"))
    if stage.startswith("returned_to_"):
        target = stage.replace("returned_to_", "", 1)
        if target in agent_sequence:
            return target
    if stage.startswith("blocked_at_"):
        target = stage.replace("blocked_at_", "", 1)
        if target in agent_sequence:
            return target
    resume_agent = _resume_agent_after_completed_stage(stage, agent_sequence)
    if resume_agent:
        return resume_agent
    workflow = mission.get("agent_workflow") if stale_resume_hint and isinstance(mission.get("agent_workflow"), list) else []
    active_agent = next((
        str(item.get("agent") or "").strip().lower()
        for item in workflow
        if isinstance(item, dict)
        and str(item.get("status") or "").strip().lower() == "active"
        and str(item.get("agent") or "").strip().lower() in agent_sequence
    ), "")
    if active_agent:
        return active_agent
    return agent_sequence[0]


def _resume_agent_after_completed_stage(stage, agent_sequence):
    stage = str(stage or "").strip().lower()
    if not stage or stage in {"intake", "blocked"}:
        return ""
    for index, agent in enumerate(agent_sequence or []):
        if str(AGENT_STAGE_MAP.get(agent) or "").strip().lower() != stage:
            continue
        next_index = index + 1
        if next_index < len(agent_sequence):
            return agent_sequence[next_index]
        return agent
    return ""


def _retry_parallel_contract_failure(
    mission,
    execution_id,
    ledger,
    agent,
    artifacts,
    parallel_artifacts,
    output_dir,
    command_base,
    runner,
    timeout_seconds,
    stage_attempts,
    context,
    completed,
    reason,
    missing_keys=None,
    artifact=None,
):
    used = ledger.setdefault("parallel_contract_retry_used", {})
    if used.get(agent):
        return {"retried": False}
    retry_queue = []
    reminder_pending = set()
    _retry_agent_contract_failure(
        ledger,
        retry_queue,
        used,
        reminder_pending,
        agent,
        context.get("attempt", 1),
        reason,
        context.get("started_at") or datetime.now(timezone.utc).isoformat(),
        context["paths"],
        output_dir,
        execution_id,
        missing_keys=missing_keys,
        artifact=artifact,
    )
    stage_attempts[agent] = int(stage_attempts.get(agent, context.get("attempt", 1))) + 1
    retry_paths = _agent_stage_paths(output_dir, execution_id, agent, attempt=stage_attempts[agent])
    prompt = _append_contract_retry_reminder(build_agent_stage_prompt(mission, agent, {**artifacts, **parallel_artifacts}, ledger))
    retry_paths["prompt_path"].write_text(prompt, encoding="utf-8")
    model_assignment = context.get("model_assignment") if isinstance(context.get("model_assignment"), dict) else choose_agent_model(
        agent=agent,
        mission_type=mission.get("mission_type", ""),
        risk_level="high" if _ui_quality_contract_for_mission(mission).get("ui_related") else "medium",
    )
    command = [
        *_readonly_command_base(_agent_command_base(command_base, model_assignment)),
        "--output-last-message",
        str(retry_paths["final_path"]),
        "-",
    ]
    if str(model_assignment.get("runtime_provider") or "").strip().lower() == "anthropic":
        command = _codex_fallback_command(command)
    stage_started = datetime.now(timezone.utc).isoformat()
    _append_ledger_stage(
        ledger,
        agent,
        "running",
        stage_started,
        retry_paths,
        current_action=f"{agent} running read-only parallel contract retry attempt {stage_attempts[agent]}",
        command=command,
        attempt=stage_attempts[agent],
    )
    _write_agent_ledger(output_dir, execution_id, ledger)
    write_runner_heartbeat({
        "status": "parallel_contract_retry_running",
        "mission_id": mission["mission_id"],
        "agent_runner_version": AGENT_RUNNER_VERSION,
        "current_agent": agent,
        "current_action": f"Retrying {agent} after handoff contract failure.",
        "agent_ledger_path": str(output_dir / f"{execution_id}.agent-ledger.json"),
    })
    try:
        retry_completed = runner(
            command,
            input=prompt,
            cwd=str(REPO_ROOT),
            timeout_seconds=min(int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS), AGENT_NO_PROGRESS_TIMEOUT_SECONDS),
            stdout_path=retry_paths["stdout_path"],
            stderr_path=retry_paths["stderr_path"],
            final_path=retry_paths["final_path"],
            mission_id=mission["mission_id"],
            model_assignment=model_assignment,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        retry_completed = _completed_process_from_stage_exception(command, exc, retry_paths)
    retry_context = {
        "agent": agent,
        "paths": retry_paths,
        "started_at": stage_started,
        "command": command,
        "attempt": stage_attempts[agent],
        "model_assignment": model_assignment,
    }
    return {"retried": True, "context": retry_context, "completed": retry_completed}


def _parallel_read_only_prefix(agent_queue):
    if str(env_value("CORE_PARALLEL_READONLY_DISABLED") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return []
    agents = []
    for agent in agent_queue or []:
        if agent in READ_ONLY_PARALLEL_AGENTS:
            agents.append(agent)
            continue
        break
    return agents if len(agents) > 1 else []


def _run_parallel_read_only_agents(
    mission,
    execution_id,
    ledger,
    artifacts,
    agents,
    output_dir,
    command_base,
    runner,
    timeout_seconds,
    stage_attempts,
    database_url=None,
    connect_factory=None,
):
    started_at = datetime.now(timezone.utc).isoformat()
    parallel_artifacts = {}
    futures = {}
    max_workers = max(1, min(int(env_value("CORE_PARALLEL_READONLY_WORKERS", "3") or 3), len(agents)))
    ledger["parallel_planning_execution"] = {
        "version": "charlie_parallel_agent_execution_v1",
        "mode": "read_only_specialists_parallel",
        "agents": list(agents),
        "started_at": started_at,
        "max_workers": max_workers,
        "sandbox": "read-only",
    }
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for agent in agents:
            stage_attempts[agent] = int(stage_attempts.get(agent, 0)) + 1
            _record_execution_stage(
                mission["mission_id"],
                agent,
                "active",
                f"CHARLIE parallel read-only stage started {agent} attempt {stage_attempts[agent]}.",
                database_url=database_url,
                connect_factory=connect_factory,
            )
            stage_paths = _agent_stage_paths(output_dir, execution_id, agent, attempt=stage_attempts[agent])
            prompt = build_agent_stage_prompt(mission, agent, artifacts, ledger)
            stage_paths["prompt_path"].write_text(prompt, encoding="utf-8")
            model_assignment = choose_agent_model(
                agent=agent,
                mission_type=mission.get("mission_type", ""),
                risk_level="high" if _ui_quality_contract_for_mission(mission).get("ui_related") else "medium",
            )
            if _strict_agent_model_routing_required() and not model_assignment.get("runtime_model"):
                result, status_code = _block_agent_stage(
                    mission["mission_id"],
                    execution_id,
                    ledger,
                    agent,
                    stage_paths,
                    SimpleNamespace(returncode=78, stdout="", stderr="Per-agent runtime model is not configured."),
                    datetime.now(timezone.utc).isoformat(),
                    blocked_reason=f"Strict per-agent model routing is enabled, but {agent} has no runtime model configured.",
                    artifact={
                        "summary": "Per-agent model routing is required before this read-only agent can run.",
                        "errors": [f"Missing CHARLIE_AGENT_MODEL_{agent.upper().replace('-', '_')} or CHARLIE_MODEL_<REGISTRY_KEY> env."],
                        "model_assignment": model_assignment,
                        "next_action": "Configure the per-agent or registry model env var, then rerun the mission from this stage.",
                    },
                    artifacts=artifacts,
                    database_url=database_url,
                    connect_factory=connect_factory,
                )
                return {"blocked": True, "result": result, "status_code": status_code}
            command = [
                *_readonly_command_base(_agent_command_base(command_base, model_assignment)),
                "--output-last-message",
                str(stage_paths["final_path"]),
                "-",
            ]
            if str(model_assignment.get("runtime_provider") or "").strip().lower() == "anthropic":
                command = _codex_fallback_command(command)
            stage_started = datetime.now(timezone.utc).isoformat()
            _append_ledger_stage(
                ledger,
                agent,
                "running",
                stage_started,
                stage_paths,
                current_action=f"{agent} running read-only parallel attempt {stage_attempts[agent]}",
                command=command,
                attempt=stage_attempts[agent],
            )
            futures[executor.submit(
                runner,
                command,
                input=prompt,
                cwd=str(REPO_ROOT),
                timeout_seconds=min(int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS), AGENT_NO_PROGRESS_TIMEOUT_SECONDS),
                stdout_path=stage_paths["stdout_path"],
                stderr_path=stage_paths["stderr_path"],
                final_path=stage_paths["final_path"],
                mission_id=mission["mission_id"],
                model_assignment=model_assignment,
            )] = {
                "agent": agent,
                "paths": stage_paths,
                "started_at": stage_started,
                "command": command,
                "attempt": stage_attempts[agent],
                "model_assignment": model_assignment,
            }
        _write_agent_ledger(output_dir, execution_id, ledger)
        write_runner_heartbeat({
            "status": "parallel_read_only_agents_running",
            "mission_id": mission["mission_id"],
            "agent_runner_version": AGENT_RUNNER_VERSION,
            "current_agent": "parallel_planning",
            "current_action": f"Running read-only agents in parallel: {', '.join(agents)}",
            "agent_ledger_path": str(output_dir / f"{execution_id}.agent-ledger.json"),
        })

        completed_by_agent = {}
        for future in as_completed(futures):
            context = futures[future]
            try:
                completed = future.result()
            except (subprocess.TimeoutExpired, OSError) as exc:
                completed = _completed_process_from_stage_exception(context["command"], exc, context["paths"])
            completed_by_agent[context["agent"]] = (context, completed)

    for agent in agents:
        context, completed = completed_by_agent[agent]
        paths = context["paths"]
        _write_process_text(paths["stdout_path"], completed.stdout or "")
        _write_process_text(paths["stderr_path"], completed.stderr or "")
        final_message = _read_text(paths["final_path"]) or (completed.stdout or "").strip()
        if final_message and not _read_text(paths["final_path"]):
            _write_process_text(paths["final_path"], final_message)
        if completed.returncode != 0:
            result, status_code = _block_agent_stage(
                mission["mission_id"],
                execution_id,
                ledger,
                agent,
                paths,
                completed,
                context["started_at"],
                blocked_reason="Parallel read-only agent did not produce a valid final artifact.",
                artifacts={**artifacts, **parallel_artifacts},
                database_url=database_url,
                connect_factory=connect_factory,
            )
            return {"blocked": True, "result": result, "status_code": status_code}
        if not _read_text(paths["final_path"]):
            retry = _retry_parallel_contract_failure(
                mission,
                execution_id,
                ledger,
                agent,
                artifacts,
                parallel_artifacts,
                output_dir,
                command_base,
                runner,
                timeout_seconds,
                stage_attempts,
                context,
                completed,
                reason="missing_final_artifact",
            )
            if retry.get("retried"):
                context = retry["context"]
                completed = retry["completed"]
                paths = context["paths"]
                final_message = _read_text(paths["final_path"]) or (completed.stdout or "").strip()
                if final_message and not _read_text(paths["final_path"]):
                    _write_process_text(paths["final_path"], final_message)
            if completed.returncode != 0 or not _read_text(paths["final_path"]):
                result, status_code = _block_agent_stage(
                    mission["mission_id"],
                    execution_id,
                    ledger,
                    agent,
                    paths,
                    completed,
                    context["started_at"],
                    blocked_reason="Parallel read-only agent did not produce a valid final artifact after contract retry.",
                    artifact={"contract_retry_exhausted": True, "first_attempt_artifact_path": _first_contract_retry_artifact_path(ledger, agent)},
                    artifacts={**artifacts, **parallel_artifacts},
                    database_url=database_url,
                    connect_factory=connect_factory,
                )
                return {"blocked": True, "result": result, "status_code": status_code}
        artifact = _agent_artifact_from_final(agent, _read_text(paths["final_path"]))
        artifact.update({
            "agent": agent,
            "parallel_mode": "read_only",
            "artifact_path": str(paths["final_path"]),
            "stdout_path": str(paths["stdout_path"]),
            "stderr_path": str(paths["stderr_path"]),
            "stdout_tail": _tail_text(completed.stdout or _read_text(paths["stdout_path"]), 1200),
            "stderr_tail": _tail_text(completed.stderr or _read_text(paths["stderr_path"]), 1200),
            "attempt": context["attempt"],
            "model_assignment": context.get("model_assignment") or choose_agent_model(
                agent=agent,
                mission_type=mission.get("mission_type", ""),
                risk_level="high" if _ui_quality_contract_for_mission(mission).get("ui_related") else "medium",
            ),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        validation = _validate_agent_artifact(agent, artifact)
        if not validation["valid"]:
            retry = _retry_parallel_contract_failure(
                mission,
                execution_id,
                ledger,
                agent,
                artifacts,
                parallel_artifacts,
                output_dir,
                command_base,
                runner,
                timeout_seconds,
                stage_attempts,
                context,
                completed,
                reason="missing_required_keys",
                missing_keys=validation["missing_keys"],
                artifact=artifact,
            )
            if retry.get("retried"):
                context = retry["context"]
                completed = retry["completed"]
                paths = context["paths"]
                _write_process_text(paths["stdout_path"], completed.stdout or "")
                _write_process_text(paths["stderr_path"], completed.stderr or "")
                final_message = _read_text(paths["final_path"]) or (completed.stdout or "").strip()
                if final_message and not _read_text(paths["final_path"]):
                    _write_process_text(paths["final_path"], final_message)
                artifact = _agent_artifact_from_final(agent, _read_text(paths["final_path"]))
                artifact.update({
                    "agent": agent,
                    "parallel_mode": "read_only",
                    "artifact_path": str(paths["final_path"]),
                    "stdout_path": str(paths["stdout_path"]),
                    "stderr_path": str(paths["stderr_path"]),
                    "stdout_tail": _tail_text(completed.stdout or _read_text(paths["stdout_path"]), 1200),
                    "stderr_tail": _tail_text(completed.stderr or _read_text(paths["stderr_path"]), 1200),
                    "attempt": context["attempt"],
                    "model_assignment": context.get("model_assignment") or choose_agent_model(
                        agent=agent,
                        mission_type=mission.get("mission_type", ""),
                        risk_level="high" if _ui_quality_contract_for_mission(mission).get("ui_related") else "medium",
                    ),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })
                validation = _validate_agent_artifact(agent, artifact)
            if validation["valid"]:
                pass
            else:
                artifact["contract_retry_exhausted"] = True
                artifact["first_attempt_artifact_path"] = _first_contract_retry_artifact_path(ledger, agent)
                result, status_code = _block_agent_stage(
                    mission["mission_id"],
                    execution_id,
                    ledger,
                    agent,
                    paths,
                    completed,
                    context["started_at"],
                    blocked_reason=f"Parallel read-only artifact missing required keys after contract retry: {', '.join(validation['missing_keys'])}.",
                    artifact=artifact,
                    artifacts={**artifacts, **parallel_artifacts},
                    database_url=database_url,
                    connect_factory=connect_factory,
                )
                return {"blocked": True, "result": result, "status_code": status_code}
        manifest_artifacts = {**artifacts, **parallel_artifacts, agent: artifact}
        artifact = bind_artifact_to_candidate(
            artifact,
            agent,
            execution_id,
            context["attempt"],
            build_candidate_manifest(mission, manifest_artifacts, source_commit=_release_candidate_revision_sha(mission, manifest_artifacts)),
            previous_artifact=artifacts.get(agent),
        )
        quality = _parallel_read_only_quality_gate(agent, artifact)
        if not quality["passed"]:
            result, status_code = _block_agent_stage(
                mission["mission_id"],
                execution_id,
                ledger,
                agent,
                paths,
                completed,
                context["started_at"],
                blocked_reason=f"Parallel read-only quality gate failed: {quality['reason']}",
                artifact={**artifact, "quality_gate": quality},
                artifacts={**artifacts, **parallel_artifacts, agent: {**artifact, "quality_gate": quality}},
                database_url=database_url,
                connect_factory=connect_factory,
            )
            return {"blocked": True, "result": result, "status_code": status_code}
        artifact["quality_gate"] = quality
        artifact["handoff_report"] = _build_handoff_report(mission, agent, artifact, ledger)
        parallel_artifacts[agent] = artifact
        _append_ledger_stage(
            ledger,
            agent,
            "complete",
            context["started_at"],
            paths,
            artifact=artifact,
            command=context["command"],
            attempt=context["attempt"],
        )
        _record_mission_memory_event(
            mission,
            build_memory_event(agent, "parallel_agent_complete", attempt=context["attempt"], artifact=artifact, quality_gate=quality),
            database_url=database_url,
            connect_factory=connect_factory,
        )
        _record_execution_stage(
            mission["mission_id"],
            agent,
            "complete",
            _truncate(artifact.get("summary") or f"{agent} completed in parallel read-only mode.", 1000),
            database_url=database_url,
            connect_factory=connect_factory,
        )
        _write_agent_ledger(output_dir, execution_id, ledger)
        write_runner_heartbeat({
            "status": "parallel_agent_complete",
            "mission_id": mission["mission_id"],
            "agent_runner_version": AGENT_RUNNER_VERSION,
            "current_agent": agent,
            "current_action": f"{agent} completed read-only parallel handoff.",
            "execution_artifact": str(paths["final_path"]),
            "agent_ledger_path": str(output_dir / f"{execution_id}.agent-ledger.json"),
        })
    completed_at = datetime.now(timezone.utc).isoformat()
    ledger["parallel_planning_execution"]["completed_at"] = completed_at
    ledger["parallel_planning_execution"]["status"] = "complete"
    _write_agent_ledger(output_dir, execution_id, ledger)
    write_runner_heartbeat({
        "status": "parallel_read_only_agents_complete",
        "mission_id": mission["mission_id"],
        "agent_runner_version": AGENT_RUNNER_VERSION,
        "current_agent": "parallel_planning",
        "current_action": f"Completed read-only agents in parallel: {', '.join(agents)}",
        "agent_ledger_path": str(output_dir / f"{execution_id}.agent-ledger.json"),
    })
    return {
        "blocked": False,
        "artifacts": parallel_artifacts,
        "parallel_execution": ledger.get("parallel_planning_execution", {}),
    }


def _parallel_read_only_quality_gate(agent, artifact):
    if _risk_agent_has_present_red_zone_violation(agent, artifact):
        present_quality = _agent_quality_gate(agent, artifact)
        if not present_quality.get("passed"):
            return present_quality
        return {
            "passed": False,
            "reason": "risk_agent recorded a present red-zone authority violation.",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    if _risk_agent_findings_belong_to_downstream_planning(agent, artifact):
        return {
            "passed": True,
            "reason": "parallel_read_only_deferred_planning_risk",
            "deferred_blocker": True,
            "deferred_reason": "Risk findings were assigned to downstream Council, Planner, Architect, or Builder stages.",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    quality = _agent_quality_gate(agent, artifact)
    if quality.get("passed"):
        return quality
    if _risk_agent_findings_belong_to_downstream_planning(agent, artifact):
        return {
            "passed": True,
            "reason": f"parallel_read_only_deferred_planning_risk: {quality.get('reason', '')}",
            "deferred_blocker": True,
            "deferred_reason": quality.get("reason", ""),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    if _read_only_block_is_downstream_evidence_only(agent, artifact, quality):
        return {
            "passed": True,
            "reason": f"parallel_read_only_deferred_evidence_warning: {quality.get('reason', '')}",
            "deferred_blocker": True,
            "deferred_reason": quality.get("reason", ""),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    return quality


def _risk_agent_findings_belong_to_downstream_planning(agent, artifact):
    if agent != "risk_agent" or not isinstance(artifact, dict):
        return False
    changed_files = artifact.get("changed_files") if isinstance(artifact.get("changed_files"), list) else []
    if _has_release_relevant_changes(changed_files):
        return False
    text = " ".join(
        str(value or "")
        for value in [
            artifact.get("summary"),
            artifact.get("next_action"),
            artifact.get("recommended_owner_decision"),
            *_artifact_value_list(artifact.get("risks")),
            *_artifact_value_list(artifact.get("risk_notes")),
            *_artifact_value_list(artifact.get("bugs")),
            *_artifact_value_list(artifact.get("errors")),
            *_artifact_value_list(artifact.get("required_mitigations")),
        ]
    ).lower()
    if _risk_agent_has_present_red_zone_violation(agent, artifact):
        return False
    downstream_terms = (
        "council",
        "planner",
        "architect",
        "builder",
        "must implement",
        "should implement",
        "add negative tests",
        "acceptance tests",
        "mandatory mitigations",
        "before owner review",
    )
    return any(term in text for term in downstream_terms)


def _risk_agent_has_present_red_zone_violation(agent, artifact):
    if agent != "risk_agent" or not isinstance(artifact, dict):
        return False
    text = " ".join(
        str(value or "")
        for value in [
            artifact.get("summary"),
            artifact.get("next_action"),
            *_artifact_value_list(artifact.get("risks")),
            *_artifact_value_list(artifact.get("risk_notes")),
            *_artifact_value_list(artifact.get("bugs")),
            *_artifact_value_list(artifact.get("errors")),
        ]
    ).lower()
    present_violation_terms = (
        "attempted production data write",
        "production data write without owner",
        "attempted customer send",
        "unauthorized customer send",
        "attempted public post",
        "payment without owner",
        "attempted payment",
        "reserve stock without owner",
        "attempted reserve stock",
        "attempted merge",
        "attempted deploy",
        "attempted migration",
        "secret leak",
        "credentials exposed",
    )
    return any(term in text for term in present_violation_terms)


def _read_only_block_is_downstream_evidence_only(agent, artifact, quality):
    if agent not in {"risk_agent", "product_architect", "technical_architect", "business_model_agent"}:
        return False
    blocking_errors = _blocking_artifact_items(agent, artifact, artifact.get("errors") if isinstance(artifact.get("errors"), list) else [])
    if blocking_errors and not _read_only_errors_are_environment_only(agent, artifact, blocking_errors):
        return False
    if _blocking_artifact_items(agent, artifact, artifact.get("bugs") if isinstance(artifact.get("bugs"), list) else []):
        return False
    changed_files = artifact.get("changed_files") if isinstance(artifact.get("changed_files"), list) else []
    if any(str(item or "").strip() and str(item or "").strip() != "No changed files detected by git diff." for item in changed_files):
        return False
    text = " ".join(
        str(value or "")
        for value in [
            quality.get("reason"),
            artifact.get("summary"),
            artifact.get("next_action"),
            artifact.get("recommended_owner_decision"),
            artifact.get("quality_gate", {}).get("reason") if isinstance(artifact.get("quality_gate"), dict) else "",
            *_artifact_value_list(artifact.get("risks")),
            *_artifact_value_list(artifact.get("risk_notes")),
            *_artifact_value_list(artifact.get("warnings")),
            *_artifact_value_list(artifact.get("required_mitigations")),
            *_artifact_value_list(artifact.get("test_evidence")),
        ]
    ).lower()
    future_terms = (
        "downstream",
        "later agent",
        "later stage",
        "final artifact",
        "final-artifact",
        "test evidence",
        "review packet",
        "review-packet",
        "owner review",
        "pr_ready",
        "persistence",
        "persisted",
        "cannot certify",
        "cannot be certified",
        "not yet",
        "timeout",
        "timed out",
        "no pass/fail claim",
        "no pass fail claim",
    )
    present_violation_terms = (
        "red-zone",
        "red zone",
        "attempted production data write",
        "unauthorized production data write",
        "production data write without owner",
        "attempted customer send",
        "unauthorized customer send",
        "public post without owner",
        "attempted public post",
        "payment without owner",
        "attempted payment",
        "reserve stock without owner",
        "attempted reserve stock",
        "merge without owner",
        "attempted merge",
        "deploy without owner",
        "attempted deploy",
        "migration without owner",
        "attempted migration",
        "secret leak",
        "security vulnerability",
        "out-of-scope change",
        "unauthorized",
    )
    present_text = text
    for safe_phrase in (
        "no present red-zone action",
        "no present red zone action",
        "no present red-zone violation",
        "no present red zone violation",
        "no red-zone action",
        "no red zone action",
        "no red-zone violation",
        "no red zone violation",
        "no present scope/safety violation",
        "no present violation",
    ):
        present_text = present_text.replace(safe_phrase, "")
    return any(term in text for term in future_terms) and not any(term in present_text for term in present_violation_terms)


def _read_only_errors_are_environment_only(agent, artifact, errors):
    if agent != "risk_agent":
        return False
    text = " ".join(_artifact_text(item).lower() for item in _artifact_value_list(errors))
    context = " ".join(
        str(value or "").lower()
        for value in [
            artifact.get("summary"),
            artifact.get("confidence_reason"),
            artifact.get("next_action"),
            artifact.get("stdout_tail"),
            artifact.get("stderr_tail"),
            *_artifact_value_list(artifact.get("test_evidence")),
        ]
    )
    environment_terms = (
        "read-only",
        "read only",
        "no usable temporary directory",
        "tempdir",
        "temporary directory",
        "permissionerror",
        "permission denied",
        "write denial",
        ".charlie_runner",
    )
    non_regression_terms = (
        "not a proven code regression",
        "not a proven present",
        "rather than asserted product defects",
        "environment constraints",
        "environment-blocked",
    )
    return any(term in text or term in context for term in environment_terms) and any(
        term in text or term in context for term in non_regression_terms
    )


def _readonly_command_base(command_base):
    command = list(command_base or [])
    for index, item in enumerate(command[:-1]):
        if item == "--sandbox":
            command[index + 1] = "read-only"
            return command
    return [*command, "--sandbox", "read-only"]


def _agent_command_base(command_base, model_assignment):
    command = list(command_base or [])
    model_assignment = model_assignment if isinstance(model_assignment, dict) else {}
    runtime_model = str(model_assignment.get("runtime_model") or "").strip()
    if not runtime_model:
        return command
    for flag in ("--model", "-m"):
        if flag in command:
            index = command.index(flag)
            if index + 1 < len(command):
                updated = list(command)
                updated[index + 1] = runtime_model
                return updated
            return [*command, runtime_model]
    return [*command, "--model", runtime_model]


def _strict_agent_model_routing_required():
    return str(env_value("CORE_REQUIRE_AGENT_MODEL_ROUTING", "")).strip().lower() in {"1", "true", "yes", "on"}


def _existing_agent_artifacts_for_rerun(mission, start_agent, agent_sequence=None):
    agent_sequence = agent_sequence or _mission_agent_sequence(mission)
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    existing = review_packet.get("agent_artifacts") if isinstance(review_packet.get("agent_artifacts"), dict) else {}
    if start_agent not in agent_sequence:
        return {}
    start_index = agent_sequence.index(start_agent)
    targeted = metadata.get("targeted_invalidation") if isinstance(metadata.get("targeted_invalidation"), dict) else {}
    explicitly_preserved = set(targeted.get("preserved_agents") or [])
    preserved = {
        agent: artifact
        for agent, artifact in existing.items()
        if agent in agent_sequence
        and (agent_sequence.index(agent) < start_index or agent in explicitly_preserved)
        and isinstance(artifact, dict)
    }
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    for report in vault.get("handoff_reports") or []:
        if not isinstance(report, dict):
            continue
        agent = str(report.get("agent") or "").strip().lower()
        if (
            not agent
            or agent in preserved
            or agent not in agent_sequence
            or agent_sequence.index(agent) >= start_index
        ):
            continue
        preserved[agent] = {
            "summary": report.get("summary") or report.get("task") or f"{agent} completed in earlier runner pass.",
            "status": report.get("pass_fail_status") or report.get("status") or "complete",
            "handoff_report": report,
            "vault_sources_used": report.get("inputs_used") or ["mission_vault"],
            "files_inspected": report.get("files_changed") or [],
            "commands_run": report.get("tests_run") or [],
            "changed_files": report.get("files_changed") or [],
            "confidence": report.get("confidence") or "96%",
            "confidence_reason": "Recovered from mission vault handoff report during runner resume.",
        }
    # Durable cross-session recovery: mission memory persists each agent's last
    # completed work in metadata (survives new runner sessions). When the review
    # packet / vault handoff reports have lost an upstream artifact, recover it
    # here so a resumed downstream agent (e.g. qa_red_team) is never handed an
    # empty previous_agent_artifacts and forced to re-block work that already
    # passed. Additive only: never overwrites an artifact already preserved above.
    memory = mission_memory_from_metadata(metadata)
    done_locks = memory.get("done_locks") if isinstance(memory.get("done_locks"), dict) else {}
    latest_by_agent = memory.get("latest_by_agent") if isinstance(memory.get("latest_by_agent"), dict) else {}
    durable_artifacts = {**latest_by_agent, **done_locks}
    for agent, event in durable_artifacts.items():
        agent = str(agent or "").strip().lower()
        if (
            not agent
            or agent in preserved
            or agent not in agent_sequence
            or agent_sequence.index(agent) >= start_index
            or not isinstance(event, dict)
        ):
            continue
        if (
            str(event.get("type") or "").strip().lower() not in {"agent_complete", "parallel_agent_complete"}
            and str(event.get("done_lock_version") or "").strip() != "charlie_done_lock_v1"
        ):
            continue
        preserved[agent] = {
            "summary": event.get("summary") or f"{agent} completed in an earlier runner session.",
            "status": "complete",
            "vault_sources_used": event.get("vault_sources_used") or ["mission_memory"],
            "files_inspected": event.get("files_inspected") or [],
            "commands_run": event.get("commands_run") or [],
            "changed_files": event.get("changed_files") or [],
            "test_evidence": event.get("tests_run") or [],
            "quality_gate": event.get("quality_gate") or {},
            "next_action": event.get("next_action") or "",
            "pr_url": event.get("pr_url") or "",
            "pr_number": event.get("pr_number") or "",
            "branch_name": event.get("branch_name") or "",
            "commit_sha": event.get("commit_sha") or "",
            "links": {"pr": event.get("pr_url") or ""},
            "confidence": event.get("confidence") or "96%",
            "confidence_reason": (
                event.get("confidence_reason")
                or "Recovered from durable mission memory during cross-session runner resume."
            ),
            "done_lock": str(event.get("done_lock_version") or "").strip() == "charlie_done_lock_v1",
            "recovered_from": "mission_memory_done_locks" if event.get("done_lock_version") else "mission_memory_latest_by_agent",
        }
    return preserved


def _agent_stage_paths(output_dir, execution_id, agent, attempt=1):
    suffix = f".attempt{attempt}" if int(attempt or 1) > 1 else ""
    stem = f"{execution_id}.{agent}{suffix}"
    return {
        "prompt_path": output_dir / f"{stem}.prompt.md",
        "stdout_path": output_dir / f"{stem}.stdout.txt",
        "stderr_path": output_dir / f"{stem}.stderr.txt",
        "final_path": output_dir / f"{stem}.final.md",
    }


def _append_ledger_stage(ledger, agent, status, started_at, paths, artifact=None, current_action="", command=None, attempt=1):
    stages = ledger.setdefault("stages", [])
    existing = next((item for item in stages if item.get("agent") == agent and int(item.get("attempt") or 1) == int(attempt or 1)), None)
    item = existing or {"agent": agent}
    updated_at = datetime.now(timezone.utc).isoformat()
    item.update({
        "status": status,
        "attempt": int(attempt or 1),
        "started_at": started_at,
        "updated_at": updated_at,
        "current_action": current_action,
        "command": _display_command(command),
        "prompt_path": str(paths["prompt_path"]),
        "stdout_path": str(paths["stdout_path"]),
        "stderr_path": str(paths["stderr_path"]),
        "final_path": str(paths["final_path"]),
    })
    if artifact:
        item["artifact"] = artifact
        item["files_inspected"] = artifact.get("files_inspected", [])
        item["commands_run"] = artifact.get("commands_run", [])
        item["changed_files"] = artifact.get("changed_files", [])
        item["stdout_tail"] = artifact.get("stdout_tail", "")
        item["stderr_tail"] = artifact.get("stderr_tail", "")
        item["quality_gate"] = artifact.get("quality_gate", {})
        item["changed_files_count"] = len(item["changed_files"])
        if item["quality_gate"]:
            gates = ledger.setdefault("quality_gates", [])
            gates = [gate for gate in gates if not (gate.get("agent") == agent and int(gate.get("attempt") or 1) == int(attempt or 1))]
            gates.append({"agent": agent, "attempt": int(attempt or 1), **item["quality_gate"]})
            ledger["quality_gates"] = gates
    if status not in {"running", "active", "in_progress"}:
        item["completed_at"] = updated_at
        try:
            start_value = datetime.fromisoformat(str(started_at or "").replace("Z", "+00:00"))
            end_value = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            item["duration_seconds"] = max(0, int((end_value - start_value).total_seconds()))
        except (TypeError, ValueError):
            pass
    if existing is None:
        stages.append(item)
    ledger["status"] = "running" if status == "running" else ledger.get("status", "running")
    ledger["last_progress_at"] = item["updated_at"]
    return ledger


def _write_agent_ledger(output_dir, execution_id, ledger):
    path = Path(output_dir) / f"{execution_id}.agent-ledger.json"
    _write_text_with_retry(path, json.dumps(ledger, indent=2))
    return path


def _write_process_text(path, text):
    path = Path(path)
    try:
        _write_text_with_retry(path, text or "")
        return {"success": True, "path": str(path)}
    except PermissionError as exc:
        fallback = path.with_name(f"{path.stem}.recovered{path.suffix}")
        _write_text_with_retry(fallback, text or "")
        return {
            "success": False,
            "path": str(path),
            "fallback_path": str(fallback),
            "error_type": exc.__class__.__name__,
        }


def _write_text_with_retry(path, text, attempts=3, delay_seconds=2):
    path = Path(path)
    last_error = None
    for attempt in range(1, max(int(attempts or 1), 1) + 1):
        try:
            path.write_text(text or "", encoding="utf-8")
            return
        except PermissionError as exc:
            last_error = exc
            if attempt >= max(int(attempts or 1), 1):
                raise
            time.sleep(delay_seconds)
    if last_error:
        raise last_error


def _append_contract_retry_reminder(prompt):
    return (
        f"{prompt}\n\n"
        "CHARLIE CONTRACT REMINDER: Your previous attempt failed the handoff contract. "
        "Return only one complete, compact JSON object in a single ```json code block. "
        "Do not include any prose outside the JSON block. Put the required keys first and keep every string concise so the object closes before the output limit. "
        "Use this exact key order: summary, errors, bugs, vault_sources_used, confidence, confidence_reason, commands_run, files_inspected, recommended_owner_decision, release_notes, changed_files, test_evidence, stdout_tail, stderr_tail, next_action, vault_updates, no_vault_update_required. "
        "Length caps: summary under 90 words, confidence_reason under 45 words, bugs/errors/release_notes/test_evidence max 3 items each, vault_sources_used/files_inspected/commands_run max 8 items each. "
        "If details are long, summarize them instead of listing everything."
    )


def _retry_agent_contract_failure(
    ledger,
    agent_queue,
    contract_retry_used,
    contract_reminder_pending,
    agent,
    attempt,
    reason,
    stage_started,
    stage_paths,
    output_dir,
    execution_id,
    missing_keys=None,
    artifact=None,
):
    if contract_retry_used.get(agent):
        return False
    contract_retry_used[agent] = True
    contract_reminder_pending.add(agent)
    entry = {
        "agent": agent,
        "failed_attempt": int(attempt or 1),
        "reason": reason,
        "missing_keys": list(missing_keys or []),
        "failed_artifact_path": str(stage_paths["final_path"]),
        "stdout_path": str(stage_paths["stdout_path"]),
        "stderr_path": str(stage_paths["stderr_path"]),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    if isinstance(artifact, dict) and artifact:
        entry["artifact_summary"] = _truncate(artifact.get("summary") or "", 500)
        entry["contract_parse_fallback"] = bool(artifact.get("contract_parse_fallback"))
    ledger.setdefault("contract_retries", []).append(entry)
    _append_ledger_stage(
        ledger,
        agent,
        "contract_retry",
        stage_started,
        stage_paths,
        current_action=f"{agent} attempt {attempt} failed the handoff contract; retrying once with a strict reminder.",
        artifact={
            "summary": f"{agent} failed the handoff contract and will retry once.",
            "contract_failure_reason": reason,
            "missing_keys": list(missing_keys or []),
            "artifact_path": str(stage_paths["final_path"]),
        },
        attempt=attempt,
    )
    _write_agent_ledger(output_dir, execution_id, ledger)
    agent_queue.insert(0, agent)
    return True


def _first_contract_retry_artifact_path(ledger, agent):
    for entry in ledger.get("contract_retries", []) if isinstance(ledger, dict) else []:
        if isinstance(entry, dict) and entry.get("agent") == agent:
            return entry.get("failed_artifact_path", "")
    return ""


def _agent_artifact_from_final(agent, final_message):
    parsed = _extract_json_object(final_message)
    if parsed:
        return _normalize_agent_artifact(agent, parsed, final_message)
    artifact = {
        "summary": _truncate(final_message or f"{agent} completed.", 1200),
        "contract_parse_fallback": True,
        "errors": _extract_errors(final_message),
        "bugs": [],
        "files_inspected": _extract_file_mentions(final_message),
        "commands_run": _extract_command_mentions(final_message),
        "stdout_tail": "",
        "stderr_tail": "",
        "next_action": "Continue to next CHARLIE agent.",
    }
    if agent == "idea_expander":
        artifact.update({"opportunity": artifact["summary"], "owner_value": artifact["summary"], "non_goals": []})
    elif agent == "visual_reference_interpreter":
        artifact.update({
            "media_references_used": [],
            "layout_requirements": [artifact["summary"]],
            "visual_hierarchy": [],
            "interaction_clues": [],
            "reference_match_checklist": [],
            "non_negotiable_visual_elements": [],
        })
    elif agent == "creative_ui_designer":
        artifact.update({
            "ui_concept": artifact["summary"],
            "layout_system": [],
            "visual_direction": [],
            "component_requirements": [],
            "design_requirements": [artifact["summary"]],
            "what_not_to_do": ["Do not only change colors."],
        })
    elif agent == "ux_interaction_designer":
        artifact.update({
            "primary_workflows": [artifact["summary"]],
            "owner_actions": [],
            "responsive_behavior": [],
            "interaction_requirements": [],
            "empty_loading_error_states": [],
        })
    elif agent == "source_mapper":
        artifact.update({
            "implementation_inventory": [artifact["summary"]],
            "current_sources": [],
            "legacy_sources": [],
            "routes_found": [],
            "tests_to_run": [],
            "migrations_found": [],
            "implementation_sources_used": [],
            "source_truth_summary": artifact["summary"],
        })
    elif agent == "product_architect":
        artifact.update({"user_flow": [artifact["summary"]], "acceptance_boundaries": [], "risk_notes": []})
    elif agent == "council_synthesis":
        artifact.update({"agreements": [artifact["summary"]], "conflicts_resolved": [], "unresolved_blockers": [], "build_brief": artifact["summary"], "acceptance_priorities": []})
    elif agent == "planner":
        artifact.update({"acceptance_criteria": ["Review final artifact."], "test_plan": ["Run focused verification."], "scope": artifact["summary"]})
    elif agent == "architect":
        artifact.update({"files_to_inspect": _changed_files(), "risk_notes": [], "implementation_plan": [artifact["summary"]]})
    elif agent == "builder":
        artifact.update({"changed_files": _changed_files(), "build_notes": [artifact["summary"]]})
    elif agent == "frontend_design_implementer":
        artifact.update({
            "changed_files": _changed_files(),
            "implementation_notes": [artifact["summary"]],
            "local_preview": {"url": ""},
            "media_references_used": [],
            "visual_reference_analysis": "",
            "viewport_plan": [],
            "browser_check_plan": [],
            "design_requirements_met": [],
            "known_visual_gaps": [],
        })
    elif agent == "tester":
        artifact.update({"tests_run": _extract_test_evidence(final_message), "test_status": "pass" if not artifact["errors"] else "blocked"})
    elif agent == "qa_red_team":
        artifact.update({"qa_findings": [artifact["summary"]], "red_team_status": "pass" if not artifact["errors"] else "blocked", "risk_rating": "low" if not artifact["errors"] else "high"})
    elif agent == "visual_qa_reviewer":
        artifact.update({
            "recommended_owner_decision": "send_back",
            "visual_acceptance_decision": "pause" if artifact["errors"] else "approve",
            "visual_review_notes": [artifact["summary"]],
            "reference_match_assessment": artifact["summary"],
            "media_references_used": [],
            "screenshots_reviewed": [],
            "send_back_stage": "frontend_design_implementer",
        })
    else:
        artifact.update({
            "recommended_owner_decision": "send_back" if agent in REVIEW_DECISION_AGENTS else "approve_final_release",
            "release_notes": ["Review PR and test evidence before final approval."],
            "changed_files": _changed_files(),
            "test_evidence": _extract_test_evidence(final_message),
        })
    return artifact


def _normalize_agent_artifact(agent, artifact, final_message=""):
    artifact = dict(artifact or {})
    required = AGENT_ARTIFACT_REQUIRED_KEYS.get(agent, [])
    if "commands_run" in required and "commands_run" not in artifact:
        artifact["commands_run"] = []
    if agent == "qa_red_team":
        findings = artifact.get("qa_findings")
        if not isinstance(findings, list) or not findings:
            bugs = artifact.get("bugs") if isinstance(artifact.get("bugs"), list) else []
            errors = artifact.get("errors") if isinstance(artifact.get("errors"), list) else []
            summary = artifact.get("summary")
            artifact["qa_findings"] = [*bugs, *errors] or ([summary] if summary else [])
        if not artifact.get("red_team_status"):
            decision_text = " ".join(
                str(value or "").lower()
                for value in [
                    artifact.get("recommended_owner_decision"),
                    artifact.get("summary"),
                    artifact.get("next_action"),
                ]
            )
            has_blocker = bool(artifact.get("bugs") or artifact.get("errors")) or any(
                term in decision_text for term in ("pause", "send back", "blocked", "blocker")
            )
            artifact["red_team_status"] = "blocked" if has_blocker else "pass"
        if not artifact.get("risk_rating"):
            artifact["risk_rating"] = "high" if artifact.get("red_team_status") == "blocked" else "low"
    if agent != "council_synthesis":
        return artifact
    summary = _truncate(artifact.get("summary") or final_message or "Council synthesis completed.", 1200)
    next_action = _truncate(artifact.get("next_action") or "", 900)
    if not artifact.get("agreements"):
        artifact["agreements"] = [summary]
    if not artifact.get("conflicts_resolved"):
        artifact["conflicts_resolved"] = ["No council conflicts were recorded in the parsed artifact."]
    if "unresolved_blockers" not in artifact:
        artifact["unresolved_blockers"] = []
    if not artifact.get("build_brief"):
        brief_parts = [summary]
        if next_action:
            brief_parts.append(f"Next action: {next_action}")
        artifact["build_brief"] = "\n\n".join(brief_parts)
    if not artifact.get("acceptance_priorities"):
        criteria = artifact.get("acceptance_criteria")
        artifact["acceptance_priorities"] = criteria[:6] if isinstance(criteria, list) else []
    return artifact


def _extract_json_object(text):
    text = str(text or "")
    candidates = []
    for match in re.finditer(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE):
        block = str(match.group(1) or "").strip()
        if "{" in block and "}" in block:
            candidates.append(block[block.find("{"):block.rfind("}") + 1])
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{"):text.rfind("}") + 1])
    for candidate in candidates:
        for repaired in (candidate, re.sub(r",\s*([}\]])", r"\1", candidate)):
            try:
                parsed = json.loads(repaired)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return {}


def _validate_agent_artifact(agent, artifact):
    required = list(AGENT_ARTIFACT_REQUIRED_KEYS.get(agent, ["summary"]))
    for key in AGENT_CONFIDENCE_REQUIRED_KEYS:
        if key not in required:
            required.append(key)
    allow_empty = AGENT_ARTIFACT_ALLOW_EMPTY_KEYS.get(agent, set())
    missing = []
    for key in required:
        if key not in artifact or artifact.get(key) is None:
            missing.append(key)
            continue
        if key in allow_empty:
            continue
        value = artifact.get(key)
        if value == "" or value == [] or value == {}:
            missing.append(key)
    if agent == "reviewer":
        decision = str(artifact.get("recommended_owner_decision") or "").strip().lower()
        if decision in {"approve", "approve_final", "approve_final_release"} and not artifact.get("release_notes"):
            missing.append("release_notes")
    return {"valid": not missing, "missing_keys": missing}


def _agent_quality_gate(agent, artifact):
    errors = artifact.get("errors") if isinstance(artifact.get("errors"), list) else []
    bugs = artifact.get("bugs") if isinstance(artifact.get("bugs"), list) else []
    errors = _blocking_artifact_items(agent, artifact, errors)
    bugs = _blocking_artifact_items(agent, artifact, bugs)
    commands = artifact.get("commands_run") if isinstance(artifact.get("commands_run"), list) else []
    inspected = artifact.get("files_inspected") if isinstance(artifact.get("files_inspected"), list) else []
    vault_sources = _artifact_vault_sources(artifact)
    confidence_quality = _artifact_confidence_quality_gate(agent, artifact)
    if not confidence_quality["passed"]:
        return confidence_quality
    revision_quality = _revision_evidence_quality_gate(agent, artifact)
    if not revision_quality["passed"]:
        return revision_quality
    if not commands and not _read_only_reviewer_has_upstream_evidence(agent, artifact):
        return {"passed": False, "reason": f"{agent} did not record commands_run evidence."}
    if not inspected:
        return {"passed": False, "reason": f"{agent} did not record files_inspected evidence."}
    if not vault_sources:
        return {"passed": False, "reason": f"{agent} did not record Vault Brain sources used."}
    if not _artifact_has_vault_brain_source(artifact):
        return {"passed": False, "reason": f"{agent} did not cite Vault Brain sources from docs/09-vault-brain."}
    implementation_quality = _implementation_source_quality_gate(agent, artifact)
    if not implementation_quality["passed"]:
        return implementation_quality
    ui_quality = _ui_agent_quality_gate(agent, artifact)
    if not ui_quality["passed"]:
        return ui_quality
    if agent == "tester" and _tester_visual_capture_environment_only_is_advisory(artifact):
        return {
            "passed": True,
            "reason": "Tester functional checks passed; screenshot-only environment limitation deferred to the dedicated Visual QA gate.",
            "visual_evidence_deferred": True,
            "focused_tests_passed": True,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    if agent == "qa_red_team" and _visual_capture_environment_only_is_advisory(agent, artifact):
        return {
            "passed": True,
            "reason": "QA/red-team focused checks passed; screenshot-only environment limitation is deferred to the dedicated Visual QA gate using the Playwright fallback.",
            "visual_evidence_deferred": True,
            "focused_tests_passed": True,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    judgement_quality = _judgement_evidence_quality_gate(agent, artifact)
    if not judgement_quality["passed"]:
        return judgement_quality
    sensitive_changes = _vault_sensitive_changed_files(artifact.get("changed_files"))
    if sensitive_changes and not _artifact_records_vault_update_decision(artifact):
        return {
            "passed": False,
            "reason": f"{agent} changed Vault-sensitive files but did not record vault_updates or no_vault_update_required.",
        }
    if agent == "tester":
        status = str(artifact.get("test_status") or "").strip().lower()
        timeout_advisory = _tester_timeout_only_failure_is_advisory(agent, artifact, allow_pass_status=True)
        if status != "pass" and _tester_visual_capture_environment_only_is_advisory(artifact):
            return {
                "passed": True,
                "reason": "Tester functional checks passed; screenshot-only environment limitation deferred to the dedicated Visual QA gate.",
                "visual_evidence_deferred": True,
                "focused_tests_passed": True,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        if timeout_advisory:
            return {
                "passed": True,
                "reason": "Tester timeout-only broad command issue treated as advisory because focused changed-surface tests passed.",
                "timeout_advisory": True,
                "focused_tests_passed": True,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        if status != "pass":
            if _artifact_has_passing_test_collection(artifact) and _has_only_recovered_process_issues(agent, artifact) and not errors and not bugs:
                artifact.setdefault("warnings", []).append(
                    f"Tester self-reported test_status={status or 'missing'}, but focused test evidence passed and only recovered setup issues were present."
                )
                artifact["test_status"] = "pass"
                status = "pass"
            else:
                return {"passed": False, "reason": f"Tester reported test_status={status or 'missing'}."}
        if errors or bugs:
            return {"passed": False, "reason": "Tester reported errors or bugs."}
    if agent == "qa_red_team":
        status = str(artifact.get("red_team_status") or "").strip().lower()
        risk = str(artifact.get("risk_rating") or "").strip().lower()
        if status != "pass" and _qa_timeout_only_failure_is_advisory(agent, artifact):
            return {
                "passed": True,
                "reason": "QA/red-team timeout-only command issue treated as advisory because focused passing evidence is present.",
                "timeout_advisory": True,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        if status != "pass":
            if _artifact_has_passing_test_collection(artifact) and _has_only_recovered_process_issues(agent, artifact) and not errors and not bugs and risk not in {"high", "critical"}:
                artifact.setdefault("warnings", []).append(
                    f"QA/red-team self-reported red_team_status={status or 'missing'}, but focused test evidence passed and no blocking findings remained."
                )
                artifact["red_team_status"] = "pass"
                status = "pass"
            else:
                return {"passed": False, "reason": f"QA/red-team reported red_team_status={status or 'missing'}."}
        if risk in {"high", "critical"}:
            return {"passed": False, "reason": f"QA/red-team risk rating is {risk}."}
        if errors or bugs:
            return {"passed": False, "reason": "QA/red-team reported errors or bugs."}
    if agent == "builder":
        changed_files = artifact.get("changed_files") if isinstance(artifact.get("changed_files"), list) else []
        code_reference = _artifact_code_review_reference(artifact)
        if _has_release_relevant_changes(changed_files) and not code_reference:
            return {"passed": False, "reason": "Builder changed releaseable files but did not record a PR link, PR number, or local branch commit reference."}
    if agent == "reviewer":
        decision = str(artifact.get("recommended_owner_decision") or "").strip()
        if decision != "approve_final_release":
            return {"passed": False, "reason": f"Reviewer recommended {decision or 'no approval'}."}
        if errors or bugs:
            return {"passed": False, "reason": "Reviewer found errors or bugs."}
        changed_files = artifact.get("changed_files") if isinstance(artifact.get("changed_files"), list) else []
        code_reference = _artifact_code_review_reference(artifact)
        if _has_release_relevant_changes(changed_files) and not code_reference:
            return {"passed": False, "reason": "Reviewer did not record a PR link, PR number, or local branch commit reference for changed code/docs."}
        qa_evidence = artifact.get("qa_evidence") or artifact.get("qa_findings") or artifact.get("test_evidence")
        if not qa_evidence:
            return {"passed": False, "reason": "Reviewer did not record QA/red-team evidence."}
    return {
        "passed": True,
        "reason": f"{agent} quality gate passed.",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _read_only_reviewer_has_upstream_evidence(agent, artifact):
    if agent not in REVIEW_DECISION_AGENTS:
        return False
    inspected = artifact.get("files_inspected") if isinstance(artifact.get("files_inspected"), list) else []
    if not inspected:
        return False
    if not _artifact_vault_sources(artifact):
        return False
    decision = str(artifact.get("recommended_owner_decision") or "").strip()
    if not decision:
        return False
    evidence_lists = (
        artifact.get("test_evidence"),
        artifact.get("changed_files"),
        artifact.get("release_notes"),
        artifact.get("visual_review_notes"),
    )
    if any(isinstance(items, list) and any(str(item).strip() for item in items) for items in evidence_lists):
        return True
    return bool(str(artifact.get("no_vault_update_required") or "").strip())


def _artifact_confidence_quality_gate(agent, artifact):
    confidence = _parse_confidence_value(artifact.get("confidence"))
    reason = str(artifact.get("confidence_reason") or "").strip()
    if confidence is None:
        return {"passed": False, "reason": f"{agent} did not record a parseable confidence value."}
    if confidence < AGENT_CONFIDENCE_MINIMUM:
        objective = _objective_evidence_quality_override(agent, artifact, confidence)
        if objective["passed"]:
            return objective
        return {
            "passed": False,
            "reason": f"{agent} confidence {confidence:.0%} is below the required 96%; clarify or inspect more evidence.",
        }
    if not reason:
        return {"passed": False, "reason": f"{agent} did not record an evidence-backed confidence_reason."}
    evidence_terms = ("source", "vault", "test", "evidence", "repo", "file", "screenshot", "log", "runtime", "owner")
    if not any(term in reason.lower() for term in evidence_terms):
        return {"passed": False, "reason": f"{agent} confidence_reason is not evidence-backed."}
    return {"passed": True, "reason": "confidence_gate_passed"}


def _objective_evidence_quality_override(agent, artifact, confidence):
    if confidence is None or confidence < 0.80:
        return {"passed": False, "reason": "objective_gate_confidence_too_low"}
    errors = _blocking_artifact_items(agent, artifact, artifact.get("errors") if isinstance(artifact.get("errors"), list) else [])
    bugs = _blocking_artifact_items(agent, artifact, artifact.get("bugs") if isinstance(artifact.get("bugs"), list) else [])
    if errors or bugs:
        return {"passed": False, "reason": "objective_gate_blocking_items_present"}
    if not _artifact_vault_sources(artifact):
        return {"passed": False, "reason": "objective_gate_missing_vault_sources"}
    inspected = artifact.get("files_inspected") if isinstance(artifact.get("files_inspected"), list) else []
    if not inspected:
        return {"passed": False, "reason": "objective_gate_missing_files_inspected"}
    tests = artifact.get("tests_run") or artifact.get("test_evidence") or artifact.get("commands_run")
    if not (isinstance(tests, list) and any(_artifact_test_evidence_passes(item) for item in tests)):
        return {"passed": False, "reason": "objective_gate_missing_passing_test_evidence"}
    if agent == "tester":
        if str(artifact.get("test_status") or "").strip().lower() != "pass":
            return {"passed": False, "reason": "objective_gate_tester_not_pass"}
    if agent == "qa_red_team":
        if str(artifact.get("red_team_status") or "").strip().lower() != "pass":
            return {"passed": False, "reason": "objective_gate_qa_not_pass"}
        if str(artifact.get("risk_rating") or "").strip().lower() in {"high", "critical"}:
            return {"passed": False, "reason": "objective_gate_high_risk"}
    if agent in REVIEW_DECISION_AGENTS or agent == "reviewer":
        decision = str(artifact.get("recommended_owner_decision") or "").strip()
        if decision and decision not in {"approve_final_release", "approve", "not_applicable"}:
            return {"passed": False, "reason": "objective_gate_reviewer_not_approve"}
    has_pr_or_diff = bool(
        artifact.get("changed_files")
        or artifact.get("pr_url")
        or artifact.get("pr_number")
        or (isinstance(artifact.get("links"), dict) and artifact["links"].get("pr"))
    )
    if agent in {"builder", "reviewer", "publisher", "product_reviewer", "evidence_reviewer"} and not has_pr_or_diff:
        return {"passed": False, "reason": "objective_gate_missing_pr_or_diff"}
    return {
        "passed": True,
        "reason": f"{agent} passed objective evidence gate with confidence {confidence:.0%}; concrete tests, inspected files, Vault sources, and no blockers were present.",
        "objective_gate": True,
    }


def _artifact_test_evidence_passes(item):
    if isinstance(item, dict):
        status = str(item.get("status") or item.get("result") or "").strip().lower()
        text = " ".join(str(value or "") for value in item.values()).lower()
    else:
        status = ""
        text = str(item or "").lower()
    if any(phrase in text for phrase in ("no errors", "no error", "no failures", "no whitespace errors")):
        return True
    if any(word in text for word in ("failed", "failure", "error", "traceback")):
        return False
    return status == "pass" or " ok" in text or "tests ok" in text or "passed" in text or "no whitespace errors" in text


def _artifact_has_passing_test_collection(artifact):
    artifact = artifact if isinstance(artifact, dict) else {}
    evidence = []
    for key in ("tests_run", "test_evidence"):
        value = artifact.get(key)
        if isinstance(value, list):
            evidence.extend(value)
        elif value:
            evidence.append(value)
    if not evidence:
        return False
    return any(_artifact_test_evidence_passes(item) for item in evidence)


def _has_only_recovered_process_issues(agent, artifact):
    artifact = artifact if isinstance(artifact, dict) else {}
    raw_items = []
    for key in ("errors", "bugs"):
        value = artifact.get(key)
        if isinstance(value, list):
            raw_items.extend(value)
        elif value:
            raw_items.append(value)
    if not raw_items:
        return False
    return all(_is_recovered_command_process_issue(agent, artifact, item) for item in raw_items)


def _parse_confidence_value(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 1:
            number = number / 100.0
        return number if 0 <= number <= 1 else None
    text = str(value or "").strip().lower()
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if match:
        return float(match.group(1)) / 100.0
    match = re.search(r"\b(0(?:\.\d+)?|1(?:\.0+)?)\b", text)
    if match:
        return float(match.group(1))
    match = re.search(r"\b(\d+(?:\.\d+)?)\b", text)
    if match:
        number = float(match.group(1))
        if number > 1:
            number = number / 100.0
        return number if 0 <= number <= 1 else None
    return None


def _ui_agent_quality_gate(agent, artifact):
    contract = artifact.get("ui_quality_contract") if isinstance(artifact.get("ui_quality_contract"), dict) else {}
    ui_agents = {
        "visual_reference_interpreter",
        "creative_ui_designer",
        "ux_interaction_designer",
        "frontend_design_implementer",
        "builder",
        "tester",
        "qa_red_team",
        "visual_qa_reviewer",
        "reviewer",
    }
    if not contract.get("ui_related") or agent not in ui_agents:
        return {"passed": True, "reason": "ui_quality_not_required"}
    reference_required = bool(contract.get("reference_media_required"))
    if reference_required and not _artifact_has_list_value(artifact, "media_references_used"):
        return {"passed": False, "reason": f"{agent} did not cite attached UI reference media."}
    if reference_required and not (
        any(_artifact_has_text_value(artifact, key) for key in ("visual_reference_analysis", "reference_match_assessment", "ui_concept"))
        or any(_artifact_has_list_value(artifact, key) for key in ("layout_requirements", "interaction_requirements", "design_requirements", "visual_review_notes"))
    ):
        return {"passed": False, "reason": f"{agent} did not explain how the attached UI reference media was used."}
    if agent == "visual_reference_interpreter":
        if not _artifact_has_list_value(artifact, "layout_requirements"):
            return {"passed": False, "reason": "Visual Reference Interpreter did not extract layout requirements."}
        if not _artifact_has_list_value(artifact, "reference_match_checklist"):
            return {"passed": False, "reason": "Visual Reference Interpreter did not create a reference-match checklist."}
    if agent == "creative_ui_designer":
        if not _artifact_has_text_value(artifact, "ui_concept"):
            return {"passed": False, "reason": "Creative UI Designer did not define a UI concept."}
        if not _artifact_has_list_value(artifact, "layout_system"):
            return {"passed": False, "reason": "Creative UI Designer did not define the layout system."}
        anti_pattern_text = " ".join(str(item or "") for item in artifact.get("what_not_to_do", []) if isinstance(artifact.get("what_not_to_do"), list)).lower()
        if "color" not in anti_pattern_text:
            return {"passed": False, "reason": "Creative UI Designer did not guard against color-only restyling."}
    if agent == "ux_interaction_designer":
        if not _artifact_has_list_value(artifact, "owner_actions"):
            return {"passed": False, "reason": "UX Interaction Designer did not define visible owner actions."}
        if not _artifact_has_list_value(artifact, "responsive_behavior"):
            return {"passed": False, "reason": "UX Interaction Designer did not define responsive behavior."}
    if agent in {"builder", "frontend_design_implementer"}:
        local_preview = artifact.get("local_preview") if isinstance(artifact.get("local_preview"), dict) else {}
        links = artifact.get("links") if isinstance(artifact.get("links"), dict) else {}
        preview_url = str(local_preview.get("url") or links.get("local_preview") or "").strip()
        if not preview_url:
            return {"passed": False, "reason": f"{agent} did not provide a real local preview URL for the changed UI."}
        if _is_control_dashboard_preview_url(preview_url) and not _preview_url_matches_changed_ui(preview_url, artifact.get("changed_files"), artifact.get("summary", "")):
            return {"passed": False, "reason": f"{agent} local preview points at the CHARLIE control dashboard instead of the changed UI route."}
        if not _artifact_has_list_value(artifact, "viewport_plan"):
            return {"passed": False, "reason": f"{agent} did not record a desktop/mobile viewport plan."}
        if agent == "frontend_design_implementer" and not _artifact_has_list_value(artifact, "design_requirements_met"):
            return {"passed": False, "reason": "Frontend Design Implementer did not list design requirements met."}
    if agent == "tester":
        if not (_artifact_has_list_value(artifact, "browser_checks") or _artifact_has_list_value(artifact, "screenshots_captured")):
            return {"passed": False, "reason": "Tester did not record browser or screenshot evidence for the UI mission."}
        if not _artifact_mentions_viewports(artifact):
            return {"passed": False, "reason": "Tester did not record desktop/laptop and mobile viewport evidence."}
    if agent == "qa_red_team":
        if not (_artifact_has_list_value(artifact, "visual_quality_findings") or _artifact_has_text_value(artifact, "reference_match_assessment")):
            return {"passed": False, "reason": "QA/red-team did not record visual quality/reference-match findings for the UI mission."}
    if agent in {"visual_qa_reviewer", "reviewer"}:
        decision = str(artifact.get("visual_acceptance_decision") or "").strip().lower()
        if decision != "approve":
            return {"passed": False, "reason": f"{agent} visual acceptance decision is {decision or 'missing'}."}
        if not _artifact_has_list_value(artifact, "visual_review_notes"):
            return {"passed": False, "reason": f"{agent} did not record visual review notes for the UI mission."}
        if agent == "visual_qa_reviewer" and not _artifact_has_text_value(artifact, "reference_match_assessment"):
            return {"passed": False, "reason": "Visual QA Reviewer did not assess reference match."}
    return {"passed": True, "reason": "ui_quality_gate_passed"}


def _implementation_source_quality_gate(agent, artifact):
    source_map = artifact.get("implementation_source_map") if isinstance(artifact.get("implementation_source_map"), dict) else {}
    if not source_map.get("matched_sections"):
        return {"passed": True, "reason": "implementation_source_map_not_required"}
    if agent not in {
        "source_mapper",
        "technical_architect",
        "business_model_agent",
        "risk_agent",
        "planner",
        "architect",
        "builder",
        "tester",
        "qa_red_team",
        "business_reviewer",
        "evidence_reviewer",
        "reviewer",
    }:
        return {"passed": True, "reason": "implementation_source_gate_not_for_agent"}
    if agent == "source_mapper":
        validation = validate_implementation_inspection(artifact, source_map)
        if not validation["passed"]:
            return {
                "passed": False,
                "reason": f"Source Mapper did not inspect required implementation groups: {', '.join(validation['missing_groups']) or 'none matched'}.",
                "implementation_inspection": validation,
            }
    elif _implementation_sensitive_source_map(source_map):
        values = []
        for key in ("files_inspected", "implementation_sources_used", "changed_files", "files_changed"):
            value = artifact.get(key)
            if isinstance(value, list):
                values.extend(str(item or "").replace("\\", "/") for item in value)
        valid_paths = set(str(path or "").replace("\\", "/") for path in source_map.get("required_inspection_paths") or [])
        for section in source_map.get("matched_sections") or []:
            if not isinstance(section, dict):
                continue
            for key in ("vault_docs", "code_paths", "tests", "legacy_sources", "app_routes", "migrations"):
                items = section.get(key)
                if isinstance(items, list):
                    valid_paths.update(str(item or "").replace("\\", "/") for item in items if str(item or "").strip())
        cited = set(path for path in values if path)
        if not valid_paths.intersection(cited):
            return {
                "passed": False,
                "reason": f"{agent} did not cite any matched implementation source-map path.",
                "required_inspection_paths_sample": sorted(set(source_map.get("required_inspection_paths") or []))[:12],
                "valid_source_map_paths_sample": sorted(valid_paths)[:16],
                "cited_paths_sample": sorted(cited)[:12],
                "matched_source_sections": [
                    section.get("key") or section.get("label")
                    for section in source_map.get("matched_sections", [])
                    if isinstance(section, dict)
                ],
            }
    return {"passed": True, "reason": "implementation_source_gate_passed"}


def _implementation_sensitive_source_map(source_map):
    sections = source_map.get("matched_sections") if isinstance(source_map.get("matched_sections"), list) else []
    return any(section.get("must_inspect_before_advice") for section in sections if isinstance(section, dict))


def _artifact_has_text_value(artifact, key):
    return bool(str((artifact or {}).get(key) or "").strip())


def _artifact_has_list_value(artifact, key):
    value = (artifact or {}).get(key)
    if isinstance(value, list):
        return any(str(item or "").strip() for item in value)
    return bool(str(value or "").strip())


def _artifact_mentions_viewports(artifact):
    values = []
    for key in ("browser_checks", "screenshots_captured", "tests_run", "test_evidence", "stdout_tail"):
        value = (artifact or {}).get(key)
        if isinstance(value, list):
            values.extend(str(item or "") for item in value)
        elif value:
            values.append(str(value))
    text = " ".join(values).lower()
    desktop = any(term in text for term in ("desktop", "laptop", "1440", "1366", "1280"))
    mobile = any(term in text for term in ("mobile", "390", "375", "414"))
    return desktop and mobile


def _artifact_vault_sources(artifact):
    artifact = artifact if isinstance(artifact, dict) else {}
    sources = []
    for key in ("vault_sources_used", "inputs_used", "files_inspected"):
        value = artifact.get(key)
        if isinstance(value, str):
            sources.append(value)
        elif isinstance(value, list):
            sources.extend(value)
    canonical = artifact.get("canonical") if isinstance(artifact.get("canonical"), dict) else {}
    for key in ("vault_sources_used", "inputs_used", "files_inspected"):
        value = canonical.get(key)
        if isinstance(value, str):
            sources.append(value)
        elif isinstance(value, list):
            sources.extend(value)
    return [str(item or "").strip().replace("\\", "/") for item in sources if str(item or "").strip()]


def _artifact_has_vault_brain_source(artifact):
    return any(source.startswith("docs/09-vault-brain/") for source in _artifact_vault_sources(artifact))


def _artifact_records_vault_update_decision(artifact):
    updates = artifact.get("vault_updates")
    if isinstance(updates, str):
        updates = [updates]
    has_update = bool([item for item in updates or [] if str(item or "").strip()])
    has_no_update_reason = bool(str(artifact.get("no_vault_update_required") or "").strip())
    return has_update or has_no_update_reason


def _judgement_evidence_quality_gate(agent, artifact):
    judgement_agents = {
        "tester",
        "risk_agent",
        "qa_red_team",
        "visual_qa_reviewer",
        "product_reviewer",
        "business_reviewer",
        "security_reviewer",
        "evidence_reviewer",
        "reviewer",
    }
    if agent not in judgement_agents:
        return {"passed": True, "reason": "judgement_gate_not_required"}
    decision_fields = {
        "recommended_owner_decision": {"approve_final_release", "approve", "mark_done"},
        "visual_acceptance_decision": {"approve"},
        "red_team_status": {"pass"},
        "test_status": {"pass"},
    }
    for field, passing_values in decision_fields.items():
        if field not in artifact:
            continue
        if field == "visual_acceptance_decision" and not _artifact_is_ui_related(artifact):
            continue
        decision = str(artifact.get(field) or "").strip().lower()
        if agent == "risk_agent" and field == "recommended_owner_decision" and decision == "pause":
            continue
        if decision and decision not in passing_values:
            if field == "red_team_status" and _qa_timeout_only_failure_is_advisory(agent, artifact):
                continue
            if field == "test_status" and _tester_timeout_only_failure_is_advisory(agent, artifact):
                continue
            if field in {"test_status", "red_team_status"} and _artifact_has_passing_test_collection(artifact) and _has_only_recovered_process_issues(agent, artifact):
                errors = _blocking_artifact_items(agent, artifact, artifact.get("errors") if isinstance(artifact.get("errors"), list) else [])
                bugs = _blocking_artifact_items(agent, artifact, artifact.get("bugs") if isinstance(artifact.get("bugs"), list) else [])
                risk = str(artifact.get("risk_rating") or "").strip().lower()
                if not errors and not bugs and risk not in {"high", "critical"}:
                    continue
            return {
                "passed": False,
                "reason": f"{agent} recorded non-passing {field}={decision}.",
            }

    negative = _negative_judgement_evidence(agent, artifact)
    if negative:
        return {
            "passed": False,
            "reason": f"{agent} recorded blocking evidence: {_truncate(_artifact_text(negative[0]), 180)}",
            "blocking_evidence": [_artifact_text(item) for item in negative[:5]],
        }
    return {"passed": True, "reason": "judgement_gate_passed"}


def _artifact_is_ui_related(artifact):
    contract = artifact.get("ui_quality_contract") if isinstance(artifact.get("ui_quality_contract"), dict) else {}
    if contract.get("ui_related"):
        return True
    values = []
    for key in ("media_references_used", "screenshots_captured", "browser_checks", "reference_match_assessment"):
        value = artifact.get(key)
        if isinstance(value, list):
            values.extend(value)
        elif value:
            values.append(value)
    text = " ".join(str(item or "") for item in values).lower()
    return any(term in text for term in ("screenshot", "viewport", "visual reference", "desktop", "mobile", "ui"))


def _negative_judgement_evidence(agent, artifact):
    fields = (
        "test_evidence",
        "tests_run",
        "visual_review_notes",
        "qa_evidence",
        "qa_findings",
        "risk_notes",
        "changed_files",
        "release_notes",
        "stdout_tail",
        "stderr_tail",
        "summary",
        "next_action",
    )
    values = []
    for field in fields:
        if field == "qa_findings" and _qa_findings_are_advisory(agent, artifact):
            continue
        if field == "visual_review_notes" and _visual_review_notes_are_advisory(agent, artifact):
            continue
        if field in {"stdout_tail", "stderr_tail"} and (
            _raw_judgement_tails_are_advisory(agent, artifact)
            or _visual_review_tails_are_advisory(agent, artifact)
        ):
            continue
        if field in {"release_notes", "stdout_tail", "stderr_tail"} and _structured_review_judgement_passed(agent, artifact):
            continue
        value = artifact.get(field)
        if isinstance(value, list):
            values.extend(value)
        elif value:
            values.append(value)
    return [value for value in values if _is_blocking_judgement_text(agent, artifact, value)]


def _qa_findings_are_advisory(agent, artifact):
    if agent != "qa_red_team":
        return False
    status = str((artifact or {}).get("red_team_status") or "").strip().lower()
    risk = str((artifact or {}).get("risk_rating") or "").strip().lower()
    return (status == "pass" and risk not in {"high", "critical"}) or _qa_timeout_only_failure_is_advisory(agent, artifact)


def _raw_judgement_tails_are_advisory(agent, artifact):
    if agent != "qa_red_team":
        return False
    status = str((artifact or {}).get("red_team_status") or "").strip().lower()
    risk = str((artifact or {}).get("risk_rating") or "").strip().lower()
    return (status == "pass" and risk not in {"high", "critical"}) or _qa_timeout_only_failure_is_advisory(agent, artifact)


def _qa_timeout_only_failure_is_advisory(agent, artifact):
    if agent != "qa_red_team" or not isinstance(artifact, dict):
        return False
    status = str(artifact.get("red_team_status") or "").strip().lower()
    if status not in {"fail", "blocked"}:
        return False
    return _timeout_only_failure_has_focused_pass_evidence(agent, artifact)


def _tester_timeout_only_failure_is_advisory(agent, artifact, allow_pass_status=False):
    if agent != "tester" or not isinstance(artifact, dict):
        return False
    status = str(artifact.get("test_status") or "").strip().lower()
    allowed_statuses = {"fail", "failed", "blocked"}
    if allow_pass_status:
        allowed_statuses.add("pass")
    if status not in allowed_statuses:
        return False
    return _timeout_only_failure_has_focused_pass_evidence(agent, artifact)


def _visual_capture_environment_only_is_advisory(agent, artifact):
    if agent not in {"tester", "qa_red_team"}:
        return False
    if not isinstance(artifact, dict) or not _artifact_has_passing_test_collection(artifact):
        return False
    bugs = _artifact_value_list(artifact.get("bugs"))
    if bugs:
        return False
    errors = [_artifact_text(item).lower() for item in _artifact_value_list(artifact.get("errors"))]
    if not errors:
        return False
    visual_environment_terms = (
        "browser-control",
        "browser control",
        "browser runtime",
        "browser list",
        "node_repl",
        "screenshot permission",
        "screenshots unless explicitly approved",
        "could not capture screenshot",
        "no real screenshots",
        "preview url",
        "preview server",
    )
    return all(any(term in error for term in visual_environment_terms) for error in errors)


def _tester_visual_capture_environment_only_is_advisory(artifact):
    return _visual_capture_environment_only_is_advisory("tester", artifact)


def _timeout_only_failure_has_focused_pass_evidence(agent, artifact):
    values = []
    for key in ("errors", "bugs", "qa_findings", "tests_run"):
        value = artifact.get(key)
        if isinstance(value, list):
            values.extend(str(item or "") for item in value if str(item or "").strip())
        elif value:
            values.append(str(value))
    if not values:
        return False
    timeout_terms = ("timed out", "timeout", "tool timeout", "command timed out", "crossed the")
    if not any(any(term in value.lower() for term in timeout_terms) for value in values):
        return False
    pseudo_pass_artifact = {**artifact, "red_team_status": "pass", "test_status": "pass", "risk_rating": "low"}
    non_timeout_blockers = [
        value for value in values
        if not any(term in value.lower() for term in timeout_terms)
        and (
            _is_blocking_judgement_text(agent, pseudo_pass_artifact, value)
            or any(term in value.lower() for term in (
                "without owner approval",
                "customer send",
                "customer message",
                "chatwoot write",
                "create an order",
                "creates an order",
                "create quote",
                "creates quote",
                "reservation",
                "reserve stock",
                "payment",
                "production write",
                "changes stock",
            ))
        )
    ]
    if non_timeout_blockers:
        return False
    evidence_values = []
    for key in ("tests_run", "test_evidence", "stdout_tail", "confidence_reason", "commands_run"):
        value = artifact.get(key)
        if isinstance(value, list):
            evidence_values.extend(value)
        elif value:
            evidence_values.append(value)
    return any(_artifact_test_evidence_passes(item) for item in evidence_values)


def _focused_test_budget_prompt(mission, agent, artifacts):
    mission = mission if isinstance(mission, dict) else {}
    agent = str(agent or "").strip().lower()
    if agent not in {"tester", "qa_red_team", "product_reviewer", "business_reviewer", "security_reviewer", "evidence_reviewer", "reviewer"}:
        return "No special test-budget instructions for this agent."
    changed = _mission_changed_files_from_artifacts(artifacts or {})
    implementation_context = implementation_source_packet(mission)
    matched_tests = []
    for section in implementation_context.get("matched_sections") or []:
        if not isinstance(section, dict):
            continue
        for test_path in section.get("tests") or []:
            text = str(test_path or "").strip()
            if text and text not in matched_tests:
                matched_tests.append(text)
    profile = "focused"
    haystack = " ".join([
        str(mission.get("title") or ""),
        str(mission.get("mission_type") or ""),
        str(mission.get("raw_text") or ""),
    ]).lower()
    if any(term in haystack for term in ("runner", "charlie core", "mission pickup", "execution bridge", "workflow", "conveyor")):
        profile = "standard"
    if any(term in haystack for term in ("migration", "security", "auth", "payment", "customer send", "reserve stock", "merge", "deploy")):
        profile = "full"
    return json.dumps({
        "version": "charlie_focused_test_budget_v1",
        "profile": profile,
        "rule": (
            "Run focused changed-surface tests first and record them as focused_tests_passed when green. "
            "Do not turn unrelated broad/full-suite timeouts into a blocker when focused tests pass and no real owner/customer/order/stock safety defect is present. "
            "Real product, security, data, source-of-truth, customer-send, order/quote, reservation, payment, or deployment failures still block."
        ),
        "changed_files_from_upstream": changed[:16],
        "source_map_matched_tests": matched_tests[:16],
        "reporting": {
            "tests_run": "List each focused and broad command separately with pass/fail/timeout.",
            "test_status": "Use pass when focused required tests pass and any broad timeout is advisory only.",
            "advisory_timeouts": "Record broad timeout details without send_back if no real blocker exists.",
        },
    }, indent=2)


def _visual_review_notes_are_advisory(agent, artifact):
    if agent not in {
        "visual_qa_reviewer",
        "product_reviewer",
        "business_reviewer",
        "security_reviewer",
        "evidence_reviewer",
        "reviewer",
    }:
        return False
    if (artifact or {}).get("errors") or (artifact or {}).get("bugs"):
        return False
    visual_decision = str((artifact or {}).get("visual_acceptance_decision") or "").strip().lower()
    owner_decision = str((artifact or {}).get("recommended_owner_decision") or "").strip().lower()
    return visual_decision == "approve" and owner_decision in {"approve", "approve_final_release", "mark_done", ""}


def _visual_review_tails_are_advisory(agent, artifact):
    if not _visual_review_notes_are_advisory(agent, artifact):
        return False
    return not ((artifact or {}).get("errors") or (artifact or {}).get("bugs"))


def _structured_review_judgement_passed(agent, artifact):
    review_agents = {
        "product_reviewer",
        "business_reviewer",
        "security_reviewer",
        "evidence_reviewer",
        "reviewer",
    }
    if agent not in review_agents:
        return False
    decision = str((artifact or {}).get("recommended_owner_decision") or "").strip().lower()
    if decision not in {"approve_final_release", "approve", "mark_done"}:
        return False
    quality_gate = artifact.get("quality_gate") if isinstance(artifact.get("quality_gate"), dict) else {}
    if quality_gate.get("passed") is not True:
        return False
    return not (artifact.get("errors") or artifact.get("bugs"))


def _is_blocking_judgement_text(agent, artifact, value):
    text = _artifact_text(value).lower()
    if not text:
        return False
    if _is_non_blocking_local_pytest_issue(agent, artifact, value):
        return False
    if _is_non_blocking_owner_review_gate_instruction(agent, artifact, text):
        return False
    if _is_non_blocking_separate_migration_application_gate(agent, artifact, text):
        return False
    blocking_phrases = (
        "send_back",
        "send back",
        "must not be approved",
        "cannot approve",
        "do not approve",
        "not approve",
        "visual_acceptance_decision\": \"send_back",
        "visual acceptance decision is send_back",
        "browser gate failed",
        "playwright cannot reach",
        "playwright failed",
        "npm run test:charlie:browser",
        "failed browser",
        "failed screenshot",
        "failed visual",
        "out-of-scope",
        "out of scope",
        "stale pr",
        "stale branch",
        "diff against current main also includes",
        "pytest module missing",
        "no module named pytest",
    )
    if any(phrase in text for phrase in blocking_phrases):
        return True
    failure_text = re.sub(r"\bfail[- ]closed\b", "", text)
    if re.search(r"\b(fail|failed|failing|failure)\b", failure_text) and not re.search(r"\b(no failures|0 failures|all passed|pass|passed)\b", failure_text):
        return True
    return False


def _is_non_blocking_separate_migration_application_gate(agent, artifact, text):
    """Distinguish PR merge approval from later migration-application authority."""
    if agent not in {"product_reviewer", "security_reviewer", "evidence_reviewer", "reviewer"}:
        return False
    artifact = artifact if isinstance(artifact, dict) else {}
    decision = str(artifact.get("recommended_owner_decision") or "").strip().lower()
    if decision not in {"approve_final_release", "approve", "mark_done"}:
        return False
    if artifact.get("errors") or artifact.get("bugs"):
        return False
    acceptance = artifact.get("acceptance_results") if isinstance(artifact.get("acceptance_results"), list) else []
    if acceptance and any(
        not isinstance(row, dict) or str(row.get("status") or "").strip().lower() != "passed"
        for row in acceptance
    ):
        return False
    changed_files = [str(path or "").replace("\\", "/") for path in (artifact.get("changed_files") or [])]
    if not any(path.startswith("supabase/migrations/") for path in changed_files):
        return False
    artifact_text = " ".join(str(value or "") for value in (
        artifact.get("summary"),
        artifact.get("next_action"),
        *(artifact.get("release_notes") or []),
    )).lower()
    if "unapplied" not in artifact_text:
        return False
    merge_approval_terms = (
        "may approve merge",
        "may approve the merge",
        "may approve final release",
        "approve merge of pr",
        "approve release of pr",
    )
    separate_gate_terms = (
        "must not approve migration application",
        "does not authorize migration application",
        "does not authorize applying the migration",
        "do not apply this migration",
        "before migration application",
        "before any migration application",
    )
    current_defect_terms = (
        "current-diff security defect",
        "current diff security defect",
        "security vulnerability",
        "acceptance failed",
        "tests failed",
        "must fix before merge",
    )
    return (
        any(term in artifact_text for term in merge_approval_terms)
        and any(term in text for term in separate_gate_terms)
        and not any(term in text for term in current_defect_terms)
    )


def _is_non_blocking_owner_review_gate_instruction(agent, artifact, text):
    review_handoff_agents = {
        "product_reviewer",
        "business_reviewer",
        "security_reviewer",
        "evidence_reviewer",
        "reviewer",
    }
    if agent not in review_handoff_agents:
        return False
    decision = str((artifact or {}).get("recommended_owner_decision") or "").strip().lower()
    if decision not in {"approve_final_release", "approve", "mark_done"}:
        return False
    if (artifact or {}).get("errors") or (artifact or {}).get("bugs"):
        return False
    approval_gate_terms = (
        "stop at owner review",
        "stops at owner review",
        "owner review pr",
        "owner should review",
        "owner/reviewer should review",
        "approve pr",
        "choose approve final release",
        "approve final release or send back",
        "or send back with comments",
        "until owner final approval",
        "until final owner approval",
        "until owner approval",
    )
    return any(term in text for term in approval_gate_terms)


def _vault_sensitive_changed_files(changed_files):
    files = [str(item or "").strip().replace("\\", "/") for item in (changed_files if isinstance(changed_files, list) else [])]
    return [
        path for path in files
        if path and path != "No changed files detected by git diff."
        and any(path.startswith(prefix) for prefix in VAULT_SENSITIVE_PATH_PREFIXES)
    ]


def _artifact_pr_reference(artifact):
    links = artifact.get("links") if isinstance(artifact.get("links"), dict) else {}
    for value in (
        artifact.get("pr_url"),
        artifact.get("pr_number"),
        links.get("pr"),
        links.get("pull_request"),
        links.get("diff"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _artifact_local_commit_reference(artifact):
    branch_name = str((artifact or {}).get("branch_name") or "").strip()
    commit_sha = str((artifact or {}).get("commit_sha") or "").strip()
    if branch_name and commit_sha:
        return f"{branch_name}@{commit_sha}"
    packaging = artifact.get("git_packaging") if isinstance(artifact.get("git_packaging"), dict) else {}
    branch_name = str(packaging.get("branch_name") or "").strip()
    commit_sha = str(packaging.get("commit_sha") or "").strip()
    if branch_name and commit_sha:
        return f"{branch_name}@{commit_sha}"
    return ""


def _artifact_code_review_reference(artifact):
    return _artifact_pr_reference(artifact) or _artifact_local_commit_reference(artifact)


def _artifact_text(value):
    if isinstance(value, dict):
        return str(value.get("finding") or value.get("bug") or value.get("error") or value.get("summary") or value.get("message") or "").strip()
    return str(value or "").strip()


def _has_passing_fallback_test_evidence(artifact):
    status = str((artifact or {}).get("test_status") or "").strip().lower()
    decision = str((artifact or {}).get("recommended_owner_decision") or "").strip().lower()
    if status != "pass" and decision not in {"approve_final_release", "approve", "mark_done"}:
        return False
    evidence = []
    for key in ("tests_run", "test_evidence", "commands_run", "stdout_tail"):
        value = artifact.get(key) if isinstance(artifact, dict) else None
        if isinstance(value, list):
            evidence.extend(str(item or "") for item in value)
        elif value:
            evidence.append(str(value))
    evidence_text = " ".join(evidence).lower()
    return "unittest" in evidence_text and (" ok" in evidence_text or "pass" in evidence_text or "passed" in evidence_text)


def _is_non_blocking_local_pytest_issue(agent, artifact, value):
    if agent not in {"tester", "reviewer", "evidence_reviewer"} or not _has_passing_fallback_test_evidence(artifact):
        return False
    text = _artifact_text(value).lower()
    return "pytest" in text and (
        "no module named pytest" in text
        or "pytest is not installed" in text
        or "pytest unavailable" in text
        or "pytest is unavailable" in text
    )


def _is_resolved_pr_process_issue(agent, artifact, value):
    if agent not in {"tester", "qa_red_team", "reviewer"} or not _artifact_pr_reference(artifact):
        return False
    text = _artifact_text(value).lower()
    return "pr" in text and (
        "no pr url" in text
        or "no pr link" in text
        or "no pr reference" in text
        or "no pr url/number" in text
        or "no pr url or number" in text
        or "no pull request" in text
        or "pr evidence is missing" in text
    )


def _is_recovered_command_process_issue(agent, artifact, value):
    if agent not in {"tester", "qa_red_team", "reviewer", "evidence_reviewer", "security_reviewer"}:
        return False
    if not _artifact_has_passing_test_collection(artifact):
        return False
    text = _artifact_text(value).lower()
    recovered_terms = (
        "reran",
        "re-run",
        "rerun",
        "recovered",
        "recaptured",
        "passed",
    )
    setup_terms = (
        "powershell invocation",
        "quoted executable",
        "call operator",
        "parser error",
        "viewport-size",
        "networkidle timed out",
        "async cards loaded",
        "explicit wait",
        "case-insensitive",
        "text-transform",
    )
    return any(term in text for term in recovered_terms) and any(term in text for term in setup_terms)


def _is_resolved_informational_process_issue(agent, artifact, value):
    if agent not in {"tester", "qa_red_team", "reviewer", "evidence_reviewer", "security_reviewer"}:
        return False
    if not isinstance(value, dict) or not _artifact_has_passing_test_collection(artifact):
        return False
    if value.get("introduced_by_current_diff") is not False:
        return False
    severity = str(value.get("severity") or "").strip().lower()
    scope = str(value.get("scope_relation") or "").strip().lower()
    acceptance = str(value.get("acceptance_relation") or "").strip().lower()
    detail = " ".join((
        _artifact_text(value),
        str(value.get("detail") or ""),
    )).lower()
    return (
        severity in {"informational", "info", "none"}
        and any(term in scope for term in ("command", "tool", "test harness", "process"))
        and any(term in acceptance for term in ("does not violate", "outside acceptance", "not acceptance"))
        and any(term in detail for term in ("corrected", "retried", "reran", "resolved", "subsequent"))
        and any(term in detail for term in ("pass", "passing", "succeeded", "green"))
    )


def _blocking_artifact_items(agent, artifact, values):
    if not isinstance(values, list):
        values = [values] if values else []
    blocking = []
    for value in values:
        if _is_reviewer_adjacent_follow_up(agent, artifact, value):
            continue
        if _is_non_blocking_local_pytest_issue(agent, artifact, value):
            continue
        if _is_resolved_pr_process_issue(agent, artifact, value):
            continue
        if _is_recovered_command_process_issue(agent, artifact, value):
            continue
        if _is_resolved_informational_process_issue(agent, artifact, value):
            continue
        blocking.append(value)
    return blocking


def _is_reviewer_adjacent_follow_up(agent, artifact, value):
    """Keep explicitly deferred owner/migration work out of current-diff backflow.

    Reviewer models occasionally place advisory follow-ups in the legacy
    ``bugs`` array while simultaneously recording their structured scope in
    ``finding_contract``.  Suppression is intentionally narrow: the release
    recommendation and every acceptance row must pass, the contract must say
    the work is adjacent and not introduced by this candidate, and the item
    itself must describe a separate future migration/capture gate.
    """
    if agent != "reviewer" or not isinstance(artifact, dict):
        return False
    if str(artifact.get("recommended_owner_decision") or "").strip().lower() != "approve_final_release":
        return False
    acceptance = artifact.get("acceptance_results") if isinstance(artifact.get("acceptance_results"), list) else []
    if not acceptance or any(
        not isinstance(row, dict) or str(row.get("status") or "").strip().lower() != "passed"
        for row in acceptance
    ):
        return False
    contract = str(artifact.get("finding_contract") or "").lower().replace(" ", "_")
    if not all(term in contract for term in (
        "adjacent_follow_up",
        "introduced_by_current_diff=false",
        "acceptance_impact=none",
    )):
        return False
    text = _artifact_text(value).lower()
    deferred_terms = (
        "before migration application",
        "before applying the migration",
        "before any migration",
        "do not apply this migration",
        "before capture implementation",
        "do not build capture",
        "capture roles",
        "correction authorization",
        "retention/deletion policy",
        "non-production rehearsal",
        "non-production postgresql",
    )
    current_defect_terms = (
        "introduced by current diff",
        "current-diff defect",
        "acceptance failed",
        "acceptance violation",
        "tests failed",
        "failing test",
        "security vulnerability",
        "data loss",
        "must fix before merge",
    )
    return any(term in text for term in deferred_terms) and not any(term in text for term in current_defect_terms)


def _auto_package_builder_changes(mission, artifact, runner=None):
    artifact = artifact if isinstance(artifact, dict) else {}
    artifact_files = artifact.get("changed_files") if isinstance(artifact.get("changed_files"), list) else []
    changed_files = list(dict.fromkeys([
        *artifact_files,
        *[path for path in _changed_files() if not _runner_generated_path(path)],
    ]))
    if not _has_release_relevant_changes(changed_files) or _artifact_pr_reference(artifact):
        return artifact
    runner = runner or subprocess.run
    branch_name = _builder_branch_name(mission)
    result = {
        "version": "charlie_builder_git_packaging_v1",
        "attempted": True,
        "branch_name": branch_name,
        "commands": [],
        "status": "started",
    }

    def run(command):
        try:
            completed = runner(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(REPO_ROOT),
                timeout=180,
                check=False,
            )
        except Exception as exc:
            record = {
                "command": " ".join(command),
                "returncode": 1,
                "stdout": "",
                "stderr": exc.__class__.__name__,
            }
            result["commands"].append(record)
            return record
        record = {
            "command": " ".join(command),
            "returncode": completed.returncode,
            "stdout": _truncate(completed.stdout or "", 1200),
            "stderr": _truncate(completed.stderr or "", 1200),
        }
        result["commands"].append(record)
        return record

    current = run(["git", "branch", "--show-current"])
    if current["returncode"] != 0:
        return _builder_packaging_failed(artifact, result, "current_branch_failed")
    if current["stdout"].strip() != branch_name:
        created = run(["git", "switch", "-c", branch_name])
        if created["returncode"] != 0:
            switched = run(["git", "switch", branch_name])
            if switched["returncode"] != 0:
                return _builder_packaging_failed(artifact, result, "branch_create_or_switch_failed")

    add_files = [path for path in changed_files if path and path != "No changed files detected by git diff."]
    added = run(["git", "add", "--", *add_files])
    if added["returncode"] != 0:
        return _builder_packaging_failed(artifact, result, "git_add_failed")
    diff_check = run(["git", "diff", "--cached", "--quiet", "--", *add_files])
    existing_commit = diff_check["returncode"] == 0
    if diff_check["returncode"] not in {0, 1}:
        return _builder_packaging_failed(artifact, result, "staged_diff_check_failed")

    commit_message = _builder_commit_message(mission)
    if not existing_commit:
        committed = run(["git", "commit", "-m", commit_message])
        if committed["returncode"] != 0:
            _preserve_builder_recovery_stash(run, result, mission)
            return _builder_packaging_failed(artifact, result, "git_commit_failed")
    sha = run(["git", "rev-parse", "--short", "HEAD"])
    commit_sha = sha["stdout"].strip()
    if sha["returncode"] != 0 or not commit_sha:
        return _builder_packaging_failed(artifact, result, "commit_sha_failed")
    result["commit_sha"] = commit_sha
    pushed = run(["git", "push", "-u", "origin", branch_name])
    if pushed["returncode"] != 0:
        return _builder_packaging_failed(artifact, result, "git_push_failed")
    pr = run([
        "gh",
        "pr",
        "create",
        "--title",
        _truncate(str((mission or {}).get("title") or commit_message), 120),
        "--body",
        _builder_pr_body(mission, artifact, result),
        "--base",
        "main",
        "--head",
        branch_name,
    ])
    if pr["returncode"] != 0:
        return _builder_packaging_failed(artifact, result, "gh_pr_create_failed")
    pr_url = _extract_pr_url(pr["stdout"]) or _extract_pr_url(pr["stderr"])
    if not pr_url:
        return _builder_packaging_failed(artifact, result, "pr_url_not_detected")

    packaged = dict(artifact)
    links = packaged.get("links") if isinstance(packaged.get("links"), dict) else {}
    links = {**links, "pr": pr_url}
    packaged["errors"] = _remove_resolved_builder_packaging_errors(packaged.get("errors"))
    packaged.update({
        "branch_name": branch_name,
        "commit_sha": commit_sha,
        "pr_url": pr_url,
        "links": links,
        "git_packaging": {**result, "status": "pr_created", "pr_url": pr_url},
    })
    return packaged


def _builder_concurrency_admission(mission, artifacts, execution_id):
    """Fail closed before Builder can touch a workspace or source file."""
    declared_files = declared_source_files(mission, artifacts)
    return build_admission(
        REPO_ROOT,
        str((mission or {}).get("mission_id") or ""),
        declared_files,
        holder=f"execution:{execution_id}:builder",
    )


def _release_builder_concurrency_admission(admission):
    admission = admission if isinstance(admission, dict) else {}
    lease = admission.get("lease") if isinstance(admission.get("lease"), dict) else {}
    canonical_root = str(admission.get("canonical_root") or "").strip()
    lease_id = str(lease.get("lease_id") or "").strip()
    if not canonical_root or not lease_id:
        return {"released": False, "status": "builder_lease_release_not_applicable"}
    return release_file_lease(canonical_root, lease_id)


def _runner_generated_path(path):
    normalized = str(path or "").replace("\\", "/").strip()
    return normalized == "planning/CODEX_CHAT.md" or normalized.startswith("test-results/") or normalized.startswith(".charlie_runner/")


def _preserve_builder_recovery_stash(run, result, mission):
    mission_id = str((mission or {}).get("mission_id") or "unknown").strip()
    stashed = run(["git", "stash", "push", "-u", "-m", f"CHARLIE recovery {mission_id}"])
    if stashed.get("returncode") != 0 or "No local changes" in str(stashed.get("stdout") or ""):
        return False
    reference = run(["git", "stash", "list", "-1", "--format=%gd"])
    stash_ref = str(reference.get("stdout") or "").strip()
    if stash_ref:
        result["recovery_stash"] = stash_ref
        result["recovery_stash_mission_id"] = mission_id
        result["worktree_cleaned_after_failure"] = True
        return True
    return False


def _remove_resolved_builder_packaging_errors(errors):
    cleaned = []
    for item in errors if isinstance(errors, list) else []:
        text = _artifact_text(item).lower()
        if (
            "could not create branch/commit/pr" in text
            or "git branch creation failed" in text
            or "permission denied creating .git/refs/heads" in text
            or "runner git packaging failed" in text
        ):
            continue
        cleaned.append(item)
    return cleaned


def _builder_packaging_failed(artifact, result, status):
    packaged = dict(artifact)
    packaging = {**result, "status": status}
    local_reviewable_statuses = {"git_push_failed", "gh_pr_create_failed", "pr_url_not_detected"}
    if status in local_reviewable_statuses and packaging.get("branch_name") and packaging.get("commit_sha"):
        packaged.update({
            "branch_name": packaged.get("branch_name") or packaging.get("branch_name"),
            "commit_sha": packaged.get("commit_sha") or packaging.get("commit_sha"),
            "git_packaging": {**packaging, "status": "local_commit_ready", "remote_status": status},
        })
        warnings = packaged.get("warnings") if isinstance(packaged.get("warnings"), list) else []
        warnings.append(f"Runner could not complete remote PR packaging ({status}); local branch commit is available for review.")
        packaged["warnings"] = warnings[-10:]
        packaged["errors"] = _remove_resolved_builder_packaging_errors(packaged.get("errors"))
        return packaged
    packaged["git_packaging"] = packaging
    errors = packaged.get("errors") if isinstance(packaged.get("errors"), list) else []
    if not any("runner git packaging failed" in str(item).lower() for item in errors):
        errors.append(f"Runner git packaging failed: {status}.")
    packaged["errors"] = errors
    return packaged


def _builder_packaging_is_terminal(packaging):
    packaging = packaging if isinstance(packaging, dict) else {}
    status = str(packaging.get("status") or "").strip().lower()
    if not packaging.get("attempted"):
        return False
    return status not in {"pr_created", "local_commit_ready"}


def _builder_branch_name(mission):
    mission = mission if isinstance(mission, dict) else {}
    suffix = str(mission.get("mission_id") or "")[-8:].lower() or "mission"
    title = re.sub(r"[^a-z0-9]+", "-", str(mission.get("title") or "charlie-build").lower()).strip("-")
    title = title[:44].strip("-") or "charlie-build"
    return f"charlie/{title}-{suffix}"


def _builder_commit_message(mission):
    title = str((mission or {}).get("title") or "CHARLIE mission").strip()
    return _truncate(f"Build {title}", 72)


def _builder_pr_body(mission, artifact, packaging):
    return "\n".join([
        f"Mission: {(mission or {}).get('mission_id', '')}",
        "",
        str(artifact.get("summary") or "Builder changes packaged by CHARLIE runner."),
        "",
        "Tests/evidence:",
        *[f"- {item}" for item in artifact.get("tests_run", []) if item],
        *[f"- {item}" for item in artifact.get("commands_run", []) if "test" in str(item).lower() or "check" in str(item).lower()],
        "",
        "Runner packaging:",
        f"- branch: {packaging.get('branch_name', '')}",
        "- Created by parent runner because Builder subprocess could not record PR evidence.",
    ]).strip()


def _extract_pr_url(value):
    match = re.search(r"https://github\.com/[^\s]+/pull/\d+", str(value or ""))
    return match.group(0).rstrip(").,") if match else ""


def _inherit_pr_reference(agent, artifact, artifacts):
    if agent == "builder" or _artifact_pr_reference(artifact):
        return artifact
    builder = artifacts.get("builder") if isinstance(artifacts.get("builder"), dict) else {}
    pr_reference = _artifact_pr_reference(builder)
    if not pr_reference:
        return artifact
    inherited = dict(artifact)
    links = inherited.get("links") if isinstance(inherited.get("links"), dict) else {}
    builder_links = builder.get("links") if isinstance(builder.get("links"), dict) else {}
    merged_links = {**builder_links, **links}
    if not merged_links.get("pr"):
        merged_links["pr"] = pr_reference
    inherited["links"] = merged_links
    inherited["pr_url"] = inherited.get("pr_url") or builder.get("pr_url") or merged_links.get("pr", "")
    inherited["pr_number"] = inherited.get("pr_number") or builder.get("pr_number") or ""
    expected_revision = str(builder.get("commit_sha") or (builder.get("git_packaging") or {}).get("commit_sha") or "").strip()
    if expected_revision:
        inherited["expected_revision"] = inherited.get("expected_revision") or expected_revision
        local_revision = _git_head_revision()
        if local_revision and (local_revision.lower().startswith(expected_revision.lower()) or expected_revision.lower().startswith(local_revision.lower())):
            inherited["tested_revision"] = inherited.get("tested_revision") or local_revision
    return inherited


def _git_head_revision(run_subprocess=None):
    runner = run_subprocess or subprocess.run
    try:
        completed = runner(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(REPO_ROOT),
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return str(completed.stdout or "").strip() if completed.returncode == 0 else ""


def _revision_evidence_quality_gate(agent, artifact):
    if agent not in {"tester", "qa_red_team", "visual_qa_reviewer", "product_reviewer", "business_reviewer", "security_reviewer", "evidence_reviewer", "reviewer"}:
        return {"passed": True, "reason": "revision_evidence_not_required"}
    expected = str(artifact.get("expected_revision") or "").strip().lower()
    tested = str(artifact.get("tested_revision") or "").strip().lower()
    if not expected or not re.fullmatch(r"[0-9a-f]{6,40}", expected):
        return {"passed": True, "reason": "no_packaged_revision_yet"}
    if tested and not re.fullmatch(r"[0-9a-f]{6,40}", tested):
        return {"passed": True, "reason": "tested_revision_not_packaged_evidence", "expected_revision": expected}
    if not tested:
        return {"passed": True, "reason": "revision_evidence_pending_final_reconciliation", "expected_revision": expected}
    if not (tested.startswith(expected) or expected.startswith(tested)):
        return {
            "passed": False,
            "reason": f"{agent} reviewed wrong revision: expected {expected}, tested {tested}.",
            "expected_revision": expected,
            "tested_revision": tested,
        }
    return {
        "passed": True,
        "reason": "exact_revision_verified",
        "expected_revision": expected,
        "tested_revision": tested,
    }


def _has_release_relevant_changes(changed_files):
    files = [str(item or "").strip() for item in (changed_files if isinstance(changed_files, list) else [])]
    ignored = {"No changed files detected by git diff.", ""}
    return any(path not in ignored for path in files)


def _agent_backflow_target(agent, artifact, quality):
    if agent == "tester":
        return "builder"
    if agent in {"risk_agent", "visual_qa_reviewer", "product_reviewer", "business_reviewer", "security_reviewer", "evidence_reviewer"}:
        target = str(artifact.get("send_back_stage") or "").strip().lower()
        if target in all_agent_names():
            return target
        if _artifact_has_ui_evidence(artifact):
            return "frontend_design_implementer"
        return "builder"
    if agent == "qa_red_team":
        target = str(artifact.get("send_back_stage") or "").strip().lower()
        return target if target in {"builder", "tester", "reviewer"} else "builder"
    if agent == "reviewer":
        target = str(artifact.get("send_back_stage") or "").strip().lower()
        return target if target in all_agent_names() else "builder"
    return ""


def _resolve_agent_backflow_target(target_agent, agent_sequence=None):
    target_agent = str(target_agent or "").strip().lower()
    agent_sequence = list(agent_sequence or AGENT_SEQUENCE)
    if target_agent in agent_sequence:
        return target_agent
    if target_agent == "frontend_design_implementer" and "builder" in agent_sequence:
        return "builder"
    return ""


def _artifact_has_ui_evidence(artifact):
    if _artifact_explicitly_non_ui(artifact):
        return False
    keys = (
        "visual_acceptance_decision",
        "visual_review_notes",
        "media_references_used",
        "screenshots_captured",
        "browser_checks",
        "reference_match_assessment",
    )
    if any(key in artifact and _artifact_has_list_value(artifact, key) for key in keys):
        return True
    text = " ".join(
        str(artifact.get(key) or "")
        for key in ("summary", "stdout_tail", "stderr_tail", "next_action")
    ).lower()
    return any(term in text for term in ("ui", "visual", "screenshot", "browser", "/charlie", "dashboard"))


def _artifact_explicitly_non_ui(artifact):
    artifact = artifact if isinstance(artifact, dict) else {}
    values = []
    for key in (
        "summary",
        "stdout_tail",
        "stderr_tail",
        "next_action",
        "visual_reference_analysis",
        "reference_match_assessment",
    ):
        value = artifact.get(key)
        if isinstance(value, list):
            values.extend(str(item or "") for item in value)
        elif value:
            values.append(str(value))
    for key in ("visual_review_notes", "media_references_used", "browser_checks", "screenshots_captured"):
        value = artifact.get(key)
        if isinstance(value, list):
            values.extend(str(item or "") for item in value)
    return explicit_non_ui_requested(" ".join(values))


def _append_backflow_event(ledger, from_agent, to_agent, reason, attempt, artifact=None, quality=None, fingerprint="", loop_detected=False):
    unresolved = _artifact_issue_items(from_agent, artifact, quality)
    fingerprint = fingerprint or _backflow_fingerprint(from_agent, to_agent, reason, artifact)
    event = {
        "from_agent": from_agent,
        "to_agent": to_agent,
        "reason": reason,
        "attempt": int(attempt or 1),
        "fingerprint": fingerprint,
        "loop_detected": bool(loop_detected),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "unresolved_blockers": unresolved,
        "next_action": str((artifact or {}).get("next_action") or "").strip() if isinstance(artifact, dict) else "",
        "artifact_path": str((artifact or {}).get("artifact_path") or "").strip() if isinstance(artifact, dict) else "",
    }
    ledger.setdefault("backflow_events", []).append(event)
    ledger["unresolved_blockers"] = unresolved
    ledger["last_backflow"] = event
    ledger["last_progress_at"] = event["recorded_at"]
    return event


def _backflow_fingerprint(from_agent, to_agent, reason, artifact=None):
    artifact = artifact if isinstance(artifact, dict) else {}
    items = _artifact_issue_items(str(from_agent or ""), artifact)
    issue_signatures = sorted({_stable_blocker_signature(item) for item in items if _stable_blocker_signature(item)})
    criteria = artifact.get("acceptance_criteria") if isinstance(artifact.get("acceptance_criteria"), list) else []
    criterion_signatures = sorted({_stable_blocker_signature(item) for item in criteria if _stable_blocker_signature(item)})
    combined = _stable_blocker_signature(" ".join([str(reason or ""), *[str(item) for item in items], *[str(item) for item in criteria]]))
    raw = "|".join([
        str(from_agent or "").strip().lower(),
        str(to_agent or "").strip().lower(),
        combined if "+" in combined else _stable_blocker_signature(reason),
        "" if "+" in combined else ",".join(issue_signatures),
        "" if "+" in combined else ",".join(criterion_signatures),
    ])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _stable_blocker_signature(value):
    if isinstance(value, dict):
        value = value.get("criterion_id") or value.get("requirement_id") or value.get("finding") or value.get("summary") or value.get("message") or value
    text = str(value or "").lower()
    families = []
    vocabulary = {
        "lifecycle_matrix": ("lifecycle", "transition matrix", "status transition"),
        "canonical_order_linkage": ("canonical order", "order linkage", "order creation", "order id"),
        "order_deep_link": ("deep-link", "deep link", "/orders/", "named action"),
        "typed_extension": ("typed", "extension", "meat readiness"),
        "focused_tests": ("focused test", "test evidence", "acceptance evidence"),
        "visual_evidence": ("screenshot", "visual evidence", "browser evidence"),
        "security": ("security", "authorization", "permission", "secret"),
    }
    for family, terms in vocabulary.items():
        if any(term in text for term in terms):
            families.append(family)
    if len(families) > 1 and "focused_tests" in families:
        families.remove("focused_tests")
    if families:
        return "+".join(sorted(set(families)))
    normalized = re.sub(r"\b(?:attempt|run|try|repeat|occurrence)\s*#?\d+\b", "", text)
    normalized = re.sub(r"\b\d+(?:\.\d+)?\b", "#", normalized)
    normalized = re.sub(r"[^a-z0-9_/#]+", " ", normalized)
    return " ".join(normalized.split())[:180]


def _backflow_fingerprint_count(ledger, fingerprint):
    if not fingerprint or not isinstance(ledger, dict):
        return 0
    events = ledger.get("backflow_events") if isinstance(ledger.get("backflow_events"), list) else []
    return sum(1 for event in events if isinstance(event, dict) and event.get("fingerprint") == fingerprint)


def _durable_backflow_fingerprint_count(mission, fingerprint):
    """Count how many times this exact blocker loop already fired across ALL
    prior runner sessions for this mission, using durable mission memory.

    The per-run ledger resets every session, so a loop that repeats after a
    runner restart used to reset its counter and could churn overnight. Mission
    memory persists in mission metadata, so counting backflow fingerprints here
    makes the hard-loop cap mission-durable: a repeated blocker converts to an
    honest owner-review block instead of an infinite cross-session retry.
    """
    if not fingerprint or not isinstance(mission, dict):
        return 0
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    memory = mission_memory_from_metadata(metadata)
    events = memory.get("events") if isinstance(memory.get("events"), list) else []
    count = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        if str(event.get("type") or "").strip().lower() != "agent_backflow":
            continue
        event_metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        if event_metadata.get("backflow_fingerprint") == fingerprint:
            count += 1
    return count


def _bounded_internal_recovery(mission_id, agent, blocked_reason, artifact, disposition, mission=None, database_url=None, connect_factory=None):
    disposition = dict(disposition if isinstance(disposition, dict) else {})
    fingerprint = _backflow_fingerprint(agent, disposition.get("responsible_stage") or agent, blocked_reason, artifact)
    loaded_mission = mission if isinstance(mission, dict) else {}
    if not loaded_mission and mission_id:
        loaded, status_code = get_mission(mission_id, database_url=database_url, connect_factory=connect_factory)
        if status_code < 400:
            loaded_mission = loaded.get("mission") or {}
    metadata = loaded_mission.get("metadata") if isinstance(loaded_mission.get("metadata"), dict) else {}
    memory = mission_memory_from_metadata(metadata)
    pattern = (memory.get("recurring_block_patterns") or {}).get(f"fingerprint:{fingerprint}") or {}
    prior_count = int(pattern.get("count") or 0)
    occurrence = prior_count + 1
    capped = bool(disposition.get("recoverable")) and occurrence >= 2
    if capped:
        disposition.update({
            "block_class": "recovery_attempts_exhausted",
            "recoverable": False,
            "owner_required": True,
            "responsible_stage": "owner",
            "recovery_cap_reached": True,
            "reason": f"Repeated internal recovery stopped after {occurrence} identical occurrences: {blocked_reason}",
        })
    return disposition, {
        "fingerprint": fingerprint,
        "prior_count": prior_count,
        "occurrence": occurrence,
        "capped": capped,
    }


def _loop_recovery_next_action(agent, backflow_target, reason, artifact):
    artifact = artifact if isinstance(artifact, dict) else {}
    base = str(artifact.get("next_action") or "").strip()
    details = [
        f"Stop automatic retries for the repeated {agent} -> {backflow_target} blocker.",
        f"Blocker: {reason}",
        "Create a precise recovery mission or owner send-back with the unresolved blocker, affected files, tests run, and expected proof before rerunning.",
    ]
    if base:
        details.append(f"Agent requested action: {base}")
    return " ".join(details)


def _discard_downstream_artifacts(artifacts, target_agent, agent_sequence=None):
    agent_sequence = agent_sequence or list(AGENT_SEQUENCE)
    target_agent = _resolve_agent_backflow_target(target_agent, agent_sequence) or (agent_sequence[0] if agent_sequence else "")
    if not target_agent:
        return artifacts
    target_index = agent_sequence.index(target_agent)
    return {
        agent: artifact
        for agent, artifact in artifacts.items()
        if agent in agent_sequence and agent_sequence.index(agent) < target_index
    }


def _agent_queue_from(target_agent, agent_sequence=None):
    agent_sequence = agent_sequence or list(AGENT_SEQUENCE)
    target_agent = _resolve_agent_backflow_target(target_agent, agent_sequence) or (agent_sequence[0] if agent_sequence else "")
    if not target_agent:
        return []
    target_index = agent_sequence.index(target_agent)
    return list(agent_sequence[target_index:])


def _targeted_agent_queue(mission, start_agent, agent_sequence=None):
    agent_sequence = list(agent_sequence or _mission_agent_sequence(mission))
    queue = _agent_queue_from(start_agent, agent_sequence)
    metadata = mission.get("metadata") if isinstance(mission, dict) and isinstance(mission.get("metadata"), dict) else {}
    targeted = metadata.get("targeted_invalidation") if isinstance(metadata.get("targeted_invalidation"), dict) else {}
    preserved = {str(agent or "").strip().lower() for agent in targeted.get("preserved_agents") or []}
    if preserved:
        queue = [agent for agent in queue if agent == start_agent or agent not in preserved]
    return queue, preserved


def _block_agent_stage(
    mission_id,
    execution_id,
    ledger,
    agent,
    paths,
    completed,
    started_at,
    blocked_reason="Agent did not produce a valid final artifact.",
    artifact=None,
    artifacts=None,
    database_url=None,
    connect_factory=None,
):
    artifact = artifact if isinstance(artifact, dict) else {}
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    if artifact and agent not in artifacts:
        artifacts = {**artifacts, agent: artifact}
    disposition = classify_block(agent, blocked_reason, artifact)
    disposition, recovery_repeat = _bounded_internal_recovery(
        mission_id, agent, blocked_reason, artifact, disposition,
        database_url=database_url, connect_factory=connect_factory,
    )
    unresolved = _artifact_issue_items(agent, artifact)
    if unresolved:
        ledger["unresolved_blockers"] = unresolved
    blocked_summary = _blocked_review_summary(agent, blocked_reason, ledger, artifact)
    blocked_artifact = {
        "summary": artifact.get("summary") or blocked_reason,
        "returncode": getattr(completed, "returncode", None),
        "stdout_excerpt": _truncate(getattr(completed, "stdout", "") or _read_text(paths["stdout_path"]), 1200),
        "stderr_excerpt": _truncate(getattr(completed, "stderr", "") or _read_text(paths["stderr_path"]), 1200),
        "files_inspected": artifact.get("files_inspected", []),
        "commands_run": artifact.get("commands_run", []),
        "changed_files": artifact.get("changed_files", []),
        "stdout_tail": artifact.get("stdout_tail", ""),
        "stderr_tail": artifact.get("stderr_tail", ""),
        "quality_gate": artifact.get("quality_gate", {}),
        "implementation_source_map": artifact.get("implementation_source_map", {}),
        "files_checked_against_source_map": artifact.get("files_inspected", []),
    }
    ledger["status"] = "blocked"
    ledger["blocked_agent"] = agent
    ledger["blocked_reason"] = blocked_reason
    ledger["completed_at"] = datetime.now(timezone.utc).isoformat()
    _append_ledger_stage(ledger, agent, "blocked", started_at, paths, artifact=blocked_artifact, attempt=_stage_attempt_from_path(paths["final_path"]))
    ledger_path = _write_agent_ledger(paths["final_path"].parent, execution_id, ledger)
    qa_artifact = artifacts.get("qa_red_team") if isinstance(artifacts.get("qa_red_team"), dict) else {}
    blocked_findings = [
        f"{agent} blocked the mission: {blocked_reason}",
        "The mission is in Owner Review so the owner can inspect evidence and send it back deliberately.",
    ]
    if artifact.get("bugs"):
        blocked_findings.extend([f"Bug: {item}" for item in artifact.get("bugs", []) if item])
    if artifact.get("qa_findings"):
        blocked_findings.extend([f"QA: {item}" for item in artifact.get("qa_findings", []) if item])
    blocked_findings.extend(_issue_lines(unresolved))
    recovery_packet = _partial_work_recovery_packet(
        artifact.get("changed_files") or _changed_files(),
        stdout_text=getattr(completed, "stdout", "") or _read_text(paths["stdout_path"]),
        stderr_text=getattr(completed, "stderr", "") or _read_text(paths["stderr_path"]),
    )
    full_recovery_packet = build_recovery_packet(
        agent=agent,
        blocked_reason=blocked_reason,
        artifact=artifact,
        ledger=ledger,
        changed_files=artifact.get("changed_files") or _changed_files(),
        stdout_text=getattr(completed, "stdout", "") or _read_text(paths["stdout_path"]),
        stderr_text=getattr(completed, "stderr", "") or _read_text(paths["stderr_path"]),
    )
    full_recovery_packet["disposition"] = disposition
    _record_mission_memory_event(
        {"mission_id": mission_id},
        build_memory_event(
            agent,
            "agent_blocked",
            summary=f"{agent} blocked: {blocked_reason}",
            attempt=_stage_attempt_from_path(paths["final_path"]),
            artifact={**artifact, "next_action": artifact.get("next_action") or recovery_packet.get("recommended_next_action", "")},
            quality_gate=artifact.get("quality_gate", {}),
            recovery=recovery_packet,
            metadata={"execution_id": execution_id, "backflow_fingerprint": recovery_repeat["fingerprint"], "recovery_occurrence": recovery_repeat["occurrence"]},
        ),
        database_url=database_url,
        connect_factory=connect_factory,
    )
    update_mission_vault(
        mission_id,
        {
            "agent_execution": ledger,
            "review_packet": {
                "summary": f"CHARLIE Agent Runner v2 blocked at {agent}: {blocked_reason}",
                "blocked_summary": blocked_summary,
                "findings": blocked_findings,
                "errors": [blocked_reason, *_collect_artifact_list(artifacts, "errors")],
                "bugs": _collect_artifact_list(artifacts, "bugs"),
                "changed_files": artifact.get("changed_files") or _changed_files() or ["No changed files detected by git diff."],
                "test_evidence": ["Agent workflow stopped before final tester/reviewer evidence."],
                "qa_evidence": qa_artifact.get("qa_findings") or artifact.get("qa_findings") or [],
                "links": {},
                "execution_artifacts": {
                    "execution_id": execution_id,
                    "agent_ledger_path": str(ledger_path),
                    "blocked_agent": agent,
                    "blocked_artifact_path": str(paths["final_path"]),
                    "stdout_excerpt": blocked_artifact.get("stdout_excerpt", ""),
                    "stderr_excerpt": blocked_artifact.get("stderr_excerpt", ""),
                    "returncode": blocked_artifact.get("returncode"),
                },
                "agent_execution": _agent_execution_summary(ledger),
                "agent_artifacts": _compact_agent_artifacts_for_review(artifacts),
                "unresolved_blockers": unresolved,
                "normalized_findings": normalize_findings(unresolved, agent=agent, artifact=artifact),
                "implementation_source_map": artifact.get("implementation_source_map", {}),
                "files_checked_against_source_map": artifact.get("files_inspected", []),
                "handoff_reports": {
                    stage_agent: stage_artifact.get("handoff_report", {})
                    for stage_agent, stage_artifact in artifacts.items()
                    if isinstance(stage_artifact, dict)
                },
                "quality_gates": ledger.get("quality_gates", []),
                "backflow_events": ledger.get("backflow_events", []),
                "partial_recovery": recovery_packet,
                "recovery_packet": full_recovery_packet,
                "blocked_agent": agent,
                "blocked_reason": blocked_reason,
                "block_disposition": disposition,
                "recovery_repeat": recovery_repeat,
                "recommended_next_action": artifact.get("next_action") or (
                    f"CORE will recover from {disposition['responsible_stage']}."
                    if disposition["recoverable"]
                    else f"Owner decision required at {agent}."
                ),
                "review_status": "internal_recovery_queued" if disposition["recoverable"] else "agent_blocked",
            },
        },
        notes="CHARLIE Agent Runner v2 recorded a blocked stage.",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    _record_execution_stage(mission_id, agent, "blocked", blocked_reason, database_url=database_url, connect_factory=connect_factory)
    next_status = "approved" if disposition["recoverable"] else "blocked"
    owner_decision = "" if disposition["recoverable"] else f"CHARLIE Agent Runner v2 blocked at {agent}."
    blocked, blocked_status = update_mission_status(
        mission_id,
        next_status,
        owner_decision=owner_decision,
        event_type="status_changed",
        notes=blocked_reason,
        metadata={
            "agent_runner_version": AGENT_RUNNER_VERSION,
            "execution_id": execution_id,
            "blocked_agent": agent,
            "block_class": disposition["block_class"],
            "recovery_stage": disposition["responsible_stage"],
            "recovery_fingerprint": recovery_repeat["fingerprint"],
            "recovery_occurrence": recovery_repeat["occurrence"],
        },
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if blocked_status >= 400:
        return blocked, blocked_status
    return {
        "success": disposition["recoverable"],
        "status": "agent_stage_recovery_queued" if disposition["recoverable"] else "agent_stage_blocked",
        "mission_id": mission_id,
        "mission_status": next_status,
        "agent": agent,
        "blocked_reason": blocked_reason,
        "block_disposition": disposition,
        "agent_ledger_path": str(ledger_path),
    }, 202 if disposition["recoverable"] else 504


def _blocked_review_summary(agent, blocked_reason, ledger, artifact):
    ledger = ledger if isinstance(ledger, dict) else {}
    artifact = artifact if isinstance(artifact, dict) else {}
    stages = ledger.get("stages") if isinstance(ledger.get("stages"), list) else []
    last_complete = ""
    for stage in reversed(stages):
        if isinstance(stage, dict) and stage.get("status") == "complete":
            last_complete = str(stage.get("agent") or "")
            break
    backflows = ledger.get("backflow_events") if isinstance(ledger.get("backflow_events"), list) else []
    unresolved = _artifact_issue_items(agent, artifact)
    return {
        "blocked_at": agent,
        "reason": blocked_reason,
        "send_back_attempts": len(backflows),
        "last_successful_stage": last_complete,
        "unresolved_blockers": unresolved,
        "recommended_action": artifact.get("next_action") or f"Send back to {_agent_backflow_target(agent, artifact, {'passed': False, 'reason': blocked_reason}) or 'builder'} after reviewing these blockers.",
        "human_summary": f"{agent} blocked after {len(backflows)} automatic send-back attempt{'s' if len(backflows) != 1 else ''}.",
    }


def _complete_agent_execution_v2(mission, execution_id, ledger, artifacts, output_dir, started_at, database_url=None, connect_factory=None):
    ledger["status"] = "complete"
    ledger["completed_at"] = datetime.now(timezone.utc).isoformat()
    ledger_path = _write_agent_ledger(output_dir, execution_id, ledger)
    reviewer = artifacts.get("reviewer", {})
    tester = artifacts.get("tester", {})
    builder = artifacts.get("builder", {})
    qa = artifacts.get("qa_red_team", {})
    reviewer_links = reviewer.get("links") if isinstance(reviewer.get("links"), dict) else {}
    changed_files = reviewer.get("changed_files") or builder.get("changed_files") or _changed_files() or ["No changed files detected by git diff."]
    local_preview = _local_preview_from_reviewer(reviewer)
    visual_review = _build_visual_review_packet(
        mission_id=mission.get("mission_id", ""),
        mission_type=mission.get("mission_type", ""),
        changed_files=changed_files,
        local_preview=local_preview,
        artifacts=artifacts,
        final_message=reviewer.get("summary", ""),
        mission=mission,
    )
    if _visual_review_blocks_owner_review(visual_review):
        blocked_reason = _visual_review_block_reason(visual_review)
        block_artifact = {
            **reviewer,
            "summary": blocked_reason,
            "bugs": [
                *[item for item in (reviewer.get("bugs") or []) if item],
                "UI mission reached review without captured Visual Review media.",
            ],
            "errors": [blocked_reason],
            "changed_files": changed_files,
            "quality_gate": {"passed": False, "reason": blocked_reason},
            "visual_review": visual_review,
            "next_action": "Send back to reviewer/builder after making local preview capture produce clickable Visual Review media.",
        }
        return _block_completed_agent_review(
            mission=mission,
            execution_id=execution_id,
            ledger=ledger,
            agent="reviewer",
            artifact=block_artifact,
            artifacts={**artifacts, "reviewer": block_artifact},
            ledger_path=ledger_path,
            output_dir=output_dir,
            blocked_reason=blocked_reason,
            database_url=database_url,
            connect_factory=connect_factory,
        )
    brain_guard = _brain_guard_review_gate(mission, artifacts, changed_files, ledger=ledger)
    if not brain_guard["passed"]:
        blocked_reason = brain_guard["reason"]
        block_artifact = {
            **reviewer,
            "summary": blocked_reason,
            "bugs": [
                *[item for item in (reviewer.get("bugs") or []) if item],
                *brain_guard.get("findings", []),
            ],
            "errors": [blocked_reason],
            "changed_files": changed_files,
            "quality_gate": {"passed": False, "reason": blocked_reason, "brain_guard": brain_guard},
            "brain_guard": brain_guard,
            "next_action": "Send back to the responsible stage and update/cite the Vault Brain before owner review.",
        }
        return _block_completed_agent_review(
            mission=mission,
            execution_id=execution_id,
            ledger=ledger,
            agent="brain_guard",
            artifact=block_artifact,
            artifacts={**artifacts, "brain_guard": block_artifact},
            ledger_path=ledger_path,
            output_dir=output_dir,
            blocked_reason=blocked_reason,
            database_url=database_url,
            connect_factory=connect_factory,
        )
    review_links = dict(reviewer_links)
    review_links["local_preview"] = review_links.get("local_preview") or local_preview.get("url", "")
    review_board = build_review_board_packet(mission, artifacts)
    normalized_vault_writes = _write_normalized_vault_records(
        mission,
        execution_id=execution_id,
        ledger=ledger,
        artifacts=artifacts,
        brain_guard=brain_guard,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    mission_quality = score_mission_quality(
        mission,
        {
            "review_status": "ready_for_owner_review",
            "changed_files": changed_files,
            "test_evidence": reviewer.get("test_evidence") or tester.get("tests_run") or [],
            "local_preview": local_preview,
            "visual_review": visual_review,
            "links": review_links,
            "pr_url": reviewer.get("pr_url") or review_links.get("pr") or review_links.get("pull_request") or "",
            "quality_gates": ledger.get("quality_gates", []),
            "backflow_events": ledger.get("backflow_events", []),
            "brain_guard": brain_guard,
            "normalized_vault_writes": normalized_vault_writes,
            "review_board": review_board,
            "agent_artifacts": artifacts,
        },
        ledger,
    )
    candidate_manifest = build_candidate_manifest(
        mission,
        artifacts,
        source_commit=_release_candidate_revision_sha(mission, artifacts),
    )
    evidence_reconciliation = resolve_effective_agent_results(
        artifacts,
        candidate_manifest,
        workflow=mission.get("agent_workflow"),
        judgement=_judgement_evidence_quality_gate,
    )
    existing_review_packet = (
        mission.get("metadata", {}).get("review_packet", {})
        if isinstance(mission.get("metadata"), dict)
        and isinstance(mission.get("metadata", {}).get("review_packet"), dict)
        else {}
    )
    artifact_history = [
        *list(existing_review_packet.get("agent_artifact_history") or []),
        *[artifact for artifact in artifacts.values() if isinstance(artifact, dict)],
    ][-120:]
    candidate_revision = str(candidate_manifest.get("source_commit") or "").strip()
    protected_operations = []
    if any(str(path or "").replace("\\", "/").startswith("supabase/migrations/") for path in changed_files):
        protected_operations.append({
            "operation": "apply_migration",
            "status": "owner_gated",
            "candidate_revision": candidate_revision,
            "note": "Approving this PR does not authorize applying the migration.",
        })
    review_packet = {
        "review_packet": {
            "summary": reviewer.get("summary") or "CHARLIE Agent Runner v2 completed all stages.",
            "findings": _artifact_stage_summaries(artifacts, _mission_agent_sequence(mission)),
            "errors": _collect_artifact_list(artifacts, "errors"),
            "bugs": _collect_artifact_list(artifacts, "bugs"),
            "changed_files": changed_files,
            "test_evidence": reviewer.get("test_evidence") or tester.get("tests_run") or ["Tester artifact did not list tests."],
            "qa_evidence": reviewer.get("qa_evidence") or qa.get("qa_findings") or [],
            "local_preview": local_preview,
            "visual_review": visual_review,
            "links": review_links,
            "pr_url": reviewer.get("pr_url") or review_links.get("pr") or review_links.get("pull_request") or "",
            "pr_number": reviewer.get("pr_number") or "",
            "release_notes": reviewer.get("release_notes") or ["Review Agent Runner v2 artifacts before final approval."],
            "recommended_owner_decision": reviewer.get("recommended_owner_decision", "approve_final_release"),
            "execution_artifacts": {
                "execution_id": execution_id,
                "agent_runner_version": AGENT_RUNNER_VERSION,
                "agent_ledger_path": str(ledger_path),
                "started_at": started_at,
                "completed_at": ledger["completed_at"],
            },
            "agent_execution": _agent_execution_summary(ledger),
            "mission_memory": memory_prompt_context(mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}),
            "final_artifact_contract": final_artifact_contract_packet(),
            "partial_recovery_contract": partial_recovery_contract_packet(),
            "quality_gates": ledger.get("quality_gates", []),
            "backflow_events": ledger.get("backflow_events", []),
            "brain_guard": brain_guard,
            "normalized_vault_writes": normalized_vault_writes,
            "mission_quality": mission_quality,
            "candidate_manifest": candidate_manifest,
            "tested_revision": candidate_revision,
            "protected_operations": protected_operations,
            "evidence_reconciliation": evidence_reconciliation,
            "active_blockers": evidence_reconciliation.get("active_blockers", []),
            "resolved_findings": evidence_reconciliation.get("resolved_findings", []),
            "follow_up_findings": evidence_reconciliation.get("follow_ups", []),
            "evidence_requiring_refresh": evidence_reconciliation.get("requires_revalidation", []),
            "recommended_action": evidence_reconciliation.get("recommended_action", {}),
            "repo_test_command_memory": repo_test_command_memory(changed_files),
            "agent_artifacts": _compact_agent_artifacts_for_review(artifacts),
            "agent_artifact_history": artifact_history,
            "handoff_reports": {
                agent: artifact.get("handoff_report", {})
                for agent, artifact in artifacts.items()
                if isinstance(artifact, dict)
            },
            "review_board": review_board,
            "core_readiness": evaluate_core_readiness({
                **mission,
                "metadata": {
                    **(mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}),
                    "review_packet": {"review_board": review_board},
                },
            }),
            "review_status": "ready_for_owner_review",
            **(
                {"owner_review_gate_failure": existing_review_packet["owner_review_gate_failure"]}
                if isinstance(existing_review_packet.get("owner_review_gate_failure"), dict)
                else {}
            ),
        },
        "agent_execution": ledger,
    }
    github_gate = _build_github_finalization_gate(mission, review_packet["review_packet"], candidate_revision)
    review_packet["review_packet"]["github_gate"] = github_gate
    workflow_ready, workflow_status = _verify_owner_review_artifacts_ready(mission, artifacts)
    if workflow_ready and not github_gate.get("passed"):
        workflow_ready = False
        workflow_status = {
            "blocked_agent": "publisher",
            "reason": "GitHub finalisation gate failed: " + ", ".join(github_gate.get("reasons") or ["unknown GitHub state"]),
            "github_gate": github_gate,
        }
    if not workflow_ready:
        blocked_agent = str(workflow_status.get("blocked_agent") or "reviewer")
        blocked_reason = str(workflow_status.get("reason") or "Owner-review workflow is not fully passing.")
        gate_failure = _owner_review_gate_failure(mission, blocked_agent, blocked_reason, workflow_status)
        incident_halted = gate_failure["occurrence"] >= 2
        review_status = "system_incident_halted" if incident_halted else "workflow_not_ready"
        if incident_halted:
            blocked_reason = (
                f"Repeated owner-review evidence recovery halted after {gate_failure['occurrence']} identical "
                f"occurrences: {blocked_reason}"
            )
        disposition = classify_block(blocked_agent, blocked_reason, workflow_status)
        disposition["responsible_stage"] = blocked_agent
        disposition["recoverable"] = not incident_halted
        disposition["owner_required"] = False
        if incident_halted:
            disposition["block_class"] = "system_incident_halted"
            disposition["recovery_cap_reached"] = True
        blocked_review_packet = dict(review_packet["review_packet"])
        blocked_review_packet.update({
            "review_status": review_status,
            "blocked_agent": blocked_agent,
            "blocked_reason": blocked_reason,
            "return_to_stage": blocked_agent,
            "block_disposition": disposition,
            "owner_review_gate_failure": gate_failure,
            "recommended_next_action": (
                "Automatic recovery is halted. Repair the repeated evidence reconciliation condition before resuming."
                if incident_halted
                else f"CORE will perform one targeted recheck at {blocked_agent}."
            ),
        })
        if isinstance(workflow_status.get("evidence_reconciliation"), dict):
            blocked_review_packet["evidence_reconciliation"] = workflow_status["evidence_reconciliation"]
        blocked_result, blocked_status = transition_mission_review_state(
            mission["mission_id"],
            "blocked",
            blocked_review_packet,
            expected_status="in_progress",
            owner_decision=blocked_reason,
            notes="CORE refused pr_ready because at least one configured workflow stage was not complete.",
            database_url=database_url,
            connect_factory=connect_factory,
        )
        if blocked_status >= 400:
            return blocked_result, blocked_status
        return {
            "success": False,
            "status": "owner_review_workflow_not_ready",
            "mission_id": mission["mission_id"],
            "mission_status": "blocked",
            "blocked_agent": blocked_agent,
            "blocked_reason": blocked_reason,
            "agent_ledger_path": str(ledger_path),
        }, 200
    ready_result, ready_status = finalize_owner_review_transaction(
        mission["mission_id"],
        review_packet["review_packet"],
        execution_id=execution_id,
        candidate_revision=candidate_revision,
        expected_status="in_progress",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if ready_status >= 400:
        return ready_result, ready_status
    return {
        "success": True,
        "status": "agent_execution_completed",
        "mission_id": mission["mission_id"],
        "mission_status": "pr_ready",
        "execution_id": execution_id,
        "agent_runner_version": AGENT_RUNNER_VERSION,
        "agent_ledger_path": str(ledger_path),
    }, 200


def _build_github_finalization_gate(mission, review_packet, candidate_revision):
    """Return machine-verified PR evidence bound to the tested revision."""
    candidate = str(candidate_revision or "").strip()
    reference = mission_pr_reference({
        **(mission if isinstance(mission, dict) else {}),
        "metadata": {
            **((mission or {}).get("metadata") if isinstance((mission or {}).get("metadata"), dict) else {}),
            "review_packet": review_packet if isinstance(review_packet, dict) else {},
        },
    })
    state = query_pr_state(reference)
    checks = state.get("statusCheckRollup") if isinstance(state.get("statusCheckRollup"), list) else []
    conclusions = [
        str(item.get("conclusion") or item.get("state") or item.get("status") or "").strip().upper()
        for item in checks if isinstance(item, dict)
    ]
    reasons = []
    if not state.get("success"):
        reasons.append(str(state.get("status") or "pr_query_failed"))
    if str(state.get("state") or "").upper() != "OPEN":
        reasons.append("pr_not_open")
    if str(state.get("mergeable") or "").upper() != "MERGEABLE":
        reasons.append("pr_not_mergeable")
    if not checks:
        reasons.append("pr_checks_missing")
    elif any(value not in PASSING_CHECK_CONCLUSIONS for value in conclusions):
        reasons.append("pr_checks_not_passing")
    head_revision = str(state.get("headRefOid") or "").strip()
    if not candidate or head_revision != candidate:
        reasons.append("pr_head_candidate_mismatch")
    return {
        "version": "charlie_github_finalization_gate_v1",
        "passed": not reasons,
        "reasons": reasons,
        "pr_reference": reference,
        "pr_number": state.get("number"),
        "pr_url": state.get("url") or reference,
        "state": state.get("state"),
        "mergeable": state.get("mergeable"),
        "head_revision": head_revision,
        "check_conclusions": conclusions,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _verify_owner_review_artifacts_ready(mission, artifacts):
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    sequence = _mission_agent_sequence(mission if isinstance(mission, dict) else {})
    if not sequence:
        return False, {"reason": "Owner-review workflow is empty."}
    # Older stored missions predate candidate-bound lineage. Preserve their
    # established gate until a targeted rerun creates versioned evidence.
    if not any(
        isinstance(artifact, dict) and isinstance(artifact.get("evidence_lineage"), dict)
        for artifact in artifacts.values()
    ):
        for agent in sequence:
            artifact = artifacts.get(agent) if isinstance(artifacts.get(agent), dict) else {}
            if not artifact:
                continue
            judgement = _judgement_evidence_quality_gate(agent, artifact)
            if not judgement.get("passed"):
                return False, {
                    "blocked_agent": agent,
                    "stage_status": "non_passing",
                    "reason": f"Owner review is not ready: {agent} is non-passing ({judgement.get('reason') or 'quality gate failed'}).",
                    "legacy_evidence": True,
                }
        return True, {"reason": "all_workflow_artifacts_passing", "legacy_evidence": True}
    manifest = build_candidate_manifest(
        mission,
        artifacts,
        source_commit=_release_candidate_revision_sha(mission, artifacts),
    )
    reconciliation = resolve_effective_agent_results(
        artifacts,
        manifest,
        # A targeted resume intentionally omits already-completed prefix stages.
        # Validate every artifact participating in this candidate without
        # manufacturing missing-evidence blockers for stages outside this run.
        workflow=[{"agent": agent} for agent in sequence if agent in artifacts],
        judgement=_judgement_evidence_quality_gate,
    )
    if reconciliation.get("active_blockers"):
        blocker = reconciliation["active_blockers"][0]
        return False, {
            "blocked_agent": blocker.get("agent") or "reviewer",
            "stage_status": "current_candidate_non_passing",
            "reason": f"Owner review is not ready: {blocker.get('agent') or 'reviewer'} has a current applicable blocker ({blocker.get('reason') or 'quality gate failed'}).",
            "evidence_reconciliation": reconciliation,
        }
    if reconciliation.get("requires_revalidation"):
        refresh = reconciliation["requires_revalidation"][0]
        return False, {
            "blocked_agent": refresh.get("agent") or "reviewer",
            "stage_status": "targeted_recheck_required",
            "reason": f"Owner review needs a targeted {refresh.get('agent') or 'reviewer'} recheck for the current release candidate ({refresh.get('reason')}).",
            "evidence_reconciliation": reconciliation,
        }
    return True, {"reason": "current_candidate_evidence_passing", "evidence_reconciliation": reconciliation}


def _verify_owner_review_packet_persisted(mission_id, *, database_url=None, connect_factory=None):
    result, status_code = get_mission(
        mission_id,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status_code >= 400 or not result.get("success"):
        return False, str(result.get("status") or f"mission_read_failed_{status_code}")
    mission = result.get("mission") if isinstance(result.get("mission"), dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    review_status = str(review_packet.get("review_status") or "").strip()
    if review_status == "ready_for_owner_review":
        return True, "review_packet_verified"
    if review_packet.get("blocked_reason") or review_packet.get("blocked_agent"):
        if mission.get("status") == "blocked":
            return True, "blocked_review_packet_verified"
        return False, "stale_blocked_review_packet_after_write"
    if review_status:
        return False, f"stale_review_packet_status_{review_status}"
    return False, "review_packet_missing_after_write"


def _visual_review_blocks_owner_review(visual_review):
    visual_review = visual_review if isinstance(visual_review, dict) else {}
    if not visual_review.get("ui_related"):
        return False
    if visual_review.get("status") != "captured":
        return True
    capture = visual_review.get("capture") if isinstance(visual_review.get("capture"), dict) else {}
    if capture.get("capture_source") != "local_preview":
        return True
    return not _visual_review_has_required_viewport_media(visual_review)


def _visual_review_block_reason(visual_review):
    visual_review = visual_review if isinstance(visual_review, dict) else {}
    summary = str(visual_review.get("summary") or "UI mission visual review media was not captured.").strip()
    capture = visual_review.get("capture") if isinstance(visual_review.get("capture"), dict) else {}
    local_preview = visual_review.get("local_preview") if isinstance(visual_review.get("local_preview"), dict) else {}
    failed = []
    for item in capture.get("captures") or []:
        if isinstance(item, dict) and not item.get("captured"):
            failed.append({
                "label": item.get("label"),
                "status": item.get("status"),
                "command": item.get("command"),
                "stderr_tail": item.get("stderr_tail"),
                "error_type": item.get("error_type"),
            })
    detail = {
        "preview_url": local_preview.get("url") or capture.get("url") or "",
        "capture_url": capture.get("capture_url") or "",
        "fallback_reason": capture.get("fallback_reason") or "",
        "capture_source": capture.get("capture_source") or "",
        "capture_url_recovery": capture.get("capture_url_recovery") or {},
        "failed_viewports": failed[:3],
    }
    return f"{summary} Visual capture diagnostics: {json.dumps(detail, ensure_ascii=False, default=str)[:1200]}"


def _visual_review_has_required_viewport_media(visual_review):
    media = visual_review.get("media") if isinstance(visual_review.get("media"), list) else []
    filenames = " ".join(
        str(item.get("filename") or item.get("label") or "").lower()
        for item in media
        if isinstance(item, dict)
    )
    has_desktop = "preview" in filenames or "desktop" in filenames or "laptop" in filenames
    has_mobile = "mobile" in filenames
    return has_desktop and has_mobile


def _write_normalized_vault_records(mission, execution_id, ledger, artifacts, brain_guard, database_url=None, connect_factory=None):
    mission = mission if isinstance(mission, dict) else {}
    ledger = ledger if isinstance(ledger, dict) else {}
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    mission_id = mission.get("mission_id", "")
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    project_truth = vault.get("project_truth") if isinstance(vault.get("project_truth"), dict) else {}
    writes = []
    vault_write_unavailable = False

    def record(label, write_call):
        nonlocal vault_write_unavailable
        if vault_write_unavailable:
            writes.append({
                "label": label,
                "status_code": 503,
                "success": False,
                "status": "skipped_after_vault_write_unavailable",
                "error_type": "",
            })
            return
        result_status = write_call() if callable(write_call) else write_call
        result, status_code = result_status
        writes.append({
            "label": label,
            "status_code": status_code,
            "success": bool(result.get("success")),
            "status": result.get("status", ""),
            "error_type": result.get("error_type", ""),
        })
        if status_code >= 500 and not result.get("success") and result.get("configured") is not False:
            vault_write_unavailable = True

    record("project", lambda: vault_store.write_project({
        "project_id": project_truth.get("project_key") or mission.get("mission_type") or "charlie_core",
        "project_key": project_truth.get("project_key") or "charlie_core",
        "name": project_truth.get("workflow_label") or mission.get("title") or "CHARLIE mission",
        "purpose": vault.get("desired_outcome") or vault.get("problem_statement") or mission.get("raw_text", ""),
        "workflow_template": project_truth.get("workflow_template") or mission.get("mission_type") or "software_build",
        "metadata": {"mission_id": mission_id, "project_truth": project_truth},
    }, database_url=database_url, connect_factory=connect_factory))

    for agent, artifact in artifacts.items():
        if not isinstance(artifact, dict):
            continue
        record(f"artifact:{agent}", lambda agent=agent, artifact=artifact: vault_store.write_artifact(
            mission_id,
            f"agent_artifact_{agent}",
            artifact,
            title=f"{agent} artifact",
            summary=artifact.get("summary", ""),
            project_id=project_truth.get("project_key") or "",
            agent=agent,
            database_url=database_url,
            connect_factory=connect_factory,
        ))
        record(f"agent_run:{agent}", lambda agent=agent, artifact=artifact: vault_store.write_agent_run(
            mission_id,
            agent,
            {
                "execution_id": execution_id,
                "attempt": artifact.get("attempt", 1),
                "status": "complete",
                "model_provider": (artifact.get("model_assignment") or {}).get("runtime_provider") if isinstance(artifact.get("model_assignment"), dict) else "",
                "model_name": (artifact.get("model_assignment") or {}).get("runtime_model") or (artifact.get("model_assignment") or {}).get("model") if isinstance(artifact.get("model_assignment"), dict) else "",
                "cost_estimate": (artifact.get("model_assignment") or {}).get("estimated_cost") if isinstance(artifact.get("model_assignment"), dict) else None,
                "started_at": ledger.get("started_at", ""),
                "completed_at": artifact.get("completed_at") or ledger.get("completed_at", ""),
                "tool_calls": [{"command": command} for command in artifact.get("commands_run", []) if command],
                "metadata": artifact,
            },
            stage=agent,
            database_url=database_url,
            connect_factory=connect_factory,
        ))
        handoff = artifact.get("handoff_report") if isinstance(artifact.get("handoff_report"), dict) else {}
        if handoff:
            record(f"handoff:{agent}", lambda handoff=handoff: vault_store.write_handoff_report(
                handoff,
                database_url=database_url,
                connect_factory=connect_factory,
            ))
        quality = artifact.get("quality_gate") if isinstance(artifact.get("quality_gate"), dict) else {}
        if quality:
            record(f"quality:{agent}", lambda agent=agent, quality=quality: vault_store.write_quality_gate(
                mission_id,
                f"{agent}_quality_gate",
                "pass" if quality.get("passed") else "fail",
                reason=quality.get("reason", ""),
                evidence=quality,
                stage=agent,
                database_url=database_url,
                connect_factory=connect_factory,
            ))

    record("brain_guard", lambda: vault_store.write_quality_gate(
        mission_id,
        "brain_guard_review_gate",
        "pass" if brain_guard.get("passed") else "fail",
        reason=brain_guard.get("reason", ""),
        evidence=brain_guard,
        stage="brain_guard",
        database_url=database_url,
        connect_factory=connect_factory,
    ))
    record("audit", lambda: vault_store.write_audit_event(
        "agent_runner_v2_completed_owner_review_packet",
        mission_id=mission_id,
        actor="charlie_core",
        target=execution_id,
        risk_level="medium",
        metadata={"brain_guard": brain_guard, "agent_count": len(artifacts)},
        database_url=database_url,
        connect_factory=connect_factory,
    ))
    return {
        "version": "charlie_normalized_vault_write_through_v1",
        "configured": any(item["status"] != "not_configured" for item in writes),
        "success_count": sum(1 for item in writes if item["success"]),
        "failed_count": sum(1 for item in writes if not item["success"]),
        "writes": writes,
    }


def _brain_guard_review_gate(mission, artifacts, changed_files, ledger=None):
    mission = mission if isinstance(mission, dict) else {}
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    ledger = ledger if isinstance(ledger, dict) else {}
    preserved = set(ledger.get("preserved_upstream_artifacts") if isinstance(ledger.get("preserved_upstream_artifacts"), list) else [])
    findings = []
    warnings = []
    context = build_vault_brain_context(mission)
    retrieval = context.get("retrieval") if isinstance(context.get("retrieval"), dict) else retrieve_vault_sources(mission)
    agent_sequence = _mission_agent_sequence(mission)
    missing_doctrine = _missing_agent_doctrine(agent_sequence)
    if missing_doctrine:
        findings.append(
            "Selected workflow has agents without loaded Vault doctrine files: "
            + ", ".join(f"{item['agent']} -> {item['path'] or 'no path'}" for item in missing_doctrine)
        )
    workflow_contract = _authoritative_workflow_contract(mission, agent_sequence)
    from modules.charlie.agentic_architecture import evaluate_agentic_architecture
    agentic_gate = evaluate_agentic_architecture(mission, artifacts)
    findings.extend(agentic_gate.get("findings") or [])
    if workflow_contract["ui_related"]:
        for required_agent in ["product_architect", "product_reviewer", "evidence_reviewer"]:
            if required_agent in workflow_contract["required_agents"] and required_agent not in agent_sequence:
                findings.append(f"UI/product mission workflow is missing required agent: {required_agent}.")
        if "builder" in agent_sequence and "product_architect" in agent_sequence:
            if agent_sequence.index("product_architect") > agent_sequence.index("builder"):
                findings.append("UI/product mission has Product Architect after Builder; product brief must happen before build.")
    active_artifacts = {
        agent: artifact
        for agent, artifact in artifacts.items()
        if agent not in preserved
    }
    source_coverage = evaluate_vault_source_coverage(active_artifacts, retrieval)
    if context.get("missing_docs"):
        findings.append(f"Vault Brain context has missing docs: {', '.join(context['missing_docs'])}.")
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    if not vault:
        findings.append("Mission Vault payload is missing from the mission.")
    if not source_coverage.get("passed"):
        findings.append(f"Vault source coverage score is {source_coverage.get('score', 0)}; required coverage not met.")
    for agent, artifact in artifacts.items():
        if not isinstance(artifact, dict):
            continue
        if not _artifact_has_vault_brain_source(artifact):
            if agent in preserved:
                warnings.append(f"{agent} is preserved legacy evidence and did not cite any docs/09-vault-brain source.")
            else:
                findings.append(f"{agent} did not cite any docs/09-vault-brain source.")
    sensitive_changes = _vault_sensitive_changed_files(changed_files)
    if sensitive_changes:
        records_update = False
        for artifact in artifacts.values():
            if isinstance(artifact, dict) and _artifact_records_vault_update_decision(artifact):
                records_update = True
                break
        if not records_update:
            findings.append(
                "Vault-sensitive files changed without any artifact recording vault_updates or no_vault_update_required: "
                + ", ".join(sensitive_changes)
            )
    passed = not findings
    return {
        "version": "charlie_brain_guard_gate_v1",
        "agent": "brain_guard",
        "passed": passed,
        "reason": "Brain Guard passed. Vault Brain was cited and update discipline was recorded." if passed else "Brain Guard blocked owner review because Vault Brain discipline is incomplete.",
        "findings": findings,
        "warnings": warnings,
        "preserved_legacy_artifacts": sorted(preserved),
        "source_coverage": source_coverage,
        "agent_sequence": agent_sequence,
        "workflow_contract": workflow_contract,
        "agentic_architecture": agentic_gate,
        "missing_doctrine": missing_doctrine,
        "retrieval": retrieval,
        "owner_preferences": context.get("owner_preferences", {}),
        "vault_context_docs": [entry.get("path", "") for entry in context.get("docs", []) if isinstance(entry, dict)],
        "sensitive_changed_files": sensitive_changes,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _authoritative_workflow_contract(mission, agent_sequence=None):
    """Return the persisted planning contract; final gates must not reclassify it."""
    mission = mission if isinstance(mission, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    core = metadata.get("charlie_core") if isinstance(metadata.get("charlie_core"), dict) else {}
    project_truth = core.get("project_truth") if isinstance(core.get("project_truth"), dict) else {}
    template = core.get("workflow_template") if isinstance(core.get("workflow_template"), dict) else {}
    template_id = str(
        project_truth.get("workflow_template")
        or template.get("template_id")
        or metadata.get("workflow_template")
        or ""
    ).strip()
    sequence = [str(item or "").strip() for item in (agent_sequence or _mission_agent_sequence(mission)) if str(item or "").strip()]
    required_agents = [str(item or "").strip() for item in (template.get("agent_order") or sequence) if str(item or "").strip()]
    required_evidence = [str(item or "").strip() for item in (template.get("required_artifacts") or project_truth.get("required_artifacts") or []) if str(item or "").strip()]
    ui_related = template_id == "ui_product_build"
    if not template_id:
        ui_related = all(agent in sequence for agent in ("product_architect", "product_reviewer"))
    risk_level = str(project_truth.get("risk_level") or metadata.get("risk_level") or mission.get("approval_level") or "standard").strip()
    return {
        "version": "charlie_workflow_contract_v1",
        "template_id": template_id or "persisted_sequence",
        "required_agents": required_agents,
        "optional_agents": [agent for agent in sequence if agent not in required_agents],
        "required_evidence": required_evidence,
        "ui_related": ui_related,
        "risk_level": risk_level,
        "authoritative": True,
    }


def _missing_agent_doctrine(agent_sequence):
    missing = []
    for agent in agent_sequence if isinstance(agent_sequence, list) else []:
        clean_agent = str(agent or "").strip().lower()
        path_text = AGENT_DOCTRINE_PATHS.get(clean_agent, "")
        if not path_text:
            missing.append({"agent": clean_agent, "path": ""})
            continue
        path = (REPO_ROOT / path_text).resolve()
        try:
            path.relative_to(REPO_ROOT)
        except ValueError:
            missing.append({"agent": clean_agent, "path": path_text})
            continue
        if not path.exists() or not path.is_file():
            missing.append({"agent": clean_agent, "path": path_text})
    return missing


def _block_completed_agent_review(
    mission,
    execution_id,
    ledger,
    agent,
    artifact,
    artifacts,
    ledger_path,
    output_dir,
    blocked_reason,
    database_url=None,
    connect_factory=None,
):
    disposition = classify_block(agent, blocked_reason, artifact)
    disposition, recovery_repeat = _bounded_internal_recovery(
        mission.get("mission_id"), agent, blocked_reason, artifact, disposition,
        mission=mission, database_url=database_url, connect_factory=connect_factory,
    )
    ledger["status"] = "blocked"
    ledger["blocked_agent"] = agent
    ledger["blocked_reason"] = blocked_reason
    ledger["completed_at"] = datetime.now(timezone.utc).isoformat()
    unresolved = _artifact_issue_items(agent, artifact)
    if unresolved:
        ledger["unresolved_blockers"] = unresolved
    ledger_path = _write_agent_ledger(output_dir, execution_id, ledger)
    recovery_packet = build_recovery_packet(
        agent=agent,
        blocked_reason=blocked_reason,
        artifact=artifact,
        ledger=ledger,
        changed_files=artifact.get("changed_files") or _changed_files(),
    )
    recovery_packet["disposition"] = disposition
    _record_mission_memory_event(
        mission,
        build_memory_event(
            agent,
            "agent_blocked",
            summary=f"{agent} blocked: {blocked_reason}",
            artifact=artifact,
            quality_gate=artifact.get("quality_gate", {}),
            recovery=recovery_packet,
            metadata={"execution_id": execution_id, "backflow_fingerprint": recovery_repeat["fingerprint"], "recovery_occurrence": recovery_repeat["occurrence"]},
        ),
        database_url=database_url,
        connect_factory=connect_factory,
    )
    mission_quality = score_mission_quality(
        mission,
        {
            "review_status": "agent_blocked",
            "blocked_agent": agent,
            "blocked_reason": blocked_reason,
            "unresolved_blockers": unresolved,
            "changed_files": artifact.get("changed_files") or _changed_files(),
            "test_evidence": artifact.get("test_evidence", []),
            "quality_gates": ledger.get("quality_gates", []),
            "backflow_events": ledger.get("backflow_events", []),
            "recovery_packet": recovery_packet,
        },
        ledger,
    )
    review_packet = {
        "summary": f"CHARLIE Agent Runner v2 blocked at {agent}: {blocked_reason}",
        "blocked_summary": _blocked_review_summary(agent, blocked_reason, ledger, artifact),
        "findings": [
            f"{agent} blocked the mission: {blocked_reason}",
            *_issue_lines(unresolved),
        ],
        "errors": [blocked_reason],
        "bugs": artifact.get("bugs", []),
        "changed_files": artifact.get("changed_files") or _changed_files() or ["No changed files detected by git diff."],
        "test_evidence": artifact.get("test_evidence", []),
        "qa_evidence": _collect_artifact_list(artifacts, "qa_findings"),
        "local_preview": artifact.get("visual_review", {}).get("local_preview", {}),
        "visual_review": artifact.get("visual_review", {}),
        "links": artifact.get("links", {}) if isinstance(artifact.get("links"), dict) else {},
        "execution_artifacts": {
            "execution_id": execution_id,
            "agent_ledger_path": str(ledger_path),
            "blocked_agent": agent,
        },
        "agent_execution": _agent_execution_summary(ledger),
        "agent_artifacts": _compact_agent_artifacts_for_review(artifacts),
        "unresolved_blockers": unresolved,
        "normalized_findings": normalize_findings(unresolved, agent=agent, artifact=artifact),
        "handoff_reports": {
            stage_agent: stage_artifact.get("handoff_report", {})
            for stage_agent, stage_artifact in artifacts.items()
            if isinstance(stage_artifact, dict)
        },
        "quality_gates": ledger.get("quality_gates", []),
        "backflow_events": ledger.get("backflow_events", []),
        "recovery_packet": recovery_packet,
        "mission_quality": mission_quality,
        "blocked_agent": agent,
        "blocked_reason": blocked_reason,
        "block_disposition": disposition,
        "recovery_repeat": recovery_repeat,
        "recommended_next_action": artifact.get("next_action") or (
            f"CORE will recover from {disposition['responsible_stage']}."
            if disposition["recoverable"]
            else "Owner decision is required."
        ),
        "review_status": "internal_recovery_queued" if disposition["recoverable"] else "agent_blocked",
    }
    update_mission_vault(
        mission["mission_id"],
        {"agent_execution": ledger, "review_packet": review_packet},
        notes="CHARLIE Agent Runner v2 blocked owner review because visual evidence was missing.",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    _record_execution_stage(mission["mission_id"], agent, "blocked", blocked_reason, database_url=database_url, connect_factory=connect_factory)
    next_status = "approved" if disposition["recoverable"] else "blocked"
    blocked, blocked_status = update_mission_status(
        mission["mission_id"],
        next_status,
        owner_decision="" if disposition["recoverable"] else f"CHARLIE Agent Runner v2 blocked at {agent}.",
        event_type="status_changed",
        notes=blocked_reason,
        metadata={
            "agent_runner_version": AGENT_RUNNER_VERSION,
            "execution_id": execution_id,
            "blocked_agent": agent,
            "block_class": disposition["block_class"],
            "recovery_stage": disposition["responsible_stage"],
            "recovery_fingerprint": recovery_repeat["fingerprint"],
            "recovery_occurrence": recovery_repeat["occurrence"],
        },
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if blocked_status >= 400:
        return blocked, blocked_status
    return {
        "success": disposition["recoverable"],
        "status": "agent_stage_recovery_queued" if disposition["recoverable"] else "agent_stage_blocked",
        "mission_id": mission["mission_id"],
        "mission_status": next_status,
        "agent": agent,
        "blocked_reason": blocked_reason,
        "block_disposition": disposition,
        "agent_ledger_path": str(ledger_path),
    }, 202 if disposition["recoverable"] else 504


def _collect_artifact_list(artifacts, key):
    collected = []
    for artifact in artifacts.values():
        value = artifact.get(key)
        if isinstance(value, list):
            collected.extend(item for item in value if item)
        elif value:
            collected.append(value)
    return collected


def _compact_agent_artifacts_for_review(artifacts):
    compact = {}
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    keep_keys = [
        "agent",
        "summary",
        "status",
        "confidence",
        "confidence_reason",
        "changed_files",
        "files_inspected",
        "commands_run",
        "tests_run",
        "test_evidence",
        "test_status",
        "qa_findings",
        "red_team_status",
        "risk_rating",
        "risk_notes",
        "errors",
        "bugs",
        "next_action",
        "recommended_owner_decision",
        "release_notes",
        "quality_gate",
        "model_assignment",
        "artifact_path",
        "stdout_path",
        "stderr_path",
        "attempt",
        "completed_at",
        "pr_url",
        "pr_number",
        "links",
        "local_preview",
        "visual_review",
        "brain_guard",
        "contract_parse_fallback",
        "contract_retry_exhausted",
        "first_attempt_artifact_path",
        "expected_revision",
        "tested_revision",
        "artifact_id",
        "source_commit",
        "candidate_fingerprint",
        "scope_hash",
        "evidence_lineage",
        "structured_findings",
        "acceptance_results",
        "protected_operations",
    ]
    for agent, artifact in artifacts.items():
        if not isinstance(artifact, dict):
            continue
        item = {}
        for key in keep_keys:
            if key not in artifact:
                continue
            value = artifact.get(key)
            if key in {"summary", "confidence_reason", "next_action"}:
                value = _truncate(value, 1200)
            elif key in {"errors", "bugs", "qa_findings", "risk_notes", "tests_run", "test_evidence", "commands_run", "files_inspected", "changed_files", "release_notes"}:
                value = [_truncate(entry, 500) for entry in _artifact_value_list(value)[:30]]
            item[key] = value
        stdout_tail = _truncate(artifact.get("stdout_tail", ""), 500)
        stderr_tail = _truncate(artifact.get("stderr_tail", ""), 500)
        if stdout_tail:
            item["stdout_tail_excerpt"] = stdout_tail
        if stderr_tail:
            item["stderr_tail_excerpt"] = stderr_tail
        compact[agent] = item
    return compact


def _agent_artifacts_for_prompt(artifacts, current_agent="", agent_sequence=None):
    compact = _compact_agent_artifacts_for_review(artifacts)
    agent_sequence = agent_sequence or list(AGENT_SEQUENCE)
    current_agent = str(current_agent or "").strip().lower()
    if current_agent in agent_sequence:
        current_index = agent_sequence.index(current_agent)
        ordered_agents = list(reversed(agent_sequence[:current_index]))
    else:
        ordered_agents = list(reversed(agent_sequence))
    ordered_agents.extend(agent for agent in compact if agent not in ordered_agents)
    prompt_artifacts = {}
    for agent in ordered_agents:
        artifact = compact.get(agent)
        if not isinstance(artifact, dict):
            continue
        item = {}
        for key, value in artifact.items():
            if isinstance(value, list):
                item[key] = value[:12]
                if len(value) > 12:
                    item[f"{key}_truncated_count"] = len(value) - 12
            else:
                item[key] = value
        prompt_artifacts[agent] = item
    return prompt_artifacts


def _artifact_value_list(value):
    return value if isinstance(value, list) else ([] if value in (None, "") else [value])


def _artifact_stage_summaries(artifacts, agent_sequence):
    summaries = []
    for agent in agent_sequence:
        artifact = artifacts.get(agent) if isinstance(artifacts.get(agent), dict) else {}
        summary = artifact.get("summary")
        if summary:
            summaries.append(f"{agent}: {summary}")
    return summaries or ["CHARLIE Agent Runner v2 completed all configured stages."]


def _artifact_issue_items(agent, artifact, quality=None):
    artifact = artifact if isinstance(artifact, dict) else {}
    quality = quality if isinstance(quality, dict) else artifact.get("quality_gate") if isinstance(artifact.get("quality_gate"), dict) else {}
    issues = []

    def add_issue(value, default_severity="medium", source="artifact"):
        if isinstance(value, dict):
            text = str(value.get("finding") or value.get("bug") or value.get("error") or value.get("summary") or value.get("message") or "").strip()
            if not text:
                return
            issues.append({
                "agent": agent,
                "severity": str(value.get("severity") or default_severity).strip() or default_severity,
                "file": str(value.get("file") or "").strip(),
                "line": value.get("line", ""),
                "finding": text,
                "source": source,
            })
            return
        text = str(value or "").strip()
        if text:
            issues.append({
                "agent": agent,
                "severity": default_severity,
                "file": "",
                "line": "",
                "finding": text,
                "source": source,
            })

    for key, severity, source in (
        ("bugs", "high", "bugs"),
        ("errors", "high", "errors"),
        ("qa_findings", str(artifact.get("risk_rating") or "medium").lower(), "qa_findings"),
    ):
        value = artifact.get(key)
        if isinstance(value, list):
            for item in _blocking_artifact_items(agent, artifact, value):
                add_issue(item, severity, source)
        elif _blocking_artifact_items(agent, artifact, [value]):
            add_issue(value, severity, source)

    reason = str(quality.get("reason") or "").strip()
    if reason and quality.get("passed") is False and not any(item["finding"] == reason for item in issues):
        add_issue(reason, "medium", "quality_gate")
    return issues[:12]


def _issue_lines(issues):
    lines = []
    for item in issues if isinstance(issues, list) else []:
        if isinstance(item, dict):
            where = str(item.get("file") or "").strip()
            if item.get("line"):
                where = f"{where}:{item.get('line')}" if where else str(item.get("line"))
            prefix = f"{where} - " if where else ""
            text = str(item.get("finding") or "").strip()
            if text:
                lines.append(f"{str(item.get('severity') or 'medium').upper()}: {prefix}{text}")
        elif item:
            lines.append(str(item))
    return lines


def _agent_unresolved_issue_context(artifacts=None, ledger=None):
    ledger = ledger if isinstance(ledger, dict) else {}
    issues = ledger.get("unresolved_blockers") if isinstance(ledger.get("unresolved_blockers"), list) else []
    if issues:
        return {
            "status": "unresolved",
            "issues": issues[-12:],
            "backflow_events": ledger.get("backflow_events", [])[-5:] if isinstance(ledger.get("backflow_events"), list) else [],
        }
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    qa = artifacts.get("qa_red_team") if isinstance(artifacts.get("qa_red_team"), dict) else {}
    qa_issues = _artifact_issue_items("qa_red_team", qa)
    return {
        "status": "unresolved" if qa_issues else "none_recorded",
        "issues": qa_issues,
        "backflow_events": ledger.get("backflow_events", [])[-5:] if isinstance(ledger.get("backflow_events"), list) else [],
    }


def _build_handoff_report(mission, agent, artifact, ledger):
    artifact = artifact if isinstance(artifact, dict) else {}
    unresolved = _agent_unresolved_issue_context({agent: artifact}, ledger)
    legacy = {
        "contract": "charlie_handoff_report_v1",
        "mission_id": mission.get("mission_id", "") if isinstance(mission, dict) else "",
        "agent": agent,
        "status": "complete",
        "summary": artifact.get("summary", ""),
        "files_inspected": artifact.get("files_inspected", []),
        "commands_run": artifact.get("commands_run", []),
        "stdout_tail": _truncate(artifact.get("stdout_tail", ""), 800),
        "stderr_tail": _truncate(artifact.get("stderr_tail", ""), 800),
        "changed_files": artifact.get("changed_files", []),
        "tests": artifact.get("tests_run") or artifact.get("test_evidence") or [],
        "risks": artifact.get("risk_notes") or artifact.get("qa_findings") or [],
        "quality_gate": artifact.get("quality_gate", {}),
        "unresolved_blockers": unresolved.get("issues", []),
        "next_action": artifact.get("next_action", ""),
        "completed_at": artifact.get("completed_at", datetime.now(timezone.utc).isoformat()),
        "ledger_execution_id": ledger.get("execution_id", "") if isinstance(ledger, dict) else "",
    }
    canonical = build_core_handoff_report(mission, agent, {
        **artifact,
        "inputs_used": artifact.get("files_inspected", []),
        "actions_taken": artifact.get("commands_run", []),
        "vault_sources_used": ["mission_vault", "mission_context_pack"],
        "artifacts_created": artifact.get("changed_files", []),
        "files_changed": artifact.get("changed_files", []),
        "risks_found": artifact.get("risk_notes") or artifact.get("qa_findings") or unresolved.get("issues", []),
        "tests_run": artifact.get("tests_run") or artifact.get("test_evidence") or [],
        "pass_fail_status": "pass",
        "recommended_next_agent": artifact.get("handoff_to", ""),
    })
    return {
        **legacy,
        "canonical": canonical,
        "validation": canonical.get("validation", {}),
    }


def _display_command(command):
    if not isinstance(command, list):
        return str(command or "")
    return " ".join(str(part) for part in command)


def _tail_text(value, max_len=1200):
    text = str(value or "")
    if len(text) <= max_len:
        return text
    return text[-max_len:]


def _read_tail(path, max_len=1200):
    try:
        return _tail_text(Path(path).read_text(encoding="utf-8", errors="replace"), max_len)
    except OSError:
        return ""


def _stage_attempt_from_path(path):
    match = re.search(r"\.attempt(\d+)\.", str(path or ""))
    return int(match.group(1)) if match else 1


def _agent_execution_summary(ledger):
    stages = []
    for stage in ledger.get("stages", []) if isinstance(ledger, dict) else []:
        stages.append({
            "agent": stage.get("agent", ""),
            "status": stage.get("status", ""),
            "attempt": stage.get("attempt", 1),
            "current_action": stage.get("current_action", ""),
            "commands_run": stage.get("commands_run", []),
            "files_inspected": stage.get("files_inspected", []),
            "changed_files": stage.get("changed_files", []),
            "stdout_tail": _truncate(stage.get("stdout_tail", ""), 800),
            "stderr_tail": _truncate(stage.get("stderr_tail", ""), 800),
            "quality_gate": stage.get("quality_gate", {}),
        })
    summary = {
        "version": ledger.get("version", ""),
        "execution_id": ledger.get("execution_id", ""),
        "status": ledger.get("status", ""),
        "last_progress_at": ledger.get("last_progress_at", ""),
        "blocked_agent": ledger.get("blocked_agent", ""),
        "blocked_reason": ledger.get("blocked_reason", ""),
        "unresolved_blockers": ledger.get("unresolved_blockers", []),
        "last_backflow": ledger.get("last_backflow", {}),
        "backflow_events": ledger.get("backflow_events", []),
        "stages": stages,
    }
    for key in ("parallel_planning_execution", "rerun_from_stage", "preserved_upstream_artifacts"):
        if key in ledger:
            summary[key] = ledger[key]
    return summary


def _load_execution_mission(mission_id="", status="in_progress", database_url=None, connect_factory=None):
    mission_id = str(mission_id or "").strip()
    if mission_id:
        loaded, status_code = get_mission(mission_id, database_url=database_url, connect_factory=connect_factory)
        if status_code >= 400:
            return None, status_code, loaded
        mission = loaded.get("mission") or {}
        if mission.get("status") != "in_progress":
            return None, 409, {
                "success": False,
                "status": "mission_not_ready_for_codex_execution",
                "mission_id": mission_id,
                "mission_status": mission.get("status", ""),
                "required_status": "in_progress",
            }
        return mission, 200, {}
    loaded, status_code = list_missions(status=status, limit=1, database_url=database_url, connect_factory=connect_factory)
    if status_code >= 400:
        return None, status_code, loaded
    missions = loaded.get("missions") or []
    if not missions:
        return None, 404, {"success": False, "status": "no_execution_mission_available", "missions": []}
    return missions[0], 200, {}


def _load_release_mission(mission_id="", database_url=None, connect_factory=None):
    mission_id = str(mission_id or "").strip()
    if mission_id:
        loaded, status_code = get_mission(mission_id, database_url=database_url, connect_factory=connect_factory)
        if status_code >= 400:
            return None, status_code, loaded
        mission = loaded.get("mission") or {}
        if mission.get("status") != "release_approved":
            return None, 409, {
                "success": False,
                "status": "mission_not_ready_for_release_execution",
                "mission_id": mission_id,
                "mission_status": mission.get("status", ""),
                "required_status": "release_approved",
            }
        return mission, 200, {}
    loaded, status_code = list_missions(status="release_approved", limit=1, database_url=database_url, connect_factory=connect_factory)
    if status_code >= 400:
        return None, status_code, loaded
    missions = loaded.get("missions") or []
    if not missions:
        return None, 404, {"success": False, "status": "no_release_approved_mission_available", "missions": []}
    return missions[0], 200, {}


def _record_execution_stage(mission_id, agent, step_status, findings, database_url=None, connect_factory=None):
    return update_mission_workflow_step(
        mission_id,
        agent,
        step_status=step_status,
        findings=findings,
        database_url=database_url,
        connect_factory=connect_factory,
    )


def _record_mission_memory_event(mission, event, database_url=None, connect_factory=None):
    mission = mission if isinstance(mission, dict) else {}
    mission_id = mission.get("mission_id", "")
    if not mission_id:
        return {"success": False, "status": "mission_id_required"}, 400
    if not isinstance(mission.get("metadata"), dict):
        loaded, status_code = get_mission(mission_id, database_url=database_url, connect_factory=connect_factory)
        if status_code < 400:
            mission = loaded.get("mission") or mission
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    patch = memory_patch_from_event(metadata, event)
    if "mission_memory" in patch:
        mission.setdefault("metadata", {})["mission_memory"] = patch["mission_memory"]
    return update_mission_vault(
        mission_id,
        patch,
        notes="CHARLIE Agent Runner v2 recorded mission memory.",
        database_url=database_url,
        connect_factory=connect_factory,
    )


def _builder_revision_sha(mission, artifacts=None):
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    builder = artifacts.get("builder") if isinstance(artifacts.get("builder"), dict) else {}
    lineage = builder.get("evidence_lineage") if isinstance(builder.get("evidence_lineage"), dict) else {}
    packaging = builder.get("git_packaging") if isinstance(builder.get("git_packaging"), dict) else {}
    revision = str(
        lineage.get("source_commit")
        or builder.get("source_commit")
        or builder.get("tested_revision")
        or builder.get("expected_revision")
        or builder.get("commit_sha")
        or packaging.get("commit_sha")
        or ""
    ).strip()
    if revision:
        return revision
    metadata = mission.get("metadata") if isinstance(mission, dict) and isinstance(mission.get("metadata"), dict) else {}
    memory = metadata.get("mission_memory") if isinstance(metadata.get("mission_memory"), dict) else {}
    latest = memory.get("latest_by_agent") if isinstance(memory.get("latest_by_agent"), dict) else {}
    builder_event = latest.get("builder") if isinstance(latest.get("builder"), dict) else {}
    event_lineage = builder_event.get("evidence_lineage") if isinstance(builder_event.get("evidence_lineage"), dict) else {}
    return str(
        event_lineage.get("source_commit")
        or builder_event.get("source_commit")
        or builder_event.get("tested_revision")
        or builder_event.get("expected_revision")
        or builder_event.get("commit_sha")
        or ""
    ).strip()


def _release_candidate_revision_sha(mission, artifacts=None):
    """Prefer the newest exact revision verified by a release-stage agent.

    A publisher may rebase or repair the packaged PR after Builder. In that
    case Builder's original commit remains useful historical evidence, but it
    is no longer the release candidate. Selecting a later agent is safe only
    when it explicitly records the revision it inspected (and, when present,
    its expected revision agrees). Older evidence will then be targeted for a
    recheck against that authoritative candidate instead of defining it.
    """
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    for agent in (
        "publisher", "reviewer", "evidence_reviewer", "security_reviewer",
        "product_reviewer", "visual_qa_reviewer", "qa_red_team", "tester",
    ):
        artifact = artifacts.get(agent) if isinstance(artifacts.get(agent), dict) else {}
        tested = str(artifact.get("tested_revision") or artifact.get("current_revision") or "").strip()
        expected = str(artifact.get("expected_revision") or "").strip()
        if tested and (not expected or tested == expected):
            return tested
    return _builder_revision_sha(mission, artifacts)


def _bind_publisher_revision(artifact, revision=""):
    artifact = dict(artifact) if isinstance(artifact, dict) else {}
    published_revision = str(revision or _git_head_revision()).strip()
    if published_revision:
        artifact["expected_revision"] = published_revision
        artifact["tested_revision"] = published_revision
        artifact["commit_sha"] = published_revision
    return artifact


def _owner_review_gate_failure(mission, blocked_agent, blocked_reason, workflow_status):
    mission = mission if isinstance(mission, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    previous = packet.get("owner_review_gate_failure") if isinstance(packet.get("owner_review_gate_failure"), dict) else {}
    reconciliation = workflow_status.get("evidence_reconciliation") if isinstance(workflow_status.get("evidence_reconciliation"), dict) else {}
    manifest = reconciliation.get("candidate_manifest") if isinstance(reconciliation.get("candidate_manifest"), dict) else {}
    refresh = reconciliation.get("requires_revalidation") if isinstance(reconciliation.get("requires_revalidation"), list) else []
    blockers = reconciliation.get("active_blockers") if isinstance(reconciliation.get("active_blockers"), list) else []
    failure_class = (
        "candidate_evidence_revalidation"
        if refresh
        else "candidate_active_blocker"
        if blockers
        else "owner_review_readiness"
    )
    fingerprint = hashlib.sha256(json.dumps({
        "mission_id": str(mission.get("mission_id") or "").strip(),
        "failure_class": failure_class,
        "candidate_revision": str(manifest.get("source_commit") or "").strip(),
    }, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    prior = int(previous.get("occurrence") or 0) if previous.get("fingerprint") == fingerprint else 0
    return {
        "version": "charlie_owner_review_gate_failure_v1",
        "fingerprint": fingerprint,
        "occurrence": prior + 1,
        "blocked_agent": blocked_agent,
        "failure_class": failure_class,
        "candidate_revision": str(manifest.get("source_commit") or "").strip(),
    }


def _agent_completion_note(agent, final_message):
    if agent == "planner":
        return "Codex execution bridge scoped the mission and followed the mission protocol."
    if agent == "architect":
        return "Codex execution bridge inspected implementation boundaries and source-of-truth rules."
    if agent == "builder":
        return "Codex execution bridge completed the approved build work or confirmed no code change was required."
    if agent == "tester":
        return "Codex execution bridge ran or reported focused verification."
    return _truncate(final_message or "Codex execution bridge prepared the owner review packet.", 1000)


def _changed_files():
    try:
        completed = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True,
            check=False,
            text=True,
            cwd=str(REPO_ROOT),
            timeout=10,
            **background_run_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _local_preview_from_reviewer(reviewer):
    reviewer = reviewer if isinstance(reviewer, dict) else {}
    links = reviewer.get("links") if isinstance(reviewer.get("links"), dict) else {}
    url = str(links.get("local_preview") or "").strip()
    local_preview = _extract_local_preview(" ".join([
        str(reviewer.get("summary") or ""),
        str(reviewer.get("stdout_tail") or ""),
        str(reviewer.get("next_action") or ""),
        url,
    ]))
    if url and not local_preview.get("url"):
        local_preview["url"] = url
        local_preview["status"] = "captured"
        local_preview["message"] = ""
    if not local_preview.get("url"):
        inferred = _infer_local_preview_url(local_preview.get("command", ""))
        if inferred.get("url"):
            local_preview.update(inferred)
    return local_preview


def _infer_local_preview_url(command_text=""):
    candidates = []
    text = str(command_text or "")
    port_matches = re.findall(r"--port\s+(\d+)|:(\d+)", text)
    for explicit, colon in port_matches:
        port = explicit or colon
        if port:
            candidates.append(f"http://127.0.0.1:{port}/charlie")
    candidates.extend([
        str(env_value("CORE_LOCAL_PREVIEW_URL", "") or "").strip(),
        "http://127.0.0.1:5002/charlie",
        "http://127.0.0.1:5000/charlie",
    ])
    seen = set()
    for url in candidates:
        url = str(url or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        probe = _probe_local_preview_url(url)
        if probe.get("ok"):
            return {
                "url": url,
                "status": "captured",
                "message": f"Inferred reachable local preview URL from runner probe ({probe.get('http_status')}).",
                "source": "local_runner_probe",
            }
    return {"url": "", "status": "not_captured", "message": "No reachable local CHARLIE preview URL was detected by the runner."}


def _probe_local_preview_url(url):
    parsed = urlparse(str(url or ""))
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost"}:
        return {"ok": False, "status": "not_local"}
    try:
        opener = url_request.build_opener(url_request.HTTPRedirectHandler)
        req = url_request.Request(url, headers={"User-Agent": "CHARLIE-local-preview-probe"})
        with opener.open(req, timeout=5) as response:
            status = int(response.status)
            final_url = response.geturl()
            body = response.read(4096).decode("utf-8", errors="replace")
    except (OSError, URLError, ValueError) as exc:
        return {"ok": False, "status": "probe_failed", "error_type": exc.__class__.__name__}
    if status != 200:
        return {"ok": False, "status": "bad_status", "http_status": status, "final_url": final_url}
    if "/owner/login" in str(final_url):
        return {"ok": False, "status": "login_redirect", "http_status": status, "final_url": final_url}
    if "CHARLIE Mission Control" not in body:
        return {"ok": False, "status": "unexpected_body", "http_status": status, "final_url": final_url}
    return {"ok": True, "status": "ok", "http_status": status, "final_url": final_url}


def _build_visual_review_packet(
    mission_id="",
    mission_type="",
    changed_files=None,
    local_preview=None,
    artifacts=None,
    final_message="",
    mission=None,
):
    mission_id = str(mission_id or "").strip()
    changed_files = [str(path or "").strip() for path in (changed_files or []) if str(path or "").strip()]
    local_preview = local_preview if isinstance(local_preview, dict) else {}
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    ui_contract = _ui_quality_contract_for_mission(mission or {"mission_type": mission_type, "raw_text": final_message})
    ui_related = bool(ui_contract.get("ui_related")) or _is_ui_related_mission(mission_type, changed_files, final_message)
    local_media_path = str(_review_media_path(mission_id)) if mission_id else ""
    if ui_related and mission_id:
        _review_media_path(mission_id).mkdir(parents=True, exist_ok=True)
    capture = _capture_visual_review_media(
        mission_id,
        local_preview,
        changed_files=changed_files,
        artifacts=artifacts,
        final_message=final_message,
    ) if ui_related else {
        "status": "not_required",
        "captured": False,
        "reason": "mission_not_ui_related",
    }
    media = _review_media_items(mission_id) if ui_related else []
    status = "not_applicable"
    if ui_related:
        status = "captured" if media else "not_captured_blocked"
    preview_url = str(local_preview.get("url") or "").strip()
    return {
        "contract": "charlie_visual_review_v1",
        "ui_related": ui_related,
        "status": status,
        "summary": _visual_review_summary(ui_related, media, preview_url),
        "required_media": ["desktop/laptop screenshot", "mobile screenshot"] if ui_related else [],
        "ui_quality_contract": ui_contract if ui_related else {},
        "local_preview": local_preview,
        "media": media,
        "capture": capture,
        "stage_evidence": _visual_stage_evidence(artifacts),
        "local_media_path": local_media_path,
        "cleanup": {
            "required": ui_related,
            "status": "pending_owner_decision" if ui_related else "not_required",
            "local_path": local_media_path if ui_related else "",
            "trigger": "owner_final_approval_or_mark_done",
        },
    }


def _capture_visual_review_media(
    mission_id,
    local_preview,
    run_subprocess=None,
    changed_files=None,
    artifacts=None,
    final_message="",
):
    mission_id = str(mission_id or "").strip()
    preview_url = str((local_preview or {}).get("url") or "").strip()
    if not mission_id:
        return {"captured": False, "status": "mission_id_missing"}
    media_dir = _review_media_path(mission_id)
    media_dir.mkdir(parents=True, exist_ok=True)

    fallback_reason = ""
    capture_url = preview_url
    recovery = {}
    if not preview_url:
        fallback_reason = "preview_url_not_captured"
    else:
        recovery = _recover_local_preview_capture_url(preview_url, local_preview)
        if recovery.get("url"):
            capture_url = recovery["url"]
        parsed = urlparse(preview_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost"}:
            fallback_reason = "preview_url_not_local"
        elif _is_control_dashboard_preview_url(preview_url) and not _preview_url_matches_changed_ui(preview_url, changed_files, final_message):
            inferred = _infer_changed_ui_preview_url(preview_url, changed_files, final_message)
            if inferred.get("url"):
                capture_url = inferred["url"]
                recovery = {
                    **recovery,
                    "changed_ui_preview_inference": inferred,
                }
            else:
                fallback_reason = "control_dashboard_preview_not_mission_visual"

    if fallback_reason:
        html_path = _write_visual_review_preview_html(
            mission_id=mission_id,
            media_dir=media_dir,
            local_preview=local_preview,
            changed_files=changed_files,
            artifacts=artifacts,
            final_message=final_message,
            fallback_reason=fallback_reason,
        )
        capture_url = html_path.resolve().as_uri()

    runner = run_subprocess or subprocess.run
    targets = [("owner_review_preview.png", "1440,900", "desktop/laptop")]
    if not fallback_reason:
        targets.append(("owner_review_mobile.png", "390,844", "mobile"))
    captures = []
    for filename, viewport, label in targets:
        output_path = media_dir / filename
        command = [
            _npx_executable(),
            "playwright",
            "screenshot",
            f"--viewport-size={viewport}",
            "--wait-for-timeout=1000",
            capture_url,
            str(output_path),
        ]
        try:
            completed = runner(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(REPO_ROOT),
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            captures.append({
                "label": label,
                "captured": False,
                "status": "capture_command_failed",
                "command": " ".join(command),
                "error_type": exc.__class__.__name__,
            })
            continue
        captured_item = completed.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0
        captures.append({
            "label": label,
            "captured": captured_item,
            "status": "captured" if captured_item else "capture_command_failed",
            "command": " ".join(command),
            "path": str(output_path) if captured_item else "",
            "returncode": completed.returncode,
            "stdout_tail": _truncate(completed.stdout or "", 1200),
            "stderr_tail": _truncate(completed.stderr or "", 1200),
        })
    captured = bool(captures) and all(item.get("captured") for item in captures)
    durable_reuse = {}
    if not captured and not fallback_reason:
        durable_reuse = _promote_durable_visual_review_media(mission_id, artifacts)
        captured = bool(durable_reuse.get("captured"))
        if captured:
            captures.append(durable_reuse)
    return {
        "captured": captured,
        "status": "captured" if captured else "capture_command_failed",
        "url": preview_url,
        "capture_url": capture_url,
        "capture_url_recovery": recovery if preview_url else {},
        "capture_source": "generated_owner_review_packet" if fallback_reason else "local_preview",
        "capture_method": "durable_stage_media_reuse" if durable_reuse.get("captured") else "playwright_screenshot",
        "durable_media_reuse": durable_reuse,
        "fallback_reason": fallback_reason,
        "captures": captures,
        "command": captures[-1].get("command", "") if captures else "",
        "path": captures[0].get("path", "") if captures and captures[0].get("captured") else "",
        "returncode": 0 if captured else 1,
        "stdout_tail": _truncate(" | ".join(item.get("stdout_tail", "") for item in captures), 1200),
        "stderr_tail": _truncate(" | ".join(item.get("stderr_tail", "") or item.get("error_type", "") for item in captures), 1200),
    }


def _recover_local_preview_capture_url(preview_url, local_preview=None):
    preview_url = str(preview_url or "").strip()
    parsed = urlparse(preview_url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost"}:
        return {"url": preview_url, "status": "not_local"}

    original_probe = _probe_local_http_url(preview_url)
    if original_probe.get("ok"):
        return {"url": preview_url, "status": "original_reachable", "probe": original_probe}

    command = str((local_preview or {}).get("command") or "")
    ports = _local_preview_ports_from_command(command)
    if parsed.port:
        ports = [port for port in ports if port != str(parsed.port)]
    for port in ports:
        candidate = parsed._replace(netloc=f"{parsed.hostname}:{port}").geturl()
        probe = _probe_local_http_url(candidate)
        if probe.get("ok"):
            return {
                "url": candidate,
                "status": "recovered_from_preview_command_port",
                "original_url": preview_url,
                "original_probe": original_probe,
                "command": command,
                "probe": probe,
            }
    return {
        "url": preview_url,
        "status": "unrecovered",
        "original_probe": original_probe,
        "candidate_ports": ports,
        "command": command,
    }


def _local_preview_ports_from_command(command_text=""):
    text = str(command_text or "")
    ports = []
    for explicit, colon in re.findall(r"--port\s+(\d+)|:(\d+)", text):
        port = explicit or colon
        if port and port not in ports:
            ports.append(port)
    return ports


def _probe_local_http_url(url):
    parsed = urlparse(str(url or ""))
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost"}:
        return {"ok": False, "status": "not_local"}
    try:
        opener = url_request.build_opener(url_request.HTTPRedirectHandler)
        req = url_request.Request(url, headers={"User-Agent": "CHARLIE-local-preview-capture-probe"})
        with opener.open(req, timeout=3) as response:
            status = int(response.status)
            final_url = response.geturl()
    except URLError as exc:
        return {"ok": False, "status": "probe_failed", "error_type": exc.__class__.__name__, "reason": str(exc.reason) if hasattr(exc, "reason") else str(exc)}
    except (OSError, ValueError) as exc:
        return {"ok": False, "status": "probe_failed", "error_type": exc.__class__.__name__}
    if status >= 500:
        return {"ok": False, "status": "bad_status", "http_status": status, "final_url": final_url}
    return {"ok": True, "status": "ok", "http_status": status, "final_url": final_url}


def _promote_durable_visual_review_media(mission_id, artifacts=None):
    mission_id = str(mission_id or "").strip()
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    media_dir = _review_media_path(mission_id)
    media_dir.mkdir(parents=True, exist_ok=True)
    evidence = _durable_visual_evidence_paths(artifacts)
    promoted = []
    for viewport, filename in (("desktop", "owner_review_preview.png"), ("mobile", "owner_review_mobile.png")):
        source_path = evidence.get(viewport)
        if not source_path:
            continue
        target_path = media_dir / filename
        try:
            shutil.copy2(source_path, target_path)
        except OSError as exc:
            promoted.append({
                "viewport": viewport,
                "captured": False,
                "status": "durable_media_copy_failed",
                "source_path": str(source_path),
                "error_type": exc.__class__.__name__,
            })
            continue
        promoted.append({
            "viewport": viewport,
            "captured": True,
            "status": "promoted_from_durable_stage_media",
            "source_path": str(source_path),
            "path": str(target_path),
            "filename": filename,
        })
    captured = (media_dir / "owner_review_preview.png").exists() and (media_dir / "owner_review_mobile.png").exists()
    return {
        "label": "durable stage media reuse",
        "captured": captured,
        "status": "promoted_from_durable_stage_media" if captured else "durable_stage_media_missing",
        "promoted": promoted,
    }


def _durable_visual_evidence_paths(artifacts=None):
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    found = {}
    for agent in ("builder", "tester", "qa_red_team", "visual_qa_reviewer", "reviewer"):
        artifact = artifacts.get(agent) if isinstance(artifacts.get(agent), dict) else {}
        for value in _visual_evidence_values_from_artifact(artifact):
            path = _resolve_durable_visual_evidence_path(value)
            if not path:
                continue
            viewport = _visual_evidence_viewport(value, path)
            if viewport and viewport not in found:
                found[viewport] = path
    return found


def _visual_evidence_values_from_artifact(artifact):
    keys = ("screenshots_captured", "media_references_used", "browser_checks", "visual_review_notes")
    values = []
    for key in keys:
        raw = artifact.get(key)
        if isinstance(raw, list):
            values.extend(raw)
        elif raw:
            values.append(raw)
    return values


def _resolve_durable_visual_evidence_path(value):
    candidates = []
    if isinstance(value, dict):
        for key in ("path", "local_path", "reference", "file", "filename"):
            if value.get(key):
                candidates.append(str(value.get(key)))
    else:
        text = str(value or "")
        candidates.append(text)
        candidates.extend(re.findall(r"[\w./:\\ -]+\.(?:png|jpe?g|webp|gif|mp4|webm)", text, flags=re.IGNORECASE))
    for candidate in candidates:
        path = _resolve_local_visual_evidence_path(candidate)
        if path:
            return path
    return None


def _resolve_local_visual_evidence_path(candidate):
    raw = str(candidate or "").strip().strip("\"'")
    if not raw:
        return None
    if raw.startswith("/api/charlie/build-relay/review-media/"):
        parts = raw.strip("/").split("/")
        if len(parts) >= 5:
            raw = str(_review_media_path(parts[-2]) / parts[-1])
    path = Path(raw)
    if not path.is_absolute():
        path = REPO_ROOT / raw
    try:
        resolved = path.resolve()
    except OSError:
        return None
    if not resolved.exists() or not resolved.is_file() or resolved.suffix.lower() not in REVIEW_MEDIA_EXTENSIONS:
        return None
    allowed_roots = [
        RUNTIME_ROOT / ".charlie_runner",
        REVIEW_MEDIA_DIR,
        LEGACY_REVIEW_MEDIA_DIR,
    ]
    for root in allowed_roots:
        try:
            resolved_root = root.resolve()
        except OSError:
            continue
        if resolved == resolved_root or resolved_root in resolved.parents:
            return resolved
    return None


def _visual_evidence_viewport(value, path):
    text = f"{value} {path.name}".lower()
    if "mobile" in text or "390" in text or "844" in text:
        return "mobile"
    if "desktop" in text or "laptop" in text or "1440" in text or "900" in text or "preview" in text:
        return "desktop"
    return ""


def _npx_executable():
    if os.name == "nt":
        return shutil.which("npx.cmd") or shutil.which("npx.exe") or "npx.cmd"
    return shutil.which("npx") or "npx"


def _is_control_dashboard_preview_url(url):
    parsed = urlparse(str(url or ""))
    return parsed.path.rstrip("/") in {"", "/charlie"}


def _preview_url_matches_changed_ui(url, changed_files=None, final_message=""):
    parsed = urlparse(str(url or ""))
    path = parsed.path.rstrip("/") or "/"
    files = " ".join(str(item or "").replace("\\", "/").lower() for item in (changed_files or []))
    text = f"{files} {str(final_message or '').lower()}"
    if path == "/charlie":
        return any(token in text for token in ("templates/charlie.html", "charliemissioncontrol", "mission control", "/charlie"))
    return path != "/"


def _infer_changed_ui_preview_url(preview_url, changed_files=None, final_message=""):
    parsed = urlparse(str(preview_url or ""))
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost"}:
        return {"url": "", "status": "not_local_preview"}
    files = " ".join(str(item or "").replace("\\", "/").lower() for item in (changed_files or []))
    text = f"{files} {str(final_message or '').lower()}"
    route = ""
    if "salesavailability.js" in text or "sales availability" in text or "sales dashboard" in text:
        route = "/sales-dashboard"
    elif "templates/charlie" in text or "charliemissioncontrol" in text or "mission control" in text:
        route = "/charlie"
    if not route or route == (parsed.path.rstrip("/") or "/"):
        return {"url": "", "status": "no_changed_route_inferred"}
    candidate = parsed._replace(path=route, params="", query="", fragment="").geturl()
    probe = _probe_local_http_url(candidate)
    if not probe.get("ok"):
        return {"url": "", "status": "inferred_route_not_reachable", "candidate_url": candidate, "probe": probe}
    return {
        "url": candidate,
        "status": "inferred_changed_ui_route",
        "source": "changed_files",
        "probe": probe,
    }


def _write_visual_review_preview_html(
    mission_id="",
    media_dir=None,
    local_preview=None,
    changed_files=None,
    artifacts=None,
    final_message="",
    fallback_reason="",
):
    media_dir = Path(media_dir or _review_media_path(mission_id))
    media_dir.mkdir(parents=True, exist_ok=True)
    html_path = media_dir / "owner_review_preview.html"
    html_path.write_text(
        _visual_review_preview_html(
            mission_id=mission_id,
            local_preview=local_preview,
            changed_files=changed_files,
            artifacts=artifacts,
            final_message=final_message,
            fallback_reason=fallback_reason,
        ),
        encoding="utf-8",
    )
    return html_path


def _visual_review_preview_html(
    mission_id="",
    local_preview=None,
    changed_files=None,
    artifacts=None,
    final_message="",
    fallback_reason="",
):
    local_preview = local_preview if isinstance(local_preview, dict) else {}
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    changed_files = [str(path or "").strip() for path in (changed_files or []) if str(path or "").strip()]
    stage_cards = []
    for agent in ("builder", "tester", "qa_red_team", "reviewer"):
        artifact = artifacts.get(agent) if isinstance(artifacts.get(agent), dict) else {}
        summary = _truncate(artifact.get("summary") or "", 320)
        status = "complete" if summary else "not recorded"
        stage_cards.append(
            f"<article><span>{html.escape(agent.replace('_', ' ').title())}</span>"
            f"<strong>{html.escape(status)}</strong><p>{html.escape(summary or 'No summary captured for this stage.')}</p></article>"
        )
    file_items = "".join(f"<li>{html.escape(path)}</li>" for path in changed_files[:12]) or "<li>No changed files listed.</li>"
    preview_url = str(local_preview.get("url") or "").strip()
    final_summary = _truncate(final_message or "Owner review packet generated from CHARLIE agent artifacts.", 500)
    reason = fallback_reason.replace("_", " ") or "generated visual packet"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>CHARLIE Owner Review Visual Packet</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; color: #17202a; background: #f5f7fa; }}
    main {{ width: 1120px; min-height: 720px; padding: 34px; box-sizing: border-box; }}
    .top {{ display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; margin-bottom: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; letter-spacing: 0; }}
    .mission {{ color: #506070; font-size: 15px; }}
    .badge {{ background: #153e75; color: white; padding: 8px 12px; border-radius: 6px; font-weight: 700; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 22px 0; }}
    article, .panel {{ background: white; border: 1px solid #d7dde5; border-radius: 8px; padding: 16px; box-shadow: 0 1px 2px rgba(20, 32, 45, .06); }}
    article span {{ display: block; color: #667789; font-size: 12px; text-transform: uppercase; font-weight: 700; margin-bottom: 8px; }}
    article strong {{ display: block; font-size: 18px; margin-bottom: 8px; }}
    article p, .panel p {{ margin: 0; line-height: 1.45; color: #354253; font-size: 14px; }}
    .two {{ display: grid; grid-template-columns: 1.1fr .9fr; gap: 16px; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; }}
    ul {{ margin: 0; padding-left: 19px; color: #354253; line-height: 1.55; font-size: 14px; }}
    .meta {{ margin-top: 14px; color: #657386; font-size: 13px; }}
  </style>
</head>
<body>
  <main>
    <div class="top">
      <div>
        <h1>CHARLIE Owner Review Visual Packet</h1>
        <div class="mission">{html.escape(str(mission_id or 'Mission'))}</div>
      </div>
      <div class="badge">Ready For Owner Review</div>
    </div>
    <section class="panel">
      <h2>Review Summary</h2>
      <p>{html.escape(final_summary)}</p>
      <div class="meta">Capture source: {html.escape(reason)}{html.escape(' | Local preview: ' + preview_url if preview_url else '')}</div>
    </section>
    <section class="grid">{''.join(stage_cards)}</section>
    <section class="two">
      <div class="panel">
        <h2>Changed Files</h2>
        <ul>{file_items}</ul>
      </div>
      <div class="panel">
        <h2>Owner Decision Gate</h2>
        <p>This packet is generated by the local runner from the completed agent handoff artifacts. Final approval remains owner-controlled before release cleanup or deployment.</p>
      </div>
    </section>
  </main>
</body>
</html>"""


def _is_ui_related_mission(mission_type="", changed_files=None, final_message=""):
    combined_text = f"{mission_type} {final_message}"
    if explicit_non_ui_requested(combined_text):
        return False
    mission_type = str(mission_type or "").lower()
    if re.search(r"\b(ui|frontend|dashboard|visual|page|browser)\b", mission_type):
        return True
    paths = [str(path or "").replace("\\", "/").lower() for path in (changed_files or [])]
    ui_prefixes = ("templates/", "static/js/", "static/css/")
    ui_suffixes = (".html", ".css", ".js", ".jsx", ".tsx", ".vue", ".svelte")
    if any(path.startswith(ui_prefixes) or path.endswith(ui_suffixes) for path in paths):
        return True
    text = str(final_message or "").lower()
    return "local preview" in text or "screenshot" in text or "visual review" in text


def _review_media_path(mission_id):
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "-", str(mission_id or "").strip())[:120] or "unknown"
    return REVIEW_MEDIA_DIR / safe_id


def _review_media_candidate_paths(mission_id):
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "-", str(mission_id or "").strip())[:120] or "unknown"
    paths = [REVIEW_MEDIA_DIR / safe_id]
    legacy = LEGACY_REVIEW_MEDIA_DIR / safe_id
    if legacy not in paths:
        paths.append(legacy)
    return paths


def _resolve_review_media_dir(media_dir):
    try:
        resolved_dir = media_dir.resolve()
    except OSError:
        return None
    for root in (REVIEW_MEDIA_DIR, LEGACY_REVIEW_MEDIA_DIR):
        try:
            resolved_root = root.resolve()
        except OSError:
            continue
        if resolved_dir == resolved_root or resolved_root in resolved_dir.parents:
            return resolved_dir
    return None


def _review_media_items(mission_id):
    items = []
    for media_dir in _review_media_candidate_paths(mission_id):
        resolved_dir = _resolve_review_media_dir(media_dir)
        if not resolved_dir or not media_dir.exists() or not media_dir.is_dir():
            continue
        for path in sorted(media_dir.iterdir(), key=lambda item: item.name.lower()):
            if not path.is_file() or path.suffix.lower() not in REVIEW_MEDIA_EXTENSIONS:
                continue
            media_type = "video" if path.suffix.lower() in {".mp4", ".webm"} else "image"
            items.append({
                "label": path.stem.replace("_", " ").replace("-", " ")[:120] or path.name,
                "media_type": media_type,
                "reference": f"/api/charlie/build-relay/review-media/{media_dir.name}/{path.name}",
                "path": str(path),
                "filename": path.name,
            })
            if len(items) >= 12:
                return items
    return items


def _visual_review_summary(ui_related, media, preview_url):
    if not ui_related:
        return "Mission did not touch detected UI files; visual review media is not required."
    if media:
        return f"{len(media)} local visual review artifact(s) captured; UI owner review requires real desktop/laptop and mobile screenshots from the changed page."
    if preview_url:
        return "UI mission has a local preview URL, but the local runner could not capture screenshot media."
    return "UI mission detected; no local preview URL was captured, so screenshot capture is blocked."


def _visual_stage_evidence(artifacts):
    evidence = []
    for agent in ("builder", "tester", "qa_red_team", "reviewer"):
        artifact = artifacts.get(agent) if isinstance(artifacts.get(agent), dict) else {}
        summary = _truncate(artifact.get("summary", ""), 220)
        if summary:
            evidence.append({"agent": agent, "summary": summary})
    return evidence


def cleanup_visual_review_media(mission_id):
    media_dir = _review_media_path(mission_id)
    try:
        resolved_dir = media_dir.resolve()
        resolved_root = REVIEW_MEDIA_DIR.resolve()
    except OSError as exc:
        return {"cleaned": False, "status": "review_media_path_invalid", "error_type": exc.__class__.__name__}
    if resolved_root not in resolved_dir.parents:
        return {"cleaned": False, "status": "review_media_path_outside_runner_root"}
    if not media_dir.exists():
        return {"cleaned": True, "status": "review_media_not_present", "local_path": str(media_dir)}
    try:
        shutil.rmtree(media_dir)
    except OSError as exc:
        return {
            "cleaned": False,
            "status": "review_media_cleanup_failed",
            "local_path": str(media_dir),
            "error_type": exc.__class__.__name__,
        }
    return {
        "cleaned": True,
        "status": "review_media_cleaned",
        "local_path": str(media_dir),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def process_visual_review_cleanup_intent(mission_id="", mission=None, database_url=None, connect_factory=None):
    mission_id = str(mission_id or "").strip()
    if not mission_id:
        return {"processed": False, "status": "mission_id_required"}
    if not isinstance(mission, dict):
        loaded, status_code = get_mission(
            mission_id,
            database_url=database_url,
            connect_factory=connect_factory,
        )
        if status_code >= 400:
            return {"processed": False, "status": loaded.get("status", "mission_load_failed")}
        mission = loaded.get("mission") or {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    review_packet = dict(metadata.get("review_packet") or {})
    visual_review = dict(review_packet.get("visual_review") or {})
    cleanup = dict(visual_review.get("cleanup") or {})
    if cleanup.get("status") != "cleanup_requested":
        return {"processed": False, "status": "cleanup_not_requested"}
    cleanup_result = cleanup_visual_review_media(mission_id)
    cleanup.update({
        "status": "cleaned" if cleanup_result.get("cleaned") else cleanup_result.get("status", "cleanup_failed"),
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "result": cleanup_result,
    })
    visual_review["cleanup"] = cleanup
    review_packet["visual_review"] = visual_review
    vault_result, vault_status = update_mission_vault(
        mission_id,
        {"review_packet": review_packet},
        notes="Local runner processed visual review cleanup intent.",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if vault_status >= 400:
        return {
            "processed": False,
            "status": "cleanup_metadata_update_failed",
            "cleanup_result": cleanup_result,
            "vault_status": vault_result.get("status", ""),
        }
    return {
        "processed": True,
        "status": cleanup.get("status"),
        "cleanup_result": cleanup_result,
    }


def process_visual_review_cleanup_queue(statuses=None, limit=20, database_url=None, connect_factory=None):
    statuses = statuses or ("release_approved", "done", "merged", "deployed")
    processed = []
    for status in statuses:
        loaded, status_code = list_missions(
            status=status,
            limit=limit,
            database_url=database_url,
            connect_factory=connect_factory,
        )
        if status_code >= 400:
            continue
        for mission in loaded.get("missions", []):
            result = process_visual_review_cleanup_intent(
                mission_id=mission.get("mission_id", ""),
                mission=mission,
                database_url=database_url,
                connect_factory=connect_factory,
            )
            if result.get("processed"):
                processed.append({"mission_id": mission.get("mission_id", ""), **result})
    return {
        "success": True,
        "status": "visual_review_cleanup_queue_processed",
        "processed_count": len(processed),
        "processed": processed,
    }


def _release_packet(mission, execution_id):
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    return {
        "execution_id": execution_id,
        "mission_id": mission.get("mission_id", ""),
        "title": mission.get("title", ""),
        "status": mission.get("status", ""),
        "approval_level": mission.get("approval_level", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "release_agent_gate",
        "release_agent_version": AGENT_RUNNER_VERSION,
        "allowed_actions_now": ["no_release_closeout"],
        "blocked_actions_without_final_owner_approval": ["merge", "deploy", "production_migration", "customer_send", "public_post", "payment", "reservation", "farm_lifecycle_write"],
        "review_summary": review_packet.get("summary", ""),
        "review_changed_files": review_packet.get("changed_files", []),
        "review_test_evidence": review_packet.get("test_evidence", []),
        "agent_execution": review_packet.get("agent_execution", {}),
        "quality_gates": review_packet.get("quality_gates", []),
        "handoff_reports": review_packet.get("handoff_reports", {}),
        "qa_evidence": review_packet.get("qa_evidence", []),
        "backflow_events": review_packet.get("backflow_events", []),
        "live_release_verification": {
            "contract": "charlie_live_release_verification_v1",
            "default_verify_url": _default_release_verify_url(),
            "required_for_deployed_status": True,
            "status_rule": "Merge can mark merged; only a verified live URL can mark deployed.",
        },
        "operator_instruction": "Release Agent may merge a referenced PR only after final owner approval, then must verify the configured live URL before marking deployed.",
    }


def _review_pr_reference(mission):
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    links = review_packet.get("links") if isinstance(review_packet.get("links"), dict) else {}
    candidates = [
        review_packet.get("pr_number"),
        review_packet.get("pr_url"),
        links.get("pr"),
        links.get("pull_request"),
        links.get("diff"),
    ]
    for candidate in candidates:
        value = str(candidate or "").strip()
        if not value:
            continue
        if "/pull/" in value:
            number = value.rstrip("/").split("/pull/")[-1].split("/")[0].strip()
            return number or value
        return value
    return ""


def _reconcile_merged_pr(pr_reference, runner):
    command = ["gh", "pr", "view", str(pr_reference), "--json", "state,mergedAt,mergeCommit,url,number"]
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(REPO_ROOT),
            timeout=120,
            check=False,
        )
    except Exception as exc:
        return {
            "merged": False,
            "status": "pr_reconciliation_failed",
            "error_type": exc.__class__.__name__,
        }
    result = {
        "command": " ".join(command),
        "returncode": completed.returncode,
        "stdout": _truncate(completed.stdout or "", 2000),
        "stderr": _truncate(completed.stderr or "", 2000),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "merged": False,
    }
    if completed.returncode != 0:
        result["status"] = "pr_reconciliation_command_failed"
        return result
    try:
        parsed = json.loads(completed.stdout or "{}")
    except ValueError:
        result["status"] = "pr_reconciliation_json_invalid"
        return result
    state = str(parsed.get("state") or "").upper()
    result.update({
        "status": "pr_reconciliation_complete",
        "state": state,
        "url": parsed.get("url", ""),
        "number": parsed.get("number", ""),
        "merged_at": parsed.get("mergedAt", ""),
        "merge_commit": parsed.get("mergeCommit", {}),
        "merged": state == "MERGED" or bool(parsed.get("mergedAt")),
    })
    return result


def _run_agent_model_process(
    command,
    input="",
    cwd=None,
    timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
    stdout_path=None,
    stderr_path=None,
    final_path=None,
    mission_id="",
    model_assignment=None,
    **kwargs,
):
    model_assignment = model_assignment if isinstance(model_assignment, dict) else {}
    provider = str(model_assignment.get("runtime_provider") or "").strip().lower()
    if provider == "anthropic":
        completed = _run_anthropic_agent_process(
            command,
            input=input,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            final_path=final_path,
            mission_id=mission_id,
            model_assignment=model_assignment,
            **kwargs,
        )
        if completed.returncode == 0:
            return completed
        write_runner_heartbeat({
            "status": "anthropic_agent_fallback_to_codex",
            "mission_id": mission_id,
            "execution_artifact": str(final_path or ""),
            "final_artifact_present": False,
            "model_provider": "codex_cli",
            "fallback_from_provider": "anthropic",
            "stderr_tail": _tail_text(completed.stderr, 1200),
        })
        fallback_prompt = (
            f"{input or ''}\n\n"
            "CHARLIE PROVIDER FALLBACK: Anthropic/Claude did not return a usable stage artifact. "
            "Complete this same stage through the local Codex provider and include provider_fallback=true in the final JSON."
        )
        return _run_codex_process(
            _codex_fallback_command(command),
            input=fallback_prompt,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            final_path=final_path,
            mission_id=mission_id,
            **kwargs,
        )
    return _run_codex_process(
        command,
        input=input,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        final_path=final_path,
        mission_id=mission_id,
        **kwargs,
    )


def _codex_fallback_command(command):
    command = list(command or [])
    cleaned = []
    skip_next = False
    for item in command:
        if skip_next:
            skip_next = False
            continue
        if item in {"--model", "-m"}:
            skip_next = True
            continue
        cleaned.append(item)
    return cleaned


def _completed_process_from_stage_exception(command, exc, paths):
    returncode = 124 if isinstance(exc, subprocess.TimeoutExpired) else 78
    error_type = exc.__class__.__name__
    error_text = str(exc)[:2000]
    if isinstance(exc, subprocess.TimeoutExpired):
        error_text = f"Stage runner timed out after {getattr(exc, 'timeout', '')} seconds."
    stderr = json.dumps({
        "status": "agent_stage_runner_exception",
        "error_type": error_type,
        "error": error_text,
        "recovery": "CHARLIE converted the runner exception into a blocked review packet instead of leaving the mission in progress.",
    }, indent=2)
    try:
        _write_process_text(paths["stderr_path"], stderr)
        if not _read_text(paths["stdout_path"]):
            _write_process_text(paths["stdout_path"], "")
    except Exception:
        pass
    return subprocess.CompletedProcess(command, returncode, "", stderr)


def _run_anthropic_agent_process(
    command,
    input="",
    cwd=None,
    timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
    stdout_path=None,
    stderr_path=None,
    final_path=None,
    mission_id="",
    model_assignment=None,
    **_kwargs,
):
    stdout_path = Path(stdout_path)
    stderr_path = Path(stderr_path)
    final_path = Path(final_path)
    started = time.monotonic()
    model_assignment = model_assignment if isinstance(model_assignment, dict) else {}
    write_runner_heartbeat({
        "status": "anthropic_agent_running",
        "mission_id": mission_id,
        "execution_artifact": str(final_path),
        "elapsed_seconds": 0,
        "changed_files_count": len(_changed_files()),
        "final_artifact_present": False,
        "model_provider": "anthropic",
        "model": model_assignment.get("runtime_model", ""),
    })
    result, status_code = run_anthropic_prompt(
        input,
        model=model_assignment.get("runtime_model", ""),
        timeout_seconds=min(int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS), AGENT_NO_PROGRESS_TIMEOUT_SECONDS),
    )
    elapsed = int(time.monotonic() - started)
    if status_code < 400 and result.get("success"):
        text = str(result.get("text") or "").strip()
        _write_process_text(final_path, text)
        _write_process_text(stdout_path, text)
        _write_process_text(stderr_path, "")
        write_runner_heartbeat({
            "status": "anthropic_agent_final_artifact_seen",
            "mission_id": mission_id,
            "execution_artifact": str(final_path),
            "elapsed_seconds": elapsed,
            "changed_files_count": len(_changed_files()),
            "final_artifact_present": bool(text),
            "model_provider": "anthropic",
            "model": result.get("model", model_assignment.get("runtime_model", "")),
            "stdout_tail": _tail_text(text, 1200),
            "stderr_tail": "",
        })
        return subprocess.CompletedProcess(command, 0, text, "")

    stderr = json.dumps({
        "status": result.get("status", "anthropic_failed"),
        "status_code": status_code,
        "error": result.get("error", ""),
        "error_type": result.get("error_type", ""),
    }, indent=2)
    _write_process_text(stdout_path, "")
    _write_process_text(stderr_path, stderr)
    write_runner_heartbeat({
        "status": "anthropic_agent_failed",
        "mission_id": mission_id,
        "execution_artifact": str(final_path),
        "elapsed_seconds": elapsed,
        "changed_files_count": len(_changed_files()),
        "final_artifact_present": False,
        "model_provider": "anthropic",
        "model": model_assignment.get("runtime_model", ""),
        "stdout_tail": "",
        "stderr_tail": _tail_text(stderr, 1200),
    })
    return subprocess.CompletedProcess(command, 78, "", stderr)


def _run_codex_process(
    command,
    input="",
    cwd=None,
    timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
    stdout_path=None,
    stderr_path=None,
    final_path=None,
    mission_id="",
    execution_id="",
    **_kwargs,
):
    stdout_path = Path(stdout_path)
    stderr_path = Path(stderr_path)
    final_path = Path(final_path)
    started = time.monotonic()
    final_seen_at = None
    last_progress_at = started
    last_progress_signature = None
    last_lease_refresh_at = 0.0
    no_final_timeout = min(
        int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS),
        NO_FINAL_ARTIFACT_TIMEOUT_SECONDS,
    )
    stdout_handle = stdout_path.open("w", encoding="utf-8", errors="replace")
    stderr_handle = stderr_path.open("w", encoding="utf-8", errors="replace")
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        **background_process_kwargs(),
    )
    execution_id = str(execution_id or f"process-{process.pid}")
    runner_generation = str(os.getenv("CHARLIE_SUPERVISOR_GENERATION") or "unmanaged-generation")
    ownership_expected = {
        "runner_generation": runner_generation, "mission_id": str(mission_id or "unscoped-mission"),
        "execution_id": execution_id, "ownership_type": "charlie_agent",
    }
    ownership_record = make_ownership_record(
        inspect_process(process.pid), **ownership_expected,
    )
    try:
        if process.stdin:
            process.stdin.write(input or "")
            process.stdin.close()
            process.stdin = None
        while process.poll() is None:
            now = time.monotonic()
            elapsed = now - started
            final_exists = final_path.exists() and final_path.stat().st_size > 0
            if final_exists and final_seen_at is None:
                final_seen_at = now
            changed_files = _changed_files()
            progress_signature = (
                _file_progress_signature(stdout_path),
                _file_progress_signature(stderr_path),
                tuple(changed_files),
            )
            if progress_signature != last_progress_signature:
                last_progress_signature = progress_signature
                last_progress_at = now
            idle_seconds = now - last_progress_at
            supervisor_status = "codex_final_artifact_seen" if final_exists else "codex_running"
            if not final_exists and idle_seconds >= NO_FINAL_ARTIFACT_WARNING_SECONDS:
                supervisor_status = "codex_no_final_artifact_warning"
            write_runner_heartbeat({
                "status": supervisor_status,
                "mission_id": mission_id,
                "execution_artifact": str(final_path),
                "elapsed_seconds": int(elapsed),
                "idle_seconds": int(idle_seconds),
                "changed_files_count": len(changed_files),
                "final_artifact_present": final_exists,
                "stdout_tail": _read_tail(stdout_path, 1200),
                "stderr_tail": _read_tail(stderr_path, 1200),
            })
            if now - last_lease_refresh_at >= 30:
                _refresh_execution_lease(mission_id, process.pid, supervisor_status)
                last_lease_refresh_at = now
            if final_seen_at and now - final_seen_at >= FINAL_ARTIFACT_GRACE_SECONDS:
                _terminate_process_tree(ownership_record, ownership_expected)
                break
            if not final_exists and idle_seconds >= no_final_timeout:
                _terminate_process_tree(ownership_record, ownership_expected)
                break
            if elapsed >= int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS):
                if final_exists:
                    _terminate_process_tree(ownership_record, ownership_expected)
                    break
                raise subprocess.TimeoutExpired(command, timeout_seconds)
            time.sleep(POLL_SECONDS)
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(ownership_record, ownership_expected)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        raise
    finally:
        stdout_handle.close()
        stderr_handle.close()
        _wait_for_file_handles_released([stdout_path, stderr_path])
    stdout = _read_text(stdout_path)
    stderr = _read_text(stderr_path)
    returncode = process.returncode
    final_exists = final_path.exists() and final_path.stat().st_size > 0
    if returncode is None:
        returncode = 0 if final_exists else 124
    write_runner_heartbeat({
        "status": "codex_final_artifact_seen" if final_exists else "codex_no_final_artifact_timeout",
        "mission_id": mission_id,
        "execution_artifact": str(final_path),
        "elapsed_seconds": int(time.monotonic() - started),
        "changed_files_count": len(_changed_files()),
        "final_artifact_present": final_exists,
        "stdout_tail": _tail_text(stdout, 1200),
        "stderr_tail": _tail_text(stderr, 1200),
    })
    if not final_exists:
        if returncode in (0, None):
            returncode = 124
        stderr = (stderr or "") + "\nCHARLIE supervisor stopped Codex because no final artifact was produced before timeout.\n"
    if final_exists and returncode not in (0,):
        returncode = 0
        stderr = (stderr or "") + "\nCodex process was stopped after final artifact was written.\n"
    return subprocess.CompletedProcess(command, returncode, stdout or "", stderr or "")


def _windowless_process_kwargs(platform_name=None):
    """Keep local agent subprocesses from opening transient Windows consoles."""
    platform_name = os.name if platform_name is None else platform_name
    if platform_name != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}


def _refresh_execution_lease(mission_id, process_id=0, stage_status=""):
    """Keep the durable lease fresh while the owned model process is alive."""
    if not mission_id:
        return False
    loaded, status_code = get_mission(mission_id)
    if status_code >= 400:
        return False
    mission = loaded.get("mission") if isinstance(loaded, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission, dict) and isinstance(mission.get("metadata"), dict) else {}
    lease = dict(metadata.get("execution_lease") or {})
    if not lease.get("lease_id"):
        return False
    now = datetime.now(timezone.utc)
    ttl = max(int(lease.get("ttl_seconds") or 900), 120)
    lease.update({
        "heartbeat_at": now.isoformat(),
        "expires_at": datetime.fromtimestamp(now.timestamp() + ttl, timezone.utc).isoformat(),
        "process_id": int(process_id or 0),
        "stage_status": str(stage_status or ""),
    })
    result, refresh_status = update_mission_vault(
        mission_id,
        {"execution_lease": lease},
        notes="CHARLIE refreshed the active execution lease.",
    )
    return refresh_status < 400 and result.get("success") is not False


def _file_progress_signature(path):
    try:
        stat = Path(path).stat()
    except OSError:
        return (0, 0)
    return (int(stat.st_size), int(stat.st_mtime_ns))


def _terminate_process_tree(ownership_record, expected_ownership=None, inspector=inspect_process):
    if emergency_process_cleanup_disabled():
        requested_pid = ownership_record.get("pid") if isinstance(ownership_record, dict) else ownership_record
        return record_emergency_cleanup_refusal("_terminate_process_tree", requested_pid)
    if not process_termination_enabled():
        return {"authorized": False, "reason": "process_termination_not_enabled"}
    decision = validate_termination(ownership_record, expected_ownership, inspector)
    if not decision["authorized"]:
        return decision
    pid = decision["pid"]
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
            **background_run_kwargs(),
        )
        return {"authorized": True, "terminated": True, "pid": pid}
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return {"authorized": False, "reason": "termination_failed", "pid": pid}
    return {"authorized": True, "terminated": True, "pid": pid}


def _wait_for_file_handles_released(paths, timeout_seconds=2.0):
    deadline = time.monotonic() + float(timeout_seconds or 0)
    paths = [Path(path) for path in (paths or []) if path]
    while paths and time.monotonic() < deadline:
        locked = []
        for path in paths:
            if not path.exists():
                continue
            probe = path.with_name(f"{path.name}.release-probe-{os.getpid()}")
            try:
                path.replace(probe)
                probe.replace(path)
            except OSError:
                locked.append(path)
                if probe.exists() and not path.exists():
                    try:
                        probe.replace(path)
                    except OSError:
                        pass
        if not locked:
            return True
        paths = locked
        time.sleep(0.05)
    return False


def _resolve_execution_artifact(mission_id, execution_id="", prompt_path=None, stdout_path=None, stderr_path=None, final_path=None):
    mission_suffix = str(mission_id or "")[-8:]
    final_path = Path(final_path) if final_path else None
    if final_path is None:
        candidates = sorted(
            EXECUTION_DIR.glob(f"{mission_suffix}-*.final.md"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        final_path = candidates[0] if candidates else EXECUTION_DIR / f"{mission_suffix}.final.md"
    stem = final_path.name[:-len(".final.md")] if final_path.name.endswith(".final.md") else final_path.stem
    return {
        "execution_id": execution_id or stem,
        "prompt_path": Path(prompt_path) if prompt_path else final_path.with_name(f"{stem}.prompt.md"),
        "stdout_path": Path(stdout_path) if stdout_path else final_path.with_name(f"{stem}.stdout.txt"),
        "stderr_path": Path(stderr_path) if stderr_path else final_path.with_name(f"{stem}.stderr.txt"),
        "final_path": final_path,
    }


def _extract_local_preview(final_message):
    text = str(final_message or "")
    match = re.search(r"https?://127\.0\.0\.1:\d+/\S*", text)
    url = match.group(0).rstrip(").,\"'") if match else ""
    return {
        "url": url,
        "command": ".\\venv\\Scripts\\python.exe -m flask --app app run --host 127.0.0.1 --port 5000",
        "status": "captured" if url else "not_captured",
        "message": "No mission-specific local preview URL was captured in the final artifact." if not url else "",
    }


def _extract_errors(final_message):
    lines = [line.strip("- ").strip() for line in str(final_message or "").splitlines()]
    return [line for line in lines if "error" in line.lower() or "could not" in line.lower()][:12]


def _verify_release_url(verify_url):
    verify_url = str(verify_url or "").strip()
    if not verify_url:
        return {"verified": False, "status": "verify_url_not_provided"}
    try:
        with url_request.urlopen(verify_url, timeout=30) as response:
            return {
                "verified": 200 <= int(response.status) < 400,
                "status": "ok",
                "url": verify_url,
                "http_status": int(response.status),
            }
    except (OSError, URLError, ValueError) as exc:
        return {
            "verified": False,
            "status": "verify_failed",
            "url": verify_url,
            "error_type": exc.__class__.__name__,
        }


def _wait_for_release_verification(verify_url, attempts=AGENT_RELEASE_VERIFY_ATTEMPTS, interval_seconds=AGENT_RELEASE_VERIFY_INTERVAL_SECONDS):
    verify_url = str(verify_url or "").strip()
    attempts = max(1, int(attempts or 1))
    interval_seconds = max(0, int(interval_seconds or 0))
    if not verify_url:
        return {
            "verified": False,
            "status": "verify_url_not_configured",
            "url": "",
            "attempts": 0,
            "history": [],
            "required_env": "CHARLIE_RELEASE_VERIFY_URL or AMADEUS_BACKEND_URL or RENDER_EXTERNAL_URL/RENDER_EXTERNAL_HOSTNAME",
        }
    results = []
    for attempt in range(1, attempts + 1):
        result = _verify_release_url(verify_url)
        result["attempt"] = attempt
        results.append(result)
        if result.get("verified"):
            return {
                **result,
                "attempts": attempt,
                "history": results,
                "status": "release_verified",
            }
        if attempt < attempts and interval_seconds:
            time.sleep(interval_seconds)
    final = results[-1] if results else {"verified": False, "status": "verify_url_not_provided", "url": verify_url}
    return {
        **final,
        "verified": False,
        "attempts": len(results),
        "history": results,
        "status": final.get("status", "release_not_verified"),
    }


def _default_release_verify_url():
    explicit_url = str(env_value("CORE_RELEASE_VERIFY_URL") or "").strip()
    if explicit_url:
        return explicit_url
    base_url = str(os.getenv("AMADEUS_BACKEND_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if base_url:
        return f"{base_url}/charlie"
    hostname = str(os.getenv("RENDER_EXTERNAL_HOSTNAME") or "").strip()
    if hostname:
        return f"https://{hostname}/charlie"
    return ""


def _codex_executable():
    if os.name == "nt":
        return shutil.which("codex.cmd") or shutil.which("codex.exe") or shutil.which("codex") or "codex.cmd"
    return shutil.which("codex") or "codex"


def _extract_test_evidence(final_message):
    lines = [line.strip("- ").strip() for line in str(final_message or "").splitlines()]
    evidence = [line for line in lines if "test" in line.lower() or "check" in line.lower() or "verify" in line.lower()]
    return evidence[:12] or ["Review Codex final response for verification details."]


def _extract_file_mentions(final_message):
    text = str(final_message or "")
    matches = re.findall(r"[\w./\\-]+\.(?:py|js|css|html|md|json|sql|yml|yaml)", text)
    cleaned = []
    for match in matches:
        value = match.strip("`'\".,)")
        if value and value not in cleaned:
            cleaned.append(value)
    return cleaned[:20] or ["Artifact did not list inspected files."]


def _extract_command_mentions(final_message):
    commands = []
    for line in str(final_message or "").splitlines():
        stripped = line.strip().strip("`")
        lower = stripped.lower()
        if lower.startswith((".\\venv", "python", "node", "npm", "git ", "gh ", "rg ", "npx ")):
            commands.append(stripped)
    return commands[:20] or ["Artifact did not list commands run."]


def _execution_id(mission_id):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    seed = f"{mission_id}|{timestamp}"
    digest = str(abs(hash(seed)))[:10]
    return f"{mission_id[-8:] or 'mission'}-{timestamp}-{digest}"


def _read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _format_list(items):
    if not isinstance(items, list) or not items:
        return "- Not captured yet."
    return "\n".join(f"- {item}" for item in items if str(item).strip()) or "- Not captured yet."


def _format_workflow(workflow):
    if not workflow:
        return "- planner, architect, builder, tester, reviewer pending"
    lines = []
    for item in workflow:
        if isinstance(item, dict):
            lines.append(f"- {item.get('agent', 'agent')}: {item.get('status', 'pending')} - {item.get('purpose', '')}")
    return "\n".join(lines) or "- planner, architect, builder, tester, reviewer pending"


def _truncate(value, max_len):
    return str(value or "").strip()[:max_len]
