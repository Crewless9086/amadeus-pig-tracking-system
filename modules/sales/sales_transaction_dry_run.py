from modules.sales.sales_transaction_validation import validate_sales_transaction_payload


def dry_run_sales_transaction(payload):
    validation = validate_sales_transaction_payload(payload or {})
    if not validation["is_valid"]:
        return {
            "success": False,
            "status": "validation_failed",
            "errors": validation["errors"],
            "source": _source_metadata(),
        }, 400

    cleaned = validation["cleaned_data"]
    return {
        "success": True,
        "status": "ok",
        "mode": "dry_run",
        "message": "Sales transaction payload is valid. No rows were written.",
        "sales_transaction": {
            key: value
            for key, value in cleaned.items()
            if key != "items"
        },
        "items": cleaned["items"],
        "summary": {
            "sale_stream": cleaned["sale_stream"],
            "pig_count": cleaned["pig_count"],
            "item_count": len(cleaned["items"]),
            "gross_total": cleaned["gross_total"],
            "deductions_total": cleaned["deductions_total"],
            "net_total": cleaned["net_total"],
            "currency": cleaned["currency"],
        },
        "source": _source_metadata(),
    }, 200


def _source_metadata():
    return {
        "source": "validation_only",
        "writes_to_sheets": False,
        "writes_to_supabase": False,
    }
