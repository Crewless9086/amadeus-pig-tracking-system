import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.google_sheets_farm_import_dry_run import load_sheet_rows
from services.database_service import DATABASE_URL_ENV


FORMULA_SHEETS = [
    "PIG_OVERVIEW",
    "SALES_AVAILABILITY",
    "SALES_STOCK_SUMMARY",
    "SALES_STOCK_TOTALS",
    "LITTER_OVERVIEW",
    "MATING_OVERVIEW",
]


def _clean(value):
    return "" if value is None else str(value).strip()


def _is_yes(value):
    return _clean(value).lower() == "yes"


def _count_by(rows, field):
    counts = {}
    for row in rows:
        key = _clean(row.get(field)) or "blank"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def summarize_sheet_formulas(sheet_rows):
    pig_rows = sheet_rows.get("PIG_OVERVIEW", [])
    sales_rows = sheet_rows.get("SALES_AVAILABILITY", [])
    sales_summary_rows = sheet_rows.get("SALES_STOCK_SUMMARY", [])
    sales_total_rows = sheet_rows.get("SALES_STOCK_TOTALS", [])
    litter_rows = sheet_rows.get("LITTER_OVERVIEW", [])
    mating_rows = sheet_rows.get("MATING_OVERVIEW", [])

    return {
        "pig_overview": {
            "row_count": len(pig_rows),
            "active_on_farm_count": len([
                row for row in pig_rows
                if _clean(row.get("Status")) == "Active" and _is_yes(row.get("On_Farm"))
            ]),
            "animal_type_counts": _count_by(pig_rows, "Animal_Type"),
            "status_counts": _count_by(pig_rows, "Status"),
            "on_farm_counts": _count_by(pig_rows, "On_Farm"),
            "current_pen_count": len({_clean(row.get("Current_Pen_ID")) for row in pig_rows if _clean(row.get("Current_Pen_ID"))}),
        },
        "sales_availability": {
            "row_count": len(sales_rows),
            "available_for_sale_count": len([row for row in sales_rows if _is_yes(row.get("Available_For_Sale"))]),
            "sale_category_counts": _count_by(sales_rows, "Sale_Category"),
        },
        "sales_stock_summary": {
            "row_count": len(sales_summary_rows),
            "sale_category_counts": _count_by(sales_summary_rows, "Sale_Category"),
        },
        "sales_stock_totals": {
            "row_count": len(sales_total_rows),
            "sale_category_counts": _count_by(sales_total_rows, "Sale_Category"),
        },
        "litter_overview": {
            "row_count": len(litter_rows),
            "needs_attention_count": len([row for row in litter_rows if _is_yes(row.get("Needs_Attention"))]),
            "status_counts": _count_by(litter_rows, "Litter_Status"),
        },
        "mating_overview": {
            "row_count": len(mating_rows),
            "status_counts": _count_by(mating_rows, "Mating_Status"),
            "outcome_counts": _count_by(mating_rows, "Outcome"),
        },
    }


def summarize_supabase_formula_sources(cursor):
    cursor.execute("set transaction read only")
    cursor.execute(
        """
        select
            count(1) as row_count,
            count(1) filter (where status = 'Active' and on_farm is true) as active_on_farm_count,
            count(distinct current_pen_id) filter (where current_pen_id is not null and current_pen_id <> '') as current_pen_count
        from public.pig_current_state
        """
    )
    pig_counts = cursor.fetchone()
    cursor.execute(
        """
        select coalesce(nullif(animal_type, ''), 'blank') as key, count(1)
        from public.pig_current_state
        group by key
        order by key
        """
    )
    animal_type_counts = dict(cursor.fetchall())
    cursor.execute(
        """
        select coalesce(nullif(status, ''), 'blank') as key, count(1)
        from public.pig_current_state
        group by key
        order by key
        """
    )
    status_counts = dict(cursor.fetchall())
    cursor.execute(
        """
        select case when on_farm is true then 'Yes' when on_farm is false then 'No' else 'blank' end as key, count(1)
        from public.pig_current_state
        group by key
        order by key
        """
    )
    on_farm_counts = dict(cursor.fetchall())

    cursor.execute("select count(1) from public.litters")
    litter_count = cursor.fetchone()[0]
    cursor.execute(
        """
        select coalesce(nullif(litter_status, ''), 'blank') as key, count(1)
        from public.litters
        group by key
        order by key
        """
    )
    litter_status_counts = dict(cursor.fetchall())

    cursor.execute("select count(1) from public.mating_events")
    mating_count = cursor.fetchone()[0]
    cursor.execute(
        """
        select coalesce(nullif(outcome, ''), 'blank') as key, count(1)
        from public.mating_events
        group by key
        order by key
        """
    )
    mating_outcome_counts = dict(cursor.fetchall())

    return {
        "pig_overview_candidate": {
            "row_count": pig_counts[0],
            "active_on_farm_count": pig_counts[1],
            "animal_type_counts": animal_type_counts,
            "status_counts": status_counts,
            "on_farm_counts": on_farm_counts,
            "current_pen_count": pig_counts[2],
        },
        "litter_overview_candidate": {
            "row_count": litter_count,
            "status_counts": litter_status_counts,
        },
        "mating_overview_candidate": {
            "row_count": mating_count,
            "outcome_counts": mating_outcome_counts,
        },
        "sales_availability_candidate": {
            "status": "not_implemented",
            "blocker": "sales readiness formula replacement view/service not built yet",
        },
        "sales_stock_candidate": {
            "status": "not_implemented",
            "blocker": "sales stock summary/totals replacement view/service not built yet",
        },
    }


def compare_metric(sheet_summary, supabase_summary, sheet_path, supabase_path):
    sheet_value = sheet_summary
    for part in sheet_path:
        sheet_value = sheet_value.get(part, {})
    supabase_value = supabase_summary
    for part in supabase_path:
        supabase_value = supabase_value.get(part, {})
    return {
        "sheet_path": ".".join(sheet_path),
        "supabase_path": ".".join(supabase_path),
        "sheet_value": sheet_value,
        "supabase_value": supabase_value,
        "match": sheet_value == supabase_value,
    }


def build_shadow_report(sheet_rows, supabase_summary=None):
    sheet_summary = summarize_sheet_formulas(sheet_rows)
    supabase_summary = supabase_summary or {}
    comparisons = []
    if supabase_summary:
        comparisons.extend([
            compare_metric(sheet_summary, supabase_summary, ("pig_overview", "row_count"), ("pig_overview_candidate", "row_count")),
            compare_metric(sheet_summary, supabase_summary, ("pig_overview", "active_on_farm_count"), ("pig_overview_candidate", "active_on_farm_count")),
            compare_metric(sheet_summary, supabase_summary, ("pig_overview", "animal_type_counts"), ("pig_overview_candidate", "animal_type_counts")),
            compare_metric(sheet_summary, supabase_summary, ("pig_overview", "status_counts"), ("pig_overview_candidate", "status_counts")),
            compare_metric(sheet_summary, supabase_summary, ("pig_overview", "on_farm_counts"), ("pig_overview_candidate", "on_farm_counts")),
            compare_metric(sheet_summary, supabase_summary, ("litter_overview", "row_count"), ("litter_overview_candidate", "row_count")),
            compare_metric(sheet_summary, supabase_summary, ("mating_overview", "row_count"), ("mating_overview_candidate", "row_count")),
        ])

    return {
        "success": True,
        "mode": "read_only_formula_shadow",
        "writes_to_supabase": False,
        "writes_to_sheets": False,
        "route_cutover": False,
        "formula_sheets": FORMULA_SHEETS,
        "sheet_summary": sheet_summary,
        "supabase_summary": supabase_summary,
        "comparisons": comparisons,
        "all_compared_metrics_match": bool(comparisons) and all(item["match"] for item in comparisons),
        "blocked_routes": [
            "dashboard",
            "sales-dashboard",
            "pig-allocation-readiness",
            "sales-availability",
            "meat-planning",
            "litters",
            "litter-detail",
        ],
    }


def render_markdown_report(report):
    lines = [
        "# GS-MIG-7B Formula Shadow Report",
        "",
        "Date: 2026-06-29",
        "",
        "## Status",
        "",
        "Read-only formula shadow comparison. No app route cutover.",
        "",
        "## Safety",
        "",
        "- No Google Sheets writes.",
        "- No Supabase writes.",
        "- No route cutover.",
        "",
        "## Compared Metrics",
        "",
        "| Metric | Sheets | Supabase | Match |",
        "| --- | ---: | ---: | --- |",
    ]
    if report["comparisons"]:
        for comparison in report["comparisons"]:
            lines.append(
                f"| `{comparison['sheet_path']}` | {comparison['sheet_value']} | {comparison['supabase_value']} | {comparison['match']} |"
            )
    else:
        lines.append("| No Supabase comparison was run | - | - | False |")
    lines.extend([
        "",
        "## Blocked Routes",
        "",
    ])
    for route in report["blocked_routes"]:
        lines.append(f"- `{route}`")
    lines.extend([
        "",
        "## Next",
        "",
        "Implement Supabase formula replacement services/views and compare route outputs before switching these routes.",
    ])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Read-only Google Sheets vs Supabase formula shadow comparison.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args()

    load_dotenv()
    sheet_rows = load_sheet_rows()
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    supabase_summary = {}
    if database_url:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                supabase_summary = summarize_supabase_formula_sources(cursor)

    report = build_shadow_report(sheet_rows, supabase_summary=supabase_summary)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print(render_markdown_report(report))


if __name__ == "__main__":
    main()
