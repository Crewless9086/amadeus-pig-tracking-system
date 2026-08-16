"""Read-only livestock-transfer and food-chain evidence contract.

The contract deliberately does not change sale purpose, reserve stock, add an
order line, generate a document, or create a disclosure acknowledgement.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal

from services.database_service import DATABASE_URL_ENV
from modules.sales.sam_pricing import resolve_live_stock_price_rule


CONTRACT_VERSION = "herdmaster_live_transfer_disclosure_v1"
WORDING_VERSION = "livestock_treatment_disclosure_en_v1"
DISCLOSURE_SNAPSHOT_VERSION = "livestock_disclosure_snapshot_v1"
DOCUMENT_TARGETS = (
    "Loading Sheet",
    "Removal Certificate",
    "Health Declaration",
    "Quote / Order Confirmation",
)
DOCUMENT_PROJECTION_REQUIREMENTS = {
    "Loading Sheet": (
        "Show the pig identity, immutable disclosure snapshot and current live-transfer "
        "gate states; food-chain withdrawal remains a separate conspicuous restriction."
    ),
    "Removal Certificate": (
        "Show the pig and medical-event identities, treatment/product/date, withdrawal end, "
        "wording and document versions, and the disclosure digest."
    ),
    "Health Declaration": (
        "Disclose the canonical treatment evidence and every Unknown or blocking veterinary, "
        "disease, quarantine, welfare, movement and transport axis without asserting clearance."
    ),
    "Quote / Order Confirmation": (
        "Disclose the treatment and food-chain restriction before acceptance, identify whether "
        "the pig is or is not an order line, and bind any later acknowledgement to this version."
    ),
}


def _text(value):
    return str(value or "").strip()


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(_text(value)[:10])
    except ValueError:
        return None


def _number(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError, ArithmeticError):
        return None


def _json_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _digest(value):
    material = json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_value)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _axis(state, reason, evidence_ids=()):
    return {
        "state": state,
        "reason": reason,
        "evidence_ids": [item for item in evidence_ids if item],
    }


def _weight_band(weight):
    if weight is None:
        return None
    for low, high, band in ((2, 5, "2_to_4_Kg"), (5, 7, "5_to_6_Kg"),
                            (7, 10, "7_to_9_Kg"), (10, 15, "10_to_14_Kg"),
                            (15, 20, "15_to_19_Kg")):
        if low <= weight < high:
            return band
    return None


def _sale_category(weight):
    if weight is None:
        return None
    if 2 <= weight < 7:
        return "Young Piglets"
    if 7 <= weight < 20:
        return "Weaner Piglets"
    if 20 <= weight < 50:
        return "Grower Pigs"
    if 50 <= weight < 80:
        return "Finisher Pigs"
    if 80 <= weight < 95:
        return "Ready for Slaughter"
    return None


def _treatment_evidence(events):
    normalized, issues = [], []
    seen = set()
    clinical_signatures = {}
    for row in sorted(events, key=lambda item: (
            _text(item.get("treatment_date")), _text(item.get("created_at")),
            _text(item.get("medical_event_id")))):
        event = {
            "medical_event_id": _text(row.get("medical_event_id")) or None,
            "pig_id": _text(row.get("pig_id")) or None,
            "product_id": _text(row.get("product_id")) or None,
            "product": _text(row.get("product_name")) or None,
            "treatment_type": _text(row.get("treatment_type")) or None,
            "treatment_date": _text(row.get("treatment_date"))[:10] or None,
            "dose": _number(row.get("dose")),
            "dose_unit": _text(row.get("dose_unit")) or None,
            "route": _text(row.get("route")) or None,
            "reason_for_treatment": _text(row.get("reason_for_treatment")) or None,
            "batch_lot_number": _text(row.get("batch_lot_number")) or None,
            "withdrawal_days": int(row["withdrawal_days"]) if row.get("withdrawal_days") is not None else None,
            "withdrawal_end_date": _text(row.get("withdrawal_end_date"))[:10] or None,
            "given_by": _text(row.get("given_by")) or None,
            "source_sheet_row": row.get("source_sheet_row"),
            "import_batch_id": _text(row.get("import_batch_id")) or None,
            "recorded_at": _text(row.get("created_at")) or None,
            "follow_up_required": row.get("follow_up_required"),
            "follow_up_date": _text(row.get("follow_up_date"))[:10] or None,
            "medical_notes": _text(row.get("medical_notes")) or None,
            "predecessor_medical_event_id": None,
            "superseded_by_medical_event_id": None,
            "correction_lineage_state": "not_supported_by_current_medical_schema",
        }
        required = ("medical_event_id", "pig_id", "product", "treatment_date",
                    "withdrawal_days", "withdrawal_end_date", "recorded_at")
        missing = [field for field in required if event.get(field) in (None, "")]
        if missing:
            issues.append({"medical_event_id": event["medical_event_id"], "missing": missing})
        identity = event["medical_event_id"]
        if identity in seen:
            issues.append({"medical_event_id": identity, "conflict": "duplicate_event_identity"})
        seen.add(identity)
        treatment_date = _date(event["treatment_date"])
        withdrawal_end = _date(event["withdrawal_end_date"])
        if (treatment_date and withdrawal_end and event["withdrawal_days"] is not None
                and (withdrawal_end - treatment_date).days != event["withdrawal_days"]):
            issues.append({"medical_event_id": identity, "conflict": "withdrawal_date_arithmetic_mismatch"})
        signature = (event["product_id"] or event["product"], event["treatment_date"],
                     event["dose"], event["dose_unit"], event["withdrawal_end_date"])
        if signature in clinical_signatures:
            issues.append({"medical_event_id": identity, "conflict": "possible_duplicate_treatment_evidence",
                           "other_medical_event_id": clinical_signatures[signature]})
        else:
            clinical_signatures[signature] = identity
        event["evidence_digest"] = _digest(event)
        normalized.append(event)
    state = "complete" if normalized and not issues else "Unknown" if not normalized else "conflicting"
    reason = ("Every canonical treatment event has identity, product, treatment date, withdrawal evidence and provenance."
              if state == "complete" else
              "No attributable canonical treatment event is available."
              if state == "Unknown" else
              "Canonical treatment evidence is incomplete or conflicting.")
    return normalized, _axis(state, reason, [row["medical_event_id"] for row in normalized]), issues


def _medical_ambiguity(events, conflicts):
    duplicate_pairs = [item for item in conflicts
                       if item.get("conflict") == "possible_duplicate_treatment_evidence"]
    if not duplicate_pairs:
        return {
            "state": "no_detected_same_signature_ambiguity",
            "event_pairs": [],
            "required_resolution": None,
        }
    by_id = {row["medical_event_id"]: row for row in events}
    pairs = []
    for item in duplicate_pairs:
        first = by_id.get(item.get("other_medical_event_id"), {})
        second = by_id.get(item.get("medical_event_id"), {})
        pairs.append({
            "medical_event_ids": [first.get("medical_event_id"), second.get("medical_event_id")],
            "recorded_at": [first.get("recorded_at"), second.get("recorded_at")],
            "product": second.get("product"),
            "dose": second.get("dose"),
            "dose_unit": second.get("dose_unit"),
            "treatment_date": second.get("treatment_date"),
            "provenance": [
                {key: row.get(key) for key in ("given_by", "source_sheet_row", "import_batch_id")}
                for row in (first, second)
            ],
        })
    return {
        "state": "unresolved_conflicting_evidence",
        "event_pairs": pairs,
        "required_resolution": (
            "An attributable owner or treating veterinary professional must state whether each "
            "same-signature pair records one administration twice or two separate administrations. "
            "If a row is erroneous, a governed append-only medical correction/supersession capability "
            "must be introduced before the effective medical projection can change."
        ),
    }


def _price_band_contract(pig, order, price_rows, as_of):
    weight = _number(pig.get("current_weight_kg"))
    pig_band = _weight_band(weight)
    category = _sale_category(weight)
    requested = _text(order.get("requested_weight_range")) or None
    rule = resolve_live_stock_price_rule(
        category, pig_band, _text(pig.get("sex")), as_of=as_of.isoformat(),
        price_entries=price_rows,
    )
    price = rule if rule.get("found") else None
    compatible = bool(pig_band and requested and pig_band == requested)
    return {
        "state": "compatible" if compatible else "incompatible" if pig_band and requested else "Unknown",
        "pig_weight_band": pig_band,
        "order_requested_weight_band": requested,
        "separately_priced_line_supported": price is not None,
        "separate_price_rule": ({
            "pricing_id": _text(price.get("pricing_id")),
            "sale_category": _text(price.get("sale_category")),
            "weight_band": _text(price.get("weight_band")),
            "unit_price": _number(price.get("unit_price")),
            "currency": _text(price.get("currency")) or None,
            "effective_from": _text(price.get("effective_from")) or None,
            "source": price.get("source") or "Supabase sales_pricing",
        } if price else None),
        "commercial_consequence": (
            "The pig matches the order header band. Any line price still requires SAM's protected order action."
            if compatible else
            "A separately priced line is technically supported by the canonical price book, but adding it would "
            "commercially depart from the order header's requested band and requires one protected owner preview."
            if price else
            "No authoritative separate price rule is available; price and order inclusion remain blocked."
        ),
    }


def _order_line_protection(pig, order, lines):
    pig_id = _text(pig.get("pig_id"))
    active = [row for row in lines if _text(row.get("pig_id")) == pig_id
              and _text(row.get("line_status")).lower() not in {"cancelled", "removed"}]
    return {
        "state": "existing_line_blocks_duplicate" if len(active) == 1
                 else "conflicting_duplicate_lines" if len(active) > 1 else "no_existing_line",
        "active_line_count": len(active),
        "active_order_line_ids": [_text(row.get("order_line_id")) for row in active],
        "database_unique_order_pig_constraint": False,
        "writer_dependency": (
            "SAM must retain its existing-line check and add transaction-safe canonical uniqueness/locking "
            "before any future line action; this read contract creates no line, reservation or allocation."
        ),
    }


def _food_chain(events, as_of, completeness):
    if completeness["state"] != "complete":
        return _axis(
            "Unknown" if completeness["state"] == "Unknown" else "conflicting",
            "Food-chain eligibility cannot be affirmed because applicable treatment withdrawal evidence is missing, invalid, or conflicting.",
            completeness.get("evidence_ids") or [],
        ), []
    active = [row for row in events if _date(row.get("withdrawal_end_date"))
              and _date(row.get("withdrawal_end_date")) >= as_of]
    if active:
        end = max(_date(row["withdrawal_end_date"]) for row in active)
        return _axis(
            "blocked",
            f"Food-chain entry remains prohibited through {end.isoformat()} by canonical treatment withdrawal evidence.",
            [row["medical_event_id"] for row in active],
        ), active
    if events:
        return _axis(
            "eligible_on_recorded_withdrawal_axis",
            "All recorded treatment withdrawal end dates are before the evidence cutoff; other food-chain gates remain separately applicable.",
            [row["medical_event_id"] for row in events],
        ), []
    return _axis("Unknown", "Food-chain eligibility is Unknown because attributable treatment evidence is absent."), []


def _within_cutoff(row, effective_field, recorded_field, as_of):
    effective = _date(row.get(effective_field))
    recorded = _date(row.get(recorded_field))
    return bool(effective and recorded and effective <= as_of and recorded <= as_of)


def _effective_observation_projection(rows, as_of):
    eligible = [row for row in rows if _within_cutoff(row, "observed_at", "recorded_at", as_of)]
    superseded = {_text(row.get("supersedes_observation_event_id")) for row in eligible
                  if _text(row.get("supersedes_observation_event_id"))}
    current = [row for row in eligible
               if _text(row.get("observation_event_id")) not in superseded]
    return {
        "current_event_ids": [_text(row.get("observation_event_id")) for row in current],
        "history_event_ids": [_text(row.get("observation_event_id")) for row in eligible],
        "superseded_event_ids": sorted(superseded),
        "excluded_future_or_undated_event_ids": [
            _text(row.get("observation_event_id")) for row in rows if row not in eligible
        ],
    }


def _missing_current_gate(name):
    labels = {
        "fit_for_transport": "No current attributable fit-for-transport assessment is stored in the supplied canonical snapshot.",
        "quarantine": "No current attributable quarantine-clearance or quarantine-hold fact is stored in the supplied canonical snapshot.",
        "notifiable_or_infectious_disease": "No current attributable notifiable/infectious-disease clearance or restriction fact is stored in the supplied canonical snapshot.",
        "veterinary_movement_stop": "No current attributable veterinary movement-clearance or movement-stop fact is stored in the supplied canonical snapshot.",
        "serious_health_or_welfare_hold": "No current attributable serious health/welfare clearance or hold fact is stored in the supplied canonical snapshot.",
    }
    return _axis("Unknown", labels[name])


def _order_axis(pig, order, lines):
    pig_id = _text(pig.get("pig_id"))
    matching = [line for line in lines if _text(line.get("pig_id")) == pig_id
                and _text(line.get("line_status")).lower() not in {"cancelled", "removed"}]
    requested_band = _text(order.get("requested_weight_range"))
    current_band = _weight_band(_number(pig.get("current_weight_kg")))
    if len(matching) > 1:
        ids = [_text(line.get("order_line_id")) for line in matching]
        return _axis(
            "conflicting_duplicate_lines",
            f"Pig has {len(matching)} active lines on order {_text(order.get('order_id'))}; canonical order eligibility fails closed until SAM reconciles them.",
            ids,
        )
    if matching:
        line = matching[0]
        return _axis(
            "included_draft_unreserved" if _text(line.get("reserved_status")).lower() in {"not_reserved", "not reserved"} else "blocked",
            f"Pig is already present once on order {_text(order.get('order_id'))} as line {_text(line.get('order_line_id'))}; reservation remains {_text(line.get('reserved_status')) or 'Unknown'}.",
            [_text(line.get("order_line_id"))],
        )
    if requested_band and current_band != requested_band:
        return _axis(
            "blocked",
            f"Latest weight maps to {current_band or 'Unknown'} and does not match order request {requested_band}.",
        )
    return _axis(
        "candidate_not_added",
        "Purpose and weight-band evidence support order review, but no order line or reservation has been created by this contract.",
    )


def _disclosure(pig, active_events):
    if not active_events:
        return None
    governing = max(active_events, key=lambda row: (
        _date(row.get("withdrawal_end_date")) or date.min,
        _text(row.get("recorded_at")), _text(row.get("medical_event_id"))))
    tag = _text(pig.get("tag_number")) or "Unknown"
    wording = (
        f"Tag {tag} received {governing['product']} on {governing['treatment_date']}. "
        f"Food-chain withdrawal applies through {governing['withdrawal_end_date']}; do not slaughter or enter the animal into the food chain during that period. "
        "This treatment disclosure does not certify fitness for transport or veterinary, welfare, disease, quarantine, or movement clearance."
    )
    evidence = {
        "pig_id": _text(pig.get("pig_id")),
        "tag_number": tag,
        "medical_event_id": governing["medical_event_id"],
        "product": governing["product"],
        "treatment_date": governing["treatment_date"],
        "withdrawal_end_date": governing["withdrawal_end_date"],
        "evidence_provenance": {
            "given_by": governing["given_by"],
            "recorded_at": governing["recorded_at"],
            "source_sheet_row": governing["source_sheet_row"],
            "import_batch_id": governing["import_batch_id"],
        },
        "medical_evidence_digest": governing["evidence_digest"],
        "wording_version": WORDING_VERSION,
        "safe_buyer_wording": wording,
        "affected_document_targets": list(DOCUMENT_TARGETS),
        "food_chain_prohibition": True,
    }
    evidence["disclosure_digest"] = _digest(evidence)
    return evidence


def compose_live_transfer_contract(snapshot, *, as_of=None):
    as_of = as_of or date.today()
    order = dict(snapshot.get("order") or {})
    lines = list(snapshot.get("order_lines") or [])
    medical = list(snapshot.get("medical_events") or [])
    observations = list(snapshot.get("observation_events") or [])
    movements = list(snapshot.get("location_events") or [])
    price_rows = list(snapshot.get("price_rows") or [])
    results = []
    for pig in list(snapshot.get("pigs") or []):
        pig_id = _text(pig.get("pig_id"))
        pig_medical = [row for row in medical if _text(row.get("pig_id")) == pig_id]
        governed_medical = [row for row in pig_medical
                            if _within_cutoff(row, "treatment_date", "created_at", as_of)]
        excluded_medical = [row for row in pig_medical if row not in governed_medical]
        events, completeness, conflicts = _treatment_evidence(governed_medical)
        history_events, _, _ = _treatment_evidence(pig_medical)
        ambiguity = _medical_ambiguity(events, conflicts)
        food_chain, active = _food_chain(events, as_of, completeness)
        observation_projection = _effective_observation_projection(
            [row for row in observations if _text(row.get("pig_id")) == pig_id], as_of)
        independent = {
            name: _missing_current_gate(name) for name in (
                "fit_for_transport", "quarantine", "notifiable_or_infectious_disease",
                "veterinary_movement_stop", "serious_health_or_welfare_hold")
        }
        purpose = _text(pig.get("purpose")) or "Unknown"
        status = _text(pig.get("status")) or "Unknown"
        on_farm = pig.get("on_farm") if pig.get("on_farm") is not None else None
        purpose_axis = (_axis("eligible", "Current canonical purpose is Sale.")
                        if purpose == "Sale" else
                        _axis("blocked", f"Current canonical purpose is {purpose}."))
        active_axis = (_axis("eligible", "Pig is Active and currently on farm.")
                       if status == "Active" and on_farm is True else
                       _axis("blocked" if status != "Unknown" and on_farm is not None else "Unknown",
                             f"Current status is {status}; on_farm is {on_farm}."))
        order_axis = _order_axis(pig, order, lines)
        required_states = [purpose_axis["state"], active_axis["state"], completeness["state"],
                           *(axis["state"] for axis in independent.values())]
        if "blocked" in required_states or "conflicting" in required_states:
            transfer = _axis("blocked", "At least one independent live-transfer gate is blocked or conflicting.")
        elif "Unknown" in required_states:
            transfer = _axis(
                "Unknown",
                "Live transfer is not yet supported because one or more current transport, disease, quarantine, veterinary, welfare, or treatment-evidence gates are Unknown.",
            )
        else:
            transfer = _axis(
                "eligible_on_current_evidence",
                "Every required live-transfer gate is affirmatively supported; food-chain eligibility remains separate.",
            )
        disclosure = _disclosure(pig, active)
        if disclosure:
            disclosure["live_transfer_supported_by_every_other_current_gate"] = (
                True if transfer["state"] == "eligible_on_current_evidence"
                else False if transfer["state"] == "blocked" else None)
        results.append({
            "identity": {"pig_id": pig_id, "tag_number": _text(pig.get("tag_number")) or None,
                         "name": _text(pig.get("pig_name")) or None,
                         "animal_type": _text(pig.get("animal_type")) or None},
            "current_state": {"purpose": purpose, "status": status, "on_farm": on_farm,
                              "latest_weight_kg": _number(pig.get("current_weight_kg")),
                              "latest_weight_date": _text(pig.get("last_weight_date"))[:10] or None,
                              "derived_weight_band": _weight_band(_number(pig.get("current_weight_kg")))},
            "livestock_transfer_eligibility": transfer,
            "food_chain_eligibility": food_chain,
            **independent,
            "treatment_evidence_completeness": completeness,
            "treatment_evidence_conflicts": conflicts,
            "medical_ambiguity": ambiguity,
            "medical_correction_authority": {
                "state": "missing_for_medical_events",
                "medical_schema_supports_supersession": False,
                "existing_append_only_observation_supersession": True,
                "boundary": "pig_observation_events may preserve a factual correction statement, but it cannot supersede or rewrite pig_medical_events.",
            },
            "current_purpose_eligibility": purpose_axis,
            "active_on_farm_eligibility": active_axis,
            "current_order_eligibility": order_axis,
            "order_line_duplication_protection": _order_line_protection(pig, order, lines),
            "price_band_compatibility": _price_band_contract(pig, order, price_rows, as_of),
            "canonical_dependency_evidence": {
                "health_and_welfare": {
                    "authority": "pig_observation_events",
                    **observation_projection,
                    "limitation": "No typed current clearance event is present; narrative absence cannot prove clearance.",
                },
                "movement": {
                    "authority": "pig_location_events plus an attributable veterinary movement-stop fact",
                    "history_event_ids": [_text(row.get("location_event_id")) for row in movements
                                          if _text(row.get("pig_id")) == pig_id],
                    "limitation": "Movement history establishes location chronology, not fitness or movement clearance.",
                },
                "quarantine_and_disease": {
                    "authority": "attributable veterinary/competent-authority evidence projected through the canonical health observation rail",
                    "current_event_ids": [],
                    "limitation": "No canonical current typed quarantine, notifiable/infectious-disease, or veterinary-stop fact is available.",
                },
            },
            "canonical_treatment_events": events,
            "canonical_treatment_history": history_events,
            "excluded_future_or_undated_medical_event_ids": [
                _text(row.get("medical_event_id")) for row in excluded_medical
            ],
            "treatment_disclosure": disclosure,
        })
    packet = {
        "contract_version": CONTRACT_VERSION,
        "status": "replacement_preview_zero_write",
        "supersedes": "op004_tags_123_151_purpose_only_preview",
        "evidence_cutoff_date": as_of.isoformat(),
        "order": {"order_id": _text(order.get("order_id")),
                  "status": _text(order.get("order_status")) or "Unknown",
                  "approval_status": _text(order.get("approval_status")) or "Unknown",
                  "requested_weight_range": _text(order.get("requested_weight_range")) or None,
                  "requested_quantity": order.get("requested_quantity"),
                  "existing_line_count": len(lines)},
        "pigs": results,
        "document_projections": [{
            "document_type": target,
            "status": "not_generated_design_only",
            "required_projection": DOCUMENT_PROJECTION_REQUIREMENTS[target],
            "required_binding": ["order_id", "order_line_id", "pig_id", "medical_event_id",
                                 "medical_evidence_digest", "wording_version", "document_id",
                                 "document_version"],
        } for target in DOCUMENT_TARGETS],
        "buyer_acknowledgement_contract": {
            "status": "design_only_not_created",
            "snapshot_version": DISCLOSURE_SNAPSHOT_VERSION,
            "append_only_binding": ["order_id", "order_line_id", "pig_id", "medical_event_id",
                                    "medical_evidence_digest", "wording_version", "document_type",
                                    "document_id", "document_version", "buyer_identity", "acknowledged_at"],
            "medical_change_rule": "A changed canonical medical digest marks prior document/disclosure versions outdated and requires a new snapshot and acknowledgement; history is never rewritten.",
            "authority_boundary": "Acknowledgement proves receipt only. It does not modify treatment evidence or establish veterinary, transport, movement, quarantine, welfare, disease, slaughter, or food-chain clearance.",
        },
        "writes_performed": False,
        "creates_order_line": False,
        "creates_reservation": False,
        "generates_document": False,
        "creates_buyer_acknowledgement": False,
        "remaining_dependencies": [
            "Tag 123 requires factual or veterinary resolution of each same-signature treatment pair and a governed append-only medical correction rail before its effective medical state can change.",
            "Tag 151 requires current attributable transport-fitness, quarantine, disease, veterinary movement-stop and serious welfare/health evidence.",
            "Tag 151's 2_to_4_Kg line would depart from the order's 5_to_6_Kg request and therefore requires a later protected SAM commercial preview; no order change is authorized here.",
            "SAM must enforce transaction-safe no-duplicate order-line semantics before any later line creation.",
        ],
    }
    packet["packet_digest"] = _digest(packet)
    return packet


def load_live_transfer_snapshot(pig_ids, order_id, *, connect_factory=None):
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if connect_factory:
        connection = connect_factory(database_url)
    else:
        if not database_url:
            raise RuntimeError("canonical_database_unavailable")
        import psycopg
        from psycopg.rows import dict_row
        connection = psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10)
    with connection:
        connection.execute("set transaction isolation level repeatable read read only")
        pigs = connection.execute("""
            select p.*,s.current_weight_kg,s.last_weight_date
            from public.current_canonical_pigs p
            left join public.current_canonical_pig_state s using(pig_id)
            where p.pig_id=any(%s) order by p.pig_id
        """, (list(pig_ids),)).fetchall()
        if {_text(row.get("pig_id")) for row in pigs} != set(pig_ids):
            raise ValueError("canonical_pig_identity_mismatch")
        medical = connection.execute("""
            select * from public.pig_medical_events
            where pig_id=any(%s)
            order by pig_id,treatment_date,created_at,medical_event_id
        """, (list(pig_ids),)).fetchall()
        orders = connection.execute("select * from public.orders where order_id=%s", (order_id,)).fetchall()
        if len(orders) != 1:
            raise ValueError("canonical_order_identity_mismatch")
        lines = connection.execute("""
            select * from public.order_lines where order_id=%s
            order by created_at,order_line_id
        """, (order_id,)).fetchall()
        observations = connection.execute("""
            select observation_event_id,pig_id,observed_at,recorded_at,observer_reference,
                   observation_category,severity,factual_note,source_system,source_reference,
                   supersedes_observation_event_id,measurements_json
            from public.pig_observation_events where pig_id=any(%s)
            order by pig_id,observed_at,recorded_at,observation_event_id
        """, (list(pig_ids),)).fetchall()
        locations = connection.execute("""
            select location_event_id,pig_id,move_date,from_pen_id,to_pen_id,reason_for_move,
                   moved_by,move_notes,source,created_at
            from public.pig_location_events where pig_id=any(%s)
            order by pig_id,move_date,created_at,location_event_id
        """, (list(pig_ids),)).fetchall()
        prices = connection.execute("""
            select pricing_id,sale_category,weight_band,sex,unit_price,currency,effective_from,
                   effective_to,active,change_reason,created_by,created_at
            from public.sales_pricing where active=true
            order by sale_category,weight_band,sex,effective_from desc,created_at desc
        """).fetchall()
    return {"pigs": list(pigs), "medical_events": list(medical),
            "order": dict(orders[0]), "order_lines": list(lines),
            "observation_events": list(observations), "location_events": list(locations),
            "price_rows": list(prices)}


def build_live_transfer_contract(pig_ids, order_id, *, as_of=None, connect_factory=None):
    return compose_live_transfer_contract(
        load_live_transfer_snapshot(pig_ids, order_id, connect_factory=connect_factory),
        as_of=as_of,
    )
