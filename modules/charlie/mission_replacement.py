"""Owner-gated, atomic many-to-one CHARLIE mission replacement contract."""

import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone

from modules.charlie.adaptive_orchestration import validate_orchestration_binding


VERSION = "charlie_many_to_one_replacement_v1"
NON_RUNNABLE_PREDECESSOR_STATUSES = {"new", "triaged", "planned", "blocked", "pr_ready", "paused"}
SUCCESSOR_STATUS = "paused"
MAX_AUTHORIZATION_SECONDS = 900


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _iso(value):
    if isinstance(value, datetime):
        value = value.astimezone(timezone.utc)
        return value.isoformat().replace("+00:00", "Z")
    return str(value or "").strip()


def prepare_many_to_one_replacement(successor_contract, predecessors):
    contract = dict(successor_contract or {})
    predecessor_rows = [dict(item or {}) for item in (predecessors or [])]
    required_contract = ("mission_id", "status", "raw_text", "title", "urgency", "mission_type", "approval_level", "metadata_json")
    missing = [key for key in required_contract if contract.get(key) in (None, "")]
    if missing:
        raise ValueError("replacement_successor_contract_incomplete:" + ",".join(missing))
    if contract["status"] != SUCCESSOR_STATUS:
        raise ValueError("replacement_successor_status_not_paused")
    metadata = contract.get("metadata_json") if isinstance(contract.get("metadata_json"), dict) else {}
    binding = validate_orchestration_binding(metadata.get("orchestration"), metadata.get("agent_workflow"))
    stored_binding = metadata.get("orchestration_binding") if isinstance(metadata.get("orchestration_binding"), dict) else {}
    if not binding.get("valid") or stored_binding.get("validated") is not True:
        raise ValueError("replacement_successor_orchestration_invalid")
    if stored_binding.get("generation_identity") != (metadata.get("orchestration") or {}).get("generation_identity"):
        raise ValueError("replacement_successor_orchestration_invalid")
    if not predecessor_rows:
        raise ValueError("replacement_predecessor_allowlist_required")
    required_predecessor = ("mission_id", "expected_status", "expected_content_digest", "expected_metadata_generation", "unfinished_value_reference")
    for item in predecessor_rows:
        if any(item.get(key) in (None, "") for key in required_predecessor):
            raise ValueError("replacement_predecessor_contract_incomplete")
        if item["expected_status"] not in NON_RUNNABLE_PREDECESSOR_STATUSES:
            raise ValueError("replacement_predecessor_status_runnable_or_unsupported")
        if len(str(item["expected_content_digest"])) != 64:
            raise ValueError("replacement_predecessor_content_digest_invalid")
    predecessor_rows.sort(key=lambda item: item["mission_id"])
    ids = [item["mission_id"] for item in predecessor_rows]
    if len(ids) != len(set(ids)):
        raise ValueError("replacement_duplicate_predecessor")
    contract_canonical = _canonical(contract)
    predecessors_canonical = _canonical(predecessor_rows)
    contract_digest = _sha(contract_canonical)
    predecessor_set_digest = _sha(predecessors_canonical)
    replacement_identity = "CHARLIE-REPLACEMENT-BATCH-" + _sha(
        f"{VERSION}|{contract_digest}|{predecessor_set_digest}"
    )[:24].upper()
    transaction_digest = _sha(
        f"{VERSION}|{replacement_identity}|{contract_digest}|{predecessor_set_digest}"
    )
    return {
        "version": VERSION,
        "replacement_identity": replacement_identity,
        "contract_canonical": contract_canonical,
        "predecessors_canonical": predecessors_canonical,
        "contract_digest": contract_digest,
        "predecessor_set_digest": predecessor_set_digest,
        "transaction_digest": transaction_digest,
        "successor_mission_id": contract["mission_id"],
        "predecessor_mission_ids": ids,
    }


def create_replacement_owner_authorization(prepared, *, owner_principal, secret, issued_at=None, expires_at=None):
    owner_principal = str(owner_principal or "").strip()
    secret = str(secret or "")
    if not owner_principal or len(secret) < 32:
        raise ValueError("replacement_owner_authority_not_configured")
    issued = issued_at or datetime.now(timezone.utc)
    expires = expires_at or (issued + timedelta(minutes=10))
    if not isinstance(issued, datetime) or not isinstance(expires, datetime):
        raise ValueError("replacement_owner_authorization_time_invalid")
    if expires <= issued or (expires - issued).total_seconds() > MAX_AUTHORIZATION_SECONDS:
        raise ValueError("replacement_owner_authorization_window_invalid")
    payload = {
        "version": VERSION,
        "replacement_identity": prepared["replacement_identity"],
        "contract_digest": prepared["contract_digest"],
        "predecessor_set_digest": prepared["predecessor_set_digest"],
        "transaction_digest": prepared["transaction_digest"],
        "owner_identity_hash": _sha(owner_principal),
        "issued_at": _iso(issued),
        "expires_at": _iso(expires),
    }
    signature = hmac.new(secret.encode("utf-8"), _canonical(payload).encode("utf-8"), hashlib.sha256).hexdigest()
    return {**payload, "signature": signature, "authorization_digest": _sha(_canonical({**payload, "signature": signature}))}


def validate_replacement_owner_authorization(prepared, authorization, *, secret, now=None, allow_expired=False):
    authorization = dict(authorization or {})
    signature = str(authorization.pop("signature", ""))
    authorization_digest = str(authorization.pop("authorization_digest", ""))
    expected_fields = {
        "version": VERSION,
        "replacement_identity": prepared["replacement_identity"],
        "contract_digest": prepared["contract_digest"],
        "predecessor_set_digest": prepared["predecessor_set_digest"],
        "transaction_digest": prepared["transaction_digest"],
    }
    if any(authorization.get(key) != value for key, value in expected_fields.items()):
        raise ValueError("replacement_owner_authorization_binding_invalid")
    secret = str(secret or "")
    if len(secret) < 32:
        raise ValueError("replacement_owner_authority_not_configured")
    expected = hmac.new(secret.encode("utf-8"), _canonical(authorization).encode("utf-8"), hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected):
        raise ValueError("replacement_owner_authorization_signature_invalid")
    full = {**authorization, "signature": signature}
    if not hmac.compare_digest(authorization_digest, _sha(_canonical(full))):
        raise ValueError("replacement_owner_authorization_digest_invalid")
    try:
        issued = datetime.fromisoformat(authorization["issued_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(authorization["expires_at"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("replacement_owner_authorization_time_invalid") from exc
    observed = now or datetime.now(timezone.utc)
    if issued > observed + timedelta(seconds=30) or (expires <= observed and not allow_expired) or expires > issued + timedelta(seconds=MAX_AUTHORIZATION_SECONDS):
        raise ValueError("replacement_owner_authorization_stale")
    return {**full, "authorization_digest": authorization_digest}


def record_replacement_owner_authorization(prepared, authorization, *, database_url=None, connect_factory=None, secret=None, expected_owner_identity_hash=None):
    validated = validate_replacement_owner_authorization(
        prepared, authorization,
        secret=secret if secret is not None else os.getenv("CHARLIE_MISSION_REPLACEMENT_AUTH_SECRET", ""),
    )
    expected_owner = str(expected_owner_identity_hash if expected_owner_identity_hash is not None else os.getenv("CHARLIE_MISSION_REPLACEMENT_OWNER_IDENTITY_HASH", "")).strip()
    if len(expected_owner) != 64 or not hmac.compare_digest(validated["owner_identity_hash"], expected_owner):
        raise ValueError("replacement_owner_identity_not_authorized")
    url = str(database_url if database_url is not None else os.getenv("CHARLIE_MISSION_REPLACEMENT_AUTHORIZER_DATABASE_URL", "")).strip()
    if not url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503
    signed = {key: value for key, value in validated.items() if key != "authorization_digest"}
    canonical = _canonical(signed)
    try:
        connection = connect_factory(url) if connect_factory else _connect(url)
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select public.append_charlie_mission_replacement_authorization(%s,%s)",
                    (canonical, validated["authorization_digest"]),
                )
                recorded = cursor.fetchone()[0]
    except Exception as exc:
        return {"success": False, "status": "replacement_owner_authorization_record_failed", "error_type": exc.__class__.__name__, "error_code": getattr(exc, "sqlstate", "") or ""}, 409
    return {"success": True, "status": "replacement_owner_authorization_recorded", "authorization_digest": recorded}, 201


def _read_exact_replay(prepared, database_url, connect_factory=None):
    connection = connect_factory(database_url) if connect_factory else _connect(database_url)
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """select result_json from public.charlie_mission_replacement_batches
                   where replacement_identity=%s and successor_mission_id=%s
                     and contract_digest=%s and predecessor_set_digest=%s and transaction_digest=%s""",
                (prepared["replacement_identity"], prepared["successor_mission_id"], prepared["contract_digest"],
                 prepared["predecessor_set_digest"], prepared["transaction_digest"]),
            )
            row = cursor.fetchone()
    return ({**dict(row[0]), "replayed": True, "rows_changed": 0} if row else None)


def execute_many_to_one_replacement(successor_contract, predecessors, authorization, *, database_url=None, connect_factory=None, secret=None):
    prepared = prepare_many_to_one_replacement(successor_contract, predecessors)
    auth_secret = secret if secret is not None else os.getenv("CHARLIE_MISSION_REPLACEMENT_AUTH_SECRET", "")
    validated = validate_replacement_owner_authorization(
        prepared,
        authorization,
        secret=auth_secret,
        allow_expired=True,
    )
    url = str(database_url if database_url is not None else os.getenv("CHARLIE_MISSION_REPLACEMENT_DATABASE_URL", "")).strip()
    if not url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured"}, 503
    try:
        replay = _read_exact_replay(prepared, url, connect_factory)
    except Exception:
        replay = None
    if replay:
        return replay, 200
    validated = validate_replacement_owner_authorization(prepared, validated, secret=auth_secret)
    try:
        for attempt in range(2):
            connection = connect_factory(url) if connect_factory else _connect(url)
            try:
                with connection:
                    with connection.cursor() as cursor:
                        cursor.execute("set local transaction isolation level serializable")
                        cursor.execute(
                    """select public.apply_charlie_many_to_one_replacement(
                       %(identity)s,%(contract)s,%(predecessors)s,%(contract_digest)s,
                       %(predecessor_digest)s,%(transaction_digest)s,%(authorization)s::jsonb)""",
                    {
                        "identity": prepared["replacement_identity"], "contract": prepared["contract_canonical"],
                        "predecessors": prepared["predecessors_canonical"], "contract_digest": prepared["contract_digest"],
                        "predecessor_digest": prepared["predecessor_set_digest"], "transaction_digest": prepared["transaction_digest"],
                        "authorization": json.dumps(validated, sort_keys=True),
                    },
                        )
                        result = cursor.fetchone()[0]
                break
            except Exception as exc:
                if getattr(exc, "sqlstate", "") == "40001" and attempt == 0:
                    continue
                raise
    except Exception as exc:
        return {"success": False, "status": "many_to_one_replacement_rejected", "error_type": exc.__class__.__name__, "error_code": getattr(exc, "sqlstate", "") or "", "error_status": str(exc).splitlines()[0][:200], "transaction_digest": prepared["transaction_digest"]}, 409
    return dict(result or {}), 200 if result.get("replayed") else 201


def _connect(database_url):
    import psycopg
    return psycopg.connect(database_url, connect_timeout=5)
