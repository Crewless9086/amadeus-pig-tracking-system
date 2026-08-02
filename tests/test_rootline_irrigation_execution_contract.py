import unittest
from datetime import datetime, timedelta, timezone

from modules.telemetry.rootline_irrigation_execution_contract import (
    AUTHORITY, ContractError, commissioning_checklist, prepare_execution_segment,
    transition_lifecycle, validate_commissioning,
)

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


def evidence(zone="B12345", channel=1):
    return {
        "platform": "eWeLink", "model": "SONOFF 4CH Pro R3", "firmware": "3.8.2",
        "device": "IRRIGATION (1) - Left", "zone_id": zone, "channel": channel,
        "observed_at": NOW.isoformat(), "power_restoration_state": "OFF",
        "native_inching_enabled": True, "native_inching_minutes": 60,
        "configuration_generation": 1, "revoked": False,
        "conflicting_schedules": [], "conflicting_scenes": [],
        "conflicting_ifttt_automations": [],
        "supervised_proof": {"duration_minutes": 1, "physical_start_confirmed": True,
            "native_auto_off_observed": True, "oom_sakkie_off_command_count": 0,
            "physical_stop_confirmed": True, "other_channel_actuation_count": 0,
            "production_setting_reverified_after_proof": True,
            "offline_timeout_proven": True, "power_cycle_off_no_restart_proven": True},
    }


def commissioned(zone="B12345", channel=1):
    return validate_commissioning(zone, evidence(zone, channel), now=NOW)


def eligibility(zone="B12345", at=NOW, identity="ELIG-1", generation=7,
                commissioning_id=None):
    item = {"eligibility_id": identity, "zone_id": zone, "eligible": True,
        "assessed_at": at.isoformat(), "conflicts": [], "concurrency_clear": True,
        "plan_id": "ROOTLINE-PLAN-20260802", "plan_generation": 4,
        "commissioning_id": commissioning_id or commissioned(zone, 1 if zone == "B12345" else 2)["commissioning_id"],
        "evidence_generation": generation, "power_evidence_id": "POWER-1",
        "local_weather_evidence_id": "WEATHER-1", "forecast_evidence_id": "FORECAST-1",
        "water_evidence_status": "available", "governing_reserve_pct": 70}
    from modules.telemetry.rootline_irrigation_execution_contract import _digest
    item["evidence_sha256"] = _digest(item)
    return item


def payload(zone="B12345", segment=1, duration=60):
    return {"zone_id": zone, "segment_number": segment, "duration_minutes": duration,
            "plan_id": "ROOTLINE-PLAN-20260802", "plan_generation": 4}


def event(execution, evidence_id, state, observed_at, **details):
    from modules.telemetry.rootline_irrigation_execution_contract import _digest
    item = {"evidence_id": evidence_id, "execution_id": execution["execution_id"],
            "state": state, "observed_at": observed_at.isoformat(),
            "provenance": "canonical-test-reader", **details}
    item["evidence_sha256"] = _digest(item)
    return item


class RootlineExecutionContractTests(unittest.TestCase):
    def build(self, *, zone="B12345", segment=1, duration=60, now=NOW,
              eligibility_packet=None, prior=None):
        raw = evidence(zone, 1 if zone == "B12345" else 2)
        proof = validate_commissioning(zone, raw, now=now)
        eligible = eligibility_packet or eligibility(zone, now, commissioning_id=proof["commissioning_id"])
        return prepare_execution_segment(payload(zone, segment, duration),
            commissioning_id=proof["commissioning_id"], eligibility_id=eligible["eligibility_id"],
            commissioning_reader=lambda _: raw, eligibility_reader=lambda _: eligible,
            prior_segment=prior, execution_reader=(lambda _: prior) if prior else None, now=now)
    def test_exact_channel_commissioning_and_independent_auto_off(self):
        for zone, channel in (("B12345", 1), ("C12345", 2)):
            result = commissioned(zone, channel)
            self.assertEqual(commissioning_checklist(zone)["channel"], channel)
            self.assertEqual(result["native_fail_stop_minutes"], 60)
            self.assertTrue(result["commissioned"])
            self.assertTrue(all(result[key] is False for key in AUTHORITY))

    def test_power_restore_conflicts_and_unconfigured_inching_fail_closed(self):
        cases = (("power_restoration_state", "ON", "power_restoration_off_not_proven"),
                 ("conflicting_schedules", ["legacy"], "conflicting_schedules_present"),
                 ("conflicting_scenes", None, "conflicting_scenes_present"),
                 ("conflicting_ifttt_automations", ["old"], "conflicting_ifttt_automations_present"),
                 ("native_inching_enabled", False, "native_inching_not_enabled"))
        for field, value, error in cases:
            item = evidence(); item[field] = value
            with self.assertRaisesRegex(ContractError, error):
                validate_commissioning("B12345", item, now=NOW)

    def test_supervised_proof_is_sub_60_and_independent(self):
        item = evidence(); item["supervised_proof"]["duration_minutes"] = 60
        with self.assertRaisesRegex(ContractError, "sub_60"):
            validate_commissioning("B12345", item, now=NOW)
        item = evidence(); item["supervised_proof"]["oom_sakkie_off_command_count"] = 1
        with self.assertRaisesRegex(ContractError, "independence_not_proven"):
            validate_commissioning("B12345", item, now=NOW)

    def test_execution_is_fresh_exact_max_60_and_has_safe_command_semantics(self):
        segment = self.build()
        self.assertEqual(segment["duration_minutes"], 60)
        self.assertEqual(segment["on_policy"]["max_attempts"], 1)
        self.assertFalse(segment["on_policy"]["ambiguous_retry"])
        self.assertEqual(segment["off_policy"]["max_attempts"], 3)
        self.assertTrue(segment["persist_before_on"])
        with self.assertRaisesRegex(ContractError, "segment_exceeds"):
            self.build(duration=61)
        with self.assertRaisesRegex(ContractError, "eligibility_stale"):
            old = eligibility(at=NOW-timedelta(minutes=16))
            self.build(eligibility_packet=old)

    def test_zone_proof_cannot_cross_or_reach_unproven_channel(self):
        with self.assertRaisesRegex(ContractError, "commissioning_zone_id_mismatch"):
            raw = evidence("B12345", 1); proof = commissioned()
            item = eligibility("C12345", commissioning_id=proof["commissioning_id"])
            prepare_execution_segment(payload(zone="C12345"),
                commissioning_id=proof["commissioning_id"], eligibility_id=item["eligibility_id"],
                commissioning_reader=lambda _: raw, eligibility_reader=lambda _: item, now=NOW)
        with self.assertRaisesRegex(ContractError, "only_proven"):
            commissioning_checklist("E12345")

    def test_two_hours_requires_completed_first_segment_and_new_decision(self):
        with self.assertRaisesRegex(ContractError, "segment_exceeds"):
            self.build(duration=120)
        first = self.build()
        active = transition_lifecycle(first, "Active", "EV-A", lambda _: event(
            first, "EV-A", "Active", NOW, on_outcome="accepted_unambiguous",
            native_timer_armed_readback=True, native_timer_minutes=60))
        stopped_at = NOW + timedelta(minutes=60)
        stopped = transition_lifecycle(active, "Stopped", "EV-S", lambda _: event(
            first, "EV-S", "Stopped", stopped_at, shutdown_verified=True))
        completed_at = stopped_at + timedelta(seconds=1)
        completed = transition_lifecycle(stopped, "Completed", "EV-C", lambda _: event(
            first, "EV-C", "Completed", completed_at, shutdown_verified=True,
            native_auto_off_observed=True))
        with self.assertRaisesRegex(ContractError, "fresh_reassessment"):
            item = eligibility(at=completed_at, identity="ELIG-2", generation=8,
                               commissioning_id=first["commissioning_id"])
            self.build(segment=2, now=completed_at, eligibility_packet=item, prior=completed)
        reassessed = completed_at + timedelta(minutes=1)
        item = eligibility(at=reassessed, identity="ELIG-2", generation=8,
                           commissioning_id=first["commissioning_id"])
        second = self.build(segment=2, now=reassessed, eligibility_packet=item, prior=completed)
        self.assertNotEqual(second["execution_id"], first["execution_id"])

    def test_replay_stable_visible_lifecycle_and_ambiguous_on_rejected(self):
        first = self.build()
        replay = self.build()
        self.assertEqual(replay, first)
        self.assertEqual(first["visible_telegram_lifecycle"],
            ["Planned", "Active", "Stopped", "Completed", "Failed"])
        self.assertTrue(all(first[key] is False for key in AUTHORITY))
        with self.assertRaisesRegex(ContractError, "unambiguous_on"):
            transition_lifecycle(first, "Active", "EV-X", lambda _: event(
                first, "EV-X", "Active", NOW, on_outcome="timeout",
                native_timer_armed_readback=True, native_timer_minutes=60))

    def test_forged_commissioning_and_eligibility_are_rejected(self):
        raw = evidence(); proof = commissioned()
        item = eligibility(commissioning_id=proof["commissioning_id"])
        item["plan_generation"] = 99
        with self.assertRaisesRegex(ContractError, "plan_or_commissioning_mismatch"):
            prepare_execution_segment(payload(), commissioning_id=proof["commissioning_id"],
                eligibility_id=item["eligibility_id"], commissioning_reader=lambda _: raw,
                eligibility_reader=lambda _: item, now=NOW)
        old_but_current = NOW + timedelta(days=31)
        current_eligibility = eligibility(at=old_but_current, commissioning_id=proof["commissioning_id"])
        accepted = prepare_execution_segment(payload(), commissioning_id=proof["commissioning_id"],
            eligibility_id="ELIG-1", commissioning_reader=lambda _: raw,
            eligibility_reader=lambda _: current_eligibility, now=old_but_current)
        self.assertEqual(accepted["commissioning_id"], proof["commissioning_id"])
        revoked = evidence(); revoked["revoked"] = True
        with self.assertRaisesRegex(ContractError, "revoked"):
            prepare_execution_segment(payload(), commissioning_id=proof["commissioning_id"],
                eligibility_id="ELIG-1", commissioning_reader=lambda _: revoked,
                eligibility_reader=lambda _: current_eligibility, now=NOW)

    def test_short_segment_primary_stop_differs_from_native_fail_stop(self):
        segment = self.build(duration=20)
        active = transition_lifecycle(segment, "Active", "EV-SHORT", lambda _: event(
            segment, "EV-SHORT", "Active", NOW, on_outcome="accepted_unambiguous",
            native_timer_armed_readback=True, native_timer_minutes=60))
        self.assertEqual(active["native_auto_off_deadline"],
                         (NOW + timedelta(minutes=60)).isoformat())
        stopped_at = NOW + timedelta(minutes=20)
        stopped = transition_lifecycle(active, "Stopped", "EV-SHORT-STOP", lambda _: event(
            segment, "EV-SHORT-STOP", "Stopped", stopped_at, shutdown_verified=True))
        completed = transition_lifecycle(stopped, "Completed", "EV-SHORT-DONE", lambda _: event(
            segment, "EV-SHORT-DONE", "Completed", stopped_at + timedelta(seconds=1),
            shutdown_verified=True, primary_off_accepted_unambiguous=True,
            native_auto_off_observed=False))
        self.assertEqual(completed["state"], "Completed")

    def test_forged_predecessor_mutation_and_conflicting_replay_fail(self):
        first = self.build()
        forged = dict(first, state="Completed", state_evidence={
            "native_auto_off_observed": True, "shutdown_verified": True,
            "observed_at": (NOW + timedelta(minutes=60)).isoformat()})
        reassessed = NOW + timedelta(minutes=61)
        item = eligibility(at=reassessed, identity="ELIG-2", generation=8,
                           commissioning_id=first["commissioning_id"])
        with self.assertRaisesRegex(ContractError, "identity_digest|state_history"):
            self.build(segment=2, now=reassessed, eligibility_packet=item, prior=forged)
        active_evidence = event(first, "EV-A", "Active", NOW,
            on_outcome="accepted_unambiguous", native_timer_armed_readback=True,
            native_timer_minutes=60)
        active = transition_lifecycle(first, "Active", "EV-A", lambda _: active_evidence)
        self.assertEqual(
            transition_lifecycle(active, "Active", "EV-A", lambda _: active_evidence), active
        )
        conflict = dict(active_evidence, provenance="conflicting-reader")
        from modules.telemetry.rootline_irrigation_execution_contract import _digest
        conflict["evidence_sha256"] = _digest({k: v for k, v in conflict.items()
                                                if k != "evidence_sha256"})
        with self.assertRaisesRegex(ContractError, "transition_chronology_conflict"):
            transition_lifecycle(active, "Active", "EV-A", lambda _: conflict)
        mutated = dict(active, duration_minutes=10)
        with self.assertRaisesRegex(ContractError, "execution_identity_digest_mismatch"):
            transition_lifecycle(mutated, "Stopped", "EV-S", lambda _: event(
                first, "EV-S", "Stopped", NOW + timedelta(minutes=60), shutdown_verified=True))


if __name__ == "__main__":
    unittest.main()
