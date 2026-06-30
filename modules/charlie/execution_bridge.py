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
POLL_SECONDS = 5


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
            write_runner_heartbeat({
                "status": "codex_final_artifact_seen" if final_exists else "codex_running",
                "mission_id": mission_id,
                "execution_artifact": str(final_path),
            })
            if final_seen_at and time.monotonic() - final_seen_at >= FINAL_ARTIFACT_GRACE_SECONDS:
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
