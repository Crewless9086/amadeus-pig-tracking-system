"""Channel-neutral metadata for the farm's canonical document capabilities.

This module deliberately contains no generator, delivery, route, persistence, or
printing callables.  It describes existing capabilities; owning domain services
remain responsible for evidence and effects.
"""

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import FrozenSet, Mapping, Tuple


class Support(str, Enum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "Unknown"


class RequesterRole(str, Enum):
    OWNER = "owner"
    FARM_MANAGER = "farm_manager"
    SALES_OPERATOR = "sales_operator"


class Requester(str, Enum):
    APPLICATION = "application"
    OOM_SAKKIE = "oom_sakkie"
    HERDMASTER = "herdmaster"
    SAM = "sam"


@dataclass(frozen=True)
class InputField:
    name: str
    description: str


@dataclass(frozen=True)
class PreviewContract:
    support: Support
    media_type: str | None
    owner: str | None


@dataclass(frozen=True)
class DocumentDefinition:
    document_id: str
    display_name_en: str
    display_name_af: str
    required_inputs: Tuple[InputField, ...]
    optional_filters: Tuple[InputField, ...]
    generator_id: str
    owning_domain: str
    evidence_source: str
    preview: PreviewContract
    pdf: Support
    telegram_delivery: Support
    direct_print: Support
    requester_roles: FrozenSet[RequesterRole]
    requesters: FrozenSet[Requester]
    audit_fields: Tuple[str, ...]
    idempotency_key_fields: Tuple[str, ...]
    telegram_recipient_binding_required: bool
    notes: str = ""


def _field(name: str, description: str) -> InputField:
    return InputField(name=name, description=description)


_CATALOGUE = (
    DocumentDefinition(
        "farm.weekly_weight_sheet.v1", "Weekly weight sheet", "Weeklikse gewigstaat",
        (_field("sheet_date", "Displayed capture date; defaults to the current local date in the existing view"),),
        (_field("pen_ids", "Optional canonical pen identifiers"),),
        "web.print_sheets.v1", "HERDMASTER", "Supabase farm livestock/weight read model",
        PreviewContract(Support.SUPPORTED, "text/html", "application:/print-sheets"),
        Support.UNSUPPORTED, Support.UNSUPPORTED, Support.UNKNOWN,
        frozenset({RequesterRole.OWNER, RequesterRole.FARM_MANAGER}),
        frozenset({Requester.APPLICATION, Requester.OOM_SAKKIE, Requester.HERDMASTER}),
        ("authenticated_principal_id", "requester", "document_id", "canonical_input_ids", "generator_id", "channel", "decision", "result_status"),
        ("authenticated_principal_id", "requester", "document_id", "canonical_input_ids", "generator_id", "channel", "requested_revision"), False,
        "Mission 2 may add PDF and Telegram adapters without changing this generator identity.",
    ),
    DocumentDefinition(
        "farm.weight_report.v1", "Weight report", "Gewigsverslag",
        (_field("date_from", "Inclusive report start date"), _field("date_to", "Inclusive report end date")),
        (_field("pig_ids", "Optional canonical pig identifiers"), _field("pen_ids", "Optional canonical pen identifiers")),
        "web.weight_report.v1", "HERDMASTER", "Supabase canonical weight read model",
        PreviewContract(Support.SUPPORTED, "text/html", "application:/weight-report"),
        Support.UNSUPPORTED, Support.UNSUPPORTED, Support.UNKNOWN,
        frozenset({RequesterRole.OWNER, RequesterRole.FARM_MANAGER}), frozenset({Requester.APPLICATION, Requester.OOM_SAKKIE, Requester.HERDMASTER}),
        ("authenticated_principal_id", "requester", "document_id", "canonical_input_ids", "generator_id", "channel", "decision", "result_status"),
        ("authenticated_principal_id", "requester", "document_id", "canonical_input_ids", "generator_id", "channel", "requested_revision"), False,
    ),
    DocumentDefinition(
        "farm.mating_litter_record.v1", "Mating and litter record", "Parings- en werpselrekord",
        (),
        (_field("mating_id", "Optional canonical mating identifier"), _field("litter_id", "Optional canonical litter identifier; must agree when both are supplied")),
        "web.mating_litter_record.v1", "HERDMASTER", "Supabase canonical mating and litter read models",
        PreviewContract(Support.SUPPORTED, "text/html", "application:/paring-werpselrekord"),
        Support.UNSUPPORTED, Support.UNSUPPORTED, Support.UNKNOWN,
        frozenset({RequesterRole.OWNER, RequesterRole.FARM_MANAGER}), frozenset({Requester.APPLICATION, Requester.OOM_SAKKIE, Requester.HERDMASTER}),
        ("authenticated_principal_id", "requester", "document_id", "canonical_input_ids", "generator_id", "channel", "decision", "result_status"),
        ("authenticated_principal_id", "requester", "document_id", "canonical_input_ids", "generator_id", "channel", "requested_revision"), False,
    ),
    DocumentDefinition(
        "sales.loading_sheet.v1", "Loading sheet", "Laaistaat",
        (_field("order_id", "Canonical order identifier"),), (),
        "modules.documents.loading_sheet_service.generate_loading_sheet_for_order", "SAM", "Transitional Supabase order reads with Google Sheets fallback plus livestock projection inputs",
        PreviewContract(Support.UNKNOWN, None, None), Support.SUPPORTED, Support.SUPPORTED, Support.UNKNOWN,
        frozenset({RequesterRole.OWNER, RequesterRole.SALES_OPERATOR}), frozenset({Requester.APPLICATION, Requester.SAM}),
        ("authenticated_principal_id", "requester", "document_id", "canonical_input_ids", "generator_id", "channel", "recipient_binding", "decision", "result_status"),
        ("authenticated_principal_id", "requester", "document_id", "canonical_input_ids", "generator_id", "channel", "requested_revision", "recipient_binding"), True,
    ),
    DocumentDefinition(
        "sales.removal_transport.v1", "Removal / transport document", "Verwyderings- / vervoerdokument",
        (_field("order_id", "Canonical order identifier"),),
        (_field("movement_date", "Optional supported movement date"), _field("movement_time", "Optional supported movement time")),
        "modules.documents.movement_documents_service.generate_removal_certificate_for_order", "SAM", "Transitional Supabase order reads with Google Sheets fallback plus operator/default movement facts whose authority may be Unknown",
        PreviewContract(Support.UNKNOWN, None, None), Support.SUPPORTED, Support.SUPPORTED, Support.UNKNOWN,
        frozenset({RequesterRole.OWNER, RequesterRole.SALES_OPERATOR}), frozenset({Requester.APPLICATION, Requester.SAM}),
        ("authenticated_principal_id", "requester", "document_id", "canonical_input_ids", "generator_id", "channel", "recipient_binding", "decision", "result_status"),
        ("authenticated_principal_id", "requester", "document_id", "canonical_input_ids", "generator_id", "channel", "requested_revision", "recipient_binding"), True,
    ),
    DocumentDefinition(
        "sales.health_declaration.v1", "Health declaration", "Gesondheidsverklaring",
        (_field("order_id", "Canonical order identifier"),),
        (),
        "modules.documents.movement_documents_service.generate_health_declaration_for_order", "SAM", "Mixed transitional order/livestock inputs plus operator-entered health notes; medical evidence authority is Unknown",
        PreviewContract(Support.UNKNOWN, None, None), Support.SUPPORTED, Support.SUPPORTED, Support.UNKNOWN,
        frozenset({RequesterRole.OWNER, RequesterRole.SALES_OPERATOR}), frozenset({Requester.APPLICATION, Requester.SAM}),
        ("authenticated_principal_id", "requester", "document_id", "canonical_input_ids", "generator_id", "channel", "recipient_binding", "decision", "result_status"),
        ("authenticated_principal_id", "requester", "document_id", "canonical_input_ids", "generator_id", "channel", "requested_revision", "recipient_binding"), True,
        "Generator output is supported, but its medical evidence authority is Unknown; the catalogue accepts no caller medical assertions.",
    ),
    DocumentDefinition(
        "sales.quote.v1", "Quote", "Kwotasie",
        (_field("order_id", "Canonical order identifier"),), (),
        "modules.documents.quote_service.generate_quote_for_order", "SAM", "Transitional mixed Supabase reads with Google Sheets master/line fallback and overlay",
        PreviewContract(Support.UNKNOWN, None, None), Support.SUPPORTED, Support.UNSUPPORTED, Support.UNKNOWN,
        frozenset({RequesterRole.OWNER, RequesterRole.SALES_OPERATOR}), frozenset({Requester.APPLICATION, Requester.SAM}),
        ("authenticated_principal_id", "requester", "document_id", "canonical_input_ids", "generator_id", "channel", "decision", "result_status"),
        ("authenticated_principal_id", "requester", "document_id", "canonical_input_ids", "generator_id", "channel", "requested_revision"), False,
        "A quote is supported; no separate order-confirmation generator is currently proven.",
    ),
)

CATALOGUE: Mapping[str, DocumentDefinition] = MappingProxyType({item.document_id: item for item in _CATALOGUE})


def get_document(document_id: str) -> DocumentDefinition:
    return CATALOGUE[document_id]


def require_generator(document_id: str, requested_generator_id: str) -> str:
    """Bind an adapter to the catalogue owner; never choose or invoke it."""
    expected = get_document(document_id).generator_id
    if requested_generator_id != expected:
        raise PermissionError("document request denied")
    return expected


def require_requester(document_id: str, authenticated_role: RequesterRole, requester: Requester) -> None:
    document = get_document(document_id)
    if authenticated_role not in document.requester_roles or requester not in document.requesters:
        raise PermissionError("document request denied")


def require_delivery_support(document_id: str, method: str) -> None:
    document = get_document(document_id)
    support = {
        "pdf": document.pdf,
        "telegram": document.telegram_delivery,
        "direct_print": document.direct_print,
    }.get(method, Support.UNKNOWN)
    if support is not Support.SUPPORTED:
        raise PermissionError("document request denied")
