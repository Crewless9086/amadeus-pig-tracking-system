import json
import subprocess
import unittest
from pathlib import Path
WORKFLOW=Path(__file__).resolve().parents[1]/"docs"/"04-n8n"/"workflows"/"2.0B - Oom Sakkie Backend Read-Only Relay"/"workflow.json"
def source():
 data=json.loads(WORKFLOW.read_text(encoding="utf-8"));return next(n for n in data["nodes"] if n["name"]=="Code - Normalize GateKeeper Message")["parameters"]["jsCode"]
def run(item):
 harness='''const vm=require("vm");const src=JSON.parse(process.argv[1]);const input=JSON.parse(process.argv[2]);const out=vm.runInNewContext(`(function(){"use strict";${src}})()`,{$json:input,String,Number,Object});process.stdout.write(JSON.stringify(out[0].json));'''
 done=subprocess.run(["node","-e",harness,json.dumps(source()),json.dumps(item)],check=True,capture_output=True,text=True);return json.loads(done.stdout)
def valid():
 return {"message_text":"Pig 11 is standing","user_id":"5721652188","chat_id":"5721652188","message_id":"3174","raw_update":{"message":{"message_id":3174,"date":1785673203,"text":"Pig 11 is standing","from":{"id":5721652188},"chat":{"id":5721652188,"type":"private"}}}}
class OomRelayProviderChronologyTests(unittest.TestCase):
 def test_authenticated_raw_message_is_complete_backend_envelope(self):
  result=run(valid());self.assertTrue(result["success"]);self.assertEqual(result["gateway_payload"],{"message":{"message_id":3174,"date":1785673203,"text":"Pig 11 is standing","from":{"id":"5721652188"},"chat":{"id":"5721652188","type":"private"}}})
 def test_missing_or_malformed_raw_provider_evidence_fails_closed(self):
  cases=[{}, {"message_id":3174,"date":1785673203,"text":"x","from":{"id":1},"chat":{"id":1,"type":"group"}}, {"message_id":"","date":1785673203,"text":"x","from":{"id":1},"chat":{"id":1,"type":"private"}}, {"message_id":1,"date":"bad","text":"x","from":{"id":1},"chat":{"id":1,"type":"private"}}]
  for raw in cases:
   item=valid();item["raw_update"]={"message":raw} if raw else {}
   with self.subTest(raw=raw):
    result=run(item);self.assertEqual(result["status"],"invalid_relay_input");self.assertFalse(result["send_allowed"]);self.assertFalse(result["sends_telegram"]);self.assertFalse(result["writes"]);self.assertNotIn("gateway_payload",result)
 def test_flat_substitution_cannot_override_raw_authority(self):
  for key,value in (("message_text","altered"),("user_id","99"),("chat_id","99"),("message_id","999")):
   item=valid();item[key]=value
   with self.subTest(key=key):
    result=run(item);self.assertEqual(result["status"],"invalid_relay_input");self.assertNotIn("gateway_payload",result)
 def test_flat_only_chronology_is_never_accepted(self):
  result=run({"message_text":"x","user_id":"1","chat_id":"1","message_id":"1","timestamp":1785673203});self.assertEqual(result["status"],"invalid_relay_input");self.assertNotIn("gateway_payload",result)
if __name__=="__main__":unittest.main()
