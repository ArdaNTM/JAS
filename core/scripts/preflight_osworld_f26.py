"""Read-only Stage F2.6 Windows account preflight.

Run separately in terminals belonging to the actual agent, auditor and broker
accounts, with each expected SID obtained by a trusted operator beforehand.
The output is a diagnostic, NOT a signed receipt or a cross-account proof.
A return code of zero MUST NOT enable a broker service, change Docker ACLs,
or authorize an AURA action.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json

from aura_core.osworld.audit_broker_protocol import BrokerDenied
from aura_core.osworld.audit_broker_readiness import inspect_role_readiness


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stage F2.6 Windows read-only per-account readiness"
    )
    parser.add_argument("--role", choices=("agent", "auditor", "broker"), required=True)
    parser.add_argument("--expected-sid", required=True)
    arguments = parser.parse_args(argv)
    try:
        observed = inspect_role_readiness(
            role=arguments.role,
            expected_sid=arguments.expected_sid,
        )
        result = asdict(observed)
        result["disclaimer"] = (
            "This is a local unsigned preflight, not cross-account proof. "
            "It cannot authorize VM startup or isolation signing."
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (BrokerDenied, PermissionError, OSError, ValueError, TypeError) as exc:
        # Avoid disclosing a broker key, policy contents, or private paths.
        print(json.dumps({
            "status": "ISOLATION_BLOCKED",
            "signed": False,
            "role": arguments.role,
            "error_type": type(exc).__name__,
            "disclaimer": "No live broker activation or host receipt was attempted.",
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
