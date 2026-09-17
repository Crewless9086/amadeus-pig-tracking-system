"""Fence every synchronous HTTPX physical request made by pinned Hermes.

Unknown transports/routes fail before inference. Reservations remain charged
on failures, SDK retries and fallback; a prepared intent blocks reissue.
"""
from contextlib import contextmanager
import hashlib
import json
import threading
import uuid

from .execution import NativeExecutionError
from .recovery import digest

_LOCK = threading.Lock()


@contextmanager
def physical_request_guard(recovery, provider, model):
    if recovery is None:
        raise NativeExecutionError("native_model_budget_authority_required")
    import httpx
    if provider != "openrouter" or model != "openai/gpt-5-mini":
        raise NativeExecutionError("native_model_unbounded_route")
    # Monetary ceilings require an owner-reviewed tariff upper bound. This
    # source candidate cannot certify live prices or silently choose a rate.
    limits = recovery.grant["limits"]
    ceiling = recovery.grant.get("pricing_ceiling")
    if not isinstance(ceiling, dict) or ceiling.get("provider") != provider or ceiling.get("model") != model:
        raise NativeExecutionError("native_model_pricing_ceiling_required")
    with _LOCK:
        original = httpx.Client._send_single_request
        original_async = httpx.AsyncClient._send_single_request
        async def asynchronous_forbidden(*_args, **_kwargs):
            raise NativeExecutionError("native_model_async_transport_unbounded")
        def guarded(client, request, *args, **kwargs):
            transport = client._transport_for_url(request.url)
            if type(transport) not in {httpx.HTTPTransport, httpx.MockTransport}:
                raise NativeExecutionError("native_model_transport_unbounded")
            pool = getattr(transport, "_pool", None)
            if pool is not None and getattr(pool, "_retries", None) != 0:
                raise NativeExecutionError("native_model_transport_retries_unbounded")
            if str(request.url) != "https://openrouter.ai/api/v1/chat/completions" or request.method != "POST":
                raise NativeExecutionError("native_model_fallback_forbidden")
            body = request.read()
            try:
                payload = json.loads(body)
            except ValueError:
                raise NativeExecutionError("native_model_request_invalid") from None
            if not isinstance(payload, dict):
                raise NativeExecutionError("native_model_request_invalid")
            allowed = {"model", "messages", "max_tokens", "max_completion_tokens", "temperature",
                       "response_format", "reasoning", "reasoning_effort", "tools", "stream", "n"}
            if (set(payload) - allowed or len(set(payload) & {"max_tokens", "max_completion_tokens"}) != 1
                    or type(payload.get("n", 1)) is not int or payload.get("n", 1) != 1
                    or payload.get("stream", False) is not False):
                raise NativeExecutionError("native_model_request_unbounded")
            output = payload.get("max_completion_tokens", payload.get("max_tokens"))
            if (payload.get("model") != model or payload.get("tools") or len(body) > 131072
                    or type(output) is not int or not 0 < output <= 6000
                    or payload.get("stream") is True or payload.get("n", 1) != 1
                    or not isinstance(payload.get("messages"), list)
                    or any(not isinstance(m, dict) or set(m) != {"role", "content"}
                           or m.get("role") not in {"system", "user", "assistant"}
                           or not isinstance(m.get("content"), str) for m in payload["messages"])):
                raise NativeExecutionError("native_model_request_unbounded")
            input_rate, output_rate = ceiling.get("input_microusd_per_token"), ceiling.get("output_microusd_per_token")
            if (type(input_rate) is not int or input_rate <= 0 or type(output_rate) is not int or output_rate <= 0
                    or len(body)*input_rate + output*output_rate > limits["per_request_microusd"]):
                raise NativeExecutionError("native_model_request_cost_unbounded")
            # The byte bound conservatively exceeds input token count. The
            # explicit max output must include reasoning; live tariff proof is
            # an owner gate, never fabricated here.
            intent = {"provider": provider, "model": model, "physical_request": uuid.uuid4().hex,
                      "request_sha256": hashlib.sha256(body).hexdigest(), "input_bytes": len(body),
                      "max_output_tokens": output}
            def send():
                response = original(client, request, *args, **kwargs)
                response.read()
                return response
            def receipt(response, exact):
                if response.status_code != 200:
                    raise NativeExecutionError("native_model_http_rejected")
                data = response.json()
                if not isinstance(data.get("id"), str) or not data["id"]:
                    raise NativeExecutionError("native_model_receipt_invalid")
                return {"intent_sha256": digest(exact), "request_id": data["id"],
                        "response_sha256": hashlib.sha256(response.content).hexdigest(),
                        "provider": provider, "model": model}
            return recovery.perform("model", intent, send, receipt)
        httpx.Client._send_single_request = guarded
        httpx.AsyncClient._send_single_request = asynchronous_forbidden
        try:
            yield
        finally:
            httpx.Client._send_single_request = original
            httpx.AsyncClient._send_single_request = original_async
