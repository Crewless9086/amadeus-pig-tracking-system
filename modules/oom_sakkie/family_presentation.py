"""Pure family-message presentation; never an identity or authority boundary.

Typed producers resolve facts and labels before calling these helpers.  The
delivery envelope only decorates the heading; it does not rewrite body text,
interpret a report, translate safety wording or change a protected payload.
"""
from __future__ import annotations

from datetime import date, datetime
import html
from html.parser import HTMLParser
from typing import Mapping

_MONTHS = {
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
    "af": ("Januarie", "Februarie", "Maart", "April", "Mei", "Junie", "Julie", "Augustus", "September", "Oktober", "November", "Desember"),
}
_HEADING_ICONS = ("🌿", "🐷", "💧", "⚠️", "⚠", "✅", "❓", "📋", "🌱", "🔔", "⏸️", "📥")


def date_label(value, *, language="en"):
    """Render a typed calendar date without inferring an absent date or time."""
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        try:
            value = date.fromisoformat(str(value))
        except (ValueError, TypeError):
            return str(value or ("Onbekend" if language == "af" else "Unknown"))
    months = _MONTHS["af" if str(language).startswith("af") else "en"]
    return f"{value.day} {months[value.month - 1]} {value.year}"


def animal_label(row: Mapping, *, language="en"):
    """Use supplied canonical name/tag; internal IDs stay in audit metadata."""
    identity = str(row.get("pig_id") or row.get("Pig_ID") or row.get("sow_pig_id") or "").strip()
    for key in ("name", "pig_name", "Pig_Name", "tag_number", "Tag_Number", "sow_display_name", "label"):
        label = str(row.get(key) or "").strip()
        if label and label != identity and not label.upper().startswith("PIG-"):
            return label
    return "Onbekende dier" if str(language).startswith("af") else "Unknown animal"


def protected_animal_labels(rows):
    """Distinct labels for already-bound protected IDs; no action mutation."""
    animals={}
    for row in rows:
        identity=str(row.get('pig_id') or row.get('Pig_ID') or '').strip()
        if not identity:
            raise ValueError('protected_display_identity_required')
        name=str(row.get('name') or row.get('Name') or row.get('pig_name') or row.get('Pig_Name') or '').strip()
        tag=str(row.get('tag_number') or row.get('Tag_Number') or '').strip()
        if name==identity or name.upper().startswith('PIG-'):
            name=''
        if tag==identity or tag.upper().startswith('PIG-'):
            tag=''
        value=(name,tag)
        if identity in animals and animals[identity]!=value:
            raise ValueError('protected_display_identity_conflict')
        animals[identity]=value
    labels={identity:name or tag or identity for identity,(name,tag) in animals.items()}
    def collisions():
        groups={}
        for identity,label in labels.items():
            groups.setdefault(label.casefold(),[]).append(identity)
        return [identity for group in groups.values() if len(group)>1 for identity in group]
    for identity in collisions():
        labels[identity]=animals[identity][1] or identity
    for identity in collisions():
        labels[identity]=identity
    if collisions():
        raise ValueError('protected_display_identity_conflict')
    return labels


def heading(title, *, emoji="🌿"):
    return f"<b>{emoji} {html.escape(str(title), quote=False)}</b>"


def birth_counts(counts, *, language="en", include_zero_details=False):
    labels = (("total_born", "piglets born", "kleintjies gebore"), ("born_alive", "born alive", "lewend gebore"),
              ("stillborn", "stillborn", "doodgebore"),
              ("mummified", "mummified", "gemummifiseer"),
              ("died_after_live_birth", "died after live birth", "dood na lewende geboorte"))
    af = str(language).startswith('af')
    rows = []
    for key, english, local in labels:
        value = counts.get(key)
        if key not in {'total_born','born_alive','stillborn'} and value == 0 and not include_zero_details:
            continue
        shown = ('Onbekend' if af else 'Unknown') if value is None else str(value)
        rows.append(f"{shown} {local if af else english}")
    return rows


def message(title, *, bullets=(), status="", question="", language="en", emoji="🌿"):
    """Compose escaped typed facts; callers retain every material fact."""
    lines = [heading(title, emoji=emoji)]
    rows = [str(row).strip() for row in bullets if str(row).strip()]
    if rows:
        lines += ["", *["• " + html.escape(row, quote=False) for row in rows]]
    if status:
        lines += ["", html.escape(str(status), quote=False)]
    if question:
        lines += ["", html.escape(str(question), quote=False)]
    return "\n".join(lines)


def envelope(text, *, title="Oom Sakkie"):
    """Idempotently place one restrained icon inside an existing HTML heading.

    Only the first heading is touched. Arbitrary body prose and protected facts
    remain byte-for-byte intact; typed producers own their concise wording.
    """
    text = str(text or "").strip()
    if not text:
        return text
    icon = "🌿"
    for known in _HEADING_ICONS:
        if text.startswith(known + " <b>"):
            icon, text = known, text[len(known) + 1:]
            break
    if text.startswith("<b>") and "</b>" in text:
        end = text.index("</b>")
        label = text[3:end]
        if any(label.startswith(known + " ") for known in _HEADING_ICONS):
            return text
        return "<b>" + icon + " " + label + text[end:]
    return heading(title) + "\n\n" + text


def plain_text(text):
    """Render known Telegram HTML as text for the separate plain-text transport."""
    class Plain(HTMLParser):
        tags = {'b','strong','i','em','u','s','code','pre','a','blockquote','br'}
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts=[]
        def handle_data(self, value): self.parts.append(value)
        def handle_starttag(self, tag, attrs):
            if tag == 'br': self.parts.append('\n')
            elif tag not in self.tags: self.parts.append(self.get_starttag_text())
        def handle_endtag(self, tag):
            if tag not in self.tags: self.parts.append('</'+tag+'>')
    parser=Plain();parser.feed(str(text));parser.close()
    return ''.join(parser.parts)
