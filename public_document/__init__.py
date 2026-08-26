from __future__ import annotations

from .document_models import (
    BetaDocumentGroup,
    Claim,
    ClaimKind,
    CurrentOfficialRule,
    DocumentTable,
    DocumentTableCell,
    Draft,
    DraftValidation,
    Evidence,
    EvidenceProvenance,
    GuidedAnswers,
    InstitutionTemplate,
    ManualDraftResult,
    Paragraph,
    ParagraphStatus,
    Section,
    TemplateConflictWarning,
    TemplateOverride,
    TemplateRegistry,
)
from .draft_builder import (
    build_beta_draft,
    build_policy_plan_draft,
    validate_draft,
)
from .hwp_export import (
    BundledRhwpAdapter,
    DuplicateWriteError,
    HWPAdapter,
    HWPCompatibilityError,
    HWPExportError,
    HWPExportOutcome,
    HWPUnavailableError,
    PageLimitExceededError,
)
from .hwpx_package import complete_manual_draft, export_hwpx
from .hwpx_xml import _HC, _HP, _NS
from .provider_contracts import (
    CloudProviderAdapter,
    ConsentGateway,
    DocumentCommand,
    LocalProviderAdapter,
    ProviderAdapter,
    ProviderCapabilities,
    ProviderConsentRequiredError,
    ProviderKind,
    ProviderRegistry,
    ProviderRequest,
    ProviderResponse,
    ProviderTransport,
    ProviderUnavailableError,
)


def __getattr__(name: str):
    if name in {"HWPXValidation", "hwpx_content_hash", "validate_hwpx"}:
        from hwpx import HWPXValidation, hwpx_content_hash, validate_hwpx

        return {"HWPXValidation": HWPXValidation, "hwpx_content_hash": hwpx_content_hash, "validate_hwpx": validate_hwpx}[name]
    if name in {
        "ConsentRequiredError",
        "CredentialStoreUnavailableError",
        "ExternalTransmissionGateway",
        "InMemoryConsentStore",
        "KeychainCredentialStore",
        "SensitiveInformationDetector",
        "SensitiveMatch",
        "SensitiveScan",
        "TransmissionEvent",
    }:
        from privacy import (
            ConsentRequiredError,
            CredentialStoreUnavailableError,
            ExternalTransmissionGateway,
            InMemoryConsentStore,
            KeychainCredentialStore,
            SensitiveInformationDetector,
            SensitiveMatch,
            SensitiveScan,
            TransmissionEvent,
        )
        return {
            "ConsentRequiredError": ConsentRequiredError,
            "CredentialStoreUnavailableError": CredentialStoreUnavailableError,
            "ExternalTransmissionGateway": ExternalTransmissionGateway,
            "InMemoryConsentStore": InMemoryConsentStore,
            "KeychainCredentialStore": KeychainCredentialStore,
            "SensitiveInformationDetector": SensitiveInformationDetector,
            "SensitiveMatch": SensitiveMatch,
            "SensitiveScan": SensitiveScan,
            "TransmissionEvent": TransmissionEvent,
        }[name]
    raise AttributeError(name)
