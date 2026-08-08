import unittest

from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport


def snapshot(**changes):
    value = {"device_id": "100204e9bc", "provider_control_calls": 0,
             "current_outputs_authoritative": True,
             "actuation_configuration_safe": True, "timers_enabled": False,
             "interlock_enabled": False, "scenes_enabled": False,
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
        self.assertEqual(safety["native_inching_seconds"], 3599)
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


if __name__ == "__main__":
    unittest.main()
