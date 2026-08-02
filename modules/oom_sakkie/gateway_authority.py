"""Opaque, request-bound authority for protected Oom Sakkie gateway reads."""

from dataclasses import dataclass
import time


GATEWAY_SERVICE = "oom_sakkie_telegram_gateway"
GATEWAY_CHANNEL = "telegram_read_only"
GATEWAY_PURPOSE = "owner_read_only_specialist"
ROOTLINE_READ_ONLY_TOOL = "rootline_water_energy_plan"
MAX_AUTHORITY_AGE_SECONDS = 120
_AUTHORITY_SEAL = object()


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
