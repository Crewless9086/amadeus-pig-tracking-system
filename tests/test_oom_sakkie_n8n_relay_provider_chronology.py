import json
import subprocess
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / "docs" / "04-n8n" / "workflows" / "2.0B - Oom Sakkie Backend Read-Only Relay" / "workflow.json"

def source():
    data=json.loads(WORKFLOW.read_text(encoding="utf-8"))
    return next(n for n in data["nodes"] if n["name"]=="Code - Normalize GateKeeper Message")["parameters"]["jsCode"]

def run(item):
    harness='''const vm=require("vm");const src=JSON.parse(process.argv[1]);const input=JSON.parse(process.argv[2]);const out=vm.runInNewContext(`(function(){"use strict";${src}})()`,{$json:input,String,Number});process.stdout.write(JSON.stringify(out[0].json));'''
    done=subprocess.run(["node","-e",harness,json.dumps(source()),json.dumps(item)],check=True,capture_output=True,text=True)
    return json.loads(done.stdout)

class OomRelayProviderChronologyTests(unittest.TestCase):
    def test_authenticated_gatekeeper_message_preserves_provider_identity_and_time(self):
        result=run({"message_text":"Pig 11 is standing","user_id":"5721652188","chat_id":"5721652188","message_id":"3174","timestamp":"ignored-fallback","raw_update":{"message":{"message_id":3174,"date":1785673203}}})
        self.assertTrue(result["success"])
        self.assertEqual(result["message_id"],"3174")
        self.assertEqual(result["gateway_payload"],{"message":{"message_id":3174,"date":1785673203,"text":"Pig 11 is standing","from":{"id":"5721652188"},"chat":{"id":"5721652188","type":"private"}}})

    def test_missing_provider_identity_or_timestamp_fails_closed(self):
        for item in (
            {"message_text":"Pig 11 is standing","user_id":"42","chat_id":"42"},
            {"message_text":"Pig 11 is standing","user_id":"42","chat_id":"42","message_id":"10"},
        ):
            with self.subTest(item=item):
                result=run(item)
                self.assertEqual(result["status"],"invalid_relay_input")
                self.assertFalse(result["send_allowed"])
                self.assertFalse(result["sends_telegram"])
                self.assertFalse(result["writes"])
                self.assertNotIn("gateway_payload",result)

    def test_raw_provider_identity_wins_over_mutable_flat_fallback(self):
        result=run({"message_text":"safe","user_id":"42","chat_id":"42","message_id":"999","timestamp":1,"raw_update":{"message":{"message_id":3174,"date":1785673203}}})
        self.assertEqual(result["gateway_payload"]["message"]["message_id"],3174)
        self.assertEqual(result["gateway_payload"]["message"]["date"],1785673203)

if __name__=="__main__":unittest.main()
