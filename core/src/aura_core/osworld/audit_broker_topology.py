"""F2.3-B: run the *complete* OSWorld topology policy under broker Docker IO.

No standalone audit success flag is accepted. The pre-existing network_audit
validations (network, gateway, VM image, volumes, ports, devices and privileges)
are reused with a narrowly scoped injected Docker backend. This module has
no Windows service installation, Owner powers, key provisioning or signer.
"""
from __future__ import annotations

from pathlib import Path
import os
import re

from .audit_broker_protocol import AuditRequest, BrokerDenied
from .audit_broker_docker import DockerAuditBackend
from . import network_audit
from .isolation import BootIdentity, REQUIRED_CHECKS

_HEX32 = re.compile(r"[0-9a-f]{32}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _measured_identity(value: object) -> tuple[str, str]:
    if type(value) is not list or len(value) != 1 or type(value[0]) is not dict:
        raise BrokerDenied("Missing unambiguous Docker VM")
    info = value[0]
    labels = (info.get("Config") or {}).get("Labels") or {}
    run_id = labels.get("aura.osworld.run_id")
    cid = info.get("Id")
    if (type(cid) is not str or _HEX64.fullmatch(cid) is None
            or type(run_id) is not str or _HEX32.fullmatch(run_id) is None
            or (info.get("State") or {}).get("Running") is not True):
        raise BrokerDenied("Docker VM identity is untrusted")
    return run_id, cid


def _require_d_drive(image: Path) -> None:
    """Production Windows image location policy (mocked in hosted CI only)."""
    if os.name == "nt" and image.drive.upper() != "D:":
        raise BrokerDenied("Pinned Windows OSWorld image must remain on D:")


class BrokerTopologyAudit:
    """Never accept expected IDs or egress results from a network client."""

    def __init__(self, *, backend: DockerAuditBackend, pinned_vm_image: Path):
        if not isinstance(backend, DockerAuditBackend):
            raise BrokerDenied("Only the allowlisted Docker backend is accepted")
        if (not isinstance(pinned_vm_image, Path) or not pinned_vm_image.is_absolute()
                or pinned_vm_image.is_symlink() or not pinned_vm_image.is_file()):
            raise BrokerDenied("Pinned local VM image is missing or redirected")
        _require_d_drive(pinned_vm_image)
        self.backend = backend
        self.pinned_vm_image = pinned_vm_image

    def measured_identity(self, container_id: str) -> tuple[str, str]:
        """Only one exact 64-hex Docker container can be inspected."""
        if type(container_id) is not str or _HEX64.fullmatch(container_id) is None:
            raise BrokerDenied("Invalid request VM identifier")
        pair = _measured_identity(self.backend.inspect_container(container_id))
        if pair[1] != container_id:
            raise BrokerDenied("Inspected container ID differs from request")
        return pair

    def audit(self, request: AuditRequest) -> tuple[BootIdentity, dict[str, str], dict[str, bool]]:
        if type(request) is not AuditRequest:
            raise BrokerDenied("Invalid broker audit request")
        observed = self.measured_identity(request.container_id)
        if observed != (request.run_id, request.container_id):
            raise BrokerDenied("Request is not bound to measured Docker run")
        boot, ports, checks = network_audit.audit_network(
            container_id=request.container_id,
            vm_image=self.pinned_vm_image,
            docker_json_fn=self.backend.policy_inspect,
            probe_check=lambda cid, name, gateway: self.backend.fixed_probe(
                container_id=cid, name=name, gateway_ip=gateway,
            ),
        )
        if (boot.container_id != request.container_id
                or set(checks) != REQUIRED_CHECKS
                or any(value is not True for value in checks.values())):
            raise BrokerDenied("Complete OSWorld network policy was not satisfied")
        if self.measured_identity(request.container_id) != observed:
            raise BrokerDenied("VM changed identity during network audit")
        return boot, ports, checks
