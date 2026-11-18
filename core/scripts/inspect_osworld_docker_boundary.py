"""Read-only Stage F2.5 Windows Docker named-pipe access inspection.

Run under each actual Windows identity (agent, auditor, broker) with
--expected-sid pinned out-of-band by the operator. Observations printed by
this script are NOT signed and never authorize starting a live broker or
signing an OSWorld receipt. There is no Docker command, group edit or ACL
change. A missing/busy daemon is INCONCLUSIVE, not an isolation pass.
"""
from __future__ import annotations

import argparse
import json

from aura_core.osworld.audit_broker_boundary import inspect_current_principal
from aura_core.osworld.audit_broker_protocol import BrokerDenied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Windows daemon access probe")
    parser.add_argument("--role", required=True, choices=("agent", "auditor", "broker"))
    parser.add_argument("--expected-sid", required=True)
    args = parser.parse_args(argv)
    try:
        observation = inspect_current_principal(
            role=args.role, expected_sid=args.expected_sid,
        )
        required = "allowed" if args.role == "broker" else "denied"
        accepted = observation.access == required
        print(json.dumps({
            "status": "OBSERVATION_ONLY" if accepted else "BOUNDARY_BLOCKED",
            "role": observation.role,
            "principal_sid": observation.principal_sid,
            "endpoint": observation.endpoint,
            "access": observation.access,
            "windows_error": observation.windows_error,
            "signed": False,
            "scope": "Does not certify cross-account separation or enable OSWorld",
        }))
        return 0 if accepted else 2
    except (BrokerDenied, OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            "status": "BOUNDARY_BLOCKED",
            "signed": False,
            "error_type": type(exc).__name__,
        }))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
