import { useEffect, useRef } from "react";

type Props = { state: string; amplitude: number; docked: boolean };

export default function AstralCore({ state, amplitude, docked }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const input = useRef({ state, amplitude });
  input.current = { state, amplitude };
  useEffect(() => {
    const element = canvas.current;
    const ctx = element?.getContext("2d");
    if (!element || !ctx) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    let energy = 0;
    let width = 320;
    const resize = () => {
      width = element.clientWidth || 320;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      element.width = Math.round(width * dpr);
      element.height = Math.round(width * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    resize();
    const draw = (now: number) => {
      const { state, amplitude } = input.current;
      energy += (Math.max(0, Math.min(1, amplitude)) - energy) * .18;
      const t = reduced.matches ? 0 : now / 1000;
      const c = width / 2;
      const r = width * .35;
      const color = state === "processing" || state === "responding" ? "#f6b94e" : "#00e7f1";
      ctx.clearRect(0, 0, width, width);
      ctx.save();
      ctx.translate(c, c);
      const glow = ctx.createRadialGradient(0, 0, 0, 0, 0, r * 1.35);
      glow.addColorStop(0, "rgba(0,231,241,.14)");
      glow.addColorStop(1, "rgba(0,231,241,0)");
      ctx.fillStyle = glow;
      ctx.fillRect(-c, -c, width, width);
      const arc = (radius: number, from: number, to: number, stroke: string, line = 1) => {
        ctx.strokeStyle = stroke; ctx.lineWidth = line;
        ctx.beginPath(); ctx.arc(0, 0, radius, from, to); ctx.stroke();
      };
      arc(r, 0, Math.PI * 2, "#ac792d");
      for (let i = 0; i < 48; i++) {
        const a = i * Math.PI / 24 + t * .09;
        const inner = r - (i % 4 === 0 ? 9 : 4);
        ctx.strokeStyle = "#9a6a26"; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(Math.cos(a) * inner, Math.sin(a) * inner);
        ctx.lineTo(Math.cos(a) * r, Math.sin(a) * r); ctx.stroke();
      }
      for (let k = 0; k < 2; k++) {
        ctx.strokeStyle = "rgba(245,158,11,.42)";
        ctx.beginPath();
        for (let i = 0; i <= 3; i++) {
          const a = i * Math.PI * 2 / 3 + k * Math.PI + t * (k ? -.1 : .1);
          const x = Math.cos(a) * r * .88, y = Math.sin(a) * r * .88;
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }
      for (let k = 0; k < 4; k++) {
        const a = k * Math.PI / 2 - t * .35;
        arc(r * .76, a + .12, a + 1.42, color, 2.5);
      }
      for (let i = 0; i < 64; i++) {
        const a = i * Math.PI / 32 + t * .06;
        const inner = r * .52;
        const length = 4 + energy * 30 * (.35 + .65 * Math.abs(Math.sin(i * .47 + t * 4)));
        ctx.strokeStyle = i % 8 === 0 ? "#eeb55b" : color;
        ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.moveTo(Math.cos(a) * inner, Math.sin(a) * inner);
        ctx.lineTo(Math.cos(a) * (inner + length), Math.sin(a) * (inner + length)); ctx.stroke();
      }
      arc(r * .47, 0, Math.PI * 2, color, 1.5);
      ctx.restore();
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => { cancelAnimationFrame(frame); observer.disconnect(); };
  }, []);
  return <div className={"astral-core" + (docked ? " astral-docked" : "")} role="img" aria-label={"AURA çekirdek durumu: " + state}>
    <canvas ref={canvas} />
    <div className="astral-nucleus"><small>{state.toUpperCase()}</small><strong>AURA</strong><span>CORE // LIVE</span></div>
  </div>;
}
