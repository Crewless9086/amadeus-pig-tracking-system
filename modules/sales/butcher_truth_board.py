"""Read-only, fail-closed pork pipeline truth projection for Butcher."""

from modules.sales.meat_match_engine import get_sales_lead_meat_match
from modules.sales.meat_ops import get_meat_ops_status
from modules.sales.meat_production import list_meat_processing_batches
from modules.sales.meat_reconciliation import get_meat_reconciliation_status


AUTHORITY = {
    "sends_customer_message": False,
    "creates_reservation": False,
    "books_provider": False,
    "confirms_payment": False,
    "changes_farm_lifecycle": False,
    "writes_operational_data": False,
}


def get_butcher_truth_board(lead_id, database_url=None):
    sources = {}
    for name, loader in (
        ("match", get_sales_lead_meat_match),
        ("ops", get_meat_ops_status),
        ("reconciliation", get_meat_reconciliation_status),
    ):
        result, code = loader(lead_id, database_url=database_url)
        if code != 200:
            return _source_failure(name, result), 503
        sources[name] = result
    batches, code = list_meat_processing_batches(database_url=database_url)
    if code != 200:
        return _source_failure("processing_batches", batches), 503
    sources["batches"] = batches
    return build_butcher_truth_board(
        sources["match"], sources["ops"], sources["batches"], sources["reconciliation"]
    ), 200


def build_butcher_truth_board(match_result, ops_result, batch_result, reconciliation_result):
    recommendation = (match_result.get("meat_match") or {}).get("recommendation") or {}
    reservations = ops_result.get("reservations") or []
    assembly = ops_result.get("assembly") or {}
    reconciliation = reconciliation_result.get("reconciliation") or {}
    pig_id = recommendation.get("pig_id") or _single_value(reservations, "pig_id")
    matching_batches = [
        row for row in batch_result.get("batches") or []
        if pig_id and _batch_has_pig(row, pig_id)
    ]
    conflicts = _reservation_conflicts(reservations)
    if len(matching_batches) > 1:
        conflicts.append("pig_linked_to_multiple_active_processing_batches")

    payment = {
        "pop_received_unverified": bool(assembly.get("pop_received_unverified")),
        "deposit_confirmed_in_bank": bool(assembly.get("deposit_confirmed")),
        "money_cleared_for_next_operation": bool(assembly.get("deposit_confirmed")),
    }
    batch = matching_batches[0] if len(matching_batches) == 1 else {}
    status, next_gate = _decision(recommendation, reservations, payment, batch, reconciliation, conflicts)
    return {
        "success": True,
        "status": "ok",
        "mode": "butcher_operational_truth_board_read_only",
        "truth_status": status,
        "next_gate": next_gate,
        "candidate": recommendation,
        "demand_match": (match_result.get("meat_match") or {}).get("criteria") or {},
        "commitments": [_commitment(item) for item in reservations],
        "reservation_risk": {"has_conflict": bool(conflicts), "reasons": conflicts},
        "payment": payment,
        "processing": {
            "batch_id": batch.get("batch_id", ""),
            "batch_code": batch.get("batch_code", ""),
            "status": batch.get("status", "not_linked"),
            "abattoir_name": batch.get("abattoir_name", ""),
            "butcher_name": batch.get("butcher_name", ""),
        },
        "packed_weight_reconciliation": reconciliation,
        "recommendation_target": "owner_approval_inbox_or_oom_sakkie",
        **AUTHORITY,
    }


def _decision(candidate, reservations, payment, batch, reconciliation, conflicts):
    if conflicts:
        return "blocked_conflict", "resolve_identity_or_reservation_conflict"
    if not candidate and not reservations:
        return "blocked_unknown", "confirm_candidate_and_reservation_truth"
    if reservations and not payment["deposit_confirmed_in_bank"]:
        return "awaiting_bank_confirmation", "confirm_deposit_in_bank"
    if reservations and not batch:
        return "blocked_unknown", "link_reservation_to_processing_batch"
    stage = batch.get("status")
    if stage and stage not in {"Packed", "Completed"}:
        return "awaiting_processing", "advance_abattoir_or_butcher_evidence"
    if batch and not reconciliation.get("actual_packed_weight_kg"):
        return "awaiting_packed_weight", "record_actual_packed_weight"
    if reconciliation and not reconciliation.get("ready_for_delivery_release"):
        return "awaiting_balance_confirmation", "confirm_final_balance_in_bank"
    if reconciliation.get("ready_for_delivery_release"):
        return "completed", "owner_review_completion"
    return "safe_to_offer_for_owner_review", "owner_reviews_offer_or_hold"


def _reservation_conflicts(reservations):
    by_pig = {}
    for item in reservations:
        by_pig.setdefault(item.get("pig_id"), []).append(item.get("carcass_side"))
    conflicts = []
    for sides in by_pig.values():
        clean = [side for side in sides if side]
        if clean.count("full") > 1 or ("full" in clean and len(clean) > 1):
            conflicts.append("overlapping_full_carcass_commitments")
        if clean.count("half_a") > 1 or clean.count("half_b") > 1:
            conflicts.append("duplicate_half_carcass_commitment")
    return sorted(set(conflicts))


def _commitment(item):
    return {key: item.get(key, "") for key in (
        "reservation_id", "lead_id", "order_id", "pig_id", "tag_number",
        "product_type", "carcass_side", "cut_set", "status", "effective_status",
        "estimated_packed_weight",
    )}


def _single_value(rows, key):
    values = {item.get(key) for item in rows if item.get(key)}
    return next(iter(values)) if len(values) == 1 else ""


def _batch_has_pig(batch, pig_id):
    return batch.get("pig_id") == pig_id or pig_id in (batch.get("pig_ids") or [])


def _source_failure(source, result):
    return {
        "success": False,
        "status": "blocked_unknown",
        "source": source,
        "source_status": result.get("status", "unavailable") if isinstance(result, dict) else "unavailable",
        "next_gate": "restore_authoritative_source_before_offer_or_hold",
        **AUTHORITY,
    }
