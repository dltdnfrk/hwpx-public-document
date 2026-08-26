from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class ProviderConsentRequiredError(RuntimeError):
    pass


class ProviderKind(Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENAI_COMPATIBLE = "openai-compatible"
    LOCAL = "local"


@dataclass(frozen=True)
class ProviderCapabilities:
    structured_commands: bool
    constrained_patches: bool
    local_execution: bool


@dataclass(frozen=True)
class ProviderRequest:
    instruction: str
    document_id: str = ""


@dataclass(frozen=True)
class DocumentCommand:
    name: str
    target: str
    value: str


@dataclass(frozen=True)
class ProviderResponse:
    commands: tuple[DocumentCommand, ...]


class ProviderUnavailableError(RuntimeError):
    pass


class ProviderAdapter(Protocol):
    @property
    def kind(self) -> ProviderKind: ...

    @property
    def capabilities(self) -> ProviderCapabilities: ...

    def generate(self, request: ProviderRequest) -> ProviderResponse: ...


class ProviderTransport(Protocol):
    def generate(self, provider: ProviderKind, request: ProviderRequest) -> ProviderResponse: ...


class ConsentGateway(Protocol):
    def transmit(self, document_id: str, body: str, *, provider: ProviderKind) -> ProviderResponse: ...


class CloudProviderAdapter:
    def __init__(self, kind: ProviderKind, transport: ProviderTransport | None = None) -> None:
        if kind is ProviderKind.LOCAL:
            raise ValueError("cloud adapter requires a cloud provider kind")
        self._kind = kind
        self._transport = transport
        self._generate_calls = 0

    @property
    def kind(self) -> ProviderKind:
        return self._kind

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(True, True, False)

    @property
    def generate_calls(self) -> int:
        return self._generate_calls

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        if self._transport is None:
            raise ProviderUnavailableError(f"{self.kind.value} provider transport is not configured")
        self._generate_calls += 1
        return self._transport.generate(self.kind, request)


class LocalProviderAdapter:
    @property
    def kind(self) -> ProviderKind:
        return ProviderKind.LOCAL

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(True, True, True)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        del request
        raise ProviderUnavailableError("local provider adapter is not implemented")


class ProviderRegistry:
    def __init__(
        self,
        adapters: tuple[ProviderAdapter, ...],
        *,
        consent_gateway: ConsentGateway | None = None,
    ) -> None:
        self._adapters = {adapter.kind: adapter for adapter in adapters}
        self._consent_gateway = consent_gateway

    def select(self, kind: ProviderKind) -> ProviderAdapter:
        try:
            return self._adapters[kind]
        except KeyError as error:
            raise ProviderUnavailableError(f"{kind.value} provider is not configured") from error

    def generate(self, request: ProviderRequest, *, preferred: ProviderKind) -> ProviderResponse:
        adapter = self.select(preferred)
        if preferred is ProviderKind.LOCAL:
            return adapter.generate(request)
        if self._consent_gateway is None or not request.document_id.strip():
            raise ProviderConsentRequiredError(
                f"external provider access requires consent gateway and document_id for {preferred.value}"
            )
        return self._consent_gateway.transmit(
            request.document_id,
            request.instruction,
            provider=preferred,
        )
