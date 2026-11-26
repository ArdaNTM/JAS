import { useEffect, useRef } from "react";

type Props = { state: string; amplitude: number; docked: boolean };
const TAU = Math.PI * 2;
const RUNES = ["◇","⟐","✧","△","⊙","⌁","✦","○","⟡","▽","⋈","⊕"];
const clamp = (n: number) => Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : 0;

export default function AstralCore({ state, amplitude, docked }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const input = useRef({ state, amplitude });
  input.current = { state, amplitude };
  useEffect(() => {
    const element = canvas.current;
    const ctx = element?.getContext("2d");
    if (!element || !ctx) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const spectrum = new Float32Array(64);
    let sampleTime = -Infinity;
    const receive = (event: Event) => {
      const detail = (event as CustomEvent<{ source: string; bands: number[] }>).detail;
      if (!detail || !Array.isArray(detail.bands) || detail.bands.length !== 64) return;
      const speaking = input.current.state === "speaking";
      if (detail.source !== (speaking ? "playback" : "microphone")) return;
      for (let i = 0; i < 64; i++) spectrum[i] = clamp(detail.bands[i]);
      sampleTime = performance.now();
    };
    window.addEventListener("aura:audio-spectrum", receive);
    let frame = 0, energy = 0, width = 480, previous = 0, elapsed = 0;
    const resize = () => {
      width = element.clientWidth || 480;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      element.width = Math.round(width * dpr);
      element.height = Math.round(width * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();
    const arc = (r: number, a: number, b: number, color: string, line = 1) => {
      ctx.strokeStyle = color; ctx.lineWidth = line;
      ctx.beginPath(); ctx.arc(0, 0, r, a, b); ctx.stroke();
    };
    const polygon = (r: number, points: number, step: number, angle: number, color: string) => {
      ctx.strokeStyle = color; ctx.lineWidth = .85;
      ctx.beginPath();
      for (let i = 0; i <= points; i++) {
        const a = angle + i * TAU * step / points;
        const x = Math.cos(a) * r, y = Math.sin(a) * r;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
    };
    const draw = (now: number) => {
      frame = requestAnimationFrame(draw);
      const dt = Math.min(.05, Math.max(0, (now - (previous || now)) / 1000));
      previous = now;
      if (document.hidden) return;
      if (!reduced.matches) elapsed += dt;
      const t = elapsed;
      const { state, amplitude } = input.current;
      const listening = state === "listening";
      const speaking = state === "speaking";
      const working = state === "processing" || state === "responding";
      const live = listening || speaking;
      const target = live ? clamp(amplitude) : 0;
      energy += (target - energy) * (1 - Math.exp(-dt * (target > energy ? 20 : 6)));
      const r = width * .39;
      const pulse = reduced.matches ? 0 : Math.sin(t * 1.7) * .022;
      const scale = 1 + pulse + energy * .065;
      const cyan = working ? "#f8c46b" : "#62f4ff";
      ctx.clearRect(0, 0, width, width);
      ctx.save(); ctx.translate(width / 2, width / 2); ctx.scale(scale, scale);

      const aura = ctx.createRadialGradient(0, 0, r * .12, 0, 0, r * 1.3);
      aura.addColorStop(0, "rgba(12,86,118,.36)");
      aura.addColorStop(.42, "rgba(0,220,240," + (.09 + energy * .2) + ")");
      aura.addColorStop(.72, "rgba(238,173,63,.055)");
      aura.addColorStop(1, "transparent");
      ctx.fillStyle = aura; ctx.fillRect(-r * 1.3, -r * 1.3, r * 2.6, r * 2.6);

      // Three independent astrolabe mechanisms, with actual counterrotation.
      arc(r * 1.13, 0, TAU, "#b9823c48");
      for (let j = 0; j < 3; j++) {
        const radius = r * (1.04 - j * .115);
        const angle = t * [.115, -.19, .29][j];
        ctx.save(); ctx.rotate(angle);
        arc(radius, 0, TAU, j === 1 ? "#1fa5b55e" : "#c8954b92");
        for (let i = 0; i < 60; i++) {
          const a = i * TAU / 60;
          const major = i % 5 === 0;
          const inside = radius - (major ? r * .045 : r * .018);
          ctx.strokeStyle = major ? "#f8c67d" : "#aa743b76";
          ctx.lineWidth = major ? 1.3 : .7;
          ctx.beginPath(); ctx.moveTo(Math.cos(a) * inside, Math.sin(a) * inside);
          ctx.lineTo(Math.cos(a) * radius, Math.sin(a) * radius); ctx.stroke();
        }
        for (let i = 0; i < 12; i++) {
          const a = i * TAU / 12;
          ctx.save(); ctx.rotate(a); ctx.translate(0, -radius + r * .065);
          ctx.fillStyle = j === 1 ? "#8de9edaa" : "#f7c879cc";
          ctx.font = Math.max(9, r * .065) + "px Segoe UI Symbol, sans-serif";
          ctx.textAlign = "center"; ctx.textBaseline = "middle";
          ctx.fillText(RUNES[(i + j * 3) % RUNES.length], 0, 0);
          ctx.restore();
        }
        ctx.restore();
      }
      polygon(r * .83, 3, 1, -Math.PI / 2 + t * .14, "#edb96088");
      polygon(r * .83, 3, 1, Math.PI / 2 + t * .14, "#edb96088");
      polygon(r * .69, 8, 3, -t * .22, "#40d9df55");
      for (let i = 0; i < 6; i++) {
        const a = i * TAU / 6 - t * .42;
        ctx.shadowColor = cyan; ctx.shadowBlur = 9 + energy * 14;
        arc(r * .64, a + .09, a + .76, cyan, 2.3 + energy * 1.7);
      }
      ctx.shadowBlur = 0;
      // No synthetic speech spectrum: stale samples decay to zero.
      const fresh = live && now - sampleTime < 350;
      for (let i = 0; i < 64; i++) {
        const a = i * TAU / 64;
        const band = fresh ? spectrum[i] : 0;
        if (!fresh) spectrum[i] *= .86;
        const inner = r * .47;
        const length = r * (.025 + energy * .07 + band * .15);
        ctx.strokeStyle = i % 8 === 0 ? "#ffc877" : cyan;
        ctx.lineWidth = 1.3 + band * 1.7;
        ctx.beginPath(); ctx.moveTo(Math.cos(a) * inner, Math.sin(a) * inner);
        ctx.lineTo(Math.cos(a) * (inner + length), Math.sin(a) * (inner + length)); ctx.stroke();
      }
      if (live || working) {
        for (let i = 0; i < 3; i++) {
          const phase = reduced.matches ? .5 : (t * (speaking ? .8 : .42) + i / 3) % 1;
          ctx.globalAlpha = (1 - phase) * (.2 + energy * .55);
          arc(r * (.46 + phase * .67), 0, TAU, cyan, 1.4);
        }
        ctx.globalAlpha = 1;
      }
      for (let i = 0; i < 18; i++) {
        const a = i * 2.399963 + t * (i % 2 ? .18 : -.24);
        const radius = r * (1.07 + (i % 3) * .052);
        ctx.fillStyle = i % 3 ? "#78efff" : "#ffd28c";
        ctx.globalAlpha = .35 + .5 * (reduced.matches ? .5 : (1 + Math.sin(t * 1.8 + i)) / 2);
        ctx.beginPath(); ctx.arc(Math.cos(a) * radius, Math.sin(a) * radius, i % 3 ? 1.2 : 2, 0, TAU); ctx.fill();
      }
      ctx.globalAlpha = 1;
      const nucleus = ctx.createRadialGradient(0, 0, 0, 0, 0, r * .43);
      nucleus.addColorStop(0, "#102e40"); nucleus.addColorStop(1, "#03101d");
      ctx.fillStyle = nucleus; ctx.beginPath(); ctx.arc(0, 0, r * .43, 0, TAU); ctx.fill();
      ctx.shadowColor = cyan; ctx.shadowBlur = 14 + energy * 24;
      arc(r * .43, 0, TAU, cyan, 1.7 + energy);
      ctx.shadowBlur = 0; arc(r * .39, 0, TAU, "#75ddea45");
      ctx.restore();
    };
    frame = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(frame); observer.disconnect();
      window.removeEventListener("aura:audio-spectrum", receive);
    };
  }, []);
  const labels: Record<string, string> = { idle: "STANDBY", listening: "DİNLİYOR", speaking: "KONUŞUYOR", processing: "İŞLİYOR", responding: "YANITLIYOR", awaiting_approval: "ONAY BEKLİYOR", error: "DEGRADED" };
  return <div className={"astral-core" + (docked ? " astral-docked" : "")} data-state={state} role="img" aria-label={"AURA çekirdek durumu: " + state}>
    <canvas ref={canvas} aria-hidden="true" />
    <div className="astral-nucleus"><small>{labels[state] ?? state.toUpperCase()}</small><strong>AURA</strong><span>ASTRAL // CORE</span></div>
  </div>;
}
