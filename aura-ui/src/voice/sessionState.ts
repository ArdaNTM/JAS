import type { OperationState } from "../api/contracts";

export type VoiceSessionState =
  | "idle"
  | "listening"
  | "processing"
  | "awaiting_approval"
  | "responding"
  | "speaking"
  | "error";

export type VoiceCaptureState =
  | "unavailable"
  | "idle"
  | "recording"
  | "transcribing"
  | "listening"
  | "error";

export function captureToSessionState(
  state: VoiceCaptureState,
): VoiceSessionState | null {
  switch (state) {
    case "recording":
    case "listening":
      return "listening";
    case "transcribing":
      return "processing";
    case "error":
    case "unavailable":
      return "error";
    case "idle":
      return null;
  }
}

export function operationToSessionState(
  state: string | OperationState,
): VoiceSessionState {
  switch (state.toLowerCase()) {
    case "awaiting_approval":
    case "pending_approval":
    case "awaiting-approval":
      return "awaiting_approval";
    case "succeeded":
    case "responding":
      return "responding";
    case "failed":
    case "cancelled":
    case "timed_out":
    case "error":
      return "error";
    case "queued":
    case "running":
    case "processing":
    case "planning":
    case "executing":
      return "processing";
    default:
      return "idle";
  }
}

export function sessionStateLabel(state: VoiceSessionState): string {
  switch (state) {
    case "idle": return "READY — PRESS ENTER TO EXECUTE";
    case "listening": return "LISTENING — MICROPHONE ACTIVE";
    case "processing": return "PROCESSING — AURA CORE WORKING";
    case "awaiting_approval": return "AWAITING APPROVAL — EXECUTION BLOCKED";
    case "responding": return "RESPONSE — PREPARING ANSWER";
    case "speaking": return "RESPONSE — SPEAKING";
    case "error": return "ERROR — REVIEW DETAILS BEFORE RETRY";
  }
}
