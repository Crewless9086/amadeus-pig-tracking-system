"""Pure Oom Sakkie adapter for HERDMASTER health/loss previews.

This module reuses the existing gateway authority and the reviewed evaluator.
It performs no I/O, routing, confirmation consumption, or persistence.
"""

from __future__ import annotations

import hashlib
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
    }
    if not all(report.values()):
        return _failure("authenticated_envelope_incomplete")
    try:
        evaluated = evaluate_health_loss_intake(report, canonical_evidence)
    except IntakeEvidenceError as exc:
        return _failure(str(exc))

    question = str(
        evaluated.get("smallest_missing_follow_up_question") or ""
    ).strip()
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
    lines = [
        "Oom Sakkie - HERDMASTER health/loss preview",
        "",
        f"Animal: {identity['name']} ({identity['pig_id']}; tag {identity['tag_number']})",
        f"Provider message: {report['provider_message_id']}",
        f"Observed at: {value['provider_report_time']}",
        "Owner evidence: authenticated private owner binding",
        f"Event: {value['event_family'].replace('_', ' ')}",
        f"Welfare priority: {value['immediate_welfare_priority']['level'].replace('_', ' ')}",
        f"Welfare action: {value['immediate_welfare_priority']['action']}",
        "",
        "Observed facts:",
        *_facts(value["observed_facts"], "None"),
        "Agent diagnosis: Unknown (none inferred)",
        "Suspected cause: Unknown" if not value["owner_suspected_cause"] else "Owner-suspected cause (not a diagnosis):",
        *_causes(value["owner_suspected_cause"], "None reported"),
        _treatment_line(value["owner_report_text"]),
        "Veterinary evidence:",
        *_diagnoses(value["veterinary_evidence"], "None reported"),
        "Agent inference: None",
        "",
        "Current canonical state:",
        *_mapping_lines(value["preview"]["before"]),
        "Proposed affected records (nothing written):",
        *_effect_lines(value["canonical_effects"]),
        "Intentionally unchanged:",
        "- " + ", ".join(value["preview"]["intentionally_unchanged"]),
    ]
    question = str(value.get("smallest_missing_follow_up_question") or "").strip()
    if question:
        lines.extend(["", f"One clarification: {question}"])
    else:
        confirmations = ", ".join(value["required_confirmations"])
        lines.extend([
            "",
            f"Protected confirmations covered: {confirmations or 'None'}",
            f"Reply exactly: CONFIRM {value['operation_id']}",
        ])
    return "\n".join(lines)


def _treatment_line(owner_report_text):
    text = str(owner_report_text or "").casefold()
    absence_pattern = (
        r"\b(?:no|without)\s+(?:treatment|medication|medicine|antibiotic\w*)\b|"
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
        return "Treatment evidence: mixed or contradictory owner wording; details Unknown / not evaluated"
    if explicit_none:
        return "Treatment evidence: owner explicitly reported none"
    if mentioned:
        return "Treatment evidence: mentioned by owner; details Unknown / not evaluated by this intake"
    return "Treatment evidence: Unknown / not evaluated or extracted by this intake"


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
