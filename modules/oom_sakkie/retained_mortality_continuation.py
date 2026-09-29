"""Owner-requested successor to an expired, verifiably delivered mortality card.

The old token and window stay immutable. A native authenticated expired-card
click requests a new review; it never confirms the new generation. Existing
source, claim, operational audit and provider rails carry the entire lineage.
"""
from copy import deepcopy
from datetime import timedelta
import json

from modules.oom_sakkie import herdmaster_source_transaction as tx
from modules.oom_sakkie import retained_mortality_history as history
from modules.oom_sakkie import retained_mortality_presentation as presentation

CONTRACT = "retained_mortality_expired_confirmation.v1"
EVENT = "retained_mortality_confirmation_continued"
KEY = "retained-mortality-continuation:"
FIELD = "confirmation_continuation"
BOUND = 128


class ContinuationPresentation(presentation.RetainedMortalityPresentation):
    """Internal rendering hint; the database audit is rechecked at admission."""


def _rows(cur, sql, args):
    return presentation._read_rows(cur, sql, args)


def _identity(claim):
    return {"claim_hash": history._sha(claim["callback_token"]), **{key: claim[key] for key in ("action_kind", "owner_user_id",
        "private_chat_id", "mission_id", "provider_message_id", "preview_digest",
        "evidence_generation", "preview_payload")}}


def _archive(claim):
    return {"claim_hash": history._sha(claim["callback_token"]),
        **{key: value for key, value in claim.items() if key != "callback_token"}}


def _base(payload):
    return {key: value for key, value in payload.items() if key != FIELD}


def read_claims(cur, source, source_history):
    bridge = source["retained_repreview"]
    providers = sorted({str(row["record"].get("provider_message_id") or "") for row in source_history} - {""})
    rows = _rows(cur, """select to_jsonb(c) from app_private.oom_protected_action_claims c
        where mission_id=any(%s) or (owner_user_id=%s and private_chat_id=%s and
          (provider_message_id=any(%s) or preview_payload->'provider_message_ids' ?| %s))
        order by callback_token limit 129""", ([source["mission_id"], bridge["claim_mission_id"]],
            source["owner_user_id"], source["chat_id"], providers, providers))
    tx.require(0 < len(rows) <= BOUND, "retained_continuation_claim_history_bound")
    return rows


def _delivered_expired(claim, now):
    """Only a proven delivered, never-confirmed decision can be continued."""
    result = claim.get("delivery_result") or {}
    tx.require(claim["status"] == "expired" and history._time(claim["expires_at"]) <= now
        and claim["delivery_state"] == "delivery_confirmed"
        and bool(claim["preview_card_message_id"]) and bool(claim["delivery_attempt_id"])
        and all(claim.get(key) is not None for key in
            ("delivery_attempted_at", "provider_accepted_at", "delivery_confirmed_at"))
        and all(claim.get(key) is None for key in ("delivery_ambiguous_at",
            "confirmation_provider_message_id", "confirmation_provider_timestamp", "result_payload", "completed_at"))
        and result.get("success") is True and result.get("telegram_sends") == 1
        and result.get("telegram_edits", 0) == 0
        and str(result.get("telegram_message_id") or "") == claim["preview_card_message_id"]
        and history._time(claim["delivery_attempted_at"]) <= history._time(claim["provider_accepted_at"])
        <= history._time(claim["delivery_confirmed_at"]) <= history._time(claim["expires_at"]) <= now,
        "retained_continuation_predecessor_not_delivered_expired")


def _window(cur, claim):
    h = history._sha(claim["callback_token"])
    rows = _rows(cur, """select to_jsonb(e) from public.operational_events e
        where aggregate_type='protected_action_claim' and aggregate_id=%s
        and event_type=%s order by occurred_at,event_id limit 2""", (h, history.WINDOW))
    row = history._one(rows, "retained_continuation_window")
    p = row["payload_json"]
    tx.require(row["event_id"] == "OOM-MORTALITY-WINDOW-" + h[:32].upper()
        and row["idempotency_key"] == presentation.KEY_PREFIX + h
        and row["source_system"] == "oom_sakkie" and row["authority_tier"] == "bounded_auto"
        and row["actor_id"] == "retained_mortality_presentation"
        and row["correlation_id"] == claim["mission_id"]
        and p.get("contract_version") == presentation.CONTRACT and p.get("claim_hash") == h
        and p.get("preview_digest") == claim["preview_digest"]
        and p.get("evidence_generation") == claim["evidence_generation"]
        and p.get("operation_id") == claim["preview_payload"]["operation_id"]
        and p.get("attempt_id") == claim["delivery_attempt_id"]
        and p.get("ttl_seconds") == history.TTL_SECONDS and p.get("one_time_only") is True
        and history._time(p["started_at"]) == history._time(claim["delivery_attempted_at"])
        == history._time(row["occurred_at"])
        and history._time(p["new_expires_at"]) == history._time(claim["expires_at"])
        == history._time(p["started_at"]) + timedelta(seconds=history.TTL_SECONDS),
        "retained_continuation_window_changed")
    return row


def validate_lineage(cur, source, claims, current, now, source_history):
    """Complete, bounded, linear generations; no other related claim is allowed."""
    from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
    by_hash = {history._sha(c["callback_token"]): c for c in claims}
    tx.require(len(by_hash) == len(claims), "retained_continuation_duplicate_claim")
    seen, links, windows = set(), [], []
    child = current
    while True:
        h = history._sha(child["callback_token"])
        tx.require(h not in seen and h in by_hash and by_hash[h] == child,
            "retained_continuation_lineage_cycle")
        seen.add(h)
        tx.require(child["action_kind"] == "mortality" and child["preview_digest"] ==
            canonical_preview_digest("mortality", child["preview_payload"])
            and all(child[key] == current[key] for key in ("owner_user_id", "private_chat_id",
                "mission_id", "provider_message_id", "evidence_generation"))
            and _base(child["preview_payload"]) == _base(current["preview_payload"]),
            "retained_continuation_material_or_principal_changed")
        link = child["preview_payload"].get(FIELD)
        if link is None:
            break
        tx.require(isinstance(link, dict) and set(link) == {"contract_version", "predecessor_claim_hash"}
            and link["contract_version"] == CONTRACT and link["predecessor_claim_hash"] in by_hash,
            "retained_continuation_link_unproven")
        parent = by_hash[link["predecessor_claim_hash"]]
        _delivered_expired(parent, now)
        window = _window(cur, parent)
        windows.append(window["event_id"])
        audits = _rows(cur, """select to_jsonb(e) from public.operational_events e
            where idempotency_key=%s limit 2""", (KEY + link["predecessor_claim_hash"],))
        audit = history._one(audits, "retained_continuation_audit")
        p = audit["payload_json"]
        before, after = p.get("source_before") or {}, p.get("source_after") or {}
        presentation._validate_source(before, parent)
        presentation._validate_source(after, child)
        tx.require(all(any(tx.record_body(row["record"]) == body for row in source_history)
            for body in (before, after)), "retained_continuation_source_edge_missing")
        tx.require(audit["event_type"] == EVENT and audit["aggregate_type"] == "protected_action_claim"
            and audit["aggregate_id"] == h and audit["source_system"] == "oom_sakkie"
            and audit["actor_type"] == "owner" and audit["actor_id"] == current["owner_user_id"]
            and audit["authority_tier"] == "owner_approved" and audit["correlation_id"] == current["mission_id"]
            and p.get("contract_version") == CONTRACT and p.get("predecessor") == _archive(parent)
            and p.get("successor") == _identity(child)
            and p.get("source_before", {}).get("mission_id") == source["mission_id"]
            and p.get("source_after", {}).get("mission_id") == source["mission_id"]
            and p.get("source_before", {}).get("preview") == source["preview"]
            and p.get("source_after", {}).get("preview") == source["preview"]
            and p.get("request", {}).get("card_message_id") == parent["preview_card_message_id"]
            and bool(p.get("request", {}).get("provider_message_id"))
            and p["request"]["provider_message_id"] == audit["causation_id"]
            and history._time(parent["expires_at"]) <= history._time(p["request"]["received_at"])
            <= history._time(audit["occurred_at"]) <= now,
            "retained_continuation_audit_changed")
        links.append(audit)
        child = parent
    tx.require(seen == set(by_hash), "retained_continuation_competing_claim")
    tx.require(all(newer["payload_json"]["source_before"] == older["payload_json"]["source_after"]
        for newer, older in zip(links, links[1:])), "retained_continuation_source_edge_changed")
    for c in claims:
        h = history._sha(c["callback_token"])
        audits = _rows(cur, """select to_jsonb(e) from public.operational_events e
            where aggregate_type='protected_action_claim' and aggregate_id=%s
            order by occurred_at,event_id limit 129""", (h,))
        tx.require(len(audits) <= BOUND and all(history._time(a["occurred_at"]) <= now for a in audits),
            "retained_continuation_audit_history_bound")
        if FIELD in c["preview_payload"]:
            allowed = {a["event_id"] for a in links if a["aggregate_id"] == h}
            if c.get("delivery_attempt_id"):
                allowed.add(_window(cur, c)["event_id"])
            tx.require({a["event_id"] for a in audits} == allowed,
                "retained_continuation_unknown_claim_audit")
        elif c.get("delivery_attempt_id"):
            window = _window(cur, c)
            prior = [a for a in audits if a["event_id"] != window["event_id"]]
            tx.require(tx.digest(prior) == window["payload_json"].get("claim_history_sha256"),
                "retained_continuation_root_audit_history_changed")
    return links, windows


def _case_history(cur, source_history, claims, case, now, validated_links):
    root = next(c for c in claims if FIELD not in c["preview_payload"])
    window = _window(cur, root)
    p, started = window["payload_json"], history._time(window["occurred_at"])
    events = _rows(cur, """select to_jsonb(e) from app_private.oom_manager_case_events e
        where case_id=%s order by occurred_at,event_id limit 4097""", (case["case_id"],))
    links = _rows(cur, """select to_jsonb(e) from public.operational_events e
        where event_type=%s and correlation_id=%s order by occurred_at,event_id limit 129""",
        (EVENT, root["mission_id"]))
    tx.require(len(links) == len(validated_links)
        and {a["event_id"]: a for a in links} == {a["event_id"]: a for a in validated_links},
        "retained_continuation_unknown_lineage_audit")
    generations = int(case["generation"]) - int(p["generation"])
    refs = [r for r in case["evidence_refs"] if str(r).startswith("retained_confirmation:")]
    # Direct owner delivery can precede the next manager reconciliation. The
    # locked case may therefore still project an earlier *audited successor* in
    # this exact validated chain; it cannot name an arbitrary or root digest.
    projected = {"retained_confirmation:" + c["preview_digest"] for c in claims if FIELD in c["preview_payload"]}
    tx.require(len(events) <= history.CASE_HISTORY_BOUND and len(links) <= BOUND
        and p.get("case_id") == case["case_id"] and 0 <= generations <= len(links)
        and (p.get("evidence_digest") == case["evidence_digest"] if generations == 0 else
            len(refs) == 1 and refs[0] in projected)
        and tx.digest([e for e in events if history._time(e["occurred_at"]) <= started]) == p.get("case_history_sha256")
        and tx.digest([r for r in source_history if history._time(r["created_at"]) <= started]) == p.get("source_history_sha256"),
        "retained_continuation_original_history_changed")
    first_generation, last_generation = int(p["generation"]), int(case["generation"])
    # Reconciliation and claiming deliberately share one cycle timestamp. Their
    # hashed event IDs do not encode causal order, so establish each generation
    # from its unique transition rather than walking the ID sort order.
    transitions = sorted((e for e in events if history._time(e["occurred_at"]) > started
        and e["event_type"] == "evidence_changed"), key=lambda e: e["generation"])
    tx.require([e["generation"] for e in transitions] == list(range(first_generation + 1, last_generation + 1)),
        "retained_continuation_case_transition_unproven")
    boundaries = {first_generation: started}
    for e in transitions:
        at = history._time(e["occurred_at"])
        tx.require(at >= boundaries[e["generation"] - 1]
            and any(history._time(a["occurred_at"]) <= at for a in links),
            "retained_continuation_case_transition_unproven")
        boundaries[e["generation"]] = at
    if generations:
        # A manager projection may lag the newest request, but may not name a
        # successor whose audited creation postdates its projection boundary.
        projected_at_boundary = {"retained_confirmation:" + a["payload_json"]["successor"]["preview_digest"]
            for a in validated_links if history._time(a["occurred_at"]) <= boundaries[last_generation]}
        tx.require(refs[0] in projected_at_boundary, "retained_continuation_case_projection_unproven")
    for e in events:
        if history._time(e["occurred_at"]) <= started:
            continue
        v = e["event_payload"]
        kind, outcome = e["event_type"], v.get("outcome_status", "")
        presend = (outcome in {"manager_cycle_deadline_deferred", "family_message_cycle_deadline_deferred"}
            and kind in {"exception", "delivery_suppressed", "reassessment_scheduled"}
            and v.get("failure_kind", "") in {"", outcome})
        statement_deferred = history._is_presend_statement_guard(e) if outcome == "retained_mortality_presend_statement_deferred" else False
        generation, at = e["generation"], history._time(e["occurred_at"])
        tx.require(e["case_id"] == v.get("case_id") == case["case_id"]
            and e["generation"] == v.get("generation") == generation
            and generation in boundaries and boundaries[generation] <= at
            and (generation == last_generation or at <= boundaries[generation + 1])
            and kind == v.get("event_type") and history._time(e["occurred_at"]) == history._time(v["occurred_at"]) <= now
            and not any(v.get(k) for k in ("writes_farm_data", "provider_ambiguity_contained", "telegram_edits",
                "telegram_sends", "provider_card_message_id", "delivery_attempt_id", "delivery_confirmed", "provider_confirmed"))
            and (v.get("failure_kind", "") == "" or presend or statement_deferred)
            and (presend or statement_deferred or (kind in {"claimed", "delegated", "heartbeat", "reassessment_scheduled", "evidence_changed"} and outcome == "")
                or (kind == "delivery_confirmed" and outcome == "protected_delivery_confirmed")
                or (kind in {"delivery_suppressed", "reassessment_scheduled"}
                    and outcome in {"manager_delivery_duplicate_suppressed", "retained_mortality_continuation_owner_review"})),
        "retained_continuation_unsafe_case_history")
    return events


def _family(cur, source, source_history, claims, current, now):
    from modules.oom_sakkie.protected_action_claims import protected_card_mission_id
    cards = {protected_card_mission_id(c["mission_id"], c["preview_digest"]): c for c in claims}
    scopes = list(cards) + [source["mission_id"], current["mission_id"]]
    cur.execute("""select review_event_id,created_at,review_json->'family_message_lifecycle'
        from public.sam_live_stock_conversation_review_events where event_source=%s and
        (chatwoot_conversation_id=any(%s) or review_json->'family_message_lifecycle'->>'mission_id'=any(%s)
         or review_json->'family_message_lifecycle'->>'card_mission_id'=any(%s))
        order by created_at,review_event_id limit 129""",
        ("oom_sakkie_family_message_lifecycle", scopes, scopes, scopes))
    rows = [{"review_event_id": r[0], "created_at": r[1], "record": r[2]} for r in cur.fetchall()]
    tx.require(len(rows) <= BOUND, "retained_continuation_family_history_bound")
    legacy = [r for r in rows if r["record"].get("card_mission_id") not in cards]
    root = next(c for c in claims if FIELD not in c["preview_payload"])
    history._validate_family_history(legacy, source_history, root,
        protected_card_mission_id(root["mission_id"], root["preview_digest"]))
    for card, c in cards.items():
        own = [r for r in rows if r["record"].get("card_mission_id") == card]
        if c["callback_token"] == current["callback_token"] and not c.get("delivery_attempt_id"):
            tx.require(not own, "retained_continuation_new_card_already_attempted")
            continue
        tx.require(len(own) == 2 and {r["record"].get("state") for r in own} == {"delivery_attempted", "delivered"}
            and all(r["record"].get("mission_id") == c["mission_id"]
                and r["record"].get("owner_user_id") == c["owner_user_id"]
                and r["record"].get("chat_id") == c["private_chat_id"]
                and r["record"].get("specialist_identity") == "HERDMASTER"
                and r["record"].get("event_id") == card + ("-DELIVERED" if r["record"].get("state") == "delivered" else "-DELIVERY-ATTEMPT")
                and not any(r["record"].get(k) for k in ("writes_farm_data", "provider_ambiguity_contained",
                    "confirmation_provider_message_id", "confirmation_provider_timestamp"))
                and history._time(c["delivery_attempted_at"]) <= history._time(r["created_at"]) <= now
                for r in own)
            and next(r["record"] for r in own if r["record"]["state"] == "delivered").get(
                "telegram_message_id") == c["preview_card_message_id"],
            "retained_continuation_family_effect_unproven")
    return rows


def admission_history(cur, claim, source, source_history, expected_case, now):
    claims = read_claims(cur, source, source_history)
    links, windows = validate_lineage(cur, source, claims, claim, now, source_history)
    tx.require(links and links[0]["payload_json"]["source_after"] == source,
        "retained_continuation_current_source_changed")
    family = _family(cur, source, source_history, claims, claim, now)
    cases = _rows(cur, "select to_jsonb(c) from app_private.oom_manager_cases c where case_id=%s for update",
        (expected_case["case_id"],))
    case = history._one(cases, "retained_continuation_case")
    tx.require(all(case.get(key) == value for key, value in expected_case.items())
        and case["specialist"] == "HERDMASTER" and case["status"] in {"open", "delegated", "waiting_reassessment", "exception"}
        and case["dedupe_key"] == "herdmaster:retained-mortality:" + claim["provider_message_id"]
        and "pig:" + claim["preview_payload"]["identity"]["pig_id"] in case["evidence_refs"],
        "retained_continuation_case_changed")
    events = _case_history(cur, source_history, claims, case, now, links)
    return {"continuation_audit_sha256": tx.digest(links), "family_history_sha256": tx.digest(family),
        "source_history_sha256": tx.digest(source_history), "claim_history_sha256": tx.digest(claims),
        "case_history_sha256": tx.digest(events),
        "_authorized_window_event_ids": windows}


def _response(source, claim, case, request):
    from modules.oom_sakkie.protected_action_claims import build_buttons, protected_card_mission_id
    requested = {k: v for k, v in _identity(claim).items() if k not in {"claim_hash", "preview_digest"}}
    language = source.get("output_language") or "en"
    prefix = ("Die vorige bevestiging het verval. Niks is aangeteken nie. Jou oorspronklike feite is behou. "
        "Hersien hierdie voorskou en bevestig dit om aan te teken. Die nuwe bevestigingsvenster is 30 minute.\n\n" if language == "af" else
        "The previous confirmation expired. Nothing has been recorded. Your original facts are retained. "
        "Review this preview and confirm it to record. The new confirmation window is 30 minutes.\n\n")
    buttons = build_buttons(claim["callback_token"], language=language)
    buttons["inline_keyboard"][0][0]["text"] = "Bevestig en teken aan" if language == "af" else "Confirm and record"
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import _delivery_context
    context = {**_delivery_context(source), "provider_message_id": request["provider_message_id"],
        "provider_timestamp": request["received_at"], "reply_to_message_id": request["card_message_id"]}
    return {"handled": True, "success": True, "status": "preview_ready", "specialist": "HERDMASTER",
        "writes_farm_data": False, "protected_actions_performed": False, "continuation_requested": True,
        "confirmation_required": True,
        "answer": prefix + source["preview"]["owner_text"], "tool_used": "herdmaster_health_loss_preview",
        "recipient_render_contract": "herdmaster_health_loss_recipient_v1", "recipient_language": language,
        "mission_id": claim["mission_id"], "card_mission_id": protected_card_mission_id(claim["mission_id"], claim["preview_digest"]),
        "callback_token": claim["callback_token"], "preview_digest": claim["preview_digest"], "action_kind": "mortality",
        "reply_markup": buttons,
        "retained_delivery_context": context,
        "_retained_mortality_policy": ContinuationPresentation(presentation._json(source), presentation._json(requested),
            presentation._json({k: case[k] for k in ("case_id", "dedupe_key", "generation", "evidence_digest")}),
            claim["callback_token"], claim["preview_digest"])}


def request_continuation(parsed, authority, callback_data, *, connect_factory=None):
    """A real expired-card click requests review only; no confirmation is consumed."""
    from modules.oom_sakkie.gateway_authority import validates_gateway_owner_authority
    from modules.oom_sakkie.herdmaster_retained_recovery_runtime import retained_recipient_authorized
    from modules.oom_sakkie.protected_action_claims import create_claim
    from modules.oom_sakkie.protected_delivery_lifecycle import _connect
    from modules.oom_sakkie.herdmaster_health_loss_runtime import _record_lifecycle_event
    parts = callback_data.split(":")
    if len(parts) != 3 or parts[0] != "oompa" or parts[2] not in {"confirm", "cancel", "change"}:
        return None
    owner, chat = str(parsed.get("telegram_user_id") or ""), str(parsed.get("telegram_chat_id") or "")
    receipt, card = str(parsed.get("callback_query_id") or ""), str(parsed.get("reply_to_message_id") or "")
    if not (validates_gateway_owner_authority(authority) and (authority.owner_user_id, authority.private_chat_id) == (owner, chat)
            and owner and owner == chat and receipt and receipt == str(parsed.get("provider_message_id") or "")
            and parsed.get("callback_data") == callback_data and card and retained_recipient_authorized(parsed)):
        return None
    try:
        received = history._time(parsed.get("provider_timestamp"))
        with (connect_factory or _connect)() as db, db.cursor() as cur:
            tx.begin(cur)
            cur.execute("select to_jsonb(c) from app_private.oom_protected_action_claims c where callback_token=%s", (parts[1],))
            hint = cur.fetchone()
            if not hint or hint[0]["action_kind"] != "mortality" or not hint[0]["mission_id"].startswith("OOM-HERDMASTER-MORTALITY-"):
                return None
            cur.execute("""select distinct review_json->'herdmaster_health_loss'->>'mission_id'
                from public.sam_live_stock_conversation_review_events where event_source=%s
                and review_json->'herdmaster_health_loss'->'retained_repreview'->>'claim_mission_id'=%s limit 2""",
                (tx.SOURCE, hint[0]["mission_id"]))
            missions = cur.fetchall()
            tx.require(len(missions) == 1 and missions[0][0], "retained_continuation_source_not_unique")
            tx.lock_sources(cur, owner, chat, [missions[0][0]])
            rows = tx.read_history(cur, [missions[0][0]])
            source = tx.latest_for(rows, missions[0][0])
            tx.require(source is not None, "retained_continuation_source_missing")
            tx.require_current(rows, source)
            cur.execute("select to_jsonb(c),clock_timestamp() from app_private.oom_protected_action_claims c where callback_token=%s for update", (parts[1],))
            predecessor, now = cur.fetchone()
            tx.require((predecessor["owner_user_id"], predecessor["private_chat_id"], predecessor["preview_card_message_id"])
                == (owner, chat, card) and history._time(predecessor["expires_at"]) <= received <= now,
                "retained_continuation_request_binding_unproven")
            _delivered_expired(predecessor, now)
            if parts[2] != "confirm":
                return feedback(parsed, "retained_continuation_expired_card_not_changed", "latest"), 200
            claims = read_claims(cur, source, rows)
            current = history._one([c for c in claims if c["preview_digest"] == source["retained_repreview"]["claim_preview_digest"]],
                "retained_continuation_current_claim")
            presentation._validate_source(source, current)
            presentation.validate_origin(rows, source, current, now)
            links, _windows = validate_lineage(cur, source, claims, current, now, rows)
            # An earlier card can resolve its existing descendant, never branch
            # or mint another window after that descendant expires/changes.
            if current["callback_token"] != predecessor["callback_token"]:
                tx.require(any(p["payload_json"]["predecessor"]["claim_hash"] == history._sha(parts[1]) for p in links),
                    "retained_continuation_stale_card")
                tx.require(current["status"] == "active" and history._time(current["expires_at"]) > now,
                    "retained_continuation_use_latest_card")
                if current["delivery_state"] not in {None, "claim_created"}:
                    confirmed = (current["delivery_state"] == "delivery_confirmed"
                        and current.get("preview_card_message_id") and not current.get("delivery_ambiguous_at")
                        and (current.get("delivery_result") or {}).get("success") is True
                        and str(current["delivery_result"].get("telegram_message_id")) == current["preview_card_message_id"])
                    return feedback(parsed, "retained_continuation_already_presented" if confirmed else
                        "retained_continuation_delivery_uncertain", "latest" if confirmed else "uncertain"), 200
            else:
                _window(cur, predecessor)
                _family(cur, source, rows, claims, current, now)
            cases = _rows(cur, "select to_jsonb(c) from app_private.oom_manager_cases c where dedupe_key=%s for update",
                ("herdmaster:retained-mortality:" + predecessor["provider_message_id"],))
            case = history._one(cases, "retained_continuation_case")
            _case_history(cur, rows, claims, case, now, links)
            if current["callback_token"] != predecessor["callback_token"]:
                return _response(source, current, case, links[0]["payload_json"]["request"]), 200
            payload = {**_base(predecessor["preview_payload"]), FIELD: {"contract_version": CONTRACT,
                "predecessor_claim_hash": history._sha(parts[1])}}
            reader = tx.TransactionReader(db)
            created = create_claim(action_kind="mortality", owner_user_id=owner, private_chat_id=chat,
                mission_id=predecessor["mission_id"], provider_message_id=predecessor["provider_message_id"],
                evidence_generation=predecessor["evidence_generation"], preview_payload=payload,
                expires_at=(now + timedelta(seconds=history.TTL_SECONDS)).isoformat(),
                connect_factory=reader, supersede_active=False)
            cur.execute("select to_jsonb(c) from app_private.oom_protected_action_claims c where callback_token=%s", (created["callback_token"],))
            successor = cur.fetchone()[0]
            next_source = deepcopy(source)
            next_source["event_phase"] = "retained_preview_generated:" + created["preview_digest"][:24]
            next_source["retained_repreview"].update(claim_preview_digest=created["preview_digest"],
                generated_at=now.isoformat(), owner_requested_continuation=True)
            p = {"contract_version": CONTRACT, "predecessor": _archive(predecessor), "successor": _identity(successor),
                "source_before": source, "source_after": next_source,
                "request": {"provider_message_id": receipt, "card_message_id": card, "received_at": received.isoformat()}}
            h = history._sha(successor["callback_token"])
            cur.execute("""insert into public.operational_events(event_id,idempotency_key,schema_version,event_type,domain,
                aggregate_type,aggregate_id,source_system,source_record_id,authority_tier,privacy_class,actor_type,actor_id,
                correlation_id,causation_id,occurred_at,recorded_at,freshness_at,payload_json,provenance_json)
                values(%s,%s,'1',%s,'approvals','protected_action_claim',%s,'oom_sakkie',%s,'owner_approved',
                'owner_private','owner',%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb) returning event_id""",
                ("OOM-MORTALITY-CONTINUE-" + h[:32].upper(), KEY + history._sha(parts[1]), EVENT, h, case["case_id"],
                    owner, predecessor["mission_id"], receipt, now, now, now, presentation._json(p),
                    presentation._json({"source_ref": source["retained_repreview"]["source_binding"]})))
            tx.require(cur.rowcount == 1 and cur.fetchone(), "retained_continuation_audit_failed")
            saved = _record_lifecycle_event(next_source, expected_sources={source["mission_id"]: tx.digest(source)}, connect_factory=reader)
            tx.require(saved.get("success") is True, "retained_continuation_source_append_failed")
        return _response(next_source, successor, case, p["request"]), 200
    except tx.SourceConflict as exc:
        return feedback(parsed, str(exc), "refused"), 200
    except Exception as exc:
        return {**feedback(parsed, "retained_continuation_preparation_unavailable", "refused"),
            "error_type": type(exc).__name__}, 200


def feedback(parsed, status, kind):
    af = str(parsed.get("output_language") or "").startswith("af")
    text = ({"latest": "Gebruik die nuutste bevestigingskaart. Hierdie druk het niks aangeteken nie.",
        "refused": "Die voorskou kon nie veilig hernu word nie. Niks is aangeteken nie; jou oorspronklike verslag is vir hersiening behou.",
        "uncertain": "Die nuwe kaart se aflewering is onseker. Hierdie druk het niks aangeteken nie; die verslag is vir hersiening behou.",
        "ready": "Die vorige kaart het verval. Hersien en bevestig die nuwe kaart om aan te teken."} if af else
        {"latest": "Use the newest confirmation card. This press did not record anything.",
        "refused": "The preview could not be refreshed safely. This press did not record anything; your original report is retained for review.",
        "uncertain": "Delivery of the newer card is uncertain. This press did not record anything; the report is retained for review.",
        "ready": "The previous card expired. Review and confirm the new card to record."})[kind]
    return {"handled": True, "success": False, "status": status, "specialist": "HERDMASTER",
        "answer": "", "callback_feedback": text, "continuation_requested": True,
        "writes_farm_data": False, "suppress_owner_delivery": True}


def delivery_feedback_kind(parsed, result, delivered):
    if delivered.get("success") is True:
        return "ready"
    if delivered.get("status") not in {"retained_mortality_window_already_started",
            "protected_delivery_existing_family_card_unbound", "protected_delivery_binding_ambiguous",
            "family_message_provider_replay_binding_conflict", "protected_delivery_ambiguous"}:
        return "refused"
    from modules.oom_sakkie.protected_delivery_lifecycle import _connect
    try:
        with _connect() as db, db.cursor() as cur:
            tx.begin(cur)
            cur.execute("""select delivery_state,preview_card_message_id,delivery_result,delivery_ambiguous_at
                from app_private.oom_protected_action_claims where callback_token=%s and preview_digest=%s
                and owner_user_id=%s and private_chat_id=%s""", (result.get("callback_token"), result.get("preview_digest"),
                    str(parsed.get("telegram_user_id") or ""), str(parsed.get("telegram_chat_id") or "")))
            row = cur.fetchone()
            if (row and row[0] == "delivery_confirmed" and row[1] and row[3] is None
                    and (row[2] or {}).get("success") is True and str(row[2].get("telegram_message_id")) == row[1]):
                return "latest"
    except Exception:
        pass
    return "uncertain"


def resume_requested_preview(source, case):
    """Rebuild only an already audited owner request, never create a claim."""
    from modules.oom_sakkie.protected_delivery_lifecycle import _connect
    with _connect() as db, db.cursor() as cur:
        tx.begin(cur)
        rows = tx.read_history(cur, [source["mission_id"]])
        source = presentation.validate_staged_source(rows, source)
        claims = read_claims(cur, source, rows)
        current = history._one([c for c in claims if c["preview_digest"] ==
            source["retained_repreview"]["claim_preview_digest"]], "retained_continuation_current_claim")
        cur.execute("select clock_timestamp()")
        now = cur.fetchone()[0]
        links, _ = validate_lineage(cur, source, claims, current, now, rows)
        tx.require(bool(links), "retained_continuation_request_missing")
        if current["delivery_state"] not in {None, "claim_created", "expired"}:
            return {"success": current["delivery_state"] == "delivery_confirmed",
                "status": "retained_mortality_continuation_owner_review", "suppress_owner_delivery": True,
                "telegram_sends": 0, "telegram_edits": 0, "writes_farm_data": False}
        return _response(source, current, case, links[0]["payload_json"]["request"])
