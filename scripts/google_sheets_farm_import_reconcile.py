import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.google_sheets_farm_import_dry_run import build_policy_backfill_verifier, load_sheet_rows
from scripts.google_sheets_farm_import_execute import IMPORT_BATCH_ID, IMPORT_ORDER, get_database_url


VIEW_NAMES = [
    "pig_current_state",
    "pig_latest_location_events",
    "pig_latest_weight_events",
]


def build_conflicting_weight_review(verifier):
    review_groups = []
    for index, item in enumerate(
        [row for row in verifier.get("review_items", []) if row.get("review_type") == "conflicting_weight"],
        start=1,
    ):
        sources = []
        for ref in item.get("source_refs", []):
            sample = ref.get("sample", {})
            sources.append({
                "source_sheet_row": ref.get("source_sheet_row"),
                "weight_log_id": sample.get("Weight_Log_ID", ""),
                "pig_name": sample.get("Pig_Name", ""),
                "weight_kg": sample.get("Weight_Kg", ""),
                "pen_id": sample.get("Pen_ID") or sample.get("To_Pen_ID") or "",
                "notes": sample.get("Notes", ""),
            })
        review_groups.append({
            "review_id": f"CW-{index:03d}",
            "status": "pending_owner_review",
            "pig_id": item.get("pig_id"),
            "weight_date": item.get("weight_date"),
            "candidate_weight_values": item.get("candidate_weight_values", []),
            "source_count": len(sources),
            "source_rows": sources,
            "decision_options": [
                "choose_canonical_weight",
                "exclude_group",
                "approve_manual_sheet_correction_then_reimport",
            ],
            "current_import_effect": "excluded_from_canonical_import_until_reviewed",
        })
    return review_groups


def summarize_supabase_counts(cursor, import_batch_id=IMPORT_BATCH_ID):
    table_counts = {}
    import_batch_counts = {}
    for table in IMPORT_ORDER:
        cursor.execute(f"select count(1) from public.{table}")
        table_counts[table] = cursor.fetchone()[0]
        cursor.execute(f"select count(1) from public.{table} where import_batch_id = %s", (import_batch_id,))
        import_batch_counts[table] = cursor.fetchone()[0]

    view_counts = {}
    for view in VIEW_NAMES:
        cursor.execute(f"select count(1) from public.{view}")
        view_counts[view] = cursor.fetchone()[0]

    return {
        "table_counts": table_counts,
        "import_batch_counts": import_batch_counts,
        "view_counts": view_counts,
    }


def compare_payloads_to_supabase(payload_summary, supabase_counts):
    comparisons = {}
    for table, expected in sorted(payload_summary.items()):
        actual = supabase_counts.get("import_batch_counts", {}).get(table)
        comparisons[table] = {
            "expected_from_policy_payload": expected,
            "actual_import_batch_rows": actual,
            "delta": None if actual is None else actual - expected,
            "status": "match" if actual == expected else "mismatch",
        }
    return comparisons


def query_conflict_import_hits(cursor, review_groups):
    hits = []
    for group in review_groups:
        cursor.execute(
            """
            select count(1)
            from public.pig_weight_events
            where pig_id = %s and weight_date = %s
            """,
            (group["pig_id"], group["weight_date"]),
        )
        imported_count = cursor.fetchone()[0]
        hits.append({
            "review_id": group["review_id"],
            "pig_id": group["pig_id"],
            "weight_date": group["weight_date"],
            "imported_count_for_conflicting_key": imported_count,
            "status": "excluded" if imported_count == 0 else "unexpected_imported_rows",
        })
    return hits


def summarize_reconciliation(verifier, supabase_counts, conflict_import_hits):
    payload_summary = verifier["canonical_payload_summary"]
    table_comparisons = compare_payloads_to_supabase(payload_summary, supabase_counts)
    table_match = all(row["status"] == "match" for row in table_comparisons.values())
    conflicts_excluded = all(row["status"] == "excluded" for row in conflict_import_hits)
    return {
        "table_comparisons": table_comparisons,
        "table_counts_match_policy_payload": table_match,
        "conflicting_weight_groups_excluded": conflicts_excluded,
        "route_cutover_ready": False,
        "route_cutover_blocker": "owner/admin review and route-by-route shadow verification required before cutover",
    }


def read_supabase_state(database_url, review_groups, import_batch_id=IMPORT_BATCH_ID, connect_factory=None):
    if connect_factory is None:
        import psycopg
        connect_factory = psycopg.connect

    with connect_factory(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute("set transaction read only")
            supabase_counts = summarize_supabase_counts(cursor, import_batch_id)
            conflict_import_hits = query_conflict_import_hits(cursor, review_groups)
    return supabase_counts, conflict_import_hits


def build_report(sheet_rows, database_url=None, import_batch_id=IMPORT_BATCH_ID, connect_factory=None):
    verifier = build_policy_backfill_verifier(sheet_rows)
    review_groups = build_conflicting_weight_review(verifier)
    if database_url:
        supabase_counts, conflict_import_hits = read_supabase_state(
            database_url,
            review_groups,
            import_batch_id=import_batch_id,
            connect_factory=connect_factory,
        )
    else:
        supabase_counts = {"table_counts": {}, "import_batch_counts": {}, "view_counts": {}}
        conflict_import_hits = []

    reconciliation = summarize_reconciliation(verifier, supabase_counts, conflict_import_hits)

    return {
        "success": True,
        "mode": "read_only_gs_mig_6_review_reconciliation",
        "import_batch_id": import_batch_id,
        "writes_to_supabase": False,
        "writes_to_sheets": False,
        "app_route_cutover": False,
        "review_summary": verifier["review_summary"],
        "conflicting_weight_review": review_groups,
        "supabase_counts": supabase_counts,
        "conflict_import_hits": conflict_import_hits,
        "reconciliation": reconciliation,
        "next_step": "owner/admin review of conflicting weights, then route-by-route shadow verification before cutover",
    }


def markdown_table_line(values):
    return "| " + " | ".join(str(value).replace("\n", " ") for value in values) + " |"


def render_markdown_report(report):
    review_groups = report["conflicting_weight_review"]
    lines = [
        "# GS-MIG-6 Conflicting Weight Review And Reconciliation",
        "",
        "Date: 2026-06-29",
        "",
        "## Status",
        "",
        "Read-only review/reconciliation complete. No app routes have been cut over.",
        "",
        "## Safety",
        "",
        "- No Google Sheets writes.",
        "- No Supabase writes.",
        "- No route cutover.",
        "- No customer sends, public posts, payments, reservations, or lifecycle/purpose writes.",
        "",
        "## Supabase Reconciliation",
        "",
        markdown_table_line(["Table", "Expected", "Imported", "Delta", "Status"]),
        markdown_table_line(["---", "---:", "---:", "---:", "---"]),
    ]
    for table, comparison in report["reconciliation"]["table_comparisons"].items():
        lines.append(markdown_table_line([
            f"`{table}`",
            comparison["expected_from_policy_payload"],
            comparison["actual_import_batch_rows"],
            comparison["delta"],
            comparison["status"],
        ]))

    lines.extend([
        "",
        "## Derived Views",
        "",
        markdown_table_line(["View", "Rows"]),
        markdown_table_line(["---", "---:"]),
    ])
    for view, count in report["supabase_counts"]["view_counts"].items():
        lines.append(markdown_table_line([f"`{view}`", count]))

    lines.extend([
        "",
        "## Conflicting Weight Groups For Review",
        "",
        "These rows were excluded from the canonical import. They must not affect current weight, meat readiness, allocation, stock valuation, or dashboards until reviewed.",
        "",
        markdown_table_line(["Review ID", "Pig ID", "Date", "Candidate weights", "Source rows", "Status"]),
        markdown_table_line(["---", "---", "---", "---", "---", "---"]),
    ])
    for group in review_groups:
        lines.append(markdown_table_line([
            group["review_id"],
            group["pig_id"],
            group["weight_date"],
            ", ".join(group["candidate_weight_values"]),
            group["source_count"],
            group["status"],
        ]))

    lines.extend(["", "## Source Row Details", ""])
    for group in review_groups:
        lines.extend([
            f"### {group['review_id']} - {group['pig_id']} on {group['weight_date']}",
            "",
            markdown_table_line(["Sheet row", "Weight_Log_ID", "Pig name", "Weight kg", "Pen", "Notes"]),
            markdown_table_line(["---:", "---", "---", "---:", "---", "---"]),
        ])
        for row in group["source_rows"]:
            lines.append(markdown_table_line([
                row["source_sheet_row"],
                row["weight_log_id"],
                row["pig_name"],
                row["weight_kg"],
                row["pen_id"],
                row["notes"],
            ]))
        lines.append("")

    lines.extend([
        "## Conflict Exclusion Check",
        "",
        markdown_table_line(["Review ID", "Pig ID", "Date", "Imported rows for conflict key", "Status"]),
        markdown_table_line(["---", "---", "---", "---:", "---"]),
    ])
    for hit in report["conflict_import_hits"]:
        lines.append(markdown_table_line([
            hit["review_id"],
            hit["pig_id"],
            hit["weight_date"],
            hit["imported_count_for_conflicting_key"],
            hit["status"],
        ]))

    lines.extend([
        "",
        "## Recommendation",
        "",
        "Do not cut over app routes yet. Next step is owner/admin review of the 9 conflicting-weight groups, followed by route-by-route shadow verification against Supabase canonical reads.",
        "",
    ])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build read-only GS-MIG-6 conflicting-weight review and Supabase reconciliation."
    )
    parser.add_argument("--write-markdown", help="Optional path for a generated Markdown report.")
    parser.add_argument("--import-batch-id", default=IMPORT_BATCH_ID)
    parser.add_argument("--no-database", action="store_true", help="Skip Supabase reconciliation.")
    args = parser.parse_args(argv)

    try:
        sheet_rows = load_sheet_rows()
        database_url = None
        if not args.no_database:
            load_dotenv(ROOT_DIR / ".env")
            database_url = os.getenv("DATABASE_URL", "").strip() or get_database_url()
        report = build_report(sheet_rows, database_url=database_url, import_batch_id=args.import_batch_id)
        if args.write_markdown:
            output_path = Path(args.write_markdown)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(render_markdown_report(report), encoding="utf-8")
    except Exception as exc:
        report = {
            "success": False,
            "mode": "read_only_gs_mig_6_review_reconciliation",
            "writes_to_supabase": False,
            "writes_to_sheets": False,
            "app_route_cutover": False,
            "error_type": exc.__class__.__name__,
            "message": str(exc),
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
