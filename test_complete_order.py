"""
Unit tests for the complete_order batch-update logic.

Tests batch_update_rows_by_id (the service helper) and the
complete_order pre-write validation, using in-memory fakes
so no Google Sheets credentials are needed.

Run with: python test_complete_order.py
"""

# ── Inline copy of batch_update_rows_by_id logic ─────────────────────────────

def _batch_update_rows_by_id_memory(all_values: list, updates_map: dict):
    """
    In-memory simulation of batch_update_rows_by_id.
    Applies updates_map to all_values and returns the mutated rows
    (without any sheet write). Raises ValueError for missing IDs.
    """
    if not updates_map:
        return all_values, 0

    if not all_values or len(all_values) < 2:
        raise ValueError("Sheet is empty.")

    headers = all_values[0]
    header_map = {h: i for i, h in enumerate(headers)}

    rows = [list(r) for r in all_values]   # deep copy so we don't mutate input
    found_ids = set()

    for row_index, row in enumerate(rows[1:], start=1):
        row_id = str(row[0]).strip() if row else ""
        if row_id not in updates_map:
            continue

        field_updates = updates_map[row_id]
        padded = row + [""] * (len(headers) - len(row))

        for field_name, field_value in field_updates.items():
            if field_name not in header_map:
                raise ValueError(f"Missing column '{field_name}'.")
            padded[header_map[field_name]] = field_value

        rows[row_index] = padded
        found_ids.add(row_id)

    missing = set(updates_map.keys()) - found_ids
    if missing:
        raise ValueError(f"IDs not found: {', '.join(sorted(missing))}")

    return rows, len(found_ids)


# ── Inline copy of complete_order validation logic ────────────────────────────

def _validate_complete_order(order_row, order_lines_headers, order_lines_rows, order_id):
    """Returns list of active line dicts or raises ValueError."""
    if not order_row:
        raise ValueError("Order not found.")

    old_status = str(order_row.get("Order_Status", "")).strip()
    if old_status != "Approved":
        raise ValueError(f"Only Approved orders can be completed. Current status: {old_status}.")

    if not order_lines_headers:
        raise ValueError("ORDER_LINES is empty.")

    header_map = {h: i for i, h in enumerate(order_lines_headers)}
    for field in ["Order_Line_ID", "Order_ID", "Pig_ID", "Line_Status"]:
        if field not in header_map:
            raise ValueError(f"Missing required column '{field}' in ORDER_LINES.")

    active_lines = []
    for row in order_lines_rows:
        if not row:
            continue
        padded = row + [""] * (len(order_lines_headers) - len(row))
        if str(padded[header_map["Order_ID"]]).strip() != order_id:
            continue
        if str(padded[header_map["Line_Status"]]).strip() == "Cancelled":
            continue
        line_id = str(padded[header_map["Order_Line_ID"]]).strip()
        pig_id  = str(padded[header_map["Pig_ID"]]).strip()
        if not line_id:
            continue
        active_lines.append({"line_id": line_id, "pig_id": pig_id})

    if not active_lines:
        raise ValueError("Order has no active lines to complete.")

    missing_pig = [l["line_id"] for l in active_lines if not l["pig_id"]]
    if missing_pig:
        raise ValueError(f"Lines without Pig_ID: {', '.join(missing_pig)}")

    return active_lines


# ── Test helpers ──────────────────────────────────────────────────────────────

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results = []

def check(name, condition):
    status = PASS if condition else FAIL
    print(f"  [{status}] {name}")
    results.append(condition)

def check_raises(name, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
        print(f"  [{FAIL}] {name} (expected ValueError, got none)")
        results.append(False)
    except ValueError as exc:
        print(f"  [{PASS}] {name} ({exc})")
        results.append(True)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_order_lines_sheet(n_pigs=20, order_id="ORD-2026-TEST01"):
    headers = ["Order_Line_ID", "Order_ID", "Pig_ID", "Tag_Number",
               "Sale_Category", "Line_Status", "Updated_At"]
    rows = []
    for i in range(1, n_pigs + 1):
        rows.append([
            f"OL-2026-{i:05d}",
            order_id,
            f"PIG-2026-{i:04d}",
            f"TAG-{i:03d}",
            "Grower Pigs",
            "Reserved",
            "01 Jan 2026",
        ])
    # Extra cancelled line — must be ignored
    rows.append(["OL-2026-99999", order_id, "PIG-2026-9999", "TAG-999",
                 "Grower Pigs", "Cancelled", "01 Jan 2026"])
    return [headers] + rows

def make_pig_master_sheet(n_pigs=20):
    headers = ["Pig_ID", "Tag_Number", "Status", "On_Farm",
               "Exit_Date", "Exit_Reason", "Exit_Order_ID", "Updated_At"]
    rows = []
    for i in range(1, n_pigs + 1):
        rows.append([
            f"PIG-2026-{i:04d}",
            f"TAG-{i:03d}",
            "Active",
            "Yes",
            "",
            "",
            "",
            "01 Jan 2026",
        ])
    return [headers] + rows


# ── TEST 1: batch update — all 20 rows updated, 1 cancelled skipped ───────────
print("\nTEST 1: batch_update_rows_by_id — 20 lines, 1 cancelled line ignored")

ORDER_ID = "ORD-2026-TEST01"
ol_sheet = make_order_lines_sheet(20, ORDER_ID)
ol_headers = ol_sheet[0]
ol_rows    = ol_sheet[1:]

order_row = {"Order_Status": "Approved", "Approval_Status": "Approved"}
active_lines = _validate_complete_order(order_row, ol_headers, ol_rows, ORDER_ID)

check("finds exactly 20 active lines (cancelled excluded)", len(active_lines) == 20)

today_str = "23 Apr 2026"
ol_updates = {l["line_id"]: {"Line_Status": "Collected", "Updated_At": today_str}
              for l in active_lines}

updated_ol, count = _batch_update_rows_by_id_memory(ol_sheet, ol_updates)
check("batch update returns count 20", count == 20)
check("all 20 active lines now show Collected",
      sum(1 for r in updated_ol[1:] if r[5] == "Collected") == 20)
check("cancelled line still shows Cancelled",
      any(r[5] == "Cancelled" for r in updated_ol[1:]))
check("Updated_At set on active rows",
      all(r[6] == today_str for r in updated_ol[1:] if r[5] == "Collected"))


# ── TEST 2: PIG_MASTER batch update ───────────────────────────────────────────
print("\nTEST 2: PIG_MASTER — 20 pigs marked Sold in one batch")

pm_sheet = make_pig_master_sheet(20)

pig_updates = {
    l["pig_id"]: {
        "Status":        "Sold",
        "On_Farm":       "No",
        "Exit_Date":     today_str,
        "Exit_Reason":   "Sold",
        "Exit_Order_ID": ORDER_ID,
        "Updated_At":    today_str,
    }
    for l in active_lines
}

updated_pm, pm_count = _batch_update_rows_by_id_memory(pm_sheet, pig_updates)
check("batch update returns count 20", pm_count == 20)
check("all 20 pigs Status=Sold",   sum(1 for r in updated_pm[1:] if r[2] == "Sold")   == 20)
check("all 20 pigs On_Farm=No",    sum(1 for r in updated_pm[1:] if r[3] == "No")     == 20)
check("Exit_Order_ID set",         all(r[6] == ORDER_ID for r in updated_pm[1:]))
check("Exit_Date set",             all(r[4] == today_str for r in updated_pm[1:]))


# ── TEST 3: Validation — rejects non-Approved order ──────────────────────────
print("\nTEST 3: Validation — rejects non-Approved status")

check_raises("Draft order rejected",
    _validate_complete_order,
    {"Order_Status": "Draft"}, ol_headers, ol_rows, ORDER_ID)

check_raises("Pending_Approval order rejected",
    _validate_complete_order,
    {"Order_Status": "Pending_Approval"}, ol_headers, ol_rows, ORDER_ID)

check_raises("already Completed order rejected",
    _validate_complete_order,
    {"Order_Status": "Completed"}, ol_headers, ol_rows, ORDER_ID)


# ── TEST 4: Validation — rejects lines with no Pig_ID ────────────────────────
print("\nTEST 4: Validation — rejects lines missing Pig_ID")

bad_headers = ["Order_Line_ID", "Order_ID", "Pig_ID", "Line_Status", "Updated_At"]
bad_rows = [
    ["OL-2026-00001", ORDER_ID, "PIG-2026-0001", "Reserved", "01 Jan 2026"],
    ["OL-2026-00002", ORDER_ID, "",              "Reserved", "01 Jan 2026"],  # no pig
]

check_raises("line with empty Pig_ID causes error",
    _validate_complete_order,
    {"Order_Status": "Approved"}, bad_headers, bad_rows, ORDER_ID)


# ── TEST 5: Validation — rejects order with only cancelled lines ──────────────
print("\nTEST 5: Validation — order with only cancelled lines")

cancelled_headers = ["Order_Line_ID", "Order_ID", "Pig_ID", "Line_Status", "Updated_At"]
cancelled_rows = [
    ["OL-2026-00001", ORDER_ID, "PIG-2026-0001", "Cancelled", "01 Jan 2026"],
    ["OL-2026-00002", ORDER_ID, "PIG-2026-0002", "Cancelled", "01 Jan 2026"],
]

check_raises("order with only cancelled lines raises error",
    _validate_complete_order,
    {"Order_Status": "Approved"}, cancelled_headers, cancelled_rows, ORDER_ID)


# ── TEST 6: batch update — missing ID raises clearly ─────────────────────────
print("\nTEST 6: batch update — unknown ID raises ValueError")

check_raises("unknown pig ID raises ValueError",
    _batch_update_rows_by_id_memory,
    pm_sheet, {"PIG-9999-FAKE": {"Status": "Sold"}})


# ── TEST 7: empty updates_map is a no-op ──────────────────────────────────────
print("\nTEST 7: empty updates_map is safe no-op")

rows_copy = [list(r) for r in pm_sheet]
result_rows, count = _batch_update_rows_by_id_memory(pm_sheet, {})
check("returns 0 count", count == 0)
check("rows unchanged", result_rows == rows_copy)


# ── Summary ───────────────────────────────────────────────────────────────────
passed = sum(results)
total  = len(results)
print(f"\n{'='*50}")
print(f"Results: {passed}/{total} passed")
if passed == total:
    print("\033[32mAll tests passed.\033[0m")
else:
    print(f"\033[31m{total - passed} test(s) failed.\033[0m")
    raise SystemExit(1)
