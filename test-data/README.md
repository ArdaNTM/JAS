# Local filesystem MCP test-data root

Place non-sensitive UTF-8 text fixtures here. The `aura-local-filesystem` MCP server can only read regular files beneath this directory, using relative forward-slash paths. It has no write, delete, or directory-listing tool and rejects traversal and symlinks. Individual reads are limited to 1 MiB.

Do not put secrets, credentials, or private production data in this directory. Local test files may remain untracked if you prefer.
