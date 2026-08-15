import threading,time
import pytest
from modules.telemetry.rootline_bounded_read_group import (
    RootlineReadGroupDeadlineExceeded,run_bounded_read_group,
)

def test_group_runs_with_constrained_parallelism():
    barrier=threading.Barrier(2)
    def reader(value):
        barrier.wait(timeout=1);return value
    assert run_bounded_read_group({"a":lambda:reader(1),"b":lambda:reader(2)},
        max_workers=2,deadline_seconds=1)=={"a":1,"b":2}

def test_group_deadline_returns_without_waiting_for_stalled_reader():
    release=threading.Event();started=time.monotonic()
    with pytest.raises(RootlineReadGroupDeadlineExceeded):
        run_bounded_read_group({"stall":lambda:release.wait(2)},max_workers=1,
            deadline_seconds=.05)
    assert time.monotonic()-started<.5
    release.set()

def test_group_rejects_fanout_above_governed_limit():
    with pytest.raises(ValueError,match="worker_limit"):
        run_bounded_read_group({"a":lambda:1},max_workers=5)
