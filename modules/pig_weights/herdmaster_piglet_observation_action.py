"""Channel-invariant canonical action for factual piglet observations."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import date, datetime, time, timezone

from services.database_service import DATABASE_URL_ENV

CONTRACT_VERSION = "herdmaster_piglet_observation_v1"
TRAITS = {
    "good_build", "strong_legs", "good_growth", "broad_body",
    "good_temperament", "potential_breeding_review", "other", "concern",
}
SENTIMENTS = {"positive", "concerning", "mixed", "neutral"}
PREVIEW_TTL_SECONDS = 30 * 60


def normalize_action(payload, *, channel):
    """Normalize every UI/conversation adapter into the same typed action."""
    raw = payload if isinstance(payload, dict) else {}
    observations = raw.get("observations") if isinstance(raw.get("observations"), list) else []
    normalized = []
    errors = []
    for index, item in enumerate(observations):
        if not isinstance(item, dict):
            errors.append(f"observation_{index}_invalid")
            continue
        pig_id = str(item.get("pig_id") or "").strip()
        note = str(item.get("factual_note") or item.get("note") or "").strip()
        traits = sorted({str(value).strip().lower() for value in item.get("traits", []) if str(value).strip()})
        sentiment = str(item.get("sentiment") or "neutral").strip().lower()
        observed_on = str(item.get("observed_on") or raw.get("observed_on") or "").strip()
        try:
            parsed_observed_on = date.fromisoformat(observed_on)
            if parsed_observed_on > datetime.now(timezone.utc).date(): raise ValueError
        except ValueError:
            parsed_observed_on = None
        if (not pig_id or not note or parsed_observed_on is None or sentiment not in SENTIMENTS
                or not traits or any(value not in TRAITS for value in traits)
                or len(note) > 500):
            errors.append(f"observation_{index}_evidence_invalid")
            continue
        normalized.append({
            "pig_id": pig_id, "observed_on": observed_on, "factual_note": note,
            "traits": traits, "sentiment": sentiment,
            "watch_flag": item.get("watch_flag") is True,
            "supersedes_observation_event_id": str(item.get("supersedes_observation_event_id") or "").strip() or None,
        })
    action = {
        "contract_version": CONTRACT_VERSION,
        "action_type": "record_piglet_observations",
        "litter_id": str(raw.get("litter_id") or "").strip(),
        "observations": sorted(normalized, key=lambda row: (row["pig_id"], row["observed_on"], row["factual_note"])),
        "source_context": str(raw.get("source_context") or "weaning").strip().lower(),
        "source_reference": str(raw.get("source_reference") or "").strip(),
        "input_provenance": str(channel or "unknown").strip().lower(),
        "idempotency_key": str(raw.get("idempotency_key") or "").strip(),
    }
    if not action["litter_id"] or not action["observations"] or not action["idempotency_key"]:
        errors.append("complete_observation_action_required")
    if action["source_context"] not in {"weaning", "historical_weaning"}:
        errors.append("invalid_observation_context")
    return action, sorted(set(errors))


def normalize_application(payload):
    return normalize_action(payload, channel="application")


def normalize_typed_oom_sakkie(payload):
    return normalize_action(payload, channel="typed_oom_sakkie")


def normalize_telegram(payload):
    return normalize_action(payload, channel="telegram")


def normalize_voice(payload):
    return normalize_action(payload, channel="voice")


def action_digest(action):
    material = {key: action[key] for key in (
        "contract_version", "action_type", "litter_id", "observations",
        "source_context", "source_reference", "idempotency_key",
        "input_provenance",
    )}
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def preview_action(payload, *, channel="application", identity_rows=None):
    action, errors = normalize_action(payload, channel=channel)
    identities = {str(row.get("pig_id")): row for row in (identity_rows or []) if isinstance(row, dict)}
    requested = {row["pig_id"] for row in action["observations"]}
    if identity_rows is not None and (requested != set(identities) or any(
            str(identities[pig_id].get("litter_id") or "") != action["litter_id"] for pig_id in requested)):
        errors.append("exact_litter_pig_identity_required")
    if errors:
        return _result(False, "observation_preview_rejected", errors=sorted(set(errors))), 409
    digest = action_digest(action)
    effects = [{
        **row,
        "visible_identity": str(identities.get(row["pig_id"], {}).get("tag_number") or row["pig_id"]),
        "effect": "append_pig_observation_event",
        "purpose_change": False,
        "breeding_selection": False,
    } for row in action["observations"]]
    return _result(True, "observation_preview", action=action, preview_digest=digest,
                   observation_count=len(effects), observation_effects=effects), 200


def preview_authoritative(payload, *, actor_id, channel="application", connect_factory=None):
    action, errors = normalize_action(payload, channel=channel)
    if errors:
        return _result(False, "observation_preview_rejected", errors=errors), 409
    try:
        with _connect(connect_factory) as connection:
            with connection.cursor() as cursor:
                pig_ids = [row["pig_id"] for row in action["observations"]]
                cursor.execute("select pig_id,litter_id,coalesce(tag_number,'') from public.pigs where pig_id=any(%s) order by pig_id", (pig_ids,))
                identities = [{"pig_id": row[0], "litter_id": row[1], "tag_number": row[2]} for row in cursor.fetchall()]
    except Exception:
        return _result(False, "observation_store_unavailable"), 503
    result, status = preview_action(payload, channel=channel, identity_rows=identities)
    if status == 200:
        result["confirmation_binding"] = _confirmation_binding(result["preview_digest"], actor_id)
    return result, status


def execute_action(payload, *, actor_id, confirmation_binding, channel="application", connect_factory=None):
    actor_id = str(actor_id or "").strip()
    preview, status = preview_action(payload, channel=channel)
    if status != 200:
        return preview, status
    action = preview["action"]
    if not actor_id:
        return _result(False, "owner_identity_required"), 403
    if not _valid_confirmation(confirmation_binding, preview["preview_digest"], actor_id):
        return _result(False, "exact_preview_confirmation_required"), 409
    try:
        with _connect(connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set transaction isolation level serializable")
                cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", ("piglet-observation:" + action["idempotency_key"],))
                existing_keys = set()
                for index, item in enumerate(action["observations"]):
                    key = f"{action['idempotency_key']}:{item['pig_id']}:{index}"
                    cursor.execute("select 1 from public.pig_observation_events where idempotency_key=%s", (key,))
                    if cursor.fetchone(): existing_keys.add(key)
                _validate_and_insert(cursor, action, actor_id)
                readback = _readback(cursor, action, existing_keys=existing_keys)
    except ValueError as exc:
        return _result(False, str(exc)), 409
    except Exception as exc:
        if getattr(exc, "sqlstate", "") in {"40001", "40P01", "23505"}:
            return _result(False, "observation_concurrency_retry_required", rows_created=0), 409
        return _result(False, "observation_store_unavailable"), 503
    replay = all(row["replay"] for row in readback)
    return _result(True, "observations_replayed_withheld" if replay else "observations_recorded",
                   preview_digest=preview["preview_digest"], canonical_readback=readback,
                   rows_created=0 if replay else sum(not row["replay"] for row in readback)), 200 if replay else 201


def _validate_and_insert(cursor, action, actor_id):
    pig_ids = [row["pig_id"] for row in action["observations"]]
    cursor.execute("select pig_id,litter_id,coalesce(tag_number,'') from public.pigs where pig_id=any(%s) order by pig_id for share", (pig_ids,))
    identities = {row[0]: row for row in cursor.fetchall()}
    if set(identities) != set(pig_ids) or any(str(row[1]) != action["litter_id"] for row in identities.values()):
        raise ValueError("exact_litter_pig_identity_required")
    digest = action_digest(action)
    for index, item in enumerate(action["observations"]):
        key = f"{action['idempotency_key']}:{item['pig_id']}:{index}"
        event_id = "OBS-WEAN-" + hashlib.sha256(key.encode()).hexdigest()[:24].upper()
        cursor.execute("select observation_event_id,source_reference from public.pig_observation_events where idempotency_key=%s", (key,))
        existing = cursor.fetchone()
        if existing:
            try:
                existing_source = json.loads(str(existing[1] or "{}"))
            except (TypeError, ValueError):
                existing_source = {}
            if existing_source.get("digest") != digest:
                raise ValueError("observation_idempotency_conflict")
            continue
        supersedes = item["supersedes_observation_event_id"]
        if supersedes:
            cursor.execute("select 1 from public.pig_observation_events prior where prior.observation_event_id=%s and prior.pig_id=%s and not exists (select 1 from public.pig_observation_events correction where correction.supersedes_observation_event_id=prior.observation_event_id)", (supersedes, item["pig_id"]))
            if not cursor.fetchone():
                raise ValueError("invalid_observation_supersession")
        try:
            observed_at = datetime.combine(date.fromisoformat(item["observed_on"]), time(0), timezone.utc)
        except ValueError as exc:
            raise ValueError("invalid_observation_date") from exc
        if observed_at > datetime.now(timezone.utc):
            raise ValueError("future_observation_date_invalid")
        measurements = {"contract_version": CONTRACT_VERSION, "litter_id": action["litter_id"],
                        "context": action["source_context"], "traits": item["traits"],
                        "sentiment": item["sentiment"], "watch_flag": item["watch_flag"],
                        "automatic_classification": False,
                        "input_provenance": action["input_provenance"],
                        "source_reference": action["source_reference"]}
        severity = "attention" if item["sentiment"] in {"concerning", "mixed"} else "informational"
        cursor.execute("""insert into public.pig_observation_events(
            observation_event_id,pig_id,observed_at,observer_reference,observation_category,
            severity,factual_note,measurements_json,source_system,source_reference,
            idempotency_key,supersedes_observation_event_id)
            values(%s,%s,%s,%s,'other',%s,%s,%s::jsonb,'owner',%s,%s,%s)""",
            (event_id, item["pig_id"], observed_at, actor_id, severity, item["factual_note"],
             json.dumps(measurements, sort_keys=True),
             json.dumps({"digest": digest, "input_provenance": action["input_provenance"],
                         "source_reference": action["source_reference"]}, sort_keys=True), key, supersedes))


def _readback(cursor, action, existing_keys=None):
    digest = action_digest(action)
    result = []
    for index, item in enumerate(action["observations"]):
        key = f"{action['idempotency_key']}:{item['pig_id']}:{index}"
        cursor.execute("select observation_event_id,observed_at,recorded_at,observer_reference,factual_note,measurements_json from public.pig_observation_events where idempotency_key=%s", (key,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("canonical_observation_readback_missing")
        result.append({"observation_event_id": row[0], "pig_id": item["pig_id"],
                       "observed_at": row[1].isoformat(), "recorded_at": row[2].isoformat(),
                       "observer": row[3], "factual_note": row[4], "measurements": row[5],
                       "source_digest": digest, "replay": key in (existing_keys or set())})
    return result


def _connect(connect_factory=None):
    if connect_factory:
        return connect_factory(os.getenv(DATABASE_URL_ENV, ""))
    import psycopg
    return psycopg.connect(os.environ[DATABASE_URL_ENV], connect_timeout=5)


def _confirmation_secret():
    return str(os.getenv("OWNER_SESSION_SECRET") or os.getenv("SECRET_KEY") or "").encode()


def _confirmation_binding(digest, actor_id, *, now=None):
    now = now or datetime.now(timezone.utc)
    issued_at = int(now.timestamp())
    material = f"{CONTRACT_VERSION}|{digest}|{actor_id}|{issued_at}"
    secret = _confirmation_secret()
    signature = hmac.new(secret, material.encode(), hashlib.sha256).hexdigest() if secret else ""
    return {"contract_version": CONTRACT_VERSION, "preview_digest": digest,
            "actor_id": actor_id, "issued_at": issued_at, "signature": signature}


def _valid_confirmation(binding, digest, actor_id, *, now=None):
    if not isinstance(binding, dict): return False
    now = now or datetime.now(timezone.utc)
    try: issued_at = int(binding.get("issued_at"))
    except (TypeError, ValueError): return False
    age = int(now.timestamp()) - issued_at
    if age < 0 or age > PREVIEW_TTL_SECONDS: return False
    expected = _confirmation_binding(digest, actor_id, now=datetime.fromtimestamp(issued_at, timezone.utc))
    return (str(binding.get("preview_digest") or "") == digest
            and str(binding.get("actor_id") or "") == actor_id
            and bool(expected["signature"])
            and hmac.compare_digest(str(binding.get("signature") or ""), expected["signature"]))


def _result(success, status, **extra):
    return {"success": success, "status": status, "contract_version": CONTRACT_VERSION,
            "append_only": True, "changes_litter": False, "changes_lifecycle": False,
            "changes_medical": False, "changes_movement": False, "changes_purpose": False,
            "selects_breeding_pig": False, "contacts_customer": False, **extra}
