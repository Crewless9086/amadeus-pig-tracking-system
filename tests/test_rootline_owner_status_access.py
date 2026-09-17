from unittest.mock import patch

from app import app


def access_env():
    return {"OWNER_ACCESS_ENABLED": "true", "OWNER_ACCESS_ALLOW_LOCAL_DEV": "false",
            "OWNER_SESSION_SECRET": "s" * 40, "OWNER_ADMIN_TOKEN": "a" * 40,
            "OWNER_READ_TOKEN": "r" * 40}


def test_canonical_status_requires_owner_session_and_admin_cookie_satisfies_read_guard():
    app.config.update(TESTING=True)
    client = app.test_client()
    with patch.dict("os.environ", access_env(), clear=True):
        denied = client.get("/api/telemetry/irrigation/status?date=2026-08-11",
                            environ_base={"REMOTE_ADDR": "203.0.113.10"})
        assert denied.status_code == 403
        assert denied.get_json()["status"] == "owner_read_access_denied"
        login = client.post("/owner/login", data={"owner_token": "a" * 40,
                            "next": "/irrigation"},
                            environ_base={"REMOTE_ADDR": "203.0.113.10"})
        assert login.status_code == 302
        with patch("modules.telemetry.telemetry_routes.get_irrigation_status",
                   return_value=({"success": True, "source": {"source": "supabase"}}, 200)):
            allowed = client.get("/api/telemetry/irrigation/status?date=2026-08-11",
                                 environ_base={"REMOTE_ADDR": "203.0.113.10"})
        assert allowed.status_code == 200
        assert allowed.get_json()["source"]["source"] == "supabase"


def test_legacy_audit_is_guarded_and_uses_only_fixed_allowlisted_sheet():
    app.config.update(TESTING=True)
    client = app.test_client()
    with patch.dict("os.environ", access_env(), clear=True):
        client.post("/owner/login", data={"owner_token": "a" * 40},
                    environ_base={"REMOTE_ADDR": "203.0.113.10"})
        with patch("modules.telemetry.telemetry_routes.get_irrigation_status",
                   return_value=({"success": True, "source": {}}, 200)) as reader:
            response = client.get("/api/telemetry/irrigation/status/legacy-audit?spreadsheet=Other",
                                  environ_base={"REMOTE_ADDR": "203.0.113.10"})
        assert response.status_code == 200
        assert reader.call_args.kwargs["spreadsheet_name"] == "Amadeus_Irrigation_Logs"
        assert response.get_json()["source"]["operational_truth"] is False
