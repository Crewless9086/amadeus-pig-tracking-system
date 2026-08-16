from datetime import date

from modules.pig_weights.herdmaster_live_transfer_contract import (
    CONTRACT_VERSION,
    compose_live_transfer_contract,
    load_live_transfer_snapshot,
)


ORDER = {
    "order_id": "ORD-2026-A6EC6D", "order_status": "Draft",
    "approval_status": "Pending", "requested_weight_range": "5_to_6_Kg",
    "requested_quantity": 2,
}


def pig(pig_id, tag, weight):
    return {"pig_id": pig_id, "tag_number": tag, "pig_name": None,
            "animal_type": "Weaner", "status": "Active", "on_farm": True,
            "purpose": "Sale", "current_weight_kg": weight,
            "last_weight_date": "2026-08-11"}


def medical(event_id, pig_id, product, treatment_date, end_date, days, *, created="2026-08-11T16:23:19+00:00"):
    return {"medical_event_id": event_id, "pig_id": pig_id, "product_id": "PRD-001",
            "product_name": product, "treatment_date": treatment_date, "dose": 1,
            "dose_unit": "ml", "withdrawal_days": days, "withdrawal_end_date": end_date,
            "given_by": "owner-admin:canonical", "source_sheet_row": None,
            "import_batch_id": None, "created_at": created}


def snapshot():
    return {
        "order": ORDER,
        "pigs": [pig("PIG-2026-A643", "123", 5.6), pig("PIG-2026-B156", "151", 4.0)],
        "order_lines": [{"order_line_id": "OL-2026-01E24C", "order_id": ORDER["order_id"],
                         "pig_id": "PIG-2026-A643", "line_status": "Draft",
                         "reserved_status": "Not_Reserved"}],
        "medical_events": [
            medical("MED-9123C224", "PIG-2026-A643", "Ecomectin 1%", "2026-07-06", "2026-08-03", 28),
            medical("MED-F924E93D", "PIG-2026-A643", "Ecomectin 1%", "2026-07-06", "2026-08-03", 28,
                    created="2026-07-06T19:27:59+00:00"),
            medical("MED-6DEF1FD54736F134C2F1D25B", "PIG-2026-B156", "Ecomectin 1%",
                    "2026-08-11", "2026-09-08", 28),
        ],
    }


def by_tag(packet):
    return {row["identity"]["tag_number"]: row for row in packet["pigs"]}


def test_active_withdrawal_blocks_food_chain_but_does_not_claim_live_transfer_authority():
    packet = compose_live_transfer_contract(snapshot(), as_of=date(2026, 8, 16))
    row = by_tag(packet)["151"]

    assert packet["contract_version"] == CONTRACT_VERSION
    assert packet["writes_performed"] is False
    assert row["food_chain_eligibility"]["state"] == "blocked"
    assert "2026-09-08" in row["food_chain_eligibility"]["reason"]
    assert row["livestock_transfer_eligibility"]["state"] == "Unknown"
    assert row["fit_for_transport"]["state"] == "Unknown"
    assert row["quarantine"]["state"] == "Unknown"
    assert row["notifiable_or_infectious_disease"]["state"] == "Unknown"
    assert row["veterinary_movement_stop"]["state"] == "Unknown"
    assert row["serious_health_or_welfare_hold"]["state"] == "Unknown"
    assert row["treatment_disclosure"]["live_transfer_supported_by_every_other_current_gate"] is None


def test_tag_151_disclosure_is_exact_and_order_fit_is_independently_blocked():
    row = by_tag(compose_live_transfer_contract(snapshot(), as_of=date(2026, 8, 16)))["151"]
    disclosure = row["treatment_disclosure"]

    assert disclosure["pig_id"] == "PIG-2026-B156"
    assert disclosure["tag_number"] == "151"
    assert disclosure["medical_event_id"] == "MED-6DEF1FD54736F134C2F1D25B"
    assert disclosure["product"] == "Ecomectin 1%"
    assert disclosure["treatment_date"] == "2026-08-11"
    assert disclosure["withdrawal_end_date"] == "2026-09-08"
    assert disclosure["medical_evidence_digest"]
    assert disclosure["disclosure_digest"]
    assert len(disclosure["affected_document_targets"]) == 4
    assert "does not certify fitness for transport" in disclosure["safe_buyer_wording"]
    assert row["current_order_eligibility"]["state"] == "blocked"
    assert "2_to_4_Kg" in row["current_order_eligibility"]["reason"]
    assert "5_to_6_Kg" in row["current_order_eligibility"]["reason"]


def test_duplicate_treatment_evidence_fails_closed_without_hiding_order_line():
    row = by_tag(compose_live_transfer_contract(snapshot(), as_of=date(2026, 8, 16)))["123"]

    assert row["treatment_evidence_completeness"]["state"] == "conflicting"
    assert row["livestock_transfer_eligibility"]["state"] == "blocked"
    assert row["current_order_eligibility"]["state"] == "included_draft_unreserved"
    assert any(item.get("conflict") == "possible_duplicate_treatment_evidence"
               for item in row["treatment_evidence_conflicts"])


def test_changed_medical_evidence_changes_disclosure_and_packet_digest_without_mutation():
    first = compose_live_transfer_contract(snapshot(), as_of=date(2026, 8, 16))
    changed = snapshot()
    changed["medical_events"][-1] = {
        **changed["medical_events"][-1], "withdrawal_end_date": "2026-09-09",
        "withdrawal_days": 29,
    }
    second = compose_live_transfer_contract(changed, as_of=date(2026, 8, 16))

    first_disclosure = by_tag(first)["151"]["treatment_disclosure"]
    second_disclosure = by_tag(second)["151"]["treatment_disclosure"]
    assert first_disclosure["medical_evidence_digest"] != second_disclosure["medical_evidence_digest"]
    assert first_disclosure["disclosure_digest"] != second_disclosure["disclosure_digest"]
    assert first["packet_digest"] != second["packet_digest"]
    assert second["creates_buyer_acknowledgement"] is False
    assert second["generates_document"] is False


def test_missing_treatment_evidence_remains_unknown_and_never_becomes_zero_or_clearance():
    missing = snapshot()
    missing["medical_events"] = [
        row for row in missing["medical_events"] if row["pig_id"] != "PIG-2026-B156"
    ]
    row = by_tag(compose_live_transfer_contract(missing, as_of=date(2026, 8, 16)))["151"]

    assert row["treatment_evidence_completeness"]["state"] == "Unknown"
    assert row["food_chain_eligibility"]["state"] == "Unknown"
    assert row["livestock_transfer_eligibility"]["state"] == "Unknown"
    assert row["treatment_disclosure"] is None


def test_document_and_acknowledgement_contracts_are_design_only_and_append_only_bound():
    packet = compose_live_transfer_contract(snapshot(), as_of=date(2026, 8, 16))

    assert {item["document_type"] for item in packet["document_projections"]} == {
        "Loading Sheet", "Removal Certificate", "Health Declaration", "Quote / Order Confirmation"
    }
    assert all(item["status"] == "not_generated_design_only"
               for item in packet["document_projections"])
    assert all("medical_evidence_digest" in item["required_binding"]
               for item in packet["document_projections"])
    acknowledgement = packet["buyer_acknowledgement_contract"]
    assert acknowledgement["status"] == "design_only_not_created"
    assert "order_line_id" in acknowledgement["append_only_binding"]
    assert "history is never rewritten" in acknowledgement["medical_change_rule"]


def test_loader_uses_one_repeatable_read_read_only_snapshot_and_no_write_sql():
    class Cursor:
        def __init__(self, rows): self.rows = rows
        def fetchall(self): return self.rows

    class Connection:
        def __init__(self): self.calls = []
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, params=None):
            self.calls.append((" ".join(sql.lower().split()), params))
            normalized = self.calls[-1][0]
            if normalized.startswith("set transaction"):
                return Cursor([])
            if "from public.current_canonical_pigs" in normalized:
                return Cursor(snapshot()["pigs"])
            if "from public.pig_medical_events" in normalized:
                return Cursor(snapshot()["medical_events"])
            if "from public.orders" in normalized:
                return Cursor([ORDER])
            if "from public.order_lines" in normalized:
                return Cursor(snapshot()["order_lines"])
            raise AssertionError(normalized)

    connection = Connection()
    loaded = load_live_transfer_snapshot(
        ["PIG-2026-A643", "PIG-2026-B156"], ORDER["order_id"],
        connect_factory=lambda _url: connection,
    )
    sql = " ".join(call[0] for call in connection.calls)

    assert len(loaded["pigs"]) == 2
    assert "repeatable read read only" in sql
    for mutation in (" insert ", " update ", " delete ", " merge ", " alter ", " create ", " drop "):
        assert mutation not in f" {sql} "
