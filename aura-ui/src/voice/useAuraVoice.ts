import { useCallback, useMemo, useRef, useState } from "react";

type RecognitionResultEvent = Event & {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
};

type Recognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onresult: ((event: RecognitionResultEvent) => void) | null;
};

type RecognitionConstructor = new () => Recognition;

type VoiceState =
  | "unavailable"
  | "idle"
  | "listening"
  | "wake_detected"
  | "error";

function getRecognitionConstructor(): RecognitionConstructor | null {
  const candidate = window as typeof window & {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  };

  return candidate.SpeechRecognition ?? candidate.webkitSpeechRecognition ?? null;
}

export function useAuraVoice(onDirective: (value: string) => void) {
  const recognitionRef = useRef<Recognition | null>(null);
  const [state, setState] = useState<VoiceState>(() =>
    getRecognitionConstructor() ? "idle" : "unavailable",
  );
  const [message, setMessage] = useState(
    getRecognitionConstructor()
      ? "Push to talk is ready. Wake-word detection is active only while listening."
      : "This Chromium runtime does not provide the Web Speech API.",
  );

  const available = useMemo(
    () => getRecognitionConstructor() !== null,
    [],
  );

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
  }, []);

  const start = useCallback(() => {
    const RecognitionApi = getRecognitionConstructor();

    if (!RecognitionApi) {
      setState("unavailable");
      return;
    }

    const recognition = new RecognitionApi();
    recognitionRef.current = recognition;
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "tr-TR";

    recognition.onstart = () => {
      setState("listening");
      setMessage('Listening for a directive beginning with "AURA".');
    };

    recognition.onerror = (event) => {
      setState("error");
      setMessage(`Speech input error: ${event.error}`);
    };

    recognition.onend = () => {
      recognitionRef.current = null;
      setState((current) => (current === "error" ? current : "idle"));
    };

    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0]?.transcript ?? "")
        .join(" ")
        .trim();

      const match = transcript.match(/^aura\b[\s,.:;!-]*(.*)$/i);

      if (!match) {
        setState("idle");
        setMessage('Wake word not heard. Start the sentence with "AURA".');
        return;
      }

      const directive = match[1].trim();
      setState("wake_detected");
      setMessage(
        directive
          ? "Wake word recognized. Directive was placed in the command deck."
          : "Wake word recognized. Add your directive in the command deck.",
      );

      if (directive) {
        onDirective(directive);
      }
    };

    recognition.start();
  }, [onDirective]);

  return {
    available,
    message,
    start,
    state,
    stop,
  };
}