import { useEffect } from "react";

import { AuraApiError, respondAsAssistant, synthesizeLocalSpeech } from "./api/client";

function normalizeSpeechText(text: string): string {
  return text
    .replace(
      /(?<!!)\[([^\]]+)\]\(\s*(?:https?:\/\/|www\.)[^)]*\)/gi,
      "$1",
    )
    .replace(
      /(?:https?:\/\/|www\.)[^\s<>{}\[\]"']+/gi,
      " ",
    )
    .replace(
      /\b(?:[a-z0-9-]+\.)+(?:com|org|net|io|ai|dev|edu|gov|tr|de|uk)(?:\/[^\s<>{}\[\]"']*)?/gi,
      " ",
    )
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/<[^>]+>/g, " ")
    .replace(/^\s{0,3}#{1,6}\s+/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/\s+([,.;:!?])/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

type AuraJarvisBridgeProps = {
  directive?: string;
  researchOutput?: unknown;
  requestId?: number;
  onStatus?: (
    status: "processing" | "ready" | "speaking" | "error",
    errorMessage?: string,
  ) => void;
};

export default function AuraJarvisBridge({
  directive,
  researchOutput,
  requestId = 0,
  onStatus,
}: AuraJarvisBridgeProps) {
  useEffect(() => {
    if (
      requestId <= 0 ||
      !directive?.trim()
    ) {
      return;
    }

    let cancelled = false;

    const run = async () => {
      onStatus?.("processing");

      try {
        const response =
          await respondAsAssistant(
            directive.trim(),
            researchOutput,
          );

        if (
          cancelled ||
          !response.assistant_reply?.trim()
        ) {
          return;
        }

        const speechText = normalizeSpeechText(
          response.assistant_reply,
        );

        if (!speechText) {
          onStatus?.("ready");
          return;
        }

        const audio = await synthesizeLocalSpeech(speechText);
        if (cancelled) return;
        const player = new Audio(`data:${audio.mime_type};base64,${audio.audio_base64}`);
        player.onplay = () => onStatus?.("speaking");
        player.onended = () => onStatus?.("ready");
        player.onerror = () => onStatus?.("error");
        await player.play();
      } catch (error) {
        if (!cancelled) {
          console.error(
            "AURA JARVIS köprü hatası:",
            error,
          );
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
    };
  }, [
    directive,
    researchOutput,
    requestId,
    onStatus,
  ]);

  return null;
}
