"""Bound aggregate latency and fan-out for independent read-only models."""
from concurrent.futures import ThreadPoolExecutor,wait
from contextvars import copy_context
import time

READ_GROUP_DEADLINE_SECONDS=18

class RootlineReadGroupDeadlineExceeded(TimeoutError):
    pass

def run_bounded_read_group(readers,*,max_workers,deadline_seconds=READ_GROUP_DEADLINE_SECONDS):
    readers=dict(readers or {})
    if not readers:return {}
    if max_workers not in range(1,5):
        raise ValueError("rootline_read_group_worker_limit_invalid")
    from modules.telemetry.rootline_cycle_budget import remaining_seconds
    deadline=time.monotonic()+remaining_seconds(float(deadline_seconds))
    executor=ThreadPoolExecutor(max_workers=min(max_workers,len(readers)),
        thread_name_prefix="rootline-bounded-read")
    futures={name:executor.submit(copy_context().run, reader) for name,reader in readers.items()}
    try:
        done,pending=wait(tuple(futures.values()),timeout=max(0,deadline-time.monotonic()))
        if pending:
            for future in pending:future.cancel()
            raise RootlineReadGroupDeadlineExceeded("rootline_read_group_deadline_exceeded")
        return {name:future.result() for name,future in futures.items()}
    finally:
        # Never let executor cleanup extend the enclosing web-worker deadline.
        # Underlying production readers retain their own shorter connection,
        # statement and lock deadlines and close their own resources.
        executor.shutdown(wait=False,cancel_futures=True)
