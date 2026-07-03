import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from modules.pig_weights.pig_weights_utils import generate_move_log_id, generate_weight_log_id
from services.database_service import DATABASE_URL_ENV


def load_local_env():
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#") or "=" not in clean:
            continue
        key, value = clean.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def connect():
    load_local_env()
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if not database_url:
        raise RuntimeError(f"{DATABASE_URL_ENV} is not configured.")
    import psycopg

    return psycopg.connect(database_url, connect_timeout=10)


def fetch_dicts(cursor):
    columns = [column.name for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def correction_note(batch_id, from_date, to_date):
    return f"Corrected bulk upload date from {from_date} to {to_date}; source batch {batch_id}."


def load_batch(cursor, batch_id):
    cursor.execute(
        """
        select batch_id::text, weight_date::text, status, visible_row_count, actionable_row_count,
            weight_row_count, movement_row_count, skipped_row_count, success_count, failed_count,
            duplicate_count, source, notes, error_summary, created_at::text, updated_at::text
        from public.bulk_weight_batches
        where batch_id = %s::uuid
        """,
        (batch_id,),
    )
    rows = fetch_dicts(cursor)
    if not rows:
        raise RuntimeError(f"Bulk batch {batch_id} was not found.")
    return rows[0]


def load_rows(cursor, batch_id):
    cursor.execute(
        """
        select row_id::text, batch_id::text, row_index, pig_id, pig_name, weight_kg,
            from_pen_id, to_pen_id, movement_type, status, status_reason, processed_at::text,
            result_json, original_row_json
        from public.bulk_weight_batch_rows
        where batch_id = %s::uuid
        order by row_index
        """,
        (batch_id,),
    )
    return fetch_dicts(cursor)


def has_weight(row):
    result_json = row.get("result_json") or {}
    return bool(result_json.get("has_weight") and row.get("pig_id") and row.get("weight_kg") is not None)


def has_pen_change(row):
    result_json = row.get("result_json") or {}
    return bool(result_json.get("has_pen_change") and row.get("pig_id") and row.get("to_pen_id"))


def existing_weight(cursor, pig_id, weight_date):
    cursor.execute(
        """
        select weight_event_id, weight_kg, bulk_batch_id::text, bulk_row_id::text, source
        from public.pig_weight_events
        where pig_id = %s and weight_date = %s::date
        order by created_at desc nulls last
        limit 1
        """,
        (pig_id, weight_date),
    )
    rows = fetch_dicts(cursor)
    return rows[0] if rows else None


def existing_move(cursor, pig_id, move_date, from_pen_id, to_pen_id):
    cursor.execute(
        """
        select location_event_id, bulk_batch_id::text, bulk_row_id::text, source
        from public.pig_location_events
        where pig_id = %s
            and move_date = %s::date
            and coalesce(from_pen_id, '') = coalesce(%s, '')
            and coalesce(to_pen_id, '') = coalesce(%s, '')
        order by created_at desc nulls last
        limit 1
        """,
        (pig_id, move_date, from_pen_id, to_pen_id),
    )
    rows = fetch_dicts(cursor)
    return rows[0] if rows else None


def wrong_date_moves(cursor, batch_id, from_date):
    cursor.execute(
        """
        select location_event_id, pig_id, move_date::text, from_pen_id, to_pen_id, bulk_row_id::text
        from public.pig_location_events
        where bulk_batch_id = %s::uuid and move_date = %s::date
        order by created_at
        """,
        (batch_id, from_date),
    )
    return fetch_dicts(cursor)


def wrong_date_weights(cursor, batch_id, from_date):
    cursor.execute(
        """
        select weight_event_id, pig_id, weight_date::text, weight_kg, bulk_row_id::text
        from public.pig_weight_events
        where bulk_batch_id = %s::uuid and weight_date = %s::date
        order by created_at
        """,
        (batch_id, from_date),
    )
    return fetch_dicts(cursor)


def build_plan(cursor, batch_id, from_date, to_date):
    batch = load_batch(cursor, batch_id)
    rows = load_rows(cursor, batch_id)
    weight_rows = [row for row in rows if has_weight(row)]
    movement_rows = [row for row in rows if has_pen_change(row)]

    weights_to_insert = []
    weights_existing_target = []
    for row in weight_rows:
        existing = existing_weight(cursor, row["pig_id"], to_date)
        if existing:
            weights_existing_target.append({"row": row, "existing": existing})
        else:
            weights_to_insert.append(row)

    moves_to_insert = []
    moves_existing_target = []
    for row in movement_rows:
        existing = existing_move(cursor, row["pig_id"], to_date, row.get("from_pen_id"), row.get("to_pen_id"))
        if existing:
            moves_existing_target.append({"row": row, "existing": existing})
        else:
            moves_to_insert.append(row)

    return {
        "batch": batch,
        "rows": rows,
        "weight_rows": weight_rows,
        "movement_rows": movement_rows,
        "weights_to_insert": weights_to_insert,
        "weights_existing_target": weights_existing_target,
        "moves_to_insert": moves_to_insert,
        "moves_existing_target": moves_existing_target,
        "wrong_date_weights": wrong_date_weights(cursor, batch_id, from_date),
        "wrong_date_moves": wrong_date_moves(cursor, batch_id, from_date),
    }


def apply_plan(cursor, plan, batch_id, from_date, to_date):
    note = correction_note(batch_id, from_date, to_date)
    corrected_status_reason = f"Corrected to target date {to_date}."
    now = datetime.now(timezone.utc)
    inserted_weights = 0
    inserted_moves = 0
    updated_wrong_moves = 0
    updated_wrong_weights = 0

    for row in plan["weights_to_insert"]:
        preflight = (row.get("result_json") or {}).get("preflight") or {}
        cursor.execute(
            """
            insert into public.pig_weight_events (
                weight_event_id, pig_id, weight_date, weight_kg, weighed_by,
                condition_notes, source, bulk_batch_id, bulk_row_id, created_at
            ) values (
                %(weight_event_id)s, %(pig_id)s, %(weight_date)s::date, %(weight_kg)s, %(weighed_by)s,
                %(condition_notes)s, 'app_bulk_weight_date_correction', %(bulk_batch_id)s::uuid,
                %(bulk_row_id)s::uuid, %(created_at)s
            )
            """,
            {
                "weight_event_id": generate_weight_log_id(),
                "pig_id": row["pig_id"],
                "weight_date": to_date,
                "weight_kg": row["weight_kg"],
                "weighed_by": preflight.get("weighed_by", "WebApp"),
                "condition_notes": " ".join(
                    item for item in [str(preflight.get("condition_notes") or "").strip(), note] if item
                ),
                "bulk_batch_id": batch_id,
                "bulk_row_id": row["row_id"],
                "created_at": now,
            },
        )
        inserted_weights += 1

    wrong_moves_by_row = {item["bulk_row_id"]: item for item in plan["wrong_date_moves"]}
    for wrong in plan["wrong_date_moves"]:
        if existing_move(cursor, wrong["pig_id"], to_date, wrong.get("from_pen_id"), wrong.get("to_pen_id")):
            continue
        cursor.execute(
            """
            update public.pig_location_events
            set move_date = %s::date,
                move_notes = concat_ws(E'\n', nullif(move_notes, ''), %s::text)
            where location_event_id = %s
            """,
            (to_date, note, wrong["location_event_id"]),
        )
        updated_wrong_moves += cursor.rowcount

    for row in plan["moves_to_insert"]:
        if row["row_id"] in wrong_moves_by_row:
            continue
        preflight = (row.get("result_json") or {}).get("preflight") or {}
        if existing_move(cursor, row["pig_id"], to_date, row.get("from_pen_id"), row.get("to_pen_id")):
            continue
        cursor.execute(
            """
            insert into public.pig_location_events (
                location_event_id, pig_id, move_date, from_pen_id, to_pen_id,
                reason_for_move, moved_by, move_notes, source, bulk_batch_id, bulk_row_id, created_at
            ) values (
                %(location_event_id)s, %(pig_id)s, %(move_date)s::date, %(from_pen_id)s, %(to_pen_id)s,
                'Moved during corrected durable bulk capture', 'WebApp', %(move_notes)s,
                'app_bulk_weight_date_correction', %(bulk_batch_id)s::uuid, %(bulk_row_id)s::uuid, %(created_at)s
            )
            """,
            {
                "location_event_id": generate_move_log_id(),
                "pig_id": row["pig_id"],
                "move_date": to_date,
                "from_pen_id": row.get("from_pen_id") or None,
                "to_pen_id": row.get("to_pen_id") or None,
                "move_notes": " ".join(
                    item for item in [str(preflight.get("condition_notes") or "").strip(), note] if item
                ),
                "bulk_batch_id": batch_id,
                "bulk_row_id": row["row_id"],
                "created_at": now,
            },
        )
        inserted_moves += 1

    for wrong in plan["wrong_date_weights"]:
        if existing_weight(cursor, wrong["pig_id"], to_date):
            continue
        cursor.execute(
            """
            update public.pig_weight_events
            set weight_date = %s::date,
                condition_notes = concat_ws(E'\n', nullif(condition_notes, ''), %s::text)
            where weight_event_id = %s
            """,
            (to_date, note, wrong["weight_event_id"]),
        )
        updated_wrong_weights += cursor.rowcount

    cursor.execute(
        """
        update public.bulk_weight_batch_rows
        set status = case when status in ('staged', 'processing') then 'success' else status end,
            status_reason = case
                when status in ('staged', 'processing') then %s::text
                else status_reason
            end,
            processed_at = coalesce(processed_at, now()),
            updated_at = now()
        where batch_id = %s::uuid
            and status in ('staged', 'processing')
        """,
        (corrected_status_reason, batch_id),
    )
    corrected_batch_rows = cursor.rowcount

    cursor.execute(
        """
        update public.bulk_weight_batches
        set status = 'complete',
            notes = concat_ws(E'\n', nullif(notes, ''), %s::text),
            error_summary = '',
            success_count = (
                select count(*) from public.bulk_weight_batch_rows
                where batch_id = %s::uuid and status = 'success'
            ),
            failed_count = (
                select count(*) from public.bulk_weight_batch_rows
                where batch_id = %s::uuid and status = 'failed'
            ),
            duplicate_count = (
                select count(*) from public.bulk_weight_batch_rows
                where batch_id = %s::uuid and status = 'duplicate'
            ),
            skipped_row_count = (
                select count(*) from public.bulk_weight_batch_rows
                where batch_id = %s::uuid and status = 'skipped'
            ),
            updated_at = now(),
            completed_at = now()
        where batch_id = %s::uuid
        """,
        (note, batch_id, batch_id, batch_id, batch_id, batch_id),
    )

    return {
        "inserted_weights": inserted_weights,
        "inserted_moves": inserted_moves,
        "updated_wrong_moves": updated_wrong_moves,
        "updated_wrong_weights": updated_wrong_weights,
        "corrected_batch_rows": corrected_batch_rows,
    }


def summarize(cursor, batch_id, from_date, to_date, plan):
    cursor.execute(
        """
        select count(*) as count
        from public.pig_weight_events
        where bulk_batch_id = %s::uuid and weight_date = %s::date
        """,
        (batch_id, to_date),
    )
    target_weights = fetch_dicts(cursor)[0]["count"]
    cursor.execute(
        """
        select count(*) as count
        from public.pig_location_events
        where bulk_batch_id = %s::uuid and move_date = %s::date
        """,
        (batch_id, to_date),
    )
    target_moves = fetch_dicts(cursor)[0]["count"]
    cursor.execute(
        """
        select count(distinct bulk_row_id) as count
        from public.pig_weight_events
        where bulk_batch_id = %s::uuid and weight_date = %s::date
        """,
        (batch_id, to_date),
    )
    target_weight_rows = fetch_dicts(cursor)[0]["count"]
    cursor.execute(
        """
        select count(distinct bulk_row_id) as count
        from public.pig_location_events
        where bulk_batch_id = %s::uuid and move_date = %s::date
        """,
        (batch_id, to_date),
    )
    target_move_rows = fetch_dicts(cursor)[0]["count"]
    cursor.execute(
        """
        select row.row_index, row.pig_id, row.weight_kg
        from public.bulk_weight_batch_rows row
        where row.batch_id = %s::uuid
            and row.weight_kg is not null
            and not exists (
                select 1
                from public.pig_weight_events event
                where event.bulk_row_id = row.row_id
                    and event.weight_date = %s::date
            )
        order by row.row_index
        limit 20
        """,
        (batch_id, to_date),
    )
    missing_weight_rows = fetch_dicts(cursor)
    cursor.execute(
        """
        select row.row_index, row.pig_id, row.from_pen_id, row.to_pen_id
        from public.bulk_weight_batch_rows row
        where row.batch_id = %s::uuid
            and coalesce(row.to_pen_id, '') <> ''
            and coalesce(row.to_pen_id, '') <> coalesce(row.from_pen_id, '')
            and not exists (
                select 1
                from public.pig_location_events event
                where event.bulk_row_id = row.row_id
                    and event.move_date = %s::date
            )
        order by row.row_index
        limit 20
        """,
        (batch_id, to_date),
    )
    missing_move_rows = fetch_dicts(cursor)
    return {
        "batch_id": batch_id,
        "from_date": from_date,
        "to_date": to_date,
        "batch_status": load_batch(cursor, batch_id)["status"],
        "batch_weight_rows": len(plan["weight_rows"]),
        "batch_movement_rows": len(plan["movement_rows"]),
        "wrong_date_weights_before": len(plan["wrong_date_weights"]),
        "wrong_date_moves_before": len(plan["wrong_date_moves"]),
        "target_weight_events_for_batch": target_weights,
        "target_move_events_for_batch": target_moves,
        "target_weight_batch_rows": target_weight_rows,
        "target_move_batch_rows": target_move_rows,
        "missing_weight_batch_rows": missing_weight_rows,
        "missing_move_batch_rows": missing_move_rows,
        "weights_to_insert": len(plan["weights_to_insert"]),
        "moves_to_insert_or_correct": len(plan["moves_to_insert"]),
        "weights_already_on_target": len(plan["weights_existing_target"]),
        "moves_already_on_target": len(plan["moves_existing_target"]),
    }


def main():
    parser = argparse.ArgumentParser(description="Correct a bulk weight batch captured against the wrong date.")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    with connect() as connection:
        with connection.cursor() as cursor:
            plan = build_plan(cursor, args.batch_id, args.from_date, args.to_date)
            before = summarize(cursor, args.batch_id, args.from_date, args.to_date, plan)
            result = {"mode": "apply" if args.apply else "dry_run", "before": before}
            if args.apply:
                result["applied"] = apply_plan(cursor, plan, args.batch_id, args.from_date, args.to_date)
                after_plan = build_plan(cursor, args.batch_id, args.from_date, args.to_date)
                result["after"] = summarize(cursor, args.batch_id, args.from_date, args.to_date, after_plan)
            else:
                result["sample_weight_rows"] = [
                    {"row_index": row["row_index"], "pig_id": row["pig_id"], "weight_kg": str(row["weight_kg"])}
                    for row in plan["weights_to_insert"][:10]
                ]
                result["sample_move_rows"] = [
                    {
                        "row_index": row["row_index"],
                        "pig_id": row["pig_id"],
                        "from_pen_id": row.get("from_pen_id"),
                        "to_pen_id": row.get("to_pen_id"),
                    }
                    for row in plan["moves_to_insert"][:10]
                ]
            print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
