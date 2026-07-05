# Gold Standard Example: Litter Summary Timing Data

Status: active reference example.

Source mission: `D1B8DA42` / PR `#89`.

Source commit: `e2b27fc52246459ef69e77e75ed9b6e7d89a6797`.

Example type: focused data-backed product improvement.

## Why This Is A Good Example

This mission is a useful standard because it changed a narrow owner-visible behavior, kept the implementation inside the existing read-service boundary, and added focused regression tests before release.

The result was not a cosmetic rewrite. It improved the truth shown to the owner by exposing known litter summary timing data from the canonical farm data path.

## Files Changed

- `modules/pig_weights/farm_supabase_read_service.py`
- `tests/test_farm_supabase_read_service.py`

## Pattern To Reuse

When a mission asks for a small data-backed UI/product improvement:

1. Find the existing read/write service boundary before touching templates or dashboard rendering.
2. Confirm which table or service already owns the truth.
3. Add the smallest data shape required by the UI.
4. Preserve existing fields and behavior.
5. Add tests proving the new field is populated and existing summary behavior still works.
6. Provide owner review evidence with changed files, test evidence, PR link, and local/Render verification when relevant.

## Quality Bar

Agents may treat a mission as similar to this example only when:

- the requested behavior is narrow and data-backed;
- the implementation uses an existing service boundary;
- the changed files are easy to inspect;
- tests prove the new output;
- no unrelated refactor is mixed into the delivery;
- review evidence names the exact behavior changed.

## Anti-Pattern To Avoid

Do not respond to a small data-backed request by rebuilding the dashboard, changing broad layout, inventing new data sources, or producing only screenshots without tests.

Do not mark review-ready if the changed behavior cannot be verified from tests or a live page/API check.
