import { useRef } from "react";

type AuraJarvisBridgeProps = {
  command?: string;
  researchOutput?: unknown;
};

type AssistantResponse = {
  assistant_reply?: string;
  reply?: string;
  response?: string;
  message?: string;
};

export default function AuraJarvisBridge({
  command,
  researchOutput,
}: AuraJarvisBridgeProps) {
  const busyRef = useRef(false);

  const speak = (text: string) => {
    if (!text || typeof window === "undefined") {
      return;
    }

    if (!("speechSynthesis" in window)) {
      return;
    }

    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "tr-TR";
    utterance.rate = 1;
    utterance.pitch = 1;

    window.speechSynthesis.speak(utterance);
  };

  const sendCommand = async () => {
    if (!command || busyRef.current) {
      return;
    }

    busyRef.current = true;

    try {
      const response = await fetch("/api/assistant/respond", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: command,
          research_output: researchOutput ?? null,
        }),
      });

      if (!response.ok) {
        throw new Error(
          `Assistant API HTTP ${response.status}`
        );
      }

      const data = (await response.json()) as AssistantResponse;

      const reply =
        data.assistant_reply ??
        data.reply ??
        data.response ??
        data.message ??
        "";

      if (reply.trim()) {
        speak(reply.trim());
      }
    } catch (error) {
      console.error("AURA JARVIS bridge error:", error);
    } finally {
      busyRef.current = false;
    }
  };

  return (
    <button
      type="button"
      onClick={sendCommand}
      disabled={!command || busyRef.current}
      style={{
        display: "none",
      }}
      aria-hidden="true"
    >
      AURA JARVIS
    </button>
  );
}