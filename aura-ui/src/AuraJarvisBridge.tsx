import { useEffect } from "react";

import { AuraApiError, streamAssistantResponse, synthesizeLocalSpeech } from "./api/client";

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
  ) => void;
  speakThroughSession?: (text: string) => Promise<boolean>;
  sessionActive?: boolean;
};

export default function AuraJarvisBridge({
  directive,
  researchOutput,
  requestId = 0,
  onStatus,
  speakThroughSession,
  sessionActive = false,
}: AuraJarvisBridgeProps) {
  useEffect(() => {
    if (requestId <= 0 || !directive?.trim()) return;

    const abort = new AbortController();
    let cancelled = false;
    let player: HTMLAudioElement | null = null;
    let spoken = "";
    let pending = "";
    let playlist = Promise.resolve();
    let everQueued = false;

    const playChunk = async (speech: string): Promise<void> => {
      if (cancelled || !speech) return;
      const audio = await synthesizeLocalSpeech(speech);
      if (cancelled) return;
      const element = new Audio(`data:${audio.mime_type};base64,${audio.audio_base64}`);
      player = element;
      await new Promise<void>((resolve, reject) => {
        element.onended = () => resolve();
        element.onerror = () => reject(new Error("TTS ses verisi oynatılamadı"));
        element.play().then(() => { if (!cancelled) onStatus?.("speaking"); }).catch(reject);
      });
      if (player === element) player = null;
    };

    const queue = (raw: string): void => {
      for (const segment of speechChunks(raw, 420)) {
        everQueued = true;
        playlist = playlist.then(async () => {
          if (sessionActive && speakThroughSession) {
            await speakThroughSession(segment);
          } else {
            await playChunk(segment);
          }
        });
        // The final await handles failures. No silent detached promises.
      }
    };

    const run = async () => {
      onStatus?.("processing");
      try {
        // Run a genuine Ollama NDJSON stream. In non-full-duplex mode
        // begin sentence playback while remaining tokens are generated.
        await streamAssistantResponse(directive.trim(), researchOutput, (delta) => {
          if (cancelled) return;
          spoken += delta;
          pending += delta;
          if (pending.length >= 80) {
              const cut = Math.max(pending.lastIndexOf(". "), pending.lastIndexOf("! "),
                pending.lastIndexOf("? "), pending.lastIndexOf("\n"));
              if (cut > 0) {
                const complete = pending.slice(0, cut + 1);
                pending = pending.slice(cut + 1);
                queue(complete);
              }
          }
        }, abort.signal);

        if (cancelled) return;
        if (pending.trim()) queue(pending);
        if (!everQueued) {
          onStatus?.("ready");
          return;
        }
        await playlist;
        if (!cancelled) onStatus?.("ready");
      } catch (error) {
        if (!cancelled) {
          console.error("AURA JARVIS köprü hatası:", error);
          const message = error instanceof AuraApiError
            ? `${error.message}${error.requestId ? ` (istek kimliği: ${error.requestId})` : ""}`
            : error instanceof Error ? error.message : "Sesli yanıt başarısız oldu.";
          onStatus?.("error", message);
        }
      }
    };
    void run();
    return () => {
      cancelled = true;
      abort.abort();
      player?.pause();
      if (player) { player.src = ""; player = null; }
    };
  }, [directive, researchOutput, requestId, onStatus, speakThroughSession, sessionActive]);

  return null;
}
