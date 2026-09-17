"""Typed zero-authority mortality packet consumer for Oom Sakkie."""
from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from modules.oom_sakkie.farm_manager_loop import (
    Authority, Provenance, SpecialistAvailability, SpecialistResult,
    SpecialistWorkItem, WorkState,
)

CONTRACT_VERSION="oom_sakkie_herdmaster_mortality_consumer_v1"
PACKET_TYPE="herdmaster.mortality_intelligence.v1"


def consume_mortality_packet(packet: Mapping, *, observed_at: datetime,
                             active_lifecycles: Sequence[Mapping]=(), language="en"):
    try:
        counts=packet.get("rolling_counts") or {}
        authority=packet.get("authority") or {}
        valid_counts=all(isinstance(counts.get(key),Mapping)
            and isinstance(counts[key].get("total"),int) and counts[key]["total"]>=0
            for key in ("7","30","90"))
        valid_actions=all(isinstance(value,str) and bool(value.strip()) for value in packet.get("actions") or [])
        valid_af_actions=all(isinstance(value,str) and bool(value.strip()) for value in packet.get("actions_af") or [])
        valid_authority=isinstance(authority,Mapping) and not any(bool(value) for value in authority.values())
    except (AttributeError,TypeError):
        valid_counts=valid_actions=valid_af_actions=valid_authority=False
    if (not isinstance(packet,Mapping) or packet.get("packet_type")!=PACKET_TYPE
            or not packet.get("review_identity") or not packet.get("evidence_digest")
            or not packet.get("deduplication_key") or not isinstance(packet.get("rolling_counts"),Mapping)
            or not isinstance(packet.get("actions"),list) or len(packet["actions"])>3
            or not valid_counts or not valid_actions or not valid_af_actions or not valid_authority
            or str(packet.get("question") or "").count("?")>1
            ):
        return _contained(observed_at,"mortality_packet_invalid")
    active_ids={str(row.get("pig_id") or "") for row in active_lifecycles
                if str(row.get("state") or "") in {"received","assigned","working","waiting_for_input","preview_ready","waiting_for_confirmation","preview_correction_pending"}}
    provenance=Provenance("herdmaster",str(packet["review_identity"]),
        (str(packet["deduplication_key"]),str(packet["evidence_digest"])),observed_at,1.0)
    counts=packet["rolling_counts"]
    is_af=str(language).casefold().startswith("af")
    title=(f"Hersien huidige vrekteseine ({counts['30']['total']} gedateerde verliese in 30 dae)"
           if is_af else f"Review current mortality signals ({counts['30']['total']} dated losses in 30 days)")
    language_text=str(packet.get("afrikaans") if is_af
                      else packet.get("english") or "")
    actions=" ".join(str(value) for value in packet["actions_af" if is_af else "actions"])
    question=str(packet.get("question_af" if is_af else "question") or "")
    active_questions=" ".join(str(row.get("current_question") or "").strip()
        for row in active_lifecycles if str(row.get("pig_id") or "") in active_ids)
    # An intelligence round must not repeat an observation already owned by a
    # governed animal lifecycle. Retain the assessment and suppress only the
    # overlapping grouped question.
    if question and active_questions:
        question=""
    item=SpecialistWorkItem(item_id=str(packet["review_identity"])+":assessment",
        dedupe_key="herdmaster:mortality-current-assessment",domain="herd",title=title,
        why=language_text,next_action=actions,assignee="charl",state=WorkState.URGENT,
        authority=Authority.ADVISORY,provenance=provenance,business_value=125,
        genuine_question=question,question_for="charl" if question else "")
    return SpecialistResult("herdmaster",str(packet["review_identity"]),observed_at,
        SpecialistAvailability.AVAILABLE,work_items=(item,)),{
            "contract_version":CONTRACT_VERSION,"active_lifecycle_pig_ids":tuple(sorted(active_ids)),
            "writes_farm_data":False,"writes_lifecycle":False,"writes_medical":False,
            "sends_telegram":False,"diagnoses":False,"treats":False}


def _contained(now,reason):
    return SpecialistResult("herdmaster","mortality-contained",now,
        SpecialistAvailability.CONTAINED),{"contract_version":CONTRACT_VERSION,
        "systemic_exception":reason,"writes_farm_data":False,"writes_lifecycle":False,
        "writes_medical":False,"sends_telegram":False,"diagnoses":False,"treats":False}
