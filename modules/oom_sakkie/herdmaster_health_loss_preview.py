"""Pure Oom Sakkie adapter for HERDMASTER health/loss previews.

This module reuses the existing gateway authority and the reviewed evaluator.
It performs no I/O, routing, confirmation consumption, or persistence.
"""

from __future__ import annotations

import hashlib
import html
import re
from typing import Mapping

from modules.oom_sakkie.gateway_authority import bind_gateway_owner_authority
from modules.pig_weights.herdmaster_natural_health_loss_intake import (
    IntakeEvidenceError,
    evaluate_health_loss_intake,
)


CONTRACT_VERSION = "oom_sakkie_herdmaster_health_loss_preview_v1"
TOOL_NAME = "herdmaster_health_loss_preview"
ZERO_AUTHORITY = {
    "zero_io": True,
    "writes_farm_data": False,
    "consumes_confirmation": False,
    "sends_telegram": False,
    "routes_messages": False,
    "protected_actions_performed": False,
}


def prepare_health_loss_owner_preview(
    envelope: Mapping, canonical_evidence: Mapping
) -> dict:
    """Return one privacy-minimal clarification or consolidated preview."""
    if not isinstance(envelope, Mapping):
        return _failure("authenticated_envelope_required")
    authority = bind_gateway_owner_authority(
        envelope.get("gateway_authority"), TOOL_NAME
    )
    if authority is None:
        return _failure("authenticated_private_owner_authority_required")

    report = {
        "authenticated": True,
        "authenticated_principal_id": authority.owner_user_id,
        "provider_message_id": _required(envelope, "provider_message_id"),
        "provider_timestamp": _required(envelope, "provider_timestamp"),
        "provider_timezone": str(
            envelope.get("provider_timezone") or "Africa/Johannesburg"
        ).strip(),
        "text": _required(envelope, "text"),
        "output_language": "af" if str(envelope.get("output_language") or "en").casefold().startswith("af") else "en",
    }
    if not all(report.values()):
        return _failure("authenticated_envelope_incomplete")
    try:
        evaluated = evaluate_health_loss_intake(report, canonical_evidence)
    except IntakeEvidenceError as exc:
        return _failure(str(exc))

    question = _localize_question(str(
        evaluated.get("smallest_missing_follow_up_question") or ""
    ).strip(), report["output_language"])
    if not evaluated.get("success"):
        return {
            "success": False,
            "status": evaluated["status"],
            "message_type": "single_clarification",
            "owner_text": question,
            "question_count": 1 if question else 0,
            "evaluator": evaluated,
            **ZERO_AUTHORITY,
        }

    owner_text = _render_preview(evaluated, report)
    binding = dict(evaluated["confirmation_binding"])
    binding.update({
        "contract_version": CONTRACT_VERSION,
        "tool_name": TOOL_NAME,
        "authenticated_principal_id": authority.owner_user_id,
        "provider_message_id": report["provider_message_id"],
        "confirmation_ready": not bool(question),
        "owner_text_sha256": _owner_text_digest(owner_text),
    })
    return {
        "success": True,
        "status": "consolidated_preview_ready",
        "message_type": "consolidated_preview",
        "output_language": report["output_language"],
        "owner_text": owner_text,
        "question_count": 1 if question else 0,
        "confirmation_required": True,
        "confirmation_ready": not bool(question),
        "confirmation_binding": binding,
        "evaluator": evaluated,
        **ZERO_AUTHORITY,
    }


def _render_preview(value, report):
    identity = value["identity"]
    af = report["output_language"] == "af"
    name = html.escape(str(identity.get("name") or identity.get("tag_number") or ("Naam onbekend" if af else "Name unknown")))
    tag = html.escape(str(identity.get("tag_number") or ("Onbekend" if af else "Unknown")))
    dead = value.get("event_family") in {"found_dead", "mortality", "maternal_death", "compound_loss"}
    facts = _owner_fact_summary(value, af=af)
    lines = [
        "<b>HERDMASTER - AFSTERWE VOORSKOU</b>" if af and dead else
        "<b>HERDMASTER - GESONDHEID VOORSKOU</b>" if af else
        "<b>HERDMASTER - DEATH PREVIEW</b>" if dead else "<b>HERDMASTER - HEALTH PREVIEW</b>",
        "",
        (f"Dier: {name} (etiket {tag})" if af else f"Animal: {name} (tag {tag})"),
        (f"Aangemeld: {value['provider_report_time']}" if af else f"Reported: {value['provider_report_time']}"),
        ("Wat aangeteken sal word:" if af else "What will be recorded:"),
        *facts,
        _treatment_line(value["owner_report_text"], language="af" if af else "en"),
        ("Oorsaak en presiese tyd bly Onbekend tensy dit aangemeld is." if af else
         "Cause and exact time remain Unknown unless reported."),
        ("Geen diagnose of behandeling word afgelei nie." if af else
         "No diagnosis or treatment is inferred."),
    ]
    question = _localize_question(str(value.get("smallest_missing_follow_up_question") or "").strip(), report["output_language"])
    if question:
        lines.extend(["", ("Een vraag: " if af else "One question: ") + html.escape(question)])
    else:
        lines.extend([
            "",
            ("Bevestig om slegs hierdie voorskou een keer aan te teken." if af else
             "Confirm to record only this preview once."),
        ])
    return "\n".join(lines)


def _owner_fact_summary(value, *, af):
    facts = []
    for effect in value.get("canonical_effects") or []:
        if not effect.get("supported"):
            continue
        area = str(effect.get("area") or "")
        data = effect.get("facts") if isinstance(effect.get("facts"), Mapping) else {}
        if area == "lifecycle":
            facts.append(f"- {'Afsterwedatum' if af else 'Death date'}: {html.escape(str(data.get('date') or ('Onbekend' if af else 'Unknown')))}")
        elif area == "movement_pen" and data.get("owner_reported_outcome"):
            facts.append(f"- {'Verwydering/wegdoening aangemeld' if af else 'Removal/disposal reported'}: {html.escape(str(data['owner_reported_outcome']))}")
        elif area == "medical_observation":
            for row in data.get("observed") or []:
                label = str(row.get('fact') or '').replace('_', ' ')
                if af:
                    label = {"not eating":"eet nie", "injured":"beseer", "bleeding":"bloei"}.get(label, label)
                facts.append(f"- {html.escape(label)}: {html.escape(str(row.get('value')))}")
    return facts or ["- Geen ondersteunde feit" if af else "- No supported fact"]


def _localize_question(question, language):
    question = re.sub(r"\s+\(PIG-[^)]+\)", "", question)
    if not question or language != "af":
        return question
    question = re.sub(r"^Has (.+?) been removed from the pen; if yes, when and what was the disposal/removal outcome\?$",
                      r"Is \1 uit die hok verwyder; indien wel, wanneer en wat was die verwydering/wegdoening?", question)
    question = question.replace("Can ", "Kan ").replace(" able to stand, breathe normally and drink water?", " staan, normaal asemhaal en water drink?")
    return question


def _treatment_line(owner_report_text, language="en"):
    text = str(owner_report_text or "").casefold()
    absence_pattern = (
        r"\b(?:no|without)\s+(?:treatment|medication|medicine|antibiotic\w*)\b(?:\s+(?:initially|earlier|yesterday|today))?(?=\s*(?:[.!?;,]|except\b|$))|"
        r"\bno\s+(?:treatment|medication|medicine|antibiotic\w*)\s+(?:was\s+)?(?:given|administered|provided)\b|"
        r"\bnot\s+treat(?:ed|ing)\b|"
        r"\b(?:treatment|medication|medicine|antibiotic\w*)\s+(?:was\s+)?not\s+(?:given|administered)\b|"
        r"\bgave\s+no\s+(?:treatment|medication|medicine|antibiotic\w*)\b"
    )
    mention_pattern = (
        r"\b(?:treat(?:ed|ment)?|medicat(?:ed|ion)?|antibiotic\w*|inject(?:ed|ion)?|dos(?:e|ed|ing))\b|"
        r"\bgave\s+(?:an?\s+)?(?:antibiotic\w*|medication|medicine|injection|dose)\b"
    )
    absence_matches = list(re.finditer(absence_pattern, text))
    mention_matches = [
        match for match in re.finditer(mention_pattern, text)
        if not any(
            match.start() < absence.end() and absence.start() < match.end()
            for absence in absence_matches
        )
    ]
    explicit_none = bool(absence_matches)
    mentioned = bool(mention_matches)
    exception_wording = explicit_none and bool(re.search(r"\bexcept\b", text))
    if explicit_none and (mentioned or exception_wording):
        return ("Behandelingsbewys: gemengde of teenstrydige verslag; besonderhede Onbekend." if language == "af" else
                "Treatment evidence: mixed or contradictory report; details Unknown.")
    if explicit_none:
        return ("Behandelingsbewys: geen behandeling is aangemeld; omvang Onbekend." if language == "af" else
                "Treatment evidence: owner reported none; scope Unknown.")
    if mentioned:
        return ("Behandelingsbewys: behandeling is genoem; besonderhede Onbekend." if language == "af" else
                "Treatment evidence: treatment mentioned; details Unknown.")
    return "Behandelingsbewys: Onbekend." if language == "af" else "Treatment evidence: Unknown."


def _facts(rows, empty):
    return [f"- {row['fact'].replace('_', ' ')}: {row['value']}" for row in rows] or [f"- {empty}"]


def _causes(rows, empty):
    return [f"- {row['cause']} - owner suspected only" for row in rows] or [f"- {empty}"]


def _diagnoses(rows, empty):
    return [f"- {row['diagnosis']} - {row['attribution'].replace('_', ' ')}" for row in rows] or [f"- {empty}"]


def _mapping_lines(value):
    return [f"- {key.replace('_', ' ')}: {item}" for key, item in value.items()]


def _effect_lines(rows):
    lines = []
    for row in rows:
        state = "proposed" if row["supported"] else "Unknown / no change"
        lines.append(
            f"- {row['area'].replace('_', ' ')}: {row['action'].replace('_', ' ')} [{state}]"
        )
        for key, value in row["facts"].items():
            lines.append(f"  - {key.replace('_', ' ')}: {value}")
    return lines


def _required(value, key):
    return str(value.get(key) or "").strip()


def _owner_text_digest(owner_text):
    material = f"{CONTRACT_VERSION}\n{TOOL_NAME}\n{owner_text}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _failure(status):
    return {
        "success": False,
        "status": status,
        "message_type": "contained",
        "owner_text": "",
        "question_count": 0,
        **ZERO_AUTHORITY,
    }
