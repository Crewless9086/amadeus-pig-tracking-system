"""Safe order-persistence canary contracts.

This module is intentionally not registered as an HTTP route.  A production
canary may validate an order preview but cannot reach ``create_order`` or any
other order/status-log writer.  Persistence evidence is limited to an
explicitly injected disposable integration runner used by tests.
"""

from modules.orders.order_validation import validate_new_order_payload


PRODUCTION_READ_ONLY = "production_read_only"
DISPOSABLE_INTEGRATION = "disposable_integration"


def preview_order_for_canary(payload: dict) -> dict:
    """Validate an order payload and return a no-write production preview."""
    validation = validate_new_order_payload(payload or {})
    return {
        "success": validation["is_valid"],
        "mode": PRODUCTION_READ_ONLY,
        "validation_errors": validation["errors"],
        "order_preview": validation["cleaned_data"],
        "no_write": True,
        "commercial_action": "none",
        "persistence": "not_attempted",
        "safety_proof": [
            "No create_order call was made.",
            "No order or status-log write was attempted.",
            "No stock reservation, payment, customer send, or lifecycle action was attempted.",
        ],
    }


def run_order_persistence_canary(
    payload: dict,
    *,
    mode: str,
    persistence_requested: bool = False,
    disposable_persistence_runner=None,
) -> dict:
    """Run one bounded canary mode.

    ``production_read_only`` always refuses persistence before any writer can
    be selected.  ``disposable_integration`` is intentionally test-only: its
    runner must return independently verifiable order and status-log evidence
    from an isolated database/connection.
    """
    if mode == PRODUCTION_READ_ONLY:
        preview = preview_order_for_canary(payload)
        if persistence_requested:
            return {
                **preview,
                "success": False,
                "error": "Persistence is forbidden in production_read_only mode.",
                "persistence": "rejected_before_write",
            }
        return preview

    if mode != DISPOSABLE_INTEGRATION:
        return {
            "success": False,
            "mode": mode,
            "error": "Unsupported canary mode.",
        }

    validation = validate_new_order_payload(payload or {})
    if not validation["is_valid"]:
        return {
            "success": False,
            "mode": DISPOSABLE_INTEGRATION,
            "validation_errors": validation["errors"],
            "persistence": "not_attempted",
        }
    if not persistence_requested:
        return {
            "success": False,
            "mode": DISPOSABLE_INTEGRATION,
            "error": "Disposable persistence must be explicitly requested.",
            "persistence": "not_attempted",
        }
    if disposable_persistence_runner is None:
        return {
            "success": False,
            "mode": DISPOSABLE_INTEGRATION,
            "error": "A disposable persistence runner is required.",
            "persistence": "not_attempted",
        }

    evidence = disposable_persistence_runner(validation["cleaned_data"])
    if not isinstance(evidence, dict) or not all(
        evidence.get(key) is True
        for key in ("isolated_database", "order_persisted", "status_log_persisted")
    ):
        return {
            "success": False,
            "mode": DISPOSABLE_INTEGRATION,
            "error": "Disposable runner did not prove isolated order and status-log persistence.",
            "persistence": "unverified",
            "evidence": evidence if isinstance(evidence, dict) else {},
        }

    return {
        "success": True,
        "mode": DISPOSABLE_INTEGRATION,
        "persistence": "verified_in_disposable_database",
        "commercial_action": "none",
        "evidence": evidence,
    }
