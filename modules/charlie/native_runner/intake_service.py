"""Deterministic HTTPS receipt poller. Never initializes or starts the coding service."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
import signal
import threading
import urllib.error
import urllib.request
import uuid

BASE_URL = "https://amadeus-pig-tracking-system.onrender.com/api/charlie/core/manager-intake/cloud"
WORKER_SERVICE = "srv-dacofeoae00c73813eug"
CONTRACT = "core.cloud_receipt_intake.v1"
HTTP_TIMEOUT_SECONDS = 90


class IntakeWorkerRefused(ValueError):
    pass


def need(value, reason):
    if not value:
        raise IntakeWorkerRefused(reason)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise IntakeWorkerRefused("redirect_refused")


class ReceiptClient:
    def __init__(self, token, *, opener=None):
        need(isinstance(token, str) and re.fullmatch(r"[A-Za-z0-9_-]{43,128}", token), "worker_credential_unavailable")
        self._token = token
        self.opener = opener or urllib.request.build_opener(NoRedirect())

    def request(self, path, payload=None):
        need(path in {"/current", "/cycles"}, "endpoint_refused")
        data = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
        request = urllib.request.Request(BASE_URL + path, data=data,
            headers={"Authorization": "Bearer " + self._token, "Content-Type": "application/json"},
            method="POST" if payload is not None else "GET")
        # An ambiguous POST is never retried here. The owner can inspect the
        # persisted begun/completed operation and canonical receipt readback.
        # Socket timeout leaves margin for admission (10s), shared intake
        # (60s) and completion (10s); it is not a total wall-clock deadline.
        with self.opener.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            need(response.status == 200, "api_refused")
            raw = response.read(65537)
            need(len(raw) <= 65536, "api_response_bound")
            packet = json.loads(raw.decode("utf-8"))
        need(isinstance(packet, dict) and packet.get("contract") == CONTRACT, "api_contract_invalid")
        return packet


def run_worker(*, environ=None, client=None, stop=None, clock=None, report=None):
    values = os.environ if environ is None else environ
    need(values.get("CORE_NATIVE_RUNNER_MODE") == "receipt_only", "receipt_mode_required")
    need(values.get("RENDER_SERVICE_ID") == WORKER_SERVICE, "worker_service_mismatch")
    revision = values.get("RENDER_GIT_COMMIT", "")
    need(re.fullmatch(r"[a-f0-9]{40}", revision), "worker_revision_invalid")
    client = client or ReceiptClient(values.get("CORE_CLOUD_INTAKE_EPOCH_TOKEN", ""))
    stop = stop or threading.Event()
    clock = clock or (lambda: datetime.now(timezone.utc))
    report = report or (lambda value: print(json.dumps(value, sort_keys=True), flush=True))
    instance = uuid.uuid4().hex
    epoch_id = None
    was_active = False
    report({"status": "receipt_worker_started", "instance": instance, "revision": revision,
            "service_id": WORKER_SERVICE, "model_initialized": False})
    try:
        while not stop.is_set():
            current = client.request("/current")
            if current.get("status") == "awaiting_epoch" and current.get("active") is False:
                report({"status": "receipt_worker_awaiting_epoch", "instance": instance})
                if stop.wait(30):
                    break
                continue
            provider = current.get("provider") or {}
            need(provider.get("worker_service_id") == WORKER_SERVICE and provider.get("worker_revision") == revision,
                 "worker_deployment_not_admitted")
            current_id = current.get("epoch_id", "")
            need(re.fullmatch(r"[a-f0-9]{32}", current_id), "epoch_identity_invalid")
            need(epoch_id in (None, current_id), "epoch_changed_restart_requires_owner")
            epoch_id = current_id
            expiry = datetime.fromisoformat(current["expires_at"].replace("Z", "+00:00"))
            need(expiry.utcoffset() is not None, "expiry_not_aware")
            if clock() >= expiry:
                report({"status": "receipt_epoch_expired", "epoch_id": epoch_id, "instance": instance})
                while not stop.wait(30):
                    pass
                break
            if current.get("active") is not True:
                report({"status": "receipt_epoch_inactive", "epoch_id": epoch_id, "instance": instance})
                if was_active or current.get("status") == "revoked":
                    while not stop.wait(30):
                        pass
                    break
                if stop.wait(30):
                    break
                continue
            was_active = True
            request_id = uuid.uuid4().hex
            result = client.request("/cycles", {"epoch_id": epoch_id, "request_id": request_id,
                "worker_instance": instance, "worker_service_id": WORKER_SERVICE, "worker_revision": revision})
            need(result.get("epoch_id") == epoch_id and result.get("request_id") == request_id,
                 "cycle_identity_mismatch")
            report({"status": "receipt_cycle_observed", "epoch_id": epoch_id, "request_id": request_id,
                    "instance": instance, "success": result.get("success") is True})
            if result.get("success") is not True:
                raise IntakeWorkerRefused("cycle_failed_requires_owner_readback")
            if stop.wait(30):
                break
    except Exception as exc:
        # Never print URLs, response bodies, tokens, database material or errors.
        report({"status": "receipt_worker_contained", "instance": instance,
                "failure_kind": type(exc).__name__})
        # Stay alive and inert; a provider restart is not an automatic retry.
        while not stop.wait(30):
            pass
        return 0
    finally:
        report({"status": "receipt_worker_stopped", "instance": instance, "epoch_id": epoch_id})
    return 0


def main():
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    return run_worker(stop=stop)
