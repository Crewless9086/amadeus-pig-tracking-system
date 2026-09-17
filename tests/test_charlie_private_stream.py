import json
import unittest

from modules.charlie.private_stream import stream_private_turn


def decode_event(value):
    rows = value.strip().splitlines()
    return rows[0].split(":", 1)[1].strip(), json.loads(rows[1].split(":", 1)[1].strip())


class CharliePrivateStreamTests(unittest.TestCase):
    def test_stream_orders_progress_reply_and_terminal_event(self):
        def runner(emit):
            emit("intent_understood", {"intent_type": "read_core_status"})
            emit("capability_started", {"capability": "read_core_status"})
            emit("evidence_received", {"capability": "read_core_status", "success": True})
            return {"status": "private_charlie_replied", "reply": "CORE is active.", "executive_packet": {"spoken_summary": "CORE is active."}}, 200
        events = [decode_event(value) for value in stream_private_turn("status", runner, turn_id="TURN-1")]
        self.assertEqual([event[0] for event in events], ["turn_started", "intent_understood", "capability_started", "evidence_received", "reply_ready", "turn_completed"])

    def test_stream_converts_worker_exception_to_safe_terminal_failure(self):
        def fail(_emit): raise RuntimeError("secret detail")
        events = [decode_event(value) for value in stream_private_turn("status", fail, turn_id="TURN-2")]
        self.assertEqual(events[-1][0], "turn_failed")
        self.assertEqual(events[-1][1]["error_type"], "RuntimeError")
        self.assertNotIn("secret detail", json.dumps(events[-1][1]))


if __name__ == "__main__":
    unittest.main()
