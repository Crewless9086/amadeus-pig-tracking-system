import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport


def snapshot(**changes):
    value = {"device_id": "100204e9bc", "provider_control_calls": 0,
             "current_outputs_authoritative": True,
             "actuation_safety_complete": True,
             "actuation_configuration_safe": True, "timers_enabled": False,
             "interlock_enabled": False, "scenes_enabled": False,
             "commissioned_baseline_id": "BASELINE-1",
             "response_digest": "READ-1", "retrieved_at": "2026-08-08T18:00:00Z",
             "channels": [{"channel": i, "output_state": "OFF",
                "native_auto_off_enabled": True, "native_auto_off_seconds": 3599,
                "power_restoration_state": "OFF"} for i in range(1, 5)]}
    value.update(changes)
    return value


class Response:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def getcode(self): return self.status
    def read(self, _limit): return b"Congratulations!"


class RootlineIFTTTTransportTests(unittest.TestCase):
    def transport(self, snap=None, calls=None, environ=None):
        calls = [] if calls is None else calls
        def open_request(request, timeout):
            calls.append((request, timeout)); return Response()
        return RootlineIFTTTTransport(token_store=object(),
            environ=({"ROOTLINE_IFTTT_MAKER_KEY": "protected-secret"}
                     if environ is None else environ),
            http_open=open_request,
            readback=lambda **_kwargs: snap or snapshot()), calls

    def test_exact_bc_state_setting_events_only(self):
        transport, calls = self.transport()
        result = transport.set_state(device_id="100204e9bc", channel=1, state="ON",
                                     idempotency_key="EXEC-1:ON")
        self.assertTrue(result["accepted_unambiguous"])
        self.assertEqual(result["event"], "irrigation_1_ch1_on")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("protected-secret", repr(result))
        with self.assertRaisesRegex(ValueError, "binding_invalid"):
            transport.set_state(device_id="100204e9bc", channel=3, state="ON",
                                idempotency_key="X")

    def test_missing_secret_or_ambiguous_provider_never_claims_acceptance(self):
        transport, calls = self.transport(environ={})
        result = transport.set_state(device_id="100204e9bc", channel=2, state="ON",
                                     idempotency_key="EXEC-2:ON")
        self.assertFalse(result["accepted_unambiguous"]); self.assertEqual(calls, [])

    def test_readback_projects_exact_channel_safety_and_output(self):
        transport, _ = self.transport()
        safety = transport.read_safety_configuration(device_id="100204e9bc", channel=2)
        state = transport.read_output_state(device_id="100204e9bc", channel=2)
        self.assertEqual((safety["zone_id"], safety["channel"]), ("C12345", 2))
        self.assertTrue(safety["authoritative"])
        self.assertEqual((safety["device_id"],safety["output_state"]),("100204e9bc","OFF"))
        self.assertEqual(safety["controller_safety_generation"],"BASELINE-1")
        self.assertEqual(safety["physical_commissioning_generation"],"BASELINE-1")
        self.assertTrue(safety["commissioned"])
        self.assertEqual(safety["native_inching_seconds"], 3599)
        self.assertTrue(safety["relevant_outputs_off"])
        self.assertTrue(transport.configuration_status(
            device_id="100204e9bc",channel=2)["configured"])
        self.assertEqual(state["state"], "OFF")

    def test_stale_or_incomplete_readback_fails_closed(self):
        transport, _ = self.transport(snapshot(actuation_configuration_safe=False))
        self.assertFalse(transport.read_safety_configuration(
            device_id="100204e9bc", channel=1)["authoritative"])
        bad, _ = self.transport(snapshot(channels=[]))
        with self.assertRaisesRegex(RuntimeError, "readback_invalid"):
            bad.read_output_state(device_id="100204e9bc", channel=1)

    def test_channel_binding_is_identity_based_and_rejects_duplicates(self):
        reordered = snapshot()
        reordered["channels"] = list(reversed(reordered["channels"]))
        transport, _ = self.transport(reordered)
        self.assertEqual(transport.read_output_state(
            device_id="100204e9bc", channel=1)["state"], "OFF")
        duplicate = snapshot()
        duplicate["channels"][3]["channel"] = 1
        bad, _ = self.transport(duplicate)
        with self.assertRaisesRegex(RuntimeError, "readback_invalid"):
            bad.read_output_state(device_id="100204e9bc", channel=1)

    def test_fertilizer_events_are_exact_and_separately_disabled_by_default(self):
        fertilizer=snapshot(device_id="100204d497")
        fertilizer["channels"][0]["native_auto_off_seconds"]=120
        fertilizer["channels"][1]["native_auto_off_seconds"]=300
        disabled,calls=self.transport(fertilizer,environ={"ROOTLINE_IFTTT_MAKER_KEY":"secret"})
        result=disabled.set_state(device_id="100204d497",channel=1,state="ON",
            idempotency_key="AUX-1:ON")
        self.assertEqual(result["status"],"auxiliary_authority_disabled")
        self.assertEqual(calls,[])
        recovery=disabled.set_state(device_id="100204d497",channel=1,state="OFF",
            idempotency_key="AUX-1:OFF:1")
        self.assertTrue(recovery["accepted_unambiguous"])
        self.assertEqual(recovery["event"],"controller_1_ch1_off")
        enabled,calls=self.transport(fertilizer,environ={"ROOTLINE_IFTTT_MAKER_KEY":"secret",
            "ROOTLINE_FERTILIZER_INJECTION_ENABLED":"true",
            "ROOTLINE_FERTILIZER_MIXING_ENABLED":"true"})
        injection=enabled.set_state(device_id="100204d497",channel=1,state="ON",
            idempotency_key="AUX-1:ON")
        mixing=enabled.set_state(device_id="100204d497",channel=2,state="OFF",
            idempotency_key="AUX-2:OFF")
        self.assertEqual(injection["event"],"controller_1_ch1_on")
        self.assertEqual(mixing["event"],"controller_1_ch2_off")
        self.assertEqual(len(calls),2)

    def test_real_transport_safety_schema_passes_auxiliary_edge_revalidation(self):
        from modules.telemetry.rootline_auxiliary_management import (
            build_auxiliary_eligibility,revalidate_auxiliary_execution_edge)
        now=datetime(2026,8,8,18,0,tzinfo=timezone.utc)
        fertilizer=snapshot(device_id="100204d497",commissioned_supervised_channels=[2])
        fertilizer["channels"][1]["native_auto_off_seconds"]=300
        transport,_calls=self.transport(fertilizer)
        safety_value=transport.read_safety_configuration(device_id="100204d497",channel=2)
        context={"plan_generation":"PLAN-EDGE","injection_active":False,
            "verified_mixing_minutes_today":0,"verified_mixing_sessions_today":0,
            "mixing_history_complete_through":now.isoformat(),"power_suitable":True}
        artifact=build_auxiliary_eligibility(task={
            "auxiliary_device_id":"FERTILIZER-MIXER-CH2"},safety=safety_value,
            context=context,flags={"ROOTLINE_FERTILIZER_MIXING_ENABLED":True},now=now)
        self.assertTrue(artifact["eligible"])
        second_snapshot=dict(fertilizer,response_digest="READ-2",
            retrieved_at=(now+timedelta(seconds=1)).isoformat())
        second_transport,_calls=self.transport(second_snapshot)
        current_safety=second_transport.read_safety_configuration(
            device_id="100204d497",channel=2)
        self.assertNotEqual(safety_value["response_digest"],current_safety["response_digest"])
        self.assertEqual(safety_value["controller_safety_generation"],
            current_safety["controller_safety_generation"])
        self.assertTrue(revalidate_auxiliary_execution_edge(artifact,
            current_context=context,current_safety=current_safety,
            now=now+timedelta(seconds=1)))

    def fertilizer_snapshot(self):
        value=snapshot(device_id="100204d497",commissioned_supervised_channels=[2])
        value["channels"][0].update(native_auto_off_seconds=120)
        value["channels"][1].update(native_auto_off_seconds=300)
        for row in value["channels"][2:]:
            row.update(native_auto_off_enabled=False,native_auto_off_seconds=None)
        value["actuation_configuration_safe"]=False
        return value

    def test_mixer_boundary_allows_off_unassigned_channels_without_auto_off(self):
        transport,calls=self.transport(self.fertilizer_snapshot())
        safety=transport.read_safety_configuration(device_id="100204d497",channel=2)
        self.assertTrue(safety["authoritative"])
        self.assertTrue(safety["relevant_outputs_off"])
        self.assertEqual(calls,[])

    def test_mixer_boundary_blocks_on_unknown_energizable_or_assigned_auxiliary(self):
        cases=[]
        on=self.fertilizer_snapshot(); on["channels"][2]["output_state"]="ON"; cases.append(on)
        unknown=self.fertilizer_snapshot(); unknown["channels"][3]["power_restoration_state"]=None; cases.append(unknown)
        scheduled=self.fertilizer_snapshot(); scheduled["timers_enabled"]=True; cases.append(scheduled)
        scene=self.fertilizer_snapshot(); scene["scenes_enabled"]=True; cases.append(scene)
        interlock=self.fertilizer_snapshot(); interlock["interlock_enabled"]=True; cases.append(interlock)
        for value in cases:
            transport,_=self.transport(value)
            self.assertFalse(transport.read_safety_configuration(
                device_id="100204d497",channel=2)["authoritative"])
        assigned,_=self.transport(self.fertilizer_snapshot(),environ={
            "ROOTLINE_FERTILIZER_INJECTION_ENABLED":"true"})
        self.assertFalse(assigned.read_safety_configuration(
            device_id="100204d497",channel=2)["authoritative"])

    def test_mixer_boundary_blocks_missing_or_wrong_target_auto_off(self):
        for enabled,seconds in ((False,300),(True,299),(True,None)):
            value=self.fertilizer_snapshot()
            value["channels"][1].update(native_auto_off_enabled=enabled,
                native_auto_off_seconds=seconds)
            transport,_=self.transport(value)
            self.assertFalse(transport.read_safety_configuration(
                device_id="100204d497",channel=2)["authoritative"])

    def test_new_assignment_on_unused_mixer_channel_fails_closed(self):
        transport,_=self.transport(self.fertilizer_snapshot())
        assignments={1:{"identity":"FERTILIZER-INJECTION-CH1",
            "authority_flag":"ROOTLINE_FERTILIZER_INJECTION_ENABLED"},
            2:{"identity":"FERTILIZER-MIXER-CH2",
               "authority_flag":"ROOTLINE_FERTILIZER_MIXING_ENABLED"},
            3:{"identity":"UNEXPECTED-AUXILIARY",
               "authority_flag":"ROOTLINE_UNEXPECTED_ENABLED"}}
        with patch("modules.telemetry.rootline_ifttt_transport.device_channel_assignments",
                   return_value=assignments):
            self.assertFalse(transport.read_safety_configuration(
                device_id="100204d497",channel=2)["authoritative"])

    def test_injection_assignment_remains_isolated_and_off(self):
        value=self.fertilizer_snapshot(); value["channels"][0]["output_state"]="ON"
        transport,calls=self.transport(value)
        self.assertFalse(transport.read_safety_configuration(
            device_id="100204d497",channel=2)["authoritative"])
        self.assertEqual(calls,[])

    def test_injection_assignment_requires_its_native_fail_stop(self):
        for enabled,seconds in ((False,120),(True,121),(True,None)):
            value=self.fertilizer_snapshot()
            value["channels"][0].update(native_auto_off_enabled=enabled,
                native_auto_off_seconds=seconds)
            transport,_=self.transport(value)
            self.assertFalse(transport.read_safety_configuration(
                device_id="100204d497",channel=2)["authoritative"])


if __name__ == "__main__":
    unittest.main()
