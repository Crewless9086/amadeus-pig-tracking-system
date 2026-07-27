"""Offline contract checks for GateKeeper's bounded BEACON photo route."""

from __future__ import annotations

import hashlib
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


def load_workflow(path: Path = WORKFLOW_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


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
        if params.get("rawContent") != "={{ JSON.stringify($json.raw_update) }}":
            errors.append("media relay does not forward the untouched raw update")
        if params.get("options", {}).get("timeout") != 10000:
            errors.append("media relay timeout is not exactly 10 seconds")
        if relay.get("retryOnFail") is not False or relay.get("onError") != "stopWorkflow":
            errors.append("media relay is not one-attempt/fail-closed")
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
    path: Path = WORKFLOW_PATH,
) -> dict[str, Any]:
    """Build a secret-free packet; activation remains a separate authority."""
    validation = validate_workflow(path)
    workflow = load_workflow(path)
    update_body = {
        "name": workflow["name"],
        "nodes": workflow["nodes"],
        "connections": workflow["connections"],
        "settings": workflow["settings"],
    }
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
