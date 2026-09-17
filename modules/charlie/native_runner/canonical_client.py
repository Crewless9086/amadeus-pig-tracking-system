"""Credential-contained clients used by the standalone CHARLIE runner."""

from __future__ import annotations

import json
import uuid
import urllib.error
import urllib.parse
import urllib.request

from .execution import NativeExecutionError


class JsonClient:
    def __init__(self, base_url, token="", *, timeout=20, opener=None):
        self.base_url = str(base_url).rstrip("/")
        self.token = str(token)
        self.timeout = min(max(int(timeout), 1), 30)
        self.opener = opener or urllib.request.urlopen

    def request(self, method, path, payload=None, query=None):
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        body = None
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with self.opener(request, timeout=self.timeout) as response:
                value = json.loads(response.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            if exc.code in {404, 409}:
                return {"status_code": exc.code}
            raise NativeExecutionError("native_transport_unavailable") from exc
        except (OSError, TimeoutError, ValueError) as exc:
            raise NativeExecutionError("native_transport_unavailable") from exc
        if isinstance(value, list):
            return {"items": value}
        if not isinstance(value, dict):
            raise NativeExecutionError("native_transport_response_invalid")
        return value


class CanonicalClient:
    def __init__(self, base_url, token, *, client=None):
        self.client = client or JsonClient(base_url, token)

    @staticmethod
    def _mission(mission_id):
        return urllib.parse.quote(str(mission_id), safe="")

    def resumable(self):
        return list(self.client.request("GET", "/charlie/hermes/native-executions/resumable").get("executions") or [])

    def mission(self, mission_id):
        return self.client.request("GET", f"/charlie/hermes/missions/{self._mission(mission_id)}")

    def native_context(self, mission_id):
        return self.client.request("GET", f"/charlie/hermes/missions/{self._mission(mission_id)}/native-context").get("context") or {}

    def writers(self):
        return int(self.client.request("GET", "/charlie/hermes/writers").get("running") or 0)

    def retire_cursor(self, mission_id, evidence):
        return self.client.request("POST", f"/charlie/hermes/missions/{self._mission(mission_id)}/cursor-retirement", evidence).get("retirement") or {}

    def renew_authority(self, mission_id):
        return self.client.request("POST", f"/charlie/hermes/missions/{self._mission(mission_id)}/dispatch-authorization", {}).get("authorization") or {}

    def prepare_native(self, mission_id, worktree_digest, starting_main_sha):
        payload = {"worktree_digest": worktree_digest, "starting_main_sha": starting_main_sha}
        return self.client.request("POST", f"/charlie/hermes/missions/{self._mission(mission_id)}/native-execution", payload).get("authorization") or {}

    def progress(self, mission_id, payload):
        result = self.client.request("POST", f"/charlie/hermes/missions/{self._mission(mission_id)}/native-execution/progress", payload)
        return result.get("authorization") or result

    def blocker(self, mission_id, payload):
        return self.client.request(
            "POST", f"/charlie/hermes/missions/{self._mission(mission_id)}/native-runner/blocker",
            payload)

    def bind_candidate(self, mission_id, payload):
        return self.client.request("POST", f"/charlie/build-relay/missions/{self._mission(mission_id)}/external-candidate", payload)

    def request_admission(self, mission_id, head_sha, pr_number):
        return self.client.request("POST", f"/charlie/hermes/missions/{self._mission(mission_id)}/admission",
                                   {"expected_head_sha": head_sha, "pr_number": int(pr_number)})


class CursorRetirementClient:
    """Cursor is available only for attempt-5 containment; it cannot create agents."""

    def __init__(self, token, *, client=None):
        self.client = client or JsonClient("https://api.cursor.com", token)

    def get_agent(self, agent_id):
        return self.client.request("GET", f"/v1/agents/{agent_id}")

    def get_run(self, agent_id, run_id):
        return self.client.request("GET", f"/v1/agents/{agent_id}/runs/{run_id}")

    def cancel(self, agent_id, run_id):
        return self.client.request("POST", f"/v1/agents/{agent_id}/runs/{run_id}/cancel", {})

    def archive(self, agent_id):
        return self.client.request("POST", f"/v1/agents/{agent_id}/archive", {})


class SlackNotifier:
    def __init__(self, token, *, client=None):
        self.client = client or JsonClient("https://slack.com/api", token)

    def post(self, channel, text, *, thread_ts="", idempotency_key=""):
        payload = {"channel": channel, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        if idempotency_key:
            payload["client_msg_id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "charlie-slack:" + idempotency_key))
        result = self.client.request("POST", "/chat.postMessage", payload)
        if result.get("ok") is not True:
            raise NativeExecutionError("native_slack_notification_failed")
        return result


class GitHubObserver:
    REQUIRED = frozenset({
        "mission-admission", "charlie-core",
        "Unit tests with disposable Postgres audit rails",
        "Closed Render migration rail with disposable Postgres",
        "Playwright real-browser behavior gate",
    })

    def __init__(self, token="", *, client=None):
        self.client = client or JsonClient("https://api.github.com", token)
        self.repository = "Crewless9086/amadeus-pig-tracking-system"

    def branch_exists(self, branch):
        result = self.client.request("GET", f"/repos/{self.repository}/git/ref/heads/{urllib.parse.quote(branch, safe='')}")
        return result.get("status_code") != 404

    def find_pull(self, branch):
        result = self.client.request("GET", f"/repos/{self.repository}/pulls",
                                     query={"state": "open", "head": "Crewless9086:" + branch})
        items = list(result.get("items") or [])
        if len(items) > 1:
            raise NativeExecutionError("native_duplicate_pull_requests")
        return int(items[0].get("number") or 0) if items else 0

    def pull_state(self, number):
        pull = self.client.request("GET", f"/repos/{self.repository}/pulls/{int(number)}")
        head = str((pull.get("head") or {}).get("sha") or "")
        checks = self.client.request("GET", f"/repos/{self.repository}/commits/{head}/check-runs",
                                     query={"filter": "latest", "per_page": 100})
        rows = list(checks.get("check_runs") or [])
        by_name = {str(item.get("name")): item for item in rows}
        admission_rows = [item for item in rows if str(item.get("name")) == "mission-admission"]
        trusted_admission = (
            len(admission_rows) == 1
            and int((admission_rows[0].get("app") or {}).get("id") or 0) == 4742997
            and admission_rows[0].get("conclusion") == "success"
        )
        passed = trusted_admission and all(
            by_name.get(name, {}).get("conclusion") == "success"
            for name in self.REQUIRED if name != "mission-admission"
        )
        conclusions = {name: by_name.get(name, {}).get("conclusion", "missing")
                       for name in sorted(self.REQUIRED)}
        if not trusted_admission:
            conclusions["mission-admission"] = "untrusted_or_ambiguous"
        return {"pr_number": int(number), "head_sha": head, "draft": bool(pull.get("draft")),
                "checks": conclusions,
                "all_required_checks_pass": passed}
