"""Pure, zero-I/O reconciliation and preview for completed livestock auction lots."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

CONTRACT_VERSION = "herdmaster_auction_sale_v2"
INVOICE_FACTS = {
    "sale_date": "2026-08-05",
    "outlet_name": "BKB",
    "outlet_location": "Riversdal",
    "invoice_reference": "S-EE02-2710",
    "gross_revenue_ex_vat": "4180.00",
    "output_vat": "627.00",
    "gross_including_vat": "4807.00",
    "commission_ex_vat": "292.60",
    "commission_input_vat": "43.89",
    "commission_including_vat": "336.49",
    "other_deductions": "0.00",
    "net_settlement_payable": "4470.51",
    "payment_method": "EFT",
}


def build_auction_sale_preview(report, evidence):
    if not isinstance(report, dict) or not isinstance(evidence, dict):
        return _fail("typed_report_and_evidence_required")
    tags = [_tag(value) for value in report.get("tags", []) if _tag(value)]
    if len(tags) != 18 or len(set(tags)) != 18:
        return _fail("exactly_18_unique_tags_required")
    rows = evidence.get("pigs") if isinstance(evidence.get("pigs"), list) else []
    if not all(isinstance(row, dict) for row in rows):
        return _fail("canonical_pig_rows_required")

    matrix, conflicts = [], []
    for tag in tags:
        matches = [row for row in rows if _tag(row.get("tag_number")) == tag]
        if len(matches) != 1:
            conflicts.append({"tag": tag, "reason": "unresolved" if not matches else "duplicate_identity"})
            continue
        pig, reasons = matches[0], []
        if not _text(pig.get("pig_id")): reasons.append("canonical_pig_id_missing")
        if _norm(pig.get("status")) != "active" or pig.get("on_farm") is not True: reasons.append("not_currently_active_on_farm")
        if _norm(pig.get("purpose")) != "sale": reasons.append("sale_purpose_not_proven")
        if _norm(pig.get("availability_state")) != "available": reasons.append("availability_not_proven")
        if _norm(pig.get("reservation_order_state")) not in {"none", "clear", "unreserved"}: reasons.append("reservation_or_order_clearance_not_proven")
        if pig.get("active_reservation") is not False or pig.get("active_order") is not False: reasons.append("reserved_or_ordered_elsewhere_or_unknown")
        if pig.get("prior_sale") is not False or _norm(pig.get("prior_sale_state")) not in {"none", "clear"}: reasons.append("prior_sale_clearance_not_proven")
        if _norm(pig.get("withdrawal_state")) not in {"explicitly_cleared", "complete_through_no_active_withdrawal"}: reasons.append("withdrawal_or_medical_clearance_not_proven")
        matrix.append({
            "tag": tag, "pig_id": _text(pig.get("pig_id")), "status": _text(pig.get("status")),
            "on_farm": pig.get("on_farm"), "purpose": _known(pig.get("purpose")),
            "pen": _known(pig.get("current_pen_name")), "availability": _known(pig.get("availability_state")),
            "reservation_order": _known(pig.get("reservation_order_state")),
            "withdrawal_medical": _known(pig.get("withdrawal_state")), "identity_conflict": False,
            "eligible": not reasons, "conflicts": reasons,
        })
        conflicts.extend({"tag": tag, "pig_id": pig.get("pig_id"), "reason": reason} for reason in reasons)
    ids = [row["pig_id"] for row in matrix]
    if len(ids) != len(set(ids)): conflicts.append({"reason": "duplicate_canonical_pig"})

    text_fields = {"sale_date", "outlet_name", "outlet_location", "invoice_reference", "payment_method"}
    for key, expected in INVOICE_FACTS.items():
        supplied = report.get(key)
        if supplied in (None, ""):
            continue
        actual = _text(supplied) if key in text_fields else _money(supplied)
        if actual != expected:
            conflicts.append({"reason": key + "_invoice_mismatch"})
    invoice_identity = _invoice_identity(report.get("invoice_evidence"))
    if not invoice_identity or invoice_identity["status"] != "bound":
        conflicts.append({"reason": "private_invoice_evidence_binding_required"})
        invoice_identity = invoice_identity or {"status": "invalid", "evidence_id": "Unknown", "sha256": "Unknown"}

    payment_received = report.get("payment_received")
    if payment_received not in (None, True, False): conflicts.append({"reason": "payment_received_must_be_true_false_or_unknown"})
    v10_tags = [_tag(value) for value in report.get("v10_tags", []) if _tag(value)]
    if v10_tags and (len(v10_tags) != 8 or len(set(v10_tags)) != 8 or not set(v10_tags).issubset(tags)):
        conflicts.append({"reason": "v10_membership_must_be_exactly_8_sale_tags"})
    v11_tags = [tag for tag in tags if tag not in v10_tags] if v10_tags else []

    total_weight = sum((Decimal(str(row.get("latest_weight_kg"))) for row in rows if _tag(row.get("tag_number")) in tags and row.get("latest_weight_kg") is not None), Decimal("0"))
    analytics = {
        "basis": "Analytical estimates using latest recorded weights dated 2026-08-03; invoice auction mass is zero/absent.",
        "combined_latest_weight_kg": str(total_weight.quantize(Decimal("0.1"))),
        "average_latest_weight_kg": str((total_weight / Decimal("18")).quantize(Decimal("0.01"))),
        "gross_including_vat_per_pig": "267.06",
        "net_settlement_per_pig": "248.36",
        "net_settlement_per_latest_kg": "28.92",
        "recommendation": "Unavailable until attributable feed-cost, growth-rate, direct-sale value, and pen-capacity evidence exists.",
    }
    payment_status = "Received" if payment_received is True else "Not_received" if payment_received is False else "Unknown"
    payload = {
        "success": not conflicts, "contract_version": CONTRACT_VERSION,
        "evidence_generation": evidence.get("evidence_generation"), "tags": tags, "pig_count": len(matrix),
        "matrix": matrix, "currency": "ZAR", "sale_stream": "Livestock", "sale_channel": "Auction",
        **INVOICE_FACTS, "payment_status": payment_status,
        "payment_received_total": "4470.51" if payment_received is True else "Unknown",
        "payment_received_evidence": "owner_or_bank_evidence_required" if payment_received is None else "owner_report_pending_persistence",
        "individual_proceeds": "Unknown", "v10_tags": v10_tags or "Unknown", "v11_tags": v11_tags or "Unknown",
        "invoice_evidence_identity": invoice_identity, "management_analysis": analytics,
        "missing_facts": [], "conflicts": conflicts, "ready_for_confirmation": not conflicts,
        "grouped_question": None if payment_received is not None and v10_tags else "Has the R4,470.51 EFT reached the bank account, and if known, which eight pigs were in V10?",
        "question_optional_for_sale": True,
        "proposed_effects": ["one completed Livestock/Auction sale and August receivable", "18 linked pig items with individual prices Unknown", "each pig Sold and off-farm with Auction Sale exit", "18 immutable exited-farm lifecycle events", "preserve all historical animal records", "report gross revenue, VAT, commission and net settlement separately", "do not claim cash receipt without later payment evidence"],
        "delivery_enabled": False, "write_enabled": False, "payment_reconciliation_enabled": False,
        "mating_execution_enabled": False, "customer_contact_enabled": False,
    }
    operation_facts = {key: payload[key] for key in (*INVOICE_FACTS.keys(), "tags", "payment_status", "v10_tags", "invoice_evidence_identity")}
    payload["operation_id"] = "HERD-AUCTION-" + _digest(operation_facts)[:32].upper()
    payload["english"] = _render(payload, "en")
    payload["afrikaans"] = _render(payload, "af")
    payload["preview_hash"] = "AUCT-PREVIEW-" + _digest(payload)[:32].upper()
    return payload


def _render(p, lang):
    mappings = ", ".join(f"{row['tag']} → {row['pig_id']}" for row in p["matrix"])
    if lang == "af":
        return f"BKB Riversdal-veiling op 5 Augustus 2026, faktuur S-EE02-2710. 18 varke: {mappings}. Bruto inkomste uitgesluit BTW R4 180,00; uitset-BTW R627,00; bruto ingesluit BTW R4 807,00; kommissie uitgesluit BTW R292,60; kommissie-inset-BTW R43,89; kommissie ingesluit BTW R336,49; ander aftrekkings R0,00; netto vereffening betaalbaar R4 470,51 via EFT. Betaling ontvang: {('Ja' if p['payment_status']=='Received' else 'Nee' if p['payment_status']=='Not_received' else 'Onbekend')}. Individuele varkpryse en lotlidmaatskap: Onbekend. Voorgestel: merk al 18 Verkoop en van die plaas af; behou geskiedenis. Niks word geskryf voor die presiese voorskou bevestig is nie."
    return f"BKB Riversdal auction on 5 August 2026, invoice S-EE02-2710. 18 pigs: {mappings}. Gross revenue excluding VAT R4,180.00; output VAT R627.00; gross including VAT R4,807.00; commission excluding VAT R292.60; commission input VAT R43.89; commission including VAT R336.49; other deductions R0.00; net settlement payable R4,470.51 by EFT. Payment received: {p['payment_status']}. Individual pig prices and tag-to-lot membership: Unknown. Proposed: mark all 18 Sold and off-farm; preserve history. Nothing is recorded until the exact preview is confirmed."


def _fail(reason): return {"success": False, "contract_version": CONTRACT_VERSION, "reason": reason, "delivery_enabled": False, "write_enabled": False, "payment_reconciliation_enabled": False, "mating_execution_enabled": False, "customer_contact_enabled": False}
def _tag(value): return _public(_text(value).lstrip("#"))
def _text(value): return str(value or "").strip()
def _norm(value): return _text(value).lower().replace(" ", "_").replace("-", "_")
def _known(value): return _text(value) or "Unknown"
def _public(value): return " ".join("".join(" " if ch in "\r\n\t" else ch for ch in _text(value) if not unicodedata.category(ch).startswith("C") or ch in "\r\n\t").split())
def _money(value):
    try: return str(Decimal(str(value)).quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError, TypeError): return "invalid"
def _invoice_identity(value):
    if not isinstance(value, dict): return None
    evidence_id, digest = _public(value.get("evidence_id")), _text(value.get("sha256")).lower()
    if not evidence_id or len(evidence_id) > 160 or not re.fullmatch(r"[0-9a-f]{64}", digest): return None
    return {"status": "bound", "evidence_id": evidence_id, "sha256": digest}
def _digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
