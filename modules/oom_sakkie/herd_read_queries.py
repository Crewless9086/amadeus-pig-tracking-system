"""Presentation of typed HERDMASTER reads over the existing canonical services.

No language classification, farm writes, model calls, or independent work queue.
"""
from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime
from zoneinfo import ZoneInfo
import html
import math

CAPABILITIES = frozenset({"herd_inventory", "pen_occupancy", "weight_attention", "litter_attention"})


def load_herd_read_evidence(capability):
    if capability not in CAPABILITIES:
        raise ValueError("herd_read_capability_invalid")
    if capability == "weight_attention":
        from modules.pig_weights.herdmaster_daily_manager_evidence import load_daily_manager_evidence
        return load_daily_manager_evidence(
            analysis_date=datetime.now(ZoneInfo("Africa/Johannesburg")).date(),
            include_mortality=False)
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    from modules.pig_weights import farm_supabase_read_service as canonical
    with connect_bounded_rootline_postgres() as connection:
        with connection.cursor() as cursor:
            cursor.execute("set transaction isolation level repeatable read")
        def borrowed(_url):
            return nullcontext(connection)
        borrowed.transaction_managed = True
        if capability == "litter_attention":
            return {"litter_attention": canonical.get_litter_attention_summary(limit=6, connect_factory=borrowed)}
        evidence = {"pig_rows": canonical.get_pig_master_rows(connect_factory=borrowed)}
        if capability == "pen_occupancy":
            evidence["pens"] = canonical.get_pens(connect_factory=borrowed)
        return evidence


def answer_herd_read_query(capability, *, language="en", loader=None):
    from modules.oom_sakkie.family_presentation import heading
    af = str(language).casefold().startswith("af")
    titles = {
        "herd_inventory": ("HERDMASTER — HERD COUNT", "HERDMASTER — KUDDETELLING"),
        "pen_occupancy": ("HERDMASTER — PEN CAPACITY", "HERDMASTER — HOKKAPASITEIT"),
        "weight_attention": ("HERDMASTER — WEIGHING", "HERDMASTER — WEEGWERK"),
        "litter_attention": ("HERDMASTER — LITTERS", "HERDMASTER — WERPSELS"),
    }
    if capability not in CAPABILITIES:
        raise ValueError("herd_read_capability_invalid")
    title = titles[capability][int(af)]
    try:
        evidence = (loader or load_herd_read_evidence)(capability)
        if capability in {"herd_inventory", "pen_occupancy"} and not isinstance(evidence.get("pig_rows"), list):
            raise ValueError("herd_read_animal_evidence_invalid")
        if capability == "weight_attention":
            lines = _weighing(evidence, af)
        elif capability == "litter_attention":
            lines = _litters(evidence["litter_attention"], af)
        elif capability == "pen_occupancy":
            lines = _pens(evidence, af)
        else:
            from modules.agents.herdmaster import run_herdmaster
            readers = {key: lambda value=value: value for key, value in evidence.items()}
            packet = run_herdmaster({"capability": capability}, readers=readers)
            if packet.get("success") is not True:
                raise ValueError("herd_read_evidence_unavailable")
            lines = _inventory(packet, af, evidence["pig_rows"])
        if len("\n".join(lines)) > 3650:
            raise ValueError("herd_read_render_bound_exceeded")
        success, status = True, "herd_read_answer_ready"
    except Exception:
        success, status = False, "herd_read_evidence_unavailable"
        lines = [("Ek kan die huidige kanonieke bewyse vir hierdie vraag nie lees nie. Dit beteken nie daar is geen diere of werk nie." if af else
                  "I cannot read the current canonical evidence for this question. This does not mean there are no animals or no work due.")]
    answer = "\n\n".join([heading(title), "\n".join(lines)])
    return {"success": success, "status": status, "answer": answer,
        "capability": capability, "read_only": True, "writes_performed": False,
        "protected_actions_performed": False, "confirmation_required": False}


def _inventory(packet, af, rows):
    metrics = packet["metrics"]
    lines = [(f"Daar is {metrics['on_farm_total']} varke as op die plaas aangeteken; {metrics['active_on_farm']} is ook Aktief." if af else
              f"There are {metrics['on_farm_total']} pigs recorded on the farm; {metrics['active_on_farm']} are also Active.")]
    if metrics["on_farm_total"] != metrics["active_on_farm"]:
        lines.append("Die verskil is 'n lewensikluskonflik wat versoen moet word; dit is nie 'n bevestigde fisiese telling nie." if af else
                     "The difference is a lifecycle conflict requiring reconciliation; this is not a verified physical count.")
    unknown = sum(str(row.get("On_Farm") or "").casefold() not in {"yes", "no"} for row in rows)
    if unknown:
        lines.append(f"{unknown} dier(e) se plaasstatus is onbekend; die telling is onvolledig." if af else
                     f"{unknown} animal(s) have unknown on-farm status; the count is incomplete.")
    lines.append("Bron: huidige kanonieke dierrekords." if af else "Source: current canonical animal records.")
    return lines


def _pens(evidence, af):
    from collections import Counter
    pigs = evidence["pig_rows"]
    active = [p for p in pigs if str(p.get("Status") or "").casefold() == "active"
              and str(p.get("On_Farm") or "").casefold() == "yes"]
    counts = Counter(str(p.get("Current_Pen_ID") or "") for p in active)
    pens = {str(p.get("pen_id") or ""): p for p in evidence["pens"]}
    comparisons, maternity, unknown = [], [], []
    for pen_id, count in sorted(counts.items()):
        row = pens.get(pen_id, {})
        name = _text(row.get("pen_name") or pen_id, "Hok onbekend" if af else "Pen unknown")
        capacity = row.get("capacity")
        valid_capacity = (isinstance(capacity, (int, float)) and not isinstance(capacity, bool)
            and math.isfinite(capacity) and capacity > 0)
        # A sow plus dependent litter cannot be compared with a unitless
        # farrowing capacity as though every head occupies a separate sow place.
        # Names supplement the canonical type conservatively; no unit is inferred.
        pen_description = str(row.get("pen_type") or "").casefold() + " " + str(row.get("pen_name") or "").casefold()
        if any(word in pen_description for word in ("farrowing", "maternity", "kraam")):
            composition = Counter(str(p.get("Animal_Type") or "Unknown") for p in active
                if str(p.get("Current_Pen_ID") or "") == pen_id)
            detail = ", ".join(f"{number} {_text(kind)}" for kind, number in sorted(composition.items()))
            recorded_capacity = f"{capacity:g}" if valid_capacity else ("Onbekend" if af else "Unknown")
            maternity.append((count, f"• {name}: {count} " +
                (f"aangetekende diere ({detail}); kapasiteit {recorded_capacity}; eenheid onbekend." if af else
                 f"recorded animals ({detail}); capacity {recorded_capacity}; unit unresolved.")))
        elif not valid_capacity:
            unknown.append(f"{name}: {count}")
        elif count > capacity:
            comparisons.append((count-capacity, f"• {name}: {count} / {capacity:g} — " +
                ("aangetekende diertelling oorskry aangetekende kapasiteit." if af else
                 "recorded animal count exceeds recorded capacity.")))
    comparisons.sort(key=lambda item: (-item[0], item[1]))
    maternity.sort(key=lambda item: (-item[0], item[1]))
    lines = [item[1] for item in comparisons[:6]] or [
        ("Geen vergelykbare hok oorskry sy bekende aangetekende kapasiteit nie." if af else
         "No comparable pen exceeds its known recorded capacity.")]
    if len(comparisons) > 6:
        lines.append(_remaining(len(comparisons)-6, af))
    if maternity:
        lines.append("Kraamhokke — geen oorbevolkingsberekening sonder die kapasiteitseenheid nie:" if af else
                     "Farrowing/maternity pens — no overcrowding calculation without the capacity unit:")
        lines.extend(item[1] for item in maternity[:3])
        if len(maternity) > 3:
            lines.append(_remaining(len(maternity)-3, af))
    if unknown:
        lines.append(("Kapasiteit/ligging ontbreek; oorbevolking kan nie beoordeel word nie: " if af else
                      "Capacity/location is missing; overcrowding cannot be assessed: ") + "; ".join(unknown[:6]) + ".")
        if len(unknown) > 6:
            lines.append(_remaining(len(unknown)-6, af))
    lines.append("Dit is rekordvergelykings; fisiese oorbevolking is nie hiermee bevestig nie." if af else
                 "These are record comparisons; physical overcrowding is not established by these counts alone.")
    if not counts:
        lines.append("Geen Aktiewe diere op die plaas is in hierdie aansig nie." if af else
                     "No Active on-farm animals are present in this view.")
    conflicts = sum(str(p.get("On_Farm") or "").casefold() == "yes"
                    and str(p.get("Status") or "").casefold() != "active" for p in pigs)
    if conflicts:
        lines.append((f"{conflicts} dier(e) het teenstrydige lewensiklusstatus; die hoktelling kan onvolledig wees." if af else
                      f"{conflicts} animal(s) have conflicting lifecycle status; pen occupancy may be incomplete."))
    unknown_status = sum(str(p.get("On_Farm") or "").casefold() not in {"yes", "no"} for p in pigs)
    if unknown_status:
        lines.append((f"{unknown_status} dier(e) se plaasstatus is onbekend; die hoktelling is onvolledig." if af else
                      f"{unknown_status} animal(s) have unknown on-farm status; pen occupancy is incomplete."))
    return lines


def _litters(packet, af):
    if not isinstance(packet, dict) or type(packet.get("count")) is not int or not isinstance(packet.get("items"), list):
        raise ValueError("litter_read_evidence_invalid")
    total, items = packet["count"], packet["items"]
    if total < len(items) or total < 0 or (total and not items):
        raise ValueError("litter_read_evidence_incomplete")
    lines = [(f"{total} werpsel(s) benodig aandag volgens die huidige werpselrekords." if af else
              f"{total} litter(s) need attention in the current litter records.")]
    for row in items[:6]:
        name = _text(row.get("sow_name") or row.get("sow_tag_number") or row.get("litter_id"))
        due = _text(row.get("estimated_wean_date"), "Onbekend" if af else "Unknown")
        reason = _text(row.get("reason"), "Onbekend" if af else "Unknown")
        action = _text(row.get("recommended_action"), "Onbekend" if af else "Unknown")
        lines.append(f"• {name}: {reason} " +
            (f"Volgende: {action} Beplande speendatum: {due}." if af else
             f"Next: {action} Estimated weaning: {due}."))
    if total > min(len(items), 6):
        lines.append(_remaining(total-min(len(items), 6), af))
    lines.append("'n Beplande speendatum bewys nie dat speen voltooi is nie." if af else
                 "An estimated weaning date does not mean weaning is completed.")
    return lines


def _weighing(packet, af):
    from modules.pig_weights.herdmaster_daily_manager_evidence import PACKET_TYPE, ELIGIBILITY_VERSION
    if packet.get("packet_type") != PACKET_TYPE:
        raise ValueError("weight_read_evidence_invalid")
    weight = packet["weight"]
    if weight.get("eligibility_rule_version") != ELIGIBILITY_VERSION:
        raise ValueError("weight_read_eligibility_unproven")
    snapshot, window = weight["current_snapshot"], weight["window"]
    covered, eligible = snapshot["covered"], snapshot["eligible_tagged"]
    lines = [(f"Vir {window['start']} tot {window['end']}: {covered}/{eligible} van die huidige geskikte groep het gewigte." if af else
              f"For {window['start']} to {window['end']}: {covered}/{eligible} of the current eligible cohort have weights.")]
    due = weight["individual_weighing_due_now"]
    conflicts = {row["pig_id"] for row in weight["conflicting_weight_evidence"]}
    actionable = [row for row in due if row["pig_id"] not in conflicts]
    if actionable:
        lines.append(("Weeg nou — 'n individuele weegtaak is verskuldig: " if af else
                      "Weigh now — an individual weighing schedule is due: ") + _names(actionable) + ".")
    else:
        lines.append("Geen afsonderlike weegtaak is nou as verskuldig bewys nie." if af else
                     "No individual weighing task is currently proven due.")
    due_ids = {row["pig_id"] for row in actionable}
    pending = [row for row in weight["missing_eligible_tagged"] if row["pig_id"] not in due_ids | conflicts]
    if pending:
        lines.append((f"{len(pending)} gewig(te) ontbreek; verkoop-/bestellingstatus moet eers versoen word: " if af else
                      f"{len(pending)} weight(s) are missing; reconcile sale/order status before instructing reweighing: ") + _names(pending) + ".")
    for key, en, af_label in (
        ("conflicting_weight_evidence", "Conflicting weights need evidence review", "Teenstrydige gewigte benodig bewysversoening"),
        ("unknown_eligibility", "Eligibility unknown", "Geskiktheid onbekend"),
        ("untagged_excluded", "No usable visible tag; excluded from individual cohort", "Geen bruikbare sigbare tag; uitgesluit van individuele groep")):
        rows = weight[key]
        if rows:
            lines.append(f"{af_label if af else en}: {len(rows)} — {_names(rows)}.")
    excluded = len(weight["breeding_excluded"])
    if excluded:
        lines.append((f"{excluded} teeldier(e) sonder individuele weegskedule is uitgesluit." if af else
                      f"{excluded} breeding animal(s) without an individual weighing schedule are excluded."))
    return lines


def _names(rows):
    shown = ", ".join(_text(row.get("tag") or row.get("pig_id")) for row in rows[:6])
    return shown + (f" (+{len(rows)-6})" if len(rows) > 6 else "")


def _remaining(count, af):
    return f"Nog {count} item(s); hierdie is 'n beperkte aansig." if af else f"Another {count} item(s); this is a bounded view."


def _text(value, default="Unknown"):
    return html.escape(" ".join(str(value or default).split())[:150])
