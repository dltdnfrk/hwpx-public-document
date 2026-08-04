from __future__ import annotations

import logging

import pytest

from privacy import (
    ConsentRequiredError,
    CredentialStoreUnavailableError,
    ExternalTransmissionGateway,
    InMemoryConsentStore,
    KeychainCredentialStore,
    SensitiveInformationDetector,
    TransmissionEvent,
)
from public_document import (
    DocumentCommand,
    ProviderCapabilities,
    ProviderKind,
    ProviderRequest,
    ProviderResponse,
)


class RecordingAdapter:
    kind = ProviderKind.OPENAI
    capabilities = ProviderCapabilities(True, True, False)

    def __init__(self) -> None:
        self.requests: list[ProviderRequest] = []

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        return ProviderResponse((DocumentCommand("replace", "p-01", "완료"),))


def test_transmission_requires_matching_document_and_provider_consent() -> None:
    adapter = RecordingAdapter()
    gateway = ExternalTransmissionGateway(adapter, InMemoryConsentStore())

    with pytest.raises(ConsentRequiredError):
        gateway.transmit("doc-1", "주민 홍길동의 연락처 010-1234-5678", provider=ProviderKind.OPENAI)

    gateway.consent.grant("doc-1", ProviderKind.ANTHROPIC)
    with pytest.raises(ConsentRequiredError):
        gateway.transmit("doc-1", "본문", provider=ProviderKind.OPENAI)


def test_sensitive_content_is_detected_and_optionally_masked_before_transmission() -> None:
    adapter = RecordingAdapter()
    consent = InMemoryConsentStore()
    gateway = ExternalTransmissionGateway(adapter, consent)
    consent.grant("doc-1", ProviderKind.OPENAI)

    scan = SensitiveInformationDetector().scan("담당자: 홍길동, 010-1234-5678, hi@example.com")
    assert {match.category for match in scan.matches} == {"phone", "email"}

    gateway.transmit(
        "doc-1", "담당자: 홍길동, 010-1234-5678, hi@example.com", provider=ProviderKind.OPENAI,
        mask_sensitive=True,
    )
    assert "010-1234-5678" not in adapter.requests[0].instruction
    assert "hi@example.com" not in adapter.requests[0].instruction


def test_revocation_blocks_future_calls_and_events_never_contain_document_body() -> None:
    adapter = RecordingAdapter()
    consent = InMemoryConsentStore()
    events: list[TransmissionEvent] = []
    gateway = ExternalTransmissionGateway(adapter, consent, event_sink=events.append)
    consent.grant("doc-1", ProviderKind.OPENAI)
    gateway.transmit("doc-1", "비공개 본문", provider=ProviderKind.OPENAI)
    consent.revoke("doc-1", ProviderKind.OPENAI)

    with pytest.raises(ConsentRequiredError):
        gateway.transmit("doc-1", "비공개 본문", provider=ProviderKind.OPENAI)
    assert all("비공개 본문" not in repr(event) for event in events)
    assert events[0].body_length == len("비공개 본문")


def test_keychain_store_never_falls_back_to_plaintext_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("privacy.sys.platform", "linux")
    store = KeychainCredentialStore()

    with pytest.raises(CredentialStoreUnavailableError):
        store.set("openai", "secret")


def test_transmission_log_record_is_redacted(caplog: pytest.LogCaptureFixture) -> None:
    adapter = RecordingAdapter()
    consent = InMemoryConsentStore()
    consent.grant("doc-1", ProviderKind.OPENAI)
    gateway = ExternalTransmissionGateway(adapter, consent, logger=logging.getLogger("privacy"))

    with caplog.at_level(logging.INFO, logger="privacy"):
        gateway.transmit("doc-1", "비밀 문서 본문", provider=ProviderKind.OPENAI)

    assert "비밀 문서 본문" not in caplog.text
    assert caplog.records[0].document_id == "doc-1"
