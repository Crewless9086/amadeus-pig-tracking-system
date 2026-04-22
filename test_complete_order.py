"""
Unit tests for the complete_order batch-update logic.

Tests batch_update_rows_by_id behaviour and the complete_order
pre-write validation using in-memory fakes — no Google Sheets
credentials needed.

Run with: python test_complete_order.py
"""

# ── In-memory simulation of batch_update_rows_by_id ──────────────────────────

def _batch_update_memory(all_values: list, updates_map: dict):
    """
    Simulate batch_update_rows_by_id against an in-memory sheet.
    Returns (mutated_rows, count_updated). Raises ValueError for missing IDs.
    """
    if not updates_map:
        return [list(r) for r in all_values], 0

    if not all_values or len(all_values) < 2:
        raise ValueError("Sheet is empty.")

    headers = all_values[0]
    header_map = {h: i for i, h in enumerate(headers)}

    rows = [list(r) for r in all_values]
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


# ── Validation logic (mirrors complete_order in order_service.py) ─────────────

def _validate(order_row, ol_headers, ol_rows, order_id):
    if not order_row:
        raise ValueError("Order not found.")
    if str(order_row.get("Order_Status", "")).strip() != "Approved":
        raise ValueError(f"Only Approved orders can be completed. Current status: {order_row.get('Order_Status')}.")
    if not ol_headers:
        raise ValueError("ORDER_LINES is empty.")
    hmap = {h: i for i, h in enumerate(ol_headers)}
    for f in ["Order_Line_ID", "Order_ID", "Pig_ID", "Line_Status"]:
        if f not in hmap:
            raise ValueError(f"Missing column '{f}'.")
    active = []
    for row in ol_rows:
        if not row:
            continue
        padded = row + [""] * (len(ol_headers) - len(row))
        if str(padded[hmap["Order_ID"]]).strip() != order_id:
            continue
        if str(padded[hmap["Line_Status"]]).strip() == "Cancelled":
            continue
        lid = str(padded[hmap["Order_Line_ID"]]).strip()
        pid = str(padded[hmap["Pig_ID"]]).strip()
        if not lid:
            continue
        active.append({"line_id": lid, "pig_id": pid})
    if not active:
        raise ValueError("No active lines.")
    no_pig = [l["line_id"] for l in active if not l["pig_id"]]
    if no_pig:
        raise ValueError(f"Lines without Pig_ID: {', '.join(no_pig)}")
    return active


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

ORDER_ID = "ORD-2026-TEST01"

def make_order_lines_sheet(n=20, order_id=ORDER_ID):
    headers = ["Order_Line_ID", "Order_ID", "Pig_ID", "Tag_Number",
               "Sale_Category", "Line_Status", "Reserved_Status", "Updated_At"]
    rows = []
    for i in range(1, n + 1):
        rows.append([f"OL-2026-{i:05d}", order_id, f"PIG-2026-{i:04d}",
                     f"TAG-{i:03d}", "Grower Pigs", "Reserved", "Reserved", "01 Jan 2026"])
    # Cancelled line — must be ignored by validation
    rows.append(["OL-2026-99999", order_id, "PIG-2026-9999", "TAG-999",
                 "Grower Pigs", "Cancelled", "Not_Reserved", "01 Jan 2026"])
    return [headers] + rows

def make_pig_master_sheet(n=20):
    headers = ["Pig_ID", "Tag_Number", "Status", "On_Farm",
               "Exit_Date", "Exit_Reason", "Exit_Order_ID", "Updated_At"]
    rows = [[f"PIG-2026-{i:04d}", f"TAG-{i:03d}", "Active", "Yes",
             "", "", "", "01 Jan 2026"] for i in range(1, n + 1)]
    return [headers] + rows


# ── TEST 1: validation finds 20 active lines, ignores cancelled ───────────────
print("\nTEST 1: Validation — 20 active lines, 1 cancelled ignored")

ol_sheet = make_order_lines_sheet(20)
ol_headers, ol_rows = ol_sheet[0], ol_sheet[1:]
order_row = {"Order_Status": "Approved"}
active_lines = _validate(order_row, ol_headers, ol_rows, ORDER_ID)

check("finds 20 active lines", len(active_lines) == 20)
check("cancelled line excluded", all(l["line_id"] != "OL-2026-99999" for l in active_lines))


# ── TEST 2: ORDER_LINES batch — Line_Status AND Reserved_Status both set ──────
print("\nTEST 2: ORDER_LINES batch — both Line_Status and Reserved_Status updated")

today_str = "23 Apr 2026"
ol_updates = {
    l["line_id"]: {
        "Line_Status":     "Collected",
        "Reserved_Status": "Collected",
        "Updated_At":      today_str,
    }
    for l in active_lines
}

updated_ol, count = _batch_update_memory(ol_sheet, ol_updates)
col_line   = ol_headers.index("Line_Status")
col_res    = ol_headers.index("Reserved_Status")
col_upd    = ol_headers.index("Updated_At")

collected_rows = [r for r in updated_ol[1:] if r[col_line] == "Collected"]
check("batch returns count 20", count == 20)
check("all 20 active lines — Line_Status = Collected", len(collected_rows) == 20)
check("all 20 active lines — Reserved_Status = Collected",
      all(r[col_res] == "Collected" for r in collected_rows))
check("all 20 active lines — Updated_At set",
      all(r[col_upd] == today_str for r in collected_rows))
check("cancelled line untouched — still Cancelled",
      any(r[col_line] == "Cancelled" for r in updated_ol[1:]))
check("cancelled line untouched — still Not_Reserved",
      any(r[col_res] == "Not_Reserved" for r in updated_ol[1:]))


# ── TEST 3: PIG_MASTER batch — all pigs marked Sold ──────────────────────────
print("\nTEST 3: PIG_MASTER — 20 pigs marked Sold")

pm_sheet = make_pig_master_sheet(20)
pm_headers = pm_sheet[0]
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

updated_pm, pm_count = _batch_update_memory(pm_sheet, pig_updates)
col_status = pm_headers.index("Status")
col_onfarm = pm_headers.index("On_Farm")
col_exit   = pm_headers.index("Exit_Order_ID")

check("pm batch returns count 20", pm_count == 20)
check("all 20 pigs Status=Sold",  all(r[col_status] == "Sold" for r in updated_pm[1:]))
check("all 20 pigs On_Farm=No",   all(r[col_onfarm] == "No"   for r in updated_pm[1:]))
check("Exit_Order_ID set",        all(r[col_exit]   == ORDER_ID for r in updated_pm[1:]))


# ── TEST 4: validation — rejects non-Approved statuses ───────────────────────
print("\nTEST 4: Validation — rejects non-Approved order statuses")

for bad_status in ("Draft", "Pending_Approval", "Completed", "Cancelled"):
    check_raises(f"{bad_status} order rejected",
                 _validate, {"Order_Status": bad_status}, ol_headers, ol_rows, ORDER_ID)


# ── TEST 5: validation — rejects lines with no Pig_ID ────────────────────────
print("\nTEST 5: Validation — rejects lines missing Pig_ID")

bad_h = ["Order_Line_ID", "Order_ID", "Pig_ID", "Line_Status"]
bad_r = [["OL-2026-00001", ORDER_ID, "PIG-001", "Reserved"],
         ["OL-2026-00002", ORDER_ID, "",        "Reserved"]]
check_raises("line with no Pig_ID raises error",
             _validate, {"Order_Status": "Approved"}, bad_h, bad_r, ORDER_ID)


# ── TEST 6: validation — rejects order with only cancelled lines ──────────────
print("\nTEST 6: Validation — only cancelled lines raises error")

cancelled_h = ["Order_Line_ID", "Order_ID", "Pig_ID", "Line_Status"]
cancelled_r = [["OL-2026-00001", ORDER_ID, "PIG-001", "Cancelled"],
               ["OL-2026-00002", ORDER_ID, "PIG-002", "Cancelled"]]
check_raises("all-cancelled order raises error",
             _validate, {"Order_Status": "Approved"}, cancelled_h, cancelled_r, ORDER_ID)


# ── TEST 7: batch — unknown ID raises clearly ─────────────────────────────────
print("\nTEST 7: batch update — unknown ID raises ValueError")

check_raises("unknown line ID raises ValueError",
             _batch_update_memory, ol_sheet, {"OL-9999-FAKE": {"Line_Status": "Collected"}})


# ── TEST 8: empty updates_map is a safe no-op ─────────────────────────────────
print("\nTEST 8: empty updates_map is a safe no-op")

original = [list(r) for r in ol_sheet]
result, count = _batch_update_memory(ol_sheet, {})
check("count is 0", count == 0)
check("rows unchanged", result == original)


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
