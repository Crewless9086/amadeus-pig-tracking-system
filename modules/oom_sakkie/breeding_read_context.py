"""Bounded identities behind displayed, read-only breeding-plan subjects."""
from collections.abc import Mapping

CONTRACT = "breeding_plan_subjects_v1"
READY_STATES = frozenset({"herdmaster_request_ready", "herdmaster_request_replay_recovered"})


def validated_subjects(value):
    if (not isinstance(value, Mapping) or set(value) != {"contract", "subjects"}
            or value.get("contract") != CONTRACT or not isinstance(value.get("subjects"), list)
            or len(value["subjects"]) > 6):
        return []
    rows = value["subjects"]
    for row in rows:
        if (not isinstance(row, Mapping) or set(row) != {"pig_id", "display_alias"}
                or any(not isinstance(row[key], str) or not row[key].strip()
                    or len(row[key]) > limit or any(ord(char) < 32 for char in row[key])
                    for key, limit in (("pig_id", 128), ("display_alias", 60)))):
            return []
    return [dict(row) for row in rows]


def selected_subjects(selected, *, language):
    from modules.oom_sakkie.family_presentation import animal_label
    rows = []
    for row in selected:
        alias = animal_label(row, language=language)[:60]
        if alias in {"Unknown animal", "Onbekende dier"}:
            return {"contract": CONTRACT, "subjects": []}
        rows.append({"pig_id": row.get("pig_id"), "display_alias": alias})
    value = {"contract": CONTRACT, "subjects": rows}
    return {"contract": CONTRACT, "subjects": validated_subjects(value)}
