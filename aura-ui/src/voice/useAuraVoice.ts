import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

type RecognitionResultEvent =
  Event & {
    results: ArrayLike<
      ArrayLike<{
        transcript: string;
      }>
    >;
  };

type Recognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  onstart:
    | (() => void)
    | null;
  onend:
    | (() => void)
    | null;
  onerror:
    | ((event: { error: string }) => void)
    | null;
  onresult:
    | ((event: RecognitionResultEvent) => void)
    | null;
};

type RecognitionConstructor =
  new () => Recognition;

type VoiceState =
  | "unavailable"
  | "idle"
  | "listening"
  | "wake_detected"
  | "error";

function getRecognitionConstructor():
  RecognitionConstructor | null {
  const candidate =
    window as typeof window & {
      SpeechRecognition?:
        RecognitionConstructor;

      webkitSpeechRecognition?:
        RecognitionConstructor;
    };

  return (
    candidate.SpeechRecognition ??
    candidate.webkitSpeechRecognition ??
    null
  );
}

export function useAuraVoice(
  onDirective: (
    value: string,
  ) => void,
) {
  const recognitionRef =
    useRef<Recognition | null>(
      null,
    );

  const [
    state,
    setState,
  ] = useState<VoiceState>(() =>
    getRecognitionConstructor()
      ? "idle"
      : "unavailable",
  );

  const [
    message,
    setMessage,
  ] = useState(
    getRecognitionConstructor()
      ? "VOICE LINK READY"
      : "VOICE LINK UNAVAILABLE",
  );

  const [
    amplitude,
    setAmplitude,
  ] = useState(0);

  const available = useMemo(
    () =>
      getRecognitionConstructor() !==
      null,
    [],
  );

  useEffect(() => {
    if (state !== "listening") {
      setAmplitude(0);
      return;
    }

    let frame = 0;
    let phase = 0;

    const animate = () => {
      phase += 0.13;

      setAmplitude(
        0.45 +
          Math.abs(
            Math.sin(phase),
          ) *
            0.55,
      );

      frame =
        requestAnimationFrame(
          animate,
        );
    };

    frame =
      requestAnimationFrame(
        animate,
      );

    return () =>
      cancelAnimationFrame(
        frame,
      );
  }, [state]);

  const stop = useCallback(
    () => {
      recognitionRef.current?.stop();
    },
    [],
  );

  const start = useCallback(
    () => {
      const RecognitionApi =
        getRecognitionConstructor();

      if (!RecognitionApi) {
        setState(
          "unavailable",
        );
        return;
      }

      const recognition =
        new RecognitionApi();

      recognitionRef.current =
        recognition;

      recognition.continuous =
        false;

      recognition.interimResults =
        false;

      recognition.lang =
        "tr-TR";

      recognition.onstart = () => {
        setState(
          "listening",
        );

        setMessage(
          "LISTENING",
        );
      };

      recognition.onerror =
        (event) => {
          setState(
            "error",
          );

          setMessage(
            `VOICE ERROR: ${event.error}`,
          );
        };

      recognition.onend = () => {
        recognitionRef.current =
          null;

        setState(
          current =>
            current === "error"
              ? current
              : "idle",
        );
      };

      recognition.onresult =
        (event) => {
          const transcript =
            Array.from(
              event.results,
            )
              .map(
                result =>
                  result[0]
                    ?.transcript ??
                  "",
              )
              .join(" ")
              .trim();

          const match =
            transcript.match(
              /^aura\b[\s,.:;!-]*(.*)$/i,
            );

          if (!match) {
            setState("idle");

            setMessage(
              "WAKE WORD NOT DETECTED",
            );

            return;
          }

          const directive =
            match[1].trim();

          setState(
            "wake_detected",
          );

          setMessage(
            directive
              ? "WAKE DETECTED"
              : "AURA ONLINE",
          );

          if (directive) {
            onDirective(
              directive,
            );
          }
        };

      recognition.start();
    },
    [onDirective],
  );

  return {
    available,
    amplitude,
    message,
    start,
    state,
    stop,
  };
}
