import json
import tempfile
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.documents.document_service import (
    DOCUMENT_TYPE_HEALTH_DECLARATION,
    DOCUMENT_TYPE_REMOVAL_CERTIFICATE,
    STATUS_GENERATED,
    append_order_document,
    build_document_file_name,
    build_document_ref,
    build_payment_ref,
    generate_document_id,
    get_document_settings,
    get_next_document_version,
)
from modules.documents.loading_sheet_service import (
    _active_lines,
    _enrich_lines_with_pen_context,
    _group_lines_by_pen,
    _line_type,
    _safe,
    _weight_text,
    _xml,
)
from modules.orders.order_service import get_order_detail
from services.google_drive_service import upload_file_to_drive


REQUIRED_MOVEMENT_DOC_SETTINGS = [
    "business_name",
    "business_address_line_1",
    "business_address_line_2",
    "business_address_line_3",
    "business_phone",
    "business_email",
    "document_logo_path",
]


def generate_removal_certificate_for_order(order_id, form_data=None, created_by="App"):
    return _generate_movement_document(
        order_id,
        document_type=DOCUMENT_TYPE_REMOVAL_CERTIFICATE,
        form_data=form_data or {},
        created_by=created_by,
    )


def generate_health_declaration_for_order(order_id, form_data=None, created_by="App"):
    return _generate_movement_document(
        order_id,
        document_type=DOCUMENT_TYPE_HEALTH_DECLARATION,
        form_data=form_data or {},
        created_by=created_by,
    )


def _generate_movement_document(order_id, document_type, form_data=None, created_by="App"):
    order_id = _safe(order_id)
    created_by = _safe(created_by) or "App"
    form_data = _clean_form_data(form_data or {})
    detail = get_order_detail(order_id)
    if not detail:
        raise ValueError("Order not found.")

    order = detail["order"]
    lines = _active_lines(detail.get("lines") or [])
    if not lines:
        raise ValueError(f"Cannot generate {document_type.lower()} because the order has no active lines.")

    settings = get_document_settings(REQUIRED_MOVEMENT_DOC_SETTINGS)
    folder_id = (
        _safe(settings.get("movement_documents_drive_folder_id"))
        or _safe(settings.get("loading_sheet_drive_folder_id"))
        or _safe(settings.get("quote_drive_folder_id"))
    )
    if not folder_id:
        raise ValueError("Missing required document setting(s): movement_documents_drive_folder_id or loading_sheet_drive_folder_id or quote_drive_folder_id")

    generated_at = datetime.now()
    version = get_next_document_version(order_id, document_type)
    document_ref = build_document_ref(order_id, document_type, version)
    payment_ref = build_payment_ref(order_id)
    file_name = build_document_file_name(document_type, generated_at, payment_ref, version, total=0, payment_method="")
    enriched_lines = _enrich_lines_with_pen_context(lines)
    pen_groups = _group_lines_by_pen(enriched_lines)

    with tempfile.TemporaryDirectory(prefix="amadeus-movement-document-") as temp_dir:
        pdf_path = Path(temp_dir) / file_name
        if document_type == DOCUMENT_TYPE_REMOVAL_CERTIFICATE:
            _render_removal_certificate_pdf(pdf_path, settings, order, enriched_lines, pen_groups, document_ref, generated_at, form_data)
        else:
            _render_health_declaration_pdf(pdf_path, settings, order, enriched_lines, pen_groups, document_ref, generated_at, form_data)
        drive_result = upload_file_to_drive(pdf_path, folder_id, file_name=file_name, mime_type="application/pdf")

    document_id = generate_document_id()
    document_record = {
        "Document_ID": document_id,
        "Order_ID": order_id,
        "Document_Type": document_type,
        "Document_Ref": document_ref,
        "Payment_Ref": payment_ref,
        "Version": version,
        "Document_Status": STATUS_GENERATED,
        "Payment_Method": "",
        "VAT_Rate": "",
        "Subtotal_Ex_VAT": "",
        "VAT_Amount": "",
        "Total": "",
        "Valid_Until": "",
        "Google_Drive_File_ID": drive_result.get("id", ""),
        "Google_Drive_URL": drive_result.get("webViewLink", ""),
        "File_Name": file_name,
        "Created_At": generated_at.strftime("%d %b %Y %H:%M"),
        "Created_By": created_by,
        "Notes": _movement_document_notes(document_type, order, enriched_lines, pen_groups, form_data),
    }
    append_order_document(document_record)
    return {
        "success": True,
        "message": f"{document_type} generated successfully.",
        "order_id": order_id,
        "document_id": document_id,
        "document_type": document_type,
        "document_ref": document_ref,
        "version": version,
        "file_name": file_name,
        "google_drive_file_id": drive_result.get("id", ""),
        "google_drive_url": drive_result.get("webViewLink", ""),
        "pig_count": len(enriched_lines),
        "pen_count": len(pen_groups),
    }


def _render_removal_certificate_pdf(pdf_path, settings, order, lines, pen_groups, document_ref, generated_at, form_data):
    story, styles = _base_story(pdf_path, settings, "REMOVAL CERTIFICATE", document_ref, generated_at)
    normal = styles["Normal"]
    small = styles["Small"]
    subheading = styles["Subheading"]
    story.append(_order_summary_table(order, lines, form_data))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("<b>Transport / Movement Details</b>", subheading))
    story.append(_two_column_table([
        ("Removal date", form_data.get("movement_date") or _safe(order.get("collection_date")) or generated_at.strftime("%Y-%m-%d")),
        ("Removal time", form_data.get("movement_time")),
        ("Driver", form_data.get("driver_name")),
        ("Driver ID / phone", form_data.get("driver_id") or form_data.get("driver_phone")),
        ("Vehicle registration", form_data.get("vehicle_registration")),
        ("Trailer registration", form_data.get("trailer_registration")),
        ("From", _farm_address(settings)),
        ("Destination", form_data.get("destination_address") or _safe(order.get("collection_location"))),
    ]))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("<b>Animals Removed</b>", subheading))
    story.append(_animal_table(lines))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(
        "I certify that the animals listed above are removed from Amadeus Farm under this order reference. "
        "This certificate identifies the animals for loading and transport record purposes.",
        normal,
    ))
    story.append(Spacer(1, 8 * mm))
    story.append(_signature_table(form_data))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("No prices, payment information, or private customer notes are shown on this certificate.", small))
    _build_doc(pdf_path, story)


def _render_health_declaration_pdf(pdf_path, settings, order, lines, pen_groups, document_ref, generated_at, form_data):
    story, styles = _base_story(pdf_path, settings, "HEALTH DECLARATION", document_ref, generated_at)
    normal = styles["Normal"]
    small = styles["Small"]
    subheading = styles["Subheading"]
    story.append(_order_summary_table(order, lines, form_data))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("<b>Declaration</b>", subheading))
    declarations = [
        "The animals listed in this document were visually checked at loading.",
        "At the time of loading, no obvious signs of illness or injury were observed unless noted below.",
        "The animals are declared fit for normal farm transport based on visual inspection.",
        "Final handling, loading, and transport remain the responsibility of the persons loading and transporting the animals.",
    ]
    for item in declarations:
        story.append(Paragraph(f"[  ] {_xml(item)}", normal))
    notes = form_data.get("health_notes") or "No additional health notes recorded at document generation."
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"<b>Health notes:</b> {_xml(notes)}", normal))
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("<b>Animals Covered By This Declaration</b>", subheading))
    story.append(_animal_table(lines))
    story.append(Spacer(1, 8 * mm))
    story.append(_signature_table(form_data))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("No prices, payment information, or private customer notes are shown on this declaration.", small))
    _build_doc(pdf_path, story)


def _base_story(pdf_path, settings, title, document_ref, generated_at):
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, leading=10))
    styles.add(ParagraphStyle("Subheading", parent=styles["Normal"], fontSize=11, leading=13, fontName="Helvetica-Bold"))
    heading = ParagraphStyle("DocHeading", parent=styles["Normal"], fontSize=17, leading=20, fontName="Helvetica-Bold")
    story = []
    logo_path = Path(_safe(settings.get("document_logo_path")))
    header_left = []
    if logo_path.exists() and logo_path.is_file():
        header_left.append(Image(str(logo_path), width=34 * mm, height=22 * mm, kind="proportional"))
    header_left.extend([
        Paragraph(f"<b>{_xml(settings.get('business_name'))}</b>", styles["Normal"]),
        Paragraph(_xml(settings.get("business_address_line_1")), styles["Small"]),
        Paragraph(_xml(settings.get("business_address_line_2")), styles["Small"]),
        Paragraph(_xml(settings.get("business_address_line_3")), styles["Small"]),
        Paragraph(_xml(settings.get("business_phone")), styles["Small"]),
        Paragraph(_xml(settings.get("business_email")), styles["Small"]),
    ])
    header_right = [
        Paragraph(f"<b>{_xml(title)}</b>", heading),
        Paragraph("<b>NO PRICES - MOVEMENT COPY</b>", styles["Subheading"]),
        Paragraph(f"<b>Ref:</b> {_xml(document_ref)}", styles["Normal"]),
        Paragraph(f"<b>Generated:</b> {generated_at.strftime('%d %b %Y %H:%M')}", styles["Small"]),
    ]
    table = Table([[header_left, header_right]], colWidths=[112 * mm, 76 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(table)
    story.append(Spacer(1, 5 * mm))
    return story, styles


def _order_summary_table(order, lines, form_data):
    rows = [
        ["Order", _safe(order.get("order_id")), "Customer", _safe(order.get("customer_name"))],
        ["Pigs", str(len(lines)), "Collection", _safe(order.get("collection_date")) or form_data.get("movement_date") or "Not set"],
        ["Request", _request_summary(order), "Destination", form_data.get("destination_address") or _safe(order.get("collection_location")) or "Not set"],
    ]
    table = Table(rows, colWidths=[24 * mm, 69 * mm, 25 * mm, 70 * mm])
    table.setStyle(_simple_grid_style())
    return table


def _two_column_table(items):
    rows = []
    for index in range(0, len(items), 2):
        left = items[index]
        right = items[index + 1] if index + 1 < len(items) else ("", "")
        rows.append([left[0], left[1] or "________________", right[0], right[1] or "________________"])
    table = Table(rows, colWidths=[32 * mm, 62 * mm, 34 * mm, 60 * mm])
    table.setStyle(_simple_grid_style())
    return table


def _animal_table(lines):
    data = [["Tag", "Pig ID", "Sex", "Type", "Latest kg", "Pen"]]
    for line in lines:
        data.append([
            _safe(line.get("tag_number")) or "-",
            _safe(line.get("pig_id")) or "-",
            _safe(line.get("sex")) or "-",
            _line_type(line),
            _weight_text(line.get("current_weight_kg")),
            _safe(line.get("current_pen_name")) or _safe(line.get("current_pen_id")) or "-",
        ])
    table = Table(data, colWidths=[22 * mm, 34 * mm, 20 * mm, 42 * mm, 22 * mm, 48 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222222")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#999999")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7f7")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _signature_table(form_data):
    responsible = form_data.get("responsible_person") or "Charl Nieuwendyk"
    return Table([
        ["Responsible person", responsible, "Signature", "____________________"],
        ["Date", form_data.get("signature_date") or datetime.now().strftime("%Y-%m-%d"), "Place", form_data.get("signature_place") or "Amadeus Farm"],
    ], colWidths=[34 * mm, 60 * mm, 26 * mm, 68 * mm], style=_simple_grid_style())


def _simple_grid_style():
    return TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.35, colors.HexColor("#777777")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eeeeee")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#eeeeee")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])


def _build_doc(pdf_path, story):
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )
    doc.build(story)


def _clean_form_data(form_data):
    allowed = {
        "movement_date", "movement_time", "driver_name", "driver_id", "driver_phone",
        "vehicle_registration", "trailer_registration", "destination_address",
        "responsible_person", "signature_date", "signature_place", "health_notes",
    }
    return {key: _safe(value)[:300] for key, value in dict(form_data or {}).items() if key in allowed}


def _movement_document_notes(document_type, order, lines, pen_groups, form_data):
    return f"{document_type}_Metadata: " + json.dumps({
        "worker_safe": True,
        "contains_prices": False,
        "contains_payment_details": False,
        "pig_count": len(lines),
        "pen_count": len(pen_groups),
        "form_fields": sorted([key for key, value in form_data.items() if value]),
    }, sort_keys=True, separators=(",", ":"))


def _request_summary(order):
    parts = [
        _safe(order.get("requested_quantity")),
        _safe(order.get("requested_sex")),
        _safe(order.get("requested_category")),
        _safe(order.get("requested_weight_range")).replace("_", " "),
    ]
    return " ".join([part for part in parts if part]) or "-"


def _farm_address(settings):
    return ", ".join([
        _safe(settings.get("business_name")),
        _safe(settings.get("business_address_line_1")),
        _safe(settings.get("business_address_line_2")),
        _safe(settings.get("business_address_line_3")),
    ]).strip(", ")
