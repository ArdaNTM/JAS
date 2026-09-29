# AURA reproducibility

Use Python 3.13.14 and install the dependency set recorded in `uv.lock`. Set
`AURA_POSTGRES_PASSWORD` before starting `deployment/docker-compose.yml`.
Run `python -m pytest tests -q` from the project virtual environment. The
release manifest is canonical JSON; its SHA-256 digest is the release identity.

External services are deliberately not bundled: PostgreSQL and Qdrant must be
started from the compose file, while browser, voice, vision and model providers
must be registered as providers with explicit capabilities and permissions.
