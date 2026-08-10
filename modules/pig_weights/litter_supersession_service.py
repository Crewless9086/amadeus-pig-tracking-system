"""Governed append-only litter supersession; never rewrites farm facts."""
from __future__ import annotations

import hashlib
import json
import time
import psycopg
from psycopg import sql

CONTRACT_VERSION = "litter_supersession_v2"
HISTORICAL_SAM_REVIEW_EVENT_SOURCES = frozenset({
    "shadow_review",
    "sam_live_stock_shadow_review",
    "sam_live_stock_read_only_review",
})
HISTORICAL_IDENTITY_PATH_SEGMENTS = frozenset({
    "availability",
    "canonical_inventory_snapshot",
    "eligible_projection",
    "excluded_pig_ids",
    "inventory_snapshot",
})


def canonical_sha256(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def operation_identity(packet):
    keys = (
        "retained_litter_id", "superseded_litter_id", "authorization_id",
        "mating_id", "preview_sha256", "reference_allowlist_sha256",
        "historical_reference_rows_sha256", "historical_reference_row_count",
        "skipped_audit_rows_sha256", "skipped_audit_row_count", "input_sha256",
    )
    identity = {"version": CONTRACT_VERSION, **{key: packet[key] for key in keys}}
    identity["superseded_child_ids"] = sorted(packet["superseded_child_ids"])
    identity["retained_child_ids"] = sorted(packet["retained_child_ids"])
    identity["skipped_audit_row_ids"] = sorted(packet["skipped_audit_row_ids"])
    identity["historical_reference_row_ids"] = sorted(
        packet["historical_reference_row_ids"]
    )
    return "LITTER-SUPERSESSION-" + canonical_sha256(identity).upper()[:32]


def _exact_json_identity_paths(value, identities, path=()):
    matches = []
    if isinstance(value, dict):
        for key, item in value.items():
            matches.extend(
                _exact_json_identity_paths(item, identities, path + (str(key),))
            )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            matches.extend(
                _exact_json_identity_paths(item, identities, path + (str(index),))
            )
    elif isinstance(value, str) and value in identities:
        matches.append((value, path))
    return matches


def _sam_review_history_references(connection, superseded_ids, column_names):
    """Classify immutable review snapshots; never treats them as current facts."""
    table_name = "sam_live_stock_conversation_review_events"
    if "decision_json" not in column_names:
        return [], []
    patterns = [f"%{pig_id}%" for pig_id in superseded_ids]
    json_history_columns = {"decision_json", "review_json"}
    other_columns = [column for column in column_names if column not in json_history_columns]
    clauses, params = [], []
    for column_name in other_columns:
        for pig_id in superseded_ids:
            clauses.append(sql.SQL("{}::text like %s").format(sql.Identifier(column_name)))
            params.append(f"%{pig_id}%")
    if clauses:
        unexpected = connection.execute(
            sql.SQL("select count(*) from {} where {}").format(
                sql.Identifier("public", table_name), sql.SQL(" or ").join(clauses)
            ),
            params,
        ).fetchone()[0]
        if unexpected:
            raise RuntimeError("SAM review identity outside decision_json blocks correction")

    trigger_rows = connection.execute(
        """
        select trigger.tgname,trigger.tgenabled,trigger.tgtype,
               namespace_function.nspname,function.proname,
               pg_get_triggerdef(trigger.oid,true),
               function.prosrc,pg_get_functiondef(function.oid),
               function.prosecdef,function.proconfig
          from pg_catalog.pg_trigger trigger
          join pg_catalog.pg_class relation on relation.oid=trigger.tgrelid
          join pg_catalog.pg_namespace namespace on namespace.oid=relation.relnamespace
          join pg_catalog.pg_proc function on function.oid=trigger.tgfoid
          join pg_catalog.pg_namespace namespace_function
            on namespace_function.oid=function.pronamespace
         where namespace.nspname='public'
           and relation.relname=%s
           and not trigger.tgisinternal
         order by trigger.tgname
        """,
        (table_name,),
    ).fetchall()
    trigger_by_name = {row[0]: row for row in trigger_rows}
    expected_triggers = {
        "prevent_sam_live_stock_review_update": 19,  # ROW|BEFORE|UPDATE
        "prevent_sam_live_stock_review_delete": 11,  # ROW|BEFORE|DELETE
    }
    append_only_guard = []
    for trigger_name, expected_type in expected_triggers.items():
        row = trigger_by_name.get(trigger_name)
        if (
            row is None
            or row[1] != "O"
            or row[2] != expected_type
            or row[3] != "public"
            or row[4] != "prevent_sam_live_stock_review_mutation"
            or " ".join(str(row[6]).split()) != (
                "begin raise exception "
                "'sam_live_stock_conversation_review_events is append-only'; "
                "end;"
            )
            or row[8] is not False
            or row[9] not in (None, [])
        ):
            raise RuntimeError("SAM review history is not provably append-only")
        append_only_guard.append({
            "trigger_name": trigger_name,
            "enabled": row[1],
            "trigger_type": row[2],
            "function": f"{row[3]}.{row[4]}",
            "definition_sha256": hashlib.sha256(str(row[5]).encode()).hexdigest(),
            "function_definition_sha256": hashlib.sha256(
                str(row[7]).encode()
            ).hexdigest(),
            "security_definer": row[8],
            "function_config": row[9] or [],
        })
    if len(append_only_guard) != 2:
        raise RuntimeError("SAM review history is not provably append-only")

    rows = connection.execute(
        """
        select review.review_event_id,review.decision_json::text,
               review.applies_learning_now,review.changes_prompt_now,review.changes_runtime_now,
               review.sends_customer_message,review.calls_chatwoot,review.calls_telegram,
               review.creates_order,review.reserves_stock,review.changes_stock,review.writes_farm_data,
               review.safe_to_send,review.owner_send_required,review.no_reply_recommended,
               review.escalation_required,review.recommended_action,
               review.conversation_mode_recommendation,review.event_source,review.review_json::text
          from public.sam_live_stock_conversation_review_events review
          join public.current_sam_review_obligation_resolutions resolution
            on resolution.review_event_id=review.review_event_id
         where resolution.represented_pig_id=any(%s)
         order by review.review_event_id
        """,
        (list(superseded_ids),),
    ).fetchall()
    references = []
    for row in rows:
        # Immutable reviews can remain action-bearing only when a separately
        # governed current resolution proves that the represented livestock
        # identity is superseded while preserving the customer obligation.
        action_bearing = any(bool(value) for value in row[2:16])
        recommended_action = str(row[16] or "").strip()
        conversation_mode = str(row[17] or "").strip().upper()
        event_source = str(row[18] or "").strip()
        legacy_historical = (
            not action_bearing
            and not recommended_action
            and conversation_mode in {"", "READ_ONLY", "SHADOW"}
            and event_source in HISTORICAL_SAM_REVIEW_EVENT_SOURCES
        )
        if not legacy_historical and not action_bearing:
            raise RuntimeError("unsupported SAM review reference blocks correction")
        resolution = None
        if action_bearing:
            resolution = connection.execute(
                """
                select resolution_event_id,represented_pig_id,
                       represented_identity_status,
                       same_animal_mapping_prohibited,
                       canonical_same_animal_pig_id,
                       governed_disposition_operation_id,
                       customer_obligation_status,resolution_action,
                       event_payload_sha256
                  from public.current_sam_review_obligation_resolutions
                 where review_event_id=%s
                """,
                (str(row[0]),),
            ).fetchone()
            if (
                resolution is None
                or resolution[1] not in superseded_ids
                or resolution[2] != "superseded"
                or resolution[3] is not True
                or resolution[4] is not None
                or not str(resolution[5] or "").strip()
                or resolution[6] == "unknown_fail_closed"
                or resolution[7] in {"indeterminate", "corrective_replanning"}
                or len(str(resolution[8] or "")) != 64
            ):
                raise RuntimeError(
                    "current governed SAM obligation resolution required"
                )
        elif (
            recommended_action
            or conversation_mode not in {"", "READ_ONLY", "SHADOW"}
            or event_source not in HISTORICAL_SAM_REVIEW_EVENT_SOURCES
        ):
            raise RuntimeError("action-bearing SAM review reference blocks correction")
        decision_text = str(row[1])
        decision = json.loads(decision_text)
        identity_paths = _exact_json_identity_paths(
            decision, frozenset(superseded_ids)
        )
        review_text = str(row[19] or "{}")
        review = json.loads(review_text)
        review_identity_paths = _exact_json_identity_paths(
            review, frozenset(superseded_ids)
        )
        if not identity_paths:
            continue
        if not resolution and any(
            not set(path) & HISTORICAL_IDENTITY_PATH_SEGMENTS
            for _identity, path in identity_paths
        ):
            raise RuntimeError("SAM review identity outside governed snapshot path")
        identities = sorted({identity for identity, _path in identity_paths})
        reference = {
            "table": table_name,
            "row_id": str(row[0]),
            "identities": identities,
            "identity_paths": [
                {"identity": identity, "path": list(path)}
                for identity, path in sorted(identity_paths)
            ],
            "decision_json_sha256": hashlib.sha256(decision_text.encode()).hexdigest(),
            "review_json_sha256": hashlib.sha256(review_text.encode()).hexdigest(),
            "review_identity_paths": [
                {"identity": identity, "path": list(path)}
                for identity, path in sorted(review_identity_paths)
            ],
            "classification": (
                "immutable_review_with_governed_current_obligation"
                if resolution else "immutable_historical_review_snapshot"
            ),
        }
        if resolution:
            reference["current_resolution"] = {
                "resolution_event_id": resolution[0],
                "represented_pig_id": resolution[1],
                "represented_identity_status": resolution[2],
                "same_animal_mapping_prohibited": resolution[3],
                "canonical_same_animal_pig_id": resolution[4],
                "governed_disposition_operation_id": resolution[5],
                "customer_obligation_status": resolution[6],
                "resolution_action": resolution[7],
                "event_payload_sha256": resolution[8],
            }
        references.append(reference)
    return references, append_only_guard


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
        "litter_correction_authorization_revocations",
        "litter_supersession_audit_rows", "bulk_weight_batch_rows",
        "sam_review_obligation_resolution_events",
    }
    grouped = {}
    for table_name, column_name in columns:
        if table_name not in excluded:
            grouped.setdefault(table_name, []).append(column_name)
    historical_review_rows, historical_review_guard = _sam_review_history_references(
        connection,
        superseded_ids,
        grouped.pop("sam_live_stock_conversation_review_events", []),
    )
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
        raise RuntimeError(
            "downstream factual reference blocks correction: "
            + json.dumps(references[:20])
        )
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
            "schema_inventory": columns,
            "references": references,
            "historical_review_rows": historical_review_rows,
            "historical_review_guard": historical_review_guard,
        }),
        "historical_reference_rows_sha256": canonical_sha256(
            historical_review_rows
        ),
        "historical_reference_row_count": len(historical_review_rows),
        "historical_reference_rows": historical_review_rows,
        "historical_reference_guard": historical_review_guard,
        "historical_reference_row_ids": [
            row["row_id"] for row in historical_review_rows
        ],
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
        "historical_reference_rows_sha256", "historical_reference_row_count",
        "historical_reference_rows", "historical_reference_row_ids",
        "historical_reference_guard",
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
                  ,historical_reference_rows_sha256,
                   historical_reference_row_count,historical_reference_row_ids
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
                packet["historical_reference_rows_sha256"],
                packet["historical_reference_row_count"],
                sorted(packet["historical_reference_row_ids"]),
            )
            normalized = list(existing)
            normalized[5], normalized[6] = sorted(normalized[5]), sorted(normalized[6])
            normalized[12] = sorted(normalized[12])
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
            "%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s::jsonb,%s,"
            "%s,%s,%s::jsonb)",
            (
                operation_id, packet["retained_litter_id"], packet["superseded_litter_id"],
                packet["authorization_id"], packet["preview_sha256"], packet["mating_id"],
                json.dumps(superseded), json.dumps(retained),
                packet["reference_allowlist_sha256"],
                packet["skipped_audit_rows_sha256"],
                json.dumps(sorted(packet["skipped_audit_row_ids"])),
                packet["input_sha256"],
                packet["historical_reference_rows_sha256"],
                packet["historical_reference_row_count"],
                json.dumps(sorted(packet["historical_reference_row_ids"])),
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
