import unittest
from unittest.mock import patch

from modules.agents.ledger import run_ledger
from modules.agents.oom_sakkie import run_oom_sakkie
from modules.charlie.agent_runtime import delegate_to_agent as framework_delegate
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority


class OomSakkieOperationalAgentTests(unittest.TestCase):
    @patch("modules.agents.oom_sakkie.delegate_to_agent")
    def test_oom_sakkie_coordinates_herdmaster_without_write_authority(self, delegate):
        delegate.return_value = ({
            "success": True, "direct_answer": "There are 12 pigs.", "summary": "Herd checked.",
            "facts": [{"name": "count", "value": 12}], "metrics": {"count": 12}, "breakdown": {},
            "anomalies": [], "recommendations": [], "unresolved_questions": [],
            "sources": [{"name": "pig_current_state"}], "confidence": .99, "agent": {"agent_id": "herdmaster"},
        }, 200)
        result = run_oom_sakkie({"question": "How are the pigs doing?"})
        self.assertTrue(result["success"])
        self.assertEqual(result["direct_answer"], "There are 12 pigs.")
        self.assertFalse(result["write_authority"])
        self.assertEqual(result["delegations"][0]["agent_id"], "herdmaster")

    def test_ledger_validates_precomputed_deterministic_price_evidence(self):
        result = run_ledger({"known_context": {"pricing": {"found": True, "unit_price": 800, "currency": "ZAR", "source": "supabase"}}})
        self.assertTrue(result["facts"][0]["value"])
        self.assertIn("800", result["direct_answer"])
        self.assertEqual(result["confidence"], .99)

    @patch("modules.oom_sakkie.herdmaster_management_runtime.consume_current_herdmaster_management",
           side_effect=RuntimeError("database unavailable"))
    @patch("modules.agents.oom_sakkie.delegate_to_agent")
    def test_proactive_failure_preserves_legacy_herd_answer(self, delegate, _consume):
        delegate.return_value = ({"success": True, "direct_answer": "Herd answer remains available.",
            "summary": "Herd checked.", "facts": [], "metrics": {}, "breakdown": {}, "anomalies": [],
            "recommendations": [], "unresolved_questions": [], "sources": [{"name":"canonical"}],
            "confidence": .99, "agent": {"agent_id":"herdmaster"}}, 200)
        result = run_oom_sakkie({"question":"Farm status", "gateway_authority":object(), "owner_user_id":"42"})
        self.assertTrue(result["success"])
        self.assertEqual(result["direct_answer"], "Herd answer remains available.")
        self.assertEqual(result["proactive_herdmaster_management"]["status"], "herdmaster_management_runtime_contained")

    @patch("modules.oom_sakkie.herdmaster_management_runtime.consume_current_herdmaster_management")
    @patch("modules.agents.oom_sakkie.delegate_to_agent")
    def test_deployed_agent_delegation_preserves_opaque_manager_authority(self, herd_delegate, consume):
        herd_delegate.return_value=({"success":True,"direct_answer":"Herd current.","summary":"Current",
            "facts":[],"metrics":{},"breakdown":{},"anomalies":[],"recommendations":[],
            "unresolved_questions":[],"sources":[{"name":"canonical"}],"confidence":.99,
            "agent":{"agent_id":"herdmaster"}},200)
        consume.return_value={"success":True,"status":"herdmaster_management_round_consumed",
            "accepted_work_item_count":1,"writes_farm_data":False,"sends_telegram":False}
        authority=issue_gateway_owner_authority("42","42")
        result,status=framework_delegate("oom-sakkie",{"question":"Farm status","gateway_authority":authority,
            "owner_user_id":"42"})
        self.assertEqual(status,200)
        self.assertEqual(result["proactive_herdmaster_management"]["accepted_work_item_count"],1)
        consume.assert_called_once_with(authority=authority,owner_user_id="42")

    @patch("modules.oom_sakkie.herdmaster_management_runtime.consume_current_herdmaster_management")
    @patch("modules.agents.oom_sakkie.delegate_to_agent")
    def test_agent_recorder_never_receives_owner_or_opaque_capability(self, herd_delegate, consume):
        herd_delegate.return_value=({"success":True,"direct_answer":"Current","summary":"Current",
            "facts":[],"metrics":{},"breakdown":{},"anomalies":[],"recommendations":[],
            "unresolved_questions":[],"sources":[{"name":"canonical"}],"confidence":.99,
            "agent":{"agent_id":"herdmaster"}},200)
        consume.return_value={"success":True,"status":"herdmaster_management_round_consumed",
            "accepted_work_item_count":0,"writes_farm_data":False,"sends_telegram":False}
        calls=[]; authority=issue_gateway_owner_authority("42","42")
        framework_delegate("oom-sakkie",{"question":"Farm status","gateway_authority":authority,
            "owner_user_id":"42"},intent_id="INTENT-1",recorder=lambda *args,**kwargs:calls.append((args,kwargs)))
        recorded_request=calls[0][0][3]
        self.assertNotIn("gateway_authority",recorded_request)
        self.assertNotIn("scheduled_manager_context",recorded_request)
        self.assertNotIn("owner_user_id",recorded_request)
        self.assertNotIn("42",str(recorded_request))


if __name__ == "__main__":
    unittest.main()
