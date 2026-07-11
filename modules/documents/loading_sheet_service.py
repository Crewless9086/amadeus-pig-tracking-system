import json
import mimetypes
import os
import tempfile
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.documents.document_service import (
    DOCUMENT_TYPE_HEALTH_DECLARATION,
    DOCUMENT_TYPE_LOADING_SHEET,
    DOCUMENT_TYPE_REMOVAL_CERTIFICATE,
    STATUS_GENERATED,
    append_order_document,
    build_document_file_name,
    build_document_ref,
    build_payment_ref,
    generate_document_id,
    get_document_settings,
    get_next_document_version,
    get_order_document,
)
from modules.documents import document_service
from modules.orders.order_service import get_order_detail
from services.database_service import DATABASE_URL_ENV
from services.google_drive_service import download_drive_file, upload_file_to_drive


REQUIRED_LOADING_SHEET_SETTINGS = [
    "business_name",
    "business_address_line_1",
    "business_address_line_2",
    "business_address_line_3",
    "business_phone",
    "document_logo_path",
]


def generate_loading_sheet_for_order(order_id, created_by="App", revision_fingerprint=""):
    order_id = str(order_id or "").strip()
    created_by = str(created_by or "").strip() or "App"
    detail = get_order_detail(order_id)
    if not detail:
        raise ValueError("Order not found.")

    order = detail["order"]
    lines = _active_lines(detail.get("lines") or [])
    if not lines:
        raise ValueError("Cannot generate loading sheet because the order has no active lines.")

    settings = get_document_settings(REQUIRED_LOADING_SHEET_SETTINGS)
    folder_id = (
        str(settings.get("loading_sheet_drive_folder_id") or "").strip()
        or str(settings.get("quote_drive_folder_id") or "").strip()
    )
    if not folder_id:
        raise ValueError("Missing required document setting(s): loading_sheet_drive_folder_id or quote_drive_folder_id")

    generated_at = datetime.now()
    version = get_next_document_version(order_id, DOCUMENT_TYPE_LOADING_SHEET)
    document_ref = build_document_ref(order_id, DOCUMENT_TYPE_LOADING_SHEET, version)
    payment_ref = build_payment_ref(order_id)
    file_name = build_document_file_name(
        DOCUMENT_TYPE_LOADING_SHEET,
        generated_at,
        payment_ref,
        version,
        total=0,
        payment_method="",
    )

    enriched_lines = _enrich_lines_with_pen_context(lines)
    pen_groups = _group_lines_by_pen(enriched_lines)

    with tempfile.TemporaryDirectory(prefix="amadeus-loading-sheet-") as temp_dir:
        pdf_path = Path(temp_dir) / file_name
        _render_loading_sheet_pdf(
            pdf_path=pdf_path,
            settings=settings,
            order=order,
            lines=enriched_lines,
            pen_groups=pen_groups,
            document_ref=document_ref,
            generated_at=generated_at,
        )
        drive_result = upload_file_to_drive(
            pdf_path,
            folder_id,
            file_name=file_name,
            mime_type="application/pdf",
        )

    document_id = generate_document_id()
    created_at = generated_at.strftime("%d %b %Y %H:%M")
    document_record = {
        "Document_ID": document_id,
        "Order_ID": order_id,
        "Document_Type": DOCUMENT_TYPE_LOADING_SHEET,
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
        "Created_At": created_at,
        "Created_By": created_by,
        "Notes": _loading_sheet_notes(order, enriched_lines, pen_groups, revision_fingerprint=revision_fingerprint),
    }
    append_order_document(document_record)

    return {
        "success": True,
        "message": "Loading sheet generated successfully.",
        "order_id": order_id,
        "document_id": document_id,
        "document_type": DOCUMENT_TYPE_LOADING_SHEET,
        "document_ref": document_ref,
        "version": version,
        "file_name": file_name,
        "google_drive_file_id": drive_result.get("id", ""),
        "google_drive_url": drive_result.get("webViewLink", ""),
        "pig_count": len(enriched_lines),
        "pen_count": len(pen_groups),
        "pen_summary": [
            {"pen": group["pen_label"], "count": len(group["lines"])}
            for group in pen_groups
        ],
    }


def send_loading_sheet_to_owner_telegram(document_id, sent_by="App", chat_id=""):
    document = get_order_document(document_id)
    if not document:
        raise ValueError("Document not found.")
    if str(document.get("Document_Type", "")).strip() not in OWNER_TELEGRAM_DOCUMENT_TYPES:
        raise ValueError("Only loading sheet and movement documents can be sent with this action.")

    chat_ids = [str(chat_id or "").strip()] if str(chat_id or "").strip() else _owner_telegram_chat_ids()
    chat_ids = [item for item in chat_ids if item]
    if not chat_ids:
        return {
            "success": False,
            "status": "telegram_owner_chat_id_required",
            "document_id": document_id,
            "message": "No owner Telegram chat ID is configured.",
        }

    deliveries = []
    ok = True
    for target in chat_ids:
        result = _send_loading_sheet_document(target, document, sent_by=sent_by)
        deliveries.append(result)
        ok = ok and result.get("success") is True
    return {
        "success": ok,
        "status": "telegram_owner_document_sent" if ok else "telegram_owner_document_partial_or_failed",
        "document_id": document_id,
        "order_id": str(document.get("Order_ID", "")).strip(),
        "document_ref": str(document.get("Document_Ref", "")).strip(),
        "deliveries": deliveries,
    }


def loading_sheet_summary(document):
    return {
        "document_id": str(document.get("Document_ID", "")).strip(),
        "order_id": str(document.get("Order_ID", "")).strip(),
        "document_ref": str(document.get("Document_Ref", "")).strip(),
        "file_name": str(document.get("File_Name", "")).strip(),
        "google_drive_url": str(document.get("Google_Drive_URL", "")).strip(),
    }


OWNER_TELEGRAM_DOCUMENT_TYPES = {
    DOCUMENT_TYPE_LOADING_SHEET,
    DOCUMENT_TYPE_REMOVAL_CERTIFICATE,
    DOCUMENT_TYPE_HEALTH_DECLARATION,
}


def _render_loading_sheet_pdf(pdf_path, settings, order, lines, pen_groups, document_ref, generated_at):
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    small = ParagraphStyle("Small", parent=normal, fontSize=8, leading=10)
    tiny = ParagraphStyle("Tiny", parent=normal, fontSize=7, leading=8)
    heading = ParagraphStyle("Heading", parent=normal, fontSize=17, leading=20, spaceAfter=4)
    subheading = ParagraphStyle("Subheading", parent=normal, fontSize=11, leading=13, fontName="Helvetica-Bold")

    story = []
    logo_path = Path(str(settings.get("document_logo_path") or "").strip())
    header_left = []
    if logo_path.exists() and logo_path.is_file():
        header_left.append(Image(str(logo_path), width=34 * mm, height=22 * mm, kind="proportional"))
    header_left.extend([
        Paragraph(f"<b>{_xml(settings.get('business_name'))}</b>", normal),
        Paragraph(_xml(settings.get("business_address_line_1")), small),
        Paragraph(_xml(settings.get("business_address_line_2")), small),
        Paragraph(_xml(settings.get("business_address_line_3")), small),
        Paragraph(_xml(settings.get("business_phone")), small),
    ])
    header_right = [
        Paragraph("<b>LOADING SHEET</b>", heading),
        Paragraph("<b>NO PRICES - WORKER COPY</b>", subheading),
        Paragraph(f"<b>Ref:</b> {_xml(document_ref)}", normal),
        Paragraph(f"<b>Generated:</b> {generated_at.strftime('%d %b %Y %H:%M')}", small),
    ]
    header = Table([[header_left, header_right]], colWidths=[112 * mm, 76 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(header)
    story.append(Spacer(1, 5 * mm))

    summary_rows = [
        ["Order", _safe(order.get("order_id")), "Customer", _safe(order.get("customer_name"))],
        ["Collection", _safe(order.get("collection_date")) or "Not set", "Location", _safe(order.get("collection_location")) or "Not set"],
        ["Request", _request_summary(order), "Pigs to load", str(len(lines))],
    ]
    summary = Table(summary_rows, colWidths=[24 * mm, 69 * mm, 25 * mm, 70 * mm])
    summary.setStyle(TableStyle([
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
    ]))
    story.append(summary)
    story.append(Spacer(1, 5 * mm))

    for group in pen_groups:
        story.append(Paragraph(f"<b>Pen: {_xml(group['pen_label'])} ({len(group['lines'])})</b>", subheading))
        table_data = [["Loaded", "Tag / Pig", "Sex", "Type", "Latest kg", "Final kg", "Notes"]]
        for line in group["lines"]:
            table_data.append([
                "[  ]",
                Paragraph(f"<b>{_xml(line.get('tag_number') or '-')}</b><br/><font size='7'>{_xml(line.get('pig_id') or '')}</font>", tiny),
                _safe(line.get("sex")) or "-",
                Paragraph(_xml(_line_type(line)), tiny),
                _weight_text(line.get("current_weight_kg")),
                "________",
                "____________",
            ])
        table = Table(table_data, colWidths=[13 * mm, 34 * mm, 18 * mm, 36 * mm, 19 * mm, 24 * mm, 44 * mm], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222222")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#999999")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 1), (0, -1), "CENTER"),
            ("ALIGN", (4, 1), (5, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7f7")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(table)
        story.append(Spacer(1, 4 * mm))

    signoff = Table([
        ["Loaded by", "____________________", "Checked by", "____________________"],
        ["Date/time", "____________________", "Total loaded", f"____ / {len(lines)}"],
        ["Problems / substitutions", "____________________________________________________________", "", ""],
    ], colWidths=[34 * mm, 60 * mm, 34 * mm, 60 * mm])
    signoff.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.35, colors.HexColor("#777777")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("SPAN", (1, 2), (-1, 2)),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(signoff)
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Worker copy: no prices, payment details, or private customer notes are shown on this sheet.", small))
    doc.build(story)


def _send_loading_sheet_document(chat_id, document, sent_by="App"):
    token = str(os.getenv("OOM_SAKKIE_TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        return {"success": False, "status": "telegram_bot_token_not_configured", "chat_id_set": bool(chat_id)}

    drive_file_id = str(document.get("Google_Drive_File_ID", "")).strip()
    if not drive_file_id:
        return {"success": False, "status": "drive_file_id_required", "chat_id_set": bool(chat_id)}

    order_id = str(document.get("Order_ID", "")).strip()
    document_type = str(document.get("Document_Type", "")).strip() or "Document"
    document_ref = str(document.get("Document_Ref", "")).strip()
    file_name = str(document.get("File_Name", "")).strip() or f"{document_ref or order_id or 'loading-sheet'}.pdf"
    caption = (
        f"{document_type} PDF\n"
        f"Order: {order_id}\n"
        f"Ref: {document_ref}\n"
        f"Owner/farm paperwork copy. No prices are shown. Check details before printing or sharing."
    )
    try:
        with tempfile.TemporaryDirectory(prefix="amadeus-loading-telegram-") as temp_dir:
            pdf_path = Path(temp_dir) / _safe_filename(file_name)
            download_drive_file(drive_file_id, pdf_path)
            boundary = "----AmadeusLoadingSheet" + uuid.uuid4().hex[:16]
            request = urllib_request.Request(
                f"https://api.telegram.org/bot{token}/sendDocument",
                data=_multipart_body(
                    boundary,
                    {"chat_id": chat_id, "caption": caption[:1024]},
                    "document",
                    pdf_path.name,
                    mimetypes.guess_type(pdf_path.name)[0] or "application/pdf",
                    pdf_path.read_bytes(),
                ),
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            with urllib_request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8", errors="replace")
                status_code = getattr(response, "status", 200)
    except urllib_error.HTTPError as exc:
        return {"success": False, "status": "telegram_api_rejected", "telegram_status_code": exc.code, "error": str(exc.reason), "chat_id_set": bool(chat_id)}
    except urllib_error.URLError as exc:
        return {"success": False, "status": "telegram_api_unreachable", "error": str(exc.reason), "chat_id_set": bool(chat_id)}
    except Exception as exc:
        return {"success": False, "status": "telegram_loading_sheet_send_failed", "error": str(exc), "chat_id_set": bool(chat_id)}

    parsed = _parse_json(body)
    return {
        "success": 200 <= status_code < 300 and parsed.get("ok") is True,
        "status": "telegram_document_sent" if parsed.get("ok") is True else "telegram_document_not_confirmed",
        "telegram_status_code": status_code,
        "telegram_message_id": ((parsed.get("result") or {}).get("message_id")),
        "chat_id_set": bool(chat_id),
        "sent_by": str(sent_by or "").strip() or "App",
    }


def _owner_telegram_chat_ids():
    explicit = os.getenv("LOADING_SHEET_TELEGRAM_CHAT_ID", "").strip()
    if explicit:
        return [item.strip() for item in explicit.split(",") if item.strip()]
    raw = (
        os.getenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "").strip()
        or os.getenv("CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS", "").strip()
    )
    ids = [item.strip() for item in raw.split(",") if item.strip()]
    return ids[:1]


def _enrich_lines_with_pen_context(lines):
    pig_ids = [_safe(line.get("pig_id")) for line in lines if _safe(line.get("pig_id"))]
    pen_lookup = _pig_pen_lookup(pig_ids)
    enriched = []
    for line in lines:
        item = dict(line)
        pen = pen_lookup.get(_safe(item.get("pig_id")), {})
        item["current_pen_id"] = _safe(pen.get("current_pen_id"))
        item["current_pen_name"] = _safe(pen.get("current_pen_name"))
        enriched.append(item)
    return enriched


def _pig_pen_lookup(pig_ids):
    pig_ids = sorted({str(item or "").strip() for item in pig_ids if str(item or "").strip()})
    if not pig_ids or not os.getenv(DATABASE_URL_ENV, "").strip():
        return {}
    try:
        import psycopg
        with psycopg.connect(os.getenv(DATABASE_URL_ENV), connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select pig_id, current_pen_id, current_pen_name
                    from public.pig_current_state
                    where pig_id = any(%s)
                    """,
                    (pig_ids,),
                )
                return {
                    _safe(pig_id): {
                        "current_pen_id": _safe(current_pen_id),
                        "current_pen_name": _safe(current_pen_name),
                    }
                    for pig_id, current_pen_id, current_pen_name in cursor.fetchall()
                }
    except Exception:
        return {}


def _group_lines_by_pen(lines):
    groups = defaultdict(list)
    for line in lines:
        label = _pen_label(line)
        groups[label].append(line)
    output = []
    for label in sorted(groups.keys(), key=lambda value: (value == "Unknown pen", value)):
        output.append({
            "pen_label": label,
            "lines": sorted(groups[label], key=lambda item: (_safe(item.get("tag_number")), _safe(item.get("pig_id")))),
        })
    return output


def _pen_label(line):
    name = _safe(line.get("current_pen_name"))
    pen_id = _safe(line.get("current_pen_id"))
    if name and pen_id and name != pen_id:
        return f"{name} ({pen_id})"
    return name or pen_id or "Unknown pen"


def _loading_sheet_notes(order, lines, pen_groups, revision_fingerprint=""):
    payload = {
        "worker_safe": True,
        "contains_prices": False,
        "contains_payment_details": False,
        "pig_count": len(lines),
        "pen_count": len(pen_groups),
        "customer": _safe(order.get("customer_name")),
    }
    revision_fingerprint = _safe(revision_fingerprint)
    if revision_fingerprint:
        payload["revision_fingerprint"] = revision_fingerprint
    return "Loading_Sheet_Metadata: " + json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _request_summary(order):
    parts = [
        _safe(order.get("requested_quantity")),
        _safe(order.get("requested_sex")),
        _safe(order.get("requested_category")),
        _safe(order.get("requested_weight_range")).replace("_", " "),
    ]
    return " ".join([part for part in parts if part]) or "-"


def _line_type(line):
    parts = [
        _safe(line.get("sale_category")),
        _safe(line.get("weight_band")).replace("_", " "),
    ]
    return " / ".join([part for part in parts if part]) or "-"


def _active_lines(lines):
    return [line for line in lines if _safe(line.get("line_status")) != "Cancelled"]


def _weight_text(value):
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "-"


def _safe(value):
    return str(value or "").strip()


def _xml(value):
    text = _safe(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _safe_filename(value):
    cleaned = _safe(value) or "loading-sheet.pdf"
    cleaned = cleaned.replace("\\", "_").replace("/", "_").replace(":", "_")
    return cleaned if cleaned.lower().endswith(".pdf") else f"{cleaned}.pdf"


def _parse_json(value):
    try:
        return json.loads(value or "{}")
    except ValueError:
        return {}


def _multipart_body(boundary, fields, file_field, filename, content_type, file_bytes):
    parts = []
    for name, value in fields.items():
        parts.extend([
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
            str(value).encode("utf-8"),
            b"\r\n",
        ])
    parts.extend([
        f"--{boundary}\r\n".encode("utf-8"),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode("utf-8"),
        f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
        file_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ])
    return b"".join(parts)
