import argparse
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from services.database_service import DATABASE_URL_ENV


LITTER_ID = "LIT-2026-322B"
WEAN_DATE = date(2026, 7, 27)
TARGET_PEN_ID = "PEN-012"
WEIGHTS = {
    "131": 6.6, "132": 5.2, "133": 7.8, "134": 7.2, "135": 6.2,
    "136": 6.8, "137": 7.2, "138": 6.6, "139": 7.4, "140": 5.8,
}
PRODUCT_IDS = ("PRD-001", "PRD-002")


def stable_id(prefix, *parts):
    digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:8].upper()
    return f"{prefix}-{digest}"


def fetchall(cursor, sql, params=()):
    cursor.execute(sql, params)
    columns = [column.name for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def recover(database_url, apply=False):
    if apply:
        raise RuntimeError(
            "LIT-2026-322B recovery is complete; production apply is permanently disabled."
        )
    import psycopg

    with psycopg.connect(database_url, connect_timeout=10) as connection:
        connection.autocommit = False
        with connection.cursor() as cursor:
            cursor.execute("set local statement_timeout = '20s'")
            pigs = fetchall(
                cursor,
                """
                select pig.pig_id, pig.tag_number, pig.status, pig.on_farm, pig.animal_type,
                       pig.wean_date, pig.wean_weight_kg, state.current_pen_id
                from public.pigs pig
                join public.pig_current_state state on state.pig_id = pig.pig_id
                where pig.litter_id = %s
                order by pig.tag_number::integer
                for update of pig
                """,
                (LITTER_ID,),
            )
            if len(pigs) != 10:
                raise RuntimeError(f"Expected 10 litter pigs; found {len(pigs)}.")
            tags = [str(row["tag_number"]) for row in pigs]
            if tags != list(WEIGHTS):
                raise RuntimeError(f"Tag identity mismatch: {tags}.")
            for row in pigs:
                if row["status"] != "Active" or row["on_farm"] is not True:
                    raise RuntimeError(f"Pig {row['tag_number']} is no longer active on farm.")
                if row["wean_date"] not in (None, WEAN_DATE):
                    raise RuntimeError(f"Conflicting wean date for tag {row['tag_number']}.")
                expected_weight = WEIGHTS[str(row["tag_number"])]
                if row["wean_weight_kg"] is not None and float(row["wean_weight_kg"]) != expected_weight:
                    raise RuntimeError(f"Conflicting wean weight for tag {row['tag_number']}.")
                if row["current_pen_id"] not in ("PEN-009", TARGET_PEN_ID):
                    raise RuntimeError(f"Conflicting pen for tag {row['tag_number']}.")

            cursor.execute(
                "select wean_date, weaned_count, litter_status from public.litters where litter_id=%s for update",
                (LITTER_ID,),
            )
            litter = cursor.fetchone()
            if not litter:
                raise RuntimeError("Litter row is missing.")
            if litter[0] not in (None, WEAN_DATE) or litter[1] not in (None, 0, 10):
                raise RuntimeError("Litter already contains conflicting weaning facts.")

            treatments = fetchall(
                cursor,
                """
                select event.*, pig.tag_number
                from public.pig_medical_events event
                join public.pigs pig on pig.pig_id=event.pig_id
                where pig.litter_id=%s and event.treatment_date=%s
                  and event.product_id=any(%s)
                order by pig.tag_number::integer, event.product_id
                """,
                (LITTER_ID, WEAN_DATE, list(PRODUCT_IDS)),
            )
            observed = {(str(row["tag_number"]), row["product_id"]) for row in treatments}
            expected = {(tag, product_id) for tag in WEIGHTS for product_id in PRODUCT_IDS}
            if not observed.issubset(expected):
                raise RuntimeError("Unexpected treatment identity exists.")
            if len(treatments) != len(observed):
                raise RuntimeError("Duplicate treatment facts already exist.")
            if len(observed) not in (17, 20):
                raise RuntimeError(f"Expected the partial 17 or complete 20 treatment facts; found {len(observed)}.")
            templates = {}
            for row in treatments:
                templates.setdefault(row["product_id"], row)
            if set(templates) != set(PRODUCT_IDS):
                raise RuntimeError("Treatment templates are incomplete.")

            existing_weights = fetchall(
                cursor,
                """
                select event.*, pig.tag_number
                from public.pig_weight_events event
                join public.pigs pig on pig.pig_id=event.pig_id
                where pig.litter_id=%s and event.weight_date=%s
                """,
                (LITTER_ID, WEAN_DATE),
            )
            for row in existing_weights:
                tag = str(row["tag_number"])
                if tag not in WEIGHTS or float(row["weight_kg"]) != WEIGHTS[tag]:
                    raise RuntimeError(f"Conflicting weight event exists for tag {tag}.")
            existing_movements = fetchall(
                cursor,
                """
                select event.*, pig.tag_number
                from public.pig_location_events event
                join public.pigs pig on pig.pig_id=event.pig_id
                where pig.litter_id=%s and event.move_date=%s
                  and event.from_pen_id='PEN-009' and event.to_pen_id=%s
                """,
                (LITTER_ID, WEAN_DATE, TARGET_PEN_ID),
            )

            pig_by_tag = {str(row["tag_number"]): row for row in pigs}
            missing_treatments = sorted(expected - observed)
            summary = {
                "litter_id": LITTER_ID,
                "mode": "apply" if apply else "preflight",
                "piglets": 10,
                "existing_treatments": len(observed),
                "missing_treatments": missing_treatments,
                "existing_matching_weights": len(existing_weights),
                "existing_matching_movements": len(existing_movements),
                "target_pen": TARGET_PEN_ID,
                "wean_date": WEAN_DATE.isoformat(),
                "piglets_weaned": sum(
                    1 for row in pigs
                    if row["wean_date"] == WEAN_DATE
                    and row["animal_type"] == "Weaner"
                    and float(row["wean_weight_kg"]) == WEIGHTS[str(row["tag_number"])]
                ),
                "piglets_in_target_pen": sum(1 for row in pigs if row["current_pen_id"] == TARGET_PEN_ID),
                "litter_weaned": (
                    litter[0] == WEAN_DATE
                    and litter[1] == 10
                    and litter[2] == "Weaned"
                ),
            }
            if not apply:
                connection.rollback()
                return summary

            for tag, product_id in missing_treatments:
                template = templates[product_id]
                cursor.execute(
                    """
                    insert into public.pig_medical_events (
                        medical_event_id, pig_id, treatment_date, treatment_type, product_id,
                        product_name, dose, dose_unit, route, reason_for_treatment,
                        batch_lot_number, withdrawal_days, withdrawal_end_date, given_by,
                        follow_up_required, follow_up_date, medical_notes
                    ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        stable_id("MED", LITTER_ID, tag, product_id, WEAN_DATE),
                        pig_by_tag[tag]["pig_id"], WEAN_DATE, template["treatment_type"], product_id,
                        template["product_name"], template["dose"], template["dose_unit"],
                        template["route"], template["reason_for_treatment"],
                        template["batch_lot_number"], template["withdrawal_days"],
                        template["withdrawal_end_date"], template["given_by"],
                        template["follow_up_required"], template["follow_up_date"],
                        template["medical_notes"],
                    ),
                )

            existing_weight_tags = {str(row["tag_number"]) for row in existing_weights}
            for tag, weight in WEIGHTS.items():
                pig_id = pig_by_tag[tag]["pig_id"]
                if tag not in existing_weight_tags:
                    cursor.execute(
                        """
                        insert into public.pig_weight_events (
                            weight_event_id, pig_id, weight_date, weight_kg, weighed_by,
                            condition_notes, source, created_at
                        ) values (%s,%s,%s,%s,%s,%s,%s,now())
                        """,
                        (
                            stable_id("WGT", LITTER_ID, tag, WEAN_DATE), pig_id, WEAN_DATE, weight,
                            "Charl", "Weaning day weight recovered from owner-confirmed form.",
                            "litter_weaning_recovery",
                        ),
                    )
                if pig_by_tag[tag]["current_pen_id"] == "PEN-009":
                    cursor.execute(
                        """
                        insert into public.pig_location_events (
                            location_event_id, pig_id, move_date, from_pen_id, to_pen_id,
                            reason_for_move, moved_by, move_notes, source, created_at
                        ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                        on conflict do nothing
                        """,
                        (
                            stable_id("MOV", LITTER_ID, tag, WEAN_DATE), pig_id, WEAN_DATE,
                            "PEN-009", TARGET_PEN_ID, "Weaning day move", "Charl",
                            "Recovered from owner-confirmed weaning-day form.",
                            "litter_weaning_recovery",
                        ),
                    )
                cursor.execute(
                    """
                    update public.pigs
                    set animal_type='Weaner', litter_size_weaned=10, wean_date=%s,
                        wean_weight_kg=%s, updated_at=now()
                    where pig_id=%s
                    """,
                    (WEAN_DATE, weight, pig_id),
                )

            cursor.execute(
                """
                update public.litters
                set weaned_count=10, wean_date=%s, litter_status='Weaned', updated_at=now()
                where litter_id=%s
                """,
                (WEAN_DATE, LITTER_ID),
            )
        connection.commit()
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    load_dotenv(Path(args.env_file), override=False)
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if not database_url:
        raise SystemExit(f"{DATABASE_URL_ENV} is not configured.")
    print(json.dumps(recover(database_url, apply=args.apply), indent=2, default=str))


if __name__ == "__main__":
    main()
