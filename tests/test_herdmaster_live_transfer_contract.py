from datetime import date

from modules.pig_weights.herdmaster_live_transfer_contract import (
    CONTRACT_VERSION,
    compose_live_transfer_contract,
    load_live_transfer_snapshot,
)


ORDER = {
    "order_id": "ORD-2026-A6EC6D", "order_status": "Draft",
    "approval_status": "Pending", "requested_weight_range": "5_to_6_Kg",
    "requested_quantity": 2, "active_pig_line_unique_guard": True,
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
        "observation_events": [],
        "location_events": [
            {"location_event_id": "MOV-C0F1D295929E5AC3461755BE",
             "pig_id": "PIG-2026-B156", "move_date": "2026-08-11",
             "created_at": "2026-08-11T16:23:19+00:00"},
        ],
        "price_rows": [
            {"pricing_id": "PRICE-YOUNG_PIGLETS_2_TO_4_KG_ANY",
             "sale_category": "Young Piglets", "weight_band": "2_to_4_Kg",
             "sex": None, "unit_price": 350, "currency": "ZAR", "active": True,
             "effective_from": "2026-05-21T00:00:00+00:00", "created_at": "2026-05-21T00:00:00+00:00"},
            {"pricing_id": "PRICE-YOUNG_PIGLETS_5_TO_6_KG_ANY",
             "sale_category": "Young Piglets", "weight_band": "5_to_6_Kg",
             "sex": None, "unit_price": 400, "currency": "ZAR", "active": True,
             "effective_from": "2026-05-21T00:00:00+00:00", "created_at": "2026-05-21T00:00:00+00:00"},
        ],
        "medical_correction_events": [],
        "medical_correction_rail_available": True,
        "medical_events": [
            medical("MED-9123C224", "PIG-2026-A643", "Ecomectin 1%", "2026-07-06", "2026-08-03", 28,
                    created="2026-07-06T19:18:15+00:00"),
            medical("MED-F924E93D", "PIG-2026-A643", "Ecomectin 1%", "2026-07-06", "2026-08-03", 28,
                    created="2026-07-06T19:27:59+00:00"),
            medical("MED-6DEF1FD54736F134C2F1D25B", "PIG-2026-B156", "Ecomectin 1%",
                    "2026-08-11", "2026-09-08", 28),
        ],
    }


def by_tag(packet):
    return {row["identity"]["tag_number"]: row for row in packet["pigs"]}


def test_active_withdrawal_blocks_food_chain_but_not_live_sale_review():
    packet = compose_live_transfer_contract(snapshot(), as_of=date(2026, 8, 16))
    row = by_tag(packet)["151"]

    assert packet["contract_version"] == CONTRACT_VERSION
    assert packet["writes_performed"] is False
    assert row["food_chain_eligibility"]["state"] == "blocked"
    assert "2026-09-08" in row["food_chain_eligibility"]["reason"]
    assert row["livestock_transfer_eligibility"]["state"] == "eligible_on_current_evidence"
    for axis_name in ("fit_for_transport", "quarantine",
                      "notifiable_or_infectious_disease", "veterinary_movement_stop",
                      "serious_health_or_welfare_hold"):
        assert row[axis_name]["state"] == "no_current_recorded_restriction"
    assert row["treatment_disclosure"]["live_transfer_supported_by_every_other_current_gate"] is True


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
    price = row["price_band_compatibility"]
    assert price["state"] == "incompatible"
    assert price["separately_priced_line_supported"] is True
    assert price["separate_price_rule"]["pricing_id"] == "PRICE-YOUNG_PIGLETS_2_TO_4_KG_ANY"
    assert price["separate_price_rule"]["unit_price"] == 350
    assert "protected owner preview" in price["commercial_consequence"]
    assert row["canonical_dependency_evidence"]["movement"]["history_event_ids"] == [
        "MOV-C0F1D295929E5AC3461755BE"
    ]


def test_duplicate_treatment_evidence_fails_closed_without_hiding_order_line():
    row = by_tag(compose_live_transfer_contract(snapshot(), as_of=date(2026, 8, 16)))["123"]

    assert row["treatment_evidence_completeness"]["state"] == "conflicting"
    assert row["livestock_transfer_eligibility"]["state"] == "eligible_on_current_evidence"
    assert row["current_order_eligibility"]["state"] == "included_draft_unreserved"
    assert any(item.get("conflict") == "possible_duplicate_treatment_evidence"
               for item in row["treatment_evidence_conflicts"])
    assert row["medical_ambiguity"]["state"] == "unresolved_conflicting_evidence"
    assert row["medical_ambiguity"]["event_pairs"][0]["medical_event_ids"] == [
        "MED-9123C224", "MED-F924E93D"
    ]
    assert "veterinary professional" in row["medical_ambiguity"]["required_resolution"]
    assert row["medical_correction_authority"]["medical_schema_supports_supersession"] is True
    protection = row["order_line_duplication_protection"]
    assert protection["state"] == "existing_line_blocks_duplicate"
    assert protection["active_line_count"] == 1
    assert protection["active_order_line_ids"] == ["OL-2026-01E24C"]
    assert protection["database_unique_order_pig_constraint"] is True


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


def test_missing_treatment_evidence_remains_unknown_without_inventing_live_sale_blocker():
    missing = snapshot()
    missing["medical_events"] = [
        row for row in missing["medical_events"] if row["pig_id"] != "PIG-2026-B156"
    ]
    row = by_tag(compose_live_transfer_contract(missing, as_of=date(2026, 8, 16)))["151"]

    assert row["treatment_evidence_completeness"]["state"] == "Unknown"
    assert row["food_chain_eligibility"]["state"] == "Unknown"
    assert row["livestock_transfer_eligibility"]["state"] == "eligible_on_current_evidence"
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
    request = packet["consolidated_evidence_request"]
    assert request["owner_interaction_count"] == 1
    assert len(request["medical_pair_questions"]) == 1
    assert request["medical_pair_questions"][0]["choices"] == [
        "one_administration_recorded_twice", "two_separate_administrations",
        "Unknown_requires_veterinary_review",
    ]
    assert request["live_transfer_assessment"]["fields"]["fit_for_transport"] == [
        "fit", "unfit", "Unknown"
    ]
    assert "change_order" in request["prohibited_effects"]


def test_future_or_wrong_sex_price_rule_cannot_create_a_false_commercial_option():
    evidence = snapshot()
    evidence["price_rows"] = [
        {**evidence["price_rows"][0], "sex": "Female"},
        {**evidence["price_rows"][0], "pricing_id": "PRICE-FUTURE",
         "sex": None, "effective_from": "2026-08-17T00:00:00+00:00"},
    ]
    row = by_tag(compose_live_transfer_contract(evidence, as_of=date(2026, 8, 16)))["151"]

    assert row["price_band_compatibility"]["separately_priced_line_supported"] is False
    assert row["price_band_compatibility"]["separate_price_rule"] is None
    assert "No authoritative separate price rule" in row["price_band_compatibility"]["commercial_consequence"]


def test_sam_price_specificity_and_exclusive_end_boundary_are_preserved():
    evidence = snapshot()
    evidence["pigs"][1]["sex"] = "Male"
    base = evidence["price_rows"][0]
    evidence["price_rows"] = [
        {**base, "pricing_id": "PRICE-EXACT-MALE", "sex": "Male", "unit_price": 325,
         "effective_from": "2026-05-01", "effective_to": None},
        {**base, "pricing_id": "PRICE-NEWER-ANY", "sex": None, "unit_price": 350,
         "effective_from": "2026-06-01", "effective_to": None},
        {**base, "pricing_id": "PRICE-ENDED", "sex": "Male", "unit_price": 999,
         "effective_from": "2026-07-01", "effective_to": "2026-08-16"},
    ]
    row = by_tag(compose_live_transfer_contract(evidence, as_of=date(2026, 8, 16)))["151"]

    assert row["price_band_compatibility"]["separate_price_rule"]["pricing_id"] == "PRICE-EXACT-MALE"
    assert row["price_band_compatibility"]["separate_price_rule"]["unit_price"] == 325


def test_same_day_price_effective_timestamp_is_included_at_end_of_day_cutoff():
    evidence = snapshot()
    evidence["price_rows"] = [{
        **evidence["price_rows"][0], "pricing_id": "PRICE-SAME-DAY",
        "effective_from": "2026-08-16T12:00:00+00:00", "effective_to": None,
    }]
    row = by_tag(compose_live_transfer_contract(evidence, as_of=date(2026, 8, 16)))["151"]

    assert row["price_band_compatibility"]["separate_price_rule"]["pricing_id"] == "PRICE-SAME-DAY"


def test_duplicate_active_order_lines_fail_closed_with_every_identity():
    evidence = snapshot()
    evidence["order_lines"].append({
        **evidence["order_lines"][0], "order_line_id": "OL-2026-DUPLICATE"
    })
    row = by_tag(compose_live_transfer_contract(evidence, as_of=date(2026, 8, 16)))["123"]

    assert row["current_order_eligibility"]["state"] == "conflicting_duplicate_lines"
    assert row["current_order_eligibility"]["evidence_ids"] == [
        "OL-2026-01E24C", "OL-2026-DUPLICATE"
    ]
    assert row["order_line_duplication_protection"]["state"] == "conflicting_duplicate_lines"


def test_append_only_medical_corrections_govern_current_without_hiding_original_history():
    evidence = snapshot()
    evidence["medical_correction_events"] = [{
        "correction_event_id": "MEDCOR-DUP", "pig_id": "PIG-2026-A643",
        "original_medical_event_id": "MED-F924E93D",
        "retained_medical_event_id": "MED-9123C224", "resolution": "duplicate_record",
        "recorded_at": "2026-08-16T10:00:00+00:00", "supersedes_correction_event_id": None,
    }]
    row = by_tag(compose_live_transfer_contract(evidence, as_of=date(2026, 8, 16)))["123"]

    assert "MED-F924E93D" not in {item["medical_event_id"] for item in row["canonical_treatment_events"]}
    assert "MED-F924E93D" in {item["medical_event_id"] for item in row["canonical_treatment_history"]}
    assert row["medical_correction_authority"]["current_correction_event_ids"] == ["MEDCOR-DUP"]


def test_attributable_transfer_assessment_governs_each_axis_but_not_food_chain_or_order():
    evidence = snapshot()
    evidence["observation_events"] = [{
        "observation_event_id": "OBS-TRANSFER", "pig_id": "PIG-2026-B156",
        "observed_at": "2026-08-16T09:00:00+00:00", "recorded_at": "2026-08-16T09:00:00+00:00",
        "supersedes_observation_event_id": None,
        "measurements_json": {
            "contract_version": "herdmaster_live_transfer_evidence_action_v1",
            "fit_for_transport": "fit", "quarantine": "clear",
            "infectious_or_notifiable_disease_restriction": "none_known",
            "veterinary_movement_stop": "none_known",
            "serious_welfare_or_health_hold": "clear",
        },
    }]
    row = by_tag(compose_live_transfer_contract(evidence, as_of=date(2026, 8, 16)))["151"]

    assert row["livestock_transfer_eligibility"]["state"] == "eligible_on_current_evidence"
    assert "not verified veterinary" in row["fit_for_transport"]["reason"]
    assert row["food_chain_eligibility"]["state"] == "blocked"
    assert row["current_order_eligibility"]["state"] == "blocked"
    assert all(row[name]["evidence_ids"] == ["OBS-TRANSFER"] for name in (
        "fit_for_transport", "quarantine", "notifiable_or_infectious_disease",
        "veterinary_movement_stop", "serious_health_or_welfare_hold"))


def test_missing_or_arithmetic_conflicting_withdrawal_never_becomes_food_chain_clear():
    for change in (
        {"withdrawal_end_date": None},
        {"withdrawal_end_date": "2026-08-04"},
    ):
        evidence = snapshot()
        evidence["medical_events"] = [
            {**row, **change} if row["pig_id"] == "PIG-2026-A643" else row
            for row in evidence["medical_events"]
        ]
        row = by_tag(compose_live_transfer_contract(evidence, as_of=date(2026, 8, 16)))["123"]
        assert row["food_chain_eligibility"]["state"] == "conflicting"
        assert "cannot be affirmed" in row["food_chain_eligibility"]["reason"]


def test_cutoff_and_observation_supersession_govern_current_without_hiding_history():
    baseline = compose_live_transfer_contract(snapshot(), as_of=date(2026, 8, 16))
    evidence = snapshot()
    evidence["medical_events"].append(
        medical("MED-FUTURE", "PIG-2026-B156", "Ecomectin 1%",
                "2026-08-17", "2026-09-14", 28, created="2026-08-17T08:00:00+00:00")
    )
    evidence["observation_events"] = [
        {"observation_event_id": "OBS-OLD", "pig_id": "PIG-2026-B156",
         "observed_at": "2026-08-14T08:00:00+00:00", "recorded_at": "2026-08-14T09:00:00+00:00",
         "supersedes_observation_event_id": None},
        {"observation_event_id": "OBS-NEW", "pig_id": "PIG-2026-B156",
         "observed_at": "2026-08-15T08:00:00+00:00", "recorded_at": "2026-08-15T09:00:00+00:00",
         "supersedes_observation_event_id": "OBS-OLD"},
        {"observation_event_id": "OBS-FUTURE", "pig_id": "PIG-2026-B156",
         "observed_at": "2026-08-17T08:00:00+00:00", "recorded_at": "2026-08-17T09:00:00+00:00",
         "supersedes_observation_event_id": None},
    ]
    evidence["location_events"].append({
        "location_event_id": "MOV-FUTURE", "pig_id": "PIG-2026-B156",
        "move_date": "2026-08-17", "created_at": "2026-08-17T09:00:00+00:00",
    })
    row = by_tag(compose_live_transfer_contract(evidence, as_of=date(2026, 8, 16)))["151"]
    health = row["canonical_dependency_evidence"]["health_and_welfare"]

    assert health["current_event_ids"] == ["OBS-NEW"]
    assert health["history_event_ids"] == ["OBS-OLD", "OBS-NEW"]
    assert health["superseded_event_ids"] == ["OBS-OLD"]
    assert "MED-FUTURE" not in {item["medical_event_id"] for item in row["canonical_treatment_events"]}
    assert "MED-FUTURE" not in {item["medical_event_id"] for item in row["canonical_treatment_history"]}
    evidence_without_future_observation = snapshot()
    evidence_without_future_observation["observation_events"] = evidence["observation_events"][:2]
    with_pre_cutoff_observations = compose_live_transfer_contract(
        evidence_without_future_observation, as_of=date(2026, 8, 16))
    with_future_evidence = compose_live_transfer_contract(evidence, as_of=date(2026, 8, 16))
    assert with_future_evidence["packet_digest"] == with_pre_cutoff_observations["packet_digest"]
    assert baseline["packet_digest"] != with_pre_cutoff_observations["packet_digest"]


def test_loader_uses_one_repeatable_read_read_only_snapshot_and_no_write_sql():
    class Cursor:
        def __init__(self, rows): self.rows = rows
        def fetchall(self): return self.rows
        def fetchone(self): return self.rows[0] if self.rows else None

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
            if "from public.pig_weight_events" in normalized:
                return Cursor([
                    {"pig_id": "PIG-2026-A643", "average_daily_gain_kg": 0.2},
                    {"pig_id": "PIG-2026-B156", "average_daily_gain_kg": 0.1},
                ])
            if "from public.orders" in normalized:
                return Cursor([ORDER])
            if "from public.order_lines" in normalized:
                return Cursor(snapshot()["order_lines"])
            if "from public.pig_observation_events" in normalized:
                return Cursor(snapshot()["observation_events"])
            if "from public.pig_location_events" in normalized:
                return Cursor(snapshot()["location_events"])
            if "from public.sales_pricing" in normalized:
                return Cursor(snapshot()["price_rows"])
            if "to_regclass('public.pig_medical_correction_events')" in normalized:
                return Cursor([("pig_medical_correction_events",)])
            if "to_regclass('public.order_lines_one_active_pig_per_order_idx')" in normalized:
                return Cursor([("order_lines_one_active_pig_per_order_idx",)])
            if "from public.pig_medical_correction_events" in normalized:
                return Cursor(snapshot()["medical_correction_events"])
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
