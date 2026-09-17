"""Streaming bridge for the owner web interface over the private runtime."""

from __future__ import annotations

import json
import queue
import threading
import uuid


TERMINAL_EVENTS = {"turn_completed", "turn_failed"}


def sse_event(event_type, data):
    return f"event: {event_type}\ndata: {json.dumps(data or {}, default=str, separators=(',', ':'))}\n\n"


def stream_private_turn(text, turn_runner, *, turn_id=None):
    """Yield SSE while a runtime turn executes in a bounded worker thread."""
    turn_id = turn_id or "TURN-" + uuid.uuid4().hex.upper()
    events = queue.Queue()

    def emit(event_type, payload=None):
        safe = dict(payload or {})
        safe["turn_id"] = turn_id
        events.put((event_type, safe))

    def worker():
        try:
            result, status = turn_runner(emit)
            packet = result.get("executive_packet") if isinstance(result, dict) else None
            emit("reply_ready", {"reply": str((result or {}).get("reply") or "")[:3900], "executive_packet": packet or {}, "status_code": status})
            emit("turn_completed" if status < 400 else "turn_failed", {"status": (result or {}).get("status"), "status_code": status})
        except Exception as exc:
            emit("turn_failed", {"status": "private_stream_failed", "error_type": exc.__class__.__name__, "status_code": 500})

    yield sse_event("turn_started", {"turn_id": turn_id, "text_length": len(str(text or ""))})
    thread = threading.Thread(target=worker, name=f"charlie-live-{turn_id[-8:]}", daemon=True)
    thread.start()
    while True:
        try:
            event_type, payload = events.get(timeout=15)
        except queue.Empty:
            yield ": keep-alive\n\n"
            continue
        yield sse_event(event_type, payload)
        if event_type in TERMINAL_EVENTS:
            break
