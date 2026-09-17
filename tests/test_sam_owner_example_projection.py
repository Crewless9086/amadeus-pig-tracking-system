import threading
import time
import unittest

from modules.sales import sam_live_stock_runtime
from modules.sales import sam_owner_example_projection as projection


EXAMPLE = {
    "customer_message_excerpt": "Where are you?",
    "owner_reply_excerpt": "Live-pig handover is arranged in Riversdale or Albertinia.",
    "classification": "owner_replaced",
}


class SamOwnerExampleProjectionTests(unittest.TestCase):
    def setUp(self):
        projection._reset_owner_example_projection_for_tests()

    def tearDown(self):
        projection._reset_owner_example_projection_for_tests()

    def test_cold_request_never_waits_for_blocked_database_loader(self):
        entered = threading.Event()
        release = threading.Event()

        def blocked_loader(**_kwargs):
            entered.set()
            release.wait(5)
            return {"success": True, "examples": [EXAMPLE]}, 200

        started = time.perf_counter()
        packet = projection.read_owner_example_projection(loader=blocked_loader)
        elapsed = time.perf_counter() - started
        self.assertLess(elapsed, 0.2)
        self.assertFalse(packet["fresh"])
        self.assertEqual(packet["examples"], [])
        self.assertFalse(packet["request_blocking_load"])
        self.assertTrue(entered.wait(1))
        release.set()
        deadline = time.time() + 1
        while (
            not projection.read_owner_example_projection(now_epoch=time.time())["fresh"]
            and time.time() < deadline
        ):
            time.sleep(0.01)

    def test_warm_projection_has_deterministic_version_identity(self):
        first = projection.refresh_owner_example_projection(
            lambda **_kwargs: ({"examples": [EXAMPLE]}, 200),
            now_epoch=100,
        )
        packet = projection.read_owner_example_projection(now_epoch=101)
        second_id = projection._projection_id([EXAMPLE])
        self.assertTrue(first["success"])
        self.assertEqual(first["projection_id"], second_id)
        self.assertEqual(packet["projection_id"], second_id)
        self.assertEqual(packet["examples"], [EXAMPLE])
        self.assertFalse(packet["canonical_authority"])

    def test_concurrent_cold_requests_start_only_one_refresh(self):
        entered = threading.Event()
        release = threading.Event()
        calls = []

        def blocked_loader(**_kwargs):
            calls.append(1)
            entered.set()
            release.wait(5)
            return {"examples": [EXAMPLE]}, 200

        threads = [
            threading.Thread(
                target=projection.read_owner_example_projection,
                kwargs={"loader": blocked_loader},
            )
            for _ in range(20)
        ]
        for thread in threads:
            thread.start()
        self.assertTrue(entered.wait(1))
        for thread in threads:
            thread.join(1)
        self.assertEqual(len(calls), 1)
        release.set()
        deadline = time.time() + 1
        while (
            not projection.read_owner_example_projection(now_epoch=time.time())["fresh"]
            and time.time() < deadline
        ):
            time.sleep(0.01)

    def test_stale_projection_is_omitted_while_refresh_runs(self):
        projection.refresh_owner_example_projection(
            lambda **_kwargs: ({"examples": [EXAMPLE]}, 200),
            now_epoch=100,
        )
        release = threading.Event()
        packet = projection.read_owner_example_projection(
            loader=lambda **_kwargs: (
                release.wait(5) or {"examples": [EXAMPLE]},
                200,
            ),
            freshness_seconds=10,
            now_epoch=111,
        )
        self.assertFalse(packet["fresh"])
        self.assertEqual(packet["status"], "stale_omitted")
        self.assertEqual(packet["examples"], [])
        release.set()
        deadline = time.time() + 1
        while projection._refresh_inflight and time.time() < deadline:
            time.sleep(0.01)

    def test_refresh_failure_and_malformed_guidance_never_raise(self):
        failure = projection.refresh_owner_example_projection(
            lambda **_kwargs: (_ for _ in ()).throw(ConnectionError("offline"))
        )
        malformed = projection.refresh_owner_example_projection(
            lambda **_kwargs: ({"examples": ["bad", {}, {"owner_reply_excerpt": ""}]}, 200)
        )
        self.assertFalse(failure["success"])
        self.assertTrue(malformed["success"])
        self.assertEqual(malformed["example_count"], 0)
        self.assertEqual(
            projection.read_owner_example_projection()["examples"],
            [],
        )

    def test_fast_failures_are_cooled_down_across_sequential_requests(self):
        calls = []
        now = [100.0]

        def failing_loader(**_kwargs):
            calls.append(1)
            raise ConnectionError("offline")

        projection.read_owner_example_projection(
            loader=failing_loader, clock=lambda: now[0]
        )
        deadline = time.time() + 1
        while len(calls) < 1 and time.time() < deadline:
            time.sleep(0.01)
        for second in range(101, 160):
            now[0] = float(second)
            projection.read_owner_example_projection(
                loader=failing_loader, clock=lambda: now[0]
            )
        self.assertEqual(len(calls), 1)
        now[0] = 160.0
        projection.read_owner_example_projection(
            loader=failing_loader, clock=lambda: now[0]
        )
        deadline = time.time() + 1
        while len(calls) < 2 and time.time() < deadline:
            time.sleep(0.01)
        self.assertEqual(len(calls), 2)

    def test_delayed_refresh_timestamps_begin_at_completion(self):
        now = [100.0]

        def successful_loader(**_kwargs):
            now[0] = 175.0
            return {"examples": [EXAMPLE]}, 200

        result = projection.refresh_owner_example_projection(
            successful_loader, clock=lambda: now[0]
        )
        self.assertTrue(result["success"])
        self.assertTrue(
            projection.read_owner_example_projection(
                clock=lambda: 176.0
            )["fresh"]
        )

        projection._reset_owner_example_projection_for_tests()
        now[0] = 200.0

        def failing_loader(**_kwargs):
            now[0] = 275.0
            raise ConnectionError("offline")

        projection.refresh_owner_example_projection(
            failing_loader, clock=lambda: now[0]
        )
        calls = []
        projection.read_owner_example_projection(
            loader=lambda **_kwargs: calls.append(1),
            clock=lambda: 334.0,
        )
        time.sleep(0.05)
        self.assertEqual(calls, [])

    def test_consumer_mutation_cannot_change_cached_content_or_identity(self):
        nested = {
            **EXAMPLE,
            "classification": {"kind": "owner_replaced"},
        }
        projection.refresh_owner_example_projection(
            lambda **_kwargs: ({"examples": [nested]}, 200),
            now_epoch=100,
        )
        first = projection.read_owner_example_projection(now_epoch=101)
        first["examples"][0]["owner_reply_excerpt"] = "mutated"
        first["examples"][0]["classification"]["kind"] = "mutated"
        second = projection.read_owner_example_projection(now_epoch=102)
        self.assertEqual(
            second["examples"][0]["owner_reply_excerpt"],
            EXAMPLE["owner_reply_excerpt"],
        )
        self.assertEqual(
            second["examples"][0]["classification"]["kind"],
            "owner_replaced",
        )
        self.assertEqual(second["projection_id"], first["projection_id"])

    def test_direct_refreshes_are_serialized(self):
        first_entered = threading.Event()
        release_first = threading.Event()
        order = []

        def first_loader(**_kwargs):
            first_entered.set()
            release_first.wait(2)
            order.append("first")
            return {"examples": [{**EXAMPLE, "owner_reply_excerpt": "first"}]}, 200

        def second_loader(**_kwargs):
            order.append("second")
            return {"examples": [{**EXAMPLE, "owner_reply_excerpt": "second"}]}, 200

        first = threading.Thread(
            target=projection.refresh_owner_example_projection,
            args=(first_loader,),
        )
        second = threading.Thread(
            target=projection.refresh_owner_example_projection,
            args=(second_loader,),
        )
        first.start()
        self.assertTrue(first_entered.wait(1))
        second.start()
        time.sleep(0.05)
        self.assertEqual(order, [])
        release_first.set()
        first.join(1)
        second.join(1)
        self.assertEqual(order, ["first", "second"])
        self.assertEqual(
            projection.read_owner_example_projection()["examples"][0][
                "owner_reply_excerpt"
            ],
            "second",
        )

    def test_direct_refresh_cannot_clear_queued_background_admission(self):
        direct_entered = threading.Event()
        release_direct = threading.Event()
        background_calls = []
        background_entered = threading.Event()
        release_background = threading.Event()

        def direct_loader(**_kwargs):
            direct_entered.set()
            release_direct.wait(2)
            return {"examples": [EXAMPLE]}, 200

        direct = threading.Thread(
            target=projection.refresh_owner_example_projection,
            args=(direct_loader,),
        )
        direct.start()
        self.assertTrue(direct_entered.wait(1))

        def background_loader(**_kwargs):
            background_calls.append(1)
            background_entered.set()
            release_background.wait(2)
            return {"examples": [EXAMPLE]}, 200

        for _ in range(20):
            projection.read_owner_example_projection(
                loader=background_loader
            )
        self.assertTrue(projection._refresh_inflight)
        release_direct.set()
        direct.join(1)
        self.assertTrue(background_entered.wait(1))
        self.assertTrue(projection._refresh_inflight)
        release_background.set()
        deadline = time.time() + 1
        while projection._refresh_inflight and time.time() < deadline:
            time.sleep(0.01)
        self.assertEqual(background_calls, [1])

    def test_request_reply_is_identical_when_optional_loader_is_blocked(self):
        release = threading.Event()

        def blocked_loader(**_kwargs):
            release.wait(5)
            return {"examples": [EXAMPLE]}, 200

        inbound = {
            "event": "message_created",
            "message_type": "incoming",
            "content": "How much for a small piglet?",
            "conversation": {
                "id": 2111,
                "inbox": {"id": 96568, "channel_type": "Channel::Whatsapp"},
            },
            "sender": {"id": 99, "name": "Customer"},
            "account": {"id": 147387},
        }
        kwargs = {
            "intake_context_loader": lambda _conversation_id: {
                "success": True, "known_fields": {}, "items": []
            },
            "conversation_history_loader": lambda _conversation_id, _source: {
                "success": True, "messages": []
            },
            "availability_loader": lambda: [],
        }
        baseline, _ = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound,
            environ={"SAM_LIVE_STOCK_OWNER_EXAMPLE_RETRIEVAL_ENABLED": "0"},
            **kwargs,
        )
        projection._reset_owner_example_projection_for_tests()
        started = time.perf_counter()
        actual, _ = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound,
            environ={},
            owner_example_loader=blocked_loader,
            **kwargs,
        )
        elapsed = time.perf_counter() - started
        release.set()
        self.assertLess(elapsed, 1.0)
        self.assertEqual(
            actual["sam_decision"]["suggested_reply_text"],
            baseline["sam_decision"]["suggested_reply_text"],
        )
        self.assertEqual(actual["sam_decision"]["owner_correction_examples"], [])
        self.assertFalse(
            actual["sam_decision"]["owner_example_projection"][
                "request_blocking_load"
            ]
        )


if __name__ == "__main__":
    unittest.main()
