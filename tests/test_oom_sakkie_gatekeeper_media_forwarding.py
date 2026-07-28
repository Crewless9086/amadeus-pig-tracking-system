import copy
import json
import unittest
from pathlib import Path

from scripts.oom_sakkie_gatekeeper_media_forwarding_contract import (
    MEDIA_NODE,
    SAM_NODE,
    TEXT_NODE,
    build_n8n_workflow_put_payload,
    build_n8n_workflow_update,
    build_deployment_packet,
    canonicalize_n8n_workflow,
    classify_update,
    load_workflow,
    n8n_workflow_semantic_sha256,
    n8n_workflows_semantically_equal,
    reconcile_n8n_variable_create,
    reconcile_n8n_variable_pair,
    validate_workflow,
    validate_n8n_workflow_update,
    variable_value_fingerprint,
    verify_n8n_variable_readback,
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

    def _production_live(self):
        live = copy.deepcopy(self.workflow)
        old_name = "Call '2.0 - OOM SAKKIE - Amadeus Assistant Agent'"
        new_name = "Call '2.0B - Oom Sakkie Backend Read-Only Relay'"
        live["settings"] = {"binaryMode": "default", "executionOrder": "v1"}
        live["nodes"] = [
            node
            for node in live["nodes"]
            if node["name"]
            not in {
                "Code - Gate BEACON Single Photo",
                "Switch - BEACON Media Intake",
                MEDIA_NODE,
            }
        ]
        for node in live["nodes"]:
            if node["name"] == old_name:
                node["name"] = new_name
                node["parameters"]["url"] = "https://example.invalid/2.0b"
        live["connections"].pop("Code - Gate BEACON Single Photo")
        live["connections"].pop("Switch - BEACON Media Intake")
        live["connections"].pop(MEDIA_NODE)
        live["connections"]["Security Check"]["main"][1] = [
            {
                "node": "Switch - Telegram Update Type",
                "type": "main",
                "index": 0,
            }
        ]
        for spec in live["connections"].values():
            for output in spec.get("main", []):
                for edge in output:
                    if edge.get("node") == old_name:
                        edge["node"] = new_name
        return live

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
        live = self._production_live()
        packet = build_deployment_packet(
            render_deployment_id="dep-safe",
            render_revision="a" * 40,
            live_workflow=live,
        )
        self.assertFalse(packet["execution"]["activate_workflow"])
        self.assertFalse(packet["execution"]["register_second_webhook"])
        self.assertFalse(packet["execution"]["consume_canary"])
        self.assertEqual(packet["execution"]["automatic_retries"], 0)
        self.assertFalse(any(packet["authority"].values()))
        serialized = json.dumps(packet)
        self.assertNotIn("owner-123", serialized)
        self.assertNotIn("secret-token", serialized)

    def test_update_payload_uses_exact_installed_api_shape(self):
        live = self._production_live()
        live.update(
            {
                "id": "read-only",
                "active": True,
                "versionId": "read-only",
                "updatedAt": "read-only",
            }
        )
        payload = build_n8n_workflow_update(
            live_workflow=live, reviewed_workflow=self.workflow
        )
        self.assertEqual(
            set(payload), {"name", "nodes", "connections", "settings"}
        )
        self.assertEqual(
            payload["settings"],
            {"executionOrder": "v1"},
        )
        self.assertNotIn("binaryMode", payload["settings"])
        self.assertFalse(set(payload) & {"id", "active", "versionId", "updatedAt"})
        by_name = {node["name"]: node for node in payload["nodes"]}
        self.assertIn("Call '2.0B - Oom Sakkie Backend Read-Only Relay'", by_name)
        self.assertNotIn("Call '2.0 - OOM SAKKIE - Amadeus Assistant Agent'", by_name)
        self.assertEqual(
            by_name["Call '2.0B - Oom Sakkie Backend Read-Only Relay'"],
            next(
                node
                for node in live["nodes"]
                if node["name"]
                == "Call '2.0B - Oom Sakkie Backend Read-Only Relay'"
            ),
        )
        self.assertEqual(
            payload["connections"]["Security Check"]["main"][0],
            live["connections"]["Security Check"]["main"][0],
        )
        self.assertEqual(
            payload["connections"]["Security Check"]["main"][1][0]["node"],
            "Code - Gate BEACON Single Photo",
        )
        self.assertEqual(
            payload["connections"]["Relay SAM Callback to Backend"],
            live["connections"]["Relay SAM Callback to Backend"],
        )

    def test_repository_only_execution_settings_are_not_sent(self):
        live = self._production_live()
        payload = build_n8n_workflow_update(
            live_workflow=live, reviewed_workflow=self.workflow
        )
        for key in (
            "binaryMode",
            "saveDataErrorExecution",
            "saveDataSuccessExecution",
            "saveExecutionProgress",
            "saveManualExecutions",
        ):
            self.assertNotIn(key, payload["settings"])

    def test_get_and_put_safe_workflows_share_one_semantic_hash(self):
        live = self._production_live()
        put_payload = build_n8n_workflow_put_payload(live)
        self.assertEqual(put_payload["settings"], {"executionOrder": "v1"})
        self.assertNotIn("binaryMode", put_payload["settings"])
        self.assertTrue(n8n_workflows_semantically_equal(live, put_payload))
        self.assertEqual(
            n8n_workflow_semantic_sha256(live),
            n8n_workflow_semantic_sha256(put_payload),
        )

    def test_provider_read_only_fields_do_not_change_semantics(self):
        live = self._production_live()
        provider_get = copy.deepcopy(live)
        provider_get.update(
            {
                "id": "provider-id",
                "active": True,
                "versionId": "provider-version",
                "updatedAt": "provider-time",
                "tags": [],
            }
        )
        self.assertEqual(
            canonicalize_n8n_workflow(provider_get),
            build_n8n_workflow_put_payload(live),
        )

    def test_meaningful_workflow_drift_changes_semantics(self):
        live = self._production_live()
        mutations = []

        changed_node = copy.deepcopy(live)
        changed_node["nodes"][0]["name"] = "Changed trigger"
        mutations.append(changed_node)

        changed_connection = copy.deepcopy(live)
        changed_connection["connections"]["Security Check"]["main"][1][0][
            "node"
        ] = "Changed route"
        mutations.append(changed_connection)

        extra_trigger = copy.deepcopy(live)
        trigger = next(
            node
            for node in extra_trigger["nodes"]
            if node["type"] == "n8n-nodes-base.telegramTrigger"
        )
        second_trigger = copy.deepcopy(trigger)
        second_trigger["name"] = "Second Telegram Trigger"
        second_trigger["id"] = "second-trigger"
        extra_trigger["nodes"].append(second_trigger)
        mutations.append(extra_trigger)

        changed_setting = copy.deepcopy(live)
        changed_setting["settings"]["executionOrder"] = "v0"
        mutations.append(changed_setting)

        for candidate in mutations:
            with self.subTest(candidate=candidate["nodes"][0]["name"]):
                self.assertFalse(n8n_workflows_semantically_equal(live, candidate))
                self.assertNotEqual(
                    n8n_workflow_semantic_sha256(live),
                    n8n_workflow_semantic_sha256(candidate),
                )

    def test_rollback_put_and_get_restore_exact_contained_semantics(self):
        contained_get = self._production_live()
        installed_put = build_n8n_workflow_update(
            live_workflow=contained_get, reviewed_workflow=self.workflow
        )
        installed_get = copy.deepcopy(installed_put)
        installed_get["settings"]["binaryMode"] = "default"
        installed_get["active"] = True
        self.assertTrue(
            n8n_workflows_semantically_equal(installed_put, installed_get)
        )

        rollback_put = build_n8n_workflow_put_payload(contained_get)
        rollback_get = copy.deepcopy(rollback_put)
        rollback_get["settings"]["binaryMode"] = "default"
        rollback_get["active"] = True
        self.assertEqual(set(rollback_put), {"name", "nodes", "connections", "settings"})
        self.assertEqual(rollback_put["settings"], {"executionOrder": "v1"})
        self.assertTrue(
            n8n_workflows_semantically_equal(contained_get, rollback_get)
        )
        self.assertEqual(
            n8n_workflow_semantic_sha256(contained_get),
            n8n_workflow_semantic_sha256(rollback_get),
        )

    def test_extra_missing_stale_read_only_and_unsupported_fields_fail_closed(self):
        live = self._production_live()
        payload = build_n8n_workflow_update(
            live_workflow=live, reviewed_workflow=self.workflow
        )
        cases = []
        extra = copy.deepcopy(payload)
        extra["unexpected"] = True
        cases.append(extra)
        missing = copy.deepcopy(payload)
        del missing["connections"]
        cases.append(missing)
        stale = copy.deepcopy(payload)
        stale["name"] = "stale"
        cases.append(stale)
        read_only = copy.deepcopy(payload)
        read_only["active"] = True
        cases.append(read_only)
        unsupported = copy.deepcopy(payload)
        unsupported["settings"]["saveManualExecutions"] = False
        cases.append(unsupported)
        for candidate in cases:
            with self.subTest(keys=sorted(candidate)):
                with self.assertRaises(ValueError):
                    validate_n8n_workflow_update(
                        candidate,
                        live_workflow=live,
                        reviewed_workflow=self.workflow,
                    )

    def test_missing_or_unsupported_live_settings_fail_closed(self):
        missing = self._production_live()
        missing.pop("settings", None)
        with self.assertRaisesRegex(ValueError, "live_workflow_settings_required"):
            build_n8n_workflow_update(
                live_workflow=missing, reviewed_workflow=self.workflow
            )
        unsupported = self._production_live()
        unsupported["settings"] = {
            "executionOrder": "v1",
            "unsupported": True,
        }
        with self.assertRaisesRegex(ValueError, "live_workflow_setting_unsupported"):
            build_n8n_workflow_update(
                live_workflow=unsupported, reviewed_workflow=self.workflow
            )
        required_missing = self._production_live()
        required_missing["settings"] = {"binaryMode": "default"}
        with self.assertRaisesRegex(
            ValueError, "workflow_canonical_required_setting_missing"
        ):
            build_n8n_workflow_update(
                live_workflow=required_missing, reviewed_workflow=self.workflow
            )

    def _fingerprint(self, key, value):
        return variable_value_fingerprint(
            stable_secret="stable-owner-secret", variable_key=key, value=value
        )

    def _pair_kwargs(self):
        owner_key = "BEACON_MEDIA_INTAKE_OWNER_USER_ID"
        chat_key = "BEACON_MEDIA_INTAKE_PRIVATE_CHAT_ID"
        return {
            "owner_key": owner_key,
            "chat_key": chat_key,
            "owner_expected_fingerprint": self._fingerprint(owner_key, "owner"),
            "chat_expected_fingerprint": self._fingerprint(chat_key, "chat"),
        }

    def _verified(self, key, value, variable_id):
        return {
            "status": "verified",
            "variable_key": key,
            "variable_id": variable_id,
            "value_fingerprint": self._fingerprint(key, value),
        }

    def test_observed_wrapped_create_response_uses_authoritative_readback(self):
        key = "BEACON_MEDIA_INTAKE_OWNER_USER_ID"
        result = reconcile_n8n_variable_create(
            create_http_status=201,
            create_response={"data": {"id": "var-1", "key": key}},
            read_payload={"data": [{"id": "var-1", "key": key, "value": "owner"}]},
            variable_key=key,
            expected_fingerprint=self._fingerprint(key, "owner"),
            stable_secret="stable-owner-secret",
        )
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["create_response_shape"], "object:data")
        self.assertFalse(result["rollback_required"])

    def test_successful_readback_is_bound_to_identity_and_fingerprint(self):
        key = "BEACON_MEDIA_INTAKE_PRIVATE_CHAT_ID"
        result = verify_n8n_variable_readback(
            {"data": [{"id": "var-chat", "key": key, "value": "chat"}]},
            variable_key=key,
            expected_fingerprint=self._fingerprint(key, "chat"),
            stable_secret="stable-owner-secret",
        )
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["variable_id"], "var-chat")
        self.assertNotIn("chat", {k: v for k, v in result.items() if k != "variable_id"})

    def test_ambiguous_create_without_persisted_variable_fails_closed(self):
        key = "BEACON_MEDIA_INTAKE_OWNER_USER_ID"
        result = reconcile_n8n_variable_create(
            create_http_status=201,
            create_response={},
            read_payload={"data": []},
            variable_key=key,
            expected_fingerprint=self._fingerprint(key, "owner"),
            stable_secret="stable-owner-secret",
        )
        self.assertEqual(result["status"], "missing")
        self.assertFalse(result["rollback_required"])

    def test_persisted_mismatched_value_is_conflict_and_requires_rollback(self):
        key = "BEACON_MEDIA_INTAKE_OWNER_USER_ID"
        result = reconcile_n8n_variable_create(
            create_http_status=201,
            create_response={"data": {}},
            read_payload={"data": [{"id": "var-1", "key": key, "value": "other"}]},
            variable_key=key,
            expected_fingerprint=self._fingerprint(key, "owner"),
            stable_secret="stable-owner-secret",
        )
        self.assertEqual(result["status"], "conflict")
        self.assertTrue(result["rollback_required"])
        self.assertNotIn("other", json.dumps(result))

    def test_partial_pair_blocks_workflow_and_rolls_back_only_created_identity(self):
        pair = reconcile_n8n_variable_pair(
            owner_result=self._verified(
                "BEACON_MEDIA_INTAKE_OWNER_USER_ID", "owner", "var-owner"
            ),
            chat_result={"status": "missing"},
            created_this_attempt={"owner"},
            **self._pair_kwargs(),
        )
        self.assertEqual(pair["status"], "partial_or_conflicting")
        self.assertFalse(pair["workflow_update_permitted"])
        self.assertEqual(pair["rollback_variable_ids"], ["var-owner"])

    def test_existing_matching_pair_is_idempotent_and_permits_workflow(self):
        pair = reconcile_n8n_variable_pair(
            owner_result=self._verified(
                "BEACON_MEDIA_INTAKE_OWNER_USER_ID", "owner", "existing-owner"
            ),
            chat_result=self._verified(
                "BEACON_MEDIA_INTAKE_PRIVATE_CHAT_ID", "chat", "existing-chat"
            ),
            created_this_attempt=set(),
            **self._pair_kwargs(),
        )
        self.assertEqual(pair["status"], "verified")
        self.assertTrue(pair["workflow_update_permitted"])
        self.assertEqual(pair["rollback_variable_ids"], [])

    def test_authoritative_create_results_form_exact_verified_pair(self):
        pair_kwargs = self._pair_kwargs()
        owner_result = reconcile_n8n_variable_create(
            create_http_status=201,
            create_response={"data": {"id": "owner-id"}},
            read_payload={
                "data": [
                    {
                        "id": "owner-id",
                        "key": pair_kwargs["owner_key"],
                        "value": "owner",
                    }
                ]
            },
            variable_key=pair_kwargs["owner_key"],
            expected_fingerprint=pair_kwargs["owner_expected_fingerprint"],
            stable_secret="stable-owner-secret",
        )
        chat_result = reconcile_n8n_variable_create(
            create_http_status=201,
            create_response={"data": {"id": "chat-id"}},
            read_payload={
                "data": [
                    {
                        "id": "chat-id",
                        "key": pair_kwargs["chat_key"],
                        "value": "chat",
                    }
                ]
            },
            variable_key=pair_kwargs["chat_key"],
            expected_fingerprint=pair_kwargs["chat_expected_fingerprint"],
            stable_secret="stable-owner-secret",
        )

        pair = reconcile_n8n_variable_pair(
            owner_result=owner_result,
            chat_result=chat_result,
            created_this_attempt={"owner", "private_chat"},
            **pair_kwargs,
        )

        self.assertEqual(pair["status"], "verified")
        self.assertTrue(pair["workflow_update_permitted"])
        self.assertEqual(pair["rollback_variable_ids"], [])

    def test_later_gatekeeper_mismatch_preserves_pair_rollback_contract(self):
        pair = reconcile_n8n_variable_pair(
            owner_result={"status": "conflict", "variable_id": "var-owner"},
            chat_result=self._verified(
                "BEACON_MEDIA_INTAKE_PRIVATE_CHAT_ID", "chat", "var-chat"
            ),
            created_this_attempt={"owner", "private_chat"},
            **self._pair_kwargs(),
        )
        self.assertFalse(pair["workflow_update_permitted"])
        self.assertEqual(
            pair["rollback_variable_ids"], ["var-chat", "var-owner"]
        )

    def test_same_verified_result_cannot_satisfy_both_pair_slots(self):
        result = self._verified(
            "BEACON_MEDIA_INTAKE_OWNER_USER_ID", "owner", "same-id"
        )
        pair = reconcile_n8n_variable_pair(
            owner_result=result,
            chat_result=result,
            created_this_attempt=set(),
            **self._pair_kwargs(),
        )
        self.assertFalse(pair["workflow_update_permitted"])

    def test_swapped_owner_and_chat_results_fail_closed(self):
        pair = reconcile_n8n_variable_pair(
            owner_result=self._verified(
                "BEACON_MEDIA_INTAKE_PRIVATE_CHAT_ID", "chat", "chat-id"
            ),
            chat_result=self._verified(
                "BEACON_MEDIA_INTAKE_OWNER_USER_ID", "owner", "owner-id"
            ),
            created_this_attempt=set(),
            **self._pair_kwargs(),
        )
        self.assertFalse(pair["workflow_update_permitted"])

    def test_duplicate_variable_ids_fail_even_with_distinct_keys(self):
        pair = reconcile_n8n_variable_pair(
            owner_result=self._verified(
                "BEACON_MEDIA_INTAKE_OWNER_USER_ID", "owner", "same-id"
            ),
            chat_result=self._verified(
                "BEACON_MEDIA_INTAKE_PRIVATE_CHAT_ID", "chat", "same-id"
            ),
            created_this_attempt=set(),
            **self._pair_kwargs(),
        )
        self.assertFalse(pair["workflow_update_permitted"])

    def test_malformed_verified_pair_result_fails_closed(self):
        pair = reconcile_n8n_variable_pair(
            owner_result={"status": "verified", "variable_id": "owner-id"},
            chat_result=self._verified(
                "BEACON_MEDIA_INTAKE_PRIVATE_CHAT_ID", "chat", "chat-id"
            ),
            created_this_attempt=set(),
            **self._pair_kwargs(),
        )
        self.assertFalse(pair["workflow_update_permitted"])

    def test_duplicate_readback_rows_are_conflict(self):
        key = "BEACON_MEDIA_INTAKE_OWNER_USER_ID"
        result = verify_n8n_variable_readback(
            {
                "data": [
                    {"id": "one", "key": key, "value": "owner"},
                    {"id": "two", "key": key, "value": "owner"},
                ]
            },
            variable_key=key,
            expected_fingerprint=self._fingerprint(key, "owner"),
            stable_secret="stable-owner-secret",
        )
        self.assertEqual(result["status"], "conflict")

    def test_rejected_create_remains_failed_even_if_readback_exists(self):
        key = "BEACON_MEDIA_INTAKE_OWNER_USER_ID"
        result = reconcile_n8n_variable_create(
            create_http_status=409,
            create_response={"message": "conflict"},
            read_payload={"data": [{"id": "existing", "key": key, "value": "owner"}]},
            variable_key=key,
            expected_fingerprint=self._fingerprint(key, "owner"),
            stable_secret="stable-owner-secret",
        )
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["rollback_required"])


if __name__ == "__main__":
    unittest.main()
