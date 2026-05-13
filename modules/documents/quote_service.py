from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import tempfile

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from modules.documents.document_service import (
    DOCUMENT_TYPE_QUOTE,
    STATUS_GENERATED,
    append_order_document,
    build_document_file_name,
    build_document_ref,
    build_payment_ref,
    generate_document_id,
    get_document_settings,
    get_latest_non_voided_quote,
    get_next_document_version,
)
from modules.orders.order_service import (
    ORDER_LINES_SHEET,
    _get_order_master_row,
    get_order_detail,
)
from services.google_sheets_service import get_all_records
from services.google_drive_service import upload_file_to_drive


REQUIRED_QUOTE_SETTINGS = [
    "quote_valid_days",
    "vat_rate",
    "business_name",
    "business_address_line_1",
    "business_address_line_2",
    "business_address_line_3",
    "business_phone",
    "business_email",
    "business_vat_number",
    "bank_name",
    "bank_account_name",
    "bank_account_type",
    "bank_account_number",
    "bank_branch_code",
    "quote_drive_folder_id",
    "document_logo_path",
    "draft_quote_note",
]


QUOTE_FINGERPRINT_PREFIX = "Quote_Fingerprint:"


def auto_generate_quote_if_ready(order_id, created_by="App"):
    readiness = get_quote_readiness(order_id)

    if not readiness["quote_ready"]:
        return {
            "success": True,
            "action": "auto_generate_quote_if_ready",
            "quote_ready": False,
            "generated": False,
            "skipped": True,
            "reason": "not_quote_ready",
            "missing_fields": readiness["missing_fields"],
            "order_id": str(order_id or "").strip(),
            "message": "Quote was not generated because the draft is not quote-ready.",
        }

    latest = get_latest_non_voided_quote(order_id)
    if latest and _document_has_fingerprint(latest, readiness["fingerprint"]):
        return {
            "success": True,
            "action": "auto_generate_quote_if_ready",
            "quote_ready": True,
            "generated": False,
            "skipped": True,
            "reason": "latest_quote_current",
            "order_id": str(order_id or "").strip(),
            "document": _document_summary(latest),
            "message": "Latest quote already matches the current draft.",
        }

    result = _generate_quote_for_order(
        order_id,
        created_by=created_by,
        quote_fingerprint=readiness["fingerprint"],
    )

    return {
        "success": True,
        "action": "auto_generate_quote_if_ready",
        "quote_ready": True,
        "generated": True,
        "skipped": False,
        "reason": "generated",
        "order_id": str(order_id or "").strip(),
        "document": _result_document_summary(result),
        "message": "Quote generated automatically because the draft is quote-ready.",
    }


def get_quote_readiness(order_id):
    order_id = str(order_id or "").strip()
    detail = _get_quote_order_detail(order_id)
    if not detail:
        return {
            "quote_ready": False,
            "missing_fields": ["order"],
            "order_id": order_id,
            "fingerprint": "",
        }

    order = detail["order"]
    lines = _active_lines(detail["lines"])
    missing_fields = []

    if str(order.get("order_status", "")).strip() != "Draft":
        missing_fields.append("draft_status")
    if not str(order.get("customer_name", "")).strip():
        missing_fields.append("customer_name")
    if str(order.get("payment_method", "")).strip() not in ("Cash", "EFT"):
        missing_fields.append("payment_method")
    if not str(order.get("collection_location", "")).strip():
        missing_fields.append("collection_location")
    if not lines:
        missing_fields.append("active_order_lines")
    requested_quantity = _to_float_or_zero(order.get("requested_quantity", 0))
    if requested_quantity > 0 and len(lines) < requested_quantity:
        missing_fields.append("complete_order_lines")

    for line in lines:
        try:
            if float(line.get("unit_price") or 0) <= 0:
                missing_fields.append("unit_price")
                break
        except (TypeError, ValueError):
            missing_fields.append("unit_price")
            break

    fingerprint = ""
    if not missing_fields:
        fingerprint = _quote_fingerprint(order, lines)

    return {
        "quote_ready": len(missing_fields) == 0,
        "missing_fields": missing_fields,
        "order_id": order_id,
        "fingerprint": fingerprint,
    }


def generate_quote_for_order(order_id, created_by="App"):
    return _generate_quote_for_order(order_id, created_by=created_by)


def _generate_quote_for_order(order_id, created_by="App", quote_fingerprint=""):
    order_id = str(order_id or "").strip()
    created_by = str(created_by or "").strip() or "App"

    detail = _get_quote_order_detail(order_id)
    if not detail:
        raise ValueError("Order not found.")

    order = detail["order"]
    lines = _active_lines(detail["lines"])
    if not lines:
        raise ValueError("Cannot generate quote because the order has no active lines.")

    payment_method = str(order.get("payment_method", "")).strip()
    if payment_method not in ("Cash", "EFT"):
        raise ValueError("Cannot generate quote because Payment_Method must be Cash or EFT.")

    quote_fingerprint = str(quote_fingerprint or "").strip()
    if not quote_fingerprint:
        quote_fingerprint = _quote_fingerprint(order, lines)

    settings = get_document_settings(REQUIRED_QUOTE_SETTINGS)
    quote_valid_days = _to_int(settings["quote_valid_days"], "quote_valid_days")
    vat_rate = _to_float(settings["vat_rate"], "vat_rate")

    line_groups = _group_quote_lines(lines)
    subtotal = sum(group["line_total"] for group in line_groups)
    vat_amount = round(subtotal * vat_rate, 2) if payment_method == "EFT" else 0.0
    total = round(subtotal + vat_amount, 2)

    version = get_next_document_version(order_id, DOCUMENT_TYPE_QUOTE)
    payment_ref = build_payment_ref(order_id)
    document_ref = build_document_ref(order_id, DOCUMENT_TYPE_QUOTE, version)
    generated_at = datetime.now()
    valid_until = generated_at.date() + timedelta(days=quote_valid_days)
    file_name = build_document_file_name(
        DOCUMENT_TYPE_QUOTE,
        generated_at,
        payment_ref,
        version,
        total,
        payment_method,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        pdf_path = Path(temp_dir) / file_name
        _render_quote_pdf(
            pdf_path=pdf_path,
            settings=settings,
            order=order,
            line_groups=line_groups,
            payment_method=payment_method,
            vat_rate=vat_rate,
            subtotal=subtotal,
            vat_amount=vat_amount,
            total=total,
            document_ref=document_ref,
            payment_ref=payment_ref,
            generated_at=generated_at,
            valid_until=valid_until,
        )

        drive_result = upload_file_to_drive(
            pdf_path,
            settings["quote_drive_folder_id"],
            file_name=file_name,
            mime_type="application/pdf",
        )

    document_id = generate_document_id()
    created_at = generated_at.strftime("%d %b %Y %H:%M")
    document_record = {
        "Document_ID": document_id,
        "Order_ID": order_id,
        "Document_Type": DOCUMENT_TYPE_QUOTE,
        "Document_Ref": document_ref,
        "Payment_Ref": payment_ref,
        "Version": version,
        "Document_Status": STATUS_GENERATED,
        "Payment_Method": payment_method,
        "VAT_Rate": vat_rate,
        "Subtotal_Ex_VAT": subtotal,
        "VAT_Amount": vat_amount,
        "Total": total,
        "Valid_Until": valid_until.strftime("%d %b %Y"),
        "Google_Drive_File_ID": drive_result.get("id", ""),
        "Google_Drive_URL": drive_result.get("webViewLink", ""),
        "File_Name": file_name,
        "Created_At": created_at,
        "Created_By": created_by,
        "Notes": _quote_notes(order, settings, quote_fingerprint),
    }
    append_order_document(document_record)

    return {
        "success": True,
        "message": "Quote generated successfully.",
        "order_id": order_id,
        "document_id": document_id,
        "document_type": DOCUMENT_TYPE_QUOTE,
        "document_ref": document_ref,
        "payment_ref": payment_ref,
        "version": version,
        "payment_method": payment_method,
        "file_name": file_name,
        "google_drive_file_id": drive_result.get("id", ""),
        "google_drive_url": drive_result.get("webViewLink", ""),
        "subtotal_ex_vat": subtotal,
        "vat_amount": vat_amount,
        "total": total,
        "valid_until": valid_until.isoformat(),
    }


def _quote_fingerprint(order, lines):
    payload = {
        "order_id": str(order.get("order_id", "")).strip(),
        "order_status": str(order.get("order_status", "")).strip(),
        "customer_name": str(order.get("customer_name", "")).strip(),
        "customer_phone": str(order.get("customer_phone", "")).strip(),
        "payment_method": str(order.get("payment_method", "")).strip(),
        "collection_date": str(order.get("collection_date", "")).strip(),
        "collection_location": str(order.get("collection_location", "")).strip(),
        "lines": [
            {
                "pig_id": str(line.get("pig_id", "")).strip(),
                "sale_category": str(line.get("sale_category", "")).strip(),
                "weight_band": str(line.get("weight_band", "")).strip(),
                "sex": str(line.get("sex", "")).strip(),
                "unit_price": float(line.get("unit_price") or 0),
            }
            for line in sorted(
                lines,
                key=lambda item: (
                    str(item.get("pig_id", "")).strip(),
                    str(item.get("sale_category", "")).strip(),
                    str(item.get("weight_band", "")).strip(),
                    str(item.get("sex", "")).strip(),
                    str(item.get("unit_price", "")).strip(),
                ),
            )
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _to_float_or_zero(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _quote_notes(order, settings, quote_fingerprint):
    notes = _draft_note_if_needed(order, settings)
    quote_fingerprint = str(quote_fingerprint or "").strip()
    if not quote_fingerprint:
        return notes
    fingerprint_note = f"{QUOTE_FINGERPRINT_PREFIX} {quote_fingerprint}"
    if notes:
        return f"{notes} | {fingerprint_note}"
    return fingerprint_note


def _document_has_fingerprint(document, quote_fingerprint):
    quote_fingerprint = str(quote_fingerprint or "").strip()
    if not quote_fingerprint:
        return False
    notes = str(document.get("Notes", "")).strip()
    return f"{QUOTE_FINGERPRINT_PREFIX} {quote_fingerprint}" in notes


def _document_summary(document):
    return {
        "document_id": str(document.get("Document_ID", "")).strip(),
        "document_type": str(document.get("Document_Type", "")).strip(),
        "document_ref": str(document.get("Document_Ref", "")).strip(),
        "document_status": str(document.get("Document_Status", "")).strip(),
        "payment_method": str(document.get("Payment_Method", "")).strip(),
        "total": document.get("Total", ""),
        "valid_until": str(document.get("Valid_Until", "")).strip(),
        "google_drive_url": str(document.get("Google_Drive_URL", "")).strip(),
    }


def _result_document_summary(result):
    return {
        "document_id": result.get("document_id", ""),
        "document_type": result.get("document_type", DOCUMENT_TYPE_QUOTE),
        "document_ref": result.get("document_ref", ""),
        "document_status": STATUS_GENERATED,
        "payment_method": result.get("payment_method", ""),
        "total": result.get("total", ""),
        "valid_until": result.get("valid_until", ""),
        "google_drive_url": result.get("google_drive_url", ""),
    }


def _get_quote_order_detail(order_id):
    order_id = str(order_id or "").strip()
    detail = get_order_detail(order_id)
    master_row = _get_order_master_row(order_id)

    if not master_row:
        return detail

    master_order = _order_from_master_row(master_row)
    lines = detail["lines"] if detail else _get_order_lines_from_sheet(order_id)
    order = dict(detail["order"]) if detail else {}
    order.update(master_order)
    _attach_line_totals(order, lines)

    return {
        "order": order,
        "lines": lines,
    }


def _order_from_master_row(row):
    return {
        "order_id": _clean(row.get("Order_ID", "")),
        "order_date": _clean(row.get("Order_Date", "")),
        "customer_name": _clean(row.get("Customer_Name", "")),
        "customer_phone": _clean(row.get("Customer_Phone", "")),
        "customer_channel": _clean(row.get("Customer_Channel", "")),
        "customer_language": _clean(row.get("Customer_Language", "")),
        "order_source": _clean(row.get("Order_Source", "")),
        "requested_category": _clean(row.get("Requested_Category", "")),
        "requested_weight_range": _clean(row.get("Requested_Weight_Range", "")),
        "requested_sex": _clean(row.get("Requested_Sex", "")),
        "requested_quantity": _to_float_or_zero(row.get("Requested_Quantity", "")),
        "quoted_total": _to_float_or_zero(row.get("Quoted_Total", "")),
        "final_total": _to_float_or_zero(row.get("Final_Total", "")),
        "order_status": _clean(row.get("Order_Status", "")),
        "approval_status": _clean(row.get("Approval_Status", "")),
        "payment_status": _clean(row.get("Payment_Status", "")),
        "collection_date": _clean(row.get("Collection_Date", "")),
        "collection_location": _clean(row.get("Collection_Location", "")),
        "notes": _clean(row.get("Notes", "")),
        "created_by": _clean(row.get("Created_By", "")),
        "created_at": _clean(row.get("Created_At", "")),
        "updated_at": _clean(row.get("Updated_At", "")),
        "payment_method": _clean(row.get("Payment_Method", "")),
        "conversation_id": _clean(row.get("ConversationId", "")),
    }


def _get_order_lines_from_sheet(order_id):
    lines = []
    for row in get_all_records(ORDER_LINES_SHEET):
        if _clean(row.get("Order_ID", "")) != order_id:
            continue
        lines.append({
            "order_line_id": _clean(row.get("Order_Line_ID", "")),
            "order_id": _clean(row.get("Order_ID", "")),
            "pig_id": _clean(row.get("Pig_ID", "")),
            "tag_number": _clean(row.get("Tag_Number", "")),
            "sale_category": _clean(row.get("Sale_Category", "")),
            "weight_band": _clean(row.get("Weight_Band", "")),
            "sex": _clean(row.get("Sex", "")),
            "current_weight_kg": _to_float_or_none(row.get("Current_Weight_Kg", "")),
            "unit_price": _to_float_or_zero(row.get("Unit_Price", "")),
            "line_status": _clean(row.get("Line_Status", "")),
            "reserved_status": _clean(row.get("Reserved_Status", "")),
            "notes": _clean(row.get("Notes", "")),
            "request_item_key": _clean(row.get("Request_Item_Key", "")),
            "created_at": _clean(row.get("Created_At", "")),
            "updated_at": _clean(row.get("Updated_At", "")),
        })
    return lines


def _attach_line_totals(order, lines):
    active_lines = _active_lines(lines)
    order["active_line_count"] = len(active_lines)
    order["cancelled_line_count"] = len(lines) - len(active_lines)
    order["active_line_total"] = sum(float(line.get("unit_price") or 0) for line in active_lines)
    order["all_line_total"] = sum(float(line.get("unit_price") or 0) for line in lines)


def _clean(value):
    return str(value or "").strip()


def _to_float_or_none(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _active_lines(lines):
    return [
        line for line in lines
        if str(line.get("line_status", "")).strip() != "Cancelled"
    ]


def _group_quote_lines(lines):
    grouped = {}

    for line in lines:
        unit_price = line.get("unit_price")
        if unit_price is None or float(unit_price) <= 0:
            raise ValueError(
                "Cannot generate quote because every active order line must have Unit_Price."
            )

        key = (
            str(line.get("sale_category", "")).strip(),
            str(line.get("weight_band", "")).strip(),
            str(line.get("sex", "")).strip(),
            float(unit_price),
        )

        if key not in grouped:
            grouped[key] = {
                "sale_category": key[0],
                "weight_band": key[1],
                "sex": key[2],
                "unit_price": key[3],
                "quantity": 0,
                "line_total": 0.0,
            }

        grouped[key]["quantity"] += 1
        grouped[key]["line_total"] += float(unit_price)

    return sorted(
        grouped.values(),
        key=lambda row: (row["sale_category"], row["weight_band"], row["sex"], row["unit_price"]),
    )


def _render_quote_pdf(
    pdf_path,
    settings,
    order,
    line_groups,
    payment_method,
    vat_rate,
    subtotal,
    vat_amount,
    total,
    document_ref,
    payment_ref,
    generated_at,
    valid_until,
):
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    small = ParagraphStyle("Small", parent=normal, fontSize=8, leading=10)
    heading = ParagraphStyle("Heading", parent=normal, fontSize=18, leading=22, spaceAfter=6)
    bold = ParagraphStyle("Bold", parent=normal, fontName="Helvetica-Bold")

    story = []
    logo_path_value = str(settings["document_logo_path"] or "").strip()
    logo_path = Path(logo_path_value) if logo_path_value else None
    header_left = []
    if logo_path and logo_path.exists() and logo_path.is_file():
        header_left.append(Image(str(logo_path), width=36 * mm, height=24 * mm, kind="proportional"))
    header_left.extend([
        Paragraph(f"<b>{settings['business_name']}</b>", normal),
        Paragraph(settings["business_address_line_1"], small),
        Paragraph(settings["business_address_line_2"], small),
        Paragraph(settings["business_address_line_3"], small),
        Paragraph(settings["business_phone"], small),
        Paragraph(settings["business_email"], small),
        Paragraph(f"VAT: {settings['business_vat_number']}", small),
    ])

    header_right = [
        Paragraph("<b>QUOTE</b>", heading),
        Paragraph(f"<b>QUOTE REF:</b> {document_ref}", normal),
        Paragraph(f"<b>DATE:</b> {generated_at.strftime('%d %b %Y')}", normal),
    ]
    header_table = Table([[header_left, header_right]], colWidths=[115 * mm, 55 * mm])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 8 * mm))

    details_table = Table([
        [
            Paragraph("<b>BILL TO</b>", bold),
            Paragraph("<b>DETAILS</b>", bold),
        ],
        [
            _bill_to_block(order, normal),
            _details_block(order, payment_method, valid_until, normal),
        ],
    ], colWidths=[90 * mm, 80 * mm])
    details_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
        ("BOX", (0, 0), (-1, -1), 0.25, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 8 * mm))

    if str(order.get("order_status", "")).strip() == "Draft":
        story.append(Paragraph(f"<b>{settings['draft_quote_note']}</b>", normal))
        story.append(Spacer(1, 4 * mm))

    line_rows = [[Paragraph("<b>DESCRIPTION</b>", normal), Paragraph("<b>AMOUNT</b>", normal)]]
    for group in line_groups:
        line_rows.append([
            Paragraph(_line_description(group), normal),
            Paragraph(_format_currency(group["line_total"]), normal),
        ])

    lines_table = Table(line_rows, colWidths=[135 * mm, 35 * mm])
    lines_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
        ("BOX", (0, 0), (-1, -1), 0.25, colors.grey),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(lines_table)
    story.append(Spacer(1, 6 * mm))

    totals_rows = [
        ["Sub-Total:", _format_currency(subtotal)],
        [f"VAT ({int(vat_rate * 100)}%)", _format_currency(vat_amount)],
        ["TOTAL", _format_currency(total)],
    ]
    totals_table = Table(totals_rows, colWidths=[135 * mm, 35 * mm])
    totals_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 8 * mm))

    footer_table = Table([
        [
            _bank_details_block(settings, payment_ref, normal),
            _notes_block(order, normal),
        ],
    ], colWidths=[85 * mm, 85 * mm])
    footer_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.white),
    ]))
    story.append(footer_table)
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Thank you for your business!", normal))

    doc.build(story)


def _bill_to_block(order, style):
    rows = [
        f"Name: {order.get('customer_name', '')}",
        "Company Name:",
        "Street Address:",
        "City, Zip:",
        f"Phone: {order.get('customer_phone', '')}",
        "Email:",
        "VAT:",
    ]
    return Paragraph("<br/>".join(rows), style)


def _details_block(order, payment_method, valid_until, style):
    rows = [
        f"Order: {order.get('order_id', '')}",
        f"Date Created: {_display_date(order.get('created_at', ''))}",
        f"Payment Method: {payment_method}",
        f"Valid Until: {valid_until.strftime('%d %b %Y')}",
    ]
    return Paragraph("<br/>".join(rows), style)


def _bank_details_block(settings, payment_ref, style):
    rows = [
        "<b>BANK DETAILS</b>",
        settings["bank_name"],
        settings["bank_account_name"],
        settings["bank_account_type"],
        settings["bank_account_number"],
        settings["bank_branch_code"],
        f"Use Reference: {payment_ref}",
    ]
    return Paragraph("<br/>".join(rows), style)


def _notes_block(order, style):
    rows = [
        "<b>NOTES</b>",
        "Delivery will take place at the below agreed locations and date",
        f"Location: {order.get('collection_location', '')}",
        f"Date: {_display_date(order.get('collection_date', '')) or 'TBC'}",
        "Time: TBC",
    ]
    return Paragraph("<br/>".join(rows), style)


def _line_description(group):
    quantity = int(group["quantity"])
    category = group["sale_category"]
    weight_band = _display_weight_band(group["weight_band"])
    unit_price = _format_currency(group["unit_price"])
    sex = group["sex"] or "Any"
    return f"{quantity}x {category} ({weight_band}) @ {unit_price} each ({sex})"


def _display_weight_band(weight_band):
    return str(weight_band or "").replace("_to_", "-").replace("_", " ")


def _format_currency(value):
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    return f"R{amount:,.2f}"


def _display_date(value):
    text = str(value or "").strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%d %b %Y")
        except ValueError:
            continue
    return text


def _draft_note_if_needed(order, settings):
    if str(order.get("order_status", "")).strip() == "Draft":
        return settings.get("draft_quote_note", "")
    return ""


def _to_int(value, setting_name):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Document setting '{setting_name}' must be a whole number.")


def _to_float(value, setting_name):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Document setting '{setting_name}' must be a number.")
