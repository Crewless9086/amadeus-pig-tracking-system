"""Canonical handling for opaque CHARLIE/CORE mission identifiers."""

from __future__ import annotations

import re


# Mission identifiers are opaque tokens. Hyphenated identifiers retain every
# segment; compact legacy identifiers remain supported when they contain both a
# letter and a digit. Matching never starts inside another word/token.
_HYPHENATED = re.compile(r"(?<![A-Z0-9-])([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)(?![A-Z0-9-])", re.I)
_COMPACT = re.compile(r"(?<![A-Z0-9-])([A-Z][A-Z0-9]{7,31})(?![A-Z0-9-])", re.I)
_MALFORMED = re.compile(r"(?<![A-Z0-9-])[A-Z][A-Z0-9]*(?:--+|-[^\s,.;:!?]*--|-[\s,.;:!?]|-$)", re.I)


def extract_mission_id(text):
    """Return one unambiguous complete mission identifier, or ``""``."""
    values = extract_mission_ids(text)
    return values[0] if len(values) == 1 else ""


def extract_mission_ids(text):
    """Return distinct complete mission identifiers in owner-text order."""
    value = str(text or "")
    found = []
    for pattern in (_HYPHENATED, _COMPACT):
        for match in pattern.finditer(value):
            candidate = match.group(1)
            if any(char.isdigit() for char in candidate):
                canonical = candidate.upper()
                if canonical not in found:
                    found.append(canonical)
    return found


def has_malformed_mission_id(text):
    """Detect identifier-shaped input whose separators cannot be canonical."""
    return bool(_MALFORMED.search(str(text or "")))
