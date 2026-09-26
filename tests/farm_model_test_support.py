"""Explicit inert accounting for business tests; budget correctness has separate tests."""
from contextlib import ExitStack
from unittest.mock import patch
from urllib import request

_ORIGINAL_URLOPEN = request.urlopen

class FakeBudgetLedger:
    def __init__(self):
        self.reservations = []
        self.settlements = []
    def reserve(self, metadata):
        result = {**metadata, "created": True, "day": "2026-09-23", "state": "reserved"}
        self.reservations.append(result)
        return result
    def settle(self, reservation, usage):
        self.settlements.append((reservation, usage))
        return {"created": True}

def isolated_model_budget():
    """Keep the real request guard; isolate only persistence and HTTP in tests."""
    stack = ExitStack()
    stack.enter_context(patch("modules.oom_sakkie.model_budget._default_store", return_value=FakeBudgetLedger()))
    def open_inert(req, timeout):
        if request.urlopen is _ORIGINAL_URLOPEN:
            raise AssertionError("Business test must explicitly fake its HTTP transport")
        return request.urlopen(req, timeout=timeout)
    stack.enter_context(patch("modules.oom_sakkie.model_budget._open_no_redirect", side_effect=open_inert))
    return stack
