"""Bridge report confirmation of camp commands, never proof of water delivery."""
from modules.telemetry.rootline_command_acceptance import accepted, command_execution, digest, moment, route_valid

CONTRACT = "rootline_camp_controller_confirmation.v1"


def camp_command(value):
    return (command_execution(value) and not value.get("auxiliary_device_id")
        and value.get("zone_id") in {"A12345", "B12345", "C12345", "E12345"})


def report_after_command(value, observation, *, now):
    """Use the original exact MQTT report clock, never the HTTP/read clock."""
    if not camp_command(value) or not accepted(value.get("command_on_receipt"), value, "ON"):
        return None
    if not route_valid(observation, device_id=value["device_id"], channel=value["channel"], now=now):
        return None
    route = observation.get("command_route", observation)
    rows = [row for row in route["channels"] if row["channel"] == value["channel"]]
    report = rows[0].get("controller_report") if len(rows) == 1 else None
    if not isinstance(report, dict):
        return None
    attempted = moment(value["command_on_receipt"].get("command_attempted_at"))
    at = moment(report.get("reported_at"))
    topic = f"cube2ha/switch/{value['device_id']}/toggle_{value['channel']}/state"
    if (report.get("source") != "home_assistant_mqtt_subscription"
            or report.get("entity_id") != value["command_on_receipt"].get("entity_id")
            or report.get("topic") != topic or report.get("retain") is not False
            or report.get("state") not in {"ON", "OFF"}
            or at is None or attempted is None or not attempted < at <= now
            or at > moment(route["route_checked_at"])):
        return None
    return dict(report)


def confirmation(value, observation, *, now):
    report = report_after_command(value, observation, now=now)
    if report is None or report["state"] != "ON":
        return None
    result = {"contract_version": CONTRACT, "execution_id": value["execution_id"],
        "on_receipt_sha256": value["command_on_receipt"]["receipt_sha256"],
        "report": report, "route_evidence": observation, "confirmed_at": now.isoformat()}
    result["confirmation_sha256"] = digest(result)
    return result


def confirmed(value):
    proof = value.get("controller_confirmation") if isinstance(value, dict) else None
    if not isinstance(proof, dict) or proof.get("contract_version") != CONTRACT:
        return False
    at = moment(proof.get("confirmed_at"))
    if at is None or proof.get("execution_id") != value.get("execution_id"):
        return False
    expected = confirmation(value, proof.get("route_evidence") or {}, now=at)
    return expected is not None and expected == proof


def historical_command_interval(value):
    """Display-only legacy receipt interval; never running/completion credit."""
    from modules.telemetry.rootline_command_acceptance import duty_closed
    if (not camp_command(value) or value.get("controller_confirmation_required") is True
            or not duty_closed(value) or not accepted(value.get("command_on_receipt"), value, "ON")):
        return None
    start = moment(value["command_on_receipt"]["accepted_at"])
    stop = moment(value["command_off_receipt"]["accepted_at"])
    limit = value.get("planned_runtime_seconds")
    if type(limit) is not int or limit <= 0 or stop < start:
        return None
    return min(limit, max(0, int((stop-start).total_seconds())))
