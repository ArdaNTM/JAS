import { useEffect, useState } from "react";
import "./hud.css";
import { useAuraVoice } from "./voice/useAuraVoice";

type HudEvent = {
  event?: string;
  data?: Record<string, unknown>;
};

type HUDDesktop = {
  hudSetInteractive?: (enabled: boolean) => Promise<boolean>;
  onHudInteractive?: (listener: (value: boolean) => void) => () => void;
};
declare global {
  interface Window { auraDesktop?: HUDDesktop & {
    minimize?: () => Promise<void>; maximize?: () => Promise<void>;
    close?: () => Promise<void>;
  }; }
}

async function postHUD<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(
      response.status === 403 ? "Yetki reddedildi / Windows onayı verilmedi." :
      response.status === 503 ? "ScreenRead kapalı: model veya ApprovalStore yapılandırmasını kontrol edin." :
      `ScreenRead HTTP ${response.status}`,
    );
  }
  return response.json() as Promise<T>;
}

export default function HudOverlay() {
  const [interactive, setInteractive] = useState(false);
  const [title, setTitle] = useState("AURA / HUD STANDBY");
  const [kind, setKind] = useState("object");
  const [question, setQuestion] = useState("Ekranda ne görüyorsun?");
  const [description, setDescription] = useState("");
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");
  const [connected, setConnected] = useState(false);
  const voice = useAuraVoice((transcript) => {
    const text = transcript.trim().slice(0, 100);
    if (text) setTitle(text);
  });


  useEffect(() => {
    const unsub = window.auraDesktop?.onHudInteractive?.(setInteractive);
    const source = new EventSource("/api/events/stream", { withCredentials: true });
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.onmessage = (message) => {
      try {
        const item = JSON.parse(message.data) as HudEvent;
        if (item.event === "HUDPanelShown") {
          const label = item.data?.title;
          const type = item.data?.kind;
          if (typeof label === "string") setTitle(label.slice(0, 100));
          if (typeof type === "string") setKind(type);
          setDescription("");
        }
        if (item.event === "HUDVisionScanStarted") setScanning(true);
        if (item.event === "HUDVisionScanEnded") setScanning(false);
      } catch {
        // Reject malformed event data without accepting commands from it.
      }
    };
    return () => { source.close(); unsub?.(); };
  }, []);

  const readScreen = async () => {
    setError("");
    setDescription("");
    setScanning(true);
    try {
      const result = await postHUD<{ description: string; bounding_boxes_verified: boolean }>(
        "/api/hud/screen/read",
        { prompt: question, confirmed: true },
      );
      setTitle("SCREENREAD / LOCAL VLM");
      setKind("vision");
      setDescription(result.description.slice(0, 4000));
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Ekran okunamadı.");
    } finally {
      setScanning(false);
    }
  };

  const displayObject = async () => {
    setError("");
    try {
      await postHUD("/api/hud/panel", { title: title.trim() || "AURA", kind: "object" });
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Panel açılamadı.");
    }
  };

  return (
    <div className={"hud-root" + (scanning ? " is-scanning" : "")}>
      <section className="hud-panel" aria-label="AURA global head up display">
        <header className="hud-top">
          <span className="hud-brand">A.U.R.A. <small>GLOBAL DISPLAY</small></span>
          <span className={"hud-status" + (connected ? " online" : "")}>
            {connected ? "● CORE LINK" : "○ CORE OFFLINE"}
          </span>
        </header>

        <div className="hud-visual">
          <div className="hud-reticle" aria-hidden="true">
            <span className="ring ring-a" /><span className="ring ring-b" />
            <span className="cross cross-h" /><span className="cross cross-v" />
            <div className="hud-schematic">
              <svg viewBox="0 0 260 106" role="img" aria-label="Temsili araç hologramı">
                <path d="M18 77 L37 63 L65 54 L82 29 Q111 15 164 23 L192 53 L226 60 L245 78 L241 89 L22 89Z" />
                <path d="M79 54 L94 32 Q120 26 161 32 L180 55 Z M27 71 L67 72 M190 72 L240 72" />
                <circle cx="66" cy="89" r="15" /><circle cx="196" cy="89" r="15" />
                <path d="M88 59 L178 59 M110 23 L110 54 M41 66 L49 78 M220 67 L213 78" />
              </svg>
            </div>
            <div className="hud-focus one" /><div className="hud-focus two" />
          </div>
          {scanning && <div className="hud-scanline" aria-label="Ekran analizi sürüyor" />}
          <div className="hud-telemetry">
            <span>OBJECT / {kind.toUpperCase()}</span>
            <span>{scanning ? "ANALYZING..." : "DISPLAY ACTIVE"}</span>
          </div>
        </div>

        <div className="hud-body">
          <div className="hud-title">{title}</div>
          <div className="hud-copy">
            {description || "Şematik görüntü temsildir; gerçek fotoğraf veya doğrulanmış CAD modeli değildir."}
          </div>
          {error && <div className="hud-error" role="alert">{error}</div>}
        </div>

        {interactive && (
          <div className="hud-controls">
            <label>HUD İÇERİĞİ
              <input value={title} maxLength={100} onChange={e => setTitle(e.target.value)} />
            </label>
            <button onClick={() => void displayObject()}>GÖSTER</button>
            <label>EKRAN SORUSU
              <input value={question} maxLength={400} onChange={e => setQuestion(e.target.value)} />
            </label>
            <button onClick={() => voice.state === "recording" ? voice.stop() : voice.start()}>
              {voice.state === "recording" ? "KAYDI DURDUR" : "BAS-KONUŞ"}
            </button>
            <button disabled={scanning} onClick={() => void readScreen()}>
              {scanning ? "TARANIYOR" : "EKRANI ONAYLA + OKU"}
            </button>
            <button className="hud-close" onClick={() => void window.auraDesktop?.hudSetInteractive?.(false)}>
              GİZLE KONTROLLERİ
            </button>
          </div>
        )}

        <footer className="hud-footer">
          <span>LOCAL ONLY / PERMISSION-GOVERNED</span>
          <span>{interactive ? "INTERACTIVE" : "CTRL+ALT+H → CONTROLS"}</span>
        </footer>
      </section>
    </div>
  );
}
