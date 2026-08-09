"""Opaque authority for one content-bound family delivery retry after proven zero send."""
from dataclasses import dataclass
import hashlib

_SEAL = object()


@dataclass(frozen=True)
class DeliveryRetryAuthority:
    mission_id: str
    card_mission_id: str
    text_sha256: str
    attempt_ordinal: int
    proof_identity: str
    _seal: object


def issue_delivery_retry_authority(*, mission_id, card_mission_id, text, proof_identity):
    values = tuple(str(value or "").strip() for value in
                   (mission_id, card_mission_id, text, proof_identity))
    if not all(values):
        return None
    return DeliveryRetryAuthority(values[0], values[1], hashlib.sha256(values[2].encode()).hexdigest(),
                                  2, values[3], _SEAL)


def validates_delivery_retry_authority(authority, *, mission_id, card_mission_id, text):
    return (isinstance(authority, DeliveryRetryAuthority) and authority._seal is _SEAL
            and authority.attempt_ordinal == 2 and bool(authority.proof_identity)
            and authority.mission_id == str(mission_id or "")
            and authority.card_mission_id == str(card_mission_id or "")
            and authority.text_sha256 == hashlib.sha256(str(text or "").encode()).hexdigest())
