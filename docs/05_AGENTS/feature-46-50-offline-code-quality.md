# Features #46/#50 — offline Python code review and contract test generation

`aura_core.application.offline_code_quality` supports two real, bounded,
read-only developer workflows:

- `review_static_python(source)`: AST-only direct red-flag heuristics
  (mutable literal defaults, straight-line unreachable statements,
  bare except handlers, direct calls to eval/exec). Returns category
  and line only, never raw secrets/source or false bug-verification claims.
- `generate_pytest_contracts(module_name, cases)`: produces actual
  `pytest` code for **explicitly supplied** input/output contracts.
  CI verifies that generated test functions execute against known
  harmless standard-library arithmetic; no expected result is invented.

The generation function NEVER imports the user module or runs tests.
Generated code is executable **when intentionally run later**; it must
be reviewed and executed only in an authorized isolated sandbox behind
JAS PermissionEngine/MCP Gateway and Owner policies. The CI controlled
fixture uses `exec` solely to verify deterministic generator output
against known harmless functions; JAS runtime does not execute generated
or arbitrary untrusted code. No filesystem edits, terminal commands,
GitHub operations or new MCP capabilities are introduced.

Limits: ≤128 KiB Python source, ≤25k AST nodes, ≤128 candidate findings,
≤40 explicit contract cases, ≤400 bounded JSON values, ≤40 KiB generated
test code. The AST heuristic is not a sound or complete defect detector.
Contracts confirm only the supplied expectations, not comprehensive
test coverage or security certification. User-supplied module imports
could have side effects when tests are *later* run; sandbox approval is
mandatory.

Features #46 (bug finding) and #50 (automatic test generation) remain
TESTING/PARTIAL pending actual repo-scoped secure analysis, sandbox CI,
quality metrics, independent review and Owner acceptance.

Run `cd core && uv run pytest -q tests/test_offline_code_quality.py`,
full Core Assurance, Remote Persistence and Final Release Lock.
