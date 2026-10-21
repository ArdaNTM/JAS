import { useCallback, useEffect, useRef, useState } from "react";
import { transcribeLocalAudio } from "../api/client";

type TimedChunk = { at: number; blob: Blob };

export function useContinuousAuraVoice(onDirective: (value: string) => void) {
  const [active, setActive] = useState(false);
  const [message, setMessage] = useState("SÜREKLİ DİNLEME KAPALI");
  const [processing, setProcessing] = useState(false);
  const onDirectiveRef = useRef(onDirective);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const chunksRef = useRef<TimedChunk[]>([]);
  const frameRef = useRef<number | null>(null);
  const speechStartRef = useRef<number | null>(null);
  const lastSpeechRef = useRef<number>(0);
  const processingRef = useRef(false);
  const activeRef = useRef(false);

  onDirectiveRef.current = onDirective;

  const stop = useCallback(() => {
    activeRef.current = false;
    setActive(false);
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    frameRef.current = null;
    recorderRef.current?.stop();
    recorderRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    sourceRef.current?.disconnect();
    sourceRef.current = null;
    void audioContextRef.current?.close().catch(() => undefined);
    audioContextRef.current = null;
    analyserRef.current = null;
    chunksRef.current = [];
    speechStartRef.current = null;
    setMessage("SÜREKLİ DİNLEME KAPALI — MİKROFON SERBEST BIRAKILDI");
  }, []);

  const start = useCallback(async () => {
    if (activeRef.current) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setMessage("SÜREKLİ DİNLEME DESTEKLENMİYOR — TARAYICI VE MİKROFON İZNİNİ KONTROL EDİN");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const audioContext = new AudioContext();
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 1024;
      source.connect(analyser);
      const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg"]
        .find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);

      streamRef.current = stream;
      audioContextRef.current = audioContext;
      sourceRef.current = source;
      analyserRef.current = analyser;
      recorderRef.current = recorder;
      chunksRef.current = [];
      speechStartRef.current = null;
      lastSpeechRef.current = 0;
      activeRef.current = true;
      setActive(true);
      setMessage("SÜREKLİ DİNLEME ETKİN — YALNIZCA KONUŞMA PARÇALARI CORE'A GÖNDERİLİR");

      recorder.ondataavailable = (event) => {
        if (!event.data.size) return;
        const at = performance.now();
        chunksRef.current.push({ at, blob: event.data });
        // Keep only a short rolling buffer. No raw audio is persisted to disk.
        const cutoff = at - 15000;
        chunksRef.current = chunksRef.current.filter((chunk) => chunk.at >= cutoff);
      };
      recorder.onerror = () => setMessage("SÜREKLİ DİNLEMEDE KAYIT HATASI — DİNLEMEYİ DURDURUP YENİDEN DENEYİN");
      recorder.start(250);

      const samples = new Float32Array(analyser.fftSize);
      const tick = () => {
        if (!activeRef.current || !analyserRef.current) return;
        analyserRef.current.getFloatTimeDomainData(samples);
        let energy = 0;
        for (const sample of samples) energy += sample * sample;
        const rms = Math.sqrt(energy / samples.length);
        const now = performance.now();
        const threshold = Number.isFinite(Number(import.meta.env.VITE_AURA_VAD_THRESHOLD))
          ? Math.max(0.008, Math.min(0.12, Number(import.meta.env.VITE_AURA_VAD_THRESHOLD)))
          : 0.018;
        if (rms >= threshold) {
          if (speechStartRef.current === null) speechStartRef.current = now;
          lastSpeechRef.current = now;
        } else if (
          speechStartRef.current !== null &&
          now - lastSpeechRef.current >= 900 &&
          now - speechStartRef.current >= 250 &&
          !processingRef.current
        ) {
          const startAt = speechStartRef.current;
          const endAt = lastSpeechRef.current + 500;
          speechStartRef.current = null;
          const selected = chunksRef.current
            .filter((chunk) => chunk.at >= startAt - 800 && chunk.at <= endAt)
            .map((chunk) => chunk.blob);
          const blob = new Blob(selected, { type: recorder.mimeType || "audio/webm" });
          if (blob.size > 0) {
            processingRef.current = true;
            setProcessing(true);
            setMessage("KONUŞMA ALGILANDI — YEREL SES TANIMA ÇALIŞIYOR");
            void transcribeLocalAudio(blob).then((result) => {
              const transcript = result.text.trim();
              if (transcript) {
                onDirectiveRef.current(transcript.replace(/^aura\b[\s,.:;!-]*/i, "").trim() || transcript);
                setMessage("KONUŞMA METNE DÖNÜŞTÜ — ÇALIŞTIRMAK İÇİN ENTER GEREKLİ");
              } else {
                setMessage("KONUŞMA ALGILANDI AMA METİN OLUŞMADI — DİNLEME SÜRÜYOR");
              }
            }).catch(() => {
              setMessage("SES ÇÖZÜMLENEMEDİ — DİNLEME SÜRÜYOR, CORE GÜNLÜKLERİNİ KONTROL EDİN");
            }).finally(() => {
              processingRef.current = false;
              setProcessing(false);
            });
          }
          lastSpeechRef.current = 0;
        }
        frameRef.current = requestAnimationFrame(tick);
      };
      frameRef.current = requestAnimationFrame(tick);
    } catch (error) {
      setMessage(error instanceof Error ? `MİKROFON AÇILAMADI: ${error.message}` : "MİKROFON AÇILAMADI");
      stop();
    }
  }, [stop]);

  useEffect(() => () => {
    activeRef.current = false;
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    recorderRef.current?.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    sourceRef.current?.disconnect();
    void audioContextRef.current?.close().catch(() => undefined);
  }, []);

  return { active, processing, message, start, stop };
}
