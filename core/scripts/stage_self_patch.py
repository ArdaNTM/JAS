"""Independent operator handoff: stage one reviewed patch in a disposable clone.

This script is never called by AURA Core, its model, or an MCP provider. It
does not create an approval receipt, execute candidate code, run tests, commit,
push, merge, regenerate release identities or deploy anything.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess

from aura_core.evolution.self_patch_review import (
    PatchRejected, TARGETS, export_review_patch,
)


def stage_patch(checkout: Path, draft: Path, *, expected_base: str,
                expected_id: str, live_checkout: Path) -> str:
    """Stage the exact operator-selected patch; refuse main and dirty clones."""
    checkout = checkout.resolve(strict=True)
    live = live_checkout.resolve(strict=True)
    if checkout.is_relative_to(live) or live.is_relative_to(checkout):
        raise PatchRejected("Use a disposable clone separate from the live release")
    gitdir = checkout / ".git"
    if (not gitdir.is_dir() or gitdir.is_symlink()
            or (hasattr(gitdir, "is_junction") and gitdir.is_junction())):
        raise PatchRejected("A standalone disposable Git clone is required")
    if not re.fullmatch(r"[0-9a-f]{40}", expected_base):
        raise PatchRejected("Select the full reviewed base commit SHA")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_id):
        raise PatchRejected("Select the full reviewed draft digest")

    # Do not inherit alternative repository, index, config or worktree settings.
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT="0")

    def git(*args: str, data: bytes | None = None) -> bytes:
        result = subprocess.run(
            ["git", "-C", str(checkout), "-c", "core.fsmonitor=false",
             "-c", "core.hooksPath=" + os.devnull, *args],
            input=data, capture_output=True, env=env, timeout=30, check=False,
        )
        if result.returncode != 0:
            # Do not print untrusted repository/configuration output.
            raise PatchRejected("Git rejected the requested isolated staging operation")
        return result.stdout

    if Path(os.fsdecode(git("rev-parse", "--show-toplevel").strip())).resolve() != checkout:
        raise PatchRejected("Checkout is not its own Git root")
    origin = git("config", "--local", "--get", "remote.origin.url").decode().strip()
    if origin not in {
        "https://github.com/ArdaNTM/JAS.git", "https://github.com/ArdaNTM/JAS",
        "git@github.com:ArdaNTM/JAS.git",
    }:
        raise PatchRejected("Expected the JAS repository origin")
    branch = git("symbolic-ref", "--short", "HEAD").decode().strip()
    if not re.fullmatch(r"self-patch/[a-zA-Z0-9][a-zA-Z0-9._-]{0,80}", branch):
        raise PatchRejected("Select an isolated self-patch/* branch, never main")
    if git("rev-parse", "HEAD").decode().strip() != expected_base:
        raise PatchRejected("Isolated branch base changed")
    if git("status", "--porcelain=v1", "--untracked-files=all"):
        raise PatchRejected("Isolated checkout must be clean")
    patch = export_review_patch(checkout, draft, expected_id=expected_id).encode("utf-8")
    # The exporter checks exact path/function scope, release/source identities,
    # candidate digest and the operator-selected review digest. Extract the
    # one target from its trusted diff header rather than re-reading the draft.
    header = patch.splitlines()[0].decode("utf-8")
    target = header.removeprefix("--- a/")
    if target not in TARGETS or header != "--- a/" + target:
        raise PatchRejected("Unexpected patch target")
    git("apply", "--check", "--index", "--whitespace=error-all", "-", data=patch)
    git("apply", "--index", "--whitespace=error-all", "-", data=patch)
    if git("diff", "--cached", "--name-only", "-z") != target.encode() + b"\0":
        raise PatchRejected("Unexpected staged file set; inspect the disposable clone")
    if git("diff", "--name-only", "-z"):
        raise PatchRejected("Unexpected unstaged changes; inspect the disposable clone")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--expected-base", required=True)
    parser.add_argument("--approve-draft-id", required=True,
                        help="Full digest explicitly selected after human review; not a signed receipt")
    args = parser.parse_args()
    target = stage_patch(
        args.checkout, args.draft, expected_base=args.expected_base,
        expected_id=args.approve_draft_id, live_checkout=Path(__file__).resolve().parents[2],
    )
    print("Staged for independent review only:", target)
    print("No candidate executed. Tests, release lock, PR and Owner promotion still required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
