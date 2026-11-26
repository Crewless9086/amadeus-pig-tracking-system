"""Shared read-only deadline inventory and request-local safety checkpoints."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from time import monotonic
from modules.telemetry.rootline_cycle_budget import remaining_seconds, on_deadline, RootlineCycleDeadlineExceeded

_checkpoint = ContextVar("rootline_owned_deadline_checkpoint", default=None)
_waited = ContextVar("rootline_owned_deadline_waited", default=None)

@contextmanager
def owned_deadline_checkpoint(callback):
    token = _checkpoint.set(callback)
    waited_token = _waited.set(set())
    try:
        yield
    finally:
        _checkpoint.reset(token)
        _waited.reset(waited_token)

def check_owned_deadline(*, safety_complete=False):
    callback = _checkpoint.get()
    if callback is not None:
        return callback(safety_complete=safety_complete)

def admit_owned_wait(delay, *, original_bound=None, monotonic_clock=None):
    remaining_seconds(minimum=delay)
    bound = on_deadline() if original_bound is None else original_bound
    if bound is not None and bound-(monotonic_clock or monotonic)() <= delay:
        raise RootlineCycleDeadlineExceeded("injector_wait_exceeds_cycle_budget")

def read_owned_inventory(store):
    auxiliaries = store("load_active_auxiliaries", None)
    check_owned_deadline()
    borehole = store("load_active_borehole", None)
    check_owned_deadline()
    parent = store("load_active", None)
    if (not isinstance(auxiliaries, list) or any(not isinstance(row, dict) or not row.get("execution_id") for row in auxiliaries)
            or any(row is not None and (not isinstance(row, dict) or not row.get("execution_id")) for row in (borehole,parent))):
        raise ValueError("deadline_inventory_unproven")
    return {"aux":auxiliaries,"borehole":borehole,"parent":parent,"proven":True}

def wait_for_parent_deadline(execution, *, store, clock, wait, original_bound):
    """No command authority: wait once only with complete earlier-duty inventory."""
    from modules.telemetry.rootline_command_acceptance import command_stop_deadline
    from modules.telemetry.rootline_borehole_conditions import continuous_borehole
    if original_bound is None:
        return "original_cycle_bound_unproven"
    before = clock()
    deadline = command_stop_deadline(execution)
    if deadline is None or deadline.tzinfo is None or before.tzinfo is None:
        return "parent_deadline_unproven"
    if before >= deadline:
        return "parent_due"
    try:
        admit_owned_wait((deadline-before).total_seconds(), original_bound=original_bound)
        inventory = read_owned_inventory(store)
        parent = inventory["parent"]
        if (not parent or parent.get("execution_id") != execution.get("execution_id")
                or command_stop_deadline(parent) != deadline):
            return "parent_changed"
        for row in inventory["aux"]+[inventory["borehole"]]:
            if not row or continuous_borehole(row):
                continue
            other = command_stop_deadline(row)
            if other is None or other.tzinfo is None:
                return "deadline_inventory_unproven"
            if other <= deadline:
                return "earlier_owned_deadline"
        current = clock()
        if current < before:
            return "parent_clock_reversed"
        delay = max(0.0,(deadline-current).total_seconds())
        admit_owned_wait(delay,original_bound=original_bound)
        if delay:
            wait(delay)
        return "parent_due" if clock() >= deadline else "parent_clock_reversed"
    except RootlineCycleDeadlineExceeded:
        return "original_cycle_bound_exhausted"
    except Exception:
        return "deadline_inventory_unproven"

def wait_for_earlier_owned_deadline(execution, *, store, clock, wait, original_bound):
    """At most one wait per canonical owned deadline; existing supervisors own OFF."""
    from modules.telemetry.rootline_command_acceptance import command_stop_deadline
    from modules.telemetry.rootline_borehole_conditions import continuous_borehole
    attempted = _waited.get()
    if attempted is None or original_bound is None:
        return None
    try:
        before = clock()
        parent_deadline = command_stop_deadline(execution)
        if parent_deadline is None or before >= parent_deadline:
            return None
        admit_owned_wait((parent_deadline-before).total_seconds(), original_bound=original_bound)
        inventory = read_owned_inventory(store)
        parent = inventory["parent"]
        if (not parent or parent.get("execution_id") != execution.get("execution_id")
                or command_stop_deadline(parent) != parent_deadline):
            return None
        candidates=[]
        for row in inventory["aux"]+[inventory["borehole"]]:
            if row is None or continuous_borehole(row):
                continue
            deadline=command_stop_deadline(row)
            if row.get("state") != "Active" or deadline is None:
                return None
            if deadline <= parent_deadline:
                candidates.append((deadline,str(row["execution_id"]),row))
        if not candidates:
            return None
        deadline, identity, duty=min(candidates,key=lambda item:(item[0],item[1]))
        key=(identity,deadline.isoformat())
        if key in attempted:
            return None  # Still-owned earlier duty prevents waiting past a failed stop.
        current = clock()
        if current < before:
            return None
        delay = max(0.0,(deadline-current).total_seconds())
        admit_owned_wait(delay, original_bound=original_bound)
        attempted.add(key)
        if delay:
            wait(delay)
        return duty if clock() >= deadline else None
    except Exception:
        return None
