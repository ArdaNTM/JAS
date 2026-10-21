import pytest

from aura_core.application.sandbox_contract import SandboxJob, SandboxPolicy


def test_sandbox_policy_defaults_to_isolated_limits():
    policy = SandboxPolicy()
    assert policy.network_enabled is False
    assert policy.host_mounts_enabled is False
    assert policy.docker_socket_enabled is False
    assert policy.allow_package_install is False


def test_policy_rejects_network_and_host_access():
    with pytest.raises(ValueError):
        SandboxPolicy(network_enabled=True)
    with pytest.raises(ValueError):
        SandboxPolicy(host_mounts_enabled=True)
    with pytest.raises(ValueError):
        SandboxPolicy(docker_socket_enabled=True)


def test_job_validation_is_bounded_and_requires_authorization_reference():
    policy = SandboxPolicy(max_input_bytes=16)
    job = SandboxJob(
        job_id="job-1",
        principal_id="local-user",
        runner="pyodide",
        source="print(1)",
        input_json="{}",
        authorization_id="permission-event-1",
    )
    job.validate(policy)

    oversized = SandboxJob(
        job_id="job-2",
        principal_id="local-user",
        runner="docker",
        source="x" * 17,
        input_json="{}",
        authorization_id="permission-event-2",
    )
    with pytest.raises(ValueError):
        oversized.validate(policy)


def test_job_rejects_blank_authorization_reference():
    job = SandboxJob(
        job_id="job-1",
        principal_id="local-user",
        runner="docker",
        source="print(1)",
        input_json="{}",
        authorization_id="",
    )
    with pytest.raises(ValueError):
        job.validate(SandboxPolicy())
