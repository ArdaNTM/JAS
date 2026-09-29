import pytest

from aura_core.config.backend import BackendConfig
from aura_core.config.kernel import KernelConfig
from aura_core.config.logging import LoggingConfig
from aura_core.config.runtime import RuntimeConfig
from aura_core.kernel.runtime import AuraKernel, KernelState


def make_config() -> KernelConfig:
    return KernelConfig(
        runtime=RuntimeConfig(model="qwen3:4b-instruct-2507-q4_K_M"),
        backend=BackendConfig(),
        logging=LoggingConfig(),
    )


def test_kernel_bootstraps_foundation_services_in_ready_state() -> None:
    kernel = AuraKernel(make_config())

    kernel.bootstrap()

    assert kernel.state is KernelState.READY
    assert kernel.service_registry is not None
    assert len(kernel.service_registry.records()) == 9
    assert all(
        component.report.ready
        for component in kernel.health_monitor.components()
    )
    assert kernel.diagnostics is not None
    assert kernel.diagnostics.snapshot().warnings == ()


def test_kernel_initializes_provider_registry() -> None:
    kernel = AuraKernel(make_config())

    kernel.bootstrap()

    assert kernel.provider_registry is not None
    assert kernel.service_registry is not None
    assert kernel.service_registry.get(
        "aura:provider_registry:0.1.0"
    )


def test_kernel_has_explicit_lifecycle_transitions() -> None:
    kernel = AuraKernel(make_config())

    with pytest.raises(RuntimeError, match="Illegal Kernel transition"):
        kernel.start()

    kernel.bootstrap()
    kernel.start()
    kernel.stop()

    assert kernel.state is KernelState.STOPPED
    assert kernel.service_registry is not None
    assert all(
        record.state.value == "stopped"
        for record in kernel.service_registry.records()
    )
