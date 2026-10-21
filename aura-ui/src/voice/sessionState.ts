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
    case "idle": return "HAZIR — ÇALIŞTIRMAK İÇİN ENTER'A BASIN";
    case "listening": return "DİNLİYOR — MİKROFON ETKİN";
    case "processing": return "İŞLENİYOR — AURA CORE ÇALIŞIYOR";
    case "awaiting_approval": return "ONAY BEKLENİYOR — YÜRÜTME ENGELLENDİ";
    case "responding": return "YANIT HAZIRLANIYOR";
    case "speaking": return "YANIT SESLENDİRİLİYOR";
    case "error": return "HATA — YENİDEN DENEMEDEN ÖNCE AYRINTILARI İNCELEYİN";
  }
}
