import json
import os
import re
import shutil
import signal
import subprocess
import time
from urllib import request as url_request
from urllib.error import URLError
from datetime import datetime, timezone
from pathlib import Path

from modules.charlie.mission_store import (
    AGENT_SEQUENCE,
    get_mission,
    list_missions,
    update_mission_status,
    update_mission_vault,
    update_mission_workflow_step,
)
from modules.charlie.runner_control import write_runner_heartbeat


REPO_ROOT = Path(__file__).resolve().parents[2]
EXECUTION_DIR = REPO_ROOT / ".charlie_runner" / "executions"
DEFAULT_TIMEOUT_SECONDS = 3600
FINAL_ARTIFACT_GRACE_SECONDS = 20
NO_FINAL_ARTIFACT_TIMEOUT_SECONDS = 1200
NO_FINAL_ARTIFACT_WARNING_SECONDS = 600
POLL_SECONDS = 5
AGENT_RUNNER_VERSION = "charlie_agent_runner_v2"
AGENT_ARTIFACT_REQUIRED_KEYS = {
    "planner": ["summary", "acceptance_criteria", "test_plan", "commands_run", "files_inspected"],
    "architect": ["summary", "files_to_inspect", "risk_notes", "implementation_plan", "commands_run", "files_inspected"],
    "builder": ["summary", "changed_files", "build_notes", "commands_run", "files_inspected"],
    "tester": ["summary", "tests_run", "test_status", "commands_run", "files_inspected"],
    "reviewer": ["summary", "recommended_owner_decision", "release_notes", "changed_files", "test_evidence", "commands_run", "files_inspected"],
}
AGENT_NO_PROGRESS_TIMEOUT_SECONDS = 1800
AGENT_BACKFLOW_LIMIT = 2
AGENT_RELEASE_VERIFY_ATTEMPTS = 12
AGENT_RELEASE_VERIFY_INTERVAL_SECONDS = 10


def prepare_codex_execution(mission_id="", status="in_progress", output_dir=None, database_url=None, connect_factory=None):
    mission, status_code, error = _load_execution_mission(
        mission_id=mission_id,
        status=status,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status_code >= 400:
        return error, status_code

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
    runner = run_subprocess or _run_codex_process
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
    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")
    final_message = _read_text(final_path) or (completed.stdout or "").strip()
    if final_message and not _read_text(final_path):
        final_path.write_text(final_message, encoding="utf-8")

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
):
    mission, status_code, error = _load_execution_mission(
        mission_id=mission_id,
        status=status,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status_code >= 400:
        return error, status_code

    output_dir = Path(output_dir or EXECUTION_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    execution_id = _execution_id(mission["mission_id"])
    started_at = datetime.now(timezone.utc).isoformat()
    ledger = _agent_execution_ledger(mission, execution_id, started_at)
    start_agent = _execution_start_agent(mission)
    artifacts = _existing_agent_artifacts_for_rerun(mission, start_agent)
    if start_agent != AGENT_SEQUENCE[0]:
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

    runner = run_subprocess or _run_codex_process
    command_base = codex_command or [
        _codex_executable(),
        "exec",
        "--cd",
        str(REPO_ROOT),
        "--sandbox",
        "workspace-write",
    ]

    agent_queue = _agent_queue_from(start_agent)
    stage_attempts = {agent: 0 for agent in AGENT_SEQUENCE}
    backflow_counts = {agent: 0 for agent in AGENT_SEQUENCE}
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
        prompt = build_agent_stage_prompt(mission, agent, artifacts, ledger)
        stage_paths["prompt_path"].write_text(prompt, encoding="utf-8")
        command = [
            *command_base,
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
        completed = runner(
            command,
            input=prompt,
            cwd=str(REPO_ROOT),
            timeout_seconds=min(int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS), AGENT_NO_PROGRESS_TIMEOUT_SECONDS),
            stdout_path=stage_paths["stdout_path"],
            stderr_path=stage_paths["stderr_path"],
            final_path=stage_paths["final_path"],
            mission_id=mission["mission_id"],
        )
        stage_paths["stdout_path"].write_text(completed.stdout or "", encoding="utf-8")
        stage_paths["stderr_path"].write_text(completed.stderr or "", encoding="utf-8")
        final_message = _read_text(stage_paths["final_path"]) or (completed.stdout or "").strip()
        if final_message and not _read_text(stage_paths["final_path"]):
            stage_paths["final_path"].write_text(final_message, encoding="utf-8")

        if completed.returncode != 0 or not _read_text(stage_paths["final_path"]):
            return _block_agent_stage(
                mission["mission_id"],
                execution_id,
                ledger,
                agent,
                stage_paths,
                completed,
                stage_started,
                database_url=database_url,
                connect_factory=connect_factory,
            )

        artifact = _agent_artifact_from_final(agent, _read_text(stage_paths["final_path"]))
        artifact = _inherit_pr_reference(agent, artifact, artifacts)
        artifact.update({
            "agent": agent,
            "artifact_path": str(stage_paths["final_path"]),
            "stdout_path": str(stage_paths["stdout_path"]),
            "stderr_path": str(stage_paths["stderr_path"]),
            "stdout_tail": _tail_text(completed.stdout or _read_text(stage_paths["stdout_path"]), 1200),
            "stderr_tail": _tail_text(completed.stderr or _read_text(stage_paths["stderr_path"]), 1200),
            "attempt": stage_attempts[agent],
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        validation = _validate_agent_artifact(agent, artifact)
        if not validation["valid"]:
            return _block_agent_stage(
                mission["mission_id"],
                execution_id,
                ledger,
                agent,
                stage_paths,
                completed,
                stage_started,
                blocked_reason=f"Agent artifact missing required keys: {', '.join(validation['missing_keys'])}.",
                database_url=database_url,
                connect_factory=connect_factory,
            )
        quality = _agent_quality_gate(agent, artifact)
        if not quality["passed"]:
            backflow_target = _agent_backflow_target(agent, artifact, quality)
            if backflow_target and backflow_counts.get(backflow_target, 0) < AGENT_BACKFLOW_LIMIT:
                backflow_counts[backflow_target] = backflow_counts.get(backflow_target, 0) + 1
                _append_backflow_event(
                    ledger,
                    from_agent=agent,
                    to_agent=backflow_target,
                    reason=quality["reason"],
                    attempt=backflow_counts[backflow_target],
                )
                artifacts[agent] = artifact
                artifacts = _discard_downstream_artifacts(artifacts, backflow_target)
                agent_queue = _agent_queue_from(backflow_target)
                _write_agent_ledger(output_dir, execution_id, ledger)
                write_runner_heartbeat({
                    "status": "agent_backflow",
                    "mission_id": mission["mission_id"],
                    "agent_runner_version": AGENT_RUNNER_VERSION,
                    "current_agent": backflow_target,
                    "current_action": f"{agent} sent work back to {backflow_target}: {quality['reason']}",
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
                database_url=database_url,
                connect_factory=connect_factory,
            )
        artifact["quality_gate"] = quality
        artifacts[agent] = artifact
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
        _record_execution_stage(
            mission["mission_id"],
            agent,
            "complete",
            _truncate(artifact.get("summary") or f"{agent} completed.", 1000),
            database_url=database_url,
            connect_factory=connect_factory,
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
    }, 504


def prepare_release_execution(mission_id="", output_dir=None, database_url=None, connect_factory=None):
    mission, status_code, error = _load_release_mission(
        mission_id=mission_id,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status_code >= 400:
        return error, status_code

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
    return {
        "success": True,
        "status": "release_no_release_completed",
        "mission_id": mission_id,
        "mission_status": "done",
        "release_packet_path": release_packet_path,
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

    runner = run_subprocess or subprocess.run
    command = ["gh", "pr", "merge", pr_reference, "--squash", "--delete-branch"]
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
        if reconciliation.get("merged"):
            merge_result["reconciled_as_merged"] = True
            return _complete_release_merge(
                mission_id=mission_id,
                release_packet_path=release_packet_path,
                merge_result=merge_result,
                verify_url=verify_url,
                verify_attempts=verify_attempts,
                verify_interval_seconds=verify_interval_seconds,
                database_url=database_url,
                connect_factory=connect_factory,
            )
        update_mission_vault(
            mission_id,
            {
                "release_packet": {
                    "mode": "merge_pr",
                    "release_packet_path": release_packet_path,
                    "merge_result": merge_result,
                    "status": "release_pr_merge_failed",
                }
            },
            notes="Local release bridge recorded failed PR merge result.",
            database_url=database_url,
            connect_factory=connect_factory,
        )
        update_mission_status(
            mission_id,
            "blocked",
            owner_decision="Local release bridge failed to merge the approved PR.",
            event_type="status_changed",
            notes="gh pr merge returned a non-zero exit code.",
            metadata={
                "script": "scripts/charlie_release_bridge.py",
                "release_packet_path": release_packet_path,
                "release_mode": "merge_pr",
                "returncode": completed.returncode,
            },
            database_url=database_url,
            connect_factory=connect_factory,
        )
        return {
            "success": False,
            "status": "release_pr_merge_failed",
            "mission_id": mission_id,
            "mission_status": "blocked",
            "release_packet_path": release_packet_path,
            "merge_result": merge_result,
        }, 502

    return _complete_release_merge(
        mission_id=mission_id,
        release_packet_path=release_packet_path,
        merge_result=merge_result,
        verify_url=verify_url,
        verify_attempts=verify_attempts,
        verify_interval_seconds=verify_interval_seconds,
        database_url=database_url,
        connect_factory=connect_factory,
    )


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
    return {
        "success": True,
        "status": "release_pr_merged",
        "mission_id": mission_id,
        "mission_status": final_status,
        "release_packet_path": release_packet_path,
        "merge_result": merge_result,
        "verify_result": verify_result,
    }, 200


def build_codex_execution_prompt(mission):
    mission = mission if isinstance(mission, dict) else {}
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    workflow = mission.get("agent_workflow") if isinstance(mission.get("agent_workflow"), list) else []
    context_pack = mission.get("mission_context_pack") if isinstance(mission.get("mission_context_pack"), dict) else {}
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
2. Stay within the recorded approval level and the forbidden actions.
3. Do not merge, deploy, apply migrations, send customers, post publicly, take payments, reserve stock, or change farm lifecycle records unless the mission explicitly authorizes that action and the deployment SOP is clean.
4. Run focused verification that fits the actual changes.
5. Stop at owner review. Do not mark the mission done.
6. In your final response, include: summary, files changed, tests run, errors/bugs, local preview link or command, and recommended owner review decision.
"""


def build_agent_stage_prompt(mission, agent, artifacts=None, ledger=None):
    mission = mission if isinstance(mission, dict) else {}
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    review_packet = (mission.get("metadata") or {}).get("review_packet") if isinstance(mission.get("metadata"), dict) else {}
    owner_comments = review_packet.get("owner_comments_pending", "") if isinstance(review_packet, dict) else ""
    return f"""You are the CHARLIE CORE {agent.upper()} agent running inside Agent Runner v2.

Mission ID: {mission.get("mission_id", "")}
Title: {mission.get("title", "")}
Approval level: {mission.get("approval_level", "")}
Mission type: {mission.get("mission_type", "")}

Mission:
{mission.get("raw_text", "")}

Required CHARLIE docs to follow:
- docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md
- docs/00-start-here/CHARLIE_CORE_AGENT_RUNNER_V2.md
- docs/00-start-here/CURRENT_STATE.md
- docs/00-start-here/NEXT_STEPS.md
- docs/00-start-here/WORKFLOW.md
- docs/00-start-here/DEPLOYMENT_SOP.md

Desired outcome:
{vault.get("desired_outcome") or ""}

Owner send-back comments:
{owner_comments or "None"}

Forbidden actions:
{_format_list(vault.get("forbidden_actions"))}

Previous agent artifacts:
{json.dumps(artifacts, indent=2)[:8000]}

You must work like an interactive coding agent:
- inspect the repo before asserting facts
- read relevant files
- run focused commands when useful
- patch only scoped files
- recover from errors
- record what you did and what remains

Stage responsibility:
{_agent_stage_instruction(agent)}

Required final response format:
Return concise markdown, and include a JSON object fenced as ```json with these keys:
{json.dumps(_agent_required_schema(agent), indent=2)}

Do not merge, deploy, apply migrations, send customers, post publicly, take payments, reserve stock, or change farm lifecycle records.
Stop at the required artifact for this stage.
"""


def _agent_stage_instruction(agent):
    if agent == "planner":
        return "Read mission context and define scope, acceptance criteria, test plan, risks, and exact next handoff."
    if agent == "architect":
        return "Inspect implementation boundaries, source files, route/data contracts, risks, and the safest build approach."
    if agent == "builder":
        return (
            "Implement only the scoped change, keep diffs tight, and record changed files. "
            "When changed_files contains releaseable changes under LEVEL 3 or higher, create or update a branch, commit the scoped diff, push it, open a PR, "
            "and record branch_name, commit_sha, pr_url/pr_number, and PR link evidence. Do not merge."
        )
    if agent == "tester":
        return "Run focused verification, investigate failures, and return pass/fail evidence."
    return "Review diff, requirements, tests, safety gates, release notes, and prepare owner review recommendation."


def _agent_required_schema(agent):
    base = {
        "summary": "short factual summary",
        "errors": [],
        "bugs": [],
        "files_inspected": [],
        "commands_run": [],
        "stdout_tail": "short relevant command output tail or empty",
        "stderr_tail": "short relevant error output tail or empty",
        "next_action": "next handoff",
    }
    if agent == "planner":
        base.update({"acceptance_criteria": [], "test_plan": [], "scope": "scoped work"})
    elif agent == "architect":
        base.update({"files_to_inspect": [], "risk_notes": [], "implementation_plan": []})
    elif agent == "builder":
        base.update({
            "changed_files": [],
            "build_notes": [],
            "branch_name": "branch containing scoped changed files",
            "commit_sha": "commit containing scoped changed files",
            "pr_url": "pull request URL when changed_files contains releaseable changes",
            "pr_number": "pull request number when changed_files contains releaseable changes",
            "links": {"pr": "pull request URL"},
        })
    elif agent == "tester":
        base.update({"tests_run": [], "test_status": "pass|fail|blocked"})
    else:
        base.update({
            "recommended_owner_decision": "approve_final_release|send_back|pause",
            "release_notes": [],
            "changed_files": [],
            "test_evidence": [],
            "pr_url": "pull request URL when changed_files contains releaseable changes",
            "pr_number": "pull request number when changed_files contains releaseable changes",
            "links": {"pr": "pull request URL", "local_preview": "local preview URL if available"},
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


def _execution_start_agent(mission):
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    target = str(review_packet.get("return_to_stage") or "").strip().lower()
    if target in AGENT_SEQUENCE:
        return target
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    stage = str(vault.get("mission_stage") or "").strip().lower()
    if stage.startswith("returned_to_"):
        target = stage.replace("returned_to_", "", 1)
        if target in AGENT_SEQUENCE:
            return target
    return AGENT_SEQUENCE[0]


def _existing_agent_artifacts_for_rerun(mission, start_agent):
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    existing = review_packet.get("agent_artifacts") if isinstance(review_packet.get("agent_artifacts"), dict) else {}
    if start_agent not in AGENT_SEQUENCE:
        return {}
    start_index = AGENT_SEQUENCE.index(start_agent)
    return {
        agent: artifact
        for agent, artifact in existing.items()
        if agent in AGENT_SEQUENCE
        and AGENT_SEQUENCE.index(agent) < start_index
        and isinstance(artifact, dict)
    }


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
    item.update({
        "status": status,
        "attempt": int(attempt or 1),
        "started_at": started_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
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
        if item["quality_gate"]:
            gates = ledger.setdefault("quality_gates", [])
            gates = [gate for gate in gates if not (gate.get("agent") == agent and int(gate.get("attempt") or 1) == int(attempt or 1))]
            gates.append({"agent": agent, "attempt": int(attempt or 1), **item["quality_gate"]})
            ledger["quality_gates"] = gates
    if existing is None:
        stages.append(item)
    ledger["status"] = "running" if status == "running" else ledger.get("status", "running")
    ledger["last_progress_at"] = item["updated_at"]
    return ledger


def _write_agent_ledger(output_dir, execution_id, ledger):
    path = Path(output_dir) / f"{execution_id}.agent-ledger.json"
    path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return path


def _agent_artifact_from_final(agent, final_message):
    parsed = _extract_json_object(final_message)
    if parsed:
        return parsed
    artifact = {
        "summary": _truncate(final_message or f"{agent} completed.", 1200),
        "errors": _extract_errors(final_message),
        "bugs": [],
        "files_inspected": _extract_file_mentions(final_message),
        "commands_run": _extract_command_mentions(final_message),
        "stdout_tail": "",
        "stderr_tail": "",
        "next_action": "Continue to next CHARLIE agent.",
    }
    if agent == "planner":
        artifact.update({"acceptance_criteria": ["Review final artifact."], "test_plan": ["Run focused verification."], "scope": artifact["summary"]})
    elif agent == "architect":
        artifact.update({"files_to_inspect": _changed_files(), "risk_notes": [], "implementation_plan": [artifact["summary"]]})
    elif agent == "builder":
        artifact.update({"changed_files": _changed_files(), "build_notes": [artifact["summary"]]})
    elif agent == "tester":
        artifact.update({"tests_run": _extract_test_evidence(final_message), "test_status": "pass" if not artifact["errors"] else "blocked"})
    else:
        artifact.update({"recommended_owner_decision": "approve_final_release", "release_notes": ["Review PR and test evidence before final approval."], "changed_files": _changed_files(), "test_evidence": _extract_test_evidence(final_message)})
    return artifact


def _extract_json_object(text):
    text = str(text or "")
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    candidates = [fenced.group(1)] if fenced else []
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{"):text.rfind("}") + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _validate_agent_artifact(agent, artifact):
    required = AGENT_ARTIFACT_REQUIRED_KEYS.get(agent, ["summary"])
    missing = [key for key in required if not artifact.get(key)]
    return {"valid": not missing, "missing_keys": missing}


def _agent_quality_gate(agent, artifact):
    errors = artifact.get("errors") if isinstance(artifact.get("errors"), list) else []
    bugs = artifact.get("bugs") if isinstance(artifact.get("bugs"), list) else []
    commands = artifact.get("commands_run") if isinstance(artifact.get("commands_run"), list) else []
    inspected = artifact.get("files_inspected") if isinstance(artifact.get("files_inspected"), list) else []
    if not commands:
        return {"passed": False, "reason": f"{agent} did not record commands_run evidence."}
    if not inspected:
        return {"passed": False, "reason": f"{agent} did not record files_inspected evidence."}
    if agent == "tester":
        status = str(artifact.get("test_status") or "").strip().lower()
        if status != "pass":
            return {"passed": False, "reason": f"Tester reported test_status={status or 'missing'}."}
        if errors or bugs:
            return {"passed": False, "reason": "Tester reported errors or bugs."}
    if agent == "builder":
        changed_files = artifact.get("changed_files") if isinstance(artifact.get("changed_files"), list) else []
        pr_reference = _artifact_pr_reference(artifact)
        if _has_release_relevant_changes(changed_files) and not pr_reference:
            return {"passed": False, "reason": "Builder changed releaseable files but did not record a PR link or PR number."}
    if agent == "reviewer":
        decision = str(artifact.get("recommended_owner_decision") or "").strip()
        if decision != "approve_final_release":
            return {"passed": False, "reason": f"Reviewer recommended {decision or 'no approval'}."}
        if errors or bugs:
            return {"passed": False, "reason": "Reviewer found errors or bugs."}
        changed_files = artifact.get("changed_files") if isinstance(artifact.get("changed_files"), list) else []
        pr_reference = _artifact_pr_reference(artifact)
        if _has_release_relevant_changes(changed_files) and not pr_reference:
            return {"passed": False, "reason": "Reviewer did not record a PR link or PR number for changed code/docs."}
    return {
        "passed": True,
        "reason": f"{agent} quality gate passed.",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


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


def _inherit_pr_reference(agent, artifact, artifacts):
    if agent != "reviewer" or _artifact_pr_reference(artifact):
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
    return inherited


def _has_release_relevant_changes(changed_files):
    files = [str(item or "").strip() for item in (changed_files if isinstance(changed_files, list) else [])]
    ignored = {"No changed files detected by git diff.", ""}
    return any(path not in ignored for path in files)


def _agent_backflow_target(agent, artifact, quality):
    if agent == "tester":
        return "builder"
    if agent == "reviewer":
        target = str(artifact.get("send_back_stage") or "").strip().lower()
        return target if target in AGENT_SEQUENCE else "builder"
    return ""


def _append_backflow_event(ledger, from_agent, to_agent, reason, attempt):
    event = {
        "from_agent": from_agent,
        "to_agent": to_agent,
        "reason": reason,
        "attempt": int(attempt or 1),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    ledger.setdefault("backflow_events", []).append(event)
    ledger["last_progress_at"] = event["recorded_at"]
    return event


def _discard_downstream_artifacts(artifacts, target_agent):
    target_index = AGENT_SEQUENCE.index(target_agent)
    return {
        agent: artifact
        for agent, artifact in artifacts.items()
        if agent in AGENT_SEQUENCE and AGENT_SEQUENCE.index(agent) < target_index
    }


def _agent_queue_from(target_agent):
    target_index = AGENT_SEQUENCE.index(target_agent)
    return list(AGENT_SEQUENCE[target_index:])


def _block_agent_stage(
    mission_id,
    execution_id,
    ledger,
    agent,
    paths,
    completed,
    started_at,
    blocked_reason="Agent did not produce a valid final artifact.",
    database_url=None,
    connect_factory=None,
):
    ledger["status"] = "blocked"
    ledger["blocked_agent"] = agent
    ledger["blocked_reason"] = blocked_reason
    ledger["completed_at"] = datetime.now(timezone.utc).isoformat()
    _append_ledger_stage(ledger, agent, "blocked", started_at, paths, artifact={
        "summary": blocked_reason,
        "returncode": getattr(completed, "returncode", None),
        "stdout_excerpt": _truncate(getattr(completed, "stdout", "") or _read_text(paths["stdout_path"]), 1200),
        "stderr_excerpt": _truncate(getattr(completed, "stderr", "") or _read_text(paths["stderr_path"]), 1200),
    }, attempt=_stage_attempt_from_path(paths["final_path"]))
    ledger_path = _write_agent_ledger(paths["final_path"].parent, execution_id, ledger)
    update_mission_vault(
        mission_id,
        {
            "agent_execution": ledger,
            "review_packet": {
                "summary": f"CHARLIE Agent Runner v2 blocked at {agent}: {blocked_reason}",
                "findings": [f"{agent} did not complete a valid stage artifact.", "The mission is blocked visibly instead of silently running."],
                "errors": [blocked_reason],
                "bugs": [],
                "changed_files": _changed_files() or ["No changed files detected by git diff."],
                "test_evidence": ["Agent workflow stopped before final tester/reviewer evidence."],
                "links": {},
                "execution_artifacts": {"execution_id": execution_id, "agent_ledger_path": str(ledger_path), "blocked_agent": agent},
                "agent_execution": _agent_execution_summary(ledger),
                "review_status": "agent_blocked",
            },
        },
        notes="CHARLIE Agent Runner v2 recorded a blocked stage.",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    _record_execution_stage(mission_id, agent, "blocked", blocked_reason, database_url=database_url, connect_factory=connect_factory)
    blocked, blocked_status = update_mission_status(
        mission_id,
        "blocked",
        owner_decision=f"CHARLIE Agent Runner v2 blocked at {agent}.",
        event_type="status_changed",
        notes=blocked_reason,
        metadata={"agent_runner_version": AGENT_RUNNER_VERSION, "execution_id": execution_id, "blocked_agent": agent},
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if blocked_status >= 400:
        return blocked, blocked_status
    return {
        "success": False,
        "status": "agent_stage_blocked",
        "mission_id": mission_id,
        "mission_status": "blocked",
        "agent": agent,
        "blocked_reason": blocked_reason,
        "agent_ledger_path": str(ledger_path),
    }, 504


def _complete_agent_execution_v2(mission, execution_id, ledger, artifacts, output_dir, started_at, database_url=None, connect_factory=None):
    ledger["status"] = "complete"
    ledger["completed_at"] = datetime.now(timezone.utc).isoformat()
    ledger_path = _write_agent_ledger(output_dir, execution_id, ledger)
    reviewer = artifacts.get("reviewer", {})
    tester = artifacts.get("tester", {})
    builder = artifacts.get("builder", {})
    reviewer_links = reviewer.get("links") if isinstance(reviewer.get("links"), dict) else {}
    local_preview = _extract_local_preview(reviewer.get("summary", ""))
    review_links = dict(reviewer_links)
    review_links["local_preview"] = review_links.get("local_preview") or local_preview.get("url", "")
    review_packet = {
        "review_packet": {
            "summary": reviewer.get("summary") or "CHARLIE Agent Runner v2 completed all stages.",
            "findings": [
                artifacts.get("planner", {}).get("summary", "Planner completed."),
                artifacts.get("architect", {}).get("summary", "Architect completed."),
                builder.get("summary", "Builder completed."),
                tester.get("summary", "Tester completed."),
                reviewer.get("summary", "Reviewer completed."),
            ],
            "errors": _collect_artifact_list(artifacts, "errors"),
            "bugs": _collect_artifact_list(artifacts, "bugs"),
            "changed_files": reviewer.get("changed_files") or builder.get("changed_files") or _changed_files() or ["No changed files detected by git diff."],
            "test_evidence": reviewer.get("test_evidence") or tester.get("tests_run") or ["Tester artifact did not list tests."],
            "local_preview": local_preview,
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
            "quality_gates": ledger.get("quality_gates", []),
            "backflow_events": ledger.get("backflow_events", []),
            "agent_artifacts": artifacts,
            "review_status": "ready_for_owner_review",
        },
        "agent_execution": ledger,
    }
    update_mission_vault(
        mission["mission_id"],
        review_packet,
        notes="CHARLIE Agent Runner v2 populated owner review packet.",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    reviewer_result, reviewer_status = update_mission_workflow_step(
        mission["mission_id"],
        "reviewer",
        step_status="complete",
        findings="CHARLIE Agent Runner v2 completed all stages and prepared owner review packet.",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if reviewer_status >= 400:
        return reviewer_result, reviewer_status
    return {
        "success": True,
        "status": "agent_execution_completed",
        "mission_id": mission["mission_id"],
        "mission_status": "pr_ready",
        "execution_id": execution_id,
        "agent_runner_version": AGENT_RUNNER_VERSION,
        "agent_ledger_path": str(ledger_path),
    }, 200


def _collect_artifact_list(artifacts, key):
    collected = []
    for artifact in artifacts.values():
        value = artifact.get(key)
        if isinstance(value, list):
            collected.extend(item for item in value if item)
        elif value:
            collected.append(value)
    return collected


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
    return {
        "version": ledger.get("version", ""),
        "execution_id": ledger.get("execution_id", ""),
        "status": ledger.get("status", ""),
        "last_progress_at": ledger.get("last_progress_at", ""),
        "blocked_agent": ledger.get("blocked_agent", ""),
        "blocked_reason": ledger.get("blocked_reason", ""),
        "backflow_events": ledger.get("backflow_events", []),
        "stages": stages,
    }


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
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


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
        "backflow_events": review_packet.get("backflow_events", []),
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


def _run_codex_process(
    command,
    input="",
    cwd=None,
    timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
    stdout_path=None,
    stderr_path=None,
    final_path=None,
    mission_id="",
    **_kwargs,
):
    stdout_path = Path(stdout_path)
    stderr_path = Path(stderr_path)
    final_path = Path(final_path)
    started = time.monotonic()
    final_seen_at = None
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
    )
    try:
        if process.stdin:
            process.stdin.write(input or "")
            process.stdin.close()
            process.stdin = None
        while process.poll() is None:
            elapsed = time.monotonic() - started
            final_exists = final_path.exists() and final_path.stat().st_size > 0
            if final_exists and final_seen_at is None:
                final_seen_at = time.monotonic()
            changed_files = _changed_files()
            supervisor_status = "codex_final_artifact_seen" if final_exists else "codex_running"
            if not final_exists and elapsed >= NO_FINAL_ARTIFACT_WARNING_SECONDS:
                supervisor_status = "codex_no_final_artifact_warning"
            write_runner_heartbeat({
                "status": supervisor_status,
                "mission_id": mission_id,
                "execution_artifact": str(final_path),
                "elapsed_seconds": int(elapsed),
                "changed_files_count": len(changed_files),
                "final_artifact_present": final_exists,
                "stdout_tail": _read_tail(stdout_path, 1200),
                "stderr_tail": _read_tail(stderr_path, 1200),
            })
            if final_seen_at and time.monotonic() - final_seen_at >= FINAL_ARTIFACT_GRACE_SECONDS:
                _terminate_process_tree(process.pid)
                break
            if not final_exists and elapsed >= no_final_timeout:
                _terminate_process_tree(process.pid)
                break
            if elapsed >= int(timeout_seconds or DEFAULT_TIMEOUT_SECONDS):
                if final_exists:
                    _terminate_process_tree(process.pid)
                    break
                raise subprocess.TimeoutExpired(command, timeout_seconds)
            time.sleep(POLL_SECONDS)
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process.pid)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        raise
    finally:
        stdout_handle.close()
        stderr_handle.close()
    stdout = _read_text(stdout_path)
    stderr = _read_text(stderr_path)
    returncode = process.returncode
    if returncode is None:
        returncode = 0 if final_path.exists() and final_path.stat().st_size > 0 else 124
    if not final_path.exists() or final_path.stat().st_size <= 0:
        if returncode in (0, None):
            returncode = 124
        stderr = (stderr or "") + "\nCHARLIE supervisor stopped Codex because no final artifact was produced before timeout.\n"
    if final_path.exists() and final_path.stat().st_size > 0 and returncode not in (0,):
        returncode = 0
        stderr = (stderr or "") + "\nCodex process was stopped after final artifact was written.\n"
    return subprocess.CompletedProcess(command, returncode, stdout or "", stderr or "")


def _terminate_process_tree(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return
    if pid <= 0:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return


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
    url = match.group(0).rstrip(").,") if match else "http://127.0.0.1:5000/charlie"
    return {
        "url": url,
        "command": ".\\venv\\Scripts\\python.exe -m flask --app app run --host 127.0.0.1 --port 5000",
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
