from datetime import datetime, timezone
from unittest.mock import patch

from app import app
from modules.telemetry.rootline_operational_evidence import (
    _bind_execution_events, _controller, _execution, build_rootline_operational_evidence,
)

NOW = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)


def env():
    return {"OWNER_ACCESS_ENABLED": "true", "OWNER_ACCESS_ALLOW_LOCAL_DEV": "false",
        "OWNER_SESSION_SECRET": "s" * 40, "OWNER_ADMIN_TOKEN": "a" * 40,
        "OWNER_READ_TOKEN": "r" * 40, "RENDER_GIT_COMMIT": "2" * 40}


def test_route_denies_unauthorized_and_returns_no_store_for_read_role():
    app.config.update(TESTING=True)
    client = app.test_client()
    with patch.dict("os.environ", env(), clear=True):
        denied = client.get("/api/telemetry/rootline/operational-evidence",
                            environ_base={"REMOTE_ADDR": "203.0.113.4"})
        assert denied.status_code == 403
        client.post("/owner/login", data={"owner_token": "r" * 40},
                    environ_base={"REMOTE_ADDR": "203.0.113.4"})
        packet = {"success": True, "audit": {"audit_id": "A", "requester": "opaque"},
                  "requested_revision": "2" * 40}
        with patch("modules.telemetry.telemetry_routes.build_rootline_operational_evidence",
                   return_value=(packet, 200)) as builder:
            allowed = client.get("/api/telemetry/rootline/operational-evidence",
                                 environ_base={"REMOTE_ADDR": "203.0.113.4"})
        assert allowed.status_code == 200
        assert allowed.headers["Cache-Control"] == "no-store, private"
        requester = builder.call_args.kwargs["requester"]
        assert requester.startswith("owner-read:") and "r" * 16 not in requester


def test_expired_and_wrong_role_sessions_fail_closed():
    app.config.update(TESTING=True)
    with patch.dict("os.environ", env(), clear=True):
        client = app.test_client()
        client.post("/owner/login", data={"owner_token": "r" * 40},
                    environ_base={"REMOTE_ADDR": "203.0.113.4"})
        with client.session_transaction() as session:
            access = dict(session["owner_access"])
            access["created_at"] = "2000-01-01T00:00:00+00:00"
            session["owner_access"] = access
        assert client.get("/api/telemetry/rootline/operational-evidence",
            environ_base={"REMOTE_ADDR": "203.0.113.4"}).status_code == 403
        with client.session_transaction() as session:
            session["owner_access"] = {"role": "provider-control", "principal_id": "forged",
                                       "created_at": NOW.isoformat()}
        assert client.get("/api/telemetry/rootline/operational-evidence",
            environ_base={"REMOTE_ADDR": "203.0.113.4"}).status_code == 403


def test_provider_readback_is_exactly_b_channel_and_never_implies_flow():
    calls = []
    def reader(device):
        calls.append(device)
        return {"device_id": "100204e9bc", "switches": [{"outlet": 1, "switch": "on"},
                             {"outlet": 2, "switch": "off"}],
                "retrieved_at": NOW.isoformat(), "response_digest": "d" * 64,
                "provider_control_calls": 0, "access_token": "must-not-leak"}
    result = _controller(reader, NOW)
    assert calls == ["100204e9bc"]
    assert result["channel"] == 1 and result["state"] == "ON"
    assert result["controller_state_proves_physical_flow"] is False
    assert "access_token" not in str(result)


def test_provider_ambiguity_and_reported_control_call_fail_to_unknown():
    ambiguous = _controller(lambda _device: (_ for _ in ()).throw(RuntimeError("secret")), NOW)
    assert ambiguous["state"] == "Unknown" and ambiguous["provider_evidence_status"] == "Ambiguous"
    assert "secret" not in str(ambiguous)
    adverse = _controller(lambda _device: {"device_id": "100204e9bc",
        "switches": [{"outlet": 1, "switch": "on"}], "retrieved_at": NOW.isoformat(),
        "response_digest": "d" * 64, "provider_control_calls": 1}, NOW)
    assert adverse["state"] == "Unknown" and adverse["provider_evidence_status"] == "Ambiguous"


def test_absent_database_preserves_unknown_and_has_zero_effect_contract():
    with patch.dict("os.environ", {"RENDER_GIT_COMMIT": "2" * 40}, clear=True):
        result, status = build_rootline_operational_evidence(
            requester="owner-read:opaque", requested_at=NOW, database_url="")
    assert status == 503 and result["status"] == "canonical_evidence_unavailable"
    assert result["safety"] == {"can_control": False, "provider_control_calls": 0,
        "canonical_writes": 0, "telegram_sends": 0, "worker_invocations": 0}
    assert result["audit"]["requester"] == "owner-read:opaque"


def test_route_surface_is_get_only_and_has_no_control_companion():
    app.config.update(TESTING=True)
    client = app.test_client()
    with patch.dict("os.environ", env(), clear=True):
        client.post("/owner/login", data={"owner_token": "a" * 40},
                    environ_base={"REMOTE_ADDR": "203.0.113.4"})
        response = client.post("/api/telemetry/rootline/operational-evidence", json={},
                               environ_base={"REMOTE_ADDR": "203.0.113.4"})
    assert response.status_code == 405


def test_provider_wrong_device_missing_duplicate_and_stale_bindings_are_unknown():
    base = {"device_id": "100204e9bc", "retrieved_at": NOW.isoformat(),
            "response_digest": "d" * 64, "provider_control_calls": 0}
    cases = [
        {**base, "device_id": "wrong", "channels": [{"channel": 1, "output_state": "OFF"}]},
        {**base, "channels": [{"channel": 2, "output_state": "OFF"}]},
        {**base, "channels": [{"channel": 1, "output_state": "OFF"},
                              {"channel": 1, "output_state": "ON"}]},
        {**base, "retrieved_at": "2026-08-20T10:00:00+00:00",
         "channels": [{"channel": 1, "output_state": "OFF"}]},
    ]
    assert all(_controller(lambda _device, value=value: value, NOW)["state"] == "Unknown"
               for value in cases)


def test_interleaved_old_completion_cannot_complete_current_execution():
    events = [
        {"action": "record_completed", "operating_date": "2026-08-19", "job_id": "OLD",
         "execution_id": "E-OLD", "objective_satisfied": True, "shutdown_verified": True,
         "provider_output_state": "OFF", "objective_evidence": {"physical_flow": "normal"}},
        {"action": "record_eligibility", "operating_date": "2026-08-20", "job_id": "NEW",
         "execution_id": "E-NEW"},
        {"action": "claim_before_on", "operating_date": "2026-08-20", "job_id": "NEW",
         "execution_id": "E-NEW"},
    ]
    eligibility, bound = _bind_execution_events(events, "2026-08-20")
    terminal = next((e for e in bound if e["action"] == "record_completed"), {})
    started = next((e for e in bound if e["action"] == "claim_before_on"), {})
    result = _execution(bound[0], started, terminal)
    assert eligibility["execution_id"] == "E-NEW"
    assert result["control_segment_completion_supported"] is False
    assert result["b_irrigation_completion_supported"] is False
    assert result["stop_supported"] is False


def test_real_completion_shape_separates_control_segment_from_physical_parent_completion():
    terminal = {"action": "record_completed", "objective_satisfied": True,
        "shutdown_verified": True, "shutdown_evidence": {"authoritative": True, "state": "OFF"},
        "objective_evidence": {"physical_flow_confirmation": "Unavailable"},
        "job_completed": True}
    result = _execution(terminal, terminal, terminal)
    assert result["stop_supported"] is True
    assert result["control_segment_completion_supported"] is True
    assert result["b_irrigation_completion_supported"] is False


def test_provider_reader_is_called_with_refresh_disabled():
    app.config.update(TESTING=True)
    client = app.test_client()
    with patch.dict("os.environ", env(), clear=True):
        client.post("/owner/login", data={"owner_token": "r" * 40},
                    environ_base={"REMOTE_ADDR": "203.0.113.4"})
        def builder(**kwargs):
            with patch("modules.telemetry.telemetry_routes.read_registered_device",
                       return_value={}) as reader:
                kwargs["provider_reader"]("100204e9bc")
                assert reader.call_args.kwargs["allow_token_refresh"] is False
            return {"success": False, "audit": {}, "requested_revision": "2" * 40}, 503
        with patch("modules.telemetry.telemetry_routes.build_rootline_operational_evidence",
                   side_effect=builder):
            client.get("/api/telemetry/rootline/operational-evidence",
                       environ_base={"REMOTE_ADDR": "203.0.113.4"})
