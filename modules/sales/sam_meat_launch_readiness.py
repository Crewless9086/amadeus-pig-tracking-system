"""Fail-closed, review-only SAM Meat launch packet.

The deployed SAM Meat runtime calls this packet through the existing inbound
route. Default readers use production-connected sources; tests inject fakes.
"""
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
import hashlib
import re

from modules.oom_sakkie.sales_campaign_store import list_meat_price_book_entries
from modules.sales.butcher_truth_board import get_butcher_truth_board
from modules.sales.meat_fulfillment import get_meat_fulfillment_timeline
from modules.sales.meat_ops import get_meat_ops_status
from modules.sales.sam_farm_knowledge import load_sam_farm_knowledge
from modules.sales.sam_meat_runtime import extract_meat_facts
from modules.sales.sam_meat_database_deadline import SamMeatDatabaseDeadline

PACKET_VERSION = "sam_meat_launch_packet_v2"
TRUTH_READER_DEADLINE_SECONDS = 5.0
DATABASE_READER_DEADLINE_SECONDS = 4.5
AF_MARKERS = {"aflewer", "bestel", "betaal", "eintlik", "ek", "halwe", "hele", "ja", "karkas", "nee", "prys", "stel", "vir", "wil"}
PROTECTED = {
    "confirm_price": r"\b(final price|confirm (?:the )?price|quote me|kwoteer)\b",
    "confirm_availability": r"\b(available|availability|beskikbaar|in stock)\b",
    "reserve_or_order": r"\b(reserve|book it|place (?:the )?order|bestel|bespreek)\b",
    "confirm_payment": r"\b(payment received|money reflects|paid|betaal|pop)\b",
    "confirm_timing": r"\b(confirm|promise).*\b(slaughter|butcher|delivery|aflewer)\b",
}


def production_truth_readers():
    return {"catalogue": _read_catalogue, "pricing": _read_pricing, "availability": _read_availability,
            "fulfilment": _read_fulfilment, "butcher": _read_butcher}


def build_sam_meat_launch_packet(messages, *, conversation_ref="", inbound_event_id="", lead_id="",
                                  truth_readers=None, now=None):
    current = _utc(now)
    rows = _messages(messages)
    facts, evidence, corrections = _accumulate(rows)
    language = _language(rows)
    readers = truth_readers if isinstance(truth_readers, dict) else production_truth_readers()
    truth = _read_truth_batch(readers, lead_id, facts, current)
    catalogue = _catalogue_match(facts, truth["catalogue"])
    price = _price_basis(facts, truth["pricing"], current)
    missing = _missing(facts)
    next_field = _next_field(missing, facts, price)
    question = _question(next_field, language)
    protected = _protected(rows)
    source_id = str(inbound_event_id or (rows[-1]["message_id"] if rows else "") or "missing-inbound-event-id")
    review_id = _id("SAM-MEAT-REVIEW", conversation_ref, source_id, PACKET_VERSION)
    correction_id = _id("SAM-MEAT-CORRECTION", conversation_ref, source_id, PACKET_VERSION) if corrections else ""
    return {
        "success": True, "packet_version": PACKET_VERSION, "mode": "prepared_owner_review_connected_no_send",
        "connection_state": {"deployed_caller_exists": True, "operationally_testable": True,
            "route": "existing_sam_meat_chatwoot_inbound", "blocked_shared_file": "", "blocked_reason": ""},
        "conversation_ref": str(conversation_ref), "language": language,
        "understood_request": {k: v for k, v in facts.items() if v not in (None, "")},
        "facts": facts, "fact_evidence": evidence, "corrections": corrections,
        "missing_facts": missing, "next_missing_field": next_field, "next_safe_question": question,
        "catalogue_match": catalogue, "quantity": {"value": facts.get("quantity"), "unit": facts.get("quantity_unit", "")},
        "price_basis": price, "final_total": {"status": "not_calculated", "amount": None,
            "reason": "owner_review_only_no_final_quote"},
        "availability": truth["availability"], "fulfilment": truth["fulfilment"], "butcher_loop": truth["butcher"],
        "truth": truth, "prepared_reply": _reply(language, question, truth, catalogue, price, protected),
        "protected_decision": {"required": bool(protected), "actions": protected,
            "exact_owner_question": _owner_question(protected, truth)},
        "review_event": {"event_id": review_id, "event_type": "sam_meat_launch_owner_review_prepared",
            "source_event_id": source_id, "packet_version": PACKET_VERSION, "prepared_in_memory": True,
            "persisted": False, "persistence_adapter": "existing_meat_sales_conversation_learning_events_candidate"},
        "correction_event": {"event_id": correction_id,
            "event_type": "sam_meat_customer_correction_prepared" if correction_id else "",
            "prepared_in_memory": bool(correction_id), "persisted": False},
        "diagnostics": {"contains_sensitive_values": False, "message_count": len(rows),
            "fact_fields": sorted(facts), "correction_count": len(corrections),
            "truth_states": {k: v["status"] for k, v in truth.items()},
            "address_captured": bool(facts.get("delivery_address"))},
        "canary": _canary(), "owner_checklist": _checklist(), "authority": _authority(),
    }


def _messages(messages):
    result = []
    for index, row in enumerate(messages if isinstance(messages, list) else [messages]):
        if isinstance(row, dict):
            content = str(row.get("content") or "").strip()
            role = str(row.get("role") or row.get("sender_type") or row.get("message_type") or "customer").lower()
            message_id = str(row.get("message_id") or row.get("event_id") or "").strip()
        else:
            content, role, message_id = str(row or "").strip(), "customer", ""
        if content and role in {"customer", "contact", "incoming"}:
            result.append({"content": content, "index": index,
                "message_id": message_id or _id("MSG", str(index), content)})
    return result


def _accumulate(rows):
    facts, evidence, corrections = {}, {}, []
    for row in rows:
        values = _extract(row["content"])
        explicit = _is_correction(row["content"])
        for field, value in values.items():
            if value in (None, "", "unknown"):
                continue
            old = facts.get(field)
            if old not in (None, "") and old != value:
                corrections.append({"field": field, "from": old, "to": value,
                                    "message_id": row["message_id"], "explicit": explicit})
            facts[field] = value
            evidence[field] = {"message_id": row["message_id"], "message_index": row["index"],
                "evidence_type": "explicit_customer_correction" if old not in (None, "") and old != value else "customer_statement"}
    return facts, evidence, corrections


def _extract(text):
    base = extract_meat_facts(text, {"content": text})
    result = {k: base.get(k) for k in ("product_type", "cut_set", "delivery_mode", "delivery_town",
              "delivery_address", "timing", "payment_method") if base.get(k) not in (None, "", "unknown")}
    lower = str(text).lower()
    if not result.get("cut_set"):
        cut = re.search(r"\b(?:set|stel)\s*([a-d])\b", lower)
        if cut:
            result["cut_set"] = "Set " + cut.group(1).upper()
    if re.search(r"\b(delivery|deliver|aflewer|afgelewer)\b", lower):
        result["delivery_mode"] = "delivery"
    elif re.search(r"\b(collection|collect|pickup|afhaal)\b", lower):
        result["delivery_mode"] = "collection"
    quantity, unit = _quantity(lower)
    if quantity is not None:
        result.update(quantity=quantity, quantity_unit=unit)
    commitment = _commitment(str(text).lower())
    if commitment:
        result["commitment"] = commitment
    if _is_correction(text):
        result["clarification"] = "customer_correction"
    return result


def _quantity(text):
    numbers = {"one": 1, "two": 2, "three": 3, "een": 1, "twee": 2, "drie": 3}
    match = re.search(r"\b(\d+(?:[.,]\d+)?|one|two|three|een|twee|drie)\s*(halves?|half carcasses?|half carcass|full carcasses?|full carcass|carcasses?|packs?|kg|kilograms?|kilos?|halwes?|halwe karkasse?|hele karkasse?|pakke?|pakkie)\b", text)
    if not match:
        return None, ""
    token, raw_unit = match.groups()
    value = numbers.get(token)
    if value is None:
        value = float(token.replace(",", ".")); value = int(value) if value.is_integer() else value
    unit = "kg" if "kg" in raw_unit or "kilo" in raw_unit else "pack" if "pack" in raw_unit or "pakk" in raw_unit else "half_carcass" if "half" in raw_unit or "halw" in raw_unit else "carcass"
    return value, unit


def _commitment(text):
    if re.fullmatch(r"\s*(yes|ja|yep|okay|ok)\s*[.!]?\s*", text):
        return ""
    return "explicit_customer_commitment" if re.search(r"\b(i want to order|i will take|place my order|ek wil bestel|ek neem dit|bestel dit)\b", text) else ""


def _is_correction(text):
    return bool(re.search(r"\b(actually|instead|correction|change that|sorry,? make|eintlik|nee,?|verander dit|maak dit)\b", str(text).lower()))


def _language(rows):
    if not rows: return "en"
    current = set(re.findall(r"[a-z]+", rows[-1]["content"].lower()))
    if current & AF_MARKERS: return "af"
    prior = set(re.findall(r"[a-z]+", " ".join(r["content"].lower() for r in rows[:-1])))
    return "af" if len(rows[-1]["content"].split()) <= 3 and prior & AF_MARKERS else "en"


def _invoke(name, reader, lead_id, facts, now):
    if not callable(reader): return _unavailable(name, "reader_not_configured")
    try: raw = reader(lead_id=lead_id, facts=dict(facts), now=now)
    except Exception as exc: return _unavailable(name, exc.__class__.__name__)
    if not isinstance(raw, dict) or raw.get("usable") is not True:
        reason = (raw.get("blockers") or [f"{name}_unavailable"])[0] if isinstance(raw, dict) else "invalid_reader_result"
        return _unavailable(name, reason)
    return {"source": name, "usable": True, "evidence_complete": True, "status": str(raw.get("status") or "verified"),
        "freshness": str(raw.get("freshness") or "current"), "effective_at": str(raw.get("effective_at") or ""),
        "blockers": list(raw.get("blockers") or []), "verified_zero": raw.get("verified_zero") is True,
        "data": raw.get("data") if isinstance(raw.get("data"), dict) else {}}


def _read_truth_batch(readers, lead_id, facts, now, *, deadline_seconds=TRUTH_READER_DEADLINE_SECONDS):
    """Run independent, database-bounded truth readers within one packet budget."""
    names = ("catalogue", "pricing", "availability", "fulfilment", "butcher")
    executor = ThreadPoolExecutor(max_workers=len(names), thread_name_prefix="sam-meat-truth")
    futures = {
        executor.submit(_invoke, name, readers.get(name), lead_id, facts, now): name
        for name in names
    }
    try:
        done, pending = wait(futures, timeout=max(0.0, float(deadline_seconds)))
        result = {}
        for future in done:
            name = futures[future]
            try:
                result[name] = future.result()
            except Exception as exc:
                result[name] = _unavailable(name, f"reader_failed:{exc.__class__.__name__}")
        for future in pending:
            name = futures[future]
            if not future.cancel():
                future.add_done_callback(_observe_finished_future)
            result[name] = _unavailable(name, "reader_timeout")
        return {name: result.get(name, _unavailable(name, "reader_result_missing")) for name in names}
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _observe_finished_future(future):
    """Retrieve a late result without translating process-control exceptions."""
    if not future.cancelled():
        future.exception()


def _database_deadline():
    return SamMeatDatabaseDeadline(total_seconds=DATABASE_READER_DEADLINE_SECONDS)

def _read_catalogue(**_):
    loaded = load_sam_farm_knowledge(); knowledge = loaded.get("knowledge", {}) if isinstance(loaded, dict) else {}
    meat, cuts = knowledge.get("meat_sales", {}), knowledge.get("cut_sets", {})
    options = meat.get("core_options", []) if isinstance(meat, dict) else []
    usable = loaded.get("status") == "ok" and bool(options)
    return {"usable": usable, "status": "verified_config", "freshness": "configured_file",
        "blockers": [] if usable else ["authoritative_catalogue_unavailable"],
        "data": {"products": options, "units": ["kg", "half_carcass", "carcass", "pack"],
                 "packs": sorted(cuts) if isinstance(cuts, dict) else [], "knowledge_version": knowledge.get("version", "")}}


def _read_pricing(**_):
    result, code = list_meat_price_book_entries(limit=100, database_deadline=_database_deadline()); entries = result.get("price_entries", []) if isinstance(result, dict) else []
    usable = code == 200 and result.get("source") == "supabase" and bool(entries)
    times = [str(e.get("effective_from") or "") for e in entries if isinstance(e, dict)]
    return {"usable": usable, "status": "active_price_book", "freshness": "source_effective_time_required",
        "effective_at": max(times or [""]), "blockers": [] if usable else ["authoritative_supabase_price_book_unavailable"],
        "data": {"entries": entries if usable else [], "mode": result.get("mode", "") if isinstance(result, dict) else ""}}


def _read_availability(*, lead_id="", **_):
    if not lead_id: return {"usable": False, "blockers": ["lead_id_required_for_capacity_status"]}
    result, code = get_meat_ops_status(lead_id, database_deadline=_database_deadline()); assembly = result.get("assembly", {}) if code == 200 else {}
    return {"usable": code == 200, "status": "lead_specific_owner_review", "freshness": "live_database_read",
        "blockers": [] if code == 200 else ["meat_ops_unavailable"], "verified_zero": assembly.get("committed_half_count") == 0,
        "data": {"assembly": assembly} if code == 200 else {}}


def _read_fulfilment(*, lead_id="", **_):
    if not lead_id: return {"usable": False, "blockers": ["lead_id_required_for_fulfilment_timeline"]}
    result, code = get_meat_fulfillment_timeline(lead_id, database_deadline=_database_deadline())
    return {"usable": code == 200, "status": "lead_specific_fulfilment", "freshness": "live_database_read",
        "blockers": [] if code == 200 else ["fulfilment_timeline_unavailable"],
        "data": {"fulfillment": result.get("fulfillment", {})} if code == 200 else {}}


def _read_butcher(*, lead_id="", **_):
    if not lead_id: return {"usable": False, "blockers": ["lead_id_required_for_butcher_truth"]}
    result, code = get_butcher_truth_board(lead_id, database_deadline=_database_deadline())
    return {"usable": code == 200, "status": result.get("truth_status", "Unavailable"),
        "freshness": "composed_live_database_reads", "blockers": [] if code == 200 else ["butcher_truth_unavailable"],
        "data": {"truth_status": result.get("truth_status"), "next_gate": result.get("next_gate")} if code == 200 else {}}


def _unavailable(name, reason):
    return {"source": name, "usable": False, "evidence_complete": False, "status": "Unavailable", "freshness": "unknown", "effective_at": "",
            "blockers": [reason], "verified_zero": False, "data": {}}


def _catalogue_match(facts, source):
    if not source["usable"]: return {"status": "Unavailable", "exact_match": False, "blockers": source["blockers"]}
    product = str(facts.get("product_type") or ""); products = [str(p).lower().replace(" ", "_") for p in source["data"].get("products", [])]
    exact = bool(product) and product.lower() in products
    return {"status": "matched" if exact else "blocked", "exact_match": exact, "product": product,
            "blockers": [] if exact else ["product_not_matched_to_verified_catalogue"]}


def _price_basis(facts, source, now):
    if not source["usable"]: return {"status": "Unavailable", "current": False, "blockers": source["blockers"], "amount": None}
    matches = [e for e in source["data"].get("entries", []) if isinstance(e, dict) and e.get("product_type") == facts.get("product_type") and (not e.get("cut_set") or not facts.get("cut_set") or e.get("cut_set") == facts.get("cut_set")) and _current(e, now)]
    if not matches: return {"status": "stale_or_unmatched", "current": False, "effective_at": source.get("effective_at", ""), "blockers": ["current_matching_price_rule_required"], "amount": None}
    rule = matches[-1]
    return {"status": "current_verified_rule", "current": True, "source": source["status"],
        "effective_at": str(rule.get("effective_from") or source.get("effective_at") or ""),
        "unit": rule.get("price_unit", ""), "amount": rule.get("price_amount"),
        "verified_zero": rule.get("price_amount") == 0, "blockers": []}


def _current(entry, now):
    if str(entry.get("status") or entry.get("approval_status") or "active").lower() not in {"active", "approved", "current"}: return False
    start, end = _parse(entry.get("effective_from")), _parse(entry.get("effective_to"))
    return (not start or start <= now) and (not end or now <= end)


def _missing(facts):
    required = ["product_type", "cut_set", "quantity", "quantity_unit", "delivery_mode"]
    if facts.get("delivery_mode") == "delivery": required += ["delivery_town", "delivery_address"]
    required += ["timing", "payment_method"]
    return [f for f in required if facts.get(f) in (None, "")]


def _next_field(missing, facts, price):
    for field in ("product_type", "cut_set", "quantity", "quantity_unit", "delivery_mode"):
        if field in missing: return field
    if facts.get("delivery_mode") == "delivery":
        for field in ("delivery_town", "delivery_address"):
            if field in missing: return field
    if "timing" in missing: return "timing"
    return "payment_method" if "payment_method" in missing and price.get("current") else ""


def _question(field, language):
    en = {"product_type": "Are you looking for a half carcass, full carcass, or another pork option?", "cut_set": "Which cut style suits you best: family freezer, braai, lean, or slow-cook?", "quantity": "How much would you like?", "quantity_unit": "Should I record that quantity in kilograms, packs, halves, or whole carcasses?", "delivery_mode": "Do you need delivery, or do you want the owner to review a collection request?", "delivery_town": "Which town or area is the delivery for?", "delivery_address": "What delivery address or farm name should we use for the review?", "timing": "When would you ideally need it?", "payment_method": "The current protected payment path is EFT. Does that suit you?"}
    af = {"product_type": "Soek jy 'n halwe karkas, 'n hele karkas, of 'n ander varkvleis-opsie?", "cut_set": "Watter snystyl pas jou die beste: gesinspak, braai, maer, of stadig-gaar?", "quantity": "Hoeveel wil jy graag hÃª?", "quantity_unit": "Moet ek die hoeveelheid as kilogram, pakke, halwes, of hele karkasse noteer?", "delivery_mode": "Moet dit afgelewer word, of wil jy hÃª die eienaar moet 'n afhaalversoek hersien?", "delivery_town": "Vir watter dorp of area is die aflewering?", "delivery_address": "Watter afleweringsadres of plaasnaam moet ons vir die hersiening gebruik?", "timing": "Wanneer het jy dit ideaal nodig?", "payment_method": "Die huidige beskermde betaalpad is EFT. Pas dit jou?"}
    return (af if language == "af" else en).get(field, "")


def _reply(language, question, truth, catalogue, price, protected):
    if question: return ("Dankie, ek het jou besonderhede genoteer. " if language == "af" else "Thanks, I have noted your details. ") + question
    blocked = not catalogue.get("exact_match") or not price.get("current") or not truth["availability"]["usable"] or not truth["fulfilment"]["usable"] or protected
    if language == "af": return "Dankie, ek het die hoofbesonderhede. Die eienaar moet nog die huidige produk-, prys-, beskikbaarheid- en afleweringswaarheid hersien voordat enigiets finaal is." if blocked else "Dankie, die hoofbesonderhede is gereed vir die eienaar se hersiening."
    return "Thanks, I have the main details. The owner still needs to review current product, price, availability, and fulfilment truth before anything is final." if blocked else "Thanks, the main details are ready for the owner's review."


def _protected(rows):
    text = " ".join(r["content"] for r in rows).lower(); return [name for name, pattern in PROTECTED.items() if re.search(pattern, text)]


def _owner_question(actions, truth):
    if actions: return "Approve or correct the prepared reply; protected decisions requested: " + ", ".join(actions) + "."
    blockers = [name for name, item in truth.items() if not item["usable"]]
    return "Restore or verify these truth sources before any commitment: " + ", ".join(blockers) + "." if blockers else "Review or correct the prepared reply; no protected execution is requested."


def _canary():
    return {"selected": False, "conversation_id": "", "contact_id": "", "inbox_id": "", "autoreply_enabled": False,
        "candidate_sends": False, "prerequisites": ["owner selects one isolated test conversation identity after deployment", "owner reviews every prepared reply", "stable replay identity passes before use", "no send, order, payment, reservation, allocation, or farm write"],
        "stop_conditions": ["unsupported promise", "known fact is asked again", "truth is unavailable or stale without blocker", "replay produces a second identity", "any mutation or customer send is attempted"]}


def _checklist():
    return {"day_1": ["Verify the deployed packet and reader mapping.", "Confirm the existing shared route remains released.", "Keep autoreply and protected writes disabled."],
        "day_2": ["Use the connected inbound runtime for preparation only.", "Review through existing meat command state; add no dashboard.", "Replay language, correction, and unavailable-truth cases."],
        "day_3": ["Use only the owner-selected test conversation.", "Review every reply and capture stable evidence.", "Stop on any canary condition; do not enable autoreply."]}


def _authority():
    return {key: False for key in ("publishes", "sends_customer_message", "calls_chatwoot", "spends", "confirms_payment", "creates_quote", "creates_invoice", "creates_final_order", "reserves_meat", "allocates_meat", "promises_availability", "books_slaughter", "books_butcher", "writes_farm_truth", "persists_review_event")}


def _id(prefix, *parts): return f"{prefix}-{hashlib.sha256('|'.join(str(p or '') for p in parts).encode()).hexdigest()[:16].upper()}"
def _parse(value):
    try: return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc) if value else None
    except (TypeError, ValueError): return None
def _utc(value): return value.astimezone(timezone.utc) if isinstance(value, datetime) else (_parse(value) or datetime.now(timezone.utc))
