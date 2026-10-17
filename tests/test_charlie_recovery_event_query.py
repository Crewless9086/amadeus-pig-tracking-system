"""Bounded native recovery-event selection and unchanged identity refusals.

The runner is synthetic: native Windows event-query syntax/performance requires
separate read-only provider qualification, never inferred from these tests.
"""
import copy
import json
import subprocess
import unittest
from unittest.mock import Mock

from modules.charlie import runtime_activation as a


class RecoveryEventQueryTests(unittest.TestCase):
    def setUp(self):
        self.instance = "ab12cdef-1234-abcd-5678-123456789abc"
        self.packet = {
            "expected_instance_guid": "{" + self.instance.upper() + "}",
            "prepared_at": "2026-10-14T16:51:30.123456+00:00",
            "task_scheduler_event_record_id_lower_bound": 268000,
            "authority": {"expires_at": "2026-10-14T17:11:30.123456+00:00"},
            "task_ownership": [{"execute": "C:/fixture/venv/Scripts/python.exe"}],
        }
        self.row = {
            "record_id": 268160, "utc": "2026-10-14T16:52:23.0000000Z",
            "activity": self.instance, "instance": "{" + self.instance.upper() + "}",
            "task": "\\" + a.TASK_NAME, "engine_pid": 128396,
            "action": "C:/fixture/venv/Scripts/python.exe",
        }

    def reader(self, rows=None, *, returncode=0, stdout=None, error=None):
        if stdout is None:
            stdout = json.dumps([self.row] if rows is None else rows)
        runner = Mock(side_effect=error) if error else Mock(
            return_value=subprocess.CompletedProcess([], returncode, stdout, "synthetic"))
        return a.WindowsExactTaskController(runner=runner), runner

    def test_native_selection_is_bounded_before_instance_postfilter(self):
        controller, runner = self.reader()
        self.assertEqual(controller.read_completed_instance_engine_pid(self.packet), 128396)
        command = runner.call_args.args[0]
        self.assertEqual(command[:4], ["powershell", "-NoProfile", "-NonInteractive", "-Command"])
        self.assertEqual(runner.call_args.kwargs["timeout"], 5)
        script = command[-1]
        xpath = script.split('$xpath="', 1)[1].split('";', 1)[0]
        for predicate in ("EventID=200", "EventRecordID > 268000",
                          "@SystemTime >= '2026-10-14T16:51:30Z'"):
            self.assertIn(predicate, xpath)
        self.assertNotIn(self.instance, xpath.casefold())
        self.assertNotIn("InstanceId", xpath)
        self.assertNotIn("TaskName", xpath)
        self.assertNotIn("@SystemTime <=", xpath)
        self.assertIn("[System.Diagnostics.Eventing.Reader.PathType]::LogName,$xpath", script)
        self.assertIn("$q.ReverseDirection=$true", script)
        self.assertIn("while($events.Count-lt 4097)", script)
        self.assertIn("$event=$reader.ReadEvent()", script)
        self.assertIn("if($null-eq $event){break};$events.Add($event)", script)
        self.assertLess(script.index("if($events.Count-gt 4096){exit 9}"), script.index("ForEach-Object"))
        self.assertLess(script.index("if($events.Count-gt 4096){exit 9}"), script.index("Where-Object"))
        self.assertIn("if($d.TaskInstanceId)", script)
        self.assertIn("else{[string]$d.InstanceId}", script)
        self.assertNotIn("Get-WinEvent", script)
        self.assertEqual(script.count("EventLogReader($q)"), 1)
        self.assertNotIn("FilterHashtable", script)

    def test_all_native_records_and_reader_are_disposed_on_every_script_exit(self):
        controller, runner = self.reader()
        controller.read_completed_instance_engine_pid(self.packet)
        script = runner.call_args.args[0][-1]
        body, cleanup = script.split("}finally{", 1)
        self.assertIn("try{$reader=New-Object", body)
        self.assertIn("if($events.Count-gt 4096){exit 9}", body)
        self.assertIn("$_.ToXml()", body)
        self.assertIn("ConvertTo-Json", body)
        self.assertIn("foreach($event in $events){try{$event.Dispose()}catch{$disposeFailed=$true}}", cleanup)
        self.assertIn("if($null-ne $reader){try{$reader.Dispose()}catch{$disposeFailed=$true}}", cleanup)
        self.assertTrue(cleanup.endswith("if($disposeFailed){throw 'event_reader_disposal_failed'}}"))
        self.assertNotIn(".Properties[", script)

    def test_guid_case_braces_and_action_path_normalization_remain_accepted(self):
        for value in (self.instance, self.instance.upper(), "{" + self.instance + "}",
                      "{" + self.instance.upper() + "}"):
            with self.subTest(guid=value):
                row = {**self.row, "activity": value, "instance": value,
                       "task": self.row["task"].swapcase(),
                       "action": "c:\\FIXTURE\\venv\\Scripts\\PYTHON.EXE"}
                controller, _ = self.reader([row])
                self.assertEqual(controller.read_completed_instance_engine_pid(self.packet), 128396)

    def test_inclusive_chronology_boundaries_remain_accepted(self):
        for stamp in (self.packet["prepared_at"], self.packet["authority"]["expires_at"],
                      "2026-10-14T18:52:23+02:00", "2026-10-14T17:11:30.1234569Z"):
            with self.subTest(stamp=stamp):
                controller, _ = self.reader([{**self.row, "utc": stamp}])
                self.assertEqual(controller.read_completed_instance_engine_pid(self.packet), 128396)

    def test_query_normalizes_non_utc_aware_window_without_local_time_assumption(self):
        packet = copy.deepcopy(self.packet)
        packet["prepared_at"] = "2026-10-14T18:51:30.123456+02:00"
        packet["authority"]["expires_at"] = "2026-10-14T19:11:30.123456+02:00"
        controller, runner = self.reader()
        self.assertEqual(controller.read_completed_instance_engine_pid(packet), 128396)
        script = runner.call_args.args[0][-1]
        self.assertIn("2026-10-14T16:51:30Z", script)
        self.assertNotIn("2026-10-14T17:11:30.123456Z", script)
        self.assertNotIn("[DateTime]::Parse", script)

    def test_each_identity_or_chronology_mismatch_refuses(self):
        for field, value in (
            ("activity", "ffffffff-ffff-ffff-ffff-ffffffffffff"),
            ("instance", "ffffffff-ffff-ffff-ffff-ffffffffffff"),
            ("task", "\\Another Task"), ("action", "C:/other/python.exe"),
            ("record_id", 268000), ("record_id", 267999), ("engine_pid", 0),
            ("engine_pid", -1), ("engine_pid", "unknown"),
            ("utc", "2026-10-14T16:51:30.123455+00:00"),
            ("utc", "2026-10-14T16:51:30.000000+00:00"),
            ("utc", "2026-10-14T17:11:30.123457+00:00"),
            ("utc", "2026-10-14T16:52:23"), ("utc", "unknown"),
        ):
            with self.subTest(field=field, value=value):
                controller, runner = self.reader([{**self.row, field: value}])
                with self.assertRaisesRegex(a.ActivationError, "^pre_starter_provider_event_unproven$"):
                    controller.read_completed_instance_engine_pid(self.packet)
                self.assertEqual(runner.call_count, 1)

    def test_empty_duplicate_or_conflicting_matches_refuse(self):
        for rows in ([], [self.row, self.row], [self.row, {**self.row, "engine_pid": 10}],
                     [self.row, {**self.row, "record_id": 268161}],
                     [self.row, {**self.row, "record_id": 268162,
                                 "utc": "2026-10-14T17:11:31+00:00"}]):
            with self.subTest(rows=len(rows)):
                controller, _ = self.reader(rows)
                with self.assertRaisesRegex(a.ActivationError, "^pre_starter_provider_event_unproven$"):
                    controller.read_completed_instance_engine_pid(self.packet)

    def test_raw_candidate_overflow_refuses_before_parsing_or_accepting_partial_match(self):
        for stdout in ("", "not-json", json.dumps([self.row])):
            with self.subTest(stdout=stdout):
                controller, runner = self.reader(returncode=9, stdout=stdout)
                with self.assertRaisesRegex(a.ActivationError, "^pre_starter_provider_event_overflow$"):
                    controller.read_completed_instance_engine_pid(self.packet)
                self.assertEqual(runner.call_count, 1)

    def test_failed_native_query_cannot_accept_otherwise_matching_output(self):
        for code in (1, 8, 10):
            with self.subTest(code=code):
                controller, runner = self.reader(returncode=code)
                with self.assertRaisesRegex(a.ActivationError, "^pre_starter_provider_event_unproven$"):
                    controller.read_completed_instance_engine_pid(self.packet)
                self.assertEqual(runner.call_count, 1)

    def test_timeout_or_launch_error_remains_unproven_without_retry(self):
        for error in (subprocess.TimeoutExpired("powershell", 5), OSError("synthetic")):
            with self.subTest(error=type(error).__name__):
                controller, runner = self.reader(error=error)
                with self.assertRaisesRegex(a.ActivationError, "^pre_starter_provider_event_unproven$"):
                    controller.read_completed_instance_engine_pid(self.packet)
                self.assertEqual(runner.call_count, 1)

    def test_malformed_native_output_refuses(self):
        for stdout in ("", "invalid", "{}", "null", "[{}]", "[null]"):
            with self.subTest(stdout=stdout):
                controller, _ = self.reader(stdout=stdout)
                with self.assertRaisesRegex(a.ActivationError, "^pre_starter_provider_event_unproven$"):
                    controller.read_completed_instance_engine_pid(self.packet)

    def test_invalid_window_refuses_before_native_process(self):
        cases = []
        for prepared, expiry in (("bad", self.packet["authority"]["expires_at"]),
                                 ("2026-10-14T16:51:30", self.packet["authority"]["expires_at"]),
                                 (self.packet["prepared_at"], "2026-10-14T17:11:30"),
                                 (self.packet["authority"]["expires_at"], self.packet["prepared_at"])):
            packet = copy.deepcopy(self.packet)
            packet["prepared_at"] = prepared; packet["authority"]["expires_at"] = expiry
            cases.append(packet)
        packet = copy.deepcopy(self.packet); packet["task_scheduler_event_record_id_lower_bound"] = -1
        cases.append(packet)
        for index, packet in enumerate(cases):
            with self.subTest(index=index):
                controller, runner = self.reader()
                with self.assertRaisesRegex(a.ActivationError, "^pre_starter_provider_event_unproven$"):
                    controller.read_completed_instance_engine_pid(packet)
                runner.assert_not_called()

    def test_invalid_instance_refuses_before_native_process(self):
        packet = {**self.packet, "expected_instance_guid": "not-a-guid"}
        controller, runner = self.reader()
        with self.assertRaisesRegex(a.ActivationError, "^task_scheduler_instance_guid_invalid$"):
            controller.read_completed_instance_engine_pid(packet)
        runner.assert_not_called()
