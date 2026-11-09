"""Read-only, import-only F2.7 runtime acceptance check.

Executed as: <sealed-runtime>/python.exe -I -B <protected-operator-proof>/verify_f27_runtime_imports.py
No Python source is passed through PowerShell's Windows native -c argument handling.
The verifier file itself is pinned to the exact source Git tree and sealed for
independent operator access before execution. No service or SSH is activated.
"""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import sys


def main() -> int:
    root = Path(sys.executable).resolve(strict=True).parent
    sys.path.insert(0, str(root))

    for module in (
        "cryptography",
        "win32api",
        "win32service",
        "aura_core.osworld.audit_broker_f27_activation",
        "aura_core.osworld.audit_broker_f27_bridge",
        "aura_core.osworld.audit_broker_ubuntu_transport",
        "aura_core.osworld.audit_broker_scm_identity",
    ):
        loaded = importlib.import_module(module)
        if module.startswith("aura_core."):
            resolved = Path(loaded.__file__).resolve(strict=True)
            if not resolved.is_relative_to(root):
                raise SystemExit("STOP: import outside sealed F2.7 runtime: " + str(resolved))

    scm_path = root / "aura_docker_broker_service.py"
    if not scm_path.is_file() or scm_path.is_symlink():
        raise SystemExit("STOP: missing or linked SCM entry module")

    spec = importlib.util.spec_from_file_location("aura_f27_scm_entry", scm_path)
    if spec is None or spec.loader is None:
        raise SystemExit("STOP: SCM entry module spec unavailable")

    scm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scm)
    if not hasattr(scm, "AuraDockerBrokerService"):
        raise SystemExit("STOP: SCM service class missing")

    print("PASS: F2.7 isolated Python and SCM import closure")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
