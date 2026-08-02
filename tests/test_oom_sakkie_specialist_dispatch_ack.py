import unittest
from datetime import datetime, timezone

from modules.oom_sakkie.specialist_dispatch_ack import (
    DispatchContractError,
    reconcile_specialist_dispatch,
)


DIGEST = "e0c8b7010d5ed206b9b95180a7de4fe8be69b40dac3055cdc80c43f08d213bb8"
MISSION = "BEACON-PR647-PUBLISH"
WORKER = "beacon-terminal-visible-1"


def event(state, event_id=None, **changes):
    row = {
        "event_id": event_id or f"event-{state}",
        "state": state,
        "mission_id": MISSION,
        "target_worker_id": WORKER,
        "release_digest": DIGEST,
        "occurred_at": "2026-08-01T10:00:00+00:00",
    }
    if state == "released":
        row.update({
            "acknowledgement_deadline_at": "2026-08-01T10:02:00+00:00",
            "start_deadline_at": "2026-08-01T10:05:00+00:00",
        })
    if state == "delivery_acknowledged":
        row.update({"occurred_at": "2026-08-01T10:01:00+00:00", "delivery_receipt_id": "receipt-1"})
    if state == "started":
        row.update({"occurred_at": "2026-08-01T10:03:30+00:00", "heartbeat_at": "2026-08-01T10:03:00+00:00", "activity_observed_at": "2026-08-01T10:03:15+00:00", "activity_id": "activity-start-1"})
    if state == "progress_observed":
        row.update({"occurred_at": "2026-08-01T10:04:30+00:00", "heartbeat_at": "2026-08-01T10:04:00+00:00", "activity_observed_at": "2026-08-01T10:04:15+00:00", "activity_id": "activity-progress-1"})
    if state == "completed":
        row.update({"occurred_at": "2026-08-01T10:05:00+00:00", "outcome_artifact_id": "BEACON-OUTCOME-1", "outcome_artifact_sha256": "a" * 64, "outcome_status": "provider_confirmed"})
    if state == "contained":
        row.update({"occurred_at": "2026-08-01T10:04:00+00:00", "containment_reason": "provider_ambiguous"})
    row.update(changes)
    return row


def baseline(*extra):
    return [event("release_requested"), event("released"), *extra]


class SpecialistDispatchAcknowledgementTests(unittest.TestCase):
    def test_release_request_and_release_never_imply_execution(self):
        requested = reconcile_specialist_dispatch(
            [event("release_requested")], now="2026-08-01T10:00:30+00:00"
        )
        released = reconcile_specialist_dispatch(
            baseline(), now="2026-08-01T10:01:00+00:00"
        )
        self.assertEqual(requested.state, "release_requested")
        self.assertEqual(released.state, "released")
        self.assertTrue(released.released)
        self.assertFalse(released.delivery_acknowledged)
        self.assertFalse(released.execution_started)
        self.assertFalse(released.automatic_resumption_claimed)
        self.assertFalse(released.calls_worker)

    def test_delivery_acknowledgement_is_distinct_from_start(self):
        snapshot = reconcile_specialist_dispatch(
            baseline(event("delivery_acknowledged")),
            now="2026-08-01T10:02:30+00:00",
        )
        self.assertEqual(snapshot.state, "delivery_acknowledged")
        self.assertTrue(snapshot.delivery_acknowledged)
        self.assertFalse(snapshot.execution_started)

    def test_start_requires_matching_fresh_activity_before_deadline(self):
        good = reconcile_specialist_dispatch(
            baseline(event("delivery_acknowledged"), event("started")),
            now="2026-08-01T10:04:00+00:00",
        )
        stale = reconcile_specialist_dispatch(
            baseline(
                event("delivery_acknowledged"),
                event("started", heartbeat_at="2026-08-01T09:50:00+00:00"),
            ),
            now="2026-08-01T10:04:00+00:00",
        )
        late = reconcile_specialist_dispatch(
            baseline(
                event("delivery_acknowledged"),
                event("started", occurred_at="2026-08-01T10:06:00+00:00", heartbeat_at="2026-08-01T10:06:00+00:00"),
            ),
            now="2026-08-01T10:06:30+00:00",
        )
        self.assertEqual(good.state, "started")
        self.assertTrue(good.execution_started)
        self.assertEqual(stale.state, "delivery_acknowledged")
        self.assertFalse(stale.execution_started)
        self.assertEqual(late.state, "ack_timeout")
        self.assertEqual(late.alert.reason, "start_not_observed")

    def test_unrelated_worker_or_mission_activity_cannot_satisfy_dispatch(self):
        wrong_worker = event("started", event_id="wrong-worker", target_worker_id="beacon-terminal-other")
        wrong_mission = event("started", event_id="wrong-mission", mission_id="OTHER-MISSION")
        snapshot = reconcile_specialist_dispatch(
            baseline(event("delivery_acknowledged"), wrong_worker, wrong_mission),
            now="2026-08-01T10:06:00+00:00",
        )
        self.assertEqual(snapshot.state, "ack_timeout")
        self.assertFalse(snapshot.execution_started)
        self.assertEqual(snapshot.alert.reason, "start_not_observed")
        self.assertEqual(snapshot.ignored_event_ids, ("wrong-mission", "wrong-worker"))

    def test_progress_requires_started_and_fresh_matching_activity(self):
        no_start = reconcile_specialist_dispatch(
            baseline(event("delivery_acknowledged"), event("progress_observed")),
            now="2026-08-01T10:04:45+00:00",
        )
        progress = reconcile_specialist_dispatch(
            baseline(event("delivery_acknowledged"), event("started"), event("progress_observed")),
            now="2026-08-01T10:04:45+00:00",
        )
        self.assertEqual(no_start.state, "delivery_acknowledged")
        self.assertFalse(no_start.progress_observed)
        self.assertEqual(progress.state, "progress_observed")
        self.assertTrue(progress.progress_observed)

    def test_completion_requires_matching_outcome_artifact(self):
        prefix = baseline(event("delivery_acknowledged"), event("started"), event("progress_observed"))
        assertion_only = reconcile_specialist_dispatch(
            prefix + [event("completed", outcome_artifact_id="", outcome_artifact_sha256="", outcome_status="")],
            now="2026-08-01T10:05:30+00:00",
        )
        complete = reconcile_specialist_dispatch(
            prefix + [event("completed")], now="2026-08-01T10:05:30+00:00"
        )
        unrelated_artifact = reconcile_specialist_dispatch(
            prefix + [event("completed", event_id="other-artifact", mission_id="OTHER-MISSION")],
            now="2026-08-01T10:05:30+00:00",
        )
        self.assertEqual(assertion_only.state, "progress_observed")
        self.assertFalse(assertion_only.completed)
        self.assertEqual(complete.state, "completed")
        self.assertEqual(complete.outcome_artifact_id, "BEACON-OUTCOME-1")
        self.assertEqual(unrelated_artifact.state, "progress_observed")

    def test_durable_start_and_completion_do_not_decay_after_heartbeat_ttl(self):
        rows = baseline(event("delivery_acknowledged"), event("started"), event("completed"))
        snapshot = reconcile_specialist_dispatch(
            rows, now="2026-08-01T12:00:00+00:00", heartbeat_ttl_seconds=60
        )
        self.assertEqual(snapshot.state, "completed")
        self.assertTrue(snapshot.execution_started)
        self.assertTrue(snapshot.completed)
        self.assertIsNone(snapshot.alert)

    def test_future_or_reverse_ordered_activity_cannot_prove_start(self):
        future = reconcile_specialist_dispatch(
            baseline(
                event("delivery_acknowledged"),
                event("started", occurred_at="2026-08-01T10:04:30+00:00", heartbeat_at="2026-08-01T10:04:00+00:00", activity_observed_at="2026-08-01T10:04:15+00:00"),
            ),
            now="2026-08-01T10:04:15+00:00",
        )
        reversed_time = reconcile_specialist_dispatch(
            baseline(
                event("delivery_acknowledged"),
                event("started", occurred_at="2026-08-01T10:04:30+00:00", heartbeat_at="2026-08-01T10:04:20+00:00", activity_observed_at="2026-08-01T10:04:10+00:00"),
            ),
            now="2026-08-01T10:04:30+00:00",
        )
        self.assertFalse(future.execution_started)
        self.assertFalse(reversed_time.execution_started)

    def test_stale_heartbeat_first_observed_late_cannot_prove_start(self):
        release = event("released", start_deadline_at="2026-08-01T11:00:00+00:00")
        late_observation = event(
            "started",
            occurred_at="2026-08-01T10:20:30+00:00",
            heartbeat_at="2026-08-01T10:03:00+00:00",
            activity_observed_at="2026-08-01T10:20:00+00:00",
        )
        snapshot = reconcile_specialist_dispatch(
            [event("release_requested"), release, event("delivery_acknowledged"), late_observation],
            now="2026-08-01T10:21:00+00:00",
            heartbeat_ttl_seconds=300,
        )
        self.assertEqual(snapshot.state, "delivery_acknowledged")
        self.assertFalse(snapshot.execution_started)

    def test_future_or_failed_outcome_cannot_complete(self):
        prefix = baseline(event("delivery_acknowledged"), event("started"))
        future = reconcile_specialist_dispatch(
            prefix + [event("completed", occurred_at="2026-08-01T11:00:00+00:00")],
            now="2026-08-01T10:05:30+00:00",
        )
        failed = reconcile_specialist_dispatch(
            prefix + [event("completed", outcome_status="failed")],
            now="2026-08-01T10:05:30+00:00",
        )
        self.assertEqual(future.state, "started")
        self.assertFalse(future.completed)
        self.assertEqual(failed.state, "started")
        self.assertFalse(failed.completed)

    def test_containment_is_distinct_from_completion(self):
        snapshot = reconcile_specialist_dispatch(
            baseline(event("delivery_acknowledged"), event("contained")),
            now="2026-08-01T10:04:30+00:00",
        )
        self.assertEqual(snapshot.state, "contained")
        self.assertTrue(snapshot.contained)
        self.assertFalse(snapshot.completed)

    def test_containment_must_follow_request_and_have_a_reason(self):
        before_request = reconcile_specialist_dispatch(
            baseline(event("contained", occurred_at="2026-08-01T09:00:00+00:00")),
            now="2026-08-01T10:01:00+00:00",
        )
        missing_reason = reconcile_specialist_dispatch(
            baseline(event("contained", containment_reason="")),
            now="2026-08-01T10:01:30+00:00",
        )
        self.assertEqual(before_request.state, "released")
        self.assertFalse(before_request.contained)
        self.assertEqual(missing_reason.state, "released")
        self.assertFalse(missing_reason.contained)

    def test_release_must_follow_request_and_not_come_from_future(self):
        with self.assertRaisesRegex(DispatchContractError, "release_before_request"):
            reconcile_specialist_dispatch(
                [event("release_requested"), event("released", occurred_at="2026-08-01T09:59:00+00:00")],
                now="2026-08-01T10:01:00+00:00",
            )
        with self.assertRaisesRegex(DispatchContractError, "release_from_future"):
            reconcile_specialist_dispatch(
                [event("release_requested"), event("released", occurred_at="2026-08-01T10:01:00+00:00")],
                now="2026-08-01T10:00:30+00:00",
            )

    def test_beacon_pr647_release_without_visible_ack_or_start_times_out_once(self):
        rows = baseline()
        first = reconcile_specialist_dispatch(rows, now="2026-08-01T10:06:00+00:00")
        replay = reconcile_specialist_dispatch(rows + [dict(rows[1])], now="2026-08-01T10:07:00+00:00")
        self.assertEqual(first.state, "ack_timeout")
        self.assertEqual(first.alert.reason, "delivery_acknowledgement_missing")
        self.assertEqual(first.alert.alert_id, replay.alert.alert_id)
        self.assertEqual(first.alert.deduplication_key, replay.alert.deduplication_key)
        self.assertFalse(first.alert.automatic_resumption_claimed)
        self.assertEqual(first.alert.buttons, 0)
        self.assertFalse(first.alert.calls_telegram)
        self.assertFalse(first.execution_started)

    def test_acknowledged_but_not_started_has_one_deduplicated_systemic_alert(self):
        rows = baseline(event("delivery_acknowledged"))
        first = reconcile_specialist_dispatch(rows, now="2026-08-01T10:06:00+00:00")
        second = reconcile_specialist_dispatch(rows, now="2026-08-01T10:30:00+00:00")
        self.assertEqual(first.state, "ack_timeout")
        self.assertEqual(first.alert.reason, "start_not_observed")
        self.assertEqual(first.alert.alert_id, second.alert.alert_id)
        self.assertTrue(first.alert.manual_coverage_required)

    def test_duplicate_release_is_noop_but_conflicting_replay_fails_closed(self):
        release = event("released")
        snapshot = reconcile_specialist_dispatch(
            [event("release_requested"), release, dict(release)],
            now="2026-08-01T10:01:00+00:00",
        )
        self.assertEqual(snapshot.state, "released")
        with self.assertRaisesRegex(DispatchContractError, "event_id_idempotency_conflict"):
            reconcile_specialist_dispatch(
                [event("release_requested"), release, dict(release, start_deadline_at="2026-08-01T10:10:00+00:00")],
                now="2026-08-01T10:01:00+00:00",
            )

    def test_exact_identity_and_deadlines_are_mandatory(self):
        with self.assertRaisesRegex(DispatchContractError, "target_worker_id_required"):
            reconcile_specialist_dispatch(
                [event("release_requested", target_worker_id="")], now="2026-08-01T10:00:00+00:00"
            )
        with self.assertRaisesRegex(DispatchContractError, "start_deadline_at_must_be_iso_datetime"):
            reconcile_specialist_dispatch(
                [event("release_requested"), event("released", start_deadline_at="")],
                now="2026-08-01T10:00:00+00:00",
            )
        with self.assertRaisesRegex(DispatchContractError, "mission_id_invalid"):
            reconcile_specialist_dispatch(
                [event("release_requested", mission_id="customer@example.com")],
                now="2026-08-01T10:00:00+00:00",
            )

    def test_contract_has_zero_io_authority_in_every_state(self):
        cases = [
            ([event("release_requested")], "2026-08-01T10:00:00+00:00"),
            (baseline(), "2026-08-01T10:01:00+00:00"),
            (baseline(event("delivery_acknowledged")), "2026-08-01T10:02:00+00:00"),
            (baseline(event("delivery_acknowledged"), event("started")), "2026-08-01T10:04:00+00:00"),
            (baseline(event("delivery_acknowledged"), event("started"), event("progress_observed")), "2026-08-01T10:04:45+00:00"),
            (baseline(event("delivery_acknowledged"), event("started"), event("completed")), "2026-08-01T10:05:30+00:00"),
            (baseline(event("contained")), "2026-08-01T10:01:00+00:00"),
            (baseline(), "2026-08-01T10:06:00+00:00"),
        ]
        for rows, now in cases:
            with self.subTest(now=now):
                snapshot = reconcile_specialist_dispatch(rows, now=now)
                self.assertFalse(snapshot.calls_worker)
                self.assertFalse(snapshot.calls_telegram)
                self.assertFalse(snapshot.writes_performed)


if __name__ == "__main__":
    unittest.main()
