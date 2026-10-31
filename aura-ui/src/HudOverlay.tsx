import { useEffect, useRef, useState } from "react";
import { useAuraVoice } from "./voice/useAuraVoice";
import { useContinuousAuraVoice } from "./voice/useContinuousAuraVoice";
import "./hud.css";

type HudEvent = { event?: string; data?: Record<string, unknown> };
type Region = {
  label: string; x: number; y: number; width: number; height: number;
  verified: false; source: "model_estimate";
};
type Panel = { id: string; title: string; kind: string; x: number; y: number; copy: string };
type HUDDesktop = {
  hudSetInteractive?: (enabled: boolean) => Promise<boolean>;
  onHudInteractive?: (listener: (value: boolean) => void) => () => void;
};
declare global {
  interface Window { auraDesktop?: HUDDesktop & {
    minimize?: () => Promise<void>; maximize?: () => Promise<void>; close?: () => Promise<void>;
  }; }
}
const slots = [[0.07, 0.19], [0.70, 0.13], [0.38, 0.52], [0.07, 0.60], [0.67, 0.61], [0.38, 0.14]];
const nextId = () => crypto.randomUUID();
const bounded = (value: number, low: number, high: number) =>
  Math.max(low, Math.min(high, value));
async function postHUD<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json" },
    credentials: "same-origin", body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: string | { code?: string } };
    const code = typeof payload.detail === "object" ? payload.detail.code : payload.detail;
    throw new Error(response.status === 403 ? "Windows onayı reddedildi veya yetki yok." :
      response.status === 503 ? "ScreenRead devre dışı veya ApprovalStore kullanılamıyor." :
      "ScreenRead HTTP " + response.status + (code ? " — " + code : ""));
  }
  return response.json() as Promise<T>;
}

export default function HudOverlay() {
  const [interactive, setInteractive] = useState(false);
  const [connected, setConnected] = useState(false);
  const [panels, setPanels] = useState<Panel[]>([]);
  const [regions, setRegions] = useState<Region[]>([]);
  const [question, setQuestion] = useState("Ekranda hangi nesneler var?");
  const [topic, setTopic] = useState("Porsche 911");
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");
  const drag = useRef<{ id: string; x: number; y: number; px: number; py: number } | null>(null);

  const addPanel = (title: string, kind = "object", copy = "", at?: [number, number]) => {
    setPanels(previous => {
      const slot = slots[previous.length % slots.length];
      const [x, y] = at ?? slot;
      return [...previous, {
        id: nextId(), title: title.slice(0, 100), kind,
        x: bounded(x, 0.015, 0.78), y: bounded(y, 0.04, 0.77), copy: copy.slice(0, 4000),
      }].slice(-9);
    });
  };
  const publishObject = (title: string) =>
    postHUD<{ status: string }>("/api/hud/panel", { title: title.slice(0, 100), kind: "object" })
      .catch(e => setError(e instanceof Error ? e.message : "Panel gösterilemedi."));

  const onTranscript = (transcript: string, requireWakeWord: boolean) => {
    let command = transcript.trim();
    if (requireWakeWord) {
      const match = /(?:^|\s)aura[\s,:;.!?-]*(.*)$/i.exec(command);
      if (!match) return;
      command = match[1].trim();
    }
    if (!command) return;
    if (/göster|show/i.test(command)) {
      setTopic(command.slice(0, 100));
      void publishObject(command);
    } else {
      // No voice command is authorized to read the screen.
      setQuestion(command.slice(0, 400));
      setError("Soru hazır. ScreenRead için düğmeye basıp Windows onayı verin.");
    }
  };
  const voice = useAuraVoice(text => onTranscript(text, false));
  const wake = useContinuousAuraVoice(text => onTranscript(text, true));

  useEffect(() => {
    const unsubscribe = window.auraDesktop?.onHudInteractive?.(setInteractive);
    const source = new EventSource("/api/events/stream", { withCredentials: true });
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = message => {
      try {
        const event = JSON.parse(message.data) as HudEvent;
        if (event.event === "HUDPanelShown" && typeof event.data?.title === "string") {
          addPanel(event.data.title, typeof event.data.kind === "string" ? event.data.kind : "object");
        }
        if (event.event === "HUDVisionScanStarted") setScanning(true);
        if (event.event === "HUDVisionScanEnded") setScanning(false);
      } catch { /* Discard malformed, untrusted event data. */ }
    };
    return () => { source.close(); unsubscribe?.(); };
  }, []);

  const readScreen = async () => {
    setError(""); setRegions([]); setScanning(true);
    try {
      const result = await postHUD<{
        description: string; bounding_boxes_verified: false; regions?: Region[];
      }>("/api/hud/screen/read", { prompt: question, confirmed: true });
      const detected = Array.isArray(result.regions) ? result.regions.filter(region =>
        region && region.source === "model_estimate" &&
        [region.x, region.y, region.width, region.height].every(n =>
          typeof n === "number" && Number.isFinite(n) && n >= 0 && n <= 1)
        && region.x + region.width <= 1.001 && region.y + region.height <= 1.001
      ).slice(0, 6) : [];
      setRegions(detected);
      if (detected.length) {
        detected.forEach(region => addPanel(region.label, "vision / estimated",
          result.description, [region.x + region.width + 0.025, region.y]));
      } else {
        addPanel("SCREENREAD / LOCAL VLM", "vision", result.description);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Ekran okunamadı.");
    } finally { setScanning(false); }
  };

  const startDrag = (event: React.PointerEvent<HTMLElement>, panel: Panel) => {
    if (!interactive) return;
    drag.current = { id: panel.id, x: panel.x, y: panel.y, px: event.clientX, py: event.clientY };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const moveDrag = (event: React.PointerEvent<HTMLElement>) => {
    if (!interactive || !drag.current) return;
    const d = drag.current;
    const dx = (event.clientX - d.px) / window.innerWidth;
    const dy = (event.clientY - d.py) / window.innerHeight;
    setPanels(previous => previous.map(panel => panel.id === d.id ?
      { ...panel, x: bounded(d.x + dx, 0, 0.78), y: bounded(d.y + dy, 0, 0.77) } : panel));
  };

  return <div className={"hud-root hud-canvas" + (scanning ? " is-scanning" : "")}>
    <div className="hud-identity" aria-label="AURA spatial display">
      <b>A.U.R.A.</b><small>SPATIAL INTERFACE / {connected ? "CORE LINK" : "OFFLINE"}</small>
    </div>
    <div className="hud-orbit" aria-hidden="true"><i /><i /><i /></div>
    {scanning && <div className="hud-sweep" aria-label="Ekran analizi sürüyor" />}
    {regions.map((region, index) => <div key={index} className="hud-region"
      style={{ left: (region.x * 100) + "%", top: (region.y * 100) + "%",
        width: (region.width * 100) + "%", height: (region.height * 100) + "%" }}
      aria-label={region.label + " (model estimate)"}>
      <span className="hud-region-tag">{region.label} / MODEL TAHMİNİ</span>
      <div className="hud-region-reticle" />
    </div>)}
    {panels.map(panel => <article key={panel.id} className="hud-float"
      style={{ left: (panel.x * 100) + "%", top: (panel.y * 100) + "%" }}>
      <header onPointerDown={event => startDrag(event, panel)}
        onPointerMove={moveDrag} onPointerUp={() => { drag.current = null; }}
        className={interactive ? "can-drag" : ""}>
        <span>✧ {panel.kind.toUpperCase()}</span>
        {interactive && <button aria-label={"Kapat " + panel.title} onPointerDown={e => e.stopPropagation()}
          onClick={() => setPanels(previous => previous.filter(item => item.id !== panel.id))}>×</button>}
      </header>
      <div className="hud-float-title">{panel.title}</div>
      {panel.copy ? <p>{panel.copy}</p> : <div className="hud-bars"><span /><span /><span /></div>}
      <footer>{panel.kind.startsWith("vision") ? "VLM ESTIMATE / NOT VERIFIED" : "PRESENTATION ONLY"}</footer>
    </article>)}
    <div className="hud-hint">CTRL + ALT + H · {interactive ? "CONTROLS ACTIVE" : "CLICK THROUGH"}</div>
    {interactive && <section className="hud-command" aria-label="AURA HUD controls">
      <header><strong>AURA / CONTROL DECK</strong><button onClick={() =>
        void window.auraDesktop?.hudSetInteractive?.(false)}>CLOSE</button></header>
      <label>HOLOGRAM <input maxLength={100} value={topic} onChange={e => setTopic(e.target.value)} /></label>
      <button onClick={() => void publishObject(topic.trim() || "AURA")}>YENİ HOLOGRAM</button>
      <label>SCREENREAD QUESTION <input maxLength={400} value={question}
        onChange={e => setQuestion(e.target.value)} /></label>
      <button disabled={scanning} onClick={() => void readScreen()}>
        {scanning ? "SCANNING..." : "EKRANI ONAYLA + OKU"}</button>
      <button onClick={() => voice.state === "recording" ? voice.stop() : voice.start()}>
        {voice.state === "recording" ? "KAYDI DURDUR" : "BAS-KONUŞ"}</button>
      <button aria-pressed={wake.active} onClick={() => wake.active ? wake.stop() : void wake.start()}>
        {wake.active ? "AURA DİNLEMEYİ KAPAT" : "AURA SESLE UYANDIR / OPT-IN"}</button>
      <small>{wake.active ? "MIC ON · YEREL STT · AURA KELİMESİ BEKLENİYOR" :
        "MIC OFF · Ses etkinleştirme isteğe bağlıdır."}</small>
      <small>Sesle ScreenRead başlatılmaz. Her ekran görüntüsü için Windows onayı gerekir.</small>
      {error && <div role="alert" className="hud-error">{error}</div>}
    </section>}
  </div>;
}
