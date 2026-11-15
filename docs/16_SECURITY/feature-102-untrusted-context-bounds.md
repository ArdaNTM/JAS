# Features #6 and #102 — bounded untrusted context synthesis

This hardening reuses the existing ContextSynthesizer. User messages,
research evidence and remembered passages remain in the user content;
only fixed style/policy text enters its system prompt. The synthesis path
no longer invokes arbitrary custom __str__ methods on untrusted memory
objects, processes at most 128 yielded memory entries, and rejects
type-confused budgets, empty/oversized messages and oversized research
text before constructing context.

This is an input safety boundary, NOT a claim to detect all adversarial
instructions or guarantee model behavior under prompt injection. The model
must still treat source text as data, and all tool execution retains
PermissionEngine and MCP Gateway authorization. This PR adds no new tool,
memory promotion, retrieval, privilege, policy or external API.

Tests exercise malicious object coercion, endless iterables, system/user
context separation, size budgets, valid style behavior, and invalid types.
Use cd core && uv run pytest -q tests/test_untrusted_context_bounds.py
plus full Core Assurance and deterministic Final Release Lock.

Full feature #6 context awareness and #102 prompt injection resilience still
need end-to-end provider, model, tool-dispatch and adversarial testing.
