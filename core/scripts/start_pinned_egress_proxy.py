"""Operator-controlled pinned CONNECT proxy for disposable AURA VM evaluation.

Example in an *isolated* VM after applying independent deny-by-default firewall:
    $env:AURA_EGRESS_PROXY_TOKEN = "<64 random hexadecimal characters>"
    $env:AURA_EGRESS_PROXY_HOSTS = "example.org"
    $env:AURA_EGRESS_FIREWALL_CONFIRMED = "1"
    uv run --frozen python scripts/start_pinned_egress_proxy.py --port 8769

Never use as a general-purpose system proxy or with a personal browser profile.
The script does not manage or attest OS firewall, DNS routing or VM isolation.
"""
from __future__ import annotations

import argparse
import asyncio
import os

from aura_core.network_egress.policy import EgressPolicy, PinnedConnectProxy


async def run(port: int) -> None:
    if os.getenv("AURA_EGRESS_FIREWALL_CONFIRMED") != "1":
        raise PermissionError("Independent OS/VM firewall proof required before proxy startup")
    hosts = frozenset(
        part.strip() for part in os.getenv("AURA_EGRESS_PROXY_HOSTS", "").split(",")
        if part.strip()
    )
    policy = EgressPolicy(hosts)
    token = os.getenv("AURA_EGRESS_PROXY_TOKEN", "")
    proxy = PinnedConnectProxy(policy=policy, token=token)
    try:
        bound = await proxy.start(port=port)
        print(f"AURA pinned CONNECT proxy ready on 127.0.0.1:{bound}; policy only")
        await proxy.serve_forever()
    finally:
        await proxy.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AURA VM-only authenticated egress proxy")
    parser.add_argument("--port", type=int, default=8769)
    args = parser.parse_args(argv)
    try:
        asyncio.run(run(args.port))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
