import { useEffect, useRef } from "react";

import { AuraApiError, respondAsAssistant, synthesizeLocalSpeech } from "./api/client";
import { OrderedAudioPlayback } from "./voice/orderedAudioPlayback";

/** Speech text is presentation-only; untrusted research/tool evidence is untouched. */
export function normalizeSpeechText(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/!?\[([^\]]+)\]\(\s*(?:https?:\/\/|www\.)[^)]*\)/gi, "$1")
    .replace(/(?:https?:\/\/|www\.)[^\s<>{}\[\]"']+/gi, " ")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/^\s*(?:[-*+]|\d+[.)])\s+/gm, "")
    .replace(/^\s*>\s*/gm, "")
    .replace(/\*\*([^*]+)\*\*|__([^_]+)__/g, (_match, a: string, b: string) => a || b)
    .replace(/(?<!\w)\*([^*\n]+)\*(?!\w)|(?<!\w)_([^_\n]+)_(?!\w)/g, (_match, a: string, b: string) => a || b)
    .replace(/`([^`]+)`/g, "$1")
    .replace(/<[^>]*>/g, " ")
    .replace(/\[\^?\d+\]|\[kaynak\s*\d+\]/gi, " ")
    .replace(/[*#`~_]+/g, " ")
    .replace(/\s+([,.;:!?])/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

/** Split only on sentence/whitespace boundaries; never silently drop the tail. */
export function speechChunks(raw: string, max = 700): string[] {
  const text = normalizeSpeechText(raw);
  const result: string[] = [];
  let rest = text;
  while (rest.length > max) {
    const sentence = Math.max(rest.lastIndexOf(". ", max), rest.lastIndexOf("! ", max), rest.lastIndexOf("? ", max));
    const boundary = sentence >= Math.floor(max / 3) ? sentence + 1 : rest.lastIndexOf(" ", max);
    const length = boundary > 0 ? boundary : max;
    const chunk = rest.slice(0, length).trim();
    if (chunk) result.push(chunk);
    rest = rest.slice(length).trimStart();
  }
  if (rest.trim()) result.push(rest.trim());
  return result;
}

type AuraJarvisBridgeProps = {
  directive?: string;
  researchOutput?: unknown;
  requestId?: number;
  onStatus?: (
    status: "processing" | "ready" | "speaking" | "error",
    errorMessage?: string,
    degraded?: boolean,
  ) => void;
  speakThroughSession?: (text: string) => Promise<boolean>;
  sessionActive?: boolean;
  enableSpeech?: boolean;
  history?: Array<{ role: "user" | "assistant"; content: string }>;
  onDelta?: (delta: string) => void;
};

export default function AuraJarvisBridge({
  directive,
  researchOutput,
  requestId = 0,
  onStatus,
  speakThroughSession,
  sessionActive = false,
  enableSpeech = false,
  history = [],
  onDelta,
}: AuraJarvisBridgeProps) {
  const latest = useRef({ directive, researchOutput, onStatus, speakThroughSession, sessionActive, enableSpeech, history, onDelta });
  latest.current = { directive, researchOutput, onStatus, speakThroughSession, sessionActive, enableSpeech, history, onDelta };
  useEffect(() => {
    const { directive, researchOutput, onStatus, speakThroughSession, sessionActive, enableSpeech, history, onDelta } = latest.current;
    if (requestId <= 0 || !directive?.trim()) return;

    const abort = new AbortController();
    let cancelled = false;
    const playback = new OrderedAudioPlayback();
    const bargeIn = () => {
      cancelled = true;
      abort.abort();
      playback.cancel();
      onStatus?.("ready");
    };
    window.addEventListener("aura:voice-barge-in", bargeIn);
    const run = async () => {
      onStatus?.("processing");
      let inferred = false;
      try {
        const result = await respondAsAssistant(directive.trim(), researchOutput, history, abort.signal);
        if (cancelled) return;
        if (result.degraded) {
          onStatus?.("error", "LLM OFFLINE / DEGRADED", true);
          return;
        }
        if (!result.assistant_reply?.trim()) throw new Error("Yerel model boş yanıt üretti.");
        inferred = true;
        onDelta?.(result.assistant_reply);
        if (enableSpeech) {
          for (const segment of speechChunks(result.assistant_reply, 420)) {
            if (cancelled) return;
            if (sessionActive && speakThroughSession) {
              if (!await speakThroughSession(segment)) throw new Error("Ses oturumu kapandı.");
            } else {
              const audio = await synthesizeLocalSpeech(segment);
              if (cancelled) return;
              const bytes = Uint8Array.from(atob(audio.audio_base64), ch => ch.charCodeAt(0));
              await playback.enqueue(new Blob([bytes], { type: audio.mime_type }), () => onStatus?.("speaking"));
            }
          }
        }
        if (!cancelled) onStatus?.("ready");
      } catch (error) {
        if (!cancelled) {
          const degraded = !inferred && error instanceof AuraApiError && error.status === 503;
          const message = degraded ? "LLM OFFLINE / DEGRADED" :
            error instanceof Error ? error.message : "Sesli yanıt başarısız oldu.";
          onStatus?.("error", message, degraded);
        }
      } finally {
        await playback.close().catch(() => undefined);
      }
    };
    void run();
    return () => {
      window.removeEventListener("aura:voice-barge-in", bargeIn);
      cancelled = true;
      abort.abort();
      playback.cancel();
      void playback.close().catch(() => undefined);
    };
  }, [requestId]);

  return null;
}
