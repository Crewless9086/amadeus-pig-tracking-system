"""Typed, zero-authority Telegram presentation for Oom Sakkie results.

The semantic LLM supplies the language hint. This module renders only typed
specialist facts; it cannot invent evidence or acquire specialist authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import html
import math
from numbers import Real
from typing import Any, Iterable, Mapping
from modules.oom_sakkie.family_presentation import animal_label, date_label, heading

from modules.oom_sakkie.rootline_daily_presentation import (
    owner_reason, owner_window, owner_zone_decision,
)

MAX_TELEGRAM_CHARS = 3900


@dataclass(frozen=True)
class DecisionLine:
    label: str
    decision: str
    reason: str = ""


@dataclass(frozen=True)
class OwnerResponse:
    title: str
    sections: tuple[tuple[str, tuple[str, ...]], ...]
    owner_action: str = ""
    reassessment: str = ""
    language: str = "en"


def compose_rootline(result: Mapping[str, Any], *, language="en") -> str:
    af = str(language).casefold().startswith("af")
    if result.get("success") is not True:
        message = ("Huidige water- en kragbewyse is nie beskikbaar nie." if af else
                   "Current water and power evidence is unavailable.")
        retry = ("Oom Sakkie sal weer met vars kanonieke bewyse beoordeel." if af else
                 "Oom Sakkie will retry from fresh canonical evidence.")
        return _render(OwnerResponse("ROOTLINE", (("Status", (message,)),), reassessment=retry, language=language))
    power = result.get("current_power") if isinstance(result.get("current_power"), Mapping) else {}
    policy = result.get("battery_policy") if isinstance(result.get("battery_policy"), Mapping) else {}
    brief = result.get("owner_brief") if isinstance(result.get("owner_brief"), Mapping) else {}
    decisions = []
    labels = {"B12345": "B Kamp" if af else "B Camp", "C12345": "C Kamp" if af else "C Camp",
              "borehole": "Boorgat" if af else "Borehole",
              "fertilizer_injection": "Kunsmisinspuiting" if af else "Fertilizer injection",
              "fertilizer_mixing": "Kunsmismenging" if af else "Fertilizer mixing"}
    for item in result.get("recommendations") or ():
        if not isinstance(item, Mapping):
            continue
        subject = str(item.get("subject") or item.get("task_id") or "")
        if subject not in labels:
            continue
        raw_decision = str(item.get("status") or item.get("recommendation") or "Needs Data")
        decision = (owner_zone_decision(result, item, zone=subject, language=language)
                    if subject in {"B12345", "C12345"}
                    else _local_decision(raw_decision, af))
        reason = str(item.get("reason") or "").strip()
        if subject == "C12345":
            reason = reason.replace("B-Camp plan", "camp plan").replace("B Camp plan", "camp plan")
        rendered_reason = owner_reason(reason, language=language)
        window = owner_window(item.get("preferred_window"))
        decisions.append(f"• <b>{labels[subject]}:</b> {_safe(decision)}" +
                         (f" · {_safe(window)}" if window else "") +
                         (f" — {_safe(rendered_reason)}" if reason else ""))
    soc = _value(power.get("battery_soc_pct"), "%", af=af)
    solar = _value(power.get("solar_power_w"), " W", af=af)
    load = _value(power.get("load_power_w"), " W", af=af)
    grid = _value(power.get("grid_power_w"), " W", af=af)
    reserve = _value(policy.get("governing_reserve_soc_pct"), "%", af=af)
    reserve_reason = str(policy.get("governing_reason") or "").strip()
    question = _genuine_question(brief.get("family_fact_needed"))
    if af and question:
        question = "Spesialisvraag (bronwoorde): " + question
    current_decision = str(brief.get("recommend_now") or result.get("overall_status") or "Needs Data")
    rendered_current = _local_decision(current_decision, af)
    if af and rendered_current == current_decision:
        rendered_current = "Bronbesluit (bronwoorde): " + current_decision
    reserve_floor = policy.get("absolute_floor_soc_pct")
    reserve_floor = reserve_floor if _is_number(reserve_floor) else None
    reserve_line = ((f"Reserweteiken: {reserve}" if af else f"Reserve target: {reserve}") +
                    ((f" (absolute vloer {reserve_floor}%)" if af else f" (absolute floor {reserve_floor}%)")
                     if reserve_floor is not None else ""))
    response = OwnerResponse(
        "ROOTLINE — WATER & KRAG" if af else "ROOTLINE — WATER & POWER",
        ((("Huidige besluit" if af else "Current decision"),
          (("ROOTLINE beveel nou aan: " if af else "ROOTLINE recommends now: ") + _safe(rendered_current) + ".",)),
         (("Krag" if af else "Power"),
          (f"SOC {soc} · {'Sonkrag' if af else 'Solar'} {solar} · {'Las' if af else 'Load'} {load} · {'Netwerk' if af else 'Grid'} {grid}",
           reserve_line,
           (("Reserwerede: " if af else "Reserve reason: ") +
            _safe(owner_reason(reserve_reason, language=language))) if reserve_reason else "")),
         (("Plaasbesluite" if af else "Farm decisions"), tuple(decisions) or
          (("Geen ondersteunde fisiese taak is nou nodig nie." if af else "No supported physical task is due now."),))),
        owner_action=question,
        reassessment=_localized_reassessment(str(brief.get("reassess") or _reassessment_text(result.get("next_reassessment"))), af),
        language=language)
    return _render(response)


def compose_manager_brief(brief, *, language="en") -> str:
    af = str(language).casefold().startswith("af")
    section_names = ({"herd": "Welsyn & Kudde", "water_energy": "Besproeiing",
                      "sales": "Verkope", "marketing": "Bemarking"} if af else
                     {"herd": "Welfare & Herd", "water_energy": "Irrigation",
                      "sales": "Sales", "marketing": "Marketing"})
    rows: dict[str, list[str]] = {}
    for item in brief.queue[:3]:
        domain = str(getattr(item, "domain", "") or "herd")
        compact = _typed_brief_row(item, af)
        if compact:
            rows.setdefault(domain, []).append(compact)
            continue
        native = _native_brief_language(item, af)
        title = _clip(_local_text(getattr(item, "title", ""), af), 120)
        if af and not native and _local_text(getattr(item, "title", ""), af) == str(getattr(item, "title", "")):
            title = "Bronitem (bronwoorde): " + title
        why = _clip(_local_text(getattr(item, "why", ""), af), 260)
        next_action = _clip(_local_text(getattr(item, "next_action", ""), af), 360)
        text = f"• <b>{title}</b>"
        if why:
            text += f" — <i>Spesialisbewys (bronwoorde):</i> {why}" if af and not native else f" — {why}"
        if next_action and str(item.next_action).strip() != str(item.genuine_question).strip():
            label = ("Volgende stap" if native else "Spesialis se volgende stap (bronwoorde)") if af else "Next"
            text += f"\n  {label}: {next_action}"
        rows.setdefault(domain, []).append(text)
    sections = tuple((section_names.get(domain, "Plaaswerk" if af else "Farm work"), tuple(values))
                     for domain, values in rows.items())
    if not sections:
        sections = ((("Huidige werk" if af else "Current work"),
                     (("Geen ondersteunde familietaak is volgens huidige bewyse nodig nie." if af else
                       "No supported family action is due from current evidence."),)),)
    questions = [q for values in brief.questions.values() for q in values]
    question_item = next((item for item in brief.queue
                         if questions and item.genuine_question == questions[0]), None)
    native_question = bool(question_item and _native_brief_language(question_item, af))
    owner_question = (("Spesialisvraag (bronwoorde): " + str(questions[0]))
                      if af and questions and not native_question else (questions[0] if questions else ""))
    return _render(OwnerResponse("OOM SAKKIE — VANDAG SE PLAASBRIEF" if af else "OOM SAKKIE — TODAY'S FARM BRIEF", sections,
        owner_action=owner_question,
        reassessment=("Oom Sakkie sal herbeoordeel wanneer spesialisbewyse of 'n plaaswaarneming verander." if af else
                      "Oom Sakkie will reassess when specialist evidence or a farm observation changes."),
        language=language))


def _native_brief_language(item, af):
    return (item.provenance.specialist == "herdmaster"
        and item.metadata.get("recipient_render_contract") == "herdmaster_whole_herd_recipient_v1"
        and item.metadata.get("recipient_language") == ("af" if af else "en"))


def _brief_date_range(start, end, af):
    """Calendar dates only; never relabel a historical measurement as today."""
    language = "af" if af else "en"
    try:
        first, last = date.fromisoformat(str(start)), date.fromisoformat(str(end))
        if first > last:
            raise ValueError("reversed_date_range")
    except (TypeError, ValueError):
        return "tydperk onbekend" if af else "period unknown"
    if first == last:
        return date_label(first, language=language)
    if (first.year, first.month) == (last.year, last.month):
        return f"{first.day}–{date_label(last, language=language)}"
    return f"{date_label(first, language=language)} – {date_label(last, language=language)}"


def _typed_brief_row(item, af):
    """Small summaries of producer facts, never a parser of specialist prose."""
    facts = item.metadata.get("brief_facts")
    if not isinstance(facts, Mapping):
        return ""
    kind = facts.get("kind")
    if kind == "farrowing_outcome_unconfirmed" and item.provenance.specialist == "herdmaster" \
            and item.dedupe_key.startswith("herdmaster:reproductive-status:"):
        labels = facts.get("labels")
        if not isinstance(labels, list) or not labels or any(
                not isinstance(label, str) or not label.strip() or len(label) > 80
                or label.upper().startswith("PIG-") for label in labels):
            return ""
        names = (" en " if af else " & ").join(labels[:3])
        if len(labels) > 3:
            names += (f" en nog {len(labels)-3}" if af else f" and {len(labels)-3} more")
        period = _brief_date_range(facts.get("window_start"), facts.get("window_end"), af)
        return (f"• <b>{_safe(names)}:</b> " +
                ("werpuitkoms onbevestig." if af else "farrowing outcome unconfirmed.") +
                f"\n  {'Verwagte tydperk' if af else 'Expected window'}: {_safe(period)}.")
    if kind == "weight_status_review" and item.provenance.specialist == "herdmaster" \
            and item.dedupe_key == "herdmaster:weekly-weight-evidence":
        counts = [facts.get(key) for key in ("covered", "eligible", "status_checks")]
        if any(value is not None and (type(value) is not int or value < 0) for value in counts):
            return ""
        covered, eligible, checks = counts
        if eligible is not None and any(value is not None and value > eligible for value in (covered, checks)):
            return ""
        unknown = "onbekend" if af else "unknown"
        coverage = "/".join(unknown if value is None else str(value) for value in (covered, eligible))
        period = _brief_date_range(facts.get("window_start"), facts.get("window_end"), af)
        check_text = (f"HERDMASTER sal dié {checks} varke se plaas-/verkoopstatus nagaan voor 'n nuwe weegopdrag."
                      if af else f"HERDMASTER will check farm/sale records for these {checks} pigs before requesting weights.") if checks is not None else (
                      "HERDMASTER sal plaas-/verkoopstatus nagaan; die aantal is onbekend." if af else
                      "HERDMASTER will check farm/sale records; the number needing checks is unknown.")
        return (f"• <b>{'Gewigte' if af else 'Weights'}:</b> {coverage} " +
                ("van die huidige groep aangeteken" if af else "of the current group recorded") +
                f" ({_safe(period)}).\n  {_safe(check_text)}")
    if kind == "irrigation_status" and item.provenance.specialist == "rootline" \
            and item.dedupe_key == "rootline:daily-plan":
        return _irrigation_brief(facts, af)
    return ""


def _irrigation_brief(facts, af):
    statuses = {
        "Currently running": "Loop tans", "Ready — starting safely": "Gereed — begin veilig",
        "Ready after the final safety check": "Gereed na die finale veiligheidskontrole",
        "Checking safely": "Kontroleer veiligheid", "Needs watering": "Moet natgemaak word",
        "Not running": "Loop nie", "Not running — does not need watering": "Loop nie — het nie water nodig nie",
        "Held safely — problem under automatic review": "Veilig teruggehou — probleem word outomaties nagegaan",
        "Controller OFF verified": "Beheerder AF geverifieer", "Needs Data": "Data nodig",
    }
    zones = facts.get("zones")
    if not isinstance(zones, list) or len(zones) != 2 or [row.get("zone") for row in zones
            if isinstance(row, Mapping)] != ["B12345", "C12345"] \
            or any(row.get("status") not in statuses for row in zones):
        return ""
    groups = [zones] if zones[0]["status"] == zones[1]["status"] else [[row] for row in zones]
    lines = []
    for group in groups:
        label = " & ".join(row["zone"][0] for row in group) + (" kampe" if af and len(group) > 1 else
                " kamp" if af else " camps" if len(group) > 1 else " camp")
        status = statuses[group[0]["status"]] if af else group[0]["status"]
        lines.append(f"• <b>{_safe(label)}:</b> {_safe(status)}.")
    reasons = list(dict.fromkeys(str(row.get("reason") or "") for row in zones))
    # This is one exact output of the existing deterministic need classifier,
    # not prose inference. Other reasons keep the safe existing projection.
    weekly = "Weekly irrigation demand, water and dry observed weather support one bounded gravity-fed segment."
    recommended = all(str(row.get("recommendation") or "").casefold() in {
        "recommend", "run", "proceed", "eligible"} for row in zones)
    if reasons == [weekly] and recommended:
        lines.append("  " + ("Aanbeveling: een beperkte swaartekragbeurt; weekbehoefte, beskikbare water en droë weer ondersteun dit."
                     if af else "Recommendation: one limited gravity-fed run, supported by weekly need, available water and dry weather."))
    elif any(reasons):
        # Unknown/other recommendation facts must not disappear behind an OFF
        # status. Use the existing bounded source-word fallback for the item.
        return ""
    return "\n".join(lines)


def compose_weight_preview(rows: Iterable[Mapping[str, Any]], *, language="en", weight_date="",
                           movement_pen_label="") -> str:
    lines = []
    labels = set()
    for row in rows:
        label = str(row.get("label") or row.get("tag_number") or "").strip()
        pig_id = str(row.get("pig_id") or "").strip()
        weight = row.get("weight_kg")
        if not label or not pig_id or not isinstance(weight, (int, float)) or weight <= 0:
            raise ValueError("invalid_weight_preview_row")
        visible = animal_label(row, language=language)
        if visible in {"Unknown animal", "Onbekende dier"}:
            raise ValueError("weight_preview_visible_identity_required")
        if visible.casefold() in labels:
            raise ValueError("weight_preview_visible_identity_ambiguous")
        labels.add(visible.casefold())
        lines.append(f"• <b>{_safe(visible)}</b>: {weight:g} kg")
    if not lines:
        raise ValueError("weight_preview_rows_required")
    title = "HERDMASTER — WEIGHT PREVIEW" if language != "af" else "HERDMASTER — GEWIG VOORSKOU"
    action = ("Confirm this grouped preview before any weight is recorded."
              if language != "af" else "Bevestig hierdie gegroepeerde voorskou voordat enige gewig aangeteken word.")
    sections=[("Weights" if language != "af" else "Gewigte",tuple(lines))]
    shared=[]
    if weight_date:shared.append(("Datum" if language=="af" else "Date")+f": {date_label(weight_date, language=language)}")
    if movement_pen_label:shared.append(("Skuif almal na" if language=="af" else "Move all to")+f": {movement_pen_label}")
    if shared:sections.append(("Shared details" if language!="af" else "Gedeelde besonderhede",tuple(shared)))
    return _render(OwnerResponse(title, tuple(sections),
                                 owner_action=action, language=language))


def _render(response: OwnerResponse) -> str:
    lines = [heading(response.title)]
    for section_heading, values in response.sections:
        clean = tuple(value for value in values if str(value).strip())
        if clean:
            lines += ["", f"<b>{_safe(section_heading)}</b>", *clean]
    if response.owner_action:
        lines += ["", _safe(response.owner_action)]
    if response.reassessment:
        lines += ["", _safe(response.reassessment)]
    rendered = "\n".join(lines)
    if len(rendered) > MAX_TELEGRAM_CHARS:
        raise ValueError("owner_response_exceeds_telegram_budget")
    return rendered


def _safe(value):
    return html.escape(" ".join(str(value or "").split()), quote=False)


def _clip(value, limit):
    text = " ".join(str(value or "").split())
    if len(html.escape(text, quote=False)) <= limit:
        return html.escape(text, quote=False)
    characters=[]; used=0
    for character in text:
        entity=html.escape(character,quote=False)
        if used+len(entity)>limit:
            break
        characters.append(character); used+=len(entity)
    candidate = "".join(characters).rstrip()
    sentence_end = max(candidate.rfind(". "), candidate.rfind("; "))
    if sentence_end >= max(40, limit // 3):
        return html.escape(candidate[:sentence_end + 1].rstrip(), quote=False)
    word_end = candidate.rfind(" ")
    candidate = candidate[:word_end if word_end > 0 else limit].rstrip(" ,;:-")
    candidate += ("." if candidate and candidate[-1] not in ".!?" else "")
    return html.escape(candidate, quote=False)


def _value(value, suffix="", *, af=False):
    return ("Nie beskikbaar" if af else "Unavailable") if not _is_number(value) else f"{value}{suffix}"


def _is_number(value):
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(float(value))


def _icon(decision):
    value = str(decision).casefold()
    if "hold" in value or "do not" in value: return "⏸️"
    if "run" in value or "recommend" in value: return "✅"
    if "need" in value or "unknown" in value: return "❓"
    if "complete" in value: return "✅"
    return "•"


def _genuine_question(value):
    text = str(value or "").strip()
    return "" if text.casefold() in {"", "no owner fact is required now.", "none"} else text


def _reassessment_text(value):
    value = value if isinstance(value, Mapping) else {}
    trigger, at = value.get("trigger"), value.get("at")
    return " ".join(str(part) for part in (trigger, at) if part) or "When canonical evidence changes."


def _local_decision(value, af):
    if not af:
        return str(value)
    return {"hold": "Hou", "run now": "Loop nou", "run later": "Loop later",
            "needs data": "Meer data nodig", "do not run": "Moenie loop nie",
            "recommend": "Aanbeveel", "plan ready": "Plan gereed"}.get(str(value).casefold(), str(value))


def _local_text(value, af):
    text = str(value or "")
    if not af:
        return text
    replacements = {
        "Reserve is below the governing target.": "Die reserwe is onder die geldende teiken.",
        "Fresh evidence supports this C Camp decision.": "Vars bewyse ondersteun hierdie C-Kamp-besluit.",
        "Current storage does not support pumping.": "Huidige berging ondersteun nie pompwerk nie.",
        "Irrigation interlock remains protected.": "Die besproeiingsvergrendeling bly beskerm.",
        "At 10:00 or when material evidence changes.": "Om 10:00 of wanneer wesenlike bewyse verander.",
        "Pig 127 mortality record follow-up": "Pig 127-sterfterekord-opvolg",
        "Owner reported dead; recording remains governed.": "Eienaar het die vark dood aangemeld; aantekening bly beheer.",
        "Review the retained mortality preview.": "Hersien die behoue sterftevoorskou.",
        "Prepare Mona and Mysikind": "Berei Mona en Mysikind voor",
        "Both remain Assumed Pregnant, not clinically confirmed.": "Albei bly operasioneel vermoedelik dragtig, nie klinies bevestig nie.",
        "Prepare proportionally.": "Berei proporsioneel voor.",
    }
    return replacements.get(text, text)


def _localized_reassessment(value, af):
    localized = _local_text(value, af)
    if af and localized == str(value):
        return "Spesialis se herbeoordeling (bronwoorde): " + str(value)
    return localized
