"""Optional local face comparison, never an identity or cryptographic authority.

Only an explicit approved call captures a camera frame. The enrolled reference and
models are provisioned locally by the operator. Images/features are not persisted
or returned by the verifier. A match can clear this module's own restriction only.
"""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Callable

from aura_core.mcp.dispatch_context import current_dispatch
from aura_core.mcp.mcp_provider import MCPTool

FACE_CAP = "jarvis.face.verify"
FACE_TOOL = "verify_local_face"
FACE_SCOPE = "jarvis/face/local-camera"
FACE_PROVIDER = "aura.local-face-verification"


class OpenCVFaceVerifier:
    def __init__(self, *, reference: str, detector: str, recognizer: str, camera_index: int = 0):
        self.reference = reference
        self.detector = detector
        self.recognizer = recognizer
        if type(camera_index) is not int or not 0 <= camera_index <= 8:
            raise ValueError("Invalid local camera index")
        self.camera_index = camera_index

    @staticmethod
    def _local_file(value: str) -> str:
        path = Path(value).expanduser()
        if not path.is_absolute() or not path.is_file() or path.is_symlink():
            raise ValueError("Explicit local model/reference file required")
        return str(path.resolve(strict=True))

    def __call__(self) -> bool | None:
        try:
            import cv2
            reference = cv2.imread(self._local_file(self.reference))
            detector = cv2.FaceDetectorYN.create(self._local_file(self.detector), "", (320, 320), 0.9)
            recognizer = cv2.FaceRecognizerSF.create(self._local_file(self.recognizer), "")
            if reference is None:
                return None

            def feature(image):
                detector.setInputSize((image.shape[1], image.shape[0]))
                _, faces = detector.detect(image)
                if faces is None or len(faces) != 1:
                    return None
                return recognizer.feature(recognizer.alignCrop(image, faces[0])).copy()

            enrolled = feature(reference)
            if enrolled is None:
                return None
            capture = cv2.VideoCapture(self.camera_index)
            try:
                if not capture.isOpened():
                    return None
                ok, frame = capture.read()
                if not ok or frame is None:
                    return None
                observed = feature(frame)
                # No face / several faces is not positive verification.
                if observed is None:
                    return False
                return bool(recognizer.match(enrolled, observed, cv2.FaceRecognizerSF_FR_COSINE) >= 0.5)
            finally:
                capture.release()
        except Exception:
            # Optional dependency, unavailable camera, invalid provisioned model:
            # retain the existing Owner policy and do not claim a match.
            return None


class FaceVerificationGate:
    def __init__(self, verifier: Callable[[], bool | None]):
        self._verifier = verifier
        self._lock = threading.Lock()
        self._capture_lock = threading.Lock()
        self._restricted = False

    def restricted(self, principal: str) -> bool:
        with self._lock:
            return principal == "local_owner" and self._restricted

    def verify(self, principal: str) -> str:
        if principal != "local_owner":
            raise PermissionError("Local Owner session required")
        with self._capture_lock:
            outcome = self._verifier()
            with self._lock:
                if outcome is True:
                    self._restricted = False
                    return "matched"
                if outcome is False:
                    self._restricted = True
                    return "restricted"
                return "unavailable"

    async def list_tools(self):
        return (MCPTool(FACE_TOOL, "Optional local camera comparison; no Owner authority is granted",
                        {"type": "object", "properties": {}, "additionalProperties": False}),)

    async def call_tool(self, name, arguments=None):
        grant = current_dispatch()
        if (grant is None or grant.principal_id != "local_owner" or grant.capability_id != FACE_CAP
                or grant.tool_name != FACE_TOOL or name != FACE_TOOL or grant.risk_level != "high"
                or not grant.approval_consumed):
            raise PermissionError("Consumed local camera Gateway approval required")
        if arguments not in ({}, None):
            raise ValueError("No caller-supplied camera inputs")
        result = await asyncio.to_thread(self.verify, grant.principal_id)
        return {"status": result, "restricted": self.restricted(grant.principal_id),
                "authority_granted": False, "owner_signature_verified": False}
