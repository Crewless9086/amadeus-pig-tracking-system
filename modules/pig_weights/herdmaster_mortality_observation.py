"""Source-bound mortality facts interpreted by Oom Sakkie, never write authority.

The model supplies meaning and verbatim quotations. The authenticated caller
adds source identities. HERDMASTER validates provenance, canonical identity and
chronology before the existing protected preview can be confirmed.
"""
from __future__ import annotations

from datetime import date, datetime
import re
from typing import Mapping


FIELDS = frozenset({"animal", "death", "date", "disposal"})


def mortality_observation(value, *, bound=False):
    if value is None:
        return None
    if not isinstance(value, Mapping) or not value or set(value) - FIELDS:
        raise ValueError("mortality_observation_invalid")
    result = {}
    keys = {"value", "quote"} | ({"provider_message_id", "provider_timestamp"} if bound else set())
    for name, fact in value.items():
        if not isinstance(fact, Mapping) or set(fact) != keys:
            raise ValueError("mortality_fact_shape_invalid")
        quote, meaning = fact["quote"], fact["value"]
        if not isinstance(quote, str) or not quote.strip() or len(quote) > 500:
            raise ValueError("mortality_source_quote_required")
        if name == "animal" and (not isinstance(meaning, str) or not meaning.strip()
                or len(meaning) > 80 or not _mentioned(meaning, quote)):
            raise ValueError("mortality_animal_reference_invalid")
        if name == "death" and meaning not in {"dead", "alive", "unknown"}:
            raise ValueError("mortality_death_state_invalid")
        if name == "disposal" and meaning not in {
                "removed", "buried", "removed_and_buried", "cremated", "disposed", "unknown"}:
            raise ValueError("mortality_disposal_state_invalid")
        if name == "date" and meaning is not None:
            if not isinstance(meaning, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", meaning):
                raise ValueError("mortality_date_invalid")
            date.fromisoformat(meaning)
        if bound:
            if not isinstance(fact["provider_message_id"], str) or not fact["provider_message_id"]:
                raise ValueError("mortality_source_identity_required")
            timestamp = datetime.fromisoformat(str(fact["provider_timestamp"]).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("mortality_source_time_required")
        result[name] = dict(fact)
    return result


def bind_mortality_observation(value, *, text, provider_message_id, provider_timestamp):
    """Bind only facts quoted from this authenticated message, never model IDs."""
    facts = mortality_observation(value)
    if facts is None:
        return None
    result = {}
    for name, fact in facts.items():
        if fact["quote"] not in text:
            raise ValueError("mortality_quote_not_in_owner_message")
        result[name] = {**fact, "provider_message_id": str(provider_message_id),
                        "provider_timestamp": str(provider_timestamp)}
    return mortality_observation(result, bound=True)


def validate_mortality_sources(value, report):
    facts = mortality_observation(value, bound=True)
    if facts is None:
        return None
    parts = report.get("report_parts") or [report]
    report_time = datetime.fromisoformat(str(report["provider_timestamp"]).replace("Z", "+00:00"))
    for fact in facts.values():
        matching = [row for row in parts if isinstance(row, Mapping)
            and str(row.get("provider_message_id") or "") == fact["provider_message_id"]
            and str(row.get("provider_timestamp") or "") == fact["provider_timestamp"]
            and fact["quote"] in str(row.get("text") or "")]
        source_time = datetime.fromisoformat(fact["provider_timestamp"].replace("Z", "+00:00"))
        if not matching or source_time > report_time:
            raise ValueError("mortality_source_binding_invalid")
    return facts


def _mentioned(reference, text):
    return bool(re.search(r"(?<!\w)" + re.escape(reference.strip()) + r"(?!\w)", text, re.I))
