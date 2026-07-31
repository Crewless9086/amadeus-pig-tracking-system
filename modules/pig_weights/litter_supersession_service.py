"""Governed append-only litter supersession; never rewrites farm facts."""
from __future__ import annotations

import hashlib
import json
import time
import psycopg
from psycopg import sql

CONTRACT_VERSION = "litter_supersession_v1"


def canonical_sha256(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def operation_identity(packet):
    keys = (
        "retained_litter_id", "superseded_litter_id", "authorization_id",
        "mating_id", "preview_sha256", "reference_allowlist_sha256",
        "skipped_audit_rows_sha256", "skipped_audit_row_count", "input_sha256",
    )
    identity = {"version": CONTRACT_VERSION, **{key: packet[key] for key in keys}}
    identity["superseded_child_ids"] = sorted(packet["superseded_child_ids"])
    identity["retained_child_ids"] = sorted(packet["retained_child_ids"])
    identity["skipped_audit_row_ids"] = sorted(packet["skipped_audit_row_ids"])
    return "LITTER-SUPERSESSION-" + canonical_sha256(identity).upper()[:32]


def _reference_digests(connection, superseded_ids, all_ids):
    columns = connection.execute(
        """
        select column_info.table_name,column_info.column_name
        from information_schema.columns column_info
        join information_schema.tables table_info
          on table_info.table_schema=column_info.table_schema
         and table_info.table_name=column_info.table_name
         and table_info.table_type='BASE TABLE'
        where column_info.table_schema='public'
        order by table_name,ordinal_position
        """
    ).fetchall()
    excluded = {
        "pigs", "pig_current_state", "current_canonical_pigs",
        "current_canonical_pig_state", "litter_cohort_dispositions",
        "litter_supersessions", "litter_correction_authorizations",
        "litter_supersession_audit_rows", "bulk_weight_batch_rows",
    }
    grouped = {}
    for table_name, column_name in columns:
        if table_name not in excluded:
            grouped.setdefault(table_name, []).append(column_name)
    references = []
    for table_name, column_names in grouped.items():
        clauses, params = [], []
        for column_name in column_names:
            for pig_id in superseded_ids:
                clauses.append(sql.SQL("{}::text like %s").format(sql.Identifier(column_name)))
                params.append(f"%{pig_id}%")
        query = sql.SQL("select ctid::text from {} where {} order by ctid").format(
            sql.Identifier("public", table_name), sql.SQL(" or ").join(clauses)
        )
        references.extend(
            (table_name, row[0])
            for row in connection.execute(query, params).fetchall()
        )
    references.extend(
        ("pigs", row[0])
        for row in connection.execute(
            """
            select pig_id from public.pigs
            where pig_id <> all(%s)
              and (mother_pig_id=any(%s) or father_pig_id=any(%s))
            order by pig_id
            """,
            (all_ids, superseded_ids, superseded_ids),
        ).fetchall()
    )
    references.sort()
    if references:
        raise RuntimeError("downstream factual reference blocks correction")
    skipped = connection.execute(
        """
        select row_id::text,batch_id::text,pig_id,status,status_reason,idempotency_key
        from public.bulk_weight_batch_rows where pig_id=any(%s) order by row_id
        """,
        (all_ids,),
    ).fetchall()
    if any(str(row[3]).lower() != "skipped" for row in skipped):
        raise RuntimeError("non-skipped bulk audit reference blocks correction")
    return {
        "reference_allowlist_sha256": canonical_sha256({
            "schema_inventory": columns, "references": references,
        }),
        "skipped_audit_rows_sha256": canonical_sha256(skipped),
        "skipped_audit_row_count": len(skipped),
        "skipped_audit_row_ids": [row[0] for row in skipped],
    }


def _apply_litter_supersession_once(packet, *, connect_factory, service_authority):
    if service_authority != "herdmaster_litter_correction_service":
        raise PermissionError("service-only litter correction authority required")
    required = (
        "retained_litter_id", "superseded_litter_id", "superseded_child_ids",
        "retained_child_ids", "authorization_id", "mating_id",
        "preview_sha256", "reference_allowlist_sha256",
        "skipped_audit_rows_sha256", "skipped_audit_row_count",
        "skipped_audit_row_ids", "input_sha256",
    )
    missing = [key for key in required if key not in packet or packet[key] in (None, "")]
    if missing:
        raise ValueError("missing correction fields: " + ", ".join(missing))
    superseded = sorted(set(packet["superseded_child_ids"]))
    retained = sorted(set(packet["retained_child_ids"]))
    if len(superseded) != len(packet["superseded_child_ids"]) or not superseded:
        raise ValueError("invalid superseded child allowlist")
    if len(retained) != len(packet["retained_child_ids"]) or set(superseded) & set(retained):
        raise ValueError("invalid retained child allowlist")

    operation_id = operation_identity(packet)
    with connect_factory() as connection:
        connection.execute("set transaction isolation level serializable")
        connection.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s,0))", (operation_id,)
        )
        existing = connection.execute(
            """
            select retained_litter_id,superseded_litter_id,authorization_id,
                   preview_sha256,mating_id,superseded_child_ids,retained_child_ids,
                   reference_allowlist_sha256,skipped_audit_rows_sha256,input_sha256
            from public.litter_supersessions where operation_id=%s
            """,
            (operation_id,),
        ).fetchone()
        if existing:
            dispositions = connection.execute(
                """
                select pig_id from public.litter_cohort_dispositions
                where operation_id=%s order by pig_id
                """,
                (operation_id,),
            ).fetchall()
            expected = (
                packet["retained_litter_id"], packet["superseded_litter_id"],
                packet["authorization_id"], packet["preview_sha256"],
                packet["mating_id"], superseded, retained,
                packet["reference_allowlist_sha256"],
                packet["skipped_audit_rows_sha256"], packet["input_sha256"],
            )
            normalized = list(existing)
            normalized[5], normalized[6] = sorted(normalized[5]), sorted(normalized[6])
            if tuple(normalized) != expected or [row[0] for row in dispositions] != superseded:
                raise RuntimeError("operation identity post-state mismatch")
            audit_evidence = connection.execute(
                """
                select row_id::text from public.litter_supersession_audit_rows
                where operation_id=%s order by row_id
                """,
                (operation_id,),
            ).fetchall()
            if [row[0] for row in audit_evidence] != sorted(packet["skipped_audit_row_ids"]):
                raise RuntimeError("operation audit-evidence post-state mismatch")

        authorization = connection.execute(
            """
            select operation_id,preview_sha256,decision_status
            from public.litter_correction_authorizations
            where authorization_id=%s
              and not exists (
                select 1 from public.litter_correction_authorization_revocations
                where authorization_id=%s
              )
            """,
            (packet["authorization_id"], packet["authorization_id"]),
        ).fetchone()
        if authorization != (operation_id, packet["preview_sha256"], "confirmed"):
            raise RuntimeError("durable owner confirmation is not current")

        litter_rows = connection.execute(
            """
            select to_jsonb(litter)
            from public.litters litter
            where litter_id=any(%s) order by litter_id for update
            """,
            ([packet["retained_litter_id"], packet["superseded_litter_id"]],),
        ).fetchall()
        if len(litter_rows) != 2:
            raise RuntimeError("exact retained/superseded litter rows required")
        litter_by_id = {row[0]["litter_id"]: row[0] for row in litter_rows}
        retained_litter = litter_by_id[packet["retained_litter_id"]]
        mating = connection.execute(
            """
            select mating_id,sow_pig_id,boar_pig_id,related_litter_id
            from public.mating_events where mating_id=%s for update
            """,
            (packet["mating_id"],),
        ).fetchone()
        if not mating or mating[1:] != (
            retained_litter["sow_pig_id"], retained_litter["boar_pig_id"],
            packet["retained_litter_id"]
        ):
            raise RuntimeError("exact retained-litter mating linkage required")
        children = connection.execute(
            """
            select to_jsonb(pig) from public.pigs pig
            where litter_id=any(%s) order by pig_id for update
            """,
            ([packet["superseded_litter_id"], packet["retained_litter_id"]],),
        ).fetchall()
        actual_child_links = sorted(
            (row[0]["pig_id"], row[0]["litter_id"]) for row in children
        )
        expected_child_links = sorted(
            [(pig_id, packet["superseded_litter_id"]) for pig_id in superseded]
            + [(pig_id, packet["retained_litter_id"]) for pig_id in retained]
        )
        if actual_child_links != expected_child_links:
            raise RuntimeError("complete child allowlist or litter linkage mismatch")
        digests = _reference_digests(connection, superseded, sorted(superseded + retained))
        if any(digests[key] != packet[key] for key in digests):
            raise RuntimeError("reference or skipped-audit digest mismatch")
        computed_input = canonical_sha256({
            "litters": litter_rows, "mating": mating, "children": children,
            "references": digests,
        })
        if computed_input != packet["input_sha256"]:
            raise RuntimeError("canonical input digest mismatch")
        if existing:
            projection = connection.execute(
                """
                select
                  (select count(*) from public.current_canonical_litters
                   where litter_id=any(%s)),
                  (select count(*) from public.current_canonical_pigs
                   where pig_id=any(%s)),
                  (select count(*) from public.historical_litter_representations
                   where litter_id=any(%s))
                """,
                (
                    [packet["retained_litter_id"], packet["superseded_litter_id"]],
                    retained + superseded,
                    [packet["retained_litter_id"], packet["superseded_litter_id"]],
                ),
            ).fetchone()
            if projection != (1, len(retained), 2):
                raise RuntimeError("canonical/history replay projection mismatch")
            return {"success": True, "status": "replayed", "operation_id": operation_id,
                    "rows_created": 0, "writes_performed": False}
        connection.execute(
            "select public.apply_litter_supersession_metadata("
            "%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s::jsonb,%s)",
            (
                operation_id, packet["retained_litter_id"], packet["superseded_litter_id"],
                packet["authorization_id"], packet["preview_sha256"], packet["mating_id"],
                json.dumps(superseded), json.dumps(retained),
                packet["reference_allowlist_sha256"],
                packet["skipped_audit_rows_sha256"],
                json.dumps(sorted(packet["skipped_audit_row_ids"])),
                packet["input_sha256"],
            ),
        )
        return {"success": True, "status": "created", "operation_id": operation_id,
                "rows_created": 1 + len(superseded) + len(packet["skipped_audit_row_ids"]),
                "writes_performed": True}


def apply_litter_supersession(packet, *, connect_factory, service_authority):
    """Apply once, retrying only serialization/deadlock races for the same rail."""
    for attempt in range(3):
        try:
            return _apply_litter_supersession_once(
                packet,
                connect_factory=connect_factory,
                service_authority=service_authority,
            )
        except (psycopg.errors.SerializationFailure, psycopg.errors.DeadlockDetected):
            if attempt == 2:
                raise
            time.sleep(0.01 * (attempt + 1))
