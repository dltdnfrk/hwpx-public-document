from __future__ import annotations

import pytest

from public_document import (
    CloudProviderAdapter,
    LocalProviderAdapter,
    ProviderCapabilities,
    ProviderKind,
    ProviderRequest,
    ProviderRegistry,
    ProviderUnavailableError,
)


def test_provider_registry_keeps_capabilities_behind_provider_contract() -> None:
    registry = ProviderRegistry(
        (
            CloudProviderAdapter(ProviderKind.OPENAI),
            CloudProviderAdapter(ProviderKind.ANTHROPIC),
            CloudProviderAdapter(ProviderKind.GEMINI),
            CloudProviderAdapter(ProviderKind.OPENAI_COMPATIBLE),
            LocalProviderAdapter(),
        )
    )

    openai = registry.select(ProviderKind.OPENAI)
    local = registry.select(ProviderKind.LOCAL)

    assert openai.capabilities == ProviderCapabilities(
        structured_commands=True,
        constrained_patches=True,
        local_execution=False,
    )
    assert local.capabilities == ProviderCapabilities(
        structured_commands=True,
        constrained_patches=True,
        local_execution=True,
    )
    assert openai.kind is ProviderKind.OPENAI
    assert local.kind is ProviderKind.LOCAL


def test_local_provider_slot_is_explicitly_unimplemented() -> None:
    registry = ProviderRegistry((CloudProviderAdapter(ProviderKind.OPENAI), LocalProviderAdapter()))

    with pytest.raises(ProviderUnavailableError, match="local provider adapter is not implemented"):
        registry.select(ProviderKind.LOCAL).generate(ProviderRequest("draft request"))


def test_local_provider_failure_does_not_fall_back_to_cloud() -> None:
    cloud = CloudProviderAdapter(ProviderKind.OPENAI)
    registry = ProviderRegistry((cloud, LocalProviderAdapter()))

    with pytest.raises(ProviderUnavailableError):
        registry.generate(ProviderRequest("draft request"), preferred=ProviderKind.LOCAL)

    assert cloud.generate_calls == 0
