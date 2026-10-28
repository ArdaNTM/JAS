# S3-compatible object storage adapter status

`S3PresignedObjectStorage` implements put/get/delete over HTTPS pre-signed
object URLs. A trusted `PresignedURLProvider` is responsible for obtaining
short-lived, object-scoped URLs from the deployment's signer/secret manager.
This keeps long-lived access keys out of the application adapter.

Security properties:
- HTTPS is mandatory; redirects are disabled to avoid leaking signed URLs.
- Object keys must be relative and cannot contain dot segments or backslashes.
- Non-success HTTP responses fail the operation; there is no local-file fallback.
- The adapter does not write credentials or object contents to local disk.

Current limitations:
- A deployment-specific signer/provider still needs to be implemented and wired.
- Existing workflow, approval, episodic-memory and artifact call sites are not
  all migrated to these contracts yet.
- The remote-mode startup gate must remain closed until every durable path is
  migrated, required services are health-checked, and end-to-end tests prove
  that remote mode creates no durable local files.
