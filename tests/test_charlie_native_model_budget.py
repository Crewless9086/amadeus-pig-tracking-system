"""Offline strict-budget boundary tests. No provider, credential or socket calls."""
import copy
import hashlib
import json
import traceback
import unittest
from contextlib import contextmanager
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from modules.charlie.native_runner.execution import NativeExecutionError
from modules.charlie.native_runner.model_adapter import (
    DEFAULT_MODEL, DEFAULT_PROVIDER, STRICT_BASE_URL, STRICT_REQUEST_BYTES,
    HermesAuxiliaryModel,
)


class StrictModelBudgetTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.requests = []
        self.reservations = []
        self.closes = []
        self.resolve_options = []
        self.transport_options = []
        self.sdk_options = []
        self.response = SimpleNamespace(
            model=DEFAULT_MODEL, id="gen-synthetic-001",
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}', tool_calls=None))],
            usage=SimpleNamespace(prompt_tokens=20, completion_tokens=5, total_tokens=25, cost=0.000015),
        )
        self.error = None
        self.resolved_model = DEFAULT_MODEL
        self.reserved_result = None
        self.reservation_error = None
        self.clone_retries = 0
        self.clone_url = STRICT_BASE_URL
        outer = self

        class FakeSDK:
            def __init__(self):
                self.base_url = STRICT_BASE_URL
                self.max_retries = 2
                self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

            def with_options(self, **options):
                outer.sdk_options.append(options)
                child = FakeSDK()
                child.max_retries = outer.clone_retries
                child.base_url = outer.clone_url
                return child

            def create(self, **kwargs):
                outer.events.append("create")
                outer.requests.append(copy.deepcopy(kwargs))
                if outer.error:
                    raise outer.error
                return outer.response

            def close(self):
                raise AssertionError("the Hermes parent/copy must not own close of shared state")

        self.sdk = FakeSDK()

        class FakeHTTP:
            def __init__(self, **options):
                outer.transport_options.append(options)

            def __enter__(self):
                outer.events.append("transport_open")
                return self

            def __exit__(self, *_args):
                outer.events.append("transport_close")
                outer.closes.append(True)

        httpx = ModuleType("httpx")
        httpx.Client = FakeHTTP
        httpx.HTTPTransport = lambda **options: dict(options)
        openai = ModuleType("openai")
        openai.OpenAI = FakeSDK
        agent = ModuleType("agent")
        aux = ModuleType("agent.auxiliary_client")

        def resolve_provider_client(**options):
            outer.events.append("resolve")
            outer.resolve_options.append(options)
            return outer.sdk, outer.resolved_model

        resolve_provider_client.__module__ = "agent.auxiliary_client"
        aux.resolve_provider_client = resolve_provider_client
        aux.call_llm = lambda **_kwargs: self.fail("strict mode must not call retrying call_llm")
        hermes = ModuleType("hermes_cli")
        plugins = ModuleType("hermes_cli.plugins")

        @contextmanager
        def profile_scope(home):
            self.assertEqual(home, "synthetic-profile")
            self.events.append("profile_open")
            try:
                yield
            finally:
                self.events.append("profile_close")

        plugins._plugin_home_scope = profile_scope
        self.modules = {"httpx": httpx, "openai": openai, "agent": agent,
                        "agent.auxiliary_client": aux, "hermes_cli": hermes,
                        "hermes_cli.plugins": plugins}
        self.addCleanup(patch.stopall)
        patch.dict("sys.modules", self.modules).start()
        self.args = dict(instructions="Return JSON only.", input=[{"text": "synthetic task"}],
                         json_schema={"type": "object", "required": ["ok"],
                                      "additionalProperties": False,
                                      "properties": {"ok": {"type": "boolean"}}},
                         schema_name="synthetic.strict", purpose="synthetic",
                         task="charlie_native_builder", max_tokens=6000, timeout=60)

    def reserve(self, **record):
        self.events.append("reserve")
        self.reservations.append(record)
        if self.reservation_error:
            raise self.reservation_error
        return self.reserved_result

    def model(self, **changes):
        options = dict(profile_home="synthetic-profile", strict_budget=True,
                       before_attempt=self.reserve)
        options.update(changes)
        return HermesAuxiliaryModel(**options)

    def complete(self, **changes):
        args = {**self.args, **changes}
        return self.model().complete_structured(**args)

    def test_reservation_precedes_single_physical_call_and_exact_request_digest(self):
        result = self.complete()
        self.assertEqual(self.events, ["profile_open", "resolve", "transport_open", "reserve",
                                       "create", "transport_close", "profile_close"])
        self.assertEqual(len(self.requests), 1)
        request = dict(self.requests[0])
        request.update(request.pop("extra_body"))
        encoded = json.dumps(request, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.assertEqual(self.reservations, [{"request_sha256": hashlib.sha256(encoded).hexdigest(),
                                            "input_bytes": len(encoded), "max_tokens": 6000,
                                            "task": "charlie_native_builder"}])
        self.assertEqual(result.audit["request_sha256"], self.reservations[0]["request_sha256"])
        self.assertEqual(result.audit["input_bytes"], len(encoded))
        self.assertEqual(result.audit["attempt_count"], 1)

    def test_route_caps_and_output_budget_reach_actual_sdk_body(self):
        self.complete()
        self.assertEqual(self.resolve_options, [{"provider": "openrouter", "model": DEFAULT_MODEL,
                                               "task": "charlie_native_builder", "async_mode": False}])
        self.assertEqual(self.requests[0]["max_tokens"], 6000)
        self.assertEqual(self.requests[0]["tools"], [])
        self.assertEqual(self.requests[0]["extra_body"], {
            "provider": {"allow_fallbacks": False, "max_price": {"prompt": 0.25, "completion": 2.0}},
            "reasoning": {"effort": "low"}})
        self.assertNotIn("temperature", self.requests[0])
        self.assertEqual(self.sdk_options[0]["max_retries"], 0)
        self.assertEqual(self.sdk_options[0]["timeout"], 60)
        self.assertEqual(self.transport_options, [{"transport": {"retries": 0, "verify": True, "trust_env": False},
                                                 "follow_redirects": False, "trust_env": False}])
        self.assertEqual(self.sdk.max_retries, 2)
        self.assertEqual(self.closes, [True])

    def test_safe_request_id_and_numeric_usage_cost_are_audited(self):
        result = self.complete()
        audit = result.audit
        self.assertEqual(result.agent_id, "gen-synthetic-001")
        self.assertRegex(audit["invocation_id"], r"^native-[0-9a-f]{32}$")
        self.assertEqual(audit["provider_request_id"], "gen-synthetic-001")
        self.assertEqual(audit["usage"], {"prompt_tokens": 20, "completion_tokens": 5,
                                        "total_tokens": 25, "cost_usd": 0.000015})
        self.assertNotIn("Return JSON", json.dumps(audit))
        self.assertNotIn("synthetic task", json.dumps(audit))

    def test_absent_usage_is_unknown_without_refunding(self):
        self.response.usage = None
        self.response.id = None
        result = self.complete()
        self.assertEqual(result.audit["usage"], {})
        self.assertIsNone(result.audit["provider_request_id"])
        self.assertEqual(len(self.reservations), 1)
        self.assertEqual(result.agent_id, result.audit["invocation_id"])
        self.assertRegex(result.agent_id, r"^native-[0-9a-f]{32}$")
        next_result = self.complete()
        self.assertNotEqual(next_result.agent_id, result.agent_id)
        self.assertEqual(next_result.agent_id, next_result.audit["invocation_id"])

    def test_nonfinite_or_arbitrary_usage_metadata_is_not_copied(self):
        self.response.usage = SimpleNamespace(cost=float("nan"), prompt_tokens=True,
                                              completion_tokens=-1, total_tokens="secret")
        self.response.id = "bad request id / credential"
        result = self.complete()
        self.assertEqual(result.audit["usage"], {})
        self.assertIsNone(result.audit["provider_request_id"])

    def test_reservation_exception_prevents_provider_call_and_closes(self):
        self.reservation_error = RuntimeError("ledger failed")
        with self.assertRaisesRegex(NativeExecutionError, "hermes_auxiliary_inference_failed"):
            self.complete()
        self.assertEqual(self.requests, [])
        self.assertEqual(self.closes, [True])

    def test_explicit_reservation_refusal_prevents_provider_call(self):
        self.reserved_result = False
        with self.assertRaisesRegex(NativeExecutionError, "native_model_reservation_refused"):
            self.complete()
        self.assertEqual(self.requests, [])

    def test_provider_exception_is_reserved_once_without_retry(self):
        for exception in (TimeoutError("unknown outcome"), ConnectionError("lost response"),
                          ValueError("unsupported parameter")):
            with self.subTest(exception=type(exception).__name__):
                self.error = exception
                before = len(self.requests)
                with self.assertRaisesRegex(NativeExecutionError, "hermes_auxiliary_inference_failed"):
                    self.complete()
                self.assertEqual(len(self.requests), before + 1)
                self.assertEqual(len(self.reservations), len(self.requests))
                self.assertEqual(len(self.closes), len(self.requests))

    def test_provider_failure_details_do_not_escape_in_traceback(self):
        self.error = RuntimeError("synthetic-private-endpoint-and-credential")
        try:
            self.complete()
        except NativeExecutionError:
            rendered = traceback.format_exc()
        else:
            self.fail("expected bounded failure")
        self.assertNotIn("synthetic-private-endpoint-and-credential", rendered)
        self.assertIn("hermes_auxiliary_inference_failed", rendered)
        self.assertEqual(len(self.reservations), 1)

    def test_invalid_response_and_schema_still_consume_reservation(self):
        for content in (None, "", "not-json", "[]", '{"wrong":true}', '{"ok":"yes"}'):
            with self.subTest(content=content):
                self.response.choices[0].message.content = content
                before = len(self.requests)
                with self.assertRaises(NativeExecutionError):
                    self.complete()
                self.assertEqual(len(self.requests), before + 1)
                self.assertEqual(len(self.reservations), len(self.requests))

    def test_response_route_change_is_refused_after_reserved_call(self):
        self.response.model = "openai/gpt-5"
        with self.assertRaisesRegex(NativeExecutionError, "native_runtime_route_mismatch"):
            self.complete()
        self.assertEqual(len(self.reservations), 1)
        self.assertEqual(len(self.requests), 1)

    def test_resolved_route_change_is_refused_before_reservation(self):
        for url in ("http://openrouter.ai/api/v1/", "https://wrong.invalid/api/v1/",
                    "https://openrouter.ai/api/v1/redirect", "https://user:secret@openrouter.ai/api/v1/"):
            with self.subTest(url=url):
                self.sdk.base_url = url
                with self.assertRaisesRegex(NativeExecutionError, "native_runtime_route_mismatch"):
                    self.complete()
        self.assertEqual(self.reservations, [])
        self.assertEqual(self.requests, [])

    def test_resolved_model_change_is_refused_before_reservation(self):
        self.resolved_model = "other-model"
        with self.assertRaisesRegex(NativeExecutionError, "native_runtime_route_mismatch"):
            self.complete()
        self.assertEqual(self.reservations, [])

    def test_unproven_sdk_client_is_refused_before_reservation(self):
        self.sdk = SimpleNamespace(base_url=STRICT_BASE_URL)
        with self.assertRaisesRegex(NativeExecutionError, "native_runtime_route_mismatch"):
            self.complete()
        self.assertEqual(self.reservations, [])

    def test_clone_that_reenables_retries_or_changes_endpoint_is_refused(self):
        self.clone_retries = 2
        with self.assertRaisesRegex(NativeExecutionError, "native_model_strict_transport_unproven"):
            self.complete()
        self.clone_retries = 0
        self.clone_url = "https://wrong.invalid/"
        with self.assertRaisesRegex(NativeExecutionError, "native_model_strict_transport_unproven"):
            self.complete()
        self.assertEqual(self.reservations, [])
        self.assertEqual(self.closes, [True, True])

    def test_constructor_rejects_route_retry_and_callback_changes(self):
        for change in ({"provider": "auto"}, {"provider": "other"}, {"model": "other"},
                       {"before_attempt": None}, {"max_attempts": 2}, {"max_attempts": True},
                       {"max_attempts": 0}, {"strict_budget": "true"}):
            with self.subTest(change=change), self.assertRaisesRegex(NativeExecutionError, "configuration_invalid"):
                self.model(**change)
        self.assertEqual(self.requests, [])

    def test_strict_mode_rejects_unbounded_legacy_call_injection(self):
        with self.assertRaisesRegex(NativeExecutionError, "native_model_strict_transport_required"):
            self.model(call=lambda **_kwargs: self.fail("not allowed"))

    def test_mutated_route_is_rechecked_before_resolution(self):
        model = self.model()
        model.model = "other"
        with self.assertRaisesRegex(NativeExecutionError, "configuration_invalid"):
            model.complete_structured(**self.args)
        self.assertEqual(self.resolve_options, [])

    def test_output_token_bounds_refuse_before_resolution(self):
        for value in (0, -1, 6001, True, 1.5, "6000"):
            with self.subTest(value=value), self.assertRaisesRegex(NativeExecutionError, "output_budget_invalid"):
                self.complete(max_tokens=value)
        self.assertEqual(self.resolve_options, [])

    def test_timeout_bounds_refuse_before_resolution(self):
        for value in (0, -1, 121, True, float("nan"), float("inf"), "60"):
            with self.subTest(value=value), self.assertRaisesRegex(NativeExecutionError, "timeout_invalid"):
                self.complete(timeout=value)
        self.assertEqual(self.resolve_options, [])

    def test_utf8_request_exact_boundary_includes_schema_and_controls(self):
        result = self.complete(instructions="", input=[])
        overhead = result.audit["input_bytes"]
        self.requests.clear(); self.reservations.clear()
        fill = "x" * (STRICT_REQUEST_BYTES - overhead)
        self.assertEqual(self.complete(instructions=fill, input=[]).audit["input_bytes"], STRICT_REQUEST_BYTES)
        with self.assertRaisesRegex(NativeExecutionError, "request_too_large"):
            self.complete(instructions=fill + "x", input=[])
        with self.assertRaisesRegex(NativeExecutionError, "request_too_large"):
            self.complete(instructions="é" * (STRICT_REQUEST_BYTES // 2), input=[])
        schema = copy.deepcopy(self.args["json_schema"])
        schema["description"] = "x" * STRICT_REQUEST_BYTES
        with self.assertRaisesRegex(NativeExecutionError, "request_too_large"):
            self.complete(json_schema=schema)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(len(self.reservations), 1)

    def test_nonserializable_or_nonfinite_schema_refuses_before_call(self):
        for value in (object(), float("nan")):
            schema = copy.deepcopy(self.args["json_schema"])
            schema["description"] = value
            with self.assertRaisesRegex(NativeExecutionError, "request_invalid"):
                self.complete(json_schema=schema)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.reservations, [])

    def test_callback_cannot_change_the_reserved_schema_body(self):
        def reserve(**record):
            self.args["json_schema"]["properties"]["ok"]["type"] = "string"
            return self.reserve(**record)
        result = self.model(before_attempt=reserve).complete_structured(**self.args)
        self.assertEqual(result.parsed, {"ok": True})
        self.assertEqual(self.requests[0]["response_format"]["json_schema"]["schema"]["properties"]["ok"]["type"], "boolean")

    def test_tools_or_multiple_choices_cannot_be_accepted(self):
        self.response.choices[0].message.tool_calls = [{"function": "forbidden"}]
        with self.assertRaisesRegex(NativeExecutionError, "response_invalid"):
            self.complete()
        self.response.choices[0].message.tool_calls = None
        self.response.choices *= 2
        with self.assertRaisesRegex(NativeExecutionError, "response_invalid"):
            self.complete()
        self.assertEqual(len(self.reservations), 2)
        self.assertEqual(len(self.requests), 2)

    def test_reported_output_over_budget_is_rejected_without_retry(self):
        self.response.usage.completion_tokens = 6001
        with self.assertRaisesRegex(NativeExecutionError, "output_budget_exceeded"):
            self.complete()
        self.assertEqual(len(self.reservations), 1)

    def test_unrecognized_request_options_refuse(self):
        with self.assertRaisesRegex(NativeExecutionError, "request_options_invalid"):
            self.complete(extra_body={"provider": {"allow_fallbacks": True}})
        self.assertEqual(self.requests, [])

    def test_invalid_task_refuses_before_any_attempt(self):
        with self.assertRaisesRegex(NativeExecutionError, "task_invalid"):
            self.complete(task="other")
        self.assertEqual(self.reservations, [])

    def test_missing_profile_scope_refuses_before_credentials_resolution(self):
        self.modules["hermes_cli.plugins"].__dict__.pop("_plugin_home_scope")
        with self.assertRaisesRegex(NativeExecutionError, "hermes_profile_scope_unavailable"):
            self.complete()
        self.assertEqual(self.resolve_options, [])

    def test_reservation_limit_is_durable_across_failed_completions(self):
        ledger = []
        def reserve(**record):
            if len(ledger) >= 8:
                raise NativeExecutionError("budget_exhausted")
            ledger.append(record)
        model = self.model(before_attempt=reserve)
        self.error = TimeoutError("uncertain")
        for _ in range(8):
            with self.assertRaisesRegex(NativeExecutionError, "inference_failed"):
                model.complete_structured(**self.args)
        with self.assertRaisesRegex(NativeExecutionError, "budget_exhausted"):
            model.complete_structured(**self.args)
        self.assertEqual(len(ledger), 8)
        self.assertEqual(len(self.requests), 8)

    def test_legacy_default_keeps_two_attempts_and_its_original_route_contract(self):
        calls = []
        def legacy_call(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise TimeoutError("legacy first attempt")
            kwargs["route_info"].update(provider=DEFAULT_PROVIDER, model=DEFAULT_MODEL)
            # Legacy accepts Hermes route_info, regardless of raw response model.
            self.response.model = "legacy-provider-model"
            return self.response
        model = HermesAuxiliaryModel(profile_home="synthetic-profile", call=legacy_call)
        result = model.complete_structured(**self.args)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["extra_body"].keys(), {"response_format"})
        self.assertEqual(result.provider, DEFAULT_PROVIDER)
        self.assertEqual(result.agent_id, "standalone")
        self.assertNotIn("strict_budget", result.audit)
        self.assertEqual(self.reservations, [])


if __name__ == "__main__":
    unittest.main()
