"""Shared source chronology fence for health intake, admission and confirmation.

Source locks precede claim/domain locks. Borrowed connections never commit or
close the enclosing transaction. No source snapshot grants provider authority.
"""
from copy import deepcopy
import hashlib
import json

SOURCE = "oom_sakkie_herdmaster_health_loss_runtime"
SOURCE_BOUND = 1024


class SourceConflict(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise SourceConflict(reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        default=str).encode()).hexdigest()


def record_body(value):
    return {key: deepcopy(item) for key, item in value.items()
        if not key.startswith("_") and key != "card_message_id"}


def predecessor(value):
    if value is None:
        return None
    return str(value.get("_source_predecessor_digest") or digest(record_body(value)))


def related_missions(value):
    missions = {str(value.get("mission_id") or ""), str(value.get("target_mission_id") or "")}
    missions.update(str(item) for item in value.get("consumed_context_missions") or ())
    missions.update(str(item) for item in value.get("superseded_duplicate_missions") or ())
    missions.update(str(item.get("mission_id") or "") for item in
        value.get("superseded_duplicate_bindings") or () if isinstance(item, dict))
    return sorted(missions - {""})


def lock_sources(cur, owner, chat, missions):
    require(bool(owner) and str(owner) == str(chat) and 0 < len(missions) <= 128,
        "health_source_lock_identity_unproven")
    keys = sorted({"herdmaster-health-source:" + digest([str(owner), str(chat), str(mission)])
        for mission in missions})
    for key in keys:
        cur.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", (key,))


def begin(cur):
    # READ COMMITTED takes the chronology snapshot after a waited source lock.
    cur.execute("set transaction isolation level read committed")
    cur.execute("set local statement_timeout='5000ms'")
    cur.execute("set local lock_timeout='5000ms'")


def read_history(cur, missions):
    cur.execute("""select review_event_id,created_at,review_json->'herdmaster_health_loss'
        from public.sam_live_stock_conversation_review_events where event_source=%s and (
          review_json->'herdmaster_health_loss'->>'mission_id'=any(%s)
          or review_json->'herdmaster_health_loss'->'consumed_context_missions' ?| %s
          or review_json->'herdmaster_health_loss'->'superseded_duplicate_missions' ?| %s
          or exists (select 1 from jsonb_array_elements(coalesce(review_json->'herdmaster_health_loss'
            ->'superseded_duplicate_bindings','[]'::jsonb)) b where b->>'mission_id'=any(%s)))
        order by created_at desc,review_event_id desc limit %s""",
        (SOURCE, missions, missions, missions, missions, SOURCE_BOUND + 1))
    rows = cur.fetchall()
    require(len(rows) <= SOURCE_BOUND, "health_source_history_overflow")
    require(all(isinstance(row[2], dict) for row in rows), "health_source_history_invalid")
    return [{"review_event_id": row[0], "created_at": row[1], "record": row[2]} for row in rows]


def latest_for(history, mission):
    return next((item["record"] for item in history if item["record"].get("mission_id") == mission), None)


def require_current(history, source):
    latest = latest_for(history, source["mission_id"])
    require(latest is not None and digest(latest) == predecessor(source), "health_source_predecessor_changed")
    require(all((item["record"].get("owner_user_id"), item["record"].get("chat_id")) ==
        (source["owner_user_id"], source["chat_id"]) for item in history), "health_source_principal_changed")
    for item in history:
        row = item["record"]
        if row.get("mission_id") != source["mission_id"]:
            require(source["mission_id"] not in superseded_missions(row), "health_source_superseded")
    return latest


def check_append(history, lifecycle, expected_sources):
    mission = lifecycle["mission_id"]
    latest = latest_for(history, mission)
    if latest == lifecycle:
        return False
    require(mission in expected_sources, "health_source_predecessor_required")
    for target in related_missions(lifecycle):
        require(not any(item["record"].get("mission_id") != mission
            and target in superseded_missions(item["record"]) for item in history),
            "health_source_append_superseded")
        prior = latest_for(history, target)
        expected = expected_sources.get(target)
        require(target in expected_sources and (digest(prior) if prior is not None else None) == expected,
            "health_source_predecessor_changed")
        require(prior is None or prior.get("status") not in {"completed", "contained"},
            "health_source_terminal_predecessor")
        if prior is not None:
            require((prior.get("owner_user_id"), prior.get("chat_id")) ==
                (lifecycle["owner_user_id"], lifecycle["chat_id"]), "health_source_principal_changed")
    return True


class BorrowedConnection:
    def __init__(self, connection): self.connection = connection
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return self.connection.cursor()
    def execute(self, *args, **kwargs): return self.connection.execute(*args, **kwargs)


class TransactionReader:
    transaction_managed = True
    def __init__(self, connection): self.connection = connection
    def __call__(self, _unused_database_url=None): return BorrowedConnection(self.connection)


def append_lifecycle(lifecycle, expected_sources, write, *, connect_factory):
    """Serialize a captured predecessor and its append in the caller transaction.

    ``write`` must use the borrowed factory. Any swallowed lower-layer failure
    becomes an exception so a caller-owned domain transaction cannot commit it.
    """
    body = record_body(lifecycle)
    expected = dict(expected_sources or {})
    expected.setdefault(body["mission_id"], None)
    with connect_factory() as db, db.cursor() as cur:
        if not getattr(connect_factory, "transaction_managed", False):
            begin(cur)
        missions = related_missions(body)
        lock_sources(cur, body["owner_user_id"], body["chat_id"], missions)
        rows = read_history(cur, missions)
        if not check_append(rows, body, expected):
            return {"success": True, "created": False, "status": "health_source_append_replayed"}
        # The exact expected predecessor is captured before any expensive work;
        # it is never silently replaced with the latest row after waiting.
        cur.execute("select clock_timestamp()")
        created_at = cur.fetchone()[0]
        # A transaction may begin before waiting for another appender. now()
        # would then place this new event behind that committed predecessor.
        require(all(item["created_at"] < created_at for item in rows), "health_source_clock_not_after_predecessor")
        result = write(body, TransactionReader(db), created_at)
        if result.get("success") is not True:
            raise RuntimeError("health_source_append_failed")
        rows = read_history(cur, [body["mission_id"]])
        if latest_for(rows, body["mission_id"]) != body:
            raise RuntimeError("health_source_append_readback_failed")
    if expected_sources is not None:
        expected_sources[body["mission_id"]] = digest(body)
    return result


def superseded_missions(row):
    return set(row.get("consumed_context_missions") or ()) | set(row.get("superseded_duplicate_missions") or ()) | {
        str(item.get("mission_id") or "") for item in row.get("superseded_duplicate_bindings") or ()
        if isinstance(item, dict)}


def require_applicable_welfare_result(lifecycle, result):
    if result.get("success") is True:
        return
    identity = ((lifecycle.get("preview") or {}).get("evaluator") or {}).get("identity") or {}
    if not identity.get("pig_id") and result.get("status") == "welfare_case_identity_incomplete":
        return  # An ordinary pending clarification has no pig-bound welfare write.
    raise RuntimeError("health_source_welfare_append_failed")
