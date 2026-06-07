import hashlib
import json
import os
from datetime import datetime, timezone

from services.database_service import DATABASE_URL_ENV


FEEDBACK_TYPES = {
    "correct",
    "wrong_tool",
    "stale_or_missing_data",
    "bad_wording",
    "needs_follow_up",
}


def build_trace_id():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    digest = hashlib.sha1(stamp.encode("utf-8")).hexdigest()[:8].upper()
    return f"OSK-{stamp}-{digest}"


def hash_tool_result(value):
    payload = json.dumps(value or {}, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_trace(trace, database_url=None):
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"stored": False, "status": "not_configured"}

    try:
        import psycopg
    except ImportError:
        return {"stored": False, "status": "dependency_missing"}

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_traces (
                        trace_id,
                        channel,
                        session_id,
                        user_text,
                        intent,
                        confidence,
                        tool_name,
                        tool_args_json,
                        tool_result_summary,
                        tool_result_hash,
                        answer,
                        risk_level,
                        stale_warnings_json,
                        safety_notes_json,
                        links_json,
                        created_at
                    )
                    values (
                        %(trace_id)s,
                        %(channel)s,
                        %(session_id)s,
                        %(user_text)s,
                        %(intent)s,
                        %(confidence)s,
                        %(tool_name)s,
                        %(tool_args_json)s::jsonb,
                        %(tool_result_summary)s,
                        %(tool_result_hash)s,
                        %(answer)s,
                        %(risk_level)s,
                        %(stale_warnings_json)s::jsonb,
                        %(safety_notes_json)s::jsonb,
                        %(links_json)s::jsonb,
                        now()
                    )
                    """
                    ,
                    _trace_params(trace),
                )
        return {"stored": True, "status": "ok"}
    except Exception as exc:
        return {
            "stored": False,
            "status": "trace_write_failed",
            "error_type": exc.__class__.__name__,
        }


def build_feedback_id(trace_id, feedback_type):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    seed = f"{trace_id}:{feedback_type}:{stamp}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8].upper()
    return f"OSKFB-{stamp}-{digest}"


def record_trace_feedback(trace_id, payload, database_url=None):
    trace_id = _clean_text(trace_id, 96)
    feedback_type = _clean_text((payload or {}).get("feedback_type", ""), 64)
    if not trace_id:
        return {"success": False, "status": "trace_id_required"}, 400
    if feedback_type not in FEEDBACK_TYPES:
        return {
            "success": False,
            "status": "invalid_feedback_type",
            "allowed_feedback_types": sorted(FEEDBACK_TYPES),
        }, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing"}, 500

    params = {
        "feedback_id": build_feedback_id(trace_id, feedback_type),
        "trace_id": trace_id,
        "feedback_type": feedback_type,
        "notes": _clean_text((payload or {}).get("notes", ""), 500),
        "reviewed_by": _clean_text((payload or {}).get("reviewed_by", ""), 80),
        "channel": _clean_text((payload or {}).get("channel", ""), 40),
    }

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_trace_feedback (
                        feedback_id,
                        trace_id,
                        feedback_type,
                        notes,
                        reviewed_by,
                        channel,
                        created_at
                    )
                    values (
                        %(feedback_id)s,
                        %(trace_id)s,
                        %(feedback_type)s,
                        %(notes)s,
                        %(reviewed_by)s,
                        %(channel)s,
                        now()
                    )
                    """,
                    params,
                )
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "feedback_write_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "feedback_id": params["feedback_id"],
        "trace_id": trace_id,
        "feedback_type": feedback_type,
    }, 201


def list_recent_traces(limit=20, channel="", review="all", search="", database_url=None):
    parsed_limit = _bounded_limit(limit)
    parsed_review = _review_filter(review)
    parsed_search = _clean_text(search, 120)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured", "traces": []}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing", "traces": []}, 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                params = {
                    "channel": channel,
                    "limit": parsed_limit,
                    "search": f"%{parsed_search}%",
                }
                where_clause = _trace_list_where_clause(parsed_review, bool(parsed_search))
                if channel:
                    cursor.execute(
                        f"""
                        select trace_id, channel, session_id, user_text, intent, confidence,
                               tool_name, tool_result_summary, tool_result_hash, answer,
                               risk_level, stale_warnings_json, safety_notes_json, links_json, created_at,
                               feedback_type, feedback_notes, feedback_reviewed_by, feedback_created_at
                        from (
                            select t.trace_id, t.channel, t.session_id, t.user_text, t.intent,
                                   t.confidence, t.tool_name, t.tool_result_summary,
                                   t.tool_result_hash, t.answer, t.risk_level,
                                   t.stale_warnings_json, t.safety_notes_json, t.links_json, t.created_at,
                                   fb.feedback_type, fb.notes as feedback_notes,
                                   fb.reviewed_by as feedback_reviewed_by,
                                   fb.created_at as feedback_created_at
                            from public.oom_sakkie_traces t
                            left join lateral (
                                select feedback_type, notes, reviewed_by, created_at
                                from public.oom_sakkie_trace_feedback f
                                where f.trace_id = t.trace_id
                                order by created_at desc
                                limit 1
                            ) fb on true
                            where t.channel = %(channel)s
                        ) recent
                        {where_clause}
                        order by created_at desc
                        limit %(limit)s
                        """,
                        params,
                    )
                else:
                    cursor.execute(
                        f"""
                        select trace_id, channel, session_id, user_text, intent, confidence,
                               tool_name, tool_result_summary, tool_result_hash, answer,
                               risk_level, stale_warnings_json, safety_notes_json, links_json, created_at,
                               feedback_type, feedback_notes, feedback_reviewed_by, feedback_created_at
                        from (
                            select t.trace_id, t.channel, t.session_id, t.user_text, t.intent,
                                   t.confidence, t.tool_name, t.tool_result_summary,
                                   t.tool_result_hash, t.answer, t.risk_level,
                                   t.stale_warnings_json, t.safety_notes_json, t.links_json, t.created_at,
                                   fb.feedback_type, fb.notes as feedback_notes,
                                   fb.reviewed_by as feedback_reviewed_by,
                                   fb.created_at as feedback_created_at
                            from public.oom_sakkie_traces t
                            left join lateral (
                                select feedback_type, notes, reviewed_by, created_at
                                from public.oom_sakkie_trace_feedback f
                                where f.trace_id = t.trace_id
                                order by created_at desc
                                limit 1
                            ) fb on true
                        ) recent
                        {where_clause}
                        order by created_at desc
                        limit %(limit)s
                        """,
                        params,
                    )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "trace_read_failed",
            "error_type": exc.__class__.__name__,
            "traces": [],
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "count": len(rows),
        "limit": parsed_limit,
        "channel": channel,
        "review": parsed_review,
        "search": parsed_search,
        "traces": [_trace_row(row) for row in rows],
    }, 200


def get_trace_review_summary(channel="", days=14, database_url=None):
    parsed_days = _bounded_days(days)
    channel = _clean_text(channel, 40)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured"}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing"}, 500

    params = {"days": parsed_days, "channel": channel}
    channel_filter = "and t.channel = %(channel)s" if channel else ""
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    with recent as (
                        select t.trace_id, t.channel, t.tool_name, t.user_text, t.answer,
                               t.created_at, fb.feedback_type, fb.notes as feedback_notes,
                               fb.reviewed_by as feedback_reviewed_by,
                               fb.created_at as feedback_created_at
                        from public.oom_sakkie_traces t
                        left join lateral (
                            select feedback_type, notes, reviewed_by, created_at
                            from public.oom_sakkie_trace_feedback f
                            where f.trace_id = t.trace_id
                            order by created_at desc
                            limit 1
                        ) fb on true
                        where t.created_at >= now() - (%(days)s::text || ' days')::interval
                        {channel_filter}
                    )
                    select
                        count(*)::int as total_traces,
                        count(feedback_type)::int as reviewed_traces,
                        count(*) filter (where feedback_type is null)::int as unreviewed_traces,
                        count(*) filter (where feedback_type is not null and feedback_type <> 'correct')::int as problem_traces,
                        count(*) filter (where feedback_type = 'correct')::int as correct,
                        count(*) filter (where feedback_type = 'wrong_tool')::int as wrong_tool,
                        count(*) filter (where feedback_type = 'stale_or_missing_data')::int as stale_or_missing_data,
                        count(*) filter (where feedback_type = 'bad_wording')::int as bad_wording,
                        count(*) filter (where feedback_type = 'needs_follow_up')::int as needs_follow_up
                    from recent
                    """,
                    params,
                )
                totals = cursor.fetchone()
                cursor.execute(
                    f"""
                    with recent as (
                        select t.tool_name
                        from public.oom_sakkie_traces t
                        where t.created_at >= now() - (%(days)s::text || ' days')::interval
                        {channel_filter}
                    )
                    select coalesce(tool_name, '') as tool_name, count(*)::int as count
                    from recent
                    group by coalesce(tool_name, '')
                    order by count desc, tool_name asc
                    limit 8
                    """,
                    params,
                )
                tool_rows = cursor.fetchall()
                cursor.execute(
                    f"""
                    with recent as (
                        select t.trace_id, t.channel, t.tool_name, t.user_text, t.answer,
                               t.created_at, fb.feedback_type, fb.notes as feedback_notes,
                               fb.reviewed_by as feedback_reviewed_by,
                               fb.created_at as feedback_created_at
                        from public.oom_sakkie_traces t
                        left join lateral (
                            select feedback_type, notes, reviewed_by, created_at
                            from public.oom_sakkie_trace_feedback f
                            where f.trace_id = t.trace_id
                            order by created_at desc
                            limit 1
                        ) fb on true
                        where t.created_at >= now() - (%(days)s::text || ' days')::interval
                        {channel_filter}
                    )
                    select trace_id, channel, tool_name, user_text, answer, created_at,
                           feedback_type, feedback_notes, feedback_reviewed_by, feedback_created_at
                    from recent
                    where feedback_type is not null and feedback_type <> 'correct'
                    order by feedback_created_at desc nulls last, created_at desc
                    limit 5
                    """,
                    params,
                )
                problem_rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "review_summary_failed",
            "error_type": exc.__class__.__name__,
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "channel": channel,
        "days": parsed_days,
        "summary": _review_summary_row(totals),
        "tool_counts": [
            {"tool_name": row[0] or "clarification", "count": int(row[1] or 0)}
            for row in tool_rows
        ],
        "recent_problem_traces": [_problem_trace_row(row) for row in problem_rows],
    }, 200


def list_review_advisor_traces(limit=12, channel="", database_url=None):
    parsed_limit = _bounded_limit(limit)
    channel = _clean_text(channel, 40)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {
            "success": False,
            "configured": False,
            "status": "not_configured",
            "issue_traces": [],
            "unreviewed_traces": [],
        }, 503

    try:
        import psycopg
    except ImportError:
        return {
            "success": False,
            "configured": True,
            "status": "dependency_missing",
            "issue_traces": [],
            "unreviewed_traces": [],
        }, 500

    params = {"channel": channel, "limit": parsed_limit}
    channel_filter = "where t.channel = %(channel)s" if channel else ""
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    with recent as (
                        select t.trace_id, t.channel, t.session_id, t.user_text, t.intent,
                               t.confidence, t.tool_name, t.tool_result_summary,
                               t.tool_result_hash, t.answer, t.risk_level,
                               t.stale_warnings_json, t.safety_notes_json, t.links_json, t.created_at,
                               fb.feedback_type, fb.notes as feedback_notes,
                               fb.reviewed_by as feedback_reviewed_by,
                               fb.created_at as feedback_created_at
                        from public.oom_sakkie_traces t
                        left join lateral (
                            select feedback_type, notes, reviewed_by, created_at
                            from public.oom_sakkie_trace_feedback f
                            where f.trace_id = t.trace_id
                            order by created_at desc
                            limit 1
                        ) fb on true
                        {channel_filter}
                    ),
                    candidates as (
                        select 'issues' as queue_kind, *
                        from recent
                        where feedback_type is not null and feedback_type <> 'correct'
                        union all
                        select 'unreviewed' as queue_kind, *
                        from recent
                        where feedback_type is null
                    ),
                    ranked as (
                        select *,
                               row_number() over (
                                   partition by queue_kind
                                   order by coalesce(feedback_created_at, created_at) desc nulls last,
                                            created_at desc
                               ) as rn
                        from candidates
                    )
                    select queue_kind, trace_id, channel, session_id, user_text, intent, confidence,
                           tool_name, tool_result_summary, tool_result_hash, answer,
                           risk_level, stale_warnings_json, safety_notes_json, links_json, created_at,
                           feedback_type, feedback_notes, feedback_reviewed_by, feedback_created_at
                    from ranked
                    where rn <= %(limit)s
                    order by case when queue_kind = 'issues' then 0 else 1 end,
                             coalesce(feedback_created_at, created_at) desc nulls last,
                             created_at desc
                    """,
                    params,
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "advisor_trace_read_failed",
            "error_type": exc.__class__.__name__,
            "issue_traces": [],
            "unreviewed_traces": [],
        }, 503

    issue_traces = []
    unreviewed_traces = []
    for row in rows:
        queue_kind = row[0]
        trace = _trace_row(row[1:])
        if queue_kind == "issues":
            issue_traces.append(trace)
        else:
            unreviewed_traces.append(trace)

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "channel": channel,
        "limit": parsed_limit,
        "issue_traces": issue_traces,
        "unreviewed_traces": unreviewed_traces,
    }, 200


def _bounded_limit(value):
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = 20
    return max(1, min(limit, 100))


def _bounded_days(value):
    try:
        days = int(value)
    except (TypeError, ValueError):
        days = 14
    return max(1, min(days, 60))


def _review_filter(value):
    review = _clean_text(value, 32).lower()
    if review in {"all", "reviewed", "unreviewed", "issues"}:
        return review
    return "all"


def _review_where_clause(review):
    if review == "reviewed":
        return "where feedback_type is not null"
    if review == "unreviewed":
        return "where feedback_type is null"
    if review == "issues":
        return "where feedback_type is not null and feedback_type <> 'correct'"
    return ""


def _trace_list_where_clause(review, has_search):
    clauses = []
    review_clause = _review_where_clause(review)
    if review_clause:
        clauses.append(review_clause.replace("where ", "", 1))
    if has_search:
        clauses.append(
            "("
            "trace_id ilike %(search)s or "
            "coalesce(user_text, '') ilike %(search)s or "
            "coalesce(answer, '') ilike %(search)s or "
            "coalesce(tool_name, '') ilike %(search)s"
            ")"
        )
    if not clauses:
        return ""
    return "where " + " and ".join(clauses)


def _trace_row(row):
    (
        trace_id,
        channel,
        session_id,
        user_text,
        intent,
        confidence,
        tool_name,
        tool_result_summary,
        tool_result_hash,
        answer,
        risk_level,
        stale_warnings,
        safety_notes,
        links,
        created_at,
        feedback_type,
        feedback_notes,
        feedback_reviewed_by,
        feedback_created_at,
    ) = row
    return {
        "trace_id": trace_id,
        "channel": channel,
        "session_id": session_id,
        "user_text": user_text,
        "intent": intent,
        "confidence": float(confidence or 0),
        "tool_name": tool_name,
        "tool_result_summary": tool_result_summary,
        "tool_result_hash": tool_result_hash,
        "answer": answer,
        "risk_level": int(risk_level or 0),
        "stale_warnings": stale_warnings or [],
        "safety_notes": safety_notes or [],
        "links": links or [],
        "created_at": created_at.isoformat() if created_at else "",
        "latest_feedback": _feedback_row(
            feedback_type,
            feedback_notes,
            feedback_reviewed_by,
            feedback_created_at,
        ),
    }


def _trace_params(trace):
    return {
        "trace_id": trace.get("trace_id", ""),
        "channel": trace.get("channel", ""),
        "session_id": trace.get("session_id", ""),
        "user_text": trace.get("user_text", ""),
        "intent": trace.get("intent", ""),
        "confidence": trace.get("confidence", 0),
        "tool_name": trace.get("tool_name", ""),
        "tool_args_json": json.dumps(trace.get("tool_args_json") or {}, separators=(",", ":")),
        "tool_result_summary": trace.get("tool_result_summary", ""),
        "tool_result_hash": trace.get("tool_result_hash", ""),
        "answer": trace.get("answer", ""),
        "risk_level": int(trace.get("risk_level", 0) or 0),
        "stale_warnings_json": json.dumps(trace.get("stale_warnings_json") or [], separators=(",", ":")),
        "safety_notes_json": json.dumps(trace.get("safety_notes_json") or [], separators=(",", ":")),
        "links_json": json.dumps(trace.get("links_json") or [], separators=(",", ":")),
    }


def _feedback_row(feedback_type, notes, reviewed_by, created_at):
    if not feedback_type:
        return None
    return {
        "feedback_type": feedback_type,
        "notes": notes or "",
        "reviewed_by": reviewed_by or "",
        "created_at": created_at.isoformat() if created_at else "",
    }


def _clean_text(value, max_length):
    text = str(value or "").replace("\x00", "").strip()
    return text[:max_length]


def _review_summary_row(row):
    if not row:
        row = (0, 0, 0, 0, 0, 0, 0, 0, 0)
    (
        total_traces,
        reviewed_traces,
        unreviewed_traces,
        problem_traces,
        correct,
        wrong_tool,
        stale_or_missing_data,
        bad_wording,
        needs_follow_up,
    ) = row
    total = int(total_traces or 0)
    reviewed = int(reviewed_traces or 0)
    problems = int(problem_traces or 0)
    review_rate = round((reviewed / total) * 100, 1) if total else 0.0
    problem_rate = round((problems / reviewed) * 100, 1) if reviewed else 0.0
    return {
        "total_traces": total,
        "reviewed_traces": reviewed,
        "unreviewed_traces": int(unreviewed_traces or 0),
        "problem_traces": problems,
        "review_rate_pct": review_rate,
        "problem_rate_pct": problem_rate,
        "feedback_counts": {
            "correct": int(correct or 0),
            "wrong_tool": int(wrong_tool or 0),
            "stale_or_missing_data": int(stale_or_missing_data or 0),
            "bad_wording": int(bad_wording or 0),
            "needs_follow_up": int(needs_follow_up or 0),
        },
    }


def _problem_trace_row(row):
    (
        trace_id,
        channel,
        tool_name,
        user_text,
        answer,
        created_at,
        feedback_type,
        feedback_notes,
        feedback_reviewed_by,
        feedback_created_at,
    ) = row
    return {
        "trace_id": trace_id,
        "channel": channel,
        "tool_name": tool_name or "clarification",
        "user_text": user_text or "",
        "answer": answer or "",
        "created_at": created_at.isoformat() if created_at else "",
        "latest_feedback": _feedback_row(
            feedback_type,
            feedback_notes,
            feedback_reviewed_by,
            feedback_created_at,
        ),
    }
