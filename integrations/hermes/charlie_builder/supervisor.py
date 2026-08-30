"""Bounded Hermes supervisor bridge for CHARLIE's canonical mission plane.

Hermes is a transport/supervision client.  It never owns mission truth, signs
receipts, writes GitHub, merges, deploys, or exposes arbitrary shell/database
access.  All durable mutation is delegated to authenticated CHARLIE APIs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .native_executor import (
    HermesIndependentReviewer, HermesStructuredPatchWorker, NativeExecutionEngine, NativeExecutionError,
    NativePackager, content_identity, execution_lock, run_argv,
)
from modules.charlie.execution_bridge import build_hermes_native_execution_context
from modules.charlie.mission_admission import canonical_candidate_diff


class HermesBridgeError(RuntimeError):
    """Stable fail-closed bridge error."""


_PLACEHOLDER_VALUES = {
    "changeme", "change-me", "dummy", "example", "none", "null",
    "placeholder", "replace-me", "todo", "unset", "your-token-here",
}


def _protected_value(environ, name, *, required=True):
    value = str((environ or {}).get(name) or "").strip()
    folded = value.lower().replace("_", "-").replace(" ", "-")
    if value and (folded in _PLACEHOLDER_VALUES or "placeholder" in folded):
        raise HermesBridgeError(f"{name.lower()}_placeholder_rejected")
    if required and not value:
        raise HermesBridgeError("hermes_protected_configuration_incomplete")
    return value


def verify_slack_request(signing_secret, timestamp, raw_body, signature, *, now=None, tolerance=300):
    secret = str(signing_secret or "").encode()
    body = raw_body if isinstance(raw_body, bytes) else str(raw_body or "").encode()
    supplied = str(signature or "")
    try:
        sent_at = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise HermesBridgeError("slack_timestamp_invalid") from exc
    if not secret or abs(int(now or time.time()) - sent_at) > tolerance:
        raise HermesBridgeError("slack_request_stale")
    expected = "v0=" + hmac.new(secret, f"v0:{sent_at}:".encode() + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied):
        raise HermesBridgeError("slack_signature_invalid")
    return True


def mission_idempotency_key(mission_id, generation):
    mission_id = str(mission_id or "").strip()
    generation = str(generation or "").strip()
    if not mission_id or not generation:
        raise HermesBridgeError("mission_generation_required")
    return f"{mission_id}:{generation}"


@dataclass(frozen=True)
class CursorAdmission:
    mission_id: str
    generation: str
    receipt_id: str
    repository: str
    base_sha: str
    allowed_files: tuple[str, ...]
    allowed_effects: tuple[str, ...]
    owner_instruction_digest: str
    acceptance_requirements: tuple[str, ...]
    branch: str = ""

    @classmethod
    def from_mapping(cls, value):
        row = dict(value or {})
        required = ("mission_id", "generation", "receipt_id", "repository", "base_sha", "owner_instruction_digest")
        if any(not str(row.get(key) or "").strip() for key in required):
            raise HermesBridgeError("valid_mission_admission_required")
        if not str(row["receipt_id"]).startswith(("MAR-", "PDA-")) or len(str(row["base_sha"])) != 40:
            raise HermesBridgeError("valid_mission_admission_required")
        files = tuple(sorted({str(item).strip() for item in row.get("allowed_files") or [] if str(item).strip()}))
        effects = tuple(sorted({str(item).strip() for item in row.get("allowed_effects") or [] if str(item).strip()}))
        acceptance = tuple(str(item).strip() for item in row.get("acceptance_requirements") or [] if str(item).strip())
        if not files or not effects or not acceptance:
            raise HermesBridgeError("valid_mission_admission_required")
        return cls(*(str(row[key]).strip() for key in required[:5]), files, effects,
                   str(row["owner_instruction_digest"]).strip(), acceptance,
                   str(row.get("branch") or "").strip())


class JsonHttpClient:
    """Small injectable JSON client; error bodies and credentials are never returned."""

    def __init__(self, base_url, token="", opener=None, timeout=15):
        self.base_url = str(base_url or "").rstrip("/")
        self.token = str(token or "")
        self.opener = opener or urllib.request.urlopen
        self.timeout = min(max(int(timeout), 1), 30)

    def request(self, method, path, payload=None, headers=None, query=None):
        if not self.base_url:
            raise HermesBridgeError("transport_not_configured")
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        request_headers = {"Accept": "application/json", **(headers or {})}
        if self.token:
            request_headers["Authorization"] = f"Bearer {self.token}"
        data = None
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode()
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with self.opener(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                return {"error": "conflict", "status_code": 409}
            raise HermesBridgeError("transport_unavailable") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise HermesBridgeError("transport_unavailable") from exc
        if isinstance(result, list):
            return {"items": result}
        if not isinstance(result, dict):
            raise HermesBridgeError("transport_response_invalid")
        return result


class CursorCloudV1:
    """Official Cursor Cloud Agents API v1 adapter."""

    def __init__(self, api_key, *, client=None):
        if not str(api_key or "").strip():
            raise HermesBridgeError("cursor_api_key_required")
        self.client = client or JsonHttpClient("https://api.cursor.com", str(api_key).strip())

    @staticmethod
    def deterministic_agent_id(idempotency_key):
        return "bc-" + str(uuid.uuid5(uuid.NAMESPACE_URL, "charlie:" + idempotency_key))

    def create_agent(self, admission, prompt, *, execution_attempt=1):
        admission = admission if isinstance(admission, CursorAdmission) else CursorAdmission.from_mapping(admission)
        attempt = int(execution_attempt)
        if attempt not in (1, 2, 3, 4, 5):
            raise HermesBridgeError("cursor_execution_attempt_invalid")
        key = mission_idempotency_key(admission.mission_id, admission.generation)
        if attempt > 1:
            key += f":attempt-{attempt}"
        payload = {
            "agentId": self.deterministic_agent_id(key),
            "prompt": {"text": str(prompt or "").strip()},
            "repos": [{"url": f"https://github.com/{admission.repository}", "startingRef": admission.base_sha}],
            "autoCreatePR": True,
            "workOnCurrentBranch": False,
            "mode": "agent",
        }
        if not payload["prompt"]["text"]:
            raise HermesBridgeError("cursor_prompt_required")
        response = self.client.request("POST", "/v1/agents", payload)
        if response.get("status_code") == 409:
            # A crash may occur after Cursor accepted create but before canonical
            # persistence. Recover the deterministic durable Agent, never fork it.
            agent = self.get_agent(payload["agentId"])
            run = self.get_latest_run(payload["agentId"])
            return {"agent": agent, "run": run, "recovered_after_conflict": True}
        return response

    def get_agent(self, agent_id):
        return self.client.request("GET", f"/v1/agents/{_cursor_id(agent_id, 'bc-')}")

    def get_latest_run(self, agent_id):
        agent = self.get_agent(agent_id)
        run_id = _cursor_id(agent.get("latestRunId"), "run-")
        return self.client.request("GET", f"/v1/agents/{_cursor_id(agent_id, 'bc-')}/runs/{run_id}")

    def continue_agent(self, agent_id, prompt):
        agent = self.get_agent(agent_id)
        if agent.get("status") != "IDLE":
            raise HermesBridgeError("cursor_agent_busy")
        return self.client.request("POST", f"/v1/agents/{_cursor_id(agent_id, 'bc-')}/runs",
                                   {"prompt": {"text": str(prompt or "").strip()}, "mode": "agent"})

    def cancel_run(self, agent_id, run_id, *, governed=False):
        if governed is not True:
            raise HermesBridgeError("governed_cancel_required")
        return self.client.request("POST", f"/v1/agents/{_cursor_id(agent_id, 'bc-')}/runs/{_cursor_id(run_id, 'run-')}/cancel")

    def archive_agent(self, agent_id, *, governed=False):
        if governed is not True:
            raise HermesBridgeError("governed_archive_required")
        return self.client.request("POST", f"/v1/agents/{_cursor_id(agent_id, 'bc-')}/archive")

    def list_agents(self, *, pr_url="", include_archived=True):
        query = {"limit": 100, "includeArchived": str(bool(include_archived)).lower()}
        if pr_url:
            query["prUrl"] = pr_url
        return self.client.request("GET", "/v1/agents", query=query)


class CanonicalCharlieApi:
    """Only the bounded authenticated Hermes surface; no raw database access."""

    def __init__(self, base_url, token, *, client=None):
        self.client = client or JsonHttpClient(base_url, token)

    def reconcile_mission(self, payload, idempotency_key):
        return self.client.request("POST", "/charlie/hermes/missions",
                                   {**payload, "idempotency_key": idempotency_key})

    def get_mission(self, mission_id):
        return self.client.request("GET", f"/charlie/hermes/missions/{urllib.parse.quote(str(mission_id), safe='')}")

    def get_dispatch(self, key):
        result = self.client.request("GET", "/charlie/hermes/dispatch", query={"idempotency_key": key})
        return result.get("dispatch") or {}

    def running_writer_count(self):
        return int(self.client.request("GET", "/charlie/hermes/writers").get("running") or 0)

    def record_dispatch(self, key, value):
        result = self.client.request("POST", "/charlie/hermes/dispatch", {**value, "idempotency_key": key})
        return result.get("dispatch") or result

    def record_progress(self, mission_id, value):
        result = self.client.request("POST", f"/charlie/hermes/missions/{mission_id}/progress", value)
        return result.get("dispatch") or result

    def prepare_dispatch_authorization(self, mission_id):
        result = self.client.request("POST", f"/charlie/hermes/missions/{urllib.parse.quote(str(mission_id), safe='')}/dispatch-authorization", {})
        return result.get("authorization") or result

    def bind_actual_branch(self, mission_id, *, generation, cursor_agent_id, cursor_run_id, branches):
        return self.client.request("POST", f"/charlie/hermes/missions/{urllib.parse.quote(str(mission_id), safe='')}/actual-branch", {
            "generation": generation, "cursor_agent_id": cursor_agent_id,
            "cursor_run_id": cursor_run_id,
            "repository": "Crewless9086/amadeus-pig-tracking-system", "branches": branches,
        })

    def refresh_dispatch_base(self, mission_id, *, generation, cursor_agent_id, old_base_sha):
        return self.client.request("POST", f"/charlie/hermes/missions/{urllib.parse.quote(str(mission_id), safe='')}/refresh-dispatch-base", {
            "generation": generation, "cursor_agent_id": cursor_agent_id,
            "old_base_sha": old_base_sha,
        })

    def record_followup(self, mission_id, agent_id, run_id, failed_attempts):
        return self.record_progress(mission_id, {"event": "cursor_followup", "cursor_agent_id": agent_id,
                                                "cursor_run_id": run_id, "failed_attempts": int(failed_attempts)})

    def request_admission(self, mission_id, expected_head_sha, pr_number=0):
        return self.client.request("POST", f"/charlie/hermes/missions/{urllib.parse.quote(str(mission_id), safe='')}/admission",
                                   {"expected_head_sha": str(expected_head_sha or ""), "pr_number": int(pr_number)})

    def prepare_successor(self, mission_id, payload):
        return self.client.request("POST", f"/charlie/hermes/missions/{urllib.parse.quote(str(mission_id), safe='')}/execution-succession", payload)

    def prepare_native_execution(self, mission_id, worktree_digest, starting_main_sha):
        result = self.client.request(
            "POST", f"/charlie/hermes/missions/{urllib.parse.quote(str(mission_id), safe='')}/native-execution",
            {"worktree_digest": str(worktree_digest),
             "starting_main_sha": str(starting_main_sha)},
        )
        return result.get("authorization") or result

    def record_native_progress(self, mission_id, value):
        result = self.client.request(
            "POST", f"/charlie/hermes/missions/{urllib.parse.quote(str(mission_id), safe='')}/native-execution/progress",
            value,
        )
        return result.get("authorization") or result

    def resumable_native_executions(self):
        result = self.client.request("GET", "/charlie/hermes/native-executions/resumable")
        return list(result.get("executions") or [])

    def bind_native_candidate(self, mission_id, binding):
        return self.client.request(
            "POST", f"/charlie/build-relay/missions/{urllib.parse.quote(str(mission_id), safe='')}/external-candidate",
            binding,
        )


class SlackBot:
    """One-way bot posting surface; it cannot impersonate the owner."""

    def __init__(self, bot_token, *, client=None):
        if not str(bot_token or "").startswith("xoxb-"):
            raise HermesBridgeError("slack_bot_token_required")
        self.client = client or JsonHttpClient("https://slack.com/api", str(bot_token))

    def post(self, channel, text, *, thread_ts=""):
        payload = {"channel": str(channel or ""), "text": str(text or "").strip()}
        if thread_ts:
            payload["thread_ts"] = str(thread_ts)
        if not payload["channel"] or not payload["text"]:
            raise HermesBridgeError("slack_post_incomplete")
        result = self.client.request("POST", "/chat.postMessage", payload)
        if result.get("ok") is not True:
            raise HermesBridgeError("slack_post_failed")
        return result


class GitHubReadMonitor:
    """Unauthenticated/read-token optional GitHub observation; never writes."""

    def __init__(self, repository, *, client=None):
        self.repository = str(repository or "").strip()
        self.client = client or JsonHttpClient("https://api.github.com")

    def find_pull(self, branch):
        owner = self.repository.split("/", 1)[0]
        result = self.client.request("GET", f"/repos/{self.repository}/pulls",
                                     query={"state": "open", "head": f"{owner}:{branch}"})
        items = list(result.get("items") or [])
        if len(items) > 1:
            raise HermesBridgeError("duplicate_open_pull_requests")
        return int(items[0].get("number") or 0) if items else 0

    def pull_state(self, number, *, now=None, stall_seconds=1800):
        pull = self.client.request("GET", f"/repos/{self.repository}/pulls/{int(number)}")
        head = str((pull.get("head") or {}).get("sha") or "")
        checks = self.client.request("GET", f"/repos/{self.repository}/commits/{head}/check-runs")
        reviews = self.client.request("GET", f"/repos/{self.repository}/pulls/{int(number)}/reviews")
        runs = list(checks.get("check_runs") or [])
        required = {run.get("name"): run.get("conclusion") for run in runs}
        trusted_admission = any(
            run.get("name") == "mission-admission" and run.get("conclusion") == "success"
            and int((run.get("app") or {}).get("id") or 0) == 4742997 for run in runs)
        review_items = list(reviews.get("items") or [])
        current_reviews = [item for item in review_items if isinstance(item, dict)
                           and str(item.get("commit_id") or head) == head]
        pull_author = str((pull.get("user") or {}).get("login") or "").strip().lower()
        verdicts = []
        role_verdicts = {}
        for item in current_reviews:
            body = str(item.get("body") or "").strip()
            state = str(item.get("state") or "").strip().upper()
            reviewer = str((item.get("user") or {}).get("login") or "").strip().lower()
            association = str(item.get("author_association") or "").strip().upper()
            role = ("SECURITY" if body.upper().startswith(("SECURITY:", "[SECURITY]"))
                    else "FUNCTIONAL" if body.upper().startswith(("FUNCTIONAL:", "[FUNCTIONAL]"))
                    else "")
            # Only GitHub's authenticated review state is authoritative.  A
            # COMMENTED review body is untrusted text and can never satisfy the
            # independent review gate.
            trusted_reviewer = bool(
                reviewer and reviewer != pull_author
                and association in {"COLLABORATOR", "MEMBER", "OWNER"})
            if state == "CHANGES_REQUESTED" and trusted_reviewer:
                verdicts.append(("SEND_BACK", body))
                if role and reviewer:
                    role_verdicts[role] = {"verdict": "SEND_BACK", "reviewer": reviewer, "findings": body}
            elif state == "APPROVED" and trusted_reviewer:
                if role and reviewer:
                    role_verdicts[role] = {"verdict": "APPROVE", "reviewer": reviewer, "findings": body}
        observed_at = float(time.time() if now is None else now)
        stalled_checks = [str(run.get("name") or "") for run in runs
                          if run.get("status") in {"queued", "in_progress"}
                          and (started := _parse_epoch(run.get("started_at")))
                          and observed_at - started > stall_seconds]
        required_names = {"mission-admission", "charlie-core",
            "Unit tests with disposable Postgres audit rails",
            "Closed Render migration rail with disposable Postgres",
            "Playwright real-browser behavior gate"}
        review, findings = next(iter(reversed(verdicts)), ("WAIT", ""))
        security = role_verdicts.get("SECURITY") or {}
        functional = role_verdicts.get("FUNCTIONAL") or {}
        if (security.get("verdict") == functional.get("verdict") == "APPROVE"
                and security.get("reviewer") != functional.get("reviewer")):
            review, findings = "APPROVE", "independent security and functional reviews approved"
        return {"pr_number": int(number), "head_sha": head,
                "branch": str((pull.get("head") or {}).get("ref") or ""),
                "checks": required, "stalled_checks": stalled_checks,
                "ci_stalled": bool(stalled_checks),
                "all_required_checks_pass": (trusted_admission and all(
                    required.get(name) == "success" for name in required_names - {"mission-admission"})),
                "mission_admission_app_id": 4742997 if trusted_admission else 0,
                "independent_review": review,
                "independent_review_findings": findings[:4000],
                "security_review": security, "functional_review": functional,
                "approved_head_sha": head if review == "APPROVE" else ""}


class PluginTools(dict):
    """Hermes tool mapping with its non-model-visible supervisor runtime."""

    def __init__(self, supervisor):
        super().__init__(supervisor.tools())
        self.supervisor = supervisor


class HermesSupervisor:
    """Low-cost deterministic supervisor over canonical CHARLIE APIs."""

    MAX_RUNNING_WRITERS = 1
    MAX_FAILED_ATTEMPTS = 2
    AUTOMATIC_DECOMPOSITION = False

    def __init__(self, canonical, cursor, *, owner_slack_user_id, slack_signing_secret="",
                 slack_command_channel_id="", slack_build_channel_id="",
                 slack_approval_channel_id="", slack_bot=None,
                 github=None, issuer=None, clock=time.time, native_llm=None,
                 native_repository_root="", native_worktree_base="",
                 github_packager_token=""):
        self.canonical = canonical
        self.cursor = cursor
        self.owner_slack_user_id = str(owner_slack_user_id or "").strip()
        self.slack_signing_secret = str(slack_signing_secret or "")
        self.slack_command_channel_id = str(slack_command_channel_id or "")
        self.slack_build_channel_id = str(slack_build_channel_id or "")
        self.slack_approval_channel_id = str(slack_approval_channel_id or "")
        self.slack_bot = slack_bot
        self.github = github
        self.issuer = issuer
        self.clock = clock
        self.native_llm = native_llm
        self.native_repository_root = str(native_repository_root or "")
        self.native_worktree_base = str(native_worktree_base or "")
        self.github_packager_token = str(github_packager_token or "")
        if not self.owner_slack_user_id:
            raise HermesBridgeError("slack_owner_id_required")
        if not all((self.slack_command_channel_id, self.slack_build_channel_id,
                    self.slack_approval_channel_id)):
            raise HermesBridgeError("slack_channel_ids_required")

    def reconcile_slack_event(self, event):
        row = dict(event or {})
        if str(row.get("user") or "") != self.owner_slack_user_id:
            raise HermesBridgeError("slack_owner_not_authorized")
        event_id = str(row.get("event_id") or "").strip()
        channel = str(row.get("channel") or "").strip()
        thread = str(row.get("thread_ts") or row.get("ts") or "").strip()
        text = str(row.get("text") or "").strip()
        if not all((event_id, channel, thread, text)):
            raise HermesBridgeError("slack_event_incomplete")
        if channel != self.slack_command_channel_id:
            raise HermesBridgeError("slack_channel_not_authorized")
        result = self.canonical.reconcile_mission({
            "source": "slack", "source_event_id": event_id, "owner_user_id": self.owner_slack_user_id,
            "channel_id": channel, "thread_ts": thread, "instruction": text,
        }, idempotency_key=f"slack:{event_id}")
        if self.slack_bot:
            self.slack_bot.post(channel, f"Acknowledged as canonical mission {result.get('mission_id')}.", thread_ts=thread)
        return result

    def handle_slack_request(self, raw_body, headers, *, now=None):
        headers = {str(key).lower(): value for key, value in dict(headers or {}).items()}
        verify_slack_request(self.slack_signing_secret,
                             headers.get("x-slack-request-timestamp"), raw_body,
                             headers.get("x-slack-signature"), now=now)
        try:
            envelope = json.loads(raw_body.decode() if isinstance(raw_body, bytes) else str(raw_body))
        except (TypeError, ValueError) as exc:
            raise HermesBridgeError("slack_event_invalid") from exc
        if envelope.get("type") == "url_verification":
            return {"challenge": str(envelope.get("challenge") or "")}
        event = dict(envelope.get("event") or {})
        event["event_id"] = str(envelope.get("event_id") or "")
        return self.reconcile_slack_event(event)

    def dispatch_builder(self, mission):
        mission_id = str(dict(mission or {}).get("mission_id") or "").strip()
        loaded = self.canonical.get_mission(mission_id)
        metadata = dict((loaded.get("mission") or {}).get("metadata") or {})
        retired = dict(metadata.get("cursor_provider_retirement") or {})
        state = dict(metadata.get("external_supervisor_state") or {})
        if (
            retired.get("provider_status") == "UNSUITABLE_FOR_CURRENT_BUILDER_CONTRACT"
            or state.get("event") == "cursor_provider_retired"
            or self.cursor is None
        ):
            return self.dispatch_native({"mission_id": mission_id})
        return self.dispatch_cursor({"mission_id": mission_id})

    def dispatch_native(self, mission):
        mission_id = str(dict(mission or {}).get("mission_id") or "").strip()
        if not mission_id or not self.native_repository_root or not self.native_worktree_base:
            raise HermesBridgeError("native_execution_not_configured")
        loaded = self.canonical.get_mission(mission_id)
        row = dict(loaded.get("mission") or {})
        metadata = dict(row.get("metadata") or {})
        dispatch = dict(metadata.get("dispatch_authorization") or {})
        generation = str(dispatch.get("generation") or "").strip()
        if self.canonical.running_writer_count() != 0:
            raise HermesBridgeError("native_writer_claim_not_released")
        native_id, branch = content_identity(mission_id, generation, 1)
        worktree = Path(self.native_worktree_base) / mission_id / generation / "native-1"
        worktree_digest = hashlib.sha256(str(worktree.resolve(strict=False)).encode()).hexdigest()
        starting_main_sha = run_argv(
            ["git", "rev-parse", "HEAD"], cwd=self.native_repository_root,
        ).stdout.strip().lower()
        authorization = self.canonical.prepare_native_execution(
            mission_id, worktree_digest, starting_main_sha)
        if authorization.get("native_execution_id") != native_id or authorization.get("branch") != branch:
            raise HermesBridgeError("native_execution_identity_conflict")
        if int(authorization.get("pr_number") or 0) and authorization.get("head_sha"):
            return self.poll_native({"mission_id": mission_id})
        if not execution_lock().acquire(blocking=False):
            raise HermesBridgeError("native_writer_capacity_reached")
        claim_id = "HNC-" + uuid.uuid4().hex
        claim_expiry = datetime.now(timezone.utc) + timedelta(minutes=10)
        claimed = self.canonical.record_native_progress(mission_id, {
            "native_execution_id": native_id, "execution_status": "RUNNING",
            "worker_claim_id": claim_id, "claim_expires_at": claim_expiry.isoformat(),
            "runner_stage": "planner", "event": "native_writer_claimed",
        })
        if isinstance(claimed, dict) and claimed.get("success") is False:
            execution_lock().release()
            raise HermesBridgeError(str(claimed.get("status") or "native_writer_claim_failed"))
        try:
            def heartbeat():
                renewed = self.canonical.record_native_progress(mission_id, {
                    "native_execution_id": native_id, "execution_status": "RUNNING",
                    "worker_claim_id": claim_id,
                    "claim_expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
                    "event": "native_writer_claimed",
                })
                if isinstance(renewed, dict) and renewed.get("success") is False:
                    raise HermesBridgeError(str(renewed.get("status") or "native_writer_claim_failed"))
            engine = NativeExecutionEngine(
                HermesStructuredPatchWorker(self.native_llm), self.native_repository_root,
                worktree, authorization, heartbeat=heartbeat,
            )
            root = engine.worktree.ensure()
            head_before = run_argv(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()
            dirty_before = bool(run_argv(["git", "status", "--porcelain"], cwd=root).stdout.strip())
            if dirty_before or head_before != authorization["starting_main_sha"]:
                built = {"state": "PATCH_READY", "changed_files": list(authorization["allowed_files"]),
                         "worker_identity": authorization.get("builder_identity"),
                         "worker_agent_id": authorization.get("builder_agent_id")}
            else:
                built = engine.build_patch(
                    row.get("raw_text") or row.get("title"),
                    governance_context=build_hermes_native_execution_context(row),
                )
                if built.get("state") == "BLOCKED":
                    return self.canonical.record_native_progress(mission_id, {
                        "native_execution_id": native_id, "execution_status": "BLOCKED",
                        "failure_reason": built.get("reason"), "worker_claim_id": claim_id,
                        "event": "native_model_blocked",
                    })
            if not built.get("worker_agent_id"):
                raise HermesBridgeError("native_builder_runtime_identity_missing")
            progress = self.canonical.record_native_progress(mission_id, {
                "native_execution_id": native_id, "execution_status": "PATCH_APPLIED",
                "changed_files": built.get("changed_files"), "worker_claim_id": claim_id,
                "builder_identity": built.get("worker_identity"),
                "builder_agent_id": built.get("worker_agent_id"),
                "runner_stage": "builder", "stage_artifact": {
                    "kind": "validated_structured_patch", "changed_files": built.get("changed_files")},
                "event": "native_patch_applied",
            })
            evidence = engine.verify()
            heartbeat()
            progress = self.canonical.record_native_progress(mission_id, {
                "native_execution_id": native_id, "execution_status": "VERIFIED",
                "changed_files": built.get("changed_files"), "worker_claim_id": claim_id,
                "runner_stage": "tester", "stage_artifact": {
                    "kind": "bounded_verification", "commands": evidence},
                "event": "native_verification_completed",
            })
            if not self.github_packager_token:
                return {**progress, "status": "PACKAGER_CREDENTIAL_REQUIRED", "verification": evidence}
            packaged = NativePackager(
                worktree, authorization, self.github_packager_token,
            ).package(row.get("title") or "CHARLIE native mission", "Native structured patch; no merge or deployment authority.")
            heartbeat()
            self._bind_native_candidate(mission_id, authorization, packaged)
            reviews = self._run_native_reviews(
                authorization, packaged, evidence, mission=row,
                builder_identity=built.get("worker_identity"),
                builder_agent_id=built.get("worker_agent_id"),
            )
            return self.canonical.record_native_progress(mission_id, {
                "native_execution_id": native_id, "execution_status": "DRAFT_PR_OPEN",
                "commit_sha": packaged["commit_sha"], "head_sha": packaged["commit_sha"],
                "pr_number": packaged["pr_number"], "changed_files": packaged["changed_files"],
                "candidate_diff_sha256": packaged["candidate_diff_sha256"],
                "worker_claim_id": claim_id, "runner_stage": "reviewer",
                "review_request_roles": ["SECURITY", "FUNCTIONAL"],
                "review_security": reviews["SECURITY"],
                "review_functional": reviews["FUNCTIONAL"],
                "review_challenge": reviews.get("CHALLENGE"),
                "stage_artifact": {"kind": "draft_pr_candidate", "head_sha": packaged["commit_sha"]},
                "event": "native_draft_pr_opened",
            })
        except NativeExecutionError as exc:
            raise HermesBridgeError(str(exc)) from exc
        finally:
            execution_lock().release()
            try:
                self.canonical.record_native_progress(mission_id, {
                    "native_execution_id": native_id,
                    "release_claim_id": claim_id, "event": "native_writer_released",
                })
            except Exception:
                pass

    def poll_native(self, mission):
        mission_id = str(dict(mission or {}).get("mission_id") or "").strip()
        loaded = self.canonical.get_mission(mission_id)
        native = dict(((loaded.get("mission") or {}).get("metadata") or {}).get("hermes_native_execution") or {})
        pr_number = int(native.get("pr_number") or 0)
        if not pr_number or not self.github:
            return {"mission_id": mission_id, **native}
        observed = self.github.pull_state(pr_number, now=self.clock())
        if native.get("execution_status") == "CORRECTION_PATCH_VERIFIED":
            prior_send_back = (native.get("review_verdict") == "SEND_BACK"
                or any(dict(native.get(key) or {}).get("verdict") == "SEND_BACK"
                       for key in ("review_security", "review_functional", "review_challenge")))
            if not prior_send_back:
                raise HermesBridgeError("native_correction_authority_missing")
            recovery_worktree = (Path(self.native_worktree_base) / mission_id
                                 / native.get("generation", "") / "native-1")
            if observed.get("head_sha") == native.get("head_sha"):
                if not self.github_packager_token:
                    raise HermesBridgeError("github_packager_token_required")
                recovery_claim = "HNC-" + uuid.uuid4().hex
                claimed = self.canonical.record_native_progress(mission_id, {
                    "native_execution_id": native.get("native_execution_id"),
                    "execution_status": "CORRECTION_PATCH_VERIFIED",
                    "worker_claim_id": recovery_claim,
                    "claim_expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
                    "event": "native_writer_claimed",
                })
                if isinstance(claimed, dict) and claimed.get("success") is False:
                    raise HermesBridgeError(str(claimed.get("status") or "native_writer_claim_failed"))
                if not execution_lock().acquire(blocking=False):
                    self.canonical.record_native_progress(mission_id, {
                        "native_execution_id": native.get("native_execution_id"),
                        "release_claim_id": recovery_claim, "event": "native_writer_released"})
                    raise HermesBridgeError("native_writer_capacity_reached")
                try:
                    packaged = NativePackager(
                        recovery_worktree, native, self.github_packager_token).package(
                        "fix(charlie): address independent native review",
                        "Recovered same native execution correction; no merge or deployment authority.")
                finally:
                    execution_lock().release()
                    self.canonical.record_native_progress(mission_id, {
                        "native_execution_id": native.get("native_execution_id"),
                        "release_claim_id": recovery_claim, "event": "native_writer_released"})
                self.canonical.record_native_progress(mission_id, {
                    "native_execution_id": native.get("native_execution_id"),
                    "execution_status": "CORRECTION_PACKAGED",
                    "commit_sha": packaged["commit_sha"], "head_sha": packaged["commit_sha"],
                    "pr_number": packaged["pr_number"], "changed_files": packaged["changed_files"],
                    "candidate_diff_sha256": packaged["candidate_diff_sha256"],
                    "builder_identity": native.get("builder_identity"),
                    "builder_agent_id": native.get("builder_agent_id"),
                    "stage_artifact": native.get("stage_artifact"),
                    "admission_requested_head": "", "event": "native_correction_packaged_recovered",
                })
                observed = self.github.pull_state(pr_number, now=self.clock())
                loaded = self.canonical.get_mission(mission_id)
                native = dict(((loaded.get("mission") or {}).get("metadata") or {}).get("hermes_native_execution") or {})
            else:
                packaged = None
        if (native.get("execution_status") == "CORRECTION_PATCH_VERIFIED"
                and observed.get("head_sha") != native.get("head_sha")):
            recovery_worktree = (Path(self.native_worktree_base) / mission_id
                                 / native.get("generation", "") / "native-1")
            local_head = run_argv(["git", "rev-parse", "HEAD"], cwd=recovery_worktree)
            names = run_argv(["git", "diff", "--name-only", native.get("starting_main_sha"),
                              observed.get("head_sha"), "--"], cwd=recovery_worktree)
            diff = run_argv(["git", "diff", "--no-ext-diff", "--no-textconv", "--binary",
                             "--full-index", native.get("starting_main_sha"),
                             observed.get("head_sha"), "--"], cwd=recovery_worktree)
            changed = sorted(item for item in names.stdout.splitlines() if item)
            if (local_head.returncode or local_head.stdout.strip() != observed.get("head_sha")
                    or names.returncode or diff.returncode or not changed
                    or not set(changed).issubset(set(native.get("allowed_files") or []))):
                raise HermesBridgeError("native_correction_recovery_conflict")
            self.canonical.record_native_progress(mission_id, {
                "native_execution_id": native.get("native_execution_id"),
                "execution_status": "CORRECTION_PACKAGED", "head_sha": observed.get("head_sha"),
                "commit_sha": observed.get("head_sha"), "pr_number": pr_number,
                "changed_files": changed,
                "candidate_diff_sha256": canonical_candidate_diff(changed, diff.stdout),
                "builder_identity": native.get("builder_identity"),
                "builder_agent_id": native.get("builder_agent_id"),
                "stage_artifact": native.get("stage_artifact"),
                "admission_requested_head": "", "event": "native_correction_packaged_recovered",
            })
            loaded = self.canonical.get_mission(mission_id)
            native = dict(((loaded.get("mission") or {}).get("metadata") or {}).get("hermes_native_execution") or {})
        if (native.get("execution_status") == "CORRECTION_PACKAGED"
                and native.get("head_sha") == observed.get("head_sha")):
            packaged = {"pr_number": pr_number, "commit_sha": native.get("head_sha"),
                "candidate_diff_sha256": native.get("candidate_diff_sha256"),
                "changed_files": list(native.get("changed_files") or [])}
            self._bind_native_candidate(mission_id, native, packaged)
            recovered_reviews = self._run_native_reviews(
                native, packaged, list((native.get("stage_artifact") or {}).get("commands") or []),
                mission=loaded.get("mission") or {},
                builder_identity=native.get("builder_identity"),
                builder_agent_id=native.get("builder_agent_id"), require_challenge=False)
            self.canonical.record_native_progress(mission_id, {
                "native_execution_id": native.get("native_execution_id"),
                "execution_status": "SEND_BACK_CORRECTED", "head_sha": native.get("head_sha"),
                "pr_number": pr_number, "changed_files": native.get("changed_files"),
                "candidate_diff_sha256": native.get("candidate_diff_sha256"),
                "review_security": recovered_reviews["SECURITY"],
                "review_functional": recovered_reviews["FUNCTIONAL"],
                "admission_requested_head": "", "event": "native_send_back_corrected",
            })
            loaded = self.canonical.get_mission(mission_id)
            native = dict(((loaded.get("mission") or {}).get("metadata") or {}).get("hermes_native_execution") or {})
        security = dict(native.get("review_security") or {})
        functional = dict(native.get("review_functional") or {})
        challenge = dict(native.get("review_challenge") or {})
        expected_binding = {
            "pr_number": pr_number,
            "base_sha": str(native.get("starting_main_sha") or ""),
            "head_sha": str(observed.get("head_sha") or ""),
            "candidate_diff_sha256": str(native.get("candidate_diff_sha256") or ""),
            "changed_files": list(native.get("changed_files") or []),
        }
        active_reviews = [security, functional] + ([challenge] if challenge else [])
        reviews_bound = all(
            dict(review.get("candidate_binding") or {}) == expected_binding
            for review in active_reviews
        )
        raw_agent_ids = [review.get("reviewer_agent_id") for review in active_reviews]
        reviewers_independent = bool(all(raw_agent_ids)
            and len(set(raw_agent_ids)) == len(raw_agent_ids)
            and native.get("builder_agent_id") not in set(raw_agent_ids))
        if not reviews_bound or not reviewers_independent:
            security = functional = challenge = {}
        if (observed.get("independent_review") != "SEND_BACK"
                and "SEND_BACK" in {security.get("verdict"), functional.get("verdict"),
                                    challenge.get("verdict")}):
            observed["independent_review"] = "SEND_BACK"
            observed["independent_review_findings"] = "\n".join(
                item for review in active_reviews for item in review.get("findings") or [])[:4000]
        elif (observed.get("independent_review") == "WAIT"
                and security.get("verdict") == functional.get("verdict") == "APPROVE"):
            if int(native.get("correction_rounds") or 0) < 1:
                observed["independent_review"] = "WAIT"
                observed["independent_review_findings"] = "commissioning_genuine_send_back_required"
            else:
                observed["independent_review"] = "APPROVE"
                observed["security_review"], observed["functional_review"] = security, functional
        admission_requested_head = str(native.get("admission_requested_head") or "")
        if admission_requested_head != observed.get("head_sha"):
            self.issue_admission(mission_id, observed.get("head_sha"), pr_number)
            admission_requested_head = observed.get("head_sha")
        recorded = self.canonical.record_native_progress(mission_id, {
            "native_execution_id": native.get("native_execution_id"),
            "execution_status": "SUPERVISING",
            "pr_number": pr_number,
            "head_sha": observed.get("head_sha"),
            "checks": observed.get("checks"),
            "review_verdict": observed.get("independent_review"),
            "review_security": observed.get("security_review"),
            "review_functional": observed.get("functional_review"),
            "admission_requested_head": admission_requested_head,
            "event": "native_candidate_supervised",
        })
        if isinstance(recorded, dict) and recorded.get("success") is False:
            raise HermesBridgeError("native_progress_record_failed")
        return {"mission_id": mission_id, **native, **observed}

    def dispatch_cursor(self, mission):
        row = dict(mission or {})
        mission_id = str(row.get("mission_id") or "").strip()
        if not mission_id:
            raise HermesBridgeError("canonical_mission_required")
        loaded = self.canonical.get_mission(mission_id)
        canonical = dict(loaded.get("mission") or {})
        metadata = dict(canonical.get("metadata") or {})
        current = dict(metadata.get("mission_admission") or {})
        contract = dict(metadata.get("mission_admission_contract") or {})
        dispatch_authorization = dict(metadata.get("dispatch_authorization") or {})
        if current.get("status") == "valid" and current.get("mission_id") == mission_id:
            authority_id = current.get("receipt_id")
        elif (dispatch_authorization.get("status") == "valid"
                and dispatch_authorization.get("mission_id") == mission_id):
            current = dispatch_authorization
            contract = dispatch_authorization
            authority_id = dispatch_authorization.get("authorization_id")
        else:
            raise HermesBridgeError("current_dispatch_authorization_required")
        if canonical.get("mission_id") != mission_id or current.get("generation") != contract.get("generation"):
            raise HermesBridgeError("current_dispatch_authorization_required")
        admission = CursorAdmission.from_mapping({
            "mission_id": mission_id, "generation": current.get("generation"),
            "receipt_id": authority_id,
            "repository": contract.get("repository") or "Crewless9086/amadeus-pig-tracking-system",
            "base_sha": contract.get("base_sha"), "allowed_files": contract.get("allowed_files"),
            "allowed_effects": contract.get("allowed_effects"),
            "owner_instruction_digest": current.get("latest_correction_digest") or contract.get("owner_instruction_digest"),
            "acceptance_requirements": contract.get("operational_acceptance") or [
                "Open one draft PR; exact-candidate admission and review follow before merge."],
            "branch": contract.get("branch"),
        })
        succession = dict(metadata.get("execution_succession") or {})
        attempt = int(succession.get("active_attempt") or 1)
        if attempt not in (1, 2, 3, 4, 5):
            raise HermesBridgeError("cursor_execution_attempt_invalid")
        key = mission_idempotency_key(admission.mission_id, admission.generation)
        if attempt > 1:
            key += f":attempt-{attempt}"
        existing = self.canonical.get_dispatch(key)
        expected_agent_id = self.cursor.deterministic_agent_id(key)
        if existing:
            if (existing.get("mission_id") != admission.mission_id
                    or existing.get("generation") != admission.generation
                    or int(existing.get("execution_attempt") or 0) != attempt
                    or existing.get("cursor_agent_id") != expected_agent_id):
                raise HermesBridgeError("cursor_dispatch_identity_conflict")
            if existing.get("cursor_run_id"):
                return {"status": "existing_dispatch", **existing}
        if self.canonical.running_writer_count() >= self.MAX_RUNNING_WRITERS:
            raise HermesBridgeError("writer_capacity_reached")
        if not existing:
            existing = self.canonical.record_dispatch(key, {
                "mission_id": admission.mission_id,
                "generation": admission.generation,
                "execution_attempt": attempt,
                "cursor_agent_id": expected_agent_id,
                "agent_state": "RESERVED",
            })
            if existing.get("cursor_agent_id") != expected_agent_id:
                raise HermesBridgeError("cursor_dispatch_reservation_failed")
        response = self.cursor.create_agent(
            admission, self._cursor_bootstrap_prompt(admission),
            execution_attempt=attempt)
        agent = dict(response.get("agent") or {})
        run = dict(response.get("run") or {})
        if not agent.get("id") or not run.get("id"):
            raise HermesBridgeError("cursor_dispatch_unverified")
        if agent["id"] != expected_agent_id:
            raise HermesBridgeError("cursor_dispatch_identity_conflict")
        return self.canonical.record_dispatch(key, {
            "mission_id": admission.mission_id,
            "generation": admission.generation,
            "execution_attempt": attempt,
            "cursor_agent_id": agent["id"], "cursor_run_id": run["id"], "agent_state": "ACTIVE",
        })

    def poll(self, mission):
        row = dict(mission or {})
        loaded = self.canonical.get_mission(row.get("mission_id"))
        metadata = dict((loaded.get("mission") or {}).get("metadata") or {})
        if metadata.get("hermes_native_execution"):
            return self.poll_native(row)
        dispatch = dict(row.get("dispatch") or {})
        agent = self.cursor.get_agent(dispatch.get("cursor_agent_id"))
        run = self.cursor.get_latest_run(agent.get("id"))
        state = str(agent.get("status") or "")
        run_state = str(run.get("status") or "")
        if state not in {"ACTIVE", "IDLE", "ARCHIVED"}:
            raise HermesBridgeError("cursor_state_invalid")
        updated_at = _parse_epoch(run.get("updatedAt"))
        stalled = state == "ACTIVE" and updated_at and self.clock() - updated_at > 1800
        git = dict(run.get("git") or {})
        branches = list(git.get("branches") or [])
        loaded = self.canonical.get_mission(row.get("mission_id"))
        metadata = dict((loaded.get("mission") or {}).get("metadata") or {})
        authorization = dict(metadata.get("dispatch_authorization") or {})
        canonical_state = dict(metadata.get("external_supervisor_state") or {})
        if authorization.get("status") == "valid":
            self.canonical.refresh_dispatch_base(
                row.get("mission_id"), generation=authorization.get("generation"),
                cursor_agent_id=agent.get("id"), old_base_sha=authorization.get("base_sha"))
        branch_binding = {}
        if branches:
            if len(branches) != 1:
                raise HermesBridgeError("cursor_branch_count_invalid")
            branch_binding = self.canonical.bind_actual_branch(
                row.get("mission_id"), generation=authorization.get("generation"),
                cursor_agent_id=agent.get("id"), cursor_run_id=run.get("id"), branches=branches)
            if isinstance(branch_binding, dict) and branch_binding.get("success") is False:
                raise HermesBridgeError("cursor_branch_binding_failed")
        if (len(branches) == 1 and state == "IDLE"
                and isinstance(branch_binding, dict) and branch_binding.get("success") is True
                and not canonical_state.get("implementation_run_id")):
            admission = CursorAdmission.from_mapping({
                "mission_id": row.get("mission_id"), "generation": authorization.get("generation"),
                "receipt_id": authorization.get("authorization_id"),
                "repository": authorization.get("repository"), "base_sha": authorization.get("base_sha"),
                "allowed_files": authorization.get("allowed_files"),
                "allowed_effects": authorization.get("allowed_effects"),
                "owner_instruction_digest": authorization.get("owner_instruction_digest"),
                "acceptance_requirements": ["Open one draft PR; do not merge or deploy."],
                "branch": branch_binding.get("branch") or authorization.get("branch"),
            })
            followup = self.cursor.continue_agent(agent.get("id"), self._cursor_prompt(
                {"instruction": (loaded.get("mission") or {}).get("raw_text")}, admission))
            followup_run = dict(followup.get("run") or {})
            if not followup_run.get("id"):
                raise HermesBridgeError("cursor_implementation_followup_unverified")
            result = self.canonical.record_progress(row.get("mission_id"), {
                "event": "cursor_implementation_started", "cursor_agent_id": agent.get("id"),
                "cursor_run_id": followup_run["id"], "implementation_run_id": followup_run["id"],
                "branch": branch_binding.get("branch") or authorization.get("branch"),
            })
            return result
        result = {"agent_state": state, "run_state": run_state, "stalled": bool(stalled),
                  "cursor_agent_id": agent.get("id"), "cursor_run_id": run.get("id"),
                  "branches": branches}
        pr_number = int(dispatch.get("pr_number") or 0)
        if self.github and not pr_number and len(branches) == 1:
            branch = branches[0].get("name") or branches[0].get("branch") \
                if isinstance(branches[0], dict) else branches[0]
            pr_number = self.github.find_pull(branch)
        if self.github and pr_number:
            result.update(self.github.pull_state(pr_number, now=self.clock()))
            if dispatch.get("admission_requested_head") != result.get("head_sha"):
                self.issue_admission(row.get("mission_id"), result.get("head_sha"), pr_number)
                result["admission_requested_head"] = result.get("head_sha")
        if self.slack_bot and (result.get("stalled") or result.get("ci_stalled")):
            self.slack_bot.post(self.slack_build_channel_id,
                                f"Mission {row.get('mission_id')} requires attention: monitored work is stalled.")
        return self.canonical.record_progress(row.get("mission_id"), result)

    def supervise_once(self, mission, *, correction="Address the independent SEND_BACK review."):
        observed = self.poll(mission)
        if observed.get("independent_review") == "SEND_BACK":
            current = {**dict(mission or {}), "dispatch": {
                **dict((mission or {}).get("dispatch") or {}),
                "cursor_agent_id": observed.get("cursor_agent_id")}}
            return self.route_send_back(
                current, "SEND_BACK", observed.get("independent_review_findings") or correction)
        loaded = self.canonical.get_mission((mission or {}).get("mission_id"))
        loaded_row = dict(loaded.get("mission") or {})
        loaded_metadata = dict(loaded_row.get("metadata") or {})
        native = dict(loaded_metadata.get("hermes_native_execution") or {})
        dispatch = native or dict((mission or {}).get("dispatch") or {})
        if (observed.get("independent_review") == "APPROVE"
                and observed.get("all_required_checks_pass") is True
                and (not native or int(native.get("correction_rounds") or 0) >= 1)
                and dispatch.get("owner_notification_head") != observed.get("head_sha")):
            decision = self.prepare_owner_decision({**observed, "mission_id": (mission or {}).get("mission_id")})
            if self.slack_bot:
                state = dict(loaded_metadata.get("external_supervisor_state") or {})
                if state.get("slack_channel_id") and state.get("slack_thread_ts"):
                    self.slack_bot.post(state["slack_channel_id"],
                        f"Mission {(mission or {}).get('mission_id')} is ready for an exact owner decision on PR #{decision['pr_number']} head {decision['head_sha']}.",
                        thread_ts=state["slack_thread_ts"])
                self.slack_bot.post(self.slack_approval_channel_id,
                    f"OWNER DECISION REQUIRED: mission {decision['mission_id']} PR #{decision['pr_number']} exact head {decision['head_sha']}. No merge or deployment has occurred.")
            if native:
                return self.canonical.record_native_progress((mission or {}).get("mission_id"), {
                    "native_execution_id": native.get("native_execution_id"),
                    "execution_status": "OWNER_DECISION_REQUIRED",
                    "pr_number": observed.get("pr_number"), "head_sha": observed.get("head_sha"),
                    "checks": observed.get("checks"), "review_verdict": "APPROVE",
                    "owner_notification_head": observed.get("head_sha"), "event": "owner_decision_required"})
            return self.canonical.record_progress((mission or {}).get("mission_id"),
                {**observed, "owner_notification_head": observed.get("head_sha"), "event": "owner_decision_required"})
        return observed

    def issue_admission(self, mission_id, expected_head_sha, pr_number=0):
        if self.issuer:
            return self.issuer(mission_id=mission_id, expected_head_sha=expected_head_sha, pr_number=pr_number)
        return self.canonical.request_admission(mission_id, expected_head_sha, pr_number)

    def route_send_back(self, mission, verdict, correction):
        row = dict(mission or {})
        if str(verdict or "").upper() != "SEND_BACK":
            raise HermesBridgeError("send_back_verdict_required")
        loaded = self.canonical.get_mission(row.get("mission_id"))
        canonical_row = dict(loaded.get("mission") or {})
        native = dict((canonical_row.get("metadata") or {}).get("hermes_native_execution") or {})
        if native:
            return self._continue_native(canonical_row, native, correction)
        dispatch = dict(row.get("dispatch") or {})
        if int(dispatch.get("failed_attempts") or 0) >= self.MAX_FAILED_ATTEMPTS:
            raise HermesBridgeError("failed_attempt_limit_reached")
        response = self.cursor.continue_agent(dispatch.get("cursor_agent_id"), str(correction or "").strip())
        run = dict(response.get("run") or {})
        failed_attempts = int(dispatch.get("failed_attempts") or 0) + 1
        return self.canonical.record_followup(row.get("mission_id"), dispatch.get("cursor_agent_id"),
                                              run.get("id"), failed_attempts)

    def _continue_native(self, mission, authorization, correction):
        rounds = int(authorization.get("correction_rounds") or 0)
        if rounds >= 2:
            raise HermesBridgeError("native_correction_round_limit")
        worktree = (Path(self.native_worktree_base) / mission["mission_id"]
                    / authorization["generation"] / "native-1")
        if not execution_lock().acquire(blocking=False):
            raise HermesBridgeError("native_writer_capacity_reached")
        claim_id = "HNC-" + uuid.uuid4().hex
        claimed = self.canonical.record_native_progress(mission["mission_id"], {
            "native_execution_id": authorization["native_execution_id"],
            "execution_status": "CORRECTING", "worker_claim_id": claim_id,
            "claim_expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            "event": "native_writer_claimed",
        })
        if isinstance(claimed, dict) and claimed.get("success") is False:
            execution_lock().release()
            raise HermesBridgeError(str(claimed.get("status") or "native_writer_claim_failed"))
        try:
            def heartbeat():
                renewed = self.canonical.record_native_progress(mission["mission_id"], {
                    "native_execution_id": authorization["native_execution_id"],
                    "execution_status": "CORRECTING", "worker_claim_id": claim_id,
                    "claim_expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
                    "event": "native_writer_claimed",
                })
                if isinstance(renewed, dict) and renewed.get("success") is False:
                    raise HermesBridgeError(str(renewed.get("status") or "native_writer_claim_failed"))
            engine = NativeExecutionEngine(
                HermesStructuredPatchWorker(self.native_llm), self.native_repository_root,
                worktree, authorization, heartbeat=heartbeat,
            )
            built = engine.build_patch(
                "Apply only this independent SEND_BACK correction: " + str(correction or "").strip(),
                governance_context={**build_hermes_native_execution_context(mission),
                    "independent_review": {"verdict": "SEND_BACK", "findings": str(correction or "").strip()}},
            )
            if built.get("state") != "PATCH_READY":
                raise HermesBridgeError("native_correction_not_ready")
            evidence = engine.verify()
            heartbeat()
            self.canonical.record_native_progress(mission["mission_id"], {
                "native_execution_id": authorization["native_execution_id"],
                "execution_status": "CORRECTION_PATCH_VERIFIED",
                "builder_identity": built.get("worker_identity"),
                "builder_agent_id": built.get("worker_agent_id"),
                "stage_artifact": {"kind": "bounded_verification", "commands": evidence},
                "worker_claim_id": claim_id, "event": "native_correction_patch_verified",
            })
            if not self.github_packager_token:
                raise HermesBridgeError("github_packager_token_required")
            packaged = NativePackager(worktree, authorization, self.github_packager_token).package(
                "fix(charlie): address independent native review",
                "Same native execution and worktree correction; no merge or deployment authority.",
            )
            heartbeat()
            self.canonical.record_native_progress(mission["mission_id"], {
                "native_execution_id": authorization["native_execution_id"],
                "execution_status": "CORRECTION_PACKAGED",
                "commit_sha": packaged["commit_sha"], "head_sha": packaged["commit_sha"],
                "pr_number": packaged["pr_number"], "changed_files": packaged["changed_files"],
                "candidate_diff_sha256": packaged["candidate_diff_sha256"],
                "builder_identity": built.get("worker_identity"),
                "builder_agent_id": built.get("worker_agent_id"),
                "stage_artifact": {"kind": "bounded_verification", "commands": evidence},
                "worker_claim_id": claim_id, "admission_requested_head": "",
                "event": "native_correction_packaged",
            })
            self._bind_native_candidate(mission["mission_id"], authorization, packaged)
            reviews = self._run_native_reviews(
                authorization, packaged, evidence, mission=mission,
                builder_identity=built.get("worker_identity"),
                builder_agent_id=built.get("worker_agent_id"), require_challenge=False,
            )
            return self.canonical.record_native_progress(mission["mission_id"], {
                "native_execution_id": authorization["native_execution_id"],
                "execution_status": "SEND_BACK_CORRECTED",
                "commit_sha": packaged["commit_sha"], "head_sha": packaged["commit_sha"],
                "pr_number": packaged["pr_number"], "changed_files": packaged["changed_files"],
                "candidate_diff_sha256": packaged["candidate_diff_sha256"],
                "worker_claim_id": claim_id, "admission_requested_head": "",
                "review_security": reviews["SECURITY"],
                "review_functional": reviews["FUNCTIONAL"],
                "review_challenge": reviews.get("CHALLENGE"),
                "event": "native_send_back_corrected",
            })
        finally:
            execution_lock().release()
            try:
                self.canonical.record_native_progress(mission["mission_id"], {
                    "native_execution_id": authorization["native_execution_id"],
                    "release_claim_id": claim_id,
                    "event": "native_writer_released",
                })
            except Exception:
                pass

    def _bind_native_candidate(self, mission_id, authorization, packaged):
        binding = {
            "pr_number": int(packaged["pr_number"]), "branch_name": authorization["branch"],
            "base_sha": authorization["starting_main_sha"], "head_sha": packaged["commit_sha"],
            "candidate_diff_sha256": packaged["candidate_diff_sha256"],
            "changed_files": packaged["changed_files"], "generation": authorization["generation"],
            "allowed_files": list(authorization["allowed_files"]), "forbidden_files": ["*"],
            "allowed_effects": list(authorization["allowed_effects"]),
            "forbidden_effects": list(authorization["forbidden_effects"]),
            "required_tests": ["mission-admission", "charlie-core",
                "Unit tests with disposable Postgres audit rails",
                "Closed Render migration rail with disposable Postgres",
                "Playwright real-browser behavior gate"],
            "operational_acceptance": [
                "same native execution worktree branch and draft PR survive SEND_BACK",
                "owner notification is exact-head bound",
                "no merge or deployment occurs",
            ],
        }
        result = self.canonical.bind_native_candidate(mission_id, binding)
        if isinstance(result, dict) and result.get("success") is False:
            raise HermesBridgeError(str(result.get("status") or "native_candidate_binding_failed"))
        return result

    def _run_native_reviews(self, authorization, packaged, verification, *, mission,
                            builder_identity=None, builder_agent_id=None, require_challenge=True):
        worktree = (Path(self.native_worktree_base) / authorization["mission_id"]
                    / authorization["generation"] / "native-1")
        diff = run_argv([
            "git", "diff", "--no-ext-diff", "--no-textconv", "--binary", "--full-index",
            authorization["starting_main_sha"], packaged["commit_sha"], "--",
        ], cwd=worktree)
        if diff.returncode != 0:
            raise HermesBridgeError("native_review_diff_unavailable")
        packet = {
            "protocol": "charlie_hermes_native_independent_review_v1",
            "candidate": {"pr_number": int(packaged["pr_number"]),
                          "base_sha": authorization["starting_main_sha"],
                          "head_sha": packaged["commit_sha"],
                          "candidate_diff_sha256": packaged["candidate_diff_sha256"],
                          "changed_files": packaged["changed_files"],
                          "diff": diff.stdout},
            "scope": {"allowed_files": list(authorization["allowed_files"]),
                      "forbidden_effects": list(authorization["forbidden_effects"])},
            "mission": {
                "mission_id": authorization["mission_id"],
                "generation": authorization["generation"],
                "owner_instruction_digest": authorization["owner_instruction_digest"],
                "instruction": str((mission or {}).get("raw_text") or (mission or {}).get("title") or "")[:8000],
                "operational_acceptance": [
                    "same native execution worktree branch and draft PR survive SEND_BACK",
                    "fresh exact-head MAR and all five protected checks pass",
                    "owner notification is exact-head bound; no merge or deployment occurs",
                ],
                "correction_rounds": int(authorization.get("correction_rounds") or 0),
            },
            "verification": list(verification or []),
        }
        reviewer = HermesIndependentReviewer(self.native_llm)
        roles = ("SECURITY", "FUNCTIONAL", "CHALLENGE") if require_challenge else ("SECURITY", "FUNCTIONAL")
        reviews = {role: reviewer.review(role, packet) for role in roles if role != "CHALLENGE"}
        if require_challenge:
            for _ in range(2):
                challenge = reviewer.review("CHALLENGE", packet)
                if challenge.get("verdict") == "SEND_BACK":
                    reviews["CHALLENGE"] = challenge
                    break
            if "CHALLENGE" not in reviews:
                raise HermesBridgeError("native_commissioning_challenge_not_obtained")
        identities = {reviews[role]["reviewer_identity"] for role in reviews}
        agent_ids = {reviews[role]["reviewer_agent_id"] for role in reviews}
        if (len(identities) != len(roles) or len(agent_ids) != len(roles)
                or (builder_identity and builder_identity in identities)
                or (builder_agent_id and builder_agent_id in agent_ids)):
            raise HermesBridgeError("native_review_principal_not_independent")
        return reviews

    def prepare_owner_decision(self, mission):
        row = dict(mission or {})
        if (row.get("all_required_checks_pass") is not True
                or row.get("independent_review") != "APPROVE"
                or not row.get("head_sha")
                or row.get("approved_head_sha") != row.get("head_sha")):
            raise HermesBridgeError("owner_decision_not_ready")
        return {"mission_id": row.get("mission_id"), "pr_number": row.get("pr_number"),
                "head_sha": row.get("head_sha"), "channel": self.slack_approval_channel_id,
                "merge_or_deploy_performed": False}

    def tools(self):
        """Actual bounded Hermes handlers, not descriptive strings."""
        return {
            "charlie_reconcile_mission": self.reconcile_slack_event,
            "charlie_dispatch_cursor": self.dispatch_builder,
            "charlie_get_mission_status": lambda value: self.canonical.get_mission(value["mission_id"]),
            "charlie_get_cursor_status": self.poll,
            "charlie_issue_admission": lambda value: self.issue_admission(
                value["mission_id"], value["expected_head_sha"], value.get("pr_number", 0)),
            "charlie_supervise_once": self.supervise_once,
            "charlie_continue_cursor": lambda value: self.route_send_back(value["mission"], "SEND_BACK", value["correction"]),
            "charlie_prepare_owner_decision": self.prepare_owner_decision,
            "charlie_handle_slack_event": self.handle_slack_request,
        }

    @staticmethod
    def _cursor_bootstrap_prompt(admission):
        return "\n".join([
            "Prepare this CHARLIE workspace without modifying files, committing, pushing, or opening a PR.",
            "Perform read-only repository discovery only so Cursor reports its generated cursor/ branch.",
            f"Mission: {admission.mission_id}", f"Generation: {admission.generation}",
            "Wait for CHARLIE to bind the reported branch before implementation.",
        ])

    @staticmethod
    def _cursor_prompt(mission, admission):
        return "\n".join([
            "Implement this bounded pre-dispatch-authorized CHARLIE mission. Do not merge or deploy.",
            f"Mission: {admission.mission_id}", f"Generation: {admission.generation}",
            f"Authorization: {admission.receipt_id}", f"Owner instruction digest: {admission.owner_instruction_digest}",
            "Cursor may choose one generated cursor/ branch; CHARLIE will bind the signed runtime branch once.",
            "Allowed files: " + ", ".join(admission.allowed_files),
            "Allowed effects: " + ", ".join(admission.allowed_effects),
            "Acceptance: " + "; ".join(admission.acceptance_requirements),
            "Instruction: " + str(mission.get("instruction") or "").strip(),
        ])


def _cursor_id(value, prefix):
    value = str(value or "").strip()
    if not value.startswith(prefix) or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for char in value):
        raise HermesBridgeError("cursor_identity_invalid")
    return value


def _parse_epoch(value):
    if not value:
        return 0
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0


def build_plugin_from_environment(environ=None, *, opener=None, validate_live=False):
    """Construct the installable Hermes package exclusively from protected config."""
    env = dict(os.environ if environ is None else environ)
    required = (
        "CHARLIE_CANONICAL_API_URL", "CHARLIE_HERMES_GATEWAY_TOKEN",
        "SLACK_SIGNING_SECRET", "SLACK_BOT_TOKEN", "CHARLIE_SLACK_OWNER_USER_ID",
        "SLACK_APP_TOKEN",
        "CHARLIE_SLACK_CHARLIE_CHANNEL_ID", "CHARLIE_SLACK_BUILD_CHANNEL_ID",
        "CHARLIE_SLACK_APPROVALS_CHANNEL_ID",
    )
    values = {key: _protected_value(env, key) for key in required}
    cursor_key = _protected_value(env, "CURSOR_API_KEY", required=False)
    packager_token = _protected_value(env, "CHARLIE_GITHUB_PACKAGER_TOKEN", required=False)
    github_token = _protected_value(env, "CHARLIE_GITHUB_READ_TOKEN", required=False)
    if any(str(env.get(name) or "").strip() for name in (
            "CHARLIE_GITHUB_WRITE_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")):
        raise HermesBridgeError("github_write_credential_forbidden")
    canonical_client = JsonHttpClient(values["CHARLIE_CANONICAL_API_URL"], values["CHARLIE_HERMES_GATEWAY_TOKEN"], opener=opener)
    cursor_client = JsonHttpClient("https://api.cursor.com", cursor_key, opener=opener) if cursor_key else None
    slack_client = JsonHttpClient("https://slack.com/api", values["SLACK_BOT_TOKEN"], opener=opener)
    github_client = JsonHttpClient("https://api.github.com", github_token, opener=opener)
    supervisor = HermesSupervisor(
        CanonicalCharlieApi(values["CHARLIE_CANONICAL_API_URL"], values["CHARLIE_HERMES_GATEWAY_TOKEN"], client=canonical_client),
        CursorCloudV1(cursor_key, client=cursor_client) if cursor_key else None,
        owner_slack_user_id=values["CHARLIE_SLACK_OWNER_USER_ID"],
        slack_signing_secret=values["SLACK_SIGNING_SECRET"],
        slack_command_channel_id=values["CHARLIE_SLACK_CHARLIE_CHANNEL_ID"],
        slack_build_channel_id=values["CHARLIE_SLACK_BUILD_CHANNEL_ID"],
        slack_approval_channel_id=values["CHARLIE_SLACK_APPROVALS_CHANNEL_ID"],
        slack_bot=SlackBot(values["SLACK_BOT_TOKEN"], client=slack_client),
        github=GitHubReadMonitor("Crewless9086/amadeus-pig-tracking-system", client=github_client),
        native_repository_root=str(env.get("CHARLIE_REPOSITORY_PATH") or "/opt/data/amadeus-pig-tracking-system"),
        native_worktree_base=str(env.get("CHARLIE_NATIVE_WORKTREE_BASE") or "/opt/data/worktrees/charlie"),
        github_packager_token=packager_token,
    )
    if validate_live:
        if cursor_client and cursor_client.request("GET", "/v1/me").get("error"):
            raise HermesBridgeError("cursor_configuration_invalid")
        if canonical_client.request("GET", "/charlie/hermes/writers").get("success") is not True:
            raise HermesBridgeError("canonical_configuration_invalid")
        if slack_client.request("POST", "/auth.test", {}).get("ok") is not True:
            raise HermesBridgeError("slack_configuration_invalid")
        repository = github_client.request("GET", "/repos/Crewless9086/amadeus-pig-tracking-system")
        if repository.get("full_name") != "Crewless9086/amadeus-pig-tracking-system":
            raise HermesBridgeError("github_read_monitor_unavailable")
    return PluginTools(supervisor)
