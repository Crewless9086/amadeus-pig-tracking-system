"""Protected, exactly-once OP-004 evidence action.

Writes only append-only medical corrections and one pig observation. It never
changes pigs, medical events, orders, prices, reservations or allocations.
"""
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone

from services.database_service import DATABASE_URL_ENV
from modules.pig_weights.herdmaster_live_transfer_contract import compose_live_transfer_contract

ACTION_VERSION = "herdmaster_live_transfer_evidence_action_v1"
TTL_SECONDS = 30 * 60
PAIR_CHOICES = {
    "one_administration_recorded_twice": "duplicate_record",
    "two_separate_administrations": "separate_administration",
    "Unknown_requires_veterinary_review": "unknown_veterinary_review",
}
ASSESSMENT_VALUES = {
    "fit_for_transport": {"fit", "unfit", "Unknown"},
    "quarantine": {"clear", "active", "Unknown"},
    "infectious_or_notifiable_disease_restriction": {"none_known", "concern_present", "Unknown"},
    "veterinary_movement_stop": {"none_known", "active", "Unknown"},
    "serious_welfare_or_health_hold": {"clear", "active", "Unknown"},
}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _secret():
    return str(os.getenv("OWNER_SESSION_SECRET") or os.getenv("SECRET_KEY") or "").encode()


def _normalize(request, answers):
    if not isinstance(request, dict) or request.get("action_version") != ACTION_VERSION:
        raise ValueError("transfer_evidence_request_invalid")
    answers = answers if isinstance(answers, dict) else {}
    supplied = answers.get("medical_pair_answers")
    questions = request.get("medical_pair_questions")
    if not isinstance(supplied, list) or not isinstance(questions, list) or len(supplied) != len(questions):
        raise ValueError("medical_pair_answers_incomplete")
    normalized_pairs = []
    for question, answer in zip(questions, supplied):
        answer = answer if isinstance(answer, dict) else {}
        event_ids = list(question.get("event_ids") or [])
        if list(answer.get("event_ids") or []) != event_ids or len(event_ids) != 2:
            raise ValueError("medical_pair_identity_mismatch")
        choice = str(answer.get("choice") or "")
        if choice not in PAIR_CHOICES:
            raise ValueError("medical_pair_choice_invalid")
        retained = str(answer.get("retained_event_id") or "") or None
        if choice == "one_administration_recorded_twice" and retained not in event_ids:
            raise ValueError("duplicate_resolution_retained_event_required")
        if choice != "one_administration_recorded_twice" and retained is not None:
            raise ValueError("retained_event_only_valid_for_duplicate")
        basis = str(answer.get("factual_basis") or "").strip()
        if not basis:
            raise ValueError("medical_resolution_factual_basis_required")
        normalized_pairs.append({"pig_id": question.get("pig_id"), "event_ids": event_ids,
                                 "choice": choice, "retained_event_id": retained,
                                 "factual_basis": basis[:1000]})
    assessment = dict(answers.get("live_transfer_assessment") or {})
    expected_pig = request.get("live_transfer_assessment", {}).get("pig_id")
    if assessment.get("pig_id") != expected_pig:
        raise ValueError("live_transfer_assessment_identity_mismatch")
    normalized_assessment = {"pig_id": expected_pig}
    for field, allowed in ASSESSMENT_VALUES.items():
        value = str(assessment.get(field) or "")
        if value not in allowed:
            raise ValueError(f"live_transfer_assessment_{field}_invalid")
        normalized_assessment[field] = value
    normalized_assessment["attributable_note"] = str(assessment.get("attributable_note") or "").strip()[:1000]
    return {"medical_pair_answers": normalized_pairs,
            "live_transfer_assessment": normalized_assessment}


def preview_evidence_action(packet, answers, *, actor_id, now=None):
    actor_id = str(actor_id or "").strip()
    if not actor_id:
        return {"success": False, "status": "owner_principal_required", "writes_performed": False}, 403
    try:
        normalized = _normalize(packet.get("consolidated_evidence_request"), answers)
    except ValueError as exc:
        return {"success": False, "status": str(exc), "writes_performed": False}, 400
    now = now or datetime.now(timezone.utc)
    envelope = {"action_version": ACTION_VERSION, "packet_digest": packet.get("packet_digest"),
                "answers": normalized, "actor_id": actor_id}
    digest = _digest(envelope)
    issued_at = int(now.timestamp())
    signature = hmac.new(_secret(), f"{digest}|{actor_id}|{issued_at}".encode(), hashlib.sha256).hexdigest() if _secret() else ""
    return {"success": True, "status": "transfer_evidence_preview_ready",
            "preview_digest": digest, "answers": normalized,
            "confirmation_binding": {"preview_digest": digest, "actor_id": actor_id,
                                     "issued_at": issued_at, "signature": signature},
            "writes_performed": False}, 200


def _valid_binding(binding, digest, actor_id, now, *, enforce_ttl=True):
    try:
        issued = int(binding.get("issued_at"))
    except (AttributeError, TypeError, ValueError):
        return False
    age = int(now.timestamp()) - issued
    expected = hmac.new(_secret(), f"{digest}|{actor_id}|{issued}".encode(), hashlib.sha256).hexdigest() if _secret() else ""
    time_valid = 0 <= age <= TTL_SECONDS if enforce_ttl else issued > 0
    return (time_valid and binding.get("preview_digest") == digest
            and binding.get("actor_id") == actor_id and bool(expected)
            and hmac.compare_digest(str(binding.get("signature") or ""), expected))


def _snapshot_from_cursor(cursor, pig_ids, order_id):
    cursor.execute("""select p.*,s.current_weight_kg,s.last_weight_date
        from public.current_canonical_pigs p left join public.current_canonical_pig_state s using(pig_id)
        where p.pig_id=any(%s) order by p.pig_id""", (pig_ids,))
    columns = [column.name for column in cursor.description]
    pigs = [dict(zip(columns, row)) for row in cursor.fetchall()]
    queries = {
        "medical_events": ("select * from public.pig_medical_events where pig_id=any(%s) order by pig_id,treatment_date,created_at,medical_event_id", (pig_ids,)),
        "order_lines": ("select * from public.order_lines where order_id=%s order by created_at,order_line_id", (order_id,)),
        "observation_events": ("select * from public.pig_observation_events where pig_id=any(%s) order by pig_id,observed_at,recorded_at,observation_event_id", (pig_ids,)),
        "location_events": ("select * from public.pig_location_events where pig_id=any(%s) order by pig_id,move_date,created_at,location_event_id", (pig_ids,)),
        "price_rows": ("select * from public.sales_pricing where active=true order by sale_category,weight_band,sex,effective_from desc,created_at desc", ()),
        "medical_correction_events": ("select * from public.pig_medical_correction_events where pig_id=any(%s) order by pig_id,recorded_at,correction_event_id", (pig_ids,)),
    }
    snapshot = {"pigs": pigs}
    for name, (sql, params) in queries.items():
        cursor.execute(sql, params)
        columns = [column.name for column in cursor.description]
        snapshot[name] = [dict(zip(columns, row)) for row in cursor.fetchall()]
    cursor.execute("select * from public.orders where order_id=%s", (order_id,))
    columns = [column.name for column in cursor.description]
    row = cursor.fetchone()
    if len(pigs) != len(pig_ids) or not row:
        raise ValueError("transfer_evidence_canonical_identity_changed")
    snapshot["order"] = dict(zip(columns, row))
    snapshot["order"]["active_pig_line_unique_guard"] = True
    snapshot["medical_correction_rail_available"] = True
    return snapshot


def execute_evidence_action(packet, answers, *, actor_id, idempotency_key,
                            confirmation_binding, connect_factory=None, now=None):
    actor_id, key = str(actor_id or "").strip(), str(idempotency_key or "").strip()
    now = now or datetime.now(timezone.utc)
    submitted_answers_digest = _digest(answers if isinstance(answers, dict) else {})
    try:
        issued_at = int((confirmation_binding or {}).get("issued_at") or 0)
    except (TypeError, ValueError):
        issued_at = 0
    if not key or not actor_id:
        return {"success": False, "status": "exact_preview_confirmation_required", "writes_performed": False}, 409
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if connect_factory:
        connection = connect_factory(database_url)
    else:
        if not database_url:
            return {"success": False, "status": "canonical_database_unavailable", "writes_performed": False}, 503
        import psycopg
        connection = psycopg.connect(database_url, connect_timeout=10)
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("set transaction isolation level serializable")
                cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", ("transfer-evidence:" + key,))
                cursor.execute("""select actor_id,preview_digest,submitted_answers_digest,action_envelope
                    from public.herdmaster_transfer_evidence_receipts where idempotency_key=%s""", (key,))
                receipt = cursor.fetchone()
                if receipt:
                    envelope = dict(receipt[3] or {})
                    if (str(receipt[0]) != actor_id or str(receipt[1]) != str((confirmation_binding or {}).get("preview_digest") or "")
                            or str(receipt[2]) != submitted_answers_digest
                            or not _valid_binding(confirmation_binding, str(receipt[1]), actor_id, now,
                                                  enforce_ttl=False)):
                        raise ValueError("transfer_evidence_idempotency_conflict")
                    replay_snapshot = _snapshot_from_cursor(cursor, list(envelope["pig_ids"]), envelope["order_id"])
                    return {"success": True, "status": "transfer_evidence_duplicate_execution",
                            "receipt_idempotency_key": key,
                            "evidence_rows_written": 0, "receipt_rows_written": 0,
                            "total_rows_written": 0, "rows_written": 0, "writes_performed": False,
                            "canonical_readback": compose_live_transfer_contract(replay_snapshot, as_of=now.date())}, 200
                preview, status = preview_evidence_action(
                    packet, answers, actor_id=actor_id,
                    now=datetime.fromtimestamp(issued_at, timezone.utc),
                )
                if status != 200 or not _valid_binding(
                        confirmation_binding, preview.get("preview_digest"), actor_id, now):
                    raise ValueError("exact_preview_confirmation_required")
                normalized = preview["answers"]
                expected_keys = []
                expected_corrections = {}
                for pair in normalized["medical_pair_answers"]:
                    targets = ([event for event in pair["event_ids"] if event != pair["retained_event_id"]]
                               if pair["choice"] == "one_administration_recorded_twice" else pair["event_ids"])
                    for event in targets:
                        event_key = f"{key}:medical:{event}"
                        expected_keys.append(event_key)
                        expected_corrections[event_key] = (
                            event, pair["retained_event_id"], PAIR_CHOICES[pair["choice"]],
                            pair["factual_basis"], actor_id,
                        )
                observation_key = f"{key}:assessment:{normalized['live_transfer_assessment']['pig_id']}"
                cursor.execute("""select idempotency_key,original_medical_event_id,
                    retained_medical_event_id,resolution,factual_basis,recorded_by
                    from public.pig_medical_correction_events where idempotency_key=any(%s)""", (expected_keys,))
                existing_rows = cursor.fetchall()
                existing_medical = {row[0] for row in existing_rows}
                cursor.execute("""select observer_reference,measurements_json,source_reference
                    from public.pig_observation_events where idempotency_key=%s""", (observation_key,))
                existing_observation_row = cursor.fetchone()
                existing_observation = bool(existing_observation_row)
                if existing_medical or existing_observation:
                    exact_medical = (existing_medical == set(expected_keys)
                                     and all(tuple(row[1:]) == expected_corrections[row[0]]
                                             for row in existing_rows))
                    exact_observation = (existing_observation
                        and str(existing_observation_row[0] or "") == actor_id
                        and dict(existing_observation_row[1] or {}) == {
                            "contract_version": ACTION_VERSION,
                            **normalized["live_transfer_assessment"],
                        }
                        and str(existing_observation_row[2] or "") == preview["preview_digest"])
                    if exact_medical and exact_observation:
                        request = packet["consolidated_evidence_request"]
                        pig_ids = sorted({pair["pig_id"] for pair in normalized["medical_pair_answers"]}
                                         | {normalized["live_transfer_assessment"]["pig_id"]})
                        replay_snapshot = _snapshot_from_cursor(cursor, pig_ids, request["order_id"])
                        return {"success": True, "status": "transfer_evidence_duplicate_execution",
                                "rows_written": 0, "writes_performed": False,
                                "canonical_readback": compose_live_transfer_contract(
                                    replay_snapshot, as_of=now.date())}, 200
                    raise ValueError("transfer_evidence_partial_replay_conflict")
                request = packet["consolidated_evidence_request"]
                pig_ids = sorted({pair["pig_id"] for pair in normalized["medical_pair_answers"]}
                                 | {normalized["live_transfer_assessment"]["pig_id"]})
                current_snapshot = _snapshot_from_cursor(cursor, pig_ids, request["order_id"])
                current_packet = compose_live_transfer_contract(current_snapshot, as_of=now.date())
                if current_packet.get("packet_digest") != packet.get("packet_digest"):
                    raise ValueError("transfer_evidence_preview_stale_or_altered")
                action_envelope = {"order_id": request["order_id"], "pig_ids": pig_ids,
                                   "normalized_answers": normalized}
                cursor.execute("""insert into public.herdmaster_transfer_evidence_receipts
                    (idempotency_key,action_version,actor_id,preview_digest,submitted_answers_digest,
                     action_envelope,executed_at) values(%s,%s,%s,%s,%s,%s::jsonb,%s)""",
                    (key, ACTION_VERSION, actor_id, preview["preview_digest"], submitted_answers_digest,
                     json.dumps(action_envelope), now))
                correction_ids = []
                for pair in normalized["medical_pair_answers"]:
                    cursor.execute("select medical_event_id,pig_id from public.pig_medical_events where medical_event_id=any(%s) for share", (pair["event_ids"],))
                    rows = cursor.fetchall()
                    if {row[0] for row in rows} != set(pair["event_ids"]) or {row[1] for row in rows} != {pair["pig_id"]}:
                        raise ValueError("medical_pair_canonical_binding_changed")
                    targets = ([event for event in pair["event_ids"] if event != pair["retained_event_id"]]
                               if pair["choice"] == "one_administration_recorded_twice" else pair["event_ids"])
                    for event_id in targets:
                        correction_id = "MEDCOR-" + uuid.uuid4().hex[:24].upper()
                        cursor.execute("""insert into public.pig_medical_correction_events
                            (correction_event_id,pig_id,original_medical_event_id,retained_medical_event_id,
                             resolution,factual_basis,recorded_by,recorded_at,idempotency_key)
                            values(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (correction_id, pair["pig_id"], event_id, pair["retained_event_id"],
                             PAIR_CHOICES[pair["choice"]], pair["factual_basis"], actor_id, now,
                             f"{key}:medical:{event_id}"))
                        correction_ids.append(correction_id)
                assessment = normalized["live_transfer_assessment"]
                observation_id = "OBS-" + uuid.uuid4().hex[:24].upper()
                note = "Current attributable live-transfer assessment; no diagnosis or food-chain clearance asserted."
                cursor.execute("""insert into public.pig_observation_events
                    (observation_event_id,pig_id,observed_at,recorded_at,observer_reference,
                     observation_category,severity,factual_note,measurements_json,source_system,
                     source_reference,idempotency_key)
                    values(%s,%s,%s,%s,%s,'welfare','informational',%s,%s::jsonb,'owner',%s,%s)""",
                    (observation_id, assessment["pig_id"], now, now, actor_id, note,
                     json.dumps({"contract_version": ACTION_VERSION, **assessment}),
                     preview["preview_digest"], observation_key))
                readback_snapshot = _snapshot_from_cursor(cursor, pig_ids, request["order_id"])
                canonical_readback = compose_live_transfer_contract(readback_snapshot, as_of=now.date())
                return {"success": True, "status": "transfer_evidence_recorded",
                        "receipt_idempotency_key": key,
                        "medical_correction_event_ids": correction_ids,
                        "observation_event_id": observation_id,
                        "evidence_rows_written": len(correction_ids) + 1,
                        "receipt_rows_written": 1,
                        "total_rows_written": len(correction_ids) + 2,
                        "rows_written": len(correction_ids) + 2, "writes_performed": True,
                        "prohibited_effects_written": False,
                        "canonical_readback": canonical_readback}, 200
    except ValueError as exc:
        return {"success": False, "status": str(exc), "rows_written": 0,
                "writes_performed": False}, 409
    except Exception:
        return {"success": False, "status": "transfer_evidence_atomic_execution_failed",
                "rows_written": 0, "writes_performed": False}, 503
