import { useCallback, useEffect, useState } from "react";

interface RunState {
  run_id: string;
  state: string;
  used: number;
  cursor: number;
  deadline: number;
  approval_id: string | null;
  error: string;
}

interface StageCStatus {
  enabled: boolean;
  kill_switch_engaged: boolean;
  max_actions: number;
  deadline_seconds: number;
}

/** HUD can start/cancel and display a pending Gateway approval.
 * It NEVER approves an action or handles passkey credentials.
 */
export default function StageCControlPanel() {
  const [expanded, setExpanded] = useState(false);
  const [status, setStatus] = useState<StageCStatus | null>(null);
  const [run, setRun] = useState<RunState | null>(null);
  const [goal, setGoal] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [notice, setNotice] = useState("Aşama C varsayılan olarak kapalıdır.");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const response = await fetch("/api/stage-c/status", {
        credentials: "omit", cache: "no-store",
      });
      if (!response.ok) {
        setStatus(null);
        setNotice("Aşama C devre dışı veya erişilemiyor (" + response.status + ")");
        return;
      }
      const current: StageCStatus = await response.json();
      setStatus(current);
      if (current.kill_switch_engaged) setNotice("ACİL DURDURMA KİLİTLİ — yeni görev yok");
    } catch {
      setStatus(null);
      setNotice("Kontrol kanalına erişilemiyor");
    }
  }, []);

  const refreshRun = useCallback(async (id: string) => {
    const response = await fetch("/api/stage-c/runs/" + encodeURIComponent(id), {
      credentials: "omit", cache: "no-store",
    });
    if (!response.ok) {
      setNotice("Görev durumu doğrulanamadı");
      return;
    }
    setRun(await response.json() as RunState);
  }, []);

  useEffect(() => {
    if (!expanded) return;
    void refresh();
  }, [expanded, refresh]);

  useEffect(() => {
    if (!expanded || !run) return;
    if (!["draft", "ready", "in_flight"].includes(run.state)) return;
    const id = window.setInterval(() => void refreshRun(run.run_id), 1200);
    return () => window.clearInterval(id);
  }, [expanded, run, refreshRun]);

  async function command(action: "start" | "resume" | "kill") {
    if (busy) return;
    if (action === "kill" && !window.confirm(
      "AURA Aşama C acil durdurma KALICI olarak etkinleşecek. Onaylıyor musun?"
    )) return;
    if (action === "start" && (!confirmed || goal.trim().length === 0)) return;
    setBusy(true);
    try {
      const url = action === "start" ? "/api/stage-c/runs"
        : action === "kill" ? "/api/stage-c/kill-switch"
          : "/api/stage-c/runs/" + encodeURIComponent(run?.run_id ?? "") + "/resume";
      const response = await fetch(url, {
        method: "POST",
        credentials: "omit",
        headers: { "Content-Type": "application/json" },
        body: action === "start" ? JSON.stringify({ goal, confirmed: true }) : "{}",
      });
      if (!response.ok) {
        setNotice("İşlem reddedildi (" + response.status + ")");
        return;
      }
      if (action === "kill") {
        setRun(null);
        setConfirmed(false);
        await refresh();
        return;
      }
      const result = await response.json() as RunState;
      setRun(result);
      setNotice("Her eylem için bağımsız Gateway yetkilendirmesi gereklidir.");
      setConfirmed(false);
    } catch {
      setNotice("Kontrol bağlantısı kesildi. Eylem sonucunu doğrula.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mx-auto mt-6 w-full max-w-5xl border border-amber-900/70 bg-slate-950/85 p-5 text-xs text-slate-200">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold tracking-[.28em] text-amber-300">
            STAGE C / GOVERNED COMPUTER AUTONOMY
          </p>
          <p className="mt-2 text-slate-400">
            En fazla 8 eylem · 120 sn · Her eylem MCP Gateway'de onaya tabidir
          </p>
        </div>
        <button type="button" aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
          className="rounded border border-amber-700 px-3 py-2 text-amber-200">
          {expanded ? "KAPAT" : "AJAN KONTROLÜ"}
        </button>
      </div>
      {expanded && (
        <div className="mt-4 space-y-3 border-t border-amber-950 pt-4">
          <p role="status" className="text-amber-300">{notice}</p>
          {status && (
            <>
              <p>Yetki: Bağımsız Owner Control Plane · Kill Switch: {
                status.kill_switch_engaged ? "AKTİF" : "Hazır"
              }</p>
              <label className="block" htmlFor="stage-c-goal">Onaylı görev tanımı</label>
              <input id="stage-c-goal" value={goal} maxLength={1000}
                onChange={e => setGoal(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-900 p-3"
                placeholder="Örneğin: İzinli web sayfasının başlığını oku"
                disabled={status.kill_switch_engaged || busy} />
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={confirmed}
                  onChange={e => setConfirmed(e.target.checked)}
                  disabled={status.kill_switch_engaged || busy} />
                Görevi açıkça istiyorum; bu onay araç izni yerine geçmez.
              </label>
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => void command("start")}
                  disabled={busy || !confirmed || !goal.trim() || status.kill_switch_engaged}
                  className="rounded border border-cyan-700 px-4 py-2 text-cyan-200 disabled:opacity-40">
                  PLANLA / BAŞLAT
                </button>
                {run?.state === "awaiting_approval" && (
                  <button type="button" onClick={() => void command("resume")}
                    disabled={busy || status.kill_switch_engaged}
                    className="rounded border border-amber-700 px-4 py-2 text-amber-200">
                    HARİCİ ONAYI YENİDEN DENETLE
                  </button>
                )}
                <button type="button" onClick={() => void command("kill")}
                  disabled={busy || status.kill_switch_engaged}
                  className="rounded border border-red-600 bg-red-950 px-4 py-2 text-red-200 disabled:opacity-40">
                  ACİL DURDUR / KİLİTLE
                </button>
              </div>
              {run && (
                <div className="space-y-1 rounded border border-slate-800 p-3">
                  <p>Durum: {run.state} · {run.used}/8 eylem</p>
                  <p className="break-all text-slate-500">Run: {run.run_id}</p>
                  {run.approval_id && (
                    <p className="break-all text-amber-300">
                      Harici onay bekleniyor: {run.approval_id}
                    </p>
                  )}
                  {run.error && <p className="text-red-300">{run.error}</p>}
                </div>
              )}
              <p className="text-slate-500">
                Passkey bu arayüzde doğrulanmaz. Ayrı Windows Owner Control Plane kullanılmalıdır.
                Acil durdurma zaten gönderilmiş bir fiziksel input'u geri alamaz.
              </p>
            </>
          )}
        </div>
      )}
    </section>
  );
}
