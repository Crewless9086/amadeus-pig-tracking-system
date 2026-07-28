"""Offline contract checks for GateKeeper's bounded BEACON photo route."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any


WORKFLOW_PATH = Path("docs/04-n8n/workflows/2 - The GateKeeper/workflow.json")
DIRECT_WEBHOOK_PATH = "/api/oom-sakkie/channels/telegram/direct-webhook"
MEDIA_NODE = "Relay BEACON Photo to Backend"
TEXT_NODE = "Call '2.0 - OOM SAKKIE - Amadeus Assistant Agent'"
SAM_NODE = "Relay SAM Callback to Backend"
DEPLOYMENT_PACKET_ID = "BEACON-GATEKEEPER-DEPLOYMENT-20260727-01"
NEXT_CANARY_ID = "BEACON-MEDIA-INTAKE-ACTIVATION-CANARY-20260727-02"
VARIABLE_FINGERPRINT_DOMAIN = b"beacon-n8n-variable-readback-v1\0"
WORKFLOW_UPDATE_KEYS = frozenset({"name", "nodes", "connections", "settings"})
SUPPORTED_LIVE_SETTING_KEYS = frozenset({"binaryMode", "executionOrder"})
SUPPORTED_UPDATE_SETTING_KEYS = frozenset({"executionOrder"})
READ_ONLY_WORKFLOW_KEYS = frozenset(
    {
        "active",
        "activeVersion",
        "activeVersionId",
        "createdAt",
        "id",
        "shared",
        "tags",
        "triggerCount",
        "updatedAt",
        "versionCounter",
        "versionId",
    }
)
NORMALIZE_NODE = "Code - Normalize Telegram Update"
MEDIA_GATE_NODE = "Code - Gate BEACON Single Photo"
MEDIA_SWITCH_NODE = "Switch - BEACON Media Intake"
BEACON_ADDED_NODES = frozenset({MEDIA_GATE_NODE, MEDIA_SWITCH_NODE, MEDIA_NODE})
LIVE_ORDINARY_NODE = "Call '2.0B - Oom Sakkie Backend Read-Only Relay'"


def load_workflow(path: Path = WORKFLOW_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def canonicalize_n8n_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    """Return the shared semantic and PUT-safe n8n workflow representation."""
    if not isinstance(workflow, dict):
        raise ValueError("workflow_object_required")
    missing = [key for key in WORKFLOW_UPDATE_KEYS if key not in workflow]
    if missing:
        raise ValueError("workflow_canonical_required_field_missing")
    if not isinstance(workflow["name"], str) or not workflow["name"]:
        raise ValueError("workflow_canonical_name_invalid")
    if not isinstance(workflow["nodes"], list) or not workflow["nodes"]:
        raise ValueError("workflow_canonical_nodes_invalid")
    node_names = [
        node.get("name") for node in workflow["nodes"] if isinstance(node, dict)
    ]
    if (
        len(node_names) != len(workflow["nodes"])
        or any(not isinstance(name, str) or not name for name in node_names)
        or len(set(node_names)) != len(node_names)
    ):
        raise ValueError("workflow_canonical_node_identity_conflict")
    if not isinstance(workflow["connections"], dict):
        raise ValueError("workflow_canonical_connections_invalid")
    settings = workflow["settings"]
    if not isinstance(settings, dict):
        raise ValueError("workflow_canonical_settings_invalid")
    if set(settings) - SUPPORTED_LIVE_SETTING_KEYS:
        raise ValueError("workflow_canonical_setting_unsupported")
    if set(settings) & SUPPORTED_UPDATE_SETTING_KEYS != SUPPORTED_UPDATE_SETTING_KEYS:
        raise ValueError("workflow_canonical_required_setting_missing")
    return {
        "name": workflow["name"],
        "nodes": copy.deepcopy(workflow["nodes"]),
        "connections": copy.deepcopy(workflow["connections"]),
        "settings": {
            key: copy.deepcopy(settings[key])
            for key in sorted(SUPPORTED_UPDATE_SETTING_KEYS)
        },
    }


def n8n_workflow_semantic_sha256(workflow: dict[str, Any]) -> str:
    canonical = canonicalize_n8n_workflow(workflow)
    return hashlib.sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def n8n_workflows_semantically_equal(
    expected: dict[str, Any], actual: dict[str, Any]
) -> bool:
    return canonicalize_n8n_workflow(expected) == canonicalize_n8n_workflow(
        actual
    )


def build_n8n_workflow_put_payload(workflow: dict[str, Any]) -> dict[str, Any]:
    """Build an accepted PUT body for installation or exact rollback."""
    return canonicalize_n8n_workflow(workflow)


def build_n8n_workflow_update(
    *,
    live_workflow: dict[str, Any],
    reviewed_workflow: dict[str, Any],
) -> dict[str, Any]:
    """Build the installed public-API payload without copying export-only fields."""
    if not isinstance(live_workflow, dict) or not isinstance(reviewed_workflow, dict):
        raise ValueError("workflow_objects_required")
    missing = [
        key
        for key in ("name", "nodes", "connections")
        if key not in live_workflow or key not in reviewed_workflow
    ]
    if missing:
        raise ValueError("workflow_update_required_field_missing")
    live_settings = live_workflow.get("settings")
    if not isinstance(live_settings, dict):
        raise ValueError("live_workflow_settings_required")
    unsupported_live_settings = set(live_settings) - SUPPORTED_LIVE_SETTING_KEYS
    if unsupported_live_settings:
        raise ValueError("live_workflow_setting_unsupported")

    live_nodes = live_workflow["nodes"]
    reviewed_nodes = reviewed_workflow["nodes"]
    if not isinstance(live_nodes, list) or not isinstance(reviewed_nodes, list):
        raise ValueError("workflow_update_nodes_invalid")
    live_by_name = {
        node.get("name"): node for node in live_nodes if isinstance(node, dict)
    }
    reviewed_by_name = {
        node.get("name"): node for node in reviewed_nodes if isinstance(node, dict)
    }
    if len(live_by_name) != len(live_nodes) or len(reviewed_by_name) != len(
        reviewed_nodes
    ):
        raise ValueError("workflow_node_identity_conflict")
    required_live = {
        NORMALIZE_NODE,
        LIVE_ORDINARY_NODE,
        SAM_NODE,
        "Security Check",
        "Switch - Telegram Update Type",
    }
    if not required_live.issubset(live_by_name):
        raise ValueError("live_workflow_topology_drift")
    if BEACON_ADDED_NODES & set(live_by_name):
        raise ValueError("beacon_media_nodes_already_present")
    if not (BEACON_ADDED_NODES | {NORMALIZE_NODE}).issubset(reviewed_by_name):
        raise ValueError("reviewed_beacon_nodes_missing")
    if sum(
        node.get("type") == "n8n-nodes-base.telegramTrigger"
        for node in live_nodes
    ) != 1:
        raise ValueError("live_telegram_trigger_count_invalid")

    merged_nodes = copy.deepcopy(live_nodes)
    merged_by_name = {node["name"]: node for node in merged_nodes}
    live_normalize = merged_by_name[NORMALIZE_NODE]
    reviewed_normalize = reviewed_by_name[NORMALIZE_NODE]
    live_normalize.setdefault("parameters", {})["jsCode"] = reviewed_normalize[
        "parameters"
    ]["jsCode"]
    reviewed_sam_params = reviewed_by_name[SAM_NODE].get("parameters", {})
    if (
        reviewed_sam_params.get("contentType") != "json"
        or reviewed_sam_params.get("specifyBody") != "json"
        or reviewed_sam_params.get("jsonBody") != "={{ $json.raw_update }}"
        or "rawContent" in reviewed_sam_params
    ):
        raise ValueError("reviewed_sam_json_transport_invalid")
    merged_sam_params = merged_by_name[SAM_NODE].setdefault("parameters", {})
    merged_sam_params.pop("rawContent", None)
    for key in ("contentType", "specifyBody", "jsonBody"):
        merged_sam_params[key] = reviewed_sam_params[key]
    for node in reviewed_nodes:
        if node.get("name") in BEACON_ADDED_NODES:
            merged_nodes.append(copy.deepcopy(node))

    live_connections = live_workflow.get("connections")
    reviewed_connections = reviewed_workflow.get("connections")
    if not isinstance(live_connections, dict) or not isinstance(
        reviewed_connections, dict
    ):
        raise ValueError("workflow_update_connections_invalid")
    merged_connections = copy.deepcopy(live_connections)
    live_security = merged_connections.get("Security Check", {}).get("main")
    reviewed_security = reviewed_connections.get("Security Check", {}).get("main")
    if (
        not isinstance(live_security, list)
        or len(live_security) != 2
        or [edge.get("node") for edge in live_security[1]]
        != ["Switch - Telegram Update Type"]
        or not isinstance(reviewed_security, list)
        or len(reviewed_security) != 2
        or [edge.get("node") for edge in reviewed_security[1]]
        != [MEDIA_GATE_NODE]
    ):
        raise ValueError("security_check_topology_drift")
    merged_connections["Security Check"]["main"][1] = copy.deepcopy(
        reviewed_security[1]
    )
    for source in BEACON_ADDED_NODES:
        if source not in reviewed_connections:
            raise ValueError("reviewed_beacon_connection_missing")
        merged_connections[source] = copy.deepcopy(reviewed_connections[source])

    payload = canonicalize_n8n_workflow({
        "name": live_workflow["name"],
        "nodes": merged_nodes,
        "connections": merged_connections,
        "settings": live_settings,
    })
    validate_n8n_workflow_update(
        payload,
        live_workflow=live_workflow,
        reviewed_workflow=reviewed_workflow,
    )
    return payload


def validate_n8n_workflow_update(
    payload: dict[str, Any],
    *,
    live_workflow: dict[str, Any],
    reviewed_workflow: dict[str, Any],
) -> None:
    """Fail closed on stale/read-only fields or any route-bearing drift."""
    if not isinstance(payload, dict) or set(payload) != WORKFLOW_UPDATE_KEYS:
        raise ValueError("workflow_update_top_level_shape_invalid")
    if set(payload) & READ_ONLY_WORKFLOW_KEYS:
        raise ValueError("workflow_update_read_only_field")
    if not isinstance(payload["name"], str) or not payload["name"]:
        raise ValueError("workflow_update_name_invalid")
    if payload["name"] != live_workflow.get("name"):
        raise ValueError("workflow_update_stale_name")
    if not isinstance(payload["nodes"], list) or not payload["nodes"]:
        raise ValueError("workflow_update_nodes_invalid")
    if not isinstance(payload["connections"], dict):
        raise ValueError("workflow_update_connections_invalid")
    payload_by_name = {node.get("name"): node for node in payload["nodes"]}
    live_by_name = {node.get("name"): node for node in live_workflow["nodes"]}
    reviewed_by_name = {
        node.get("name"): node for node in reviewed_workflow["nodes"]
    }
    for name, live_node in live_by_name.items():
        if name == NORMALIZE_NODE:
            expected = copy.deepcopy(live_node)
            expected.setdefault("parameters", {})["jsCode"] = reviewed_by_name[
                NORMALIZE_NODE
            ]["parameters"]["jsCode"]
            if payload_by_name.get(name) != expected:
                raise ValueError("workflow_update_normalizer_drift")
        elif name == SAM_NODE:
            expected = copy.deepcopy(live_node)
            expected_params = expected.setdefault("parameters", {})
            reviewed_params = reviewed_by_name[SAM_NODE].get("parameters", {})
            expected_params.pop("rawContent", None)
            for key in ("contentType", "specifyBody", "jsonBody"):
                expected_params[key] = reviewed_params[key]
            if payload_by_name.get(name) != expected:
                raise ValueError("workflow_update_sam_json_transport_drift")
        elif payload_by_name.get(name) != live_node:
            raise ValueError("workflow_update_live_node_drift")
    for name in BEACON_ADDED_NODES:
        if payload_by_name.get(name) != reviewed_by_name.get(name):
            raise ValueError("workflow_update_beacon_node_drift")
    if set(payload_by_name) != set(live_by_name) | BEACON_ADDED_NODES:
        raise ValueError("workflow_update_node_scope_expanded")

    payload_connections = payload["connections"]
    live_connections = live_workflow["connections"]
    reviewed_connections = reviewed_workflow["connections"]
    for source, live_connection in live_connections.items():
        if source == "Security Check":
            expected = copy.deepcopy(live_connection)
            expected["main"][1] = copy.deepcopy(
                reviewed_connections["Security Check"]["main"][1]
            )
            if payload_connections.get(source) != expected:
                raise ValueError("workflow_update_security_edge_drift")
        elif payload_connections.get(source) != live_connection:
            raise ValueError("workflow_update_live_connection_drift")
    for source in BEACON_ADDED_NODES:
        if payload_connections.get(source) != reviewed_connections.get(source):
            raise ValueError("workflow_update_beacon_connection_drift")
    if set(payload_connections) != set(live_connections) | BEACON_ADDED_NODES:
        raise ValueError("workflow_update_connection_scope_expanded")
    settings = payload["settings"]
    if not isinstance(settings, dict):
        raise ValueError("workflow_update_settings_invalid")
    if set(settings) != SUPPORTED_UPDATE_SETTING_KEYS:
        raise ValueError("workflow_update_setting_unsupported")
    if settings != {
        key: live_workflow["settings"][key]
        for key in sorted(live_workflow["settings"])
        if key in SUPPORTED_UPDATE_SETTING_KEYS
    }:
        raise ValueError("workflow_update_settings_drift")


def variable_value_fingerprint(
    *, stable_secret: str, variable_key: str, value: str
) -> str:
    if not stable_secret or not variable_key or not value:
        raise ValueError("stable_secret_variable_key_and_value_required")
    return hmac.new(
        stable_secret.encode("utf-8"),
        VARIABLE_FINGERPRINT_DOMAIN
        + variable_key.encode("utf-8")
        + b"\0"
        + value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_n8n_variable_readback(
    payload: Any,
    *,
    variable_key: str,
    expected_fingerprint: str,
    stable_secret: str,
) -> dict[str, Any]:
    """Treat only the authoritative list/read response as persistence proof."""
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {"status": "unavailable", "reason": "read_response_malformed"}
    matches = [
        row
        for row in rows
        if isinstance(row, dict) and str(row.get("key") or "") == variable_key
    ]
    if not matches:
        return {"status": "missing", "reason": "variable_not_persisted"}
    if len(matches) != 1:
        return {"status": "conflict", "reason": "duplicate_variable_identity"}
    row = matches[0]
    variable_id = str(row.get("id") or "")
    value = row.get("value")
    if not variable_id or not isinstance(value, str) or not value:
        return {"status": "unavailable", "reason": "read_identity_or_value_missing"}
    actual_fingerprint = variable_value_fingerprint(
        stable_secret=stable_secret, variable_key=variable_key, value=value
    )
    if not hmac.compare_digest(actual_fingerprint, expected_fingerprint):
        return {
            "status": "conflict",
            "reason": "protected_value_fingerprint_mismatch",
            "variable_id": variable_id,
        }
    return {
        "status": "verified",
        "reason": "authoritative_readback_match",
        "variable_key": variable_key,
        "variable_id": variable_id,
        "value_fingerprint": actual_fingerprint,
    }


def reconcile_n8n_variable_create(
    *,
    create_http_status: int,
    create_response: Any,
    read_payload: Any,
    variable_key: str,
    expected_fingerprint: str,
    stable_secret: str,
) -> dict[str, Any]:
    """Accept response-envelope variation, never response-only persistence."""
    response_shape = (
        "object:" + ",".join(sorted(create_response))
        if isinstance(create_response, dict)
        else type(create_response).__name__
    )
    readback = verify_n8n_variable_readback(
        read_payload,
        variable_key=variable_key,
        expected_fingerprint=expected_fingerprint,
        stable_secret=stable_secret,
    )
    accepted_status = create_http_status in {200, 201, 202, 204}
    if not accepted_status:
        return {
            "status": "failed",
            "reason": "create_http_rejected",
            "create_response_shape": response_shape,
            "rollback_required": readback["status"] != "missing",
        }
    if readback["status"] != "verified":
        return {
            "status": readback["status"],
            "reason": readback["reason"],
            "create_response_shape": response_shape,
            "rollback_required": readback["status"] != "missing",
            **(
                {"variable_id": readback["variable_id"]}
                if readback.get("variable_id")
                else {}
            ),
        }
    return {
        "status": "verified",
        "reason": "create_accepted_and_authoritative_readback_match",
        "create_response_shape": response_shape,
        "variable_key": readback["variable_key"],
        "variable_id": readback["variable_id"],
        "value_fingerprint": readback["value_fingerprint"],
        "rollback_required": False,
    }


def reconcile_n8n_variable_pair(
    *,
    owner_result: dict[str, Any],
    chat_result: dict[str, Any],
    created_this_attempt: set[str],
    owner_key: str,
    chat_key: str,
    owner_expected_fingerprint: str,
    chat_expected_fingerprint: str,
) -> dict[str, Any]:
    results = {"owner": owner_result, "private_chat": chat_result}
    expected = {
        "owner": (owner_key, owner_expected_fingerprint),
        "private_chat": (chat_key, chat_expected_fingerprint),
    }
    identities = [str(result.get("variable_id") or "") for result in results.values()]
    structurally_valid = bool(
        owner_key
        and chat_key
        and owner_key != chat_key
        and all(identities)
        and len(set(identities)) == 2
    )
    verified = structurally_valid and all(
        result.get("status") == "verified"
        and result.get("variable_key") == expected[name][0]
        and isinstance(result.get("value_fingerprint"), str)
        and hmac.compare_digest(
            result["value_fingerprint"], expected[name][1]
        )
        for name, result in results.items()
    )
    if verified:
        return {
            "status": "verified",
            "rollback_variable_ids": [],
            "workflow_update_permitted": True,
        }
    rollback_ids = sorted(
        str(result["variable_id"])
        for name, result in results.items()
        if name in created_this_attempt and result.get("variable_id")
    )
    return {
        "status": "partial_or_conflicting",
        "rollback_variable_ids": rollback_ids,
        "workflow_update_permitted": False,
    }


def classify_update(
    update: dict[str, Any],
    *,
    authenticated: bool,
    expected_user: str,
    expected_chat: str,
) -> str:
    """Mirror the n8n gate without returning or logging sensitive evidence."""
    if not authenticated:
        return "unauthorized"
    message = update.get("message") or {}
    photos = message.get("photo") if isinstance(message.get("photo"), list) else []
    unsupported = any(
        message.get(key)
        for key in ("video", "document", "animation", "audio", "voice", "video_note")
    )
    media_present = bool(photos or unsupported or message.get("media_group_id"))
    if not media_present:
        return "ordinary"
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    private_owner = bool(
        expected_user
        and expected_chat
        and str(sender.get("id") or "") == expected_user
        and str(chat.get("id") or "") == expected_chat
        and chat.get("type") == "private"
    )
    forwarded = any(
        message.get(key)
        for key in (
            "forward_origin",
            "forward_from",
            "forward_from_chat",
            "forward_sender_name",
            "forward_date",
            "sender_chat",
        )
    )
    stable = (
        isinstance(update.get("update_id"), int)
        and isinstance(message.get("message_id"), int)
        and all(
            isinstance(photo.get("file_id"), str)
            and bool(photo["file_id"])
            and isinstance(photo.get("file_unique_id"), str)
            and bool(photo["file_unique_id"])
            for photo in photos
        )
    )
    if private_owner and not forwarded and photos and not unsupported and not message.get(
        "media_group_id"
    ) and stable:
        return "beacon_single_photo"
    return "media_rejected"


def validate_workflow(path: Path = WORKFLOW_PATH) -> dict[str, Any]:
    workflow = load_workflow(path)
    nodes = {node["name"]: node for node in workflow["nodes"]}
    connections = workflow["connections"]
    errors: list[str] = []

    triggers = [
        node for node in workflow["nodes"] if node["type"] == "n8n-nodes-base.telegramTrigger"
    ]
    if len(triggers) != 1:
        errors.append("GateKeeper must remain the single Telegram-trigger workflow")
    if MEDIA_NODE not in nodes or TEXT_NODE not in nodes or SAM_NODE not in nodes:
        errors.append("required media/text/SAM nodes are missing")
    else:
        relay = nodes[MEDIA_NODE]
        params = relay.get("parameters", {})
        if not str(params.get("url", "")).endswith(DIRECT_WEBHOOK_PATH):
            errors.append("media relay does not target the protected direct webhook")
        if (
            params.get("contentType") != "json"
            or params.get("specifyBody") != "json"
            or params.get("jsonBody") != "={{ $json.raw_update }}"
            or "rawContent" in params
        ):
            errors.append("media relay does not forward one structured JSON object")
        if params.get("options", {}).get("timeout") != 10000:
            errors.append("media relay timeout is not exactly 10 seconds")
        if relay.get("retryOnFail") is not False or relay.get("onError") != "stopWorkflow":
            errors.append("media relay is not one-attempt/fail-closed")
        sam_params = nodes[SAM_NODE].get("parameters", {})
        if (
            sam_params.get("contentType") != "json"
            or sam_params.get("specifyBody") != "json"
            or sam_params.get("jsonBody") != "={{ $json.raw_update }}"
            or "rawContent" in sam_params
        ):
            errors.append("SAM relay does not forward one structured JSON object")
        headers = params.get("headerParameters", {}).get("parameters", [])
        expected_header = {
            "name": "X-Telegram-Bot-Api-Secret-Token",
            "value": "={{$vars.OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET}}",
        }
        if headers != [expected_header]:
            errors.append("media relay secret boundary changed")

    authorized = connections.get("Security Check", {}).get("main", [[], []])
    if len(authorized) < 2 or [edge.get("node") for edge in authorized[1]] != [
        "Code - Gate BEACON Single Photo"
    ]:
        errors.append("authorized traffic does not enter the media gate first")
    media_outputs = connections.get("Switch - BEACON Media Intake", {}).get("main", [])
    if len(media_outputs) != 3:
        errors.append("media switch must have forward, ordinary, and rejected outputs")
    else:
        if [edge.get("node") for edge in media_outputs[0]] != [MEDIA_NODE]:
            errors.append("authorized photo is not isolated to the BEACON handler")
        if [edge.get("node") for edge in media_outputs[1]] != [
            "Switch - Telegram Update Type"
        ]:
            errors.append("ordinary routing changed")
        if media_outputs[2]:
            errors.append("rejected media must terminate without a responder")
    if connections.get(MEDIA_NODE, {}).get("main") != [[]]:
        errors.append("backend success/failure must not fall through to text routing")

    settings = workflow.get("settings", {})
    for key in ("saveDataErrorExecution", "saveDataSuccessExecution"):
        if settings.get(key) != "none":
            errors.append(f"{key} could persist sensitive Telegram evidence")
    if settings.get("saveExecutionProgress") is not False:
        errors.append("execution progress persistence must be disabled")

    serialized = json.dumps(workflow, sort_keys=True, ensure_ascii=False)
    forbidden = ("access_token=", "bot_token", "BEACON_MEDIA_INTAKE_OWNER_USER_ID\":")
    if any(value.lower() in serialized.lower() for value in forbidden):
        errors.append("workflow contains persisted credential or configured identity material")

    if errors:
        raise ValueError("; ".join(errors))
    return {
        "workflow_id": workflow["id"],
        "workflow_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "telegram_trigger_count": len(triggers),
        "media_timeout_ms": 10000,
        "automatic_retries": 0,
        "ordinary_text_route_preserved": True,
        "sam_callback_route_preserved": True,
        "authority": {
            "library_acceptance": False,
            "public_use": False,
            "publication": False,
            "meta_call": False,
            "customer_message": False,
            "advertising": False,
            "boost": False,
            "spend": False,
        },
    }


def build_deployment_packet(
    *,
    render_deployment_id: str,
    render_revision: str,
    live_workflow: dict[str, Any],
    path: Path = WORKFLOW_PATH,
) -> dict[str, Any]:
    """Build a secret-free packet; activation remains a separate authority."""
    validation = validate_workflow(path)
    workflow = load_workflow(path)
    update_body = build_n8n_workflow_update(
        live_workflow=live_workflow,
        reviewed_workflow=workflow,
    )
    update_sha = hashlib.sha256(
        json.dumps(
            update_body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()
    packet = {
        "packet_id": DEPLOYMENT_PACKET_ID,
        "packet_version": "beacon_gatekeeper_media_forwarding_v1",
        "workflow_id": validation["workflow_id"],
        "workflow_update_sha256": update_sha,
        "repository_workflow_sha256": validation["workflow_sha256"],
        "required_render_deployment_id": render_deployment_id,
        "required_render_revision": render_revision,
        "next_canary_id": NEXT_CANARY_ID,
        "preconditions": {
            "same_gatekeeper_remains_sole_telegram_webhook_owner": True,
            "backend_direct_webhook_loaded_at_required_revision": True,
            "private_bucket_proven": True,
            "eight_intake_tables_expected_zero": True,
            "owner_user_and_private_chat_variables_configured": True,
            "webhook_secret_configured": True,
            "single_photo_only": True,
            "album_enabled": False,
            "video_enabled": False,
            "historical_import_enabled": False,
        },
        "execution": {
            "n8n_workflow_update_attempts": 1,
            "automatic_retries": 0,
            "activate_workflow": False,
            "register_second_webhook": False,
            "consume_canary": False,
        },
        "authority": validation["authority"]
        | {
            "telegram_gateway_activation": False,
            "media_upload": False,
            "intake_row_creation": False,
            "telegram_receipt": False,
        },
    }
    packet["packet_sha256"] = hashlib.sha256(
        json.dumps(packet, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return packet


if __name__ == "__main__":
    print(json.dumps(validate_workflow(), sort_keys=True))
