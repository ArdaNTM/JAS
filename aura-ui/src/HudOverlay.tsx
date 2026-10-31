import { useCallback, useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { useAuraVoice } from "./voice/useAuraVoice";
import { useContinuousAuraVoice } from "./voice/useContinuousAuraVoice";
import "./hud.css";

type Region = {
  label: string; x: number; y: number; width: number; height: number;
  verified: false; source: "model_estimate";
};
type MediaAsset = { url: string; page: string; artist: string; license: string };
type Panel = {
  id: string; displayId: number; x: number; y: number;
  title: string; kind: string; copy: string; media: MediaAsset | null;
};
type Scene = {
  displayId: number; primary: boolean; interactive: boolean;
  bounds: { x: number; y: number; width: number; height: number } | null;
  panels: Panel[]; regions: Region[];
};
type HUDDesktop = {
  hudSetInteractive?: (enabled: boolean) => Promise<boolean>;
  onHudInteractive?: (listener: (value: boolean) => void) => () => void;
  hudGetScene?: () => Promise<Scene | null>;
  onHudScene?: (listener: (value: Scene) => void) => () => void;
  hudPublishPanel?: (panel: { title: string; kind: string; copy?: string }) => Promise<string | null>;
  hudUpdatePanel?: (id: string, media: MediaAsset) => Promise<boolean>;
  hudDismissPanel?: (id: string) => Promise<boolean>;
  hudSetRegions?: (regions: Region[]) => Promise<boolean>;
  hudDragStart?: (id: string) => Promise<boolean>;
  hudDragEnd?: () => Promise<boolean>;
};
declare global {
  interface Window { auraDesktop?: HUDDesktop & {
    minimize?: () => Promise<void>; maximize?: () => Promise<void>; close?: () => Promise<void>;
  }; }
}
type HttpError = { detail?: string | { code?: string } };
async function postHUD<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST", headers: { "Content-Type": "application/json" },
    credentials: "same-origin", body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as HttpError;
    const code = typeof payload.detail === "object" ? payload.detail.code : payload.detail;
    throw new Error((response.status === 403 ? "Yetki reddedildi" :
      response.status === 503 ? "Core özelliği kullanılamıyor" :
      "ScreenRead HTTP " + response.status) + (code ? " — " + code : ""));
  }
  return response.json() as Promise<T>;
}

function splitShowRequest(transcript: string): string[] {
  const request = transcript.trim().replace(/^aura[\s,:;.!?-]*/i, "")
    .replace(/^bana\s+/i, "").replace(/\s+(göster(?:ir misin)?|show(?: me)?)\s*[.!?]*$/i, "").trim();
  return request.split(/\s*(?:,|\s+ve\s+|\s+and\s+|\s*&\s*)\s*/i)
    .map(value => value.trim().slice(0, 100))
    .filter(Boolean).slice(0, 5);
}

function Schematic({ title }: { title: string }) {
  return <div className="hud-schematic" aria-label={"Temsili teknik çizim: " + title}>
    <svg viewBox="0 0 320 125" role="img" aria-label="Genel nesne şeması; gerçek CAD veya fotoğraf değil">
      <path d="M16 86 L52 70 L84 65 L115 34 Q158 18 213 36 L246 66 L289 71 L306 91 L300 101 L19 101 Z" />
      <path d="M103 65 L123 40 Q162 28 208 42 L232 66 Z M119 72 L245 72 M23 91 L305 91" />
      <circle cx="85" cy="102" r="20" /><circle cx="251" cy="102" r="20" />
      <path d="M145 42 L145 70 M39 77 L65 77 M270 77 L290 77" />
    </svg>
    <span>ILLUSTRATIVE WIREFRAME · NOT AN IDENTIFIED MODEL</span>
  </div>;
}

export default function HudOverlay() {
  const [scene, setScene] = useState<Scene | null>(null);
  const [connected, setConnected] = useState(false);
  const [topic, setTopic] = useState("Porsche 911");
  const [question, setQuestion] = useState("Ekranda hangi nesneler var?");
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");
  const [trusted, setTrusted] = useState<{ token: string; until: number; remaining: number } | null>(null);
  const trustedRef = useRef(trusted);
  trustedRef.current = trusted;

  useEffect(() => {
    const desktop = window.auraDesktop;
    const detachScene = desktop?.onHudScene?.(setScene);
    const detachInteractive = desktop?.onHudInteractive?.(interactive =>
      setScene(previous => previous ? { ...previous, interactive } : previous));
    void desktop?.hudGetScene?.().then(setScene);
    return () => { detachScene?.(); detachInteractive?.(); };
  }, []);

  const publishObject = useCallback(async (name: string) => {
    if (!name.trim()) return;
    try {
      await postHUD<{ status: string }>("/api/hud/panel",
        { title: name.trim().slice(0, 100), kind: "object" });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Panel gösterilemedi");
    }
  }, []);

  const readScreen = useCallback(async (prompt: string, session?: { token: string; until: number; remaining: number }) => {
    setError(""); setScanning(true);
    try {
      const usable = session && session.remaining > 0 && Date.now() < session.until ? session : null;
      const result = await postHUD<{ description: string; regions?: Region[]; bounding_boxes_verified: false }>(
        "/api/hud/screen/read",
        { prompt: prompt.slice(0, 400), confirmed: true,
          ...(usable ? { trusted_session_token: usable.token } : {}) });
      if (usable) setTrusted(previous => previous && previous.token === usable.token ?
        { ...previous, remaining: Math.max(0, previous.remaining - 1) } : previous);
      const regions = Array.isArray(result.regions) ? result.regions.filter(region =>
        region && region.verified === false && region.source === "model_estimate" &&
        [region.x, region.y, region.width, region.height].every(value =>
          typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1) &&
        region.x + region.width <= 1.001 && region.y + region.height <= 1.001
      ).slice(0, 8) : [];
      await window.auraDesktop?.hudSetRegions?.(regions);
      if (regions.length) {
        for (const item of regions) {
          await window.auraDesktop?.hudPublishPanel?.({
            title: item.label, kind: "vision · unverified", copy: result.description.slice(0, 4000),
          });
        }
      } else {
        await window.auraDesktop?.hudPublishPanel?.({
          title: "SCREENREAD / LOCAL VLM", kind: "vision",
          copy: result.description.slice(0, 4000),
        });
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "ScreenRead başarısız");
      if (session) setTrusted(null);
    } finally { setScanning(false); }
  }, []);

  const handleTranscript = (transcript: string, wakeRequired: boolean) => {
    const phrase = transcript.trim();
    const command = wakeRequired ? /(?:^|\s)aura[\s,:;.!?-]*(.*)$/i.exec(phrase)?.[1]?.trim() : phrase;
    if (!command) return;
    if (/\b(göster|show)\b/i.test(command)) {
      for (const name of splitShowRequest(command)) void publishObject(name);
    } else if (/ekran.*(oku|analiz|tara)|screen.*(read|analy[sz]e)/i.test(command)) {
      setQuestion(command.slice(0, 400));
      const session = trustedRef.current;
      if (session && Date.now() < session.until && session.remaining > 0) {
        void readScreen(command, session);
      } else {
        setError("Ekran okumak için kontrol panelinden Trusted Session başlatın veya tek-seferlik onay verin.");
      }
    } else {
      setQuestion(command.slice(0, 400));
    }
  };
  const voice = useAuraVoice(text => handleTranscript(text, false));
  const wake = useContinuousAuraVoice(text => handleTranscript(text, true));

  useEffect(() => {
    if (!scene?.primary) return;
    const source = new EventSource("/api/events/stream", { withCredentials: true });
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = event => {
      try {
        const item = JSON.parse(event.data) as { event?: string; data?: Record<string, unknown> };
        if (item.event === "HUDPanelShown" && typeof item.data?.title === "string") {
          const title = item.data.title.slice(0, 100);
          const kind = typeof item.data.kind === "string" ? item.data.kind : "object";
          void (async () => {
            const id = await window.auraDesktop?.hudPublishPanel?.({ title, kind });
            if (!id || kind !== "object") return;
            // User-initiated keyword only. No screenshot text is sent to Commons.
            try {
              const reply = await postHUD<{ results: MediaAsset[] }>(
                "/api/hud/media/search", { query: title });
              if (reply.results?.[0]) await window.auraDesktop?.hudUpdatePanel?.(id, reply.results[0]);
            } catch {
              // Keep explicitly-labelled, local illustrative wireframe on lookup failure.
            }
          })();
        }
        if (item.event === "HUDVisionScanStarted") setScanning(true);
        if (item.event === "HUDVisionScanEnded") setScanning(false);
      } catch { /* malformed events are ignored */ }
    };
    return () => { source.close(); setConnected(false); };
  }, [scene?.primary]);

  const armTrusted = async () => {
    try {
      const response = await postHUD<{ token: string; expires_in: number; captures_remaining: number }>(
        "/api/hud/session/start", { confirmed: true });
      setTrusted({ token: response.token, until: Date.now() + response.expires_in * 1000,
        remaining: response.captures_remaining });
      setError("");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Oturum açılamadı"); }
  };
  const revokeTrusted = async () => {
    const session = trustedRef.current;
    setTrusted(null);
    if (session) await postHUD("/api/hud/session/revoke", { token: session.token }).catch(() => undefined);
  };
  const startDrag = (e: ReactPointerEvent<HTMLElement>, id: string) => {
    if (!scene?.interactive) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    void window.auraDesktop?.hudDragStart?.(id);
  };
  const stopDrag = () => { void window.auraDesktop?.hudDragEnd?.(); };

  const isPrimary = Boolean(scene?.primary);
  const activeSession = trusted && trusted.until > Date.now() && trusted.remaining > 0 ? trusted : null;

  return <div className={"hud-root hud-canvas" + (scanning ? " is-scanning" : "")}>
    <div className="hud-identity">
      <b>A.U.R.A.</b>
      <small>{connected || scene ? "SPATIAL MESH / CORE" : "AWAITING CORE"}
        {scene?.displayId !== undefined ? " · DISPLAY " + scene.displayId : ""}</small>
    </div>
    {isPrimary && <div className="hud-orbit" aria-hidden="true"><i /><i /><i /></div>}
    {scanning && isPrimary && <div className="hud-sweep" aria-label="Görsel analiz sürüyor" />}
    {(scene?.regions ?? []).map((region, index) => <div key={index} className="hud-region"
      style={{ left: region.x * 100 + "%", top: region.y * 100 + "%",
        width: region.width * 100 + "%", height: region.height * 100 + "%" }}>
      <span className="hud-region-tag">{region.label} · MODEL TAHMİNİ</span>
      <div className="hud-region-reticle" />
    </div>)}
    {(scene?.panels ?? []).map(panel => <article className="hud-float" key={panel.id}
      style={{ left: panel.x - (scene?.bounds?.x ?? 0),
        top: panel.y - (scene?.bounds?.y ?? 0) }}>
      <header className={scene?.interactive ? "can-drag" : ""}
        onPointerDown={e => startDrag(e, panel.id)}
        onPointerUp={stopDrag} onPointerCancel={stopDrag}
        onLostPointerCapture={stopDrag}>
        <span>✧ {panel.kind.toUpperCase()}</span>
        {scene?.interactive && <button onPointerDown={e => e.stopPropagation()}
          aria-label={"Kapat " + panel.title}
          onClick={() => void window.auraDesktop?.hudDismissPanel?.(panel.id)}>×</button>}
      </header>
      <div className="hud-float-title">{panel.title}</div>
      {panel.media ? <div className="hud-media">
        <img src={panel.media.url} alt={panel.title + " — Wikimedia Commons görseli"}
          referrerPolicy="no-referrer" loading="lazy" />
        <div className="hud-media-meta">{panel.media.license} · {panel.media.artist || "Wikimedia Commons"}</div>
        <div className="hud-media-source">WIKIMEDIA COMMONS · EXTERNAL QUERY · SOURCE AVAILABLE</div>
      </div> : panel.copy ? <p>{panel.copy}</p> : <Schematic title={panel.title} />}
      {panel.copy && panel.media && <p>{panel.copy}</p>}
      <footer>{panel.kind.startsWith("vision") ? "UNTRUSTED VLM ESTIMATE · NOT VERIFIED" :
        panel.media ? "SOURCED IMAGE · CREDIT ABOVE" : "ILLUSTRATIVE · ASSET NOT FOUND"}</footer>
    </article>)}
    <div className="hud-hint">CTRL + ALT + H · {scene?.interactive ? "INTERACTIVE" : "CLICK THROUGH"}</div>
    {isPrimary && scene?.interactive && <section className="hud-command" aria-label="AURA HUD control deck">
      <header><strong>AURA / SPATIAL CONTROL</strong>
        <button onClick={() => void window.auraDesktop?.hudSetInteractive?.(false)}>CLOSE</button></header>
      <label>GÖRSEL NESNE / NESNELER <input maxLength={100} value={topic}
        onChange={e => setTopic(e.target.value)} /></label>
      <button onClick={() => splitShowRequest(topic).forEach(name => void publishObject(name))}>
        GÖRSEL BUL + HOLOGRAM AÇ</button>
      <small>Görsel araması yalnızca açık isteğinizle Wikimedia Commons'a gider.</small>
      <label>SCREENREAD QUESTION <input maxLength={400} value={question}
        onChange={e => setQuestion(e.target.value)} /></label>
      <button disabled={scanning} onClick={() => void readScreen(question, activeSession ?? undefined)}>
        {scanning ? "SCANNING..." : "EKRANI ONAYLA + OKU"}</button>
      <button onClick={() => activeSession ? void revokeTrusted() : void armTrusted()}>
        {activeSession ? "TRUSTED SESSION İPTAL · " + activeSession.remaining + " KALDI" :
          "TRUSTED SESSION AÇ · 90S / 3 OKUMA"}
      </button>
      <button onClick={() => voice.state === "recording" ? voice.stop() : voice.start()}>
        {voice.state === "recording" ? "KAYDI DURDUR" : "BAS-KONUŞ"}</button>
      <button aria-pressed={wake.active} onClick={() => wake.active ? wake.stop() : void wake.start()}>
        {wake.active ? "MİKROFONU KAPAT" : "AURA WAKE PHRASE / OPT-IN"}
      </button>
      <small>{wake.active ? "MIC ON · YEREL STT" : "MIC OFF"}
        {" · "}
        {activeSession ? "TRUSTED CAPTURE ACTIVE" : "CAPTURE REQUIRES NATIVE APPROVAL"}</small>
      <small>Ses tek başına yeni ekran yetkisi vermez. Trusted Session otomatik yenilenmez.</small>
      {error && <div role="alert" className="hud-error">{error}</div>}
    </section>}
  </div>;
}
