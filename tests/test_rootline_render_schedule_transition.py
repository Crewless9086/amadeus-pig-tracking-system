from scripts.rootline_render_schedule_transition import (
    CRON_ID, EXPECTED_PRIOR_SCHEDULE, TARGET_SCHEDULE, transition,
)


REVISION = "a" * 40


def provider(*, schedule=EXPECTED_PRIOR_SCHEDULE, web_revision=REVISION,
             cron_revision=REVISION, refuse_patch=False):
    state = {"schedule": schedule, "calls": []}
    def request(method, url, payload):
        state["calls"].append((method, url, payload))
        if url.endswith("/health/revision"):
            return {"status": "ok", "provider": "render", "identity_complete": True,
                    "revision": web_revision}
        if "/deploys?" in url:
            return [{"deploy": {"status": "live", "commit": {"id": cron_revision}}}]
        if method == "PATCH":
            if not refuse_patch:
                state["schedule"] = payload["serviceDetails"]["schedule"]
            return {}
        return {"service": {"id": CRON_ID, "name": "rootline-autonomous-reassessment",
            "type": "cron_job", "suspended": "not_suspended",
            "serviceDetails": {"schedule": state["schedule"]}}}
    return state, request


def test_transition_requires_exact_live_web_and_cron_revision_before_patch():
    for changes in ({"web_revision": "b" * 40}, {"cron_revision": "b" * 40}):
        state, request = provider(**changes)
        result = transition(expected_source_commit=REVISION, request_json=request)
        assert result["success"] is False
        assert not [call for call in state["calls"] if call[0] == "PATCH"]


def test_transition_updates_only_named_schedule_and_verifies_readback():
    state, request = provider()
    result = transition(expected_source_commit=REVISION, request_json=request)
    patches = [call for call in state["calls"] if call[0] == "PATCH"]
    assert result["status"] == "render_cron_schedule_transition_verified"
    assert result["schedule"] == state["schedule"] == TARGET_SCHEDULE
    assert patches == [("PATCH", f"https://api.render.com/v1/services/{CRON_ID}",
                        {"serviceDetails": {"schedule": TARGET_SCHEDULE}})]
    assert result["hardware_commands"] == result["farm_writes"] == 0


def test_transition_fails_closed_on_unexpected_prior_schedule():
    state, request = provider(schedule="*/5 * * * *")
    result = transition(expected_source_commit=REVISION, request_json=request)
    assert result["status"] == "render_cron_prior_schedule_mismatch"
    assert not [call for call in state["calls"] if call[0] == "PATCH"]


def test_transition_attempts_exact_rollback_when_readback_does_not_change():
    state, request = provider(refuse_patch=True)
    result = transition(expected_source_commit=REVISION, request_json=request)
    patches = [call for call in state["calls"] if call[0] == "PATCH"]
    assert result["status"] == "render_cron_schedule_readback_mismatch"
    assert patches[-1][2] == {"serviceDetails": {"schedule": EXPECTED_PRIOR_SCHEDULE}}
