"""Read-only canonical audit for ROOTLINE Recovery Slot 2."""
from __future__ import annotations
import json, os
import psycopg


def main():
    database_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL is not configured")
    result = {}
    with psycopg.connect(database_url, connect_timeout=10,
            options="-c default_transaction_read_only=on") as connection:
        with connection.cursor() as cursor:
            def rows(sql, args=()):
                cursor.execute(sql, args)
                names = [column.name for column in cursor.description]
                return [dict(zip(names, row)) for row in cursor.fetchall()]
            result["current_plan"] = rows("""select i.plan_id,i.operating_date,
                i.current_generation,g.evidence_sha256,g.evidence_observed_at,
                g.plan_json->'candidate_tasks' candidate_tasks
                from public.rootline_water_energy_plan_identities i
                join public.rootline_water_energy_plan_generations g
                  on g.plan_id=i.plan_id and g.generation=i.current_generation
                where i.operating_date=(now() at time zone 'Africa/Johannesburg')::date""")
            result["tank_observations"] = rows("""select observation_id,observed_at,
                storage_state,reservoir_state,storage_fraction_numerator,
                storage_fraction_denominator,reservoir_fraction_numerator,
                reservoir_fraction_denominator,provider_message_id,source
                from public.rootline_tank_observations order by observed_at desc limit 10""")
            result["physical_acceptance"] = rows("""select review_event_id,created_at,
                review_json->'rootline_physical_acceptance' payload
                from public.sam_live_stock_conversation_review_events
                where event_source='rootline_physical_acceptance'
                order by created_at desc limit 10""")
            result["manager_question"] = rows("""select review_event_id,created_at,
                review_json->'manager_question_reply' payload
                from public.sam_live_stock_conversation_review_events
                where event_source='oom_sakkie_manager_question_reply'
                  and created_at>='2026-08-17 15:55:00+00'
                order by created_at""")
            result["device_registry"] = rows("""select device_key,commissioning_stage,
                standing_authority_id,standing_authority_version,registry_generation
                from app_private.rootline_device_registry order by device_key""")
            result["authorities"] = rows("""select standing_authority_id,version,issuer,
                active,revoked from app_private.rootline_standing_authorities""")
    print(json.dumps(result, default=str, indent=2))


if __name__ == "__main__":
    main()
