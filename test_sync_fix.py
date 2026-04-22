"""
Focused unit tests for the split-item re-sync bug fix.

Tests _get_matching_available_pigs and the own_pig_ids logic
without requiring Google Sheets credentials.

Run with: python test_sync_fix.py
"""

# ── Inline copies of the helpers under test ──────────────────────────────────
# We duplicate only the two functions we're testing so we don't need the full
# Google Sheets service stack to be configured.

def to_clean_string(value):
    if value is None:
        return ""
    return str(value).strip()


def _sales_categories_for_request(category: str):
    mapping = {
        "Piglet":   ["Young Piglets"],
        "Weaner":   ["Weaner Piglets"],
        "Grower":   ["Grower Pigs"],
        "Finisher": ["Finisher Pigs"],
        "Slaughter":["Ready for Slaughter"],
        "Young Piglets":       ["Young Piglets"],
        "Weaner Piglets":      ["Weaner Piglets"],
        "Grower Pigs":         ["Grower Pigs"],
        "Finisher Pigs":       ["Finisher Pigs"],
        "Ready for Slaughter": ["Ready for Slaughter"],
    }
    return mapping.get(to_clean_string(category), [to_clean_string(category)])


def _get_matching_available_pigs(
    sales_rows, blocked_pig_ids, category: str, weight_range: str, sex: str,
    own_pig_ids: set = None
):
    own_pig_ids = own_pig_ids or set()
    target_categories = _sales_categories_for_request(category)
    matches = []

    for row in sales_rows:
        if to_clean_string(row.get("Available_For_Sale", "")) != "Yes":
            continue

        row_pig_id = to_clean_string(row.get("Pig_ID", ""))

        if to_clean_string(row.get("Reserved_Status", "")) == "Reserved":
            if row_pig_id not in own_pig_ids:
                continue

        row_sale_category = to_clean_string(row.get("Sale_Category", ""))
        row_weight_band   = to_clean_string(row.get("Weight_Band", ""))
        row_sex           = to_clean_string(row.get("Sex", ""))

        if row_sale_category not in target_categories:
            continue
        if row_weight_band != to_clean_string(weight_range):
            continue
        if sex and sex != "Any" and row_sex != sex:
            continue
        if row_pig_id in blocked_pig_ids:
            continue

        matches.append({
            "pig_id":           row_pig_id,
            "tag_number":       to_clean_string(row.get("Tag_Number", "")),
            "sex":              row_sex,
            "current_weight_kg": row.get("Current_Weight_Kg"),
            "weight_band":      row_weight_band,
            "sale_category":    row_sale_category,
        })

    return sorted(matches, key=lambda x: (
        (x["tag_number"] or "").lower(), (x["pig_id"] or "").lower()
    ))


# ── Test helpers ─────────────────────────────────────────────────────────────

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
results = []

def check(name, condition):
    status = PASS if condition else FAIL
    print(f"  [{status}] {name}")
    results.append(condition)


# ── Sample SALES_AVAILABILITY rows ───────────────────────────────────────────

def make_pig(pig_id, sex, reserved="Available", available="Yes",
             category="Grower Pigs", band="20_to_24_Kg"):
    return {
        "Pig_ID":            pig_id,
        "Tag_Number":        pig_id,
        "Sex":               sex,
        "Sale_Category":     category,
        "Weight_Band":       band,
        "Available_For_Sale": available,
        "Reserved_Status":   reserved,
        "Current_Weight_Kg": 22.0,
    }

SALES_ROWS = [
    make_pig("M1", "Male"),
    make_pig("M2", "Male"),
    make_pig("M3", "Male"),
    make_pig("F1", "Female"),
    make_pig("F2", "Female"),
    make_pig("F3", "Female"),
]


# ── TEST 1: Basic matching, no reservations ───────────────────────────────────
print("\nTEST 1: Basic matching — no reservations")

males   = _get_matching_available_pigs(SALES_ROWS, set(), "Grower Pigs", "20_to_24_Kg", "Male")
females = _get_matching_available_pigs(SALES_ROWS, set(), "Grower Pigs", "20_to_24_Kg", "Female")

check("finds 3 males",   len(males)   == 3)
check("finds 3 females", len(females) == 3)


# ── TEST 2: After reserve — without fix, females return 0 ─────────────────────
print("\nTEST 2: After reserve — old behaviour (no own_pig_ids)")

# Simulate: F1 and F2 were reserved for primary_02 in a previous sync
reserved_rows = [
    make_pig("M1", "Male",   reserved="Available"),
    make_pig("M2", "Male",   reserved="Available"),
    make_pig("M3", "Male",   reserved="Available"),
    make_pig("F1", "Female", reserved="Reserved"),   # reserved for this order
    make_pig("F2", "Female", reserved="Reserved"),   # reserved for this order
    make_pig("F3", "Female", reserved="Available"),
]

females_no_fix = _get_matching_available_pigs(
    reserved_rows, set(), "Grower Pigs", "20_to_24_Kg", "Female"
    # no own_pig_ids → old behaviour
)
check("without fix: only non-reserved females returned (1)", len(females_no_fix) == 1)
check("without fix: F1 and F2 excluded",
      all(p["pig_id"] not in ("F1", "F2") for p in females_no_fix))


# ── TEST 3: After reserve — WITH fix (own_pig_ids) ────────────────────────────
print("\nTEST 3: After reserve — WITH fix (own_pig_ids passed)")

own_pig_ids = {"F1", "F2"}   # pigs already on primary_02's active lines

females_fixed = _get_matching_available_pigs(
    reserved_rows, set(), "Grower Pigs", "20_to_24_Kg", "Female",
    own_pig_ids=own_pig_ids
)
check("with fix: 3 females returned (F1, F2, F3)", len(females_fixed) == 3)
check("with fix: F1 included", any(p["pig_id"] == "F1" for p in females_fixed))
check("with fix: F2 included", any(p["pig_id"] == "F2" for p in females_fixed))
check("with fix: F3 included", any(p["pig_id"] == "F3" for p in females_fixed))


# ── TEST 4: own_pig_ids does NOT bypass blocked_pig_ids ───────────────────────
print("\nTEST 4: own_pig_ids does NOT override blocked_pig_ids")

# F1 is own AND blocked — it must still be excluded
females_blocked = _get_matching_available_pigs(
    reserved_rows,
    blocked_pig_ids={"F1"},   # F1 is blocked (used by another item)
    category="Grower Pigs", weight_range="20_to_24_Kg", sex="Female",
    own_pig_ids={"F1", "F2"}
)
check("F1 excluded (in blocked_pig_ids even though own)",
      all(p["pig_id"] != "F1" for p in females_blocked))
check("F2 still included (own but not blocked)",
      any(p["pig_id"] == "F2" for p in females_blocked))


# ── TEST 5: Split-order scenario end-to-end simulation ───────────────────────
print("\nTEST 5: Split-order re-sync simulation")

# State: primary_01 already synced (M1, M2 reserved), primary_02 already synced
# (F1, F2 reserved). Re-sync called. sales_rows fetched BEFORE cancellation.
split_sales_rows = [
    make_pig("M1", "Male",   reserved="Reserved"),  # reserved for primary_01
    make_pig("M2", "Male",   reserved="Reserved"),  # reserved for primary_01
    make_pig("M3", "Male",   reserved="Available"),
    make_pig("F1", "Female", reserved="Reserved"),  # reserved for primary_02
    make_pig("F2", "Female", reserved="Reserved"),  # reserved for primary_02
    make_pig("F3", "Female", reserved="Available"),
]

# primary_01 processing: own = {M1, M2}, blocked = {F1, F2} (from primary_02)
p01_own = {"M1", "M2"}
p01_blocked = {"F1", "F2"}
males_resync = _get_matching_available_pigs(
    split_sales_rows, p01_blocked, "Grower Pigs", "20_to_24_Kg", "Male",
    own_pig_ids=p01_own
)
check("primary_01 re-sync: finds 3 males (M1, M2 own + M3 available)",
      len(males_resync) == 3)

# primary_02 processing: own = {F1, F2}, blocked = {M1, M2} (from primary_01 new lines)
p02_own = {"F1", "F2"}
p02_blocked = {"M1", "M2"}
females_resync = _get_matching_available_pigs(
    split_sales_rows, p02_blocked, "Grower Pigs", "20_to_24_Kg", "Female",
    own_pig_ids=p02_own
)
check("primary_02 re-sync: finds 3 females (F1, F2 own + F3 available)",
      len(females_resync) == 3)
check("primary_02 re-sync: F1 included", any(p["pig_id"] == "F1" for p in females_resync))
check("primary_02 re-sync: F2 included", any(p["pig_id"] == "F2" for p in females_resync))


# ── TEST 6: empty own_pig_ids defaults safely ─────────────────────────────────
print("\nTEST 6: own_pig_ids defaults (None and empty set)")

r1 = _get_matching_available_pigs(SALES_ROWS, set(), "Grower Pigs", "20_to_24_Kg", "Male", own_pig_ids=None)
r2 = _get_matching_available_pigs(SALES_ROWS, set(), "Grower Pigs", "20_to_24_Kg", "Male", own_pig_ids=set())
r3 = _get_matching_available_pigs(SALES_ROWS, set(), "Grower Pigs", "20_to_24_Kg", "Male")

check("None, set(), and omitted all return 3 males",
      len(r1) == len(r2) == len(r3) == 3)


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
