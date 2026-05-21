import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.google_sheets_service import get_all_records


ORDER_MASTER_SHEET = "ORDER_MASTER"
ORDER_STATUS_LOG_SHEET = "ORDER_STATUS_LOG"
TEST_CUSTOMER_NAMES = {"charl n"}


def clean(value):
    return str(value or "").strip()


def clean_lower(value):
    return clean(value).lower()


def build_order_status_log_diagnostic(order_rows, status_log_rows, sample_limit=20):
    order_customer_by_id = {
        clean(row.get("Order_ID")): clean(row.get("Customer_Name"))
        for row in order_rows
        if clean(row.get("Order_ID"))
    }
    all_order_ids = set(order_customer_by_id)
    test_order_ids = {
        order_id
        for order_id, customer_name in order_customer_by_id.items()
        if clean_lower(customer_name) in TEST_CUSTOMER_NAMES
    }

    reason_counts = Counter()
    samples = {
        "missing_order_id": [],
        "missing_parent_order": [],
        "test_parent_order": [],
        "included_candidate": [],
    }

    for index, row in enumerate(status_log_rows, start=2):
        order_id = clean(row.get("Order_ID"))
        log_id = clean(row.get("Order_Status_Log_ID"))

        if not order_id:
            reason = "missing_order_id"
        elif order_id not in all_order_ids:
            reason = "missing_parent_order"
        elif order_id in test_order_ids:
            reason = "test_parent_order"
        else:
            reason = "included_candidate"

        reason_counts[reason] += 1

        if len(samples[reason]) < sample_limit:
            samples[reason].append(
                {
                    "sheet_row": index,
                    "status_log_id": log_id,
                    "order_id": order_id,
                    "old_status": clean(row.get("Old_Status")),
                    "new_status": clean(row.get("New_Status")),
                    "changed_by": clean(row.get("Changed_By")),
                    "change_source": clean(row.get("Change_Source")),
                    "notes": clean(row.get("Notes"))[:250],
                }
            )

    return {
        "success": True,
        "mode": "diagnostic_only",
        "writes_to_supabase": False,
        "writes_to_sheets": False,
        "order_master_rows": len(order_rows),
        "status_log_rows": len(status_log_rows),
        "order_master_ids": len(all_order_ids),
        "test_order_ids": len(test_order_ids),
        "reason_counts": dict(sorted(reason_counts.items())),
        "samples": samples,
        "recommendation": (
            "Import included_candidate status logs only. Exclude missing parent/test parent logs "
            "unless owner explicitly identifies specific rows as business history."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose ORDER_STATUS_LOG rows before Supabase import mapping."
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=20,
        help="Maximum examples to include for each reason.",
    )
    args = parser.parse_args()

    report = build_order_status_log_diagnostic(
        get_all_records(ORDER_MASTER_SHEET),
        get_all_records(ORDER_STATUS_LOG_SHEET),
        sample_limit=args.sample_limit,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
