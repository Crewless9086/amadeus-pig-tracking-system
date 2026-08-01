import unittest
import json
from pathlib import Path
from unittest.mock import patch

from modules.oom_sakkie.telegram_gateway import (
    _send_owner_task_telegram,
    handle_telegram_gateway_message,
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
    @patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input")
    @patch("modules.oom_sakkie.telegram_gateway.handle_message")
    def test_authenticated_owner_media_uses_existing_gateway_without_ordinary_reply(self,mock_message,mock_task):
        mock_task.return_value=({"handled":True,"success":True,"status":"owner_task_album_receiving",
            "acknowledgements":0,"results":0},202)
        result,status=handle_telegram_gateway_message(PHOTO,headers=HEADERS,environ=ENV)
        self.assertEqual((status,result["mode"]),(202,"authenticated_gateway_owner_task"))
        self.assertEqual(result["reply_transport"],"backend_handles_owner_task_delivery")
        self.assertFalse(result["sends_telegram"]);self.assertFalse(result["writes"])
        mock_task.assert_called_once();mock_message.assert_not_called()

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

    def test_gatekeeper_reuses_single_trigger_and_active_gateway_for_owner_request_media(self):
        workflow=json.loads(Path("docs/04-n8n/workflows/2 - The GateKeeper/workflow.json").read_text(encoding="utf-8-sig"))
        nodes={node["name"]:node for node in workflow["nodes"]}
        relay=nodes["Relay Owner Request Media to Gateway"]
        self.assertEqual(relay["parameters"]["url"],
            "https://amadeus-pig-tracking-system.onrender.com/api/oom-sakkie/channels/telegram/message")
        headers=relay["parameters"]["headerParameters"]["parameters"]
        self.assertEqual(headers[0]["name"],"Authorization")
        self.assertIn("OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN",headers[0]["value"])
        self.assertEqual(sum(node.get("type")=="n8n-nodes-base.telegramTrigger" for node in workflow["nodes"]),1)
        outputs=workflow["connections"]["Switch - BEACON Media Intake"]["main"]
        self.assertEqual(outputs[2],[])
        self.assertEqual(outputs[3][0]["node"],"Relay Owner Request Media to Gateway")


if __name__=="__main__": unittest.main()
