import json
import threading
import unittest
from unittest.mock import patch
from urllib import error as urllib_error

from modules.beacon.meta_ads_insights_preview import (
    AD_ACCOUNT_ID_ENV,
    ADS_READ_TOKEN_ENV,
    GRAPH_VERSION_ENV,
    MetaPreviewError,
    _PREVIEW_FLIGHTS,
    _http_get,
    _reset_meta_preview_singleflight_for_tests,
    _safe_request_fingerprint,
    build_meta_ads_insights_preview,
    meta_ads_preview_configuration,
)


class FakeMetaGetter:
    def __init__(self, *, insight_rows=None, paging=None):
        self.calls = []
        self.insight_rows = insight_rows if insight_rows is not None else [{
            "campaign_id": "CAMPAIGN-1",
            "adset_id": "ADSET-1",
            "ad_id": "AD-1",
            "date_start": "2025-11-10",
            "date_stop": "2026-07-14",
            "spend": "0",
            "reach": None,
            "impressions": "125",
            "clicks": "7",
            "inline_link_clicks": "0",
            "actions": [{"action_type": "onsite_conversion.messaging_conversation_started_7d", "value": "2"}],
            "attribution_setting": "7d_click_1d_view",
        }]
        self.paging = paging

    def __call__(self, url, *, headers, timeout):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        if url.endswith("?fields=id%2Cname%2Ccurrency%2Caccount_status"):
            return {"id": "act_123", "name": "Private account", "currency": "ZAR"}
        if "/campaigns?" in url:
            return {"data": [{"id": "CAMPAIGN-1", "name": "Old advert"}], **self._paging()}
        if "/adsets?" in url:
            return {"data": [{"id": "ADSET-1", "campaign_id": "CAMPAIGN-1"}], **self._paging()}
        if "/ads?" in url:
            return {"data": [{"id": "AD-1", "campaign_id": "CAMPAIGN-1", "adset_id": "ADSET-1"}], **self._paging()}
        if "/insights?" in url:
            return {"data": self.insight_rows, **self._paging()}
        raise AssertionError(f"Unexpected fake URL shape: {url.split('?')[0]}")

    def _paging(self):
        return {"paging": self.paging} if self.paging else {}


class BeaconMetaAdsInsightsPreviewTests(unittest.TestCase):
    def setUp(self):
        _reset_meta_preview_singleflight_for_tests()

    def config(self, account="act_123", token="SUPER-SECRET-TOKEN"):
        return {
            AD_ACCOUNT_ID_ENV: account,
            ADS_READ_TOKEN_ENV: token,
            GRAPH_VERSION_ENV: "v23.0",
        }

    def preview(self, getter=None, **kwargs):
        return build_meta_ads_insights_preview(
            environ=self.config(),
            http_get=getter or FakeMetaGetter(),
            now="2026-07-24T12:00:00Z",
            singleflight=False,
            **kwargs,
        )

    def test_configuration_contract_is_boolean_only_and_page_token_is_not_reused(self):
        secret = "DO-NOT-RETURN"
        config = meta_ads_preview_configuration({
            AD_ACCOUNT_ID_ENV: "123",
            ADS_READ_TOKEN_ENV: secret,
            GRAPH_VERSION_ENV: "v23.0",
            "BEACON_FACEBOOK_PAGE_ACCESS_TOKEN": "PAGE-SECRET",
        })

        serialized = json.dumps(config)
        self.assertTrue(config["configured"])
        self.assertFalse(config["contains_secret_values"])
        self.assertFalse(config["page_token_reused"])
        self.assertNotIn(secret, serialized)
        self.assertNotIn("PAGE-SECRET", serialized)
        self.assertEqual(
            config["environment_variables"],
            {
                "ad_account_id": AD_ACCOUNT_ID_ENV,
                "ads_read_token": ADS_READ_TOKEN_ENV,
                "graph_version": GRAPH_VERSION_ENV,
            },
        )

    def test_unconfigured_preview_does_not_call_meta(self):
        getter = FakeMetaGetter()

        result, status = build_meta_ads_insights_preview(
            environ={}, http_get=getter
        )

        self.assertEqual(status, 503)
        self.assertEqual(result["status"], "meta_ads_preview_not_configured")
        self.assertEqual(getter.calls, [])
        self.assertFalse(result["authority"]["imports_evidence"])
        self.assertEqual(
            result["metric_summary"]["spend"]["aggregate_status"],
            "not_yet_requested",
        )
        self.assertEqual(
            result["metric_summary"]["qualified_buyer_leads"]["aggregate_status"],
            "unsupported",
        )

    def test_get_urls_use_one_act_prefix_explicit_fields_and_bearer_header(self):
        getter = FakeMetaGetter()

        result, status = self.preview(getter)

        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "preview_ready")
        self.assertEqual(len(getter.calls), 5)
        urls = [call["url"] for call in getter.calls]
        self.assertTrue(all("/act_123" in url for url in urls))
        self.assertTrue(all("act_act_" not in url for url in urls))
        self.assertTrue(any("/campaigns?" in url for url in urls))
        self.assertTrue(any("/adsets?" in url for url in urls))
        self.assertTrue(any("/ads?" in url for url in urls))
        insight_url = next(url for url in urls if "/insights?" in url)
        self.assertIn("time_range=", insight_url)
        self.assertIn("level=ad", insight_url)
        self.assertIn("fields=", insight_url)
        self.assertNotIn("access_token", insight_url)
        self.assertTrue(all(
            call["headers"]["Authorization"] == "Bearer SUPER-SECRET-TOKEN"
            for call in getter.calls
        ))
        self.assertTrue(all(call["timeout"] == 12.0 for call in getter.calls))

    def test_default_and_bounded_owner_selected_reporting_windows(self):
        result, _ = self.preview()
        self.assertEqual(
            result["reporting_window"],
            {"start": "2025-11-10", "end": "2026-07-14", "level": "ad"},
        )

        custom, status = self.preview(
            start_date="2026-01-01", end_date="2026-01-31", level="campaign"
        )
        self.assertEqual(status, 200)
        self.assertEqual(custom["reporting_window"]["level"], "campaign")

        rejected, status = self.preview(
            start_date="2023-01-01", end_date="2026-01-31"
        )
        self.assertEqual(status, 400)
        self.assertEqual(rejected["status"], "reporting_range_too_large")
        malformed, status = self.preview(start_date="not-a-date")
        self.assertEqual(status, 400)
        self.assertEqual(malformed["status"], "invalid_reporting_date")

    def test_verified_zero_remains_zero_while_missing_and_malformed_remain_distinct(self):
        result, _ = self.preview()
        event = result["proposed_append_only_events"][0]

        self.assertEqual(event["metrics"]["spend"]["status"], "verified")
        self.assertEqual(event["metrics"]["spend"]["value"], 0)
        self.assertEqual(event["metrics"]["reach"]["status"], "missing")
        self.assertIsNone(event["metrics"]["reach"]["value"])
        self.assertEqual(event["metrics"]["inline_link_clicks"]["value"], 0)
        self.assertEqual(
            result["metric_summary"]["spend"]["verified_zero_row_count"], 1
        )
        self.assertIsNone(result["metric_summary"]["reach"]["aggregate_value"])

        malformed, _ = self.preview(FakeMetaGetter(insight_rows=[{
            "ad_id": "AD-2", "date_start": "2026-01-01",
            "date_stop": "2026-01-31", "spend": "not-a-number",
        }]))
        self.assertEqual(
            malformed["proposed_append_only_events"][0]["metrics"]["spend"]["status"],
            "malformed",
        )

    def test_actions_never_become_leads_sales_or_revenue(self):
        result, _ = self.preview()
        event = result["proposed_append_only_events"][0]

        self.assertEqual(
            event["actions"]["items"][0]["classification"],
            "meta_reported_action_only",
        )
        for name in ("qualified_buyer_leads", "orders", "sales", "revenue"):
            self.assertEqual(event[name]["status"], "unsupported")
            self.assertIsNone(event[name]["value"])
        self.assertIn(
            "not_leads_sales_or_revenue",
            result["action_results"]["classification"],
        )

    def test_proposed_event_has_append_only_provenance_and_stable_key(self):
        first, _ = self.preview()
        second, _ = self.preview()
        event = first["proposed_append_only_events"][0]

        self.assertEqual(
            event["idempotency_key"],
            second["proposed_append_only_events"][0]["idempotency_key"],
        )
        self.assertEqual(event["source"], "meta_ads_insights")
        self.assertEqual(event["currency"], {"status": "verified", "value": "ZAR"})
        self.assertEqual(event["retrieved_at"], "2026-07-24T12:00:00+00:00")
        self.assertEqual(first["idempotency_preview"]["duplicate_key_count"], 0)
        self.assertFalse(first["future_backfill"]["executes_now"])
        self.assertIn("64 legacy rows", first["future_backfill"]["legacy_reconciliation"])
        self.assertFalse(
            first["connection"]["configured_ad_account_identifier_exposed"]
        )
        self.assertNotIn("identifiers_exposed", first["connection"])

    def test_page_and_record_bounds_report_partial_without_unbounded_fetch(self):
        class BoundGetter(FakeMetaGetter):
            def __call__(self, url, *, headers, timeout):
                result = super().__call__(url, headers=headers, timeout=timeout)
                result["paging"] = {
                    "next": (
                        url.split("?", 1)[0]
                        + "?after=NEXT&access_token=PAGE-SECRET"
                    )
                }
                return result

        getter = BoundGetter()

        result, status = self.preview(getter, max_pages=1, max_records=10)

        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["limits"]["partial"])
        self.assertEqual(
            result["metric_summary"]["spend"]["aggregate_status"], "partial"
        )
        self.assertLessEqual(len(getter.calls), 5)
        self.assertNotIn("PAGE-SECRET", json.dumps(result))

    def test_repeated_paging_url_is_detected_and_token_is_never_returned(self):
        class RepeatedGetter(FakeMetaGetter):
            def __call__(self, url, *, headers, timeout):
                result = super().__call__(url, headers=headers, timeout=timeout)
                path = url.split("?", 1)[0]
                result["paging"] = {
                    "next": path + "?page=SAME&access_token=PAGING-SECRET"
                }
                return result

        result, _ = self.preview(RepeatedGetter(), max_pages=4)
        serialized = json.dumps(result)

        self.assertEqual(result["status"], "partial")
        self.assertIn("repeated_paging_url", serialized)
        self.assertNotIn("PAGING-SECRET", serialized)
        self.assertNotIn("SUPER-SECRET-TOKEN", serialized)

    def test_repeated_paging_cursor_is_detected_even_if_url_changes(self):
        class CursorGetter(FakeMetaGetter):
            def __init__(self):
                super().__init__()
                self.sequence = 0

            def __call__(self, url, *, headers, timeout):
                result = super().__call__(url, headers=headers, timeout=timeout)
                self.sequence += 1
                path = url.split("?", 1)[0]
                result["paging"] = {
                    "cursors": {"after": "REPEATED"},
                    "next": f"{path}?after=REPEATED&page={self.sequence}",
                }
                return result

        result, _ = self.preview(CursorGetter(), max_pages=4)

        self.assertEqual(result["status"], "partial")
        self.assertIn("repeated_paging_cursor", json.dumps(result))

    def test_permission_rate_limit_api_and_injected_secret_errors_are_safe(self):
        for error, expected in (
            (MetaPreviewError("permission_denied", http_status=403), "permission_denied"),
            (MetaPreviewError("rate_limited", http_status=429), "rate_limited"),
            (MetaPreviewError("api_failed"), "api_failed"),
        ):
            def failing_getter(url, *, headers, timeout, failure=error):
                raise failure

            result, status = self.preview(failing_getter)
            self.assertEqual(status, 200)
            self.assertEqual(result["status"], "partial")
            self.assertEqual(
                result["resource_diagnostics"]["insights"]["status"], expected
            )
            self.assertNotIn("SUPER-SECRET-TOKEN", json.dumps(result))

        def arbitrary_failure(url, *, headers, timeout):
            raise RuntimeError("failure includes SUPER-SECRET-TOKEN")

        result, _ = self.preview(arbitrary_failure)
        self.assertNotIn("SUPER-SECRET-TOKEN", json.dumps(result))

    def test_total_deadline_stops_pages_and_marks_remaining_resources(self):
        class FakeClock:
            value = 100.0

            def __call__(self):
                return self.value

            def advance(self, seconds):
                self.value += seconds

        clock = FakeClock()
        getter = FakeMetaGetter()
        original = getter.__call__

        def timed_get(url, *, headers, timeout):
            payload = original(url, headers=headers, timeout=timeout)
            clock.advance(min(0.6, timeout))
            return payload

        result, status = self.preview(
            timed_get,
            clock=clock,
            total_timeout_seconds=1,
            timeout_seconds=12,
        )

        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(getter.calls), 2)
        self.assertEqual(getter.calls[0]["timeout"], 1.0)
        self.assertAlmostEqual(getter.calls[1]["timeout"], 0.4, places=6)
        diagnostics = result["resource_diagnostics"]
        self.assertEqual(diagnostics["account"]["status"], "verified")
        self.assertEqual(diagnostics["campaigns"]["status"], "timed_out")
        for name in ("adsets", "ads", "insights"):
            self.assertEqual(
                diagnostics[name]["status"],
                "not_attempted_due_to_total_deadline",
            )
        self.assertTrue(result["limits"]["total_deadline_exhausted"])
        self.assertEqual(result["limits"]["total_elapsed_seconds"], 1.0)
        self.assertEqual(
            result["metric_summary"]["spend"]["aggregate_status"],
            "not_attempted_due_to_total_deadline",
        )
        self.assertIsNone(result["metric_summary"]["spend"]["aggregate_value"])

    def test_singleflight_prevents_duplicate_worker_and_returns_cached_success(self):
        entered = threading.Event()
        release = threading.Event()
        getter = FakeMetaGetter()
        original = getter.__call__

        def blocking_get(url, *, headers, timeout):
            if not getter.calls:
                entered.set()
                release.wait(5)
            return original(url, headers=headers, timeout=timeout)

        first_result = []

        def run_first():
            first_result.append(build_meta_ads_insights_preview(
                environ=self.config(),
                http_get=blocking_get,
                now="2026-07-24T12:00:00Z",
            ))

        worker = threading.Thread(target=run_first)
        worker.start()
        self.assertTrue(entered.wait(2))
        repeated, status = build_meta_ads_insights_preview(
            environ=self.config(),
            http_get=blocking_get,
            now="2026-07-24T12:00:00Z",
        )
        self.assertEqual(status, 202)
        self.assertEqual(repeated["status"], "in_progress")
        self.assertEqual(len(getter.calls), 0)
        release.set()
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(first_result[0][0]["status"], "preview_ready")
        self.assertEqual(len(getter.calls), 5)

        cached, status = build_meta_ads_insights_preview(
            environ=self.config(),
            http_get=lambda *args, **kwargs: self.fail("cache started a read"),
            now="2026-07-24T12:00:00Z",
        )
        self.assertEqual(status, 200)
        self.assertEqual(cached["concurrency"]["status"], "cached")
        self.assertEqual(len(getter.calls), 5)

    def test_success_cache_and_failure_cooldown_expire_without_queue(self):
        class FakeClock:
            value = 10.0

            def __call__(self):
                return self.value

            def advance(self, seconds):
                self.value += seconds

        clock = FakeClock()
        getter = FakeMetaGetter()
        first, _ = build_meta_ads_insights_preview(
            environ=self.config(), http_get=getter, clock=clock
        )
        self.assertEqual(first["concurrency"]["status"], "executed")
        calls = len(getter.calls)
        cached, _ = build_meta_ads_insights_preview(
            environ=self.config(), http_get=getter, clock=clock
        )
        self.assertEqual(cached["concurrency"]["status"], "cached")
        self.assertEqual(len(getter.calls), calls)
        clock.advance(15.1)
        refreshed, _ = build_meta_ads_insights_preview(
            environ=self.config(), http_get=getter, clock=clock
        )
        self.assertEqual(refreshed["concurrency"]["status"], "executed")
        self.assertGreater(len(getter.calls), calls)

        _reset_meta_preview_singleflight_for_tests()
        failures = {"count": 0}

        def failing_get(url, *, headers, timeout):
            failures["count"] += 1
            raise MetaPreviewError("api_failed")

        failed, _ = build_meta_ads_insights_preview(
            environ=self.config(), http_get=failing_get, clock=clock
        )
        self.assertEqual(failed["status"], "partial")
        failure_calls = failures["count"]
        cooled, _ = build_meta_ads_insights_preview(
            environ=self.config(), http_get=failing_get, clock=clock
        )
        self.assertEqual(cooled["status"], "cooling_down")
        self.assertEqual(cooled["concurrency"]["status"], "cooling_down")
        self.assertEqual(failures["count"], failure_calls)
        clock.advance(2.1)
        build_meta_ads_insights_preview(
            environ=self.config(), http_get=failing_get, clock=clock
        )
        self.assertGreater(failures["count"], failure_calls)

    def test_singleflight_fingerprint_is_configuration_isolated_and_secret_safe(self):
        dimensions = {
            "start_date": None, "end_date": None, "level": "ad",
            "timeout_seconds": 12, "total_timeout_seconds": 25,
            "max_pages": 10, "max_records": 500,
        }
        first = _safe_request_fingerprint(
            self.config(account="111", token="TOKEN-ONE"),
            **dimensions,
        )
        equivalent = _safe_request_fingerprint(
            self.config(account="act_111", token="TOKEN-ONE"),
            **dimensions,
        )
        changed_account = _safe_request_fingerprint(
            self.config(account="999", token="TOKEN-ONE"),
            **dimensions,
        )
        changed_token = _safe_request_fingerprint(
            self.config(account="111", token="TOKEN-TWO"),
            **dimensions,
        )
        self.assertEqual(first, equivalent)
        self.assertNotEqual(first, changed_account)
        self.assertNotEqual(first, changed_token)
        self.assertNotIn("111", first)
        self.assertNotIn("TOKEN-ONE", first)

        result, _ = build_meta_ads_insights_preview(
            environ=self.config(account="111", token="TOKEN-ONE"),
            http_get=FakeMetaGetter(),
        )
        serialized = json.dumps({
            "concurrency": result["concurrency"],
            "cache_state": _PREVIEW_FLIGHTS,
        })
        self.assertNotIn("111", serialized)
        self.assertNotIn("TOKEN-ONE", serialized)
        self.assertFalse(
            result["concurrency"]["raw_configured_identifier_in_fingerprint"]
        )
        self.assertFalse(result["concurrency"]["raw_token_in_fingerprint"])
        self.assertTrue(
            result["concurrency"]["configuration_isolated_fingerprint"]
        )
        self.assertFalse(result["concurrency"]["fingerprint_exposed"])

    def test_cached_result_is_not_shared_after_account_or_token_rotation(self):
        first_getter = FakeMetaGetter()
        first, status = build_meta_ads_insights_preview(
            environ=self.config(account="111", token="TOKEN-ONE"),
            http_get=first_getter,
        )
        self.assertEqual(status, 200)
        self.assertEqual(first["concurrency"]["status"], "executed")
        self.assertEqual(len(first_getter.calls), 5)

        account_getter = FakeMetaGetter()
        account_changed, status = build_meta_ads_insights_preview(
            environ=self.config(account="999", token="TOKEN-ONE"),
            http_get=account_getter,
        )
        self.assertEqual(status, 200)
        self.assertEqual(account_changed["concurrency"]["status"], "executed")
        self.assertEqual(len(account_getter.calls), 5)

        token_getter = FakeMetaGetter()
        token_changed, status = build_meta_ads_insights_preview(
            environ=self.config(account="111", token="TOKEN-TWO"),
            http_get=token_getter,
        )
        self.assertEqual(status, 200)
        self.assertEqual(token_changed["concurrency"]["status"], "executed")
        self.assertEqual(len(token_getter.calls), 5)

    def test_http_400_meta_error_mapping_uses_codes_not_raw_messages(self):
        cases = (
            (
                {"message": "expired SUPER-SECRET-TOKEN", "type": "OAuthException",
                 "code": 190, "error_subcode": 463},
                "invalid_or_expired_token",
            ),
            (
                {"message": "permission denied", "type": "OAuthException", "code": 10},
                "permission_denied",
            ),
            (
                {"message": "rate limit", "type": "OAuthException", "code": 4},
                "rate_limited",
            ),
            (
                {"message": "bad field", "type": "OAuthException", "code": 100},
                "invalid_field_or_request",
            ),
        )
        for error_payload, expected in cases:
            error = urllib_error.HTTPError(
                "https://graph.facebook.com/path?access_token=URL-SECRET",
                400, "Bad Request", {}, None,
            )
            error.read = lambda payload=error_payload: json.dumps(
                {"error": payload}
            ).encode()
            with patch(
                "modules.beacon.meta_ads_insights_preview.urllib_request.urlopen",
                side_effect=error,
            ):
                with self.assertRaises(MetaPreviewError) as context:
                    _http_get(
                        "https://graph.facebook.com/v23.0/act_123/insights",
                        headers={"Authorization": "Bearer SUPER-SECRET-TOKEN"},
                        timeout=4,
                    )
            exc = context.exception
            self.assertEqual(exc.status, expected)
            self.assertEqual(exc.http_status, 400)
            self.assertEqual(exc.meta_code, error_payload["code"])
            self.assertEqual(exc.meta_type, "OAuthException")
            self.assertEqual(
                exc.meta_subcode, error_payload.get("error_subcode")
            )
            self.assertNotIn("SECRET", str(exc))
            self.assertNotIn("permission denied", str(exc))

    def test_optional_attribution_field_retries_once_and_only_for_exact_error(self):
        getter = FakeMetaGetter()
        original = getter.__call__
        insight_calls = []

        def optional_field_get(url, *, headers, timeout):
            if "/insights?" in url:
                insight_calls.append(url)
                if len(insight_calls) == 1:
                    raise MetaPreviewError(
                        "invalid_optional_field",
                        http_status=400,
                        meta_code=100,
                        meta_type="OAuthException",
                        optional_field="attribution_setting",
                    )
            return original(url, headers=headers, timeout=timeout)

        result, _ = self.preview(optional_field_get)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(insight_calls), 2)
        self.assertIn("attribution_setting", insight_calls[0])
        self.assertNotIn("attribution_setting", insight_calls[1])
        diagnostic = result["resource_diagnostics"]["insights"]
        self.assertTrue(diagnostic["optional_field_retry_performed"])
        event = result["proposed_append_only_events"][0]
        self.assertEqual(event["attribution"]["status"], "unsupported")
        self.assertIsNone(event["attribution"]["setting"])

        for failure in (
            "permission_denied", "invalid_or_expired_token", "rate_limited",
            "invalid_field_or_request", "api_failed",
        ):
            calls = {"insights": 0}

            def no_retry(url, *, headers, timeout, status=failure):
                if "/insights?" in url:
                    calls["insights"] += 1
                    raise MetaPreviewError(status, http_status=400)
                return FakeMetaGetter()(url, headers=headers, timeout=timeout)

            self.preview(no_retry)
            self.assertEqual(calls["insights"], 1, failure)

    def test_http_400_optional_field_classification_does_not_expose_body(self):
        body = {
            "error": {
                "message": "(#100) attribution_setting is not valid. SUPER-SECRET",
                "type": "OAuthException",
                "code": 100,
            }
        }
        error = urllib_error.HTTPError(
            "https://graph.facebook.com/path?access_token=URL-SECRET",
            400, "Bad Request", {}, None,
        )
        error.read = lambda: json.dumps(body).encode()
        with patch(
            "modules.beacon.meta_ads_insights_preview.urllib_request.urlopen",
            side_effect=error,
        ):
            with self.assertRaises(MetaPreviewError) as context:
                _http_get(
                    "https://graph.facebook.com/v23.0/act_123/insights",
                    headers={"Authorization": "Bearer SUPER-SECRET"},
                    timeout=4,
                )
        exc = context.exception
        self.assertEqual(exc.status, "invalid_optional_field")
        self.assertEqual(exc.optional_field, "attribution_setting")
        self.assertNotIn("SUPER-SECRET", str(exc))

    def test_default_http_adapter_constructs_get_and_sanitizes_http_error(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return b'{"data":[]}'

        with patch(
            "modules.beacon.meta_ads_insights_preview.urllib_request.urlopen",
            return_value=Response(),
        ) as opener:
            payload = _http_get(
                "https://graph.facebook.com/v23.0/act_123/insights",
                headers={"Authorization": "Bearer SECRET"},
                timeout=4,
            )

        request = opener.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(payload, {"data": []})

        error = urllib_error.HTTPError(
            "https://graph.facebook.com/path?access_token=SECRET",
            403,
            "Forbidden",
            {},
            None,
        )
        error.read = lambda: b'{"error":{"message":"SECRET","code":200}}'
        with patch(
            "modules.beacon.meta_ads_insights_preview.urllib_request.urlopen",
            side_effect=error,
        ):
            with self.assertRaises(MetaPreviewError) as context:
                _http_get(
                    "https://graph.facebook.com/v23.0/act_123/insights",
                    headers={"Authorization": "Bearer SECRET"},
                    timeout=4,
                )
        self.assertEqual(context.exception.status, "permission_denied")
        self.assertNotIn("SECRET", str(context.exception))

    def test_every_authority_flag_prohibits_writes_and_spend(self):
        result, _ = self.preview()

        self.assertTrue(result["authority"]["read_only"])
        self.assertTrue(result["authority"]["http_get_only"])
        self.assertTrue(result["authority"]["calls_meta_read"])
        for name, value in result["authority"].items():
            if name not in {"read_only", "http_get_only", "calls_meta_read"}:
                self.assertFalse(value, name)


if __name__ == "__main__":
    unittest.main()
