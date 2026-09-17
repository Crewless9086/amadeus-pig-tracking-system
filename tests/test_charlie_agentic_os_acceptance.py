import unittest

from modules.charlie.agentic_os_acceptance import PHASE_GATES, evaluate_phase, evaluate_program


class AgenticOsAcceptanceTests(unittest.TestCase):
    def test_phase_fails_closed_when_one_gate_is_missing(self):
        evidence = {gate: True for gate in PHASE_GATES[2]}
        evidence.pop("single_release_coordinator")
        result = evaluate_phase(2, evidence)
        self.assertFalse(result["complete"])
        self.assertEqual(result["missing_gates"], ["single_release_coordinator"])

    def test_truthy_non_boolean_does_not_pass(self):
        evidence = {gate: True for gate in PHASE_GATES[3]}
        evidence["existing_sources_reconciled"] = "probably"
        self.assertFalse(evaluate_phase(3, evidence)["complete"])

    def test_program_requires_every_phase(self):
        evidence = {phase: {gate: True for gate in gates} for phase, gates in PHASE_GATES.items()}
        self.assertTrue(evaluate_program(evidence)["complete"])
        evidence[7]["live_owner_canary"] = False
        result = evaluate_program(evidence)
        self.assertFalse(result["complete"])
        self.assertEqual(result["incomplete_phases"], [7])


if __name__ == "__main__":
    unittest.main()
