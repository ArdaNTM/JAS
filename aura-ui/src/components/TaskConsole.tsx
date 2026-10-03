import { useState } from "react";
import type { FormEvent } from "react";
import { createTask } from "../api/client";
import { useTaskEvents } from "../hooks/useTaskEvents";
export function TaskConsole() {
  const [goal, setGoal] = useState("");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { events } = useTaskEvents(taskId);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!goal.trim()) return;

    setSubmitting(true);
    try {
      const task = await createTask({ goal: goal.trim() });
      setTaskId(task.task_id);
      setGoal("");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-cyan-400 font-mono p-6 flex flex-col items-center justify-start">
      <header className="w-full max-w-4xl border-b border-cyan-800 pb-4 mb-6 flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-widest text-cyan-300 drop-shadow-[0_0_10px_rgba(6,182,212,0.6)]">
            A.U.R.A. // J.A.R.V.I.S. CORE
          </h1>
          <p className="text-xs text-cyan-600">SYSTEM STATUS: ONLINE [DETERMINISTIC KERNEL]</p>
        </div>
        <div className="flex items-center space-x-2">
          <span className="h-3 w-3 rounded-full bg-cyan-400 animate-ping"></span>
          <span className="text-xs text-cyan-400">ACTIVE LINK</span>
        </div>
      </header>

      <main className="w-full max-w-4xl grid grid-cols-1 md:grid-cols-3 gap-6">
        <section className="md:col-span-1 bg-slate-900/80 border border-cyan-800/50 p-4 rounded-xl shadow-[0_0_15px_rgba(6,182,212,0.1)] flex flex-col justify-between">
          <form onSubmit={submit} className="flex flex-col h-full space-y-4">
            <div>
              <label className="block text-xs uppercase tracking-wider text-cyan-500 mb-2">
                Command Directive
              </label>
              <textarea
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                placeholder="Efendim, emrinizdeyim. Ne yapmamı istersiniz?"
                disabled={submitting}
                className="w-full h-36 bg-slate-950 border border-cyan-700/60 rounded-lg p-3 text-cyan-200 placeholder-cyan-700 focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400 text-sm resize-none"
              />
            </div>
            <button
              type="submit"
              disabled={submitting || !goal.trim()}
              className="w-full py-3 bg-cyan-950 hover:bg-cyan-900 border border-cyan-500 text-cyan-300 font-semibold rounded-lg tracking-widest uppercase text-xs transition duration-300 shadow-[0_0_10px_rgba(6,182,212,0.3)] disabled:opacity-50"
            >
              {submitting ? "İşleniyor..." : "Komutu İlet"}
            </button>
          </form>

          <div className="mt-6 border-t border-cyan-900 pt-4 text-center">
            <div className="inline-block w-16 h-16 rounded-full border-2 border-cyan-500 border-dashed animate-spin flex items-center justify-center">
              <div className="w-8 h-8 rounded-full bg-cyan-500/20 shadow-[0_0_10px_rgba(6,182,212,0.8)]"></div>
            </div>
            <p className="text-[10px] text-cyan-600 mt-2">ARC REACTOR STABLE</p>
          </div>
        </section>

        <section className="md:col-span-2 bg-slate-900/80 border border-cyan-800/50 p-4 rounded-xl shadow-[0_0_15px_rgba(6,182,212,0.1)] flex flex-col h-[500px]">
          <h2 className="text-xs uppercase tracking-wider text-cyan-500 border-b border-cyan-900 pb-2 mb-3 flex justify-between">
            <span>Live Telemetry Feed</span>
            <span>{taskId ? "TASK: " + taskId.slice(0, 8) : "STANDBY"}</span>
          </h2>
          <div className="flex-1 overflow-y-auto space-y-3 pr-2">
            {!taskId && (
              <div className="h-full flex items-center justify-center text-cyan-700 text-sm tracking-wider animate-pulse">
                J.A.R.V.I.S. hazır. Komut bekleniyor...
              </div>
            )}
            {events.map((event, index) => (
              <article key={index} className="bg-slate-950 border border-cyan-900/80 p-3 rounded-lg text-xs">
                <div className="flex justify-between text-cyan-600 mb-1">
                  <span className="font-bold text-cyan-400">[{event.type.toUpperCase()}]</span>
                  <span>{new Date().toLocaleTimeString()}</span>
                </div>
                <pre className="text-cyan-200 overflow-x-auto whitespace-pre-wrap font-mono">
                  {JSON.stringify(event.payload, null, 2)}
                </pre>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}



