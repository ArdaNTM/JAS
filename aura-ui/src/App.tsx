import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import {
  createTask,
  getHealth,
  type HealthResponse,
  type TaskStep,
} from "./api/client";
import { useAuraVoice } from "./voice/useAuraVoice";

function makeId(): string {
  return crypto.randomUUID?.() ?? `task-${Date.now()}`;
}

function ArcReactor({ active }: { active: boolean }) {
  return (
    <div className="relative flex h-44 w-44 items-center justify-center">
      <div className={`absolute inset-0 rounded-full border border-cyan-400/35 ${active ? "animate-[spin_14s_linear_infinite]" : ""}`} />
      <div className="absolute inset-4 rounded-full border border-cyan-500/50" />
      <div className={`absolute inset-9 rounded-full border-2 border-cyan-200 shadow-[0_0_28px_rgba(34,211,238,.85),inset_0_0_26px_rgba(34,211,238,.28)] ${active ? "animate-pulse" : ""}`} />
      <div className="h-9 w-9 rounded-full bg-cyan-100 shadow-[0_0_38px_rgba(103,232,249,1)]" />
      <div className="absolute inset-0 animate-[spin_23s_linear_infinite_reverse] rounded-full border border-dashed border-cyan-500/35" />
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const online = ["healthy", "ready", "configured", "listening", "wake_detected"].includes(status);

  return (
    <span className={`inline-block h-2 w-2 rounded-full ${online ? "bg-cyan-300 shadow-[0_0_12px_rgba(103,232,249,.95)]" : "bg-amber-400 shadow-[0_0_12px_rgba(251,191,36,.85)]"}`} />
  );
}

export default function App() {
  const [goal, setGoal] = useState("");
  const [planJson, setPlanJson] = useState("[]");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [status, setStatus] = useState("STANDBY");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const voice = useAuraVoice((directive) => setGoal(directive));

  useEffect(() => {
    let mounted = true;

    const refresh = async () => {
      try {
        const result = await getHealth();
        if (mounted) setHealth(result);
      } catch {
        if (mounted) setHealth(null);
      }
    };

    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);

    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  const diagnostics = useMemo(
    () => Object.entries(health?.components ?? {}),
    [health],
  );

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const title = goal.trim();
    if (!title) {
      setError("A directive is required.");
      return;
    }

    let steps: TaskStep[];

    try {
      const candidate: unknown = JSON.parse(planJson);
      if (!Array.isArray(candidate) || candidate.length === 0) {
        throw new Error("Execution plan must contain at least one explicit step.");
      }
      steps = candidate as TaskStep[];
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Execution plan is invalid JSON.");
      return;
    }

    setSubmitting(true);
    setStatus("SUBMITTING");

    try {
      const result = await createTask({
        task_id: makeId(),
        principal_id: "agent:desktop",
        title,
        resource_scope: import.meta.env.VITE_RESOURCE_SCOPE ?? "D:/AURA/workspace",
        steps,
      });

      setTaskId(result.task_id);
      setStatus(result.state.toUpperCase());
      setGoal("");
    } catch (cause) {
      setStatus("FAILED");
      setError(cause instanceof Error ? cause.message : "AURA rejected the task.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#02070d] text-cyan-100">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_48%_0%,rgba(6,182,212,.16),transparent_36%),linear-gradient(rgba(34,211,238,.025)_1px,transparent_1px),linear-gradient(90deg,rgba(34,211,238,.025)_1px,transparent_1px)] bg-[size:auto,32px_32px,32px_32px]" />

      <div className="relative mx-auto max-w-[1550px] p-4 md:p-6">
        <header className="mb-5 flex flex-wrap items-center justify-between gap-4 border-b border-cyan-900/70 pb-4">
          <div>
            <h1 className="text-2xl font-black tracking-[.28em] text-cyan-200">A.U.R.A.</h1>
            <p className="mt-1 text-[9px] tracking-[.26em] text-slate-500">ARTIFICIAL USER RESPONSE ARCHITECTURE // CONTROLLED AUTONOMY</p>
          </div>

          <div className="flex items-center gap-3 rounded-full border border-cyan-700/60 bg-slate-950/85 px-4 py-2 shadow-[0_0_28px_rgba(34,211,238,.10)]">
            <StatusDot status={voice.state} />
            <div>
              <div className="text-[9px] font-bold tracking-[.18em] text-cyan-300">
                {voice.state.replace("_", " ").toUpperCase()}
              </div>
              <div className="max-w-60 text-[9px] text-slate-500">{voice.message}</div>
            </div>
            <button
              type="button"
              disabled={!voice.available}
              onClick={voice.state === "listening" ? voice.stop : voice.start}
              className="rounded-full border border-cyan-400/70 px-3 py-1 text-[9px] font-bold tracking-[.14em] text-cyan-200 disabled:opacity-40"
            >
              {voice.state === "listening" ? "STOP" : "LISTEN"}
            </button>
          </div>
        </header>

        <main className="grid grid-cols-1 gap-5 xl:grid-cols-[300px_minmax(0,1fr)_310px]">
          <aside className="rounded-xl border border-cyan-900/65 bg-slate-950/75 p-5">
            <div className="text-[10px] font-bold tracking-[.24em] text-cyan-500">ARC REACTOR</div>
            <div className="mt-4 flex justify-center"><ArcReactor active={submitting || voice.state === "listening"} /></div>
            <div className="mt-5 border-t border-cyan-950 pt-4 text-[10px]">
              <div className="flex justify-between"><span className="text-slate-500">CORE STATE</span><span className="text-cyan-300">{status}</span></div>
              <div className="mt-3 h-1 overflow-hidden rounded bg-slate-900"><div className="h-full w-[84%] bg-cyan-400 shadow-[0_0_12px_rgba(34,211,238,.9)]" /></div>
            </div>
          </aside>

          <section className="rounded-xl border border-cyan-900/65 bg-slate-950/75">
            <div className="flex justify-between border-b border-cyan-950 px-5 py-4">
              <div><div className="text-[10px] font-bold tracking-[.24em] text-cyan-500">COMMAND DECK</div><div className="mt-1 text-xs text-slate-500">Voice fills the directive; execution always requires an explicit governed plan.</div></div>
              <div className="font-mono text-[10px] text-cyan-300">{taskId ? taskId.slice(0, 12) : "NO ACTIVE TASK"}</div>
            </div>

            <form onSubmit={submit} className="space-y-4 p-5">
              <div>
                <label className="mb-2 block text-[9px] font-bold tracking-[.22em] text-cyan-600">DIRECTIVE</label>
                <textarea value={goal} onChange={(event) => setGoal(event.target.value)} rows={4} placeholder='“AURA, günlük raporu hazırla”' className="w-full resize-none rounded-lg border border-cyan-900 bg-[#020910] p-4 font-mono text-sm outline-none focus:border-cyan-400" />
              </div>

              <div>
                <label className="mb-2 block text-[9px] font-bold tracking-[.22em] text-cyan-600">EXPLICIT EXECUTION PLAN (JSON)</label>
                <textarea value={planJson} onChange={(event) => setPlanJson(event.target.value)} rows={7} spellCheck={false} className="w-full resize-none rounded-lg border border-cyan-950 bg-black/30 p-4 font-mono text-xs text-cyan-100 outline-none focus:border-cyan-400" />
                <p className="mt-2 text-[9px] leading-4 text-slate-600">AURA doğal dili sahte bir tool çağrısına dönüştürmez. Plan; step_id, capability_id, operation_id, tool_name ve risk_level içermelidir.</p>
              </div>

              {error && <div className="rounded border border-red-900/70 bg-red-950/25 p-3 text-xs text-red-300">{error}</div>}

              <div className="flex items-center justify-between gap-3">
                <span className="text-[9px] tracking-[.16em] text-slate-600">KERNEL → PERMISSION → MCP GATEWAY → PROVIDER</span>
                <button disabled={submitting} className="rounded border border-cyan-400 bg-cyan-950/65 px-6 py-3 text-[10px] font-bold tracking-[.18em] text-cyan-100 disabled:opacity-40">
                  {submitting ? "EXECUTING…" : "EXECUTE GOVERNED PLAN"}
                </button>
              </div>
            </form>
          </section>

          <aside className="rounded-xl border border-cyan-900/65 bg-slate-950/75 p-5">
            <div className="text-[10px] font-bold tracking-[.24em] text-cyan-500">SYSTEM DIAGNOSTICS</div>
            <div className="mt-4 space-y-3">
              {diagnostics.length ? diagnostics.map(([name, value]) => (
                <div key={name} className="flex items-center justify-between border-b border-slate-900 pb-2">
                  <span className="text-xs text-slate-400">{name}</span>
                  <span className="flex items-center gap-2 text-[10px] text-cyan-300"><StatusDot status={value.status} />{value.status}</span>
                </div>
              )) : <div className="text-xs text-slate-600">Backend diagnostics unavailable.</div>}
            </div>

            <div className="mt-8 border-t border-cyan-950 pt-4">
              <div className="text-[9px] font-bold tracking-[.18em] text-cyan-600">VOICE CAPABILITY</div>
              <p className="mt-2 text-[10px] leading-5 text-slate-500">This is browser speech recognition while the app is listening. A native always-on wake-word provider is intentionally not simulated.</p>
            </div>
          </aside>
        </main>
      </div>
    </div>
  );
}
