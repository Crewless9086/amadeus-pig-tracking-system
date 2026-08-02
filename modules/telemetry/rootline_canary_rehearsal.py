"""Pure, command-inert rehearsal model for the C12345 physical canary.

This module has no transport, credential, persistence, scheduling, retry, or
hardware interface.  It reduces predeclared observations into append-only
evidence so safety paths can be rehearsed without acquiring authority.
"""

from copy import deepcopy


PACKET_ID = "ROOTLINE-CANARY-C12345-CH2-G1"
ZONE_ID = "C12345"
ON_EVENT = "irrigation_1_ch2_on"
OFF_EVENT = "irrigation_1_ch2_off"
MAX_PULSE_SECONDS = 30

AUTHORITY = {
    "network_access": False,
    "credentials_loaded": False,
    "transport_authority": False,
    "hardware_control_authority": False,
    "automatic_retry": False,
    "schedule_authority": False,
    "workflow_authority": False,
    "command_queue_authority": False,
    "autonomous_continuation": False,
    "writes_performed": False,
    "hardware_control_performed": False,
}

SCENARIOS = {
    "normal": {
        "on_response": "accepted",
        "valve_open": "observed",
        "flow": "observed",
        "off_response": "accepted",
        "valve_closed": "observed",
        "supply_flow_stopped": "observed",
        "residual_drainage": "diminishing",
    },
    "on_accepted_no_valve_movement": {
        "on_response": "accepted",
        "valve_open": "not_observed",
        "flow": "not_observed",
        "off_response": "accepted",
        "valve_closed": "unclear",
        "supply_flow_stopped": "unclear",
        "residual_drainage": "none_observed",
    },
    "on_timeout_uncertain_delivery": {
        "on_response": "timeout",
        "valve_open": "unclear",
        "flow": "unclear",
        "off_response": "accepted",
        "valve_closed": "unclear",
        "supply_flow_stopped": "unclear",
        "residual_drainage": "unclear",
    },
    "unexpected_flow": {
        "on_response": "accepted",
        "valve_open": "unexpected_identity_or_behavior",
        "flow": "unexpected",
        "off_response": "accepted",
        "valve_closed": "unclear",
        "supply_flow_stopped": "unclear",
        "residual_drainage": "unclear",
    },
    "off_timeout": {
        "on_response": "accepted",
        "valve_open": "observed",
        "flow": "observed",
        "off_response": "timeout",
        "valve_closed": "unclear",
        "supply_flow_stopped": "unclear",
        "residual_drainage": "full_pressure_or_unclear",
    },
    "physical_closure_unclear": {
        "on_response": "accepted",
        "valve_open": "observed",
        "flow": "observed",
        "off_response": "accepted",
        "valve_closed": "unclear",
        "supply_flow_stopped": "unclear",
        "residual_drainage": "unclear",
    },
    "manual_isolation": {
        "on_response": "timeout",
        "valve_open": "unclear",
        "flow": "unexpected",
        "manual_isolation": "physically_verified_safe_closed",
        "off_response": "not_required_after_verified_manual_isolation",
        "valve_closed": "observed",
        "supply_flow_stopped": "observed",
        "residual_drainage": "diminishing",
    },
    "operator_abort": {
        "on_response": "unavailable",
        "valve_open": "unclear",
        "flow": "unclear",
        "operator_abort": True,
        "off_response": "accepted",
        "valve_closed": "unclear",
        "supply_flow_stopped": "unclear",
        "residual_drainage": "unclear",
    },
}


def rehearse_scenario(name):
    """Return an offline append-only evidence packet for a named scenario."""
    if name not in SCENARIOS:
        raise ValueError("unknown rehearsal scenario")

    observation = deepcopy(SCENARIOS[name])
    manual_safe = (
        observation.get("manual_isolation")
        == "physically_verified_safe_closed"
    )
    on_invoked = True
    off_required = on_invoked and not manual_safe
    off_issued = off_required

    entries = []

    def append(evidence_type, status, details=None):
        entries.append(
            {
                "evidence_id": f"{PACKET_ID}-E{len(entries) + 1:02d}",
                "packet_id": PACKET_ID,
                "sequence": len(entries) + 1,
                "evidence_type": evidence_type,
                "status": status,
                "details": deepcopy(details or {}),
                "simulated": True,
                "append_only": True,
            }
        )

    append(
        "on_request",
        observation["on_response"],
        {"event": ON_EVENT, "attempt": 1},
    )
    append("physical_valve_opening", observation["valve_open"])
    append("observed_water_flow", observation["flow"])
    if observation.get("operator_abort"):
        append("operator_abort", "requested")
    if manual_safe:
        append("manual_isolation", observation["manual_isolation"])
    if off_issued:
        append(
            "off_request",
            observation["off_response"],
            {
                "event": OFF_EVENT,
                "attempt": 1,
                "issued_despite_on_response": observation["on_response"]
                in {"failed", "timeout", "unavailable"},
            },
        )
    else:
        append(
            "off_request",
            observation["off_response"],
            {"exception": "manual_isolation_physically_verified_safe_closed"},
        )
    append("physical_valve_closure", observation["valve_closed"])
    append("new_supply_flow_stopped", observation["supply_flow_stopped"])
    append("residual_downstream_drainage", observation["residual_drainage"])

    physically_safe = (
        observation["valve_closed"] == "observed"
        and observation["supply_flow_stopped"] == "observed"
    )
    final_state = (
        "physically_verified_safe_closed" if physically_safe else "unavailable"
    )
    append("final_physical_state", final_state)

    return {
        "packet_id": PACKET_ID,
        "scenario": name,
        "zone_id": ZONE_ID,
        "max_pulse_seconds": MAX_PULSE_SECONDS,
        "on_invoked": on_invoked,
        "off_required": off_required,
        "off_issued": off_issued,
        "retry_count": 0,
        "final_physical_state": final_state,
        "authority": deepcopy(AUTHORITY),
        "evidence": entries,
    }


def rehearse_all():
    return [rehearse_scenario(name) for name in SCENARIOS]
