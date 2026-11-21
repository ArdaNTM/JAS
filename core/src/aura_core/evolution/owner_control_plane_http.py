"""Loopback-only, unprivileged discovery review front end for AURA desktop.

This process serves untrusted catalog evidence without opening the trusted
owner signing store. The protected, passkey-enabled approval service remains
an explicit separately-provisioned process under a dedicated OS identity.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from aura_core.enterprise.approval_store import SQLiteApprovalStore
from aura_core.evolution.external_staging import EvolutionWorkspace
from aura_core.evolution.owner_control_plane import create_owner_control_plane


def build_local_review_app(evolution_root: Path | str):
    workspace = EvolutionWorkspace(evolution_root)
    # No credential, no approval signing key and no writable owner database
    # is mounted into the ordinary desktop session.
    store = SQLiteApprovalStore(":memory:")
    app = create_owner_control_plane(
        approvals=store, decider=None, read_only=True,
        catalog_db=workspace.root / "catalog" / "proposals.sqlite3",
    )

    @app.on_event("shutdown")
    def close_store() -> None:
        store.close()

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="AURA local read-only owner discovery review")
    parser.add_argument(
        "--evolution-root",
        default=os.environ.get("AURA_EVOLUTION_ROOT"),
        help="Absolute external Evolution workspace (not the git checkout)",
    )
    args = parser.parse_args()
    if not args.evolution_root:
        parser.error("AURA_EVOLUTION_ROOT or --evolution-root is required")
    app = build_local_review_app(Path(args.evolution_root))
    uvicorn.run(
        app, host="127.0.0.1", port=8766,
        access_log=False, reload=False, workers=1,
    )


if __name__ == "__main__":
    main()
