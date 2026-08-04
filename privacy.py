from __future__ import annotations

import hashlib
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Final, Protocol

from public_document import (
    ProviderAdapter,
    ProviderConsentRequiredError,
    ProviderKind,
    ProviderRequest,
    ProviderResponse,
)


ConsentRequiredError = ProviderConsentRequiredError

class CredentialStoreUnavailableError(RuntimeError):
    pass

@dataclass(frozen=True)
class SensitiveMatch:
    category: str
    start: int
    end: int


@dataclass(frozen=True)
class SensitiveScan:
    matches: tuple[SensitiveMatch, ...]
    masked_text: str


class SensitiveInformationDetector:
    _PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
        ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
        ("phone", re.compile(r"(?<!\d)01[016789][- ]?\d{3,4}[- ]?\d{4}(?!\d)")),
        ("resident-id", re.compile(r"(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)")),
        ("api-key", re.compile(r"(?i)\b(?:sk|api|token)[-_][A-Za-z0-9_-]{12,}\b")),
    )

    def scan(self, text: str) -> SensitiveScan:
        matches = tuple(
            SensitiveMatch(category, found.start(), found.end())
            for category, pattern in self._PATTERNS
            for found in pattern.finditer(text)
        )
        return SensitiveScan(matches, self._mask(text, matches))

    @staticmethod
    def _mask(text: str, matches: tuple[SensitiveMatch, ...]) -> str:
        masked = text
        for match in sorted(matches, key=lambda item: item.start, reverse=True):
            masked = masked[: match.start] + f"[{match.category} 마스킹]" + masked[match.end :]
        return masked


class ConsentStore(Protocol):
    def is_granted(self, document_id: str, provider: ProviderKind) -> bool: ...

    def grant(self, document_id: str, provider: ProviderKind) -> None: ...

    def revoke(self, document_id: str, provider: ProviderKind) -> None: ...


class InMemoryConsentStore:
    def __init__(self) -> None:
        self._grants: set[tuple[str, ProviderKind]] = set()

    def is_granted(self, document_id: str, provider: ProviderKind) -> bool:
        return (document_id, provider) in self._grants

    def grant(self, document_id: str, provider: ProviderKind) -> None:
        self._grants.add((document_id, provider))

    def revoke(self, document_id: str, provider: ProviderKind) -> None:
        self._grants.discard((document_id, provider))


class KeychainCredentialStore:
    _SERVICE: Final = "public-document-provider"

    def _require_macos(self) -> None:
        if sys.platform != "darwin":
            raise CredentialStoreUnavailableError("macOS Keychain is required for cloud credentials")

    def set(self, account: str, secret: str) -> None:
        self._require_macos()
        subprocess.run(
            ["security", "add-generic-password", "-a", account, "-s", self._SERVICE, "-w", secret, "-U"],
            check=True,
            capture_output=True,
            text=True,
        )

    def get(self, account: str) -> str:
        self._require_macos()
        result = subprocess.run(
            ["security", "find-generic-password", "-a", account, "-s", self._SERVICE, "-w"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.rstrip("\n")

    def delete(self, account: str) -> None:
        self._require_macos()
        subprocess.run(
            ["security", "delete-generic-password", "-a", account, "-s", self._SERVICE],
            check=True,
            capture_output=True,
            text=True,
        )


@dataclass(frozen=True)
class TransmissionEvent:
    document_id: str
    provider: ProviderKind
    body_length: int
    body_sha256: str
    masked: bool


class ExternalTransmissionGateway:
    def __init__(
        self,
        adapter: ProviderAdapter,
        consent: ConsentStore,
        *,
        detector: SensitiveInformationDetector | None = None,
        event_sink: Callable[[TransmissionEvent], None] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.adapter = adapter
        self.consent = consent
        self._detector = detector or SensitiveInformationDetector()
        self._event_sink = event_sink
        self._logger = logger

    def transmit(
        self,
        document_id: str,
        body: str,
        *,
        provider: ProviderKind,
        mask_sensitive: bool = False,
    ) -> ProviderResponse:
        if provider is not self.adapter.kind or not self.consent.is_granted(document_id, provider):
            raise ConsentRequiredError(f"consent required for {document_id}/{provider.value}")
        scan = self._detector.scan(body)
        transmitted = scan.masked_text if mask_sensitive else body
        event = TransmissionEvent(
            document_id,
            provider,
            len(transmitted),
            hashlib.sha256(transmitted.encode("utf-8")).hexdigest(),
            mask_sensitive and bool(scan.matches),
        )
        if self._event_sink is not None:
            self._event_sink(event)
        if self._logger is not None:
            self._logger.info("external transmission", extra={"document_id": document_id, "provider": provider.value})
        return self.adapter.generate(ProviderRequest(transmitted, document_id))
