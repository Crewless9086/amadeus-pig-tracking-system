import unittest
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from modules.oom_sakkie.telegram_gateway import (
    _send_owner_task_telegram,
    handle_telegram_gateway_message,
    telegram_gateway_policy,
)


ENV={
    "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED":"1",
    "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"g"*40,
    "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"42",
    "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN":"secret-bot-token",
}
HEADERS={"Authorization":"Bearer "+"g"*40}
PHOTO={"update_id":1,"message":{"message_id":3157,"date":1785603680,
    "from":{"id":42},"chat":{"id":42,"type":"private"},
    "media_group_id":"album","photo":[{"file_id":"f","file_unique_id":"u","file_size":4}]}}


class OwnerTaskGatewayTests(unittest.TestCase):
    class EventStore:
        def __init__(self):
            self.rows=[]; self.lock=threading.Lock()
        def __call__(self, action, mission_id, payload):
            with self.lock:
                if action == "load":
                    return [row for row in self.rows if row.get("card_mission_id") == mission_id]
                if any(row.get("event_id") == payload.get("event_id") for row in self.rows):
                    return {"success":True,"created":False}
                self.rows.append(dict(payload)); return {"success":True,"created":True}

    @patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input")
    @patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
    @patch("modules.oom_sakkie.telegram_gateway.handle_telegram_media_intake")
    @patch("modules.oom_sakkie.telegram_gateway.handle_message")
    def test_authenticated_owner_media_uses_typed_intake_before_generic_context(
            self,mock_message,mock_media,mock_delivery,mock_task):
        mock_media.side_effect=lambda *args,**kwargs: ({"success":True,
            "status":"media_intake_stored_private_review_pending",
            "receipt_text":"BEACON started this private album. Reply /beacon-complete ABC.",
            "receipt_mission_id":"BEACON-INTAKE-GROUP-ONE"},201)
        mock_delivery.return_value={"success":True,"status":"family_message_delivered",
            "telegram_sends":1,"telegram_edits":0,"telegram_message_id":"4001"}
        result,status=handle_telegram_gateway_message(PHOTO,headers=HEADERS,environ=ENV)
        self.assertEqual((status,result["status"]),(201,"media_intake_stored_private_review_pending"))
        self.assertEqual(result["reply_transport"],"family_message_lifecycle")
        self.assertTrue(result["sends_telegram"])
        mock_media.assert_called_once();mock_delivery.assert_called_once()
        mock_task.assert_not_called();mock_message.assert_not_called()

    @patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input")
    @patch("modules.oom_sakkie.telegram_gateway.handle_telegram_media_intake")
    def test_concurrent_album_members_create_one_provider_receipt(
            self,mock_media,mock_task):
        mock_media.side_effect=lambda *args,**kwargs: ({"success":True,
            "status":"media_intake_stored_private_review_pending",
            "receipt_text":"BEACON started this private album. Reply /beacon-complete ABC.",
            "receipt_mission_id":"BEACON-INTAKE-GROUP-ONE"},201)
        store=self.EventStore(); sends=[]; send_lock=threading.Lock()
        def sender(chat_id,text,source):
            with send_lock:
                sends.append((chat_id,text))
            return {"success":True,"telegram_message_id":"4001",
                    "provider_timestamp":"2026-08-15T09:30:00+00:00"}
        second=json.loads(json.dumps(PHOTO)); second["update_id"]=2
        second["message"]["message_id"]=3158
        second["message"]["photo"][0]["file_unique_id"]="u2"
        with patch("modules.oom_sakkie.family_message_lifecycle._event_store",store), \
             patch("modules.oom_sakkie.telegram_gateway._send_owner_task_telegram",sender):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda payload: handle_telegram_gateway_message(
                    payload,headers=HEADERS,environ=ENV),(PHOTO,second)))
            replay=handle_telegram_gateway_message(PHOTO,headers=HEADERS,environ=ENV)
        self.assertEqual(len(sends),1)
        self.assertEqual(sum(result[0]["delivery"]["telegram_sends"] for result in results),1)
        self.assertEqual(replay[0]["delivery"]["telegram_sends"],0)
        mock_task.assert_not_called()

    @patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input")
    @patch("modules.oom_sakkie.telegram_gateway.complete_telegram_album")
    @patch("modules.oom_sakkie.telegram_gateway.handle_telegram_media_intake")
    def test_bound_recovery_completes_by_editing_receipt_once_and_replay_is_silent(
            self,mock_media,mock_complete,mock_task):
        mock_media.side_effect=lambda *args,**kwargs: ({"success":True,
            "status":"media_intake_stored_private_review_pending",
            "receipt_text":"BEACON started this private album. Reply /beacon-complete ABC.",
            "receipt_mission_id":"BEACON-INTAKE-GROUP-ONE",
            "completion_code":"ABC"},201)
        mock_complete.return_value=({"success":True,"status":"media_group_completed",
            "intake_group_id":"BEACON-INTAKE-GROUP-ONE",
            "received_count":4,"attention_count":0},200)
        recovery=json.loads(json.dumps(PHOTO))
        recovery["update_id"]=4
        recovery["message"]["message_id"]=3160
        recovery["message"]["photo"][0]["file_unique_id"]="u4"
        recovery["beacon_media_recovery"]={"token":"r"*40,
            "media_group_id":"album","owner_context":"Molly; litter size eight; born 11 August 2026",
            "complete_album":True}
        store=self.EventStore(); sends=[]; edits=[]
        def sender(chat_id,text,source):
            sends.append((chat_id,text))
            return {"success":True,"telegram_message_id":"4001",
                    "provider_timestamp":"2026-08-15T09:30:00+00:00"}
        def editor(chat_id,message_id,text,reply_markup=None):
            edits.append((chat_id,message_id,text,reply_markup))
            return {"success":True,"telegram_message_id":message_id}
        with patch("modules.oom_sakkie.family_message_lifecycle._event_store",store), \
             patch("modules.oom_sakkie.telegram_gateway._send_owner_task_telegram",sender), \
             patch("modules.oom_sakkie.family_message_lifecycle._edit_telegram",editor):
            receipt=handle_telegram_gateway_message(PHOTO,headers=HEADERS,environ=ENV)
            first=handle_telegram_gateway_message(recovery,headers=HEADERS,environ=ENV)
            replay=handle_telegram_gateway_message(recovery,headers=HEADERS,environ=ENV)
        self.assertEqual((receipt[1],first[1],len(sends),len(edits)),(201,201,1,1))
        self.assertEqual(receipt[0]["delivery"]["telegram_sends"],1)
        self.assertEqual(first[0]["delivery"]["telegram_sends"],0)
        self.assertEqual(first[0]["delivery"]["telegram_edits"],1)
        self.assertEqual(replay[0]["delivery"]["telegram_sends"],0)
        self.assertEqual(replay[0]["delivery"]["telegram_edits"],0)
        self.assertEqual(edits[0][1],"4001")
        self.assertEqual(edits[0][3],{"inline_keyboard":[]})
        self.assertEqual(mock_complete.call_count,2)
        mock_task.assert_not_called()

    @patch("modules.sales.sam_live_stock_launch_control._telegram_api")
    def test_owner_task_sender_reuses_existing_bot_and_requires_provider_identity(self,mock_api):
        mock_api.return_value={"ok":True,"result":{"message_id":4001}}
        source={**ENV,"OOM_SAKKIE_TELEGRAM_BOT_TOKEN":"different-disabled-direct-token"}
        result=_send_owner_task_telegram("42","<b>done</b>",source)
        self.assertTrue(result["success"]);self.assertEqual(result["telegram_message_id"],"4001")
        self.assertEqual(mock_api.call_args.args[0],"secret-bot-token")
        packet=mock_api.call_args.args[2]
        self.assertEqual((packet["chat_id"],packet["parse_mode"]),("42","HTML"))
        self.assertNotIn("secret-bot-token",str(result))

    @patch("modules.sales.sam_live_stock_launch_control._telegram_api")
    def test_missing_provider_identity_never_counts_as_delivery(self,mock_api):
        mock_api.return_value={"ok":True,"result":{}}
        result=_send_owner_task_telegram("42","done",ENV)
        self.assertFalse(result["success"]);self.assertEqual(result["telegram_message_id"],"")

    @patch("modules.sales.sam_live_stock_launch_control._telegram_api")
    def test_owner_task_sender_uses_canonical_oom_bot_when_sam_bot_is_absent(self,mock_api):
        mock_api.return_value={"ok":True,"result":{"message_id":4002}}
        source={key:value for key,value in ENV.items()
                if key != "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN"}
        source["OOM_SAKKIE_TELEGRAM_BOT_TOKEN"]="oom-sakkie-bot-token"
        result=_send_owner_task_telegram("42","question",source)
        self.assertTrue(result["success"])
        self.assertEqual(result["telegram_message_id"],"4002")
        self.assertEqual(mock_api.call_args.args[0],"oom-sakkie-bot-token")
        self.assertNotIn("oom-sakkie-bot-token",str(result))

    def test_policy_reports_oom_bot_fallback_send_authority(self):
        source={key:value for key,value in ENV.items()
                if key != "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN"}
        source["OOM_SAKKIE_TELEGRAM_BOT_TOKEN"]="oom-sakkie-bot-token"
        policy=telegram_gateway_policy(source)
        self.assertTrue(policy["owner_task_lifecycle"]["enabled"])
        self.assertTrue(policy["owner_task_lifecycle"]["sends_telegram"])
        self.assertNotIn("oom-sakkie-bot-token",str(policy))

    def test_gatekeeper_reuses_single_trigger_and_active_gateway_for_owner_request_media(self):
        workflow=json.loads(Path("docs/04-n8n/workflows/2 - The GateKeeper/workflow.json").read_text(encoding="utf-8-sig"))
        nodes={node["name"]:node for node in workflow["nodes"]}
        relay=nodes["Relay Owner Request Media to Gateway"]
        self.assertEqual(relay["parameters"]["url"],
            "https://amadeus-pig-tracking-system.onrender.com/api/oom-sakkie/channels/telegram/message")
        headers=relay["parameters"]["headerParameters"]["parameters"]
        self.assertEqual(headers[0]["name"],"X-Oom-Sakkie-Telegram-Token")
        self.assertIn("OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN",headers[0]["value"])
        self.assertEqual(sum(node.get("type")=="n8n-nodes-base.telegramTrigger" for node in workflow["nodes"]),1)
        outputs=workflow["connections"]["Switch - BEACON Media Intake"]["main"]
        self.assertEqual(outputs[2],[])
        self.assertEqual(outputs[3][0]["node"],"Relay Owner Request Media to Gateway")


if __name__=="__main__": unittest.main()
