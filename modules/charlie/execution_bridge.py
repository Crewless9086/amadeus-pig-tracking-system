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
    "planner": ["summary", "acceptance_criteria", "test_plan"],
    "architect": ["summary", "files_to_inspect", "risk_notes"],
    "builder": ["summary", "changed_files"],
    "tester": ["summary", "tests_run"],
    "reviewer": ["summary", "recommended_owner_decision"],
}
AGENT_NO_PROGRESS_TIMEOUT_SECONDS = 1800


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
    artifacts = {}

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

    for agent in AGENT_SEQUENCE:
        _record_execution_stage(
            mission["mission_id"],
            agent,
            "active",
            f"CHARLIE Agent Runner v2 started {agent}.",
            database_url=database_url,
            connect_factory=connect_factory,
        )
        stage_paths = _agent_stage_paths(output_dir, execution_id, agent)
        prompt = build_agent_stage_prompt(mission, agent, artifacts, ledger)
        stage_paths["prompt_path"].write_text(prompt, encoding="utf-8")
        command = [
            *command_base,
            "--output-last-message",
            str(stage_paths["final_path"]),
            "-",
        ]
        stage_started = datetime.now(timezone.utc).isoformat()
        _append_ledger_stage(ledger, agent, "running", stage_started, stage_paths, current_action=f"{agent} running")
        _write_agent_ledger(output_dir, execution_id, ledger)
        write_runner_heartbeat({
            "status": "agent_stage_running",
            "mission_id": mission["mission_id"],
            "agent_runner_version": AGENT_RUNNER_VERSION,
            "current_agent": agent,
            "current_action": f"{agent} running",
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
        artifact.update({
            "agent": agent,
            "artifact_path": str(stage_paths["final_path"]),
            "stdout_path": str(stage_paths["stdout_path"]),
            "stderr_path": str(stage_paths["stderr_path"]),
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
        artifacts[agent] = artifact
        _append_ledger_stage(ledger, agent, "complete", stage_started, stage_paths, artifact=artifact)
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

    verify_result = _verify_release_url(verify_url)
    final_status = "deployed" if verify_result.get("verified") else "merged"
    vault_result, vault_status = update_mission_vault(
        mission_id,
        {
            "release_packet": {
                "mode": "merge_pr",
                "release_packet_path": release_packet_path,
                "merge_result": merge_result,
                "verify_result": verify_result,
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
        return "Implement only the scoped change, keep diffs tight, and record changed files."
    if agent == "tester":
        return "Run focused verification, investigate failures, and return pass/fail evidence."
    return "Review diff, requirements, tests, safety gates, release notes, and prepare owner review recommendation."


def _agent_required_schema(agent):
    base = {
        "summary": "short factual summary",
        "errors": [],
        "bugs": [],
        "next_action": "next handoff",
    }
    if agent == "planner":
        base.update({"acceptance_criteria": [], "test_plan": [], "scope": "scoped work"})
    elif agent == "architect":
        base.update({"files_to_inspect": [], "risk_notes": [], "implementation_plan": []})
    elif agent == "builder":
        base.update({"changed_files": [], "build_notes": []})
    elif agent == "tester":
        base.update({"tests_run": [], "test_status": "pass|fail|blocked"})
    else:
        base.update({"recommended_owner_decision": "approve_final_release|send_back|pause", "release_notes": [], "changed_files": [], "test_evidence": []})
    return base


def _agent_execution_ledger(mission, execution_id, started_at):
    return {
        "version": AGENT_RUNNER_VERSION,
        "execution_id": execution_id,
        "mission_id": mission.get("mission_id", ""),
        "title": mission.get("title", ""),
        "started_at": started_at,
        "status": "running",
        "stages": [],
    }


def _agent_stage_paths(output_dir, execution_id, agent):
    stem = f"{execution_id}.{agent}"
    return {
        "prompt_path": output_dir / f"{stem}.prompt.md",
        "stdout_path": output_dir / f"{stem}.stdout.txt",
        "stderr_path": output_dir / f"{stem}.stderr.txt",
        "final_path": output_dir / f"{stem}.final.md",
    }


def _append_ledger_stage(ledger, agent, status, started_at, paths, artifact=None, current_action=""):
    stages = ledger.setdefault("stages", [])
    existing = next((item for item in stages if item.get("agent") == agent), None)
    item = existing or {"agent": agent}
    item.update({
        "status": status,
        "started_at": started_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "current_action": current_action,
        "prompt_path": str(paths["prompt_path"]),
        "stdout_path": str(paths["stdout_path"]),
        "stderr_path": str(paths["stderr_path"]),
        "final_path": str(paths["final_path"]),
    })
    if artifact:
        item["artifact"] = artifact
    if existing is None:
        stages.append(item)
    ledger["status"] = "running" if status == "running" else ledger.get("status", "running")
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
    })
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
            "local_preview": _extract_local_preview(reviewer.get("summary", "")),
            "links": {"local_preview": _extract_local_preview(reviewer.get("summary", "")).get("url", "")},
            "release_notes": reviewer.get("release_notes") or ["Review Agent Runner v2 artifacts before final approval."],
            "recommended_owner_decision": reviewer.get("recommended_owner_decision", "approve_final_release"),
            "execution_artifacts": {
                "execution_id": execution_id,
                "agent_runner_version": AGENT_RUNNER_VERSION,
                "agent_ledger_path": str(ledger_path),
                "started_at": started_at,
                "completed_at": ledger["completed_at"],
            },
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
        "mode": "release_gate",
        "allowed_actions_now": ["no_release_closeout"],
        "blocked_actions_without_next_bridge": ["merge", "deploy", "production_migration", "customer_send", "public_post", "payment", "reservation", "farm_lifecycle_write"],
        "review_summary": review_packet.get("summary", ""),
        "review_changed_files": review_packet.get("changed_files", []),
        "review_test_evidence": review_packet.get("test_evidence", []),
        "operator_instruction": "Use --complete-no-release only when final owner approval is enough and no merge/deploy is required.",
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
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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
        stdout, stderr = process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process.pid)
        stdout, stderr = process.communicate(timeout=10)
        raise
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
    stdout_path.write_text(stdout or "", encoding="utf-8")
    stderr_path.write_text(stderr or "", encoding="utf-8")
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


def _codex_executable():
    if os.name == "nt":
        return shutil.which("codex.cmd") or shutil.which("codex.exe") or shutil.which("codex") or "codex.cmd"
    return shutil.which("codex") or "codex"


def _extract_test_evidence(final_message):
    lines = [line.strip("- ").strip() for line in str(final_message or "").splitlines()]
    evidence = [line for line in lines if "test" in line.lower() or "check" in line.lower() or "verify" in line.lower()]
    return evidence[:12] or ["Review Codex final response for verification details."]


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
