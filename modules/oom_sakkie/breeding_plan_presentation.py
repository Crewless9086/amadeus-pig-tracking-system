"""Pure, bounded breeding-plan wording over the existing canonical worklist.

No prose parsing, source mutation or inference of physical observations. Tasks
retain their original identities; detailed facts come from one exact case.
"""
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import html

from modules.oom_sakkie.family_presentation import animal_label, date_label
from modules.pig_weights.herdmaster_breeding_policy import (
    BREEDING_BODY_CONDITION_MIN, BREEDING_BODY_CONDITION_MAX,
)

_CHECKS = {
    "body condition": ("current body-condition score", "huidige liggaamskondisietelling"),
    "current weight": ("current weight", "huidige gewig"),
    "movement": ("walking and leg condition", "loopvermoë en beentoestand"),
    "visible concerns": ("any visible injuries or concerns", "enige sigbare beserings of probleme"),
    "pregnancy result": ("pregnancy result", "dragtigheidsuitslag"),
    "governed pregnancy check result": ("dated pregnancy-check result", "gedateerde dragtigheidstoetsuitslag"),
    "attributable farrowing observation chronology": ("farrowing observation and litter dates", "waarneming oor werping en werpseldatums"),
    "governed actual weaning date": ("actual weaning date", "werklike speendatum"),
    "service chronology": ("service dates", "dekdatums"),
    "owner decision": ("owner decision", "eienaar se besluit"),
    "review the attributable prince trial outcome.": ("current Prince trial outcome", "huidige Prince-proefuitslag"),
    "medical or withdrawal evidence": ("medical or withdrawal clearance", "mediese of onttrekkingsklaring"),
}
_STATES = {
    "Recovery hold": ("Recovery hold remains active; fresh condition evidence and explicit clearance are needed.",
                      "Herstelwag bly aktief; nuwe kondisiebewyse en uitdruklike klaring is nodig."),
    "Needs current condition": ("Placement review waits for a current body-condition score.",
                                "Plasingshersiening wag op 'n huidige liggaamskondisietelling."),
    "Hold for medical/withdrawal evidence": ("Breeding is on hold for medical, withdrawal or availability clearance.",
                                            "Teling wag op mediese, onttrekkings- of beskikbaarheidsklaring."),
    "Near farrowing observation": ("Reported close to farrowing; monitor her. Father and mating date remain unknown.",
                                   "Na berig word naby werping; hou haar dop. Vader en dekdatum bly onbekend."),
    "Nursing": ("Still nursing; wait for recorded weaning before placement review.",
                "Soog nog; wag op aangetekende speenwerk voor plasingshersiening."),
    "Do Not Breed": ("Excluded from breeding by current lifecycle, location or purpose.",
                     "Uitgesluit van teling volgens huidige lewenstatus, ligging of doel."),
    "Controlled trial backlog": ("Await the current trial outcome before another trial placement.",
                                 "Wag op die huidige proef se uitslag voor nog 'n proefplasing."),
    "Repeat-service decision required": ("Repeated unsuccessful services need a decision before another placement.",
                                          "Herhaalde onsuksesvolle dekkings verg 'n besluit voor nog 'n plasing."),
    "Confirmed not pregnant for latest mating": (
        "A not-pregnant result is recorded for the latest mating. Review return-to-heat or repeat-service evidence before another placement.",
        "'n Nie-dragtige uitslag is vir die jongste dekking aangeteken. Hersien terugkeer na bronstigheid of herdekbewyse voor nog 'n plasing."),
    "Conflicting pregnancy evidence": (
        "Pregnancy results for the latest mating conflict; reconcile them before another breeding decision.",
        "Dragtigheidsuitslae vir die jongste dekking bots; klaar dit uit voor nog 'n teelbesluit."),
    "Pregnancy evidence conflicts with future mating chronology": (
        "The recorded mating date is in the future. Review and correct the dates before a breeding decision.",
        "Die aangetekende dekdatum is in die toekoms. Hersien en korrigeer die datums voor 'n teelbesluit."),
    "Pregnancy evidence is future-dated and not currently applicable": (
        "The pregnancy result is future-dated and cannot establish current status. Review and correct the dates.",
        "Die dragtigheidsuitslag is in die toekoms gedateer en bewys nie huidige status nie. Hersien en korrigeer die datums."),
    "Pregnancy evidence conflicts with mating chronology": (
        "The pregnancy result predates the latest mating. Reconcile the dates before a breeding decision.",
        "Die dragtigheidsuitslag dateer van voor die jongste dekking. Klaar die datums uit voor 'n teelbesluit."),
    "Historical pregnancy result; current status Unknown": (
        "The pregnancy result is historical; current status is unknown. Review current reproductive evidence before a breeding decision.",
        "Die dragtigheidsuitslag is histories; huidige status is onbekend. Hersien huidige voortplantingsbewyse voor 'n teelbesluit."),
    "Pregnancy result is provisional or unattributed": (
        "The pregnancy result is provisional or lacks attribution. Review current reproductive evidence before a breeding decision.",
        "Die dragtigheidsuitslag is voorlopig of nie aan die regte gebeurtenis gekoppel nie. Hersien huidige voortplantingsbewyse voor 'n teelbesluit."),
    "Confirmed pregnant": (
        "Pregnancy is confirmed; monitor pregnancy and farrowing milestones.",
        "Dragtigheid is bevestig; hou dragtigheids- en werpmylpale dop."),
    "Pregnancy evidence pending": ("A mating is recorded; pregnancy is not confirmed.",
                                   "'n Dekking is aangeteken; dragtigheid is nie bevestig nie."),
}

_TASK_SUMMARIES = {
    "resolve reproductive chronology": (
        "No active cycle or confirmed weaning date establishes the next placement. Review reproductive history.",
        "Geen aktiewe siklus of bevestigde speendatum bepaal die volgende plasing nie. Hersien die voortplantingsgeskiedenis."),
    "resolve actual weaning chronology": (
        "Actual weaning is unresolved; reconcile the litter records before placement.",
        "Werklike speenwerk is onopgelos; klaar die werpselrekords uit voor plasing."),
    "reconcile farrowing observation with litter chronology": (
        "The farrowing observation and litter dates need reconciliation before placement.",
        "Die waarneming oor werping en die werpseldatums moet voor plasing uitgeklaar word."),
    "inspect for breeding readiness": (
        "Breeding readiness needs the listed observations.",
        "Teelgereedheid verg die gelyste waarnemings."),
}


def _map(value):
    return value if isinstance(value, Mapping) else {}


def _safe(value):
    return html.escape(str(value), quote=False)


def _date(value, language):
    # These fields are calendar facts; preserve unknown dates rather than guess.
    try:
        parsed = value.date() if isinstance(value, datetime) else date.fromisoformat(str(value)[:10])
        return date_label(parsed, language=language)
    except (TypeError, ValueError):
        return "datum onbekend" if language == "af" else "date unknown"


def _case(packet, row):
    identity = row.get("pig_id")
    matches = [value for value in packet.get("cases") or ()
               if isinstance(value, Mapping) and identity and value.get("pig_id") == identity]
    if len(matches) != 1:
        return None
    classification = _map(matches[0].get("classification"))
    state = row.get("provisional_recommendation")
    # Cohort scheduling can retire a ready task into the controlled-trial backlog.
    if (classification.get("state") != state
            and not (state == "Controlled trial backlog"
                     and classification.get("state") == "Ready for mating review")):
        return None
    known = _map(row.get("known_evidence"))
    known_states = {None, classification.get("state")}
    if state == "Controlled trial backlog":
        known_states.add("Ready for mating review")  # Existing cohort projection preserves this earlier state.
    if known.get("state") not in known_states:
        return None
    return classification


def _proposal(packet, row, language):
    matches = [(group, member) for group in _map(packet.get("placement_cohorts")).get("cohorts") or ()
               if isinstance(group, Mapping) for member in group.get("females") or ()
               if isinstance(member, Mapping) and member.get("pig_id") == row.get("pig_id")]
    if len(matches) != 1:
        return None
    group, member = matches[0]
    if (not row.get("proposed_placement_date")
            or row["proposed_placement_date"] != member.get("proposed_placement_date")
            or row["proposed_placement_date"] != group.get("start_date")
            or not group.get("boar_pig_id")):
        return None
    boar = animal_label({"pig_id": group["boar_pig_id"], "tag_number": group.get("boar_name")}, language=language)
    if boar in {"Unknown animal", "Onbekende dier"} or boar != member.get("primary_boar"):
        return None
    when = _date(group["start_date"], language)
    end = _date(group.get("end_date"), language)
    trial = member.get("evidence_class") == "Controlled trial"
    text = (f"Voorgestelde {'proef' if trial else ''}plasing by {boar}: {when} tot {end}; nog nie uitgevoer nie."
            if language == "af" else
            f"Proposed {'trial ' if trial else ''}placement with {boar}: {when} to {end}; not yet performed.")
    reserve = member.get("reserve_boar")
    if reserve and len(str(reserve)) <= 60 and not str(reserve).upper().startswith("PIG-"):
        text += (f" Reserwe: {reserve}." if language == "af" else f" Reserve: {reserve}.")
    classes = {
        "Proven repeat": ("proven repeat pairing", "bewese herhaalde paring"),
        "Supported cross": ("supported pairing", "ondersteunde paring"),
        "Corrective cross": ("corrective pairing", "regstellende paring"),
        "Controlled trial": ("controlled trial", "beheerde proef"),
        "Limited evidence": ("limited pairing evidence", "beperkte paringsbewyse"),
    }
    label = classes.get(member.get("evidence_class"))
    if label:
        text += (" Bewyse: " if language == "af" else " Evidence: ") + label[int(language == "af")] + "."
    return text


def _legacy_details(row, *, language):
    """Keep bounded, attributed task content without asserting richer case facts."""
    af = language == "af"
    from modules.oom_sakkie.owner_response_composer import _clip
    groups = {"pregnancy check due": ("Pregnancy check due", "Dragtigheidstoets verskuldig"),
              "resolve reproductive chronology": ("Reproductive dates need review", "Voortplantingsdatums verg hersiening")}
    group = str(row.get("task_group") or "")
    lines = [groups[group][int(af)] + "."] if group in groups else []
    if group and group not in groups:
        lines.append(("Brontaak: " if af else "Source task: ") + _clip(group, 90))
    why = _clip(row.get("why"), 120)
    if why:
        lines.append(("Bronnota (oorspronklike woorde): " if af else "Source note: ") + why)
    checks = []
    for value in row.get("required_checks") or ():
        key = str(value).strip().replace("_", " ").casefold()
        if key == "owner review":
            continue
        checks.append(_safe(_CHECKS[key][int(af)]) if key in _CHECKS else _clip(value, 50))
    if checks:
        lines.append(("Vereistes uit werklys: " if af else "Worklist requirements: ") + "; ".join(checks[:3])
                     + (f" (+{len(checks)-3})" if len(checks) > 3 else "") + ".")
    lines.append("Volledige bewyse vir plasing ontbreek." if af else "Complete placement evidence is unavailable.")
    return " ".join(lines)


def breeding_task_lines(packet, row, *, language="en"):
    """Return display lines and, only when supported, one factual next question."""
    language = "af" if str(language).casefold().startswith("af") else "en"
    af = language == "af"
    name = animal_label(row, language=language)[:60]
    classification = _case(packet, row)
    state = row.get("provisional_recommendation")
    prefix = f"• <b>{_safe(name)}</b> — "
    unavailable = ("Hersiening nodig; volledige of ooreenstemmende bewyse ontbreek."
                   if af else "Review needed; complete matching evidence is unavailable.")
    if classification is None:
        if not packet.get("cases"):
            return [prefix + _legacy_details(row, language=language)], None
        return [prefix + unavailable], None
    if classification.get("conflicting"):
        if state == "Needs Data" and row.get("task_group") in _TASK_SUMMARIES:
            return [prefix + _safe(_TASK_SUMMARIES[row["task_group"]][int(af)])], None
        return [prefix + ("Teenstrydige teelrekords moet eers nagegaan word; geen nuwe plasing nie."
                          if af else "Conflicting breeding records need review before a new placement.")], None
    text = None
    question = None
    body_condition_question = False
    if state == "Boar exposure active":
        exposure = _map(classification.get("active_exposure"))
        if not exposure.get("exposure_identity") or not exposure.get("boar_pig_id"):
            return [prefix + unavailable], None
        text = "Blootstelling aan 'n beer is aangeteken en steeds aktief" if af else "Recorded boar exposure is still active"
        if exposure.get("started_on"):
            text += (" sedert " if af else " since ") + _date(exposure["started_on"], language)
        text += "."
        if exposure.get("planned_removal_on"):
            text += (" Beplande uithaal: " if af else " Planned removal: ") + _date(exposure["planned_removal_on"], language) + "."
    elif state == "Body condition recovery":
        try:
            score = Decimal(str(classification.get("body_condition")))
        except InvalidOperation:
            score = Decimal("NaN")
        if not score.is_finite():
            return [prefix + unavailable], None
        minimum, maximum = Decimal(str(BREEDING_BODY_CONDITION_MIN)), Decimal(str(BREEDING_BODY_CONDITION_MAX))
        if minimum <= score <= maximum:
            return [prefix + unavailable], None
        when = _date(classification.get("body_condition_observed_at"), language)
        boundary = (f"onder minimum {minimum.normalize():g}" if score < minimum else f"bo maksimum {maximum.normalize():g}") if af else (
            f"below minimum {minimum.normalize():g}" if score < minimum else f"above maximum {maximum.normalize():g}")
        text = (f"Herstel nodig. Laaste kondisietelling {score.normalize():g} ({when}), {boundary}."
                if af else f"Recovery needed. Last body-condition score {score.normalize():g} ({when}), {boundary}.")
        text += (" Nuwe kondisiebewyse en uitdruklike klaring is nodig." if af else
                 " Fresh condition evidence and explicit clearance are needed.")
        body_condition_question = True
        question = (f"Wat is {name} se huidige liggaamskondisietelling?" if af else
                    f"What is {name}'s current body-condition score?")
    elif state == "Ready for mating review":
        text = _proposal(packet, row, language) or (
            "Plasingshersiening is nodig; geen volledige beer-en-datumvoorstel is beskikbaar nie." if af else
            "Placement review is needed; no complete boar-and-date proposal is available.")
    elif state in _STATES:
        text = _STATES[state][int(af)]
    elif state == "Needs Data" and row.get("task_group") in _TASK_SUMMARIES:
        text = _TASK_SUMMARIES[row["task_group"]][int(af)]
    else:
        # An added canonical state must retain its explicit source action/reason;
        # never silently flatten it into a vague generic review message.
        return [prefix + _legacy_details(row, language=language)], None
    checks = []
    check_keys = []
    unsupported = False
    for check in row.get("required_checks") or ():
        key = str(check).strip().replace("_", " ").casefold()
        if key == "owner review":
            continue  # A decision/review marker is not a missing physical fact.
        if key in _CHECKS:
            check_keys.append(key)
            checks.append(_CHECKS[key][int(af)])
        else:
            unsupported = True
    checks = list(dict.fromkeys(checks))
    if checks:
        text += (" Benodig: " if af else " Needed: ") + "; ".join(checks) + "."
        if question is None and check_keys[0] != "review the attributable prince trial outcome.":
            body_condition_question = check_keys[0] == "body condition"
            question = (f"Kan jy {name} se {checks[0]} gee?" if af else
                        f"Can you provide {name}'s {checks[0]}?")
    elif state == "Needs current condition":
        body_condition_question = True
        question = (f"Wat is {name} se huidige liggaamskondisietelling?" if af else
                    f"What is {name}'s current body-condition score?")
    missing_count = len(classification.get("missing") or ())
    if missing_count:
        text += (f" Nog {missing_count} bewysgaping(s) op die volledige werklys." if af else
                 f" {missing_count} evidence gap(s) remain on the detailed worklist.")
    if unsupported:
        text += (" Ander vereistes wag op hersiening." if af else "Other requirements await review.")
    if question and body_condition_question:
        question += (" Sluit haar naam en die waarnemingsdatum by jou antwoord in." if af else
                     " Include her name and the observation date in your reply.")
    return [prefix + _safe(text)], _safe(question) if question else None
