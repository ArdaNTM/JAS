import { useCallback, useEffect, useRef, useState } from "react";
import { transcribeLocalAudio } from "../api/client";

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
type VoiceState = "unavailable" | "idle" | "recording" | "transcribing" | "listening" | "error";

function getRecognitionConstructor(): RecognitionConstructor | null {
  const candidate = window as typeof window & {
    SpeechRecognition?: RecognitionConstructor;
    webkitSpeechRecognition?: RecognitionConstructor;
  };
  return candidate.SpeechRecognition ?? candidate.webkitSpeechRecognition ?? null;
}

function normalizeDirective(transcript: string): string {
  const trimmed = transcript.trim();
  // Preserve wake-word compatibility, while ENTER remains explicit execution confirmation.
  return trimmed.replace(/^aura\b[\s,.:;!-]*/i, "").trim() || trimmed;
}

export function useAuraVoice(onDirective: (value: string) => void) {
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recognitionRef = useRef<Recognition | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const [state, setState] = useState<VoiceState>(() =>
    typeof navigator !== "undefined" && navigator.mediaDevices?.getUserMedia
      ? "idle"
      : getRecognitionConstructor() ? "idle" : "unavailable",
  );
  const [message, setMessage] = useState("LOCAL STT READY");
  const [amplitude, setAmplitude] = useState(0);

  const startBrowserFallback = useCallback(() => {
    const RecognitionApi = getRecognitionConstructor();
    if (!RecognitionApi) {
      setState("error");
      setMessage("STT UNAVAILABLE — CHECK MICROPHONE PERMISSIONS");
      return;
    }
    const recognition = new RecognitionApi();
    recognitionRef.current = recognition;
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "tr-TR";
    recognition.onstart = () => {
      setState("listening");
      setMessage("BROWSER STT FALLBACK — LISTENING");
    };
    recognition.onerror = (event) => {
      setState("error");
      setMessage(`VOICE ERROR: ${event.error}`);
    };
    recognition.onend = () => {
      recognitionRef.current = null;
      setState((current) => current === "error" ? current : "idle");
    };
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0]?.transcript ?? "")
        .join(" ")
        .trim();
      if (transcript) {
        onDirective(normalizeDirective(transcript));
        setMessage("TRANSCRIPT READY — PRESS ENTER TO EXECUTE");
      } else {
        setMessage("NO SPEECH DETECTED");
      }
    };
    recognition.start();
  }, [onDirective]);

  const stop = useCallback(() => {
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
      return;
    }
    recognitionRef.current?.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  const start = useCallback(() => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia ||
        typeof MediaRecorder === "undefined") {
      startBrowserFallback();
      return;
    }

    void navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
      streamRef.current = stream;
      chunksRef.current = [];
      const preferredType = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg"]
        .find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = preferredType
        ? new MediaRecorder(stream, { mimeType: preferredType })
        : new MediaRecorder(stream);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstart = () => {
        setState("recording");
        setMessage("RECORDING LOCALLY — PRESS STOP WHEN FINISHED");
      };
      recorder.onerror = () => {
        setState("error");
        setMessage("MICROPHONE RECORDING FAILED");
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        recorderRef.current = null;
        if (!blob.size) {
          setState("error");
          setMessage("NO AUDIO CAPTURED");
          return;
        }
        setState("transcribing");
        setMessage("LOCAL FASTER-WHISPER TRANSCRIBING…");
        void transcribeLocalAudio(blob).then((result) => {
          if (!result.text.trim()) {
            setState("idle");
            setMessage("NO SPEECH DETECTED");
            return;
          }
          onDirective(normalizeDirective(result.text));
          setState("idle");
          setMessage(`LOCAL STT READY (${result.language}) — PRESS ENTER TO EXECUTE`);
        }).catch((cause: unknown) => {
          // Do not silently start a second capture session after STOP. That made
          // the first STOP appear to be ignored when local STT was unavailable.
          setState("error");
          setMessage(
            cause instanceof Error
              ? `LOCAL STT FAILED: ${cause.message} — PRESS VOICE TO RETRY`
              : "LOCAL STT UNAVAILABLE — PRESS VOICE TO RETRY",
          );
        });
      };
      recorder.start();
    }).catch((cause: unknown) => {
      setState("error");
      setMessage(cause instanceof Error ? `MICROPHONE ERROR: ${cause.message}` : "MICROPHONE ACCESS FAILED");
    });
  }, [onDirective, startBrowserFallback]);

  useEffect(() => {
    if (state !== "recording") {
      setAmplitude(0);
      return;
    }
    let frame = 0;
    let phase = 0;
    const animate = () => {
      phase += 0.13;
      setAmplitude(0.45 + Math.abs(Math.sin(phase)) * 0.55);
      frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [state]);

  useEffect(() => () => {
    recorderRef.current?.stop();
    recognitionRef.current?.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  const available = typeof navigator !== "undefined" &&
    (!!navigator.mediaDevices?.getUserMedia || getRecognitionConstructor() !== null);

  return { available, amplitude, message, start, state, stop };
}
