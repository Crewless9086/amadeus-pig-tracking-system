"""Typed, zero-authority Telegram presentation for Oom Sakkie results.

The semantic LLM supplies the language hint. This module renders only typed
specialist facts; it cannot invent evidence or acquire specialist authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import html
import math
from numbers import Real
from typing import Any, Iterable, Mapping

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
        decision = str(item.get("status") or item.get("recommendation") or "Needs Data")
        reason = str(item.get("reason") or "").strip()
        rendered_reason = _local_text(reason, af)
        if af and reason and rendered_reason == reason:
            rendered_reason = "Spesialisrede (bronwoorde): " + reason
        decisions.append(f"{_icon(decision)} <b>{labels[subject]}:</b> {_safe(_local_decision(decision, af))}" +
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
          (f"🔋 SOC {soc} · ☀️ {'Sonkrag' if af else 'Solar'} {solar} · {'Las' if af else 'Load'} {load} · {'Netwerk' if af else 'Grid'} {grid}",
           reserve_line,
           (("Reserwerede: " if af else "Reserve reason: ") +
            _safe(("Spesialisbewys (bronwoorde): " + reserve_reason)
                  if af and _local_text(reserve_reason, af) == reserve_reason else _local_text(reserve_reason, af))) if reserve_reason else "")),
         (("Plaasbesluite" if af else "Farm decisions"), tuple(decisions) or
          (("Geen ondersteunde fisiese taak is nou nodig nie." if af else "No supported physical task is due now."),))),
        owner_action=question,
        reassessment=_localized_reassessment(str(brief.get("reassess") or _reassessment_text(result.get("next_reassessment"))), af),
        language=language)
    return _render(response)


def compose_manager_brief(brief, *, language="en") -> str:
    af = str(language).casefold().startswith("af")
    section_names = ({"herd": "🐷 Welsyn & Kudde", "water_energy": "💧 Besproeiing",
                      "sales": "💬 Verkope", "marketing": "📣 Bemarking"} if af else
                     {"herd": "🐷 Welfare & Herd", "water_energy": "💧 Irrigation",
                      "sales": "💬 Sales", "marketing": "📣 Marketing"})
    rows: dict[str, list[str]] = {}
    for item in brief.queue[:3]:
        domain = str(getattr(item, "domain", "") or "herd")
        title = _clip(_local_text(getattr(item, "title", ""), af), 120)
        if af and _local_text(getattr(item, "title", ""), af) == str(getattr(item, "title", "")):
            title = "Bronitem (bronwoorde): " + title
        why = _clip(_local_text(getattr(item, "why", ""), af), 260)
        next_action = _clip(_local_text(getattr(item, "next_action", ""), af), 360)
        text = f"• <b>{title}</b>"
        if why:
            text += f" — <i>Spesialisbewys (bronwoorde):</i> {why}" if af else f" — {why}"
        if next_action and next_action != getattr(item, "genuine_question", ""):
            label = "Spesialis se volgende stap (bronwoorde)" if af else "Next"
            text += f"\n  {label}: {next_action}"
        rows.setdefault(domain, []).append(text)
    sections = tuple((section_names.get(domain, "🌱 Plaaswerk" if af else "🌱 Farm work"), tuple(values))
                     for domain, values in rows.items())
    if not sections:
        sections = ((("Huidige werk" if af else "Current work"),
                     (("Geen ondersteunde familietaak is volgens huidige bewyse nodig nie." if af else
                       "No supported family action is due from current evidence."),)),)
    questions = [q for values in brief.questions.values() for q in values]
    owner_question = (("Spesialisvraag (bronwoorde): " + str(questions[0])) if af and questions else
                      (questions[0] if questions else ""))
    return _render(OwnerResponse("OOM SAKKIE — VANDAG SE PLAASBRIEF" if af else "OOM SAKKIE — TODAY'S FARM BRIEF", sections,
        owner_action=owner_question,
        reassessment=("Oom Sakkie sal herbeoordeel wanneer spesialisbewyse of 'n plaaswaarneming verander." if af else
                      "Oom Sakkie will reassess when specialist evidence or a farm observation changes."),
        language=language))


def compose_weight_preview(rows: Iterable[Mapping[str, Any]], *, language="en") -> str:
    lines = []
    for row in rows:
        label = str(row.get("label") or row.get("tag_number") or "").strip()
        pig_id = str(row.get("pig_id") or "").strip()
        weight = row.get("weight_kg")
        if not label or not pig_id or not isinstance(weight, (int, float)) or weight <= 0:
            raise ValueError("invalid_weight_preview_row")
        lines.append(f"• <b>{_safe(label)}</b> ({_safe(pig_id)}): {weight:g} kg")
    if not lines:
        raise ValueError("weight_preview_rows_required")
    title = "HERDMASTER — WEIGHT PREVIEW" if language != "af" else "HERDMASTER — GEWIG VOORSKOU"
    action = ("Confirm this grouped preview before any weight is recorded."
              if language != "af" else "Bevestig hierdie gegroepeerde voorskou voordat enige gewig aangeteken word.")
    return _render(OwnerResponse(title, (("Weights" if language != "af" else "Gewigte", tuple(lines)),),
                                 owner_action=action, language=language))


def _render(response: OwnerResponse) -> str:
    lines = [f"<b>{_safe(response.title)}</b>"]
    for heading, values in response.sections:
        clean = tuple(value for value in values if str(value).strip())
        if clean:
            lines += ["", f"<b>{_safe(heading)}</b>", *clean]
    if response.owner_action:
        heading = "Wat ek van jou nodig het" if response.language == "af" else "What I need from you"
        lines += ["", f"<b>❓ {heading}</b>", _safe(response.owner_action)]
    if response.reassessment:
        heading = "Volgende herbeoordeling" if response.language == "af" else "Next reassessment"
        lines += ["", f"<b>🔄 {heading}</b>", _safe(response.reassessment)]
    rendered = "\n".join(lines)
    if len(rendered) > MAX_TELEGRAM_CHARS:
        raise ValueError("owner_response_exceeds_telegram_budget")
    return rendered


def _safe(value):
    return html.escape(" ".join(str(value or "").split()), quote=False)


def _clip(value, limit):
    text = " ".join(str(value or "").split())
    escaped, used = [], 0
    for character in text:
        entity = html.escape(character, quote=False)
        if used + len(entity) > limit:
            return "".join(escaped).rstrip() + "…"
        escaped.append(entity); used += len(entity)
    return "".join(escaped)


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
