# Features #7 and #21 — offline scoped conversation review (partial)

Adds `aura_core.memory.conversation_review.OfflineConversationReview` as
an ephemeral, bounded transcript buffer for **previously authenticated**
conversation events. It supports explicit exact-principal/conversation
readback, deterministic oldest-first eviction and replay-ID rejection.

A `user_requested_review=True` operation can propose memory candidates
only from explicit user-turn `remember:` or `hatırla:` prefixes. Proposals
are always marked `untrusted=True`, `owner_approval_verified=False`,
`persisted=False`, and are never automatically stored, executed or sent
to a model. An upstream authenticated caller must verify speaker identity;
the `speaker="user"` label alone is not a proof of origin. Unsupported
content (empty/oversized/multiline proposal) fails closed. No direct tool,
filesystem, network or provider capability is added.

Limits: ≤128 retained turns, ≤20,000 retained characters, ≤4,096 encoded
bytes per turn, ≤2,048 distinct turn IDs per volatile instance, ≤20 memory
review candidates per request. `clear(confirm=True)` erases *only this
instance's memory*, not persistent chat records, other storage or backups.
It is NOT the constitutional Owner consent or secure erasure receipt.

Feature #7 conversational memory conversion and #21 conversation history
remain **PARTIAL**, not COMPLETED. Production integration requires
principal/speaker authentication, actual Owner-reviewed memory promotion,
persistent encrypted journal, retention/erasure across all replicas,
accessibility UX and independent negative security acceptance.

Tests: `cd core && uv run pytest -q tests/test_offline_conversation_review.py`
followed by all Core Assurance and Final Release Lock gates. No new
dependencies.
