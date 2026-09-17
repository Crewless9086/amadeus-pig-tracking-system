"""Fail-closed authority contract for SAM Meat while the butcher loop is unproven."""

CONTROL_MODE = "interest_capture_only"
BLOCKER = "butcher_loop_not_proven"

ALLOWED_CAPABILITIES = frozenset({
    "capture_interest",
    "prepare_owner_review_reply",
    "read_internal_status",
})


def sam_meat_control_policy():
    """Return the current authority policy.

    Graduation is deliberately not configurable in this stage. A later mission must
    add authoritative runtime evidence and explicit owner approval before this
    evaluator can return a broader mode.
    """
    return {
        "mode": CONTROL_MODE,
        "butcher_loop_proven": False,
        "owner_review_required": True,
        "allowed_capabilities": sorted(ALLOWED_CAPABILITIES),
        "blockers": [BLOCKER],
        "customer_public_output_enabled": False,
    }


def capability_allowed(capability):
    return str(capability or "").strip() in ALLOWED_CAPABILITIES


def controlled_mode_denial(capability):
    return {
        "success": False,
        "status": "sam_meat_controlled_mode_blocked",
        "mode": CONTROL_MODE,
        "denied_capability": str(capability or "").strip(),
        "butcher_loop_proven": False,
        "owner_review_required": True,
        "blockers": [BLOCKER],
        "sent": False,
        "sends_customer_message": False,
        "posts_publicly": False,
        "creates_quote": False,
        "creates_invoice": False,
        "creates_order": False,
        "changes_stock": False,
        "reserves_carcass": False,
        "books_slaughter": False,
        "books_butcher": False,
        "confirms_payment": False,
        "writes_farm_data": False,
    }, 409
