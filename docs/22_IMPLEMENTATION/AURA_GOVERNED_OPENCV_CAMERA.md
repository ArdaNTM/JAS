# Actual local OpenCV camera capture behind Core MCP Gateway — feature #83 (partial)

**Stacked on Draft PR #137** for the separately registered local Ollama image-understanding tool. This PR implements real OpenCV `cv2.VideoCapture` one-frame capture from a **fixed, trusted local device integer**, with two independent Core authorization boundaries and an independent short-lived trusted application-side Owner consent lease. It does **not** implement continuous background filming, remote camera URLs, microphone, automated recognition of persons, stream storage, or any mouse/robot actuation.

## Owner/permission enforcement

1. Trusted Core application composition creates `OwnerCameraConsentLease(authenticated_principal_id=...)`. Only trusted Owner-identity UI/transport code is allowed to call `arm(session_id=..., owner_confirmed=True, ttl_seconds=...)` after authenticating the real Owner. The lease is **not an HTTP endpoint** and is revoked with `revoke()`. `owner_confirmed=True` is only an input contract, not proof that the real Owner approved it; external deployment must establish that fact.
2. The trusted composition explicitly registers `LocalOpenCVCameraMCP` using `register_local_opencv_camera(services, providers, capabilities, consent_lease, trusted_device_index=0)`. It installs **no policy**. The `vision.camera.frame.read` operation and capability have HIGH risk, tool `capture_local_camera_frame` and scope `vision/camera/0/frame`. External callers cannot choose camera indexes or device URLs.
3. The public `GovernedLocalCameraReader` requires the same already-authenticated principal, existing MCP Gateway, registered camera provider, **exact same consent lease**, fixed device index and `GovernedImageUnderstanding` bound to that Gateway/principal. Only a current leased session can even attempt the first Gateway invocation.
4. The existing PermissionEngine must explicitly allow the HIGH-risk camera scope, then MCP Gateway dispatches the provider. **The provider itself** checks `current_dispatch()` capability/tool/risk, the principal identity and the exact consented session ID in tool arguments **before opening `cv2.VideoCapture`**. Even a direct Gateway invocation with ALLOW policy but no active lease fails closed before touching hardware. This is critical: facade-only consent would be bypassable.
5. A real on-demand camera read uses the trusted configured integer device, requests 640x480 resolution, rejects oversized geometry and oversized JPEG output (2 MiB maximum), encodes a real `.jpg`, releases the device handle after each read, and validates SHA256 before forwarding locally to the registered image MCP provider. The lease is rechecked after camera access and after the **separately permission-checked** Ollama frame description.
6. Returns immutable `CameraFrameEvidence` with bounded, **UNTRUSTED** model text and image SHA, no raw pixels or automatic computer/robot actuation. No camera image or model content is stored or emitted on EventBus.

## Tests

`cd core && uv run pytest -q tests/test_opencv_camera_mcp.py`
`cd core && uv run pytest -q`
`cd core && uv run python scripts/verify_final_lock.py`

CI instantiates real JAS Core Service/Capability/Provider registries, `PermissionEngine` and `MCPGateway`, real local Ollama HTTP serialization with `httpx.MockTransport`, and controlled OpenCV device objects in place of physically opening a test runner's camera. Positive actual capture API path, separate camera and vision ALLOW/DENY, no lease, direct Gateway bypass without lease, direct-provider bypass, wrong principal, revoked/expired lease, unavailable device, malformed JPEG, wrong session and device, handle release and no auto device opening at registration are checked.

## Incomplete real device and security acceptance

- `cv2` is **optional** and must be installed locally with a trusted native driver; the code imports it only at capture time. CI tests the actual adapter logic against a controlled cv2 object; it does not prove a real camera device was opened.
- `asyncio.to_thread` has a **soft timeout only**; a stuck OS camera driver cannot be forcibly killed by cancelling that thread. Production needs a dedicated permission-bounded out-of-process helper with a hard time/memory budget, driver provenance, device privacy controls and reliable Windows NTFS/Owner authorization. No continuous streaming or hotplug recovery is included.
- Owner lease creation must be bound to authenticated real UI/broker action; a caller-provided `owner_confirmed=True` argument alone is **never** accepted as independent Owner verification.
- Real Windows camera hardware, frame privacy, local model weights, viewer UI, live video, resource CPU limits and end-to-end quality are **NOT_VERIFIED**. No automatic actions and no `COMPLETED` claim.
- #83 stays **TESTING / PARTIAL_VERIFIED** only after exact-head CI and human/physical acceptance. No auto-merge; #137 and F2.7 Owner boundaries remain prerequisites.
