"""Opaque, request-bound authority for protected Oom Sakkie gateway reads."""

from dataclasses import dataclass
import time


GATEWAY_SERVICE = "oom_sakkie_telegram_gateway"
GATEWAY_CHANNEL = "telegram_read_only"
GATEWAY_PURPOSE = "owner_read_only_specialist"
ROOTLINE_READ_ONLY_TOOL = "rootline_water_energy_plan"
ROOTLINE_OBSERVATION_WRITE_TOOL = "rootline_owner_water_observation"
MAX_AUTHORITY_AGE_SECONDS = 120
_AUTHORITY_SEAL = object()
_OBSERVATION_WRITE_SEAL = object()


@dataclass(frozen=True)
class GatewayOwnerAuthority:
    service: str
    channel: str
    purpose: str
    owner_user_id: str
    private_chat_id: str
    tool_name: str
    issued_monotonic: float
    _seal: object


@dataclass(frozen=True)
class RootlineObservationWriteAuthority:
    owner_user_id: str
    private_chat_id: str
    mission_id: str
    provider_message_id: str
    provider_timestamp: str
    content_sha256: str
    issued_monotonic: float
    _seal: object


def issue_gateway_owner_authority(owner_user_id, private_chat_id):
    owner = str(owner_user_id or "").strip()
    chat = str(private_chat_id or "").strip()
    if not owner or not chat or owner != chat:
        return None
    return GatewayOwnerAuthority(
        service=GATEWAY_SERVICE,
        channel=GATEWAY_CHANNEL,
        purpose=GATEWAY_PURPOSE,
        owner_user_id=owner,
        private_chat_id=chat,
        tool_name="",
        issued_monotonic=time.monotonic(),
        _seal=_AUTHORITY_SEAL,
    )


def bind_gateway_owner_authority(authority, tool_name):
    if not _valid_base_authority(authority) or authority.tool_name:
        return None
    return GatewayOwnerAuthority(
        service=authority.service,
        channel=authority.channel,
        purpose=authority.purpose,
        owner_user_id=authority.owner_user_id,
        private_chat_id=authority.private_chat_id,
        tool_name=str(tool_name or "").strip(),
        issued_monotonic=authority.issued_monotonic,
        _seal=_AUTHORITY_SEAL,
    )


def validates_rootline_gateway_authority(authority):
    return (
        _valid_base_authority(authority)
        and authority.tool_name == ROOTLINE_READ_ONLY_TOOL
    )


def issue_rootline_observation_write_authority(authority, *, mission_id, provider_message_id,
                                               provider_timestamp, content_sha256):
    if not _valid_base_authority(authority) or authority.tool_name:
        return None
    values=[mission_id,provider_message_id,provider_timestamp,content_sha256]
    if not all(str(value or "").strip() for value in values): return None
    return RootlineObservationWriteAuthority(authority.owner_user_id,authority.private_chat_id,
        str(mission_id),str(provider_message_id),str(provider_timestamp),str(content_sha256),
        authority.issued_monotonic,_OBSERVATION_WRITE_SEAL)


def validates_rootline_observation_write_authority(authority):
    return (isinstance(authority,RootlineObservationWriteAuthority)
            and authority._seal is _OBSERVATION_WRITE_SEAL
            and 0 <= time.monotonic()-authority.issued_monotonic <= MAX_AUTHORITY_AGE_SECONDS
            and authority.owner_user_id == authority.private_chat_id)


def _valid_base_authority(authority):
    if not isinstance(authority, GatewayOwnerAuthority):
        return False
    age = time.monotonic() - authority.issued_monotonic
    return (
        authority._seal is _AUTHORITY_SEAL
        and authority.service == GATEWAY_SERVICE
        and authority.channel == GATEWAY_CHANNEL
        and authority.purpose == GATEWAY_PURPOSE
        and bool(authority.owner_user_id)
        and authority.owner_user_id == authority.private_chat_id
        and 0 <= age <= MAX_AUTHORITY_AGE_SECONDS
    )
