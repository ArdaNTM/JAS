import { useEffect } from "react";

import { respondAsAssistant } from "./api/client";

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
    status: "ready" | "speaking" | "offline",
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
      onStatus?.("ready");

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

        if (
          typeof window === "undefined" ||
          !("speechSynthesis" in window)
        ) {
          onStatus?.("offline");
          return;
        }

        window.speechSynthesis.cancel();

        const speechText = normalizeSpeechText(
          response.assistant_reply,
        );

        if (!speechText) {
          onStatus?.("ready");
          return;
        }

        const utterance =
          new SpeechSynthesisUtterance(speechText);

        utterance.lang = "tr-TR";
        utterance.rate = 1;
        utterance.pitch = 1;

        utterance.onstart = () => {
          if (!cancelled) {
            onStatus?.("speaking");
          }
        };

        utterance.onend = () => {
          if (!cancelled) {
            onStatus?.("ready");
          }
        };

        utterance.onerror = () => {
          if (!cancelled) {
            onStatus?.("offline");
          }
        };

        window.speechSynthesis.speak(
          utterance,
        );
      } catch (error) {
        if (!cancelled) {
          console.error(
            "AURA JARVIS bridge error:",
            error,
          );
          onStatus?.("offline");
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
