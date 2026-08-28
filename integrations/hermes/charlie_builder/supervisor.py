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

    @classmethod
    def from_mapping(cls, value):
        row = dict(value or {})
        required = ("mission_id", "generation", "receipt_id", "repository", "base_sha", "owner_instruction_digest")
        if any(not str(row.get(key) or "").strip() for key in required):
            raise HermesBridgeError("valid_mission_admission_required")
        if not str(row["receipt_id"]).startswith("MAR-") or len(str(row["base_sha"])) != 40:
            raise HermesBridgeError("valid_mission_admission_required")
        files = tuple(sorted({str(item).strip() for item in row.get("allowed_files") or [] if str(item).strip()}))
        effects = tuple(sorted({str(item).strip() for item in row.get("allowed_effects") or [] if str(item).strip()}))
        acceptance = tuple(str(item).strip() for item in row.get("acceptance_requirements") or [] if str(item).strip())
        if not files or not effects or not acceptance:
            raise HermesBridgeError("valid_mission_admission_required")
        return cls(*(str(row[key]).strip() for key in required[:5]), files, effects,
                   str(row["owner_instruction_digest"]).strip(), acceptance)


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

    def create_agent(self, admission, prompt):
        admission = admission if isinstance(admission, CursorAdmission) else CursorAdmission.from_mapping(admission)
        key = mission_idempotency_key(admission.mission_id, admission.generation)
        payload = {
            "agentId": self.deterministic_agent_id(key),
            "prompt": {"text": str(prompt or "").strip()},
            "repos": [{"url": f"https://github.com/{admission.repository}", "startingRef": admission.base_sha}],
            "autoCreatePR": True,
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

    def record_followup(self, mission_id, agent_id, run_id, failed_attempts):
        return self.record_progress(mission_id, {"event": "cursor_followup", "cursor_agent_id": agent_id,
                                                "cursor_run_id": run_id, "failed_attempts": int(failed_attempts)})

    def request_admission(self, mission_id, expected_head_sha):
        return self.client.request("POST", f"/charlie/hermes/missions/{urllib.parse.quote(str(mission_id), safe='')}/admission",
                                   {"expected_head_sha": str(expected_head_sha or "")})


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
        review_items = list(reviews.get("items") or [])
        verdicts = [str(item.get("body") or "").strip().upper()
                    for item in review_items if isinstance(item, dict)]
        observed_at = float(time.time() if now is None else now)
        stalled_checks = [str(run.get("name") or "") for run in runs
                          if run.get("status") in {"queued", "in_progress"}
                          and (started := _parse_epoch(run.get("started_at")))
                          and observed_at - started > stall_seconds]
        return {"pr_number": int(number), "head_sha": head,
                "branch": str((pull.get("head") or {}).get("ref") or ""),
                "checks": required, "stalled_checks": stalled_checks,
                "ci_stalled": bool(stalled_checks),
                "independent_review": "SEND_BACK" if "SEND_BACK" in verdicts else ("APPROVE" if "APPROVE" in verdicts else "WAIT")}


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
                 github=None, issuer=None, clock=time.time):
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
        if (canonical.get("mission_id") != mission_id or current.get("status") != "valid"
                or current.get("mission_id") != mission_id
                or current.get("generation") != contract.get("generation")):
            raise HermesBridgeError("current_canonical_admission_required")
        admission = CursorAdmission.from_mapping({
            "mission_id": mission_id, "generation": current.get("generation"),
            "receipt_id": current.get("receipt_id"),
            "repository": "Crewless9086/amadeus-pig-tracking-system",
            "base_sha": contract.get("base_sha"), "allowed_files": contract.get("allowed_files"),
            "allowed_effects": contract.get("allowed_effects"),
            "owner_instruction_digest": current.get("latest_correction_digest"),
            "acceptance_requirements": contract.get("operational_acceptance"),
        })
        key = mission_idempotency_key(admission.mission_id, admission.generation)
        existing = self.canonical.get_dispatch(key)
        if existing and existing.get("cursor_agent_id"):
            return {"status": "existing_dispatch", **existing}
        if self.canonical.running_writer_count() >= self.MAX_RUNNING_WRITERS:
            raise HermesBridgeError("writer_capacity_reached")
        response = self.cursor.create_agent(
            admission, self._cursor_prompt({**row, "instruction": canonical.get("raw_text")}, admission))
        agent = dict(response.get("agent") or {})
        run = dict(response.get("run") or {})
        if not agent.get("id") or not run.get("id"):
            raise HermesBridgeError("cursor_dispatch_unverified")
        return self.canonical.record_dispatch(key, {
            "mission_id": admission.mission_id,
            "generation": admission.generation,
            "cursor_agent_id": agent["id"], "cursor_run_id": run["id"], "agent_state": "ACTIVE",
        })

    def poll(self, mission):
        row = dict(mission or {})
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
            return self.route_send_back(current, "SEND_BACK", correction)
        return observed

    def issue_admission(self, mission_id, expected_head_sha):
        if self.issuer:
            return self.issuer(mission_id=mission_id, expected_head_sha=expected_head_sha)
        return self.canonical.request_admission(mission_id, expected_head_sha)

    def route_send_back(self, mission, verdict, correction):
        row = dict(mission or {})
        if str(verdict or "").upper() != "SEND_BACK":
            raise HermesBridgeError("send_back_verdict_required")
        dispatch = dict(row.get("dispatch") or {})
        if int(dispatch.get("failed_attempts") or 0) >= self.MAX_FAILED_ATTEMPTS:
            raise HermesBridgeError("failed_attempt_limit_reached")
        response = self.cursor.continue_agent(dispatch.get("cursor_agent_id"), str(correction or "").strip())
        run = dict(response.get("run") or {})
        failed_attempts = int(dispatch.get("failed_attempts") or 0) + 1
        return self.canonical.record_followup(row.get("mission_id"), dispatch.get("cursor_agent_id"),
                                              run.get("id"), failed_attempts)

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
            "charlie_dispatch_cursor": self.dispatch_cursor,
            "charlie_get_mission_status": lambda value: self.canonical.get_mission(value["mission_id"]),
            "charlie_get_cursor_status": self.poll,
            "charlie_issue_admission": lambda value: self.issue_admission(value["mission_id"], value["expected_head_sha"]),
            "charlie_supervise_once": self.supervise_once,
            "charlie_continue_cursor": lambda value: self.route_send_back(value["mission"], "SEND_BACK", value["correction"]),
            "charlie_prepare_owner_decision": self.prepare_owner_decision,
            "charlie_handle_slack_event": self.handle_slack_request,
        }

    @staticmethod
    def _cursor_prompt(mission, admission):
        return "\n".join([
            "Implement this already-admitted CHARLIE mission. Do not merge or deploy.",
            f"Mission: {admission.mission_id}", f"Generation: {admission.generation}",
            f"Admission: {admission.receipt_id}", f"Owner instruction digest: {admission.owner_instruction_digest}",
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
        "CHARLIE_CANONICAL_API_URL", "CHARLIE_HERMES_GATEWAY_TOKEN", "CURSOR_API_KEY",
        "SLACK_SIGNING_SECRET", "SLACK_BOT_TOKEN", "CHARLIE_SLACK_OWNER_USER_ID",
        "SLACK_APP_TOKEN", "SLACK_ALLOWED_USERS",
        "CHARLIE_SLACK_CHARLIE_CHANNEL_ID", "CHARLIE_SLACK_BUILD_CHANNEL_ID",
        "CHARLIE_SLACK_APPROVALS_CHANNEL_ID",
    )
    values = {key: _protected_value(env, key) for key in required}
    github_token = _protected_value(env, "CHARLIE_GITHUB_READ_TOKEN", required=False)
    if any(str(env.get(name) or "").strip() for name in (
            "CHARLIE_GITHUB_WRITE_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")):
        raise HermesBridgeError("github_write_credential_forbidden")
    allowed_users = {item.strip() for item in values["SLACK_ALLOWED_USERS"].split(",") if item.strip()}
    if values["CHARLIE_SLACK_OWNER_USER_ID"] not in allowed_users:
        raise HermesBridgeError("slack_owner_missing_from_gateway_allowlist")
    canonical_client = JsonHttpClient(values["CHARLIE_CANONICAL_API_URL"], values["CHARLIE_HERMES_GATEWAY_TOKEN"], opener=opener)
    cursor_client = JsonHttpClient("https://api.cursor.com", values["CURSOR_API_KEY"], opener=opener)
    slack_client = JsonHttpClient("https://slack.com/api", values["SLACK_BOT_TOKEN"], opener=opener)
    github_client = JsonHttpClient("https://api.github.com", github_token, opener=opener)
    supervisor = HermesSupervisor(
        CanonicalCharlieApi(values["CHARLIE_CANONICAL_API_URL"], values["CHARLIE_HERMES_GATEWAY_TOKEN"], client=canonical_client),
        CursorCloudV1(values["CURSOR_API_KEY"], client=cursor_client),
        owner_slack_user_id=values["CHARLIE_SLACK_OWNER_USER_ID"],
        slack_signing_secret=values["SLACK_SIGNING_SECRET"],
        slack_command_channel_id=values["CHARLIE_SLACK_CHARLIE_CHANNEL_ID"],
        slack_build_channel_id=values["CHARLIE_SLACK_BUILD_CHANNEL_ID"],
        slack_approval_channel_id=values["CHARLIE_SLACK_APPROVALS_CHANNEL_ID"],
        slack_bot=SlackBot(values["SLACK_BOT_TOKEN"], client=slack_client),
        github=GitHubReadMonitor("Crewless9086/amadeus-pig-tracking-system", client=github_client),
    )
    if validate_live:
        if cursor_client.request("GET", "/v1/me").get("error"):
            raise HermesBridgeError("cursor_configuration_invalid")
        if canonical_client.request("GET", "/charlie/hermes/writers").get("success") is not True:
            raise HermesBridgeError("canonical_configuration_invalid")
        if slack_client.request("POST", "/auth.test", {}).get("ok") is not True:
            raise HermesBridgeError("slack_configuration_invalid")
        repository = github_client.request("GET", "/repos/Crewless9086/amadeus-pig-tracking-system")
        if repository.get("full_name") != "Crewless9086/amadeus-pig-tracking-system":
            raise HermesBridgeError("github_read_monitor_unavailable")
    return PluginTools(supervisor)
