import os
import socket
import unittest
from unittest import mock

from modules.telemetry.rootline_canary_rehearsal import (
    AUTHORITY,
    MAX_PULSE_SECONDS,
    OFF_EVENT,
    SCENARIOS,
    rehearse_all,
    rehearse_scenario,
)


class RootlineCanaryRehearsalTests(unittest.TestCase):
    def test_every_simulated_path_is_offline_command_inert_and_zero_retry(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            socket, "socket", side_effect=AssertionError("network forbidden")
        ) as socket_mock:
            results = rehearse_all()

        self.assertFalse(socket_mock.called)
        self.assertEqual(len(results), len(SCENARIOS))
        for result in results:
            self.assertEqual(result["retry_count"], 0)
            self.assertEqual(result["max_pulse_seconds"], MAX_PULSE_SECONDS)
            self.assertEqual(result["authority"], AUTHORITY)
            self.assertFalse(any(result["authority"].values()))
            self.assertTrue(all(row["simulated"] for row in result["evidence"]))
            self.assertTrue(all(row["append_only"] for row in result["evidence"]))

    def test_off_is_issued_after_any_on_outcome_unless_manual_safe_is_proven(self):
        manual = rehearse_scenario("manual_isolation")
        self.assertFalse(manual["off_required"])
        self.assertFalse(manual["off_issued"])
        self.assertEqual(
            manual["final_physical_state"], "physically_verified_safe_closed"
        )

        for name in SCENARIOS:
            if name == "manual_isolation":
                continue
            result = rehearse_scenario(name)
            self.assertTrue(result["on_invoked"], name)
            self.assertTrue(result["off_required"], name)
            self.assertTrue(result["off_issued"], name)
            off = next(
                row for row in result["evidence"]
                if row["evidence_type"] == "off_request"
            )
            self.assertEqual(off["details"]["event"], OFF_EVENT)
            self.assertEqual(off["details"]["attempt"], 1)

    def test_uncertain_paths_finish_unavailable_not_safe(self):
        uncertain = {
            "on_accepted_no_valve_movement",
            "on_timeout_uncertain_delivery",
            "unexpected_flow",
            "off_timeout",
            "physical_closure_unclear",
            "operator_abort",
        }
        for name in uncertain:
            result = rehearse_scenario(name)
            self.assertEqual(result["final_physical_state"], "unavailable", name)

    def test_normal_path_separates_acceptance_movement_flow_and_shutdown(self):
        result = rehearse_scenario("normal")
        evidence_types = [row["evidence_type"] for row in result["evidence"]]
        self.assertEqual(
            evidence_types,
            [
                "on_request",
                "physical_valve_opening",
                "observed_water_flow",
                "off_request",
                "physical_valve_closure",
                "new_supply_flow_stopped",
                "residual_downstream_drainage",
                "final_physical_state",
            ],
        )
        self.assertEqual(
            result["final_physical_state"], "physically_verified_safe_closed"
        )

    def test_evidence_is_append_only_sequenced_and_has_stable_identity(self):
        result = rehearse_scenario("operator_abort")
        self.assertEqual(
            [row["sequence"] for row in result["evidence"]],
            list(range(1, len(result["evidence"]) + 1)),
        )
        self.assertEqual(
            len({row["evidence_id"] for row in result["evidence"]}),
            len(result["evidence"]),
        )

    def test_unknown_scenario_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unknown rehearsal scenario"):
            rehearse_scenario("invented")


if __name__ == "__main__":
    unittest.main()
