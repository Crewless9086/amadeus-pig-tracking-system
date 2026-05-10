from datetime import datetime
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
    DOCUMENT_TYPE_INVOICE,
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
from modules.documents.quote_service import _active_lines, _format_currency, _group_quote_lines
from modules.orders.order_service import get_order_detail
from services.google_drive_service import upload_file_to_drive


REQUIRED_INVOICE_SETTINGS = [
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
    "invoice_drive_folder_id",
    "document_logo_path",
]


def generate_invoice_for_order(order_id, created_by="App"):
    order_id = str(order_id or "").strip()
    created_by = str(created_by or "").strip() or "App"

    detail = get_order_detail(order_id)
    if not detail:
        raise ValueError("Order not found.")

    order = detail["order"]
    order_status = str(order.get("order_status", "")).strip()
    if order_status not in ("Approved", "Completed"):
        raise ValueError("Invoice can only be generated for Approved or Completed orders.")

    quote = get_latest_non_voided_quote(order_id)
    if not quote:
        raise ValueError("Invoice requires an existing non-voided quote.")

    lines = _active_lines(detail["lines"])
    if not lines:
        raise ValueError("Cannot generate invoice because the order has no active lines.")

    settings = get_document_settings(REQUIRED_INVOICE_SETTINGS)
    payment_method = str(quote.get("Payment_Method", "")).strip()
    if payment_method not in ("Cash", "EFT"):
        raise ValueError("Latest quote has invalid Payment_Method.")

    vat_rate = _to_float(quote.get("VAT_Rate", ""), "VAT_Rate")
    subtotal = _to_float(quote.get("Subtotal_Ex_VAT", ""), "Subtotal_Ex_VAT")
    vat_amount = _to_float(quote.get("VAT_Amount", ""), "VAT_Amount")
    total = _to_float(quote.get("Total", ""), "Total")

    line_groups = _group_quote_lines(lines)
    payment_ref = build_payment_ref(order_id)
    version = get_next_document_version(order_id, DOCUMENT_TYPE_INVOICE)
    document_ref = build_document_ref(order_id, DOCUMENT_TYPE_INVOICE, version)
    generated_at = datetime.now()
    file_name = build_document_file_name(
        DOCUMENT_TYPE_INVOICE,
        generated_at,
        payment_ref,
        version,
        total,
        payment_method,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        pdf_path = Path(temp_dir) / file_name
        _render_invoice_pdf(
            pdf_path=pdf_path,
            settings=settings,
            order=order,
            quote=quote,
            line_groups=line_groups,
            payment_method=payment_method,
            vat_rate=vat_rate,
            subtotal=subtotal,
            vat_amount=vat_amount,
            total=total,
            document_ref=document_ref,
            payment_ref=payment_ref,
            generated_at=generated_at,
        )

        drive_result = upload_file_to_drive(
            pdf_path,
            settings["invoice_drive_folder_id"],
            file_name=file_name,
            mime_type="application/pdf",
        )

    document_id = generate_document_id()
    created_at = generated_at.strftime("%d %b %Y %H:%M")
    document_record = {
        "Document_ID": document_id,
        "Order_ID": order_id,
        "Document_Type": DOCUMENT_TYPE_INVOICE,
        "Document_Ref": document_ref,
        "Payment_Ref": payment_ref,
        "Version": version,
        "Document_Status": STATUS_GENERATED,
        "Payment_Method": payment_method,
        "VAT_Rate": vat_rate,
        "Subtotal_Ex_VAT": subtotal,
        "VAT_Amount": vat_amount,
        "Total": total,
        "Google_Drive_File_ID": drive_result.get("id", ""),
        "Google_Drive_URL": drive_result.get("webViewLink", ""),
        "File_Name": file_name,
        "Created_At": created_at,
        "Created_By": created_by,
        "Notes": f"Generated from quote {quote.get('Document_Ref', '')}",
    }
    append_order_document(document_record)

    return {
        "success": True,
        "message": "Invoice generated successfully.",
        "order_id": order_id,
        "document_id": document_id,
        "document_type": DOCUMENT_TYPE_INVOICE,
        "document_ref": document_ref,
        "payment_ref": payment_ref,
        "version": version,
        "source_quote_document_id": quote.get("Document_ID", ""),
        "source_quote_ref": quote.get("Document_Ref", ""),
        "file_name": file_name,
        "google_drive_file_id": drive_result.get("id", ""),
        "google_drive_url": drive_result.get("webViewLink", ""),
        "subtotal_ex_vat": subtotal,
        "vat_amount": vat_amount,
        "total": total,
    }


def _render_invoice_pdf(
    pdf_path,
    settings,
    order,
    quote,
    line_groups,
    payment_method,
    vat_rate,
    subtotal,
    vat_amount,
    total,
    document_ref,
    payment_ref,
    generated_at,
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
    logo_path = Path(settings["document_logo_path"])
    header_left = []
    if logo_path.exists():
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
        Paragraph("<b>INVOICE</b>", heading),
        Paragraph(f"<b>INVOICE REF:</b> {document_ref}", normal),
        Paragraph(f"<b>DATE:</b> {generated_at.strftime('%d %b %Y')}", normal),
        Paragraph(f"<b>QUOTE REF:</b> {quote.get('Document_Ref', '')}", normal),
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
            _details_block(order, payment_method, quote, normal),
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

    totals_table = Table([
        ["Sub-Total:", _format_currency(subtotal)],
        [f"VAT ({int(vat_rate * 100)}%)", _format_currency(vat_amount)],
        ["TOTAL", _format_currency(total)],
    ], colWidths=[135 * mm, 35 * mm])
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


def _details_block(order, payment_method, quote, style):
    rows = [
        f"Order: {order.get('order_id', '')}",
        f"Date Created: {_display_date(order.get('created_at', ''))}",
        f"Payment Method: {payment_method}",
        f"Quote Used: {quote.get('Document_Ref', '')}",
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
    weight_band = str(group["weight_band"] or "").replace("_to_", "-").replace("_", " ")
    unit_price = _format_currency(group["unit_price"])
    sex = group["sex"] or "Any"
    return f"{quantity}x {category} ({weight_band}) @ {unit_price} each ({sex})"


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


def _to_float(value, field_name):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Quote field '{field_name}' must be a number.")
