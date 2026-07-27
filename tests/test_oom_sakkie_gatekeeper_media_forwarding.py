import copy
import json
import unittest
from pathlib import Path

from scripts.oom_sakkie_gatekeeper_media_forwarding_contract import (
    MEDIA_NODE,
    SAM_NODE,
    TEXT_NODE,
    build_deployment_packet,
    classify_update,
    load_workflow,
    validate_workflow,
)


OWNER = "owner-123"
CHAT = "owner-123"


def photo_update(**message_overrides):
    message = {
        "message_id": 22,
        "from": {"id": OWNER, "first_name": "Owner"},
        "chat": {"id": CHAT, "type": "private"},
        "caption": "A short farm explanation",
        "photo": [
            {"file_id": "small-file", "file_unique_id": "stable-photo", "width": 90, "height": 90},
            {"file_id": "large-file", "file_unique_id": "stable-photo", "width": 1280, "height": 960},
        ],
    }
    message.update(message_overrides)
    return {"update_id": 101, "message": message}


class GateKeeperMediaForwardingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = load_workflow()
        cls.nodes = {node["name"]: node for node in cls.workflow["nodes"]}

    def test_workflow_contract_is_fail_closed_and_authority_free(self):
        report = validate_workflow()
        self.assertEqual(report["workflow_id"], "s8QaxmqT69Z5mhvE")
        self.assertEqual(report["telegram_trigger_count"], 1)
        self.assertEqual(report["automatic_retries"], 0)
        self.assertFalse(any(report["authority"].values()))

    def test_ordinary_text_still_uses_existing_route(self):
        update = {
            "update_id": 1,
            "message": {
                "message_id": 2,
                "from": {"id": OWNER},
                "chat": {"id": CHAT, "type": "private"},
                "text": "How are things?",
            },
        }
        self.assertEqual(
            classify_update(update, authenticated=True, expected_user=OWNER, expected_chat=CHAT),
            "ordinary",
        )
        switch = self.workflow["connections"]["Switch - BEACON Media Intake"]["main"]
        self.assertEqual(switch[1][0]["node"], "Switch - Telegram Update Type")
        self.assertIn(TEXT_NODE, self.nodes)

    def test_sam_callback_route_is_unchanged(self):
        callback_switch = self.workflow["connections"][
            "Switch - Route Telegram Callback Type"
        ]["main"]
        self.assertEqual(callback_switch[3][0]["node"], SAM_NODE)
        self.assertEqual(
            self.nodes[SAM_NODE]["parameters"]["rawContent"],
            "={{ JSON.stringify($json.raw_update) }}",
        )

    def test_allowlisted_private_photo_reaches_only_beacon_handler(self):
        update = photo_update()
        self.assertEqual(
            classify_update(update, authenticated=True, expected_user=OWNER, expected_chat=CHAT),
            "beacon_single_photo",
        )
        outputs = self.workflow["connections"]["Switch - BEACON Media Intake"]["main"]
        self.assertEqual([edge["node"] for edge in outputs[0]], [MEDIA_NODE])
        self.assertEqual(self.workflow["connections"][MEDIA_NODE]["main"], [[]])
        self.assertEqual(
            self.nodes[MEDIA_NODE]["parameters"]["rawContent"],
            "={{ JSON.stringify($json.raw_update) }}",
        )

    def test_unauthorized_and_wrong_chat_media_fail_closed(self):
        self.assertEqual(
            classify_update(photo_update(), authenticated=False, expected_user=OWNER, expected_chat=CHAT),
            "unauthorized",
        )
        wrong_chat = photo_update(chat={"id": "other", "type": "private"})
        self.assertEqual(
            classify_update(wrong_chat, authenticated=True, expected_user=OWNER, expected_chat=CHAT),
            "media_rejected",
        )
        group = photo_update(chat={"id": CHAT, "type": "group"})
        self.assertEqual(
            classify_update(group, authenticated=True, expected_user=OWNER, expected_chat=CHAT),
            "media_rejected",
        )

    def test_forwarded_malformed_and_unsupported_media_fail_closed(self):
        cases = [
            photo_update(forward_origin={"type": "user"}),
            photo_update(photo=[{"file_id": "", "file_unique_id": ""}]),
            photo_update(photo=[], video={"file_id": "video"}),
            photo_update(photo=[], document={"file_id": "document"}),
            {"update_id": "bad", "message": photo_update()["message"]},
        ]
        for update in cases:
            with self.subTest(update=update):
                self.assertEqual(
                    classify_update(
                        update, authenticated=True, expected_user=OWNER, expected_chat=CHAT
                    ),
                    "media_rejected",
                )

    def test_album_is_unavailable_during_single_photo_canary(self):
        album = photo_update(media_group_id="album-1")
        self.assertEqual(
            classify_update(album, authenticated=True, expected_user=OWNER, expected_chat=CHAT),
            "media_rejected",
        )

    def test_backend_failure_cannot_fall_through_or_send_extra_reply(self):
        relay = self.nodes[MEDIA_NODE]
        self.assertFalse(relay["retryOnFail"])
        self.assertEqual(relay["onError"], "stopWorkflow")
        self.assertEqual(relay["parameters"]["options"]["timeout"], 10000)
        self.assertEqual(self.workflow["connections"][MEDIA_NODE]["main"], [[]])
        telegram_nodes = [
            node["name"]
            for node in self.workflow["nodes"]
            if node["type"] == "n8n-nodes-base.telegram"
        ]
        self.assertNotIn(MEDIA_NODE, telegram_nodes)

    def test_replay_identity_is_preserved_for_backend_idempotency(self):
        update = photo_update()
        forwarded = json.loads(json.dumps(update))
        self.assertEqual(forwarded["update_id"], 101)
        self.assertEqual(forwarded["message"]["message_id"], 22)
        self.assertEqual(forwarded["message"]["photo"], update["message"]["photo"])
        self.assertEqual(forwarded["message"]["caption"], "A short farm explanation")
        self.assertEqual(
            classify_update(forwarded, authenticated=True, expected_user=OWNER, expected_chat=CHAT),
            "beacon_single_photo",
        )
        self.assertEqual(forwarded, update)

    def test_no_sensitive_literal_or_second_webhook_is_added(self):
        raw = Path(
            "docs/04-n8n/workflows/2 - The GateKeeper/workflow.json"
        ).read_text(encoding="utf-8-sig")
        self.assertEqual(
            sum(node["type"] == "n8n-nodes-base.telegramTrigger" for node in self.workflow["nodes"]),
            1,
        )
        self.assertNotIn(OWNER, raw)
        self.assertNotIn("small-file", raw)
        self.assertNotIn("large-file", raw)
        self.assertNotIn("access_token=", raw.lower())

    def test_conflicting_envelope_never_becomes_ordinary_text(self):
        changed = copy.deepcopy(photo_update())
        changed["message"]["media_group_id"] = "group"
        self.assertNotEqual(
            classify_update(changed, authenticated=True, expected_user=OWNER, expected_chat=CHAT),
            "ordinary",
        )

    def test_deployment_packet_is_secret_free_and_does_not_activate(self):
        packet = build_deployment_packet(
            render_deployment_id="dep-safe", render_revision="a" * 40
        )
        self.assertFalse(packet["execution"]["activate_workflow"])
        self.assertFalse(packet["execution"]["register_second_webhook"])
        self.assertFalse(packet["execution"]["consume_canary"])
        self.assertEqual(packet["execution"]["automatic_retries"], 0)
        self.assertFalse(any(packet["authority"].values()))
        serialized = json.dumps(packet)
        self.assertNotIn("owner-123", serialized)
        self.assertNotIn("secret-token", serialized)


if __name__ == "__main__":
    unittest.main()
