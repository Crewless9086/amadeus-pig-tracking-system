"""Request-local limits for optional ROOTLINE work; safety duties keep ownership."""
from contextlib import contextmanager
from contextvars import ContextVar
import math
import time

# Leave room inside the existing 200-second web worker for durable outcome
# recording and any already-owned shutdown duty. This does not extend a service.
CYCLE_WORK_SECONDS = 140.0
REPORT_MINIMUM_SECONDS = 25.0
_work_deadline = ContextVar("rootline_cycle_work_deadline", default=None)
_on_deadline = ContextVar("rootline_cycle_on_deadline", default=None)


class RootlineCycleDeadlineExceeded(TimeoutError):
    pass


def work_deadline():
    return _work_deadline.get()


def on_deadline():
    return _on_deadline.get()


def remaining_seconds(maximum=None, *, minimum=0.0):
    deadline = work_deadline()
    remaining = float("inf") if deadline is None else deadline-time.monotonic()
    if remaining <= minimum:
        raise RootlineCycleDeadlineExceeded("rootline_cycle_deadline_exceeded")
    return min(remaining, maximum) if maximum is not None else remaining


@contextmanager
def cycle_budget(deadline=None):
    supplied = time.monotonic()+CYCLE_WORK_SECONDS if deadline is None else float(deadline)
    if not math.isfinite(supplied):
        raise ValueError("rootline_cycle_deadline_invalid")
    current = work_deadline()
    bound = min(current, supplied) if current is not None else supplied
    prior_on = on_deadline()
    work_token = _work_deadline.set(bound)
    on_token = _on_deadline.set(min(prior_on, bound) if prior_on is not None else bound)
    try:
        yield bound
    finally:
        _on_deadline.reset(on_token)
        _work_deadline.reset(work_token)


@contextmanager
def mandatory_safety():
    """An expired optional-work budget never abandons OFF or its durable proof.

    The ON deadline deliberately remains in force, including managed-device
    work that shares this scope with its independent safety duties.
    """
    token = _work_deadline.set(None)
    try:
        yield
    finally:
        _work_deadline.reset(token)
