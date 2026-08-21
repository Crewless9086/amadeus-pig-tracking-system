from datetime import datetime, timedelta, timezone
from hashlib import sha256
import importlib.util
import json
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).parents[1]
APP = ROOT / "green_print_bridge"
SPEC = importlib.util.spec_from_file_location("green_app_service", APP / "app" / "service.py")
SERVICE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVICE)
NOW = datetime(2026, 8, 21, 8, tzinfo=timezone.utc)
PDF = b"%PDF-1.4\nsynthetic non-farm fixture\n%%EOF"


def config(tmp_path):
    certificate = tmp_path / "private-ca.crt"
    certificate.write_text("synthetic-test-placeholder", encoding="utf-8")
    return {
        "canonical_api_origin": "https://documents.invalid",
        "canonical_intake_path": "/api/documents/print-jobs/claimable",
        "canonical_bearer_token": "synthetic-test-token",
        "green_id": "green-synthetic",
        "printer_id": "printer-synthetic",
        "cups_queue_id": "weekly-a4",
        "registry_version": "registry-synthetic-v1",
        "printer_uri": "ipps://printer.invalid/ipp/print",
        "ca_certificate_path": str(certificate),
        "poll_seconds": 30,
    }


def envelope(**changes):
    value = {
        "job_id": "JOB-SYNTHETIC-1",
        "document_id": "WWS-SYNTHETIC",
        "document_version": "WWS-SYNTHETIC.r1.abcdef123456",
        "document_type": SERVICE.PILOT_DOCUMENT,
        "generator_id": SERVICE.PILOT_GENERATOR,
        "pdf_sha256": sha256(PDF).hexdigest(),
        "retrieval_url": "https://documents.invalid/api/documents/WWS-SYNTHETIC/versions/WWS-SYNTHETIC.r1.abcdef123456/pdf",
        "green_id": "green-synthetic",
        "printer_id": "printer-synthetic",
        "cups_queue_id": "weekly-a4",
        "registry_version": "registry-synthetic-v1",
        "authorization_receipt_id": "AUTH-SYNTHETIC-1",
        "authorization_expires_at": (NOW + timedelta(hours=1)).isoformat(),
        "options": dict(SERVICE.FIXED_OPTIONS),
    }
    value.update(changes)
    return value


def test_repository_and_app_are_bounded_aarch64_artifacts():
    repository = yaml.safe_load((ROOT / "repository.yaml").read_text(encoding="utf-8"))
    app = yaml.safe_load((APP / "config.yaml").read_text(encoding="utf-8"))
    assert repository["name"] and app["arch"] == ["aarch64"]
    assert app["boot"] == "auto" and app["backup"] == "cold" and app["tmpfs"] is True
    assert app["host_network"] is False and app["privileged"] == [] and app["full_access"] is False
    assert app["map"] == [{"type": "addon_config", "read_only": True}]
    assert app["schema"]["canonical_bearer_token"] == "password"
    assert "canonical_intake_path" not in app["schema"] and "ca_certificate_path" not in app["schema"]
    assert not app.get("ports") and not app.get("ports_description")
    assert "BUILD_FROM" not in (APP / "Dockerfile").read_text(encoding="utf-8")


def test_contract_rejects_owner_controlled_url_queue_and_options(tmp_path):
    cfg = config(tmp_path)
    SERVICE.validate(envelope(), cfg, NOW)
    for changed in (
        {"cups_queue_id": "owner-text-queue"},
        {"retrieval_url": "https://other.invalid/file.pdf"},
        {"retrieval_url": envelope()["retrieval_url"] + "?token=secret"},
        {"options": {**SERVICE.FIXED_OPTIONS, "copies": 2}},
        {"document_type": "arbitrary.pdf"},
    ):
        with pytest.raises(SERVICE.Hold):
            SERVICE.validate(envelope(**changed), cfg, NOW)


def test_runtime_configuration_requires_private_tls_and_credential_free_ipps(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    monkeypatch.setattr(SERVICE, "CA_CERTIFICATE_PATH", cfg["ca_certificate_path"])
    path = tmp_path / "options.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(SERVICE.socket, "getaddrinfo", lambda *_args: [(None, None, None, None, ("10.23.0.5", 0))])
    loaded = SERVICE.load_config(str(path))
    assert loaded["cups_queue_id"] == "weekly-a4"
    assert loaded["canonical_intake_path"] == SERVICE.CANONICAL_INTAKE_PATH
    assert loaded["ca_certificate_path"] == cfg["ca_certificate_path"]
    for changes in (
        {"canonical_api_origin": "http://documents.invalid"},
        {"printer_uri": "ipp://printer.invalid/ipp/print"},
        {"printer_uri": "ipps://user:password@printer.invalid/ipp/print"},
    ):
        path.write_text(json.dumps({**cfg, **changes}), encoding="utf-8")
        with pytest.raises(SERVICE.Hold):
            SERVICE.load_config(str(path))


def test_runtime_configuration_rejects_public_resolution(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    path = tmp_path / "options.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setattr(SERVICE.socket, "getaddrinfo", lambda *_args: [(None, None, None, None, ("8.8.8.8", 0))])
    with pytest.raises(SERVICE.Hold, match="public_endpoint_forbidden"):
        SERVICE.load_config(str(path))


def test_ledger_replay_concurrency_and_restart_reconciliation_state(tmp_path):
    ledger = SERVICE.Ledger(str(tmp_path / "ledger.sqlite3"))
    job = envelope()
    ledger.ingest(job, NOW)
    ledger.ingest(job, NOW)
    token = ledger.claim(job["job_id"], "worker-one", NOW)
    assert token
    assert ledger.claim(job["job_id"], "worker-two", NOW) is None
    attempt = ledger.prepare(job["job_id"], token, NOW)
    ledger.submitted(job["job_id"], token, "weekly-a4-42", NOW)
    reopened = SERVICE.Ledger(str(tmp_path / "ledger.sqlite3"))
    assert reopened.get(job["job_id"])["attempt_id"] == attempt
    assert reopened.get(job["job_id"])["cups_job_id"] == "weekly-a4-42"
    assert reopened.recoverable()[0]["job_id"] == job["job_id"]


def test_pre_submission_exception_is_retryable_but_post_attempt_is_ambiguous(tmp_path):
    ledger = SERVICE.Ledger(str(tmp_path / "ledger.sqlite3"))
    job = envelope()
    ledger.ingest(job, NOW)
    token = ledger.claim(job["job_id"], "worker-one", NOW)
    ledger.prepare(job["job_id"], token, NOW)
    ledger.ambiguous(job["job_id"], "synthetic_timeout", NOW)
    assert ledger.get(job["job_id"])["state"] == "ambiguous"
    assert ledger.claim(job["job_id"], "worker-two", NOW + timedelta(minutes=6)) is None


def test_cups_submission_is_fixed_and_shell_free(monkeypatch):
    observed = {}

    class Result:
        stdout = "request id is weekly-a4-42 (1 file(s))"

    def fake_run(args, **kwargs):
        observed.update(args=args, kwargs=kwargs)
        return Result()

    monkeypatch.setattr(SERVICE.subprocess, "run", fake_run)
    assert SERVICE.Cups("weekly-a4").submit("/tmp/synthetic.pdf") == "weekly-a4-42"
    assert observed["args"] == ["lp", "-d", "weekly-a4", "-n", "1", "-o", "media=A4",
                                "-o", "ColorModel=Gray", "-o", "sides=one-sided", "/tmp/synthetic.pdf"]
    assert observed["kwargs"]["check"] is True and observed["kwargs"]["capture_output"] is True


def test_cups_observation_matches_exact_provider_identity(monkeypatch):
    outputs = iter(("weekly-a4-420 owner 1\n", "weekly-a4-42 owner 1\n"))

    class Result:
        def __init__(self, stdout):
            self.stdout = stdout

    monkeypatch.setattr(SERVICE.subprocess, "run", lambda *_args, **_kwargs: Result(next(outputs)))
    assert SERVICE.Cups("weekly-a4").observe("weekly-a4-42") == "completed"


def test_intake_rejects_ambiguity_instead_of_reporting_event_waiting():
    client = object.__new__(SERVICE.CanonicalClient)
    client.config = {}
    client.request = lambda *_args, **_kwargs: {"jobs": [envelope(), envelope(job_id="JOB-SYNTHETIC-2")]}
    with pytest.raises(SERVICE.Hold, match="canonical_intake_ambiguous"):
        client.next_job()


def test_redirect_and_naive_authorization_timestamp_fail_closed(tmp_path):
    with pytest.raises(SERVICE.Hold, match="https_redirect_forbidden"):
        SERVICE.assert_exact_response_url("https://other.invalid/file.pdf", envelope()["retrieval_url"])
    with pytest.raises(SERVICE.Hold, match="timestamp_timezone_required"):
        SERVICE.validate(envelope(authorization_expires_at="2026-08-21T09:00:00"), config(tmp_path), NOW)


def test_restart_reconciles_local_submission_before_polling_new_intake(tmp_path, monkeypatch):
    ledger = SERVICE.Ledger(str(tmp_path / "ledger.sqlite3"))
    job = envelope()
    ledger.ingest(job, NOW)
    token = ledger.claim(job["job_id"], "worker-one", NOW)
    ledger.prepare(job["job_id"], token, NOW)
    ledger.submitted(job["job_id"], token, "weekly-a4-42", NOW)

    class Client:
        def next_job(self):
            raise AssertionError("new intake must wait for local recovery")

        def evidence(self, *_args):
            return None

    class Provider:
        def observe(self, _cups_id):
            return "completed"

    monkeypatch.setattr(SERVICE, "utcnow", lambda: NOW + timedelta(minutes=1))
    assert SERVICE.cycle(ledger, Client(), Provider(), config(tmp_path), "worker-two") == "provider_completed"


def test_health_and_logs_are_content_and_secret_free(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(SERVICE, "Path", lambda value: Path("data/health.json") if value == "/data/health.json" else Path(value))
    SERVICE.write_health("event_waiting", "green-worker-synthetic", "event_waiting", NOW)
    value = json.loads((tmp_path / "data" / "health.json").read_text(encoding="utf-8"))
    material = json.dumps(value)
    assert "synthetic-test-token" not in material and "%PDF" not in material
    assert value["terminal_participated"] is False


def test_no_sensitive_runtime_values_are_committed_in_app_artifact():
    material = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in APP.rglob("*") if path.is_file())
    forbidden = ("service_role", "SUPABASE_SERVICE_ROLE_KEY=", "BEGIN CERTIFICATE", "192.168.", "10.0.")
    assert not any(value in material for value in forbidden)
