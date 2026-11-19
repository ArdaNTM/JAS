# Human-released capabilities only

This directory is an immutable source tree, not a hot-reload scratchpad.
Do not move generated Python here at runtime: doing so invalidates the JAS
release lock and may bypass the registry authorization boundary.
Only independently attested, manually reviewed and committed artifacts
belong in this directory; they must be registered as normal pre-approved
MCP providers by the trusted release composition and executed via Gateway.
