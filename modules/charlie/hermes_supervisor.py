"""Bounded Hermes supervisor bridge for CHARLIE's canonical mission plane.

Hermes is a transport/supervision client.  It never owns mission truth, signs
receipts, writes GitHub, merges, deploys, or exposes arbitrary shell/database
access.  All durable mutation is delegated to authenticated CHARLIE APIs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass


class HermesBridgeError(RuntimeError):
    """Stable fail-closed bridge error."""


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
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise HermesBridgeError("transport_unavailable") from exc
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
        return self.client.request("POST", "/v1/agents", payload)

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


class HermesSupervisor:
    """Low-cost deterministic supervisor over canonical CHARLIE APIs."""

    MAX_RUNNING_WRITERS = 1
    MAX_FAILED_ATTEMPTS = 2
    AUTOMATIC_DECOMPOSITION = False

    def __init__(self, canonical, cursor, *, owner_slack_user_id, clock=time.time):
        self.canonical = canonical
        self.cursor = cursor
        self.owner_slack_user_id = str(owner_slack_user_id or "").strip()
        self.clock = clock
        if not self.owner_slack_user_id:
            raise HermesBridgeError("slack_owner_id_required")

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
        return self.canonical.reconcile_mission({
            "source": "slack", "source_event_id": event_id, "owner_user_id": self.owner_slack_user_id,
            "channel_id": channel, "thread_ts": thread, "instruction": text,
        }, idempotency_key=f"slack:{event_id}")

    def dispatch_cursor(self, mission):
        row = dict(mission or {})
        admission = CursorAdmission.from_mapping(row.get("admission"))
        key = mission_idempotency_key(admission.mission_id, admission.generation)
        existing = self.canonical.get_dispatch(key)
        if existing and existing.get("cursor_agent_id"):
            return {"status": "existing_dispatch", **existing}
        if self.canonical.running_writer_count() >= self.MAX_RUNNING_WRITERS:
            raise HermesBridgeError("writer_capacity_reached")
        response = self.cursor.create_agent(admission, self._cursor_prompt(row, admission))
        agent = dict(response.get("agent") or {})
        run = dict(response.get("run") or {})
        if not agent.get("id") or not run.get("id"):
            raise HermesBridgeError("cursor_dispatch_unverified")
        return self.canonical.record_dispatch(key, {
            "mission_id": admission.mission_id, "generation": admission.generation,
            "cursor_agent_id": agent["id"], "cursor_run_id": run["id"], "state": "ACTIVE",
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
        result = {"agent_state": state, "run_state": run_state, "stalled": bool(stalled)}
        return self.canonical.record_progress(row.get("mission_id"), result)

    def route_send_back(self, mission, verdict, correction):
        row = dict(mission or {})
        if str(verdict or "").upper() != "SEND_BACK":
            raise HermesBridgeError("send_back_verdict_required")
        dispatch = dict(row.get("dispatch") or {})
        if int(dispatch.get("failed_attempts") or 0) >= self.MAX_FAILED_ATTEMPTS:
            raise HermesBridgeError("failed_attempt_limit_reached")
        response = self.cursor.continue_agent(dispatch.get("cursor_agent_id"), str(correction or "").strip())
        run = dict(response.get("run") or {})
        return self.canonical.record_followup(row.get("mission_id"), dispatch.get("cursor_agent_id"), run.get("id"))

    def prepare_owner_decision(self, mission):
        row = dict(mission or {})
        if (row.get("all_required_checks_pass") is not True
                or row.get("independent_review") != "APPROVE"
                or not row.get("head_sha")
                or row.get("approved_head_sha") != row.get("head_sha")):
            raise HermesBridgeError("owner_decision_not_ready")
        return {"mission_id": row.get("mission_id"), "pr_number": row.get("pr_number"),
                "head_sha": row.get("head_sha"), "channel": "owner-approvals",
                "merge_or_deploy_performed": False}

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
