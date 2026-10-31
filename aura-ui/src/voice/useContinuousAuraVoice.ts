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
  const noiseFloorRef = useRef(0.006);
  const lastTranscriptRef = useRef({ text: "", at: 0 });

  onDirectiveRef.current = onDirective;

  const stop = useCallback(() => {
    activeRef.current = false;
    setActive(false);
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    frameRef.current = null;
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
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
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
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
      noiseFloorRef.current = 0.006;
      activeRef.current = true;
      setActive(true);
      setMessage("SÜREKLİ DİNLEME ETKİN — YALNIZCA KONUŞMA PARÇALARI CORE'A GÖNDERİLİR");

      recorder.ondataavailable = (event) => {
        if (!event.data.size) return;
        const at = performance.now();
        chunksRef.current.push({ at, blob: event.data });
        // Keep only a short rolling buffer. No raw audio is persisted to disk.
        const cutoff = at - 9500;
        chunksRef.current = chunksRef.current.filter((chunk) => chunk.at >= cutoff);
      };
      recorder.onerror = () => setMessage("SÜREKLİ DİNLEMEDE KAYIT HATASI — DİNLEMEYİ DURDURUP YENİDEN DENEYİN");
      recorder.start(200);

      const samples = new Float32Array(analyser.fftSize);
      const MIN_UTTERANCE_MS = 320;
      const END_SILENCE_MS = 650;
      const MAX_UTTERANCE_MS = 7500;
      const tick = () => {
        if (!activeRef.current || !analyserRef.current) return;
        analyserRef.current.getFloatTimeDomainData(samples);
        let energy = 0;
        for (const sample of samples) energy += sample * sample;
        const rms = Math.sqrt(energy / samples.length);
        const now = performance.now();
        // Browser echo cancellation + adaptive noise floor reduce false VAD.
        // The transcript is still produced by the configured local STT
        // provider; this is not a trained keyword-spotting model.
        if (speechStartRef.current === null || rms < noiseFloorRef.current * 1.5) {
          noiseFloorRef.current = Math.max(0.003, Math.min(0.06,
            0.985 * noiseFloorRef.current + 0.015 * rms));
        }
        const configured = Number(import.meta.env.VITE_AURA_VAD_THRESHOLD);
        const threshold = Number.isFinite(configured) && configured > 0
          ? Math.max(0.008, Math.min(0.12, configured))
          : Math.max(0.012, Math.min(0.08, noiseFloorRef.current * 3.2));
        if (rms >= threshold) {
          if (speechStartRef.current === null) speechStartRef.current = now;
          lastSpeechRef.current = now;
        }
        if (
          speechStartRef.current !== null &&
          now - speechStartRef.current >= MIN_UTTERANCE_MS &&
          (now - lastSpeechRef.current >= END_SILENCE_MS ||
            now - speechStartRef.current >= MAX_UTTERANCE_MS) &&
          !processingRef.current
        ) {
          const startAt = speechStartRef.current;
          const endAt = Math.min(now, lastSpeechRef.current + 450);
          speechStartRef.current = null;
          const selected = chunksRef.current
            .filter((chunk) => chunk.at >= startAt - 600 && chunk.at <= endAt)
            .map((chunk) => chunk.blob);
          const blob = new Blob(selected, { type: recorder.mimeType || "audio/webm" });
          if (blob.size > 0) {
            processingRef.current = true;
            setProcessing(true);
            setMessage("KONUŞMA ALGILANDI — YEREL SES TANIMA ÇALIŞIYOR");
            void transcribeLocalAudio(blob).then((result) => {
              const transcript = result.text.trim();
              if (transcript && activeRef.current) {
                const previous = lastTranscriptRef.current;
                const normalized = transcript.toLocaleLowerCase("tr-TR");
                if (previous.text !== normalized || performance.now() - previous.at > 2500) {
                  lastTranscriptRef.current = { text: normalized, at: performance.now() };
                  // Preserve the wake phrase: HUD alone decides if "AURA" exists.
                  onDirectiveRef.current(transcript);
                }
                setMessage("YEREL SES TANIMA TAMAMLANDI — YENİ KOMUT BEKLENİYOR");
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
      stop();
      setMessage(error instanceof Error ? `MİKROFON AÇILAMADI: ${error.message}` : "MİKROFON AÇILAMADI");
    }
  }, [stop]);

  useEffect(() => () => {
    activeRef.current = false;
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    sourceRef.current?.disconnect();
    void audioContextRef.current?.close().catch(() => undefined);
  }, []);

  return { active, processing, message, start, stop };
}
