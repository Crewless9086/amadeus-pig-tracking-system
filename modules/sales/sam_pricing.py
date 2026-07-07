import os
import re
import uuid
from datetime import datetime, timezone

from modules.pig_weights.pig_weights_utils import to_clean_string, to_float
from services.database_service import DATABASE_URL_ENV


LIVE_STOCK_PRICE_DEFAULTS = [
    ("Newborn", "N/A", 300),
    ("Young Piglets", "2_to_4_Kg", 350),
    ("Young Piglets", "5_to_6_Kg", 400),
    ("Weaner Piglets", "7_to_9_Kg", 450),
    ("Weaner Piglets", "10_to_14_Kg", 500),
    ("Weaner Piglets", "15_to_19_Kg", 600),
    ("Grower Pigs", "20_to_24_Kg", 800),
    ("Grower Pigs", "25_to_29_Kg", 1000),
    ("Grower Pigs", "30_to_34_Kg", 1200),
    ("Grower Pigs", "35_to_39_Kg", 1400),
    ("Grower Pigs", "40_to_44_Kg", 1600),
    ("Grower Pigs", "45_to_49_Kg", 1800),
    ("Finisher Pigs", "50_to_54_Kg", 2200),
    ("Finisher Pigs", "55_to_59_Kg", 2300),
    ("Finisher Pigs", "60_to_64_Kg", 2400),
    ("Finisher Pigs", "65_to_69_Kg", 2500),
    ("Finisher Pigs", "70_to_74_Kg", 2600),
    ("Finisher Pigs", "75_to_79_Kg", 2700),
    ("Ready for Slaughter", "80_to_84_Kg", 2800),
    ("Ready for Slaughter", "85_to_89_Kg", 2900),
    ("Ready for Slaughter", "90_to_94_Kg", 3000),
]


CATEGORY_TO_SALE_CATEGORY = {
    "piglet": "Young Piglets",
    "Piglet": "Young Piglets",
    "Young Piglets": "Young Piglets",
    "weaner": "Weaner Piglets",
    "Weaner": "Weaner Piglets",
    "Weaner Piglets": "Weaner Piglets",
    "grower": "Grower Pigs",
    "Grower": "Grower Pigs",
    "Grower Pigs": "Grower Pigs",
    "finisher": "Finisher Pigs",
    "Finisher": "Finisher Pigs",
    "Finisher Pigs": "Finisher Pigs",
    "ready_for_slaughter": "Ready for Slaughter",
    "Slaughter": "Ready for Slaughter",
    "Ready for Slaughter": "Ready for Slaughter",
}


def default_live_stock_price_entries():
    created_at = "2026-05-21T00:00:00+00:00"
    return [
        {
            "pricing_id": _pricing_id(category, band, "ANY", "DEFAULT"),
            "sale_category": category,
            "weight_band": band,
            "sex": "",
            "unit_price": float(price),
            "currency": "ZAR",
            "effective_from": created_at,
            "effective_to": "",
            "active": True,
            "change_reason": "Code fallback copied from SALES_PRICING.",
            "created_by": "code_defaults",
            "created_at": created_at,
            "source": "code_defaults",
        }
        for category, band, price in LIVE_STOCK_PRICE_DEFAULTS
    ]


def list_live_stock_price_entries(limit=100, database_url=None):
    parsed_limit = _bounded_limit(limit, default=100, maximum=500)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        entries = default_live_stock_price_entries()[:parsed_limit]
        return _price_list_result(entries, configured=False, source="code_defaults"), 200

    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", configured=True), 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select pricing_id, sale_category, weight_band, sex, unit_price, currency,
                           effective_from, effective_to, active, change_reason, created_by, created_at
                    from public.sales_pricing
                    order by effective_from desc, created_at desc, sale_category, weight_band
                    limit %(limit)s
                    """,
                    {"limit": parsed_limit},
                )
                columns = [column.name for column in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "live_stock_pricing_read_failed",
            "error_type": exc.__class__.__name__,
            "price_entries": [],
            "active_recommendations": {},
            "writes": False,
            "sends_customer_message": False,
        }, 503

    entries = [_public_price_row(row, source="supabase") for row in rows]
    source = "supabase" if entries else "code_defaults"
    effective_entries = entries if entries else default_live_stock_price_entries()
    return _price_list_result(entries, configured=True, source=source, effective_entries=effective_entries), 200


def record_live_stock_price_entry(payload, database_url=None):
    params, error = _live_stock_price_params(payload)
    if error:
        return error, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _unavailable("not_configured", configured=False), 503

    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", configured=True), 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.sales_pricing (
                        pricing_id, sale_category, weight_band, sex, unit_price, currency,
                        effective_from, effective_to, active, change_reason, created_by, created_at, updated_at
                    )
                    values (
                        %(pricing_id)s, %(sale_category)s, %(weight_band)s, %(sex)s, %(unit_price)s, 'ZAR',
                        %(effective_from)s::timestamptz, %(effective_to)s::timestamptz, true,
                        %(change_reason)s, %(created_by)s, now(), now()
                    )
                    returning pricing_id
                    """,
                    params,
                )
                cursor.fetchone()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "live_stock_pricing_write_failed",
            "error_type": exc.__class__.__name__,
            "writes": False,
            "sends_customer_message": False,
        }, 503

    listed, status_code = list_live_stock_price_entries(limit=100, database_url=database_url)
    if status_code != 200:
        return listed, status_code
    entry = next(
        (item for item in listed.get("price_entries", []) if item.get("pricing_id") == params["pricing_id"]),
        _public_price_row(params, source="supabase"),
    )
    return {
        "success": True,
        "status": "live_stock_price_entry_recorded",
        "price_entry": entry,
        "price_entries": listed.get("price_entries", []),
        "active_recommendations": listed.get("active_recommendations", {}),
        "writes": True,
        "sends_customer_message": False,
    }, 201


def resolve_live_stock_price_rule(category, weight_band, sex="", as_of=None, database_url=None):
    sale_category = normal_live_sale_category(category)
    weight_band = to_clean_string(weight_band)
    sex = to_clean_string(sex)
    if not sale_category or not weight_band:
        return {
            "found": False,
            "status": "missing_category_or_weight_band",
            "sale_category": sale_category,
            "weight_band": weight_band,
        }
    listed, status_code = list_live_stock_price_entries(limit=500, database_url=database_url)
    entries = listed.get("price_entries", []) if status_code == 200 else default_live_stock_price_entries()
    selected = _select_effective_price(entries, sale_category, weight_band, sex, as_of=as_of)
    if not selected:
        return {
            "found": False,
            "status": "price_not_found",
            "sale_category": sale_category,
            "weight_band": weight_band,
            "source": listed.get("source", "unknown") if isinstance(listed, dict) else "unknown",
        }
    return {
        "found": True,
        "status": "ok",
        "pricing_id": selected.get("pricing_id", ""),
        "sale_category": selected.get("sale_category", sale_category),
        "weight_band": selected.get("weight_band", weight_band),
        "sex": selected.get("sex", ""),
        "unit_price": selected.get("unit_price"),
        "currency": selected.get("currency", "ZAR"),
        "effective_from": selected.get("effective_from", ""),
        "effective_to": selected.get("effective_to", ""),
        "source": selected.get("source", listed.get("source", "")),
    }


def normal_live_sale_category(category):
    clean = to_clean_string(category)
    return CATEGORY_TO_SALE_CATEGORY.get(clean, clean)


def _price_list_result(entries, configured, source, effective_entries=None):
    effective_entries = effective_entries if effective_entries is not None else entries
    return {
        "success": True,
        "configured": configured,
        "status": "ok" if configured else "code_defaults_only",
        "mode": "sam_live_stock_pricing_append_only",
        "price_entries": entries,
        "active_recommendations": _active_live_stock_price_recommendations(effective_entries),
        "source": source,
        "writes": False,
        "sends_customer_message": False,
    }


def _active_live_stock_price_recommendations(entries):
    recommendations = {}
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or entry.get("active") is False:
            continue
        category = to_clean_string(entry.get("sale_category"))
        band = to_clean_string(entry.get("weight_band"))
        if not category or not band:
            continue
        key = f"{category}|{band}"
        current = recommendations.get(key)
        if not current or _sort_date(entry) >= _sort_date(current):
            recommendations[key] = {
                "sale_category": category,
                "weight_band": band,
                "price_label": _money_label(entry.get("unit_price")),
                "unit_price": entry.get("unit_price"),
                "effective_from": _iso(entry.get("effective_from")),
                "source": entry.get("source", ""),
            }
    return recommendations


def _select_effective_price(entries, sale_category, weight_band, sex="", as_of=None):
    as_of_key = _iso(as_of) or datetime.now(timezone.utc).isoformat()
    candidates = []
    fallback = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        if entry.get("active") is False:
            continue
        if to_clean_string(entry.get("sale_category")) != sale_category:
            continue
        if to_clean_string(entry.get("weight_band")) != weight_band:
            continue
        effective_from = _iso(entry.get("effective_from"))
        effective_to = _iso(entry.get("effective_to"))
        if effective_from and effective_from > as_of_key:
            continue
        if effective_to and effective_to <= as_of_key:
            continue
        entry_sex = to_clean_string(entry.get("sex"))
        if sex and entry_sex and entry_sex == sex:
            candidates.append(entry)
        elif not entry_sex:
            fallback.append(entry)
    selected = _latest_effective_entry(candidates) or _latest_effective_entry(fallback)
    return selected


def _latest_effective_entry(entries):
    if not entries:
        return {}
    return sorted(entries, key=_sort_date, reverse=True)[0]


def _live_stock_price_params(payload):
    payload = payload if isinstance(payload, dict) else {}
    sale_category = normal_live_sale_category(payload.get("sale_category") or payload.get("category"))
    weight_band = to_clean_string(payload.get("weight_band"))
    unit_price = to_float(payload.get("unit_price") or payload.get("price_amount"))
    effective_from = to_clean_string(payload.get("effective_from")) or datetime.now(timezone.utc).isoformat()
    effective_to = to_clean_string(payload.get("effective_to"))
    sex = to_clean_string(payload.get("sex"))
    created_by = to_clean_string(payload.get("created_by")) or "Farm App"
    change_reason = to_clean_string(payload.get("change_reason")) or "Owner price update."
    errors = []
    if not sale_category:
        errors.append("Sale_Category is required.")
    if not weight_band:
        errors.append("Weight_Band is required.")
    if unit_price is None or unit_price < 0:
        errors.append("Unit_Price must be a non-negative number.")
    if errors:
        return {}, {"success": False, "status": "validation_failed", "errors": errors, "writes": False}
    pricing_id = _pricing_id(sale_category, weight_band, sex or "ANY", uuid.uuid4().hex[:8].upper())
    return {
        "pricing_id": pricing_id,
        "sale_category": sale_category,
        "weight_band": weight_band,
        "sex": sex or None,
        "unit_price": unit_price,
        "effective_from": effective_from,
        "effective_to": effective_to or None,
        "change_reason": change_reason,
        "created_by": created_by,
    }, None


def _public_price_row(row, source):
    return {
        "pricing_id": to_clean_string(row.get("pricing_id")),
        "sale_category": to_clean_string(row.get("sale_category")),
        "weight_band": to_clean_string(row.get("weight_band")),
        "sex": to_clean_string(row.get("sex")),
        "unit_price": to_float(row.get("unit_price")),
        "currency": to_clean_string(row.get("currency")) or "ZAR",
        "effective_from": _iso(row.get("effective_from")),
        "effective_to": _iso(row.get("effective_to")),
        "active": row.get("active") is not False,
        "change_reason": to_clean_string(row.get("change_reason")),
        "created_by": to_clean_string(row.get("created_by")),
        "created_at": _iso(row.get("created_at")),
        "source": source,
    }


def _pricing_id(category, band, sex, suffix):
    raw = f"SAM-LIVE-PRICE-{category}-{band}-{sex}-{suffix}"
    return re.sub(r"[^A-Z0-9_]+", "_", raw.upper()).strip("_")[:100]


def _bounded_limit(value, default=100, maximum=500):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, maximum))


def _sort_date(entry):
    return (_iso(entry.get("effective_from")), _iso(entry.get("created_at")), to_clean_string(entry.get("pricing_id")))


def _iso(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return to_clean_string(value)


def _money_label(value):
    number = to_float(value)
    return "" if number is None else f"R{number:,.2f}"


def _unavailable(status, configured):
    return {
        "success": False,
        "configured": configured,
        "status": status,
        "price_entries": [],
        "active_recommendations": {},
        "writes": False,
        "sends_customer_message": False,
    }
