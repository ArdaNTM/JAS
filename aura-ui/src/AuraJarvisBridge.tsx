import { useEffect } from "react";

import { respondAsAssistant } from "./api/client";

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

        const utterance =
          new SpeechSynthesisUtterance(
            response.assistant_reply.trim(),
          );

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