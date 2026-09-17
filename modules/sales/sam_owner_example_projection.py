"""Non-request-critical projection of optional SAM owner reply examples."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable, Mapping


PROJECTION_VERSION = "sam_owner_example_projection_v1"
DEFAULT_FRESHNESS_SECONDS = 900
FAILURE_RETRY_SECONDS = 60
MAX_EXAMPLES = 30

_lock = threading.Lock()
_refresh_lock = threading.Lock()
_snapshot = {
    "version": PROJECTION_VERSION,
    "projection_id": "",
    "refreshed_at_epoch": 0.0,
    "examples": (),
    "status": "cold",
    "next_refresh_epoch": 0.0,
}
_refresh_inflight = False


def read_owner_example_projection(
    *,
    loader: Callable | None = None,
    freshness_seconds: int = DEFAULT_FRESHNESS_SECONDS,
    now_epoch: float | None = None,
    clock: Callable[[], float] = time.time,
) -> dict:
    """Return only a fresh immutable snapshot and never wait for its loader."""
    now = float(clock() if now_epoch is None else now_epoch)
    freshness = max(1, min(int(freshness_seconds), 3600))
    with _lock:
        snapshot = dict(_snapshot)
        snapshot["examples"] = _clone_examples(_snapshot["examples"])
        age = (
            max(0.0, now - float(snapshot["refreshed_at_epoch"]))
            if snapshot["refreshed_at_epoch"]
            else None
        )
        fresh = bool(
            snapshot["projection_id"]
            and age is not None
            and age <= freshness
            and snapshot["status"] == "ready"
        )
    if not fresh:
        _start_background_refresh(loader, now_epoch=now, clock=clock)
    return {
        "version": PROJECTION_VERSION,
        "projection_id": snapshot["projection_id"] if fresh else "",
        "fresh": fresh,
        "age_seconds": round(age, 3) if age is not None else None,
        "status": "ready" if fresh else (
            "stale_omitted" if snapshot["projection_id"] else snapshot["status"]
        ),
        "examples": snapshot["examples"][:3] if fresh else [],
        "request_blocking_load": False,
        "canonical_authority": False,
    }


def refresh_owner_example_projection(
    loader: Callable | None = None,
    *,
    now_epoch: float | None = None,
    clock: Callable[[], float] = time.time,
) -> dict:
    """Refresh outside the response critical path; failures publish no guidance."""
    with _refresh_lock:
        actual_loader = loader or _default_loader
        try:
            result, status = actual_loader(
                conversation_id="",
                limit=MAX_EXAMPLES,
                customer_message="",
                customer_language="",
                conversation_stage="",
                reply_class="",
            )
            raw = result.get("examples") if isinstance(result, Mapping) else []
            examples = _validated_examples(raw)
            if int(status) >= 400 or not isinstance(raw, list):
                raise ValueError("owner_example_projection_source_unavailable")
            refreshed = float(clock() if now_epoch is None else now_epoch)
            projection_id = _projection_id(examples)
            with _lock:
                _snapshot.update({
                    "version": PROJECTION_VERSION,
                    "projection_id": projection_id,
                    "refreshed_at_epoch": refreshed,
                    "examples": tuple(_clone_examples(examples)),
                    "status": "ready",
                    "next_refresh_epoch": 0.0,
                })
            return {
                "success": True,
                "version": PROJECTION_VERSION,
                "projection_id": projection_id,
                "example_count": len(examples),
            }
        except Exception as exc:
            failed_at = float(clock() if now_epoch is None else now_epoch)
            with _lock:
                _snapshot["status"] = "refresh_failed"
                _snapshot["next_refresh_epoch"] = (
                    failed_at + FAILURE_RETRY_SECONDS
                )
            return {
                "success": False,
                "version": PROJECTION_VERSION,
                "status": "refresh_failed",
                "error_type": exc.__class__.__name__,
            }


def _start_background_refresh(loader, *, now_epoch=None, clock=time.time):
    global _refresh_inflight
    now = float(time.time() if now_epoch is None else now_epoch)
    with _lock:
        if (
            _refresh_inflight
            or now < float(_snapshot.get("next_refresh_epoch") or 0.0)
        ):
            return False
        _refresh_inflight = True
    thread = threading.Thread(
        target=_background_refresh,
        args=(loader, clock),
        name="sam-owner-example-projection-refresh",
        daemon=True,
    )
    thread.start()
    return True


def _background_refresh(loader, clock):
    global _refresh_inflight
    try:
        refresh_owner_example_projection(loader, clock=clock)
    finally:
        with _lock:
            _refresh_inflight = False


def _default_loader(**kwargs):
    from modules.sales.conversation_learning import (
        list_live_stock_owner_reply_examples,
    )

    return list_live_stock_owner_reply_examples(**kwargs)


def _validated_examples(values):
    examples = []
    for item in values or []:
        if not isinstance(item, Mapping):
            continue
        owner_reply = str(item.get("owner_reply_excerpt") or "").strip()
        if not owner_reply:
            continue
        examples.append({
            str(key): value
            for key, value in item.items()
            if str(key) in {
                "customer_message_excerpt",
                "rejected_sam_draft",
                "owner_reply_excerpt",
                "classification",
                "example_relevance_score",
                "created_at",
            }
        })
        if len(examples) >= MAX_EXAMPLES:
            break
    return examples


def _projection_id(examples):
    payload = json.dumps(
        examples,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return "SAM-OWNER-EXAMPLES-" + hashlib.sha256(
        (PROJECTION_VERSION + "\n" + payload).encode()
    ).hexdigest()[:24].upper()


def _clone_examples(examples):
    return json.loads(json.dumps(
        list(examples or []),
        ensure_ascii=True,
        sort_keys=True,
        default=str,
    ))


def _reset_owner_example_projection_for_tests():
    global _refresh_inflight
    with _lock:
        _snapshot.update({
            "version": PROJECTION_VERSION,
            "projection_id": "",
            "refreshed_at_epoch": 0.0,
            "examples": (),
            "status": "cold",
            "next_refresh_epoch": 0.0,
        })
        _refresh_inflight = False
