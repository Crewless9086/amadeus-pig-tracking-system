"""Shared, fail-closed farm OpenAI admission on the existing append-only audit rail.

Only priced plain-text Chat Completions are supported. A committed SAST-day
reservation precedes every provider request. Unknown outcomes keep that reserve.
No prompt, response text, credential or exception body is stored in the ledger.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
import io
import json
import os
import re
import time
from urllib import error as urllib_error, request as urllib_request
from urllib.parse import urlsplit
from uuid import uuid4

from modules.oom_sakkie.bounded_postgres_read import connect_bounded_postgres

DAY_CAP_MICRO_USD = 1_000_000
MAX_INPUT_BYTES = 100_000
MAX_MESSAGES = 32
FRAMING_TOKEN_ALLOWANCE = 2048
MAX_COMPLETION_TOKENS = 2048
MAX_RESPONSE_BYTES = 1_048_576
EVENT_SOURCE = "farm_openai_budget"
POLICY_VERSION = "farm_openai_text_budget.v1.2026-09-23"
LOCK_NAMESPACE = 184902731
# USD per million tokens; numerically also micro-USD per token. Verified:
# https://developers.openai.com/api/docs/models/gpt-5.4-mini
# https://developers.openai.com/api/docs/models/gpt-4.1-mini
# https://developers.openai.com/api/docs/models/gpt-4o-mini
_MODELS = {
    "gpt-5.4-mini": ("gpt-5.4-mini-2026-03-17", "0.75", "0.075", "4.50"),
    "gpt-4.1-mini": ("gpt-4.1-mini-2025-04-14", "0.40", "0.10", "1.60"),
    "gpt-4o-mini": ("gpt-4o-mini-2024-07-18", "0.15", "0.075", "0.60"),
}
PRICING = {key: value for alias, value in _MODELS.items() for key in (alias, value[0])}
_PURPOSE = re.compile(r"[a-z][a-z0-9_.:-]{0,95}\Z")
_ATTEMPT = re.compile(r"[0-9a-f]{32}\Z")
_ALLOWED_FIELDS = frozenset({"model", "messages", "temperature", "top_p", "seed",
    "frequency_penalty", "presence_penalty", "stop", "response_format", "reasoning_effort",
    "max_tokens", "max_completion_tokens", "n", "stream", "service_tier"})


class ModelBudgetError(urllib_error.URLError):
    """Safe status only; existing provider-unavailable handlers can contain it."""
    def __init__(self, status):
        self.status = status
        super().__init__(status)


def _integer(value, *, maximum=None):
    if type(value) is not int or value < 0 or (maximum is not None and value > maximum):
        raise ModelBudgetError("farm_model_budget_invalid_accounting")
    return value


def _cost(model, prompt, completion, cached=0):
    _, input_rate, cached_rate, output_rate = PRICING[model]
    return int(((Decimal(prompt - cached) * Decimal(input_rate))
        + Decimal(cached) * Decimal(cached_rate)
        + Decimal(completion) * Decimal(output_rate)).to_integral_value(rounding=ROUND_CEILING))


def _prepare(request, purpose):
    if not isinstance(request, urllib_request.Request) or not _PURPOSE.fullmatch(str(purpose)):
        raise ModelBudgetError("farm_model_budget_request_invalid")
    try:
        url = urlsplit(request.full_url)
        endpoint_ok = (url.scheme == "https" and url.hostname == "api.openai.com"
            and url.port in (None, 443) and not url.username and not url.password
            and url.path == "/v1/chat/completions" and not url.query and not url.fragment)
    except ValueError:
        endpoint_ok = False
    if not endpoint_ok or request.get_method() != "POST":
        raise ModelBudgetError("farm_model_budget_endpoint_unpriced")
    raw = request.data
    if not isinstance(raw, bytes) or len(raw) > MAX_INPUT_BYTES:
        raise ModelBudgetError("farm_model_budget_input_limit")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise ModelBudgetError("farm_model_budget_request_invalid") from None
    if not isinstance(payload, dict) or set(payload) - _ALLOWED_FIELDS:
        raise ModelBudgetError("farm_model_budget_request_unpriced")
    model = payload.get("model")
    if not isinstance(model, str) or model not in PRICING:
        raise ModelBudgetError("farm_model_budget_model_unpriced")
    messages = payload.get("messages")
    if not isinstance(messages, list) or not 1 <= len(messages) <= MAX_MESSAGES:
        raise ModelBudgetError("farm_model_budget_messages_invalid")
    for message in messages:
        if (not isinstance(message, dict) or set(message) - {"role", "content", "name"}
                or message.get("role") not in {"system", "developer", "user", "assistant"}
                or not isinstance(message.get("content"), str)
                or ("name" in message and (not isinstance(message["name"], str)
                                            or len(message["name"]) > 64))):
            raise ModelBudgetError("farm_model_budget_multimodal_unpriced")
    if (payload.get("n", 1) != 1 or type(payload.get("n", 1)) is not int
            or payload.get("stream", False) is not False
            or payload.get("service_tier", "default") != "default"):
        raise ModelBudgetError("farm_model_budget_request_unpriced")
    limits = [payload[key] for key in ("max_tokens", "max_completion_tokens") if key in payload]
    if len(limits) > 1 or (limits and (type(limits[0]) is not int or not 1 <= limits[0] <= MAX_COMPLETION_TOKENS)):
        raise ModelBudgetError("farm_model_budget_output_limit")
    maximum = limits[0] if limits else MAX_COMPLETION_TOKENS
    snapshot = PRICING[model][0]
    payload["model"] = snapshot
    payload.pop("max_tokens", None)
    payload.pop("max_completion_tokens", None)
    payload["max_completion_tokens" if snapshot.startswith("gpt-5") else "max_tokens"] = maximum
    payload["service_tier"] = "default"
    try:
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError):
        raise ModelBudgetError("farm_model_budget_request_invalid") from None
    if len(body) > MAX_INPUT_BYTES:
        raise ModelBudgetError("farm_model_budget_input_limit")
    # Restricted text only: one token per UTF-8/JSON byte plus a generous fixed
    # framing allowance for <=32 messages. No image, tool, audio or hidden tool fee.
    input_bound = len(body) + FRAMING_TOKEN_ALLOWANCE
    prepared = urllib_request.Request(request.full_url, data=body,
        headers={k: v for k, v in request.header_items()
                 if k.lower() not in {"content-length", "transfer-encoding", "host"}}, method="POST")
    metadata = {"attempt_id": uuid4().hex, "purpose": purpose, "model": snapshot,
        "policy": POLICY_VERSION, "input_token_bound": input_bound,
        "output_token_bound": maximum, "reserved_micro_usd": _cost(snapshot, input_bound, maximum)}
    return prepared, metadata


def _validated_usage(body, reservation):
    try:
        envelope = json.loads(body)
        if envelope.get("model") != reservation["model"]:
            return None
        usage = envelope["usage"]
        prompt = _integer(usage["prompt_tokens"], maximum=reservation["input_token_bound"])
        completion = _integer(usage["completion_tokens"], maximum=reservation["output_token_bound"])
        if _integer(usage["total_tokens"]) != prompt + completion:
            return None
        details = usage.get("prompt_tokens_details") or {}
        cached = _integer(details.get("cached_tokens", 0), maximum=prompt)
        charged = _cost(reservation["model"], prompt, completion, cached)
        if charged > reservation["reserved_micro_usd"]:
            return None
        return {"prompt_tokens": prompt, "completion_tokens": completion,
            "cached_tokens": cached, "charged_micro_usd": charged,
            "returned_model": envelope["model"],
            "reasoning_tokens": _integer((usage.get("completion_tokens_details") or {}).get(
                "reasoning_tokens", 0), maximum=completion)}
    except (KeyError, TypeError, ValueError, AttributeError, ModelBudgetError):
        return None


class BufferedResponse(io.BytesIO):
    def __init__(self, body, *, status=200, headers=None, url=""):
        super().__init__(body)
        self.status, self.headers, self.url = status, headers or {}, url
    def getcode(self): return self.status
    def geturl(self): return self.url
    def info(self): return self.headers


class _NoRedirect(urllib_request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ModelBudgetError("farm_model_budget_redirect_denied")


def _open_no_redirect(request, timeout):
    return urllib_request.build_opener(_NoRedirect()).open(request, timeout=timeout)


def _default_store(environ):
    """Explicit ledger injection seam; fake transports never bypass accounting."""
    source = environ if environ is not None else os.environ
    return PostgresBudgetStore(database_url=str(source.get("DATABASE_URL") or ""))


def budgeted_urlopen(request, *, timeout, purpose, environ=None, http_open=None, store=None):
    prepared, metadata = _prepare(request, purpose)
    ledger = store if store is not None else _default_store(environ)
    try:
        reservation = ledger.reserve(metadata)
        if (not isinstance(reservation, dict) or reservation.get("created") is not True
                or any(reservation.get(key) != value for key, value in metadata.items())):
            raise ModelBudgetError("farm_model_budget_reservation_unproven")
    except ModelBudgetError:
        raise
    except Exception:
        raise ModelBudgetError("farm_model_budget_store_unavailable") from None
    opener = http_open if http_open is not None else _open_no_redirect
    started = time.monotonic()
    # No retries/refund on errors: reservation committed before entering opener.
    with opener(prepared, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        body = response.read(MAX_RESPONSE_BYTES + 1)
        headers = getattr(response, "headers", {})
    if not isinstance(body, bytes) or len(body) > MAX_RESPONSE_BYTES:
        raise ModelBudgetError("farm_model_budget_response_unbounded")
    usage = _validated_usage(body, reservation)
    if usage is not None and status == 200:
        provider_id = str(headers.get("x-request-id") or "")
        usage.update({"latency_ms": max(0, int((time.monotonic() - started) * 1000)),
            "provider_request_id": provider_id if re.fullmatch(r"[A-Za-z0-9_-]{1,200}", provider_id) else ""})
        try:
            ledger.settle(reservation, usage)
        except Exception:
            # The durable reservation remains the conservative charge. Provider
            # output can still be consumed; no second request is authorized here.
            pass
    return BufferedResponse(body, status=status, headers=headers, url=prepared.full_url)


def _aggregate(rows):
    reservations, settlements = {}, {}
    for (event,) in rows:
        if not isinstance(event, dict) or event.get("policy") != POLICY_VERSION:
            raise ModelBudgetError("farm_model_budget_history_invalid")
        identity = event.get("attempt_id")
        if not isinstance(identity, str) or not _ATTEMPT.fullmatch(identity):
            raise ModelBudgetError("farm_model_budget_history_invalid")
        target = reservations if event.get("state") == "reserved" else settlements if event.get("state") == "settled" else None
        if target is None or identity in target:
            raise ModelBudgetError("farm_model_budget_history_invalid")
        target[identity] = event
    total = 0
    for identity, reserve in reservations.items():
        amount = _integer(reserve["reserved_micro_usd"])
        settled = settlements.pop(identity, None)
        if settled is not None:
            if any(settled.get(key) != reserve.get(key) for key in (
                    "model", "purpose", "day", "input_token_bound", "output_token_bound", "reserved_micro_usd")):
                raise ModelBudgetError("farm_model_budget_history_invalid")
            amount = _integer(settled["charged_micro_usd"], maximum=amount)
        total += amount
    if settlements:
        raise ModelBudgetError("farm_model_budget_history_invalid")
    return total, reservations


class PostgresBudgetStore:
    """Only append-only metadata writes, all decisions serialized before HTTP."""
    def __init__(self, *, database_url, connect_factory=None):
        self.database_url = database_url
        self.connect_factory = connect_factory

    def _connect(self):
        if self.connect_factory is not None:
            return self.connect_factory()
        if not self.database_url:
            raise ModelBudgetError("farm_model_budget_store_unavailable")
        return connect_bounded_postgres(database_url=self.database_url,
            connect_deadline_seconds=3)

    @staticmethod
    def _begin(cursor):
        cursor.execute("set transaction isolation level read committed")
        cursor.execute("set local statement_timeout='3000ms'")
        cursor.execute("set local lock_timeout='1000ms'")

    @staticmethod
    def _lock(cursor, day):
        cursor.execute("select pg_advisory_xact_lock(%s,%s)",
            (LOCK_NAMESPACE, int(day.replace("-", ""))))

    @staticmethod
    def _rows(cursor, day):
        cursor.execute("""select review_json from public.sam_live_stock_conversation_review_events
            where event_source=%s and chatwoot_conversation_id=%s""",
            (EVENT_SOURCE, "FARM-OPENAI-BUDGET:" + day))
        return cursor.fetchall()

    @staticmethod
    def _insert(cursor, event):
        suffix = "RESERVE" if event["state"] == "reserved" else "SETTLE"
        identity = "FARM-OPENAI-" + event["attempt_id"] + "-" + suffix
        cursor.execute("""insert into public.sam_live_stock_conversation_review_events
            (review_event_id,chatwoot_conversation_id,channel,source_agent,event_source,review_json)
            values (%s,%s,'internal','farm_model_budget',%s,%s::jsonb)
            on conflict (review_event_id) do nothing returning review_event_id""",
            (identity, "FARM-OPENAI-BUDGET:" + event["day"], EVENT_SOURCE,
             json.dumps(event, sort_keys=True, separators=(",", ":"))))
        if not cursor.fetchone():
            raise ModelBudgetError("farm_model_budget_event_conflict")

    def reserve(self, metadata):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._begin(cursor)
                cursor.execute("select (clock_timestamp() at time zone 'Africa/Johannesburg')::date::text")
                day = cursor.fetchone()[0]
                self._lock(cursor, day)
                cursor.execute("select (clock_timestamp() at time zone 'Africa/Johannesburg')::date::text")
                if cursor.fetchone()[0] != day:
                    raise ModelBudgetError("farm_model_budget_day_changed")
                total, existing = _aggregate(self._rows(cursor, day))
                amount = _integer(metadata["reserved_micro_usd"], maximum=DAY_CAP_MICRO_USD)
                if metadata["attempt_id"] in existing:
                    raise ModelBudgetError("farm_model_budget_attempt_replayed")
                if total + amount > DAY_CAP_MICRO_USD:
                    raise ModelBudgetError("farm_model_daily_budget_exhausted")
                event = {**metadata, "day": day, "state": "reserved"}
                self._insert(cursor, event)
        # Connection context exits successfully (commit) before authorizing HTTP.
        return {**event, "created": True}

    def report(self):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("set transaction read only")
                cursor.execute("set local statement_timeout='3000ms'")
                cursor.execute("select (clock_timestamp() at time zone 'Africa/Johannesburg')::date::text")
                day = cursor.fetchone()[0]
                rows = self._rows(cursor, day)
                total, reservations = _aggregate(rows)
                settled = {event["attempt_id"]: event for (event,) in rows if event["state"] == "settled"}
                spent = sum(event["charged_micro_usd"] for event in settled.values())
        return {"status": "farm_model_budget_ready", "day": day, "timezone": "Africa/Johannesburg",
            "cap_micro_usd": DAY_CAP_MICRO_USD, "spent_micro_usd": spent,
            "reserved_micro_usd": total - spent, "remaining_micro_usd": max(0, DAY_CAP_MICRO_USD - total),
            "reason_counts": {"settled": len(settled),
                "in_flight_or_unknown_outcome": len(reservations) - len(settled)}}

    def settle(self, reservation, usage):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._begin(cursor)
                self._lock(cursor, reservation["day"])
                rows = self._rows(cursor, reservation["day"])
                _, existing = _aggregate(rows)
                stored = existing.get(reservation["attempt_id"])
                if not stored or any(stored.get(k) != v for k, v in reservation.items() if k != "created"):
                    raise ModelBudgetError("farm_model_budget_reservation_conflict")
                _integer(usage["charged_micro_usd"], maximum=stored["reserved_micro_usd"])
                event = {**stored, **usage, "state": "settled"}
                prior = [row[0] for row in rows if row[0].get("state") == "settled"
                         and row[0].get("attempt_id") == reservation["attempt_id"]]
                if prior:
                    if prior != [event]:
                        raise ModelBudgetError("farm_model_budget_settlement_conflict")
                    return {"created": False}
                self._insert(cursor, event)
        return {"created": True}


class BufferedRequestsResponse:
    """Small requests-compatible view; the provider has already been called once."""
    def __init__(self, buffered):
        self.content = buffered.read()
        self.status_code = buffered.status
        self.headers = buffered.headers
        self.url = buffered.url
    def json(self): return json.loads(self.content)
    def raise_for_status(self):
        if not 200 <= self.status_code < 300:
            import requests
            raise requests.HTTPError("farm_model_provider_http_error", response=self)


def budgeted_requests_post(url, *, purpose, environ=None, http_client=None, **kwargs):
    """Route a requests-style caller through the same reserve-before-POST guard.

    Multipart/audio remains unpriced and fails before invoking the client. The
    original client is invoked once, using the guard's rewritten request bytes.
    """
    import requests
    allowed = {"data", "files", "json", "headers", "timeout"}
    if set(kwargs) - allowed:
        raise ModelBudgetError("farm_model_budget_request_unpriced")
    try:
        prepared = requests.Request("POST", url, **{key: value for key, value in kwargs.items()
                                      if key != "timeout"}).prepare()
        body = prepared.body
        if isinstance(body, str):
            body = body.encode("utf-8")
        request = urllib_request.Request(prepared.url, data=body,
            headers=dict(prepared.headers), method="POST")
    except (TypeError, ValueError):
        raise ModelBudgetError("farm_model_budget_request_invalid") from None
    client = http_client if http_client is not None else requests

    def transport(bound, timeout):
        response = client.post(bound.full_url, data=bound.data,
            headers=dict(bound.header_items()), timeout=timeout, allow_redirects=False)
        return BufferedResponse(response.content, status=response.status_code,
            headers=response.headers, url=bound.full_url)

    buffered = budgeted_urlopen(request, timeout=kwargs.get("timeout", 30),
        purpose=purpose, environ=environ, http_open=transport)
    return BufferedRequestsResponse(buffered)


def budget_status(*, environ=None, store=None):
    """Read-only metadata view; unknown reservations stay charged, no reset/refund.

    Counters describe durable ledger states, not inferred denial/exception totals.
    """
    try:
        ledger = store if store is not None else _default_store(environ)
        return ledger.report()
    except Exception:
        return {"status": "farm_model_budget_store_unavailable", "available": False}
